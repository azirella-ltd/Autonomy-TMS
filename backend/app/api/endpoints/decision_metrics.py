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
- GET /override-effectiveness: Override effectiveness metrics for executive dashboard
- GET /override-posteriors: Bayesian posteriors for override effectiveness by (user, trm_type)
"""

from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.agent_performance_service import AgentPerformanceService
from app.services.override_effectiveness_service import (
    OverrideEffectivenessService, TIER_MAP,
)


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

    # Use user's customer if they have one, otherwise use demo customer ID
    customer_id = current_user.customer_id or 1

    data = service.get_executive_dashboard_data(customer_id, planning_cycle)

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
    customer_id = current_user.customer_id or 1

    exec_data = service.get_executive_dashboard_data(customer_id, planning_cycle)

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
    customer_id = current_user.customer_id or 1

    items = service.get_sop_worklist_items(customer_id, status, category)
    summary = service.get_sop_worklist_summary(customer_id)

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
    customer_id = current_user.customer_id or 1

    summary = service.get_sop_worklist_summary(customer_id)

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

    customer_id = current_user.customer_id or 1

    query = db.query(AgentDecision).filter(AgentDecision.customer_id == customer_id)

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


# =============================================================================
# Override Effectiveness (Executive Dashboard)
# =============================================================================

@router.get("/override-effectiveness")
async def get_override_effectiveness(
    days: int = Query(default=90, ge=7, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get override effectiveness metrics for the executive dashboard.

    Aggregates across all sites for the customer, showing whether
    human overrides are adding value or creating friction.
    """
    from app.models.powell_decision import SiteAgentDecision

    customer_id = current_user.customer_id or 1
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)

    # We can't filter SiteAgentDecision by customer_id directly (it uses site_key),
    # so we aggregate across all sites for now.
    base_q = db.query(SiteAgentDecision).filter(
        SiteAgentDecision.is_overridden == True,
        SiteAgentDecision.timestamp > cutoff,
    )

    total_overrides = base_q.count()

    classified = base_q.filter(SiteAgentDecision.override_classification.isnot(None))
    beneficial = classified.filter(SiteAgentDecision.override_classification == "BENEFICIAL").count()
    neutral = classified.filter(SiteAgentDecision.override_classification == "NEUTRAL").count()
    detrimental = classified.filter(SiteAgentDecision.override_classification == "DETRIMENTAL").count()
    classified_total = beneficial + neutral + detrimental
    pending = total_overrides - classified_total

    effectiveness_rate = (beneficial / classified_total * 100) if classified_total > 0 else 0.0

    net_delta = db.query(func.sum(SiteAgentDecision.override_delta)).filter(
        SiteAgentDecision.is_overridden == True,
        SiteAgentDecision.override_delta.isnot(None),
        SiteAgentDecision.timestamp > cutoff,
    ).scalar() or 0.0

    # By TRM type
    type_rows = db.query(
        SiteAgentDecision.decision_type,
        func.count(SiteAgentDecision.id).label("count"),
        func.sum(case(
            (SiteAgentDecision.override_classification == "BENEFICIAL", 1), else_=0
        )).label("beneficial"),
        func.sum(case(
            (SiteAgentDecision.override_classification == "NEUTRAL", 1), else_=0
        )).label("neutral"),
        func.sum(case(
            (SiteAgentDecision.override_classification == "DETRIMENTAL", 1), else_=0
        )).label("detrimental"),
        func.coalesce(func.sum(SiteAgentDecision.override_delta), 0.0).label("net_delta"),
    ).filter(
        SiteAgentDecision.is_overridden == True,
        SiteAgentDecision.timestamp > cutoff,
    ).group_by(SiteAgentDecision.decision_type).all()

    by_trm_type = {}
    for row in type_rows:
        ct = int(row.beneficial or 0) + int(row.neutral or 0) + int(row.detrimental or 0)
        by_trm_type[row.decision_type] = {
            "total": row.count,
            "beneficial": int(row.beneficial or 0),
            "neutral": int(row.neutral or 0),
            "detrimental": int(row.detrimental or 0),
            "effectiveness_rate": (int(row.beneficial or 0) / ct * 100) if ct > 0 else 0.0,
            "net_delta": float(row.net_delta),
        }

    # Weekly trend
    trend_rows = db.query(
        func.date_trunc("week", SiteAgentDecision.timestamp).label("week"),
        func.count(SiteAgentDecision.id).label("count"),
        func.sum(case(
            (SiteAgentDecision.override_classification == "BENEFICIAL", 1), else_=0
        )).label("beneficial"),
        func.sum(case(
            (SiteAgentDecision.override_classification == "NEUTRAL", 1), else_=0
        )).label("neutral"),
        func.sum(case(
            (SiteAgentDecision.override_classification == "DETRIMENTAL", 1), else_=0
        )).label("detrimental"),
    ).filter(
        SiteAgentDecision.is_overridden == True,
        SiteAgentDecision.timestamp > cutoff,
    ).group_by("week").order_by("week").all()

    trend = []
    for row in trend_rows:
        ct = int(row.beneficial or 0) + int(row.neutral or 0) + int(row.detrimental or 0)
        trend.append({
            "week": row.week.isoformat() if row.week else None,
            "total": row.count,
            "beneficial": int(row.beneficial or 0),
            "neutral": int(row.neutral or 0),
            "detrimental": int(row.detrimental or 0),
            "effectiveness_rate": (int(row.beneficial or 0) / ct * 100) if ct > 0 else 0.0,
        })

    # Recent overrides for the "examples" section
    recent_beneficial = db.query(SiteAgentDecision).filter(
        SiteAgentDecision.is_overridden == True,
        SiteAgentDecision.override_classification == "BENEFICIAL",
        SiteAgentDecision.timestamp > cutoff,
    ).order_by(SiteAgentDecision.override_delta.desc()).limit(5).all()

    recent_detrimental = db.query(SiteAgentDecision).filter(
        SiteAgentDecision.is_overridden == True,
        SiteAgentDecision.override_classification == "DETRIMENTAL",
        SiteAgentDecision.timestamp > cutoff,
    ).order_by(SiteAgentDecision.override_delta.asc()).limit(5).all()

    def _decision_summary(d):
        return {
            "decision_id": d.decision_id,
            "site_key": d.site_key,
            "decision_type": d.decision_type,
            "override_delta": d.override_delta,
            "agent_counterfactual_reward": d.agent_counterfactual_reward,
            "human_actual_reward": d.human_actual_reward,
            "override_reason": d.override_reason_text,
            "timestamp": d.timestamp.isoformat() if d.timestamp else None,
        }

    # Enrich by_trm_type with observability tier
    for trm_type_key, data in by_trm_type.items():
        data["tier"] = TIER_MAP.get(trm_type_key, 3)

    return {
        "success": True,
        "data": {
            "effectiveness_rate": effectiveness_rate,
            "net_reward_delta": float(net_delta),
            "total_overrides": total_overrides,
            "beneficial_count": beneficial,
            "neutral_count": neutral,
            "detrimental_count": detrimental,
            "pending_count": pending,
            "by_trm_type": by_trm_type,
            "trend": trend,
            "top_beneficial": [_decision_summary(d) for d in recent_beneficial],
            "top_detrimental": [_decision_summary(d) for d in recent_detrimental],
        },
    }


# =============================================================================
# Bayesian Override Posteriors
# =============================================================================

@router.get("/override-posteriors")
async def get_override_posteriors(
    trm_type: Optional[str] = Query(None, description="Filter by TRM type"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get Bayesian posteriors for override effectiveness.

    Returns per-(user, trm_type) Beta posteriors with credible intervals.
    Used by the Override Effectiveness dashboard to show confidence-aware metrics.
    """
    from app.models.override_effectiveness import OverrideEffectivenessPosterior
    from app.models.user import User as UserModel

    query = db.query(OverrideEffectivenessPosterior)
    if trm_type:
        query = query.filter(OverrideEffectivenessPosterior.trm_type == trm_type)

    posteriors = query.order_by(
        OverrideEffectivenessPosterior.observation_count.desc(),
    ).limit(200).all()

    # Enrich with user names and credible intervals
    results = []
    for p in posteriors:
        user = db.query(UserModel).filter(UserModel.id == p.user_id).first()
        ci = OverrideEffectivenessService.get_credible_interval(p)

        results.append({
            **p.to_dict(),
            "user_name": user.name if user else f"User {p.user_id}",
            "user_email": user.email if user else None,
            "credible_interval": ci,
            "tier": TIER_MAP.get(p.trm_type, 3),
        })

    # Aggregate stats
    aggregate = OverrideEffectivenessService.get_aggregate_stats(db, trm_type)

    return {
        "success": True,
        "posteriors": results,
        "aggregate": aggregate,
        "tier_map": {k: v for k, v in TIER_MAP.items()},
    }


# =============================================================================
# Causal Matching Stats
# =============================================================================

@router.get("/causal-matching-stats")
async def get_causal_matching_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get causal matching statistics — propensity-score matched pairs
    for Tier 2 override effectiveness.

    Shows how many matched pairs exist, quality distribution, and
    average treatment effects by TRM type.
    """
    from app.services.causal_matching_service import CausalMatchingService

    service = CausalMatchingService(db)
    stats = service.get_matching_stats()

    return {
        "success": True,
        "data": stats,
    }
