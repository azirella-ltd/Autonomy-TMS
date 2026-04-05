"""Historical extractor for to_execution TRM.

Every transfer_order (+ line items) becomes one or more samples.
- State at order_date: source + dest inventory, in-transit, demand at dest
- Action: source/dest/quantity/requested arrival
- Outcome: actual ship/arrival, destination stockout avoidance during window
"""

import logging
from datetime import timedelta
from typing import AsyncIterator, Optional

from sqlalchemy import text as sql_text

from .base import BaseHistoricalExtractor, SampleRecord
from .state_reconstruction import StateReconstructor

logger = logging.getLogger(__name__)


class TOExecutionHistoricalExtractor(BaseHistoricalExtractor):
    trm_type = "to_execution"

    async def extract(
        self, tenant_id: int, config_id: int, since=None,
    ) -> AsyncIterator[SampleRecord]:
        state_rec = StateReconstructor(self.db)
        where_since = ""
        params = {"cid": config_id}
        if since is not None:
            where_since = " AND t.order_date >= :since"
            params["since"] = since

        result = await self.db.execute(
            sql_text(f"""
                SELECT
                    li.id                         AS line_id,
                    li.product_id                 AS product_id,
                    t.source_site_id              AS source_site,
                    t.destination_site_id         AS dest_site,
                    li.quantity                   AS qty,
                    li.requested_delivery_date    AS requested_arrival,
                    li.actual_delivery_date       AS line_actual_arrival,
                    t.order_date                  AS order_date,
                    t.estimated_delivery_date     AS planned_arrival,
                    t.actual_delivery_date        AS order_actual_arrival,
                    t.status                      AS order_status
                FROM transfer_order t
                JOIN transfer_order_line_item li ON li.to_id = t.id
                WHERE t.config_id = :cid
                  AND t.order_date IS NOT NULL
                  AND li.product_id IS NOT NULL
                  AND t.destination_site_id IS NOT NULL
                  {where_since}
                ORDER BY t.order_date ASC, li.id ASC
            """),
            params,
        )
        rows = result.fetchall()
        logger.info("TOExecutionHistoricalExtractor: %d TO lines to process", len(rows))

        for row in rows:
            try:
                sample = await self._build_sample(row, state_rec, config_id)
                if sample is not None:
                    yield sample
            except Exception as e:
                logger.debug("TO line %s skipped: %s", row.line_id, e)

    async def _build_sample(
        self, row, state_rec: StateReconstructor, config_id: int,
    ) -> Optional[SampleRecord]:
        order_date = row.order_date
        if order_date is None:
            return None
        qty = float(row.qty or 0)
        if qty <= 0:
            return None

        # State at decision time: both source and dest
        src_inv = await state_rec.inventory_at(config_id, row.product_id, row.source_site, order_date)
        dst_inv = await state_rec.inventory_at(config_id, row.product_id, row.dest_site, order_date)
        dst_demand = await state_rec.demand_stats_at(config_id, row.product_id, row.dest_site, order_date)
        dst_policy = await state_rec.policy_at(config_id, row.product_id, row.dest_site, order_date)

        # Outcome: actual arrival timing + destination stockout during window
        actual_arrival = row.line_actual_arrival or row.order_actual_arrival
        planned_arrival = row.requested_arrival or row.planned_arrival
        on_time = None
        lateness_days = None
        if actual_arrival and planned_arrival:
            lateness_days = (actual_arrival - planned_arrival).days
            on_time = lateness_days <= 0

        window_end = actual_arrival or (
            planned_arrival + timedelta(days=7) if planned_arrival else order_date + timedelta(days=21)
        )
        dest_stockout = await state_rec.db.execute(
            sql_text("""
                SELECT COALESCE(SUM(GREATEST(
                    COALESCE(ordered_quantity, 0) - COALESCE(shipped_quantity, 0), 0
                )), 0) AS unmet
                FROM outbound_order_line
                WHERE config_id = :cid
                  AND product_id = :pid
                  AND site_id = :sid
                  AND order_date >= :start
                  AND order_date <  :end
            """),
            {"cid": config_id, "pid": row.product_id, "sid": row.dest_site,
             "start": order_date, "end": window_end},
        )
        stockout_qty = float((dest_stockout.fetchone().unmet) or 0)

        # Reward: covering a destination shortage with on-time arrival = good
        reward = 0.5
        if on_time is True:
            reward += 0.3
        if stockout_qty == 0:
            reward += 0.2
        reward = min(1.0, reward)

        label_weight = 1.0
        if on_time is False:
            label_weight *= 0.6
        if stockout_qty > qty * 0.2:
            label_weight *= 0.4
        label_weight = max(0.1, label_weight)

        return SampleRecord(
            trm_type=self.trm_type,
            product_id=row.product_id,
            site_id=str(row.dest_site),  # destination is the "owning" site for the decision
            decision_at=order_date,
            state_features={
                "src_on_hand": src_inv.on_hand,
                "src_in_transit": src_inv.in_transit,
                "dst_on_hand": dst_inv.on_hand,
                "dst_in_transit": dst_inv.in_transit,
                "dst_safety_stock": dst_inv.safety_stock,
                "dst_reorder_point": dst_policy.reorder_point,
                "dst_demand_mean_weekly": dst_demand.mean_weekly,
                "dst_demand_cv": dst_demand.cv,
            },
            action={
                "quantity": qty,
                "source_site": str(row.source_site) if row.source_site else None,
                "requested_arrival": planned_arrival.isoformat() if planned_arrival else None,
            },
            outcome={
                "actual_arrival": actual_arrival.isoformat() if actual_arrival else None,
                "on_time": on_time,
                "lateness_days": lateness_days,
                "dst_stockout_during_window": stockout_qty,
                "status": row.order_status,
            },
            reward_components={
                "on_time": 1.0 if on_time else (0.0 if on_time is False else None),
                "dst_stockout": stockout_qty,
            },
            aggregate_reward=reward,
            label_weight=label_weight,
        )
