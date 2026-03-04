import { api } from './api';

/**
 * Get all games for the current user
 * @returns {Promise<Array>} List of games with basic info
 */
export const getUserScenarios = async () => {
  try {
    const response = await api.get('/dashboard/user-games');
    return response.data;
  } catch (error) {
    console.error('Error fetching user games:', error);
    throw error;
  }
};

/**
 * Get human dashboard data
 * @param {number|null} gameId - Optional game ID to view specific game
 * @returns {Promise<Object>} Dashboard data including game info, metrics, and time series
 */
export const getHumanDashboard = async (gameId = null) => {
  try {
    const url = gameId
      ? `/dashboard/human-dashboard?scenario_id=${gameId}`
      : '/dashboard/human-dashboard';
    const response = await api.get(url);
    
    // Transform the response to match the expected format
    const formattedData = {
      ...response.data,
      metrics: {
        current_inventory: response.data.metrics.current_inventory,
        inventory_change: response.data.metrics.inventory_change,
        backlog: response.data.metrics.backlog,
        total_cost: response.data.metrics.total_cost,
        avg_weekly_cost: response.data.metrics.avg_weekly_cost,
        service_level: response.data.metrics.service_level,
        service_level_change: response.data.metrics.service_level_change,
      },
      time_series: response.data.time_series.map(point => ({
        week: point.week,
        inventory: point.inventory,
        order: point.order,
        cost: point.cost,
        backlog: point.backlog,
        demand: point.demand,
        supply: point.supply,
        reason: point.reason,
      }))
    };
    
    return formattedData;
  } catch (error) {
    console.error('Error fetching human dashboard:', error);
    throw error;
  }
};

/**
 * Format time series data for chart display
 * @param {Array} timeSeries - Array of TimeSeriesPoint objects from API
 * @param {string} role - ScenarioUser's role in the scenario
 * @returns {Array} Formatted data for chart
 */
export const formatChartData = (timeSeries, role) => {
  if (!timeSeries || !timeSeries.length) return [];
  
  return timeSeries.map(point => ({
    week: point.week,
    inventory: point.inventory,
    order: point.order,
    cost: point.cost,
    backlog: point.backlog,
    demand: role === 'RETAILER' || role === 'MANUFACTURER' || role === 'DISTRIBUTOR' ? point.demand : undefined,
    supply: role === 'SUPPLIER' || role === 'MANUFACTURER' || role === 'DISTRIBUTOR' ? point.supply : undefined,
    reason: point.reason,
  }));
};

