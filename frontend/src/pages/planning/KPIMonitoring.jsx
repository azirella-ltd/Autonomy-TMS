/**
 * KPI Monitoring — Gartner Hierarchy of Supply Chain Metrics
 *
 * Tabs: Tier 1 ASSESS | Tier 2 DIAGNOSE | Tier 3 CORRECT | Tier 4 AI Performance
 * HierarchyFilterBar for Geography / Product / Time drill-down
 * All charts use Recharts (consistent with rest of platform)
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
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
  LayoutDashboard,
  TrendingUp,
  RefreshCw,
  Download,
  Bot,
  Target,
  Search,
  Wrench,
  Sparkles,
} from 'lucide-react';
import { cn } from '@azirella-ltd/autonomy-frontend';
import { api } from '../../services/api';
import HierarchyFilterBar from '../../components/metrics/HierarchyFilterBar';
import GartnerMetricCard from '../../components/metrics/GartnerMetricCard';
import CompositeMetricCard from '../../components/metrics/CompositeMetricCard';

const KPIMonitoring = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'tier1');
  const [metricsData, setMetricsData] = useState(null);

  // Hierarchy state from URL params (bookmarkable)
  const [hierarchy, setHierarchy] = useState({
    site_level: searchParams.get('site_level') || 'company',
    site_key: searchParams.get('site_key') || 'ALL',
    product_level: searchParams.get('product_level') || 'category',
    product_key: searchParams.get('product_key') || 'ALL',
    time_bucket: searchParams.get('time_bucket') || 'year',
    time_key: searchParams.get('time_key') || '2025',
  });

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get('/hierarchical-metrics/dashboard', {
        params: hierarchy,
      });
      setMetricsData(response.data?.data || response.data);
    } catch (err) {
      console.warn('Hierarchical metrics endpoint not available:', err);
      setError('Failed to load metrics data. Using fallback.');
    } finally {
      setLoading(false);
    }
  }, [hierarchy]);

  useEffect(() => {
    fetchMetrics();
  }, [fetchMetrics]);

  // Sync hierarchy to URL params
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

  const handleBreadcrumbClick = (dimension, level, key) => {
    handleDrillDown(dimension, level, key);
  };

  const tiers = metricsData?.tiers;

  // ── Tier 1 ASSESS ──────────────────────────────────────────────
  const renderTier1 = () => {
    const metrics = tiers?.tier1_assess?.metrics;
    if (!metrics) return <p className="text-muted-foreground text-sm">No Tier 1 data available.</p>;

    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {Object.entries(metrics).map(([key, m]) => (
            <GartnerMetricCard
              key={key}
              label={m.label}
              value={m.value}
              unit={m.unit}
              target={m.target}
              trend={m.trend}
              benchmark={m.benchmark}
              status={m.status}
              tier="tier1"
              scorCode={m.scor_code}
              lowerIsBetter={m.lower_is_better}
              ciLower={m.ci_lower}
              ciUpper={m.ci_upper}
              n={m.n}
            />
          ))}
        </div>

        {/* Trend chart */}
        {metricsData?.trend_data && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Tier 1 Performance Trend</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={metricsData.trend_data}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <RTooltip />
                  <Legend />
                  <Line type="monotone" dataKey="pof" name="POF %" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="touchless" name="Touchless %" stroke="#06b6d4" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="otif" name="OTIF %" stroke="#22c55e" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>
    );
  };

  // ── Tier 2 DIAGNOSE ────────────────────────────────────────────
  const renderTier2 = () => {
    const metrics = tiers?.tier2_diagnose?.metrics;
    if (!metrics) return <p className="text-muted-foreground text-sm">No Tier 2 data available.</p>;

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

        {/* C2C Trend */}
        {metricsData?.trend_data && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Cash-to-Cash & OFCT Trend</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={metricsData.trend_data}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
                  <RTooltip />
                  <Legend />
                  <Line yAxisId="left" type="monotone" dataKey="c2c" name="C2C (days)" stroke="#f59e0b" strokeWidth={2} dot={false} />
                  <Line yAxisId="right" type="monotone" dataKey="ofct" name="OFCT (days)" stroke="#3b82f6" strokeWidth={2} dot={false} />
                  <ReferenceLine yAxisId="left" y={35} stroke="#f59e0b" strokeDasharray="3 3" label="C2C Target" />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>
    );
  };

  // ── Tier 3 CORRECT ─────────────────────────────────────────────
  const renderTier3 = () => {
    const categories = tiers?.tier3_correct?.categories;
    if (!categories) return <p className="text-muted-foreground text-sm">No Tier 3 data available.</p>;

    const CATEGORY_LABELS = {
      demand_planning: 'Demand Planning',
      inventory: 'Inventory Management',
      procurement: 'Procurement',
      manufacturing: 'Manufacturing',
      fulfillment: 'Fulfillment',
    };

    return (
      <div className="space-y-6">
        {Object.entries(categories).map(([catKey, catMetrics]) => (
          <div key={catKey}>
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
              {CATEGORY_LABELS[catKey] || catKey}
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {Object.entries(catMetrics).map(([metKey, m]) => (
                <GartnerMetricCard
                  key={metKey}
                  label={m.label}
                  value={m.value}
                  unit={m.unit}
                  target={m.target}
                  trend={m.trend}
                  benchmark={m.benchmark}
                  status={m.status}
                  tier="tier3"
                  agent={m.agent}
                  scorCode={m.scor_code}
                  lowerIsBetter={m.lower_is_better}
                  ciLower={m.ci_lower}
                  ciUpper={m.ci_upper}
                  n={m.n}
                  compact
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  // ── Tier 4 AI PERFORMANCE ──────────────────────────────────────
  const renderTier4 = () => {
    const tier4 = tiers?.tier4_agent;
    if (!tier4) return <p className="text-muted-foreground text-sm">No Tier 4 data available.</p>;

    const { metrics: agentMetrics, per_trm, hive_metrics } = tier4;

    return (
      <div className="space-y-6">
        {/* Summary KPIs */}
        {agentMetrics && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(agentMetrics).map(([key, m]) => (
              <GartnerMetricCard
                key={key}
                label={m.label}
                value={m.value}
                unit={m.unit}
                target={m.target}
                trend={m.trend}
                status={m.status}
                tier="tier4"
                lowerIsBetter={m.lower_is_better}
              />
            ))}
          </div>
        )}

        {/* Per-TRM Agent Table */}
        {per_trm && per_trm.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Bot className="h-4 w-4" />
                Per-TRM Agent Performance
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

        {/* Hive Metrics */}
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

        {/* Agent performance trend */}
        {metricsData?.trend_data && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">AI Performance Trend</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={metricsData.trend_data}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <RTooltip />
                  <Legend />
                  <Bar dataKey="touchless" name="Touchless %" fill="#06b6d4" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
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
        <div className="flex items-center gap-2">
          <LayoutDashboard className="h-7 w-7 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">KPI Monitoring</h1>
            <p className="text-xs text-muted-foreground">Gartner Hierarchy of Supply Chain Metrics</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={fetchMetrics}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm">
            <Download className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Hierarchy Filter Bar */}
      <HierarchyFilterBar
        breadcrumbs={metricsData?.breadcrumbs}
        children={metricsData?.children}
        onDrillDown={handleDrillDown}
        onBreadcrumbClick={handleBreadcrumbClick}
      />

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <div className="flex justify-center p-12">
          <Spinner size="lg" />
        </div>
      ) : (
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-4">
            <TabsTrigger value="tier1" className="flex items-center gap-1.5">
              <Target className="h-4 w-4" />
              Tier 1 ASSESS
            </TabsTrigger>
            <TabsTrigger value="tier2" className="flex items-center gap-1.5">
              <Search className="h-4 w-4" />
              Tier 2 DIAGNOSE
            </TabsTrigger>
            <TabsTrigger value="tier3" className="flex items-center gap-1.5">
              <Wrench className="h-4 w-4" />
              Tier 3 CORRECT
            </TabsTrigger>
            <TabsTrigger value="tier4" className="flex items-center gap-1.5">
              <Bot className="h-4 w-4" />
              Tier 4 AI
            </TabsTrigger>
          </TabsList>

          <TabsContent value="tier1">{renderTier1()}</TabsContent>
          <TabsContent value="tier2">{renderTier2()}</TabsContent>
          <TabsContent value="tier3">{renderTier3()}</TabsContent>
          <TabsContent value="tier4">{renderTier4()}</TabsContent>
        </Tabs>
      )}

      {/* Context bar */}
      {metricsData?.hierarchy_context && (
        <div className="mt-4 text-xs text-muted-foreground flex items-center gap-4">
          <span>Context: {metricsData.hierarchy_context.site_level}/{metricsData.hierarchy_context.site_key}</span>
          <span>{metricsData.hierarchy_context.product_level}/{metricsData.hierarchy_context.product_key}</span>
          <span>{metricsData.hierarchy_context.time_bucket}/{metricsData.hierarchy_context.time_key}</span>
        </div>
      )}
    </div>
  );
};

export default KPIMonitoring;
