/**
 * Capability-Aware Sidebar Navigation Component
 *
 * Left-side collapsible navigation bar with RBAC integration.
 * Shows greyed-out items for capabilities user doesn't have.
 *
 * Migrated to Autonomy UI Kit (shadcn/ui + Tailwind CSS + lucide-react)
 */

import React, { useState, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ChevronLeft, ChevronRight, ChevronDown, ChevronUp } from 'lucide-react';
import { IconButton, Badge } from './common';
import { cn } from '../lib/utils/cn';
import { useAuth } from '../contexts/AuthContext';
import { useCapabilities } from '../hooks/useCapabilities';
import { useActiveConfig } from '../contexts/ActiveConfigContext';
import { getFilteredNavigation } from '../config/navigationConfig';
import { isSystemAdmin, isTenantAdmin as checkIsTenantAdmin } from '../utils/authUtils';

const DRAWER_WIDTH = 280;
const DRAWER_WIDTH_COLLAPSED = 65;

/**
 * Simple Tooltip wrapper component
 * Provides tooltip on hover using native title attribute with enhanced styling
 */
const Tooltip = ({ children, title, placement = 'right' }) => {
  if (!title) return children;

  return (
    <div className="group relative">
      {children}
      <div
        className={cn(
          'absolute z-50 hidden group-hover:block',
          'px-2 py-1 text-xs font-medium text-white bg-gray-900 rounded shadow-lg',
          'whitespace-nowrap pointer-events-none',
          placement === 'right' && 'left-full ml-2 top-1/2 -translate-y-1/2'
        )}
      >
        {title}
        <div
          className={cn(
            'absolute w-2 h-2 bg-gray-900 rotate-45',
            placement === 'right' && 'left-0 top-1/2 -translate-x-1/2 -translate-y-1/2'
          )}
        />
      </div>
    </div>
  );
};

const CapabilityAwareSidebar = ({ open, onToggle }) => {
  const { user } = useAuth();
  const { hasCapability, loading: capabilitiesLoading } = useCapabilities();
  // Use configMode from ActiveConfigContext so navigation reacts to config switches
  const { configMode, loading: configLoading } = useActiveConfig();
  const [expandedSections, setExpandedSections] = useState({});
  const navigate = useNavigate();
  const location = useLocation();

  const isSysAdmin = isSystemAdmin(user);
  const isGrpAdmin = checkIsTenantAdmin(user);

  // Get filtered navigation based on user capabilities and config mode
  const navigation = useMemo(() => {
    if (capabilitiesLoading || configLoading) return [];
    return getFilteredNavigation(hasCapability, isSysAdmin, isGrpAdmin, configMode);
  }, [hasCapability, isSysAdmin, isGrpAdmin, capabilitiesLoading, configLoading, configMode]);

  const handleSectionToggle = (sectionId) => {
    setExpandedSections((prev) => ({
      ...prev,
      [sectionId]: !prev[sectionId],
    }));
  };

  const isCurrentPath = (path) => {
    return location.pathname === path || location.pathname.startsWith(path + '/');
  };

  const handleNavigation = (path, disabled) => {
    if (disabled) return;
    navigate(path);
  };

  return (
    <aside
      className={cn(
        'fixed top-0 left-0 h-full bg-background border-r border-border',
        'transition-all duration-300 ease-in-out overflow-x-hidden z-40',
        'flex flex-col'
      )}
      style={{ width: open ? DRAWER_WIDTH : DRAWER_WIDTH_COLLAPSED }}
    >
      {/* Sidebar Header */}
      <div
        className={cn(
          'flex items-center min-h-[64px] p-4',
          open ? 'justify-between' : 'justify-center'
        )}
      >
        {open && (
          <div className="flex items-center">
            <img
              src="/autonomy_logo.svg"
              alt="Autonomy"
              className="h-7 w-auto mr-2"
            />
          </div>
        )}
        <IconButton onClick={onToggle} variant="ghost" size="sm">
          {open ? (
            <ChevronLeft className="h-5 w-5" />
          ) : (
            <ChevronRight className="h-5 w-5" />
          )}
        </IconButton>
      </div>

      <hr className="border-border" />

      {/* Navigation List */}
      <nav className="flex-1 overflow-y-auto px-2 py-2">
        {navigation.map((section, sectionIndex) => (
          <div key={section.section}>
            {section.divider && sectionIndex > 0 && (
              <hr className="my-2 border-border" />
            )}

            {/* Section Header */}
            <div className="mb-1">
              <button
                onClick={() => handleSectionToggle(section.section)}
                className={cn(
                  'w-full flex items-center rounded-md min-h-[40px] px-3',
                  'transition-colors',
                  open
                    ? 'bg-primary hover:bg-primary-hover text-primary-foreground'
                    : 'hover:bg-accent'
                )}
              >
                {open ? (
                  <>
                    <span className="flex-1 text-left text-xs font-bold uppercase tracking-wide">
                      {section.section}
                    </span>
                    {expandedSections[section.section] ? (
                      <ChevronUp className="h-4 w-4" />
                    ) : (
                      <ChevronDown className="h-4 w-4" />
                    )}
                  </>
                ) : (
                  <hr className="w-full border-border" />
                )}
              </button>
            </div>

            {/* Section Items - Expanded */}
            {open && expandedSections[section.section] && (
              <div className="space-y-0.5">
                {section.items.map((item, itemIndex) => {
                  // Handle section sub-headers (e.g., "— STRATEGIC —")
                  if (item.isSectionHeader) {
                    return (
                      <div
                        key={`header-${itemIndex}`}
                        className="pl-4 py-2 mt-2 first:mt-0"
                      >
                        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                          {item.label}
                        </span>
                      </div>
                    );
                  }

                  const Icon = item.icon;
                  const current = isCurrentPath(item.path);
                  const disabled = item.disabled || item.comingSoon;

                  const tooltipTitle = disabled
                    ? item.comingSoon
                      ? 'Coming Soon'
                      : `Requires: ${item.requiredCapability || 'Permission'}`
                    : '';

                  return (
                    <Tooltip key={item.path || `item-${itemIndex}`} title={tooltipTitle} placement="right">
                      <div className="pl-4">
                        <button
                          onClick={() => handleNavigation(item.path, disabled)}
                          disabled={disabled}
                          className={cn(
                            'w-full flex items-center rounded-md min-h-[40px] px-3 gap-3',
                            'transition-colors text-left',
                            disabled && 'opacity-40 cursor-not-allowed',
                            !disabled && 'cursor-pointer',
                            current
                              ? 'bg-primary/10 text-primary'
                              : !disabled && 'hover:bg-accent',
                            current && 'font-semibold'
                          )}
                        >
                          {Icon && (
                            <span className="w-6 flex items-center justify-center">
                              <Icon
                                fontSize="small"
                                className={cn(
                                  'h-5 w-5',
                                  current && 'text-primary',
                                  disabled && 'text-muted-foreground'
                                )}
                              />
                            </span>
                          )}
                          <span
                            className={cn(
                              'flex-1 text-sm',
                              current ? 'font-semibold' : 'font-normal'
                            )}
                          >
                            {item.label}
                          </span>
                          {item.comingSoon && (
                            <Badge size="sm" variant="secondary" className="ml-1 text-[10px] h-5">
                              Soon
                            </Badge>
                          )}
                        </button>
                      </div>
                    </Tooltip>
                  );
                })}
              </div>
            )}

            {/* Collapsed sidebar - show only icons (skip section headers) */}
            {!open &&
              section.items
                .filter((item) => !item.isSectionHeader && item.icon)
                .map((item, itemIndex) => {
                  const Icon = item.icon;
                  const current = isCurrentPath(item.path);
                  const disabled = item.disabled || item.comingSoon;

                  const tooltipTitle = disabled
                    ? item.comingSoon
                      ? `${item.label} - Coming Soon`
                      : `${item.label} - Requires: ${item.requiredCapability}`
                    : item.label;

                  return (
                    <Tooltip key={item.path || `collapsed-${itemIndex}`} title={tooltipTitle} placement="right">
                      <button
                        onClick={() => handleNavigation(item.path, disabled)}
                        disabled={disabled}
                        className={cn(
                          'w-full flex items-center justify-center rounded-md min-h-[40px]',
                          'transition-colors',
                          disabled && 'opacity-40 cursor-not-allowed',
                          !disabled && 'cursor-pointer',
                          current
                            ? 'bg-primary/10 text-primary'
                            : !disabled && 'hover:bg-accent'
                        )}
                      >
                        <Icon
                          fontSize="small"
                          className={cn(
                            'h-5 w-5',
                            current && 'text-primary',
                            disabled && 'text-muted-foreground'
                          )}
                        />
                      </button>
                    </Tooltip>
                  );
                })}
          </div>
        ))}
      </nav>
    </aside>
  );
};

export default CapabilityAwareSidebar;
