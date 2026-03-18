"""
Industry Default Stochastic Parameters

Provides sensible default distribution parameters for operational variables
based on customer industry vertical. These defaults are applied when a new
tenant is created, populating *_dist columns on ProductionProcess,
VendorLeadTime, and TransportationLane so that stochastic planning can
run immediately without waiting for SAP operational statistics extraction.

Parameters are derived from published industry benchmarks:
- APICS/ASCM Supply Chain Operations Reference (SCOR) model benchmarks
- Industry-specific lead time and yield studies
- Equipment reliability handbooks (MIL-HDBK-217, OREDA)

Convention: NULL *_dist = use deterministic base field. These defaults
are intentionally overwritten by SAP operational statistics when available.
"""

from typing import Dict, Any, List, Optional

# Distribution JSON format:
#   {"type": "lognormal", "mean_log": ..., "stddev_log": ..., "min": ..., "max": ...}
#   {"type": "beta", "alpha": ..., "beta": ..., "mean": ...}
#   {"type": "normal", "mean": ..., "stddev": ..., "min": ..., "max": ...}
#   {"type": "triangular", "min": ..., "mode": ..., "max": ...}


def _lognormal(mean: float, cv: float) -> Dict[str, Any]:
    """Build lognormal dist JSON from mean and coefficient of variation."""
    import math
    stddev = mean * cv
    var = stddev ** 2
    mu_log = math.log(mean ** 2 / math.sqrt(var + mean ** 2))
    sigma_log = math.sqrt(math.log(1 + var / mean ** 2))
    return {
        "type": "lognormal",
        "mean_log": round(mu_log, 6),
        "stddev_log": round(sigma_log, 6),
        "mean": round(mean, 2),
        "stddev": round(stddev, 2),
        "min": round(max(mean * 0.3, 0.5), 2),
        "max": round(mean * 2.5, 2),
    }


def _beta(mean: float, concentration: float = 30) -> Dict[str, Any]:
    """Build beta dist JSON from mean (0-1) and concentration."""
    alpha = mean * concentration
    beta_param = (1 - mean) * concentration
    return {
        "type": "beta",
        "alpha": round(max(alpha, 1.0), 4),
        "beta": round(max(beta_param, 1.0), 4),
        "mean": round(mean, 4),
    }


def _normal(mean: float, cv: float) -> Dict[str, Any]:
    """Build normal dist JSON from mean and CV."""
    stddev = mean * cv
    return {
        "type": "normal",
        "mean": round(mean, 2),
        "stddev": round(stddev, 2),
        "min": round(max(mean - 3 * stddev, 0), 2),
        "max": round(mean + 3 * stddev, 2),
    }


# ============================================================================
# Industry Default Parameters
#
# Each industry entry contains default distributions for:
#   supplier_lead_time_days  - Avg supplier lead time
#   supplier_lead_time_cv    - Coefficient of variation for supplier LT
#   supplier_on_time_rate    - Fraction of on-time deliveries
#   manufacturing_yield      - First-pass yield (0-1)
#   manufacturing_cycle_days - Avg production cycle time
#   manufacturing_cycle_cv   - CV for cycle time
#   setup_time_hours         - Avg changeover/setup time
#   setup_time_cv            - CV for setup time
#   mtbf_days                - Mean time between failures
#   mtbf_cv                  - CV for MTBF
#   mttr_hours               - Mean time to repair
#   mttr_cv                  - CV for MTTR
#   transport_lead_days      - Avg transportation lead time
#   transport_lead_cv        - CV for transport LT
#   quality_rejection_rate   - Fraction rejected at inspection
#   demand_cv                - Demand coefficient of variation
# ============================================================================

INDUSTRY_DEFAULTS: Dict[str, Dict[str, float]] = {
    "food_beverage": {
        "supplier_lead_time_days": 7,
        "supplier_lead_time_cv": 0.25,
        "supplier_on_time_rate": 0.92,
        "manufacturing_yield": 0.96,
        "manufacturing_cycle_days": 1.5,
        "manufacturing_cycle_cv": 0.30,
        "setup_time_hours": 1.5,
        "setup_time_cv": 0.35,
        "mtbf_days": 45,
        "mtbf_cv": 0.50,
        "mttr_hours": 4,
        "mttr_cv": 0.60,
        "transport_lead_days": 2,
        "transport_lead_cv": 0.30,
        "quality_rejection_rate": 0.02,
        "demand_cv": 0.30,
    },
    "pharmaceutical": {
        "supplier_lead_time_days": 30,
        "supplier_lead_time_cv": 0.20,
        "supplier_on_time_rate": 0.88,
        "manufacturing_yield": 0.92,
        "manufacturing_cycle_days": 14,
        "manufacturing_cycle_cv": 0.25,
        "setup_time_hours": 8,
        "setup_time_cv": 0.20,
        "mtbf_days": 60,
        "mtbf_cv": 0.40,
        "mttr_hours": 8,
        "mttr_cv": 0.50,
        "transport_lead_days": 5,
        "transport_lead_cv": 0.20,
        "quality_rejection_rate": 0.05,
        "demand_cv": 0.20,
    },
    "automotive": {
        "supplier_lead_time_days": 14,
        "supplier_lead_time_cv": 0.30,
        "supplier_on_time_rate": 0.94,
        "manufacturing_yield": 0.985,
        "manufacturing_cycle_days": 3,
        "manufacturing_cycle_cv": 0.15,
        "setup_time_hours": 2,
        "setup_time_cv": 0.25,
        "mtbf_days": 30,
        "mtbf_cv": 0.45,
        "mttr_hours": 6,
        "mttr_cv": 0.55,
        "transport_lead_days": 3,
        "transport_lead_cv": 0.25,
        "quality_rejection_rate": 0.008,
        "demand_cv": 0.25,
    },
    "electronics": {
        "supplier_lead_time_days": 21,
        "supplier_lead_time_cv": 0.40,
        "supplier_on_time_rate": 0.85,
        "manufacturing_yield": 0.94,
        "manufacturing_cycle_days": 5,
        "manufacturing_cycle_cv": 0.30,
        "setup_time_hours": 3,
        "setup_time_cv": 0.30,
        "mtbf_days": 90,
        "mtbf_cv": 0.55,
        "mttr_hours": 3,
        "mttr_cv": 0.50,
        "transport_lead_days": 7,
        "transport_lead_cv": 0.35,
        "quality_rejection_rate": 0.03,
        "demand_cv": 0.40,
    },
    "chemical": {
        "supplier_lead_time_days": 21,
        "supplier_lead_time_cv": 0.20,
        "supplier_on_time_rate": 0.90,
        "manufacturing_yield": 0.95,
        "manufacturing_cycle_days": 2,
        "manufacturing_cycle_cv": 0.20,
        "setup_time_hours": 4,
        "setup_time_cv": 0.25,
        "mtbf_days": 40,
        "mtbf_cv": 0.50,
        "mttr_hours": 12,
        "mttr_cv": 0.60,
        "transport_lead_days": 4,
        "transport_lead_cv": 0.25,
        "quality_rejection_rate": 0.015,
        "demand_cv": 0.20,
    },
    "industrial_equipment": {
        "supplier_lead_time_days": 28,
        "supplier_lead_time_cv": 0.35,
        "supplier_on_time_rate": 0.87,
        "manufacturing_yield": 0.97,
        "manufacturing_cycle_days": 10,
        "manufacturing_cycle_cv": 0.30,
        "setup_time_hours": 4,
        "setup_time_cv": 0.30,
        "mtbf_days": 60,
        "mtbf_cv": 0.50,
        "mttr_hours": 8,
        "mttr_cv": 0.55,
        "transport_lead_days": 5,
        "transport_lead_cv": 0.30,
        "quality_rejection_rate": 0.01,
        "demand_cv": 0.35,
    },
    "consumer_goods": {
        "supplier_lead_time_days": 10,
        "supplier_lead_time_cv": 0.25,
        "supplier_on_time_rate": 0.93,
        "manufacturing_yield": 0.97,
        "manufacturing_cycle_days": 2,
        "manufacturing_cycle_cv": 0.25,
        "setup_time_hours": 1,
        "setup_time_cv": 0.30,
        "mtbf_days": 50,
        "mtbf_cv": 0.45,
        "mttr_hours": 3,
        "mttr_cv": 0.50,
        "transport_lead_days": 3,
        "transport_lead_cv": 0.25,
        "quality_rejection_rate": 0.015,
        "demand_cv": 0.35,
    },
    "metals_mining": {
        "supplier_lead_time_days": 35,
        "supplier_lead_time_cv": 0.30,
        "supplier_on_time_rate": 0.85,
        "manufacturing_yield": 0.93,
        "manufacturing_cycle_days": 7,
        "manufacturing_cycle_cv": 0.25,
        "setup_time_hours": 6,
        "setup_time_cv": 0.30,
        "mtbf_days": 25,
        "mtbf_cv": 0.55,
        "mttr_hours": 16,
        "mttr_cv": 0.65,
        "transport_lead_days": 7,
        "transport_lead_cv": 0.30,
        "quality_rejection_rate": 0.025,
        "demand_cv": 0.25,
    },
    "aerospace_defense": {
        "supplier_lead_time_days": 60,
        "supplier_lead_time_cv": 0.25,
        "supplier_on_time_rate": 0.82,
        "manufacturing_yield": 0.96,
        "manufacturing_cycle_days": 30,
        "manufacturing_cycle_cv": 0.20,
        "setup_time_hours": 8,
        "setup_time_cv": 0.20,
        "mtbf_days": 120,
        "mtbf_cv": 0.40,
        "mttr_hours": 12,
        "mttr_cv": 0.50,
        "transport_lead_days": 7,
        "transport_lead_cv": 0.20,
        "quality_rejection_rate": 0.005,
        "demand_cv": 0.15,
    },
    "building_materials": {
        "supplier_lead_time_days": 14,
        "supplier_lead_time_cv": 0.30,
        "supplier_on_time_rate": 0.88,
        "manufacturing_yield": 0.95,
        "manufacturing_cycle_days": 3,
        "manufacturing_cycle_cv": 0.25,
        "setup_time_hours": 2,
        "setup_time_cv": 0.30,
        "mtbf_days": 35,
        "mtbf_cv": 0.50,
        "mttr_hours": 6,
        "mttr_cv": 0.55,
        "transport_lead_days": 4,
        "transport_lead_cv": 0.35,
        "quality_rejection_rate": 0.02,
        "demand_cv": 0.30,
    },
    "textile_apparel": {
        "supplier_lead_time_days": 45,
        "supplier_lead_time_cv": 0.35,
        "supplier_on_time_rate": 0.83,
        "manufacturing_yield": 0.92,
        "manufacturing_cycle_days": 5,
        "manufacturing_cycle_cv": 0.30,
        "setup_time_hours": 1.5,
        "setup_time_cv": 0.35,
        "mtbf_days": 40,
        "mtbf_cv": 0.50,
        "mttr_hours": 4,
        "mttr_cv": 0.50,
        "transport_lead_days": 14,
        "transport_lead_cv": 0.30,
        "quality_rejection_rate": 0.04,
        "demand_cv": 0.45,
    },
    "wholesale_distribution": {
        "supplier_lead_time_days": 10,
        "supplier_lead_time_cv": 0.25,
        "supplier_on_time_rate": 0.91,
        "manufacturing_yield": 0.99,  # No manufacturing — passthrough
        "manufacturing_cycle_days": 0.5,
        "manufacturing_cycle_cv": 0.20,
        "setup_time_hours": 0.5,
        "setup_time_cv": 0.25,
        "mtbf_days": 90,
        "mtbf_cv": 0.40,
        "mttr_hours": 2,
        "mttr_cv": 0.40,
        "transport_lead_days": 2,
        "transport_lead_cv": 0.30,
        "quality_rejection_rate": 0.005,
        "demand_cv": 0.30,
    },
    "third_party_logistics": {
        "supplier_lead_time_days": 5,
        "supplier_lead_time_cv": 0.20,
        "supplier_on_time_rate": 0.94,
        "manufacturing_yield": 0.99,  # No manufacturing
        "manufacturing_cycle_days": 0.25,
        "manufacturing_cycle_cv": 0.15,
        "setup_time_hours": 0.25,
        "setup_time_cv": 0.20,
        "mtbf_days": 120,
        "mtbf_cv": 0.35,
        "mttr_hours": 2,
        "mttr_cv": 0.40,
        "transport_lead_days": 2,
        "transport_lead_cv": 0.25,
        "quality_rejection_rate": 0.003,
        "demand_cv": 0.25,
    },
}


def get_industry_distributions(industry: str) -> Dict[str, Dict[str, Any]]:
    """Return distribution parameter dicts for a given industry.

    Returns a dict with keys:
        supplier_lead_time_dist, supplier_on_time_dist,
        manufacturing_yield_dist, manufacturing_cycle_dist,
        setup_time_dist, mtbf_dist, mttr_dist,
        transport_lead_dist, quality_rejection_dist
    """
    params = INDUSTRY_DEFAULTS.get(industry, INDUSTRY_DEFAULTS["consumer_goods"])

    return {
        "supplier_lead_time_dist": _lognormal(
            params["supplier_lead_time_days"],
            params["supplier_lead_time_cv"],
        ),
        "supplier_on_time_dist": _beta(params["supplier_on_time_rate"]),
        "manufacturing_yield_dist": _beta(params["manufacturing_yield"], concentration=50),
        "manufacturing_cycle_dist": _lognormal(
            params["manufacturing_cycle_days"],
            params["manufacturing_cycle_cv"],
        ),
        "setup_time_dist": _lognormal(
            params["setup_time_hours"],
            params["setup_time_cv"],
        ),
        "mtbf_dist": _lognormal(params["mtbf_days"], params["mtbf_cv"]),
        "mttr_dist": _lognormal(params["mttr_hours"], params["mttr_cv"]),
        "transport_lead_dist": _lognormal(
            params["transport_lead_days"],
            params["transport_lead_cv"],
        ),
        "quality_rejection_dist": _beta(
            params["quality_rejection_rate"],
            concentration=100,
        ),
    }


def apply_industry_defaults_to_config(
    db,
    config_id: int,
    industry: str,
) -> Dict[str, int]:
    """Apply industry-default distribution parameters to all entities in a config.

    Updates ProductionProcess, VendorLeadTime, and TransportationLane records
    that belong to the given config and currently have NULL *_dist columns.
    Only fills in defaults — never overwrites SAP-derived distributions.

    Returns counts of updated records by entity type.
    """
    from app.models.sc_entities import ProductionProcess
    from app.models.supply_chain_config import TransportationLane, Site
    from app.models.supplier import VendorLeadTime

    dists = get_industry_distributions(industry)
    counts: Dict[str, int] = {"production_process": 0, "vendor_lead_time": 0, "transportation_lane": 0}

    # --- ProductionProcess ---
    procs = db.query(ProductionProcess).filter(
        ProductionProcess.config_id == config_id,
    ).all()
    for proc in procs:
        changed = False
        if proc.operation_time_dist is None:
            proc.operation_time_dist = dists["manufacturing_cycle_dist"]
            if proc.operation_time is None:
                proc.operation_time = dists["manufacturing_cycle_dist"]["mean"]
            changed = True
        if proc.setup_time_dist is None:
            proc.setup_time_dist = dists["setup_time_dist"]
            if proc.setup_time is None:
                proc.setup_time = dists["setup_time_dist"]["mean"]
            changed = True
        if proc.yield_dist is None:
            proc.yield_dist = dists["manufacturing_yield_dist"]
            if proc.yield_percentage is None:
                proc.yield_percentage = dists["manufacturing_yield_dist"]["mean"]
            changed = True
        if proc.mtbf_dist is None:
            proc.mtbf_dist = dists["mtbf_dist"]
            changed = True
        if proc.mttr_dist is None:
            proc.mttr_dist = dists["mttr_dist"]
            changed = True
        if changed:
            counts["production_process"] += 1

    # --- VendorLeadTime (via sites belonging to config) ---
    site_ids = [s.id for s in db.query(Site.id).filter(Site.config_id == config_id).all()]
    if site_ids:
        vlts = db.query(VendorLeadTime).filter(
            VendorLeadTime.site_id.in_(site_ids),
            VendorLeadTime.lead_time_dist.is_(None),
        ).all()
        for vlt in vlts:
            vlt.lead_time_dist = dists["supplier_lead_time_dist"]
            if vlt.lead_time_variability_days is None:
                vlt.lead_time_variability_days = dists["supplier_lead_time_dist"]["stddev"]
            counts["vendor_lead_time"] += 1

    # --- TransportationLane ---
    lanes = db.query(TransportationLane).filter(
        TransportationLane.config_id == config_id,
        TransportationLane.supply_lead_time_dist.is_(None),
    ).all()
    for lane in lanes:
        lane.supply_lead_time_dist = dists["transport_lead_dist"]
        counts["transportation_lane"] += 1

    db.flush()
    return counts


# ============================================================================
# Per-Agent Stochastic Parameters (agent_stochastic_params table)
# ============================================================================

# Maps param_name (used in TRM_PARAM_MAP) → key in get_industry_distributions()
_PARAM_TO_DIST_KEY = {
    "demand_variability": "demand_variability",
    "supplier_lead_time": "supplier_lead_time_dist",
    "supplier_on_time": "supplier_on_time_dist",
    "manufacturing_cycle_time": "manufacturing_cycle_dist",
    "manufacturing_yield": "manufacturing_yield_dist",
    "setup_time": "setup_time_dist",
    "mtbf": "mtbf_dist",
    "mttr": "mttr_dist",
    "transport_lead_time": "transport_lead_dist",
    "quality_rejection_rate": "quality_rejection_dist",
}


def get_agent_distributions(industry: str) -> Dict[str, Dict[str, Any]]:
    """Return distribution dicts keyed by canonical param_name.

    These keys match the param_name column in agent_stochastic_params
    and the entries in TRM_PARAM_MAP.
    """
    dists = get_industry_distributions(industry)
    params = INDUSTRY_DEFAULTS.get(industry, INDUSTRY_DEFAULTS["consumer_goods"])

    # demand_variability is not in get_industry_distributions — build it here
    demand_dist = _normal(1.0, params["demand_cv"])
    demand_dist["description"] = f"CV={params['demand_cv']}"

    result = {}
    for param_name, dist_key in _PARAM_TO_DIST_KEY.items():
        if param_name == "demand_variability":
            result[param_name] = demand_dist
        else:
            result[param_name] = dists[dist_key]
    return result


def apply_agent_stochastic_defaults(
    db,
    config_id: int,
    tenant_id: int,
    industry: str,
    *,
    only_defaults: bool = False,
) -> int:
    """Populate agent_stochastic_params rows for all TRM types.

    Creates one row per (config_id, trm_type, param_name) with config-wide
    scope (site_id=NULL). Rows are marked is_default=True, source='industry_default'.

    Args:
        db: SQLAlchemy session
        config_id: Supply chain config to populate
        tenant_id: Owning tenant
        industry: Industry key (e.g. 'food_beverage')
        only_defaults: If True, only update rows where is_default=True
                       (used when industry changes on an existing tenant)

    Returns:
        Number of rows created or updated.
    """
    from app.models.agent_stochastic_param import (
        AgentStochasticParam, TRM_PARAM_MAP,
    )

    agent_dists = get_agent_distributions(industry)
    count = 0

    for trm_type, param_names in TRM_PARAM_MAP.items():
        for param_name in param_names:
            dist = agent_dists.get(param_name)
            if not dist:
                continue

            existing = db.query(AgentStochasticParam).filter(
                AgentStochasticParam.config_id == config_id,
                AgentStochasticParam.trm_type == trm_type,
                AgentStochasticParam.param_name == param_name,
                AgentStochasticParam.site_id.is_(None),
            ).first()

            if existing:
                if only_defaults and not existing.is_default:
                    # Skip — this value was manually edited or SAP-imported
                    continue
                existing.distribution = dist
                existing.is_default = True
                existing.source = "industry_default"
            else:
                db.add(AgentStochasticParam(
                    config_id=config_id,
                    tenant_id=tenant_id,
                    site_id=None,
                    trm_type=trm_type,
                    param_name=param_name,
                    distribution=dist,
                    is_default=True,
                    source="industry_default",
                ))
            count += 1

    db.flush()
    return count
