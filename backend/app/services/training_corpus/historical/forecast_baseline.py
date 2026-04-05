"""Historical extractor for forecast_baseline TRM.

For each forecast record with a forecast_date in the past, compare the
predicted value against what actually happened (outbound_order_line realized
demand in the period the forecast was predicting). The resulting MAPE is the
outcome signal for training the forecast baseline TRM.
"""

import logging
from datetime import timedelta
from typing import AsyncIterator, Optional

from sqlalchemy import text as sql_text

from .base import BaseHistoricalExtractor, SampleRecord

logger = logging.getLogger(__name__)


class ForecastBaselineHistoricalExtractor(BaseHistoricalExtractor):
    trm_type = "forecast_baseline"

    async def extract(
        self, tenant_id: int, config_id: int, since=None,
    ) -> AsyncIterator[SampleRecord]:
        # Sample forecasts at weekly granularity to avoid N^2 blow-up: take
        # the latest forecast per (p,s,week) and look forward 1 week for realized.
        params = {"cid": config_id}
        where_since = ""
        if since is not None:
            where_since = " AND forecast_date >= :since"
            params["since"] = since

        result = await self.db.execute(
            sql_text(f"""
                SELECT DISTINCT ON (product_id, site_id, DATE_TRUNC('week', forecast_date))
                       id, product_id, site_id, forecast_date,
                       COALESCE(forecast_p50, forecast_quantity) AS p50,
                       forecast_p10, forecast_p90, forecast_method, demand_pattern
                FROM forecast
                WHERE config_id = :cid
                  AND forecast_date IS NOT NULL
                  AND COALESCE(forecast_p50, forecast_quantity) IS NOT NULL
                  {where_since}
                ORDER BY product_id, site_id, DATE_TRUNC('week', forecast_date), forecast_date DESC
            """),
            params,
        )
        rows = result.fetchall()
        logger.info("ForecastBaselineHistoricalExtractor: %d weekly forecasts", len(rows))

        for row in rows:
            try:
                sample = await self._build_sample(row, config_id)
                if sample is not None:
                    yield sample
            except Exception as e:
                logger.debug("forecast %s skipped: %s", row.id, e)

    async def _build_sample(self, row, config_id: int) -> Optional[SampleRecord]:
        forecast_date = row.forecast_date
        if forecast_date is None:
            return None
        p50 = float(row.p50 or 0)
        # Realized demand in the following week
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
             "start": forecast_date, "end": forecast_date + timedelta(days=7)},
        )
        realized = float(r.fetchone().realized or 0)

        # MAPE on this forecast
        if p50 > 0:
            ape = abs(realized - p50) / p50
            accuracy = max(0.0, 1.0 - ape)
        else:
            ape = None
            accuracy = 0.5

        reward = accuracy
        label_weight = 1.0 if p50 > 0 else 0.3

        return SampleRecord(
            trm_type="forecast_baseline",
            product_id=row.product_id,
            site_id=str(row.site_id),
            decision_at=forecast_date,
            state_features={
                "demand_pattern": row.demand_pattern,
                "method": row.forecast_method,
            },
            action={
                "forecast_p50": p50,
                "forecast_p10": float(row.forecast_p10) if row.forecast_p10 is not None else None,
                "forecast_p90": float(row.forecast_p90) if row.forecast_p90 is not None else None,
            },
            outcome={
                "realized": realized,
                "ape": ape,
                "accuracy": accuracy,
            },
            reward_components={"accuracy": accuracy, "ape": ape},
            aggregate_reward=reward,
            label_weight=label_weight,
        )
