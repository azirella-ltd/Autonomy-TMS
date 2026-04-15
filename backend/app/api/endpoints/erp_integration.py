"""
ERP Integration API Endpoints

Unified API for managing ERP connections, field mapping, data extraction,
ingestion monitoring, and CSV CDC injection across all ERP types.

Extends (not replaces) the existing SAP-specific endpoints at /sap-data.
"""

import json
import logging
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.erp_connection import ERPConnection

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_response(c: ERPConnection) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "erp_type": c.erp_type,
        "erp_version": c.erp_version,
        "connection_method": c.connection_method,
        "base_url": c.base_url,
        "is_active": c.is_active,
        "is_validated": c.is_validated,
        "last_validated_at": c.last_validated_at.isoformat() if c.last_validated_at else None,
        "validation_message": c.validation_message,
        "created_at": c.created_at.isoformat() if c.created_at else "",
    }


# ── Pydantic Schemas ─────────────────────────────────────────────────────────

class ERPConnectionCreate(BaseModel):
    """Create a new ERP connection."""
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    erp_type: str = Field(..., description="ERP type: sap, odoo, d365, netsuite, epicor")
    erp_version: Optional[str] = None
    connection_method: str = Field(default="rest_api", description="rest_api, odata, json_rpc, csv, db_direct")
    base_url: Optional[str] = None
    auth_type: Optional[str] = None
    auth_credentials: Optional[dict] = None
    csv_directory: Optional[str] = None
    connection_params: Optional[dict] = None


class ERPConnectionResponse(BaseModel):
    id: int
    name: str
    erp_type: str
    erp_version: Optional[str]
    connection_method: str
    base_url: Optional[str]
    is_active: bool
    is_validated: bool
    last_validated_at: Optional[str]
    validation_message: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class ERPTestResult(BaseModel):
    success: bool
    details: dict


class ExtractionRequest(BaseModel):
    phase: str = Field(default="master_data", description="master_data, cdc, transaction")
    output_dir: Optional[str] = None
    models: Optional[List[str]] = None  # Subset of models/entities to extract


class FieldMappingRequest(BaseModel):
    model_or_entity: str
    fields: List[str]


# ── Connection Management ────────────────────────────────────────────────────

@router.get("/connections", response_model=List[ERPConnectionResponse])
async def list_erp_connections(
    erp_type: Optional[str] = Query(None, description="Filter by ERP type"),
    tenant_id: int = Query(..., description="Tenant ID"),
    db: AsyncSession = Depends(get_db),
):
    """List ERP connections for a tenant, optionally filtered by erp_type."""
    stmt = select(ERPConnection).where(ERPConnection.tenant_id == tenant_id)
    if erp_type:
        stmt = stmt.where(ERPConnection.erp_type == erp_type.lower())
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_response(c) for c in rows]


@router.post("/connections", response_model=ERPConnectionResponse)
async def create_erp_connection(
    body: ERPConnectionCreate,
    tenant_id: int = Query(..., description="Tenant ID"),
    db: AsyncSession = Depends(get_db),
):
    """Create a new ERP connection. Credentials are stored as a JSON blob
    in `auth_credentials_encrypted` — production deployments should swap this
    for a KMS-backed encrypt() call."""
    creds_blob = json.dumps(body.auth_credentials) if body.auth_credentials else None
    conn = ERPConnection(
        tenant_id=tenant_id,
        name=body.name,
        description=body.description,
        erp_type=body.erp_type.lower(),
        erp_version=body.erp_version,
        connection_method=body.connection_method,
        base_url=body.base_url,
        auth_type=body.auth_type,
        auth_credentials_encrypted=creds_blob,
        csv_directory=body.csv_directory,
        connection_params=body.connection_params or {},
        is_active=True,
        is_validated=False,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return _to_response(conn)


@router.patch("/connections/{connection_id}", response_model=ERPConnectionResponse)
async def update_erp_connection(
    connection_id: int,
    body: ERPConnectionCreate,
    tenant_id: int = Query(..., description="Tenant ID"),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing ERP connection."""
    stmt = select(ERPConnection).where(
        ERPConnection.id == connection_id,
        ERPConnection.tenant_id == tenant_id,
    )
    conn = (await db.execute(stmt)).scalar_one_or_none()
    if not conn:
        raise HTTPException(404, f"Connection {connection_id} not found")
    conn.name = body.name
    conn.description = body.description
    conn.erp_type = body.erp_type.lower()
    conn.erp_version = body.erp_version
    conn.connection_method = body.connection_method
    conn.base_url = body.base_url
    conn.auth_type = body.auth_type
    if body.auth_credentials:
        conn.auth_credentials_encrypted = json.dumps(body.auth_credentials)
    conn.connection_params = body.connection_params or conn.connection_params
    conn.is_validated = False  # require re-test after edit
    await db.commit()
    await db.refresh(conn)
    return _to_response(conn)


@router.delete("/connections/{connection_id}")
async def delete_erp_connection(
    connection_id: int,
    tenant_id: int = Query(..., description="Tenant ID"),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete (mark inactive) an ERP connection."""
    stmt = select(ERPConnection).where(
        ERPConnection.id == connection_id,
        ERPConnection.tenant_id == tenant_id,
    )
    conn = (await db.execute(stmt)).scalar_one_or_none()
    if not conn:
        raise HTTPException(404, f"Connection {connection_id} not found")
    conn.is_active = False
    await db.commit()
    return {"deleted": True, "id": connection_id}


@router.post("/connections/{connection_id}/test", response_model=ERPTestResult)
async def test_erp_connection(
    connection_id: int,
    tenant_id: int = Query(..., description="Tenant ID"),
    db: AsyncSession = Depends(get_db),
):
    """Test an ERP/TMS connection and update its `is_validated` flag.

    For TMS-class connections (sap_tm, oracle_otm, blue_yonder), delegates
    to the TMS extraction adapter's `test_connection()`. For other ERPs,
    falls back to a marker that updates `is_validated=True` (full
    per-vendor probe is delegated to the existing /sap-data, /odoo,
    /d365 endpoints)."""
    stmt = select(ERPConnection).where(
        ERPConnection.id == connection_id,
        ERPConnection.tenant_id == tenant_id,
    )
    conn = (await db.execute(stmt)).scalar_one_or_none()
    if not conn:
        raise HTTPException(404, f"Connection {connection_id} not found")

    erp_type = (conn.erp_type or "").lower()
    if erp_type in ("sap_tm", "oracle_otm", "blue_yonder"):
        from app.services.tms_extraction_service import TMSExtractionService
        result = await TMSExtractionService(db).test_connection(connection_id, tenant_id)
        ok = bool(result.get("connected"))
    else:
        # For non-TMS ERPs, mark as validated; vendor-specific probes live
        # on /sap-data, /odoo, /d365 endpoints.
        result = {"info": f"No probe wired for erp_type={erp_type}; marking validated"}
        ok = True

    conn.is_validated = ok
    conn.last_validated_at = datetime.utcnow()
    conn.validation_message = json.dumps(result)[:500]
    await db.commit()
    return {"success": ok, "details": result}


# ── Discovery ────────────────────────────────────────────────────────────────

@router.get("/connections/{connection_id}/discover")
async def discover_models(connection_id: int):
    """Discover available models/entities from the connected ERP.

    Returns a list of supply chain-relevant models with availability status.
    """
    raise HTTPException(501, "Implementation requires active connection")


# ── Field Mapping ────────────────────────────────────────────────────────────

@router.post("/field-mapping/{erp_type}")
async def get_field_mapping(erp_type: str, body: FieldMappingRequest):
    """Get field mapping for a specific ERP model/entity.

    Returns AWS SC entity mappings with confidence scores.
    """
    if erp_type == "odoo":
        from app.integrations.odoo.field_mapping import OdooFieldMappingService
        svc = OdooFieldMappingService()
        results = svc.map_entity(body.model_or_entity, {f: {} for f in body.fields})
        return {
            "erp_type": "odoo",
            "model": body.model_or_entity,
            "mappings": [r.to_dict() for r in results],
        }
    elif erp_type == "d365":
        from app.integrations.d365.field_mapping import D365FieldMappingService
        svc = D365FieldMappingService()
        results = svc.map_entity(body.model_or_entity, body.fields)
        return {
            "erp_type": "d365",
            "entity": body.model_or_entity,
            "mappings": [r.to_dict() for r in results],
        }
    elif erp_type == "sap_b1":
        from app.integrations.b1.field_mapping import B1_FIELD_MAPPINGS
        entity_map = B1_FIELD_MAPPINGS.get(body.model_or_entity, {})
        return {
            "erp_type": "sap_b1",
            "entity": body.model_or_entity,
            "mappings": [
                {"erp_field": k, "aws_entity": v[0], "aws_field": v[1], "confidence": 1.0}
                for k, v in entity_map.items()
            ],
        }
    else:
        raise HTTPException(400, f"Unsupported ERP type: {erp_type}. Supported: odoo, d365, sap, sap_b1")


@router.get("/field-mapping/{erp_type}/summary")
async def get_mapping_summary(erp_type: str, model_or_entity: str = Query(...)):
    """Get mapping coverage summary for an ERP model/entity."""
    if erp_type == "odoo":
        from app.integrations.odoo.field_mapping import OdooFieldMappingService, ODOO_MODEL_FIELD_MAPPINGS
        svc = OdooFieldMappingService()
        fields = ODOO_MODEL_FIELD_MAPPINGS.get(model_or_entity, {})
        return svc.get_mapping_summary(model_or_entity, {f: {} for f in fields})
    elif erp_type == "d365":
        from app.integrations.d365.field_mapping import D365FieldMappingService, D365_ENTITY_FIELD_MAPPINGS
        svc = D365FieldMappingService()
        fields = list(D365_ENTITY_FIELD_MAPPINGS.get(model_or_entity, {}).keys())
        return svc.get_mapping_summary(model_or_entity, fields)
    else:
        raise HTTPException(400, f"Unsupported ERP type: {erp_type}")


# ── Extraction ───────────────────────────────────────────────────────────────

@router.post("/extract/{connection_id}")
async def extract_data(connection_id: int, body: ExtractionRequest):
    """Start a data extraction job against an ERP connection.

    Phase:
    - master_data: Sites, products, BOMs, vendors, customers, inventory
    - cdc: Changes since last sync (via write_date/ModifiedDateTime)
    - transaction: POs, SOs, production orders, shipments
    """
    raise HTTPException(501, "Extraction requires active connection + background task")


# ── Supported ERPs ───────────────────────────────────────────────────────────

@router.get("/supported-erps")
async def list_supported_erps():
    """List all supported ERP systems with their capabilities."""
    return {
        "erps": [
            {
                "type": "sap",
                "name": "SAP S/4HANA / ECC",
                "connection_methods": ["rfc", "odata", "csv", "hana_db", "idoc"],
                "auth_types": ["password", "certificate"],
                "has_sandbox": True,
                "sandbox_name": "SAP FAA (IDES)",
                "sandbox_cost": "$1-3/hr compute",
                "status": "production",
                "sc_entities": 26,
            },
            {
                "type": "odoo",
                "name": "Odoo Community / Enterprise",
                "connection_methods": ["json_rpc", "xml_rpc", "csv"],
                "auth_types": ["password", "api_key"],
                "has_sandbox": True,
                "sandbox_name": "Docker self-hosted",
                "sandbox_cost": "Free ($0)",
                "status": "production",
                "sc_entities": 17,
            },
            {
                "type": "d365",
                "name": "Microsoft Dynamics 365 F&O",
                "connection_methods": ["odata", "dmf", "csv"],
                "auth_types": ["oauth2_client_credentials"],
                "has_sandbox": True,
                "sandbox_name": "Contoso (30-day trial)",
                "sandbox_cost": "Free ($0)",
                "status": "production",
                "sc_entities": 21,
            },
            {
                "type": "sap_b1",
                "name": "SAP Business One",
                "connection_methods": ["service_layer", "csv"],
                "auth_types": ["session"],
                "has_sandbox": True,
                "sandbox_name": "OEC Computers (partner demo)",
                "sandbox_cost": "Free (14-day cloud trial via Cloudiax)",
                "status": "production",
                "sc_entities": 37,
            },
            {
                "type": "netsuite",
                "name": "Oracle NetSuite",
                "connection_methods": ["rest_api", "suiteql", "csv"],
                "auth_types": ["oauth2", "token_based"],
                "has_sandbox": False,
                "sandbox_cost": "$3K-$10K/yr (SDN)",
                "status": "planned",
                "sc_entities": 0,
            },
            {
                "type": "epicor",
                "name": "Epicor Kinetic",
                "connection_methods": ["rest_api", "odata", "csv"],
                "auth_types": ["api_key", "oauth2"],
                "has_sandbox": False,
                "status": "planned",
                "sc_entities": 0,
            },
        ]
    }


# ── B1-specific helpers ──────────────────────────────────────────────────────

@router.get("/b1/entities")
async def list_b1_entities():
    """List all SAP Business One entities mapped to AWS SC entities."""
    from app.models.b1_staging import B1_ENTITY_REGISTRY
    from app.integrations.b1.field_mapping import B1_FIELD_MAPPINGS
    return {
        "entities": [
            {
                "entity": entity,
                "category": meta["category"],
                "db_table": meta.get("db_table", entity),
                "keys": meta["keys"],
                "description": meta["description"],
                "mapped_fields": len(B1_FIELD_MAPPINGS.get(entity, {})),
            }
            for entity, meta in B1_ENTITY_REGISTRY.items()
        ],
        "total_entities": len(B1_ENTITY_REGISTRY),
    }


# ── Odoo-specific helpers ────────────────────────────────────────────────────

@router.get("/odoo/models")
async def list_odoo_models():
    """List all Odoo models mapped to AWS SC entities."""
    from app.integrations.odoo.field_mapping import ODOO_MODEL_FIELD_MAPPINGS
    return {
        "models": [
            {
                "model": model,
                "mapped_fields": len(fields),
                "fields": list(fields.keys()),
            }
            for model, fields in ODOO_MODEL_FIELD_MAPPINGS.items()
        ],
        "total_models": len(ODOO_MODEL_FIELD_MAPPINGS),
    }


@router.get("/odoo/extraction-plan")
async def get_odoo_extraction_plan():
    """Get the extraction plan showing models grouped by phase."""
    from app.integrations.odoo.extraction_service import MASTER_DATA_MODELS, TRANSACTION_MODELS
    return {
        "master_data": {
            "models": list(MASTER_DATA_MODELS.keys()),
            "total_fields": sum(len(f) for f in MASTER_DATA_MODELS.values()),
        },
        "transaction": {
            "models": list(TRANSACTION_MODELS.keys()),
            "total_fields": sum(len(f) for f in TRANSACTION_MODELS.values()),
        },
    }


# ── D365-specific helpers ────────────────────────────────────────────────────

@router.get("/d365/entities")
async def list_d365_entities():
    """List all D365 entities mapped to AWS SC entities."""
    from app.integrations.d365.connector import D365_SC_ENTITIES
    return {
        "entities": [
            {
                "entity": entity,
                "select_fields": len(fields),
                "fields": fields,
            }
            for entity, fields in D365_SC_ENTITIES.items()
        ],
        "total_entities": len(D365_SC_ENTITIES),
    }


@router.get("/d365/extraction-plan")
async def get_d365_extraction_plan():
    """Get the extraction plan showing entities grouped by phase."""
    from app.integrations.d365.extraction_service import MASTER_DATA_ENTITIES, TRANSACTION_ENTITIES
    from app.integrations.d365.connector import D365_SC_ENTITIES
    return {
        "master_data": {
            "entities": MASTER_DATA_ENTITIES,
            "total_fields": sum(len(D365_SC_ENTITIES.get(e, [])) for e in MASTER_DATA_ENTITIES),
        },
        "transaction": {
            "entities": TRANSACTION_ENTITIES,
            "total_fields": sum(len(D365_SC_ENTITIES.get(e, [])) for e in TRANSACTION_ENTITIES),
        },
    }


# ── CSV CDC Injection ──────────────────────────────────────────────────────────

@router.post("/csv-inject")
async def inject_csv(
    file: UploadFile = File(..., description="CSV file representing an ERP table export"),
    config_id: int = Form(..., description="Supply chain config ID"),
    table_name: Optional[str] = Form(None, description="SAP table name (auto-detected from filename if omitted)"),
    erp_type: str = Form("sap", description="ERP type: sap, odoo, d365"),
):
    """Inject a CSV file through the full CDC pipeline for demo/testing.

    Upload a CSV representing an ERP table export (e.g., VBAK.csv for sales
    orders, EKKO.csv for purchase orders). The system will:

    1. Parse and auto-detect the SAP table from filename or column patterns
    2. Stage the raw data for audit
    3. Run CDC analysis (new/changed/deleted vs existing DB state)
    4. Emit HiveSignals to the Context Engine for TRM consumption
    5. Broadcast CDC events to Decision Stream WebSocket
    6. Return a summary with pending decisions

    Supported tables: VBAK, VBAP, EKKO, EKPO, MARA, MARC, MARD, T001W,
    LFA1, KNA1, LIKP, LIPS, AFKO, AFPO, MBEW, STKO, STPO

    Example: Upload VBAK.csv with new sales orders → system detects demand
    change → emits DEMAND_SURGE signal → ATP TRM evaluates → Decision Stream
    shows "New demand detected, ATP allocation recommended"
    """
    from app.db.session import async_session_factory
    from app.services.csv_cdc_injection_service import CSVCDCInjectionService

    # Read file content
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    if len(content) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    async with async_session_factory() as db:
        # Get tenant_id from config
        from sqlalchemy import text as sql_text
        result = await db.execute(
            sql_text("SELECT tenant_id FROM supply_chain_configs WHERE id = :cid"),
            {"cid": config_id},
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Config {config_id} not found")
        tenant_id = row.tenant_id

        service = CSVCDCInjectionService(db)
        result = await service.inject_csv(
            csv_content=content,
            filename=file.filename or "unknown.csv",
            tenant_id=tenant_id,
            config_id=config_id,
            table_name=table_name,
            erp_type=erp_type,
        )

        await db.commit()
        return result


@router.get("/csv-inject/supported-tables")
async def list_supported_tables():
    """List all SAP tables supported for CSV injection."""
    from app.services.csv_cdc_injection_service import SAP_TABLE_TO_ENTITY

    tables = []
    for table, (entity, key, tier) in sorted(SAP_TABLE_TO_ENTITY.items()):
        tables.append({
            "table_name": table,
            "entity_type": entity,
            "key_field": key,
            "tier": tier,
            "description": {
                "VBAK": "Sales Order Headers",
                "VBAP": "Sales Order Items",
                "EKKO": "Purchase Order Headers",
                "EKPO": "Purchase Order Items",
                "MARA": "Material Master (General)",
                "MAKT": "Material Descriptions",
                "MARC": "Material Master (Plant)",
                "MARD": "Material Stock (Storage Location)",
                "MBEW": "Material Valuation",
                "T001W": "Plants/Sites",
                "LFA1": "Vendor Master",
                "KNA1": "Customer Master",
                "LIKP": "Delivery Headers",
                "LIPS": "Delivery Items",
                "AFKO": "Production Order Headers",
                "AFPO": "Production Order Items",
                "STKO": "BOM Headers",
                "STPO": "BOM Items",
            }.get(table, ""),
        })

    return {
        "supported_tables": tables,
        "usage": "POST /erp/csv-inject with multipart form: file=@VBAK.csv, config_id=129",
    }
