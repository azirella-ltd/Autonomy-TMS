"""
Carrier Integration API

Provides abstraction layer for connecting with carrier APIs.
Supports rate retrieval, tracking, and label generation.

Phase 3.5: Carrier Integration Framework
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
import uuid
import hashlib

from app.db.session import get_db

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class Address(BaseModel):
    """Standard address format."""
    name: str = Field(..., max_length=100)
    company: Optional[str] = Field(None, max_length=100)
    street1: str = Field(..., max_length=200)
    street2: Optional[str] = Field(None, max_length=200)
    city: str = Field(..., max_length=100)
    state: str = Field(..., max_length=50)
    postal_code: str = Field(..., max_length=20)
    country: str = Field(default="US", max_length=2)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)


class Package(BaseModel):
    """Package dimensions and weight."""
    weight: float = Field(..., gt=0, description="Weight in pounds")
    length: float = Field(..., gt=0, description="Length in inches")
    width: float = Field(..., gt=0, description="Width in inches")
    height: float = Field(..., gt=0, description="Height in inches")
    packaging_type: str = Field(default="box", description="box, envelope, tube, pallet")
    declared_value: Optional[float] = Field(None, description="Declared value for insurance")


class RateRequest(BaseModel):
    """Request for shipping rates."""
    origin: Address
    destination: Address
    packages: List[Package]
    ship_date: Optional[datetime] = None
    service_types: Optional[List[str]] = Field(None, description="Filter by service types")
    carrier_ids: Optional[List[str]] = Field(None, description="Filter by carriers")
    residential: bool = Field(default=False)
    signature_required: bool = Field(default=False)
    insurance_required: bool = Field(default=False)


class Rate(BaseModel):
    """Shipping rate from a carrier."""
    carrier_id: str
    carrier_name: str
    service_type: str
    service_name: str
    rate: float
    currency: str = "USD"
    estimated_delivery_date: Optional[datetime]
    transit_days: Optional[int]
    guaranteed: bool = False
    negotiated_rate: Optional[float] = None
    fuel_surcharge: Optional[float] = None
    additional_charges: Optional[List[Dict[str, Any]]] = None


class RateResponse(BaseModel):
    """Response containing shipping rates."""
    success: bool
    request_id: str
    rates: List[Rate]
    cheapest_rate: Optional[Rate]
    fastest_rate: Optional[Rate]
    message: Optional[str]


class ShipmentRequest(BaseModel):
    """Request to create a shipment."""
    origin: Address
    destination: Address
    packages: List[Package]
    carrier_id: str
    service_type: str
    ship_date: Optional[datetime] = None
    reference: Optional[str] = None
    po_number: Optional[str] = None
    special_instructions: Optional[str] = None
    signature_required: bool = False
    insurance_required: bool = False
    saturday_delivery: bool = False
    return_label: bool = False


class ShipmentResponse(BaseModel):
    """Response for created shipment."""
    success: bool
    shipment_id: str
    tracking_number: str
    carrier_id: str
    service_type: str
    label_url: Optional[str]
    label_format: str = "PDF"
    estimated_delivery_date: Optional[datetime]
    total_charge: float
    message: Optional[str]


class TrackingEvent(BaseModel):
    """Single tracking event."""
    timestamp: datetime
    status: str
    description: str
    location: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]


class TrackingResponse(BaseModel):
    """Response for tracking request."""
    success: bool
    tracking_number: str
    carrier_id: str
    carrier_name: str
    status: str
    status_detail: str
    estimated_delivery: Optional[datetime]
    actual_delivery: Optional[datetime]
    signed_by: Optional[str]
    events: List[TrackingEvent]
    origin: Optional[Address]
    destination: Optional[Address]
    weight: Optional[float]
    dimensions: Optional[str]


class CarrierConfig(BaseModel):
    """Carrier configuration."""
    carrier_id: str
    carrier_name: str
    api_endpoint: Optional[str]
    api_key: Optional[str]
    api_secret: Optional[str]
    account_number: Optional[str]
    meter_number: Optional[str]
    is_active: bool = True
    supported_services: List[str] = []
    rate_multiplier: float = 1.0
    handling_fee: float = 0.0


class CarrierConfigResponse(BaseModel):
    """Response for carrier configuration."""
    carrier_id: str
    carrier_name: str
    is_active: bool
    supported_services: List[str]
    last_rate_update: Optional[datetime]


# ============================================================================
# Mock Carrier Data (would be replaced with actual API integrations)
# ============================================================================

MOCK_CARRIERS = {
    "fedex": {
        "name": "FedEx",
        "services": [
            {"code": "FEDEX_GROUND", "name": "FedEx Ground", "transit_days": 5},
            {"code": "FEDEX_EXPRESS_SAVER", "name": "FedEx Express Saver", "transit_days": 3},
            {"code": "FEDEX_2DAY", "name": "FedEx 2Day", "transit_days": 2},
            {"code": "FEDEX_STANDARD_OVERNIGHT", "name": "FedEx Standard Overnight", "transit_days": 1},
            {"code": "FEDEX_PRIORITY_OVERNIGHT", "name": "FedEx Priority Overnight", "transit_days": 1},
        ]
    },
    "ups": {
        "name": "UPS",
        "services": [
            {"code": "UPS_GROUND", "name": "UPS Ground", "transit_days": 5},
            {"code": "UPS_3_DAY_SELECT", "name": "UPS 3 Day Select", "transit_days": 3},
            {"code": "UPS_2ND_DAY_AIR", "name": "UPS 2nd Day Air", "transit_days": 2},
            {"code": "UPS_NEXT_DAY_AIR_SAVER", "name": "UPS Next Day Air Saver", "transit_days": 1},
            {"code": "UPS_NEXT_DAY_AIR", "name": "UPS Next Day Air", "transit_days": 1},
        ]
    },
    "usps": {
        "name": "USPS",
        "services": [
            {"code": "USPS_GROUND_ADVANTAGE", "name": "USPS Ground Advantage", "transit_days": 5},
            {"code": "USPS_PRIORITY_MAIL", "name": "USPS Priority Mail", "transit_days": 3},
            {"code": "USPS_PRIORITY_MAIL_EXPRESS", "name": "Priority Mail Express", "transit_days": 2},
        ]
    },
    "dhl": {
        "name": "DHL",
        "services": [
            {"code": "DHL_EXPRESS_WORLDWIDE", "name": "DHL Express Worldwide", "transit_days": 4},
            {"code": "DHL_EXPRESS_1030", "name": "DHL Express 10:30", "transit_days": 2},
            {"code": "DHL_EXPRESS_0900", "name": "DHL Express 9:00", "transit_days": 1},
        ]
    }
}


def calculate_mock_rate(carrier_id: str, service_code: str, packages: List[Package], distance_factor: float = 1.0) -> float:
    """Calculate mock shipping rate based on weight and dimensions."""
    total_weight = sum(p.weight for p in packages)
    total_dim_weight = sum((p.length * p.width * p.height) / 139 for p in packages)
    billable_weight = max(total_weight, total_dim_weight)

    # Base rates per pound by service speed
    base_rates = {
        1: 15.0,  # Overnight
        2: 10.0,  # 2-day
        3: 7.0,   # 3-day
        5: 4.0,   # Ground
    }

    # Find transit days for this service
    carrier = MOCK_CARRIERS.get(carrier_id, {})
    services = carrier.get("services", [])
    service = next((s for s in services if s["code"] == service_code), None)
    transit_days = service["transit_days"] if service else 5

    base_rate = base_rates.get(transit_days, 5.0)
    rate = billable_weight * base_rate * distance_factor

    # Add fuel surcharge (mock 10%)
    rate *= 1.10

    # Minimum charge
    return max(rate, 8.99)


def generate_mock_tracking_number(carrier_id: str) -> str:
    """Generate mock tracking number."""
    prefix = {
        "fedex": "7489",
        "ups": "1Z",
        "usps": "9400",
        "dhl": "JD"
    }.get(carrier_id, "TRK")

    random_part = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()[:12].upper()
    return f"{prefix}{random_part}"


# ============================================================================
# Rate Shopping Endpoints
# ============================================================================

@router.post("/rates", response_model=RateResponse)
async def get_shipping_rates(
    request: RateRequest,
    db: Session = Depends(get_db)
):
    """
    Get shipping rates from all configured carriers.

    Returns rates sorted by price, with cheapest and fastest options highlighted.
    """
    request_id = str(uuid.uuid4())
    rates = []

    # Calculate distance factor (mock - would use actual geocoding)
    distance_factor = 1.0
    if request.destination.state != request.origin.state:
        distance_factor = 1.5
    if request.destination.country != request.origin.country:
        distance_factor = 3.0

    # Get rates from each carrier
    carrier_ids = request.carrier_ids or list(MOCK_CARRIERS.keys())

    for carrier_id in carrier_ids:
        if carrier_id not in MOCK_CARRIERS:
            continue

        carrier = MOCK_CARRIERS[carrier_id]

        for service in carrier["services"]:
            # Filter by service type if specified
            if request.service_types and service["code"] not in request.service_types:
                continue

            rate_amount = calculate_mock_rate(
                carrier_id, service["code"], request.packages, distance_factor
            )

            # Add residential surcharge
            if request.residential:
                rate_amount += 4.50

            # Add signature surcharge
            if request.signature_required:
                rate_amount += 5.00

            ship_date = request.ship_date or datetime.utcnow()
            estimated_delivery = ship_date + timedelta(days=service["transit_days"])

            rates.append(Rate(
                carrier_id=carrier_id,
                carrier_name=carrier["name"],
                service_type=service["code"],
                service_name=service["name"],
                rate=round(rate_amount, 2),
                estimated_delivery_date=estimated_delivery,
                transit_days=service["transit_days"],
                guaranteed=service["transit_days"] <= 2,
                fuel_surcharge=round(rate_amount * 0.10, 2),
            ))

    # Sort by rate
    rates.sort(key=lambda r: r.rate)

    # Find cheapest and fastest
    cheapest = rates[0] if rates else None
    fastest = min(rates, key=lambda r: r.transit_days) if rates else None

    return RateResponse(
        success=True,
        request_id=request_id,
        rates=rates,
        cheapest_rate=cheapest,
        fastest_rate=fastest,
        message=f"Found {len(rates)} rates from {len(carrier_ids)} carriers"
    )


@router.get("/rates/compare")
async def compare_rates(
    origin_zip: str,
    destination_zip: str,
    weight: float = Query(..., gt=0),
    length: float = Query(default=10),
    width: float = Query(default=10),
    height: float = Query(default=10),
    db: Session = Depends(get_db)
):
    """Quick rate comparison with minimal input."""
    package = Package(weight=weight, length=length, width=width, height=height)

    rates = []
    for carrier_id, carrier in MOCK_CARRIERS.items():
        for service in carrier["services"]:
            rate = calculate_mock_rate(carrier_id, service["code"], [package])
            rates.append({
                "carrier": carrier["name"],
                "service": service["name"],
                "rate": round(rate, 2),
                "transit_days": service["transit_days"]
            })

    rates.sort(key=lambda r: r["rate"])

    return {
        "origin_zip": origin_zip,
        "destination_zip": destination_zip,
        "package": {"weight": weight, "dimensions": f"{length}x{width}x{height}"},
        "rates": rates[:10]  # Top 10 rates
    }


# ============================================================================
# Shipment Creation Endpoints
# ============================================================================

@router.post("/shipments", response_model=ShipmentResponse)
async def create_shipment(
    request: ShipmentRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Create a shipment and generate shipping label.

    In production, this would call the carrier's API to purchase the label.
    """
    if request.carrier_id not in MOCK_CARRIERS:
        raise HTTPException(status_code=400, detail=f"Unknown carrier: {request.carrier_id}")

    carrier = MOCK_CARRIERS[request.carrier_id]
    service = next(
        (s for s in carrier["services"] if s["code"] == request.service_type),
        None
    )

    if not service:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown service type: {request.service_type}"
        )

    # Generate tracking number
    tracking_number = generate_mock_tracking_number(request.carrier_id)
    shipment_id = str(uuid.uuid4())

    # Calculate rate
    rate = calculate_mock_rate(request.carrier_id, request.service_type, request.packages)

    ship_date = request.ship_date or datetime.utcnow()
    estimated_delivery = ship_date + timedelta(days=service["transit_days"])

    # In production: Call carrier API to create shipment and get label
    # For now, return mock response
    label_url = f"/api/carrier-integration/labels/{shipment_id}/download"

    return ShipmentResponse(
        success=True,
        shipment_id=shipment_id,
        tracking_number=tracking_number,
        carrier_id=request.carrier_id,
        service_type=request.service_type,
        label_url=label_url,
        label_format="PDF",
        estimated_delivery_date=estimated_delivery,
        total_charge=round(rate, 2),
        message=f"Shipment created with tracking number {tracking_number}"
    )


@router.get("/shipments/{shipment_id}")
async def get_shipment(
    shipment_id: str,
    db: Session = Depends(get_db)
):
    """Get shipment details."""
    # In production: Look up shipment in database
    return {
        "shipment_id": shipment_id,
        "status": "created",
        "message": "Shipment details would be retrieved from database"
    }


@router.delete("/shipments/{shipment_id}")
async def cancel_shipment(
    shipment_id: str,
    db: Session = Depends(get_db)
):
    """Cancel/void a shipment."""
    # In production: Call carrier API to void shipment
    return {
        "success": True,
        "shipment_id": shipment_id,
        "status": "cancelled",
        "refund_amount": 0,  # Would calculate actual refund
        "message": "Shipment cancelled successfully"
    }


# ============================================================================
# Tracking Endpoints
# ============================================================================

@router.get("/tracking/{tracking_number}", response_model=TrackingResponse)
async def track_shipment(
    tracking_number: str,
    carrier_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get tracking information for a shipment.

    If carrier_id is not provided, attempts to detect carrier from tracking number.
    """
    # Detect carrier from tracking number if not provided
    if not carrier_id:
        if tracking_number.startswith("1Z"):
            carrier_id = "ups"
        elif tracking_number.startswith("7489") or tracking_number.startswith("9"):
            carrier_id = "fedex"
        elif tracking_number.startswith("9400") or tracking_number.startswith("9"):
            carrier_id = "usps"
        elif tracking_number.startswith("JD"):
            carrier_id = "dhl"
        else:
            carrier_id = "unknown"

    carrier = MOCK_CARRIERS.get(carrier_id, {"name": "Unknown Carrier"})

    # Generate mock tracking events
    now = datetime.utcnow()
    events = [
        TrackingEvent(
            timestamp=now - timedelta(days=3),
            status="PICKED_UP",
            description="Package picked up",
            location="Origin Facility",
            city="Los Angeles",
            state="CA",
            country="US"
        ),
        TrackingEvent(
            timestamp=now - timedelta(days=2),
            status="IN_TRANSIT",
            description="Departed origin facility",
            location="Los Angeles Hub",
            city="Los Angeles",
            state="CA",
            country="US"
        ),
        TrackingEvent(
            timestamp=now - timedelta(days=1),
            status="IN_TRANSIT",
            description="Arrived at destination facility",
            location="Chicago Hub",
            city="Chicago",
            state="IL",
            country="US"
        ),
        TrackingEvent(
            timestamp=now - timedelta(hours=6),
            status="OUT_FOR_DELIVERY",
            description="Out for delivery",
            location="Local Delivery Center",
            city="Chicago",
            state="IL",
            country="US"
        ),
    ]

    return TrackingResponse(
        success=True,
        tracking_number=tracking_number,
        carrier_id=carrier_id,
        carrier_name=carrier["name"],
        status="OUT_FOR_DELIVERY",
        status_detail="Package is out for delivery",
        estimated_delivery=now + timedelta(hours=4),
        actual_delivery=None,
        signed_by=None,
        events=events,
        weight=5.0,
        dimensions="10x10x10"
    )


@router.post("/tracking/batch")
async def track_multiple_shipments(
    tracking_numbers: List[str],
    db: Session = Depends(get_db)
):
    """Track multiple shipments at once."""
    results = []
    for tracking_number in tracking_numbers[:50]:  # Limit to 50
        try:
            # Would call track_shipment for each
            results.append({
                "tracking_number": tracking_number,
                "status": "IN_TRANSIT",
                "carrier": "auto-detected"
            })
        except Exception as e:
            results.append({
                "tracking_number": tracking_number,
                "error": str(e)
            })

    return {
        "success": True,
        "total": len(tracking_numbers),
        "results": results
    }


# ============================================================================
# Carrier Configuration Endpoints
# ============================================================================

@router.get("/carriers", response_model=List[CarrierConfigResponse])
async def list_carriers(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """List all configured carriers."""
    carriers = []
    for carrier_id, carrier in MOCK_CARRIERS.items():
        carriers.append(CarrierConfigResponse(
            carrier_id=carrier_id,
            carrier_name=carrier["name"],
            is_active=True,
            supported_services=[s["code"] for s in carrier["services"]],
            last_rate_update=datetime.utcnow()
        ))
    return carriers


@router.get("/carriers/{carrier_id}")
async def get_carrier(
    carrier_id: str,
    db: Session = Depends(get_db)
):
    """Get carrier configuration and available services."""
    if carrier_id not in MOCK_CARRIERS:
        raise HTTPException(status_code=404, detail="Carrier not found")

    carrier = MOCK_CARRIERS[carrier_id]
    return {
        "carrier_id": carrier_id,
        "carrier_name": carrier["name"],
        "is_active": True,
        "services": carrier["services"],
        "supported_countries": ["US", "CA", "MX"],
        "supports_international": carrier_id in ["fedex", "ups", "dhl"],
        "supports_returns": True,
        "supports_insurance": True
    }


@router.get("/carriers/{carrier_id}/services")
async def get_carrier_services(
    carrier_id: str,
    db: Session = Depends(get_db)
):
    """Get available services for a carrier."""
    if carrier_id not in MOCK_CARRIERS:
        raise HTTPException(status_code=404, detail="Carrier not found")

    return {
        "carrier_id": carrier_id,
        "services": MOCK_CARRIERS[carrier_id]["services"]
    }


# ============================================================================
# Label Management Endpoints
# ============================================================================

@router.get("/labels/{shipment_id}/download")
async def download_label(
    shipment_id: str,
    format: str = Query(default="PDF", description="PDF, PNG, ZPL"),
    db: Session = Depends(get_db)
):
    """Download shipping label for a shipment."""
    # In production: Generate actual label from carrier API
    return {
        "shipment_id": shipment_id,
        "format": format,
        "message": "Label download would be implemented with actual carrier API",
        "label_url": f"https://example.com/labels/{shipment_id}.{format.lower()}"
    }


@router.post("/labels/batch")
async def generate_batch_labels(
    shipment_ids: List[str],
    format: str = Query(default="PDF"),
    db: Session = Depends(get_db)
):
    """Generate labels for multiple shipments."""
    labels = []
    for shipment_id in shipment_ids[:100]:  # Limit to 100
        labels.append({
            "shipment_id": shipment_id,
            "label_url": f"https://example.com/labels/{shipment_id}.{format.lower()}"
        })

    return {
        "success": True,
        "total": len(shipment_ids),
        "labels": labels,
        "combined_pdf_url": f"https://example.com/labels/batch_{uuid.uuid4()}.pdf"
    }


# ============================================================================
# Address Validation
# ============================================================================

@router.post("/validate-address")
async def validate_address(
    address: Address,
    db: Session = Depends(get_db)
):
    """Validate and standardize an address."""
    # In production: Call address validation API (USPS, SmartyStreets, etc.)

    # Mock validation
    is_valid = bool(address.street1 and address.city and address.state and address.postal_code)

    suggestions = []
    if len(address.postal_code) == 5:
        suggestions.append({
            "postal_code": f"{address.postal_code}-0000",
            "message": "Consider adding ZIP+4 for faster delivery"
        })

    return {
        "is_valid": is_valid,
        "is_residential": True,  # Would be determined by validation service
        "standardized_address": {
            "street1": address.street1.upper(),
            "street2": address.street2.upper() if address.street2 else None,
            "city": address.city.upper(),
            "state": address.state.upper(),
            "postal_code": address.postal_code,
            "country": address.country
        },
        "suggestions": suggestions,
        "delivery_point_barcode": None  # Would come from USPS validation
    }
