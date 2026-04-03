"""
Scenario Events API — Inject supply chain events for what-if analysis.

Endpoints:
  GET  /catalog              — Event type catalog (categories, types, parameters)
  GET  /config/{id}/events   — List events for a scenario config
  POST /config/{id}/inject   — Inject an event into a scenario config
  POST /events/{id}/revert   — Revert a previously injected event
  GET  /config/{id}/entities — Get selectable entities for event parameter dropdowns
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.models import user as models
from app.models.supply_chain_config import SupplyChainConfig, Site as SiteModel, TransportationLane as Lane
from app.models.sc_entities import OutboundOrder, Product
from app.services.scenario_event_service import ScenarioEventService
from app.services.scenario_branching_service import ScenarioBranchingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scenario-events", tags=["scenario-events"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class InjectEventRequest(BaseModel):
    event_type: str = Field(..., description="Event type key from catalog")
    parameters: Dict[str, Any] = Field(..., description="Event parameters")
    scenario_name: Optional[str] = Field(None, description="Auto-create scenario branch with this name")


class RevertEventRequest(BaseModel):
    pass  # No body needed


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/catalog")
def get_event_catalog(
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Return the full event type catalog for the UI."""
    from app.models.scenario_event import EVENT_CATEGORIES
    return EVENT_CATEGORIES


@router.get("/config/{config_id}/events")
def list_events(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """List all events injected into a scenario config."""
    service = ScenarioEventService(db)
    return service.get_events(config_id)


@router.post("/config/{config_id}/inject")
def inject_event(
    config_id: int,
    request: InjectEventRequest,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Inject an event into a scenario config.

    If scenario_name is provided and the config is a BASELINE,
    auto-creates a scenario branch first.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant context")

    # Check config exists and belongs to tenant
    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == config_id,
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    if config.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Config not in your tenant")

    # Auto-create scenario branch if requested or if config is baseline
    target_config_id = config_id
    scenario_type = getattr(config, "scenario_type", "BASELINE") or "BASELINE"
    if request.scenario_name or scenario_type == "BASELINE":
        branch_name = request.scenario_name or f"What-if: {request.event_type}"
        try:
            branching = ScenarioBranchingService(db)
            branch = branching.create_branch(
                parent_config_id=config_id,
                name=branch_name,
                description=f"Scenario created for {request.event_type} event injection",
                scenario_type="SIMULATION",
                created_by=current_user.id,
            )
            target_config_id = branch.id
            logger.info("Auto-created scenario branch %d from baseline %d", target_config_id, config_id)
        except Exception as e:
            logger.warning("Could not create scenario branch: %s — injecting into config %d directly", e, config_id)
            target_config_id = config_id

    # Inject the event
    service = ScenarioEventService(db)
    try:
        result = service.inject_event(
            config_id=target_config_id,
            tenant_id=tenant_id,
            user_id=current_user.id,
            event_type=request.event_type,
            parameters=request.parameters,
        )
        result["target_config_id"] = target_config_id

        # Broadcast event injection to Decision Stream WebSocket
        try:
            from app.api.endpoints.decision_stream_ws import manager as ws_manager
            import asyncio

            event_labels = {
                "demand_spike": "Demand Surge",
                "drop_in_order": "Demand Drop",
                "supplier_delay": "Supplier Delay",
                "supplier_loss": "Supplier Loss",
                "quality_hold": "Quality Hold",
                "component_shortage": "Component Shortage",
                "machine_breakdown": "Machine Breakdown",
                "capacity_loss": "Capacity Reduction",
                "shipment_delay": "Shipment Delay",
                "lane_disruption": "Lane Disruption",
            }
            label = event_labels.get(request.event_type, request.event_type.replace("_", " ").title())
            trm_types = result.get("trms_responding", [])

            asyncio.create_task(ws_manager.broadcast_to_tenant(tenant_id, {
                "type": "scenario_event_injected",
                "data": {
                    "event_type": request.event_type,
                    "label": label,
                    "config_id": target_config_id,
                    "parameters": request.parameters,
                    "trms_responding": trm_types,
                    "message": (
                        f"Scenario event injected: {label}. "
                        f"{len(trm_types)} TRM agent(s) responding: {', '.join(trm_types)}."
                    ),
                },
            }))
        except Exception as e:
            logger.debug("WebSocket broadcast for scenario event failed: %s", e)

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/events/{event_id}/revert")
def revert_event(
    event_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Revert a previously injected event."""
    service = ScenarioEventService(db)
    try:
        return service.revert_event(event_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/config/{config_id}/entities")
def get_selectable_entities(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Get selectable entities for event parameter dropdowns.

    Returns customers, vendors, products, internal sites, lanes, and
    existing outbound orders — all scoped to the config.
    """
    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == config_id,
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    # Products
    products = db.query(Product).filter(Product.config_id == config_id).all()

    # Sites by type
    sites = db.query(SiteModel).filter(SiteModel.config_id == config_id).all()
    internal_sites = [s for s in sites if s.master_type in ("MANUFACTURER", "INVENTORY")]
    customer_sites = [s for s in sites if s.master_type in ("CUSTOMER", "CUSTOMER")]
    vendor_sites = [s for s in sites if s.master_type in ("VENDOR", "VENDOR")]

    # Lanes
    lanes = db.query(Lane).filter(Lane.config_id == config_id).all()

    # Existing outbound orders
    orders = db.query(OutboundOrder).filter(
        OutboundOrder.config_id == config_id,
        OutboundOrder.status.in_(["DRAFT", "CONFIRMED"]),
    ).all()

    def _site_option(s):
        return {"id": s.id, "name": s.name, "type": s.type or s.master_type}

    def _lane_option(l):
        up = l.upstream_site.name if l.upstream_site else f"Site {l.from_site_id}"
        down = l.downstream_site.name if l.downstream_site else f"Site {l.to_site_id}"
        return {"id": l.id, "name": f"{up} → {down}"}

    return {
        "products": [{"id": p.id, "name": p.description or p.id} for p in products],
        "customers": [_site_option(s) for s in customer_sites],
        "vendor_sites": [_site_option(s) for s in vendor_sites],
        "internal_sites": [_site_option(s) for s in internal_sites],
        "lanes": [_lane_option(l) for l in lanes],
        "outbound_orders": [
            {"id": o.id, "name": f"{o.id} — {o.customer_name or o.customer_id} ({o.status})"}
            for o in orders
        ],
    }
