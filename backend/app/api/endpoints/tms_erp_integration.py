"""
TMS ERP Integration API Endpoints

TMS-specific data extraction and decision injection for external TMS systems
(SAP TM, Oracle OTM, Blue Yonder, Manhattan). Uses the TMSExtractionAdapter
pattern — each vendor implements the same interface.

Extends the generic ERP integration at /erp-integration with TMS-specific
extraction types (shipments, loads, carriers, rates, appointments, exceptions)
and decision injection (carrier assignment, appointment change, load plan).

Routes:
    POST /tms-integration/extract/{connection_id}     — trigger extraction
    POST /tms-integration/test/{connection_id}        — test connection
    POST /tms-integration/inject/{connection_id}      — inject decision
    GET  /tms-integration/supported-systems            — list supported TMS systems
"""

import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Pydantic Schemas ─────────────────────────────────────────────────────────

class TMSExtractionRequest(BaseModel):
    """Request to trigger a TMS data extraction."""
    entity_types: Optional[List[str]] = Field(
        default=None,
        description="Which entities to extract: shipments, loads, carriers, rates, appointments, exceptions. Default: all.",
    )
    mode: str = Field(
        default="incremental",
        description="Extraction mode: full, incremental, or historical",
    )
    since: Optional[str] = Field(
        default=None,
        description="ISO datetime — for incremental mode, extract records changed since this time",
    )
    batch_size: int = Field(default=500, ge=1, le=10000)


class TMSExtractionResponse(BaseModel):
    status: str
    connection_id: Optional[int] = None
    erp_type: Optional[str] = None
    mode: Optional[str] = None
    entity_types: Optional[List[str]] = None
    results: Optional[List[dict]] = None
    duration_seconds: Optional[float] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class TMSInjectionRequest(BaseModel):
    """Request to inject a decision into the external TMS."""
    decision_id: int
    decision_type: str = Field(
        description="carrier_assignment, appointment_change, load_plan",
    )
    shipment_external_id: Optional[str] = None
    appointment_external_id: Optional[str] = None
    load_external_id: Optional[str] = None
    carrier_id: Optional[str] = None
    rate: Optional[float] = None
    new_start: Optional[str] = None
    new_end: Optional[str] = None
    shipment_ids: Optional[List[str]] = None
    equipment_type: Optional[str] = None
    metadata: Optional[dict] = None


class TMSInjectionResponse(BaseModel):
    success: bool
    decision_id: Optional[int] = None
    decision_type: Optional[str] = None
    external_id: Optional[str] = None
    error: Optional[str] = None


# ── Extraction ───────────────────────────────────────────────────────────────

@router.post("/extract/{connection_id}", response_model=TMSExtractionResponse)
async def extract_tms_data(
    connection_id: int,
    body: TMSExtractionRequest,
    tenant_id: int = Query(..., description="Tenant ID"),
    db=Depends(get_db),
):
    """
    Trigger a TMS data extraction job.

    Extracts shipments, loads, carriers, rates, appointments, and/or
    exceptions from the external TMS system connected via `connection_id`.

    The connection must be an active ERPConnection record for this tenant
    with a supported erp_type (sap, sap_s4hana, sap_tm, oracle_otm,
    blue_yonder, manhattan).

    Modes:
    - **full**: Extract all records (initial load or periodic refresh)
    - **incremental**: Only records changed since `since` (or last watermark)
    - **historical**: Bulk extraction for ML training (6-24 months)
    """
    from app.services.tms_extraction_service import TMSExtractionService

    since_dt = None
    if body.since:
        try:
            since_dt = datetime.fromisoformat(body.since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, f"Invalid 'since' datetime: {body.since}")

    service = TMSExtractionService(db)
    result = await service.run_extraction(
        connection_id=connection_id,
        tenant_id=tenant_id,
        entity_types=body.entity_types,
        mode=body.mode,
        since=since_dt,
    )

    if result.get("status") == "error":
        raise HTTPException(400, result.get("error", "Extraction failed"))

    return result


# ── Test Connection ──────────────────────────────────────────────────────────

@router.post("/test/{connection_id}")
async def test_tms_connection(
    connection_id: int,
    tenant_id: int = Query(..., description="Tenant ID"),
    db=Depends(get_db),
):
    """
    Test a TMS-compatible ERP connection.

    Verifies that the connection credentials are valid, the external TMS
    is reachable, and the adapter can authenticate.
    """
    from app.services.tms_extraction_service import TMSExtractionService

    service = TMSExtractionService(db)
    return await service.test_connection(connection_id, tenant_id)


# ── Decision Injection ───────────────────────────────────────────────────────

@router.post("/inject/{connection_id}", response_model=TMSInjectionResponse)
async def inject_decision(
    connection_id: int,
    body: TMSInjectionRequest,
    tenant_id: int = Query(..., description="Tenant ID"),
    db=Depends(get_db),
):
    """
    Push an AIIO-governed decision back to the external TMS.

    Called when the governance pipeline approves a decision for execution
    in the external system. Supports:
    - **carrier_assignment**: Assign a carrier to a shipment/freight order
    - **appointment_change**: Reschedule a dock appointment
    - **load_plan**: Update load composition (assign shipments to a load)
    """
    from app.services.tms_extraction_service import TMSExtractionService

    service = TMSExtractionService(db)
    result = await service.inject_decision(
        connection_id=connection_id,
        tenant_id=tenant_id,
        decision=body.dict(),
    )

    if not result.get("success") and result.get("error"):
        raise HTTPException(400, result["error"])

    return result


# ── Supported Systems ────────────────────────────────────────────────────────

@router.get("/supported-systems")
async def list_supported_tms_systems():
    """List all TMS systems that Autonomy can integrate with."""
    return {
        "systems": [
            {
                "erp_type": "sap_tm",
                "name": "SAP Transportation Management",
                "vendor": "SAP",
                "connection_methods": ["rfc", "odata"],
                "extraction_entities": [
                    "shipments", "loads", "carriers", "rates",
                    "appointments", "exceptions",
                ],
                "injection_capabilities": [
                    "carrier_assignment", "appointment_change",
                ],
                "status": "available",
                "notes": "Requires SAP S/4HANA with TM module. RFC needs pyrfc; OData needs API access.",
            },
            {
                "erp_type": "oracle_otm",
                "name": "Oracle Transportation Management",
                "vendor": "Oracle",
                "connection_methods": ["rest_api"],
                "extraction_entities": [
                    "shipments", "loads", "carriers", "rates",
                    "appointments", "exceptions",
                ],
                "injection_capabilities": [
                    "carrier_assignment", "appointment_change", "load_plan",
                ],
                "status": "planned",
                "notes": "REST API via Oracle Integration Cloud. Implementation pending.",
            },
            {
                "erp_type": "blue_yonder",
                "name": "Blue Yonder TMS",
                "vendor": "Blue Yonder",
                "connection_methods": ["rest_api"],
                "extraction_entities": [
                    "shipments", "loads", "carriers", "rates",
                    "appointments", "exceptions",
                ],
                "injection_capabilities": [
                    "carrier_assignment", "appointment_change", "load_plan",
                ],
                "status": "planned",
                "notes": "REST-native API. Implementation pending.",
            },
            {
                "erp_type": "manhattan",
                "name": "Manhattan Active TM",
                "vendor": "Manhattan Associates",
                "connection_methods": ["rest_api"],
                "extraction_entities": [
                    "shipments", "loads", "carriers", "rates",
                ],
                "injection_capabilities": [
                    "carrier_assignment",
                ],
                "status": "planned",
                "notes": "Modern REST API. Implementation pending.",
            },
        ],
    }
