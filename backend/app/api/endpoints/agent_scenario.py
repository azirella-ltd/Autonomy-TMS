from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional

from fastapi import Body

from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.scenario import ScenarioCreate
from app.services.agent_game_service import AgentGameService

router = APIRouter()

def get_agent_service(db: Session = Depends(get_db)) -> AgentGameService:
    """Dependency to get an instance of AgentGameService."""
    return AgentGameService(db)

@router.post("/agent-scenarios/", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_agent_game(
    scenario_in: ScenarioCreate,
    agent_service: AgentGameService = Depends(get_agent_service),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new game with AI agents.
    
    - **name**: Name of the game
    - **max_periods**: Maximum number of rounds (default: 20)
    - **demand_pattern**: Configuration for the demand pattern
    """
    try:
        scenario = agent_service.create_scenario(scenario_in)
        return {"message": "Scenario created successfully", "scenario_id": scenario.id}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/agent-scenarios/{scenario_id}/start", response_model=Dict[str, Any])
def start_agent_game(
    scenario_id: int,
    agent_service: AgentGameService = Depends(get_agent_service),
    current_user: dict = Depends(get_current_user)
):
    """Start an agent-based game."""
    try:
        scenario = agent_service.start_scenario(scenario_id)
        return {"message": "Scenario started successfully", "scenario_id": scenario.id}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(e).lower() 
            else status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/agent-scenarios/{scenario_id}/play-round", response_model=Dict[str, Any])
def play_agent_round(
    scenario_id: int,
    agent_service: AgentGameService = Depends(get_agent_service),
    current_user: dict = Depends(get_current_user)
):
    """Play one round of an agent-based game."""
    try:
        scenario_state = agent_service.play_round(scenario_id)
        return {"message": "Round played successfully", "scenario_state": scenario_state}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/agent-scenarios/{scenario_id}/state", response_model=Dict[str, Any])
def get_agent_game_state(
    scenario_id: int,
    agent_service: AgentGameService = Depends(get_agent_service),
    current_user: dict = Depends(get_current_user)
):
    """Get the current state of an agent-based game."""
    try:
        return agent_service.get_scenario_state(scenario_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

@router.put("/agent-scenarios/{scenario_id}/agent-strategy")
def set_agent_strategy(
    scenario_id: int,
    role: str,
    strategy: str,
    params: Optional[Dict[str, Any]] = Body(default=None),
    agent_service: AgentGameService = Depends(get_agent_service),
    current_user: dict = Depends(get_current_user)
):
    """
    Set the strategy for an AI agent.
    
    - **role**: The role of the agent (retailer, wholesaler, distributor, manufacturer)
    - **strategy**: The strategy to use (naive, bullwhip, conservative, random)
    """
    try:
        agent_service.set_agent_strategy(scenario_id, role, strategy, params=params)
        return {"message": f"Strategy for {role} set to {strategy}"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.put("/agent-scenarios/{scenario_id}/demand-visibility")
def set_demand_visibility(
    scenario_id: int,
    visible: bool,
    agent_service: AgentGameService = Depends(get_agent_service),
    current_user: dict = Depends(get_current_user)
):
    """
    Set whether agents can see the actual customer demand.
    
    - **visible**: Whether agents can see the demand (true/false)
    """
    try:
        agent_service.set_demand_visibility(visible)
        return {"message": f"Demand visibility set to {visible}"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
