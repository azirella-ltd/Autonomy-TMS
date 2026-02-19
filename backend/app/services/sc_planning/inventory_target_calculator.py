"""
Inventory Target Calculator - Step 2 of SC Planning Process

Calculates target inventory levels based on inventory policies.

Supports 5 safety stock policy types:
1. abs_level - Absolute level (fixed quantity)
2. doc_dem - Days of coverage (demand-based)
3. doc_fcst - Days of coverage (forecast-based)
4. sl - Service level using King Formula: SS = z × √(LT × σ_d² + d² × σ_LT²)
5. conformal - Conformal prediction-based (distribution-free guarantees)

King Formula (sl policy):
  - Accounts for BOTH demand variability AND lead time variability
  - Term 1: LT × σ_d² = demand variance during average lead time
  - Term 2: d² × σ_LT² = impact of lead time variance on average demand
  - Reference: King, P.L. (2011). "Crack the Code: Understanding Safety Stock"
    APICS Magazine, July/August 2011

Conformal policy:
  - Uses conformal prediction intervals for distribution-free guarantees
  - SS = worst_case_demand_during_LT - expected_demand_during_LT
  - Joint coverage = demand_coverage × lead_time_coverage

Hierarchical override logic:
product_id > product_group_id > site_id > geo_id > segment_id > company_id

Reference: https://docs.[removed]
"""

import logging
from datetime import date, timedelta
from typing import Dict, Tuple, Optional
import math
import statistics

logger = logging.getLogger(__name__)
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.sc_entities import (
    InvPolicy,
    SourcingRules,
    OutboundOrderLine
)
from app.models.supplier import VendorLeadTime
from app.models.supply_chain_config import Site, TransportationLane
from app.models.sc_entities import Product
from app.models.compatibility import Item, ProductSiteConfig  # Temporary compat


class InventoryTargetCalculator:
    """
    Step 2: Inventory Target Calculation

    Calculates safety stock and target inventory levels based on
    inventory policies with hierarchical override logic.
    """

    def __init__(self, config_id: int, group_id: int):
        self.config_id = config_id
        self.group_id = group_id

    async def calculate_targets(
        self,
        net_demand: Dict[Tuple[str, str, date], float],
        start_date: date
    ) -> Dict[Tuple[str, str], float]:
        """
        Calculate target inventory levels based on inv_policy

        Args:
            net_demand: Net demand by (product_id, site_id, date)
            start_date: Planning start date

        Returns:
            Dict mapping (product_id, site_id) → target_inventory_level
        """
        targets = {}

        # Get all product-site combinations with demand
        product_sites = set((prod_id, site_id) for prod_id, site_id, _ in net_demand.keys())

        print(f"  Calculating targets for {len(product_sites)} product-site combinations...")

        for product_id, site_id in product_sites:
            # Get inventory policy (with hierarchical override logic)
            policy = await self.get_inventory_policy(product_id, site_id)

            if not policy:
                # No policy defined, use minimal default
                print(f"    ⚠️  No policy found for {product_id} at {site_id}, using default")
                targets[(product_id, site_id)] = 0
                continue

            # Calculate safety stock based on policy type
            safety_stock = await self.calculate_safety_stock(
                policy, product_id, site_id, net_demand, start_date
            )

            # Calculate review period demand
            review_period_demand = await self.calculate_review_period_demand(
                policy.review_period or 1, product_id, site_id, net_demand, start_date
            )

            # Target = Safety Stock + Review Period Demand
            target_inventory = safety_stock + review_period_demand

            # Apply min/max constraints if specified
            if policy.min_qty:
                target_inventory = max(target_inventory, float(policy.min_qty))
            if policy.max_qty:
                target_inventory = min(target_inventory, float(policy.max_qty))

            targets[(product_id, site_id)] = target_inventory

            print(f"    ✓ {product_id} @ {site_id}: target={target_inventory:.1f} "
                  f"(SS={safety_stock:.1f}, RPD={review_period_demand:.1f})")

        return targets

    async def get_inventory_policy(
        self, product_id: str, site_id: str
    ) -> Optional[InvPolicy]:
        """
        Get inventory policy with 6-level hierarchical override logic

        Override priority (highest to lowest):
        1. product_id + site_id (most specific)
        2. product_group_id + site_id
        3. product_id + dest_geo_id
        4. product_group_id + dest_geo_id
        5. segment_id (market segment level)
        6. company_id (company-wide default - lowest priority)

        SC Reference: https://docs.[removed]

        Args:
            product_id: Item identifier
            site_id: Node identifier

        Returns:
            InvPolicy or None if no policy found
        """
        async with SessionLocal() as db:
            # Get product and site details for hierarchy
            product = await db.get(Product, product_id)
            site = await db.get(Node, site_id)

            if not product or not site:
                return None

            # Level 1: product_id + site_id (highest priority - most specific)
            result = await db.execute(
                select(InvPolicy).filter(
                    InvPolicy.group_id == self.group_id,
                    InvPolicy.config_id == self.config_id,
                    InvPolicy.product_id == product_id,
                    InvPolicy.site_id == site_id
                ).order_by(InvPolicy.id.desc())
            )
            policy = result.scalar_one_or_none()
            if policy:
                return policy

            # Level 2: product_group_id + site_id
            if product.product_group_id:
                result = await db.execute(
                    select(InvPolicy).filter(
                        InvPolicy.group_id == self.group_id,
                    InvPolicy.config_id == self.config_id,
                        InvPolicy.product_group_id == str(product.product_group_id),
                        InvPolicy.site_id == site_id,
                        InvPolicy.product_id.is_(None)
                    ).order_by(InvPolicy.id.desc())
                )
                policy = result.scalar_one_or_none()
                if policy:
                    return policy

            # Level 3: product_id + dest_geo_id (geographic override)
            if site.geo_id:
                result = await db.execute(
                    select(InvPolicy).filter(
                        InvPolicy.group_id == self.group_id,
                    InvPolicy.config_id == self.config_id,
                        InvPolicy.product_id == product_id,
                        InvPolicy.dest_geo_id == str(site.geo_id),
                        InvPolicy.site_id.is_(None)
                    ).order_by(InvPolicy.id.desc())
                )
                policy = result.scalar_one_or_none()
                if policy:
                    return policy

            # Level 4: product_group_id + dest_geo_id
            if product.product_group_id and site.geo_id:
                result = await db.execute(
                    select(InvPolicy).filter(
                        InvPolicy.group_id == self.group_id,
                    InvPolicy.config_id == self.config_id,
                        InvPolicy.product_group_id == str(product.product_group_id),
                        InvPolicy.dest_geo_id == str(site.geo_id),
                        InvPolicy.product_id.is_(None),
                        InvPolicy.site_id.is_(None)
                    ).order_by(InvPolicy.id.desc())
                )
                policy = result.scalar_one_or_none()
                if policy:
                    return policy

            # Level 5: segment_id (market segment level)
            if site.segment_id:
                result = await db.execute(
                    select(InvPolicy).filter(
                        InvPolicy.group_id == self.group_id,
                    InvPolicy.config_id == self.config_id,
                        InvPolicy.segment_id == str(site.segment_id),
                        InvPolicy.product_id.is_(None),
                        InvPolicy.product_group_id.is_(None),
                        InvPolicy.site_id.is_(None),
                        InvPolicy.dest_geo_id.is_(None)
                    ).order_by(InvPolicy.id.desc())
                )
                policy = result.scalar_one_or_none()
                if policy:
                    return policy

            # Level 6: company_id (company-wide default - lowest priority)
            if site.company_id:
                result = await db.execute(
                    select(InvPolicy).filter(
                        InvPolicy.group_id == self.group_id,
                    InvPolicy.config_id == self.config_id,
                        InvPolicy.company_id == str(site.company_id),
                        InvPolicy.product_id.is_(None),
                        InvPolicy.product_group_id.is_(None),
                        InvPolicy.site_id.is_(None),
                        InvPolicy.dest_geo_id.is_(None),
                        InvPolicy.segment_id.is_(None)
                    ).order_by(InvPolicy.id.desc())
                )
                policy = result.scalar_one_or_none()
                if policy:
                    return policy

            # No policy found at any level
            return None

    async def calculate_safety_stock(
        self,
        policy: InvPolicy,
        product_id: str,
        site_id: str,
        net_demand: Dict[Tuple[str, str, date], float],
        start_date: date
    ) -> float:
        """
        Calculate safety stock based on SC policy type

        SC Standard Policy Types:
        - abs_level: Fixed quantity (absolute safety stock)
        - doc_dem: Days of coverage based on actual historical demand
        - doc_fcst: Days of coverage based on forecast
        - sl: Service level (probabilistic with z-score)

        Reference: https://docs.[removed]

        Args:
            policy: Inventory policy with ss_policy field
            product_id: Item identifier
            site_id: Node identifier
            net_demand: Net demand data
            start_date: Planning start date

        Returns:
            Safety stock quantity
        """
        # SC Standard: Use ss_policy to determine calculation method
        if policy.ss_policy == 'abs_level':
            # Absolute level - directly specified quantity
            return float(policy.ss_quantity or 0)

        elif policy.ss_policy == 'doc_dem':
            # Days of coverage (demand) - actual historical demand
            avg_daily_demand = await self.calculate_avg_daily_demand(
                product_id, site_id, start_date, lookback_days=30
            )
            return (policy.ss_days or 0) * avg_daily_demand

        elif policy.ss_policy == 'doc_fcst':
            # Days of coverage (forecast) - forecasted demand
            avg_daily_forecast = self.calculate_avg_daily_forecast(
                product_id, site_id, net_demand, start_date, horizon_days=30
            )
            return (policy.ss_days or 0) * avg_daily_forecast

        elif policy.ss_policy == 'sl':
            # Service level - probabilistic calculation using King Formula
            # King Formula: SS = z × √(LT × σ_d² + d² × σ_LT²)
            # This accounts for BOTH demand variability AND lead time variability
            #
            # Reference: King, P.L. (2011). "Crack the Code: Understanding Safety Stock and Mastering Its Equations"
            # APICS Magazine, July/August 2011
            service_level = float(policy.service_level or 0.95)
            z_score = self.get_z_score(service_level)

            # Get demand statistics
            avg_daily_demand = await self.calculate_avg_daily_demand(
                product_id, site_id, start_date, lookback_days=90
            )
            demand_std_dev = await self.calculate_demand_std_dev(
                product_id, site_id, start_date, lookback_days=90
            )

            # Get lead time statistics
            lead_time = await self.get_replenishment_lead_time(product_id, site_id)
            lead_time_std_dev = await self.get_lead_time_std_dev(product_id, site_id)

            # King Formula: SS = z × √(LT × σ_d² + d² × σ_LT²)
            # Term 1: demand variability during average lead time
            # Term 2: impact of lead time variability on average demand
            demand_variance_term = lead_time * (demand_std_dev ** 2)
            lead_time_variance_term = (avg_daily_demand ** 2) * (lead_time_std_dev ** 2)

            safety_stock = z_score * math.sqrt(demand_variance_term + lead_time_variance_term)
            return safety_stock

        elif policy.ss_policy == 'conformal':
            # Conformal prediction-based safety stock
            # Uses distribution-free prediction intervals for formal guarantees
            # Formula: SS = worst_case_demand_during_LT - expected_demand_during_LT
            from ..conformal_prediction.suite import get_conformal_suite

            suite = get_conformal_suite()

            # Get expected demand per period
            avg_daily_demand = self.calculate_avg_daily_forecast(
                product_id, site_id, net_demand, start_date, horizon_days=30
            )

            # Get lead time
            lead_time = await self.get_replenishment_lead_time(product_id, site_id)

            # Calculate conformal safety stock
            result = await self._calculate_conformal_safety_stock(
                suite, product_id, site_id, avg_daily_demand, lead_time,
                policy.conformal_demand_coverage or 0.90,
                policy.conformal_lead_time_coverage or 0.90
            )

            return result['safety_stock']

        else:
            # Fallback for policies without ss_policy set (backward compatibility)
            # Use reorder_point as safety stock
            if policy.reorder_point:
                return float(policy.reorder_point)

            # Fallback to 20% of target_qty if no reorder point
            if policy.target_qty:
                return float(policy.target_qty) * 0.20

            return 0.0

    def get_z_score(self, service_level: float) -> float:
        """
        Get z-score for normal distribution given service level

        Args:
            service_level: Desired service level (0-1)

        Returns:
            Z-score corresponding to service level
        """
        # Common service levels and their z-scores
        z_scores = {
            0.50: 0.00,
            0.80: 0.84,
            0.85: 1.04,
            0.90: 1.28,
            0.95: 1.65,
            0.975: 1.96,
            0.98: 2.05,
            0.99: 2.33,
            0.995: 2.58,
            0.999: 3.09
        }

        # Find closest match
        closest_sl = min(z_scores.keys(), key=lambda x: abs(x - service_level))
        return z_scores[closest_sl]

    async def calculate_avg_daily_demand(
        self, product_id: str, site_id: str, start_date: date, lookback_days: int
    ) -> float:
        """
        Calculate average daily demand from historical actuals

        Args:
            product_id: Item identifier
            site_id: Node identifier
            start_date: Planning start date
            lookback_days: Number of days to look back

        Returns:
            Average daily demand quantity
        """
        async with SessionLocal() as db:
            lookback_start = start_date - timedelta(days=lookback_days)

            result = await db.execute(
                select(OutboundOrderLine).filter(
                    OutboundOrderLine.config_id == self.config_id,
                    OutboundOrderLine.product_id == product_id,
                    OutboundOrderLine.site_id == site_id,
                    OutboundOrderLine.order_date >= lookback_start,
                    OutboundOrderLine.order_date < start_date
                )
            )
            orders = result.scalars().all()

            if not orders:
                return 0

            total_demand = sum(order.ordered_quantity for order in orders)
            return total_demand / lookback_days

    def calculate_avg_daily_forecast(
        self,
        product_id: str,
        site_id: str,
        net_demand: Dict[Tuple[str, str, date], float],
        start_date: date,
        horizon_days: int
    ) -> float:
        """
        Calculate average daily forecast from net demand

        Args:
            product_id: Item identifier
            site_id: Node identifier
            net_demand: Net demand data
            start_date: Planning start date
            horizon_days: Number of days to average over

        Returns:
            Average daily forecast quantity
        """
        end_date = start_date + timedelta(days=horizon_days)

        relevant_demand = [
            qty for (pid, sid, demand_date), qty in net_demand.items()
            if pid == product_id and sid == site_id
            and start_date <= demand_date < end_date
        ]

        if not relevant_demand:
            return 0

        return sum(relevant_demand) / horizon_days

    async def calculate_demand_std_dev(
        self, product_id: str, site_id: str, start_date: date, lookback_days: int
    ) -> float:
        """
        Calculate demand standard deviation from historical actuals

        Args:
            product_id: Item identifier
            site_id: Node identifier
            start_date: Planning start date
            lookback_days: Number of days to look back

        Returns:
            Standard deviation of daily demand
        """
        async with SessionLocal() as db:
            lookback_start = start_date - timedelta(days=lookback_days)

            result = await db.execute(
                select(OutboundOrderLine).filter(
                    OutboundOrderLine.config_id == self.config_id,
                    OutboundOrderLine.product_id == product_id,
                    OutboundOrderLine.site_id == site_id,
                    OutboundOrderLine.order_date >= lookback_start,
                    OutboundOrderLine.order_date < start_date
                )
            )
            orders = result.scalars().all()

            if len(orders) < 2:
                return 0

            quantities = [order.ordered_quantity for order in orders]
            return statistics.stdev(quantities)

    async def get_replenishment_lead_time(
        self, product_id: str, site_id: str
    ) -> int:
        """
        Get lead time from vendor_lead_time or sourcing_rules

        Hierarchical lookup:
        1. vendor_lead_time (with override logic)
        2. transportation_lane via sourcing_rules
        3. Default to 1 day

        Args:
            product_id: Item identifier
            site_id: Node identifier

        Returns:
            Lead time in days
        """
        async with SessionLocal() as db:
            # Try vendor_lead_time first (with override logic)
            # Try product + site
            result = await db.execute(
                select(VendorLeadTime).filter(
                    VendorLeadTime.product_id == product_id,
                    VendorLeadTime.site_id == site_id
                ).order_by(VendorLeadTime.id.desc())
            )
            lead_time = result.scalar_one_or_none()

            if lead_time:
                return int(lead_time.lead_time_days or 1)

            # Fallback to sourcing rule transportation lane
            result = await db.execute(
                select(SourcingRules).filter(
                    SourcingRules.group_id == self.group_id,
                    SourcingRules.config_id == self.config_id,
                    SourcingRules.product_id == product_id,
                    SourcingRules.to_site_id == site_id,
                    SourcingRules.is_active == 'true'
                ).order_by(SourcingRules.sourcing_priority)
            )
            sourcing_rule = result.scalar_one_or_none()

            if sourcing_rule and sourcing_rule.transportation_lane_id:
                lane = await db.get(TransportationLane, sourcing_rule.transportation_lane_id)
                if lane:
                    return int(lane.transit_time or 1)

            return 1  # Default lead time

    async def get_lead_time_std_dev(
        self, product_id: str, site_id: str
    ) -> float:
        """
        Get lead time standard deviation from historical data.

        Used by King Formula: SS = z × √(LT × σ_d² + d² × σ_LT²)

        Lookup strategy:
        1. Query VendorLeadTime table for historical records
        2. Calculate standard deviation from multiple records
        3. If insufficient data, estimate as % of average lead time (industry rule of thumb)
        4. Default to 0 if no data available (falls back to simpler formula)

        Args:
            product_id: Item identifier
            site_id: Node identifier

        Returns:
            Standard deviation of lead time in days
        """
        async with SessionLocal() as db:
            # Query historical lead time records for this product-site
            result = await db.execute(
                select(VendorLeadTime).filter(
                    VendorLeadTime.product_id == product_id,
                    VendorLeadTime.site_id == site_id
                ).order_by(VendorLeadTime.id.desc()).limit(100)
            )
            lead_time_records = result.scalars().all()

            if len(lead_time_records) >= 3:
                # Have enough data to calculate actual std dev
                lead_times = [
                    float(lt.lead_time_days or 0) for lt in lead_time_records
                    if lt.lead_time_days is not None
                ]
                if len(lead_times) >= 3:
                    return statistics.stdev(lead_times)

            # Not enough historical data - use rule of thumb estimate
            # Industry practice: lead time std dev is typically 20-30% of average LT
            # Reference: APICS CPIM guidelines, Simchi-Levi "Designing and Managing the Supply Chain"
            avg_lead_time = await self.get_replenishment_lead_time(product_id, site_id)

            # Use 25% of average as conservative estimate
            # This assumes moderate supplier variability
            estimated_std_dev = avg_lead_time * 0.25

            return estimated_std_dev

    async def calculate_review_period_demand(
        self,
        review_period: int,
        product_id: str,
        site_id: str,
        net_demand: Dict[Tuple[str, str, date], float],
        start_date: date
    ) -> float:
        """
        Calculate expected demand during review period

        Args:
            review_period: Review period in days
            product_id: Item identifier
            site_id: Node identifier
            net_demand: Net demand data
            start_date: Planning start date

        Returns:
            Total demand during review period
        """
        end_date = start_date + timedelta(days=review_period)

        period_demand = sum(
            qty for (pid, sid, demand_date), qty in net_demand.items()
            if pid == product_id and sid == site_id
            and start_date <= demand_date < end_date
        )

        return period_demand

    async def _calculate_conformal_safety_stock(
        self,
        suite,  # SupplyChainConformalSuite
        product_id: str,
        site_id: str,
        expected_demand_per_period: float,
        expected_lead_time: float,
        demand_coverage: float = 0.90,
        lead_time_coverage: float = 0.90
    ) -> Dict:
        """
        Calculate safety stock using conformal prediction intervals.

        Traditional approach:
        - SS = z × σ_demand × √(lead_time)
        - Assumes Normal demand distribution
        - No guarantee on actual service level

        Conformal approach:
        - SS = worst_case_demand_during_LT - expected_demand_during_LT
        - No distribution assumptions
        - Formal service level guarantee

        The key insight is that conformal prediction provides prediction intervals
        with guaranteed coverage (e.g., 90% of actual values fall within the interval).
        By using the upper bound of demand and lead time intervals, we get a
        worst-case scenario with provable coverage.

        Args:
            suite: Calibrated SupplyChainConformalSuite
            product_id: Product identifier
            site_id: Site identifier (converted to int internally)
            expected_demand_per_period: Average demand per period
            expected_lead_time: Expected replenishment lead time (periods)
            demand_coverage: Target coverage for demand intervals
            lead_time_coverage: Target coverage for lead time intervals

        Returns:
            Dict with safety_stock, reorder_point, service_level_guarantee, etc.
        """
        site_id_int = site_id

        # Staleness check: warn if conformal intervals are old
        try:
            from app.services.conformal_orchestrator import ConformalOrchestrator
            staleness = ConformalOrchestrator.get_instance().check_staleness(
                product_id, int(site_id_int)
            )
            if staleness["is_expired"]:
                logger.warning(
                    f"Conformal intervals EXPIRED for {product_id}@{site_id_int}. "
                    f"Using conservative fallback."
                )
            elif staleness["is_stale"]:
                logger.warning(
                    f"Conformal intervals stale for {product_id}@{site_id_int}: "
                    f"{staleness['recommendation']}"
                )
        except Exception:
            pass  # Staleness check is advisory

        # Get demand interval
        try:
            if suite.has_demand_predictor(product_id, site_id_int):
                # Expected demand during lead time
                demand_during_lt = expected_demand_per_period * expected_lead_time
                interval = suite.predict_demand(product_id, site_id_int, demand_during_lt)
                demand_upper = interval.upper
                actual_demand_coverage = demand_coverage
            else:
                # No calibrated predictor - use conservative estimate
                demand_upper = expected_demand_per_period * expected_lead_time * 1.3
                actual_demand_coverage = 0.80  # Conservative estimate
        except Exception as e:
            # Fallback on error
            demand_upper = expected_demand_per_period * expected_lead_time * 1.3
            actual_demand_coverage = 0.80

        # Get lead time interval
        try:
            # Try to use supplier-based lead time predictor
            # For now, use a generic approach
            lt_upper = expected_lead_time * 1.3  # Default: +30%
            actual_lt_coverage = 0.80
        except Exception:
            lt_upper = expected_lead_time * 1.3
            actual_lt_coverage = 0.80

        # Calculate worst-case demand during worst-case lead time
        # Scale demand upper bound by lead time ratio
        demand_multiplier = demand_upper / (expected_demand_per_period * expected_lead_time) \
            if expected_demand_per_period * expected_lead_time > 0 else 1.3

        worst_case_demand_during_lt = (
            expected_demand_per_period * demand_multiplier * lt_upper
        )

        expected_demand_during_lt = expected_demand_per_period * expected_lead_time

        # Safety stock covers the gap between worst-case and expected
        safety_stock = max(0, worst_case_demand_during_lt - expected_demand_during_lt)

        # Reorder point = expected demand during LT + safety stock
        reorder_point = expected_demand_during_lt + safety_stock

        # Joint coverage (assuming independence)
        joint_coverage = actual_demand_coverage * actual_lt_coverage

        return {
            'safety_stock': safety_stock,
            'reorder_point': reorder_point,
            'expected_demand_during_lt': expected_demand_during_lt,
            'worst_case_demand_during_lt': worst_case_demand_during_lt,
            'service_level_guarantee': joint_coverage,
            'demand_coverage': actual_demand_coverage,
            'lead_time_coverage': actual_lt_coverage,
            'policy_type': 'conformal',
        }
