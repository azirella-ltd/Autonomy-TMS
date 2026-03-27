"""
Inventory Visibility API Endpoints
Provides inventory position snapshots, KPI summaries, and site-health rollups.
Follows AWS Supply Chain Inventory Visibility capability.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case, literal
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.models.sc_entities import InvLevel, InvPolicy, Product
from app.models.supply_chain_config import Site, SupplyChainConfig
from app.models.user import User
from app.api.deps import get_current_user
from app.core.permissions import RequirePermission
from app.services.user_scope_service import resolve_user_scope

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic response schemas
# ---------------------------------------------------------------------------

class InventoryPositionRow(BaseModel):
    product_id: str
    product_description: Optional[str] = None
    site_id: int
    site_name: Optional[str] = None
    site_type: Optional[str] = None
    on_hand_qty: float = 0
    in_transit_qty: float = 0
    on_order_qty: float = 0
    allocated_qty: float = 0
    available_qty: float = 0
    reserved_qty: float = 0
    unit_cost: Optional[float] = None
    unit_price: Optional[float] = None
    inventory_value: float = 0
    days_of_supply: Optional[float] = None
    safety_stock_qty: Optional[float] = None
    safety_stock_days: Optional[float] = None
    risk_level: str = "LOW"
    risk_reason: Optional[str] = None
    overstock: bool = False
    inventory_date: Optional[str] = None

    class Config:
        from_attributes = True


class InventorySummary(BaseModel):
    total_skus: int = 0
    total_sites: int = 0
    total_inventory_value: float = 0
    at_risk_count: int = 0
    stockout_count: int = 0
    overstock_count: int = 0
    avg_days_of_supply: float = 0
    fill_rate: float = 0

    class Config:
        from_attributes = True


class SiteHealthRow(BaseModel):
    site_id: int
    site_name: str
    site_type: Optional[str] = None
    total_value: float = 0
    sku_count: int = 0
    risk_breakdown: Dict[str, int] = {}
    health_score: float = 100

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Helper: risk scoring
# ---------------------------------------------------------------------------

def _compute_risk(
    on_hand: float,
    avg_daily_demand: float,
    safety_stock_days: float,
) -> tuple:
    """Return (days_of_supply, risk_level, risk_reason, overstock)."""
    if avg_daily_demand <= 0:
        # No demand — can't compute DOS; treat as LOW risk
        return (None, "LOW", "No demand history", on_hand > 0)

    dos = on_hand / avg_daily_demand

    if dos == 0:
        return (0, "CRITICAL", "Stockout — zero on-hand", False)
    elif dos < safety_stock_days * 0.5:
        return (round(dos, 1), "HIGH", f"DOS {dos:.0f} < 50% safety stock ({safety_stock_days:.0f}d)", False)
    elif dos < safety_stock_days:
        return (round(dos, 1), "MEDIUM", f"DOS {dos:.0f} below safety stock ({safety_stock_days:.0f}d)", False)
    else:
        overstock = dos > safety_stock_days * 3
        reason = f"Overstock — DOS {dos:.0f} > 3× safety stock" if overstock else None
        return (round(dos, 1), "LOW", reason, overstock)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/snapshot", response_model=List[InventoryPositionRow])
async def get_inventory_snapshot(
    config_id: int = Query(..., description="Supply chain configuration ID"),
    site_id: Optional[int] = Query(None, description="Filter by site ID"),
    product_id: Optional[str] = Query(None, description="Filter by product ID"),
    risk_level: Optional[str] = Query(
        None,
        pattern="^(CRITICAL|HIGH|MEDIUM|LOW)$",
        description="Filter by risk level",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequirePermission("view_inventory_visibility")),
):
    """
    Main data endpoint — inventory positions with risk scoring.

    Joins InvLevel + Site + Product + InvPolicy for the latest inventory date
    in the given config. Computes days-of-supply, inventory value, and risk
    level per product-site combination.
    """

    # 1. Determine which sites belong to this config
    sites_q = select(Site).where(Site.config_id == config_id)
    sites_result = await db.execute(sites_q)
    sites = {s.id: s for s in sites_result.scalars().all()}

    if not sites:
        return []

    site_ids = list(sites.keys())

    # User scope filtering — restrict to sites/products the user can access
    allowed_sites, allowed_products = await resolve_user_scope(db, current_user)
    if allowed_sites is not None:
        # Convert site names to IDs within this config
        allowed_site_ids = {sid for sid, s in sites.items() if s.name in allowed_sites}
        site_ids = [sid for sid in site_ids if sid in allowed_site_ids]
        sites = {sid: s for sid, s in sites.items() if sid in allowed_site_ids}
        if not site_ids:
            return []

    # 2. Get latest inventory date for these sites
    latest_date_q = (
        select(func.max(InvLevel.inventory_date))
        .where(InvLevel.site_id.in_(site_ids))
    )
    latest_date_result = await db.execute(latest_date_q)
    latest_date = latest_date_result.scalar()

    if latest_date is None:
        # No inventory data — return empty with site/product skeleton
        return []

    # 3. Query inv_level rows for that date
    inv_q = select(InvLevel).where(
        and_(
            InvLevel.site_id.in_(site_ids),
            InvLevel.inventory_date == latest_date,
        )
    )
    if site_id is not None:
        inv_q = inv_q.where(InvLevel.site_id == site_id)
    if product_id is not None:
        inv_q = inv_q.where(InvLevel.product_id == product_id)
    if allowed_products is not None:
        inv_q = inv_q.where(InvLevel.product_id.in_(allowed_products))

    inv_result = await db.execute(inv_q)
    inv_rows = inv_result.scalars().all()

    # 4. Bulk-load products
    product_ids = list({r.product_id for r in inv_rows})
    products: Dict[str, Any] = {}
    if product_ids:
        prod_q = select(Product).where(Product.id.in_(product_ids))
        prod_result = await db.execute(prod_q)
        products = {p.id: p for p in prod_result.scalars().all()}

    # 5. Bulk-load inv_policies (most specific match per product+site)
    policy_q = select(InvPolicy).where(
        InvPolicy.site_id.in_(site_ids),
    )
    policy_result = await db.execute(policy_q)
    all_policies = policy_result.scalars().all()
    # Build lookup: (product_id, site_id) → policy  (prefer most specific)
    policy_map: Dict[tuple, InvPolicy] = {}
    for pol in all_policies:
        key = (pol.product_id, pol.site_id)
        existing = policy_map.get(key)
        if existing is None or (pol.product_id is not None and existing.product_id is None):
            policy_map[key] = pol

    # 6. Build response rows
    rows: List[InventoryPositionRow] = []
    for inv in inv_rows:
        site = sites.get(inv.site_id)
        product = products.get(inv.product_id)

        unit_cost = product.unit_cost if product and product.unit_cost else 0
        unit_price = product.unit_price if product and product.unit_price else 0
        on_hand = inv.on_hand_qty or 0
        inventory_value = on_hand * unit_cost

        # Look up policy for safety-stock days
        policy = policy_map.get((inv.product_id, inv.site_id)) or policy_map.get((None, inv.site_id))
        safety_stock_days = 14.0  # default fallback
        safety_stock_qty = 0
        if policy:
            if policy.ss_policy == "abs_level" and policy.ss_quantity:
                safety_stock_qty = policy.ss_quantity
                safety_stock_days = 14.0  # default if no demand basis
            elif policy.ss_days:
                safety_stock_days = policy.ss_days
            elif policy.ss_quantity:
                safety_stock_qty = policy.ss_quantity

        # Avg daily demand: approximate from policy or use a simple heuristic
        # In a real implementation this would query forecast / demand_history.
        # For now, derive from safety_stock_qty / safety_stock_days if available,
        # or use on_hand / 30 as a rough proxy.
        avg_daily_demand = 0
        if safety_stock_qty and safety_stock_days:
            avg_daily_demand = safety_stock_qty / safety_stock_days
        elif on_hand > 0:
            avg_daily_demand = on_hand / 30.0  # rough proxy

        dos, risk, reason, overstock = _compute_risk(on_hand, avg_daily_demand, safety_stock_days)

        row = InventoryPositionRow(
            product_id=inv.product_id,
            product_description=product.description if product else None,
            site_id=inv.site_id,
            site_name=site.name if site else None,
            site_type=site.type if site else None,
            on_hand_qty=on_hand,
            in_transit_qty=inv.in_transit_qty or 0,
            on_order_qty=inv.on_order_qty or 0,
            allocated_qty=inv.allocated_qty or 0,
            available_qty=inv.available_qty or 0,
            reserved_qty=inv.reserved_qty or 0,
            unit_cost=unit_cost,
            unit_price=unit_price,
            inventory_value=round(inventory_value, 2),
            days_of_supply=dos,
            safety_stock_qty=safety_stock_qty,
            safety_stock_days=safety_stock_days,
            risk_level=risk,
            risk_reason=reason,
            overstock=overstock,
            inventory_date=latest_date.isoformat() if latest_date else None,
        )
        rows.append(row)

    # 7. Optional: filter by risk_level
    if risk_level:
        rows = [r for r in rows if r.risk_level == risk_level]

    # Sort: CRITICAL first, then HIGH, MEDIUM, LOW
    risk_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    rows.sort(key=lambda r: risk_order.get(r.risk_level, 4))

    return rows


@router.get("/summary", response_model=InventorySummary)
async def get_inventory_summary(
    config_id: int = Query(..., description="Supply chain configuration ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequirePermission("view_inventory_visibility")),
):
    """
    Aggregated KPI summary cards.

    Returns total SKUs, total sites, total inventory value, at-risk counts,
    stockout count, overstock count, average days-of-supply, and fill rate.
    """
    # Re-use snapshot logic for aggregation
    snapshot = await get_inventory_snapshot(
        config_id=config_id,
        site_id=None,
        product_id=None,
        risk_level=None,
        db=db,
        current_user=current_user,
    )

    if not snapshot:
        return InventorySummary()

    total_value = sum(r.inventory_value for r in snapshot)
    stockout = sum(1 for r in snapshot if r.risk_level == "CRITICAL")
    at_risk = sum(1 for r in snapshot if r.risk_level in ("CRITICAL", "HIGH"))
    overstock = sum(1 for r in snapshot if r.overstock)
    dos_values = [r.days_of_supply for r in snapshot if r.days_of_supply is not None]
    avg_dos = sum(dos_values) / len(dos_values) if dos_values else 0

    # Fill rate: % of product-sites with available_qty > 0
    fillable = sum(1 for r in snapshot if r.available_qty > 0)
    fill_rate = (fillable / len(snapshot) * 100) if snapshot else 0

    unique_products = len({r.product_id for r in snapshot})
    unique_sites = len({r.site_id for r in snapshot})

    return InventorySummary(
        total_skus=unique_products,
        total_sites=unique_sites,
        total_inventory_value=round(total_value, 2),
        at_risk_count=at_risk,
        stockout_count=stockout,
        overstock_count=overstock,
        avg_days_of_supply=round(avg_dos, 1),
        fill_rate=round(fill_rate, 1),
    )


@router.get("/site-health", response_model=List[SiteHealthRow])
async def get_site_health(
    config_id: int = Query(..., description="Supply chain configuration ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequirePermission("view_inventory_visibility")),
):
    """
    Per-site health rollup.

    Returns per-site: site_name, site_type, total_value, sku_count,
    risk_breakdown (critical/high/medium/low counts), and health_score (0–100).
    """
    snapshot = await get_inventory_snapshot(
        config_id=config_id,
        site_id=None,
        product_id=None,
        risk_level=None,
        db=db,
        current_user=current_user,
    )

    if not snapshot:
        return []

    # Group by site
    site_groups: Dict[int, List[InventoryPositionRow]] = {}
    for row in snapshot:
        site_groups.setdefault(row.site_id, []).append(row)

    results: List[SiteHealthRow] = []
    for sid, rows in site_groups.items():
        total_value = sum(r.inventory_value for r in rows)
        breakdown = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for r in rows:
            breakdown[r.risk_level] = breakdown.get(r.risk_level, 0) + 1

        # Health score: 100 minus penalties
        # -25 per CRITICAL, -10 per HIGH, -3 per MEDIUM
        score = 100
        score -= breakdown["CRITICAL"] * 25
        score -= breakdown["HIGH"] * 10
        score -= breakdown["MEDIUM"] * 3
        score = max(0, min(100, score))

        results.append(SiteHealthRow(
            site_id=sid,
            site_name=rows[0].site_name or f"Site {sid}",
            site_type=rows[0].site_type,
            total_value=round(total_value, 2),
            sku_count=len(rows),
            risk_breakdown=breakdown,
            health_score=round(score, 1),
        ))

    # Sort by health score ascending (worst first)
    results.sort(key=lambda r: r.health_score)

    return results
