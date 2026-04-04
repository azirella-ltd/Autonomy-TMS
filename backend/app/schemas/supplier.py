"""
Supplier Entity Pydantic Schemas - SC Compliant

Schemas for TradingPartner (type='vendor'), VendorProduct, VendorLeadTime,
and SupplierPerformance entities.

Based on SC entities: trading_partner, vendor_product, vendor_lead_time
"""

from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class TradingPartnerType(str, Enum):
    """Trading partner types"""
    VENDOR = "vendor"
    CUSTOMER = "customer"
    THREE_PL = "3PL"
    CARRIER = "carrier"


class SupplierTier(str, Enum):
    """Supplier tier classification"""
    TIER_1 = "TIER_1"  # Strategic suppliers
    TIER_2 = "TIER_2"  # Preferred suppliers
    TIER_3 = "TIER_3"  # Approved suppliers
    TIER_4 = "TIER_4"  # Contingency suppliers


class RiskLevel(str, Enum):
    """Supplier risk levels"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PerformancePeriodType(str, Enum):
    """Performance tracking period types"""
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"


# ============================================================================
# TradingPartner (Supplier) Schemas
# ============================================================================

class TradingPartnerBase(BaseModel):
    """Base schema for TradingPartner (shared fields)"""
    # SC Core Fields
    description: Optional[str] = Field(None, max_length=500, description="Supplier description")
    company_id: Optional[str] = Field(None, max_length=100, description="Company ID")
    is_active: str = Field("true", description="Active status: 'true' or 'false'")

    # Address
    address_1: Optional[str] = Field(None, max_length=255)
    address_2: Optional[str] = Field(None, max_length=255)
    address_3: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state_prov: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=50)
    country: Optional[str] = Field(None, max_length=100)

    # Contact & Location
    phone_number: Optional[str] = Field(None, max_length=50)
    time_zone: Optional[str] = Field(None, max_length=50)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)

    # Source Tracking
    source: Optional[str] = Field(None, max_length=100)
    source_event_id: Optional[str] = Field(None, max_length=100)
    source_update_dttm: Optional[datetime] = None

    # Extensions
    tier: Optional[SupplierTier] = Field(None, description="Supplier tier classification")
    production_capacity: Optional[float] = Field(None, ge=0, description="Production capacity")
    capacity_unit: Optional[str] = Field(None, max_length=50, description="Capacity unit (e.g., 'units/month')")
    minimum_order_quantity: Optional[float] = Field(None, ge=0)
    maximum_order_quantity: Optional[float] = Field(None, ge=0)
    iso_certified: bool = Field(False, description="ISO certification status")
    certifications: Optional[str] = Field(None, max_length=500, description="Certifications (comma-separated)")
    risk_level: Optional[RiskLevel] = None
    risk_notes: Optional[str] = Field(None, max_length=1000)
    tax_id: Optional[str] = Field(None, max_length=50)
    duns_number: Optional[str] = Field(None, max_length=20)
    payment_terms: Optional[str] = Field(None, max_length=100, description="e.g., 'Net 30', 'Net 60'")
    currency: str = Field("USD", max_length=10)
    contact_name: Optional[str] = Field(None, max_length=255)
    contact_email: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=2000)

    @field_validator('is_active')
    @classmethod
    def validate_is_active(cls, v: str) -> str:
        """Validate is_active is 'true' or 'false'"""
        if v not in ['true', 'false']:
            raise ValueError("is_active must be 'true' or 'false'")
        return v

    @field_validator('minimum_order_quantity', 'maximum_order_quantity')
    @classmethod
    def validate_order_quantities(cls, v: Optional[float], info) -> Optional[float]:
        """Validate order quantities are non-negative"""
        if v is not None and v < 0:
            raise ValueError(f"{info.field_name} must be non-negative")
        return v


class TradingPartnerCreate(TradingPartnerBase):
    """Schema for creating a TradingPartner (Supplier)"""
    id: str = Field(..., max_length=100, description="Trading partner ID/code")
    tpartner_type: TradingPartnerType = Field(TradingPartnerType.VENDOR, description="Partner type (use 'vendor' for suppliers)")
    geo_id: str = Field(..., max_length=100, description="Geography ID")
    eff_start_date: datetime = Field(..., description="Effective start date")
    eff_end_date: datetime = Field(datetime(9999, 12, 31), description="Effective end date (use 9999-12-31 for current)")


class TradingPartnerUpdate(TradingPartnerBase):
    """Schema for updating a TradingPartner (Supplier)"""
    # All fields optional for updates
    pass


class TradingPartnerResponse(TradingPartnerBase):
    """Schema for TradingPartner (Supplier) response"""
    id: str
    tpartner_type: str
    geo_id: str
    eff_start_date: datetime
    eff_end_date: datetime

    # Performance metrics (cached)
    on_time_delivery_rate: Optional[float] = Field(None, description="On-time delivery rate (%)")
    quality_rating: Optional[float] = Field(None, description="Quality rating (0-100)")
    lead_time_reliability: Optional[float] = Field(None, description="Lead time reliability (%)")
    total_spend_ytd: float = Field(0.0, description="Total spend year-to-date")

    # Audit fields
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    is_deleted: bool = False

    # Computed fields
    performance_score: Optional[float] = Field(None, description="Overall performance score (0-100)")

    class Config:
        from_attributes = True


class TradingPartnerList(BaseModel):
    """Schema for paginated list of TradingPartners"""
    items: List[TradingPartnerResponse]
    total: int
    page: int
    page_size: int
    pages: int


class TradingPartnerSummary(BaseModel):
    """Summary statistics for suppliers (type='vendor')"""
    total_suppliers: int
    active_suppliers: int
    inactive_suppliers: int
    by_tier: dict = Field(default_factory=dict, description="Count by tier")
    by_country: dict = Field(default_factory=dict, description="Count by country")
    avg_performance_score: Optional[float] = None
    avg_on_time_delivery: Optional[float] = None
    avg_quality_rating: Optional[float] = None
    high_risk_count: int = 0
    iso_certified_count: int = 0


# ============================================================================
# VendorProduct Schemas
# ============================================================================

class VendorProductBase(BaseModel):
    """Base schema for VendorProduct"""
    company_id: Optional[str] = Field(None, max_length=100)
    vendor_product_id: Optional[str] = Field(None, max_length=100, description="Vendor's item code")
    vendor_unit_cost: float = Field(..., ge=0, description="Vendor unit cost")
    currency: str = Field("USD", max_length=10)
    eff_start_date: datetime = Field(..., description="Effective start date")
    eff_end_date: Optional[datetime] = Field(None, description="Effective end date (null = no end)")
    is_active: str = Field("true", description="Active status: 'true' or 'false'")
    source: Optional[str] = Field(None, max_length=100)
    source_event_id: Optional[str] = Field(None, max_length=100)
    source_update_dttm: Optional[datetime] = None

    # Extensions
    priority: int = Field(1, ge=1, description="Multi-sourcing priority (1=primary, 2=secondary, etc.)")
    is_primary: bool = Field(False, description="Primary supplier flag")
    minimum_order_quantity: Optional[float] = Field(None, ge=0)
    maximum_order_quantity: Optional[float] = Field(None, ge=0)
    order_multiple: Optional[float] = Field(None, ge=0, description="Must order in multiples of this")
    vendor_item_name: Optional[str] = Field(None, max_length=255, description="Vendor's item name")

    @field_validator('is_active')
    @classmethod
    def validate_is_active(cls, v: str) -> str:
        """Validate is_active is 'true' or 'false'"""
        if v not in ['true', 'false']:
            raise ValueError("is_active must be 'true' or 'false'")
        return v


class VendorProductCreate(VendorProductBase):
    """Schema for creating a VendorProduct"""
    tpartner_id: str = Field(..., max_length=100, description="Trading partner ID")
    product_id: int = Field(..., gt=0, description="Product/Item ID")


class VendorProductUpdate(BaseModel):
    """Schema for updating a VendorProduct"""
    vendor_unit_cost: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=10)
    eff_end_date: Optional[datetime] = None
    is_active: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1)
    is_primary: Optional[bool] = None
    minimum_order_quantity: Optional[float] = Field(None, ge=0)
    maximum_order_quantity: Optional[float] = Field(None, ge=0)
    order_multiple: Optional[float] = Field(None, ge=0)
    vendor_item_name: Optional[str] = Field(None, max_length=255)


class VendorProductResponse(VendorProductBase):
    """Schema for VendorProduct response"""
    id: int
    tpartner_id: str
    product_id: int

    # Populated from relationships
    product_name: Optional[str] = None
    supplier_description: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VendorProductList(BaseModel):
    """Schema for paginated list of VendorProducts"""
    items: List[VendorProductResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ============================================================================
# VendorLeadTime Schemas
# ============================================================================

class VendorLeadTimeBase(BaseModel):
    """Base schema for VendorLeadTime"""
    # Hierarchy levels (most specific wins)
    company_id: Optional[str] = Field(None, max_length=100, description="Company-wide default")
    region_id: Optional[str] = Field(None, max_length=100, description="Region-specific")
    site_id: Optional[int] = Field(None, gt=0, description="Site-specific")
    product_group_id: Optional[str] = Field(None, max_length=100, description="Product group")
    product_id: Optional[int] = Field(None, gt=0, description="Product-specific (highest priority)")

    lead_time_days: float = Field(..., ge=0, description="Lead time in days")
    eff_start_date: datetime = Field(..., description="Effective start date")
    eff_end_date: Optional[datetime] = Field(None, description="Effective end date (null = no end)")
    source: Optional[str] = Field(None, max_length=100)
    source_event_id: Optional[str] = Field(None, max_length=100)
    source_update_dttm: Optional[datetime] = None

    # Extension
    lead_time_variability_days: Optional[float] = Field(None, ge=0, description="Standard deviation for stochastic planning")

    @field_validator('lead_time_days')
    @classmethod
    def validate_lead_time(cls, v: float) -> float:
        """Validate lead time is non-negative"""
        if v < 0:
            raise ValueError("lead_time_days must be non-negative")
        return v


class VendorLeadTimeCreate(VendorLeadTimeBase):
    """Schema for creating a VendorLeadTime"""
    tpartner_id: str = Field(..., max_length=100, description="Trading partner ID")


class VendorLeadTimeUpdate(BaseModel):
    """Schema for updating a VendorLeadTime"""
    lead_time_days: Optional[float] = Field(None, ge=0)
    eff_end_date: Optional[datetime] = None
    lead_time_variability_days: Optional[float] = Field(None, ge=0)


class VendorLeadTimeResponse(VendorLeadTimeBase):
    """Schema for VendorLeadTime response"""
    id: int
    tpartner_id: str

    # Populated from relationships
    supplier_description: Optional[str] = None
    product_name: Optional[str] = None
    site_name: Optional[str] = None

    # Hierarchy level indicator
    specificity_level: Optional[str] = Field(None, description="product > product_group > site > region > company")

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VendorLeadTimeList(BaseModel):
    """Schema for paginated list of VendorLeadTimes"""
    items: List[VendorLeadTimeResponse]
    total: int
    page: int
    page_size: int
    pages: int


class LeadTimeResolutionRequest(BaseModel):
    """Request schema for resolving lead time using hierarchy"""
    tpartner_id: str = Field(..., description="Trading partner ID")
    product_id: Optional[int] = Field(None, description="Product ID for resolution")
    site_id: Optional[int] = Field(None, description="Site ID for resolution")
    region_id: Optional[str] = Field(None, description="Region ID for resolution")
    product_group_id: Optional[str] = Field(None, description="Product group ID for resolution")
    company_id: Optional[str] = Field(None, description="Company ID for resolution")
    as_of_date: Optional[datetime] = Field(None, description="Date for temporal resolution (default: now)")


class LeadTimeResolutionResponse(BaseModel):
    """Response schema for lead time resolution"""
    tpartner_id: str
    lead_time_days: float
    lead_time_variability_days: Optional[float] = None
    resolution_level: str = Field(..., description="Which hierarchy level was used")
    lead_time_record_id: int
    eff_start_date: datetime
    eff_end_date: Optional[datetime] = None


# ============================================================================
# SupplierPerformance Schemas
# ============================================================================

class SupplierPerformanceBase(BaseModel):
    """Base schema for SupplierPerformance"""
    period_start: datetime
    period_end: datetime
    period_type: PerformancePeriodType = Field(PerformancePeriodType.MONTHLY)

    # Delivery metrics
    orders_placed: int = Field(0, ge=0)
    orders_delivered_on_time: int = Field(0, ge=0)
    orders_delivered_late: int = Field(0, ge=0)
    average_days_late: Optional[float] = Field(None, ge=0)

    # Quality metrics
    units_received: int = Field(0, ge=0)
    units_accepted: int = Field(0, ge=0)
    units_rejected: int = Field(0, ge=0)
    reject_rate_percent: Optional[float] = Field(None, ge=0, le=100)

    # Lead time metrics
    average_lead_time_days: Optional[float] = Field(None, ge=0)
    std_dev_lead_time_days: Optional[float] = Field(None, ge=0)

    # Cost metrics
    total_spend: float = Field(0.0, ge=0)
    currency: str = Field("USD", max_length=10)


class SupplierPerformanceCreate(SupplierPerformanceBase):
    """Schema for creating a SupplierPerformance record"""
    tpartner_id: str = Field(..., max_length=100, description="Trading partner ID")


class SupplierPerformanceResponse(SupplierPerformanceBase):
    """Schema for SupplierPerformance response"""
    id: int
    tpartner_id: str

    # Calculated metrics
    on_time_delivery_rate: Optional[float] = Field(None, description="Percentage (0-100)")
    quality_rating: Optional[float] = Field(None, description="Score (0-100)")
    overall_performance_score: Optional[float] = Field(None, description="Score (0-100)")

    # Populated from relationships
    supplier_description: Optional[str] = None

    created_at: datetime

    class Config:
        from_attributes = True


class SupplierPerformanceList(BaseModel):
    """Schema for paginated list of SupplierPerformance records"""
    items: List[SupplierPerformanceResponse]
    total: int
    page: int
    page_size: int
    pages: int


class SupplierPerformanceTrend(BaseModel):
    """Trend analysis for supplier performance over time"""
    tpartner_id: str
    supplier_description: Optional[str] = None
    period_type: PerformancePeriodType
    periods: List[SupplierPerformanceResponse]

    # Trend indicators
    on_time_delivery_trend: str = Field(..., description="IMPROVING, STABLE, DECLINING")
    quality_trend: str = Field(..., description="IMPROVING, STABLE, DECLINING")
    spend_trend: str = Field(..., description="INCREASING, STABLE, DECREASING")

    # Aggregated metrics
    avg_on_time_delivery: Optional[float] = None
    avg_quality_rating: Optional[float] = None
    total_spend: float = 0.0


# ============================================================================
# Multi-Sourcing Schemas
# ============================================================================

class SourceRecommendation(BaseModel):
    """Recommendation for supplier selection in multi-sourcing scenario"""
    tpartner_id: str
    supplier_description: Optional[str] = None
    priority: int
    is_primary: bool
    vendor_unit_cost: float
    currency: str
    lead_time_days: float
    lead_time_variability_days: Optional[float] = None
    available_capacity: Optional[float] = None
    performance_score: Optional[float] = None
    risk_level: Optional[str] = None
    recommendation_reason: str = Field(..., description="Why this supplier is recommended")


class MultiSourcingAnalysis(BaseModel):
    """Analysis of multi-sourcing options for a product"""
    product_id: int
    product_name: Optional[str] = None
    total_suppliers: int
    active_suppliers: int
    primary_supplier: Optional[SourceRecommendation] = None
    alternative_suppliers: List[SourceRecommendation] = Field(default_factory=list)

    # Risk analysis
    single_source_risk: bool = Field(..., description="True if only one supplier")
    geographic_diversity: bool = Field(..., description="True if suppliers in different regions")
    cost_variance_percent: Optional[float] = Field(None, description="Cost variance across suppliers")
    lead_time_variance_days: Optional[float] = Field(None, description="Lead time variance across suppliers")


# ============================================================================
# Type Aliases for API Compatibility
# ============================================================================

# Supplier-specific aliases (more intuitive naming)
SupplierCreate = TradingPartnerCreate
SupplierUpdate = TradingPartnerUpdate
SupplierResponse = TradingPartnerResponse
SupplierList = TradingPartnerList
SupplierSummary = TradingPartnerSummary
