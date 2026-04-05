"""Historical extractor for atp_allocation TRM.

Uses outbound_order_line as the primary source: each line is a historical
ATP decision, where `promised_quantity` and `promised_delivery_date` are the
action, and `shipped_quantity` / `backlog_quantity` are the realized outcome.

If the dedicated aatp_consumption_record or order_promise tables have data,
they're richer and should be preferred — falls back to outbound_order_line
otherwise.
"""

import logging
from typing import AsyncIterator, Optional

from sqlalchemy import text as sql_text

from .base import BaseHistoricalExtractor, SampleRecord

logger = logging.getLogger(__name__)


class ATPAllocationHistoricalExtractor(BaseHistoricalExtractor):
    trm_type = "atp_allocation"

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
                SELECT id, product_id, site_id,
                       ordered_quantity, promised_quantity, shipped_quantity,
                       backlog_quantity, status, priority_code,
                       order_date, promised_delivery_date, requested_delivery_date
                FROM outbound_order_line
                WHERE config_id = :cid
                  AND product_id IS NOT NULL
                  AND site_id IS NOT NULL
                  AND order_date IS NOT NULL
                  {where_since}
                ORDER BY order_date ASC
            """),
            params,
        )
        rows = result.fetchall()
        logger.info("ATPAllocationHistoricalExtractor: %d outbound lines", len(rows))

        for row in rows:
            try:
                sample = self._build_sample(row)
                if sample is not None:
                    yield sample
            except Exception as e:
                logger.debug("ATP line %s skipped: %s", row.id, e)

    @staticmethod
    def _build_sample(row) -> Optional[SampleRecord]:
        if row.order_date is None:
            return None
        ordered = float(row.ordered_quantity or 0)
        if ordered <= 0:
            return None
        promised = float(row.promised_quantity or 0)
        shipped = float(row.shipped_quantity or 0)
        backlog = float(row.backlog_quantity or 0)

        promise_rate = (promised / ordered) if ordered else None
        fill_rate = (shipped / ordered) if ordered else None
        honored = (shipped >= promised * 0.95) if promised > 0 else None

        # Reward: high promise coverage + honored promise = good ATP decision
        reward = 0.5
        if promise_rate is not None:
            reward += 0.25 * min(1.0, promise_rate)
        if honored is True:
            reward += 0.25
        reward = min(1.0, reward)

        label_weight = 1.0
        if honored is False:
            label_weight *= 0.5

        return SampleRecord(
            trm_type="atp_allocation",
            product_id=row.product_id,
            site_id=str(row.site_id),
            decision_at=row.order_date,
            state_features={
                "priority_code": row.priority_code,
            },
            action={
                "ordered_quantity": ordered,
                "promised_quantity": promised,
                "promised_date": row.promised_delivery_date.isoformat() if row.promised_delivery_date else None,
            },
            outcome={
                "shipped_quantity": shipped,
                "backlog_quantity": backlog,
                "promise_rate": promise_rate,
                "fill_rate": fill_rate,
                "honored": honored,
                "status": row.status,
            },
            reward_components={
                "promise_rate": promise_rate,
                "fill_rate": fill_rate,
                "honored": honored,
            },
            aggregate_reward=reward,
            label_weight=label_weight,
        )
