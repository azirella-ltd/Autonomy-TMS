/**
 * Context Engine — Unified hub for external context sources.
 *
 * Provides a bird's-eye view of Knowledge Base, Email Signals,
 * Slack Signals, and Market Intelligence with quick navigation to
 * each individual admin page.
 *
 * All sources feed into Azirella question answering and AI agent
 * decision context. ERP integrations (SAP / Odoo / D365 / B1 / Infor)
 * are explicitly NOT part of the Context Engine — they are the
 * transactional system of record, not side-channel context, and live
 * under Administration → ERP Data Management.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BookOpen,
  Mail,
  MessageSquare,
  Globe,
  Database,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertCircle,
  RefreshCw,
  Layers,
  ArrowRight,
} from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  CardContent,
  Skeleton,
} from '../../components/common';
import { api } from '../../services/api';
import { cn } from '@azirella-ltd/autonomy-frontend';

// ============================================================================
// Status helpers
// ============================================================================

const STATUS_CONFIG = {
  active: {
    label: 'Active',
    variant: 'success',
    icon: CheckCircle2,
    dotColor: 'bg-emerald-500',
  },
  inactive: {
    label: 'Inactive',
    variant: 'warning',
    icon: AlertCircle,
    dotColor: 'bg-amber-500',
  },
  not_configured: {
    label: 'Not Configured',
    variant: 'secondary',
    icon: XCircle,
    dotColor: 'bg-gray-400',
  },
  error: {
    label: 'Error',
    variant: 'destructive',
    icon: XCircle,
    dotColor: 'bg-red-500',
  },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.not_configured;
  const Icon = cfg.icon;
  return (
    <Badge variant={cfg.variant} size="sm">
      <Icon className="h-3 w-3 mr-0.5" />
      {cfg.label}
    </Badge>
  );
}

// ============================================================================
// Metric display
// ============================================================================

function MetricRow({ label, value, loading }) {
  if (loading) {
    return (
      <div className="flex items-center justify-between py-1">
        <span className="text-sm text-muted-foreground">{label}</span>
        <Skeleton className="h-4 w-16" />
      </div>
    );
  }
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{value ?? '--'}</span>
    </div>
  );
}

// ============================================================================
// Loading skeleton for a source card
// ============================================================================

function CardSkeleton() {
  return (
    <Card className="flex flex-col">
      <CardContent className="p-6 flex-1 flex flex-col">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-10 w-10 rounded-lg" />
            <div>
              <Skeleton className="h-5 w-32 mb-1" />
              <Skeleton className="h-3 w-20" />
            </div>
          </div>
        </div>
        <Skeleton className="h-4 w-full mb-4" />
        <div className="space-y-2 flex-1">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
        <Skeleton className="h-9 w-full mt-4" />
      </CardContent>
    </Card>
  );
}

// ============================================================================
// Source Card
// ============================================================================

function SourceCard({
  icon: Icon,
  name,
  description,
  status,
  metrics,
  loading,
  error,
  primaryAction,
  primaryLabel,
  secondaryAction,
  secondaryLabel,
  iconBgClass,
  iconColorClass,
}) {
  const resolvedStatus = error ? 'not_configured' : status;

  return (
    <Card className="flex flex-col transition-shadow hover:shadow-md">
      <CardContent className="p-6 flex-1 flex flex-col">
        {/* Header row */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                'flex items-center justify-center h-10 w-10 rounded-lg',
                iconBgClass || 'bg-primary/10'
              )}
            >
              <Icon
                className={cn(
                  'h-5 w-5',
                  iconColorClass || 'text-primary'
                )}
              />
            </div>
            <div>
              <h3 className="text-base font-semibold leading-tight">{name}</h3>
            </div>
          </div>
          <StatusBadge status={resolvedStatus} />
        </div>

        {/* Description */}
        <p className="text-sm text-muted-foreground mb-4 leading-relaxed">
          {description}
        </p>

        {/* Metrics */}
        <div className="flex-1 border-t border-border pt-3 mb-4">
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          ) : error ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
              <AlertCircle className="h-4 w-4 text-amber-500 flex-shrink-0" />
              <span>Not configured or unavailable</span>
            </div>
          ) : (
            <div className="space-y-0.5">
              {metrics.map((m) => (
                <MetricRow key={m.label} label={m.label} value={m.value} loading={false} />
              ))}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 mt-auto">
          <Button
            variant={error ? 'default' : 'outline'}
            size="sm"
            className="flex-1"
            onClick={primaryAction}
          >
            {error ? 'Set Up' : primaryLabel}
            <ArrowRight className="h-3.5 w-3.5 ml-1" />
          </Button>
          {secondaryAction && !error && (
            <Button variant="ghost" size="sm" onClick={secondaryAction}>
              {secondaryLabel}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function ContextEngine() {
  const navigate = useNavigate();

  // -- Knowledge Base state
  const [kbData, setKbData] = useState(null);
  const [kbLoading, setKbLoading] = useState(true);
  const [kbError, setKbError] = useState(false);

  // -- Email Signals state
  const [emailData, setEmailData] = useState(null);
  const [emailLoading, setEmailLoading] = useState(true);
  const [emailError, setEmailError] = useState(false);

  // -- Slack state
  const [slackData, setSlackData] = useState(null);
  const [slackLoading, setSlackLoading] = useState(true);
  const [slackError, setSlackError] = useState(false);

  // -- External Signals state (outside-in planning intelligence)
  const [extData, setExtData] = useState(null);
  const [extLoading, setExtLoading] = useState(true);
  const [extError, setExtError] = useState(false);

  // -- Global refresh
  const [refreshing, setRefreshing] = useState(false);

  // ── Fetch functions ────────────────────────────────────────────────────────

  // Active SC config that the Context Engine is reading from.
  // All four source endpoints return the same envelope with active_config_id /
  // active_config_name, so we pick whichever one answered first.
  const [activeConfig, setActiveConfig] = useState(null);

  // Each source's envelope:
  //   { is_configured, is_active, active_config_id, active_config_name, ...metrics }
  // We store the envelope directly and resolve status from the flags.

  const fetchKnowledgeBase = useCallback(async () => {
    setKbLoading(true);
    setKbError(false);
    try {
      const res = await api.get('/knowledge-base/dashboard');
      const d = res.data || {};
      setKbData({
        isConfigured: !!d.is_configured,
        isActive: !!d.is_active,
        documentCount: d.document_count || 0,
        chunkCount: d.chunk_count || 0,
        lastUpload: d.last_upload ? new Date(d.last_upload).toLocaleDateString() : null,
      });
      if (d.active_config_id != null) {
        setActiveConfig({ id: d.active_config_id, name: d.active_config_name });
      }
    } catch {
      setKbError(true);
    } finally {
      setKbLoading(false);
    }
  }, []);

  const fetchEmailSignals = useCallback(async () => {
    setEmailLoading(true);
    setEmailError(false);
    try {
      const res = await api.get('/email-signals/dashboard');
      const d = res.data || {};
      setEmailData({
        isConfigured: !!d.is_configured,
        isActive: !!d.is_active,
        activeConnections: d.active_connections ?? 0,
        totalConnections: d.total_connections ?? 0,
        signalsLast7d: d.signals_last_7d ?? d.signals_7d ?? d.recent_signals ?? 0,
        unprocessed: d.unprocessed ?? d.pending ?? 0,
      });
      if (d.active_config_id != null) {
        setActiveConfig({ id: d.active_config_id, name: d.active_config_name });
      }
    } catch {
      setEmailError(true);
    } finally {
      setEmailLoading(false);
    }
  }, []);

  const fetchSlackSignals = useCallback(async () => {
    setSlackLoading(true);
    setSlackError(false);
    try {
      const res = await api.get('/slack-signals/dashboard');
      const d = res.data || {};
      setSlackData({
        isConfigured: !!d.is_configured,
        isActive: !!d.is_active,
        activeConnections: d.active_connections ?? 0,
        totalConnections: d.total_connections ?? 0,
        signalsLast7d: d.signals_last_7d ?? 0,
        channelsMonitored: d.channels_monitored ?? 0,
      });
      if (d.active_config_id != null) {
        setActiveConfig({ id: d.active_config_id, name: d.active_config_name });
      }
    } catch {
      setSlackError(true);
    } finally {
      setSlackLoading(false);
    }
  }, []);

  const fetchExternalSignals = useCallback(async () => {
    setExtLoading(true);
    setExtError(false);
    try {
      const res = await api.get('/external-signals/dashboard');
      const d = res.data || {};
      setExtData({
        isConfigured: !!d.is_configured,
        isActive: !!d.is_active,
        activeSources: d.active_sources ?? d.sources?.filter(s => s.is_active).length ?? 0,
        totalSources: d.total_sources ?? d.sources?.length ?? 0,
        signalsLast30d: d.total_signals_30d ?? d.signals_last_30d ?? 0,
        highRelevance: d.high_relevance_signals ?? 0,
        topCategory: Object.entries(d.signals_by_category || {}).sort((a, b) => b[1] - a[1])[0]?.[0] || 'None',
      });
      if (d.active_config_id != null) {
        setActiveConfig({ id: d.active_config_id, name: d.active_config_name });
      }
    } catch {
      setExtError(true);
    } finally {
      setExtLoading(false);
    }
  }, []);

  const fetchAll = useCallback(async () => {
    setRefreshing(true);
    await Promise.allSettled([
      fetchKnowledgeBase(),
      fetchEmailSignals(),
      fetchSlackSignals(),
      fetchExternalSignals(),
    ]);
    setRefreshing(false);
  }, [fetchKnowledgeBase, fetchEmailSignals, fetchSlackSignals, fetchExternalSignals]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // ── Derived metrics ────────────────────────────────────────────────────────

  const activeCount = [
    !kbError && kbData?.isActive,
    !emailError && emailData?.isActive,
    !slackError && slackData?.isActive,
    !extError && extData?.isActive,
  ].filter(Boolean).length;

  const totalIngested = (
    (kbData?.documentCount || 0) +
    (emailData?.signalsLast7d || 0) +
    (slackData?.signalsLast7d || 0) +
    (extData?.signalsLast30d || 0)
  );

  const allLoading = kbLoading && emailLoading && slackLoading && extLoading;

  // ── Status resolvers ───────────────────────────────────────────────────────

  // Unified state resolver: uses the envelope flags from the backend.
  //   error          = API call failed (deployment or connectivity issue)
  //   not_configured = backend says is_configured=false (never set up)
  //   inactive       = configured but is_active=false (paused/empty)
  //   active         = configured and actively producing signals
  function resolveStatus(data, error) {
    if (error) return 'error';
    if (!data) return 'not_configured';
    if (!data.isConfigured) return 'not_configured';
    if (!data.isActive) return 'inactive';
    return 'active';
  }
  const kbStatus = () => resolveStatus(kbData, kbError);
  const emailStatus = () => resolveStatus(emailData, emailError);
  const slackStatus = () => resolveStatus(slackData, slackError);
  const extStatus = () => resolveStatus(extData, extError);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* ── Page header ─────────────────────────────────────────────────── */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <div className="flex items-center justify-center h-9 w-9 rounded-lg bg-primary/10">
                <Layers className="h-5 w-5 text-primary" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight">Context Engine</h1>
            </div>
            <p className="text-muted-foreground ml-12">
              Configure external context sources that inform AI agent decisions and power Azirella answers
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchAll}
            disabled={refreshing}
          >
            <RefreshCw
              className={cn('h-4 w-4 mr-1.5', refreshing && 'animate-spin')}
            />
            Refresh
          </Button>
        </div>

        {/* ── Active SC config banner ─────────────────────────────────────────
            The Context Engine is scoped to the tenant's active supply chain
            config. This banner shows which config's data is being read so
            admins can confirm they're looking at the right one. */}
        <Card className="mb-6 border-l-4 border-l-primary">
          <CardContent className="p-5">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-md bg-primary/10 text-primary">
                  <Database className="h-5 w-5" />
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">
                    Active Supply Chain Configuration
                  </div>
                  <div className="text-lg font-semibold">
                    {activeConfig?.name || <span className="text-muted-foreground italic">No active config</span>}
                  </div>
                  {activeConfig?.id != null && (
                    <div className="text-xs text-muted-foreground mt-0.5">
                      Context sources below are scoped to this configuration
                    </div>
                  )}
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate('/admin/supply-chain-configs')}
              >
                Manage Configs
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* ── Source cards grid ──────────────────────────────────────────────
            Order (per product spec):
              1. Active SC config (banner above)
              2. Internal knowledge base
              3. Market Intelligence
              4. Email Signals
              5. Slack Signals
        */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* 2. Knowledge Base */}
          <SourceCard
            icon={BookOpen}
            name="Knowledge Base"
            description="RAG document store powering agent context retrieval and Azirella answers. Upload PDFs, policies, and reference materials."
            status={kbStatus()}
            loading={kbLoading}
            error={kbError}
            iconBgClass="bg-blue-500/10"
            iconColorClass="text-blue-600 dark:text-blue-400"
            metrics={[
              { label: 'Documents indexed', value: kbData?.documentCount?.toLocaleString() },
              { label: 'Total chunks', value: kbData?.chunkCount?.toLocaleString() },
              { label: 'Last upload', value: kbData?.lastUpload || 'Never' },
            ]}
            primaryLabel="Manage Documents"
            primaryAction={() => navigate('/admin/knowledge-base')}
          />

          {/* 3. Market Intelligence (External Signals) */}
          <SourceCard
            icon={Globe}
            name="Market Intelligence"
            description="Outside-in planning signals from public APIs: weather, economic indicators, energy prices, geopolitical events, consumer trends, and regulatory alerts."
            status={extStatus()}
            loading={extLoading}
            error={extError}
            iconBgClass="bg-sky-500/10"
            iconColorClass="text-sky-600 dark:text-sky-400"
            metrics={[
              { label: 'Active sources', value: extData ? `${extData.activeSources} of ${extData.totalSources}` : null },
              { label: 'Signals (last 30 days)', value: extData?.signalsLast30d?.toLocaleString() },
              { label: 'High-relevance signals', value: extData?.highRelevance?.toLocaleString() },
              { label: 'Top category', value: extData?.topCategory },
            ]}
            primaryLabel="Manage Sources"
            primaryAction={() => navigate('/admin/external-signals')}
            secondaryLabel="Activate Defaults"
            secondaryAction={async () => {
              try {
                await api.post('/external-signals/sources/activate-defaults');
                fetchExternalSignals();
              } catch { /* ignore */ }
            }}
          />

          {/* 4. Email Signals */}
          <SourceCard
            icon={Mail}
            name="Email Signals"
            description="GDPR-safe email ingestion that extracts supply chain signals from customer and supplier emails. PII is stripped before storage."
            status={emailStatus()}
            loading={emailLoading}
            error={emailError}
            iconBgClass="bg-emerald-500/10"
            iconColorClass="text-emerald-600 dark:text-emerald-400"
            metrics={[
              { label: 'Active connections', value: emailData?.activeConnections },
              { label: 'Signals (last 7 days)', value: emailData?.signalsLast7d?.toLocaleString() },
              { label: 'Unprocessed', value: emailData?.unprocessed },
            ]}
            primaryLabel="Manage Connections"
            primaryAction={() => navigate('/admin/email-signals')}
          />

          {/* 5. Slack Signals */}
          <SourceCard
            icon={MessageSquare}
            name="Slack Signals"
            description="Monitor Slack channels for supply chain signals. Classify messages and route actionable intelligence to TRM agents."
            status={slackStatus()}
            loading={slackLoading}
            error={slackError}
            iconBgClass="bg-amber-500/10"
            iconColorClass="text-amber-600 dark:text-amber-400"
            metrics={[
              { label: 'Active connections', value: slackData?.activeConnections },
              { label: 'Signals (last 7 days)', value: slackData?.signalsLast7d?.toLocaleString() },
              { label: 'Channels monitored', value: slackData?.channelsMonitored },
            ]}
            primaryLabel="Manage Slack"
            primaryAction={() => navigate('/admin/slack-signals')}
          />
        </div>

        {/* ── Summary status bar ──────────────────────────────────────────── */}
        <Card>
          <CardContent className="p-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div className="flex items-center gap-6">
                {/* Active sources */}
                <div className="flex items-center gap-2">
                  <div className="flex -space-x-1">
                    {[kbStatus(), emailStatus(), slackStatus(), extStatus()].map(
                      (s, i) => (
                        <div
                          key={i}
                          className={cn(
                            'h-3 w-3 rounded-full border-2 border-background',
                            STATUS_CONFIG[s]?.dotColor || 'bg-gray-400'
                          )}
                        />
                      )
                    )}
                  </div>
                  <span className="text-sm font-medium">
                    {allLoading ? (
                      <Loader2 className="h-4 w-4 animate-spin inline" />
                    ) : (
                      <>
                        {activeCount} of 5{' '}
                        <span className="text-muted-foreground font-normal">
                          sources active
                        </span>
                      </>
                    )}
                  </span>
                </div>

                {/* Divider */}
                <div className="hidden sm:block h-5 w-px bg-border" />

                {/* Total ingested */}
                <div className="text-sm">
                  <span className="font-medium">{allLoading ? '--' : totalIngested.toLocaleString()}</span>{' '}
                  <span className="text-muted-foreground">
                    documents and signals ingested
                  </span>
                </div>
              </div>

              <p className="text-xs text-muted-foreground max-w-md">
                All sources feed into Azirella question answering and AI agent decision context
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
