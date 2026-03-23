"""
SAP S/4HANA & ECC Heuristic Implementations.

Mirrors SAP MRP logic from MARC (material-plant master), EORD (purchasing
info record), STKO/STPO (BOM), and PM (maintenance) tables.  Each method
replicates how SAP would decide, using parameters extracted via the SAP
staging pipeline.

Key SAP references:
  - MARC.DISMM  -> planning_method  (VB/VV/V1/V2/PD/ND)
  - MARC.DISLS  -> lot_sizing_rule  (EX/FX/HB/WB/MB/TB)
  - MARC.MINBE  -> reorder_point
  - MARC.MABST  -> max_inventory
  - MARC.BSTRF  -> order_multiple (rounding value)
  - MARC.BSTMI  -> min_order_quantity
  - MARC.BSTMA  -> max_order_quantity
  - MARC.FXHOR  -> frozen_horizon_days
  - MARC.BESKZ  -> procurement_type (E=in-house, F=external, X=both)
  - MARC.STRGR  -> strategy_group (consumption strategy)
  - MARC.VRMOD/VINT -> forecast consumption mode/period
  - EORD         -> source list (vendor, agreement, plant)
  - STKO/STPO    -> BOM header/items (AUSCH = component scrap %)
  - T024D + AFVGD -> work center setup/run times for MO sequencing
  - QMFE         -> QM defect classification (SAP QM)
  - MPLA/MHIS    -> PM maintenance plan / history (MTBF calculation)

All functions are pure: f(state, params) -> HeuristicDecision.
"""

from __future__ import annotations

import math
from typing import Dict, Any

from .base import (
    BaseHeuristics,
    HeuristicDecision,
    ERPPlanningParams,
    ReplenishmentState,
    ATPState,
    RebalancingState,
    OrderTrackingState,
    MOExecutionState,
    TOExecutionState,
    QualityState,
    MaintenanceState,
    SubcontractingState,
    ForecastAdjustmentState,
    InventoryBufferState,
    apply_lot_sizing,
    apply_order_modifications,
)


class SAPHeuristics(BaseHeuristics):
    """SAP S/4HANA and ECC planning heuristic implementations.

    Replicates MRP run logic from SAP MARC parameters.  Each planning
    method (DISMM) has a distinct netting algorithm; lot sizing (DISLS)
    is applied after netting.
    """

    # ===================================================================
    # 1. REPLENISHMENT (PO/TO creation) -- SAP MRP netting
    # ===================================================================

    def compute_replenishment(
        self, state: ReplenishmentState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """SAP MRP netting: DISMM selects method, DISLS selects lot size.

        Pipeline: netting -> lot sizing -> order modifications.

        SAP DISMM logic:
          VB/VM: Reorder point procedure -- if IP < ROP, order to OUL
          VV:    Forecast-based planning -- net forecast over review period
          V1/V2: Automatic ROP with external requirements
          PD:    Deterministic MRP -- time-phased netting of all requirements
          ND:    No planning
        """
        method = params.planning_method
        erp = params.erp_params

        # SAP-specific: respect frozen horizon (FXHOR)
        # Within the frozen horizon, no new planned orders are created
        if params.frozen_horizon_days > 0:
            sim_day = erp.get("sim_day", 0)
            if sim_day < params.frozen_horizon_days:
                return HeuristicDecision(
                    trm_type="po_creation",
                    action=0,
                    quantity=0.0,
                    reasoning=f"Within frozen horizon ({params.frozen_horizon_days}d). "
                              f"SAP MARC.FXHOR blocks new planned orders.",
                    erp_params_used={"FXHOR": params.frozen_horizon_days},
                )

        # Netting by DISMM
        if method == "REORDER_POINT":
            raw_qty = self._net_reorder_point(state, params)
            reason_prefix = "SAP VB reorder point"
        elif method == "FORECAST_BASED":
            raw_qty = self._net_forecast_based(state, params)
            reason_prefix = "SAP VV forecast-based"
        elif method in ("MRP_AUTO", "MRP_DETERMINISTIC"):
            raw_qty = self._net_mrp(state, params)
            reason_prefix = f"SAP {'V1/V2 auto' if method == 'MRP_AUTO' else 'PD deterministic'} MRP"
        elif method == "PERIOD_BATCHING":
            raw_qty = self._net_period_batching(state, params)
            reason_prefix = "SAP period batching"
        elif method == "MIN_MAX":
            raw_qty = self._net_min_max(state, params)
            reason_prefix = "SAP HB min-max"
        elif method == "NO_PLANNING":
            return HeuristicDecision(
                trm_type="po_creation",
                action=0,
                quantity=0.0,
                reasoning="SAP DISMM=ND: no automatic replenishment.",
                erp_params_used={"DISMM": "ND"},
            )
        else:
            # Fallback to reorder point for unknown methods
            raw_qty = self._net_reorder_point(state, params)
            reason_prefix = f"SAP fallback (unknown method={method})"

        if raw_qty <= 0:
            return HeuristicDecision(
                trm_type="po_creation",
                action=0,
                quantity=0.0,
                reasoning=f"{reason_prefix}: no net requirement. "
                          f"IP={state.inventory_position:.1f}, ROP={params.reorder_point:.1f}",
                erp_params_used={"DISMM": method, "IP": state.inventory_position},
            )

        # Lot sizing by DISLS
        lot_qty = apply_lot_sizing(raw_qty, state.inventory_position, params)
        if lot_qty <= 0:
            return HeuristicDecision(
                trm_type="po_creation", action=0, quantity=0.0,
                reasoning=f"{reason_prefix}: lot sizing reduced to zero.",
                erp_params_used={"DISMM": method, "DISLS": params.lot_sizing_rule},
            )

        # Order modifications (MOQ, rounding, max)
        final_qty = apply_order_modifications(lot_qty, params)

        return HeuristicDecision(
            trm_type="po_creation",
            action=1,
            quantity=final_qty,
            reasoning=f"{reason_prefix}: net={raw_qty:.1f}, lot={lot_qty:.1f}, "
                      f"final={final_qty:.1f}. "
                      f"IP={state.inventory_position:.1f}, ROP={params.reorder_point:.1f}, "
                      f"OUL={params.order_up_to:.1f}",
            erp_params_used={
                "DISMM": method,
                "DISLS": params.lot_sizing_rule,
                "MINBE": params.reorder_point,
                "BSTMI": params.min_order_quantity,
                "BSTMA": params.max_order_quantity,
                "BSTRF": params.order_multiple,
            },
        )

    def _net_reorder_point(
        self, state: ReplenishmentState, params: ERPPlanningParams,
    ) -> float:
        """SAP VB/VM: if inventory position < reorder point, order up to OUL."""
        if state.inventory_position < params.reorder_point:
            return max(0.0, params.order_up_to - state.inventory_position)
        return 0.0

    def _net_forecast_based(
        self, state: ReplenishmentState, params: ERPPlanningParams,
    ) -> float:
        """SAP VV: net forecast demand over review period against IP.

        SAP forecast-based planning (DISMM=VV) uses MARC.VRMOD and MARC.VINT
        to determine the forecast consumption window.  The net requirement is:
          forecast_daily * review_period + safety_stock - inventory_position

        If forecast consumption is configured (VRMOD), SAP reduces planned
        independent requirements by actual consumption within the window.
        """
        erp = params.erp_params
        # SAP VRMOD: 1=backward, 2=backward+forward, 3=period-based
        vrmod = erp.get("VRMOD", 0)

        if vrmod and params.forecast_consumption_fwd_days > 0:
            # Extended consumption: use forward + backward window
            coverage_days = max(
                params.review_period_days,
                params.forecast_consumption_fwd_days + params.forecast_consumption_bwd_days,
            )
        else:
            coverage_days = params.review_period_days

        coverage_demand = state.forecast_daily * coverage_days
        net_need = coverage_demand + params.safety_stock - state.inventory_position
        return max(0.0, net_need)

    def _net_mrp(
        self, state: ReplenishmentState, params: ERPPlanningParams,
    ) -> float:
        """SAP PD/V1/V2: deterministic MRP netting.

        SAP MRP run (DISMM=PD) processes requirements time-bucket by time-bucket:
          1. Gross requirement = customer orders + forecast (after consumption)
          2. Projected available = on-hand + scheduled receipts - gross requirement
          3. If projected available < safety stock, create planned order

        For the simulation (single-period snapshot), we approximate:
          net = avg_demand * lead_time + safety_stock - inventory_position

        This covers the lead time demand plus safety stock cushion,
        which is the core SAP MRP netting logic in a single-period view.
        """
        # SAP MRP nets over the lead time horizon
        lt_demand = state.avg_daily_demand * params.lead_time_days
        net_need = lt_demand + params.safety_stock - state.inventory_position
        return max(0.0, net_need)

    def _net_period_batching(
        self, state: ReplenishmentState, params: ERPPlanningParams,
    ) -> float:
        """SAP WB/MB/TB: accumulate demand, order on review boundary.

        SAP DISLS=WB orders weekly (every Monday), MB monthly (1st of month),
        TB daily.  Between boundaries, no orders are placed.
        """
        rule = params.lot_sizing_rule

        if rule == "WEEKLY_BATCH" and state.day_of_week != 0:
            return 0.0
        if rule == "MONTHLY_BATCH" and state.day_of_month != 1:
            return 0.0
        # DAILY_BATCH: order every day

        coverage = state.avg_daily_demand * params.review_period_days
        net_need = coverage + params.safety_stock - state.inventory_position
        return max(0.0, net_need)

    def _net_min_max(
        self, state: ReplenishmentState, params: ERPPlanningParams,
    ) -> float:
        """SAP HB: if IP < min (reorder point), order to max (MABST)."""
        if state.inventory_position < params.reorder_point:
            target = params.max_inventory if params.max_inventory > 0 else params.order_up_to
            return max(0.0, target - state.inventory_position)
        return 0.0

    # ===================================================================
    # 2. ATP ALLOCATION -- SAP aATP priority waterfall
    # ===================================================================

    def compute_atp_allocation(
        self, state: ATPState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """SAP Allocated ATP (aATP) with priority-based consumption waterfall.

        SAP aATP BOP (Business Object Processing) consumption sequence:
          1. Consume own priority tier first
          2. Bottom-up from lowest priority (5->4->3->...)
          3. Stop at own tier (cannot consume above own priority)

        For simulation: simple available-vs-requested check with priority
        consideration.  Full BOP WIN/GAIN/REDISTRIBUTE modes are in the
        TRM itself.
        """
        erp = params.erp_params
        # SAP delivery date control: ATP, ATP+CMR, CTP, etc.
        atp_check_mode = erp.get("ATP_CHECK_MODE", "ATP")

        available_for_order = state.available_inventory - state.allocated_inventory
        can_fulfill = available_for_order >= state.order_qty

        if can_fulfill:
            return HeuristicDecision(
                trm_type="atp_executor",
                action=1,  # confirm
                quantity=state.order_qty,
                reasoning=f"SAP aATP: full confirmation. Available={available_for_order:.1f} "
                          f">= requested={state.order_qty:.1f}. "
                          f"Priority={state.order_priority}, mode={atp_check_mode}.",
                erp_params_used={
                    "ATP_CHECK_MODE": atp_check_mode,
                    "priority": state.order_priority,
                },
            )

        # Partial fulfillment -- SAP allows partial confirmation
        partial_qty = max(0.0, available_for_order)
        if partial_qty > 0:
            return HeuristicDecision(
                trm_type="atp_executor",
                action=2,  # partial confirm
                quantity=partial_qty,
                reasoning=f"SAP aATP: partial confirmation. Available={available_for_order:.1f} "
                          f"< requested={state.order_qty:.1f}. "
                          f"Confirming {partial_qty:.1f}. Remainder backordered.",
                erp_params_used={
                    "ATP_CHECK_MODE": atp_check_mode,
                    "priority": state.order_priority,
                },
            )

        return HeuristicDecision(
            trm_type="atp_executor",
            action=0,  # reject / backorder
            quantity=0.0,
            reasoning=f"SAP aATP: no available inventory. "
                      f"Available={available_for_order:.1f}, requested={state.order_qty:.1f}.",
            erp_params_used={"ATP_CHECK_MODE": atp_check_mode},
        )

    # ===================================================================
    # 3. INVENTORY REBALANCING -- SAP APO deployment
    # ===================================================================

    def compute_rebalancing(
        self, state: RebalancingState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """SAP APO deployment / SNP heuristic rebalancing.

        SAP APO uses "fair share" or "push" deployment:
          - Calculate days of supply at each location
          - Transfer from surplus (DOS > target) to deficit (DOS < target)
          - Respect minimum transfer quantity and transfer cost threshold

        Heuristic: transfer if source has excess above safety stock AND
        target is below safety stock, limited by the surplus amount.
        """
        source_excess = state.source_on_hand - state.source_safety_stock - state.source_backlog
        target_deficit = state.target_safety_stock + state.target_backlog - state.target_on_hand

        if source_excess <= 0 or target_deficit <= 0:
            return HeuristicDecision(
                trm_type="inventory_rebalancing",
                action=0,
                quantity=0.0,
                reasoning="SAP deployment: no rebalancing needed. "
                          f"Source excess={source_excess:.1f}, target deficit={target_deficit:.1f}.",
                erp_params_used={},
            )

        transfer_qty = min(source_excess, target_deficit)

        # SAP cost threshold: skip transfer if cost exceeds benefit
        erp = params.erp_params
        min_transfer = erp.get("MIN_TRANSFER_QTY", 0.0)
        if transfer_qty < min_transfer:
            return HeuristicDecision(
                trm_type="inventory_rebalancing",
                action=0,
                quantity=0.0,
                reasoning=f"SAP deployment: transfer qty={transfer_qty:.1f} "
                          f"below minimum={min_transfer:.1f}.",
                erp_params_used={"MIN_TRANSFER_QTY": min_transfer},
            )

        return HeuristicDecision(
            trm_type="inventory_rebalancing",
            action=1,
            quantity=transfer_qty,
            reasoning=f"SAP APO deployment: transfer {transfer_qty:.1f} from surplus to deficit. "
                      f"Source excess={source_excess:.1f}, target deficit={target_deficit:.1f}.",
            erp_params_used={
                "source_excess": source_excess,
                "target_deficit": target_deficit,
            },
        )

    # ===================================================================
    # 4. ORDER TRACKING -- SAP delivery monitoring
    # ===================================================================

    def compute_order_tracking(
        self, state: OrderTrackingState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """SAP order monitoring: exception detection based on delivery status.

        SAP creates exception messages in the MRP run:
          - Type 06: Delivery date in past (reschedule in)
          - Type 07: Delivery date too early (reschedule out)
          - Type 10: Open purchase requisition exists
          - Type 40: Recommended rescheduling

        Heuristic: flag orders that are overdue or have low supplier reliability.
        """
        erp = params.erp_params
        # Configurable thresholds from SAP customizing
        overdue_threshold_days = erp.get("OVERDUE_THRESHOLD_DAYS", 2.0)
        reliability_threshold = erp.get("RELIABILITY_THRESHOLD", 0.80)

        actions = []
        severity = 0

        # Check overdue
        if state.days_overdue > overdue_threshold_days:
            actions.append(f"overdue by {state.days_overdue:.0f}d (SAP exception type 06)")
            severity = max(severity, 2)  # expedite

        # Check partial delivery
        if state.quantity_received > 0 and state.quantity_received < state.quantity_ordered:
            shortfall_pct = (1 - state.quantity_received / state.quantity_ordered) * 100
            actions.append(f"partial delivery ({shortfall_pct:.0f}% short)")
            severity = max(severity, 1)  # monitor

        # Check supplier reliability
        if state.supplier_on_time_rate < reliability_threshold:
            actions.append(
                f"supplier OTD={state.supplier_on_time_rate:.0%} "
                f"below threshold={reliability_threshold:.0%}"
            )
            severity = max(severity, 1)

        # Critical order escalation
        if state.is_critical and state.days_overdue > 0:
            severity = max(severity, 3)  # escalate
            actions.append("critical order -- escalate to planner")

        if not actions:
            return HeuristicDecision(
                trm_type="order_tracking",
                action=0,
                quantity=0.0,
                reasoning=f"SAP order monitoring: {state.order_id} on track. "
                          f"Status={state.current_status}.",
                erp_params_used={},
            )

        return HeuristicDecision(
            trm_type="order_tracking",
            action=severity,
            quantity=state.quantity_ordered - state.quantity_received,
            reasoning=f"SAP order exception: {state.order_id} -- {'; '.join(actions)}.",
            erp_params_used={
                "OVERDUE_THRESHOLD_DAYS": overdue_threshold_days,
                "RELIABILITY_THRESHOLD": reliability_threshold,
            },
        )

    # ===================================================================
    # 5. MO EXECUTION -- SAP PP scheduling with Glenday sieve
    # ===================================================================

    def compute_mo_execution(
        self, state: MOExecutionState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """SAP PP production order scheduling with Glenday Sieve categorization.

        SAP PP scheduling uses work center capacity (T024D), setup matrix
        (AFVGD), and operation times.  The Glenday Sieve (not native SAP)
        categorizes products by volume:
          - Green (top 6% SKUs, ~50% volume): fixed schedule, no changeover
          - Yellow (next 14% SKUs, ~45% volume): regular slots
          - Blue (next 30% SKUs, ~4% volume): campaign batching
          - Red (bottom 50% SKUs, ~1% volume): make-to-order only

        Sequencing uses nearest-neighbor changeover minimization via AFVGD
        setup matrix when available, else product family grouping.
        """
        erp = params.erp_params

        # Glenday category determines scheduling strategy
        category = state.glenday_category.lower() if state.glenday_category else "yellow"

        # Check capacity
        required_hours = state.setup_time_hours + state.run_time_hours
        capacity_ok = state.available_capacity_hours >= required_hours

        if not capacity_ok:
            # SAP: reschedule or split
            if category in ("green", "yellow"):
                # High-volume: expedite or overtime
                return HeuristicDecision(
                    trm_type="mo_execution",
                    action=3,  # expedite
                    quantity=state.quantity,
                    reasoning=f"SAP PP: MO {state.mo_id} needs {required_hours:.1f}h "
                              f"but only {state.available_capacity_hours:.1f}h available. "
                              f"Glenday={category} -- recommend overtime/expedite.",
                    erp_params_used={"glenday": category, "capacity_gap": required_hours - state.available_capacity_hours},
                )
            else:
                # Low-volume: defer to next slot
                return HeuristicDecision(
                    trm_type="mo_execution",
                    action=4,  # defer
                    quantity=state.quantity,
                    reasoning=f"SAP PP: MO {state.mo_id} deferred -- insufficient capacity. "
                              f"Glenday={category}, needed={required_hours:.1f}h, "
                              f"available={state.available_capacity_hours:.1f}h.",
                    erp_params_used={"glenday": category},
                )

        # Sequencing: nearest-neighbor changeover minimization
        # If AFVGD setup matrix data exists, use it; else group by family
        setup_matrix = erp.get("AFVGD_SETUP_MATRIX", {})
        changeover_time = 0.0
        if setup_matrix and state.last_product_run:
            key = f"{state.last_product_run}->{state.product_id}"
            changeover_time = setup_matrix.get(key, state.setup_time_hours)
        else:
            # Family grouping: zero changeover within family, full setup between
            if state.last_product_run and state.product_family:
                last_family = erp.get("product_families", {}).get(state.last_product_run, "")
                if last_family == state.product_family:
                    changeover_time = state.setup_time_hours * 0.2  # reduced within family
                else:
                    changeover_time = state.setup_time_hours

        action = 1  # release
        reasoning = (
            f"SAP PP: release MO {state.mo_id}. Glenday={category}, "
            f"OEE={state.oee:.0%}, setup={changeover_time:.1f}h, "
            f"run={state.run_time_hours:.1f}h."
        )

        return HeuristicDecision(
            trm_type="mo_execution",
            action=action,
            quantity=state.quantity,
            reasoning=reasoning,
            erp_params_used={
                "glenday": category,
                "changeover_hours": changeover_time,
                "AFVGD": bool(setup_matrix),
            },
        )

    # ===================================================================
    # 6. TO EXECUTION -- SAP shipment processing
    # ===================================================================

    def compute_to_execution(
        self, state: TOExecutionState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """SAP shipment document (VT01N) processing.

        SAP consolidates deliveries into shipments based on:
          - Route determination (shipping point -> destination)
          - Transportation planning date
          - Load optimization (vehicle utilization)

        Heuristic: consolidate within window, expedite if priority is high.
        """
        erp = params.erp_params
        min_load_pct = erp.get("MIN_LOAD_PCT", 0.65)

        # Check if consolidation makes sense
        if state.current_load_pct < min_load_pct and state.consolidation_window_days > 0:
            if state.priority <= 2:
                # High priority overrides consolidation
                return HeuristicDecision(
                    trm_type="to_execution",
                    action=1,  # release immediately
                    quantity=state.quantity,
                    reasoning=f"SAP shipment: TO {state.to_id} released despite "
                              f"low load ({state.current_load_pct:.0%}) -- priority={state.priority}.",
                    erp_params_used={"priority": state.priority, "MIN_LOAD_PCT": min_load_pct},
                )
            return HeuristicDecision(
                trm_type="to_execution",
                action=2,  # consolidate / hold
                quantity=state.quantity,
                reasoning=f"SAP shipment: TO {state.to_id} held for consolidation. "
                          f"Load={state.current_load_pct:.0%} < minimum={min_load_pct:.0%}. "
                          f"Window={state.consolidation_window_days}d.",
                erp_params_used={"MIN_LOAD_PCT": min_load_pct},
            )

        # Check if expediting needed
        if state.priority <= 1 and state.is_expeditable:
            mode = "air" if state.transport_mode in ("sea", "rail") else state.transport_mode
            return HeuristicDecision(
                trm_type="to_execution",
                action=3,  # expedite
                quantity=state.quantity,
                reasoning=f"SAP shipment: expedite TO {state.to_id}. "
                          f"Priority={state.priority}, switching to {mode}.",
                erp_params_used={"original_mode": state.transport_mode, "expedite_mode": mode},
            )

        return HeuristicDecision(
            trm_type="to_execution",
            action=1,  # release normally
            quantity=state.quantity,
            reasoning=f"SAP shipment: release TO {state.to_id}. "
                      f"Mode={state.transport_mode}, load={state.current_load_pct:.0%}.",
            erp_params_used={"transport_mode": state.transport_mode},
        )

    # ===================================================================
    # 7. QUALITY DISPOSITION -- SAP QM defect classification
    # ===================================================================

    def compute_quality_disposition(
        self, state: QualityState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """SAP QM quality decision based on defect classification (QMFE).

        SAP QM disposition options:
          - Accept (usage decision = accept)
          - Rework (create rework production order)
          - Scrap (goods issue to scrap)
          - Return to vendor
          - Use-as-is (accept with deviation)

        Decision tree:
          Critical defect -> scrap (unless rework cost << unit cost)
          Major defect    -> rework if economical, else scrap
          Minor defect    -> accept / use-as-is
        """
        erp = params.erp_params

        # SAP QM catalog (QPCD) defect severity thresholds
        rework_threshold = erp.get("REWORK_COST_THRESHOLD_PCT", 0.50)
        # Rework only if rework cost < threshold % of unit cost

        rework_is_economical = (
            state.rework_cost_per_unit < state.unit_cost * rework_threshold
        )

        if state.defect_severity == "critical":
            if state.customer_impact:
                return HeuristicDecision(
                    trm_type="quality_disposition",
                    action=3,  # scrap
                    quantity=state.quantity,
                    reasoning=f"SAP QM: SCRAP lot {state.lot_id}. Critical defect "
                              f"({state.defect_type}) with customer impact.",
                    erp_params_used={"severity": "critical", "customer_impact": True},
                )
            if rework_is_economical:
                return HeuristicDecision(
                    trm_type="quality_disposition",
                    action=2,  # rework
                    quantity=state.quantity,
                    reasoning=f"SAP QM: REWORK lot {state.lot_id}. Critical defect but "
                              f"rework cost ({state.rework_cost_per_unit:.2f}) < "
                              f"threshold ({state.unit_cost * rework_threshold:.2f}).",
                    erp_params_used={"rework_cost": state.rework_cost_per_unit},
                )
            return HeuristicDecision(
                trm_type="quality_disposition",
                action=3,  # scrap
                quantity=state.quantity,
                reasoning=f"SAP QM: SCRAP lot {state.lot_id}. Critical defect, rework uneconomical.",
                erp_params_used={"severity": "critical"},
            )

        if state.defect_severity == "major":
            if rework_is_economical:
                return HeuristicDecision(
                    trm_type="quality_disposition",
                    action=2,  # rework
                    quantity=state.quantity,
                    reasoning=f"SAP QM: REWORK lot {state.lot_id}. Major {state.defect_type} defect, "
                              f"rework economical.",
                    erp_params_used={"severity": "major", "rework_cost": state.rework_cost_per_unit},
                )
            return HeuristicDecision(
                trm_type="quality_disposition",
                action=3,  # scrap
                quantity=state.quantity,
                reasoning=f"SAP QM: SCRAP lot {state.lot_id}. Major defect, rework uneconomical.",
                erp_params_used={"severity": "major"},
            )

        # Minor defect: accept / use-as-is
        return HeuristicDecision(
            trm_type="quality_disposition",
            action=1,  # accept
            quantity=state.quantity,
            reasoning=f"SAP QM: ACCEPT lot {state.lot_id}. Minor {state.defect_type} defect.",
            erp_params_used={"severity": "minor"},
        )

    # ===================================================================
    # 8. MAINTENANCE SCHEDULING -- SAP PM MTBF-driven
    # ===================================================================

    def compute_maintenance_scheduling(
        self, state: MaintenanceState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """SAP Plant Maintenance (PM) preventive scheduling.

        SAP PM uses maintenance plans (MPLA) with:
          - Time-based strategy: fixed intervals (e.g., every 720h)
          - Performance-based: counter readings (operating hours, cycles)
          - Condition-based: sensor thresholds (SAP PM with IoT)

        Heuristic: MTBF-driven scheduling from PM history (MHIS).
        Schedule PM when hours_since_last_pm > threshold % of MTBF.
        Defer if upcoming production load is high and asset is non-critical.
        """
        erp = params.erp_params

        # SAP PM strategy: schedule at configured % of MTBF
        pm_trigger_pct = erp.get("PM_TRIGGER_PCT", 0.80)
        # Deferral allowed for B/C criticality if production load is high
        defer_load_threshold = erp.get("DEFER_LOAD_THRESHOLD", 0.90)

        hours_threshold = state.mtbf_days * 24 * pm_trigger_pct
        pm_due = state.hours_since_last_pm >= hours_threshold

        if not pm_due:
            remaining_hours = hours_threshold - state.hours_since_last_pm
            return HeuristicDecision(
                trm_type="maintenance_scheduling",
                action=0,  # no action
                quantity=0.0,
                reasoning=f"SAP PM: asset {state.asset_id} not due. "
                          f"Hours since PM={state.hours_since_last_pm:.0f}, "
                          f"threshold={hours_threshold:.0f} ({pm_trigger_pct:.0%} of MTBF). "
                          f"Next PM in ~{remaining_hours:.0f}h.",
                erp_params_used={"PM_TRIGGER_PCT": pm_trigger_pct, "MTBF_days": state.mtbf_days},
            )

        # PM is due -- check if deferral is appropriate
        if state.criticality in ("B", "C") and state.upcoming_production_load > defer_load_threshold:
            return HeuristicDecision(
                trm_type="maintenance_scheduling",
                action=2,  # defer
                quantity=0.0,
                reasoning=f"SAP PM: DEFER asset {state.asset_id}. PM due but "
                          f"production load={state.upcoming_production_load:.0%} > "
                          f"threshold={defer_load_threshold:.0%}. "
                          f"Criticality={state.criticality} allows deferral.",
                erp_params_used={
                    "DEFER_LOAD_THRESHOLD": defer_load_threshold,
                    "criticality": state.criticality,
                },
            )

        return HeuristicDecision(
            trm_type="maintenance_scheduling",
            action=1,  # schedule PM
            quantity=state.mttr_hours,
            reasoning=f"SAP PM: SCHEDULE PM for asset {state.asset_id}. "
                      f"Hours since PM={state.hours_since_last_pm:.0f} >= "
                      f"threshold={hours_threshold:.0f}. "
                      f"Criticality={state.criticality}, MTTR={state.mttr_hours:.1f}h.",
            erp_params_used={
                "PM_TRIGGER_PCT": pm_trigger_pct,
                "criticality": state.criticality,
                "MTBF_days": state.mtbf_days,
            },
        )

    # ===================================================================
    # 9. SUBCONTRACTING -- SAP external procurement (BESKZ=X/F)
    # ===================================================================

    def compute_subcontracting(
        self, state: SubcontractingState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """SAP subcontracting decision (MARC.BESKZ = X for both, F for external).

        SAP uses procurement type (BESKZ) to determine routing:
          E = in-house production only
          F = external procurement only
          X = both possible -- MRP considers costs and capacity

        When BESKZ=X, SAP's decision is driven by:
          1. Internal capacity availability
          2. Cost comparison (internal vs external including quality risk)
          3. Lead time comparison
        """
        erp = params.erp_params
        beskz = erp.get("BESKZ", "X")

        # Fixed routing from SAP config
        if beskz == "E":
            return HeuristicDecision(
                trm_type="subcontracting",
                action=1,  # internal
                quantity=state.quantity_needed,
                reasoning=f"SAP: BESKZ=E (in-house only). Route {state.product_id} internally.",
                erp_params_used={"BESKZ": "E"},
            )
        if beskz == "F":
            return HeuristicDecision(
                trm_type="subcontracting",
                action=2,  # external
                quantity=state.quantity_needed,
                reasoning=f"SAP: BESKZ=F (external only). Route {state.product_id} to subcontractor.",
                erp_params_used={"BESKZ": "F"},
            )

        # BESKZ=X: evaluate make-vs-buy
        internal_possible = state.internal_capacity_available >= state.quantity_needed

        if not internal_possible:
            # Must subcontract (no internal capacity)
            overflow = state.quantity_needed - state.internal_capacity_available
            if state.internal_capacity_available > 0:
                return HeuristicDecision(
                    trm_type="subcontracting",
                    action=3,  # split
                    quantity=overflow,
                    reasoning=f"SAP: BESKZ=X split routing. Internal capacity "
                              f"({state.internal_capacity_available:.1f}) insufficient "
                              f"for {state.quantity_needed:.1f}. Subcontract {overflow:.1f}.",
                    erp_params_used={"BESKZ": "X", "split": True},
                )
            return HeuristicDecision(
                trm_type="subcontracting",
                action=2,  # external
                quantity=state.quantity_needed,
                reasoning=f"SAP: BESKZ=X but no internal capacity. Full subcontract.",
                erp_params_used={"BESKZ": "X"},
            )

        # Both possible -- cost-based decision
        # Include quality risk premium in external cost
        quality_premium = state.external_cost_per_unit * state.quality_risk_external
        effective_external_cost = state.external_cost_per_unit + quality_premium

        if state.internal_cost_per_unit <= effective_external_cost:
            return HeuristicDecision(
                trm_type="subcontracting",
                action=1,  # internal
                quantity=state.quantity_needed,
                reasoning=f"SAP: BESKZ=X, internal cheaper. "
                          f"Internal={state.internal_cost_per_unit:.2f}/u vs "
                          f"external={effective_external_cost:.2f}/u "
                          f"(incl quality risk premium {quality_premium:.2f}).",
                erp_params_used={"BESKZ": "X", "cost_comparison": "internal"},
            )

        return HeuristicDecision(
            trm_type="subcontracting",
            action=2,  # external
            quantity=state.quantity_needed,
            reasoning=f"SAP: BESKZ=X, external cheaper. "
                      f"Internal={state.internal_cost_per_unit:.2f}/u vs "
                      f"external={effective_external_cost:.2f}/u.",
            erp_params_used={"BESKZ": "X", "cost_comparison": "external"},
        )

    # ===================================================================
    # 10. FORECAST ADJUSTMENT -- SAP APO demand sensing
    # ===================================================================

    def compute_forecast_adjustment(
        self, state: ForecastAdjustmentState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """SAP APO/IBP demand sensing adjustment.

        SAP IBP handles forecast adjustments via:
          - Statistical forecast as base
          - Demand sensing (short-term ML correction)
          - Manual planner overrides (consensus round)

        For signal-based adjustments, SAP IBP applies a dampening factor
        to prevent overreaction.  The adjustment is:
          adjusted = current * (1 + direction * magnitude * dampening)

        SAP VRMOD/VINT from MARC control how forecasts are consumed
        (backward, forward, or period-based).
        """
        erp = params.erp_params

        # SAP IBP dampening factor: prevents overreaction to signals
        dampening = erp.get("FORECAST_DAMPENING", 0.50)
        # Minimum confidence to act on signal
        min_confidence = erp.get("FORECAST_MIN_CONFIDENCE", 0.40)

        if state.signal_confidence < min_confidence:
            return HeuristicDecision(
                trm_type="forecast_adjustment",
                action=0,  # no adjustment
                quantity=state.current_forecast,
                reasoning=f"SAP IBP: signal confidence ({state.signal_confidence:.2f}) "
                          f"below threshold ({min_confidence:.2f}). No adjustment.",
                erp_params_used={"FORECAST_DAMPENING": dampening, "MIN_CONFIDENCE": min_confidence},
            )

        direction_mult = 1.0 if state.signal_direction == "increase" else -1.0
        if state.signal_direction == "unchanged":
            direction_mult = 0.0

        raw_adjustment_pct = state.signal_magnitude_pct * dampening
        adjustment = state.current_forecast * direction_mult * (raw_adjustment_pct / 100.0)
        new_forecast = max(0.0, state.current_forecast + adjustment)

        action = 1 if direction_mult > 0 else (2 if direction_mult < 0 else 0)

        return HeuristicDecision(
            trm_type="forecast_adjustment",
            action=action,
            quantity=new_forecast,
            reasoning=f"SAP IBP demand sensing: {state.signal_direction} signal "
                      f"({state.signal_type}, conf={state.signal_confidence:.2f}). "
                      f"Raw magnitude={state.signal_magnitude_pct:.1f}%, "
                      f"dampened={raw_adjustment_pct:.1f}%. "
                      f"Forecast: {state.current_forecast:.1f} -> {new_forecast:.1f}.",
            erp_params_used={
                "FORECAST_DAMPENING": dampening,
                "signal_type": state.signal_type,
                "VRMOD": erp.get("VRMOD", ""),
            },
        )

    # ===================================================================
    # 11. INVENTORY BUFFER -- SAP safety stock recalculation
    # ===================================================================

    def compute_inventory_buffer(
        self, state: InventoryBufferState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """SAP safety stock recalculation (MARC.EISBE or MRP-computed).

        SAP calculates safety stock using:
          - Fixed (MARC.EISBE): static value, manually maintained
          - Service level (MARC.PRMOD=V): z-score * sigma_demand * sqrt(LT)
          - Range of coverage: MARC.SHZET (days of coverage for SS)

        Heuristic: recalculate SS using the z-score formula when demand
        variability or lead time changes significantly.
        """
        erp = params.erp_params

        # SAP MARC.PRMOD: V=automatic (service level), S=fixed (EISBE), empty=no SS
        prmod = erp.get("PRMOD", "V")

        if prmod == "S":
            # Fixed SS from SAP (MARC.EISBE) -- no adjustment
            return HeuristicDecision(
                trm_type="inventory_buffer",
                action=0,
                quantity=state.current_safety_stock,
                reasoning=f"SAP: PRMOD=S (fixed safety stock). "
                          f"EISBE={state.current_safety_stock:.1f}. No automatic adjustment.",
                erp_params_used={"PRMOD": "S", "EISBE": state.current_safety_stock},
            )

        if prmod == "" or prmod is None:
            return HeuristicDecision(
                trm_type="inventory_buffer",
                action=0,
                quantity=0.0,
                reasoning="SAP: no safety stock profile configured (PRMOD empty).",
                erp_params_used={"PRMOD": ""},
            )

        # PRMOD=V: automatic service-level-based calculation
        # z-score lookup (approximation for common service levels)
        z_scores = {
            0.90: 1.282, 0.92: 1.405, 0.95: 1.645, 0.97: 1.881,
            0.98: 2.054, 0.99: 2.326, 0.995: 2.576,
        }
        # Find closest service level
        sl = state.service_level_target
        z = z_scores.get(round(sl, 3), 1.645)  # default to 95% if not found
        # Interpolate for non-standard levels
        if z == 1.645 and sl != 0.95:
            for target_sl, target_z in sorted(z_scores.items()):
                if target_sl >= sl:
                    z = target_z
                    break

        # SS = z * sigma_demand * sqrt(lead_time)
        sigma_demand = state.avg_daily_demand * state.demand_cv
        new_ss = z * sigma_demand * math.sqrt(max(1.0, state.lead_time_days))

        # Include lead time variability if available
        if state.lead_time_cv > 0:
            sigma_lt = state.lead_time_days * state.lead_time_cv
            # Combined: sqrt((z*sigma_d)^2 * LT + (z*sigma_lt)^2 * d^2)
            new_ss = math.sqrt(
                (z * sigma_demand) ** 2 * state.lead_time_days
                + (z * sigma_lt * state.avg_daily_demand) ** 2
            )

        change_pct = abs(new_ss - state.current_safety_stock) / max(state.current_safety_stock, 1.0) * 100

        # Only recommend change if delta > 10% (avoid noise)
        if change_pct < 10.0:
            return HeuristicDecision(
                trm_type="inventory_buffer",
                action=0,
                quantity=state.current_safety_stock,
                reasoning=f"SAP SS recalc: delta={change_pct:.1f}% (< 10% threshold). "
                          f"Current={state.current_safety_stock:.1f}, calculated={new_ss:.1f}. No change.",
                erp_params_used={"PRMOD": "V", "z": z, "SL": sl},
            )

        action = 1 if new_ss > state.current_safety_stock else 2
        direction = "increase" if action == 1 else "decrease"

        return HeuristicDecision(
            trm_type="inventory_buffer",
            action=action,
            quantity=new_ss,
            reasoning=f"SAP SS recalc: {direction} from {state.current_safety_stock:.1f} "
                      f"to {new_ss:.1f} ({change_pct:.1f}% change). "
                      f"SL={sl:.0%}, z={z:.3f}, sigma_d={sigma_demand:.1f}, "
                      f"LT={state.lead_time_days}d.",
            erp_params_used={
                "PRMOD": "V",
                "z_score": z,
                "service_level": sl,
                "sigma_demand": sigma_demand,
            },
        )
