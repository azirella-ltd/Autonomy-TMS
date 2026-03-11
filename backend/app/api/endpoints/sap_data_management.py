"""
SAP Data Management API Endpoints

Provides REST API for:
1. SAP deployment configuration
2. Z-table/Z-field mapping
3. Data ingestion monitoring
4. Insights and actions

Accessible to Tenant Admins and authorized users.
"""

import logging
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

# Base directory for SAP import files (mounted volume)
SAP_IMPORTS_BASE = Path(os.getenv("SAP_IMPORTS_DIR", "/app/imports"))

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_tenant_admin
from app.db.session import get_db
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
from app.services.sap_user_provisioning_service import (
    SAPUserProvisioningService,
    SC_AUTH_OBJECTS,
    SC_TRANSACTION_CODES,
)
from app.models.sap_user_import import SAPRoleMapping, SAPUserImportLog

router = APIRouter()


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------

# Connection Models
class ConnectionCreateRequest(BaseModel):
    name: str = Field(..., description="Connection name")
    description: Optional[str] = Field(None, description="Connection description")
    system_type: str = Field(..., description="SAP system type: s4hana, apo, ecc, bw")
    connection_method: str = Field(..., description="Connection method: rfc, csv, odata, idoc, hana_db")
    # Network
    hostname: Optional[str] = Field(None, description="Hostname or IP address")
    port: Optional[int] = Field(None, description="Port number")
    use_ssl: bool = Field(True, description="Use SSL/HTTPS")
    ssl_verify: bool = Field(False, description="Verify SSL certificate")
    # SAP system
    sid: Optional[str] = Field(None, description="SAP System ID (SID)")
    ashost: Optional[str] = Field(None, description="RFC application server host")
    sysnr: Optional[str] = Field(None, description="SAP system number")
    client: Optional[str] = Field(None, description="SAP ABAP client")
    user: Optional[str] = Field(None, description="SAP username")
    password: Optional[str] = Field(None, description="SAP password (stored encrypted)")
    language: Optional[str] = Field("EN", description="SAP logon language")
    # OData
    odata_base_path: Optional[str] = Field(None, description="OData service base path")
    # CSV
    csv_directory: Optional[str] = Field(None, description="CSV export directory")
    csv_pattern: Optional[str] = Field(None, description="CSV file glob pattern")
    # HANA DB
    hana_schema: Optional[str] = Field("SAPHANADB", description="HANA database schema")
    hana_port: Optional[int] = Field(None, description="HANA SQL port (typically 30215)")
    # Advanced
    sap_router_string: Optional[str] = Field(None, description="SAP Router string")
    cloud_connector_location_id: Optional[str] = Field(None, description="Cloud Connector location ID")


class ConnectionResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    system_type: str
    connection_method: str
    hostname: Optional[str] = None
    port: Optional[int] = None
    use_ssl: bool = True
    ssl_verify: bool = False
    sid: Optional[str] = None
    client: Optional[str] = None
    user: Optional[str] = None
    language: Optional[str] = None
    odata_base_path: Optional[str] = None
    csv_directory: Optional[str] = None
    hana_schema: Optional[str] = None
    hana_port: Optional[int] = None
    is_active: bool
    is_validated: bool
    last_validated_at: Optional[datetime] = None
    validation_message: Optional[str] = None


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
    tenant_id: int
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
# Helpers
# -------------------------------------------------------------------------

def _config_to_response(c) -> ConnectionResponse:
    """Map SAPConnectionConfig dataclass to ConnectionResponse."""
    return ConnectionResponse(
        id=c.id,
        name=c.name,
        description=c.description,
        system_type=c.system_type.value if hasattr(c.system_type, "value") else c.system_type,
        connection_method=c.connection_method.value if hasattr(c.connection_method, "value") else c.connection_method,
        hostname=c.hostname,
        port=c.port,
        use_ssl=c.use_ssl,
        ssl_verify=c.ssl_verify,
        sid=c.sid,
        client=c.client,
        user=c.user,
        language=c.language,
        odata_base_path=c.odata_base_path,
        csv_directory=c.csv_directory,
        is_active=c.is_active,
        is_validated=c.is_validated,
        last_validated_at=c.last_validated_at,
        validation_message=c.validation_message,
    )


# -------------------------------------------------------------------------
# Connection Endpoints
# -------------------------------------------------------------------------

@router.post("/connections", response_model=ConnectionResponse, tags=["sap-connections"])
async def create_connection(
    request: ConnectionCreateRequest,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new SAP connection configuration."""
    service = create_deployment_service(db, current_user.tenant_id)

    try:
        system_type = SAPSystemType(request.system_type)
        connection_method = ConnectionMethod(request.connection_method)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid enum value: {e}")

    config = await service.create_connection(
        name=request.name,
        system_type=system_type,
        connection_method=connection_method,
        password=request.password,
        description=request.description,
        hostname=request.hostname,
        port=request.port,
        use_ssl=request.use_ssl,
        ssl_verify=request.ssl_verify,
        sid=request.sid,
        ashost=request.ashost,
        sysnr=request.sysnr,
        client=request.client,
        user=request.user,
        language=request.language,
        odata_base_path=request.odata_base_path,
        csv_directory=request.csv_directory,
        csv_pattern=request.csv_pattern,
        sap_router_string=request.sap_router_string,
        cloud_connector_location_id=request.cloud_connector_location_id,
    )

    return _config_to_response(config)


@router.get("/connections", response_model=List[ConnectionResponse], tags=["sap-connections"])
async def list_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all SAP connections for the tenant."""
    service = create_deployment_service(db, current_user.tenant_id)
    connections = await service.get_connections()

    return [_config_to_response(c) for c in connections]


@router.post("/connections/{connection_id}/test", response_model=ConnectionTestResponse, tags=["sap-connections"])
async def test_connection(
    connection_id: int,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Test an SAP connection."""
    service = create_deployment_service(db, current_user.tenant_id)
    success, message = await service.test_connection(connection_id)
    return ConnectionTestResponse(success=success, message=message)


@router.put("/connections/{connection_id}", response_model=ConnectionResponse, tags=["sap-connections"])
async def update_connection(
    connection_id: int,
    request: ConnectionCreateRequest,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing SAP connection configuration."""
    service = create_deployment_service(db, current_user.tenant_id)
    row = await service._get_connection_row(connection_id)
    if not row:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Update fields
    row.name = request.name
    row.description = request.description
    row.system_type = request.system_type
    row.connection_method = request.connection_method
    row.hostname = request.hostname
    row.port = request.port
    row.use_ssl = request.use_ssl
    row.ssl_verify = request.ssl_verify
    row.sid = request.sid
    row.ashost = request.ashost
    row.sysnr = request.sysnr
    row.client = request.client
    row.sap_user = request.user
    row.language = request.language
    row.odata_base_path = request.odata_base_path
    row.csv_directory = request.csv_directory
    row.csv_pattern = request.csv_pattern
    row.sap_router_string = request.sap_router_string
    row.cloud_connector_location_id = request.cloud_connector_location_id
    if request.password:
        row.sap_password_encrypted = request.password  # Service encrypts on commit

    # Reset validation since config changed
    row.is_validated = False
    row.validation_message = None

    await db.commit()
    await db.refresh(row)

    from app.services.sap_deployment_service import SAPConnectionConfig
    config = SAPConnectionConfig.from_db(row)
    return _config_to_response(config)


@router.delete("/connections/{connection_id}", tags=["sap-connections"])
async def delete_connection(
    connection_id: int,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete an SAP connection."""
    service = create_deployment_service(db, current_user.tenant_id)
    row = await service._get_connection_row(connection_id)
    if not row:
        raise HTTPException(status_code=404, detail="Connection not found")

    await db.delete(row)
    await db.commit()
    return {"status": "deleted", "id": connection_id}


# -------------------------------------------------------------------------
# Import Directory Browser
# -------------------------------------------------------------------------

class ImportDirectoryEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None
    csv_count: Optional[int] = None


@router.get("/import-directories", response_model=List[ImportDirectoryEntry], tags=["sap-connections"])
async def list_import_directories(
    subpath: str = Query("", description="Subdirectory to browse relative to imports base"),
    current_user: User = Depends(require_tenant_admin),
):
    """
    Browse available import directories on the server.

    Returns directories and CSV files under the configured imports volume.
    Used by the connection form to select a CSV directory path.
    """
    base = SAP_IMPORTS_BASE
    target = (base / subpath).resolve()

    # Prevent path traversal outside the imports directory
    if not str(target).startswith(str(base.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists():
        return []

    entries = []
    try:
        for item in sorted(target.iterdir()):
            if item.name.startswith("."):
                continue
            entry = ImportDirectoryEntry(
                name=item.name,
                path=str(item),
                is_dir=item.is_dir(),
            )
            if item.is_dir():
                # Count CSV files in this directory
                entry.csv_count = sum(1 for f in item.iterdir() if f.suffix.lower() == ".csv")
            elif item.suffix.lower() == ".csv":
                entry.size = item.stat().st_size
            else:
                continue  # Skip non-CSV files
            entries.append(entry)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    return entries


@router.get("/import-directories/default", tags=["sap-connections"])
async def get_default_import_directory(
    current_user: User = Depends(require_tenant_admin),
):
    """
    Return the default import directory path if one exists.

    Scans the imports base for the first directory containing CSV files.
    """
    base = SAP_IMPORTS_BASE
    if not base.exists():
        return {"path": None, "csv_count": 0}

    # Walk up to 2 levels deep to find the first directory with CSVs
    for dirpath in sorted(base.rglob("*")):
        if not dirpath.is_dir():
            continue
        # Limit depth to 2 levels
        rel = dirpath.relative_to(base)
        if len(rel.parts) > 2:
            continue
        csv_count = sum(1 for f in dirpath.iterdir() if f.suffix.lower() == ".csv")
        if csv_count > 0:
            return {"path": str(dirpath), "csv_count": csv_count}

    return {"path": None, "csv_count": 0}


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
    service = create_deployment_service(db, current_user.tenant_id)

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
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Configure a table for extraction."""
    service = create_deployment_service(db, current_user.tenant_id)

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
    service = create_deployment_service(db, current_user.tenant_id)
    z_tables = await service.discover_z_tables(connection_id)
    return z_tables


# -------------------------------------------------------------------------
# Field Discovery & Auto-Mapping Endpoints
# -------------------------------------------------------------------------

@router.get(
    "/connections/{connection_id}/tables/{table_name}/fields",
    tags=["sap-field-mapping"],
)
async def get_table_fields_with_mapping(
    connection_id: int,
    table_name: str,
    use_ai: bool = Query(False, description="Use AI for fuzzy matching (slower)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get fields for a table and auto-map them to AWS SC entities.

    For CSV connections: reads column headers from the CSV file.
    For other connections: uses known SAP table field definitions.
    Returns each field with its best-match AWS SC mapping.
    """
    import pandas as pd
    from pathlib import Path

    service = create_deployment_service(db, current_user.tenant_id)
    row = await service._get_connection_row(connection_id)
    if not row:
        raise HTTPException(status_code=404, detail="Connection not found")

    from app.services.sap_deployment_service import SAPConnectionConfig, ConnectionMethod
    connection = SAPConnectionConfig.from_db(row)

    fields_input: List[Dict[str, str]] = []

    # Extract field names from the data source
    if connection.connection_method == ConnectionMethod.CSV and connection.csv_directory:
        csv_dir = Path(connection.csv_directory)
        # Try exact match then case-insensitive
        csv_file = csv_dir / f"{table_name}.csv"
        if not csv_file.exists():
            csv_file = csv_dir / f"{table_name.lower()}.csv"
        if not csv_file.exists():
            csv_file = csv_dir / f"{table_name.upper()}.csv"
        if not csv_file.exists():
            # Search all files — match exact stem or prefix (e.g. MARC_material_plant.csv for MARC)
            tn_upper = table_name.upper()
            for f in csv_dir.glob("*.csv"):
                stem = f.stem.upper()
                if stem == tn_upper or stem.startswith(tn_upper + "_"):
                    csv_file = f
                    break

        if csv_file.exists():
            try:
                df = pd.read_csv(csv_file, nrows=0, dtype=str)
                for col in df.columns:
                    fields_input.append({
                        "field_name": col.strip().upper(),
                        "field_type": "CHAR",
                        "field_description": col.strip(),
                    })
            except Exception as e:
                logger.warning(f"Failed to read CSV headers from {csv_file}: {e}")
    else:
        # Use known SAP table field definitions
        from app.services.sap_deployment_service import STANDARD_SAP_TABLES as _STD
        system_tables = _STD.get(
            connection.system_type.value if hasattr(connection.system_type, "value") else connection.system_type,
            {},
        )
        table_info = system_tables.get(table_name, {})
        key_fields = table_info.get("key_fields", [])
        if key_fields:
            for kf in key_fields:
                fields_input.append({
                    "field_name": kf,
                    "field_type": "CHAR",
                    "field_description": kf,
                })

    if not fields_input:
        return []

    # Run batch field mapping
    mapping_service = create_field_mapping_service(db, current_user.tenant_id)
    # Determine target entity from known table mapping
    target_entity = None
    from app.services.sap_deployment_service import STANDARD_SAP_TABLES as _ALL_STD
    for sys_tables in _ALL_STD.values():
        if table_name in sys_tables:
            target_entity = sys_tables[table_name].get("aws_sc_entity")
            break

    # Extract base table name from CSV filename (e.g. "MARC_material_plant" → "MARC")
    source_table = table_name.split("_")[0] if "_" in table_name else table_name

    results = await mapping_service.match_fields_batch(
        fields=[
            {
                "name": f["field_name"],
                "type": f.get("field_type", ""),
                "description": f.get("field_description", ""),
            }
            for f in fields_input
        ],
        target_entity=target_entity,
        source_table=source_table,
        use_ai=use_ai,
    )

    return [r.to_dict() for r in results]


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
    service = create_field_mapping_service(db, current_user.tenant_id)

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
    service = create_field_mapping_service(db, current_user.tenant_id)

    results = await service.match_fields_batch(
        fields=request.fields,
        target_entity=request.target_entity,
        use_ai=request.use_ai,
    )

    return [r.to_dict() for r in results]


@router.post("/field-mapping/confirm", tags=["sap-field-mapping"])
async def confirm_mapping(
    request: ConfirmMappingRequest,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Confirm a field mapping (adds to learned mappings)."""
    service = create_field_mapping_service(db, current_user.tenant_id)
    await service.confirm_mapping(
        sap_field=request.sap_field,
        aws_entity=request.aws_entity,
        aws_field=request.aws_field,
    )
    return {"status": "confirmed", "mapping": request.dict()}


@router.delete("/field-mapping/{sap_field}", tags=["sap-field-mapping"])
async def reject_mapping(
    sap_field: str,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Reject a learned mapping."""
    service = create_field_mapping_service(db, current_user.tenant_id)
    await service.reject_mapping(sap_field)
    return {"status": "rejected", "sap_field": sap_field}


@router.get("/field-mapping/statistics", tags=["sap-field-mapping"])
async def get_mapping_statistics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get statistics about current field mappings."""
    service = create_field_mapping_service(db, current_user.tenant_id)
    return await service.get_mapping_statistics()


@router.get("/field-mapping/export", tags=["sap-field-mapping"])
async def export_mappings(
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Export all learned mappings."""
    service = create_field_mapping_service(db, current_user.tenant_id)
    return await service.export_mappings()


@router.post("/field-mapping/import", tags=["sap-field-mapping"])
async def import_mappings(
    data: Dict[str, Any],
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Import previously exported mappings."""
    service = create_field_mapping_service(db, current_user.tenant_id)
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
    service = create_field_mapping_service(db, current_user.tenant_id)

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
    """Get overall deployment status for the tenant."""
    service = create_deployment_service(db, current_user.tenant_id)
    status = await service.get_deployment_status()

    return DeploymentStatusResponse(
        tenant_id=status.tenant_id,
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
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Validate the entire configuration."""
    service = create_deployment_service(db, current_user.tenant_id)
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
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new ingestion job."""
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)

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
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Start an ingestion job.

    Marks the job as running and launches background CSV processing.
    Progress is updated per-table as rows are read and ingested.
    """
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)
    job = await service.start_job(job_id)

    # Launch actual background ingestion
    import asyncio
    asyncio.create_task(_run_ingestion(job_id, current_user.tenant_id))

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


async def _run_ingestion(job_id: int, tenant_id: int):
    """Background task: process CSV files for an ingestion job."""
    import pandas as pd
    from pathlib import Path
    from app.db.session import async_session_factory
    from app.services.sap_deployment_service import SAPConnectionConfig, ConnectionMethod

    async with async_session_factory() as db:
        try:
            service = create_ingestion_monitoring_service(db, tenant_id)
            job = await service.get_job(job_id)
            if not job:
                return

            # Get the connection to find the CSV directory
            deploy_service = create_deployment_service(db, tenant_id)
            conn_row = await deploy_service._get_connection_row(job.connection_id)
            if not conn_row:
                await service.complete_job(job_id, JobStatus.FAILED)
                return

            connection = SAPConnectionConfig.from_db(conn_row)

            if connection.connection_method != ConnectionMethod.CSV or not connection.csv_directory:
                # For non-CSV, just mark as completed (real RFC/OData processing TBD)
                await service.complete_job(job_id, JobStatus.COMPLETED)
                return

            csv_dir = Path(connection.csv_directory)
            if not csv_dir.exists():
                await service.complete_job(job_id, JobStatus.FAILED)
                return

            total_rows = 0
            total_failed = 0

            for idx, table_name in enumerate(job.tables):
                # Check if job was cancelled
                current_job = await service.get_job(job_id)
                if current_job and current_job.status == JobStatus.CANCELLED:
                    logger.info(f"Job {job_id} was cancelled, stopping")
                    return

                # Find the CSV file (case-insensitive search)
                csv_file = None
                for f in csv_dir.glob("*.csv"):
                    if f.stem.upper() == table_name.upper() or f.stem.lower() == table_name.lower():
                        csv_file = f
                        break
                if not csv_file:
                    # Try with underscores for names like ADRC_addresses
                    for f in csv_dir.glob("*.csv"):
                        if table_name.upper() in f.stem.upper():
                            csv_file = f
                            break

                rows_processed = 0
                rows_failed = 0

                if csv_file and csv_file.exists():
                    try:
                        df = pd.read_csv(csv_file, dtype=str, na_values=["", "NULL"])
                        rows_processed = len(df)
                        logger.info(f"Job {job_id}: Read {rows_processed} rows from {csv_file.name}")
                    except Exception as e:
                        rows_failed = 1
                        logger.warning(f"Job {job_id}: Failed to read {csv_file}: {e}")
                else:
                    logger.info(f"Job {job_id}: No CSV file found for table {table_name}")

                total_rows += rows_processed
                total_failed += rows_failed

                # Update progress
                await service.update_job_progress(
                    job_id=job_id,
                    table=table_name,
                    rows_processed=rows_processed,
                    rows_failed=rows_failed,
                )

            # Mark completed
            final_status = JobStatus.COMPLETED if total_failed == 0 else JobStatus.PARTIAL
            await service.complete_job(job_id, final_status)
            logger.info(f"Job {job_id} completed: {total_rows} rows, {total_failed} failed")

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            try:
                service = create_ingestion_monitoring_service(db, tenant_id)
                await service.complete_job(job_id, JobStatus.FAILED)
            except Exception:
                pass


@router.post("/jobs/{job_id}/cancel", tags=["sap-ingestion"])
async def cancel_job(
    job_id: int,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a running or pending job."""
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)
    cancelled = await service.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(status_code=400, detail="Job not found or already completed")
    return {"ok": True, "status": "cancelled"}


class UpdateJobRequest(BaseModel):
    tables: Optional[List[str]] = None
    job_type: Optional[str] = None


@router.put("/jobs/{job_id}", response_model=JobResponse, tags=["sap-ingestion"])
async def update_job(
    job_id: int,
    request: UpdateJobRequest,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a pending job (tables, job_type). Only works for pending jobs."""
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)
    job = await service.update_job_tables(
        job_id,
        tables=request.tables or [],
        job_type=request.job_type,
    )
    if not job:
        raise HTTPException(status_code=400, detail="Job not found or not in pending status")
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
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)

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
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Mark a job as completed."""
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)

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


@router.delete("/jobs/{job_id}", tags=["sap-ingestion"])
async def delete_job(
    job_id: int,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a job (only if not currently running)."""
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)
    deleted = await service.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=400, detail="Job not found or is currently running")
    return {"ok": True}


@router.get("/jobs", response_model=List[JobResponse], tags=["sap-ingestion"])
async def list_jobs(
    active_only: bool = False,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List ingestion jobs."""
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)

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
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)
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
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)

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
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)
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
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)

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
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)

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
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)
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


@router.get(
    "/connections/{connection_id}/suggest-config-name",
    tags=["sap-config-builder"],
)
async def suggest_config_name(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Derive a meaningful SC config name from SAP data.

    Uses T001 company name, or T001W plant names as fallback.
    Call this before build-config/preview to pre-fill the config name.
    """
    sap_data = await _load_sap_data(db, current_user.tenant_id, connection_id)
    suggested = SAPConfigBuilder.suggest_config_name(sap_data)
    return {"suggested_name": suggested}


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
    sap_data = await _load_sap_data(db, current_user.tenant_id, request.connection_id)

    # Auto-suggest name if using default
    config_name = request.config_name
    if config_name == "SAP Import":
        config_name = SAPConfigBuilder.suggest_config_name(sap_data)

    builder = SAPConfigBuilder(db, current_user.tenant_id)
    preview = await builder.preview(
        sap_data=sap_data,
        config_name=config_name,
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
    sap_data = await _load_sap_data(db, current_user.tenant_id, request.connection_id)

    # Auto-suggest name if using default
    config_name = request.config_name
    if config_name == "SAP Import":
        config_name = SAPConfigBuilder.suggest_config_name(sap_data)

    builder = SAPConfigBuilder(db, current_user.tenant_id)
    result = await builder.build(
        sap_data=sap_data,
        config_name=config_name,
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
    total_steps: int = 9


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
    sap_data = await _load_sap_data(db, current_user.tenant_id, request.connection_id)

    # Auto-suggest name if using default
    config_name = request.config_name
    if config_name == "SAP Import":
        config_name = SAPConfigBuilder.suggest_config_name(sap_data)

    builder = SAPConfigBuilder(db, current_user.tenant_id)
    result = await builder.start_build(
        sap_data=sap_data,
        config_name=config_name,
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
    if step_number < 2 or step_number > 9:
        raise HTTPException(status_code=400, detail="Step must be between 2 and 8")

    sap_data = await _load_sap_data(db, current_user.tenant_id, request.connection_id)

    builder = SAPConfigBuilder(db, current_user.tenant_id)
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
    sap_data = await _load_sap_data(db, current_user.tenant_id, request.connection_id)

    builder = SAPConfigBuilder(db, current_user.tenant_id)
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
    builder = SAPConfigBuilder(db, current_user.tenant_id)
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
    builder = SAPConfigBuilder(db, current_user.tenant_id)
    deleted = await builder.delete_build(config_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Config {config_id} not found")

    return {"deleted": True, "config_id": config_id}


class ZTableDeepAnalysisRequest(BaseModel):
    """Request for deep Z-table analysis with AI-powered fuzzy matching."""
    connection_id: int = Field(..., description="SAP connection to use")
    table_name: str = Field(..., description="Z-table name to analyze")


@router.post(
    "/build-config/z-table-analyze",
    tags=["sap-config-builder"],
)
async def analyze_z_table_deep(
    request: ZTableDeepAnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deep analysis of a Z-table using AI-powered fuzzy matching.

    Calls SAPFieldMappingService.analyze_z_table() for per-field mapping
    with confidence scores, entity inference, and AI integration guidance.
    """
    sap_data = await _load_sap_data(db, current_user.tenant_id, request.connection_id)

    builder = SAPConfigBuilder(db, current_user.tenant_id)
    result = await builder.analyze_z_table_deep(request.table_name, sap_data)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


# Standard SAP tables extracted for supply chain config building
STANDARD_SAP_TABLES = [
    # Master data
    "T001", "T001W", "T001L", "MARA", "MAKT", "MARC", "MBEW", "MARD", "MARM",
    "STKO", "STPO", "LFA1", "KNA1", "EORD", "EINA", "EINE",
    "CRHD", "PLKO", "PLPO", "ADRC",
    # Transactional data (orders)
    "VBAK", "VBAP", "VBEP", "EKKO", "EKPO", "EKET",
    "LIKP", "LIPS", "AFKO", "AFPO", "RESB",
    # Status & quality
    "JEST", "TJ02T", "QMEL", "QALS",
    # Forecasts (PIR)
    "PBIM", "PBED",
    # Equipment / maintenance
    "EQUI", "AUFK",
    # APO tables (if available)
    "/SAPAPO/LOC", "/SAPAPO/SNPFC", "/SAPAPO/MATLOC",
    "/SAPAPO/TRLANE", "/SAPAPO/PDS", "/SAPAPO/SNPBV",
]


async def _load_sap_data(
    db: AsyncSession,
    tenant_id: int,
    connection_id: int,
) -> Dict[str, "pd.DataFrame"]:
    """
    Load SAP data from a connection.

    Supports all connection methods: CSV, RFC, HANA_DB, OData.
    Returns a dict of table_name → DataFrame.
    """
    import asyncio
    import pandas as pd
    from app.services.sap_deployment_service import (
        _decrypt_password,
        SAPConnectionConfig,
    )

    service = create_deployment_service(db, tenant_id)
    row = await service._get_connection_row(connection_id)

    if not row:
        raise HTTPException(status_code=404, detail=f"Connection {connection_id} not found")

    connection = SAPConnectionConfig.from_db(row)
    sap_data: Dict[str, pd.DataFrame] = {}

    method = connection.connection_method

    # -----------------------------------------------------------------
    # CSV mode: read all available CSV files from the configured directory
    # -----------------------------------------------------------------
    if method == ConnectionMethod.CSV and connection.csv_directory:
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

    # -----------------------------------------------------------------
    # HANA DB mode: direct SQL queries to HANA database
    # -----------------------------------------------------------------
    elif method == ConnectionMethod.HANA_DB:
        password = _decrypt_password(row.sap_password_encrypted) if row.sap_password_encrypted else ""
        hana_port = connection.hana_port or 30215
        hana_schema = connection.hana_schema or "SAPHANADB"

        def _extract_hana():
            from hdbcli import dbapi
            conn = dbapi.connect(
                address=connection.hostname,
                port=hana_port,
                user=connection.user,
                password=password,
            )
            result = {}
            for table in STANDARD_SAP_TABLES:
                # APO tables use / prefix which needs quoting
                qualified = f'"{hana_schema}"."{table}"'
                try:
                    df = pd.read_sql(f"SELECT * FROM {qualified}", conn)
                    df.columns = [c.upper().strip() for c in df.columns]
                    if not df.empty:
                        result[table] = df
                except Exception:
                    pass  # Table may not exist in this system
            conn.close()
            return result

        try:
            sap_data = await asyncio.to_thread(_extract_hana)
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="hdbcli package not installed. Run: pip install hdbcli",
            )

    # -----------------------------------------------------------------
    # RFC mode: extract via SAP RFC function modules
    # -----------------------------------------------------------------
    elif method == ConnectionMethod.RFC:
        password = _decrypt_password(row.sap_password_encrypted) if row.sap_password_encrypted else ""

        def _extract_rfc():
            from app.integrations.sap.s4hana_connector import S4HANAConnector
            connector = S4HANAConnector({
                "ashost": connection.ashost or connection.hostname,
                "sysnr": connection.sysnr or "00",
                "client": connection.client or "100",
                "user": connection.user,
                "passwd": password,
                "lang": connection.language or "EN",
            })
            result = {}
            for table in STANDARD_SAP_TABLES:
                if table.startswith("/"):
                    continue  # APO tables need APOConnector
                try:
                    df = connector.read_table(table)
                    if df is not None and not df.empty:
                        df.columns = [c.upper().strip() for c in df.columns]
                        result[table] = df
                except Exception:
                    pass
            return result

        try:
            sap_data = await asyncio.to_thread(_extract_rfc)
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="pyrfc package not installed. Required for RFC connections.",
            )

    # -----------------------------------------------------------------
    # OData mode: extract via OData service endpoints
    # -----------------------------------------------------------------
    elif method == ConnectionMethod.ODATA:
        # OData extraction reads entity sets from the configured base path
        import httpx

        base_url = f"{'https' if connection.use_ssl else 'http'}://{connection.hostname}"
        if connection.port:
            base_url += f":{connection.port}"
        base_path = connection.odata_base_path or "/sap/opu/odata/sap"
        password = _decrypt_password(row.sap_password_encrypted) if row.sap_password_encrypted else ""

        # OData entity set names map to SAP table names
        odata_entity_map = {
            "A_Plant": "T001W", "A_Product": "MARA",
            "A_ProductPlant": "MARC", "A_ProductValuation": "MBEW",
            "A_Supplier": "LFA1", "A_Customer": "KNA1",
            "A_PurchaseOrder": "EKKO", "A_PurchaseOrderItem": "EKPO",
            "A_SalesOrder": "VBAK", "A_SalesOrderItem": "VBAP",
            "A_ProductionOrder": "AFKO",
        }

        async with httpx.AsyncClient(verify=connection.ssl_verify) as client:
            for entity_set, table_name in odata_entity_map.items():
                try:
                    url = f"{base_url}{base_path}/{entity_set}?$format=json&$top=50000"
                    resp = await client.get(
                        url,
                        auth=(connection.user, password) if connection.user else None,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        records = data.get("d", {}).get("results", data.get("value", []))
                        if records:
                            df = pd.DataFrame(records)
                            df.columns = [c.upper().strip() for c in df.columns]
                            sap_data[table_name] = df
                except Exception as e:
                    logger.warning(f"OData extract failed for {entity_set}: {e}")

    if not sap_data:
        raise HTTPException(
            status_code=400,
            detail=f"No SAP data could be loaded via {method.value}. Check connection settings and data availability.",
        )

    return sap_data


# =========================================================================
# SAP User Import Endpoints
# =========================================================================

# --- Pydantic models for user import ---

class RoleMappingCreateRequest(BaseModel):
    agr_name_pattern: str = Field(..., description="SAP role pattern (glob or regex)")
    pattern_type: str = Field("glob", description="Pattern type: glob or regex")
    powell_role: str = Field(..., description="Target Autonomy powell_role")
    user_type: str = Field("USER", description="Target user type")
    derive_site_scope_from_werks: bool = Field(True)
    derive_product_scope_from_matkl: bool = Field(False)
    priority: int = Field(100, description="Priority (lower = first)")
    description: Optional[str] = None


class UserImportFilterConfig(BaseModel):
    extra_auth_objects: List[str] = Field(default_factory=list)
    excluded_auth_objects: List[str] = Field(default_factory=list)
    extra_tcodes: List[str] = Field(default_factory=list)
    excluded_tcodes: List[str] = Field(default_factory=list)
    include_ustyp: List[str] = Field(default_factory=lambda: ["A"])
    exclude_expired: bool = True


class UserImportRequest(BaseModel):
    """Raw SAP table data (7 tables) plus optional filter config."""
    usr02: List[Dict[str, Any]] = Field(default_factory=list)
    usr21: List[Dict[str, Any]] = Field(default_factory=list)
    adrp: List[Dict[str, Any]] = Field(default_factory=list)
    agr_users: List[Dict[str, Any]] = Field(default_factory=list)
    agr_define: List[Dict[str, Any]] = Field(default_factory=list)
    agr_1251: List[Dict[str, Any]] = Field(default_factory=list)
    agr_tcodes: List[Dict[str, Any]] = Field(default_factory=list)
    filter_config: Optional[UserImportFilterConfig] = None


# --- Role Mapping CRUD ---

@router.get("/user-import/role-mappings")
async def list_role_mappings(
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all role mapping rules for the current tenant."""
    from sqlalchemy import select as sa_select

    result = await db.execute(
        sa_select(SAPRoleMapping)
        .where(SAPRoleMapping.tenant_id == current_user.tenant_id)
        .order_by(SAPRoleMapping.priority)
    )
    mappings = result.scalars().all()
    return [m.to_dict() for m in mappings]


@router.post("/user-import/role-mappings")
async def create_role_mapping(
    body: RoleMappingCreateRequest,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new role mapping rule."""
    mapping = SAPRoleMapping(
        tenant_id=current_user.tenant_id,
        agr_name_pattern=body.agr_name_pattern,
        pattern_type=body.pattern_type,
        powell_role=body.powell_role,
        user_type=body.user_type,
        derive_site_scope_from_werks=body.derive_site_scope_from_werks,
        derive_product_scope_from_matkl=body.derive_product_scope_from_matkl,
        priority=body.priority,
        description=body.description,
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)
    return mapping.to_dict()


@router.delete("/user-import/role-mappings/{mapping_id}")
async def delete_role_mapping(
    mapping_id: int,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a role mapping rule."""
    from sqlalchemy import select as sa_select

    result = await db.execute(
        sa_select(SAPRoleMapping).where(
            SAPRoleMapping.id == mapping_id,
            SAPRoleMapping.tenant_id == current_user.tenant_id,
        )
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Role mapping not found")

    await db.delete(mapping)
    await db.commit()
    return {"status": "deleted", "id": mapping_id}


# --- Import Preview & Execute ---

@router.post("/user-import/preview")
async def preview_user_import(
    body: UserImportRequest,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Dry-run: show proposed user mappings without creating records."""
    service = SAPUserProvisioningService(db, current_user.tenant_id)
    raw_data = {
        "usr02": body.usr02,
        "usr21": body.usr21,
        "adrp": body.adrp,
        "agr_users": body.agr_users,
        "agr_define": body.agr_define,
        "agr_1251": body.agr_1251,
        "agr_tcodes": body.agr_tcodes,
    }
    filter_cfg = body.filter_config.model_dump() if body.filter_config else None
    return await service.preview_import(raw_data, filter_cfg)


@router.post("/user-import/execute")
async def execute_user_import(
    body: UserImportRequest,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Commit import: create/update Autonomy users from SAP data."""
    service = SAPUserProvisioningService(db, current_user.tenant_id)
    raw_data = {
        "usr02": body.usr02,
        "usr21": body.usr21,
        "adrp": body.adrp,
        "agr_users": body.agr_users,
        "agr_define": body.agr_define,
        "agr_1251": body.agr_1251,
        "agr_tcodes": body.agr_tcodes,
    }
    filter_cfg = body.filter_config.model_dump() if body.filter_config else None
    log = await service.execute_import(
        raw_data, filter_cfg, initiated_by_user_id=current_user.id
    )
    return log.to_dict()


# --- Import History ---

@router.get("/user-import/logs")
async def list_import_logs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return paginated import audit history."""
    from sqlalchemy import select as sa_select, func

    # Count
    count_q = await db.execute(
        sa_select(func.count(SAPUserImportLog.id)).where(
            SAPUserImportLog.tenant_id == current_user.tenant_id
        )
    )
    total = count_q.scalar() or 0

    # Fetch
    result = await db.execute(
        sa_select(SAPUserImportLog)
        .where(SAPUserImportLog.tenant_id == current_user.tenant_id)
        .order_by(SAPUserImportLog.started_at.desc())
        .offset(offset)
        .limit(limit)
    )
    logs = result.scalars().all()
    return {"total": total, "items": [l.to_dict() for l in logs]}


# --- SC Filter Config ---

@router.get("/user-import/sc-filter-config")
async def get_sc_filter_config(
    current_user: User = Depends(get_current_user),
):
    """Return the default SC relevance filter constants."""
    return {
        "auth_objects": sorted(SC_AUTH_OBJECTS),
        "transaction_codes": sorted(SC_TRANSACTION_CODES),
    }
