/**
 * useGroupMode Hook
 *
 * Hook to fetch and manage the current user's group mode (learning vs production).
 * Used to determine which navigation structure to display.
 *
 * NOTE: "Learning" mode is for user education (learning how AI agents work).
 * This is separate from "AI Model Training" (TRM/GNN/RL training) which can
 * happen in BOTH Learning and Production groups.
 */

import { useState, useEffect, useMemo } from 'react';
import { api } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

// Group mode constants matching backend enum
export const GROUP_MODES = {
  LEARNING: 'learning',      // User education mode
  PRODUCTION: 'production',  // Real data, real planning
};

// Clock mode constants for learning groups
export const CLOCK_MODES = {
  TURN_BASED: 'turn_based',
  TIMED: 'timed',
  REALTIME: 'realtime',
};

export const useGroupMode = () => {
  const { user, isAuthenticated } = useAuth();
  const [group, setGroup] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchGroup = async () => {
      if (!isAuthenticated || !user) {
        setGroup(null);
        setLoading(false);
        return;
      }

      // System admins without a group default to production mode
      if (!user.customer_id) {
        setGroup(null);
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        const response = await api.get('/groups/my');
        setGroup(response.data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch group:', err);
        setError(err.message);
        // Default to production mode on error
        setGroup(null);
      } finally {
        setLoading(false);
      }
    };

    fetchGroup();
  }, [isAuthenticated, user]);

  // Derived values
  const groupMode = useMemo(() => {
    if (!group) return GROUP_MODES.PRODUCTION;
    return group.mode || GROUP_MODES.PRODUCTION;
  }, [group]);

  const isLearningMode = useMemo(() => {
    return groupMode === GROUP_MODES.LEARNING;
  }, [groupMode]);

  const isProductionMode = useMemo(() => {
    return groupMode === GROUP_MODES.PRODUCTION;
  }, [groupMode]);

  const clockMode = useMemo(() => {
    if (!group || !isLearningMode) return null;
    return group.clock_mode || CLOCK_MODES.TURN_BASED;
  }, [group, isLearningMode]);

  return {
    group,
    groupMode,
    isLearningMode,
    isProductionMode,
    clockMode,
    loading,
    error,
  };
};

export default useGroupMode;
