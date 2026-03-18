"""
Hive Curriculum Generators — 7 remaining TRM curricula

Follows the same 3-phase pattern as the existing 4 curricula in trm_curriculum.py:
  Phase 1: Simple, stable scenarios (easy decisions)
  Phase 2: Mixed complexity (trade-offs, multiple factors)
  Phase 3: Stress/disruption scenarios (chaos, cascading failures)

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

from .trm_curriculum import TRMCurriculumBase, CurriculumData, SCConfigData


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
                actions[i] = 0  # release
                rewards[i] = 1.0
            elif phase == 2:
                states[i] = self._phase2_state()
                actions[i], rewards[i] = self._phase2_decision(states[i])
            else:
                states[i] = self._phase3_state()
                actions[i], rewards[i] = self._phase3_decision(states[i])

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=np.zeros((n, 1), dtype=np.float32),
            rewards=rewards,
            next_state_vectors=states * 0.95,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

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

    def _phase3_state(self):
        s = self._phase2_state()
        s[1] = np.random.uniform(0.0, 0.2)   # near-zero capacity
        s[3] = np.random.uniform(0.6, 1.0)   # high urgency
        s[7] = np.random.uniform(0.7, 0.88)  # lower quality rate
        s[9] = np.random.uniform(0.3, 0.8)   # maintenance due
        return s

    def _phase2_decision(self, s):
        if s[5] < 0.5:  # no material
            return 1, 0.5  # defer
        if s[1] < 0.25:  # very low capacity
            return 2, 0.7  # split
        return 0, 0.9  # release

    def _phase3_decision(self, s):
        if s[7] < 0.8:  # poor quality rate
            return 1, 0.3  # defer
        if s[9] > 0.5 and s[3] < 0.7:
            return 1, 0.4  # defer for maintenance
        if s[3] > 0.8:
            return 3, 0.6  # expedite
        if s[1] < 0.1:
            return 2, 0.5  # split
        return 0, 0.7  # release


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
                actions[i] = 0
                rewards[i] = 1.0
            elif phase == 2:
                states[i] = self._mixed_state()
                actions[i], rewards[i] = self._mixed_decision(states[i])
            else:
                states[i] = self._stress_state()
                actions[i], rewards[i] = self._stress_decision(states[i])

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=np.zeros((n, 1), dtype=np.float32),
            rewards=rewards,
            next_state_vectors=states * 0.95,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

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

    def _stress_state(self):
        s = self._mixed_state()
        s[1] = np.random.uniform(0.05, 0.2)  # low dest inventory
        s[6] = np.random.uniform(0.6, 1.0)   # high urgency
        s[10] = np.random.uniform(0.5, 0.85) # lower reliability
        s[13] = np.random.uniform(0.3, 0.8)  # high dest backlog
        return s

    def _mixed_decision(self, s):
        if s[8] > 0.5:
            return 2, 0.8  # consolidate
        if s[6] > 0.6:
            return 3, 0.7  # expedite
        return 0, 0.9  # release

    def _stress_decision(self, s):
        if s[1] < 0.1 and s[6] > 0.8:
            return 3, 0.6  # expedite critically
        if s[10] < 0.6:
            return 1, 0.5  # defer (unreliable route)
        if s[13] > 0.6:
            return 3, 0.5  # expedite (high backlog)
        return 0, 0.7  # release


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
                actions[i], rewards[i] = self._simple_decision(states[i])
            elif phase == 2:
                states[i] = self._mixed_state()
                actions[i], rewards[i] = self._mixed_decision(states[i])
            else:
                states[i] = self._stress_state()
                actions[i], rewards[i] = self._stress_decision(states[i])

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=np.zeros((n, 1), dtype=np.float32),
            rewards=rewards,
            next_state_vectors=states * 0.95,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

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

    def _stress_state(self):
        s = self._mixed_state()
        s[0] = np.random.uniform(0.05, 0.25)  # high defect rate
        s[1] = np.random.uniform(0.5, 1.0)    # high severity
        s[6] = np.random.uniform(0.6, 1.0)    # high order urgency
        s[8] = np.random.uniform(0.2, 0.5)    # low rework capacity
        return s

    def _simple_decision(self, s):
        if s[0] < 0.02:
            return 0, 1.0  # accept
        return 1, 0.8  # reject

    def _mixed_decision(self, s):
        if s[0] < 0.03 and s[1] < 0.3:
            return 0, 0.9  # accept minor
        if s[0] > 0.08:
            if s[4] < s[3] * 0.5:
                return 3, 0.6  # scrap (cheaper than rework)
            return 1, 0.7  # reject
        return 2, 0.7  # rework

    def _stress_decision(self, s):
        if s[6] > 0.8 and s[0] < 0.08:
            return 4, 0.4  # use_as_is (urgent order override)
        if s[1] > 0.8:
            return 3, 0.5  # scrap critical defects
        if s[0] > 0.1:
            return 1, 0.6  # reject
        return 2, 0.5  # rework


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
                actions[i] = 0
                rewards[i] = 0.9
            elif phase == 2:
                states[i] = self._mixed_state()
                actions[i], rewards[i] = self._mixed_decision(states[i])
            else:
                states[i] = self._stress_state()
                actions[i], rewards[i] = self._stress_decision(states[i])

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=np.zeros((n, 1), dtype=np.float32),
            rewards=rewards,
            next_state_vectors=states * 0.95,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

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

    def _stress_state(self):
        s = self._mixed_state()
        s[0] = np.random.uniform(0.3, 0.6)   # degraded health
        s[1] = np.random.uniform(0.2, 0.5)   # higher failure prob
        s[3] = np.random.uniform(0.6, 1.0)   # high production impact
        s[7] = np.random.uniform(0.5, 0.9)   # higher order urgency
        return s

    def _mixed_decision(self, s):
        if s[5] < 0.5:  # low crew
            return 1, 0.6  # defer
        if s[6] < 0.5:  # no parts
            return 3, 0.5  # outsource
        if s[3] > 0.6:  # high production impact
            return 1, 0.5  # defer
        return 0, 0.8  # schedule

    def _stress_decision(self, s):
        if s[1] > 0.4:  # high failure risk
            if s[6] < 0.5:
                return 3, 0.4  # outsource urgently
            return 2, 0.6  # expedite
        if s[7] > 0.7:
            return 2, 0.5  # expedite
        if s[3] > 0.8:
            return 1, 0.3  # defer (risky)
        return 0, 0.6  # schedule


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
                actions[i] = 0  # keep internal
                rewards[i] = 0.9
            elif phase == 2:
                states[i] = self._mixed_state()
                actions[i], rewards[i] = self._mixed_decision(states[i])
            else:
                states[i] = self._stress_state()
                actions[i], rewards[i] = self._stress_decision(states[i])

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=np.zeros((n, 1), dtype=np.float32),
            rewards=rewards,
            next_state_vectors=states * 0.95,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

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

    def _stress_state(self):
        s = self._mixed_state()
        s[1] = np.random.uniform(0.1, 0.4)   # very low internal capacity
        s[14] = np.random.uniform(0.6, 1.0)  # high demand urgency
        s[15] = np.random.uniform(0.3, 0.8)  # high backlog
        return s

    def _mixed_decision(self, s):
        if s[1] < 0.4 and s[9] < 0.5:
            return 1, 0.7  # route external
        if s[1] < 0.6:
            return 2, 0.7  # split
        return 0, 0.8  # keep internal

    def _stress_decision(self, s):
        if s[9] > 0.5 and s[7] < 0.9:
            return 0, 0.5  # keep internal (critical product, bad vendor)
        if s[1] < 0.2:
            return 1, 0.5  # route external (no choice)
        if s[13] > 0.1:
            return 3, 0.4  # change vendor
        return 2, 0.6  # split


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
                actions[i], rewards[i] = self._simple_decision(states[i])
            elif phase == 2:
                states[i] = self._mixed_state()
                actions[i], rewards[i] = self._mixed_decision(states[i])
            else:
                states[i] = self._stress_state()
                actions[i], rewards[i] = self._stress_decision(states[i])

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=np.zeros((n, 1), dtype=np.float32),
            rewards=rewards,
            next_state_vectors=states * 0.95,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

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

    def _stress_state(self):
        s = self._mixed_state()
        s[0] = np.random.uniform(0.2, 0.6)  # low signal strength
        s[4] = np.random.uniform(0.2, 0.5)  # high forecast error
        s[5] = np.random.uniform(-0.2, 0.2) # strong trend
        return s

    def _simple_decision(self, s):
        if s[0] > 0.8 and s[2] > 0.8:
            if s[1] > 0.5:
                return 1, 0.9  # increase_low
            elif s[1] < -0.5:
                return 3, 0.9  # decrease_low
        return 2, 0.7  # hold

    def _mixed_decision(self, s):
        if s[0] > 0.6 and s[2] > 0.6:
            if s[1] > 0.5:
                if s[16] > 0.1:
                    return 0, 0.7  # increase_high
                return 1, 0.7  # increase_low
            elif s[1] < -0.5:
                if s[16] > 0.1:
                    return 4, 0.7  # decrease_high
                return 3, 0.7  # decrease_low
        return 2, 0.6  # hold (uncertain)

    def _stress_decision(self, s):
        if s[0] < 0.4:
            return 2, 0.5  # too uncertain, hold
        if s[15] < 0.5:
            return 2, 0.4  # low historical accuracy, hold
        if s[1] > 0.5:
            return 1, 0.5  # increase_low only
        elif s[1] < -0.5:
            return 3, 0.5  # decrease_low only
        return 2, 0.5


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
                actions[i] = 0  # maintain
                rewards[i] = 0.8
            elif phase == 2:
                states[i] = self._mixed_state()
                actions[i], rewards[i] = self._mixed_decision(states[i])
            else:
                states[i] = self._stress_state()
                actions[i], rewards[i] = self._stress_decision(states[i])

        return CurriculumData(
            state_vectors=states,
            action_discrete=actions,
            action_continuous=np.zeros((n, 1), dtype=np.float32),
            rewards=rewards,
            next_state_vectors=states * 0.95,
            is_expert=np.ones(n, dtype=bool),
            dones=np.zeros(n, dtype=bool),
        )

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

    def _stress_state(self):
        s = self._mixed_state()
        s[2] = np.random.uniform(0.25, 0.5)   # high demand variability
        s[4] = np.random.uniform(0.15, 0.35)  # high lead time variability
        s[6] = np.random.uniform(0.80, 0.92)  # low service level
        s[7] = np.random.uniform(0.1, 0.25)   # frequent stockouts
        s[11] = np.random.uniform(0.4, 1.0)   # ATP shortage
        return s

    def _mixed_decision(self, s):
        if s[6] < s[5] - 0.03:  # service level below target
            if s[7] > 0.1:
                return 2, 0.7  # increase large
            return 1, 0.8  # increase small
        if s[8] > 0.15:  # high excess cost
            return 3, 0.7  # decrease small
        return 0, 0.8  # maintain

    def _stress_decision(self, s):
        if s[7] > 0.15:  # frequent stockouts
            return 2, 0.6  # increase large
        if s[6] < s[5] - 0.05:
            return 1, 0.6  # increase small
        if s[8] > 0.2 and s[7] < 0.05:
            return 4, 0.4  # decrease large (excess)
        return 0, 0.5  # maintain (uncertain)


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
