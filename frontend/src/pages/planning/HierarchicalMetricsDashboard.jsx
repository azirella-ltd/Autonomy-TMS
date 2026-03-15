/**
 * HierarchicalMetricsDashboard — Full drill-down Gartner Hierarchy metrics
 *
 * Dedicated page for navigating all 4 Gartner tiers across
 * Geography / Product / Time hierarchies with breadcrumb navigation.
 *
 * Linked from Executive Dashboard "View Full Metrics" button.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, ResponsiveContainer, Legend, ReferenceLine,
} from 'recharts';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Alert,
  Badge,
  Spinner,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from '../../components/common';
import {
  BarChart3,
  TrendingUp,
  RefreshCw,
  ArrowLeft,
  Bot,
  Target,
  Search,
  Wrench,
  Sparkles,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';
import { api } from '../../services/api';
import HierarchyFilterBar from '../../components/metrics/HierarchyFilterBar';
import GartnerMetricCard from '../../components/metrics/GartnerMetricCard';
import CompositeMetricCard from '../../components/metrics/CompositeMetricCard';

const CATEGORY_LABELS = {
  demand_planning: 'Demand Planning',
  inventory: 'Inventory Management',
  procurement: 'Procurement',
  manufacturing: 'Manufacturing',
  fulfillment: 'Fulfillment',
};

const HierarchicalMetricsDashboard = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'tier1');
  const [metricsData, setMetricsData] = useState(null);

  const [hierarchy, setHierarchy] = useState({
    site_level: searchParams.get('site_level') || 'company',
    site_key: searchParams.get('site_key') || 'ALL',
    product_level: searchParams.get('product_level') || 'category',
    product_key: searchParams.get('product_key') || 'ALL',
    time_bucket: searchParams.get('time_bucket') || 'year',
    time_key: searchParams.get('time_key') || null,
  });

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get('/hierarchical-metrics/dashboard', { params: hierarchy });
      setMetricsData(response.data?.data || response.data);
    } catch (err) {
      console.error('Failed to fetch hierarchical metrics:', err);
      setError('Failed to load metrics data.');
    } finally {
      setLoading(false);
    }
  }, [hierarchy]);

  useEffect(() => { fetchMetrics(); }, [fetchMetrics]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (activeTab !== 'tier1') params.set('tab', activeTab);
    Object.entries(hierarchy).forEach(([k, v]) => {
      if (v && v !== 'ALL' && v !== 'company' && v !== 'category' && v !== 'year' && v !== '2025') {
        params.set(k, v);
      }
    });
    setSearchParams(params, { replace: true });
  }, [hierarchy, activeTab, setSearchParams]);

  const handleDrillDown = (dimension, level, key) => {
    const dimMap = { site: ['site_level', 'site_key'], product: ['product_level', 'product_key'], time: ['time_bucket', 'time_key'] };
    const [levelKey, keyKey] = dimMap[dimension];
    setHierarchy(prev => ({ ...prev, [levelKey]: level, [keyKey]: key }));
  };

  const tiers = metricsData?.tiers;

  // ── Tier 1 ─────────────────────────────────────────────────────
  const renderTier1 = () => {
    const metrics = tiers?.tier1_assess?.metrics;
    if (!metrics) return <EmptyState tier="1" />;

    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {Object.entries(metrics).map(([key, m]) => (
            <GartnerMetricCard key={key} {...mapMetricProps(m, 'tier1')} />
          ))}
        </div>
        <TrendChart data={metricsData?.trend_data} title="Strategic Performance Trend" lines={[
          { key: 'pof', name: 'POF %', color: '#8b5cf6' },
          { key: 'otif', name: 'OTIF %', color: '#22c55e' },
          { key: 'touchless', name: 'Touchless %', color: '#06b6d4' },
        ]} />
      </div>
    );
  };

  // ── Tier 2 ─────────────────────────────────────────────────────
  const renderTier2 = () => {
    const metrics = tiers?.tier2_diagnose?.metrics;
    if (!metrics) return <EmptyState tier="2" />;

    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {Object.entries(metrics).map(([key, m]) => (
            <CompositeMetricCard
              key={key}
              label={m.label}
              value={m.value}
              unit={m.unit}
              target={m.target}
              trend={m.trend}
              benchmark={m.benchmark}
              status={m.status}
              scorCode={m.scor_code}
              formula={m.formula}
              components={m.components}
              lowerIsBetter={m.lower_is_better}
              ciLower={m.ci_lower}
              ciUpper={m.ci_upper}
              n={m.n}
            />
          ))}
        </div>
        <TrendChart data={metricsData?.trend_data} title="Diagnostic Trend" lines={[
          { key: 'c2c', name: 'C2C (days)', color: '#f59e0b' },
          { key: 'ofct', name: 'OFCT (days)', color: '#3b82f6' },
          { key: 'pof', name: 'POF %', color: '#8b5cf6' },
        ]} />
      </div>
    );
  };

  // ── Tier 3 ─────────────────────────────────────────────────────
  const renderTier3 = () => {
    const categories = tiers?.tier3_correct?.categories;
    if (!categories) return <EmptyState tier="3" />;

    return (
      <div className="space-y-6">
        {Object.entries(categories).map(([catKey, catMetrics]) => (
          <div key={catKey}>
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
              {CATEGORY_LABELS[catKey] || catKey}
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {Object.entries(catMetrics).map(([metKey, m]) => (
                <GartnerMetricCard key={metKey} {...mapMetricProps(m, 'tier3')} compact />
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  // ── Tier 4 ─────────────────────────────────────────────────────
  const renderTier4 = () => {
    const tier4 = tiers?.tier4_agent;
    if (!tier4) return <EmptyState tier="4" />;

    const { metrics: agentMetrics, per_trm, hive_metrics } = tier4;

    return (
      <div className="space-y-6">
        {agentMetrics && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(agentMetrics).map(([key, m]) => (
              <GartnerMetricCard key={key} {...mapMetricProps(m, 'tier4')} />
            ))}
          </div>
        )}

        {per_trm && per_trm.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Bot className="h-4 w-4" />
                Per-TRM Agent Performance ({per_trm.length} agents)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs text-muted-foreground">
                      <th className="pb-2 pr-4 font-medium">Agent</th>
                      <th className="pb-2 pr-4 font-medium text-right">Score</th>
                      <th className="pb-2 pr-4 font-medium text-right">Touchless %</th>
                      <th className="pb-2 pr-4 font-medium text-right">Override %</th>
                      <th className="pb-2 font-medium text-center">Urgency</th>
                    </tr>
                  </thead>
                  <tbody>
                    {per_trm.map((agent) => (
                      <tr key={agent.agent} className="border-b last:border-0 hover:bg-muted/50">
                        <td className="py-2 pr-4 font-medium flex items-center gap-2">
                          <Bot className="h-3.5 w-3.5 text-muted-foreground" />
                          {agent.label || agent.agent}
                        </td>
                        <td className="py-2 pr-4 text-right">
                          <span className={cn(
                            'font-mono font-medium',
                            agent.score >= 70 ? 'text-green-600' : agent.score >= 40 ? 'text-amber-600' : 'text-red-600',
                          )}>
                            {agent.score}
                          </span>
                        </td>
                        <td className="py-2 pr-4 text-right font-mono">{agent.touchless_pct}%</td>
                        <td className="py-2 pr-4 text-right font-mono">{agent.override_pct}%</td>
                        <td className="py-2 text-center">
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
        )}

        {hive_metrics && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Sparkles className="h-4 w-4" />
                Hive Coordination Metrics
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                {Object.entries(hive_metrics).map(([key, val]) => (
                  <div key={key} className="text-center">
                    <p className="text-2xl font-bold">{typeof val === 'number' ? val.toFixed(2) : val}</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                    </p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    );
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <BarChart3 className="h-6 w-6 text-primary" />
              Hierarchical Metrics
            </h1>
            <p className="text-xs text-muted-foreground">
              Gartner Hierarchy of Supply Chain Metrics — Drill down by Geography, Product, Time
            </p>
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={fetchMetrics}>
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {/* Hierarchy Filter */}
      <HierarchyFilterBar
        breadcrumbs={metricsData?.breadcrumbs}
        children={metricsData?.children}
        onDrillDown={handleDrillDown}
        onBreadcrumbClick={handleDrillDown}
      />

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <div className="flex justify-center p-16">
          <Spinner size="lg" />
        </div>
      ) : (
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-4">
            <TabsTrigger value="tier1" className="flex items-center gap-1.5">
              <Target className="h-4 w-4" />
              ASSESS
            </TabsTrigger>
            <TabsTrigger value="tier2" className="flex items-center gap-1.5">
              <Search className="h-4 w-4" />
              DIAGNOSE
            </TabsTrigger>
            <TabsTrigger value="tier3" className="flex items-center gap-1.5">
              <Wrench className="h-4 w-4" />
              CORRECT
            </TabsTrigger>
            <TabsTrigger value="tier4" className="flex items-center gap-1.5">
              <Bot className="h-4 w-4" />
              AI Performance
            </TabsTrigger>
          </TabsList>

          <TabsContent value="tier1">{renderTier1()}</TabsContent>
          <TabsContent value="tier2">{renderTier2()}</TabsContent>
          <TabsContent value="tier3">{renderTier3()}</TabsContent>
          <TabsContent value="tier4">{renderTier4()}</TabsContent>
        </Tabs>
      )}
    </div>
  );
};

// ── Helpers ────────────────────────────────────────────────────────

const mapMetricProps = (m, tier) => ({
  label: m.label,
  value: m.value,
  unit: m.unit,
  target: m.target,
  trend: m.trend,
  benchmark: m.benchmark,
  status: m.status,
  tier,
  agent: m.agent,
  scorCode: m.scor_code,
  lowerIsBetter: m.lower_is_better,
  ciLower: m.ci_lower,
  ciUpper: m.ci_upper,
  n: m.n,
});

const EmptyState = ({ tier }) => (
  <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
    <BarChart3 className="h-10 w-10 mb-2 opacity-30" />
    <p className="text-sm">No Tier {tier} data available at this hierarchy level.</p>
  </div>
);

const TrendChart = ({ data, title, lines }) => {
  if (!data || data.length === 0) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis dataKey="period" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <RTooltip />
            <Legend />
            {lines.map((l) => (
              <Line key={l.key} type="monotone" dataKey={l.key} name={l.name} stroke={l.color} strokeWidth={2} dot={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
};

export default HierarchicalMetricsDashboard;
