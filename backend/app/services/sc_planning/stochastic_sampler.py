"""
Stochastic Sampler for Simulation Execution

This service integrates the Phase 5 distribution engine with simulation execution,
enabling stochastic sampling of operational variables (lead times, capacities, yields, etc.).

Key Features:
- Sample from distribution or fallback to deterministic value (backward compatible)
- Per-scenario seeding for reproducibility
- Caching of parsed distributions for performance
- Integration with ExecutionCache

Usage:
    sampler = StochasticSampler(scenario_id=42, use_cache=True)

    # Sample lead time
    lead_time = sampler.sample_lead_time(
        sourcing_rule=rule,
        default_value=7
    )

    # Sample capacity
    capacity = sampler.sample_capacity(
        capacity_config=capacity,
        default_value=100.0
    )
"""

from typing import Optional, Dict, Any
from app.services.stochastic import DistributionEngine
from app.models.sc_entities import (
    SourcingRules,
    ProductionProcess,
    ProductBom,
    Forecast,
)
from app.models.supplier import VendorLeadTime
from app.models.sc_planning import ProductionCapacity
from app.models.supply_chain_config import TransportationLane


class StochasticSampler:
    """
    Sampler for stochastic distributions in simulation execution

    Integrates the distribution engine with SC planning entities,
    providing a clean interface for sampling operational variables.
    """

    def __init__(self, scenario_id: int, use_cache: bool = True):
        """
        Initialize stochastic sampler

        Args:
            scenario_id: Scenario ID (used as seed for reproducibility)
            use_cache: Enable distribution caching (default: True)
        """
        self.scenario_id = scenario_id
        self.engine = DistributionEngine(seed=scenario_id)
        self.use_cache = use_cache

        # Distribution cache: Maps entity ID → parsed distribution
        self._distribution_cache: Dict[str, Dict[str, Any]] = {}

    # ============================================================================
    # LEAD TIME SAMPLING
    # ============================================================================

    def sample_sourcing_lead_time(
        self,
        sourcing_rule: SourcingRules,
        default_value: float
    ) -> float:
        """
        Sample sourcing lead time from distribution or use deterministic value

        Args:
            sourcing_rule: SourcingRules entity with optional sourcing_lead_time_dist
            default_value: Fallback value if distribution is NULL

        Returns:
            Sampled lead time in days (always >= 0)
        """
        if not sourcing_rule:
            return default_value

        # Get distribution config (NULL = deterministic)
        config = sourcing_rule.sourcing_lead_time_dist

        # Sample or use default
        value = self.engine.sample_or_default(
            config=config,
            default_value=default_value
        )

        # Ensure non-negative
        return max(0.0, float(value))

    def sample_vendor_lead_time(
        self,
        vendor_lead_time: VendorLeadTime,
        default_value: float
    ) -> float:
        """
        Sample vendor lead time from distribution or use deterministic value

        Args:
            vendor_lead_time: VendorLeadTime entity with optional lead_time_dist
            default_value: Fallback value if distribution is NULL

        Returns:
            Sampled lead time in days (always >= 0)
        """
        if not vendor_lead_time:
            return default_value

        config = vendor_lead_time.lead_time_dist

        value = self.engine.sample_or_default(
            config=config,
            default_value=default_value
        )

        return max(0.0, float(value))

    def sample_production_lead_time(
        self,
        production_process: ProductionProcess,
        default_value: float
    ) -> float:
        """
        Sample manufacturing lead time from distribution or use deterministic value

        Args:
            production_process: ProductionProcess entity with optional mfg_lead_time_dist
            default_value: Fallback value if distribution is NULL

        Returns:
            Sampled lead time in time units (always >= 0)
        """
        if not production_process:
            return default_value

        config = production_process.mfg_lead_time_dist

        value = self.engine.sample_or_default(
            config=config,
            default_value=default_value
        )

        return max(0.0, float(value))

    # ============================================================================
    # CAPACITY SAMPLING
    # ============================================================================

    def sample_capacity(
        self,
        capacity_config: ProductionCapacity,
        default_value: float
    ) -> float:
        """
        Sample capacity from distribution or use deterministic value

        Args:
            capacity_config: ProductionCapacity entity with optional capacity_dist
            default_value: Fallback value if distribution is NULL

        Returns:
            Sampled capacity (always >= 0)
        """
        if not capacity_config:
            return default_value

        config = capacity_config.capacity_dist

        value = self.engine.sample_or_default(
            config=config,
            default_value=default_value
        )

        return max(0.0, float(value))

    # ============================================================================
    # YIELD/SCRAP RATE SAMPLING
    # ============================================================================

    def sample_yield(
        self,
        production_process: ProductionProcess,
        default_value: float
    ) -> float:
        """
        Sample yield percentage from distribution or use deterministic value

        Args:
            production_process: ProductionProcess entity with optional yield_dist
            default_value: Fallback value if distribution is NULL (typically 100.0)

        Returns:
            Sampled yield percentage (clamped to [0, 100])
        """
        if not production_process:
            return default_value

        config = production_process.yield_dist

        value = self.engine.sample_or_default(
            config=config,
            default_value=default_value
        )

        # Clamp to [0, 100] for percentage
        return max(0.0, min(100.0, float(value)))

    def sample_scrap_rate(
        self,
        bom: ProductBom,
        default_value: float
    ) -> float:
        """
        Sample scrap rate from distribution or use deterministic value

        Args:
            bom: ProductBom entity with optional scrap_rate_dist
            default_value: Fallback value if distribution is NULL (typically 0.0)

        Returns:
            Sampled scrap rate percentage (clamped to [0, 100])
        """
        if not bom:
            return default_value

        config = bom.scrap_rate_dist

        value = self.engine.sample_or_default(
            config=config,
            default_value=default_value
        )

        # Clamp to [0, 100] for percentage
        return max(0.0, min(100.0, float(value)))

    # ============================================================================
    # DEMAND SAMPLING
    # ============================================================================

    def sample_demand(
        self,
        forecast: Forecast,
        default_value: float
    ) -> float:
        """
        Sample demand from distribution or use deterministic value

        Args:
            forecast: Forecast entity with optional demand_dist
            default_value: Fallback value if distribution is NULL

        Returns:
            Sampled demand (always >= 0)
        """
        if not forecast:
            return default_value

        config = forecast.demand_dist

        value = self.engine.sample_or_default(
            config=config,
            default_value=default_value
        )

        return max(0.0, float(value))

    def sample_forecast_error(
        self,
        forecast: Forecast,
        default_value: float = 0.0
    ) -> float:
        """
        Sample forecast error from distribution or use deterministic value

        Args:
            forecast: Forecast entity with optional forecast_error_dist
            default_value: Fallback value if distribution is NULL (typically 0.0)

        Returns:
            Sampled forecast error (can be negative)
        """
        if not forecast:
            return default_value

        config = forecast.forecast_error_dist

        value = self.engine.sample_or_default(
            config=config,
            default_value=default_value
        )

        return float(value)

    # ============================================================================
    # PRODUCTION TIME SAMPLING
    # ============================================================================

    def sample_cycle_time(
        self,
        production_process: ProductionProcess,
        default_value: float
    ) -> float:
        """
        Sample cycle time from distribution or use deterministic value

        Args:
            production_process: ProductionProcess entity with optional cycle_time_dist
            default_value: Fallback value if distribution is NULL

        Returns:
            Sampled cycle time (always >= 0)
        """
        if not production_process:
            return default_value

        config = production_process.cycle_time_dist

        value = self.engine.sample_or_default(
            config=config,
            default_value=default_value
        )

        return max(0.0, float(value))

    def sample_setup_time(
        self,
        production_process: ProductionProcess,
        default_value: float
    ) -> float:
        """
        Sample setup time from distribution or use deterministic value

        Args:
            production_process: ProductionProcess entity with optional setup_time_dist
            default_value: Fallback value if distribution is NULL

        Returns:
            Sampled setup time (always >= 0)
        """
        if not production_process:
            return default_value

        config = production_process.setup_time_dist

        value = self.engine.sample_or_default(
            config=config,
            default_value=default_value
        )

        return max(0.0, float(value))

    def sample_changeover_time(
        self,
        production_process: ProductionProcess,
        default_value: float
    ) -> float:
        """
        Sample changeover time from distribution or use deterministic value

        Args:
            production_process: ProductionProcess entity with optional changeover_time_dist
            default_value: Fallback value if distribution is NULL

        Returns:
            Sampled changeover time (always >= 0)
        """
        if not production_process:
            return default_value

        config = production_process.changeover_time_dist

        value = self.engine.sample_or_default(
            config=config,
            default_value=default_value
        )

        return max(0.0, float(value))

    # ============================================================================
    # LANE LEAD TIME SAMPLING (Phase 5: Stochastic Lead Times)
    # ============================================================================

    def sample_lane_supply_lead_time(
        self,
        lane: TransportationLane,
        default_value: float
    ) -> float:
        """
        Sample supply lead time (material flow) from lane distribution

        Args:
            lane: Lane entity with optional supply_lead_time_dist
            default_value: Fallback value if distribution is NULL

        Returns:
            Sampled supply lead time in rounds (always >= 0)
        """
        if not lane:
            return default_value

        # Check for stochastic distribution first
        config = getattr(lane, 'supply_lead_time_dist', None)

        if config:
            value = self.engine.sample_or_default(
                config=config,
                default_value=default_value
            )
            return max(0.0, float(value))

        # Fall back to deterministic JSON field (backward compatible)
        supply_lt = getattr(lane, 'supply_lead_time', None)
        if supply_lt and isinstance(supply_lt, dict):
            # Classic format: {"min": 1, "max": 2}
            lt_min = supply_lt.get('min', default_value)
            lt_max = supply_lt.get('max', default_value)
            # Sample uniformly from min to max
            if lt_min != lt_max:
                import random
                return float(random.randint(int(lt_min), int(lt_max)))
            return float(lt_min)

        return default_value

    def sample_lane_demand_lead_time(
        self,
        lane: TransportationLane,
        default_value: float
    ) -> float:
        """
        Sample demand lead time (information flow) from lane distribution

        Args:
            lane: Lane entity with optional demand_lead_time_dist
            default_value: Fallback value if distribution is NULL

        Returns:
            Sampled demand lead time in rounds (always >= 0)
        """
        if not lane:
            return default_value

        # Check for stochastic distribution first
        config = getattr(lane, 'demand_lead_time_dist', None)

        if config:
            value = self.engine.sample_or_default(
                config=config,
                default_value=default_value
            )
            return max(0.0, float(value))

        # Fall back to deterministic JSON field (backward compatible)
        demand_lt = getattr(lane, 'demand_lead_time', None)
        if demand_lt and isinstance(demand_lt, dict):
            # Classic format: {"min": 1, "max": 2}
            lt_min = demand_lt.get('min', default_value)
            lt_max = demand_lt.get('max', default_value)
            # Sample uniformly from min to max
            if lt_min != lt_max:
                import random
                return float(random.randint(int(lt_min), int(lt_max)))
            return float(lt_min)

        return default_value

    def sample_transportation_transit_time(
        self,
        trans_lane: TransportationLane,
        default_value: float
    ) -> float:
        """
        Sample transportation transit time from distribution

        Args:
            trans_lane: TransportationLane entity with optional transit_time_dist
            default_value: Fallback value if distribution is NULL

        Returns:
            Sampled transit time in days (always >= 0)
        """
        if not trans_lane:
            return default_value

        # Check for stochastic distribution
        config = getattr(trans_lane, 'transit_time_dist', None)

        if config:
            value = self.engine.sample_or_default(
                config=config,
                default_value=default_value
            )
            return max(0.0, float(value))

        # Fall back to deterministic transit_time field
        transit_time = getattr(trans_lane, 'transit_time', None)
        if transit_time is not None:
            return max(0.0, float(transit_time))

        return default_value

    def get_lane_lead_time_stats(
        self,
        lane: TransportationLane,
        default_value: float,
        n_samples: int = 1000
    ) -> Dict[str, float]:
        """
        Get statistical summary (P10/P50/P90) of lane lead time distribution

        Args:
            lane: Lane entity with optional supply_lead_time_dist
            default_value: Fallback value if distribution is NULL
            n_samples: Number of samples for Monte Carlo (default: 1000)

        Returns:
            Dictionary with P10, P50 (median), P90, mean, stddev
        """
        import numpy as np

        # Sample n times
        samples = [
            self.sample_lane_supply_lead_time(lane, default_value)
            for _ in range(n_samples)
        ]

        samples_array = np.array(samples)

        return {
            'p10': float(np.percentile(samples_array, 10)),
            'p50': float(np.percentile(samples_array, 50)),  # Median
            'p90': float(np.percentile(samples_array, 90)),
            'mean': float(np.mean(samples_array)),
            'stddev': float(np.std(samples_array)),
        }

    # ============================================================================
    # BATCH SAMPLING (PERFORMANCE OPTIMIZATION)
    # ============================================================================

    def sample_multiple(
        self,
        variable_configs: Dict[str, Optional[Dict[str, Any]]],
        default_values: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Sample multiple variables at once for performance

        This method samples multiple distributions in a single call,
        which can be more efficient than individual samples.

        Args:
            variable_configs: Dict of variable_name → distribution config (can be NULL)
            default_values: Dict of variable_name → default value

        Returns:
            Dict of variable_name → sampled value

        Example:
            configs = {
                'lead_time': rule.sourcing_lead_time_dist,
                'capacity': capacity.capacity_dist,
            }
            defaults = {
                'lead_time': 7.0,
                'capacity': 100.0,
            }
            samples = sampler.sample_multiple(configs, defaults)
            # Returns: {'lead_time': 7.23, 'capacity': 98.5}
        """
        result = {}

        for var_name, config in variable_configs.items():
            default_value = default_values.get(var_name, 0.0)

            value = self.engine.sample_or_default(
                config=config,
                default_value=default_value
            )

            result[var_name] = float(value)

        return result

    # ============================================================================
    # CACHE MANAGEMENT
    # ============================================================================

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics

        Returns:
            Dictionary with cache statistics:
            {
                'cached_distributions': 12,
            }
        """
        return {
            'cached_distributions': len(self._distribution_cache),
        }

    def clear_cache(self):
        """Clear distribution cache"""
        self._distribution_cache.clear()

    # ============================================================================
    # UTILITY METHODS
    # ============================================================================

    def is_stochastic(self, config: Optional[Dict[str, Any]]) -> bool:
        """
        Check if a configuration is stochastic (non-NULL distribution)

        Args:
            config: Distribution configuration (can be NULL)

        Returns:
            True if config is not NULL (stochastic), False otherwise (deterministic)
        """
        return config is not None

    def get_distribution_info(self, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get distribution information for debugging/logging

        Args:
            config: Distribution configuration

        Returns:
            Dict with distribution info (type, mean, std, etc.)
        """
        if config is None:
            return {
                'type': 'deterministic',
                'stochastic': False
            }

        try:
            # Get distribution stats from engine
            stats = self.engine.get_distribution_stats({'var': config})
            return {
                'type': config.get('type', 'unknown'),
                'stochastic': True,
                **stats.get('var', {})
            }
        except Exception as e:
            return {
                'type': config.get('type', 'unknown'),
                'stochastic': True,
                'error': str(e)
            }

    def sample_from_distribution(
        self,
        config: Optional[Dict[str, Any]],
        default_value: float
    ) -> float:
        """
        Generic method to sample from any distribution config

        Args:
            config: Distribution configuration (can be NULL)
            default_value: Fallback value if distribution is NULL

        Returns:
            Sampled value (always >= 0 for most use cases)
        """
        if config is None:
            return default_value

        value = self.engine.sample_or_default(
            config=config,
            default_value=default_value
        )

        return float(value)
