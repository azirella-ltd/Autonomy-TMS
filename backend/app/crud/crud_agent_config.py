from typing import Any, Dict, List, Optional, Union

from sqlalchemy.orm import Session

from .. import models, schemas
from .base import CRUDBase

class CRUDAgentConfig(CRUDBase[models.AgentConfig, schemas.AgentConfigCreate, schemas.AgentConfigUpdate]):
    """CRUD operations for AgentConfig"""
    
    def get_multi_by_game(
        self, db: Session, *, game_id: int, skip: int = 0, limit: int = 100
    ) -> List[models.AgentConfig]:
        """Get all agent configurations for a specific game"""
        return (
            db.query(self.model)
            .filter(self.model.game_id == game_id)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_by_role(
        self, db: Session, *, game_id: int, role: str
    ) -> Optional[models.AgentConfig]:
        """Get agent configuration by game ID and role"""
        return (
            db.query(self.model)
            .filter(self.model.game_id == game_id, self.model.role == role)
            .first()
        )
    
    def update_or_create(
        self, db: Session, *, obj_in: schemas.AgentConfigCreate
    ) -> models.AgentConfig:
        """Update existing agent config or create if it doesn't exist"""
        db_obj = self.get_by_role(db, game_id=obj_in.game_id, role=obj_in.role)
        if db_obj:
            return self.update(db, db_obj=db_obj, obj_in=obj_in)
        return self.create(db, obj_in=obj_in)

agent_config = CRUDAgentConfig(models.AgentConfig)
