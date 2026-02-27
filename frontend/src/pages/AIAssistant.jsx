/**
 * AI Assistant Dashboard
 *
 * Claude-powered AI assistant for supply chain management with RAG-backed
 * tenant-scoped knowledge base. Supports multi-turn conversation, source
 * citations, and SC config scoping.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Badge, Button, Card, CardContent, Input } from '../components/common';
import {
  Bot,
  Send,
  Brain,
  Lightbulb,
  TrendingUp,
  HelpCircle,
  Loader2,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  BookOpen,
} from 'lucide-react';
import { assistantApi, simulationApi } from '../services/api';

const AIAssistant = () => {
  const [message, setMessage] = useState('');
  const [chatHistory, setChatHistory] = useState([
    {
      role: 'assistant',
      content:
        "Hello! I'm your AI supply chain assistant. I have access to your supply chain configurations and knowledge base. How can I help you today?",
    },
  ]);
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [selectedConfigId, setSelectedConfigId] = useState(null);
  const [configs, setConfigs] = useState([]);
  const [sources, setSources] = useState([]);
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const [suggestedFollowups, setSuggestedFollowups] = useState([]);
  const [error, setError] = useState(null);

  const chatEndRef = useRef(null);
  const inputRef = useRef(null);

  // Load available SC configs
  useEffect(() => {
    const loadConfigs = async () => {
      try {
        const data = await simulationApi.getSupplyChainConfigs();
        const items = data.items || data || [];
        setConfigs(items);
        if (items.length > 0 && !selectedConfigId) {
          // Default to the first active or first config
          const active = items.find((c) => c.is_active);
          setSelectedConfigId((active || items[0]).id);
        }
      } catch (err) {
        console.error('Failed to load configs:', err);
      }
    };
    loadConfigs();
  }, []);

  // Scroll to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, loading]);

  const handleSendMessage = useCallback(
    async (text) => {
      const msgText = (text || message).trim();
      if (!msgText || loading) return;

      const userMessage = { role: 'user', content: msgText };
      setChatHistory((prev) => [...prev, userMessage]);
      setMessage('');
      setError(null);
      setSources([]);
      setSuggestedFollowups([]);
      setLoading(true);

      try {
        const result = await assistantApi.sendMessage(
          msgText,
          conversationId,
          selectedConfigId,
        );

        const aiMessage = {
          role: 'assistant',
          content: result.response,
          sources: result.sources || [],
        };
        setChatHistory((prev) => [...prev, aiMessage]);
        setConversationId(result.conversation_id);
        setSources(result.sources || []);
        setSuggestedFollowups(result.suggested_followups || []);
      } catch (err) {
        console.error('Assistant error:', err);
        const errMsg =
          err.response?.data?.detail ||
          'Failed to get a response. Please try again.';
        setError(errMsg);
        setChatHistory((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: `Sorry, I encountered an error: ${errMsg}`,
            isError: true,
          },
        ]);
      } finally {
        setLoading(false);
        inputRef.current?.focus();
      }
    },
    [message, loading, conversationId, selectedConfigId],
  );

  const handleNewConversation = () => {
    setChatHistory([
      {
        role: 'assistant',
        content:
          "Hello! I'm your AI supply chain assistant. How can I help you today?",
      },
    ]);
    setConversationId(null);
    setSources([]);
    setSuggestedFollowups([]);
    setError(null);
  };

  const suggestedQuestions = [
    'What sites are in my supply chain?',
    'What are the transportation lanes and lead times?',
    'How is demand distributed across markets?',
    'What products flow through my network?',
    'What are the key risks in my supply chain?',
  ];

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bot className="h-10 w-10 text-primary" />
          <div>
            <h1 className="text-3xl font-bold">AI Assistant</h1>
            <p className="text-sm text-muted-foreground">
              RAG-Powered Supply Chain Intelligence
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* Config selector */}
          {configs.length > 0 && (
            <select
              className="border rounded-md px-3 py-2 text-sm bg-background"
              value={selectedConfigId || ''}
              onChange={(e) =>
                setSelectedConfigId(
                  e.target.value ? parseInt(e.target.value, 10) : null,
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
          <Button variant="outline" size="sm" onClick={handleNewConversation}>
            <RefreshCw className="h-4 w-4 mr-1" />
            New Chat
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card className="h-[600px] flex flex-col">
            {/* Chat Messages */}
            <div className="flex-1 p-6 overflow-y-auto bg-muted/30">
              {chatHistory.map((msg, index) => (
                <div
                  key={index}
                  className={`flex gap-3 mb-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                >
                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
                      msg.role === 'user'
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-secondary'
                    }`}
                  >
                    {msg.role === 'user' ? 'U' : <Bot className="h-5 w-5" />}
                  </div>
                  <div
                    className={`max-w-[75%] p-3 rounded-lg ${
                      msg.role === 'user'
                        ? 'bg-primary/10 text-foreground'
                        : msg.isError
                          ? 'bg-destructive/10 border border-destructive/20'
                          : 'bg-card border'
                    }`}
                  >
                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                    {/* Inline sources for this message */}
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-muted">
                        <p className="text-xs text-muted-foreground flex items-center gap-1 mb-1">
                          <BookOpen className="h-3 w-3" />
                          Sources
                        </p>
                        {msg.sources.map((src, i) => (
                          <p
                            key={i}
                            className="text-xs text-muted-foreground ml-4"
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
              {loading && (
                <div className="flex gap-3 mb-4">
                  <div className="w-10 h-10 rounded-full flex items-center justify-center bg-secondary flex-shrink-0">
                    <Bot className="h-5 w-5" />
                  </div>
                  <div className="p-3 rounded-lg bg-card border">
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  </div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>

            {/* Suggested follow-ups */}
            {suggestedFollowups.length > 0 && !loading && (
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
                  placeholder="Ask me anything about your supply chain..."
                  className="flex-1"
                  disabled={loading}
                />
                <Button onClick={() => handleSendMessage()} disabled={loading}>
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4 mr-2" />
                  )}
                  {loading ? '' : 'Send'}
                </Button>
              </div>
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          {/* Source Citations Panel */}
          {sources.length > 0 && (
            <Card>
              <CardContent className="pt-6">
                <button
                  className="flex items-center gap-2 w-full text-left mb-3"
                  onClick={() => setSourcesExpanded(!sourcesExpanded)}
                >
                  <BookOpen className="h-5 w-5 text-primary" />
                  <h3 className="text-lg font-semibold flex-1">
                    Sources ({sources.length})
                  </h3>
                  {sourcesExpanded ? (
                    <ChevronUp className="h-4 w-4" />
                  ) : (
                    <ChevronDown className="h-4 w-4" />
                  )}
                </button>
                {sourcesExpanded && (
                  <div className="space-y-3">
                    {sources.map((src, i) => (
                      <div
                        key={i}
                        className="p-3 bg-muted/30 rounded-lg border"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <p className="font-medium text-sm">{src.title}</p>
                          <Badge variant="secondary" className="text-xs">
                            {Math.round(src.relevance * 100)}%
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground line-clamp-3">
                          {src.excerpt}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardContent className="pt-6">
              <h3 className="text-lg font-semibold mb-4">Capabilities</h3>
              <div className="space-y-3">
                <div className="flex items-start gap-3">
                  <Brain className="h-5 w-5 text-primary mt-0.5" />
                  <div>
                    <p className="font-medium text-sm">Supply Chain Analysis</p>
                    <p className="text-xs text-muted-foreground">
                      Deep insights into your network topology
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <TrendingUp className="h-5 w-5 text-primary mt-0.5" />
                  <div>
                    <p className="font-medium text-sm">Demand Forecasting</p>
                    <p className="text-xs text-muted-foreground">
                      AI-powered predictions from your data
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <Lightbulb className="h-5 w-5 text-primary mt-0.5" />
                  <div>
                    <p className="font-medium text-sm">Optimization Tips</p>
                    <p className="text-xs text-muted-foreground">
                      Actionable recommendations
                    </p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-2 mb-4">
                <HelpCircle className="h-5 w-5 text-muted-foreground" />
                <h3 className="text-lg font-semibold">Suggested Questions</h3>
              </div>
              <div className="flex flex-col gap-2">
                {suggestedQuestions.map((question, index) => (
                  <Badge
                    key={index}
                    variant="outline"
                    className="justify-start cursor-pointer hover:bg-muted py-2 px-3 text-left"
                    onClick={() => handleSendMessage(question)}
                  >
                    {question}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default AIAssistant;
