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
    IngestionPhase,
    MASTER_DATA_TABLES,
    TRANSACTION_TABLES,
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
    file_table_mapping: Optional[List[dict]] = None


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
    phase: str = Field("master_data", description="Ingestion phase: master_data, cdc, transaction")
    tables: List[str]
    save_csv: bool = Field(False, description="Save extracted data as CSV files (useful for audit/backup when extracting via OData/HANA/RFC)")
    update_tenant_data: bool = Field(True, description="Create/update sites, products, lanes, etc. in the DB. When false, runs extraction + validation only (dry run)")


class JobResponse(BaseModel):
    id: int
    job_type: str
    phase: str = "master_data"
    status: str
    tables: List[str]
    current_table: Optional[str] = None
    progress_percent: float
    total_rows_processed: int
    total_rows_failed: int
    config_id: Optional[int] = None
    build_summary: Optional[Dict[str, Any]] = None
    table_status: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    save_csv: bool = False
    update_tenant_data: bool = True


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
        file_table_mapping=getattr(c, "file_table_mapping", None),
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
    """Test an SAP connection.

    For CSV connections, also scans the directory, identifies SAP tables from
    file headers, and stores the mapping on the connection for review.
    """
    service = create_deployment_service(db, current_user.tenant_id)
    success, message = await service.test_connection(connection_id)

    # For CSV connections, also identify files and store the mapping
    if success:
        conn_row = await service._get_connection_row(connection_id)
        if conn_row and conn_row.connection_method == "csv" and conn_row.csv_directory:
            file_mapping = _scan_and_identify_csv_files(conn_row.csv_directory)
            conn_row.file_table_mapping = file_mapping
            await db.commit()
            identified = sum(1 for m in file_mapping if m.get("table"))
            total = len(file_mapping)
            message += f" | Identified {identified}/{total} CSV files as SAP tables."

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
# CSV File Identification (content-based)
# -------------------------------------------------------------------------

class FileIdentification(BaseModel):
    filename: str
    identified_table: Optional[str] = None
    confidence: float = 0.0
    row_count: int = 0
    columns: List[str] = []
    confirmed: bool = False


class FileMappingUpdate(BaseModel):
    filename: str
    table: Optional[str] = None
    confirmed: bool = True


def _identify_sap_table(csv_columns: set, filename: str = "") -> tuple:
    """Match CSV columns to known SAP table using Jaccard-like similarity.

    Also checks HANA_TABLE_FIELDS (from extractors) and falls back to
    filename-based matching if column matching is inconclusive.

    Returns (table_name, confidence) where confidence is the fraction
    of known table columns found in the CSV header.
    """
    from app.services.sap_field_mapping_service import SAP_TABLE_FIELD_MAPPINGS

    best_table = None
    best_score = 0.0
    csv_upper = {c.upper() for c in csv_columns}

    # Source 1: SAP_TABLE_FIELD_MAPPINGS (field mapping service)
    for table_name, field_map in SAP_TABLE_FIELD_MAPPINGS.items():
        known_cols = {c.upper() for c in field_map.keys()}
        if not known_cols:
            continue
        intersection = csv_upper & known_cols
        score = len(intersection) / len(known_cols) if known_cols else 0.0
        if score > best_score:
            best_score = score
            best_table = table_name

    # Source 2: HANA_TABLE_FIELDS (extractor field definitions)
    try:
        from app.integrations.sap.extractors import HANA_TABLE_FIELDS
        for table_name, fields in HANA_TABLE_FIELDS.items():
            known_cols = {c.upper() for c in fields}
            if not known_cols:
                continue
            intersection = csv_upper & known_cols
            score = len(intersection) / len(known_cols) if known_cols else 0.0
            if score > best_score:
                best_score = score
                best_table = table_name
    except ImportError:
        pass

    # Fallback: filename-based matching against known SAP tables
    if best_score < 0.7 and filename:
        stem = filename.rsplit(".", 1)[0].upper() if "." in filename else filename.upper()
        try:
            from app.services.sap_deployment_service import STANDARD_SAP_TABLES
            all_tables = set()
            for tables in STANDARD_SAP_TABLES.values():
                all_tables.update(t.upper() for t in tables)
            if stem in all_tables:
                best_table = stem
                best_score = max(best_score, 0.8)  # filename match = 0.8 confidence
        except ImportError:
            pass

    return best_table, best_score


def _scan_and_identify_csv_files(csv_dir: str) -> List[dict]:
    """Scan a CSV directory, read headers, and identify SAP tables.

    Returns list of dicts with keys: filename, table, confidence, row_count, columns, confirmed.
    Files with confidence >= 0.7 are auto-confirmed.
    """
    import csv as csv_mod
    from app.services.sap_ingestion_monitoring_service import SAPIngestionMonitoringService

    csv_path = Path(csv_dir)
    if not csv_path.exists():
        return []

    results: List[dict] = []

    for csv_file in sorted(csv_path.glob("*.csv")):
        try:
            with open(csv_file, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv_mod.reader(f)
                header = next(reader, None)
                if not header:
                    results.append({
                        "filename": csv_file.name,
                        "table": None,
                        "confidence": 0.0,
                        "row_count": 0,
                        "columns": [],
                        "confirmed": False,
                    })
                    continue

                row_count = sum(1 for _ in reader)

            columns = [c.strip() for c in header]
            table_name, confidence = _identify_sap_table(set(columns), filename=csv_file.name)
            confidence = round(confidence, 4)

            results.append({
                "filename": csv_file.name,
                "table": table_name,
                "confidence": confidence,
                "row_count": row_count,
                "columns": columns,
                "confirmed": confidence >= 0.7,
            })
        except Exception as e:
            logger.warning(f"Failed to read CSV header from {csv_file}: {e}")
            results.append({
                "filename": csv_file.name,
                "table": None,
                "confidence": 0.0,
                "row_count": 0,
                "columns": [],
                "confirmed": False,
            })

    # Sort by table dependency order
    priority_map = SAPIngestionMonitoringService._TABLE_PRIORITY
    results.sort(key=lambda r: priority_map.get(r.get("table") or "", 999))

    return results


@router.post(
    "/connections/{connection_id}/identify-files",
    response_model=List[FileIdentification],
    tags=["sap-connections"],
)
async def identify_csv_files(
    connection_id: int,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Identify SAP tables from CSV file headers using column-name matching.

    Reads only the header row (and counts lines) for each .csv file in the
    connection's configured CSV directory, then matches columns against
    SAP_TABLE_FIELD_MAPPINGS to determine which SAP table each file contains.
    Results are sorted by table dependency order (_TABLE_PRIORITY).

    Note: file identification also runs automatically during connection testing.
    This endpoint can be used to re-scan without re-testing the connection.
    """
    service = create_deployment_service(db, current_user.tenant_id)
    row = await service._get_connection_row(connection_id)
    if not row:
        raise HTTPException(status_code=404, detail="Connection not found")

    csv_directory = row.csv_directory
    if not csv_directory:
        raise HTTPException(status_code=400, detail="Connection has no CSV directory configured")

    csv_dir = Path(csv_directory)
    if not csv_dir.exists():
        raise HTTPException(status_code=400, detail=f"CSV directory not found: {csv_directory}")

    mapping = _scan_and_identify_csv_files(str(csv_dir))

    # Persist the mapping on the connection
    row.file_table_mapping = mapping
    await db.commit()

    return [
        FileIdentification(
            filename=m["filename"],
            identified_table=m["table"],
            confidence=m["confidence"],
            row_count=m["row_count"],
            columns=m["columns"],
            confirmed=m["confirmed"],
        )
        for m in mapping
    ]


@router.post(
    "/connections/{connection_id}/confirm-file-mapping",
    tags=["sap-connections"],
)
async def confirm_file_mapping(
    connection_id: int,
    updates: List[FileMappingUpdate],
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update file-to-table mappings on a connection.

    Allows the user to confirm auto-identified mappings, override them with
    a different table name, or set table to null to skip a file during ingestion.
    """
    service = create_deployment_service(db, current_user.tenant_id)
    row = await service._get_connection_row(connection_id)
    if not row:
        raise HTTPException(status_code=404, detail="Connection not found")

    current_mapping = row.file_table_mapping or []

    # Index current mapping by filename for fast lookup
    mapping_by_file = {m["filename"]: m for m in current_mapping}

    for update in updates:
        if update.filename not in mapping_by_file:
            raise HTTPException(
                status_code=400,
                detail=f"File not found in mapping: {update.filename}. "
                       f"Run connection test or identify-files first.",
            )
        entry = mapping_by_file[update.filename]
        entry["table"] = update.table
        entry["confirmed"] = update.confirmed

    # Write back the full list (preserving order)
    row.file_table_mapping = list(mapping_by_file.values())
    await db.commit()

    return {"status": "updated", "files_updated": len(updates)}


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
    elif connection.connection_method == ConnectionMethod.HANA_DB:
        # Query actual column metadata from HANA information schema
        from app.services.sap_deployment_service import _decrypt_password
        password = _decrypt_password(row.sap_password_encrypted) if row.sap_password_encrypted else ""
        hana_port = connection.hana_port or 30215
        hana_schema = (connection.hana_schema or "SAPHANADB").upper()

        import asyncio
        def _get_hana_columns():
            from hdbcli import dbapi
            conn = dbapi.connect(
                address=connection.hostname,
                port=hana_port,
                user=connection.user,
                password=password,
            )
            cursor = conn.cursor()
            cursor.execute(
                'SELECT COLUMN_NAME, DATA_TYPE_NAME, LENGTH, COMMENTS '
                'FROM TABLE_COLUMNS '
                'WHERE SCHEMA_NAME = ? AND TABLE_NAME = ? '
                'ORDER BY POSITION',
                (hana_schema, table_name.upper()),
            )
            cols = cursor.fetchall()
            cursor.close()
            conn.close()
            return cols

        try:
            hana_cols = await asyncio.to_thread(_get_hana_columns)
            for col_name, data_type, length, comments in hana_cols:
                desc = comments if comments else col_name
                fields_input.append({
                    "field_name": col_name.strip().upper(),
                    "field_type": data_type or "CHAR",
                    "field_description": desc,
                })
        except Exception as e:
            logger.warning(f"Failed to query HANA columns for {table_name}: {e}")
            # Fall back to key_fields
            from app.services.sap_deployment_service import STANDARD_SAP_TABLES as _STD
            system_tables = _STD.get(
                connection.system_type.value if hasattr(connection.system_type, "value") else connection.system_type,
                {},
            )
            table_info = system_tables.get(table_name, {})
            for kf in table_info.get("key_fields", []):
                fields_input.append({"field_name": kf, "field_type": "CHAR", "field_description": kf})
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


def _job_to_response(job) -> JobResponse:
    """Convert an IngestionJob to a JobResponse."""
    return JobResponse(
        id=job.id,
        job_type=job.job_type.value,
        phase=job.phase.value if hasattr(job.phase, 'value') else str(job.phase),
        status=job.status.value,
        tables=job.tables,
        current_table=job.current_table,
        progress_percent=job.progress_percent,
        total_rows_processed=job.total_rows_processed,
        total_rows_failed=job.total_rows_failed,
        config_id=job.config_id,
        build_summary=job.build_summary,
        table_status=job.table_status,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=job.duration_seconds,
        save_csv=job.save_csv,
        update_tenant_data=job.update_tenant_data,
    )


# -------------------------------------------------------------------------
# Ingestion Job Endpoints
# -------------------------------------------------------------------------

@router.post("/jobs", response_model=JobResponse, tags=["sap-ingestion"])
async def create_job(
    request: CreateJobRequest,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new ingestion job.

    If ``tables`` is ``["from_mapping"]``, the job's table list is populated
    from the connection's ``file_table_mapping`` (confirmed entries with a
    non-null table, sorted by ``_TABLE_PRIORITY``).
    """
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)

    try:
        job_type = JobType(request.job_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid job type: {request.job_type}")

    try:
        phase = IngestionPhase(request.phase)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid phase: {request.phase}. Must be: master_data, cdc, transaction")

    tables = request.tables

    # Resolve tables from connection's file_table_mapping
    if tables == ["from_mapping"]:
        deploy_service = create_deployment_service(db, current_user.tenant_id)
        conn_row = await deploy_service._get_connection_row(request.connection_id)
        if not conn_row:
            raise HTTPException(status_code=404, detail="Connection not found")
        mapping = conn_row.file_table_mapping or []
        tables = [
            entry["table"]
            for entry in mapping
            if entry.get("confirmed") and entry.get("table")
        ]
        if not tables:
            raise HTTPException(
                status_code=400,
                detail="No confirmed file mappings found. Test the connection first, "
                       "then confirm the file-to-table mapping.",
            )
        # Sort by dependency priority
        priority_map = SAPIngestionMonitoringService._TABLE_PRIORITY
        tables.sort(key=lambda t: priority_map.get(t, 999))

    job = await service.create_job(
        connection_id=request.connection_id,
        job_type=job_type,
        tables=tables,
        phase=phase,
        save_csv=request.save_csv,
        update_tenant_data=request.update_tenant_data,
    )

    return _job_to_response(job)


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

    return _job_to_response(job)


@router.post("/jobs/{job_id}/rerun", response_model=JobResponse, tags=["sap-ingestion"])
async def rerun_job(
    job_id: int,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """Rerun a completed/failed/cancelled ingestion job.

    Resets all progress stats (rows, progress, timestamps, errors, build results)
    and relaunches the ingestion pipeline from scratch.
    """
    service = create_ingestion_monitoring_service(db, current_user.tenant_id)
    job = await service.rerun_job(job_id)

    # Launch actual background ingestion
    import asyncio
    asyncio.create_task(_run_ingestion(job_id, current_user.tenant_id))

    return _job_to_response(job)


def _find_csv_file(
    csv_dir: "Path",
    table_name: str,
    file_table_mapping: Optional[List[dict]] = None,
) -> "Optional[Path]":
    """Find a CSV file for a table name.

    If file_table_mapping is provided (from connection test), uses it to look up
    the confirmed filename for the given table. Falls back to filename-based
    matching (exact, prefix, substring) if no mapping entry is found.
    """
    from pathlib import Path

    # Check file_table_mapping first (populated during connection test)
    if file_table_mapping:
        for entry in file_table_mapping:
            if (
                entry.get("table")
                and entry["table"].upper() == table_name.upper()
                and entry.get("confirmed")
            ):
                mapped_file = csv_dir / entry["filename"]
                if mapped_file.exists():
                    return mapped_file

    # Fallback: filename-based matching
    tn_upper = table_name.upper()
    # Exact match first
    for f in csv_dir.glob("*.csv"):
        if f.stem.upper() == tn_upper:
            return f
    # Prefix match (e.g. MARC_material_plant.csv matches MARC)
    for f in csv_dir.glob("*.csv"):
        if f.stem.upper().startswith(tn_upper + "_") or f.stem.upper().startswith(tn_upper + "-"):
            return f
    # Substring match
    for f in csv_dir.glob("*.csv"):
        if tn_upper in f.stem.upper():
            return f
    return None


async def _read_csv_tables(
    csv_dir: "Path",
    tables: list,
    job_id: int,
    tenant_id: int,
    service,
    file_table_mapping: Optional[List[dict]] = None,
) -> "Tuple[Dict[str, Any], int, int]":
    """Read CSV files for all tables, updating progress. Returns (sap_data, total_rows, total_failed)."""
    import pandas as pd
    from pathlib import Path

    sap_data = {}
    total_rows = 0
    total_failed = 0

    # Expand "all" to every CSV file in the directory
    if tables == ["all"] or "all" in tables:
        tables = sorted(f.stem for f in Path(csv_dir).glob("*.csv"))
        logger.info(f"Expanded 'all' tables to {len(tables)} CSV files")

    for idx, table_name in enumerate(tables):
        # Check cancellation
        current_job = await service.get_job(job_id)
        if current_job and current_job.status == JobStatus.CANCELLED:
            logger.info(f"Job {job_id} was cancelled, stopping")
            return sap_data, total_rows, total_failed

        csv_file = _find_csv_file(csv_dir, table_name, file_table_mapping)
        rows_processed = 0
        rows_failed = 0

        if csv_file and csv_file.exists():
            try:
                df = pd.read_csv(csv_file, dtype=str, na_values=["", "NULL"])
                rows_processed = len(df)
                # Normalize column names to uppercase for SAPConfigBuilder
                df.columns = [c.upper() for c in df.columns]
                # Store under normalized table name
                from app.services.sap_ingestion_monitoring_service import SAPIngestionMonitoringService
                norm_name = SAPIngestionMonitoringService._extract_table_name(table_name)
                sap_data[norm_name] = df
                logger.info(f"Job {job_id}: Read {rows_processed} rows from {csv_file.name} → {norm_name}")
            except Exception as e:
                rows_failed = 1
                logger.warning(f"Job {job_id}: Failed to read {csv_file}: {e}")
        else:
            logger.info(f"Job {job_id}: No CSV file found for table {table_name}")

        total_rows += rows_processed
        total_failed += rows_failed

        await service.update_job_progress(
            job_id=job_id,
            table=table_name,
            rows_processed=rows_processed,
            rows_failed=rows_failed,
        )

    return sap_data, total_rows, total_failed


async def _extract_via_extractor(
    conn_row, connection, tables: list, job_id: int, tenant_id: int, service
) -> "Tuple[Dict[str, Any], int, int]":
    """Extract tables via OData/HANA_DB/RFC using unified extractor interface."""
    from app.integrations.sap.extractors import create_extractor
    from app.services.sap_deployment_service import _decrypt_password

    password = _decrypt_password(conn_row.sap_password_encrypted) if conn_row.sap_password_encrypted else ""

    try:
        extractor = create_extractor(connection, password)
    except ImportError as e:
        logger.error(f"Job {job_id}: extractor import error: {e}")
        return {}, 0, 1
    except ValueError as e:
        logger.error(f"Job {job_id}: extractor error: {e}")
        return {}, 0, 1

    async def progress_cb(table: str, rows_ok: int, rows_fail: int):
        await service.update_job_progress(
            job_id=job_id,
            table=table,
            rows_processed=rows_ok,
            rows_failed=rows_fail,
        )

    sap_data, total_rows, total_failed = await extractor.extract_tables(
        tables=tables,
        progress_callback=progress_cb,
    )

    # Normalize table names for consistency with CSV path
    from app.services.sap_ingestion_monitoring_service import SAPIngestionMonitoringService
    normalized = {}
    for tbl, df in sap_data.items():
        norm = SAPIngestionMonitoringService._extract_table_name(tbl)
        normalized[norm] = df
    sap_data = normalized

    return sap_data, total_rows, total_failed


async def _save_extracted_csvs(
    sap_data: dict,
    conn_row,
    connection,
    job_id: int,
    tenant_id: int,
    service,
    db=None,
):
    """Save extracted DataFrames as CSV files for audit/backup.

    Files are saved into the connection's csv_directory (or a default
    tenant-scoped directory under SAP_IMPORTS_BASE).  Each table becomes
    ``<TABLE_NAME>.csv``.
    """
    import pandas as pd
    import re

    if connection.csv_directory:
        csv_dir = Path(connection.csv_directory)
    else:
        # Use tenant name (slugified) for the directory
        folder_name = f"tenant_{tenant_id}"
        if db is not None:
            try:
                from sqlalchemy import text as sql_text
                row = (await db.execute(sql_text(
                    "SELECT name FROM tenants WHERE id = :tid"
                ), {"tid": tenant_id})).first()
                if row and row[0]:
                    folder_name = re.sub(r'[^\w\s-]', '', row[0]).strip().replace(' ', '_')
            except Exception:
                pass
        csv_dir = SAP_IMPORTS_BASE / folder_name
    csv_dir.mkdir(parents=True, exist_ok=True)

    saved_count = 0
    for table_name, df in sap_data.items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        out_path = csv_dir / f"{table_name}.csv"
        df.to_csv(out_path, index=False)
        saved_count += 1
        logger.info(f"Job {job_id}: Saved {len(df)} rows → {out_path}")

    logger.info(f"Job {job_id}: CSV save complete — {saved_count} files → {csv_dir}")


async def _run_ingestion(job_id: int, tenant_id: int):
    """
    Background task: 3-phase SAP ingestion pipeline.

    Phase 1 (MASTER_DATA): Read master data CSVs → build SC config via SAPConfigBuilder
    Phase 2 (CDC): Read master data CSVs → compare against existing config → child config if changed
    Phase 3 (TRANSACTION): Read transaction CSVs → import against active SC config
    """
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
                await service.complete_job(job_id, JobStatus.FAILED,
                    error_message=f"Connection {job.connection_id} not found")
                return

            connection = SAPConnectionConfig.from_db(conn_row)

            if connection.connection_method == ConnectionMethod.CSV:
                # CSV extraction path
                if not connection.csv_directory:
                    await service.complete_job(job_id, JobStatus.FAILED,
                        error_message="No CSV directory configured")
                    return
                csv_dir = Path(connection.csv_directory)
                if not csv_dir.exists():
                    await service.complete_job(job_id, JobStatus.FAILED,
                        error_message=f"CSV directory not found: {connection.csv_directory}")
                    return
                sap_data, total_rows, total_failed = await _read_csv_tables(
                    csv_dir, job.tables, job_id, tenant_id, service,
                    file_table_mapping=conn_row.file_table_mapping,
                )

            elif connection.connection_method in (
                ConnectionMethod.ODATA, ConnectionMethod.HANA_DB, ConnectionMethod.RFC,
            ):
                # OData / HANA DB / RFC extraction via unified extractors
                sap_data, total_rows, total_failed = await _extract_via_extractor(
                    conn_row, connection, job.tables, job_id, tenant_id, service
                )

            else:
                await service.complete_job(job_id, JobStatus.FAILED,
                    error_message=f"Connection method not yet supported: {connection.connection_method.value}")
                return

            if not sap_data:
                await service.complete_job(job_id, JobStatus.FAILED,
                    error_message=f"No data extracted for the requested tables (method={connection.connection_method.value})")
                return

            # Save extracted data as CSV files if requested
            if job.save_csv:
                await _save_extracted_csvs(
                    sap_data, conn_row, connection, job_id, tenant_id, service,
                    db=db,
                )

            # Phase-specific processing (skip if dry run)
            if not job.update_tenant_data:
                summary = {
                    "dry_run": True,
                    "tables_extracted": len(sap_data),
                    "tables": {name: len(df) for name, df in sap_data.items()},
                    "csv_saved": job.save_csv,
                }
                await service.set_job_build_result(
                    job_id=job_id, config_id=None, build_summary=summary,
                )
                await service.complete_job(job_id, JobStatus.COMPLETED)
                logger.info(f"Job {job_id} dry run complete: {len(sap_data)} tables extracted, update_tenant_data=false")
            elif job.phase == IngestionPhase.MASTER_DATA:
                await _run_phase1_master_data(db, service, job_id, tenant_id, sap_data)
            elif job.phase == IngestionPhase.CDC:
                await _run_phase2_cdc(db, service, job_id, tenant_id, sap_data)
            elif job.phase == IngestionPhase.TRANSACTION:
                await _run_phase3_transaction(db, service, job_id, tenant_id, sap_data)
            else:
                # Legacy: just mark completed
                final_status = JobStatus.COMPLETED if total_failed == 0 else JobStatus.PARTIAL
                await service.complete_job(job_id, final_status)

            logger.info(f"Job {job_id} phase={job.phase.value} completed: {total_rows} rows")

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            try:
                service = create_ingestion_monitoring_service(db, tenant_id)
                await service.complete_job(job_id, JobStatus.FAILED,
                    error_message=str(e)[:2000])
            except Exception:
                pass


async def _run_phase1_master_data(db, service, job_id: int, tenant_id: int, sap_data: dict):
    """
    Phase 1: Build a new SC config from master data.

    Uses SAPConfigBuilder to create sites, products, lanes, BOMs, inventory policies,
    and forecasts from the extracted SAP tables.
    """
    builder = SAPConfigBuilder(db, tenant_id)
    config_name = builder.suggest_config_name(sap_data)

    from sqlalchemy import text as sql_text

    async def _build_progress(step: int, total: int, description: str):
        """Report build step progress to the job record."""
        import json as _json
        summary_patch = _json.dumps({"build_step": step, "build_total": total, "build_description": description})
        await db.execute(sql_text("""
            UPDATE sap_ingestion_jobs
            SET current_table = :desc,
                build_summary = (COALESCE(build_summary::jsonb, '{}'::jsonb) || (:summary_patch)::jsonb)::json,
                updated_at = NOW()
            WHERE id = :jid AND tenant_id = :tid
        """), {"desc": description, "summary_patch": summary_patch, "jid": job_id, "tid": tenant_id})
        await db.commit()

    _geocoding_done_count = 0

    async def _geocoding_progress(index: int, total: int, label: str, status: str):
        """Report per-address geocoding progress to the job record.

        Uses its own DB session since geocoding runs concurrently with
        other build steps that use the main session.

        status="init": label is JSON list of all address labels (sent once before geocoding starts)
        status="in_progress": address at `index` is being geocoded now
        status="completed"/"failed": address at `index` finished
        """
        nonlocal _geocoding_done_count
        import json as _json
        if status == "init":
            geo_patch = _json.dumps({
                "geocoding_total": total,
                "geocoding_addresses": _json.loads(label),
                "geocoding_done": 0,
                "geocoding_active": -1,
            })
        elif status == "in_progress":
            geo_patch = _json.dumps({
                "geocoding_active": index,
            })
        else:
            _geocoding_done_count += 1
            geo_patch = _json.dumps({
                "geocoding_done": _geocoding_done_count,
                "geocoding_active": index if status == "in_progress" else -1,
            })
        # Use a separate session — geocoding runs concurrently with
        # the main build pipeline which holds the primary session.
        from app.db.session import async_session_factory
        async with async_session_factory() as geo_db:
            await geo_db.execute(sql_text("""
                UPDATE sap_ingestion_jobs
                SET build_summary = (COALESCE(build_summary::jsonb, '{}'::jsonb) || (:geo_patch)::jsonb)::json,
                    updated_at = NOW()
                WHERE id = :jid AND tenant_id = :tid
            """), {"geo_patch": geo_patch, "jid": job_id, "tid": tenant_id})
            await geo_db.commit()

    try:
        result = await builder.build(
            sap_data=sap_data,
            config_name=config_name,
            options={
                "include_forecasts": True,
                "include_inventory": True,
                "default_inv_policy": "doc_dem",
                "default_safety_days": 14,
            },
            progress_callback=_build_progress,
            geocoding_callback=_geocoding_progress,
        )

        # Apply industry defaults and geo-based lead times to the new config
        config_id = result["config_id"]
        try:
            from app.db.session import sync_session_factory
            from app.services.industry_defaults_service import (
                apply_industry_defaults_to_config,
                apply_agent_stochastic_defaults,
            )
            from app.services.geocoding_service import calculate_geo_lead_times_for_config
            from app.models.tenant import Tenant

            sync_db = sync_session_factory()
            try:
                tenant = sync_db.query(Tenant).filter(Tenant.id == tenant_id).first()
                industry_key = (
                    tenant.industry.value
                    if tenant and tenant.industry
                    else "consumer_goods"
                )

                # Entity-level defaults (fills NULL *_dist columns)
                entity_counts = apply_industry_defaults_to_config(
                    sync_db, config_id, industry_key,
                )
                # Agent stochastic params (config-wide)
                agent_count = apply_agent_stochastic_defaults(
                    sync_db, config_id, tenant_id, industry_key,
                )
                # Geo-based transport lead times (site-specific)
                geo_result = calculate_geo_lead_times_for_config(
                    sync_db, config_id,
                )
                sync_db.commit()
                logger.info(
                    f"Post-build defaults for config {config_id}: "
                    f"entities={entity_counts}, agents={agent_count}, "
                    f"geo_lanes={geo_result['updated_lanes']}"
                )
            except Exception as e:
                sync_db.rollback()
                logger.warning(f"Post-build defaults failed for config {config_id}: {e}")
            finally:
                sync_db.close()
        except Exception as e:
            logger.warning(f"Could not apply post-build defaults: {e}")

        # Store the build result on the job
        await service.set_job_build_result(
            job_id=job_id,
            config_id=config_id,
            build_summary=result["summary"],
        )
        await service.complete_job(job_id, JobStatus.COMPLETED)
        logger.info(
            f"Phase 1 complete: config_id={config_id}, "
            f"name='{config_name}', summary={result['summary']}"
        )

    except Exception as e:
        logger.error(f"Phase 1 config build failed: {e}", exc_info=True)
        await service.complete_job(job_id, JobStatus.FAILED,
            error_message=f"Config build failed: {e}")


async def _run_phase2_cdc(db, service, job_id: int, tenant_id: int, sap_data: dict):
    """
    Phase 2: Change Data Capture — compare new master data against active config.

    If topology changes detected (new/removed sites, lanes, products), creates a
    child config branched from the active config and makes it the new active.
    If no changes detected, marks job as completed with no new config.
    """
    from sqlalchemy import text as sql_text

    # Find the active config for this tenant
    result = await db.execute(
        sql_text("""
            SELECT id, name FROM supply_chain_configs
            WHERE tenant_id = :tid AND is_active = true
            ORDER BY id DESC LIMIT 1
        """),
        {"tid": tenant_id}
    )
    active_row = result.mappings().first()
    if not active_row:
        logger.warning(f"CDC: No active config for tenant {tenant_id}. Run Phase 1 first.")
        await service.complete_job(job_id, JobStatus.FAILED,
            error_message="No active supply chain config found. Run Phase 1 (Master Data) first.")
        return

    active_config_id = active_row["id"]
    active_config_name = active_row["name"]

    # Compare key entities: sites (from T001W), products (from MARA/MARC)
    changes_detected = False
    change_summary = {"sites_added": 0, "sites_removed": 0, "products_added": 0, "products_removed": 0}

    # Check site changes
    t001w = sap_data.get("T001W")
    if t001w is not None and "WERKS" in t001w.columns:
        sap_site_keys = set(t001w["WERKS"].dropna().unique())
        existing_result = await db.execute(
            sql_text("SELECT name FROM site WHERE config_id = :cid"),
            {"cid": active_config_id}
        )
        existing_sites = {r["name"] for r in existing_result.mappings().all()}
        new_sites = sap_site_keys - existing_sites
        removed_sites = existing_sites - sap_site_keys - {"Market Supply", "Market Demand"}
        if new_sites or removed_sites:
            changes_detected = True
            change_summary["sites_added"] = len(new_sites)
            change_summary["sites_removed"] = len(removed_sites)

    # Check product changes
    mara = sap_data.get("MARA")
    if mara is not None and "MATNR" in mara.columns:
        sap_product_ids = set(mara["MATNR"].dropna().unique())
        existing_result = await db.execute(
            sql_text("SELECT id FROM product WHERE config_id = :cid"),
            {"cid": active_config_id}
        )
        existing_products = {r["id"] for r in existing_result.mappings().all()}
        new_products = sap_product_ids - existing_products
        removed_products = existing_products - sap_product_ids
        if new_products or removed_products:
            changes_detected = True
            change_summary["products_added"] = len(new_products)
            change_summary["products_removed"] = len(removed_products)

    if not changes_detected:
        logger.info(f"CDC: No topology changes detected against config {active_config_id}")
        await service.set_job_build_result(
            job_id=job_id,
            config_id=active_config_id,
            build_summary={"cdc_result": "no_changes", **change_summary},
        )
        await service.complete_job(job_id, JobStatus.COMPLETED)
        return

    # Changes detected — build new child config
    logger.info(f"CDC: Changes detected: {change_summary}. Building child config.")
    builder = SAPConfigBuilder(db, tenant_id)
    config_name = f"{active_config_name} (CDC {datetime.now().strftime('%Y-%m-%d %H:%M')})"

    try:
        result = await builder.build(sap_data=sap_data, config_name=config_name)

        # Set parent lineage
        new_config_id = result["config_id"]
        await db.execute(
            sql_text("""
                UPDATE supply_chain_configs
                SET parent_config_id = :parent_id, base_config_id = :base_id
                WHERE id = :new_id
            """),
            {"parent_id": active_config_id, "base_id": active_config_id, "new_id": new_config_id}
        )
        # Deactivate old, activate new
        await db.execute(
            sql_text("UPDATE supply_chain_configs SET is_active = false WHERE id = :old_id"),
            {"old_id": active_config_id}
        )
        await db.execute(
            sql_text("UPDATE supply_chain_configs SET is_active = true WHERE id = :new_id"),
            {"new_id": new_config_id}
        )
        await db.commit()

        await service.set_job_build_result(
            job_id=job_id,
            config_id=new_config_id,
            build_summary={
                "cdc_result": "changes_detected",
                "parent_config_id": active_config_id,
                **change_summary,
                **result["summary"],
            },
        )
        await service.complete_job(job_id, JobStatus.COMPLETED)
        logger.info(f"CDC complete: new config {new_config_id} (child of {active_config_id})")

    except Exception as e:
        logger.error(f"CDC config build failed: {e}", exc_info=True)
        await service.complete_job(job_id, JobStatus.FAILED,
            error_message=f"CDC config build failed: {e}")


async def _run_phase3_transaction(db, service, job_id: int, tenant_id: int, sap_data: dict):
    """
    Phase 3: Incremental staging of SAP data against the active SC config.

    Uses SAPDataStagingService for upsert-based staging. All extracted tables
    are mapped and upserted — master data updates existing records, transaction
    data (orders, shipments) is staged for planning consumption.
    """
    from sqlalchemy import text as sql_text
    from app.services.sap_data_staging_service import SAPDataStagingService

    # Find active config
    result = await db.execute(
        sql_text("""
            SELECT id, company_id FROM supply_chain_configs
            WHERE tenant_id = :tid AND is_active = true
            ORDER BY id DESC LIMIT 1
        """),
        {"tid": tenant_id}
    )
    active_row = result.mappings().first()
    if not active_row:
        logger.warning(f"Phase 3: No active config for tenant {tenant_id}. Run Phase 1 first.")
        await service.complete_job(job_id, JobStatus.FAILED,
            error_message="No active supply chain config found. Run Phase 1 (Master Data) first.")
        return

    active_config_id = active_row["id"]
    company_id = active_row.get("company_id")

    try:
        staging_service = SAPDataStagingService(
            db=db,
            tenant_id=tenant_id,
            config_id=active_config_id,
            company_id=company_id,
        )
        pipeline_result = await staging_service.stage_all(sap_data)

        # Run reconciliation
        recon = await staging_service.reconcile(sap_data)

        await service.set_job_build_result(
            job_id=job_id,
            config_id=active_config_id,
            build_summary={
                "staging": True,
                "total_records": pipeline_result.total_records,
                "entities": {
                    k: {"inserted": v.records_inserted, "updated": v.records_updated}
                    for k, v in pipeline_result.entity_results.items()
                },
                "reconciliation": recon,
                "errors": pipeline_result.errors,
            },
        )

        final_status = JobStatus.COMPLETED if pipeline_result.success else JobStatus.PARTIAL
        await service.complete_job(job_id, final_status)
        logger.info(
            f"Phase 3 staging complete: {pipeline_result.total_records} records "
            f"staged against config {active_config_id}"
        )

    except Exception as e:
        logger.error(f"Phase 3 staging failed: {e}", exc_info=True)
        await service.complete_job(job_id, JobStatus.FAILED,
            error_message=f"Staging failed: {e}")


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
    return _job_to_response(job)


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

    return _job_to_response(job)


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

    return [_job_to_response(job) for job in jobs]


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

    return _job_to_response(job)


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
    "MVKE", "STKO", "STPO", "LFA1", "KNA1", "KNVV", "EORD", "EINA", "EINE",
    "CRHD", "CRCO", "PLKO", "PLPO", "ADRC",
    # Transactional data (orders)
    "VBAK", "VBAP", "VBEP", "EKKO", "EKPO", "EKET", "EKBE",
    "LIKP", "LIPS", "AFKO", "AFPO", "AFVC", "AFRU", "RESB",
    # Goods movements (in-transit visibility)
    "MKPF", "MSEG",
    # Pricing conditions
    "KONV",
    # Status & quality
    "JEST", "TJ02T", "QMEL", "QALS", "QASE",
    # Forecasts (PIR) & planned orders
    "PBIM", "PBED", "PLAF",
    # Equipment / maintenance
    "EQUI", "AUFK",
    # Change audit trail
    "CDHDR", "CDPOS",
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
            s = f'"{hana_schema}"'

            # Step 1: Discover company codes and plants for smart filtering
            try:
                t001_df = pd.read_sql(f'SELECT * FROM {s}."T001"', conn)
                t001_df.columns = [c.upper().strip() for c in t001_df.columns]
                if not t001_df.empty:
                    result["T001"] = t001_df
            except Exception:
                pass

            plants = []
            company_codes = []
            try:
                t001w_df = pd.read_sql(f'SELECT * FROM {s}."T001W"', conn)
                t001w_df.columns = [c.upper().strip() for c in t001w_df.columns]
                if not t001w_df.empty:
                    result["T001W"] = t001w_df
                    plants = t001w_df["WERKS"].dropna().unique().tolist()
                    if "BUKRS" in t001w_df.columns:
                        company_codes = t001w_df["BUKRS"].dropna().unique().tolist()
            except Exception:
                pass

            # Build plant filter SQL fragment
            if plants:
                plant_list = ",".join(f"'{p}'" for p in plants)
            else:
                plant_list = "''"
            if company_codes:
                bukrs_list = ",".join(f"'{b}'" for b in company_codes)
            else:
                bukrs_list = "''"

            # Smart filter map: table → WHERE clause using discovered plants/company codes
            _HANA_FILTERS = {
                "MARC": f'"WERKS" IN ({plant_list})',
                "MARD": f'"WERKS" IN ({plant_list})',
                "MBEW": f'"BWKEY" IN ({plant_list})',
                "MARA": f'"MATNR" IN (SELECT DISTINCT "MATNR" FROM {s}."MARC" WHERE "WERKS" IN ({plant_list}))',
                "MAKT": f'"MATNR" IN (SELECT DISTINCT "MATNR" FROM {s}."MARC" WHERE "WERKS" IN ({plant_list})) AND "SPRAS" = \'E\'',
                "MARM": f'"MATNR" IN (SELECT DISTINCT "MATNR" FROM {s}."MARC" WHERE "WERKS" IN ({plant_list}))',
                "MVKE": f'"MATNR" IN (SELECT DISTINCT "MATNR" FROM {s}."MARC" WHERE "WERKS" IN ({plant_list}))',
                "T001L": f'"WERKS" IN ({plant_list})',
                "EORD": f'"WERKS" IN ({plant_list})',
                "EBAN": f'"WERKS" IN ({plant_list})',
                "CRHD": f'"WERKS" IN ({plant_list})',
                "PLKO": f'"WERKS" IN ({plant_list})',
                "PLPO": f'"WERKS" IN ({plant_list})',
                "PBIM": f'"WERKS" IN ({plant_list})',
                "PLAF": f'"PLWRK" IN ({plant_list})',
                "EKKO": f'"BUKRS" IN ({bukrs_list})',
                "EKPO": f'"WERKS" IN ({plant_list})',
                "EKET": f'"EBELN" IN (SELECT DISTINCT "EBELN" FROM {s}."EKPO" WHERE "WERKS" IN ({plant_list}))',
                "VBAP": f'"WERKS" IN ({plant_list})',
                "VBAK": f'"VBELN" IN (SELECT DISTINCT "VBELN" FROM {s}."VBAP" WHERE "WERKS" IN ({plant_list}))',
                "LIKP": f'"VBELN" IN (SELECT DISTINCT "VBELN" FROM {s}."LIPS" WHERE "WERKS" IN ({plant_list}))',
                "LIPS": f'"WERKS" IN ({plant_list})',
                "AFPO": f'"PWERK" IN ({plant_list})',
                "AFKO": f'"AUFNR" IN (SELECT DISTINCT "AUFNR" FROM {s}."AFPO" WHERE "PWERK" IN ({plant_list}))',
                "AFVC": f'"AUFPL" IN (SELECT DISTINCT "AUFPL" FROM {s}."AFKO" WHERE "AUFNR" IN (SELECT DISTINCT "AUFNR" FROM {s}."AFPO" WHERE "PWERK" IN ({plant_list})))',
                "AFRU": f'"AUFNR" IN (SELECT DISTINCT "AUFNR" FROM {s}."AFPO" WHERE "PWERK" IN ({plant_list}))',
                "RESB": f'"WERKS" IN ({plant_list})',
                "MKPF": f'"BUDAT" >= ADD_DAYS(CURRENT_DATE, -365)',
                "MSEG": f'"WERKS" IN ({plant_list}) AND "MBLNR" IN (SELECT "MBLNR" FROM {s}."MKPF" WHERE "BUDAT" >= ADD_DAYS(CURRENT_DATE, -365))',
                "EKBE": f'"EBELN" IN (SELECT DISTINCT "EBELN" FROM {s}."EKPO" WHERE "WERKS" IN ({plant_list}))',
                "VBEP": f'"VBELN" IN (SELECT DISTINCT "VBELN" FROM {s}."VBAP" WHERE "WERKS" IN ({plant_list}))',
                "KONV": f'"KNUMV" IN (SELECT DISTINCT "KNUMV" FROM {s}."EKKO" WHERE "BUKRS" IN ({bukrs_list}))',
                "PLAF": f'"PLWRK" IN ({plant_list})',
                "CDHDR": f'"UDATE" >= ADD_DAYS(CURRENT_DATE, -365)',
                "CDPOS": f'"OBJECTID" IN (SELECT "OBJECTID" FROM {s}."CDHDR" WHERE "UDATE" >= ADD_DAYS(CURRENT_DATE, -365))',
                "MAKT": '"SPRAS" = \'E\'',
                "TJ02T": '"SPRAS" = \'E\'',
                "PBED": f'"BESSION" IN (SELECT DISTINCT "BESSION" FROM {s}."PBIM" WHERE "WERKS" IN ({plant_list}))',
            }

            # Step 2: Extract remaining tables with smart filters
            for table in STANDARD_SAP_TABLES:
                if table in ("T001", "T001W"):
                    continue  # Already extracted
                qualified = f'{s}."{table}"'
                where = _HANA_FILTERS.get(table, "")
                sql = f"SELECT * FROM {qualified}"
                if where:
                    sql += f" WHERE {where}"
                try:
                    df = pd.read_sql(sql, conn)
                    df.columns = [c.upper().strip() for c in df.columns]
                    if not df.empty:
                        result[table] = df
                        logger.info(f"HANA: {table} → {len(df)} rows")
                except Exception as exc:
                    logger.debug(f"HANA: {table} skipped — {exc}")
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


# -------------------------------------------------------------------------
# Geography Geocoding
# -------------------------------------------------------------------------

@router.post("/geography/geocode")
async def geocode_geography(
    config_id: Optional[int] = Query(None, description="Limit to specific config"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_admin),
):
    """
    Geocode geography records that are missing lat/lon coordinates.

    Uses OpenStreetMap Nominatim to convert addresses (city, state, country,
    postal_code) into latitude/longitude. Rate-limited to 1 request/second.
    """
    from sqlalchemy import select as sa_select, and_, or_
    from app.models.sc_entities import Geography
    from app.models.supply_chain_config import Site
    from app.services.geocoding_service import geocode_batch

    # Find geography records missing coordinates
    conditions = [
        or_(Geography.latitude.is_(None), Geography.longitude.is_(None)),
    ]
    if config_id is not None:
        # Filter to geographies linked to sites in this config
        site_geo_ids = sa_select(Site.geo_id).where(
            Site.config_id == config_id
        ).distinct()
        conditions.append(Geography.id.in_(site_geo_ids))

    stmt = sa_select(Geography).where(and_(*conditions))
    result = await db.execute(stmt)
    geos = result.scalars().all()

    if not geos:
        return {"geocoded": 0, "total": 0, "message": "All geography records already have coordinates"}

    # Build address inputs
    address_inputs = [
        {
            "street": g.address_1 or "",
            "city": g.city or "",
            "state": g.state_prov or "",
            "country": g.country or "",
            "postal_code": g.postal_code or "",
        }
        for g in geos
    ]

    coords = await geocode_batch(address_inputs)

    geocoded = 0
    failed = []
    for geo, coord in zip(geos, coords):
        if coord:
            geo.latitude = coord[0]
            geo.longitude = coord[1]
            geocoded += 1
        else:
            failed.append({
                "id": geo.id,
                "city": geo.city,
                "country": geo.country,
            })

    await db.commit()

    return {
        "geocoded": geocoded,
        "total": len(geos),
        "failed": failed[:20],  # Show first 20 failures
        "message": f"Geocoded {geocoded}/{len(geos)} geography records",
    }


@router.get("/geography/status")
async def geography_status(
    config_id: Optional[int] = Query(None, description="Limit to specific config"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check how many geography records have/lack coordinates."""
    from sqlalchemy import select as sa_select, func, and_, or_, case
    from app.models.sc_entities import Geography
    from app.models.supply_chain_config import Site

    conditions = []
    if config_id is not None:
        site_geo_ids = sa_select(Site.geo_id).where(
            Site.config_id == config_id
        ).distinct()
        conditions.append(Geography.id.in_(site_geo_ids))

    base = sa_select(
        func.count().label("total"),
        func.count(
            case(
                (and_(Geography.latitude.isnot(None), Geography.longitude.isnot(None)), 1),
            )
        ).label("with_coords"),
    )
    if conditions:
        base = base.where(and_(*conditions))

    result = await db.execute(base)
    row = result.one()

    return {
        "total": row.total,
        "with_coordinates": row.with_coords,
        "missing_coordinates": row.total - row.with_coords,
    }


# -------------------------------------------------------------------------
# SAP Data Staging — Full Pipeline
# -------------------------------------------------------------------------

class StagingRequest(BaseModel):
    connection_id: int = Field(..., description="SAP connection to extract from")
    config_id: int = Field(..., description="Target SC config to stage into")
    entity_filter: Optional[List[str]] = Field(None, description="Entity types to stage (null=all)")
    tables: Optional[List[str]] = Field(None, description="SAP tables to extract (null=auto from entity_filter)")


class StagingResponse(BaseModel):
    config_id: int
    tenant_id: int
    total_records: int
    success: bool
    errors: List[str]
    entities: Dict[str, Any]
    reconciliation: Optional[Dict[str, Any]] = None


@router.post("/staging/run", response_model=StagingResponse, tags=["sap-staging"])
async def run_staging_pipeline(
    request: StagingRequest,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Run the full SAP data staging pipeline.

    Extracts data from the specified SAP connection, maps to AWS SC entities,
    and upserts into the Postgres staging tables. All downstream planning
    services (Powell, TRM, etc.) consume from these staged tables unchanged.
    """
    from app.services.sap_data_staging_service import (
        SAPDataStagingService, StagingEntityType,
    )

    # Get connection and extract data
    deploy_service = create_deployment_service(db, current_user.tenant_id)
    conn_row = await deploy_service._get_connection_row(request.connection_id)
    if not conn_row:
        raise HTTPException(status_code=404, detail="Connection not found")

    from app.services.sap_deployment_service import SAPConnectionConfig, ConnectionMethod

    connection = SAPConnectionConfig.from_db(conn_row)

    # Determine which tables to extract
    tables = request.tables
    if not tables:
        # Auto-determine from entity filter or use all known tables
        tables = list(MASTER_DATA_TABLES) + list(TRANSACTION_TABLES)

    # Extract data
    if connection.connection_method == ConnectionMethod.CSV:
        from pathlib import Path
        csv_dir = Path(connection.csv_directory) if connection.csv_directory else None
        if not csv_dir or not csv_dir.exists():
            raise HTTPException(status_code=400, detail="CSV directory not found")

        mon_service = create_ingestion_monitoring_service(db, current_user.tenant_id)
        sap_data, total_rows, total_failed = await _read_csv_tables(
            csv_dir, tables, 0, current_user.tenant_id, mon_service,
            file_table_mapping=conn_row.file_table_mapping,
        )
    else:
        sap_data, total_rows, total_failed = await _extract_via_extractor(
            conn_row, connection, tables, 0, current_user.tenant_id,
            create_ingestion_monitoring_service(db, current_user.tenant_id),
        )

    if not sap_data:
        raise HTTPException(status_code=400, detail="No data extracted")

    # Resolve company_id from config or T001
    company_id = None
    from sqlalchemy import select as sa_select
    from app.models.supply_chain_config import SupplyChainConfig
    config_result = await db.execute(
        sa_select(SupplyChainConfig).where(SupplyChainConfig.id == request.config_id)
    )
    config = config_result.scalar_one_or_none()
    if config:
        company_id = config.company_id

    # Parse entity filter
    entity_filter = None
    if request.entity_filter:
        entity_filter = [StagingEntityType(e) for e in request.entity_filter]

    # Run staging
    staging_service = SAPDataStagingService(
        db=db,
        tenant_id=current_user.tenant_id,
        config_id=request.config_id,
        company_id=company_id,
    )
    result = await staging_service.stage_all(sap_data, entity_filter=entity_filter)

    # Run reconciliation
    recon = await staging_service.reconcile(sap_data)

    return StagingResponse(
        config_id=result.config_id,
        tenant_id=result.tenant_id,
        total_records=result.total_records,
        success=result.success,
        errors=result.errors,
        entities={
            k: {
                "mapped": v.records_mapped,
                "inserted": v.records_inserted,
                "updated": v.records_updated,
                "skipped": v.records_skipped,
                "validation_errors": v.validation_errors,
            }
            for k, v in result.entity_results.items()
        },
        reconciliation=recon,
    )


@router.post("/staging/reconcile", tags=["sap-staging"])
async def reconcile_staging(
    request: StagingRequest,
    current_user: User = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Run reconciliation only — compare SAP source counts with staged Postgres counts.

    Does NOT modify any data. Returns per-entity comparison.
    """
    from app.services.sap_data_staging_service import SAPDataStagingService

    deploy_service = create_deployment_service(db, current_user.tenant_id)
    conn_row = await deploy_service._get_connection_row(request.connection_id)
    if not conn_row:
        raise HTTPException(status_code=404, detail="Connection not found")

    from app.services.sap_deployment_service import SAPConnectionConfig, ConnectionMethod

    connection = SAPConnectionConfig.from_db(conn_row)

    tables = request.tables or list(MASTER_DATA_TABLES) + list(TRANSACTION_TABLES)

    if connection.connection_method == ConnectionMethod.CSV:
        from pathlib import Path
        csv_dir = Path(connection.csv_directory) if connection.csv_directory else None
        if not csv_dir or not csv_dir.exists():
            raise HTTPException(status_code=400, detail="CSV directory not found")
        mon_service = create_ingestion_monitoring_service(db, current_user.tenant_id)
        sap_data, _, _ = await _read_csv_tables(
            csv_dir, tables, 0, current_user.tenant_id, mon_service,
            file_table_mapping=conn_row.file_table_mapping,
        )
    else:
        sap_data, _, _ = await _extract_via_extractor(
            conn_row, connection, tables, 0, current_user.tenant_id,
            create_ingestion_monitoring_service(db, current_user.tenant_id),
        )

    if not sap_data:
        raise HTTPException(status_code=400, detail="No data extracted")

    staging_service = SAPDataStagingService(
        db=db,
        tenant_id=current_user.tenant_id,
        config_id=request.config_id,
    )
    recon = await staging_service.reconcile(sap_data)
    return {"config_id": request.config_id, "reconciliation": recon}
