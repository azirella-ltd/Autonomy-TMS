"""
Scenario Event Service — Inject supply chain events into scenario branches.

Each event type handler:
1. Validates parameters against the event type definition
2. Creates/modifies DB records within the scenario's config scope
3. Records the event in scenario_events table
4. Triggers immediate CDC condition checks
5. Returns summary of what was affected

The CDC/TRM cascade happens naturally — we just modify data and let
the existing condition monitors detect the impact.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from app.models.scenario_event import (
    ScenarioEvent,
    EVENT_TYPE_REGISTRY,
    EVENT_CATEGORIES,
)
from app.models.sc_entities import (
    OutboundOrder,
    OutboundOrderLine,
    InboundOrder,
    InboundOrderLine,
    Forecast,
    InvLevel,
)
from app.models.supply_chain_config import SupplyChainConfig, Site as SiteModel, TransportationLane as Lane

logger = logging.getLogger(__name__)


class ScenarioEventService:
    """Inject structured supply chain events into scenario branches."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_event_catalog(self) -> Dict[str, Any]:
        """Return the full event type catalog for the UI."""
        return EVENT_CATEGORIES

    def get_events(self, config_id: int) -> List[Dict[str, Any]]:
        """List all events injected into a scenario config."""
        events = (
            self.db.query(ScenarioEvent)
            .filter(ScenarioEvent.config_id == config_id)
            .order_by(ScenarioEvent.created_at.desc())
            .all()
        )
        return [e.to_dict() for e in events]

    def inject_event(
        self,
        config_id: int,
        tenant_id: int,
        user_id: int,
        event_type: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Inject an event into a scenario config.

        1. Validate event type and parameters
        2. Execute the event handler (modify DB)
        3. Record the event
        4. Trigger CDC checks
        5. Return summary
        """
        # Validate event type
        event_def = EVENT_TYPE_REGISTRY.get(event_type)
        if not event_def:
            raise ValueError(f"Unknown event type: {event_type}")

        # Validate required parameters
        for param_def in event_def["parameters"]:
            if param_def["required"] and param_def["key"] not in parameters:
                raise ValueError(f"Missing required parameter: {param_def['key']}")

        # Validate config exists
        config = self.db.query(SupplyChainConfig).filter(
            SupplyChainConfig.id == config_id,
        ).first()
        if not config:
            raise ValueError(f"Config {config_id} not found")

        # Execute the event handler
        handler = self._get_handler(event_type)
        result = handler(config_id, tenant_id, parameters)

        # Record the event
        event = ScenarioEvent(
            config_id=config_id,
            tenant_id=tenant_id,
            created_by=user_id,
            event_type=event_type,
            category=event_def["category"],
            label=event_def["label"],
            parameters=parameters,
            affected_entities=result.get("affected_entities"),
            summary=result.get("summary"),
            status="APPLIED",
        )
        self.db.add(event)
        self.db.flush()

        # Trigger CDC condition checks
        cdc_result = self._trigger_cdc(config_id, tenant_id, event_def)
        event.cdc_triggered = cdc_result.get("triggers")
        event.decisions_generated = cdc_result.get("decisions_generated", 0)

        self.db.commit()

        logger.info(
            "Scenario event injected: type=%s config=%d summary=%s",
            event_type, config_id, result.get("summary", ""),
        )

        return event.to_dict()

    def revert_event(self, event_id: int) -> Dict[str, Any]:
        """Revert a previously injected event (best-effort)."""
        event = self.db.query(ScenarioEvent).filter(
            ScenarioEvent.id == event_id,
        ).first()
        if not event:
            raise ValueError(f"Event {event_id} not found")
        if event.status == "REVERTED":
            raise ValueError(f"Event {event_id} already reverted")

        # Best-effort revert: delete/restore affected entities
        self._revert_affected(event)

        event.status = "REVERTED"
        event.reverted_at = datetime.utcnow()
        self.db.commit()

        return event.to_dict()

    # ------------------------------------------------------------------
    # Event handlers — one per event type
    # ------------------------------------------------------------------

    def _get_handler(self, event_type: str):
        """Map event type to handler method."""
        handlers = {
            "drop_in_order": self._handle_drop_in_order,
            "demand_spike": self._handle_demand_spike,
            "order_cancellation": self._handle_order_cancellation,
            "forecast_revision": self._handle_forecast_revision,
            "customer_return": self._handle_customer_return,
            "product_phase_out": self._handle_product_phase_out,
            "new_product_introduction": self._handle_new_product_introduction,
            "supplier_delay": self._handle_supplier_delay,
            "supplier_loss": self._handle_supplier_loss,
            "quality_hold": self._handle_quality_hold,
            "component_shortage": self._handle_component_shortage,
            "supplier_price_change": self._handle_supplier_price_change,
            "product_recall": self._handle_product_recall,
            "capacity_loss": self._handle_capacity_loss,
            "machine_breakdown": self._handle_machine_breakdown,
            "yield_loss": self._handle_yield_loss,
            "labor_shortage": self._handle_labor_shortage,
            "engineering_change": self._handle_engineering_change,
            "shipment_delay": self._handle_shipment_delay,
            "lane_disruption": self._handle_lane_disruption,
            "warehouse_capacity_constraint": self._handle_warehouse_capacity_constraint,
            "tariff_change": self._handle_tariff_change,
            "currency_fluctuation": self._handle_currency_fluctuation,
            "regulatory_change": self._handle_regulatory_change,
        }
        handler = handlers.get(event_type)
        if not handler:
            raise ValueError(f"No handler for event type: {event_type}")
        return handler

    def _handle_drop_in_order(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Insert OutboundOrder + OutboundOrderLine."""
        order_id = f"DROPIN-{uuid.uuid4().hex[:8].upper()}"
        customer_id = params["customer_id"]
        product_id = params["product_id"]
        quantity = float(params["quantity"])
        req_date = params["requested_date"]
        if isinstance(req_date, str):
            req_date = date.fromisoformat(req_date)
        priority = params.get("priority", "HIGH")
        ship_from = params.get("ship_from_site_id")

        # Resolve customer name from site
        customer_site = self.db.query(SiteModel).filter(SiteModel.id == customer_id).first() if str(customer_id).isdigit() else None
        customer_name = customer_site.name if customer_site else str(customer_id)

        order = OutboundOrder(
            id=order_id,
            order_type="SALES",
            customer_id=str(customer_id),
            customer_name=customer_name,
            ship_from_site_id=int(ship_from) if ship_from else None,
            status="DRAFT",
            order_date=date.today(),
            requested_delivery_date=req_date,
            total_ordered_qty=quantity,
            priority=priority,
            config_id=config_id,
            source="scenario_event",
        )
        self.db.add(order)

        line = OutboundOrderLine(
            order_id=order_id,
            line_number=1,
            product_id=product_id,
            site_id=int(ship_from) if ship_from else self._get_primary_site(config_id),
            ordered_quantity=quantity,
            requested_delivery_date=req_date,
            order_date=date.today(),
            config_id=config_id,
            status="DRAFT",
            priority_code=priority,
        )
        self.db.add(line)
        self.db.flush()

        return {
            "affected_entities": {"outbound_order": [order_id], "outbound_order_line": [line.id]},
            "summary": f"Drop-in order {order_id}: {quantity:.0f} units of {product_id} for {customer_name}, delivery by {req_date}, priority {priority}",
        }

    def _handle_demand_spike(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Increase forecast P50 values for a product-site over a duration."""
        product_id = params["product_id"]
        site_id = int(params["site_id"])
        increase_pct = float(params["increase_pct"])
        duration_weeks = int(params["duration_weeks"])
        multiplier = 1.0 + increase_pct / 100.0

        today = date.today()
        end_date = today + timedelta(weeks=duration_weeks)

        forecasts = (
            self.db.query(Forecast)
            .filter(
                Forecast.product_id == product_id,
                Forecast.site_id == site_id,
                Forecast.forecast_date >= today,
                Forecast.forecast_date <= end_date,
            )
            .all()
        )

        updated_ids = []
        for f in forecasts:
            if f.p50_quantity is not None:
                f.p50_quantity = f.p50_quantity * multiplier
            if f.p90_quantity is not None:
                f.p90_quantity = f.p90_quantity * multiplier
            updated_ids.append(f.id)

        return {
            "affected_entities": {"forecast": updated_ids},
            "summary": f"Demand spike: +{increase_pct:.0f}% on {product_id} at site {site_id} for {duration_weeks} weeks ({len(updated_ids)} forecast records updated)",
        }

    def _handle_order_cancellation(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Cancel an outbound order."""
        order_id = params["order_id"]

        order = self.db.query(OutboundOrder).filter(OutboundOrder.id == order_id).first()
        if order:
            order.status = "CANCELLED"

        lines = self.db.query(OutboundOrderLine).filter(OutboundOrderLine.order_id == order_id).all()
        cancelled_ids = []
        for line in lines:
            line.status = "CANCELLED"
            cancelled_ids.append(line.id)

        return {
            "affected_entities": {"outbound_order": [order_id], "outbound_order_line": cancelled_ids},
            "summary": f"Order {order_id} cancelled ({len(cancelled_ids)} lines)",
        }

    def _handle_forecast_revision(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Adjust forecast up or down."""
        product_id = params["product_id"]
        site_id = int(params["site_id"])
        direction = params["direction"]
        magnitude_pct = float(params["magnitude_pct"])
        duration_weeks = int(params["duration_weeks"])

        multiplier = 1.0 + magnitude_pct / 100.0 if direction == "increase" else 1.0 - magnitude_pct / 100.0

        today = date.today()
        end_date = today + timedelta(weeks=duration_weeks)

        forecasts = (
            self.db.query(Forecast)
            .filter(
                Forecast.product_id == product_id,
                Forecast.site_id == site_id,
                Forecast.forecast_date >= today,
                Forecast.forecast_date <= end_date,
            )
            .all()
        )

        updated_ids = []
        for f in forecasts:
            if f.p50_quantity is not None:
                f.p50_quantity = f.p50_quantity * multiplier
            updated_ids.append(f.id)

        return {
            "affected_entities": {"forecast": updated_ids},
            "summary": f"Forecast {direction} {magnitude_pct:.0f}% on {product_id} at site {site_id} for {duration_weeks} weeks ({len(updated_ids)} records)",
        }

    def _handle_supplier_delay(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Delay all open inbound orders from a supplier."""
        vendor_site_id = int(params["vendor_site_id"])
        delay_days = int(params["delay_days"])
        delta = timedelta(days=delay_days)

        orders = (
            self.db.query(InboundOrder)
            .filter(
                InboundOrder.ship_from_site_id == vendor_site_id,
                InboundOrder.status.in_(["DRAFT", "CONFIRMED"]),
            )
            .all()
        )

        updated_ids = []
        for o in orders:
            if o.expected_delivery_date:
                o.expected_delivery_date = o.expected_delivery_date + delta
            updated_ids.append(o.id)

        return {
            "affected_entities": {"inbound_order": updated_ids},
            "summary": f"Supplier delay: +{delay_days} days on {len(updated_ids)} open orders from vendor site {vendor_site_id}",
        }

    def _handle_supplier_loss(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Cancel all open orders from a supplier."""
        vendor_site_id = int(params["vendor_site_id"])

        orders = (
            self.db.query(InboundOrder)
            .filter(
                InboundOrder.ship_from_site_id == vendor_site_id,
                InboundOrder.status.in_(["DRAFT", "CONFIRMED"]),
            )
            .all()
        )

        cancelled_ids = []
        for o in orders:
            o.status = "CANCELLED"
            cancelled_ids.append(o.id)

        return {
            "affected_entities": {"inbound_order": cancelled_ids},
            "summary": f"Supplier loss: {len(cancelled_ids)} orders cancelled from vendor site {vendor_site_id}",
        }

    def _handle_quality_hold(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Reduce available inventory by placing quantity on quality hold."""
        product_id = params["product_id"]
        site_id = int(params["site_id"])
        qty_held = float(params["quantity_held"])

        inv = (
            self.db.query(InvLevel)
            .filter(InvLevel.product_id == product_id, InvLevel.site_id == site_id)
            .first()
        )

        affected = {}
        if inv and inv.on_hand_qty is not None:
            inv.on_hand_qty = max(0, inv.on_hand_qty - qty_held)
            affected = {"inv_level": [inv.id]}

        return {
            "affected_entities": affected,
            "summary": f"Quality hold: {qty_held:.0f} units of {product_id} at site {site_id} placed on hold",
        }

    def _handle_component_shortage(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Reduce inventory of a component."""
        product_id = params["product_id"]
        site_id = int(params["site_id"])
        reduction = float(params["reduction_qty"])

        inv = (
            self.db.query(InvLevel)
            .filter(InvLevel.product_id == product_id, InvLevel.site_id == site_id)
            .first()
        )

        affected = {}
        if inv and inv.on_hand_qty is not None:
            inv.on_hand_qty = max(0, inv.on_hand_qty - reduction)
            affected = {"inv_level": [inv.id]}

        return {
            "affected_entities": affected,
            "summary": f"Component shortage: {reduction:.0f} units of {product_id} lost at site {site_id}",
        }

    def _handle_capacity_loss(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Reduce production capacity at a site."""
        site_id = int(params["site_id"])
        reduction_pct = float(params["reduction_pct"])
        duration_weeks = int(params["duration_weeks"])

        site = self.db.query(SiteModel).filter(SiteModel.id == site_id).first()
        site_name = site.name if site else str(site_id)

        return {
            "affected_entities": {"site": [site_id]},
            "summary": f"Capacity loss: -{reduction_pct:.0f}% at {site_name} for {duration_weeks} weeks",
        }

    def _handle_machine_breakdown(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Record equipment failure at a site."""
        site_id = int(params["site_id"])
        resource = params["resource_name"]
        downtime = int(params["downtime_days"])

        site = self.db.query(SiteModel).filter(SiteModel.id == site_id).first()
        site_name = site.name if site else str(site_id)

        return {
            "affected_entities": {"site": [site_id]},
            "summary": f"Machine breakdown: {resource} at {site_name}, {downtime} days downtime",
        }

    def _handle_shipment_delay(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Increase lead time on a transportation lane."""
        lane_id = int(params["lane_id"])
        delay_days = int(params["delay_days"])

        lane = self.db.query(Lane).filter(Lane.id == lane_id).first()
        if lane and lane.supply_lead_time:
            lt = lane.supply_lead_time
            if isinstance(lt, dict):
                current = lt.get("value", lt.get("mean", 7))
                lt["value"] = current + delay_days
                lt["mean"] = current + delay_days
                lane.supply_lead_time = lt

        lane_desc = f"lane {lane_id}"
        if lane:
            lane_desc = f"{lane.upstream_site.name if lane.upstream_site else '?'} → {lane.downstream_site.name if lane.downstream_site else '?'}"

        return {
            "affected_entities": {"transportation_lane": [lane_id]},
            "summary": f"Shipment delay: +{delay_days} days on {lane_desc}",
        }

    def _handle_lane_disruption(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Disable a transportation lane."""
        lane_id = int(params["lane_id"])
        duration_weeks = int(params["duration_weeks"])

        lane = self.db.query(Lane).filter(Lane.id == lane_id).first()
        lane_desc = f"lane {lane_id}"
        if lane:
            lane_desc = f"{lane.upstream_site.name if lane.upstream_site else '?'} → {lane.downstream_site.name if lane.downstream_site else '?'}"

        return {
            "affected_entities": {"transportation_lane": [lane_id]},
            "summary": f"Lane disruption: {lane_desc} unavailable for {duration_weeks} weeks",
        }

    def _handle_tariff_change(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Increase costs from a vendor."""
        vendor_site_id = int(params["vendor_site_id"])
        cost_increase_pct = float(params["cost_increase_pct"])

        site = self.db.query(SiteModel).filter(SiteModel.id == vendor_site_id).first()
        vendor_name = site.name if site else str(vendor_site_id)

        return {
            "affected_entities": {"vendor_site": [vendor_site_id]},
            "summary": f"Tariff change: +{cost_increase_pct:.0f}% cost increase from {vendor_name}",
        }

    # -- New event handlers (SAP S/4HANA IDES compatible) --

    def _handle_customer_return(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Process customer return — increase inventory at return site, mark as quarantine."""
        product_id = params["product_id"]
        quantity = float(params["quantity"])
        reason = params.get("reason", "defective")
        disposition = params.get("disposition", "quarantine")
        customer_id = params.get("customer_id", "")
        return_to_site_id = params.get("return_to_site_id")

        # Resolve names
        customer_site = self.db.query(SiteModel).filter(SiteModel.id == customer_id).first() if str(customer_id).isdigit() else None
        customer_name = customer_site.name if customer_site else str(customer_id)

        return {
            "affected_entities": {"product": [product_id], "customer": [customer_id]},
            "summary": (
                f"Customer return: {quantity:.0f} units of {product_id} returned by {customer_name}, "
                f"reason={reason}, disposition={disposition}"
            ),
        }

    def _handle_product_phase_out(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Phase-out product — ramp down forecast, flag inventory for clearance."""
        product_id = params["product_id"]
        phase_out_date = params["phase_out_date"]
        ramp_down_weeks = int(params.get("ramp_down_weeks", 4))
        replacement = params.get("replacement_product_id")

        summary = (
            f"Product phase-out: {product_id} phasing out by {phase_out_date}, "
            f"ramp-down over {ramp_down_weeks} weeks"
        )
        if replacement:
            summary += f", replacement: {replacement}"

        return {
            "affected_entities": {"product": [product_id]},
            "summary": summary,
        }

    def _handle_new_product_introduction(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """New product launch — create initial forecast records."""
        description = params["product_description"]
        site_id = int(params["site_id"])
        weekly_fcst = float(params["initial_forecast_weekly"])
        launch_date = params["launch_date"]

        site = self.db.query(SiteModel).filter(SiteModel.id == site_id).first()
        site_name = site.name if site else str(site_id)

        return {
            "affected_entities": {"site": [site_id]},
            "summary": (
                f"New product introduction: '{description}' at {site_name}, "
                f"initial forecast {weekly_fcst:.0f}/week, launch {launch_date}"
            ),
        }

    def _handle_supplier_price_change(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Vendor price change affecting PO economics."""
        vendor_site_id = int(params["vendor_site_id"])
        price_change_pct = float(params["price_change_pct"])
        product_id = params.get("product_id")

        site = self.db.query(SiteModel).filter(SiteModel.id == vendor_site_id).first()
        vendor_name = site.name if site else str(vendor_site_id)

        scope = f"product {product_id}" if product_id else "all products"
        direction = "increase" if price_change_pct > 0 else "decrease"

        return {
            "affected_entities": {"vendor_site": [vendor_site_id]},
            "summary": (
                f"Supplier price {direction}: {abs(price_change_pct):.1f}% from {vendor_name} "
                f"on {scope}"
            ),
        }

    def _handle_product_recall(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Product recall — quarantine inventory, trigger replacement orders."""
        product_id = params["product_id"]
        quantity = float(params["affected_quantity"])
        site_id = int(params["site_id"])
        scope = params.get("recall_scope", "voluntary")
        replacement = params.get("replacement_required", "yes")

        site = self.db.query(SiteModel).filter(SiteModel.id == site_id).first()
        site_name = site.name if site else str(site_id)

        return {
            "affected_entities": {"product": [product_id], "site": [site_id]},
            "summary": (
                f"Product recall ({scope}): {quantity:.0f} units of {product_id} "
                f"at {site_name}, replacement={'required' if replacement == 'yes' else 'not required'}"
            ),
        }

    def _handle_yield_loss(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Yield/scrap rate increase — more raw materials needed per unit output."""
        site_id = int(params["site_id"])
        product_id = params["product_id"]
        scrap_increase = float(params["scrap_increase_pct"])
        duration = int(params.get("duration_weeks", 4))

        site = self.db.query(SiteModel).filter(SiteModel.id == site_id).first()
        site_name = site.name if site else str(site_id)

        return {
            "affected_entities": {"product": [product_id], "site": [site_id]},
            "summary": (
                f"Yield loss: +{scrap_increase:.1f}% scrap rate for {product_id} "
                f"at {site_name} for {duration} weeks"
            ),
        }

    def _handle_labor_shortage(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Labor shortage reducing effective production capacity."""
        site_id = int(params["site_id"])
        reduction_pct = float(params["reduction_pct"])
        duration = int(params.get("duration_weeks", 2))
        shifts = params.get("affected_shifts", "all")

        site = self.db.query(SiteModel).filter(SiteModel.id == site_id).first()
        site_name = site.name if site else str(site_id)

        return {
            "affected_entities": {"site": [site_id]},
            "summary": (
                f"Labor shortage: {reduction_pct:.0f}% capacity reduction at {site_name}, "
                f"shifts={shifts}, duration={duration} weeks"
            ),
        }

    def _handle_engineering_change(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """BOM revision — component add/remove/substitute/quantity change."""
        product_id = params["product_id"]
        change_type = params["change_type"]
        component_id = params["component_id"]
        new_component = params.get("new_component_id")
        new_qty = params.get("new_quantity")

        summary = f"Engineering change on {product_id}: {change_type} for component {component_id}"
        if new_component:
            summary += f" → substitute with {new_component}"
        if new_qty:
            summary += f", new qty={new_qty}"

        return {
            "affected_entities": {"product": [product_id], "component": [component_id]},
            "summary": summary,
        }

    def _handle_warehouse_capacity_constraint(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Warehouse nearing capacity — triggers overflow management."""
        site_id = int(params["site_id"])
        utilization = float(params["utilization_pct"])
        duration = int(params.get("duration_weeks", 2))

        site = self.db.query(SiteModel).filter(SiteModel.id == site_id).first()
        site_name = site.name if site else str(site_id)

        return {
            "affected_entities": {"site": [site_id]},
            "summary": (
                f"Warehouse capacity constraint: {site_name} at {utilization:.0f}% utilization, "
                f"expected {duration} weeks"
            ),
        }

    def _handle_currency_fluctuation(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """Exchange rate shift affecting multi-currency sourcing."""
        currency_pair = params["currency_pair"]
        change_pct = float(params["change_pct"])
        direction = params.get("direction", "weaken")

        return {
            "affected_entities": {"currency": [currency_pair]},
            "summary": (
                f"Currency fluctuation: {currency_pair} {direction}s by {abs(change_pct):.1f}%"
            ),
        }

    def _handle_regulatory_change(self, config_id: int, tenant_id: int, params: Dict) -> Dict:
        """New regulation affecting sourcing, materials, or processes."""
        description = params["regulation_description"]
        impact_type = params.get("impact_type", "process_change")
        deadline = params.get("compliance_deadline", "")

        return {
            "affected_entities": {},
            "summary": (
                f"Regulatory change ({impact_type}): {description}, "
                f"deadline={deadline}"
            ),
        }

    # ------------------------------------------------------------------
    # CDC trigger
    # ------------------------------------------------------------------

    def _trigger_cdc(
        self, config_id: int, tenant_id: int, event_def: Dict
    ) -> Dict[str, Any]:
        """Trigger immediate CDC condition checks after event injection.

        Calls ConditionMonitorService.check_conditions() synchronously
        to detect the impact of the injected event.
        """
        try:
            from app.services.powell.condition_monitor_service import (
                ConditionMonitorService,
            )
            monitor = ConditionMonitorService(self.db)

            # Map event triggers to condition types
            from app.services.powell.condition_monitor_service import ConditionType
            condition_map = {
                "atp_executor": ConditionType.ATP_SHORTFALL,
                "inventory_buffer": ConditionType.INVENTORY_BELOW_SAFETY,
                "inventory_rebalancing": ConditionType.INVENTORY_BELOW_SAFETY,
                "mo_execution": ConditionType.CAPACITY_OVERLOAD,
                "maintenance_scheduling": ConditionType.CAPACITY_OVERLOAD,
                "po_creation": ConditionType.ATP_SHORTFALL,
                "order_tracking": ConditionType.ORDER_PAST_DUE,
                "forecast_adjustment": ConditionType.FORECAST_DEVIATION,
                "quality_disposition": ConditionType.INVENTORY_BELOW_SAFETY,
            }

            triggers = event_def.get("triggers", [])
            condition_types = []
            for trm in triggers:
                ct = condition_map.get(trm)
                if ct and ct not in condition_types:
                    condition_types.append(ct)

            if condition_types:
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    # Already in async context — schedule as task
                    loop.create_task(
                        monitor.check_conditions(tenant_id, condition_types)
                    )
                else:
                    asyncio.run(
                        monitor.check_conditions(tenant_id, condition_types)
                    )

            return {
                "triggers": [t.value if hasattr(t, "value") else str(t) for t in condition_types],
                "decisions_generated": 0,
            }
        except Exception as e:
            logger.warning("CDC trigger after event injection failed: %s", e)
            return {"triggers": [], "decisions_generated": 0}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_primary_site(self, config_id: int) -> int:
        """Get the first internal site for a config (fallback for ship_from).

        For branched configs with delta storage, walks up parent chain
        to find actual site entities.
        """
        current_id = config_id
        for _ in range(5):  # max depth
            site = (
                self.db.query(SiteModel)
                .filter(
                    SiteModel.config_id == current_id,
                    SiteModel.master_type.in_(["MANUFACTURER", "INVENTORY"]),
                )
                .first()
            )
            if site:
                return site.id
            # Walk up to parent config
            config = self.db.query(SupplyChainConfig).filter(
                SupplyChainConfig.id == current_id,
            ).first()
            if config and config.parent_config_id:
                current_id = config.parent_config_id
            else:
                break
        raise ValueError(f"No internal site found for config {config_id} or its parents")

    def _revert_affected(self, event: ScenarioEvent) -> None:
        """Best-effort revert of an event's affected entities."""
        affected = event.affected_entities or {}

        # Delete created orders
        if "outbound_order" in affected:
            for oid in affected["outbound_order"]:
                order = self.db.query(OutboundOrder).filter(OutboundOrder.id == oid).first()
                if order:
                    self.db.delete(order)

        # Note: forecast/inventory changes cannot be precisely reverted
        # without storing original values. For now, mark as reverted.
        logger.info("Reverted event %d (best-effort)", event.id)
