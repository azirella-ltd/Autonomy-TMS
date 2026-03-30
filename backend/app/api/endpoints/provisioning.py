"""Provisioning API endpoints — Powell Cascade warm-start stepper.

Provides a 10-step provisioning pipeline with dependency tracking for any
supply chain config. Each step can be run individually or all at once.
"""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
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
    scope: Optional[str] = Query(
        None,
        description=(
            "Provisioning scope: 'PARAMETER_ONLY' for policy/parameter changes "
            "(reuses existing TRM/GNN models, only re-runs cfa_optimization, "
            "decision_seed, conformal, briefing). 'FULL' or omit for structural "
            "changes (new sites, lanes, products, BOMs) — runs all 14 steps."
        ),
    ),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Archive the current config version and re-run provisioning steps.

    Creates a read-only archived snapshot of the current config (visible in the
    SC config list with its original creation date), then resets provisioning
    step statuses and runs the pipeline.

    Use scope=PARAMETER_ONLY for policy/parameter changes (safety stock policy,
    service level targets, CFA parameters). These reuse existing TRM weights,
    GNN models, and simulation data.

    Use scope=FULL (default) for structural changes (new sites, lanes, products,
    BOMs) which require full retraining.

    Returns immediately — the frontend polls /status/{config_id} for progress.
    """
    import asyncio
    from app.db.session import async_session_factory as AsyncSessionLocal

    effective_scope = scope if scope in ("PARAMETER_ONLY", "FULL") else "FULL"

    # Mark as in_progress immediately so the UI reflects it
    service = ProvisioningService(db)
    status = await service.get_or_create_status(config_id)
    status.overall_status = "in_progress"
    status.provisioning_scope = effective_scope
    await db.commit()

    async def _reprovision_background(cid: int, sc: str):
        async with AsyncSessionLocal() as bg_db:
            bg_service = ProvisioningService(bg_db)
            try:
                await bg_service.reprovision(cid, scope=sc)
            except Exception:
                logger.exception("Background reprovision failed for config %d", cid)

    asyncio.create_task(_reprovision_background(config_id, effective_scope))
    return {
        "status": "started",
        "config_id": config_id,
        "scope": effective_scope,
        "note": (
            "Parameter-only reprovisioning — reusing existing models"
            if effective_scope == "PARAMETER_ONLY"
            else "Full reprovisioning — previous version archived"
        ),
    }


@router.get("/audit/{config_id}")
async def get_extraction_audit(
    config_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get the extraction audit report for a config.

    Shows per-table extraction status: which ERP tables had data,
    which were empty, which entities were derived from alternative sources,
    and which were skipped. Visible to any authenticated user with access
    to the config's tenant.
    """
    from app.services.extraction_audit_service import get_extraction_audit as _get_audit

    audit = await _get_audit(db, config_id)
    if not audit:
        raise HTTPException(
            status_code=404,
            detail=f"No extraction audit found for config {config_id}",
        )
    return audit


@router.delete("/config/{config_id}")
async def delete_config(
    config_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Delete an archived/inactive config and all its dependent data + checkpoints.

    Active configs cannot be deleted — archive or deactivate first.
    Removes: all DB records (sites, products, BOMs, lanes, decisions, etc.)
    and checkpoint files on disk (TRM weights, GNN models).
    """
    service = ProvisioningService(db)
    result = await service.delete_config(config_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/cleanup-checkpoints")
async def cleanup_orphaned_checkpoints(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.require_tenant_admin),
):
    """Find and remove checkpoint directories for configs that no longer exist.

    Safe to run anytime — only removes directories whose config_id
    has no matching row in supply_chain_configs.
    """
    service = ProvisioningService(db)
    return await service.cleanup_orphaned_checkpoints()


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
