import { renderHook, act } from '@testing-library/react';
import { AuthProvider, useAuth } from '../../contexts/AuthContext';
import simulationApi from '../../services/api';

// Mock the API module
jest.mock('../../services/api');

describe('AuthContext', () => {
  const mockUser = {
    id: 1,
    username: 'testuser',
    email: 'test@example.com',
    first_name: 'Test',
    last_name: 'User',
    roles: ['user'],
  };

  beforeEach(() => {
    // Clear all mocks before each test
    jest.clearAllMocks();
    
    // Mock localStorage
    Storage.prototype.setItem = jest.fn();
    Storage.prototype.removeItem = jest.fn();
  });

  it('should initialize with default values', () => {
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
    expect(result.current.loading).toBe(true);
    expect(result.current.error).toBeNull();
  });

  describe('login', () => {
    it('should successfully log in a user', async () => {
      // Mock successful API response
      simulationApi.login.mockResolvedValueOnce(mockUser);
      
      const { result, waitForNextUpdate } = renderHook(() => useAuth(), { wrapper: AuthProvider });
      
      // Initial state
      expect(result.current.loading).toBe(true);
      
      // Wait for initial auth check to complete
      await waitForNextUpdate();
      
      // Perform login
      await act(async () => {
        const loginResult = await result.current.login({
          email: 'test@example.com',
          password: 'password123',
        });
        
        expect(loginResult).toEqual({ success: true });
      });
      
      // Verify state after login
      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user).toEqual(mockUser);
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
      expect(simulationApi.login).toHaveBeenCalledWith({
        email: 'test@example.com',
        password: 'password123',
      });
    });

    it('should handle login failure', async () => {
      // Mock failed API response
      const errorMessage = 'Invalid credentials';
      simulationApi.login.mockRejectedValueOnce({
        response: { data: { detail: errorMessage } },
      });
      
      const { result, waitForNextUpdate } = renderHook(() => useAuth(), { wrapper: AuthProvider });
      
      // Wait for initial auth check to complete
      await waitForNextUpdate();
      
      // Perform login that will fail
      await act(async () => {
        const loginResult = await result.current.login({
          email: 'wrong@example.com',
          password: 'wrongpassword',
        });
        
        expect(loginResult).toEqual({
          success: false,
          error: errorMessage,
        });
      });
      
      // Verify state after failed login
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBeNull();
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBe(errorMessage);
    });
  });

  describe('logout', () => {
    it('should log out a user', async () => {
      // Mock initial auth state as logged in
      simulationApi.getCurrentUser.mockResolvedValueOnce(mockUser);
      simulationApi.logout.mockResolvedValueOnce({});
      
      const { result, waitForNextUpdate } = renderHook(() => useAuth(), { wrapper: AuthProvider });
      
      // Wait for initial auth check to complete
      await waitForNextUpdate();
      
      // Verify initial logged in state
      expect(result.current.isAuthenticated).toBe(true);
      
      // Perform logout
      await act(async () => {
        await result.current.logout();
      });
      
      // Verify state after logout
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBeNull();
      expect(localStorage.removeItem).toHaveBeenCalledWith('authState');
      expect(simulationApi.logout).toHaveBeenCalled();
    });
  });

  describe('refreshUser', () => {
    it('should refresh user data', async () => {
      // Mock initial auth state
      simulationApi.getCurrentUser
        .mockResolvedValueOnce(mockUser) // Initial auth check
        .mockResolvedValueOnce({ ...mockUser, first_name: 'Updated' }); // Refresh call
      
      const { result, waitForNextUpdate } = renderHook(() => useAuth(), { wrapper: AuthProvider });
      
      // Wait for initial auth check to complete
      await waitForNextUpdate();
      
      // Verify initial state
      expect(result.current.user.first_name).toBe('Test');
      
      // Perform refresh
      await act(async () => {
        const updatedUser = await result.current.refreshUser();
        expect(updatedUser.first_name).toBe('Updated');
      });
      
      // Verify state after refresh
      expect(result.current.user.first_name).toBe('Updated');
    });
  });
});
