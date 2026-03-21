/**
 * AzirellaPanel — Persistent right-side assistant panel.
 *
 * Provides a DOM target (#azirella-panel-root) that TopNavbar portals
 * its input + AzirellaPopup content into when the panel is open.
 *
 * Desktop: side panel with resizable width
 * Mobile: full-screen overlay
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { cn } from '../lib/utils/cn';
import { ChevronRight } from 'lucide-react';

const MIN_PANEL_WIDTH = 300;
const MAX_PANEL_PCT = 50;
const DEFAULT_WIDTH = 380;

const AzirellaPanel = ({ isOpen, onToggle }) => {
  const [panelWidth, setPanelWidth] = useState(() => {
    const saved = localStorage.getItem('azirella:panel-width');
    return saved ? parseInt(saved, 10) : DEFAULT_WIDTH;
  });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);

  useEffect(() => {
    if (panelWidth > 0) localStorage.setItem('azirella:panel-width', String(panelWidth));
  }, [panelWidth]);

  const handleMouseDown = useCallback((e) => {
    e.preventDefault();
    setIsDragging(true);
    dragStartX.current = e.clientX;
    dragStartWidth.current = panelWidth;
  }, [panelWidth]);

  useEffect(() => {
    if (!isDragging) return;
    const move = (e) => {
      const delta = dragStartX.current - e.clientX;
      setPanelWidth(Math.max(MIN_PANEL_WIDTH, Math.min(window.innerWidth * MAX_PANEL_PCT / 100, dragStartWidth.current + delta)));
    };
    const up = () => setIsDragging(false);
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up);
    return () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); };
  }, [isDragging]);

  // Mobile
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  if (!isOpen) return null;

  // Mobile: full screen overlay
  if (isMobile) {
    return (
      <div className="fixed inset-0 z-50 bg-background flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b flex-shrink-0">
          <div className="flex items-center gap-2">
            <img src="/azirella_avatar.svg" alt="" className="h-6 w-6" onError={(e) => {e.target.style.display='none';}} />
            <span className="font-semibold text-sm">Azirella</span>
          </div>
          <button onClick={onToggle} className="p-1.5 rounded-md hover:bg-muted">
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>
        {/* TopNavbar portals input + popup content here */}
        <div id="azirella-panel-root" className="flex-1 overflow-y-auto" />
      </div>
    );
  }

  // Desktop: right panel
  return (
    <div className="fixed right-0 top-16 bottom-0 z-30 flex" style={{ width: panelWidth }}>
      {/* Resizable divider */}
      <div
        onMouseDown={handleMouseDown}
        className={cn(
          'w-1.5 cursor-col-resize flex-shrink-0 transition-colors',
          isDragging ? 'bg-violet-400' : 'bg-border hover:bg-violet-300',
        )}
      />

      {/* Panel */}
      <div className="flex-1 flex flex-col bg-background border-l overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/30 flex-shrink-0">
          <div className="flex items-center gap-2">
            <img src="/azirella_avatar.svg" alt="" className="h-5 w-5" onError={(e) => {e.target.style.display='none';}} />
            <span className="font-semibold text-xs">Azirella</span>
          </div>
          <button onClick={onToggle} className="p-1 rounded-md hover:bg-muted text-muted-foreground" title="Close">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>

        {/* Portal target — TopNavbar renders its input + AzirellaPopup here */}
        <div id="azirella-panel-root" className="flex-1 overflow-y-auto" />
      </div>
    </div>
  );
};

export default AzirellaPanel;
