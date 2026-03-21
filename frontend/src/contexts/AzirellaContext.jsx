/**
 * AzirellaContext — Shared conversation state for the Azirella assistant.
 *
 * Lifts conversation state out of TopNavbar so it can be consumed by:
 * - TopNavbar (input bar in the header)
 * - AzirellaPanel (persistent right panel)
 * - Layout (panel open/close state)
 *
 * The actual LLM/API calls still happen in TopNavbar (or wherever the
 * handlers are). This context just shares the state and callbacks.
 */

import React, { createContext, useContext, useState, useCallback, useRef } from 'react';

const AzirellaContext = createContext(null);

export function AzirellaProvider({ children }) {
  // Panel state
  const [panelOpen, setPanelOpen] = useState(() => {
    if (typeof localStorage !== 'undefined') {
      const saved = localStorage.getItem('azirella:panel-open');
      // Default to OPEN on first visit (no saved preference)
      return saved === null ? true : saved === 'true';
    }
    return true;
  });

  const togglePanel = useCallback(() => {
    setPanelOpen(prev => {
      const next = !prev;
      localStorage.setItem('azirella:panel-open', String(next));
      return next;
    });
  }, []);

  const openPanel = useCallback(() => {
    setPanelOpen(true);
    localStorage.setItem('azirella:panel-open', 'true');
  }, []);

  // Conversation state (shared between navbar input and panel)
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);

  // Output tab state (for visualizations that need full-width rendering)
  const [outputContent, setOutputContent] = useState(null);
  const [outputTabVisible, setOutputTabVisible] = useState(false);

  const addMessage = useCallback((role, content, metadata = {}) => {
    setMessages(prev => [...prev, { role, content, timestamp: Date.now(), ...metadata }]);
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setOutputContent(null);
    setOutputTabVisible(false);
  }, []);

  // Show a visualization in the Azirella Output tab (left content area)
  const showOutput = useCallback((content) => {
    setOutputContent(content);
    setOutputTabVisible(true);
  }, []);

  const hideOutput = useCallback(() => {
    setOutputTabVisible(false);
  }, []);

  const value = {
    // Panel
    panelOpen,
    setPanelOpen,
    togglePanel,
    openPanel,
    // Conversation
    messages,
    setMessages,
    addMessage,
    clearMessages,
    inputValue,
    setInputValue,
    isProcessing,
    setIsProcessing,
    // Output tab
    outputContent,
    outputTabVisible,
    showOutput,
    hideOutput,
  };

  return (
    <AzirellaContext.Provider value={value}>
      {children}
    </AzirellaContext.Provider>
  );
}

export function useAzirella() {
  const ctx = useContext(AzirellaContext);
  if (!ctx) {
    throw new Error('useAzirella must be used within AzirellaProvider');
  }
  return ctx;
}

export default AzirellaContext;
