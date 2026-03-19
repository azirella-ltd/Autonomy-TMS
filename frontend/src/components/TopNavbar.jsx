/**
 * TopNavbar - Autonomy UI Kit Version
 *
 * Top navigation bar using Tailwind CSS and lucide-react icons.
 * Provides user menu, notifications, context breadcrumbs, and
 * a central "Talk to me" AI prompt input with avatar.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Link, useNavigate, useLocation, useParams } from 'react-router-dom';
import {
  Menu,
  X,
  User,
  Settings,
  LogOut,
  HelpCircle,
  Bell,
  Shield,
  GraduationCap,
  Brain,
  Users,
  Network,
  SendHorizontal,
  Sparkles,
  LayoutGrid,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useActiveConfig } from '../contexts/ActiveConfigContext';
import { isSystemAdmin } from '../utils/authUtils';
import simulationApi, { api } from '../services/api';
import { getSupplyChainConfigById } from '../services/supplyChainConfigService';
import { cn } from '../lib/utils/cn';
import TalkToMePopup from './TalkToMePopup';

// ─── AI Avatar ────────────────────────────────────────────────────────────────
// A small circular avatar used alongside the "Talk to me" prompt.
// Stylized microphone with speech waves — the Talk to Me brand mark.
// Talk to Me avatar — stylized microphone with speech waves
const TalkToMeAvatar = ({ size = 'sm' }) => {
  const dim = size === 'sm' ? 'h-7 w-7' : 'h-9 w-9';
  return (
    <img
      src="/talk_to_me_avatar.svg"
      alt=""
      className={cn(dim, 'flex-shrink-0')}
      aria-hidden="true"
    />
  );
};

const TopNavbar = ({ sidebarOpen = true }) => {
  const { user, isAuthenticated, logout } = useAuth();
  const { effectiveConfigId } = useActiveConfig();
  const [currentPath, setCurrentPath] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const [gameInfo, setGameInfo] = useState(null);
  const [systemConfigName, setSystemConfigName] = useState(null);
  const [supplyChainConfigName, setSupplyChainConfigName] = useState(null);

  // Talk-to-me state — two-phase: analyze → clarify → submit
  const [talkInput, setTalkInput] = useState('');
  const [talkFocused, setTalkFocused] = useState(false);
  const [talkSubmitting, setTalkSubmitting] = useState(false);
  const [directiveResult, setDirectiveResult] = useState(null);
  // Clarification flow
  const [analysisResult, setAnalysisResult] = useState(null); // from /analyze
  const [originalText, setOriginalText] = useState('');
  const [clarifications, setClarifications] = useState({}); // field → value
  const [streamMessages, setStreamMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [rephrasedPrompt, setRephrasedPrompt] = useState('');
  const [popupOpen, setPopupOpen] = useState(false);
  const talkInputRef = useRef(null);

  // UI mode state (stream = Decision Stream, console = Planning Console)
  const [uiMode, setUiMode] = useState(() => localStorage.getItem('ui:mode') || 'stream');

  const menuRef = useRef(null);
  const navigate = useNavigate();
  const location = useLocation();
  const params = useParams();
  const { gameId, id: routeId, configId } = params;
  const supplyChainConfigId = routeId || configId || null;

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Update current path when location changes
  useEffect(() => {
    setCurrentPath(location.pathname);
  }, [location]);

  // Load system config name
  useEffect(() => {
    let isMounted = true;

    const loadSystemConfigName = async () => {
      try {
        const data = await simulationApi.getSystemConfig();
        if (isMounted) {
          setSystemConfigName(data?.name || null);
        }
      } catch (error) {
        if (!isMounted) return;

        let cachedName = null;
        try {
          const cached = localStorage.getItem('systemConfigRanges');
          if (cached) {
            const parsed = JSON.parse(cached);
            cachedName = parsed?.name || null;
          }
        } catch (_) {
          cachedName = null;
        }
        setSystemConfigName(cachedName);
      }
    };

    const shouldFetch = systemConfigName === null || location.pathname.includes('system-config');
    if (shouldFetch) {
      loadSystemConfigName();
    }

    return () => {
      isMounted = false;
    };
  }, [location.pathname, systemConfigName]);

  // Load game information when on a scenario page
  useEffect(() => {
    const fetchGameInfo = async () => {
      if (gameId) {
        try {
          const data = await simulationApi.getScenario(gameId);
          setGameInfo(data);
        } catch (err) {
          console.error('Failed to load scenario info', err);
        }
      } else {
        setGameInfo(null);
      }
    };
    fetchGameInfo();
  }, [gameId]);

  // Load supply chain config name
  useEffect(() => {
    const onSupplyChainRoute = location.pathname.includes('/supply-chain-config');
    const onCustomerSupplyChainRoute = location.pathname.includes('/admin/tenant/supply-chain-configs');
    const onGameFromConfigRoute = location.pathname.includes('/scenarios/new-from-config');

    if (!(onSupplyChainRoute || onCustomerSupplyChainRoute || onGameFromConfigRoute)) {
      setSupplyChainConfigName(null);
      return;
    }

    if (!supplyChainConfigId) {
      setSupplyChainConfigName(null);
      return;
    }

    let isMounted = true;

    const loadSupplyChainConfigName = async () => {
      try {
        const config = await getSupplyChainConfigById(supplyChainConfigId);
        if (isMounted) {
          setSupplyChainConfigName(config?.name || null);
        }
      } catch (error) {
        if (isMounted) {
          setSupplyChainConfigName(null);
        }
      }
    };

    loadSupplyChainConfigName();

    return () => {
      isMounted = false;
    };
  }, [supplyChainConfigId, location.pathname]);

  const isSysAdmin = isSystemAdmin(user);

  const handleLogout = async () => {
    try {
      await logout();
      setMenuOpen(false);
      navigate('/login');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  const getInitials = (name) => {
    if (!name) return '';
    return name
      .split(' ')
      .map((part) => part[0])
      .join('')
      .toUpperCase()
      .substring(0, 2);
  };

  // ── Mode Toggle ────────────────────────────────────────────────────────────
  const handleModeToggle = () => {
    const newMode = uiMode === 'stream' ? 'console' : 'stream';
    setUiMode(newMode);
    localStorage.setItem('ui:mode', newMode);
    if (newMode === 'stream') {
      navigate('/decision-stream');
    } else {
      navigate('/dashboard');
    }
  };

  // ── Talk to me — Two-Phase Directive Capture ────────────────────────────────

  const dismissClarification = useCallback(() => {
    setAnalysisResult(null);
    setOriginalText('');
    setClarifications({});
    setRephrasedPrompt('');
    setPopupOpen(false);
    setStreamMessages([]);
    setIsStreaming(false);
    setDirectiveResult(null);
  }, []);

  // Phase 1: Analyze the directive, check for missing fields
  const handleTalkSubmit = async () => {
    const prompt = talkInput.trim();
    if (!prompt || talkSubmitting) return;

    // If no active config, fall back to navigation behavior
    if (!effectiveConfigId) {
      setTalkInput('');
      setTalkFocused(false);
      talkInputRef.current?.blur();
      const target = uiMode === 'stream' ? '/decision-stream' : '/ai-assistant';
      navigate(target, { state: { initialPrompt: prompt } });
      return;
    }

    setTalkSubmitting(true);
    setPopupOpen(true);
    try {
      const response = await api.post('/directives/analyze', {
        config_id: effectiveConfigId,
        text: prompt,
      });
      const analysis = response.data;
      const intent = analysis.intent;

      // Question flow — show the LLM answer directly
      if (intent === 'question') {
        setOriginalText(prompt);
        setAnalysisResult(analysis);
        setTalkInput('');
        // If a target page was identified, offer navigation
        // Auto-dismiss after reading time (or user can dismiss manually)
        return;
      }

      // Ambiguous — show clarification asking if directive or question
      if (intent === 'unknown' || analysis.clarification_needed) {
        setOriginalText(prompt);
        setAnalysisResult(analysis);
        setTalkInput('');
        return;
      }

      // Scenario event / scenario question flow
      if (intent === 'scenario_event' || intent === 'scenario_question') {
        const hasMissing = (analysis.missing_fields?.length || 0) > 0;
        if (hasMissing) {
          // Need more info — show clarification panel
          setOriginalText(prompt);
          setAnalysisResult(analysis);
          setClarifications({});
          setTalkInput('');
        } else if (intent === 'scenario_question' && analysis.answer) {
          // Event injected + answer synthesized — show result panel
          setOriginalText(prompt);
          setAnalysisResult(analysis);
          setTalkInput('');
        } else {
          // scenario_event with no missing fields and no question — submit and navigate
          await submitFinalDirective(prompt, {});
        }
        return;
      }

      // Compound flow — demand signal + directive
      if (intent === 'compound') {
        if (analysis.is_complete) {
          // No gaps — submit via SSE stream
          await submitCompoundStream(prompt, analysis.actions);
        } else {
          // Show rephrased prompt for editing, or clarification panel
          setOriginalText(prompt);
          setAnalysisResult(analysis);
          setRephrasedPrompt(analysis.rephrased_prompt || prompt);
          setClarifications({});
          setTalkInput('');
        }
        return;
      }

      // Directive flow — check for missing fields
      if (analysis.is_complete || (analysis.missing_fields?.length || 0) === 0) {
        // No gaps — submit immediately
        await submitFinalDirective(prompt, {});
      } else {
        // Gaps found — show clarification panel
        setOriginalText(prompt);
        setAnalysisResult(analysis);
        setRephrasedPrompt(analysis.rephrased_prompt || prompt);
        setClarifications({});
        setTalkInput('');
      }
    } catch (err) {
      console.error('Directive analysis failed:', err);
      // Fall back to navigation
      setTalkInput('');
      setTalkFocused(false);
      talkInputRef.current?.blur();
      const target = uiMode === 'stream' ? '/decision-stream' : '/ai-assistant';
      navigate(target, { state: { initialPrompt: prompt } });
    } finally {
      setTalkSubmitting(false);
    }
  };

  // Phase 2: Submit with clarifications
  const submitFinalDirective = async (text, clarifs) => {
    setTalkSubmitting(true);
    try {
      const response = await api.post('/directives/submit', {
        config_id: effectiveConfigId,
        text,
        clarifications: Object.keys(clarifs).length > 0 ? clarifs : undefined,
        // Pass prior injection info to avoid re-injecting
        scenario_event_id: analysisResult?.event_id || undefined,
        target_config_id: analysisResult?.target_config_id || undefined,
      });
      const result = response.data;
      // Merge analysis-phase data into result for scenario questions
      // (the answer and event summary were computed during analyze, not submit)
      if (analysisResult?.intent === 'scenario_question' && analysisResult.answer) {
        result._scenario_answer = analysisResult.answer;
        result._event_summary = analysisResult.event_summary;
        result._can_fulfill = analysisResult.can_fulfill;
        result._target_config_id = analysisResult.target_config_id;
      }
      if (analysisResult?.intent === 'scenario_event' && analysisResult.event_summary) {
        result._event_summary = analysisResult.event_summary;
        result._target_config_id = analysisResult.target_config_id;
      }
      setDirectiveResult(result);
      setTalkInput('');
      // Keep popup open to show results — don't auto-dismiss
      setAnalysisResult(null);
      setClarifications({});
      setRephrasedPrompt('');
    } catch (err) {
      console.error('Directive submission failed:', err);
    } finally {
      setTalkSubmitting(false);
    }
  };

  const submitCompoundStream = async (text, actions, clarifs = {}) => {
    setIsStreaming(true);
    setStreamMessages([]);
    setTalkInput('');
    dismissClarification();

    try {
      const response = await fetch('/api/directives/submit-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          config_id: effectiveConfigId,
          text,
          actions,
          clarifications: Object.keys(clarifs).length > 0 ? clarifs : undefined,
        }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const blocks = buffer.split('\n\n');
        buffer = blocks.pop() || '';

        for (const block of blocks) {
          if (!block.trim()) continue;
          const eventMatch = block.match(/^event:\s*(.+)\ndata:\s*(.+)$/m);
          if (eventMatch) {
            const [, eventType, dataStr] = eventMatch;
            try {
              const data = JSON.parse(dataStr);
              setStreamMessages((prev) => [...prev, { type: eventType, ...data }]);

              if (eventType === 'complete') {
                setTimeout(() => {
                  setIsStreaming(false);
                  setStreamMessages([]);
                }, 5000);
              }
              if (eventType === 'error') {
                setTimeout(() => {
                  setIsStreaming(false);
                  setStreamMessages([]);
                }, 4000);
              }
            } catch { /* ignore malformed JSON */ }
          }
        }
      }
    } catch (err) {
      console.error('SSE stream failed:', err);
      setStreamMessages((prev) => [...prev, { type: 'error', message: 'Connection failed' }]);
      setTimeout(() => { setIsStreaming(false); setStreamMessages([]); }, 4000);
    }
  };

  const submitStrategyStream = async (text, actions, clarifs = {}) => {
    setIsStreaming(true);
    setStreamMessages([]);
    setTalkInput('');
    dismissClarification();

    try {
      const response = await fetch('/api/directives/submit-strategy-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          config_id: effectiveConfigId,
          text,
          actions,
          clarifications: Object.keys(clarifs).length > 0 ? clarifs : undefined,
        }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const blocks = buffer.split('\n\n');
        buffer = blocks.pop() || '';

        for (const block of blocks) {
          if (!block.trim()) continue;
          const eventMatch = block.match(/^event:\s*(.+)\ndata:\s*(.+)$/m);
          if (eventMatch) {
            const [, eventType, dataStr] = eventMatch;
            try {
              const data = JSON.parse(dataStr);
              setStreamMessages((prev) => [...prev, { type: eventType, ...data }]);

              if (eventType === 'complete' || eventType === 'error') {
                // Don't auto-dismiss — user clicks Done
              }
            } catch { /* ignore malformed JSON */ }
          }
        }
      }
    } catch (err) {
      console.error('Strategy SSE stream failed:', err);
      setStreamMessages((prev) => [...prev, { type: 'error', message: 'Connection failed' }]);
    } finally {
      setIsStreaming(false);
    }
  };

  const handleClarificationAnswer = (field, value) => {
    setClarifications((prev) => ({ ...prev, [field]: value }));
  };

  const handleClarificationSubmit = () => {
    // Use the edited prompt if changed, otherwise the original
    const finalText = (rephrasedPrompt && rephrasedPrompt !== originalText)
      ? rephrasedPrompt
      : originalText;

    if (analysisResult?.intent === 'compound') {
      // Submit compound actions directly with the (possibly edited) text
      submitCompoundStream(finalText, analysisResult.actions, clarifications);
    } else {
      // Standard flow: submit directly — no re-analyze round trip
      const missing = (analysisResult?.missing_fields || []);
      const unanswered = missing.filter((m) => !clarifications[m.field]?.trim());
      if (unanswered.length > 0 && finalText === originalText) return; // still missing answers
      submitFinalDirective(finalText, clarifications);
    }
  };

  const handleActivateDirective = async () => {
    // User confirmed "Yes, activate the directive"
    if (analysisResult?.intent === 'compound' && analysisResult.actions) {
      await submitCompoundStream(originalText, analysisResult.actions, clarifications);
    }
  };

  const handleSkipDirective = async () => {
    // User said "No, just create the order" — execute only demand signal actions
    if (analysisResult?.intent === 'compound' && analysisResult.actions) {
      const demandOnly = analysisResult.actions.filter(a => a.action_type === 'demand_signal');
      if (demandOnly.length > 0) {
        await submitCompoundStream(originalText, demandOnly, clarifications);
      }
    }
  };

  const handleCompareStrategies = async () => {
    if (analysisResult?.intent === 'compound' && analysisResult.actions) {
      await submitStrategyStream(originalText, analysisResult.actions, clarifications);
    }
  };

  const handlePromoteStrategy = async (scenarioId) => {
    try {
      setTalkSubmitting(true);
      await api.post(`/directives/promote-strategy/${scenarioId}`, null, {
        params: { rationale: 'Selected from strategy comparison' },
      });
      setStreamMessages((prev) => [...prev, {
        type: 'action_complete',
        message: 'Strategy promoted — changes applied to active plan.',
      }]);
    } catch (err) {
      console.error('Promote failed:', err);
    } finally {
      setTalkSubmitting(false);
    }
  };

  const handleNavigateFromPopup = (page, state) => {
    dismissClarification();
    navigate(page, { state });
  };

  const handleSubmitRephrased = () => {
    if (rephrasedPrompt) {
      // Submit directly — no re-analyze round trip
      submitFinalDirective(rephrasedPrompt, clarifications);
    }
  };

  // Count how many clarifications are answered
  const answeredCount = analysisResult
    ? (analysisResult.missing_fields || []).filter((m) => clarifications[m.field]?.trim()).length
    : 0;
  const totalMissing = analysisResult?.missing_fields?.length || 0;
  const allAnswered = answeredCount === totalMissing && totalMissing > 0;

  const handleTalkKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleTalkSubmit();
    }
    if (e.key === 'Escape') {
      if (analysisResult) {
        dismissClarification();
      } else {
        setTalkInput('');
        setTalkFocused(false);
        talkInputRef.current?.blur();
      }
    }
  };

  const groupName = user?.group?.name || gameInfo?.group?.name;
  const gameConfigName = gameInfo?.config?.name;
  const scDisplayName = supplyChainConfigName || gameConfigName || systemConfigName;
  const gameName = gameInfo?.name;
  const onSystemAdminPage = location.pathname.startsWith('/system');
  const shouldShowContext = !onSystemAdminPage && (groupName || scDisplayName || gameName);

  const contextParts = [];
  if (groupName) contextParts.push(`Group: ${groupName}`);
  if (scDisplayName) contextParts.push(`Config: ${scDisplayName}`);
  if (gameName) contextParts.push(`Game: ${gameName}`);

  if (!isAuthenticated) {
    return null;
  }

  const menuItems = [
    { label: 'Profile', icon: User, path: '/profile' },
    { label: 'Settings', icon: Settings, path: '/settings' },
  ];

  const adminMenuItems = isSysAdmin ? [
    { label: 'Organizations', icon: Users, path: '/admin/tenants' },
  ] : [];

  return (
    <header
      className={cn(
        "fixed top-0 right-0 z-30 h-16 bg-background/80 backdrop-blur-md border-b border-border shadow-sm transition-all duration-200 ease-in-out",
        sidebarOpen ? "left-[280px]" : "left-16"
      )}
    >
      <div className="flex items-center h-full px-4 md:px-6 gap-4">

        {/* ── LEFT: Logo & Context ─────────────────────────────────────────── */}
        <div className="flex items-center gap-4 flex-shrink-0">
          <Link
            to={isSysAdmin ? '/admin/tenants' : '/dashboard'}
            className="flex items-center gap-2 font-medium hover:opacity-80 transition-opacity"
          >
            <img
              src="/autonomy_logo.svg"
              alt="Autonomy"
              className="h-7 w-auto"
            />
          </Link>

          {shouldShowContext && (
            <span className="hidden lg:block text-sm text-muted-foreground">
              {contextParts.join(' | ')}
            </span>
          )}
        </div>

        {/* ── CENTER: Talk to me ────────────────────────────────────────────── */}
        <div className="flex-1 flex justify-center px-2 relative">
          <div
            className={cn(
              'hidden md:flex items-center w-full max-w-lg gap-2.5',
              'bg-accent/40 border rounded-full px-3 py-1.5',
              'transition-all duration-200',
              talkFocused
                ? 'border-violet-400/60 bg-background ring-2 ring-violet-400/20 shadow-sm'
                : 'border-border hover:border-muted-foreground/40 hover:bg-accent/60',
            )}
          >
            {/* AI avatar */}
            <TalkToMeAvatar size="sm" />

            {/* Prompt input */}
            <input
              ref={talkInputRef}
              type="text"
              value={talkInput}
              onChange={(e) => setTalkInput(e.target.value)}
              onKeyDown={handleTalkKeyDown}
              onFocus={() => setTalkFocused(true)}
              onBlur={() => setTalkFocused(false)}
              placeholder="Talk to me…"
              className={cn(
                'flex-1 bg-transparent text-sm outline-none min-w-0',
                'text-foreground placeholder:text-muted-foreground/70',
              )}
              aria-label="Talk to the AI assistant"
            />

            {/* Send button — visible when there's content */}
            <button
              onClick={handleTalkSubmit}
              disabled={talkSubmitting}
              aria-label="Send prompt"
              className={cn(
                'flex items-center justify-center h-6 w-6 rounded-full flex-shrink-0 transition-all duration-150',
                talkSubmitting
                  ? 'bg-violet-400 text-white opacity-100 scale-100 animate-pulse'
                  : talkInput.trim()
                    ? 'bg-violet-500 text-white hover:bg-violet-600 opacity-100 scale-100'
                    : 'opacity-0 scale-75 pointer-events-none',
              )}
            >
              <SendHorizontal className="h-3.5 w-3.5" />
            </button>
          </div>

          <TalkToMePopup
            open={popupOpen}
            onClose={dismissClarification}
            userPrompt={originalText}
            analysisResult={analysisResult}
            streamMessages={streamMessages}
            isStreaming={isStreaming}
            directiveResult={directiveResult}
            rephrasedPrompt={rephrasedPrompt}
            onRephrasedChange={setRephrasedPrompt}
            onSubmitRephrased={handleSubmitRephrased}
            onSubmitCompound={() => submitCompoundStream(originalText, analysisResult?.actions || [], clarifications)}
            onActivateDirective={handleActivateDirective}
            onSkipDirective={handleSkipDirective}
            onCompareStrategies={handleCompareStrategies}
            onPromoteStrategy={handlePromoteStrategy}
            onNavigate={handleNavigateFromPopup}
            submitting={talkSubmitting}
            clarifications={clarifications}
            onClarificationAnswer={handleClarificationAnswer}
            onClarificationSubmit={handleClarificationSubmit}
          />
        </div>

        {/* ── RIGHT: Actions & User Menu ───────────────────────────────────── */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {!isSysAdmin && (
            <>
              <button
                onClick={handleModeToggle}
                className={cn(
                  'p-2 rounded-full transition-colors',
                  uiMode === 'stream'
                    ? 'bg-violet-500/10 text-violet-500 hover:bg-violet-500/20'
                    : 'hover:bg-accent text-muted-foreground hover:text-foreground',
                )}
                title={uiMode === 'stream' ? 'Switch to Planning Console' : 'Switch to Decision Stream'}
              >
                {uiMode === 'stream' ? (
                  <LayoutGrid className="h-5 w-5" />
                ) : (
                  <Sparkles className="h-5 w-5" />
                )}
              </button>
              <button
                onClick={() => navigate('/help')}
                className="p-2 rounded-full hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                title="Help"
              >
                <HelpCircle className="h-5 w-5" />
              </button>
              <button
                className="relative p-2 rounded-full hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                title="Notifications"
              >
                <Bell className="h-5 w-5" />
                <span className="absolute top-1 right-1 h-2 w-2 bg-destructive rounded-full" />
              </button>
            </>
          )}

          {/* User Menu */}
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-accent transition-colors"
            >
              <div className="h-8 w-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-sm font-medium">
                {getInitials(user?.name || '')}
              </div>
              <div className="hidden sm:block text-left mr-1">
                <p className="text-sm font-medium text-foreground">{user?.name || user?.full_name || 'User'}</p>
                <p className="text-xs text-muted-foreground">
                  {user?.powell_role
                    ? user.powell_role.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
                    : user?.user_type === 'systemadmin'
                      ? 'System Admin'
                      : user?.user_type === 'tenantadmin'
                        ? 'Organization Admin'
                        : ''}
                </p>
              </div>
              {menuOpen ? (
                <X className="h-4 w-4 text-muted-foreground" />
              ) : (
                <Menu className="h-4 w-4 text-muted-foreground" />
              )}
            </button>

            {/* Dropdown Menu */}
            {menuOpen && (
              <div className="absolute right-0 mt-2 w-56 bg-popover border border-border rounded-lg shadow-lg py-1 z-50">
                {menuItems.map((item) => (
                  <button
                    key={item.path}
                    onClick={() => {
                      navigate(item.path);
                      setMenuOpen(false);
                    }}
                    className="w-full flex items-center gap-3 px-4 py-2 text-sm text-popover-foreground hover:bg-accent transition-colors"
                  >
                    <item.icon className="h-4 w-4" />
                    {item.label}
                  </button>
                ))}

                {adminMenuItems.length > 0 && (
                  <>
                    <div className="my-1 border-t border-border" />
                    {adminMenuItems.map((item) => (
                      <button
                        key={item.path}
                        onClick={() => {
                          navigate(item.path);
                          setMenuOpen(false);
                        }}
                        className="w-full flex items-center gap-3 px-4 py-2 text-sm text-popover-foreground hover:bg-accent transition-colors"
                      >
                        <item.icon className="h-4 w-4" />
                        {item.label}
                      </button>
                    ))}
                  </>
                )}

                <div className="my-1 border-t border-border" />
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-3 px-4 py-2 text-sm text-destructive hover:bg-accent transition-colors"
                >
                  <LogOut className="h-4 w-4" />
                  Logout
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};

export default TopNavbar;
