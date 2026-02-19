"""Forecast pipeline endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_sync_db
from app.models.user import User
from app.models.forecast_pipeline import (
    ForecastPipelineConfig,
    ForecastPipelineRun,
    ForecastPipelinePublishLog,
)
from app.services.forecast_pipeline_service import ForecastPipelineService

router = APIRouter()


class PipelineConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    config_id: int
    time_bucket: str = Field("W", pattern="^(D|W|M)$")
    forecast_horizon: int = Field(8, ge=1, le=104)
    min_clusters: int = Field(2, ge=1, le=100)
    max_clusters: int = Field(8, ge=1, le=100)
    min_observations: int = Field(12, ge=3, le=1000)
    forecast_metric: str = Field("wape")
    model_type: str = Field("clustered_naive")
    parameters: Optional[Dict[str, Any]] = None


class PipelineRunCreate(BaseModel):
    pipeline_config_id: int
    auto_start: bool = True


class PublishRequest(BaseModel):
    notes: Optional[str] = None


@router.get("/configs")
def list_configs(
    config_id: Optional[int] = None,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    q = db.query(ForecastPipelineConfig).filter(ForecastPipelineConfig.group_id == current_user.group_id)
    if config_id is not None:
        q = q.filter(ForecastPipelineConfig.config_id == config_id)
    items = q.order_by(ForecastPipelineConfig.updated_at.desc()).all()
    return [
        {
            "id": i.id,
            "name": i.name,
            "description": i.description,
            "config_id": i.config_id,
            "time_bucket": i.time_bucket,
            "forecast_horizon": i.forecast_horizon,
            "min_clusters": i.min_clusters,
            "max_clusters": i.max_clusters,
            "min_observations": i.min_observations,
            "forecast_metric": i.forecast_metric,
            "model_type": i.model_type,
            "parameters": i.parameters or {},
            "is_active": i.is_active,
            "updated_at": i.updated_at,
        }
        for i in items
    ]


@router.post("/configs")
def create_config(
    payload: PipelineConfigCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    if payload.max_clusters < payload.min_clusters:
        raise HTTPException(status_code=400, detail="max_clusters must be >= min_clusters")

    item = ForecastPipelineConfig(
        name=payload.name,
        description=payload.description,
        group_id=current_user.group_id,
        config_id=payload.config_id,
        time_bucket=payload.time_bucket,
        forecast_horizon=payload.forecast_horizon,
        min_clusters=payload.min_clusters,
        max_clusters=payload.max_clusters,
        min_observations=payload.min_observations,
        forecast_metric=payload.forecast_metric,
        model_type=payload.model_type,
        parameters=payload.parameters or {},
        created_by_id=current_user.id,
    )
    db.add(item)
    db.flush()
    return {"id": item.id, "name": item.name}


@router.get("/runs")
def list_runs(
    pipeline_config_id: Optional[int] = None,
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    q = db.query(ForecastPipelineRun).filter(ForecastPipelineRun.group_id == current_user.group_id)
    if pipeline_config_id is not None:
        q = q.filter(ForecastPipelineRun.pipeline_config_id == pipeline_config_id)
    rows = q.order_by(ForecastPipelineRun.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "pipeline_config_id": r.pipeline_config_id,
            "status": r.status,
            "error_message": r.error_message,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "created_at": r.created_at,
            "model_type": r.model_type,
            "forecast_metric": r.forecast_metric,
            "records_processed": r.records_processed,
            "run_log": r.run_log or {},
        }
        for r in rows
    ]


@router.post("/runs")
def create_run(
    payload: PipelineRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    cfg = (
        db.query(ForecastPipelineConfig)
        .filter(
            ForecastPipelineConfig.id == payload.pipeline_config_id,
            ForecastPipelineConfig.group_id == current_user.group_id,
            ForecastPipelineConfig.is_active.is_(True),
        )
        .first()
    )
    if not cfg:
        raise HTTPException(status_code=404, detail="Pipeline config not found")

    run = ForecastPipelineRun(
        pipeline_config_id=cfg.id,
        group_id=cfg.group_id,
        config_id=cfg.config_id,
        status="pending",
        created_by_id=current_user.id,
        model_type=cfg.model_type,
        forecast_metric=cfg.forecast_metric,
    )
    db.add(run)
    db.flush()

    if payload.auto_start:
        background_tasks.add_task(ForecastPipelineService.run_pipeline_task, run.id)
    return {"id": run.id, "status": run.status, "auto_started": payload.auto_start}


@router.post("/runs/{run_id}/execute")
def execute_run(
    run_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    run = (
        db.query(ForecastPipelineRun)
        .filter(
            ForecastPipelineRun.id == run_id,
            ForecastPipelineRun.group_id == current_user.group_id,
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status == "running":
        raise HTTPException(status_code=409, detail="Run is already in progress")

    run.status = "pending"
    run.error_message = None
    run.started_at = None
    run.completed_at = None
    background_tasks.add_task(ForecastPipelineService.run_pipeline_task, run.id)
    return {"id": run.id, "status": run.status}


@router.get("/runs/{run_id}")
def get_run(
    run_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    run = (
        db.query(ForecastPipelineRun)
        .filter(
            ForecastPipelineRun.id == run_id,
            ForecastPipelineRun.group_id == current_user.group_id,
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": run.id,
        "pipeline_config_id": run.pipeline_config_id,
        "status": run.status,
        "error_message": run.error_message,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "created_at": run.created_at,
        "model_type": run.model_type,
        "forecast_metric": run.forecast_metric,
        "records_processed": run.records_processed,
        "run_log": run.run_log or {},
    }


@router.post("/runs/{run_id}/publish")
def publish_run(
    run_id: int,
    payload: PublishRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    run = (
        db.query(ForecastPipelineRun)
        .filter(
            ForecastPipelineRun.id == run_id,
            ForecastPipelineRun.group_id == current_user.group_id,
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    try:
        published = ForecastPipelineService(db).publish_run(run.id, current_user.id, payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"run_id": run.id, "published_records": published, "status": "published"}


@router.get("/runs/{run_id}/publish-log")
def get_publish_log(
    run_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    run = (
        db.query(ForecastPipelineRun)
        .filter(
            ForecastPipelineRun.id == run_id,
            ForecastPipelineRun.group_id == current_user.group_id,
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    logs = (
        db.query(ForecastPipelinePublishLog)
        .filter(ForecastPipelinePublishLog.run_id == run_id)
        .order_by(ForecastPipelinePublishLog.published_at.desc())
        .all()
    )
    return [
        {
            "id": item.id,
            "run_id": item.run_id,
            "published_by_id": item.published_by_id,
            "published_at": item.published_at,
            "records_published": item.records_published,
            "notes": item.notes,
        }
        for item in logs
    ]
