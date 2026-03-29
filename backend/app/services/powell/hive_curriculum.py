"""
Hive Curriculum Generators — 7 remaining TRM curricula

Follows the same 3-phase pattern as the existing 4 curricula in trm_curriculum.py:
  Phase 1: Simple, stable scenarios (easy decisions)
  Phase 2: Mixed complexity (trade-offs, multiple factors)
  Phase 3: Stress/disruption scenarios (chaos, cascading failures)

Expert actions are computed by the ERP-aware heuristic library
(``app.services.powell.heuristic_library``) rather than inline if/then
rules.  The curriculum still generates random state vectors (controlling
difficulty progression per phase), but the *label* for each sample comes
from ``compute_decision(trm_type, state_dataclass, erp_params)``.

TRMs covered:
  - MOExecutionCurriculum   (mo_execution)
  - TOExecutionCurriculum   (to_execution)
  - QualityDispositionCurriculum (quality)
  - MaintenanceSchedulingCurriculum (maintenance)
  - SubcontractingCurriculum (subcontracting)
  - ForecastAdjustmentCurriculum (forecast_adj)
  - InventoryBufferCurriculum   (inventory_buffer)
"""

from __future__ import annotations

import random
from typing import Optional, List

import numpy as np

from .trm_curriculum import (
    TRMCurriculumBase, CurriculumData, SCConfigData, _pick_disruption,
)

from app.services.powell.heuristic_library.dispatch import compute_decision
from app.services.powell.heuristic_library.base import (
    ERPPlanningParams,
    MOExecutionState,
    TOExecutionState,
    QualityState,
    MaintenanceState,
    SubcontractingState,
    ForecastAdjustmentState,
    InventoryBufferState,
)


# ---------------------------------------------------------------------------
# State dimensions per TRM
# ---------------------------------------------------------------------------

# State dims MUST match the per-TRM model definitions in app.models.trm.*
MO_STATE_DIM = 20           # Must match app.models.trm.MO_STATE_DIM
TO_STATE_DIM = 16           # Must match app.models.trm.TO_STATE_DIM
QUALITY_STATE_DIM = 14      # Must match app.models.trm.QD_STATE_DIM
MAINTENANCE_STATE_DIM = 14  # Must match app.models.trm.MS_STATE_DIM
SUBCONTRACTING_STATE_DIM = 16   # Must match app.models.trm.SUB_STATE_DIM
FORECAST_ADJ_STATE_DIM = 18     # Must match app.models.trm.FA_STATE_DIM
INVENTORY_BUFFER_STATE_DIM = 14  # Must match app.models.trm.IB_STATE_DIM


# ---------------------------------------------------------------------------
# Action mapping: heuristic library -> curriculum action indices
# ---------------------------------------------------------------------------
# MO heuristic: 0=no-action, 1=release, 2=rework(?), 3=expedite, 4=defer
# MO curriculum: 0=release, 1=defer, 2=split, 3=expedite, 4=cancel
_MO_ACTION_MAP = {0: 1, 1: 0, 2: 2, 3: 3, 4: 1}

# TO heuristic: 0=no-action, 1=release, 2=consolidate, 3=expedite
# TO curriculum: 0=release, 1=defer, 2=consolidate, 3=expedite
_TO_ACTION_MAP = {0: 1, 1: 0, 2: 2, 3: 3}

# Quality heuristic: 1=accept, 2=rework, 3=scrap
# Quality curriculum: 0=accept, 1=reject, 2=rework, 3=scrap, 4=use_as_is
_QUALITY_ACTION_MAP = {0: 1, 1: 0, 2: 2, 3: 3}

# Maintenance heuristic: 0=no-action, 1=schedule, 2=defer
# Maintenance curriculum: 0=schedule, 1=defer, 2=expedite, 3=outsource
_MAINT_ACTION_MAP = {0: 1, 1: 0, 2: 1}

# Subcontracting heuristic: 1=internal, 2=external, 3=split
# Subcontracting curriculum: 0=keep_internal, 1=route_external, 2=split, 3=change_vendor
_SUB_ACTION_MAP = {0: 0, 1: 0, 2: 1, 3: 2}

# Forecast adjustment heuristic: 0=no_adjustment, 1=increase, 2=decrease
# Forecast curriculum: 0=increase_high, 1=increase_low, 2=hold, 3=decrease_low, 4=decrease_high
_FA_ACTION_MAP = {0: 2, 1: 1, 2: 3}

# Inventory buffer heuristic: 0=maintain, 1=increase, 2=decrease
# Buffer curriculum: 0=maintain, 1=increase_small, 2=increase_large, 3=decrease_small, 4=decrease_large
_IB_ACTION_MAP = {0: 0, 1: 1, 2: 3}


# ---------------------------------------------------------------------------
# MO Execution Curriculum
# ---------------------------------------------------------------------------

class MOExecutionCurriculum(TRMCurriculumBase):
    """Curriculum for Manufacturing Order execution decisions.

    State (20 floats, matches MOExecutionTRMModel):
        [0] work_in_progress       [1] capacity_available
        [2] order_qty              [3] due_date_urgency (0-1)
        [4] backlog                [5] material_available (0-1)
        [6] operator_available (0-1) [7] quality_rate (0-1)
        [8] tool_wear (0-1)        [9] maintenance_due (0-1)
        [10] parallel_orders       [11] priority (0-1)
        [12] yield_rate (0-1)      [13] energy_cost (normalised)
        [14] overtime_available (0-1) [15] sequence_position (normalised)
        [16] bom_coverage (0-1)    [17] defect_rate (0-1)
        [18] setup_time (normalised) [19] cycle_time (normalised)

    Actions: 0=release, 1=defer, 2=split, 3=expedite, 4=cancel
    """

    @property
    def state_dim(self) -> int:
        return MO_STATE_DIM

    @property
    def trm_type(self) -> str:
        return "mo_execution"

    def generate(self, phase: int, num_samples: int) -> CurriculumData:
        n = num_samples
        states = np.zeros((n, self.state_dim), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            if phase == 1:
                states[i] = self._phase1_state()
                actions[i], rewards[i] = self._compute_mo_decision(states[i], phase)
            elif phase == 2:
                states[i] = self._phase2_state()
                actions[i], rewards[i] = self._compute_mo_decision(states[i], phase)
            else:
                states[i], actions[i], rewards[i] = self._phase3_disruption()

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=np.zeros((n, 1), dtype=np.float32),
            rewards=rewards,
            next_state_vectors=states * 0.95,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _compute_mo_decision(self, s, phase):
        """Build MOExecutionState from normalised state vector and call heuristic."""
        # Denormalise key fields for the heuristic state dataclass
        capacity_hours = s[1] * 100.0  # normalised -> hours
        setup_hours = s[18] * 8.0
        run_hours = s[19] * 16.0
        order_qty = s[2] * 500.0

        mo_state = MOExecutionState(
            mo_id="CURRICULUM",
            product_id="CURRICULUM",
            site_id="CURRICULUM",
            quantity=order_qty,
            priority=max(1, int(s[11] * 5)),
            due_date="",
            setup_time_hours=setup_hours,
            run_time_hours=run_hours,
            available_capacity_hours=capacity_hours,
            current_wip=s[0] * 200.0,
            glenday_category="yellow",
            oee=float(s[7]),
        )
        decision = compute_decision("mo_execution", mo_state, self.erp_params)

        # Map heuristic action to curriculum action
        curriculum_action = _MO_ACTION_MAP.get(decision.action, 1)

        # Handle material unavailability (not captured by heuristic state)
        if s[5] < 0.5:
            curriculum_action = 1  # defer when no material

        phase_discount = {1: 1.0, 2: 0.9, 3: 0.8}.get(phase, 0.8)
        reward_map = {0: 0.9, 1: 0.5, 2: 0.7, 3: 0.6, 4: 0.3}
        reward = reward_map.get(curriculum_action, 0.5) * phase_discount

        return curriculum_action, reward

    def _phase3_disruption(self):
        """Phase 3: Disruption scenarios where heuristics fail.

        - demand_spike: Rush orders flood in; heuristic releases all (overloads).
          TRM should split orders and expedite high-priority only.
        - supply_disruption: BOM material shortage; heuristic releases anyway.
          TRM should defer until material arrives.
        - capacity_constraint: Machine breakdown (near-zero capacity).
          Heuristic ignores; TRM should split across shifts or cancel low-priority.
        - seasonal_shift: Seasonal demand pulls forward.  Heuristic follows
          static sequence; TRM should resequence for high-value items.
        - cross_product_interaction: Parallel orders competing for same
          capacity.  Heuristic treats independently; TRM should prioritize.
        """
        disruption = _pick_disruption()
        s = self._phase2_state()

        # --- Apply disruption to state ---
        if disruption == "demand_spike":
            s[2] = np.random.uniform(0.6, 1.0)   # large order qty
            s[3] = np.random.uniform(0.7, 1.0)   # high urgency
            s[10] = np.random.uniform(0.5, 0.9)  # many parallel orders
            s[4] = np.random.uniform(0.3, 0.7)   # growing backlog
        elif disruption == "supply_disruption":
            s[5] = 0.0                            # no material available
            s[16] = np.random.uniform(0.3, 0.6)  # low BOM coverage
            s[3] = np.random.uniform(0.5, 0.9)   # urgent
        elif disruption == "capacity_constraint":
            s[1] = np.random.uniform(0.0, 0.1)   # near-zero capacity
            s[9] = np.random.uniform(0.5, 0.9)   # maintenance overdue
            s[7] = np.random.uniform(0.6, 0.8)   # degraded quality
            s[8] = np.random.uniform(0.5, 0.9)   # high tool wear
        elif disruption == "seasonal_shift":
            s[2] = np.random.uniform(0.4, 0.8)   # moderate qty
            s[3] = np.random.uniform(0.5, 0.8)   # rising urgency
            s[11] = np.random.uniform(0.6, 1.0)  # high-priority products
        elif disruption == "cross_product_interaction":
            s[10] = np.random.uniform(0.6, 1.0)  # many parallel orders
            s[1] = np.random.uniform(0.15, 0.35) # limited capacity
            s[3] = np.random.uniform(0.4, 0.8)   # moderate urgency
        else:
            # No disruption — stress baseline
            s[1] = np.random.uniform(0.0, 0.2)
            s[3] = np.random.uniform(0.6, 1.0)
            s[7] = np.random.uniform(0.7, 0.88)
            s[9] = np.random.uniform(0.3, 0.8)

        # --- Compute heuristic baseline ---
        h_act, _ = self._compute_mo_decision(s, 3)

        # --- Override with disruption-aware corrective label ---
        priority = max(1, int(s[11] * 5))
        if disruption == "demand_spike":
            if priority <= 2:
                act, rew = 3, 0.80  # expedite high-priority
            else:
                act, rew = 2, 0.70  # split to manage capacity
        elif disruption == "supply_disruption":
            act, rew = 1, 0.75  # defer — material not available
        elif disruption == "capacity_constraint":
            if priority <= 2:
                act, rew = 3, 0.70  # expedite critical
            else:
                act, rew = 4, 0.55  # cancel non-critical
        elif disruption == "seasonal_shift":
            if priority <= 2:
                act, rew = 0, 0.80  # release high-value first
            else:
                act, rew = 1, 0.65  # defer low-value
        elif disruption == "cross_product_interaction":
            if priority <= 2:
                act, rew = 0, 0.75  # release prioritized
            else:
                act, rew = 1, 0.60  # defer lower priority
        else:
            act, rew = h_act, 0.5 * 0.8

        return s, act, rew

    def _phase1_state(self):
        return np.array([
            np.random.uniform(0.1, 0.4),   # [0] work_in_progress
            np.random.uniform(0.5, 0.8),   # [1] capacity_available
            np.random.uniform(0.1, 0.5),   # [2] order_qty
            np.random.uniform(0.0, 0.3),   # [3] due_date_urgency
            np.random.uniform(0.0, 0.15),  # [4] backlog
            1.0,                           # [5] material_available
            np.random.uniform(0.8, 1.0),   # [6] operator_available
            np.random.uniform(0.92, 0.99), # [7] quality_rate
            np.random.uniform(0.0, 0.15),  # [8] tool_wear
            np.random.uniform(0.0, 0.1),   # [9] maintenance_due
            np.random.uniform(0.1, 0.4),   # [10] parallel_orders
            np.random.randint(1, 4) / 5.0, # [11] priority
            np.random.uniform(0.9, 0.98),  # [12] yield_rate
            np.random.uniform(0.1, 0.3),   # [13] energy_cost
            np.random.uniform(0.5, 1.0),   # [14] overtime_available
            np.random.uniform(0.0, 0.5),   # [15] sequence_position
            np.random.uniform(0.9, 1.0),   # [16] bom_coverage
            np.random.uniform(0.0, 0.03),  # [17] defect_rate
            np.random.uniform(0.1, 0.3),   # [18] setup_time
            np.random.uniform(0.2, 0.5),   # [19] cycle_time
        ], dtype=np.float32)

    def _phase2_state(self):
        s = self._phase1_state()
        s[1] = np.random.uniform(0.2, 0.4)   # lower capacity available
        s[3] = np.random.uniform(0.3, 0.7)   # higher urgency
        s[5] = np.random.choice([0.0, 1.0], p=[0.2, 0.8])  # sometimes no material
        return s


# ---------------------------------------------------------------------------
# TO Execution Curriculum
# ---------------------------------------------------------------------------

class TOExecutionCurriculum(TRMCurriculumBase):
    """Curriculum for Transfer Order execution decisions.

    State (16 floats, matches TOExecutionTRMModel):
        [0] origin_inventory       [1] dest_inventory
        [2] origin_safety_stock    [3] dest_safety_stock
        [4] in_transit_qty         [5] lead_time_days (normalised)
        [6] urgency_score (0-1)    [7] carrier_available (0-1)
        [8] consolidation_opportunity (0-1)  [9] priority (0-1)
        [10] route_reliability (0-1)  [11] mode_cost (normalised)
        [12] quantity              [13] dest_backlog
        [14] origin_excess         [15] days_to_due (normalised)

    Actions: 0=release, 1=defer, 2=consolidate, 3=expedite
    """

    @property
    def state_dim(self) -> int:
        return TO_STATE_DIM

    @property
    def trm_type(self) -> str:
        return "to_execution"

    def generate(self, phase: int, num_samples: int) -> CurriculumData:
        n = num_samples
        states = np.zeros((n, self.state_dim), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            if phase == 1:
                states[i] = self._simple_state()
                actions[i], rewards[i] = self._compute_to_decision(states[i], phase)
            elif phase == 2:
                states[i] = self._mixed_state()
                actions[i], rewards[i] = self._compute_to_decision(states[i], phase)
            else:
                states[i], actions[i], rewards[i] = self._phase3_disruption()

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=np.zeros((n, 1), dtype=np.float32),
            rewards=rewards,
            next_state_vectors=states * 0.95,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _compute_to_decision(self, s, phase):
        """Build TOExecutionState from normalised state vector and call heuristic."""
        priority = max(1, int(s[9] * 5))
        quantity = s[12] * 500.0
        consolidation_days = 2 if s[8] > 0.5 else 0

        to_state = TOExecutionState(
            to_id="CURRICULUM",
            product_id="CURRICULUM",
            from_site_id="CURRICULUM_SRC",
            to_site_id="CURRICULUM_DST",
            quantity=quantity,
            priority=priority,
            due_date="",
            transport_mode="truck",
            consolidation_window_days=consolidation_days,
            current_load_pct=float(1.0 - s[8]) if s[8] > 0.5 else 0.8,
            is_expeditable=True,
        )
        decision = compute_decision("to_execution", to_state, self.erp_params)

        curriculum_action = _TO_ACTION_MAP.get(decision.action, 1)

        phase_discount = {1: 1.0, 2: 0.9, 3: 0.8}.get(phase, 0.8)
        reward_map = {0: 0.9, 1: 0.5, 2: 0.8, 3: 0.7}
        reward = reward_map.get(curriculum_action, 0.5) * phase_discount

        return curriculum_action, reward

    def _phase3_disruption(self):
        """Phase 3: Disruption scenarios where heuristics fail.

        - demand_spike: Destination needs urgent replenishment.
          Heuristic consolidates; TRM should expedite immediately.
        - supply_disruption: Origin inventory collapses.
          Heuristic releases TO; TRM should defer (nothing to ship).
        - capacity_constraint: Carrier unavailable / route degraded.
          Heuristic ignores; TRM should defer or consolidate.
        - seasonal_shift: Peak season, destinations need more.
          Heuristic delays for consolidation; TRM should release fast.
        - bullwhip_amplification: False urgency signals.
          Heuristic expedites; TRM should consolidate to dampen.
        """
        disruption = _pick_disruption()
        s = self._mixed_state()

        # --- Apply disruption ---
        if disruption == "demand_spike":
            s[1] = np.random.uniform(0.0, 0.1)   # dest near empty
            s[6] = np.random.uniform(0.8, 1.0)   # very urgent
            s[13] = np.random.uniform(0.5, 1.0)  # high dest backlog
            s[15] = np.random.uniform(0.0, 0.2)  # very close to due
        elif disruption == "supply_disruption":
            s[0] = np.random.uniform(0.0, 0.1)   # origin has nothing
            s[14] = np.random.uniform(0.0, 0.05) # no origin excess
            s[10] = np.random.uniform(0.4, 0.7)  # lower route reliability
        elif disruption == "capacity_constraint":
            s[7] = np.random.uniform(0.0, 0.3)   # carrier unavailable
            s[10] = np.random.uniform(0.3, 0.6)  # degraded route
            s[11] = np.random.uniform(0.6, 1.0)  # high mode cost
        elif disruption == "seasonal_shift":
            s[1] = np.random.uniform(0.1, 0.3)   # dest running low
            s[6] = np.random.uniform(0.5, 0.8)   # moderate urgency
            s[8] = 1.0                            # consolidation opportunity
        elif disruption == "bullwhip_amplification":
            s[6] = np.random.uniform(0.7, 1.0)   # false high urgency
            s[13] = np.random.uniform(0.1, 0.3)  # actually OK dest backlog
            s[1] = np.random.uniform(0.3, 0.5)   # dest inventory adequate
        else:
            s[1] = np.random.uniform(0.05, 0.2)
            s[6] = np.random.uniform(0.6, 1.0)
            s[10] = np.random.uniform(0.5, 0.85)
            s[13] = np.random.uniform(0.3, 0.8)

        # --- Compute heuristic baseline ---
        h_act, _ = self._compute_to_decision(s, 3)

        # --- Override with disruption-aware corrective label ---
        priority = max(1, int(s[9] * 5))
        if disruption == "demand_spike":
            act, rew = 3, 0.80  # expedite
        elif disruption == "supply_disruption":
            act, rew = 1, 0.75  # defer — nothing to ship
        elif disruption == "capacity_constraint":
            if s[7] < 0.2:
                act, rew = 1, 0.70  # defer — no carrier
            else:
                act, rew = 2, 0.65  # consolidate to reduce cost
        elif disruption == "seasonal_shift":
            act, rew = 0, 0.80  # release immediately, don't wait
        elif disruption == "bullwhip_amplification":
            act, rew = 2, 0.75  # consolidate — dampen noise
        else:
            act, rew = h_act, 0.5 * 0.8

        return s, act, rew

    def _simple_state(self):
        return np.array([
            np.random.uniform(0.5, 0.9),   # [0] origin_inventory
            np.random.uniform(0.3, 0.6),   # [1] dest_inventory
            np.random.uniform(0.2, 0.4),   # [2] origin_safety_stock
            np.random.uniform(0.2, 0.4),   # [3] dest_safety_stock
            np.random.uniform(0.0, 0.2),   # [4] in_transit_qty
            np.random.uniform(0.1, 0.3),   # [5] lead_time_days
            np.random.uniform(0.1, 0.4),   # [6] urgency_score
            np.random.uniform(0.8, 1.0),   # [7] carrier_available
            0.0,                           # [8] consolidation_opportunity
            np.random.randint(1, 4) / 5.0, # [9] priority
            np.random.uniform(0.85, 0.98), # [10] route_reliability
            np.random.uniform(0.1, 0.3),   # [11] mode_cost
            np.random.uniform(0.1, 0.4),   # [12] quantity
            np.random.uniform(0.0, 0.1),   # [13] dest_backlog
            np.random.uniform(0.2, 0.5),   # [14] origin_excess
            np.random.uniform(0.3, 0.7),   # [15] days_to_due
        ], dtype=np.float32)

    def _mixed_state(self):
        s = self._simple_state()
        s[6] = np.random.uniform(0.3, 0.7)   # higher urgency
        s[8] = np.random.choice([0.0, 1.0], p=[0.6, 0.4])  # consolidation
        s[13] = np.random.uniform(0.1, 0.4)  # some dest backlog
        return s


# ---------------------------------------------------------------------------
# Quality Disposition Curriculum
# ---------------------------------------------------------------------------

class QualityDispositionCurriculum(TRMCurriculumBase):
    """Curriculum for Quality disposition decisions.

    State (14 floats, matches QualityDispositionTRMModel):
        [0] defect_rate (0-1)      [1] severity_score (0-1)
        [2] units_affected (norm)  [3] rework_cost (norm)
        [4] scrap_cost (norm)      [5] hold_duration (norm days)
        [6] order_urgency (0-1)    [7] inspection_cost (norm)
        [8] rework_capacity (0-1)  [9] supplier_reliability (0-1)
        [10] warranty_risk (0-1)   [11] customer_impact (0-1)
        [12] production_disruption (0-1)  [13] disposition_cost (norm)

    Actions: 0=accept, 1=reject, 2=rework, 3=scrap, 4=use_as_is
    """

    @property
    def state_dim(self) -> int:
        return QUALITY_STATE_DIM

    @property
    def trm_type(self) -> str:
        return "quality_disposition"

    def generate(self, phase: int, num_samples: int) -> CurriculumData:
        n = num_samples
        states = np.zeros((n, self.state_dim), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            if phase == 1:
                states[i] = self._simple_state()
                actions[i], rewards[i] = self._compute_quality_decision(states[i], phase)
            elif phase == 2:
                states[i] = self._mixed_state()
                actions[i], rewards[i] = self._compute_quality_decision(states[i], phase)
            else:
                states[i], actions[i], rewards[i] = self._phase3_disruption()

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=np.zeros((n, 1), dtype=np.float32),
            rewards=rewards,
            next_state_vectors=states * 0.95,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _compute_quality_decision(self, s, phase):
        """Build QualityState from normalised state vector and call heuristic."""
        # Map severity score to severity string
        if s[1] > 0.7:
            severity_str = "critical"
        elif s[1] > 0.3:
            severity_str = "major"
        else:
            severity_str = "minor"

        # Map defect rate to defect type
        defect_types = ["visual", "dimensional", "functional", "contamination"]
        defect_type = defect_types[np.random.randint(0, len(defect_types))]

        unit_cost = 50.0  # representative unit cost
        q_state = QualityState(
            lot_id="CURRICULUM",
            product_id="CURRICULUM",
            defect_type=defect_type,
            defect_severity=severity_str,
            quantity=s[2] * 500.0,
            unit_cost=unit_cost,
            rework_cost_per_unit=s[3] * unit_cost,
            scrap_value_per_unit=s[4] * unit_cost * 0.1,
            customer_impact=bool(s[11] > 0.5),
        )
        decision = compute_decision("quality_disposition", q_state, self.erp_params)

        curriculum_action = _QUALITY_ACTION_MAP.get(decision.action, 1)

        # Handle urgent orders with minor defects -> use_as_is
        if s[6] > 0.8 and s[0] < 0.08 and severity_str == "minor" and phase >= 3:
            curriculum_action = 4  # use_as_is

        phase_discount = {1: 1.0, 2: 0.9, 3: 0.8}.get(phase, 0.8)
        reward_map = {0: 0.9, 1: 0.7, 2: 0.7, 3: 0.5, 4: 0.4}
        reward = reward_map.get(curriculum_action, 0.5) * phase_discount

        return curriculum_action, reward

    def _phase3_disruption(self):
        """Phase 3: Disruption scenarios where heuristics fail.

        - supply_disruption: Supplier quality collapse (high defect rate from
          supplier going through problems).  Heuristic scraps everything;
          TRM should rework when possible to maintain supply.
        - demand_spike: Urgent customer orders need product NOW.  Heuristic
          rejects; TRM should use-as-is for cosmetic defects.
        - capacity_constraint: Rework line at capacity.  Heuristic queues
          for rework; TRM should scrap low-value and use-as-is borderline.
        - cross_product_interaction: Shared production line causes
          contamination across products.  Heuristic treats each lot
          independently; TRM should escalate (reject) to stop the line.
        """
        disruption = _pick_disruption()
        s = self._mixed_state()

        # --- Apply disruption ---
        if disruption == "supply_disruption":
            s[0] = np.random.uniform(0.15, 0.35)  # very high defect rate
            s[9] = np.random.uniform(0.3, 0.6)    # supplier reliability crashed
            s[1] = np.random.uniform(0.3, 0.7)    # moderate severity
        elif disruption == "demand_spike":
            s[6] = np.random.uniform(0.8, 1.0)    # extreme urgency
            s[0] = np.random.uniform(0.02, 0.08)  # minor defects
            s[1] = np.random.uniform(0.1, 0.3)    # low severity
            s[11] = np.random.uniform(0.1, 0.3)   # low customer impact
        elif disruption == "capacity_constraint":
            s[8] = np.random.uniform(0.05, 0.2)   # rework capacity exhausted
            s[0] = np.random.uniform(0.05, 0.15)  # moderate defect rate
            s[12] = np.random.uniform(0.3, 0.7)   # production disrupted
        elif disruption == "cross_product_interaction":
            s[0] = np.random.uniform(0.10, 0.25)  # widespread defects
            s[1] = np.random.uniform(0.6, 1.0)    # high severity
            s[12] = np.random.uniform(0.5, 1.0)   # production disruption
            s[10] = np.random.uniform(0.5, 0.9)   # high warranty risk
        else:
            s[0] = np.random.uniform(0.05, 0.25)
            s[1] = np.random.uniform(0.5, 1.0)
            s[6] = np.random.uniform(0.6, 1.0)
            s[8] = np.random.uniform(0.2, 0.5)

        # --- Compute heuristic baseline ---
        h_act, _ = self._compute_quality_decision(s, 3)

        # --- Override with disruption-aware corrective label ---
        if disruption == "supply_disruption":
            if s[1] < 0.5:
                act, rew = 2, 0.80  # rework — preserve supply
            else:
                act, rew = 3, 0.60  # scrap critical defects
        elif disruption == "demand_spike":
            act, rew = 4, 0.75  # use_as_is — cosmetic, urgent need
        elif disruption == "capacity_constraint":
            if s[3] < 0.1:  # low rework cost items
                act, rew = 4, 0.65  # use_as_is borderline
            else:
                act, rew = 3, 0.55  # scrap — can't rework
        elif disruption == "cross_product_interaction":
            act, rew = 1, 0.80  # reject — stop the contamination
        else:
            act, rew = h_act, 0.5 * 0.8

        return s, act, rew

    def _simple_state(self):
        return np.array([
            np.random.uniform(0.0, 0.03),  # [0] defect_rate (low)
            np.random.uniform(0.0, 0.3),   # [1] severity_score
            np.random.uniform(0.2, 0.6),   # [2] units_affected
            np.random.uniform(0.05, 0.15), # [3] rework_cost
            np.random.uniform(0.1, 0.3),   # [4] scrap_cost
            np.random.uniform(0.0, 0.2),   # [5] hold_duration
            np.random.uniform(0.1, 0.4),   # [6] order_urgency
            np.random.uniform(0.05, 0.15), # [7] inspection_cost
            np.random.uniform(0.6, 0.9),   # [8] rework_capacity
            np.random.uniform(0.85, 0.98), # [9] supplier_reliability
            np.random.uniform(0.0, 0.2),   # [10] warranty_risk
            np.random.uniform(0.1, 0.4),   # [11] customer_impact
            np.random.uniform(0.0, 0.15),  # [12] production_disruption
            np.random.uniform(0.05, 0.2),  # [13] disposition_cost
        ], dtype=np.float32)

    def _mixed_state(self):
        s = self._simple_state()
        s[0] = np.random.uniform(0.02, 0.10)  # higher defect rate
        s[1] = np.random.uniform(0.2, 0.7)    # higher severity
        s[6] = np.random.uniform(0.3, 0.7)    # higher order urgency
        return s


# ---------------------------------------------------------------------------
# Maintenance Scheduling Curriculum
# ---------------------------------------------------------------------------

class MaintenanceSchedulingCurriculum(TRMCurriculumBase):
    """Curriculum for Maintenance scheduling decisions.

    State (14 floats, matches MaintenanceSchedulingTRMModel):
        [0] asset_health (0-1)     [1] failure_probability (0-1)
        [2] days_to_planned (norm) [3] production_impact (0-1)
        [4] maintenance_duration (norm)  [5] crew_available (0-1)
        [6] parts_available (0-1)  [7] order_urgency (0-1)
        [8] overtime_cost (norm)   [9] outsource_available (0-1)
        [10] last_maintenance_days (norm)  [11] criticality (0-1)
        [12] schedule_backlog (norm)  [13] maintenance_cost (norm)

    Actions: 0=schedule, 1=defer, 2=expedite, 3=outsource
    """

    @property
    def state_dim(self) -> int:
        return MAINTENANCE_STATE_DIM

    @property
    def trm_type(self) -> str:
        return "maintenance_scheduling"

    def generate(self, phase: int, num_samples: int) -> CurriculumData:
        n = num_samples
        states = np.zeros((n, self.state_dim), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            if phase == 1:
                states[i] = self._simple_state()
                actions[i], rewards[i] = self._compute_maint_decision(states[i], phase)
            elif phase == 2:
                states[i] = self._mixed_state()
                actions[i], rewards[i] = self._compute_maint_decision(states[i], phase)
            else:
                states[i], actions[i], rewards[i] = self._phase3_disruption()

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=np.zeros((n, 1), dtype=np.float32),
            rewards=rewards,
            next_state_vectors=states * 0.95,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _compute_maint_decision(self, s, phase):
        """Build MaintenanceState from normalised state vector and call heuristic."""
        # Map criticality score to letter
        if s[11] > 0.7:
            criticality = "A"
        elif s[11] > 0.4:
            criticality = "B"
        else:
            criticality = "C"

        mtbf_days = 90.0  # representative MTBF
        hours_since_pm = s[10] * mtbf_days * 24  # normalised -> hours

        m_state = MaintenanceState(
            asset_id="CURRICULUM",
            site_id="CURRICULUM",
            last_maintenance_date="",
            mtbf_days=mtbf_days,
            mttr_hours=s[4] * 24.0,
            current_operating_hours=hours_since_pm,
            hours_since_last_pm=hours_since_pm,
            criticality=criticality,
            upcoming_production_load=float(s[3]),
            maintenance_cost=s[13] * 1000.0,
        )
        decision = compute_decision("maintenance_scheduling", m_state, self.erp_params)

        curriculum_action = _MAINT_ACTION_MAP.get(decision.action, 1)

        # Handle conditions not captured by heuristic state:
        # Low crew -> defer; no parts -> outsource
        if s[5] < 0.5 and phase >= 2:
            curriculum_action = 1  # defer (low crew)
        elif s[6] < 0.5 and phase >= 2:
            curriculum_action = 3  # outsource (no parts)

        # High failure risk with urgency -> expedite
        if s[1] > 0.4 and s[7] > 0.7 and phase >= 3:
            curriculum_action = 2  # expedite

        phase_discount = {1: 1.0, 2: 0.9, 3: 0.8}.get(phase, 0.8)
        reward_map = {0: 0.8, 1: 0.5, 2: 0.6, 3: 0.5}
        reward = reward_map.get(curriculum_action, 0.5) * phase_discount

        return curriculum_action, reward

    def _phase3_disruption(self):
        """Phase 3: Disruption scenarios where heuristics fail.

        - capacity_constraint: Machine degrading fast (high failure prob +
          high production load).  Heuristic defers maintenance during peak;
          TRM should expedite to prevent catastrophic failure.
        - demand_spike: Production surge needs all machines running.
          Heuristic schedules routine PM; TRM should defer non-critical PM.
        - supply_disruption: Spare parts unavailable.  Heuristic schedules;
          TRM should outsource or defer until parts arrive.
        - seasonal_shift: Off-peak approaching.  Heuristic maintains regular
          schedule; TRM should schedule PM during low-demand window.
        """
        disruption = _pick_disruption()
        s = self._mixed_state()

        # --- Apply disruption ---
        if disruption == "capacity_constraint":
            s[0] = np.random.uniform(0.15, 0.35)  # severely degraded health
            s[1] = np.random.uniform(0.5, 0.8)    # high failure probability
            s[3] = np.random.uniform(0.7, 1.0)    # high production load
            s[11] = np.random.uniform(0.7, 1.0)   # critical asset
        elif disruption == "demand_spike":
            s[3] = np.random.uniform(0.8, 1.0)    # peak production
            s[7] = np.random.uniform(0.7, 1.0)    # high order urgency
            s[0] = np.random.uniform(0.5, 0.75)   # OK health — not urgent
            s[1] = np.random.uniform(0.05, 0.2)   # low failure prob
        elif disruption == "supply_disruption":
            s[6] = 0.0                            # no spare parts
            s[5] = np.random.uniform(0.1, 0.4)   # limited crew
            s[0] = np.random.uniform(0.3, 0.5)   # moderate health
        elif disruption == "seasonal_shift":
            s[3] = np.random.uniform(0.0, 0.2)   # low production (off-peak)
            s[7] = np.random.uniform(0.0, 0.2)   # low urgency
            s[0] = np.random.uniform(0.4, 0.7)   # health needs attention
            s[10] = np.random.uniform(0.6, 0.9)  # long since last PM
        else:
            s[0] = np.random.uniform(0.3, 0.6)
            s[1] = np.random.uniform(0.2, 0.5)
            s[3] = np.random.uniform(0.6, 1.0)
            s[7] = np.random.uniform(0.5, 0.9)

        # --- Compute heuristic baseline ---
        h_act, _ = self._compute_maint_decision(s, 3)

        # --- Override with disruption-aware corrective label ---
        if disruption == "capacity_constraint":
            act, rew = 2, 0.85  # expedite — prevent failure
        elif disruption == "demand_spike":
            if s[11] < 0.5:
                act, rew = 1, 0.75  # defer non-critical PM
            else:
                act, rew = 0, 0.70  # schedule critical — risk too high
        elif disruption == "supply_disruption":
            if s[9] > 0.5:
                act, rew = 3, 0.70  # outsource
            else:
                act, rew = 1, 0.65  # defer — no parts, no outsource
        elif disruption == "seasonal_shift":
            act, rew = 0, 0.85  # schedule during off-peak window
        else:
            act, rew = h_act, 0.5 * 0.8

        return s, act, rew

    def _simple_state(self):
        return np.array([
            np.random.uniform(0.7, 0.95),  # [0] asset_health
            np.random.uniform(0.0, 0.1),   # [1] failure_probability
            np.random.uniform(0.3, 0.7),   # [2] days_to_planned
            np.random.uniform(0.1, 0.3),   # [3] production_impact
            np.random.uniform(0.1, 0.3),   # [4] maintenance_duration
            np.random.uniform(0.7, 1.0),   # [5] crew_available
            1.0,                           # [6] parts_available
            np.random.uniform(0.1, 0.4),   # [7] order_urgency
            np.random.uniform(0.1, 0.3),   # [8] overtime_cost
            np.random.uniform(0.5, 0.9),   # [9] outsource_available
            np.random.uniform(0.3, 0.6),   # [10] last_maintenance_days
            np.random.uniform(0.3, 0.7),   # [11] criticality
            np.random.uniform(0.0, 0.2),   # [12] schedule_backlog
            np.random.uniform(0.1, 0.3),   # [13] maintenance_cost
        ], dtype=np.float32)

    def _mixed_state(self):
        s = self._simple_state()
        s[3] = np.random.uniform(0.3, 0.7)  # higher production impact
        s[5] = np.random.choice([0.3, 0.8], p=[0.3, 0.7])  # sometimes low crew
        s[6] = np.random.choice([0.0, 1.0], p=[0.3, 0.7])  # sometimes no parts
        return s


# ---------------------------------------------------------------------------
# Subcontracting Curriculum
# ---------------------------------------------------------------------------

class SubcontractingCurriculum(TRMCurriculumBase):
    """Curriculum for Subcontracting routing decisions.

    State: [required_qty_norm, internal_capacity_pct,
            internal_cost_norm, internal_lead_time_norm,
            internal_quality_yield, external_cost_norm,
            external_lead_time_norm, external_quality_score,
            external_on_time_score, is_critical_product,
            has_special_tooling, ip_sensitivity,
            current_external_pct, vendor_reject_rate,
            demand_urgency, backlog_norm]

    Actions: 0=keep_internal, 1=route_external, 2=split, 3=change_vendor
    """

    @property
    def state_dim(self) -> int:
        return SUBCONTRACTING_STATE_DIM

    @property
    def trm_type(self) -> str:
        return "subcontracting"

    def generate(self, phase: int, num_samples: int) -> CurriculumData:
        n = num_samples
        states = np.zeros((n, self.state_dim), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            if phase == 1:
                states[i] = self._simple_state()
                actions[i], rewards[i] = self._compute_sub_decision(states[i], phase)
            elif phase == 2:
                states[i] = self._mixed_state()
                actions[i], rewards[i] = self._compute_sub_decision(states[i], phase)
            else:
                states[i], actions[i], rewards[i] = self._phase3_disruption()

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=np.zeros((n, 1), dtype=np.float32),
            rewards=rewards,
            next_state_vectors=states * 0.95,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _compute_sub_decision(self, s, phase):
        """Build SubcontractingState from normalised state vector and call heuristic."""
        qty_needed = s[0] * 500.0
        internal_capacity = s[1] * 500.0
        unit_cost_base = 50.0

        sub_state = SubcontractingState(
            product_id="CURRICULUM",
            site_id="CURRICULUM",
            quantity_needed=qty_needed,
            internal_capacity_available=internal_capacity,
            internal_cost_per_unit=s[2] * unit_cost_base,
            external_cost_per_unit=s[5] * unit_cost_base,
            external_lead_time_days=s[6] * 30.0,
            internal_lead_time_days=s[3] * 30.0,
            quality_risk_external=float(1.0 - s[7]),
        )
        decision = compute_decision("subcontracting", sub_state, self.erp_params)

        curriculum_action = _SUB_ACTION_MAP.get(decision.action, 0)

        # Handle vendor reject rate -> change_vendor
        if s[13] > 0.1 and curriculum_action == 1 and phase >= 3:
            curriculum_action = 3  # change vendor (bad external quality)

        phase_discount = {1: 1.0, 2: 0.9, 3: 0.8}.get(phase, 0.8)
        reward_map = {0: 0.8, 1: 0.7, 2: 0.7, 3: 0.4}
        reward = reward_map.get(curriculum_action, 0.5) * phase_discount

        return curriculum_action, reward

    def _phase3_disruption(self):
        """Phase 3: Disruption scenarios where heuristics fail.

        - capacity_constraint: Internal capacity collapses (breakdown).
          Heuristic keeps internal; TRM should route external or split.
        - demand_spike: Urgent surge requires all capacity.
          Heuristic treats independently; TRM should split to parallelize.
        - supply_disruption: External vendor quality crashes.
          Heuristic continues routing; TRM should change vendor or keep internal.
        - cross_product_interaction: Multiple products competing for
          same internal capacity.  Heuristic doesn't coordinate;
          TRM should externalize low-value to free internal for critical.
        """
        disruption = _pick_disruption()
        s = self._mixed_state()

        # --- Apply disruption ---
        if disruption == "capacity_constraint":
            s[1] = np.random.uniform(0.0, 0.15)   # near-zero internal capacity
            s[14] = np.random.uniform(0.5, 0.9)   # moderate urgency
        elif disruption == "demand_spike":
            s[0] = np.random.uniform(0.6, 1.0)    # large qty needed
            s[14] = np.random.uniform(0.7, 1.0)   # high urgency
            s[15] = np.random.uniform(0.4, 0.8)   # growing backlog
        elif disruption == "supply_disruption":
            s[7] = np.random.uniform(0.4, 0.65)   # external quality crashed
            s[8] = np.random.uniform(0.4, 0.65)   # external on-time crashed
            s[13] = np.random.uniform(0.15, 0.3)  # high vendor reject rate
        elif disruption == "cross_product_interaction":
            s[1] = np.random.uniform(0.2, 0.4)    # limited internal
            s[9] = 1.0                             # critical product
            s[0] = np.random.uniform(0.4, 0.7)    # moderate qty
        else:
            s[1] = np.random.uniform(0.1, 0.4)
            s[14] = np.random.uniform(0.6, 1.0)
            s[15] = np.random.uniform(0.3, 0.8)

        # --- Compute heuristic baseline ---
        h_act, _ = self._compute_sub_decision(s, 3)

        # --- Override with disruption-aware corrective label ---
        if disruption == "capacity_constraint":
            if s[7] > 0.7:
                act, rew = 1, 0.80  # route_external (good vendor)
            else:
                act, rew = 2, 0.70  # split — hedge
        elif disruption == "demand_spike":
            act, rew = 2, 0.80  # split to parallelize delivery
        elif disruption == "supply_disruption":
            if s[1] > 0.3:
                act, rew = 0, 0.80  # keep_internal
            else:
                act, rew = 3, 0.65  # change_vendor
        elif disruption == "cross_product_interaction":
            if s[9] > 0.5:
                act, rew = 0, 0.80  # keep critical internal
            else:
                act, rew = 1, 0.70  # route non-critical external
        else:
            act, rew = h_act, 0.5 * 0.8

        return s, act, rew

    def _simple_state(self):
        return np.array([
            np.random.uniform(0.1, 0.4),   # required_qty
            np.random.uniform(0.5, 0.8),   # internal_capacity
            np.random.uniform(0.3, 0.6),   # internal_cost
            np.random.uniform(0.2, 0.5),   # internal_lead_time
            np.random.uniform(0.95, 0.99), # internal_quality
            np.random.uniform(0.4, 0.7),   # external_cost
            np.random.uniform(0.3, 0.6),   # external_lead_time
            np.random.uniform(0.85, 0.95), # external_quality
            np.random.uniform(0.85, 0.95), # external_on_time
            0.0,                           # is_critical
            0.0,                           # has_special_tooling
            np.random.uniform(0.0, 0.3),   # ip_sensitivity
            np.random.uniform(0.0, 0.2),   # current_external_pct
            np.random.uniform(0.01, 0.05), # vendor_reject_rate
            np.random.uniform(0.1, 0.4),   # demand_urgency
            np.random.uniform(0.0, 0.2),   # backlog
        ], dtype=np.float32)

    def _mixed_state(self):
        s = self._simple_state()
        s[1] = np.random.uniform(0.3, 0.6)  # lower internal capacity
        s[9] = np.random.choice([0.0, 1.0], p=[0.7, 0.3])  # sometimes critical
        s[14] = np.random.uniform(0.3, 0.7)
        return s


# ---------------------------------------------------------------------------
# Forecast Adjustment Curriculum
# ---------------------------------------------------------------------------

class ForecastAdjustmentCurriculum(TRMCurriculumBase):
    """Curriculum for Forecast adjustment decisions.

    State (18 floats, matches ForecastAdjustmentTRMModel):
        [0] signal_strength (0-1)      [1] signal_direction (-1 to 1)
        [2] signal_confidence (0-1)    [3] current_forecast (norm)
        [4] forecast_error_recent (norm)  [5] demand_trend (-1 to 1)
        [6] seasonality_index (norm)   [7] days_to_horizon (norm)
        [8] inventory_position (norm)  [9] backlog_rate (0-1)
        [10] customer_order_coverage (0-1)  [11] market_indicator (norm)
        [12] news_sentiment (-1 to 1)  [13] price_signal (norm)
        [14] competitor_signal (norm)  [15] historical_accuracy (0-1)
        [16] adjustment_magnitude (norm)  [17] safety_factor (0-1)

    Actions: 0=increase_high, 1=increase_low, 2=hold,
             3=decrease_low, 4=decrease_high
    """

    @property
    def state_dim(self) -> int:
        return FORECAST_ADJ_STATE_DIM

    @property
    def trm_type(self) -> str:
        return "forecast_adjustment"

    def generate(self, phase: int, num_samples: int) -> CurriculumData:
        n = num_samples
        states = np.zeros((n, self.state_dim), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            if phase == 1:
                states[i] = self._simple_state()
                actions[i], rewards[i] = self._compute_fa_decision(states[i], phase)
            elif phase == 2:
                states[i] = self._mixed_state()
                actions[i], rewards[i] = self._compute_fa_decision(states[i], phase)
            else:
                states[i], actions[i], rewards[i] = self._phase3_disruption()

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=np.zeros((n, 1), dtype=np.float32),
            rewards=rewards,
            next_state_vectors=states * 0.95,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _compute_fa_decision(self, s, phase):
        """Build ForecastAdjustmentState from normalised state vector and call heuristic."""
        # Map signal direction from continuous to categorical
        if s[1] > 0.3:
            direction_str = "increase"
        elif s[1] < -0.3:
            direction_str = "decrease"
        else:
            direction_str = "unchanged"

        signal_types = ["email", "voice", "market_intel", "demand_sensing"]
        signal_type = signal_types[np.random.randint(0, len(signal_types))]

        current_forecast = max(1.0, s[3] * 1000.0)

        fa_state = ForecastAdjustmentState(
            product_id="CURRICULUM",
            site_id="CURRICULUM",
            current_forecast=current_forecast,
            signal_type=signal_type,
            signal_direction=direction_str,
            signal_magnitude_pct=float(s[16] * 50.0),  # up to 50% adjustment
            signal_confidence=float(s[2]),
            forecast_error_recent=float(s[4]),
            demand_cv=float(abs(s[5]) + 0.1),
        )
        decision = compute_decision("forecast_adjustment", fa_state, self.erp_params)

        # Base mapping from heuristic
        base_action = _FA_ACTION_MAP.get(decision.action, 2)

        # Refine: distinguish high vs low magnitude
        curriculum_action = base_action
        if base_action == 1 and s[16] > 0.1:
            curriculum_action = 0  # increase_high
        elif base_action == 3 and s[16] > 0.1:
            curriculum_action = 4  # decrease_high

        # Low confidence -> hold regardless
        if s[0] < 0.4 and phase >= 3:
            curriculum_action = 2
        if s[15] < 0.5 and phase >= 3:
            curriculum_action = 2

        phase_discount = {1: 1.0, 2: 0.9, 3: 0.8}.get(phase, 0.8)
        reward_map = {0: 0.7, 1: 0.8, 2: 0.6, 3: 0.8, 4: 0.7}
        reward = reward_map.get(curriculum_action, 0.5) * phase_discount

        return curriculum_action, reward

    def _phase3_disruption(self):
        """Phase 3: Disruption scenarios where heuristics fail.

        - demand_spike: Strong increase signal + multiple confirming sources.
          Heuristic caps adjustment; TRM should increase_high.
        - supply_disruption: Supplier signals supply reduction.  Heuristic
          holds forecast; TRM should decrease to avoid over-ordering into
          constrained supply.
        - seasonal_shift: Seasonality index diverging from historical.
          Heuristic uses static seasonal; TRM should adjust based on
          leading indicators.
        - bullwhip_amplification: Contradictory signals (email up, market
          down).  Heuristic follows strongest; TRM should hold and wait.
        """
        disruption = _pick_disruption()
        s = self._mixed_state()

        # --- Apply disruption ---
        if disruption == "demand_spike":
            s[0] = np.random.uniform(0.8, 1.0)    # strong signal
            s[1] = 1.0                             # direction: increase
            s[2] = np.random.uniform(0.7, 0.95)   # high confidence
            s[11] = np.random.uniform(0.3, 0.8)   # confirming market indicator
            s[12] = np.random.uniform(0.3, 0.8)   # confirming news
            s[16] = np.random.uniform(0.2, 0.4)   # moderate magnitude
        elif disruption == "supply_disruption":
            s[1] = -1.0                            # direction: decrease
            s[0] = np.random.uniform(0.5, 0.8)    # moderate signal
            s[2] = np.random.uniform(0.5, 0.8)    # moderate confidence
            s[9] = np.random.uniform(0.2, 0.5)    # growing backlog
            s[8] = np.random.uniform(0.2, 0.4)    # low inventory
        elif disruption == "seasonal_shift":
            s[6] = np.random.choice([0.5, 1.5])   # abnormal seasonality
            s[5] = np.random.uniform(0.1, 0.3) if s[6] > 1 else np.random.uniform(-0.3, -0.1)
            s[4] = np.random.uniform(0.2, 0.4)    # forecast error rising
            s[15] = np.random.uniform(0.5, 0.7)   # declining accuracy
        elif disruption == "bullwhip_amplification":
            s[1] = np.random.uniform(-0.2, 0.2)   # ambiguous direction
            s[11] = np.random.uniform(-0.5, -0.2)  # market says down
            s[12] = np.random.uniform(0.2, 0.5)   # news says up
            s[0] = np.random.uniform(0.3, 0.6)    # weak signal
            s[2] = np.random.uniform(0.3, 0.6)    # low confidence
        else:
            s[0] = np.random.uniform(0.2, 0.6)
            s[4] = np.random.uniform(0.2, 0.5)
            s[5] = np.random.uniform(-0.2, 0.2)

        # --- Compute heuristic baseline ---
        h_act, _ = self._compute_fa_decision(s, 3)

        # --- Override with disruption-aware corrective label ---
        if disruption == "demand_spike":
            act, rew = 0, 0.85  # increase_high — strong confirmed signal
        elif disruption == "supply_disruption":
            act, rew = 4, 0.75  # decrease_high — reduce forecast into constrained supply
        elif disruption == "seasonal_shift":
            if s[6] > 1.2:
                act, rew = 0, 0.80  # increase_high — entering peak season
            elif s[6] < 0.8:
                act, rew = 4, 0.80  # decrease_high — entering trough
            else:
                act, rew = 2, 0.65  # hold — ambiguous
        elif disruption == "bullwhip_amplification":
            act, rew = 2, 0.80  # hold — contradictory signals, wait for clarity
        else:
            act, rew = h_act, 0.6 * 0.8

        return s, act, rew

    def _simple_state(self):
        direction = np.random.choice([-1.0, 0.0, 1.0])
        return np.array([
            np.random.uniform(0.7, 0.95),  # [0] signal_strength
            direction,                     # [1] signal_direction
            np.random.uniform(0.7, 0.95),  # [2] signal_confidence
            np.random.uniform(0.3, 0.7),   # [3] current_forecast
            np.random.uniform(0.05, 0.15), # [4] forecast_error_recent
            np.random.uniform(-0.05, 0.05),# [5] demand_trend
            np.random.uniform(0.9, 1.1),   # [6] seasonality_index
            np.random.uniform(0.2, 0.5),   # [7] days_to_horizon
            np.random.uniform(0.4, 0.7),   # [8] inventory_position
            np.random.uniform(0.0, 0.1),   # [9] backlog_rate
            np.random.uniform(0.6, 0.9),   # [10] customer_order_coverage
            np.random.uniform(-0.1, 0.1),  # [11] market_indicator
            np.random.uniform(-0.1, 0.1),  # [12] news_sentiment
            np.random.uniform(-0.1, 0.1),  # [13] price_signal
            np.random.uniform(-0.1, 0.1),  # [14] competitor_signal
            np.random.uniform(0.8, 0.95),  # [15] historical_accuracy
            np.random.uniform(0.05, 0.15), # [16] adjustment_magnitude
            np.random.uniform(0.3, 0.6),   # [17] safety_factor
        ], dtype=np.float32)

    def _mixed_state(self):
        s = self._simple_state()
        s[0] = np.random.uniform(0.4, 0.8)  # lower signal strength
        s[2] = np.random.uniform(0.4, 0.8)  # lower confidence
        s[4] = np.random.uniform(0.1, 0.3)  # higher forecast error
        return s


# ---------------------------------------------------------------------------
# Inventory Buffer Curriculum
# ---------------------------------------------------------------------------

class InventoryBufferCurriculum(TRMCurriculumBase):
    """Curriculum for Inventory Buffer adjustment decisions.

    State: [current_ss_norm, demand_mean_norm, demand_cv,
            lead_time_mean_norm, lead_time_cv, service_level_target,
            actual_service_level, stockout_frequency,
            excess_inventory_cost_norm, holding_cost_norm,
            forecast_error_pct, atp_shortage_signal,
            demand_trend, seasonality_index]

    Actions: 0=maintain, 1=increase_small, 2=increase_large,
             3=decrease_small, 4=decrease_large
    """

    @property
    def state_dim(self) -> int:
        return INVENTORY_BUFFER_STATE_DIM

    @property
    def trm_type(self) -> str:
        return "inventory_buffer"

    def generate(self, phase: int, num_samples: int) -> CurriculumData:
        n = num_samples
        states = np.zeros((n, self.state_dim), dtype=np.float32)
        actions = np.zeros(n, dtype=np.int64)
        rewards = np.zeros(n, dtype=np.float32)

        for i in range(n):
            if phase == 1:
                states[i] = self._simple_state()
                actions[i], rewards[i] = self._compute_ib_decision(states[i], phase)
            elif phase == 2:
                states[i] = self._mixed_state()
                actions[i], rewards[i] = self._compute_ib_decision(states[i], phase)
            else:
                states[i], actions[i], rewards[i] = self._phase3_disruption()

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=np.zeros((n, 1), dtype=np.float32),
            rewards=rewards,
            next_state_vectors=states * 0.95,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

    def _compute_ib_decision(self, s, phase):
        """Build InventoryBufferState from normalised state vector and call heuristic."""
        avg_demand = max(1.0, s[1] * 200.0)
        current_ss = s[0] * avg_demand * 3.0  # denormalise
        lead_time = max(1.0, s[3] * 30.0)

        ib_state = InventoryBufferState(
            product_id="CURRICULUM",
            site_id="CURRICULUM",
            current_safety_stock=current_ss,
            avg_daily_demand=avg_demand,
            demand_cv=float(s[2]),
            lead_time_days=lead_time,
            lead_time_cv=float(s[4]),
            service_level_target=float(s[5]),
            recent_stockout_count=int(s[7] * 20),
            recent_excess_days=int(s[8] * 30),
            holding_cost_per_unit=float(s[9] * 10.0),
            stockout_cost_per_unit=float(s[9] * 50.0),
        )
        decision = compute_decision("inventory_buffer", ib_state, self.erp_params)

        # Base mapping from heuristic
        base_action = _IB_ACTION_MAP.get(decision.action, 0)

        # Refine: distinguish small vs large adjustments
        curriculum_action = base_action
        if decision.action == 1:
            # Increase: check magnitude
            if current_ss > 0 and decision.quantity > current_ss * 1.3:
                curriculum_action = 2  # increase_large
            else:
                curriculum_action = 1  # increase_small
        elif decision.action == 2:
            # Decrease: check magnitude
            if current_ss > 0 and decision.quantity < current_ss * 0.7:
                curriculum_action = 4  # decrease_large
            else:
                curriculum_action = 3  # decrease_small

        # Override for stockout frequency
        if s[7] > 0.15 and phase >= 3:
            curriculum_action = 2  # increase_large (frequent stockouts)
        elif s[8] > 0.2 and s[7] < 0.05 and phase >= 3:
            curriculum_action = 4  # decrease_large (excess with no stockouts)

        phase_discount = {1: 1.0, 2: 0.9, 3: 0.8}.get(phase, 0.8)
        reward_map = {0: 0.8, 1: 0.7, 2: 0.6, 3: 0.7, 4: 0.4}
        reward = reward_map.get(curriculum_action, 0.5) * phase_discount

        return curriculum_action, reward

    def _phase3_disruption(self):
        """Phase 3: Disruption scenarios where heuristics fail.

        - demand_spike: Sudden demand surge.  Heuristic safety stock formula
          uses historical average; TRM should increase_large immediately.
        - supply_disruption: Lead times double/triple.  Heuristic uses fixed
          lead time; TRM should increase_large to cover extended lead time.
        - seasonal_shift: Entering peak season.  Heuristic uses static SS;
          TRM should pre-increase buffer ahead of the shift.
        - bullwhip_amplification: High demand CV with excess inventory.
          Heuristic keeps increasing; TRM should maintain or decrease.
        - capacity_constraint: Upstream bottleneck reduces supply rate.
          Heuristic doesn't see capacity; TRM should increase buffer
          to absorb supply variability.
        """
        disruption = _pick_disruption()
        s = self._mixed_state()

        # --- Apply disruption ---
        if disruption == "demand_spike":
            s[2] = np.random.uniform(0.4, 0.8)    # very high demand CV
            s[7] = np.random.uniform(0.15, 0.35)  # frequent stockouts
            s[11] = np.random.uniform(0.5, 1.0)   # ATP shortage
            s[12] = np.random.uniform(0.05, 0.15)  # demand trending up
            s[6] = np.random.uniform(0.80, 0.88)  # service level dropping
        elif disruption == "supply_disruption":
            s[3] = np.random.uniform(0.5, 0.9)    # extended lead time
            s[4] = np.random.uniform(0.3, 0.6)    # high lead time CV
            s[7] = np.random.uniform(0.10, 0.25)  # growing stockouts
            s[6] = np.random.uniform(0.82, 0.90)  # service declining
        elif disruption == "seasonal_shift":
            s[13] = np.random.choice([0.6, 1.5])  # abnormal seasonality
            s[12] = np.random.uniform(0.05, 0.15) if s[13] > 1 else np.random.uniform(-0.15, -0.05)
            s[10] = np.random.uniform(0.15, 0.35) # forecast error rising
        elif disruption == "bullwhip_amplification":
            s[2] = np.random.uniform(0.4, 0.7)    # high demand CV
            s[8] = np.random.uniform(0.25, 0.5)   # excess inventory cost
            s[7] = np.random.uniform(0.0, 0.03)   # few stockouts (over-buffered)
            s[6] = np.random.uniform(0.96, 0.99)  # high service (over-served)
        elif disruption == "capacity_constraint":
            s[4] = np.random.uniform(0.2, 0.45)   # variable lead time
            s[11] = np.random.uniform(0.3, 0.7)   # ATP shortages
            s[7] = np.random.uniform(0.08, 0.18)  # some stockouts
        else:
            s[2] = np.random.uniform(0.25, 0.5)
            s[4] = np.random.uniform(0.15, 0.35)
            s[6] = np.random.uniform(0.80, 0.92)
            s[7] = np.random.uniform(0.1, 0.25)
            s[11] = np.random.uniform(0.4, 1.0)

        # --- Compute heuristic baseline ---
        h_act, _ = self._compute_ib_decision(s, 3)

        # --- Override with disruption-aware corrective label ---
        if disruption == "demand_spike":
            act, rew = 2, 0.85  # increase_large — cover the surge
        elif disruption == "supply_disruption":
            act, rew = 2, 0.80  # increase_large — cover extended lead time
        elif disruption == "seasonal_shift":
            if s[13] > 1.2:
                act, rew = 2, 0.80  # increase_large — peak coming
            elif s[13] < 0.8:
                act, rew = 4, 0.75  # decrease_large — trough, release capital
            else:
                act, rew = 0, 0.65  # maintain
        elif disruption == "bullwhip_amplification":
            act, rew = 4, 0.80  # decrease_large — over-buffered, dampen
        elif disruption == "capacity_constraint":
            act, rew = 1, 0.75  # increase_small — absorb supply variability
        else:
            act, rew = h_act, 0.5 * 0.8

        return s, act, rew

    def _simple_state(self):
        return np.array([
            np.random.uniform(0.3, 0.6),   # current_ss
            np.random.uniform(0.3, 0.6),   # demand_mean
            np.random.uniform(0.1, 0.25),  # demand_cv
            np.random.uniform(0.2, 0.4),   # lead_time_mean
            np.random.uniform(0.05, 0.15), # lead_time_cv
            0.95,                          # service_level_target
            np.random.uniform(0.93, 0.97), # actual_service_level
            np.random.uniform(0.0, 0.05),  # stockout_frequency
            np.random.uniform(0.05, 0.15), # excess_inv_cost
            np.random.uniform(0.05, 0.1),  # holding_cost
            np.random.uniform(0.05, 0.15), # forecast_error
            0.0,                           # atp_shortage_signal
            np.random.uniform(-0.02, 0.02),# demand_trend
            np.random.uniform(0.9, 1.1),   # seasonality
        ], dtype=np.float32)

    def _mixed_state(self):
        s = self._simple_state()
        s[6] = np.random.uniform(0.88, 0.96)  # variable service level
        s[7] = np.random.uniform(0.03, 0.12)  # more stockouts
        s[11] = np.random.uniform(0.0, 0.5)   # some ATP shortage
        return s


# ---------------------------------------------------------------------------
# Stochastic Curriculum — Monte Carlo from fitted distributions
# ---------------------------------------------------------------------------

class StochasticCurriculumWrapper:
    """Wraps any TRMCurriculumBase and replaces hand-crafted ranges with
    Monte Carlo samples from distributions fitted to actual DB data.

    Falls back to the underlying curriculum if no DB data is available.

    Usage (sync, typically called from provisioning or training scripts):
        from app.db.session import sync_session_factory
        db = sync_session_factory()
        wrapper = StochasticCurriculumWrapper(
            base_curriculum=MOExecutionCurriculum(sc_config),
            config_id=22,
            db=db,
        )
        data = wrapper.generate(phase=1, num_samples=1000)
    """

    def __init__(
        self,
        base_curriculum: TRMCurriculumBase,
        config_id: int,
        db=None,
        n_mc_draws: int = 1000,
    ):
        self.base = base_curriculum
        self.config_id = config_id
        self.db = db
        self.n_mc_draws = n_mc_draws
        self._fitted_params: Optional[dict] = None

    def _fit_distributions(self) -> dict:
        """Fit distributions to actual Forecast, InvLevel, and VendorLeadTime data."""
        if self._fitted_params is not None:
            return self._fitted_params

        if self.db is None:
            return {}

        fitted = {}
        try:
            from app.services.stochastic.distribution_fitter import DistributionFitter

            # Fit demand distribution from Forecast data
            from app.models.sc_entities import Forecast, InvLevel, VendorLeadTime
            from sqlalchemy import func as sqla_func

            forecasts = (
                self.db.query(Forecast.forecast_quantity)
                .filter(Forecast.config_id == self.config_id)
                .filter(Forecast.forecast_quantity > 0)
                .limit(5000)
                .all()
            )
            if len(forecasts) >= 30:
                demand_values = np.array([f[0] for f in forecasts], dtype=np.float64)
                fitter = DistributionFitter()
                result = fitter.fit(demand_values)
                if result and result.get("best_fit"):
                    fitted["demand"] = {
                        "distribution": result["best_fit"]["distribution"],
                        "params": result["best_fit"]["params"],
                        "mean": float(np.mean(demand_values)),
                        "std": float(np.std(demand_values)),
                    }

            # Fit inventory levels
            inv_levels = (
                self.db.query(InvLevel.on_hand_qty)
                .filter(InvLevel.config_id == self.config_id)
                .filter(InvLevel.on_hand_qty > 0)
                .limit(5000)
                .all()
            )
            if len(inv_levels) >= 30:
                inv_values = np.array([i[0] for i in inv_levels], dtype=np.float64)
                fitter = DistributionFitter()
                result = fitter.fit(inv_values)
                if result and result.get("best_fit"):
                    fitted["inventory"] = {
                        "distribution": result["best_fit"]["distribution"],
                        "params": result["best_fit"]["params"],
                        "mean": float(np.mean(inv_values)),
                        "std": float(np.std(inv_values)),
                    }

            # Fit lead time distribution
            lead_times = (
                self.db.query(VendorLeadTime.lead_time_days)
                .filter(VendorLeadTime.config_id == self.config_id)
                .filter(VendorLeadTime.lead_time_days > 0)
                .limit(5000)
                .all()
            )
            if len(lead_times) >= 10:
                lt_values = np.array([lt[0] for lt in lead_times], dtype=np.float64)
                fitter = DistributionFitter()
                result = fitter.fit(lt_values)
                if result and result.get("best_fit"):
                    fitted["lead_time"] = {
                        "distribution": result["best_fit"]["distribution"],
                        "params": result["best_fit"]["params"],
                        "mean": float(np.mean(lt_values)),
                        "std": float(np.std(lt_values)),
                    }

        except Exception:
            pass  # Fall back to base curriculum if DB access fails

        self._fitted_params = fitted
        return fitted

    def _sample_from_fitted(self, key: str, n: int) -> Optional[np.ndarray]:
        """Sample n values from a fitted distribution."""
        fitted = self._fit_distributions()
        if key not in fitted:
            return None

        try:
            from app.services.stochastic.distribution_fitter import DistributionFitter
            info = fitted[key]
            dist_name = info["distribution"]
            params = info["params"]

            # Use scipy to sample from fitted distribution
            import scipy.stats as stats
            dist_obj = getattr(stats, dist_name, None)
            if dist_obj is None:
                return None

            samples = dist_obj.rvs(*params, size=n)
            return np.maximum(samples, 0).astype(np.float32)  # Clip negative
        except Exception:
            return None

    def generate(self, phase: int, num_samples: int, multiplier: int = 1) -> CurriculumData:
        """Generate curriculum data using Monte Carlo samples from fitted distributions.

        For state dimensions that correspond to demand, inventory, or lead time,
        replaces the hand-crafted uniform ranges with samples from fitted
        distributions. Falls back to the base curriculum for any dimension where
        no fitted distribution is available.

        Args:
            phase: Curriculum sub-phase (1, 2, or 3).
            num_samples: Number of base samples per draw.
            multiplier: Number of independent Monte Carlo draws to generate.
                When multiplier > 1, generates M independent batches of
                num_samples each (with different random seeds for both the
                base curriculum AND the stochastic overlay), producing
                M × num_samples total samples. This is critical for data
                volume scaling (Stöckl 2021): overlaying noise on the same
                base samples does NOT produce truly independent training data.
                Each draw uses a different random seed to ensure distinct
                state-action trajectories.

        Returns:
            CurriculumData with (multiplier × num_samples) rows.
        """
        if multiplier <= 1:
            return self._generate_single(phase, num_samples)

        # Generate M independent batches and concatenate
        all_states = []
        all_act_disc = []
        all_act_cont = []
        all_rewards = []
        all_next_states = []
        all_is_expert = []
        all_dones = []

        for draw_idx in range(multiplier):
            # Set a unique seed per draw so base curriculum + stochastic overlay
            # produce genuinely different samples (not the same data M times)
            draw_seed = (draw_idx + 1) * 7919  # Prime multiplier for spread
            np.random.seed(draw_seed)

            data = self._generate_single(phase, num_samples)
            all_states.append(data.state_vectors)
            all_act_disc.append(data.action_discrete)
            all_act_cont.append(data.action_continuous)
            all_rewards.append(data.rewards)
            all_next_states.append(data.next_state_vectors)
            all_is_expert.append(data.is_expert)
            all_dones.append(data.dones)

        # Reset numpy RNG to avoid side effects
        np.random.seed(None)

        return CurriculumData(
            state_vectors=np.concatenate(all_states, axis=0),
            action_discrete=np.concatenate(all_act_disc, axis=0),
            action_continuous=np.concatenate(all_act_cont, axis=0),
            rewards=np.concatenate(all_rewards, axis=0),
            next_state_vectors=np.concatenate(all_next_states, axis=0),
            is_expert=np.concatenate(all_is_expert, axis=0),
            dones=np.concatenate(all_dones, axis=0),
        )

    def _generate_single(self, phase: int, num_samples: int) -> CurriculumData:
        """Generate a single batch of curriculum data with stochastic overlay."""
        # First generate from the base curriculum (hand-crafted)
        base_data = self.base.generate(phase, num_samples)

        # Try to overlay with stochastic samples
        fitted = self._fit_distributions()
        if not fitted:
            return base_data  # No DB data → use hand-crafted as-is

        # Sample from fitted distributions
        demand_samples = self._sample_from_fitted("demand", num_samples)
        inv_samples = self._sample_from_fitted("inventory", num_samples)
        lt_samples = self._sample_from_fitted("lead_time", num_samples)

        # Normalize samples to [0, 1] range for state vector injection
        def normalize(arr):
            if arr is None or len(arr) == 0:
                return None
            mn, mx = arr.min(), arr.max()
            if mx - mn < 1e-8:
                return np.full_like(arr, 0.5)
            return (arr - mn) / (mx - mn)

        norm_demand = normalize(demand_samples)
        norm_inv = normalize(inv_samples)
        norm_lt = normalize(lt_samples)

        # Inject normalized samples into appropriate state dimensions
        # The exact dimensions depend on the TRM type. We use a generic mapping
        # that works across all curricula: demand-like dims get demand samples,
        # inventory-like dims get inventory samples, lead-time dims get LT samples.
        trm_type = self.base.trm_type
        states = base_data.state_vectors.copy()

        # Generic injection based on common patterns across TRM state vectors
        # These map state index → fitted distribution key
        INJECTION_MAP = {
            "atp_executor": {2: "inventory", 3: "inventory", 5: "demand"},
            "inventory_rebalancing": {0: "inventory", 1: "inventory", 2: "demand"},
            "po_creation": {0: "inventory", 2: "demand", 4: "lead_time"},
            "order_tracking": {3: "lead_time"},
            "mo_execution": {2: "demand", 0: "inventory"},
            "to_execution": {0: "inventory", 2: "demand"},
            "quality_disposition": {},  # Quality is defect-rate driven, not demand
            "maintenance_scheduling": {},  # Asset-driven, not demand
            "subcontracting": {2: "demand"},
            "forecast_adjustment": {0: "demand"},
            "inventory_buffer": {0: "demand", 1: "inventory", 3: "lead_time"},
        }

        dim_map = INJECTION_MAP.get(trm_type, {})
        sample_arrays = {
            "demand": norm_demand,
            "inventory": norm_inv,
            "lead_time": norm_lt,
        }

        for dim_idx, dist_key in dim_map.items():
            samples = sample_arrays.get(dist_key)
            if samples is not None and dim_idx < states.shape[1]:
                states[:, dim_idx] = samples

        # Also inject into next_state_vectors with slight perturbation
        next_states = base_data.next_state_vectors.copy()
        for dim_idx, dist_key in dim_map.items():
            samples = sample_arrays.get(dist_key)
            if samples is not None and dim_idx < next_states.shape[1]:
                # Add small noise to simulate state transition
                noise = np.random.normal(0, 0.05, size=num_samples).astype(np.float32)
                next_states[:, dim_idx] = np.clip(samples + noise, 0, 1)

        return CurriculumData(
            state_vectors=states,
            action_discrete=base_data.action_discrete,
            action_continuous=base_data.action_continuous,
            rewards=base_data.rewards,
            next_state_vectors=next_states,
            is_expert=base_data.is_expert,
            dones=base_data.dones,
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

HIVE_CURRICULUM_REGISTRY = {
    # Canonical names (match TRM service types)
    "mo_execution": MOExecutionCurriculum,
    "to_execution": TOExecutionCurriculum,
    "quality_disposition": QualityDispositionCurriculum,
    "maintenance_scheduling": MaintenanceSchedulingCurriculum,
    "subcontracting": SubcontractingCurriculum,
    "forecast_adjustment": ForecastAdjustmentCurriculum,
    "inventory_buffer": InventoryBufferCurriculum,
    # Short aliases for backward compatibility
    "quality": QualityDispositionCurriculum,
    "maintenance": MaintenanceSchedulingCurriculum,
    "forecast_adj": ForecastAdjustmentCurriculum,
}


def generate_stochastic_curriculum(
    trm_type: str,
    config_id: int,
    phase: int = 1,
    num_samples: int = 50_000,
    multiplier: int = 1,
    db=None,
    seed: Optional[int] = None,
) -> CurriculumData:
    """Convenience function to generate Monte Carlo curriculum for any TRM type.

    Looks up the base curriculum class, wraps it with StochasticCurriculumWrapper,
    and generates samples from fitted distributions.

    Falls back to hand-crafted curriculum if DB data is insufficient.

    Args:
        trm_type: Canonical TRM type name (e.g. "atp_executor").
        config_id: Supply chain config ID for distribution fitting.
        phase: Curriculum sub-phase (1, 2, or 3).
        num_samples: Samples per draw (default 50K per Stöckl 2021 guidance).
        multiplier: Independent MC draws — total samples = multiplier × num_samples.
            Use multiplier=3 for 150K total, matching the "medium" data regime.
        db: Optional sync DB session for distribution fitting.
        seed: Optional random seed for the base curriculum.
    """
    from .trm_curriculum import CURRICULUM_REGISTRY

    # Try hive registry first, then main registry
    curriculum_cls = HIVE_CURRICULUM_REGISTRY.get(trm_type) or CURRICULUM_REGISTRY.get(trm_type)
    if curriculum_cls is None:
        raise ValueError(f"No curriculum registered for TRM type: {trm_type}")

    sc_config = SCConfigData()
    base = curriculum_cls(sc_config, seed=seed)
    wrapper = StochasticCurriculumWrapper(
        base_curriculum=base,
        config_id=config_id,
        db=db,
    )
    return wrapper.generate(phase, num_samples, multiplier=multiplier)
