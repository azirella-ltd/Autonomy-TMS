"""
Shipment Tracking API Endpoints
Sprint 2: Material Visibility
Provides endpoints for shipment tracking and delivery risk management
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.services.shipment_tracking_service import ShipmentTrackingService
from app.models.sc_entities import Shipment
from app.models.user import User
from app.api.deps import get_current_user
from app.core.permissions import RequirePermission

router = APIRouter()


# Pydantic schemas

class ShipmentResponse(BaseModel):
    """Shipment response schema"""
    shipment_id: str
    order_id: str
    product_id: str
    quantity: float
    uom: Optional[str]
    from_site_id: str
    to_site_id: str
    carrier_name: Optional[str]
    tracking_number: Optional[str]
    status: str
    ship_date: Optional[str]
    expected_delivery_date: Optional[str]
    actual_delivery_date: Optional[str]
    current_location: Optional[str]
    last_tracking_update: Optional[str]
    delivery_risk_score: Optional[float]
    risk_level: Optional[str]
    risk_factors: Dict[str, Any] = {}
    tracking_events: List[Dict[str, Any]] = []
    recommended_actions: List[Dict[str, Any]] = []
    mitigation_status: Optional[str]

    class Config:
        from_attributes = True


class InTransitInventoryResponse(BaseModel):
    """In-transit inventory response schema"""
    shipment_id: str
    order_id: str
    product_id: str
    quantity: float
    uom: Optional[str]
    from_site_id: str
    to_site_id: str
    carrier_name: Optional[str]
    status: str
    expected_delivery_date: Optional[str]
    delivery_risk_score: Optional[float]
    risk_level: Optional[str]
    days_in_transit: Optional[int]

    class Config:
        from_attributes = True


class DeliveryRiskResponse(BaseModel):
    """Delivery risk assessment response"""
    shipment_id: str
    delivery_risk_score: float
    risk_level: str
    probability_on_time: float
    risk_factors: Dict[str, float]

    class Config:
        from_attributes = True


class MitigationActionResponse(BaseModel):
    """Mitigation action recommendation"""
    action: str
    description: str
    impact: str
    estimated_cost: str
    priority: str


class ShipmentStatusUpdate(BaseModel):
    """Request body for status update"""
    status: str = Field(..., pattern="^(planned|in_transit|delivered|delayed|exception|cancelled)$")
    current_location: Optional[str] = None
    event_type: Optional[str] = None
    event_description: Optional[str] = None


# API endpoints

@router.get("/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment_status(
    shipment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequirePermission("shipment_tracking.view"))
):
    """
    Get real-time shipment status with risk assessment

    Returns detailed shipment information including:
    - Current status and location
    - Delivery risk score and factors
    - Tracking event history
    - Recommended mitigation actions
    """
    service = ShipmentTrackingService(db)
    result = await service.track_shipment(shipment_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/in-transit", response_model=List[InTransitInventoryResponse])
async def get_in_transit_inventory(
    product_id: Optional[str] = Query(None, description="Filter by product ID"),
    site_id: Optional[str] = Query(None, description="Filter by destination site ID"),
    risk_level: Optional[str] = Query(None, pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$", description="Filter by risk level"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequirePermission("shipment_tracking.view"))
):
    """
    Get all in-transit inventory with optional filters

    Returns list of active shipments with:
    - Product and quantity information
    - Origin and destination sites
    - Delivery risk assessment
    - Days in transit
    """
    service = ShipmentTrackingService(db)
    result = await service.get_in_transit_inventory(product_id, site_id, risk_level)

    return result


@router.get("/{shipment_id}/risk", response_model=DeliveryRiskResponse)
async def get_delivery_risk(
    shipment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequirePermission("shipment_tracking.view"))
):
    """
    Calculate delivery risk for a specific shipment

    Analyzes:
    - Carrier historical performance
    - Transit time variance
    - Route congestion
    - Tracking update freshness

    Returns probability of on-time delivery and risk factors
    """
    service = ShipmentTrackingService(db)
    result = await service.calculate_delivery_risk(shipment_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/{shipment_id}/mitigation", response_model=List[MitigationActionResponse])
async def get_mitigation_recommendations(
    shipment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequirePermission("shipment_tracking.view"))
):
    """
    Get recommended mitigation actions for at-risk shipments

    Returns prioritized list of actions:
    - Expedite shipping
    - Reroute to alternate carrier
    - Increase safety stock at destination
    - Customer notifications
    - Split shipment across carriers

    Each action includes impact assessment and cost estimate
    """
    service = ShipmentTrackingService(db)
    result = await service.recommend_mitigation(shipment_id)

    return result


@router.put("/{shipment_id}/status", response_model=ShipmentResponse)
async def update_shipment_status(
    shipment_id: str,
    status_update: ShipmentStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequirePermission("shipment_tracking.manage"))
):
    """
    Update shipment status and add tracking event

    Updates:
    - Shipment status (planned, in_transit, delivered, delayed, exception)
    - Current location
    - Tracking event history
    - Actual delivery date (if status = delivered)

    Requires manage_shipments capability
    """
    service = ShipmentTrackingService(db)

    tracking_event = None
    if status_update.event_type:
        tracking_event = {
            "event_type": status_update.event_type,
            "description": status_update.event_description,
            "location": status_update.current_location,
        }

    result = await service.update_shipment_status(
        shipment_id,
        status_update.status,
        status_update.current_location,
        tracking_event,
    )

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/summary", response_model=Dict[str, Any])
async def get_shipment_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequirePermission("shipment_tracking.view"))
):
    """
    Get summary statistics for all shipments

    Returns:
    - Total shipments by status
    - At-risk shipment count by risk level
    - Average delivery risk score
    - On-time delivery rate (last 30 days)
    """
    service = ShipmentTrackingService(db)

    # Get all shipments
    result = await db.execute(select(Shipment))
    all_shipments = result.scalars().all()

    # Count by status
    status_counts = {}
    for shipment in all_shipments:
        status = shipment.status
        status_counts[status] = status_counts.get(status, 0) + 1

    # Count at-risk shipments
    risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    total_risk_score = 0
    risk_count = 0

    in_transit = [s for s in all_shipments if s.status in ["in_transit", "delayed"]]
    for shipment in in_transit:
        if shipment.risk_level:
            risk_counts[shipment.risk_level] += 1
        if shipment.delivery_risk_score is not None:
            total_risk_score += shipment.delivery_risk_score
            risk_count += 1

    avg_risk_score = total_risk_score / risk_count if risk_count > 0 else 0

    # Calculate on-time delivery rate (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_delivered = [
        s for s in all_shipments
        if s.status == "delivered"
        and s.actual_delivery_date
        and s.actual_delivery_date >= thirty_days_ago
    ]

    on_time_count = sum(
        1 for s in recent_delivered
        if s.actual_delivery_date <= s.expected_delivery_date
    )
    total_delivered = len(recent_delivered)
    on_time_rate = (on_time_count / total_delivered * 100) if total_delivered > 0 else 0

    return {
        "total_shipments": len(all_shipments),
        "status_counts": status_counts,
        "at_risk_shipments": risk_counts,
        "average_risk_score": round(avg_risk_score, 2),
        "on_time_delivery_rate": round(on_time_rate, 2),
        "total_delivered_last_30_days": total_delivered,
    }
