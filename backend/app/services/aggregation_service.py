"""
Aggregation Service for Planning Hierarchies

Provides generic aggregation of data across planning hierarchies following
Powell's state abstraction principles. This service is hierarchy-agnostic
and can aggregate any metric across site, product, or time dimensions.

Powell Framework Alignment:
- Aggregation = State Abstraction (reduce dimensionality for tractable optimization)
- Consistency requirement: V_agg(S_agg) ≈ E[V_detail(S) | disaggregate(S_agg)]
- Higher-level plans set constraints (θ) for lower-level decisions

Key Principles:
1. Aggregation preserves totals (demand, inventory, capacity)
2. Aggregation computes weighted averages for rates (lead time, cost, yield)
3. Aggregation tracks membership for later disaggregation
4. Statistical moments are propagated (mean, variance, percentiles)
"""

from typing import Dict, List, Optional, Tuple, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import date, datetime, timedelta
from collections import defaultdict
import math
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.planning_hierarchy import (
    PlanningHierarchyConfig,
    SiteHierarchyNode,
    ProductHierarchyNode,
    PlanningType,
    SiteHierarchyLevel,
    ProductHierarchyLevel,
    TimeBucketType
)

logger = logging.getLogger(__name__)


# ============================================================================
# Aggregation Methods
# ============================================================================

class AggregationMethod(str, Enum):
    """Methods for aggregating values."""
    SUM = "sum"                    # Total (demand, inventory, capacity)
    AVERAGE = "average"            # Simple average
    WEIGHTED_AVERAGE = "weighted"  # Weighted by another metric (e.g., demand-weighted lead time)
    MIN = "min"                    # Minimum value
    MAX = "max"                    # Maximum value
    COUNT = "count"                # Count of members
    VARIANCE = "variance"          # Pooled variance
    PERCENTILE = "percentile"      # Aggregate percentile (requires distribution assumption)


@dataclass
class AggregationRule:
    """Rule for aggregating a specific metric."""
    metric_name: str
    method: AggregationMethod
    weight_metric: Optional[str] = None  # For weighted average
    percentile_value: Optional[float] = None  # For percentile method (e.g., 0.90)


# Default aggregation rules for common planning metrics
DEFAULT_AGGREGATION_RULES = {
    # Additive metrics (SUM)
    "demand": AggregationRule("demand", AggregationMethod.SUM),
    "forecast": AggregationRule("forecast", AggregationMethod.SUM),
    "inventory": AggregationRule("inventory", AggregationMethod.SUM),
    "on_hand": AggregationRule("on_hand", AggregationMethod.SUM),
    "in_transit": AggregationRule("in_transit", AggregationMethod.SUM),
    "backlog": AggregationRule("backlog", AggregationMethod.SUM),
    "capacity": AggregationRule("capacity", AggregationMethod.SUM),
    "production": AggregationRule("production", AggregationMethod.SUM),
    "orders": AggregationRule("orders", AggregationMethod.SUM),
    "shipments": AggregationRule("shipments", AggregationMethod.SUM),
    "cost_total": AggregationRule("cost_total", AggregationMethod.SUM),
    "revenue": AggregationRule("revenue", AggregationMethod.SUM),

    # Rate metrics (WEIGHTED_AVERAGE by demand)
    "lead_time": AggregationRule("lead_time", AggregationMethod.WEIGHTED_AVERAGE, "demand"),
    "unit_cost": AggregationRule("unit_cost", AggregationMethod.WEIGHTED_AVERAGE, "demand"),
    "unit_price": AggregationRule("unit_price", AggregationMethod.WEIGHTED_AVERAGE, "demand"),
    "holding_cost_rate": AggregationRule("holding_cost_rate", AggregationMethod.WEIGHTED_AVERAGE, "inventory"),
    "service_level": AggregationRule("service_level", AggregationMethod.WEIGHTED_AVERAGE, "demand"),
    "fill_rate": AggregationRule("fill_rate", AggregationMethod.WEIGHTED_AVERAGE, "demand"),
    "yield_rate": AggregationRule("yield_rate", AggregationMethod.WEIGHTED_AVERAGE, "production"),

    # Constraint metrics
    "max_capacity": AggregationRule("max_capacity", AggregationMethod.SUM),
    "min_order_qty": AggregationRule("min_order_qty", AggregationMethod.SUM),

    # Statistical metrics
    "demand_std": AggregationRule("demand_std", AggregationMethod.VARIANCE),
    "lead_time_std": AggregationRule("lead_time_std", AggregationMethod.VARIANCE),
}


# ============================================================================
# Aggregated Data Structures
# ============================================================================

@dataclass
class AggregatedValue:
    """A single aggregated value with metadata."""
    value: float
    method: AggregationMethod
    member_count: int
    member_keys: List[str] = field(default_factory=list)
    member_values: Dict[str, float] = field(default_factory=dict)  # For disaggregation
    weight_total: float = 0.0  # Sum of weights (for weighted average)


@dataclass
class AggregatedRecord:
    """
    A record at an aggregated hierarchy level.

    Contains all metrics aggregated from detailed records,
    plus membership information for disaggregation.
    """
    # Hierarchy keys
    site_key: str  # Aggregated site identifier (e.g., "REGION_AMERICAS")
    product_key: str  # Aggregated product identifier (e.g., "FAMILY_BEVERAGE")
    time_key: str  # Aggregated time identifier (e.g., "2026-01" for monthly)

    # Hierarchy levels
    site_level: SiteHierarchyLevel
    product_level: ProductHierarchyLevel
    time_bucket: TimeBucketType

    # Aggregated metrics
    metrics: Dict[str, AggregatedValue] = field(default_factory=dict)

    # Membership tracking (for disaggregation)
    member_sites: List[str] = field(default_factory=list)
    member_products: List[str] = field(default_factory=list)
    member_time_periods: List[str] = field(default_factory=list)

    # Disaggregation weights (learned or historical)
    # Key: "site_product_time" -> weight (proportion)
    disaggregation_weights: Dict[str, float] = field(default_factory=dict)

    def get_metric(self, name: str) -> Optional[float]:
        """Get aggregated metric value."""
        if name in self.metrics:
            return self.metrics[name].value
        return None

    def set_metric(self, name: str, value: AggregatedValue):
        """Set aggregated metric value."""
        self.metrics[name] = value


@dataclass
class DetailedRecord:
    """A record at the detailed (SKU x Site x Day) level."""
    site_key: str
    product_key: str
    time_key: str
    metrics: Dict[str, float] = field(default_factory=dict)

    # Hierarchy path information (for aggregation)
    site_path: Optional[str] = None  # e.g., "COMPANY/REGION/COUNTRY/SITE"
    product_path: Optional[str] = None  # e.g., "CATEGORY/FAMILY/GROUP/SKU"


# ============================================================================
# Aggregation Service
# ============================================================================

class AggregationService:
    """
    Generic service for aggregating data across planning hierarchies.

    This service:
    1. Aggregates detailed records to any hierarchy level
    2. Supports multiple aggregation methods per metric
    3. Tracks membership for disaggregation
    4. Computes statistical moments

    Usage:
        service = AggregationService(db, tenant_id)
        await service.load_hierarchies()

        # Aggregate demand to S&OP level (Country x Family x Month)
        aggregated = service.aggregate(
            detailed_records,
            target_site_level=SiteHierarchyLevel.COUNTRY,
            target_product_level=ProductHierarchyLevel.FAMILY,
            target_time_bucket=TimeBucketType.MONTH
        )
    """

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: int,
        aggregation_rules: Optional[Dict[str, AggregationRule]] = None
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.rules = aggregation_rules or DEFAULT_AGGREGATION_RULES

        # Hierarchy caches
        self._site_hierarchy: Dict[str, Dict] = {}  # code -> {level, parent, path, ...}
        self._product_hierarchy: Dict[str, Dict] = {}
        self._hierarchies_loaded = False

    async def load_hierarchies(self):
        """Load site and product hierarchies from database."""
        await self._load_site_hierarchy()
        await self._load_product_hierarchy()
        self._hierarchies_loaded = True

    async def _load_site_hierarchy(self):
        """Load site hierarchy structure."""
        result = await self.db.execute(
            select(SiteHierarchyNode).where(
                SiteHierarchyNode.tenant_id == self.tenant_id
            )
        )
        nodes = result.scalars().all()

        for node in nodes:
            self._site_hierarchy[node.code] = {
                'id': node.id,
                'code': node.code,
                'name': node.name,
                'level': node.hierarchy_level,
                'parent_id': node.parent_id,
                'path': node.hierarchy_path,
                'depth': node.depth
            }

        # Build parent lookup by level
        for code, data in self._site_hierarchy.items():
            path_parts = data['path'].split('/')
            data['ancestors'] = {}
            for i, level in enumerate([
                SiteHierarchyLevel.COMPANY,
                SiteHierarchyLevel.REGION,
                SiteHierarchyLevel.COUNTRY,
                SiteHierarchyLevel.STATE,
                SiteHierarchyLevel.SITE
            ]):
                if i < len(path_parts):
                    data['ancestors'][level] = path_parts[i]

    async def _load_product_hierarchy(self):
        """Load product hierarchy structure."""
        result = await self.db.execute(
            select(ProductHierarchyNode).where(
                ProductHierarchyNode.tenant_id == self.tenant_id
            )
        )
        nodes = result.scalars().all()

        for node in nodes:
            self._product_hierarchy[node.code] = {
                'id': node.id,
                'code': node.code,
                'name': node.name,
                'level': node.hierarchy_level,
                'parent_id': node.parent_id,
                'path': node.hierarchy_path,
                'depth': node.depth,
                'split_factors': node.demand_split_factors or {}
            }

        # Build parent lookup by level
        for code, data in self._product_hierarchy.items():
            path_parts = data['path'].split('/')
            data['ancestors'] = {}
            for i, level in enumerate([
                ProductHierarchyLevel.CATEGORY,
                ProductHierarchyLevel.FAMILY,
                ProductHierarchyLevel.GROUP,
                ProductHierarchyLevel.PRODUCT
            ]):
                if i < len(path_parts):
                    data['ancestors'][level] = path_parts[i]

    def get_site_ancestor(self, site_code: str, target_level: SiteHierarchyLevel) -> Optional[str]:
        """Get the ancestor at a target level for a site."""
        if site_code in self._site_hierarchy:
            return self._site_hierarchy[site_code].get('ancestors', {}).get(target_level)
        return None

    def get_product_ancestor(self, product_code: str, target_level: ProductHierarchyLevel) -> Optional[str]:
        """Get the ancestor at a target level for a product."""
        if product_code in self._product_hierarchy:
            return self._product_hierarchy[product_code].get('ancestors', {}).get(target_level)
        return None

    def aggregate_time_key(self, time_key: str, target_bucket: TimeBucketType) -> str:
        """
        Aggregate a time key to a coarser bucket.

        Supports various input formats:
        - ISO date: "2026-01-15"
        - ISO datetime: "2026-01-15T14:30:00"
        - Year-month: "2026-01"
        - Year-week: "2026-W03"
        """
        # Parse the time key
        try:
            if 'T' in time_key:
                dt = datetime.fromisoformat(time_key)
            elif '-W' in time_key:
                year, week = time_key.split('-W')
                dt = datetime.strptime(f"{year}-W{week}-1", "%Y-W%W-%w")
            elif len(time_key) == 7:  # YYYY-MM
                dt = datetime.strptime(time_key, "%Y-%m")
            else:
                dt = datetime.fromisoformat(time_key)
        except ValueError:
            return time_key  # Return original if unparseable

        # Aggregate to target bucket
        if target_bucket == TimeBucketType.HOUR:
            return dt.strftime("%Y-%m-%dT%H:00")
        elif target_bucket == TimeBucketType.DAY:
            return dt.strftime("%Y-%m-%d")
        elif target_bucket == TimeBucketType.WEEK:
            return dt.strftime("%Y-W%W")
        elif target_bucket == TimeBucketType.MONTH:
            return dt.strftime("%Y-%m")
        elif target_bucket == TimeBucketType.QUARTER:
            quarter = (dt.month - 1) // 3 + 1
            return f"{dt.year}-Q{quarter}"
        elif target_bucket == TimeBucketType.YEAR:
            return str(dt.year)

        return time_key

    def aggregate(
        self,
        detailed_records: List[DetailedRecord],
        target_site_level: SiteHierarchyLevel,
        target_product_level: ProductHierarchyLevel,
        target_time_bucket: TimeBucketType,
        custom_rules: Optional[Dict[str, AggregationRule]] = None
    ) -> List[AggregatedRecord]:
        """
        Aggregate detailed records to target hierarchy levels.

        Args:
            detailed_records: List of records at detailed level
            target_site_level: Target site hierarchy level
            target_product_level: Target product hierarchy level
            target_time_bucket: Target time bucket
            custom_rules: Optional custom aggregation rules

        Returns:
            List of aggregated records
        """
        if not self._hierarchies_loaded:
            raise RuntimeError("Hierarchies not loaded. Call load_hierarchies() first.")

        rules = {**self.rules, **(custom_rules or {})}

        # Group records by aggregated keys
        grouped: Dict[Tuple[str, str, str], List[DetailedRecord]] = defaultdict(list)

        for record in detailed_records:
            # Get aggregated keys
            agg_site = self.get_site_ancestor(record.site_key, target_site_level) or record.site_key
            agg_product = self.get_product_ancestor(record.product_key, target_product_level) or record.product_key
            agg_time = self.aggregate_time_key(record.time_key, target_time_bucket)

            key = (agg_site, agg_product, agg_time)
            grouped[key].append(record)

        # Aggregate each group
        aggregated_records = []

        for (site_key, product_key, time_key), records in grouped.items():
            agg_record = AggregatedRecord(
                site_key=site_key,
                product_key=product_key,
                time_key=time_key,
                site_level=target_site_level,
                product_level=target_product_level,
                time_bucket=target_time_bucket
            )

            # Track membership
            for record in records:
                if record.site_key not in agg_record.member_sites:
                    agg_record.member_sites.append(record.site_key)
                if record.product_key not in agg_record.member_products:
                    agg_record.member_products.append(record.product_key)
                if record.time_key not in agg_record.member_time_periods:
                    agg_record.member_time_periods.append(record.time_key)

            # Aggregate each metric
            all_metrics = set()
            for record in records:
                all_metrics.update(record.metrics.keys())

            for metric_name in all_metrics:
                rule = rules.get(metric_name, AggregationRule(metric_name, AggregationMethod.SUM))
                agg_value = self._aggregate_metric(records, metric_name, rule)
                agg_record.set_metric(metric_name, agg_value)

            # Compute disaggregation weights (based on primary metric, usually demand)
            self._compute_disaggregation_weights(agg_record, records, "demand")

            aggregated_records.append(agg_record)

        return aggregated_records

    def _aggregate_metric(
        self,
        records: List[DetailedRecord],
        metric_name: str,
        rule: AggregationRule
    ) -> AggregatedValue:
        """Aggregate a single metric across records."""
        values = []
        weights = []
        member_values = {}

        for record in records:
            if metric_name in record.metrics:
                value = record.metrics[metric_name]
                values.append(value)
                member_key = f"{record.site_key}_{record.product_key}_{record.time_key}"
                member_values[member_key] = value

                # Get weight if needed
                if rule.weight_metric and rule.weight_metric in record.metrics:
                    weights.append(record.metrics[rule.weight_metric])
                else:
                    weights.append(1.0)

        if not values:
            return AggregatedValue(
                value=0.0,
                method=rule.method,
                member_count=0
            )

        # Apply aggregation method
        if rule.method == AggregationMethod.SUM:
            agg_value = sum(values)
        elif rule.method == AggregationMethod.AVERAGE:
            agg_value = sum(values) / len(values)
        elif rule.method == AggregationMethod.WEIGHTED_AVERAGE:
            total_weight = sum(weights)
            if total_weight > 0:
                agg_value = sum(v * w for v, w in zip(values, weights)) / total_weight
            else:
                agg_value = sum(values) / len(values)
        elif rule.method == AggregationMethod.MIN:
            agg_value = min(values)
        elif rule.method == AggregationMethod.MAX:
            agg_value = max(values)
        elif rule.method == AggregationMethod.COUNT:
            agg_value = len(values)
        elif rule.method == AggregationMethod.VARIANCE:
            # Pooled variance: sum of variances (assumes independence)
            agg_value = math.sqrt(sum(v**2 for v in values))
        elif rule.method == AggregationMethod.PERCENTILE:
            # Approximate percentile aggregation
            p = rule.percentile_value or 0.5
            sorted_values = sorted(values)
            idx = int(p * (len(sorted_values) - 1))
            agg_value = sorted_values[idx]
        else:
            agg_value = sum(values)

        return AggregatedValue(
            value=agg_value,
            method=rule.method,
            member_count=len(values),
            member_keys=list(member_values.keys()),
            member_values=member_values,
            weight_total=sum(weights)
        )

    def _compute_disaggregation_weights(
        self,
        agg_record: AggregatedRecord,
        detailed_records: List[DetailedRecord],
        weight_metric: str
    ):
        """
        Compute disaggregation weights based on a metric (typically demand).

        These weights will be used by the DisaggregationService to split
        aggregated plans back to detailed level.
        """
        total = 0.0
        weights = {}

        for record in detailed_records:
            key = f"{record.site_key}_{record.product_key}_{record.time_key}"
            value = record.metrics.get(weight_metric, 1.0)
            weights[key] = value
            total += value

        # Normalize to proportions
        if total > 0:
            agg_record.disaggregation_weights = {
                k: v / total for k, v in weights.items()
            }
        else:
            # Equal weights if no data
            n = len(detailed_records)
            agg_record.disaggregation_weights = {
                f"{r.site_key}_{r.product_key}_{r.time_key}": 1.0 / n
                for r in detailed_records
            }


# ============================================================================
# Convenience Functions
# ============================================================================

async def aggregate_to_sop_level(
    db: AsyncSession,
    tenant_id: int,
    detailed_records: List[DetailedRecord]
) -> List[AggregatedRecord]:
    """Aggregate records to S&OP level (Country x Family x Month)."""
    service = AggregationService(db, tenant_id)
    await service.load_hierarchies()
    return service.aggregate(
        detailed_records,
        target_site_level=SiteHierarchyLevel.COUNTRY,
        target_product_level=ProductHierarchyLevel.FAMILY,
        target_time_bucket=TimeBucketType.MONTH
    )


async def aggregate_to_mps_level(
    db: AsyncSession,
    tenant_id: int,
    detailed_records: List[DetailedRecord]
) -> List[AggregatedRecord]:
    """Aggregate records to MPS level (Site x Group x Week)."""
    service = AggregationService(db, tenant_id)
    await service.load_hierarchies()
    return service.aggregate(
        detailed_records,
        target_site_level=SiteHierarchyLevel.SITE,
        target_product_level=ProductHierarchyLevel.GROUP,
        target_time_bucket=TimeBucketType.WEEK
    )
