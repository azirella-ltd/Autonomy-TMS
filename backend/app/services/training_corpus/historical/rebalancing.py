"""Historical extractor for rebalancing TRM.

Rebalancing uses the same transfer_order data as to_execution but labels
from a different angle: the "decision" is whether to initiate an inter-site
transfer at all, framed as "did this transfer relieve a real imbalance?"
"""

import logging
from typing import AsyncIterator, Optional

from sqlalchemy import text as sql_text

from .base import BaseHistoricalExtractor, SampleRecord
from .state_reconstruction import StateReconstructor

logger = logging.getLogger(__name__)


class RebalancingHistoricalExtractor(BaseHistoricalExtractor):
    trm_type = "rebalancing"

    async def extract(
        self, tenant_id: int, config_id: int, since=None,
    ) -> AsyncIterator[SampleRecord]:
        state_rec = StateReconstructor(self.db)

        params = {"cid": config_id}
        where_since = ""
        if since is not None:
            where_since = " AND t.order_date >= :since"
            params["since"] = since

        result = await self.db.execute(
            sql_text(f"""
                SELECT li.id, li.product_id, li.quantity,
                       t.source_site_id, t.destination_site_id,
                       t.order_date,
                       t.actual_delivery_date
                FROM transfer_order t
                JOIN transfer_order_line_item li ON li.to_id = t.id
                WHERE t.config_id = :cid
                  AND t.order_date IS NOT NULL
                  AND li.product_id IS NOT NULL
                  {where_since}
                ORDER BY t.order_date ASC
            """),
            params,
        )
        rows = result.fetchall()
        logger.info("RebalancingHistoricalExtractor: %d transfer lines", len(rows))

        for row in rows:
            try:
                sample = await self._build_sample(row, state_rec, config_id)
                if sample is not None:
                    yield sample
            except Exception as e:
                logger.debug("Rebalance line %s skipped: %s", row.id, e)

    async def _build_sample(
        self, row, state_rec: StateReconstructor, config_id: int,
    ) -> Optional[SampleRecord]:
        order_date = row.order_date
        qty = float(row.quantity or 0)
        if qty <= 0 or order_date is None:
            return None

        src = await state_rec.inventory_at(config_id, row.product_id, row.source_site_id, order_date)
        dst = await state_rec.inventory_at(config_id, row.product_id, row.destination_site_id, order_date)
        dst_pol = await state_rec.policy_at(config_id, row.product_id, row.destination_site_id, order_date)

        # Was the source actually over-stocked or the dest actually short?
        src_excess = max(0, src.on_hand - (dst_pol.order_up_to_level or src.on_hand))
        dst_shortage = max(0, (dst_pol.reorder_point or 0) - dst.on_hand)
        justified = (src_excess > 0 or dst_shortage > 0)

        reward = 0.85 if justified else 0.45  # transfers with no clear imbalance reason
        label_weight = 1.0 if justified else 0.5

        return SampleRecord(
            trm_type="rebalancing",
            product_id=row.product_id,
            site_id=str(row.destination_site_id),
            decision_at=order_date,
            state_features={
                "src_on_hand": src.on_hand,
                "dst_on_hand": dst.on_hand,
                "dst_reorder_point": dst_pol.reorder_point,
                "dst_order_up_to": dst_pol.order_up_to_level,
                "src_excess": src_excess,
                "dst_shortage": dst_shortage,
            },
            action={
                "quantity": qty,
                "source_site": str(row.source_site_id) if row.source_site_id else None,
                "direction": "outbound" if src_excess > 0 else "inbound",
            },
            outcome={
                "justified": justified,
            },
            reward_components={"justified": justified, "shortage": dst_shortage, "excess": src_excess},
            aggregate_reward=reward,
            label_weight=label_weight,
        )
