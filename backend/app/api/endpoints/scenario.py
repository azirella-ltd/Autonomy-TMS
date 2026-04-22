from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.db.session import get_sync_db
from app.models.scenario import Scenario as ScenarioModel
from app.models.scenario_user import ScenarioUser
from app.models.supply_chain import ScenarioPeriod, ScenarioUserPeriod
from app.schemas.scenario import (
    ScenarioCreate, ScenarioUpdate,
    ScenarioUserCreate, ScenarioUserUpdate, ScenarioUser as ScenarioUserSchema,
    ScenarioState, OrderCreate, OrderResponse, ScenarioUserPeriod as ScenarioUserPeriodSchema,
    ScenarioPeriod as ScenarioPeriodSchema,
    DemandPattern
)
from app.core.demand_patterns import normalize_demand_pattern, DEFAULT_DEMAND_PATTERN
from app.services.llm_agent import AutonomyLLMError

class ScenarioUserResponse(ScenarioUserSchema):
    """Response model for scenario_user data."""
    class Config:
        from_attributes = True

class ScenarioUserPeriodResponse(ScenarioUserPeriodSchema):
    """Response model for scenario_user period data."""
    class Config:
        from_attributes = True

class ScenarioPeriodResponse(ScenarioPeriodSchema):
    """Response model for scenario period data."""
    class Config:
        from_attributes = True
from pydantic import BaseModel
from typing import Dict, Any

class ScenarioResponse(BaseModel):
    id: int
    name: str
    status: str
    current_period: int
    max_periods: int
    demand_pattern: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm(cls, obj):
        # Safely handle demand_pattern conversion
        try:
            if hasattr(obj, 'demand_pattern') and obj.demand_pattern is not None:
                if isinstance(obj.demand_pattern, dict):
                    demand_pattern = dict(obj.demand_pattern)
                    demand_pattern.pop('model_config', None)
                elif hasattr(obj.demand_pattern, '__dict__'):
                    demand_pattern = {
                        k: v
                        for k, v in obj.demand_pattern.__dict__.items()
                        if not k.startswith('_') and k != 'model_config'
                    }
                else:
                    import json

                    try:
                        demand_pattern = json.loads(obj.demand_pattern) if isinstance(obj.demand_pattern, str) else {}
                        if isinstance(demand_pattern, dict):
                            demand_pattern.pop('model_config', None)
                    except json.JSONDecodeError:
                        demand_pattern = DEFAULT_DEMAND_PATTERN.copy()
            else:
                demand_pattern = DEFAULT_DEMAND_PATTERN.copy()

            normalized = normalize_demand_pattern(demand_pattern)

            clean_demand_pattern = {
                'type': str(normalized.get('type', 'classic')),
                'params': dict(normalized.get('params', {})) if isinstance(normalized.get('params', {}), dict) else {},
            }

            # Convert SQLAlchemy model to dict
            data = {
                'id': int(obj.id),
                'name': str(obj.name),
                'status': obj.status.value if hasattr(obj.status, 'value') else str(obj.status),
                'current_period': int(obj.current_period) if obj.current_period is not None else 0,
                'max_periods': int(obj.max_periods) if obj.max_periods is not None else 20,
                'demand_pattern': clean_demand_pattern,
                'created_at': obj.created_at,
                'updated_at': obj.updated_at
            }

            return cls(**data)

        except Exception as e:
            print(f"Error in ScenarioResponse.from_orm: {e}")
            import traceback
            traceback.print_exc()

            # Return a minimal valid response if something goes wrong
            return cls(
                id=getattr(obj, 'id', 0),
                name=getattr(obj, 'name', 'Unknown'),
                status=str(getattr(obj, 'status', 'UNKNOWN')),
                current_period=int(getattr(obj, 'current_period', 0)),
                max_periods=int(getattr(obj, 'max_periods', 20)),
                demand_pattern={
                    'type': DEFAULT_DEMAND_PATTERN['type'],
                    'params': DEFAULT_DEMAND_PATTERN['params'].copy(),
                },
                created_at=getattr(obj, 'created_at', None),
                updated_at=getattr(obj, 'updated_at', None)
            )
from app.services.mixed_scenario_service import MixedScenarioService
from app.core.security import get_current_user

router = APIRouter()

# Scenario endpoints
@router.post("/", response_model=ScenarioResponse, status_code=status.HTTP_201_CREATED)
def create_scenario(
    scenario_in: ScenarioCreate,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new scenario.
    """
    scenario_service = MixedScenarioService(db)
    scenario = scenario_service.create_game(scenario_in)
    return ScenarioResponse.from_orm(scenario)

@router.get("/")
async def list_scenarios(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all scenarios - DEBUG VERSION
    """
    try:
        print("Fetching scenarios from database...")
        # Get all scenarios from the database
        scenarios = db.query(ScenarioModel).offset(skip).limit(limit).all()
        print(f"Found {len(scenarios)} scenarios in the database")

        if not scenarios:
            print("No scenarios found in the database")
            return []

        # Convert each scenario to a simple dictionary
        response = []
        for scenario in scenarios:
            try:
                # Create a simple dictionary for the scenario
                scenario_dict = {
                    'id': scenario.id,
                    'name': scenario.name,
                    'status': scenario.status.value if hasattr(scenario.status, 'value') else str(scenario.status),
                    'current_period': scenario.current_period,
                    'max_periods': scenario.max_periods,
                    'created_at': scenario.created_at.isoformat() if scenario.created_at else None,
                    'updated_at': scenario.updated_at.isoformat() if scenario.updated_at else None
                }

                # Handle demand_pattern
                if hasattr(scenario, 'demand_pattern') and scenario.demand_pattern is not None:
                    if isinstance(scenario.demand_pattern, dict):
                        demand_pattern = dict(scenario.demand_pattern)
                        demand_pattern.pop('model_config', None)
                    elif hasattr(scenario.demand_pattern, '__dict__'):
                        demand_pattern = {
                            k: v
                            for k, v in scenario.demand_pattern.__dict__.items()
                            if not k.startswith('_') and k != 'model_config'
                        }
                    else:
                        import json

                        try:
                            demand_pattern = json.loads(scenario.demand_pattern) if isinstance(scenario.demand_pattern, str) else {}
                            if isinstance(demand_pattern, dict):
                                demand_pattern.pop('model_config', None)
                        except json.JSONDecodeError:
                            demand_pattern = DEFAULT_DEMAND_PATTERN.copy()
                else:
                    demand_pattern = DEFAULT_DEMAND_PATTERN.copy()

                scenario_dict['demand_pattern'] = normalize_demand_pattern(demand_pattern)
                response.append(scenario_dict)

            except Exception as e:
                print(f"Error processing scenario {getattr(scenario, 'id', 'unknown')}: {str(e)}")
                continue

        print(f"Successfully processed {len(response)} out of {len(scenarios)} scenarios")

        # Print the raw response for debugging
        import json
        print("\nRaw response data:")
        print(json.dumps(response, indent=2, default=str))

        return response

    except Exception as e:
        print(f"Error in list_scenarios endpoint: {str(e)}")
        import traceback
        traceback.print_exc()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing scenarios: {str(e)}"
        )

@router.get("/{scenario_id}", response_model=ScenarioResponse)
def get_scenario(
    scenario_id: int,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a scenario by ID.
    """
    scenario = db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found"
        )
    return ScenarioResponse.from_orm(scenario)

@router.put("/{scenario_id}", response_model=ScenarioResponse)
def update_scenario(
    scenario_id: int,
    scenario_in: ScenarioUpdate,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update a scenario.
    """
    scenario = db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found"
        )

    update_data = scenario_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(scenario, field, value)

    db.commit()
    db.refresh(scenario)
    return ScenarioResponse.from_orm(scenario)

@router.post("/{scenario_id}/start", response_model=ScenarioResponse)
def start_scenario(
    scenario_id: int,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Start a scenario that is in the 'created' state.
    """
    scenario_service = MixedScenarioService(db)
    try:
        scenario = scenario_service.start_game(scenario_id)
        return ScenarioResponse.from_orm(scenario)
    except AutonomyLLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/{scenario_id}/state", response_model=ScenarioState)
def get_scenario_state(
    scenario_id: int,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get the current state of a scenario.
    """
    scenario_service = MixedScenarioService(db)
    try:
        return scenario_service.get_game_state(scenario_id)
    except AutonomyLLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

# ScenarioUser endpoints
@router.post("/{scenario_id}/scenario_users", response_model=ScenarioUserResponse, status_code=status.HTTP_201_CREATED)
def add_participant(
    scenario_id: int,
    participant_in: ScenarioUserCreate,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Add a scenario_user to a scenario.
    """
    scenario_service = MixedScenarioService(db)
    try:
        scenario_user = scenario_service.add_scenario_user(scenario_id, participant_in)
        return ScenarioUserResponse.model_validate(scenario_user)
    except AutonomyLLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/{scenario_id}/scenario_users", response_model=List[ScenarioUserResponse])
def list_participants(
    scenario_id: int,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all scenario_users in a scenario.
    """
    scenario_users = db.query(ScenarioUser).filter(ScenarioUser.scenario_id == scenario_id).all()
    return [ScenarioUserResponse.model_validate(scenario_user) for scenario_user in scenario_users]

@router.get("/{scenario_id}/scenario_users/{scenario_user_id}", response_model=ScenarioUserResponse)
def get_participant(
    scenario_id: int,
    scenario_user_id: int,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a scenario_user by ID.
    """
    scenario_user = db.query(ScenarioUser).filter(
        ScenarioUser.id == scenario_user_id,
        ScenarioUser.scenario_id == scenario_id
    ).first()

    if not scenario_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ScenarioUser not found"
        )

    return ScenarioUserResponse.from_orm(scenario_user)

# Order endpoints
@router.post("/scenarios/{scenario_id}/scenario_users/{scenario_user_id}/orders", response_model=ScenarioUserPeriodResponse)
async def submit_order(
    scenario_id: int,
    scenario_user_id: int,
    order_in: OrderCreate,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Submit or update an order for the current round.

    ScenarioUsers can submit or update their order for the current round until the round ends.
    If the round time expires, any unsubmitted orders will be set to zero.
    """
    scenario_service = MixedScenarioService(db)
    try:
        participant_round = scenario_service.submit_order(scenario_id, scenario_user_id, order_in.quantity, order_in.comment)
        return participant_round
    except AutonomyLLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# Round endpoints
@router.get("/{scenario_id}/rounds", response_model=List[ScenarioPeriodResponse])
def list_rounds(
    scenario_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all rounds for a scenario.
    """
    rounds = db.query(ScenarioPeriod).filter(ScenarioPeriod.scenario_id == scenario_id).all()
    return [ScenarioPeriodResponse.model_validate(round) for round in rounds]

@router.get("/{scenario_id}/rounds/{round_number}", response_model=ScenarioPeriodResponse)
def get_round(
    scenario_id: int,
    round_number: int,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific round for a scenario.
    """
    scenario_round = db.query(ScenarioPeriod).filter(
        ScenarioPeriod.scenario_id == scenario_id,
        ScenarioPeriod.round_number == round_number
    ).first()

    if not scenario_round:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Round not found"
        )

    return ScenarioPeriodResponse.model_validate(scenario_round)

@router.get("/{scenario_id}/current-round", response_model=ScenarioPeriodResponse)
def get_current_period(
    scenario_id: int,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get the current round for a scenario.
    """
    scenario = db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found"
        )

    scenario_round = db.query(ScenarioPeriod).filter(
        ScenarioPeriod.scenario_id == scenario_id,
        ScenarioPeriod.round_number == scenario.current_period
    ).first()

    if not scenario_round:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Current round not found"
        )

    return ScenarioPeriodResponse.model_validate(scenario_round)

@router.get("/scenarios/{scenario_id}/rounds/current/status", response_model=Dict[str, Any])
async def get_round_submission_status(
    scenario_id: int,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get the submission status of the current round.

    Returns:
        A dictionary with submission status and details
    """
    scenario = db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    # Get current round
    current_period = db.query(ScenarioPeriod).filter(
        ScenarioPeriod.scenario_id == scenario_id,
        ScenarioPeriod.round_number == scenario.current_period
    ).first()

    if not current_period:
        raise HTTPException(status_code=404, detail="Current round not found")

    # Get all scenario_users in the scenario
    scenario_users = db.query(ScenarioUser).filter(ScenarioUser.scenario_id == scenario_id).all()
    total_participants = len(scenario_users)

    # Get scenario_users who have submitted for the current round
    submitted_participants = db.query(ScenarioUserPeriod).filter(
        ScenarioUserPeriod.round_id == current_period.id
    ).all()
    submitted_count = len(submitted_participants)

    # Get list of scenario_users who haven't submitted yet
    submitted_scenario_user_ids = [p.scenario_user_id for p in submitted_participants]
    pending_participants = [p for p in scenario_users if p.id not in submitted_scenario_user_ids]

    return {
        "scenario_id": scenario_id,
        "round_number": current_period.round_number,
        "is_completed": current_period.is_completed,
        "total_participants": total_participants,
        "submitted_count": submitted_count,
        "pending_count": total_participants - submitted_count,
        "pending_participants": [{"id": p.id, "name": p.name, "role": p.role} for p in pending_participants],
        "all_submitted": current_period.is_completed
    }

# ScenarioUser Round endpoints
@router.get("/{scenario_id}/scenario_users/{scenario_user_id}/current-round", response_model=ScenarioUserPeriodResponse)
def get_participant_current_period(
    scenario_id: int,
    scenario_user_id: int,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get the current round for a scenario_user.
    """
    # Get the current scenario round
    scenario = db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found"
        )

    current_period = db.query(ScenarioPeriod).filter(
        ScenarioPeriod.scenario_id == scenario_id,
        ScenarioPeriod.round_number == scenario.current_period
    ).first()

    if not current_period:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Current round not found"
        )

    # Get the scenario_user's round
    participant_round = db.query(ScenarioUserPeriod).filter(
        ScenarioUserPeriod.scenario_user_id == scenario_user_id,
        ScenarioUserPeriod.round_id == current_period.id
    ).first()

    if not participant_round:
        # If the scenario_user hasn't taken their turn yet, create a new scenario_user round
        participant_round = ScenarioUserPeriod(
            scenario_user_id=scenario_user_id,
            round_id=current_period.id,
            order_placed=0,  # Default to 0, will be updated when order is placed
            order_received=0,
            inventory_before=0,
            inventory_after=0,
            backorders_before=0,
            backorders_after=0,
            holding_cost=0.0,
            backorder_cost=0.0,
            total_cost=0.0
        )
        db.add(participant_round)
        db.commit()
        db.refresh(participant_round)

    return participant_round
