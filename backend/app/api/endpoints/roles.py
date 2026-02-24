from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from ... import crud, schemas, models
from ...database import get_db
from ..deps import get_current_active_user
from ...schemas.agent import RoleAssignment, AgentConfigCreate, AgentConfigUpdate, AgentConfigInDB

router = APIRouter()

# Agent Configuration Endpoints
@router.post("/agent-configs/", response_model=AgentConfigInDB)
def create_agent_config(
    config: AgentConfigCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Create a new agent configuration"""
    # Verify user has access to the scenario
    scenario = crud.game.get(db, config.scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    if not crud.user.is_superuser(current_user) and not crud.user.has_game_access(current_user.id, scenario.id, db):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    return crud.agent_config.create(db, obj_in=config)

@router.get("/agent-configs/{config_id}", response_model=AgentConfigInDB)
def read_agent_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get agent configuration by ID"""
    config = crud.agent_config.get(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Agent configuration not found")
    
    if not crud.user.is_superuser(current_user) and not crud.user.has_game_access(current_user.id, config.scenario_id, db):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    return config

@router.get("/scenarios/{scenario_id}/agent-configs", response_model=List[AgentConfigInDB])
def read_scenario_agent_configs(
    scenario_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get all agent configurations for a scenario"""
    if not crud.user.is_superuser(current_user) and not crud.user.has_game_access(current_user.id, scenario_id, db):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    return crud.agent_config.get_multi_by_game(db, scenario_id=scenario_id, skip=skip, limit=limit)

@router.put("/agent-configs/{config_id}", response_model=AgentConfigInDB)
def update_agent_config(
    config_id: int,
    config_in: AgentConfigUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Update an agent configuration"""
    config = crud.agent_config.get(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Agent configuration not found")
    
    if not crud.user.is_superuser(current_user) and not crud.user.has_game_access(current_user.id, config.scenario_id, db):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    return crud.agent_config.update(db, db_obj=config, obj_in=config_in)

# Role Assignment Endpoints
@router.get("/scenarios/{scenario_id}/roles", response_model=Dict[str, RoleAssignment])
def get_role_assignments(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get all role assignments for a scenario"""
    scenario = crud.game.get(db, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    if not crud.user.is_superuser(current_user) and not crud.user.has_game_access(current_user.id, scenario_id, db):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return scenario.role_assignments or {}

@router.put("/scenarios/{scenario_id}/roles/{role}", response_model=RoleAssignment)
def update_role_assignment(
    scenario_id: int,
    role: str,
    assignment: RoleAssignment,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Update role assignment for a specific role in a scenario"""
    scenario = crud.game.get(db, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    if not crud.user.is_superuser(current_user) and not crud.user.has_game_access(current_user.id, scenario_id, db):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # If assigning to a user, verify the user exists and is part of the scenario
    if not assignment.is_ai and assignment.user_id:
        user = crud.user.get(db, assignment.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if not any(u.id == assignment.user_id for u in scenario.users):
            raise HTTPException(status_code=400, detail="User is not part of this scenario")

    # If assigning to AI, verify the agent config exists and belongs to this scenario
    if assignment.is_ai and assignment.agent_config_id:
        agent_config = crud.agent_config.get(db, assignment.agent_config_id)
        if not agent_config or agent_config.scenario_id != scenario_id:
            raise HTTPException(status_code=400, detail="Invalid agent configuration")
    
    # Update the role assignment
    scenario.set_role_assignment(
        role=role,
        is_ai=assignment.is_ai,
        agent_config_id=assignment.agent_config_id,
        user_id=assignment.user_id
    )
    
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    
    return assignment

@router.get("/scenarios/{scenario_id}/available-roles", response_model=List[str])
def get_available_roles(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get all available roles that can be assigned"""
    # In a real implementation, this would come from scenario configuration
    return ["retailer", "wholesaler", "distributor", "manufacturer"]
