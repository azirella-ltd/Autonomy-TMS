/**
 * CategoryBar — Tier 1 of the two-tier navigation.
 *
 * Horizontal row of section headers from navigationConfig.
 * Clicking a category reveals its child pages in the PageBar (Tier 2).
 * Decision Stream is pinned on the left and navigates directly (no Tier 2).
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Sparkles } from 'lucide-react';
import { cn } from '../lib/utils/cn';
import useTabStore from '../stores/useTabStore';

const CategoryBar = ({ sections, activeCategoryId, onSelectCategory, onOpenPalette, showDecisionStream }) => {
  const navigate = useNavigate();
  const openTab = useTabStore((s) => s.openTab);

  const handleDecisionStreamClick = () => {
    openTab('/decision-stream', 'Decision Stream');
    navigate('/decision-stream');
    // Clear active category so Tier 2 hides
    onSelectCategory(null);
  };

  const handleCategoryClick = (sectionId) => {
    if (activeCategoryId === sectionId) {
      // Toggle off if already active
      onSelectCategory(null);
    } else {
      onSelectCategory(sectionId);
      // Navigate to the first navigable page in this category
      const section = sections.find((s) => s.section === sectionId);
      if (section?.items) {
        const firstPage = section.items.find((item) => item.path && !item.isSectionHeader);
        if (firstPage) {
          openTab(firstPage.path, firstPage.label);
          navigate(firstPage.path);
        }
      }
    }
  };

  return (
    <div className="flex items-center bg-background border-b border-border h-9 px-1 flex-shrink-0">
      {/* Decision Stream — pinned left */}
      {showDecisionStream && (
        <button
          onClick={handleDecisionStreamClick}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium flex-shrink-0',
            'transition-colors duration-100 rounded-sm',
            'hover:bg-muted/80',
            // Highlight when no category is active and we're on decision-stream
            activeCategoryId === null
              ? 'text-violet-700'
              : 'text-muted-foreground',
          )}
          title="Decision Stream"
        >
          <Sparkles className="h-4 w-4 text-violet-500" />
          <span className="hidden sm:inline">Decision Stream</span>
        </button>
      )}

      {/* Separator */}
      {showDecisionStream && sections.length > 0 && (
        <div className="w-px h-5 bg-border mx-1 flex-shrink-0" />
      )}

      {/* Category tabs — scrollable */}
      <div className="flex items-center flex-1 overflow-x-auto scrollbar-none gap-0.5">
        {sections.map((section) => {
          const SectionIcon = section.sectionIcon;
          const isActive = activeCategoryId === section.section;
          return (
            <button
              key={section.section}
              onClick={() => handleCategoryClick(section.section)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium flex-shrink-0',
                'transition-colors duration-100 rounded-sm relative',
                'hover:bg-muted/80',
                isActive
                  ? 'text-foreground'
                  : 'text-muted-foreground',
              )}
              title={section.section}
            >
              {SectionIcon && <SectionIcon className="h-4 w-4 flex-shrink-0" />}
              <span className="whitespace-nowrap">{section.section}</span>
              {/* Active indicator — bottom border */}
              {isActive && (
                <span className="absolute bottom-0 left-1 right-1 h-0.5 bg-violet-600 rounded-full" />
              )}
            </button>
          );
        })}
      </div>

      {/* "+" button — open palette */}
      <button
        onClick={onOpenPalette}
        className="flex items-center justify-center h-7 w-7 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors flex-shrink-0 ml-1"
        title="Open page in new tab (Ctrl+T)"
      >
        <Plus className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};

export default CategoryBar;
