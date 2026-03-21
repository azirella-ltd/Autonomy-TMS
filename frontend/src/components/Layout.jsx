/**
 * Main Layout Component — Hierarchical Tab Navigation
 *
 * Replaces the sidebar with two-tier tab navigation:
 * - Top level: Category tabs (Decision Stream, Planning, Execution, AI, Admin)
 * - Second level: Capability tabs within the selected category
 *
 * Decision Stream is always the first tab and collapses all sub-tabs.
 * Tenant admins do NOT see Decision Stream — they land on Administration.
 */

import React, { useState } from 'react';
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

  // Active category state
  const [activeCategory, setActiveCategory] = useState(
    isDecisionStream ? 'decision_stream' : null
  );

  // Navigation config is the default export — an array of section objects
  const navConfig = NAVIGATION_CONFIG || [];

  return (
    <div className="min-h-screen bg-background">
      {/* Top Navbar */}
      <TopNavbar sidebarOpen={false} />

      {/* Hierarchical Tabs — below navbar */}
      <HierarchicalTabs
        navigationConfig={Array.isArray(navConfig) ? navConfig : []}
        activeCategory={activeCategory}
        onCategoryChange={setActiveCategory}
      />

      {/* Page Content — full width, no sidebar margin */}
      <main className={cn(
        'pb-6 px-6',
        // Decision Stream gets less top padding (tabs are thinner)
        isDecisionStream ? 'pt-4' : 'pt-4',
      )}>
        {children}
      </main>
    </div>
  );
};

export default Layout;
