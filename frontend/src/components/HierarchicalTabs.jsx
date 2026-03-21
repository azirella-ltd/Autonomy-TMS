/**
 * HierarchicalTabs — Replaces sidebar with two-tier tab navigation.
 *
 * Top level: Category tabs (Decision Stream, Planning, Execution, AI, Admin, etc.)
 * Second level: Capability tabs within the selected category
 *
 * Behavior:
 * - Decision Stream is always the first tab
 * - Selecting Decision Stream collapses all sub-tabs (immersive mode)
 * - Selecting another category shows its sub-tabs
 * - Only one category active at a time
 * - Tabs are filtered by user capabilities
 * - Tenant Admin sees Admin tab but NOT Decision Stream
 */

import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useCapabilities } from '../hooks/useCapabilities';
import { useAuth } from '../contexts/AuthContext';
import { cn } from '../lib/utils/cn';

// ── Category definitions ────────────────────────────────────────────────────
// Maps navigation sections to consolidated top-level tabs.
// Each category has a label, icon, color, and the section names from
// navigationConfig.js that it contains.

const CATEGORIES = [
  {
    key: 'decision_stream',
    label: 'Decision Stream',
    icon: '⚡',
    path: '/',
    color: 'border-purple-500 text-purple-700 bg-purple-50',
    activeColor: 'border-purple-600 bg-purple-600 text-white',
    sections: [],  // No sub-tabs — immersive mode
    // Decision Stream is visible to ALL users including tenant admins.
    // The tenant admin needs to see what agents are doing.
  },
  {
    key: 'insights',
    label: 'Insights',
    icon: '📊',
    color: 'border-blue-400 text-blue-700 bg-blue-50',
    activeColor: 'border-blue-600 bg-blue-600 text-white',
    sections: ['Home', 'Insights & Analytics'],
  },
  {
    key: 'planning',
    label: 'Planning',
    icon: '📋',
    color: 'border-green-400 text-green-700 bg-green-50',
    activeColor: 'border-green-600 bg-green-600 text-white',
    sections: ['Planning', 'Planning Cascade'],
  },
  {
    key: 'execution',
    label: 'Execution',
    icon: '🔄',
    color: 'border-orange-400 text-orange-700 bg-orange-50',
    activeColor: 'border-orange-600 bg-orange-600 text-white',
    sections: ['Execution'],
  },
  {
    key: 'scenarios',
    label: 'Scenarios',
    icon: '🔀',
    color: 'border-cyan-400 text-cyan-700 bg-cyan-50',
    activeColor: 'border-cyan-600 bg-cyan-600 text-white',
    sections: ['Scenarios'],
  },
  {
    key: 'ai',
    label: 'AI & Agents',
    icon: '🧠',
    color: 'border-violet-400 text-violet-700 bg-violet-50',
    activeColor: 'border-violet-600 bg-violet-600 text-white',
    sections: ['AI & Agents'],
  },
  {
    key: 'deployment',
    label: 'Deployment',
    icon: '🚀',
    color: 'border-gray-400 text-gray-700 bg-gray-50',
    activeColor: 'border-gray-600 bg-gray-600 text-white',
    sections: ['Deployment'],
    adminOnly: true,
  },
  {
    key: 'admin',
    label: 'Administration',
    icon: '⚙️',
    color: 'border-gray-400 text-gray-700 bg-gray-50',
    activeColor: 'border-gray-600 bg-gray-600 text-white',
    sections: ['Administration', 'System Administration'],
    adminOnly: true,
  },
];


const HierarchicalTabs = ({ navigationConfig = [], activeCategory, onCategoryChange, onItemClick }) => {
  const { hasCapability } = useCapabilities();
  const { user, isTenantAdmin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const isUserTenantAdmin = user?.user_type === 'TENANT_ADMIN' && !hasCapability('demo_all_access');

  // Build the sub-items for the active category from navigationConfig
  const categoryItems = useMemo(() => {
    if (!activeCategory || activeCategory === 'decision_stream') return [];

    const cat = CATEGORIES.find(c => c.key === activeCategory);
    if (!cat) return [];

    // Find matching sections in navigationConfig
    const items = [];
    for (const section of navigationConfig) {
      if (cat.sections.includes(section.section)) {
        for (const item of (section.items || [])) {
          // Check capability
          if (item.requiredCapability && !hasCapability(item.requiredCapability)) continue;
          items.push(item);
        }
      }
    }
    return items;
  }, [activeCategory, navigationConfig, hasCapability]);

  // Determine active category from current path
  useEffect(() => {
    const path = location.pathname;
    if (path === '/' || path === '/decision-stream') {
      if (activeCategory !== 'decision_stream') onCategoryChange?.('decision_stream');
      return;
    }
    // Find which category contains the current path
    for (const cat of CATEGORIES) {
      for (const section of navigationConfig) {
        if (cat.sections.includes(section.section)) {
          for (const item of (section.items || [])) {
            if (item.path === path) {
              if (activeCategory !== cat.key) onCategoryChange?.(cat.key);
              return;
            }
          }
        }
      }
    }
  }, [location.pathname, navigationConfig]);

  // Filter categories by capability and user type.
  // Most users have narrow access — only show categories with accessible items.
  // An ATP analyst might see just: [Decision Stream] [ATP Worklist]
  const visibleCategories = useMemo(() => {
    return CATEGORIES.filter(cat => {
      // No categories are hidden from tenant admin — they need full visibility
      if (cat.adminOnly && !isTenantAdmin) return false;
      if (cat.key === 'decision_stream') return true;

      // Count accessible items in this category
      let accessibleCount = 0;
      for (const section of navigationConfig) {
        if (cat.sections.includes(section.section)) {
          for (const item of (section.items || [])) {
            if (!item.requiredCapability || hasCapability(item.requiredCapability)) {
              accessibleCount++;
            }
          }
        }
      }
      return accessibleCount > 0;
    });
  }, [navigationConfig, hasCapability, isTenantAdmin, isUserTenantAdmin]);

  // For narrow-scope users (≤3 categories), if a category has only 1 item,
  // show it as a direct tab instead of a category with sub-tabs.
  const flattenedCategories = useMemo(() => {
    return visibleCategories.map(cat => {
      if (cat.key === 'decision_stream') return { ...cat, singleItem: null };
      let items = [];
      for (const section of navigationConfig) {
        if (cat.sections.includes(section.section)) {
          for (const item of (section.items || [])) {
            if (!item.requiredCapability || hasCapability(item.requiredCapability)) {
              items.push(item);
            }
          }
        }
      }
      // If only 1 item in the category, flatten it to a direct link
      if (items.length === 1) {
        return { ...cat, singleItem: items[0], label: items[0].label };
      }
      return { ...cat, singleItem: null };
    });
  }, [visibleCategories, navigationConfig, hasCapability]);

  const handleCategoryClick = (catKey) => {
    onCategoryChange?.(catKey);
    if (catKey === 'decision_stream') {
      navigate('/');
    }
  };

  const handleItemClick = (item) => {
    navigate(item.path);
    onItemClick?.(item);
  };

  return (
    <div className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80 sticky top-16 z-40">
      {/* Top-level category tabs */}
      <div className="flex items-center gap-1 px-4 py-1.5 overflow-x-auto scrollbar-hide">
        {flattenedCategories.map(cat => {
          const isActive = activeCategory === cat.key;
          return (
            <button
              key={cat.key}
              onClick={() => {
                if (cat.singleItem) {
                  // Single-item category — navigate directly
                  navigate(cat.singleItem.path);
                  onCategoryChange?.(cat.key);
                } else {
                  handleCategoryClick(cat.key);
                }
              }}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium',
                'border transition-all duration-150 whitespace-nowrap flex-shrink-0',
                isActive ? cat.activeColor : cat.color,
                !isActive && 'hover:shadow-sm',
              )}
            >
              <span className="text-sm">{cat.icon}</span>
              {cat.label}
            </button>
          );
        })}
      </div>

      {/* Second-level capability tabs (hidden when Decision Stream is active) */}
      {activeCategory && activeCategory !== 'decision_stream' && categoryItems.length > 0 && (
        <div className="flex items-center gap-0.5 px-4 py-1 overflow-x-auto scrollbar-hide border-t border-muted/50 bg-muted/20">
          {categoryItems.map(item => {
            const isActive = location.pathname === item.path;
            return (
              <button
                key={item.path}
                onClick={() => handleItemClick(item)}
                title={item.description}
                className={cn(
                  'px-2.5 py-1 rounded text-xs whitespace-nowrap transition-colors',
                  isActive
                    ? 'bg-primary text-primary-foreground font-medium'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
                )}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default HierarchicalTabs;
