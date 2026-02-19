"""
Exception Workflow Management API

Endpoints for managing exception workflows, automated routing,
and escalation paths for forecast exceptions.

Phase 3.3: Exception Management Workflows
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
import uuid

from app.db.session import get_db
from app.models.forecast_exception import (
    ForecastException, ForecastExceptionRule, ForecastExceptionComment,
    ExceptionWorkflowTemplate, ExceptionEscalationLog
)
from app.models.user import User

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class EscalationLevel(BaseModel):
    """Single escalation level configuration."""
    level: int = Field(..., description="Escalation level (1, 2, 3...)")
    hours_after_creation: int = Field(..., description="Hours to wait before escalating")
    assign_to_role: Optional[str] = Field(None, description="Role to assign to")
    assign_to_user_id: Optional[int] = Field(None, description="Specific user to assign to")
    notification_channels: List[str] = Field(default_factory=lambda: ["email"], description="email, slack, teams")
    escalation_message: Optional[str] = Field(None, description="Custom message for escalation")


class AutoResolveConfig(BaseModel):
    """Auto-resolve configuration."""
    enabled: bool = Field(default=False)
    conditions: Dict[str, Any] = Field(default_factory=dict, description="Conditions for auto-resolution")
    action: str = Field(default="resolve", description="resolve, defer, suppress")
    defer_hours: Optional[int] = Field(None, description="Hours to defer if action is defer")


class WorkflowTemplateCreate(BaseModel):
    """Create workflow template request."""
    name: str = Field(..., max_length=100)
    code: str = Field(..., max_length=50)
    description: Optional[str] = None
    exception_types: List[str] = Field(default_factory=list, description="Exception types this applies to")
    severity_levels: List[str] = Field(default_factory=list, description="Severity levels: low, medium, high, critical")
    initial_assignment: Optional[Dict[str, Any]] = Field(None, description="Initial assignment rules")
    escalation_levels: List[EscalationLevel] = Field(default_factory=list)
    auto_resolve_config: Optional[AutoResolveConfig] = None
    sla_hours: Optional[int] = Field(None, description="SLA hours for resolution")
    is_active: bool = True


class WorkflowTemplateUpdate(BaseModel):
    """Update workflow template request."""
    name: Optional[str] = None
    description: Optional[str] = None
    exception_types: Optional[List[str]] = None
    severity_levels: Optional[List[str]] = None
    initial_assignment: Optional[Dict[str, Any]] = None
    escalation_levels: Optional[List[EscalationLevel]] = None
    auto_resolve_config: Optional[AutoResolveConfig] = None
    sla_hours: Optional[int] = None
    is_active: Optional[bool] = None


class WorkflowTemplateResponse(BaseModel):
    """Workflow template response."""
    id: int
    name: str
    code: str
    description: Optional[str]
    exception_types: Optional[Dict[str, Any]]
    severity_levels: Optional[Dict[str, Any]]
    initial_assignment: Optional[Dict[str, Any]]
    escalation_levels: Optional[Dict[str, Any]]
    auto_resolve_config: Optional[Dict[str, Any]]
    sla_hours: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EscalationLogResponse(BaseModel):
    """Escalation log response."""
    id: int
    exception_id: int
    workflow_template_id: Optional[int]
    escalation_level: int
    escalated_from_id: Optional[int]
    escalated_to_id: int
    escalation_reason: str
    triggered_by: str
    trigger_user_id: Optional[int]
    notifications_sent: Optional[Dict[str, Any]]
    escalated_at: datetime

    class Config:
        from_attributes = True


class ApplyWorkflowRequest(BaseModel):
    """Apply workflow to exceptions request."""
    exception_ids: List[int] = Field(..., description="Exception IDs to apply workflow to")
    workflow_template_id: int


class ApplyWorkflowResponse(BaseModel):
    """Apply workflow response."""
    success: bool
    applied_count: int
    skipped_count: int
    details: List[Dict[str, Any]]


class EscalateRequest(BaseModel):
    """Manual escalation request."""
    reason: str = Field(..., max_length=500)
    assign_to_user_id: Optional[int] = None
    assign_to_role: Optional[str] = None
    notification_channels: List[str] = Field(default_factory=lambda: ["email"])


class WorkflowStatsResponse(BaseModel):
    """Workflow statistics response."""
    total_exceptions: int
    pending_exceptions: int
    in_progress_exceptions: int
    resolved_exceptions: int
    escalated_exceptions: int
    avg_resolution_time_hours: Optional[float]
    sla_compliance_rate: Optional[float]
    escalation_rate: Optional[float]
    by_severity: Dict[str, int]
    by_type: Dict[str, int]


# ============================================================================
# Workflow Template CRUD Endpoints
# ============================================================================

@router.get("/templates", response_model=List[WorkflowTemplateResponse])
async def list_workflow_templates(
    is_active: Optional[bool] = None,
    exception_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all workflow templates with optional filtering."""
    stmt = select(ExceptionWorkflowTemplate)

    if is_active is not None:
        stmt = stmt.where(ExceptionWorkflowTemplate.is_active == is_active)

    stmt = stmt.order_by(ExceptionWorkflowTemplate.name)
    result = await db.execute(stmt)
    templates = list(result.scalars().all())

    # Filter by exception type if specified (JSON field filtering)
    if exception_type:
        templates = [
            t for t in templates
            if t.exception_types and exception_type in t.exception_types.get('types', [])
        ]

    return templates


@router.post("/templates", response_model=WorkflowTemplateResponse)
async def create_workflow_template(
    request: WorkflowTemplateCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new workflow template."""
    # Check for duplicate code
    result = await db.execute(
        select(ExceptionWorkflowTemplate).where(ExceptionWorkflowTemplate.code == request.code)
    )
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Workflow template with code '{request.code}' already exists")

    template = ExceptionWorkflowTemplate(
        name=request.name,
        code=request.code,
        description=request.description,
        exception_types={'types': request.exception_types} if request.exception_types else None,
        severity_levels={'levels': request.severity_levels} if request.severity_levels else None,
        initial_assignment=request.initial_assignment,
        escalation_levels={'levels': [e.model_dump() for e in request.escalation_levels]} if request.escalation_levels else None,
        auto_resolve_config=request.auto_resolve_config.model_dump() if request.auto_resolve_config else None,
        sla_hours=request.sla_hours,
        is_active=request.is_active
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    return template


@router.get("/templates/{template_id}", response_model=WorkflowTemplateResponse)
async def get_workflow_template(
    template_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific workflow template."""
    result = await db.execute(
        select(ExceptionWorkflowTemplate).where(ExceptionWorkflowTemplate.id == template_id)
    )
    template = result.scalars().first()

    if not template:
        raise HTTPException(status_code=404, detail="Workflow template not found")

    return template


@router.put("/templates/{template_id}", response_model=WorkflowTemplateResponse)
async def update_workflow_template(
    template_id: int,
    request: WorkflowTemplateUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a workflow template."""
    result = await db.execute(
        select(ExceptionWorkflowTemplate).where(ExceptionWorkflowTemplate.id == template_id)
    )
    template = result.scalars().first()

    if not template:
        raise HTTPException(status_code=404, detail="Workflow template not found")

    if request.name is not None:
        template.name = request.name
    if request.description is not None:
        template.description = request.description
    if request.exception_types is not None:
        template.exception_types = {'types': request.exception_types}
    if request.severity_levels is not None:
        template.severity_levels = {'levels': request.severity_levels}
    if request.initial_assignment is not None:
        template.initial_assignment = request.initial_assignment
    if request.escalation_levels is not None:
        template.escalation_levels = {'levels': [e.model_dump() for e in request.escalation_levels]}
    if request.auto_resolve_config is not None:
        template.auto_resolve_config = request.auto_resolve_config.model_dump()
    if request.sla_hours is not None:
        template.sla_hours = request.sla_hours
    if request.is_active is not None:
        template.is_active = request.is_active

    template.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(template)

    return template


@router.delete("/templates/{template_id}")
async def delete_workflow_template(
    template_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a workflow template."""
    result = await db.execute(
        select(ExceptionWorkflowTemplate).where(ExceptionWorkflowTemplate.id == template_id)
    )
    template = result.scalars().first()

    if not template:
        raise HTTPException(status_code=404, detail="Workflow template not found")

    # Check if template is in use
    count_result = await db.execute(
        select(func.count()).select_from(ForecastException).where(
            ForecastException.workflow_template_id == template_id
        )
    )
    in_use = count_result.scalar() or 0

    if in_use > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete template - it is used by {in_use} exceptions. Deactivate instead."
        )

    await db.delete(template)
    await db.commit()

    return {"success": True, "message": "Workflow template deleted"}


# ============================================================================
# Workflow Application Endpoints
# ============================================================================

@router.post("/apply", response_model=ApplyWorkflowResponse)
async def apply_workflow_to_exceptions(
    request: ApplyWorkflowRequest,
    db: AsyncSession = Depends(get_db)
):
    """Apply a workflow template to multiple exceptions."""
    result = await db.execute(
        select(ExceptionWorkflowTemplate).where(
            ExceptionWorkflowTemplate.id == request.workflow_template_id
        )
    )
    template = result.scalars().first()

    if not template:
        raise HTTPException(status_code=404, detail="Workflow template not found")

    if not template.is_active:
        raise HTTPException(status_code=400, detail="Workflow template is not active")

    applied = []
    skipped = []

    for exc_id in request.exception_ids:
        exc_result = await db.execute(
            select(ForecastException).where(ForecastException.id == exc_id)
        )
        exception = exc_result.scalars().first()

        if not exception:
            skipped.append({'id': exc_id, 'reason': 'Not found'})
            continue

        if exception.status in ['resolved', 'closed']:
            skipped.append({'id': exc_id, 'reason': 'Already resolved/closed'})
            continue

        # Apply workflow
        exception.workflow_template_id = template.id
        exception.current_escalation_level = 0

        # Apply initial assignment if configured
        if template.initial_assignment:
            if 'user_id' in template.initial_assignment:
                exception.assigned_to_id = template.initial_assignment['user_id']
            elif 'role' in template.initial_assignment:
                exception.assigned_to_role = template.initial_assignment['role']

        # Set SLA deadline
        if template.sla_hours:
            exception.sla_deadline = datetime.utcnow() + timedelta(hours=template.sla_hours)

        applied.append({'id': exc_id, 'workflow': template.code})

    await db.commit()

    return ApplyWorkflowResponse(
        success=True,
        applied_count=len(applied),
        skipped_count=len(skipped),
        details=applied + skipped
    )


@router.post("/exceptions/{exception_id}/escalate", response_model=EscalationLogResponse)
async def escalate_exception(
    exception_id: int,
    request: EscalateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Manually escalate an exception."""
    result = await db.execute(
        select(ForecastException).where(ForecastException.id == exception_id)
    )
    exception = result.scalars().first()

    if not exception:
        raise HTTPException(status_code=404, detail="Exception not found")

    if exception.status in ['resolved', 'closed']:
        raise HTTPException(status_code=400, detail="Cannot escalate resolved/closed exception")

    # Get current escalation level
    current_level = exception.current_escalation_level or 0
    new_level = current_level + 1

    # Create escalation log
    # Determine the escalation target - must have a user ID
    target_user_id = request.assign_to_user_id
    if not target_user_id:
        # If only role specified, would need to lookup a user with that role
        # For now, keep existing assignee or fail
        target_user_id = exception.assigned_to_id
        if not target_user_id:
            raise HTTPException(status_code=400, detail="Must specify assign_to_user_id or have existing assignee")

    escalation_log = ExceptionEscalationLog(
        exception_id=exception_id,
        workflow_template_id=exception.workflow_template_id,
        escalation_level=new_level,
        escalated_from_id=exception.assigned_to_id,
        escalated_to_id=target_user_id,
        escalation_reason=request.reason,
        triggered_by="USER",
        notifications_sent={'channels': request.notification_channels, 'sent': True}
    )

    # Update exception
    exception.current_escalation_level = new_level
    exception.last_escalated_at = datetime.utcnow()
    if request.assign_to_user_id:
        exception.assigned_to_id = request.assign_to_user_id
    if request.assign_to_role:
        exception.assigned_to_role = request.assign_to_role

    db.add(escalation_log)
    await db.commit()
    await db.refresh(escalation_log)

    return escalation_log


@router.get("/exceptions/{exception_id}/escalation-history", response_model=List[EscalationLogResponse])
async def get_escalation_history(
    exception_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get escalation history for an exception."""
    result = await db.execute(
        select(ExceptionEscalationLog).where(
            ExceptionEscalationLog.exception_id == exception_id
        ).order_by(ExceptionEscalationLog.escalated_at.desc())
    )
    logs = list(result.scalars().all())

    return logs


# ============================================================================
# Auto-Processing Endpoints
# ============================================================================

@router.post("/process-escalations")
async def process_automatic_escalations(
    db: AsyncSession = Depends(get_db)
):
    """
    Process automatic escalations based on workflow templates.
    This would typically be called by a scheduler/cron job.
    """
    now = datetime.utcnow()
    escalated_count = 0

    # Get all active exceptions with workflow templates
    result = await db.execute(
        select(ForecastException).where(
            ForecastException.status.in_(['new', 'in_progress', 'pending']),
            ForecastException.workflow_template_id.isnot(None)
        )
    )
    exceptions = list(result.scalars().all())

    for exception in exceptions:
        tmpl_result = await db.execute(
            select(ExceptionWorkflowTemplate).where(
                ExceptionWorkflowTemplate.id == exception.workflow_template_id
            )
        )
        template = tmpl_result.scalars().first()

        if not template or not template.escalation_levels:
            continue

        escalation_config = template.escalation_levels.get('levels', [])
        current_level = exception.current_escalation_level or 0

        # Find next applicable escalation level
        for level_config in escalation_config:
            if level_config['level'] <= current_level:
                continue

            # Check if enough time has passed
            hours_since_creation = (now - exception.created_at).total_seconds() / 3600
            if hours_since_creation >= level_config['hours_after_creation']:
                # Escalate
                new_level = level_config['level']

                # Determine target user
                target_user_id = level_config.get('assign_to_user_id')
                if not target_user_id:
                    # If no specific user, keep current or use fallback
                    target_user_id = exception.assigned_to_id or 1  # Fallback to admin

                escalation_log = ExceptionEscalationLog(
                    exception_id=exception.id,
                    workflow_template_id=template.id,
                    escalation_level=new_level,
                    escalated_from_id=exception.assigned_to_id,
                    escalated_to_id=target_user_id,
                    escalation_reason=f"Automatic escalation - {level_config['hours_after_creation']} hours elapsed",
                    triggered_by="WORKFLOW",
                    notifications_sent={'channels': level_config.get('notification_channels', ['email']), 'sent': True}
                )

                exception.current_escalation_level = new_level
                exception.last_escalated_at = now
                if level_config.get('assign_to_user_id'):
                    exception.assigned_to_id = level_config['assign_to_user_id']
                if level_config.get('assign_to_role'):
                    exception.assigned_to_role = level_config['assign_to_role']

                db.add(escalation_log)
                escalated_count += 1
                break

    await db.commit()

    return {
        "success": True,
        "processed_exceptions": len(exceptions),
        "escalated_count": escalated_count,
        "timestamp": now.isoformat()
    }


@router.post("/process-auto-resolve")
async def process_auto_resolutions(
    db: AsyncSession = Depends(get_db)
):
    """
    Process automatic resolutions based on workflow templates.
    This would typically be called by a scheduler/cron job.
    """
    now = datetime.utcnow()
    resolved_count = 0
    deferred_count = 0

    # Get all active exceptions with workflow templates
    result = await db.execute(
        select(ForecastException).where(
            ForecastException.status.in_(['new', 'in_progress', 'pending']),
            ForecastException.workflow_template_id.isnot(None)
        )
    )
    exceptions = list(result.scalars().all())

    for exception in exceptions:
        tmpl_result = await db.execute(
            select(ExceptionWorkflowTemplate).where(
                ExceptionWorkflowTemplate.id == exception.workflow_template_id
            )
        )
        template = tmpl_result.scalars().first()

        if not template or not template.auto_resolve_config:
            continue

        auto_config = template.auto_resolve_config
        if not auto_config.get('enabled', False):
            continue

        # Check conditions (simplified - would need more complex logic)
        conditions = auto_config.get('conditions', {})
        should_auto_resolve = True

        # Example condition checks
        if 'max_age_hours' in conditions:
            hours_old = (now - exception.created_at).total_seconds() / 3600
            if hours_old < conditions['max_age_hours']:
                should_auto_resolve = False

        if 'min_severity' in conditions:
            severity_order = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
            if severity_order.get(exception.severity, 0) > severity_order.get(conditions['min_severity'], 0):
                should_auto_resolve = False

        if should_auto_resolve:
            action = auto_config.get('action', 'resolve')

            if action == 'resolve':
                exception.status = 'resolved'
                exception.resolved_at = now
                exception.resolution_notes = "Auto-resolved by workflow"
                resolved_count += 1
            elif action == 'defer':
                defer_hours = auto_config.get('defer_hours', 24)
                exception.deferred_until = now + timedelta(hours=defer_hours)
                exception.status = 'deferred'
                deferred_count += 1
            elif action == 'suppress':
                exception.status = 'suppressed'
                resolved_count += 1

    await db.commit()

    return {
        "success": True,
        "processed_exceptions": len(exceptions),
        "resolved_count": resolved_count,
        "deferred_count": deferred_count,
        "timestamp": now.isoformat()
    }


# ============================================================================
# Statistics and Reporting
# ============================================================================

@router.get("/stats", response_model=WorkflowStatsResponse)
async def get_workflow_statistics(
    config_id: Optional[int] = None,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Get exception workflow statistics."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    stmt = select(ForecastException).where(ForecastException.created_at >= cutoff)

    if config_id:
        stmt = stmt.where(ForecastException.config_id == config_id)

    result = await db.execute(stmt)
    exceptions = list(result.scalars().all())

    total = len(exceptions)
    pending = sum(1 for e in exceptions if e.status == 'new')
    in_progress = sum(1 for e in exceptions if e.status == 'in_progress')
    resolved = sum(1 for e in exceptions if e.status in ['resolved', 'closed'])
    escalated = sum(1 for e in exceptions if (e.current_escalation_level or 0) > 0)

    # Calculate average resolution time
    resolution_times = []
    for e in exceptions:
        if e.resolved_at and e.created_at:
            hours = (e.resolved_at - e.created_at).total_seconds() / 3600
            resolution_times.append(hours)

    avg_resolution = sum(resolution_times) / len(resolution_times) if resolution_times else None

    # Calculate SLA compliance
    sla_compliant = 0
    sla_total = 0
    for e in exceptions:
        if e.sla_deadline:
            sla_total += 1
            if e.resolved_at and e.resolved_at <= e.sla_deadline:
                sla_compliant += 1
            elif not e.resolved_at and datetime.utcnow() <= e.sla_deadline:
                sla_compliant += 1

    sla_compliance = (sla_compliant / sla_total * 100) if sla_total > 0 else None
    escalation_rate = (escalated / total * 100) if total > 0 else None

    # Group by severity and type
    by_severity = {}
    by_type = {}
    for e in exceptions:
        sev = e.severity or 'unknown'
        by_severity[sev] = by_severity.get(sev, 0) + 1

        exc_type = e.exception_type or 'unknown'
        by_type[exc_type] = by_type.get(exc_type, 0) + 1

    return WorkflowStatsResponse(
        total_exceptions=total,
        pending_exceptions=pending,
        in_progress_exceptions=in_progress,
        resolved_exceptions=resolved,
        escalated_exceptions=escalated,
        avg_resolution_time_hours=round(avg_resolution, 2) if avg_resolution else None,
        sla_compliance_rate=round(sla_compliance, 2) if sla_compliance else None,
        escalation_rate=round(escalation_rate, 2) if escalation_rate else None,
        by_severity=by_severity,
        by_type=by_type
    )


@router.get("/sla-report")
async def get_sla_report(
    config_id: Optional[int] = None,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed SLA compliance report."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    now = datetime.utcnow()

    stmt = select(ForecastException).where(
        ForecastException.created_at >= cutoff,
        ForecastException.sla_deadline.isnot(None)
    )

    if config_id:
        stmt = stmt.where(ForecastException.config_id == config_id)

    result = await db.execute(stmt)
    exceptions = list(result.scalars().all())

    breached = []
    at_risk = []
    compliant = []

    for e in exceptions:
        if e.resolved_at:
            if e.resolved_at > e.sla_deadline:
                breached.append({
                    'id': e.id,
                    'exception_type': e.exception_type,
                    'severity': e.severity,
                    'breach_hours': round((e.resolved_at - e.sla_deadline).total_seconds() / 3600, 2)
                })
            else:
                compliant.append({'id': e.id, 'exception_type': e.exception_type})
        else:
            hours_remaining = (e.sla_deadline - now).total_seconds() / 3600
            if hours_remaining < 0:
                breached.append({
                    'id': e.id,
                    'exception_type': e.exception_type,
                    'severity': e.severity,
                    'breach_hours': round(abs(hours_remaining), 2)
                })
            elif hours_remaining < 4:
                at_risk.append({
                    'id': e.id,
                    'exception_type': e.exception_type,
                    'severity': e.severity,
                    'hours_remaining': round(hours_remaining, 2)
                })
            else:
                compliant.append({'id': e.id, 'exception_type': e.exception_type})

    total = len(exceptions)

    return {
        "period_days": days,
        "total_with_sla": total,
        "compliant_count": len(compliant),
        "at_risk_count": len(at_risk),
        "breached_count": len(breached),
        "compliance_rate": round(len(compliant) / total * 100, 2) if total > 0 else None,
        "breached": breached[:20],  # Limit to 20 most recent
        "at_risk": at_risk,
        "generated_at": now.isoformat()
    }
