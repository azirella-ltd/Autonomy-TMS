"""
Risk Analysis API Endpoints
Sprint 1: Enhanced Insights & Risk Analysis
Provides endpoints for risk detection, watchlists, and predictions
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.session import get_sync_db
from app.services.risk_detection_service import RiskDetectionService
from app.models.risk import RiskAlert, Watchlist, RiskPrediction
from app.models.user import User
from app.api.deps import get_current_active_user

router = APIRouter()


# Pydantic schemas

class RiskAlertResponse(BaseModel):
    """Risk alert response schema"""
    id: int
    alert_id: str
    type: str
    severity: str
    product_id: str
    site_id: str
    vendor_id: Optional[str] = None
    probability: Optional[float] = None
    days_until_stockout: Optional[int] = None
    days_of_supply: Optional[float] = None
    excess_quantity: Optional[float] = None
    message: str
    recommended_action: str
    factors: Optional[Dict] = None
    status: str
    created_at: datetime
    acknowledged_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WatchlistCreate(BaseModel):
    """Create watchlist request"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    config_id: Optional[int] = None
    product_filter: Optional[List[str]] = None
    site_filter: Optional[List[str]] = None
    stockout_threshold: Optional[float] = Field(None, ge=0, le=100)
    overstock_threshold_days: Optional[float] = Field(None, gt=0)
    leadtime_variance_threshold: Optional[float] = Field(None, gt=0)
    enable_notifications: bool = True
    notification_frequency: str = Field(default="DAILY", pattern="^(REALTIME|HOURLY|DAILY|WEEKLY)$")
    notification_channels: Optional[List[str]] = None
    notification_recipients: Optional[List[int]] = None


class WatchlistUpdate(BaseModel):
    """Update watchlist request"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    product_filter: Optional[List[str]] = None
    site_filter: Optional[List[str]] = None
    stockout_threshold: Optional[float] = Field(None, ge=0, le=100)
    overstock_threshold_days: Optional[float] = Field(None, gt=0)
    leadtime_variance_threshold: Optional[float] = Field(None, gt=0)
    enable_notifications: Optional[bool] = None
    notification_frequency: Optional[str] = Field(None, pattern="^(REALTIME|HOURLY|DAILY|WEEKLY)$")
    notification_channels: Optional[List[str]] = None
    notification_recipients: Optional[List[int]] = None
    is_active: Optional[bool] = None


class WatchlistResponse(BaseModel):
    """Watchlist response schema"""
    id: int
    name: str
    description: Optional[str]
    created_by: int
    group_id: Optional[int]
    config_id: Optional[int]
    product_filter: Optional[List[str]]
    site_filter: Optional[List[str]]
    stockout_threshold: Optional[float]
    overstock_threshold_days: Optional[float]
    leadtime_variance_threshold: Optional[float]
    enable_notifications: bool
    notification_frequency: str
    notification_channels: Optional[List[str]]
    is_active: bool
    created_at: datetime
    last_checked_at: Optional[datetime]

    class Config:
        from_attributes = True


class RiskAnalysisRequest(BaseModel):
    """Request to analyze specific product/site"""
    product_id: str
    site_id: str
    horizon_days: int = Field(default=30, ge=1, le=365)


class VendorLeadTimeRequest(BaseModel):
    """Request for vendor lead time prediction"""
    vendor_id: str
    product_id: str
    site_id: str


class AlertAcknowledgeRequest(BaseModel):
    """Acknowledge alert request"""
    notes: Optional[str] = None


class AlertResolveRequest(BaseModel):
    """Resolve alert request"""
    resolution_notes: str = Field(..., min_length=1)


# Endpoints

@router.get("/alerts", response_model=List[RiskAlertResponse])
async def get_risk_alerts(
    severity: Optional[str] = Query(None, pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$"),
    alert_type: Optional[str] = Query(None, pattern="^(STOCKOUT|OVERSTOCK|VENDOR_LEADTIME)$"),
    status: Optional[str] = Query(None, pattern="^(ACTIVE|ACKNOWLEDGED|RESOLVED|DISMISSED)$"),
    config_id: Optional[int] = None,
    product_id: Optional[str] = None,
    site_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get risk alerts with optional filtering.

    Filters:
    - severity: LOW, MEDIUM, HIGH, CRITICAL
    - alert_type: STOCKOUT, OVERSTOCK, VENDOR_LEADTIME
    - status: ACTIVE, ACKNOWLEDGED, RESOLVED, DISMISSED
    - config_id: Filter by supply chain config
    - product_id: Filter by product
    - site_id: Filter by site
    """
    query = db.query(RiskAlert)

    # Apply filters
    if severity:
        query = query.filter(RiskAlert.severity == severity)
    if alert_type:
        query = query.filter(RiskAlert.type == alert_type)
    if status:
        query = query.filter(RiskAlert.status == status)
    if config_id:
        query = query.filter(RiskAlert.config_id == config_id)
    if product_id:
        query = query.filter(RiskAlert.product_id == product_id)
    if site_id:
        query = query.filter(RiskAlert.site_id == site_id)

    # Order by severity and creation time
    severity_order = {
        "CRITICAL": 0,
        "HIGH": 1,
        "MEDIUM": 2,
        "LOW": 3
    }

    alerts = query.limit(limit).all()

    # Sort by severity in Python (SQLAlchemy custom ordering is complex)
    alerts.sort(key=lambda x: (severity_order.get(x.severity, 4), -x.created_at.timestamp()))

    return alerts


@router.get("/alerts/{alert_id}", response_model=RiskAlertResponse)
async def get_alert_detail(
    alert_id: str,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get detailed information about a specific risk alert."""
    alert = db.query(RiskAlert).filter(RiskAlert.alert_id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Risk alert not found")

    return alert


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    request: AlertAcknowledgeRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user)
):
    """Acknowledge a risk alert."""
    alert = db.query(RiskAlert).filter(RiskAlert.alert_id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Risk alert not found")

    if alert.status != "ACTIVE":
        raise HTTPException(status_code=400, detail="Only active alerts can be acknowledged")

    alert.status = "ACKNOWLEDGED"
    alert.acknowledged_by = current_user.id
    alert.acknowledged_at = datetime.utcnow()

    if request.notes:
        alert.resolution_notes = request.notes

    db.commit()
    db.refresh(alert)

    return {"message": "Alert acknowledged successfully", "alert": alert}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    request: AlertResolveRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user)
):
    """Resolve a risk alert with resolution notes."""
    alert = db.query(RiskAlert).filter(RiskAlert.alert_id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Risk alert not found")

    if alert.status == "RESOLVED":
        raise HTTPException(status_code=400, detail="Alert is already resolved")

    alert.status = "RESOLVED"
    alert.resolved_at = datetime.utcnow()
    alert.resolution_notes = request.resolution_notes

    if not alert.acknowledged_by:
        alert.acknowledged_by = current_user.id
        alert.acknowledged_at = datetime.utcnow()

    db.commit()
    db.refresh(alert)

    return {"message": "Alert resolved successfully", "alert": alert}


@router.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: str,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user)
):
    """Dismiss a risk alert (mark as false positive)."""
    alert = db.query(RiskAlert).filter(RiskAlert.alert_id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Risk alert not found")

    alert.status = "DISMISSED"
    alert.acknowledged_by = current_user.id
    alert.acknowledged_at = datetime.utcnow()

    db.commit()
    db.refresh(alert)

    return {"message": "Alert dismissed successfully"}


@router.post("/analyze", response_model=Dict[str, Any])
async def analyze_risk(
    request: RiskAnalysisRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Perform risk analysis for a specific product/site combination.

    Returns both stock-out and overstock risk assessments.
    """
    risk_service = RiskDetectionService(db)

    # Run both analyses
    stockout_risk = await risk_service.detect_stockout_risk(
        request.product_id,
        request.site_id,
        request.horizon_days
    )

    overstock_risk = await risk_service.detect_overstock_risk(
        request.product_id,
        request.site_id,
        threshold_days=90
    )

    return {
        "product_id": request.product_id,
        "site_id": request.site_id,
        "horizon_days": request.horizon_days,
        "stockout_risk": stockout_risk,
        "overstock_risk": overstock_risk,
        "analyzed_at": datetime.utcnow().isoformat()
    }


@router.post("/vendor-leadtime", response_model=Dict[str, Any])
async def predict_vendor_leadtime(
    request: VendorLeadTimeRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Predict vendor lead time variability.

    Returns P10/P50/P90 predictions and reliability score.
    """
    risk_service = RiskDetectionService(db)

    prediction = await risk_service.predict_vendor_leadtime(
        request.vendor_id,
        request.product_id,
        request.site_id
    )

    return {
        "vendor_id": request.vendor_id,
        "product_id": request.product_id,
        "site_id": request.site_id,
        "prediction": prediction,
        "predicted_at": datetime.utcnow().isoformat()
    }


@router.post("/generate-alerts")
async def generate_alerts(
    config_id: Optional[int] = None,
    severity_filter: Optional[str] = Query(None, pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Generate risk alerts for all monitored items.

    This endpoint runs the risk detection service across all inventory levels
    and creates/updates alert records in the database.
    """
    risk_service = RiskDetectionService(db)

    # Generate alerts
    alerts = await risk_service.generate_risk_alerts(
        config_id=config_id,
        severity_filter=severity_filter
    )

    # Persist alerts to database
    persisted_count = 0
    updated_count = 0

    for alert_data in alerts:
        existing_alert = db.query(RiskAlert).filter(
            RiskAlert.alert_id == alert_data["alert_id"]
        ).first()

        if existing_alert:
            # Update existing alert
            for key, value in alert_data.items():
                if key != "alert_id":
                    setattr(existing_alert, key, value)
            existing_alert.updated_at = datetime.utcnow()
            updated_count += 1
        else:
            # Create new alert
            new_alert = RiskAlert(**alert_data)
            db.add(new_alert)
            persisted_count += 1

    db.commit()

    return {
        "message": "Alert generation completed",
        "total_alerts": len(alerts),
        "new_alerts": persisted_count,
        "updated_alerts": updated_count
    }


# Watchlist endpoints

@router.post("/watchlists", response_model=WatchlistResponse)
async def create_watchlist(
    watchlist: WatchlistCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new watchlist."""
    new_watchlist = Watchlist(
        name=watchlist.name,
        description=watchlist.description,
        created_by=current_user.id,
        group_id=current_user.group_id,
        config_id=watchlist.config_id,
        product_filter=watchlist.product_filter,
        site_filter=watchlist.site_filter,
        stockout_threshold=watchlist.stockout_threshold,
        overstock_threshold_days=watchlist.overstock_threshold_days,
        leadtime_variance_threshold=watchlist.leadtime_variance_threshold,
        enable_notifications=watchlist.enable_notifications,
        notification_frequency=watchlist.notification_frequency,
        notification_channels=watchlist.notification_channels,
        notification_recipients=watchlist.notification_recipients
    )

    db.add(new_watchlist)
    db.commit()
    db.refresh(new_watchlist)

    return new_watchlist


@router.get("/watchlists", response_model=List[WatchlistResponse])
async def get_watchlists(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all watchlists for the current user's group."""
    query = db.query(Watchlist).filter(Watchlist.created_by == current_user.id)

    if is_active is not None:
        query = query.filter(Watchlist.is_active == is_active)

    watchlists = query.all()
    return watchlists


@router.get("/watchlists/{watchlist_id}", response_model=WatchlistResponse)
async def get_watchlist(
    watchlist_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific watchlist by ID."""
    watchlist = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()

    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    # Check ownership
    if watchlist.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this watchlist")

    return watchlist


@router.put("/watchlists/{watchlist_id}", response_model=WatchlistResponse)
async def update_watchlist(
    watchlist_id: int,
    updates: WatchlistUpdate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update an existing watchlist."""
    watchlist = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()

    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    # Check ownership
    if watchlist.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this watchlist")

    # Update fields
    update_data = updates.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(watchlist, field, value)

    watchlist.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(watchlist)

    return watchlist


@router.delete("/watchlists/{watchlist_id}")
async def delete_watchlist(
    watchlist_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a watchlist."""
    watchlist = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()

    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    # Check ownership
    if watchlist.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this watchlist")

    db.delete(watchlist)
    db.commit()

    return {"message": "Watchlist deleted successfully"}


# Prediction endpoints

@router.get("/predictions", response_model=List[Dict[str, Any]])
async def get_predictions(
    product_id: Optional[str] = None,
    site_id: Optional[str] = None,
    prediction_type: Optional[str] = Query(None, pattern="^(DEMAND|STOCKOUT|OVERSTOCK|LEADTIME)$"),
    model_name: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get historical risk predictions for model validation."""
    query = db.query(RiskPrediction)

    if product_id:
        query = query.filter(RiskPrediction.product_id == product_id)
    if site_id:
        query = query.filter(RiskPrediction.site_id == site_id)
    if prediction_type:
        query = query.filter(RiskPrediction.prediction_type == prediction_type)
    if model_name:
        query = query.filter(RiskPrediction.model_name == model_name)

    predictions = query.order_by(RiskPrediction.prediction_date.desc()).limit(limit).all()

    return [
        {
            "id": p.id,
            "model_name": p.model_name,
            "model_version": p.model_version,
            "product_id": p.product_id,
            "site_id": p.site_id,
            "prediction_type": p.prediction_type,
            "predicted_value": p.predicted_value,
            "confidence": p.confidence,
            "prediction_interval": [p.prediction_interval_lower, p.prediction_interval_upper],
            "actual_value": p.actual_value,
            "prediction_error": p.prediction_error,
            "target_date": p.target_date,
            "prediction_date": p.prediction_date
        }
        for p in predictions
    ]
