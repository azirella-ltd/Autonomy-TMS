// /frontend/src/contexts/AuthContext.js
import { createContext, useContext, useEffect, useMemo, useState, useCallback, useRef } from 'react';
import simulationApi from '../services/api';
import { toast } from 'react-toastify';
import {
  isSystemAdmin,
  isTenantAdmin as isTenantAdminUtil,
  getUserType,
} from '../utils/authUtils';

// Warning shown 60 seconds before logout
const WARNING_LEAD_SECONDS = 60;

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showTimeoutWarning, setShowTimeoutWarning] = useState(false);
  const [timeLeft, setTimeLeft] = useState(0);
  const [provisioningStatus, setProvisioningStatus] = useState(null);
  const [provisioningStep, setProvisioningStep] = useState(null);
  const [sessionTimeoutMinutes, setSessionTimeoutMinutes] = useState(() => {
    const stored = localStorage.getItem('sessionTimeoutMinutes');
    return stored ? parseInt(stored, 10) || 5 : 5;
  });

  const logoutTimer = useRef(null);
  const warningTimer = useRef(null);
  const countdownInterval = useRef(null);
  const activityEvents = useMemo(() => ['mousedown', 'keydown', 'scroll', 'touchstart'], []);

  const logout = useCallback(async () => {
    try {
      setLoading(true);
      await simulationApi.logout();
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      if (logoutTimer.current) clearTimeout(logoutTimer.current);
      if (warningTimer.current) clearTimeout(warningTimer.current);
      if (countdownInterval.current) clearInterval(countdownInterval.current);
      setUser(null);
      setIsAuthenticated(false);
      setShowTimeoutWarning(false);
      setSessionTimeoutMinutes(5);
      setProvisioningStatus(null);
      setProvisioningStep(null);
      setLoading(false);
      localStorage.removeItem('authState');
      localStorage.removeItem('sessionTimeoutMinutes');
    }
  }, []);

  // Handle user activity - reset timers
  const resetTimers = useCallback(() => {
    if (logoutTimer.current) clearTimeout(logoutTimer.current);
    if (warningTimer.current) clearTimeout(warningTimer.current);
    if (countdownInterval.current) clearInterval(countdownInterval.current);
    setShowTimeoutWarning(false);

    if (isAuthenticated) {
      const timeoutMs = sessionTimeoutMinutes * 60 * 1000;
      const warningMs = WARNING_LEAD_SECONDS * 1000;
      // Only show warning if timeout is long enough (> 2 minutes)
      const showWarning = timeoutMs > warningMs * 2;

      if (showWarning) {
        // Show warning modal 60 seconds before logout
        warningTimer.current = setTimeout(() => {
          setShowTimeoutWarning(true);
          setTimeLeft(WARNING_LEAD_SECONDS);
          // Tick down every second for the countdown display
          countdownInterval.current = setInterval(() => {
            setTimeLeft((prev) => (prev > 0 ? prev - 1 : 0));
          }, 1000);
        }, timeoutMs - warningMs);
      }

      // Set logout timer
      logoutTimer.current = setTimeout(() => {
        if (countdownInterval.current) clearInterval(countdownInterval.current);
        logout();
        toast.info('You have been logged out due to inactivity.');
      }, timeoutMs);
    }
  }, [isAuthenticated, logout, sessionTimeoutMinutes]);

  // Set up activity listeners
  useEffect(() => {
    if (isAuthenticated) {
      // Throttle activity resets to at most once per second
      let lastReset = 0;
      const handleActivity = () => {
        const now = Date.now();
        if (now - lastReset < 1000) return;
        lastReset = now;
        resetTimers();
      };

      activityEvents.forEach(event => {
        window.addEventListener(event, handleActivity);
      });
      
      // Initialize timers
      resetTimers();
      
      // Clean up
      return () => {
        activityEvents.forEach(event => {
          window.removeEventListener(event, handleActivity);
        });
        if (logoutTimer.current) clearTimeout(logoutTimer.current);
        if (warningTimer.current) clearTimeout(warningTimer.current);
        if (countdownInterval.current) clearInterval(countdownInterval.current);
      };
    }
  }, [isAuthenticated, resetTimers, activityEvents]);

  // Check if user is authenticated on initial load and handle token refresh
  useEffect(() => {
    const checkAuth = async () => {
      try {
        // Avoid running auth check on the login route to prevent noisy 401/refresh loops
        if (typeof window !== 'undefined' && window.location.pathname.startsWith('/login')) {
          setLoading(false);
          return;
        }

        setLoading(true);
        const userData = await simulationApi.getCurrentUser();
        setUser(userData);
        setIsAuthenticated(true);

        // Refresh token periodically (every 15 minutes)
        const refreshInterval = setInterval(async () => {
          try {
            await simulationApi.refreshToken();
          } catch (error) {
            console.error('Token refresh failed:', error);
            // If refresh fails, log the user out
            logout();
          }
        }, 15 * 60 * 1000); // 15 minutes

        return () => clearInterval(refreshInterval);
      } catch (err) {
        setIsAuthenticated(false);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    checkAuth();
  }, [logout]);

  const login = useCallback(async (credentials) => {
    try {
      setLoading(true);
      setError(null);

      // This will automatically handle CSRF token and cookies
      const result = await simulationApi.login(credentials);

      if (result?.success) {
        let nextUser = result.user;

        if (!nextUser) {
          try {
            nextUser = await simulationApi.getCurrentUser();
          } catch (fetchError) {
            console.error('Failed to fetch user details after login:', fetchError);
          }
        }

        if (nextUser) {
          setUser(nextUser);
        }
        setIsAuthenticated(true);

        // Store provisioning status from login response
        setProvisioningStatus(result.provisioning_status || null);
        setProvisioningStep(result.provisioning_step || null);

        // Store session timeout from tenant setting
        // (timers will auto-start via the useEffect that watches isAuthenticated + resetTimers)
        const timeout = result.session_timeout_minutes || 5;
        setSessionTimeoutMinutes(timeout);
        localStorage.setItem('sessionTimeoutMinutes', String(timeout));

        return { success: true, user: nextUser };
      }

      const message = result?.error || 'Login failed. Please check your credentials.';
      setError(message);
      return { success: false, error: message, detail: result?.detail };
    } catch (error) {
      const detail = error?.response?.data?.detail;
      let message = 'Login failed. Please check your credentials.';

      if (detail && typeof detail === 'object') {
        message = detail.message || message;
      } else if (typeof detail === 'string') {
        message = detail;
      } else if (error?.message) {
        message = error.message;
      }

      setError(message);
      return {
        success: false,
        error: message,
        detail: detail && typeof detail === 'object' ? detail : undefined,
      };
    } finally {
      setLoading(false);
    }
  }, []);

  

  const refreshUser = useCallback(async () => {
    try {
      const userData = await simulationApi.getCurrentUser();
      setUser(userData);
      return userData;
    } catch (error) {
      setIsAuthenticated(false);
      setUser(null);
      throw error;
    }
  }, []);

  // ----- Role helpers -----
  const hasRole = useCallback((role) => {
    if (!user || !role) return false;

    const normalized = String(role).trim().toLowerCase().replace(/[\s_-]+/g, '');
    const userType = getUserType(user);

    if (normalized === 'systemadmin') {
      return userType === 'systemadmin';
    }

    if (normalized === 'tenantadmin' || normalized === 'admin') {
      return userType === 'tenantadmin' || userType === 'systemadmin';
    }

    if (normalized === 'scenarioUser' || normalized === 'user') {
      return userType === 'user';
    }

    return false;
  }, [user]);

  const hasAnyRole = useCallback((roles = []) => {
    if (!roles || roles.length === 0) return true;
    return roles.some((r) => hasRole(r));
  }, [hasRole]);

  const hasAllRoles = useCallback((roles = []) => {
    if (!roles || roles.length === 0) return true;
    return roles.every((r) => hasRole(r));
  }, [hasRole]);

  const isTenantAdmin = useMemo(() => {
    if (!user) return false;
    if (isSystemAdmin(user)) return true;
    return isTenantAdminUtil(user);
  }, [user]);

  const dismissProvisioningBanner = useCallback(() => {
    setProvisioningStatus('dismissed');
  }, []);

  const value = useMemo(() => ({
    isAuthenticated,
    user,
    loading,
    error,
    login,
    logout,
    refreshUser,
    // role helpers
    hasRole,
    hasAnyRole,
    hasAllRoles,
    isTenantAdmin,
    showTimeoutWarning,
    timeLeft,
    resetTimers,
    // provisioning status
    provisioningStatus,
    provisioningStep,
    dismissProvisioningBanner,
  }), [isAuthenticated, user, loading, error, login, logout, refreshUser, hasRole, hasAnyRole, hasAllRoles, isTenantAdmin, showTimeoutWarning, timeLeft, resetTimers, provisioningStatus, provisioningStep, dismissProvisioningBanner]);

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export default AuthContext;
