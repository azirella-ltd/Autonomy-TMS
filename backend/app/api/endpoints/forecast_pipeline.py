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

VALID_CLUSTER_METHODS = (
    "KMeans", "HDBSCAN", "Agglomerative", "OPTICS", "Birch",
    "GaussianMixture", "MeanShift", "Spectral", "AffinityPropagation",
)
VALID_FEATURE_METHODS = ("LassoCV", "RandomForest", "MutualInformation")
VALID_CHAR_METHODS = ("tsfresh", "classifier", "both")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

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

    # Dataset & Column Mapping
    demand_item: Optional[str] = None
    demand_point: Optional[str] = None
    target_column: Optional[str] = None
    date_column: Optional[str] = None

    # Forecast Settings
    number_of_items_analyzed: Optional[int] = Field(None, ge=1)

    # Data Quality Thresholds
    ignore_numeric_columns: Optional[str] = None
    cv_sq_threshold: float = Field(0.49, ge=0.0, le=10.0)
    adi_threshold: float = Field(1.32, ge=0.0, le=10.0)

    # Clustering Configuration
    min_cluster_size: int = Field(5, ge=1)
    min_cluster_size_uom: str = Field("items", pattern="^(items|percent)$")
    cluster_selection_method: str = Field("KMeans")

    # Feature Engineering
    characteristics_creation_method: str = Field("tsfresh")
    feature_correlation_threshold: float = Field(0.8, ge=0.0, le=1.0)
    feature_importance_method: str = Field("LassoCV")
    feature_importance_threshold: float = Field(0.01, ge=0.0, le=1.0)
    pca_variance_threshold: float = Field(0.95, ge=0.0, le=1.0)
    pca_importance_threshold: float = Field(0.01, ge=0.0, le=1.0)


class PipelineConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None
    time_bucket: Optional[str] = Field(None, pattern="^(D|W|M)$")
    forecast_horizon: Optional[int] = Field(None, ge=1, le=104)
    min_clusters: Optional[int] = Field(None, ge=1, le=100)
    max_clusters: Optional[int] = Field(None, ge=1, le=100)
    min_observations: Optional[int] = Field(None, ge=3, le=1000)
    forecast_metric: Optional[str] = None
    model_type: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None

    # Dataset & Column Mapping
    demand_item: Optional[str] = None
    demand_point: Optional[str] = None
    target_column: Optional[str] = None
    date_column: Optional[str] = None

    # Forecast Settings
    number_of_items_analyzed: Optional[int] = Field(None, ge=1)

    # Data Quality Thresholds
    ignore_numeric_columns: Optional[str] = None
    cv_sq_threshold: Optional[float] = Field(None, ge=0.0, le=10.0)
    adi_threshold: Optional[float] = Field(None, ge=0.0, le=10.0)

    # Clustering Configuration
    min_cluster_size: Optional[int] = Field(None, ge=1)
    min_cluster_size_uom: Optional[str] = Field(None, pattern="^(items|percent)$")
    cluster_selection_method: Optional[str] = None

    # Feature Engineering
    characteristics_creation_method: Optional[str] = None
    feature_correlation_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    feature_importance_method: Optional[str] = None
    feature_importance_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    pca_variance_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    pca_importance_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)


class PipelineRunCreate(BaseModel):
    pipeline_config_id: int
    auto_start: bool = True


class PublishRequest(BaseModel):
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config_to_dict(cfg: ForecastPipelineConfig) -> dict:
    return {
        "id": cfg.id,
        "name": cfg.name,
        "description": cfg.description,
        "config_id": cfg.config_id,
        "time_bucket": cfg.time_bucket,
        "forecast_horizon": cfg.forecast_horizon,
        "min_clusters": cfg.min_clusters,
        "max_clusters": cfg.max_clusters,
        "min_observations": cfg.min_observations,
        "forecast_metric": cfg.forecast_metric,
        "model_type": cfg.model_type,
        "parameters": cfg.parameters or {},
        # Dataset & Column Mapping
        "demand_item": cfg.demand_item,
        "demand_point": cfg.demand_point,
        "target_column": cfg.target_column,
        "date_column": cfg.date_column,
        # Forecast Settings
        "number_of_items_analyzed": cfg.number_of_items_analyzed,
        # Data Quality Thresholds
        "ignore_numeric_columns": cfg.ignore_numeric_columns,
        "cv_sq_threshold": cfg.cv_sq_threshold,
        "adi_threshold": cfg.adi_threshold,
        # Clustering Configuration
        "min_cluster_size": cfg.min_cluster_size,
        "min_cluster_size_uom": cfg.min_cluster_size_uom,
        "cluster_selection_method": cfg.cluster_selection_method,
        # Feature Engineering
        "characteristics_creation_method": cfg.characteristics_creation_method,
        "feature_correlation_threshold": cfg.feature_correlation_threshold,
        "feature_importance_method": cfg.feature_importance_method,
        "feature_importance_threshold": cfg.feature_importance_threshold,
        "pca_variance_threshold": cfg.pca_variance_threshold,
        "pca_importance_threshold": cfg.pca_importance_threshold,
        # Metadata
        "is_active": cfg.is_active,
        "created_at": cfg.created_at,
        "updated_at": cfg.updated_at,
    }


# ---------------------------------------------------------------------------
# Config endpoints
# ---------------------------------------------------------------------------

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
    return [_config_to_dict(i) for i in items]


@router.post("/configs")
def create_config(
    payload: PipelineConfigCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    if payload.max_clusters < payload.min_clusters:
        raise HTTPException(status_code=400, detail="max_clusters must be >= min_clusters")
    if payload.cluster_selection_method not in VALID_CLUSTER_METHODS:
        raise HTTPException(status_code=400, detail=f"cluster_selection_method must be one of {VALID_CLUSTER_METHODS}")
    if payload.feature_importance_method not in VALID_FEATURE_METHODS:
        raise HTTPException(status_code=400, detail=f"feature_importance_method must be one of {VALID_FEATURE_METHODS}")
    if payload.characteristics_creation_method not in VALID_CHAR_METHODS:
        raise HTTPException(status_code=400, detail=f"characteristics_creation_method must be one of {VALID_CHAR_METHODS}")

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
        # Dataset & Column Mapping
        demand_item=payload.demand_item,
        demand_point=payload.demand_point,
        target_column=payload.target_column,
        date_column=payload.date_column,
        # Forecast Settings
        number_of_items_analyzed=payload.number_of_items_analyzed,
        # Data Quality Thresholds
        ignore_numeric_columns=payload.ignore_numeric_columns,
        cv_sq_threshold=payload.cv_sq_threshold,
        adi_threshold=payload.adi_threshold,
        # Clustering Configuration
        min_cluster_size=payload.min_cluster_size,
        min_cluster_size_uom=payload.min_cluster_size_uom,
        cluster_selection_method=payload.cluster_selection_method,
        # Feature Engineering
        characteristics_creation_method=payload.characteristics_creation_method,
        feature_correlation_threshold=payload.feature_correlation_threshold,
        feature_importance_method=payload.feature_importance_method,
        feature_importance_threshold=payload.feature_importance_threshold,
        pca_variance_threshold=payload.pca_variance_threshold,
        pca_importance_threshold=payload.pca_importance_threshold,
        created_by_id=current_user.id,
    )
    db.add(item)
    db.flush()
    return _config_to_dict(item)


@router.put("/configs/{config_id}")
def update_config(
    config_id: int,
    payload: PipelineConfigUpdate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    item = (
        db.query(ForecastPipelineConfig)
        .filter(
            ForecastPipelineConfig.id == config_id,
            ForecastPipelineConfig.group_id == current_user.group_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline config not found")

    update_data = payload.model_dump(exclude_unset=True)

    # Validate enum fields if provided
    if "cluster_selection_method" in update_data and update_data["cluster_selection_method"] not in VALID_CLUSTER_METHODS:
        raise HTTPException(status_code=400, detail=f"cluster_selection_method must be one of {VALID_CLUSTER_METHODS}")
    if "feature_importance_method" in update_data and update_data["feature_importance_method"] not in VALID_FEATURE_METHODS:
        raise HTTPException(status_code=400, detail=f"feature_importance_method must be one of {VALID_FEATURE_METHODS}")
    if "characteristics_creation_method" in update_data and update_data["characteristics_creation_method"] not in VALID_CHAR_METHODS:
        raise HTTPException(status_code=400, detail=f"characteristics_creation_method must be one of {VALID_CHAR_METHODS}")

    for key, value in update_data.items():
        setattr(item, key, value)

    # Cross-field validation after applying updates
    if item.max_clusters < item.min_clusters:
        raise HTTPException(status_code=400, detail="max_clusters must be >= min_clusters")

    item.updated_at = datetime.utcnow()
    db.flush()
    return _config_to_dict(item)


# ---------------------------------------------------------------------------
# Run endpoints
# ---------------------------------------------------------------------------

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
