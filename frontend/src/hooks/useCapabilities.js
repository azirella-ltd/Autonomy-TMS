/**
 * useCapabilities Hook
 *
 * Hook to fetch and check user capabilities for permission-based UI.
 */

import { useState, useEffect } from 'react';
import { api } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

export const useCapabilities = () => {
  const { user, isAuthenticated } = useAuth();
  const [capabilities, setCapabilities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchCapabilities = async () => {
      if (!isAuthenticated || !user) {
        setCapabilities([]);
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        // Use /capabilities/me endpoint - works for any authenticated user
        const response = await api.get('/capabilities/me');
        setCapabilities(response.data.capabilities || []);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch capabilities:', err);
        setError(err.message);
        // Fallback: grant basic capabilities based on user type
        setCapabilities(getFallbackCapabilities(user.user_type));
      } finally {
        setLoading(false);
      }
    };

    fetchCapabilities();
  }, [isAuthenticated, user]);

  const hasCapability = (capability) => {
    if (!isAuthenticated) return false;

    // System admin has all capabilities
    if (capabilities.includes('system_admin')) return true;

    return capabilities.includes(capability);
  };

  const hasAnyCapability = (...caps) => {
    return caps.some((cap) => hasCapability(cap));
  };

  const hasAllCapabilities = (...caps) => {
    return caps.every((cap) => hasCapability(cap));
  };

  return {
    capabilities,
    loading,
    error,
    hasCapability,
    hasAnyCapability,
    hasAllCapabilities,
  };
};

/**
 * Get fallback capabilities based on user type when API fails
 */
function getFallbackCapabilities(userType) {
  const type = (userType || '').toUpperCase();

  if (type === 'SYSTEM_ADMIN') {
    return ['system_admin'];
  }

  if (type === 'TENANT_ADMIN') {
    return [
      // Overview
      'view_dashboard',
      'view_analytics',
      'view_sc_analytics',
      'view_insights',
      'view_uncertainty_quantification',

      // Risk Analysis & Insights
      'view_risk_analysis',
      'manage_risk_alerts',
      'view_watchlists',
      'view_predictions',
      'view_recommendations',

      // Powell Dashboards
      'view_executive_dashboard',
      'view_sop_worklist',
      'view_agent_decisions',

      // Material Visibility
      'view_shipment_tracking',
      'view_inventory_visibility',
      'view_ntier_visibility',

      // Gamification
      'view_simulations',
      'create_simulation',
      'play_simulation',
      'delete_simulation',
      'manage_simulations',

      // Supply Chain
      'view_sc_configs',
      'view_inventory_models',
      'view_tenant_configs',
      'manage_tenant_configs',

      // Planning - All
      'view_sop',
      'view_network_design',
      'view_order_planning',
      'view_demand_planning',
      'view_forecasting',
      'view_demand_collaboration',
      'view_forecast_exceptions',
      'view_supply_planning',
      'view_supply_plan',
      'view_mps',
      'view_lot_sizing',
      'view_capacity_check',
      'view_inventory_optimization',
      'view_mrp',
      'view_production_process',
      'view_atp_ctp',
      'view_sourcing_allocation',
      'view_supplier_management',
      'view_vendor_lead_times',
      'view_capacity_planning',
      'view_resource_capacity',
      'view_optimization',
      'view_collaboration',
      'view_kpi_monitoring',

      // Planning Cascade
      'view_cascade_dashboard',
      'view_sop_policy',
      'view_mps_candidates',
      'view_supply_worklist',
      'view_allocation_worklist',
      'view_execution_dashboard',

      // TRM Worklists
      'view_atp_worklist',
      'view_rebalancing_worklist',
      'view_po_worklist',
      'view_order_tracking_worklist',

      // Order Management
      'view_order_management',
      'view_production_orders',
      'view_project_orders',
      'view_maintenance_orders',
      'view_turnaround_orders',
      'view_service_orders',

      // Analytics
      'view_scenario_comparison',

      // AI/ML
      'use_ai_assistant',
      'view_ai_agents',
      'manage_ai_agents',
      'view_trm_training',
      'view_gnn_training',
      'view_rl_training',
      'view_model_setup',
      'view_powell',

      // Admin
      'view_tenants',
      'manage_tenants',
      'view_scenario_users',
      'manage_scenario_users',
      'view_users',
      'create_user',
      'edit_user',
      'manage_permissions',
      'manage_roles',
      'manage_tenant_users',
      'manage_approval_templates',
    ];
  }

  // Default: USER - Standard user access
  return [
    'view_dashboard',
    'view_simulations',
    'play_simulation',
  ];
}

export default useCapabilities;
