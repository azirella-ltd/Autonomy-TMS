"""
Powell Training Configuration API Endpoints

Provides CRUD for Powell training configurations and training job management.
Customer administrators configure AI model training here.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from pydantic import BaseModel, Field

from app.db.session import get_db as get_async_session
from app.models.powell_training_config import (
    PowellTrainingConfig,
    TRMTrainingConfig,
    TRMSiteTrainingConfig,
    TrainingRun,
    TRMType,
    TrainingStatus,
    LearningPhase,
    PhaseStatus,
    TRM_APPLICABILITY,
    DEFAULT_TRM_REWARD_WEIGHTS,
)
from app.models.planning_hierarchy import PlanningHierarchyConfig, PlanningType
from app.api.deps import get_current_user
from app.models.user import User, UserTypeEnum

router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class TRMTrainingConfigSchema(BaseModel):
    """Schema for TRM training configuration."""
    trm_type: str
    enabled: bool = True
    state_dim: int = 26
    hidden_dim: int = 128
    num_heads: int = 4
    num_layers: int = 2
    epochs: Optional[int] = None
    learning_rate: Optional[float] = None
    batch_size: Optional[int] = None
    reward_weights: Dict[str, float] = Field(default_factory=dict)
    retrain_frequency_hours: int = 24
    min_training_samples: int = 1000


class PowellTrainingConfigCreate(BaseModel):
    """Schema for creating Powell training configuration."""
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    config_id: int  # Supply chain config

    # Hierarchy config references
    sop_hierarchy_config_id: Optional[int] = None
    execution_hierarchy_config_id: Optional[int] = None

    # Data generation
    num_simulation_runs: int = Field(ge=10, le=1000, default=128)
    timesteps_per_run: int = Field(ge=20, le=500, default=64)
    history_window: int = Field(ge=10, le=100, default=52)
    forecast_horizon: int = Field(ge=1, le=52, default=8)
    demand_patterns: Dict[str, float] = Field(default_factory=lambda: {
        "random": 0.3, "seasonal": 0.3, "step": 0.2, "trend": 0.2
    })

    # S&OP GraphSAGE
    train_sop_graphsage: bool = True
    sop_hidden_dim: int = Field(ge=32, le=512, default=128)
    sop_embedding_dim: int = Field(ge=16, le=256, default=64)
    sop_num_layers: int = Field(ge=1, le=6, default=3)
    sop_epochs: int = Field(ge=1, le=500, default=50)
    sop_learning_rate: float = Field(ge=1e-6, le=1e-1, default=1e-3)
    sop_retrain_frequency_hours: int = Field(ge=1, default=168)

    # Execution tGNN
    train_execution_tgnn: bool = True
    tgnn_hidden_dim: int = Field(ge=32, le=512, default=128)
    tgnn_window_size: int = Field(ge=5, le=50, default=10)
    tgnn_num_layers: int = Field(ge=1, le=6, default=2)
    tgnn_epochs: int = Field(ge=1, le=500, default=100)
    tgnn_learning_rate: float = Field(ge=1e-6, le=1e-1, default=1e-3)
    tgnn_retrain_frequency_hours: int = Field(ge=1, default=24)

    # TRM settings
    trm_training_method: str = Field(default="hybrid", pattern="^(behavioral_cloning|td_learning|hybrid|offline_rl)$")
    trm_bc_epochs: int = Field(ge=1, le=100, default=20)
    trm_rl_epochs: int = Field(ge=1, le=500, default=80)
    trm_learning_rate: float = Field(ge=1e-6, le=1e-1, default=1e-4)

    # TRM configs per type
    trm_configs: List[TRMTrainingConfigSchema] = Field(default_factory=list)


class PowellTrainingConfigUpdate(BaseModel):
    """Schema for updating Powell training configuration."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    sop_hierarchy_config_id: Optional[int] = None
    execution_hierarchy_config_id: Optional[int] = None
    num_simulation_runs: Optional[int] = Field(None, ge=10, le=1000)
    train_sop_graphsage: Optional[bool] = None
    train_execution_tgnn: Optional[bool] = None
    sop_epochs: Optional[int] = Field(None, ge=1, le=500)
    tgnn_epochs: Optional[int] = Field(None, ge=1, le=500)
    is_active: Optional[bool] = None


class PowellTrainingConfigResponse(BaseModel):
    """Response schema for Powell training configuration."""
    id: int
    tenant_id: int
    config_id: int
    name: str
    description: Optional[str]

    sop_hierarchy_config_id: Optional[int]
    execution_hierarchy_config_id: Optional[int]

    # Data generation
    num_simulation_runs: int
    timesteps_per_run: int
    history_window: int
    forecast_horizon: int
    demand_patterns: Dict[str, float]

    # S&OP
    train_sop_graphsage: bool
    sop_hidden_dim: int
    sop_embedding_dim: int
    sop_epochs: int
    sop_retrain_frequency_hours: int

    # tGNN
    train_execution_tgnn: bool
    tgnn_hidden_dim: int
    tgnn_window_size: int
    tgnn_epochs: int
    tgnn_retrain_frequency_hours: int

    # TRM
    trm_training_method: str
    trm_bc_epochs: int
    trm_rl_epochs: int

    # State
    is_active: bool
    last_training_started: Optional[datetime]
    last_training_completed: Optional[datetime]
    last_training_status: Optional[str]

    # TRM configs
    trm_configs: List[Dict[str, Any]] = []

    class Config:
        from_attributes = True


class TrainingRunResponse(BaseModel):
    """Response schema for training run."""
    id: int
    powell_config_id: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    current_phase: str
    progress_percent: float
    samples_generated: Optional[int]
    sop_epochs_completed: Optional[int]
    sop_final_loss: Optional[float]
    tgnn_epochs_completed: Optional[int]
    tgnn_final_loss: Optional[float]
    trm_results: Dict[str, Any]
    error_message: Optional[str]

    class Config:
        from_attributes = True


class TRMTypeInfo(BaseModel):
    """Information about a TRM type."""
    type: str
    name: str
    description: str
    decision_scope: str
    default_reward_weights: Dict[str, float]


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/trm-types", response_model=List[TRMTypeInfo])
async def list_trm_types():
    """
    List all TRM types with their descriptions.

    Each TRM type has a different decision scope and reward function.
    """
    return [
        TRMTypeInfo(
            type=TRMType.ATP_EXECUTOR.value,
            name="ATP Executor",
            description="Allocated Available-to-Promise consumption decisions",
            decision_scope="Per order, <10ms - decides how to fulfill customer orders using allocated inventory",
            default_reward_weights=DEFAULT_TRM_REWARD_WEIGHTS[TRMType.ATP_EXECUTOR]
        ),
        TRMTypeInfo(
            type=TRMType.REBALANCING.value,
            name="Inventory Rebalancing",
            description="Cross-location inventory transfer decisions",
            decision_scope="Per product-location pair, daily - decides when to transfer inventory between sites",
            default_reward_weights=DEFAULT_TRM_REWARD_WEIGHTS[TRMType.REBALANCING]
        ),
        TRMTypeInfo(
            type=TRMType.PO_CREATION.value,
            name="PO Creation",
            description="Purchase order timing and quantity decisions",
            decision_scope="Per product-location, daily - decides when and how much to order",
            default_reward_weights=DEFAULT_TRM_REWARD_WEIGHTS[TRMType.PO_CREATION]
        ),
        TRMTypeInfo(
            type=TRMType.ORDER_TRACKING.value,
            name="Order Tracking",
            description="Exception detection and recommended resolution actions",
            decision_scope="Per order, continuous - detects issues and suggests actions",
            default_reward_weights=DEFAULT_TRM_REWARD_WEIGHTS[TRMType.ORDER_TRACKING]
        ),
        TRMTypeInfo(
            type=TRMType.SAFETY_STOCK.value,
            name="Safety Stock",
            description="Safety stock adjustment decisions based on demand patterns and risk",
            decision_scope="Per product-location, periodic - adjusts safety stock multipliers",
            default_reward_weights=DEFAULT_TRM_REWARD_WEIGHTS[TRMType.SAFETY_STOCK]
        )
    ]


@router.get("/configs", response_model=List[PowellTrainingConfigResponse])
async def list_powell_training_configs(
    tenant_id: int,
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    List all Powell training configurations for a customer.
    """
    if current_user.tenant_id != tenant_id and current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    query = select(PowellTrainingConfig).where(
        PowellTrainingConfig.tenant_id == tenant_id
    )
    if not include_inactive:
        query = query.where(PowellTrainingConfig.is_active == True)

    result = await db.execute(query)
    configs = result.scalars().all()

    responses = []
    for config in configs:
        # Get TRM configs
        trm_result = await db.execute(
            select(TRMTrainingConfig).where(
                TRMTrainingConfig.powell_config_id == config.id
            )
        )
        trm_configs = trm_result.scalars().all()

        responses.append(PowellTrainingConfigResponse(
            id=config.id,
            tenant_id=config.tenant_id,
            config_id=config.config_id,
            name=config.name,
            description=config.description,
            sop_hierarchy_config_id=config.sop_hierarchy_config_id,
            execution_hierarchy_config_id=config.execution_hierarchy_config_id,
            num_simulation_runs=config.num_simulation_runs,
            timesteps_per_run=config.timesteps_per_run,
            history_window=config.history_window,
            forecast_horizon=config.forecast_horizon,
            demand_patterns=config.demand_patterns or {},
            train_sop_graphsage=config.train_sop_graphsage,
            sop_hidden_dim=config.sop_hidden_dim,
            sop_embedding_dim=config.sop_embedding_dim,
            sop_epochs=config.sop_epochs,
            sop_retrain_frequency_hours=config.sop_retrain_frequency_hours,
            train_execution_tgnn=config.train_execution_tgnn,
            tgnn_hidden_dim=config.tgnn_hidden_dim,
            tgnn_window_size=config.tgnn_window_size,
            tgnn_epochs=config.tgnn_epochs,
            tgnn_retrain_frequency_hours=config.tgnn_retrain_frequency_hours,
            trm_training_method=config.trm_training_method,
            trm_bc_epochs=config.trm_bc_epochs,
            trm_rl_epochs=config.trm_rl_epochs,
            is_active=config.is_active,
            last_training_started=config.last_training_started,
            last_training_completed=config.last_training_completed,
            last_training_status=config.last_training_status,
            trm_configs=[{
                "trm_type": tc.trm_type.value,
                "enabled": tc.enabled,
                "state_dim": tc.state_dim,
                "hidden_dim": tc.hidden_dim,
                "epochs": tc.epochs,
                "reward_weights": tc.reward_weights or {},
                "last_trained": tc.last_trained.isoformat() if tc.last_trained else None,
                "last_training_loss": tc.last_training_loss
            } for tc in trm_configs]
        ))

    return responses


@router.post("/configs", response_model=PowellTrainingConfigResponse)
async def create_powell_training_config(
    tenant_id: int,
    config: PowellTrainingConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new Powell training configuration.

    Only Customer Admin can create training configurations.
    """
    if current_user.tenant_id != tenant_id and current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Verify hierarchy configs exist if specified
    if config.sop_hierarchy_config_id:
        sop_result = await db.execute(
            select(PlanningHierarchyConfig).where(
                and_(
                    PlanningHierarchyConfig.id == config.sop_hierarchy_config_id,
                    PlanningHierarchyConfig.tenant_id == tenant_id
                )
            )
        )
        if not sop_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="S&OP hierarchy config not found")

    # Create main config
    db_config = PowellTrainingConfig(
        tenant_id=tenant_id,
        config_id=config.config_id,
        name=config.name,
        description=config.description,
        sop_hierarchy_config_id=config.sop_hierarchy_config_id,
        execution_hierarchy_config_id=config.execution_hierarchy_config_id,
        num_simulation_runs=config.num_simulation_runs,
        timesteps_per_run=config.timesteps_per_run,
        history_window=config.history_window,
        forecast_horizon=config.forecast_horizon,
        demand_patterns=config.demand_patterns,
        train_sop_graphsage=config.train_sop_graphsage,
        sop_hidden_dim=config.sop_hidden_dim,
        sop_embedding_dim=config.sop_embedding_dim,
        sop_num_layers=config.sop_num_layers,
        sop_epochs=config.sop_epochs,
        sop_learning_rate=config.sop_learning_rate,
        sop_retrain_frequency_hours=config.sop_retrain_frequency_hours,
        train_execution_tgnn=config.train_execution_tgnn,
        tgnn_hidden_dim=config.tgnn_hidden_dim,
        tgnn_window_size=config.tgnn_window_size,
        tgnn_num_layers=config.tgnn_num_layers,
        tgnn_epochs=config.tgnn_epochs,
        tgnn_learning_rate=config.tgnn_learning_rate,
        tgnn_retrain_frequency_hours=config.tgnn_retrain_frequency_hours,
        trm_training_method=config.trm_training_method,
        trm_bc_epochs=config.trm_bc_epochs,
        trm_rl_epochs=config.trm_rl_epochs,
        trm_learning_rate=config.trm_learning_rate,
        created_by=current_user.id
    )
    db.add(db_config)
    await db.flush()

    # Create TRM configs
    trm_configs_list = config.trm_configs if config.trm_configs else [
        TRMTrainingConfigSchema(trm_type=t.value) for t in TRMType
    ]

    created_trm_configs = []
    for trm_config in trm_configs_list:
        trm_type = TRMType(trm_config.trm_type)
        reward_weights = trm_config.reward_weights or DEFAULT_TRM_REWARD_WEIGHTS.get(trm_type, {})

        db_trm = TRMTrainingConfig(
            powell_config_id=db_config.id,
            trm_type=trm_type,
            enabled=trm_config.enabled,
            state_dim=trm_config.state_dim,
            hidden_dim=trm_config.hidden_dim,
            num_heads=trm_config.num_heads,
            num_layers=trm_config.num_layers,
            epochs=trm_config.epochs,
            learning_rate=trm_config.learning_rate,
            batch_size=trm_config.batch_size,
            reward_weights=reward_weights,
            retrain_frequency_hours=trm_config.retrain_frequency_hours,
            min_training_samples=trm_config.min_training_samples
        )
        db.add(db_trm)
        created_trm_configs.append(db_trm)

    await db.commit()
    await db.refresh(db_config)

    return PowellTrainingConfigResponse(
        id=db_config.id,
        tenant_id=db_config.tenant_id,
        config_id=db_config.config_id,
        name=db_config.name,
        description=db_config.description,
        sop_hierarchy_config_id=db_config.sop_hierarchy_config_id,
        execution_hierarchy_config_id=db_config.execution_hierarchy_config_id,
        num_simulation_runs=db_config.num_simulation_runs,
        timesteps_per_run=db_config.timesteps_per_run,
        history_window=db_config.history_window,
        forecast_horizon=db_config.forecast_horizon,
        demand_patterns=db_config.demand_patterns or {},
        train_sop_graphsage=db_config.train_sop_graphsage,
        sop_hidden_dim=db_config.sop_hidden_dim,
        sop_embedding_dim=db_config.sop_embedding_dim,
        sop_epochs=db_config.sop_epochs,
        sop_retrain_frequency_hours=db_config.sop_retrain_frequency_hours,
        train_execution_tgnn=db_config.train_execution_tgnn,
        tgnn_hidden_dim=db_config.tgnn_hidden_dim,
        tgnn_window_size=db_config.tgnn_window_size,
        tgnn_epochs=db_config.tgnn_epochs,
        tgnn_retrain_frequency_hours=db_config.tgnn_retrain_frequency_hours,
        trm_training_method=db_config.trm_training_method,
        trm_bc_epochs=db_config.trm_bc_epochs,
        trm_rl_epochs=db_config.trm_rl_epochs,
        is_active=db_config.is_active,
        last_training_started=None,
        last_training_completed=None,
        last_training_status=None,
        trm_configs=[{
            "trm_type": tc.trm_type.value,
            "enabled": tc.enabled,
            "state_dim": tc.state_dim,
            "hidden_dim": tc.hidden_dim,
            "epochs": tc.epochs,
            "reward_weights": tc.reward_weights or {},
            "last_trained": None,
            "last_training_loss": None
        } for tc in created_trm_configs]
    )


@router.post("/configs/{config_id}/start-training", response_model=TrainingRunResponse)
async def start_training_run(
    config_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Start a training run for a Powell configuration.

    This triggers the full training pipeline:
    1. Generate training data from SC config
    2. Aggregate data to S&OP hierarchy level
    3. Train S&OP GraphSAGE on aggregated data
    4. Train Execution tGNN with S&OP embeddings
    5. Train each enabled TRM

    Only Group Admin can trigger training.
    """
    # Get config
    result = await db.execute(
        select(PowellTrainingConfig).where(PowellTrainingConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    if current_user.tenant_id != config.tenant_id and current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Create training run record
    training_run = TrainingRun(
        powell_config_id=config_id,
        status=TrainingStatus.PENDING,
        current_phase="queued",
        progress_percent=0.0,
        triggered_by=current_user.id
    )
    db.add(training_run)
    await db.commit()
    await db.refresh(training_run)

    # Update config status
    config.last_training_started = datetime.utcnow()
    config.last_training_status = "running"
    await db.commit()

    # Queue background training task
    # Note: actual implementation would use Celery or similar
    background_tasks.add_task(
        execute_training_pipeline,
        training_run.id,
        config_id
    )

    return TrainingRunResponse(
        id=training_run.id,
        powell_config_id=training_run.powell_config_id,
        status=training_run.status.value,
        started_at=training_run.started_at,
        completed_at=training_run.completed_at,
        current_phase=training_run.current_phase,
        progress_percent=training_run.progress_percent,
        samples_generated=training_run.samples_generated,
        sop_epochs_completed=training_run.sop_epochs_completed,
        sop_final_loss=training_run.sop_final_loss,
        tgnn_epochs_completed=training_run.tgnn_epochs_completed,
        tgnn_final_loss=training_run.tgnn_final_loss,
        trm_results=training_run.trm_results or {},
        error_message=training_run.error_message
    )


@router.get("/configs/{config_id}/runs", response_model=List[TrainingRunResponse])
async def list_training_runs(
    config_id: int,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    List training runs for a configuration.
    """
    result = await db.execute(
        select(TrainingRun)
        .where(TrainingRun.powell_config_id == config_id)
        .order_by(TrainingRun.started_at.desc())
        .limit(limit)
    )
    runs = result.scalars().all()

    return [TrainingRunResponse(
        id=r.id,
        powell_config_id=r.powell_config_id,
        status=r.status.value,
        started_at=r.started_at,
        completed_at=r.completed_at,
        current_phase=r.current_phase,
        progress_percent=r.progress_percent,
        samples_generated=r.samples_generated,
        sop_epochs_completed=r.sop_epochs_completed,
        sop_final_loss=r.sop_final_loss,
        tgnn_epochs_completed=r.tgnn_epochs_completed,
        tgnn_final_loss=r.tgnn_final_loss,
        trm_results=r.trm_results or {},
        error_message=r.error_message
    ) for r in runs]


async def execute_training_pipeline(run_id: int, config_id: int):
    """
    Background task to execute the full training pipeline.

    This is a placeholder - actual implementation would be in
    powell_training_service.py
    """
    from app.services.powell.powell_training_service import execute_training_pipeline as execute_pipeline
    await execute_pipeline(run_id, config_id)


# ============================================================================
# Per-Site TRM Training Endpoints
# ============================================================================

class SiteTrainingStatusResponse(BaseModel):
    """Per-site training status for one site."""
    site_id: int
    site_name: str
    master_type: str
    trm_configs: List[Dict[str, Any]]


class SiteTrainRequest(BaseModel):
    """Request to train specific site(s)."""
    trm_types: Optional[List[str]] = None
    phases: Optional[List[int]] = None
    epochs: Optional[int] = None


@router.get("/configs/{config_id}/sites")
async def list_training_sites(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
) -> List[SiteTrainingStatusResponse]:
    """
    List sites with per-TRM training status for a configuration.

    Returns each operational site (inventory/manufacturer) with its
    applicable TRM types and 3-phase learning-depth progress.
    """
    from sqlalchemy import func

    result = await db.execute(
        select(PowellTrainingConfig).where(PowellTrainingConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    if current_user.tenant_id != config.tenant_id and current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get all site training configs for this powell config
    result = await db.execute(
        select(TRMSiteTrainingConfig).where(
            TRMSiteTrainingConfig.powell_config_id == config_id
        ).order_by(TRMSiteTrainingConfig.site_id, TRMSiteTrainingConfig.trm_type)
    )
    site_configs = result.scalars().all()

    # Group by site
    sites_map: Dict[int, SiteTrainingStatusResponse] = {}
    for sc in site_configs:
        if sc.site_id not in sites_map:
            sites_map[sc.site_id] = SiteTrainingStatusResponse(
                site_id=sc.site_id,
                site_name=sc.site_name,
                master_type=sc.master_type,
                trm_configs=[],
            )
        sites_map[sc.site_id].trm_configs.append({
            "trm_type": sc.trm_type.value if hasattr(sc.trm_type, 'value') else sc.trm_type,
            "enabled": sc.enabled,
            "phase1_status": sc.phase1_status,
            "phase1_epochs": sc.phase1_epochs_completed,
            "phase1_loss": sc.phase1_loss,
            "phase2_status": sc.phase2_status,
            "phase2_epochs": sc.phase2_epochs_completed,
            "phase2_loss": sc.phase2_loss,
            "phase2_expert_samples": sc.phase2_expert_samples,
            "phase2_min_samples": sc.phase2_min_samples,
            "phase3_status": sc.phase3_status,
            "phase3_epochs": sc.phase3_epochs_completed,
            "phase3_loss": sc.phase3_loss,
            "phase3_outcome_samples": sc.phase3_outcome_samples,
            "phase3_min_samples": sc.phase3_min_samples,
            "model_version": sc.model_version,
            "checkpoint_path": sc.model_checkpoint_path,
            "last_trained_at": sc.last_trained_at.isoformat() if sc.last_trained_at else None,
            "eval_accuracy": sc.eval_accuracy,
            "eval_vs_engine_improvement": sc.eval_vs_engine_improvement,
        })

    return list(sites_map.values())


@router.post("/configs/{config_id}/sites/{site_id}/train")
async def train_site(
    config_id: int,
    site_id: int,
    request: SiteTrainRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
) -> Dict[str, Any]:
    """
    Train TRM models for a specific site.

    Runs the 3-phase learning-depth curriculum:
    - Phase 1: Engine Imitation (BC) — always available
    - Phase 2: Context Learning — requires ≥500 expert decisions
    - Phase 3: Outcome Optimization — requires ≥1000 outcome records
    """
    result = await db.execute(
        select(PowellTrainingConfig).where(PowellTrainingConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    if current_user.tenant_id != config.tenant_id and current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    from app.services.powell.powell_training_service import PowellTrainingService

    service = PowellTrainingService(db, config_id)
    result = await service.train_trm_per_site(
        site_ids=[site_id],
        trm_types=request.trm_types,
        phases=request.phases,
        epochs_override=request.epochs,
    )

    return result


@router.post("/configs/{config_id}/train-all-sites")
async def train_all_sites(
    config_id: int,
    request: SiteTrainRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
) -> Dict[str, Any]:
    """
    Train TRM models for all operational sites in a configuration.

    Iterates all inventory/manufacturer sites and runs the learning-depth
    curriculum for each applicable TRM type.
    """
    result = await db.execute(
        select(PowellTrainingConfig).where(PowellTrainingConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    if current_user.tenant_id != config.tenant_id and current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    from app.services.powell.powell_training_service import PowellTrainingService

    service = PowellTrainingService(db, config_id)
    result = await service.train_trm_per_site(
        trm_types=request.trm_types,
        phases=request.phases,
        epochs_override=request.epochs,
    )

    return result


@router.get("/configs/{config_id}/sites/{site_id}/progress")
async def get_site_progress(
    config_id: int,
    site_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
) -> Dict[str, Any]:
    """
    Get detailed training progress for a specific site.

    Returns per-TRM-type phase progress, data availability,
    and model evaluation metrics.
    """
    result = await db.execute(
        select(PowellTrainingConfig).where(PowellTrainingConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    if current_user.tenant_id != config.tenant_id and current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get site training configs
    result = await db.execute(
        select(TRMSiteTrainingConfig).where(
            TRMSiteTrainingConfig.powell_config_id == config_id,
            TRMSiteTrainingConfig.site_id == site_id,
        )
    )
    site_configs = result.scalars().all()

    if not site_configs:
        raise HTTPException(status_code=404, detail="No training configs for this site")

    # Count available data per TRM type
    from app.models.trm_training_data import TRMReplayBuffer
    from sqlalchemy import func

    trm_details = []
    for sc in site_configs:
        trm_type_val = sc.trm_type.value if hasattr(sc.trm_type, 'value') else sc.trm_type

        # Count replay buffer entries
        rb_result = await db.execute(
            select(func.count(TRMReplayBuffer.id)).where(
                TRMReplayBuffer.site_id == site_id,
                TRMReplayBuffer.trm_type == trm_type_val,
            )
        )
        replay_count = rb_result.scalar() or 0

        # Count expert entries
        expert_result = await db.execute(
            select(func.count(TRMReplayBuffer.id)).where(
                TRMReplayBuffer.site_id == site_id,
                TRMReplayBuffer.trm_type == trm_type_val,
                TRMReplayBuffer.is_expert == True,
            )
        )
        expert_count = expert_result.scalar() or 0

        phases_complete = sum(1 for p in [sc.phase1_status, sc.phase2_status, sc.phase3_status]
                             if p == PhaseStatus.COMPLETED.value)
        total_phases = sum(1 for p in [sc.phase1_status, sc.phase2_status, sc.phase3_status]
                          if p != PhaseStatus.NOT_APPLICABLE.value)

        trm_details.append({
            "trm_type": trm_type_val,
            "enabled": sc.enabled,
            "overall_progress": phases_complete / max(1, total_phases),
            "phase1": {
                "status": sc.phase1_status,
                "epochs": f"{sc.phase1_epochs_completed}/{sc.phase1_epochs_target}",
                "loss": sc.phase1_loss,
                "accuracy": sc.phase1_accuracy,
            },
            "phase2": {
                "status": sc.phase2_status,
                "epochs": f"{sc.phase2_epochs_completed}/{sc.phase2_epochs_target}",
                "loss": sc.phase2_loss,
                "accuracy": sc.phase2_accuracy,
                "expert_samples": sc.phase2_expert_samples,
                "min_required": sc.phase2_min_samples,
                "data_available": expert_count,
                "ready": expert_count >= sc.phase2_min_samples,
            },
            "phase3": {
                "status": sc.phase3_status,
                "epochs": f"{sc.phase3_epochs_completed}/{sc.phase3_epochs_target}",
                "loss": sc.phase3_loss,
                "reward_mean": sc.phase3_reward_mean,
                "outcome_samples": sc.phase3_outcome_samples,
                "min_required": sc.phase3_min_samples,
                "data_available": replay_count,
                "ready": replay_count >= sc.phase3_min_samples,
            },
            "model": {
                "version": sc.model_version,
                "checkpoint": sc.model_checkpoint_path,
                "eval_accuracy": sc.eval_accuracy,
                "vs_engine_improvement": sc.eval_vs_engine_improvement,
                "last_trained": sc.last_trained_at.isoformat() if sc.last_trained_at else None,
            },
        })

    return {
        "site_id": site_id,
        "site_name": site_configs[0].site_name if site_configs else "",
        "master_type": site_configs[0].master_type if site_configs else "",
        "trm_details": trm_details,
    }


# ============================================================================
# Synthetic Data Generation Endpoints
# ============================================================================

class SyntheticDataRequest(BaseModel):
    """Request schema for synthetic data generation."""
    num_days: int = Field(ge=30, le=730, default=365, description="Number of days to simulate")
    num_orders_per_day: int = Field(ge=10, le=500, default=50, description="Average orders per day")
    num_decisions_per_day: int = Field(ge=5, le=200, default=20, description="Average TRM decisions per day")
    seed: Optional[int] = Field(None, description="Random seed for reproducibility")


class SyntheticDataResponse(BaseModel):
    """Response schema for synthetic data generation."""
    success: bool
    message: str
    stats: Dict[str, int]
    duration_seconds: float


@router.post("/configs/{config_id}/generate-synthetic-data", response_model=SyntheticDataResponse)
async def generate_synthetic_trm_data(
    config_id: int,
    request: SyntheticDataRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Generate synthetic transactional data for TRM training.

    This creates realistic training data including:
    - **Forecasts**: Demand forecasts at different hierarchy levels with P10/P50/P90
    - **Inventory Levels**: Historical inventory snapshots (on-hand, in-transit, allocated)
    - **Orders**: Customer orders and purchase orders with full lifecycle
    - **TRM Decisions**: Expert planner decisions for each TRM type (ATP, Rebalancing, PO, Order Tracking)
    - **Outcomes**: What happened after each decision (for reward calculation)
    - **Replay Buffer**: (state, action, reward, next_state) tuples for RL training

    The data simulates realistic supply chain operations with:
    - Multiple demand patterns (seasonal, trending, promotional, etc.)
    - Lead time variability
    - Supplier reliability issues
    - Inventory imbalances
    - Order exceptions

    Only Group Admin can generate synthetic data.
    """
    import time
    from app.services.powell.synthetic_trm_data_generator import generate_synthetic_trm_data as generate_data

    # Get config
    result = await db.execute(
        select(PowellTrainingConfig).where(PowellTrainingConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    if current_user.tenant_id != config.tenant_id and current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    start_time = time.time()

    try:
        stats = await generate_data(
            db=db,
            config_id=config.config_id,
            tenant_id=config.tenant_id,
            num_days=request.num_days,
            num_orders_per_day=request.num_orders_per_day,
            num_decisions_per_day=request.num_decisions_per_day,
            seed=request.seed
        )

        duration = time.time() - start_time

        return SyntheticDataResponse(
            success=True,
            message=f"Generated {request.num_days} days of synthetic data",
            stats={
                "forecasts_created": stats.forecasts_created,
                "inventory_snapshots_created": stats.inventory_snapshots_created,
                "outbound_orders_created": stats.outbound_orders_created,
                "purchase_orders_created": stats.purchase_orders_created,
                "atp_decisions_created": stats.atp_decisions_created,
                "rebalancing_decisions_created": stats.rebalancing_decisions_created,
                "po_decisions_created": stats.po_decisions_created,
                "order_tracking_decisions_created": stats.order_tracking_decisions_created,
                "replay_buffer_entries_created": stats.replay_buffer_entries_created
            },
            duration_seconds=duration
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate synthetic data: {str(e)}"
        )


@router.get("/configs/{config_id}/training-data-stats")
async def get_training_data_stats(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
) -> Dict[str, Any]:
    """
    Get statistics about available training data for a configuration.

    Returns counts of:
    - Decision logs per TRM type
    - Replay buffer entries
    - Forecasts and inventory snapshots
    - Orders (inbound and outbound)
    """
    from app.models.trm_training_data import (
        ATPDecisionLog, RebalancingDecisionLog, PODecisionLog, OrderTrackingDecisionLog, TRMReplayBuffer
    )
    from app.models.sc_entities import Forecast, InvLevel, OutboundOrderLine
    from app.models.purchase_order import PurchaseOrder

    # Get config
    result = await db.execute(
        select(PowellTrainingConfig).where(PowellTrainingConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    if current_user.tenant_id != config.tenant_id and current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Count records
    stats = {}

    # Decision logs
    for model, name in [
        (ATPDecisionLog, "atp_decisions"),
        (RebalancingDecisionLog, "rebalancing_decisions"),
        (PODecisionLog, "po_decisions"),
        (OrderTrackingDecisionLog, "order_tracking_decisions")
    ]:
        result = await db.execute(
            select(func.count(model.id)).where(
                and_(model.tenant_id == config.tenant_id, model.config_id == config.config_id)
            )
        )
        stats[name] = result.scalar() or 0

    # Replay buffer
    result = await db.execute(
        select(func.count(TRMReplayBuffer.id)).where(
            and_(TRMReplayBuffer.tenant_id == config.tenant_id, TRMReplayBuffer.config_id == config.config_id)
        )
    )
    stats["replay_buffer_entries"] = result.scalar() or 0

    # Expert entries in replay buffer
    result = await db.execute(
        select(func.count(TRMReplayBuffer.id)).where(
            and_(
                TRMReplayBuffer.tenant_id == config.tenant_id,
                TRMReplayBuffer.config_id == config.config_id,
                TRMReplayBuffer.is_expert == True
            )
        )
    )
    stats["expert_entries"] = result.scalar() or 0

    # Forecasts
    result = await db.execute(
        select(func.count(Forecast.id)).where(Forecast.config_id == config.config_id)
    )
    stats["forecasts"] = result.scalar() or 0

    # Inventory levels
    result = await db.execute(
        select(func.count(InvLevel.id)).where(InvLevel.config_id == config.config_id)
    )
    stats["inventory_snapshots"] = result.scalar() or 0

    # Orders
    result = await db.execute(
        select(func.count(OutboundOrderLine.id)).where(OutboundOrderLine.config_id == config.config_id)
    )
    stats["outbound_orders"] = result.scalar() or 0

    result = await db.execute(
        select(func.count(PurchaseOrder.id)).where(PurchaseOrder.config_id == config.config_id)
    )
    stats["purchase_orders"] = result.scalar() or 0

    # Total training samples
    stats["total_samples"] = (
        stats["atp_decisions"] + stats["rebalancing_decisions"] +
        stats["po_decisions"] + stats["order_tracking_decisions"]
    )

    # Replay buffer by TRM type
    replay_by_type = {}
    for trm_type in TRMType:
        result = await db.execute(
            select(func.count(TRMReplayBuffer.id)).where(
                and_(
                    TRMReplayBuffer.tenant_id == config.tenant_id,
                    TRMReplayBuffer.config_id == config.config_id,
                    TRMReplayBuffer.trm_type == trm_type.value
                )
            )
        )
        replay_by_type[trm_type.value] = result.scalar() or 0
    stats["replay_buffer_by_type"] = replay_by_type

    return stats
