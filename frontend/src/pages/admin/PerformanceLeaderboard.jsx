/**
 * Performance Leaderboard
 *
 * Phase 4 dashboard for ranking participants and agents across scenarios.
 * Shows leaderboard table with trend indicators, filters by scenario and
 * agent type, and summary statistics. Uses demo data fallback when API
 * is unavailable.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Card, CardContent, CardHeader, CardTitle,
  Alert, Badge, Button,
} from '../../components/common';
import {
  Trophy, TrendingUp, TrendingDown, Minus, RefreshCw, ChevronRight,
  Users, Award, BarChart3, Filter, Medal,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';
import { api } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';

// ============================================================================
// Demo Data Generation
// ============================================================================

const AGENT_TYPES_ALL = ['human', 'naive', 'conservative', 'reactive', 'ml_forecast', 'optimizer', 'llm'];
const AGENT_LABELS = {
  human: 'Human',
  naive: 'Naive',
  conservative: 'Conservative',
  reactive: 'Reactive',
  ml_forecast: 'ML Forecast',
  optimizer: 'Optimizer',
  llm: 'LLM Agent',
};
const SCENARIOS = ['Freight Tender', 'Network Disruption', 'Mode Selection', 'All Scenarios'];

const NAMES = [
  'Alice Chen', 'Bob Martinez', 'Carol Singh', 'David Kim',
  'Eva Johansson', 'Frank Okafor', 'Grace Tanaka', 'Henry Mueller',
  'Iris Petrov', 'James Wilson', 'Kate Thompson', 'Leo Fernandez',
];

function generateDemoData() {
  const entries = [];

  // Mix of human scenario users and AI agents
  NAMES.forEach((name, idx) => {
    const isAgent = idx >= 8;
    const agentType = isAgent
      ? AGENT_TYPES_ALL[2 + (idx % 5)]
      : 'human';
    const baseImprovement = isAgent
      ? 15 + (idx % 5) * 6 + Math.random() * 8
      : 5 + Math.random() * 25;

    entries.push({
      id: idx + 1,
      name: isAgent ? `${AGENT_LABELS[agentType]} Agent` : name,
      agent_type: agentType,
      total_cost: Math.round(90000 - baseImprovement * 800 + (Math.random() - 0.5) * 8000),
      service_level: Math.round((78 + baseImprovement * 0.6 + Math.random() * 5) * 10) / 10,
      improvement_pct: Math.round(baseImprovement * 10) / 10,
      scenarios_played: Math.round(3 + Math.random() * 15),
      trend: Math.random() > 0.6 ? 'up' : Math.random() > 0.3 ? 'steady' : 'down',
      best_scenario: SCENARIOS[Math.floor(Math.random() * 3)],
      avg_bullwhip: Math.round((2.0 - baseImprovement * 0.04 + Math.random() * 0.5) * 100) / 100,
    });
  });

  // Sort by improvement descending
  entries.sort((a, b) => b.improvement_pct - a.improvement_pct);

  // Add rank
  entries.forEach((entry, idx) => {
    entry.rank = idx + 1;
  });

  // Summary stats
  const avgImprovement = Math.round(
    entries.reduce((sum, e) => sum + e.improvement_pct, 0) / entries.length * 10
  ) / 10;
  const bestEntry = entries[0];

  return {
    leaderboard: entries,
    summary: {
      total_participants: entries.length,
      human_count: entries.filter(e => e.agent_type === 'human').length,
      agent_count: entries.filter(e => e.agent_type !== 'human').length,
      avg_improvement: avgImprovement,
      best_name: bestEntry.name,
      best_improvement: bestEntry.improvement_pct,
      best_service_level: bestEntry.service_level,
    },
    scenarios: SCENARIOS,
    agent_types: AGENT_TYPES_ALL,
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

const TrendIndicator = ({ trend }) => {
  if (trend === 'up') return <TrendingUp className="h-4 w-4 text-green-500" />;
  if (trend === 'down') return <TrendingDown className="h-4 w-4 text-red-500" />;
  return <Minus className="h-4 w-4 text-muted-foreground" />;
};

const RankBadge = ({ rank }) => {
  if (rank === 1) return <Medal className="h-5 w-5 text-yellow-500" />;
  if (rank === 2) return <Medal className="h-5 w-5 text-gray-400" />;
  if (rank === 3) return <Medal className="h-5 w-5 text-amber-700" />;
  return <span className="text-sm font-mono text-muted-foreground w-5 text-center">{rank}</span>;
};

// ============================================================================
// Main Component
// ============================================================================

const PerformanceLeaderboard = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [scenarioFilter, setScenarioFilter] = useState('All Scenarios');
  const [agentFilter, setAgentFilter] = useState('all');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get('/performance/leaderboard');
      setData(response.data);
    } catch (err) {
      console.warn('Leaderboard endpoint not available, using demo data:', err.message);
      setData(generateDemoData());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Apply filters
  const filteredLeaderboard = useMemo(() => {
    if (!data?.leaderboard) return [];
    let entries = [...data.leaderboard];

    if (agentFilter !== 'all') {
      if (agentFilter === 'human') {
        entries = entries.filter(e => e.agent_type === 'human');
      } else if (agentFilter === 'ai') {
        entries = entries.filter(e => e.agent_type !== 'human');
      } else {
        entries = entries.filter(e => e.agent_type === agentFilter);
      }
    }

    // Re-rank after filtering
    entries.forEach((entry, idx) => {
      entry.filtered_rank = idx + 1;
    });

    return entries;
  }, [data, agentFilter]);

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex justify-center p-12">
          <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
        </div>
      </div>
    );
  }

  const { summary, scenarios, agent_types } = data || {};

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Demo data banner */}
      <div className="mb-4 px-4 py-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-center gap-2">
        <span className="font-semibold">Demo Data</span>
        <span>This dashboard shows illustrative data. Real performance rankings will populate from agent decisions and planner activity.</span>
      </div>

      {/* Breadcrumbs */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
        <Link to="/" className="hover:text-foreground">Home</Link>
        <ChevronRight className="h-4 w-4" />
        <Link to="/admin?section=training" className="hover:text-foreground">AI & Agents</Link>
        <ChevronRight className="h-4 w-4" />
        <span className="text-foreground">Performance Leaderboard</span>
      </nav>

      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-3">
          <Trophy className="h-7 w-7 text-yellow-500" />
          <div>
            <h1 className="text-2xl font-bold">Performance Leaderboard</h1>
            <p className="text-sm text-muted-foreground">
              Rankings across humans and AI agents by cost reduction and service level
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
          title="Total Participants"
          value={summary?.total_participants || 0}
          subtitle={`${summary?.human_count || 0} human, ${summary?.agent_count || 0} AI`}
          icon={Users}
          color="blue"
        />
        <StatCard
          title="Avg Improvement"
          value={`${summary?.avg_improvement || 0}%`}
          subtitle="vs naive baseline"
          icon={TrendingUp}
          color="green"
        />
        <StatCard
          title="Top Performer"
          value={summary?.best_name || '--'}
          subtitle={`+${summary?.best_improvement || 0}% improvement`}
          icon={Award}
          color="amber"
        />
        <StatCard
          title="Best Service Level"
          value={`${summary?.best_service_level || 0}%`}
          subtitle="highest achieved"
          icon={BarChart3}
          color="purple"
        />
      </div>

      {/* Filters */}
      <Card className="mb-4">
        <CardContent className="p-3">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Filters:</span>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm text-muted-foreground">Scenario:</label>
              <select
                value={scenarioFilter}
                onChange={(e) => setScenarioFilter(e.target.value)}
                className="px-3 py-1.5 text-sm border rounded-md bg-background"
              >
                {(scenarios || SCENARIOS).map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm text-muted-foreground">Type:</label>
              <select
                value={agentFilter}
                onChange={(e) => setAgentFilter(e.target.value)}
                className="px-3 py-1.5 text-sm border rounded-md bg-background"
              >
                <option value="all">All Participants</option>
                <option value="human">Humans Only</option>
                <option value="ai">AI Agents Only</option>
                {(agent_types || AGENT_TYPES_ALL).filter(t => t !== 'human').map(t => (
                  <option key={t} value={t}>{AGENT_LABELS[t] || t}</option>
                ))}
              </select>
            </div>
            <Badge variant="outline" className="ml-auto">
              {filteredLeaderboard.length} result{filteredLeaderboard.length !== 1 ? 's' : ''}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Leaderboard Table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Trophy className="h-4 w-4" />
            Rankings
          </CardTitle>
        </CardHeader>
        <CardContent>
          {filteredLeaderboard.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="pb-2 pr-3 font-medium w-12 text-center">Rank</th>
                    <th className="pb-2 pr-4 font-medium">Name</th>
                    <th className="pb-2 pr-4 font-medium">Type</th>
                    <th className="pb-2 pr-4 font-medium text-right">Total Cost</th>
                    <th className="pb-2 pr-4 font-medium text-right">Service Level</th>
                    <th className="pb-2 pr-4 font-medium text-right">Bullwhip</th>
                    <th className="pb-2 pr-4 font-medium text-right">Improvement</th>
                    <th className="pb-2 pr-4 font-medium text-right">Scenarios</th>
                    <th className="pb-2 font-medium text-center">Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredLeaderboard.map((row) => (
                    <tr
                      key={row.id}
                      className={cn(
                        'border-b last:border-0 hover:bg-muted/50 transition-colors',
                        row.filtered_rank <= 3 && 'bg-amber-50/30 dark:bg-amber-900/5',
                      )}
                    >
                      <td className="py-2.5 pr-3 text-center">
                        <RankBadge rank={row.filtered_rank} />
                      </td>
                      <td className="py-2.5 pr-4">
                        <span className="font-medium">{row.name}</span>
                      </td>
                      <td className="py-2.5 pr-4">
                        <Badge
                          variant={row.agent_type === 'human' ? 'default' : 'outline'}
                          className="text-xs"
                        >
                          {AGENT_LABELS[row.agent_type] || row.agent_type}
                        </Badge>
                      </td>
                      <td className="py-2.5 pr-4 text-right font-mono">
                        ${row.total_cost.toLocaleString()}
                      </td>
                      <td className="py-2.5 pr-4 text-right">
                        <span className={cn(
                          'font-mono font-medium',
                          row.service_level >= 92 ? 'text-green-600'
                            : row.service_level >= 85 ? 'text-amber-600'
                            : 'text-red-600',
                        )}>
                          {row.service_level}%
                        </span>
                      </td>
                      <td className="py-2.5 pr-4 text-right font-mono">
                        {row.avg_bullwhip}
                      </td>
                      <td className="py-2.5 pr-4 text-right">
                        <span className={cn(
                          'font-mono font-medium',
                          row.improvement_pct >= 20 ? 'text-green-600'
                            : row.improvement_pct >= 10 ? 'text-blue-600'
                            : 'text-muted-foreground',
                        )}>
                          +{row.improvement_pct}%
                        </span>
                      </td>
                      <td className="py-2.5 pr-4 text-right font-mono text-muted-foreground">
                        {row.scenarios_played}
                      </td>
                      <td className="py-2.5 text-center">
                        <TrendIndicator trend={row.trend} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-muted-foreground text-center py-12">
              No participants match the current filters
            </p>
          )}
        </CardContent>
      </Card>

      {/* Context Footer */}
      <div className="mt-4 text-xs text-muted-foreground flex items-center gap-4">
        <span>Improvement measured against naive (pass-through) baseline policy</span>
        <span>|</span>
        <span>Scenario: {scenarioFilter}</span>
        <span>|</span>
        <span>Filter: {agentFilter === 'all' ? 'All' : AGENT_LABELS[agentFilter] || agentFilter}</span>
      </div>
    </div>
  );
};

export default PerformanceLeaderboard;
