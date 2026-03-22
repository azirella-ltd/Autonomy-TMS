/**
 * Context Engine — Unified hub for all external context sources.
 *
 * Provides a bird's-eye view of Knowledge Base, Email Signals,
 * SAP Integration, and Slack Signals with quick navigation to
 * each individual admin page.
 *
 * All sources feed into Azirella question answering and
 * AI agent decision context.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BookOpen,
  Mail,
  Database,
  MessageSquare,
  Globe,
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
import { cn } from '../../lib/utils/cn';

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

  // -- SAP state
  const [sapData, setSapData] = useState(null);
  const [sapLoading, setSapLoading] = useState(true);
  const [sapError, setSapError] = useState(false);

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

  const fetchKnowledgeBase = useCallback(async () => {
    setKbLoading(true);
    setKbError(false);
    try {
      const res = await api.get('/knowledge-base/documents');
      const docs = Array.isArray(res.data) ? res.data : res.data?.documents || [];
      const totalChunks = docs.reduce(
        (sum, d) => sum + (d.chunk_count || d.chunks?.length || 0),
        0
      );
      const lastUpload = docs.length > 0
        ? docs
            .map((d) => d.created_at || d.uploaded_at)
            .filter(Boolean)
            .sort()
            .pop()
        : null;
      setKbData({
        documentCount: docs.length,
        chunkCount: totalChunks,
        lastUpload: lastUpload
          ? new Date(lastUpload).toLocaleDateString()
          : null,
      });
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
      const d = res.data;
      setEmailData({
        activeConnections: d.active_connections ?? d.connections_active ?? 0,
        signalsLast7d: d.signals_last_7d ?? d.signals_7d ?? d.recent_signals ?? 0,
        unprocessed: d.unprocessed ?? d.pending ?? 0,
      });
    } catch {
      setEmailError(true);
    } finally {
      setEmailLoading(false);
    }
  }, []);

  const fetchSapData = useCallback(async () => {
    setSapLoading(true);
    setSapError(false);
    try {
      const res = await api.get('/sap-data/dashboard');
      const d = res.data;
      setSapData({
        connections: d.total_connections ?? d.connections ?? 0,
        lastSync: d.last_sync
          ? new Date(d.last_sync).toLocaleDateString()
          : d.last_sync_label ?? 'Never',
        mappedFields: d.mapped_fields ?? d.total_mapped_fields ?? 0,
      });
    } catch {
      setSapError(true);
    } finally {
      setSapLoading(false);
    }
  }, []);

  const fetchSlackSignals = useCallback(async () => {
    setSlackLoading(true);
    setSlackError(false);
    try {
      const res = await api.get('/slack-signals/dashboard');
      const d = res.data;
      setSlackData({
        activeConnections: d.active_connections ?? d.connections_active ?? 0,
        signalsLast7d: d.signals_last_7d ?? d.signals_7d ?? d.recent_signals ?? 0,
        channelsMonitored: d.channels_monitored ?? d.channels ?? 0,
      });
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
      const d = res.data;
      setExtData({
        activeSources: d.sources?.filter(s => s.is_active).length ?? 0,
        totalSources: d.sources?.length ?? 0,
        signalsLast30d: d.total_signals_30d ?? 0,
        highRelevance: d.high_relevance_signals ?? 0,
        topCategory: Object.entries(d.signals_by_category || {}).sort((a, b) => b[1] - a[1])[0]?.[0] || 'None',
      });
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
      fetchSapData(),
      fetchSlackSignals(),
      fetchExternalSignals(),
    ]);
    setRefreshing(false);
  }, [fetchKnowledgeBase, fetchEmailSignals, fetchSapData, fetchSlackSignals, fetchExternalSignals]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // ── Derived metrics ────────────────────────────────────────────────────────

  const activeCount = [
    !kbError && kbData && kbData.documentCount > 0,
    !emailError && emailData && emailData.activeConnections > 0,
    !sapError && sapData && sapData.connections > 0,
    !slackError && slackData && slackData.activeConnections > 0,
    !extError && extData && extData.activeSources > 0,
  ].filter(Boolean).length;

  const totalIngested = (
    (kbData?.documentCount || 0) +
    (emailData?.signalsLast7d || 0) +
    (slackData?.signalsLast7d || 0) +
    (extData?.signalsLast30d || 0)
  );

  const allLoading = kbLoading && emailLoading && sapLoading && slackLoading && extLoading;

  // ── Status resolvers ───────────────────────────────────────────────────────

  function kbStatus() {
    if (kbError) return 'not_configured';
    if (!kbData) return 'not_configured';
    return kbData.documentCount > 0 ? 'active' : 'inactive';
  }

  function emailStatus() {
    if (emailError) return 'not_configured';
    if (!emailData) return 'not_configured';
    return emailData.activeConnections > 0 ? 'active' : 'inactive';
  }

  function sapStatus() {
    if (sapError) return 'not_configured';
    if (!sapData) return 'not_configured';
    return sapData.connections > 0 ? 'active' : 'inactive';
  }

  function slackStatus() {
    if (slackError) return 'not_configured';
    if (!slackData) return 'not_configured';
    return slackData.activeConnections > 0 ? 'active' : 'inactive';
  }

  function extStatus() {
    if (extError) return 'not_configured';
    if (!extData) return 'not_configured';
    return extData.activeSources > 0 ? 'active' : 'inactive';
  }

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

        {/* ── Source cards grid ────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* Knowledge Base */}
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

          {/* Email Signals */}
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

          {/* SAP Integration */}
          <SourceCard
            icon={Database}
            name="SAP Integration"
            description="Connect to S/4HANA, APO, ECC, or BW to ingest master data via RFC, CSV, or OData. AI-powered field mapping for Z-tables."
            status={sapStatus()}
            loading={sapLoading}
            error={sapError}
            iconBgClass="bg-purple-500/10"
            iconColorClass="text-purple-600 dark:text-purple-400"
            metrics={[
              { label: 'Connections', value: sapData?.connections },
              { label: 'Last sync', value: sapData?.lastSync },
              { label: 'Mapped fields', value: sapData?.mappedFields?.toLocaleString() },
            ]}
            primaryLabel="Manage SAP"
            primaryAction={() => navigate('/admin/sap-data')}
          />

          {/* Slack Signals */}
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

          {/* External Signals — Outside-In Planning */}
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
        </div>

        {/* ── Summary status bar ──────────────────────────────────────────── */}
        <Card>
          <CardContent className="p-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div className="flex items-center gap-6">
                {/* Active sources */}
                <div className="flex items-center gap-2">
                  <div className="flex -space-x-1">
                    {[kbStatus(), emailStatus(), sapStatus(), slackStatus(), extStatus()].map(
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
