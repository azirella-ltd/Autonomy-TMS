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
  Sparkles as SparklesIcon,
  FlaskConical as ScenariosIcon,
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
  Mail as MailIcon,
  BrainCircuit as BrainCircuitIcon,
  Dice5 as MonteCarloIcon,
  Zap as ScenarioEventIcon,
  Scale as GovernanceIcon,
  Monitor as MonitoringIcon,
  Workflow as HierarchyIcon,
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
    sectionIcon: SparklesIcon,
    items: [
      {
        label: 'Decision Stream',
        path: '/decision-stream',
        icon: SparklesIcon,
        requiredCapability: null, // Visible to all except tenant admin (filtered below)
        hiddenForTenantAdmin: true, // Tenant admin uses Administration, not Decision Stream
        description: 'LLM-first decision inbox with conversational triage',
      },
      {
        label: 'Briefing',
        path: '/strategy-briefing',
        icon: BookOpenIcon,
        requiredCapability: 'view_executive_dashboard',
        description: 'AI-generated executive briefings with follow-up',
      },
      {
        label: 'Dashboard',
        path: '/executive-dashboard',
        icon: DashboardIcon,
        requiredCapability: 'view_executive_dashboard',
        description: 'Strategic KPIs, performance summary, ROI',
      },
      {
        label: 'Scenario Events',
        path: '/scenario-events',
        icon: ScenarioEventIcon,
        requiredCapability: null, // Always visible
        description: 'Inject what-if events and see CDC cascade responses',
      },
    ],
  },

  // ============================================================================
  // INSIGHTS & ANALYTICS (Consolidated)
  // ============================================================================
  {
    section: 'Insights & Analytics',
    sectionIcon: AnalyticsIcon,
    divider: true,
    items: [
      // Worklists by ADH level (Strategic → Tactical → Operational)
      // NOTE: Briefing and Dashboard moved to Home section
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
      {
        label: 'Monte Carlo Simulation',
        path: '/planning/monte-carlo',
        icon: MonteCarloIcon,
        requiredCapability: 'view_uncertainty_quantification',
        description: 'Stochastic simulation and scenario analysis',
      },
      {
        label: 'AI Recommendations',
        path: '/planning/recommendations',
        icon: RecommendIcon,
        requiredCapability: 'view_recommendations',
        description: 'AI agent recommendation history and outcomes',
      },
      {
        label: 'Performance Reports',
        path: '/reports/performance',
        icon: StatsIcon,
        requiredCapability: 'view_executive_dashboard',
        description: 'Performance reporting and insights landing',
      },
      {
        label: 'Capacity Analytics',
        path: '/analytics/capacity-optimization',
        icon: AssessmentIcon,
        requiredCapability: 'view_capacity_planning',
        description: 'Capacity optimization deep-dive analytics',
      },
      {
        label: 'Inventory Analytics',
        path: '/analytics/inventory-optimization',
        icon: InventoryIcon,
        requiredCapability: 'view_inventory_optimization',
        description: 'Inventory optimization analytics and what-if',
      },
      {
        label: 'Network Analytics',
        path: '/analytics/network-optimization',
        icon: NetworkIcon,
        requiredCapability: 'view_network_design',
        description: 'Network design and optimization analysis',
      },
    ],
  },

  // ============================================================================
  // PLANNING - Strategic / Tactical / Operational
  // ============================================================================
  {
    section: 'Planning',
    sectionIcon: CalendarIcon,
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
        label: 'Demand Planning',
        path: '/planning/demand-planning',
        icon: ForecastIcon,
        requiredCapability: 'view_demand_planning',
        description: 'Forecast, Sensing, Shaping, Consensus, Life Cycle, Exceptions',
      },
      {
        label: 'Supply Planning',
        path: '/planning/supply-planning',
        icon: ViewIcon,
        requiredCapability: 'view_supply_plan',
        description: 'Plan Generation, Sourcing, Net Requirements, Lot Sizing, RCCP',
      },
      {
        label: 'Inventory Planning',
        path: '/planning/inventory-planning',
        icon: InventoryIcon,
        requiredCapability: 'view_inventory_optimization',
        description: 'Policies, Projections, Segmentation, Allocations, ATP/CTP',
      },
      {
        label: 'Capacity Planning',
        path: '/planning/capacity-planning',
        icon: AssessmentIcon,
        requiredCapability: 'view_capacity_planning',
        description: 'Utilization, Bottleneck, Rough-Cut, Processes, Maintenance',
      },
      {
        label: 'Forecast Analytics',
        path: '/planning/forecast-analytics',
        icon: AnalyticsIcon,
        requiredCapability: 'view_forecasting',
        description: 'Pipeline, Accuracy, Drift, Distributions, Backtesting',
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
        label: 'Planning Board',
        path: '/planning/board',
        icon: LayersIcon,
        requiredCapability: 'view_supply_planning',
        description: 'Unified demand-supply netting with fan chart and MRP grid',
      },
      {
        label: 'AATP Allocations',
        path: '/execution/atp-ctp',
        icon: CrosshairIcon,
        requiredCapability: 'view_atp_ctp',
        description: 'Priority-based Available-to-Promise allocation',
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
  // PLANNING CASCADE — Modular ADH Layers (Independently Sellable)
  // ============================================================================
  {
    section: 'Planning Cascade',
    sectionIcon: CascadeIcon,
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
        description: 'Layer 5: MRP, Inventory Buffer, AATP, AI agents, feed-back signals',
      },
      // --- TRM SPECIALIST WORKLISTS ---
      {
        label: '— AI AGENT WORKLISTS —',
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
      {
        label: 'MO Execution Worklist',
        path: '/planning/execution/mo-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_mo_worklist',
        description: 'Manufacturing order decisions — release/expedite/defer with reason capture',
      },
      {
        label: 'TO Execution Worklist',
        path: '/planning/execution/to-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_to_worklist',
        description: 'Transfer order decisions — release/expedite/consolidate with reason capture',
      },
      {
        label: 'Quality Worklist',
        path: '/planning/execution/quality-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_quality_worklist',
        description: 'Quality disposition decisions — accept/reject/rework with reason capture',
      },
      {
        label: 'Maintenance Worklist',
        path: '/planning/execution/maintenance-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_maintenance_worklist',
        description: 'Maintenance scheduling decisions — schedule/defer/expedite with reason capture',
      },
      {
        label: 'Subcontracting Worklist',
        path: '/planning/execution/subcontracting-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_subcontracting_worklist',
        description: 'Make-vs-buy routing decisions — internal/external/split with reason capture',
      },
      {
        label: 'Forecast Adj. Worklist',
        path: '/planning/execution/forecast-adj-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_forecast_adj_worklist',
        description: 'Forecast adjustment decisions — up/down with signal context and reason capture',
      },
      {
        label: 'Buffer Worklist',
        path: '/planning/execution/buffer-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_buffer_worklist',
        description: 'Inventory buffer adjustment decisions — increase/decrease with reason capture',
      },
    ],
  },

  // ============================================================================
  // EXECUTION - Orders, Tracking, Procurement
  // ============================================================================
  {
    section: 'Execution',
    sectionIcon: ExecutionIcon,
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
    sectionIcon: ScenariosIcon,
    divider: true,
    productionOnly: true,  // Only show in Production mode
    items: [
      {
        label: 'Scenario Browser',
        path: '/scenarios',
        icon: ScenariosIcon,
        requiredCapability: 'view_simulations',
        description: 'Browse and manage scenarios',
      },
      {
        label: 'Create Scenario',
        path: '/scenarios/new',
        icon: ScenariosIcon,
        requiredCapability: 'create_simulation',
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
  // AI & AGENTS — 4-tier architecture:
  //   Strategic (Network) → Tactical (Network) → Operational (Site) → Execution (Site/Role)
  // ============================================================================
  {
    section: 'AI & Agents',
    sectionIcon: BrainIcon,
    divider: true,
    items: [
      // ── Agent Tiers ──────────────────────────────────────────────────
      {
        label: 'Strategic Agent',
        path: '/admin/graphsage',
        icon: BrainIcon,
        requiredCapability: 'view_gnn_training',
        description: 'Strategic / Network — weekly policy parameters and risk scoring',
      },
      {
        label: 'Tactical Agent',
        path: '/admin/gnn',
        icon: BrainIcon,
        requiredCapability: 'view_gnn_training',
        description: 'Tactical / Network — daily priority allocations across sites',
      },
      {
        label: 'Operational Agent',
        path: '/admin/hive',
        icon: BrainIcon,
        requiredCapability: 'view_trm_training',
        description: 'Operational / Site — hourly cross-agent coordination within a site',
      },
      {
        label: 'Execution Agents',
        path: '/admin/trm',
        icon: BrainIcon,
        requiredCapability: 'view_trm_training',
        description: 'Execution / Site / Role — 11 narrow decision agents per site',
      },
      // ── Agent Infrastructure ─────────────────────────────────────────
      {
        label: 'Decision Cascade',
        path: '/admin/powell',
        icon: LayersIcon,
        requiredCapability: 'view_powell',
        description: 'SDAM framework — State → Policy → Decision → Outcome',
      },
      // Hive Visualization is now accessed via Operational Agent above
      {
        label: 'Exception Handler',
        path: '/admin/skills',
        icon: ActivityIcon,
        requiredCapability: 'view_trm_training',
        description: 'LLM exception handling — escalation rates, RAG memory, outcomes',
      },
      {
        label: 'Agent Training',
        path: '/admin/rl',
        icon: BrainIcon,
        requiredCapability: 'view_rl_training',
        description: 'Reinforcement learning — behavioral cloning and fine-tuning',
      },
      // ── Performance & Feedback ───────────────────────────────────────
      {
        label: 'Agent Benchmark',
        path: '/admin/agent-benchmark',
        icon: AwardIcon,
        requiredCapability: 'view_ai_agents',
        description: 'Compare agent strategies — cost, service, efficiency (demo data)',
      },
      {
        label: 'Override Feedback',
        path: '/admin/rlhf',
        icon: ThumbsUpIcon,
        requiredCapability: 'view_rl_training',
        description: 'Human override patterns — training signal from planner decisions (demo data)',
      },
      {
        label: 'Performance Leaderboard',
        path: '/admin/leaderboard',
        icon: TrophyIcon,
        requiredCapability: 'view_ai_agents',
        description: 'Agent and planner performance rankings (demo data)',
      },
    ],
  },

  // ============================================================================
  // DEPLOYMENT (Demo System Builder)
  // ============================================================================
  {
    section: 'Deployment',
    sectionIcon: WandIcon,
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
    sectionIcon: AdminIcon,
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
        label: 'Context Engine',
        path: '/admin/context-engine',
        icon: LayersIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Unified hub for all external context sources',
      },
      {
        label: 'Market Intelligence',
        path: '/admin/external-signals',
        icon: LayersIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Outside-in planning signals: weather, economics, energy, geopolitical, sentiment, regulatory',
      },
      {
        label: 'SAP Data Management',
        path: '/admin/sap-data',
        icon: DatabaseIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'SAP connections, field mapping, and data ingestion',
      },
      {
        label: 'ERP Data Management',
        path: '/admin/erp-data',
        icon: DatabaseIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Odoo, D365, and other ERP connections and data extraction',
      },
      {
        label: 'Stochastic Parameters',
        path: '/admin/stochastic-params',
        icon: TuneIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Per-agent distribution parameters for stochastic simulation',
      },
      {
        label: 'Metric Configuration',
        path: '/admin/metric-config',
        icon: TuneIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Choose which SCOR metrics to display and set custom targets',
      },
      {
        label: 'Email Signals',
        path: '/admin/email-signals',
        icon: MailIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'GDPR-safe email ingestion for supply chain intelligence',
      },
      {
        label: 'Experiential Knowledge',
        path: '/admin/experiential-knowledge',
        icon: BrainCircuitIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Planner behavioral patterns — override-driven knowledge for RL training',
      },
      {
        label: 'Knowledge Base',
        path: '/admin/knowledge-base',
        icon: BookOpenIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Upload documents for AI agent context (RAG)',
      },
      {
        label: 'BSC Configuration',
        path: '/admin/bsc-config',
        icon: TuneIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Set balanced scorecard weights for AI calibration',
      },
      {
        label: 'Governance',
        path: '/admin/governance',
        icon: GovernanceIcon,
        requiredCapability: 'manage_approval_templates',
        description: 'Governance workflows and compliance controls',
      },
      {
        label: 'Planning Hierarchy',
        path: '/admin/tenant/planning-hierarchy',
        icon: HierarchyIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Configure MPS/MRP/S&OP planning levels',
      },
      {
        label: 'Model Setup',
        path: '/admin/model-setup',
        icon: SettingsIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'AI model architecture and training configuration',
      },
      {
        label: 'System Monitoring',
        path: '/admin/monitoring',
        icon: MonitoringIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'System health, telemetry, and performance monitoring',
      },
      {
        label: 'Synthetic Data Wizard',
        path: '/admin/synthetic-data',
        icon: WandIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'AI-guided company and supply chain data generation',
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
    sectionIcon: AdminIcon,
    items: [
      {
        label: 'Organizations',
        path: '/admin/tenants',
        icon: AdminIcon,
        description: 'Create and manage tenants and their administrators',
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
    sectionIcon: DashboardIcon,
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
    sectionIcon: ScenariosIcon,
    divider: true,
    items: [
      {
        label: 'New Scenario',
        path: '/scenarios/new',
        icon: ScenariosIcon,
        requiredCapability: 'create_simulation',
        description: 'Create a new learning scenario',
      },
      {
        label: 'My Scenarios',
        path: '/scenarios',
        icon: ScenariosIcon,
        requiredCapability: 'view_simulations',
        description: 'View and join active scenarios',
      },
    ],
  },
  {
    section: 'Results',
    sectionIcon: AnalyticsIcon,
    divider: true,
    items: [
      {
        label: 'Scenario Reports',
        path: '/training/reports',
        icon: AnalyticsIcon,
        requiredCapability: 'view_simulations',
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
    sectionIcon: BookOpenIcon,
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
    sectionIcon: AdminIcon,
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
export function getFilteredNavigation(hasCapability, isSystemAdmin, isTenantAdmin, tenantMode = 'production', decisionLevel = null) {
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

  // Decision-level section visibility — derived from the user's role in the Powell hierarchy.
  // DEMO_ALL and tenant admins see everything. Others see only sections relevant to their level.
  const DECISION_LEVEL_SECTIONS = {
    EXECUTIVE:     ['Home'],
    SC_VP:         ['Home'],
    SOP_DIRECTOR:  ['Home', 'Insights & Analytics', 'Planning', 'Planning Cascade'],
    MPS_MANAGER:   ['Home', 'Insights & Analytics', 'Planning', 'Planning Cascade', 'Execution'],
    DEMO_ALL:      null, // null = show all
  };
  // Executive/SC_VP: only show these items within Home
  const EXECUTIVE_HOME_ITEMS = new Set(['Decision Stream', 'Briefing', 'Dashboard']);
  const isExecutiveLevel = decisionLevel === 'EXECUTIVE' || decisionLevel === 'SC_VP';

  const allowedSections = (decisionLevel && DECISION_LEVEL_SECTIONS[decisionLevel]) || null;

  // Tenant admin (no decision_level) = Administration only.
  // They manage the tenant — they don't plan, execute, or monitor.
  const sectionFilter = (sectionName) => {
    if (isTenantAdmin && !decisionLevel) {
      return sectionName === 'Administration';
    }
    if (!allowedSections) return true; // DEMO_ALL → show all
    if (sectionName === 'Administration' && isTenantAdmin) return true;
    return allowedSections.includes(sectionName);
  };
  // Item-level filter for executives
  const itemFilter = (sectionName, itemLabel) => {
    if (isExecutiveLevel && sectionName === 'Home') {
      return EXECUTIVE_HOME_ITEMS.has(itemLabel);
    }
    return true;
  };

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
  // Filter by decision level (section visibility) and capabilities (item visibility)
  return NAVIGATION_CONFIG
    .filter(section => {
      // Decision-level section filter
      if (!sectionFilter(section.section)) return false;
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

          // Hide items flagged for tenant admin exclusion
          if (item.hiddenForTenantAdmin && isTenantAdmin) {
            return { ...item, enabled: false, disabled: true };
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
        // Filter out disabled items and decision-level restricted items
        .filter(item => (item.enabled || item.isSectionHeader) && itemFilter(section.section, item.label))
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
