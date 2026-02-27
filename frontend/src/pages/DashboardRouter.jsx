/**
 * Dashboard Router
 *
 * Routes users to appropriate dashboard based on their Powell role and user type.
 *
 * KEY DESIGN PRINCIPLE (Feb 2026):
 * - powell_role (stored on user) → Determines landing page (FIXED)
 * - capabilities (via RBAC roles) → Determines what user can do (CUSTOMIZABLE)
 *
 * This separation allows customer admins to customize a user's capabilities
 * while maintaining consistent navigation patterns for each role.
 *
 * Routing Priority:
 * 1. SYSTEM_ADMIN always → /admin/tenants
 * 2. Powell role checked FIRST for all other users (from user.powell_role field)
 * 3. Falls back to user_type based routing if no Powell role
 *
 * Powell Framework Routing (role-based, checked first):
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
 * Fallback Routing (user_type based, if no Powell role):
 * - TENANT_ADMIN (Learning Tenant): → /admin (Learning Home - game-centric training dashboard)
 * - TENANT_ADMIN (Production Tenant): → /admin/production (Configuration-focused dashboard)
 *   Features: Supply Chains, Scenarios (tree), Users, Settings (hierarchies, data sources, CDC)
 * - USER: → Active game or /scenarios/play
 *
 * Demo User (demo@distdemo.com):
 * - Has powell_role=DEMO_ALL → lands on /executive-dashboard
 * - Has all Powell capabilities → can navigate to all Powell dashboards without logout
 */

import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Spinner } from '../components/common';
import { useAuth } from '../contexts/AuthContext';
import { getUserScenarios } from '../services/dashboardService';
import { api } from '../services/api';

/**
 * Get Powell role from API response
 *
 * Powell role is now stored on the user record (not derived from capabilities).
 * This allows capabilities to be customized while maintaining fixed landing pages.
 *
 * Returns: { powellRole: 'SC_VP' | 'SOP_DIRECTOR' | 'MPS_MANAGER' | 'DEMO_ALL' | null, capabilities: string[] }
 */
const getPowellRoleFromAPI = async () => {
  try {
    // Use /capabilities/me endpoint - returns powell_role and capabilities
    const response = await api.get('/capabilities/me');
    const { powell_role, capabilities = [] } = response.data;

    return {
      powellRole: powell_role || null,  // Explicit powell_role from user record
      capabilities,
    };
  } catch (err) {
    console.error('Failed to fetch Powell role:', err);
    return { powellRole: null, capabilities: [] };
  }
};

/**
 * Get landing page for Powell role
 *
 * Powell role determines the fixed landing page regardless of capabilities.
 * This allows customer admins to customize user capabilities while maintaining
 * consistent navigation patterns for each role.
 */
const getPowellLandingPage = (powellRole) => {
  switch (powellRole) {
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
  const navigate = useNavigate();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const handleRedirect = async () => {
      if (!user) return;

      // SYSTEM_ADMIN: Always go to Organization Management (skip Powell check)
      if (user.user_type === 'SYSTEM_ADMIN') {
        navigate('/admin/tenants', { replace: true });
        return;
      }

      // Check Powell role FIRST for ALL non-system users (USER, TENANT_ADMIN, etc.)
      // Powell role is stored on user record - determines landing page (fixed)
      // Capabilities determine what user can do (customizable by customer admin)
      const { powellRole } = await getPowellRoleFromAPI();
      const powellLanding = getPowellLandingPage(powellRole);

      if (powellLanding) {
        navigate(powellLanding, { replace: true });
        return;
      }

      // No Powell role - route based on user_type

      // USER without Powell capabilities: Redirect to active scenario
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

      // TENANT_ADMIN without Powell role: Route based on tenant mode
      if (user.user_type === 'TENANT_ADMIN' || user.user_type === 'GROUP_ADMIN') {
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
  }, [user, navigate]);

  // Always show loading while redirecting
  return (
    <div className="flex justify-center items-center min-h-[60vh]">
      <Spinner size="lg" />
    </div>
  );
};

export default DashboardRouter;
