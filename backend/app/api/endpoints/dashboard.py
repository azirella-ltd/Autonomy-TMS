from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List

from ... import models, schemas
from ...crud import crud_dashboard as crud
from ...db.session import get_sync_db as get_db
from ...core.security import get_current_active_user
from ...models.scenario_user import ScenarioUser
from ...models.scenario import Scenario, ScenarioStatus

# Router for dashboard endpoints
dashboard_router = APIRouter()

@dashboard_router.get("/user-scenarios")
async def get_user_scenarios(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get all active scenarios for the current user.
    Returns a list of scenarios with basic info (id, name, status, role).
    """
    # Get all scenarios where user is a scenario_user
    scenarios = (
        db.query(Scenario)
        .join(ScenarioUser, ScenarioUser.scenario_id == Scenario.id)
        .filter(ScenarioUser.user_id == current_user.id)
        .all()
    )

    if not scenarios:
        return []

    # Get scenario_user roles for each scenario
    result = []
    for scenario in scenarios:
        scenario_user = (
            db.query(ScenarioUser)
            .filter(
                ScenarioUser.user_id == current_user.id,
                ScenarioUser.scenario_id == scenario.id
            )
            .first()
        )

        if scenario_user:
            role_value = getattr(scenario_user.role, "name", str(scenario_user.role)).upper()
            result.append({
                "id": scenario.id,
                "name": scenario.name,
                "status": scenario.status.value if hasattr(scenario.status, 'value') else str(scenario.status),
                "role": role_value,
                "current_period": scenario.current_period,
                "max_periods": scenario.max_periods,
                "created_at": scenario.created_at.isoformat() if scenario.created_at else None
            })

    return result

@dashboard_router.get("/human-dashboard", response_model=schemas.DashboardResponse)
async def get_human_dashboard(
    scenario_id: Optional[int] = Query(None, description="Specific scenario ID to view. If not provided, returns the most recent active scenario."),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get dashboard data for a human scenario_user.
    Returns scenario info, scenario_user role, current period, and metrics.

    If scenario_id is provided, returns data for that specific scenario.
    Otherwise, returns data for the most recent active scenario.
    """
    # Get active scenario for the user (either specific scenario_id or most recent)
    if scenario_id:
        active_scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
        if not active_scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario with ID {scenario_id} not found"
            )
        # Verify user is a scenario_user in this scenario
        scenario_user_check = (
            db.query(ScenarioUser)
            .filter(
                ScenarioUser.user_id == current_user.id,
                ScenarioUser.scenario_id == scenario_id
            )
            .first()
        )
        if not scenario_user_check:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a scenario_user in this scenario"
            )
    else:
        active_scenario = crud.get_active_scenario_for_user(db, user_id=current_user.id)
        if not active_scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active scenario found for the user"
            )
    
    # Get scenario_user's role in the scenario
    scenario_user = (
        db.query(ScenarioUser)
        .filter(
            ScenarioUser.user_id == current_user.id,
            ScenarioUser.scenario_id == active_scenario.id,
        )
        .first()
    )

    if not scenario_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ScenarioUser data not found for this scenario"
        )
    
    # Get scenario metrics
    metrics = crud.get_participant_metrics(db, scenario_user_id=scenario_user.id, scenario_id=active_scenario.id)
    
    # Get time series data for the scenario_user
    role_value = getattr(scenario_user.role, "name", str(scenario_user.role)).upper()

    time_series = crud.get_time_series_metrics(
        db,
        scenario_user_id=scenario_user.id,
        scenario_id=active_scenario.id,
        role=role_value,
    )

    # Convert time series data to TimeSeriesPoint models
    time_series_points = [
        schemas.TimeSeriesPoint(
            week=point.get('week', 0),
            inventory=point.get('inventory', 0),
            order=point.get('order', 0),
            cost=point.get('cost', 0),
            backlog=point.get('backlog', 0),
            demand=point.get('demand'),
            supply=point.get('supply'),
            reason=point.get('reason'),
        )
        for point in time_series
    ]

    # Create the response model
    return schemas.DashboardResponse(
        scenario_id=active_scenario.id,
        scenario_user_id=scenario_user.id,
        scenario_name=active_scenario.name,
        current_period=active_scenario.current_period,
        max_periods=active_scenario.max_periods,
        participant_role=role_value,
        metrics=schemas.ScenarioUserMetrics(**metrics),
        time_series=time_series_points,
        last_updated=datetime.utcnow().isoformat()
    )
