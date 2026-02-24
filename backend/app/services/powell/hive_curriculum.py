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

MO_STATE_DIM = 14
TO_STATE_DIM = 14
QUALITY_STATE_DIM = 12
MAINTENANCE_STATE_DIM = 13
SUBCONTRACTING_STATE_DIM = 16
FORECAST_ADJ_STATE_DIM = 15
INVENTORY_BUFFER_STATE_DIM = 14


# ---------------------------------------------------------------------------
# MO Execution Curriculum
# ---------------------------------------------------------------------------

class MOExecutionCurriculum(TRMCurriculumBase):
    """Curriculum for Manufacturing Order execution decisions.

    State: [planned_qty_norm, capacity_util, setup_hrs, run_hrs,
            priority, due_days, material_available, quality_hold,
            downstream_demand, wip_level, changeover_cost_norm,
            maintenance_risk, batch_efficiency, urgency]

    Actions: 0=release, 1=sequence, 2=split, 3=expedite, 4=defer
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
                # Simple: high capacity, materials available, no holds
                states[i] = self._phase1_state()
                actions[i] = 0  # release
                rewards[i] = 1.0
            elif phase == 2:
                # Mixed: capacity constraints, sequencing decisions
                states[i] = self._phase2_state()
                actions[i], rewards[i] = self._phase2_decision(states[i])
            else:
                # Stress: quality holds, maintenance risk, urgent orders
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
            np.random.uniform(0.1, 0.5),   # planned_qty_norm
            np.random.uniform(0.3, 0.6),   # capacity_util
            np.random.uniform(0.5, 2.0),   # setup_hrs
            np.random.uniform(1.0, 4.0),   # run_hrs
            np.random.randint(1, 4) / 5.0, # priority
            np.random.uniform(3.0, 10.0) / 14.0, # due_days (normalized)
            1.0,                           # material_available
            0.0,                           # quality_hold
            np.random.uniform(0.3, 0.7),   # downstream_demand
            np.random.uniform(0.1, 0.4),   # wip_level
            np.random.uniform(0.05, 0.2),  # changeover_cost_norm
            np.random.uniform(0.0, 0.1),   # maintenance_risk
            np.random.uniform(0.7, 0.95),  # batch_efficiency
            np.random.uniform(0.0, 0.3),   # urgency
        ], dtype=np.float32)

    def _phase2_state(self):
        s = self._phase1_state()
        s[1] = np.random.uniform(0.6, 0.9)   # higher capacity util
        s[6] = np.random.choice([0.0, 1.0], p=[0.2, 0.8])  # sometimes no material
        s[13] = np.random.uniform(0.2, 0.7)  # higher urgency
        return s

    def _phase3_state(self):
        s = self._phase2_state()
        s[1] = np.random.uniform(0.8, 1.0)   # near full capacity
        s[7] = np.random.choice([0.0, 1.0], p=[0.7, 0.3])  # quality holds
        s[11] = np.random.uniform(0.3, 0.8)  # maintenance risk
        s[13] = np.random.uniform(0.5, 1.0)  # high urgency
        return s

    def _phase2_decision(self, s):
        if s[6] < 0.5:  # no material
            return 4, 0.5  # defer
        if s[1] > 0.85:  # high capacity
            return 1, 0.7  # sequence
        return 0, 0.9  # release

    def _phase3_decision(self, s):
        if s[7] > 0.5:  # quality hold
            return 4, 0.3  # defer
        if s[11] > 0.5 and s[13] < 0.7:
            return 4, 0.4  # defer for maintenance
        if s[13] > 0.8:
            return 3, 0.6  # expedite
        if s[1] > 0.9:
            return 2, 0.5  # split
        return 0, 0.7  # release


# ---------------------------------------------------------------------------
# TO Execution Curriculum
# ---------------------------------------------------------------------------

class TOExecutionCurriculum(TRMCurriculumBase):
    """Curriculum for Transfer Order execution decisions.

    State: [planned_qty_norm, source_inv_norm, dest_inv_norm,
            transit_days_norm, transportation_cost_norm, priority,
            consolidation_opportunity, dest_urgency, source_excess,
            lane_reliability, dest_dos, source_dos,
            rebalance_signal, network_imbalance]

    Actions: 0=release, 1=expedite, 2=consolidate, 3=reroute, 4=defer
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
            np.random.uniform(0.1, 0.4),   # planned_qty
            np.random.uniform(0.5, 0.9),   # source_inv
            np.random.uniform(0.2, 0.5),   # dest_inv
            np.random.uniform(0.1, 0.3),   # transit_days
            np.random.uniform(0.05, 0.15), # transportation_cost
            np.random.randint(1, 4) / 5.0, # priority
            0.0,                           # consolidation_opportunity
            np.random.uniform(0.1, 0.4),   # dest_urgency
            np.random.uniform(0.3, 0.6),   # source_excess
            np.random.uniform(0.85, 0.98), # lane_reliability
            np.random.uniform(10, 25) / 30.0, # dest_dos
            np.random.uniform(15, 30) / 30.0, # source_dos
            0.0,                           # rebalance_signal
            np.random.uniform(0.0, 0.2),   # network_imbalance
        ], dtype=np.float32)

    def _mixed_state(self):
        s = self._simple_state()
        s[6] = np.random.choice([0.0, 1.0], p=[0.6, 0.4])  # consolidation
        s[7] = np.random.uniform(0.3, 0.8)
        s[12] = np.random.uniform(0.0, 0.6)  # rebalance signal
        return s

    def _stress_state(self):
        s = self._mixed_state()
        s[2] = np.random.uniform(0.0, 0.2)  # low dest inv
        s[7] = np.random.uniform(0.6, 1.0)  # high dest urgency
        s[9] = np.random.uniform(0.5, 0.85)  # lower reliability
        s[13] = np.random.uniform(0.4, 0.9)  # network imbalance
        return s

    def _mixed_decision(self, s):
        if s[6] > 0.5:
            return 2, 0.8  # consolidate
        if s[7] > 0.7:
            return 1, 0.7  # expedite
        return 0, 0.9  # release

    def _stress_decision(self, s):
        if s[2] < 0.1 and s[7] > 0.8:
            return 1, 0.6  # expedite critically
        if s[9] < 0.6:
            return 3, 0.5  # reroute around unreliable lane
        if s[13] > 0.7:
            return 4, 0.4  # defer, network unstable
        return 0, 0.7  # release


# ---------------------------------------------------------------------------
# Quality Disposition Curriculum
# ---------------------------------------------------------------------------

class QualityDispositionCurriculum(TRMCurriculumBase):
    """Curriculum for Quality disposition decisions.

    State: [defect_rate, severity_norm, inspection_qty_norm,
            rework_cost_norm, scrap_cost_norm, service_risk,
            inventory_coverage, customer_criticality,
            historical_pass_rate, atp_shortage_signal,
            lot_age_norm, supplier_quality_score]

    Actions: 0=accept, 1=reject, 2=rework, 3=scrap, 4=use_as_is
    """

    @property
    def state_dim(self) -> int:
        return QUALITY_STATE_DIM

    @property
    def trm_type(self) -> str:
        return "quality"

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
            np.random.uniform(0.0, 0.03),  # defect_rate (low)
            np.random.uniform(0.0, 0.3),   # severity
            np.random.uniform(0.2, 0.6),   # inspection_qty
            np.random.uniform(0.05, 0.15), # rework_cost
            np.random.uniform(0.1, 0.3),   # scrap_cost
            np.random.uniform(0.0, 0.1),   # service_risk
            np.random.uniform(0.6, 1.0),   # inventory_coverage
            np.random.uniform(0.3, 0.7),   # customer_criticality
            np.random.uniform(0.9, 0.99),  # historical_pass_rate
            0.0,                           # atp_shortage_signal
            np.random.uniform(0.0, 0.3),   # lot_age
            np.random.uniform(0.85, 0.98), # supplier_quality_score
        ], dtype=np.float32)

    def _mixed_state(self):
        s = self._simple_state()
        s[0] = np.random.uniform(0.02, 0.10)  # higher defect rate
        s[1] = np.random.uniform(0.2, 0.7)
        s[9] = np.random.uniform(0.0, 0.5)  # some ATP shortage
        return s

    def _stress_state(self):
        s = self._mixed_state()
        s[0] = np.random.uniform(0.05, 0.25)  # high defect rate
        s[1] = np.random.uniform(0.5, 1.0)    # high severity
        s[6] = np.random.uniform(0.1, 0.4)    # low inventory coverage
        s[9] = np.random.uniform(0.4, 1.0)    # ATP shortage
        return s

    def _simple_decision(self, s):
        if s[0] < 0.02:
            return 0, 1.0  # accept
        return 1, 0.8  # reject

    def _mixed_decision(self, s):
        if s[0] < 0.03 and s[1] < 0.3:
            return 0, 0.9  # accept minor
        if s[0] > 0.08:
            if s[4] < s[2] * 0.5:
                return 3, 0.6  # scrap (cheap)
            return 1, 0.7  # reject
        return 2, 0.7  # rework

    def _stress_decision(self, s):
        if s[9] > 0.7 and s[0] < 0.08:
            return 4, 0.4  # use_as_is (shortage override)
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

    State: [asset_health_score, time_since_last_pm_norm,
            failure_probability, production_load_norm,
            spare_parts_available, downtime_cost_norm,
            mo_pending_count_norm, maintenance_window_available,
            asset_criticality, risk_if_deferred,
            production_impact_norm, seasonal_factor,
            maintenance_backlog_norm]

    Actions: 0=schedule, 1=defer, 2=expedite, 3=combine, 4=outsource
    """

    @property
    def state_dim(self) -> int:
        return MAINTENANCE_STATE_DIM

    @property
    def trm_type(self) -> str:
        return "maintenance"

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
            np.random.uniform(0.7, 0.95),  # asset_health
            np.random.uniform(0.3, 0.6),   # time_since_last_pm
            np.random.uniform(0.0, 0.1),   # failure_probability
            np.random.uniform(0.3, 0.6),   # production_load
            1.0,                           # spare_parts_available
            np.random.uniform(0.1, 0.3),   # downtime_cost
            np.random.uniform(0.1, 0.4),   # mo_pending
            1.0,                           # maintenance_window
            np.random.uniform(0.3, 0.7),   # asset_criticality
            np.random.uniform(0.0, 0.2),   # risk_if_deferred
            np.random.uniform(0.1, 0.3),   # production_impact
            np.random.uniform(0.8, 1.2),   # seasonal_factor
            np.random.uniform(0.0, 0.2),   # maintenance_backlog
        ], dtype=np.float32)

    def _mixed_state(self):
        s = self._simple_state()
        s[3] = np.random.uniform(0.6, 0.9)  # higher production load
        s[4] = np.random.choice([0.0, 1.0], p=[0.3, 0.7])  # sometimes no parts
        s[7] = np.random.choice([0.0, 1.0], p=[0.4, 0.6])  # window not always open
        return s

    def _stress_state(self):
        s = self._mixed_state()
        s[0] = np.random.uniform(0.3, 0.6)   # degraded health
        s[2] = np.random.uniform(0.2, 0.5)   # higher failure prob
        s[3] = np.random.uniform(0.8, 1.0)   # high production load
        s[9] = np.random.uniform(0.4, 0.9)   # high deferral risk
        return s

    def _mixed_decision(self, s):
        if s[7] < 0.5:  # no window
            return 1, 0.6  # defer
        if s[4] < 0.5:  # no parts
            return 4, 0.5  # outsource
        if s[3] > 0.8:  # high production load
            return 1, 0.5  # defer
        return 0, 0.8  # schedule

    def _stress_decision(self, s):
        if s[2] > 0.4:  # high failure risk
            if s[4] < 0.5:
                return 4, 0.4  # outsource urgently
            return 2, 0.6  # expedite
        if s[9] > 0.6:
            return 2, 0.5  # expedite
        if s[3] > 0.9:
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

    State: [signal_confidence, direction_encoded, magnitude_hint,
            current_forecast_norm, forecast_confidence,
            historical_accuracy, source_reliability,
            signal_type_accuracy, product_volatility,
            product_trend, seasonality_factor,
            inventory_dos_norm, pending_orders_norm,
            time_horizon_norm, source_encoded]

    Actions: 0=no_change, 1=adjust_up_small, 2=adjust_up_large,
             3=adjust_down_small, 4=adjust_down_large
    """

    @property
    def state_dim(self) -> int:
        return FORECAST_ADJ_STATE_DIM

    @property
    def trm_type(self) -> str:
        return "forecast_adj"

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
            np.random.uniform(0.7, 0.95),  # signal_confidence
            direction,                     # direction_encoded
            np.random.uniform(0.05, 0.15), # magnitude_hint
            np.random.uniform(0.3, 0.7),   # current_forecast
            np.random.uniform(0.7, 0.9),   # forecast_confidence
            np.random.uniform(0.8, 0.95),  # historical_accuracy
            np.random.uniform(0.7, 0.95),  # source_reliability
            np.random.uniform(0.7, 0.9),   # signal_type_accuracy
            np.random.uniform(0.1, 0.3),   # product_volatility
            np.random.uniform(-0.05, 0.05),# product_trend
            np.random.uniform(0.9, 1.1),   # seasonality
            np.random.uniform(0.4, 0.7),   # inventory_dos
            np.random.uniform(0.1, 0.3),   # pending_orders
            np.random.uniform(0.2, 0.5),   # time_horizon
            np.random.uniform(0.1, 0.6),   # source_encoded
        ], dtype=np.float32)

    def _mixed_state(self):
        s = self._simple_state()
        s[0] = np.random.uniform(0.4, 0.8)  # lower confidence
        s[6] = np.random.uniform(0.4, 0.8)  # mixed source reliability
        s[8] = np.random.uniform(0.2, 0.5)  # higher volatility
        return s

    def _stress_state(self):
        s = self._mixed_state()
        s[0] = np.random.uniform(0.2, 0.6)  # low confidence
        s[8] = np.random.uniform(0.4, 0.8)  # high volatility
        s[9] = np.random.uniform(-0.2, 0.2) # strong trend
        return s

    def _simple_decision(self, s):
        if s[0] > 0.8 and s[6] > 0.8:
            if s[1] > 0.5:
                return 1, 0.9  # adjust up small
            elif s[1] < -0.5:
                return 3, 0.9  # adjust down small
        return 0, 0.7  # no change

    def _mixed_decision(self, s):
        if s[0] > 0.6 and s[6] > 0.6:
            if s[1] > 0.5:
                if s[2] > 0.1:
                    return 2, 0.7  # adjust up large
                return 1, 0.7  # adjust up small
            elif s[1] < -0.5:
                if s[2] > 0.1:
                    return 4, 0.7  # adjust down large
                return 3, 0.7  # adjust down small
        return 0, 0.6  # no change (uncertain)

    def _stress_decision(self, s):
        # In stress, be conservative
        if s[0] < 0.4:
            return 0, 0.5  # too uncertain
        if s[6] < 0.5:
            return 0, 0.4  # unreliable source
        if s[1] > 0.5:
            return 1, 0.5  # small up only
        elif s[1] < -0.5:
            return 3, 0.5  # small down only
        return 0, 0.5


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
# Registry
# ---------------------------------------------------------------------------

HIVE_CURRICULUM_REGISTRY = {
    "mo_execution": MOExecutionCurriculum,
    "to_execution": TOExecutionCurriculum,
    "quality": QualityDispositionCurriculum,
    "maintenance": MaintenanceSchedulingCurriculum,
    "subcontracting": SubcontractingCurriculum,
    "forecast_adj": ForecastAdjustmentCurriculum,
    "inventory_buffer": InventoryBufferCurriculum,
}
