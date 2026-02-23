"""
Per-TRM Curriculum Training Data Generators

Each TRM has its own curriculum with 3 progressive phases:
- Phase 1: Simple scenarios (easy decisions, clear signals)
- Phase 2: Moderate complexity (trade-offs, variability)
- Phase 3: Full complexity (disruptions, uncertainty, edge cases)

All curricula generate numpy arrays matching the TRM model's exact
state/action contract, sourced from realistic SC config parameters.

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

logger = logging.getLogger(__name__)


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

            # Easy: inventory always sufficient → fulfill
            available = inventory + pipeline
            if available >= requested:
                actions[i] = 0  # fulfill
                qty_fracs[i, 0] = 1.0
                rewards[i] = 1.0
            else:
                actions[i] = 1  # partial
                qty_fracs[i, 0] = available / requested
                rewards[i] = available / requested

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

            available = inventory + pipeline
            if available >= requested and priority <= 2:
                actions[i] = 0  # fulfill high priority
                qty_fracs[i, 0] = 1.0
                rewards[i] = 1.0 + (3 - priority) * 0.1
            elif available >= requested * 0.5:
                actions[i] = 1  # partial
                qty_fracs[i, 0] = min(1.0, available / requested)
                rewards[i] = qty_fracs[i, 0] * 0.8
            elif priority >= 4:
                actions[i] = 2  # defer low priority
                qty_fracs[i, 0] = 0.0
                rewards[i] = 0.3
            else:
                actions[i] = 3  # reserve
                qty_fracs[i, 0] = 0.0
                rewards[i] = 0.2

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

            available = inventory + pipeline
            ratio = available / (requested + 1e-6)

            if ratio >= 1.0 and priority <= 2:
                actions[i] = 0
                qty_fracs[i, 0] = 1.0
                rewards[i] = 1.0 + (3 - priority) * 0.15
            elif ratio >= 0.5:
                actions[i] = 1
                qty_fracs[i, 0] = min(1.0, ratio)
                rewards[i] = ratio * 0.7
            elif priority >= 4 or disruption:
                actions[i] = 2  # defer
                qty_fracs[i, 0] = 0.0
                rewards[i] = 0.1 if not disruption else 0.3
            elif ratio < 0.1:
                actions[i] = 4  # reject
                qty_fracs[i, 0] = 0.0
                rewards[i] = -0.2
            else:
                actions[i] = 3  # reserve
                qty_fracs[i, 0] = 0.0
                rewards[i] = 0.15

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

            src = self._make_site_features(
                src_oh, safety, 0, np.random.uniform(10, 30),
                demand, demand * 0.1, 0.5, 0.95, 0.01, 0.05)
            dst = self._make_site_features(
                dst_oh, safety, np.random.uniform(0, 10), np.random.uniform(5, 20),
                demand, demand * 0.1, 0.5, 0.85, 0.01, 0.3)

            lane = np.array([3.0, 0.5, 0.95], dtype=np.float32)
            imbalance = abs(src_oh - dst_oh) / (safety + 1e-6)
            excess = max(0, src_oh - safety)
            deficit = max(0, safety - dst_oh)
            network = np.array([imbalance, excess, deficit], dtype=np.float32)

            states[i] = np.concatenate([src, dst, lane, network])

            if src_oh > safety * 1.5 and dst_oh < safety * 0.7:
                actions[i] = 1  # transfer
                qty = min(src_oh - safety, safety - dst_oh)
                qtys[i, 0] = max(0, qty)
                rewards[i] = 0.8
            else:
                actions[i] = 0  # hold
                qtys[i, 0] = 0
                rewards[i] = 0.5

        next_states = states.copy()
        # Update inventories after transfer
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

            src = self._make_site_features(
                src_oh, safety, np.random.uniform(0, 15), np.random.uniform(10, 40),
                demand, demand * 0.2, np.random.uniform(0.4, 0.8),
                np.random.uniform(0.8, 0.98), np.random.uniform(0.005, 0.02),
                np.random.uniform(0.05, 0.3))
            dst = self._make_site_features(
                dst_oh, safety, np.random.uniform(0, 20), np.random.uniform(5, 30),
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

            # Trade-off: benefit of transfer vs cost
            transfer_benefit = max(0, safety - dst_oh) / (safety + 1e-6)
            transfer_cost_norm = transit_cost / 3.0
            net_benefit = transfer_benefit - transfer_cost_norm * 0.3

            if net_benefit > 0.2 and src_oh > safety:
                actions[i] = 1
                qty = min(src_oh - safety * 0.8, deficit)
                qtys[i, 0] = max(0, qty)
                rewards[i] = net_benefit
            else:
                actions[i] = 0
                qtys[i, 0] = 0
                rewards[i] = 0.3 if dst_oh > safety * 0.5 else -0.1

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

            src = self._make_site_features(
                src_oh, safety, np.random.uniform(0, 25), np.random.uniform(0, 50),
                demand, demand * np.random.uniform(0.1, 0.4),
                np.random.uniform(0.3, 0.9), np.random.uniform(0.6, 0.99),
                np.random.uniform(0.005, 0.03), stockout_risk_src)
            dst = self._make_site_features(
                dst_oh, safety, np.random.uniform(0, 30), np.random.uniform(0, 40),
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

            # Proactive: transfer even before crisis if risk is high
            if stockout_risk_dst > 0.6 and src_oh > safety * 0.8:
                actions[i] = 1
                qty = min(src_oh * 0.3, deficit)
                qtys[i, 0] = max(0, qty)
                rewards[i] = 0.7 + (stockout_risk_dst - 0.6)
            elif src_oh > safety * 1.5 and dst_oh < safety * 0.5:
                actions[i] = 1
                qty = min(src_oh - safety, safety - dst_oh)
                qtys[i, 0] = max(0, qty)
                rewards[i] = 0.6
            elif reliability < 0.7 and transit_time > 7:
                # Unreliable lane — risky to transfer
                actions[i] = 0
                qtys[i, 0] = 0
                rewards[i] = 0.4
            else:
                actions[i] = 0
                qtys[i, 0] = 0
                rewards[i] = 0.3 if dst_oh > safety * 0.5 else -0.1

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

            ip = on_hand + in_transit + on_order - committed - backlog
            if ip < rop:
                actions[i] = 0  # order
                qty = max(moq, rop - ip + safety * 0.5)
                qtys[i, 0] = qty
                rewards[i] = 0.8
            else:
                actions[i] = 1  # defer
                qtys[i, 0] = 0
                rewards[i] = 0.6

        next_states = states.copy()
        # After ordering, on_order increases
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

            ip = on_hand + in_transit + on_order - committed - backlog

            if not available:
                actions[i] = 1  # defer (supplier unavailable)
                qtys[i, 0] = 0
                rewards[i] = 0.2
            elif ip < safety * 0.5:
                actions[i] = 2  # expedite (urgent)
                qty = max(moq, rop - ip + safety)
                qtys[i, 0] = qty
                rewards[i] = 0.6
            elif ip < rop:
                actions[i] = 0  # order
                qty = max(moq, rop - ip + safety * 0.3)
                qtys[i, 0] = qty
                rewards[i] = 0.8
            else:
                actions[i] = 1  # defer
                qtys[i, 0] = 0
                rewards[i] = 0.5

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

            ip = on_hand + in_transit + on_order - committed - backlog

            if not available:
                if ip < safety * 0.3:
                    actions[i] = 3  # cancel (find alternate)
                    qtys[i, 0] = 0
                    rewards[i] = 0.1
                else:
                    actions[i] = 1  # defer
                    qtys[i, 0] = 0
                    rewards[i] = 0.3
            elif ip < safety * 0.3:
                actions[i] = 2  # expedite
                qty = max(moq, rop - ip + safety)
                qtys[i, 0] = qty
                rewards[i] = 0.5  # expedite is costly
            elif ip < rop:
                actions[i] = 0  # order
                qty = max(moq, rop - ip + safety * 0.5)
                qtys[i, 0] = qty
                rewards[i] = 0.8
            elif ip > rop * 1.5:
                actions[i] = 3  # cancel excess
                qtys[i, 0] = 0
                rewards[i] = 0.4
            else:
                actions[i] = 1  # defer
                qtys[i, 0] = 0
                rewards[i] = 0.6

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
        Encoded as single index: exception_type * (4*9) + severity * 9 + action
        OR we output 3 separate discrete arrays.

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

            # Status
            is_transit = float(np.random.random() < 0.6)
            is_partial = float(not is_transit and np.random.random() < 0.3)

            # Timing
            is_late = np.random.random() < 0.3
            days_until = np.random.uniform(-10, 0) if is_late else np.random.uniform(0, 10)
            days_since = np.random.uniform(1, 20)

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

            if is_late and days_until < -2:
                exception_types[i] = 0  # late_delivery
                cont[i, 0] = 1  # warning
                cont[i, 1] = 1  # expedite
                rewards[i] = 0.7
            else:
                exception_types[i] = 8  # no_exception
                cont[i, 0] = 0  # info
                cont[i, 1] = 0  # no_action
                rewards[i] = 0.9

        next_states = states.copy()
        # After detection, order progresses
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

            states[i] = [is_po, is_to, is_co, is_transit, is_partial,
                         days_until, days_since, ordered, received, remaining,
                         fill_rate, price_var, partner_otr, partner_fr, transit_days]

            # Classify exception
            if days_until < -7:
                exception_types[i] = 0  # late
                cont[i, 0] = 3  # critical
                cont[i, 1] = 4  # find_alternate
                rewards[i] = 0.6
            elif days_until < -2:
                exception_types[i] = 0  # late
                cont[i, 0] = 2  # high
                cont[i, 1] = 1  # expedite
                rewards[i] = 0.7
            elif days_until > transit_days * 0.5 and is_transit:
                exception_types[i] = 1  # early
                cont[i, 0] = 1  # warning
                cont[i, 1] = 2  # delay_acceptance
                rewards[i] = 0.75
            elif shortage and fill_rate < 0.75:
                exception_types[i] = 2  # quantity_shortage
                cont[i, 0] = 2  # high
                cont[i, 1] = 3  # partial_receipt
                rewards[i] = 0.65
            elif shortage and fill_rate < 0.95:
                exception_types[i] = 2  # quantity_shortage
                cont[i, 0] = 1  # warning
                cont[i, 1] = 3  # partial_receipt
                rewards[i] = 0.75
            elif abs(price_var) > 0.1:
                exception_types[i] = 7  # price_variance
                cont[i, 0] = 1  # warning
                cont[i, 1] = 7  # price_negotiation
                rewards[i] = 0.7
            elif days_since > transit_days * 2 and is_transit:
                exception_types[i] = 6  # stuck_in_transit
                cont[i, 0] = 3  # critical
                cont[i, 1] = 4  # find_alternate
                rewards[i] = 0.5
            elif days_since > 2 and not is_transit and not is_partial and received == 0:
                exception_types[i] = 5  # missing_confirmation
                cont[i, 0] = 2  # high
                cont[i, 1] = 8  # escalate
                rewards[i] = 0.6
            else:
                exception_types[i] = 8  # no_exception
                cont[i, 0] = 0  # info
                cont[i, 1] = 0  # no_action
                rewards[i] = 0.9

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

            states[i] = [is_po, is_to, is_co, is_transit, is_partial,
                         days_until, days_since, ordered, received, remaining,
                         fill_rate, price_var, partner_otr, partner_fr, transit_days]

            # Context-aware decisions
            if scenario == "late":
                severity_val = 3 if days_until < -10 else (2 if days_until < -5 else 1)
                if severity_val == 3 and partner_otr < 0.7:
                    exception_types[i] = 0
                    cont[i] = [3, 4]  # critical, find_alternate
                    rewards[i] = 0.5
                elif severity_val >= 2:
                    exception_types[i] = 0
                    cont[i] = [severity_val, 1]  # expedite
                    rewards[i] = 0.6
                else:
                    exception_types[i] = 0
                    cont[i] = [1, 1]  # warning, expedite
                    rewards[i] = 0.7
            elif scenario == "early":
                exception_types[i] = 1
                cont[i] = [1, 2]  # warning, delay_acceptance
                rewards[i] = 0.75
            elif scenario == "shortage":
                sev = 3 if fill_rate < 0.5 else (2 if fill_rate < 0.75 else 1)
                action = 4 if sev == 3 else 3  # find_alternate or partial_receipt
                exception_types[i] = 2
                cont[i] = [sev, action]
                rewards[i] = 0.5 + fill_rate * 0.3
            elif scenario == "overage":
                exception_types[i] = 3
                cont[i] = [0, 0]  # info, no_action
                rewards[i] = 0.8
            elif scenario == "quality":
                exception_types[i] = 4
                cont[i] = [2, 6]  # high, quality_inspection
                rewards[i] = 0.55
            elif scenario == "stuck":
                exception_types[i] = 6
                cont[i] = [3, 4]  # critical, find_alternate
                rewards[i] = 0.4
            elif scenario == "price":
                sev = 2 if abs(price_var) > 0.15 else 1
                exception_types[i] = 7
                cont[i] = [sev, 7]  # price_negotiation
                rewards[i] = 0.65
            elif scenario == "missing":
                exception_types[i] = 5
                cont[i] = [2, 8]  # high, escalate
                rewards[i] = 0.55
            else:
                exception_types[i] = 8
                cont[i] = [0, 0]
                rewards[i] = 0.9

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
