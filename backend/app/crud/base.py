from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union, Tuple
from sqlalchemy import and_
from sqlalchemy.orm import Session, Query
from pydantic import BaseModel
from fastapi.encoders import jsonable_encoder
from app.db.base_class import Base

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]):
        """
        CRUD object with default methods to Create, Read, Update, Delete (CRUD).
        
        **Parameters**
        * `model`: A SQLAlchemy model class
        * `schema`: A Pydantic model (schema) class
        """
        self.model = model
        
    def _get_query_with_filters(
        self, 
        db: Session, 
        *, 
        skip: int = 0, 
        limit: int = 100,
        **filters: Any
    ) -> Query:
        """Helper method to build a query with filters."""
        query = db.query(self.model)
        if filters:
            filter_conditions = [
                getattr(self.model, key) == value 
                for key, value in filters.items() 
                if hasattr(self.model, key) and value is not None
            ]
            if filter_conditions:
                query = query.filter(and_(*filter_conditions))
        return query.offset(skip).limit(limit)

    def get(self, db: Session, id: Any) -> Optional[ModelType]:
        return db.query(self.model).filter(self.model.id == id).first()
    
    def get_by_config(self, db: Session, *, config_id: int) -> List[ModelType]:
        """Get all records for a specific configuration."""
        return self.get_multi_by_config(db, config_id=config_id)
    
    def get_multi_by_config(
        self, 
        db: Session, 
        *, 
        config_id: int, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[ModelType]:
        """Get multiple records filtered by config_id."""
        return self._get_query_with_filters(
            db, 
            skip=skip, 
            limit=limit, 
            config_id=config_id
        ).all()

    def get_multi(
        self, db: Session, *, skip: int = 0, limit: int = 100, **filters: Any
    ) -> List[ModelType]:
        """Get multiple records with optional filtering."""
        return self._get_query_with_filters(
            db, 
            skip=skip, 
            limit=limit, 
            **filters
        ).all()
    
    def create_with_config(
        self, 
        db: Session, 
        *, 
        obj_in: CreateSchemaType, 
        config_id: int
    ) -> ModelType:
        """Create a new record with a config_id."""
        obj_in_data = jsonable_encoder(obj_in)
        if hasattr(self.model, 'config_id'):
            obj_in_data['config_id'] = config_id
        db_obj = self.model(**obj_in_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def create(self, db: Session, *, obj_in: CreateSchemaType) -> ModelType:
        obj_in_data = jsonable_encoder(obj_in)
        db_obj = self.model(**obj_in_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self,
        db: Session,
        *,
        db_obj: ModelType,
        obj_in: Union[UpdateSchemaType, Dict[str, Any]]
    ) -> ModelType:
        obj_data = jsonable_encoder(db_obj)
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.dict(exclude_unset=True)
        for field in obj_data:
            if field in update_data:
                setattr(db_obj, field, update_data[field])
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def remove(self, db: Session, *, id: int) -> Optional[ModelType]:
        obj = db.query(self.model).get(id)
        if obj:
            db.delete(obj)
            db.commit()
        return obj
    
    def remove_by_config(self, db: Session, *, config_id: int) -> int:
        """Remove all records for a specific configuration."""
        deleted_count = db.query(self.model).filter(
            self.model.config_id == config_id
        ).delete(synchronize_session=False)
        db.commit()
        return deleted_count
