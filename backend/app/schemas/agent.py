from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class AgentConfigBase(BaseModel):
    agent_type: str = Field(..., description="Type of agent (e.g., 'base', 'reinforcement_learning', 'rule_based')")
    config: Dict[str, Any] = Field(default_factory=dict, description="Agent-specific configuration")

class AgentConfigCreate(AgentConfigBase):
    pass

class AgentConfigUpdate(AgentConfigBase):
    agent_type: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

class AgentConfigInDB(AgentConfigBase):
    id: int
    game_id: int

    class Config:
        from_attributes = True

class RoleAssignment(BaseModel):
    role: str = Field(..., description="Role name (e.g., 'retailer', 'wholesaler')")
    is_ai: bool = Field(default=False, description="Whether this role is controlled by AI")
    agent_config_id: Optional[int] = Field(None, description="ID of the agent configuration to use")
    user_id: Optional[int] = Field(None, description="ID of the user assigned to this role, if any")
