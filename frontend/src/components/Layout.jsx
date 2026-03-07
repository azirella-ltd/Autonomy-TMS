/**
 * Main Layout Component - Autonomy UI Kit Version
 *
 * Provides the main application layout with sidebar and top navbar.
 * Uses Tailwind CSS for styling with CSS variables for theming.
 */

import React, { useState, useEffect } from 'react';
import CapabilityAwareSidebar from './CapabilityAwareSidebar';
import TopNavbar from './TopNavbar';
import { cn } from '../lib/utils/cn';

const Layout = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Persist sidebar state
  useEffect(() => {
    const saved = localStorage.getItem('sidebar:state');
    if (saved !== null) {
      setSidebarOpen(saved === 'true');
    }
  }, []);

  const handleSidebarToggle = () => {
    const newState = !sidebarOpen;
    setSidebarOpen(newState);
    localStorage.setItem('sidebar:state', String(newState));
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Left Sidebar - Uses navigationConfig.js as single source of truth */}
      <CapabilityAwareSidebar open={sidebarOpen} onToggle={handleSidebarToggle} />

      {/* Main Content Area */}
      <div
        className={cn(
          'min-h-screen transition-all duration-200 ease-in-out',
          sidebarOpen ? 'ml-[280px]' : 'ml-[65px]'
        )}
      >
        {/* Top Navbar */}
        <TopNavbar sidebarOpen={sidebarOpen} />

        {/* Page Content */}
        <main className="pt-20 pb-6 px-6">
          {children}
        </main>
      </div>
    </div>
  );
};

export default Layout;
