/**
 * TwoTierNav — Two-tier horizontal navigation bar.
 *
 * Tier 1 (CategoryBar): Section headers from navigationConfig (Home, Planning, etc.)
 * Tier 2 (PageBar): Child pages of the selected category.
 *
 * Replaces the flat TabBar. Integrates with useTabStore for tab management
 * and useNavStore for persisting the active category selection.
 */

import React, { useState, useEffect, useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import CategoryBar from './CategoryBar';
import PageBar from './PageBar';
import NewTabPalette from './NewTabPalette';
import useNavStore from '../stores/useNavStore';
import { useAuth } from '../contexts/AuthContext';
import { useCapabilities } from '../hooks/useCapabilities';
import { useActiveConfig } from '../contexts/ActiveConfigContext';
import { getFilteredNavigation } from '../config/navigationConfig';
import { isSystemAdmin, isTenantAdmin as checkIsTenantAdmin } from '../utils/authUtils';

const TwoTierNav = () => {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const location = useLocation();

  const { user } = useAuth();
  const { hasCapability, loading: capLoading } = useCapabilities();
  const { configMode, loading: cfgLoading } = useActiveConfig();

  const activeCategoryId = useNavStore((s) => s.activeCategoryId);
  const setActiveCategory = useNavStore((s) => s.setActiveCategory);

  const isSysAdmin = isSystemAdmin(user);
  const isGrpAdmin = checkIsTenantAdmin(user);

  // Build filtered navigation sections
  const filteredSections = useMemo(() => {
    if (capLoading || cfgLoading) return [];
    return getFilteredNavigation(hasCapability, isSysAdmin, isGrpAdmin, configMode);
  }, [hasCapability, isSysAdmin, isGrpAdmin, configMode, capLoading, cfgLoading]);

  // Determine if Decision Stream should show (not for admin-only users)
  const showDecisionStream = !isSysAdmin && !isGrpAdmin;

  // Sync URL -> active category on navigation
  useEffect(() => {
    const path = location.pathname;

    // Decision Stream path — clear category
    if (path === '/decision-stream' || path === '/') {
      // Don't force category to null here — let the user's explicit category choice stand
      // unless they navigated to decision stream
      if (path === '/decision-stream') {
        setActiveCategory(null);
      }
      return;
    }

    // Find which section contains a page matching the current path
    for (const section of filteredSections) {
      const match = (section.items || []).find(
        (item) => item.path && !item.isSectionHeader && item.path === path,
      );
      if (match) {
        if (activeCategoryId !== section.section) {
          setActiveCategory(section.section);
        }
        return;
      }
    }

    // No exact match — try prefix matching (for nested routes like /admin/users/123)
    for (const section of filteredSections) {
      const match = (section.items || []).find(
        (item) => item.path && !item.isSectionHeader && path.startsWith(item.path),
      );
      if (match) {
        if (activeCategoryId !== section.section) {
          setActiveCategory(section.section);
        }
        return;
      }
    }
    // Path doesn't match any section — leave category as-is
  }, [location.pathname, filteredSections]); // eslint-disable-line react-hooks/exhaustive-deps

  // Get items for the active category
  const activeSectionItems = useMemo(() => {
    if (!activeCategoryId) return [];
    const section = filteredSections.find((s) => s.section === activeCategoryId);
    return section?.items || [];
  }, [activeCategoryId, filteredSections]);

  // Ctrl+T opens palette
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 't') {
        e.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  return (
    <>
      {/* Tier 1 — Category bar */}
      <CategoryBar
        sections={filteredSections}
        activeCategoryId={activeCategoryId}
        onSelectCategory={setActiveCategory}
        onOpenPalette={() => setPaletteOpen(true)}
        showDecisionStream={showDecisionStream}
      />

      {/* Tier 2 — Page bar (only when a category is selected and has items) */}
      {activeCategoryId && activeSectionItems.length > 0 && (
        <PageBar items={activeSectionItems} />
      )}

      {/* Command palette overlay */}
      <NewTabPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </>
  );
};

export default TwoTierNav;
