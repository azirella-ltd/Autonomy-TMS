/**
 * ActiveConfigContext
 *
 * Provides the tenant's active BASELINE supply chain config to all planning
 * pages.  Supports working branches for what-if analysis (alternate sourcing,
 * network redesign).
 *
 * Usage:
 *   const { activeConfigId, effectiveConfigId, setWorkingBranch } = useActiveConfig();
 *
 *   // effectiveConfigId = workingBranchId ?? activeConfigId
 *   // Use effectiveConfigId for all planning API calls.
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import { useAuth } from './AuthContext';

const ActiveConfigContext = createContext({
  activeConfig: null,
  activeConfigId: null,
  configMode: 'production',
  workingBranch: null,
  workingBranchId: null,
  effectiveConfigId: null,
  branches: [],
  loading: true,
  error: null,
  setWorkingBranch: () => {},
  clearWorkingBranch: () => {},
  createBranch: async () => {},
  refresh: async () => {},
});

export function ActiveConfigProvider({ children }) {
  const { isAuthenticated, user } = useAuth();
  const [activeConfig, setActiveConfig] = useState(null);
  const [workingBranch, setWorkingBranchState] = useState(null);
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const activeConfigId = activeConfig?.id ?? null;
  const configMode = activeConfig?.mode ?? 'production';
  const workingBranchId = workingBranch?.id ?? null;
  const effectiveConfigId = workingBranchId ?? activeConfigId;

  const fetchActiveConfig = useCallback(async () => {
    if (!isAuthenticated) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.get('/supply-chain-config/active');
      setActiveConfig(response.data);

      // Fetch WORKING branches for this tenant
      if (response.data?.id) {
        try {
          const childrenRes = await api.get(
            `/supply-chain-config/${response.data.id}/children`
          );
          const workingBranches = (childrenRes.data || []).filter(
            (c) => c.scenario_type === 'WORKING' && !c.committed_at
          );
          setBranches(workingBranches);
        } catch {
          setBranches([]);
        }
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load active config');
      setActiveConfig(null);
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    fetchActiveConfig();
  }, [fetchActiveConfig]);

  const setWorkingBranch = useCallback((branch) => {
    setWorkingBranchState(branch);
  }, []);

  const clearWorkingBranch = useCallback(() => {
    setWorkingBranchState(null);
  }, []);

  const createBranch = useCallback(
    async (name, description = '') => {
      if (!activeConfigId) throw new Error('No active baseline config');
      const response = await api.post(
        `/supply-chain-config/${activeConfigId}/branch`,
        {
          name,
          description,
          scenario_type: 'WORKING',
        }
      );
      const newBranch = response.data;
      setBranches((prev) => [...prev, newBranch]);
      setWorkingBranchState(newBranch);
      return newBranch;
    },
    [activeConfigId]
  );

  return (
    <ActiveConfigContext.Provider
      value={{
        activeConfig,
        activeConfigId,
        configMode,
        workingBranch,
        workingBranchId,
        effectiveConfigId,
        branches,
        loading,
        error,
        setWorkingBranch,
        clearWorkingBranch,
        createBranch,
        refresh: fetchActiveConfig,
      }}
    >
      {children}
    </ActiveConfigContext.Provider>
  );
}

export function useActiveConfig() {
  const context = useContext(ActiveConfigContext);
  if (!context) {
    throw new Error('useActiveConfig must be used within an ActiveConfigProvider');
  }
  return context;
}

export default ActiveConfigContext;
