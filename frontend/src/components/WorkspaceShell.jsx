/**
 * WorkspaceShell — Tabbed workspace container.
 *
 * Replaces the old Layout component. Renders:
 *   TopNavbar → TabBar → [Sidebar + TabPanes]
 *
 * The active tab's content is rendered via React Router's <Outlet />.
 * Background tabs keep their DOM alive via TabPane (display: none).
 *
 * Key design: React Router still resolves the active tab's route.
 * When the user switches tabs, we call navigate(tab.path) which
 * updates the URL and lets React Router render the correct component.
 * The previous tab's content is preserved in a cached TabPane.
 */

import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate, Outlet } from 'react-router-dom';
import TopNavbar from './TopNavbar';
import TabBar from './TabBar';
import TabPane from './TabPane';
import CapabilityAwareSidebar from './CapabilityAwareSidebar';
import useTabStore from '../stores/useTabStore';
import { useAuth } from '../contexts/AuthContext';
import { isSystemAdmin, isTenantAdmin as checkIsTenantAdmin } from '../utils/authUtils';
import { cn } from '../lib/utils/cn';

const ADMIN_TAB_ID = 'tab-administration';

const WorkspaceShell = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const tabs = useTabStore((s) => s.tabs);
  const activeTabId = useTabStore((s) => s.activeTabId);
  const openTab = useTabStore((s) => s.openTab);
  const focusTab = useTabStore((s) => s.focusTab);
  const getActiveTab = useTabStore((s) => s.getActiveTab);

  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Map of tabId → rendered React element (cached for background tabs)
  const cachedPanesRef = useRef(new Map());
  const adminTabOpened = useRef(false);

  // ── Clear stale tabs when user changes (e.g., login as different user) ─
  useEffect(() => {
    if (!user) return;
    const prevUser = sessionStorage.getItem('autonomy-tabs-user');
    if (prevUser && prevUser !== String(user.id)) {
      // Different user — clear tabs to avoid stale state
      sessionStorage.removeItem('autonomy-tabs');
      useTabStore.setState({
        tabs: [{ id: 'tab-decision-stream', path: '/decision-stream', label: 'Decision Stream', pinned: true, closeable: false, scrollY: 0 }],
        activeTabId: 'tab-decision-stream',
      });
    }
    sessionStorage.setItem('autonomy-tabs-user', String(user.id));
  }, [user]);

  // ── Auto-open Administration tab for tenant admins / system admins ────
  useEffect(() => {
    if (adminTabOpened.current || !user) return;
    const isTenantAdm = checkIsTenantAdmin(user);
    const isSysAdm = isSystemAdmin(user);
    if (isTenantAdm || isSysAdm) {
      const adminPath = isSysAdm ? '/admin/tenants' : '/admin';
      // Only open if not already present
      const existing = useTabStore.getState().tabs.find((t) => t.id === ADMIN_TAB_ID);
      if (!existing) {
        useTabStore.setState((s) => ({
          tabs: [
            ...s.tabs,
            {
              id: ADMIN_TAB_ID,
              path: adminPath,
              label: 'Administration',
              pinned: false,
              closeable: true,
              scrollY: 0,
            },
          ],
        }));
      }
      adminTabOpened.current = true;
    }
  }, [user]);

  // ── Sync URL changes → tab store ──────────────────────────────────────
  // When the URL changes (browser back/forward, deep link), open/focus a tab.
  // Ignore paths that are just redirectors (DashboardRouter, login, etc.)
  const REDIRECT_PATHS = new Set(['/', '/dashboard', '/login', '/auto-login', '/unauthorized']);

  useEffect(() => {
    const path = location.pathname;

    if (path === '/' || path === '/decision-stream') {
      focusTab('tab-decision-stream');
      return;
    }

    // Skip redirect-only paths — they'll redirect to the real page
    if (REDIRECT_PATHS.has(path)) return;

    // Check if any tab already has this path
    const existing = tabs.find((t) => t.path === path);
    if (existing) {
      if (existing.id !== activeTabId) {
        focusTab(existing.id);
      }
    } else {
      // New URL → open a tab for it
      const label = path.split('/').filter(Boolean).pop()?.replace(/-/g, ' ') || 'Page';
      openTab(path, label);
    }
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Sync tab focus → URL ──────────────────────────────────────────────
  // When active tab changes in the store, update the URL
  const prevActiveRef = useRef(activeTabId);
  useEffect(() => {
    if (activeTabId !== prevActiveRef.current) {
      prevActiveRef.current = activeTabId;
      const tab = getActiveTab();
      if (tab && tab.path !== location.pathname) {
        navigate(tab.path, { replace: true });
      }
    }
  }, [activeTabId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Cache the current Outlet content for each tab ─────────────────────
  // When the active tab renders, we capture its Outlet content and cache it.
  // When a tab goes to the background, the cached content stays in a hidden TabPane.
  const outletElement = <Outlet />;

  // Update cache for current active tab
  cachedPanesRef.current.set(activeTabId, outletElement);

  // Clean up cached panes for tabs that no longer exist
  for (const key of cachedPanesRef.current.keys()) {
    if (!tabs.find((t) => t.id === key)) {
      cachedPanesRef.current.delete(key);
    }
  }

  // ── Keyboard shortcuts ────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e) => {
      // Ctrl+W — close active tab
      if ((e.ctrlKey || e.metaKey) && e.key === 'w') {
        const tab = getActiveTab();
        if (tab?.closeable) {
          e.preventDefault();
          useTabStore.getState().closeTab(tab.id);
        }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Is the active tab an admin page? Show sidebar inside that tab.
  const activeTab = getActiveTab();
  const isAdminTab = activeTab?.path?.startsWith('/admin') ||
                     activeTab?.path?.startsWith('/system') ||
                     activeTab?.path?.startsWith('/deployment') ||
                     activeTab?.id === ADMIN_TAB_ID;

  const handleSidebarToggle = () => {
    const next = !sidebarOpen;
    setSidebarOpen(next);
    localStorage.setItem('sidebar:admin-state', String(next));
  };

  // Restore admin sidebar state
  useEffect(() => {
    const saved = localStorage.getItem('sidebar:admin-state');
    if (saved !== null) setSidebarOpen(saved === 'true');
  }, []);

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Top Navbar — always visible */}
      <TopNavbar sidebarOpen={false} />

      {/* Tab Bar */}
      <div
        className={cn(
          'pt-16 transition-all duration-200 ease-in-out',
          isAdminTab ? (sidebarOpen ? 'ml-[280px]' : 'ml-[65px]') : 'ml-0',
        )}
      >
        <TabBar />
      </div>

      {/* Sidebar — only visible when an admin tab is active */}
      {isAdminTab && (
        <CapabilityAwareSidebar
          open={sidebarOpen}
          onToggle={handleSidebarToggle}
          adminOnly={user?.powell_role !== 'DEMO_ALL'}
        />
      )}

      {/* Tab content area */}
      <div
        className={cn(
          'flex-1 flex flex-col transition-all duration-200 ease-in-out',
          isAdminTab ? (sidebarOpen ? 'ml-[280px]' : 'ml-[65px]') : 'ml-0',
        )}
      >
        {/* Render ALL open tabs — active one visible, others hidden */}
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          const content = isActive
            ? outletElement
            : cachedPanesRef.current.get(tab.id);

          if (!content) return null;

          return (
            <TabPane key={tab.id} tabId={tab.id} active={isActive}>
              {content}
            </TabPane>
          );
        })}
      </div>

      {/* Azirella input bar — portal target, fixed at bottom */}
      <div
        id="azirella-input-root"
        className={cn(
          'fixed bottom-0 left-0 right-0 z-30 transition-all duration-200',
          isAdminTab ? (sidebarOpen ? 'ml-[280px]' : 'ml-[65px]') : 'ml-0',
        )}
      />
    </div>
  );
};

export default WorkspaceShell;
