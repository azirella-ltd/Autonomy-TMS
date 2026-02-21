"""
SAP Data Management API Endpoints

Provides REST API for:
1. SAP deployment configuration
2. Z-table/Z-field mapping
3. Data ingestion monitoring
4. Insights and actions

Accessible to Group Admins and authorized users.
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_group_admin
from app.models.user import User
from app.services.sap_deployment_service import (
    SAPDeploymentService,
    SAPSystemType,
    ConnectionMethod,
    DeploymentPhase,
    MappingStatus,
    create_deployment_service,
)
from app.services.sap_field_mapping_service import (
    SAPFieldMappingService,
    MatchConfidence,
    create_field_mapping_service,
)
from app.services.sap_ingestion_monitoring_service import (
    SAPIngestionMonitoringService,
    JobStatus,
    JobType,
    InsightSeverity,
    ActionStatus,
    ActionType,
    create_ingestion_monitoring_service,
)
from app.services.sap_config_builder import SAPConfigBuilder

router = APIRouter()


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------

# Connection Models
class ConnectionCreateRequest(BaseModel):
    name: str = Field(..., description="Connection name")
    system_type: str = Field(..., description="SAP system type: s4hana, apo, ecc, bw")
    connection_method: str = Field(..., description="Connection method: rfc, csv, odata, idoc")
    ashost: Optional[str] = None
    sysnr: Optional[str] = None
    client: Optional[str] = None
    user: Optional[str] = None
    csv_directory: Optional[str] = None
    csv_pattern: Optional[str] = None
    odata_url: Optional[str] = None


class ConnectionResponse(BaseModel):
    id: int
    name: str
    system_type: str
    connection_method: str
    is_active: bool
    is_validated: bool
    last_validated_at: Optional[datetime]


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str


# Table Configuration Models
class TableConfigRequest(BaseModel):
    table_name: str
    description: Optional[str] = ""
    is_enabled: bool = True
    priority: int = 1
    aws_sc_entity: Optional[str] = None
    extraction_mode: str = "full"


class TableConfigResponse(BaseModel):
    id: int
    table_name: str
    description: str
    is_standard: bool
    is_enabled: bool
    priority: int
    aws_sc_entity: Optional[str]


# Field Mapping Models
class FieldMappingRequest(BaseModel):
    sap_field: str
    sap_field_type: Optional[str] = ""
    sap_field_description: Optional[str] = ""
    target_entity: Optional[str] = None
    use_ai: bool = True


class FieldMappingResponse(BaseModel):
    sap_field: str
    aws_sc_entity: Optional[str]
    aws_sc_field: Optional[str]
    confidence: str
    confidence_score: float
    match_source: str
    alternatives: List[Dict[str, Any]]
    ai_rationale: Optional[str]


class BatchFieldMappingRequest(BaseModel):
    fields: List[Dict[str, str]]
    target_entity: Optional[str] = None
    use_ai: bool = True


class ConfirmMappingRequest(BaseModel):
    sap_field: str
    aws_entity: str
    aws_field: str


# Z-Table Analysis Models
class ZTableAnalysisRequest(BaseModel):
    table_name: str
    table_description: str
    fields: List[Dict[str, str]]
    use_ai: bool = True


class ZTableAnalysisResponse(BaseModel):
    table_name: str
    description: str
    suggested_entity: Optional[str]
    entity_confidence: float
    field_mappings: List[Dict[str, Any]]
    mappable_fields: int
    mapped_fields: int
    unmapped_required: int
    ai_purpose_analysis: Optional[str]
    ai_integration_guidance: Optional[str]


# Deployment Status Models
class DeploymentStatusResponse(BaseModel):
    group_id: int
    phase: str
    connection_configured: bool
    connection_tested: bool
    tables_discovered: int
    tables_configured: int
    tables_enabled: int
    total_fields: int
    mapped_fields: int
    unmapped_fields: int
    z_fields_count: int
    z_fields_mapped: int
    validation_errors: List[str]
    validation_warnings: List[str]
    ready_for_production: bool


# Ingestion Job Models
class CreateJobRequest(BaseModel):
    connection_id: int
    job_type: str = Field(..., description="Job type: full_extract, delta_extract, incremental")
    tables: List[str]


class JobResponse(BaseModel):
    id: int
    job_type: str
    status: str
    tables: List[str]
    current_table: Optional[str]
    progress_percent: float
    total_rows_processed: int
    total_rows_failed: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]


class JobProgressUpdate(BaseModel):
    table: str
    rows_processed: int
    rows_failed: int = 0
    errors: Optional[List[Dict[str, Any]]] = None


# Insight Models
class InsightResponse(BaseModel):
    id: int
    timestamp: datetime
    severity: str
    category: str
    title: str
    description: str
    affected_entity: Optional[str]
    affected_table: Optional[str]
    metric_name: Optional[str]
    metric_value: Optional[float]
    suggested_actions: List[Dict[str, Any]]
    is_acknowledged: bool


# Action Models
class ActionResponse(BaseModel):
    id: int
    action_type: str
    status: str
    title: str
    description: str
    affected_entity: Optional[str]
    affected_table: Optional[str]
    created_at: datetime
    assigned_to: Optional[str]


class UpdateActionRequest(BaseModel):
    status: str
    result: Optional[str] = None
    records_fixed: int = 0


# Dashboard Summary
class DashboardSummaryResponse(BaseModel):
    active_jobs: int
    jobs_running: List[Dict[str, Any]]
    recent_jobs: List[Dict[str, Any]]
    total_jobs_completed: int
    average_job_duration_seconds: float
    unacknowledged_insights: int
    insights_by_severity: Dict[str, int]
    pending_actions: int
    latest_quality_scores: Dict[str, float]


# -------------------------------------------------------------------------
# Connection Endpoints
# -------------------------------------------------------------------------

@router.post("/connections", response_model=ConnectionResponse, tags=["sap-connections"])
async def create_connection(
    request: ConnectionCreateRequest,
    current_user: User = Depends(require_group_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new SAP connection configuration."""
    service = create_deployment_service(db, current_user.group_id)

    try:
        system_type = SAPSystemType(request.system_type)
        connection_method = ConnectionMethod(request.connection_method)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid enum value: {e}")

    config = await service.create_connection(
        name=request.name,
        system_type=system_type,
        connection_method=connection_method,
        ashost=request.ashost,
        sysnr=request.sysnr,
        client=request.client,
        user=request.user,
        csv_directory=request.csv_directory,
        csv_pattern=request.csv_pattern,
        odata_url=request.odata_url,
    )

    return ConnectionResponse(
        id=config.id,
        name=config.name,
        system_type=config.system_type.value,
        connection_method=config.connection_method.value,
        is_active=config.is_active,
        is_validated=config.is_validated,
        last_validated_at=config.last_validated_at,
    )


@router.get("/connections", response_model=List[ConnectionResponse], tags=["sap-connections"])
async def list_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all SAP connections for the group."""
    service = create_deployment_service(db, current_user.group_id)
    connections = await service.get_connections()

    return [
        ConnectionResponse(
            id=c.id,
            name=c.name,
            system_type=c.system_type.value,
            connection_method=c.connection_method.value,
            is_active=c.is_active,
            is_validated=c.is_validated,
            last_validated_at=c.last_validated_at,
        )
        for c in connections
    ]


@router.post("/connections/{connection_id}/test", response_model=ConnectionTestResponse, tags=["sap-connections"])
async def test_connection(
    connection_id: int,
    current_user: User = Depends(require_group_admin),
    db: AsyncSession = Depends(get_db),
):
    """Test an SAP connection."""
    service = create_deployment_service(db, current_user.group_id)
    success, message = await service.test_connection(connection_id)
    return ConnectionTestResponse(success=success, message=message)


# -------------------------------------------------------------------------
# Table Configuration Endpoints
# -------------------------------------------------------------------------

@router.get("/connections/{connection_id}/tables", response_model=List[TableConfigResponse], tags=["sap-tables"])
async def discover_tables(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Discover available tables from an SAP connection."""
    service = create_deployment_service(db, current_user.group_id)

    try:
        tables = await service.discover_tables(connection_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return [
        TableConfigResponse(
            id=idx,
            table_name=t.table_name,
            description=t.description,
            is_standard=t.is_standard,
            is_enabled=t.is_enabled,
            priority=t.priority,
            aws_sc_entity=t.aws_sc_entity,
        )
        for idx, t in enumerate(tables, 1)
    ]


@router.post("/connections/{connection_id}/tables", response_model=TableConfigResponse, tags=["sap-tables"])
async def configure_table(
    connection_id: int,
    request: TableConfigRequest,
    current_user: User = Depends(require_group_admin),
    db: AsyncSession = Depends(get_db),
):
    """Configure a table for extraction."""
    service = create_deployment_service(db, current_user.group_id)

    table = await service.configure_table(
        connection_id=connection_id,
        table_name=request.table_name,
        description=request.description,
        is_enabled=request.is_enabled,
        priority=request.priority,
        aws_sc_entity=request.aws_sc_entity,
        extraction_mode=request.extraction_mode,
    )

    return TableConfigResponse(
        id=table.id,
        table_name=table.table_name,
        description=table.description,
        is_standard=table.is_standard,
        is_enabled=table.is_enabled,
        priority=table.priority,
        aws_sc_entity=table.aws_sc_entity,
    )


@router.get("/connections/{connection_id}/z-tables", tags=["sap-tables"])
async def discover_z_tables(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Discover Z-tables (custom SAP tables) from connection."""
    service = create_deployment_service(db, current_user.group_id)
    z_tables = await service.discover_z_tables(connection_id)
    return z_tables


# -------------------------------------------------------------------------
# Field Mapping Endpoints
# -------------------------------------------------------------------------

@router.post("/field-mapping/match", response_model=FieldMappingResponse, tags=["sap-field-mapping"])
async def match_field(
    request: FieldMappingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Match a single SAP field to the best AWS SC field."""
    service = create_field_mapping_service(db, current_user.group_id)

    result = await service.match_field(
        sap_field=request.sap_field,
        sap_field_type=request.sap_field_type,
        sap_field_description=request.sap_field_description,
        target_entity=request.target_entity,
        use_ai=request.use_ai,
    )

    return FieldMappingResponse(
        sap_field=result.sap_field,
        aws_sc_entity=result.aws_sc_entity,
        aws_sc_field=result.aws_sc_field,
        confidence=result.confidence.value,
        confidence_score=result.confidence_score,
        match_source=result.match_source.value,
        alternatives=result.alternatives,
        ai_rationale=result.ai_rationale,
    )


@router.post("/field-mapping/batch", tags=["sap-field-mapping"])
async def match_fields_batch(
    request: BatchFieldMappingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Match multiple SAP fields in batch."""
    service = create_field_mapping_service(db, current_user.group_id)

    results = await service.match_fields_batch(
        fields=request.fields,
        target_entity=request.target_entity,
        use_ai=request.use_ai,
    )

    return [r.to_dict() for r in results]


@router.post("/field-mapping/confirm", tags=["sap-field-mapping"])
async def confirm_mapping(
    request: ConfirmMappingRequest,
    current_user: User = Depends(require_group_admin),
    db: AsyncSession = Depends(get_db),
):
    """Confirm a field mapping (adds to learned mappings)."""
    service = create_field_mapping_service(db, current_user.group_id)
    await service.confirm_mapping(
        sap_field=request.sap_field,
        aws_entity=request.aws_entity,
        aws_field=request.aws_field,
    )
    return {"status": "confirmed", "mapping": request.dict()}


@router.delete("/field-mapping/{sap_field}", tags=["sap-field-mapping"])
async def reject_mapping(
    sap_field: str,
    current_user: User = Depends(require_group_admin),
    db: AsyncSession = Depends(get_db),
):
    """Reject a learned mapping."""
    service = create_field_mapping_service(db, current_user.group_id)
    await service.reject_mapping(sap_field)
    return {"status": "rejected", "sap_field": sap_field}


@router.get("/field-mapping/statistics", tags=["sap-field-mapping"])
async def get_mapping_statistics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get statistics about current field mappings."""
    service = create_field_mapping_service(db, current_user.group_id)
    return await service.get_mapping_statistics()


@router.get("/field-mapping/export", tags=["sap-field-mapping"])
async def export_mappings(
    current_user: User = Depends(require_group_admin),
    db: AsyncSession = Depends(get_db),
):
    """Export all learned mappings."""
    service = create_field_mapping_service(db, current_user.group_id)
    return await service.export_mappings()


@router.post("/field-mapping/import", tags=["sap-field-mapping"])
async def import_mappings(
    data: Dict[str, Any],
    current_user: User = Depends(require_group_admin),
    db: AsyncSession = Depends(get_db),
):
    """Import previously exported mappings."""
    service = create_field_mapping_service(db, current_user.group_id)
    count = await service.import_mappings(data)
    return {"status": "imported", "mappings_count": count}


# -------------------------------------------------------------------------
# Z-Table Analysis Endpoints
# -------------------------------------------------------------------------

@router.post("/z-table-analysis", response_model=ZTableAnalysisResponse, tags=["sap-z-tables"])
async def analyze_z_table(
    request: ZTableAnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyze a Z-table and suggest entity/field mappings."""
    service = create_field_mapping_service(db, current_user.group_id)

    analysis = await service.analyze_z_table(
        table_name=request.table_name,
        table_description=request.table_description,
        fields=request.fields,
        use_ai=request.use_ai,
    )

    return ZTableAnalysisResponse(
        table_name=analysis.table_name,
        description=analysis.description,
        suggested_entity=analysis.suggested_entity,
        entity_confidence=analysis.entity_confidence,
        field_mappings=[f.to_dict() for f in analysis.field_mappings],
        mappable_fields=analysis.mappable_fields,
        mapped_fields=analysis.mapped_fields,
        unmapped_required=analysis.unmapped_required,
        ai_purpose_analysis=analysis.ai_purpose_analysis,
        ai_integration_guidance=analysis.ai_integration_guidance,
    )


# -------------------------------------------------------------------------
# Deployment Status Endpoints
# -------------------------------------------------------------------------

@router.get("/deployment-status", response_model=DeploymentStatusResponse, tags=["sap-deployment"])
async def get_deployment_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get overall deployment status for the group."""
    service = create_deployment_service(db, current_user.group_id)
    status = await service.get_deployment_status()

    return DeploymentStatusResponse(
        group_id=status.group_id,
        phase=status.phase.value,
        connection_configured=status.connection_configured,
        connection_tested=status.connection_tested,
        tables_discovered=status.tables_discovered,
        tables_configured=status.tables_configured,
        tables_enabled=status.tables_enabled,
        total_fields=status.total_fields,
        mapped_fields=status.mapped_fields,
        unmapped_fields=status.unmapped_fields,
        z_fields_count=status.z_fields_count,
        z_fields_mapped=status.z_fields_mapped,
        validation_errors=status.validation_errors,
        validation_warnings=status.validation_warnings,
        ready_for_production=status.ready_for_production,
    )


@router.post("/deployment-status/validate", tags=["sap-deployment"])
async def validate_configuration(
    connection_id: int,
    current_user: User = Depends(require_group_admin),
    db: AsyncSession = Depends(get_db),
):
    """Validate the entire configuration."""
    service = create_deployment_service(db, current_user.group_id)
    is_valid, errors, warnings = await service.validate_configuration(connection_id)

    return {
        "is_valid": is_valid,
        "errors": errors,
        "warnings": warnings,
    }


# -------------------------------------------------------------------------
# Ingestion Job Endpoints
# -------------------------------------------------------------------------

@router.post("/jobs", response_model=JobResponse, tags=["sap-ingestion"])
async def create_job(
    request: CreateJobRequest,
    current_user: User = Depends(require_group_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new ingestion job."""
    service = create_ingestion_monitoring_service(db, current_user.group_id)

    try:
        job_type = JobType(request.job_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid job type: {request.job_type}")

    job = await service.create_job(
        connection_id=request.connection_id,
        job_type=job_type,
        tables=request.tables,
    )

    return JobResponse(
        id=job.id,
        job_type=job.job_type.value,
        status=job.status.value,
        tables=job.tables,
        current_table=job.current_table,
        progress_percent=job.progress_percent,
        total_rows_processed=job.total_rows_processed,
        total_rows_failed=job.total_rows_failed,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=job.duration_seconds,
    )


@router.post("/jobs/{job_id}/start", response_model=JobResponse, tags=["sap-ingestion"])
async def start_job(
    job_id: int,
    current_user: User = Depends(require_group_admin),
    db: AsyncSession = Depends(get_db),
):
    """Start an ingestion job."""
    service = create_ingestion_monitoring_service(db, current_user.group_id)
    job = await service.start_job(job_id)

    return JobResponse(
        id=job.id,
        job_type=job.job_type.value,
        status=job.status.value,
        tables=job.tables,
        current_table=job.current_table,
        progress_percent=job.progress_percent,
        total_rows_processed=job.total_rows_processed,
        total_rows_failed=job.total_rows_failed,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=job.duration_seconds,
    )


@router.post("/jobs/{job_id}/progress", tags=["sap-ingestion"])
async def update_job_progress(
    job_id: int,
    update: JobProgressUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update job progress."""
    service = create_ingestion_monitoring_service(db, current_user.group_id)

    job = await service.update_job_progress(
        job_id=job_id,
        table=update.table,
        rows_processed=update.rows_processed,
        rows_failed=update.rows_failed,
        errors=update.errors,
    )

    return job.to_dict()


@router.post("/jobs/{job_id}/complete", response_model=JobResponse, tags=["sap-ingestion"])
async def complete_job(
    job_id: int,
    status: str = "completed",
    current_user: User = Depends(require_group_admin),
    db: AsyncSession = Depends(get_db),
):
    """Mark a job as completed."""
    service = create_ingestion_monitoring_service(db, current_user.group_id)

    try:
        job_status = JobStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    job = await service.complete_job(job_id, job_status)

    return JobResponse(
        id=job.id,
        job_type=job.job_type.value,
        status=job.status.value,
        tables=job.tables,
        current_table=job.current_table,
        progress_percent=job.progress_percent,
        total_rows_processed=job.total_rows_processed,
        total_rows_failed=job.total_rows_failed,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=job.duration_seconds,
    )


@router.get("/jobs", response_model=List[JobResponse], tags=["sap-ingestion"])
async def list_jobs(
    active_only: bool = False,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List ingestion jobs."""
    service = create_ingestion_monitoring_service(db, current_user.group_id)

    if active_only:
        jobs = await service.get_active_jobs()
    else:
        jobs = await service.get_recent_jobs(limit)

    return [
        JobResponse(
            id=job.id,
            job_type=job.job_type.value,
            status=job.status.value,
            tables=job.tables,
            current_table=job.current_table,
            progress_percent=job.progress_percent,
            total_rows_processed=job.total_rows_processed,
            total_rows_failed=job.total_rows_failed,
            started_at=job.started_at,
            completed_at=job.completed_at,
            duration_seconds=job.duration_seconds,
        )
        for job in jobs
    ]


@router.get("/jobs/{job_id}", response_model=JobResponse, tags=["sap-ingestion"])
async def get_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific job."""
    service = create_ingestion_monitoring_service(db, current_user.group_id)
    job = await service.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse(
        id=job.id,
        job_type=job.job_type.value,
        status=job.status.value,
        tables=job.tables,
        current_table=job.current_table,
        progress_percent=job.progress_percent,
        total_rows_processed=job.total_rows_processed,
        total_rows_failed=job.total_rows_failed,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=job.duration_seconds,
    )


# -------------------------------------------------------------------------
# Insights Endpoints
# -------------------------------------------------------------------------

@router.get("/insights", response_model=List[InsightResponse], tags=["sap-insights"])
async def list_insights(
    severity: Optional[str] = None,
    category: Optional[str] = None,
    unacknowledged_only: bool = False,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List data ingestion insights."""
    service = create_ingestion_monitoring_service(db, current_user.group_id)

    severity_enum = None
    if severity:
        try:
            severity_enum = InsightSeverity(severity)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")

    insights = await service.get_insights(
        severity=severity_enum,
        category=category,
        unacknowledged_only=unacknowledged_only,
        limit=limit,
    )

    return [
        InsightResponse(
            id=i.id,
            timestamp=i.timestamp,
            severity=i.severity.value,
            category=i.category,
            title=i.title,
            description=i.description,
            affected_entity=i.affected_entity,
            affected_table=i.affected_table,
            metric_name=i.metric_name,
            metric_value=i.metric_value,
            suggested_actions=i.suggested_actions,
            is_acknowledged=i.is_acknowledged,
        )
        for i in insights
    ]


@router.post("/insights/{insight_id}/acknowledge", tags=["sap-insights"])
async def acknowledge_insight(
    insight_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge an insight."""
    service = create_ingestion_monitoring_service(db, current_user.group_id)
    insight = await service.acknowledge_insight(insight_id, current_user.email)

    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")

    return {"status": "acknowledged", "insight_id": insight_id}


# -------------------------------------------------------------------------
# Actions Endpoints
# -------------------------------------------------------------------------

@router.get("/actions", response_model=List[ActionResponse], tags=["sap-actions"])
async def list_actions(
    status: Optional[str] = None,
    action_type: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List remediation actions."""
    service = create_ingestion_monitoring_service(db, current_user.group_id)

    status_enum = None
    if status:
        try:
            status_enum = ActionStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    type_enum = None
    if action_type:
        try:
            type_enum = ActionType(action_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid action type: {action_type}")

    actions = await service.get_actions(
        status=status_enum,
        action_type=type_enum,
        limit=limit,
    )

    return [
        ActionResponse(
            id=a.id,
            action_type=a.action_type.value,
            status=a.status.value,
            title=a.title,
            description=a.description,
            affected_entity=a.affected_entity,
            affected_table=a.affected_table,
            created_at=a.created_at,
            assigned_to=a.assigned_to,
        )
        for a in actions
    ]


@router.patch("/actions/{action_id}", tags=["sap-actions"])
async def update_action(
    action_id: int,
    request: UpdateActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an action's status."""
    service = create_ingestion_monitoring_service(db, current_user.group_id)

    try:
        status = ActionStatus(request.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {request.status}")

    action = await service.update_action_status(
        action_id=action_id,
        status=status,
        user=current_user.email,
        result=request.result,
        records_fixed=request.records_fixed,
    )

    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    return action.to_dict()


# -------------------------------------------------------------------------
# Dashboard Endpoints
# -------------------------------------------------------------------------

@router.get("/dashboard", response_model=DashboardSummaryResponse, tags=["sap-dashboard"])
async def get_dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard summary for SAP data management."""
    service = create_ingestion_monitoring_service(db, current_user.group_id)
    summary = await service.get_dashboard_summary()

    return DashboardSummaryResponse(**summary)


# -------------------------------------------------------------------------
# Config Builder Endpoints
# -------------------------------------------------------------------------

class ConfigBuildPreviewRequest(BaseModel):
    """Request for previewing a config build from SAP data."""
    connection_id: int = Field(..., description="SAP connection to use for extraction")
    config_name: str = Field("SAP Import", description="Name for the config")
    company_filter: Optional[str] = Field(None, description="Filter by company code")
    plant_filter: Optional[List[str]] = Field(None, description="Filter by plant codes")


class ConfigBuildRequest(BaseModel):
    """Request for building a SupplyChainConfig from SAP data."""
    connection_id: int = Field(..., description="SAP connection to use")
    config_name: str = Field("SAP Import", description="Name for the config")
    company_filter: Optional[str] = Field(None, description="Filter by company code")
    plant_filter: Optional[List[str]] = Field(None, description="Filter by plant codes")
    master_type_overrides: Optional[Dict[str, str]] = Field(
        None, description="User corrections to inferred master types {site_key: master_type}"
    )
    options: Optional[Dict[str, Any]] = Field(None, description="Build options")


class ConfigBuildPreviewResponse(BaseModel):
    """Preview of what the config build will create."""
    sites: List[Dict[str, Any]]
    lanes: List[Dict[str, Any]]
    products: Dict[str, int]
    vendors: int
    customers: int
    sourcing_rules: int
    warnings: List[str]


class ConfigBuildResponse(BaseModel):
    """Result of a config build."""
    config_id: int
    config_name: str
    summary: Dict[str, int]


@router.post(
    "/build-config/preview",
    response_model=ConfigBuildPreviewResponse,
    tags=["sap-config-builder"],
)
async def preview_config_build(
    request: ConfigBuildPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Dry-run analysis of building a SupplyChainConfig from SAP data.

    Extracts data, infers network topology (sites, lanes, master types),
    and returns a preview without creating anything in the database.
    """
    # Load SAP data from connection
    sap_data = await _load_sap_data(db, current_user.group_id, request.connection_id)

    builder = SAPConfigBuilder(db, current_user.group_id)
    preview = await builder.preview(
        sap_data=sap_data,
        config_name=request.config_name,
        plant_filter=request.plant_filter,
        company_filter=request.company_filter,
    )

    return ConfigBuildPreviewResponse(**preview.to_dict())


@router.post(
    "/build-config",
    response_model=ConfigBuildResponse,
    tags=["sap-config-builder"],
)
async def build_config_from_sap(
    request: ConfigBuildRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Build a SupplyChainConfig from SAP data.

    Creates all entities (sites, products, lanes, sourcing rules, BOM,
    inventory, forecasts) in the database from extracted SAP tables.
    """
    sap_data = await _load_sap_data(db, current_user.group_id, request.connection_id)

    builder = SAPConfigBuilder(db, current_user.group_id)
    result = await builder.build(
        sap_data=sap_data,
        config_name=request.config_name,
        plant_filter=request.plant_filter,
        company_filter=request.company_filter,
        master_type_overrides=request.master_type_overrides,
        options=request.options,
    )

    return ConfigBuildResponse(**result)


# -------------------------------------------------------------------------
# Step-by-Step Config Builder Endpoints
# -------------------------------------------------------------------------

class ConfigStartRequest(BaseModel):
    """Request to start a step-by-step config build."""
    connection_id: int = Field(..., description="SAP connection to use")
    config_name: str = Field("SAP Import", description="Name for the config")
    company_filter: Optional[str] = Field(None, description="Filter by company code")
    plant_filter: Optional[List[str]] = Field(None, description="Filter by plant codes")


class StepExecuteRequest(BaseModel):
    """Request to execute a single build step."""
    connection_id: int = Field(..., description="SAP connection for data reload")
    company_filter: Optional[str] = Field(None, description="Company filter")
    plant_filter: Optional[List[str]] = Field(None, description="Plant filter")
    master_type_overrides: Optional[Dict[str, str]] = Field(
        None, description="Master type overrides for step 3 (sites)"
    )
    options: Optional[Dict[str, Any]] = Field(
        None, description="Build options for step 8 (planning)"
    )
    z_table_includes: Optional[List[str]] = Field(
        None, description="Z-tables to include in the build"
    )


class StepResultResponse(BaseModel):
    """Result from executing one build step."""
    config_id: Optional[int]
    step: int
    step_name: str
    entities_created: int
    entity_type: str
    sample_data: List[Dict[str, Any]]
    anomalies: List[Dict[str, Any]]
    z_tables: List[Dict[str, Any]]
    warnings: List[str]
    table_inventory: List[Dict[str, Any]] = []
    completed_steps: List[int]
    total_steps: int = 8


class BuildStatusResponse(BaseModel):
    """Current build status for a config."""
    config_id: int
    config_name: str
    completed_steps: List[int]
    entity_counts: Dict[str, int]
    created_at: Optional[str]


@router.post(
    "/build-config/start",
    response_model=StepResultResponse,
    tags=["sap-config-builder"],
)
async def start_config_build(
    request: ConfigStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Step 1: Start a config build — creates config record, validates tables,
    detects Z-tables, and returns table inventory with anomalies.
    """
    sap_data = await _load_sap_data(db, current_user.group_id, request.connection_id)

    builder = SAPConfigBuilder(db, current_user.group_id)
    result = await builder.start_build(
        sap_data=sap_data,
        config_name=request.config_name,
        plant_filter=request.plant_filter,
        company_filter=request.company_filter,
    )

    return StepResultResponse(**result.to_dict())


@router.post(
    "/build-config/{config_id}/step/{step_number}",
    response_model=StepResultResponse,
    tags=["sap-config-builder"],
)
async def execute_build_step(
    config_id: int,
    step_number: int,
    request: StepExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute a single build step for an existing config.

    Steps 2-8 create entities incrementally. Each step commits
    and returns results with anomaly detection.
    """
    if step_number < 2 or step_number > 8:
        raise HTTPException(status_code=400, detail="Step must be between 2 and 8")

    sap_data = await _load_sap_data(db, current_user.group_id, request.connection_id)

    builder = SAPConfigBuilder(db, current_user.group_id)
    result = await builder.build_step(
        config_id=config_id,
        step=step_number,
        sap_data=sap_data,
        plant_filter=request.plant_filter,
        company_filter=request.company_filter,
        master_type_overrides=request.master_type_overrides,
        options=request.options,
    )

    return StepResultResponse(**result.to_dict())


@router.post(
    "/build-config/{config_id}/complete",
    response_model=ConfigBuildResponse,
    tags=["sap-config-builder"],
)
async def complete_config_build(
    config_id: int,
    request: StepExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Complete all remaining build steps for a config.

    Checks which steps are already done and runs the rest.
    """
    sap_data = await _load_sap_data(db, current_user.group_id, request.connection_id)

    builder = SAPConfigBuilder(db, current_user.group_id)
    result = await builder.build_remaining(
        config_id=config_id,
        sap_data=sap_data,
        plant_filter=request.plant_filter,
        company_filter=request.company_filter,
        master_type_overrides=request.master_type_overrides,
        options=request.options,
    )

    return ConfigBuildResponse(**result)


@router.get(
    "/build-config/{config_id}/status",
    response_model=BuildStatusResponse,
    tags=["sap-config-builder"],
)
async def get_build_status(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current build status for a config (completed steps, entity counts)."""
    builder = SAPConfigBuilder(db, current_user.group_id)
    status = await builder.get_build_status(config_id)

    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])

    return BuildStatusResponse(**status)


@router.delete(
    "/build-config/{config_id}",
    tags=["sap-config-builder"],
)
async def delete_config_build(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a config build and all its child entities.

    Use this to cancel a partial build or remove an unwanted config.
    """
    builder = SAPConfigBuilder(db, current_user.group_id)
    deleted = await builder.delete_build(config_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Config {config_id} not found")

    return {"deleted": True, "config_id": config_id}


async def _load_sap_data(
    db: AsyncSession,
    group_id: int,
    connection_id: int,
) -> Dict[str, "pd.DataFrame"]:
    """
    Load SAP data from a connection.

    Supports CSV mode (reads from configured directory) and RFC mode.
    Returns a dict of table_name → DataFrame.
    """
    import pandas as pd

    service = create_deployment_service(db, group_id)
    connection = service._connections.get(connection_id)

    if not connection:
        raise HTTPException(status_code=404, detail=f"Connection {connection_id} not found")

    sap_data: Dict[str, pd.DataFrame] = {}

    # CSV mode: read all available CSV files from the configured directory
    if connection.connection_method.value == "csv" and connection.csv_directory:
        from pathlib import Path
        csv_dir = Path(connection.csv_directory)
        if csv_dir.exists():
            for csv_file in csv_dir.glob("*.csv"):
                table_name = csv_file.stem.upper()
                # Handle /SAPAPO/ prefix conventions
                if table_name.startswith("_SAPAPO_"):
                    table_name = f"/SAPAPO/{table_name[8:]}"
                elif table_name.startswith("SAPAPO_"):
                    table_name = f"/SAPAPO/{table_name[7:]}"
                try:
                    df = pd.read_csv(csv_file, dtype=str, na_values=["", "NULL"])
                    df.columns = [c.upper().strip() for c in df.columns]
                    sap_data[table_name] = df
                except Exception as e:
                    logger.warning(f"Failed to read {csv_file}: {e}")

    if not sap_data:
        raise HTTPException(
            status_code=400,
            detail="No SAP data could be loaded from the connection. Ensure CSV files are present.",
        )

    return sap_data
