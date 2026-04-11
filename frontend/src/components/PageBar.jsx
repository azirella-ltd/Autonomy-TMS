/**
 * PageBar — Tier 2 of the two-tier navigation.
 *
 * Shows the child pages of the currently selected category (Tier 1).
 * Clicking a page item opens it as a tab and navigates to it.
 * Section headers render as small muted dividers.
 */

import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { cn } from '@azirella-ltd/autonomy-frontend';
import useTabStore from '../stores/useTabStore';

const PageBar = ({ items }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const openTab = useTabStore((s) => s.openTab);

  if (!items || items.length === 0) return null;

  const handlePageClick = (item) => {
    if (!item.path || item.isSectionHeader) return;
    openTab(item.path, item.label);
    navigate(item.path);
  };

  return (
    <div className="flex items-center bg-muted/30 border-b border-border h-8 px-1 flex-shrink-0 overflow-hidden">
      <div className="flex items-center flex-1 overflow-x-auto scrollbar-none gap-0.5">
        {items.map((item, idx) => {
          if (item.isSectionHeader) {
            return (
              <span
                key={`hdr-${idx}`}
                className="flex items-center px-2 py-1 text-[10px] uppercase tracking-wider text-muted-foreground/60 font-semibold flex-shrink-0 select-none"
              >
                {item.label.replace(/^—\s*/, '').replace(/\s*—$/, '')}
              </span>
            );
          }

          const isActive = location.pathname === item.path;
          const Icon = item.icon;

          return (
            <button
              key={item.path || `item-${idx}`}
              onClick={() => handlePageClick(item)}
              className={cn(
                'flex items-center gap-1 px-2 py-1 text-xs font-medium flex-shrink-0',
                'transition-colors duration-100 rounded-sm relative whitespace-nowrap',
                'hover:bg-muted/80',
                isActive
                  ? 'text-foreground'
                  : 'text-muted-foreground',
              )}
              title={item.description || item.label}
            >
              {Icon && <Icon className="h-3.5 w-3.5 flex-shrink-0" />}
              <span>{item.label}</span>
              {/* Active indicator */}
              {isActive && (
                <span className="absolute bottom-0 left-1 right-1 h-0.5 bg-violet-600 rounded-full" />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default PageBar;
