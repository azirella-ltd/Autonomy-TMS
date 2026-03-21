/**
 * Main Layout Component — Split Screen
 *
 * Content (left) | Azirella (right, fixed 380px)
 * The Azirella panel is ALWAYS visible. No toggle, no collapse.
 */

import React, { useState } from 'react';
import { useLocation } from 'react-router-dom';
import TopNavbar from './TopNavbar';
import HierarchicalTabs from './HierarchicalTabs';
import NAVIGATION_CONFIG from '../config/navigationConfig';
import { useAuth } from '../contexts/AuthContext';

const PANEL_WIDTH = 380;

const Layout = ({ children }) => {
  const location = useLocation();
  const { user } = useAuth();
  const isDecisionStream = location.pathname === '/' || location.pathname === '/decision-stream';

  const [activeCategory, setActiveCategory] = useState(
    isDecisionStream ? 'decision_stream' : null
  );

  const navConfig = NAVIGATION_CONFIG || [];

  return (
    <div className="min-h-screen bg-background">
      {/* Top Navbar */}
      <TopNavbar sidebarOpen={false} azirellaPanelOpen={true} onToggleAzirellaPanel={() => {}} />

      {/* Hierarchical Tabs */}
      <div style={{ marginRight: PANEL_WIDTH }} className="transition-[margin] duration-200">
        <HierarchicalTabs
          navigationConfig={Array.isArray(navConfig) ? navConfig : []}
          activeCategory={activeCategory}
          onCategoryChange={setActiveCategory}
        />
      </div>

      {/* Page Content — left side */}
      <main className="pb-6 px-6 pt-4" style={{ marginRight: PANEL_WIDTH }}>
        {children}
      </main>

      {/* Azirella Panel — ALWAYS visible, right side */}
      <div
        className="fixed right-0 top-16 bottom-0 z-30 flex border-l bg-background"
        style={{ width: PANEL_WIDTH }}
      >
        {/* Panel header */}
        <div className="flex flex-col w-full">
          <div className="flex items-center gap-2 px-3 py-2 border-b bg-muted/30 flex-shrink-0">
            <img src="/azirella_avatar.svg" alt="" className="h-5 w-5" onError={(e) => {e.target.style.display='none';}} />
            <span className="font-semibold text-xs">Azirella</span>
          </div>

          {/* Portal target — TopNavbar renders its input + AzirellaPopup here */}
          <div id="azirella-panel-root" className="flex-1 overflow-y-auto" />
        </div>
      </div>

      {/* Hidden bottom bar target (fallback — should not be needed) */}
      <div id="azirella-input-root" style={{ display: 'none' }} />
    </div>
  );
};

export default Layout;
