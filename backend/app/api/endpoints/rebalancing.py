"""
Rebalancing API Endpoints

Network-wide inventory rebalancing recommendations using LP optimization.
"""

from typing import List, Optional
from datetime import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_sync_db as get_db
from app.models.user import User
from app.models.supply_chain_config import Node as DBNode, Lane as DBLane, SupplyChainConfig
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

        # Load nodes with inventory data
        db_nodes = db.query(DBNode).filter(DBNode.config_id == request.config_id).all()
        for db_node in db_nodes:
            # Get current inventory from node state or use defaults
            current_inv = getattr(db_node, 'current_inventory', 100)
            target_inv = getattr(db_node, 'target_inventory', 150)
            safety_stock = getattr(db_node, 'safety_stock', 30)
            demand = getattr(db_node, 'demand_forecast', 50)

            nodes.append(Node(
                id=db_node.id,
                name=db_node.name,
                current_inventory=current_inv,
                target_inventory=target_inv,
                min_inventory=safety_stock,
                max_inventory=getattr(db_node, 'max_inventory', 1000),
                holding_cost_per_unit=getattr(db_node, 'holding_cost', 0.5),
                backlog_cost_per_unit=getattr(db_node, 'backlog_cost', 2.0),
                demand_forecast=demand
            ))

        # Load lanes
        db_lanes = db.query(DBLane).filter(DBLane.config_id == request.config_id).all()
        for db_lane in db_lanes:
            lanes.append(Lane(
                id=db_lane.id,
                source_node_id=db_lane.source_node_id,
                dest_node_id=db_lane.dest_node_id,
                transport_cost_per_unit=getattr(db_lane, 'transport_cost', 0.1),
                lead_time_days=getattr(db_lane, 'lead_time', 1),
                max_capacity=getattr(db_lane, 'capacity', 10000)
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
    Run demo rebalancing with sample data.
    Useful for testing and demonstration.
    """
    # Sample 4-node Beer Game network
    nodes = [
        Node(id=1, name="Retailer", current_inventory=25, target_inventory=100,
             min_inventory=30, max_inventory=500, holding_cost_per_unit=0.5,
             backlog_cost_per_unit=2.0, demand_forecast=50),
        Node(id=2, name="Wholesaler", current_inventory=180, target_inventory=150,
             min_inventory=40, max_inventory=600, holding_cost_per_unit=0.4,
             backlog_cost_per_unit=1.8, demand_forecast=55),
        Node(id=3, name="Distributor", current_inventory=220, target_inventory=200,
             min_inventory=50, max_inventory=800, holding_cost_per_unit=0.35,
             backlog_cost_per_unit=1.5, demand_forecast=60),
        Node(id=4, name="Factory", current_inventory=350, target_inventory=300,
             min_inventory=80, max_inventory=1000, holding_cost_per_unit=0.3,
             backlog_cost_per_unit=1.2, demand_forecast=65),
    ]

    lanes = [
        Lane(id=1, source_node_id=2, dest_node_id=1, transport_cost_per_unit=0.15,
             lead_time_days=2, max_capacity=200),
        Lane(id=2, source_node_id=3, dest_node_id=2, transport_cost_per_unit=0.12,
             lead_time_days=2, max_capacity=250),
        Lane(id=3, source_node_id=4, dest_node_id=3, transport_cost_per_unit=0.10,
             lead_time_days=3, max_capacity=300),
        # Cross-dock option
        Lane(id=4, source_node_id=3, dest_node_id=1, transport_cost_per_unit=0.20,
             lead_time_days=1, max_capacity=100),
    ]

    service = RebalancingService(db)
    result = service.optimize_rebalancing(
        nodes=nodes,
        lanes=lanes,
        planning_horizon_days=7,
        min_transfer_quantity=10.0,
        target_service_level=0.95
    )

    savings_pct = 0.0
    if result.total_cost_before > 0:
        savings_pct = (result.total_savings / result.total_cost_before) * 100

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
        optimization_status=result.optimization_status + " (Demo Data)",
        computation_time_ms=round(result.computation_time_ms, 2)
    )


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
