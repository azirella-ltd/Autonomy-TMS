"""
Stochastic Sampling Module for Supply Plan Generation

Provides functions to sample demand, lead times, and supplier reliability
distributions for Monte Carlo simulation in probabilistic supply planning.
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.stats import norm, poisson, uniform, lognorm
from sqlalchemy.orm import Session

from app.models.supply_chain_config import (
    SupplyChainConfig,
    TransportationLane,
    MarketDemand,
    Node,
)


class StochasticParameters:
    """Configuration for stochastic parameter sampling."""

    def __init__(
        self,
        demand_model: str = "normal",
        demand_variability: float = 0.15,
        lead_time_model: str = "normal",
        lead_time_variability: float = 0.10,
        supplier_reliability: float = 0.95,
        random_seed: Optional[int] = None
    ):
        """
        Initialize stochastic parameters.

        Args:
            demand_model: Distribution type for demand ("normal", "poisson", "empirical")
            demand_variability: Coefficient of variation for demand (std/mean)
            lead_time_model: Distribution type for lead time ("deterministic", "normal", "uniform")
            lead_time_variability: Coefficient of variation for lead time
            supplier_reliability: Probability of on-time delivery (0-1)
            random_seed: Seed for reproducibility
        """
        self.demand_model = demand_model
        self.demand_variability = demand_variability
        self.lead_time_model = lead_time_model
        self.lead_time_variability = lead_time_variability
        self.supplier_reliability = supplier_reliability
        self.random_seed = random_seed

        if random_seed is not None:
            np.random.seed(random_seed)


def sample_demand(
    session: Session,
    config: SupplyChainConfig,
    parameters: StochasticParameters,
    horizon: int
) -> Dict[int, np.ndarray]:
    """
    Sample demand scenarios for planning horizon.

    Args:
        session: Database session
        config: Supply chain configuration
        parameters: Stochastic sampling parameters
        horizon: Number of periods to sample

    Returns:
        Dictionary mapping {market_demand_id: demand_samples[horizon]}
    """
    market_demands = (
        session.query(MarketDemand)
        .filter(MarketDemand.config_id == config.id)
        .all()
    )

    demand_samples = {}

    for market_demand in market_demands:
        # Extract mean demand from demand_pattern
        demand_pattern = market_demand.demand_pattern or {}
        parameters_dict = demand_pattern.get("parameters", {})
        mean_demand = parameters_dict.get("mean", 100.0)

        if parameters.demand_model == "normal":
            # Normal distribution with specified variability
            std_dev = mean_demand * parameters.demand_variability
            samples = norm.rvs(loc=mean_demand, scale=std_dev, size=horizon)
            # Ensure non-negative demand
            samples = np.maximum(samples, 0)

        elif parameters.demand_model == "poisson":
            # Poisson distribution (discrete, non-negative)
            lambda_param = mean_demand
            samples = poisson.rvs(mu=lambda_param, size=horizon)

        elif parameters.demand_model == "lognormal":
            # Log-normal distribution (always positive, right-skewed)
            # Parameterize to match mean and CV
            cv = parameters.demand_variability
            sigma = np.sqrt(np.log(1 + cv**2))
            mu = np.log(mean_demand) - 0.5 * sigma**2
            samples = lognorm.rvs(s=sigma, scale=np.exp(mu), size=horizon)

        else:
            # Default to constant demand
            samples = np.full(horizon, mean_demand)

        demand_samples[market_demand.id] = samples

    return demand_samples


def sample_lead_times(
    session: Session,
    config: SupplyChainConfig,
    parameters: StochasticParameters
) -> Dict[int, int]:
    """
    Sample lead times for each lane (edge in supply chain network).

    Args:
        session: Database session
        config: Supply chain configuration
        parameters: Stochastic sampling parameters

    Returns:
        Dictionary mapping {lane_id: sampled_lead_time}
    """
    lanes = session.query(TransportationLane).filter(
        TransportationLane.config_id == config.id
    ).all()

    lead_time_samples = {}

    for lane in lanes:
        # Extract lead time from supply_lead_time JSON
        supply_lead_time_dict = lane.supply_lead_time or {}
        base_lead_time = supply_lead_time_dict.get("mean", 2)

        if parameters.lead_time_model == "deterministic":
            # No variability
            sampled_lead_time = base_lead_time

        elif parameters.lead_time_model == "normal":
            # Normal distribution truncated at minimum of 1 period
            std_dev = base_lead_time * parameters.lead_time_variability
            sampled = norm.rvs(loc=base_lead_time, scale=std_dev)
            sampled_lead_time = max(1, int(round(sampled)))

        elif parameters.lead_time_model == "uniform":
            # Uniform distribution around base lead time
            delta = base_lead_time * parameters.lead_time_variability
            lower = max(1, base_lead_time - delta)
            upper = base_lead_time + delta
            sampled = uniform.rvs(loc=lower, scale=upper - lower)
            sampled_lead_time = max(1, int(round(sampled)))

        else:
            sampled_lead_time = base_lead_time

        lead_time_samples[lane.id] = sampled_lead_time

    return lead_time_samples


def sample_supplier_reliability(
    session: Session,
    config: SupplyChainConfig,
    parameters: StochasticParameters,
    horizon: int
) -> Dict[int, np.ndarray]:
    """
    Sample supplier on-time delivery reliability for each period.

    Args:
        session: Database session
        config: Supply chain configuration
        parameters: Stochastic sampling parameters
        horizon: Number of periods

    Returns:
        Dictionary mapping {node_id: on_time_flags[horizon]}
        where on_time_flags[t] = 1 (on-time) or 0 (delayed)
    """
    # Get all supplier nodes
    all_nodes = session.query(Node).filter(Node.config_id == config.id).all()
    suppliers = [
        node for node in all_nodes
        if str(node.type).lower() in {"supplier", "component_supplier", "component supplier", "market_supply", "market supply"}
    ]

    reliability_samples = {}

    for supplier in suppliers:
        # Bernoulli trials: 1 = on-time, 0 = delayed
        on_time_prob = parameters.supplier_reliability
        samples = np.random.binomial(n=1, p=on_time_prob, size=horizon)
        reliability_samples[supplier.id] = samples

    return reliability_samples


def sample_manufacturing_yield(
    session: Session,
    config: SupplyChainConfig,
    yield_variability: float = 0.05,
    horizon: int = 52
) -> Dict[int, np.ndarray]:
    """
    Sample manufacturing yield variability (optional enhancement).

    Args:
        session: Database session
        config: Supply chain configuration
        yield_variability: Coefficient of variation for yield
        horizon: Number of periods

    Returns:
        Dictionary mapping {node_id: yield_multipliers[horizon]}
        where yield_multipliers[t] is the actual/expected yield ratio
    """
    all_nodes = session.query(Node).filter(Node.config_id == config.id).all()
    manufacturers = [
        node for node in all_nodes
        if str(node.type).lower() in {"manufacturer", "plant"}
    ]

    yield_samples = {}

    for manufacturer in manufacturers:
        # Normal distribution around 1.0 (100% yield)
        mean_yield = 1.0
        std_dev = mean_yield * yield_variability
        samples = norm.rvs(loc=mean_yield, scale=std_dev, size=horizon)
        # Ensure yield is between 0.5 and 1.0
        samples = np.clip(samples, 0.5, 1.0)
        yield_samples[manufacturer.id] = samples

    return yield_samples


def generate_scenario(
    session: Session,
    config: SupplyChainConfig,
    parameters: StochasticParameters,
    horizon: int,
    scenario_number: int
) -> Dict:
    """
    Generate a complete scenario with all stochastic parameters sampled.

    Args:
        session: Database session
        config: Supply chain configuration
        parameters: Stochastic sampling parameters
        horizon: Planning horizon in periods
        scenario_number: Scenario index for tracking

    Returns:
        Dictionary containing all sampled parameters for this scenario
    """
    # Set seed for this scenario for reproducibility
    if parameters.random_seed is not None:
        np.random.seed(parameters.random_seed + scenario_number)

    scenario = {
        "scenario_number": scenario_number,
        "config_id": config.id,
        "horizon": horizon,
        "demand_samples": sample_demand(session, config, parameters, horizon),
        "lead_time_samples": sample_lead_times(session, config, parameters),
        "supplier_reliability": sample_supplier_reliability(session, config, parameters, horizon),
        "manufacturing_yield": sample_manufacturing_yield(session, config, 0.05, horizon),
    }

    return scenario


def compute_scenario_statistics(
    scenarios: List[Dict],
    metric_name: str
) -> Dict:
    """
    Compute statistical summary for a metric across scenarios.

    Args:
        scenarios: List of scenario results
        metric_name: Name of the metric to analyze

    Returns:
        Dictionary with expected value, percentiles, and distribution
    """
    values = [scenario[metric_name] for scenario in scenarios if metric_name in scenario]

    if not values:
        return {
            "expected": None,
            "p10": None,
            "p50": None,
            "p90": None,
            "min": None,
            "max": None,
            "std_dev": None,
            "distribution": []
        }

    values_array = np.array(values)

    return {
        "expected": float(np.mean(values_array)),
        "p10": float(np.percentile(values_array, 10)),
        "p50": float(np.percentile(values_array, 50)),  # median
        "p90": float(np.percentile(values_array, 90)),
        "min": float(np.min(values_array)),
        "max": float(np.max(values_array)),
        "std_dev": float(np.std(values_array)),
        "distribution": values_array.tolist()
    }


def compute_probability_above_threshold(
    scenarios: List[Dict],
    metric_name: str,
    threshold: float
) -> float:
    """
    Compute probability that a metric exceeds a threshold.

    Args:
        scenarios: List of scenario results
        metric_name: Name of the metric
        threshold: Threshold value

    Returns:
        Probability (0-1) that metric > threshold
    """
    values = [scenario[metric_name] for scenario in scenarios if metric_name in scenario]

    if not values:
        return 0.0

    values_array = np.array(values)
    num_above = np.sum(values_array > threshold)

    return num_above / len(values_array)


def compute_probability_below_threshold(
    scenarios: List[Dict],
    metric_name: str,
    threshold: float
) -> float:
    """
    Compute probability that a metric is below a threshold.

    Args:
        scenarios: List of scenario results
        metric_name: Name of the metric
        threshold: Threshold value

    Returns:
        Probability (0-1) that metric < threshold
    """
    values = [scenario[metric_name] for scenario in scenarios if metric_name in scenario]

    if not values:
        return 0.0

    values_array = np.array(values)
    num_below = np.sum(values_array < threshold)

    return num_below / len(values_array)
