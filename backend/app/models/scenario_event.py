"""
Scenario Event — Structured supply chain event injection for what-if analysis.

Events are data modifications applied to a scenario branch (Kinaxis pattern).
Each event type maps to specific DB table modifications and triggers CDC/TRM
cascade responses. Events are recorded for auditability and undo support.

13 event types across 5 categories:
  Demand:    drop_in_order, demand_spike, order_cancellation, forecast_revision
  Supply:    supplier_delay, supplier_loss, quality_hold, component_shortage
  Capacity:  capacity_loss, machine_breakdown
  Logistics: shipment_delay, lane_disruption
  Macro:     tariff_change
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
