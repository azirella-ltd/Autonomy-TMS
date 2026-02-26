/**
 * useTenantMode Hook
 *
 * Hook to fetch and manage the current user's tenant mode (learning vs production).
 * Used to determine which navigation structure to display.
 *
 * NOTE: "Learning" mode is for user education (learning how AI agents work).
 * This is separate from "AI Model Training" (TRM/GNN/RL training) which can
 * happen in BOTH Learning and Production tenants.
 */

import { useState, useEffect, useMemo } from 'react';
import { api } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

// Tenant mode constants matching backend enum
export const TENANT_MODES = {
  LEARNING: 'learning',      // User education mode
  PRODUCTION: 'production',  // Real data, real planning
};

// Clock mode constants for learning tenants
export const CLOCK_MODES = {
  TURN_BASED: 'turn_based',
  TIMED: 'timed',
  REALTIME: 'realtime',
};

export const useTenantMode = () => {
  const { user, isAuthenticated } = useAuth();
  const [tenant, setTenant] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchTenant = async () => {
      if (!isAuthenticated || !user) {
        setTenant(null);
        setLoading(false);
        return;
      }

      // System admins without a tenant default to production mode
      if (!user.tenant_id) {
        setTenant(null);
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        const response = await api.get('/tenants/my');
        setTenant(response.data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch tenant:', err);
        setError(err.message);
        // Default to production mode on error
        setTenant(null);
      } finally {
        setLoading(false);
      }
    };

    fetchTenant();
  }, [isAuthenticated, user]);

  // Derived values
  const tenantMode = useMemo(() => {
    if (!tenant) return TENANT_MODES.PRODUCTION;
    return tenant.mode || TENANT_MODES.PRODUCTION;
  }, [tenant]);

  const isLearningMode = useMemo(() => {
    return tenantMode === TENANT_MODES.LEARNING;
  }, [tenantMode]);

  const isProductionMode = useMemo(() => {
    return tenantMode === TENANT_MODES.PRODUCTION;
  }, [tenantMode]);

  const clockMode = useMemo(() => {
    if (!tenant || !isLearningMode) return null;
    return tenant.clock_mode || CLOCK_MODES.TURN_BASED;
  }, [tenant, isLearningMode]);

  return {
    tenant,
    tenantMode,
    isLearningMode,
    isProductionMode,
    clockMode,
    loading,
    error,
  };
};

export default useTenantMode;
