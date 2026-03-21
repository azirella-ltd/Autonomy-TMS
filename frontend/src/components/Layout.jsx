/**
 * Main Layout — Split Screen: Content (left) | Azirella (right)
 *
 * The Azirella panel has its own input and conversation display,
 * completely independent of TopNavbar portals.
 */

import React, { useState, useRef, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import TopNavbar from './TopNavbar';
import HierarchicalTabs from './HierarchicalTabs';
import NAVIGATION_CONFIG from '../config/navigationConfig';
import { useAuth } from '../contexts/AuthContext';
import { Send, Mic, Loader2 } from 'lucide-react';

const PANEL_WIDTH = 380;

const Layout = ({ children }) => {
  const location = useLocation();
  const { user } = useAuth();
  const isDecisionStream = location.pathname === '/' || location.pathname === '/decision-stream';

  const [activeCategory, setActiveCategory] = useState(
    isDecisionStream ? 'decision_stream' : null
  );

  // Azirella conversation state — self-contained, no portals
  const [azInput, setAzInput] = useState('');
  const [azMessages, setAzMessages] = useState([]);
  const [azLoading, setAzLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [azMessages]);

  const handleAzSubmit = async () => {
    const text = azInput.trim();
    if (!text || azLoading) return;

    setAzMessages(prev => [...prev, { role: 'user', content: text }]);
    setAzInput('');
    setAzLoading(true);

    try {
      const { api } = await import('../services/api');
      const resp = await api.post('/decision-stream/chat', {
        message: text,
        config_id: null,
      });
      const answer = resp.data?.response || resp.data?.content || 'No response.';
      setAzMessages(prev => [...prev, { role: 'assistant', content: answer }]);
    } catch (err) {
      setAzMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${err.response?.data?.detail || err.message || 'Unable to reach Azirella.'}`,
      }]);
    } finally {
      setAzLoading(false);
    }
  };

  const navConfig = NAVIGATION_CONFIG || [];

  return (
    <div className="min-h-screen bg-background">
      <TopNavbar sidebarOpen={false} />

      {/* Hierarchical Tabs — left content area */}
      <div style={{ marginRight: PANEL_WIDTH }}>
        <HierarchicalTabs
          navigationConfig={Array.isArray(navConfig) ? navConfig : []}
          activeCategory={activeCategory}
          onCategoryChange={setActiveCategory}
        />
      </div>

      {/* Page Content — left side */}
      <main className="pb-6 px-6 pt-4" style={{ marginRight: PANEL_WIDTH }}>
        {children}
      </main>

      {/* ═══ AZIRELLA PANEL — right side, always visible ═══ */}
      <div
        className="fixed right-0 top-16 bottom-0 z-30 flex flex-col border-l bg-background"
        style={{ width: PANEL_WIDTH }}
      >
        {/* Header */}
        <div className="flex items-center gap-2 px-3 py-2.5 border-b bg-violet-50/50 flex-shrink-0">
          <img
            src="/azirella_avatar.svg"
            alt=""
            className="h-6 w-6"
            onError={(e) => { e.target.style.display = 'none'; }}
          />
          <span className="font-semibold text-sm text-violet-900">Azirella</span>
          <span className="text-[10px] text-violet-400 ml-auto">AI Assistant</span>
        </div>

        {/* Conversation area */}
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
          {azMessages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center px-4 opacity-60">
              <img
                src="/azirella_avatar.svg"
                alt=""
                className="h-10 w-10 mb-3 opacity-40"
                onError={(e) => { e.target.style.display = 'none'; }}
              />
              <p className="text-sm font-medium text-muted-foreground mb-1">
                Ask me anything
              </p>
              <p className="text-xs text-muted-foreground/70">
                Decisions, metrics, risks, or directives.
                I know your supply chain.
              </p>
            </div>
          )}

          {azMessages.map((msg, i) => (
            <div key={i} className={msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
              <div
                className={
                  msg.role === 'user'
                    ? 'max-w-[85%] rounded-2xl rounded-tr-sm bg-violet-500 text-white px-3.5 py-2 text-sm'
                    : 'max-w-[85%] rounded-2xl rounded-tl-sm bg-muted px-3.5 py-2 text-sm'
                }
              >
                {msg.content}
              </div>
            </div>
          ))}

          {azLoading && (
            <div className="flex justify-start">
              <div className="rounded-2xl rounded-tl-sm bg-muted px-3.5 py-2 text-sm text-muted-foreground">
                <div className="flex items-center gap-2">
                  <div className="flex gap-0.5">
                    <div className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                  <span className="text-xs">Thinking...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input bar — at the bottom of the panel */}
        <div className="border-t px-3 py-2.5 flex items-center gap-2 bg-muted/10 flex-shrink-0">
          <input
            type="text"
            value={azInput}
            onChange={(e) => setAzInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleAzSubmit();
              }
            }}
            placeholder="Ask Azirella..."
            className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400/30 bg-background"
          />
          <button
            onClick={handleAzSubmit}
            disabled={azLoading || !azInput.trim()}
            className={
              azLoading || !azInput.trim()
                ? 'p-2 rounded-full text-muted-foreground'
                : 'p-2 rounded-full text-violet-500 hover:bg-violet-50'
            }
          >
            {azLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Layout;
