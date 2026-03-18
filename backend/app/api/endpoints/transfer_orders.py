"""
Transfer Order API Endpoints

Provides REST API for Transfer Order data and analytics.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.db.session import get_sync_db as get_db
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.scenario import Scenario
from app.models.supply_chain_config import Site
from app.services.sc_execution.to_analytics import TransferOrderAnalytics
from app.services.sc_execution.site_id_mapper import SimulationIdMapper

router = APIRouter()


@router.get("/scenarios/{scenario_id}/transfer-orders")
async def get_game_transfer_orders(
    scenario_id: int,
    status: Optional[str] = Query(None, description="Filter by status"),
    round_number: Optional[int] = Query(None, description="Filter by round"),
    db: Session = Depends(get_db)
):
    """Get all Transfer Orders for a scenario with site names for display."""
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

    # Initialize ID mapper for site name lookup
    mapper = SimulationIdMapper(db, scenario.config_id)

    query = db.query(TransferOrder).filter(TransferOrder.scenario_id == scenario_id)
    if status:
        query = query.filter(TransferOrder.status == status)
    if round_number is not None:
        query = query.filter(
            (TransferOrder.order_round == round_number) |
            (TransferOrder.arrival_round == round_number)
        )

    tos = query.order_by(TransferOrder.order_round, TransferOrder.created_at).all()

    result = []
    for to in tos:
        line_items = db.query(TransferOrderLineItem).filter(
            TransferOrderLineItem.to_id == to.id
        ).all()
        total_quantity = sum(line.shipped_quantity for line in line_items)

        # Get site names for display
        source_name = mapper.get_site_name(to.source_site_id) if to.source_site_id else "UNKNOWN"
        dest_name = mapper.get_site_name(to.destination_site_id) if to.destination_site_id else "MARKET"

        result.append({
            "to_number": to.to_number,
            "source_site_id": to.source_site_id,  # Integer site ID
            "source_site_name": source_name,  # Human-readable name for display
            "destination_site_id": to.destination_site_id,  # Integer site ID
            "destination_site_name": dest_name,  # Human-readable name for display
            "status": to.status,
            "order_round": to.order_round,
            "arrival_round": to.arrival_round,
            "quantity": total_quantity,
            "line_item_count": len(line_items)
        })

    return {"scenario_id": scenario_id, "total_count": len(result), "transfer_orders": result}


@router.get("/scenarios/{scenario_id}/transfer-order-analytics")
async def get_transfer_order_analytics(
    scenario_id: int,
    include_routes: bool = Query(True),
    include_timeline: bool = Query(True),
    db: Session = Depends(get_db)
):
    """Get comprehensive TO analytics for a scenario."""
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

    analytics = TransferOrderAnalytics(db)
    return analytics.get_scenario_to_metrics(scenario_id, include_routes, include_timeline)
