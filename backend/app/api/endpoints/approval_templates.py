"""
Approval Workflow Templates API Endpoints

CRUD operations for approval workflow templates and approval request management.
"""

from typing import List, Optional
from datetime import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.db.session import get_db
from app.models.user import User
from app.models.approval_template import ApprovalTemplate, ApprovalRequest, ApprovalAction
from app.api.endpoints.auth import get_current_user

router = APIRouter(prefix="/approval-templates", tags=["approval-templates", "workflow"])
logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Schemas
# ============================================================================

class ApprovalLevelConfig(BaseModel):
    """Configuration for a single approval level."""
    level: int = Field(..., ge=1, le=10)
    name: str = Field(..., min_length=1, max_length=100)
    approvers: List[int] = Field(..., min_items=1, description="List of user IDs who can approve")
    type: str = Field("any", description="'any' = any approver, 'all' = all approvers required")
    timeout_hours: Optional[int] = Field(None, ge=1, le=720, description="Hours before escalation")


class ApprovalConditions(BaseModel):
    """Conditions for template applicability."""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    categories: Optional[List[str]] = None
    regions: Optional[List[str]] = None


class CreateTemplateRequest(BaseModel):
    """Request to create an approval template."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    code: str = Field(..., min_length=1, max_length=50)
    entity_type: str = Field(..., description="purchase_order, transfer_order, etc.")
    levels: List[ApprovalLevelConfig]
    conditions: Optional[ApprovalConditions] = None
    is_active: bool = True
    is_default: bool = False
    priority: int = Field(100, ge=1, le=1000)
    auto_approve_below: Optional[float] = None
    auto_escalate_after_hours: Optional[int] = None


class UpdateTemplateRequest(BaseModel):
    """Request to update an approval template."""
    name: Optional[str] = None
    description: Optional[str] = None
    levels: Optional[List[ApprovalLevelConfig]] = None
    conditions: Optional[ApprovalConditions] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    priority: Optional[int] = None
    auto_approve_below: Optional[float] = None
    auto_escalate_after_hours: Optional[int] = None


class TemplateResponse(BaseModel):
    """Approval template response."""
    id: int
    name: str
    description: Optional[str]
    code: str
    entity_type: str
    levels: List[dict]
    conditions: Optional[dict]
    is_active: bool
    is_default: bool
    priority: int
    auto_approve_below: Optional[float]
    auto_escalate_after_hours: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CreateApprovalRequest(BaseModel):
    """Request to create an approval request."""
    entity_type: str
    entity_id: str
    title: str
    description: Optional[str] = None
    value: Optional[float] = None
    metadata: Optional[dict] = None


class ApprovalRequestResponse(BaseModel):
    """Approval request response."""
    id: int
    template_id: int
    template_name: Optional[str] = None
    entity_type: str
    entity_id: str
    title: str
    description: Optional[str]
    value: Optional[float]
    status: str
    current_level: int
    total_levels: int = 0
    requested_by_id: int
    requested_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class ApproveRejectRequest(BaseModel):
    """Request to approve or reject."""
    action: str = Field(..., description="approved or rejected")
    comment: Optional[str] = None


# ============================================================================
# Template CRUD Endpoints
# ============================================================================

@router.post("/", response_model=TemplateResponse)
async def create_template(
    request: CreateTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new approval workflow template."""
    # Check for duplicate code
    result = await db.execute(
        select(ApprovalTemplate).where(ApprovalTemplate.code == request.code)
    )
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Template with code '{request.code}' already exists")

    # If setting as default, unset other defaults for this entity type
    if request.is_default:
        await db.execute(
            update(ApprovalTemplate).where(
                ApprovalTemplate.entity_type == request.entity_type,
                ApprovalTemplate.is_default == True
            ).values(is_default=False)
        )

    template = ApprovalTemplate(
        name=request.name,
        description=request.description,
        code=request.code,
        entity_type=request.entity_type,
        levels=[level.dict() for level in request.levels],
        conditions=request.conditions.dict() if request.conditions else None,
        is_active=request.is_active,
        is_default=request.is_default,
        priority=request.priority,
        auto_approve_below=request.auto_approve_below,
        auto_escalate_after_hours=request.auto_escalate_after_hours,
        created_by_id=current_user.id,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    logger.info(f"Created approval template: {template.code} by {current_user.email}")
    return template


@router.get("/", response_model=List[TemplateResponse])
async def list_templates(
    entity_type: Optional[str] = Query(None),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List approval templates with optional filtering."""
    stmt = select(ApprovalTemplate)

    if entity_type:
        stmt = stmt.where(ApprovalTemplate.entity_type == entity_type)
    if active_only:
        stmt = stmt.where(ApprovalTemplate.is_active == True)

    stmt = stmt.order_by(ApprovalTemplate.priority, ApprovalTemplate.name)
    result = await db.execute(stmt)
    templates = list(result.scalars().all())
    return templates


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific approval template."""
    result = await db.execute(
        select(ApprovalTemplate).where(ApprovalTemplate.id == template_id)
    )
    template = result.scalars().first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    request: UpdateTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an approval template."""
    result = await db.execute(
        select(ApprovalTemplate).where(ApprovalTemplate.id == template_id)
    )
    template = result.scalars().first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # If setting as default, unset other defaults
    if request.is_default:
        await db.execute(
            update(ApprovalTemplate).where(
                ApprovalTemplate.entity_type == template.entity_type,
                ApprovalTemplate.id != template_id,
                ApprovalTemplate.is_default == True
            ).values(is_default=False)
        )

    # Update fields
    if request.name is not None:
        template.name = request.name
    if request.description is not None:
        template.description = request.description
    if request.levels is not None:
        template.levels = [level.dict() for level in request.levels]
    if request.conditions is not None:
        template.conditions = request.conditions.dict()
    if request.is_active is not None:
        template.is_active = request.is_active
    if request.is_default is not None:
        template.is_default = request.is_default
    if request.priority is not None:
        template.priority = request.priority
    if request.auto_approve_below is not None:
        template.auto_approve_below = request.auto_approve_below
    if request.auto_escalate_after_hours is not None:
        template.auto_escalate_after_hours = request.auto_escalate_after_hours

    await db.commit()
    await db.refresh(template)

    logger.info(f"Updated approval template: {template.code} by {current_user.email}")
    return template


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an approval template (soft delete - set inactive)."""
    result = await db.execute(
        select(ApprovalTemplate).where(ApprovalTemplate.id == template_id)
    )
    template = result.scalars().first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Check if template has active requests
    count_result = await db.execute(
        select(func.count()).select_from(ApprovalRequest).where(
            ApprovalRequest.template_id == template_id,
            ApprovalRequest.status.in_(['pending', 'in_progress'])
        )
    )
    active_requests = count_result.scalar() or 0

    if active_requests > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete template with {active_requests} active requests"
        )

    template.is_active = False
    await db.commit()

    logger.info(f"Deleted approval template: {template.code} by {current_user.email}")
    return {"success": True, "message": "Template deactivated"}


# ============================================================================
# Approval Request Endpoints
# ============================================================================

@router.post("/requests", response_model=ApprovalRequestResponse)
async def create_approval_request(
    request: CreateApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new approval request for an entity."""
    # Find applicable template
    result = await db.execute(
        select(ApprovalTemplate).where(
            ApprovalTemplate.entity_type == request.entity_type,
            ApprovalTemplate.is_active == True
        ).order_by(ApprovalTemplate.priority)
    )
    templates = list(result.scalars().all())

    selected_template = None
    for template in templates:
        if _template_matches_conditions(template, request.value):
            selected_template = template
            break

    if not selected_template:
        # Use default template if exists
        default_result = await db.execute(
            select(ApprovalTemplate).where(
                ApprovalTemplate.entity_type == request.entity_type,
                ApprovalTemplate.is_default == True,
                ApprovalTemplate.is_active == True
            )
        )
        selected_template = default_result.scalars().first()

    if not selected_template:
        raise HTTPException(
            status_code=400,
            detail=f"No approval template found for entity type '{request.entity_type}'"
        )

    # Check for auto-approval
    if selected_template.auto_approve_below and request.value:
        if request.value < selected_template.auto_approve_below:
            # Auto-approve
            logger.info(
                f"Auto-approved {request.entity_type} {request.entity_id} "
                f"(value {request.value} < {selected_template.auto_approve_below})"
            )
            return ApprovalRequestResponse(
                id=0,
                template_id=selected_template.id,
                template_name=selected_template.name,
                entity_type=request.entity_type,
                entity_id=request.entity_id,
                title=request.title,
                description=request.description,
                value=request.value,
                status='approved',
                current_level=0,
                total_levels=len(selected_template.levels),
                requested_by_id=current_user.id,
                requested_at=datetime.utcnow(),
                completed_at=datetime.utcnow()
            )

    # Create approval request
    approval_request = ApprovalRequest(
        template_id=selected_template.id,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        title=request.title,
        description=request.description,
        value=request.value,
        metadata=request.metadata,
        status='pending',
        current_level=1,
        requested_by_id=current_user.id,
    )
    db.add(approval_request)
    await db.commit()
    await db.refresh(approval_request)

    logger.info(
        f"Created approval request: {approval_request.id} for "
        f"{request.entity_type} {request.entity_id} by {current_user.email}"
    )

    return ApprovalRequestResponse(
        id=approval_request.id,
        template_id=selected_template.id,
        template_name=selected_template.name,
        entity_type=approval_request.entity_type,
        entity_id=approval_request.entity_id,
        title=approval_request.title,
        description=approval_request.description,
        value=approval_request.value,
        status=approval_request.status,
        current_level=approval_request.current_level,
        total_levels=len(selected_template.levels),
        requested_by_id=approval_request.requested_by_id,
        requested_at=approval_request.requested_at,
        completed_at=approval_request.completed_at
    )


@router.get("/requests", response_model=List[ApprovalRequestResponse])
async def list_approval_requests(
    status: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    pending_for_me: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List approval requests with filtering."""
    stmt = select(ApprovalRequest)

    if status:
        stmt = stmt.where(ApprovalRequest.status == status)
    if entity_type:
        stmt = stmt.where(ApprovalRequest.entity_type == entity_type)

    stmt = stmt.order_by(ApprovalRequest.requested_at.desc()).limit(100)
    result = await db.execute(stmt)
    requests = list(result.scalars().all())

    # Get template names
    template_ids = list(set(r.template_id for r in requests))
    if template_ids:
        tmpl_result = await db.execute(
            select(ApprovalTemplate).where(ApprovalTemplate.id.in_(template_ids))
        )
        templates = {t.id: t for t in tmpl_result.scalars().all()}
    else:
        templates = {}

    response = []
    for req in requests:
        template = templates.get(req.template_id)
        response.append(ApprovalRequestResponse(
            id=req.id,
            template_id=req.template_id,
            template_name=template.name if template else None,
            entity_type=req.entity_type,
            entity_id=req.entity_id,
            title=req.title,
            description=req.description,
            value=req.value,
            status=req.status,
            current_level=req.current_level,
            total_levels=len(template.levels) if template else 0,
            requested_by_id=req.requested_by_id,
            requested_at=req.requested_at,
            completed_at=req.completed_at
        ))

    return response


@router.post("/requests/{request_id}/action")
async def process_approval_action(
    request_id: int,
    action_request: ApproveRejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Process an approval or rejection action on a request."""
    result = await db.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == request_id)
    )
    approval_request = result.scalars().first()
    if not approval_request:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if approval_request.status not in ['pending', 'in_progress']:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot process request with status '{approval_request.status}'"
        )

    # Get template to check approvers
    tmpl_result = await db.execute(
        select(ApprovalTemplate).where(ApprovalTemplate.id == approval_request.template_id)
    )
    template = tmpl_result.scalars().first()
    if not template:
        raise HTTPException(status_code=500, detail="Template not found")

    # Verify user is an approver at current level
    current_level_config = None
    for level in template.levels:
        if level['level'] == approval_request.current_level:
            current_level_config = level
            break

    if not current_level_config:
        raise HTTPException(status_code=500, detail="Level configuration not found")

    if current_user.id not in current_level_config.get('approvers', []):
        raise HTTPException(status_code=403, detail="You are not an approver at this level")

    # Record action
    action = ApprovalAction(
        request_id=request_id,
        level=approval_request.current_level,
        action=action_request.action,
        actor_id=current_user.id,
        comment=action_request.comment
    )
    db.add(action)

    # Process action
    if action_request.action == 'rejected':
        approval_request.status = 'rejected'
        approval_request.completed_at = datetime.utcnow()
        approval_request.final_decision_by_id = current_user.id
    elif action_request.action == 'approved':
        # Check if more levels
        if approval_request.current_level < len(template.levels):
            approval_request.current_level += 1
            approval_request.status = 'in_progress'
        else:
            approval_request.status = 'approved'
            approval_request.completed_at = datetime.utcnow()
            approval_request.final_decision_by_id = current_user.id

    await db.commit()

    logger.info(
        f"Approval action: {action_request.action} on request {request_id} "
        f"by {current_user.email}"
    )

    return {
        "success": True,
        "request_id": request_id,
        "action": action_request.action,
        "new_status": approval_request.status,
        "current_level": approval_request.current_level
    }


def _template_matches_conditions(template: ApprovalTemplate, value: Optional[float]) -> bool:
    """Check if template conditions match the request."""
    if not template.conditions:
        return True

    conditions = template.conditions

    # Check value range
    if value is not None:
        if conditions.get('min_value') and value < conditions['min_value']:
            return False
        if conditions.get('max_value') and value > conditions['max_value']:
            return False

    return True
