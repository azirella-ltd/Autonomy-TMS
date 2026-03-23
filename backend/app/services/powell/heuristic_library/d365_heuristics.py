"""
Microsoft Dynamics 365 Finance & Operations Heuristic Implementations.

Mirrors D365 F&O Master Planning logic from ReqItemTable (item coverage
settings), ReqGroup (coverage groups), InventItemPurchSetup (vendor defaults),
BOMVersion/RouteVersion (BOM and route), and ProdParameters.

Key D365 references:
  - ReqItemTable.CovRule       -> CoverageCode (0=None, 1=Period, 2=Requirement, 3=Min/Max, 4=DDMRP)
  - ReqItemTable.CovTimeFence  -> coverage time fence in days
  - ReqItemTable.ReqTimeFence  -> requirement time fence (frozen horizon)
  - ReqItemTable.FrozenTimeFence -> firm planned order time fence
  - ReqItemTable.PositiveDays  -> positive days (receipts considered)
  - ReqItemTable.NegativeDays  -> negative days (issues considered)
  - InventItemPurchSetup       -> preferred vendor, lead time, MOQ
  - PurchParameters.PriceDiscAdmPolicy -> purchase price policies
  - SalesParameters.ATPTimeFence -> ATP check horizon
  - SalesParameters.DelivDateControl -> delivery date control group
  - ProdParameters.RoutePlanning -> scheduling method (operations/job)

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


class D365Heuristics(BaseHeuristics):
    """Microsoft Dynamics 365 F&O Master Planning heuristic implementations.

    D365 Master Planning (and Planning Optimization) uses coverage codes
    to determine replenishment strategy per item-warehouse combination.
    The planning engine collects requirements within a coverage time fence
    and generates planned orders based on the coverage rule.
    """

    # ===================================================================
    # 1. REPLENISHMENT -- D365 coverage code logic
    # ===================================================================

    def compute_replenishment(
        self, state: ReplenishmentState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """D365 Master Planning replenishment based on CoverageCode.

        D365 coverage codes:
          0 (None):        No planning -- manual only
          1 (Period):      Collect requirements within period, single order
          2 (Requirement): One planned order per requirement (lot-for-lot)
          3 (Min/Max):     Maintain inventory between min and max levels
          4 (DDMRP):       Demand-Driven buffer zones

        D365 Planning Optimization collects net requirements within the
        coverage time fence (CovTimeFence), then applies the coverage rule
        to generate planned orders.  Positive days and negative days control
        how far the engine looks for existing supply/demand.
        """
        method = params.planning_method
        erp = params.erp_params

        # D365: respect frozen time fence (ReqItemTable.FrozenTimeFence)
        frozen_fence = params.frozen_horizon_days
        if frozen_fence > 0:
            sim_day = erp.get("sim_day", 0)
            if sim_day < frozen_fence:
                return HeuristicDecision(
                    trm_type="po_creation",
                    action=0,
                    quantity=0.0,
                    reasoning=f"D365: within frozen time fence ({frozen_fence}d). "
                              f"No new planned orders allowed.",
                    erp_params_used={"FrozenTimeFence": frozen_fence},
                )

        # D365 positive/negative days
        positive_days = erp.get("PositiveDays", 0)
        negative_days = erp.get("NegativeDays", 0)

        if method == "NO_PLANNING":
            return HeuristicDecision(
                trm_type="po_creation",
                action=0,
                quantity=0.0,
                reasoning="D365: CoverageCode=0 (None). No automatic planning.",
                erp_params_used={"CovRule": 0},
            )

        if method == "PERIOD_BATCHING":
            raw_qty = self._net_period_coverage(state, params)
            reason_prefix = "D365 CoverageCode=1 (Period)"
        elif method == "LOT_FOR_LOT":
            raw_qty = self._net_requirement(state, params)
            reason_prefix = "D365 CoverageCode=2 (Requirement)"
        elif method == "MIN_MAX":
            raw_qty = self._net_min_max(state, params)
            reason_prefix = "D365 CoverageCode=3 (Min/Max)"
        elif method == "DDMRP":
            raw_qty = self._net_ddmrp(state, params)
            reason_prefix = "D365 CoverageCode=4 (DDMRP)"
        elif method in ("REORDER_POINT", "FORECAST_BASED", "MRP_AUTO", "MRP_DETERMINISTIC"):
            # Map SAP-style methods to nearest D365 equivalent
            raw_qty = self._net_requirement(state, params)
            reason_prefix = f"D365 (mapped from {method})"
        else:
            raw_qty = self._net_requirement(state, params)
            reason_prefix = f"D365 fallback (method={method})"

        if raw_qty <= 0:
            return HeuristicDecision(
                trm_type="po_creation",
                action=0,
                quantity=0.0,
                reasoning=f"{reason_prefix}: no net requirement. "
                          f"IP={state.inventory_position:.1f}.",
                erp_params_used={"CovRule": method, "IP": state.inventory_position},
            )

        # D365 lot sizing + order modifications
        lot_qty = apply_lot_sizing(raw_qty, state.inventory_position, params)
        if lot_qty <= 0:
            return HeuristicDecision(
                trm_type="po_creation", action=0, quantity=0.0,
                reasoning=f"{reason_prefix}: lot sizing reduced to zero.",
                erp_params_used={"CovRule": method},
            )

        final_qty = apply_order_modifications(lot_qty, params)

        return HeuristicDecision(
            trm_type="po_creation",
            action=1,
            quantity=final_qty,
            reasoning=f"{reason_prefix}: net={raw_qty:.1f}, lot={lot_qty:.1f}, "
                      f"final={final_qty:.1f}. PositiveDays={positive_days}, "
                      f"NegativeDays={negative_days}.",
            erp_params_used={
                "CovRule": method,
                "PositiveDays": positive_days,
                "NegativeDays": negative_days,
                "CovTimeFence": erp.get("CovTimeFence", params.review_period_days),
            },
        )

    def _net_period_coverage(
        self, state: ReplenishmentState, params: ERPPlanningParams,
    ) -> float:
        """D365 CoverageCode=1: collect demand within period, generate one order.

        D365 Period coverage groups all net requirements within a coverage
        period (daily, weekly, monthly) into a single planned order.  The
        planned order quantity covers the total net requirement for the period.

        Unlike SAP WB/MB which only orders on boundary days, D365 Period
        coverage always evaluates but the planned order covers the full period.
        """
        erp = params.erp_params
        coverage_period_days = erp.get("CovTimeFence", params.review_period_days)

        # D365: only create one order per period boundary
        period_type = erp.get("CoveragePeriod", "weekly")
        if period_type == "weekly" and state.day_of_week != 0:
            return 0.0
        if period_type == "monthly" and state.day_of_month != 1:
            return 0.0

        # Collect gross requirement for the coverage period
        gross_requirement = state.avg_daily_demand * coverage_period_days

        # D365: considers positive days (how far to look for existing supply)
        positive_days = erp.get("PositiveDays", 0)
        # Existing scheduled receipts within positive days offset requirement
        pipeline_offset = min(state.pipeline_qty, gross_requirement) if positive_days > 0 else 0.0

        net_need = gross_requirement + params.safety_stock - state.inventory_position - pipeline_offset
        return max(0.0, net_need)

    def _net_requirement(
        self, state: ReplenishmentState, params: ERPPlanningParams,
    ) -> float:
        """D365 CoverageCode=2: one planned order per net requirement (lot-for-lot).

        D365 Requirement coverage generates a planned order for each individual
        net requirement.  In single-period simulation, this is the daily net:
          net = demand + safety_stock - inventory_position

        D365 considers negative days: how many days of past-due demand to include.
        """
        erp = params.erp_params
        negative_days = erp.get("NegativeDays", 0)

        # Include backlog as past-due demand (up to NegativeDays)
        backlog_demand = state.backlog if negative_days > 0 else 0.0

        net_need = (
            state.avg_daily_demand
            + backlog_demand
            + params.safety_stock
            - state.inventory_position
        )
        return max(0.0, net_need)

    def _net_min_max(
        self, state: ReplenishmentState, params: ERPPlanningParams,
    ) -> float:
        """D365 CoverageCode=3: if on-hand < minimum, order to maximum.

        D365 Min/Max uses ReqItemTable.ReqMinQty and ReqItemTable.ReqMaxQty.
        When projected on-hand falls below minimum, a planned order is
        created to bring inventory up to the maximum level.
        """
        minimum = params.reorder_point   # maps to ReqMinQty
        maximum = params.max_inventory if params.max_inventory > 0 else params.order_up_to

        if state.inventory_position < minimum:
            return max(0.0, maximum - state.inventory_position)
        return 0.0

    def _net_ddmrp(
        self, state: ReplenishmentState, params: ERPPlanningParams,
    ) -> float:
        """D365 CoverageCode=4: DDMRP buffer zone logic.

        D365 DDMRP uses three buffer zones:
          Red zone   = base (lead time demand) + safety (variability)
          Yellow zone = red + average daily usage * decoupled lead time
          Green zone  = yellow + min(MOQ, lead_time_demand, order_cycle)

        Net Flow Position = on_hand + on_order - qualified demand
        If NFP < top_of_yellow -> order to top_of_green

        For phase 1: approximate zones from available parameters.
        """
        erp = params.erp_params

        # DDMRP zone calculations
        adu = state.avg_daily_demand  # Average Daily Usage
        dlt = params.lead_time_days   # Decoupled Lead Time
        variability_factor = erp.get("DDMRP_VARIABILITY_FACTOR", 0.50)
        lead_time_factor = erp.get("DDMRP_LEAD_TIME_FACTOR", 0.50)

        # Red zone
        red_base = adu * dlt * lead_time_factor
        red_safety = red_base * variability_factor
        red_zone = red_base + red_safety

        # Yellow zone
        yellow_zone = adu * dlt

        # Green zone: max of MOQ, lead_time_demand, or order_cycle_demand
        green_lot = max(
            params.min_order_quantity,
            adu * dlt,
            adu * params.review_period_days if params.review_period_days > 0 else 0.0,
        )
        green_zone = green_lot

        top_of_red = red_zone
        top_of_yellow = red_zone + yellow_zone
        top_of_green = red_zone + yellow_zone + green_zone

        # Net Flow Position
        nfp = state.on_hand + state.pipeline_qty - state.backlog

        if nfp <= top_of_yellow:
            order_qty = top_of_green - nfp
            return max(0.0, order_qty)
        return 0.0

    # ===================================================================
    # 2. ATP ALLOCATION -- D365 delivery date control
    # ===================================================================

    def compute_atp_allocation(
        self, state: ATPState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """D365 ATP based on delivery date control group.

        D365 delivery date control options (SalesParameters.DelivDateControl):
          0 (None):           No ATP check, confirm requested date
          1 (Sales lead time): Confirm if within sales lead time
          2 (ATP):            Check ATP based on cumulative on-hand + receipts
          3 (ATP + issue margin): ATP with safety margin for issues
          4 (CTP):            Capable-to-Promise (checks capacity + materials)

        D365 ATP accumulates supply (on-hand + scheduled receipts) and subtracts
        demand (sales orders + forecast) over the ATP time fence to find the
        earliest date when the full quantity can be promised.
        """
        erp = params.erp_params
        delivery_control = erp.get("DelivDateControl", 2)
        atp_time_fence = erp.get("ATPTimeFence", 30)

        if delivery_control == 0:
            # No check: always confirm
            return HeuristicDecision(
                trm_type="atp_executor",
                action=1,
                quantity=state.order_qty,
                reasoning=f"D365: DelivDateControl=None. Auto-confirm {state.order_qty:.1f}.",
                erp_params_used={"DelivDateControl": 0},
            )

        # D365 ATP: available = on_hand + pipeline - already allocated - confirmed
        cumulative_atp = (
            state.available_inventory
            + state.pipeline_qty
            - state.allocated_inventory
            - state.confirmed_orders
        )

        # ATP + issue margin: reduce available by a safety margin
        if delivery_control == 3:
            issue_margin_days = erp.get("ATPIssueMargin", 1)
            margin_demand = state.forecast_remaining / max(1, atp_time_fence) * issue_margin_days
            cumulative_atp -= margin_demand

        if cumulative_atp >= state.order_qty:
            return HeuristicDecision(
                trm_type="atp_executor",
                action=1,
                quantity=state.order_qty,
                reasoning=f"D365 ATP: full confirmation. Cumulative ATP={cumulative_atp:.1f} "
                          f">= order={state.order_qty:.1f}. "
                          f"DelivDateControl={delivery_control}.",
                erp_params_used={"DelivDateControl": delivery_control, "ATPTimeFence": atp_time_fence},
            )

        if cumulative_atp > 0:
            return HeuristicDecision(
                trm_type="atp_executor",
                action=2,  # partial
                quantity=cumulative_atp,
                reasoning=f"D365 ATP: partial. Cumulative ATP={cumulative_atp:.1f} "
                          f"< order={state.order_qty:.1f}. "
                          f"Partial confirm {cumulative_atp:.1f}.",
                erp_params_used={"DelivDateControl": delivery_control},
            )

        # CTP fallback: check if production could fulfill
        if delivery_control == 4:
            return HeuristicDecision(
                trm_type="atp_executor",
                action=4,  # CTP check needed
                quantity=0.0,
                reasoning=f"D365 CTP: no ATP available. Requires capacity/material check "
                          f"for {state.order_qty:.1f}. DelivDateControl=CTP.",
                erp_params_used={"DelivDateControl": 4},
            )

        return HeuristicDecision(
            trm_type="atp_executor",
            action=0,
            quantity=0.0,
            reasoning=f"D365 ATP: no availability. ATP={cumulative_atp:.1f}.",
            erp_params_used={"DelivDateControl": delivery_control},
        )

    # ===================================================================
    # 3. INVENTORY REBALANCING -- D365 intercompany/transfer planning
    # ===================================================================

    def compute_rebalancing(
        self, state: RebalancingState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """D365 transfer order planning between warehouses.

        D365 uses intercompany planning and transfer orders:
          - Planning Optimization generates planned transfer orders
          - Based on coverage settings at destination warehouse
          - Source must have sufficient on-hand above safety stock

        D365 planning calculates days-of-supply at each location and
        balances by generating transfer planned orders when destination
        is below coverage and source has surplus.
        """
        erp = params.erp_params

        # D365: calculate days of supply at each location
        source_dos = (
            state.source_on_hand / max(state.source_avg_demand, 0.01)
        )
        target_dos = (
            state.target_on_hand / max(state.target_avg_demand, 0.01)
        )
        target_dos_needed = (
            state.target_safety_stock / max(state.target_avg_demand, 0.01)
        )

        source_excess = state.source_on_hand - state.source_safety_stock - state.source_backlog
        target_deficit = state.target_safety_stock + state.target_backlog - state.target_on_hand

        if source_excess <= 0 or target_deficit <= 0:
            return HeuristicDecision(
                trm_type="inventory_rebalancing",
                action=0,
                quantity=0.0,
                reasoning=f"D365 transfer planning: no transfer needed. "
                          f"Source DOS={source_dos:.1f}d, target DOS={target_dos:.1f}d.",
                erp_params_used={},
            )

        transfer_qty = min(source_excess, target_deficit)

        # D365: apply transfer lead time to check if timely
        min_transfer = erp.get("TransferMinQty", 0.0)
        if transfer_qty < min_transfer:
            return HeuristicDecision(
                trm_type="inventory_rebalancing",
                action=0,
                quantity=0.0,
                reasoning=f"D365: transfer qty={transfer_qty:.1f} below minimum={min_transfer:.1f}.",
                erp_params_used={"TransferMinQty": min_transfer},
            )

        return HeuristicDecision(
            trm_type="inventory_rebalancing",
            action=1,
            quantity=transfer_qty,
            reasoning=f"D365 transfer order: {transfer_qty:.1f} units. "
                      f"Source DOS={source_dos:.1f}d (excess={source_excess:.1f}), "
                      f"Target DOS={target_dos:.1f}d (deficit={target_deficit:.1f}). "
                      f"Transfer LT={state.transfer_lead_time_days:.0f}d.",
            erp_params_used={
                "source_dos": source_dos,
                "target_dos": target_dos,
                "transfer_lead_time": state.transfer_lead_time_days,
            },
        )

    # ===================================================================
    # 4. ORDER TRACKING -- D365 action/futures messages
    # ===================================================================

    def compute_order_tracking(
        self, state: OrderTrackingState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """D365 action and futures messages from Planning Optimization.

        D365 generates action messages:
          - Advance:    Move receipt date earlier (demand moved up)
          - Postpone:   Move receipt date later (demand moved out)
          - Increase:   Increase order quantity
          - Decrease:   Decrease order quantity
          - Cancel:     Cancel planned order (no longer needed)

        And futures messages when a requirement cannot be met by the
        requested date, suggesting the earliest possible date.

        Heuristic: check overdue, partial, and reliability indicators.
        """
        erp = params.erp_params
        action_msg_enabled = erp.get("ActionMessages", True)
        futures_msg_enabled = erp.get("FuturesMessages", True)

        actions = []
        severity = 0

        if state.days_overdue > 0:
            if futures_msg_enabled:
                actions.append(
                    f"D365 Futures: overdue {state.days_overdue:.0f}d -- "
                    f"earliest receipt delayed"
                )
            severity = max(severity, 2)

            if action_msg_enabled and state.days_overdue > 5:
                actions.append("D365 Action: consider expediting or alternate sourcing")
                severity = max(severity, 3)

        if state.quantity_received > 0 and state.quantity_received < state.quantity_ordered:
            shortfall = state.quantity_ordered - state.quantity_received
            actions.append(f"D365: partial receipt, shortfall={shortfall:.1f}")
            severity = max(severity, 1)

        if state.supplier_on_time_rate < 0.85:
            actions.append(
                f"D365: vendor performance below target "
                f"({state.supplier_on_time_rate:.0%} OTD)"
            )
            severity = max(severity, 1)

        if state.is_critical and severity > 0:
            severity = max(severity, 3)
            actions.append("D365: critical item -- escalate")

        if not actions:
            return HeuristicDecision(
                trm_type="order_tracking",
                action=0,
                quantity=0.0,
                reasoning=f"D365: order {state.order_id} on track. "
                          f"Status={state.current_status}.",
                erp_params_used={},
            )

        return HeuristicDecision(
            trm_type="order_tracking",
            action=severity,
            quantity=state.quantity_ordered - state.quantity_received,
            reasoning=f"D365 exception: {state.order_id} -- {'; '.join(actions)}.",
            erp_params_used={
                "ActionMessages": action_msg_enabled,
                "FuturesMessages": futures_msg_enabled,
            },
        )

    # ===================================================================
    # 5. MO EXECUTION -- D365 route-based scheduling
    # ===================================================================

    def compute_mo_execution(
        self, state: MOExecutionState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """D365 production order scheduling (operations / job scheduling).

        D365 production scheduling modes (ProdParameters.RoutePlanning):
          - Operations scheduling: rough capacity check by operation
          - Job scheduling: detailed scheduling to individual resources
          - Finite/Infinite capacity

        D365 allows operation overlap (next operation starts before
        previous finishes) controlled by RouteOprTable.OprOverlap.

        Sequencing is route-based: follow the defined production route.
        No native Glenday Sieve in D365, but we still apply it as an
        overlay for the Autonomy platform.
        """
        erp = params.erp_params
        scheduling_mode = erp.get("SchedulingMode", "operations")
        finite_capacity = erp.get("FiniteCapacity", False)

        required_hours = state.setup_time_hours + state.run_time_hours
        capacity_ok = state.available_capacity_hours >= required_hours

        if not capacity_ok:
            if finite_capacity:
                # D365 finite capacity: postpone to next available slot
                return HeuristicDecision(
                    trm_type="mo_execution",
                    action=4,  # defer
                    quantity=state.quantity,
                    reasoning=f"D365 {scheduling_mode}: MO {state.mo_id} deferred. "
                              f"Finite capacity -- needed={required_hours:.1f}h, "
                              f"available={state.available_capacity_hours:.1f}h.",
                    erp_params_used={"SchedulingMode": scheduling_mode, "FiniteCapacity": True},
                )
            # Infinite capacity: allow overload but flag
            return HeuristicDecision(
                trm_type="mo_execution",
                action=1,  # release with overload
                quantity=state.quantity,
                reasoning=f"D365 {scheduling_mode}: MO {state.mo_id} released with overload. "
                          f"Infinite capacity mode. Needed={required_hours:.1f}h, "
                          f"available={state.available_capacity_hours:.1f}h.",
                erp_params_used={"SchedulingMode": scheduling_mode, "FiniteCapacity": False},
            )

        # D365 operation overlap: check if overlap is configured
        overlap_pct = erp.get("OperationOverlapPct", 0)
        effective_time = required_hours * (1.0 - overlap_pct / 100.0) if overlap_pct > 0 else required_hours

        return HeuristicDecision(
            trm_type="mo_execution",
            action=1,  # release
            quantity=state.quantity,
            reasoning=f"D365 {scheduling_mode}: release MO {state.mo_id}. "
                      f"Effective time={effective_time:.1f}h "
                      f"(overlap={overlap_pct}%), "
                      f"capacity OK ({state.available_capacity_hours:.1f}h available).",
            erp_params_used={
                "SchedulingMode": scheduling_mode,
                "OperationOverlapPct": overlap_pct,
                "effective_time": effective_time,
            },
        )

    # ===================================================================
    # 6. TO EXECUTION -- D365 transportation management
    # ===================================================================

    def compute_to_execution(
        self, state: TOExecutionState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """D365 Transportation Management (TMS) for transfer orders.

        D365 TMS features:
          - Load building: consolidation by route/appointment
          - Rate shopping: compare carrier rates
          - Dock scheduling: inbound/outbound appointment management
          - Load templates for standardized shipments

        Heuristic: consolidate within load-building window, release when
        load is sufficient or priority demands it.
        """
        erp = params.erp_params
        min_load_pct = erp.get("MinLoadPct", 0.70)
        use_rate_shopping = erp.get("RateShopping", False)

        # D365 load building: hold shipments to build full loads
        if state.current_load_pct < min_load_pct and state.consolidation_window_days > 0:
            if state.priority <= 2:
                return HeuristicDecision(
                    trm_type="to_execution",
                    action=1,
                    quantity=state.quantity,
                    reasoning=f"D365 TMS: release TO {state.to_id} despite low load "
                              f"({state.current_load_pct:.0%}). High priority={state.priority}.",
                    erp_params_used={"priority": state.priority},
                )
            return HeuristicDecision(
                trm_type="to_execution",
                action=2,  # hold for load building
                quantity=state.quantity,
                reasoning=f"D365 TMS: hold TO {state.to_id} for load building. "
                          f"Current load={state.current_load_pct:.0%} < min={min_load_pct:.0%}.",
                erp_params_used={"MinLoadPct": min_load_pct},
            )

        # D365 rate shopping: compare transport modes
        if use_rate_shopping and state.is_expeditable and state.priority <= 1:
            return HeuristicDecision(
                trm_type="to_execution",
                action=3,  # expedite
                quantity=state.quantity,
                reasoning=f"D365 TMS: expedite TO {state.to_id}. "
                          f"Rate shopping selected faster mode for priority={state.priority}.",
                erp_params_used={"RateShopping": True},
            )

        return HeuristicDecision(
            trm_type="to_execution",
            action=1,
            quantity=state.quantity,
            reasoning=f"D365 TMS: release TO {state.to_id}. "
                      f"Mode={state.transport_mode}, load={state.current_load_pct:.0%}.",
            erp_params_used={"transport_mode": state.transport_mode},
        )

    # ===================================================================
    # 7. QUALITY DISPOSITION -- D365 Quality Management
    # ===================================================================

    def compute_quality_disposition(
        self, state: QualityState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """D365 Quality Management disposition.

        D365 QM uses quality orders with:
          - Quality associations (when to create quality orders)
          - Test groups and test instruments
          - Quarantine orders for suspicious material
          - Non-conformance types and severity

        D365 disposition actions:
          - Accept: release from quarantine
          - Rework: create rework production order
          - Scrap: write off as scrap
          - Return to vendor: create return order
        """
        erp = params.erp_params
        auto_accept_minor = erp.get("AutoAcceptMinor", True)

        # D365: auto-accept minor defects if configured
        if state.defect_severity == "minor" and auto_accept_minor:
            return HeuristicDecision(
                trm_type="quality_disposition",
                action=1,  # accept
                quantity=state.quantity,
                reasoning=f"D365 QM: auto-accept lot {state.lot_id}. "
                          f"Minor {state.defect_type} defect.",
                erp_params_used={"AutoAcceptMinor": True, "severity": "minor"},
            )

        # Cost-based decision for major/critical
        total_value = state.quantity * state.unit_cost
        rework_total = state.quantity * state.rework_cost_per_unit
        scrap_recovery = state.quantity * state.scrap_value_per_unit

        if state.defect_severity == "critical":
            if state.customer_impact:
                return HeuristicDecision(
                    trm_type="quality_disposition",
                    action=3,  # scrap
                    quantity=state.quantity,
                    reasoning=f"D365 QM: scrap lot {state.lot_id}. Critical defect with customer impact. "
                              f"Value loss=${total_value - scrap_recovery:.2f}.",
                    erp_params_used={"severity": "critical"},
                )
            # D365 quarantine: hold for detailed inspection
            return HeuristicDecision(
                trm_type="quality_disposition",
                action=4,  # quarantine
                quantity=state.quantity,
                reasoning=f"D365 QM: quarantine lot {state.lot_id}. "
                          f"Critical {state.defect_type} defect, pending detailed inspection.",
                erp_params_used={"severity": "critical", "quarantine": True},
            )

        # Major defect: rework vs scrap based on net cost
        rework_net_cost = rework_total  # cost to rework
        scrap_net_cost = total_value - scrap_recovery  # value lost by scrapping

        if rework_net_cost < scrap_net_cost:
            return HeuristicDecision(
                trm_type="quality_disposition",
                action=2,  # rework
                quantity=state.quantity,
                reasoning=f"D365 QM: rework lot {state.lot_id}. "
                          f"Rework cost=${rework_net_cost:.2f} < scrap loss=${scrap_net_cost:.2f}.",
                erp_params_used={"severity": "major", "rework_net": rework_net_cost},
            )

        return HeuristicDecision(
            trm_type="quality_disposition",
            action=3,  # scrap
            quantity=state.quantity,
            reasoning=f"D365 QM: scrap lot {state.lot_id}. "
                      f"Scrap loss=${scrap_net_cost:.2f} <= rework cost=${rework_net_cost:.2f}.",
            erp_params_used={"severity": "major"},
        )

    # ===================================================================
    # 8. MAINTENANCE SCHEDULING -- D365 Asset Management
    # ===================================================================

    def compute_maintenance_scheduling(
        self, state: MaintenanceState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """D365 Asset Management (formerly Dynamics AX Enterprise Asset Management).

        D365 Asset Management uses:
          - Maintenance plans (time/counter-based)
          - Maintenance rounds (grouped equipment inspections)
          - Work orders with lifecycle states
          - Integration with production scheduling (maintenance downtime)

        D365 calculates maintenance schedule based on:
          - Fixed intervals (e.g., every 30 days)
          - Counter-based (e.g., every 5000 operating hours)
          - Condition-based (IoT sensor thresholds)
        """
        erp = params.erp_params

        # D365 maintenance plan type
        plan_type = erp.get("MaintenancePlanType", "time_based")
        interval_days = erp.get("MaintenanceIntervalDays", state.mtbf_days * 0.80)

        # Check if PM is due based on plan type
        if plan_type == "counter_based":
            counter_limit = erp.get("CounterLimit", state.mtbf_days * 24 * 0.80)
            pm_due = state.current_operating_hours >= counter_limit
        else:
            # Time-based: check hours since last PM against interval
            pm_due = state.hours_since_last_pm >= (interval_days * 24)

        if not pm_due:
            return HeuristicDecision(
                trm_type="maintenance_scheduling",
                action=0,
                quantity=0.0,
                reasoning=f"D365 Asset Mgmt: asset {state.asset_id} not due. "
                          f"Plan type={plan_type}. "
                          f"Hours since PM={state.hours_since_last_pm:.0f}.",
                erp_params_used={"MaintenancePlanType": plan_type},
            )

        # D365: check work order lifecycle -- can we schedule now?
        # Consider production impact
        if state.criticality == "C" and state.upcoming_production_load > 0.85:
            return HeuristicDecision(
                trm_type="maintenance_scheduling",
                action=2,  # defer
                quantity=0.0,
                reasoning=f"D365 Asset Mgmt: defer asset {state.asset_id}. "
                          f"Low criticality (C) and high production load "
                          f"({state.upcoming_production_load:.0%}).",
                erp_params_used={"criticality": "C", "plan_type": plan_type},
            )

        return HeuristicDecision(
            trm_type="maintenance_scheduling",
            action=1,  # schedule
            quantity=state.mttr_hours,
            reasoning=f"D365 Asset Mgmt: schedule PM for asset {state.asset_id}. "
                      f"Plan type={plan_type}, criticality={state.criticality}, "
                      f"MTTR={state.mttr_hours:.1f}h.",
            erp_params_used={
                "MaintenancePlanType": plan_type,
                "criticality": state.criticality,
            },
        )

    # ===================================================================
    # 9. SUBCONTRACTING -- D365 external items / subcontracting
    # ===================================================================

    def compute_subcontracting(
        self, state: SubcontractingState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """D365 subcontracting via external items and service purchase orders.

        D365 subcontracting approaches:
          - BOM line type "Vendor" (outsourced operation)
          - Service items on purchase orders
          - Route operation with external resource

        D365 determines routing based on:
          - Default order settings (InventItemPurchSetup: make/buy flags)
          - Route version with external operations
          - Capacity constraints drive overflow to subcontractor
        """
        erp = params.erp_params
        default_order_type = erp.get("DefaultOrderType", "production")
        # D365: Production=internal, Purchase=external, Transfer=intercompany

        if default_order_type == "purchase":
            return HeuristicDecision(
                trm_type="subcontracting",
                action=2,  # external
                quantity=state.quantity_needed,
                reasoning=f"D365: default order type=Purchase. "
                          f"Route {state.product_id} to external vendor.",
                erp_params_used={"DefaultOrderType": "purchase"},
            )

        if default_order_type == "production":
            # Check capacity
            if state.internal_capacity_available >= state.quantity_needed:
                return HeuristicDecision(
                    trm_type="subcontracting",
                    action=1,  # internal
                    quantity=state.quantity_needed,
                    reasoning=f"D365: default=Production, capacity available. "
                              f"Produce {state.product_id} internally.",
                    erp_params_used={"DefaultOrderType": "production"},
                )

            # Overflow to subcontractor
            internal_qty = state.internal_capacity_available
            external_qty = state.quantity_needed - internal_qty

            if internal_qty > 0:
                return HeuristicDecision(
                    trm_type="subcontracting",
                    action=3,  # split
                    quantity=external_qty,
                    reasoning=f"D365: capacity overflow. Internal={internal_qty:.1f}, "
                              f"subcontract={external_qty:.1f}.",
                    erp_params_used={"DefaultOrderType": "production", "split": True},
                )

            return HeuristicDecision(
                trm_type="subcontracting",
                action=2,  # full external
                quantity=state.quantity_needed,
                reasoning=f"D365: no internal capacity. Full subcontract.",
                erp_params_used={"DefaultOrderType": "production"},
            )

        # Transfer (intercompany)
        return HeuristicDecision(
            trm_type="subcontracting",
            action=2,  # treated as external
            quantity=state.quantity_needed,
            reasoning=f"D365: default order type=Transfer (intercompany). "
                      f"Route to intercompany site.",
            erp_params_used={"DefaultOrderType": default_order_type},
        )

    # ===================================================================
    # 10. FORECAST ADJUSTMENT -- D365 Demand Forecasting
    # ===================================================================

    def compute_forecast_adjustment(
        self, state: ForecastAdjustmentState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """D365 demand forecast adjustment via demand forecasting module.

        D365 Demand Forecasting uses:
          - Azure Machine Learning baseline forecast
          - Manual adjustments via Demand forecast lines form
          - Forecast authorization (approve adjusted forecast)
          - Intercompany demand propagation

        D365 applies forecast reduction keys (ForecastReductionKeys) to
        control how actual demand consumes forecasts.  Adjustments are
        capped by the authorization hierarchy.
        """
        erp = params.erp_params

        # D365: adjustment authorization limit (% change allowed without approval)
        auth_limit_pct = erp.get("ForecastAuthLimitPct", 25.0)
        # D365: forecast reduction principle
        reduction_key = erp.get("ForecastReductionKey", "consumption")

        if state.signal_confidence < 0.30:
            return HeuristicDecision(
                trm_type="forecast_adjustment",
                action=0,
                quantity=state.current_forecast,
                reasoning=f"D365: signal confidence ({state.signal_confidence:.2f}) too low. "
                          f"No adjustment.",
                erp_params_used={"min_confidence": 0.30},
            )

        direction_mult = 1.0 if state.signal_direction == "increase" else -1.0
        if state.signal_direction == "unchanged":
            direction_mult = 0.0

        raw_pct = state.signal_magnitude_pct
        # D365: cap at authorization limit
        capped_pct = min(raw_pct, auth_limit_pct)
        if raw_pct > auth_limit_pct:
            needs_approval = True
        else:
            needs_approval = False

        adjustment = state.current_forecast * direction_mult * (capped_pct / 100.0)
        new_forecast = max(0.0, state.current_forecast + adjustment)

        action = 1 if direction_mult > 0 else (2 if direction_mult < 0 else 0)

        reasoning = (
            f"D365 forecast adjustment: {state.signal_direction} by {capped_pct:.1f}% "
            f"(signal={raw_pct:.1f}%, auth limit={auth_limit_pct:.1f}%). "
            f"Forecast: {state.current_forecast:.1f} -> {new_forecast:.1f}."
        )
        if needs_approval:
            reasoning += " Exceeds auth limit -- requires approval."

        return HeuristicDecision(
            trm_type="forecast_adjustment",
            action=action,
            quantity=new_forecast,
            reasoning=reasoning,
            erp_params_used={
                "ForecastAuthLimitPct": auth_limit_pct,
                "ForecastReductionKey": reduction_key,
                "needs_approval": needs_approval,
            },
        )

    # ===================================================================
    # 11. INVENTORY BUFFER -- D365 safety stock calculation
    # ===================================================================

    def compute_inventory_buffer(
        self, state: InventoryBufferState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """D365 safety stock calculation from coverage settings.

        D365 safety stock options (ReqItemTable):
          - Fixed minimum: ReqItemTable.ReqMinQty (static safety stock)
          - Days of supply: ReqItemTable.ReqMinDays (dynamic, demand-based)
          - Fulfillment key: safety stock varies by season/period
          - DDMRP zones: red zone = safety buffer

        Heuristic: recalculate based on coverage type and demand variability.
        """
        erp = params.erp_params
        ss_type = erp.get("SafetyStockType", "days_of_supply")

        if ss_type == "fixed":
            # Fixed minimum -- no automatic adjustment
            fixed_min = erp.get("ReqMinQty", state.current_safety_stock)
            return HeuristicDecision(
                trm_type="inventory_buffer",
                action=0,
                quantity=fixed_min,
                reasoning=f"D365: fixed safety stock (ReqMinQty={fixed_min:.1f}). "
                          f"No automatic adjustment.",
                erp_params_used={"SafetyStockType": "fixed", "ReqMinQty": fixed_min},
            )

        if ss_type == "days_of_supply":
            # Dynamic: safety_days * avg_daily_demand
            safety_days = erp.get("ReqMinDays", 7)
            new_ss = safety_days * state.avg_daily_demand
        elif ss_type == "service_level":
            # Z-score based (similar to SAP but using D365 terminology)
            z_map = {0.90: 1.282, 0.95: 1.645, 0.98: 2.054, 0.99: 2.326}
            sl = state.service_level_target
            z = 1.645
            for tgt, tgt_z in sorted(z_map.items()):
                if tgt >= sl:
                    z = tgt_z
                    break
            sigma = state.avg_daily_demand * state.demand_cv
            new_ss = z * sigma * math.sqrt(max(1.0, state.lead_time_days))
        else:
            # Default: days of supply fallback
            new_ss = 7 * state.avg_daily_demand

        change_pct = abs(new_ss - state.current_safety_stock) / max(state.current_safety_stock, 1.0) * 100

        if change_pct < 10.0:
            return HeuristicDecision(
                trm_type="inventory_buffer",
                action=0,
                quantity=state.current_safety_stock,
                reasoning=f"D365 SS: change={change_pct:.1f}% (below 10% threshold). "
                          f"Current={state.current_safety_stock:.1f}, calc={new_ss:.1f}.",
                erp_params_used={"SafetyStockType": ss_type},
            )

        action = 1 if new_ss > state.current_safety_stock else 2
        direction = "increase" if action == 1 else "decrease"

        return HeuristicDecision(
            trm_type="inventory_buffer",
            action=action,
            quantity=new_ss,
            reasoning=f"D365 SS: {direction} from {state.current_safety_stock:.1f} "
                      f"to {new_ss:.1f} ({change_pct:.1f}%). Type={ss_type}.",
            erp_params_used={"SafetyStockType": ss_type, "new_ss": new_ss},
        )
