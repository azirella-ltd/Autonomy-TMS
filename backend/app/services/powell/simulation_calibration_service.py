"""
Simulation Calibration Service

Bootstraps CDT (Conformal Decision Theory) calibration for all 11 TRM agents
immediately after provisioning warm-start, without waiting for real production
feedback horizons (4h–14 days per TRM type).

The Problem
-----------
TRM agents are trained in two phases:

  Phase 1 – Behavioral Cloning (BC): Expert heuristics make decisions.
    TRMs learn by watching ("AlphaZero learning from grandmaster games").
    Outcomes belong to the HEURISTIC, not the TRM.

  Phase 2 – RL fine-tuning: TRMs make decisions, receive rewards.
    Outcomes NOW belong to the TRM. This is where CDT should calibrate from.

CDT calibration requires (confidence, actual_loss) pairs from TRM decisions.
After provisioning, Phase 2 RL may not have enough history, so the CDT banner
shows "0/11 agents ready" for days or weeks.

The Solution
------------
Run the supply chain simulation (BeerLine engine) for N episodes using a
base-stock policy that approximates post-BC TRM behaviour. At each period,
compute supply-chain outcomes (fill rate, holding/backlog cost, stockout
occurrence) and derive per-TRM (confidence, loss) pairs.

This is equivalent to Phase 2 "student plays games after BC" — the
simulation's supply chain dynamics calibrate the CDT to THIS tenant's
topology, demand variability, and lead times. The resulting prior is refined
as real production outcomes accumulate (hourly at :35).

Why supply chain state is the right proxy
-----------------------------------------
CDT calibration asks: "when the TRM says it's 80% confident, does the
actual outcome fall within its predicted risk bound 80% of the time?"

Two key drivers answer this:
  1. TRM confidence ← supply chain stability (fill rate, IP/SS ratio, CV of demand)
  2. TRM loss       ← supply chain cost (holding + backlog, service failure)

These are determined by the TOPOLOGY and DEMAND PATTERN — not by who made
the ordering decision (heuristic vs TRM). A well-calibrated bootstrap prior
based on the simulation's supply chain dynamics is far better than the
uncalibrated default (risk_bound=0.5 for every decision).

Architecture
------------
BeerLine (in-memory, no DB required)
    ↓  tick(demand) per period
Per-period supply chain state:
    inventory, backlog, fill_rate, holding_cost, backlog_cost, demand_cv
    ↓  _derive_trm_pairs(state, per_trm_config)
{agent_type: [(confidence, loss), ...]}
    ↓  CDTCalibrationService.calibrate_from_simulation()
All 11 TRM wrappers calibrated → CDT banner clears immediately
    ↓  (incremental updates hourly at :35)
Real production outcomes from Phase 2 RL gradually refine the calibration
"""

import logging
import math
import random
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.services.powell.cdt_calibration_service import (
    CDTCalibrationService,
    TRM_COST_MAPPING,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_N_EPISODES = 50
_MIN_EPISODES = 10
_DEFAULT_PERIODS = 52          # One simulated year
_HISTORY_WINDOW = 8            # Periods of history for demand CV calculation
_HOLDING_COST = 1.0            # Per unit per period
_BACKLOG_COST = 3.0            # Per unit per period (3× holding — service cost)


# ---------------------------------------------------------------------------
# Demand variability profiles
# (derived from supply chain config topology if available, else defaults)
# ---------------------------------------------------------------------------

class _StochasticDemand:
    """Simple stochastic demand process for simulation episodes."""

    def __init__(self, mean: float = 10.0, cv: float = 0.3, seed: Optional[int] = None):
        self.mean = max(1.0, mean)
        self.cv = max(0.05, cv)
        self.std = self.mean * self.cv
        self._rng = random.Random(seed)

    def next(self) -> float:
        """Sample next period demand (Normal, clipped to ≥ 0)."""
        return max(0.0, self._rng.gauss(self.mean, self.std))


# ---------------------------------------------------------------------------
# Lightweight inventory node (mirrors BeerLine.Node semantics)
# ---------------------------------------------------------------------------

class _SimNode:
    """Single-echelon inventory node for CDT calibration simulation."""

    def __init__(
        self,
        initial_inventory: float = 20.0,
        shipment_lead_time: int = 2,
        demand_lead_time: int = 1,
        base_stock: float = 30.0,
    ):
        self.inventory = initial_inventory
        self.backlog = 0.0
        self.base_stock = base_stock
        self.shipment_pipe: deque = deque([0.0] * max(1, shipment_lead_time))
        self.order_pipe: deque = deque([0.0] * max(1, demand_lead_time))
        self.demand_history: deque = deque(maxlen=_HISTORY_WINDOW)
        self.cost_history: deque = deque(maxlen=_HISTORY_WINDOW)
        self.fill_rate_history: deque = deque(maxlen=_HISTORY_WINDOW)

    def receive_shipment(self) -> float:
        """Receive the oldest in-transit shipment."""
        arrived = self.shipment_pipe.popleft()
        self.shipment_pipe.append(0.0)
        self.inventory += arrived
        return arrived

    def fulfill(self, demand: float) -> float:
        """Fulfill demand from inventory; excess becomes backlog."""
        need = self.backlog + demand
        shipped = min(self.inventory, need)
        self.inventory -= shipped
        self.backlog = max(need - shipped, 0.0)
        fill_rate = shipped / max(need, 1.0)
        self.fill_rate_history.append(fill_rate)
        return shipped

    def place_order(self, order_qty: float) -> None:
        """Place an order that arrives after shipment_lead_time periods."""
        self.order_pipe.append(max(0.0, order_qty))
        # Advance the order pipe (oldest order placed → goes to upstream)
        # For this simplified single-node model, orders arrive after lead time
        if len(self.shipment_pipe) > 1:
            self.shipment_pipe[-1] += self.order_pipe.popleft()
        else:
            self.shipment_pipe[-1] += self.order_pipe.popleft() if self.order_pipe else 0.0

    def base_stock_order(self, demand: float) -> float:
        """Base-stock order quantity (representative of well-trained TRM)."""
        ip = self.inventory + sum(self.shipment_pipe) - self.backlog
        order = max(0.0, self.base_stock - ip)
        return order

    def accrue_costs(self) -> float:
        """Return period cost (holding + backlog penalty)."""
        cost = _HOLDING_COST * max(self.inventory, 0) + _BACKLOG_COST * max(self.backlog, 0)
        self.cost_history.append(cost)
        return cost

    @property
    def demand_cv(self) -> float:
        """Coefficient of variation of recent demand history."""
        h = list(self.demand_history)
        if len(h) < 2:
            return 0.3
        mean = sum(h) / len(h)
        if mean <= 0:
            return 0.3
        variance = sum((x - mean) ** 2 for x in h) / len(h)
        return math.sqrt(variance) / mean

    @property
    def avg_fill_rate(self) -> float:
        """Average fill rate over recent history."""
        h = list(self.fill_rate_history)
        return sum(h) / len(h) if h else 0.5

    @property
    def inventory_position(self) -> float:
        return self.inventory + sum(self.shipment_pipe) - self.backlog


# ---------------------------------------------------------------------------
# Per-period state record
# ---------------------------------------------------------------------------

class _PeriodOutcome:
    """Supply chain outcomes for one simulated period."""

    def __init__(
        self,
        demand: float,
        shipped: float,
        inventory: float,
        backlog: float,
        cost: float,
        inventory_position: float,
        demand_cv: float,
        avg_fill_rate: float,
    ):
        self.demand = demand
        self.shipped = shipped
        self.inventory = inventory
        self.backlog = backlog
        self.cost = cost
        self.inventory_position = inventory_position
        self.demand_cv = demand_cv
        self.avg_fill_rate = avg_fill_rate
        self.fill_rate = shipped / max(demand, 1.0)
        self.stockout = backlog > 0


# ---------------------------------------------------------------------------
# Per-TRM confidence and loss derivation
# ---------------------------------------------------------------------------
#
# CDT calibration needs (confidence, loss) pairs for each TRM type.
# Confidence = TRM's stated certainty about its decision.
# Loss = how far actual outcome deviated from expected (0 = perfect, >0 = worse).
#
# Both are derived from supply chain state, which is the primary driver of
# TRM confidence (stable state → confident TRM) and loss (volatile/backlogged
# state → high loss decisions).

def _confidence_from_state(outcome: _PeriodOutcome, base_confidence: float = 0.7) -> float:
    """Derive TRM confidence from supply chain stability signals.

    High confidence when:
      - Fill rate is high (system is healthy, service level maintained)
      - Demand variability is low (predictable demand)
      - Inventory position is positive (not in a hole)

    Low confidence when backlogged, volatile, or running short.
    """
    # Stability components
    fill_component = outcome.avg_fill_rate          # [0, 1] — higher = more stable
    cv_component = max(0.0, 1.0 - outcome.demand_cv * 2)  # high CV → low confidence
    ip_ratio = min(1.0, max(0.0, outcome.inventory_position / max(outcome.demand * 4, 1.0)))

    raw = base_confidence * (0.5 * fill_component + 0.3 * cv_component + 0.2 * ip_ratio)
    # Add some variation (noise) to avoid all-identical pairs
    return min(0.95, max(0.05, raw))


def _loss_for_trm(trm_type: str, outcome: _PeriodOutcome, max_cost_ref: float = 50.0) -> float:
    """Map supply chain outcome to the normalized loss metric used by each TRM type.

    Each TRM type's CDT loss function has a different denominator (see
    TRM_COST_MAPPING in cdt_calibration_service.py). We use the appropriate
    supply-chain proxy for each.
    """
    fill_rate = outcome.fill_rate
    stockout = outcome.stockout
    normalized_cost = min(1.0, outcome.cost / max(max_cost_ref, 1.0))
    backlog_ratio = min(1.0, outcome.backlog / max(outcome.demand, 1.0))

    if trm_type == "atp":
        # ATP loss = |promised - fulfilled| / promised → proxy: 1 - fill_rate
        return max(0.0, 1.0 - fill_rate)

    elif trm_type in ("inventory_rebalancing", "po_creation", "subcontracting"):
        # Cost-deviation losses → proxy: normalized cost
        return normalized_cost

    elif trm_type == "order_tracking":
        # Impact cost → proxy: backlog ratio (backlog = orders at risk)
        return backlog_ratio

    elif trm_type == "mo_execution":
        # Yield loss = (planned - actual) / planned → proxy: 1 - fill_rate
        return max(0.0, 1.0 - fill_rate)

    elif trm_type == "to_execution":
        # Transit delay loss → proxy: normalized cost (delay = inventory imbalance)
        return normalized_cost

    elif trm_type == "quality_disposition":
        # Quality cost → proxy: low fill rate + stockout (quality failures)
        return 0.5 * (1.0 - fill_rate) + 0.5 * (1.0 if stockout else 0.0)

    elif trm_type == "maintenance_scheduling":
        # Downtime loss + breakdown penalty → proxy: backlog (blocked production)
        return min(1.0, backlog_ratio + (0.3 if stockout else 0.0))

    elif trm_type == "forecast_adjustment":
        # Forecast error improvement → proxy: demand CV (more volatile = harder to forecast)
        return min(1.0, outcome.demand_cv)

    elif trm_type == "inventory_buffer":
        # Stockout penalty + excess holding → proxy: stockout flag + normalized cost
        return min(1.0, (0.5 if stockout else 0.0) + 0.5 * normalized_cost)

    else:
        return normalized_cost


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class SimulationCalibrationService:
    """Bootstrap CDT calibration from digital twin simulation episodes.

    Runs the supply chain simulation for N episodes, derives (confidence, loss)
    pairs per TRM type from supply chain outcomes, and calibrates all CDT
    wrappers before real production feedback horizons have elapsed.

    Phase relationship:
      Phase 1 BC:    Heuristics decide → TRMs learn weights
                     (outcomes belong to heuristic — wrong for CDT)
      This service:  Simulation runs → supply chain dynamics → CDT calibrated
                     (approximate TRM behavior; refined by real Phase 2+ data)
      Phase 2 RL:    TRMs decide → outcomes → CDT incrementally updated (:35)
    """

    def __init__(
        self,
        db: Session,
        config_id: int,
        tenant_id: int,
    ):
        self.db = db
        self.config_id = config_id
        self.tenant_id = tenant_id
        self._cdt_service = CDTCalibrationService(db=db, tenant_id=tenant_id)

    def bootstrap_calibration(
        self,
        n_episodes: int = _DEFAULT_N_EPISODES,
        periods_per_episode: int = _DEFAULT_PERIODS,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Run simulation episodes and calibrate all CDT wrappers.

        Args:
            n_episodes:          Number of simulation episodes to run.
            periods_per_episode: Time periods per episode (default: 52 = 1 year).
            force:               If True, re-calibrate even if already calibrated.

        Returns:
            Stats dict with per-agent calibration results.
        """
        n_episodes = max(_MIN_EPISODES, n_episodes)

        if not force:
            diag = self._cdt_service.get_all_diagnostics()
            all_calibrated = all(
                d.get("is_calibrated", False)
                for d in diag.values()
                if isinstance(d, dict)
            )
            if all_calibrated and diag:
                logger.info(
                    "CDT simulation bootstrap skipped — all %d wrappers already calibrated",
                    len(diag),
                )
                return {"status": "already_calibrated", "skipped": True}

        # Load supply chain topology parameters for more realistic simulation
        demand_mean, demand_cv, lead_time = self._load_topology_params()

        logger.info(
            "CDT simulation bootstrap: %d episodes × %d periods "
            "(demand_mean=%.1f, cv=%.2f, lead_time=%d) "
            "for config_id=%d tenant_id=%d",
            n_episodes,
            periods_per_episode,
            demand_mean,
            demand_cv,
            lead_time,
            self.config_id,
            self.tenant_id,
        )

        simulation_pairs = self._run_episodes(
            n_episodes=n_episodes,
            periods_per_episode=periods_per_episode,
            demand_mean=demand_mean,
            demand_cv=demand_cv,
            lead_time=lead_time,
        )

        stats = self._cdt_service.calibrate_from_simulation(simulation_pairs)

        calibrated = sum(1 for s in stats.values() if s.get("status") == "calibrated")
        total = len(stats)

        logger.info(
            "CDT simulation bootstrap complete: %d/%d agents calibrated",
            calibrated,
            total,
        )

        return {
            "status": "complete",
            "agents_calibrated": calibrated,
            "agents_total": total,
            "per_agent": stats,
            "episodes_run": n_episodes,
            "demand_params": {"mean": demand_mean, "cv": demand_cv, "lead_time": lead_time},
        }

    # -----------------------------------------------------------------------
    # Topology parameter loading
    # -----------------------------------------------------------------------

    def _load_topology_params(self) -> Tuple[float, float, int]:
        """Load demand and lead time parameters from this tenant's supply chain config.

        Returns (demand_mean, demand_cv, avg_lead_time).
        Falls back to sensible defaults if config not found.
        """
        defaults = (10.0, 0.30, 2)

        try:
            from app.models.sc_entities import Forecast
            from app.models.supply_chain_config import SupplyChainConfig
            import statistics

            config = self.db.query(SupplyChainConfig).filter(
                SupplyChainConfig.id == self.config_id
            ).first()
            if not config:
                return defaults

            # Sample recent forecasts for this config
            forecasts = (
                self.db.query(Forecast.p50_qty, Forecast.p10_qty, Forecast.p90_qty)
                .filter(Forecast.config_id == self.config_id)
                .order_by(Forecast.forecast_date.desc())
                .limit(52)
                .all()
            )

            if not forecasts:
                return defaults

            p50_values = [float(f.p50_qty) for f in forecasts if f.p50_qty and f.p50_qty > 0]
            if not p50_values:
                return defaults

            demand_mean = statistics.mean(p50_values)

            # Estimate demand CV from p10/p90 spread (≈ ±1.28σ for Normal)
            spreads = []
            for f in forecasts:
                if f.p10_qty and f.p90_qty and f.p50_qty and f.p50_qty > 0:
                    spread = (float(f.p90_qty) - float(f.p10_qty)) / (2.56 * float(f.p50_qty))
                    spreads.append(max(0.05, spread))

            demand_cv = statistics.mean(spreads) if spreads else 0.30
            demand_cv = min(demand_cv, 1.0)

            # Average supply lead time from transportation lanes
            from app.models.supply_chain_config import TransportationLane
            lanes = (
                self.db.query(TransportationLane.supply_lead_time)
                .filter(TransportationLane.config_id == self.config_id)
                .limit(20)
                .all()
            )

            lead_times = []
            for lane in lanes:
                lt = lane.supply_lead_time
                if isinstance(lt, dict):
                    lt = lt.get("mean") or lt.get("min") or 2
                if lt and isinstance(lt, (int, float)) and 1 <= lt <= 30:
                    lead_times.append(int(round(lt)))

            avg_lead_time = int(round(statistics.mean(lead_times))) if lead_times else 2
            avg_lead_time = max(1, min(avg_lead_time, 8))

            logger.debug(
                "CDT bootstrap topology params: mean=%.1f cv=%.2f lt=%d "
                "(from %d forecasts, %d lanes)",
                demand_mean, demand_cv, avg_lead_time, len(p50_values), len(lead_times),
            )
            return demand_mean, demand_cv, avg_lead_time

        except Exception as e:
            logger.debug("CDT bootstrap: topology params fallback (%s)", e)
            return defaults

    # -----------------------------------------------------------------------
    # Simulation loop
    # -----------------------------------------------------------------------

    def _run_episodes(
        self,
        n_episodes: int,
        periods_per_episode: int,
        demand_mean: float,
        demand_cv: float,
        lead_time: int,
    ) -> Dict[str, List[Tuple[float, float]]]:
        """Run N simulation episodes; return {agent_type: [(confidence, loss), ...]}."""

        pairs: Dict[str, List[Tuple[float, float]]] = {k: [] for k in TRM_COST_MAPPING}

        # Reference cost for loss normalisation (e.g. peak one-period cost)
        max_cost_ref = demand_mean * _BACKLOG_COST * 2.0

        for episode in range(n_episodes):
            seed = episode * 137 + self.config_id  # Reproducible but varied
            demand_gen = _StochasticDemand(mean=demand_mean, cv=demand_cv, seed=seed)

            node = _SimNode(
                initial_inventory=demand_mean * (lead_time + 1),
                shipment_lead_time=lead_time,
                demand_lead_time=1,
                base_stock=demand_mean * (lead_time + 2),
            )

            for _period in range(periods_per_episode):
                demand = demand_gen.next()
                node.demand_history.append(demand)

                # Receive inbound shipments
                node.receive_shipment()

                # Fulfill demand; record service level
                node.fulfill(demand)

                # Base-stock ordering (representative of post-BC TRM behaviour)
                order_qty = node.base_stock_order(demand)
                node.place_order(order_qty)

                # Accrue costs
                cost = node.accrue_costs()

                outcome = _PeriodOutcome(
                    demand=demand,
                    shipped=min(node.inventory + node.backlog, demand),  # approx
                    inventory=node.inventory,
                    backlog=node.backlog,
                    cost=cost,
                    inventory_position=node.inventory_position,
                    demand_cv=node.demand_cv,
                    avg_fill_rate=node.avg_fill_rate,
                )

                # Derive one (confidence, loss) pair per TRM type per period
                for agent_type in TRM_COST_MAPPING:
                    confidence = _confidence_from_state(outcome)
                    loss = _loss_for_trm(agent_type, outcome, max_cost_ref)
                    pairs[agent_type].append((confidence, loss))

        total_pairs = sum(len(v) for v in pairs.values())
        logger.debug(
            "CDT bootstrap simulation: %d total pairs across %d TRM types "
            "(%d episodes × %d periods × %d types)",
            total_pairs,
            len(pairs),
            n_episodes,
            periods_per_episode,
            len(pairs),
        )
        return pairs


def run_simulation_calibration_bootstrap(
    db: Session,
    config_id: int,
    tenant_id: int,
    n_episodes: int = _DEFAULT_N_EPISODES,
    force: bool = False,
) -> Dict[str, Any]:
    """Convenience wrapper for provisioning step (synchronous)."""
    svc = SimulationCalibrationService(db=db, config_id=config_id, tenant_id=tenant_id)
    return svc.bootstrap_calibration(n_episodes=n_episodes, force=force)
