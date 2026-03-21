/**
 * Claude Skills Monitoring Dashboard
 *
 * Displays metrics for the hybrid TRM + Claude Skills architecture:
 * - Escalation rates (TRM handles ~95%, Skills ~5%)
 * - Skills decision outcomes and reward distributions
 * - RAG decision memory statistics
 * - Recent skills decisions with state/outcome details
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Alert,
  Badge,
  Button,
  Spinner,
} from '../../components/common';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import {
  Brain,
  Activity,
  Database,
  TrendingUp,
  AlertTriangle,
  CheckCircle,
  Clock,
  Sparkles,
  Target,
  RefreshCw,
  Zap,
  BarChart3,
  Search,
  Settings,
  Server,
  Cloud,
  Cpu,
} from 'lucide-react';
import { api } from '../../services/api';

// ============================================================================
// StatCard Component
// ============================================================================

const StatCard = ({ title, value, subtitle, icon: Icon, color = 'blue' }) => (
  <Card>
    <CardContent className="p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="text-2xl font-bold">{value}</p>
          {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
        </div>
        <div className={`p-3 rounded-lg bg-${color}-100 dark:bg-${color}-900/20`}>
          <Icon className={`h-6 w-6 text-${color}-600 dark:text-${color}-400`} />
        </div>
      </div>
    </CardContent>
  </Card>
);

// ============================================================================
// Colors
// ============================================================================

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];
const REWARD_COLORS = { good: '#10b981', moderate: '#f59e0b', poor: '#ef4444', pending: '#94a3b8' };

// ============================================================================
// Overview Tab
// ============================================================================

const OverviewTab = ({ stats }) => {
  if (!stats) return null;

  const escalationData = [
    { name: 'Agent Decisions', value: stats.total_trm_decisions, fill: '#3b82f6' },
    { name: 'Skills Escalations', value: stats.total_skill_decisions, fill: '#f59e0b' },
  ];

  const rewardData = stats.reward_distribution ? [
    { name: 'Good (>0.5)', value: stats.reward_distribution.good, fill: REWARD_COLORS.good },
    { name: 'Moderate', value: stats.reward_distribution.moderate, fill: REWARD_COLORS.moderate },
    { name: 'Poor (<=0)', value: stats.reward_distribution.poor, fill: REWARD_COLORS.poor },
    { name: 'Pending', value: stats.reward_distribution.pending_outcome, fill: REWARD_COLORS.pending },
  ].filter(d => d.value > 0) : [];

  return (
    <div className="space-y-6">
      {/* Top Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          title="Escalation Rate"
          value={`${stats.escalation_rate}%`}
          subtitle={`${stats.total_skill_decisions} of ${stats.total_trm_decisions + stats.total_skill_decisions} decisions`}
          icon={AlertTriangle}
          color="amber"
        />
        <StatCard
          title="Total AI Decisions"
          value={stats.total_trm_decisions.toLocaleString()}
          subtitle={`Last ${stats.period_days} days`}
          icon={Zap}
          color="blue"
        />
        <StatCard
          title="Skills Decisions"
          value={stats.total_skill_decisions.toLocaleString()}
          subtitle="Exception handling"
          icon={Sparkles}
          color="purple"
        />
        <StatCard
          title="Avg Skills Reward"
          value={stats.reward_distribution?.avg_reward?.toFixed(3) || '0'}
          subtitle={`${stats.reward_distribution?.good || 0} good outcomes`}
          icon={Target}
          color="green"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Decision Distribution Pie */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Decision Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={escalationData}
                  cx="50%" cy="50%"
                  innerRadius={60} outerRadius={100}
                  dataKey="value"
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(1)}%`}
                >
                  {escalationData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Pie>
                <RechartsTooltip />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Reward Distribution */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Skills Outcome Quality</CardTitle>
          </CardHeader>
          <CardContent>
            {rewardData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={rewardData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis />
                  <RechartsTooltip />
                  <Bar dataKey="value" name="Decisions">
                    {rewardData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[250px] text-muted-foreground">
                No skill decisions recorded yet
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Source Breakdown */}
      {Object.keys(stats.source_breakdown || {}).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Decision Sources</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(stats.source_breakdown).map(([source, count]) => (
                <div key={source} className="p-3 rounded-lg border">
                  <p className="text-xs text-muted-foreground">{source.replace(/_/g, ' ')}</p>
                  <p className="text-xl font-bold">{count}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

// ============================================================================
// Per-Agent Role Tab
// ============================================================================

const TypeBreakdownTab = ({ stats }) => {
  if (!stats?.type_breakdown) return null;

  const chartData = Object.entries(stats.type_breakdown).map(([trm, sources]) => {
    const row = { trm_type: trm.replace('_', ' ') };
    Object.entries(sources).forEach(([source, data]) => {
      row[source] = data.count;
      row[`${source}_reward`] = data.avg_reward;
    });
    return row;
  });

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Decisions by Agent Type and Source</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={350}>
            <BarChart data={chartData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis dataKey="trm_type" type="category" width={120} tick={{ fontSize: 11 }} />
              <RechartsTooltip />
              <Legend />
              <Bar dataKey="trm" name="Agent" fill="#3b82f6" stackId="a" />
              <Bar dataKey="skill_exception" name="Skills" fill="#f59e0b" stackId="a" />
              <Bar dataKey="engine" name="Engine" fill="#94a3b8" stackId="a" />
              <Bar dataKey="backfill" name="Backfill" fill="#e5e7eb" stackId="a" />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Detailed Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Detailed Metrics</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-2">Agent Role</th>
                  <th className="text-left p-2">Source</th>
                  <th className="text-right p-2">Count</th>
                  <th className="text-right p-2">Avg Confidence</th>
                  <th className="text-right p-2">Avg Reward</th>
                  <th className="text-right p-2">With Outcome</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(stats.type_breakdown).flatMap(([trm, sources]) =>
                  Object.entries(sources).map(([source, data]) => (
                    <tr key={`${trm}-${source}`} className="border-b hover:bg-muted/50">
                      <td className="p-2 font-mono text-xs">{trm}</td>
                      <td className="p-2">
                        <Badge variant={source === 'skill_exception' ? 'warning' : 'secondary'}>
                          {source}
                        </Badge>
                      </td>
                      <td className="p-2 text-right">{data.count}</td>
                      <td className="p-2 text-right">{data.avg_confidence}</td>
                      <td className="p-2 text-right">
                        <span className={data.avg_reward > 0.5 ? 'text-green-600' : data.avg_reward > 0 ? 'text-amber-600' : 'text-red-600'}>
                          {data.avg_reward}
                        </span>
                      </td>
                      <td className="p-2 text-right">{data.with_outcome}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// RAG Memory Tab
// ============================================================================

const RAGMemoryTab = ({ ragStats }) => {
  if (!ragStats) return null;

  return (
    <div className="space-y-6">
      {/* RAG Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          title="Total Embeddings"
          value={ragStats.total_embeddings.toLocaleString()}
          subtitle="Decision memory store"
          icon={Database}
          color="blue"
        />
        <StatCard
          title="Embedding Coverage"
          value={`${ragStats.embedding_coverage}%`}
          subtitle={`${ragStats.with_embedding_vector} with vectors`}
          icon={Search}
          color="purple"
        />
        <StatCard
          title="With Outcomes"
          value={ragStats.with_outcome}
          subtitle="Available for few-shot RAG"
          icon={CheckCircle}
          color="green"
        />
        <StatCard
          title="High-Reward Examples"
          value={ragStats.high_reward_examples}
          subtitle="Reward > 0.5 (best RAG examples)"
          icon={TrendingUp}
          color="emerald"
        />
      </div>

      {/* Per-Type Breakdown */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">RAG Memory by Agent Role</CardTitle>
        </CardHeader>
        <CardContent>
          {ragStats.by_type?.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={ragStats.by_type}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="trm_type" tick={{ fontSize: 11 }} />
                <YAxis />
                <RechartsTooltip />
                <Legend />
                <Bar dataKey="total" name="Total" fill="#3b82f6" />
                <Bar dataKey="with_outcome" name="With Outcome" fill="#10b981" />
                <Bar dataKey="high_reward" name="High Reward" fill="#f59e0b" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-[200px] text-muted-foreground">
              No decision memory data yet
            </div>
          )}
        </CardContent>
      </Card>

      {/* Architecture Info */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">RAG Decision Memory Architecture</CardTitle>
        </CardHeader>
        <CardContent className="text-sm space-y-2">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-3 rounded-lg border border-green-200 bg-green-50 dark:bg-green-900/10">
              <p className="font-medium text-green-800 dark:text-green-400">Cache Hit (&gt;0.95)</p>
              <p className="text-xs text-muted-foreground mt-1">Near-exact match. Return directly, skip LLM call entirely.</p>
            </div>
            <div className="p-3 rounded-lg border border-amber-200 bg-amber-50 dark:bg-amber-900/10">
              <p className="font-medium text-amber-800 dark:text-amber-400">Few-Shot Hit (&gt;0.70)</p>
              <p className="text-xs text-muted-foreground mt-1">Good match. Inject as examples, use cheaper Haiku model.</p>
            </div>
            <div className="p-3 rounded-lg border border-blue-200 bg-blue-50 dark:bg-blue-900/10">
              <p className="font-medium text-blue-800 dark:text-blue-400">No Match (&lt;0.70)</p>
              <p className="text-xs text-muted-foreground mt-1">Novel situation. Full skill prompt to Sonnet model.</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// Recent Decisions Tab
// ============================================================================

const RecentDecisionsTab = ({ stats }) => {
  const decisions = stats?.recent_decisions || [];

  if (decisions.length === 0) {
    return (
      <Alert>
        <Clock className="h-4 w-4" />
        <span>No recent decisions found. Skills decisions will appear here once the AI agent pipeline processes exceptions.</span>
      </Alert>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Recent Decisions (Last 20)</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className="text-left p-2">Time</th>
                <th className="text-left p-2">Agent Role</th>
                <th className="text-left p-2">Source</th>
                <th className="text-left p-2">Site</th>
                <th className="text-right p-2">Confidence</th>
                <th className="text-right p-2">Reward</th>
                <th className="text-left p-2">State Summary</th>
              </tr>
            </thead>
            <tbody>
              {decisions.map((d) => (
                <tr key={d.id} className="border-b hover:bg-muted/50">
                  <td className="p-2 text-xs whitespace-nowrap">
                    {d.created_at ? new Date(d.created_at).toLocaleString() : '-'}
                  </td>
                  <td className="p-2 font-mono text-xs">{d.trm_type}</td>
                  <td className="p-2">
                    <Badge variant={
                      d.decision_source === 'skill_exception' ? 'warning' :
                      d.decision_source === 'trm' ? 'default' : 'secondary'
                    }>
                      {d.decision_source}
                    </Badge>
                  </td>
                  <td className="p-2 text-xs">{d.site_key || '-'}</td>
                  <td className="p-2 text-right">{d.confidence}</td>
                  <td className="p-2 text-right">
                    {d.reward !== null ? (
                      <span className={
                        d.reward > 0.5 ? 'text-green-600 font-medium' :
                        d.reward > 0 ? 'text-amber-600' : 'text-red-600'
                      }>
                        {d.reward}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">pending</span>
                    )}
                  </td>
                  <td className="p-2 text-xs max-w-[300px] truncate">{d.state_summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
};

// ============================================================================
// LLM Settings Tab
// ============================================================================

const PROVIDER_OPTIONS = [
  {
    value: 'auto',
    label: 'Auto',
    description: 'Use Claude API if CLAUDE_API_KEY is set, otherwise fall back to vLLM.',
    icon: Cpu,
    color: 'text-gray-600',
  },
  {
    value: 'claude',
    label: 'Claude API',
    description: 'Always use Anthropic Claude (claude-sonnet-4-6). Best quality. Requires CLAUDE_API_KEY.',
    icon: Cloud,
    color: 'text-purple-600',
  },
  {
    value: 'vllm',
    label: 'vLLM (Local)',
    description: 'Always use local vLLM on LLM_API_BASE. Free but limited by GPU context window.',
    icon: Server,
    color: 'text-blue-600',
  },
];

const ProviderCard = ({ value, selected, onSelect }) => {
  const opt = PROVIDER_OPTIONS.find(o => o.value === value) || PROVIDER_OPTIONS[0];
  const Icon = opt.icon;
  return (
    <div
      onClick={() => onSelect(value)}
      className={`cursor-pointer rounded-lg border-2 p-4 transition-all ${
        selected === value
          ? 'border-primary bg-primary/5'
          : 'border-border hover:border-primary/50'
      }`}
    >
      <div className="flex items-center gap-3 mb-2">
        <Icon className={`h-5 w-5 ${opt.color}`} />
        <span className="font-semibold text-sm">{opt.label}</span>
        {selected === value && (
          <Badge variant="default" className="ml-auto text-xs">Active</Badge>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{opt.description}</p>
    </div>
  );
};

const LLMSettingsTab = () => {
  const [settings, setSettings] = useState({ briefing_provider: 'auto', skills_provider: 'auto' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get('/config/llm')
      .then(r => setSettings(r.data))
      .catch(() => {/* use defaults */})
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const r = await api.put('/config/llm', settings);
      setSettings(r.data);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="p-8 text-center text-muted-foreground">Loading settings…</div>;

  return (
    <div className="space-y-6 pt-4">
      <Alert>
        <Settings className="h-4 w-4" />
        <div>
          <strong>Changes take effect immediately</strong> — no restart required.
          Settings are written to <code>data/llm_settings.json</code> and read on each request.
        </div>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-purple-500" />
            Executive Briefing Provider
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Weekly/monthly briefings. Low-frequency, quality-critical.
            Recommended: Claude API (~$0.05/briefing).
          </p>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {PROVIDER_OPTIONS.map(opt => (
              <ProviderCard
                key={opt.value}
                value={opt.value}
                selected={settings.briefing_provider}
                onSelect={v => setSettings(s => ({ ...s, briefing_provider: v }))}
              />
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Brain className="h-4 w-4 text-blue-500" />
            Skills Exception Handler Provider
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Exception handling (~5% of decisions). Higher volume, latency-tolerant.
            Recommended: vLLM for air-gapped or cost-sensitive deployments.
          </p>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {PROVIDER_OPTIONS.map(opt => (
              <ProviderCard
                key={opt.value}
                value={opt.value}
                selected={settings.skills_provider}
                onSelect={v => setSettings(s => ({ ...s, skills_provider: v }))}
              />
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? <Spinner className="h-4 w-4 mr-2" /> : <Settings className="h-4 w-4 mr-2" />}
          {saving ? 'Saving…' : 'Save Settings'}
        </Button>
        {saved && <span className="text-sm text-green-600 flex items-center gap-1"><CheckCircle className="h-4 w-4" /> Saved — active immediately</span>}
        {error && <span className="text-sm text-red-600">{error}</span>}
      </div>
    </div>
  );
};

// ============================================================================
// Main Dashboard
// ============================================================================

const SkillsDashboard = () => {
  const [stats, setStats] = useState(null);
  const [ragStats, setRagStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsRes, ragRes] = await Promise.all([
        api.get('/skills-monitoring/stats?days=30'),
        api.get('/skills-monitoring/rag-stats?days=30'),
      ]);
      setStats(statsRes.data);
      setRagStats(ragRes.data);
    } catch (err) {
      console.error('Failed to fetch skills stats:', err);
      setError(err.message || 'Failed to load skills monitoring data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-purple-600" />
            Exception Handler
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            LLM exception handling — execution agents handle ~95% of decisions, exceptions escalate to LLM reasoning
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchData}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <span>{error}</span>
        </Alert>
      )}

      {/* Architecture Banner */}
      <Card className="border-purple-200 bg-purple-50/50 dark:bg-purple-900/10">
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            <Brain className="h-5 w-5 text-purple-600 mt-0.5" />
            <div className="text-sm">
              <p className="font-medium">LeCun JEPA Hybrid Architecture</p>
              <p className="text-muted-foreground">
                Execution agents (TRMs (Actor, &lt;10ms) &rarr; Conformal Prediction routing &rarr; Claude Skills (Configurator, ~5% exceptions) &rarr; Decision recorded for TRM retraininglt;10ms) TRMs (Actor, &lt;10ms) &rarr; Conformal Prediction routing &rarr; Claude Skills (Configurator, ~5% exceptions) &rarr; Decision recorded for TRM retrainingrarr; Confidence routing TRMs (Actor, &lt;10ms) &rarr; Conformal Prediction routing &rarr; Claude Skills (Configurator, ~5% exceptions) &rarr; Decision recorded for TRM retrainingrarr; Claude Skills (~5% exceptions) TRMs (Actor, &lt;10ms) &rarr; Conformal Prediction routing &rarr; Claude Skills (Configurator, ~5% exceptions) &rarr; Decision recorded for TRM retrainingrarr; Decision recorded for agent retraining
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview">
            <Activity className="h-4 w-4 mr-1" /> Overview
          </TabsTrigger>
          <TabsTrigger value="types">
            <BarChart3 className="h-4 w-4 mr-1" /> By Agent Role
          </TabsTrigger>
          <TabsTrigger value="rag">
            <Database className="h-4 w-4 mr-1" /> RAG Memory
          </TabsTrigger>
          <TabsTrigger value="recent">
            <Clock className="h-4 w-4 mr-1" /> Recent Decisions
          </TabsTrigger>
          <TabsTrigger value="llm-settings">
            <Settings className="h-4 w-4 mr-1" /> LLM Settings
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab stats={stats} />
        </TabsContent>
        <TabsContent value="types">
          <TypeBreakdownTab stats={stats} />
        </TabsContent>
        <TabsContent value="rag">
          <RAGMemoryTab ragStats={ragStats} />
        </TabsContent>
        <TabsContent value="recent">
          <RecentDecisionsTab stats={stats} />
        </TabsContent>
        <TabsContent value="llm-settings">
          <LLMSettingsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default SkillsDashboard;
