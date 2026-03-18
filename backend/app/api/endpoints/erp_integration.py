"""
ERP Integration API Endpoints

Unified API for managing ERP connections, field mapping, data extraction,
and ingestion monitoring across SAP, Odoo, and Dynamics 365 F&O.

Extends (not replaces) the existing SAP-specific endpoints at /sap-data.
"""

import logging
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


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
):
    """List all ERP connections for the current tenant."""
    # NOTE: In production, inject db session and current_user via Depends()
    # For now, return schema documentation
    return []


@router.post("/connections", response_model=ERPConnectionResponse)
async def create_erp_connection(body: ERPConnectionCreate):
    """Create a new ERP connection."""
    raise HTTPException(501, "Connect via tenant admin — implementation uses db session injection")


@router.post("/connections/{connection_id}/test", response_model=ERPTestResult)
async def test_erp_connection(connection_id: int):
    """Test an ERP connection and return server info."""
    raise HTTPException(501, "Implementation requires db session for connection lookup")


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
    else:
        raise HTTPException(400, f"Unsupported ERP type: {erp_type}. Supported: odoo, d365, sap")


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
