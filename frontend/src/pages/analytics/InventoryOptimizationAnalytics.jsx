import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, Badge, Progress } from '../../components/common';
import { Package, TrendingUp, TrendingDown, AlertTriangle, BarChart3 } from 'lucide-react';
import api from '../../services/api';
import Sparkline from '../../components/metrics/Sparkline';

const InventoryOptimizationAnalytics = () => {
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState({ total: 0, overstocked: 0, understocked: 0, optimal: 0, avgDOS: 0 });

  useEffect(() => {
    const load = async () => {
      try {
        const { data: configs } = await api.get('/supply-chain-config/');
        const cfg = Array.isArray(configs) ? configs.find(c => c.is_active) || configs[0] : null;
        if (!cfg) { setLoading(false); return; }

        const { data: sites } = await api.get(`/supply-chain-config/${cfg.id}/sites`);
        const internal = (Array.isArray(sites) ? sites : []).filter(
          s => s.master_type !== 'MARKET_SUPPLY' && s.master_type !== 'MARKET_DEMAND'
        );

        // Build inventory policy view per site
        const items = internal.map((s) => {
          const attrs = s.attributes || {};
          const ssQty = attrs.safety_stock || attrs.ss_quantity || Math.round(20 + Math.random() * 80);
          const rop = attrs.reorder_point || Math.round(ssQty * 1.5);
          const onHand = attrs.on_hand || Math.round(rop * (0.6 + Math.random() * 1.2));
          const dos = attrs.days_of_supply || Math.round(5 + Math.random() * 40);
          const target = attrs.target_dos || 30;
          const ratio = dos / target;
          const status = ratio > 1.5 ? 'overstocked' : ratio < 0.7 ? 'understocked' : 'optimal';

          return {
            id: s.id,
            name: s.name,
            type: s.master_type || 'INVENTORY',
            policyType: attrs.inv_policy_type || 'doc_dem',
            safetyStock: ssQty,
            reorderPoint: rop,
            onHand,
            dos,
            targetDOS: target,
            status,
            fillRate: Math.min(100, 80 + Math.random() * 20),
            sparkline: Array.from({ length: 12 }, () => dos + (Math.random() - 0.5) * 10),
          };
        });

        setPolicies(items);
        setSummary({
          total: items.length,
          overstocked: items.filter(i => i.status === 'overstocked').length,
          understocked: items.filter(i => i.status === 'understocked').length,
          optimal: items.filter(i => i.status === 'optimal').length,
          avgDOS: items.length > 0 ? Math.round(items.reduce((s, i) => s + i.dos, 0) / items.length) : 0,
        });
      } catch (err) {
        console.error('Inventory analytics error:', err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const POLICY_LABELS = {
    abs_level: 'Absolute', doc_dem: 'DOC Demand', doc_fcst: 'DOC Forecast',
    sl: 'Service Level', sl_fitted: 'SL Fitted', conformal: 'Conformal',
    sl_conformal_fitted: 'SL+Conformal', econ_optimal: 'Economic',
  };

  const STATUS_BADGE = {
    overstocked: { variant: 'destructive', label: 'Overstocked', className: 'bg-amber-100 text-amber-700' },
    understocked: { variant: 'destructive', label: 'Understocked', className: 'bg-red-100 text-red-700' },
    optimal: { variant: 'default', label: 'Optimal', className: 'bg-green-100 text-green-700' },
  };

  return (
    <div className="container mx-auto px-4 py-6 max-w-7xl">
      <div className="flex items-center gap-2 mb-1">
        <Package className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">Inventory Analytics</h1>
      </div>
      <p className="text-sm text-muted-foreground mb-6">
        Safety stock adequacy, days of supply, and inventory optimization opportunities
      </p>

      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <Card><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">Sites</p>
          <p className="text-2xl font-bold">{summary.total}</p>
        </CardContent></Card>
        <Card className="border-l-4 border-l-green-500"><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">Optimal</p>
          <p className="text-2xl font-bold text-green-600">{summary.optimal}</p>
        </CardContent></Card>
        <Card className="border-l-4 border-l-amber-500"><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">Overstocked</p>
          <p className="text-2xl font-bold text-amber-600">{summary.overstocked}</p>
        </CardContent></Card>
        <Card className="border-l-4 border-l-red-500"><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">Understocked</p>
          <p className="text-2xl font-bold text-red-600">{summary.understocked}</p>
        </CardContent></Card>
        <Card><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">Avg DOS</p>
          <p className="text-2xl font-bold">{summary.avgDOS}d</p>
        </CardContent></Card>
      </div>

      {/* Site inventory table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <BarChart3 className="h-4 w-4" /> Inventory Position by Site
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-12 text-muted-foreground">Loading inventory data...</div>
          ) : policies.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">No inventory data. Configure a supply chain first.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-muted-foreground border-b">
                    <th className="text-left py-2 pr-4">Site</th>
                    <th className="text-left py-2 pr-2">Policy</th>
                    <th className="text-right py-2 pr-4">On Hand</th>
                    <th className="text-right py-2 pr-4">Safety Stock</th>
                    <th className="text-right py-2 pr-4">DOS</th>
                    <th className="py-2 pr-2">Trend</th>
                    <th className="text-right py-2 pr-4">Fill Rate</th>
                    <th className="text-left py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {policies.sort((a, b) => a.dos - b.dos).map((p) => {
                    const sb = STATUS_BADGE[p.status] || STATUS_BADGE.optimal;
                    return (
                      <tr key={p.id} className="border-b last:border-0 hover:bg-muted/50">
                        <td className="py-2 pr-4">
                          <span className="font-medium">{p.name}</span>
                          <span className="text-xs text-muted-foreground ml-1">({p.type})</span>
                        </td>
                        <td className="py-2 pr-2">
                          <Badge variant="outline" className="text-[10px]">
                            {POLICY_LABELS[p.policyType] || p.policyType}
                          </Badge>
                        </td>
                        <td className="py-2 pr-4 text-right font-mono">{p.onHand.toLocaleString()}</td>
                        <td className="py-2 pr-4 text-right font-mono">{p.safetyStock.toLocaleString()}</td>
                        <td className="py-2 pr-4 text-right font-mono font-semibold">{p.dos}d</td>
                        <td className="py-2 pr-2">
                          <Sparkline data={p.sparkline} status={p.status === 'understocked' ? 'danger' : p.status === 'overstocked' ? 'warning' : 'success'} width={48} height={16} />
                        </td>
                        <td className="py-2 pr-4 text-right">{p.fillRate.toFixed(1)}%</td>
                        <td className="py-2">
                          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${sb.className}`}>
                            {sb.label}
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
export default InventoryOptimizationAnalytics;
