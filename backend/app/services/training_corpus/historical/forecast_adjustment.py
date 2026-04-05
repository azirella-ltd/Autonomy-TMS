"""Historical extractor for forecast_adjustment TRM.

forecast_adjustments rows → each adjustment is an action. Outcome: did the
adjusted forecast get closer to realized than the baseline?
"""

import logging
from datetime import timedelta
from typing import AsyncIterator, Optional

from sqlalchemy import text as sql_text

from .base import BaseHistoricalExtractor, SampleRecord

logger = logging.getLogger(__name__)


class ForecastAdjustmentHistoricalExtractor(BaseHistoricalExtractor):
    trm_type = "forecast_adjustment"

    async def extract(
        self, tenant_id: int, config_id: int, since=None,
    ) -> AsyncIterator[SampleRecord]:
        # forecast_adjustments has no direct config_id — scope via the
        # parent forecast row.
        params = {"cid": config_id}
        where_since = ""
        if since is not None:
            where_since = " AND fa.period_start >= :since"
            params["since"] = since

        result = await self.db.execute(
            sql_text(f"""
                SELECT fa.id, fa.adjustment_type, fa.original_value, fa.new_value,
                       fa.period_start, fa.period_end, fa.reason_code,
                       f.product_id, f.site_id, f.forecast_date
                FROM forecast_adjustments fa
                JOIN forecast f ON f.id = fa.forecast_id
                WHERE f.config_id = :cid
                  AND fa.period_start IS NOT NULL
                  {where_since}
                ORDER BY fa.period_start ASC
            """),
            params,
        )
        rows = result.fetchall()
        logger.info("ForecastAdjustmentHistoricalExtractor: %d adjustments", len(rows))

        for row in rows:
            try:
                sample = await self._build_sample(row, config_id)
                if sample is not None:
                    yield sample
            except Exception as e:
                logger.debug("Adjustment %s skipped: %s", row.id, e)

    async def _build_sample(self, row, config_id: int) -> Optional[SampleRecord]:
        if row.period_start is None:
            return None
        original = float(row.original_value or 0)
        new = float(row.new_value or 0)
        # Realized demand during the adjustment's period
        r = await self.db.execute(
            sql_text("""
                SELECT COALESCE(SUM(COALESCE(shipped_quantity, ordered_quantity, 0)), 0) AS realized
                FROM outbound_order_line
                WHERE config_id = :cid
                  AND product_id = :pid
                  AND site_id = :sid
                  AND order_date >= :start
                  AND order_date <  :end
            """),
            {"cid": config_id, "pid": row.product_id, "sid": row.site_id,
             "start": row.period_start,
             "end": row.period_end or (row.period_start + timedelta(days=7))},
        )
        realized = float(r.fetchone().realized or 0)

        def ape(pred):
            return abs(realized - pred) / max(pred, 1) if pred > 0 else None

        ape_orig = ape(original)
        ape_new = ape(new)
        improved = (ape_new is not None and ape_orig is not None and ape_new < ape_orig)

        reward = 0.8 if improved else 0.3
        label_weight = 1.0 if improved else 0.4

        return SampleRecord(
            trm_type="forecast_adjustment",
            product_id=row.product_id,
            site_id=str(row.site_id),
            decision_at=row.period_start,
            state_features={
                "baseline": original,
                "reason_code": row.reason_code,
            },
            action={
                "adjustment_type": row.adjustment_type,
                "new_value": new,
                "delta_pct": (new - original) / max(original, 1) if original else None,
            },
            outcome={
                "realized": realized,
                "ape_original": ape_orig,
                "ape_new": ape_new,
                "improved_accuracy": improved,
            },
            reward_components={"improved": improved},
            aggregate_reward=reward,
            label_weight=label_weight,
        )
