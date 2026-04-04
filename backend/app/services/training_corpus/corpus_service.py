"""
TrainingCorpusService — main API for the unified training corpus.

Entry point for:
  - create_corpus(config_id): full generation pipeline (extract -> perturb -> simulate -> aggregate)
  - get_samples(config_id, layer, ...): retrieve training samples for a specific layer
  - append_real_outcome(decision_id, outcome): add a real decision to the corpus
  - compute_weights(config_id): update sample weights based on age and origin
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, and_, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training_corpus import TrainingCorpusSample

logger = logging.getLogger(__name__)


class TrainingCorpusService:
    """Main service for managing the unified training corpus."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Generation Pipeline ──

    async def create_corpus(
        self,
        tenant_id: int,
        config_id: int,
        num_perturbations: int = 500,
        planning_horizon_weeks: int = 26,
    ) -> Dict[str, Any]:
        """Full corpus generation pipeline for a tenant's config.

        Steps:
          1. Extract ERP baseline
          2. Generate N perturbations
          3. For each perturbation: run Digital Twin simulation with TRMs
          4. Capture TRM decisions as Layer 1 samples
          5. Aggregate upward to Layer 1.5, 2, 4

        Returns summary with sample counts per layer.
        """
        from .erp_baseline_extractor import ERPBaselineExtractor
        from .perturbation_generator import PerturbationGenerator
        from .simulation_runner import SimulationRunner
        from .aggregator import TrainingCorpusAggregator

        logger.info(
            "TrainingCorpusService: creating corpus for tenant=%d config=%d perturbations=%d",
            tenant_id, config_id, num_perturbations,
        )

        # Step 1: Extract ERP baseline
        extractor = ERPBaselineExtractor(self.db)
        baseline = await extractor.extract(config_id)
        if not baseline.sites:
            return {"status": "error", "error": "No sites found in ERP baseline"}

        # Step 2: Generate perturbations
        generator = PerturbationGenerator(seed=config_id)
        perturbations = generator.generate(baseline, n=num_perturbations)

        # Step 3 & 4: Run simulations, capture TRM decisions as Layer 1 samples
        runner = SimulationRunner(self.db)
        layer1_sample_count = 0
        for i, perturbation in enumerate(perturbations):
            scenario_id = str(uuid.uuid4())
            samples = await runner.run_scenario(
                tenant_id=tenant_id,
                config_id=config_id,
                baseline=baseline,
                perturbation=perturbation,
                scenario_id=scenario_id,
                planning_horizon_weeks=planning_horizon_weeks,
            )
            # Persist as Layer 1 samples
            for sample in samples:
                self.db.add(TrainingCorpusSample(
                    tenant_id=tenant_id,
                    config_id=config_id,
                    layer=1.0,
                    scenario_id=scenario_id,
                    origin="perturbation",
                    trm_type=sample["trm_type"],
                    product_id=sample.get("product_id"),
                    site_id=sample.get("site_id"),
                    sample_data=sample,
                    reward=sample.get("aggregate_reward"),
                    weight=1.0,
                ))
                layer1_sample_count += 1

            if (i + 1) % 50 == 0:
                await self.db.flush()
                logger.info("Corpus generation: %d/%d perturbations complete", i + 1, num_perturbations)

        await self.db.flush()

        # Step 5: Aggregate upward
        aggregator = TrainingCorpusAggregator(self.db)
        agg_summary = await aggregator.aggregate_all_levels(
            tenant_id=tenant_id,
            config_id=config_id,
        )

        await self.db.commit()

        return {
            "status": "success",
            "tenant_id": tenant_id,
            "config_id": config_id,
            "num_perturbations": num_perturbations,
            "layer1_samples": layer1_sample_count,
            "layer1_5_samples": agg_summary.get("layer1_5_count", 0),
            "layer2_samples": agg_summary.get("layer2_count", 0),
            "layer4_samples": agg_summary.get("layer4_count", 0),
        }

    # ── Sample Retrieval ──

    async def get_samples(
        self,
        config_id: int,
        layer: float,
        trm_type: Optional[str] = None,
        site_id: Optional[str] = None,
        min_weight: float = 0.05,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve training samples for a specific layer.

        Used by layer-specific trainers:
          - TRM trainer: layer=1.0, trm_type="po_creation" (etc.)
          - Site tGNN trainer: layer=1.5, site_id=site
          - Tactical tGNN trainers: layer=2.0
          - S&OP GraphSAGE trainer: layer=4.0

        Args:
            config_id: Supply chain config scope
            layer: 1.0, 1.5, 2.0, or 4.0
            trm_type: Filter by TRM type (Layer 1 only)
            site_id: Filter by site (Layer 1, 1.5 only)
            min_weight: Exclude low-weight (decayed) samples
            limit: Optional cap on number of samples returned

        Returns:
            List of sample dicts ready for training
        """
        query = (
            select(TrainingCorpusSample)
            .where(TrainingCorpusSample.config_id == config_id)
            .where(TrainingCorpusSample.layer == layer)
            .where(TrainingCorpusSample.weight >= min_weight)
        )
        if trm_type:
            query = query.where(TrainingCorpusSample.trm_type == trm_type)
        if site_id:
            query = query.where(TrainingCorpusSample.site_id == site_id)

        query = query.order_by(TrainingCorpusSample.created_at.desc())
        if limit:
            query = query.limit(limit)

        result = await self.db.execute(query)
        samples = result.scalars().all()
        return [s.to_dict() for s in samples]

    # ── Real Outcome Append ──

    async def append_real_outcome(
        self,
        tenant_id: int,
        config_id: int,
        decision_id: int,
        trm_type: str,
        sample_data: Dict[str, Any],
        reward: float,
        product_id: Optional[str] = None,
        site_id: Optional[str] = None,
    ) -> int:
        """Append a real decision outcome as a new Layer 1 sample.

        Called by OutcomeCollectorService after the reward for a live
        decision has been measured. The aggregator will re-roll this
        sample into higher layers on the next retraining cycle.
        """
        sample = TrainingCorpusSample(
            tenant_id=tenant_id,
            config_id=config_id,
            layer=1.0,
            scenario_id=f"real_{decision_id}",
            origin="real",
            trm_type=trm_type,
            product_id=product_id,
            site_id=site_id,
            sample_data=sample_data,
            reward=reward,
            weight=2.0,  # Real outcomes weighted higher than perturbations
            decision_id=decision_id,
        )
        self.db.add(sample)
        await self.db.flush()
        return sample.id

    # ── Weight Decay ──

    async def compute_weights(self, config_id: int) -> int:
        """Update sample weights based on age.

        Weight formula:
            w = base * exp(-age_days / 365)  # 1-year half-life
            origin_factor: real = 2.0, perturbation = 1.0

        Samples with w < 0.05 are pruned.
        """
        try:
            await self.db.execute(
                sql_text("""
                    UPDATE training_corpus
                    SET weight = CASE
                        WHEN origin = 'real' THEN 2.0 * EXP(-EXTRACT(EPOCH FROM (NOW() - created_at)) / (365 * 86400))
                        ELSE 1.0 * EXP(-EXTRACT(EPOCH FROM (NOW() - created_at)) / (365 * 86400))
                    END
                    WHERE config_id = :cid
                """),
                {"cid": config_id},
            )
            # Delete samples with very low weight (saves index space)
            result = await self.db.execute(
                sql_text("""
                    DELETE FROM training_corpus
                    WHERE config_id = :cid AND weight < 0.05
                """),
                {"cid": config_id},
            )
            await self.db.commit()
            return result.rowcount
        except Exception as e:
            logger.error("Weight decay failed: %s", e)
            await self.db.rollback()
            return 0

    # ── Stats ──

    async def get_stats(self, config_id: int) -> Dict[str, Any]:
        """Return corpus statistics for a config."""
        result = await self.db.execute(
            sql_text("""
                SELECT
                    layer,
                    origin,
                    COUNT(*) as count,
                    AVG(reward) as avg_reward,
                    AVG(weight) as avg_weight
                FROM training_corpus
                WHERE config_id = :cid
                GROUP BY layer, origin
                ORDER BY layer, origin
            """),
            {"cid": config_id},
        )
        rows = result.fetchall()
        return {
            "config_id": config_id,
            "by_layer": [
                {
                    "layer": float(row.layer),
                    "origin": row.origin,
                    "count": row.count,
                    "avg_reward": float(row.avg_reward) if row.avg_reward else None,
                    "avg_weight": float(row.avg_weight) if row.avg_weight else None,
                }
                for row in rows
            ],
        }
