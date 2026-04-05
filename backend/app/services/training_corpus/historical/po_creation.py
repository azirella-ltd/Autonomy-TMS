"""Historical extractor for po_creation TRM.

For every historical PO line in inbound_order_line, reconstructs:
- State at order_date - 1 (inventory, policy, demand stats, forecast)
- Action: the quantity and lead time the ERP chose
- Outcome: did the PO arrive on time, did a stockout occur between
  order and arrival, was the qty appropriate given realized demand
"""

import logging
from datetime import timedelta
from typing import AsyncIterator, Optional

from sqlalchemy import text as sql_text

from .base import BaseHistoricalExtractor, SampleRecord
from .state_reconstruction import StateReconstructor

logger = logging.getLogger(__name__)


class POCreationHistoricalExtractor(BaseHistoricalExtractor):
    trm_type = "po_creation"

    async def extract(
        self, tenant_id: int, config_id: int, since=None,
    ) -> AsyncIterator[SampleRecord]:
        state_rec = StateReconstructor(self.db)

        # Pull all PO lines with their parent order's timing.
        # We join so we can get order_date (decision time) from inbound_order.
        where_since = ""
        params = {"cid": config_id}
        if since is not None:
            where_since = " AND io.order_date >= :since"
            params["since"] = since

        result = await self.db.execute(
            sql_text(f"""
                SELECT iol.id                       AS line_id,
                       iol.product_id               AS product_id,
                       iol.to_site_id               AS site_id,
                       iol.quantity_submitted       AS ordered_qty,
                       iol.quantity_received        AS received_qty,
                       iol.expected_delivery_date   AS expected_date,
                       iol.order_receive_date       AS actual_receive_date,
                       iol.lead_time_days           AS line_lead_days,
                       io.order_date                AS order_date,
                       io.promised_delivery_date    AS promised_date,
                       io.actual_delivery_date      AS order_actual_date,
                       io.supplier_id               AS supplier_id,
                       io.status                    AS order_status
                FROM inbound_order_line iol
                JOIN inbound_order io ON io.id = iol.order_id
                WHERE iol.config_id = :cid
                  AND io.order_date IS NOT NULL
                  AND iol.product_id IS NOT NULL
                  AND iol.to_site_id IS NOT NULL
                  {where_since}
                ORDER BY io.order_date ASC, iol.id ASC
            """),
            params,
        )
        rows = result.fetchall()
        logger.info("POCreationHistoricalExtractor: %d PO lines to process", len(rows))

        for row in rows:
            try:
                sample = await self._build_sample(row, state_rec, config_id)
                if sample is not None:
                    yield sample
            except Exception as e:
                logger.debug("PO line %s skipped: %s", row.line_id, e)

    async def _build_sample(
        self, row, state_rec: StateReconstructor, config_id: int,
    ) -> Optional[SampleRecord]:
        order_date = row.order_date
        if order_date is None:
            return None

        # State at order_date (the ERP saw this when deciding to place the PO)
        inv = await state_rec.inventory_at(config_id, row.product_id, row.site_id, order_date)
        policy = await state_rec.policy_at(config_id, row.product_id, row.site_id, order_date)
        demand = await state_rec.demand_stats_at(config_id, row.product_id, row.site_id, order_date)
        fc_p50 = await state_rec.forecast_p50_at(config_id, row.product_id, row.site_id, order_date)

        ordered_qty = float(row.ordered_qty or 0)
        if ordered_qty <= 0:
            return None

        # Lead time: prefer expected - order for most accurate, else field
        if row.expected_date and order_date:
            planned_lt_days = (row.expected_date - order_date).days
        else:
            planned_lt_days = float(row.line_lead_days or 0) or 7.0

        # Outcome: compare expected vs actual arrival, did a stockout occur?
        actual_date = row.actual_receive_date or row.order_actual_date
        on_time = None
        lateness_days = None
        if actual_date and row.expected_date:
            lateness_days = (actual_date - row.expected_date).days
            on_time = lateness_days <= 0

        # Look-forward stockout check: did outbound_order_line have unfulfilled
        # demand between order_date and actual_date (or order_date + planned_lt)?
        stockout_qty = await self._stockout_in_window(
            config_id, row.product_id, row.site_id,
            start=order_date,
            end=(actual_date or (order_date + timedelta(days=int(planned_lt_days + 14)))),
        )

        # Reward / label weight logic
        reward_components = {
            "on_time": 1.0 if on_time else (0.0 if on_time is False else None),
            "lateness_days": lateness_days,
            "stockout_qty_during_lt": stockout_qty,
            "fill_rate": (float(row.received_qty or 0) / ordered_qty) if ordered_qty else None,
        }
        label_weight = self._label_weight(on_time, stockout_qty, ordered_qty)
        # Aggregate reward is a simple blend for ranking; trainer can recompute.
        reward = 0.0
        n = 0
        if on_time is not None:
            reward += (1.0 if on_time else 0.3)
            n += 1
        if stockout_qty is not None:
            # Penalty for stockouts during the lead time window
            reward += max(0.0, 1.0 - min(1.0, stockout_qty / max(ordered_qty, 1)))
            n += 1
        aggregate_reward = reward / n if n else 0.5

        state_features = {
            "inv_on_hand": inv.on_hand,
            "inv_in_transit": inv.in_transit,
            "inv_safety_stock": inv.safety_stock,
            "inv_as_of": inv.as_of.isoformat() if inv.as_of else None,
            "policy_ss": policy.ss_quantity,
            "policy_reorder_point": policy.reorder_point,
            "policy_order_up_to": policy.order_up_to_level,
            "policy_service_level": policy.service_level,
            "demand_mean_weekly": demand.mean_weekly,
            "demand_cv": demand.cv,
            "demand_observations": demand.observations,
            "forecast_p50": fc_p50,
        }
        action = {
            "ordered_quantity": ordered_qty,
            "planned_lead_time_days": float(planned_lt_days),
            "supplier_id": str(row.supplier_id) if row.supplier_id else None,
        }
        outcome = {
            "actual_lead_time_days": (
                (actual_date - order_date).days if actual_date else None
            ),
            "received_qty": float(row.received_qty) if row.received_qty is not None else None,
            "on_time_delivery": on_time,
            "lateness_days": lateness_days,
            "stockout_qty_during_window": stockout_qty,
            "order_status": row.order_status,
        }

        return SampleRecord(
            trm_type=self.trm_type,
            product_id=row.product_id,
            site_id=str(row.site_id),
            decision_at=order_date,  # order_date is a date, stored as ISO
            state_features=state_features,
            action=action,
            outcome=outcome,
            reward_components=reward_components,
            aggregate_reward=aggregate_reward,
            label_weight=label_weight,
        )

    async def _stockout_in_window(
        self, config_id: int, product_id: str, site_id, start, end,
    ) -> Optional[float]:
        """Unfulfilled demand (backlog_quantity or ordered - shipped) during window."""
        if start is None or end is None or end < start:
            return None
        r = await self.db.execute(
            sql_text("""
                SELECT COALESCE(SUM(
                    CASE
                        WHEN backlog_quantity IS NOT NULL THEN backlog_quantity
                        ELSE GREATEST(
                            COALESCE(ordered_quantity, 0) - COALESCE(shipped_quantity, 0),
                            0
                        )
                    END
                ), 0) AS unmet
                FROM outbound_order_line
                WHERE config_id = :cid
                  AND product_id = :pid
                  AND site_id = :sid
                  AND order_date >= :start
                  AND order_date <  :end
            """),
            {"cid": config_id, "pid": product_id, "sid": site_id,
             "start": start, "end": end},
        )
        row = r.fetchone()
        return float(row.unmet) if row and row.unmet is not None else 0.0

    @staticmethod
    def _label_weight(on_time, stockout_qty, ordered_qty) -> float:
        """BC label weight from outcome quality.

        A PO with on-time delivery and no stockout during lead time = 1.0
        (imitate this). A PO that failed to prevent a large stockout or
        arrived very late = near 0 (don't imitate).
        """
        w = 1.0
        if on_time is False:
            w *= 0.7
        if stockout_qty is not None and ordered_qty > 0:
            sr = stockout_qty / ordered_qty
            if sr > 0.1:
                w *= max(0.2, 1.0 - sr)  # degrade as stockout ratio grows
        return max(0.1, min(1.0, w))
