"""
Sync Job Pydantic Schemas

Request/response models for SAP data sync job API.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class SyncDataTypeEnum(str, Enum):
    """Data types that can be synced from SAP."""
    MATERIAL_MASTER = "material_master"
    VENDOR_MASTER = "vendor_master"
    CUSTOMER_MASTER = "customer_master"
    BOM = "bom"
    ROUTING = "routing"
    WORK_CENTER = "work_center"
    INVENTORY = "inventory"
    PURCHASE_ORDERS = "purchase_orders"
    SALES_ORDERS = "sales_orders"
    PRODUCTION_ORDERS = "production_orders"
    DEMAND_FORECAST = "demand_forecast"
    ATP = "atp"
    PRICING = "pricing"


class SyncStatusEnum(str, Enum):
    """Status of sync job execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


# ============================================================================
# Sync Job Config Schemas
# ============================================================================

class SyncJobConfigBase(BaseModel):
    """Base schema for sync job configuration."""
    name: str = Field(..., max_length=200, description="Descriptive name for the sync job")
    data_type: SyncDataTypeEnum = Field(..., description="Type of data to sync")
    cron_expression: str = Field(..., max_length=100, description="Cron schedule (e.g., '0 2 * * *' for daily 2 AM)")

    is_enabled: bool = Field(default=True, description="Whether the job is active")
    is_delta_load: bool = Field(default=True, description="Use delta (incremental) loading")
    use_claude_ai: bool = Field(default=True, description="Enable Claude AI for validation")

    lookback_days: int = Field(default=7, ge=0, le=365, description="Days to look back for delta loads")

    sap_connection_params: Optional[Dict[str, Any]] = Field(
        default=None, description="SAP connection parameters override"
    )
    table_mapping: Optional[Dict[str, str]] = Field(
        default=None, description="Custom table name mappings"
    )
    field_mapping: Optional[Dict[str, str]] = Field(
        default=None, description="Custom field mappings"
    )
    filter_criteria: Optional[Dict[str, Any]] = Field(
        default=None, description="Data filter criteria"
    )

    retry_attempts: int = Field(default=3, ge=0, le=10, description="Number of retry attempts on failure")
    retry_delay_seconds: int = Field(default=60, ge=0, le=3600, description="Delay between retries")
    timeout_minutes: int = Field(default=30, ge=1, le=480, description="Job timeout in minutes")

    notification_emails: Optional[List[str]] = Field(
        default=None, description="Email addresses for notifications"
    )
    workflow_template_id: Optional[int] = Field(
        default=None, description="Workflow to trigger after sync"
    )


class SyncJobConfigCreate(SyncJobConfigBase):
    """Schema for creating a sync job configuration."""
    customer_id: int = Field(..., gt=0, description="Customer this config belongs to")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Daily Material Master Sync",
                "data_type": "material_master",
                "cron_expression": "0 2 * * *",
                "customer_id": 1,
                "is_enabled": True,
                "is_delta_load": True,
                "lookback_days": 1,
                "retry_attempts": 3,
                "timeout_minutes": 30
            }
        }


class SyncJobConfigUpdate(BaseModel):
    """Schema for updating a sync job configuration."""
    name: Optional[str] = Field(None, max_length=200)
    cron_expression: Optional[str] = Field(None, max_length=100)
    is_enabled: Optional[bool] = None
    is_delta_load: Optional[bool] = None
    use_claude_ai: Optional[bool] = None
    lookback_days: Optional[int] = Field(None, ge=0, le=365)
    retry_attempts: Optional[int] = Field(None, ge=0, le=10)
    retry_delay_seconds: Optional[int] = Field(None, ge=0, le=3600)
    timeout_minutes: Optional[int] = Field(None, ge=1, le=480)
    notification_emails: Optional[List[str]] = None
    workflow_template_id: Optional[int] = None


class SyncJobConfigResponse(SyncJobConfigBase):
    """Schema for sync job configuration response."""
    id: int
    customer_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_execution_at: Optional[datetime] = None
    next_execution_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "name": "Daily Material Master Sync",
                "data_type": "material_master",
                "cron_expression": "0 2 * * *",
                "customer_id": 1,
                "is_enabled": True,
                "is_delta_load": True,
                "lookback_days": 1,
                "created_at": "2026-02-01T10:00:00Z",
                "next_execution_at": "2026-02-02T02:00:00Z"
            }
        }


# ============================================================================
# Sync Job Execution Schemas
# ============================================================================

class SyncJobExecutionResponse(BaseModel):
    """Schema for sync job execution response."""
    id: int
    config_id: int
    config_name: Optional[str] = None
    status: SyncStatusEnum

    started_at: datetime
    completed_at: Optional[datetime] = None

    records_processed: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    records_deleted: int = 0
    records_failed: int = 0

    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None

    execution_metrics: Optional[Dict[str, Any]] = None

    triggered_workflow_id: Optional[int] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 123,
                "config_id": 1,
                "config_name": "Daily Material Master Sync",
                "status": "completed",
                "started_at": "2026-02-01T02:00:00Z",
                "completed_at": "2026-02-01T02:15:30Z",
                "records_processed": 15000,
                "records_inserted": 250,
                "records_updated": 1200,
                "records_deleted": 0,
                "records_failed": 5,
                "triggered_workflow_id": 45
            }
        }


class SyncTableResultResponse(BaseModel):
    """Schema for sync table result response."""
    id: int
    execution_id: int
    table_name: str
    status: SyncStatusEnum

    started_at: datetime
    completed_at: Optional[datetime] = None

    records_read: int = 0
    records_written: int = 0
    records_failed: int = 0

    error_message: Optional[str] = None

    class Config:
        from_attributes = True


# ============================================================================
# Request/Response for Operations
# ============================================================================

class SyncJobTriggerRequest(BaseModel):
    """Request to manually trigger a sync job."""
    force_full_load: bool = Field(default=False, description="Force full load instead of delta")
    custom_lookback_days: Optional[int] = Field(
        None, ge=0, le=365, description="Override lookback days"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "force_full_load": False,
                "custom_lookback_days": 14
            }
        }


class SyncJobTriggerResponse(BaseModel):
    """Response from manual sync job trigger."""
    execution_id: int
    config_id: int
    status: SyncStatusEnum
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "execution_id": 124,
                "config_id": 1,
                "status": "running",
                "message": "Sync job started successfully"
            }
        }


class SyncJobListResponse(BaseModel):
    """Response for listing sync job configs."""
    items: List[SyncJobConfigResponse]
    total: int
    page: int
    page_size: int


class SyncExecutionListResponse(BaseModel):
    """Response for listing sync job executions."""
    items: List[SyncJobExecutionResponse]
    total: int
    page: int
    page_size: int


class DefaultCadenceResponse(BaseModel):
    """Response with default cadence configuration."""
    data_type: SyncDataTypeEnum
    cron_expression: str
    lookback_days: int
    sap_tables: List[str]
    description: str


class DefaultCadencesResponse(BaseModel):
    """Response listing all default cadences."""
    cadences: List[DefaultCadenceResponse]
