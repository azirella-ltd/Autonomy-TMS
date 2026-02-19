from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class AgentConfigBase(BaseModel):
    """Base model for agent configuration."""
    name: str = Field(..., max_length=100, description="Name of the agent configuration")
    description: Optional[str] = Field(None, max_length=500, description="Description of the agent configuration")
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Configuration parameters for the agent"
    )
    is_public: bool = Field(
        default=True,
        description="Whether this configuration is public or private to the creator"
    )

class AgentConfigCreate(AgentConfigBase):
    """Model for creating a new agent configuration."""
    pass

class AgentConfigUpdate(BaseModel):
    """Model for updating an existing agent configuration."""
    name: Optional[str] = Field(None, max_length=100, description="Name of the agent configuration")
    description: Optional[str] = Field(None, max_length=500, description="Description of the agent configuration")
    config: Optional[Dict[str, Any]] = Field(
        None,
        description="Configuration parameters for the agent"
    )
    is_public: Optional[bool] = Field(
        None,
        description="Whether this configuration is public or private to the creator"
    )

class AgentConfigInDBBase(AgentConfigBase):
    """Base model for agent configuration with database fields."""
    id: int
    created_by: int = Field(..., description="ID of the user who created this configuration")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True

class AgentConfig(AgentConfigInDBBase):
    """Complete agent configuration model with database-specific fields."""
    pass
