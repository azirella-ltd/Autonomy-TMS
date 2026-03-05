"""
Workflow Pydantic Schemas

Request/response models for workflow API.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class WorkflowStatusEnum(str, Enum):
    """Status of workflow execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class WorkflowStepTypeEnum(str, Enum):
    """Type of workflow step."""
    VALIDATE = "validate"
    TRANSFORM = "transform"
    ANALYTICS = "analytics"
    INSIGHTS = "insights"
    NOTIFY = "notify"
    PLAN_UPDATE = "plan_update"
    SNAPSHOT = "snapshot"
    ATP_REFRESH = "atp_refresh"
    RECONCILE = "reconcile"
    CUSTOM = "custom"


class WorkflowTriggerTypeEnum(str, Enum):
    """Type of workflow trigger."""
    MANUAL = "manual"
    POST_SYNC = "post_sync"
    SCHEDULED = "scheduled"
    EVENT = "event"


# ============================================================================
# Workflow Step Schemas
# ============================================================================

class WorkflowStepConfigSchema(BaseModel):
    """Configuration for a workflow step."""
    step_order: int = Field(..., ge=1, description="Order of step execution")
    step_type: WorkflowStepTypeEnum = Field(..., description="Type of step to execute")
    step_name: str = Field(..., max_length=100, description="Display name for the step")
    step_config: Optional[Dict[str, Any]] = Field(
        default=None, description="Step-specific configuration"
    )
    timeout_seconds: int = Field(default=300, ge=0, le=3600, description="Step timeout")
    continue_on_failure: bool = Field(default=False, description="Continue workflow if step fails")

    class Config:
        json_schema_extra = {
            "example": {
                "step_order": 1,
                "step_type": "validate",
                "step_name": "Data Quality Check",
                "step_config": {"check_nulls": True, "check_duplicates": True},
                "timeout_seconds": 300,
                "continue_on_failure": False
            }
        }


# ============================================================================
# Workflow Template Schemas
# ============================================================================

class WorkflowTemplateBase(BaseModel):
    """Base schema for workflow template."""
    name: str = Field(..., max_length=200, description="Template name")
    description: Optional[str] = Field(None, max_length=1000, description="Template description")
    trigger_type: WorkflowTriggerTypeEnum = Field(..., description="How the workflow is triggered")
    is_enabled: bool = Field(default=True, description="Whether template is active")

    steps: List[WorkflowStepConfigSchema] = Field(
        ..., min_length=1, max_length=20, description="Workflow steps"
    )

    notification_config: Optional[Dict[str, Any]] = Field(
        default=None, description="Notification settings"
    )


class WorkflowTemplateCreate(WorkflowTemplateBase):
    """Schema for creating a workflow template."""
    tenant_id: Optional[int] = Field(None, gt=0, description="Tenant this template belongs to (auto-set from auth)")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Post-Sync Analytics Pipeline",
                "description": "Run analytics after SAP data sync",
                "trigger_type": "post_sync",
                "tenant_id": 1,
                "is_enabled": True,
                "steps": [
                    {
                        "step_order": 1,
                        "step_type": "validate",
                        "step_name": "Data Quality Check",
                        "timeout_seconds": 300
                    },
                    {
                        "step_order": 2,
                        "step_type": "analytics",
                        "step_name": "Inventory Projections",
                        "timeout_seconds": 600
                    },
                    {
                        "step_order": 3,
                        "step_type": "insights",
                        "step_name": "Generate Recommendations",
                        "timeout_seconds": 300
                    },
                    {
                        "step_order": 4,
                        "step_type": "notify",
                        "step_name": "Send Alerts",
                        "timeout_seconds": 60
                    }
                ]
            }
        }


class WorkflowTemplateUpdate(BaseModel):
    """Schema for updating a workflow template."""
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    is_enabled: Optional[bool] = None
    steps: Optional[List[WorkflowStepConfigSchema]] = None
    notification_config: Optional[Dict[str, Any]] = None


class WorkflowTemplateResponse(WorkflowTemplateBase):
    """Schema for workflow template response."""
    id: int
    tenant_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by_id: Optional[int] = None

    class Config:
        from_attributes = True


# ============================================================================
# Workflow Execution Schemas
# ============================================================================

class WorkflowStepExecutionResponse(BaseModel):
    """Schema for workflow step execution response."""
    id: int
    workflow_execution_id: int
    step_order: int
    step_type: WorkflowStepTypeEnum
    step_name: str
    status: WorkflowStatusEnum

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class WorkflowExecutionResponse(BaseModel):
    """Schema for workflow execution response."""
    id: int
    template_id: int
    template_name: Optional[str] = None
    status: WorkflowStatusEnum

    triggered_by: WorkflowTriggerTypeEnum
    trigger_source_id: Optional[int] = None
    trigger_source_type: Optional[str] = None

    started_at: datetime
    completed_at: Optional[datetime] = None

    context_data: Optional[Dict[str, Any]] = None
    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    steps: Optional[List[WorkflowStepExecutionResponse]] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 45,
                "template_id": 1,
                "template_name": "Post-Sync Analytics Pipeline",
                "status": "completed",
                "triggered_by": "post_sync",
                "trigger_source_id": 123,
                "trigger_source_type": "sync_execution",
                "started_at": "2026-02-01T02:15:30Z",
                "completed_at": "2026-02-01T02:18:45Z"
            }
        }


# ============================================================================
# Request/Response for Operations
# ============================================================================

class WorkflowTriggerRequest(BaseModel):
    """Request to manually trigger a workflow."""
    context_data: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional context data for workflow"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "context_data": {
                    "reason": "Manual verification run",
                    "requested_by": "admin@example.com"
                }
            }
        }


class WorkflowTriggerResponse(BaseModel):
    """Response from workflow trigger."""
    execution_id: int
    template_id: int
    status: WorkflowStatusEnum
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "execution_id": 46,
                "template_id": 1,
                "status": "running",
                "message": "Workflow started successfully"
            }
        }


class WorkflowCancelResponse(BaseModel):
    """Response from workflow cancellation."""
    execution_id: int
    status: WorkflowStatusEnum
    message: str


class WorkflowTemplateListResponse(BaseModel):
    """Response for listing workflow templates."""
    items: List[WorkflowTemplateResponse]
    total: int
    page: int
    page_size: int


class WorkflowExecutionListResponse(BaseModel):
    """Response for listing workflow executions."""
    items: List[WorkflowExecutionResponse]
    total: int
    page: int
    page_size: int


class DefaultWorkflowTemplateResponse(BaseModel):
    """Response with a default workflow template."""
    name: str
    description: str
    trigger_type: WorkflowTriggerTypeEnum
    steps: List[WorkflowStepConfigSchema]


class DefaultWorkflowTemplatesResponse(BaseModel):
    """Response listing all default workflow templates."""
    templates: List[DefaultWorkflowTemplateResponse]
