"""
SiteAgent API Endpoints

REST API for SiteAgent operations:
- ATP checking with TRM adjustments
- Replenishment planning
- CDC status and triggers
- Model management
"""

from datetime import date, datetime
from typing import Optional, List, Dict, Any
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.services.powell import (
    SiteAgent,
    SiteAgentConfig,
    CDCMonitor,
    CDCConfig,
    SiteMetrics,
    TriggerReason,
    ReplanAction,
    Priority,
)
from app.services.powell.engines import (
    MRPConfig,
    AATPConfig,
    SafetyStockConfig,
    Order as EngineOrder,
    GrossRequirement,
)

router = APIRouter(prefix="/site-agent", tags=["site-agent"])


# ----- Request/Response Models -----

class ATPCheckRequest(BaseModel):
    """Request to check ATP availability"""
    order_id: str
    product_id: str
    location_id: str
    requested_qty: float
    requested_date: date
    priority: int = Field(default=3, ge=1, le=5)
    customer_id: str = "DEFAULT"
    order_type: str = "standard"


class ATPCheckResponse(BaseModel):
    """Response from ATP check"""
    order_id: str
    can_fulfill: bool
    promised_qty: float
    shortage_qty: float
    promise_date: date
    source: str  # "deterministic", "trm_adjusted"
    confidence: float
    explanation: str
    consumption_detail: Optional[List[Dict]] = None


class ReplenishmentRequest(BaseModel):
    """Request for replenishment planning"""
    site_key: str
    planning_horizon_days: int = 90
    include_trm_adjustments: bool = True


class ReplenishmentResponse(BaseModel):
    """Response from replenishment planning"""
    site_key: str
    recommendations: List[Dict]
    total_orders: int
    expedited_orders: int
    generated_at: datetime


class CDCStatusResponse(BaseModel):
    """CDC monitor status"""
    site_key: str
    enabled: bool
    last_check: Optional[datetime]
    last_trigger: Optional[datetime]
    backlog_growth_days: int
    thresholds: Dict[str, float]
    recent_triggers: List[Dict]


class CDCTriggerRequest(BaseModel):
    """Manual CDC trigger request"""
    site_key: str
    reason: str = "manual"


class CDCTriggerResponse(BaseModel):
    """CDC trigger result"""
    triggered: bool
    reasons: List[str]
    recommended_action: str
    severity: str
    message: str


class SiteMetricsInput(BaseModel):
    """Current site metrics for CDC check"""
    demand_cumulative: float
    forecast_cumulative: float
    inventory_on_hand: float
    inventory_target: float
    service_level: float
    target_service_level: float = 0.95
    avg_lead_time_actual: float
    avg_lead_time_expected: float
    supplier_on_time_rate: float = 0.95
    backlog_units: float = 0
    backlog_yesterday: float = 0


class LoadAllocationsRequest(BaseModel):
    """Request to load allocations from tGNN"""
    site_key: str
    allocations: List[Dict]  # [{product_id, location_id, priority, allocated_qty}]


class SiteAgentStatusResponse(BaseModel):
    """Overall site agent status"""
    site_key: str
    agent_mode: str
    use_trm: bool
    model_loaded: bool
    model_checkpoint: Optional[str]
    param_counts: Optional[Dict]
    cdc_enabled: bool
    allocation_summary: Dict


# ----- Site Agent Cache -----

_site_agents: Dict[str, SiteAgent] = {}


def get_site_agent(
    site_key: str,
    db: Session,
    use_trm: bool = True
) -> SiteAgent:
    """Get or create SiteAgent for site"""
    cache_key = f"{site_key}:{use_trm}"

    if cache_key not in _site_agents:
        config = SiteAgentConfig(
            site_key=site_key,
            use_trm_adjustments=use_trm,
            agent_mode="copilot",
        )
        _site_agents[cache_key] = SiteAgent(config, db)

    return _site_agents[cache_key]


# ----- ATP Endpoints -----

@router.post("/atp/check", response_model=ATPCheckResponse)
async def check_atp(
    request: ATPCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Check Available-to-Promise for an order.

    Uses deterministic AATP engine with optional TRM adjustments
    for exception handling (partial fill, substitute, etc.).
    """
    site_agent = get_site_agent(request.location_id, db)

    order = EngineOrder(
        order_id=request.order_id,
        product_id=request.product_id,
        location_id=request.location_id,
        requested_qty=request.requested_qty,
        requested_date=request.requested_date,
        priority=Priority.from_value(request.priority),
        customer_id=request.customer_id,
        order_type=request.order_type,
    )

    result = await site_agent.execute_atp(order)

    return ATPCheckResponse(
        order_id=result.order_id,
        can_fulfill=result.promised_qty >= request.requested_qty,
        promised_qty=result.promised_qty,
        shortage_qty=max(0, request.requested_qty - result.promised_qty),
        promise_date=result.promise_date,
        source=result.source,
        confidence=result.confidence,
        explanation=result.explanation,
    )


@router.post("/atp/batch", response_model=List[ATPCheckResponse])
async def check_atp_batch(
    requests: List[ATPCheckRequest],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check ATP for multiple orders"""
    results = []

    for req in requests:
        site_agent = get_site_agent(req.location_id, db)

        order = EngineOrder(
            order_id=req.order_id,
            product_id=req.product_id,
            location_id=req.location_id,
            requested_qty=req.requested_qty,
            requested_date=req.requested_date,
            priority=Priority.from_value(req.priority),
            customer_id=req.customer_id,
            order_type=req.order_type,
        )

        result = await site_agent.execute_atp(order)

        results.append(ATPCheckResponse(
            order_id=result.order_id,
            can_fulfill=result.promised_qty >= req.requested_qty,
            promised_qty=result.promised_qty,
            shortage_qty=max(0, req.requested_qty - result.promised_qty),
            promise_date=result.promise_date,
            source=result.source,
            confidence=result.confidence,
            explanation=result.explanation,
        ))

    return results


@router.post("/allocations/load")
async def load_allocations(
    request: LoadAllocationsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Load allocations from tGNN into AATP engine"""
    from app.services.powell.engines import ATPAllocation, Priority

    site_agent = get_site_agent(request.site_key, db)

    allocations = [
        ATPAllocation(
            product_id=a['product_id'],
            location_id=a.get('location_id', request.site_key),
            priority=Priority.from_value(a.get('priority', 3)),
            allocated_qty=a['allocated_qty'],
            period_start=date.today(),
            period_end=date.today(),
        )
        for a in request.allocations
    ]

    site_agent.aatp_engine.load_allocations(allocations)

    return {
        "status": "success",
        "site_key": request.site_key,
        "allocations_loaded": len(allocations),
        "summary": site_agent.aatp_engine.get_allocation_summary()
    }


# ----- Replenishment Endpoints -----

@router.post("/replenishment/plan", response_model=ReplenishmentResponse)
async def plan_replenishment(
    request: ReplenishmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate replenishment plan using MRP engine with TRM adjustments.
    """
    site_agent = get_site_agent(request.site_key, db, request.include_trm_adjustments)

    # TODO: Load actual data from database
    # For now, return placeholder
    return ReplenishmentResponse(
        site_key=request.site_key,
        recommendations=[],
        total_orders=0,
        expedited_orders=0,
        generated_at=datetime.utcnow(),
    )


# ----- CDC Endpoints -----

@router.get("/cdc/status/{site_key}", response_model=CDCStatusResponse)
async def get_cdc_status(
    site_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get CDC monitor status for a site"""
    from app.models.powell_decision import CDCTriggerLog
    from sqlalchemy import desc

    site_agent = get_site_agent(site_key, db)
    status = site_agent.cdc_monitor.get_status()

    # Load recent triggers from database
    trigger_rows = (
        db.query(CDCTriggerLog)
        .filter(CDCTriggerLog.site_key == site_key)
        .order_by(desc(CDCTriggerLog.timestamp))
        .limit(20)
        .all()
    )
    recent_triggers = [
        {
            "id": t.id,
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
            "triggered": t.triggered,
            "reasons": t.reasons or [],
            "severity": t.severity,
            "recommended_action": t.recommended_action,
            "action_taken": t.action_taken,
            "replan_completed": t.replan_completed,
            "threshold_breaches": t.threshold_breaches or {},
        }
        for t in trigger_rows
    ]

    # Determine last_check from most recent trigger entry
    last_check = trigger_rows[0].timestamp if trigger_rows else None
    # Determine last_trigger from most recent actual trigger
    last_trigger_row = next((t for t in trigger_rows if t.triggered), None)
    last_trigger_time = last_trigger_row.timestamp if last_trigger_row else None

    return CDCStatusResponse(
        site_key=site_key,
        enabled=status['enabled'],
        last_check=last_check,
        last_trigger=last_trigger_time,
        backlog_growth_days=status['backlog_growth_days'],
        thresholds=status['thresholds'],
        recent_triggers=recent_triggers,
    )


@router.post("/cdc/check", response_model=CDCTriggerResponse)
async def check_cdc_trigger(
    site_key: str,
    metrics: SiteMetricsInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Check if CDC thresholds are exceeded.

    Provide current site metrics to check against configured thresholds.
    """
    site_agent = get_site_agent(site_key, db)

    site_metrics = SiteMetrics(
        site_key=site_key,
        timestamp=datetime.utcnow(),
        demand_cumulative=metrics.demand_cumulative,
        forecast_cumulative=metrics.forecast_cumulative,
        inventory_on_hand=metrics.inventory_on_hand,
        inventory_target=metrics.inventory_target,
        service_level=metrics.service_level,
        target_service_level=metrics.target_service_level,
        avg_lead_time_actual=metrics.avg_lead_time_actual,
        avg_lead_time_expected=metrics.avg_lead_time_expected,
        supplier_on_time_rate=metrics.supplier_on_time_rate,
        backlog_units=metrics.backlog_units,
        backlog_yesterday=metrics.backlog_yesterday,
    )

    trigger = await site_agent.check_cdc_trigger(site_metrics)

    return CDCTriggerResponse(
        triggered=trigger.triggered,
        reasons=[r.value for r in trigger.reasons],
        recommended_action=trigger.recommended_action.value,
        severity=trigger.severity,
        message=trigger.message,
    )


@router.post("/cdc/trigger-manual", response_model=CDCTriggerResponse)
async def trigger_cdc_manual(
    request: CDCTriggerRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manually trigger CDC replanning.

    Use this to force an out-of-cadence planning run.
    """
    # TODO: Implement actual replanning trigger
    return CDCTriggerResponse(
        triggered=True,
        reasons=["manual"],
        recommended_action="full_cfa",
        severity="medium",
        message=f"Manual CDC trigger initiated by {current_user.email}",
    )


@router.put("/cdc/thresholds/{site_key}")
async def update_cdc_thresholds(
    site_key: str,
    thresholds: Dict[str, float],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update CDC thresholds for a site"""
    site_agent = get_site_agent(site_key, db)

    # Update thresholds
    for key, value in thresholds.items():
        if key in site_agent.cdc_monitor.config.thresholds:
            site_agent.cdc_monitor.config.thresholds[key] = value

    # TODO: Persist to database

    return {
        "status": "success",
        "site_key": site_key,
        "thresholds": site_agent.cdc_monitor.config.thresholds
    }


# ----- Inventory Adjustment Endpoints -----

@router.get("/inventory/adjustments/{site_key}")
async def get_inventory_adjustments(
    site_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get TRM-suggested inventory parameter adjustments"""
    site_agent = get_site_agent(site_key, db)
    adjustments = await site_agent.get_inventory_adjustments()

    return {
        "site_key": site_key,
        "adjustments": adjustments,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ----- Status Endpoints -----

@router.get("/status/{site_key}", response_model=SiteAgentStatusResponse)
async def get_site_agent_status(
    site_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get overall SiteAgent status"""
    site_agent = get_site_agent(site_key, db)
    status = site_agent.get_status()

    param_counts = None
    if site_agent.model:
        param_counts = site_agent.model.get_parameter_count()

    return SiteAgentStatusResponse(
        site_key=site_key,
        agent_mode=status['agent_mode'],
        use_trm=status['use_trm'],
        model_loaded=status['model_loaded'],
        model_checkpoint=site_agent.config.model_checkpoint_path,
        param_counts=param_counts,
        cdc_enabled=status['cdc_status']['enabled'],
        allocation_summary=status['allocations_summary'],
    )


@router.get("/status")
async def list_site_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all active site agents"""
    return {
        "active_agents": list(_site_agents.keys()),
        "count": len(_site_agents),
    }


@router.delete("/cache/{site_key}")
async def clear_site_agent_cache(
    site_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clear cached site agent (forces reload)"""
    removed = []
    for key in list(_site_agents.keys()):
        if key.startswith(site_key):
            del _site_agents[key]
            removed.append(key)

    return {
        "status": "success",
        "removed": removed,
    }


# ----- CDC Trigger History & Retraining Endpoints -----

@router.get("/cdc/triggers/{site_key}")
async def get_cdc_triggers(
    site_key: str,
    limit: int = Query(default=50, ge=1, le=200),
    triggered_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get CDC trigger history for a site.

    Returns recent trigger events from powell_cdc_trigger_log.
    """
    from app.models.powell_decision import CDCTriggerLog
    from sqlalchemy import desc

    query = db.query(CDCTriggerLog).filter(CDCTriggerLog.site_key == site_key)
    if triggered_only:
        query = query.filter(CDCTriggerLog.triggered == True)

    rows = query.order_by(desc(CDCTriggerLog.timestamp)).limit(limit).all()

    return {
        "site_key": site_key,
        "total": len(rows),
        "triggers": [
            {
                "id": t.id,
                "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                "triggered": t.triggered,
                "reasons": t.reasons or [],
                "severity": t.severity,
                "recommended_action": t.recommended_action,
                "action_taken": t.action_taken,
                "replan_completed": t.replan_completed,
                "threshold_breaches": t.threshold_breaches or {},
                "metrics_snapshot": t.metrics_snapshot or {},
            }
            for t in rows
        ],
    }


@router.get("/retraining/status/{site_key}")
async def get_retraining_status(
    site_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get retraining status for a site.

    Returns latest checkpoint info, pending experience count,
    and readiness indicator.
    """
    from app.models.powell_decision import SiteAgentCheckpoint, SiteAgentDecision, CDCTriggerLog
    from sqlalchemy import desc, func
    from datetime import timedelta

    now = datetime.utcnow()

    # Latest active checkpoint
    checkpoint = (
        db.query(SiteAgentCheckpoint)
        .filter(
            SiteAgentCheckpoint.site_key == site_key,
            SiteAgentCheckpoint.is_active == True,
        )
        .order_by(desc(SiteAgentCheckpoint.created_at))
        .first()
    )

    # Count decisions with outcomes (potential training data)
    total_with_outcomes = (
        db.query(func.count(SiteAgentDecision.decision_id))
        .filter(
            SiteAgentDecision.site_key == site_key,
            SiteAgentDecision.actual_outcome.isnot(None),
        )
        .scalar() or 0
    )

    # Count decisions with outcomes since last checkpoint
    last_checkpoint_time = checkpoint.created_at if checkpoint else datetime.min
    pending_experiences = (
        db.query(func.count(SiteAgentDecision.decision_id))
        .filter(
            SiteAgentDecision.site_key == site_key,
            SiteAgentDecision.actual_outcome.isnot(None),
            SiteAgentDecision.timestamp > last_checkpoint_time,
        )
        .scalar() or 0
    )

    # Count decisions awaiting outcomes
    awaiting_outcomes = (
        db.query(func.count(SiteAgentDecision.decision_id))
        .filter(
            SiteAgentDecision.site_key == site_key,
            SiteAgentDecision.actual_outcome.is_(None),
            SiteAgentDecision.timestamp > now - timedelta(days=30),
        )
        .scalar() or 0
    )

    # Recent CDC triggers
    recent_trigger_count = (
        db.query(func.count(CDCTriggerLog.id))
        .filter(
            CDCTriggerLog.site_key == site_key,
            CDCTriggerLog.triggered == True,
            CDCTriggerLog.timestamp > now - timedelta(hours=24),
        )
        .scalar() or 0
    )

    # Determine readiness: green (ready), orange (almost), red (not ready)
    min_experiences = 100
    cooldown_ok = (
        not checkpoint
        or (now - checkpoint.created_at).total_seconds() > 6 * 3600
    )
    has_enough_data = pending_experiences >= min_experiences
    has_trigger = recent_trigger_count > 0

    if has_enough_data and cooldown_ok and has_trigger:
        readiness = "ready"
    elif has_enough_data and cooldown_ok:
        readiness = "waiting_for_trigger"
    elif pending_experiences >= min_experiences * 0.5:
        readiness = "collecting"
    else:
        readiness = "not_ready"

    return {
        "site_key": site_key,
        "checkpoint": {
            "id": checkpoint.checkpoint_id if checkpoint else None,
            "model_version": checkpoint.model_version if checkpoint else None,
            "training_loss": checkpoint.training_loss if checkpoint else None,
            "training_samples": checkpoint.training_samples if checkpoint else None,
            "training_phase": checkpoint.training_phase if checkpoint else None,
            "created_at": checkpoint.created_at.isoformat() if checkpoint else None,
            "is_validated": checkpoint.is_validated if checkpoint else None,
        } if checkpoint else None,
        "experiences": {
            "total_with_outcomes": total_with_outcomes,
            "pending_since_checkpoint": pending_experiences,
            "awaiting_outcomes": awaiting_outcomes,
            "min_required": min_experiences,
        },
        "recent_cdc_triggers": recent_trigger_count,
        "cooldown_ok": cooldown_ok,
        "readiness": readiness,
    }


@router.post("/retraining/trigger/{site_key}")
async def trigger_retraining(
    site_key: str,
    reason: Optional[str] = Query(None, description="Manual trigger reason"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manually trigger TRM retraining for a site.

    Creates a TriggerEvent with manual reason, logs it to
    powell_cdc_trigger_log, and runs retraining in background.
    Returns a pipeline_id for status polling.
    """
    import uuid
    from app.services.powell.cdc_retraining_service import CDCRetrainingService
    from app.services.powell.cdc_monitor import TriggerEvent

    pipeline_id = str(uuid.uuid4())

    svc = CDCRetrainingService(db=db, site_key=site_key, group_id=0)

    # Quick pre-check
    if not svc.evaluate_retraining_need(skip_trigger_check=True):
        return {
            "status": "skipped",
            "pipeline_id": pipeline_id,
            "site_key": site_key,
            "message": "Not enough training data or cooldown not elapsed",
        }

    # Create a manual TriggerEvent
    manual_trigger = TriggerEvent(
        triggered=True,
        reasons=[TriggerReason.DEMAND_DEVIATION],
        metrics_snapshot=SiteMetrics(
            site_key=site_key,
            timestamp=datetime.utcnow(),
            demand_cumulative=0.0,
            forecast_cumulative=0.0,
            inventory_on_hand=0.0,
            inventory_target=0.0,
            service_level=0.0,
            target_service_level=0.95,
            avg_lead_time_actual=0.0,
            avg_lead_time_expected=0.0,
            supplier_on_time_rate=1.0,
            backlog_units=0.0,
        ),
        recommended_action=ReplanAction.FULL_CFA,
        severity="medium",
        message=f"Manual trigger by {current_user.email}: {reason or 'no reason given'}",
    )

    # Log trigger event to DB
    try:
        from app.models.powell_decision import CDCTriggerLog

        trigger_log = CDCTriggerLog(
            site_key=site_key,
            triggered=True,
            reasons=["manual_trigger"],
            severity="medium",
            recommended_action=ReplanAction.FULL_CFA.value,
            metrics_snapshot={
                "site_key": site_key,
                "manual": True,
                "reason": reason or "manual_trigger",
                "triggered_by": current_user.email,
                "pipeline_id": pipeline_id,
            },
        )
        db.add(trigger_log)
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to log manual trigger: {e}")

    def _run_retraining():
        from app.db.session import SessionLocal
        bg_db = SessionLocal()
        try:
            bg_svc = CDCRetrainingService(db=bg_db, site_key=site_key, group_id=0)
            result = bg_svc.execute_retraining(trigger_event=manual_trigger)
            if result and result.final_loss < float("inf"):
                logger.info(
                    f"Manual retraining completed for {site_key} "
                    f"(pipeline={pipeline_id}): loss={result.final_loss:.4f}"
                )
            else:
                logger.warning(
                    f"Manual retraining for {site_key} "
                    f"(pipeline={pipeline_id}) produced no improvement"
                )
        except Exception as e:
            logger.error(f"Manual retraining failed for {site_key} (pipeline={pipeline_id}): {e}")
        finally:
            bg_db.close()

    background_tasks.add_task(_run_retraining)

    return {
        "status": "started",
        "pipeline_id": pipeline_id,
        "site_key": site_key,
        "message": f"Retraining triggered by {current_user.email}, running in background",
    }


# ============================================================================
# Hive Signal Bus & Decision Cycle Endpoints
# ============================================================================

@router.get("/hive/status/{site_key}")
async def get_hive_status(
    site_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get hive signal bus status, urgency vector, and signal divergence."""
    site_agent = get_site_agent(site_key, db)
    result: Dict[str, Any] = {
        "site_key": site_key,
        "hive_enabled": site_agent.signal_bus is not None,
    }

    if site_agent.signal_bus is None:
        result["urgency_vector"] = None
        result["signal_bus"] = None
        result["signal_divergence"] = 0.0
        result["hive_health"] = None
        return result

    bus = site_agent.signal_bus

    # Urgency vector as labelled dict
    uv = bus.urgency
    uv_values = uv.values_array()
    uv_snapshot = uv.snapshot()
    idx_to_name = {v: k for k, v in uv.TRM_INDICES.items()}
    result["urgency_vector"] = {
        "values": {idx_to_name[i]: round(v, 4) for i, v in enumerate(uv_values)},
        "directions": {
            idx_to_name[i]: d for i, d in enumerate(uv_snapshot["directions"])
        },
        "last_updated": {
            idx_to_name[i]: t for i, t in enumerate(uv_snapshot["last_updated"])
        },
    }

    # Signal bus stats
    result["signal_bus"] = bus.stats()
    result["signal_summary"] = bus.signal_summary()

    # Active signals (limited to 50 most recent)
    active = bus.active_signals()
    result["active_signals"] = [s.to_dict() for s in active[-50:]]

    # Signal divergence
    result["signal_divergence"] = getattr(
        site_agent.cdc_monitor, "_signal_divergence_score", 0.0
    )

    # Hive health metrics
    result["hive_health"] = site_agent.get_hive_health()

    # tGNN directive status
    directive = site_agent.get_current_directive()
    if directive is not None:
        result["directive"] = {
            "site_key": getattr(directive, "site_key", ""),
            "criticality_score": getattr(directive, "criticality_score", 0.0),
            "bottleneck_risk": getattr(directive, "bottleneck_risk", 0.0),
            "safety_stock_multiplier": getattr(directive, "safety_stock_multiplier", 1.0),
            "resilience_score": getattr(directive, "resilience_score", 0.0),
            "confidence": getattr(directive, "confidence", 0.0),
            "inter_hive_signal_count": len(getattr(directive, "inter_hive_signals", [])),
        }
    else:
        result["directive"] = None

    # Registered TRMs
    result["registered_trms"] = list(site_agent._registered_trms.keys())

    return result


@router.get("/hive/decision-cycle/{site_key}")
async def get_decision_cycle_info(
    site_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get decision cycle phase mapping and TRM assignments."""
    from app.services.powell.decision_cycle import PHASE_TRM_MAP, DecisionCyclePhase

    phases = []
    for phase in DecisionCyclePhase:
        trms = PHASE_TRM_MAP.get(phase, [])
        phases.append({
            "phase": phase.value,
            "name": phase.name,
            "trms": trms,
        })

    site_agent = get_site_agent(site_key, db)
    registered = list(site_agent._registered_trms.keys())

    return {
        "site_key": site_key,
        "phases": phases,
        "registered_trms": registered,
        "total_phases": len(phases),
    }


@router.post("/hive/decision-cycle/{site_key}/run")
async def run_decision_cycle(
    site_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute a decision cycle and return phase-by-phase results."""
    site_agent = get_site_agent(site_key, db)

    # Build executors from registered TRMs (if they're callable)
    executors = {}
    for name, trm in site_agent._registered_trms.items():
        if callable(trm):
            executors[name] = trm

    result = site_agent.execute_decision_cycle(trm_executors=executors)

    return {
        "site_key": site_key,
        "completed_at": result.completed_at.isoformat() if result.completed_at else None,
        "total_duration_ms": round(result.total_duration_ms, 2),
        "total_signals_emitted": result.total_signals_emitted,
        "conflicts_detected": result.conflicts_detected,
        "phases": [
            {
                "phase": p.phase.value,
                "name": p.phase.name,
                "trms_executed": p.trms_executed,
                "signals_emitted": p.signals_emitted,
                "duration_ms": round(p.duration_ms, 2),
                "errors": p.errors,
            }
            for p in result.phases
        ],
    }
