"""Historical extractor for maintenance_scheduling TRM."""

import logging
from typing import AsyncIterator, Optional

from sqlalchemy import text as sql_text

from .base import BaseHistoricalExtractor, SampleRecord

logger = logging.getLogger(__name__)


class MaintenanceSchedulingHistoricalExtractor(BaseHistoricalExtractor):
    trm_type = "maintenance_scheduling"

    async def extract(
        self, tenant_id: int, config_id: int, since=None,
    ) -> AsyncIterator[SampleRecord]:
        params = {"cid": config_id}
        where_since = ""
        if since is not None:
            where_since = " AND order_date >= :since"
            params["since"] = since

        result = await self.db.execute(
            sql_text(f"""
                SELECT id, asset_id, asset_category, site_id,
                       maintenance_type, priority, status,
                       order_date, scheduled_start_date, scheduled_end_date,
                       actual_start_date
                FROM maintenance_order
                WHERE config_id = :cid
                  AND site_id IS NOT NULL
                  {where_since}
                ORDER BY order_date ASC NULLS LAST
            """),
            params,
        )
        rows = result.fetchall()
        logger.info("MaintenanceSchedulingHistoricalExtractor: %d maintenance orders", len(rows))

        for row in rows:
            try:
                sample = self._build_sample(row)
                if sample is not None:
                    yield sample
            except Exception as e:
                logger.debug("MX %s skipped: %s", row.id, e)

    @staticmethod
    def _build_sample(row) -> Optional[SampleRecord]:
        decision_at = row.order_date or row.scheduled_start_date
        if decision_at is None:
            return None
        mtype = (row.maintenance_type or "").lower()
        is_preventive = "prevent" in mtype or "planned" in mtype or "schedul" in mtype
        is_corrective = "correct" in mtype or "breakdown" in mtype or "reactive" in mtype

        # Preventive on-schedule = best; corrective = penalty (should have been caught earlier)
        reward = 0.8 if is_preventive else (0.4 if is_corrective else 0.6)
        label_weight = 0.8 if is_preventive else 0.5

        return SampleRecord(
            trm_type="maintenance_scheduling",
            product_id=str(row.asset_id) if row.asset_id else "unknown",
            site_id=str(row.site_id),
            decision_at=decision_at,
            state_features={
                "asset_category": row.asset_category,
                "priority": row.priority,
            },
            action={
                "maintenance_type": row.maintenance_type,
                "scheduled_start": row.scheduled_start_date.isoformat() if row.scheduled_start_date else None,
                "scheduled_end": row.scheduled_end_date.isoformat() if row.scheduled_end_date else None,
            },
            outcome={
                "was_preventive": is_preventive,
                "was_corrective": is_corrective,
                "status": row.status,
            },
            reward_components={"preventive": is_preventive, "corrective": is_corrective},
            aggregate_reward=reward,
            label_weight=label_weight,
        )
