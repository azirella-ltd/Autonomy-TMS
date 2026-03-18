"""
Query Router — Maps natural language questions to frontend pages with filters.

Two routing strategies:
  Option A (primary): LLM-based routing via the directive analyze prompt.
    The LLM receives the ROUTE_REGISTRY as context and returns target_page + filters.
  Option B (fallback): Embedding-based cosine similarity when LLM is unavailable.
    Pre-computes TF-IDF vectors for route descriptions; cosine-matches the query.

Both strategies enforce tenant/role scoping: routes are filtered by the user's
capabilities before being presented to the LLM or matched by embeddings.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class RouteEntry:
    """A navigable frontend page with semantic metadata."""
    path: str
    label: str
    description: str
    keywords: List[str]
    capability: Optional[str] = None
    filters: List[str] = field(default_factory=list)
    category: str = "general"


# ---------------------------------------------------------------------------
# Route Registry — all navigable pages with semantic descriptions
# ---------------------------------------------------------------------------

ROUTE_REGISTRY: List[RouteEntry] = [
    # ── Decision Stream ──
    RouteEntry(
        path="/decision-stream",
        label="Decision Stream",
        description="Primary inbox for all AI agent decisions across all TRM types. Shows decisions ranked by urgency and likelihood, with accept/override/inspect actions.",
        keywords=["decisions", "inbox", "worklist", "actions", "agent decisions", "review", "approve", "override"],
        filters=["trm_type", "status", "urgency", "site", "product"],
        category="execution",
    ),

    # ── Scenario Events ──
    RouteEntry(
        path="/scenario-events",
        label="Scenario Events",
        description="What-if event injection workspace. Inject supply chain disruptions (drop-in orders, supplier delays, capacity loss, demand spikes) into scenario branches and observe the CDC cascade response.",
        keywords=["what-if", "scenario", "event", "disruption", "drop-in order", "supplier delay", "capacity loss", "demand spike", "simulate", "test", "injection", "rush order"],
        filters=["event_type", "category"],
        category="execution",
    ),

    # ── Executive & Strategic ──
    RouteEntry(
        path="/executive-dashboard",
        label="Executive Dashboard",
        description="High-level KPIs, balanced scorecard, service level, cost, and inventory performance metrics for leadership.",
        keywords=["executive", "KPIs", "scorecard", "performance", "summary", "overview", "leadership"],
        capability="view_executive_dashboard",
        filters=["date_range", "region"],
        category="strategic",
    ),
    RouteEntry(
        path="/strategy-briefing",
        label="Strategy Briefing",
        description="LLM-synthesized executive strategy briefing with follow-up Q&A. Summarizes supply chain state, risks, and recommendations.",
        keywords=["briefing", "strategy", "executive summary", "AI briefing", "risk summary"],
        capability="view_executive_dashboard",
        category="strategic",
    ),
    RouteEntry(
        path="/sop-worklist",
        label="S&OP Worklist",
        description="Sales and Operations Planning worklist — exception items requiring cross-functional review and consensus decisions.",
        keywords=["S&OP", "sales operations planning", "consensus", "exceptions", "cross-functional"],
        capability="view_sop_worklist",
        filters=["status", "product_family", "site", "date_range"],
        category="strategic",
    ),
    RouteEntry(
        path="/agent-performance",
        label="Agent Performance",
        description="AI agent performance metrics — decision accuracy, override rates, acceptance rates, response times across all TRM types.",
        keywords=["agent performance", "AI accuracy", "override rate", "decision quality", "agent metrics"],
        capability="view_executive_dashboard",
        filters=["trm_type", "date_range"],
        category="strategic",
    ),

    # ── Planning Cascade ──
    RouteEntry(
        path="/planning/cascade",
        label="Planning Cascade",
        description="Modular Adaptive Decision Hierarchy — shows all Powell layers from strategic S&OP to execution TRMs with status and health.",
        keywords=["cascade", "planning hierarchy", "Powell layers", "decision architecture"],
        capability="view_cascade_dashboard",
        category="planning",
    ),
    RouteEntry(
        path="/planning/sop",
        label="S&OP Planning",
        description="Sales and Operations Planning — strategic demand-supply balancing, policy parameters, consensus board.",
        keywords=["S&OP", "sales operations", "demand supply balance", "consensus", "strategic planning"],
        capability="view_sop",
        filters=["product_family", "region", "date_range"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/sop-policy",
        label="S&OP Policy",
        description="S&OP policy parameters — safety stock multipliers, service level targets, allocation priorities by site and product.",
        keywords=["policy parameters", "safety stock multiplier", "service level target", "allocation priority"],
        capability="view_sop_policy",
        filters=["site", "product"],
        category="planning",
    ),

    # ── Demand Planning ──
    RouteEntry(
        path="/planning/demand",
        label="Demand Plan",
        description="Demand plan view — forecast quantities by product, site, and time period with P10/P50/P90 percentiles.",
        keywords=["demand", "forecast", "demand plan", "P50", "percentile", "demand forecast"],
        capability="view_demand_planning",
        filters=["product", "site", "date_range"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/demand/edit",
        label="Edit Demand Plan",
        description="Edit demand forecasts — adjust forecast values, add overrides, manage forecast versions.",
        keywords=["edit forecast", "adjust demand", "forecast override", "demand edit"],
        capability="manage_demand_planning",
        filters=["product", "site", "date_range"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/forecasting",
        label="Forecasting",
        description="Statistical and ML demand forecasting — model selection, accuracy metrics, forecast generation.",
        keywords=["forecasting", "statistical forecast", "ML forecast", "forecast accuracy", "MAPE", "prediction"],
        capability="view_forecasting",
        filters=["product", "site", "model_type"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/forecast-exceptions",
        label="Forecast Exceptions",
        description="Forecast exceptions requiring review — outliers, accuracy violations, and anomalous demand patterns.",
        keywords=["forecast exceptions", "outliers", "anomalies", "forecast errors", "accuracy violations"],
        capability="view_forecast_exceptions",
        filters=["product", "site", "severity"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/consensus",
        label="Consensus Planning",
        description="Consensus demand planning — compare statistical, sales, and marketing forecasts to reach agreed demand numbers.",
        keywords=["consensus", "demand consensus", "forecast agreement", "collaborative planning"],
        capability="view_demand_planning",
        filters=["product_family", "region"],
        category="planning",
    ),

    # ── Supply Planning ──
    RouteEntry(
        path="/planning/supply-plan",
        label="Supply Plan",
        description="Supply plan generation and review — generates PO, TO, and MO requests based on demand, inventory, and sourcing rules.",
        keywords=["supply plan", "supply planning", "PO requests", "TO requests", "MO requests", "net requirements"],
        capability="view_supply_plan",
        filters=["product", "site", "date_range", "plan_status"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/supply-worklist",
        label="Supply Worklist",
        description="Supply plan worklist — exception items from supply plan generation that need planner review and approval.",
        keywords=["supply worklist", "supply exceptions", "supply plan review", "planner review"],
        capability="view_supply_worklist",
        filters=["product", "site", "status"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/mps",
        label="Master Production Schedule",
        description="Master Production Scheduling — production plan management with approval workflow, rough-cut capacity validation.",
        keywords=["MPS", "master production schedule", "production plan", "production scheduling"],
        capability="view_mps",
        filters=["product", "site", "date_range", "status"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/mps/capacity-check",
        label="Capacity Check",
        description="Rough-cut capacity check for the master production schedule — validates production plans against resource constraints.",
        keywords=["capacity check", "RCCP", "rough cut", "resource constraints", "capacity validation"],
        capability="view_capacity_check",
        filters=["site", "resource"],
        category="planning",
    ),
    RouteEntry(
        path="/execution/mrp",
        label="MRP Run",
        description="Material Requirements Planning — BOM explosion, component requirements, time-phased netting.",
        keywords=["MRP", "material requirements", "BOM explosion", "component planning", "netting"],
        capability="view_mrp",
        filters=["product", "site"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/sourcing",
        label="Sourcing & Allocation",
        description="Sourcing rules and allocation — buy, transfer, and manufacture priorities by product and site.",
        keywords=["sourcing", "allocation", "sourcing rules", "buy transfer manufacture", "supplier allocation"],
        capability="view_sourcing_allocation",
        filters=["product", "site", "source_type"],
        category="planning",
    ),

    # ── Inventory ──
    RouteEntry(
        path="/planning/inventory-optimization",
        label="Inventory Optimization",
        description="Inventory optimization — safety stock policies (8 types), target levels, policy management by product and site.",
        keywords=["inventory optimization", "safety stock", "inventory buffer", "reorder point", "inventory policy", "DOC", "service level"],
        capability="view_inventory_optimization",
        filters=["product", "site", "policy_type"],
        category="planning",
    ),
    RouteEntry(
        path="/visibility/inventory",
        label="Inventory Visibility",
        description="Current inventory levels across all sites — on-hand, in-transit, allocated, available quantities.",
        keywords=["inventory", "stock levels", "on-hand", "in-transit", "available inventory", "inventory visibility"],
        capability="view_inventory_visibility",
        filters=["product", "site", "region"],
        category="visibility",
    ),
    RouteEntry(
        path="/planning/inventory-projection",
        label="Inventory Projection",
        description="Forward inventory projection — simulates future inventory levels based on demand, supply plans, and lead times.",
        keywords=["inventory projection", "future inventory", "stock projection", "inventory forecast"],
        filters=["product", "site", "date_range"],
        category="planning",
    ),

    # ── Execution Worklists (11 TRM types) ──
    RouteEntry(
        path="/planning/execution/atp-worklist",
        label="ATP Worklist",
        description="Available-to-Promise worklist — ATP decisions pending review, order promising with priority consumption.",
        keywords=["ATP", "available to promise", "order promising", "allocation", "fulfillment"],
        capability="view_atp_worklist",
        filters=["site", "product", "status", "priority", "date_range"],
        category="execution",
    ),
    RouteEntry(
        path="/planning/execution/rebalancing-worklist",
        label="Rebalancing Worklist",
        description="Inventory rebalancing worklist — cross-location transfer recommendations to optimize stock distribution.",
        keywords=["rebalancing", "inventory transfer", "cross-location", "stock redistribution", "lateral transfer"],
        capability="view_rebalancing_worklist",
        filters=["site", "product", "status", "date_range"],
        category="execution",
    ),
    RouteEntry(
        path="/planning/execution/po-worklist",
        label="PO Worklist",
        description="Purchase Order worklist — PO creation decisions with timing, quantity, and supplier recommendations.",
        keywords=["purchase order", "PO", "procurement", "supplier order", "buying", "purchasing"],
        capability="view_po_worklist",
        filters=["site", "product", "supplier", "status", "date_range"],
        category="execution",
    ),
    RouteEntry(
        path="/planning/execution/order-tracking-worklist",
        label="Order Tracking Worklist",
        description="Order tracking exceptions — late shipments, quantity discrepancies, and order anomalies requiring attention.",
        keywords=["order tracking", "late orders", "order exceptions", "shipment delays", "order discrepancies"],
        capability="view_order_tracking_worklist",
        filters=["site", "product", "status", "exception_type", "date_range"],
        category="execution",
    ),
    RouteEntry(
        path="/planning/execution/mo-worklist",
        label="MO Worklist",
        description="Manufacturing Order worklist — production order release, sequencing, expedite, and split decisions.",
        keywords=["manufacturing order", "MO", "production order", "work order", "manufacturing", "production"],
        capability="view_mo_worklist",
        filters=["site", "product", "status", "date_range"],
        category="execution",
    ),
    RouteEntry(
        path="/planning/execution/to-worklist",
        label="TO Worklist",
        description="Transfer Order worklist — transfer order release, consolidation, mode selection, and expedite decisions.",
        keywords=["transfer order", "TO", "logistics", "shipment", "transport", "freight"],
        capability="view_to_worklist",
        filters=["site", "product", "status", "date_range"],
        category="execution",
    ),
    RouteEntry(
        path="/planning/execution/quality-worklist",
        label="Quality Worklist",
        description="Quality disposition worklist — quality holds, inspection results, rework/scrap/use-as-is decisions.",
        keywords=["quality", "quality hold", "inspection", "disposition", "rework", "scrap", "defect"],
        capability="view_quality_worklist",
        filters=["site", "product", "status", "disposition_type"],
        category="execution",
    ),
    RouteEntry(
        path="/planning/execution/maintenance-worklist",
        label="Maintenance Worklist",
        description="Maintenance scheduling worklist — preventive maintenance scheduling, deferral, and expedite decisions.",
        keywords=["maintenance", "preventive maintenance", "PM", "work order", "equipment", "downtime", "asset"],
        capability="view_maintenance_worklist",
        filters=["site", "status", "asset", "date_range"],
        category="execution",
    ),
    RouteEntry(
        path="/planning/execution/subcontracting-worklist",
        label="Subcontracting Worklist",
        description="Subcontracting worklist — make-vs-buy decisions, external manufacturing routing.",
        keywords=["subcontracting", "make vs buy", "outsource", "external manufacturing", "contract manufacturing"],
        capability="view_subcontracting_worklist",
        filters=["site", "product", "status", "date_range"],
        category="execution",
    ),
    RouteEntry(
        path="/planning/execution/forecast-adj-worklist",
        label="Forecast Adjustment Worklist",
        description="Forecast adjustment worklist — signal-driven forecast adjustments from email, voice, or market intelligence.",
        keywords=["forecast adjustment", "demand signal", "forecast override", "market intelligence", "demand change"],
        capability="view_forecast_adj_worklist",
        filters=["site", "product", "signal_type", "status", "date_range"],
        category="execution",
    ),
    RouteEntry(
        path="/planning/execution/buffer-worklist",
        label="Inventory Buffer Worklist",
        description="Inventory buffer worklist — safety stock parameter adjustments and reoptimization decisions.",
        keywords=["inventory buffer", "safety stock adjustment", "buffer optimization", "SS adjustment", "inventory policy change"],
        capability="view_buffer_worklist",
        filters=["site", "product", "status", "date_range"],
        category="execution",
    ),

    # ── Orders & Visibility ──
    RouteEntry(
        path="/planning/orders",
        label="Order Planning",
        description="Order planning overview — inbound and outbound order status, fulfillment rates, and order pipeline.",
        keywords=["orders", "order planning", "order status", "fulfillment", "order pipeline"],
        capability="view_order_planning",
        filters=["site", "product", "order_type", "status", "date_range"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/order-management",
        label="Order Management",
        description="Detailed order management — create, view, edit purchase orders, transfer orders, and production orders.",
        keywords=["order management", "create order", "edit order", "order details"],
        capability="view_purchase_orders",
        filters=["order_type", "status", "site", "date_range"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/purchase-orders",
        label="Purchase Orders",
        description="Purchase order list — all POs with status, supplier, quantities, delivery dates.",
        keywords=["purchase orders", "PO list", "procurement orders", "supplier orders"],
        capability="view_order_management",
        filters=["supplier", "site", "status", "date_range"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/transfer-orders",
        label="Transfer Orders",
        description="Transfer order list — all inter-site transfers with status, quantities, transit times.",
        keywords=["transfer orders", "inter-site transfers", "TO list", "logistics orders"],
        capability="view_order_management",
        filters=["site", "status", "date_range"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/production-orders",
        label="Production Orders",
        description="Production order list — all manufacturing orders with status, quantities, and scheduling.",
        keywords=["production orders", "manufacturing orders", "MO list", "work orders"],
        filters=["site", "product", "status", "date_range"],
        category="planning",
    ),
    RouteEntry(
        path="/visibility/shipments",
        label="Shipment Tracking",
        description="Shipment tracking — in-transit shipments, delivery status, estimated arrival times, exceptions.",
        keywords=["shipments", "tracking", "delivery", "in-transit", "shipment status", "logistics"],
        capability="view_shipment_tracking",
        filters=["site", "status", "carrier", "date_range"],
        category="visibility",
    ),
    RouteEntry(
        path="/execution/atp-ctp",
        label="ATP/CTP",
        description="Available-to-Promise / Capable-to-Promise — check product availability and delivery dates for customer orders.",
        keywords=["ATP", "CTP", "available to promise", "capable to promise", "delivery date", "availability check"],
        capability="view_atp_ctp",
        filters=["product", "site", "date"],
        category="execution",
    ),

    # ── Capacity ──
    RouteEntry(
        path="/planning/capacity",
        label="Capacity Planning",
        description="Capacity planning — resource utilization, bottleneck identification, capacity requirements vs availability.",
        keywords=["capacity", "capacity planning", "utilization", "bottleneck", "resource planning", "capacity constraint"],
        filters=["site", "resource", "date_range"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/resource-capacity",
        label="Resource Capacity",
        description="Resource capacity details — per-resource utilization rates, shift patterns, capacity profiles.",
        keywords=["resource capacity", "utilization rate", "shift", "capacity profile"],
        capability="view_resource_capacity",
        filters=["site", "resource", "date_range"],
        category="planning",
    ),

    # ── Analytics ──
    RouteEntry(
        path="/analytics",
        label="Analytics Dashboard",
        description="Supply chain analytics dashboard — charts, trends, and KPI visualization across demand, supply, and inventory.",
        keywords=["analytics", "charts", "trends", "KPI", "dashboard", "reporting"],
        capability="view_analytics",
        filters=["date_range", "region", "product_family"],
        category="analytics",
    ),
    RouteEntry(
        path="/sc-analytics",
        label="Supply Chain Analytics",
        description="Supply chain-specific analytics — network flow, bullwhip metrics, fill rates, cost analysis.",
        keywords=["supply chain analytics", "bullwhip", "fill rate", "cost analysis", "network flow"],
        capability="view_analytics",
        filters=["date_range", "site", "product"],
        category="analytics",
    ),
    RouteEntry(
        path="/planning/kpi-monitoring",
        label="KPI Monitoring",
        description="Real-time KPI monitoring — service level, OTIF, inventory turns, days of supply, cost metrics.",
        keywords=["KPI", "monitoring", "service level", "OTIF", "inventory turns", "days of supply"],
        capability="view_kpi_monitoring",
        filters=["site", "product_family", "date_range"],
        category="analytics",
    ),
    RouteEntry(
        path="/planning/metrics",
        label="Hierarchical Metrics",
        description="Hierarchical metrics dashboard — drill-down metrics by region, site, product family, and product.",
        keywords=["metrics", "hierarchical", "drill-down", "regional metrics", "site metrics"],
        capability="view_kpi_monitoring",
        filters=["region", "site", "product_family", "product"],
        category="analytics",
    ),
    RouteEntry(
        path="/analytics/risk",
        label="Risk Analysis",
        description="Supply chain risk analysis — supplier concentration, single-source risk, network vulnerability assessment.",
        keywords=["risk", "risk analysis", "supplier risk", "concentration risk", "vulnerability", "exposure"],
        capability="view_risk_analysis",
        filters=["site", "supplier", "risk_type"],
        category="analytics",
    ),
    RouteEntry(
        path="/analytics/uncertainty",
        label="Uncertainty Quantification",
        description="Uncertainty quantification — conformal prediction intervals, calibration status, coverage metrics.",
        keywords=["uncertainty", "conformal prediction", "prediction intervals", "calibration", "coverage", "confidence"],
        capability="view_uncertainty_quantification",
        filters=["entity_type", "product", "site"],
        category="analytics",
    ),
    RouteEntry(
        path="/analytics/inventory-optimization",
        label="Inventory Analytics",
        description="Inventory optimization analytics — policy effectiveness, excess/shortage analysis, inventory health.",
        keywords=["inventory analytics", "excess inventory", "shortage", "inventory health", "stock analysis"],
        capability="view_inventory_optimization_analytics",
        filters=["site", "product", "policy_type"],
        category="analytics",
    ),
    RouteEntry(
        path="/analytics/capacity-optimization",
        label="Capacity Analytics",
        description="Capacity optimization analytics — utilization trends, bottleneck history, capacity waste analysis.",
        keywords=["capacity analytics", "utilization trends", "bottleneck analysis", "capacity waste"],
        capability="view_capacity_optimization_analytics",
        filters=["site", "resource", "date_range"],
        category="analytics",
    ),

    # ── Insights & Recommendations ──
    RouteEntry(
        path="/insights",
        label="Insights",
        description="AI-generated insights — anomalies, patterns, and opportunities detected across the supply chain.",
        keywords=["insights", "anomalies", "patterns", "opportunities", "AI insights"],
        capability="view_analytics",
        filters=["category", "severity", "date_range"],
        category="analytics",
    ),
    RouteEntry(
        path="/insights/actions",
        label="Recommended Actions",
        description="Recommended actions dashboard — AI-suggested corrective actions with expected impact and priority.",
        keywords=["recommended actions", "recommendations", "corrective actions", "suggestions", "what to do"],
        capability="view_recommendations",
        filters=["action_type", "priority", "status"],
        category="analytics",
    ),
    RouteEntry(
        path="/planning/recommendations",
        label="Planning Recommendations",
        description="Planning recommendations — AI-generated rebalancing, procurement, and policy adjustment recommendations.",
        keywords=["planning recommendations", "rebalancing recommendations", "procurement suggestions"],
        capability="view_recommendations",
        filters=["recommendation_type", "site", "product"],
        category="planning",
    ),

    # ── Suppliers & Lead Times ──
    RouteEntry(
        path="/planning/suppliers",
        label="Supplier Management",
        description="Supplier management — vendor list, performance scores, contact details, and sourcing rules.",
        keywords=["suppliers", "vendors", "supplier management", "vendor performance", "supplier list"],
        filters=["region", "performance_tier"],
        category="planning",
    ),
    RouteEntry(
        path="/planning/vendor-lead-times",
        label="Vendor Lead Times",
        description="Vendor lead time data — historical and current lead times by product and supplier.",
        keywords=["lead times", "vendor lead time", "supplier lead time", "delivery time"],
        capability="view_vendor_lead_times",
        filters=["supplier", "product", "site"],
        category="planning",
    ),

    # ── Monte Carlo & Simulation ──
    RouteEntry(
        path="/planning/monte-carlo",
        label="Monte Carlo Simulation",
        description="Monte Carlo simulation — stochastic scenario analysis with demand, lead time, and yield variability.",
        keywords=["Monte Carlo", "simulation", "stochastic", "scenario analysis", "what-if", "risk simulation"],
        filters=["product", "site", "num_scenarios"],
        category="planning",
    ),

    # ── Admin — AI & Agents ──
    RouteEntry(
        path="/admin/trm",
        label="TRM Dashboard",
        description="TRM agent training dashboard — training status, model management, testing across all 11 TRM types.",
        keywords=["TRM", "agent training", "model training", "TRM dashboard"],
        category="admin",
    ),
    RouteEntry(
        path="/admin/gnn",
        label="GNN Dashboard",
        description="Temporal GNN training dashboard — execution-level GNN model training and evaluation.",
        keywords=["GNN", "graph neural network", "GNN training", "temporal GNN"],
        category="admin",
    ),
    RouteEntry(
        path="/admin/graphsage",
        label="GraphSAGE Dashboard",
        description="S&OP GraphSAGE model training — strategic network analysis, criticality scoring, resilience metrics.",
        keywords=["GraphSAGE", "S&OP model", "network analysis", "strategic model"],
        category="admin",
    ),
    RouteEntry(
        path="/admin/powell",
        label="Powell Dashboard",
        description="Powell SDAM framework dashboard — state, decision, policy, and outcomes visualization.",
        keywords=["Powell", "SDAM", "framework", "state decision", "policy parameters"],
        category="admin",
    ),
    RouteEntry(
        path="/admin/hive",
        label="Hive Dashboard",
        description="TRM Hive visualization — urgency vectors, signal bus, decision cycle phases, inter-agent coordination.",
        keywords=["hive", "urgency", "signal bus", "TRM coordination", "decision cycle"],
        category="admin",
    ),
    RouteEntry(
        path="/admin/skills",
        label="Claude Skills",
        description="Claude Skills monitoring — exception handler stats, RAG memory, escalation metrics, skill performance.",
        keywords=["Claude Skills", "skills", "exception handler", "RAG", "escalation"],
        category="admin",
    ),
    RouteEntry(
        path="/admin/knowledge-base",
        label="Knowledge Base",
        description="RAG knowledge base — document management, vector search, embedding configuration.",
        keywords=["knowledge base", "RAG", "documents", "vector search", "embeddings"],
        category="admin",
    ),
    RouteEntry(
        path="/admin/stochastic-params",
        label="Stochastic Parameters",
        description="Per-agent stochastic parameter editor — distribution parameters for demand variability, lead times, yields, etc.",
        keywords=["stochastic parameters", "distribution parameters", "demand variability", "lead time distribution", "yield distribution"],
        category="admin",
    ),
    RouteEntry(
        path="/admin/email-signals",
        label="Email Signals",
        description="Email signal intelligence — GDPR-safe email ingestion, signal classification, TRM routing.",
        keywords=["email signals", "email intelligence", "signal ingestion", "email classification"],
        category="admin",
    ),
    RouteEntry(
        path="/admin/sap-data",
        label="SAP Data Management",
        description="SAP integration — connections, field mapping, data ingestion monitoring, insights and actions.",
        keywords=["SAP", "SAP integration", "field mapping", "data ingestion", "SAP connection"],
        category="admin",
    ),
    RouteEntry(
        path="/admin/authorization-protocol",
        label="Authorization Protocol",
        description="Agentic Authorization Protocol board — cross-functional negotiation threads, authorization requests.",
        keywords=["AAP", "authorization protocol", "negotiation", "cross-functional", "trade-offs"],
        category="admin",
    ),
    RouteEntry(
        path="/admin/governance",
        label="Governance",
        description="Decision governance — approval workflows, exception handling rules, escalation policies.",
        keywords=["governance", "approval", "workflow", "escalation policy", "rules"],
        category="admin",
    ),

    # ── Admin — Configuration ──
    RouteEntry(
        path="/admin/tenant/supply-chain-configs",
        label="Supply Chain Configs",
        description="Supply chain configuration management — network topology, sites, transportation lanes, products, BOMs.",
        keywords=["supply chain config", "network topology", "sites", "lanes", "products", "BOM", "configuration"],
        category="admin",
    ),
    RouteEntry(
        path="/admin/tenant/planning-hierarchy",
        label="Planning Hierarchy",
        description="Planning hierarchy configuration — MPS, MRP, and S&OP hierarchy setup by product and site levels.",
        keywords=["planning hierarchy", "MPS hierarchy", "MRP hierarchy", "aggregation levels"],
        category="admin",
    ),
    RouteEntry(
        path="/admin/users",
        label="User Management",
        description="User management — create, edit, and manage user accounts, role assignments, and permissions.",
        keywords=["users", "user management", "accounts", "permissions", "roles"],
        category="admin",
    ),
    RouteEntry(
        path="/admin/tenants",
        label="Tenant Management",
        description="Tenant management — create and manage organizational tenants (system admin only).",
        keywords=["tenants", "organizations", "tenant management", "multi-tenant"],
        category="admin",
    ),
]

# Build lookup by path for quick access
_ROUTE_BY_PATH: Dict[str, RouteEntry] = {r.path: r for r in ROUTE_REGISTRY}


def get_accessible_routes(user_capabilities: Optional[List[str]] = None) -> List[RouteEntry]:
    """Filter routes to those the user has access to."""
    if user_capabilities is None:
        return list(ROUTE_REGISTRY)
    cap_set = set(user_capabilities)
    return [
        r for r in ROUTE_REGISTRY
        if r.capability is None or r.capability in cap_set
    ]


def build_route_context_for_llm(user_capabilities: Optional[List[str]] = None) -> str:
    """Build a compact route listing for injection into the LLM prompt.

    Format designed for minimal token usage while providing the LLM enough
    context to match queries to pages.
    """
    routes = get_accessible_routes(user_capabilities)
    lines = []
    for r in routes:
        filters_str = ", ".join(r.filters) if r.filters else "none"
        lines.append(f"- {r.path} | {r.label} | {r.description} | filters: {filters_str}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Option B: TF-IDF Embedding Fallback (no LLM required)
# ---------------------------------------------------------------------------

_tfidf_vectorizer = None
_tfidf_matrix = None
_tfidf_routes: List[RouteEntry] = []


def _build_tfidf_index():
    """Lazily build TF-IDF index from route descriptions + keywords."""
    global _tfidf_vectorizer, _tfidf_matrix, _tfidf_routes
    if _tfidf_vectorizer is not None:
        return

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError:
        logger.warning("scikit-learn not available; embedding fallback disabled")
        return

    _tfidf_routes = list(ROUTE_REGISTRY)
    corpus = []
    for r in _tfidf_routes:
        text = f"{r.label} {r.description} {' '.join(r.keywords)}"
        corpus.append(text.lower())

    _tfidf_vectorizer = TfidfVectorizer(stop_words="english", max_features=500)
    _tfidf_matrix = _tfidf_vectorizer.fit_transform(corpus)


def match_route_by_embedding(
    query: str,
    user_capabilities: Optional[List[str]] = None,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Match a query to routes using TF-IDF cosine similarity.

    Returns top_k matches with path, label, score. Used as fallback when
    the LLM is unavailable.
    """
    _build_tfidf_index()
    if _tfidf_vectorizer is None or _tfidf_matrix is None:
        return []

    from sklearn.metrics.pairwise import cosine_similarity

    query_vec = _tfidf_vectorizer.transform([query.lower()])
    scores = cosine_similarity(query_vec, _tfidf_matrix).flatten()

    # Filter by capabilities
    cap_set = set(user_capabilities) if user_capabilities else None
    results = []
    for idx in scores.argsort()[::-1]:
        route = _tfidf_routes[idx]
        if cap_set is not None and route.capability and route.capability not in cap_set:
            continue
        results.append({
            "path": route.path,
            "label": route.label,
            "description": route.description,
            "score": float(scores[idx]),
            "filters": route.filters,
        })
        if len(results) >= top_k:
            break

    return results
