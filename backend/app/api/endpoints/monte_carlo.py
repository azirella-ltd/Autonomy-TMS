"""
Monte Carlo Simulation API Endpoints

Provides endpoints for:
- Creating and managing Monte Carlo simulation runs
- Querying simulation results and statistics
- Retrieving time-series data with confidence bands
- Viewing risk alerts
"""

from typing import List, Optional
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from pydantic import BaseModel, Field

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.monte_carlo import (
    MonteCarloRun, MonteCarloScenario, MonteCarloTimeSeries,
    MonteCarloRiskAlert, SimulationStatus
)
from app.models.supply_chain_config import SupplyChainConfig
from app.models.mps import MPSPlan
from app.services.monte_carlo.engine import MonteCarloEngine


# ============================================================================
# Request/Response Schemas
# ============================================================================

class MonteCarloRunCreate(BaseModel):
    """Request schema for creating a Monte Carlo run"""
    name: str = Field(..., description="Simulation run name")
    description: Optional[str] = Field(None, description="Run description")
    supply_chain_config_id: int = Field(..., description="Supply chain configuration ID")
    mps_plan_id: Optional[int] = Field(None, description="Optional MPS plan ID to simulate")
    scenario_id: Optional[int] = Field(None, description="Optional scenario ID for integration")
    group_id: int = Field(..., description="Group ID")

    num_scenarios: int = Field(1000, description="Number of scenarios to run", ge=100, le=10000)
    random_seed: Optional[int] = Field(None, description="Random seed for reproducibility")

    planning_horizon_weeks: int = Field(52, description="Planning horizon in weeks", ge=4, le=104)
    start_date: Optional[date] = Field(None, description="Simulation start date (defaults to today)")


class MonteCarloRunResponse(BaseModel):
    """Response schema for Monte Carlo run"""
    id: int
    name: str
    description: Optional[str]
    supply_chain_config_id: int
    config_name: Optional[str]
    mps_plan_id: Optional[int]
    scenario_id: Optional[int]
    group_id: int

    num_scenarios: int
    random_seed: Optional[int]

    start_date: datetime
    end_date: datetime
    planning_horizon_weeks: int

    status: str
    progress_percent: float
    scenarios_completed: int

    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    execution_time_seconds: Optional[float]

    error_message: Optional[str]
    summary_statistics: Optional[dict]
    risk_metrics: Optional[dict]

    created_by: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MonteCarloScenarioResponse(BaseModel):
    """Response schema for individual scenario"""
    id: int
    run_id: int
    scenario_number: int
    sampled_inputs: dict
    total_cost: Optional[float]
    holding_cost: Optional[float]
    backlog_cost: Optional[float]
    ordering_cost: Optional[float]
    service_level: Optional[float]
    final_inventory: Optional[float]
    final_backlog: Optional[float]
    max_inventory: Optional[float]
    max_backlog: Optional[float]
    had_stockout: bool
    had_overstock: bool
    had_capacity_violation: bool
    created_at: datetime

    class Config:
        from_attributes = True


class MonteCarloTimeSeriesResponse(BaseModel):
    """Response schema for time-series data"""
    id: int
    run_id: int
    product_id: Optional[int]
    site_id: Optional[int]
    period_week: int
    period_date: datetime
    metric_name: str

    mean_value: Optional[float]
    median_value: Optional[float]
    std_dev: Optional[float]

    p5_value: Optional[float]
    p10_value: Optional[float]
    p25_value: Optional[float]
    p75_value: Optional[float]
    p90_value: Optional[float]
    p95_value: Optional[float]

    min_value: Optional[float]
    max_value: Optional[float]

    class Config:
        from_attributes = True


class MonteCarloRiskAlertResponse(BaseModel):
    """Response schema for risk alert"""
    id: int
    run_id: int
    alert_type: str
    severity: str
    product_id: Optional[int]
    site_id: Optional[int]
    period_week: Optional[int]
    period_date: Optional[datetime]
    title: str
    description: Optional[str]
    probability: Optional[float]
    expected_impact: Optional[float]
    recommendation: Optional[str]
    acknowledged: bool
    acknowledged_by: Optional[int]
    acknowledged_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class TimeSeriesWithConfidenceBands(BaseModel):
    """Time-series data formatted for charting with confidence bands"""
    metric_name: str
    product_id: Optional[int]
    site_id: Optional[int]
    data_points: List[dict]  # [{week, date, mean, p5, p25, p75, p95, ...}]


# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(prefix="/monte-carlo", tags=["Monte Carlo Simulation"])


# ============================================================================
# Helper Functions
# ============================================================================

def check_monte_carlo_permission(user: User, action: str) -> None:
    """Check if user has permission for Monte Carlo actions"""
    required_permissions = {
        "view": "view_analytics",
        "manage": "manage_analytics",
    }

    permission = required_permissions.get(action)
    if not permission:
        return

    has_permission = False
    for role in user.roles:
        for capability in role.capabilities:
            if capability.key == permission:
                has_permission = True
                break
        if has_permission:
            break

    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have permission to {action} Monte Carlo simulations"
        )


async def run_monte_carlo_simulation(
    run_id: int,
    config_id: int,
    group_id: int,
    num_scenarios: int,
    random_seed: Optional[int],
    start_date: date,
    planning_horizon_weeks: int
):
    """Background task to run Monte Carlo simulation"""
    engine = MonteCarloEngine(
        run_id=run_id,
        config_id=config_id,
        group_id=group_id,
        num_scenarios=num_scenarios,
        random_seed=random_seed
    )

    await engine.run_simulation(
        start_date=start_date,
        planning_horizon_weeks=planning_horizon_weeks
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/runs", response_model=MonteCarloRunResponse, status_code=status.HTTP_201_CREATED)
async def create_monte_carlo_run(
    run_create: MonteCarloRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new Monte Carlo simulation run

    The simulation will be executed in the background.
    Poll the run status to check for completion.
    """
    check_monte_carlo_permission(current_user, "manage")

    # Validate config exists
    config = db.get(SupplyChainConfig, run_create.supply_chain_config_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supply chain configuration {run_create.supply_chain_config_id} not found"
        )

    # Validate MPS plan if provided
    if run_create.mps_plan_id:
        mps_plan = db.get(MPSPlan, run_create.mps_plan_id)
        if not mps_plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"MPS plan {run_create.mps_plan_id} not found"
            )

    # Set start date
    start_date = run_create.start_date or date.today()
    end_date = start_date + timedelta(weeks=run_create.planning_horizon_weeks)

    # Create run record
    run = MonteCarloRun(
        supply_chain_config_id=run_create.supply_chain_config_id,
        mps_plan_id=run_create.mps_plan_id,
        scenario_id=run_create.scenario_id,
        group_id=run_create.group_id,
        name=run_create.name,
        description=run_create.description,
        num_scenarios=run_create.num_scenarios,
        random_seed=run_create.random_seed,
        start_date=start_date,
        end_date=end_date,
        planning_horizon_weeks=run_create.planning_horizon_weeks,
        status=SimulationStatus.QUEUED,
        created_by=current_user.id,
    )

    db.add(run)
    db.commit()
    db.refresh(run)

    # Schedule background simulation
    background_tasks.add_task(
        run_monte_carlo_simulation,
        run_id=run.id,
        config_id=run_create.supply_chain_config_id,
        group_id=run_create.group_id,
        num_scenarios=run_create.num_scenarios,
        random_seed=run_create.random_seed,
        start_date=start_date,
        planning_horizon_weeks=run_create.planning_horizon_weeks
    )

    # Format response
    config = db.get(SupplyChainConfig, run.supply_chain_config_id)
    response = MonteCarloRunResponse(
        **run.__dict__,
        config_name=config.name if config else None,
        status=run.status.value if isinstance(run.status, SimulationStatus) else run.status
    )

    return response


@router.get("/runs", response_model=List[MonteCarloRunResponse])
async def list_monte_carlo_runs(
    group_id: Optional[int] = None,
    config_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List Monte Carlo simulation runs with optional filters"""
    check_monte_carlo_permission(current_user, "view")

    query = select(MonteCarloRun).order_by(desc(MonteCarloRun.created_at))

    if group_id:
        query = query.filter(MonteCarloRun.group_id == group_id)
    if config_id:
        query = query.filter(MonteCarloRun.supply_chain_config_id == config_id)
    if status_filter:
        query = query.filter(MonteCarloRun.status == status_filter)

    query = query.limit(limit)

    result = db.execute(query)
    runs = result.scalars().all()

    # Format responses
    responses = []
    for run in runs:
        config = db.get(SupplyChainConfig, run.supply_chain_config_id)
        responses.append(MonteCarloRunResponse(
            **run.__dict__,
            config_name=config.name if config else None,
            status=run.status.value if isinstance(run.status, SimulationStatus) else run.status
        ))

    return responses


@router.get("/runs/{run_id}", response_model=MonteCarloRunResponse)
async def get_monte_carlo_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get Monte Carlo run details"""
    check_monte_carlo_permission(current_user, "view")

    run = db.get(MonteCarloRun, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monte Carlo run {run_id} not found"
        )

    config = db.get(SupplyChainConfig, run.supply_chain_config_id)

    return MonteCarloRunResponse(
        **run.__dict__,
        config_name=config.name if config else None,
        status=run.status.value if isinstance(run.status, SimulationStatus) else run.status
    )


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monte_carlo_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a Monte Carlo run (only allowed for QUEUED or FAILED runs)"""
    check_monte_carlo_permission(current_user, "manage")

    run = db.get(MonteCarloRun, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monte Carlo run {run_id} not found"
        )

    # Only allow deletion of queued or failed runs
    if run.status not in [SimulationStatus.QUEUED, SimulationStatus.FAILED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete run with status {run.status}. Only QUEUED or FAILED runs can be deleted."
        )

    db.delete(run)
    db.commit()


@router.post("/runs/{run_id}/cancel", response_model=MonteCarloRunResponse)
async def cancel_monte_carlo_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel a running Monte Carlo simulation"""
    check_monte_carlo_permission(current_user, "manage")

    run = db.get(MonteCarloRun, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monte Carlo run {run_id} not found"
        )

    if run.status not in [SimulationStatus.QUEUED, SimulationStatus.RUNNING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel run with status {run.status}"
        )

    run.status = SimulationStatus.CANCELLED
    run.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(run)

    config = db.get(SupplyChainConfig, run.supply_chain_config_id)

    return MonteCarloRunResponse(
        **run.__dict__,
        config_name=config.name if config else None,
        status=run.status.value if isinstance(run.status, SimulationStatus) else run.status
    )


@router.get("/runs/{run_id}/scenarios", response_model=List[MonteCarloScenarioResponse])
async def get_scenarios(
    run_id: int,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get scenarios for a Monte Carlo run"""
    check_monte_carlo_permission(current_user, "view")

    # Verify run exists
    run = db.get(MonteCarloRun, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monte Carlo run {run_id} not found"
        )

    query = select(MonteCarloScenario)\
        .filter(MonteCarloScenario.run_id == run_id)\
        .order_by(MonteCarloScenario.scenario_number)\
        .limit(limit)\
        .offset(offset)

    result = db.execute(query)
    scenarios = result.scalars().all()

    return [MonteCarloScenarioResponse(**s.__dict__) for s in scenarios]


@router.get("/runs/{run_id}/time-series", response_model=List[TimeSeriesWithConfidenceBands])
async def get_time_series_data(
    run_id: int,
    metric_names: Optional[str] = None,  # Comma-separated list
    product_id: Optional[int] = None,
    site_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get time-series data with confidence bands for charting

    Returns data grouped by metric, suitable for plotting with P5-P95 bands.
    """
    check_monte_carlo_permission(current_user, "view")

    # Verify run exists
    run = db.get(MonteCarloRun, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monte Carlo run {run_id} not found"
        )

    # Build query
    query = select(MonteCarloTimeSeries).filter(MonteCarloTimeSeries.run_id == run_id)

    if metric_names:
        metrics = [m.strip() for m in metric_names.split(",")]
        query = query.filter(MonteCarloTimeSeries.metric_name.in_(metrics))

    if product_id:
        query = query.filter(MonteCarloTimeSeries.product_id == product_id)

    if site_id:
        query = query.filter(MonteCarloTimeSeries.site_id == site_id)

    query = query.order_by(
        MonteCarloTimeSeries.metric_name,
        MonteCarloTimeSeries.product_id,
        MonteCarloTimeSeries.site_id,
        MonteCarloTimeSeries.period_week
    )

    result = db.execute(query)
    time_series = result.scalars().all()

    # Group by metric, product, site
    grouped = {}
    for ts in time_series:
        key = (ts.metric_name, ts.product_id, ts.site_id)
        if key not in grouped:
            grouped[key] = []

        grouped[key].append({
            "week": ts.period_week,
            "date": ts.period_date.isoformat(),
            "mean": ts.mean_value,
            "median": ts.median_value,
            "std_dev": ts.std_dev,
            "p5": ts.p5_value,
            "p10": ts.p10_value,
            "p25": ts.p25_value,
            "p75": ts.p75_value,
            "p90": ts.p90_value,
            "p95": ts.p95_value,
            "min": ts.min_value,
            "max": ts.max_value,
        })

    # Format response
    responses = []
    for (metric_name, product_id, site_id), data_points in grouped.items():
        responses.append(TimeSeriesWithConfidenceBands(
            metric_name=metric_name,
            product_id=product_id,
            site_id=site_id,
            data_points=data_points
        ))

    return responses


@router.get("/runs/{run_id}/risk-alerts", response_model=List[MonteCarloRiskAlertResponse])
async def get_risk_alerts(
    run_id: int,
    acknowledged: Optional[bool] = None,
    severity: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get risk alerts for a Monte Carlo run"""
    check_monte_carlo_permission(current_user, "view")

    # Verify run exists
    run = db.get(MonteCarloRun, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monte Carlo run {run_id} not found"
        )

    query = select(MonteCarloRiskAlert)\
        .filter(MonteCarloRiskAlert.run_id == run_id)\
        .order_by(desc(MonteCarloRiskAlert.created_at))

    if acknowledged is not None:
        query = query.filter(MonteCarloRiskAlert.acknowledged == acknowledged)

    if severity:
        query = query.filter(MonteCarloRiskAlert.severity == severity)

    result = db.execute(query)
    alerts = result.scalars().all()

    return [MonteCarloRiskAlertResponse(**a.__dict__) for a in alerts]


@router.post("/runs/{run_id}/risk-alerts/{alert_id}/acknowledge", response_model=MonteCarloRiskAlertResponse)
async def acknowledge_risk_alert(
    run_id: int,
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Acknowledge a risk alert"""
    check_monte_carlo_permission(current_user, "manage")

    alert = db.get(MonteCarloRiskAlert, alert_id)
    if not alert or alert.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Risk alert {alert_id} not found for run {run_id}"
        )

    alert.acknowledged = True
    alert.acknowledged_by = current_user.id
    alert.acknowledged_at = datetime.utcnow()

    db.commit()
    db.refresh(alert)

    return MonteCarloRiskAlertResponse(**alert.__dict__)
