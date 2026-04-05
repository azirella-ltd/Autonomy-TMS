"""Historical extractor for inventory_buffer TRM.

One sample per active inv_policy row. The policy is the "action" the ERP
chose; the outcome is the service level actually achieved during the policy's
effective window, measured from outbound_order_line fill vs demand.
"""

import logging
from datetime import date, datetime, timedelta
from typing import AsyncIterator, Optional

from sqlalchemy import text as sql_text

from .base import BaseHistoricalExtractor, SampleRecord
from .state_reconstruction import StateReconstructor

logger = logging.getLogger(__name__)


class InventoryBufferHistoricalExtractor(BaseHistoricalExtractor):
    trm_type = "inventory_buffer"

    async def extract(
        self, tenant_id: int, config_id: int, since=None,
    ) -> AsyncIterator[SampleRecord]:
        state_rec = StateReconstructor(self.db)

        result = await self.db.execute(
            sql_text("""
                SELECT id, product_id, site_id,
                       ss_policy, ss_quantity, service_level,
                       reorder_point, order_up_to_level,
                       eff_start_date, eff_end_date
                FROM inv_policy
                WHERE config_id = :cid
                  AND product_id IS NOT NULL
                  AND site_id IS NOT NULL
            """),
            {"cid": config_id},
        )
        rows = result.fetchall()
        logger.info("InventoryBufferHistoricalExtractor: %d inv_policy rows", len(rows))

        for row in rows:
            try:
                sample = await self._build_sample(row, state_rec, config_id)
                if sample is not None:
                    yield sample
            except Exception as e:
                logger.debug("inv_policy %s skipped: %s", row.id, e)

    async def _build_sample(
        self, row, state_rec: StateReconstructor, config_id: int,
    ) -> Optional[SampleRecord]:
        # Decision anchor: policy effective start (or a sensible default)
        eff_start: Optional[date] = row.eff_start_date
        eff_end: Optional[date] = row.eff_end_date
        if eff_start is None:
            # Use the earliest inv_level observation we have for this (p,s) as anchor
            r = await self.db.execute(
                sql_text("""
                    SELECT MIN(inventory_date) AS d FROM inv_level
                    WHERE config_id = :cid AND product_id = :pid AND site_id = :sid
                """),
                {"cid": config_id, "pid": row.product_id, "sid": row.site_id},
            )
            d = r.fetchone().d
            if d is None:
                return None
            eff_start = d
        if eff_end is None:
            eff_end = eff_start + timedelta(days=365)

        # Demand stats over the policy's effective window
        demand = await state_rec.demand_stats_at(
            config_id, row.product_id, row.site_id,
            at=eff_end, lookback_weeks=max(1, (eff_end - eff_start).days // 7),
        )

        # Service-level outcome: fraction of (ordered) that was shipped on time
        # during the policy window
        r = await self.db.execute(
            sql_text("""
                SELECT
                    COALESCE(SUM(ordered_quantity), 0)       AS ordered,
                    COALESCE(SUM(shipped_quantity), 0)       AS shipped,
                    COALESCE(SUM(backlog_quantity), 0)       AS backlog,
                    COUNT(*)                                 AS orders
                FROM outbound_order_line
                WHERE config_id = :cid
                  AND product_id = :pid
                  AND site_id = :sid
                  AND order_date >= :start
                  AND order_date <  :end
            """),
            {"cid": config_id, "pid": row.product_id, "sid": row.site_id,
             "start": eff_start, "end": eff_end},
        )
        oo = r.fetchone()
        ordered = float(oo.ordered or 0)
        shipped = float(oo.shipped or 0)
        backlog = float(oo.backlog or 0)
        achieved_service_level = (shipped / ordered) if ordered > 0 else None
        n_orders = int(oo.orders or 0)

        target_sl = float(row.service_level) if row.service_level is not None else None

        # Reward: did the policy meet its service-level target?
        if target_sl is not None and achieved_service_level is not None:
            gap = achieved_service_level - target_sl
            reward = max(0.0, min(1.0, 0.5 + gap))  # hit target = 0.5, +exceed / -miss
        elif achieved_service_level is not None:
            reward = achieved_service_level
        else:
            reward = 0.5

        label_weight = 1.0
        if n_orders < 3:
            # Too few observations to trust the outcome label
            label_weight *= 0.3
        if achieved_service_level is not None and target_sl is not None:
            miss = target_sl - achieved_service_level
            if miss > 0.1:
                label_weight *= 0.5  # big miss → don't over-fit

        return SampleRecord(
            trm_type=self.trm_type,
            product_id=row.product_id,
            site_id=str(row.site_id),
            decision_at=datetime.combine(eff_start, datetime.min.time()),
            state_features={
                "demand_mean_weekly": demand.mean_weekly,
                "demand_std_weekly": demand.std_weekly,
                "demand_cv": demand.cv,
                "demand_observations": demand.observations,
                "policy_effective_days": (eff_end - eff_start).days,
            },
            action={
                "ss_policy": row.ss_policy,
                "ss_quantity": float(row.ss_quantity or 0),
                "target_service_level": target_sl,
                "reorder_point": float(row.reorder_point or 0),
                "order_up_to_level": float(row.order_up_to_level or 0),
            },
            outcome={
                "orders_in_window": n_orders,
                "total_ordered": ordered,
                "total_shipped": shipped,
                "total_backlog": backlog,
                "achieved_service_level": achieved_service_level,
            },
            reward_components={
                "achieved_sl": achieved_service_level,
                "target_sl": target_sl,
                "backlog": backlog,
            },
            aggregate_reward=reward,
            label_weight=max(0.1, label_weight),
        )
