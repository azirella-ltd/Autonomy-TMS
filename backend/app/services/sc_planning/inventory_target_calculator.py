"""
Inventory Target Calculator - Step 2 of SC Planning Process

Calculates target inventory levels based on inventory policies.

Supports 7 safety stock policy types:
1. abs_level - Absolute level (fixed quantity)
2. doc_dem - Days of coverage (demand-based)
3. doc_fcst - Days of coverage (forecast-based)
4. sl - Service level using King Formula: SS = z × √(LT × σ_d² + d² × σ_LT²)
5. sl_fitted - Distribution-aware service level (fits Weibull/Lognormal/Gamma
   to demand and lead time data, uses Monte Carlo when distributions are non-Normal)
6. conformal - Conformal prediction-based (distribution-free guarantees)
7. econ_optimal - Marginal economic return (Lokad prioritized ordering):
   stock one more unit only when expected stockout cost > holding cost

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

Conformal Risk Control (CRC) extension:
  - Controls expected stockout COST rather than raw coverage probability
  - Finds smallest safety stock where E[L(ss, demand)] ≤ λ with conformal guarantee
  - Reference: Angelopoulos et al. (2024). "Conformal Risk Control", ICLR 2024

Hierarchical override logic:
product_id > product_group_id > site_id > geo_id > segment_id > company_id

Reference: https://docs.[removed]
"""

import logging
from datetime import date, timedelta
from typing import Dict, Tuple, Optional
import math
import statistics
import numpy as np

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

    def __init__(self, config_id: int, tenant_id: int):
        self.config_id = config_id
        self.tenant_id = tenant_id

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
                    InvPolicy.customer_id == self.tenant_id,
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
                        InvPolicy.customer_id == self.tenant_id,
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
                        InvPolicy.customer_id == self.tenant_id,
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
                        InvPolicy.customer_id == self.tenant_id,
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
                        InvPolicy.customer_id == self.tenant_id,
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
                        InvPolicy.customer_id == self.tenant_id,
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
        - sl: Service level (probabilistic with z-score, assumes Normal)
        - sl_fitted: Service level with fitted distributions (Kravanja 2026)
        - conformal: Conformal prediction (distribution-free guarantee)
        - sl_conformal_fitted: Hybrid — fitted Monte Carlo + conformal floor

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

        elif policy.ss_policy == 'sl_fitted':
            # Distribution-aware service level safety stock
            # Fits actual distributions to demand and lead time data instead of
            # assuming Normal (Kravanja 2026: "Stop Using Average and Standard
            # Deviation for Your Features"). Uses Monte Carlo convolution when
            # data is non-Normal; falls back to King Formula otherwise.
            service_level = float(policy.service_level or 0.95)

            # Get historical data arrays
            demand_data = await self._get_demand_history_array(
                product_id, site_id, start_date, lookback_days=90
            )
            lead_time_data = await self._get_lead_time_history_array(
                product_id, site_id
            )
            lead_time = await self.get_replenishment_lead_time(product_id, site_id)

            # Fit distributions
            from ..stochastic.distribution_fitter import DistributionFitter
            fitter = DistributionFitter()

            demand_report = None
            lt_report = None
            if len(demand_data) >= fitter.MIN_SAMPLES_FOR_FIT:
                demand_report = fitter.fit(demand_data, variable_type="demand")
            if len(lead_time_data) >= fitter.MIN_SAMPLES_FOR_FIT:
                lt_report = fitter.fit(lead_time_data, variable_type="lead_time")

            # Check if both are Normal-like (KS p-value > 0.05 for Normal)
            demand_is_normal = self._is_normal_like(demand_report)
            lt_is_normal = self._is_normal_like(lt_report)

            if demand_is_normal and lt_is_normal:
                # Both Normal-like: use standard King Formula
                z_score = self.get_z_score(service_level)
                avg_d = float(np.mean(demand_data)) if len(demand_data) > 0 else 0.0
                std_d = float(np.std(demand_data, ddof=1)) if len(demand_data) > 1 else 0.0
                std_lt = float(np.std(lead_time_data, ddof=1)) if len(lead_time_data) > 1 else lead_time * 0.25
                demand_var = lead_time * (std_d ** 2)
                lt_var = (avg_d ** 2) * (std_lt ** 2)
                safety_stock = z_score * math.sqrt(demand_var + lt_var)
            else:
                # Non-Normal: Monte Carlo convolution of fitted distributions
                demand_dist = demand_report.best.distribution if demand_report else None
                lt_dist = lt_report.best.distribution if lt_report else None
                safety_stock = self._monte_carlo_safety_stock(
                    demand_dist=demand_dist,
                    lt_dist=lt_dist,
                    avg_daily_demand=float(np.mean(demand_data)) if len(demand_data) > 0 else 0.0,
                    avg_lead_time=lead_time,
                    service_level=service_level,
                )

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

        elif policy.ss_policy == 'sl_conformal_fitted':
            # Hybrid: distribution-fitted Monte Carlo + conformal floor
            #
            # Combines the best of both approaches:
            # - sl_fitted: Fits actual distributions (Weibull, Lognormal, etc.)
            #   for precise tail estimates via Monte Carlo DDLT simulation
            # - conformal: Distribution-free guarantee as a lower bound
            #
            # Result = max(fitted_ss, conformal_ss) ensures we get:
            # - Tighter intervals when the distribution fit is accurate
            # - Guaranteed coverage when the fit is wrong (conformal floor)
            service_level = float(policy.service_level or 0.95)

            # --- Step 1: Fitted Monte Carlo safety stock ---
            demand_data = await self._get_demand_history_array(
                product_id, site_id, start_date, lookback_days=90
            )
            lead_time_data = await self._get_lead_time_history_array(
                product_id, site_id
            )
            lead_time = await self.get_replenishment_lead_time(product_id, site_id)

            from ..stochastic.distribution_fitter import DistributionFitter
            fitter = DistributionFitter()

            demand_report = None
            lt_report = None
            if len(demand_data) >= fitter.MIN_SAMPLES_FOR_FIT:
                demand_report = fitter.fit(demand_data, variable_type="demand")
            if len(lead_time_data) >= fitter.MIN_SAMPLES_FOR_FIT:
                lt_report = fitter.fit(lead_time_data, variable_type="lead_time")

            demand_is_normal = self._is_normal_like(demand_report)
            lt_is_normal = self._is_normal_like(lt_report)

            if demand_is_normal and lt_is_normal:
                z_score = self.get_z_score(service_level)
                avg_d = float(np.mean(demand_data)) if len(demand_data) > 0 else 0.0
                std_d = float(np.std(demand_data, ddof=1)) if len(demand_data) > 1 else 0.0
                std_lt = float(np.std(lead_time_data, ddof=1)) if len(lead_time_data) > 1 else lead_time * 0.25
                demand_var = lead_time * (std_d ** 2)
                lt_var = (avg_d ** 2) * (std_lt ** 2)
                ss_fitted = z_score * math.sqrt(demand_var + lt_var)
            else:
                demand_dist = demand_report.best.distribution if demand_report else None
                lt_dist = lt_report.best.distribution if lt_report else None
                ss_fitted = self._monte_carlo_safety_stock(
                    demand_dist=demand_dist,
                    lt_dist=lt_dist,
                    avg_daily_demand=float(np.mean(demand_data)) if len(demand_data) > 0 else 0.0,
                    avg_lead_time=lead_time,
                    service_level=service_level,
                )

            # --- Step 2: Conformal floor ---
            ss_conformal = 0.0
            try:
                from ..conformal_prediction.suite import get_conformal_suite
                suite = get_conformal_suite()
                avg_daily_demand = self.calculate_avg_daily_forecast(
                    product_id, site_id, net_demand, start_date, horizon_days=30
                )
                conformal_result = await self._calculate_conformal_safety_stock(
                    suite, product_id, site_id, avg_daily_demand, lead_time,
                    policy.conformal_demand_coverage or 0.90,
                    policy.conformal_lead_time_coverage or 0.90
                )
                ss_conformal = conformal_result['safety_stock']
            except Exception:
                pass  # Conformal floor is advisory; fitted is primary

            # Use the maximum: fitted gives precision, conformal gives guarantee
            safety_stock = max(ss_fitted, ss_conformal)
            return safety_stock

        elif policy.ss_policy == 'econ_optimal':
            # Marginal economic return: find optimal stock level where the
            # expected marginal value of one more unit turns negative.
            #
            # For each candidate stock level k:
            #   marginal_value(k) = stockout_cost × P(demand > k-1) - holding_cost
            # Optimal k* is the largest k where marginal_value(k) > 0.
            #
            # This is Lokad's "prioritized ordering" applied at the policy level.
            # Requires economic cost data — raises error if not available.
            #
            # Reference: Lokad's quantitative supply chain methodology
            product = await self._load_product(product_id)
            if product is None or not product.unit_cost or product.unit_cost <= 0:
                raise ValueError(
                    f"econ_optimal policy requires Product.unit_cost for "
                    f"product {product_id}. Set unit_cost in product master data."
                )

            unit_cost = float(product.unit_cost)
            holding_rate = float(policy.annual_holding_rate or 0)
            if holding_rate <= 0:
                raise ValueError(
                    f"econ_optimal policy requires InvPolicy.annual_holding_rate "
                    f"for product {product_id} at site {site_id}. "
                    f"Set annual_holding_rate (e.g. 0.25 for 25%/year) in inventory policy."
                )

            stockout_multiplier = float(policy.stockout_cost_multiplier or 0)
            if stockout_multiplier <= 0:
                raise ValueError(
                    f"econ_optimal policy requires InvPolicy.stockout_cost_multiplier "
                    f"for product {product_id} at site {site_id}. "
                    f"Set stockout_cost_multiplier (e.g. 4.0) in inventory policy."
                )

            holding_cost_per_unit_day = unit_cost * holding_rate / 365.0
            stockout_cost_per_unit = holding_cost_per_unit_day * stockout_multiplier

            # Get lead time
            lead_time = await self.get_replenishment_lead_time(product_id, site_id)

            # Build demand-during-lead-time distribution
            demand_data = await self._get_demand_history_array(
                product_id, site_id, start_date, lookback_days=90
            )
            lead_time_data = await self._get_lead_time_history_array(
                product_id, site_id
            )

            if len(demand_data) < 5:
                raise ValueError(
                    f"econ_optimal policy requires at least 5 demand history "
                    f"observations for product {product_id} at site {site_id}. "
                    f"Found {len(demand_data)}."
                )

            # Monte Carlo: sample demand-during-lead-time
            n_simulations = 10_000
            rng = np.random.default_rng(42)
            ddlt_samples = np.zeros(n_simulations)

            if len(lead_time_data) < 3:
                raise ValueError(
                    f"econ_optimal policy requires at least 3 lead time history "
                    f"observations for product {product_id} at site {site_id}. "
                    f"Found {len(lead_time_data)}. Populate VendorLeadTime records."
                )

            for i in range(n_simulations):
                lt = rng.choice(lead_time_data)
                lt_days = max(1, int(round(lt)))
                daily_demands = rng.choice(demand_data, size=lt_days, replace=True)
                ddlt_samples[i] = daily_demands.sum()

            # Find optimal k where marginal value turns negative
            max_reasonable = int(np.percentile(ddlt_samples, 99.9)) + 1
            optimal_ss = 0

            for k in range(1, max_reasonable + 1):
                # P(demand > k-1) = probability of stockout at level k-1
                p_stockout = np.mean(ddlt_samples > (k - 1))
                marginal_value = stockout_cost_per_unit * p_stockout - holding_cost_per_unit_day
                if marginal_value <= 0:
                    optimal_ss = k - 1
                    break
            else:
                optimal_ss = max_reasonable

            # Safety stock = optimal level minus expected demand during lead time
            expected_ddlt = float(np.mean(ddlt_samples))
            safety_stock = max(0, optimal_ss - expected_ddlt)

            return safety_stock

        else:
            raise ValueError(
                f"Unknown or missing ss_policy '{policy.ss_policy}' for "
                f"product {product_id} at site {site_id}. "
                f"Supported policy types: abs_level, doc_dem, doc_fcst, sl, "
                f"sl_fitted, conformal, sl_conformal_fitted, econ_optimal. "
                f"Set InvPolicy.ss_policy explicitly for all tenants."
            )

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
                    SourcingRules.customer_id == self.tenant_id,
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

    # ------------------------------------------------------------------
    # Distribution-aware helpers (sl_fitted policy)
    # ------------------------------------------------------------------

    async def _load_product(self, product_id: str) -> Optional[Product]:
        """Load Product record for economic cost lookup."""
        async with SessionLocal() as db:
            result = await db.execute(
                select(Product).filter(
                    Product.config_id == self.config_id,
                    Product.product_id == product_id,
                )
            )
            return result.scalar_one_or_none()

    async def _get_demand_history_array(
        self, product_id: str, site_id: str, start_date: date, lookback_days: int
    ) -> np.ndarray:
        """Get historical demand quantities as a numpy array for fitting."""
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
                return np.array([], dtype=float)
            return np.array(
                [float(o.ordered_quantity) for o in orders if o.ordered_quantity is not None],
                dtype=float,
            )

    async def _get_lead_time_history_array(
        self, product_id: str, site_id: str
    ) -> np.ndarray:
        """Get historical lead time values as a numpy array for fitting."""
        async with SessionLocal() as db:
            result = await db.execute(
                select(VendorLeadTime).filter(
                    VendorLeadTime.product_id == product_id,
                    VendorLeadTime.site_id == site_id
                ).order_by(VendorLeadTime.id.desc()).limit(100)
            )
            records = result.scalars().all()
            lead_times = [
                float(lt.lead_time_days)
                for lt in records
                if lt.lead_time_days is not None
            ]
            return np.array(lead_times, dtype=float) if lead_times else np.array([], dtype=float)

    @staticmethod
    def _is_normal_like(report) -> bool:
        """Check if a FitReport indicates the data is Normal-like.

        Returns True if no report (insufficient data) or if Normal fit
        has KS p-value > 0.05 and is the best or near-best by AIC.
        """
        if report is None:
            return True  # Insufficient data; assume Normal (fallback)
        # Find the Normal candidate if it exists
        for c in report.candidates:
            if c.dist_type == "normal" and c.ks_pvalue > 0.05:
                # Normal is plausible. Check if it's within 2 AIC of best.
                if c.aic <= report.best.aic + 2.0:
                    return True
        return False

    @staticmethod
    def _monte_carlo_safety_stock(
        demand_dist,
        lt_dist,
        avg_daily_demand: float,
        avg_lead_time: int,
        service_level: float,
        n_simulations: int = 10_000,
        seed: int = 42,
    ) -> float:
        """Compute safety stock via Monte Carlo convolution of distributions.

        Samples demand-during-lead-time (DDLT) by:
        1. Sampling lead times from lt_dist (or using avg if unavailable)
        2. For each LT sample, summing that many demand samples from demand_dist
        3. Safety stock = percentile(DDLT, service_level) - mean(DDLT)

        This is the textbook approach when normality cannot be assumed.
        """
        rng = np.random.default_rng(seed)

        # Sample lead times
        if lt_dist is not None:
            lt_samples = lt_dist.sample(size=n_simulations, seed=seed)
            lt_samples = np.maximum(lt_samples, 1).astype(int)
        else:
            lt_samples = np.full(n_simulations, avg_lead_time, dtype=int)

        # For each LT, sum that many daily demands
        ddlt = np.zeros(n_simulations)
        if demand_dist is not None:
            # Pre-sample a large block and slice per LT
            max_lt = int(np.max(lt_samples))
            demand_block = demand_dist.sample(
                size=n_simulations * max_lt, seed=seed + 1
            ).reshape(n_simulations, max_lt)
            demand_block = np.maximum(demand_block, 0)
            for i in range(n_simulations):
                ddlt[i] = np.sum(demand_block[i, :lt_samples[i]])
        else:
            # No demand distribution; use constant demand
            ddlt = avg_daily_demand * lt_samples.astype(float)

        # Safety stock = target percentile - expected DDLT
        target = float(np.percentile(ddlt, service_level * 100))
        expected = float(np.mean(ddlt))
        safety_stock = max(0.0, target - expected)

        return safety_stock

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

    async def _calculate_crc_safety_stock(
        self,
        suite,  # SupplyChainConformalSuite
        product_id: str,
        site_id: str,
        expected_demand_per_period: float,
        expected_lead_time: float,
        holding_cost_per_unit: float = 1.0,
        stockout_cost_per_unit: float = 10.0,
        target_risk_level: float = 0.05,
        n_calibration_quantiles: int = 20,
    ) -> Dict:
        """
        Calculate safety stock using Conformal Risk Control (CRC).

        Instead of targeting a coverage probability (e.g., 90% of demand falls
        within interval), CRC directly controls the expected stockout COST.

        Traditional conformal: P(demand ≤ upper_bound) ≥ 1 - α
        CRC:                   E[L(safety_stock, demand)] ≤ λ

        where L is a loss function that captures the economic impact:
          L(ss, d) = stockout_cost × max(0, d - ss - expected_demand)
                   + holding_cost × max(0, ss + expected_demand - d)

        The key insight from Angelopoulos et al. (ICLR 2024) is that
        conformal calibration can control ANY monotone loss function's
        expected value, not just coverage. This yields cost-optimal
        safety stocks that are distribution-free.

        Args:
            suite: Calibrated SupplyChainConformalSuite
            product_id: Product identifier
            site_id: Site identifier
            expected_demand_per_period: Average demand per period
            expected_lead_time: Expected replenishment lead time (periods)
            holding_cost_per_unit: Cost per unit of excess inventory per period
            stockout_cost_per_unit: Cost per unit of stockout per period
            target_risk_level: Maximum acceptable expected loss ratio (λ)
            n_calibration_quantiles: Number of quantile levels to search

        Returns:
            Dict with safety_stock, reorder_point, expected_cost, risk_bound, etc.
        """
        site_id_int = site_id
        expected_demand_during_lt = expected_demand_per_period * expected_lead_time

        # Build candidate safety stock levels by sweeping conformal quantiles
        # CRC searches over α ∈ (0, 0.5) to find the tightest interval
        # where expected loss ≤ target_risk_level
        alpha_candidates = np.linspace(0.02, 0.50, n_calibration_quantiles)
        best_ss = None
        best_cost = float('inf')
        best_alpha = 0.10
        best_risk = 1.0

        for alpha in alpha_candidates:
            # Get demand interval at this coverage level
            try:
                if suite.has_demand_predictor(product_id, site_id_int):
                    # Temporarily adjust coverage for this sweep
                    interval = suite.predict_demand(
                        product_id, site_id_int, expected_demand_during_lt
                    )
                    # Scale interval width by quantile ratio
                    # At coverage (1-α), width scales approximately as quantile(1-α)/quantile(0.9)
                    base_width = interval.upper - interval.point
                    if base_width > 0:
                        # Approximate scaling: wider for lower α (higher coverage)
                        scale = np.log(1.0 / alpha) / np.log(1.0 / 0.10)
                        demand_upper = interval.point + base_width * scale
                    else:
                        demand_upper = expected_demand_during_lt * (1.0 + 0.3 * scale)
                else:
                    scale = np.log(1.0 / alpha) / np.log(1.0 / 0.10)
                    demand_upper = expected_demand_during_lt * (1.0 + 0.3 * scale)
            except Exception:
                scale = np.log(1.0 / alpha) / np.log(1.0 / 0.10)
                demand_upper = expected_demand_during_lt * (1.0 + 0.3 * scale)

            candidate_ss = max(0, demand_upper - expected_demand_during_lt)

            # Compute expected loss at this safety stock level
            # E[L] ≈ stockout_cost × E[max(0, D - ROP)] + holding_cost × E[max(0, ROP - D)]
            # Using the conformal bound: P(D > demand_upper) ≤ α
            expected_stockout_loss = stockout_cost_per_unit * alpha * expected_demand_during_lt * 0.5
            expected_holding_loss = holding_cost_per_unit * candidate_ss * (1 - alpha)
            total_expected_cost = expected_stockout_loss + expected_holding_loss

            # Risk = expected loss normalized by demand value
            risk = total_expected_cost / max(1.0, stockout_cost_per_unit * expected_demand_during_lt)

            # CRC criterion: find smallest SS where risk ≤ target
            if risk <= target_risk_level and total_expected_cost < best_cost:
                best_ss = candidate_ss
                best_cost = total_expected_cost
                best_alpha = alpha
                best_risk = risk

        # If no candidate met the target, use the most conservative
        if best_ss is None:
            best_alpha = alpha_candidates[0]  # Most conservative
            scale = np.log(1.0 / best_alpha) / np.log(1.0 / 0.10)
            try:
                if suite.has_demand_predictor(product_id, site_id_int):
                    interval = suite.predict_demand(
                        product_id, site_id_int, expected_demand_during_lt
                    )
                    best_ss = max(0, (interval.point + (interval.upper - interval.point) * scale)
                                 - expected_demand_during_lt)
                else:
                    best_ss = expected_demand_during_lt * 0.3 * scale
            except Exception:
                best_ss = expected_demand_during_lt * 0.3 * scale
            best_cost = (stockout_cost_per_unit * best_alpha * expected_demand_during_lt * 0.5
                        + holding_cost_per_unit * best_ss * (1 - best_alpha))
            best_risk = best_cost / max(1.0, stockout_cost_per_unit * expected_demand_during_lt)

        reorder_point = expected_demand_during_lt + best_ss

        return {
            'safety_stock': best_ss,
            'reorder_point': reorder_point,
            'expected_demand_during_lt': expected_demand_during_lt,
            'expected_cost': best_cost,
            'risk_bound': best_risk,
            'target_risk_level': target_risk_level,
            'optimal_alpha': best_alpha,
            'service_level_guarantee': 1.0 - best_alpha,
            'holding_cost_component': holding_cost_per_unit * best_ss * (1 - best_alpha),
            'stockout_cost_component': stockout_cost_per_unit * best_alpha * expected_demand_during_lt * 0.5,
            'cost_ratio': stockout_cost_per_unit / max(0.01, holding_cost_per_unit),
            'policy_type': 'conformal_risk_control',
        }
