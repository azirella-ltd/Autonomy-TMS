/**
 * RLHF Dashboard
 *
 * Phase 4 dashboard for visualizing Reinforcement Learning from Human Feedback.
 * Tracks feedback actions (accepted/modified/rejected), override rate trends,
 * top override reasons, and training data statistics.
 * Uses demo data fallback when API is unavailable.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, ResponsiveContainer, Legend, Cell,
} from 'recharts';
import {
  Card, CardContent, CardHeader, CardTitle,
  Alert, Badge, Button,
} from '../../components/common';
import {
  MessageSquare, TrendingDown, RefreshCw, ChevronRight,
  Database, CheckCircle, XCircle, Edit3, ThumbsUp, Clock,
} from 'lucide-react';
import { cn } from '@azirella-ltd/autonomy-frontend';
import { api } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';

// ============================================================================
// Demo Data Generation
// ============================================================================

const ACTION_COLORS = {
  accepted: '#10b981',
  modified: '#f59e0b',
  rejected: '#ef4444',
};

function generateDemoData() {
  // Feedback action distribution by agent type
  const agentTypes = ['ATP', 'PO Creation', 'Rebalancing', 'MO Execution', 'Forecast Adj', 'Safety Stock'];
  const feedbackByAgent = agentTypes.map(agent => {
    const accepted = Math.round(50 + Math.random() * 35);
    const modified = Math.round(10 + Math.random() * 20);
    const rejected = Math.round(100 - accepted - modified);
    return { agent, accepted, modified, rejected: Math.max(0, rejected) };
  });

  // Override rate trend (12 weeks, showing decreasing trend as agents improve)
  const overrideTrend = Array.from({ length: 12 }, (_, i) => ({
    week: `W${i + 1}`,
    override_rate: Math.round((35 - i * 1.8 + (Math.random() - 0.5) * 6) * 10) / 10,
    modification_rate: Math.round((18 - i * 0.9 + (Math.random() - 0.5) * 4) * 10) / 10,
    rejection_rate: Math.round((12 - i * 0.7 + (Math.random() - 0.5) * 3) * 10) / 10,
  }));

  // Top override reasons
  const overrideReasons = [
    { reason: 'Safety stock too aggressive', count: 142, agent: 'Safety Stock', trend: 'decreasing' },
    { reason: 'Lead time estimate inaccurate', count: 98, agent: 'PO Creation', trend: 'stable' },
    { reason: 'Demand signal not captured', count: 87, agent: 'Forecast Adj', trend: 'decreasing' },
    { reason: 'Priority allocation mismatch', count: 72, agent: 'ATP', trend: 'increasing' },
    { reason: 'Maintenance window conflict', count: 56, agent: 'MO Execution', trend: 'stable' },
    { reason: 'Supplier capacity not updated', count: 43, agent: 'PO Creation', trend: 'decreasing' },
    { reason: 'Cross-dock opportunity missed', count: 38, agent: 'Rebalancing', trend: 'stable' },
    { reason: 'Quality hold release premature', count: 29, agent: 'Quality', trend: 'decreasing' },
  ];

  // Training stats
  const trainingStats = {
    total_examples: 12847,
    accepted_examples: 8942,
    modified_examples: 2631,
    rejected_examples: 1274,
    latest_batch_size: 384,
    latest_batch_date: '2026-02-24',
    quality_score: 87.3,
    avg_reward_signal: 0.72,
    next_training_eta: '2h 15m',
    model_version: 'v3.2.1',
  };

  return {
    feedback_by_agent: feedbackByAgent,
    override_trend: overrideTrend,
    override_reasons: overrideReasons,
    training_stats: trainingStats,
  };
}

// ============================================================================
// Sub-Components
// ============================================================================

const StatCard = ({ title, value, subtitle, icon: Icon, color = 'blue' }) => (
  <Card>
    <CardContent className="p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="text-2xl font-bold">{value}</p>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        <div className={`p-3 rounded-lg bg-${color}-100 dark:bg-${color}-900/20`}>
          <Icon className={`h-6 w-6 text-${color}-600 dark:text-${color}-400`} />
        </div>
      </div>
    </CardContent>
  </Card>
);

const TrendBadge = ({ trend }) => {
  const config = {
    increasing: { label: 'Increasing', variant: 'destructive' },
    decreasing: { label: 'Decreasing', variant: 'success' },
    stable: { label: 'Stable', variant: 'secondary' },
  };
  const { label, variant } = config[trend] || config.stable;
  return <Badge variant={variant} className="text-xs">{label}</Badge>;
};

// ============================================================================
// Main Component
// ============================================================================

const RLHFDashboard = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get('/rlhf/dashboard');
      setData(response.data);
    } catch (err) {
      console.warn('RLHF dashboard endpoint not available, using demo data:', err.message);
      setData(generateDemoData());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex justify-center p-12">
          <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
        </div>
      </div>
    );
  }

  const { feedback_by_agent, override_trend, override_reasons, training_stats } = data || {};

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Demo data banner */}
      <div className="mb-4 px-4 py-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-center gap-2">
        <span className="font-semibold">Demo Data</span>
        <span>This dashboard shows illustrative data. Override feedback will populate from real planner decisions.</span>
      </div>

      {/* Breadcrumbs */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
        <Link to="/" className="hover:text-foreground">Home</Link>
        <ChevronRight className="h-4 w-4" />
        <Link to="/admin?section=training" className="hover:text-foreground">AI & Agents</Link>
        <ChevronRight className="h-4 w-4" />
        <span className="text-foreground">RLHF Feedback</span>
      </nav>

      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-3">
          <MessageSquare className="h-7 w-7 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">RLHF Feedback Dashboard</h1>
            <p className="text-sm text-muted-foreground">
              Human override patterns, feedback distribution, and training data quality
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={fetchData}>
          <RefreshCw className="h-4 w-4 mr-1" /> Refresh
        </Button>
      </div>

      {error && (
        <Alert variant="warning" className="mb-4">
          {error}
        </Alert>
      )}

      {/* Training Data Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          title="Total Training Examples"
          value={training_stats?.total_examples?.toLocaleString() || '0'}
          subtitle={`${training_stats?.accepted_examples?.toLocaleString() || 0} accepted`}
          icon={Database}
          color="blue"
        />
        <StatCard
          title="Latest Batch"
          value={training_stats?.latest_batch_size || 0}
          subtitle={training_stats?.latest_batch_date || '--'}
          icon={Clock}
          color="purple"
        />
        <StatCard
          title="Quality Score"
          value={`${training_stats?.quality_score || 0}%`}
          subtitle={`Reward signal: ${training_stats?.avg_reward_signal || 0}`}
          icon={ThumbsUp}
          color="green"
        />
        <StatCard
          title="Model Version"
          value={training_stats?.model_version || '--'}
          subtitle={`Next training: ${training_stats?.next_training_eta || '--'}`}
          icon={CheckCircle}
          color="amber"
        />
      </div>

      {/* Feedback Action Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <MessageSquare className="h-4 w-4" />
              Feedback Actions by Agent
            </CardTitle>
          </CardHeader>
          <CardContent>
            {feedback_by_agent && feedback_by_agent.length > 0 ? (
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={feedback_by_agent} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis dataKey="agent" type="category" width={100} tick={{ fontSize: 10 }} />
                  <RTooltip />
                  <Legend />
                  <Bar dataKey="accepted" name="Accepted" stackId="a" fill={ACTION_COLORS.accepted} />
                  <Bar dataKey="modified" name="Modified" stackId="a" fill={ACTION_COLORS.modified} />
                  <Bar dataKey="rejected" name="Rejected" stackId="a" fill={ACTION_COLORS.rejected} radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-muted-foreground text-center py-12">No feedback data available</p>
            )}
          </CardContent>
        </Card>

        {/* Override Rate Trend */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingDown className="h-4 w-4" />
              Override Rate Trend
            </CardTitle>
          </CardHeader>
          <CardContent>
            {override_trend && override_trend.length > 0 ? (
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={override_trend}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="week" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} unit="%" />
                  <RTooltip />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="override_rate"
                    name="Total Override %"
                    stroke="#3b82f6"
                    strokeWidth={2.5}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="modification_rate"
                    name="Modification %"
                    stroke="#f59e0b"
                    strokeWidth={1.5}
                    dot={false}
                    strokeDasharray="5 5"
                  />
                  <Line
                    type="monotone"
                    dataKey="rejection_rate"
                    name="Rejection %"
                    stroke="#ef4444"
                    strokeWidth={1.5}
                    dot={false}
                    strokeDasharray="3 3"
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-muted-foreground text-center py-12">No trend data available</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Top Override Reasons */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Edit3 className="h-4 w-4" />
            Top Override Reasons
            <Badge variant="outline" className="ml-auto">{override_reasons?.length || 0} reasons tracked</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {override_reasons && override_reasons.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="pb-2 pr-4 font-medium w-8">#</th>
                    <th className="pb-2 pr-4 font-medium">Reason</th>
                    <th className="pb-2 pr-4 font-medium">Agent</th>
                    <th className="pb-2 pr-4 font-medium text-right">Count</th>
                    <th className="pb-2 pr-4 font-medium">Frequency</th>
                    <th className="pb-2 font-medium text-center">Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {override_reasons.map((row, idx) => {
                    const maxCount = override_reasons[0]?.count || 1;
                    const pct = Math.round((row.count / maxCount) * 100);
                    return (
                      <tr key={idx} className="border-b last:border-0 hover:bg-muted/50">
                        <td className="py-2.5 pr-4 text-muted-foreground font-mono">{idx + 1}</td>
                        <td className="py-2.5 pr-4 font-medium">{row.reason}</td>
                        <td className="py-2.5 pr-4">
                          <Badge variant="outline" className="text-xs">{row.agent}</Badge>
                        </td>
                        <td className="py-2.5 pr-4 text-right font-mono">{row.count}</td>
                        <td className="py-2.5 pr-4 w-40">
                          <div className="h-2 bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full bg-blue-500"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </td>
                        <td className="py-2.5 text-center">
                          <TrendBadge trend={row.trend} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-muted-foreground text-center py-12">No override reasons recorded</p>
          )}
        </CardContent>
      </Card>

      {/* Training Data Summary */}
      <Card className="mt-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Training Data Composition</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-6">
            {[
              { label: 'Accepted', count: training_stats?.accepted_examples, icon: CheckCircle, color: 'green' },
              { label: 'Modified', count: training_stats?.modified_examples, icon: Edit3, color: 'amber' },
              { label: 'Rejected', count: training_stats?.rejected_examples, icon: XCircle, color: 'red' },
            ].map(({ label, count, icon: Icon, color }) => {
              const total = training_stats?.total_examples || 1;
              const pct = Math.round(((count || 0) / total) * 100);
              return (
                <div key={label} className="text-center space-y-2">
                  <Icon className={`h-8 w-8 mx-auto text-${color}-500`} />
                  <p className="text-2xl font-bold">{(count || 0).toLocaleString()}</p>
                  <p className="text-sm text-muted-foreground">{label} ({pct}%)</p>
                  <div className="h-2 bg-muted rounded-full overflow-hidden mx-auto w-3/4">
                    <div
                      className={`h-full rounded-full bg-${color}-500`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default RLHFDashboard;
