/**
 * useCustomerMode Hook
 *
 * Hook to fetch and manage the current user's customer mode (learning vs production).
 * Used to determine which navigation structure to display.
 *
 * NOTE: "Learning" mode is for user education (learning how AI agents work).
 * This is separate from "AI Model Training" (TRM/GNN/RL training) which can
 * happen in BOTH Learning and Production customers.
 */

import { useState, useEffect, useMemo } from 'react';
import { api } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

// Customer mode constants matching backend enum
export const CUSTOMER_MODES = {
  LEARNING: 'learning',      // User education mode
  PRODUCTION: 'production',  // Real data, real planning
};

// Clock mode constants for learning customers
export const CLOCK_MODES = {
  TURN_BASED: 'turn_based',
  TIMED: 'timed',
  REALTIME: 'realtime',
};

export const useCustomerMode = () => {
  const { user, isAuthenticated } = useAuth();
  const [customer, setCustomer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchCustomer = async () => {
      if (!isAuthenticated || !user) {
        setCustomer(null);
        setLoading(false);
        return;
      }

      // System admins without a customer default to production mode
      if (!user.customer_id) {
        setCustomer(null);
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        const response = await api.get('/customers/my');
        setCustomer(response.data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch customer:', err);
        setError(err.message);
        // Default to production mode on error
        setCustomer(null);
      } finally {
        setLoading(false);
      }
    };

    fetchCustomer();
  }, [isAuthenticated, user]);

  // Derived values
  const customerMode = useMemo(() => {
    if (!customer) return CUSTOMER_MODES.PRODUCTION;
    return customer.mode || CUSTOMER_MODES.PRODUCTION;
  }, [customer]);

  const isLearningMode = useMemo(() => {
    return customerMode === CUSTOMER_MODES.LEARNING;
  }, [customerMode]);

  const isProductionMode = useMemo(() => {
    return customerMode === CUSTOMER_MODES.PRODUCTION;
  }, [customerMode]);

  const clockMode = useMemo(() => {
    if (!customer || !isLearningMode) return null;
    return customer.clock_mode || CLOCK_MODES.TURN_BASED;
  }, [customer, isLearningMode]);

  return {
    customer,
    customerMode,
    isLearningMode,
    isProductionMode,
    clockMode,
    loading,
    error,
  };
};

export default useCustomerMode;
