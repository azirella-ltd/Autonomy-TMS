"""
Deployment Pipeline API Endpoints

Manages demo system deployment pipelines:
- Start pipeline (7-step background process)
- Monitor progress
- Download generated CSVs
- Import Day 2 + trigger CDC
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.deployment_pipeline import DeploymentPipelineRun

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class PipelineCreateRequest(BaseModel):
    """Request to start a new deployment pipeline."""
    config_template: str = Field(
        default="Food Distribution",
        description="Name of the supply chain config template"
    )
    periods: int = Field(default=52, ge=4, le=104)
    monte_carlo_runs: int = Field(default=128, ge=1, le=1000)
    epochs: int = Field(default=50, ge=1, le=500)
    device: str = Field(default="cpu")
    seed: int = Field(default=42)
    demand_noise_cv: float = Field(default=0.15, ge=0, le=1.0)
    day2_profile: str = Field(default="mixed")


class PipelineResponse(BaseModel):
    """Pipeline status response."""
    id: int
    config_template: str
    config_id: Optional[int] = None
    status: str
    current_step: int
    total_steps: int
    step_statuses: Dict[str, Any] = {}
    parameters: Dict[str, Any] = {}
    results: Dict[str, Any] = {}
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    error_step: Optional[int] = None
    created_at: Optional[str] = None


class PipelineListResponse(BaseModel):
    """List of pipeline runs."""
    pipelines: List[PipelineResponse]
    total: int


# ============================================================================
# Helper
# ============================================================================

def _pipeline_to_response(p: DeploymentPipelineRun) -> PipelineResponse:
    return PipelineResponse(
        id=p.id,
        config_template=p.config_template,
        config_id=p.config_id,
        status=p.status,
        current_step=p.current_step,
        total_steps=p.total_steps,
        step_statuses=p.step_statuses or {},
        parameters=p.parameters or {},
        results=p.results or {},
        started_at=p.started_at.isoformat() if p.started_at else None,
        completed_at=p.completed_at.isoformat() if p.completed_at else None,
        error_message=p.error_message,
        error_step=p.error_step,
        created_at=p.created_at.isoformat() if p.created_at else None,
    )


# ============================================================================
# Background task runner
# ============================================================================

async def _run_pipeline_background(pipeline_id: int):
    """Run pipeline in background using a fresh DB session."""
    from app.db.session import async_session_factory
    from app.services.deployment_pipeline_service import DeploymentPipelineService

    async with async_session_factory() as db:
        try:
            svc = DeploymentPipelineService(db=db, pipeline_id=pipeline_id)
            await svc.run()
            await db.commit()
        except Exception as e:
            await db.rollback()
            # Update status to failed
            try:
                result = await db.execute(
                    select(DeploymentPipelineRun)
                    .where(DeploymentPipelineRun.id == pipeline_id)
                )
                pipeline = result.scalar_one_or_none()
                if pipeline:
                    pipeline.status = "failed"
                    pipeline.error_message = str(e)
                    await db.commit()
            except Exception:
                pass


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/pipelines", response_model=PipelineResponse)
async def create_pipeline(
    request: PipelineCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Start a new deployment pipeline.

    Creates and immediately starts a 7-step background pipeline.
    Poll GET /pipelines/{id} for progress.
    """
    pipeline = DeploymentPipelineRun(
        config_template=request.config_template,
        group_id=getattr(current_user, 'group_id', None),
        status="pending",
        current_step=0,
        total_steps=7,
        parameters={
            "periods": request.periods,
            "monte_carlo_runs": request.monte_carlo_runs,
            "epochs": request.epochs,
            "device": request.device,
            "seed": request.seed,
            "demand_noise_cv": request.demand_noise_cv,
            "day2_profile": request.day2_profile,
        },
        triggered_by=current_user.id,
    )
    db.add(pipeline)
    await db.flush()

    pipeline_id = pipeline.id

    # Start in background
    import asyncio
    asyncio.create_task(_run_pipeline_background(pipeline_id))

    return _pipeline_to_response(pipeline)


@router.get("/pipelines", response_model=PipelineListResponse)
async def list_pipelines(
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all deployment pipeline runs."""
    query = select(DeploymentPipelineRun).order_by(
        DeploymentPipelineRun.created_at.desc()
    )

    if status:
        query = query.where(DeploymentPipelineRun.status == status)

    # Count total
    from sqlalchemy import func
    count_query = select(func.count()).select_from(DeploymentPipelineRun)
    if status:
        count_query = count_query.where(DeploymentPipelineRun.status == status)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Fetch page
    result = await db.execute(query.offset(offset).limit(limit))
    pipelines = result.scalars().all()

    return PipelineListResponse(
        pipelines=[_pipeline_to_response(p) for p in pipelines],
        total=total,
    )


@router.get("/pipelines/{pipeline_id}", response_model=PipelineResponse)
async def get_pipeline(
    pipeline_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get pipeline status and progress."""
    result = await db.execute(
        select(DeploymentPipelineRun)
        .where(DeploymentPipelineRun.id == pipeline_id)
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    return _pipeline_to_response(pipeline)


@router.get("/pipelines/{pipeline_id}/steps/{step}")
async def get_pipeline_step(
    pipeline_id: int,
    step: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed status for a specific pipeline step."""
    result = await db.execute(
        select(DeploymentPipelineRun)
        .where(DeploymentPipelineRun.id == pipeline_id)
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    step_statuses = pipeline.step_statuses or {}
    step_info = step_statuses.get(str(step))

    if not step_info:
        return {
            "step": step,
            "status": "pending",
            "name": {
                1: "Seed Config", 2: "Deterministic Simulation",
                3: "Stochastic Monte Carlo", 4: "Convert Training Data",
                5: "Train Models", 6: "Generate Day 1 CSVs",
                7: "Generate Day 2 CSVs",
            }.get(step, f"Step {step}"),
        }

    return {"step": step, **step_info}


@router.post("/pipelines/{pipeline_id}/cancel")
async def cancel_pipeline(
    pipeline_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a running pipeline."""
    result = await db.execute(
        select(DeploymentPipelineRun)
        .where(DeploymentPipelineRun.id == pipeline_id)
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if pipeline.status not in ("pending", "running"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel pipeline in '{pipeline.status}' status"
        )

    pipeline.status = "cancelled"
    pipeline.error_message = "Cancelled by user"
    await db.flush()

    return {"status": "cancelled", "pipeline_id": pipeline_id}


@router.get("/csvs/{pipeline_id}")
async def list_csvs(
    pipeline_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List generated CSV ZIP files for a pipeline."""
    result = await db.execute(
        select(DeploymentPipelineRun)
        .where(DeploymentPipelineRun.id == pipeline_id)
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    results = pipeline.results or {}
    csvs = []

    # Check for Day 1 ZIP
    step6 = results.get("step_6", {})
    if step6.get("zip_path"):
        from pathlib import Path
        zip_path = Path(step6["zip_path"])
        csvs.append({
            "type": "day1",
            "filename": zip_path.name,
            "path": str(zip_path),
            "exists": zip_path.exists(),
        })

    # Check for Day 2 ZIP
    step7 = results.get("step_7", {})
    if step7.get("zip_path"):
        from pathlib import Path
        zip_path = Path(step7["zip_path"])
        csvs.append({
            "type": "day2",
            "filename": zip_path.name,
            "path": str(zip_path),
            "exists": zip_path.exists(),
            "profile": step7.get("profile"),
        })

    return {"pipeline_id": pipeline_id, "csvs": csvs}


@router.get("/csvs/{pipeline_id}/{csv_type}")
async def download_csv(
    pipeline_id: int,
    csv_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download a generated CSV ZIP file (day1 or day2)."""
    from fastapi.responses import FileResponse
    from pathlib import Path

    result = await db.execute(
        select(DeploymentPipelineRun)
        .where(DeploymentPipelineRun.id == pipeline_id)
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    results = pipeline.results or {}

    if csv_type == "day1":
        step_result = results.get("step_6", {})
    elif csv_type == "day2":
        step_result = results.get("step_7", {})
    else:
        raise HTTPException(status_code=400, detail="csv_type must be 'day1' or 'day2'")

    zip_path = step_result.get("zip_path")
    if not zip_path:
        raise HTTPException(status_code=404, detail=f"No {csv_type} CSV available")

    zip_file = Path(zip_path)
    if not zip_file.exists():
        raise HTTPException(status_code=404, detail=f"CSV file not found: {zip_file.name}")

    return FileResponse(
        path=str(zip_file),
        filename=zip_file.name,
        media_type="application/zip",
    )
