/**
 * Decision Stream Page — LLM-First UI with Decision-Back Planning
 *
 * The default landing experience for all Powell-role users. Presents
 * pending TRM decisions in a conversational "inbox" format with:
 *   - Inbox section: shared <DecisionStream> from @azirella-ltd/autonomy-frontend
 *     (alerts, CDT readiness banner, AIIO filter bar, digest, override flow)
 *   - Conversational chat with decision-context injection
 *   - Searchable clarification dropdowns for Azirella disambiguation
 *
 * The inbox section is owned end-to-end by the shared package container
 * (Phase 2.5 of TMS_INDEPENDENCE_PLAN). The Azirella chat below is
 * TMS-specific and stays in this page.
 *
 * Exists in parallel with the Planning Console (96+ page point-and-click
 * UI). Users toggle between modes via the TopNavbar mode toggle.
 *
 * Follows conversation pattern from AIAssistant.jsx.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Loader2,
  Send,
  RefreshCw,
  Sparkles,
  ChevronDown,
} from 'lucide-react';
import { DecisionStream as UIDecisionStream } from '@azirella-ltd/autonomy-frontend';
import { Badge, Button, Card, Input } from '../components/common';
import ChatDataBlock from '../components/chat/ChatDataBlock';
import { decisionStreamApi } from '../services/decisionStreamApi';
import { simulationApi } from '../services/api';
import { cn } from '../lib/utils/cn';
import { useDisplayPreferences } from '../contexts/DisplayPreferencesContext';
import { useAuth } from '../contexts/AuthContext';

/**
 * Searchable clarification dropdown for Azirella disambiguation.
 * Shows filtered options as user types, with "None of these" at bottom.
 */
const ClarificationDropdown = ({ clarification: cl, onSelect }) => {
  const [search, setSearch] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef(null);

  const filtered = (cl.options || []).filter((opt) =>
    !search || opt.toLowerCase().includes(search.toLowerCase())
  );

  // Close on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setIsOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  return (
    <div ref={ref}>
      <label className="block text-xs font-semibold text-violet-800 mb-1">
        {cl.question}
      </label>
      <div className="relative">
        <input
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setIsOpen(true); }}
          onFocus={() => setIsOpen(true)}
          placeholder={`Search ${(cl.category || 'options').toLowerCase()}...`}
          className="w-full rounded-md border border-violet-200 bg-background px-2.5 py-1.5 text-sm
            focus:outline-none focus:ring-2 focus:ring-violet-400/30 focus:border-violet-400/60"
        />
        {isOpen && (
          <div className="absolute z-50 w-full mt-1 max-h-48 overflow-y-auto bg-background border border-violet-200 rounded-md shadow-lg">
            {filtered.map((opt) => (
              <button
                key={opt}
                type="button"
                className="w-full text-left px-3 py-1.5 text-sm hover:bg-violet-100 truncate"
                onClick={() => { setIsOpen(false); setSearch(opt); onSelect(opt); }}
              >
                {opt}
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="px-3 py-2 text-xs text-muted-foreground italic">
                No matches found
              </div>
            )}
            {cl.none_option && (
              <button
                type="button"
                className="w-full text-left px-3 py-1.5 text-sm text-violet-600 hover:bg-violet-100 border-t border-violet-100 font-medium"
                onClick={() => { setIsOpen(false); setSearch(''); onSelect('__none__'); }}
              >
                None of these — show full list
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

const DecisionStream = () => {
  const location = useLocation();
  const { user, isTenantAdmin } = useAuth();

  // Override permissions by decision level:
  // - Executive/VP: Inspect only — they direct via Azirella, not override individual decisions
  // - S&OP Director, MPS Manager, Analyst: Can override decisions at their level
  // - Tenant Admin: Inspect only (technical admin, not functional planner)
  const userDecisionLevel = user?.decision_level;
  const OVERRIDE_LEVELS = ['S&OP_DIRECTOR', 'SOP_DIRECTOR', 'MPS_MANAGER', 'ANALYST',
    'ATP_ANALYST', 'REBALANCING_ANALYST', 'PO_ANALYST', 'ORDER_TRACKING_ANALYST',
    'ALLOCATION_MANAGER', 'ORDER_PROMISE_MANAGER', 'DEMO_ALL'];
  const canOverride = OVERRIDE_LEVELS.includes(userDecisionLevel);

  // Chat state (same pattern as AIAssistant.jsx)
  const [message, setMessage] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [suggestedFollowups, setSuggestedFollowups] = useState([]);

  // Config state
  const [configs, setConfigs] = useState([]);
  const [selectedConfigId, setSelectedConfigId] = useState(null);

  // Force-remount the shared <DecisionStream> when the user clicks Refresh.
  // The package container owns its own digest state internally; bumping
  // this nonce changes the React `key` and triggers a fresh fetch.
  const [refreshNonce, setRefreshNonce] = useState(0);

  const { loadLookupsForConfig } = useDisplayPreferences();

  const chatEndRef = useRef(null);
  const inputRef = useRef(null);
  const initialPromptHandled = useRef(false);

  // Load configs on mount
  useEffect(() => {
    const loadConfigs = async () => {
      try {
        const data = await simulationApi.getSupplyChainConfigs();
        const all = data.items || data || [];
        // Filter out archived configs — they have no active decisions
        const items = all.filter((c) => c.scenario_type !== 'ARCHIVED');
        setConfigs(items);
        if (items.length > 0 && !selectedConfigId) {
          const active = items.find((c) => c.is_active);
          setSelectedConfigId((active || items[0]).id);
        }
      } catch (err) {
        console.error('Failed to load configs:', err);
      }
    };
    loadConfigs();
  }, []);

  // Load identifier lookups when config changes — TMS-specific display prefs.
  useEffect(() => {
    if (selectedConfigId) {
      loadLookupsForConfig(selectedConfigId);
    }
  }, [selectedConfigId, loadLookupsForConfig]);

  // Scroll to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, chatLoading]);

  // Handle initial prompt or filters from TopNavbar "Azirella"
  useEffect(() => {
    const initialPrompt = location.state?.initialPrompt;
    const filters = location.state?.filters;
    if (initialPrompt && !initialPromptHandled.current) {
      initialPromptHandled.current = true;
      window.history.replaceState({}, '');
      handleSendMessage(initialPrompt);
    } else if (filters?.fromAzirella && !initialPromptHandled.current) {
      initialPromptHandled.current = true;
      window.history.replaceState({}, '');
      // If routed here with filters, inject as a context message
      const filterSummary = Object.entries(filters)
        .filter(([k]) => k !== 'fromAzirella')
        .map(([k, v]) => `${k}: ${v}`)
        .join(', ');
      if (filterSummary) {
        handleSendMessage(`Show me decisions filtered by ${filterSummary}`);
      }
    }
  }, [location.state]);

  const handleRefresh = useCallback(() => {
    setRefreshNonce((n) => n + 1);
  }, []);

  const handleSendMessage = useCallback(
    async (text) => {
      const msgText = (text || message).trim();
      if (!msgText || chatLoading) return;

      const userMessage = { role: 'user', content: msgText };
      setChatHistory((prev) => [...prev, userMessage]);
      setMessage('');
      setSuggestedFollowups([]);
      setChatLoading(true);

      try {
        const result = await decisionStreamApi.chat({
          message: msgText,
          conversation_id: conversationId,
          config_id: selectedConfigId,
        });

        const aiMessage = {
          role: 'assistant',
          content: result.response,
          sources: result.sources || [],
          dataBlocks: result.data_blocks || [],
          clarifications: result.clarifications || [],
        };
        setChatHistory((prev) => [...prev, aiMessage]);
        setConversationId(result.conversation_id);
        setSuggestedFollowups(result.suggested_followups || []);
      } catch (err) {
        console.error('Chat error:', err);
        setChatHistory((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: 'Sorry, I encountered an error. Please try again.',
            isError: true,
          },
        ]);
      } finally {
        setChatLoading(false);
        inputRef.current?.focus();
      }
    },
    [message, chatLoading, conversationId, selectedConfigId]
  );

  return (
    <>
      {/* TMS branding strip — own container, padded top only so the
          package's <DecisionStream> below sits flush. */}
      <div className="container mx-auto px-4 max-w-4xl pt-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full flex items-center justify-center bg-gradient-to-br from-violet-500 via-purple-500 to-indigo-600 shadow-[0_0_12px_rgba(139,92,246,0.4)]">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold">Decision Stream</h1>
              <p className="text-sm text-muted-foreground">
                Conversational AI assistant for transportation decisions
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {configs.length > 0 && (
              <div className="relative max-w-[280px]">
                <select
                  className="appearance-none border rounded-md pl-3 pr-8 py-2 text-sm bg-background w-full truncate cursor-pointer"
                  value={selectedConfigId || ''}
                  onChange={(e) =>
                    setSelectedConfigId(
                      e.target.value ? parseInt(e.target.value, 10) : null
                    )
                  }
                  title={configs.find(c => c.id === selectedConfigId)?.name || 'All Configs'}
                >
                  <option value="">All Configs</option>
                  {configs.map((cfg) => (
                    <option key={cfg.id} value={cfg.id}>
                      {cfg.name}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              </div>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={handleRefresh}
            >
              <RefreshCw className="h-4 w-4 mr-1" />
              Refresh
            </Button>
          </div>
        </div>
      </div>

      {/* Inbox section — owned end-to-end by @azirella-ltd/autonomy-frontend. The
          `key` forces a fresh digest fetch when the user clicks Refresh
          (the package container manages its own digest state internally). */}
      <UIDecisionStream
        key={`${selectedConfigId ?? 'all'}-${refreshNonce}`}
        configId={selectedConfigId}
        canOverride={canOverride}
        isAdmin={isTenantAdmin}
        hideHeader
      />

      {/* Azirella chat — TMS-specific, not in scope of ui-core. */}
      <div className="container mx-auto px-4 max-w-4xl pb-6">
        <Card className="flex flex-col min-h-[400px]">
          <div className="flex-1 p-6 overflow-y-auto bg-muted/20">
            {chatHistory.map((msg, index) => (
              <div
                key={index}
                className={cn(
                  'flex gap-3 mb-4',
                  msg.role === 'user' ? 'flex-row-reverse' : ''
                )}
              >
                <div
                  className={cn(
                    'w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0',
                    msg.role === 'user'
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-gradient-to-br from-violet-500 via-purple-500 to-indigo-600'
                  )}
                >
                  {msg.role === 'user' ? (
                    'U'
                  ) : (
                    <Sparkles className="h-4 w-4 text-white" />
                  )}
                </div>
                <div
                  className={cn(
                    'max-w-[75%] p-3 rounded-lg',
                    msg.role === 'user'
                      ? 'bg-primary/10 text-foreground'
                      : msg.isError
                        ? 'bg-destructive/10 border border-destructive/20'
                        : 'bg-card border'
                  )}
                >
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                  {msg.dataBlocks?.length > 0 && (
                    <div className="mt-2 space-y-2">
                      {msg.dataBlocks.map((block, i) => (
                        <ChatDataBlock key={i} block={block} />
                      ))}
                    </div>
                  )}
                  {/* Structured clarification dropdowns — searchable with "None of these" */}
                  {msg.clarifications?.length > 0 && (
                    <div className="mt-3 p-3 bg-violet-50 border border-violet-200 rounded-lg space-y-2.5">
                      {msg.clarifications.map((cl) => (
                        <ClarificationDropdown
                          key={cl.field}
                          clarification={cl}
                          onSelect={(value) => {
                            if (value === '__none__') {
                              handleSendMessage(`None of the ${cl.category || 'options'} listed — please show me the full list`);
                            } else {
                              handleSendMessage(`I mean: ${value}`);
                            }
                          }}
                        />
                      ))}
                    </div>
                  )}
                  {msg.sources?.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-muted">
                      <p className="text-xs text-muted-foreground mb-1">
                        Sources
                      </p>
                      {msg.sources.map((src, i) => (
                        <p
                          key={i}
                          className="text-xs text-muted-foreground ml-2"
                        >
                          {src.title}{' '}
                          <span className="opacity-60">
                            ({Math.round(src.relevance * 100)}%)
                          </span>
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Loading indicator */}
            {chatLoading && (
              <div className="flex gap-3 mb-4">
                <div className="w-9 h-9 rounded-full flex items-center justify-center bg-gradient-to-br from-violet-500 via-purple-500 to-indigo-600 flex-shrink-0">
                  <Sparkles className="h-4 w-4 text-white" />
                </div>
                <div className="p-3 rounded-lg bg-card border">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          {/* Suggested follow-ups */}
          {suggestedFollowups.length > 0 && !chatLoading && (
            <div className="px-4 py-2 border-t bg-muted/20 flex flex-wrap gap-2">
              {suggestedFollowups.map((q, i) => (
                <Badge
                  key={i}
                  variant="outline"
                  className="cursor-pointer hover:bg-muted text-xs"
                  onClick={() => handleSendMessage(q)}
                >
                  {q}
                </Badge>
              ))}
            </div>
          )}

          {/* Input Area */}
          <div className="p-4 border-t">
            <div className="flex gap-2">
              <Input
                ref={inputRef}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage();
                  }
                }}
                placeholder="Ask about your decisions, override reasoning, or supply chain status..."
                className="flex-1"
                disabled={chatLoading}
              />
              <Button
                onClick={() => handleSendMessage()}
                disabled={chatLoading}
              >
                {chatLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4 mr-2" />
                )}
                {chatLoading ? '' : 'Send'}
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </>
  );
};

export default DecisionStream;
