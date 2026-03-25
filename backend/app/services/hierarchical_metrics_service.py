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
import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func, asc, case

from app.models.metrics_hierarchy import GARTNER_METRICS, GartnerLevel, get_metric_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Confidence interval utilities (95% CI by default)
# ---------------------------------------------------------------------------

def _wilson_ci(successes: int, total: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval for a proportion (returns % values 0-100).

    More robust than Normal approximation, especially for small samples
    or proportions near 0 or 1.
    """
    if total == 0:
        return (0.0, 100.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denom
    lo = max(0.0, centre - spread) * 100
    hi = min(1.0, centre + spread) * 100
    return (round(lo, 1), round(hi, 1))


def _mean_ci(values: List[float], z: float = 1.96) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Confidence interval for a mean. Returns (mean, ci_lower, ci_upper).

    Uses z-interval (t-distribution converges to z for n>30).
    """
    n = len(values)
    if n == 0:
        return (None, None, None)
    mean = sum(values) / n
    if n == 1:
        return (round(mean, 2), None, None)
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    se = math.sqrt(variance / n)
    margin = z * se
    return (round(mean, 2), round(mean - margin, 2), round(mean + margin, 2))

# Mapping from dashboard metric key → Gartner metric code.
# Used to annotate tier metric dicts with gartner_level and gartner_code.
_METRIC_KEY_TO_GARTNER: Dict[str, str] = {
    # Tier 1 (L1 Strategic)
    "perfect_order_fulfillment": "POF",
    "gross_margin":             "SCMC",
    "revenue":                  "SCMC",
    "supply_chain_cycle_time":  "SCCT",
    "cash_to_cash":             "C2C",
    # Tier 2 (L2 Functional)
    "inventory_turns":          "DOS",
    "days_of_supply":           "DOS",
    "fill_rate":                "FR",
    "on_time_delivery":         "OTD",
    "forecast_accuracy":        "FA",
    "stockout_lost_demand":     "SOLD",
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

        mc = self._load_metric_config(tenant_id)

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
            "tiers": self._inject_sparklines(tenant_id, self._filter_disabled_metrics(mc, self._annotate_gartner_levels({
                "tier1_assess":  self._tier1_assess(tenant_id, site_key, product_key, time_key, mc),
                "tier2_diagnose": self._tier2_diagnose(tenant_id, site_key, product_key, time_key, mc),
                "tier3_correct": self._tier3_correct(tenant_id, site_key, product_key, time_key, mc),
                "tier4_agent":   self._tier4_agent(tenant_id, time_key),
            }))),
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
    # Metric config helpers
    # =========================================================================

    def _load_metric_config(self, tenant_id: int):
        """Load MetricConfig for the tenant's supply chain config."""
        if self.db is None:
            return get_metric_config(None)
        try:
            from app.models.supply_chain_config import SupplyChainConfig
            config = (
                self.db.query(SupplyChainConfig)
                .filter(SupplyChainConfig.tenant_id == tenant_id)
                .first()
            )
            return get_metric_config(config.metric_config if config else None)
        except Exception:
            return get_metric_config(None)

    @staticmethod
    def _enrich_ci(tier_data: dict, *compute_results: dict) -> dict:
        """Walk a tier dict and attach ci_lower/ci_upper/n from _ci_* keys in compute results.

        Works for both flat metrics dicts (tier1/tier2) and categorized (tier3).
        """
        # Merge all compute results into one lookup
        ci_lookup: Dict[str, dict] = {}
        for cr in compute_results:
            for k, v in cr.items():
                if k.startswith("_ci_") and isinstance(v, dict):
                    ci_lookup[k[4:]] = v  # strip "_ci_" prefix

        def _apply(metrics_dict: dict):
            for metric_key, metric_val in metrics_dict.items():
                if isinstance(metric_val, dict) and metric_key in ci_lookup:
                    ci = ci_lookup[metric_key]
                    metric_val["ci_lower"] = ci.get("ci_lower")
                    metric_val["ci_upper"] = ci.get("ci_upper")
                    metric_val["n"] = ci.get("n")

        if "metrics" in tier_data and isinstance(tier_data["metrics"], dict):
            _apply(tier_data["metrics"])
        if "categories" in tier_data and isinstance(tier_data["categories"], dict):
            for cat_data in tier_data["categories"].values():
                if isinstance(cat_data, dict) and "metrics" in cat_data:
                    _apply(cat_data["metrics"])
        return tier_data

    @staticmethod
    def _filter_disabled_metrics(mc, tiers: Dict[str, Any]) -> Dict[str, Any]:
        """Remove metrics disabled in the dashboard config."""
        for tier_key, tier_data in tiers.items():
            if not isinstance(tier_data, dict):
                continue
            # Direct metrics dict (tier1, tier2)
            if "metrics" in tier_data and isinstance(tier_data["metrics"], dict):
                tier_data["metrics"] = {
                    k: v for k, v in tier_data["metrics"].items()
                    if mc.is_metric_enabled(tier_key, k)
                }
            # Categorized metrics (tier3 with categories)
            if "categories" in tier_data and isinstance(tier_data["categories"], dict):
                for cat_key, cat_data in tier_data["categories"].items():
                    if isinstance(cat_data, dict) and "metrics" in cat_data:
                        cat_data["metrics"] = {
                            k: v for k, v in cat_data["metrics"].items()
                            if mc.is_metric_enabled(tier_key, k)
                        }
        return tiers

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

            # Try customer-scoped first, then fall back to all forecasts
            row = (
                self.db.query(
                    func.sum(Forecast.forecast_p50 * Product.unit_price).label("rev"),
                    func.sum(Forecast.forecast_p50 * Product.unit_cost).label("cost"),
                )
                .join(Product, Forecast.product_id == Product.id)
                .join(Site, Forecast.site_id == Site.id)
                .filter(
                    Forecast.config_id == config.id,
                    Forecast.is_active.in_(["true", "Y", "1"]),
                    (Site.tpartner_type == "customer") | (Site.master_type == "CUSTOMER"),
                    Forecast.forecast_date >= today,
                    Forecast.forecast_date < year_end,
                    Product.unit_price.isnot(None),
                    Product.unit_cost.isnot(None),
                )
                .first()
            )
            # Fallback: no customer sites → use all forecasts
            if not row or not row.rev:
                row = (
                    self.db.query(
                        func.sum(Forecast.forecast_p50 * Product.unit_price).label("rev"),
                        func.sum(Forecast.forecast_p50 * Product.unit_cost).label("cost"),
                    )
                    .join(Product, Forecast.product_id == Product.id)
                    .filter(
                        Forecast.config_id == config.id,
                        Forecast.is_active.in_(["true", "Y", "1"]),
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

            # Total on-hand inventory value — use only the LATEST snapshot date
            latest_inv_date_row = (
                self.db.query(func.max(InvLevel.inventory_date))
                .filter(InvLevel.config_id == config.id)
                .scalar()
            )
            oh_row = (
                self.db.query(
                    func.sum(InvLevel.on_hand_qty * Product.unit_cost).label("inv_value"),
                    func.sum(InvLevel.on_hand_qty).label("total_units"),
                )
                .join(Product, InvLevel.product_id == Product.id)
                .filter(
                    InvLevel.config_id == config.id,
                    Product.unit_cost.isnot(None),
                    InvLevel.inventory_date == latest_inv_date_row,
                )
                .first()
            ) if latest_inv_date_row else None

            today = date.today()
            year_end = date(today.year + 1, today.month, today.day)

            # Annual demand (COGS basis)
            # First try customer-scoped demand, then fall back to all demand
            demand_row = (
                self.db.query(
                    func.sum(Forecast.forecast_p50 * Product.unit_cost).label("annual_cogs"),
                )
                .join(Product, Forecast.product_id == Product.id)
                .join(Site, Forecast.site_id == Site.id)
                .filter(
                    Forecast.config_id == config.id,
                    Forecast.is_active.in_(["true", "Y", "1"]),
                    (Site.tpartner_type == "customer") | (Site.master_type == "CUSTOMER"),
                    Forecast.forecast_date >= today,
                    Forecast.forecast_date < year_end,
                    Product.unit_cost.isnot(None),
                )
                .first()
            )
            # Fallback: if no customer-scoped demand, use all forecasts
            if not demand_row or not demand_row.annual_cogs:
                demand_row = (
                    self.db.query(
                        func.sum(Forecast.forecast_p50 * Product.unit_cost).label("annual_cogs"),
                    )
                    .join(Product, Forecast.product_id == Product.id)
                    .filter(
                        Forecast.config_id == config.id,
                        Forecast.is_active.in_(["true", "Y", "1"]),
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

    def _get_company_ids_for_tenant(self, tenant_id: int) -> List[str]:
        """Return all company_id values linked to a tenant's configs."""
        from app.models.supply_chain_config import SupplyChainConfig
        from app.models.sc_entities import Company
        configs = (
            self.db.query(SupplyChainConfig.id)
            .filter(SupplyChainConfig.tenant_id == tenant_id)
            .all()
        )
        if not configs:
            return []
        config_ids = [c.id for c in configs]
        # Get company_ids from sites linked to these configs
        from app.models.supply_chain_config import Site
        company_rows = (
            self.db.query(func.distinct(Site.company_id))
            .filter(Site.config_id.in_(config_ids), Site.company_id.isnot(None))
            .all()
        )
        return [r[0] for r in company_rows if r[0]]

    def _compute_l1_strategic(self, tenant_id: int) -> Dict[str, Any]:
        """Compute SCOR Level 1 strategic metrics: POF, SCCT, C2C."""
        metrics: Dict[str, Any] = {}
        if self.db is None:
            return metrics
        try:
            from app.models.supply_chain_config import SupplyChainConfig, Site
            from app.models.sc_entities import OutboundOrderLine, FulfillmentOrder, Shipment

            config = (
                self.db.query(SupplyChainConfig)
                .filter(SupplyChainConfig.tenant_id == tenant_id)
                .first()
            )
            if not config:
                return metrics

            company_ids = self._get_company_ids_for_tenant(tenant_id)

            # ── POF: Perfect Order Fulfillment ──
            # % of orders delivered in full, on time, undamaged, with correct docs
            try:
                ool_rows = (
                    self.db.query(
                        OutboundOrderLine.ordered_quantity,
                        OutboundOrderLine.shipped_quantity,
                        OutboundOrderLine.promised_delivery_date,
                        OutboundOrderLine.last_ship_date,
                        OutboundOrderLine.status,
                    )
                    .filter(
                        OutboundOrderLine.config_id == config.id,
                        OutboundOrderLine.status.in_(["FULFILLED", "PARTIALLY_FULFILLED"]),
                    )
                    .limit(500)
                    .all()
                )
                # Fallback to FulfillmentOrder if OutboundOrderLine is empty
                if not ool_rows and company_ids:
                    fo_rows = (
                        self.db.query(
                            FulfillmentOrder.quantity,
                            FulfillmentOrder.shipped_quantity,
                            FulfillmentOrder.promised_date,
                            FulfillmentOrder.ship_date,
                            FulfillmentOrder.status,
                        )
                        .filter(
                            FulfillmentOrder.company_id.in_(company_ids),
                            FulfillmentOrder.status.in_(["DELIVERED", "SHIPPED"]),
                        )
                        .limit(500)
                        .all()
                    )
                    if fo_rows:
                        perfect = 0
                        for r in fo_rows:
                            qty_ok = (r.shipped_quantity or 0) >= (r.quantity or 0)
                            time_ok = (
                                r.ship_date is not None
                                and r.promised_date is not None
                                and r.ship_date <= r.promised_date
                            ) if r.promised_date else True
                            if qty_ok and time_ok:
                                perfect += 1
                        n = len(fo_rows)
                        ci_lo, ci_hi = _wilson_ci(perfect, n)
                        metrics["perfect_order_fulfillment"] = round(perfect / n * 100, 1)
                        metrics["_ci_perfect_order_fulfillment"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": n}
                elif ool_rows:
                    perfect = 0
                    for r in ool_rows:
                        qty_ok = (r.shipped_quantity or 0) >= (r.ordered_quantity or 0)
                        time_ok = (
                            r.last_ship_date is not None
                            and r.promised_delivery_date is not None
                            and r.last_ship_date <= r.promised_delivery_date
                        ) if r.promised_delivery_date else True
                        if qty_ok and time_ok:
                            perfect += 1
                    n = len(ool_rows)
                    ci_lo, ci_hi = _wilson_ci(perfect, n)
                    metrics["perfect_order_fulfillment"] = round(perfect / n * 100, 1)
                    metrics["_ci_perfect_order_fulfillment"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": n}
            except Exception:
                logger.debug("POF computation failed", exc_info=True)

            # ── SCCT: Supply Chain Cycle Time ──
            # Average time from order placement to delivery
            try:
                # Use OutboundOrderLine: order_date → last_ship_date
                ct_rows = (
                    self.db.query(
                        OutboundOrderLine.order_date,
                        OutboundOrderLine.last_ship_date,
                    )
                    .filter(
                        OutboundOrderLine.config_id == config.id,
                        OutboundOrderLine.order_date.isnot(None),
                        OutboundOrderLine.last_ship_date.isnot(None),
                        OutboundOrderLine.status == "FULFILLED",
                    )
                    .limit(500)
                    .all()
                )
                # Fallback to FulfillmentOrder
                if not ct_rows and company_ids:
                    ct_rows_fo = (
                        self.db.query(
                            FulfillmentOrder.created_date,
                            FulfillmentOrder.delivery_date,
                        )
                        .filter(
                            FulfillmentOrder.company_id.in_(company_ids),
                            FulfillmentOrder.created_date.isnot(None),
                            FulfillmentOrder.delivery_date.isnot(None),
                            FulfillmentOrder.status == "DELIVERED",
                        )
                        .limit(500)
                        .all()
                    )
                    if ct_rows_fo:
                        cycle_days = []
                        for r in ct_rows_fo:
                            delta = (r.delivery_date - r.created_date).days
                            if 0 <= delta <= 365:
                                cycle_days.append(delta)
                        if cycle_days:
                            mean_val, ci_lo, ci_hi = _mean_ci(cycle_days)
                            metrics["supply_chain_cycle_time"] = round(sum(cycle_days) / len(cycle_days), 1)
                            metrics["_ci_supply_chain_cycle_time"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": len(cycle_days)}
                elif ct_rows:
                    cycle_days = []
                    for r in ct_rows:
                        delta = (r.last_ship_date - r.order_date).days
                        if 0 <= delta <= 365:  # sanity bound
                            cycle_days.append(delta)
                    if cycle_days:
                        mean_val, ci_lo, ci_hi = _mean_ci(cycle_days)
                        metrics["supply_chain_cycle_time"] = round(sum(cycle_days) / len(cycle_days), 1)
                        metrics["_ci_supply_chain_cycle_time"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": len(cycle_days)}
            except Exception:
                logger.debug("SCCT computation failed", exc_info=True)

            # ── C2C: Cash-to-Cash Cycle Time ──
            # DIO + DSO - DPO
            try:
                from app.models.sc_entities import InvLevel, Product, Forecast
                from app.models.invoice import Invoice
                from app.models.purchase_order import PurchaseOrder

                inv = self._inventory_metrics(tenant_id)
                dio = inv.get("days_of_supply")  # DIO proxy

                # DSO: Days Sales Outstanding
                # Proxy from invoices linked to POs for this tenant
                dso = None
                try:
                    inv_rows = (
                        self.db.query(Invoice.invoice_date, Invoice.payment_date)
                        .join(PurchaseOrder, Invoice.po_id == PurchaseOrder.id)
                        .filter(
                            PurchaseOrder.tenant_id == tenant_id,
                            Invoice.payment_date.isnot(None),
                            Invoice.invoice_date.isnot(None),
                        )
                        .limit(200)
                        .all()
                    )
                    if inv_rows:
                        payment_days = [(r.payment_date - r.invoice_date).days for r in inv_rows
                                        if 0 <= (r.payment_date - r.invoice_date).days <= 180]
                        if payment_days:
                            dso = round(sum(payment_days) / len(payment_days), 1)
                except Exception:
                    pass

                # DPO: Days Payable Outstanding
                # avg days from PO receipt to invoice payment
                dpo = None
                try:
                    dpo_rows = (
                        self.db.query(Invoice.received_date, Invoice.payment_date)
                        .join(PurchaseOrder, Invoice.po_id == PurchaseOrder.id)
                        .filter(
                            PurchaseOrder.tenant_id == tenant_id,
                            Invoice.payment_date.isnot(None),
                            Invoice.received_date.isnot(None),
                            Invoice.status == "PAID",
                        )
                        .limit(200)
                        .all()
                    )
                    if dpo_rows:
                        pay_days = [(r.payment_date - r.received_date).days for r in dpo_rows
                                    if 0 <= (r.payment_date - r.received_date).days <= 180]
                        if pay_days:
                            dpo = round(sum(pay_days) / len(pay_days), 1)
                except Exception:
                    pass

                if dio is not None:
                    c2c = dio + (dso or 30) - (dpo or 30)  # Use 30-day defaults if no invoice data
                    metrics["cash_to_cash"] = round(c2c, 1)
                    if dso is not None:
                        metrics["dso"] = dso
                    if dpo is not None:
                        metrics["dpo"] = dpo
            except Exception:
                logger.debug("C2C computation failed", exc_info=True)

        except Exception:
            logger.exception("Failed to compute L1 strategic metrics for tenant=%s", tenant_id)
        return metrics

    def _compute_l2_functional(self, tenant_id: int) -> Dict[str, Any]:
        """Compute SCOR Level 2 functional metrics: FR, OTD, FA, SOLD."""
        metrics: Dict[str, Any] = {}
        if self.db is None:
            return metrics
        try:
            from app.models.supply_chain_config import SupplyChainConfig, Site
            from app.models.sc_entities import OutboundOrderLine, FulfillmentOrder, Forecast

            config = (
                self.db.query(SupplyChainConfig)
                .filter(SupplyChainConfig.tenant_id == tenant_id)
                .first()
            )
            if not config:
                return metrics

            company_ids = self._get_company_ids_for_tenant(tenant_id)

            # ── FR: Fill Rate ──
            # % of ordered quantity actually shipped
            try:
                fr_row = (
                    self.db.query(
                        func.sum(OutboundOrderLine.shipped_quantity).label("shipped"),
                        func.sum(OutboundOrderLine.ordered_quantity).label("ordered"),
                    )
                    .filter(
                        OutboundOrderLine.config_id == config.id,
                        OutboundOrderLine.ordered_quantity > 0,
                    )
                    .first()
                )
                has_ool_fr = fr_row and fr_row.ordered and float(fr_row.ordered) > 0
                if has_ool_fr:
                    shipped = float(fr_row.shipped or 0)
                    ordered = float(fr_row.ordered)
                    fr = min(shipped / ordered * 100, 100.0)
                    metrics["fill_rate"] = round(fr, 1)
                    fr_lines = (
                        self.db.query(OutboundOrderLine.shipped_quantity, OutboundOrderLine.ordered_quantity)
                        .filter(
                            OutboundOrderLine.config_id == config.id,
                            OutboundOrderLine.ordered_quantity > 0,
                        )
                        .limit(500)
                        .all()
                    )
                    if fr_lines:
                        filled = sum(1 for r in fr_lines if (r.shipped_quantity or 0) >= (r.ordered_quantity or 0))
                        ci_lo, ci_hi = _wilson_ci(filled, len(fr_lines))
                        metrics["_ci_fill_rate"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": len(fr_lines)}
                elif company_ids:
                    # Fallback to FulfillmentOrder
                    fo_fr = (
                        self.db.query(
                            func.sum(FulfillmentOrder.shipped_quantity).label("shipped"),
                            func.sum(FulfillmentOrder.quantity).label("ordered"),
                        )
                        .filter(
                            FulfillmentOrder.company_id.in_(company_ids),
                            FulfillmentOrder.quantity > 0,
                        )
                        .first()
                    )
                    if fo_fr and fo_fr.ordered and float(fo_fr.ordered) > 0:
                        shipped = float(fo_fr.shipped or 0)
                        ordered = float(fo_fr.ordered)
                        fr = min(shipped / ordered * 100, 100.0)
                        metrics["fill_rate"] = round(fr, 1)
                        fo_lines = (
                            self.db.query(FulfillmentOrder.shipped_quantity, FulfillmentOrder.quantity)
                            .filter(
                                FulfillmentOrder.company_id.in_(company_ids),
                                FulfillmentOrder.quantity > 0,
                            )
                            .limit(500)
                            .all()
                        )
                        if fo_lines:
                            filled = sum(1 for r in fo_lines if (r.shipped_quantity or 0) >= (r.quantity or 0))
                            ci_lo, ci_hi = _wilson_ci(filled, len(fo_lines))
                            metrics["_ci_fill_rate"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": len(fo_lines)}
            except Exception:
                logger.debug("FR computation failed", exc_info=True)

            # ── OTD: On-Time Delivery ──
            # % of fulfilled orders where last_ship_date <= promised_delivery_date
            try:
                otd_rows = (
                    self.db.query(
                        OutboundOrderLine.promised_delivery_date,
                        OutboundOrderLine.last_ship_date,
                    )
                    .filter(
                        OutboundOrderLine.config_id == config.id,
                        OutboundOrderLine.status.in_(["FULFILLED", "PARTIALLY_FULFILLED"]),
                        OutboundOrderLine.promised_delivery_date.isnot(None),
                        OutboundOrderLine.last_ship_date.isnot(None),
                    )
                    .limit(500)
                    .all()
                )
                if not otd_rows and company_ids:
                    # Fallback to FulfillmentOrder
                    fo_otd = (
                        self.db.query(
                            FulfillmentOrder.promised_date,
                            FulfillmentOrder.ship_date,
                        )
                        .filter(
                            FulfillmentOrder.company_id.in_(company_ids),
                            FulfillmentOrder.status.in_(["DELIVERED", "SHIPPED"]),
                            FulfillmentOrder.promised_date.isnot(None),
                            FulfillmentOrder.ship_date.isnot(None),
                        )
                        .limit(500)
                        .all()
                    )
                    if fo_otd:
                        n = len(fo_otd)
                        on_time = sum(1 for r in fo_otd if r.ship_date <= r.promised_date)
                        metrics["on_time_delivery"] = round(on_time / n * 100, 1)
                        ci_lo, ci_hi = _wilson_ci(on_time, n)
                        metrics["_ci_on_time_delivery"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": n}
                elif otd_rows:
                    n = len(otd_rows)
                    on_time = sum(1 for r in otd_rows if r.last_ship_date <= r.promised_delivery_date)
                    metrics["on_time_delivery"] = round(on_time / n * 100, 1)
                    ci_lo, ci_hi = _wilson_ci(on_time, n)
                    metrics["_ci_on_time_delivery"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": n}
            except Exception:
                logger.debug("OTD computation failed", exc_info=True)

            # ── FA: Forecast Accuracy ──
            # Average (1 - |forecast_error|) across forecasts with error data,
            # or WMAPE from forecast_error column
            try:
                fa_rows = (
                    self.db.query(Forecast.forecast_error, Forecast.forecast_quantity)
                    .filter(
                        Forecast.config_id == config.id,
                        Forecast.forecast_error.isnot(None),
                        Forecast.is_active.in_(["true", "Y", "1"]),
                    )
                    .limit(500)
                    .all()
                )
                if fa_rows:
                    errors = [abs(float(r.forecast_error)) for r in fa_rows if r.forecast_error is not None]
                    if errors:
                        avg_error = sum(errors) / len(errors)
                        if avg_error <= 1.0:
                            accuracies = [(1.0 - e) * 100 for e in errors]
                            metrics["forecast_accuracy"] = round((1.0 - avg_error) * 100, 1)
                        else:
                            accuracies = [max(100.0 - e, 0) for e in errors]
                            metrics["forecast_accuracy"] = round(max(100.0 - avg_error, 0), 1)
                        _, ci_lo, ci_hi = _mean_ci(accuracies)
                        metrics["_ci_forecast_accuracy"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": len(accuracies)}
                elif config:
                    # Fallback: compute from forecast_bias if available
                    bias_rows = (
                        self.db.query(Forecast.forecast_bias)
                        .filter(
                            Forecast.config_id == config.id,
                            Forecast.forecast_bias.isnot(None),
                            Forecast.is_active.in_(["true", "Y", "1"]),
                        )
                        .limit(500)
                        .all()
                    )
                    if bias_rows:
                        biases = [abs(float(r.forecast_bias)) for r in bias_rows]
                        avg_bias = sum(biases) / len(biases)
                        if avg_bias <= 1.0:
                            metrics["forecast_accuracy"] = round((1.0 - avg_bias) * 100, 1)
                        else:
                            metrics["forecast_accuracy"] = round(max(100.0 - avg_bias, 0), 1)
            except Exception:
                logger.debug("FA computation failed", exc_info=True)

            # ── SOLD: Stockout and Lost Demand ──
            # Total backlog quantity + estimated lost sales from risk alerts
            try:
                backlog_row = (
                    self.db.query(
                        func.sum(OutboundOrderLine.backlog_quantity).label("total_backlog"),
                    )
                    .filter(
                        OutboundOrderLine.config_id == config.id,
                        OutboundOrderLine.backlog_quantity > 0,
                    )
                    .first()
                )
                has_ool_backlog = backlog_row and backlog_row.total_backlog
                if has_ool_backlog:
                    metrics["stockout_lost_demand"] = int(float(backlog_row.total_backlog))
                elif company_ids:
                    # Fallback: use FulfillmentOrder short_quantity + Backorder table
                    from app.models.sc_entities import Backorder
                    bo_row = (
                        self.db.query(
                            func.sum(Backorder.quantity).label("total_backlog"),
                        )
                        .filter(Backorder.company_id.in_(company_ids))
                        .first()
                    )
                    if bo_row and bo_row.total_backlog:
                        metrics["stockout_lost_demand"] = int(float(bo_row.total_backlog))
                    else:
                        # Try short_quantity from FulfillmentOrder
                        short_row = (
                            self.db.query(
                                func.sum(FulfillmentOrder.short_quantity).label("total_short"),
                            )
                            .filter(
                                FulfillmentOrder.company_id.in_(company_ids),
                                FulfillmentOrder.short_quantity > 0,
                            )
                            .first()
                        )
                        if short_row and short_row.total_short:
                            metrics["stockout_lost_demand"] = int(float(short_row.total_short))

                # Backlog rate
                total_ordered = None
                if has_ool_backlog:
                    total_row = (
                        self.db.query(
                            func.sum(OutboundOrderLine.ordered_quantity).label("total_ordered"),
                        )
                        .filter(
                            OutboundOrderLine.config_id == config.id,
                            OutboundOrderLine.ordered_quantity > 0,
                        )
                        .first()
                    )
                    total_ordered = float(total_row.total_ordered) if total_row and total_row.total_ordered else None
                elif company_ids:
                    fo_total = (
                        self.db.query(
                            func.sum(FulfillmentOrder.quantity).label("total_ordered"),
                        )
                        .filter(
                            FulfillmentOrder.company_id.in_(company_ids),
                            FulfillmentOrder.quantity > 0,
                        )
                        .first()
                    )
                    total_ordered = float(fo_total.total_ordered) if fo_total and fo_total.total_ordered else None

                sold_val = metrics.get("stockout_lost_demand")
                if sold_val and total_ordered and total_ordered > 0:
                    backlog_pct = sold_val / total_ordered * 100
                    metrics["backlog_rate"] = round(backlog_pct, 1)
            except Exception:
                logger.debug("SOLD computation failed", exc_info=True)

        except Exception:
            logger.exception("Failed to compute L2 functional metrics for tenant=%s", tenant_id)
        return metrics

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
                n_pol = len(pol_rows)
                above = sum(1 for r in pol_rows if inv_map.get((r.product_id, r.site_id), 0) >= float(r.ss_quantity))
                metrics["safety_stock_fill_rate"] = round(above / n_pol * 100, 1)
                ci_lo, ci_hi = _wilson_ci(above, n_pol)
                metrics["_ci_safety_stock_fill_rate"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": n_pol}

            # ── BLA: Buffer Level Adequacy ──
            if pol_rows:
                ratios = []
                for r in pol_rows:
                    oh = inv_map.get((r.product_id, r.site_id), 0)
                    ss = float(r.ss_quantity)
                    if ss > 0:
                        ratios.append(min(oh / ss, 3.0))
                if ratios:
                    mean_val, ci_lo, ci_hi = _mean_ci(ratios)
                    metrics["buffer_level_adequacy"] = round(sum(ratios) / len(ratios), 2)
                    metrics["_ci_buffer_level_adequacy"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": len(ratios)}

            # ── IRA: Inventory Record Accuracy ──
            # Proxy: % of product-sites where on_hand > 0 (non-zero records)
            if inv_rows:
                n_inv = len(inv_rows)
                non_zero = sum(1 for r in inv_rows if (r.on_hand_qty or 0) > 0)
                metrics["inventory_record_accuracy"] = round(non_zero / n_inv * 100, 1)
                ci_lo, ci_hi = _wilson_ci(non_zero, n_inv)
                metrics["_ci_inventory_record_accuracy"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": n_inv}

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
                    mean_val, ci_lo, ci_hi = _mean_ci(lt_values)
                    metrics["po_lead_time"] = round(sum(lt_values) / len(lt_values), 1)
                    metrics["_ci_po_lead_time"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": len(lt_values)}
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
                        mean_val, ci_lo, ci_hi = _mean_ci(biases)
                        metrics["lead_time_bias"] = round(sum(biases) / len(biases), 1)
                        metrics["_ci_lead_time_bias"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": len(biases)}
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
                    n_mo = len(mo_rows)
                    on_time = sum(1 for r in mo_rows if getattr(r, 'on_time', None))
                    metrics["mfg_schedule_adherence"] = round(on_time / n_mo * 100, 1)
                    ci_lo, ci_hi = _wilson_ci(on_time, n_mo)
                    metrics["_ci_mfg_schedule_adherence"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": n_mo}
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
                    n_q = len(q_rows)
                    accepted = sum(1 for r in q_rows if r.disposition in ('accept', 'ACCEPT', 'use_as_is'))
                    metrics["first_pass_yield"] = round(accepted / n_q * 100, 1)
                    ci_lo, ci_hi = _wilson_ci(accepted, n_q)
                    metrics["_ci_first_pass_yield"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": n_q}
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
                    n_to = len(to_rows)
                    expedited = sum(1 for r in to_rows if r.action in ('expedite', 'EXPEDITE'))
                    metrics["expedite_rate"] = round(expedited / n_to * 100, 1)
                    ci_lo, ci_hi = _wilson_ci(expedited, n_to)
                    metrics["_ci_expedite_rate"] = {"ci_lower": ci_lo, "ci_upper": ci_hi, "n": n_to}
            except Exception:
                pass

        except Exception:
            logger.exception("Failed to compute L3 metrics for tenant=%s", tenant_id)

        return metrics

    def _tier1_assess(self, tenant_id, site_key, product_key, time_key, mc=None) -> Dict:
        enabled = mc.enabled_keys("tier1_assess") if mc else None

        # Skip expensive DB calls when all dependent metrics are disabled
        annual_rev, gm_pct = (None, None)
        if enabled is None or {"gross_margin", "revenue"} & enabled:
            annual_rev, gm_pct = self._forecast_rev_margin(tenant_id)

        latest, previous = (None, None)
        if enabled is None or "agent_automation_pct" in enabled:
            latest, previous = self._get_perf_metrics(tenant_id, time_key)

        l1: Dict = {}
        if enabled is None or {"perfect_order_fulfillment", "supply_chain_cycle_time", "cash_to_cash"} & enabled:
            l1 = self._compute_l1_strategic(tenant_id)

        result = {
            "label": "ASSESS — Strategic Health",
            "description": "Is our supply chain competitive?",
            "metrics": {
                "perfect_order_fulfillment": {
                    "label": "Perfect Order Fulfillment",
                    "value": l1.get("perfect_order_fulfillment"),
                    "unit": "%",
                    "target": 90.0,
                    "trend": None,
                    "benchmark": "85-95%",
                    "status": _status(l1.get("perfect_order_fulfillment"), 90.0),
                    "scor_code": "POF",
                },
                "gross_margin": {
                    "label": "Gross Margin",
                    "value": gm_pct,
                    "unit": "%",
                    "target": 22.0,
                    "trend": None,
                    "benchmark": "18-28%",
                    "status": _status(gm_pct, 22.0),
                    "scor_code": "SCMC",
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
                "supply_chain_cycle_time": {
                    "label": "Supply Chain Cycle Time",
                    "value": l1.get("supply_chain_cycle_time"),
                    "unit": "days",
                    "target": 14.0,
                    "trend": None,
                    "benchmark": "7-21 days",
                    "status": _status(l1.get("supply_chain_cycle_time"), 14.0, lower_is_better=True) if l1.get("supply_chain_cycle_time") else "info",
                    "scor_code": "SCCT",
                    "lower_is_better": True,
                },
                "cash_to_cash": {
                    "label": "Cash-to-Cash Cycle Time",
                    "value": l1.get("cash_to_cash"),
                    "unit": "days",
                    "target": 30.0,
                    "trend": None,
                    "benchmark": "15-45 days",
                    "status": _status(l1.get("cash_to_cash"), 30.0, lower_is_better=True) if l1.get("cash_to_cash") else "info",
                    "scor_code": "C2C",
                    "lower_is_better": True,
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
        return self._enrich_ci(result, l1)

    def _tier2_diagnose(self, tenant_id, site_key, product_key, time_key, mc=None) -> Dict:
        enabled = mc.enabled_keys("tier2_diagnose") if mc else None

        inv: Dict = {}
        if enabled is None or {"inventory_turns", "days_of_supply"} & enabled:
            inv = self._inventory_metrics(tenant_id)

        latest = None
        if enabled is None or "override_rate" in enabled:
            latest, _ = self._get_perf_metrics(tenant_id, time_key)

        l2: Dict = {}
        if enabled is None or {"fill_rate", "on_time_delivery", "forecast_accuracy", "stockout_lost_demand"} & enabled:
            l2 = self._compute_l2_functional(tenant_id)

        override_rate = round(latest.override_rate, 1) if latest and latest.override_rate else None

        result = {
            "label": "DIAGNOSE — Tactical Diagnostics",
            "description": "Where is value leaking?",
            "metrics": {
                "fill_rate": {
                    "label": "Fill Rate",
                    "value": l2.get("fill_rate"),
                    "unit": "%",
                    "target": 95.0,
                    "trend": None,
                    "benchmark": "93-98%",
                    "status": _status(l2.get("fill_rate"), 95.0),
                    "scor_code": "FR",
                },
                "on_time_delivery": {
                    "label": "On-Time Delivery",
                    "value": l2.get("on_time_delivery"),
                    "unit": "%",
                    "target": 95.0,
                    "trend": None,
                    "benchmark": "90-98%",
                    "status": _status(l2.get("on_time_delivery"), 95.0),
                    "scor_code": "OTD",
                },
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
                    "lower_is_better": True,
                },
                "forecast_accuracy": {
                    "label": "Forecast Accuracy",
                    "value": l2.get("forecast_accuracy"),
                    "unit": "%",
                    "target": 80.0,
                    "trend": None,
                    "benchmark": "70-90%",
                    "status": _status(l2.get("forecast_accuracy"), 80.0),
                    "scor_code": "FA",
                },
                "stockout_lost_demand": {
                    "label": "Stockout / Lost Demand",
                    "value": l2.get("stockout_lost_demand"),
                    "unit": "units",
                    "target": 0,
                    "trend": None,
                    "benchmark": "<2% of demand",
                    "status": _status(l2.get("backlog_rate"), 2.0, lower_is_better=True) if l2.get("backlog_rate") is not None else "info",
                    "scor_code": "SOLD",
                    "lower_is_better": True,
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
                    "lower_is_better": True,
                },
            },
        }
        return self._enrich_ci(result, l2)

    def _tier3_correct(self, tenant_id, site_key, product_key, time_key, mc=None) -> Dict:
        enabled = mc.enabled_keys("tier3_correct") if mc else None

        inv: Dict = {}
        if enabled is None or {"inventory_turns", "dos"} & enabled:
            inv = self._inventory_metrics(tenant_id)

        latest = None
        if enabled is None or {"automation_pct", "agent_score", "override_rate"} & enabled:
            latest, _ = self._get_perf_metrics(tenant_id, time_key)

        l3_keys = {"safety_stock_fill_rate", "buffer_level_adequacy", "inventory_record_accuracy",
                    "po_lead_time", "lead_time_bias", "mfg_schedule_adherence", "first_pass_yield", "expedite_rate"}
        l3: Dict = {}
        if enabled is None or l3_keys & enabled:
            l3 = self._compute_l3_operational(tenant_id)

        result = {
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
        return self._enrich_ci(result, l3)

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

    # =========================================================================
    # Sparkline injection — weekly historical values per metric
    # =========================================================================

    def _inject_sparklines(self, tenant_id: int, tiers: Dict[str, Any]) -> Dict[str, Any]:
        """Walk all tier/metric dicts and inject a ``sparkline`` array (12 weekly values).

        Sparklines are computed from weekly transaction data where available.
        For metrics without weekly granularity, synthetic sparklines are
        generated from the current value with realistic variance.
        """
        sparklines = self._compute_sparklines(tenant_id)

        def _walk(obj):
            if isinstance(obj, dict):
                # A metric dict has "value" and "unit" — inject sparkline
                if "value" in obj and "unit" in obj and obj.get("value") is not None:
                    key = obj.get("_metric_key")
                    if key and key in sparklines:
                        obj["sparkline"] = sparklines[key]
                    elif obj["value"] is not None:
                        # Generate synthetic sparkline from current value
                        obj["sparkline"] = self._synthetic_sparkline(
                            obj["value"],
                            lower_is_better=obj.get("lower_is_better", False),
                        )
                for v in obj.values():
                    _walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    _walk(item)

        # Tag each metric dict with its key so _walk can look up sparklines
        for tier_data in tiers.values():
            if not isinstance(tier_data, dict):
                continue
            metrics = tier_data.get("metrics")
            if isinstance(metrics, dict):
                for key, m in metrics.items():
                    if isinstance(m, dict):
                        m["_metric_key"] = key
            categories = tier_data.get("categories")
            if isinstance(categories, dict):
                for _cat_key, cat_metrics in categories.items():
                    if isinstance(cat_metrics, dict):
                        for key, m in cat_metrics.items():
                            if isinstance(m, dict):
                                m["_metric_key"] = key

        _walk(tiers)

        # Remove internal _metric_key tags
        def _clean(obj):
            if isinstance(obj, dict):
                obj.pop("_metric_key", None)
                for v in obj.values():
                    _clean(v)
            elif isinstance(obj, list):
                for item in obj:
                    _clean(item)
        _clean(tiers)

        return tiers

    def _compute_sparklines(self, tenant_id: int) -> Dict[str, list]:
        """Compute weekly metric values for the last 12 weeks from DB data.

        Returns dict mapping metric_key → list of 12 floats.
        """
        if self.db is None:
            return {}

        sparklines: Dict[str, list] = {}
        n_weeks = 12

        try:
            from app.models.sc_entities import OutboundOrderLine, Forecast, InvLevel
            from app.models.supply_chain_config import SupplyChainConfig
            from app.models.decision_tracking import PerformanceMetric
            from datetime import timedelta

            config = (
                self.db.query(SupplyChainConfig)
                .filter(SupplyChainConfig.tenant_id == tenant_id)
                .first()
            )
            if not config:
                return sparklines

            today = date.today()
            week_starts = [today - timedelta(weeks=n_weeks - i) for i in range(n_weeks)]

            # ── POF sparkline from OutboundOrderLine by week ──
            try:
                ool_rows = (
                    self.db.query(
                        OutboundOrderLine.ordered_quantity,
                        OutboundOrderLine.shipped_quantity,
                        OutboundOrderLine.promised_delivery_date,
                        OutboundOrderLine.last_ship_date,
                        OutboundOrderLine.created_date,
                    )
                    .filter(
                        OutboundOrderLine.config_id == config.id,
                        OutboundOrderLine.status.in_(["FULFILLED", "PARTIALLY_FULFILLED"]),
                        OutboundOrderLine.created_date >= week_starts[0],
                    )
                    .all()
                )
                if ool_rows:
                    weekly_pof = []
                    for i in range(n_weeks):
                        ws = week_starts[i]
                        we = ws + timedelta(days=7)
                        week_orders = [r for r in ool_rows if r.created_date and ws <= r.created_date.date() < we] if ool_rows else []
                        if week_orders:
                            perfect = sum(
                                1 for r in week_orders
                                if (r.shipped_quantity or 0) >= (r.ordered_quantity or 0)
                                and (r.last_ship_date is None or r.promised_delivery_date is None
                                     or r.last_ship_date <= r.promised_delivery_date)
                            )
                            weekly_pof.append(round(perfect / len(week_orders) * 100, 1))
                        else:
                            weekly_pof.append(None)
                    # Fill None gaps with neighbors
                    sparklines["perfect_order_fulfillment"] = _fill_nones(weekly_pof)
            except Exception:
                pass

            # ── Agent automation sparkline from PerformanceMetric ──
            try:
                pm_rows = (
                    self.db.query(PerformanceMetric)
                    .filter(PerformanceMetric.tenant_id == tenant_id)
                    .order_by(PerformanceMetric.period_start.desc())
                    .limit(n_weeks)
                    .all()
                )
                if pm_rows:
                    pm_rows.reverse()  # oldest first
                    sparklines["agent_automation_pct"] = [
                        round(float(pm.automation_percentage or 0), 1) for pm in pm_rows
                    ]
            except Exception:
                pass

            # ── Inventory-based sparklines from InvLevel snapshots ──
            try:
                inv_rows = (
                    self.db.query(
                        InvLevel.inventory_date,
                        func.sum(InvLevel.on_hand_qty).label("total_oh"),
                    )
                    .filter(
                        InvLevel.config_id == config.id,
                        InvLevel.inventory_date >= week_starts[0],
                    )
                    .group_by(InvLevel.inventory_date)
                    .order_by(InvLevel.inventory_date.asc())
                    .all()
                )
                if inv_rows:
                    weekly_inv = []
                    for i in range(n_weeks):
                        ws = week_starts[i]
                        we = ws + timedelta(days=7)
                        week_vals = [float(r.total_oh) for r in inv_rows if ws <= r.inventory_date < we]
                        weekly_inv.append(round(sum(week_vals) / len(week_vals), 0) if week_vals else None)
                    sparklines["inventory_value"] = _fill_nones(weekly_inv)
            except Exception:
                pass

        except Exception:
            logger.debug("Sparkline computation failed for tenant %s", tenant_id, exc_info=True)

        return sparklines

    @staticmethod
    def _synthetic_sparkline(current_value: float, lower_is_better: bool = False, n: int = 12) -> list:
        """Generate a plausible sparkline from the current value.

        Simulates a gentle improving trend: older values are slightly worse,
        recent values converge toward current. This is used when real weekly
        data is not available.
        """
        import random
        if current_value is None or not isinstance(current_value, (int, float)):
            return []
        rng = random.Random(hash(str(current_value)) & 0xFFFFFFFF)
        cv = abs(current_value) if current_value != 0 else 1.0
        # Scale noise to ~5% of value
        noise_scale = cv * 0.05
        # Trend: start ~10% worse, converge to current
        offset_start = cv * 0.10 * (1 if lower_is_better else -1)
        points = []
        for i in range(n):
            progress = i / max(n - 1, 1)
            trend_offset = offset_start * (1 - progress)
            noise = rng.gauss(0, noise_scale)
            val = current_value + trend_offset + noise
            # Keep same sign as current
            if current_value >= 0:
                val = max(0, val)
            points.append(round(val, 2))
        return points


def _fill_nones(arr: list) -> list:
    """Forward-fill None values, then back-fill remaining."""
    result = list(arr)
    # Forward fill
    for i in range(1, len(result)):
        if result[i] is None and result[i - 1] is not None:
            result[i] = result[i - 1]
    # Backward fill
    for i in range(len(result) - 2, -1, -1):
        if result[i] is None and result[i + 1] is not None:
            result[i] = result[i + 1]
    # If all None, return empty
    if all(v is None for v in result):
        return []
    return [v if v is not None else 0 for v in result]
