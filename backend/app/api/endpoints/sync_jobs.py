"""
Sync Jobs API Endpoints

CRUD operations and management for SAP data sync jobs.
"""

import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.models.sync_job import (
    SyncJobConfig, SyncJobExecution, SyncTableResult,
    SyncDataType, SyncStatus, DEFAULT_SYNC_CADENCES
)
from app.models.user import User
from app.schemas.sync_job import (
    SyncJobConfigCreate, SyncJobConfigUpdate, SyncJobConfigResponse,
    SyncJobExecutionResponse, SyncTableResultResponse,
    SyncJobTriggerRequest, SyncJobTriggerResponse,
    SyncJobListResponse, SyncExecutionListResponse,
    DefaultCadenceResponse, DefaultCadencesResponse,
)
from app.services.sync_scheduler_service import SyncSchedulerService

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Sync Job Configs
# ============================================================================

@router.get("/configs", response_model=SyncJobListResponse)
def list_sync_configs(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    data_type: Optional[SyncDataType] = None,
    is_enabled: Optional[bool] = None,
):
    """List sync job configurations for the user's customer."""
    query = db.query(SyncJobConfig).filter(
        SyncJobConfig.tenant_id == current_user.tenant_id
    )

    if data_type:
        query = query.filter(SyncJobConfig.data_type == data_type)
    if is_enabled is not None:
        query = query.filter(SyncJobConfig.is_enabled == is_enabled)

    total = query.count()
    items = query.order_by(SyncJobConfig.name).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return SyncJobListResponse(
        items=[SyncJobConfigResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("/configs", response_model=SyncJobConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_sync_config(
    config_in: SyncJobConfigCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Create a new sync job configuration."""
    # Verify user has access to the tenant
    config_tenant = getattr(config_in, 'tenant_id', None)
    if config_tenant and config_tenant != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create config for a different tenant"
        )

    # Create config
    config = SyncJobConfig(
        tenant_id=current_user.tenant_id,
        name=config_in.name,
        data_type=config_in.data_type,
        cron_expression=config_in.cron_expression,
        is_enabled=config_in.is_enabled,
        is_delta_load=config_in.is_delta_load,
        use_claude_ai=config_in.use_claude_ai,
        lookback_days=config_in.lookback_days,
        sap_connection_params=config_in.sap_connection_params,
        table_mapping=config_in.table_mapping,
        field_mapping=config_in.field_mapping,
        filter_criteria=config_in.filter_criteria,
        retry_attempts=config_in.retry_attempts,
        retry_delay_seconds=config_in.retry_delay_seconds,
        timeout_minutes=config_in.timeout_minutes,
        notification_emails=config_in.notification_emails,
        workflow_template_id=config_in.workflow_template_id,
    )

    db.add(config)
    db.commit()
    db.refresh(config)

    # Register with scheduler if enabled
    if config.is_enabled:
        try:
            scheduler = SyncSchedulerService.get_instance()
            if scheduler:
                await scheduler.register_job(db, config)
        except Exception as e:
            logger.error(f"Failed to register job with scheduler: {e}")

    return SyncJobConfigResponse.model_validate(config)


@router.get("/configs/{config_id}", response_model=SyncJobConfigResponse)
def get_sync_config(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get a specific sync job configuration."""
    config = db.query(SyncJobConfig).filter(
        SyncJobConfig.id == config_id,
        SyncJobConfig.tenant_id == current_user.tenant_id
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync configuration not found"
        )

    return SyncJobConfigResponse.model_validate(config)


@router.put("/configs/{config_id}", response_model=SyncJobConfigResponse)
async def update_sync_config(
    config_id: int,
    config_in: SyncJobConfigUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Update a sync job configuration."""
    config = db.query(SyncJobConfig).filter(
        SyncJobConfig.id == config_id,
        SyncJobConfig.tenant_id == current_user.tenant_id
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync configuration not found"
        )

    # Update fields
    update_data = config_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)

    # Update scheduler registration
    try:
        scheduler = SyncSchedulerService.get_instance()
        if scheduler:
            if config.is_enabled:
                await scheduler.register_job(db, config)
            else:
                scheduler.remove_job(f"sync_{config.id}")
    except Exception as e:
        logger.error(f"Failed to update scheduler registration: {e}")

    return SyncJobConfigResponse.model_validate(config)


@router.delete("/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sync_config(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Delete a sync job configuration."""
    config = db.query(SyncJobConfig).filter(
        SyncJobConfig.id == config_id,
        SyncJobConfig.tenant_id == current_user.tenant_id
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync configuration not found"
        )

    # Remove from scheduler
    try:
        scheduler = SyncSchedulerService.get_instance()
        if scheduler:
            scheduler.remove_job(f"sync_{config.id}")
    except Exception as e:
        logger.error(f"Failed to remove job from scheduler: {e}")

    db.delete(config)
    db.commit()


@router.post("/configs/{config_id}/trigger", response_model=SyncJobTriggerResponse)
async def trigger_sync_job(
    config_id: int,
    trigger_request: SyncJobTriggerRequest = None,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Manually trigger a sync job."""
    config = db.query(SyncJobConfig).filter(
        SyncJobConfig.id == config_id,
        SyncJobConfig.tenant_id == current_user.tenant_id
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync configuration not found"
        )

    scheduler = SyncSchedulerService.get_instance()
    if not scheduler:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler service not available"
        )

    # Trigger the job
    force_full = trigger_request.force_full_load if trigger_request else False
    custom_lookback = trigger_request.custom_lookback_days if trigger_request else None

    execution_id = await scheduler.trigger_job_now(
        db, config_id,
        force_full_load=force_full,
        custom_lookback_days=custom_lookback
    )

    return SyncJobTriggerResponse(
        execution_id=execution_id,
        config_id=config_id,
        status=SyncStatus.RUNNING,
        message="Sync job started successfully"
    )


@router.post("/configs/{config_id}/enable", response_model=SyncJobConfigResponse)
async def enable_sync_config(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Enable a sync job configuration."""
    config = db.query(SyncJobConfig).filter(
        SyncJobConfig.id == config_id,
        SyncJobConfig.tenant_id == current_user.tenant_id
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync configuration not found"
        )

    config.is_enabled = True
    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)

    # Register with scheduler
    try:
        scheduler = SyncSchedulerService.get_instance()
        if scheduler:
            await scheduler.register_job(db, config)
    except Exception as e:
        logger.error(f"Failed to register job with scheduler: {e}")

    return SyncJobConfigResponse.model_validate(config)


@router.post("/configs/{config_id}/disable", response_model=SyncJobConfigResponse)
def disable_sync_config(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Disable a sync job configuration."""
    config = db.query(SyncJobConfig).filter(
        SyncJobConfig.id == config_id,
        SyncJobConfig.tenant_id == current_user.tenant_id
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync configuration not found"
        )

    config.is_enabled = False
    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)

    # Remove from scheduler
    try:
        scheduler = SyncSchedulerService.get_instance()
        if scheduler:
            scheduler.remove_job(f"sync_{config.id}")
    except Exception as e:
        logger.error(f"Failed to remove job from scheduler: {e}")

    return SyncJobConfigResponse.model_validate(config)


# ============================================================================
# Sync Job Executions
# ============================================================================

@router.get("/executions", response_model=SyncExecutionListResponse)
def list_sync_executions(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    config_id: Optional[int] = None,
    status_filter: Optional[SyncStatus] = Query(None, alias="status"),
):
    """List sync job executions for the user's customer."""
    query = db.query(SyncJobExecution).join(SyncJobConfig).filter(
        SyncJobConfig.tenant_id == current_user.tenant_id
    )

    if config_id:
        query = query.filter(SyncJobExecution.config_id == config_id)
    if status_filter:
        query = query.filter(SyncJobExecution.status == status_filter)

    total = query.count()
    items = query.order_by(SyncJobExecution.started_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    # Add config name to response
    result_items = []
    for item in items:
        response = SyncJobExecutionResponse.model_validate(item)
        response.config_name = item.config.name if item.config else None
        result_items.append(response)

    return SyncExecutionListResponse(
        items=result_items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/executions/{execution_id}", response_model=SyncJobExecutionResponse)
def get_sync_execution(
    execution_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get a specific sync job execution."""
    execution = db.query(SyncJobExecution).join(SyncJobConfig).filter(
        SyncJobExecution.id == execution_id,
        SyncJobConfig.tenant_id == current_user.tenant_id
    ).first()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync execution not found"
        )

    response = SyncJobExecutionResponse.model_validate(execution)
    response.config_name = execution.config.name if execution.config else None
    return response


@router.get("/executions/{execution_id}/tables", response_model=List[SyncTableResultResponse])
def get_sync_execution_tables(
    execution_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get table-level results for a sync execution."""
    execution = db.query(SyncJobExecution).join(SyncJobConfig).filter(
        SyncJobExecution.id == execution_id,
        SyncJobConfig.tenant_id == current_user.tenant_id
    ).first()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync execution not found"
        )

    tables = db.query(SyncTableResult).filter(
        SyncTableResult.execution_id == execution_id
    ).order_by(SyncTableResult.started_at).all()

    return [SyncTableResultResponse.model_validate(t) for t in tables]


# ============================================================================
# Default Cadences
# ============================================================================

@router.get("/defaults", response_model=DefaultCadencesResponse)
def get_default_cadences(
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get default sync cadence configurations."""
    cadences = []
    for data_type, config in DEFAULT_SYNC_CADENCES.items():
        cadences.append(DefaultCadenceResponse(
            data_type=data_type,
            cron_expression=config["cron"],
            lookback_days=config["lookback_days"],
            sap_tables=config["sap_tables"],
            description=f"Default cadence for {data_type.value}"
        ))

    return DefaultCadencesResponse(cadences=cadences)


@router.post("/configs/from-defaults", response_model=List[SyncJobConfigResponse], status_code=status.HTTP_201_CREATED)
async def create_configs_from_defaults(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    data_types: Optional[List[SyncDataType]] = None,
):
    """Create sync configs from default cadences for the user's customer."""
    created_configs = []

    types_to_create = data_types if data_types else list(DEFAULT_SYNC_CADENCES.keys())

    for data_type in types_to_create:
        if data_type not in DEFAULT_SYNC_CADENCES:
            continue

        defaults = DEFAULT_SYNC_CADENCES[data_type]

        # Check if config already exists
        existing = db.query(SyncJobConfig).filter(
            SyncJobConfig.tenant_id == current_user.tenant_id,
            SyncJobConfig.data_type == data_type
        ).first()

        if existing:
            continue

        config = SyncJobConfig(
            tenant_id=current_user.tenant_id,
            name=f"Default {data_type.value.replace('_', ' ').title()} Sync",
            data_type=data_type,
            cron_expression=defaults["cron"],
            lookback_days=defaults["lookback_days"],
            is_enabled=False,  # Start disabled by default
            is_delta_load=True,
            use_claude_ai=True,
        )

        db.add(config)
        created_configs.append(config)

    db.commit()

    # Refresh and return
    for config in created_configs:
        db.refresh(config)

    return [SyncJobConfigResponse.model_validate(c) for c in created_configs]
