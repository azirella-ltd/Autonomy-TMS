/**
 * TabPane — Wrapper for a single tab's content.
 *
 * Uses display: block/none to keep inactive tabs alive in the DOM
 * (preserving component state, form inputs, scroll positions).
 * Saves/restores scroll position via the tab store.
 */

import React, { useRef, useEffect } from 'react';
import useTabStore from '../stores/useTabStore';

const TabPane = ({ tabId, active, children }) => {
  const containerRef = useRef(null);
  const saveScrollPosition = useTabStore((s) => s.saveScrollPosition);
  const tabs = useTabStore((s) => s.tabs);
  const tab = tabs.find((t) => t.id === tabId);
  const wasActiveRef = useRef(active);

  // Save scroll position when becoming inactive
  useEffect(() => {
    if (wasActiveRef.current && !active && containerRef.current) {
      saveScrollPosition(tabId, containerRef.current.scrollTop);
    }
    wasActiveRef.current = active;
  }, [active, tabId, saveScrollPosition]);

  // Restore scroll position when becoming active
  useEffect(() => {
    if (active && containerRef.current && tab?.scrollY) {
      // Small delay to let content render before scrolling
      requestAnimationFrame(() => {
        containerRef.current?.scrollTo(0, tab.scrollY);
      });
    }
  }, [active, tab?.scrollY]);

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto"
      style={{ display: active ? 'block' : 'none' }}
      data-tab-id={tabId}
    >
      <main className="pb-6 px-6 pt-4">
        {children}
      </main>
    </div>
  );
};

export default TabPane;
