/**
 * Games Slice
 * Phase 7 Sprint 1: Mobile Application
 */

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { apiClient } from '../../services/api';

interface Game {
  id: number;
  name: string;
  status: string;
  current_round: number;
  max_rounds: number;
  created_at: string;
  supply_chain_config: any;
}

interface GamesState {
  games: Game[];
  currentGame: Game | null;
  gameState: any | null;
  loading: boolean;
  error: string | null;
  page: number;
  totalPages: number;
}

const initialState: GamesState = {
  games: [],
  currentGame: null,
  gameState: null,
  loading: false,
  error: null,
  page: 1,
  totalPages: 1,
};

// Async thunks
export const fetchGames = createAsyncThunk(
  'games/fetchGames',
  async ({ page = 1, status }: { page?: number; status?: string } = {}) => {
    const response = await apiClient.getGames({ page, page_size: 20, status });
    return response.data;
  }
);

export const fetchGame = createAsyncThunk('games/fetchGame', async (id: number) => {
  const response = await apiClient.getGame(id);
  return response.data;
});

export const createGame = createAsyncThunk(
  'games/createGame',
  async (data: {
    name: string;
    supply_chain_config_id: number;
    max_rounds?: number;
    description?: string;
  }) => {
    const response = await apiClient.createGame(data);
    return response.data;
  }
);

export const startGame = createAsyncThunk('games/startGame', async (id: number) => {
  const response = await apiClient.startGame(id);
  return response.data;
});

export const playRound = createAsyncThunk(
  'games/playRound',
  async ({ id, orders }: { id: number; orders?: any }) => {
    const response = await apiClient.playRound(id, orders);
    return response.data;
  }
);

export const fetchGameState = createAsyncThunk(
  'games/fetchGameState',
  async (id: number) => {
    const response = await apiClient.getGameState(id);
    return response.data;
  }
);

// Slice
const gamesSlice = createSlice({
  name: 'games',
  initialState,
  reducers: {
    clearCurrentGame: (state) => {
      state.currentGame = null;
      state.gameState = null;
    },
    clearError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    // Fetch games
    builder
      .addCase(fetchGames.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchGames.fulfilled, (state, action) => {
        state.loading = false;
        state.games = action.payload.games || action.payload;
        state.page = action.payload.page || 1;
        state.totalPages = action.payload.total_pages || 1;
      })
      .addCase(fetchGames.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to fetch games';
      });

    // Fetch single game
    builder
      .addCase(fetchGame.pending, (state) => {
        state.loading = true;
      })
      .addCase(fetchGame.fulfilled, (state, action) => {
        state.loading = false;
        state.currentGame = action.payload;
      })
      .addCase(fetchGame.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to fetch game';
      });

    // Create game
    builder
      .addCase(createGame.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(createGame.fulfilled, (state, action) => {
        state.loading = false;
        state.games.unshift(action.payload);
        state.currentGame = action.payload;
      })
      .addCase(createGame.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to create game';
      });

    // Start game
    builder.addCase(startGame.fulfilled, (state, action) => {
      if (state.currentGame) {
        state.currentGame.status = 'active';
      }
      const game = state.games.find((g) => g.id === action.payload.id);
      if (game) {
        game.status = 'active';
      }
    });

    // Play round
    builder.addCase(playRound.fulfilled, (state, action) => {
      if (state.currentGame) {
        state.currentGame.current_round = action.payload.current_round;
      }
    });

    // Fetch game state
    builder
      .addCase(fetchGameState.pending, (state) => {
        state.loading = true;
      })
      .addCase(fetchGameState.fulfilled, (state, action) => {
        state.loading = false;
        state.gameState = action.payload;
      })
      .addCase(fetchGameState.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to fetch game state';
      });
  },
});

export const { clearCurrentGame, clearError } = gamesSlice.actions;
export default gamesSlice.reducer;
