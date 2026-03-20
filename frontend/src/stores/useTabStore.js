/**
 * useTabStore — Zustand store for the tabbed workspace.
 *
 * Manages open tabs, active tab, per-tab scroll positions.
 * Persists to sessionStorage so tabs survive page refresh.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// ── Helpers ──────────────────────────────────────────────────────────────────

let _nextId = 1;
const makeId = () => `tab-${Date.now()}-${_nextId++}`;

const DECISION_STREAM_TAB = {
  id: 'tab-decision-stream',
  path: '/decision-stream',
  label: 'Decision Stream',
  pinned: true,
  closeable: false,
  scrollY: 0,
};

const MAX_TABS = 15;

// ── Store ────────────────────────────────────────────────────────────────────

const useTabStore = create(
  persist(
    (set, get) => ({
      tabs: [DECISION_STREAM_TAB],
      activeTabId: DECISION_STREAM_TAB.id,

      // ── Open or focus a tab ────────────────────────────────────────────
      openTab: (path, label, opts = {}) => {
        const { tabs } = get();

        // Normalise path (strip trailing slash except for root)
        const normPath = path === '/' ? '/decision-stream' : path.replace(/\/$/, '');

        // Decision Stream special case
        if (normPath === '/decision-stream') {
          set({ activeTabId: DECISION_STREAM_TAB.id });
          return DECISION_STREAM_TAB.id;
        }

        // Already open? Focus it.
        const existing = tabs.find((t) => t.path === normPath);
        if (existing) {
          set({ activeTabId: existing.id });
          return existing.id;
        }

        // Enforce tab limit — close oldest non-pinned tab
        const nonPinned = tabs.filter((t) => !t.pinned);
        let nextTabs = [...tabs];
        if (nonPinned.length >= MAX_TABS) {
          const oldest = nonPinned[0];
          nextTabs = nextTabs.filter((t) => t.id !== oldest.id);
        }

        const newTab = {
          id: makeId(),
          path: normPath,
          label: label || normPath.split('/').filter(Boolean).pop()?.replace(/-/g, ' ') || 'New Tab',
          pinned: false,
          closeable: true,
          scrollY: 0,
          ...opts,
        };

        nextTabs.push(newTab);
        set({ tabs: nextTabs, activeTabId: newTab.id });
        return newTab.id;
      },

      // ── Close a tab ────────────────────────────────────────────────────
      closeTab: (id) => {
        const { tabs, activeTabId } = get();
        const tab = tabs.find((t) => t.id === id);
        if (!tab || tab.pinned) return;

        const idx = tabs.indexOf(tab);
        const nextTabs = tabs.filter((t) => t.id !== id);

        // If closing the active tab, focus the adjacent one
        let nextActive = activeTabId;
        if (activeTabId === id) {
          const fallback = nextTabs[Math.min(idx, nextTabs.length - 1)];
          nextActive = fallback?.id || DECISION_STREAM_TAB.id;
        }

        set({ tabs: nextTabs, activeTabId: nextActive });
      },

      // ── Focus a tab ────────────────────────────────────────────────────
      focusTab: (id) => {
        set({ activeTabId: id });
      },

      // ── Update tab label ───────────────────────────────────────────────
      updateTabLabel: (id, label) => {
        set((s) => ({
          tabs: s.tabs.map((t) => (t.id === id ? { ...t, label } : t)),
        }));
      },

      // ── Save scroll position before switching away ─────────────────────
      saveScrollPosition: (id, scrollY) => {
        set((s) => ({
          tabs: s.tabs.map((t) => (t.id === id ? { ...t, scrollY } : t)),
        }));
      },

      // ── Get active tab ─────────────────────────────────────────────────
      getActiveTab: () => {
        const { tabs, activeTabId } = get();
        return tabs.find((t) => t.id === activeTabId) || tabs[0];
      },

      // ── Close all non-pinned tabs ──────────────────────────────────────
      closeOtherTabs: (keepId) => {
        set((s) => ({
          tabs: s.tabs.filter((t) => t.pinned || t.id === keepId),
          activeTabId: keepId || DECISION_STREAM_TAB.id,
        }));
      },

      // ── Ensure Decision Stream tab always exists ───────────────────────
      ensureDecisionStream: () => {
        const { tabs } = get();
        if (!tabs.find((t) => t.id === DECISION_STREAM_TAB.id)) {
          set({ tabs: [DECISION_STREAM_TAB, ...tabs] });
        }
      },
    }),
    {
      name: 'autonomy-tabs',
      storage: {
        getItem: (name) => {
          const str = sessionStorage.getItem(name);
          return str ? JSON.parse(str) : null;
        },
        setItem: (name, value) => sessionStorage.setItem(name, JSON.stringify(value)),
        removeItem: (name) => sessionStorage.removeItem(name),
      },
      // Only persist tabs + activeTabId (not functions)
      partialize: (state) => ({
        tabs: state.tabs,
        activeTabId: state.activeTabId,
      }),
      onRehydrate: (_state, options) => {
        // After rehydration, ensure Decision Stream tab exists
        return (state) => {
          if (state) {
            state.ensureDecisionStream();
          }
        };
      },
    },
  ),
);

export default useTabStore;
