"""
SAP ATP/CTP Integration API Endpoints

Provides endpoints for:
- Real-time ATP check via SAP BAPI
- Bulk ATP calculation from SAP data
- CTP with production capacity from SAP
- Order promise confirmation with SAP write-back
- Data synchronization triggers
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import date, datetime

from app.api import deps
from app.models.user import User
from app.core.capabilities import require_capabilities

router = APIRouter()


# =============================================================================
# Pydantic Schemas
# =============================================================================

class SAPATPCheckRequest(BaseModel):
    """Request for real-time SAP ATP check."""
    plant: str = Field(..., description="SAP Plant code (e.g., '1000')")
    material: str = Field(..., description="SAP Material number")
    check_date: date = Field(default_factory=date.today, description="Date to check availability")
    quantity: float = Field(default=1.0, ge=0, description="Quantity to check")
    use_bapi: bool = Field(default=True, description="Use BAPI vs table extraction")


class SAPATPCheckResponse(BaseModel):
    """Response from SAP ATP check."""
    plant: str
    material: str
    check_date: date

    # Core ATP
    atp_qty: float
    on_hand_qty: float
    scheduled_receipts_qty: float
    allocated_qty: float
    safety_stock_qty: float

    # SAP breakdown
    unrestricted_stock: float = 0
    quality_inspection_stock: float = 0
    blocked_stock: float = 0
    in_transit_stock: float = 0

    # Supply breakdown
    purchase_order_qty: float = 0
    production_order_qty: float = 0
    stock_transfer_qty: float = 0

    # Demand breakdown
    sales_order_qty: float = 0
    reservation_qty: float = 0

    # Metadata
    bapi_used: bool
    check_timestamp: datetime


class SAPBulkATPRequest(BaseModel):
    """Request for bulk ATP check."""
    plant: str = Field(..., description="SAP Plant code")
    materials: List[str] = Field(..., description="List of material numbers")
    check_date: date = Field(default_factory=date.today)


class SAPCTPCheckRequest(BaseModel):
    """Request for CTP check (includes capacity)."""
    plant: str = Field(..., description="SAP Plant code")
    material: str = Field(..., description="SAP Material number")
    check_date: date = Field(default_factory=date.today)
    quantity: float = Field(..., gt=0, description="Quantity requested")
    check_components: bool = Field(default=True, description="Check component availability")


class SAPCTPCheckResponse(BaseModel):
    """Response from SAP CTP check."""
    plant: str
    material: str
    check_date: date

    # CTP result
    ctp_qty: float
    atp_qty: float
    available_capacity_qty: float

    # Capacity details
    available_capacity_hours: float = 0
    committed_capacity_hours: float = 0
    capacity_utilization_pct: float = 0

    # Lead time
    production_lead_time_days: int = 0

    # Constraint info
    constraining_factor: Optional[str] = None
    constraining_component: Optional[str] = None

    # Promise date
    earliest_ship_date: date
    confidence: float


class OrderPromiseRequest(BaseModel):
    """Request to confirm an order promise."""
    order_id: str = Field(..., description="Sales order number")
    order_line: int = Field(..., description="Sales order line number")
    promised_quantity: float = Field(..., gt=0)
    promised_date: date
    update_sap: bool = Field(default=True, description="Write back to SAP")


class OrderPromiseResponse(BaseModel):
    """Response from order promise confirmation."""
    success: bool
    order_id: str
    sap_document: Optional[str] = None
    message: str


class SyncRequest(BaseModel):
    """Request to trigger SAP data sync."""
    plant: Optional[str] = None
    sync_type: str = Field(
        ...,
        description="Type of sync: inventory, production_orders, safety_stock, scheduled_receipts, all"
    )
    delta_only: bool = Field(default=True, description="Only sync changed records")


class SyncResponse(BaseModel):
    """Response from sync operation."""
    sync_type: str
    records_synced: int
    records_created: int
    records_updated: int
    duration_seconds: float
    delta_mode: bool
    errors: List[str] = []


class ConnectionStatusResponse(BaseModel):
    """SAP connection status."""
    connected: bool
    host: Optional[str] = None
    client: Optional[str] = None
    message: str


# =============================================================================
# Helper Functions
# =============================================================================

def _get_sap_atp_bridge(db: Session):
    """Create SAP ATP bridge instance from environment config."""
    from app.core.config import settings
    from app.integrations.sap.s4hana_connector import S4HANAConnectionConfig
    from app.integrations.sap.sap_atp_bridge import SAPATPBridge, SAPATPConfig

    # Check if SAP is configured
    if not getattr(settings, 'SAP_HOST', None):
        raise HTTPException(
            status_code=503,
            detail="SAP integration not configured. Set SAP_HOST environment variable."
        )

    config = SAPATPConfig(
        s4hana_config=S4HANAConnectionConfig(
            ashost=settings.SAP_HOST,
            sysnr=getattr(settings, 'SAP_SYSNR', '00'),
            client=getattr(settings, 'SAP_CLIENT', '100'),
            user=getattr(settings, 'SAP_USER', ''),
            passwd=getattr(settings, 'SAP_PASSWORD', ''),
        ),
        use_realtime_bapi=getattr(settings, 'SAP_USE_BAPI', True),
        fallback_to_batch=True,
    )

    return SAPATPBridge(config=config, db=db)


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/status", response_model=ConnectionStatusResponse)
async def check_sap_connection_status(
    db: Session = Depends(deps.get_sync_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Check SAP connection status.

    Returns whether SAP integration is configured and can connect.
    """
    from app.core.config import settings

    sap_host = getattr(settings, 'SAP_HOST', None)

    if not sap_host:
        return ConnectionStatusResponse(
            connected=False,
            message="SAP integration not configured"
        )

    try:
        bridge = _get_sap_atp_bridge(db)
        connected = bridge.connect()
        bridge.disconnect()

        return ConnectionStatusResponse(
            connected=connected,
            host=sap_host,
            client=getattr(settings, 'SAP_CLIENT', '100'),
            message="Connected successfully" if connected else "Connection failed"
        )
    except Exception as e:
        return ConnectionStatusResponse(
            connected=False,
            host=sap_host,
            message=f"Connection error: {str(e)}"
        )


@router.post("/check-atp", response_model=SAPATPCheckResponse)
@require_capabilities(["view_atp_ctp"])
async def check_atp_sap(
    request: SAPATPCheckRequest,
    db: Session = Depends(deps.get_sync_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Real-time ATP check against SAP S/4HANA.

    Uses BAPI_MATERIAL_AVAILABILITY for instant check, with fallback
    to table extraction if BAPI fails.

    Returns:
        ATP breakdown with on-hand, scheduled receipts, allocations, and safety stock.
    """
    bridge = _get_sap_atp_bridge(db)

    try:
        if not bridge.connect():
            raise HTTPException(status_code=503, detail="Failed to connect to SAP")

        result = bridge.check_atp_realtime(
            plant=request.plant,
            material=request.material,
            check_date=request.check_date,
            quantity=request.quantity
        )

        return SAPATPCheckResponse(
            plant=result.sap_plant,
            material=result.sap_material,
            check_date=result.sap_check_date,
            atp_qty=result.atp.atp,
            on_hand_qty=result.atp.on_hand,
            scheduled_receipts_qty=result.atp.scheduled_receipts,
            allocated_qty=result.atp.allocated_orders,
            safety_stock_qty=result.atp.safety_stock,
            unrestricted_stock=result.unrestricted_stock,
            quality_inspection_stock=result.quality_inspection_stock,
            blocked_stock=result.blocked_stock,
            in_transit_stock=result.in_transit_stock,
            purchase_order_qty=result.purchase_order_qty,
            production_order_qty=result.production_order_qty,
            stock_transfer_qty=result.stock_transfer_qty,
            sales_order_qty=result.sales_order_qty,
            reservation_qty=result.reservation_qty,
            bapi_used=result.bapi_used,
            check_timestamp=datetime.utcnow()
        )

    finally:
        bridge.disconnect()


@router.post("/check-atp/bulk", response_model=Dict[str, SAPATPCheckResponse])
@require_capabilities(["view_atp_ctp"])
async def check_atp_bulk(
    request: SAPBulkATPRequest,
    db: Session = Depends(deps.get_sync_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Bulk ATP check for multiple materials.

    More efficient than multiple single checks - uses batch extraction.

    Returns:
        Dictionary mapping material number to ATP result.
    """
    bridge = _get_sap_atp_bridge(db)

    try:
        if not bridge.connect():
            raise HTTPException(status_code=503, detail="Failed to connect to SAP")

        results = bridge.check_atp_bulk(
            plant=request.plant,
            materials=request.materials,
            check_date=request.check_date
        )

        return {
            material: SAPATPCheckResponse(
                plant=result.sap_plant,
                material=material,
                check_date=result.sap_check_date,
                atp_qty=result.atp.atp,
                on_hand_qty=result.atp.on_hand,
                scheduled_receipts_qty=result.atp.scheduled_receipts,
                allocated_qty=result.atp.allocated_orders,
                safety_stock_qty=result.atp.safety_stock,
                unrestricted_stock=result.unrestricted_stock,
                quality_inspection_stock=result.quality_inspection_stock,
                blocked_stock=result.blocked_stock,
                in_transit_stock=result.in_transit_stock,
                purchase_order_qty=result.purchase_order_qty,
                production_order_qty=result.production_order_qty,
                stock_transfer_qty=result.stock_transfer_qty,
                sales_order_qty=result.sales_order_qty,
                reservation_qty=result.reservation_qty,
                bapi_used=result.bapi_used,
                check_timestamp=datetime.utcnow()
            )
            for material, result in results.items()
        }

    finally:
        bridge.disconnect()


@router.post("/check-ctp", response_model=SAPCTPCheckResponse)
@require_capabilities(["view_atp_ctp"])
async def check_ctp_sap(
    request: SAPCTPCheckRequest,
    db: Session = Depends(deps.get_sync_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    CTP check including SAP production capacity.

    Steps:
    1. Check ATP for finished good
    2. Get production capacity and WIP from SAP
    3. Check component ATP (BOM explosion)
    4. Calculate CTP and promise date

    Returns:
        CTP result with capacity breakdown, constraints, and earliest ship date.
    """
    from datetime import timedelta

    bridge = _get_sap_atp_bridge(db)

    try:
        if not bridge.connect():
            raise HTTPException(status_code=503, detail="Failed to connect to SAP")

        result = bridge.check_ctp_realtime(
            plant=request.plant,
            material=request.material,
            check_date=request.check_date,
            quantity=request.quantity
        )

        # Calculate promise date based on lead time
        lead_time_days = result.production_lead_time_days or 1
        earliest_ship = request.check_date + timedelta(days=lead_time_days)

        # Determine confidence based on capacity buffer
        confidence = 0.95 if result.ctp.ctp >= request.quantity else 0.75

        return SAPCTPCheckResponse(
            plant=result.sap_plant,
            material=result.sap_material,
            check_date=request.check_date,
            ctp_qty=result.ctp.ctp,
            atp_qty=result.ctp.available_capacity,
            available_capacity_qty=result.ctp.production_capacity - result.ctp.current_commitments,
            available_capacity_hours=result.available_capacity_hours,
            committed_capacity_hours=result.committed_capacity_hours,
            capacity_utilization_pct=result.capacity_utilization_pct,
            production_lead_time_days=lead_time_days,
            constraining_factor=result.ctp.constrained_by,
            constraining_component=result.constraining_component,
            earliest_ship_date=earliest_ship,
            confidence=confidence
        )

    finally:
        bridge.disconnect()


@router.post("/confirm-promise", response_model=OrderPromiseResponse)
@require_capabilities(["manage_atp_ctp"])
async def confirm_order_promise(
    request: OrderPromiseRequest,
    db: Session = Depends(deps.get_sync_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Confirm an order promise and optionally update SAP.

    Creates an order promise record and calls SAP BAPI to update
    sales order confirmed quantity and schedule line.

    Returns:
        Success status and SAP document number if updated.
    """
    bridge = _get_sap_atp_bridge(db)

    if not request.update_sap:
        # Just create local record without SAP update
        return OrderPromiseResponse(
            success=True,
            order_id=request.order_id,
            sap_document=None,
            message="Promise created (SAP update skipped)"
        )

    try:
        if not bridge.connect():
            return OrderPromiseResponse(
                success=False,
                order_id=request.order_id,
                sap_document=None,
                message="Failed to connect to SAP"
            )

        success, result = bridge.confirm_order_promise(
            order_id=request.order_id,
            order_line=request.order_line,
            promised_quantity=request.promised_quantity,
            promised_date=request.promised_date,
            update_sap=True
        )

        return OrderPromiseResponse(
            success=success,
            order_id=request.order_id,
            sap_document=result if success else None,
            message="Promise confirmed in SAP" if success else result
        )

    finally:
        bridge.disconnect()


@router.post("/sync", response_model=SyncResponse)
@require_capabilities(["manage_atp_ctp"])
async def trigger_sap_sync(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(deps.get_sync_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Trigger SAP data synchronization.

    Sync types:
    - inventory: Sync MARD inventory levels
    - production_orders: Sync AFKO/AFPO production orders
    - safety_stock: Sync MARC.EISBE safety stock policies
    - scheduled_receipts: Sync EKET schedule lines
    - all: Sync all data types

    Returns:
        Sync statistics including records synced and duration.
    """
    bridge = _get_sap_atp_bridge(db)
    start_time = datetime.utcnow()

    try:
        if not bridge.connect():
            raise HTTPException(status_code=503, detail="Failed to connect to SAP")

        total_synced = 0
        total_created = 0
        total_updated = 0
        errors = []

        sync_types = [request.sync_type] if request.sync_type != "all" else [
            "inventory", "production_orders", "safety_stock", "scheduled_receipts"
        ]

        for sync_type in sync_types:
            try:
                if sync_type == "inventory":
                    result = bridge.sync_inventory_levels(
                        plant=request.plant,
                        delta_only=request.delta_only
                    )
                elif sync_type == "production_orders":
                    result = bridge.sync_production_orders(plant=request.plant)
                elif sync_type == "safety_stock":
                    result = bridge.sync_safety_stock_policies(plant=request.plant)
                elif sync_type == "scheduled_receipts":
                    result = bridge.sync_scheduled_receipts(plant=request.plant)
                else:
                    continue

                total_synced += result.records_synced
                total_created += result.records_created
                total_updated += result.records_updated
                errors.extend(result.errors)

            except Exception as e:
                errors.append(f"{sync_type}: {str(e)}")

        duration = (datetime.utcnow() - start_time).total_seconds()

        return SyncResponse(
            sync_type=request.sync_type,
            records_synced=total_synced,
            records_created=total_created,
            records_updated=total_updated,
            duration_seconds=duration,
            delta_mode=request.delta_only,
            errors=errors
        )

    finally:
        bridge.disconnect()


@router.get("/materials/{plant}", response_model=List[Dict])
@require_capabilities(["view_atp_ctp"])
async def list_materials_for_atp(
    plant: str,
    db: Session = Depends(deps.get_sync_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    List materials available for ATP check at a plant.

    Returns materials with their ATP settings from MARC.
    """
    bridge = _get_sap_atp_bridge(db)

    try:
        if not bridge.connect():
            raise HTTPException(status_code=503, detail="Failed to connect to SAP")

        marc_df = bridge.connector.extract_material_atp_data(plant=plant)

        if marc_df.empty:
            return []

        materials = []
        for _, row in marc_df.iterrows():
            materials.append({
                "material": str(row['MATNR']).strip(),
                "plant": str(row['WERKS']).strip(),
                "safety_stock": float(row.get('EISBE', 0) or 0),
                "lead_time_days": int(row.get('PLIFZ', 0) or 0),
                "mrp_controller": str(row.get('DISPO', '')).strip(),
                "availability_check_group": str(row.get('MTVFP', '')).strip(),
            })

        return materials

    finally:
        bridge.disconnect()
