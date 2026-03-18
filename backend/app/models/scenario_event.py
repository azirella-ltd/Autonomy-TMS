"""
Scenario Event — Structured supply chain event injection for what-if analysis.

Events are data modifications applied to a scenario branch (Kinaxis pattern).
Each event type maps to specific DB table modifications and triggers CDC/TRM
cascade responses. Events are recorded for auditability and undo support.

24 event types across 5 categories (SAP S/4HANA IDES compatible):
  Demand:     drop_in_order, demand_spike, order_cancellation, forecast_revision,
              customer_return, product_phase_out, new_product_introduction
  Supply:     supplier_delay, supplier_loss, quality_hold, component_shortage,
              supplier_price_change, product_recall
  Capacity:   capacity_loss, machine_breakdown, yield_loss, labor_shortage,
              engineering_change
  Logistics:  shipment_delay, lane_disruption, warehouse_capacity_constraint
  Macro:      tariff_change, currency_fluctuation, regulatory_change
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, JSON,
    ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


# ---------------------------------------------------------------------------
# Event type catalog
# ---------------------------------------------------------------------------

EVENT_CATEGORIES = {
    "demand": {
        "label": "Demand",
        "description": "Customer orders, demand changes, forecast adjustments",
        "types": {
            "drop_in_order": {
                "label": "Drop-in Order",
                "description": "Large unexpected customer order",
                "parameters": [
                    {"key": "customer_id", "label": "Customer", "type": "select", "required": True, "source": "customers"},
                    {"key": "product_id", "label": "Product", "type": "select", "required": True, "source": "products"},
                    {"key": "quantity", "label": "Quantity", "type": "number", "required": True},
                    {"key": "requested_date", "label": "Requested Delivery Date", "type": "date", "required": True},
                    {"key": "priority", "label": "Priority", "type": "select", "required": False, "options": ["VIP", "HIGH", "STANDARD"], "default": "HIGH"},
                    {"key": "ship_from_site_id", "label": "Ship From Site", "type": "select", "required": False, "source": "internal_sites"},
                ],
                "affects_tables": ["outbound_order", "outbound_order_line"],
                "triggers": ["atp_executor", "po_creation", "mo_execution", "inventory_rebalancing"],
            },
            "demand_spike": {
                "label": "Demand Spike",
                "description": "Sudden increase in demand for a product at a site",
                "parameters": [
                    {"key": "product_id", "label": "Product", "type": "select", "required": True, "source": "products"},
                    {"key": "site_id", "label": "Site", "type": "select", "required": True, "source": "internal_sites"},
                    {"key": "increase_pct", "label": "Increase %", "type": "number", "required": True},
                    {"key": "duration_weeks", "label": "Duration (weeks)", "type": "number", "required": True},
                ],
                "affects_tables": ["forecast"],
                "triggers": ["forecast_adjustment", "inventory_buffer", "po_creation"],
            },
            "order_cancellation": {
                "label": "Order Cancellation",
                "description": "Customer cancels an existing order",
                "parameters": [
                    {"key": "order_id", "label": "Order", "type": "select", "required": True, "source": "outbound_orders"},
                ],
                "affects_tables": ["outbound_order", "outbound_order_line"],
                "triggers": ["atp_executor", "inventory_rebalancing"],
            },
            "forecast_revision": {
                "label": "Forecast Revision",
                "description": "Adjust forecast up or down for a product-site",
                "parameters": [
                    {"key": "product_id", "label": "Product", "type": "select", "required": True, "source": "products"},
                    {"key": "site_id", "label": "Site", "type": "select", "required": True, "source": "internal_sites"},
                    {"key": "direction", "label": "Direction", "type": "select", "required": True, "options": ["increase", "decrease"]},
                    {"key": "magnitude_pct", "label": "Magnitude %", "type": "number", "required": True},
                    {"key": "duration_weeks", "label": "Duration (weeks)", "type": "number", "required": True},
                ],
                "affects_tables": ["forecast"],
                "triggers": ["forecast_adjustment", "inventory_buffer"],
            },
            "customer_return": {
                "label": "Customer Return",
                "description": "Customer returns shipped goods (defective, unwanted, recall)",
                "parameters": [
                    {"key": "customer_id", "label": "Customer", "type": "select", "required": True, "source": "customers"},
                    {"key": "product_id", "label": "Product", "type": "select", "required": True, "source": "products"},
                    {"key": "quantity", "label": "Return Quantity", "type": "number", "required": True},
                    {"key": "return_to_site_id", "label": "Return-To Site", "type": "select", "required": False, "source": "internal_sites"},
                    {"key": "reason", "label": "Return Reason", "type": "select", "required": True, "options": ["defective", "damaged", "wrong_item", "unwanted", "recall"]},
                    {"key": "disposition", "label": "Disposition", "type": "select", "required": False, "options": ["restock", "quarantine", "scrap"], "default": "quarantine"},
                ],
                "affects_tables": ["inv_level", "outbound_order"],
                "triggers": ["quality_disposition", "inventory_rebalancing", "atp_executor"],
            },
            "product_phase_out": {
                "label": "Product Phase-Out",
                "description": "Product approaching end-of-life — ramp down forecast, manage remaining inventory",
                "parameters": [
                    {"key": "product_id", "label": "Product", "type": "select", "required": True, "source": "products"},
                    {"key": "phase_out_date", "label": "Phase-Out Date", "type": "date", "required": True},
                    {"key": "ramp_down_weeks", "label": "Ramp-Down Period (weeks)", "type": "number", "required": True},
                    {"key": "replacement_product_id", "label": "Replacement Product", "type": "select", "required": False, "source": "products"},
                ],
                "affects_tables": ["forecast", "inv_policy"],
                "triggers": ["forecast_adjustment", "inventory_buffer", "po_creation"],
            },
            "new_product_introduction": {
                "label": "New Product Introduction",
                "description": "Launch a new product — initial forecast, sourcing, inventory targets",
                "parameters": [
                    {"key": "product_description", "label": "Product Description", "type": "text", "required": True},
                    {"key": "site_id", "label": "Manufacturing/Stocking Site", "type": "select", "required": True, "source": "internal_sites"},
                    {"key": "initial_forecast_weekly", "label": "Initial Weekly Forecast", "type": "number", "required": True},
                    {"key": "launch_date", "label": "Launch Date", "type": "date", "required": True},
                    {"key": "similar_product_id", "label": "Similar Product (for forecast basis)", "type": "select", "required": False, "source": "products"},
                ],
                "affects_tables": ["product", "forecast", "inv_policy"],
                "triggers": ["forecast_adjustment", "po_creation", "mo_execution"],
            },
        },
    },
    "supply": {
        "label": "Supply",
        "description": "Supplier disruptions, quality issues, material shortages",
        "types": {
            "supplier_delay": {
                "label": "Supplier Delay",
                "description": "Supplier delays deliveries by N days",
                "parameters": [
                    {"key": "vendor_site_id", "label": "Supplier", "type": "select", "required": True, "source": "vendor_sites"},
                    {"key": "delay_days", "label": "Delay (days)", "type": "number", "required": True},
                ],
                "affects_tables": ["inbound_order"],
                "triggers": ["po_creation", "to_execution", "inventory_buffer"],
            },
            "supplier_loss": {
                "label": "Supplier Loss",
                "description": "Supplier becomes unavailable (bankruptcy, sanctions, etc.)",
                "parameters": [
                    {"key": "vendor_site_id", "label": "Supplier", "type": "select", "required": True, "source": "vendor_sites"},
                ],
                "affects_tables": ["inbound_order", "inbound_order_line"],
                "triggers": ["po_creation", "subcontracting", "inventory_rebalancing"],
            },
            "quality_hold": {
                "label": "Quality Hold",
                "description": "Product lot placed on quality hold",
                "parameters": [
                    {"key": "product_id", "label": "Product", "type": "select", "required": True, "source": "products"},
                    {"key": "site_id", "label": "Site", "type": "select", "required": True, "source": "internal_sites"},
                    {"key": "quantity_held", "label": "Quantity Held", "type": "number", "required": True},
                ],
                "affects_tables": ["inv_level"],
                "triggers": ["quality_disposition", "mo_execution", "po_creation"],
            },
            "component_shortage": {
                "label": "Component Shortage",
                "description": "Unexpected reduction in component inventory",
                "parameters": [
                    {"key": "product_id", "label": "Component", "type": "select", "required": True, "source": "products"},
                    {"key": "site_id", "label": "Site", "type": "select", "required": True, "source": "internal_sites"},
                    {"key": "reduction_qty", "label": "Quantity Lost", "type": "number", "required": True},
                ],
                "affects_tables": ["inv_level"],
                "triggers": ["po_creation", "subcontracting", "inventory_rebalancing"],
            },
            "supplier_price_change": {
                "label": "Supplier Price Change",
                "description": "Vendor increases or decreases prices for materials",
                "parameters": [
                    {"key": "vendor_site_id", "label": "Supplier", "type": "select", "required": True, "source": "vendor_sites"},
                    {"key": "product_id", "label": "Product (or leave empty for all)", "type": "select", "required": False, "source": "products"},
                    {"key": "price_change_pct", "label": "Price Change %", "type": "number", "required": True},
                    {"key": "effective_date", "label": "Effective Date", "type": "date", "required": False},
                ],
                "affects_tables": ["vendor_product"],
                "triggers": ["po_creation", "subcontracting"],
            },
            "product_recall": {
                "label": "Product Recall",
                "description": "Batch-level quality failure requiring recall of shipped goods",
                "parameters": [
                    {"key": "product_id", "label": "Product", "type": "select", "required": True, "source": "products"},
                    {"key": "affected_quantity", "label": "Affected Quantity", "type": "number", "required": True},
                    {"key": "site_id", "label": "Originating Site", "type": "select", "required": True, "source": "internal_sites"},
                    {"key": "recall_scope", "label": "Recall Scope", "type": "select", "required": True, "options": ["voluntary", "mandatory"]},
                    {"key": "replacement_required", "label": "Replacement Required", "type": "select", "required": False, "options": ["yes", "no"], "default": "yes"},
                ],
                "affects_tables": ["inv_level", "outbound_order"],
                "triggers": ["quality_disposition", "mo_execution", "po_creation", "order_tracking"],
            },
        },
    },
    "capacity": {
        "label": "Capacity",
        "description": "Production capacity changes and equipment failures",
        "types": {
            "capacity_loss": {
                "label": "Capacity Loss",
                "description": "Reduction in production capacity at a site",
                "parameters": [
                    {"key": "site_id", "label": "Site", "type": "select", "required": True, "source": "internal_sites"},
                    {"key": "reduction_pct", "label": "Reduction %", "type": "number", "required": True},
                    {"key": "duration_weeks", "label": "Duration (weeks)", "type": "number", "required": True},
                ],
                "affects_tables": ["production_process"],
                "triggers": ["mo_execution", "maintenance_scheduling", "subcontracting"],
            },
            "machine_breakdown": {
                "label": "Machine Breakdown",
                "description": "Equipment failure requiring maintenance",
                "parameters": [
                    {"key": "site_id", "label": "Site", "type": "select", "required": True, "source": "internal_sites"},
                    {"key": "resource_name", "label": "Resource/Line", "type": "text", "required": True},
                    {"key": "downtime_days", "label": "Downtime (days)", "type": "number", "required": True},
                ],
                "affects_tables": ["production_process"],
                "triggers": ["maintenance_scheduling", "mo_execution"],
            },
            "yield_loss": {
                "label": "Yield Loss",
                "description": "Production scrap rate increases — more raw materials needed per unit output",
                "parameters": [
                    {"key": "site_id", "label": "Site", "type": "select", "required": True, "source": "internal_sites"},
                    {"key": "product_id", "label": "Product", "type": "select", "required": True, "source": "products"},
                    {"key": "scrap_increase_pct", "label": "Scrap Rate Increase %", "type": "number", "required": True},
                    {"key": "duration_weeks", "label": "Duration (weeks)", "type": "number", "required": True},
                ],
                "affects_tables": ["product_bom", "production_process"],
                "triggers": ["mo_execution", "po_creation", "quality_disposition"],
            },
            "labor_shortage": {
                "label": "Labor Shortage",
                "description": "Workforce unavailability reducing effective capacity",
                "parameters": [
                    {"key": "site_id", "label": "Site", "type": "select", "required": True, "source": "internal_sites"},
                    {"key": "reduction_pct", "label": "Capacity Reduction %", "type": "number", "required": True},
                    {"key": "duration_weeks", "label": "Duration (weeks)", "type": "number", "required": True},
                    {"key": "affected_shifts", "label": "Affected Shifts", "type": "select", "required": False, "options": ["all", "day", "night", "weekend"], "default": "all"},
                ],
                "affects_tables": ["production_process"],
                "triggers": ["mo_execution", "maintenance_scheduling", "subcontracting"],
            },
            "engineering_change": {
                "label": "Engineering Change",
                "description": "BOM revision — changes component requirements mid-planning",
                "parameters": [
                    {"key": "product_id", "label": "Finished Good", "type": "select", "required": True, "source": "products"},
                    {"key": "change_type", "label": "Change Type", "type": "select", "required": True, "options": ["add_component", "remove_component", "change_quantity", "substitute"]},
                    {"key": "component_id", "label": "Component (affected)", "type": "select", "required": True, "source": "products"},
                    {"key": "new_component_id", "label": "New/Substitute Component", "type": "select", "required": False, "source": "products"},
                    {"key": "new_quantity", "label": "New Quantity per Unit", "type": "number", "required": False},
                    {"key": "effective_date", "label": "Effective Date", "type": "date", "required": False},
                ],
                "affects_tables": ["product_bom"],
                "triggers": ["mo_execution", "po_creation"],
            },
        },
    },
    "logistics": {
        "label": "Logistics",
        "description": "Shipping delays and transportation disruptions",
        "types": {
            "shipment_delay": {
                "label": "Shipment Delay",
                "description": "In-transit shipment delayed",
                "parameters": [
                    {"key": "lane_id", "label": "Transportation Lane", "type": "select", "required": True, "source": "lanes"},
                    {"key": "delay_days", "label": "Delay (days)", "type": "number", "required": True},
                ],
                "affects_tables": ["transportation_lane"],
                "triggers": ["order_tracking", "to_execution"],
            },
            "lane_disruption": {
                "label": "Lane Disruption",
                "description": "Transportation lane becomes unavailable",
                "parameters": [
                    {"key": "lane_id", "label": "Transportation Lane", "type": "select", "required": True, "source": "lanes"},
                    {"key": "duration_weeks", "label": "Duration (weeks)", "type": "number", "required": True},
                ],
                "affects_tables": ["transportation_lane"],
                "triggers": ["to_execution", "inventory_rebalancing"],
            },
            "warehouse_capacity_constraint": {
                "label": "Warehouse Capacity Constraint",
                "description": "Storage location approaching or exceeding capacity — requires overflow management",
                "parameters": [
                    {"key": "site_id", "label": "Warehouse/DC", "type": "select", "required": True, "source": "internal_sites"},
                    {"key": "utilization_pct", "label": "Current Utilization %", "type": "number", "required": True},
                    {"key": "duration_weeks", "label": "Expected Duration (weeks)", "type": "number", "required": True},
                ],
                "affects_tables": ["inv_level"],
                "triggers": ["inventory_rebalancing", "to_execution"],
            },
        },
    },
    "macro": {
        "label": "Macro",
        "description": "External economic and regulatory changes",
        "types": {
            "tariff_change": {
                "label": "Tariff Change",
                "description": "Cost increase from tariffs or duties",
                "parameters": [
                    {"key": "vendor_site_id", "label": "Supplier/Region", "type": "select", "required": True, "source": "vendor_sites"},
                    {"key": "cost_increase_pct", "label": "Cost Increase %", "type": "number", "required": True},
                ],
                "affects_tables": ["vendor_product"],
                "triggers": ["po_creation", "subcontracting"],
            },
            "currency_fluctuation": {
                "label": "Currency Fluctuation",
                "description": "Exchange rate shift affecting multi-currency sourcing and landed costs",
                "parameters": [
                    {"key": "currency_pair", "label": "Currency Pair (e.g. EUR/USD)", "type": "text", "required": True},
                    {"key": "change_pct", "label": "Rate Change %", "type": "number", "required": True},
                    {"key": "direction", "label": "Direction", "type": "select", "required": True, "options": ["strengthen", "weaken"]},
                ],
                "affects_tables": ["vendor_product"],
                "triggers": ["po_creation", "subcontracting"],
            },
            "regulatory_change": {
                "label": "Regulatory Change",
                "description": "New compliance requirement affecting sourcing, materials, or processes",
                "parameters": [
                    {"key": "regulation_description", "label": "Regulation Description", "type": "text", "required": True},
                    {"key": "affected_products", "label": "Affected Products", "type": "text", "required": False},
                    {"key": "affected_sites", "label": "Affected Sites", "type": "text", "required": False},
                    {"key": "compliance_deadline", "label": "Compliance Deadline", "type": "date", "required": True},
                    {"key": "impact_type", "label": "Impact Type", "type": "select", "required": True, "options": ["sourcing_restriction", "material_ban", "testing_requirement", "labeling_change", "process_change"]},
                ],
                "affects_tables": ["sourcing_rules", "production_process"],
                "triggers": ["po_creation", "mo_execution", "quality_disposition"],
            },
        },
    },
}

# Flat lookup: event_type_key → definition
EVENT_TYPE_REGISTRY = {}
for _cat_key, _cat in EVENT_CATEGORIES.items():
    for _type_key, _type_def in _cat["types"].items():
        EVENT_TYPE_REGISTRY[_type_key] = {**_type_def, "category": _cat_key}


class ScenarioEvent(Base):
    """A recorded supply chain event injected into a scenario branch."""
    __tablename__ = "scenario_events"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Scenario context
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Event definition
    event_type = Column(String(50), nullable=False)  # Key from EVENT_TYPE_REGISTRY
    category = Column(String(30), nullable=False)  # demand, supply, capacity, logistics, macro
    label = Column(String(100), nullable=False)  # Human-readable label
    parameters = Column(JSON, nullable=False)  # User-provided parameter values

    # What was modified
    affected_entities = Column(JSON, nullable=True)  # IDs of created/modified records
    summary = Column(Text, nullable=True)  # Human-readable summary of what happened

    # CDC response
    cdc_triggered = Column(JSON, nullable=True)  # CDC trigger reasons fired
    decisions_generated = Column(Integer, default=0)  # Count of decisions created

    # Lifecycle
    status = Column(String(20), nullable=False, default="APPLIED")
    # APPLIED → REVERTED
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    reverted_at = Column(DateTime, nullable=True)

    # Relationships
    config = relationship("SupplyChainConfig")
    user = relationship("User")

    __table_args__ = (
        Index("idx_scenario_event_config", "config_id"),
        Index("idx_scenario_event_tenant", "tenant_id", "created_at"),
        Index("idx_scenario_event_type", "event_type"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "config_id": self.config_id,
            "tenant_id": self.tenant_id,
            "created_by": self.created_by,
            "event_type": self.event_type,
            "category": self.category,
            "label": self.label,
            "parameters": self.parameters,
            "affected_entities": self.affected_entities,
            "summary": self.summary,
            "cdc_triggered": self.cdc_triggered,
            "decisions_generated": self.decisions_generated,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "reverted_at": self.reverted_at.isoformat() if self.reverted_at else None,
        }
