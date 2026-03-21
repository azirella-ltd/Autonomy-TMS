/**
 * Main Layout Component — Split Screen with Azirella Panel
 *
 * Desktop: Content (left) | Azirella (right, resizable)
 * Mobile: Full-width content + bottom Azirella bar
 */

import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import TopNavbar from './TopNavbar';
import HierarchicalTabs from './HierarchicalTabs';
import AzirellaPanel from './AzirellaPanel';
import NAVIGATION_CONFIG from '../config/navigationConfig';
import { useAuth } from '../contexts/AuthContext';

const Layout = ({ children }) => {
  const location = useLocation();
  const { user } = useAuth();
  const isDecisionStream = location.pathname === '/' || location.pathname === '/decision-stream';

  const [activeCategory, setActiveCategory] = useState(
    isDecisionStream ? 'decision_stream' : null
  );

  // Panel state — simple useState, no context needed
  const [panelOpen, setPanelOpen] = useState(() => {
    try {
      const saved = localStorage.getItem('azirella:panel-open');
      return saved === null ? true : saved === 'true';
    } catch { return true; }
  });

  useEffect(() => {
    try { localStorage.setItem('azirella:panel-open', String(panelOpen)); } catch {}
  }, [panelOpen]);

  const togglePanel = () => setPanelOpen(v => !v);

  const navConfig = NAVIGATION_CONFIG || [];
  const panelWidth = panelOpen ? parseInt(localStorage.getItem('azirella:panel-width') || '380', 10) : 0;

  return (
    <div className="min-h-screen bg-background">
      {/* Top Navbar */}
      <TopNavbar
        sidebarOpen={false}
        azirellaPanelOpen={panelOpen}
        onToggleAzirellaPanel={togglePanel}
      />

      {/* Hierarchical Tabs */}
      <div style={{ marginRight: panelWidth }} className="transition-[margin] duration-200">
        <HierarchicalTabs
          navigationConfig={Array.isArray(navConfig) ? navConfig : []}
          activeCategory={activeCategory}
          onCategoryChange={setActiveCategory}
        />
      </div>

      {/* Page Content */}
      <main
        className="pb-6 px-6 pt-4 transition-[margin] duration-200"
        style={{ marginRight: panelWidth }}
      >
        {children}
      </main>

      {/* Azirella Panel */}
      <AzirellaPanel isOpen={panelOpen} onToggle={togglePanel} />

      {/* Bottom input bar target (when panel is closed) */}
      {!panelOpen && (
        <div id="azirella-input-root" className="fixed bottom-0 left-0 right-0 z-40" />
      )}

      {/* Toggle strip when closed */}
      {!panelOpen && (
        <button
          onClick={() => setPanelOpen(true)}
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
