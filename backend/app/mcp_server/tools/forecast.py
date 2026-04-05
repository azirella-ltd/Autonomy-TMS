"""
MCP Tool: Forecast Retrieval.

Returns demand forecasts with conformal prediction intervals (P10/P50/P90).
Supports product and site filtering with hierarchy drilldown.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def register(mcp):
    """Register forecast tools on the MCP server."""

    @mcp.tool()
    async def get_forecast(
        tenant_id: int,
        config_id: int,
        product_id: Optional[str] = None,
        site_id: Optional[str] = None,
        horizon_periods: int = 12,
        plan_version: str = "live",
    ) -> dict:
        """Get demand forecast with conformal prediction intervals.

        Returns the Plan of Record forecast (P50) with uncertainty bounds
        (P10 = downside, P90 = upside) from conformal prediction. These
        intervals are distribution-free and calibrated — the true value
        falls within [P10, P90] with 80% probability.

        Args:
            tenant_id: Organization ID
            config_id: Supply chain config ID
            product_id: Filter by product (optional — returns all if omitted)
            site_id: Filter by site (optional)
            horizon_periods: Number of future periods to return (default 12)
            plan_version: "live" (Plan of Record) or "erp_baseline"

        Returns:
            Forecast data with P10/P50/P90 per period, product, and site.
        """
        from sqlalchemy import text as sql_text
        from .db import get_db

        async with get_db() as db:
            # Schema note: forecast table uses forecast_p10/p50/p90 + forecast_date
            # (no quantity_p* aliases, no plan_version or period_start/end columns).
            filters = ["f.config_id = :config_id"]
            params = {"config_id": config_id, "limit": horizon_periods}

            if product_id:
                filters.append("f.product_id = :product_id")
                params["product_id"] = product_id
            if site_id:
                filters.append("f.site_id = :site_id")
                params["site_id"] = site_id

            where = " AND ".join(filters)

            result = await db.execute(
                sql_text(f"""
                    SELECT f.product_id, f.site_id, f.forecast_date,
                           COALESCE(f.forecast_p50, f.forecast_quantity) AS p50,
                           f.forecast_p10, f.forecast_p90,
                           f.forecast_method
                    FROM forecast f
                    WHERE {where}
                    ORDER BY f.product_id, f.site_id, f.forecast_date
                    LIMIT :limit * 100
                """),
                params,
            )

            forecasts = []
            for r in result.fetchall():
                forecasts.append({
                    "product_id": r.product_id,
                    "site_id": r.site_id,
                    "forecast_date": r.forecast_date.isoformat() if r.forecast_date else None,
                    "p50": float(r.p50) if r.p50 else 0,
                    "p10": float(r.forecast_p10) if r.forecast_p10 else None,
                    "p90": float(r.forecast_p90) if r.forecast_p90 else None,
                    "method": r.forecast_method,
                })

            return {
                "config_id": config_id,
                "record_count": len(forecasts),
                "forecasts": forecasts,
            }
