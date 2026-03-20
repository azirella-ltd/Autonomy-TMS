/**
 * Main Layout Component - Autonomy UI Kit Version
 *
 * Provides the main application layout with sidebar and top navbar.
 * Uses Tailwind CSS for styling with CSS variables for theming.
 */

import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import CapabilityAwareSidebar from './CapabilityAwareSidebar';
import TopNavbar from './TopNavbar';
import { cn } from '../lib/utils/cn';

const Layout = ({ children }) => {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Auto-collapse sidebar on Decision Stream (immersive view)
  const isDecisionStream = location.pathname === '/' || location.pathname === '/decision-stream';

  // Persist sidebar state (only for non-Decision Stream pages)
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

  return (
    <div className="min-h-screen bg-background">
      {/* Left Sidebar - Auto-collapsed on Decision Stream for immersive view */}
      <CapabilityAwareSidebar
        open={isDecisionStream ? false : sidebarOpen}
        onToggle={handleSidebarToggle}
      />

      {/* Main Content Area */}
      <div
        className={cn(
          'min-h-screen transition-all duration-200 ease-in-out',
          (isDecisionStream ? false : sidebarOpen) ? 'ml-[280px]' : 'ml-[65px]'
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
