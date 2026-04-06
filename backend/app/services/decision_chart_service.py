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
        """Forecast Adjustment: Original baseline vs revised forecast vs actuals.

        Shows 12 weeks centered on the decision point so the user can see:
        - What the baseline forecast was before the adjustment
        - What the revised forecast is after the adjustment
        - What actually happened (realized demand from outbound_order_line)
        """
        # Resolve human-readable names for the title
        product_name = product_id
        site_name = str(site_id)
        try:
            r = await self.db.execute(
                sql_text("SELECT description FROM product WHERE id = :pid AND config_id = :cid"),
                {"pid": product_id, "cid": config_id},
            )
            row = r.fetchone()
            if row and row[0]:
                product_name = f"{row[0]} [{product_id}]"
            r = await self.db.execute(
                sql_text("SELECT name FROM site WHERE id = :sid"),
                {"sid": site_id},
            )
            row = r.fetchone()
            if row and row[0]:
                site_name = row[0]
        except Exception:
            pass

        # Get the decision's adjustment details to compute original baseline
        adj_pct = None
        adj_value = None
        original_value = None
        try:
            r = await self.db.execute(
                sql_text("""
                    SELECT adjustment_pct, current_forecast_value, adjusted_forecast_value
                    FROM powell_forecast_adjustment_decisions
                    WHERE id = :did
                """),
                {"did": decision_id},
            )
            row = r.fetchone()
            if row:
                adj_pct = float(row[0]) if row[0] else None
                original_value = float(row[1]) if row[1] else None
                adj_value = float(row[2]) if row[2] else None
        except Exception:
            pass

        # Current forecast (the revised version — what's in the forecast table now)
        result = await self.db.execute(
            sql_text("""
                SELECT forecast_date,
                       COALESCE(forecast_p50, forecast_quantity) AS p50,
                       forecast_p10, forecast_p90
                FROM forecast
                WHERE config_id = :cid AND product_id = :pid
                  AND CAST(site_id AS TEXT) = CAST(:sid AS TEXT)
                ORDER BY forecast_date
                LIMIT 12
            """),
            {"cid": config_id, "pid": product_id, "sid": site_id},
        )
        rows = result.fetchall()

        # Realized demand (actuals from outbound_order_line)
        actuals_result = await self.db.execute(
            sql_text("""
                SELECT date_trunc('week', order_date)::date AS wk,
                       SUM(COALESCE(shipped_quantity, ordered_quantity, 0)) AS actual
                FROM outbound_order_line
                WHERE config_id = :cid AND product_id = :pid
                  AND CAST(site_id AS TEXT) = CAST(:sid AS TEXT)
                  AND ordered_quantity > 0
                GROUP BY 1
                ORDER BY 1 DESC
                LIMIT 12
            """),
            {"cid": config_id, "pid": product_id, "sid": site_id},
        )
        actuals = {r.wk.isoformat(): float(r.actual) for r in actuals_result.fetchall()}

        # Build series
        revised_series = []
        original_series = []
        p10_series = []
        p90_series = []
        actuals_series = []

        for r in rows:
            x = r.forecast_date.isoformat() if r.forecast_date else ""
            p50 = float(r.p50 or 0)
            revised_series.append({"x": x, "y": p50})
            p10_series.append({"x": x, "y": float(r.forecast_p10 or 0)})
            p90_series.append({"x": x, "y": float(r.forecast_p90 or 0)})

            # Compute original baseline by reversing the adjustment
            if adj_pct and adj_pct != 0:
                orig = p50 / (1 + adj_pct / 100.0)
            elif original_value is not None and adj_value is not None and adj_value != 0:
                scale = original_value / adj_value
                orig = p50 * scale
            else:
                orig = p50  # can't reverse — show same as revised
            original_series.append({"x": x, "y": round(orig, 1)})

            # Actuals for this week (if we have them)
            if x in actuals:
                actuals_series.append({"x": x, "y": actuals[x]})

        # Date range for context label
        dates = [r.forecast_date for r in rows if r.forecast_date]
        window_str = f"{dates[0].isoformat()} to {dates[-1].isoformat()}" if dates else ""

        series = [
            {"name": "Original Forecast", "data": original_series, "dashStyle": "dash", "color": "#94a3b8"},
            {"name": "Revised Forecast (P50)", "data": revised_series, "color": "#3b82f6"},
            {"name": "P10 (Low)", "data": p10_series, "dashStyle": "dot", "color": "#22c55e"},
            {"name": "P90 (High)", "data": p90_series, "dashStyle": "dot", "color": "#ef4444"},
        ]
        if actuals_series:
            series.append({"name": "Actual Demand", "data": actuals_series, "color": "#f97316", "lineWidth": 2})

        return {
            "title": f"Forecast Adjustment — {product_name} @ {site_name}",
            "subtitle": f"Agent adjusted forecast {'up' if (adj_pct or 0) > 0 else 'down'} {abs(adj_pct or 0):.1f}%" if adj_pct else None,
            "window": window_str,
            "series": series,
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
                  AND plan_type IN ('manufacturing_order', 'production_order', 'mrp')
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
        """Quality: Inventory impact from quality decisions (holds, rejects)."""
        # Show inventory before/after quality decision impact
        result = await self.db.execute(
            sql_text("""
                SELECT il.snapshot_date, il.on_hand_quantity,
                       il.in_transit_quantity, il.allocated_quantity
                FROM inventory_level il
                WHERE il.config_id = :cid AND il.product_id = :pid AND il.site_id = :sid
                ORDER BY il.snapshot_date DESC
                LIMIT 14
            """),
            {"cid": config_id, "pid": product_id, "sid": site_id},
        )
        rows = list(reversed(result.fetchall()))
        if not rows:
            return {"title": f"Quality: Inventory Impact at {site_id}", "series": [], "note": "No inventory data available"}

        return {
            "title": f"Quality: Inventory Impact at {site_id}",
            "window": "-2w → +1w",
            "series": [
                {"name": "On-hand", "data": [{"x": r.snapshot_date.isoformat() if r.snapshot_date else "", "y": float(r.on_hand_quantity or 0)} for r in rows]},
                {"name": "Allocated", "data": [{"x": r.snapshot_date.isoformat() if r.snapshot_date else "", "y": float(r.allocated_quantity or 0)} for r in rows]},
            ],
        }

    async def _chart_maintenance(self, config_id, product_id, site_id, decision_id) -> Dict:
        """Maintenance: Capacity utilization trend + maintenance orders."""
        # Show resource capacity utilization at the site
        result = await self.db.execute(
            sql_text("""
                SELECT rc.effective_date, rc.available_capacity,
                       rc.planned_downtime_hours, rc.hours_per_shift, rc.shift_count
                FROM resource_capacity rc
                WHERE rc.config_id = :cid AND rc.site_id = :sid
                ORDER BY rc.effective_date DESC
                LIMIT 14
            """),
            {"cid": config_id, "sid": site_id},
        )
        rows = list(reversed(result.fetchall()))
        if not rows:
            # Fallback: show maintenance order count if resource_capacity empty
            try:
                mo_result = await self.db.execute(
                    sql_text("""
                        SELECT planned_start_date, maintenance_type, status
                        FROM maintenance_orders
                        WHERE config_id = :cid AND site_id = :sid
                        ORDER BY planned_start_date DESC
                        LIMIT 10
                    """),
                    {"cid": config_id, "sid": site_id},
                )
                mo_rows = mo_result.fetchall()
                if mo_rows:
                    return {
                        "title": f"Maintenance: Orders at {site_id}",
                        "window": "Recent maintenance",
                        "series": [
                            {"name": "Maintenance", "data": [
                                {"x": r.planned_start_date.isoformat() if r.planned_start_date else "", "y": 1, "label": f"{r.maintenance_type}: {r.status}"}
                                for r in mo_rows
                            ]},
                        ],
                    }
            except Exception:
                pass
            return {"title": f"Maintenance: Capacity at {site_id}", "series": [], "note": "No capacity or maintenance data available"}

        return {
            "title": f"Maintenance: Capacity Utilization at {site_id}",
            "window": "-4w → +maintenance window",
            "series": [
                {"name": "Available Capacity", "data": [
                    {"x": r.effective_date.isoformat() if r.effective_date else "", "y": float(r.available_capacity or 0)}
                    for r in rows
                ]},
                {"name": "Planned Downtime (h)", "data": [
                    {"x": r.effective_date.isoformat() if r.effective_date else "", "y": float(r.planned_downtime_hours or 0)}
                    for r in rows
                ]},
            ],
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
