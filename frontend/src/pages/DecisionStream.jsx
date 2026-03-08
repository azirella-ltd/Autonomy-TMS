/**
 * Decision Stream Page — LLM-First UI with Decision-Back Planning
 *
 * The default landing experience for all Powell-role users. Presents
 * pending TRM decisions in a conversational "inbox" format with:
 *   - Alert banner (CDC/condition alerts)
 *   - LLM-synthesized digest with embedded decision cards
 *   - Conversational chat with decision-context injection
 *   - Accept/Override/Ask Why actions inline
 *
 * Exists in parallel with the Planning Console (96+ page point-and-click UI).
 * Users toggle between modes via the TopNavbar mode toggle.
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
  Inbox,
} from 'lucide-react';
import { Badge, Button, Card, CardContent, Input } from '../components/common';
import AlertBanner from '../components/decision-stream/AlertBanner';
import DigestMessage from '../components/decision-stream/DigestMessage';
import DecisionCard from '../components/decision-stream/DecisionCard';
import ChatDataBlock from '../components/decision-stream/ChatDataBlock';
import { decisionStreamApi } from '../services/decisionStreamApi';
import { simulationApi } from '../services/api';
import { cn } from '../lib/utils/cn';

const DecisionStream = () => {
  const location = useLocation();

  // Digest state
  const [digest, setDigest] = useState(null);
  const [digestLoading, setDigestLoading] = useState(true);
  const [alerts, setAlerts] = useState([]);

  // Chat state (same pattern as AIAssistant.jsx)
  const [message, setMessage] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [suggestedFollowups, setSuggestedFollowups] = useState([]);

  // Config state
  const [configs, setConfigs] = useState([]);
  const [selectedConfigId, setSelectedConfigId] = useState(null);

  const chatEndRef = useRef(null);
  const inputRef = useRef(null);
  const initialPromptHandled = useRef(false);

  // Load configs on mount
  useEffect(() => {
    const loadConfigs = async () => {
      try {
        const data = await simulationApi.getSupplyChainConfigs();
        const items = data.items || data || [];
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

  // Load digest when config changes
  useEffect(() => {
    loadDigest();
  }, [selectedConfigId]);

  // Scroll to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, chatLoading]);

  // Handle initial prompt from TopNavbar "Talk to me"
  useEffect(() => {
    const initialPrompt = location.state?.initialPrompt;
    if (initialPrompt && !initialPromptHandled.current) {
      initialPromptHandled.current = true;
      window.history.replaceState({}, '');
      handleSendMessage(initialPrompt);
    }
  }, [location.state]);

  const loadDigest = async () => {
    try {
      setDigestLoading(true);
      const data = await decisionStreamApi.getDigest(selectedConfigId);
      setDigest(data);
      setAlerts(data.alerts || []);
    } catch (err) {
      console.error('Failed to load digest:', err);
      setDigest({
        digest_text:
          'Unable to load your decision digest. Please check that the backend is running.',
        decisions: [],
        alerts: [],
        total_pending: 0,
      });
    } finally {
      setDigestLoading(false);
    }
  };

  const handleAccept = async (decision) => {
    try {
      await decisionStreamApi.actOnDecision({
        decision_id: decision.id,
        decision_type: decision.decision_type,
        action: 'accept',
      });
      // Refresh digest
      loadDigest();
    } catch (err) {
      console.error('Accept failed:', err);
    }
  };

  const handleOverride = async (decision, reasonCode, reasonText) => {
    try {
      await decisionStreamApi.actOnDecision({
        decision_id: decision.id,
        decision_type: decision.decision_type,
        action: 'override',
        override_reason_code: reasonCode,
        override_reason_text: reasonText,
      });
      loadDigest();
    } catch (err) {
      console.error('Override failed:', err);
    }
  };

  const handleAskWhy = async (decision) => {
    // Show the pre-computed reasoning instantly instead of routing through LLM
    const reasoning = decision.decision_reasoning;
    if (reasoning) {
      // Instant display — reasoning was captured at decision time
      const userMessage = {
        role: 'user',
        content: `Why did you recommend "${decision.suggested_action}" for ${decision.summary}?`,
      };
      const aiMessage = {
        role: 'assistant',
        content: reasoning,
      };
      setChatHistory((prev) => [...prev, userMessage, aiMessage]);
    } else {
      // Fallback: fetch explanation from the dedicated ask-why endpoint
      const userMessage = {
        role: 'user',
        content: `Why did you recommend "${decision.suggested_action}" for ${decision.summary}?`,
      };
      setChatHistory((prev) => [...prev, userMessage]);
      setChatLoading(true);
      try {
        const result = await decisionStreamApi.askWhy(decision.id, decision.decision_type);
        const aiMessage = {
          role: 'assistant',
          content: result.reasoning || result.decision_reasoning || 'No reasoning available for this decision.',
        };
        setChatHistory((prev) => [...prev, aiMessage]);
      } catch (err) {
        console.error('Ask Why failed:', err);
        const aiMessage = {
          role: 'assistant',
          content: 'Unable to retrieve reasoning for this decision.',
        };
        setChatHistory((prev) => [...prev, aiMessage]);
      } finally {
        setChatLoading(false);
      }
    }
  };

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
    <div className="container mx-auto py-6 px-4 max-w-4xl">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full flex items-center justify-center bg-gradient-to-br from-violet-500 via-purple-500 to-indigo-600 shadow-[0_0_12px_rgba(139,92,246,0.4)]">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Decision Stream</h1>
            <p className="text-sm text-muted-foreground">
              {digest?.total_pending ?? '...'} decisions awaiting review
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {configs.length > 0 && (
            <select
              className="border rounded-md px-3 py-2 text-sm bg-background"
              value={selectedConfigId || ''}
              onChange={(e) =>
                setSelectedConfigId(
                  e.target.value ? parseInt(e.target.value, 10) : null
                )
              }
            >
              <option value="">All Configs</option>
              {configs.map((cfg) => (
                <option key={cfg.id} value={cfg.id}>
                  {cfg.name}
                </option>
              ))}
            </select>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={loadDigest}
            disabled={digestLoading}
          >
            <RefreshCw
              className={cn('h-4 w-4 mr-1', digestLoading && 'animate-spin')}
            />
            Refresh
          </Button>
        </div>
      </div>

      {/* Main stream area */}
      <Card className="min-h-[600px] flex flex-col">
        <div className="flex-1 p-6 overflow-y-auto bg-muted/20">
          {/* Alert banner */}
          <AlertBanner alerts={alerts} />

          {/* Digest */}
          {digestLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              <span className="ml-3 text-muted-foreground">
                Loading your decision stream...
              </span>
            </div>
          ) : digest ? (
            <DigestMessage
              digestText={digest.digest_text}
              decisions={digest.decisions || []}
              onAccept={handleAccept}
              onOverride={handleOverride}
              onAskWhy={handleAskWhy}
            />
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Inbox className="h-12 w-12 mb-3 opacity-40" />
              <p>No decisions pending</p>
            </div>
          )}

          {/* Chat messages */}
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
  );
};

export default DecisionStream;
