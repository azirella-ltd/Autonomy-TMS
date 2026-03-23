"""
Per-TRM Curriculum Training Data Generators

Each TRM has its own curriculum with 3 progressive phases:
- Phase 1: Simple scenarios (easy decisions, clear signals)
- Phase 2: Moderate complexity (trade-offs, variability)
- Phase 3: Full complexity (disruptions, uncertainty, edge cases)

All curricula generate numpy arrays matching the TRM model's exact
state/action contract, sourced from realistic SC config parameters.

Expert actions are computed by the ERP-aware heuristic library
(``app.services.powell.heuristic_library``) rather than inline if/then
rules.  The curriculum still generates random state vectors (controlling
difficulty progression per phase), but the *label* for each sample comes
from ``compute_decision(trm_type, state_dataclass, erp_params)``.

Usage:
    curriculum = CURRICULUM_REGISTRY["atp_executor"](sc_config_data)
    data = curriculum.generate(phase=1, num_samples=5000)
    # data["state_vectors"].shape == (5000, 12) for ATP
"""

import numpy as np
import random
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from app.models.trm.atp_trm_model import ATP_STATE_DIM, ATP_NUM_ACTIONS
from app.models.trm.rebalancing_trm_model import REB_STATE_DIM
from app.models.trm.po_creation_trm_model import PO_STATE_DIM, PO_NUM_ACTIONS
from app.models.trm.order_tracking_trm_model import (
    OT_STATE_DIM, OT_NUM_EXCEPTION_TYPES, OT_NUM_SEVERITIES, OT_NUM_ACTIONS,
)

from app.services.powell.heuristic_library.dispatch import compute_decision
from app.services.powell.heuristic_library.base import (
    ERPPlanningParams,
    ATPState,
    RebalancingState,
    ReplenishmentState,
    OrderTrackingState,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers: build ERPPlanningParams from SCConfigData
# ---------------------------------------------------------------------------

def _build_erp_params(sc_config: "SCConfigData") -> ERPPlanningParams:
    """Construct ERPPlanningParams from the lightweight SC config data.

    Uses values from the SC config where available, otherwise sensible
    defaults matching SAP MARC parameters.
    """
    cfg = sc_config.extra_config if hasattr(sc_config, "extra_config") and sc_config.extra_config else {}
    return ERPPlanningParams(
        planning_method=cfg.get("planning_method", "REORDER_POINT"),
        lot_sizing_rule=cfg.get("lot_sizing_rule", "LOT_FOR_LOT"),
        reorder_point=cfg.get("reorder_point", sc_config.avg_demand * sc_config.avg_lead_time * 0.5),
        safety_stock=cfg.get("safety_stock", sc_config.avg_demand * 1.5),
        order_up_to=cfg.get("order_up_to", sc_config.avg_demand * sc_config.avg_lead_time * 1.5),
        fixed_lot_size=cfg.get("fixed_lot_size", 0.0),
        min_order_quantity=cfg.get("min_order_quantity", 0.0),
        max_order_quantity=cfg.get("max_order_quantity", 0.0),
        order_multiple=cfg.get("order_multiple", 0.0),
        lead_time_days=int(cfg.get("lead_time_days", sc_config.avg_lead_time)),
        review_period_days=int(cfg.get("review_period_days", 7)),
        frozen_horizon_days=int(cfg.get("frozen_horizon_days", 0)),
        max_inventory=cfg.get("max_inventory", 0.0),
        procurement_type=cfg.get("procurement_type", "buy"),
        erp_source=cfg.get("erp_source", "sap"),
        erp_params=cfg.get("erp_params", {}),
    )


# ---------------------------------------------------------------------------
# Action mapping: heuristic library action -> curriculum action index
# ---------------------------------------------------------------------------
# The heuristic library and the curriculum may use different action index
# conventions.  These maps translate heuristic library actions to the
# curriculum action space.
#
# ATP heuristic: 0=reject/backorder, 1=confirm, 2=partial
# ATP curriculum: 0=fulfill, 1=partial, 2=defer, 3=reserve, 4=reject
_ATP_ACTION_MAP = {0: 4, 1: 0, 2: 1}

# Rebalancing heuristic: 0=hold, 1=transfer  (same as curriculum)
_REB_ACTION_MAP = {0: 0, 1: 1}

# PO heuristic: 0=no order, 1=order (same as curriculum 0=order, 1=defer)
# Heuristic returns action=0 for "no order" and action=1 for "order".
# Curriculum: 0=order, 1=defer, 2=expedite, 3=cancel
_PO_ACTION_MAP = {0: 1, 1: 0}  # heuristic 0(no-order)->curriculum 1(defer), heuristic 1(order)->curriculum 0(order)

# Order tracking heuristic: action = severity (0=none, 1=monitor, 2=expedite, 3=escalate)
# Curriculum: action_discrete = exception type, cont[0] = severity, cont[1] = recommended action
# These are different enough that we handle order_tracking specially.


# ---------------------------------------------------------------------------
# Reward from heuristic decision
# ---------------------------------------------------------------------------

def _reward_from_decision(action: int, quantity: float, confidence: float,
                          phase: int) -> float:
    """Derive a reward from the heuristic decision quality.

    Higher phases get slightly lower base rewards to reflect increased
    difficulty.
    """
    phase_discount = {1: 1.0, 2: 0.9, 3: 0.8}.get(phase, 0.8)
    # Heuristic confidence is always 1.0 for deterministic heuristics,
    # so we base the reward on whether an action was taken.
    if action == 0 and quantity <= 0:
        return 0.5 * phase_discount  # No-action baseline
    return confidence * phase_discount


@dataclass
class SCConfigData:
    """Lightweight SC config info needed for curriculum generation (no DB dependency)."""
    num_sites: int = 4
    num_products: int = 5
    num_lanes: int = 6
    avg_lead_time: float = 7.0
    avg_demand: float = 50.0
    num_suppliers: int = 2
    num_priority_levels: int = 5
    site_types: Optional[List[str]] = None
    extra_config: Optional[Dict[str, Any]] = None


@dataclass
class CurriculumData:
    """Output of a curriculum generation run."""
    state_vectors: np.ndarray       # [N, state_dim]
    action_discrete: np.ndarray     # [N] int action indices
    action_continuous: np.ndarray   # [N, cont_dim] continuous actions
    rewards: np.ndarray             # [N] float
    next_state_vectors: np.ndarray  # [N, state_dim]
    is_expert: np.ndarray           # [N] bool
    dones: np.ndarray               # [N] bool


class TRMCurriculumBase(ABC):
    """Base class for per-TRM curriculum generators."""

    def __init__(self, sc_config: SCConfigData, seed: Optional[int] = None):
        self.sc_config = sc_config
        self.erp_params = _build_erp_params(sc_config)
        if seed is not None:
            np.random.seed(seed)
            random.seed(seed)

    @abstractmethod
    def generate(self, phase: int, num_samples: int) -> CurriculumData:
        """Generate curriculum data for a given phase."""
        ...

    @property
    @abstractmethod
    def state_dim(self) -> int:
        ...

    @property
    @abstractmethod
    def trm_type(self) -> str:
        ...

    def _clip_positive(self, arr: np.ndarray) -> np.ndarray:
        return np.maximum(arr, 0.0)


# ---------------------------------------------------------------------------
# ATP Executor Curriculum
# ---------------------------------------------------------------------------

class ATPCurriculum(TRMCurriculumBase):
    """
    Curriculum for ATP Executor TRM.

    State (12): order_priority, requested_qty, current_inventory,
        pipeline_inventory, safety_stock_level, demand_forecast,
        demand_uncertainty, allocation_available[1..5]

    Action discrete (5): fulfill, partial, defer, reserve, reject
    Action continuous (1): fulfill_qty (0-1 fraction of requested)
    """

    @property
    def state_dim(self) -> int:
        return ATP_STATE_DIM

    @property
    def trm_type(self) -> str:
        return "atp_executor"

    def generate(self, phase: int, num_samples: int) -> CurriculumData:
        if phase == 1:
            return self._phase1(num_samples)
        elif phase == 2:
            return self._phase2(num_samples)
        else:
            return self._phase3(num_samples)

    def _compute_atp_action(self, priority, requested, inventory, pipeline,
                            safety, forecast, phase):
        """Build ATPState and call the heuristic library."""
        atp_state = ATPState(
            order_qty=requested,
            order_priority=int(priority),
            product_id="CURRICULUM",
            site_id="CURRICULUM",
            available_inventory=inventory + pipeline,
            allocated_inventory=0.0,
            pipeline_qty=pipeline,
            forecast_remaining=forecast,
            confirmed_orders=0.0,
        )
        decision = compute_decision("atp_executor", atp_state, self.erp_params)

        # Map heuristic action to curriculum action space
        curriculum_action = _ATP_ACTION_MAP.get(decision.action, 4)
        fulfill_fraction = decision.quantity / (requested + 1e-6)
        fulfill_fraction = min(1.0, max(0.0, fulfill_fraction))

        # Derive reward: fulfilled orders are good, higher priority fulfillment is better
        if curriculum_action == 0:  # fulfill
            reward = 1.0 + (3 - priority) * 0.1
        elif curriculum_action == 1:  # partial
            reward = fulfill_fraction * 0.8
        elif curriculum_action == 2:  # defer
            reward = 0.3
        elif curriculum_action == 3:  # reserve
            reward = 0.2
        else:  # reject
            reward = -0.2

        reward *= {1: 1.0, 2: 0.9, 3: 0.8}.get(phase, 0.8)
        return curriculum_action, fulfill_fraction, reward

    def _phase1(self, n: int) -> CurriculumData:
        """Phase 1: Single product, abundant inventory, stable demand."""
        states = np.zeros((n, ATP_STATE_DIM), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        qty_fracs = np.zeros((n, 1), dtype=np.float32)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            priority = np.random.randint(1, 6)
            requested = np.random.uniform(10, 60)
            inventory = np.random.uniform(80, 200)
            pipeline = np.random.uniform(30, 80)
            safety = np.random.uniform(20, 40)
            forecast = np.random.uniform(30, 60)
            uncertainty = np.random.uniform(0.05, 0.15)
            allocs = np.random.uniform(50, 150, 5)

            states[i] = [priority, requested, inventory, pipeline, safety,
                         forecast, uncertainty, *allocs]

            act, frac, rew = self._compute_atp_action(
                priority, requested, inventory, pipeline, safety, forecast, 1)
            actions[i] = act
            qty_fracs[i, 0] = frac
            rewards[i] = rew

        next_states = states.copy()
        next_states[:, 2] -= states[:, 1] * qty_fracs[:, 0]  # reduce inventory

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=qty_fracs,
            rewards=rewards,
            next_state_vectors=next_states,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _phase2(self, n: int) -> CurriculumData:
        """Phase 2: Multi-product, scarcity, multi-priority."""
        states = np.zeros((n, ATP_STATE_DIM), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        qty_fracs = np.zeros((n, 1), dtype=np.float32)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            priority = np.random.randint(1, 6)
            requested = np.random.uniform(20, 100)
            # Scarce inventory
            inventory = np.random.uniform(10, 80)
            pipeline = np.random.uniform(5, 40)
            safety = np.random.uniform(15, 50)
            forecast = np.random.uniform(40, 90)
            uncertainty = np.random.uniform(0.1, 0.3)
            # Allocation tiers with some empty
            allocs = np.random.uniform(0, 80, 5)
            allocs[np.random.choice(5, 2, replace=False)] = 0

            states[i] = [priority, requested, inventory, pipeline, safety,
                         forecast, uncertainty, *allocs]

            act, frac, rew = self._compute_atp_action(
                priority, requested, inventory, pipeline, safety, forecast, 2)
            actions[i] = act
            qty_fracs[i, 0] = frac
            rewards[i] = rew

        next_states = states.copy()
        next_states[:, 2] -= states[:, 1] * qty_fracs[:, 0]
        next_states[:, 2] = np.maximum(next_states[:, 2], 0)

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=qty_fracs,
            rewards=rewards,
            next_state_vectors=next_states,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _phase3(self, n: int) -> CurriculumData:
        """Phase 3: Full complexity, demand spikes, supply disruptions."""
        states = np.zeros((n, ATP_STATE_DIM), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        qty_fracs = np.zeros((n, 1), dtype=np.float32)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            priority = np.random.randint(1, 6)
            # Demand spikes
            spike = np.random.random() < 0.2
            requested = np.random.uniform(50, 200) if spike else np.random.uniform(10, 80)
            # Supply disruption
            disruption = np.random.random() < 0.15
            inventory = np.random.uniform(0, 30) if disruption else np.random.uniform(20, 120)
            pipeline = np.random.uniform(0, 10) if disruption else np.random.uniform(10, 60)
            safety = np.random.uniform(10, 60)
            forecast = np.random.uniform(30, 120)
            uncertainty = np.random.uniform(0.15, 0.5)
            allocs = np.random.uniform(0, 60, 5)
            if disruption:
                allocs *= 0.3

            states[i] = [priority, requested, inventory, pipeline, safety,
                         forecast, uncertainty, *allocs]

            act, frac, rew = self._compute_atp_action(
                priority, requested, inventory, pipeline, safety, forecast, 3)
            actions[i] = act
            qty_fracs[i, 0] = frac
            rewards[i] = rew

        next_states = states.copy()
        next_states[:, 2] -= states[:, 1] * qty_fracs[:, 0]
        next_states[:, 2] = np.maximum(next_states[:, 2], 0)

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=qty_fracs,
            rewards=rewards,
            next_state_vectors=next_states,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )


# ---------------------------------------------------------------------------
# Rebalancing Curriculum
# ---------------------------------------------------------------------------

class RebalancingCurriculum(TRMCurriculumBase):
    """
    Curriculum for Inventory Rebalancing TRM.

    State (30): source_site(12) + dest_site(12) + lane(3) + network(3)
        Per-site 12: on_hand, safety_stock, backlog, pipeline, demand_avg,
            demand_std, days_of_supply, capacity_utilization, service_level,
            holding_cost_rate, stockout_risk, excess_ratio
        Lane 3: transit_time, transit_cost, lane_reliability
        Network 3: network_imbalance, total_excess, total_deficit

    Action discrete (1): 0=hold, 1=transfer
    Action continuous (1): transfer_qty
    """

    @property
    def state_dim(self) -> int:
        return REB_STATE_DIM

    @property
    def trm_type(self) -> str:
        return "rebalancing"

    def generate(self, phase: int, num_samples: int) -> CurriculumData:
        if phase == 1:
            return self._phase1(num_samples)
        elif phase == 2:
            return self._phase2(num_samples)
        else:
            return self._phase3(num_samples)

    def _make_site_features(self, on_hand, safety, backlog, pipeline,
                            demand_avg, demand_std, capacity_util,
                            service_level, holding_cost, stockout_risk):
        """Build 12-dim site feature vector."""
        dos = on_hand / (demand_avg + 1e-6) * 7
        excess = max(0, on_hand - safety * 1.5) / (safety + 1e-6)
        return np.array([
            on_hand, safety, backlog, pipeline, demand_avg, demand_std,
            dos, capacity_util, service_level, holding_cost, stockout_risk, excess
        ], dtype=np.float32)

    def _compute_reb_action(self, src_oh, src_safety, src_backlog,
                            dst_oh, dst_safety, dst_backlog,
                            transit_cost, phase):
        """Build RebalancingState and call the heuristic library."""
        demand = self.sc_config.avg_demand
        reb_state = RebalancingState(
            source_on_hand=src_oh,
            source_backlog=src_backlog,
            source_avg_demand=demand,
            source_safety_stock=src_safety,
            target_on_hand=dst_oh,
            target_backlog=dst_backlog,
            target_avg_demand=demand,
            target_safety_stock=dst_safety,
            transfer_lead_time_days=self.sc_config.avg_lead_time * 0.5,
            transfer_cost_per_unit=transit_cost,
        )
        decision = compute_decision("inventory_rebalancing", reb_state, self.erp_params)

        curriculum_action = _REB_ACTION_MAP.get(decision.action, 0)
        transfer_qty = max(0.0, decision.quantity)

        if curriculum_action == 1 and transfer_qty > 0:
            reward = 0.8 * {1: 1.0, 2: 0.9, 3: 0.8}.get(phase, 0.8)
        else:
            reward = 0.5 * {1: 1.0, 2: 0.85, 3: 0.7}.get(phase, 0.7)

        return curriculum_action, transfer_qty, reward

    def _phase1(self, n: int) -> CurriculumData:
        """Phase 1: 2 sites, 1 product, clear imbalance."""
        states = np.zeros((n, REB_STATE_DIM), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        qtys = np.zeros((n, 1), dtype=np.float32)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            demand = np.random.uniform(30, 60)
            safety = demand * 1.5

            # Clear imbalance: one site has excess, other has deficit
            if np.random.random() < 0.7:
                src_oh = np.random.uniform(safety * 1.5, safety * 3)
                dst_oh = np.random.uniform(0, safety * 0.5)
            else:
                src_oh = np.random.uniform(safety * 0.8, safety * 1.2)
                dst_oh = np.random.uniform(safety * 0.8, safety * 1.2)

            src_backlog = 0.0
            dst_backlog = np.random.uniform(0, 10)

            src = self._make_site_features(
                src_oh, safety, src_backlog, np.random.uniform(10, 30),
                demand, demand * 0.1, 0.5, 0.95, 0.01, 0.05)
            dst = self._make_site_features(
                dst_oh, safety, dst_backlog, np.random.uniform(5, 20),
                demand, demand * 0.1, 0.5, 0.85, 0.01, 0.3)

            transit_cost = 0.5
            lane = np.array([3.0, transit_cost, 0.95], dtype=np.float32)
            imbalance = abs(src_oh - dst_oh) / (safety + 1e-6)
            excess = max(0, src_oh - safety)
            deficit = max(0, safety - dst_oh)
            network = np.array([imbalance, excess, deficit], dtype=np.float32)

            states[i] = np.concatenate([src, dst, lane, network])

            act, qty, rew = self._compute_reb_action(
                src_oh, safety, src_backlog, dst_oh, safety, dst_backlog,
                transit_cost, 1)
            actions[i] = act
            qtys[i, 0] = qty
            rewards[i] = rew

        next_states = states.copy()
        transferred = actions.astype(float) * qtys[:, 0]
        next_states[:, 0] -= transferred  # source on_hand
        next_states[:, 12] += transferred  # dest on_hand

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=qtys,
            rewards=rewards,
            next_state_vectors=next_states,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _phase2(self, n: int) -> CurriculumData:
        """Phase 2: Cost/time trade-offs, seasonal demand."""
        states = np.zeros((n, REB_STATE_DIM), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        qtys = np.zeros((n, 1), dtype=np.float32)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            # Seasonal demand
            season = np.random.choice(["peak", "trough", "normal"], p=[0.3, 0.2, 0.5])
            base_demand = np.random.uniform(30, 80)
            if season == "peak":
                demand = base_demand * 1.5
            elif season == "trough":
                demand = base_demand * 0.6
            else:
                demand = base_demand

            safety = demand * np.random.uniform(1.0, 2.0)
            src_oh = np.random.uniform(safety * 0.3, safety * 2.5)
            dst_oh = np.random.uniform(safety * 0.2, safety * 1.8)
            src_backlog = np.random.uniform(0, 15)
            dst_backlog = np.random.uniform(0, 20)

            src = self._make_site_features(
                src_oh, safety, src_backlog, np.random.uniform(10, 40),
                demand, demand * 0.2, np.random.uniform(0.4, 0.8),
                np.random.uniform(0.8, 0.98), np.random.uniform(0.005, 0.02),
                np.random.uniform(0.05, 0.3))
            dst = self._make_site_features(
                dst_oh, safety, dst_backlog, np.random.uniform(5, 30),
                demand, demand * 0.2, np.random.uniform(0.3, 0.7),
                np.random.uniform(0.7, 0.95), np.random.uniform(0.005, 0.02),
                np.random.uniform(0.1, 0.5))

            transit_time = np.random.uniform(1, 10)
            transit_cost = np.random.uniform(0.2, 3.0)
            reliability = np.random.uniform(0.8, 0.99)
            lane = np.array([transit_time, transit_cost, reliability], dtype=np.float32)

            imbalance = abs(src_oh - dst_oh) / (safety + 1e-6)
            excess = max(0, src_oh - safety)
            deficit = max(0, safety - dst_oh)
            network = np.array([imbalance, excess, deficit], dtype=np.float32)

            states[i] = np.concatenate([src, dst, lane, network])

            act, qty, rew = self._compute_reb_action(
                src_oh, safety, src_backlog, dst_oh, safety, dst_backlog,
                transit_cost, 2)
            actions[i] = act
            qtys[i, 0] = qty
            rewards[i] = rew

        next_states = states.copy()
        transferred = actions.astype(float) * qtys[:, 0]
        next_states[:, 0] -= transferred
        next_states[:, 12] += transferred

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=qtys,
            rewards=rewards,
            next_state_vectors=next_states,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _phase3(self, n: int) -> CurriculumData:
        """Phase 3: Full network, risk scores, proactive rebalancing."""
        states = np.zeros((n, REB_STATE_DIM), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        qtys = np.zeros((n, 1), dtype=np.float32)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            demand = np.random.uniform(20, 100)
            safety = demand * np.random.uniform(1.0, 2.5)

            # Disruption scenarios
            disruption = np.random.random() < 0.2
            src_oh = np.random.uniform(safety * 0.1, safety * 3)
            dst_oh = np.random.uniform(0, safety * 0.4) if disruption else np.random.uniform(
                safety * 0.2, safety * 2)

            stockout_risk_src = max(0, 1 - src_oh / (safety + 1e-6))
            stockout_risk_dst = max(0, 1 - dst_oh / (safety + 1e-6))

            src_backlog = np.random.uniform(0, 25)
            dst_backlog = np.random.uniform(0, 30)

            src = self._make_site_features(
                src_oh, safety, src_backlog, np.random.uniform(0, 50),
                demand, demand * np.random.uniform(0.1, 0.4),
                np.random.uniform(0.3, 0.9), np.random.uniform(0.6, 0.99),
                np.random.uniform(0.005, 0.03), stockout_risk_src)
            dst = self._make_site_features(
                dst_oh, safety, dst_backlog, np.random.uniform(0, 40),
                demand, demand * np.random.uniform(0.1, 0.4),
                np.random.uniform(0.3, 0.9), np.random.uniform(0.5, 0.95),
                np.random.uniform(0.005, 0.03), stockout_risk_dst)

            transit_time = np.random.uniform(1, 14)
            transit_cost = np.random.uniform(0.1, 5.0)
            reliability = np.random.uniform(0.6, 0.99)
            lane = np.array([transit_time, transit_cost, reliability], dtype=np.float32)

            imbalance = abs(src_oh - dst_oh) / (safety + 1e-6)
            excess = max(0, src_oh - safety)
            deficit = max(0, safety - dst_oh)
            network = np.array([imbalance, excess, deficit], dtype=np.float32)

            states[i] = np.concatenate([src, dst, lane, network])

            act, qty, rew = self._compute_reb_action(
                src_oh, safety, src_backlog, dst_oh, safety, dst_backlog,
                transit_cost, 3)
            actions[i] = act
            qtys[i, 0] = qty
            rewards[i] = rew

        next_states = states.copy()
        transferred = actions.astype(float) * qtys[:, 0]
        next_states[:, 0] -= transferred
        next_states[:, 12] += transferred

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=qtys,
            rewards=rewards,
            next_state_vectors=next_states,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )


# ---------------------------------------------------------------------------
# PO Creation Curriculum
# ---------------------------------------------------------------------------

class POCreationCurriculum(TRMCurriculumBase):
    """
    Curriculum for PO Creation TRM.

    State (17): on_hand, in_transit, on_order, committed, backlog,
        safety_stock, reorder_point, days_of_supply,
        lead_time_days, unit_cost, min_order_qty, on_time_rate, is_available,
        forecast_next_30_days, forecast_uncertainty,
        supply_risk_score, demand_volatility_score

    Action discrete (4): order, defer, expedite, cancel
    Action continuous (1): order_qty
    """

    @property
    def state_dim(self) -> int:
        return PO_STATE_DIM

    @property
    def trm_type(self) -> str:
        return "po_creation"

    def generate(self, phase: int, num_samples: int) -> CurriculumData:
        if phase == 1:
            return self._phase1(num_samples)
        elif phase == 2:
            return self._phase2(num_samples)
        else:
            return self._phase3(num_samples)

    def _compute_po_action(self, on_hand, in_transit, on_order, committed,
                           backlog, safety, rop, forecast, lead_time, moq,
                           otr, available, supply_risk, phase):
        """Build ReplenishmentState and call the heuristic library."""
        ip = on_hand + in_transit + on_order - committed - backlog
        demand_daily = forecast / 30.0

        replenishment_state = ReplenishmentState(
            inventory_position=ip,
            on_hand=on_hand,
            backlog=backlog,
            pipeline_qty=in_transit + on_order,
            avg_daily_demand=demand_daily,
            demand_cv=0.2,
            lead_time_days=lead_time,
            forecast_daily=demand_daily,
            day_of_week=np.random.randint(0, 5),
            day_of_month=np.random.randint(1, 29),
        )

        # Build ERP params with the sampled per-sample overrides
        erp = ERPPlanningParams(
            planning_method=self.erp_params.planning_method,
            lot_sizing_rule=self.erp_params.lot_sizing_rule,
            reorder_point=rop,
            safety_stock=safety,
            order_up_to=rop + safety,
            min_order_quantity=moq,
            lead_time_days=int(lead_time),
            erp_source=self.erp_params.erp_source,
            erp_params=self.erp_params.erp_params,
        )

        decision = compute_decision("po_creation", replenishment_state, erp)

        # Map heuristic action to curriculum action space
        # Heuristic: action=0 (no order) -> curriculum defer (1)
        # Heuristic: action=1 (order) -> curriculum order (0)
        if decision.action == 0 and decision.quantity <= 0:
            # No order needed
            curriculum_action = 1  # defer
            qty = 0.0
        elif decision.action == 1 and decision.quantity > 0:
            # Order
            curriculum_action = 0  # order
            qty = decision.quantity
        else:
            # Edge case
            curriculum_action = 1
            qty = 0.0

        # Adjust for supplier unavailability and urgency (phase 2+)
        if not available and phase >= 2:
            if ip < safety * 0.3 and phase == 3:
                curriculum_action = 3  # cancel (find alternate)
                qty = 0.0
            else:
                curriculum_action = 1  # defer
                qty = 0.0

        # Check for expedite condition (urgent replenishment)
        if curriculum_action == 0 and ip < safety * 0.5 and phase >= 2:
            curriculum_action = 2  # expedite
            # Keep the quantity from the heuristic

        # Reward based on action appropriateness
        phase_discount = {1: 1.0, 2: 0.9, 3: 0.8}.get(phase, 0.8)
        if curriculum_action == 0:
            reward = 0.8 * phase_discount
        elif curriculum_action == 1:
            reward = 0.6 * phase_discount
        elif curriculum_action == 2:
            reward = 0.5 * phase_discount  # expediting is costly
        elif curriculum_action == 3:
            reward = 0.2 * phase_discount
        else:
            reward = 0.4 * phase_discount

        return curriculum_action, qty, reward

    def _phase1(self, n: int) -> CurriculumData:
        """Phase 1: 1 reliable supplier, clear reorder point."""
        states = np.zeros((n, PO_STATE_DIM), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        qtys = np.zeros((n, 1), dtype=np.float32)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            forecast = np.random.uniform(30, 80)
            safety = forecast * np.random.uniform(1.0, 1.5)
            rop = safety + forecast * 0.5
            on_hand = np.random.uniform(0, rop * 2)
            in_transit = np.random.uniform(0, forecast * 0.3)
            on_order = np.random.uniform(0, forecast * 0.2)
            committed = np.random.uniform(0, on_hand * 0.3)
            backlog = np.random.uniform(0, 5)
            dos = on_hand / (forecast / 30 + 1e-6)
            lead_time = np.random.uniform(5, 10)
            unit_cost = np.random.uniform(5, 30)
            moq = np.random.uniform(10, 50)
            otr = np.random.uniform(0.9, 0.99)  # reliable
            available = 1.0
            uncertainty = np.random.uniform(0.05, 0.15)
            supply_risk = np.random.uniform(0.0, 0.2)
            demand_vol = np.random.uniform(0.05, 0.15)

            states[i] = [on_hand, in_transit, on_order, committed, backlog,
                         safety, rop, dos, lead_time, unit_cost, moq, otr,
                         available, forecast, uncertainty, supply_risk, demand_vol]

            act, qty, rew = self._compute_po_action(
                on_hand, in_transit, on_order, committed, backlog,
                safety, rop, forecast, lead_time, moq, otr, available,
                supply_risk, 1)
            actions[i] = act
            qtys[i, 0] = qty
            rewards[i] = rew

        next_states = states.copy()
        next_states[:, 2] += qtys[:, 0]  # on_order
        next_states[:, 7] = (next_states[:, 0] + qtys[:, 0]) / (states[:, 13] / 30 + 1e-6)

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=qtys,
            rewards=rewards,
            next_state_vectors=next_states,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _phase2(self, n: int) -> CurriculumData:
        """Phase 2: Multi-supplier, lead time variability, MOQ constraints."""
        states = np.zeros((n, PO_STATE_DIM), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        qtys = np.zeros((n, 1), dtype=np.float32)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            forecast = np.random.uniform(30, 100)
            safety = forecast * np.random.uniform(1.0, 2.0)
            rop = safety + forecast * np.random.uniform(0.3, 0.8)
            on_hand = np.random.uniform(0, rop * 1.5)
            in_transit = np.random.uniform(0, forecast * 0.5)
            on_order = np.random.uniform(0, forecast * 0.4)
            committed = np.random.uniform(0, on_hand * 0.4)
            backlog = np.random.uniform(0, 15)
            dos = on_hand / (forecast / 30 + 1e-6)
            lead_time = np.random.uniform(3, 21)
            unit_cost = np.random.uniform(3, 50)
            moq = np.random.uniform(20, 100)
            otr = np.random.uniform(0.7, 0.95)
            available = 1.0 if np.random.random() > 0.1 else 0.0
            uncertainty = np.random.uniform(0.1, 0.3)
            supply_risk = np.random.uniform(0.1, 0.4)
            demand_vol = np.random.uniform(0.1, 0.3)

            states[i] = [on_hand, in_transit, on_order, committed, backlog,
                         safety, rop, dos, lead_time, unit_cost, moq, otr,
                         available, forecast, uncertainty, supply_risk, demand_vol]

            act, qty, rew = self._compute_po_action(
                on_hand, in_transit, on_order, committed, backlog,
                safety, rop, forecast, lead_time, moq, otr, available,
                supply_risk, 2)
            actions[i] = act
            qtys[i, 0] = qty
            rewards[i] = rew

        next_states = states.copy()
        next_states[:, 2] += qtys[:, 0]

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=qtys,
            rewards=rewards,
            next_state_vectors=next_states,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _phase3(self, n: int) -> CurriculumData:
        """Phase 3: Disruptions, forecast uncertainty, expedite costs."""
        states = np.zeros((n, PO_STATE_DIM), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        qtys = np.zeros((n, 1), dtype=np.float32)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            disruption = np.random.random() < 0.2
            demand_spike = np.random.random() < 0.15

            forecast = np.random.uniform(40, 120)
            if demand_spike:
                forecast *= 1.8
            safety = forecast * np.random.uniform(1.0, 2.5)
            rop = safety + forecast * np.random.uniform(0.3, 1.0)
            on_hand = np.random.uniform(0, rop * 1.2)
            in_transit = np.random.uniform(0, forecast * 0.6)
            on_order = np.random.uniform(0, forecast * 0.5)
            committed = np.random.uniform(0, on_hand * 0.5)
            backlog = np.random.uniform(0, 30) if demand_spike else np.random.uniform(0, 10)
            dos = on_hand / (forecast / 30 + 1e-6)
            lead_time = np.random.uniform(2, 30)
            unit_cost = np.random.uniform(2, 80)
            moq = np.random.uniform(10, 150)
            otr = np.random.uniform(0.5, 0.7) if disruption else np.random.uniform(0.75, 0.98)
            available = 0.0 if (disruption and np.random.random() < 0.4) else 1.0
            uncertainty = np.random.uniform(0.2, 0.5)
            supply_risk = np.random.uniform(0.4, 0.9) if disruption else np.random.uniform(0.05, 0.3)
            demand_vol = np.random.uniform(0.2, 0.5) if demand_spike else np.random.uniform(0.05, 0.25)

            states[i] = [on_hand, in_transit, on_order, committed, backlog,
                         safety, rop, dos, lead_time, unit_cost, moq, otr,
                         available, forecast, uncertainty, supply_risk, demand_vol]

            act, qty, rew = self._compute_po_action(
                on_hand, in_transit, on_order, committed, backlog,
                safety, rop, forecast, lead_time, moq, otr, available,
                supply_risk, 3)
            actions[i] = act
            qtys[i, 0] = qty
            rewards[i] = rew

        next_states = states.copy()
        next_states[:, 2] += qtys[:, 0]

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=qtys,
            rewards=rewards,
            next_state_vectors=next_states,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )


# ---------------------------------------------------------------------------
# Order Tracking Curriculum
# ---------------------------------------------------------------------------

class OrderTrackingCurriculum(TRMCurriculumBase):
    """
    Curriculum for Order Tracking TRM.

    State (15): is_purchase_order, is_transfer_order, is_customer_order,
        is_in_transit, is_partially_received, days_until_expected,
        days_since_created, ordered_qty, received_qty, remaining_qty,
        fill_rate, price_variance_pct, partner_on_time_rate,
        partner_fill_rate, typical_transit_days

    Action discrete: exception_type (9), severity (4), recommended_action (9)
        For simplicity, we use 3 separate arrays in CurriculumData:
        action_discrete = exception_type index (0-8)
        action_continuous[:, 0] = severity index (0-3)
        action_continuous[:, 1] = recommended_action index (0-8)
    """

    @property
    def state_dim(self) -> int:
        return OT_STATE_DIM

    @property
    def trm_type(self) -> str:
        return "order_tracking"

    def generate(self, phase: int, num_samples: int) -> CurriculumData:
        if phase == 1:
            return self._phase1(num_samples)
        elif phase == 2:
            return self._phase2(num_samples)
        else:
            return self._phase3(num_samples)

    def _compute_ot_action(self, order_type_str, days_overdue, qty_ordered,
                           qty_received, otr, is_critical, price_var,
                           is_transit, is_partial, days_since, transit_days,
                           phase):
        """Build OrderTrackingState and call the heuristic library.

        Returns (exception_type, severity, recommended_action, reward).

        The heuristic library returns a severity-based action (0-3) and
        the remaining quantity.  We map this to the curriculum's richer
        exception-type / severity / action triple.
        """
        ot_state = OrderTrackingState(
            order_id="CURRICULUM",
            order_type=order_type_str,
            expected_date="",
            current_status="in_transit" if is_transit else "open",
            quantity_ordered=qty_ordered,
            quantity_received=qty_received,
            days_overdue=days_overdue,
            supplier_on_time_rate=otr,
            is_critical=is_critical,
        )
        decision = compute_decision("order_tracking", ot_state, self.erp_params)

        # The heuristic library returns action = severity (0-3)
        heuristic_severity = decision.action
        fill_rate = qty_received / (qty_ordered + 1e-6)

        # Map to curriculum triple: (exception_type, severity, recommended_action)
        if heuristic_severity == 0:
            # No exception
            return 8, 0, 0, 0.9 * {1: 1.0, 2: 0.95, 3: 0.9}.get(phase, 0.9)

        # Classify exception type from state context
        if days_overdue > 0:
            exception_type = 0  # late_delivery
        elif qty_received > 0 and qty_received < qty_ordered:
            exception_type = 2  # quantity_shortage
        elif abs(price_var) > 0.1:
            exception_type = 7  # price_variance
        elif is_transit and days_since > transit_days * 2:
            exception_type = 6  # stuck_in_transit
        elif not is_transit and not is_partial and qty_received == 0 and days_since > 2:
            exception_type = 5  # missing_confirmation
        else:
            exception_type = 0  # default to late

        # Map severity to recommended action
        if heuristic_severity >= 3:
            rec_action = 4  # find_alternate
            reward = 0.5
        elif heuristic_severity >= 2:
            rec_action = 1  # expedite
            reward = 0.6
        else:
            rec_action = 1  # expedite (monitor)
            reward = 0.7

        # Override for specific exception types
        if exception_type == 7:
            rec_action = 7  # price_negotiation
        elif exception_type == 5:
            rec_action = 8  # escalate
        elif exception_type == 2 and fill_rate < 0.75:
            rec_action = 3  # partial_receipt

        reward *= {1: 1.0, 2: 0.95, 3: 0.9}.get(phase, 0.9)
        return exception_type, heuristic_severity, rec_action, reward

    def _phase1(self, n: int) -> CurriculumData:
        """Phase 1: Binary late/on-time detection."""
        states = np.zeros((n, OT_STATE_DIM), dtype=np.float32)
        exception_types = np.zeros(n, dtype=np.int64)
        cont = np.zeros((n, 2), dtype=np.float32)  # severity, action
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            # Order type (one-hot)
            otype = np.random.choice(3)
            is_po = float(otype == 0)
            is_to = float(otype == 1)
            is_co = float(otype == 2)
            otype_str = ["PO", "TO", "CO"][otype]

            # Status
            is_transit = float(np.random.random() < 0.6)
            is_partial = float(not is_transit and np.random.random() < 0.3)

            # Timing
            is_late = np.random.random() < 0.3
            days_until = np.random.uniform(-10, 0) if is_late else np.random.uniform(0, 10)
            days_since = np.random.uniform(1, 20)
            days_overdue = max(0, -days_until)

            # Quantities
            ordered = np.random.uniform(20, 100)
            received = ordered * np.random.uniform(0.8, 1.0) if not is_transit else 0
            remaining = ordered - received

            fill_rate = received / (ordered + 1e-6)
            price_var = np.random.uniform(-0.02, 0.02)  # minimal variance
            partner_otr = np.random.uniform(0.85, 0.99)
            partner_fr = np.random.uniform(0.9, 0.99)
            transit_days = np.random.uniform(3, 10)

            states[i] = [is_po, is_to, is_co, is_transit, is_partial,
                         days_until, days_since, ordered, received, remaining,
                         fill_rate, price_var, partner_otr, partner_fr, transit_days]

            et, sev, act, rew = self._compute_ot_action(
                otype_str, days_overdue, ordered, received, partner_otr,
                False, price_var, bool(is_transit), bool(is_partial),
                days_since, transit_days, 1)
            exception_types[i] = et
            cont[i, 0] = sev
            cont[i, 1] = act
            rewards[i] = rew

        next_states = states.copy()
        next_states[:, 5] -= 1  # one day closer

        return CurriculumData(
            state_vectors=states,
            action_discrete=exception_types,
            action_continuous=cont,
            rewards=rewards,
            next_state_vectors=next_states,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _phase2(self, n: int) -> CurriculumData:
        """Phase 2: All exception types + severity classification."""
        states = np.zeros((n, OT_STATE_DIM), dtype=np.float32)
        exception_types = np.zeros(n, dtype=np.int64)
        cont = np.zeros((n, 2), dtype=np.float32)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            otype = np.random.choice(3)
            is_po, is_to, is_co = float(otype == 0), float(otype == 1), float(otype == 2)
            otype_str = ["PO", "TO", "CO"][otype]
            is_transit = float(np.random.random() < 0.5)
            is_partial = float(not is_transit and np.random.random() < 0.3)

            days_until = np.random.uniform(-15, 10)
            days_since = np.random.uniform(1, 30)
            ordered = np.random.uniform(20, 150)
            shortage = np.random.random() < 0.2
            received = ordered * np.random.uniform(0.5, 0.85) if shortage else ordered * np.random.uniform(0.9, 1.0)
            if is_transit:
                received = 0
            remaining = ordered - received
            fill_rate = received / (ordered + 1e-6)
            price_var = np.random.uniform(-0.15, 0.15)
            partner_otr = np.random.uniform(0.7, 0.98)
            partner_fr = np.random.uniform(0.8, 0.99)
            transit_days = np.random.uniform(2, 15)
            days_overdue = max(0, -days_until)

            states[i] = [is_po, is_to, is_co, is_transit, is_partial,
                         days_until, days_since, ordered, received, remaining,
                         fill_rate, price_var, partner_otr, partner_fr, transit_days]

            et, sev, act, rew = self._compute_ot_action(
                otype_str, days_overdue, ordered, received, partner_otr,
                False, price_var, bool(is_transit), bool(is_partial),
                days_since, transit_days, 2)
            exception_types[i] = et
            cont[i, 0] = sev
            cont[i, 1] = act
            rewards[i] = rew

        next_states = states.copy()
        next_states[:, 5] -= 1

        return CurriculumData(
            state_vectors=states,
            action_discrete=exception_types,
            action_continuous=cont,
            rewards=rewards,
            next_state_vectors=next_states,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _phase3(self, n: int) -> CurriculumData:
        """Phase 3: Context-aware resolution with cascading impacts."""
        states = np.zeros((n, OT_STATE_DIM), dtype=np.float32)
        exception_types = np.zeros(n, dtype=np.int64)
        cont = np.zeros((n, 2), dtype=np.float32)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            otype = np.random.choice(3)
            is_po, is_to, is_co = float(otype == 0), float(otype == 1), float(otype == 2)
            otype_str = ["PO", "TO", "CO"][otype]
            is_transit = float(np.random.random() < 0.4)
            is_partial = float(not is_transit and np.random.random() < 0.3)

            # More extreme scenarios
            days_until = np.random.uniform(-20, 15)
            days_since = np.random.uniform(1, 45)
            ordered = np.random.uniform(10, 200)

            # Complex shortage/overage
            scenario = np.random.choice(
                ["normal", "late", "early", "shortage", "overage", "quality",
                 "stuck", "price", "missing"],
                p=[0.3, 0.15, 0.05, 0.12, 0.03, 0.08, 0.07, 0.08, 0.12]
            )

            if scenario == "shortage":
                received = ordered * np.random.uniform(0.3, 0.8) if not is_transit else 0
            elif scenario == "overage":
                received = ordered * np.random.uniform(1.05, 1.2) if not is_transit else 0
            else:
                received = ordered * np.random.uniform(0.9, 1.0) if not is_transit else 0

            remaining = ordered - received
            fill_rate = received / (ordered + 1e-6)
            price_var = np.random.uniform(-0.25, 0.25) if scenario == "price" else np.random.uniform(-0.05, 0.05)
            partner_otr = np.random.uniform(0.5, 0.99)
            partner_fr = np.random.uniform(0.6, 0.99)
            transit_days = np.random.uniform(1, 21)

            if scenario == "late":
                days_until = np.random.uniform(-15, -1)
            elif scenario == "early":
                days_until = np.random.uniform(3, 15)
            elif scenario == "stuck":
                days_since = transit_days * np.random.uniform(2, 4)
                is_transit = 1.0
            elif scenario == "missing":
                days_since = np.random.uniform(3, 10)
                is_transit = 0.0
                is_partial = 0.0
                received = 0.0

            fill_rate = received / (ordered + 1e-6)
            remaining = ordered - received
            days_overdue = max(0, -days_until)

            is_critical = scenario in ("late", "stuck") and np.random.random() < 0.3

            states[i] = [is_po, is_to, is_co, is_transit, is_partial,
                         days_until, days_since, ordered, received, remaining,
                         fill_rate, price_var, partner_otr, partner_fr, transit_days]

            et, sev, act, rew = self._compute_ot_action(
                otype_str, days_overdue, ordered, received, partner_otr,
                is_critical, price_var, bool(is_transit), bool(is_partial),
                days_since, transit_days, 3)
            exception_types[i] = et
            cont[i, 0] = sev
            cont[i, 1] = act
            rewards[i] = rew

        next_states = states.copy()
        next_states[:, 5] -= 1

        return CurriculumData(
            state_vectors=states,
            action_discrete=exception_types,
            action_continuous=cont,
            rewards=rewards,
            next_state_vectors=next_states,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CURRICULUM_REGISTRY = {
    "atp_executor": ATPCurriculum,
    "rebalancing": RebalancingCurriculum,
    "po_creation": POCreationCurriculum,
    "order_tracking": OrderTrackingCurriculum,
}

# Register hive curricula (7 remaining TRMs) from hive_curriculum module
_hive_registered = False

def register_hive_curricula():
    """Import and register the 7 hive TRM curricula.

    Safe to call multiple times — only registers once.
    Called automatically on first import; call explicitly if needed.
    """
    global _hive_registered
    if _hive_registered:
        return
    try:
        from .hive_curriculum import HIVE_CURRICULUM_REGISTRY
        CURRICULUM_REGISTRY.update(HIVE_CURRICULUM_REGISTRY)
        _hive_registered = True
    except Exception:
        pass  # hive_curriculum not yet available

register_hive_curricula()
