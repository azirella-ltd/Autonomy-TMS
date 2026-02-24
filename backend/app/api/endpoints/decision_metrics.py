"""
Decision Metrics API Endpoints

Provides Agent Performance and Human Override metrics
for the Powell Framework demonstration dashboards.

Endpoints:
- GET /executive-dashboard: Executive dashboard data for SC_VP
- GET /agent-performance: Agent performance data for SOP_DIRECTOR
- GET /sop-worklist: S&OP worklist items
- POST /sop-worklist/{id}/resolve: Resolve a worklist item
- GET /sop-worklist/{id}/reasoning: Get agent reasoning ("Ask Why")
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.agent_performance_service import AgentPerformanceService


router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class WorklistResolveRequest(BaseModel):
    """Request to resolve a worklist item."""
    action: str  # "accept" or "reject"
    notes: Optional[str] = None


class WorklistResolveResponse(BaseModel):
    """Response after resolving a worklist item."""
    success: bool
    item: dict
    message: str


# =============================================================================
# Executive Dashboard (SC_VP)
# =============================================================================

@router.get("/executive-dashboard")
async def get_executive_dashboard(
    planning_cycle: Optional[str] = Query(None, description="Planning cycle (e.g., 'Q3 2025')"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get executive dashboard data for SC_VP.

    Returns:
    - Summary KPIs (autonomous decisions %, active agents/planners, performance scores)
    - Trend data over time
    - ROI metrics
    - Category breakdown
    - Key insights
    """
    service = AgentPerformanceService(db)

    # Use user's group if they have one, otherwise use demo group ID
    group_id = current_user.group_id or 1

    data = service.get_executive_dashboard_data(group_id, planning_cycle)

    return {
        "success": True,
        "data": data,
        "planning_cycle": planning_cycle or "Q3 2025",
    }


# =============================================================================
# Agent Performance (SOP_DIRECTOR drill-down)
# =============================================================================

@router.get("/agent-performance")
async def get_agent_performance(
    planning_cycle: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed agent performance metrics.

    Returns:
    - Performance score trends over time (planner vs agent)
    - Human override rate trends
    - Planner capacity metrics
    - Category-level breakdown
    """
    service = AgentPerformanceService(db)
    group_id = current_user.group_id or 1

    exec_data = service.get_executive_dashboard_data(group_id, planning_cycle)

    # Add decision performance specific data
    return {
        "success": True,
        "data": {
            "summary": exec_data["summary"],
            "trends": exec_data["trends"],
            "categories": exec_data.get("categories", []),
            "planner_capacity": {
                "active_planners": exec_data["summary"]["active_planners"],
                "from_planners": 25,
                "skus_per_planner": 972,
                "efficiency_gain_pct": 94,
                "agent_automation_pct": exec_data["summary"]["autonomous_decisions_pct"],
            },
            "key_events": [
                {"date": "Aug '24", "event": "Go-Live", "description": "AI agent deployment begins with 25 planners"},
                {"date": "Dec '24", "event": "RIF #1 (-3)", "description": "20% automation achieved, headcount 25→22"},
                {"date": "Feb '25", "event": "RIF #2 + NPI #1", "description": "52% automation + 2,500 new SKUs, headcount 22→20"},
                {"date": "Apr '25", "event": "RIF #3 + NPI #2", "description": "74% automation + 2,500 new SKUs, headcount 20→18"},
            ],
        },
        "planning_cycle": planning_cycle or "Q3 2025",
    }


# =============================================================================
# S&OP Worklist
# =============================================================================

@router.get("/sop-worklist")
async def get_sop_worklist(
    status: Optional[str] = Query(None, description="Filter by status: pending, accepted, rejected"),
    category: Optional[str] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get S&OP worklist items.

    Returns worklist items with issues, impacts, and due dates.
    """
    service = AgentPerformanceService(db)
    group_id = current_user.group_id or 1

    items = service.get_sop_worklist_items(group_id, status, category)
    summary = service.get_sop_worklist_summary(group_id)

    return {
        "success": True,
        "summary": summary,
        "items": items,
        "filters": {
            "status": status,
            "category": category,
        },
    }


@router.get("/sop-worklist/summary")
async def get_sop_worklist_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get just the S&OP worklist summary KPIs."""
    service = AgentPerformanceService(db)
    group_id = current_user.group_id or 1

    summary = service.get_sop_worklist_summary(group_id)

    return {
        "success": True,
        "data": summary,
    }


@router.post("/sop-worklist/{item_id}/resolve")
async def resolve_worklist_item(
    item_id: int,
    request: WorklistResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Resolve a worklist item (accept or reject).

    For copilot mode, this records the user's decision on the agent recommendation.
    """
    if request.action not in ["accept", "reject"]:
        raise HTTPException(
            status_code=400,
            detail="Action must be 'accept' or 'reject'"
        )

    service = AgentPerformanceService(db)

    try:
        item = service.resolve_worklist_item(
            item_id=item_id,
            user_id=current_user.id,
            action=request.action,
            notes=request.notes,
        )

        return WorklistResolveResponse(
            success=True,
            item=item,
            message=f"Item {request.action}ed successfully",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/sop-worklist/{item_id}/reasoning")
async def get_agent_reasoning(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed agent reasoning for a worklist item ("Ask Why" functionality).

    Returns the agent's reasoning, confidence, and supporting data.
    """
    service = AgentPerformanceService(db)

    try:
        reasoning = service.get_agent_reasoning(item_id)

        return {
            "success": True,
            "item_id": item_id,
            "data": reasoning,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# Agent Decisions (for mps_manager operational view)
# =============================================================================

@router.get("/agent-decisions")
async def get_agent_decisions(
    decision_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get recent agent decisions for operational review.

    Used by MPS_MANAGER to see what the TRM agents are deciding.
    """
    from app.models.decision_tracking import AgentDecision, DecisionStatus

    group_id = current_user.group_id or 1

    query = db.query(AgentDecision).filter(AgentDecision.group_id == group_id)

    if decision_type:
        query = query.filter(AgentDecision.decision_type == decision_type)

    if status:
        query = query.filter(AgentDecision.status == status)

    decisions = query.order_by(AgentDecision.created_at.desc()).limit(limit).all()

    return {
        "success": True,
        "decisions": [d.to_dict() for d in decisions],
        "count": len(decisions),
    }
