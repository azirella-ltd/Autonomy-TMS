/**
 * Analytics Slice
 * Phase 7 Sprint 1: Mobile Application
 */

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { apiClient } from '../../services/api';

interface MonteCarloResult {
  scenario_id: number;
  percentile_10: number;
  percentile_50: number;
  percentile_90: number;
  mean: number;
  std_dev: number;
  outcomes: number[];
}

interface StochasticMetrics {
  total_cost: MonteCarloResult;
  service_level: MonteCarloResult;
  bullwhip_ratio: MonteCarloResult;
  inventory_variance: MonteCarloResult;
}

interface AdvancedMetrics {
  game_id: number;
  bullwhip_effect: number;
  service_level: number;
  avg_inventory: number;
  avg_backlog: number;
  total_cost: number;
  cost_breakdown: {
    holding_cost: number;
    backlog_cost: number;
    ordering_cost: number;
  };
  node_metrics: Array<{
    node_name: string;
    bullwhip_ratio: number;
    service_level: number;
    avg_inventory: number;
  }>;
}

interface AnalyticsState {
  advancedMetrics: AdvancedMetrics | null;
  stochasticMetrics: StochasticMetrics | null;
  monteCarloResults: any | null;
  loading: boolean;
  error: string | null;
  simulationProgress: {
    current: number;
    total: number;
    status: 'idle' | 'running' | 'completed' | 'failed';
  };
}

const initialState: AnalyticsState = {
  advancedMetrics: null,
  stochasticMetrics: null,
  monteCarloResults: null,
  loading: false,
  error: null,
  simulationProgress: {
    current: 0,
    total: 0,
    status: 'idle',
  },
};

// Async thunks
export const fetchAdvancedMetrics = createAsyncThunk(
  'analytics/fetchAdvancedMetrics',
  async (gameId: number) => {
    const response = await apiClient.getAdvancedMetrics(gameId);
    return response.data;
  }
);

export const fetchStochasticMetrics = createAsyncThunk(
  'analytics/fetchStochasticMetrics',
  async (gameId: number) => {
    const response = await apiClient.getStochasticMetrics(gameId);
    return response.data;
  }
);

export const runMonteCarloSimulation = createAsyncThunk(
  'analytics/runMonteCarloSimulation',
  async (params: {
    gameId: number;
    numSimulations: number;
    varianceLevel: number;
  }) => {
    const response = await apiClient.runMonteCarloSimulation(
      params.gameId,
      params.numSimulations,
      params.varianceLevel
    );
    return response.data;
  }
);

export const fetchGameAnalytics = createAsyncThunk(
  'analytics/fetchGameAnalytics',
  async (gameId: number) => {
    const response = await apiClient.getGameAnalytics(gameId);
    return response.data;
  }
);

// Slice
const analyticsSlice = createSlice({
  name: 'analytics',
  initialState,
  reducers: {
    clearAnalytics: (state) => {
      state.advancedMetrics = null;
      state.stochasticMetrics = null;
      state.monteCarloResults = null;
      state.error = null;
    },
    clearError: (state) => {
      state.error = null;
    },
    updateSimulationProgress: (state, action) => {
      state.simulationProgress = {
        ...state.simulationProgress,
        ...action.payload,
      };
    },
  },
  extraReducers: (builder) => {
    // Fetch advanced metrics
    builder
      .addCase(fetchAdvancedMetrics.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchAdvancedMetrics.fulfilled, (state, action) => {
        state.loading = false;
        state.advancedMetrics = action.payload;
      })
      .addCase(fetchAdvancedMetrics.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to fetch advanced metrics';
      });

    // Fetch stochastic metrics
    builder
      .addCase(fetchStochasticMetrics.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchStochasticMetrics.fulfilled, (state, action) => {
        state.loading = false;
        state.stochasticMetrics = action.payload;
      })
      .addCase(fetchStochasticMetrics.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to fetch stochastic metrics';
      });

    // Run Monte Carlo simulation
    builder
      .addCase(runMonteCarloSimulation.pending, (state) => {
        state.loading = true;
        state.error = null;
        state.simulationProgress = {
          current: 0,
          total: 0,
          status: 'running',
        };
      })
      .addCase(runMonteCarloSimulation.fulfilled, (state, action) => {
        state.loading = false;
        state.monteCarloResults = action.payload;
        state.simulationProgress = {
          ...state.simulationProgress,
          status: 'completed',
        };
      })
      .addCase(runMonteCarloSimulation.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to run Monte Carlo simulation';
        state.simulationProgress = {
          ...state.simulationProgress,
          status: 'failed',
        };
      });

    // Fetch game analytics
    builder
      .addCase(fetchGameAnalytics.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchGameAnalytics.fulfilled, (state, action) => {
        state.loading = false;
        // Store general analytics data
      })
      .addCase(fetchGameAnalytics.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to fetch game analytics';
      });
  },
});

export const { clearAnalytics, clearError, updateSimulationProgress } =
  analyticsSlice.actions;
export default analyticsSlice.reducer;
