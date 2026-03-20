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

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useLocation, useNavigate, Outlet } from 'react-router-dom';
import CapabilityAwareSidebar from './CapabilityAwareSidebar';
import TopNavbar from './TopNavbar';
import TabBar from './TabBar';
import TabPane from './TabPane';
import useTabStore from '../stores/useTabStore';
import { cn } from '../lib/utils/cn';

const WorkspaceShell = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const tabs = useTabStore((s) => s.tabs);
  const activeTabId = useTabStore((s) => s.activeTabId);
  const openTab = useTabStore((s) => s.openTab);
  const focusTab = useTabStore((s) => s.focusTab);
  const getActiveTab = useTabStore((s) => s.getActiveTab);

  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Map of tabId → rendered React element (cached for background tabs)
  const cachedPanesRef = useRef(new Map());

  // ── Sync URL changes → tab store ──────────────────────────────────────
  // When the URL changes (browser back/forward, deep link), open/focus a tab
  useEffect(() => {
    const path = location.pathname;
    if (path === '/' || path === '/decision-stream') {
      focusTab('tab-decision-stream');
      return;
    }

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

  // ── Sidebar state ─────────────────────────────────────────────────────
  const activeTab = getActiveTab();
  const isDecisionStream = activeTab?.path === '/decision-stream';

  useEffect(() => {
    if (!isDecisionStream) {
      const saved = localStorage.getItem('sidebar:state');
      if (saved !== null) {
        setSidebarOpen(saved === 'true');
      }
    }
  }, [isDecisionStream]);

  const handleSidebarToggle = () => {
    const newState = !sidebarOpen;
    setSidebarOpen(newState);
    localStorage.setItem('sidebar:state', String(newState));
  };

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

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Top Navbar — always visible */}
      <TopNavbar sidebarOpen={isDecisionStream ? false : sidebarOpen} />

      {/* Tab Bar */}
      <div
        className={cn(
          'transition-all duration-200 ease-in-out pt-16',
          isDecisionStream ? 'ml-0' : sidebarOpen ? 'ml-[280px]' : 'ml-[65px]',
        )}
      >
        <TabBar />
      </div>

      {/* Sidebar — hidden on Decision Stream */}
      {!isDecisionStream && (
        <CapabilityAwareSidebar
          open={sidebarOpen}
          onToggle={handleSidebarToggle}
        />
      )}

      {/* Tab content area */}
      <div
        className={cn(
          'flex-1 flex flex-col transition-all duration-200 ease-in-out',
          isDecisionStream ? 'ml-0' : sidebarOpen ? 'ml-[280px]' : 'ml-[65px]',
        )}
      >
        {/* Render ALL open tabs — active one visible, others hidden */}
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          const content = isActive
            ? outletElement
            : cachedPanesRef.current.get(tab.id);

          // Only render tabs that have been visited (have cached content)
          if (!content) return null;

          return (
            <TabPane key={tab.id} tabId={tab.id} active={isActive}>
              {content}
            </TabPane>
          );
        })}
      </div>
    </div>
  );
};

export default WorkspaceShell;
