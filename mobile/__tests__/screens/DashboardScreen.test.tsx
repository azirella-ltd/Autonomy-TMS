/**
 * Unit tests for DashboardScreen
 * Tests dashboard rendering, stats, and quick actions
 */

import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { Provider } from 'react-redux';
import configureStore from 'redux-mock-store';
import thunk from 'redux-thunk';
import DashboardScreen from '../../src/screens/Dashboard/DashboardScreen';

const middlewares = [thunk];
const mockStore = configureStore(middlewares);

// Mock navigation
const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  ...jest.requireActual('@react-navigation/native'),
  useNavigation: () => ({
    navigate: mockNavigate,
  }),
  useFocusEffect: (callback: any) => {
    callback();
  },
}));

describe('DashboardScreen', () => {
  let store: any;

  const mockUser = {
    id: 1,
    email: 'test@example.com',
    name: 'Test User',
    role: 'PLAYER' as const,
  };

  const mockGames = [
    {
      id: 1,
      name: 'Active Game 1',
      status: 'active' as const,
      current_round: 5,
      max_rounds: 10,
      created_at: '2024-01-01T00:00:00Z',
      config: {
        id: 1,
        name: 'Default TBG',
        description: 'Standard Beer Game',
      },
      players: [],
    },
    {
      id: 2,
      name: 'Active Game 2',
      status: 'active' as const,
      current_round: 3,
      max_rounds: 10,
      created_at: '2024-01-02T00:00:00Z',
      config: {
        id: 2,
        name: 'Complex TBG',
        description: 'Complex Beer Game',
      },
      players: [],
    },
  ];

  beforeEach(() => {
    store = mockStore({
      auth: {
        isAuthenticated: true,
        user: mockUser,
        token: 'token123',
        refreshToken: 'refresh123',
        loading: false,
        error: null,
      },
      games: {
        games: mockGames,
        selectedGameId: null,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 2,
          hasMore: false,
        },
      },
      ui: {
        theme: 'light',
        networkStatus: 'online',
        toasts: [],
      },
    });
    store.dispatch = jest.fn();
    jest.clearAllMocks();
  });

  it('should render correctly', () => {
    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    expect(getByText('Welcome back, Test User!')).toBeTruthy();
    expect(getByText('Active Games')).toBeTruthy();
    expect(getByText('Quick Actions')).toBeTruthy();
  });

  it('should display user stats', () => {
    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    expect(getByText('2')).toBeTruthy(); // Active games count
    expect(getByText('Active Games')).toBeTruthy();
  });

  it('should display active games list', () => {
    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    expect(getByText('Active Game 1')).toBeTruthy();
    expect(getByText('Active Game 2')).toBeTruthy();
    expect(getByText('Round 5 of 10')).toBeTruthy();
    expect(getByText('Round 3 of 10')).toBeTruthy();
  });

  it('should navigate to game detail when game card is pressed', () => {
    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    const gameCard = getByText('Active Game 1');
    fireEvent.press(gameCard);

    expect(mockNavigate).toHaveBeenCalledWith('GameDetail', { gameId: 1 });
  });

  it('should display quick actions', () => {
    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    expect(getByText('New Game')).toBeTruthy();
    expect(getByText('Browse Templates')).toBeTruthy();
    expect(getByText('View Analytics')).toBeTruthy();
  });

  it('should navigate to create game screen', () => {
    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    const newGameButton = getByText('New Game');
    fireEvent.press(newGameButton);

    expect(mockNavigate).toHaveBeenCalledWith('CreateGame');
  });

  it('should navigate to template library', () => {
    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    const templatesButton = getByText('Browse Templates');
    fireEvent.press(templatesButton);

    expect(mockNavigate).toHaveBeenCalledWith('Templates');
  });

  it('should navigate to analytics screen', () => {
    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    const analyticsButton = getByText('View Analytics');
    fireEvent.press(analyticsButton);

    expect(mockNavigate).toHaveBeenCalledWith('Analytics');
  });

  it('should show empty state when no active games', () => {
    store = mockStore({
      auth: {
        isAuthenticated: true,
        user: mockUser,
        token: 'token123',
        refreshToken: 'refresh123',
        loading: false,
        error: null,
      },
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
      ui: {
        theme: 'light',
        networkStatus: 'online',
        toasts: [],
      },
    });

    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    expect(getByText('No active games')).toBeTruthy();
    expect(getByText('Create your first game to get started')).toBeTruthy();
  });

  it('should show loading state', () => {
    store = mockStore({
      auth: {
        isAuthenticated: true,
        user: mockUser,
        token: 'token123',
        refreshToken: 'refresh123',
        loading: false,
        error: null,
      },
      games: {
        games: [],
        selectedGameId: null,
        loading: true,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 0,
          hasMore: false,
        },
      },
      ui: {
        theme: 'light',
        networkStatus: 'online',
        toasts: [],
      },
    });

    const { getByTestId } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    expect(getByTestId('loading-spinner')).toBeTruthy();
  });

  it('should show error state', () => {
    store = mockStore({
      auth: {
        isAuthenticated: true,
        user: mockUser,
        token: 'token123',
        refreshToken: 'refresh123',
        loading: false,
        error: null,
      },
      games: {
        games: [],
        selectedGameId: null,
        loading: false,
        error: 'Failed to load games',
        pagination: {
          page: 1,
          pageSize: 20,
          total: 0,
          hasMore: false,
        },
      },
      ui: {
        theme: 'light',
        networkStatus: 'online',
        toasts: [],
      },
    });

    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    expect(getByText('Failed to load games')).toBeTruthy();
  });

  it('should support pull to refresh', async () => {
    const { getByTestId } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    const scrollView = getByTestId('games-list');
    fireEvent(scrollView, 'refresh');

    await waitFor(() => {
      expect(store.dispatch).toHaveBeenCalled();
    });
  });

  it('should show recent activity section', () => {
    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    expect(getByText('Recent Activity')).toBeTruthy();
  });

  it('should display notifications badge', () => {
    const { getByTestId } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    const notificationBadge = getByTestId('notification-badge');
    expect(notificationBadge).toBeTruthy();
  });

  it('should filter completed games', () => {
    const gamesWithCompleted = [
      ...mockGames,
      {
        id: 3,
        name: 'Completed Game',
        status: 'completed' as const,
        current_round: 10,
        max_rounds: 10,
        created_at: '2024-01-03T00:00:00Z',
        config: {
          id: 1,
          name: 'Default TBG',
          description: 'Standard Beer Game',
        },
        players: [],
      },
    ];

    store = mockStore({
      auth: {
        isAuthenticated: true,
        user: mockUser,
        token: 'token123',
        refreshToken: 'refresh123',
        loading: false,
        error: null,
      },
      games: {
        games: gamesWithCompleted,
        selectedGameId: null,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 3,
          hasMore: false,
        },
      },
      ui: {
        theme: 'light',
        networkStatus: 'online',
        toasts: [],
      },
    });

    const { getByText, queryByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    // Active games should be shown
    expect(getByText('Active Game 1')).toBeTruthy();
    expect(getByText('Active Game 2')).toBeTruthy();

    // Completed game should not be in active section
    expect(queryByText('Completed Game')).toBeNull();
  });

  it('should show game progress percentage', () => {
    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    expect(getByText('50%')).toBeTruthy(); // Game 1: 5/10 rounds
    expect(getByText('30%')).toBeTruthy(); // Game 2: 3/10 rounds
  });

  it('should handle game card long press for options', () => {
    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    const gameCard = getByText('Active Game 1');
    fireEvent(gameCard, 'longPress');

    expect(getByText('Leave Game')).toBeTruthy();
    expect(getByText('View Details')).toBeTruthy();
  });

  it('should display welcome message based on time of day', () => {
    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    // Mock current time to morning
    const now = new Date();
    const hour = now.getHours();

    if (hour < 12) {
      expect(getByText(/Good morning/i)).toBeTruthy();
    } else if (hour < 18) {
      expect(getByText(/Good afternoon/i)).toBeTruthy();
    } else {
      expect(getByText(/Good evening/i)).toBeTruthy();
    }
  });

  it('should show offline banner when offline', () => {
    store = mockStore({
      auth: {
        isAuthenticated: true,
        user: mockUser,
        token: 'token123',
        refreshToken: 'refresh123',
        loading: false,
        error: null,
      },
      games: {
        games: mockGames,
        selectedGameId: null,
        loading: false,
        error: null,
        pagination: {
          page: 1,
          pageSize: 20,
          total: 2,
          hasMore: false,
        },
      },
      ui: {
        theme: 'light',
        networkStatus: 'offline',
        toasts: [],
      },
    });

    const { getByText } = render(
      <Provider store={store}>
        <DashboardScreen />
      </Provider>
    );

    expect(getByText(/offline/i)).toBeTruthy();
  });
});
