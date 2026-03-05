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

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    data = service.get_executive_dashboard_data(tenant_id, planning_cycle)

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
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    exec_data = service.get_executive_dashboard_data(tenant_id, planning_cycle)

    # Add decision performance specific data
    # Compute planner capacity from PerformanceMetric history
    from app.models.decision_tracking import PerformanceMetric as PM
    from sqlalchemy import asc as _asc

    pm_rows = (
        db.query(PM)
        .filter(PM.tenant_id == tenant_id, PM.category.is_(None))
        .order_by(_asc(PM.period_start))
        .all()
    )

    earliest = pm_rows[0] if pm_rows else None
    latest_pm = pm_rows[-1] if pm_rows else None

    from_planners = int(earliest.active_planners) if earliest and earliest.active_planners else None
    current_planners = exec_data["summary"].get("active_planners")
    skus_per_planner = (
        round(float(latest_pm.skus_per_planner), 1)
        if latest_pm and latest_pm.skus_per_planner and float(latest_pm.skus_per_planner) > 0
        else None
    )
    efficiency_gain_pct = (
        round((from_planners - current_planners) / from_planners * 100)
        if from_planners and current_planners and from_planners > current_planners
        else None
    )

    # Build key_events from periods when planner count decreased
    key_events = []
    if len(pm_rows) > 1:
        _MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        prev_planners = None
        for pm in pm_rows:
            if pm.active_planners is None:
                continue
            curr = int(pm.active_planners)
            mo = pm.period_start.month
            yr = pm.period_start.year
            date_label = f"{_MONTH_ABBR[mo - 1]} '{str(yr)[2:]}"
            if prev_planners is None:
                key_events.append({
                    "date": date_label,
                    "event": "Go-Live",
                    "description": f"AI agent deployment begins with {curr} planners",
                })
            elif curr < prev_planners:
                reduction = prev_planners - curr
                key_events.append({
                    "date": date_label,
                    "event": f"Reduction (-{reduction})",
                    "description": (
                        f"{round(pm.automation_percentage or 0)}% automation achieved, "
                        f"headcount {prev_planners}→{curr}"
                    ),
                })
            prev_planners = curr
        key_events = key_events[:6]  # cap at 6 events

    return {
        "success": True,
        "data": {
            "summary": exec_data["summary"],
            "trends": exec_data["trends"],
            "categories": exec_data.get("categories", []),
            "planner_capacity": {
                "active_planners": current_planners,
                "from_planners": from_planners,
                "skus_per_planner": skus_per_planner,
                "efficiency_gain_pct": efficiency_gain_pct,
                "agent_automation_pct": exec_data["summary"]["autonomous_decisions_pct"],
            },
            "key_events": key_events,
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
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    items = service.get_sop_worklist_items(tenant_id, status, category)
    summary = service.get_sop_worklist_summary(tenant_id)

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
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    summary = service.get_sop_worklist_summary(tenant_id)

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

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    query = db.query(AgentDecision).filter(AgentDecision.tenant_id == tenant_id)

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

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)

    # TODO: Filter SiteAgentDecision by tenant's sites once site_key→tenant mapping is available
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


# =============================================================================
# Gartner SCOR Metric Hierarchy
# =============================================================================

@router.get("/metrics/hierarchy")
async def get_metrics_hierarchy(
    current_user: User = Depends(get_current_user),
):
    """
    Return the full Gartner SCOR metric hierarchy.

    Includes all defined metric codes with name, level (L1–L4), unit,
    direction (higher_is_better), SCOR process category, and description.

    Use to drive the metric selector UI and populate metric definitions.
    """
    from app.models.metrics_hierarchy import GARTNER_METRICS, TRM_METRIC_MAPPING, POWELL_LAYER_METRICS

    metrics = {
        code: {
            "code": defn.code,
            "name": defn.name,
            "level": defn.level.value,
            "unit": defn.unit,
            "higher_is_better": defn.higher_is_better,
            "description": defn.description,
            "scor_process": defn.scor_process,
        }
        for code, defn in GARTNER_METRICS.items()
    }

    return {
        "success": True,
        "data": {
            "metrics": metrics,
            "trm_metric_mapping": TRM_METRIC_MAPPING,
            "powell_layer_defaults": POWELL_LAYER_METRICS,
            "total_metrics": len(metrics),
        },
    }


@router.get("/metrics/config/{config_id}")
async def get_metrics_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return the resolved MetricConfig for a supply chain config.

    Merges per-config overrides (stored in SupplyChainConfig.metric_config)
    on top of Gartner SCOR defaults.  Returns defaults if no overrides are set.
    """
    from app.models.supply_chain_config import SupplyChainConfig
    from app.models.metrics_hierarchy import get_metric_config

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == config_id,
        SupplyChainConfig.tenant_id == tenant_id,
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail=f"Supply chain config {config_id} not found.")

    mc = get_metric_config(getattr(config, "metric_config", None))
    return {
        "success": True,
        "config_id": config_id,
        "data": mc.to_dict(),
    }


class MetricConfigPatch(BaseModel):
    sop_weights: Optional[Dict[str, float]] = None
    tgnn_weights: Optional[Dict[str, float]] = None
    trm_weights: Optional[Dict[str, Dict[str, float]]] = None


@router.patch("/metrics/config/{config_id}")
async def patch_metrics_config(
    config_id: int,
    body: MetricConfigPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update the Gartner SCOR metric config overrides for a supply chain config.

    Only the keys present in the request body are updated; others retain
    their current values.  Weights for each layer are validated to sum to 1.0
    (within a tolerance of 0.01).
    """
    from app.models.supply_chain_config import SupplyChainConfig
    from app.models.metrics_hierarchy import get_metric_config, GARTNER_METRICS

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == config_id,
        SupplyChainConfig.tenant_id == tenant_id,
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail=f"Supply chain config {config_id} not found.")

    # Load existing overrides (or start from empty)
    existing = dict(getattr(config, "metric_config", None) or {})

    def _validate_weights(weights: Dict[str, float], layer: str) -> None:
        for code in weights:
            if code not in GARTNER_METRICS:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown metric code '{code}' in {layer}_weights. "
                           f"Valid codes: {sorted(GARTNER_METRICS.keys())}",
                )
        total = sum(weights.values())
        if abs(total - 1.0) > 0.01:
            raise HTTPException(
                status_code=422,
                detail=f"{layer}_weights sum to {total:.4f}; must sum to 1.0 (±0.01).",
            )

    if body.sop_weights is not None:
        _validate_weights(body.sop_weights, "sop")
        existing["sop_weights"] = body.sop_weights

    if body.tgnn_weights is not None:
        _validate_weights(body.tgnn_weights, "tgnn")
        existing["tgnn_weights"] = body.tgnn_weights

    if body.trm_weights is not None:
        for trm_type, weights in body.trm_weights.items():
            _validate_weights(weights, f"trm[{trm_type}]")
        trm = dict(existing.get("trm_weights") or {})
        trm.update(body.trm_weights)
        existing["trm_weights"] = trm

    # Persist using a direct assignment so SQLAlchemy detects the change
    from sqlalchemy.orm.attributes import flag_modified
    config.metric_config = existing
    flag_modified(config, "metric_config")
    db.commit()

    from app.models.metrics_hierarchy import get_metric_config as _gmc
    mc = _gmc(config.metric_config)
    return {
        "success": True,
        "config_id": config_id,
        "data": mc.to_dict(),
    }
