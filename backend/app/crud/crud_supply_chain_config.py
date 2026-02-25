from typing import List, Optional, Dict, Any, Type, TypeVar, Generic
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session, Query, joinedload
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel

from app.models.supply_chain_config import (
    SupplyChainConfig,
    Site,
    TransportationLane,
    Market,
    MarketDemand,
)
# AWS SC DM compliant: Site (table: site), TransportationLane (table: transportation_lane)
from app.models.sc_entities import InvPolicy as ProductSiteConfig  # AWS SC: inv_policy table
from app.services.mixed_scenario_service import MixedScenarioService
from app.schemas.supply_chain_config import (
    SupplyChainConfigCreate,
    SupplyChainConfigUpdate,
    # Site schemas (DB: nodes)
    SiteCreate,
    SiteUpdate,
    # Transportation Lane schemas (AWS SC DM)
    TransportationLaneCreate,
    TransportationLaneUpdate,
    LaneCreate,  # DEPRECATED alias
    LaneUpdate,  # DEPRECATED alias
    # Product-Site config schemas (DB: product_site_configs)
    ProductSiteConfigCreate,
    ProductSiteConfigUpdate,
    # Market schemas
    MarketCreate,
    MarketUpdate,
    MarketDemandCreate,
    MarketDemandUpdate,
)
from app.crud.base import CRUDBase

ModelType = TypeVar("ModelType", bound=Any)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)

class CRUDSupplyChainConfig(CRUDBase[SupplyChainConfig, SupplyChainConfigCreate, SupplyChainConfigUpdate]):
    def get_active(self, db: Session) -> Optional[SupplyChainConfig]:
        return db.query(self.model).filter(self.model.is_active == True).first()

    def get_multi_by_creator(
        self, db: Session, *, creator_id: int, skip: int = 0, limit: int = 100
    ) -> List[SupplyChainConfig]:
        """Return configs created by a specific user."""
        return (
            db.query(self.model)
            .filter(self.model.created_by == creator_id)
            .offset(skip)
            .limit(limit)
            .all()
        )
            
    def create(self, db: Session, *, obj_in: SupplyChainConfigCreate) -> SupplyChainConfig:
        # Ensure only one active config per customer
        if obj_in.is_active:
            customer_id = getattr(obj_in, "customer_id", None)
            query = db.query(self.model).filter(self.model.is_active == True)
            if customer_id is not None:
                query = query.filter(self.model.customer_id == customer_id)
            else:
                query = query.filter(self.model.customer_id.is_(None))
            query.update({"is_active": False})
        return super().create(db, obj_in=obj_in)

    def update(
        self, db: Session, *, db_obj: SupplyChainConfig, obj_in: SupplyChainConfigUpdate
    ) -> SupplyChainConfig:
        # Handle is_active update
        if obj_in.is_active is True and not db_obj.is_active:
            # Deactivate other active configs
            query = db.query(self.model).filter(
                self.model.id != db_obj.id,
                self.model.is_active == True
            )
            if db_obj.customer_id is not None:
                query = query.filter(self.model.customer_id == db_obj.customer_id)
            else:
                query = query.filter(self.model.customer_id.is_(None))
            query.update({"is_active": False})

        return super().update(db, db_obj=db_obj, obj_in=obj_in)

class CRUDProduct:
    """CRUD operations for SC Product table (String PK)"""

    def _compute_hierarchy_path(self, db: Session, product_group_id: str) -> Optional[str]:
        """
        Walk up the product_hierarchy tree to build breadcrumb path.
        Returns: "Category > Family > Group" (e.g., "Frozen > Proteins > Poultry")
        """
        if not product_group_id:
            return None

        from app.models.sc_entities import ProductHierarchy

        # Collect hierarchy nodes from leaf to root
        path_parts = []
        current_id = product_group_id
        visited = set()  # Prevent infinite loops

        while current_id and current_id not in visited:
            visited.add(current_id)
            node = db.query(ProductHierarchy).filter(ProductHierarchy.id == current_id).first()
            if not node:
                break
            path_parts.append(node.description or node.id)
            current_id = node.parent_product_group_id

        # Reverse to get root-to-leaf order (Category > Family > Group)
        if path_parts:
            path_parts.reverse()
            return " > ".join(path_parts)
        return None

    def _enrich_with_hierarchy(self, db: Session, product) -> dict:
        """Add computed hierarchy_path to product dict"""
        product_dict = {
            "id": product.id,
            "description": product.description,
            "company_id": product.company_id,
            "config_id": product.config_id,
            "product_type": product.product_type,
            "base_uom": product.base_uom,
            "unit_cost": product.unit_cost,
            "unit_price": product.unit_price,
            "is_active": product.is_active,
            "product_group_id": product.product_group_id,
            "hierarchy_path": self._compute_hierarchy_path(db, product.product_group_id),
        }
        return product_dict

    def get(self, db: Session, id: str):
        """Get product by string ID"""
        from app.models.sc_entities import Product
        return db.query(Product).filter(Product.id == id).first()

    def get_with_hierarchy(self, db: Session, id: str) -> Optional[dict]:
        """Get product by ID with computed hierarchy_path"""
        product = self.get(db, id)
        if product:
            return self._enrich_with_hierarchy(db, product)
        return None

    def get_by_id(self, db: Session, *, product_id: str):
        """Get product by ID (alias for get)"""
        return self.get(db, product_id)

    def get_by_config(self, db: Session, *, config_id: int):
        """Get all products for a configuration"""
        from app.models.sc_entities import Product
        return db.query(Product).filter(Product.config_id == config_id).all()

    def get_by_config_with_hierarchy(self, db: Session, *, config_id: int) -> List[dict]:
        """Get all products for a configuration with computed hierarchy_path"""
        products = self.get_by_config(db, config_id=config_id)
        return [self._enrich_with_hierarchy(db, p) for p in products]

    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 100):
        """Get multiple products"""
        from app.models.sc_entities import Product
        return db.query(Product).offset(skip).limit(limit).all()

    def get_multi_with_hierarchy(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[dict]:
        """Get multiple products with computed hierarchy_path"""
        products = self.get_multi(db, skip=skip, limit=limit)
        return [self._enrich_with_hierarchy(db, p) for p in products]

    def create(self, db: Session, *, obj_in):
        """Create new product"""
        from app.models.sc_entities import Product
        db_obj = Product(**obj_in.dict())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, *, db_obj, obj_in):
        """Update existing product"""
        update_data = obj_in.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def remove(self, db: Session, *, id: str):
        """Delete product by ID"""
        from app.models.sc_entities import Product
        obj = db.query(Product).filter(Product.id == id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj


class CRUDSite(CRUDBase[Site, SiteCreate, SiteUpdate]):
    """AWS SC DM: Site CRUD operations (DB table: site)."""
    def _canonical(self, value: Optional[str]) -> Optional[str]:
        return MixedScenarioService._canonical_role(value)

    def get_by_name_and_type(self, db: Session, *, name: str, node_type: Optional[str], config_id: int) -> Optional[Site]:
        dag_type = self._canonical(node_type)
        query = db.query(self.model).options(
            joinedload(self.model.geography)
        ).filter(
            self.model.name == name,
            self.model.config_id == config_id
        )
        if dag_type:
            query = query.filter(self.model.dag_type == dag_type)
        return query.first()

    def get_by_type(self, db: Session, *, node_type: Optional[str], config_id: int) -> List[Site]:
        """Get sites by type with geography data eager-loaded for map view support."""
        dag_type = self._canonical(node_type)
        query = db.query(self.model).options(
            joinedload(self.model.geography)
        ).filter(self.model.config_id == config_id)
        if dag_type:
            query = query.filter(self.model.dag_type == dag_type)
        return query.all()

    def get_multi_by_config(
        self,
        db: Session,
        *,
        config_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> List[Site]:
        """Get sites with geography data eager-loaded for map view support."""
        return db.query(self.model).options(
            joinedload(self.model.geography)
        ).filter(
            self.model.config_id == config_id
        ).offset(skip).limit(limit).all()

class CRUDTransportationLane(CRUDBase[TransportationLane, LaneCreate, LaneUpdate]):
    """AWS SC DM: Transportation Lane CRUD operations (DB table: transportation_lane)."""
    def get_by_sites(
        self,
        db: Session,
        *,
        from_site_id: int,
        to_site_id: int,
        config_id: int
    ) -> Optional[TransportationLane]:
        return db.query(self.model).filter(
            self.model.from_site_id == from_site_id,
            self.model.to_site_id == to_site_id,
            self.model.config_id == config_id
        ).first()

    def get_by_config(self, db: Session, *, config_id: int) -> List[TransportationLane]:
        return db.query(self.model).options(
            joinedload(self.model.upstream_site),
            joinedload(self.model.downstream_site)
        ).filter(self.model.config_id == config_id).all()

class CRUDProductSiteConfig:
    """
    AWS SC DM: Product-Site configuration CRUD.
    DB table: item_node_configs (legacy name).
    Data migrated to InvPolicy table for active configs.
    """
    def __init__(self, model):
        self.model = model

    def get(self, db: Session, id: int) -> Optional[ProductSiteConfig]:
        # Product-Site configs now stored in InvPolicy
        return None

    def get_by_product_and_site(
        self,
        db: Session,
        *,
        product_id: int,
        site_id: int
    ) -> Optional[ProductSiteConfig]:
        # Product-Site configs now stored in InvPolicy
        return None

    def get_by_config(self, db: Session, *, config_id: int) -> List[ProductSiteConfig]:
        # Product-Site configs now stored in InvPolicy
        return []

    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 100):
        # Product-Site configs now stored in InvPolicy
        return []

class CRUDMarket(CRUDBase[Market, MarketCreate, MarketUpdate]):
    def get_by_name(self, db: Session, *, config_id: int, name: str) -> Optional[Market]:
        return db.query(self.model).filter(
            self.model.config_id == config_id,
            self.model.name == name
        ).first()


class CRUDMarketDemand(CRUDBase[MarketDemand, MarketDemandCreate, MarketDemandUpdate]):
    def get_by_item_and_market(
        self,
        db: Session,
        *,
        product_id: int,
        market_id: int,
        config_id: int
    ) -> Optional[MarketDemand]:
        return db.query(self.model).filter(
            self.model.product_id == product_id,
            self.model.market_id == market_id,
            self.model.config_id == config_id
        ).first()

    def get_by_config(self, db: Session, *, config_id: int) -> List[MarketDemand]:
        return db.query(self.model).options(
            joinedload(self.model.item),
            joinedload(self.model.market)
        ).filter(self.model.config_id == config_id).all()

# Initialize CRUD classes (AWS SC DM terminology)
supply_chain_config = CRUDSupplyChainConfig(SupplyChainConfig)
product = CRUDProduct()  # AWS SC DM: Product
site = CRUDSite(Site)  # AWS SC DM: Site (DB table: site)
transportation_lane = CRUDTransportationLane(TransportationLane)  # AWS SC DM: TransportationLane (DB table: transportation_lane)
lane = transportation_lane  # DEPRECATED: Use transportation_lane
product_site_config = CRUDProductSiteConfig(ProductSiteConfig)  # AWS SC DM: Product-Site config (DB: item_node_configs)
market = CRUDMarket(Market)
market_demand = CRUDMarketDemand(MarketDemand)
