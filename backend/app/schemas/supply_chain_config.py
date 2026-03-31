import re
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum
from datetime import datetime

from app.core.time_buckets import TimeBucket

try:  # Prefer Pydantic v2's model_validator when available
    from pydantic import model_validator

    def after_validator(**kwargs):
        def decorator(func):
            return model_validator(mode="after", **kwargs)(func)

        return decorator

except ImportError:  # Fallback to v1 root_validator semantics
    from pydantic import root_validator

    def after_validator(**kwargs):
        def decorator(func):
            return root_validator(skip_on_failure=True, **kwargs)(func)

        return decorator

# AWS SC DM models - Product, Site (DB: Node)
from app.models.sc_entities import Product as ProductModel
from app.models.sc_entities import InvPolicy as ProductSiteConfigModel  # Product-site config (AWS SC: inv_policy)


class NodeType(str, Enum):
    RETAILER = "retailer"
    WHOLESALER = "wholesaler"
    DISTRIBUTOR = "distributor"
    INVENTORY = "inventory"
    MANUFACTURER = "manufacturer"
    SUPPLIER = "supplier"
    CUSTOMER = "customer"
    VENDOR = "vendor"


class MasterNodeType(str, Enum):
    """Collapsed master processing categories used by the engine."""

    CUSTOMER = "CUSTOMER"
    VENDOR = "VENDOR"
    INVENTORY = "INVENTORY"
    MANUFACTURER = "MANUFACTURER"


def canonicalize_node_type(value: Any) -> str:
    """Normalize DAG node type identifiers."""
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    text = re.sub(r"_+", "_", text).strip("_")
    return text


class NodeTypeDefinition(BaseModel):
    type: str = Field(..., min_length=1, max_length=100, description="Internal node type identifier")
    label: str = Field(..., min_length=1, max_length=100, description="Display label for this node type")
    order: int = Field(..., ge=0, description="Display order for this node type")
    is_required: bool = Field(False, description="Whether this node type is required for the configuration")
    master_type: MasterNodeType = Field(
        MasterNodeType.INVENTORY,
        description="Engine master node type (INVENTORY/MANUFACTURER/VENDOR/CUSTOMER)",
    )

    @validator("type")
    def normalize_type(cls, value: str) -> str:
        cleaned = canonicalize_node_type(value)
        if not cleaned:
            raise ValueError("Type must not be blank")
        return cleaned

    @validator("label")
    def normalize_label(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Label must not be blank")
        return cleaned

    @validator("master_type", pre=True, always=True)
    def default_master_type(cls, value, values):
        """Map legacy roles to a master processing category and handle case conversion."""
        if value:
            # Handle case-insensitive conversion
            if isinstance(value, MasterNodeType):
                return value
            str_val = str(value).lower()
            try:
                return MasterNodeType(str_val)
            except ValueError:
                # Try mapping from uppercase enum name
                name_map = {e.name.lower(): e for e in MasterNodeType}
                if str_val in name_map:
                    return name_map[str_val]
                # Fall through to role-based default
        role = str(values.get("type") or "").lower()
        if role in {"retailer", "wholesaler", "distributor", "inventory", "supplier"}:
            return MasterNodeType.INVENTORY
        if role == "manufacturer":
            return MasterNodeType.MANUFACTURER
        if role == "vendor":
            return MasterNodeType.VENDOR
        return MasterNodeType.CUSTOMER


def default_site_type_definitions() -> List[NodeTypeDefinition]:
    return [
        NodeTypeDefinition(
            type=NodeType.VENDOR.value,
            label="Vendor",
            order=0,
            is_required=True,
            master_type=MasterNodeType.VENDOR,
        ),
        NodeTypeDefinition(
            type="manufacturer",
            label="Manufacturer",
            order=1,
            is_required=False,
            master_type=MasterNodeType.MANUFACTURER,
        ),
        NodeTypeDefinition(
            type="distributor",
            label="Distributor",
            order=2,
            is_required=False,
            master_type=MasterNodeType.INVENTORY,
        ),
        NodeTypeDefinition(
            type="wholesaler",
            label="Wholesaler",
            order=3,
            is_required=False,
            master_type=MasterNodeType.INVENTORY,
        ),
        NodeTypeDefinition(
            type="retailer",
            label="Retailer",
            order=4,
            is_required=False,
            master_type=MasterNodeType.INVENTORY,
        ),
        NodeTypeDefinition(
            type=NodeType.CUSTOMER.value,
            label="Customer",
            order=5,
            is_required=True,
            master_type=MasterNodeType.CUSTOMER,
        ),
    ]


class RangeConfig(BaseModel):
    min: float = Field(..., ge=0, description="Minimum value")
    max: float = Field(..., gt=0, description="Maximum value")

    @validator('max')
    def max_greater_than_min(cls, v, values):
        if 'min' in values and v < values['min']:
            raise ValueError('max must be greater than or equal to min')
        return v


class DistributionType(str, Enum):
    DETERMINISTIC = "deterministic"
    UNIFORM = "uniform"
    NORMAL = "normal"
    LOGNORMAL = "lognormal"
    TRIANGULAR = "triangular"


class DistributionConfig(BaseModel):
    type: DistributionType = Field(
        DistributionType.DETERMINISTIC,
        description="Distribution family",
    )
    value: Optional[float] = Field(
        None, ge=0, description="Deterministic value or mode (triangular)"
    )
    minimum: Optional[float] = Field(
        None, ge=0, description="Minimum value for uniform/triangular distributions"
    )
    maximum: Optional[float] = Field(
        None, ge=0, description="Maximum value for uniform/triangular distributions"
    )
    mean: Optional[float] = Field(None, ge=0, description="Mean for normal/lognormal")
    standard_deviation: Optional[float] = Field(
        None, ge=0, description="Standard deviation for normal"
    )
    sigma: Optional[float] = Field(
        None, ge=0, description="Sigma parameter for lognormal"
    )

    @after_validator()
    def validate_parameters(self) -> "DistributionConfig":
        dtype = self.type or DistributionType.DETERMINISTIC

        if dtype == DistributionType.DETERMINISTIC:
            if self.value is None:
                raise ValueError("Deterministic distribution requires a value")
        elif dtype == DistributionType.UNIFORM:
            if self.minimum is None or self.maximum is None:
                raise ValueError("Uniform distribution requires minimum and maximum")
            if self.maximum < self.minimum:
                raise ValueError("Uniform distribution requires maximum >= minimum")
        elif dtype == DistributionType.NORMAL:
            if self.mean is None or self.standard_deviation is None:
                raise ValueError("Normal distribution requires mean and standard deviation")
        elif dtype == DistributionType.LOGNORMAL:
            if self.mean is None or self.sigma is None:
                raise ValueError("Lognormal distribution requires mean and sigma")
        elif dtype == DistributionType.TRIANGULAR:
            if self.minimum is None or self.value is None or self.maximum is None:
                raise ValueError("Triangular distribution requires minimum, mode, and maximum")
            if not (self.minimum <= self.value <= self.maximum):
                raise ValueError("Triangular distribution requires minimum <= mode <= maximum")

        return self


class DemandType(str, Enum):
    NONE = "none"
    CONSTANT = "constant"
    RANDOM = "random"
    SEASONAL = "seasonal"
    TRENDING = "trending"
    CLASSIC = "classic"
    LOGNORMAL = "lognormal"
    NORMAL = "normal"
    UNIFORM = "uniform"


class VariabilityType(str, Enum):
    FLAT = "flat"
    STEP = "step"
    UNIFORM = "uniform"
    LOGNORMAL = "lognormal"
    NORMAL = "normal"


class SeasonalityType(str, Enum):
    NONE = "none"
    MULTIPLICATIVE = "multiplicative"


class TrendType(str, Enum):
    NONE = "none"
    LINEAR = "linear"


class VariabilityConfig(BaseModel):
    type: VariabilityType = Field(VariabilityType.FLAT, description="Variability strategy")
    value: Optional[float] = Field(1.0, ge=0, description="Constant multiplier for flat variability")
    start: Optional[float] = Field(None, ge=0, description="Starting multiplier for step variability")
    end: Optional[float] = Field(None, ge=0, description="Ending multiplier for step variability")
    period: Optional[int] = Field(None, gt=0, description="Number of periods for step variability")
    minimum: Optional[float] = Field(None, ge=0, description="Minimum for uniform variability")
    maximum: Optional[float] = Field(None, ge=0, description="Maximum for uniform variability")
    mean: Optional[float] = Field(None, ge=0, description="Mean demand for normal/lognormal variability")
    cov: Optional[float] = Field(None, ge=0, description="Coefficient of variation")

    @after_validator()
    def validate_parameters(self) -> "VariabilityConfig":
        vtype = self.type or VariabilityType.FLAT
        if vtype == VariabilityType.FLAT:
            if self.value is None:
                raise ValueError('Flat variability requires a value parameter')
        elif vtype == VariabilityType.STEP:
            if self.start is None or self.end is None or self.period is None:
                raise ValueError('Step variability requires start, end, and period parameters')
        elif vtype == VariabilityType.UNIFORM:
            if self.minimum is None or self.maximum is None or self.maximum < self.minimum:
                raise ValueError('Uniform variability requires minimum and maximum where max >= min')
        elif vtype in {VariabilityType.LOGNORMAL, VariabilityType.NORMAL}:
            if self.mean is None or self.cov is None:
                raise ValueError(f'{vtype.value.title()} variability requires mean and cov parameters')
        return self


class SeasonalityConfig(BaseModel):
    type: SeasonalityType = Field(SeasonalityType.NONE, description="Seasonality model")
    amplitude: Optional[float] = Field(0.0, ge=0, description="Seasonality amplitude")
    period: Optional[int] = Field(12, gt=0, description="Seasonality period")
    phase: Optional[int] = Field(0, description="Phase shift for the cycle")

    @after_validator()
    def validate_seasonality(self) -> "SeasonalityConfig":
        stype = self.type or SeasonalityType.NONE
        if stype != SeasonalityType.NONE:
            if self.amplitude is None or self.period is None:
                raise ValueError('Seasonality requires amplitude and period when enabled')
        return self


class TrendConfig(BaseModel):
    type: TrendType = Field(TrendType.NONE, description="Trend model")
    slope: Optional[float] = Field(0.0, description="Slope per period for linear trend")
    intercept: Optional[float] = Field(0.0, description="Intercept for linear trend")

    @after_validator()
    def validate_trend(self) -> "TrendConfig":
        trend_type = self.type or TrendType.NONE
        if trend_type == TrendType.LINEAR and self.slope is None:
            raise ValueError('Linear trend requires a slope value')
        return self


class DemandPattern(BaseModel):
    demand_type: DemandType = Field(DemandType.CONSTANT, description="Overall demand type")
    variability: VariabilityConfig = Field(
        default_factory=VariabilityConfig,
        description="Variability configuration"
    )
    seasonality: SeasonalityConfig = Field(
        default_factory=SeasonalityConfig,
        description="Seasonality configuration"
    )
    trend: TrendConfig = Field(
        default_factory=TrendConfig,
        description="Trend configuration"
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional demand parameters",
    )

    @validator('demand_type')
    def ensure_demand_type(cls, value: DemandType) -> DemandType:
        if value not in DemandType:
            raise ValueError(f'Invalid demand type: {value}')
        return value

# Base schemas
class SupplyChainConfigBase(BaseModel):
    name: str = Field(..., max_length=100, description="Name of the configuration")
    description: Optional[str] = Field(None, max_length=500, description="Description of the configuration")
    is_active: bool = Field(False, description="Whether this is the active configuration")
    mode: str = Field('production', description="Config-level operating mode: 'production' or 'learning'")
    tenant_id: Optional[int] = Field(
        None,
        description="ID of the tenant that owns this configuration"
    )
    time_bucket: TimeBucket = Field(TimeBucket.WEEK, description="Time aggregation unit for the simulation")
    site_type_definitions: List[NodeTypeDefinition] = Field(
        ...,
        description="Ordered list of site type definitions available to this configuration",
    )

    @after_validator()
    def validate_site_type_definitions(self) -> "SupplyChainConfigBase":
        definitions: List[NodeTypeDefinition] = self.site_type_definitions or []
        # Allow empty definitions for backwards compatibility with legacy data
        if not definitions:
            return self

        seen_types = set()
        normalized: List[NodeTypeDefinition] = []
        for index, definition in enumerate(definitions):
            if definition.type in seen_types:
                # Skip duplicates rather than raising error (backwards compat)
                continue
            seen_types.add(definition.type)
            if definition.order is None:
                definition.order = index
            normalized.append(definition)

        # Log warning instead of raising error for missing required types
        # This allows reading legacy data that may not have all required types
        required_types = {"customer", "vendor"}
        missing_required = [rtype for rtype in required_types if rtype not in {d.type for d in normalized}]
        if missing_required:
            import logging
            logging.getLogger(__name__).warning(
                f"Config missing required site type definitions: {', '.join(sorted(missing_required))}"
            )

        return self

class SiteBase(BaseModel):
    """AWS SC DM: Site (DB table: nodes)."""
    name: str = Field(..., max_length=100, description="Name of the node")
    type: str = Field(..., max_length=100, description="DAG node type identifier")
    dag_type: Optional[str] = Field(
        None,
        description="DAG role/type used for graph routing (defaults to type)",
    )
    master_type: Optional[MasterNodeType] = Field(
        None,
        description="Master processing type used for shared logic (defaults to type with aliases)",
    )
    priority: Optional[int] = Field(
        None,
        description=(
            "Priority for ordering nodes of the same type (lower values processed first; "
            "None falls back to alphabetical order)"
        ),
    )
    order_aging: int = Field(
        0,
        ge=0,
        description=(
            "Number of periods a backlog order can remain before turning into lost sales; "
            "0 disables aging"
        ),
    )
    lost_sale_cost: Optional[float] = Field(
        None,
        description=(
            "Cost per unit for aged-out orders; defaults to twice the backlog cost when omitted"
        ),
    )
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Flexible metadata for the node (capacity, targets, etc.)",
    )

    @validator("dag_type", pre=True, always=True)
    def ensure_dag_type(cls, value, values):
        candidate = value or values.get("type")
        cleaned = canonicalize_node_type(candidate)
        if cleaned:
            return cleaned
        raise ValueError("dag_type must be provided")

    @validator("type", pre=True, always=True)
    def normalize_type_field(cls, value, values):
        candidate = values.get("dag_type") or value
        cleaned = canonicalize_node_type(candidate)
        if cleaned:
            return cleaned
        raise ValueError("type must be provided")

    @validator("master_type", pre=True, always=True)
    def normalize_master_type(cls, value):
        """Handle case-insensitive master_type parsing from database."""
        if value is None:
            return None
        if isinstance(value, MasterNodeType):
            return value
        # Convert string to lowercase and look up enum
        str_val = str(value).lower()
        try:
            return MasterNodeType(str_val)
        except ValueError:
            # Try mapping from uppercase enum name
            name_map = {e.name.lower(): e for e in MasterNodeType}
            if str_val in name_map:
                return name_map[str_val]
            return None

class TransportationLaneBase(BaseModel):
    """AWS SC DM: Transportation lane connecting two sites."""
    from_site_id: int = Field(..., description="ID of the upstream (from) site")
    to_site_id: int = Field(..., description="ID of the downstream (to) site")
    capacity: int = Field(..., gt=0, description="Capacity in units per day")
    lead_time_days: Optional[RangeConfig] = Field(
        None, description="Legacy range of lead times in days"
    )
    demand_lead_time: DistributionConfig = Field(
        default_factory=lambda: DistributionConfig(
            type=DistributionType.DETERMINISTIC,
            value=0,
        ),
        description="Distribution for upstream information lead time",
        alias="demand_lead_time",
    )
    supply_lead_time: DistributionConfig = Field(
        default_factory=lambda: DistributionConfig(
            type=DistributionType.DETERMINISTIC,
            value=1,
        ),
        description="Distribution for downstream material lead time",
    )

    @validator('to_site_id')
    def sites_must_differ(cls, v, values):
        if 'from_site_id' in values and v == values['from_site_id']:
            raise ValueError('From and to sites must be different')
        return v

# DEPRECATED: Use TransportationLaneBase
LaneBase = TransportationLaneBase

class ProductSiteConfigBase(BaseModel):
    """AWS SC DM compliant: Product-Site configuration."""
    product_id: int = Field(..., description="ID of the product")
    site_id: int = Field(..., description="ID of the site")
    inventory_target_range: RangeConfig = Field(..., description="Range of inventory targets")
    initial_inventory_range: RangeConfig = Field(..., description="Range of initial inventory levels")
    holding_cost_range: RangeConfig = Field(..., description="Range of holding costs")
    backlog_cost_range: RangeConfig = Field(..., description="Range of backlog costs")
    selling_price_range: RangeConfig = Field(..., description="Range of selling prices")


class ProductSiteSupplierBase(BaseModel):
    """AWS SC DM: Product-Site supplier configuration."""
    product_site_config_id: int = Field(..., description="ID of the product-site configuration")
    supplier_site_id: int = Field(..., description="ID of the supplier site")
    priority: int = Field(default=0, ge=0, description="Priority for this supplier (0 = highest priority)")

class MarketBase(BaseModel):
    name: str = Field(..., max_length=100, description="Name of the market")
    company: Optional[str] = Field(
        None, max_length=100, description="Owning company for this demand site"
    )
    description: Optional[str] = Field(None, max_length=255, description="Description of the market")


class MarketCreate(MarketBase):
    pass


class MarketUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100, description="Name of the market")
    description: Optional[str] = Field(None, max_length=255, description="Description of the market")


class Market(MarketBase):
    id: int

    class Config:
        orm_mode = True


class MarketDemandBase(BaseModel):
    product_id: int = Field(..., description="ID of the product")
    market_id: int = Field(..., description="ID of the market")
    demand_pattern: DemandPattern = Field(..., description="Demand pattern configuration")

# Create schemas
class SupplyChainConfigCreate(SupplyChainConfigBase):
    pass

class SiteCreate(SiteBase):
    """AWS SC DM: Create a site (DB table: nodes)."""
    pass

class TransportationLaneCreate(TransportationLaneBase):
    """AWS SC DM: Create a transportation lane."""
    pass

# DEPRECATED: Use TransportationLaneCreate
LaneCreate = TransportationLaneCreate

class ProductSiteConfigCreate(ProductSiteConfigBase):
    """AWS SC DM: Create a Product-Site configuration."""
    pass

class ProductSiteSupplierCreate(ProductSiteSupplierBase):
    """AWS SC DM: Create a Product-Site supplier."""
    pass

class MarketDemandCreate(MarketDemandBase):
    pass

# Update schemas
class SupplyChainConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100, description="Name of the configuration")
    description: Optional[str] = Field(None, max_length=500, description="Description of the configuration")
    is_active: Optional[bool] = Field(None, description="Whether this is the active configuration")
    mode: Optional[str] = Field(None, description="Config-level operating mode: 'production' or 'learning'")
    tenant_id: Optional[int] = Field(None, description="ID of the tenant that owns this configuration")
    time_bucket: Optional[TimeBucket] = Field(None, description="Time aggregation unit for the simulation")
    site_type_definitions: Optional[List[NodeTypeDefinition]] = Field(
        None,
        description="Updated site type definitions",
    )

class SiteUpdate(BaseModel):
    """AWS SC DM: Update a site (DB table: nodes)."""
    name: Optional[str] = Field(None, max_length=100, description="Name of the site")
    type: Optional[str] = Field(None, max_length=100, description="Type of the site")
    dag_type: Optional[str] = Field(
        None,
        description="DAG role/type used for graph routing (defaults to type)",
    )
    master_type: Optional[MasterNodeType] = Field(
        None,
        description="Master processing type used for shared logic (defaults to type with aliases)",
    )
    priority: Optional[int] = Field(None, description="Priority for ordering sites of the same type")
    order_aging: Optional[int] = Field(
        None,
        ge=0,
        description="Number of periods backlog can age before converting to lost sales",
    )
    lost_sale_cost: Optional[float] = Field(
        None,
        description="Cost per unit applied to aged-out orders",
    )
    attributes: Optional[Dict[str, Any]] = Field(
        None, description="Updated metadata for the site"
    )

    @validator("type", "dag_type", pre=True)
    def normalize_update_types(cls, value):
        if value is None:
            return value
        cleaned = canonicalize_node_type(value)
        if not cleaned:
            raise ValueError("Site type must not be blank")
        return cleaned

class TransportationLaneUpdate(BaseModel):
    """AWS SC DM: Update a transportation lane."""
    capacity: Optional[int] = Field(None, gt=0, description="Capacity in units per day")
    lead_time_days: Optional[RangeConfig] = Field(None, description="Legacy lead time range")
    demand_lead_time: Optional[DistributionConfig] = Field(
        None, description="Updated demand lead time distribution", alias="demand_lead_time"
    )
    supply_lead_time: Optional[DistributionConfig] = Field(
        None, description="Updated supply lead time distribution"
    )

# DEPRECATED: Use TransportationLaneUpdate
LaneUpdate = TransportationLaneUpdate

class ProductSiteConfigUpdate(BaseModel):
    """AWS SC DM: Update a Product-Site configuration."""
    inventory_target_range: Optional[RangeConfig] = Field(None, description="Range of inventory targets")
    initial_inventory_range: Optional[RangeConfig] = Field(None, description="Range of initial inventory levels")
    holding_cost_range: Optional[RangeConfig] = Field(None, description="Range of holding costs")
    backlog_cost_range: Optional[RangeConfig] = Field(None, description="Range of backlog costs")
    selling_price_range: Optional[RangeConfig] = Field(None, description="Range of selling prices")

class ProductSiteSupplierUpdate(BaseModel):
    """AWS SC DM: Update a Product-Site supplier."""
    priority: Optional[int] = Field(None, ge=0, description="Priority for this supplier (0 = highest priority)")

class MarketDemandUpdate(BaseModel):
    demand_pattern: Optional[DemandPattern] = Field(None, description="Demand pattern configuration")

# Response schemas
class ProductSiteSupplier(ProductSiteSupplierBase):
    """AWS SC DM: Product-Site supplier response."""
    id: int

    class Config:
        orm_mode = True

class ProductSiteConfig(ProductSiteConfigBase):
    """AWS SC DM: Product-Site configuration response."""
    id: int
    suppliers: List['ProductSiteSupplier'] = []

    class Config:
        orm_mode = True

class MarketDemand(MarketDemandBase):
    id: int

    class Config:
        orm_mode = True

# AWS SC DM aliases — use these in new code
CustomerDemandBase = MarketDemandBase
CustomerDemandCreate = MarketDemandCreate
CustomerDemandUpdate = MarketDemandUpdate
CustomerDemand = MarketDemand

class TransportationLane(TransportationLaneBase):
    """AWS SC DM: Transportation lane response (edge between sites)."""
    id: int
    upstream_site: 'Site'  # AWS SC DM: from_site
    downstream_site: 'Site'  # AWS SC DM: to_site

    class Config:
        orm_mode = True

# DEPRECATED: Use TransportationLane
Lane = TransportationLane

class SiteGeography(BaseModel):
    """Embedded geography data for Site response (map view support)."""
    id: Optional[str] = None
    city: Optional[str] = None
    state_prov: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    class Config:
        orm_mode = True


class Site(SiteBase):
    """AWS SC DM: Site (DB table: nodes)."""
    id: int
    product_site_configs: List[ProductSiteConfig] = []
    upstream_transportation_lanes: List[TransportationLane] = []
    downstream_transportation_lanes: List[TransportationLane] = []
    # Geography data for map view support
    geo_id: Optional[str] = Field(None, description="ID of the linked geography record")
    geography: Optional[SiteGeography] = Field(None, description="Embedded geography data with lat/lon")

    class Config:
        orm_mode = True

class SupplyChainConfig(SupplyChainConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime
    validation_status: str = Field(
        "unchecked",
        description="Validation status: unchecked, valid, or invalid",
    )
    validation_errors: Optional[List[str]] = Field(
        None,
        description="List of validation error messages if invalid",
    )
    validated_at: Optional[datetime] = Field(
        None,
        description="Timestamp of the last validation check",
    )
    needs_training: bool = Field(True, description="Whether the configuration requires retraining")
    training_status: Optional[str] = Field(
        None,
        description="Human-readable status for the most recent training job",
    )
    trained_at: Optional[datetime] = Field(
        None,
        description="Timestamp of the last successful training run",
    )
    trained_model_path: Optional[str] = Field(
        None,
        description="Filesystem path to the most recent trained model",
    )
    last_trained_config_hash: Optional[str] = Field(
        None,
        description="Hash of the configuration when it was last trained",
    )
    scenario_type: str = Field(
        "BASELINE",
        description="Config type: BASELINE, WORKING, SIMULATION, or ARCHIVED",
    )
    version: int = Field(
        1,
        description="Config version number (incremented on reprovisioning)",
    )
    parent_config_id: Optional[int] = Field(
        None,
        description="ID of the parent config (set on archived versions)",
    )
    # AWS SC DM terminology
    products: List['ProductResponse'] = []
    sites: List[Site] = []
    transportation_lanes: List[TransportationLane] = []
    markets: List[Market] = []
    market_demands: List[MarketDemand] = []
    customer_demands: List[CustomerDemand] = []  # AWS SC DM terminology

    class Config:
        orm_mode = True


# ============================================================================
# Product Schemas (SC Compliant)
# ============================================================================

class ProductBase(BaseModel):
    """Base schema for SC Product"""
    id: str = Field(..., max_length=100, description="Product ID (e.g., CASE, SIXPACK, BOTTLE)")
    description: Optional[str] = Field(None, max_length=500, description="Product description")
    product_type: Optional[str] = Field("finished_good", description="Product type: finished_good, component, raw_material")
    base_uom: str = Field("EA", description="Base unit of measure (default: EA)")
    unit_cost: Optional[float] = Field(None, description="Unit cost")
    unit_price: Optional[float] = Field(None, description="Unit selling price")
    is_active: str = Field("true", description="Active status (true/false)")
    # AWS SC DM compliant hierarchy via product_hierarchy table
    product_group_id: Optional[str] = Field(None, max_length=100, description="FK to product_hierarchy table")

class ProductCreate(ProductBase):
    """Schema for creating a new Product"""
    config_id: Optional[int] = Field(None, description="Supply chain configuration ID")
    company_id: str = Field("DEFAULT", description="Company ID (default: DEFAULT)")

class ProductUpdate(BaseModel):
    """Schema for updating a Product"""
    description: Optional[str] = Field(None, max_length=500)
    unit_cost: Optional[float] = None
    unit_price: Optional[float] = None
    is_active: Optional[str] = None
    product_group_id: Optional[str] = Field(None, max_length=100, description="FK to product_hierarchy table")


class ProductResponse(ProductBase):
    """Full Product schema with database fields and computed hierarchy_path"""
    company_id: str
    config_id: Optional[int] = None
    # AWS SC DM compliant: hierarchy_path computed from product_hierarchy table
    # Format: "Category > Family > Group" (e.g., "Frozen > Proteins > Poultry")
    hierarchy_path: Optional[str] = Field(None, description="Breadcrumb path from product_hierarchy tree")
    # Product hierarchy fields (for filtering/aggregation)
    category: Optional[str] = Field(None, description="Top-level category (e.g., Meat & Poultry)")
    family: Optional[str] = Field(None, description="Product family (e.g., Frozen Proteins)")
    product_group_name: Optional[str] = Field(None, description="Product group code (e.g., FRZ_PROTEIN)")

    class Config:
        orm_mode = True


# Alias for convenience
Product = ProductResponse


# Update forward refs for proper type hints
Site.update_forward_refs()
TransportationLane.update_forward_refs()
ProductSiteConfig.update_forward_refs()
ProductSiteSupplier.update_forward_refs()
