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
        At Phase 3, extend to simulate near-overload scenarios.
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
        Mode = nominal (planned budget). Right tail allows over-budget scenarios.
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
        disruption scenarios (Phase 3 explores CVs up to ~1.15).

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
        Right tail extends into disrupted/long-distance scenarios.

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
        At Phase 3, explores high-penalty scenarios up to $80/unit.

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
    ) -> dict:
        """
        Sample a complete site state dict using all shared distributions.
        Drop-in replacement for the inline sampling in site_tgnn_oracle._sample_site_state().
        """
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
            demand_variability_cv=D.demand_variability_cv(rng, variance_pct),
            service_level_actual=D.service_level_actual(rng, sl_target, variance_pct),
            service_level_target=sl_target,
            inventory_dos=D.inventory_dos(rng, target_dos, variance_pct),
            target_dos=target_dos,
            has_quality_hold=D.quality_hold_flag(rng, variance_pct),
            has_maintenance_due=D.maintenance_due_flag(rng, variance_pct),
            has_atp_shortfall=D.atp_shortfall_flag(rng, variance_pct),
            num_open_exceptions=D.open_exceptions_count(rng, variance_pct),
        )
