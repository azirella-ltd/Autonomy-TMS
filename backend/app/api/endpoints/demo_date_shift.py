"""
Demo Date Shift API — Manual trigger for shifting demo data dates forward.

POST /api/v1/demo/shift-dates/{config_id}  — Trigger a date shift for a specific config
GET  /api/v1/demo/shift-status/{config_id} — Check shift status for a config
GET  /api/v1/demo/shift-status              — List all tracked configs
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import sync_engine
from app.core.security import get_current_active_user

router = APIRouter()

SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


def _get_sync_db():
    db = SyncSessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/shift-dates/{config_id}")
def shift_demo_dates(
    config_id: int,
    db: Session = Depends(_get_sync_db),
    current_user=Depends(get_current_active_user),
):
    """
    Manually trigger a demo date shift for the given config_id.

    The shift is calculated as the number of whole days since the last shift.
    Only shifts if gap >= 1 day. Requires an existing demo_date_shift_log entry
    for the tenant/config pair (creates one on first call with no shift).

    Returns shift summary including days shifted and rows affected per table.
    """
    from app.services.demo_date_shift_service import DemoDateShiftService
    from sqlalchemy import text

    # Resolve tenant_id from config
    row = db.execute(
        text(
            "SELECT dsl.tenant_id FROM demo_date_shift_log dsl "
            "WHERE dsl.config_id = :cid LIMIT 1"
        ),
        {"cid": config_id},
    ).fetchone()

    if row is None:
        # No tracking entry — try to resolve tenant from the user
        tenant_id = getattr(current_user, "tenant_id", None)
        if not tenant_id:
            raise HTTPException(
                status_code=404,
                detail=f"No demo_date_shift_log entry for config_id={config_id}. "
                       f"Create one first or ensure the migration has been applied.",
            )
    else:
        tenant_id = row[0]

    service = DemoDateShiftService(db)
    result = service.shift_demo_dates(tenant_id=tenant_id, config_id=config_id)
    return result


@router.get("/shift-status/{config_id}")
def get_shift_status(
    config_id: int,
    db: Session = Depends(_get_sync_db),
    current_user=Depends(get_current_active_user),
):
    """Get the current date shift status for a specific config."""
    from app.services.demo_date_shift_service import DemoDateShiftService
    from sqlalchemy import text

    # Resolve tenant_id from the log
    row = db.execute(
        text("SELECT tenant_id FROM demo_date_shift_log WHERE config_id = :cid LIMIT 1"),
        {"cid": config_id},
    ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No demo_date_shift_log entry for config_id={config_id}",
        )

    service = DemoDateShiftService(db)
    status = service.get_shift_status(tenant_id=row[0], config_id=config_id)
    return status


@router.get("/shift-status")
def list_shift_status(
    db: Session = Depends(_get_sync_db),
    current_user=Depends(get_current_active_user),
):
    """List all tracked tenant/config pairs and their shift status."""
    from app.services.demo_date_shift_service import DemoDateShiftService

    service = DemoDateShiftService(db)
    return service.get_all_tracked_configs()
