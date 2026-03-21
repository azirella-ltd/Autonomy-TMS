/**
 * Main Layout Component — Split Screen with Azirella Panel
 *
 * Desktop: Content (left) | Azirella (right, resizable)
 * Mobile: Full-width content + full-screen Azirella overlay
 *
 * TopNavbar portals its input + AzirellaPopup into the panel when open.
 * When panel is closed, input stays in the bottom bar (azirella-input-root).
 */

import React, { useState } from 'react';
import { useLocation } from 'react-router-dom';
import TopNavbar from './TopNavbar';
import HierarchicalTabs from './HierarchicalTabs';
import AzirellaPanel from './AzirellaPanel';
import NAVIGATION_CONFIG from '../config/navigationConfig';
import { useAuth } from '../contexts/AuthContext';
import { useAzirella } from '../contexts/AzirellaContext';

const Layout = ({ children }) => {
  const location = useLocation();
  const { user } = useAuth();
  const azirella = useAzirella();
  const isDecisionStream = location.pathname === '/' || location.pathname === '/decision-stream';

  const [activeCategory, setActiveCategory] = useState(
    isDecisionStream ? 'decision_stream' : null
  );

  const navConfig = NAVIGATION_CONFIG || [];
  const panelWidth = parseInt(localStorage.getItem('azirella:panel-width') || '380', 10);
  const contentMarginRight = azirella.panelOpen ? panelWidth : 0;

  return (
    <div className="min-h-screen bg-background">
      <TopNavbar
        sidebarOpen={false}
        azirellaPanelOpen={azirella.panelOpen}
        onToggleAzirellaPanel={azirella.togglePanel}
      />

      <div style={{ marginRight: contentMarginRight }} className="transition-[margin] duration-200">
        <HierarchicalTabs
          navigationConfig={Array.isArray(navConfig) ? navConfig : []}
          activeCategory={activeCategory}
          onCategoryChange={setActiveCategory}
        />
      </div>

      <main
        className="pb-6 px-6 pt-4 transition-[margin] duration-200"
        style={{ marginRight: contentMarginRight }}
      >
        {children}
      </main>

      {/* Azirella Panel — TopNavbar portals content into #azirella-panel-root */}
      <AzirellaPanel isOpen={azirella.panelOpen} onToggle={azirella.togglePanel} />

      {/* Bottom input bar target (when panel is closed) */}
      {!azirella.panelOpen && (
        <div id="azirella-input-root" className="fixed bottom-0 left-0 right-0 z-40" />
      )}

      {/* Collapsed toggle strip */}
      {!azirella.panelOpen && (
        <button
          onClick={azirella.openPanel}
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
