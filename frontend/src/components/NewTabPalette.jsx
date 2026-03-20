/**
 * NewTabPalette — Command palette for opening new tabs.
 *
 * Triggered by the '+' button in TabBar or Ctrl+T.
 * Shows a searchable list of all available navigation items
 * filtered by user capabilities.
 */

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, X } from 'lucide-react';
import { cn } from '../lib/utils/cn';
import { useAuth } from '../contexts/AuthContext';
import { useCapabilities } from '../hooks/useCapabilities';
import { useActiveConfig } from '../contexts/ActiveConfigContext';
import { getFilteredNavigation } from '../config/navigationConfig';
import { isSystemAdmin, isTenantAdmin as checkIsTenantAdmin } from '../utils/authUtils';
import useTabStore from '../stores/useTabStore';

const NewTabPalette = ({ open, onClose }) => {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef(null);
  const listRef = useRef(null);
  const navigate = useNavigate();

  const { user } = useAuth();
  const { hasCapability, loading: capLoading } = useCapabilities();
  const { configMode, loading: cfgLoading } = useActiveConfig();
  const openTab = useTabStore((s) => s.openTab);

  const isSysAdmin = isSystemAdmin(user);
  const isGrpAdmin = checkIsTenantAdmin(user);

  // Build flat list of all navigable items
  const allItems = useMemo(() => {
    if (capLoading || cfgLoading) return [];
    const nav = getFilteredNavigation(hasCapability, isSysAdmin, isGrpAdmin, configMode);
    const items = [];
    for (const section of nav) {
      for (const item of section.items || []) {
        if (item.isSectionHeader || !item.path || item.disabled) continue;
        items.push({
          label: item.label,
          path: item.path,
          section: section.section,
          icon: item.icon,
          description: item.description || '',
        });
      }
    }
    return items;
  }, [hasCapability, isSysAdmin, isGrpAdmin, configMode, capLoading, cfgLoading]);

  // Filter by search query
  const filtered = useMemo(() => {
    if (!query.trim()) return allItems;
    const lower = query.toLowerCase();
    return allItems.filter(
      (item) =>
        item.label.toLowerCase().includes(lower) ||
        item.section.toLowerCase().includes(lower) ||
        item.description.toLowerCase().includes(lower) ||
        item.path.toLowerCase().includes(lower),
    );
  }, [allItems, query]);

  // Reset selection when filter changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [filtered.length]);

  // Focus input when palette opens
  useEffect(() => {
    if (open) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Scroll selected item into view
  useEffect(() => {
    const el = listRef.current?.children[selectedIndex];
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex]);

  const handleSelect = (item) => {
    openTab(item.path, item.label);
    navigate(item.path);
    onClose();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filtered[selectedIndex]) handleSelect(filtered[selectedIndex]);
    } else if (e.key === 'Escape') {
      onClose();
    }
  };

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/30 backdrop-blur-[1px]"
        onClick={onClose}
      />

      {/* Palette */}
      <div
        className={cn(
          'fixed top-24 left-1/2 -translate-x-1/2 z-50',
          'w-full max-w-lg mx-4',
          'bg-popover border border-border rounded-xl shadow-2xl',
          'flex flex-col max-h-[60vh]',
          'animate-in fade-in slide-in-from-top-2 duration-150',
        )}
        onKeyDown={handleKeyDown}
      >
        {/* Search input */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
          <Search className="h-4 w-4 text-muted-foreground flex-shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search pages... (e.g. inventory, MPS, demand)"
            className="flex-1 bg-transparent text-sm outline-none text-foreground placeholder:text-muted-foreground"
            autoComplete="off"
          />
          <button
            onClick={onClose}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Results list */}
        <div ref={listRef} className="flex-1 overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-muted-foreground">
              No pages match "{query}"
            </div>
          ) : (
            filtered.map((item, i) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.path}
                  onClick={() => handleSelect(item)}
                  className={cn(
                    'w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors',
                    i === selectedIndex
                      ? 'bg-accent text-foreground'
                      : 'text-foreground hover:bg-accent/50',
                  )}
                >
                  {Icon && <Icon className="h-4 w-4 text-muted-foreground flex-shrink-0" />}
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">{item.label}</div>
                    <div className="text-[11px] text-muted-foreground truncate">
                      {item.section}
                      {item.description && ` — ${item.description}`}
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Footer hint */}
        <div className="px-4 py-2 border-t border-border text-[11px] text-muted-foreground flex gap-3">
          <span><kbd className="px-1 py-0.5 rounded bg-muted text-[10px]">↑↓</kbd> navigate</span>
          <span><kbd className="px-1 py-0.5 rounded bg-muted text-[10px]">Enter</kbd> open</span>
          <span><kbd className="px-1 py-0.5 rounded bg-muted text-[10px]">Esc</kbd> close</span>
        </div>
      </div>
    </>
  );
};

export default NewTabPalette;
