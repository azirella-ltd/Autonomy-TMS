"""Provisioning API endpoints — Powell Cascade warm-start stepper.

Provides a 10-step provisioning pipeline with dependency tracking for any
supply chain config. Each step can be run individually or all at once.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import get_async_db
from app.models.user import User
from app.services.provisioning_service import ProvisioningService

router = APIRouter(prefix="/provisioning", tags=["Provisioning"])
logger = logging.getLogger(__name__)


@router.get("/status/{config_id}")
async def get_provisioning_status(
    config_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get provisioning status for a config (stepper state)."""
    service = ProvisioningService(db)
    status = await service.get_or_create_status(config_id)
    return status.to_dict()


@router.post("/run/{config_id}/{step_key}")
async def run_provisioning_step(
    config_id: int,
    step_key: str,
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Run a single provisioning step."""
    from app.models.user_directive import ConfigProvisioningStatus

    if step_key not in ConfigProvisioningStatus.STEPS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown step: {step_key}. Valid: {ConfigProvisioningStatus.STEPS}",
        )

    service = ProvisioningService(db)
    result = await service.run_step(config_id, step_key)

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.post("/run-all/{config_id}")
async def run_all_provisioning(
    config_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Run all provisioning steps in dependency order.

    Steps that are already completed are skipped. Steps with unmet
    dependencies are skipped with an error note. This is idempotent
    and safe to call multiple times.
    """
    service = ProvisioningService(db)
    return await service.run_all(config_id)


@router.post("/reset/{config_id}/{step_key}")
async def reset_provisioning_step(
    config_id: int,
    step_key: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Reset a single step back to pending (for re-running)."""
    from app.models.user_directive import ConfigProvisioningStatus

    if step_key not in ConfigProvisioningStatus.STEPS:
        raise HTTPException(status_code=400, detail=f"Unknown step: {step_key}")

    service = ProvisioningService(db)
    status = await service.get_or_create_status(config_id)
    setattr(status, f"{step_key}_status", "pending")
    setattr(status, f"{step_key}_at", None)
    setattr(status, f"{step_key}_error", None)
    status.overall_status = "in_progress"
    await db.commit()

    return {"status": "reset", "step": step_key, "config_id": config_id}
