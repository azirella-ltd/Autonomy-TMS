"""
Odoo Community / Enterprise Heuristic Implementations.

Mirrors Odoo replenishment logic from stock.warehouse.orderpoint (reorder
rules), mrp.bom (manufacturing BOMs), mrp.production (manufacturing orders),
and stock.picking (delivery orders / transfers).

Key Odoo references:
  - stock.warehouse.orderpoint:
      trigger='auto'    -> automatic replenishment (REORDER_POINT)
      trigger='manual'  -> manual trigger only (NO_PLANNING)
      product_min_qty   -> reorder point (minimum stock)
      product_max_qty   -> order up to level (maximum stock)
      qty_multiple      -> order rounding multiple
      route_id          -> buy, manufacture, or transfer route
  - mrp.bom:
      type='normal'     -> standard manufacturing BOM
      type='phantom'    -> phantom/kit (exploded in picking)
  - mrp.production:
      Simple FIFO scheduling (no operation overlap by default)
      date_start / date_finished for scheduling
  - stock.quant:
      quantity          -> on-hand stock per location
      reserved_quantity -> allocated/reserved
  - purchase.order:
      partner_id        -> vendor (trading partner)
  - product.supplierinfo:
      min_qty           -> minimum purchase quantity from vendor
      price             -> vendor price
      delay             -> vendor lead time in days

Odoo replenishment runs daily as a scheduled action (ir.cron).
Unlike SAP/D365, Odoo has no native frozen horizon, no forecast
consumption, and limited priority-based allocation.

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


class OdooHeuristics(BaseHeuristics):
    """Odoo Community/Enterprise planning heuristic implementations.

    Odoo uses a simpler planning model than SAP or D365:
      - Reorder rules (orderpoints) for automatic replenishment
      - No native MRP time-phased netting (Odoo MRP is BOM-only)
      - Routes determine procurement method (Buy/Manufacture/Transfer)
      - Manufacturing is FIFO with simple capacity checks

    Odoo Enterprise adds:
      - Demand forecasting (ML-based)
      - MRP scheduler (mrp.schedulerservice)
      - Quality module (quality.check)
      - Maintenance module (maintenance.request)
    """

    # ===================================================================
    # 1. REPLENISHMENT -- Odoo orderpoint logic
    # ===================================================================

    def compute_replenishment(
        self, state: ReplenishmentState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Odoo stock.warehouse.orderpoint replenishment.

        Odoo orderpoint logic (trigger='auto'):
          1. On-hand quantity drops below product_min_qty -> trigger
          2. Order quantity = product_max_qty - on_hand_qty
          3. Apply qty_multiple rounding
          4. Respect vendor minimum (product.supplierinfo.min_qty)

        Key difference from SAP/D365:
          - Odoo uses on_hand, NOT inventory position (no pipeline consideration)
          - No lead time demand coverage in the orderpoint -- just min/max
          - MRP module adds a scheduler that considers demand and WIP

        Since Odoo 14+, the scheduler considers forecasted stock
        (virtual_available = on_hand + incoming - outgoing) when the
        MRP module is installed.
        """
        method = params.planning_method
        erp = params.erp_params

        # Odoo trigger='manual': no automatic replenishment
        trigger = erp.get("trigger", "auto")
        if method == "NO_PLANNING" or trigger == "manual":
            return HeuristicDecision(
                trm_type="po_creation",
                action=0,
                quantity=0.0,
                reasoning="Odoo: orderpoint trigger=manual. No automatic replenishment.",
                erp_params_used={"trigger": "manual"},
            )

        # Odoo: use on-hand (not IP) for basic orderpoint
        # With MRP module: use forecasted stock (virtual_available)
        has_mrp = erp.get("mrp_module", False)

        if has_mrp:
            # Odoo MRP scheduler: considers incoming and outgoing
            effective_stock = state.inventory_position  # on_hand + pipeline - backlog
            stock_label = "forecasted stock (MRP)"
        else:
            # Basic Odoo: only on_hand
            effective_stock = state.on_hand
            stock_label = "on-hand"

        min_qty = params.reorder_point   # product_min_qty
        max_qty = params.order_up_to     # product_max_qty (0 = use min_qty)

        if max_qty <= 0:
            # Odoo: if max_qty is 0, order exactly the deficit
            max_qty = min_qty

        if effective_stock >= min_qty:
            return HeuristicDecision(
                trm_type="po_creation",
                action=0,
                quantity=0.0,
                reasoning=f"Odoo orderpoint: {stock_label}={effective_stock:.1f} "
                          f">= min_qty={min_qty:.1f}. No order needed.",
                erp_params_used={
                    "product_min_qty": min_qty,
                    "product_max_qty": max_qty,
                    "stock_type": stock_label,
                },
            )

        # Below minimum: order up to max
        raw_qty = max(0.0, max_qty - effective_stock)

        # Odoo qty_multiple: round up to nearest multiple
        if params.order_multiple > 0:
            raw_qty = math.ceil(raw_qty / params.order_multiple) * params.order_multiple

        # Odoo vendor minimum (product.supplierinfo.min_qty)
        vendor_min = erp.get("supplierinfo_min_qty", params.min_order_quantity)
        if vendor_min > 0:
            raw_qty = max(raw_qty, vendor_min)

        # Odoo does NOT have lot sizing rules like SAP DISLS -- the max_qty IS the target
        # Apply platform-level order modifications for compatibility
        final_qty = apply_order_modifications(raw_qty, params)

        # Determine route (Buy / Manufacture / Transfer)
        route = erp.get("route", params.procurement_type)

        return HeuristicDecision(
            trm_type="po_creation",
            action=1,
            quantity=final_qty,
            reasoning=f"Odoo orderpoint triggered: {stock_label}={effective_stock:.1f} "
                      f"< min_qty={min_qty:.1f}. Order {final_qty:.1f} to reach "
                      f"max_qty={max_qty:.1f}. Route={route}.",
            erp_params_used={
                "product_min_qty": min_qty,
                "product_max_qty": max_qty,
                "qty_multiple": params.order_multiple,
                "route": route,
                "supplierinfo_min_qty": vendor_min,
            },
        )

    # ===================================================================
    # 2. ATP ALLOCATION -- Odoo available stock check
    # ===================================================================

    def compute_atp_allocation(
        self, state: ATPState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Odoo available-to-promise via stock.quant reservation.

        Odoo does NOT have native allocated ATP with priorities.
        Instead, Odoo uses:
          - qty_available = on_hand - reserved_quantity
          - FIFO reservation (first come, first served)
          - No priority-based allocation waterfall

        Odoo Enterprise adds "forecasted stock" which considers
        planned receipts and planned deliveries.
        """
        erp = params.erp_params

        # Odoo: simple availability = on_hand - reserved
        qty_available = state.available_inventory - state.allocated_inventory

        if qty_available >= state.order_qty:
            return HeuristicDecision(
                trm_type="atp_executor",
                action=1,  # confirm
                quantity=state.order_qty,
                reasoning=f"Odoo: stock available. qty_available={qty_available:.1f} "
                          f">= order={state.order_qty:.1f}. FIFO reservation.",
                erp_params_used={"reservation": "FIFO"},
            )

        # Odoo: partial delivery depends on picking policy
        picking_policy = erp.get("picking_policy", "direct")
        # "direct": ship what's available (partial)
        # "one": wait until all available (no partial)

        if picking_policy == "one":
            return HeuristicDecision(
                trm_type="atp_executor",
                action=0,  # wait
                quantity=0.0,
                reasoning=f"Odoo: insufficient stock ({qty_available:.1f} < "
                          f"{state.order_qty:.1f}). Picking policy='one' -- "
                          f"waiting for full availability.",
                erp_params_used={"picking_policy": "one"},
            )

        # Direct: partial shipment
        if qty_available > 0:
            return HeuristicDecision(
                trm_type="atp_executor",
                action=2,  # partial
                quantity=qty_available,
                reasoning=f"Odoo: partial delivery. Available={qty_available:.1f} of "
                          f"{state.order_qty:.1f}. Picking policy='direct' -- "
                          f"ship available, backorder remainder.",
                erp_params_used={"picking_policy": "direct"},
            )

        return HeuristicDecision(
            trm_type="atp_executor",
            action=0,  # backorder
            quantity=0.0,
            reasoning=f"Odoo: no stock available. Backorder created for "
                      f"{state.order_qty:.1f}.",
            erp_params_used={"picking_policy": picking_policy},
        )

    # ===================================================================
    # 3. INVENTORY REBALANCING -- Odoo inter-warehouse transfer
    # ===================================================================

    def compute_rebalancing(
        self, state: RebalancingState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Odoo inter-warehouse transfer via stock.picking (internal transfer).

        Odoo handles transfers via stock routes:
          - Internal transfer type creates a stock.picking
          - No native "rebalancing" -- transfers are manual or via orderpoints
            with "Transfer" route type

        Odoo 16+ added inter-warehouse replenishment:
          - Configure orderpoint at destination with "Supply From" = source warehouse
          - Scheduler creates internal transfers automatically

        Heuristic: replicate the orderpoint-driven transfer logic.
        """
        # Odoo: check if destination is below its orderpoint min_qty
        target_deficit = state.target_safety_stock + state.target_backlog - state.target_on_hand
        source_excess = state.source_on_hand - state.source_safety_stock - state.source_backlog

        if target_deficit <= 0:
            return HeuristicDecision(
                trm_type="inventory_rebalancing",
                action=0,
                quantity=0.0,
                reasoning=f"Odoo: target not below min_qty. "
                          f"Target on_hand={state.target_on_hand:.1f}, "
                          f"safety_stock={state.target_safety_stock:.1f}.",
                erp_params_used={},
            )

        if source_excess <= 0:
            return HeuristicDecision(
                trm_type="inventory_rebalancing",
                action=0,
                quantity=0.0,
                reasoning=f"Odoo: source has no excess. "
                          f"Source on_hand={state.source_on_hand:.1f}, "
                          f"safety_stock={state.source_safety_stock:.1f}.",
                erp_params_used={},
            )

        transfer_qty = min(source_excess, target_deficit)

        return HeuristicDecision(
            trm_type="inventory_rebalancing",
            action=1,
            quantity=transfer_qty,
            reasoning=f"Odoo internal transfer: {transfer_qty:.1f} units. "
                      f"Source excess={source_excess:.1f}, target deficit={target_deficit:.1f}. "
                      f"LT={state.transfer_lead_time_days:.0f}d.",
            erp_params_used={"transfer_type": "internal"},
        )

    # ===================================================================
    # 4. ORDER TRACKING -- Odoo purchase order / receipt tracking
    # ===================================================================

    def compute_order_tracking(
        self, state: OrderTrackingState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Odoo order tracking via purchase.order and stock.picking status.

        Odoo order states:
          - Draft -> Confirmed -> Approved -> Done/Cancel
          - stock.picking states: draft, waiting, confirmed, assigned, done

        Odoo does NOT have SAP-style exception messages or D365 action
        messages.  Tracking is primarily via late receipt detection and
        vendor performance (purchase module receipts vs PO date).

        Odoo 16+ added "Purchase Late Review" activity type.
        """
        erp = params.erp_params
        late_threshold_days = erp.get("late_threshold_days", 3.0)

        actions = []
        severity = 0

        # Late delivery
        if state.days_overdue > late_threshold_days:
            actions.append(f"overdue by {state.days_overdue:.0f}d")
            severity = 2
        elif state.days_overdue > 0:
            actions.append(f"slightly late ({state.days_overdue:.0f}d)")
            severity = 1

        # Partial receipt
        if state.quantity_received > 0 and state.quantity_received < state.quantity_ordered:
            pct = state.quantity_received / state.quantity_ordered * 100
            actions.append(f"partial receipt ({pct:.0f}%)")
            severity = max(severity, 1)

        # Vendor reliability (Odoo tracks via purchase receipts)
        if state.supplier_on_time_rate < 0.80:
            actions.append(
                f"vendor OTD low ({state.supplier_on_time_rate:.0%})"
            )
            severity = max(severity, 1)

        if not actions:
            return HeuristicDecision(
                trm_type="order_tracking",
                action=0,
                quantity=0.0,
                reasoning=f"Odoo: order {state.order_id} on track. "
                          f"Status={state.current_status}.",
                erp_params_used={},
            )

        return HeuristicDecision(
            trm_type="order_tracking",
            action=severity,
            quantity=state.quantity_ordered - state.quantity_received,
            reasoning=f"Odoo order alert: {state.order_id} -- {'; '.join(actions)}.",
            erp_params_used={"late_threshold_days": late_threshold_days},
        )

    # ===================================================================
    # 5. MO EXECUTION -- Odoo MRP manufacturing order
    # ===================================================================

    def compute_mo_execution(
        self, state: MOExecutionState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Odoo mrp.production manufacturing order scheduling.

        Odoo MRP scheduling:
          - Simple FIFO ordering (no operation overlap by default)
          - Work center capacity check via mrp.workcenter.capacity
          - No native Glenday Sieve or setup matrix
          - Odoo Enterprise adds MRP Planner with basic lead time scheduling

        Odoo manufacturing route:
          1. MO created from orderpoint or sales order
          2. Components reserved (or waiting)
          3. Work orders created per routing operation
          4. Sequential execution (no overlap)
          5. Done + post-production quality check (if quality module)
        """
        erp = params.erp_params

        required_hours = state.setup_time_hours + state.run_time_hours
        capacity_ok = state.available_capacity_hours >= required_hours

        if not capacity_ok:
            # Odoo: no finite scheduling -- just flag as overloaded
            use_work_centers = erp.get("use_work_centers", False)
            if use_work_centers:
                return HeuristicDecision(
                    trm_type="mo_execution",
                    action=4,  # defer
                    quantity=state.quantity,
                    reasoning=f"Odoo MRP: MO {state.mo_id} deferred. Work center overloaded "
                              f"(needed={required_hours:.1f}h, available={state.available_capacity_hours:.1f}h).",
                    erp_params_used={"use_work_centers": True},
                )
            # Without work centers: release anyway (Odoo default)
            return HeuristicDecision(
                trm_type="mo_execution",
                action=1,  # release (infinite capacity)
                quantity=state.quantity,
                reasoning=f"Odoo MRP: release MO {state.mo_id}. "
                          f"No work center capacity constraint configured.",
                erp_params_used={"use_work_centers": False},
            )

        # FIFO: release in order received (no sequencing optimization)
        return HeuristicDecision(
            trm_type="mo_execution",
            action=1,  # release
            quantity=state.quantity,
            reasoning=f"Odoo MRP: release MO {state.mo_id}. FIFO scheduling. "
                      f"Setup={state.setup_time_hours:.1f}h, run={state.run_time_hours:.1f}h, "
                      f"capacity available={state.available_capacity_hours:.1f}h.",
            erp_params_used={"scheduling": "FIFO"},
        )

    # ===================================================================
    # 6. TO EXECUTION -- Odoo stock.picking transfer
    # ===================================================================

    def compute_to_execution(
        self, state: TOExecutionState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Odoo stock.picking for inter-warehouse transfers.

        Odoo transfer picking:
          - No native load consolidation (each order = one picking)
          - Batch transfer (Odoo Enterprise): group multiple pickings
          - Carrier integration: delivery.carrier module

        Odoo Enterprise adds:
          - Batch picking (group multiple pickings for same carrier/route)
          - Wave picking (for warehouse operations)
        """
        erp = params.erp_params
        batch_enabled = erp.get("batch_picking", False)

        if batch_enabled and state.current_load_pct < 0.50 and state.priority > 2:
            return HeuristicDecision(
                trm_type="to_execution",
                action=2,  # hold for batch
                quantity=state.quantity,
                reasoning=f"Odoo: hold TO {state.to_id} for batch picking. "
                          f"Load={state.current_load_pct:.0%}, priority={state.priority}.",
                erp_params_used={"batch_picking": True},
            )

        # Odoo: immediate transfer (stock.picking created and validated)
        return HeuristicDecision(
            trm_type="to_execution",
            action=1,  # release
            quantity=state.quantity,
            reasoning=f"Odoo: release transfer {state.to_id}. "
                      f"Mode={state.transport_mode}.",
            erp_params_used={"transport_mode": state.transport_mode},
        )

    # ===================================================================
    # 7. QUALITY DISPOSITION -- Odoo Quality module
    # ===================================================================

    def compute_quality_disposition(
        self, state: QualityState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Odoo quality.check disposition (Enterprise module).

        Odoo Quality module:
          - Quality checks triggered at picking (receipt, delivery, internal)
          - Check types: pass_fail, measure, take_picture, instructions
          - Alert types: quality.alert
          - No native defect severity classification (simpler than SAP QM)

        Without Enterprise quality module, Odoo has no quality disposition.
        Products are accepted or returned at receipt.
        """
        erp = params.erp_params
        has_quality_module = erp.get("quality_module", False)

        if not has_quality_module:
            # Without quality module: binary accept/reject at receipt
            if state.defect_severity == "critical":
                return HeuristicDecision(
                    trm_type="quality_disposition",
                    action=4,  # return to vendor
                    quantity=state.quantity,
                    reasoning=f"Odoo (no quality module): return lot {state.lot_id} to vendor. "
                              f"Critical defect detected at receipt.",
                    erp_params_used={"quality_module": False},
                )
            return HeuristicDecision(
                trm_type="quality_disposition",
                action=1,  # accept
                quantity=state.quantity,
                reasoning=f"Odoo (no quality module): accept lot {state.lot_id}. "
                          f"Basic receipt check passed.",
                erp_params_used={"quality_module": False},
            )

        # With quality module: pass/fail check
        if state.defect_severity == "critical":
            if state.customer_impact:
                return HeuristicDecision(
                    trm_type="quality_disposition",
                    action=3,  # scrap
                    quantity=state.quantity,
                    reasoning=f"Odoo QC: fail -- scrap lot {state.lot_id}. "
                              f"Critical defect with customer impact.",
                    erp_params_used={"quality_module": True, "check_result": "fail"},
                )
            return HeuristicDecision(
                trm_type="quality_disposition",
                action=4,  # return to vendor
                quantity=state.quantity,
                reasoning=f"Odoo QC: fail -- return lot {state.lot_id} to vendor. "
                          f"Critical {state.defect_type} defect.",
                erp_params_used={"quality_module": True, "check_result": "fail"},
            )

        if state.defect_severity == "major":
            # Odoo: no native rework -- either accept with alert or return
            rework_available = erp.get("rework_route", False)
            if rework_available and state.rework_cost_per_unit < state.unit_cost * 0.60:
                return HeuristicDecision(
                    trm_type="quality_disposition",
                    action=2,  # rework
                    quantity=state.quantity,
                    reasoning=f"Odoo QC: rework lot {state.lot_id}. "
                              f"Major defect, rework route available.",
                    erp_params_used={"quality_module": True, "rework_route": True},
                )
            return HeuristicDecision(
                trm_type="quality_disposition",
                action=4,  # return
                quantity=state.quantity,
                reasoning=f"Odoo QC: return lot {state.lot_id} to vendor. "
                          f"Major defect, no rework route.",
                erp_params_used={"quality_module": True},
            )

        # Minor: accept with quality alert
        return HeuristicDecision(
            trm_type="quality_disposition",
            action=1,  # accept
            quantity=state.quantity,
            reasoning=f"Odoo QC: pass (with alert) -- accept lot {state.lot_id}. "
                      f"Minor {state.defect_type} defect.",
            erp_params_used={"quality_module": True, "check_result": "pass_with_alert"},
        )

    # ===================================================================
    # 8. MAINTENANCE SCHEDULING -- Odoo Maintenance module
    # ===================================================================

    def compute_maintenance_scheduling(
        self, state: MaintenanceState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Odoo maintenance.request scheduling (Enterprise module).

        Odoo Maintenance module:
          - Equipment records (maintenance.equipment)
          - Preventive maintenance with fixed period or MTBF
          - maintenance.request = work order equivalent
          - Simple calendar-based scheduling (no capacity integration)
          - No native condition-based or IoT-triggered maintenance

        Odoo tracks:
          - period (fixed interval in days)
          - mtbf (calculated from maintenance history)
          - estimated_next_failure (period or MTBF based)
        """
        erp = params.erp_params
        has_maintenance = erp.get("maintenance_module", True)

        if not has_maintenance:
            return HeuristicDecision(
                trm_type="maintenance_scheduling",
                action=0,
                quantity=0.0,
                reasoning=f"Odoo: no maintenance module installed for asset {state.asset_id}.",
                erp_params_used={"maintenance_module": False},
            )

        # Odoo: uses either fixed period or MTBF
        maintenance_period_days = erp.get("maintenance_period_days", 0)

        if maintenance_period_days > 0:
            # Fixed interval
            hours_threshold = maintenance_period_days * 24
        else:
            # MTBF-based (Odoo calculates from history)
            hours_threshold = state.mtbf_days * 24 * 0.85  # 85% of MTBF

        pm_due = state.hours_since_last_pm >= hours_threshold

        if not pm_due:
            return HeuristicDecision(
                trm_type="maintenance_scheduling",
                action=0,
                quantity=0.0,
                reasoning=f"Odoo maintenance: asset {state.asset_id} not due. "
                          f"Hours since PM={state.hours_since_last_pm:.0f}, "
                          f"threshold={hours_threshold:.0f}.",
                erp_params_used={"maintenance_period_days": maintenance_period_days},
            )

        # Odoo: no production scheduling integration -- always schedule
        # (Odoo Enterprise does not defer PM based on production load)
        return HeuristicDecision(
            trm_type="maintenance_scheduling",
            action=1,  # schedule
            quantity=state.mttr_hours,
            reasoning=f"Odoo maintenance: schedule PM for asset {state.asset_id}. "
                      f"Hours since PM={state.hours_since_last_pm:.0f} >= "
                      f"threshold={hours_threshold:.0f}.",
            erp_params_used={
                "maintenance_period_days": maintenance_period_days,
                "mtbf_days": state.mtbf_days,
            },
        )

    # ===================================================================
    # 9. SUBCONTRACTING -- Odoo subcontracting route
    # ===================================================================

    def compute_subcontracting(
        self, state: SubcontractingState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Odoo subcontracting via mrp.bom with type='subcontract'.

        Odoo 12+ introduced subcontracting:
          - BOM type = 'subcontract' with subcontractor (partner)
          - On purchase receipt from subcontractor, components consumed
          - Resupply rules determine component delivery to subcontractor

        Odoo routing: determined by product route (Buy / Manufacture / Subcontract)
        If product has subcontracting BOM, purchases from that vendor
        trigger the subcontracting flow automatically.
        """
        erp = params.erp_params
        route = erp.get("route", params.procurement_type)
        has_subcontract_bom = erp.get("subcontract_bom", False)

        if route == "manufacture" and not has_subcontract_bom:
            # Pure manufacturing route
            if state.internal_capacity_available >= state.quantity_needed:
                return HeuristicDecision(
                    trm_type="subcontracting",
                    action=1,  # internal
                    quantity=state.quantity_needed,
                    reasoning=f"Odoo: manufacture route, capacity available. "
                              f"Produce {state.product_id} internally.",
                    erp_params_used={"route": "manufacture"},
                )
            # No capacity: Odoo would create a late MO, not auto-subcontract
            return HeuristicDecision(
                trm_type="subcontracting",
                action=1,  # still internal (Odoo doesn't auto-switch)
                quantity=state.quantity_needed,
                reasoning=f"Odoo: manufacture route, capacity short. MO will be late. "
                          f"Needed={state.quantity_needed:.1f}, "
                          f"available={state.internal_capacity_available:.1f}.",
                erp_params_used={"route": "manufacture", "late": True},
            )

        if route == "buy" or has_subcontract_bom:
            return HeuristicDecision(
                trm_type="subcontracting",
                action=2,  # external (subcontract)
                quantity=state.quantity_needed,
                reasoning=f"Odoo: {'subcontract BOM' if has_subcontract_bom else 'buy route'}. "
                          f"Route {state.product_id} to external vendor.",
                erp_params_used={
                    "route": route,
                    "subcontract_bom": has_subcontract_bom,
                },
            )

        # Default: internal
        return HeuristicDecision(
            trm_type="subcontracting",
            action=1,
            quantity=state.quantity_needed,
            reasoning=f"Odoo: default internal routing for {state.product_id}.",
            erp_params_used={"route": route},
        )

    # ===================================================================
    # 10. FORECAST ADJUSTMENT -- Odoo demand forecast
    # ===================================================================

    def compute_forecast_adjustment(
        self, state: ForecastAdjustmentState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Odoo demand forecast adjustment (Enterprise forecast module).

        Odoo Enterprise Demand Forecasting:
          - stock.forecasting module with ML-based predictions
          - Uses exponential smoothing / linear regression
          - Manual adjustments via forecast lines in UI
          - No native demand sensing or signal-based adjustment

        Without Enterprise: no native forecasting at all.
        """
        erp = params.erp_params
        has_forecast = erp.get("forecast_module", False)

        if not has_forecast:
            return HeuristicDecision(
                trm_type="forecast_adjustment",
                action=0,
                quantity=state.current_forecast,
                reasoning="Odoo: no forecast module installed. No adjustment capability.",
                erp_params_used={"forecast_module": False},
            )

        if state.signal_confidence < 0.35:
            return HeuristicDecision(
                trm_type="forecast_adjustment",
                action=0,
                quantity=state.current_forecast,
                reasoning=f"Odoo: signal confidence ({state.signal_confidence:.2f}) too low.",
                erp_params_used={"min_confidence": 0.35},
            )

        # Odoo: simple proportional adjustment (no dampening factor)
        direction_mult = 1.0 if state.signal_direction == "increase" else -1.0
        if state.signal_direction == "unchanged":
            direction_mult = 0.0

        # Odoo: apply full signal magnitude (less sophisticated than SAP/D365)
        adjustment = state.current_forecast * direction_mult * (state.signal_magnitude_pct / 100.0)
        new_forecast = max(0.0, state.current_forecast + adjustment)

        # Odoo: cap extreme adjustments at 50% change
        max_change_pct = erp.get("max_forecast_change_pct", 50.0)
        change_pct = abs(adjustment) / max(state.current_forecast, 1.0) * 100
        if change_pct > max_change_pct:
            capped_adj = state.current_forecast * direction_mult * (max_change_pct / 100.0)
            new_forecast = max(0.0, state.current_forecast + capped_adj)

        action = 1 if direction_mult > 0 else (2 if direction_mult < 0 else 0)

        return HeuristicDecision(
            trm_type="forecast_adjustment",
            action=action,
            quantity=new_forecast,
            reasoning=f"Odoo forecast: {state.signal_direction} by "
                      f"{min(state.signal_magnitude_pct, max_change_pct):.1f}%. "
                      f"Forecast: {state.current_forecast:.1f} -> {new_forecast:.1f}.",
            erp_params_used={
                "max_forecast_change_pct": max_change_pct,
                "forecast_module": True,
            },
        )

    # ===================================================================
    # 11. INVENTORY BUFFER -- Odoo orderpoint safety stock
    # ===================================================================

    def compute_inventory_buffer(
        self, state: InventoryBufferState, params: ERPPlanningParams,
    ) -> HeuristicDecision:
        """Odoo safety stock via orderpoint product_min_qty.

        Odoo safety stock model:
          - product_min_qty on stock.warehouse.orderpoint IS the safety stock
          - No service-level-based calculation (manual setting)
          - Odoo Enterprise 16+ adds "Demand Forecast" for suggested min_qty
          - No automatic recalculation based on demand variability

        Heuristic: suggest adjustment based on recent stockout/excess history.
        Since Odoo doesn't auto-recalculate, we provide a recommendation
        based on simple rules.
        """
        erp = params.erp_params

        # Odoo: product_min_qty is typically set manually
        # We recommend adjustments based on observed performance
        if state.recent_stockout_count > 3:
            # Frequent stockouts: increase by 20%
            new_ss = state.current_safety_stock * 1.20
            return HeuristicDecision(
                trm_type="inventory_buffer",
                action=1,  # increase
                quantity=new_ss,
                reasoning=f"Odoo orderpoint: increase min_qty. "
                          f"Recent stockouts={state.recent_stockout_count}. "
                          f"Recommend {state.current_safety_stock:.1f} -> {new_ss:.1f} (+20%).",
                erp_params_used={
                    "recent_stockouts": state.recent_stockout_count,
                    "adjustment": "+20%",
                },
            )

        if state.recent_excess_days > 30:
            # Chronic excess: decrease by 15%
            new_ss = state.current_safety_stock * 0.85
            return HeuristicDecision(
                trm_type="inventory_buffer",
                action=2,  # decrease
                quantity=new_ss,
                reasoning=f"Odoo orderpoint: decrease min_qty. "
                          f"Excess inventory for {state.recent_excess_days} days. "
                          f"Recommend {state.current_safety_stock:.1f} -> {new_ss:.1f} (-15%).",
                erp_params_used={
                    "recent_excess_days": state.recent_excess_days,
                    "adjustment": "-15%",
                },
            )

        return HeuristicDecision(
            trm_type="inventory_buffer",
            action=0,
            quantity=state.current_safety_stock,
            reasoning=f"Odoo orderpoint: min_qty={state.current_safety_stock:.1f} is adequate. "
                      f"No recent stockouts or chronic excess.",
            erp_params_used={"current_min_qty": state.current_safety_stock},
        )
