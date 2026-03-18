import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, Badge } from '../../components/common';
import { Settings, Target, TrendingUp, BarChart3, DollarSign, Users, Truck, Bot } from 'lucide-react';
import api from '../../services/api';
import Sparkline from '../../components/metrics/Sparkline';

const TIER_COLORS = {
  tier1_assess: 'bg-purple-100 text-purple-700',
  tier2_diagnose: 'bg-blue-100 text-blue-700',
  tier3_correct: 'bg-amber-100 text-amber-700',
  tier4_agent: 'bg-green-100 text-green-700',
};

const TIER_LABELS = {
  tier1_assess: 'ASSESS',
  tier2_diagnose: 'DIAGNOSE',
  tier3_correct: 'CORRECT',
  tier4_agent: 'AI',
};

const CATEGORY_ICONS = {
  financial: DollarSign,
  customer: Users,
  operational: Truck,
  agent: Bot,
};

const KPIConfigurationAnalytics = () => {
  const [catalogue, setCatalogue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [counts, setCounts] = useState({ total: 0, financial: 0, customer: 0, operational: 0, agent: 0 });

  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await api.get('/hierarchical-metrics/catalogue');
        const metrics = Array.isArray(data) ? data : data?.metrics || [];
        setCatalogue(metrics);

        // Count by category
        const c = { total: metrics.length, financial: 0, customer: 0, operational: 0, agent: 0 };
        for (const m of metrics) {
          const cat = (m.category || m.perspective || '').toLowerCase();
          if (cat.includes('financ') || cat.includes('cost') || cat.includes('revenue')) c.financial++;
          else if (cat.includes('customer') || cat.includes('service')) c.customer++;
          else if (cat.includes('agent') || cat.includes('ai')) c.agent++;
          else c.operational++;
        }
        setCounts(c);
      } catch {
        // Fallback: load from dashboard metrics
        try {
          const { data } = await api.get('/hierarchical-metrics/dashboard');
          const tiers = data?.tiers || {};
          const allMetrics = [];

          for (const [tierKey, tierData] of Object.entries(tiers)) {
            if (!tierData || typeof tierData !== 'object') continue;
            const metrics = tierData.metrics || {};
            for (const [key, m] of Object.entries(metrics)) {
              if (typeof m === 'object' && 'value' in m) {
                allMetrics.push({ ...m, key, tier: tierKey });
              }
            }
            // Handle categorized metrics (tier3)
            const categories = tierData.categories || {};
            for (const [, catData] of Object.entries(categories)) {
              const catMetrics = catData?.metrics || catData || {};
              for (const [key, m] of Object.entries(catMetrics)) {
                if (typeof m === 'object' && 'value' in m) {
                  allMetrics.push({ ...m, key, tier: tierKey });
                }
              }
            }
          }

          setCatalogue(allMetrics);
          const c = { total: allMetrics.length, financial: 0, customer: 0, operational: 0, agent: 0 };
          for (const m of allMetrics) {
            if (m.tier === 'tier4_agent') c.agent++;
            else if (m.tier === 'tier1_assess') c.financial++;
            else if (m.tier === 'tier2_diagnose') c.customer++;
            else c.operational++;
          }
          setCounts(c);
        } catch (e2) {
          console.error('KPI catalogue error:', e2);
        }
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  return (
    <div className="container mx-auto px-4 py-6 max-w-7xl">
      <div className="flex items-center gap-2 mb-1">
        <Target className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">KPI Catalogue</h1>
      </div>
      <p className="text-sm text-muted-foreground mb-6">
        All configured supply chain KPIs organized by Gartner SCOR tier with current values and targets
      </p>

      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <Card><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">Total KPIs</p>
          <p className="text-2xl font-bold">{counts.total}</p>
        </CardContent></Card>
        <Card className="border-l-4 border-l-purple-500"><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">Strategic</p>
          <p className="text-2xl font-bold">{counts.financial}</p>
        </CardContent></Card>
        <Card className="border-l-4 border-l-blue-500"><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">Diagnostic</p>
          <p className="text-2xl font-bold">{counts.customer}</p>
        </CardContent></Card>
        <Card className="border-l-4 border-l-amber-500"><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">Operational</p>
          <p className="text-2xl font-bold">{counts.operational}</p>
        </CardContent></Card>
        <Card className="border-l-4 border-l-green-500"><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">AI Agent</p>
          <p className="text-2xl font-bold">{counts.agent}</p>
        </CardContent></Card>
      </div>

      {/* Metric table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <BarChart3 className="h-4 w-4" /> All Metrics
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-12 text-muted-foreground">Loading metrics catalogue...</div>
          ) : catalogue.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">No metrics configured. Visit Hierarchical Metrics to see available KPIs.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-muted-foreground border-b">
                    <th className="text-left py-2 pr-2">Tier</th>
                    <th className="text-left py-2 pr-4">Metric</th>
                    <th className="text-left py-2 pr-2">Code</th>
                    <th className="text-right py-2 pr-4">Value</th>
                    <th className="text-right py-2 pr-4">Target</th>
                    <th className="py-2 pr-2">Trend</th>
                    <th className="text-left py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {catalogue.map((m, idx) => {
                    const tier = m.tier || 'tier3_correct';
                    const status = m.status || 'info';
                    const statusColor = status === 'success' ? 'bg-green-100 text-green-700' :
                      status === 'warning' ? 'bg-amber-100 text-amber-700' :
                      status === 'danger' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-500';
                    return (
                      <tr key={m.key || idx} className="border-b last:border-0 hover:bg-muted/50">
                        <td className="py-2 pr-2">
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${TIER_COLORS[tier] || 'bg-gray-100 text-gray-700'}`}>
                            {TIER_LABELS[tier] || tier}
                          </span>
                        </td>
                        <td className="py-2 pr-4 font-medium">{m.label || m.name || m.key}</td>
                        <td className="py-2 pr-2">
                          {m.scor_code && <Badge variant="outline" className="text-[10px] font-mono">{m.scor_code}</Badge>}
                        </td>
                        <td className="py-2 pr-4 text-right font-mono">
                          {m.value != null ? (typeof m.value === 'number' ? m.value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : m.value) : '-'}
                          {m.unit && <span className="text-muted-foreground ml-1">{m.unit}</span>}
                        </td>
                        <td className="py-2 pr-4 text-right font-mono text-muted-foreground">
                          {m.target != null ? m.target : '-'}
                        </td>
                        <td className="py-2 pr-2">
                          {m.sparkline && <Sparkline data={m.sparkline} status={status} width={48} height={14} />}
                        </td>
                        <td className="py-2">
                          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${statusColor}`}>
                            {status}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};
export default KPIConfigurationAnalytics;
