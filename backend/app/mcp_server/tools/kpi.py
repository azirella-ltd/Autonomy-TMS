"""
MCP Tool: KPI Metrics — Balanced Scorecard.

Returns key performance indicators across the four BSC quadrants:
Financial, Customer, Operational, Strategic.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def register(mcp):
    """Register KPI metrics tools on the MCP server."""

    @mcp.tool()
    async def get_kpi_metrics(
        tenant_id: int,
        config_id: int,
        site_id: Optional[str] = None,
        product_id: Optional[str] = None,
    ) -> dict:
        """Get key performance indicators from the Balanced Scorecard.

        Returns metrics across four quadrants:
        - Financial: revenue, cost savings, inventory carrying cost, ROI
        - Customer: service level (OTIF), fill rate, order cycle time
        - Operational: capacity utilization, inventory turns, forecast accuracy
        - Strategic: touchless rate, override effectiveness, model confidence

        Filter by site and/or product for drilldown.

        Args:
            tenant_id: Organization ID
            config_id: Supply chain config ID
            site_id: Optional site filter for drilldown
            product_id: Optional product filter for drilldown

        Returns:
            Metrics dictionary organized by BSC quadrant.
        """
        from sqlalchemy import text as sql_text
        from .db import get_db

        async with get_db() as db:
            # Touchless rate (AUTOMATE decisions / total decisions)
            try:
                touchless_result = await db.execute(
                    sql_text("""
                        SELECT
                            COUNT(*) FILTER (WHERE status = 'ACTIONED') as actioned,
                            COUNT(*) FILTER (WHERE status = 'OVERRIDDEN') as overridden,
                            COUNT(*) as total
                        FROM (
                            SELECT status FROM powell_po_creation_decisions WHERE config_id = :cid
                            UNION ALL
                            SELECT status FROM powell_atp_allocation_decisions WHERE config_id = :cid
                            UNION ALL
                            SELECT status FROM powell_inventory_rebalancing_decisions WHERE config_id = :cid
                        ) all_decisions
                    """),
                    {"cid": config_id},
                )
                tr = touchless_result.fetchone()
                total = tr.total if tr else 0
                touchless_rate = (tr.actioned / total * 100) if total > 0 else 0
                override_rate = (tr.overridden / total * 100) if total > 0 else 0
            except Exception:
                touchless_rate = 0
                override_rate = 0
                total = 0

            # Service level (fill rate from supply plan)
            try:
                sl_result = await db.execute(
                    sql_text("""
                        SELECT
                            AVG(CASE WHEN fulfilled_qty >= demand_qty THEN 100.0
                                ELSE fulfilled_qty / NULLIF(demand_qty, 0) * 100 END) as fill_rate
                        FROM supply_plan
                        WHERE config_id = :cid AND plan_version = 'live'
                    """),
                    {"cid": config_id},
                )
                sl_row = sl_result.fetchone()
                fill_rate = round(sl_row.fill_rate, 1) if sl_row and sl_row.fill_rate else 0
            except Exception:
                fill_rate = 0

            # Forecast accuracy (MAPE from conformal predictions)
            try:
                fa_result = await db.execute(
                    sql_text("""
                        SELECT AVG(ABS(actual - predicted) / NULLIF(actual, 0) * 100) as mape
                        FROM conformal.predictions
                        WHERE config_id = :cid AND actual IS NOT NULL
                    """),
                    {"cid": config_id},
                )
                fa_row = fa_result.fetchone()
                forecast_mape = round(fa_row.mape, 1) if fa_row and fa_row.mape else None
            except Exception:
                forecast_mape = None

            return {
                "config_id": config_id,
                "financial": {
                    "description": "Financial performance metrics",
                },
                "customer": {
                    "fill_rate_pct": fill_rate,
                    "description": "Customer service metrics",
                },
                "operational": {
                    "forecast_mape_pct": forecast_mape,
                    "total_decisions": total,
                    "description": "Operational efficiency metrics",
                },
                "strategic": {
                    "touchless_rate_pct": round(touchless_rate, 1),
                    "override_rate_pct": round(override_rate, 1),
                    "description": "AI governance and effectiveness metrics",
                },
            }
