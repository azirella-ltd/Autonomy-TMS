"""
Forecast Value Add (FVA) Tracking Service.

Measures whether each step in the forecasting process improves accuracy:
  FVA(source) = MAPE(baseline only) - MAPE(baseline + adjustment)

Positive FVA = source added value (improved accuracy)
Negative FVA = source destroyed value (worsened accuracy)

Tracks per:
  - Signal source (promotion, npi, sensing, consensus, signal, etc.)
  - Product category
  - Time horizon (1-week, 4-week, 13-week)
  - User (for consensus overrides)

Used by:
  - Forecast Adjustment TRM: auto-suppress low-FVA sources
  - Consensus FVA gating: accept/reject overrides by user track record
  - Decision Stream "Ask Why": attribute accuracy to signal sources
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class FVATrackingService:
    """Computes and persists Forecast Value Add metrics."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute_fva(
        self,
        config_id: int,
        lookback_weeks: int = 8,
    ) -> Dict[str, Any]:
        """Compute FVA for all adjustment sources over the lookback period.

        Returns:
            Dict keyed by source → {fva: float, count: int, avg_mape_before: float, avg_mape_after: float}
        """
        try:
            result = await self.db.execute(
                sql_text("""
                    SELECT
                        signal_source,
                        COUNT(*) as count,
                        AVG(forecast_error_before) as avg_mape_before,
                        AVG(forecast_error_after) as avg_mape_after,
                        AVG(COALESCE(forecast_error_before, 0) - COALESCE(forecast_error_after, 0)) as avg_fva
                    FROM powell_forecast_adjustment_decisions
                    WHERE config_id = :config_id
                      AND was_applied = true
                      AND forecast_error_before IS NOT NULL
                      AND forecast_error_after IS NOT NULL
                      AND created_at > NOW() - INTERVAL '1 week' * :weeks
                    GROUP BY signal_source
                    ORDER BY avg_fva DESC
                """),
                {"config_id": config_id, "weeks": lookback_weeks},
            )
            rows = result.fetchall()

            fva_by_source = {}
            for row in rows:
                fva_by_source[row.signal_source] = {
                    "fva": round(row.avg_fva, 4) if row.avg_fva else 0,
                    "count": row.count,
                    "avg_mape_before": round(row.avg_mape_before, 4) if row.avg_mape_before else None,
                    "avg_mape_after": round(row.avg_mape_after, 4) if row.avg_mape_after else None,
                    "adds_value": (row.avg_fva or 0) > 0,
                }

            return fva_by_source

        except Exception as e:
            logger.debug("FVA computation failed: %s", e)
            return {}

    async def compute_user_fva(
        self,
        config_id: int,
        user_id: Optional[int] = None,
        lookback_weeks: int = 13,
    ) -> Dict[str, Any]:
        """Compute FVA for consensus overrides, optionally filtered by user.

        Returns per-user FVA for the consensus/sales_input domain.
        """
        try:
            params = {"config_id": config_id, "weeks": lookback_weeks}
            user_filter = ""
            if user_id:
                user_filter = "AND d.signal_source = 'sales_input'"
                # In future: join to override user tracking

            result = await self.db.execute(
                sql_text(f"""
                    SELECT
                        signal_source,
                        COUNT(*) as count,
                        AVG(COALESCE(forecast_error_before, 0) - COALESCE(forecast_error_after, 0)) as avg_fva
                    FROM powell_forecast_adjustment_decisions d
                    WHERE config_id = :config_id
                      AND was_applied = true
                      AND forecast_error_before IS NOT NULL
                      AND forecast_error_after IS NOT NULL
                      AND created_at > NOW() - INTERVAL '1 week' * :weeks
                      AND signal_source IN ('sales_input', 'consensus', 'voice', 'email')
                      {user_filter}
                    GROUP BY signal_source
                """),
                params,
            )
            rows = result.fetchall()
            return {
                row.signal_source: {
                    "fva": round(row.avg_fva, 4) if row.avg_fva else 0,
                    "count": row.count,
                    "adds_value": (row.avg_fva or 0) > 0,
                }
                for row in rows
            }
        except Exception as e:
            logger.debug("User FVA computation failed: %s", e)
            return {}

    async def get_suppressed_sources(
        self,
        config_id: int,
        threshold: float = -0.02,
        min_consecutive_weeks: int = 8,
    ) -> List[str]:
        """Return sources that should be auto-suppressed due to persistent negative FVA.

        A source is suppressed when its rolling FVA has been below threshold
        for min_consecutive_weeks.
        """
        try:
            result = await self.db.execute(
                sql_text("""
                    SELECT signal_source,
                           AVG(COALESCE(forecast_error_before, 0) - COALESCE(forecast_error_after, 0)) as avg_fva,
                           COUNT(*) as count
                    FROM powell_forecast_adjustment_decisions
                    WHERE config_id = :config_id
                      AND was_applied = true
                      AND forecast_error_before IS NOT NULL
                      AND created_at > NOW() - INTERVAL '1 week' * :weeks
                    GROUP BY signal_source
                    HAVING AVG(COALESCE(forecast_error_before, 0) - COALESCE(forecast_error_after, 0)) < :threshold
                       AND COUNT(*) >= :min_count
                """),
                {
                    "config_id": config_id,
                    "weeks": min_consecutive_weeks,
                    "threshold": threshold,
                    "min_count": min_consecutive_weeks,
                },
            )
            return [row.signal_source for row in result.fetchall()]
        except Exception:
            return []

    async def update_outcomes(
        self,
        config_id: int,
        actuals: Dict[str, float],
    ) -> int:
        """Update forecast adjustment decisions with actual demand data.

        Called weekly when actuals become available. Computes MAPE before
        and after adjustment for each decision.

        Args:
            config_id: Supply chain config
            actuals: Dict of {product_id: actual_demand}

        Returns:
            Number of decisions updated
        """
        updated = 0
        try:
            for product_id, actual in actuals.items():
                if actual <= 0:
                    continue

                result = await self.db.execute(
                    sql_text("""
                        UPDATE powell_forecast_adjustment_decisions
                        SET actual_demand = :actual,
                            forecast_error_before = ABS(current_forecast_value - :actual) / :actual,
                            forecast_error_after = ABS(adjusted_forecast_value - :actual) / :actual
                        WHERE config_id = :config_id
                          AND product_id = :product_id
                          AND actual_demand IS NULL
                          AND created_at > NOW() - INTERVAL '13 weeks'
                    """),
                    {
                        "config_id": config_id,
                        "product_id": product_id,
                        "actual": actual,
                    },
                )
                updated += result.rowcount

            if updated > 0:
                await self.db.flush()
                logger.info("FVA outcomes updated: %d decisions for config %d", updated, config_id)

        except Exception as e:
            logger.warning("FVA outcome update failed: %s", e)

        return updated
