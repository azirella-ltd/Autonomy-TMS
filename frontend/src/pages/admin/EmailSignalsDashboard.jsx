/**
 * EmailSignalsDashboard — Monitor and manage email-derived SC signals.
 *
 * Tabs:
 *   1. Signals: Table of ingested signals with status, partner, type, urgency
 *   2. Connections: Configure IMAP/Gmail inbox connections
 *   3. Analytics: Signal volume, type breakdown, partner breakdown
 *   4. Test: Manual email paste for testing the classification pipeline
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Mail, PlugZap, BarChart3, FlaskConical, RefreshCw,
  ChevronRight, CheckCircle2, XCircle, AlertTriangle,
  Clock, ArrowUpRight, ArrowDownRight, Minus, Plus,
  Trash2, Play, Eye, X, Send, Loader2,
} from 'lucide-react';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import { cn } from '@azirella-ltd/autonomy-frontend';

// ── Signal type colors ──────────────────────────────────────────────────────
const SIGNAL_COLORS = {
  demand_increase: 'bg-emerald-500/10 text-emerald-700',
  demand_decrease: 'bg-red-500/10 text-red-700',
  supply_disruption: 'bg-orange-500/10 text-orange-700',
  lead_time_change: 'bg-amber-500/10 text-amber-700',
  price_change: 'bg-purple-500/10 text-purple-700',
  quality_issue: 'bg-rose-500/10 text-rose-700',
  new_product: 'bg-blue-500/10 text-blue-700',
  discontinuation: 'bg-gray-500/10 text-gray-700',
  order_exception: 'bg-yellow-500/10 text-yellow-700',
  capacity_change: 'bg-indigo-500/10 text-indigo-700',
  regulatory: 'bg-slate-500/10 text-slate-700',
  general_inquiry: 'bg-zinc-500/10 text-zinc-600',
};

const STATUS_ICONS = {
  INGESTED: Clock,
  CLASSIFIED: Eye,
  ROUTED: ArrowUpRight,
  ACTED: CheckCircle2,
  DISMISSED: XCircle,
};

const DirectionIcon = ({ direction }) => {
  if (direction === 'up') return <ArrowUpRight className="h-3.5 w-3.5 text-emerald-600" />;
  if (direction === 'down') return <ArrowDownRight className="h-3.5 w-3.5 text-red-600" />;
  return <Minus className="h-3.5 w-3.5 text-muted-foreground" />;
};

const UrgencyBadge = ({ urgency }) => {
  const u = urgency || 0;
  const color = u >= 0.8 ? 'bg-red-500' : u >= 0.5 ? 'bg-amber-500' : 'bg-emerald-500';
  return (
    <div className="flex items-center gap-1.5">
      <div className={cn('h-2 w-2 rounded-full', color)} />
      <span className="text-xs">{Math.round(u * 100)}%</span>
    </div>
  );
};

// ── Tabs ────────────────────────────────────────────────────────────────────

const TABS = [
  { key: 'signals', label: 'Signals', icon: Mail },
  { key: 'connections', label: 'Connections', icon: PlugZap },
  { key: 'analytics', label: 'Analytics', icon: BarChart3 },
  { key: 'test', label: 'Test Ingestion', icon: FlaskConical },
];

export default function EmailSignalsDashboard() {
  const [activeTab, setActiveTab] = useState('signals');
  const [signals, setSignals] = useState([]);
  const [connections, setConnections] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedSignal, setSelectedSignal] = useState(null);
  const { effectiveConfigId } = useActiveConfig();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [sigRes, connRes, dashRes] = await Promise.allSettled([
        api.get('/email-signals/signals', { params: { limit: 100 } }),
        api.get('/email-signals/connections'),
        api.get('/email-signals/dashboard'),
      ]);
      if (sigRes.status === 'fulfilled') setSignals(sigRes.value.data);
      if (connRes.status === 'fulfilled') setConnections(connRes.value.data);
      if (dashRes.status === 'fulfilled') setDashboard(dashRes.value.data);
    } catch (err) {
      console.error('Failed to load email signals data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Email Signal Intelligence</h1>
          <p className="text-sm text-muted-foreground mt-1">
            GDPR-safe email ingestion — company identification only, no personal data stored
          </p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border hover:bg-accent text-sm"
        >
          <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
          Refresh
        </button>
      </div>

      {/* Stats row */}
      {dashboard && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total Signals" value={dashboard.total} />
          <StatCard label="Last 24h" value={dashboard.last_24h} />
          <StatCard label="Avg Confidence" value={`${Math.round(dashboard.avg_confidence * 100)}%`} />
          <StatCard label="Avg Urgency" value={`${Math.round(dashboard.avg_urgency * 100)}%`} />
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-border">
        <div className="flex gap-1">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors',
                activeTab === tab.key
                  ? 'border-violet-500 text-violet-600'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      {activeTab === 'signals' && (
        <SignalsTab
          signals={signals}
          selectedSignal={selectedSignal}
          setSelectedSignal={setSelectedSignal}
          onRefresh={loadData}
        />
      )}
      {activeTab === 'connections' && (
        <ConnectionsTab connections={connections} onRefresh={loadData} />
      )}
      {activeTab === 'analytics' && (
        <AnalyticsTab dashboard={dashboard} />
      )}
      {activeTab === 'test' && (
        <TestTab configId={effectiveConfigId} onRefresh={loadData} />
      )}
    </div>
  );
}

// ── Signals Tab ─────────────────────────────────────────────────────────────

function SignalsTab({ signals, selectedSignal, setSelectedSignal, onRefresh }) {
  const handleDismiss = async (signalId) => {
    try {
      await api.post(`/email-signals/signals/${signalId}/dismiss`, {
        reason: 'Not actionable',
      });
      onRefresh();
    } catch (err) {
      console.error('Dismiss failed:', err);
    }
  };

  return (
    <div className="space-y-4">
      {signals.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Mail className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p>No email signals yet</p>
          <p className="text-xs mt-1">Configure an email connection or use the Test tab to try it out</p>
        </div>
      ) : (
        <div className="border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 border-b border-border">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium">Signal</th>
                <th className="text-left px-4 py-2.5 font-medium">Partner</th>
                <th className="text-left px-4 py-2.5 font-medium">Type</th>
                <th className="text-left px-4 py-2.5 font-medium">Direction</th>
                <th className="text-left px-4 py-2.5 font-medium">Urgency</th>
                <th className="text-left px-4 py-2.5 font-medium">Status</th>
                <th className="text-left px-4 py-2.5 font-medium">Received</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {signals.map((s) => {
                const StatusIcon = STATUS_ICONS[s.status] || Clock;
                return (
                  <React.Fragment key={s.id}>
                    <tr
                      onClick={() => setSelectedSignal(selectedSignal?.id === s.id ? null : s)}
                      className={cn(
                        'hover:bg-accent/50 cursor-pointer transition-colors',
                        selectedSignal?.id === s.id && 'bg-accent/30',
                      )}
                    >
                      <td className="px-4 py-2.5 max-w-[280px]">
                        <p className="truncate font-medium">{s.signal_summary}</p>
                        {s.subject_scrubbed && (
                          <p className="text-xs text-muted-foreground truncate">{s.subject_scrubbed}</p>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="font-medium">{s.partner_name || s.sender_domain}</span>
                        {s.partner_type && s.partner_type !== 'unknown' && (
                          <span className="text-xs text-muted-foreground ml-1">({s.partner_type})</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={cn(
                          'px-2 py-0.5 rounded-full text-xs font-medium',
                          SIGNAL_COLORS[s.signal_type] || SIGNAL_COLORS.general_inquiry,
                        )}>
                          {s.signal_type?.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-1">
                          <DirectionIcon direction={s.signal_direction} />
                          {s.signal_magnitude_pct && (
                            <span className="text-xs">{s.signal_magnitude_pct}%</span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-2.5">
                        <UrgencyBadge urgency={s.signal_urgency} />
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-1.5">
                          <StatusIcon className="h-3.5 w-3.5" />
                          <span className="text-xs">{s.status}</span>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground">
                        {s.received_at ? new Date(s.received_at).toLocaleDateString() : '-'}
                      </td>
                      <td className="px-4 py-2.5">
                        {s.status !== 'DISMISSED' && (
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDismiss(s.id); }}
                            className="text-muted-foreground hover:text-destructive p-1 rounded"
                            title="Dismiss"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </td>
                    </tr>
                    {/* Expanded detail */}
                    {selectedSignal?.id === s.id && (
                      <tr>
                        <td colSpan={8} className="px-4 py-4 bg-muted/20">
                          <div className="space-y-3 text-sm">
                            <div>
                              <span className="font-medium">Scrubbed body:</span>
                              <p className="mt-1 text-muted-foreground whitespace-pre-wrap bg-background rounded-lg p-3 border border-border text-xs max-h-48 overflow-y-auto">
                                {s.body_scrubbed}
                              </p>
                            </div>
                            <div className="grid grid-cols-3 gap-4">
                              <div>
                                <span className="text-xs font-medium text-muted-foreground">Confidence</span>
                                <p>{Math.round(s.signal_confidence * 100)}%</p>
                              </div>
                              <div>
                                <span className="text-xs font-medium text-muted-foreground">Products</span>
                                <p>{s.resolved_product_ids?.join(', ') || 'None resolved'}</p>
                              </div>
                              <div>
                                <span className="text-xs font-medium text-muted-foreground">Sites</span>
                                <p>{s.resolved_site_ids?.join(', ') || 'None resolved'}</p>
                              </div>
                            </div>
                            {s.target_trm_types?.length > 0 && (
                              <div>
                                <span className="text-xs font-medium text-muted-foreground">Routed to TRMs:</span>
                                <div className="flex gap-1.5 mt-1">
                                  {s.target_trm_types.map((trm) => (
                                    <span key={trm} className="px-2 py-0.5 rounded-full text-xs bg-violet-500/10 text-violet-700">
                                      {trm.replace(/_/g, ' ')}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Connections Tab ──────────────────────────────────────────────────────────

function ConnectionsTab({ connections, onRefresh }) {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: '', connection_type: 'imap', imap_host: '', imap_port: 993,
    imap_username: '', imap_password: '', imap_folder: 'INBOX',
    domain_allowlist: '',
  });
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {
        ...form,
        imap_port: parseInt(form.imap_port) || 993,
        domain_allowlist: form.domain_allowlist
          ? form.domain_allowlist.split(',').map((d) => d.trim()).filter(Boolean)
          : null,
      };
      await api.post('/email-signals/connections', payload);
      setShowForm(false);
      setForm({ name: '', connection_type: 'imap', imap_host: '', imap_port: 993, imap_username: '', imap_password: '', imap_folder: 'INBOX', domain_allowlist: '' });
      onRefresh();
    } catch (err) {
      console.error('Save failed:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (id) => {
    try {
      const res = await api.post(`/email-signals/connections/${id}/test`);
      alert(res.data.ok ? `Connected: ${res.data.message}` : `Failed: ${res.data.message}`);
    } catch (err) {
      alert('Test failed: ' + err.message);
    }
  };

  const handlePoll = async (id) => {
    try {
      const res = await api.post(`/email-signals/connections/${id}/poll`);
      alert(`Fetched ${res.data.fetched} emails, ingested ${res.data.ingested} signals`);
      onRefresh();
    } catch (err) {
      alert('Poll failed: ' + err.message);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this connection?')) return;
    try {
      await api.delete(`/email-signals/connections/${id}`);
      onRefresh();
    } catch (err) {
      console.error('Delete failed:', err);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <p className="text-sm text-muted-foreground">
          Email connections are polled automatically every 5 minutes for new SC signals.
        </p>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-violet-500 text-white hover:bg-violet-600 text-sm"
        >
          <Plus className="h-4 w-4" />
          Add Connection
        </button>
      </div>

      {/* New connection form */}
      {showForm && (
        <div className="border border-border rounded-lg p-4 space-y-3 bg-muted/30">
          <div className="grid grid-cols-2 gap-3">
            <input className="border border-border rounded-md px-3 py-2 text-sm bg-background" placeholder="Connection name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <select className="border border-border rounded-md px-3 py-2 text-sm bg-background" value={form.connection_type} onChange={(e) => setForm({ ...form, connection_type: e.target.value })}>
              <option value="imap">IMAP</option>
              <option value="gmail">Gmail</option>
            </select>
            <input className="border border-border rounded-md px-3 py-2 text-sm bg-background" placeholder="IMAP Host" value={form.imap_host} onChange={(e) => setForm({ ...form, imap_host: e.target.value })} />
            <input className="border border-border rounded-md px-3 py-2 text-sm bg-background" placeholder="Port" type="number" value={form.imap_port} onChange={(e) => setForm({ ...form, imap_port: e.target.value })} />
            <input className="border border-border rounded-md px-3 py-2 text-sm bg-background" placeholder="Username" value={form.imap_username} onChange={(e) => setForm({ ...form, imap_username: e.target.value })} />
            <input className="border border-border rounded-md px-3 py-2 text-sm bg-background" placeholder="Password" type="password" value={form.imap_password} onChange={(e) => setForm({ ...form, imap_password: e.target.value })} />
            <input className="border border-border rounded-md px-3 py-2 text-sm bg-background" placeholder="Folder (default: INBOX)" value={form.imap_folder} onChange={(e) => setForm({ ...form, imap_folder: e.target.value })} />
            <input className="border border-border rounded-md px-3 py-2 text-sm bg-background" placeholder="Domain allowlist (comma-separated)" value={form.domain_allowlist} onChange={(e) => setForm({ ...form, domain_allowlist: e.target.value })} />
          </div>
          <div className="flex gap-2">
            <button onClick={handleSave} disabled={saving || !form.name} className="px-3 py-1.5 rounded-lg bg-violet-500 text-white hover:bg-violet-600 text-sm disabled:opacity-50">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}
            </button>
            <button onClick={() => setShowForm(false)} className="px-3 py-1.5 rounded-lg border border-border text-sm hover:bg-accent">Cancel</button>
          </div>
        </div>
      )}

      {/* Existing connections */}
      {connections.length === 0 && !showForm ? (
        <div className="text-center py-12 text-muted-foreground">
          <PlugZap className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p>No email connections configured</p>
        </div>
      ) : (
        <div className="space-y-3">
          {connections.map((c) => (
            <div key={c.id} className="border border-border rounded-lg p-4 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className={cn('h-2 w-2 rounded-full', c.is_active ? 'bg-emerald-500' : 'bg-gray-400')} />
                  <span className="font-medium">{c.name}</span>
                  <span className="text-xs text-muted-foreground">{c.connection_type.toUpperCase()}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {c.imap_host || 'Gmail'} | Folder: {c.imap_folder || 'INBOX'} | Poll every {c.poll_interval_minutes}m
                  {c.last_poll_at && ` | Last poll: ${new Date(c.last_poll_at).toLocaleString()}`}
                </p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => handleTest(c.id)} className="px-2 py-1 rounded text-xs border border-border hover:bg-accent" title="Test">Test</button>
                <button onClick={() => handlePoll(c.id)} className="px-2 py-1 rounded text-xs border border-border hover:bg-accent" title="Poll now">
                  <Play className="h-3 w-3" />
                </button>
                <button onClick={() => handleDelete(c.id)} className="px-2 py-1 rounded text-xs border border-border hover:bg-accent text-destructive" title="Delete">
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Analytics Tab ───────────────────────────────────────────────────────────

function AnalyticsTab({ dashboard }) {
  if (!dashboard || dashboard.total === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <BarChart3 className="h-12 w-12 mx-auto mb-3 opacity-30" />
        <p>No data yet — signals will appear after email ingestion starts</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {/* By type */}
      <div className="border border-border rounded-lg p-4">
        <h3 className="font-medium mb-3">Signal Types</h3>
        <div className="space-y-2">
          {Object.entries(dashboard.by_type).map(([type, count]) => (
            <div key={type} className="flex items-center justify-between">
              <span className={cn(
                'px-2 py-0.5 rounded-full text-xs font-medium',
                SIGNAL_COLORS[type] || SIGNAL_COLORS.general_inquiry,
              )}>
                {type.replace(/_/g, ' ')}
              </span>
              <span className="text-sm font-medium">{count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* By status */}
      <div className="border border-border rounded-lg p-4">
        <h3 className="font-medium mb-3">By Status</h3>
        <div className="space-y-2">
          {Object.entries(dashboard.by_status).map(([status, count]) => {
            const Icon = STATUS_ICONS[status] || Clock;
            return (
              <div key={status} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm">{status}</span>
                </div>
                <span className="text-sm font-medium">{count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Top partners */}
      <div className="border border-border rounded-lg p-4 md:col-span-2">
        <h3 className="font-medium mb-3">Top Partners</h3>
        <div className="space-y-2">
          {(dashboard.top_partners || []).map((p, i) => (
            <div key={i} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-medium">{p.name}</span>
                {p.type && p.type !== 'unknown' && (
                  <span className="text-xs text-muted-foreground">({p.type})</span>
                )}
              </div>
              <span className="text-sm font-medium">{p.count} signals</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Test Tab ────────────────────────────────────────────────────────────────

function TestTab({ configId, onRefresh }) {
  const [form, setForm] = useState({
    from_header: 'Sarah Johnson <sarah.johnson@acme-supplies.com>',
    subject: 'Lead time extension notice - Q2 2026',
    body: `Dear [NAME],

We are writing to inform you that due to raw material shortages affecting our tier-2 suppliers, we will need to extend lead times on the following product categories by approximately 2-3 weeks effective April 1st:

- Frozen proteins (all SKUs)
- Refrigerated dairy products

Current lead time: 5 business days
New lead time: 7-8 business days (estimated)

We expect this situation to normalize by mid-May 2026. We recommend adjusting your safety stock levels accordingly.

Please let us know if you need to discuss alternative sourcing arrangements.

Best regards,
[NAME]
VP of Sales, ACME Supplies
[PHONE] | [EMAIL]`,
  });
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const handleSubmit = async () => {
    if (!configId) {
      alert('No active supply chain config selected');
      return;
    }
    setSubmitting(true);
    setResult(null);
    try {
      const res = await api.post('/email-signals/ingest-manual', {
        config_id: configId,
        from_header: form.from_header,
        subject: form.subject,
        body: form.body,
      });
      setResult(res.data);
      onRefresh();
    } catch (err) {
      setResult({ error: err.response?.data?.detail || err.message });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Paste an email to test the classification pipeline. PII will be scrubbed, the sender domain
        resolved to a TradingPartner, and the content classified into a supply chain signal.
      </p>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium mb-1">From (include email for domain resolution)</label>
          <input
            className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background"
            value={form.from_header}
            onChange={(e) => setForm({ ...form, from_header: e.target.value })}
          />
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">Subject</label>
          <input
            className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background"
            value={form.subject}
            onChange={(e) => setForm({ ...form, subject: e.target.value })}
          />
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium mb-1">Email Body</label>
        <textarea
          className="w-full border border-border rounded-md px-3 py-2 text-sm bg-background min-h-[200px] font-mono"
          value={form.body}
          onChange={(e) => setForm({ ...form, body: e.target.value })}
        />
      </div>

      <button
        onClick={handleSubmit}
        disabled={submitting}
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-500 text-white hover:bg-violet-600 text-sm disabled:opacity-50"
      >
        {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        Classify & Ingest
      </button>

      {/* Result */}
      {result && (
        <div className={cn(
          'border rounded-lg p-4 text-sm',
          result.error ? 'border-red-300 bg-red-50' : 'border-emerald-300 bg-emerald-50',
        )}>
          {result.error ? (
            <p className="text-red-700">{result.error}</p>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span className="font-medium text-emerald-700">Signal classified successfully</span>
              </div>
              <div className="grid grid-cols-3 gap-3 mt-2">
                <div>
                  <span className="text-xs text-muted-foreground">Type</span>
                  <p className="font-medium">{result.signal_type?.replace(/_/g, ' ')}</p>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">Partner</span>
                  <p className="font-medium">{result.partner_name} ({result.partner_type})</p>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">Confidence</span>
                  <p className="font-medium">{Math.round(result.signal_confidence * 100)}%</p>
                </div>
              </div>
              <div>
                <span className="text-xs text-muted-foreground">Summary</span>
                <p>{result.signal_summary}</p>
              </div>
              {result.target_trm_types?.length > 0 && (
                <div>
                  <span className="text-xs text-muted-foreground">Routed to</span>
                  <p>{result.target_trm_types.join(', ')}</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function StatCard({ label, value }) {
  return (
    <div className="border border-border rounded-lg p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
    </div>
  );
}
