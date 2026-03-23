import React from "react";
import { Routes, Route, Navigate, Outlet, useLocation } from "react-router-dom";
import { Spinner } from "./components/common";
import Navbar from "./components/Navbar";
import LayoutWrapper from "./components/LayoutWrapper";
import CapabilityProtectedRoute from "./components/CapabilityProtectedRoute";
import SystemAdminRoute from "./components/SystemAdminRoute";
import { isSystemAdmin } from "./utils/authUtils";
import Dashboard from "./pages/Dashboard";
import DashboardRouter from "./pages/DashboardRouter";
import ProvisioningPage from "./pages/ProvisioningPage";
import ScenariosList from "./pages/ScenariosList";
import CreateScenario from "./pages/CreateScenario";
import CreateScenarioFromConfig from "./components/scenario/CreateScenarioFromConfig";
import ScenarioBoard from "./pages/ScenarioBoard";
import PlayGame from "./pages/PlayGame";
import ScenarioReport from "./pages/ScenarioReport.jsx";
import ScenarioVisualizations from "./pages/ScenarioVisualizations.jsx";
import Login from "./pages/Login.jsx";
import AutoLogin from "./pages/AutoLogin.jsx";
import { WebSocketProvider } from "./contexts/WebSocketContext";
import { useAuth } from "./contexts/AuthContext";
import "./utils/fetchInterceptor";
import AdminDashboard from "./pages/admin/Dashboard.jsx";
import ProductionAdminDashboard from "./pages/admin/ProductionAdminDashboard.jsx";
import AdminTraining from "./pages/admin/Training.jsx";
import ModelSetup from "./pages/admin/ModelSetup.jsx";
import TRMDashboard from "./pages/admin/TRMDashboard.jsx";
import GNNDashboard from "./pages/admin/GNNDashboard.jsx";
import GraphSAGEDashboard from "./pages/admin/GraphSAGEDashboard.jsx";
import RLDashboard from "./pages/admin/RLDashboard.jsx";
import PowellDashboard from "./pages/admin/PowellDashboard.jsx";
import Users from "./pages/Users";
import AdminUserManagement from "./pages/admin/UserManagement.js";
import SystemAdminUserManagement from "./pages/admin/SystemAdminUserManagement.jsx";
import TenantAdminUserManagement from "./pages/admin/TenantAdminUserManagement.jsx";
import TenantManagement from "./pages/admin/TenantManagement.jsx";
import Settings from "./pages/Settings";
import SystemConfig from "./pages/SystemConfig.jsx";
import Unauthorized from "./pages/Unauthorized";
import SupplyChainConfigList from "./components/supply-chain-config/SupplyChainConfigList";
import SupplyChainConfigForm from "./components/supply-chain-config/SupplyChainConfigForm";
import TenantSupplyChainConfigList from "./pages/admin/TenantSupplyChainConfigList.jsx";
import TenantSupplyChainConfigForm from "./pages/admin/TenantSupplyChainConfigForm.jsx";
import ScenarioTreeManager from "./pages/admin/ScenarioTreeManager.jsx";
import { ScenarioComparison } from "./components/stochastic";
import SyntheticDataWizard from "./pages/admin/SyntheticDataWizard.jsx";
import PlanningHierarchyConfig from "./pages/admin/PlanningHierarchyConfig.jsx";
import SAPDataManagement from "./pages/admin/SAPDataManagement.jsx";
import ERPDataManagement from "./pages/admin/ERPDataManagement.jsx";
import EmailSignalsDashboard from "./pages/admin/EmailSignalsDashboard.jsx";
import ExperientialKnowledgeDashboard from "./pages/admin/ExperientialKnowledgeDashboard.jsx";
import BscConfigPage from "./pages/admin/BscConfigPage.jsx";
import ContextEngine from "./pages/admin/ContextEngine.jsx";
import ExternalSignalsDashboard from "./pages/admin/ExternalSignalsDashboard.jsx";
import StochasticParamsEditor from "./pages/admin/StochasticParamsEditor.jsx";
import MetricConfigPage from "./pages/admin/MetricConfigPage.jsx";

import HiveDashboard from "./pages/admin/HiveDashboard.jsx";
import SkillsDashboard from "./pages/admin/SkillsDashboard.jsx";
import AuthorizationProtocolBoard from "./pages/admin/AuthorizationProtocolBoard.jsx";
import KnowledgeBase from "./pages/admin/KnowledgeBase.jsx";
import AgentBenchmarkDashboard from "./pages/admin/AgentBenchmarkDashboard.jsx";
import RLHFDashboard from "./pages/admin/RLHFDashboard.jsx";
import PerformanceLeaderboard from "./pages/admin/PerformanceLeaderboard.jsx";
import ScenarioUsers from "./pages/ScenarioUsers.jsx";
import DebugBanner from "./components/DebugBanner.jsx";
import AnalyticsDashboard from "./pages/AnalyticsDashboard.jsx";
import SystemDashboard from "./components/monitoring/SystemDashboard";
import SupplyChainAnalytics from "./pages/SupplyChainAnalytics.jsx";
import Insights from "./pages/Insights.jsx";
import InsightsLanding from "./pages/InsightsLanding.jsx";
import OrderPlanning from "./pages/OrderPlanning.jsx";
import NTierVisibility from "./pages/NTierVisibility.jsx";
import AIAssistant from "./pages/AIAssistant.jsx";
import UserRoleManagement from "./pages/admin/UserRoleManagement.jsx";
import MasterProductionScheduling from "./pages/MasterProductionScheduling.jsx";
import MonteCarloSimulation from "./pages/MonteCarloSimulation.jsx";
import ProductionOrdersPage from "./pages/production/ProductionOrders.jsx";
import CapacityPlanning from "./pages/CapacityPlanning.jsx";
import SupplierManagement from "./pages/SupplierManagement.jsx";
import InventoryProjection from "./pages/planning/InventoryProjection.jsx";
import LotSizingAnalysis from "./pages/planning/LotSizingAnalysis.jsx";
import CapacityCheck from "./pages/planning/CapacityCheck.jsx";
import MRPRun from "./pages/planning/MRPRun.jsx";
import PurchaseOrders from "./pages/planning/PurchaseOrders.jsx";
import Invoices from "./pages/planning/Invoices.jsx";
import TransferOrders from "./pages/planning/TransferOrders.jsx";
import SupplyPlanGeneration from "./pages/planning/SupplyPlanGeneration.jsx";
import ATPCTPView from "./pages/planning/ATPCTPView.jsx";
import SourcingAllocation from "./pages/planning/SourcingAllocation.jsx";
import KPIMonitoring from "./pages/planning/KPIMonitoring.jsx";
import HierarchicalMetricsDashboard from "./pages/planning/HierarchicalMetricsDashboard.jsx";
import Recommendations from "./pages/planning/Recommendations.jsx";
import DemandPlanView from "./pages/planning/DemandPlanView.jsx";
import DemandPlanningHub from "./pages/planning/DemandPlanningHub.jsx";
import SupplyPlanningHub from "./pages/planning/SupplyPlanningHub.jsx";
import InventoryPlanningHub from "./pages/planning/InventoryPlanningHub.jsx";
import CapacityPlanningHub from "./pages/planning/CapacityPlanningHub.jsx";
import ForecastAnalyticsHub from "./pages/planning/ForecastAnalyticsHub.jsx";
import CollaborationHub from "./pages/planning/CollaborationHub.jsx";
import ProjectOrders from "./pages/planning/ProjectOrders.jsx";
import MaintenanceOrders from "./pages/planning/MaintenanceOrders.jsx";
import TurnaroundOrders from "./pages/planning/TurnaroundOrders.jsx";
import RiskAnalysis from "./pages/analytics/RiskAnalysis.jsx";
import MaterialVisibility from "./pages/visibility/MaterialVisibility.jsx";
import ShipmentTracking from "./pages/planning/ShipmentTracking.jsx";
import VendorLeadTimes from "./pages/planning/VendorLeadTimes.jsx";
import ProductionProcesses from "./pages/planning/ProductionProcesses.jsx";
import ResourceCapacity from "./pages/planning/ResourceCapacity.jsx";
import DemandCollaboration from "./pages/planning/DemandCollaboration.jsx";
import ConsensusPlanning from "./pages/planning/ConsensusPlanning.jsx";
import ForecastExceptions from "./pages/planning/ForecastExceptions.jsx";
import Forecasting from "./pages/planning/Forecasting.jsx";
import ServiceOrders from "./pages/execution/ServiceOrders.jsx";
import InventoryOptimizationAnalytics from "./pages/analytics/InventoryOptimizationAnalytics.jsx";
import CapacityOptimizationAnalytics from "./pages/analytics/CapacityOptimizationAnalytics.jsx";
import NetworkOptimizationAnalytics from "./pages/analytics/NetworkOptimizationAnalytics.jsx";
import KPIConfigurationAnalytics from "./pages/analytics/KPIConfigurationAnalytics.jsx";
import UncertaintyQuantification from "./pages/analytics/UncertaintyQuantification.jsx";
import Governance from "./pages/admin/Governance.jsx";
import ApprovalTemplates from "./pages/admin/ApprovalTemplates.jsx";
import ExceptionWorkflows from "./pages/admin/ExceptionWorkflows.jsx";
import DemandPlanEdit from "./pages/planning/DemandPlanEdit.jsx";
import OrderManagement from "./pages/planning/OrderManagement.jsx";
import RecommendedActionsDashboard from "./pages/RecommendedActionsDashboard.jsx";
import SalesOperationsPlanning from "./pages/planning/SalesOperationsPlanning.jsx";
import InventoryOptimization from "./pages/planning/InventoryOptimization.jsx";
import PlanningBoard from "./pages/planning/PlanningBoard.jsx";
import PromotionalPlanning from "./pages/planning/PromotionalPlanning.jsx";
import ProductLifecycle from "./pages/planning/ProductLifecycle.jsx";
import MarkdownClearance from "./pages/planning/MarkdownClearance.jsx";
import InventoryVisibility from "./pages/visibility/InventoryVisibility.jsx";
import SOPPolicyPage from "./pages/planning/SOPPolicyPage.jsx";
import MPSCandidatesPage from "./pages/planning/MPSCandidatesPage.jsx";
import SupplyWorklistPage from "./pages/planning/SupplyWorklistPage.jsx";
import AllocationWorklistPage from "./pages/planning/AllocationWorklistPage.jsx";
import ExecutionPage from "./pages/planning/ExecutionPage.jsx";
import CascadeDashboard from "./pages/planning/CascadeDashboard.jsx";
import ATPWorklistPage from "./pages/planning/ATPWorklistPage.jsx";
import RebalancingWorklistPage from "./pages/planning/RebalancingWorklistPage.jsx";
import POWorklistPage from "./pages/planning/POWorklistPage.jsx";
import OrderTrackingWorklistPage from "./pages/planning/OrderTrackingWorklistPage.jsx";
import MOWorklistPage from "./pages/planning/MOWorklistPage.jsx";
import TOWorklistPage from "./pages/planning/TOWorklistPage.jsx";
import QualityWorklistPage from "./pages/planning/QualityWorklistPage.jsx";
import MaintenanceWorklistPage from "./pages/planning/MaintenanceWorklistPage.jsx";
import SubcontractingWorklistPage from "./pages/planning/SubcontractingWorklistPage.jsx";
import ForecastAdjWorklistPage from "./pages/planning/ForecastAdjWorklistPage.jsx";
import BufferWorklistPage from "./pages/planning/BufferWorklistPage.jsx";
import { TrainingLeaderboards, TrainingReports, TrainingCompare } from "./pages/training";
import ExecutiveDashboard from "./pages/ExecutiveDashboard";
import ExecutiveBriefingPage from "./pages/ExecutiveBriefingPage";
import DecisionStream from "./pages/DecisionStream";
import ScenarioEvents from "./pages/ScenarioEvents";
import AgentPerformancePage from "./pages/AgentPerformancePage";
import SOPWorklistPage from "./pages/SOPWorklistPage";
import DemoSystemBuilder from "./pages/deployment/DemoSystemBuilder.jsx";
import PipelineStatusPage from "./pages/deployment/PipelineStatus.jsx";
import CSVDownloads from "./pages/deployment/CSVDownloads.jsx";
import SAPConfigBuilder from "./pages/deployment/SAPConfigBuilder.jsx";
import { buildLoginRedirectPath, getDefaultLandingPath } from "./utils/authUtils";

window.onerror = function (message, source, lineno, colno, error) {
  console.error("Global error:", { message, source, lineno, colno, error });
  return false;
};
window.onunhandledrejection = function (event) {
  console.error("Unhandled rejection (promise):", event.reason);
};

function RequireAuth() {
  const { isAuthenticated, loading, user } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-screen">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to={buildLoginRedirectPath(location)} replace />;
  }

  // System admins can only access tenant/user management pages
  if (isSystemAdmin(user)) {
    const allowedPrefixes = ['/admin/tenants', '/admin/synthetic-data', '/system/users', '/profile', '/settings', '/unauthorized'];
    const isAllowed = allowedPrefixes.some(p => location.pathname.startsWith(p));
    if (!isAllowed) {
      return <Navigate to="/admin/tenants" replace />;
    }
  }

  return <Outlet />;
}

function LandingRedirect() {
  const { user } = useAuth();
  const destination = getDefaultLandingPath(user);

  return <Navigate to={destination} replace />;
}

const AppContent = () => {
  const location = useLocation();
  const isGamePage = location.pathname.startsWith("/scenarios/");

  return (
    <>
      <DebugBanner />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/auto-login" element={<AutoLogin />} />
        <Route path="/unauthorized" element={<Unauthorized />} />

        <Route element={<RequireAuth />}>
          <Route element={<LayoutWrapper />}>
            <Route path="/dashboard" element={<DashboardRouter />} />
            <Route path="/provisioning" element={<ProvisioningPage />} />

            {/* AIIO Framework - Insights & Actions Landing Page */}
            <Route path="/insights" element={<InsightsLanding />} />

            {/* Analytics Dashboard (charts/metrics view) */}
            <Route
              path="/reports/performance"
              element={
                <CapabilityProtectedRoute requiredCapability="view_analytics">
                  <Dashboard />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/scenarios/play"
              element={
                <CapabilityProtectedRoute requiredCapability="play_simulation">
                  <PlayGame />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/scenarios"
              element={
                <CapabilityProtectedRoute requiredCapability="view_simulations">
                  <ScenariosList />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/scenarios/new"
              element={
                <CapabilityProtectedRoute requiredCapability="create_simulation">
                  <CreateScenario />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/scenarios/new-from-config/:configId"
              element={
                <CapabilityProtectedRoute requiredCapability="create_simulation">
                  <CreateScenarioFromConfig />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/scenarios/compare"
              element={
                <CapabilityProtectedRoute requiredCapability="view_scenario_comparison">
                  <div className="p-6">
                    <ScenarioComparison />
                  </div>
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/scenarios/:scenarioId/edit"
              element={
                <CapabilityProtectedRoute requiredCapability="manage_simulations">
                  <CreateScenario />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/scenarios/:scenarioId"
              element={
                <CapabilityProtectedRoute requiredCapability="play_simulation">
                  {isGamePage ? (
                    <WebSocketProvider>
                      <ScenarioBoard />
                    </WebSocketProvider>
                  ) : (
                    <ScenarioBoard />
                  )}
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/scenarios/:scenarioId/report"
              element={
                <CapabilityProtectedRoute requiredCapability="view_scenario_analytics">
                  <ScenarioReport />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/scenarios/:scenarioId/visualizations"
              element={
                <CapabilityProtectedRoute requiredCapability="view_scenario_analytics">
                  <ScenarioVisualizations />
                </CapabilityProtectedRoute>
              }
            />

            {/* Training Mode routes */}
            <Route
              path="/training/leaderboards"
              element={
                <CapabilityProtectedRoute requiredCapability="view_analytics">
                  <TrainingLeaderboards />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/training/reports"
              element={
                <CapabilityProtectedRoute requiredCapability="view_simulations">
                  <TrainingReports />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/training/compare"
              element={
                <CapabilityProtectedRoute requiredCapability="view_analytics">
                  <TrainingCompare />
                </CapabilityProtectedRoute>
              }
            />

            {/* Adaptive Decision Hierarchy Dashboards */}
            <Route
              path="/executive-dashboard"
              element={
                <CapabilityProtectedRoute requiredCapability="view_executive_dashboard">
                  <ExecutiveDashboard />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/strategy-briefing"
              element={
                <CapabilityProtectedRoute requiredCapability="view_executive_dashboard">
                  <ExecutiveBriefingPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/sop-worklist"
              element={
                <CapabilityProtectedRoute requiredCapability="view_sop_worklist">
                  <SOPWorklistPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/agent-performance"
              element={
                <CapabilityProtectedRoute requiredCapability="view_executive_dashboard">
                  <AgentPerformancePage />
                </CapabilityProtectedRoute>
              }
            />

            {/* Admin routes */}
            <Route
              path="/admin"
              element={<AdminDashboard />}
            />
            <Route
              path="/admin/production"
              element={<ProductionAdminDashboard />}
            />
            <Route
              path="/admin/training"
              element={<AdminTraining />}
            />
            <Route
              path="/admin/model-setup"
              element={<ModelSetup />}
            />
            <Route
              path="/admin/trm"
              element={<TRMDashboard />}
            />
            <Route
              path="/admin/gnn"
              element={<GNNDashboard />}
            />
            <Route
              path="/admin/graphsage"
              element={<GraphSAGEDashboard />}
            />
            <Route
              path="/admin/rl"
              element={<RLDashboard />}
            />
            <Route
              path="/admin/powell"
              element={<PowellDashboard />}
            />
            <Route
              path="/admin/monitoring"
              element={<SystemDashboard />}
            />
            <Route
              path="/admin/governance"
              element={<Governance />}
            />
            <Route
              path="/admin/approval-templates"
              element={<ApprovalTemplates />}
            />
            <Route
              path="/admin/exception-workflows"
              element={<ExceptionWorkflows />}
            />
            <Route
              path="/admin/tenants"
              element={
                <SystemAdminRoute>
                  <TenantManagement />
                </SystemAdminRoute>
              }
            />
            <Route
              path="/admin/users"
              element={<AdminUserManagement />}
            />
            <Route
              path="/admin/tenant/users"
              element={<TenantAdminUserManagement />}
            />
            <Route
              path="/system/users"
              element={<SystemAdminUserManagement />}
            />
            <Route
              path="/admin/tenant/supply-chain-configs"
              element={<TenantSupplyChainConfigList />}
            />
            <Route
              path="/admin/tenant/supply-chain-configs/new"
              element={<TenantSupplyChainConfigForm />}
            />
            <Route
              path="/admin/tenant/supply-chain-configs/edit/:id"
              element={<TenantSupplyChainConfigForm />}
            />
            <Route
              path="/admin/tenant/supply-chain-configs/:configId/scenarios"
              element={<ScenarioTreeManager />}
            />
            <Route
              path="/admin/synthetic-data"
              element={
                <SystemAdminRoute>
                  <SyntheticDataWizard />
                </SystemAdminRoute>
              }
            />
            <Route
              path="/admin/tenant/planning-hierarchy"
              element={<PlanningHierarchyConfig />}
            />
            <Route
              path="/admin/sap-data"
              element={<SAPDataManagement />}
            />
            <Route
              path="/admin/erp-data"
              element={<ERPDataManagement />}
            />
            <Route
              path="/admin/stochastic-params"
              element={<StochasticParamsEditor />}
            />
            <Route
              path="/admin/metric-config"
              element={<MetricConfigPage />}
            />
            <Route
              path="/admin/email-signals"
              element={<EmailSignalsDashboard />}
            />
            <Route
              path="/admin/experiential-knowledge"
              element={<ExperientialKnowledgeDashboard />}
            />
            <Route
              path="/admin/bsc-config"
              element={<BscConfigPage />}
            />
            <Route
              path="/admin/context-engine"
              element={<ContextEngine />}
            />
            <Route
              path="/admin/external-signals"
              element={<ExternalSignalsDashboard />}
            />

            <Route
              path="/admin/hive"
              element={<HiveDashboard />}
            />
            <Route
              path="/admin/skills"
              element={<SkillsDashboard />}
            />
            <Route
              path="/admin/authorization-protocol"
              element={<AuthorizationProtocolBoard />}
            />
            <Route
              path="/admin/knowledge-base"
              element={<KnowledgeBase />}
            />
            <Route
              path="/admin/agent-benchmark"
              element={<AgentBenchmarkDashboard />}
            />
            <Route
              path="/admin/rlhf"
              element={<RLHFDashboard />}
            />
            <Route
              path="/admin/leaderboard"
              element={<PerformanceLeaderboard />}
            />

            <Route
              path="/users"
              element={<Users />}
            />

            <Route
              path="/admin/role-management"
              element={<UserRoleManagement />}
            />

            <Route
              path="/settings"
              element={<Settings />}
            />

            <Route
              path="/analytics"
              element={
                <CapabilityProtectedRoute requiredCapability="view_analytics">
                  <AnalyticsDashboard />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/sc-analytics"
              element={
                <CapabilityProtectedRoute requiredCapability="view_analytics">
                  <SupplyChainAnalytics />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/kpi-monitoring"
              element={
                <CapabilityProtectedRoute requiredCapability="view_kpi_monitoring">
                  <KPIMonitoring />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/metrics"
              element={
                <CapabilityProtectedRoute requiredCapability="view_kpi_monitoring">
                  <HierarchicalMetricsDashboard />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/analytics/risk"
              element={
                <CapabilityProtectedRoute requiredCapability="view_risk_analysis">
                  <RiskAnalysis />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/insights"
              element={
                <CapabilityProtectedRoute requiredCapability="view_analytics">
                  <Insights />
                </CapabilityProtectedRoute>
              }
            />

            {/* Recommended Actions Dashboard - AWS Supply Chain style */}
            <Route
              path="/insights/actions"
              element={
                <CapabilityProtectedRoute requiredCapability="view_recommendations">
                  <RecommendedActionsDashboard />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/analytics/inventory-optimization"
              element={
                <CapabilityProtectedRoute requiredCapability="view_inventory_optimization_analytics">
                  <InventoryOptimizationAnalytics />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/analytics/capacity-optimization"
              element={
                <CapabilityProtectedRoute requiredCapability="view_capacity_optimization_analytics">
                  <CapacityOptimizationAnalytics />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/analytics/network-optimization"
              element={
                <CapabilityProtectedRoute requiredCapability="view_network_optimization_analytics">
                  <NetworkOptimizationAnalytics />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/analytics/kpi-configuration"
              element={
                <CapabilityProtectedRoute requiredCapability="view_kpi_configuration_analytics">
                  <KPIConfigurationAnalytics />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/analytics/uncertainty"
              element={
                <CapabilityProtectedRoute requiredCapability="view_uncertainty_quantification">
                  <UncertaintyQuantification />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/orders"
              element={
                <CapabilityProtectedRoute requiredCapability="view_order_planning">
                  <OrderPlanning />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/recommendations"
              element={
                <CapabilityProtectedRoute requiredCapability="view_recommendations">
                  <Recommendations />
                </CapabilityProtectedRoute>
              }
            />

            {/* Strategic Planning */}
            <Route
              path="/planning/sop"
              element={
                <CapabilityProtectedRoute requiredCapability="view_sop">
                  <SalesOperationsPlanning />
                </CapabilityProtectedRoute>
              }
            />

            {/* Planning Cascade — Modular ADH Layers */}
            <Route
              path="/planning/cascade"
              element={
                <CapabilityProtectedRoute requiredCapability="view_cascade_dashboard">
                  <CascadeDashboard />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/sop-policy"
              element={
                <CapabilityProtectedRoute requiredCapability="view_sop_policy">
                  <SOPPolicyPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/mps-candidates"
              element={
                <CapabilityProtectedRoute requiredCapability="view_mps_candidates">
                  <MPSCandidatesPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/supply-worklist"
              element={
                <CapabilityProtectedRoute requiredCapability="view_supply_worklist">
                  <SupplyWorklistPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/allocation-worklist"
              element={
                <CapabilityProtectedRoute requiredCapability="view_allocation_worklist">
                  <AllocationWorklistPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/execution"
              element={
                <CapabilityProtectedRoute requiredCapability="view_execution_dashboard">
                  <ExecutionPage />
                </CapabilityProtectedRoute>
              }
            />

            {/* TRM Specialist Worklists */}
            <Route
              path="/planning/execution/atp-worklist"
              element={
                <CapabilityProtectedRoute requiredCapability="view_atp_worklist">
                  <ATPWorklistPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/execution/rebalancing-worklist"
              element={
                <CapabilityProtectedRoute requiredCapability="view_rebalancing_worklist">
                  <RebalancingWorklistPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/execution/po-worklist"
              element={
                <CapabilityProtectedRoute requiredCapability="view_po_worklist">
                  <POWorklistPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/execution/order-tracking-worklist"
              element={
                <CapabilityProtectedRoute requiredCapability="view_order_tracking_worklist">
                  <OrderTrackingWorklistPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/execution/mo-worklist"
              element={
                <CapabilityProtectedRoute requiredCapability="view_mo_worklist">
                  <MOWorklistPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/execution/to-worklist"
              element={
                <CapabilityProtectedRoute requiredCapability="view_to_worklist">
                  <TOWorklistPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/execution/quality-worklist"
              element={
                <CapabilityProtectedRoute requiredCapability="view_quality_worklist">
                  <QualityWorklistPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/execution/maintenance-worklist"
              element={
                <CapabilityProtectedRoute requiredCapability="view_maintenance_worklist">
                  <MaintenanceWorklistPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/execution/subcontracting-worklist"
              element={
                <CapabilityProtectedRoute requiredCapability="view_subcontracting_worklist">
                  <SubcontractingWorklistPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/execution/forecast-adj-worklist"
              element={
                <CapabilityProtectedRoute requiredCapability="view_forecast_adj_worklist">
                  <ForecastAdjWorklistPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/execution/buffer-worklist"
              element={
                <CapabilityProtectedRoute requiredCapability="view_buffer_worklist">
                  <BufferWorklistPage />
                </CapabilityProtectedRoute>
              }
            />

            {/* Tactical Planning Hubs */}
            <Route
              path="/planning/demand-planning"
              element={
                <CapabilityProtectedRoute requiredCapability="view_demand_planning">
                  <DemandPlanningHub />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/supply-planning"
              element={
                <CapabilityProtectedRoute requiredCapability="view_supply_plan">
                  <SupplyPlanningHub />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/inventory-planning"
              element={
                <CapabilityProtectedRoute requiredCapability="view_inventory_optimization">
                  <InventoryPlanningHub />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/capacity-planning"
              element={
                <CapabilityProtectedRoute requiredCapability="view_capacity_planning">
                  <CapacityPlanningHub />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/forecast-analytics"
              element={
                <CapabilityProtectedRoute requiredCapability="view_forecasting">
                  <ForecastAnalyticsHub />
                </CapabilityProtectedRoute>
              }
            />

            {/* Tactical Planning (legacy individual routes — still accessible for deep links) */}
            <Route
              path="/planning/inventory-optimization"
              element={
                <CapabilityProtectedRoute requiredCapability="view_inventory_optimization">
                  <InventoryOptimization />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/promotions"
              element={
                <CapabilityProtectedRoute requiredCapability="view_demand_planning">
                  <PromotionalPlanning />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/product-lifecycle"
              element={
                <CapabilityProtectedRoute requiredCapability="view_demand_planning">
                  <ProductLifecycle />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/markdown-clearance"
              element={
                <CapabilityProtectedRoute requiredCapability="view_inventory_optimization">
                  <MarkdownClearance />
                </CapabilityProtectedRoute>
              }
            />

            {/* Operational Planning */}
            <Route
              path="/planning/demand"
              element={
                <CapabilityProtectedRoute requiredCapability="view_demand_planning">
                  <DemandPlanView />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/demand/edit"
              element={
                <CapabilityProtectedRoute requiredCapability="manage_demand_planning">
                  <DemandPlanEdit />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/order-management"
              element={
                <CapabilityProtectedRoute requiredCapability="view_purchase_orders">
                  <OrderManagement />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/demand-collaboration"
              element={
                <CapabilityProtectedRoute requiredCapability="view_demand_collaboration">
                  <DemandCollaboration />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/consensus"
              element={
                <CapabilityProtectedRoute requiredCapability="view_demand_planning">
                  <ConsensusPlanning />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/forecasting"
              element={
                <CapabilityProtectedRoute requiredCapability="view_forecasting">
                  <Forecasting />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/forecast-exceptions"
              element={
                <CapabilityProtectedRoute requiredCapability="view_forecast_exceptions">
                  <ForecastExceptions />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/collaboration"
              element={
                <CapabilityProtectedRoute requiredCapability="view_collaboration">
                  <CollaborationHub />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/project-orders"
              element={
                <CapabilityProtectedRoute requiredCapability="view_project_orders">
                  <ProjectOrders />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/maintenance-orders"
              element={
                <CapabilityProtectedRoute requiredCapability="view_maintenance_orders">
                  <MaintenanceOrders />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/turnaround-orders"
              element={
                <CapabilityProtectedRoute requiredCapability="view_turnaround_orders">
                  <TurnaroundOrders />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/execution/service-orders"
              element={
                <CapabilityProtectedRoute requiredCapability="view_service_orders">
                  <ServiceOrders />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/supply-plan"
              element={
                <CapabilityProtectedRoute requiredCapability="view_supply_plan">
                  <SupplyPlanGeneration />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/board"
              element={
                <CapabilityProtectedRoute requiredCapability="view_supply_planning">
                  <PlanningBoard />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/execution/atp-ctp"
              element={
                <CapabilityProtectedRoute requiredCapability="view_atp_ctp">
                  <ATPCTPView />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/atp-ctp"
              element={<Navigate to="/execution/atp-ctp" replace />}
            />

            <Route
              path="/planning/sourcing"
              element={
                <CapabilityProtectedRoute requiredCapability="view_sourcing_allocation">
                  <SourcingAllocation />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/mps"
              element={
                <CapabilityProtectedRoute requiredCapability="view_mps">
                  <MasterProductionScheduling />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/mps/lot-sizing"
              element={
                <CapabilityProtectedRoute requiredCapability="view_lot_sizing">
                  <LotSizingAnalysis />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/mps/capacity-check"
              element={
                <CapabilityProtectedRoute requiredCapability="view_capacity_check">
                  <CapacityCheck />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/execution/mrp"
              element={
                <CapabilityProtectedRoute requiredCapability="view_mrp">
                  <MRPRun />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/planning/mrp"
              element={<Navigate to="/execution/mrp" replace />}
            />
            <Route
              path="/execution/po-creation"
              element={
                <CapabilityProtectedRoute requiredCapability="view_po_worklist">
                  <POWorklistPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/execution/inventory-rebalancing"
              element={
                <CapabilityProtectedRoute requiredCapability="view_rebalancing_worklist">
                  <RebalancingWorklistPage />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/production-processes"
              element={
                <CapabilityProtectedRoute requiredCapability="view_production_process">
                  <ProductionProcesses />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/purchase-orders"
              element={
                <CapabilityProtectedRoute requiredCapability="view_order_management">
                  <PurchaseOrders />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/invoices"
              element={
                <CapabilityProtectedRoute requiredCapability="view_order_management">
                  <Invoices />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/transfer-orders"
              element={
                <CapabilityProtectedRoute requiredCapability="view_order_management">
                  <TransferOrders />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/production-orders"
              element={<ProductionOrdersPage />}
            />

            <Route
              path="/production/orders"
              element={<ProductionOrdersPage />}
            />

            <Route
              path="/planning/capacity"
              element={<CapacityPlanning />}
            />

            <Route
              path="/planning/resource-capacity"
              element={
                <CapabilityProtectedRoute requiredCapability="view_resource_capacity">
                  <ResourceCapacity />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/suppliers"
              element={<SupplierManagement />}
            />

            <Route
              path="/planning/vendor-lead-times"
              element={
                <CapabilityProtectedRoute requiredCapability="view_vendor_lead_times">
                  <VendorLeadTimes />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/inventory-projection"
              element={<InventoryProjection />}
            />

            <Route
              path="/planning/monte-carlo"
              element={<MonteCarloSimulation />}
            />

            <Route
              path="/planning/optimization"
              element={
                <CapabilityProtectedRoute requiredCapability="view_optimization">
                  <div className="p-8 text-center">
                    <h2 className="text-xl font-semibold">Optimization</h2>
                    <p className="mt-4 text-muted-foreground">Coming Soon</p>
                  </div>
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/planning/network-design"
              element={
                <CapabilityProtectedRoute requiredCapability="view_network_design">
                  <div className="p-8 text-center">
                    <h2 className="text-xl font-semibold">Network Design</h2>
                    <p className="mt-4 text-muted-foreground">Coming Soon</p>
                  </div>
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/visibility/inventory"
              element={
                <CapabilityProtectedRoute requiredCapability="view_inventory_visibility">
                  <InventoryVisibility />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/analytics/scenarios"
              element={
                <CapabilityProtectedRoute requiredCapability="view_scenario_comparison">
                  <div className="p-8 text-center">
                    <h2 className="text-xl font-semibold">Scenario Comparison</h2>
                    <p className="mt-4 text-muted-foreground">Coming Soon</p>
                  </div>
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/ai/agents"
              element={
                <CapabilityProtectedRoute requiredCapability="manage_ai_agents">
                  <div className="p-8 text-center">
                    <h2 className="text-xl font-semibold">AI Agent Management</h2>
                    <p className="mt-4 text-muted-foreground">Coming Soon</p>
                  </div>
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/visibility/shipments"
              element={
                <CapabilityProtectedRoute requiredCapability="view_shipment_tracking">
                  <ShipmentTracking />
                </CapabilityProtectedRoute>
              }
            />

            <Route
              path="/visibility/ntier"
              element={<NTierVisibility />}
            />

            {/* AI Assistant removed — Azirella/Azirella replaces it */}
            <Route
              path="/ai-assistant"
              element={<Navigate to="/decision-stream" replace />}
            />
            <Route
              path="/decision-stream"
              element={<DecisionStream />}
            />
            <Route
              path="/scenario-events"
              element={<ScenarioEvents />}
            />

            <Route
              path="/system-config"
              element={<SystemConfig />}
            />

            <Route
              path="/scenarioUsers"
              element={<ScenarioUsers />}
            />
            {/* New terminology route (Feb 2026): /users -> ScenarioUsers page */}
            <Route
              path="/users"
              element={<ScenarioUsers />}
            />

            <Route
              path="/supply-chain-config"
              element={<SupplyChainConfigList />}
            />
            <Route
              path="/system/supply-chain-configs"
              element={<SupplyChainConfigList />}
            />
            <Route
              path="/supply-chain-config/new"
              element={<SupplyChainConfigForm />}
            />
            <Route
              path="/supply-chain-config/edit/:id"
              element={<SupplyChainConfigForm />}
            />

            {/* Deployment Pipeline */}
            <Route
              path="/deployment/builder"
              element={
                <CapabilityProtectedRoute requiredCapability="manage_deployment">
                  <DemoSystemBuilder />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/deployment/pipelines"
              element={
                <CapabilityProtectedRoute requiredCapability="manage_deployment">
                  <PipelineStatusPage />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/deployment/csvs"
              element={
                <CapabilityProtectedRoute requiredCapability="manage_deployment">
                  <CSVDownloads />
                </CapabilityProtectedRoute>
              }
            />
            <Route
              path="/deployment/sap-config-builder"
              element={
                <CapabilityProtectedRoute requiredCapability="manage_deployment">
                  <SAPConfigBuilder />
                </CapabilityProtectedRoute>
              }
            />

            <Route path="/" element={<LandingRedirect />} />
            <Route path="*" element={<Navigate to="/scenarios" replace />} />
          </Route>
        </Route>
      </Routes>
    </>
  );
};

export default AppContent;
