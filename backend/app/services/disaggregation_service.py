"""
Disaggregation Service for Planning Hierarchies

Provides generic disaggregation of aggregated plans back to detailed levels.
This service implements Powell's insight that disaggregation is itself a
policy that can be learned and optimized.

Powell Framework Alignment:
- Disaggregation = Policy for allocating aggregated quantities to detail
- Three approaches supported:
  1. PFA (Policy Function Approximation): Historical proportions (simple, fast)
  2. CFA (Cost Function Approximation): Parameterized splits (θ = learned proportions)
  3. VFA (Value Function Approximation): Value-based allocation (maximize expected value)

Consistency Requirement:
- Sum of disaggregated values must equal aggregated value (conservation)
- Disaggregated values should respect constraints (min/max, capacity)
- V_detail(disaggregated) ≈ V_aggregated (value consistency)

Disaggregation Methods:
1. PROPORTIONAL: Use historical demand proportions
2. EQUAL: Equal split across members
3. CAPACITY_WEIGHTED: Weight by available capacity
4. FORECAST_DRIVEN: Use bottom-up forecasts
5. LEARNED: ML-based splits from historical data
6. VALUE_BASED: Allocate to maximize expected value (VFA)
"""

from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import date, datetime, timedelta
from collections import defaultdict
import math
import logging
import numpy as np

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.planning_hierarchy import (
    SiteHierarchyNode,
    ProductHierarchyNode,
    SiteHierarchyLevel,
    ProductHierarchyLevel,
    TimeBucketType
)
from app.services.aggregation_service import AggregatedRecord, DetailedRecord, AggregatedValue

logger = logging.getLogger(__name__)


# ============================================================================
# Disaggregation Methods
# ============================================================================

class DisaggregationMethod(str, Enum):
    """Methods for disaggregating values."""
    PROPORTIONAL = "proportional"      # Historical demand proportions
    EQUAL = "equal"                    # Equal split across members
    CAPACITY_WEIGHTED = "capacity"     # Weight by capacity
    FORECAST_DRIVEN = "forecast"       # Use bottom-up forecasts
    LEARNED = "learned"                # ML-based learned splits
    VALUE_BASED = "value"              # VFA - allocate to maximize value
    CONSTRAINT_AWARE = "constrained"   # Respect min/max constraints


@dataclass
class DisaggregationRule:
    """Rule for disaggregating a specific metric."""
    metric_name: str
    method: DisaggregationMethod
    weight_metric: Optional[str] = None  # Metric to use for proportional weights
    min_value: Optional[float] = None    # Minimum disaggregated value
    max_value: Optional[float] = None    # Maximum disaggregated value
    round_to_integer: bool = False       # Round results to integers


# Default disaggregation rules
DEFAULT_DISAGGREGATION_RULES = {
    # Quantity metrics (use demand proportions)
    "demand": DisaggregationRule("demand", DisaggregationMethod.PROPORTIONAL, "historical_demand"),
    "forecast": DisaggregationRule("forecast", DisaggregationMethod.PROPORTIONAL, "historical_demand"),
    "production": DisaggregationRule("production", DisaggregationMethod.CAPACITY_WEIGHTED, "capacity"),
    "orders": DisaggregationRule("orders", DisaggregationMethod.PROPORTIONAL, "historical_demand", round_to_integer=True),
    "inventory_target": DisaggregationRule("inventory_target", DisaggregationMethod.PROPORTIONAL, "historical_demand"),

    # Capacity-driven metrics
    "capacity_plan": DisaggregationRule("capacity_plan", DisaggregationMethod.CAPACITY_WEIGHTED, "capacity"),
    "safety_stock": DisaggregationRule("safety_stock", DisaggregationMethod.PROPORTIONAL, "historical_demand"),

    # Cost metrics (proportional to quantity)
    "cost_budget": DisaggregationRule("cost_budget", DisaggregationMethod.PROPORTIONAL, "demand"),
}


# ============================================================================
# Learned Splits Storage
# ============================================================================

@dataclass
class LearnedSplit:
    """
    Learned disaggregation split for a hierarchy combination.

    Stores the learned proportions for splitting an aggregated value
    to detailed members, along with confidence and update metadata.
    """
    aggregated_key: str  # "site_product_time" at aggregated level
    member_proportions: Dict[str, float]  # member_key -> proportion (sums to 1.0)
    confidence: float  # 0-1, higher = more confident
    sample_count: int  # Number of observations used to learn
    last_updated: datetime
    method: str  # How splits were learned (e.g., "historical", "ml", "manual")

    def get_proportion(self, member_key: str) -> float:
        """Get proportion for a member, defaulting to equal split."""
        if member_key in self.member_proportions:
            return self.member_proportions[member_key]
        # Default: equal split among known members
        if self.member_proportions:
            return 1.0 / len(self.member_proportions)
        return 0.0


@dataclass
class DisaggregatedRecord:
    """A disaggregated record at detailed level."""
    site_key: str
    product_key: str
    time_key: str
    metrics: Dict[str, float] = field(default_factory=dict)

    # Source aggregated record
    source_site_key: str = ""
    source_product_key: str = ""
    source_time_key: str = ""

    # Disaggregation metadata
    proportion_used: float = 0.0  # The proportion used for this member
    method_used: DisaggregationMethod = DisaggregationMethod.PROPORTIONAL


# ============================================================================
# Disaggregation Service
# ============================================================================

class DisaggregationService:
    """
    Generic service for disaggregating aggregated plans to detailed levels.

    This service implements Powell's framework where disaggregation is a policy:
    - Simple PFA: Historical proportions (default)
    - CFA: Parameterized splits that can be optimized
    - VFA: Value-based allocation

    Usage:
        service = DisaggregationService(db, tenant_id)
        await service.load_hierarchies()
        await service.load_learned_splits()  # Optional: load ML-based splits

        # Disaggregate S&OP plan to MPS level
        detailed = service.disaggregate(
            aggregated_records,
            target_site_level=SiteHierarchyLevel.SITE,
            target_product_level=ProductHierarchyLevel.GROUP,
            target_time_bucket=TimeBucketType.WEEK
        )
    """

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: int,
        disaggregation_rules: Optional[Dict[str, DisaggregationRule]] = None
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.rules = disaggregation_rules or DEFAULT_DISAGGREGATION_RULES

        # Hierarchy caches
        self._site_hierarchy: Dict[str, Dict] = {}
        self._product_hierarchy: Dict[str, Dict] = {}
        self._hierarchies_loaded = False

        # Learned splits cache
        self._learned_splits: Dict[str, LearnedSplit] = {}

        # Historical data cache (for computing proportions)
        self._historical_data: Dict[str, Dict[str, float]] = {}

    async def load_hierarchies(self):
        """Load site and product hierarchies."""
        await self._load_site_hierarchy()
        await self._load_product_hierarchy()
        self._hierarchies_loaded = True

    async def _load_site_hierarchy(self):
        """Load site hierarchy with children information."""
        result = await self.db.execute(
            select(SiteHierarchyNode).where(
                SiteHierarchyNode.tenant_id == self.tenant_id
            )
        )
        nodes = result.scalars().all()

        # Build hierarchy with children
        for node in nodes:
            self._site_hierarchy[node.code] = {
                'id': node.id,
                'code': node.code,
                'name': node.name,
                'level': node.hierarchy_level,
                'parent_id': node.parent_id,
                'path': node.hierarchy_path,
                'children': []
            }

        # Link children to parents
        for node in nodes:
            if node.parent_id:
                parent_code = next(
                    (n['code'] for n in self._site_hierarchy.values()
                     if self._site_hierarchy.get(n['code'], {}).get('id') == node.parent_id),
                    None
                )
                if parent_code and parent_code in self._site_hierarchy:
                    self._site_hierarchy[parent_code]['children'].append(node.code)

    async def _load_product_hierarchy(self):
        """Load product hierarchy with children and split factors."""
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
                'children': [],
                'split_factors': node.demand_split_factors or {}
            }

        # Link children
        for node in nodes:
            if node.parent_id:
                parent_code = next(
                    (n['code'] for n in self._product_hierarchy.values()
                     if self._product_hierarchy.get(n['code'], {}).get('id') == node.parent_id),
                    None
                )
                if parent_code and parent_code in self._product_hierarchy:
                    self._product_hierarchy[parent_code]['children'].append(node.code)

    async def load_learned_splits(self, metric_name: str = "demand"):
        """
        Load learned disaggregation splits from database or ML model.

        This implements Powell's CFA approach where splits are parameters
        that have been learned/optimized.
        """
        # In a full implementation, this would load from a database table
        # or ML model. For now, we compute from hierarchy split_factors.
        for code, data in self._product_hierarchy.items():
            if data.get('split_factors'):
                key = f"*_{code}_*"  # Wildcard site and time
                self._learned_splits[key] = LearnedSplit(
                    aggregated_key=key,
                    member_proportions=data['split_factors'],
                    confidence=0.9,
                    sample_count=100,
                    last_updated=datetime.now(),
                    method="hierarchy_defined"
                )

    def set_historical_proportions(
        self,
        aggregated_key: str,
        member_proportions: Dict[str, float]
    ):
        """
        Set historical proportions for disaggregation.

        Called by external data loading to provide historical demand
        proportions for PFA-style disaggregation.
        """
        self._historical_data[aggregated_key] = member_proportions

    def learn_splits_from_history(
        self,
        historical_records: List[DetailedRecord],
        aggregated_records: List[AggregatedRecord],
        metric_name: str = "demand"
    ):
        """
        Learn disaggregation splits from historical data.

        This implements Powell's insight that disaggregation proportions
        can be learned from data rather than assumed.
        """
        # Group detailed records by their aggregated parent
        for agg_record in aggregated_records:
            # Find all detailed records that belong to this aggregate
            members = []
            total_value = 0.0

            for detail in historical_records:
                if (detail.site_key in agg_record.member_sites and
                    detail.product_key in agg_record.member_products and
                    detail.time_key in agg_record.member_time_periods):

                    value = detail.metrics.get(metric_name, 0.0)
                    member_key = f"{detail.site_key}_{detail.product_key}_{detail.time_key}"
                    members.append((member_key, value))
                    total_value += value

            # Compute proportions
            if total_value > 0:
                proportions = {k: v / total_value for k, v in members}
            else:
                n = len(members)
                proportions = {k: 1.0 / n for k, _ in members} if n > 0 else {}

            # Store learned split
            agg_key = f"{agg_record.site_key}_{agg_record.product_key}_{agg_record.time_key}"
            self._learned_splits[agg_key] = LearnedSplit(
                aggregated_key=agg_key,
                member_proportions=proportions,
                confidence=min(0.95, len(members) / 100),  # Confidence grows with data
                sample_count=len(members),
                last_updated=datetime.now(),
                method="historical"
            )

    def disaggregate(
        self,
        aggregated_records: List[AggregatedRecord],
        target_site_level: SiteHierarchyLevel,
        target_product_level: ProductHierarchyLevel,
        target_time_bucket: TimeBucketType,
        custom_rules: Optional[Dict[str, DisaggregationRule]] = None,
        default_method: DisaggregationMethod = DisaggregationMethod.PROPORTIONAL
    ) -> List[DisaggregatedRecord]:
        """
        Disaggregate aggregated records to target hierarchy levels.

        Args:
            aggregated_records: Records at aggregated level
            target_site_level: Target site hierarchy level
            target_product_level: Target product hierarchy level
            target_time_bucket: Target time bucket
            custom_rules: Optional custom disaggregation rules
            default_method: Default method if no rule specified

        Returns:
            List of disaggregated records at target level
        """
        if not self._hierarchies_loaded:
            raise RuntimeError("Hierarchies not loaded. Call load_hierarchies() first.")

        rules = {**self.rules, **(custom_rules or {})}
        result = []

        for agg_record in aggregated_records:
            # Get member keys at target level
            target_members = self._get_target_members(
                agg_record, target_site_level, target_product_level, target_time_bucket
            )

            if not target_members:
                logger.warning(f"No target members found for {agg_record.site_key}/{agg_record.product_key}")
                continue

            # Get proportions for disaggregation
            proportions = self._get_disaggregation_proportions(
                agg_record, target_members, default_method
            )

            # Disaggregate each metric
            for member_key, proportion in proportions.items():
                site_key, product_key, time_key = self._parse_member_key(member_key)

                disagg_record = DisaggregatedRecord(
                    site_key=site_key,
                    product_key=product_key,
                    time_key=time_key,
                    source_site_key=agg_record.site_key,
                    source_product_key=agg_record.product_key,
                    source_time_key=agg_record.time_key,
                    proportion_used=proportion
                )

                for metric_name, agg_value in agg_record.metrics.items():
                    rule = rules.get(
                        metric_name,
                        DisaggregationRule(metric_name, default_method)
                    )

                    # Compute disaggregated value
                    disagg_value = self._disaggregate_value(
                        agg_value.value, proportion, rule, member_key, agg_record
                    )

                    disagg_record.metrics[metric_name] = disagg_value
                    disagg_record.method_used = rule.method

                result.append(disagg_record)

        return result

    def _get_target_members(
        self,
        agg_record: AggregatedRecord,
        target_site_level: SiteHierarchyLevel,
        target_product_level: ProductHierarchyLevel,
        target_time_bucket: TimeBucketType
    ) -> List[str]:
        """Get member keys at the target hierarchy level."""
        members = []

        # Get sites at target level under this aggregate
        target_sites = self._get_descendants_at_level(
            agg_record.site_key, target_site_level, self._site_hierarchy
        )
        if not target_sites:
            target_sites = [agg_record.site_key]

        # Get products at target level under this aggregate
        target_products = self._get_descendants_at_level(
            agg_record.product_key, target_product_level, self._product_hierarchy
        )
        if not target_products:
            target_products = [agg_record.product_key]

        # Get time periods at target bucket
        target_times = self._expand_time_bucket(
            agg_record.time_key, agg_record.time_bucket, target_time_bucket
        )
        if not target_times:
            target_times = [agg_record.time_key]

        # Generate all combinations
        for site in target_sites:
            for product in target_products:
                for time in target_times:
                    members.append(f"{site}_{product}_{time}")

        return members

    def _get_descendants_at_level(
        self,
        parent_code: str,
        target_level: Enum,
        hierarchy: Dict[str, Dict]
    ) -> List[str]:
        """Get all descendants at a specific hierarchy level."""
        if parent_code not in hierarchy:
            return []

        parent_data = hierarchy[parent_code]
        parent_level = parent_data['level']

        # If already at or below target level, return self
        if self._level_depth(parent_level) >= self._level_depth(target_level):
            return [parent_code]

        # Recursively get descendants
        descendants = []
        for child_code in parent_data.get('children', []):
            if child_code in hierarchy:
                child_level = hierarchy[child_code]['level']
                if child_level == target_level:
                    descendants.append(child_code)
                else:
                    descendants.extend(
                        self._get_descendants_at_level(child_code, target_level, hierarchy)
                    )

        return descendants if descendants else [parent_code]

    def _level_depth(self, level: Enum) -> int:
        """Get numeric depth of a hierarchy level."""
        site_order = [SiteHierarchyLevel.COMPANY, SiteHierarchyLevel.REGION,
                      SiteHierarchyLevel.COUNTRY, SiteHierarchyLevel.STATE,
                      SiteHierarchyLevel.SITE]
        product_order = [ProductHierarchyLevel.CATEGORY, ProductHierarchyLevel.FAMILY,
                        ProductHierarchyLevel.GROUP, ProductHierarchyLevel.PRODUCT]

        if level in site_order:
            return site_order.index(level)
        if level in product_order:
            return product_order.index(level)
        return 0

    def _expand_time_bucket(
        self,
        time_key: str,
        source_bucket: TimeBucketType,
        target_bucket: TimeBucketType
    ) -> List[str]:
        """Expand a time bucket to finer granularity periods."""
        # If same or coarser bucket, return original
        bucket_order = [TimeBucketType.YEAR, TimeBucketType.QUARTER, TimeBucketType.MONTH,
                       TimeBucketType.WEEK, TimeBucketType.DAY, TimeBucketType.HOUR]

        source_idx = bucket_order.index(source_bucket) if source_bucket in bucket_order else 0
        target_idx = bucket_order.index(target_bucket) if target_bucket in bucket_order else 0

        if target_idx <= source_idx:
            return [time_key]

        # Expand to finer buckets
        periods = []

        if source_bucket == TimeBucketType.MONTH and target_bucket == TimeBucketType.WEEK:
            # Month -> ~4 weeks
            year, month = time_key.split('-')
            for week in range(4):
                periods.append(f"{year}-W{int(month)*4 - 3 + week:02d}")

        elif source_bucket == TimeBucketType.MONTH and target_bucket == TimeBucketType.DAY:
            # Month -> 28-31 days
            year, month = time_key.split('-')
            start = datetime(int(year), int(month), 1)
            for day in range(31):
                d = start + timedelta(days=day)
                if d.month == int(month):
                    periods.append(d.strftime("%Y-%m-%d"))

        elif source_bucket == TimeBucketType.WEEK and target_bucket == TimeBucketType.DAY:
            # Week -> 7 days
            year, week = time_key.split('-W')
            start = datetime.strptime(f"{year}-W{week}-1", "%Y-W%W-%w")
            for day in range(7):
                d = start + timedelta(days=day)
                periods.append(d.strftime("%Y-%m-%d"))

        if not periods:
            periods = [time_key]

        return periods

    def _get_disaggregation_proportions(
        self,
        agg_record: AggregatedRecord,
        target_members: List[str],
        default_method: DisaggregationMethod
    ) -> Dict[str, float]:
        """
        Get disaggregation proportions for target members.

        Priority order:
        1. Stored disaggregation weights from aggregation
        2. Learned splits
        3. Historical proportions
        4. Equal split
        """
        # 1. Check if aggregation stored weights
        if agg_record.disaggregation_weights:
            # Map stored weights to target members
            proportions = {}
            total = 0.0
            for member in target_members:
                # Find matching stored weight
                weight = agg_record.disaggregation_weights.get(member, 0.0)
                if weight == 0.0:
                    # Try partial match
                    for stored_key, stored_weight in agg_record.disaggregation_weights.items():
                        if self._keys_match(member, stored_key):
                            weight = stored_weight
                            break
                proportions[member] = weight
                total += weight

            if total > 0:
                return {k: v / total for k, v in proportions.items()}

        # 2. Check learned splits
        agg_key = f"{agg_record.site_key}_{agg_record.product_key}_{agg_record.time_key}"
        if agg_key in self._learned_splits:
            split = self._learned_splits[agg_key]
            proportions = {}
            for member in target_members:
                proportions[member] = split.get_proportion(member)
            total = sum(proportions.values())
            if total > 0:
                return {k: v / total for k, v in proportions.items()}

        # 3. Check historical proportions
        if agg_key in self._historical_data:
            hist = self._historical_data[agg_key]
            proportions = {}
            for member in target_members:
                proportions[member] = hist.get(member, 0.0)
            total = sum(proportions.values())
            if total > 0:
                return {k: v / total for k, v in proportions.items()}

        # 4. Equal split
        n = len(target_members)
        return {member: 1.0 / n for member in target_members}

    def _keys_match(self, member_key: str, stored_key: str) -> bool:
        """Check if member key matches stored key (with wildcards)."""
        member_parts = member_key.split('_')
        stored_parts = stored_key.split('_')

        if len(member_parts) != len(stored_parts):
            return False

        for mp, sp in zip(member_parts, stored_parts):
            if sp != '*' and mp != sp:
                return False

        return True

    def _parse_member_key(self, member_key: str) -> Tuple[str, str, str]:
        """Parse member key into site, product, time components."""
        parts = member_key.split('_')
        if len(parts) >= 3:
            return parts[0], parts[1], '_'.join(parts[2:])
        elif len(parts) == 2:
            return parts[0], parts[1], ""
        else:
            return member_key, "", ""

    def _disaggregate_value(
        self,
        aggregated_value: float,
        proportion: float,
        rule: DisaggregationRule,
        member_key: str,
        agg_record: AggregatedRecord
    ) -> float:
        """Compute disaggregated value for a single member."""
        # Base disaggregation
        value = aggregated_value * proportion

        # Apply constraints
        if rule.min_value is not None:
            value = max(value, rule.min_value)
        if rule.max_value is not None:
            value = min(value, rule.max_value)

        # Round if needed
        if rule.round_to_integer:
            value = round(value)

        return value


# ============================================================================
# Value-Based Disaggregation (VFA Approach)
# ============================================================================

class ValueBasedDisaggregator:
    """
    Implements Powell's VFA approach to disaggregation.

    Instead of using fixed proportions, allocates aggregated quantities
    to maximize expected value across members.

    V(disaggregation) = sum_i V_i(allocated_qty_i)

    where V_i is the value function for member i.
    """

    def __init__(self, value_functions: Dict[str, Callable[[float], float]]):
        """
        Args:
            value_functions: Dict of member_key -> V(quantity) functions
                            Each function returns expected value for a quantity
        """
        self.value_functions = value_functions

    def allocate(
        self,
        total_quantity: float,
        members: List[str],
        constraints: Optional[Dict[str, Tuple[float, float]]] = None
    ) -> Dict[str, float]:
        """
        Allocate total quantity to members to maximize total value.

        Uses gradient-based allocation:
        - Allocate marginal unit to member with highest marginal value
        - Respect min/max constraints

        Args:
            total_quantity: Total quantity to allocate
            members: List of member keys
            constraints: Optional dict of member_key -> (min, max) constraints

        Returns:
            Dict of member_key -> allocated_quantity
        """
        constraints = constraints or {}
        allocations = {m: constraints.get(m, (0, float('inf')))[0] for m in members}
        remaining = total_quantity - sum(allocations.values())

        if remaining <= 0:
            return allocations

        # Greedy allocation based on marginal value
        step_size = max(1, total_quantity / 1000)  # Small steps for accuracy

        while remaining > 0:
            # Find member with highest marginal value
            best_member = None
            best_marginal = -float('inf')

            for member in members:
                current = allocations[member]
                max_qty = constraints.get(member, (0, float('inf')))[1]

                if current < max_qty:
                    # Compute marginal value
                    vf = self.value_functions.get(member, lambda x: x)
                    marginal = vf(current + step_size) - vf(current)

                    if marginal > best_marginal:
                        best_marginal = marginal
                        best_member = member

            if best_member is None:
                break

            # Allocate step
            allocations[best_member] += min(step_size, remaining)
            remaining -= step_size

        return allocations


# ============================================================================
# Convenience Functions
# ============================================================================

async def disaggregate_sop_to_mps(
    db: AsyncSession,
    tenant_id: int,
    sop_records: List[AggregatedRecord]
) -> List[DisaggregatedRecord]:
    """Disaggregate S&OP plans (Country x Family x Month) to MPS level (Site x Group x Week)."""
    service = DisaggregationService(db, tenant_id)
    await service.load_hierarchies()
    await service.load_learned_splits()

    return service.disaggregate(
        sop_records,
        target_site_level=SiteHierarchyLevel.SITE,
        target_product_level=ProductHierarchyLevel.GROUP,
        target_time_bucket=TimeBucketType.WEEK
    )


async def disaggregate_mps_to_mrp(
    db: AsyncSession,
    tenant_id: int,
    mps_records: List[AggregatedRecord]
) -> List[DisaggregatedRecord]:
    """Disaggregate MPS plans (Site x Group x Week) to MRP level (Site x SKU x Day)."""
    service = DisaggregationService(db, tenant_id)
    await service.load_hierarchies()
    await service.load_learned_splits()

    return service.disaggregate(
        mps_records,
        target_site_level=SiteHierarchyLevel.SITE,
        target_product_level=ProductHierarchyLevel.PRODUCT,
        target_time_bucket=TimeBucketType.DAY
    )
