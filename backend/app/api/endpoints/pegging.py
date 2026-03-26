"""
Full-Level Pegging & Multi-Stage CTP API Endpoints

Provides REST API for:
- Demand-to-supply tracing (full pegging chain)
- Supply-to-demand tracing (reverse pegging)
- Product@site pegging summary
- Multi-stage CTP calculation
- Order promising with pegging chain creation
- Unpegged demand listing
"""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.services.pegging_service import PeggingService
from app.services.multi_stage_ctp_service import MultiStageCTPService

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request/Response schemas
# ---------------------------------------------------------------------------

class MultiStageCTPRequest(BaseModel):
    product_id: str
    site_id: int
    quantity: float
    target_date: Optional[str] = None  # ISO date string
    config_id: int
    tenant_id: int


class OrderPromiseRequest(BaseModel):
    order_id: str
    product_id: str
    site_id: int
    quantity: float
    target_date: str  # ISO date string
    priority: int = 3
    config_id: int
    tenant_id: int


# ---------------------------------------------------------------------------
# Demand-to-supply tracing
# ---------------------------------------------------------------------------

@router.get("/demand/{demand_type}/{demand_id}")
def trace_demand_to_supply(
    demand_type: str,
    demand_id: str,
    config_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trace from demand to all supply backing it.

    Full pegging chain: customer order → DC inventory → factory PO → vendor.
    """
    svc = PeggingService(db)
    chains = svc.trace_demand_to_supply(demand_type, demand_id, config_id)

    return {
        "demand_type": demand_type,
        "demand_id": demand_id,
        "chains_count": len(chains),
        "chains": [
            {
                "chain_id": c.chain_id,
                "demand_product": c.demand_product,
                "demand_site_name": c.demand_site_name,
                "demand_quantity": c.demand_quantity,
                "demand_priority": c.demand_priority,
                "total_stages": c.total_stages,
                "is_fully_pegged": c.is_fully_pegged,
                "unpegged_quantity": c.unpegged_quantity,
                "links": [
                    {
                        "depth": l.depth,
                        "product_id": l.product_id,
                        "demand_type": l.demand_type,
                        "demand_id": l.demand_id,
                        "supply_type": l.supply_type,
                        "supply_id": l.supply_id,
                        "site_name": l.site_name,
                        "supply_site_name": l.supply_site_name,
                        "pegged_quantity": l.pegged_quantity,
                        "status": l.status,
                    }
                    for l in c.links
                ],
            }
            for c in chains
        ],
    }


# ---------------------------------------------------------------------------
# Supply-to-demand tracing
# ---------------------------------------------------------------------------

@router.get("/supply/{supply_type}/{supply_id}")
def trace_supply_to_demand(
    supply_type: str,
    supply_id: str,
    config_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trace from supply to all demand it backs.

    Reverse pegging: supply → what orders does this serve?
    """
    svc = PeggingService(db)
    chains = svc.trace_supply_to_demand(supply_type, supply_id, config_id)

    return {
        "supply_type": supply_type,
        "supply_id": supply_id,
        "chains_count": len(chains),
        "chains": [
            {
                "chain_id": c.chain_id,
                "demand_type": c.demand_type,
                "demand_id": c.demand_id,
                "demand_product": c.demand_product,
                "demand_quantity": c.demand_quantity,
                "demand_priority": c.demand_priority,
                "total_stages": c.total_stages,
                "is_fully_pegged": c.is_fully_pegged,
            }
            for c in chains
        ],
    }


# ---------------------------------------------------------------------------
# Product@site pegging summary
# ---------------------------------------------------------------------------

@router.get("/product-site/{product_id}/{site_id}")
def get_product_site_pegging(
    product_id: str,
    site_id: int,
    config_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Pegging summary for a product at a site.

    Shows total demand, pegged/unpegged breakdown by type.
    """
    svc = PeggingService(db)
    summary = svc.get_product_site_pegging(product_id, site_id, config_id)

    return {
        "product_id": summary.product_id,
        "site_id": summary.site_id,
        "site_name": summary.site_name,
        "total_demand": summary.total_demand,
        "pegged_demand": summary.pegged_demand,
        "unpegged_demand": summary.unpegged_demand,
        "total_supply": summary.total_supply,
        "pegged_supply": summary.pegged_supply,
        "demand_by_type": summary.demand_by_type,
        "supply_by_type": summary.supply_by_type,
        "chains_count": len(summary.chains),
    }


# ---------------------------------------------------------------------------
# Chain lookup
# ---------------------------------------------------------------------------

@router.get("/chain/{chain_id}")
def get_pegging_chain(
    chain_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get a full end-to-end pegging chain by chain_id.
    """
    svc = PeggingService(db)
    chain = svc.rebuild_pegging_chain(chain_id)

    if not chain:
        raise HTTPException(status_code=404, detail=f"Chain {chain_id} not found")

    return {
        "chain_id": chain.chain_id,
        "demand_type": chain.demand_type,
        "demand_id": chain.demand_id,
        "demand_product": chain.demand_product,
        "demand_site_name": chain.demand_site_name,
        "demand_quantity": chain.demand_quantity,
        "demand_priority": chain.demand_priority,
        "total_stages": chain.total_stages,
        "is_fully_pegged": chain.is_fully_pegged,
        "unpegged_quantity": chain.unpegged_quantity,
        "links": [
            {
                "depth": l.depth,
                "product_id": l.product_id,
                "demand_type": l.demand_type,
                "demand_id": l.demand_id,
                "supply_type": l.supply_type,
                "supply_id": l.supply_id,
                "site_id": l.site_id,
                "site_name": l.site_name,
                "supply_site_id": l.supply_site_id,
                "supply_site_name": l.supply_site_name,
                "pegged_quantity": l.pegged_quantity,
                "status": l.status,
            }
            for l in chain.links
        ],
    }


# ---------------------------------------------------------------------------
# Multi-stage CTP
# ---------------------------------------------------------------------------

@router.post("/ctp/multi-stage")
def calculate_multi_stage_ctp(
    req: MultiStageCTPRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Calculate multi-stage CTP for a product at a site.

    Traverses the supply chain DAG upstream, checking availability
    at each stage with BOM explosion and lead time accumulation.
    """
    target = None
    if req.target_date:
        target = date.fromisoformat(req.target_date)

    svc = MultiStageCTPService(
        db=db,
        config_id=req.config_id,
        tenant_id=req.tenant_id,
    )

    result = svc.calculate_multi_stage_ctp(
        product_id=req.product_id,
        site_id=req.site_id,
        quantity=req.quantity,
        target_date=target,
    )

    return result.to_dict()


# ---------------------------------------------------------------------------
# Order promising with pegging
# ---------------------------------------------------------------------------

@router.post("/ctp/promise")
def promise_order(
    req: OrderPromiseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Promise an order with full pegging chain creation.

    1. Calculate multi-stage CTP
    2. If feasible, create pegging chain from demand to upstream supply
    3. Return promise result with chain_id for tracing
    """
    target = date.fromisoformat(req.target_date)

    svc = MultiStageCTPService(
        db=db,
        config_id=req.config_id,
        tenant_id=req.tenant_id,
    )

    result = svc.promise_order(
        order_id=req.order_id,
        product_id=req.product_id,
        site_id=req.site_id,
        quantity=req.quantity,
        target_date=target,
        priority=req.priority,
    )

    return {
        "order_id": result.order_id,
        "promised": result.promised,
        "promised_qty": result.promised_qty,
        "promised_date": result.promised_date.isoformat() if result.promised_date else None,
        "pegging_chain_id": result.pegging_chain_id,
        "ctp": result.ctp_result.to_dict(),
    }


# ---------------------------------------------------------------------------
# Unpegged demand
# ---------------------------------------------------------------------------

@router.get("/unpegged/{config_id}")
def get_unpegged_demand(
    config_id: int,
    tenant_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all unpegged demand for a config.

    Returns demand records that are not yet linked to supply,
    useful as a planning action list.
    """
    svc = PeggingService(db)
    result = svc.get_unpegged_demand(config_id, tenant_id)

    return {
        "config_id": config_id,
        "unpegged": result,
    }


# ---------------------------------------------------------------------------
# Pegging Gantt chart
# ---------------------------------------------------------------------------

@router.get("/gantt/{config_id}/{product_id}/{site_id}")
def get_pegging_gantt(
    config_id: int,
    product_id: str,
    site_id: int,
    demand_date: str = Query(..., description="ISO date of the demand bucket"),
    demand_type: Optional[str] = Query(None),
    demand_id: Optional[str] = Query(None),
    include_conformal: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Build Gantt chart data showing how demand at a specific time bucket
    is satisfied through the full pegging tree (multi-level BOM).

    Returns hierarchical rows (by BOM level) with supply bars showing
    order dates, receipt dates, quantities, and conformal prediction
    intervals for lead time uncertainty.
    """
    from app.services.pegging_gantt_service import PeggingGanttService

    svc = PeggingGanttService(db)
    result = svc.build_gantt_data(
        config_id=config_id,
        product_id=product_id,
        site_id=site_id,
        demand_date=date.fromisoformat(demand_date),
        demand_type=demand_type,
        demand_id=demand_id,
        include_conformal=include_conformal,
    )
    return result
