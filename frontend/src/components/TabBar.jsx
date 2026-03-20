/**
 * TabBar — Horizontal tab strip for the workspace shell.
 *
 * Renders below the TopNavbar. Decision Stream is always pinned first.
 * Other tabs have close buttons. '+' button at the end for new tabs.
 */

import React, { useRef, useEffect } from 'react';
import { Plus, X, Sparkles } from 'lucide-react';
import useTabStore from '../stores/useTabStore';
import { cn } from '../lib/utils/cn';

const TabBar = () => {
  const tabs = useTabStore((s) => s.tabs);
  const activeTabId = useTabStore((s) => s.activeTabId);
  const focusTab = useTabStore((s) => s.focusTab);
  const closeTab = useTabStore((s) => s.closeTab);
  const openTab = useTabStore((s) => s.openTab);
  const scrollRef = useRef(null);

  // Scroll active tab into view when it changes
  useEffect(() => {
    const el = document.getElementById(`tab-${activeTabId}`);
    if (el && scrollRef.current) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
    }
  }, [activeTabId]);

  const handleMiddleClick = (e, tab) => {
    if (e.button === 1 && tab.closeable) {
      e.preventDefault();
      closeTab(tab.id);
    }
  };

  const handleNewTab = () => {
    // Open a blank "New" tab — user will type into Azirella to populate it
    openTab('/dashboard', 'Dashboard');
  };

  return (
    <div className="flex items-center bg-background border-b border-border h-10 px-1 flex-shrink-0 overflow-hidden">
      {/* Scrollable tab strip */}
      <div
        ref={scrollRef}
        className="flex items-center flex-1 overflow-x-auto scrollbar-none gap-0.5"
      >
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          return (
            <button
              key={tab.id}
              id={`tab-${tab.id}`}
              onClick={() => focusTab(tab.id)}
              onMouseDown={(e) => handleMiddleClick(e, tab)}
              className={cn(
                'group flex items-center gap-1.5 px-3 h-8 rounded-t-md text-xs font-medium',
                'transition-all duration-100 flex-shrink-0 max-w-[200px] min-w-[80px]',
                'border border-b-0',
                isActive
                  ? 'bg-background border-border text-foreground shadow-sm -mb-px z-10'
                  : 'bg-muted/30 border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/60',
              )}
              title={tab.label}
            >
              {/* Icon for Decision Stream */}
              {tab.pinned && <Sparkles className="h-3 w-3 text-violet-500 flex-shrink-0" />}

              {/* Label */}
              <span className="truncate capitalize">{tab.label}</span>

              {/* Close button */}
              {tab.closeable && (
                <span
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(tab.id);
                  }}
                  className={cn(
                    'flex items-center justify-center h-4 w-4 rounded-sm flex-shrink-0',
                    'opacity-0 group-hover:opacity-100 transition-opacity',
                    'hover:bg-destructive/10 hover:text-destructive',
                  )}
                  title="Close tab"
                >
                  <X className="h-3 w-3" />
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* New tab button */}
      <button
        onClick={handleNewTab}
        className="flex items-center justify-center h-7 w-7 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors flex-shrink-0 ml-1"
        title="New tab (Dashboard)"
      >
        <Plus className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};

export default TabBar;
