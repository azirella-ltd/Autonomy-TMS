/**
 * ExperientialKnowledgeDashboard — Manage structured behavioral knowledge from override patterns.
 *
 * Based on Alicke's "The Planner Was the System" — experiential knowledge as
 * Powell Belief State (Bt) that feeds into TRM state augmentation, reward shaping,
 * conditional CDT, and simulation modifiers.
 *
 * Tabs:
 *   1. Knowledge Library: ACTIVE entities with RL impact columns
 *   2. Candidates: Awaiting planner confirmation
 *   3. Validation Queue: STALE entities needing re-validation
 *   4. Contradictions: Conflicting entities needing resolution
 *   5. Analytics: Pattern type distribution, GENUINE vs COMPENSATING, conversion rate
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  BrainCircuit, CheckCircle2, XCircle, AlertTriangle, Clock,
  RefreshCw, Plus, Eye, Shield, Zap, TrendingUp,
  ChevronRight, Loader2, Search, Filter,
} from 'lucide-react';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import { cn } from '@azirella-ltd/autonomy-frontend';

// ── Status & Type Colors ────────────────────────────────────────────────────

const STATUS_COLORS = {
  ACTIVE: 'bg-emerald-500/10 text-emerald-700 border-emerald-200',
  CANDIDATE: 'bg-blue-500/10 text-blue-700 border-blue-200',
  STALE: 'bg-amber-500/10 text-amber-700 border-amber-200',
  CONTRADICTED: 'bg-red-500/10 text-red-700 border-red-200',
  RETIRED: 'bg-gray-500/10 text-gray-500 border-gray-200',
  SUPERSEDED: 'bg-slate-500/10 text-slate-500 border-slate-200',
};

const KNOWLEDGE_TYPE_COLORS = {
  GENUINE: 'bg-emerald-500/10 text-emerald-700',
  COMPENSATING: 'bg-amber-500/10 text-amber-700',
};

const PATTERN_ICONS = {
  lead_time_variation: Clock,
  demand_seasonality: TrendingUp,
  capacity_constraint: Zap,
  quality_degradation: AlertTriangle,
  forecast_bias: Eye,
  supplier_behavior: Shield,
  default: BrainCircuit,
};

// ── Badge Components ────────────────────────────────────────────────────────

const StatusBadge = ({ status }) => (
  <span className={cn('inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full border', STATUS_COLORS[status] || STATUS_COLORS.RETIRED)}>
    {status}
  </span>
);

const KnowledgeTypeBadge = ({ type }) => {
  if (!type) return <span className="text-xs text-muted-foreground italic">Unclassified</span>;
  return (
    <span className={cn('inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full', KNOWLEDGE_TYPE_COLORS[type])}>
      {type}
    </span>
  );
};

const ConfidenceBar = ({ value }) => (
  <div className="flex items-center gap-2">
    <div className="h-1.5 w-16 bg-muted rounded-full overflow-hidden">
      <div className="h-full bg-primary rounded-full" style={{ width: `${Math.round(value * 100)}%` }} />
    </div>
    <span className="text-xs text-muted-foreground">{Math.round(value * 100)}%</span>
  </div>
);

// ── Entity Row ──────────────────────────────────────────────────────────────

const EntityRow = ({ entity, onAction, expanded, onToggle }) => {
  const PatternIcon = PATTERN_ICONS[entity.pattern_type] || PATTERN_ICONS.default;
  const effect = entity.effect || {};

  return (
    <div className="border-b last:border-0">
      <div
        className="flex items-center gap-3 px-4 py-3 hover:bg-muted/50 cursor-pointer"
        onClick={onToggle}
      >
        <ChevronRight className={cn('h-4 w-4 transition-transform text-muted-foreground', expanded && 'rotate-90')} />
        <PatternIcon className="h-4 w-4 text-muted-foreground shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{entity.summary}</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {entity.entity_type} &middot; {entity.pattern_type.replace(/_/g, ' ')}
            {effect.multiplier && <> &middot; x{effect.multiplier}</>}
          </p>
        </div>
        <KnowledgeTypeBadge type={entity.knowledge_type} />
        <ConfidenceBar value={entity.confidence} />
        <StatusBadge status={entity.status} />
      </div>

      {expanded && (
        <div className="px-4 pb-3 ml-11 space-y-2 text-sm">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">Conditions</p>
              <pre className="text-xs bg-muted/50 p-2 rounded">{JSON.stringify(entity.conditions, null, 2)}</pre>
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">Effect</p>
              <pre className="text-xs bg-muted/50 p-2 rounded">{JSON.stringify(entity.effect, null, 2)}</pre>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-muted-foreground">TRM Types</p>
              <p className="text-xs">{(entity.trm_types_affected || []).join(', ') || 'None'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">State Features</p>
              <p className="text-xs font-mono">{(entity.state_feature_names || []).join(', ') || 'None'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">CDT Multiplier</p>
              <p className="text-xs">x{entity.cdt_uncertainty_multiplier || 1.0}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <span className="text-xs text-muted-foreground">
              {(entity.evidence || []).length} evidence items &middot;
              Source: {entity.source_type?.replace(/_/g, ' ')} &middot;
              Last validated: {entity.last_validated_at ? new Date(entity.last_validated_at).toLocaleDateString() : 'Never'}
            </span>
          </div>
          {onAction && (
            <div className="flex gap-2 mt-2">
              {entity.status === 'CANDIDATE' && (
                <>
                  <button onClick={() => onAction('confirm', entity)} className="text-xs px-3 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700">Confirm</button>
                  <button onClick={() => onAction('retire', entity)} className="text-xs px-3 py-1 rounded bg-gray-200 hover:bg-gray-300">Dismiss</button>
                </>
              )}
              {entity.status === 'STALE' && (
                <>
                  <button onClick={() => onAction('validate', entity)} className="text-xs px-3 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700">Still Valid</button>
                  <button onClick={() => onAction('retire', entity)} className="text-xs px-3 py-1 rounded bg-gray-200 hover:bg-gray-300">Retire</button>
                </>
              )}
              {entity.status === 'ACTIVE' && !entity.knowledge_type && (
                <>
                  <button onClick={() => onAction('classify_genuine', entity)} className="text-xs px-3 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700">Mark Genuine</button>
                  <button onClick={() => onAction('classify_compensating', entity)} className="text-xs px-3 py-1 rounded bg-amber-600 text-white hover:bg-amber-700">Mark Compensating</button>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ── Main Dashboard ──────────────────────────────────────────────────────────

export default function ExperientialKnowledgeDashboard() {
  const { activeConfig } = useActiveConfig();
  const configId = activeConfig?.id;

  const [activeTab, setActiveTab] = useState('library');
  const [entities, setEntities] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [detecting, setDetecting] = useState(false);

  const tabs = [
    { id: 'library', label: 'Knowledge Library', icon: BrainCircuit },
    { id: 'candidates', label: 'Candidates', icon: Plus },
    { id: 'stale', label: 'Validation Queue', icon: Clock },
    { id: 'contradictions', label: 'Contradictions', icon: AlertTriangle },
    { id: 'analytics', label: 'Analytics', icon: TrendingUp },
  ];

  const fetchEntities = useCallback(async () => {
    setLoading(true);
    try {
      const statusMap = {
        library: 'ACTIVE',
        candidates: null,  // uses /candidates endpoint
        stale: null,       // uses /stale endpoint
        contradictions: null,
      };

      let url;
      if (activeTab === 'candidates') {
        url = `/experiential-knowledge/candidates${configId ? `?config_id=${configId}` : ''}`;
      } else if (activeTab === 'stale') {
        url = `/experiential-knowledge/stale${configId ? `?config_id=${configId}` : ''}`;
      } else if (activeTab === 'contradictions') {
        url = `/experiential-knowledge/contradictions${configId ? `?config_id=${configId}` : ''}`;
      } else {
        const params = new URLSearchParams();
        if (configId) params.set('config_id', configId);
        if (activeTab === 'library') params.set('status', 'ACTIVE');
        url = `/experiential-knowledge/?${params.toString()}`;
      }

      const { data } = await api.get(url);
      setEntities(data.items || []);
    } catch (err) {
      console.error('Failed to fetch EK entities:', err);
      setEntities([]);
    } finally {
      setLoading(false);
    }
  }, [activeTab, configId]);

  const fetchStats = useCallback(async () => {
    try {
      const { data } = await api.get(`/experiential-knowledge/stats${configId ? `?config_id=${configId}` : ''}`);
      setStats(data);
    } catch (err) {
      console.error('Failed to fetch EK stats:', err);
    }
  }, [configId]);

  useEffect(() => { fetchEntities(); fetchStats(); }, [fetchEntities, fetchStats]);

  const handleAction = async (action, entity) => {
    try {
      if (action === 'confirm') {
        await api.post(`/experiential-knowledge/${entity.id}/confirm`, { knowledge_type: 'GENUINE' });
      } else if (action === 'validate') {
        await api.put(`/experiential-knowledge/${entity.id}/validate`);
      } else if (action === 'retire') {
        await api.put(`/experiential-knowledge/${entity.id}/retire`, { reason: 'Dismissed by admin' });
      } else if (action === 'classify_genuine') {
        await api.put(`/experiential-knowledge/${entity.id}/classify`, { knowledge_type: 'GENUINE', rationale: 'Classified by admin' });
      } else if (action === 'classify_compensating') {
        await api.put(`/experiential-knowledge/${entity.id}/classify`, { knowledge_type: 'COMPENSATING', rationale: 'Classified by admin as workaround' });
      }
      fetchEntities();
      fetchStats();
    } catch (err) {
      console.error(`Action ${action} failed:`, err);
    }
  };

  const handleDetectNow = async () => {
    setDetecting(true);
    try {
      const { data } = await api.post(`/experiential-knowledge/detect-now${configId ? `?config_id=${configId}` : ''}`);
      alert(`Detection: ${data.detection?.created || 0} new candidates, ${data.lifecycle?.stale || 0} stale`);
      fetchEntities();
      fetchStats();
    } catch (err) {
      console.error('Detection failed:', err);
    } finally {
      setDetecting(false);
    }
  };

  const candidateCount = stats?.by_status?.CANDIDATE || 0;
  const staleCount = stats?.by_status?.STALE || 0;
  const contradictedCount = stats?.by_status?.CONTRADICTED || 0;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BrainCircuit className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-lg font-semibold">Experiential Knowledge</h1>
            <p className="text-xs text-muted-foreground">
              Planner behavioral patterns — Alicke's "The Planner Was the System"
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleDetectNow}
            disabled={detecting}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {detecting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
            Detect Patterns
          </button>
          <button
            onClick={() => { fetchEntities(); fetchStats(); }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded border hover:bg-muted"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      {stats && (
        <div className="grid grid-cols-5 gap-3">
          {[
            { label: 'Active', value: stats.by_status?.ACTIVE || 0, color: 'text-emerald-600' },
            { label: 'Candidates', value: candidateCount, color: 'text-blue-600' },
            { label: 'Stale', value: staleCount, color: 'text-amber-600' },
            { label: 'Contradicted', value: contradictedCount, color: 'text-red-600' },
            { label: 'Total', value: stats.total || 0, color: 'text-foreground' },
          ].map(({ label, value, color }) => (
            <div key={label} className="border rounded-lg p-3">
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className={cn('text-2xl font-bold', color)}>{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="border-b flex gap-0">
        {tabs.map(({ id, label, icon: Icon }) => {
          const badge = id === 'candidates' ? candidateCount : id === 'stale' ? staleCount : id === 'contradictions' ? contradictedCount : 0;
          return (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={cn(
                'flex items-center gap-1.5 px-4 py-2 text-sm border-b-2 -mb-px transition-colors',
                activeTab === id
                  ? 'border-primary text-primary font-medium'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
              {badge > 0 && (
                <span className="ml-1 px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-primary text-primary-foreground">{badge}</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div className="border rounded-lg">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : activeTab === 'analytics' ? (
          <AnalyticsTab stats={stats} />
        ) : entities.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground text-sm">
            No {activeTab === 'library' ? 'active knowledge' : activeTab} entities found.
            {activeTab === 'candidates' && ' Run "Detect Patterns" to scan override history.'}
          </div>
        ) : (
          entities.map(entity => (
            <EntityRow
              key={entity.id}
              entity={entity}
              expanded={expandedId === entity.id}
              onToggle={() => setExpandedId(expandedId === entity.id ? null : entity.id)}
              onAction={activeTab !== 'analytics' ? handleAction : null}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ── Analytics Tab ───────────────────────────────────────────────────────────

function AnalyticsTab({ stats }) {
  if (!stats) return <div className="p-8 text-center text-muted-foreground text-sm">Loading analytics...</div>;

  const byPattern = stats.by_pattern_type || {};
  const byType = stats.by_knowledge_type || {};
  const genuineCount = byType.GENUINE || 0;
  const compensatingCount = byType.COMPENSATING || 0;
  const totalClassified = genuineCount + compensatingCount;

  return (
    <div className="p-4 space-y-6">
      {/* GENUINE vs COMPENSATING */}
      <div>
        <h3 className="text-sm font-medium mb-3">Knowledge Type Distribution</h3>
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <div className="h-4 rounded-full overflow-hidden bg-muted flex">
              {totalClassified > 0 && (
                <>
                  <div className="h-full bg-emerald-500" style={{ width: `${(genuineCount / totalClassified) * 100}%` }} />
                  <div className="h-full bg-amber-500" style={{ width: `${(compensatingCount / totalClassified) * 100}%` }} />
                </>
              )}
            </div>
          </div>
          <div className="flex gap-4 text-xs">
            <span className="flex items-center gap-1.5">
              <div className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
              Genuine ({genuineCount})
            </span>
            <span className="flex items-center gap-1.5">
              <div className="h-2.5 w-2.5 rounded-full bg-amber-500" />
              Compensating ({compensatingCount})
            </span>
          </div>
        </div>
      </div>

      {/* Pattern Type Breakdown */}
      <div>
        <h3 className="text-sm font-medium mb-3">Active Knowledge by Pattern Type</h3>
        {Object.keys(byPattern).length === 0 ? (
          <p className="text-xs text-muted-foreground">No active entities yet.</p>
        ) : (
          <div className="space-y-2">
            {Object.entries(byPattern).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
              <div key={type} className="flex items-center gap-3">
                <span className="text-xs w-40 truncate text-muted-foreground">{type.replace(/_/g, ' ')}</span>
                <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                  <div className="h-full bg-primary/60 rounded-full" style={{ width: `${(count / Math.max(...Object.values(byPattern))) * 100}%` }} />
                </div>
                <span className="text-xs font-medium w-6 text-right">{count}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Status Summary */}
      <div>
        <h3 className="text-sm font-medium mb-3">Status Overview</h3>
        <div className="grid grid-cols-3 gap-3">
          {Object.entries(stats.by_status || {}).map(([status, count]) => (
            <div key={status} className="border rounded-lg p-3 text-center">
              <StatusBadge status={status} />
              <p className="text-xl font-bold mt-1">{count}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
