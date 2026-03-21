/**
 * Main Layout Component — Split Screen with Azirella Panel
 *
 * Desktop: Content (left) | Azirella (right, resizable)
 * Mobile: Full-width content with bottom Azirella bar
 *
 * Hierarchical tabs sit below the navbar for category navigation.
 * The Azirella panel is persistent — conversation survives page navigation.
 */

import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import TopNavbar from './TopNavbar';
import HierarchicalTabs from './HierarchicalTabs';
import NAVIGATION_CONFIG from '../config/navigationConfig';
import { useAuth } from '../contexts/AuthContext';
import { cn } from '../lib/utils/cn';

const Layout = ({ children }) => {
  const location = useLocation();
  const { user } = useAuth();
  const isDecisionStream = location.pathname === '/' || location.pathname === '/decision-stream';

  // Active category state for hierarchical tabs
  const [activeCategory, setActiveCategory] = useState(
    isDecisionStream ? 'decision_stream' : null
  );

  // Azirella panel state
  const [azirellaPanelOpen, setAzirellaPanelOpen] = useState(() => {
    const saved = localStorage.getItem('azirella:panel-open');
    return saved === 'true';
  });

  const azirellaPanelWidth = parseInt(localStorage.getItem('azirella:panel-width') || '380', 10);

  useEffect(() => {
    localStorage.setItem('azirella:panel-open', String(azirellaPanelOpen));
  }, [azirellaPanelOpen]);

  // Navigation config
  const navConfig = NAVIGATION_CONFIG || [];

  // Content margin adjusts when panel is open
  const contentMarginRight = azirellaPanelOpen ? azirellaPanelWidth : 0;

  return (
    <div className="min-h-screen bg-background">
      {/* Top Navbar — passes panel toggle */}
      <TopNavbar
        sidebarOpen={false}
        azirellaPanelOpen={azirellaPanelOpen}
        onToggleAzirellaPanel={() => setAzirellaPanelOpen(v => !v)}
      />

      {/* Hierarchical Tabs — adjusts with panel */}
      <div style={{ marginRight: contentMarginRight }} className="transition-[margin] duration-200">
        <HierarchicalTabs
          navigationConfig={Array.isArray(navConfig) ? navConfig : []}
          activeCategory={activeCategory}
          onCategoryChange={setActiveCategory}
        />
      </div>

      {/* Page Content — left side, adjusts when panel is open */}
      <main
        className="pb-6 px-6 pt-4 transition-[margin] duration-200"
        style={{ marginRight: contentMarginRight }}
      >
        {children}
      </main>

      {/* Azirella Panel toggle strip (when collapsed) */}
      {!azirellaPanelOpen && (
        <button
          onClick={() => setAzirellaPanelOpen(true)}
          className="fixed right-0 top-1/2 -translate-y-1/2 z-40 bg-violet-500 text-white px-1.5 py-6 rounded-l-lg shadow-lg hover:bg-violet-600 transition-colors"
          title="Open Azirella"
        >
          <div className="flex flex-col items-center gap-1">
            <img src="/azirella_avatar.svg" alt="" className="h-5 w-5 opacity-90" onError={(e) => {e.target.style.display='none';}} />
            <span className="text-[9px] font-medium"
              style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}>
              Azirella
            </span>
          </div>
        </button>
      )}
    </div>
  );
};

export default Layout;
