"""Warm Start API endpoints.

Generates consistent historical demand data for any SC config using
Monte Carlo sampling from existing Forecast P10/P50/P90 distributions.
"""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_sync_db
from app.models.user import User
from app.services.warm_start_generator import WarmStartGenerator

router = APIRouter(prefix="/warm-start", tags=["Warm Start"])
logger = logging.getLogger(__name__)


def _run_warm_start(config_id: int, weeks: int) -> None:
    """Background task with its own DB session."""
    from app.db.session import sync_session_factory
    db = sync_session_factory()
    try:
        result = WarmStartGenerator(db).generate_for_config(config_id, weeks)
        db.commit()
        logger.info("WarmStart background task complete: %s", result)
    except Exception:
        db.rollback()
        logger.exception("WarmStart background task failed for config_id=%d", config_id)
    finally:
        db.close()


@router.post("/provision/{config_id}")
def provision_warm_start(
    config_id: int,
    weeks: int = 52,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Generate historical demand data for a SC config.

    Idempotent — safe to call multiple times. Runs asynchronously in the
    background so the response is immediate.
    """
    background_tasks.add_task(_run_warm_start, config_id, weeks)
    return {"status": "queued", "config_id": config_id, "weeks": weeks}


@router.post("/provision/{config_id}/sync")
def provision_warm_start_sync(
    config_id: int,
    weeks: int = 52,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Generate historical demand data synchronously (for scripts/testing)."""
    try:
        generator = WarmStartGenerator(db)
        result = generator.generate_for_config(config_id, weeks)
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status/{config_id}")
def warm_start_status(
    config_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Return counts of warm start data for this config."""
    return WarmStartGenerator(db).get_status(config_id)
