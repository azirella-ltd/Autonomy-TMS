/**
 * Agent Benchmark Dashboard
 *
 * Phase 4 dashboard for comparing AI agent performance across strategies.
 * Shows performance trends, metric comparisons, mode distribution, and
 * summary statistics. Uses demo data fallback when API is unavailable.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, ResponsiveContainer, Legend,
} from 'recharts';
import {
  Card, CardContent, CardHeader, CardTitle,
  Alert, Badge, Button,
  Tabs, TabsList, TabsTrigger, TabsContent,
} from '../../components/common';
import {
  Bot, TrendingUp, TrendingDown, RefreshCw, ChevronRight,
  Award, BarChart3, PieChart as PieChartIcon, Minus,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';
import { api } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';

// ============================================================================
// Demo Data Generation
// ============================================================================

const AGENT_TYPES = ['naive', 'conservative', 'reactive', 'ml_forecast', 'optimizer', 'llm'];
const AGENT_LABELS = {
  naive: 'Naive (Baseline)',
  conservative: 'Conservative',
  reactive: 'Reactive',
  ml_forecast: 'ML Forecast',
  optimizer: 'Optimizer',
  llm: 'LLM Multi-Agent',
};
const COLORS = ['#94a3b8', '#f59e0b', '#3b82f6', '#8b5cf6', '#10b981', '#06b6d4'];
const MODE_COLORS = { manual: '#94a3b8', copilot: '#3b82f6', autonomous: '#10b981' };

function generateDemoData() {
  // Performance trend (12 weeks)
  const trendData = Array.from({ length: 12 }, (_, i) => {
    const week = `W${i + 1}`;
    const entry = { week };
    AGENT_TYPES.forEach((agent, idx) => {
      const base = [0, 8, 12, 22, 28, 32][idx];
      const noise = (Math.random() - 0.5) * 6;
      entry[agent] = Math.round(Math.max(-5, Math.min(50, base + (i * 0.8) + noise)));
    });
    return entry;
  });

  // Comparison table
  const comparisonData = AGENT_TYPES.map((type, idx) => ({
    agent_type: type,
    label: AGENT_LABELS[type],
    total_cost: Math.round(((6 - idx) * 15000 + Math.random() * 5000)),
    service_level: Math.round((75 + idx * 4 + Math.random() * 3) * 10) / 10,
    stockout_rate: Math.round((15 - idx * 2.2 + Math.random() * 2) * 10) / 10,
    bullwhip_ratio: Math.round((2.5 - idx * 0.3 + Math.random() * 0.4) * 100) / 100,
    improvement_vs_naive: idx === 0 ? 0 : Math.round(idx * 5.5 + Math.random() * 4),
    scenarios_run: Math.round(20 + Math.random() * 80),
  }));

  // Mode distribution
  const modeDistribution = [
    { name: 'Manual', value: 15, color: MODE_COLORS.manual },
    { name: 'Copilot', value: 45, color: MODE_COLORS.copilot },
    { name: 'Autonomous', value: 40, color: MODE_COLORS.autonomous },
  ];

  // Summary
  const bestAgent = comparisonData.reduce((best, curr) =>
    curr.improvement_vs_naive > best.improvement_vs_naive ? curr : best
  );
  const avgImprovement = Math.round(
    comparisonData.reduce((sum, a) => sum + a.improvement_vs_naive, 0) / comparisonData.length
  );

  return {
    trend_data: trendData,
    comparison: comparisonData,
    mode_distribution: modeDistribution,
    summary: {
      best_agent: bestAgent.label,
      best_improvement: bestAgent.improvement_vs_naive,
      avg_improvement: avgImprovement,
      total_scenarios: comparisonData.reduce((s, a) => s + a.scenarios_run, 0),
      active_agents: AGENT_TYPES.length,
    },
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

const TrendIndicator = ({ value }) => {
  if (value > 2) return <TrendingUp className="h-4 w-4 text-green-500" />;
  if (value < -2) return <TrendingDown className="h-4 w-4 text-red-500" />;
  return <Minus className="h-4 w-4 text-muted-foreground" />;
};

// ============================================================================
// Main Component
// ============================================================================

const AgentBenchmarkDashboard = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [activeTab, setActiveTab] = useState('trends');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get('/agent-performance/dashboard');
      setData(response.data);
    } catch (err) {
      console.warn('Agent benchmark endpoint not available, using demo data:', err.message);
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

  const { trend_data, comparison, mode_distribution, summary } = data || {};

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
        <Link to="/" className="hover:text-foreground">Home</Link>
        <ChevronRight className="h-4 w-4" />
        <Link to="/admin?section=training" className="hover:text-foreground">AI & Agents</Link>
        <ChevronRight className="h-4 w-4" />
        <span className="text-foreground">Agent Benchmark</span>
      </nav>

      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-3">
          <Bot className="h-7 w-7 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">Agent Benchmark Dashboard</h1>
            <p className="text-sm text-muted-foreground">
              Compare AI agent strategies across cost, service level, and efficiency metrics
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

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          title="Best Performing Agent"
          value={summary?.best_agent || '--'}
          subtitle={`${summary?.best_improvement || 0}% vs naive baseline`}
          icon={Award}
          color="green"
        />
        <StatCard
          title="Avg Improvement"
          value={`${summary?.avg_improvement || 0}%`}
          subtitle="across all agent types"
          icon={TrendingUp}
          color="blue"
        />
        <StatCard
          title="Total Scenarios"
          value={summary?.total_scenarios || 0}
          subtitle="benchmark runs completed"
          icon={BarChart3}
          color="purple"
        />
        <StatCard
          title="Active Agents"
          value={summary?.active_agents || 0}
          subtitle="strategies configured"
          icon={Bot}
          color="amber"
        />
      </div>

      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="trends" className="flex items-center gap-1.5">
            <TrendingUp className="h-4 w-4" />
            Performance Trends
          </TabsTrigger>
          <TabsTrigger value="comparison" className="flex items-center gap-1.5">
            <BarChart3 className="h-4 w-4" />
            Comparison Table
          </TabsTrigger>
          <TabsTrigger value="distribution" className="flex items-center gap-1.5">
            <PieChartIcon className="h-4 w-4" />
            Mode Distribution
          </TabsTrigger>
        </TabsList>

        {/* Performance Trend Tab */}
        <TabsContent value="trends">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Agent Score Over Time (% improvement vs naive)</CardTitle>
            </CardHeader>
            <CardContent>
              {trend_data && trend_data.length > 0 ? (
                <ResponsiveContainer width="100%" height={360}>
                  <LineChart data={trend_data}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis dataKey="week" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} unit="%" />
                    <RTooltip />
                    <Legend />
                    {AGENT_TYPES.map((agent, idx) => (
                      <Line
                        key={agent}
                        type="monotone"
                        dataKey={agent}
                        name={AGENT_LABELS[agent]}
                        stroke={COLORS[idx]}
                        strokeWidth={agent === 'llm' || agent === 'optimizer' ? 2.5 : 1.5}
                        dot={false}
                        strokeDasharray={agent === 'naive' ? '5 5' : undefined}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-muted-foreground text-center py-12">No trend data available</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Comparison Table Tab */}
        <TabsContent value="comparison">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Bot className="h-4 w-4" />
                Agent Strategy Comparison
              </CardTitle>
            </CardHeader>
            <CardContent>
              {comparison && comparison.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs text-muted-foreground">
                        <th className="pb-2 pr-4 font-medium">Agent Strategy</th>
                        <th className="pb-2 pr-4 font-medium text-right">Total Cost</th>
                        <th className="pb-2 pr-4 font-medium text-right">Service Level %</th>
                        <th className="pb-2 pr-4 font-medium text-right">Stockout Rate %</th>
                        <th className="pb-2 pr-4 font-medium text-right">Bullwhip Ratio</th>
                        <th className="pb-2 pr-4 font-medium text-right">vs Naive</th>
                        <th className="pb-2 font-medium text-right">Scenarios</th>
                      </tr>
                    </thead>
                    <tbody>
                      {comparison.map((row) => (
                        <tr key={row.agent_type} className="border-b last:border-0 hover:bg-muted/50">
                          <td className="py-2.5 pr-4 font-medium flex items-center gap-2">
                            <Bot className="h-3.5 w-3.5 text-muted-foreground" />
                            {row.label}
                          </td>
                          <td className="py-2.5 pr-4 text-right font-mono">
                            ${row.total_cost.toLocaleString()}
                          </td>
                          <td className="py-2.5 pr-4 text-right">
                            <span className={cn(
                              'font-mono font-medium',
                              row.service_level >= 92 ? 'text-green-600' : row.service_level >= 85 ? 'text-amber-600' : 'text-red-600',
                            )}>
                              {row.service_level}%
                            </span>
                          </td>
                          <td className="py-2.5 pr-4 text-right">
                            <span className={cn(
                              'font-mono',
                              row.stockout_rate <= 5 ? 'text-green-600' : row.stockout_rate <= 10 ? 'text-amber-600' : 'text-red-600',
                            )}>
                              {row.stockout_rate}%
                            </span>
                          </td>
                          <td className="py-2.5 pr-4 text-right font-mono">
                            {row.bullwhip_ratio}
                          </td>
                          <td className="py-2.5 pr-4 text-right">
                            <div className="flex items-center justify-end gap-1">
                              <TrendIndicator value={row.improvement_vs_naive} />
                              <span className={cn(
                                'font-mono font-medium',
                                row.improvement_vs_naive > 0 ? 'text-green-600' : 'text-muted-foreground',
                              )}>
                                {row.improvement_vs_naive > 0 ? '+' : ''}{row.improvement_vs_naive}%
                              </span>
                            </div>
                          </td>
                          <td className="py-2.5 text-right font-mono text-muted-foreground">
                            {row.scenarios_run}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-muted-foreground text-center py-12">No comparison data available</p>
              )}
            </CardContent>
          </Card>

          {/* Cost vs Service Level Bar Chart */}
          {comparison && comparison.length > 0 && (
            <Card className="mt-4">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Cost by Agent Strategy</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={comparison}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <RTooltip />
                    <Bar dataKey="total_cost" name="Total Cost ($)" radius={[4, 4, 0, 0]}>
                      {comparison.map((_, idx) => (
                        <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Mode Distribution Tab */}
        <TabsContent value="distribution">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Agent Mode Distribution</CardTitle>
              </CardHeader>
              <CardContent>
                {mode_distribution && mode_distribution.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={mode_distribution}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={110}
                        paddingAngle={3}
                        dataKey="value"
                        label={({ name, value }) => `${name}: ${value}%`}
                      >
                        {mode_distribution.map((entry, idx) => (
                          <Cell key={idx} fill={entry.color} />
                        ))}
                      </Pie>
                      <RTooltip />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="text-muted-foreground text-center py-12">No distribution data</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Mode Breakdown</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4 py-4">
                  {(mode_distribution || []).map((mode) => (
                    <div key={mode.name} className="space-y-1">
                      <div className="flex justify-between text-sm">
                        <span className="font-medium">{mode.name}</span>
                        <span className="font-mono">{mode.value}%</span>
                      </div>
                      <div className="h-3 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{ width: `${mode.value}%`, backgroundColor: mode.color }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-6 p-4 rounded-lg bg-muted/30">
                  <p className="text-sm text-muted-foreground">
                    <strong>Manual:</strong> Human makes all decisions.{' '}
                    <strong>Copilot:</strong> AI suggests, human approves.{' '}
                    <strong>Autonomous:</strong> AI decides, human monitors.
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default AgentBenchmarkDashboard;
