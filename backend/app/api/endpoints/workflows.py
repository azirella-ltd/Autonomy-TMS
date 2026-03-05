"""
Workflows API Endpoints

CRUD operations and management for workflow templates and executions.
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.models.workflow import (
    WorkflowTemplate, WorkflowExecution, WorkflowStepExecution,
    WorkflowStatus, WorkflowStepType, WorkflowTriggerType,
    DEFAULT_WORKFLOW_TEMPLATES
)
from app.models.user import User
from app.schemas.workflow import (
    WorkflowTemplateCreate, WorkflowTemplateUpdate, WorkflowTemplateResponse,
    WorkflowExecutionResponse, WorkflowStepExecutionResponse,
    WorkflowTriggerRequest, WorkflowTriggerResponse, WorkflowCancelResponse,
    WorkflowTemplateListResponse, WorkflowExecutionListResponse,
    DefaultWorkflowTemplateResponse, DefaultWorkflowTemplatesResponse,
    WorkflowStepConfigSchema,
)
from app.services.workflow_service import WorkflowService

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Workflow Templates
# ============================================================================

@router.get("/templates", response_model=WorkflowTemplateListResponse)
def list_workflow_templates(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    trigger_type: Optional[WorkflowTriggerType] = None,
    is_enabled: Optional[bool] = None,
):
    """List workflow templates for the user's customer."""
    query = db.query(WorkflowTemplate).filter(
        WorkflowTemplate.tenant_id == current_user.tenant_id
    )

    if trigger_type:
        query = query.filter(WorkflowTemplate.trigger_type == trigger_type)
    if is_enabled is not None:
        query = query.filter(WorkflowTemplate.is_enabled == is_enabled)

    total = query.count()
    items = query.order_by(WorkflowTemplate.name).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return WorkflowTemplateListResponse(
        items=[WorkflowTemplateResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("/templates", response_model=WorkflowTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_workflow_template(
    template_in: WorkflowTemplateCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Create a new workflow template."""
    # Verify user has access to the tenant
    template_tenant_id = getattr(template_in, 'tenant_id', None) or getattr(template_in, 'customer_id', None)
    if template_tenant_id and template_tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create template for a different tenant"
        )

    # Convert steps to JSON-serializable format
    steps_data = [step.model_dump() for step in template_in.steps]

    template = WorkflowTemplate(
        tenant_id=current_user.tenant_id,
        name=template_in.name,
        description=template_in.description,
        trigger_type=template_in.trigger_type,
        is_enabled=template_in.is_enabled,
        steps=steps_data,
        notification_config=template_in.notification_config,
        created_by_id=current_user.id,
    )

    db.add(template)
    db.commit()
    db.refresh(template)

    return WorkflowTemplateResponse.model_validate(template)


@router.get("/templates/{template_id}", response_model=WorkflowTemplateResponse)
def get_workflow_template(
    template_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get a specific workflow template."""
    template = db.query(WorkflowTemplate).filter(
        WorkflowTemplate.id == template_id,
        WorkflowTemplate.tenant_id == current_user.tenant_id
    ).first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow template not found"
        )

    return WorkflowTemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=WorkflowTemplateResponse)
def update_workflow_template(
    template_id: int,
    template_in: WorkflowTemplateUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Update a workflow template."""
    template = db.query(WorkflowTemplate).filter(
        WorkflowTemplate.id == template_id,
        WorkflowTemplate.tenant_id == current_user.tenant_id
    ).first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow template not found"
        )

    update_data = template_in.model_dump(exclude_unset=True)

    # Handle steps conversion
    if "steps" in update_data and update_data["steps"]:
        update_data["steps"] = [step.model_dump() if hasattr(step, 'model_dump') else step
                                for step in update_data["steps"]]

    for field, value in update_data.items():
        setattr(template, field, value)

    template.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(template)

    return WorkflowTemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow_template(
    template_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Delete a workflow template."""
    template = db.query(WorkflowTemplate).filter(
        WorkflowTemplate.id == template_id,
        WorkflowTemplate.tenant_id == current_user.tenant_id
    ).first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow template not found"
        )

    # Check for running executions
    running = db.query(WorkflowExecution).filter(
        WorkflowExecution.template_id == template_id,
        WorkflowExecution.status == WorkflowStatus.RUNNING
    ).count()

    if running > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete template with {running} running execution(s)"
        )

    db.delete(template)
    db.commit()


@router.post("/templates/{template_id}/trigger", response_model=WorkflowTriggerResponse)
async def trigger_workflow(
    template_id: int,
    trigger_request: WorkflowTriggerRequest = None,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Manually trigger a workflow."""
    template = db.query(WorkflowTemplate).filter(
        WorkflowTemplate.id == template_id,
        WorkflowTemplate.tenant_id == current_user.tenant_id
    ).first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow template not found"
        )

    if not template.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workflow template is disabled"
        )

    service = WorkflowService(db)
    context_data = trigger_request.context_data if trigger_request else None

    try:
        execution = await service.trigger_manual_workflow(
            template_id=template_id,
            triggered_by_id=current_user.id,
            context_data=context_data
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    return WorkflowTriggerResponse(
        execution_id=execution.id,
        template_id=template_id,
        status=execution.status,
        message="Workflow triggered successfully"
    )


@router.post("/templates/{template_id}/enable", response_model=WorkflowTemplateResponse)
def enable_workflow_template(
    template_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Enable a workflow template."""
    template = db.query(WorkflowTemplate).filter(
        WorkflowTemplate.id == template_id,
        WorkflowTemplate.tenant_id == current_user.tenant_id
    ).first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow template not found"
        )

    template.is_enabled = True
    template.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(template)

    return WorkflowTemplateResponse.model_validate(template)


@router.post("/templates/{template_id}/disable", response_model=WorkflowTemplateResponse)
def disable_workflow_template(
    template_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Disable a workflow template."""
    template = db.query(WorkflowTemplate).filter(
        WorkflowTemplate.id == template_id,
        WorkflowTemplate.tenant_id == current_user.tenant_id
    ).first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow template not found"
        )

    template.is_enabled = False
    template.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(template)

    return WorkflowTemplateResponse.model_validate(template)


# ============================================================================
# Workflow Executions
# ============================================================================

@router.get("/executions", response_model=WorkflowExecutionListResponse)
def list_workflow_executions(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    template_id: Optional[int] = None,
    status_filter: Optional[WorkflowStatus] = Query(None, alias="status"),
):
    """List workflow executions for the user's customer."""
    query = db.query(WorkflowExecution).join(WorkflowTemplate).filter(
        WorkflowTemplate.tenant_id == current_user.tenant_id
    )

    if template_id:
        query = query.filter(WorkflowExecution.template_id == template_id)
    if status_filter:
        query = query.filter(WorkflowExecution.status == status_filter)

    total = query.count()
    items = query.order_by(WorkflowExecution.started_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    # Add template name to response
    result_items = []
    for item in items:
        response = WorkflowExecutionResponse.model_validate(item)
        response.template_name = item.template.name if item.template else None
        result_items.append(response)

    return WorkflowExecutionListResponse(
        items=result_items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/executions/{execution_id}", response_model=WorkflowExecutionResponse)
def get_workflow_execution(
    execution_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    include_steps: bool = Query(True, description="Include step execution details"),
):
    """Get a specific workflow execution."""
    execution = db.query(WorkflowExecution).join(WorkflowTemplate).filter(
        WorkflowExecution.id == execution_id,
        WorkflowTemplate.tenant_id == current_user.tenant_id
    ).first()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow execution not found"
        )

    response = WorkflowExecutionResponse.model_validate(execution)
    response.template_name = execution.template.name if execution.template else None

    if include_steps:
        steps = db.query(WorkflowStepExecution).filter(
            WorkflowStepExecution.workflow_execution_id == execution_id
        ).order_by(WorkflowStepExecution.step_order).all()
        response.steps = [WorkflowStepExecutionResponse.model_validate(s) for s in steps]

    return response


@router.post("/executions/{execution_id}/cancel", response_model=WorkflowCancelResponse)
def cancel_workflow_execution(
    execution_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Cancel a running workflow execution."""
    execution = db.query(WorkflowExecution).join(WorkflowTemplate).filter(
        WorkflowExecution.id == execution_id,
        WorkflowTemplate.tenant_id == current_user.tenant_id
    ).first()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow execution not found"
        )

    if execution.status not in [WorkflowStatus.RUNNING, WorkflowStatus.PENDING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel execution with status: {execution.status.value}"
        )

    execution.status = WorkflowStatus.CANCELLED
    execution.completed_at = datetime.utcnow()
    execution.error_message = "Cancelled by user"
    db.commit()
    db.refresh(execution)

    return WorkflowCancelResponse(
        execution_id=execution.id,
        status=execution.status,
        message="Workflow execution cancelled"
    )


# ============================================================================
# Default Templates
# ============================================================================

@router.get("/defaults", response_model=DefaultWorkflowTemplatesResponse)
def get_default_workflow_templates(
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get default workflow template configurations."""
    templates = []
    for name, config in DEFAULT_WORKFLOW_TEMPLATES.items():
        steps = [
            WorkflowStepConfigSchema(
                step_order=step["step_order"],
                step_type=step["step_type"],
                step_name=step["step_name"],
                step_config=step.get("step_config"),
                timeout_seconds=step.get("timeout_seconds", 300),
                continue_on_failure=step.get("continue_on_failure", False)
            )
            for step in config["steps"]
        ]
        templates.append(DefaultWorkflowTemplateResponse(
            name=name,
            description=config.get("description", ""),
            trigger_type=config["trigger_type"],
            steps=steps
        ))

    return DefaultWorkflowTemplatesResponse(templates=templates)


@router.post("/templates/from-defaults", response_model=list[WorkflowTemplateResponse], status_code=status.HTTP_201_CREATED)
def create_templates_from_defaults(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    template_names: Optional[list[str]] = None,
):
    """Create workflow templates from defaults for the user's customer."""
    created_templates = []

    names_to_create = template_names if template_names else list(DEFAULT_WORKFLOW_TEMPLATES.keys())

    for name in names_to_create:
        if name not in DEFAULT_WORKFLOW_TEMPLATES:
            continue

        defaults = DEFAULT_WORKFLOW_TEMPLATES[name]

        # Check if template already exists
        existing = db.query(WorkflowTemplate).filter(
            WorkflowTemplate.tenant_id == current_user.tenant_id,
            WorkflowTemplate.name == name
        ).first()

        if existing:
            continue

        template = WorkflowTemplate(
            tenant_id=current_user.tenant_id,
            name=name,
            description=defaults.get("description", ""),
            trigger_type=defaults["trigger_type"],
            is_enabled=False,  # Start disabled by default
            steps=defaults["steps"],
            created_by_id=current_user.id,
        )

        db.add(template)
        created_templates.append(template)

    db.commit()

    # Refresh and return
    for template in created_templates:
        db.refresh(template)

    return [WorkflowTemplateResponse.model_validate(t) for t in created_templates]
