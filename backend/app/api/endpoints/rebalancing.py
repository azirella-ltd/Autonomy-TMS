"""
Rebalancing API Endpoints

Network-wide inventory rebalancing recommendations using LP optimization.
"""

from typing import List, Optional
from datetime import datetime, date
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import get_sync_db as get_db
from app.models.user import User
from app.models.supply_chain_config import Node as DBNode, Lane as DBLane, SupplyChainConfig
from app.models.sc_entities import InvLevel, InvPolicy, Forecast, Product
from app.models.recommendations import Recommendation, RecommendationDecision
from app.api.endpoints.auth import get_current_user
from app.services.rebalancing_service import (
    RebalancingService, Node, Lane, TransferRecommendation, RebalancingResult
)

router = APIRouter(prefix="/rebalancing", tags=["rebalancing", "recommendations"])
logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Schemas
# ============================================================================

class NodeInput(BaseModel):
    """Node input for rebalancing"""
    id: int
    name: str
    current_inventory: float = Field(..., ge=0)
    target_inventory: float = Field(..., ge=0)
    min_inventory: float = Field(0, ge=0, description="Safety stock")
    max_inventory: float = Field(10000, ge=0, description="Storage capacity")
    holding_cost_per_unit: float = Field(0.5, ge=0)
    backlog_cost_per_unit: float = Field(2.0, ge=0)
    demand_forecast: float = Field(0, ge=0)


class LaneInput(BaseModel):
    """Lane input for rebalancing"""
    id: int
    source_node_id: int
    dest_node_id: int
    transport_cost_per_unit: float = Field(0.1, ge=0)
    lead_time_days: int = Field(1, ge=0)
    max_capacity: float = Field(10000, ge=0)


class RebalancingRequest(BaseModel):
    """Request for rebalancing optimization"""
    config_id: Optional[int] = Field(None, description="Supply chain config ID to load nodes/lanes from")
    nodes: Optional[List[NodeInput]] = Field(None, description="Manual node input")
    lanes: Optional[List[LaneInput]] = Field(None, description="Manual lane input")
    planning_horizon_days: int = Field(7, ge=1, le=90)
    min_transfer_quantity: float = Field(10.0, ge=1)
    target_service_level: float = Field(0.95, ge=0.5, le=1.0)


class TransferRecommendationResponse(BaseModel):
    """Single transfer recommendation"""
    source_node_id: int
    source_node_name: str
    dest_node_id: int
    dest_node_name: str
    quantity: float
    transport_cost: float
    cost_saving: float
    priority: str
    reason: str


class RebalancingResponse(BaseModel):
    """Rebalancing optimization response"""
    success: bool
    total_cost_before: float
    total_cost_after: float
    total_savings: float
    savings_percentage: float
    recommendations: List[TransferRecommendationResponse]
    recommendation_count: int
    optimization_status: str
    computation_time_ms: float


class ExecuteRebalancingRequest(BaseModel):
    """Request to execute rebalancing recommendations"""
    recommendation_ids: List[int] = Field(..., min_items=1)
    notes: Optional[str] = None


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/optimize", response_model=RebalancingResponse)
async def optimize_rebalancing(
    request: RebalancingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Run rebalancing optimization to generate transfer recommendations.

    Either provide config_id to load from database, or provide nodes/lanes manually.
    """
    nodes = []
    lanes = []

    if request.config_id:
        # Load from supply chain config
        config = db.get(SupplyChainConfig, request.config_id)
        if not config:
            raise HTTPException(status_code=404, detail="Supply chain config not found")

        # --- Real inventory data from InvLevel ---
        # Sum on_hand_qty per site for the most recent inventory_date
        max_date_sub = (
            db.query(func.max(InvLevel.inventory_date))
            .filter(InvLevel.config_id == request.config_id)
            .scalar_subquery()
        )
        inv_by_site = (
            db.query(InvLevel.site_id, func.sum(InvLevel.on_hand_qty).label("total_on_hand"))
            .filter(InvLevel.config_id == request.config_id, InvLevel.inventory_date == max_date_sub)
            .group_by(InvLevel.site_id)
            .all()
        )
        inv_map = {row.site_id: float(row.total_on_hand or 0) for row in inv_by_site}

        # --- Safety stock from InvPolicy (abs_level ss_quantity or ss_days × avg demand) ---
        ss_by_site = (
            db.query(InvPolicy.site_id, func.sum(InvPolicy.ss_quantity).label("total_ss"))
            .filter(InvPolicy.config_id == request.config_id, InvPolicy.ss_policy == "abs_level")
            .group_by(InvPolicy.site_id)
            .all()
        )
        ss_map = {row.site_id: float(row.total_ss or 0) for row in ss_by_site}

        # --- Demand forecast: avg weekly P50 per site for next 4 weeks ---
        today = date.today()
        from datetime import timedelta
        horizon_end = today + timedelta(weeks=4)
        demand_by_site = (
            db.query(Forecast.site_id, func.avg(Forecast.forecast_p50).label("avg_weekly"))
            .filter(
                Forecast.config_id == request.config_id,
                Forecast.is_active == "true",
                Forecast.forecast_date >= today,
                Forecast.forecast_date <= horizon_end,
            )
            .group_by(Forecast.site_id)
            .all()
        )
        demand_map = {row.site_id: float(row.avg_weekly or 0) for row in demand_by_site}

        # --- Avg unit cost for holding cost estimate ---
        avg_cost_sub = (
            db.query(func.avg(Product.unit_cost).label("avg_cost"))
            .join(Forecast, Forecast.product_id == Product.id)
            .filter(Forecast.config_id == request.config_id, Forecast.is_active == "true")
            .scalar()
        )
        avg_unit_cost = float(avg_cost_sub or 5.0)
        weekly_holding_cost = avg_unit_cost * 0.25 / 52  # 25% annual carrying cost

        # Load nodes with real inventory data (INVENTORY + MANUFACTURER sites only)
        db_nodes = db.query(DBNode).filter(
            DBNode.config_id == request.config_id,
            DBNode.master_type.in_(["INVENTORY", "MANUFACTURER"]),
        ).all()
        for db_node in db_nodes:
            current_inv = inv_map.get(db_node.id, 0.0)
            safety_stock = ss_map.get(db_node.id, 0.0)
            demand = demand_map.get(db_node.id, 0.0)
            target_inv = safety_stock + demand  # 1 week of demand above safety stock

            nodes.append(Node(
                id=db_node.id,
                name=db_node.name,
                current_inventory=current_inv,
                target_inventory=max(target_inv, safety_stock * 1.5),
                min_inventory=safety_stock,
                max_inventory=current_inv * 3 or 10000,
                holding_cost_per_unit=weekly_holding_cost,
                backlog_cost_per_unit=weekly_holding_cost * 4,
                demand_forecast=demand,
            ))

        # Load lanes with real lead times and capacities
        db_lanes = db.query(DBLane).filter(DBLane.config_id == request.config_id).all()
        for db_lane in db_lanes:
            # Extract lead time from supply_lead_time JSON
            lt_json = db_lane.supply_lead_time or {}
            if isinstance(lt_json, dict):
                lead_time = int(lt_json.get("value", lt_json.get("min", 1)))
            else:
                lead_time = 1

            lanes.append(Lane(
                id=db_lane.id,
                source_node_id=db_lane.from_site_id,
                dest_node_id=db_lane.to_site_id,
                transport_cost_per_unit=avg_unit_cost * 0.02,  # 2% of unit cost
                lead_time_days=lead_time,
                max_capacity=float(db_lane.capacity or 10000),
            ))

    elif request.nodes and request.lanes:
        # Use manual input
        nodes = [
            Node(
                id=n.id,
                name=n.name,
                current_inventory=n.current_inventory,
                target_inventory=n.target_inventory,
                min_inventory=n.min_inventory,
                max_inventory=n.max_inventory,
                holding_cost_per_unit=n.holding_cost_per_unit,
                backlog_cost_per_unit=n.backlog_cost_per_unit,
                demand_forecast=n.demand_forecast
            )
            for n in request.nodes
        ]
        lanes = [
            Lane(
                id=l.id,
                source_node_id=l.source_node_id,
                dest_node_id=l.dest_node_id,
                transport_cost_per_unit=l.transport_cost_per_unit,
                lead_time_days=l.lead_time_days,
                max_capacity=l.max_capacity
            )
            for l in request.lanes
        ]
    else:
        raise HTTPException(
            status_code=400,
            detail="Either config_id or nodes/lanes must be provided"
        )

    if not nodes:
        raise HTTPException(status_code=400, detail="No nodes found for rebalancing")

    # Run optimization
    service = RebalancingService(db)
    result = service.optimize_rebalancing(
        nodes=nodes,
        lanes=lanes,
        planning_horizon_days=request.planning_horizon_days,
        min_transfer_quantity=request.min_transfer_quantity,
        target_service_level=request.target_service_level
    )

    # Calculate savings percentage
    savings_pct = 0.0
    if result.total_cost_before > 0:
        savings_pct = (result.total_savings / result.total_cost_before) * 100

    logger.info(
        f"Rebalancing optimization by {current_user.email}: "
        f"{len(result.recommendations)} recommendations, ${result.total_savings:.2f} savings"
    )

    return RebalancingResponse(
        success=result.success,
        total_cost_before=result.total_cost_before,
        total_cost_after=result.total_cost_after,
        total_savings=result.total_savings,
        savings_percentage=round(savings_pct, 2),
        recommendations=[
            TransferRecommendationResponse(
                source_node_id=r.source_node_id,
                source_node_name=r.source_node_name,
                dest_node_id=r.dest_node_id,
                dest_node_name=r.dest_node_name,
                quantity=r.quantity,
                transport_cost=r.transport_cost,
                cost_saving=r.cost_saving,
                priority=r.priority,
                reason=r.reason
            )
            for r in result.recommendations
        ],
        recommendation_count=len(result.recommendations),
        optimization_status=result.optimization_status,
        computation_time_ms=round(result.computation_time_ms, 2)
    )


@router.post("/demo", response_model=RebalancingResponse)
async def demo_rebalancing(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Run rebalancing optimization using the current user's supply chain config.
    Falls back gracefully if no config exists for the tenant.
    """
    # Find the user's first SC config
    config = (
        db.query(SupplyChainConfig)
        .filter(SupplyChainConfig.tenant_id == current_user.tenant_id)
        .order_by(SupplyChainConfig.id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="No supply chain config found for your tenant")

    # Delegate to the real optimize endpoint via a synthetic request
    synthetic_req = RebalancingRequest(
        config_id=config.id,
        planning_horizon_days=7,
        min_transfer_quantity=10.0,
        target_service_level=0.95,
    )
    return await optimize_rebalancing(request=synthetic_req, db=db, current_user=current_user)


@router.post("/save-recommendations")
async def save_rebalancing_recommendations(
    request: RebalancingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Run rebalancing and save recommendations to the recommendations table
    for tracking and execution workflow.
    """
    # First run optimization
    optimize_response = await optimize_rebalancing(request, db, current_user)

    if not optimize_response.success:
        raise HTTPException(status_code=400, detail="Optimization failed")

    # Save each recommendation
    saved_count = 0
    for rec in optimize_response.recommendations:
        db_rec = Recommendation(
            recommendation_type='rebalancing',
            entity_type='transfer_order',
            entity_id=None,  # Will be set when TO is created
            title=f"Transfer {rec.quantity:.0f} units: {rec.source_node_name} → {rec.dest_node_name}",
            description=rec.reason,
            priority=rec.priority,
            score=min(100, int(50 + rec.cost_saving / 10)),  # Convert cost saving to score
            impact_description=f"Cost saving: ${rec.cost_saving:.2f}, Transport: ${rec.transport_cost:.2f}",
            recommended_action=f"Create transfer order for {rec.quantity:.0f} units",
            metadata={
                'source_node_id': rec.source_node_id,
                'source_node_name': rec.source_node_name,
                'dest_node_id': rec.dest_node_id,
                'dest_node_name': rec.dest_node_name,
                'quantity': rec.quantity,
                'transport_cost': rec.transport_cost,
                'cost_saving': rec.cost_saving,
            },
            status='pending',
            created_by_id=current_user.id,
        )
        db.add(db_rec)
        saved_count += 1

    db.commit()

    logger.info(f"Saved {saved_count} rebalancing recommendations for user {current_user.email}")

    return {
        "success": True,
        "saved_count": saved_count,
        "total_savings": optimize_response.total_savings,
        "message": f"Saved {saved_count} rebalancing recommendations"
    }
