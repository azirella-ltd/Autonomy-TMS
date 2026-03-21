/**
 * AzirellaPanel — Persistent right-side assistant panel.
 *
 * Layout: Content (left, resizable) | Azirella (right, resizable)
 *
 * Desktop: side-by-side split with draggable divider
 * Mobile: bottom input bar, full-screen overlay when active
 *
 * Hosts the AzirellaPopup content in a persistent panel instead
 * of a floating overlay. All conversation state stays in TopNavbar.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { cn } from '../lib/utils/cn';
import { MessageSquare, ChevronLeft, ChevronRight, Mic, Send, Loader2 } from 'lucide-react';

const MIN_PANEL_WIDTH = 280;
const MAX_PANEL_WIDTH_PCT = 50; // Never more than 50% of screen
const DEFAULT_PANEL_WIDTH = 380;
const COLLAPSED_WIDTH = 0;

const AzirellaPanel = ({
  isOpen,
  onToggle,
  children, // The AzirellaPopup content rendered as children
  inputValue,
  onInputChange,
  onSubmit,
  submitting,
  onVoiceClick,
  voiceActive,
  placeholder = 'Ask Azirella...',
}) => {
  const [panelWidth, setPanelWidth] = useState(() => {
    const saved = localStorage.getItem('azirella:panel-width');
    return saved ? parseInt(saved, 10) : DEFAULT_PANEL_WIDTH;
  });
  const [isDragging, setIsDragging] = useState(false);
  const panelRef = useRef(null);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);

  // Persist width
  useEffect(() => {
    if (panelWidth > 0) {
      localStorage.setItem('azirella:panel-width', String(panelWidth));
    }
  }, [panelWidth]);

  // Drag handler for resizable divider
  const handleMouseDown = useCallback((e) => {
    e.preventDefault();
    setIsDragging(true);
    dragStartX.current = e.clientX;
    dragStartWidth.current = panelWidth;
  }, [panelWidth]);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e) => {
      const delta = dragStartX.current - e.clientX; // dragging left = wider panel
      const newWidth = Math.max(
        MIN_PANEL_WIDTH,
        Math.min(
          window.innerWidth * (MAX_PANEL_WIDTH_PCT / 100),
          dragStartWidth.current + delta
        )
      );
      setPanelWidth(newWidth);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging]);

  // Handle form submit
  const handleSubmit = (e) => {
    e?.preventDefault();
    if (inputValue?.trim() && onSubmit) {
      onSubmit(inputValue.trim());
    }
  };

  // Mobile detection
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  // ── Mobile: bottom bar + full-screen overlay ──────────────────────────
  if (isMobile) {
    return (
      <>
        {/* Full-screen overlay when open */}
        {isOpen && (
          <div className="fixed inset-0 z-50 bg-background flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <div className="flex items-center gap-2">
                <img src="/azirella_avatar.svg" alt="" className="h-6 w-6" onError={(e) => e.target.style.display='none'} />
                <span className="font-semibold text-sm">Azirella</span>
              </div>
              <button onClick={onToggle} className="p-1.5 rounded-md hover:bg-muted">
                <ChevronRight className="h-5 w-5" />
              </button>
            </div>

            {/* Conversation */}
            <div className="flex-1 overflow-y-auto px-4 py-3">
              {children}
            </div>

            {/* Input */}
            <form onSubmit={handleSubmit} className="border-t px-4 py-3 flex items-center gap-2">
              <button type="button" onClick={onVoiceClick} className={cn(
                'p-2 rounded-full transition-colors',
                voiceActive ? 'bg-red-500 text-white' : 'bg-muted text-muted-foreground hover:bg-muted/80'
              )}>
                <Mic className="h-4 w-4" />
              </button>
              <input
                type="text"
                value={inputValue || ''}
                onChange={(e) => onInputChange?.(e.target.value)}
                placeholder={placeholder}
                className="flex-1 border rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400/30"
              />
              <button
                type="submit"
                disabled={submitting || !inputValue?.trim()}
                className={cn(
                  'p-2 rounded-full transition-colors',
                  submitting ? 'bg-muted text-muted-foreground' : 'bg-violet-500 text-white hover:bg-violet-600'
                )}
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </button>
            </form>
          </div>
        )}

        {/* Bottom bar (always visible on mobile) */}
        {!isOpen && (
          <div className="fixed bottom-0 left-0 right-0 z-40 bg-background border-t px-4 py-2 flex items-center gap-2">
            <button onClick={onToggle} className="p-2 rounded-full bg-violet-500 text-white">
              <MessageSquare className="h-4 w-4" />
            </button>
            <input
              type="text"
              value={inputValue || ''}
              onChange={(e) => onInputChange?.(e.target.value)}
              onFocus={onToggle}
              placeholder={placeholder}
              className="flex-1 border rounded-full px-4 py-2 text-sm"
            />
          </div>
        )}
      </>
    );
  }

  // ── Desktop: right-side panel with resizable divider ──────────────────
  if (!isOpen) {
    // Collapsed — show a thin toggle strip on the right edge
    return (
      <button
        onClick={onToggle}
        className="fixed right-0 top-1/2 -translate-y-1/2 z-40 bg-violet-500 text-white p-2 rounded-l-lg shadow-lg hover:bg-violet-600 transition-colors"
        title="Open Azirella"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>
    );
  }

  return (
    <div
      ref={panelRef}
      className="fixed right-0 top-16 bottom-0 z-30 flex"
      style={{ width: panelWidth }}
    >
      {/* Resizable divider */}
      <div
        onMouseDown={handleMouseDown}
        className={cn(
          'w-1.5 cursor-col-resize flex-shrink-0 transition-colors',
          isDragging ? 'bg-violet-400' : 'bg-border hover:bg-violet-300',
        )}
      />

      {/* Panel content */}
      <div className="flex-1 flex flex-col bg-background border-l overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/30 flex-shrink-0">
          <div className="flex items-center gap-2">
            <img src="/azirella_avatar.svg" alt="" className="h-5 w-5" onError={(e) => e.target.style.display='none'} />
            <span className="font-semibold text-xs">Azirella</span>
          </div>
          <button
            onClick={onToggle}
            className="p-1 rounded-md hover:bg-muted text-muted-foreground"
            title="Close panel"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>

        {/* Conversation area */}
        <div className="flex-1 overflow-y-auto px-3 py-3">
          {children}
        </div>

        {/* Input area */}
        <form onSubmit={handleSubmit} className="border-t px-3 py-2 flex items-center gap-2 flex-shrink-0 bg-muted/10">
          <button
            type="button"
            onClick={onVoiceClick}
            className={cn(
              'p-1.5 rounded-full transition-colors flex-shrink-0',
              voiceActive ? 'bg-red-500 text-white' : 'text-muted-foreground hover:bg-muted'
            )}
          >
            <Mic className="h-3.5 w-3.5" />
          </button>
          <input
            type="text"
            value={inputValue || ''}
            onChange={(e) => onInputChange?.(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit();
              }
            }}
            placeholder={placeholder}
            className="flex-1 border rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400/30 bg-background"
          />
          <button
            type="submit"
            disabled={submitting || !inputValue?.trim()}
            className={cn(
              'p-1.5 rounded-full transition-colors flex-shrink-0',
              submitting ? 'text-muted-foreground' : 'text-violet-500 hover:bg-violet-50'
            )}
          >
            {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
          </button>
        </form>
      </div>
    </div>
  );
};

export default AzirellaPanel;
