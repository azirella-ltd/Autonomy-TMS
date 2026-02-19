/**
 * Insights & Actions API Service - AIIO Framework
 *
 * Client for the insights landing page API with hierarchy drill-down.
 * Supports the Automate, Inform, Inspect, Override (AIIO) workflow.
 */

import { api } from './api';

const BASE_URL = '/insights';

/**
 * Build query params from hierarchy context
 */
const buildHierarchyParams = (context = {}) => {
  const params = new URLSearchParams();

  if (context.siteLevel) params.append('site_level', context.siteLevel);
  if (context.siteKey) params.append('site_key', context.siteKey);
  if (context.productLevel) params.append('product_level', context.productLevel);
  if (context.productKey) params.append('product_key', context.productKey);
  if (context.timeBucket) params.append('time_bucket', context.timeBucket);
  if (context.timeKey) params.append('time_key', context.timeKey);

  return params;
};

/**
 * Get dashboard summary at specified hierarchy level
 *
 * @param {Object} context - Hierarchy context
 * @param {string} context.siteLevel - Site hierarchy level (company, region, country, state, site)
 * @param {string} context.siteKey - Specific site key
 * @param {string} context.productLevel - Product hierarchy level (category, family, group, product)
 * @param {string} context.productKey - Specific product key
 * @param {string} context.timeBucket - Time bucket (year, quarter, month, week, day, hour)
 * @param {string} context.timeKey - Specific time period
 * @param {number} recentLimit - Number of recent actions to include
 * @returns {Promise<Object>} Dashboard summary
 */
export const getDashboard = async (context = {}, recentLimit = 10) => {
  const params = buildHierarchyParams(context);
  params.append('recent_limit', recentLimit);

  const response = await api.get(`${BASE_URL}/dashboard?${params.toString()}`);
  return response.data;
};

/**
 * Get list of actions with filtering
 *
 * @param {Object} filters - Action filters
 * @param {string} filters.mode - Filter by mode (automate, inform)
 * @param {string} filters.category - Filter by category
 * @param {string} filters.actionType - Filter by action type
 * @param {boolean} filters.acknowledged - Filter by acknowledged status
 * @param {boolean} filters.overridden - Filter by overridden status
 * @param {string} filters.agentId - Filter by agent
 * @param {number} filters.offset - Pagination offset
 * @param {number} filters.limit - Page size
 * @param {Object} context - Hierarchy context
 * @returns {Promise<Object>} Actions list response
 */
export const getActions = async (filters = {}, context = {}) => {
  const params = buildHierarchyParams(context);

  // Add filters
  if (filters.mode) params.append('mode', filters.mode);
  if (filters.category) params.append('category', filters.category);
  if (filters.actionType) params.append('action_type', filters.actionType);
  if (filters.acknowledged !== undefined) params.append('acknowledged', filters.acknowledged);
  if (filters.overridden !== undefined) params.append('overridden', filters.overridden);
  if (filters.agentId) params.append('agent_id', filters.agentId);
  if (filters.executionResult) params.append('execution_result', filters.executionResult);

  // Pagination
  params.append('offset', filters.offset || 0);
  params.append('limit', filters.limit || 50);

  const response = await api.get(`${BASE_URL}/actions?${params.toString()}`);
  return response.data;
};

/**
 * Get action detail for INSPECT workflow
 *
 * @param {number} actionId - Action ID
 * @returns {Promise<Object>} Action detail with explanation and alternatives
 */
export const getActionDetail = async (actionId) => {
  const response = await api.get(`${BASE_URL}/actions/${actionId}`);
  return response.data;
};

/**
 * Acknowledge an INFORM action
 *
 * @param {number} actionId - Action ID
 * @returns {Promise<Object>} Updated action
 */
export const acknowledgeAction = async (actionId) => {
  const response = await api.post(`${BASE_URL}/actions/${actionId}/acknowledge`);
  return response.data;
};

/**
 * Override an action with required reason
 *
 * @param {number} actionId - Action ID
 * @param {string} reason - REQUIRED reason for override
 * @param {Object} overrideAction - Optional structured data about what user did instead
 * @returns {Promise<Object>} Updated action
 */
export const overrideAction = async (actionId, reason, overrideAction = null) => {
  const response = await api.post(`${BASE_URL}/actions/${actionId}/override`, {
    reason,
    override_action: overrideAction,
  });
  return response.data;
};

/**
 * Get children for drill-down navigation
 *
 * @param {string} dimension - Dimension to drill down (site, product, time)
 * @param {Object} context - Current hierarchy context
 * @returns {Promise<Object>} Drill-down children
 */
export const getDrillDown = async (dimension, context = {}) => {
  const params = buildHierarchyParams(context);
  params.append('dimension', dimension);

  const response = await api.get(`${BASE_URL}/drill-down?${params.toString()}`);
  return response.data;
};

/**
 * Helper to navigate down one hierarchy level
 *
 * @param {Object} context - Current context
 * @param {string} dimension - Dimension to drill down
 * @param {string} targetKey - Key to drill into
 * @returns {Object} New context at lower level
 */
export const drillDown = (context, dimension, targetKey) => {
  const levelOrders = {
    site: ['company', 'region', 'country', 'state', 'site'],
    product: ['category', 'family', 'group', 'product'],
    time: ['year', 'quarter', 'month', 'week', 'day', 'hour'],
  };

  const newContext = { ...context };

  if (dimension === 'site') {
    const levels = levelOrders.site;
    const currentIdx = levels.indexOf(context.siteLevel || 'company');
    if (currentIdx < levels.length - 1) {
      newContext.siteLevel = levels[currentIdx + 1];
      newContext.siteKey = targetKey;
    }
  } else if (dimension === 'product') {
    const levels = levelOrders.product;
    const currentIdx = levels.indexOf(context.productLevel || 'category');
    if (currentIdx < levels.length - 1) {
      newContext.productLevel = levels[currentIdx + 1];
      newContext.productKey = targetKey;
    }
  } else if (dimension === 'time') {
    const levels = levelOrders.time;
    const currentIdx = levels.indexOf(context.timeBucket || 'month');
    if (currentIdx < levels.length - 1) {
      newContext.timeBucket = levels[currentIdx + 1];
      newContext.timeKey = targetKey;
    }
  }

  return newContext;
};

/**
 * Helper to navigate up one hierarchy level
 *
 * @param {Object} context - Current context
 * @param {string} dimension - Dimension to drill up
 * @returns {Object} New context at higher level
 */
export const drillUp = (context, dimension) => {
  const levelOrders = {
    site: ['company', 'region', 'country', 'state', 'site'],
    product: ['category', 'family', 'group', 'product'],
    time: ['year', 'quarter', 'month', 'week', 'day', 'hour'],
  };

  const newContext = { ...context };

  if (dimension === 'site') {
    const levels = levelOrders.site;
    const currentIdx = levels.indexOf(context.siteLevel || 'company');
    if (currentIdx > 0) {
      newContext.siteLevel = levels[currentIdx - 1];
      newContext.siteKey = null;
    }
  } else if (dimension === 'product') {
    const levels = levelOrders.product;
    const currentIdx = levels.indexOf(context.productLevel || 'category');
    if (currentIdx > 0) {
      newContext.productLevel = levels[currentIdx - 1];
      newContext.productKey = null;
    }
  } else if (dimension === 'time') {
    const levels = levelOrders.time;
    const currentIdx = levels.indexOf(context.timeBucket || 'month');
    if (currentIdx > 0) {
      newContext.timeBucket = levels[currentIdx - 1];
      newContext.timeKey = null;
    }
  }

  return newContext;
};

// Mode labels for display
export const ACTION_MODES = {
  automate: { label: 'Automated', color: 'bg-blue-100 text-blue-800', description: 'Executed automatically' },
  inform: { label: 'Informed', color: 'bg-green-100 text-green-800', description: 'Executed and notified' },
};

// Category labels for display
export const ACTION_CATEGORIES = {
  inventory: { label: 'Inventory', icon: 'Package' },
  procurement: { label: 'Procurement', icon: 'ShoppingCart' },
  demand: { label: 'Demand', icon: 'TrendingUp' },
  production: { label: 'Production', icon: 'Factory' },
  logistics: { label: 'Logistics', icon: 'Truck' },
  pricing: { label: 'Pricing', icon: 'DollarSign' },
  risk: { label: 'Risk', icon: 'AlertTriangle' },
  allocation: { label: 'Allocation', icon: 'GitBranch' },
  other: { label: 'Other', icon: 'MoreHorizontal' },
};

// Hierarchy level labels
export const HIERARCHY_LEVELS = {
  site: {
    company: 'Company',
    region: 'Region',
    country: 'Country',
    state: 'State',
    site: 'Site',
  },
  product: {
    category: 'Category',
    family: 'Family',
    group: 'Group',
    product: 'Product',
  },
  time: {
    year: 'Year',
    quarter: 'Quarter',
    month: 'Month',
    week: 'Week',
    day: 'Day',
    hour: 'Hour',
  },
};

export default {
  getDashboard,
  getActions,
  getActionDetail,
  acknowledgeAction,
  overrideAction,
  getDrillDown,
  drillDown,
  drillUp,
  ACTION_MODES,
  ACTION_CATEGORIES,
  HIERARCHY_LEVELS,
};
