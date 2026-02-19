/**
 * Unit tests for gamesSlice
 * Tests game management, creation, fetching, and real-time updates
 */

import configureStore from 'redux-mock-store';
import thunk from 'redux-thunk';
import gamesReducer, {
  fetchGames,
  fetchGameById,
  createGame,
  joinGame,
  leaveGame,
  updateGameState,
  addGame,
  updateGame,
  removeGame,
  setSelectedGameId,
  GamesState,
  Game,
} from '../../../src/store/slices/gamesSlice';
import { apiClient } from '../../../src/services/api';

// Mock API client
jest.mock('../../../src/services/api');

const middlewares = [thunk];
const mockStore = configureStore(middlewares);

describe('gamesSlice', () => {
  let store: any;

  const mockGame: Game = {
    id: 1,
    name: 'Test Game',
    status: 'active',
    current_round: 3,
    max_rounds: 10,
    created_at: '2024-01-01T00:00:00Z',
    config: {
      id: 1,
      name: 'Default TBG',
      description: 'Standard Beer Game',
    },
    players: [
      {
        id: 1,
        user_id: 1,
        node_name: 'Retailer',
        is_ai: false,
      },
      {
        id: 2,
        user_id: null,
        node_name: 'Wholesaler',
        is_ai: true,
      },
    ],
  };

  beforeEach(() => {
    store = mockStore({
      games: {
        games: [],
        selectedGameId: null,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 0,
          hasMore: false,
        },
      },
    });
    jest.clearAllMocks();
  });

  describe('initial state', () => {
    it('should return initial state', () => {
      expect(gamesReducer(undefined, { type: 'unknown' })).toEqual({
        games: [],
        selectedGameId: null,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 0,
          hasMore: false,
        },
      });
    });
  });

  describe('synchronous actions', () => {
    it('should handle addGame', () => {
      const state = gamesReducer(undefined, addGame(mockGame));

      expect(state.games).toHaveLength(1);
      expect(state.games[0]).toEqual(mockGame);
    });

    it('should handle updateGame', () => {
      const initialState: GamesState = {
        games: [mockGame],
        selectedGameId: null,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 1,
          hasMore: false,
        },
      };

      const updatedGame = { ...mockGame, current_round: 5, status: 'completed' as const };
      const state = gamesReducer(initialState, updateGame(updatedGame));

      expect(state.games[0].current_round).toBe(5);
      expect(state.games[0].status).toBe('completed');
    });

    it('should handle removeGame', () => {
      const initialState: GamesState = {
        games: [mockGame],
        selectedGameId: 1,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 1,
          hasMore: false,
        },
      };

      const state = gamesReducer(initialState, removeGame(1));

      expect(state.games).toHaveLength(0);
      expect(state.selectedGameId).toBeNull();
    });

    it('should handle setSelectedGameId', () => {
      const state = gamesReducer(undefined, setSelectedGameId(1));

      expect(state.selectedGameId).toBe(1);
    });

    it('should handle updateGameState', () => {
      const initialState: GamesState = {
        games: [mockGame],
        selectedGameId: null,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 1,
          hasMore: false,
        },
      };

      const update = {
        gameId: 1,
        current_round: 6,
        status: 'active' as const,
      };

      const state = gamesReducer(initialState, updateGameState(update));

      expect(state.games[0].current_round).toBe(6);
      expect(state.games[0].status).toBe('active');
    });

    it('should not update non-existent game', () => {
      const initialState: GamesState = {
        games: [mockGame],
        selectedGameId: null,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 1,
          hasMore: false,
        },
      };

      const update = {
        gameId: 999,
        current_round: 6,
      };

      const state = gamesReducer(initialState, updateGameState(update));

      expect(state.games[0].current_round).toBe(3); // Unchanged
    });
  });

  describe('fetchGames async thunk', () => {
    it('should handle successful fetch', async () => {
      const mockResponse = {
        data: {
          games: [mockGame],
          pagination: {
            page: 1,
            pageSize: 20,
            total: 1,
            hasMore: false,
          },
        },
      };

      (apiClient.getGames as jest.Mock).mockResolvedValue(mockResponse);

      const result = await store.dispatch(fetchGames({ page: 1 }));

      expect(result.type).toBe('games/fetchGames/fulfilled');
      expect(result.payload).toEqual(mockResponse.data);
    });

    it('should handle fetch failure', async () => {
      const mockError = new Error('Network error');
      (apiClient.getGames as jest.Mock).mockRejectedValue(mockError);

      const result = await store.dispatch(fetchGames({ page: 1 }));

      expect(result.type).toBe('games/fetchGames/rejected');
      expect(result.error.message).toBe('Network error');
    });

    it('should set loading state during fetch', () => {
      const pendingState = gamesReducer(undefined, {
        type: fetchGames.pending.type,
        meta: { requestId: '123', arg: { page: 1 } },
      });

      expect(pendingState.loading).toBe(true);
      expect(pendingState.error).toBeNull();
    });

    it('should update state on successful fetch', () => {
      const payload = {
        games: [mockGame],
        pagination: {
          page: 1,
          pageSize: 20,
          total: 1,
          hasMore: false,
        },
      };

      const fulfilledState = gamesReducer(undefined, {
        type: fetchGames.fulfilled.type,
        payload,
        meta: { requestId: '123', arg: { page: 1 } },
      });

      expect(fulfilledState.loading).toBe(false);
      expect(fulfilledState.games).toEqual([mockGame]);
      expect(fulfilledState.pagination).toEqual(payload.pagination);
      expect(fulfilledState.error).toBeNull();
    });

    it('should append games on page > 1', () => {
      const initialState: GamesState = {
        games: [mockGame],
        selectedGameId: null,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 2,
          hasMore: true,
        },
      };

      const newGame: Game = {
        ...mockGame,
        id: 2,
        name: 'Second Game',
      };

      const payload = {
        games: [newGame],
        pagination: {
          page: 2,
          pageSize: 20,
          total: 2,
          hasMore: false,
        },
      };

      const fulfilledState = gamesReducer(initialState, {
        type: fetchGames.fulfilled.type,
        payload,
        meta: { requestId: '123', arg: { page: 2 } },
      });

      expect(fulfilledState.games).toHaveLength(2);
      expect(fulfilledState.games[1]).toEqual(newGame);
    });
  });

  describe('fetchGameById async thunk', () => {
    it('should handle successful fetch', async () => {
      const mockResponse = {
        data: mockGame,
      };

      (apiClient.getGameById as jest.Mock).mockResolvedValue(mockResponse);

      const result = await store.dispatch(fetchGameById(1));

      expect(result.type).toBe('games/fetchGameById/fulfilled');
      expect(result.payload).toEqual(mockGame);
    });

    it('should add game if not in list', () => {
      const fulfilledState = gamesReducer(undefined, {
        type: fetchGameById.fulfilled.type,
        payload: mockGame,
        meta: { requestId: '123', arg: 1 },
      });

      expect(fulfilledState.games).toHaveLength(1);
      expect(fulfilledState.games[0]).toEqual(mockGame);
    });

    it('should update game if already in list', () => {
      const initialState: GamesState = {
        games: [mockGame],
        selectedGameId: null,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 1,
          hasMore: false,
        },
      };

      const updatedGame = { ...mockGame, current_round: 7 };

      const fulfilledState = gamesReducer(initialState, {
        type: fetchGameById.fulfilled.type,
        payload: updatedGame,
        meta: { requestId: '123', arg: 1 },
      });

      expect(fulfilledState.games).toHaveLength(1);
      expect(fulfilledState.games[0].current_round).toBe(7);
    });
  });

  describe('createGame async thunk', () => {
    it('should handle successful creation', async () => {
      const mockResponse = {
        data: mockGame,
      };

      (apiClient.createGame as jest.Mock).mockResolvedValue(mockResponse);

      const gameData = {
        name: 'Test Game',
        supply_chain_config_id: 1,
        max_rounds: 10,
        players: [],
      };

      const result = await store.dispatch(createGame(gameData));

      expect(result.type).toBe('games/createGame/fulfilled');
      expect(result.payload).toEqual(mockGame);
    });

    it('should add created game to list', () => {
      const fulfilledState = gamesReducer(undefined, {
        type: createGame.fulfilled.type,
        payload: mockGame,
        meta: { requestId: '123', arg: {} },
      });

      expect(fulfilledState.games).toHaveLength(1);
      expect(fulfilledState.games[0]).toEqual(mockGame);
      expect(fulfilledState.loading).toBe(false);
    });

    it('should handle creation failure', async () => {
      const mockError = new Error('Validation error');
      (apiClient.createGame as jest.Mock).mockRejectedValue(mockError);

      const result = await store.dispatch(createGame({} as any));

      expect(result.type).toBe('games/createGame/rejected');
      expect(result.error.message).toBe('Validation error');
    });
  });

  describe('joinGame async thunk', () => {
    it('should handle successful join', async () => {
      const mockResponse = {
        data: mockGame,
      };

      (apiClient.joinGame as jest.Mock).mockResolvedValue(mockResponse);

      const result = await store.dispatch(joinGame({ gameId: 1, nodeName: 'Retailer' }));

      expect(result.type).toBe('games/joinGame/fulfilled');
      expect(result.payload).toEqual(mockGame);
    });

    it('should update game after join', () => {
      const initialState: GamesState = {
        games: [mockGame],
        selectedGameId: null,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 1,
          hasMore: false,
        },
      };

      const updatedGame = {
        ...mockGame,
        players: [
          ...mockGame.players,
          {
            id: 3,
            user_id: 2,
            node_name: 'Distributor',
            is_ai: false,
          },
        ],
      };

      const fulfilledState = gamesReducer(initialState, {
        type: joinGame.fulfilled.type,
        payload: updatedGame,
        meta: { requestId: '123', arg: { gameId: 1, nodeName: 'Distributor' } },
      });

      expect(fulfilledState.games[0].players).toHaveLength(3);
    });
  });

  describe('leaveGame async thunk', () => {
    it('should handle successful leave', async () => {
      (apiClient.leaveGame as jest.Mock).mockResolvedValue({});

      const result = await store.dispatch(leaveGame(1));

      expect(result.type).toBe('games/leaveGame/fulfilled');
      expect(apiClient.leaveGame).toHaveBeenCalledWith(1);
    });

    it('should remove game from list after leave', () => {
      const initialState: GamesState = {
        games: [mockGame],
        selectedGameId: 1,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 1,
          hasMore: false,
        },
      };

      const fulfilledState = gamesReducer(initialState, {
        type: leaveGame.fulfilled.type,
        meta: { requestId: '123', arg: 1 },
      });

      expect(fulfilledState.games).toHaveLength(0);
      expect(fulfilledState.selectedGameId).toBeNull();
    });
  });

  describe('edge cases', () => {
    it('should handle undefined error message', () => {
      const rejectedState = gamesReducer(undefined, {
        type: fetchGames.rejected.type,
        error: {},
        meta: { requestId: '123', arg: { page: 1 } },
      });

      expect(rejectedState.error).toBe('An error occurred');
    });

    it('should prevent duplicate games', () => {
      const initialState: GamesState = {
        games: [mockGame],
        selectedGameId: null,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 1,
          hasMore: false,
        },
      };

      const state = gamesReducer(initialState, addGame(mockGame));

      expect(state.games).toHaveLength(1);
    });

    it('should handle removing selected game', () => {
      const initialState: GamesState = {
        games: [mockGame],
        selectedGameId: 1,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 1,
          hasMore: false,
        },
      };

      const state = gamesReducer(initialState, removeGame(1));

      expect(state.selectedGameId).toBeNull();
    });

    it('should handle empty games list', () => {
      const state = gamesReducer(undefined, { type: 'unknown' });

      expect(state.games).toEqual([]);
      expect(state.selectedGameId).toBeNull();
    });
  });
});
