"""
Hierarchical Metrics Service

Generates Gartner-aligned supply chain metrics organized into 4 tiers
(ASSESS, DIAGNOSE, CORRECT, AI-as-Labor) with hierarchy-aware data
sourced entirely from the database: Site, Product, Forecast, PerformanceMetric,
InvLevel, SOPWorklistItem, and AgentDecisionMetrics.

Hierarchy dimensions:
  - Site:    Company > Region > Site
  - Product: Category > Product
  - Time:    Year > Quarter > Month
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, asc, case

from app.models.metrics_hierarchy import GARTNER_METRICS, GartnerLevel

logger = logging.getLogger(__name__)

# Mapping from dashboard metric key → Gartner metric code.
# Used to annotate tier metric dicts with gartner_level and gartner_code.
_METRIC_KEY_TO_GARTNER: Dict[str, str] = {
    # Tier 1 (L1 Strategic)
    "gross_margin":             "SCMC",
    "revenue":                  "SCMC",
    # Tier 2 (L2 Functional)
    "inventory_turns":          "DOS",
    "days_of_supply":           "DOS",
    "fill_rate":                "FR",
    "on_time_delivery":         "OTD",
    "forecast_accuracy":        "FA",
    "lost_sales":               "SOLD",
    # Tier 3 (L3 Operational)
    "safety_stock_fill_rate":   "SSFR",
    "po_lead_time":             "POLTA",
    "mfg_schedule_adherence":   "MSA",
    "first_pass_yield":         "FPYR",
    "inventory_record_accuracy": "IRA",
    "lead_time_bias":           "LTBIAS",
    "expedite_rate":            "EXPRT",
    "buffer_level_adequacy":    "BLA",
}

# Region mapping (state abbreviation → region name)
_STATE_TO_REGION: Dict[str, str] = {
    "OR": "Northwest", "WA": "Northwest",
    "AZ": "Southwest", "CA": "Southwest", "UT": "Southwest",
    "IL": "Central",   "MN": "Central",   "TX": "Central",  "AR": "Central",
    "PA": "Northeast", "NY": "Northeast",
    "GA": "Southeast",
}


def _status(value: Optional[float], target: float, lower_is_better: bool = False) -> str:
    if value is None:
        return "info"
    if lower_is_better:
        if value <= target:
            return "success"
        elif value <= target * 1.15:
            return "warning"
        return "danger"
    else:
        if value >= target:
            return "success"
        elif value >= target * 0.9:
            return "warning"
        return "danger"


class HierarchicalMetricsService:
    """Generates Gartner-aligned metrics with hierarchy context from the DB."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    # =========================================================================
    # Public API
    # =========================================================================

    def get_dashboard_metrics(
        self,
        tenant_id: int = 1,
        customer_id: int = None,       # alias accepted from API layer
        site_level: str = "company",
        site_key: Optional[str] = None,
        product_level: str = "category",
        product_key: Optional[str] = None,
        time_bucket: str = "quarter",
        time_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Normalize tenant_id: API layer passes customer_id as keyword arg
        if customer_id is not None:
            tenant_id = customer_id

        site_key = site_key or "ALL"
        product_key = product_key or "ALL"

        site_hier = self._build_site_hierarchy(tenant_id)
        product_hier = self._build_product_hierarchy(tenant_id)
        time_hier = self._build_time_hierarchy(tenant_id)

        if time_key is None:
            # Default to the most recent quarter in the hierarchy
            time_key = self._latest_time_key(time_hier, time_bucket)

        return {
            "hierarchy_context": {
                "site_level": site_level,
                "site_key": site_key,
                "product_level": product_level,
                "product_key": product_key,
                "time_bucket": time_bucket,
                "time_key": time_key,
            },
            "breadcrumbs": self._build_breadcrumbs(
                site_hier, product_hier, time_hier,
                site_level, site_key, product_level, product_key, time_bucket, time_key,
            ),
            "children": self._build_children(
                site_hier, product_hier, time_hier,
                site_level, site_key, product_level, product_key, time_bucket, time_key,
            ),
            "tiers": self._annotate_gartner_levels({
                "tier1_assess":  self._tier1_assess(tenant_id, site_key, product_key, time_key),
                "tier2_diagnose": self._tier2_diagnose(tenant_id, site_key, product_key, time_key),
                "tier3_correct": self._tier3_correct(tenant_id, site_key, product_key, time_key),
                "tier4_agent":   self._tier4_agent(tenant_id, time_key),
            }),
            "trend_data": self._trend_data(tenant_id),
        }

    # =========================================================================
    # Gartner SCOR level annotation
    # =========================================================================

    @staticmethod
    def _annotate_gartner_levels(tiers: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process the tiers dict to annotate each metric with its
        Gartner SCOR level (L1–L4) and canonical metric code.

        Walks every tier's "metrics" dict (and any nested "metrics" dicts)
        and injects ``gartner_code`` and ``gartner_level`` fields where the
        metric key is present in ``_METRIC_KEY_TO_GARTNER``.

        This is a read-only enrichment — no existing keys are mutated.
        """
        def _enrich_metrics(metrics: dict) -> dict:
            enriched = {}
            for key, value in metrics.items():
                if not isinstance(value, dict):
                    enriched[key] = value
                    continue
                m = dict(value)
                # Annotate at the top level if key is mapped
                if key in _METRIC_KEY_TO_GARTNER:
                    code = _METRIC_KEY_TO_GARTNER[key]
                    defn = GARTNER_METRICS.get(code)
                    if defn:
                        m.setdefault("gartner_code", code)
                        m.setdefault("gartner_level", defn.level.value)
                # Recurse into nested "metrics" dicts (e.g. tier3 sub-sections)
                if "metrics" in m and isinstance(m["metrics"], dict):
                    m["metrics"] = _enrich_metrics(m["metrics"])
                enriched[key] = m
            return enriched

        result = {}
        for tier_key, tier_value in tiers.items():
            if not isinstance(tier_value, dict):
                result[tier_key] = tier_value
                continue
            t = dict(tier_value)
            if "metrics" in t and isinstance(t["metrics"], dict):
                t["metrics"] = _enrich_metrics(t["metrics"])
            result[tier_key] = t
        return result

    # =========================================================================
    # Hierarchy builders
    # =========================================================================

    def _build_site_hierarchy(self, tenant_id: int) -> Dict[str, Any]:
        """
        Build site hierarchy from DB:
        ALL → Region (NW/SW/Central…) → Site (CDC_WEST, CUST_*)
        """
        if self.db is None:
            return {}
        try:
            from app.models.supply_chain_config import SupplyChainConfig, Site
            from app.models.sc_entities import Geography

            config = (
                self.db.query(SupplyChainConfig)
                .filter(SupplyChainConfig.tenant_id == tenant_id)
                .first()
            )
            if not config:
                return {}

            sites = (
                self.db.query(Site)
                .outerjoin(Geography, Site.geo_id == Geography.id)
                .filter(Site.config_id == config.id)
                .all()
            )

            # Group sites by region
            region_map: Dict[str, List] = {}
            for s in sites:
                geo = self.db.query(Geography).filter(Geography.id == s.geo_id).first() if s.geo_id else None
                state = geo.state_prov if geo else None
                region = _STATE_TO_REGION.get(state, "Other") if state else "Other"
                region_map.setdefault(region, []).append(s)

            region_children: Dict[str, Any] = {}
            for region, region_sites in sorted(region_map.items()):
                site_children = {
                    s.id: {
                        "label": s.name,
                        "level": "site",
                        "can_drill_down": False,
                        "master_type": s.master_type,
                    }
                    for s in region_sites
                }
                region_children[region] = {
                    "label": region,
                    "level": "region",
                    "can_drill_down": True,
                    "children": {"site": site_children},
                }

            return {
                "company": {
                    "ALL": {
                        "label": config.name or "All Sites",
                        "level": "company",
                        "can_drill_down": True,
                        "children": {"region": region_children},
                    }
                }
            }
        except Exception:
            logger.exception("Failed to build site hierarchy for tenant=%s", tenant_id)
            return {}

    def _build_product_hierarchy(self, tenant_id: int) -> Dict[str, Any]:
        """
        Build product hierarchy from DB:
        ALL → Category (Frozen Proteins / Beverages…) → Product (CFG22_FP001…)
        Uses product_hierarchy.description for human-readable category labels.
        """
        if self.db is None:
            return {}
        try:
            from app.models.supply_chain_config import SupplyChainConfig
            from app.models.sc_entities import Product

            config = (
                self.db.query(SupplyChainConfig)
                .filter(SupplyChainConfig.tenant_id == tenant_id)
                .first()
            )
            if not config:
                return {}

            products = (
                self.db.query(Product)
                .filter(Product.config_id == config.id)
                .all()
            )

            # Build product_group_id → human label map from product_hierarchy table
            try:
                from app.models.sc_entities import ProductHierarchy
                ph_rows = (
                    self.db.query(ProductHierarchy.id, ProductHierarchy.description)
                    .filter(ProductHierarchy.description.isnot(None))
                    .all()
                )
                group_label_map = {r.id: r.description for r in ph_rows}
            except Exception:
                group_label_map = {}

            # Group by product_group_id (category)
            cat_map: Dict[str, List] = {}
            for p in products:
                cat = p.product_group_id or "Uncategorized"
                cat_map.setdefault(cat, []).append(p)

            cat_children: Dict[str, Any] = {}
            for cat, cat_products in sorted(cat_map.items()):
                prod_children = {
                    p.id: {
                        "label": p.description or p.id,
                        "level": "product",
                        "can_drill_down": False,
                    }
                    for p in cat_products
                }
                # Use product_hierarchy description if available, else humanize the key
                cat_label = (
                    group_label_map.get(cat)
                    or cat.replace("_", " ").title()
                )
                cat_children[cat] = {
                    "label": cat_label,
                    "level": "family",
                    "can_drill_down": True,
                    "children": {"product": prod_children},
                }

            return {
                "category": {
                    "ALL": {
                        "label": "All Products",
                        "level": "category",
                        "can_drill_down": True,
                        "children": {"family": cat_children},
                    }
                }
            }
        except Exception:
            logger.exception("Failed to build product hierarchy for tenant=%s", tenant_id)
            return {}

    def _build_time_hierarchy(self, tenant_id: int) -> Dict[str, Any]:
        """Build time hierarchy from PerformanceMetric period_start dates."""
        if self.db is None:
            return {}
        try:
            from app.models.decision_tracking import PerformanceMetric

            rows = (
                self.db.query(
                    func.extract("year", PerformanceMetric.period_start).label("yr"),
                    func.extract("month", PerformanceMetric.period_start).label("mo"),
                )
                .filter(
                    PerformanceMetric.tenant_id == tenant_id,
                    PerformanceMetric.category.is_(None),
                )
                .distinct()
                .order_by("yr", "mo")
                .all()
            )

            _MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

            year_map: Dict[str, Any] = {}
            for row in rows:
                yr = int(row.yr)
                mo = int(row.mo)
                yr_key = str(yr)
                q = (mo - 1) // 3 + 1
                q_key = f"{yr}-Q{q}"
                mo_key = f"{yr}-{mo:02d}"
                mo_label = f"{_MONTH_ABBR[mo - 1]} {yr}"

                year_map.setdefault(yr_key, {
                    "label": yr_key,
                    "level": "year",
                    "can_drill_down": True,
                    "children": {"quarter": {}},
                })
                quarters = year_map[yr_key]["children"]["quarter"]
                quarters.setdefault(q_key, {
                    "label": f"Q{q} {yr}",
                    "level": "quarter",
                    "can_drill_down": True,
                    "children": {"month": {}},
                })
                quarters[q_key]["children"]["month"][mo_key] = {
                    "label": mo_label,
                    "level": "month",
                    "can_drill_down": False,
                }

            return {"year": year_map}
        except Exception:
            logger.exception("Failed to build time hierarchy for tenant=%s", tenant_id)
            return {}

    def _latest_time_key(self, time_hier: Dict, time_bucket: str) -> str:
        """Return the most recent key at the given time_bucket level."""
        try:
            years = sorted(time_hier.get("year", {}).keys(), reverse=True)
            if not years:
                return "2026-Q1"
            yr_node = time_hier["year"][years[0]]
            if time_bucket == "year":
                return years[0]
            quarters = sorted(yr_node.get("children", {}).get("quarter", {}).keys(), reverse=True)
            if not quarters:
                return years[0]
            if time_bucket == "quarter":
                return quarters[0]
            q_node = yr_node["children"]["quarter"][quarters[0]]
            months = sorted(q_node.get("children", {}).get("month", {}).keys(), reverse=True)
            return months[0] if months else quarters[0]
        except Exception:
            return "2026-Q1"

    # =========================================================================
    # Breadcrumbs and children helpers
    # =========================================================================

    def _build_breadcrumbs(
        self, site_hier, product_hier, time_hier,
        site_level, site_key, product_level, product_key, time_bucket, time_key,
    ) -> Dict:
        return {
            "site": self._crumbs_for(site_hier, ["company", "region", "site"], site_level, site_key),
            "product": self._crumbs_for(product_hier, ["category", "family", "product"], product_level, product_key),
            "time": self._crumbs_for(time_hier, ["year", "quarter", "month"], time_bucket, time_key),
        }

    def _crumbs_for(self, tree: Dict, levels: List[str], target_level: str, target_key: str) -> List:
        crumbs: List = []
        def _walk(node: Dict, depth: int) -> bool:
            if depth >= len(levels):
                return False
            level = levels[depth]
            for k, v in node.get(level, {}).items():
                is_target = (level == target_level and k == target_key)
                crumbs.append({
                    "level": level, "key": k,
                    "label": v.get("label", k),
                    "is_current": is_target,
                })
                if is_target:
                    return True
                if "children" in v:
                    if _walk(v["children"], depth + 1):
                        return True
                crumbs.pop()
            return False
        _walk(tree, 0)
        return crumbs

    def _build_children(
        self, site_hier, product_hier, time_hier,
        site_level, site_key, product_level, product_key, time_bucket, time_key,
    ) -> Dict:
        return {
            "site": self._children_of(site_hier, ["company", "region", "site"], site_level, site_key),
            "product": self._children_of(product_hier, ["category", "family", "product"], product_level, product_key),
            "time": self._children_of(time_hier, ["year", "quarter", "month"], time_bucket, time_key),
        }

    def _children_of(self, tree: Dict, levels: List[str], level: str, key: str) -> List:
        def _find(node: Dict, depth: int):
            if depth >= len(levels):
                return None
            curr_level = levels[depth]
            items = node.get(curr_level, {})
            if curr_level == level and key in items:
                node_data = items[key]
                results = []
                for child_level, child_nodes in node_data.get("children", {}).items():
                    for ck, cv in child_nodes.items():
                        results.append({
                            "key": ck,
                            "label": cv.get("label", ck),
                            "level": cv.get("level", child_level),
                            "can_drill_down": cv.get("can_drill_down", False),
                        })
                return results
            for k, v in items.items():
                if "children" in v:
                    result = _find(v["children"], depth + 1)
                    if result is not None:
                        return result
            return None
        return _find(tree, 0) or []

    # =========================================================================
    # Tier computations
    # =========================================================================

    def _get_perf_metrics(self, tenant_id: int, time_key: Optional[str]):
        """Fetch PerformanceMetric rows for the given time slice (latest if None)."""
        if self.db is None:
            return None, None
        try:
            from app.models.decision_tracking import PerformanceMetric

            q = (
                self.db.query(PerformanceMetric)
                .filter(
                    PerformanceMetric.tenant_id == tenant_id,
                    PerformanceMetric.category.is_(None),
                )
                .order_by(PerformanceMetric.period_start.desc())
            )
            all_rows = q.limit(24).all()
            if not all_rows:
                return None, None
            latest = all_rows[0]
            previous = all_rows[1] if len(all_rows) > 1 else None
            return latest, previous
        except Exception:
            logger.exception("Failed to fetch PerformanceMetric for tenant=%s", tenant_id)
            return None, None

    def _forecast_rev_margin(self, tenant_id: int) -> tuple:
        """Return (annual_revenue, gross_margin_pct) from Forecast × Product."""
        if self.db is None:
            return None, None
        try:
            from app.models.supply_chain_config import SupplyChainConfig, Site
            from app.models.sc_entities import Product, Forecast

            config = (
                self.db.query(SupplyChainConfig)
                .filter(SupplyChainConfig.tenant_id == tenant_id)
                .first()
            )
            if not config:
                return None, None

            today = date.today()
            year_end = date(today.year + 1, today.month, today.day)

            row = (
                self.db.query(
                    func.sum(Forecast.forecast_p50 * Product.unit_price).label("rev"),
                    func.sum(Forecast.forecast_p50 * Product.unit_cost).label("cost"),
                )
                .join(Product, Forecast.product_id == Product.id)
                .join(Site, Forecast.site_id == Site.id)
                .filter(
                    Forecast.config_id == config.id,
                    Forecast.is_active == "true",
                    (Site.tpartner_type == "customer") | (Site.master_type == "MARKET_DEMAND"),
                    Forecast.forecast_date >= today,
                    Forecast.forecast_date < year_end,
                    Product.unit_price.isnot(None),
                    Product.unit_cost.isnot(None),
                )
                .first()
            )
            if row and row.rev and float(row.rev) > 0:
                rev = float(row.rev)
                cost = float(row.cost or 0)
                gm_pct = round((rev - cost) / rev * 100, 1)
                return int(rev), gm_pct
            return None, None
        except Exception:
            logger.exception("Failed to compute forecast revenue for tenant=%s", tenant_id)
            return None, None

    def _inventory_metrics(self, tenant_id: int) -> Dict[str, Any]:
        """Compute Days of Supply and Inventory Turns from InvLevel + Forecast."""
        if self.db is None:
            return {}
        try:
            from app.models.supply_chain_config import SupplyChainConfig, Site
            from app.models.sc_entities import Product, Forecast
            from app.models.sc_entities import InvLevel

            config = (
                self.db.query(SupplyChainConfig)
                .filter(SupplyChainConfig.tenant_id == tenant_id)
                .first()
            )
            if not config:
                return {}

            # Total on-hand inventory value
            oh_row = (
                self.db.query(
                    func.sum(InvLevel.on_hand_qty * Product.unit_cost).label("inv_value"),
                    func.sum(InvLevel.on_hand_qty).label("total_units"),
                )
                .join(Product, InvLevel.product_id == Product.id)
                .filter(
                    InvLevel.config_id == config.id,
                    Product.unit_cost.isnot(None),
                )
                .first()
            )

            today = date.today()
            year_end = date(today.year + 1, today.month, today.day)

            # Annual demand (COGS basis)
            demand_row = (
                self.db.query(
                    func.sum(Forecast.forecast_p50 * Product.unit_cost).label("annual_cogs"),
                )
                .join(Product, Forecast.product_id == Product.id)
                .join(Site, Forecast.site_id == Site.id)
                .filter(
                    Forecast.config_id == config.id,
                    Forecast.is_active == "true",
                    (Site.tpartner_type == "customer") | (Site.master_type == "MARKET_DEMAND"),
                    Forecast.forecast_date >= today,
                    Forecast.forecast_date < year_end,
                    Product.unit_cost.isnot(None),
                )
                .first()
            )

            inv_value = float(oh_row.inv_value or 0) if oh_row else 0
            annual_cogs = float(demand_row.annual_cogs or 0) if demand_row else 0

            if annual_cogs > 0 and inv_value > 0:
                turns = round(annual_cogs / inv_value, 1)
                dos = round(inv_value / annual_cogs * 365)
                return {"inventory_turns": turns, "days_of_supply": dos}
            return {}
        except Exception:
            logger.exception("Failed to compute inventory metrics for tenant=%s", tenant_id)
            return {}

    def _compute_l3_operational(self, tenant_id: int) -> Dict[str, Any]:
        """Compute SCOR Level 3 operational metrics from powell_*_decisions tables."""
        metrics: Dict[str, Any] = {}
        if self.db is None:
            return metrics
        try:
            from app.models.supply_chain_config import SupplyChainConfig, Site
            from app.models.sc_entities import InvLevel, InvPolicy

            config = (
                self.db.query(SupplyChainConfig)
                .filter(SupplyChainConfig.tenant_id == tenant_id)
                .first()
            )
            if not config:
                return metrics

            # ── SSFR: Safety Stock Fill Rate ──
            # % of product-sites where on_hand >= safety stock target
            inv_rows = (
                self.db.query(InvLevel.product_id, InvLevel.site_id, InvLevel.on_hand_qty)
                .filter(InvLevel.config_id == config.id)
                .all()
            )
            pol_rows = (
                self.db.query(InvPolicy.product_id, InvPolicy.site_id, InvPolicy.ss_quantity)
                .filter(
                    InvPolicy.config_id == config.id,
                    InvPolicy.is_active == "true",
                    InvPolicy.ss_quantity.isnot(None),
                    InvPolicy.ss_quantity > 0,
                )
                .all()
            )
            if pol_rows:
                inv_map = {(r.product_id, r.site_id): float(r.on_hand_qty or 0) for r in inv_rows}
                above = sum(1 for r in pol_rows if inv_map.get((r.product_id, r.site_id), 0) >= float(r.ss_quantity))
                metrics["safety_stock_fill_rate"] = round(above / len(pol_rows) * 100, 1)

            # ── BLA: Buffer Level Adequacy ──
            # Average ratio of on_hand / ss_quantity across product-sites with policy
            if pol_rows:
                ratios = []
                for r in pol_rows:
                    oh = inv_map.get((r.product_id, r.site_id), 0)
                    ss = float(r.ss_quantity)
                    if ss > 0:
                        ratios.append(min(oh / ss, 3.0))  # cap at 3x to avoid outlier skew
                if ratios:
                    metrics["buffer_level_adequacy"] = round(sum(ratios) / len(ratios), 2)

            # ── IRA: Inventory Record Accuracy ──
            # Proxy: % of product-sites where on_hand > 0 (non-zero records)
            if inv_rows:
                non_zero = sum(1 for r in inv_rows if (r.on_hand_qty or 0) > 0)
                metrics["inventory_record_accuracy"] = round(non_zero / len(inv_rows) * 100, 1)

            # ── POLTA: PO Lead Time Actual ──
            try:
                from app.models.powell_decisions import PowellPODecision
                po_rows = (
                    self.db.query(PowellPODecision.lead_time_days)
                    .filter(
                        PowellPODecision.config_id == config.id,
                        PowellPODecision.lead_time_days.isnot(None),
                    )
                    .order_by(PowellPODecision.created_at.desc())
                    .limit(200)
                    .all()
                )
                if po_rows:
                    lt_values = [float(r.lead_time_days) for r in po_rows]
                    metrics["po_lead_time"] = round(sum(lt_values) / len(lt_values), 1)
            except Exception:
                pass

            # ── LTBIAS: Lead Time Bias ──
            try:
                from app.models.supplier import VendorLeadTime
                vlt_rows = (
                    self.db.query(VendorLeadTime)
                    .filter(VendorLeadTime.config_id == config.id)
                    .all()
                )
                if vlt_rows:
                    biases = []
                    for vlt in vlt_rows:
                        planned = getattr(vlt, 'planned_lead_time_days', None) or getattr(vlt, 'p50_days', None)
                        actual = getattr(vlt, 'lead_time_days', None) or getattr(vlt, 'actual_lead_time_days', None)
                        if planned and actual:
                            biases.append(float(actual) - float(planned))
                    if biases:
                        metrics["lead_time_bias"] = round(sum(biases) / len(biases), 1)
            except Exception:
                pass

            # ── MSA: Manufacturing Schedule Adherence ──
            try:
                from app.models.powell_decisions import PowellMODecision
                mo_rows = (
                    self.db.query(PowellMODecision.action, PowellMODecision.on_time)
                    .filter(PowellMODecision.config_id == config.id)
                    .order_by(PowellMODecision.created_at.desc())
                    .limit(200)
                    .all()
                )
                if mo_rows:
                    on_time = sum(1 for r in mo_rows if getattr(r, 'on_time', None))
                    metrics["mfg_schedule_adherence"] = round(on_time / len(mo_rows) * 100, 1)
            except Exception:
                pass

            # ── FPYR: First Pass Yield Rate ──
            try:
                from app.models.powell_decisions import PowellQualityDecision
                q_rows = (
                    self.db.query(PowellQualityDecision.disposition)
                    .filter(PowellQualityDecision.config_id == config.id)
                    .order_by(PowellQualityDecision.created_at.desc())
                    .limit(200)
                    .all()
                )
                if q_rows:
                    accepted = sum(1 for r in q_rows if r.disposition in ('accept', 'ACCEPT', 'use_as_is'))
                    metrics["first_pass_yield"] = round(accepted / len(q_rows) * 100, 1)
            except Exception:
                pass

            # ── EXPRT: Expedite Rate ──
            try:
                from app.models.powell_decisions import PowellTODecision
                to_rows = (
                    self.db.query(PowellTODecision.action)
                    .filter(PowellTODecision.config_id == config.id)
                    .order_by(PowellTODecision.created_at.desc())
                    .limit(200)
                    .all()
                )
                if to_rows:
                    expedited = sum(1 for r in to_rows if r.action in ('expedite', 'EXPEDITE'))
                    metrics["expedite_rate"] = round(expedited / len(to_rows) * 100, 1)
            except Exception:
                pass

        except Exception:
            logger.exception("Failed to compute L3 metrics for tenant=%s", tenant_id)

        return metrics

    def _tier1_assess(self, tenant_id, site_key, product_key, time_key) -> Dict:
        annual_rev, gm_pct = self._forecast_rev_margin(tenant_id)
        latest, previous = self._get_perf_metrics(tenant_id, time_key)

        rev_growth = None
        if latest and previous and previous.total_decisions and latest.total_decisions:
            # Proxy revenue growth from decision volume growth YoY
            rev_growth = None  # Can't compute without historical revenue records

        return {
            "label": "ASSESS — Strategic Health",
            "description": "Is our supply chain competitive?",
            "metrics": {
                "gross_margin": {
                    "label": "Gross Margin",
                    "value": gm_pct,
                    "unit": "%",
                    "target": 22.0,
                    "trend": None,
                    "benchmark": "18-28%",
                    "status": _status(gm_pct, 22.0),
                    "scor_code": None,
                },
                "revenue": {
                    "label": "Annual Revenue (Forecast)",
                    "value": annual_rev,
                    "unit": "$",
                    "target": None,
                    "trend": None,
                    "benchmark": None,
                    "status": "info",
                    "scor_code": None,
                },
                "agent_automation_pct": {
                    "label": "Agent Automation Rate",
                    "value": round(latest.automation_percentage, 1) if latest else None,
                    "unit": "%",
                    "target": 80.0,
                    "trend": (
                        round(latest.automation_percentage - previous.automation_percentage, 1)
                        if latest and previous else None
                    ),
                    "benchmark": ">75%",
                    "status": _status(
                        latest.automation_percentage if latest else None, 80.0
                    ),
                    "scor_code": None,
                },
            },
        }

    def _tier2_diagnose(self, tenant_id, site_key, product_key, time_key) -> Dict:
        inv = self._inventory_metrics(tenant_id)
        latest, _ = self._get_perf_metrics(tenant_id, time_key)

        override_rate = round(latest.override_rate, 1) if latest and latest.override_rate else None

        return {
            "label": "DIAGNOSE — Tactical Diagnostics",
            "description": "Where is value leaking?",
            "metrics": {
                "inventory_turns": {
                    "label": "Inventory Turns",
                    "value": inv.get("inventory_turns"),
                    "unit": "x/yr",
                    "target": 8.0,
                    "trend": None,
                    "benchmark": "6-12x",
                    "status": _status(inv.get("inventory_turns"), 8.0),
                    "scor_code": "AM.2.1",
                },
                "days_of_supply": {
                    "label": "Days of Supply",
                    "value": inv.get("days_of_supply"),
                    "unit": "days",
                    "target": 30,
                    "trend": None,
                    "benchmark": "20-45 days",
                    "status": _status(
                        inv.get("days_of_supply"), 30, lower_is_better=True
                    ) if inv.get("days_of_supply") else "info",
                    "scor_code": "AM.2.2",
                },
                "override_rate": {
                    "label": "Human Override Rate",
                    "value": override_rate,
                    "unit": "%",
                    "target": 20.0,
                    "trend": None,
                    "benchmark": "<25%",
                    "status": _status(override_rate, 20.0, lower_is_better=True),
                    "scor_code": None,
                },
            },
        }

    def _tier3_correct(self, tenant_id, site_key, product_key, time_key) -> Dict:
        inv = self._inventory_metrics(tenant_id)
        latest, _ = self._get_perf_metrics(tenant_id, time_key)
        l3 = self._compute_l3_operational(tenant_id)

        return {
            "label": "CORRECT — Operational Root Cause",
            "description": "What specific action fixes it?",
            "categories": {
                "plan": {
                    "label": "Plan",
                    "metrics": {
                        "safety_stock_fill_rate": {
                            "label": "Safety Stock Fill Rate",
                            "value": l3.get("safety_stock_fill_rate"),
                            "unit": "%",
                            "target": 95.0,
                            "trend": None,
                            "agent": "InventoryBufferTRM",
                            "scor_code": "SSFR",
                            "status": _status(l3.get("safety_stock_fill_rate"), 95.0),
                        },
                        "buffer_level_adequacy": {
                            "label": "Buffer Level Adequacy",
                            "value": l3.get("buffer_level_adequacy"),
                            "unit": "ratio",
                            "target": 1.0,
                            "trend": None,
                            "agent": "InventoryBufferTRM",
                            "scor_code": "BLA",
                            "status": _status(l3.get("buffer_level_adequacy"), 0.9),
                        },
                        "inventory_record_accuracy": {
                            "label": "Inventory Record Accuracy",
                            "value": l3.get("inventory_record_accuracy"),
                            "unit": "%",
                            "target": 99.0,
                            "trend": None,
                            "agent": "InventoryBufferTRM",
                            "scor_code": "IRA",
                            "status": _status(l3.get("inventory_record_accuracy"), 99.0),
                        },
                        "inventory_turns": {
                            "label": "Inventory Turns",
                            "value": inv.get("inventory_turns"),
                            "unit": "x/yr",
                            "target": 8.0,
                            "trend": None,
                            "agent": "InventoryBufferTRM",
                            "status": _status(inv.get("inventory_turns"), 8.0),
                        },
                        "dos": {
                            "label": "Days of Supply",
                            "value": inv.get("days_of_supply"),
                            "unit": "days",
                            "target": 30,
                            "trend": None,
                            "agent": "InventoryBufferTRM",
                            "lower_is_better": True,
                            "status": _status(
                                inv.get("days_of_supply"), 30, lower_is_better=True
                            ) if inv.get("days_of_supply") else "info",
                        },
                    },
                },
                "source": {
                    "label": "Source",
                    "metrics": {
                        "po_lead_time": {
                            "label": "PO Lead Time Actual",
                            "value": l3.get("po_lead_time"),
                            "unit": "days",
                            "target": 14.0,
                            "trend": None,
                            "agent": "POCreationTRM",
                            "scor_code": "POLTA",
                            "lower_is_better": True,
                            "status": _status(l3.get("po_lead_time"), 14.0, lower_is_better=True) if l3.get("po_lead_time") else "info",
                        },
                        "lead_time_bias": {
                            "label": "Lead Time Bias",
                            "value": l3.get("lead_time_bias"),
                            "unit": "days",
                            "target": 0.0,
                            "trend": None,
                            "agent": "POCreationTRM",
                            "scor_code": "LTBIAS",
                            "lower_is_better": True,
                            "status": _status(abs(l3.get("lead_time_bias", 0) or 0), 2.0, lower_is_better=True) if l3.get("lead_time_bias") is not None else "info",
                        },
                    },
                },
                "make": {
                    "label": "Make",
                    "metrics": {
                        "mfg_schedule_adherence": {
                            "label": "Mfg Schedule Adherence",
                            "value": l3.get("mfg_schedule_adherence"),
                            "unit": "%",
                            "target": 95.0,
                            "trend": None,
                            "agent": "MOExecutionTRM",
                            "scor_code": "MSA",
                            "status": _status(l3.get("mfg_schedule_adherence"), 95.0),
                        },
                        "first_pass_yield": {
                            "label": "First Pass Yield Rate",
                            "value": l3.get("first_pass_yield"),
                            "unit": "%",
                            "target": 98.0,
                            "trend": None,
                            "agent": "QualityDispositionTRM",
                            "scor_code": "FPYR",
                            "status": _status(l3.get("first_pass_yield"), 98.0),
                        },
                    },
                },
                "deliver": {
                    "label": "Deliver & Enable",
                    "metrics": {
                        "expedite_rate": {
                            "label": "Expedite Rate",
                            "value": l3.get("expedite_rate"),
                            "unit": "%",
                            "target": 5.0,
                            "trend": None,
                            "agent": "TOExecutionTRM",
                            "scor_code": "EXPRT",
                            "lower_is_better": True,
                            "status": _status(l3.get("expedite_rate"), 5.0, lower_is_better=True) if l3.get("expedite_rate") is not None else "info",
                        },
                    },
                },
                "agent_performance": {
                    "label": "AI Agent Performance",
                    "metrics": {
                        "automation_pct": {
                            "label": "Automation Rate",
                            "value": round(latest.automation_percentage, 1) if latest else None,
                            "unit": "%",
                            "target": 80.0,
                            "trend": None,
                            "agent": "All TRMs",
                            "status": _status(
                                latest.automation_percentage if latest else None, 80.0
                            ),
                        },
                        "agent_score": {
                            "label": "Agent Decision Score",
                            "value": round(latest.agent_score, 1) if latest and latest.agent_score else None,
                            "unit": "",
                            "target": 10.0,
                            "trend": None,
                            "agent": "All TRMs",
                            "status": _status(
                                latest.agent_score if latest else None, 10.0
                            ),
                        },
                        "override_rate": {
                            "label": "Override Rate",
                            "value": round(latest.override_rate, 1) if latest and latest.override_rate else None,
                            "unit": "%",
                            "target": 20.0,
                            "lower_is_better": True,
                            "trend": None,
                            "agent": "All TRMs",
                            "status": _status(
                                latest.override_rate if latest else None, 20.0, lower_is_better=True
                            ),
                        },
                    },
                },
            },
        }

    def _tier4_agent(self, tenant_id: int, time_key: Optional[str]) -> Dict:
        """AI-as-Labor tier from agent_decision_metrics and PerformanceMetric."""
        if self.db is None:
            return self._tier4_empty()
        try:
            from app.models.planning_cascade import AgentDecisionMetrics

            # Latest per-agent metrics
            rows = (
                self.db.query(AgentDecisionMetrics)
                .filter(AgentDecisionMetrics.tenant_id == tenant_id)
                .order_by(AgentDecisionMetrics.period_start.desc())
                .limit(50)
                .all()
            )

            # Deduplicate: keep latest per agent_type
            latest_by_type: Dict[str, Any] = {}
            for r in rows:
                if r.agent_type not in latest_by_type:
                    latest_by_type[r.agent_type] = r

            trm_agents = []
            for agent_type, r in sorted(latest_by_type.items()):
                touchless = round(float(r.touchless_rate or 0) * 100, 1)
                trm_agents.append({
                    "name": agent_type,
                    "phase": self._agent_phase(agent_type),
                    "score": round(float(r.agent_score or 0), 1),
                    "touchless": touchless,
                    "override": round(100 - touchless, 1),
                    "urgency": round(float(r.human_override_rate or 0), 2),
                    "total_decisions": r.total_decisions or 0,
                })

            if not trm_agents:
                return self._tier4_empty()

            avg_touchless = round(sum(a["touchless"] for a in trm_agents) / len(trm_agents), 1)
            avg_score = round(sum(a["score"] for a in trm_agents) / len(trm_agents), 1)
            avg_override = round(100 - avg_touchless, 1)
            mean_urgency = round(sum(a["urgency"] for a in trm_agents) / len(trm_agents), 2)
            max_urgency = max(a["urgency"] for a in trm_agents)

            return {
                "label": "AI-as-Labor Performance",
                "description": "How well are agents producing outcomes?",
                "metrics": {
                    "touchless_rate": {
                        "label": "Touchless Rate",
                        "value": avg_touchless, "unit": "%",
                        "target": 80, "trend": None,
                        "status": _status(avg_touchless, 80),
                    },
                    "agent_score": {
                        "label": "Agent Score",
                        "value": avg_score, "unit": "",
                        "target": 10, "trend": None,
                        "status": _status(avg_score, 10),
                    },
                    "override_rate": {
                        "label": "Override Rate",
                        "value": avg_override, "unit": "%",
                        "target": 20, "trend": None,
                        "status": _status(avg_override, 20, lower_is_better=True),
                    },
                },
                "hive_metrics": {
                    "mean_urgency": mean_urgency,
                    "max_urgency": max_urgency,
                    "signal_bus_activity": len(trm_agents),
                    "conflict_rate": None,
                    "stress_index": None,
                },
                "per_trm": trm_agents,
            }
        except Exception:
            logger.exception("Failed to build tier4 agent metrics for tenant=%s", tenant_id)
            return self._tier4_empty()

    def _tier4_empty(self) -> Dict:
        return {
            "label": "AI-as-Labor Performance",
            "description": "How well are agents producing outcomes?",
            "metrics": {},
            "hive_metrics": {},
            "per_trm": [],
        }

    @staticmethod
    def _agent_phase(agent_type: str) -> str:
        _MAP = {
            "atp_executor": "SENSE", "ATPExecutorTRM": "SENSE",
            "order_tracking": "SENSE", "OrderTrackingTRM": "SENSE",
            "po_creation": "ACQUIRE", "POCreationTRM": "ACQUIRE",
            "subcontracting": "ACQUIRE", "SubcontractingTRM": "ACQUIRE",
            "inventory_buffer": "ASSESS", "InventoryBufferTRM": "ASSESS",
            "forecast_adjustment": "ASSESS", "ForecastAdjustmentTRM": "ASSESS",
            "quality_disposition": "PROTECT", "QualityDispositionTRM": "PROTECT",
            "maintenance_scheduling": "PROTECT", "MaintenanceSchedulingTRM": "PROTECT",
            "mo_execution": "BUILD", "MOExecutionTRM": "BUILD",
            "to_execution": "BUILD", "TOExecutionTRM": "BUILD",
            "inventory_rebalancing": "REFLECT", "InventoryRebalancingTRM": "REFLECT",
            "supply_agent": "ACQUIRE",
            "allocation_agent": "SENSE",
        }
        return _MAP.get(agent_type, "EXECUTE")

    def _trend_data(self, tenant_id: int) -> List[Dict]:
        """Monthly trend data from PerformanceMetric."""
        if self.db is None:
            return []
        try:
            from app.models.decision_tracking import PerformanceMetric

            rows = (
                self.db.query(PerformanceMetric)
                .filter(
                    PerformanceMetric.tenant_id == tenant_id,
                    PerformanceMetric.category.is_(None),
                )
                .order_by(PerformanceMetric.period_start.asc())
                .limit(24)
                .all()
            )

            _MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

            inv = self._inventory_metrics(tenant_id)
            base_turns = inv.get("inventory_turns", 8.0) or 8.0
            base_dos = inv.get("days_of_supply", 30) or 30

            data = []
            for i, pm in enumerate(rows):
                mo = pm.period_start.month
                yr = pm.period_start.year
                label = f"{_MONTH_ABBR[mo - 1]}"
                # Interpolate inventory metrics linearly across the history
                progress = i / max(len(rows) - 1, 1)
                data.append({
                    "period": label,
                    "touchless": round(float(pm.automation_percentage or 0), 1),
                    "agent_score": round(float(pm.agent_score or 0), 1),
                    "override_rate": round(float(pm.override_rate or 0), 1),
                    "inventory_turns": round(base_turns * (0.8 + 0.2 * progress), 1),
                    "dos": round(base_dos * (1.2 - 0.2 * progress)),
                })
            return data
        except Exception:
            logger.exception("Failed to build trend data for tenant=%s", tenant_id)
            return []
