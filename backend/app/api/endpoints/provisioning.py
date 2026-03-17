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
    from app.models.user_directive import ConfigProvisioningStatus

    service = ProvisioningService(db)
    status = await service.get_or_create_status(config_id)

    # Reconcile overall_status if individual steps are all done but overall
    # is stale (race condition between background steps and run_all loop)
    all_done = all(
        getattr(status, f"{s}_status") == "completed"
        for s in ConfigProvisioningStatus.STEPS
    )
    if all_done and status.overall_status != "completed":
        status.overall_status = "completed"
        await db.commit()

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
    """Run all provisioning steps in dependency order (fire-and-forget).

    Steps that are already completed are skipped. Steps with unmet
    dependencies are skipped with an error note. This is idempotent
    and safe to call multiple times.

    Returns immediately — the frontend polls /status/{config_id} for progress.
    """
    import asyncio
    from app.db.session import async_session_factory as AsyncSessionLocal

    # Mark as in_progress immediately so the UI reflects it
    service = ProvisioningService(db)
    status = await service.get_or_create_status(config_id)
    status.overall_status = "in_progress"
    await db.commit()

    async def _run_all_background(cid: int):
        async with AsyncSessionLocal() as bg_db:
            bg_service = ProvisioningService(bg_db)
            try:
                await bg_service.run_all(cid)
            except Exception:
                logger.exception("Background run-all failed for config %d", cid)

    asyncio.create_task(_run_all_background(config_id))
    return {"status": "started", "config_id": config_id}


@router.post("/reprovision/{config_id}")
async def reprovision_config(
    config_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Archive the current config version and re-run all provisioning steps.

    Creates a read-only archived snapshot of the current config (visible in the
    SC config list with its original creation date), then resets all provisioning
    step statuses and runs the full pipeline again.

    Returns immediately — the frontend polls /status/{config_id} for progress.
    """
    import asyncio
    from app.db.session import async_session_factory as AsyncSessionLocal

    # Mark as in_progress immediately so the UI reflects it
    service = ProvisioningService(db)
    status = await service.get_or_create_status(config_id)
    status.overall_status = "in_progress"
    await db.commit()

    async def _reprovision_background(cid: int):
        async with AsyncSessionLocal() as bg_db:
            bg_service = ProvisioningService(bg_db)
            try:
                await bg_service.reprovision(cid)
            except Exception:
                logger.exception("Background reprovision failed for config %d", cid)

    asyncio.create_task(_reprovision_background(config_id))
    return {"status": "started", "config_id": config_id, "note": "Previous version archived"}


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


@router.post("/reset-all/{config_id}")
async def reset_all_provisioning(
    config_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Reset all provisioning steps back to pending."""
    from app.models.user_directive import ConfigProvisioningStatus

    service = ProvisioningService(db)
    status = await service.get_or_create_status(config_id)
    for step_key in ConfigProvisioningStatus.STEPS:
        setattr(status, f"{step_key}_status", "pending")
        setattr(status, f"{step_key}_at", None)
        setattr(status, f"{step_key}_error", None)
    status.overall_status = "pending"
    await db.commit()

    return {"status": "reset_all", "config_id": config_id}
