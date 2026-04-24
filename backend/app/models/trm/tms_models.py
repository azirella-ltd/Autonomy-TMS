"""
TMS TRM Model Definitions — Transportation-Specific Tiny Recursive Models

Defines 11 PyTorch models for the 11 TMS TRM agents with transportation-
specific state dimensions and action spaces. Each model follows the same
architecture as the SC TRM models (encoder → refinement → action/qty/confidence/value)
but with state vectors tailored to transportation operations.

State vectors are derived from the TMS heuristic library state dataclasses
in ``app.services.powell.tms_heuristic_library.base``.
"""

import torch
import torch.nn as nn


# ============================================================================
# State dimensions and action counts per TMS TRM
# ============================================================================

# 1. Capacity Promise (replaces ATP)
CP_STATE_DIM = 13
CP_NUM_ACTIONS = 4
CP_ACTION_NAMES = ["accept", "defer", "reject", "escalate"]

# 2. Shipment Tracking (replaces Order Tracking)
ST_STATE_DIM = 14
ST_NUM_ACTIONS = 5
ST_ACTION_NAMES = ["accept", "escalate", "modify", "reroute", "hold"]

# 3. Demand Sensing (replaces Forecast Adjustment)
DS_STATE_DIM = 12
DS_NUM_ACTIONS = 3
DS_ACTION_NAMES = ["accept", "modify", "escalate"]

# 4. Capacity Buffer (replaces Inventory Buffer)
CB_STATE_DIM = 14
CB_NUM_ACTIONS = 3
CB_ACTION_NAMES = ["accept", "modify", "escalate"]

# 5. Exception Management (replaces Quality Disposition)
EM_STATE_DIM = 16
EM_NUM_ACTIONS = 6
EM_ACTION_NAMES = ["accept", "retender", "reroute", "escalate", "modify", "hold"]

# 6. Freight Procurement (replaces PO Creation)
FP_STATE_DIM = 16
FP_NUM_ACTIONS = 4
FP_ACTION_NAMES = ["accept", "defer", "escalate", "reject"]

# 7. Broker Routing (replaces Subcontracting)
BR_STATE_DIM = 12
BR_NUM_ACTIONS = 3
BR_ACTION_NAMES = ["accept", "escalate", "reject"]

# 8. Dock Scheduling (replaces Maintenance Scheduling)
DK_STATE_DIM = 16
DK_NUM_ACTIONS = 4
DK_ACTION_NAMES = ["accept", "defer", "modify", "escalate"]

# 9. Load Build (replaces MO Execution)
LB_STATE_DIM = 18
LB_NUM_ACTIONS = 5
LB_ACTION_NAMES = ["consolidate", "split", "accept", "defer", "reject"]

# 10. Intermodal Transfer (replaces TO Execution)
IT_STATE_DIM = 16
IT_NUM_ACTIONS = 4
IT_ACTION_NAMES = ["accept", "defer", "reject", "modify"]

# 11. Equipment Reposition (replaces Rebalancing)
ER_STATE_DIM = 14
ER_NUM_ACTIONS = 4
ER_ACTION_NAMES = ["reposition", "hold", "defer", "reject"]


# ============================================================================
# Base TMS TRM Model
# ============================================================================

class TMSTRMModel(nn.Module):
    """
    Base TRM model for TMS execution decisions.

    Architecture:
    - Encoder: state → hidden (ReLU + LayerNorm + Dropout)
    - Recursive refinement block (N steps with residual connections)
    - Action head (discrete logits)
    - Quantity head (continuous, Softplus for non-negative)
    - Confidence head (0-1 sigmoid)
    - Value head (for RL training)
    """

    def __init__(self, state_dim: int, hidden_dim: int = 128,
                 num_actions: int = 4, num_refinement_steps: int = 3):
        super().__init__()
        self.state_dim = state_dim
        self.hidden_dim = hidden_dim
        self.num_refinement_steps = num_refinement_steps

        self.encoder = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
            nn.Dropout(0.1),
        )

        self.refine = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )

        self.action_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, num_actions),
        )

        self.qty_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
            nn.Softplus(),
        )

        self.confidence_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, 1),
            nn.Sigmoid(),
        )

        self.value_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, 1),
        )

    def forward(self, x: torch.Tensor) -> dict:
        h = self.encoder(x)
        for _ in range(self.num_refinement_steps):
            h = h + self.refine(h)

        return {
            "action_logits": self.action_head(h),
            "quantity": self.qty_head(h),
            "confidence": self.confidence_head(h),
            "value": self.value_head(h),
        }


# ============================================================================
# Per-TRM Model Classes
# ============================================================================

class CapacityPromiseTRMModel(TMSTRMModel):
    """TRM for capacity promise decisions.

    State (13): priority, requested_loads, mode_enc, committed_capacity,
        total_capacity, buffer_capacity, forecast_loads, booked_loads,
        primary_carrier_available, backup_carriers_count,
        spot_rate_premium_pct, utilization_pct, available_capacity_ratio
    """
    def __init__(self, state_dim: int = CP_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = CP_NUM_ACTIONS, num_refinement_steps: int = 3):
        super().__init__(state_dim, hidden_dim, num_actions, num_refinement_steps)


class ShipmentTrackingTRMModel(TMSTRMModel):
    """TRM for shipment tracking and exception detection.

    State (14): status_enc, hours_since_pickup, eta_delta_hours,
        last_update_hours_ago, pct_complete, miles_remaining_norm,
        carrier_otp_pct, carrier_reliability_score, active_exceptions_count,
        is_temperature_sensitive, temp_deviation, tracking_freshness,
        is_late, hours_to_delivery_norm
    """
    def __init__(self, state_dim: int = ST_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = ST_NUM_ACTIONS, num_refinement_steps: int = 3):
        super().__init__(state_dim, hidden_dim, num_actions, num_refinement_steps)


class DemandSensingTRMModel(TMSTRMModel):
    """TRM for shipping volume forecast adjustments.

    State (12): forecast_loads_norm, forecast_mape, actual_loads_norm,
        actual_prior_norm, week_over_week_change_pct, rolling_avg_norm,
        signal_magnitude, signal_confidence, seasonal_index,
        is_peak_season, forecast_bias, day_pattern_variance
    """
    def __init__(self, state_dim: int = DS_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = DS_NUM_ACTIONS, num_refinement_steps: int = 3):
        super().__init__(state_dim, hidden_dim, num_actions, num_refinement_steps)


class CapacityBufferTRMModel(TMSTRMModel):
    """TRM for capacity buffer level decisions.

    State (14): baseline_buffer_norm, forecast_loads_norm, forecast_p10_norm,
        forecast_p90_norm, committed_loads_norm, contract_capacity_norm,
        spot_availability_norm, tender_reject_rate, capacity_miss_count_norm,
        avg_spot_premium_pct, demand_cv, demand_trend, is_peak_season,
        buffer_ratio
    """
    def __init__(self, state_dim: int = CB_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = CB_NUM_ACTIONS, num_refinement_steps: int = 3):
        super().__init__(state_dim, hidden_dim, num_actions, num_refinement_steps)


class ExceptionManagementTRMModel(TMSTRMModel):
    """TRM for shipment exception response.

    State (16): exception_type_enc, severity_enc, hours_since_detected,
        estimated_delay_hrs_norm, estimated_cost_impact_norm,
        revenue_at_risk_norm, shipment_priority, is_temperature_sensitive,
        is_hazmat, delivery_window_remaining_hrs_norm,
        carrier_reliability_score, carrier_response_time_hrs_norm,
        can_retender, alternate_carriers_available_norm,
        can_reroute, is_critical_path
    """
    def __init__(self, state_dim: int = EM_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = EM_NUM_ACTIONS, num_refinement_steps: int = 3):
        super().__init__(state_dim, hidden_dim, num_actions, num_refinement_steps)


class FreightProcurementTRMModel(TMSTRMModel):
    """TRM for carrier waterfall tendering.

    State (16): mode_enc, weight_norm, pallet_count_norm, is_hazmat,
        is_temperature_sensitive, lead_time_hours_norm,
        primary_carrier_rate_norm, primary_carrier_acceptance_pct,
        spot_rate_norm, contract_rate_norm, market_tightness,
        dat_benchmark_rate_norm, tender_attempt_norm,
        hours_to_deadline_norm, rate_vs_benchmark, backup_carrier_count_norm
    """
    def __init__(self, state_dim: int = FP_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = FP_NUM_ACTIONS, num_refinement_steps: int = 3):
        super().__init__(state_dim, hidden_dim, num_actions, num_refinement_steps)


class BrokerRoutingTRMModel(TMSTRMModel):
    """TRM for broker selection when carrier waterfall exhausted.

    State (12): tender_attempts_exhausted_norm, all_carriers_declined,
        hours_to_pickup_norm, num_brokers_norm, best_broker_rate_norm,
        best_broker_reliability, contract_rate_norm, spot_rate_norm,
        broker_rate_premium_pct, budget_remaining_norm,
        shipment_priority, is_customer_committed
    """
    def __init__(self, state_dim: int = BR_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = BR_NUM_ACTIONS, num_refinement_steps: int = 3):
        super().__init__(state_dim, hidden_dim, num_actions, num_refinement_steps)


class DockSchedulingTRMModel(TMSTRMModel):
    """TRM for dock door assignment and appointment optimization.

    State (16): appointment_type_enc, total_dock_doors_norm,
        available_dock_doors_norm, yard_spots_ratio,
        appointments_in_window_norm, avg_dwell_time_norm,
        current_queue_depth_norm, shipment_priority, is_live_load,
        estimated_load_time_norm, free_time_norm,
        detention_rate_norm, carrier_avg_dwell_norm,
        utilization_pct, detention_risk_score, time_slot_available
    """
    def __init__(self, state_dim: int = DK_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = DK_NUM_ACTIONS, num_refinement_steps: int = 3):
        super().__init__(state_dim, hidden_dim, num_actions, num_refinement_steps)


class LoadBuildTRMModel(TMSTRMModel):
    """TRM for load consolidation and optimization.

    State (18): max_weight_norm, max_volume_norm, max_pallets_norm,
        total_weight_norm, total_volume_norm, total_pallets_norm,
        shipment_count_norm, has_hazmat_conflict, has_temp_conflict,
        has_destination_conflict, max_stops_norm,
        consolidation_window_hours_norm, ftl_rate_norm,
        ltl_rate_sum_norm, consolidation_savings_norm,
        weight_utilization, volume_utilization, should_consolidate
    """
    def __init__(self, state_dim: int = LB_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = LB_NUM_ACTIONS, num_refinement_steps: int = 3):
        super().__init__(state_dim, hidden_dim, num_actions, num_refinement_steps)


class IntermodalTransferTRMModel(TMSTRMModel):
    """TRM for mode shift evaluation (truck/rail/ocean).

    State (16): origin_to_ramp_miles_norm, ramp_to_ramp_miles_norm,
        ramp_to_dest_miles_norm, total_truck_miles_norm,
        truck_rate_norm, intermodal_rate_norm, drayage_rate_origin_norm,
        drayage_rate_dest_norm, truck_transit_days_norm,
        intermodal_transit_days_norm, delivery_window_days_norm,
        rail_capacity_available, ramp_congestion_level,
        intermodal_reliability_pct, weather_risk_score,
        cost_savings_pct
    """
    def __init__(self, state_dim: int = IT_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = IT_NUM_ACTIONS, num_refinement_steps: int = 3):
        super().__init__(state_dim, hidden_dim, num_actions, num_refinement_steps)


class EquipmentRepositionTRMModel(TMSTRMModel):
    """TRM for empty equipment repositioning.

    State (14): source_equipment_norm, source_demand_norm,
        target_equipment_norm, target_demand_norm,
        reposition_miles_norm, reposition_cost_norm,
        reposition_transit_hours_norm, network_surplus_locations_norm,
        network_deficit_locations_norm, fleet_utilization_pct,
        cost_of_not_repositioning_norm, source_surplus_norm,
        target_deficit_norm, reposition_roi
    """
    def __init__(self, state_dim: int = ER_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = ER_NUM_ACTIONS, num_refinement_steps: int = 3):
        super().__init__(state_dim, hidden_dim, num_actions, num_refinement_steps)


# ============================================================================
# TMS Model Registry
# ============================================================================

TMS_MODEL_REGISTRY = {
    "capacity_promise":      (CapacityPromiseTRMModel, CP_STATE_DIM),
    "shipment_tracking":     (ShipmentTrackingTRMModel, ST_STATE_DIM),
    "demand_sensing":        (DemandSensingTRMModel, DS_STATE_DIM),
    "capacity_buffer":       (CapacityBufferTRMModel, CB_STATE_DIM),
    "exception_management":  (ExceptionManagementTRMModel, EM_STATE_DIM),
    "freight_procurement":   (FreightProcurementTRMModel, FP_STATE_DIM),
    "broker_routing":        (BrokerRoutingTRMModel, BR_STATE_DIM),
    "dock_scheduling":       (DockSchedulingTRMModel, DK_STATE_DIM),
    "load_build":            (LoadBuildTRMModel, LB_STATE_DIM),
    "intermodal_transfer":   (IntermodalTransferTRMModel, IT_STATE_DIM),
    "equipment_reposition":  (EquipmentRepositionTRMModel, ER_STATE_DIM),
}
