/**
 * Agent Performance Page - Detailed Performance Analysis
 *
 * ADH Agent Performance Analysis Dashboard
 * Shows detailed Agent Performance Score and Human Override Rate
 * metrics with breakdowns by category/segment.
 *
 * Features:
 * - Summary KPIs (Agent Score vs Planner Score, Override Rate, Automation %)
 * - Performance & Override Trend Charts over time
 * - Category-level breakdown with individual metrics
 * - Planner capacity metrics (lanes per planner, efficiency gains)
 * - Key events timeline (Go-live, RIFs, NPIs)
 */

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  TrendingUp,
  TrendingDown,
  Brain,
  Bot,
  Users,
  Package,
  Activity,
  Calendar,
  BarChart3,
  ChevronRight,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  RefreshCw,
} from 'lucide-react';
import { cn } from '../lib/utils/cn';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Badge,
  Button,
  Spinner,
  Alert,
} from '../components/common';
import { api } from '../services/api';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
} from 'recharts';
import { Sparkles } from 'lucide-react';

// =============================================================================
// Summary KPI Card
// =============================================================================

const SummaryKPICard = ({ title, value, subtitle, icon: Icon, trend, trendLabel, variant = 'default' }) => {
  const isPositive = trend > 0;
  const isNegative = trend < 0;

  const variantStyles = {
    success: 'border-green-200 bg-green-50/50 dark:border-green-900 dark:bg-green-950/20',
    warning: 'border-amber-200 bg-amber-50/50 dark:border-amber-900 dark:bg-amber-950/20',
    info: 'border-blue-200 bg-blue-50/50 dark:border-blue-900 dark:bg-blue-950/20',
    default: '',
  };

  const iconStyles = {
    success: 'bg-green-100 text-green-600 dark:bg-green-900/40 dark:text-green-400',
    warning: 'bg-amber-100 text-amber-600 dark:bg-amber-900/40 dark:text-amber-400',
    info: 'bg-blue-100 text-blue-600 dark:bg-blue-900/40 dark:text-blue-400',
    default: 'bg-primary/10 text-primary',
  };

  return (
    <Card className={cn('border', variantStyles[variant])}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{title}</p>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-3xl font-bold">{value}</span>
              {trend !== undefined && (
                <span className={cn(
                  'flex items-center text-xs font-medium',
                  isPositive && 'text-green-600',
                  isNegative && 'text-red-600',
                  !isPositive && !isNegative && 'text-muted-foreground'
                )}>
                  {isPositive && <ArrowUpRight className="h-3 w-3" />}
                  {isNegative && <ArrowDownRight className="h-3 w-3" />}
                  {!isPositive && !isNegative && <Minus className="h-3 w-3" />}
                  {Math.abs(trend)}%
                </span>
              )}
            </div>
            {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
            {trendLabel && <p className="text-xs text-muted-foreground">{trendLabel}</p>}
          </div>
          {Icon && (
            <div className={cn('rounded-lg p-2.5', iconStyles[variant])}>
              <Icon className="h-5 w-5" />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

// =============================================================================
// Agent Performance Card
// =============================================================================

const AgentPerformanceCard = ({ agentScore, plannerScore }) => {
  const diff = agentScore - plannerScore;

  return (
    <Card className="border-2 border-green-200 bg-green-50/30 dark:border-green-900 dark:bg-green-950/10">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg flex items-center gap-2">
          <Bot className="h-5 w-5 text-green-600" />
          Agent Performance Score
        </CardTitle>
        <p className="text-xs text-muted-foreground">-100 to +100 scale, higher is better</p>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          <div className="text-center p-4 bg-white dark:bg-gray-900 rounded-lg border">
            <Bot className="h-8 w-8 mx-auto text-green-600 mb-2" />
            <p className="text-3xl font-bold text-green-600">+{agentScore}</p>
            <p className="text-sm text-muted-foreground">Agent Decisions</p>
          </div>
          <div className="text-center p-4 bg-white dark:bg-gray-900 rounded-lg border">
            <Users className="h-8 w-8 mx-auto text-blue-600 mb-2" />
            <p className="text-3xl font-bold text-blue-600">+{plannerScore}</p>
            <p className="text-sm text-muted-foreground">Planner Decisions</p>
          </div>
        </div>
        <div className="mt-4 p-3 bg-green-100 dark:bg-green-900/30 rounded-lg text-center">
          <p className="text-sm text-green-800 dark:text-green-300">
            Agent decisions outperforming manual by <span className="font-bold">+{diff}</span> points
          </p>
        </div>
      </CardContent>
    </Card>
  );
};

// =============================================================================
// Human Overrides Card
// =============================================================================

const HumanOverridesCard = ({ overrideRate, automationPct }) => {
  return (
    <Card className="border-2 border-blue-200 bg-blue-50/30 dark:border-blue-900 dark:bg-blue-950/10">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg flex items-center gap-2">
          <Activity className="h-5 w-5 text-blue-600" />
          Human Overrides
        </CardTitle>
        <p className="text-xs text-muted-foreground">Lower override rate = more trust in AI agents</p>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-center gap-8">
          <div className="text-center">
            <p className="text-5xl font-bold text-blue-600">{overrideRate}%</p>
            <p className="text-sm text-muted-foreground mt-1">Override Rate</p>
          </div>
          <div className="h-20 w-px bg-border" />
          <div className="text-center">
            <p className="text-5xl font-bold text-green-600">{automationPct}%</p>
            <p className="text-sm text-muted-foreground mt-1">Automation Adoption</p>
          </div>
        </div>
        <div className="mt-4">
          <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-green-500 to-blue-500 rounded-full transition-all"
              style={{ width: `${automationPct}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground mt-1">
            <span>0% (All Manual)</span>
            <span>100% (Fully Automated)</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

// =============================================================================
// Category Breakdown Table
// =============================================================================

const CategoryBreakdownTable = ({ categories }) => {
  if (!categories || categories.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Package className="h-5 w-5" />
          Performance by Category
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2 px-3 text-sm font-medium text-muted-foreground">Category</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-muted-foreground">Agent Score</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-muted-foreground">Planner Score</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-muted-foreground">Automation</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-muted-foreground">Override Rate</th>
                <th className="text-right py-2 px-3 text-sm font-medium text-muted-foreground">Decisions</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((cat, idx) => (
                <tr key={idx} className="border-b last:border-b-0 hover:bg-muted/50">
                  <td className="py-3 px-3 font-medium">{cat.category}</td>
                  <td className="py-3 px-3 text-right">
                    <span className="text-green-600 font-semibold">+{cat.agent_score?.toFixed(1) || 'N/A'}</span>
                  </td>
                  <td className="py-3 px-3 text-right">
                    <span className="text-blue-600 font-semibold">+{cat.planner_score?.toFixed(1) || 'N/A'}</span>
                  </td>
                  <td className="py-3 px-3 text-right">
                    <Badge variant={cat.automation_percentage >= 70 ? 'success' : cat.automation_percentage >= 50 ? 'warning' : 'outline'}>
                      {cat.automation_percentage?.toFixed(0) || 0}%
                    </Badge>
                  </td>
                  <td className="py-3 px-3 text-right">
                    <span className={cn(
                      'font-medium',
                      cat.override_rate <= 30 ? 'text-green-600' : cat.override_rate <= 50 ? 'text-amber-600' : 'text-red-600'
                    )}>
                      {cat.override_rate?.toFixed(0) || 0}%
                    </span>
                  </td>
                  <td className="py-3 px-3 text-right text-muted-foreground">
                    {cat.total_decisions?.toLocaleString() || 0}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
};

// =============================================================================
// Trend Chart
// =============================================================================

const TrendChart = ({ trends }) => {
  if (!trends || trends.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <BarChart3 className="h-5 w-5" />
          Performance & Override Trends
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={trends}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis dataKey="period" className="text-xs" />
            <YAxis yAxisId="left" domain={[-20, 100]} className="text-xs" />
            <YAxis yAxisId="right" orientation="right" domain={[0, 100]} className="text-xs" />
            <Tooltip
              contentStyle={{
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '8px',
              }}
            />
            <Legend />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="agent_score"
              name="Agent Score"
              stroke="#16a34a"
              strokeWidth={2}
              dot={{ fill: '#16a34a' }}
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="planner_score"
              name="Planner Score"
              stroke="#2563eb"
              strokeWidth={2}
              dot={{ fill: '#2563eb' }}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="override_rate"
              name="Override Rate %"
              stroke="#f59e0b"
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={{ fill: '#f59e0b' }}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
};

// =============================================================================
// Planner Capacity Card
// =============================================================================

const PlannerCapacityCard = ({ capacity }) => {
  if (!capacity) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Users className="h-5 w-5" />
          Planner Capacity
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          <div className="p-4 bg-muted/50 rounded-lg text-center">
            <p className="text-3xl font-bold">{capacity.active_planners}</p>
            <p className="text-sm text-muted-foreground">Active Planners</p>
            <p className="text-xs text-green-600 mt-1">
              Down from {capacity.from_planners} planners
            </p>
          </div>
          <div className="p-4 bg-muted/50 rounded-lg text-center">
            <p className="text-3xl font-bold">{capacity.skus_per_planner?.toLocaleString()}</p>
            <p className="text-sm text-muted-foreground">SKUs per Planner</p>
            <p className="text-xs text-green-600 mt-1">
              +{capacity.efficiency_gain_pct}% efficiency
            </p>
          </div>
        </div>
        <div className="mt-4 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
          <p className="text-sm text-center">
            <span className="font-semibold text-green-700 dark:text-green-400">
              {capacity.agent_automation_pct}%
            </span>
            <span className="text-muted-foreground"> of decisions now handled by AI agents</span>
          </p>
        </div>
      </CardContent>
    </Card>
  );
};

// =============================================================================
// Key Events Timeline
// =============================================================================

const KeyEventsTimeline = ({ events }) => {
  if (!events || events.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Calendar className="h-5 w-5" />
          Key Events
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {events.map((event, idx) => (
            <div key={idx} className="flex gap-4">
              <div className="flex flex-col items-center">
                <div className="w-3 h-3 rounded-full bg-primary" />
                {idx < events.length - 1 && <div className="w-0.5 h-full bg-border mt-1" />}
              </div>
              <div className="pb-4">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{event.event}</span>
                  <Badge variant="outline" className="text-xs">{event.date}</Badge>
                </div>
                <p className="text-sm text-muted-foreground mt-1">{event.description}</p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

// =============================================================================
// Per-TRM Agent Table
// =============================================================================

const PerTRMTable = ({ perTrm }) => {
  if (!perTrm || perTrm.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Bot className="h-5 w-5" />
          Per-TRM Agent Performance ({perTrm.length} agents)
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="pb-2 pr-4 font-medium">AI Agent</th>
                <th className="pb-2 pr-4 font-medium text-right">Score</th>
                <th className="pb-2 pr-4 font-medium text-right">Touchless %</th>
                <th className="pb-2 pr-4 font-medium text-right">Override %</th>
                <th className="pb-2 font-medium text-center">Urgency</th>
              </tr>
            </thead>
            <tbody>
              {perTrm.map((agent) => (
                <tr key={agent.agent} className="border-b last:border-0 hover:bg-muted/50">
                  <td className="py-2.5 pr-4 font-medium flex items-center gap-2">
                    <Bot className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                    {agent.label || agent.agent}
                  </td>
                  <td className="py-2.5 pr-4 text-right">
                    <span className={cn(
                      'font-mono font-semibold',
                      agent.score >= 70 ? 'text-green-600' : agent.score >= 40 ? 'text-amber-600' : 'text-red-600',
                    )}>
                      {agent.score}
                    </span>
                  </td>
                  <td className="py-2.5 pr-4 text-right font-mono">{agent.touchless_pct}%</td>
                  <td className="py-2.5 pr-4 text-right font-mono">{agent.override_pct}%</td>
                  <td className="py-2.5 text-center">
                    <Badge
                      variant={agent.urgency === 'low' ? 'success' : agent.urgency === 'medium' ? 'default' : 'destructive'}
                      className="text-xs"
                    >
                      {agent.urgency}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
};

// =============================================================================
// Hive Metrics Card
// =============================================================================

const HiveMetricsCard = ({ hiveMetrics }) => {
  if (!hiveMetrics) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Sparkles className="h-5 w-5" />
          Hive Coordination Metrics
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {Object.entries(hiveMetrics).map(([key, val]) => (
            <div key={key} className="text-center p-3 bg-muted/30 rounded-lg">
              <p className="text-2xl font-bold">{typeof val === 'number' ? val.toFixed(2) : val}</p>
              <p className="text-xs text-muted-foreground mt-1">
                {key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
              </p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

// =============================================================================
// Main Agent Performance Page
// =============================================================================

const AgentPerformancePage = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [tier4Data, setTier4Data] = useState(null);
  const [planningCycle, setPlanningCycle] = useState('Q3 2025');
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = async () => {
    try {
      setRefreshing(true);
      const [perfResponse, metricsResponse] = await Promise.allSettled([
        api.get('/decision-metrics/agent-performance', {
          params: { planning_cycle: planningCycle }
        }),
        api.get('/hierarchical-metrics/dashboard'),
      ]);
      if (perfResponse.status === 'fulfilled') {
        setData(perfResponse.value.data.data);
      }
      if (metricsResponse.status === 'fulfilled') {
        setTier4Data(metricsResponse.value.data?.tiers?.tier4_agent);
      }
      setError(null);
    } catch (err) {
      console.error('Failed to fetch agent performance:', err);
      setError('Failed to load agent performance data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [planningCycle]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert variant="error">{error}</Alert>
      </div>
    );
  }

  const { summary, trends, categories, planner_capacity, key_events } = data || {};

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Agent Performance</h1>
          <p className="text-muted-foreground">
            Detailed performance and human override analysis by category and segment
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-muted/50 rounded-lg border">
            <span className="text-xs text-muted-foreground">Period:</span>
            <select
              value={planningCycle}
              onChange={(e) => setPlanningCycle(e.target.value)}
              className="text-sm font-medium bg-transparent border-none focus:outline-none focus:ring-0 cursor-pointer pr-6"
            >
              <option value="Q3 2025">Q3 2025</option>
              <option value="Q2 2025">Q2 2025</option>
              <option value="Q1 2025">Q1 2025</option>
              <option value="Q4 2024">Q4 2024</option>
            </select>
          </div>
          <Button variant="outline" size="icon" onClick={fetchData} disabled={refreshing}>
            <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
          </Button>
        </div>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-4 gap-4">
        <SummaryKPICard
          title="Total Decisions"
          value={summary?.total_decisions?.toLocaleString() || '0'}
          subtitle={`${summary?.agent_decisions || 0} by agents, ${summary?.planner_decisions || 0} by planners`}
          icon={Activity}
          variant="info"
        />
        <SummaryKPICard
          title="Touchless Rate"
          value={`${summary?.autonomous_decisions_pct || 0}%`}
          subtitle="Decisions without human intervention"
          icon={Bot}
          trend={summary?.touchless_trend}
          variant="success"
        />
        <SummaryKPICard
          title="Active Agents"
          value={summary?.active_agents || '0'}
          subtitle={`Managing ${(summary?.total_skus || 0).toLocaleString()} SKUs`}
          icon={Brain}
          variant="default"
        />
        <SummaryKPICard
          title="Active Planners"
          value={summary?.active_planners || '0'}
          subtitle={`${(summary?.skus_per_planner || 0).toLocaleString()} SKUs each`}
          icon={Users}
          variant="default"
        />
      </div>

      {/* Performance and Overrides Cards */}
      <div className="grid grid-cols-2 gap-6">
        <AgentPerformanceCard
          agentScore={summary?.agent_score || 0}
          plannerScore={summary?.planner_score || 0}
        />
        <HumanOverridesCard
          overrideRate={100 - (summary?.autonomous_decisions_pct || 0)}
          automationPct={summary?.autonomous_decisions_pct || 0}
        />
      </div>

      {/* Trend Chart */}
      <TrendChart trends={trends} />

      {/* Category Breakdown and Planner Capacity */}
      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2">
          <CategoryBreakdownTable categories={categories} />
        </div>
        <div className="space-y-6">
          <PlannerCapacityCard capacity={planner_capacity} />
          <KeyEventsTimeline events={key_events} />
        </div>
      </div>

      {/* Per-TRM Agent Performance */}
      <PerTRMTable perTrm={tier4Data?.per_trm} />

      {/* Hive Coordination Metrics */}
      <HiveMetricsCard hiveMetrics={tier4Data?.hive_metrics} />

      {/* Back to Executive Dashboard */}
      <div className="flex justify-center pt-4">
        <Button variant="outline" onClick={() => navigate('/executive-dashboard')}>
          <ChevronRight className="h-4 w-4 mr-2 rotate-180" />
          Back to Executive Dashboard
        </Button>
      </div>
    </div>
  );
};

export default AgentPerformancePage;
