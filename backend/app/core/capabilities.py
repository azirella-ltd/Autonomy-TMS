"""
User Capability Flags System

Defines granular capabilities that users can have to access specific functionality.
Capabilities are more fine-grained than roles and determine what appears in the UI.
"""

from enum import Enum
from typing import List, Set, Callable
from dataclasses import dataclass
from functools import wraps
from fastapi import HTTPException, Depends, status


class Capability(str, Enum):
    """
    Capability flags that determine what functionality a user can access.
    These control both backend permissions and frontend UI visibility.
    """

    # Overview & Dashboard
    VIEW_DASHBOARD = "view_dashboard"
    VIEW_ANALYTICS = "view_analytics"
    VIEW_SC_ANALYTICS = "view_sc_analytics"

    # Advanced Analytics & Uncertainty Quantification
    VIEW_UNCERTAINTY_QUANTIFICATION = "view_uncertainty_quantification"  # View conformal prediction and planning method comparison

    # Insights
    VIEW_INSIGHTS = "view_insights"
    MANAGE_INSIGHTS = "manage_insights"

    # Risk Analysis & Insights (Sprint 1)
    VIEW_RISK_ANALYSIS = "view_risk_analysis"
    MANAGE_RISK_ALERTS = "manage_risk_alerts"
    VIEW_WATCHLISTS = "view_watchlists"
    MANAGE_WATCHLISTS = "manage_watchlists"
    VIEW_PREDICTIONS = "view_predictions"

    # Material Visibility (Sprint 2)
    VIEW_SHIPMENT_TRACKING = "view_shipment_tracking"
    MANAGE_SHIPMENTS = "manage_shipments"
    VIEW_INVENTORY_VISIBILITY = "view_inventory_visibility"
    MANAGE_INVENTORY_VISIBILITY = "manage_inventory_visibility"

    # Recommended Actions (Sprint 4)
    VIEW_RECOMMENDATIONS = "view_recommendations"
    GENERATE_RECOMMENDATIONS = "generate_recommendations"
    APPROVE_RECOMMENDATIONS = "approve_recommendations"
    EXECUTE_RECOMMENDATIONS = "execute_recommendations"

    # Gamification
    VIEW_GAMES = "view_games"
    CREATE_GAME = "create_game"
    PLAY_GAME = "play_game"
    DELETE_GAME = "delete_game"
    MANAGE_GAMES = "manage_games"

    # Supply Chain Design
    VIEW_SC_CONFIGS = "view_sc_configs"
    CREATE_SC_CONFIG = "create_sc_config"
    EDIT_SC_CONFIG = "edit_sc_config"
    DELETE_SC_CONFIG = "delete_sc_config"
    VIEW_INVENTORY_MODELS = "view_inventory_models"
    MANAGE_INVENTORY_MODELS = "manage_inventory_models"
    VIEW_GROUP_CONFIGS = "view_group_configs"
    MANAGE_GROUP_CONFIGS = "manage_group_configs"
    VIEW_NTIER_VISIBILITY = "view_ntier_visibility"

    # Planning & Optimization
    VIEW_ORDER_PLANNING = "view_order_planning"
    MANAGE_ORDER_PLANNING = "manage_order_planning"
    VIEW_DEMAND_PLANNING = "view_demand_planning"
    MANAGE_DEMAND_PLANNING = "manage_demand_planning"
    VIEW_FORECASTING = "view_forecasting"  # ML-based statistical forecast generation
    VIEW_DEMAND_COLLABORATION = "view_demand_collaboration"  # Demand collaboration workspace
    VIEW_FORECAST_EXCEPTIONS = "view_forecast_exceptions"  # View forecast exception alerts
    MANAGE_FORECAST_EXCEPTIONS = "manage_forecast_exceptions"  # Manage and resolve forecast exceptions
    VIEW_SUPPLY_PLANNING = "view_supply_planning"
    MANAGE_SUPPLY_PLANNING = "manage_supply_planning"
    VIEW_SUPPLY_PLAN = "view_supply_plan"  # View supply plan results
    VIEW_MPS = "view_mps"  # Master Production Scheduling
    MANAGE_MPS = "manage_mps"  # Create and manage MPS
    APPROVE_MPS = "approve_mps"  # Approve MPS plans
    VIEW_LOT_SIZING = "view_lot_sizing"  # Lot sizing within MPS
    VIEW_CAPACITY_CHECK = "view_capacity_check"  # Rough-cut capacity check
    VIEW_INVENTORY_OPTIMIZATION = "view_inventory_optimization"  # Safety stock and reorder optimization
    VIEW_SOP = "view_sop"  # Sales & Operations Planning
    VIEW_NETWORK_DESIGN = "view_network_design"  # Network design and optimization
    VIEW_PRODUCTION_PROCESS = "view_production_process"  # Manufacturing process definitions
    VIEW_SOURCING_ALLOCATION = "view_sourcing_allocation"  # Sourcing rules and allocation
    VIEW_RESOURCE_CAPACITY = "view_resource_capacity"  # Resource capacity planning
    VIEW_KPI_MONITORING = "view_kpi_monitoring"  # KPI monitoring dashboards
    VIEW_MRP = "view_mrp"  # Material Requirements Planning
    VIEW_OPTIMIZATION = "view_optimization"
    RUN_OPTIMIZATION = "run_optimization"

    # Supply Chain Planning Entities (Phase 2-3)
    VIEW_PRODUCTION_ORDERS = "view_production_orders"  # View production orders
    MANAGE_PRODUCTION_ORDERS = "manage_production_orders"  # Create and manage production orders
    RELEASE_PRODUCTION_ORDERS = "release_production_orders"  # Release production orders to shop floor
    VIEW_CAPACITY_PLANNING = "view_capacity_planning"  # View capacity plans (RCCP)
    MANAGE_CAPACITY_PLANNING = "manage_capacity_planning"  # Create and manage capacity plans
    VIEW_SUPPLIERS = "view_suppliers"  # View supplier master data
    MANAGE_SUPPLIERS = "manage_suppliers"  # Create and manage suppliers
    VIEW_SUPPLIER_MANAGEMENT = "view_supplier_management"  # Supplier management dashboard
    VIEW_VENDOR_LEAD_TIMES = "view_vendor_lead_times"  # Vendor lead time management
    VIEW_ORDER_MANAGEMENT = "view_order_management"  # Order management (PO/TO/MO)
    VIEW_INVENTORY_PROJECTION = "view_inventory_projection"  # View ATP/CTP projections
    VIEW_SALES_FORECAST = "view_sales_forecast"  # View sales forecasts
    MANAGE_SALES_FORECAST = "manage_sales_forecast"  # Create and manage sales forecasts
    VIEW_CONSENSUS_DEMAND = "view_consensus_demand"  # View consensus demand
    MANAGE_CONSENSUS_DEMAND = "manage_consensus_demand"  # Participate in consensus planning
    APPROVE_CONSENSUS_DEMAND = "approve_consensus_demand"  # Approve consensus demand
    VIEW_SCENARIOS = "view_scenarios"  # View planning scenarios
    MANAGE_SCENARIOS = "manage_scenarios"  # Create and manage scenarios
    RUN_MONTE_CARLO = "run_monte_carlo"  # Run Monte Carlo simulations
    VIEW_FULFILLMENT_ORDERS = "view_fulfillment_orders"  # View fulfillment orders
    MANAGE_FULFILLMENT_ORDERS = "manage_fulfillment_orders"  # Manage fulfillment orders
    VIEW_BACKORDERS = "view_backorders"  # View backorders
    MANAGE_BACKORDERS = "manage_backorders"  # Manage and prioritize backorders

    # Additional Order Types (Sprint 6 - Phase 3)
    VIEW_SERVICE_ORDERS = "view_service_orders"  # View service orders
    MANAGE_SERVICE_ORDERS = "manage_service_orders"  # Create and manage service orders
    VIEW_PROJECT_ORDERS = "view_project_orders"  # View project orders
    MANAGE_PROJECT_ORDERS = "manage_project_orders"  # Create and manage project orders
    APPROVE_PROJECT_ORDERS = "approve_project_orders"  # Approve project orders
    VIEW_MAINTENANCE_ORDERS = "view_maintenance_orders"  # View maintenance orders
    MANAGE_MAINTENANCE_ORDERS = "manage_maintenance_orders"  # Create and manage maintenance orders
    APPROVE_MAINTENANCE_ORDERS = "approve_maintenance_orders"  # Approve maintenance orders
    VIEW_TURNAROUND_ORDERS = "view_turnaround_orders"  # View turnaround orders
    MANAGE_TURNAROUND_ORDERS = "manage_turnaround_orders"  # Create and manage turnaround orders
    APPROVE_TURNAROUND_ORDERS = "approve_turnaround_orders"  # Approve turnaround orders

    # AI & ML Models
    VIEW_AI_AGENTS = "view_ai_agents"  # View AI agents and assistant
    MANAGE_AI_AGENTS = "manage_ai_agents"  # Configure and manage AI agents
    VIEW_SCENARIO_COMPARISON = "view_scenario_comparison"  # Side-by-side scenario comparison
    USE_AI_ASSISTANT = "use_ai_assistant"
    VIEW_TRM_TRAINING = "view_trm_training"
    START_TRM_TRAINING = "start_trm_training"
    MANAGE_TRM_MODELS = "manage_trm_models"
    VIEW_GNN_TRAINING = "view_gnn_training"
    START_GNN_TRAINING = "start_gnn_training"
    MANAGE_GNN_MODELS = "manage_gnn_models"
    VIEW_RL_TRAINING = "view_rl_training"
    START_RL_TRAINING = "start_rl_training"
    MANAGE_RL_MODELS = "manage_rl_models"
    VIEW_MODEL_SETUP = "view_model_setup"
    MANAGE_MODEL_SETUP = "manage_model_setup"

    # Deployment Pipeline (Demo System Builder)
    MANAGE_DEPLOYMENT = "manage_deployment"  # Start pipelines, download CSVs, trigger Day 2 imports

    # Powell SDAM Framework (Narrow TRM Execution Services)
    VIEW_POWELL = "view_powell"  # View Powell dashboard, AATP allocations, exception detection, rebalancing
    MANAGE_POWELL = "manage_powell"  # Configure Powell TRM services and run monitoring checks
    VIEW_ATP_CTP = "view_atp_ctp"  # View ATP/CTP allocations and consumption

    # Powell Framework Dashboard Capabilities (Feb 2026)
    VIEW_EXECUTIVE_DASHBOARD = "view_executive_dashboard"  # SC_VP landing - strategic performance metrics, ROI
    VIEW_SOP_WORKLIST = "view_sop_worklist"  # SOP_DIRECTOR landing - tactical worklist, agent recommendations
    VIEW_AGENT_DECISIONS = "view_agent_decisions"  # MPS_MANAGER - operational agent decision monitoring

    # Planning Cascade — Modular Powell Layers (Feb 2026)
    # Each layer can be sold independently; capabilities control per-layer access.
    VIEW_CASCADE_DASHBOARD = "view_cascade_dashboard"  # Cascade orchestration overview
    VIEW_SOP_POLICY = "view_sop_policy"  # Layer 1: View S&OP Policy Envelope parameters
    MANAGE_SOP_POLICY = "manage_sop_policy"  # Layer 1: Edit/approve Policy Envelope
    VIEW_MRS_CANDIDATES = "view_mrs_candidates"  # Layer 2: View Supply Baseline Pack candidates
    MANAGE_MRS_CANDIDATES = "manage_mrs_candidates"  # Layer 2: Select/blend SupBP candidates, upload plans
    VIEW_SUPPLY_WORKLIST = "view_supply_worklist"  # Layer 3: View Supply Commits
    MANAGE_SUPPLY_WORKLIST = "manage_supply_worklist"  # Layer 3: Accept/Override/Reject Supply Commits
    VIEW_ALLOCATION_WORKLIST = "view_allocation_worklist"  # Layer 4: View Allocation Commits
    MANAGE_ALLOCATION_WORKLIST = "manage_allocation_worklist"  # Layer 4: Accept/Override/Reject Allocation Commits
    VIEW_EXECUTION_DASHBOARD = "view_execution_dashboard"  # Layer 5: View MRP/Safety Stock/AATP/TRM
    MANAGE_EXECUTION_DASHBOARD = "manage_execution_dashboard"  # Layer 5: Override execution decisions, apply re-tunes

    # TRM Specialist Worklists (Feb 2026)
    # Per-TRM decision inspection and override capabilities.
    # Overrides + reasons feed back into RL training via trm_replay_buffer.
    VIEW_ATP_WORKLIST = "view_atp_worklist"  # View ATP decisions (fulfill/partial/defer/reject)
    MANAGE_ATP_WORKLIST = "manage_atp_worklist"  # Override ATP decisions with reason capture
    VIEW_REBALANCING_WORKLIST = "view_rebalancing_worklist"  # View inventory transfer recommendations
    MANAGE_REBALANCING_WORKLIST = "manage_rebalancing_worklist"  # Override rebalancing decisions
    VIEW_PO_WORKLIST = "view_po_worklist"  # View PO creation recommendations
    MANAGE_PO_WORKLIST = "manage_po_worklist"  # Override PO decisions (qty, supplier, timing)
    VIEW_ORDER_TRACKING_WORKLIST = "view_order_tracking_worklist"  # View order exceptions
    MANAGE_ORDER_TRACKING_WORKLIST = "manage_order_tracking_worklist"  # Override exception actions

    # Collaboration
    VIEW_GROUPS = "view_groups"
    CREATE_GROUP = "create_group"
    MANAGE_GROUPS = "manage_groups"
    VIEW_PLAYERS = "view_players"
    MANAGE_PLAYERS = "manage_players"
    VIEW_USERS = "view_users"
    CREATE_USER = "create_user"
    EDIT_USER = "edit_user"
    DELETE_USER = "delete_user"

    # Collaboration Hub (Sprint 5)
    VIEW_COLLABORATION = "view_collaboration"  # View A2A/H2A/H2H collaboration threads
    MANAGE_COLLABORATION = "manage_collaboration"  # Send messages, capture decisions, request approvals
    VIEW_AGENT_EXPLANATIONS = "view_agent_explanations"  # View agent decision explainability
    APPROVE_AGENT_SUGGESTIONS = "approve_agent_suggestions"  # Accept/override agent suggestions with rationale

    # Administration
    VIEW_ADMIN_DASHBOARD = "view_admin_dashboard"
    VIEW_SYSTEM_MONITORING = "view_system_monitoring"
    MANAGE_SYSTEM_CONFIG = "manage_system_config"
    VIEW_GOVERNANCE = "view_governance"
    MANAGE_GOVERNANCE = "manage_governance"
    MANAGE_PERMISSIONS = "manage_permissions"
    MANAGE_ROLES = "manage_roles"  # Configure roles and permissions
    MANAGE_GROUP_USERS = "manage_group_users"  # Manage users within a group (SAP data mgmt access)
    MANAGE_APPROVAL_TEMPLATES = "manage_approval_templates"  # Configure multi-level approval workflows

    # System-level
    SYSTEM_ADMIN = "system_admin"  # Master capability - grants all others


@dataclass
class CapabilitySet:
    """A set of capabilities for a user role or user type."""
    capabilities: Set[Capability]

    def has(self, capability: Capability) -> bool:
        """Check if this set includes a specific capability."""
        return capability in self.capabilities or Capability.SYSTEM_ADMIN in self.capabilities

    def has_any(self, *capabilities: Capability) -> bool:
        """Check if this set includes any of the given capabilities."""
        return any(self.has(cap) for cap in capabilities)

    def has_all(self, *capabilities: Capability) -> bool:
        """Check if this set includes all of the given capabilities."""
        return all(self.has(cap) for cap in capabilities)


# Predefined capability sets for common user types
SYSTEM_ADMIN_CAPABILITIES = CapabilitySet(
    capabilities={Capability.SYSTEM_ADMIN}  # Grants everything
)

GROUP_ADMIN_CAPABILITIES = CapabilitySet(
    capabilities={
        # Overview
        Capability.VIEW_DASHBOARD,
        Capability.VIEW_ANALYTICS,
        Capability.VIEW_SC_ANALYTICS,

        # Advanced Analytics
        Capability.VIEW_UNCERTAINTY_QUANTIFICATION,

        # Insights
        Capability.VIEW_INSIGHTS,

        # Risk Analysis & Insights (Sprint 1)
        Capability.VIEW_RISK_ANALYSIS,
        Capability.MANAGE_RISK_ALERTS,
        Capability.VIEW_WATCHLISTS,
        Capability.MANAGE_WATCHLISTS,
        Capability.VIEW_PREDICTIONS,

        # Material Visibility (Sprint 2)
        Capability.VIEW_SHIPMENT_TRACKING,
        Capability.MANAGE_SHIPMENTS,
        Capability.VIEW_INVENTORY_VISIBILITY,

        # Gamification - Full access
        Capability.VIEW_GAMES,
        Capability.CREATE_GAME,
        Capability.PLAY_GAME,
        Capability.DELETE_GAME,
        Capability.MANAGE_GAMES,

        # Supply Chain - View and manage group configs
        Capability.VIEW_SC_CONFIGS,
        Capability.VIEW_INVENTORY_MODELS,
        Capability.VIEW_GROUP_CONFIGS,
        Capability.MANAGE_GROUP_CONFIGS,
        Capability.VIEW_NTIER_VISIBILITY,

        # Planning - View and manage
        Capability.VIEW_ORDER_PLANNING,
        Capability.MANAGE_ORDER_PLANNING,
        Capability.VIEW_DEMAND_PLANNING,
        Capability.MANAGE_DEMAND_PLANNING,
        Capability.VIEW_FORECASTING,
        Capability.VIEW_DEMAND_COLLABORATION,
        Capability.VIEW_SUPPLY_PLANNING,
        Capability.MANAGE_SUPPLY_PLANNING,
        Capability.VIEW_SUPPLY_PLAN,
        Capability.VIEW_MPS,
        Capability.MANAGE_MPS,
        Capability.APPROVE_MPS,
        Capability.VIEW_LOT_SIZING,
        Capability.VIEW_CAPACITY_CHECK,
        Capability.VIEW_INVENTORY_OPTIMIZATION,
        Capability.VIEW_SOP,
        Capability.VIEW_NETWORK_DESIGN,
        Capability.VIEW_PRODUCTION_PROCESS,
        Capability.VIEW_SOURCING_ALLOCATION,
        Capability.VIEW_RESOURCE_CAPACITY,
        Capability.VIEW_KPI_MONITORING,
        Capability.VIEW_MRP,
        Capability.VIEW_OPTIMIZATION,
        Capability.RUN_OPTIMIZATION,

        # Supply Chain Planning Entities - Full access for Group Admin
        Capability.VIEW_PRODUCTION_ORDERS,
        Capability.MANAGE_PRODUCTION_ORDERS,
        Capability.RELEASE_PRODUCTION_ORDERS,
        Capability.VIEW_CAPACITY_PLANNING,
        Capability.MANAGE_CAPACITY_PLANNING,
        Capability.VIEW_SUPPLIERS,
        Capability.MANAGE_SUPPLIERS,
        Capability.VIEW_SUPPLIER_MANAGEMENT,
        Capability.VIEW_VENDOR_LEAD_TIMES,
        Capability.VIEW_ORDER_MANAGEMENT,
        Capability.VIEW_INVENTORY_PROJECTION,
        Capability.VIEW_SALES_FORECAST,
        Capability.MANAGE_SALES_FORECAST,
        Capability.VIEW_CONSENSUS_DEMAND,
        Capability.MANAGE_CONSENSUS_DEMAND,
        Capability.APPROVE_CONSENSUS_DEMAND,
        Capability.VIEW_SCENARIOS,
        Capability.MANAGE_SCENARIOS,
        Capability.VIEW_SCENARIO_COMPARISON,
        Capability.RUN_MONTE_CARLO,
        Capability.VIEW_FULFILLMENT_ORDERS,
        Capability.MANAGE_FULFILLMENT_ORDERS,
        Capability.VIEW_BACKORDERS,
        Capability.MANAGE_BACKORDERS,

        # Additional Order Types (Sprint 6) - Full access
        Capability.VIEW_SERVICE_ORDERS,
        Capability.MANAGE_SERVICE_ORDERS,
        Capability.VIEW_PROJECT_ORDERS,
        Capability.MANAGE_PROJECT_ORDERS,
        Capability.APPROVE_PROJECT_ORDERS,
        Capability.VIEW_MAINTENANCE_ORDERS,
        Capability.MANAGE_MAINTENANCE_ORDERS,
        Capability.APPROVE_MAINTENANCE_ORDERS,
        Capability.VIEW_TURNAROUND_ORDERS,
        Capability.MANAGE_TURNAROUND_ORDERS,
        Capability.APPROVE_TURNAROUND_ORDERS,

        # AI/ML - View only + AI Assistant
        Capability.USE_AI_ASSISTANT,
        Capability.VIEW_AI_AGENTS,
        Capability.MANAGE_AI_AGENTS,
        Capability.VIEW_TRM_TRAINING,
        Capability.VIEW_GNN_TRAINING,
        Capability.VIEW_RL_TRAINING,
        Capability.VIEW_MODEL_SETUP,

        # Deployment Pipeline
        Capability.MANAGE_DEPLOYMENT,

        # Powell SDAM Framework
        Capability.VIEW_POWELL,
        Capability.VIEW_ATP_CTP,

        # Powell Framework Dashboards (all 3 for GROUP_ADMIN to enable demo access)
        Capability.VIEW_EXECUTIVE_DASHBOARD,  # SC_VP landing
        Capability.VIEW_SOP_WORKLIST,         # SOP_DIRECTOR landing
        Capability.VIEW_AGENT_DECISIONS,      # MPS_MANAGER landing

        # Planning Cascade - Full access to all layers (GROUP_ADMIN)
        Capability.VIEW_CASCADE_DASHBOARD,
        Capability.VIEW_SOP_POLICY,
        Capability.MANAGE_SOP_POLICY,
        Capability.VIEW_MRS_CANDIDATES,
        Capability.MANAGE_MRS_CANDIDATES,
        Capability.VIEW_SUPPLY_WORKLIST,
        Capability.MANAGE_SUPPLY_WORKLIST,
        Capability.VIEW_ALLOCATION_WORKLIST,
        Capability.MANAGE_ALLOCATION_WORKLIST,
        Capability.VIEW_EXECUTION_DASHBOARD,
        Capability.MANAGE_EXECUTION_DASHBOARD,

        # TRM Specialist Worklists - Full access to all TRMs (GROUP_ADMIN)
        Capability.VIEW_ATP_WORKLIST,
        Capability.MANAGE_ATP_WORKLIST,
        Capability.VIEW_REBALANCING_WORKLIST,
        Capability.MANAGE_REBALANCING_WORKLIST,
        Capability.VIEW_PO_WORKLIST,
        Capability.MANAGE_PO_WORKLIST,
        Capability.VIEW_ORDER_TRACKING_WORKLIST,
        Capability.MANAGE_ORDER_TRACKING_WORKLIST,

        # Collaboration - Full access within group
        Capability.VIEW_GROUPS,
        Capability.MANAGE_GROUPS,
        Capability.VIEW_PLAYERS,
        Capability.MANAGE_PLAYERS,
        Capability.VIEW_USERS,
        Capability.CREATE_USER,
        Capability.EDIT_USER,
        Capability.MANAGE_PERMISSIONS,
        Capability.MANAGE_ROLES,
        Capability.MANAGE_GROUP_USERS,
        Capability.MANAGE_APPROVAL_TEMPLATES,

        # Collaboration Hub (Sprint 5) - Full access
        Capability.VIEW_COLLABORATION,
        Capability.MANAGE_COLLABORATION,
        Capability.VIEW_AGENT_EXPLANATIONS,
        Capability.APPROVE_AGENT_SUGGESTIONS,

        # Recommended Actions (Sprint 4) - Full access
        Capability.VIEW_RECOMMENDATIONS,
        Capability.GENERATE_RECOMMENDATIONS,
        Capability.APPROVE_RECOMMENDATIONS,
        Capability.EXECUTE_RECOMMENDATIONS,
    }
)

USER_CAPABILITIES = CapabilitySet(
    capabilities={
        # Overview - Users only see their game dashboard
        Capability.VIEW_DASHBOARD,

        # Gamification - Play games only
        Capability.VIEW_GAMES,
        Capability.PLAY_GAME,
    }
)


# =============================================================================
# Powell Framework Aligned Role Capability Sets
# =============================================================================
# These capability sets map to the Powell SDAM framework hierarchy:
# - SC_VP (CFA Level): Strategic, sets policy parameters θ, approves decisions
# - SOP_DIRECTOR (S&OP Level): Tactical, accepts/overrides AI recommendations
# - MPS_MANAGER (tGNN+TRM Level): Operational, works with AI agents for execution
#
# IMPORTANT: AI model training (TRM, GNN, RL) is GROUP_ADMIN responsibility,
# not SC_VP. GROUP_ADMIN manages training cadence for both Training and
# Operational groups.
#
# See POWELL_APPROACH.md for framework documentation
# =============================================================================

# Supply Chain VP - Strategic/CFA Level (Powell Framework)
#
# Responsibilities:
# - Set policy parameters θ (inventory policies, safety stock multipliers)
# - Set global constraints and strategic parameters
# - Approve major planning decisions (MPS, consensus demand)
# - Full visibility across all sites and products
# NOTE: AI model training is GROUP_ADMIN responsibility (VIEW only for SC_VP)
SC_VP_CAPABILITIES = CapabilitySet(
    capabilities={
        # Powell Dashboard - Executive Dashboard (SC_VP landing page)
        Capability.VIEW_EXECUTIVE_DASHBOARD,

        # Overview - Full dashboard access
        Capability.VIEW_DASHBOARD,
        Capability.VIEW_ANALYTICS,
        Capability.VIEW_SC_ANALYTICS,
        Capability.VIEW_UNCERTAINTY_QUANTIFICATION,

        # Insights - Full access
        Capability.VIEW_INSIGHTS,
        Capability.MANAGE_INSIGHTS,

        # Risk Analysis - Full strategic oversight
        Capability.VIEW_RISK_ANALYSIS,
        Capability.MANAGE_RISK_ALERTS,
        Capability.VIEW_WATCHLISTS,
        Capability.MANAGE_WATCHLISTS,
        Capability.VIEW_PREDICTIONS,

        # Supply Chain Design - Full configuration
        Capability.VIEW_SC_CONFIGS,
        Capability.CREATE_SC_CONFIG,
        Capability.EDIT_SC_CONFIG,
        Capability.VIEW_INVENTORY_MODELS,
        Capability.MANAGE_INVENTORY_MODELS,
        Capability.VIEW_GROUP_CONFIGS,
        Capability.MANAGE_GROUP_CONFIGS,
        Capability.VIEW_NTIER_VISIBILITY,

        # Strategic Planning - Full authority
        Capability.VIEW_SOP,
        Capability.VIEW_NETWORK_DESIGN,
        Capability.VIEW_DEMAND_PLANNING,
        Capability.MANAGE_DEMAND_PLANNING,
        Capability.VIEW_FORECASTING,
        Capability.VIEW_DEMAND_COLLABORATION,
        Capability.VIEW_SUPPLY_PLANNING,
        Capability.MANAGE_SUPPLY_PLANNING,
        Capability.VIEW_SUPPLY_PLAN,
        Capability.VIEW_CONSENSUS_DEMAND,
        Capability.MANAGE_CONSENSUS_DEMAND,
        Capability.APPROVE_CONSENSUS_DEMAND,  # Strategic approval
        Capability.VIEW_SCENARIOS,
        Capability.MANAGE_SCENARIOS,
        Capability.VIEW_SCENARIO_COMPARISON,
        Capability.RUN_MONTE_CARLO,
        Capability.VIEW_OPTIMIZATION,
        Capability.RUN_OPTIMIZATION,
        Capability.VIEW_KPI_MONITORING,
        Capability.VIEW_INVENTORY_OPTIMIZATION,
        Capability.VIEW_SOURCING_ALLOCATION,

        # Tactical Planning - Approval authority
        Capability.VIEW_MPS,
        Capability.MANAGE_MPS,
        Capability.APPROVE_MPS,  # Strategic approval
        Capability.VIEW_LOT_SIZING,
        Capability.VIEW_CAPACITY_CHECK,
        Capability.VIEW_CAPACITY_PLANNING,
        Capability.MANAGE_CAPACITY_PLANNING,
        Capability.VIEW_RESOURCE_CAPACITY,

        # AI Model Training - VIEW ONLY (training is GROUP_ADMIN responsibility)
        Capability.USE_AI_ASSISTANT,
        Capability.VIEW_AI_AGENTS,
        Capability.VIEW_TRM_TRAINING,
        Capability.VIEW_GNN_TRAINING,
        Capability.VIEW_RL_TRAINING,
        Capability.VIEW_MODEL_SETUP,

        # Deployment Pipeline
        Capability.MANAGE_DEPLOYMENT,

        # Powell Framework - Full configuration
        Capability.VIEW_POWELL,
        Capability.MANAGE_POWELL,
        Capability.VIEW_ATP_CTP,

        # Planning Cascade - Strategic: owns L1 (S&OP), views all layers
        Capability.VIEW_CASCADE_DASHBOARD,
        Capability.VIEW_SOP_POLICY,
        Capability.MANAGE_SOP_POLICY,  # SC_VP owns Policy Envelope
        Capability.VIEW_MRS_CANDIDATES,
        Capability.VIEW_SUPPLY_WORKLIST,
        Capability.VIEW_ALLOCATION_WORKLIST,
        Capability.VIEW_EXECUTION_DASHBOARD,

        # Collaboration Hub - Agent oversight
        Capability.VIEW_COLLABORATION,
        Capability.MANAGE_COLLABORATION,
        Capability.VIEW_AGENT_EXPLANATIONS,
        Capability.APPROVE_AGENT_SUGGESTIONS,

        # Recommendations - Strategic approval
        Capability.VIEW_RECOMMENDATIONS,
        Capability.GENERATE_RECOMMENDATIONS,
        Capability.APPROVE_RECOMMENDATIONS,
        Capability.EXECUTE_RECOMMENDATIONS,

        # User Management - Manage team
        Capability.VIEW_USERS,
        Capability.CREATE_USER,
        Capability.EDIT_USER,
        Capability.MANAGE_PERMISSIONS,
        Capability.MANAGE_APPROVAL_TEMPLATES,

        # View operational items (visibility, not management)
        Capability.VIEW_ORDER_PLANNING,
        Capability.VIEW_PRODUCTION_ORDERS,
        Capability.VIEW_PRODUCTION_PROCESS,
        Capability.VIEW_MRP,
        Capability.VIEW_ORDER_MANAGEMENT,
        Capability.VIEW_SUPPLIERS,
        Capability.VIEW_SUPPLIER_MANAGEMENT,
        Capability.VIEW_VENDOR_LEAD_TIMES,
        Capability.VIEW_INVENTORY_PROJECTION,
        Capability.VIEW_SALES_FORECAST,
        Capability.VIEW_FULFILLMENT_ORDERS,
        Capability.VIEW_BACKORDERS,
        Capability.VIEW_SERVICE_ORDERS,
        Capability.VIEW_SHIPMENT_TRACKING,
        Capability.VIEW_INVENTORY_VISIBILITY,
    }
)

# S&OP Director - Tactical Level (Powell Framework)
#
# Responsibilities:
# - Run S&OP processes and consensus planning
# - Accept/override AI recommendations within policy bounds
# - Set group policy within strategic constraints
# - Cannot train AI models (view training status only)
# - Product category scope (e.g., specific product families)
SOP_DIRECTOR_CAPABILITIES = CapabilitySet(
    capabilities={
        # Powell Dashboard - S&OP Worklist (SOP_DIRECTOR landing page)
        Capability.VIEW_SOP_WORKLIST,

        # Overview - Tactical dashboards
        Capability.VIEW_DASHBOARD,
        Capability.VIEW_ANALYTICS,
        Capability.VIEW_SC_ANALYTICS,
        Capability.VIEW_UNCERTAINTY_QUANTIFICATION,

        # Insights
        Capability.VIEW_INSIGHTS,
        Capability.MANAGE_INSIGHTS,

        # Risk Analysis - Manage alerts
        Capability.VIEW_RISK_ANALYSIS,
        Capability.MANAGE_RISK_ALERTS,
        Capability.VIEW_WATCHLISTS,
        Capability.MANAGE_WATCHLISTS,
        Capability.VIEW_PREDICTIONS,

        # Supply Chain Design - View only (strategic decisions)
        Capability.VIEW_SC_CONFIGS,
        Capability.VIEW_INVENTORY_MODELS,
        Capability.VIEW_GROUP_CONFIGS,
        Capability.VIEW_NTIER_VISIBILITY,

        # S&OP Planning - Full tactical authority
        Capability.VIEW_SOP,
        Capability.VIEW_DEMAND_PLANNING,
        Capability.MANAGE_DEMAND_PLANNING,
        Capability.VIEW_FORECASTING,
        Capability.VIEW_DEMAND_COLLABORATION,
        Capability.VIEW_FORECAST_EXCEPTIONS,
        Capability.MANAGE_FORECAST_EXCEPTIONS,
        Capability.VIEW_SUPPLY_PLANNING,
        Capability.MANAGE_SUPPLY_PLANNING,
        Capability.VIEW_SUPPLY_PLAN,
        Capability.VIEW_CONSENSUS_DEMAND,
        Capability.MANAGE_CONSENSUS_DEMAND,
        Capability.VIEW_SALES_FORECAST,
        Capability.MANAGE_SALES_FORECAST,
        Capability.VIEW_SCENARIOS,
        Capability.MANAGE_SCENARIOS,
        Capability.VIEW_SCENARIO_COMPARISON,
        Capability.RUN_MONTE_CARLO,
        Capability.VIEW_OPTIMIZATION,
        Capability.VIEW_INVENTORY_OPTIMIZATION,
        Capability.VIEW_SOURCING_ALLOCATION,
        Capability.VIEW_KPI_MONITORING,
        Capability.VIEW_PRODUCTION_PROCESS,
        Capability.VIEW_RESOURCE_CAPACITY,

        # MPS - Manage but not approve (approval goes to VP)
        Capability.VIEW_MPS,
        Capability.MANAGE_MPS,
        Capability.VIEW_LOT_SIZING,
        Capability.VIEW_CAPACITY_CHECK,
        Capability.VIEW_CAPACITY_PLANNING,
        Capability.MANAGE_CAPACITY_PLANNING,
        Capability.VIEW_MRP,

        # AI Models - View only (cannot train, CFA is VP responsibility)
        Capability.USE_AI_ASSISTANT,
        Capability.VIEW_AI_AGENTS,
        Capability.VIEW_TRM_TRAINING,
        Capability.VIEW_GNN_TRAINING,
        Capability.VIEW_RL_TRAINING,
        Capability.VIEW_MODEL_SETUP,

        # Powell Framework - View allocations, manage operational decisions
        Capability.VIEW_POWELL,
        Capability.VIEW_ATP_CTP,

        # Planning Cascade - Tactical: owns L2 (MRS), manages L3-L4, views L1/L5
        Capability.VIEW_CASCADE_DASHBOARD,
        Capability.VIEW_SOP_POLICY,  # Views PE from SC_VP (no manage)
        Capability.VIEW_MRS_CANDIDATES,
        Capability.MANAGE_MRS_CANDIDATES,  # SOP_DIRECTOR owns SupBP selection
        Capability.VIEW_SUPPLY_WORKLIST,
        Capability.MANAGE_SUPPLY_WORKLIST,  # Accept/Override Supply Commits
        Capability.VIEW_ALLOCATION_WORKLIST,
        Capability.MANAGE_ALLOCATION_WORKLIST,  # Accept/Override Allocation Commits
        Capability.VIEW_EXECUTION_DASHBOARD,

        # Collaboration Hub - Approve agent suggestions
        Capability.VIEW_COLLABORATION,
        Capability.MANAGE_COLLABORATION,
        Capability.VIEW_AGENT_EXPLANATIONS,
        Capability.APPROVE_AGENT_SUGGESTIONS,

        # Recommendations - Generate and approve within bounds
        Capability.VIEW_RECOMMENDATIONS,
        Capability.GENERATE_RECOMMENDATIONS,
        Capability.APPROVE_RECOMMENDATIONS,

        # Operational visibility
        Capability.VIEW_ORDER_PLANNING,
        Capability.MANAGE_ORDER_PLANNING,
        Capability.VIEW_PRODUCTION_ORDERS,
        Capability.VIEW_ORDER_MANAGEMENT,
        Capability.VIEW_SUPPLIERS,
        Capability.MANAGE_SUPPLIERS,
        Capability.VIEW_SUPPLIER_MANAGEMENT,
        Capability.VIEW_VENDOR_LEAD_TIMES,
        Capability.VIEW_INVENTORY_PROJECTION,
        Capability.VIEW_FULFILLMENT_ORDERS,
        Capability.MANAGE_FULFILLMENT_ORDERS,
        Capability.VIEW_BACKORDERS,
        Capability.MANAGE_BACKORDERS,
        Capability.VIEW_SERVICE_ORDERS,
        Capability.VIEW_SHIPMENT_TRACKING,
        Capability.VIEW_INVENTORY_VISIBILITY,

        # Team visibility
        Capability.VIEW_USERS,
        Capability.VIEW_PLAYERS,
    }
)

# Allocation Manager - Narrow Scope (Powell Framework)
#
# Responsibilities:
# - Inspect and override tGNN-generated priority allocations
# - Review Allocation Commits (accept/override with reason)
# - View S&OP Policy Envelope as context (guardrails)
# - Cannot access planning, execution, or other worklists
# - Lands on: /planning/allocation-worklist
ALLOCATION_MANAGER_CAPABILITIES = CapabilitySet(
    capabilities={
        # Allocation Worklist (Layer 4) - Primary responsibility
        Capability.VIEW_ALLOCATION_WORKLIST,
        Capability.MANAGE_ALLOCATION_WORKLIST,

        # S&OP Policy Envelope (Layer 1) - View-only context for guardrails
        Capability.VIEW_SOP_POLICY,

        # Agent explanations - Ask Why on allocation commits
        Capability.VIEW_AGENT_EXPLANATIONS,
    }
)

# Order Promise Manager - Narrow Scope (Powell Framework)
#
# Responsibilities:
# - Inspect and override TRM order promising / ATP consumption decisions
# - View allocations as context (what was allocated to each priority tier)
# - View S&OP Policy Envelope for OTIF floors (performance expectations)
# - Cannot access planning, supply worklist, or broader execution
# - Lands on: /planning/execution/atp-worklist
ORDER_PROMISE_MANAGER_CAPABILITIES = CapabilitySet(
    capabilities={
        # ATP Worklist - Primary responsibility (inspect/override TRM decisions)
        Capability.VIEW_ATP_WORKLIST,
        Capability.MANAGE_ATP_WORKLIST,

        # Allocation Worklist (Layer 4) - View-only context for allocation state
        Capability.VIEW_ALLOCATION_WORKLIST,

        # S&OP Policy Envelope (Layer 1) - OTIF floors as performance expectations
        Capability.VIEW_SOP_POLICY,

        # Agent explanations - Ask Why on TRM order promise decisions
        Capability.VIEW_AGENT_EXPLANATIONS,
    }
)


# MPS/Execution Manager - Operational Level (Powell Framework)
#
# Responsibilities:
# - Work with AI agents (AATP, rebalancing, PO creation TRMs)
# - Manage MPS execution and material requirements
# - Handle day-to-day operational decisions
# - Cannot approve major decisions or train AI models
# - Site scope (e.g., specific regions/DCs)
MPS_MANAGER_CAPABILITIES = CapabilitySet(
    capabilities={
        # Powell Dashboard - Agent Decisions (MPS_MANAGER landing page)
        Capability.VIEW_AGENT_DECISIONS,

        # Overview - Operational dashboards
        Capability.VIEW_DASHBOARD,
        Capability.VIEW_ANALYTICS,
        Capability.VIEW_SC_ANALYTICS,

        # Insights - View only
        Capability.VIEW_INSIGHTS,

        # Risk Analysis - View alerts
        Capability.VIEW_RISK_ANALYSIS,
        Capability.VIEW_WATCHLISTS,
        Capability.VIEW_PREDICTIONS,

        # Supply Chain Design - View only
        Capability.VIEW_SC_CONFIGS,
        Capability.VIEW_INVENTORY_MODELS,
        Capability.VIEW_GROUP_CONFIGS,
        Capability.VIEW_NTIER_VISIBILITY,

        # Planning - Operational execution focus
        Capability.VIEW_DEMAND_PLANNING,
        Capability.VIEW_FORECASTING,
        Capability.VIEW_DEMAND_COLLABORATION,
        Capability.VIEW_FORECAST_EXCEPTIONS,
        Capability.VIEW_SUPPLY_PLANNING,
        Capability.VIEW_SUPPLY_PLAN,
        Capability.VIEW_CONSENSUS_DEMAND,
        Capability.VIEW_SALES_FORECAST,
        Capability.VIEW_SCENARIOS,
        Capability.VIEW_OPTIMIZATION,
        Capability.VIEW_SOURCING_ALLOCATION,
        Capability.VIEW_KPI_MONITORING,
        Capability.VIEW_PRODUCTION_PROCESS,
        Capability.VIEW_RESOURCE_CAPACITY,

        # MPS - Core operational responsibility
        Capability.VIEW_MPS,
        Capability.MANAGE_MPS,  # Manage MPS execution
        Capability.VIEW_LOT_SIZING,
        Capability.VIEW_CAPACITY_CHECK,
        Capability.VIEW_CAPACITY_PLANNING,
        Capability.VIEW_MRP,
        Capability.VIEW_INVENTORY_OPTIMIZATION,

        # Production and Orders - Full operational control
        Capability.VIEW_ORDER_PLANNING,
        Capability.MANAGE_ORDER_PLANNING,
        Capability.VIEW_PRODUCTION_ORDERS,
        Capability.MANAGE_PRODUCTION_ORDERS,
        Capability.RELEASE_PRODUCTION_ORDERS,
        Capability.VIEW_ORDER_MANAGEMENT,
        Capability.VIEW_SUPPLIERS,
        Capability.VIEW_SUPPLIER_MANAGEMENT,
        Capability.VIEW_VENDOR_LEAD_TIMES,
        Capability.VIEW_INVENTORY_PROJECTION,
        Capability.VIEW_FULFILLMENT_ORDERS,
        Capability.MANAGE_FULFILLMENT_ORDERS,
        Capability.VIEW_BACKORDERS,
        Capability.MANAGE_BACKORDERS,
        Capability.VIEW_SERVICE_ORDERS,

        # Material Visibility - Full operational access
        Capability.VIEW_SHIPMENT_TRACKING,
        Capability.MANAGE_SHIPMENTS,
        Capability.VIEW_INVENTORY_VISIBILITY,
        Capability.MANAGE_INVENTORY_VISIBILITY,

        # AI Models - View only (uses agents, doesn't configure them)
        Capability.USE_AI_ASSISTANT,
        Capability.VIEW_AI_AGENTS,
        Capability.VIEW_TRM_TRAINING,
        Capability.VIEW_GNN_TRAINING,
        Capability.VIEW_MODEL_SETUP,

        # Powell Framework - Work with TRM agents (core operational tool)
        Capability.VIEW_POWELL,
        Capability.VIEW_ATP_CTP,

        # Planning Cascade - Operational: owns L3-L5, views L1-L2
        Capability.VIEW_CASCADE_DASHBOARD,
        Capability.VIEW_SOP_POLICY,  # Views PE (no manage)
        Capability.VIEW_MRS_CANDIDATES,  # Views SupBP (no manage)
        Capability.VIEW_SUPPLY_WORKLIST,
        Capability.MANAGE_SUPPLY_WORKLIST,  # MPS_MANAGER works with Supply Agent
        Capability.VIEW_ALLOCATION_WORKLIST,
        Capability.MANAGE_ALLOCATION_WORKLIST,  # MPS_MANAGER works with Allocation Agent
        Capability.VIEW_EXECUTION_DASHBOARD,
        Capability.MANAGE_EXECUTION_DASHBOARD,  # MPS_MANAGER owns execution decisions

        # TRM Specialist Worklists - MPS_MANAGER oversees all TRMs
        Capability.VIEW_ATP_WORKLIST,
        Capability.MANAGE_ATP_WORKLIST,
        Capability.VIEW_REBALANCING_WORKLIST,
        Capability.MANAGE_REBALANCING_WORKLIST,
        Capability.VIEW_PO_WORKLIST,
        Capability.MANAGE_PO_WORKLIST,
        Capability.VIEW_ORDER_TRACKING_WORKLIST,
        Capability.MANAGE_ORDER_TRACKING_WORKLIST,

        # Collaboration Hub - View explanations, work with agents
        Capability.VIEW_COLLABORATION,
        Capability.MANAGE_COLLABORATION,
        Capability.VIEW_AGENT_EXPLANATIONS,

        # Recommendations - Execute within approved bounds
        Capability.VIEW_RECOMMENDATIONS,
        Capability.EXECUTE_RECOMMENDATIONS,
    }
)


# =============================================================================
# TRM Specialist Roles (Subordinate to MPS_MANAGER)
# =============================================================================
# Each TRM specialist is the human counterpart of one narrow TRM agent.
# They inspect agent decisions, override with reason capture, and their
# overrides feed back into RL training via trm_replay_buffer (is_expert=True).
#
# Hierarchy: SC_VP → SOP_DIRECTOR → MPS_MANAGER → TRM Specialists
# =============================================================================

# Shared base capabilities for all TRM specialists
_TRM_SPECIALIST_BASE = {
    Capability.VIEW_DASHBOARD,
    Capability.VIEW_ANALYTICS,
    Capability.VIEW_INSIGHTS,
    Capability.VIEW_RISK_ANALYSIS,
    Capability.VIEW_WATCHLISTS,

    # Execution visibility (read-only for context)
    Capability.VIEW_EXECUTION_DASHBOARD,
    Capability.VIEW_CASCADE_DASHBOARD,
    Capability.VIEW_POWELL,
    Capability.VIEW_ATP_CTP,
    Capability.VIEW_SC_CONFIGS,
    Capability.VIEW_INVENTORY_MODELS,
    Capability.VIEW_GROUP_CONFIGS,

    # Operational context (read-only)
    Capability.VIEW_ORDER_PLANNING,
    Capability.VIEW_SUPPLY_PLANNING,
    Capability.VIEW_SUPPLY_PLAN,
    Capability.VIEW_DEMAND_PLANNING,
    Capability.VIEW_FORECASTING,
    Capability.VIEW_MRP,
    Capability.VIEW_ORDER_MANAGEMENT,
    Capability.VIEW_INVENTORY_PROJECTION,
    Capability.VIEW_SHIPMENT_TRACKING,
    Capability.VIEW_INVENTORY_VISIBILITY,
    Capability.VIEW_FULFILLMENT_ORDERS,
    Capability.VIEW_PRODUCTION_ORDERS,
    Capability.VIEW_PRODUCTION_PROCESS,
    Capability.VIEW_SUPPLIERS,
    Capability.VIEW_SUPPLIER_MANAGEMENT,
    Capability.VIEW_BACKORDERS,
    Capability.VIEW_SERVICE_ORDERS,

    # Collaboration - work with agents
    Capability.USE_AI_ASSISTANT,
    Capability.VIEW_COLLABORATION,
    Capability.VIEW_AGENT_EXPLANATIONS,
    Capability.VIEW_AGENT_DECISIONS,

    # Recommendations
    Capability.VIEW_RECOMMENDATIONS,
    Capability.EXECUTE_RECOMMENDATIONS,
}

# ATP Analyst - Inspects and overrides order fulfillment decisions
#
# Responsibilities:
# - Review ATP fulfillment decisions (FULFILL/PARTIAL/DEFER/REJECT)
# - Override allocation tier consumption and promise dates
# - Monitor fill rate, promise accuracy, priority consumption patterns
# - Overrides train ATP TRM via RL (is_expert=True in replay buffer)
ATP_ANALYST_CAPABILITIES = CapabilitySet(
    capabilities=_TRM_SPECIALIST_BASE | {
        Capability.VIEW_ATP_WORKLIST,
        Capability.MANAGE_ATP_WORKLIST,
    }
)

# Rebalancing Analyst - Inspects and overrides inventory transfer decisions
#
# Responsibilities:
# - Review transfer recommendations (TRANSFER/HOLD/EXPEDITE)
# - Override transfer qty, timing, destination site
# - Monitor DOS improvement, transfer costs, network balance
# - Overrides train Rebalancing TRM via RL
REBALANCING_ANALYST_CAPABILITIES = CapabilitySet(
    capabilities=_TRM_SPECIALIST_BASE | {
        Capability.VIEW_REBALANCING_WORKLIST,
        Capability.MANAGE_REBALANCING_WORKLIST,
        Capability.MANAGE_SHIPMENTS,  # Manage transfer orders
    }
)

# PO Analyst - Inspects and overrides purchase order creation decisions
#
# Responsibilities:
# - Review PO recommendations (ORDER/DEFER/EXPEDITE/CANCEL)
# - Override order qty, supplier selection, expedite flags
# - Monitor order accuracy, lead time compliance, expedite rate
# - Overrides train PO Creation TRM via RL
PO_ANALYST_CAPABILITIES = CapabilitySet(
    capabilities=_TRM_SPECIALIST_BASE | {
        Capability.VIEW_PO_WORKLIST,
        Capability.MANAGE_PO_WORKLIST,
        Capability.MANAGE_ORDER_PLANNING,  # Create/modify purchase orders
    }
)

# Order Tracking Analyst - Inspects and overrides exception handling decisions
#
# Responsibilities:
# - Review exception detections (LATE_DELIVERY, QUANTITY_SHORTAGE, etc.)
# - Override recommended actions (ESCALATE, EXPEDITE, FIND_ALTERNATE, etc.)
# - Monitor exception resolution time, escalation rates
# - Overrides train Order Tracking TRM via RL
ORDER_TRACKING_ANALYST_CAPABILITIES = CapabilitySet(
    capabilities=_TRM_SPECIALIST_BASE | {
        Capability.VIEW_ORDER_TRACKING_WORKLIST,
        Capability.MANAGE_ORDER_TRACKING_WORKLIST,
        Capability.MANAGE_SHIPMENTS,  # Act on shipping exceptions
        Capability.MANAGE_BACKORDERS,  # Act on backorder exceptions
    }
)


def get_capabilities_for_user_type(user_type: str) -> CapabilitySet:
    """
    Get the default capability set for a user type or Powell-aligned role.

    Args:
        user_type: User type enum value (SYSTEM_ADMIN, GROUP_ADMIN, USER)
                   or Powell role (SC_VP, SOP_DIRECTOR, MPS_MANAGER)

    Returns:
        CapabilitySet for the user type
    """
    user_type_upper = user_type.upper()

    if user_type_upper == "SYSTEM_ADMIN":
        return SYSTEM_ADMIN_CAPABILITIES
    elif user_type_upper == "GROUP_ADMIN":
        return GROUP_ADMIN_CAPABILITIES
    elif user_type_upper == "USER":
        return USER_CAPABILITIES
    # Powell Framework aligned roles
    elif user_type_upper == "SC_VP":
        return SC_VP_CAPABILITIES
    elif user_type_upper == "SOP_DIRECTOR":
        return SOP_DIRECTOR_CAPABILITIES
    elif user_type_upper == "ALLOCATION_MANAGER":
        return ALLOCATION_MANAGER_CAPABILITIES
    elif user_type_upper == "ORDER_PROMISE_MANAGER":
        return ORDER_PROMISE_MANAGER_CAPABILITIES
    elif user_type_upper == "MPS_MANAGER":
        return MPS_MANAGER_CAPABILITIES
    # TRM Specialist roles (subordinate to MPS_MANAGER)
    elif user_type_upper == "ATP_ANALYST":
        return ATP_ANALYST_CAPABILITIES
    elif user_type_upper == "REBALANCING_ANALYST":
        return REBALANCING_ANALYST_CAPABILITIES
    elif user_type_upper == "PO_ANALYST":
        return PO_ANALYST_CAPABILITIES
    elif user_type_upper == "ORDER_TRACKING_ANALYST":
        return ORDER_TRACKING_ANALYST_CAPABILITIES
    else:
        # Default to user capabilities if unknown
        return USER_CAPABILITIES


# Map Powell roles to their descriptions for documentation
POWELL_ROLE_DESCRIPTIONS = {
    "SC_VP": {
        "name": "VP of Supply Chain",
        "powell_level": "Strategic/CFA",
        "description": "Sets policy parameters θ, configures AI training, approves major decisions",
        "scope": "Full access (all sites, all products)",
    },
    "SOP_DIRECTOR": {
        "name": "S&OP Director",
        "powell_level": "Tactical/S&OP",
        "description": "Runs S&OP processes, accepts/overrides AI recommendations within policy bounds",
        "scope": "Product category scope (specific product families)",
    },
    "ALLOCATION_MANAGER": {
        "name": "Allocation Manager",
        "powell_level": "Tactical/Allocation",
        "description": "Inspects and overrides tGNN-generated allocations by priority class and time bucket",
        "scope": "Allocation Worklist only (priority × product × location)",
    },
    "ORDER_PROMISE_MANAGER": {
        "name": "Order Promise Manager",
        "powell_level": "Execution/ATP",
        "description": "Inspects and overrides TRM order promising and ATP consumption decisions",
        "scope": "ATP Worklist only (allocation context + OTIF performance expectations)",
    },
    "MPS_MANAGER": {
        "name": "MPS/Execution Manager",
        "powell_level": "Operational/tGNN+TRM",
        "description": "Works with AI agents for execution, manages day-to-day operations",
        "scope": "Site scope (specific regions/DCs)",
    },
    "ATP_ANALYST": {
        "name": "ATP Analyst",
        "powell_level": "Execution/TRM",
        "description": "Reviews and overrides ATP fulfillment decisions; overrides train ATP TRM via RL",
        "scope": "Order-level (assigned sites)",
        "trm_type": "atp_executor",
    },
    "REBALANCING_ANALYST": {
        "name": "Rebalancing Analyst",
        "powell_level": "Execution/TRM",
        "description": "Reviews and overrides inventory transfer decisions; overrides train Rebalancing TRM via RL",
        "scope": "Cross-site transfers (assigned sites)",
        "trm_type": "rebalancing",
    },
    "PO_ANALYST": {
        "name": "PO Analyst",
        "powell_level": "Execution/TRM",
        "description": "Reviews and overrides purchase order decisions; overrides train PO Creation TRM via RL",
        "scope": "Supplier orders (assigned sites)",
        "trm_type": "po_creation",
    },
    "ORDER_TRACKING_ANALYST": {
        "name": "Order Tracking Analyst",
        "powell_level": "Execution/TRM",
        "description": "Reviews and overrides exception handling decisions; overrides train Order Tracking TRM via RL",
        "scope": "Order exceptions (all order types)",
        "trm_type": "order_tracking",
    },
}


def capability_to_permission_name(capability: Capability) -> str:
    """
    Convert a capability to RBAC permission name format.

    Example: Capability.VIEW_GAMES -> "games.view"
    """
    name = capability.value
    parts = name.split('_', 1)

    if len(parts) == 2:
        action, resource = parts
        return f"{resource.lower()}.{action.lower()}"

    return name.lower()


def get_navigation_capabilities() -> dict:
    """
    Map navigation categories and items to required capabilities.

    Returns:
        Dictionary mapping navigation paths to required capabilities
    """
    return {
        # Overview category
        "overview": {
            "category_capability": Capability.VIEW_DASHBOARD,
            "items": {
                "/dashboard": [Capability.VIEW_DASHBOARD],
                "/analytics": [Capability.VIEW_ANALYTICS],
            }
        },

        # Gamification category
        "gamification": {
            "category_capability": Capability.VIEW_GAMES,
            "items": {
                "/games": [Capability.VIEW_GAMES],
                "/games/new": [Capability.CREATE_GAME],
            }
        },

        # Supply Chain Design category
        "supply-chain": {
            "category_capability": Capability.VIEW_SC_CONFIGS,
            "items": {
                "/system/supply-chain-configs": [Capability.VIEW_SC_CONFIGS],
                "/admin/model-setup": [Capability.VIEW_MODEL_SETUP],
                "/admin/group/supply-chain-configs": [Capability.VIEW_GROUP_CONFIGS],
            }
        },

        # Planning & Optimization category
        "planning": {
            "category_capability": Capability.VIEW_DEMAND_PLANNING,
            "items": {
                "/planning/orders": [Capability.VIEW_ORDER_PLANNING],
                "/planning/demand": [Capability.VIEW_DEMAND_PLANNING],
                "/planning/supply": [Capability.VIEW_SUPPLY_PLANNING],
                "/planning/mps": [Capability.VIEW_MPS],
                "/planning/production-orders": [Capability.VIEW_PRODUCTION_ORDERS],
                "/planning/capacity": [Capability.VIEW_CAPACITY_PLANNING],
                "/planning/suppliers": [Capability.VIEW_SUPPLIERS],
                "/planning/inventory-projection": [Capability.VIEW_INVENTORY_PROJECTION],
                "/planning/sales-forecast": [Capability.VIEW_SALES_FORECAST],
                "/planning/consensus-demand": [Capability.VIEW_CONSENSUS_DEMAND],
                "/planning/scenarios": [Capability.VIEW_SCENARIOS],
                "/planning/monte-carlo": [Capability.VIEW_SCENARIOS, Capability.RUN_MONTE_CARLO],
                "/planning/fulfillment-orders": [Capability.VIEW_FULFILLMENT_ORDERS],
                "/planning/backorders": [Capability.VIEW_BACKORDERS],
                "/planning/optimization": [Capability.VIEW_OPTIMIZATION],
            }
        },

        # Planning Cascade (Modular Powell Layers)
        "planning-cascade": {
            "category_capability": Capability.VIEW_CASCADE_DASHBOARD,
            "items": {
                "/planning/cascade": [Capability.VIEW_CASCADE_DASHBOARD],
                "/planning/sop-policy": [Capability.VIEW_SOP_POLICY],
                "/planning/mrs-candidates": [Capability.VIEW_MRS_CANDIDATES],
                "/planning/supply-worklist": [Capability.VIEW_SUPPLY_WORKLIST],
                "/planning/allocation-worklist": [Capability.VIEW_ALLOCATION_WORKLIST],
                "/planning/execution": [Capability.VIEW_EXECUTION_DASHBOARD],
            }
        },

        # TRM Specialist Worklists
        "trm-worklists": {
            "category_capability": Capability.VIEW_ATP_WORKLIST,
            "items": {
                "/planning/execution/atp-worklist": [Capability.VIEW_ATP_WORKLIST],
                "/planning/execution/rebalancing-worklist": [Capability.VIEW_REBALANCING_WORKLIST],
                "/planning/execution/po-worklist": [Capability.VIEW_PO_WORKLIST],
                "/planning/execution/order-tracking-worklist": [Capability.VIEW_ORDER_TRACKING_WORKLIST],
            }
        },

        # AI & ML Models category
        "ai-ml": {
            "category_capability": Capability.VIEW_TRM_TRAINING,
            "items": {
                "/admin/trm": [Capability.VIEW_TRM_TRAINING],
                "/admin/gnn": [Capability.VIEW_GNN_TRAINING],
                "/admin/model-setup": [Capability.VIEW_MODEL_SETUP],
                "/admin/powell": [Capability.VIEW_POWELL],
                "/planning/atp-ctp": [Capability.VIEW_ATP_CTP],
            }
        },

        # Collaboration category
        "collaboration": {
            "category_capability": Capability.VIEW_GROUPS,
            "items": {
                "/admin/groups": [Capability.VIEW_GROUPS],
                "/players": [Capability.VIEW_PLAYERS],
                "/admin/users": [Capability.VIEW_USERS],
            }
        },

        # Administration category
        "admin": {
            "category_capability": Capability.VIEW_ADMIN_DASHBOARD,
            "items": {
                "/admin": [Capability.VIEW_ADMIN_DASHBOARD],
                "/admin/monitoring": [Capability.VIEW_SYSTEM_MONITORING],
                "/system-config": [Capability.MANAGE_SYSTEM_CONFIG],
                "/admin/governance": [Capability.VIEW_GOVERNANCE],
            }
        },
    }


def require_capabilities(capabilities: List[str]):
    """
    Decorator to require specific capabilities for an endpoint.

    Usage:
        @router.get("/protected")
        @require_capabilities(["view_dashboard", "manage_users"])
        async def protected_endpoint(current_user: User = Depends(get_current_user)):
            ...

    Args:
        capabilities: List of capability names required to access the endpoint

    Returns:
        Decorated function that checks user capabilities

    Raises:
        HTTPException: 403 if user doesn't have required capabilities
    """
    def _check_capabilities(current_user, db):
        """Shared capability check logic."""
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )

        # System admins have all capabilities
        user_type = getattr(current_user, 'user_type', None)
        user_type_str = user_type.value if hasattr(user_type, 'value') else str(user_type) if user_type else ''
        if getattr(current_user, 'is_superuser', False) or user_type_str == 'SYSTEM_ADMIN':
            return  # Allowed

        # Load capabilities from capability service (uses RBAC + user_type fallback)
        user_capabilities = getattr(current_user, '_cached_capabilities', None)
        if user_capabilities is None:
            try:
                from app.services.capability_service import get_user_capabilities_list
                if db is not None:
                    user_capabilities = get_user_capabilities_list(current_user, db)
                else:
                    cap_set = get_capabilities_for_user_type(user_type_str)
                    user_capabilities = [cap.value for cap in cap_set.capabilities]
            except Exception:
                cap_set = get_capabilities_for_user_type(user_type_str)
                user_capabilities = [cap.value for cap in cap_set.capabilities]
            current_user._cached_capabilities = user_capabilities

        user_caps_set = set(user_capabilities)
        required_caps_set = set(capabilities)

        if not required_caps_set.issubset(user_caps_set):
            missing_caps = required_caps_set - user_caps_set
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required capabilities: {', '.join(missing_caps)}"
            )

    def decorator(func: Callable):
        import asyncio
        import inspect

        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                current_user = kwargs.get('current_user')
                if not current_user:
                    for arg in args:
                        if hasattr(arg, 'user_type'):
                            current_user = arg
                            break
                _check_capabilities(current_user, kwargs.get('db'))
                return await func(*args, **kwargs)
            return wrapper
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                current_user = kwargs.get('current_user')
                if not current_user:
                    for arg in args:
                        if hasattr(arg, 'user_type'):
                            current_user = arg
                            break
                _check_capabilities(current_user, kwargs.get('db'))
                return func(*args, **kwargs)
            return wrapper
    return decorator
