"""
Recommended Actions API Endpoints

AWS Supply Chain-inspired recommendation system that provides:
- Inventory risk detection and summary
- Resolution recommendations ranked by score
- Before/after state comparison
- Accept/reject workflow

Respects agent mode: Empty when fully manual, populated when copilot/autonomous
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from enum import Enum
import random

from app.db.session import get_sync_db
from app.api import deps
from app.models.user import User
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["recommendations"])  # prefix added in main.py


class AgentMode(str, Enum):
    MANUAL = "manual"
    COPILOT = "copilot"
    AUTONOMOUS = "autonomous"


class RiskStatus(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    HEALTHY = "healthy"


class InventoryRisk(BaseModel):
    """Inventory risk summary for a location/product combination."""
    id: str
    location_name: str
    product_name: str
    status: RiskStatus
    summary_message: str
    current_inventory: int
    min_qty: int
    target_inventory: int
    days_of_supply: int
    projected_inventory: List[int] = Field(description="Projected inventory for next N periods")


class LocationState(BaseModel):
    """State of a single location."""
    name: str
    available: int
    min_qty: int
    target: int
    days_of_cover: int
    projected: List[int]


class BeforeAfterState(BaseModel):
    """Before/after comparison for a recommendation."""
    locations: List[LocationState]


class Recommendation(BaseModel):
    """A resolution recommendation with impact analysis."""
    id: str
    action_title: str
    description: str
    arrival_estimate: Optional[str] = None
    score: int = Field(ge=0, le=100, description="Recommendation score 0-100")
    risk_resolved_pct: int = Field(ge=0, le=100)
    emissions_kg: float = Field(ge=0)
    shipping_cost: float = Field(ge=0)
    before_state: BeforeAfterState
    after_state: BeforeAfterState


class RecommendationsDashboardResponse(BaseModel):
    """Full dashboard response."""
    agent_mode: AgentMode
    inventory_risks: List[InventoryRisk]
    recommendations: List[Recommendation]
    last_updated: datetime


class AcceptRecommendationRequest(BaseModel):
    """Request to accept a recommendation."""
    notes: Optional[str] = None


class AcceptRecommendationResponse(BaseModel):
    """Response after accepting a recommendation."""
    success: bool
    message: str
    recommendation_id: str
    execution_id: Optional[str] = None


class BatchApproveRequest(BaseModel):
    """Request to batch approve/reject recommendations."""
    recommendation_ids: List[str]
    action: str  # 'accepted' or 'rejected'
    reason: Optional[str] = None


class BatchApproveResponse(BaseModel):
    """Response after batch approval."""
    success: bool
    message: str
    processed_count: int
    failed_ids: List[str] = []


@router.get("/dashboard", response_model=RecommendationsDashboardResponse)
def get_recommendations_dashboard(
    config_id: Optional[int] = Query(None, description="Supply chain config ID to filter by"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get the recommended actions dashboard.

    Returns inventory risks and resolution recommendations based on
    the user's agent mode and current supply chain state.

    - Manual mode: Returns empty recommendations (user makes all decisions)
    - Copilot mode: Returns AI recommendations for user approval
    - Autonomous mode: Shows actions taken by AI agents
    """
    # TODO: Get actual agent mode from user/game configuration
    # For now, default to copilot mode
    agent_mode = AgentMode.COPILOT

    # If manual mode, return empty dashboard
    if agent_mode == AgentMode.MANUAL:
        return RecommendationsDashboardResponse(
            agent_mode=agent_mode,
            inventory_risks=[],
            recommendations=[],
            last_updated=datetime.utcnow()
        )

    # TODO: Replace with actual risk detection from inventory data
    # For now, return mock data
    inventory_risks = _generate_mock_inventory_risks(config_id)
    recommendations = _generate_mock_recommendations(inventory_risks)

    return RecommendationsDashboardResponse(
        agent_mode=agent_mode,
        inventory_risks=inventory_risks,
        recommendations=recommendations,
        last_updated=datetime.utcnow()
    )


class ApproveActionRequest(BaseModel):
    """Request to approve/reject a single recommendation."""
    action: str  # 'accepted' or 'rejected'
    reason: Optional[str] = None


@router.post("/{recommendation_id}/approve")
def approve_recommendation_action(
    recommendation_id: str,
    request: ApproveActionRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Approve or reject a recommendation with action and reason.

    Args:
        recommendation_id: ID of the recommendation
        request: Contains action (accepted/rejected) and optional reason
    """
    # TODO: Implement actual recommendation processing
    # 1. Validate recommendation exists
    # 2. Update status based on action
    # 3. If accepted, create appropriate orders
    # 4. Log the action with reason for audit trail

    action_word = "accepted" if request.action == "accepted" else "rejected"
    return {
        "success": True,
        "message": f"Recommendation {recommendation_id} {action_word}",
        "recommendation_id": recommendation_id,
        "action": request.action,
        "reason": request.reason
    }


@router.post("/{recommendation_id}/accept", response_model=AcceptRecommendationResponse)
def accept_recommendation(
    recommendation_id: str,
    request: AcceptRecommendationRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Accept a recommendation and execute the suggested action.

    Creates appropriate orders (transfer orders, purchase orders, etc.)
    based on the recommendation type.
    """
    # TODO: Implement actual recommendation execution
    # 1. Validate recommendation exists and is still valid
    # 2. Create appropriate orders based on recommendation type
    # 3. Update recommendation status
    # 4. Log the action for audit trail

    return AcceptRecommendationResponse(
        success=True,
        message=f"Recommendation {recommendation_id} accepted and queued for execution",
        recommendation_id=recommendation_id,
        execution_id=f"exec-{recommendation_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    )


@router.post("/{recommendation_id}/reject")
def reject_recommendation(
    recommendation_id: str,
    reason: Optional[str] = Query(None, description="Reason for rejection"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Reject a recommendation.

    Records the rejection for learning purposes (improves future recommendations).
    """
    # TODO: Implement rejection tracking for RLHF
    return {
        "success": True,
        "message": f"Recommendation {recommendation_id} rejected",
        "recommendation_id": recommendation_id,
        "reason": reason
    }


@router.post("/batch-approve", response_model=BatchApproveResponse)
def batch_approve_recommendations(
    request: BatchApproveRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Batch approve or reject multiple recommendations at once.

    Args:
        request: Contains list of recommendation IDs, action (accepted/rejected), and optional reason

    Returns:
        Summary of batch operation with success/failure counts
    """
    failed_ids = []
    processed_count = 0

    for rec_id in request.recommendation_ids:
        try:
            # TODO: Implement actual batch processing with database updates
            # For now, simulate success for each recommendation
            processed_count += 1
        except Exception as e:
            failed_ids.append(rec_id)

    action_word = "accepted" if request.action == "accepted" else "rejected"
    return BatchApproveResponse(
        success=len(failed_ids) == 0,
        message=f"Successfully {action_word} {processed_count} recommendations",
        processed_count=processed_count,
        failed_ids=failed_ids
    )


class BatchExecuteRequest(BaseModel):
    """Request to batch execute multiple recommendations."""
    recommendation_ids: List[str]
    notes: Optional[str] = None
    simulate_combined_impact: bool = False  # Run combined Monte Carlo simulation


class BatchExecuteResponse(BaseModel):
    """Response after batch execution."""
    success: bool
    message: str
    executed_count: int
    failed_ids: List[str] = []
    transfer_orders_created: List[str] = []
    combined_impact: Optional[Dict[str, Any]] = None


@router.post("/batch-execute", response_model=BatchExecuteResponse)
def batch_execute_recommendations(
    request: BatchExecuteRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Batch execute multiple approved recommendations.

    This creates transfer orders for all selected recommendations
    and captures execution snapshots for each.

    Features:
    - Atomic execution (all or none)
    - Combined impact simulation
    - Execution snapshots for rollback support
    """
    import uuid

    failed_ids = []
    executed_count = 0
    transfer_orders = []

    for rec_id in request.recommendation_ids:
        try:
            # Get recommendation details
            rec = _get_mock_recommendation_details(rec_id)
            if not rec:
                failed_ids.append(rec_id)
                continue

            # Create transfer order
            to_id = f"TO-{uuid.uuid4().hex[:8].upper()}"
            transfer_orders.append(to_id)

            # In production:
            # 1. Update recommendation status to 'executed'
            # 2. Capture execution snapshot
            # 3. Create actual transfer order in database

            executed_count += 1

        except Exception as e:
            logger.error(f"Failed to execute recommendation {rec_id}: {e}")
            failed_ids.append(rec_id)

    # Calculate combined impact if requested
    combined_impact = None
    if request.simulate_combined_impact and executed_count > 0:
        combined_impact = {
            "total_quantity_transferred": executed_count * 100,  # Mock
            "estimated_total_cost": executed_count * 5000,
            "estimated_service_level_improvement": min(5 * executed_count, 20),  # Cap at 20%
            "estimated_stockout_risk_reduction": min(10 * executed_count, 50),  # Cap at 50%
        }

    success = len(failed_ids) == 0
    logger.info(f"Batch executed {executed_count}/{len(request.recommendation_ids)} recommendations")

    return BatchExecuteResponse(
        success=success,
        message=f"Successfully executed {executed_count} recommendations" if success
                else f"Executed {executed_count} recommendations, {len(failed_ids)} failed",
        executed_count=executed_count,
        failed_ids=failed_ids,
        transfer_orders_created=transfer_orders,
        combined_impact=combined_impact
    )


class BatchRollbackRequest(BaseModel):
    """Request to batch rollback multiple executed recommendations."""
    recommendation_ids: List[str]
    reason: str = Field(..., min_length=1, max_length=500)


class BatchRollbackResponse(BaseModel):
    """Response after batch rollback."""
    success: bool
    message: str
    rolled_back_count: int
    failed_ids: List[str] = []
    rollback_transfer_orders: List[str] = []


@router.post("/batch-rollback", response_model=BatchRollbackResponse)
def batch_rollback_recommendations(
    request: BatchRollbackRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Batch rollback multiple executed recommendations.

    Creates reverse transfer orders for all selected recommendations
    and restores inventory to pre-execution state.
    """
    import uuid

    failed_ids = []
    rolled_back_count = 0
    rollback_orders = []

    for rec_id in request.recommendation_ids:
        try:
            # Validate recommendation exists and was executed
            rec = _get_mock_recommendation_details(rec_id)
            if not rec:
                failed_ids.append(rec_id)
                continue

            # Create reverse transfer order
            rb_to_id = f"TO-RB-{uuid.uuid4().hex[:8].upper()}"
            rollback_orders.append(rb_to_id)

            # In production:
            # 1. Update recommendation status to 'rolled_back'
            # 2. Create reverse transfer order
            # 3. Update rollback tracking fields

            rolled_back_count += 1

        except Exception as e:
            logger.error(f"Failed to rollback recommendation {rec_id}: {e}")
            failed_ids.append(rec_id)

    success = len(failed_ids) == 0
    logger.info(f"Batch rolled back {rolled_back_count}/{len(request.recommendation_ids)} recommendations: {request.reason}")

    return BatchRollbackResponse(
        success=success,
        message=f"Successfully rolled back {rolled_back_count} recommendations" if success
                else f"Rolled back {rolled_back_count} recommendations, {len(failed_ids)} failed",
        rolled_back_count=rolled_back_count,
        failed_ids=failed_ids,
        rollback_transfer_orders=rollback_orders
    )


# ============================================================================
# Execution and Rollback Endpoints
# ============================================================================

class ExecuteRecommendationRequest(BaseModel):
    """Request to execute a recommendation."""
    notes: Optional[str] = None


class ExecuteRecommendationResponse(BaseModel):
    """Response from executing a recommendation."""
    success: bool
    message: str
    recommendation_id: str
    transfer_order_id: Optional[str] = None
    execution_snapshot: Optional[Dict[str, Any]] = None


class RollbackRequest(BaseModel):
    """Request to rollback an executed recommendation."""
    reason: str = Field(..., min_length=1, max_length=500)


class RollbackResponse(BaseModel):
    """Response from rolling back a recommendation."""
    success: bool
    message: str
    recommendation_id: str
    rollback_transfer_order_id: Optional[str] = None
    restored_inventory: Optional[Dict[str, Any]] = None


@router.post("/{recommendation_id}/execute", response_model=ExecuteRecommendationResponse)
def execute_recommendation(
    recommendation_id: str,
    request: ExecuteRecommendationRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Execute an approved recommendation.

    This creates the actual transfer order and records the pre-execution
    state for potential rollback.

    Steps:
    1. Validate recommendation is approved and not already executed
    2. Capture pre-execution inventory snapshot
    3. Create transfer order
    4. Update recommendation status to 'executed'
    5. Return execution details
    """
    import uuid

    # Get recommendation (mock for now)
    # In production: recommendation = db.get(Recommendation, recommendation_id)
    rec = _get_mock_recommendation_details(recommendation_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    # Capture pre-execution snapshot
    execution_snapshot = {
        "captured_at": datetime.utcnow().isoformat(),
        "from_site_inventory": rec.get("current_inventory", 0) + rec.get("transfer_quantity", 0),
        "to_site_inventory": rec.get("current_inventory", 0),
        "transfer_quantity": rec.get("transfer_quantity", 0),
    }

    # Create transfer order (mock)
    transfer_order_id = f"TO-{uuid.uuid4().hex[:8].upper()}"

    # In production, update the database record:
    # recommendation.status = 'executed'
    # recommendation.executed_at = datetime.utcnow()
    # recommendation.executed_by_id = str(current_user.id)
    # recommendation.execution_snapshot = execution_snapshot

    logger.info(f"Recommendation {recommendation_id} executed by user {current_user.id}")

    return ExecuteRecommendationResponse(
        success=True,
        message=f"Recommendation executed. Transfer order {transfer_order_id} created.",
        recommendation_id=recommendation_id,
        transfer_order_id=transfer_order_id,
        execution_snapshot=execution_snapshot
    )


@router.post("/{recommendation_id}/rollback", response_model=RollbackResponse)
def rollback_recommendation(
    recommendation_id: str,
    request: RollbackRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Rollback an executed recommendation.

    This creates a reverse transfer order to undo the original action
    and restores inventory to the pre-execution state.

    Steps:
    1. Validate recommendation was executed and not already rolled back
    2. Retrieve execution snapshot
    3. Create reverse transfer order
    4. Update recommendation status to 'rolled_back'
    5. Record rollback details for audit
    """
    import uuid

    # Get recommendation (mock for now)
    rec = _get_mock_recommendation_details(recommendation_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    # Simulate checking execution status
    # In production: if recommendation.status != 'executed' or recommendation.is_rolled_back

    # Create reverse transfer order
    rollback_to_id = f"TO-RB-{uuid.uuid4().hex[:8].upper()}"

    # Calculate restored inventory
    restored_inventory = {
        "from_site_id": rec.get("from_site_id", "SITE-ATL"),
        "from_site_restored_qty": rec.get("transfer_quantity", 0),
        "to_site_id": rec.get("to_site_id", "SITE-CHI"),
        "to_site_reduced_qty": rec.get("transfer_quantity", 0),
    }

    # In production, update the database record:
    # recommendation.is_rolled_back = True
    # recommendation.rolled_back_at = datetime.utcnow()
    # recommendation.rolled_back_by_id = str(current_user.id)
    # recommendation.rollback_reason = request.reason
    # recommendation.rollback_transfer_order_id = rollback_to_id
    # recommendation.status = 'rolled_back'

    logger.info(f"Recommendation {recommendation_id} rolled back by user {current_user.id}: {request.reason}")

    return RollbackResponse(
        success=True,
        message=f"Recommendation rolled back. Reverse transfer order {rollback_to_id} created.",
        recommendation_id=recommendation_id,
        rollback_transfer_order_id=rollback_to_id,
        restored_inventory=restored_inventory
    )


@router.get("/{recommendation_id}/execution-history")
def get_execution_history(
    recommendation_id: str,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get the execution and rollback history for a recommendation.

    Returns timeline of all actions taken on this recommendation.
    """
    # Mock implementation
    return {
        "recommendation_id": recommendation_id,
        "events": [
            {
                "event_type": "created",
                "timestamp": "2026-01-28T10:00:00Z",
                "user_id": "user-1",
                "details": {"total_score": 85.5}
            },
            {
                "event_type": "approved",
                "timestamp": "2026-01-28T14:30:00Z",
                "user_id": "user-2",
                "details": {"reason": "High urgency - stockout risk"}
            },
            {
                "event_type": "executed",
                "timestamp": "2026-01-28T15:00:00Z",
                "user_id": "user-2",
                "details": {
                    "transfer_order_id": "TO-ABC123",
                    "snapshot": {"from_site_inventory": 5000, "to_site_inventory": 500}
                }
            }
        ]
    }


@router.get("/history")
def get_recommendation_history(
    status: Optional[str] = Query(None, description="Filter by status: accepted, rejected, expired"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get history of past recommendations and their outcomes.
    """
    # TODO: Implement recommendation history from database
    return {
        "recommendations": [],
        "total": 0,
        "limit": limit
    }


# ============================================================================
# Impact Simulation Endpoints
# ============================================================================

class SimulationScenario(BaseModel):
    """A single simulation scenario result."""
    scenario_id: int
    total_cost: float
    service_level: float
    stockout_days: int
    inventory_turns: float


class SimulationResult(BaseModel):
    """Monte Carlo simulation result."""
    scenarios_run: int
    computation_time_ms: float

    # Without recommendation (baseline)
    baseline_cost_p10: float
    baseline_cost_p50: float
    baseline_cost_p90: float
    baseline_service_level_avg: float
    baseline_stockout_probability: float

    # With recommendation applied
    with_rec_cost_p10: float
    with_rec_cost_p50: float
    with_rec_cost_p90: float
    with_rec_service_level_avg: float
    with_rec_stockout_probability: float

    # Impact metrics
    cost_reduction_expected: float
    cost_reduction_pct: float
    service_level_improvement: float
    stockout_reduction_pct: float
    confidence_level: float


class SimulateRequest(BaseModel):
    """Request to simulate recommendation impact."""
    scenarios: int = Field(1000, ge=100, le=10000, description="Number of Monte Carlo scenarios")
    planning_horizon_days: int = Field(14, ge=1, le=90)
    demand_cv: float = Field(0.2, ge=0.05, le=0.5, description="Demand coefficient of variation")
    lead_time_cv: float = Field(0.1, ge=0, le=0.3, description="Lead time coefficient of variation")


@router.post("/{recommendation_id}/simulate", response_model=SimulationResult)
def simulate_recommendation_impact(
    recommendation_id: str,
    request: SimulateRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Run Monte Carlo simulation to assess recommendation impact.

    Simulates supply chain dynamics with and without the recommendation
    applied, using stochastic demand and lead time variability.

    Returns:
        SimulationResult with percentile distributions and impact metrics
    """
    import time
    import numpy as np
    start_time = time.time()

    # Get recommendation details (mock for now)
    # In production, fetch from database based on recommendation_id
    rec = _get_mock_recommendation_details(recommendation_id)

    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    # Run Monte Carlo simulation
    np.random.seed(42)  # For reproducibility in demo

    baseline_costs = []
    baseline_service_levels = []
    baseline_stockouts = []

    with_rec_costs = []
    with_rec_service_levels = []
    with_rec_stockouts = []

    # Base parameters
    base_demand = 100  # Units per day
    base_lead_time = 3  # Days
    holding_cost = 0.5  # Per unit per day
    stockout_cost = 10  # Per unit

    for scenario in range(request.scenarios):
        # Generate stochastic demand for planning horizon
        daily_demand = np.random.normal(
            base_demand,
            base_demand * request.demand_cv,
            request.planning_horizon_days
        )
        daily_demand = np.maximum(daily_demand, 0)  # No negative demand

        lead_time = max(1, int(np.random.normal(
            base_lead_time,
            base_lead_time * request.lead_time_cv
        )))

        # Simulate WITHOUT recommendation (baseline)
        inventory = rec.get('current_inventory', 950)
        total_cost_baseline = 0
        stockout_days_baseline = 0

        for day in range(request.planning_horizon_days):
            demand = daily_demand[day]
            if inventory >= demand:
                inventory -= demand
            else:
                stockout_days_baseline += 1
                total_cost_baseline += (demand - inventory) * stockout_cost
                inventory = 0
            total_cost_baseline += inventory * holding_cost

        baseline_costs.append(total_cost_baseline)
        baseline_service_levels.append(
            (request.planning_horizon_days - stockout_days_baseline) / request.planning_horizon_days * 100
        )
        baseline_stockouts.append(stockout_days_baseline > 0)

        # Simulate WITH recommendation applied
        inventory = rec.get('current_inventory', 950) + rec.get('transfer_quantity', 3000)
        total_cost_with_rec = rec.get('shipping_cost', 12234)  # Include shipping cost
        stockout_days_with_rec = 0

        for day in range(request.planning_horizon_days):
            demand = daily_demand[day]
            if inventory >= demand:
                inventory -= demand
            else:
                stockout_days_with_rec += 1
                total_cost_with_rec += (demand - inventory) * stockout_cost
                inventory = 0
            total_cost_with_rec += inventory * holding_cost

        with_rec_costs.append(total_cost_with_rec)
        with_rec_service_levels.append(
            (request.planning_horizon_days - stockout_days_with_rec) / request.planning_horizon_days * 100
        )
        with_rec_stockouts.append(stockout_days_with_rec > 0)

    # Calculate statistics
    baseline_cost_p10 = float(np.percentile(baseline_costs, 10))
    baseline_cost_p50 = float(np.percentile(baseline_costs, 50))
    baseline_cost_p90 = float(np.percentile(baseline_costs, 90))
    baseline_service_avg = float(np.mean(baseline_service_levels))
    baseline_stockout_prob = float(np.mean(baseline_stockouts) * 100)

    with_rec_cost_p10 = float(np.percentile(with_rec_costs, 10))
    with_rec_cost_p50 = float(np.percentile(with_rec_costs, 50))
    with_rec_cost_p90 = float(np.percentile(with_rec_costs, 90))
    with_rec_service_avg = float(np.mean(with_rec_service_levels))
    with_rec_stockout_prob = float(np.mean(with_rec_stockouts) * 100)

    # Calculate impact
    cost_reduction = baseline_cost_p50 - with_rec_cost_p50
    cost_reduction_pct = (cost_reduction / baseline_cost_p50) * 100 if baseline_cost_p50 > 0 else 0
    service_improvement = with_rec_service_avg - baseline_service_avg
    stockout_reduction = baseline_stockout_prob - with_rec_stockout_prob

    # Calculate confidence (based on variance reduction)
    baseline_var = np.var(baseline_costs)
    combined_var = np.var(with_rec_costs)
    confidence = min(95, 80 + (baseline_var - combined_var) / max(baseline_var, 1) * 15)

    computation_time = (time.time() - start_time) * 1000

    return SimulationResult(
        scenarios_run=request.scenarios,
        computation_time_ms=round(computation_time, 2),

        baseline_cost_p10=round(baseline_cost_p10, 2),
        baseline_cost_p50=round(baseline_cost_p50, 2),
        baseline_cost_p90=round(baseline_cost_p90, 2),
        baseline_service_level_avg=round(baseline_service_avg, 2),
        baseline_stockout_probability=round(baseline_stockout_prob, 2),

        with_rec_cost_p10=round(with_rec_cost_p10, 2),
        with_rec_cost_p50=round(with_rec_cost_p50, 2),
        with_rec_cost_p90=round(with_rec_cost_p90, 2),
        with_rec_service_level_avg=round(with_rec_service_avg, 2),
        with_rec_stockout_probability=round(with_rec_stockout_prob, 2),

        cost_reduction_expected=round(cost_reduction, 2),
        cost_reduction_pct=round(cost_reduction_pct, 2),
        service_level_improvement=round(service_improvement, 2),
        stockout_reduction_pct=round(stockout_reduction, 2),
        confidence_level=round(confidence, 2)
    )


def _get_mock_recommendation_details(recommendation_id: str) -> Optional[Dict[str, Any]]:
    """Get recommendation details (mock for development)."""
    mock_recommendations = {
        "rec-1": {
            "id": "rec-1",
            "action": "Transfer inventory from Alabama DC",
            "current_inventory": 950,
            "transfer_quantity": 3000,
            "shipping_cost": 12234,
            "lead_time_days": 3
        },
        "rec-2": {
            "id": "rec-2",
            "action": "Expedite supplier shipment",
            "current_inventory": 950,
            "transfer_quantity": 2000,
            "shipping_cost": 8500,
            "lead_time_days": 5
        },
        "rec-3": {
            "id": "rec-3",
            "action": "Adjust safety stock policy",
            "current_inventory": 950,
            "transfer_quantity": 0,
            "shipping_cost": 0,
            "lead_time_days": 0
        }
    }
    return mock_recommendations.get(recommendation_id)


# Mock data generation functions
def _generate_mock_inventory_risks(config_id: Optional[int]) -> List[InventoryRisk]:
    """Generate mock inventory risks for development."""
    risks = [
        InventoryRisk(
            id="risk-1",
            location_name="Atlanta Distribution Center",
            product_name="Brake Pads - Premium",
            status=RiskStatus.CRITICAL,
            summary_message="At risk of stocking out in 3 days which will result in a shortage of 3,000 units / 31%",
            current_inventory=950,
            min_qty=300,
            target_inventory=1500,
            days_of_supply=2,
            projected_inventory=[950, 700, 400, 200, 0, 0, 0, 0, 100, 300, 500, 700]
        ),
        InventoryRisk(
            id="risk-2",
            location_name="Denver Warehouse",
            product_name="Oil Filter - Standard",
            status=RiskStatus.WARNING,
            summary_message="Inventory below target levels, may impact fulfillment in 7 days",
            current_inventory=2400,
            min_qty=1000,
            target_inventory=4000,
            days_of_supply=8,
            projected_inventory=[2400, 2200, 2000, 1800, 1600, 1400, 1200, 1000, 1200, 1400, 1600, 1800]
        )
    ]
    return risks


def _generate_mock_recommendations(risks: List[InventoryRisk]) -> List[Recommendation]:
    """Generate mock recommendations based on detected risks."""
    if not risks:
        return []

    recommendations = [
        Recommendation(
            id="rec-1",
            action_title="Move 3,000 units from Alabama DC",
            description="Transfer inventory from Alabama Distribution Center which has excess stock",
            arrival_estimate="3 days",
            score=86,
            risk_resolved_pct=91,
            emissions_kg=46.8,
            shipping_cost=12234,
            before_state=BeforeAfterState(
                locations=[
                    LocationState(
                        name="Atlanta DC",
                        available=950,
                        min_qty=300,
                        target=1500,
                        days_of_cover=2,
                        projected=[950, 700, 400, 200, 0, 0, 0, 0]
                    ),
                    LocationState(
                        name="Alabama DC",
                        available=7000,
                        min_qty=500,
                        target=3000,
                        days_of_cover=14,
                        projected=[7000, 6500, 6000, 5500, 5000, 4500, 4000, 3500]
                    )
                ]
            ),
            after_state=BeforeAfterState(
                locations=[
                    LocationState(
                        name="Atlanta DC",
                        available=3950,
                        min_qty=300,
                        target=1500,
                        days_of_cover=9,
                        projected=[950, 700, 3700, 3500, 3300, 3100, 2900, 2700]
                    ),
                    LocationState(
                        name="Alabama DC",
                        available=4000,
                        min_qty=500,
                        target=3000,
                        days_of_cover=8,
                        projected=[7000, 6500, 3000, 2500, 2000, 1500, 1000, 500]
                    )
                ]
            )
        ),
        Recommendation(
            id="rec-2",
            action_title="Expedite supplier shipment",
            description="Request expedited delivery from primary supplier for incoming PO-2024-1234",
            arrival_estimate="5 days",
            score=72,
            risk_resolved_pct=78,
            emissions_kg=82.5,
            shipping_cost=8500,
            before_state=BeforeAfterState(
                locations=[
                    LocationState(
                        name="Atlanta DC",
                        available=950,
                        min_qty=300,
                        target=1500,
                        days_of_cover=2,
                        projected=[950, 700, 400, 200, 0, 0, 0, 0]
                    )
                ]
            ),
            after_state=BeforeAfterState(
                locations=[
                    LocationState(
                        name="Atlanta DC",
                        available=950,
                        min_qty=300,
                        target=1500,
                        days_of_cover=7,
                        projected=[950, 700, 400, 200, 100, 2100, 2000, 1900]
                    )
                ]
            )
        ),
        Recommendation(
            id="rec-3",
            action_title="Adjust safety stock policy",
            description="Temporarily reduce safety stock at Atlanta DC to extend coverage while awaiting replenishment",
            arrival_estimate="Immediate",
            score=58,
            risk_resolved_pct=45,
            emissions_kg=0,
            shipping_cost=0,
            before_state=BeforeAfterState(
                locations=[
                    LocationState(
                        name="Atlanta DC",
                        available=950,
                        min_qty=300,
                        target=1500,
                        days_of_cover=2,
                        projected=[950, 700, 400, 200, 0, 0, 0, 0]
                    )
                ]
            ),
            after_state=BeforeAfterState(
                locations=[
                    LocationState(
                        name="Atlanta DC",
                        available=950,
                        min_qty=150,
                        target=1000,
                        days_of_cover=4,
                        projected=[950, 700, 400, 200, 100, 50, 25, 0]
                    )
                ]
            )
        )
    ]

    return recommendations
