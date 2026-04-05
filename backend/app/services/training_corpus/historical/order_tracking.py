"""Historical extractor for order_tracking TRM.

For each open/received inbound order line, the tracking decision is whether
to flag the order as at-risk (delayed). The historical "action" is the
implicit one: the ERP did nothing special and let the order proceed. The
outcome is whether the order actually arrived late.

This generates BC labels for the "alert / escalate" policy: when should a
TRM raise an order-tracking exception?
"""

import logging
from typing import AsyncIterator, Optional

from sqlalchemy import text as sql_text

from .base import BaseHistoricalExtractor, SampleRecord

logger = logging.getLogger(__name__)


class OrderTrackingHistoricalExtractor(BaseHistoricalExtractor):
    trm_type = "order_tracking"

    async def extract(
        self, tenant_id: int, config_id: int, since=None,
    ) -> AsyncIterator[SampleRecord]:
        params = {"cid": config_id}
        where_since = ""
        if since is not None:
            where_since = " AND io.order_date >= :since"
            params["since"] = since

        # Only orders that have completed (actual_delivery_date set) — that's
        # where we have a ground-truth outcome for "was it late?".
        result = await self.db.execute(
            sql_text(f"""
                SELECT iol.id, iol.product_id, iol.to_site_id AS site_id,
                       iol.quantity_submitted, iol.quantity_received,
                       iol.expected_delivery_date, iol.order_receive_date,
                       io.order_date, io.promised_delivery_date,
                       io.actual_delivery_date, io.supplier_id, io.status
                FROM inbound_order_line iol
                JOIN inbound_order io ON io.id = iol.order_id
                WHERE iol.config_id = :cid
                  AND io.order_date IS NOT NULL
                  AND (iol.order_receive_date IS NOT NULL OR io.actual_delivery_date IS NOT NULL)
                  {where_since}
                ORDER BY io.order_date ASC
            """),
            params,
        )
        rows = result.fetchall()
        logger.info("OrderTrackingHistoricalExtractor: %d tracked order lines", len(rows))

        for row in rows:
            try:
                sample = self._build_sample(row)
                if sample is not None:
                    yield sample
            except Exception as e:
                logger.debug("Order tracking line %s skipped: %s", row.id, e)

    @staticmethod
    def _build_sample(row) -> Optional[SampleRecord]:
        actual = row.order_receive_date or row.actual_delivery_date
        expected = row.expected_delivery_date or row.promised_delivery_date
        if actual is None or expected is None or row.order_date is None:
            return None
        lateness_days = (actual - expected).days
        was_late = lateness_days > 0
        # Decision anchor: midpoint between order and expected (when tracking
        # would matter most)
        from datetime import timedelta
        days_elapsed = (expected - row.order_date).days
        decision_at = row.order_date + timedelta(days=max(1, days_elapsed // 2))

        # "Ground truth" action: if late, the TRM SHOULD have alerted; if on-time
        # the alert would have been a false positive.
        should_alert = was_late
        reward = 0.9 if was_late else 0.8  # high confidence either way

        return SampleRecord(
            trm_type="order_tracking",
            product_id=row.product_id,
            site_id=str(row.site_id),
            decision_at=decision_at,
            state_features={
                "days_since_order": days_elapsed,
                "days_until_expected": (expected - decision_at).days,
                "quantity_submitted": float(row.quantity_submitted or 0),
            },
            action={
                "should_alert": should_alert,
                "supplier_id": str(row.supplier_id) if row.supplier_id else None,
            },
            outcome={
                "was_late": was_late,
                "lateness_days": lateness_days,
                "fill_rate": (float(row.quantity_received or 0) / float(row.quantity_submitted or 1)),
            },
            reward_components={"was_late": was_late, "lateness_days": lateness_days},
            aggregate_reward=reward,
            label_weight=1.0,
        )
