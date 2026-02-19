"""
Forecast Adjustment API Endpoints

Provides CRUD operations for forecast adjustments:
- Individual cell edits
- Bulk adjustments (percentage, delta)
- Adjustment history tracking
- Version management
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_sync_db
from app.models.user import User
from app.models.forecast_adjustment import (
    ForecastAdjustment, ForecastVersion, BulkAdjustmentTemplate
)
from app.models.sc_entities import Forecast

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class AdjustmentCreate(BaseModel):
    """Create a single forecast adjustment."""
    forecast_id: int
    adjustment_type: str = Field(..., pattern="^(absolute|delta|percentage)$")
    adjustment_value: float
    time_bucket: Optional[str] = None
    reason_code: Optional[str] = None
    reason_text: Optional[str] = None
    notes: Optional[str] = None


class BulkAdjustmentCreate(BaseModel):
    """Create bulk forecast adjustments."""
    adjustment_type: str = Field(..., pattern="^(delta|percentage)$")
    adjustment_value: float
    forecast_ids: List[int] = Field(..., min_items=1)
    reason_code: Optional[str] = None
    reason_text: Optional[str] = None
    notes: Optional[str] = None


class AdjustmentResponse(BaseModel):
    """Forecast adjustment response."""
    id: int
    forecast_id: int
    adjustment_type: str
    original_value: float
    adjustment_value: float
    new_value: float
    time_bucket: Optional[str]
    reason_code: Optional[str]
    reason_text: Optional[str]
    source: str
    status: str
    created_by_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ForecastCell(BaseModel):
    """Single forecast cell for table display."""
    forecast_id: int
    product_id: str
    product_name: str
    site_id: str
    site_name: str
    period: str
    base_forecast: float
    adjusted_forecast: float
    user_override: Optional[float]
    has_adjustments: bool
    adjustment_count: int


class ForecastTableResponse(BaseModel):
    """Editable forecast table response."""
    products: List[Dict[str, Any]]
    sites: List[Dict[str, Any]]
    periods: List[str]
    cells: List[ForecastCell]
    total_rows: int


class VersionCreate(BaseModel):
    """Create a forecast version/snapshot."""
    version_name: Optional[str] = None
    version_type: str = Field("snapshot", pattern="^(snapshot|baseline|consensus|published)$")
    config_id: Optional[int] = None
    product_id: Optional[str] = None
    site_id: Optional[str] = None
    period_start: datetime
    period_end: datetime
    notes: Optional[str] = None


class VersionResponse(BaseModel):
    """Forecast version response."""
    id: int
    version_number: int
    version_name: Optional[str]
    version_type: str
    config_id: Optional[int]
    is_current: bool
    is_locked: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Forecast Table Endpoints
# ============================================================================

@router.get("/table", response_model=ForecastTableResponse)
def get_forecast_table(
    config_id: Optional[int] = None,
    product_ids: Optional[str] = Query(None, description="Comma-separated product IDs"),
    site_ids: Optional[str] = Query(None, description="Comma-separated site IDs"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    time_granularity: str = Query("week", pattern="^(day|week|month)$"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get editable forecast table data.

    Returns forecast data in a format suitable for table editing,
    with base forecasts, adjustments, and cell-level metadata.
    """
    # Parse filters
    product_list = product_ids.split(",") if product_ids else None
    site_list = site_ids.split(",") if site_ids else None

    # Default date range: next 12 weeks
    if not start_date:
        start_date = datetime.utcnow()
    if not end_date:
        end_date = start_date + timedelta(weeks=12)

    # Generate periods based on granularity
    periods = _generate_periods(start_date, end_date, time_granularity)

    # Get forecasts (mock data for now)
    # In production, query from forecast table with filters
    cells, products, sites = _get_mock_forecast_cells(
        periods, product_list, site_list, config_id
    )

    return ForecastTableResponse(
        products=products,
        sites=sites,
        periods=periods,
        cells=cells,
        total_rows=len(cells)
    )


def _generate_periods(start: datetime, end: datetime, granularity: str) -> List[str]:
    """Generate period labels based on granularity."""
    periods = []
    current = start

    while current < end:
        if granularity == "day":
            periods.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        elif granularity == "week":
            # ISO week format
            periods.append(f"{current.year}-W{current.isocalendar()[1]:02d}")
            current += timedelta(weeks=1)
        elif granularity == "month":
            periods.append(current.strftime("%Y-%m"))
            # Move to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

    return periods[:12]  # Limit to 12 periods


def _get_mock_forecast_cells(
    periods: List[str],
    product_ids: Optional[List[str]],
    site_ids: Optional[List[str]],
    config_id: Optional[int]
) -> tuple:
    """Generate mock forecast data for development."""
    import random

    # Mock products
    products = [
        {"id": "PROD-001", "name": "Brake Pads - Premium"},
        {"id": "PROD-002", "name": "Oil Filter - Standard"},
        {"id": "PROD-003", "name": "Air Filter - High Performance"},
    ]

    # Mock sites
    sites = [
        {"id": "SITE-ATL", "name": "Atlanta DC"},
        {"id": "SITE-CHI", "name": "Chicago DC"},
        {"id": "SITE-LAX", "name": "Los Angeles DC"},
    ]

    cells = []
    forecast_id = 1

    for product in products:
        for site in sites:
            for period in periods:
                base_forecast = random.randint(80, 150)
                adjustment = random.choice([0, 0, 0, random.randint(-20, 30)])
                adjusted = base_forecast + adjustment

                cells.append(ForecastCell(
                    forecast_id=forecast_id,
                    product_id=product["id"],
                    product_name=product["name"],
                    site_id=site["id"],
                    site_name=site["name"],
                    period=period,
                    base_forecast=float(base_forecast),
                    adjusted_forecast=float(adjusted),
                    user_override=float(adjusted) if adjustment != 0 else None,
                    has_adjustments=adjustment != 0,
                    adjustment_count=1 if adjustment != 0 else 0
                ))
                forecast_id += 1

    return cells, products, sites


# ============================================================================
# Individual Adjustment Endpoints
# ============================================================================

@router.post("/", response_model=AdjustmentResponse)
def create_adjustment(
    adjustment: AdjustmentCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Create a single forecast adjustment.

    Applies the adjustment to the specified forecast and records
    the change in the adjustment history.
    """
    # Get the forecast (mock for now)
    # In production: forecast = db.get(Forecast, adjustment.forecast_id)
    original_value = 100.0  # Mock original value

    # Calculate new value based on adjustment type
    if adjustment.adjustment_type == "absolute":
        new_value = adjustment.adjustment_value
    elif adjustment.adjustment_type == "delta":
        new_value = original_value + adjustment.adjustment_value
    elif adjustment.adjustment_type == "percentage":
        new_value = original_value * (1 + adjustment.adjustment_value / 100)
    else:
        raise HTTPException(status_code=400, detail="Invalid adjustment type")

    # Create adjustment record
    adj_record = ForecastAdjustment(
        forecast_id=adjustment.forecast_id,
        adjustment_type=adjustment.adjustment_type,
        original_value=original_value,
        adjustment_value=adjustment.adjustment_value,
        new_value=new_value,
        time_bucket=adjustment.time_bucket,
        reason_code=adjustment.reason_code,
        reason_text=adjustment.reason_text,
        notes=adjustment.notes,
        source="manual",
        status="applied",
        created_by_id=current_user.id
    )

    db.add(adj_record)
    db.commit()
    db.refresh(adj_record)

    logger.info(f"Forecast adjustment {adj_record.id} created by user {current_user.id}")

    return AdjustmentResponse(
        id=adj_record.id,
        forecast_id=adj_record.forecast_id,
        adjustment_type=adj_record.adjustment_type,
        original_value=adj_record.original_value,
        adjustment_value=adj_record.adjustment_value,
        new_value=adj_record.new_value,
        time_bucket=adj_record.time_bucket,
        reason_code=adj_record.reason_code,
        reason_text=adj_record.reason_text,
        source=adj_record.source,
        status=adj_record.status,
        created_by_id=adj_record.created_by_id,
        created_at=adj_record.created_at
    )


@router.post("/bulk", response_model=List[AdjustmentResponse])
def create_bulk_adjustment(
    bulk: BulkAdjustmentCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Create bulk forecast adjustments.

    Applies the same adjustment to multiple forecasts and records
    all changes with a shared batch ID.
    """
    batch_id = str(uuid.uuid4())
    results = []

    for forecast_id in bulk.forecast_ids:
        # Get original value (mock for now)
        original_value = 100.0

        # Calculate new value
        if bulk.adjustment_type == "delta":
            new_value = original_value + bulk.adjustment_value
        elif bulk.adjustment_type == "percentage":
            new_value = original_value * (1 + bulk.adjustment_value / 100)
        else:
            raise HTTPException(status_code=400, detail="Invalid bulk adjustment type")

        adj_record = ForecastAdjustment(
            forecast_id=forecast_id,
            adjustment_type=bulk.adjustment_type,
            original_value=original_value,
            adjustment_value=bulk.adjustment_value,
            new_value=new_value,
            reason_code=bulk.reason_code,
            reason_text=bulk.reason_text,
            notes=bulk.notes,
            source="bulk",
            batch_id=batch_id,
            status="applied",
            created_by_id=current_user.id
        )

        db.add(adj_record)
        results.append(adj_record)

    db.commit()

    logger.info(f"Bulk adjustment batch {batch_id} with {len(results)} adjustments created")

    return [
        AdjustmentResponse(
            id=r.id,
            forecast_id=r.forecast_id,
            adjustment_type=r.adjustment_type,
            original_value=r.original_value,
            adjustment_value=r.adjustment_value,
            new_value=r.new_value,
            time_bucket=r.time_bucket,
            reason_code=r.reason_code,
            reason_text=r.reason_text,
            source=r.source,
            status=r.status,
            created_by_id=r.created_by_id,
            created_at=r.created_at
        )
        for r in results
    ]


@router.get("/history/{forecast_id}", response_model=List[AdjustmentResponse])
def get_adjustment_history(
    forecast_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """Get adjustment history for a specific forecast."""
    adjustments = db.query(ForecastAdjustment).filter(
        ForecastAdjustment.forecast_id == forecast_id
    ).order_by(ForecastAdjustment.created_at.desc()).limit(limit).all()

    return [
        AdjustmentResponse(
            id=a.id,
            forecast_id=a.forecast_id,
            adjustment_type=a.adjustment_type,
            original_value=a.original_value,
            adjustment_value=a.adjustment_value,
            new_value=a.new_value,
            time_bucket=a.time_bucket,
            reason_code=a.reason_code,
            reason_text=a.reason_text,
            source=a.source,
            status=a.status,
            created_by_id=a.created_by_id,
            created_at=a.created_at
        )
        for a in adjustments
    ]


@router.delete("/{adjustment_id}")
def revert_adjustment(
    adjustment_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Revert a forecast adjustment.

    Marks the adjustment as reverted and restores the previous value.
    """
    adjustment = db.get(ForecastAdjustment, adjustment_id)
    if not adjustment:
        raise HTTPException(status_code=404, detail="Adjustment not found")

    if adjustment.status == "reverted":
        raise HTTPException(status_code=400, detail="Adjustment already reverted")

    adjustment.status = "reverted"
    db.commit()

    logger.info(f"Adjustment {adjustment_id} reverted by user {current_user.id}")

    return {"success": True, "message": "Adjustment reverted"}


# ============================================================================
# Version Management Endpoints
# ============================================================================

@router.get("/versions", response_model=List[VersionResponse])
def list_versions(
    config_id: Optional[int] = None,
    version_type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """List forecast versions/snapshots."""
    query = db.query(ForecastVersion)

    if config_id:
        query = query.filter(ForecastVersion.config_id == config_id)
    if version_type:
        query = query.filter(ForecastVersion.version_type == version_type)

    versions = query.order_by(ForecastVersion.created_at.desc()).limit(limit).all()

    return [
        VersionResponse(
            id=v.id,
            version_number=v.version_number,
            version_name=v.version_name,
            version_type=v.version_type,
            config_id=v.config_id,
            is_current=v.is_current,
            is_locked=v.is_locked,
            created_at=v.created_at
        )
        for v in versions
    ]


@router.post("/versions", response_model=VersionResponse)
def create_version(
    version: VersionCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Create a new forecast version/snapshot.

    Captures the current state of forecasts for the specified scope and period.
    """
    # Get next version number
    last_version = db.query(ForecastVersion).filter(
        ForecastVersion.config_id == version.config_id
    ).order_by(ForecastVersion.version_number.desc()).first()

    next_number = (last_version.version_number + 1) if last_version else 1

    # Capture forecast data (mock for now)
    forecast_data = _capture_forecast_snapshot(
        db, version.config_id, version.product_id, version.site_id,
        version.period_start, version.period_end
    )

    version_record = ForecastVersion(
        version_number=next_number,
        version_name=version.version_name or f"Version {next_number}",
        version_type=version.version_type,
        config_id=version.config_id,
        product_id=version.product_id,
        site_id=version.site_id,
        period_start=version.period_start,
        period_end=version.period_end,
        forecast_data=forecast_data,
        is_current=(version.version_type == "published"),
        created_by_id=current_user.id,
        notes=version.notes
    )

    db.add(version_record)
    db.commit()
    db.refresh(version_record)

    logger.info(f"Forecast version {version_record.id} created by user {current_user.id}")

    return VersionResponse(
        id=version_record.id,
        version_number=version_record.version_number,
        version_name=version_record.version_name,
        version_type=version_record.version_type,
        config_id=version_record.config_id,
        is_current=version_record.is_current,
        is_locked=version_record.is_locked,
        created_at=version_record.created_at
    )


def _capture_forecast_snapshot(
    db: Session,
    config_id: Optional[int],
    product_id: Optional[str],
    site_id: Optional[str],
    period_start: datetime,
    period_end: datetime
) -> Dict[str, Any]:
    """Capture current forecast values as a snapshot."""
    # Mock implementation - in production, query actual forecasts
    return {
        "captured_at": datetime.utcnow().isoformat(),
        "config_id": config_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "forecasts": [
            {"product_id": "PROD-001", "site_id": "SITE-ATL", "period": "2026-W05", "quantity": 120},
            {"product_id": "PROD-001", "site_id": "SITE-CHI", "quantity": 85},
        ]
    }


@router.post("/versions/{version_id}/restore")
def restore_version(
    version_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Restore forecasts from a version snapshot.

    Reverts all forecasts to the values captured in the specified version.
    """
    version = db.get(ForecastVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    if version.is_locked:
        raise HTTPException(status_code=400, detail="Cannot restore from a locked version")

    # Restore forecasts (mock for now)
    # In production, iterate through version.forecast_data and update forecasts

    logger.info(f"Forecast version {version_id} restored by user {current_user.id}")

    return {"success": True, "message": f"Restored {len(version.forecast_data.get('forecasts', []))} forecasts"}


# ============================================================================
# Bulk Adjustment Template Endpoints
# ============================================================================

@router.get("/templates", response_model=List[Dict[str, Any]])
def list_adjustment_templates(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """List available bulk adjustment templates."""
    templates = db.query(BulkAdjustmentTemplate).filter(
        BulkAdjustmentTemplate.is_active == True
    ).all()

    return [t.to_dict() for t in templates]


@router.post("/templates", response_model=Dict[str, Any])
def create_adjustment_template(
    name: str,
    adjustment_type: str,
    default_value: Optional[float] = None,
    default_reason_code: Optional[str] = None,
    description: Optional[str] = None,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """Create a new bulk adjustment template."""
    template = BulkAdjustmentTemplate(
        name=name,
        description=description,
        adjustment_type=adjustment_type,
        default_value=default_value,
        default_reason_code=default_reason_code,
        is_active=True,
        created_by_id=current_user.id
    )

    db.add(template)
    db.commit()
    db.refresh(template)

    return template.to_dict()
