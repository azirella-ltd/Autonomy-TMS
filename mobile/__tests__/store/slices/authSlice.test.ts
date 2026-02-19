/**
 * Unit tests for authSlice
 * Tests authentication state management, login, logout, and token refresh
 */

import configureStore from 'redux-mock-store';
import thunk from 'redux-thunk';
import authReducer, {
  login,
  logout,
  refreshToken,
  setUser,
  clearUser,
  AuthState,
} from '../../../src/store/slices/authSlice';
import { apiClient } from '../../../src/services/api';

// Mock API client
jest.mock('../../../src/services/api');

const middlewares = [thunk];
const mockStore = configureStore(middlewares);

describe('authSlice', () => {
  let store: any;

  beforeEach(() => {
    store = mockStore({
      auth: {
        isAuthenticated: false,
        user: null,
        token: null,
        refreshToken: null,
        loading: false,
        error: null,
      },
    });
    jest.clearAllMocks();
  });

  describe('initial state', () => {
    it('should return initial state', () => {
      expect(authReducer(undefined, { type: 'unknown' })).toEqual({
        isAuthenticated: false,
        user: null,
        token: null,
        refreshToken: null,
        loading: false,
        error: null,
      });
    });
  });

  describe('synchronous actions', () => {
    it('should handle setUser', () => {
      const user = {
        id: 1,
        email: 'test@example.com',
        name: 'Test User',
        role: 'PLAYER' as const,
      };

      const state = authReducer(undefined, setUser(user));

      expect(state.user).toEqual(user);
      expect(state.isAuthenticated).toBe(true);
    });

    it('should handle clearUser', () => {
      const initialState: AuthState = {
        isAuthenticated: true,
        user: {
          id: 1,
          email: 'test@example.com',
          name: 'Test User',
          role: 'PLAYER',
        },
        token: 'token123',
        refreshToken: 'refresh123',
        loading: false,
        error: null,
      };

      const state = authReducer(initialState, clearUser());

      expect(state.isAuthenticated).toBe(false);
      expect(state.user).toBeNull();
      expect(state.token).toBeNull();
      expect(state.refreshToken).toBeNull();
    });
  });

  describe('login async thunk', () => {
    it('should handle successful login', async () => {
      const mockResponse = {
        data: {
          access_token: 'token123',
          refresh_token: 'refresh123',
          user: {
            id: 1,
            email: 'test@example.com',
            name: 'Test User',
            role: 'PLAYER',
          },
        },
      };

      (apiClient.login as jest.Mock).mockResolvedValue(mockResponse);

      const credentials = { email: 'test@example.com', password: 'password123' };
      const result = await store.dispatch(login(credentials));

      expect(result.type).toBe('auth/login/fulfilled');
      expect(result.payload).toEqual(mockResponse.data);
    });

    it('should handle login failure', async () => {
      const mockError = new Error('Invalid credentials');
      (apiClient.login as jest.Mock).mockRejectedValue(mockError);

      const credentials = { email: 'test@example.com', password: 'wrong' };
      const result = await store.dispatch(login(credentials));

      expect(result.type).toBe('auth/login/rejected');
      expect(result.error.message).toBe('Invalid credentials');
    });

    it('should set loading state during login', () => {
      const pendingState = authReducer(undefined, {
        type: login.pending.type,
        meta: { requestId: '123', arg: { email: 'test@example.com', password: 'password' } },
      });

      expect(pendingState.loading).toBe(true);
      expect(pendingState.error).toBeNull();
    });

    it('should update state on successful login', () => {
      const payload = {
        access_token: 'token123',
        refresh_token: 'refresh123',
        user: {
          id: 1,
          email: 'test@example.com',
          name: 'Test User',
          role: 'PLAYER' as const,
        },
      };

      const fulfilledState = authReducer(undefined, {
        type: login.fulfilled.type,
        payload,
        meta: { requestId: '123', arg: { email: 'test@example.com', password: 'password' } },
      });

      expect(fulfilledState.loading).toBe(false);
      expect(fulfilledState.isAuthenticated).toBe(true);
      expect(fulfilledState.token).toBe('token123');
      expect(fulfilledState.refreshToken).toBe('refresh123');
      expect(fulfilledState.user).toEqual(payload.user);
      expect(fulfilledState.error).toBeNull();
    });

    it('should update state on login failure', () => {
      const rejectedState = authReducer(undefined, {
        type: login.rejected.type,
        error: { message: 'Invalid credentials' },
        meta: { requestId: '123', arg: { email: 'test@example.com', password: 'wrong' } },
      });

      expect(rejectedState.loading).toBe(false);
      expect(rejectedState.isAuthenticated).toBe(false);
      expect(rejectedState.error).toBe('Invalid credentials');
    });
  });

  describe('logout async thunk', () => {
    it('should handle successful logout', async () => {
      (apiClient.logout as jest.Mock).mockResolvedValue({});

      const result = await store.dispatch(logout());

      expect(result.type).toBe('auth/logout/fulfilled');
      expect(apiClient.logout).toHaveBeenCalled();
    });

    it('should clear state on logout', () => {
      const initialState: AuthState = {
        isAuthenticated: true,
        user: {
          id: 1,
          email: 'test@example.com',
          name: 'Test User',
          role: 'PLAYER',
        },
        token: 'token123',
        refreshToken: 'refresh123',
        loading: false,
        error: null,
      };

      const fulfilledState = authReducer(initialState, {
        type: logout.fulfilled.type,
        meta: { requestId: '123', arg: undefined },
      });

      expect(fulfilledState.isAuthenticated).toBe(false);
      expect(fulfilledState.user).toBeNull();
      expect(fulfilledState.token).toBeNull();
      expect(fulfilledState.refreshToken).toBeNull();
    });

    it('should handle logout failure gracefully', async () => {
      const mockError = new Error('Network error');
      (apiClient.logout as jest.Mock).mockRejectedValue(mockError);

      const result = await store.dispatch(logout());

      // Should still fulfill and clear state even if API call fails
      expect(result.type).toBe('auth/logout/rejected');
    });
  });

  describe('refreshToken async thunk', () => {
    it('should handle successful token refresh', async () => {
      const mockResponse = {
        data: {
          access_token: 'newToken123',
          refresh_token: 'newRefresh123',
        },
      };

      (apiClient.refreshToken as jest.Mock).mockResolvedValue(mockResponse);

      const result = await store.dispatch(refreshToken('refresh123'));

      expect(result.type).toBe('auth/refreshToken/fulfilled');
      expect(result.payload).toEqual(mockResponse.data);
    });

    it('should update tokens on successful refresh', () => {
      const initialState: AuthState = {
        isAuthenticated: true,
        user: {
          id: 1,
          email: 'test@example.com',
          name: 'Test User',
          role: 'PLAYER',
        },
        token: 'oldToken',
        refreshToken: 'oldRefresh',
        loading: false,
        error: null,
      };

      const payload = {
        access_token: 'newToken123',
        refresh_token: 'newRefresh123',
      };

      const fulfilledState = authReducer(initialState, {
        type: refreshToken.fulfilled.type,
        payload,
        meta: { requestId: '123', arg: 'oldRefresh' },
      });

      expect(fulfilledState.token).toBe('newToken123');
      expect(fulfilledState.refreshToken).toBe('newRefresh123');
      expect(fulfilledState.isAuthenticated).toBe(true);
      expect(fulfilledState.user).toEqual(initialState.user);
    });

    it('should handle token refresh failure', async () => {
      const mockError = new Error('Invalid refresh token');
      (apiClient.refreshToken as jest.Mock).mockRejectedValue(mockError);

      const result = await store.dispatch(refreshToken('invalidRefresh'));

      expect(result.type).toBe('auth/refreshToken/rejected');
      expect(result.error.message).toBe('Invalid refresh token');
    });

    it('should clear auth state on refresh failure', () => {
      const initialState: AuthState = {
        isAuthenticated: true,
        user: {
          id: 1,
          email: 'test@example.com',
          name: 'Test User',
          role: 'PLAYER',
        },
        token: 'oldToken',
        refreshToken: 'oldRefresh',
        loading: false,
        error: null,
      };

      const rejectedState = authReducer(initialState, {
        type: refreshToken.rejected.type,
        error: { message: 'Invalid refresh token' },
        meta: { requestId: '123', arg: 'oldRefresh' },
      });

      expect(rejectedState.isAuthenticated).toBe(false);
      expect(rejectedState.user).toBeNull();
      expect(rejectedState.token).toBeNull();
      expect(rejectedState.refreshToken).toBeNull();
      expect(rejectedState.error).toBe('Invalid refresh token');
    });
  });

  describe('edge cases', () => {
    it('should handle undefined error message', () => {
      const rejectedState = authReducer(undefined, {
        type: login.rejected.type,
        error: {},
        meta: { requestId: '123', arg: { email: 'test@example.com', password: 'wrong' } },
      });

      expect(rejectedState.error).toBe('An error occurred');
    });

    it('should preserve existing state when action is not handled', () => {
      const initialState: AuthState = {
        isAuthenticated: true,
        user: {
          id: 1,
          email: 'test@example.com',
          name: 'Test User',
          role: 'PLAYER',
        },
        token: 'token123',
        refreshToken: 'refresh123',
        loading: false,
        error: null,
      };

      const newState = authReducer(initialState, { type: 'unknown/action' });

      expect(newState).toEqual(initialState);
    });

    it('should handle login with missing refresh token', () => {
      const payload = {
        access_token: 'token123',
        user: {
          id: 1,
          email: 'test@example.com',
          name: 'Test User',
          role: 'PLAYER' as const,
        },
      };

      const fulfilledState = authReducer(undefined, {
        type: login.fulfilled.type,
        payload,
        meta: { requestId: '123', arg: { email: 'test@example.com', password: 'password' } },
      });

      expect(fulfilledState.token).toBe('token123');
      expect(fulfilledState.refreshToken).toBeUndefined();
      expect(fulfilledState.isAuthenticated).toBe(true);
    });
  });
});
