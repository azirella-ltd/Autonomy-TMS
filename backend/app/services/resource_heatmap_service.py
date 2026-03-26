"""
Resource Heatmap Service

Builds a sites x weeks grid of capacity utilization data for visual heatmap rendering.
Queries resource_capacity, supply_plan (mo_request), production_orders, and powell_mo_decisions
to compute utilization per site per week across the planning horizon.
"""

from datetime import date, timedelta
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session


class ResourceHeatmapService:
    """Compute a sites x weeks utilization grid for a given supply chain config."""

    def __init__(self, db: Session):
        self.db = db

    def build_heatmap_data(
        self,
        config_id: int,
        horizon_weeks: int = 12,
        site_type: Optional[str] = None,
    ) -> dict:
        """
        Build the heatmap grid.

        Parameters
        ----------
        config_id : int
            Supply chain config to scope queries.
        horizon_weeks : int
            Number of weeks to project (default 12).
        site_type : str, optional
            Filter by site master_type (e.g. MANUFACTURER, INVENTORY).

        Returns
        -------
        dict with config_id, horizon_weeks, week_labels, sites[], bottleneck_alerts[].
        """
        # --- 1. Resolve sites ---
        site_filter = ""
        params = {"config_id": config_id, "horizon_weeks": horizon_weeks}
        if site_type:
            site_filter = "AND UPPER(s.master_type) = :site_type"
            params["site_type"] = site_type.upper()

        sites_sql = text(f"""
            SELECT s.id, s.name, s.master_type
            FROM site s
            WHERE s.config_id = :config_id
              AND s.is_external = false
              {site_filter}
            ORDER BY
              CASE UPPER(COALESCE(s.master_type, ''))
                WHEN 'MANUFACTURER' THEN 1
                WHEN 'INVENTORY' THEN 2
                ELSE 3
              END,
              s.name
        """)
        sites_rows = self.db.execute(sites_sql, params).fetchall()

        if not sites_rows:
            return self._empty_response(config_id, horizon_weeks)

        site_ids = [r[0] for r in sites_rows]
        site_map = {r[0]: {"site_id": str(r[0]), "site_name": r[1], "master_type": r[2]} for r in sites_rows}

        # --- 2. Determine week boundaries ---
        today = date.today()
        # Start on Monday of the current week
        week_start = today - timedelta(days=today.weekday())
        weeks = []
        week_labels = []
        for i in range(horizon_weeks):
            ws = week_start + timedelta(weeks=i)
            we = ws + timedelta(days=6)
            iso_week = ws.isocalendar()[1]
            weeks.append((ws, we))
            week_labels.append(f"W{iso_week} {ws.strftime('%b %d')}")

        horizon_start = weeks[0][0]
        horizon_end = weeks[-1][1]

        # --- 3. Query average available capacity per site per week from resource_capacity ---
        capacity_sql = text("""
            SELECT
                rc.site_id,
                DATE_TRUNC('week', rc.capacity_date)::date AS week_start,
                SUM(rc.available_capacity_hours) AS total_available,
                SUM(rc.utilized_capacity_hours) AS total_utilized
            FROM resource_capacity rc
            JOIN site s ON s.id = rc.site_id AND s.config_id = :config_id
            WHERE rc.site_id = ANY(:site_ids)
              AND rc.capacity_date >= :horizon_start
              AND rc.capacity_date <= :horizon_end
            GROUP BY rc.site_id, DATE_TRUNC('week', rc.capacity_date)::date
        """)
        cap_rows = self.db.execute(capacity_sql, {
            "config_id": config_id,
            "site_ids": site_ids,
            "horizon_start": horizon_start,
            "horizon_end": horizon_end,
        }).fetchall()

        # Index: (site_id, week_start_date) -> {available, utilized}
        cap_index = {}
        for row in cap_rows:
            key = (row[0], row[1])
            cap_index[key] = {"available": float(row[2] or 0), "utilized": float(row[3] or 0)}

        # --- 4. Count planned MOs from supply_plan ---
        mo_sql = text("""
            SELECT
                sp.site_id,
                DATE_TRUNC('week', sp.planned_order_date)::date AS week_start,
                COUNT(*) AS order_count,
                COALESCE(SUM(sp.planned_order_quantity), 0) AS total_qty
            FROM supply_plan sp
            WHERE sp.config_id = :config_id
              AND sp.plan_type = 'mo_request'
              AND sp.site_id = ANY(:site_ids)
              AND sp.planned_order_date >= :horizon_start
              AND sp.planned_order_date <= :horizon_end
            GROUP BY sp.site_id, DATE_TRUNC('week', sp.planned_order_date)::date
        """)
        mo_rows = self.db.execute(mo_sql, {
            "config_id": config_id,
            "site_ids": site_ids,
            "horizon_start": horizon_start,
            "horizon_end": horizon_end,
        }).fetchall()

        mo_index = {}
        for row in mo_rows:
            key = (row[0], row[1])
            mo_index[key] = {"count": int(row[2]), "qty": float(row[3])}

        # --- 5. Count production_orders ---
        po_sql = text("""
            SELECT
                po.site_id,
                DATE_TRUNC('week', po.planned_start_date)::date AS week_start,
                COUNT(*) AS order_count,
                COALESCE(SUM(po.resource_hours_planned), 0) AS total_hours
            FROM production_orders po
            WHERE po.config_id = :config_id
              AND po.site_id = ANY(:site_ids)
              AND po.status IN ('PLANNED', 'RELEASED', 'IN_PROGRESS')
              AND po.planned_start_date >= :horizon_start
              AND po.planned_start_date <= :horizon_end
            GROUP BY po.site_id, DATE_TRUNC('week', po.planned_start_date)::date
        """)
        po_rows = self.db.execute(po_sql, {
            "config_id": config_id,
            "site_ids": site_ids,
            "horizon_start": horizon_start,
            "horizon_end": horizon_end,
        }).fetchall()

        po_index = {}
        for row in po_rows:
            key = (row[0], row[1])
            po_index[key] = {"count": int(row[2]), "hours": float(row[3])}

        # --- 6. Check powell_mo_decisions for pending/actioned load ---
        powell_sql = text("""
            SELECT
                pmd.site_id,
                DATE_TRUNC('week', pmd.created_at)::date AS week_start,
                COUNT(*) AS decision_count
            FROM powell_mo_decisions pmd
            WHERE pmd.config_id = :config_id
              AND pmd.site_id::int = ANY(:site_ids)
              AND pmd.status IN ('INFORMED', 'ACTIONED')
              AND pmd.created_at >= :horizon_start
              AND pmd.created_at <= :horizon_end
            GROUP BY pmd.site_id, DATE_TRUNC('week', pmd.created_at)::date
        """)
        try:
            powell_rows = self.db.execute(powell_sql, {
                "config_id": config_id,
                "site_ids": site_ids,
                "horizon_start": horizon_start,
                "horizon_end": horizon_end,
            }).fetchall()
            powell_index = {}
            for row in powell_rows:
                key = (int(row[0]) if row[0] else None, row[1])
                powell_index[key] = int(row[2])
        except Exception:
            # Table may not exist yet in all environments
            powell_index = {}

        # --- 7. Query competing products per site per week (for bottleneck alerts) ---
        products_sql = text("""
            SELECT
                sp.site_id,
                DATE_TRUNC('week', sp.planned_order_date)::date AS week_start,
                ARRAY_AGG(DISTINCT sp.product_id) AS product_ids
            FROM supply_plan sp
            WHERE sp.config_id = :config_id
              AND sp.plan_type = 'mo_request'
              AND sp.site_id = ANY(:site_ids)
              AND sp.planned_order_date >= :horizon_start
              AND sp.planned_order_date <= :horizon_end
            GROUP BY sp.site_id, DATE_TRUNC('week', sp.planned_order_date)::date
        """)
        prod_rows = self.db.execute(products_sql, {
            "config_id": config_id,
            "site_ids": site_ids,
            "horizon_start": horizon_start,
            "horizon_end": horizon_end,
        }).fetchall()

        prod_index = {}
        for row in prod_rows:
            key = (row[0], row[1])
            prod_index[key] = row[2] or []

        # --- 8. Assemble the grid ---
        result_sites = []
        bottleneck_alerts = []
        DEFAULT_WEEKLY_CAPACITY = 40.0  # 5 days x 8 hours fallback

        for sid in site_ids:
            info = site_map[sid]
            week_cells = []

            for ws, _we in weeks:
                cap = cap_index.get((sid, ws))
                mo = mo_index.get((sid, ws), {"count": 0, "qty": 0})
                po = po_index.get((sid, ws), {"count": 0, "hours": 0})
                powell_count = powell_index.get((sid, ws), 0)

                available = cap["available"] if cap else DEFAULT_WEEKLY_CAPACITY
                planned_orders = mo["count"] + po["count"] + powell_count

                # Compute utilization: prefer resource_capacity utilized hours,
                # supplement with production_order resource hours
                if cap and cap["utilized"] > 0:
                    utilized = cap["utilized"] + po["hours"]
                elif po["hours"] > 0:
                    utilized = po["hours"]
                elif mo["qty"] > 0:
                    # Rough estimate: 1 hour per unit of planned MO quantity
                    utilized = mo["qty"] * 0.5
                else:
                    utilized = 0.0

                utilization = min(utilized / available, 2.0) if available > 0 else 0.0

                week_cells.append({
                    "week": ws.isoformat(),
                    "utilization": round(utilization, 3),
                    "planned_orders": planned_orders,
                    "available_capacity": round(available, 1),
                })

                # Bottleneck detection: utilization > 85%
                if utilization > 0.85:
                    products = prod_index.get((sid, ws), [])
                    bottleneck_alerts.append({
                        "site_id": str(sid),
                        "site_name": info["site_name"],
                        "week": ws.isoformat(),
                        "utilization": round(utilization, 3),
                        "competing_products": [str(p) for p in products[:10]],
                    })

            result_sites.append({
                "site_id": str(sid),
                "site_name": info["site_name"],
                "master_type": info["master_type"],
                "team_size": None,
                "weeks": week_cells,
            })

        # Sort bottleneck alerts by utilization descending
        bottleneck_alerts.sort(key=lambda a: a["utilization"], reverse=True)

        return {
            "config_id": config_id,
            "horizon_weeks": horizon_weeks,
            "week_labels": week_labels,
            "sites": result_sites,
            "bottleneck_alerts": bottleneck_alerts,
        }

    def get_cell_detail(
        self,
        config_id: int,
        site_id: int,
        week_start: date,
    ) -> dict:
        """
        Get detail for a single cell: which products/orders consume capacity that week.
        """
        week_end = week_start + timedelta(days=6)

        # Supply plan MOs
        detail_sql = text("""
            SELECT sp.product_id, p.description, sp.planned_order_quantity, sp.planned_order_date
            FROM supply_plan sp
            LEFT JOIN product p ON p.id = sp.product_id
            WHERE sp.config_id = :config_id
              AND sp.site_id = :site_id
              AND sp.plan_type = 'mo_request'
              AND sp.planned_order_date >= :week_start
              AND sp.planned_order_date <= :week_end
            ORDER BY sp.planned_order_quantity DESC
        """)
        sp_rows = self.db.execute(detail_sql, {
            "config_id": config_id,
            "site_id": site_id,
            "week_start": week_start,
            "week_end": week_end,
        }).fetchall()

        # Production orders
        po_sql = text("""
            SELECT po.order_number, po.item_id, po.planned_quantity, po.resource_hours_planned,
                   po.status, po.priority
            FROM production_orders po
            WHERE po.config_id = :config_id
              AND po.site_id = :site_id
              AND po.status IN ('PLANNED', 'RELEASED', 'IN_PROGRESS')
              AND po.planned_start_date >= :week_start
              AND po.planned_start_date <= :week_end
            ORDER BY po.priority ASC, po.resource_hours_planned DESC
        """)
        po_rows = self.db.execute(po_sql, {
            "config_id": config_id,
            "site_id": site_id,
            "week_start": week_start,
            "week_end": week_end,
        }).fetchall()

        supply_plan_items = [
            {
                "product_id": str(r[0]),
                "product_name": r[1] or str(r[0]),
                "quantity": float(r[2] or 0),
                "date": r[3].isoformat() if r[3] else None,
            }
            for r in sp_rows
        ]

        production_orders = [
            {
                "order_number": r[0],
                "product_id": str(r[1]),
                "planned_quantity": int(r[2] or 0),
                "resource_hours": float(r[3] or 0),
                "status": r[4],
                "priority": int(r[5] or 5),
            }
            for r in po_rows
        ]

        return {
            "config_id": config_id,
            "site_id": str(site_id),
            "week_start": week_start.isoformat(),
            "supply_plan_items": supply_plan_items,
            "production_orders": production_orders,
        }

    def _empty_response(self, config_id: int, horizon_weeks: int) -> dict:
        return {
            "config_id": config_id,
            "horizon_weeks": horizon_weeks,
            "week_labels": [],
            "sites": [],
            "bottleneck_alerts": [],
        }
