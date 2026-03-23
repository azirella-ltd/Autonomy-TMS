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
import { Send, Loader2 } from 'lucide-react';
import Markdown from 'react-markdown';
import AzirellaAvatar from './AzirellaAvatar';

const ADMIN_TAB_ID = 'tab-administration';
const AZIRELLA_PANEL_WIDTH = 380;

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

  // ── Azirella panel state ────────────────────────────────────────────
  const [azInput, setAzInput] = useState('');
  const [azMessages, setAzMessages] = useState([]);
  const [azLoading, setAzLoading] = useState(false);
  const [azPanelOpen, setAzPanelOpen] = useState(true); // Toggle panel visibility
  const [azConversationId, setAzConversationId] = useState(null); // Thread conversation history
  const azEndRef = useRef(null);

  useEffect(() => {
    azEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [azMessages, azLoading]);

  const handleAzSubmit = async () => {
    const text = azInput.trim();
    if (!text || azLoading) return;
    setAzMessages(prev => [...prev, { role: 'user', content: text }]);
    setAzInput('');
    setAzLoading(true);
    try {
      const { api } = await import('../services/api');
      const resp = await api.post('/decision-stream/chat', {
        message: text,
        conversation_id: azConversationId,  // Thread history
        config_id: null,  // Backend resolves from user's active config
      });
      const answer = resp.data?.response || resp.data?.content || 'No response.';
      // Persist conversation ID for subsequent messages
      if (resp.data?.conversation_id) {
        setAzConversationId(resp.data.conversation_id);
      }
      setAzMessages(prev => [...prev, { role: 'assistant', content: answer }]);
    } catch (err) {
      setAzMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.response?.data?.detail || err.message}` }]);
    } finally {
      setAzLoading(false);
    }
  };

  // Show Azirella panel for non-system-admin users when toggled open
  const canShowAzirella = !isSystemAdmin(user);
  const showAzirellaPanel = canShowAzirella && azPanelOpen;
  const panelWidth = showAzirellaPanel ? AZIRELLA_PANEL_WIDTH : 0;

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

  // ── Auto-open role-based tabs ───────────────────────────────────────
  useEffect(() => {
    if (adminTabOpened.current || !user) return;
    adminTabOpened.current = true;

    const isTenantAdm = checkIsTenantAdmin(user);
    const isSysAdm = isSystemAdmin(user);
    const decisionLevel = user.decision_level;
    const currentTabs = useTabStore.getState().tabs;

    // DEMO_ALL → Decision Stream (active) + Strategy Briefing + Executive Dashboard
    if (decisionLevel === 'DEMO_ALL') {
      if (!currentTabs.find((t) => t.path === '/strategy-briefing')) {
        useTabStore.getState().openTab('/strategy-briefing', 'Strategy Briefing');
      }
      if (!currentTabs.find((t) => t.path === '/executive-dashboard')) {
        useTabStore.getState().openTab('/executive-dashboard', 'Executive Dashboard');
      }
      // Always focus Decision Stream on login
      useTabStore.getState().focusTab('tab-decision-stream');
      navigate('/decision-stream');
      return; // Skip admin tab for DEMO_ALL
    }

    // Tenant admin / System admin → Administration only (no Decision Stream)
    if (isTenantAdm || isSysAdm) {
      const adminPath = isSysAdm ? '/admin/tenants' : '/admin/user-management';
      // Replace tabs entirely — admin doesn't get Decision Stream
      const adminTab = {
        id: ADMIN_TAB_ID,
        path: adminPath,
        label: 'Administration',
        pinned: true,
        closeable: false,
        scrollY: 0,
      };
      // Remove Decision Stream, keep only Administration as the pinned tab
      useTabStore.setState((s) => {
        const nonDS = s.tabs.filter((t) => t.id !== 'tab-decision-stream');
        const hasAdmin = nonDS.find((t) => t.id === ADMIN_TAB_ID);
        return {
          tabs: hasAdmin ? nonDS : [adminTab, ...nonDS],
          activeTabId: ADMIN_TAB_ID,
        };
      });
      navigate(adminPath);
      return;
    }

    // Executives → Decision Stream + Strategy Briefing + Executive Dashboard
    if (decisionLevel === 'SC_VP' || decisionLevel === 'EXECUTIVE') {
      if (!currentTabs.find((t) => t.path === '/strategy-briefing')) {
        useTabStore.getState().openTab('/strategy-briefing', 'Strategy Briefing');
      }
      if (!currentTabs.find((t) => t.path === '/executive-dashboard')) {
        useTabStore.getState().openTab('/executive-dashboard', 'Executive Dashboard');
      }
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

  // Is the active tab one that shows a sidebar?
  const activeTab = getActiveTab();
  const isFullFunctionalityTab = activeTab?.id === 'tab-full-functionality';
  const isAdminTab = isFullFunctionalityTab ||
                     activeTab?.path?.startsWith('/admin') ||
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
      <TopNavbar
        sidebarOpen={false}
        azirellaPanelWidth={panelWidth}
        azirellaPanelOpen={showAzirellaPanel}
        onToggleAzirella={canShowAzirella ? () => setAzPanelOpen(prev => !prev) : null}
      />

      {/* Tab Bar */}
      <div
        className={cn(
          'pt-16 transition-all duration-200 ease-in-out',
          'ml-0',
        )}
        style={{ marginRight: panelWidth }}
      >
        <TabBar />
      </div>

      {/* Sidebar removed — all navigation through tabs via "+" palette */}

      {/* Tab content area */}
      <div
        className={cn(
          'flex-1 flex flex-col transition-all duration-200 ease-in-out',
          'ml-0',
        )}
        style={{ marginRight: panelWidth }}
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

      {/* ═══ AZIRELLA PANEL — right side ═══ */}
      {showAzirellaPanel && (
        <div
          className="fixed right-0 top-16 bottom-0 z-30 flex flex-col border-l"
          style={{ width: AZIRELLA_PANEL_WIDTH, backgroundColor: '#faf9ff' }}
        >
          {/* Header with animated Azirella avatar */}
          <div className="flex items-center gap-2 px-3 py-1.5 border-b flex-shrink-0" style={{ backgroundColor: '#f0edff' }}>
            <AzirellaAvatar
              voiceState={azLoading ? 'processing' : 'idle'}
              size={36}
              inline
            />
            <span className="font-semibold text-sm" style={{ color: '#5b21b6' }}>Azirella</span>
            <span className="text-xs ml-auto" style={{ color: '#a78bfa' }}>AI Assistant</span>
          </div>

          {/* Conversation */}
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
            {azMessages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-center px-4" style={{ opacity: 0.5 }}>
                <img src="/Azirella_logo.png" alt="" className="h-10 w-10 mb-3" style={{ opacity: 0.4 }} onError={(e) => {e.target.style.display='none';}} />
                <p className="text-sm font-medium" style={{ color: '#6b7280' }}>Ask me anything</p>
                <p className="text-xs" style={{ color: '#9ca3af' }}>Decisions, metrics, risks, or directives</p>
              </div>
            )}
            {azMessages.map((msg, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                <div style={{
                  maxWidth: '85%',
                  borderRadius: '16px',
                  padding: '8px 14px',
                  fontSize: '13px',
                  lineHeight: '1.5',
                  ...(msg.role === 'user'
                    ? { backgroundColor: '#7c3aed', color: 'white', borderTopRightRadius: '4px' }
                    : { backgroundColor: '#f3f4f6', color: '#1f2937', borderTopLeftRadius: '4px' }),
                }}>
                  {msg.role === 'user' ? msg.content : (
                    <div className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0.5 prose-strong:font-semibold">
                      <Markdown>{msg.content}</Markdown>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {azLoading && (
              <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                <div style={{ backgroundColor: '#f3f4f6', borderRadius: '16px', padding: '10px 14px', fontSize: '13px', color: '#6b7280' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" style={{ color: '#7c3aed' }} />
                      <span style={{ fontSize: '12px', fontWeight: 500 }}>Analyzing your question...</span>
                    </div>
                    <div style={{ fontSize: '11px', color: '#9ca3af' }}>
                      Checking decisions • Loading supply chain context • Querying knowledge base
                    </div>
                  </div>
                </div>
              </div>
            )}
            <div ref={azEndRef} />
          </div>

          {/* Input */}
          <div className="border-t px-3 py-2.5 flex items-center gap-2 flex-shrink-0" style={{ backgroundColor: '#faf9ff' }}>
            <input
              type="text"
              value={azInput}
              onChange={(e) => setAzInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAzSubmit(); } }}
              placeholder="Ask Azirella..."
              style={{ flex: 1, border: '1px solid #e5e7eb', borderRadius: '8px', padding: '8px 12px', fontSize: '13px', outline: 'none' }}
            />
            <button
              onClick={handleAzSubmit}
              disabled={azLoading || !azInput.trim()}
              style={{ padding: '8px', borderRadius: '50%', color: azLoading || !azInput.trim() ? '#9ca3af' : '#7c3aed', background: 'none', border: 'none', cursor: 'pointer' }}
            >
              {azLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </button>
          </div>
        </div>
      )}

      {/* Fallback portal target (hidden — only used if panel is somehow not visible) */}
      <div id="azirella-input-root" style={{ display: 'none' }} />
    </div>
  );
};

export default WorkspaceShell;
