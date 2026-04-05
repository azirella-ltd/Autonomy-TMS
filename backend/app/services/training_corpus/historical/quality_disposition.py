"""Historical extractor for quality_disposition TRM.

Every quality_order row is one historical disposition decision. The quality_order
table carries the real disposition (accept/reject/rework/scrap) and outcome
metrics (defect_rate, quality_cost, etc.) directly — no need to aggregate line
items.
"""

import logging
from typing import AsyncIterator, Optional

from sqlalchemy import text as sql_text

from .base import BaseHistoricalExtractor, SampleRecord

logger = logging.getLogger(__name__)


class QualityDispositionHistoricalExtractor(BaseHistoricalExtractor):
    trm_type = "quality_disposition"

    async def extract(
        self, tenant_id: int, config_id: int, since=None,
    ) -> AsyncIterator[SampleRecord]:
        params = {"cid": config_id}
        where_since = ""
        if since is not None:
            where_since = " AND COALESCE(order_date, created_at) >= :since"
            params["since"] = since

        result = await self.db.execute(
            sql_text(f"""
                SELECT id, product_id, site_id,
                       inspection_type, inspection_plan_id,
                       inspection_quantity, sample_size,
                       accepted_quantity, rejected_quantity,
                       rework_quantity, scrap_quantity, use_as_is_quantity,
                       disposition, disposition_reason, disposition_decided_at,
                       defect_rate, defect_category, severity_level,
                       total_quality_cost, hold_inventory,
                       order_date, inspection_start_date, inspection_end_date,
                       created_at, status
                FROM quality_order
                WHERE config_id = :cid
                  AND product_id IS NOT NULL
                  AND site_id IS NOT NULL
                  {where_since}
                ORDER BY COALESCE(order_date, created_at) ASC
            """),
            params,
        )
        rows = result.fetchall()
        logger.info("QualityDispositionHistoricalExtractor: %d quality orders", len(rows))

        for row in rows:
            try:
                sample = self._build_sample(row)
                if sample is not None:
                    yield sample
            except Exception as e:
                logger.debug("QO %s skipped: %s", row.id, e)

    @staticmethod
    def _build_sample(row) -> Optional[SampleRecord]:
        decision_at = row.disposition_decided_at or row.order_date or row.created_at
        if decision_at is None:
            return None

        insp_qty = float(row.inspection_quantity or 0) or float(row.sample_size or 0)
        defect_rate = float(row.defect_rate or 0)
        disposition = (row.disposition or "").lower()

        accepted = float(row.accepted_quantity or 0)
        rejected = float(row.rejected_quantity or 0)
        reworked = float(row.rework_quantity or 0)
        scrapped = float(row.scrap_quantity or 0)

        # Reward: disposition should match defect severity
        # - high defect rate → reject/rework/scrap is correct
        # - low defect rate → accept/use-as-is is correct
        reward = 0.5
        if defect_rate > 0.1 and disposition in ("reject", "rework", "scrap", "rejected"):
            reward = 0.9
        elif defect_rate <= 0.03 and disposition in ("accept", "accepted", "use_as_is", "released"):
            reward = 0.9
        elif disposition in ("accept", "reject", "rework", "scrap", "accepted", "rejected", "released", "use_as_is"):
            reward = 0.65
        else:
            reward = 0.4  # unknown / partial disposition

        label_weight = 1.0 if insp_qty > 0 else 0.3
        if row.severity_level and str(row.severity_level).lower() in ("critical", "high"):
            # Critical lots carry higher training signal
            label_weight = min(1.0, label_weight * 1.2)

        return SampleRecord(
            trm_type="quality_disposition",
            product_id=row.product_id,
            site_id=str(row.site_id),
            decision_at=decision_at,
            state_features={
                "inspection_type": row.inspection_type,
                "inspection_quantity": insp_qty,
                "defect_rate": defect_rate,
                "defect_category": row.defect_category,
                "severity_level": row.severity_level,
                "hold_inventory": bool(row.hold_inventory) if row.hold_inventory is not None else None,
            },
            action={
                "disposition": disposition,
                "accepted_quantity": accepted,
                "rejected_quantity": rejected,
                "rework_quantity": reworked,
                "scrap_quantity": scrapped,
            },
            outcome={
                "total_quality_cost": float(row.total_quality_cost or 0),
                "status": row.status,
            },
            reward_components={
                "defect_rate": defect_rate,
                "disposition": disposition,
                "quality_cost": float(row.total_quality_cost or 0),
            },
            aggregate_reward=reward,
            label_weight=max(0.1, min(1.0, label_weight)),
        )
