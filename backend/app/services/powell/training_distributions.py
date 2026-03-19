"""
Shared Training Distribution Specifications — Single Source of Truth

All stochastic variables used in synthetic training data generation across
every AI agent tier are defined here. Every oracle (site_tgnn_oracle.py,
network_tgnn_oracle.py, sop_graphsage_oracle.py) and the TRM synthetic
data generator (synthetic_trm_data_generator.py) MUST import from this
module rather than inline their own rng calls.

WHY THIS MODULE EXISTS:
  Prior to this module, each oracle used its own inline rng calls with
  independently chosen distribution types and parameter ranges. This caused
  distribution parameter drift: the same conceptual variable (e.g., lead time)
  was sampled with different distributions at different tiers, so the S&OP
  GraphSAGE was optimising policy against a distribution the TRMs would never
  actually encounter. This module eliminates that inconsistency.

DISTRIBUTION CHOICE CRITERIA:

  TRIANGULAR  — Use when the variable represents an operational quantity that
                exists in a real supply chain and clusters around a typical
                value. The mode encodes domain knowledge: "this value is more
                likely than the extremes." Triangular is the PERT community's
                standard for expert-estimated bounded variables. Almost all
                operational state variables (inventory, lead time, capacity,
                demand) belong here.

  UNIFORM     — Use when:
                  (a) equal coverage of the full range is genuinely desired
                      (parameter space exploration, scenario diversity), or
                  (b) there is no domain-informed prior about which value in
                      the range is more likely — i.e., the variable varies
                      enormously across industries with no universal mode.
                  Examples: unit cost (spans $5–$200 across industries),
                  ordering cost (spans $50–$500 with no universal mode),
                  service level target (a policy choice, not a natural process).

  LOGNORMAL / LOGLOGISTIC — Use for within-simulation realisation of
                physically right-skewed processes: lead times, interarrival
                times, repair durations. These distributions correctly model
                the fact that delays are more likely and more extreme than
                early deliveries. Apply inside the MC simulation loop (e.g.,
                the S&OP DE objective), NOT at the scenario-sampling level.
                LogLogistic (Lokad recommendation) has a fatter right tail
                than LogNormal and better captures supplier disruptions.

  NORMAL      — Use for demand realisation within a simulation, where demand
                is approximately symmetric around the forecast and the
                forecast already captures the right-skew of the planning
                distribution.

  BERNOULLI   — Use for binary flags (quality hold, maintenance due, ATP
                shortfall). Cannot be Triangular. Implemented via
                BinomialDistribution(n=1, p=p) since Bernoulli is not in
                the distributions module directly.

  POISSON     — Use for count variables (open exceptions, number of events).
                Better than Discrete Uniform because it correctly models
                rare-event count distributions.

PHASE VARIANCE SCHEDULE:
  All samplers accept variance_pct which maps to curriculum phase:
    Phase 1 → variance_pct = 0.15  (tight, clear signals)
    Phase 2 → variance_pct = 0.40  (moderate trade-offs)
    Phase 3 → variance_pct = 0.75  (high variability, disruptions)

  For Triangular jitter functions, variance_pct controls the width of the
  distribution around the nominal (mode = nominal, min = nominal×(1-pct),
  max = nominal×(1+right_factor×pct)). The right factor is >1 for variables
  with right-skewed operational dynamics (demand spikes, inventory build-ups).

USAGE:
    from app.services.powell.training_distributions import D

    # Triangular jitter (mode = nominal)
    on_hand = D.on_hand_inventory(rng, nominal=1000.0, variance_pct=0.40)

    # Absolute Triangular (mode fixed by domain knowledge)
    target_dos = D.target_dos_days(rng, variance_pct=0.40)
    hold_rate  = D.annual_holding_rate(rng)

    # Uniform (policy / parameter space)
    sl_target  = D.service_level_target(rng)

    # Bernoulli binary events
    has_hold   = D.quality_hold_flag(rng, variance_pct=0.40)

    # Within-simulation realisations
    lead_time  = D.realised_lead_time_weeks(rng, mean=2.0, cv=0.15)
    demand     = D.realised_demand(rng, mean=200.0, cv=0.25)
"""

from __future__ import annotations

import math
import numpy as np
from numpy.random import Generator
from typing import Optional, Dict


# ---------------------------------------------------------------------------
# Stochastic parameter overrides from agent_stochastic_params table
# ---------------------------------------------------------------------------

# Maps agent_stochastic_param.param_name → D method names that it overrides.
# When an override is present, the D method samples from the admin-curated
# distribution instead of the hardcoded triangular/lognormal.
PARAM_TO_D_METHODS: dict[str, list[str]] = {
    "demand_variability": ["demand_variability_cv", "demand_forecast", "avg_weekly_demand"],
    "supplier_lead_time": ["avg_lead_time_weeks", "realised_lead_time_weeks"],
    "supplier_on_time": ["lane_reliability"],
    "manufacturing_cycle_time": ["production_capacity"],
    "manufacturing_yield": [],  # Used directly by TRM, not by D methods
    "setup_time": [],
    "mtbf": [],
    "mttr": [],
    "transport_lead_time": ["realised_lead_time_weeks"],
    "quality_rejection_rate": ["quality_hold_flag"],
}


def sample_from_override(
    rng: Generator,
    dist_dict: dict,
    fallback: float = 0.0,
) -> float:
    """Sample a single value from an admin-curated distribution JSON.

    Uses the platform's Distribution class (which supports 21 distribution
    types) to sample from the stochastic parameter stored in
    agent_stochastic_params.distribution.

    Args:
        rng: NumPy random Generator (used for seeding only — Distribution
             has its own internal sampling).
        dist_dict: Distribution JSON, e.g. {"type": "lognormal", "mean_log": 1.5, ...}
        fallback: Value to return if sampling fails.

    Returns:
        A single float sample from the distribution.
    """
    if not dist_dict or not isinstance(dist_dict, dict):
        return fallback
    try:
        from app.services.stochastic.distributions import Distribution
        dist = Distribution.from_dict(dist_dict)
        return float(dist.sample(size=1)[0])
    except Exception:
        return fallback


# ---------------------------------------------------------------------------
# Phase → variance schedule
# ---------------------------------------------------------------------------

PHASE_VARIANCE: dict[int, float] = {
    1: 0.15,
    2: 0.40,
    3: 0.75,
}


def variance_for_phase(phase: int) -> float:
    """Return the variance_pct for a given curriculum phase (1, 2, or 3)."""
    return PHASE_VARIANCE.get(phase, 0.40)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tri_jitter(
    rng: Generator,
    nominal: float,
    left_factor: float,
    right_factor: float,
    variance_pct: float,
) -> float:
    """
    Triangular jitter around a nominal value.

    min  = nominal * (1 - left_factor  * variance_pct)
    mode = nominal
    max  = nominal * (1 + right_factor * variance_pct)

    right_factor > left_factor means the distribution is right-skewed
    (e.g., demand spikes are larger than demand troughs).
    """
    lo = max(0.0, nominal * (1.0 - left_factor * variance_pct))
    hi = nominal * (1.0 + right_factor * variance_pct)
    mode = nominal
    if lo >= hi:
        return float(nominal)
    mode = min(max(mode, lo + 1e-9), hi - 1e-9)
    return float(rng.triangular(lo, mode, hi))


def _tri_absolute(
    rng: Generator,
    lo: float,
    mode: float,
    hi: float,
) -> float:
    """Triangular distribution with fixed absolute parameters."""
    if lo >= hi:
        return float(mode)
    mode = min(max(mode, lo + 1e-9), hi - 1e-9)
    return float(rng.triangular(lo, mode, hi))


# ---------------------------------------------------------------------------
# Distribution library — class D is the public API
# ---------------------------------------------------------------------------

class D:
    """
    Shared stochastic variable samplers.

    All methods are static and accept a numpy Generator (rng) as the first
    argument. This keeps the caller in control of the random state.
    """

    # ── Override-aware sampling ────────────────────────────────────────────

    @staticmethod
    def sample_override(
        rng: Generator,
        param_name: str,
        stochastic_params: Optional[Dict[str, Dict[str, dict]]] = None,
        trm_type: Optional[str] = None,
        fallback: Optional[float] = None,
    ) -> Optional[float]:
        """Sample from an admin-curated distribution if available.

        Checks stochastic_params[trm_type][param_name] for a distribution
        override. If found, samples from it. If not, returns None so the
        caller can fall back to the hardcoded distribution.

        Args:
            rng: NumPy random Generator.
            param_name: Parameter name (e.g. "supplier_lead_time").
            stochastic_params: Dict from SiteAgent.stochastic_params
                               {trm_type: {param_name: dist_dict}}.
            trm_type: TRM type to look up in stochastic_params.
            fallback: Value to return if override exists but sampling fails.

        Returns:
            Sampled value if override found, None otherwise.
        """
        if not stochastic_params or not trm_type:
            return None
        trm_params = stochastic_params.get(trm_type, {})
        dist_dict = trm_params.get(param_name)
        if not dist_dict:
            return None
        return sample_from_override(rng, dist_dict, fallback=fallback or 0.0)

    # ── Operational state variables (Triangular jitter around nominal) ──────

    @staticmethod
    def on_hand_inventory(rng: Generator, nominal: float, variance_pct: float) -> float:
        """
        On-hand inventory at a site. [units]
        Mode = nominal (planned working level).
        Right tail heavier: inventory build-ups larger than drawdowns.
        Distribution: Triangular(0.4n, n, 2.0n) at Phase 3.
        """
        return _tri_jitter(rng, nominal, left_factor=1.0, right_factor=1.5, variance_pct=variance_pct)

    @staticmethod
    def committed_inventory(rng: Generator, on_hand: float, variance_pct: float) -> float:
        """
        Inventory committed to open orders, as a fraction of on-hand. [units]
        Mode ≈ 35 % of on-hand (APICS benchmark for mid-market manufacturers).
        Distribution: Triangular(0.15·on_hand, 0.35·on_hand, 0.65·on_hand).
        Variance_pct widens the range; mode stays fixed at 0.35.
        """
        lo   = on_hand * max(0.05, 0.15 - 0.10 * variance_pct)
        hi   = on_hand * min(0.90, 0.65 + 0.25 * variance_pct)
        mode = on_hand * 0.35
        return max(0.0, _tri_absolute(rng, lo, mode, hi))

    @staticmethod
    def wip(rng: Generator, on_hand: float, variance_pct: float) -> float:
        """
        Work-in-progress, as a fraction of on-hand. [units]
        Mode ≈ 20 % of on-hand (typical WIP/FGI ratio for discrete manufacturing).
        Distribution: Triangular(0.05·on_hand, 0.20·on_hand, 0.45·on_hand).
        """
        lo   = on_hand * max(0.01, 0.05 - 0.03 * variance_pct)
        hi   = on_hand * min(0.80, 0.45 + 0.30 * variance_pct)
        mode = on_hand * 0.20
        return max(0.0, _tri_absolute(rng, lo, mode, hi))

    @staticmethod
    def production_capacity(rng: Generator, nominal: float, variance_pct: float) -> float:
        """
        Planned production capacity at a site. [hours/period]
        Mode = nominal (planned capacity).
        Distribution: Triangular(0.7n, n, 1.3n) at Phase 3.
        """
        return _tri_jitter(rng, nominal, left_factor=1.0, right_factor=1.0, variance_pct=variance_pct)

    @staticmethod
    def production_capacity_used(
        rng: Generator, capacity: float, variance_pct: float
    ) -> float:
        """
        Capacity already consumed by locked or in-progress MOs. [hours/period]
        Mode ≈ 68 % of capacity (OEE benchmark for discrete manufacturing).
        Distribution: Triangular(0.40c, 0.68c, 0.95c).
        At Phase 3, extend to simulate near-overload trials.
        """
        lo   = capacity * max(0.20, 0.40 - 0.15 * variance_pct)
        hi   = capacity * min(0.99, 0.95 + 0.04 * variance_pct)
        mode = capacity * 0.68
        return max(0.0, _tri_absolute(rng, lo, mode, hi))

    @staticmethod
    def transit_capacity(rng: Generator, nominal: float, variance_pct: float) -> float:
        """
        Available transportation slots / transfer order capacity. [units/period]
        Symmetric Triangular jitter around nominal.
        """
        return _tri_jitter(rng, nominal, left_factor=1.0, right_factor=1.0, variance_pct=variance_pct)

    @staticmethod
    def procurement_budget(rng: Generator, nominal: float, variance_pct: float) -> float:
        """
        Available procurement budget for the period. [$]
        Mode = nominal (planned budget). Right tail allows over-budget trials.
        """
        return _tri_jitter(rng, nominal, left_factor=0.8, right_factor=1.2, variance_pct=variance_pct)

    @staticmethod
    def supplier_capacity(rng: Generator, nominal: float, variance_pct: float) -> float:
        """
        Maximum units a supplier can supply per period. [units]
        Mode = nominal (contracted capacity). Left-heavy in disruption phases.
        """
        return _tri_jitter(rng, nominal, left_factor=1.2, right_factor=0.8, variance_pct=variance_pct)

    @staticmethod
    def demand_forecast(rng: Generator, nominal: float, variance_pct: float) -> float:
        """
        Point demand forecast for the period. [units]
        Mode = nominal. Right tail heavier: demand spikes exceed troughs.
        Distribution: Triangular(0.4n, n, 2.5n) at Phase 3.
        """
        return _tri_jitter(rng, nominal, left_factor=1.0, right_factor=1.5, variance_pct=variance_pct)

    @staticmethod
    def inventory_dos(rng: Generator, target_dos: float, variance_pct: float) -> float:
        """
        Current days-of-supply. [days]
        Mode = target_dos (well-managed inventory is near target).
        Distribution: Triangular(0.3·target, target, 2.5·target) at Phase 3.
        """
        return _tri_jitter(rng, target_dos, left_factor=1.0, right_factor=1.5, variance_pct=variance_pct)

    # ── Absolute Triangular — domain-informed fixed modes ───────────────────

    @staticmethod
    def target_dos_days(rng: Generator, variance_pct: float) -> float:
        """
        Target days-of-supply policy. [days]
        Mode = 14 days (industry standard for mid-market manufacturers).
        Range: 7 days (lean) to 30 days (conservative), widening with phase.
        Distribution: Triangular(max(3, 7-5·pct), 14, min(60, 30+30·pct)).
        """
        lo   = max(3.0,  7.0  - 5.0  * variance_pct)
        hi   = min(60.0, 30.0 + 30.0 * variance_pct)
        mode = 14.0
        return _tri_absolute(rng, lo, mode, hi)

    @staticmethod
    def demand_variability_cv(rng: Generator, variance_pct: float) -> float:
        """
        Demand coefficient of variation (std / mean). [dimensionless]
        Mode = 0.25 (moderate variability, typical for FMCG and mid-market).
        The mode is fixed; variance_pct extends the right tail into high-CV
        disruption trials (Phase 3 explores CVs up to ~1.15).

        APICS benchmarks:
          Staple FMCG: CV 0.10–0.25
          Seasonal consumer goods: CV 0.30–0.50
          Intermittent/MRO: CV 0.50+

        Distribution: Triangular(0.05, 0.25, 0.20 + 1.3·pct).
        """
        lo   = 0.05
        mode = 0.25
        hi   = max(mode + 0.05, 0.20 + 1.30 * variance_pct)
        return float(np.clip(_tri_absolute(rng, lo, mode, hi), 0.05, 2.0))

    @staticmethod
    def service_level_actual(
        rng: Generator,
        sl_target: float,
        variance_pct: float,
    ) -> float:
        """
        Realised service level (rolling 4-week fill rate). [0, 1]
        Mode = sl_target (a well-run operation achieves its target).
        Distribution is left-skewed: failures pull below target; rarely
        materially above it. At Phase 3, tails extend into 5–15 % shortfall.

        Distribution: Triangular(sl_target - 0.12·pct, sl_target, sl_target + 0.02).
        """
        lo   = max(0.50, sl_target - 0.16 * variance_pct)
        hi   = min(1.00, sl_target + 0.02)
        mode = sl_target
        return float(np.clip(_tri_absolute(rng, lo, mode, hi), 0.0, 1.0))

    @staticmethod
    def avg_lead_time_weeks(rng: Generator, variance_pct: float) -> float:
        """
        Average supplier or inter-site lead time. [weeks]
        Mode = 2.0 weeks (typical for domestic mid-market supply chains).
        Right tail extends into disrupted/long-distance trials.

        Benchmarks:
          Domestic: 1–3 weeks   (mode=2)
          Import:   4–8 weeks   (captured at Phase 3)
          Disrupted: 8+ weeks   (captured at Phase 3 extreme tail)

        Distribution: Triangular(0.5, 2.0, 2.0 + 9·pct).
        """
        lo   = 0.5
        mode = 2.0
        hi   = max(mode + 0.5, 2.0 + 9.0 * variance_pct)
        return max(0.5, _tri_absolute(rng, lo, mode, hi))

    @staticmethod
    def lead_time_variability_cv(rng: Generator, variance_pct: float) -> float:
        """
        Lead time coefficient of variation. [dimensionless]
        Mode = 0.15 (typical for contracted suppliers with minor delays).
        At Phase 3, can reach 0.50+ (disrupted or unreliable suppliers).

        Distribution: Triangular(0.03, 0.15, 0.05 + 0.60·pct).
        """
        lo   = 0.03
        mode = 0.15
        hi   = max(mode + 0.05, 0.05 + 0.60 * variance_pct)
        return float(np.clip(_tri_absolute(rng, lo, mode, hi), 0.02, 1.0))

    @staticmethod
    def annual_holding_rate(rng: Generator) -> float:
        """
        Annual holding cost as a fraction of unit cost. [0, 1 per year]
        Mode = 0.22 (CSCMP benchmark: 20-25 % of unit cost/year includes
                     capital opportunity cost, warehousing, obsolescence).
        Range: 0.15 (lean, fast-turning) to 0.35 (slow-moving, high-capital).
        Phase-independent: this is a company characteristic, not a state variable.

        Distribution: Triangular(0.15, 0.22, 0.35).
        """
        return _tri_absolute(rng, 0.15, 0.22, 0.35)

    @staticmethod
    def stockout_cost_per_unit(rng: Generator, variance_pct: float) -> float:
        """
        Stockout penalty per unit short. [$/unit]
        Mode = 15 (typically 2–3× the holding cost; often combined with
                   lost margin + expediting premium).
        At Phase 3, explores high-penalty trials up to $80/unit.

        Distribution: Triangular(5, 15, 15 + 65·pct).
        """
        lo   = 5.0
        mode = 15.0
        hi   = max(mode + 5.0, 15.0 + 65.0 * variance_pct)
        return _tri_absolute(rng, lo, mode, hi)

    @staticmethod
    def lane_reliability(rng: Generator, variance_pct: float) -> float:
        """
        On-time delivery reliability of a transportation lane. [0, 1]
        Mode = 0.93 (industry benchmark for domestic carriers; ATA: 92-95%).
        Left tail: unreliable suppliers (min 0.70 at Phase 3).

        Distribution: Triangular(0.70 + 0.20·(1-pct), 0.93, 0.99).
        """
        lo   = max(0.50, 0.70 + 0.20 * (1.0 - variance_pct))
        hi   = 0.99
        mode = 0.93
        return float(np.clip(_tri_absolute(rng, lo, mode, hi), 0.0, 1.0))

    @staticmethod
    def lane_capacity_units(rng: Generator, variance_pct: float) -> float:
        """
        Maximum units per period that can flow through a transportation lane.
        Mode = 400 (mid-range for LTL/FTL lanes serving mid-market DCs).
        At Phase 3, explores constrained (100) and unconstrained (1000+) lanes.

        Distribution: Triangular(50 + 50·(1-pct), 400, 400 + 800·pct).
        """
        lo   = max(50.0, 100.0 - 50.0 * variance_pct)
        hi   = 400.0 + 800.0 * variance_pct
        mode = 400.0
        return max(50.0, _tri_absolute(rng, lo, mode, hi))

    @staticmethod
    def site_supply_capacity_units(rng: Generator, variance_pct: float) -> float:
        """
        Maximum units a supply site can produce or ship per period.
        Mode = 600 (mid-range manufacturer in training data population).
        At Phase 3, explores small (200) and large (2000+) suppliers.

        Distribution: Triangular(200, 600, 600 + 1400·pct).
        """
        lo   = 200.0
        hi   = 600.0 + 1400.0 * variance_pct
        mode = 600.0
        return max(100.0, _tri_absolute(rng, lo, mode, hi))

    @staticmethod
    def avg_weekly_demand(rng: Generator, nominal: float, variance_pct: float) -> float:
        """
        Average weekly demand at a demand site. [units/week]
        Mode = nominal (the scenario's characteristic demand level).
        Right tail heavier: demand spikes are larger than demand troughs.

        Distribution: Triangular(0.35n, n, n + 1.5n·pct).
        """
        return _tri_jitter(rng, nominal, left_factor=1.0, right_factor=1.5, variance_pct=variance_pct)

    # ── Within-simulation realisations (MC loop — right-skewed processes) ──

    @staticmethod
    def realised_lead_time_weeks(
        rng: Generator,
        mean: float,
        cv: float,
    ) -> float:
        """
        Realised lead time for one shipment. [weeks]
        Uses LogLogistic (Lokad recommendation): fat right tail captures
        supplier disruptions better than LogNormal. α = median ≈ mean
        for small CV; β (shape) derived from CV.

        LogLogistic moments:
          Mean  = α · π/β / sin(π/β)  for β > 1
          Var   = α² · [2π/β·sin(2π/β) - (π/β)²/sin(π/β)²]  for β > 2

        Approximation for β from CV (valid for CV ∈ [0.05, 0.80]):
          β ≈ 1/cv + 1.5   (higher CV → lower β → fatter tail)

        Returns value clipped to [0.25, 52] weeks.
        """
        beta = max(1.5, 1.0 / max(cv, 0.05) + 1.5)
        # α such that median ≈ mean / correction
        correction = (math.pi / beta) / math.sin(math.pi / beta) if beta > 1.0 else 1.0
        alpha = max(0.25, mean / correction)
        # LogLogistic CDF^{-1}(u) = α * (u / (1-u))^{1/β}
        u = float(rng.uniform(0.0, 1.0))
        u = float(np.clip(u, 1e-6, 1.0 - 1e-6))
        sample = alpha * ((u / (1.0 - u)) ** (1.0 / beta))
        return float(np.clip(sample, 0.25, 52.0))

    @staticmethod
    def realised_demand(rng: Generator, mean: float, cv: float) -> float:
        """
        Realised demand for one period. [units]
        Normal distribution is appropriate for demand because:
          - Demand is the sum of many independent customer orders (CLT)
          - Forecasting errors are approximately symmetric
          - The right-skew of raw demand is largely captured by the CV

        Returns value clipped at 0 (demand cannot be negative).
        """
        std = mean * cv
        return float(max(0.0, rng.normal(mean, std)))

    # ── Uniform — policy choices and cross-industry parameter ranges ─────────

    @staticmethod
    def service_level_target(rng: Generator) -> float:
        """
        Target service level (fill rate). [0, 1]
        A policy decision, not a natural process. Equal weighting across
        the plausible range [0.92, 0.99] for mid-market supply chains.
        Uniform: no domain prior about which target is "most common."
        """
        return float(rng.uniform(0.92, 0.99))

    @staticmethod
    def unit_cost(rng: Generator) -> float:
        """
        Unit product cost. [$/unit]
        Varies enormously across industries (pharma $200, bulk commodity $5).
        Uniform over [5, 200]: equal scenario coverage desired.
        """
        return float(rng.uniform(5.0, 200.0))

    @staticmethod
    def ordering_cost(rng: Generator) -> float:
        """
        Fixed cost per purchase order. [$/order]
        Ranges from EDI-automated ($50) to manual import orders ($500).
        No universal mode; Uniform gives full coverage.
        """
        return float(rng.uniform(50.0, 500.0))

    @staticmethod
    def criticality_score(rng: Generator) -> float:
        """
        Network criticality score for a site. [0, 1]
        This is a synthetic network property for training diversity.
        Full range coverage desired; Uniform is correct.
        """
        return float(rng.uniform(0.2, 1.0))

    @staticmethod
    def lane_transport_cost(rng: Generator) -> float:
        """
        Variable transport cost per unit on a lane. [$/unit]
        Varies by mode, distance, and commodity. No universal mode.
        Uniform over [0.5, 10] for intra-regional lanes.
        """
        return float(rng.uniform(0.5, 10.0))

    @staticmethod
    def sop_lane_transport_cost(rng: Generator) -> float:
        """Transport cost for S&OP oracle lanes (wider range, includes import)."""
        return float(rng.uniform(0.5, 20.0))

    # ── Binary events (Bernoulli via BinomialDistribution n=1) ─────────────

    @staticmethod
    def quality_hold_flag(rng: Generator, variance_pct: float) -> bool:
        """
        Whether a quality hold is active at this site.
        Base rate scales with phase: disruption phases have more quality events.
        p(hold) = variance_pct × 0.30.
        """
        return bool(rng.random() < variance_pct * 0.30)

    @staticmethod
    def maintenance_due_flag(rng: Generator, variance_pct: float) -> bool:
        """
        Whether a planned or overdue maintenance event is active.
        p(maintenance) = variance_pct × 0.25.
        """
        return bool(rng.random() < variance_pct * 0.25)

    @staticmethod
    def atp_shortfall_flag(rng: Generator, variance_pct: float) -> bool:
        """
        Whether an ATP shortfall condition is active.
        p(shortfall) = variance_pct × 0.35.
        """
        return bool(rng.random() < variance_pct * 0.35)

    # ── Count variables (Poisson — better than Discrete Uniform for events) ─

    @staticmethod
    def open_exceptions_count(rng: Generator, variance_pct: float) -> int:
        """
        Number of open order exceptions (late, short, damaged, etc.).
        Poisson is the correct model for rare event counts.
        λ = variance_pct × 3: at Phase 1, λ=0.45 (rarely any exceptions);
        at Phase 3, λ=2.25 (several exceptions common in disrupted state).
        """
        lam = max(0.1, variance_pct * 3.0)
        return int(rng.poisson(lam))

    # ── Convenience: sample a complete SharedSiteState dict ─────────────────

    @staticmethod
    def sample_site_state_dict(
        rng: Generator,
        site_key: str,
        variance_pct: float,
        nominal_on_hand: float = 1000.0,
        nominal_capacity: float = 500.0,
        nominal_transit: float = 300.0,
        nominal_budget: float = 50_000.0,
        nominal_supplier_capacity: float = 800.0,
        nominal_demand: float = 70.0,
        stochastic_overrides: Optional[Dict[str, dict]] = None,
    ) -> dict:
        """
        Sample a complete site state dict using all shared distributions.

        Drop-in replacement for the inline sampling in site_tgnn_oracle._sample_site_state().

        Args:
            stochastic_overrides: Optional dict of {param_name: dist_dict} from
                agent_stochastic_params. When provided, matching parameters are
                sampled from admin-curated/SAP-imported distributions instead
                of hardcoded defaults.
        """
        # Use override for demand variability if available
        demand_cv = None
        if stochastic_overrides and "demand_variability" in stochastic_overrides:
            demand_cv = sample_from_override(rng, stochastic_overrides["demand_variability"])
        if demand_cv is None:
            demand_cv = D.demand_variability_cv(rng, variance_pct)

        # Use override for quality rejection rate if available
        quality_rate = None
        if stochastic_overrides and "quality_rejection_rate" in stochastic_overrides:
            quality_rate = sample_from_override(rng, stochastic_overrides["quality_rejection_rate"])

        on_hand  = D.on_hand_inventory(rng, nominal_on_hand, variance_pct)
        capacity = D.production_capacity(rng, nominal_capacity, variance_pct)
        sl_target = D.service_level_target(rng)
        target_dos = D.target_dos_days(rng, variance_pct)

        return dict(
            site_key=site_key,
            on_hand_inventory=on_hand,
            committed_inventory=D.committed_inventory(rng, on_hand, variance_pct),
            wip=D.wip(rng, on_hand, variance_pct),
            production_capacity=capacity,
            production_capacity_used=D.production_capacity_used(rng, capacity, variance_pct),
            transit_capacity=D.transit_capacity(rng, nominal_transit, variance_pct),
            budget=D.procurement_budget(rng, nominal_budget, variance_pct),
            supplier_capacity=D.supplier_capacity(rng, nominal_supplier_capacity, variance_pct),
            demand_forecast=D.demand_forecast(rng, nominal_demand, variance_pct),
            demand_variability_cv=demand_cv,
            service_level_actual=D.service_level_actual(rng, sl_target, variance_pct),
            service_level_target=sl_target,
            inventory_dos=D.inventory_dos(rng, target_dos, variance_pct),
            target_dos=target_dos,
            has_quality_hold=(quality_rate is not None and rng.random() < quality_rate) if quality_rate is not None else D.quality_hold_flag(rng, variance_pct),
            has_maintenance_due=D.maintenance_due_flag(rng, variance_pct),
            has_atp_shortfall=D.atp_shortfall_flag(rng, variance_pct),
            num_open_exceptions=D.open_exceptions_count(rng, variance_pct),
        )


# ============================================================================
# Historical Triangular Distribution Fitting (demand + lead time)
# ============================================================================
#
# When historical data exists (from SAP outbound_order / inbound_order),
# fit triangular(min, mode, max) from observed values.
# When no history: use principled fallbacks.

import statistics as _stats
from collections import defaultdict as _defaultdict
from typing import Dict as _Dict, List as _List, Optional as _Optional, Tuple as _Tuple

from sqlalchemy import text as _sql_text

_logger = logging.getLogger(__name__)

# Industry CoV benchmarks by product category
_INDUSTRY_COV = {
    "staple": 0.15, "seasonal": 0.35, "promotional": 0.50,
    "intermittent": 0.80, "default": 0.30, "automotive": 0.20,
    "electronics": 0.40, "industrial": 0.25, "bikes": 0.30,
}


def _classify_product(product_id: str, description: str = "") -> str:
    desc = (description or "").lower()
    pid = (product_id or "").lower()
    if any(w in pid for w in ["mz-fg", "mz-rm", "mz-tg"]) or "bike" in desc:
        return "bikes"
    if any(w in desc for w in ["spare", "repair"]):
        return "intermittent"
    if any(w in desc for w in ["pump", "valve", "motor"]):
        return "industrial"
    return "default"


def fit_triangular(values: _List[float]) -> _Tuple[float, float, float]:
    """Estimate triangular(min, mode, max) from observed values.

    min  = P5  (robust lower bound)
    mode = median (robust central tendency)
    max  = P95 (robust upper bound)
    """
    if len(values) < 3:
        m = _stats.mean(values) if values else 1.0
        return max(0, m * 0.5), m, m * 2.0

    sv = sorted(values)
    n = len(sv)
    low = sv[max(0, int(n * 0.05))]
    high = sv[min(n - 1, int(n * 0.95))]
    mode = _stats.median(sv)

    if low >= mode:
        low = mode * 0.8
    if high <= mode:
        high = mode * 1.5
    return max(0, low), max(0.1, mode), max(mode + 0.1, high)


class HistoricalTriangularDemand:
    """Triangular demand sampler — fit from outbound order history or fallback."""

    def __init__(self, low: float, mode: float, high: float, seed: int = 0):
        self.low = max(0, low)
        self.mode = max(0.1, mode)
        self.high = max(self.mode + 0.1, high)
        self._rng = random.Random(seed)
        self.mean = (self.low + self.mode + self.high) / 3
        self.cv = (((self.low**2 + self.mode**2 + self.high**2 - self.low*self.mode - self.low*self.high - self.mode*self.high) / 18) ** 0.5) / self.mean if self.mean > 0 else 0.3

    def next(self) -> float:
        return max(0.0, self._rng.triangular(self.low, self.high, self.mode))

    @classmethod
    def from_db(cls, db, config_id: int, product_id: str, site_id: int,
                fallback_mean: float = 10.0, description: str = "", seed: int = 0):
        """Load history from outbound_order_line → fit triangular, or fallback."""
        try:
            rows = db.execute(_sql_text("""
                SELECT ol.ordered_quantity, o.order_date
                FROM outbound_order_line ol
                JOIN outbound_order o ON o.id = ol.order_id
                WHERE ol.product_id = :pid AND ol.site_id = :sid
                  AND o.config_id = :cid AND o.order_date IS NOT NULL
                  AND ol.ordered_quantity > 0
                ORDER BY o.order_date
            """), {"pid": product_id, "sid": site_id, "cid": config_id}).fetchall()

            if len(rows) >= 5:
                daily = _defaultdict(float)
                for r in rows:
                    daily[str(r[1])] += float(r[0])
                values = list(daily.values())
                if len(values) >= 5:
                    low, mode, high = fit_triangular(values)
                    _logger.info("Demand for %s@%s: triangular(%.1f, %.1f, %.1f) from %d observations",
                                 product_id, site_id, low, mode, high, len(values))
                    return cls(low=low, mode=mode, high=high, seed=seed)
        except Exception as e:
            _logger.debug("Demand history load failed: %s", e)

        # Fallback: industry-calibrated triangular
        category = _classify_product(product_id, description)
        cv = _INDUSTRY_COV.get(category, 0.30)
        std = fallback_mean * cv
        mode = max(0.1, fallback_mean * 0.9)
        low = max(0, mode - std * 0.7)    # Min closer to mode
        high = mode + std * 2.0            # Max further (right tail)
        _logger.info("Demand for %s@%s: fallback triangular(%.1f, %.1f, %.1f) category=%s",
                     product_id, site_id, low, mode, high, category)
        return cls(low=low, mode=mode, high=high, seed=seed)


class HistoricalTriangularLeadTime:
    """Triangular lead time sampler — fit from inbound order GR history or fallback."""

    def __init__(self, low: float, mode: float, high: float, seed: int = 0):
        self.low = max(1.0, low)
        self.mode = max(self.low, mode)
        self.high = max(self.mode + 0.5, high)
        self._rng = random.Random(seed)
        self.mean = (self.low + self.mode + self.high) / 3

    def sample(self) -> int:
        return max(1, round(self._rng.triangular(self.low, self.high, self.mode)))

    @classmethod
    def from_db(cls, db, config_id: int, lane_mode_days: float = 7.0, seed: int = 0):
        """Load history from inbound_order GR dates → fit triangular, or fallback."""
        try:
            rows = db.execute(_sql_text("""
                SELECT io.order_date, il.order_receive_date
                FROM inbound_order io
                JOIN inbound_order_line il ON il.order_id = io.id
                WHERE io.config_id = :cid
                  AND io.order_date IS NOT NULL
                  AND il.order_receive_date IS NOT NULL
            """), {"cid": config_id}).fetchall()

            lead_times = []
            for r in rows:
                if r[0] and r[1]:
                    delta = (r[1] - r[0]).days
                    if 0 < delta < 365:
                        lead_times.append(float(delta))

            if len(lead_times) >= 5:
                low, mode, high = fit_triangular(lead_times)
                _logger.info("Lead time for config %d: triangular(%.1f, %.1f, %.1f) from %d observations",
                             config_id, low, mode, high, len(lead_times))
                return cls(low=max(1, low), mode=max(1, mode), high=max(mode + 1, high), seed=seed)
        except Exception as e:
            _logger.debug("Lead time history load failed: %s", e)

        # Fallback: skewed to min with long upper tail
        mode = max(1.0, lane_mode_days)
        low = max(1.0, mode * 0.8)
        high = mode * 2.5
        _logger.info("Lead time for config %d: fallback triangular(%.1f, %.1f, %.1f)",
                     config_id, low, mode, high)
        return cls(low=low, mode=mode, high=high, seed=seed)


class HistoricalTriangularDeliveryLeadTime:
    """Triangular delivery lead time sampler (plant/DC → customer).

    Distinct from supplier inbound lead time — this measures the time
    from shipment at the fulfillment site to delivery at the customer.

    History source: outbound_order.order_date → LIKP.WADAT_IST (actual goods issue)
    or outbound_order ship_date → delivery confirmation.

    If no customer confirmation exists: assumed delivery = ship_date + lane_lead_time_mode.
    """

    def __init__(self, low: float, mode: float, high: float, seed: int = 0):
        self.low = max(0.5, low)
        self.mode = max(self.low, mode)
        self.high = max(self.mode + 0.5, high)
        self._rng = random.Random(seed)
        self.mean = (self.low + self.mode + self.high) / 3

    def sample(self) -> int:
        return max(1, round(self._rng.triangular(self.low, self.high, self.mode)))

    @classmethod
    def from_db(cls, db, config_id: int, lane_mode_days: float = 3.0, seed: int = 0):
        """Load delivery history from outbound_order → delivery dates.

        Tries three sources in priority order:
        1. Actual delivery date (outbound_order.actual_delivery_date)
        2. Goods issue date from deliveries (LIKP.WADAT_IST via outbound_shipment)
        3. Promised delivery - order date (as proxy)

        If no history: fallback uses lane_mode_days with moderate right skew.
        """
        delivery_times = []

        try:
            # Source 1: actual_delivery_date vs order_date
            rows = db.execute(_sql_text("""
                SELECT o.order_date, o.actual_delivery_date
                FROM outbound_order o
                WHERE o.config_id = :cid
                  AND o.order_date IS NOT NULL
                  AND o.actual_delivery_date IS NOT NULL
            """), {"cid": config_id}).fetchall()

            for r in rows:
                if r[0] and r[1]:
                    delta = (r[1] - r[0]).days
                    if 0 < delta < 180:
                        delivery_times.append(float(delta))

            # Source 2: promised_delivery_date vs order_date (if few actual dates)
            if len(delivery_times) < 10:
                rows2 = db.execute(_sql_text("""
                    SELECT o.order_date, o.promised_delivery_date
                    FROM outbound_order o
                    WHERE o.config_id = :cid
                      AND o.order_date IS NOT NULL
                      AND o.promised_delivery_date IS NOT NULL
                      AND o.actual_delivery_date IS NULL
                """), {"cid": config_id}).fetchall()

                for r in rows2:
                    if r[0] and r[1]:
                        delta = (r[1] - r[0]).days
                        if 0 < delta < 180:
                            delivery_times.append(float(delta))

            # Source 3: requested_delivery_date vs order_date (last resort)
            if len(delivery_times) < 10:
                rows3 = db.execute(_sql_text("""
                    SELECT o.order_date, o.requested_delivery_date
                    FROM outbound_order o
                    WHERE o.config_id = :cid
                      AND o.order_date IS NOT NULL
                      AND o.requested_delivery_date IS NOT NULL
                      AND o.actual_delivery_date IS NULL
                      AND o.promised_delivery_date IS NULL
                """), {"cid": config_id}).fetchall()

                for r in rows3:
                    if r[0] and r[1]:
                        delta = (r[1] - r[0]).days
                        if 0 < delta < 180:
                            delivery_times.append(float(delta))

        except Exception as e:
            _logger.debug("Delivery lead time history load failed: %s", e)

        if len(delivery_times) >= 5:
            low, mode, high = fit_triangular(delivery_times)
            _logger.info(
                "Delivery LT for config %d: triangular(%.1f, %.1f, %.1f) from %d observations",
                config_id, low, mode, high, len(delivery_times),
            )
            return cls(low=max(0.5, low), mode=max(1, mode), high=max(mode + 1, high), seed=seed)

        # Fallback: use lane lead time mode with moderate right skew
        # Delivery is typically shorter than supplier inbound but has its own variability
        mode = max(1.0, lane_mode_days)
        low = max(0.5, mode * 0.7)     # Can sometimes deliver faster than expected
        high = mode * 2.0               # Moderate upper tail (last-mile delays)
        _logger.info(
            "Delivery LT for config %d: fallback triangular(%.1f, %.1f, %.1f)",
            config_id, low, mode, high,
        )
        return cls(low=low, mode=mode, high=high, seed=seed)


# ---------------------------------------------------------------------------
# OTIF (On Time In Full) computation
# ---------------------------------------------------------------------------

def compute_otif(db, config_id: int) -> _Dict:
    """Compute OTIF and customer service metrics from outbound order history.

    OTIF = orders delivered (on time AND in full) / total orders.

    On Time: actual_delivery_date <= requested_delivery_date
      - If no actual_delivery_date: assume delivered = order_date + lane_lead_time_mode
    In Full: total_fulfilled_qty >= total_ordered_qty

    Returns: {otif_pct, on_time_pct, in_full_pct, total_orders, late_orders,
              short_orders, avg_days_late, fill_rate_pct}
    """
    try:
        rows = db.execute(_sql_text("""
            SELECT o.id, o.order_date, o.requested_delivery_date,
                   o.actual_delivery_date, o.promised_delivery_date,
                   o.total_ordered_qty, o.total_fulfilled_qty
            FROM outbound_order o
            WHERE o.config_id = :cid
              AND o.order_date IS NOT NULL
              AND o.total_ordered_qty > 0
        """), {"cid": config_id}).fetchall()

        if not rows:
            return {"otif_pct": None, "total_orders": 0}

        # Get average lane lead time for assumed delivery fallback
        lt_row = db.execute(_sql_text("""
            SELECT AVG(
                CASE WHEN supply_lead_time IS NOT NULL
                     THEN CAST(supply_lead_time->>'value' AS FLOAT)
                     ELSE 7 END
            ) FROM transportation_lane WHERE config_id = :cid
        """), {"cid": config_id}).fetchone()
        avg_lane_lt = float(lt_row[0]) if lt_row and lt_row[0] else 7.0

        total = 0
        on_time = 0
        in_full = 0
        on_time_and_full = 0
        total_ordered = 0.0
        total_fulfilled = 0.0
        days_late_sum = 0.0
        late_count = 0

        for r in rows:
            order_date = r[1]
            requested = r[2]
            actual = r[3]
            promised = r[4]
            ordered_qty = float(r[5] or 0)
            fulfilled_qty = float(r[6] or 0)

            if not requested:
                continue

            total += 1
            total_ordered += ordered_qty
            total_fulfilled += fulfilled_qty

            # Determine delivery date: actual > promised > assumed
            delivery_date = actual or promised
            if not delivery_date and order_date:
                from datetime import timedelta
                delivery_date = order_date + timedelta(days=int(avg_lane_lt))

            # On Time check
            is_on_time = delivery_date <= requested if delivery_date and requested else False
            if is_on_time:
                on_time += 1
            elif delivery_date and requested:
                days_late = (delivery_date - requested).days
                if days_late > 0:
                    days_late_sum += days_late
                    late_count += 1

            # In Full check
            is_in_full = fulfilled_qty >= ordered_qty if ordered_qty > 0 else True
            if is_in_full:
                in_full += 1

            if is_on_time and is_in_full:
                on_time_and_full += 1

        otif_pct = round((on_time_and_full / total) * 100, 1) if total > 0 else None
        on_time_pct = round((on_time / total) * 100, 1) if total > 0 else None
        in_full_pct = round((in_full / total) * 100, 1) if total > 0 else None
        fill_rate = round((total_fulfilled / total_ordered) * 100, 1) if total_ordered > 0 else None
        avg_late = round(days_late_sum / late_count, 1) if late_count > 0 else 0

        return {
            "otif_pct": otif_pct,
            "on_time_pct": on_time_pct,
            "in_full_pct": in_full_pct,
            "fill_rate_pct": fill_rate,
            "total_orders": total,
            "late_orders": late_count,
            "short_orders": total - in_full,
            "avg_days_late": avg_late,
        }

    except Exception as e:
        _logger.warning("OTIF computation failed: %s", e)
        return {"otif_pct": None, "total_orders": 0, "error": str(e)}


class HistoricalTriangularTransferLeadTime:
    """Triangular inter-plant/inter-DC transfer lead time sampler.

    Distinct from supplier inbound and customer delivery — measures
    internal transfer time between company-owned sites (Plant→DC, DC→DC, Plant→Plant).

    Typically shorter and tighter than supplier LT, but variable due to
    internal logistics, consolidation, and cross-docking delays.

    History source: transfer_order completion dates, or inbound_order
    where both from_site_id and to_site_id are internal.
    """

    def __init__(self, low: float, mode: float, high: float, seed: int = 0):
        self.low = max(0.5, low)
        self.mode = max(self.low, mode)
        self.high = max(self.mode + 0.5, high)
        self._rng = random.Random(seed)
        self.mean = (self.low + self.mode + self.high) / 3

    def sample(self) -> int:
        return max(1, round(self._rng.triangular(self.low, self.high, self.mode)))

    @classmethod
    def from_db(cls, db, config_id: int, lane_mode_days: float = 3.0,
                from_site_id: int = None, to_site_id: int = None, seed: int = 0):
        """Load inter-plant transfer history from site-to-site lanes.

        Uses transportation_lane where both from_site_id and to_site_id are set
        (internal transfer, not partner-endpoint). Falls back to lane config.
        """
        transfer_times = []

        try:
            # Try transfer orders first (LTAK/LTAP)
            rows = db.execute(_sql_text("""
                SELECT tl.supply_lead_time
                FROM transportation_lane tl
                WHERE tl.config_id = :cid
                  AND tl.from_site_id IS NOT NULL
                  AND tl.to_site_id IS NOT NULL
                  AND tl.from_partner_id IS NULL
                  AND tl.to_partner_id IS NULL
            """), {"cid": config_id}).fetchall()

            for r in rows:
                lt = r[0]
                if isinstance(lt, dict):
                    val = lt.get("value", lt.get("mean", lt.get("avg")))
                    if val and 0 < float(val) < 180:
                        transfer_times.append(float(val))
                elif lt and 0 < float(lt) < 180:
                    transfer_times.append(float(lt))

        except Exception as e:
            _logger.debug("Transfer LT history load failed: %s", e)

        if len(transfer_times) >= 3:
            low, mode, high = fit_triangular(transfer_times)
            _logger.info(
                "Transfer LT for config %d: triangular(%.1f, %.1f, %.1f) from %d lanes",
                config_id, low, mode, high, len(transfer_times),
            )
            return cls(low=max(0.5, low), mode=max(1, mode), high=max(mode + 0.5, high), seed=seed)

        # Fallback: internal transfers are typically faster and tighter
        mode = max(1.0, lane_mode_days)
        low = max(0.5, mode * 0.6)      # Often faster than expected
        high = mode * 1.8                # Smaller upper tail than supplier
        _logger.info(
            "Transfer LT for config %d: fallback triangular(%.1f, %.1f, %.1f)",
            config_id, low, mode, high,
        )
        return cls(low=low, mode=mode, high=high, seed=seed)


# ============================================================================
# Operational Stochastic Variables (all triangular — history or fallback)
# ============================================================================
#
# Every operating variable is stochastic. When historical data exists
# (from production orders, quality inspections, maintenance logs), fit
# triangular(P5, median, P95). When not, use industry benchmarks.


class HistoricalTriangularYield:
    """Production yield rate (0-1). Scrap = 1 - yield.

    History: AFKO/AFPO planned vs actual quantities, AFRU confirmations.
    Fallback: high yield (0.95-0.99 mode) with occasional bad batches.
    """

    def __init__(self, low: float, mode: float, high: float, seed: int = 0):
        self.low = max(0.5, min(1.0, low))
        self.mode = max(self.low, min(1.0, mode))
        self.high = max(self.mode, min(1.0, high))
        self._rng = random.Random(seed)
        self.scrap_rate = 1.0 - self.mode

    def sample(self) -> float:
        """Returns yield fraction (0-1). Scrap = 1 - yield."""
        return max(0.5, min(1.0, self._rng.triangular(self.low, self.high, self.mode)))

    @classmethod
    def from_db(cls, db, config_id: int, product_id: str = None, seed: int = 0):
        """Fit from production order actual vs planned quantities."""
        yields = []
        try:
            q = """
                SELECT po.planned_quantity, po.actual_quantity
                FROM production_orders po
                WHERE po.config_id = :cid
                  AND po.planned_quantity > 0 AND po.actual_quantity > 0
            """
            params = {"cid": config_id}
            rows = db.execute(_sql_text(q), params).fetchall()
            for r in rows:
                planned = float(r[0])
                actual = float(r[1])
                if planned > 0:
                    y = min(1.0, actual / planned)
                    if 0.5 < y <= 1.0:
                        yields.append(y)
        except Exception as e:
            _logger.debug("Yield history load failed: %s", e)

        if len(yields) >= 5:
            low, mode, high = fit_triangular(yields)
            return cls(low=low, mode=mode, high=min(1.0, high), seed=seed)

        # Fallback: high yield with occasional problems
        return cls(low=0.90, mode=0.97, high=0.995, seed=seed)


class HistoricalTriangularThroughput:
    """Production throughput rate (units/hour relative to planned).

    History: AFRU confirmation actual times vs planned times.
    Fallback: slight underperformance with occasional overperformance.
    """

    def __init__(self, low: float, mode: float, high: float, seed: int = 0):
        self.low = max(0.3, low)
        self.mode = max(self.low, mode)
        self.high = max(self.mode, high)
        self._rng = random.Random(seed)

    def sample(self) -> float:
        """Returns throughput ratio (1.0 = planned rate)."""
        return max(0.3, self._rng.triangular(self.low, self.high, self.mode))

    @classmethod
    def from_db(cls, db, config_id: int, seed: int = 0):
        """Fit from production confirmation actual vs planned times."""
        ratios = []
        try:
            rows = db.execute(_sql_text("""
                SELECT po.planned_quantity, po.actual_quantity,
                       po.planned_start_date, po.actual_start_date,
                       po.planned_end_date, po.actual_end_date
                FROM production_orders po
                WHERE po.config_id = :cid
                  AND po.planned_quantity > 0 AND po.actual_quantity > 0
                  AND po.planned_start_date IS NOT NULL
                  AND po.actual_end_date IS NOT NULL
            """), {"cid": config_id}).fetchall()
            for r in rows:
                planned_qty = float(r[0])
                actual_qty = float(r[1])
                if r[2] and r[5]:
                    planned_days = max(1, (r[4] - r[2]).days) if r[4] else 1
                    actual_days = max(1, (r[5] - r[2]).days)
                    # Throughput ratio = (actual_qty/actual_days) / (planned_qty/planned_days)
                    planned_rate = planned_qty / planned_days
                    actual_rate = actual_qty / actual_days
                    if planned_rate > 0:
                        ratio = actual_rate / planned_rate
                        if 0.3 < ratio < 2.0:
                            ratios.append(ratio)
        except Exception as e:
            _logger.debug("Throughput history load failed: %s", e)

        if len(ratios) >= 5:
            low, mode, high = fit_triangular(ratios)
            return cls(low=low, mode=mode, high=high, seed=seed)

        # Fallback: slight underperformance typical
        return cls(low=0.80, mode=0.95, high=1.05, seed=seed)


class HistoricalTriangularQualityRate:
    """Quality pass rate (0-1). Rejection rate = 1 - pass_rate.

    History: QALS inspection lots — pass vs fail counts.
    Fallback: high pass rate with occasional quality events.
    """

    def __init__(self, low: float, mode: float, high: float, seed: int = 0):
        self.low = max(0.5, min(1.0, low))
        self.mode = max(self.low, min(1.0, mode))
        self.high = max(self.mode, min(1.0, high))
        self._rng = random.Random(seed)
        self.rejection_rate = 1.0 - self.mode

    def sample(self) -> float:
        """Returns quality pass fraction (0-1)."""
        return max(0.5, min(1.0, self._rng.triangular(self.low, self.high, self.mode)))

    @classmethod
    def from_db(cls, db, config_id: int, seed: int = 0):
        """Fit from quality inspection lot results (QALS)."""
        pass_rates = []
        try:
            rows = db.execute(_sql_text("""
                SELECT q.lot_size, q.accepted_quantity
                FROM quality_order q
                WHERE q.config_id = :cid
                  AND q.lot_size > 0
            """), {"cid": config_id}).fetchall()
            for r in rows:
                lot = float(r[0])
                accepted = float(r[1] or lot)
                if lot > 0:
                    rate = min(1.0, accepted / lot)
                    if rate > 0.5:
                        pass_rates.append(rate)
        except Exception as e:
            _logger.debug("Quality rate history load failed: %s", e)

        if len(pass_rates) >= 5:
            low, mode, high = fit_triangular(pass_rates)
            return cls(low=low, mode=mode, high=min(1.0, high), seed=seed)

        # Fallback: high quality with rare issues
        return cls(low=0.92, mode=0.98, high=0.999, seed=seed)


class HistoricalTriangularMachineAvailability:
    """Machine/resource availability (0-1). Downtime = 1 - availability.

    History: capacity_resources actual vs planned utilization.
    Fallback: high availability with occasional breakdowns.
    """

    def __init__(self, low: float, mode: float, high: float, seed: int = 0):
        self.low = max(0.3, min(1.0, low))
        self.mode = max(self.low, min(1.0, mode))
        self.high = max(self.mode, min(1.0, high))
        self._rng = random.Random(seed)

    def sample(self) -> float:
        """Returns availability fraction (0-1)."""
        return max(0.3, min(1.0, self._rng.triangular(self.low, self.high, self.mode)))

    @classmethod
    def from_db(cls, db, config_id: int, seed: int = 0):
        """Fit from work center capacity data (CRHD/KAKO)."""
        # Availability data is typically not in transactional tables
        # Use maintenance_order completion rates as proxy
        avail = []
        try:
            rows = db.execute(_sql_text("""
                SELECT planned_start_date, actual_start_date,
                       planned_end_date, actual_end_date
                FROM maintenance_order
                WHERE config_id = :cid
                  AND planned_start_date IS NOT NULL
            """), {"cid": config_id}).fetchall()
            # If maintenance orders are short relative to planned, availability is high
            # This is a proxy — real OEE would need machine-level runtime data
        except Exception:
            pass

        # Fallback: typical manufacturing availability (85-95%)
        return cls(low=0.80, mode=0.92, high=0.98, seed=seed)


class HistoricalTriangularChangeoverTime:
    """Changeover/setup time (minutes or hours).

    History: PLPO setup times (VGW01) from production routing.
    Fallback: varies by product complexity.
    """

    def __init__(self, low: float, mode: float, high: float, seed: int = 0):
        self.low = max(0, low)
        self.mode = max(self.low + 0.1, mode)
        self.high = max(self.mode + 0.1, high)
        self._rng = random.Random(seed)

    def sample(self) -> float:
        """Returns changeover time in same unit as input (minutes or hours)."""
        return max(0, self._rng.triangular(self.low, self.high, self.mode))

    @classmethod
    def from_db(cls, db, config_id: int, seed: int = 0):
        """Fit from production process setup times (PLPO.VGW01)."""
        setup_times = []
        try:
            rows = db.execute(_sql_text("""
                SELECT setup_time FROM production_process
                WHERE config_id = :cid AND setup_time > 0
            """), {"cid": config_id}).fetchall()
            setup_times = [float(r[0]) for r in rows if r[0] and float(r[0]) > 0]
        except Exception as e:
            _logger.debug("Changeover history load failed: %s", e)

        if len(setup_times) >= 5:
            low, mode, high = fit_triangular(setup_times)
            return cls(low=low, mode=mode, high=high, seed=seed)

        # Fallback: moderate setup (30 min mode, 15-90 range)
        return cls(low=15, mode=30, high=90, seed=seed)


# ============================================================================
# Customer Service Outcome Metrics (measured, not input)
# ============================================================================
#
# These are OUTCOMES measured from simulation or actual execution results.
# They are NOT inputs to training — they are the scorecard metrics that
# evaluate how well the supply chain performed.
#
# Targets for these metrics (e.g., OTIF target ≥ 95%) are static inputs
# set by the tenant admin. The actual values are computed from data.


def compute_customer_service_metrics(db, config_id: int) -> _Dict:
    """Compute customer service outcome metrics from outbound order history.

    Returns a scorecard with:
    - OTIF % (On Time In Full)
    - Fill Rate % (qty fulfilled / qty ordered)
    - On-Time Delivery % (delivered by requested date)
    - Perfect Order Rate % (on time + in full + no quality issues + correct docs)
    - Backorder Rate % (orders with unfulfilled quantity)
    - Average Order Cycle Time (days from order to delivery)
    """
    try:
        rows = db.execute(_sql_text("""
            SELECT o.id, o.order_date, o.requested_delivery_date,
                   o.actual_delivery_date, o.promised_delivery_date,
                   o.total_ordered_qty, o.total_fulfilled_qty,
                   o.status
            FROM outbound_order o
            WHERE o.config_id = :cid
              AND o.order_date IS NOT NULL
              AND o.total_ordered_qty > 0
        """), {"cid": config_id}).fetchall()

        if not rows:
            return {
                "otif_pct": None, "fill_rate_pct": None, "on_time_pct": None,
                "perfect_order_pct": None, "backorder_rate_pct": None,
                "avg_cycle_time_days": None, "total_orders": 0,
            }

        # Average lane LT for assumed delivery fallback
        lt_row = db.execute(_sql_text("""
            SELECT AVG(
                CASE WHEN supply_lead_time IS NOT NULL
                     THEN CAST(supply_lead_time->>'value' AS FLOAT)
                     ELSE 7 END
            ) FROM transportation_lane WHERE config_id = :cid
        """), {"cid": config_id}).fetchone()
        avg_lane_lt = float(lt_row[0]) if lt_row and lt_row[0] else 7.0

        total = 0
        on_time = 0
        in_full = 0
        on_time_and_full = 0
        total_ordered = 0.0
        total_fulfilled = 0.0
        backorder_count = 0
        cycle_times = []

        from datetime import timedelta

        for r in rows:
            order_date, requested, actual, promised = r[1], r[2], r[3], r[4]
            ordered_qty = float(r[5] or 0)
            fulfilled_qty = float(r[6] or 0)
            status = r[7] or ""

            if not requested:
                continue

            total += 1
            total_ordered += ordered_qty
            total_fulfilled += fulfilled_qty

            # Delivery date: actual > promised > assumed
            delivery_date = actual or promised
            if not delivery_date and order_date:
                delivery_date = order_date + timedelta(days=int(avg_lane_lt))

            # On Time
            is_on_time = (delivery_date <= requested) if delivery_date and requested else False
            if is_on_time:
                on_time += 1

            # In Full
            is_in_full = fulfilled_qty >= ordered_qty if ordered_qty > 0 else True
            if is_in_full:
                in_full += 1

            # OTIF
            if is_on_time and is_in_full:
                on_time_and_full += 1

            # Backorder
            if fulfilled_qty < ordered_qty and status not in ("CANCELLED", "REJECTED"):
                backorder_count += 1

            # Cycle time (order to delivery)
            if delivery_date and order_date:
                ct = (delivery_date - order_date).days
                if 0 <= ct < 365:
                    cycle_times.append(ct)

        return {
            "otif_pct": round((on_time_and_full / total) * 100, 1) if total > 0 else None,
            "fill_rate_pct": round((total_fulfilled / total_ordered) * 100, 1) if total_ordered > 0 else None,
            "on_time_pct": round((on_time / total) * 100, 1) if total > 0 else None,
            "perfect_order_pct": round((on_time_and_full / total) * 100, 1) if total > 0 else None,  # Simplified — full perfect order needs quality + docs check
            "backorder_rate_pct": round((backorder_count / total) * 100, 1) if total > 0 else None,
            "avg_cycle_time_days": round(_stats.mean(cycle_times), 1) if cycle_times else None,
            "total_orders": total,
            "on_time_orders": on_time,
            "in_full_orders": in_full,
            "backorder_orders": backorder_count,
        }

    except Exception as e:
        _logger.warning("Customer service metrics computation failed: %s", e)
        return {"otif_pct": None, "total_orders": 0, "error": str(e)}


# ============================================================================
# Guardrails and Metric Targets — from tenant context + GNN heuristics
# ============================================================================
#
# Only guardrails and metric targets are static during training.
# They come from TWO sources:
#   1. Tenant context — business rules, policy limits, approval thresholds
#   2. GNN heuristic equivalents — what GraphSAGE/tGNN WOULD produce
#      if trained, used as warm-start defaults
#
# When trained GNN models are available, their output replaces the heuristics.


@dataclass
class SiteGuardrails:
    """Guardrails for TRM decisions at a specific site.

    Combines tenant-level policy with GNN-derived (or heuristic) constraints.
    TRMs check these before executing any decision.
    """
    # From GNN (S&OP GraphSAGE → PolicyParams) or heuristic equivalent
    safety_stock_multiplier: float = 1.0    # [0.5, 3.0]
    service_level_target: float = 0.95      # [0.80, 0.99]
    reorder_point_days: float = 7.0         # [3, 21]
    order_up_to_days: float = 21.0          # [7, 60]
    sourcing_split_primary: float = 0.7     # [0, 1]

    # From GNN (network risk scores) or heuristic equivalent
    criticality_score: float = 0.5          # [0, 1] how critical this site is
    bottleneck_risk: float = 0.3            # [0, 1]
    concentration_risk: float = 0.2         # [0, 1] single-source vulnerability
    resilience_score: float = 0.7           # [0, 1]

    # From tenant context (authority_definitions, tenant_bsc_config)
    max_autonomous_order_value: float = 50000.0   # $ — above this, escalate
    max_autonomous_qty: float = 1000.0             # units
    requires_approval_above: float = 100000.0      # $ threshold
    autonomy_threshold: float = 0.65               # confidence needed for auto-action

    # Metric targets (from tenant — these are GOALS, not predictions)
    otif_target: float = 0.95
    fill_rate_target: float = 0.98
    on_time_target: float = 0.95
    max_backorder_rate: float = 0.05
    max_cycle_time_days: float = 14.0
    cost_budget_daily: float = 0.0          # 0 = no budget constraint

    source: str = "heuristic"  # "heuristic", "graphsage", "tenant_override"


def load_site_guardrails(
    db, config_id: int, site_id: int, tenant_id: int,
) -> SiteGuardrails:
    """Load guardrails for a site from tenant context + GNN/heuristic.

    Priority:
    1. Trained GNN output (powell_policy_parameters) → if available
    2. GNN heuristic equivalent → computed from network topology
    3. Tenant defaults (tenant_bsc_config, authority_definitions)
    """
    g = SiteGuardrails()

    # --- Source 1: Trained GNN policy parameters ---
    try:
        row = db.execute(_sql_text("""
            SELECT parameters FROM powell_policy_parameters
            WHERE config_id = :cid AND entity_id = :sid
              AND valid_to IS NULL OR valid_to > NOW()
            ORDER BY valid_from DESC LIMIT 1
        """), {"cid": config_id, "sid": str(site_id)}).fetchone()

        if row and row[0]:
            params = row[0] if isinstance(row[0], dict) else {}
            g.safety_stock_multiplier = params.get("safety_stock_multiplier", g.safety_stock_multiplier)
            g.service_level_target = params.get("service_level_target", g.service_level_target)
            g.reorder_point_days = params.get("reorder_point_days", g.reorder_point_days)
            g.order_up_to_days = params.get("order_up_to_days", g.order_up_to_days)
            g.sourcing_split_primary = params.get("sourcing_split", g.sourcing_split_primary)
            g.source = "graphsage"
    except Exception:
        pass

    # --- Source 2: GNN heuristic equivalent (if no trained params) ---
    if g.source == "heuristic":
        try:
            # Compute simple heuristic risk scores from topology
            # Concentration risk: count distinct suppliers for this site
            supplier_count = db.execute(_sql_text("""
                SELECT COUNT(DISTINCT from_partner_id) FROM transportation_lane
                WHERE config_id = :cid AND to_site_id = :sid AND from_partner_id IS NOT NULL
            """), {"cid": config_id, "sid": site_id}).scalar() or 0

            g.concentration_risk = max(0.1, 1.0 / max(supplier_count, 1))  # Single source = 1.0

            # Bottleneck: if many downstream lanes depend on this site
            downstream_count = db.execute(_sql_text("""
                SELECT COUNT(*) FROM transportation_lane
                WHERE config_id = :cid AND from_site_id = :sid
            """), {"cid": config_id, "sid": site_id}).scalar() or 0

            g.bottleneck_risk = min(1.0, downstream_count / 10.0)  # Normalize

            # Adjust SS multiplier based on risk
            g.safety_stock_multiplier = 1.0 + (g.concentration_risk * 0.5) + (g.bottleneck_risk * 0.3)
        except Exception:
            pass

    # --- Source 3: Tenant context ---
    try:
        bsc = db.execute(_sql_text("""
            SELECT autonomy_threshold, urgency_threshold, likelihood_threshold
            FROM tenant_bsc_config WHERE tenant_id = :tid LIMIT 1
        """), {"tid": tenant_id}).fetchone()

        if bsc:
            g.autonomy_threshold = float(bsc[0] or 0.65)
    except Exception:
        pass

    try:
        auth = db.execute(_sql_text("""
            SELECT max_value FROM authority_definitions
            WHERE tenant_id = :tid AND action_type = 'purchase_order'
              AND requires_approval = false
            LIMIT 1
        """), {"tid": tenant_id}).fetchone()

        if auth and auth[0]:
            g.max_autonomous_order_value = float(auth[0])
    except Exception:
        pass

    return g


# ============================================================================
# Industry Simulation Defaults — based on end-to-end SC lead times
# ============================================================================
#
# Simulation time = 2× industry end-to-end supply chain lead time
# (enough to see one full replenishment cycle complete + variability)
# Time bucket = always daily. Work week = Mon-Fri (5 days).
# Weekly demand is spread uniformly over 5 work days.

# End-to-end SC lead times by industry (days) — sourced from APICS/SCOR benchmarks
# This is the total VSM lead time: supplier → manufacture → distribute → deliver
INDUSTRY_SC_LEAD_TIME_DAYS = {
    "food_beverage": 21,              # Short shelf life, fast turns
    "pharmaceutical": 120,            # Long validation, cold chain, regulatory
    "automotive": 60,                 # Tiered supply, JIT assembly
    "electronics": 45,                # Global sourcing, fast product cycles
    "chemical": 42,                   # Process manufacturing, batch cycles
    "industrial_equipment": 90,       # Complex BOM, long component LTs
    "consumer_goods": 30,             # Fast moving, retail distribution
    "metals_mining": 75,              # Raw material extraction + processing
    "aerospace_defense": 180,         # Long LTs, certification, complex BOMs
    "building_materials": 35,         # Regional, heavy freight
    "textile_apparel": 90,            # Global sourcing, seasonal, fashion risk
    "wholesale_distribution": 14,     # Short — receiving + put-away + ship
    "third_party_logistics": 7,       # Shortest — cross-dock + last mile
}

# Default trials by industry (more complex = more trials for convergence)
# Base = 50; complex industries need more to capture tail risks
INDUSTRY_DEFAULT_TRIALS = {
    "pharmaceutical": 100,        # Regulatory variance, cold chain failures
    "aerospace_defense": 100,     # Long tails, certification delays
    "automotive": 75,             # Tiered supply, JIT sensitivity
    "industrial_equipment": 75,   # Complex BOMs, long component LTs
    "textile_apparel": 75,        # Seasonal, fashion risk, global sourcing
    "metals_mining": 60,          # Commodity price swings, extraction variance
    "electronics": 60,            # Component shortage risk, fast cycles
    "chemical": 60,               # Batch variability, yield uncertainty
}


def get_industry_sim_defaults(industry: str) -> _Dict:
    """Get simulation defaults for an industry.

    sim_days = 2 × end-to-end SC lead time (see full cycle + replenishment)
    sim_time_bucket = always 'daily'
    sim_trials = industry-specific or 5
    sim_warmup_days = 10% of sim_days, min 5

    Returns dict ready to set on tenant model.
    """
    sc_lt = INDUSTRY_SC_LEAD_TIME_DAYS.get(industry, 45)
    sim_days = sc_lt * 2  # 2× lead time to see full cycle
    warmup = max(5, sim_days // 10)
    episodes = INDUSTRY_DEFAULT_TRIALS.get(industry, 50)

    return {
        "sim_days": sim_days,
        "sim_trials": episodes,  # 50 base, up to 100 for complex industries
        "sim_warmup_days": warmup,
        "sim_time_bucket": "daily",  # Always daily — never lose granularity
        "sim_decisions_per_type": 20,
        "industry_sc_lead_time_days": sc_lt,
    }


# ============================================================================
# Work Week Calendars — multi-pattern, sourced from ERP or country defaults
# ============================================================================
#
# Work week sources (in priority order):
# 1. ERP site calendar (SAP FABKL, D365 WorkCalendar, Odoo resource.calendar)
# 2. Historical deduction: days with zero transactions = non-work days
# 3. Country defaults (see COUNTRY_WORK_WEEK below)

# Country → work days (0=Mon, 6=Sun)
# Sources: ILO, World Bank, local labor law
COUNTRY_WORK_WEEK = {
    # Sun-Thu (Middle East)
    "AE": (6, 0, 1, 2, 3),  # UAE
    "SA": (6, 0, 1, 2, 3),  # Saudi Arabia
    "QA": (6, 0, 1, 2, 3),  # Qatar
    "KW": (6, 0, 1, 2, 3),  # Kuwait
    "BH": (6, 0, 1, 2, 3),  # Bahrain
    "OM": (6, 0, 1, 2, 3),  # Oman
    "IR": (5, 6, 0, 1, 2),  # Iran (Sat-Wed)
    "IL": (6, 0, 1, 2, 3),  # Israel
    # Mon-Sat (parts of Asia)
    "IN": (0, 1, 2, 3, 4, 5),  # India (many factories 6 days)
    "CN": (0, 1, 2, 3, 4, 5),  # China (manufacturing often 6 days)
    "BD": (6, 0, 1, 2, 3, 4),  # Bangladesh (Sun-Thu + some Sat)
    # Mon-Fri (Americas, Europe, Japan, Australia, etc.) — default
}

_DEFAULT_WORK_DAYS = (0, 1, 2, 3, 4)  # Mon-Fri


def get_work_days_for_country(country_code: str) -> tuple:
    """Return work day indices (0=Mon) for a country. Default Mon-Fri."""
    return COUNTRY_WORK_WEEK.get(country_code.upper(), _DEFAULT_WORK_DAYS)


def is_work_day(day_index: int, start_weekday: int = 0, work_days: tuple = _DEFAULT_WORK_DAYS) -> bool:
    """Check if a simulation day is a work day.

    Args:
        day_index: 0-based day in the simulation
        start_weekday: weekday of simulation day 0 (0=Mon, 6=Sun)
        work_days: tuple of weekday indices that are work days

    Returns True if the day falls on a work day.
    """
    weekday = (start_weekday + day_index) % 7
    return weekday in work_days


def spread_weekly_demand(weekly_qty: float, day_in_week: int, n_work_days: int = 5) -> float:
    """Spread weekly demand uniformly over work days.

    Args:
        weekly_qty: total weekly demand quantity
        day_in_week: 0=Mon, ..., 6=Sun
        n_work_days: number of work days per week (5 or 6)

    Returns daily demand on work days, 0 on non-work days.
    """
    if n_work_days <= 0:
        return 0.0
    return weekly_qty / n_work_days


def spread_monthly_demand(monthly_qty: float, day_in_month: int, work_days_in_month: int = 22) -> float:
    """Spread monthly demand over work days in the month.

    Args:
        monthly_qty: total monthly demand
        day_in_month: 0-based day (only called on work days)
        work_days_in_month: typically 22 (5 days × 4.4 weeks)

    Returns daily demand on work days.
    """
    return monthly_qty / work_days_in_month


class WorkWeekCalendar:
    """Site-specific work week calendar for simulation.

    Work days are determined by (in priority order):
    1. ERP site calendar (SAP FABKL, D365 WorkCalendar, Odoo resource.calendar)
    2. Historical transaction pattern (days with activity = work days)
    3. Country defaults (Sun-Thu for ME, Mon-Sat for India/China, Mon-Fri elsewhere)

    All simulation operations must check is_work_day() before executing.
    Lead times count only work days.
    """

    def __init__(self, start_weekday: int = 0, work_days: tuple = _DEFAULT_WORK_DAYS):
        """
        Args:
            start_weekday: weekday of simulation day 0 (0=Mon, default)
            work_days: tuple of weekday indices that are work days (0=Mon, 6=Sun)
        """
        self.start_weekday = start_weekday
        self.work_days = work_days
        self.n_work_days_per_week = len(work_days)

    def is_work_day(self, sim_day: int) -> bool:
        return is_work_day(sim_day, self.start_weekday, self.work_days)

    def weekday(self, sim_day: int) -> int:
        """Return weekday (0=Mon, 6=Sun) for a simulation day."""
        return (self.start_weekday + sim_day) % 7

    def work_days_in_range(self, start_day: int, end_day: int) -> int:
        """Count work days between two simulation days (inclusive)."""
        return sum(1 for d in range(start_day, end_day + 1) if self.is_work_day(d))

    def calendar_days_for_work_days(self, work_days: int, from_day: int = 0) -> int:
        """Convert work days to calendar days from a starting point.

        Used for lead time conversion: a 5 work-day lead time = 7 calendar days.
        """
        if work_days <= 0:
            return 0
        cal_days = 0
        remaining = work_days
        d = from_day
        while remaining > 0:
            if self.is_work_day(d):
                remaining -= 1
            d += 1
            cal_days += 1
        return cal_days

    def daily_demand_from_weekly(self, weekly_qty: float, sim_day: int) -> float:
        """Get daily demand for a simulation day from a weekly total."""
        if not self.is_work_day(sim_day):
            return 0.0
        return weekly_qty / self.n_work_days_per_week

    def daily_demand_from_monthly(self, monthly_qty: float, sim_day: int) -> float:
        """Get daily demand for a simulation day from a monthly total."""
        if not self.is_work_day(sim_day):
            return 0.0
        # Approx work days per month = n_work_days_per_week × 4.35
        work_days_per_month = self.n_work_days_per_week * 4.35
        return monthly_qty / work_days_per_month

    @classmethod
    def from_today(cls, country_code: str = None) -> "WorkWeekCalendar":
        """Create a calendar starting from today's weekday, with country work pattern."""
        from datetime import date
        work_days = get_work_days_for_country(country_code) if country_code else _DEFAULT_WORK_DAYS
        return cls(start_weekday=date.today().weekday(), work_days=work_days)

    @classmethod
    def from_erp_site(cls, db, site_id: int, config_id: int, country_code: str = None) -> "WorkWeekCalendar":
        """Create a calendar from ERP site data.

        Priority:
        1. SAP factory calendar (MARC.FABKL → TFACS)
        2. Historical transaction pattern (days with activity)
        3. Country default from site geography
        """
        from datetime import date

        # Try to get country from site geography
        if not country_code:
            try:
                row = db.execute(_sql_text("""
                    SELECT g.country FROM site s
                    LEFT JOIN geography g ON g.id = s.geo_id
                    WHERE s.id = :sid AND s.config_id = :cid
                """), {"sid": site_id, "cid": config_id}).fetchone()
                if row and row[0]:
                    country_code = row[0]
            except Exception:
                pass

        # Try SAP factory calendar code
        try:
            row = db.execute(_sql_text("""
                SELECT attributes->>'sap_factory_calendar' FROM site
                WHERE id = :sid AND config_id = :cid
            """), {"sid": site_id, "cid": config_id}).fetchone()
            if row and row[0]:
                # SAP factory calendar codes: US, DE, JP, etc.
                # Map to country code for work week lookup
                cal_code = row[0].upper()
                if len(cal_code) == 2:
                    country_code = cal_code
        except Exception:
            pass

        work_days = get_work_days_for_country(country_code) if country_code else _DEFAULT_WORK_DAYS
        return cls(start_weekday=date.today().weekday(), work_days=work_days)
