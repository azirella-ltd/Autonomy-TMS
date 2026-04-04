"""
Decision-Contextual Chart Service.

Returns time-series data specific to each TRM decision type.
Each chart shows the ISSUE → ACTION → PROJECTED OUTCOME
with a narrow, contextual time window.

12 TRM types × specific chart query = 12 chart generators.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DecisionChartService:
    """Generates contextual chart data for Decision Stream cards."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_chart_data(
        self,
        decision_type: str,
        decision_id: int,
        config_id: int,
        product_id: Optional[str] = None,
        site_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch to the appropriate chart generator by decision type."""
        generators = {
            "atp_allocation": self._chart_atp,
            "atp_executor": self._chart_atp,
            "rebalancing": self._chart_rebalancing,
            "inventory_rebalancing": self._chart_rebalancing,
            "po_creation": self._chart_po_creation,
            "forecast_adjustment": self._chart_forecast_adjustment,
            "forecast_baseline": self._chart_forecast_baseline,
            "inventory_buffer": self._chart_inventory_buffer,
            "mo_execution": self._chart_mo_execution,
            "mo_release": self._chart_mo_execution,
            "to_execution": self._chart_to_execution,
            "transfer_order": self._chart_to_execution,
            "quality_disposition": self._chart_quality,
            "maintenance_scheduling": self._chart_maintenance,
            "subcontracting": self._chart_subcontracting,
            "order_tracking": self._chart_order_tracking,
        }

        generator = generators.get(decision_type)
        if not generator:
            return {"error": f"No chart generator for {decision_type}", "series": []}

        try:
            return await generator(config_id, product_id, site_id, decision_id)
        except Exception as e:
            logger.warning("Chart generation failed for %s: %s", decision_type, e)
            return {"error": str(e), "series": []}

    async def _chart_atp(self, config_id, product_id, site_id, decision_id) -> Dict:
        """ATP: Buckets by priority + demand at site. Window: -3d → +1w."""
        result = await self.db.execute(
            sql_text("""
                SELECT plan_date, planned_order_quantity as supply,
                       demand_quantity as demand
                FROM supply_plan
                WHERE config_id = :cid AND product_id = :pid AND site_id = :sid
                  AND plan_version = 'live'
                  AND plan_date BETWEEN CURRENT_DATE - INTERVAL '3 days' AND CURRENT_DATE + INTERVAL '7 days'
                ORDER BY plan_date
            """),
            {"cid": config_id, "pid": product_id, "sid": site_id},
        )
        rows = result.fetchall()
        return {
            "title": f"ATP: Supply vs Demand at {site_id}",
            "window": "-3d → +1w",
            "series": [
                {"name": "Supply", "data": [{"x": r.plan_date.isoformat(), "y": float(r.supply or 0)} for r in rows]},
                {"name": "Demand", "data": [{"x": r.plan_date.isoformat(), "y": float(r.demand or 0)} for r in rows]},
            ],
        }

    async def _chart_rebalancing(self, config_id, product_id, site_id, decision_id) -> Dict:
        """Rebalancing: Inventory at source + destination. Window: -1w → +2w."""
        # Get source and destination from decision
        try:
            dec = await self.db.execute(
                sql_text("""
                    SELECT site_id as source_site, product_id,
                           decision_reasoning
                    FROM powell_inventory_rebalancing_decisions
                    WHERE id = :did
                """),
                {"did": decision_id},
            )
            dec_row = dec.fetchone()
            source_site = dec_row.source_site if dec_row else site_id
        except Exception:
            source_site = site_id

        result = await self.db.execute(
            sql_text("""
                SELECT il.site_id, il.snapshot_date, il.on_hand_quantity,
                       ip.safety_stock_quantity
                FROM inventory_level il
                LEFT JOIN inventory_policy ip ON ip.product_id = il.product_id
                    AND ip.site_id = il.site_id AND ip.config_id = il.config_id
                WHERE il.config_id = :cid AND il.product_id = :pid
                  AND il.site_id IN (:s1, :s2)
                ORDER BY il.site_id, il.snapshot_date DESC
                LIMIT 20
            """),
            {"cid": config_id, "pid": product_id, "s1": source_site, "s2": site_id},
        )
        rows = result.fetchall()

        by_site: Dict[str, list] = {}
        ss_by_site: Dict[str, float] = {}
        for r in rows:
            sk = str(r.site_id)
            if sk not in by_site:
                by_site[sk] = []
            by_site[sk].append({"x": r.snapshot_date.isoformat() if r.snapshot_date else "", "y": float(r.on_hand_quantity or 0)})
            if r.safety_stock_quantity:
                ss_by_site[sk] = float(r.safety_stock_quantity)

        series = []
        for sk, data in by_site.items():
            series.append({"name": f"On-hand: {sk}", "data": data})
            if sk in ss_by_site:
                series.append({"name": f"Safety Stock: {sk}", "data": [{"x": d["x"], "y": ss_by_site[sk]} for d in data], "dashStyle": "dash"})

        return {
            "title": f"Inventory: Rebalancing Impact",
            "window": "-1w → +2w",
            "series": series,
        }

    async def _chart_po_creation(self, config_id, product_id, site_id, decision_id) -> Dict:
        """PO Creation: Inventory vs ROP + expected receipt. Window: -1w → +lead_time."""
        result = await self.db.execute(
            sql_text("""
                SELECT il.snapshot_date, il.on_hand_quantity,
                       ip.reorder_point, ip.safety_stock_quantity
                FROM inventory_level il
                LEFT JOIN inventory_policy ip ON ip.product_id = il.product_id
                    AND ip.site_id = il.site_id AND ip.config_id = il.config_id
                WHERE il.config_id = :cid AND il.product_id = :pid AND il.site_id = :sid
                ORDER BY il.snapshot_date DESC
                LIMIT 14
            """),
            {"cid": config_id, "pid": product_id, "sid": site_id},
        )
        rows = list(reversed(result.fetchall()))
        rop = rows[0].reorder_point if rows and rows[0].reorder_point else 0
        ss = rows[0].safety_stock_quantity if rows and rows[0].safety_stock_quantity else 0

        return {
            "title": f"PO Trigger: Inventory vs Reorder Point at {site_id}",
            "window": "-2w → +lead time",
            "series": [
                {"name": "On-hand", "data": [{"x": r.snapshot_date.isoformat() if r.snapshot_date else "", "y": float(r.on_hand_quantity or 0)} for r in rows]},
                {"name": "Reorder Point", "data": [{"x": r.snapshot_date.isoformat() if r.snapshot_date else "", "y": float(rop)} for r in rows], "dashStyle": "dash"},
                {"name": "Safety Stock", "data": [{"x": r.snapshot_date.isoformat() if r.snapshot_date else "", "y": float(ss)} for r in rows], "dashStyle": "dot"},
            ],
        }

    async def _chart_forecast_adjustment(self, config_id, product_id, site_id, decision_id) -> Dict:
        """Forecast Adjustment: Old vs new forecast vs actuals. Window: -4w → +4w."""
        result = await self.db.execute(
            sql_text("""
                SELECT period_start, quantity as forecast_p50,
                       quantity_p10, quantity_p90
                FROM forecast
                WHERE config_id = :cid AND product_id = :pid AND site_id = :sid
                  AND plan_version = 'live'
                ORDER BY period_start
                LIMIT 8
            """),
            {"cid": config_id, "pid": product_id, "sid": site_id},
        )
        rows = result.fetchall()
        return {
            "title": f"Forecast Adjustment: {product_id} at {site_id}",
            "window": "-4w → +4w",
            "series": [
                {"name": "Forecast P50", "data": [{"x": r.period_start.isoformat() if r.period_start else "", "y": float(r.forecast_p50 or 0)} for r in rows]},
                {"name": "P10 (downside)", "data": [{"x": r.period_start.isoformat() if r.period_start else "", "y": float(r.quantity_p10 or 0)} for r in rows], "dashStyle": "dot"},
                {"name": "P90 (upside)", "data": [{"x": r.period_start.isoformat() if r.period_start else "", "y": float(r.quantity_p90 or 0)} for r in rows], "dashStyle": "dot"},
            ],
        }

    async def _chart_forecast_baseline(self, config_id, product_id, site_id, decision_id) -> Dict:
        """Forecast Baseline: Model performance + conformal intervals."""
        return await self._chart_forecast_adjustment(config_id, product_id, site_id, decision_id)

    async def _chart_inventory_buffer(self, config_id, product_id, site_id, decision_id) -> Dict:
        """Inventory Buffer: On-hand vs old/new safety stock. Window: -2w → +2w."""
        return await self._chart_po_creation(config_id, product_id, site_id, decision_id)

    async def _chart_mo_execution(self, config_id, product_id, site_id, decision_id) -> Dict:
        """MO Execution: WIP + FG inventory + capacity utilization."""
        result = await self.db.execute(
            sql_text("""
                SELECT plan_date, planned_order_quantity
                FROM supply_plan
                WHERE config_id = :cid AND product_id = :pid AND site_id = :sid
                  AND plan_version = 'live'
                  AND order_type IN ('manufacturing_order', 'production_order')
                ORDER BY plan_date
                LIMIT 14
            """),
            {"cid": config_id, "pid": product_id, "sid": site_id},
        )
        rows = result.fetchall()
        return {
            "title": f"Production: MO Schedule at {site_id}",
            "window": "-1w → +production LT",
            "series": [
                {"name": "Planned Production", "data": [{"x": r.plan_date.isoformat() if r.plan_date else "", "y": float(r.planned_order_quantity or 0)} for r in rows]},
            ],
        }

    async def _chart_to_execution(self, config_id, product_id, site_id, decision_id) -> Dict:
        """TO Execution: In-transit + source/dest on-hand."""
        return await self._chart_rebalancing(config_id, product_id, site_id, decision_id)

    async def _chart_quality(self, config_id, product_id, site_id, decision_id) -> Dict:
        """Quality: Inspection results + disposition impact on inventory."""
        return {
            "title": f"Quality: Inspection Impact at {site_id}",
            "window": "-2w → +1w",
            "series": [],
            "note": "Quality inspection time-series not yet populated from ERP data",
        }

    async def _chart_maintenance(self, config_id, product_id, site_id, decision_id) -> Dict:
        """Maintenance: Equipment downtime + capacity impact."""
        return {
            "title": f"Maintenance: Capacity Impact at {site_id}",
            "window": "-4w → +maintenance window",
            "series": [],
            "note": "Maintenance downtime time-series not yet populated from ERP data",
        }

    async def _chart_subcontracting(self, config_id, product_id, site_id, decision_id) -> Dict:
        """Subcontracting: Internal capacity vs demand."""
        return await self._chart_mo_execution(config_id, product_id, site_id, decision_id)

    async def _chart_order_tracking(self, config_id, product_id, site_id, decision_id) -> Dict:
        """Order Tracking: Order timeline + delivery risk."""
        return {
            "title": f"Order Tracking: Delivery Risk",
            "window": "order date → +2w past due",
            "series": [],
            "note": "Order tracking timeline requires shipment integration",
        }
