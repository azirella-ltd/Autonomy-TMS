/**
 * Dashboard Router
 *
 * Routes users to appropriate dashboard based on their ADH role and user type.
 *
 * KEY DESIGN PRINCIPLE (Feb 2026):
 * - decision_level (stored on user) → Determines landing page (FIXED)
 * - capabilities (via RBAC roles) → Determines what user can do (CUSTOMIZABLE)
 *
 * This separation allows customer admins to customize a user's capabilities
 * while maintaining consistent navigation patterns for each role.
 *
 * Routing Priority:
 * 1. SYSTEM_ADMIN always → /admin/tenants
 * 2. ADH role checked FIRST for all other users (from user.decision_level field)
 * 3. Falls back to user_type based routing if no ADH role
 *
 * Adaptive Decision Hierarchy Routing (role-based, checked first):
 * - SC_VP: → /executive-dashboard
 *   Focus: Strategic/CFA level, performance metrics, ROI, category automation
 *
 * - SOP_DIRECTOR: → /sop-worklist
 *   Focus: Tactical/S&OP level, worklist items, agent recommendations
 *
 * - MPS_MANAGER: → /insights/actions
 *   Focus: Operational/TRM level, execution items, agent decision monitoring
 *
 * - DEMO_ALL: → /executive-dashboard (has all capabilities for demos)
 *
 * Fallback Routing (user_type based, if no decision level):
 * - TENANT_ADMIN (Learning Tenant): → /admin (Learning Home - game-centric training dashboard)
 * - TENANT_ADMIN (Production Tenant): → /admin/production (Configuration-focused dashboard)
 *   Features: Supply Chains, Scenarios (tree), Users, Settings (hierarchies, data sources, CDC)
 * - USER: → Active game or /scenarios/play
 *
 * Demo User (demo@distdemo.com):
 * - Has decision_level=DEMO_ALL → lands on /executive-dashboard
 * - Has all ADH capabilities → can navigate to all ADH dashboards without logout
 */

import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Spinner } from '../components/common';
import { useAuth } from '../contexts/AuthContext';
import { useActiveConfig } from '../contexts/ActiveConfigContext';
import { getUserScenarios } from '../services/dashboardService';
import { api } from '../services/api';

/**
 * Get ADH role from API response
 *
 * ADH role is now stored on the user record (not derived from capabilities).
 * This allows capabilities to be customized while maintaining fixed landing pages.
 *
 * Returns: { decisionLevel: 'SC_VP' | 'SOP_DIRECTOR' | 'MPS_MANAGER' | 'DEMO_ALL' | null, capabilities: string[] }
 */
const getDecisionLevelFromAPI = async () => {
  try {
    // Use /capabilities/me endpoint - returns decision_level and capabilities
    const response = await api.get('/capabilities/me');
    const { decision_level, capabilities = [] } = response.data;

    return {
      decisionLevel: decision_level || null,  // Explicit decision_level from user record
      capabilities,
    };
  } catch (err) {
    console.error('Failed to fetch decision level:', err);
    return { decisionLevel: null, capabilities: [] };
  }
};

/**
 * Get landing page for ADH role
 *
 * ADH role determines the fixed landing page regardless of capabilities.
 * This allows customer admins to customize user capabilities while maintaining
 * consistent navigation patterns for each role.
 */
const getDecisionLevelLandingPage = (decisionLevel) => {
  switch (decisionLevel) {
    case 'SC_VP':
    case 'EXECUTIVE':
      return '/strategy-briefing';
    case 'DEMO_ALL':  // DEMO_ALL lands on executive dashboard (highest level)
      return '/executive-dashboard';
    case 'SOP_DIRECTOR':
      return '/sop-worklist';
    case 'ALLOCATION_MANAGER':
      return '/planning/allocation-worklist';
    case 'ORDER_PROMISE_MANAGER':
      return '/planning/execution/atp-worklist';
    case 'MPS_MANAGER':
      return '/insights/actions';
    default:
      return null;
  }
};

const DashboardRouter = () => {
  const { user } = useAuth();
  const { provisioningRequired, loading: configLoading, activeConfigId } = useActiveConfig();
  const navigate = useNavigate();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const handleRedirect = async () => {
      if (!user) return;

      // Wait for active config to finish loading (provisioning check happens there)
      if (configLoading) return;

      // If tenant's config is not provisioned, redirect to provisioning page
      // (skip for SYSTEM_ADMIN who manages all tenants)
      if (provisioningRequired && activeConfigId && user.user_type !== 'SYSTEM_ADMIN') {
        navigate('/provisioning', { replace: true });
        return;
      }

      // SYSTEM_ADMIN: Always go to Organization Management
      if (user.user_type === 'SYSTEM_ADMIN') {
        navigate('/admin/tenants', { replace: true });
        return;
      }

      // TENANT_ADMIN: Always go to User Management (their primary task)
      if (user.user_type === 'TENANT_ADMIN' && !user.decision_level) {
        navigate('/admin/user-management', { replace: true });
        return;
      }

      // Check ADH role FIRST for ALL non-system users (USER, TENANT_ADMIN, etc.)
      // ADH role is stored on user record - determines landing page (fixed)
      // Capabilities determine what user can do (customizable by customer admin)
      const { decisionLevel } = await getDecisionLevelFromAPI();
      const decisionLevelLanding = getDecisionLevelLandingPage(decisionLevel);

      if (decisionLevelLanding) {
        navigate(decisionLevelLanding, { replace: true });
        return;
      }

      // No ADH role - route based on user_type

      // USER without ADH capabilities: Redirect to active scenario
      if (user.user_type === 'USER') {
        try {
          const games = await getUserScenarios();
          if (games.length > 0) {
            const activeGame = games.find(
              (g) => g.status === 'IN_PROGRESS' || g.status === 'STARTED'
            );
            const targetGame = activeGame || games[0];
            navigate(`/scenarios/${targetGame.id}`, { replace: true });
          } else {
            navigate('/scenarios/play', { replace: true });
          }
        } catch (err) {
          console.error('Failed to fetch user games:', err);
          navigate('/scenarios/play', { replace: true });
        }
        return;
      }

      // TENANT_ADMIN without ADH role: Route based on tenant mode
      if (user.user_type === 'TENANT_ADMIN') {
        try {
          if (user.tenant_id) {
            const response = await api.get(`/tenants/${user.tenant_id}`);
            const tenant = response.data;

            if (tenant.mode === 'learning') {
              // Learning customers go to Learning Home (training-focused admin dashboard)
              navigate('/admin', { replace: true });
            } else {
              // Production customers go to Production Admin Dashboard (configuration-focused)
              navigate('/admin/production', { replace: true });
            }
          } else {
            // No tenant assigned, default to production admin
            navigate('/admin/production', { replace: true });
          }
        } catch (err) {
          console.error('Failed to fetch tenant info:', err);
          // Default to production admin on error
          navigate('/admin/production', { replace: true });
        }
        return;
      }

      // Fallback
      navigate('/insights', { replace: true });
    };

    handleRedirect();
  }, [user, navigate, configLoading, provisioningRequired, activeConfigId]);

  // Always show loading while redirecting
  return (
    <div className="flex justify-center items-center min-h-[60vh]">
      <Spinner size="lg" />
    </div>
  );
};

export default DashboardRouter;
