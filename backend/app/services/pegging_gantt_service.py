"""
Pegging Gantt Service

Builds Gantt chart data from pegging chains + BOM + supply plans.
Shows how demand at a specific time bucket is satisfied through the
full pegging tree (multi-level BOM) with conformal prediction intervals.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class PeggingGanttService:
    def __init__(self, db: Session):
        self.db = db

    def build_gantt_data(
        self,
        config_id: int,
        product_id: str,
        site_id: int,
        demand_date: date,
        demand_type: Optional[str] = None,
        demand_id: Optional[str] = None,
        include_conformal: bool = True,
    ) -> dict:
        """
        Build Gantt chart data showing how demand at a specific time bucket
        is satisfied through the full pegging tree (multi-level BOM).

        Returns hierarchical rows (by BOM level) with supply bars showing
        order dates, receipt dates, quantities, and conformal prediction
        intervals for lead time uncertainty.
        """
        # Step 1: Get demand context
        demand_summary = self._get_demand_summary(
            config_id, product_id, site_id, demand_date,
        )

        # Step 2: Get pegging chains
        date_lo = demand_date - timedelta(days=3)
        date_hi = demand_date + timedelta(days=3)
        pegging_rows = self._get_pegging_records(
            config_id, product_id, site_id, date_lo, date_hi,
            demand_type, demand_id,
        )

        # Step 3: Walk upstream to build full pegging tree
        pegging_tree = self._walk_upstream(pegging_rows)

        # Step 4: Get BOM hierarchy
        bom_tree = self._get_bom_hierarchy(config_id, product_id)

        # Step 5: Build Gantt rows
        if pegging_tree:
            gantt_rows = self._build_gantt_rows_from_pegging(
                config_id, product_id, site_id, demand_date,
                pegging_tree, bom_tree, include_conformal,
            )
            total_pegged = sum(
                r["pegged_quantity"] for r in pegging_rows
            )
        else:
            # Step 6: Fallback — no pegging data
            gantt_rows = self._build_gantt_rows_fallback(
                config_id, product_id, site_id, demand_date,
                bom_tree, include_conformal,
            )
            total_pegged = 0.0

        demand_summary["total_pegged"] = total_pegged
        demand_summary["unpegged"] = max(
            0.0, demand_summary["total_demand"] - total_pegged,
        )

        # Step 7: Conformal metadata
        conformal_metadata = self._get_conformal_metadata(
            config_id, product_id, site_id, demand_date,
        ) if include_conformal else {"joint_coverage": None, "demand_interval": None}

        # Sort rows by bom_level ASC, then product_id
        gantt_rows.sort(key=lambda r: (r["bom_level"], r["product_id"]))

        return {
            "demand_summary": demand_summary,
            "gantt_rows": gantt_rows,
            "conformal_metadata": conformal_metadata,
        }

    # ------------------------------------------------------------------
    # Step 1: Demand context
    # ------------------------------------------------------------------

    def _get_demand_summary(
        self, config_id: int, product_id: str, site_id: int, demand_date: date,
    ) -> dict:
        """Sum all demand sources (forecast + customer orders) for product/site/date."""
        # Product and site names
        names = self.db.execute(
            text("""
                SELECT p.description AS product_name, s.name AS site_name
                FROM product p, site s
                WHERE p.id = :product_id AND s.id = :site_id
            """),
            {"product_id": product_id, "site_id": site_id},
        ).fetchone()

        product_name = names.product_name if names else product_id
        site_name = names.site_name if names else str(site_id)

        # Forecast demand
        fcst_row = self.db.execute(
            text("""
                SELECT COALESCE(SUM(forecast_quantity), 0) AS total
                FROM forecast
                WHERE config_id = :config_id
                  AND product_id = :product_id
                  AND site_id = :site_id
                  AND forecast_date = :demand_date
            """),
            {
                "config_id": config_id,
                "product_id": product_id,
                "site_id": site_id,
                "demand_date": demand_date,
            },
        ).fetchone()
        forecast_demand = fcst_row.total if fcst_row else 0.0

        # Customer order demand
        order_row = self.db.execute(
            text("""
                SELECT COALESCE(SUM(ordered_quantity), 0) AS total
                FROM outbound_order_line
                WHERE config_id = :config_id
                  AND product_id = :product_id
                  AND site_id = :site_id
                  AND requested_delivery_date = :demand_date
            """),
            {
                "config_id": config_id,
                "product_id": product_id,
                "site_id": site_id,
                "demand_date": demand_date,
            },
        ).fetchone()
        order_demand = order_row.total if order_row else 0.0

        return {
            "product_id": product_id,
            "product_name": product_name,
            "site_id": site_id,
            "site_name": site_name,
            "demand_date": demand_date.isoformat(),
            "total_demand": forecast_demand + order_demand,
            "total_pegged": 0.0,  # filled later
            "unpegged": 0.0,  # filled later
        }

    # ------------------------------------------------------------------
    # Step 2: Pegging records
    # ------------------------------------------------------------------

    def _get_pegging_records(
        self,
        config_id: int,
        product_id: str,
        site_id: int,
        date_lo: date,
        date_hi: date,
        demand_type: Optional[str],
        demand_id: Optional[str],
    ) -> list[dict]:
        """Query supply_demand_pegging for matching records."""
        params: dict = {
            "config_id": config_id,
            "product_id": product_id,
            "site_id": site_id,
            "date_lo": date_lo,
            "date_hi": date_hi,
        }

        where_extra = ""
        if demand_type:
            where_extra += " AND demand_type = :demand_type"
            params["demand_type"] = demand_type
        if demand_id:
            where_extra += " AND demand_id = :demand_id"
            params["demand_id"] = demand_id

        rows = self.db.execute(
            text(f"""
                SELECT id, product_id, site_id, demand_type, demand_id,
                       supply_type, supply_id, supply_site_id,
                       pegged_quantity, pegging_date, pegging_status,
                       upstream_pegging_id, chain_id, chain_depth,
                       demand_priority, is_active
                FROM supply_demand_pegging
                WHERE config_id = :config_id
                  AND product_id = :product_id
                  AND site_id = :site_id
                  AND pegging_date BETWEEN :date_lo AND :date_hi
                  AND is_active = true
                  {where_extra}
                ORDER BY chain_id, chain_depth
            """),
            params,
        ).fetchall()

        return [dict(r._mapping) for r in rows]

    # ------------------------------------------------------------------
    # Step 3: Walk upstream
    # ------------------------------------------------------------------

    def _walk_upstream(self, pegging_rows: list[dict]) -> list[dict]:
        """
        Follow upstream_pegging_id recursively to build the full tree.
        Returns all pegging records in the tree (original + upstream).
        """
        if not pegging_rows:
            return []

        # Collect all chain_ids from the initial set
        chain_ids = list({r["chain_id"] for r in pegging_rows})
        if not chain_ids:
            return pegging_rows

        # Use chain_id to fetch all records in those chains (all depths)
        placeholders = ", ".join(f":cid_{i}" for i in range(len(chain_ids)))
        params = {f"cid_{i}": cid for i, cid in enumerate(chain_ids)}

        rows = self.db.execute(
            text(f"""
                SELECT id, product_id, site_id, demand_type, demand_id,
                       supply_type, supply_id, supply_site_id,
                       pegged_quantity, pegging_date, pegging_status,
                       upstream_pegging_id, chain_id, chain_depth,
                       demand_priority, is_active
                FROM supply_demand_pegging
                WHERE chain_id IN ({placeholders})
                  AND is_active = true
                ORDER BY chain_id, chain_depth
            """),
            params,
        ).fetchall()

        return [dict(r._mapping) for r in rows]

    # ------------------------------------------------------------------
    # Step 4: BOM hierarchy
    # ------------------------------------------------------------------

    def _get_bom_hierarchy(
        self, config_id: int, product_id: str, max_depth: int = 10,
    ) -> list[dict]:
        """
        Recursively get BOM components for a product.
        Returns flat list with bom_level indicating depth.
        """
        # Recursive CTE to walk the BOM tree
        rows = self.db.execute(
            text("""
                WITH RECURSIVE bom_tree AS (
                    -- Base: direct components of the root product
                    SELECT
                        b.product_id AS parent_product_id,
                        b.component_product_id AS product_id,
                        b.component_quantity,
                        b.scrap_percentage,
                        1 AS bom_level
                    FROM product_bom b
                    WHERE b.product_id = :product_id
                      AND b.config_id = :config_id
                      AND (b.is_active IS NULL OR b.is_active = 'true')

                    UNION ALL

                    -- Recurse: components of components
                    SELECT
                        b.product_id AS parent_product_id,
                        b.component_product_id AS product_id,
                        b.component_quantity,
                        b.scrap_percentage,
                        bt.bom_level + 1 AS bom_level
                    FROM product_bom b
                    JOIN bom_tree bt ON bt.product_id = b.product_id
                    WHERE b.config_id = :config_id
                      AND (b.is_active IS NULL OR b.is_active = 'true')
                      AND bt.bom_level < :max_depth
                )
                SELECT bt.parent_product_id, bt.product_id,
                       bt.component_quantity, bt.scrap_percentage,
                       bt.bom_level,
                       p.description AS product_name
                FROM bom_tree bt
                LEFT JOIN product p ON p.id = bt.product_id
                ORDER BY bt.bom_level, bt.product_id
            """),
            {
                "product_id": product_id,
                "config_id": config_id,
                "max_depth": max_depth,
            },
        ).fetchall()

        return [dict(r._mapping) for r in rows]

    # ------------------------------------------------------------------
    # Step 5: Build Gantt rows from pegging
    # ------------------------------------------------------------------

    def _build_gantt_rows_from_pegging(
        self,
        config_id: int,
        product_id: str,
        site_id: int,
        demand_date: date,
        pegging_tree: list[dict],
        bom_tree: list[dict],
        include_conformal: bool,
    ) -> list[dict]:
        """Build Gantt rows from pegging records + BOM."""
        # Collect all unique product_ids from pegging tree
        products_in_tree: dict[str, dict] = {}
        for peg in pegging_tree:
            pid = peg["product_id"]
            if pid not in products_in_tree:
                products_in_tree[pid] = {
                    "pegging_records": [],
                    "chain_depth": peg["chain_depth"],
                }
            products_in_tree[pid]["pegging_records"].append(peg)

        # Build a BOM lookup: product_id -> {parent, quantity, bom_level}
        bom_lookup: dict[str, dict] = {}
        for bom in bom_tree:
            bom_lookup[bom["product_id"]] = {
                "parent_product_id": bom["parent_product_id"],
                "bom_quantity": bom["component_quantity"] or 1.0,
                "bom_level": bom["bom_level"],
                "product_name": bom.get("product_name"),
            }

        # Fetch product names and site names for all products in tree
        all_product_ids = list(products_in_tree.keys())
        all_product_ids.append(product_id)  # include root
        product_names = self._get_product_names(all_product_ids)
        site_names_cache: dict[int, str] = {}

        gantt_rows = []

        # Root product row (bom_level=0)
        root_bars = self._get_bars_for_product(
            config_id, product_id, site_id, demand_date,
            products_in_tree.get(product_id, {}).get("pegging_records", []),
            include_conformal, site_names_cache,
        )
        gantt_rows.append({
            "product_id": product_id,
            "product_name": product_names.get(product_id, product_id),
            "bom_level": 0,
            "parent_product_id": None,
            "bom_quantity": 1.0,
            "bars": root_bars,
        })

        # BOM component rows
        for bom in bom_tree:
            comp_id = bom["product_id"]
            bom_info = bom_lookup.get(comp_id, {})
            pegging_recs = products_in_tree.get(comp_id, {}).get("pegging_records", [])

            # Determine which site to look up supply for this component
            comp_site_id = site_id  # default to demand site
            for peg in pegging_recs:
                if peg.get("supply_site_id"):
                    comp_site_id = peg["supply_site_id"]
                    break

            bars = self._get_bars_for_product(
                config_id, comp_id, comp_site_id, demand_date,
                pegging_recs, include_conformal, site_names_cache,
            )

            gantt_rows.append({
                "product_id": comp_id,
                "product_name": product_names.get(comp_id, bom.get("product_name") or comp_id),
                "bom_level": bom["bom_level"],
                "parent_product_id": bom["parent_product_id"],
                "bom_quantity": bom["component_quantity"] or 1.0,
                "bars": bars,
            })

        return gantt_rows

    # ------------------------------------------------------------------
    # Step 6: Fallback — no pegging data
    # ------------------------------------------------------------------

    def _build_gantt_rows_fallback(
        self,
        config_id: int,
        product_id: str,
        site_id: int,
        demand_date: date,
        bom_tree: list[dict],
        include_conformal: bool,
    ) -> list[dict]:
        """Build Gantt rows when no pegging records exist."""
        product_names = self._get_product_names(
            [product_id] + [b["product_id"] for b in bom_tree],
        )
        site_names_cache: dict[int, str] = {}

        gantt_rows = []

        # Root product row
        root_bars = self._get_bars_for_product(
            config_id, product_id, site_id, demand_date,
            [], include_conformal, site_names_cache,
        )
        gantt_rows.append({
            "product_id": product_id,
            "product_name": product_names.get(product_id, product_id),
            "bom_level": 0,
            "parent_product_id": None,
            "bom_quantity": 1.0,
            "bars": root_bars,
        })

        # BOM component rows
        for bom in bom_tree:
            comp_id = bom["product_id"]
            bars = self._get_bars_for_product(
                config_id, comp_id, site_id, demand_date,
                [], include_conformal, site_names_cache,
            )
            gantt_rows.append({
                "product_id": comp_id,
                "product_name": product_names.get(comp_id, bom.get("product_name") or comp_id),
                "bom_level": bom["bom_level"],
                "parent_product_id": bom["parent_product_id"],
                "bom_quantity": bom["component_quantity"] or 1.0,
                "bars": bars,
            })

        return gantt_rows

    # ------------------------------------------------------------------
    # Bar construction helpers
    # ------------------------------------------------------------------

    def _get_bars_for_product(
        self,
        config_id: int,
        product_id: str,
        site_id: int,
        demand_date: date,
        pegging_records: list[dict],
        include_conformal: bool,
        site_names_cache: dict[int, str],
    ) -> list[dict]:
        """Build all bars (on-hand + supply plan records) for a product/site."""
        bars: list[dict] = []

        # On-hand inventory bar
        inv_row = self.db.execute(
            text("""
                SELECT on_hand_qty, in_transit_qty
                FROM inv_level
                WHERE config_id = :config_id
                  AND product_id = :product_id
                  AND site_id = :site_id
                ORDER BY inventory_date DESC NULLS LAST
                LIMIT 1
            """),
            {
                "config_id": config_id,
                "product_id": product_id,
                "site_id": site_id,
            },
        ).fetchone()

        if inv_row and inv_row.on_hand_qty and inv_row.on_hand_qty > 0:
            bars.append({
                "type": "on_hand",
                "supply_id": None,
                "quantity": inv_row.on_hand_qty,
                "bar_start": None,
                "bar_end": None,
                "lead_time_days": None,
                "lead_time_lower": None,
                "lead_time_upper": None,
                "source_site": None,
                "supplier": None,
                "pegging_id": None,
                "chain_id": None,
                "pegging_status": None,
                "priority": None,
                "label": "On Hand",
            })

        if inv_row and inv_row.in_transit_qty and inv_row.in_transit_qty > 0:
            bars.append({
                "type": "in_transit",
                "supply_id": None,
                "quantity": inv_row.in_transit_qty,
                "bar_start": None,
                "bar_end": None,
                "lead_time_days": None,
                "lead_time_lower": None,
                "lead_time_upper": None,
                "source_site": None,
                "supplier": None,
                "pegging_id": None,
                "chain_id": None,
                "pegging_status": None,
                "priority": None,
                "label": "In Transit",
            })

        # Supply plan records
        supply_rows = self.db.execute(
            text("""
                SELECT id, plan_type, planned_order_quantity,
                       planned_order_date, planned_receipt_date,
                       supplier_id, from_site_id,
                       lead_time_lower, lead_time_upper, joint_coverage
                FROM supply_plan
                WHERE config_id = :config_id
                  AND product_id = :product_id
                  AND site_id = :site_id
                  AND planned_receipt_date BETWEEN :date_lo AND :date_hi
                ORDER BY planned_order_date
            """),
            {
                "config_id": config_id,
                "product_id": product_id,
                "site_id": site_id,
                "date_lo": demand_date - timedelta(days=30),
                "date_hi": demand_date + timedelta(days=7),
            },
        ).fetchall()

        # Build a set of supply_ids from pegging for quick lookup
        pegged_supply_ids = {
            r["supply_id"]: r for r in pegging_records
        }

        for sp in supply_rows:
            plan_type = sp.plan_type or "planned_order"
            bar_type = plan_type if plan_type in (
                "po_request", "mo_request", "to_request",
            ) else "planned_order"

            # Calculate lead time in days
            lead_time_days = None
            if sp.planned_order_date and sp.planned_receipt_date:
                lead_time_days = (sp.planned_receipt_date - sp.planned_order_date).days

            # Source site name
            source_site_name = None
            if sp.from_site_id:
                source_site_name = self._get_site_name(sp.from_site_id, site_names_cache)

            # Match to pegging record
            sp_id_str = str(sp.id)
            peg_match = pegged_supply_ids.get(sp_id_str)

            # Label
            label_map = {
                "po_request": "Purchase Order",
                "mo_request": "Manufacturing Order",
                "to_request": "Transfer Order",
                "planned_order": "Planned Order",
            }
            label = label_map.get(bar_type, bar_type.replace("_", " ").title())
            if sp.supplier_id:
                label += f" ({sp.supplier_id})"

            bar = {
                "type": bar_type,
                "supply_id": sp_id_str,
                "quantity": sp.planned_order_quantity or 0.0,
                "bar_start": sp.planned_order_date.isoformat() if sp.planned_order_date else None,
                "bar_end": sp.planned_receipt_date.isoformat() if sp.planned_receipt_date else None,
                "lead_time_days": lead_time_days,
                "lead_time_lower": None,
                "lead_time_upper": None,
                "source_site": source_site_name,
                "supplier": sp.supplier_id,
                "pegging_id": peg_match["id"] if peg_match else None,
                "chain_id": peg_match["chain_id"] if peg_match else None,
                "pegging_status": peg_match["pegging_status"] if peg_match else None,
                "priority": peg_match["demand_priority"] if peg_match else None,
                "label": label,
            }

            # Conformal intervals
            if include_conformal and sp.lead_time_lower is not None:
                bar["lead_time_lower"] = sp.lead_time_lower
                bar["lead_time_upper"] = sp.lead_time_upper

            bars.append(bar)

        return bars

    def _get_product_names(self, product_ids: list[str]) -> dict[str, str]:
        """Fetch product descriptions for a list of product IDs."""
        if not product_ids:
            return {}
        unique_ids = list(set(product_ids))
        placeholders = ", ".join(f":pid_{i}" for i in range(len(unique_ids)))
        params = {f"pid_{i}": pid for i, pid in enumerate(unique_ids)}

        rows = self.db.execute(
            text(f"""
                SELECT id, description FROM product
                WHERE id IN ({placeholders})
            """),
            params,
        ).fetchall()

        return {r.id: (r.description or r.id) for r in rows}

    def _get_site_name(self, site_id: int, cache: dict[int, str]) -> str:
        """Get site name with caching."""
        if site_id in cache:
            return cache[site_id]
        row = self.db.execute(
            text("SELECT name FROM site WHERE id = :site_id"),
            {"site_id": site_id},
        ).fetchone()
        name = row.name if row else str(site_id)
        cache[site_id] = name
        return name

    # ------------------------------------------------------------------
    # Conformal metadata
    # ------------------------------------------------------------------

    def _get_conformal_metadata(
        self, config_id: int, product_id: str, site_id: int, demand_date: date,
    ) -> dict:
        """Get aggregate conformal prediction metadata for the demand bucket."""
        row = self.db.execute(
            text("""
                SELECT MIN(joint_coverage) AS joint_coverage,
                       MIN(demand_lower) AS demand_lower,
                       MAX(demand_upper) AS demand_upper
                FROM supply_plan
                WHERE config_id = :config_id
                  AND product_id = :product_id
                  AND site_id = :site_id
                  AND planned_receipt_date BETWEEN :date_lo AND :date_hi
                  AND joint_coverage IS NOT NULL
            """),
            {
                "config_id": config_id,
                "product_id": product_id,
                "site_id": site_id,
                "date_lo": demand_date - timedelta(days=30),
                "date_hi": demand_date + timedelta(days=7),
            },
        ).fetchone()

        if row and row.joint_coverage is not None:
            demand_interval = None
            if row.demand_lower is not None and row.demand_upper is not None:
                demand_interval = [row.demand_lower, row.demand_upper]
            return {
                "joint_coverage": row.joint_coverage,
                "demand_interval": demand_interval,
            }

        return {"joint_coverage": None, "demand_interval": None}
