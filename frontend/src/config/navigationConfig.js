/**
 * Navigation Configuration
 *
 * Maps capabilities to navigation menu items.
 * Each nav item requires specific capability to be enabled.
 *
 * Structure based on industry best practices (SAP IBP, Kinaxis, Oracle SCM):
 * 1. Home/Dashboard - Role-adaptive landing
 * 2. Insights & Analytics - Consolidated analytics and recommendations
 * 3. Planning - Strategic/Tactical/Operational hierarchy
 * 4. Execution - Orders, Tracking, Procurement
 * 5. Simulation - What-if scenarios and simulation
 * 6. AI & Agents - AI assistant and agent training
 * 7. Administration - User and system management
 *
 * Terminology update (Feb 2026):
 * - Gamification -> Simulation (section name)
 * - Games -> Scenarios (feature name)
 * - ScenarioUsers -> Users/ScenarioUsers (UI display)
 * - Rounds -> Periods (time periods)
 */

import {
  LayoutDashboard as DashboardIcon,
  Gamepad2 as GamesIcon,
  Users as PeopleIcon,
  BarChart3 as AnalyticsIcon,
  TrendingUp as ForecastIcon,
  ClipboardCheck as AssessmentIcon,
  Package as InventoryIcon,
  Calculator as CalculateIcon,
  Calendar as CalendarIcon,
  Factory as FactoryIcon,
  Truck as ShippingIcon,
  Eye as VisibilityIcon,
  Bot as AIIcon,
  Brain as BrainIcon,
  Shield as AdminIcon,
  Network as NetworkIcon,
  ShoppingCart as OrderIcon,
  Store as StoreIcon,
  BarChart2 as StatsIcon,
  AlertTriangle as RiskIcon,
  ArrowLeftRight as CompareIcon,
  Box as ViewIcon,
  Lightbulb as RecommendIcon,
  MessageSquare as CollaborationIcon,
  ClipboardList as ProjectIcon,
  Wrench as MaintenanceIcon,
  RefreshCw as TurnaroundIcon,
  Settings2 as ServiceIcon,
  SlidersHorizontal as TuneIcon,
  CircuitBoard as HubIcon,
  Settings as SettingsIcon,
  FlaskConical as ScienceIcon,
  CheckSquare as ApprovalIcon,
  GitBranch as WorkflowIcon,
  Target as TargetIcon,
  Layers as LayersIcon,
  Database as DatabaseIcon,
  Wand2 as WandIcon,
  Activity as ActivityIcon,
  Crosshair as CrosshairIcon,
  GitMerge as CascadeIcon,
  FileInput as InputIcon,
  ListChecks as WorklistIcon,
  Cpu as ExecutionIcon,
  BookOpen as BookOpenIcon,
  Award as AwardIcon,
  ThumbsUp as ThumbsUpIcon,
  Trophy as TrophyIcon,
} from 'lucide-react';

/**
 * Navigation structure with capability-based access control
 *
 * Organized by planning horizon and function per SAP IBP / Kinaxis patterns:
 * - Strategic (18-36 months): S&OP, Network Design
 * - Tactical (3-12 months): MPS, Inventory Optimization
 * - Operational (0-3 months): Demand, Supply, MRP
 */
export const NAVIGATION_CONFIG = [
  // ============================================================================
  // HOME / DASHBOARD
  // ============================================================================
  {
    section: 'Home',
    items: [
      {
        label: 'Dashboard',
        path: '/dashboard',
        icon: DashboardIcon,
        requiredCapability: null, // Always visible
        description: 'Role-adaptive home with KPIs and alerts',
      },
    ],
  },

  // ============================================================================
  // INSIGHTS & ANALYTICS (Consolidated)
  // ============================================================================
  {
    section: 'Insights & Analytics',
    divider: true,
    items: [
      // Worklists by Powell level (Strategic → Tactical → Operational)
      {
        label: 'Executive Dashboard',
        path: '/executive-dashboard',
        icon: AnalyticsIcon,
        requiredCapability: 'view_executive_dashboard',
        description: 'Strategic KPIs, performance summary, ROI',
      },
      {
        label: 'Strategy Briefing',
        path: '/strategy-briefing',
        icon: BookOpenIcon,
        requiredCapability: 'view_executive_dashboard',
        description: 'AI-generated executive strategy briefings',
      },
      {
        label: 'S&OP Worklist',
        path: '/sop-worklist',
        icon: RecommendIcon,
        requiredCapability: 'view_sop_worklist',
        description: 'Tactical worklist with agent recommendations',
      },
      {
        label: 'MPS Worklist',
        path: '/insights/actions',
        icon: RecommendIcon,
        requiredCapability: 'view_recommendations',
        description: 'Operational inventory risks and recommendations',
      },
      {
        label: 'Agent Performance',
        path: '/agent-performance',
        icon: ActivityIcon,
        requiredCapability: 'view_executive_dashboard',
        description: 'Performance breakdown by category',
      },
      // Analytics
      {
        label: 'Scenario Comparison',
        path: '/sc-analytics',
        icon: CompareIcon,
        requiredCapability: 'view_analytics',
        description: 'Balanced scorecard comparison',
      },
      {
        label: 'KPI Monitoring',
        path: '/planning/kpi-monitoring',
        icon: StatsIcon,
        requiredCapability: 'view_kpi_monitoring',
      },
      {
        label: 'Hierarchical Metrics',
        path: '/planning/metrics',
        icon: TargetIcon,
        requiredCapability: 'view_kpi_monitoring',
        description: 'Gartner hierarchy drill-down by Geography/Product/Time',
      },
      {
        label: 'Risk Analysis',
        path: '/analytics/risk',
        icon: RiskIcon,
        requiredCapability: 'view_risk_analysis',
      },
      {
        label: 'Uncertainty Quantification',
        path: '/analytics/uncertainty',
        icon: ScienceIcon,
        requiredCapability: 'view_uncertainty_quantification',
        description: 'Stochastic vs deterministic analysis',
      },
      {
        label: 'Exception Detection',
        path: '/planning/execution/order-tracking-worklist',
        icon: RiskIcon,
        requiredCapability: 'view_order_tracking_worklist',
        description: 'Order tracking exceptions and anomaly alerts',
      },
    ],
  },

  // ============================================================================
  // PLANNING - Strategic / Tactical / Operational
  // ============================================================================
  {
    section: 'Planning',
    divider: true,
    items: [
      // --- STRATEGIC PLANNING (18-36 month horizon) ---
      {
        label: '— STRATEGIC —',
        path: null,
        icon: null,
        requiredCapability: null,
        isSectionHeader: true,
      },
      {
        label: 'S&OP',
        path: '/planning/sop',
        icon: CalendarIcon,
        requiredCapability: 'view_sop',
        description: 'Sales & Operations Planning - cross-functional alignment',
      },
      {
        label: 'Network Design',
        path: '/planning/network-design',
        icon: NetworkIcon,
        requiredCapability: 'view_network_design',
        comingSoon: true,
      },

      // --- TACTICAL PLANNING (3-12 month horizon) ---
      {
        label: '— TACTICAL —',
        path: null,
        icon: null,
        requiredCapability: null,
        isSectionHeader: true,
      },
      {
        label: 'Master Production Schedule',
        path: '/planning/mps',
        icon: CalendarIcon,
        requiredCapability: 'view_mps',
      },
      {
        label: 'Lot Sizing',
        path: '/planning/mps/lot-sizing',
        icon: CalculateIcon,
        requiredCapability: 'view_lot_sizing',
      },
      {
        label: 'Capacity Check',
        path: '/planning/mps/capacity-check',
        icon: AssessmentIcon,
        requiredCapability: 'view_capacity_check',
      },
      {
        label: 'Inventory Optimization',
        path: '/planning/inventory-optimization',
        icon: TargetIcon,
        requiredCapability: 'view_inventory_optimization',
        description: 'Safety stock and reorder point optimization',
      },

      // --- OPERATIONAL PLANNING (0-3 month horizon) ---
      {
        label: '— OPERATIONAL —',
        path: null,
        icon: null,
        requiredCapability: null,
        isSectionHeader: true,
      },
      {
        label: 'Forecasting',
        path: '/planning/forecasting',
        icon: AnalyticsIcon,
        requiredCapability: 'view_forecasting',
        description: 'ML-based statistical forecast generation at agreed cadence',
      },
      {
        label: 'Demand Planning',
        path: '/planning/demand',
        icon: ForecastIcon,
        requiredCapability: 'view_demand_planning',
      },
      {
        label: 'Forecast Editor',
        path: '/planning/demand/edit',
        icon: ForecastIcon,
        requiredCapability: 'manage_demand_planning',
      },
      {
        label: 'Demand Collaboration',
        path: '/planning/demand-collaboration',
        icon: CollaborationIcon,
        requiredCapability: 'view_demand_collaboration',
      },
      {
        label: 'Forecast Exceptions',
        path: '/planning/forecast-exceptions',
        icon: RiskIcon,
        requiredCapability: 'view_forecast_exceptions',
      },
      {
        label: 'Supply Planning',
        path: '/planning/supply-plan',
        icon: ViewIcon,
        requiredCapability: 'view_supply_plan',
      },
      {
        label: 'Production Processes',
        path: '/planning/production-processes',
        icon: FactoryIcon,
        requiredCapability: 'view_production_process',
      },
      {
        label: 'Inventory Projection',
        path: '/planning/inventory-projection',
        icon: InventoryIcon,
        requiredCapability: 'view_inventory_projection',
        description: 'Day-to-day inventory levels and ATP/CTP',
      },
      {
        label: 'Sourcing & Allocation',
        path: '/planning/sourcing',
        icon: StoreIcon,
        requiredCapability: 'view_sourcing_allocation',
      },
      {
        label: 'AATP Allocations',
        path: '/execution/atp-ctp',
        icon: CrosshairIcon,
        requiredCapability: 'view_atp_ctp',
        description: 'Priority-based Available-to-Promise allocation',
      },
      {
        label: 'Capacity Planning',
        path: '/planning/capacity',
        icon: AssessmentIcon,
        requiredCapability: 'view_capacity_planning',
      },
      {
        label: 'Resource Capacity',
        path: '/planning/resource-capacity',
        icon: AssessmentIcon,
        requiredCapability: 'view_resource_capacity',
      },
      {
        label: 'Collaboration Hub',
        path: '/planning/collaboration',
        icon: CollaborationIcon,
        requiredCapability: 'view_collaboration',
      },
    ],
  },

  // ============================================================================
  // PLANNING CASCADE — Modular Powell Layers (Independently Sellable)
  // ============================================================================
  {
    section: 'Planning Cascade',
    divider: true,
    items: [
      {
        label: 'Cascade Dashboard',
        path: '/planning/cascade',
        icon: CascadeIcon,
        requiredCapability: 'view_cascade_dashboard',
        description: 'Orchestration overview across all planning layers',
      },
      // --- STRATEGIC LAYERS ---
      {
        label: '— STRATEGIC —',
        path: null,
        icon: null,
        requiredCapability: null,
        isSectionHeader: true,
      },
      {
        label: 'S&OP Policy Envelope',
        path: '/planning/sop-policy',
        icon: TargetIcon,
        requiredCapability: 'view_sop_policy',
        description: 'Layer 1: Policy parameters θ — safety stock, OTIF floors, allocation reserves',
      },
      {
        label: 'Supply Baseline Pack',
        path: '/planning/mps-candidates',
        icon: CompareIcon,
        requiredCapability: 'view_mps_candidates',
        description: 'Layer 2: Candidate supply plans with cost vs service tradeoff',
      },
      // --- OPERATIONAL LAYERS ---
      {
        label: '— OPERATIONAL —',
        path: null,
        icon: null,
        requiredCapability: null,
        isSectionHeader: true,
      },
      {
        label: 'Supply Worklist',
        path: '/planning/supply-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_supply_worklist',
        description: 'Layer 3: Supply Commits — PO/TO/MO recommendations',
      },
      {
        label: 'Allocation Worklist',
        path: '/planning/allocation-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_allocation_worklist',
        description: 'Layer 4: Allocation Commits — priority × product × location',
      },
      {
        label: 'Execution',
        path: '/planning/execution',
        icon: ExecutionIcon,
        requiredCapability: 'view_execution_dashboard',
        description: 'Layer 5: MRP, Inventory Buffer, AATP, TRM agents, feed-back signals',
      },
      // --- TRM SPECIALIST WORKLISTS ---
      {
        label: '— TRM WORKLISTS —',
        path: null,
        icon: null,
        requiredCapability: null,
        isSectionHeader: true,
      },
      {
        label: 'ATP Worklist',
        path: '/planning/execution/atp-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_atp_worklist',
        description: 'ATP fulfillment decisions — accept/override with reason capture',
      },
      {
        label: 'Rebalancing Worklist',
        path: '/planning/execution/rebalancing-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_rebalancing_worklist',
        description: 'Inventory transfer decisions — accept/override with reason capture',
      },
      {
        label: 'PO Worklist',
        path: '/planning/execution/po-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_po_worklist',
        description: 'Purchase order decisions — accept/override with reason capture',
      },
      {
        label: 'Order Tracking Worklist',
        path: '/planning/execution/order-tracking-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_order_tracking_worklist',
        description: 'Exception handling decisions — accept/override with reason capture',
      },
    ],
  },

  // ============================================================================
  // EXECUTION - Orders, Tracking, Procurement
  // ============================================================================
  {
    section: 'Execution',
    divider: true,
    items: [
      // --- FULFILLMENT ---
      {
        label: '— FULFILLMENT —',
        path: null,
        icon: null,
        requiredCapability: null,
        isSectionHeader: true,
      },
      {
        label: 'MRP',
        path: '/execution/mrp',
        icon: FactoryIcon,
        requiredCapability: 'view_mrp',
        description: 'Material Requirements Planning — component requirements from MPS',
      },
      {
        label: 'Order Promising (ATP/CTP)',
        path: '/execution/atp-ctp',
        icon: StatsIcon,
        requiredCapability: 'view_atp_ctp',
        description: 'Available-to-Promise and Capable-to-Promise',
      },
      {
        label: 'PO Creation',
        path: '/execution/po-creation',
        icon: OrderIcon,
        requiredCapability: 'view_po_worklist',
        description: 'Automated purchase order generation and timing',
      },
      {
        label: 'Inventory Rebalancing',
        path: '/execution/inventory-rebalancing',
        icon: CompareIcon,
        requiredCapability: 'view_rebalancing_worklist',
        description: 'Cross-location inventory transfer decisions',
      },

      // --- ORDERS ---
      {
        label: '— ORDERS —',
        path: null,
        icon: null,
        requiredCapability: null,
        isSectionHeader: true,
      },
      {
        label: 'Purchase Orders',
        path: '/planning/purchase-orders',
        icon: OrderIcon,
        requiredCapability: 'view_order_management',
      },
      {
        label: 'Production Orders',
        path: '/production/orders',
        icon: FactoryIcon,
        requiredCapability: 'view_order_management',
      },
      {
        label: 'Transfer Orders',
        path: '/planning/transfer-orders',
        icon: ShippingIcon,
        requiredCapability: 'view_order_management',
      },
      {
        label: 'Order Management',
        path: '/planning/order-management',
        icon: TuneIcon,
        requiredCapability: 'view_order_management',
        description: 'Split, consolidate, and optimize orders',
      },
      {
        label: 'Project Orders',
        path: '/planning/project-orders',
        icon: ProjectIcon,
        requiredCapability: 'view_project_orders',
      },
      {
        label: 'Maintenance Orders',
        path: '/planning/maintenance-orders',
        icon: MaintenanceIcon,
        requiredCapability: 'view_maintenance_orders',
      },
      {
        label: 'Turnaround Orders',
        path: '/planning/turnaround-orders',
        icon: TurnaroundIcon,
        requiredCapability: 'view_turnaround_orders',
      },
      {
        label: 'Service Orders',
        path: '/execution/service-orders',
        icon: ServiceIcon,
        requiredCapability: 'view_service_orders',
      },

      // --- TRACKING & VISIBILITY ---
      {
        label: '— VISIBILITY —',
        path: null,
        icon: null,
        requiredCapability: null,
        isSectionHeader: true,
      },
      {
        label: 'Shipment Tracking',
        path: '/visibility/shipments',
        icon: ShippingIcon,
        requiredCapability: 'view_shipment_tracking',
      },
      {
        label: 'N-Tier Visibility',
        path: '/visibility/ntier',
        icon: VisibilityIcon,
        requiredCapability: 'view_ntier_visibility',
      },
      {
        label: 'Inventory Visibility',
        path: '/visibility/inventory',
        icon: InventoryIcon,
        requiredCapability: 'view_inventory_visibility',
      },
      {
        label: 'Order Tracking',
        path: '/planning/execution/order-tracking-worklist',
        icon: ShippingIcon,
        requiredCapability: 'view_order_tracking_worklist',
        description: 'Exception detection and recommended actions',
      },

      // --- PROCUREMENT ---
      {
        label: '— PROCUREMENT —',
        path: null,
        icon: null,
        requiredCapability: null,
        isSectionHeader: true,
      },
      {
        label: 'Supplier Management',
        path: '/planning/suppliers',
        icon: StoreIcon,
        requiredCapability: 'view_supplier_management',
      },
      {
        label: 'Vendor Lead Times',
        path: '/planning/vendor-lead-times',
        icon: StoreIcon,
        requiredCapability: 'view_vendor_lead_times',
      },
      {
        label: 'Invoices & 3-Way Match',
        path: '/planning/invoices',
        icon: OrderIcon,
        requiredCapability: 'view_order_management',
      },
    ],
  },

  // ============================================================================
  // SCENARIOS (What-If Planning) - Production Mode
  // ============================================================================
  {
    section: 'Scenarios',
    divider: true,
    productionOnly: true,  // Only show in Production mode
    items: [
      {
        label: 'Scenario Browser',
        path: '/scenarios',
        icon: GamesIcon,
        requiredCapability: 'view_games',
        description: 'Browse and manage scenarios',
      },
      {
        label: 'Create Scenario',
        path: '/scenarios/new',
        icon: GamesIcon,
        requiredCapability: 'create_game',
        description: 'Create new what-if scenario',
      },
      {
        label: 'Compare Scenarios',
        path: '/scenarios/compare',
        icon: CompareIcon,
        requiredCapability: 'view_scenario_comparison',
        description: 'Side-by-side scenario analysis',
      },
    ],
  },

  // ============================================================================
  // AI & AGENTS
  // ============================================================================
  {
    section: 'AI & Agents',
    divider: true,
    items: [
      {
        label: 'AI Assistant',
        path: '/ai-assistant',
        icon: AIIcon,
        requiredCapability: 'view_ai_agents',
        description: 'Conversational AI for planning queries',
      },
      {
        label: 'Decision Cascade',
        path: '/admin/powell',
        icon: LayersIcon,
        requiredCapability: 'view_powell',
        description: 'SDAM framework — State → Policy → Decision → Outcome',
      },
      {
        label: 'S&OP Agent',
        path: '/admin/graphsage',
        icon: BrainIcon,
        requiredCapability: 'view_gnn_training',
        description: 'S&OP GraphSAGE — network structure and risk scoring',
      },
      {
        label: 'Operational Agent',
        path: '/admin/gnn',
        icon: BrainIcon,
        requiredCapability: 'view_gnn_training',
        description: 'Execution tGNN — priority allocations and context',
      },
      {
        label: 'Execution Agents',
        path: '/admin/trm',
        icon: BrainIcon,
        requiredCapability: 'view_trm_training',
        description: 'Tiny Recursive Model — narrow execution agents',
      },
      {
        label: 'Claude Skills',
        path: '/admin/skills',
        icon: ActivityIcon,
        requiredCapability: 'view_trm_training',
        description: 'Skills monitoring — escalation rates, RAG memory, outcomes',
      },
      {
        label: 'Reinforcement Learning',
        path: '/admin/rl',
        icon: BrainIcon,
        requiredCapability: 'view_rl_training',
        description: 'Reinforcement Learning — VFA fine-tuning for TRMs',
      },
      {
        label: 'Agent Benchmark',
        path: '/admin/agent-benchmark',
        icon: AwardIcon,
        requiredCapability: 'view_ai_agents',
        description: 'Compare agent strategies — cost, service, efficiency',
      },
      {
        label: 'RLHF Feedback',
        path: '/admin/rlhf',
        icon: ThumbsUpIcon,
        requiredCapability: 'view_rl_training',
        description: 'Human feedback collection — override patterns and training data',
      },
      {
        label: 'Performance Leaderboard',
        path: '/admin/leaderboard',
        icon: TrophyIcon,
        requiredCapability: 'view_ai_agents',
        description: 'Participant and agent performance rankings',
      },
      {
        label: 'Agent Management',
        path: '/ai/agents',
        icon: AIIcon,
        requiredCapability: 'manage_ai_agents',
        comingSoon: true,
      },
    ],
  },

  // ============================================================================
  // DEPLOYMENT (Demo System Builder)
  // ============================================================================
  {
    section: 'Deployment',
    divider: true,
    items: [
      {
        label: 'Demo System Builder',
        path: '/deployment/builder',
        icon: WandIcon,
        requiredCapability: 'manage_deployment',
        description: 'End-to-end pipeline: simulate, train, export SAP CSVs',
      },
      {
        label: 'Pipeline Status',
        path: '/deployment/pipelines',
        icon: ActivityIcon,
        requiredCapability: 'manage_deployment',
        description: 'Monitor deployment pipeline runs and step progress',
      },
      {
        label: 'SAP CSV Exports',
        path: '/deployment/csvs',
        icon: DatabaseIcon,
        requiredCapability: 'manage_deployment',
        description: 'Download generated SAP-format CSV files',
      },
    ],
  },

  // ============================================================================
  // ADMINISTRATION (Customer Admin)
  // ============================================================================
  {
    section: 'Administration',
    divider: true,
    adminOnly: true,
    items: [
      {
        label: 'User Management',
        path: '/admin/users',
        icon: PeopleIcon,
        requiredCapability: 'view_users',
        description: 'Manage users in your organization',
      },
      {
        label: 'Role Management',
        path: '/admin/role-management',
        icon: AdminIcon,
        requiredCapability: 'manage_roles',
        description: 'Configure roles and permissions',
      },
      {
        label: 'Supply Chain Configs',
        path: '/admin/tenant/supply-chain-configs',
        icon: NetworkIcon,
        requiredCapability: 'view_sc_configs',
      },
      {
        label: 'Approval Templates',
        path: '/admin/approval-templates',
        icon: ApprovalIcon,
        requiredCapability: 'manage_approval_templates',
      },
      {
        label: 'Exception Workflows',
        path: '/admin/exception-workflows',
        icon: WorkflowIcon,
        requiredCapability: 'manage_approval_templates',
      },
      {
        label: 'SAP Data Management',
        path: '/admin/sap-data',
        icon: DatabaseIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'SAP connections, field mapping, and data ingestion',
      },
      {
        label: 'Knowledge Base',
        path: '/admin/knowledge-base',
        icon: BookOpenIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Upload documents for AI agent context (RAG)',
      },
    ],
  },



];

/**
 * System Admin specific navigation (shown instead of regular nav)
 */
export const SYSTEM_ADMIN_NAVIGATION = [
  {
    section: 'System Administration',
    items: [
      {
        label: 'Admin Dashboard',
        path: '/admin',
        icon: DashboardIcon,
      },
      {
        label: 'Organizations',
        path: '/admin/tenants',
        icon: AdminIcon,
        description: 'Manage all organizations (System Admin only)',
      },
      {
        label: 'System Users',
        path: '/system/users',
        icon: PeopleIcon,
        description: 'Manage all users across groups',
      },
      {
        label: 'Supply Chain Configs',
        path: '/system/supply-chain-configs',
        icon: NetworkIcon,
        description: 'System-wide SC configurations',
      },
      {
        label: 'Decision Cascade',
        path: '/admin/powell',
        icon: LayersIcon,
        description: 'SDAM framework — State → Policy → Decision → Outcome',
      },
      {
        label: 'S&OP Agent',
        path: '/admin/graphsage',
        icon: BrainIcon,
      },
      {
        label: 'Operational Agent',
        path: '/admin/gnn',
        icon: BrainIcon,
      },
      {
        label: 'Execution Agents',
        path: '/admin/trm',
        icon: BrainIcon,
      },
      {
        label: 'Reinforcement Learning',
        path: '/admin/rl',
        icon: BrainIcon,
      },
      {
        label: 'System Monitoring',
        path: '/admin/monitoring',
        icon: AssessmentIcon,
      },
      {
        label: 'Synthetic Data Wizard',
        path: '/admin/synthetic-data',
        icon: WandIcon,
        description: 'AI-guided setup for test environments',
      },
      {
        label: 'Demo System Builder',
        path: '/deployment/builder',
        icon: WandIcon,
        description: 'End-to-end deployment pipeline',
      },
      {
        label: 'Pipeline Status',
        path: '/deployment/pipelines',
        icon: ActivityIcon,
        description: 'Monitor pipeline runs',
      },
      {
        label: 'SAP CSV Exports',
        path: '/deployment/csvs',
        icon: DatabaseIcon,
        description: 'Download SAP-format CSV files',
      },


      {
        label: 'Knowledge Base',
        path: '/admin/knowledge-base',
        icon: BookOpenIcon,
        description: 'Upload documents for AI agent context (RAG)',
      },
    ],
  },
];

/**
 * Learning Mode Navigation (Simplified)
 *
 * For Learning customers - focused on scenario-based learning and AI familiarization.
 * Simplified navigation with only essential simulation features.
 *
 * NOTE: This is for user education, not AI model training.
 */
export const LEARNING_NAVIGATION = [
  {
    section: 'Dashboard',
    items: [
      {
        label: 'Learning Home',
        path: '/dashboard',
        icon: DashboardIcon,
        requiredCapability: null,
        description: 'Scenario status, leaderboards, progress',
      },
    ],
  },
  {
    section: 'Simulate',
    divider: true,
    items: [
      {
        label: 'New Scenario',
        path: '/scenarios/new',
        icon: GamesIcon,
        requiredCapability: 'create_game',
        description: 'Create a new learning scenario',
      },
      {
        label: 'My Scenarios',
        path: '/scenarios',
        icon: GamesIcon,
        requiredCapability: 'view_games',
        description: 'View and join active scenarios',
      },
    ],
  },
  {
    section: 'Results',
    divider: true,
    items: [
      {
        label: 'Scenario Reports',
        path: '/training/reports',
        icon: AnalyticsIcon,
        requiredCapability: 'view_games',
        description: 'Review scenario results and decisions',
      },
      {
        label: 'Compare Scenarios',
        path: '/training/compare',
        icon: CompareIcon,
        requiredCapability: 'view_analytics',
        description: 'Compare performance across scenarios',
      },
      {
        label: 'Leaderboards',
        path: '/training/leaderboards',
        icon: StatsIcon,
        requiredCapability: 'view_analytics',
        description: 'See how you rank against others',
      },
    ],
  },
  {
    section: 'Learn',
    divider: true,
    items: [
      {
        label: 'Supply Chain Basics',
        path: '/training/tutorials',
        icon: RecommendIcon,
        requiredCapability: null,
        description: 'Learn supply chain concepts',
        comingSoon: true,
      },
      {
        label: 'AI Agent Guide',
        path: '/training/ai-guide',
        icon: AIIcon,
        requiredCapability: null,
        description: 'Understand how AI agents work',
        comingSoon: true,
      },
    ],
  },
  {
    section: 'Administration',
    divider: true,
    adminOnly: true,
    items: [
      {
        label: 'Users',
        path: '/admin/users',
        icon: PeopleIcon,
        requiredCapability: 'view_users',
        description: 'Manage learning users',
      },
      {
        label: 'Scenario Configurations',
        path: '/admin/tenant/supply-chain-configs',
        icon: NetworkIcon,
        requiredCapability: 'view_sc_configs',
        description: 'Configure learning scenarios',
      },
    ],
  },
];

/**
 * Customer mode types
 *
 * NOTE: "LEARNING" is for user education (understanding AI agents).
 * This is separate from "AI Model Training" (TRM/GNN/RL training)
 * which can happen in BOTH Learning and Production customers.
 */
export const TENANT_MODES = {
  LEARNING: 'learning',      // User education mode
  PRODUCTION: 'production',  // Real data, real planning
};

// Backward-compatible aliases
export const CUSTOMER_MODES = TENANT_MODES;
export const GROUP_MODES = TENANT_MODES;

/**
 * Get filtered navigation based on user capabilities and tenant mode
 *
 * @param {Function} hasCapability - Function to check if user has capability
 * @param {boolean} isSystemAdmin - Whether user is system admin
 * @param {boolean} isTenantAdmin - Whether user is organization admin (TENANT_ADMIN type)
 * @param {string} tenantMode - Tenant mode: 'learning' or 'production' (default: 'production')
 * @returns {Array} Filtered navigation sections with enabled/disabled state
 */
export function getFilteredNavigation(hasCapability, isSystemAdmin, isTenantAdmin, tenantMode = 'production') {
  // System admins get special navigation
  if (isSystemAdmin) {
    return SYSTEM_ADMIN_NAVIGATION.map(section => ({
      ...section,
      items: section.items.map(item => ({
        ...item,
        enabled: true,
        disabled: false,
      })),
    }));
  }

  // Learning customers get simplified navigation (user education mode)
  // For admin sections, show if user is TENANT_ADMIN OR has any admin capability
  const hasAdminCapability = hasCapability('view_customers') ||
    hasCapability('view_users') ||
    hasCapability('view_sc_configs') ||
    hasCapability('manage_roles');

  if (tenantMode === TENANT_MODES.LEARNING) {
    return LEARNING_NAVIGATION
      .filter(section => {
        if (section.adminOnly && !isTenantAdmin && !hasAdminCapability) {
          return false;
        }
        return true;
      })
      .map(section => ({
        ...section,
        items: section.items
          .map(item => {
            if (!item.requiredCapability) {
              return { ...item, enabled: true, disabled: false };
            }
            const enabled = hasCapability(item.requiredCapability);
            return { ...item, enabled, disabled: !enabled };
          })
          .filter(item => item.enabled),
      }))
      .filter(section => section.items.length > 0);
  }

  // Production mode - full navigation
  // Filter and mark items as enabled/disabled based on capabilities
  return NAVIGATION_CONFIG
    .filter(section => {
      // Show admin sections if user is TENANT_ADMIN or has admin-related capabilities
      if (section.adminOnly && !isTenantAdmin && !hasAdminCapability) {
        return false;
      }
      return true;
    })
    .map(section => ({
      ...section,
      items: section.items
        .map(item => {
          // Section headers are always shown (filtered later if section empty)
          if (item.isSectionHeader) {
            return {
              ...item,
              enabled: true,
              disabled: false,
            };
          }

          // Items without capability requirement are always enabled
          if (!item.requiredCapability) {
            return {
              ...item,
              enabled: true,
              disabled: false,
            };
          }

          // Check if user has required capability
          const enabled = hasCapability(item.requiredCapability);

          return {
            ...item,
            enabled,
            disabled: !enabled,
          };
        })
        // Filter out disabled items (hide items user can't access)
        .filter(item => item.enabled || item.isSectionHeader)
    }))
    // Remove section headers that have no following items
    .map(section => {
      const filteredItems = [];
      let lastWasHeader = false;

      for (const item of section.items) {
        if (item.isSectionHeader) {
          // Only add header if we have items after it
          lastWasHeader = true;
        } else if (item.enabled) {
          // Add pending header if any
          if (lastWasHeader) {
            const headerIndex = section.items.indexOf(item) - 1;
            if (headerIndex >= 0) {
              filteredItems.push(section.items[headerIndex]);
            }
            lastWasHeader = false;
          }
          filteredItems.push(item);
        }
      }

      return {
        ...section,
        items: filteredItems,
      };
    })
    .filter(section => section.items.length > 0); // Remove empty sections
}

export default NAVIGATION_CONFIG;
