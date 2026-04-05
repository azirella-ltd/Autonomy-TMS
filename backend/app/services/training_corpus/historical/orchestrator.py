"""Orchestrator: run all historical extractors, persist samples, summarize coverage.

Called from the training_corpus provisioning step. Each extractor streams
SampleRecord instances; the orchestrator persists them into training_corpus
with origin='historical' and builds a coverage summary that the downstream
simulation step consults to decide where augmentation is needed.
"""

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training_corpus import TrainingCorpusSample

from .base import (
    BaseHistoricalExtractor,
    ExtractorCoverage,
    HistoricalExtractionSummary,
    SampleRecord,
)
from .atp_allocation import ATPAllocationHistoricalExtractor
from .forecast_adjustment import ForecastAdjustmentHistoricalExtractor
from .forecast_baseline import ForecastBaselineHistoricalExtractor
from .inventory_buffer import InventoryBufferHistoricalExtractor
from .maintenance_scheduling import MaintenanceSchedulingHistoricalExtractor
from .mo_execution import MOExecutionHistoricalExtractor
from .order_tracking import OrderTrackingHistoricalExtractor
from .po_creation import POCreationHistoricalExtractor
from .quality_disposition import QualityDispositionHistoricalExtractor
from .rebalancing import RebalancingHistoricalExtractor
from .subcontracting import SubcontractingHistoricalExtractor
from .to_execution import TOExecutionHistoricalExtractor

logger = logging.getLogger(__name__)


# Registry of all 12 per-TRM historical extractors. Each extractor yields
# SampleRecord instances; the orchestrator persists them as training_corpus
# rows with origin='historical'. Extractors with no underlying data return
# empty iterators — the orchestrator flags them as thin so the simulation
# stream can augment them.
EXTRACTORS: List[type[BaseHistoricalExtractor]] = [
    POCreationHistoricalExtractor,
    TOExecutionHistoricalExtractor,
    MOExecutionHistoricalExtractor,
    ATPAllocationHistoricalExtractor,
    InventoryBufferHistoricalExtractor,
    QualityDispositionHistoricalExtractor,
    MaintenanceSchedulingHistoricalExtractor,
    SubcontractingHistoricalExtractor,
    OrderTrackingHistoricalExtractor,
    RebalancingHistoricalExtractor,
    ForecastBaselineHistoricalExtractor,
    ForecastAdjustmentHistoricalExtractor,
]


class HistoricalExtractionOrchestrator:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def extract_all(
        self, tenant_id: int, config_id: int, since: Optional[datetime] = None,
    ) -> HistoricalExtractionSummary:
        summary = HistoricalExtractionSummary(
            tenant_id=tenant_id,
            config_id=config_id,
            total_samples=0,
            started_at=datetime.utcnow(),
        )

        for cls in EXTRACTORS:
            extractor = cls(self.db)
            cov = await self._run_one(extractor, tenant_id, config_id, since)
            summary.coverage[extractor.trm_type] = cov
            summary.total_samples += cov.sample_count

        summary.finished_at = datetime.utcnow()
        return summary

    async def _run_one(
        self,
        extractor: BaseHistoricalExtractor,
        tenant_id: int,
        config_id: int,
        since: Optional[datetime],
    ) -> ExtractorCoverage:
        count = 0
        earliest: Optional[datetime] = None
        latest: Optional[datetime] = None
        sites: set = set()
        products: set = set()
        reward_sum = 0.0
        label_buckets = {"good": 0, "mixed": 0, "poor": 0}

        batch: List[TrainingCorpusSample] = []
        BATCH = 500

        async for rec in extractor.extract(tenant_id, config_id, since=since):
            count += 1
            reward_sum += rec.aggregate_reward
            if rec.label_weight >= 0.8:
                label_buckets["good"] += 1
            elif rec.label_weight >= 0.4:
                label_buckets["mixed"] += 1
            else:
                label_buckets["poor"] += 1
            sites.add(rec.site_id)
            products.add(rec.product_id)
            if earliest is None or (rec.decision_at and rec.decision_at < earliest):
                earliest = rec.decision_at
            if latest is None or (rec.decision_at and rec.decision_at > latest):
                latest = rec.decision_at

            batch.append(
                TrainingCorpusSample(
                    tenant_id=tenant_id,
                    config_id=config_id,
                    layer=1.0,
                    scenario_id=f"historical_{extractor.trm_type}",
                    origin="historical",
                    trm_type=rec.trm_type,
                    product_id=rec.product_id,
                    site_id=rec.site_id,
                    sample_data={
                        "decision_at": rec.decision_at.isoformat() if rec.decision_at else None,
                        "state_features": rec.state_features,
                        "action": rec.action,
                        "outcome": rec.outcome,
                        "reward_components": rec.reward_components,
                        "teacher_source": "historical",
                    },
                    reward=rec.aggregate_reward,
                    weight=rec.label_weight,
                )
            )
            if len(batch) >= BATCH:
                self.db.add_all(batch)
                await self.db.flush()
                for obj in batch:
                    self.db.expunge(obj)
                batch.clear()

        if batch:
            self.db.add_all(batch)
            await self.db.flush()
            for obj in batch:
                self.db.expunge(obj)
            batch.clear()

        await self.db.commit()

        return ExtractorCoverage(
            trm_type=extractor.trm_type,
            sample_count=count,
            earliest=earliest,
            latest=latest,
            distinct_sites=len(sites),
            distinct_products=len(products),
            avg_reward=(reward_sum / count) if count else 0.0,
            label_weight_distribution=label_buckets,
        )
