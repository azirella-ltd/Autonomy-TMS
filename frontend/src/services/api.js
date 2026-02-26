// /frontend/src/services/api.js
/**
 * API Service for Autonomy Supply Chain Platform
 *
 * Terminology (Feb 2026):
 * - Game -> Scenario (simulation scenario)
 * - ScenarioUser -> ScenarioUser (in code) / User (in UI)
 * - Round -> Period (time period)
 * - Gamification -> Simulation
 *
 * This module provides both new terminology and backward-compatible aliases.
 */
import axios from "axios";
import { API_BASE_URL } from "../config/api";
import { buildLoginRedirectPath } from "../utils/authUtils";

// Create a single axios instance for the app
const http = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // Required for cookies
  // Long-running scenario operations (start/stop/auto-advance) can exceed
  // 20s; allow up to 60s before surfacing a client timeout.
  timeout: 60000,
  headers: {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
  },
});

// Backward-compatible axios export for modules that import `{ api }`
export const api = http;

// Request interceptor: handle CSRF token and auth headers
http.interceptors.request.use(async (config) => {
  // Skip only for login and the token-fetch endpoint to avoid loops
  const isAuthRequest = ['/auth/login', '/auth/csrf-token'].some(path =>
    config.url?.includes(path)
  );

  if (!isAuthRequest) {
    // Get CSRF token from cookie or fetch a new one
    const csrfToken = getCookie('csrf_token') || await fetchCsrfToken();
    if (csrfToken) {
      config.headers['X-CSRF-Token'] = csrfToken;
    }
  }

  return config;
});

// Response interceptor: handle token refresh and auth errors
http.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config || {};
    const url = originalRequest.url || '';

    // Do not try to refresh for auth endpoints themselves to avoid loops
    const isAuthEndpoint = ['/auth/login', '/auth/refresh-token', '/auth/csrf-token'].some((p) => url.includes(p));

    // Handle 401 Unauthorized once per request (except auth endpoints)
    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      originalRequest._retry = true;
      try {
        await http.post('/auth/refresh-token');
        return http(originalRequest);
      } catch (refreshError) {
        // If refresh fails, go to login only once
        if (window.location.pathname !== '/login') {
          const loginPath = buildLoginRedirectPath({
            pathname: window.location.pathname,
            search: window.location.search,
          });
          window.location.replace(loginPath);
        }
        return Promise.reject(refreshError);
      }
    }

    // Handle CSRF token errors
    if (error.response?.status === 403 && error.response.data?.code === 'csrf_token_mismatch') {
      document.cookie = 'csrftoken=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;';
      return http(originalRequest);
    }

    return Promise.reject(error);
  }
);

// Helper function to get cookie by name
function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return null;
}

// Fetch a new CSRF token
async function fetchCsrfToken() {
  try {
    const response = await http.get('/auth/csrf-token');
    return response.data.csrf_token;
  } catch (error) {
    console.error('Failed to fetch CSRF token:', error);
    return null;
  }
}

// ----- High-level API wrappers -----
// Simulation API - canonical terminology (Feb 2026)
export const simulationApi = {
  async health() {
    const { data } = await http.get("/health");
    return data;
  },
  async getSystemConfig() {
    const { data } = await http.get('/config/system');
    return data;
  },
  async saveSystemConfig(cfg) {
    const { data } = await http.put('/config/system', cfg);
    return data;
  },
  async getSupplyChainConfigs() {
    const { data } = await http.get('/supply-chain-config/');
    return data;
  },
  /**
   * Get the root baseline config for the current user's organization.
   * Finds the config with parent_config_id=null and scenario_type=BASELINE.
   * Falls back to the first active config, then the first config.
   */
  async getRootSupplyChainConfig() {
    const { data } = await http.get('/supply-chain-config/');
    const items = data.items || data || [];
    if (items.length === 0) return null;
    // Prefer BASELINE with no parent (root of the tree)
    const root = items.find(c => !c.parent_config_id && c.scenario_type === 'BASELINE');
    if (root) return root;
    // Fallback: first active config
    const active = items.find(c => c.is_active);
    if (active) return active;
    // Last resort: first config
    return items[0];
  },

  // Model configuration
  async getModelConfig() {
    const { data } = await http.get('/config/model');
    return data;
  },
  async saveModelConfig(cfg) {
    const { data } = await http.put('/config/model', cfg);
    return data;
  },

  // ==========================================================================
  // Scenario Management (formerly "Games")
  // ==========================================================================
  async createScenario(scenarioData) {
    const { data } = await http.post('/mixed-scenarios/', scenarioData);
    return data;
  },
  async updateScenario(scenarioId, scenarioData) {
    const { data } = await http.put(`/mixed-scenarios/${scenarioId}`, scenarioData);
    return data;
  },
  async getScenarios() {
    const { data } = await http.get('/mixed-scenarios/');
    return data;
  },
  async deleteScenario(scenarioId) {
    const { data } = await http.delete(`/mixed-scenarios/${scenarioId}`);
    return data;
  },

  async startScenario(scenarioId, options = {}) {
    const payload = {};
    if (Object.prototype.hasOwnProperty.call(options, 'debugLogging')) {
      payload.debug_logging = Boolean(options.debugLogging);
    }

    let response;
    if (Object.keys(payload).length > 0) {
      response = await http.post(`/mixed-scenarios/${scenarioId}/start`, payload);
    } else {
      response = await http.post(`/mixed-scenarios/${scenarioId}/start`);
    }
    return response.data;
  },

  async stopScenario(scenarioId) {
    const { data } = await http.post(`/mixed-scenarios/${scenarioId}/stop`);
    return data;
  },

  async resetScenario(scenarioId) {
    const { data } = await http.post(`/mixed-scenarios/${scenarioId}/reset`);
    return data;
  },

  async nextPeriod(scenarioId) {
    const { data } = await http.post(`/mixed-scenarios/${scenarioId}/next-round`);
    return data;
  },

  async finishScenario(scenarioId) {
    const { data } = await http.post(`/mixed-scenarios/${scenarioId}/finish`);
    return data;
  },

  async getScenarioReport(scenarioId) {
    const { data } = await http.get(`/mixed-scenarios/${scenarioId}/report`);
    return data;
  },

  async getScenarioState(scenarioId) {
    const { data } = await http.get(`/mixed-scenarios/${scenarioId}/state`);
    return data;
  },

  async trainModel(payload) {
    const { data } = await http.post('/model/train', payload);
    return data;
  },
  async getJobStatus(jobId) {
    const { data } = await http.get(`/model/job/${jobId}/status`);
    return data;
  },
  async generateData(payload) {
    const { data } = await http.post('/model/generate-data', payload);
    return data;
  },
  async stopJob(jobId) {
    const { data } = await http.post(`/model/job/${jobId}/stop`);
    return data;
  },

  // Classic scenario endpoints (state, details, orders)
  async getScenario(scenarioId) {
    const { data } = await http.get(`/scenarios/${scenarioId}`);
    return data;
  },

  // ==========================================================================
  // User Management (formerly "Users")
  // ==========================================================================
  async getScenarioUsers(scenarioId) {
    const { data } = await http.get(`/scenarios/${scenarioId}/scenarioUsers`);
    return data;
  },
  async addScenarioUser(scenarioId, scenarioUser) {
    const { data } = await http.post(`/scenarios/${scenarioId}/scenarioUsers`, scenarioUser);
    return data;
  },

  async submitOrder(scenarioId, scenarioUserId, quantity, comment) {
    const { data } = await http.post(`/scenarios/${scenarioId}/scenarioUsers/${scenarioUserId}/orders`, { quantity, comment });
    return data;
  },

  // ==========================================================================
  // Period Management (formerly "Rounds")
  // ==========================================================================
  async getPeriods(scenarioId) {
    const { data } = await http.get(`/scenarios/${scenarioId}/rounds`);
    return data;
  },

  async getPeriodStatus(scenarioId) {
    const { data } = await http.get(`/scenarios/${scenarioId}/rounds/current/status`);
    return data;
  },

  // ==========================================================================
  // Authentication endpoints
  // ==========================================================================
  async login(credentials) {
    const form = new URLSearchParams();
    form.set('username', credentials.username);
    form.set('password', credentials.password);
    form.set('grant_type', 'password');

    try {
      const { data } = await http.post('/auth/login', form, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });

      if (data?.access_token) {
        return { success: true, user: data.user };
      }

      const detail = data?.detail;
      if (detail && typeof detail === 'object') {
        return {
          success: false,
          error: detail.message || 'Login failed',
          detail,
        };
      }

      return { success: false, error: detail || 'Login failed' };
    } catch (error) {
      const detail = error?.response?.data?.detail;

      if (detail && typeof detail === 'object') {
        return {
          success: false,
          error: detail.message || 'Login failed. Please try again.',
          detail,
        };
      }

      if (typeof detail === 'string') {
        return { success: false, error: detail };
      }

      return {
        success: false,
        error: error?.message || 'Login failed. Please try again.',
      };
    }
  },

  async logout() {
    try {
      await http.post('/auth/logout');
      return { success: true };
    } catch (error) {
      console.error('Logout error:', error);
      return { success: false, error: 'Failed to log out' };
    }
  },

  async getCurrentUser() {
    try {
      const { data } = await http.get('/auth/me');
      return data;
    } catch (error) {
      console.error('Failed to fetch current user:', error);
      throw error;
    }
  },

  async refreshToken() {
    try {
      const { data } = await http.post('/auth/refresh-token');
      return data;
    } catch (error) {
      console.error('Failed to refresh token:', error);
      throw error;
    }
  },

  async requestPasswordReset(email) {
    try {
      const { data } = await http.post('/auth/forgot-password', { email });
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.detail || 'Failed to request password reset',
      };
    }
  },

  async resetPassword(token, newPassword) {
    try {
      const { data } = await http.post('/auth/reset-password', {
        token,
        new_password: newPassword,
      });
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.detail || 'Failed to reset password',
      };
    }
  },

  async changePassword(currentPassword, newPassword) {
    try {
      const { data } = await http.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.detail || 'Failed to change password',
      };
    }
  },

  // MFA endpoints
  async setupMFA() {
    const { data } = await http.post('/auth/mfa/setup');
    return data;
  },

  async verifyMFA({ code, secret }) {
    const { data } = await http.post('/auth/mfa/verify', { code, secret });
    return data;
  },

  async disableMFA() {
    const { data } = await http.post('/auth/mfa/disable');
    return data;
  },

  // User management endpoints
  async register(userData) {
    try {
      const { data } = await http.post('/auth/register', userData);
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.detail || 'Registration failed',
      };
    }
  },

  async updateProfile(userData) {
    try {
      const { data } = await http.patch('/auth/me', userData);
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.detail || 'Failed to update profile',
      };
    }
  },

  // ==========================================================================
  // Analytics endpoints
  // ==========================================================================
  async getAggregationMetrics(scenarioId) {
    try {
      const { data } = await http.get(`/analytics/aggregation/${scenarioId}`);
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.detail || 'Failed to fetch aggregation metrics',
      };
    }
  },

  async getCapacityMetrics(scenarioId) {
    try {
      const { data } = await http.get(`/analytics/capacity/${scenarioId}`);
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.detail || 'Failed to fetch capacity metrics',
      };
    }
  },

  async getPolicyEffectiveness(configId, tenantId) {
    try {
      const { data } = await http.get(`/analytics/policies/${configId}`, {
        params: { tenant_id: tenantId }
      });
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.detail || 'Failed to fetch policy effectiveness',
      };
    }
  },

  async getComparativeAnalytics(scenarioId) {
    try {
      const { data } = await http.get(`/analytics/comparison/${scenarioId}`);
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.detail || 'Failed to fetch comparative analytics',
      };
    }
  },

  async getAnalyticsSummary(scenarioId) {
    try {
      const { data } = await http.get(`/analytics/summary/${scenarioId}`);
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.detail || 'Failed to fetch analytics summary',
      };
    }
  },

  // Analytics export endpoints
  exportAggregationCSV(scenarioId) {
    window.open(`/api/analytics/export/aggregation/${scenarioId}/csv`, '_blank');
  },

  exportCapacityCSV(scenarioId) {
    window.open(`/api/analytics/export/capacity/${scenarioId}/csv`, '_blank');
  },

  exportPoliciesCSV(configId, tenantId) {
    window.open(`/api/analytics/export/policies/${configId}/csv?tenant_id=${tenantId}`, '_blank');
  },

  exportComparisonCSV(scenarioId) {
    window.open(`/api/analytics/export/comparison/${scenarioId}/csv`, '_blank');
  },

  exportAllJSON(scenarioId) {
    window.open(`/api/analytics/export/${scenarioId}/json`, '_blank');
  },

  // ==========================================================================
  // LLM Integration (Chat, Suggestions, What-If Analysis)
  // ==========================================================================
  async requestAISuggestion(scenarioId, agentName, requestData = {}) {
    const response = await http.post(
      `/scenarios/${scenarioId}/chat/request-suggestion?agent_name=${agentName}`,
      requestData
    );
    return response;
  },

  async runWhatIfAnalysis(scenarioId, analysisData) {
    const response = await http.post(
      `/scenarios/${scenarioId}/chat/what-if`,
      analysisData
    );
    return response;
  },

  async getChatMessages(scenarioId, limit = 50) {
    const { data } = await http.get(`/scenarios/${scenarioId}/chat/messages?limit=${limit}`);
    return data;
  },

  async sendChatMessage(scenarioId, messageData) {
    const { data } = await http.post(`/scenarios/${scenarioId}/chat/messages`, messageData);
    return data;
  },

  async getAgentSuggestions(scenarioId, agentName = null) {
    const url = agentName
      ? `/scenarios/${scenarioId}/chat/suggestions?agent_name=${agentName}`
      : `/scenarios/${scenarioId}/chat/suggestions`;
    const { data } = await http.get(url);
    return data;
  },

  async acceptSuggestion(scenarioId, suggestionId) {
    const { data } = await http.post(
      `/scenarios/${scenarioId}/chat/suggestions/${suggestionId}/accept`
    );
    return data;
  },

  // ==========================================================================
  // Multi-Turn Conversations
  // ==========================================================================
  async sendConversationMessage(scenarioId, messageData) {
    const { data } = await http.post(
      `/conversation/scenarios/${scenarioId}/message`,
      messageData
    );
    return data;
  },

  async getConversationHistory(scenarioId, limit = 50) {
    const { data } = await http.get(
      `/conversation/scenarios/${scenarioId}/history?limit=${limit}`
    );
    return data;
  },

  async clearConversation(scenarioId) {
    const { data} = await http.delete(`/conversation/scenarios/${scenarioId}/clear`);
    return data;
  },

  async getConversationSummary(scenarioId) {
    const { data } = await http.get(`/conversation/scenarios/${scenarioId}/summary`);
    return data;
  },

  // ==========================================================================
  // Supply Chain Visibility
  // ==========================================================================
  async getSupplyChainHealth(scenarioId, periodNumber = null) {
    const params = periodNumber ? { round_number: periodNumber } : {};
    const { data } = await http.get(`/visibility/scenarios/${scenarioId}/health`, { params });
    return data;
  },

  async detectBottlenecks(scenarioId, periodNumber = null) {
    const params = periodNumber ? { round_number: periodNumber } : {};
    const { data } = await http.get(`/visibility/scenarios/${scenarioId}/bottlenecks`, { params });
    return data;
  },

  async measureBullwhip(scenarioId, windowSize = 10) {
    const { data } = await http.get(`/visibility/scenarios/${scenarioId}/bullwhip`, {
      params: { window_size: windowSize }
    });
    return data;
  },

  async setVisibilityPermissions(scenarioId, permissions) {
    const { data } = await http.post(`/visibility/scenarios/${scenarioId}/permissions`, permissions);
    return data;
  },

  async getVisibilityPermissions(scenarioId) {
    const { data } = await http.get(`/visibility/scenarios/${scenarioId}/permissions`);
    return data;
  },

  async createVisibilitySnapshot(scenarioId, periodNumber) {
    const { data } = await http.post(`/visibility/scenarios/${scenarioId}/snapshots`, null, {
      params: { round_number: periodNumber }
    });
    return data;
  },

  async getVisibilitySnapshots(scenarioId, limit = 20) {
    const { data } = await http.get(`/visibility/scenarios/${scenarioId}/snapshots`, {
      params: { limit }
    });
    return data;
  },

  // ==========================================================================
  // Pattern Analysis
  // ==========================================================================
  async getScenarioUserPatterns(scenarioId, scenarioUserId = null) {
    const url = scenarioUserId
      ? `/analytics/scenarios/${scenarioId}/scenarioUsers/${scenarioUserId}/patterns`
      : `/analytics/scenarios/${scenarioId}/patterns`;
    const { data } = await http.get(url);
    return data;
  },

  async getAIEffectiveness(scenarioId) {
    const { data } = await http.get(`/analytics/scenarios/${scenarioId}/ai-effectiveness`);
    return data;
  },

  async getSuggestionHistory(scenarioId, limit = 20) {
    const { data } = await http.get(`/analytics/scenarios/${scenarioId}/suggestion-history`, {
      params: { limit }
    });
    return data;
  },

  async getInsights(scenarioId, scenarioUserId = null) {
    const url = scenarioUserId
      ? `/analytics/scenarios/${scenarioId}/scenarioUsers/${scenarioUserId}/insights`
      : `/analytics/scenarios/${scenarioId}/insights`;
    const { data } = await http.get(url);
    return data;
  },

  // ==========================================================================
  // Negotiations
  // ==========================================================================
  async createNegotiation(scenarioId, proposal) {
    const { data } = await http.post(`/negotiations/scenarios/${scenarioId}/create`, proposal);
    return data;
  },

  async respondToNegotiation(negotiationId, response) {
    const { data } = await http.post(`/negotiations/${negotiationId}/respond`, response);
    return data;
  },

  async getScenarioUserNegotiations(scenarioId, statusFilter = null, limit = 20) {
    const params = { limit };
    if (statusFilter) params.status_filter = statusFilter;
    const { data } = await http.get(`/negotiations/scenarios/${scenarioId}/list`, { params });
    return data;
  },

  async getNegotiationMessages(negotiationId) {
    const { data } = await http.get(`/negotiations/${negotiationId}/messages`);
    return data;
  },

  async getNegotiationSuggestion(scenarioId, targetScenarioUserId) {
    const { data } = await http.get(`/negotiations/scenarios/${scenarioId}/suggest/${targetScenarioUserId}`);
    return data;
  },

  // ==========================================================================
  // Global Optimization
  // ==========================================================================
  async getGlobalOptimization(scenarioId, focusNodes = null) {
    const { data } = await http.post(`/optimization/scenarios/${scenarioId}/global`, {
      focus_nodes: focusNodes
    });
    return data;
  },

  // ==========================================================================
  // Simulation System (formerly "Gamification")
  // ==========================================================================

  // ScenarioUser Stats (formerly ScenarioUser Stats)
  async getScenarioUserStats(scenarioUserId) {
    const { data } = await http.get(`/gamification/scenarioUsers/${scenarioUserId}/stats`);
    return data;
  },

  async getScenarioUserProgress(scenarioUserId) {
    const { data } = await http.get(`/gamification/scenarioUsers/${scenarioUserId}/progress`);
    return data;
  },

  async updateStatsAfterScenario(scenarioUserId, scenarioId, won) {
    const { data } = await http.post(`/gamification/scenarioUsers/${scenarioUserId}/scenarios/${scenarioId}/complete?won=${won}`);
    return data;
  },

  // Achievements
  async getAllAchievements(activeOnly = true) {
    const { data } = await http.get(`/gamification/achievements?active_only=${activeOnly}`);
    return data;
  },

  async getAchievement(achievementId) {
    const { data } = await http.get(`/gamification/achievements/${achievementId}`);
    return data;
  },

  async checkScenarioUserAchievements(scenarioUserId, scenarioId = null) {
    const url = scenarioId
      ? `/gamification/scenarioUsers/${scenarioUserId}/check-achievements?scenario_id=${scenarioId}`
      : `/gamification/scenarioUsers/${scenarioUserId}/check-achievements`;
    const { data } = await http.post(url);
    return data;
  },

  async getScenarioUserAchievements(scenarioUserId) {
    const { data } = await http.get(`/gamification/scenarioUsers/${scenarioUserId}/achievements`);
    return data;
  },

  // Leaderboards
  async getAllLeaderboards(activeOnly = true) {
    const { data } = await http.get(`/gamification/leaderboards?active_only=${activeOnly}`);
    return data;
  },

  async getLeaderboard(leaderboardId, limit = 50, scenarioUserId = null) {
    const url = scenarioUserId
      ? `/gamification/leaderboards/${leaderboardId}?limit=${limit}&scenario_user_id=${scenarioUserId}`
      : `/gamification/leaderboards/${leaderboardId}?limit=${limit}`;
    const { data } = await http.get(url);
    return data;
  },

  // Notifications
  async getScenarioUserNotifications(scenarioUserId, limit = 10) {
    const { data } = await http.get(`/gamification/scenarioUsers/${scenarioUserId}/notifications?limit=${limit}`);
    return data;
  },

  async markNotificationRead(notificationId) {
    await http.post(`/gamification/notifications/${notificationId}/read`);
  },

  async markNotificationShown(notificationId) {
    await http.post(`/gamification/notifications/${notificationId}/shown`);
  },

  // Badges
  async getScenarioUserBadges(scenarioUserId) {
    const { data} = await http.get(`/gamification/scenarioUsers/${scenarioUserId}/badges`);
    return data;
  },

  // ==========================================================================
  // Reporting & Analytics
  // ==========================================================================
  async getScenarioReportDetails(scenarioId) {
    const { data } = await http.get(`/reports/scenarios/${scenarioId}`);
    return data;
  },

  async exportScenario(scenarioId, format = 'csv', includePeriods = true) {
    const response = await http.get(
      `/reports/scenarios/${scenarioId}/export?format=${format}&include_rounds=${includePeriods}`,
      { responseType: 'blob' }
    );
    return response.data;
  },

  async getScenarioUserTrends(scenarioUserId, metric = 'cost', lookback = 10) {
    const { data } = await http.get(
      `/reports/trends/${scenarioUserId}?metric=${metric}&lookback=${lookback}`
    );
    return data;
  },

  async compareScenarios(scenarioIds, metrics = null) {
    let url = `/reports/comparisons?${scenarioIds.map(id => `scenario_ids=${id}`).join('&')}`;
    if (metrics && metrics.length > 0) {
      url += `&${metrics.map(m => `metrics=${m}`).join('&')}`;
    }
    const { data } = await http.get(url);
    return data;
  },

  async getScenarioUserAnalyticsSummary(scenarioUserId) {
    const { data } = await http.get(`/reports/analytics/summary/${scenarioUserId}`);
    return data;
  },

  // ==========================================================================
  // ATP/CTP Probabilistic endpoints
  // ==========================================================================
  async getATP(scenarioId, scenarioUserId) {
    const { data } = await http.get(`/mixed-scenarios/${scenarioId}/atp/${scenarioUserId}`);
    return data;
  },

  async getATPProbabilistic(scenarioId, scenarioUserId, nSimulations = 100, includeSafetyStock = true) {
    const { data } = await http.get(
      `/mixed-scenarios/${scenarioId}/atp-probabilistic/${scenarioUserId}`,
      {
        params: {
          n_simulations: nSimulations,
          include_safety_stock: includeSafetyStock,
        }
      }
    );
    return data;
  },

  async getCTP(scenarioId, scenarioUserId, productId) {
    const { data } = await http.get(
      `/mixed-scenarios/${scenarioId}/ctp/${scenarioUserId}`,
      { params: { product_id: productId } }
    );
    return data;
  },

  async getCTPProbabilistic(scenarioId, scenarioUserId, productId, nSimulations = 100) {
    const { data } = await http.get(
      `/mixed-scenarios/${scenarioId}/ctp-probabilistic/${scenarioUserId}`,
      {
        params: {
          product_id: productId,
          n_simulations: nSimulations,
        }
      }
    );
    return data;
  },

  async getPipelineVisualization(scenarioId, scenarioUserId, nSimulations = 100) {
    const { data } = await http.get(
      `/mixed-scenarios/${scenarioId}/pipeline-visualization/${scenarioUserId}`,
      { params: { n_simulations: nSimulations } }
    );
    return data;
  },

  async getATPHistory(scenarioId, scenarioUserId, limit = 20) {
    const { data } = await http.get(
      `/mixed-scenarios/${scenarioId}/atp-history/${scenarioUserId}`,
      { params: { limit } }
    );
    return data;
  },

  async getATPProjection(scenarioId, scenarioUserId, periods = 8) {
    const { data } = await http.get(
      `/mixed-scenarios/${scenarioId}/atp-projection/${scenarioUserId}`,
      { params: { periods } }
    );
    return data;
  },

  async allocateATP(scenarioId, scenarioUserId, demands, allocationMethod = 'proportional') {
    const { data } = await http.post(
      `/mixed-scenarios/${scenarioId}/allocate-atp`,
      {
        scenario_user_id: scenarioUserId,
        demands,
        allocation_method: allocationMethod,
      }
    );
    return data;
  },

  // ==========================================================================
  // Conformal Prediction Endpoints
  // ==========================================================================
  async getConformalATP(scenarioId, scenarioUserId, coverage = 0.90, method = 'adaptive') {
    const { data } = await http.get(
      `/mixed-scenarios/${scenarioId}/atp-conformal/${scenarioUserId}`,
      { params: { coverage, method } }
    );
    return data;
  },

  async calibrateConformalATP(scenarioId, scenarioUserId, predictions, actuals, coverage = 0.90, method = 'adaptive') {
    const { data } = await http.post(
      `/mixed-scenarios/${scenarioId}/atp-conformal/${scenarioUserId}/calibrate`,
      { predictions, actuals },
      { params: { coverage, method } }
    );
    return data;
  },

  async getConformalDemand(scenarioId, scenarioUserId, horizon = 1, coverage = 0.90) {
    const { data } = await http.get(
      `/mixed-scenarios/${scenarioId}/demand-conformal/${scenarioUserId}`,
      { params: { horizon, coverage } }
    );
    return data;
  },

  async getConformalLeadTime(scenarioId, scenarioUserId, coverage = 0.90) {
    const { data } = await http.get(
      `/mixed-scenarios/${scenarioId}/lead-time-conformal/${scenarioUserId}`,
      { params: { coverage } }
    );
    return data;
  },
};

// =============================================================================
// Collaboration Scenarios (Agentic Authorization Protocol)
// =============================================================================

export const collaborationApi = {
  async getScenarios(tenantId, { level, status } = {}) {
    const params = new URLSearchParams();
    if (tenantId) params.append('tenant_id', tenantId);
    if (level) params.append('level', level);
    if (status) params.append('status', status);
    const { data } = await http.get(`/v1/collaboration/scenarios?${params.toString()}`);
    return data;
  },

  async getScenario(scenarioCode) {
    const { data } = await http.get(`/v1/collaboration/scenarios/${scenarioCode}`);
    return data;
  },
};

// =============================================================================
// Backward Compatibility Aliases (DEPRECATED - use new terminology)
// =============================================================================

// Scenario aliases (Game -> Scenario)
simulationApi.getGames = simulationApi.getScenarios;
simulationApi.createGame = simulationApi.createScenario;
simulationApi.updateGame = simulationApi.updateScenario;
simulationApi.deleteGame = simulationApi.deleteScenario;
simulationApi.startGame = simulationApi.startScenario;
simulationApi.stopGame = simulationApi.stopScenario;
simulationApi.resetGame = simulationApi.resetScenario;
simulationApi.finishGame = simulationApi.finishScenario;
simulationApi.getGameState = simulationApi.getScenarioState;
simulationApi.getReport = simulationApi.getScenarioReport;
simulationApi.getGame = simulationApi.getScenario;

// Period aliases (Round -> Period)
simulationApi.nextRound = simulationApi.nextPeriod;
simulationApi.getRounds = simulationApi.getPeriods;
simulationApi.getRoundStatus = simulationApi.getPeriodStatus;

// ScenarioUser aliases (ScenarioUser -> ScenarioUser)
simulationApi.getScenarioUsers = simulationApi.getScenarioUsers;
// Backward-compatible alias (player -> scenarioUser)
simulationApi.addPlayer = simulationApi.addScenarioUser;
simulationApi.getScenarioUserStats = simulationApi.getScenarioUserStats;
simulationApi.getPlayerProgress = simulationApi.getScenarioUserProgress;
simulationApi.getPlayerNegotiations = simulationApi.getScenarioUserNegotiations;

// Backward-compatible named export
export const mixedGameApi = simulationApi;

export default simulationApi;
