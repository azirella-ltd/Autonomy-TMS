from fastapi import APIRouter

from app.api.endpoints import (
    auth_router,
    users_router,
    scenario_router,
    model_router,
    dashboard_router,
    config_router,
    supply_chain_config_router,
    tenant_router,
    analytics_router,
    advanced_analytics_router,
    health_router,
    metrics_router,
    chat_router,
    trm_router,
    mps_router,
    monte_carlo_router,
    production_orders_router,
    capacity_plans_router,
    mrp_router,
    purchase_orders_router,
    transfer_orders_router,
    supply_plan_crud_router,
    atp_ctp_router,
    vendor_lead_time_router,
    production_process_router,
    resource_capacity_router,
    demand_collaboration_router,
    service_order_router,
    analytics_optimization_router,
    simulation_execution_router,
    # SAP Data Import Cadence & Planning Cycle Management
    sync_jobs_router,
    workflows_router,
    planning_cycles_router,
    planning_decisions_router,
    # Planning Hierarchy & Synthetic Data Generation
    planning_hierarchy_router,
    synthetic_data_router,
    # SAP Data Management
    sap_data_management_router,
    # Powell Framework (SDAM)
    powell_router,
    site_agent_router,
    powell_training_router,
    # AIIO Framework - Insights & Actions
    insights_router,
    # Planning Cascade (S&OP → MPS → Supply Agent → Allocation Agent)
    planning_cascade_router,
    # Decision Metrics (Agent Performance) for Powell Framework Dashboards
    decision_metrics_router,
)
from app.api.endpoints.sap_atp import router as sap_atp_router
from app.api.endpoints.capabilities import router as capabilities_router
from app.api.endpoints.user_capabilities import router as user_capabilities_router
from app.core.config import settings

api_router = APIRouter()

# Include API routes
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(scenario_router, prefix="/scenarios", tags=["scenarios"])
api_router.include_router(model_router, prefix="/model", tags=["model"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(config_router, tags=["config"])
api_router.include_router(supply_chain_config_router, prefix="/supply-chain-config", tags=["supply-chain-config"])
api_router.include_router(tenant_router, prefix="/tenants", tags=["tenants"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(advanced_analytics_router, prefix="/advanced-analytics", tags=["advanced-analytics"])
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(metrics_router, prefix="/metrics", tags=["metrics"])
api_router.include_router(chat_router, tags=["chat"])
api_router.include_router(trm_router, prefix="/trm", tags=["trm"])
api_router.include_router(mps_router, tags=["mps"])
api_router.include_router(monte_carlo_router, tags=["monte-carlo"])
api_router.include_router(production_orders_router, prefix="/production-orders", tags=["production-orders"])
api_router.include_router(capacity_plans_router, prefix="/capacity-plans", tags=["capacity-plans"])
api_router.include_router(mrp_router, tags=["mrp"])
api_router.include_router(purchase_orders_router, tags=["purchase-orders"])
api_router.include_router(transfer_orders_router, tags=["transfer-orders"])
api_router.include_router(supply_plan_crud_router, prefix="/supply-plan-crud", tags=["supply-plan-crud"])
api_router.include_router(atp_ctp_router, prefix="/atp-ctp", tags=["atp-ctp"])
api_router.include_router(vendor_lead_time_router, prefix="/vendor-lead-time", tags=["vendor-lead-time"])
api_router.include_router(production_process_router, prefix="/production-process", tags=["production-process"])
api_router.include_router(resource_capacity_router, prefix="/resource-capacity", tags=["resource-capacity"])
api_router.include_router(demand_collaboration_router, prefix="/demand-collaboration", tags=["demand-collaboration"])
api_router.include_router(service_order_router, prefix="/service-order", tags=["service-order"])
api_router.include_router(analytics_optimization_router, prefix="/analytics-optimization", tags=["analytics-optimization"])
api_router.include_router(capabilities_router)  # prefix="/capabilities" defined in router
api_router.include_router(user_capabilities_router, tags=["user-capabilities"])
api_router.include_router(simulation_execution_router, prefix="/simulation-execution", tags=["simulation-execution"])
api_router.include_router(sap_atp_router, prefix="/sap-atp", tags=["sap-atp"])

# SAP Data Import Cadence & Planning Cycle Management
api_router.include_router(sync_jobs_router, prefix="/sync-jobs", tags=["sync-jobs"])
api_router.include_router(workflows_router, prefix="/workflows", tags=["workflows"])
api_router.include_router(planning_cycles_router, prefix="/planning-cycles", tags=["planning-cycles"])
api_router.include_router(planning_decisions_router, prefix="/planning-decisions", tags=["planning-decisions"])

# Planning Hierarchy & Synthetic Data Generation
api_router.include_router(planning_hierarchy_router, prefix="/planning-hierarchy", tags=["planning-hierarchy"])
api_router.include_router(synthetic_data_router, prefix="/synthetic-data", tags=["synthetic-data"])

# SAP Data Management
api_router.include_router(sap_data_management_router, prefix="/sap-data", tags=["sap-data-management"])

# Powell Framework (SDAM) - Narrow TRM Execution
api_router.include_router(powell_router, prefix="/powell", tags=["powell"])
api_router.include_router(site_agent_router, tags=["site-agent"])
api_router.include_router(powell_training_router, prefix="/powell-training", tags=["powell-training"])

# AIIO Framework - Insights & Actions Landing Page
api_router.include_router(insights_router, tags=["insights"])

# Planning Cascade (S&OP → MPS → Supply Agent → Allocation Agent)
api_router.include_router(planning_cascade_router, prefix="/planning-cascade", tags=["planning-cascade"])

# Decision Metrics (Agent Performance) for Powell Framework Dashboards
api_router.include_router(decision_metrics_router, prefix="/decision-metrics", tags=["decision-metrics"])
