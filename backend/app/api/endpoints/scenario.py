from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.db.session import get_sync_db
from app.models.scenario import Scenario as ScenarioModel
from app.models.participant import Participant
from app.models.supply_chain import ScenarioRound, ParticipantRound
from app.schemas.scenario import (
    ScenarioCreate, ScenarioUpdate,
    ParticipantCreate, ParticipantUpdate, Participant as ParticipantSchema,
    ScenarioState, OrderCreate, OrderResponse, ParticipantPeriod as ParticipantPeriodSchema,
    ScenarioPeriod as ScenarioPeriodSchema,
    DemandPattern
)
from app.core.demand_patterns import normalize_demand_pattern, DEFAULT_DEMAND_PATTERN
from app.services.llm_agent import AutonomyLLMError

class ParticipantResponse(ParticipantSchema):
    """Response model for participant data."""
    class Config:
        from_attributes = True

class ParticipantPeriodResponse(ParticipantPeriodSchema):
    """Response model for participant period data."""
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
    current_round: int
    max_rounds: int
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
                'current_round': int(obj.current_round) if obj.current_round is not None else 0,
                'max_rounds': int(obj.max_rounds) if obj.max_rounds is not None else 20,
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
                current_round=int(getattr(obj, 'current_round', 0)),
                max_rounds=int(getattr(obj, 'max_rounds', 20)),
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
                    'current_round': scenario.current_round,
                    'max_rounds': scenario.max_rounds,
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

# Participant endpoints
@router.post("/{scenario_id}/participants", response_model=ParticipantResponse, status_code=status.HTTP_201_CREATED)
def add_participant(
    scenario_id: int,
    participant_in: ParticipantCreate,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Add a participant to a scenario.
    """
    scenario_service = MixedScenarioService(db)
    try:
        participant = scenario_service.add_player(scenario_id, participant_in)
        return ParticipantResponse.model_validate(participant)
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

@router.get("/{scenario_id}/participants", response_model=List[ParticipantResponse])
def list_participants(
    scenario_id: int,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all participants in a scenario.
    """
    participants = db.query(Participant).filter(Participant.scenario_id == scenario_id).all()
    return [ParticipantResponse.model_validate(participant) for participant in participants]

@router.get("/{scenario_id}/participants/{participant_id}", response_model=ParticipantResponse)
def get_participant(
    scenario_id: int,
    participant_id: int,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a participant by ID.
    """
    participant = db.query(Participant).filter(
        Participant.id == participant_id,
        Participant.scenario_id == scenario_id
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participant not found"
        )

    return ParticipantResponse.from_orm(participant)

# Order endpoints
@router.post("/scenarios/{scenario_id}/participants/{participant_id}/orders", response_model=ParticipantPeriodResponse)
async def submit_order(
    scenario_id: int,
    participant_id: int,
    order_in: OrderCreate,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Submit or update an order for the current round.

    Participants can submit or update their order for the current round until the round ends.
    If the round time expires, any unsubmitted orders will be set to zero.
    """
    scenario_service = MixedScenarioService(db)
    try:
        participant_round = scenario_service.submit_order(scenario_id, participant_id, order_in.quantity, order_in.comment)
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
    rounds = db.query(ScenarioRound).filter(ScenarioRound.scenario_id == scenario_id).all()
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
    scenario_round = db.query(ScenarioRound).filter(
        ScenarioRound.scenario_id == scenario_id,
        ScenarioRound.round_number == round_number
    ).first()

    if not scenario_round:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Round not found"
        )

    return ScenarioPeriodResponse.model_validate(scenario_round)

@router.get("/{scenario_id}/current-round", response_model=ScenarioPeriodResponse)
def get_current_round(
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

    scenario_round = db.query(ScenarioRound).filter(
        ScenarioRound.scenario_id == scenario_id,
        ScenarioRound.round_number == scenario.current_round
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
    current_round = db.query(ScenarioRound).filter(
        ScenarioRound.scenario_id == scenario_id,
        ScenarioRound.round_number == scenario.current_round
    ).first()

    if not current_round:
        raise HTTPException(status_code=404, detail="Current round not found")

    # Get all participants in the scenario
    participants = db.query(Participant).filter(Participant.scenario_id == scenario_id).all()
    total_participants = len(participants)

    # Get participants who have submitted for the current round
    submitted_participants = db.query(ParticipantRound).filter(
        ParticipantRound.round_id == current_round.id
    ).all()
    submitted_count = len(submitted_participants)

    # Get list of participants who haven't submitted yet
    submitted_participant_ids = [p.participant_id for p in submitted_participants]
    pending_participants = [p for p in participants if p.id not in submitted_participant_ids]

    return {
        "scenario_id": scenario_id,
        "round_number": current_round.round_number,
        "is_completed": current_round.is_completed,
        "total_participants": total_participants,
        "submitted_count": submitted_count,
        "pending_count": total_participants - submitted_count,
        "pending_participants": [{"id": p.id, "name": p.name, "role": p.role} for p in pending_participants],
        "all_submitted": current_round.is_completed
    }

# Participant Round endpoints
@router.get("/{scenario_id}/participants/{participant_id}/current-round", response_model=ParticipantPeriodResponse)
def get_participant_current_round(
    scenario_id: int,
    participant_id: int,
    db: Session = Depends(get_sync_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get the current round for a participant.
    """
    # Get the current scenario round
    scenario = db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found"
        )

    current_round = db.query(ScenarioRound).filter(
        ScenarioRound.scenario_id == scenario_id,
        ScenarioRound.round_number == scenario.current_round
    ).first()

    if not current_round:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Current round not found"
        )

    # Get the participant's round
    participant_round = db.query(ParticipantRound).filter(
        ParticipantRound.participant_id == participant_id,
        ParticipantRound.round_id == current_round.id
    ).first()

    if not participant_round:
        # If the participant hasn't taken their turn yet, create a new participant round
        participant_round = ParticipantRound(
            participant_id=participant_id,
            round_id=current_round.id,
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
