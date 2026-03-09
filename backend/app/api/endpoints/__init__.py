from .auth import router as auth_router
from .users import router as users_router
from .scenario import router as scenario_router
from .model import router as model_router
from .dashboard import dashboard_router
from .config import router as config_router
from .supply_chain_config import router as supply_chain_config_router
from .tenant import router as tenant_router
from .analytics import router as analytics_router
from .advanced_analytics import router as advanced_analytics_router
from .health import router as health_router
from .metrics import router as metrics_router
from .chat import router as chat_router
from .trm import router as trm_router
from .mps import router as mps_router
from .monte_carlo import router as monte_carlo_router
from .production_orders import router as production_orders_router
from .capacity_plans import router as capacity_plans_router
from .mrp import router as mrp_router
from .purchase_orders import router as purchase_orders_router
from .transfer_orders import router as transfer_orders_router
from .supply_plan_crud import router as supply_plan_crud_router
from .atp_ctp_view import router as atp_ctp_router
from .vendor_lead_time import router as vendor_lead_time_router
from .production_process import router as production_process_router
from .resource_capacity import router as resource_capacity_router
from .demand_collaboration import router as demand_collaboration_router
from .service_order import router as service_order_router
from .analytics_optimization import router as analytics_optimization_router
from .simulation_execution import router as simulation_execution_router

# SAP Data Import Cadence & Planning Cycle Management (Feb 2026)
from .sync_jobs import router as sync_jobs_router
from .workflows import router as workflows_router
from .planning_cycles import router as planning_cycles_router
from .planning_decisions import router as planning_decisions_router

# Planning Hierarchy & Synthetic Data Generation
from .planning_hierarchy import router as planning_hierarchy_router
from .synthetic_data import router as synthetic_data_router

# SAP Data Management
from .sap_data_management import router as sap_data_management_router
from .sap_change_simulator import router as sap_change_simulator_router

# Powell Framework (SDAM)
from .powell import router as powell_router
from .site_agent import router as site_agent_router
from .powell_training import router as powell_training_router

# AIIO Framework - Insights & Actions Landing Page
from .insights import router as insights_router

# Planning Cascade (S&OP → MPS → Supply Agent → Allocation Agent)
from .planning_cascade import router as planning_cascade_router

# Deployment Pipeline (Demo System Builder)
from .deployment import router as deployment_router

# Fulfillment Orders (AWS SC Entity)
from .fulfillment_orders import router as fulfillment_orders_router

# Decision Metrics (Agent Performance) for Powell Framework Dashboards
from .decision_metrics import router as decision_metrics_router

# Export all routers
__all__ = [
    'auth_router',
    'users_router',
    'scenario_router',
    'model_router',
    'dashboard_router',
    'config_router',
    'supply_chain_config_router',
    'tenant_router',
    'analytics_router',
    'advanced_analytics_router',
    'health_router',
    'metrics_router',
    'chat_router',
    'trm_router',
    'mps_router',
    'monte_carlo_router',
    'production_orders_router',
    'capacity_plans_router',
    'mrp_router',
    'purchase_orders_router',
    'transfer_orders_router',
    'supply_plan_crud_router',
    'atp_ctp_router',
    'vendor_lead_time_router',
    'production_process_router',
    'resource_capacity_router',
    'demand_collaboration_router',
    'service_order_router',
    'analytics_optimization_router',
    'simulation_execution_router',
    # SAP Data Import Cadence & Planning Cycle Management
    'sync_jobs_router',
    'workflows_router',
    'planning_cycles_router',
    'planning_decisions_router',
    # Planning Hierarchy & Synthetic Data Generation
    'planning_hierarchy_router',
    'synthetic_data_router',
    # SAP Data Management
    'sap_data_management_router',
    'sap_change_simulator_router',
    # Powell Framework (SDAM)
    'powell_router',
    'site_agent_router',
    'powell_training_router',
    # AIIO Framework - Insights & Actions
    'insights_router',
    # Planning Cascade
    'planning_cascade_router',
    # Decision Metrics (Agent Performance)
    'decision_metrics_router',
    # Deployment Pipeline (Demo System Builder)
    'deployment_router',
    # Fulfillment Orders (AWS SC Entity)
    'fulfillment_orders_router',
]
