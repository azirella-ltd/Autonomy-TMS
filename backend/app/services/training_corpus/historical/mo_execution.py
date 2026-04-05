"""Historical extractor for mo_execution TRM.

Every production_orders row is one historical MO release decision.
Outcome: actual vs planned completion, yield, downstream availability.
"""

import logging
from typing import AsyncIterator, Optional

from sqlalchemy import text as sql_text

from .base import BaseHistoricalExtractor, SampleRecord
from .state_reconstruction import StateReconstructor

logger = logging.getLogger(__name__)


class MOExecutionHistoricalExtractor(BaseHistoricalExtractor):
    trm_type = "mo_execution"

    async def extract(
        self, tenant_id: int, config_id: int, since=None,
    ) -> AsyncIterator[SampleRecord]:
        state_rec = StateReconstructor(self.db)

        params = {"cid": config_id}
        where_since = ""
        if since is not None:
            where_since = " AND released_date >= :since"
            params["since"] = since

        result = await self.db.execute(
            sql_text(f"""
                SELECT id, item_id AS product_id, site_id,
                       planned_quantity, actual_quantity, scrap_quantity,
                       yield_percentage,
                       released_date, planned_start_date, planned_completion_date,
                       actual_start_date, actual_completion_date,
                       status, lead_time_planned
                FROM production_orders
                WHERE config_id = :cid
                  AND item_id IS NOT NULL
                  AND site_id IS NOT NULL
                  AND (released_date IS NOT NULL OR planned_start_date IS NOT NULL)
                  {where_since}
                ORDER BY COALESCE(released_date, planned_start_date) ASC
            """),
            params,
        )
        rows = result.fetchall()
        logger.info("MOExecutionHistoricalExtractor: %d production orders", len(rows))

        for row in rows:
            try:
                sample = await self._build_sample(row, state_rec, config_id)
                if sample is not None:
                    yield sample
            except Exception as e:
                logger.debug("MO %s skipped: %s", row.id, e)

    async def _build_sample(self, row, state_rec: StateReconstructor, config_id: int) -> Optional[SampleRecord]:
        decision_at = row.released_date or row.planned_start_date
        if decision_at is None:
            return None
        planned_qty = float(row.planned_quantity or 0)
        if planned_qty <= 0:
            return None

        inv = await state_rec.inventory_at(config_id, row.product_id, row.site_id, decision_at)
        demand = await state_rec.demand_stats_at(config_id, row.product_id, row.site_id, decision_at)
        fc_p50 = await state_rec.forecast_p50_at(config_id, row.product_id, row.site_id, decision_at)

        # Outcome
        actual_qty = float(row.actual_quantity or 0) if row.actual_quantity is not None else None
        yield_pct = float(row.yield_percentage or 0)
        on_time = None
        lateness_days = None
        if row.actual_completion_date and row.planned_completion_date:
            lateness_days = (row.actual_completion_date - row.planned_completion_date).days
            on_time = lateness_days <= 0

        reward = 0.5
        if on_time is True:
            reward += 0.25
        if actual_qty is not None and planned_qty > 0:
            fill_rate = min(1.0, actual_qty / planned_qty)
            reward += 0.25 * fill_rate
        reward = min(1.0, reward)

        label_weight = 1.0
        if on_time is False:
            label_weight *= 0.7
        if yield_pct and yield_pct < 85:
            label_weight *= 0.6

        return SampleRecord(
            trm_type=self.trm_type,
            product_id=row.product_id,
            site_id=str(row.site_id),
            decision_at=decision_at,
            state_features={
                "inv_on_hand": inv.on_hand,
                "inv_in_transit": inv.in_transit,
                "demand_mean_weekly": demand.mean_weekly,
                "demand_cv": demand.cv,
                "forecast_p50": fc_p50,
                "planned_lead_time_days": float(row.lead_time_planned or 0),
            },
            action={
                "planned_quantity": planned_qty,
                "planned_start": row.planned_start_date.isoformat() if row.planned_start_date else None,
                "planned_completion": row.planned_completion_date.isoformat() if row.planned_completion_date else None,
            },
            outcome={
                "actual_quantity": actual_qty,
                "scrap_quantity": float(row.scrap_quantity or 0),
                "yield_percentage": yield_pct,
                "on_time": on_time,
                "lateness_days": lateness_days,
                "status": row.status,
            },
            reward_components={"on_time": on_time, "yield": yield_pct},
            aggregate_reward=reward,
            label_weight=max(0.1, label_weight),
        )
