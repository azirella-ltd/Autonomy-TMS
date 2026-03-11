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
  CheckCircle2,
  ChevronRight,
  Loader2,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useActiveConfig } from '../contexts/ActiveConfigContext';
import { isSystemAdmin } from '../utils/authUtils';
import simulationApi, { api } from '../services/api';
import { getSupplyChainConfigById } from '../services/supplyChainConfigService';
import { cn } from '../lib/utils/cn';

// ─── AI Avatar ────────────────────────────────────────────────────────────────
// A small circular avatar used alongside the "Talk to me" prompt.
// Uses a violet-to-indigo gradient with a Sparkles icon to evoke AI/intelligence.
const AIAvatar = ({ size = 'sm' }) => {
  const dim = size === 'sm' ? 'h-7 w-7' : 'h-9 w-9';
  const icon = size === 'sm' ? 'h-3.5 w-3.5' : 'h-4 w-4';
  return (
    <div
      className={cn(
        dim,
        'rounded-full flex items-center justify-center flex-shrink-0',
        'bg-gradient-to-br from-violet-500 via-purple-500 to-indigo-600',
        'shadow-[0_0_10px_rgba(139,92,246,0.4)]',
      )}
      aria-hidden="true"
    >
      <Sparkles className={cn(icon, 'text-white')} />
    </div>
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
  const talkInputRef = useRef(null);
  const clarificationRef = useRef(null);

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

  // Dismiss clarification panel when clicking outside
  useEffect(() => {
    if (!analysisResult) return;
    const handleClickOutside = (event) => {
      if (
        clarificationRef.current &&
        !clarificationRef.current.contains(event.target) &&
        !talkInputRef.current?.contains(event.target)
      ) {
        dismissClarification();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [analysisResult, dismissClarification]);

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
    try {
      const response = await api.post('/directives/analyze', {
        config_id: effectiveConfigId,
        text: prompt,
      });
      const analysis = response.data;

      if (analysis.is_complete || (analysis.missing_fields?.length || 0) === 0) {
        // No gaps — submit immediately
        await submitFinalDirective(prompt, {});
      } else {
        // Gaps found — show clarification panel
        setOriginalText(prompt);
        setAnalysisResult(analysis);
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
      });
      const result = response.data;
      setDirectiveResult(result);
      setTalkInput('');
      dismissClarification();
      setTimeout(() => setDirectiveResult(null), 6000);
    } catch (err) {
      console.error('Directive submission failed:', err);
    } finally {
      setTalkSubmitting(false);
    }
  };

  const handleClarificationAnswer = (field, value) => {
    setClarifications((prev) => ({ ...prev, [field]: value }));
  };

  const handleClarificationSubmit = () => {
    // Check all required fields are answered
    const missing = (analysisResult?.missing_fields || []);
    const unanswered = missing.filter((m) => !clarifications[m.field]?.trim());
    if (unanswered.length > 0) return; // Still have unanswered questions
    submitFinalDirective(originalText, clarifications);
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
            <AIAvatar size="sm" />

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

          {/* Clarification panel — shown when analysis found missing fields */}
          {analysisResult && totalMissing > 0 && (
            <div
              ref={clarificationRef}
              className={cn(
                'absolute top-full mt-1 left-1/2 -translate-x-1/2 z-50',
                'bg-popover border border-border rounded-lg shadow-lg px-4 py-3',
                'text-sm max-w-lg w-full animate-in fade-in slide-in-from-top-2 duration-200',
              )}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-2.5">
                <div className="flex items-center gap-2">
                  <AIAvatar size="sm" />
                  <span className="font-medium text-foreground">
                    A few clarifying questions
                  </span>
                </div>
                <button
                  onClick={dismissClarification}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>

              {/* Parsed context */}
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-3">
                <span className="truncate italic">"{originalText}"</span>
                <ChevronRight className="h-3 w-3 flex-shrink-0" />
                <span className="capitalize">{analysisResult.target_layer} layer</span>
                {analysisResult.confidence > 0 && (
                  <span className="ml-1">({Math.round(analysisResult.confidence * 100)}%)</span>
                )}
              </div>

              {/* Missing fields */}
              <div className="space-y-2.5">
                {(analysisResult.missing_fields || []).map((mf) => (
                  <div key={mf.field}>
                    <label className="block text-xs font-medium text-foreground mb-1">
                      {mf.question}
                    </label>
                    {mf.type === 'select' && mf.options?.length > 0 ? (
                      <select
                        value={clarifications[mf.field] || ''}
                        onChange={(e) => handleClarificationAnswer(mf.field, e.target.value)}
                        className={cn(
                          'w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm',
                          'focus:outline-none focus:ring-2 focus:ring-violet-400/30 focus:border-violet-400/60',
                        )}
                      >
                        <option value="">Select…</option>
                        {mf.options.map((opt) => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    ) : mf.type === 'number' ? (
                      <input
                        type="number"
                        value={clarifications[mf.field] || ''}
                        onChange={(e) => handleClarificationAnswer(mf.field, e.target.value)}
                        placeholder="e.g. 10"
                        className={cn(
                          'w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm',
                          'focus:outline-none focus:ring-2 focus:ring-violet-400/30 focus:border-violet-400/60',
                        )}
                      />
                    ) : (
                      <input
                        type="text"
                        value={clarifications[mf.field] || ''}
                        onChange={(e) => handleClarificationAnswer(mf.field, e.target.value)}
                        placeholder="Type your answer…"
                        className={cn(
                          'w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm',
                          'focus:outline-none focus:ring-2 focus:ring-violet-400/30 focus:border-violet-400/60',
                        )}
                      />
                    )}
                  </div>
                ))}
              </div>

              {/* Progress + Submit */}
              <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-border">
                <span className="text-xs text-muted-foreground">
                  {answeredCount} of {totalMissing} answered
                </span>
                <button
                  onClick={handleClarificationSubmit}
                  disabled={!allAnswered || talkSubmitting}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all',
                    allAnswered && !talkSubmitting
                      ? 'bg-violet-500 text-white hover:bg-violet-600'
                      : 'bg-muted text-muted-foreground cursor-not-allowed',
                  )}
                >
                  {talkSubmitting ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <CheckCircle2 className="h-3 w-3" />
                  )}
                  Submit directive
                </button>
              </div>
            </div>
          )}

          {/* Directive result feedback */}
          {directiveResult && (
            <div
              className={cn(
                'absolute top-full mt-1 left-1/2 -translate-x-1/2 z-50',
                'bg-popover border border-border rounded-lg shadow-lg px-4 py-2.5',
                'text-sm max-w-lg w-full animate-in fade-in slide-in-from-top-2 duration-200',
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className={cn(
                      'h-2 w-2 rounded-full flex-shrink-0',
                      directiveResult.parser_confidence >= 0.7 ? 'bg-emerald-500' :
                      directiveResult.parser_confidence >= 0.4 ? 'bg-amber-500' : 'bg-red-500',
                    )}
                  />
                  <span className="font-medium truncate">
                    {directiveResult.directive_type?.replace(/_/g, ' ')}
                  </span>
                  <span className="text-muted-foreground">
                    → {directiveResult.target_layer}
                  </span>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0 text-xs text-muted-foreground">
                  <span>{Math.round(directiveResult.parser_confidence * 100)}% confidence</span>
                  <span className={cn(
                    'px-1.5 py-0.5 rounded-full text-[10px] font-medium',
                    directiveResult.status === 'APPLIED' ? 'bg-emerald-500/10 text-emerald-600' : 'bg-blue-500/10 text-blue-600',
                  )}>
                    {directiveResult.status}
                  </span>
                  <button
                    onClick={() => setDirectiveResult(null)}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              {directiveResult.routed_actions?.length > 0 && (
                <div className="mt-1.5 text-xs text-muted-foreground">
                  Routed to {directiveResult.routed_actions.length} action{directiveResult.routed_actions.length > 1 ? 's' : ''}: {
                    directiveResult.routed_actions.map(a => a.layer || a.trm_type).join(', ')
                  }
                </div>
              )}
            </div>
          )}
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
