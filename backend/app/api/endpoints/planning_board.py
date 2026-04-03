"""
Planning Board API Endpoints

Netting timeline and planning grid data for the unified Planning Board view.
Supports hierarchical drill-down across Geography, Product, and Time dimensions
with P10/P50/P90 fan chart data.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
from calendar import monthrange
import logging

from app.db.session import get_db
from app.models.sc_entities import (
    SupplyPlan, Product, Forecast, InvLevel, InvPolicy,
    Geography, ProductHierarchy,
)
from app.models.supply_chain_config import Site, SupplyChainConfig
from app.core.capabilities import require_capabilities
from app.api import deps
from app.models.user import User
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class NettingBucket(BaseModel):
    period_start: date
    period_end: date
    period_label: str

    opening_inventory: float = 0.0
    gross_demand: float = 0.0
    scheduled_receipts: float = 0.0
    net_requirement: float = 0.0
    planned_orders: float = 0.0
    closing_inventory: float = 0.0
    safety_stock: float = 0.0

    demand_p10: Optional[float] = None
    demand_p50: Optional[float] = None
    demand_p90: Optional[float] = None
    projected_inv_low: Optional[float] = None
    projected_inv_high: Optional[float] = None

    po_quantity: float = 0.0
    to_quantity: float = 0.0
    mo_quantity: float = 0.0


class NettingGroup(BaseModel):
    """Netting timeline for one aggregation group (product-site or hierarchy node)."""
    group_key: str  # e.g. product_id or hierarchy node key
    group_label: str
    product_ids: List[str]
    site_ids: List[int]
    buckets: List[NettingBucket]


class HierarchyCrumb(BaseModel):
    level: str
    key: str
    label: str
    is_current: bool = False


class HierarchyChild(BaseModel):
    level: str
    key: str
    label: str
    can_drill_down: bool = False


class NettingTimelineResponse(BaseModel):
    config_id: int
    bucket_type: str
    horizon_weeks: int
    groups: List[NettingGroup]
    breadcrumbs: Dict[str, List[HierarchyCrumb]]
    children: Dict[str, List[HierarchyChild]]
    generated_at: datetime


# ============================================================================
# State → Region mapping (same as hierarchical_metrics_service)
# ============================================================================

_STATE_TO_REGION = {
    "WA": "NW", "OR": "NW", "ID": "NW", "MT": "NW",
    "CA": "SW", "NV": "SW", "AZ": "SW", "NM": "SW", "TX": "SW",
    "CO": "Central", "KS": "Central", "NE": "Central", "MO": "Central",
    "IA": "Central", "MN": "Central", "WI": "Central", "IL": "Central",
    "IN": "Central", "OH": "Central", "MI": "Central",
    "NY": "NE", "PA": "NE", "NJ": "NE", "CT": "NE", "MA": "NE",
    "NH": "NE", "VT": "NE", "ME": "NE", "RI": "NE",
    "FL": "SE", "GA": "SE", "NC": "SE", "SC": "SE", "VA": "SE",
    "TN": "SE", "AL": "SE", "MS": "SE", "LA": "SE", "AR": "SE", "KY": "SE",
}

_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ============================================================================
# Hierarchy builders (async versions of hierarchical_metrics_service patterns)
# ============================================================================

async def _build_site_hierarchy(db: AsyncSession, config_id: int) -> Dict:
    """Build site hierarchy: ALL → Region → Site"""
    try:
        config_result = await db.execute(
            select(SupplyChainConfig).where(SupplyChainConfig.id == config_id)
        )
        config = config_result.scalar_one_or_none()
        if not config:
            return {}

        site_result = await db.execute(
            select(Site).where(Site.config_id == config_id)
        )
        sites = site_result.scalars().all()

        region_map: Dict[str, list] = {}
        for s in sites:
            region = "Other"
            if s.geo_id:
                geo_result = await db.execute(
                    select(Geography).where(Geography.id == s.geo_id)
                )
                geo = geo_result.scalar_one_or_none()
                if geo and geo.state_prov:
                    region = _STATE_TO_REGION.get(geo.state_prov, "Other")
            region_map.setdefault(region, []).append(s)

        region_children = {}
        for region, region_sites in sorted(region_map.items()):
            site_children = {
                str(s.id): {
                    "label": getattr(s, 'site_name', None) or s.name or f"Site {s.id}",
                    "level": "site",
                    "can_drill_down": False,
                    "site_ids": [s.id],
                }
                for s in region_sites
            }
            region_children[region] = {
                "label": region,
                "level": "region",
                "can_drill_down": True,
                "site_ids": [s.id for s in region_sites],
                "children": {"site": site_children},
            }

        all_site_ids = [s.id for s in sites]
        return {
            "company": {
                "ALL": {
                    "label": config.name or "All Sites",
                    "level": "company",
                    "can_drill_down": True,
                    "site_ids": all_site_ids,
                    "children": {"region": region_children},
                }
            }
        }
    except Exception:
        logger.exception("Failed to build site hierarchy for config=%s", config_id)
        return {}


async def _build_product_hierarchy(db: AsyncSession, config_id: int) -> Dict:
    """Build product hierarchy: ALL → Family/Category → Product"""
    try:
        prod_result = await db.execute(
            select(Product).where(Product.config_id == config_id)
        )
        products = prod_result.scalars().all()

        # Build group label map
        group_label_map = {}
        try:
            ph_result = await db.execute(
                select(ProductHierarchy.id, ProductHierarchy.description)
                .where(ProductHierarchy.description.isnot(None))
            )
            group_label_map = {r[0]: r[1] for r in ph_result.all()}
        except Exception:
            pass

        cat_map: Dict[str, list] = {}
        for p in products:
            cat = p.product_group_id or "Uncategorized"
            cat_map.setdefault(cat, []).append(p)

        cat_children = {}
        for cat, cat_products in sorted(cat_map.items()):
            prod_children = {
                p.id: {
                    "label": p.description or p.id,
                    "level": "product",
                    "can_drill_down": False,
                    "product_ids": [p.id],
                }
                for p in cat_products
            }
            cat_label = group_label_map.get(cat, cat.replace("_", " ").title())
            cat_children[cat] = {
                "label": cat_label,
                "level": "family",
                "can_drill_down": True,
                "product_ids": [p.id for p in cat_products],
                "children": {"product": prod_children},
            }

        all_prod_ids = [p.id for p in products]
        return {
            "category": {
                "ALL": {
                    "label": "All Products",
                    "level": "category",
                    "can_drill_down": True,
                    "product_ids": all_prod_ids,
                    "children": {"family": cat_children},
                }
            }
        }
    except Exception:
        logger.exception("Failed to build product hierarchy for config=%s", config_id)
        return {}


def _build_time_hierarchy(horizon_weeks: int) -> Dict:
    """Build time hierarchy from planning horizon: Year → Quarter → Month → Week"""
    today = date.today()
    start = today - timedelta(days=today.weekday())

    year_map: Dict[str, Any] = {}
    for i in range(horizon_weeks):
        d = start + timedelta(weeks=i)
        yr = str(d.year)
        q = (d.month - 1) // 3 + 1
        q_key = f"{d.year}-Q{q}"
        mo_key = f"{d.year}-{d.month:02d}"
        mo_label = f"{_MONTH_ABBR[d.month - 1]} {d.year}"
        wk = d.isocalendar()[1]
        wk_key = f"{d.year}-W{wk:02d}"
        wk_label = f"W{wk} {d.strftime('%b %d')}"

        year_map.setdefault(yr, {
            "label": yr, "level": "year", "can_drill_down": True,
            "children": {"quarter": {}},
        })
        quarters = year_map[yr]["children"]["quarter"]
        quarters.setdefault(q_key, {
            "label": f"Q{q} {d.year}", "level": "quarter", "can_drill_down": True,
            "children": {"month": {}},
        })
        months = quarters[q_key]["children"]["month"]
        months.setdefault(mo_key, {
            "label": mo_label, "level": "month", "can_drill_down": True,
            "children": {"week": {}},
        })
        months[mo_key]["children"]["week"][wk_key] = {
            "label": wk_label, "level": "week", "can_drill_down": False,
        }

    return {"year": year_map}


# ============================================================================
# Hierarchy navigation helpers
# ============================================================================

SITE_LEVELS = ["company", "region", "site"]
PRODUCT_LEVELS = ["category", "family", "product"]
TIME_LEVELS = ["year", "quarter", "month", "week"]


def _find_node(tree: Dict, levels: List[str], target_level: str, target_key: str) -> Optional[Dict]:
    """Walk tree to find the node at (target_level, target_key)."""
    def _walk(node: Dict, depth: int):
        if depth >= len(levels):
            return None
        level = levels[depth]
        items = node.get(level, {})
        if level == target_level and target_key in items:
            return items[target_key]
        for k, v in items.items():
            if "children" in v:
                result = _walk(v["children"], depth + 1)
                if result is not None:
                    return result
        return None
    return _walk(tree, 0)


def _build_crumbs(tree: Dict, levels: List[str], target_level: str, target_key: str) -> List[Dict]:
    crumbs = []
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


def _build_children_list(tree: Dict, levels: List[str], target_level: str, target_key: str) -> List[Dict]:
    node = _find_node(tree, levels, target_level, target_key)
    if not node or "children" not in node:
        return []
    results = []
    for child_level, child_nodes in node["children"].items():
        for ck, cv in child_nodes.items():
            results.append({
                "key": ck,
                "label": cv.get("label", ck),
                "level": cv.get("level", child_level),
                "can_drill_down": cv.get("can_drill_down", False),
            })
    return results


def _resolve_ids(tree: Dict, levels: List[str], target_level: str, target_key: str, id_field: str) -> List:
    """Resolve a hierarchy node to concrete IDs (site_ids or product_ids)."""
    node = _find_node(tree, levels, target_level, target_key)
    if not node:
        return []
    return node.get(id_field, [])


def _time_range_for_node(target_level: str, target_key: str) -> Optional[tuple]:
    """Convert time hierarchy key to (start_date, end_date)."""
    try:
        if target_level == "year":
            yr = int(target_key)
            return (date(yr, 1, 1), date(yr, 12, 31))
        elif target_level == "quarter":
            yr, q = target_key.split("-Q")
            q = int(q)
            m_start = (q - 1) * 3 + 1
            m_end = q * 3
            return (date(int(yr), m_start, 1), date(int(yr), m_end, monthrange(int(yr), m_end)[1]))
        elif target_level == "month":
            yr, mo = target_key.split("-")
            yr, mo = int(yr), int(mo)
            return (date(yr, mo, 1), date(yr, mo, monthrange(yr, mo)[1]))
        elif target_level == "week":
            yr, wk = target_key.split("-W")
            yr, wk = int(yr), int(wk)
            jan1 = date(yr, 1, 1)
            start = jan1 + timedelta(weeks=wk - 1) - timedelta(days=jan1.weekday())
            return (start, start + timedelta(days=6))
    except Exception:
        pass
    return None


def _bucket_type_for_level(time_level: str) -> str:
    """Determine appropriate bucket granularity based on time hierarchy level."""
    return {
        "year": "monthly",
        "quarter": "monthly",
        "month": "weekly",
        "week": "weekly",
    }.get(time_level, "weekly")


# ============================================================================
# Netting computation
# ============================================================================

async def _compute_netting(
    db: AsyncSession,
    config_id: int,
    product_ids: List[str],
    site_ids: List[int],
    buckets_def: List[tuple],
    plan_version: Optional[str],
) -> List[NettingBucket]:
    """Compute aggregated netting across given products and sites."""
    if not product_ids or not site_ids or not buckets_def:
        return []

    horizon_start = buckets_def[0][0]
    horizon_end = buckets_def[-1][1]

    # Fetch supply plans
    sp_stmt = (
        select(SupplyPlan)
        .where(and_(
            SupplyPlan.config_id == config_id,
            SupplyPlan.product_id.in_(product_ids),
            SupplyPlan.site_id.in_(site_ids),
            SupplyPlan.plan_date >= horizon_start,
            SupplyPlan.plan_date <= horizon_end,
        ))
        .order_by(SupplyPlan.plan_date)
    )
    if plan_version:
        sp_stmt = sp_stmt.where(SupplyPlan.plan_version == plan_version)
    sp_result = await db.execute(sp_stmt)
    supply_plans = sp_result.scalars().all()

    # Fetch forecasts
    fc_stmt = (
        select(Forecast)
        .where(and_(
            Forecast.config_id == config_id,
            Forecast.product_id.in_(product_ids),
            Forecast.site_id.in_(site_ids),
            Forecast.forecast_date >= horizon_start,
            Forecast.forecast_date <= horizon_end,
        ))
        .order_by(Forecast.forecast_date)
    )
    fc_result = await db.execute(fc_stmt)
    forecasts = fc_result.scalars().all()

    # Aggregate current inventory across all product-site combos
    inv_stmt = (
        select(func.sum(InvLevel.on_hand_qty))
        .where(and_(
            InvLevel.product_id.in_(product_ids),
            InvLevel.site_id.in_(site_ids),
        ))
    )
    inv_result = await db.execute(inv_stmt)
    opening_inv = float(inv_result.scalar_one_or_none() or 0)

    # Aggregate safety stock
    ss_stmt = (
        select(func.sum(InvPolicy.ss_quantity))
        .where(and_(
            InvPolicy.product_id.in_(product_ids),
            InvPolicy.site_id.in_(site_ids),
            or_(InvPolicy.config_id == config_id, InvPolicy.config_id.is_(None)),
        ))
    )
    ss_result = await db.execute(ss_stmt)
    ss_qty = float(ss_result.scalar_one_or_none() or 0)

    # Build buckets
    buckets = []
    running_inv = opening_inv

    for b_start, b_end, b_label in buckets_def:
        bucket_demand = 0.0
        bucket_p10 = 0.0
        bucket_p50 = 0.0
        bucket_p90 = 0.0
        has_probabilistic = False

        for fc in forecasts:
            if fc.forecast_date and b_start <= fc.forecast_date <= b_end:
                bucket_demand += float(fc.forecast_quantity or fc.forecast_p50 or 0)
                if fc.forecast_p10 is not None:
                    bucket_p10 += float(fc.forecast_p10)
                    bucket_p50 += float(fc.forecast_p50 or fc.forecast_quantity or 0)
                    bucket_p90 += float(fc.forecast_p90 or 0)
                    has_probabilistic = True

        bucket_supply = 0.0
        bucket_po = 0.0
        bucket_to = 0.0
        bucket_mo = 0.0
        bucket_sp_demand = 0.0

        for sp in supply_plans:
            if sp.plan_date and b_start <= sp.plan_date <= b_end:
                qty = float(sp.planned_order_quantity or 0)
                if sp.plan_type == "po_request":
                    bucket_po += qty
                elif sp.plan_type == "to_request":
                    bucket_to += qty
                elif sp.plan_type == "mo_request":
                    bucket_mo += qty
                bucket_supply += qty
                if sp.demand_quantity:
                    bucket_sp_demand += float(sp.demand_quantity)

        gross_demand = bucket_sp_demand if bucket_sp_demand > 0 else bucket_demand
        scheduled_receipts = bucket_supply
        net_req = max(0, gross_demand + ss_qty - running_inv - scheduled_receipts)
        closing_inv = running_inv + scheduled_receipts - gross_demand

        proj_low = None
        proj_high = None
        if has_probabilistic:
            proj_low = running_inv + scheduled_receipts - bucket_p90
            proj_high = running_inv + scheduled_receipts - bucket_p10

        buckets.append(NettingBucket(
            period_start=b_start,
            period_end=b_end,
            period_label=b_label,
            opening_inventory=round(running_inv, 1),
            gross_demand=round(gross_demand, 1),
            scheduled_receipts=round(scheduled_receipts, 1),
            net_requirement=round(net_req, 1),
            planned_orders=round(bucket_supply, 1),
            closing_inventory=round(closing_inv, 1),
            safety_stock=round(ss_qty, 1),
            demand_p10=round(bucket_p10, 1) if has_probabilistic else None,
            demand_p50=round(bucket_p50, 1) if has_probabilistic else None,
            demand_p90=round(bucket_p90, 1) if has_probabilistic else None,
            projected_inv_low=round(proj_low, 1) if proj_low is not None else None,
            projected_inv_high=round(proj_high, 1) if proj_high is not None else None,
            po_quantity=round(bucket_po, 1),
            to_quantity=round(bucket_to, 1),
            mo_quantity=round(bucket_mo, 1),
        ))
        running_inv = closing_inv

    return buckets


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/netting-timeline", response_model=NettingTimelineResponse)
@require_capabilities(["view_supply_planning"])
async def get_netting_timeline(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    config_id: int = Query(..., description="Supply chain config ID"),
    # Hierarchy navigation (same pattern as hierarchical-metrics/dashboard)
    site_level: str = Query("company", description="Geography level: company, region, site"),
    site_key: str = Query("ALL", description="Geography key at current level"),
    product_level: str = Query("category", description="Product level: category, family, product"),
    product_key: str = Query("ALL", description="Product key at current level"),
    time_level: str = Query("year", description="Time level: year, quarter, month, week"),
    time_key: Optional[str] = Query(None, description="Time key (e.g. 2026, 2026-Q1, 2026-03)"),
    plan_version: Optional[str] = Query(None),
):
    """
    Netting timeline with hierarchical drill-down.

    Navigate Geography (Company→Region→Site), Product (Category→Family→SKU),
    and Time (Year→Quarter→Month→Week) dimensions. Data is aggregated at
    the selected level. Returns breadcrumbs + children for navigation.
    """
    try:
        today = date.today()

        # Build all three hierarchies
        site_hier = await _build_site_hierarchy(db, config_id)
        product_hier = await _build_product_hierarchy(db, config_id)

        # Determine time range from hierarchy selection
        if time_key:
            time_range = _time_range_for_node(time_level, time_key)
        else:
            # Default: current year
            time_key = str(today.year)
            time_range = (date(today.year, 1, 1), date(today.year, 12, 31))

        if not time_range:
            time_range = (today, today + timedelta(weeks=26))

        horizon_weeks = max(4, (time_range[1] - time_range[0]).days // 7 + 1)
        time_hier = _build_time_hierarchy(horizon_weeks)

        # Determine bucket granularity from time level
        bucket_type = _bucket_type_for_level(time_level)

        # Build time buckets within the selected range
        buckets_def = []
        if bucket_type == "weekly":
            start = time_range[0] - timedelta(days=time_range[0].weekday())
            while start <= time_range[1]:
                b_end = start + timedelta(days=6)
                wk = start.isocalendar()[1]
                label = f"W{wk} {start.strftime('%b %d')}"
                buckets_def.append((start, min(b_end, time_range[1]), label))
                start += timedelta(weeks=1)
        else:
            cur = time_range[0].replace(day=1)
            while cur <= time_range[1]:
                m, y = cur.month, cur.year
                days_in = monthrange(y, m)[1]
                b_start = date(y, m, 1)
                b_end = date(y, m, days_in)
                label = f"{_MONTH_ABBR[m - 1]} {y}"
                buckets_def.append((max(b_start, time_range[0]), min(b_end, time_range[1]), label))
                # Next month
                if m == 12:
                    cur = date(y + 1, 1, 1)
                else:
                    cur = date(y, m + 1, 1)

        if not buckets_def:
            buckets_def = [(today, today + timedelta(days=6), "Current")]

        # Resolve hierarchy selections to concrete IDs
        resolved_site_ids = _resolve_ids(site_hier, SITE_LEVELS, site_level, site_key, "site_ids")
        resolved_product_ids = _resolve_ids(product_hier, PRODUCT_LEVELS, product_level, product_key, "product_ids")

        # Build breadcrumbs and children for all dimensions
        breadcrumbs = {
            "site": _build_crumbs(site_hier, SITE_LEVELS, site_level, site_key),
            "product": _build_crumbs(product_hier, PRODUCT_LEVELS, product_level, product_key),
            "time": _build_crumbs(time_hier, TIME_LEVELS, time_level, time_key),
        }
        children_nav = {
            "site": _build_children_list(site_hier, SITE_LEVELS, site_level, site_key),
            "product": _build_children_list(product_hier, PRODUCT_LEVELS, product_level, product_key),
            "time": _build_children_list(time_hier, TIME_LEVELS, time_level, time_key),
        }

        # Build netting groups based on drill-down children at the current level
        groups = []
        child_dimension = None

        # Determine which dimension has the most specific drill-down context
        # Show children of the narrower dimension as separate groups
        site_children = children_nav.get("site", [])
        product_children = children_nav.get("product", [])

        if len(resolved_product_ids) <= 1 and len(resolved_site_ids) <= 1:
            # Single product, single site — one group
            if resolved_product_ids and resolved_site_ids:
                netting = await _compute_netting(
                    db, config_id, resolved_product_ids, resolved_site_ids,
                    buckets_def, plan_version,
                )
                label_parts = []
                if len(resolved_product_ids) == 1:
                    label_parts.append(resolved_product_ids[0])
                if len(resolved_site_ids) == 1:
                    label_parts.append(f"Site {resolved_site_ids[0]}")
                groups.append(NettingGroup(
                    group_key="all",
                    group_label=" @ ".join(label_parts) or "Selected",
                    product_ids=resolved_product_ids,
                    site_ids=resolved_site_ids,
                    buckets=netting,
                ))
        elif product_children and len(product_children) <= 20:
            # Show each product child as a separate group
            child_node_data = _find_node(product_hier, PRODUCT_LEVELS, product_level, product_key)
            if child_node_data and "children" in child_node_data:
                for child_level, child_nodes in child_node_data["children"].items():
                    for ck, cv in list(child_nodes.items())[:20]:
                        child_prod_ids = cv.get("product_ids", [ck])
                        netting = await _compute_netting(
                            db, config_id, child_prod_ids, resolved_site_ids,
                            buckets_def, plan_version,
                        )
                        if any(b.gross_demand > 0 or b.planned_orders > 0 for b in netting):
                            groups.append(NettingGroup(
                                group_key=ck,
                                group_label=cv.get("label", ck),
                                product_ids=child_prod_ids,
                                site_ids=resolved_site_ids,
                                buckets=netting,
                            ))
        elif site_children and len(site_children) <= 20:
            # Show each site child as a separate group
            child_node_data = _find_node(site_hier, SITE_LEVELS, site_level, site_key)
            if child_node_data and "children" in child_node_data:
                for child_level, child_nodes in child_node_data["children"].items():
                    for ck, cv in list(child_nodes.items())[:20]:
                        child_site_ids = cv.get("site_ids", [])
                        netting = await _compute_netting(
                            db, config_id, resolved_product_ids, child_site_ids,
                            buckets_def, plan_version,
                        )
                        if any(b.gross_demand > 0 or b.planned_orders > 0 for b in netting):
                            groups.append(NettingGroup(
                                group_key=ck,
                                group_label=cv.get("label", ck),
                                product_ids=resolved_product_ids,
                                site_ids=child_site_ids,
                                buckets=netting,
                            ))

        # Fallback: single aggregated group
        if not groups and resolved_product_ids and resolved_site_ids:
            netting = await _compute_netting(
                db, config_id, resolved_product_ids, resolved_site_ids,
                buckets_def, plan_version,
            )
            groups.append(NettingGroup(
                group_key="all",
                group_label="All Selected",
                product_ids=resolved_product_ids,
                site_ids=resolved_site_ids,
                buckets=netting,
            ))

        return NettingTimelineResponse(
            config_id=config_id,
            bucket_type=bucket_type,
            horizon_weeks=horizon_weeks,
            groups=groups,
            breadcrumbs=breadcrumbs,
            children=children_nav,
            generated_at=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"Error getting netting timeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))
