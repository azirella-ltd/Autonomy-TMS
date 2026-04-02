/**
 * ERP vs Autonomy Plan Comparison Panel
 *
 * Shows side-by-side KPIs: ERP baseline plan vs AI-generated Plan of Record.
 * Demonstrates the value the AI plan provides.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, CardContent, Badge, Button,
} from '../common';
import { GitCompare, TrendingUp, TrendingDown, Minus, RefreshCw } from 'lucide-react';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import { cn } from '../../lib/utils/cn';

const DeltaIndicator = ({ delta_pct, inverse = false }) => {
  if (!delta_pct || delta_pct === 0) return <Minus className="h-4 w-4 text-muted-foreground" />;
  const isPositive = inverse ? delta_pct < 0 : delta_pct > 0;
  return isPositive
    ? <TrendingUp className="h-4 w-4 text-green-600" />
    : <TrendingDown className="h-4 w-4 text-red-600" />;
};

const METRIC_CONFIG = [
  { key: 'total_orders', label: 'Total Orders', format: 'int', description: 'Number of planned orders' },
  { key: 'total_planned_qty', label: 'Total Planned Qty', format: 'int', description: 'Sum of all planned quantities' },
  { key: 'avg_order_qty', label: 'Avg Order Size', format: 'decimal', description: 'Average order quantity', inverse: true },
  { key: 'periods', label: 'Planning Periods', format: 'int', description: 'Number of weekly buckets covered' },
  { key: 'products', label: 'Products', format: 'int', description: 'Distinct products planned' },
];

export default function ERPComparisonPanel({ className }) {
  const { effectiveConfigId } = useActiveConfig();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const cfgId = effectiveConfigId || 129;

  const load = useCallback(async () => {
    if (!cfgId) return;
    setLoading(true);
    try {
      const res = await api.get('/scenario-planning/erp-comparison', { params: { config_id: cfgId } });
      setData(res.data);
    } catch (err) {
      console.error('ERP comparison failed:', err);
    } finally {
      setLoading(false);
    }
  }, [cfgId]);

  useEffect(() => { load(); }, [load]);

  if (!data?.erp_baseline || !data?.autonomy_plan) {
    return null; // Don't show panel if no comparison data
  }

  const comp = data.comparison || {};

  return (
    <Card className={cn("border-blue-200 bg-blue-50/30", className)}>
      <CardContent className="pt-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <GitCompare className="h-5 w-5 text-blue-600" />
            <h3 className="font-semibold">ERP Plan vs Autonomy AI Plan</h3>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs border-amber-300 text-amber-700 bg-amber-50">
              ERP Baseline: {data.erp_baseline.total_orders} orders
            </Badge>
            <Badge variant="outline" className="text-xs border-blue-300 text-blue-700 bg-blue-50">
              Autonomy: {data.autonomy_plan.total_orders} orders
            </Badge>
            <Button variant="ghost" size="sm" className="h-6" onClick={load} disabled={loading}>
              <RefreshCw className={cn("h-3 w-3", loading && "animate-spin")} />
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-5 gap-3">
          {METRIC_CONFIG.map(({ key, label, format, description, inverse }) => {
            const d = comp[key];
            if (!d) return null;
            const fmt = (v) => format === 'int' ? Math.round(v).toLocaleString() : v?.toLocaleString(undefined, { maximumFractionDigits: 1 });

            return (
              <div key={key} className="bg-white rounded-lg border p-3">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{label}</p>
                <div className="grid grid-cols-2 gap-1 text-sm mb-1">
                  <div>
                    <span className="text-[10px] text-amber-600">ERP</span>
                    <p className="font-medium">{fmt(d.erp)}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-blue-600">AI</span>
                    <p className="font-bold">{fmt(d.autonomy)}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <DeltaIndicator delta_pct={d.delta_pct} inverse={inverse} />
                  <span className={cn(
                    "text-xs font-medium",
                    d.delta_pct > 0 ? (inverse ? "text-red-600" : "text-green-600") :
                    d.delta_pct < 0 ? (inverse ? "text-green-600" : "text-red-600") :
                    "text-muted-foreground"
                  )}>
                    {d.delta_pct > 0 ? '+' : ''}{d.delta_pct}%
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Inventory position */}
        {comp.avg_inventory && (
          <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
            <span>Current Avg Inventory: <strong>{Math.round(comp.avg_inventory).toLocaleString()}</strong></span>
            <span>DOS Ratio: <strong>{comp.dos_ratio}</strong></span>
            <span>Total Inventory: <strong>{Math.round(comp.total_inventory).toLocaleString()}</strong></span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
