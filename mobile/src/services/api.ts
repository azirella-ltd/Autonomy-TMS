/**
 * API Client Service
 * Phase 7 Sprint 1: Mobile Application
 *
 * Axios-based API client with request/response interceptors
 */

import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

// API Configuration
const API_BASE_URL = __DEV__
  ? Platform.OS === 'ios'
    ? 'http://localhost:8000'
    : 'http://10.0.2.2:8000'
  : 'https://api.beergame.com';

// Storage Keys
const TOKEN_KEY = 'auth_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

// Create axios instance
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request Interceptor - Add auth token
api.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const token = await AsyncStorage.getItem(TOKEN_KEY);

    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Add correlation ID for request tracking
    const correlationId = `mobile-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    if (config.headers) {
      config.headers['X-Correlation-ID'] = correlationId;
    }

    console.log(`[API] ${config.method?.toUpperCase()} ${config.url}`);
    return config;
  },
  (error: AxiosError) => {
    console.error('[API] Request Error:', error);
    return Promise.reject(error);
  }
);

// Response Interceptor - Handle errors and token refresh
api.interceptors.response.use(
  (response) => {
    console.log(`[API] Success: ${response.config.url}`);
    return response;
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // Handle 401 - Token expired
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshToken = await AsyncStorage.getItem(REFRESH_TOKEN_KEY);

        if (refreshToken) {
          // Attempt token refresh
          const response = await axios.post(`${API_BASE_URL}/api/v1/auth/refresh`, {
            refresh_token: refreshToken,
          });

          const { access_token, refresh_token: newRefreshToken } = response.data;

          // Save new tokens
          await AsyncStorage.setItem(TOKEN_KEY, access_token);
          await AsyncStorage.setItem(REFRESH_TOKEN_KEY, newRefreshToken);

          // Retry original request
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${access_token}`;
          }
          return api(originalRequest);
        }
      } catch (refreshError) {
        // Refresh failed - clear tokens and redirect to login
        await AsyncStorage.multiRemove([TOKEN_KEY, REFRESH_TOKEN_KEY]);
        console.error('[API] Token refresh failed:', refreshError);
        // Emit event for logout (handled by Redux)
        return Promise.reject(new Error('Session expired'));
      }
    }

    // Handle other errors
    const errorMessage = getErrorMessage(error);
    console.error('[API] Response Error:', errorMessage);

    return Promise.reject(error);
  }
);

// Helper function to extract error message
function getErrorMessage(error: AxiosError): string {
  if (error.response) {
    // Server responded with error
    const data = error.response.data as any;
    return data?.detail || data?.message || `Error ${error.response.status}`;
  } else if (error.request) {
    // No response received
    return 'Network error. Please check your connection.';
  } else {
    // Request setup error
    return error.message || 'An unexpected error occurred';
  }
}

// API Methods
export const apiClient = {
  // Authentication
  login: (email: string, password: string) =>
    api.post('/api/v1/auth/login', { username: email, password }),

  register: (data: { email: string; password: string; full_name: string }) =>
    api.post('/api/v1/auth/register', data),

  logout: () => api.post('/api/v1/auth/logout'),

  getCurrentUser: () => api.get('/api/v1/auth/me'),

  // Templates
  getTemplates: (params?: {
    page?: number;
    page_size?: number;
    query?: string;
    category?: string;
    industry?: string;
    difficulty?: string;
  }) => api.get('/api/v1/templates', { params }),

  getFeaturedTemplates: (limit: number = 5) =>
    api.get('/api/v1/templates/featured', { params: { limit } }),

  getTemplate: (id: number) => api.get(`/api/v1/templates/${id}`),

  useTemplate: (id: number) => api.post(`/api/v1/templates/${id}/use`),

  quickStart: (data: {
    industry: string;
    difficulty: string;
    num_players: number;
    features?: string[];
  }) => api.post('/api/v1/templates/quick-start', data),

  // Games
  getGames: (params?: { page?: number; page_size?: number; status?: string }) =>
    api.get('/api/v1/mixed-games', { params }),

  getGame: (id: number) => api.get(`/api/v1/mixed-games/${id}`),

  createGame: (data: {
    name: string;
    supply_chain_config_id: number;
    max_rounds?: number;
    description?: string;
  }) => api.post('/api/v1/mixed-games', data),

  startGame: (id: number) => api.post(`/api/v1/mixed-games/${id}/start`),

  playRound: (id: number, orders?: any) =>
    api.post(`/api/v1/mixed-games/${id}/play-round`, { orders }),

  getGameState: (id: number) => api.get(`/api/v1/mixed-games/${id}/state`),

  getGameHistory: (id: number) => api.get(`/api/v1/mixed-games/${id}/history`),

  // Supply Chain Configs
  getSupplyChainConfigs: () => api.get('/api/v1/supply-chain-configs'),

  getSupplyChainConfig: (id: number) => api.get(`/api/v1/supply-chain-configs/${id}`),

  // Analytics
  getStochasticPreview: (data: any) =>
    api.post('/api/v1/stochastic/preview', data),

  startMonteCarloSimulation: (data: {
    game_id: number;
    num_runs: number;
    seed?: number;
  }) => api.post('/api/v1/stochastic/analytics/monte-carlo/start', data),

  getMonteCarloStatus: (jobId: string) =>
    api.get(`/api/v1/stochastic/analytics/monte-carlo/${jobId}/status`),

  getMonteCarloResults: (jobId: string) =>
    api.get(`/api/v1/stochastic/analytics/monte-carlo/${jobId}/results`),

  // Health & Metrics
  getHealth: () => api.get('/api/v1/health/ready'),

  getMetrics: () => api.get('/api/v1/metrics/json'),

  // Push Notifications
  registerFCMToken: (token: string, platform: string) =>
    api.post('/api/v1/notifications/register', { fcm_token: token, platform }),

  unregisterFCMToken: (token: string) =>
    api.post('/api/v1/notifications/unregister', { fcm_token: token }),

  updateNotificationPreferences: (preferences: {
    game_updates?: boolean;
    round_completed?: boolean;
    your_turn?: boolean;
    marketing?: boolean;
  }) => api.put('/api/v1/notifications/preferences', preferences),

  getNotificationPreferences: () => api.get('/api/v1/notifications/preferences'),

  // Chat & A2A Collaboration
  getChatMessages: (gameId: number, params?: { since?: string }) =>
    api.get(`/api/v1/games/${gameId}/chat/messages`, { params }),

  sendChatMessage: (gameId: number, data: any) =>
    api.post(`/api/v1/games/${gameId}/chat/messages`, data),

  markMessagesAsRead: (gameId: number, messageIds: string[]) =>
    api.put(`/api/v1/games/${gameId}/chat/messages/read`, { messageIds }),

  requestAgentSuggestion: (gameId: number, context?: any) =>
    api.post(`/api/v1/games/${gameId}/chat/request-suggestion`, { context }),

  getAgentSuggestions: (gameId: number) =>
    api.get(`/api/v1/games/${gameId}/chat/suggestions`),

  acceptSuggestion: (gameId: number, suggestionId: string) =>
    api.put(`/api/v1/games/${gameId}/chat/suggestions/${suggestionId}/accept`),

  declineSuggestion: (gameId: number, suggestionId: string) =>
    api.put(`/api/v1/games/${gameId}/chat/suggestions/${suggestionId}/decline`),

  runWhatIfAnalysis: (gameId: number, data: { question: string; scenario: any }) =>
    api.post(`/api/v1/games/${gameId}/chat/what-if`, data),
};

// Token Management
export const tokenManager = {
  getToken: () => AsyncStorage.getItem(TOKEN_KEY),

  setToken: (token: string) => AsyncStorage.setItem(TOKEN_KEY, token),

  getRefreshToken: () => AsyncStorage.getItem(REFRESH_TOKEN_KEY),

  setRefreshToken: (token: string) =>
    AsyncStorage.setItem(REFRESH_TOKEN_KEY, token),

  clearTokens: () => AsyncStorage.multiRemove([TOKEN_KEY, REFRESH_TOKEN_KEY]),
};

export default api;
