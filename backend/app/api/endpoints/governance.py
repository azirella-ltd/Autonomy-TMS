"""
Governance API — Decision pipeline inspection and configuration.

Provides CRUD for:
  - Decision governance policies (AIIO thresholds, impact weights)
  - Guardrail directives (executive overrides with effective periods)
  - Planning envelope settings (adjust-before-create, Glenday preferences)
  - Pipeline visualization (how a decision flows through the gate)
  - Audit trail (provisioning + decision actions)

Access: Tenant Admin + System Admin (super user)
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.session import get_db as get_async_db
from app.models.user import User

router = APIRouter(prefix="/governance", tags=["Governance"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PolicyResponse(BaseModel):
    id: int
    tenant_id: int
    action_type: Optional[str]
    category: Optional[str]
    agent_id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    is_active: bool
    priority: int
    automate_below: float
    inform_below: float
    hold_minutes: int
    max_hold_minutes: int
    auto_apply_on_expiry: bool
    escalate_after_minutes: int
    weight_financial: float
    weight_scope: float
    weight_reversibility: float
    weight_confidence: float
    weight_override_rate: float
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    action_type: Optional[str] = None
    category: Optional[str] = None
    agent_id: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None
    automate_below: Optional[float] = None
    inform_below: Optional[float] = None
    hold_minutes: Optional[int] = None
    max_hold_minutes: Optional[int] = None
    auto_apply_on_expiry: Optional[bool] = None
    escalate_after_minutes: Optional[int] = None
    weight_financial: Optional[float] = None
    weight_scope: Optional[float] = None
    weight_reversibility: Optional[float] = None
    weight_confidence: Optional[float] = None
    weight_override_rate: Optional[float] = None


class DirectiveCreate(BaseModel):
    objective: str
    context: Optional[str] = None
    reason: Optional[str] = None
    affected_scope: Optional[Dict[str, Any]] = None
    extracted_parameters: Optional[Dict[str, Any]] = None
    effective_from: Optional[str] = None
    effective_until: Optional[str] = None
    source_channel: str = "manual"


class PipelineSimulation(BaseModel):
    """Simulate how a hypothetical decision would flow through the governance gate."""
    action_type: str
    category: str = "OTHER"
    estimated_impact: Optional[float] = None
    confidence_level: Optional[float] = None
    product_id: Optional[str] = None
    site_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper: resolve tenant_id for both tenant admin and super user
# ---------------------------------------------------------------------------

def _resolve_tenant_id(user: User, tenant_id_param: Optional[int] = None) -> int:
    """Super user can specify tenant_id; tenant admin uses their own."""
    if user.is_system_admin:
        if tenant_id_param:
            return tenant_id_param
        raise HTTPException(400, "System admin must specify tenant_id parameter")
    return user.tenant_id


# ---------------------------------------------------------------------------
# Policies CRUD
# ---------------------------------------------------------------------------

@router.get("/policies")
async def list_policies(
    tenant_id: Optional[int] = Query(None, description="Tenant ID (required for super user)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """List all governance policies for a tenant."""
    tid = _resolve_tenant_id(current_user, tenant_id)

    from app.models.decision_governance import DecisionGovernancePolicy
    result = await db.execute(
        select(DecisionGovernancePolicy)
        .where(DecisionGovernancePolicy.tenant_id == tid)
        .order_by(DecisionGovernancePolicy.priority, DecisionGovernancePolicy.id)
    )
    policies = result.scalars().all()
    return [_policy_to_dict(p) for p in policies]


@router.post("/policies")
async def create_policy(
    body: PolicyUpdate,
    tenant_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Create a new governance policy."""
    tid = _resolve_tenant_id(current_user, tenant_id)

    from app.models.decision_governance import DecisionGovernancePolicy
    policy = DecisionGovernancePolicy(tenant_id=tid, created_by=current_user.id)
    for k, v in body.dict(exclude_none=True).items():
        setattr(policy, k, v)
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return _policy_to_dict(policy)


@router.put("/policies/{policy_id}")
async def update_policy(
    policy_id: int,
    body: PolicyUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Update an existing governance policy."""
    from app.models.decision_governance import DecisionGovernancePolicy
    result = await db.execute(
        select(DecisionGovernancePolicy).where(DecisionGovernancePolicy.id == policy_id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "Policy not found")

    for k, v in body.dict(exclude_none=True).items():
        setattr(policy, k, v)
    policy.updated_at = datetime.utcnow()
    await db.commit()
    return _policy_to_dict(policy)


@router.delete("/policies/{policy_id}")
async def delete_policy(
    policy_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Delete a governance policy."""
    from app.models.decision_governance import DecisionGovernancePolicy
    result = await db.execute(
        select(DecisionGovernancePolicy).where(DecisionGovernancePolicy.id == policy_id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "Policy not found")
    await db.delete(policy)
    await db.commit()
    return {"status": "deleted", "id": policy_id}


# ---------------------------------------------------------------------------
# Guardrail Directives
# ---------------------------------------------------------------------------

@router.get("/directives")
async def list_directives(
    tenant_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """List guardrail directives."""
    tid = _resolve_tenant_id(current_user, tenant_id)

    from app.models.decision_governance import GuardrailDirective
    query = select(GuardrailDirective).where(
        GuardrailDirective.tenant_id == tid,
    ).order_by(desc(GuardrailDirective.created_at))
    if status:
        query = query.where(GuardrailDirective.status == status)

    result = await db.execute(query.limit(50))
    return [_directive_to_dict(d) for d in result.scalars().all()]


@router.post("/directives")
async def create_directive(
    body: DirectiveCreate,
    tenant_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Create a new guardrail directive."""
    tid = _resolve_tenant_id(current_user, tenant_id)

    from app.models.decision_governance import GuardrailDirective
    directive = GuardrailDirective(
        tenant_id=tid,
        source_user_id=current_user.id,
        source_channel=body.source_channel,
        raw_content=body.objective,
        objective=body.objective,
        context=body.context,
        reason=body.reason,
        affected_scope=body.affected_scope,
        extracted_parameters=body.extracted_parameters,
        effective_from=datetime.fromisoformat(body.effective_from) if body.effective_from else datetime.utcnow(),
        effective_until=datetime.fromisoformat(body.effective_until) if body.effective_until else None,
        status="APPLIED",
        extraction_confidence=1.0,
        extraction_model="manual",
    )
    db.add(directive)
    await db.commit()
    await db.refresh(directive)
    return _directive_to_dict(directive)


# ---------------------------------------------------------------------------
# Pipeline visualization & simulation
# ---------------------------------------------------------------------------

@router.get("/pipeline")
async def get_pipeline_config(
    tenant_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get the full governance pipeline configuration for visualization.

    Returns the complete gate flow: planning envelope → impact scoring →
    mode assignment → guardrail overrides, with current thresholds and weights.
    """
    tid = _resolve_tenant_id(current_user, tenant_id)

    from app.models.decision_governance import DecisionGovernancePolicy, GuardrailDirective

    # Get all active policies
    pol_result = await db.execute(
        select(DecisionGovernancePolicy).where(
            DecisionGovernancePolicy.tenant_id == tid,
            DecisionGovernancePolicy.is_active == True,
        ).order_by(DecisionGovernancePolicy.priority)
    )
    policies = pol_result.scalars().all()

    # Get active directives
    dir_result = await db.execute(
        select(GuardrailDirective).where(
            GuardrailDirective.tenant_id == tid,
            GuardrailDirective.status == "APPLIED",
        ).order_by(desc(GuardrailDirective.created_at))
    )
    directives = dir_result.scalars().all()

    # Pipeline stages
    return {
        "stages": [
            {
                "name": "Planning Envelope",
                "description": "Check existing planned/open orders before creating new (Glenday Sieve)",
                "enabled": True,
                "settings": {
                    "adjust_before_create": True,
                    "glenday_preferences": {
                        "green": 0.95, "yellow": 0.80, "red": 0.50, "blue": 0.20,
                    },
                    "eligible_statuses": ["planned", "open"],
                },
            },
            {
                "name": "Impact Scoring",
                "description": "5-dimension weighted composite score (0-100)",
                "dimensions": [
                    {"key": "financial", "label": "Financial Magnitude", "default_weight": 0.30},
                    {"key": "scope", "label": "Blast Radius", "default_weight": 0.20},
                    {"key": "reversibility", "label": "Reversibility", "default_weight": 0.20},
                    {"key": "confidence", "label": "Model Confidence (inverted)", "default_weight": 0.15},
                    {"key": "override_rate", "label": "Historical Override Rate", "default_weight": 0.15},
                ],
            },
            {
                "name": "Mode Assignment (AIIO)",
                "description": "Map impact score to execution mode",
                "modes": [
                    {"mode": "AUTOMATE", "label": "Auto-execute", "condition": "impact < automate_below"},
                    {"mode": "INFORM", "label": "Notify user, execute", "condition": "impact < inform_below"},
                    {"mode": "INSPECT", "label": "Hold for review", "condition": "impact >= inform_below"},
                ],
            },
            {
                "name": "Guardrail Override",
                "description": "Executive directives can tighten thresholds",
                "active_directives": len(directives),
            },
        ],
        "policies": [_policy_to_dict(p) for p in policies],
        "active_directives": [_directive_to_dict(d) for d in directives],
        "action_types": [
            "po_creation", "mo_execution", "to_execution", "rebalancing",
            "atp_executor", "quality_disposition", "maintenance_scheduling",
            "subcontracting", "forecast_adjustment", "inventory_buffer",
            "order_tracking",
        ],
    }


@router.post("/pipeline/simulate")
async def simulate_pipeline(
    body: PipelineSimulation,
    tenant_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Simulate how a hypothetical decision would flow through the governance gate.

    Useful for testing policy changes before applying them.
    """
    tid = _resolve_tenant_id(current_user, tenant_id)

    from app.services.decision_governance_service import DecisionGovernanceService
    from app.db.session import sync_session_factory

    sync_db = sync_session_factory()
    try:
        policy = DecisionGovernanceService.get_policy(
            sync_db, tid, body.action_type, body.category, None,
        )

        breakdown = DecisionGovernanceService.score_impact(
            action_type=body.action_type,
            category=body.category,
            estimated_impact=body.estimated_impact,
            confidence_level=body.confidence_level or 0.8,
            site_hierarchy_level="SITE",
            product_hierarchy_level="SKU",
            tenant_id=tid,
            db=sync_db,
            policy=policy,
        )

        from app.models.agent_action import ActionMode
        mode = DecisionGovernanceService.assign_mode(breakdown["score"], policy)

        return {
            "impact_score": round(breakdown["score"], 1),
            "impact_breakdown": {k: round(v, 1) for k, v in breakdown.items() if k != "score"},
            "assigned_mode": mode.value,
            "policy_used": {
                "id": policy.id,
                "name": policy.name,
                "automate_below": policy.automate_below,
                "inform_below": policy.inform_below,
            } if policy else None,
            "explanation": (
                f"Impact score {breakdown['score']:.1f} → {mode.value}. "
                f"{'Auto-executed (low impact)' if mode == ActionMode.AUTOMATE else ''}"
                f"{'User notified (medium impact)' if mode == ActionMode.INFORM else ''}"
                f"{'Held for review (high impact)' if mode == ActionMode.INSPECT else ''}"
            ),
        }
    finally:
        sync_db.close()


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

@router.get("/audit")
async def get_audit_trail(
    tenant_id: Optional[int] = Query(None),
    resource_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get audit trail entries."""
    tid = _resolve_tenant_id(current_user, tenant_id)

    from app.models.audit_log import AuditLog
    query = select(AuditLog).where(
        AuditLog.tenant_id == tid,
    ).order_by(desc(AuditLog.created_at))

    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)

    result = await db.execute(query.limit(limit))
    logs = result.scalars().all()

    return [
        {
            "id": log.id,
            "timestamp": log.created_at.isoformat() if log.created_at else None,
            "user": log.user_email or log.username,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource": log.resource_name or log.resource_id,
            "status": log.status,
            "error_message": log.error_message,
            "ip": log.ip_address,
            "description": log.description,
        }
        for log in logs
    ]


# ---------------------------------------------------------------------------
# Decision action history (governance gate outcomes)
# ---------------------------------------------------------------------------

@router.get("/decisions")
async def get_governance_decisions(
    tenant_id: Optional[int] = Query(None),
    action_type: Optional[str] = Query(None),
    mode: Optional[str] = Query(None, description="AUTOMATE, INFORM, or INSPECT"),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get recent decisions that passed through the governance gate."""
    tid = _resolve_tenant_id(current_user, tenant_id)

    from app.models.agent_action import AgentAction
    query = select(AgentAction).where(
        AgentAction.tenant_id == tid,
    ).order_by(desc(AgentAction.created_at))

    if action_type:
        query = query.where(AgentAction.action_type == action_type)
    if mode:
        query = query.where(AgentAction.action_mode == mode)

    result = await db.execute(query.limit(limit))
    actions = result.scalars().all()

    return [
        {
            "id": a.id,
            "action_type": a.action_type,
            "category": a.category.value if hasattr(a.category, "value") else str(a.category),
            "title": a.title,
            "mode": a.action_mode.value if hasattr(a.action_mode, "value") else str(a.action_mode),
            "impact_score": a.impact_score,
            "impact_breakdown": a.impact_breakdown,
            "execution_result": a.execution_result.value if hasattr(a.execution_result, "value") else str(a.execution_result),
            "confidence": a.confidence_level,
            "hold_until": a.hold_until.isoformat() if a.hold_until else None,
            "is_overridden": a.is_overridden,
            "override_reason": a.override_reason,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "planning_envelope": getattr(a, "planning_envelope_check", None),
        }
        for a in actions
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _policy_to_dict(p) -> dict:
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "action_type": p.action_type,
        "category": p.category,
        "agent_id": p.agent_id,
        "name": p.name,
        "description": p.description,
        "is_active": p.is_active,
        "priority": p.priority,
        "automate_below": p.automate_below,
        "inform_below": p.inform_below,
        "hold_minutes": p.hold_minutes,
        "max_hold_minutes": p.max_hold_minutes,
        "auto_apply_on_expiry": p.auto_apply_on_expiry,
        "escalate_after_minutes": p.escalate_after_minutes,
        "weight_financial": p.weight_financial,
        "weight_scope": p.weight_scope,
        "weight_reversibility": p.weight_reversibility,
        "weight_confidence": p.weight_confidence,
        "weight_override_rate": p.weight_override_rate,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _directive_to_dict(d) -> dict:
    return {
        "id": d.id,
        "tenant_id": d.tenant_id,
        "source_channel": d.source_channel,
        "objective": d.objective,
        "context": d.context,
        "reason": d.reason,
        "affected_scope": d.affected_scope,
        "extracted_parameters": d.extracted_parameters,
        "status": d.status,
        "effective_from": d.effective_from.isoformat() if d.effective_from else None,
        "effective_until": d.effective_until.isoformat() if d.effective_until else None,
        "extraction_confidence": d.extraction_confidence,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
