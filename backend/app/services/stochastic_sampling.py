"""
Stochastic Sampling Module for Supply Plan Generation

DB-coupled sampling functions that query TMS models (Forecast, TransportationLane,
Site) and delegate to pure-math helpers in azirella_data_model.stochastic.sampling.

Pure math (StochasticParameters, statistics, Weibull helpers, distribution-aware
sampling) lives in Autonomy-Core: azirella_data_model.stochastic.sampling
"""

from typing import Dict, List, Optional
import logging
import numpy as np
from scipy.stats import lognorm
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models.supply_chain_config import (
    SupplyChainConfig,
    TransportationLane,
    Site as Node,
)
from app.models.sc_entities import Forecast

# Re-export Core pure-math classes/functions so existing imports keep working
from azirella_data_model.stochastic.sampling import (  # noqa: F401
    StochasticParameters,
    compute_scenario_statistics,
    compute_probability_above_threshold,
    compute_probability_below_threshold,
    sample_demand_from_mean,
    sample_lead_time as _sample_lead_time_pure,
    sample_supplier_reliability_bernoulli,
    sample_manufacturing_yield as _sample_manufacturing_yield_pure,
    sample_weibull_lead_time as _sample_weibull_lead_time,
    weibull_shape_from_cv as _weibull_shape_from_cv,
    auto_sample_demand_from_history,
)


def sample_demand(
    session: Session,
    config: SupplyChainConfig,
    parameters: StochasticParameters,
    horizon: int
) -> Dict[int, np.ndarray]:
    """
    Sample demand scenarios for planning horizon.

    Uses Forecast table (P50 median forecast) to derive mean demand per
    product, then generates stochastic samples around it.

    Args:
        session: Database session
        config: Supply chain configuration
        parameters: Stochastic sampling parameters
        horizon: Number of periods to sample

    Returns:
        Dictionary mapping {product_id: demand_samples[horizon]}
    """
    from sqlalchemy import func

    # Get average P50 forecast per product from the Forecast table
    forecast_means = (
        session.query(
            Forecast.product_id,
            func.avg(Forecast.forecast_p50).label("mean_demand"),
        )
        .filter(
            Forecast.config_id == config.id,
            Forecast.forecast_p50.isnot(None),
        )
        .group_by(Forecast.product_id)
        .all()
    )

    if not forecast_means:
        logger.warning("No forecasts found for config %s — demand sampling returns empty", config.id)
        return {}

    demand_samples = {}

    for row in forecast_means:
        product_id = row.product_id
        mean_demand = float(row.mean_demand or 100.0)

        if parameters.demand_model == "auto":
            # Auto-detect best distribution from forecast data
            demand_pattern = {"parameters": {"mean": mean_demand}}
            samples = _auto_sample_demand(
                demand_pattern, mean_demand, horizon, parameters
            )
        else:
            # Delegate to Core pure-math sampler
            samples = sample_demand_from_mean(
                mean_demand, parameters.demand_model,
                parameters.demand_variability, horizon,
            )

        demand_samples[product_id] = samples

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

        if parameters.lead_time_model == "auto":
            # Auto-detect from historical lane data (DB-coupled)
            sampled_lead_time = _auto_sample_lead_time(
                session, lane, base_lead_time, parameters
            )
        else:
            # Delegate to Core pure-math sampler
            sampled_lead_time = _sample_lead_time_pure(
                base_lead_time, parameters.lead_time_model,
                parameters.lead_time_variability,
            )

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
        if str(node.type).lower() in {"supplier", "component_supplier", "component supplier", "vendor", "market supply"}
    ]

    reliability_samples = {}

    for supplier in suppliers:
        reliability_samples[supplier.id] = sample_supplier_reliability_bernoulli(
            parameters.supplier_reliability, horizon
        )

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
        yield_samples[manufacturer.id] = _sample_manufacturing_yield_pure(
            yield_variability, horizon
        )

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


# ============================================================================
# DB-coupled auto-detection helpers (remain in TMS)
# ============================================================================

def _auto_sample_demand(
    demand_pattern: dict,
    mean_demand: float,
    horizon: int,
    parameters,
) -> np.ndarray:
    """Auto-detect best demand distribution and sample from it.

    Tries to extract historical data from the demand_pattern JSON. If
    enough historical values exist, fits candidate distributions and
    samples from the best fit. Otherwise falls back to lognormal.
    """
    # Check for historical values in demand_pattern
    historical = demand_pattern.get("historical_values", [])
    if isinstance(historical, list) and len(historical) >= 10:
        try:
            from app.services.stochastic.distribution_fitter import DistributionFitter
            fitter = DistributionFitter()
            data = np.array(historical, dtype=float)
            data = data[np.isfinite(data) & (data >= 0)]
            if len(data) >= fitter.MIN_SAMPLES_FOR_FIT:
                report = fitter.fit(data, variable_type="demand")
                samples = report.best.distribution.sample(size=horizon)
                return np.maximum(samples, 0)
        except Exception as e:
            logger.debug("Auto demand fit failed, using lognormal fallback: %s", e)

    # Fallback: lognormal (better default than normal for demand)
    cv = max(0.01, parameters.demand_variability)
    sigma = np.sqrt(np.log(1 + cv ** 2))
    mu = np.log(max(0.01, mean_demand)) - 0.5 * sigma ** 2
    return lognorm.rvs(s=sigma, scale=np.exp(mu), size=horizon)


def _auto_sample_lead_time(
    session: Session,
    lane: "TransportationLane",
    base_lead_time: float,
    parameters,
) -> int:
    """Auto-detect best lead time distribution and sample from it.

    Queries historical lead time data for this lane. If enough records exist,
    fits candidate distributions and samples. Otherwise defaults to Weibull.
    """
    try:
        from app.models.supplier import VendorLeadTime
        from app.services.stochastic.distribution_fitter import DistributionFitter

        # Try to find historical LT data for this lane's destination
        records = (
            session.query(VendorLeadTime.lead_time_days)
            .filter(VendorLeadTime.site_id == lane.to_site_id)
            .order_by(VendorLeadTime.id.desc())
            .limit(100)
            .all()
        )
        lt_values = [float(r[0]) for r in records if r[0] is not None and r[0] > 0]

        if len(lt_values) >= 5:
            fitter = DistributionFitter()
            data = np.array(lt_values, dtype=float)
            report = fitter.fit(data, variable_type="lead_time")
            sampled = float(report.best.distribution.sample(size=1)[0])
            return max(1, int(round(sampled)))
    except Exception as e:
        logger.debug("Auto LT fit failed, using weibull fallback: %s", e)

    # Fallback: Weibull with specified CV
    return _sample_weibull_lead_time(base_lead_time, parameters.lead_time_variability)
