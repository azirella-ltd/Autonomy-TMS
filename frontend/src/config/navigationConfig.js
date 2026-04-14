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
    // v1.11.1 declarative gate
    visibleToDecisionLevels: ['EXECUTIVE', 'SC_VP', 'SOP_DIRECTOR', 'MPS_MANAGER', 'DEMO_ALL'],
    items: [
      // Order: Decision Stream is the super-user landing page for all non-
      // tenant-admin roles. Briefing and Dashboard follow as strategic
      // context. Scenario Events was removed — the /scenario-events page
      // renders a blank component (tracked as tech debt); the "what-if"
      // flow lives under Scenarios instead.
      {
        label: 'Decision Stream',
        path: '/decision-stream',
        icon: SparklesIcon,
        requiredCapability: null, // Visible to all except tenant admin (filtered below)
        hiddenForTenantAdmin: true, // Tenant admin uses Administration, not Decision Stream
        description: 'Agent decisions with inspect and override',
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
    ],
  },

  // ============================================================================
  // INSIGHTS & ANALYTICS (Consolidated)
  // ============================================================================
  {
    section: 'Insights & Analytics',
    visibleToDecisionLevels: ['SOP_DIRECTOR', 'MPS_MANAGER', 'DEMO_ALL'],
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
    visibleToDecisionLevels: ['SOP_DIRECTOR', 'MPS_MANAGER', 'DEMO_ALL'],
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
      // MPS merged into Supply & Production Plan — no separate nav entry.
      // Forecast Analytics merged into Demand Planning → Analytics tab.
      {
        label: 'Supply & Production Plan',
        path: '/planning/supply-planning',
        icon: ViewIcon,
        requiredCapability: 'view_supply_plan',
        description: 'Plan of Record, Sourcing, Net Requirements, Capacity, Agent Directives',
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
    visibleToDecisionLevels: ['SOP_DIRECTOR', 'MPS_MANAGER', 'DEMO_ALL'],
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
      // --- TMS TRM AGENT WORKLISTS ---
      // Grouped by decision cycle phase: SENSE → ASSESS → ACQUIRE → PROTECT → BUILD → REFLECT
      {
        label: '— TMS AGENT WORKLISTS —',
        path: null,
        icon: null,
        requiredCapability: null,
        isSectionHeader: true,
      },
      // SENSE Phase
      {
        label: 'Capacity Promise',
        path: '/planning/execution/capacity-promise-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_capacity_promise_worklist',
        description: 'Lane capacity commitment decisions — promise/defer/escalate with reason capture',
      },
      {
        label: 'Shipment Tracking',
        path: '/planning/execution/shipment-tracking-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_shipment_tracking_worklist',
        description: 'In-transit exception and ETA decisions — reroute/retender/hold with reason capture',
      },
      {
        label: 'Demand Sensing',
        path: '/planning/execution/demand-sensing-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_demand_sensing_worklist',
        description: 'Shipping volume forecast adjustments — signal-driven with reason capture',
      },
      // ASSESS Phase
      {
        label: 'Capacity Buffer',
        path: '/planning/execution/capacity-buffer-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_capacity_buffer_worklist',
        description: 'Reserve carrier capacity decisions — buffer sizing with reason capture',
      },
      {
        label: 'Exception Mgmt',
        path: '/planning/execution/exception-mgmt-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_exception_mgmt_worklist',
        description: 'Delay/damage/refusal resolution — retender/reroute/escalate with reason capture',
      },
      // ACQUIRE Phase
      {
        label: 'Freight Procurement',
        path: '/planning/execution/freight-procurement-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_freight_procurement_worklist',
        description: 'Carrier waterfall tendering — tender/spot/broker with reason capture',
      },
      {
        label: 'Broker Routing',
        path: '/planning/execution/broker-routing-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_broker_routing_worklist',
        description: 'Broker vs asset carrier routing — overflow decisions with reason capture',
      },
      // PROTECT Phase
      {
        label: 'Dock Scheduling',
        path: '/planning/execution/dock-scheduling-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_dock_scheduling_worklist',
        description: 'Appointment and dock door optimization — schedule/defer with reason capture',
      },
      // BUILD Phase
      {
        label: 'Load Build',
        path: '/planning/execution/load-build-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_load_build_worklist',
        description: 'Load consolidation and optimization — consolidate/split with reason capture',
      },
      {
        label: 'Intermodal Transfer',
        path: '/planning/execution/intermodal-transfer-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_intermodal_transfer_worklist',
        description: 'Cross-mode transfer decisions — mode shift with reason capture',
      },
      // REFLECT Phase
      {
        label: 'Equipment Reposition',
        path: '/planning/execution/equipment-reposition-worklist',
        icon: WorklistIcon,
        requiredCapability: 'view_equipment_reposition_worklist',
        description: 'Empty container/trailer repositioning — reposition/hold with reason capture',
      },
    ],
  },

  // ============================================================================
  // EXECUTION - Orders, Tracking, Procurement
  // ============================================================================
  {
    section: 'Execution',
    visibleToDecisionLevels: ['MPS_MANAGER', 'DEMO_ALL'],
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

      // --- TMS VISIBILITY ---
      {
        label: '— TMS VISIBILITY —',
        path: null,
        icon: null,
        requiredCapability: null,
        isSectionHeader: true,
      },
      {
        label: 'Shipment Map',
        path: '/visibility/shipment-map',
        icon: ShippingIcon,
        requiredCapability: 'view_shipment_tracking',
        description: 'Real-time shipment positions, status markers, disruption overlays',
      },
      // --- TMS PLANNING ---
      {
        label: '— TMS PLANNING —',
        path: null,
        icon: null,
        requiredCapability: null,
        isSectionHeader: true,
      },
      {
        label: 'Load Board',
        path: '/planning/load-board',
        icon: OrderIcon,
        requiredCapability: 'view_load_board',
        description: 'Load planning, status board, carrier assignment',
      },
      {
        label: 'Lane Analytics',
        path: '/planning/lane-analytics',
        icon: StatsIcon,
        requiredCapability: 'view_lane_analytics',
        description: 'Lane performance, cost trends, carrier mix, OTD by lane',
      },
      {
        label: 'Dock Schedule',
        path: '/planning/dock-schedule',
        icon: FactoryIcon,
        requiredCapability: 'view_dock_schedule',
        description: 'Appointment timeline, door utilization, dwell tracking',
      },
      {
        label: 'Exception Dashboard',
        path: '/planning/exception-dashboard',
        icon: RiskIcon,
        requiredCapability: 'view_exception_dashboard',
        description: 'Real-time shipment exception monitoring and resolution',
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
    visibleToDecisionLevels: ['DEMO_ALL'],
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
    visibleToDecisionLevels: ['DEMO_ALL'],
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
    visibleToDecisionLevels: ['DEMO_ALL'],
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
    adminOnly: true,  // legacy flag — kept for local filter (pending retirement)
    // v1.11.1: visible to tenant admins OR DEMO_ALL users (OR-gate)
    tenantAdminOnly: true,
    visibleToDecisionLevels: ['DEMO_ALL'],
    items: [
      {
        label: 'Supply Chain Configs',
        path: '/admin/tenant/supply-chain-configs',
        icon: NetworkIcon,
        requiredCapability: 'view_sc_configs',
        description: 'Manage supply chain configurations, provisioning, and model confidence',
      },
      {
        label: 'Decision Governance',
        path: '/admin/governance',
        icon: GovernanceIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Decision pipeline: AIIO thresholds, guardrails, planning envelope, audit trail',
      },
      // --- TMS-SPECIFIC ADMIN ---
      {
        label: 'Carrier Management',
        path: '/admin/carrier-management',
        icon: NetworkIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Carrier onboarding, scorecards, lane coverage, contract management',
      },
      {
        label: 'Rate Management',
        path: '/admin/rate-management',
        icon: TuneIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Contract rates, spot quotes, rate cards, accessorial charges',
      },
      {
        label: 'p44 Settings',
        path: '/admin/p44-settings',
        icon: LayersIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'project44 connection configuration and webhook setup',
      },
      {
        label: 'p44 Dashboard',
        path: '/admin/p44-dashboard',
        icon: MonitoringIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'project44 tracking coverage, webhook health, event feed',
      },
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
      // Approval Templates and Exception Workflows removed:
      // AIIO principle — agents always act, no approval workflow needed.
      // Exception handling is done by TRM agents (Order Tracking, Quality).
      {
        label: 'Context Engine',
        path: '/admin/context-engine',
        icon: LayersIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Unified hub for all external context sources',
      },
      // Market Intelligence removed as separate nav entry — it's a card inside Context Engine.
      {
        label: 'ERP Data Management',
        path: '/admin/erp-data',
        icon: DatabaseIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'SAP, Odoo, D365, B1 connections and data ingestion',
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
      // Email Signals, Knowledge Base — already cards inside Context Engine.
      // Model Setup, System Monitoring — internal/technical, not tenant admin facing.
      {
        label: 'BSC Configuration',
        path: '/admin/bsc-config',
        icon: TuneIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Cost vs service weights and AI autonomy thresholds',
      },
      {
        label: 'Experiential Knowledge',
        path: '/admin/experiential-knowledge',
        icon: BrainCircuitIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'Planner behavioral patterns — override-driven knowledge for RL training',
      },
      {
        label: 'Planning Hierarchy',
        path: '/admin/tenant/planning-hierarchy',
        icon: HierarchyIcon,
        requiredCapability: 'manage_tenant_users',
        description: 'S&OP / MPS / Execution planning levels (auto-derived from master data)',
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
      {
        label: 'Decision Governance',
        path: '/admin/governance',
        icon: GovernanceIcon,
        description: 'Inspect and configure decision governance pipeline across tenants',
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
    adminOnly: true,  // legacy flag — kept for local filter (pending retirement)
    // v1.11.1: visible to tenant admins OR DEMO_ALL users (OR-gate)
    tenantAdminOnly: true,
    visibleToDecisionLevels: ['DEMO_ALL'],
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
/**
 * @deprecated since v1.11.1 of @azirella-ltd/autonomy-frontend.
 *
 * WorkspaceShell uses the shared useFilteredNavigation hook via
 * declarative fields (requiredCapability, requiredDecisionLevels,
 * hiddenForTenantAdmin, visibleToDecisionLevels, tenantAdminOnly).
 * This function is retained only for CapabilityAwareNavbar,
 * CapabilityAwareSidebar, TwoTierNav (local copy), and NewTabPalette,
 * which are candidates for replacement with the shared shell components.
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
