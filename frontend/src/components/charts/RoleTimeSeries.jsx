/**
 * RoleTimeSeries — Compact time series dashboard for any user role.
 *
 * Renders 2-4 sparkline/area charts in a compact header bar based on
 * the role configuration. Each chart shows a key metric over time.
 *
 * Props:
 *   roleKey: string — key into ROLE_METRICS config
 *   configId: number — active supply chain config
 *   siteId: number (optional) — for site-specific roles
 *   compact: boolean — single row vs expanded layout
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';

// ── Role metric configurations ────────────────────────────────────────────

const ROLE_METRICS = {
  // ── Executive ────────────────────────────────────────────────────────
  executive: {
    label: 'Executive Dashboard',
    scope: 'network',        // span of control: entire network
    metrics: [
      { key: 'otif', label: 'OTIF %', color: '#10b981', unit: '%', target: 95, chart: 'area' },
      { key: 'fill_rate', label: 'Fill Rate %', color: '#3b82f6', unit: '%', target: 98, chart: 'area' },
      { key: 'inventory_value', label: 'Inventory $', color: '#f59e0b', unit: '$', chart: 'area' },
      { key: 'cost_to_serve', label: 'Cost/Order', color: '#ef4444', unit: '$', chart: 'line' },
    ],
  },

  // ── S&OP ─────────────────────────────────────────────────────────────
  sop: {
    label: 'S&OP Overview',
    scope: 'network',        // span of control: cross-functional network
    metrics: [
      { key: 'demand_supply_balance', label: 'Demand vs Supply', color: '#8b5cf6', unit: 'units', chart: 'area', dual: true },
      { key: 'forecast_accuracy', label: 'Forecast Accuracy', color: '#10b981', unit: '%', target: 85, chart: 'line' },
      { key: 'network_risk', label: 'Network Risk', color: '#ef4444', unit: '', chart: 'line', invert: true },
    ],
  },

  // ── Tactical Roles (network-wide, daily/weekly cadence) ────────────
  demand_planner: {
    label: 'Demand Planning',
    scope: 'network',        // demand planners see all demand nodes
    tabs: ['forecast', 'sensing', 'shaping', 'consensus', 'lifecycle', 'exceptions', 'collaboration'],
    metrics: [
      { key: 'forecast_vs_actual', label: 'Forecast vs Actual', color: '#3b82f6', unit: 'units', chart: 'area', dual: true },
      { key: 'mape', label: 'MAPE %', color: '#ef4444', unit: '%', chart: 'line', invert: true },
      { key: 'forecast_bias', label: 'Bias', color: '#f59e0b', unit: '%', chart: 'line', zeroline: true },
    ],
  },
  supply_planner: {
    label: 'Supply Planning',
    scope: 'network',        // supply planners see all supply nodes
    tabs: ['supply_plan', 'sourcing', 'netting', 'supplier_mgmt', 'worklist', 'collaboration'],
    metrics: [
      { key: 'supply_coverage', label: 'Coverage %', color: '#10b981', unit: '%', target: 100, chart: 'area' },
      { key: 'open_po_aging', label: 'Open PO Aging', color: '#f59e0b', unit: 'days', chart: 'bar' },
      { key: 'supplier_otd', label: 'Supplier OTD %', color: '#3b82f6', unit: '%', target: 95, chart: 'line' },
    ],
  },
  inventory_planner: {
    label: 'Inventory Planning',
    scope: 'network',        // inventory planners see all stocking locations
    tabs: ['positions', 'policies', 'segmentation', 'excess_obsolete', 'rebalancing', 'projections'],
    metrics: [
      { key: 'dos_by_site', label: 'Days of Supply', color: '#8b5cf6', unit: 'days', chart: 'area' },
      { key: 'inventory_turns', label: 'Turns', color: '#10b981', unit: 'x', chart: 'line' },
      { key: 'excess_obsolete', label: 'Excess & Obsolete', color: '#ef4444', unit: '$', chart: 'area', invert: true },
    ],
  },
  capacity_planner: {
    label: 'Capacity Planning',
    scope: 'network',        // capacity planners see all production/warehouse sites
    tabs: ['utilization', 'bottleneck', 'roughcut', 'scenario', 'workforce', 'maintenance'],
    metrics: [
      { key: 'utilization', label: 'Utilization %', color: '#3b82f6', unit: '%', target: 85, chart: 'area' },
      { key: 'bottleneck_hours', label: 'Bottleneck Hrs', color: '#ef4444', unit: 'hrs', chart: 'bar' },
      { key: 'planned_vs_actual', label: 'Plan vs Actual', color: '#10b981', unit: 'units', chart: 'area', dual: true },
    ],
  },
  forecast_analyst: {
    label: 'ML Forecast',
    scope: 'network',        // forecast analysts manage models network-wide
    tabs: ['pipeline', 'accuracy', 'feature_importance', 'drift', 'backtesting'],
    metrics: [
      { key: 'crps', label: 'CRPS Score', color: '#8b5cf6', unit: '', chart: 'line', invert: true },
      { key: 'pipeline_runs', label: 'Pipeline Runs', color: '#3b82f6', unit: '', chart: 'bar' },
      { key: 'feature_drift', label: 'Feature Drift', color: '#f59e0b', unit: '', chart: 'line', invert: true },
    ],
  },

  // ── Operational (site-level, hourly cadence) ───────────────────────
  site_coordinator: {
    label: 'Site Coordination',
    scope: 'site',           // site coordinator manages one site
    metrics: [
      { key: 'decision_throughput', label: 'Decisions/Hr', color: '#3b82f6', unit: '/hr', chart: 'area' },
      { key: 'urgency_heatmap', label: 'Avg Urgency', color: '#ef4444', unit: '', chart: 'line' },
      { key: 'escalation_rate', label: 'Escalation %', color: '#f59e0b', unit: '%', chart: 'line', invert: true },
    ],
  },

  // ── Execution Roles (site-specific, per-decision) ──────────────────
  atp_executor: {
    label: 'ATP',
    scope: 'site',           // ATP decisions are site-specific
    metrics: [
      { key: 'atp_qty', label: 'ATP Qty', color: '#10b981', unit: 'units', chart: 'area' },
      { key: 'fill_rate', label: 'Fill Rate %', color: '#3b82f6', unit: '%', target: 98, chart: 'line' },
      { key: 'order_backlog', label: 'Backlog', color: '#ef4444', unit: 'orders', chart: 'bar', invert: true },
    ],
  },
  po_creation: {
    label: 'PO Creation',
    scope: 'site',
    metrics: [
      { key: 'open_pos', label: 'Open POs', color: '#3b82f6', unit: '', chart: 'area' },
      { key: 'days_until_stockout', label: 'Days to Stockout', color: '#ef4444', unit: 'days', chart: 'line', invert: true },
      { key: 'supplier_lead_time', label: 'Supplier LT', color: '#f59e0b', unit: 'days', chart: 'line' },
    ],
  },
  mo_execution: {
    label: 'MO Execution',
    scope: 'site',
    metrics: [
      { key: 'wip_level', label: 'WIP Level', color: '#8b5cf6', unit: 'units', chart: 'area' },
      { key: 'capacity_util', label: 'Capacity %', color: '#3b82f6', unit: '%', target: 85, chart: 'area' },
      { key: 'production_backlog', label: 'Backlog', color: '#ef4444', unit: 'units', chart: 'bar', invert: true },
    ],
  },
  to_execution: {
    label: 'TO Execution',
    scope: 'site',
    metrics: [
      { key: 'in_transit', label: 'In Transit', color: '#3b82f6', unit: 'units', chart: 'area' },
      { key: 'transfer_lt', label: 'Transfer LT', color: '#f59e0b', unit: 'days', chart: 'line' },
      { key: 'on_time_transfer', label: 'On Time %', color: '#10b981', unit: '%', target: 95, chart: 'line' },
    ],
  },
  rebalancing: {
    label: 'Rebalancing',
    scope: 'site',
    metrics: [
      { key: 'inventory_imbalance', label: 'Imbalance Index', color: '#ef4444', unit: '', chart: 'line', invert: true },
      { key: 'surplus_sites', label: 'Surplus Sites', color: '#f59e0b', unit: '', chart: 'bar' },
      { key: 'deficit_sites', label: 'Deficit Sites', color: '#ef4444', unit: '', chart: 'bar', invert: true },
    ],
  },
  inventory_buffer: {
    label: 'Buffer Adjustment',
    scope: 'site',
    metrics: [
      { key: 'ss_compliance', label: 'SS Compliance %', color: '#10b981', unit: '%', target: 95, chart: 'area' },
      { key: 'dos_trend', label: 'Days of Supply', color: '#3b82f6', unit: 'days', chart: 'line' },
      { key: 'below_ss_count', label: 'Below SS Count', color: '#ef4444', unit: '', chart: 'bar', invert: true },
    ],
  },
  order_tracking: {
    label: 'Order Tracking',
    scope: 'site',
    metrics: [
      { key: 'orders_past_due', label: 'Past Due', color: '#ef4444', unit: '', chart: 'bar', invert: true },
      { key: 'exception_trend', label: 'Exceptions', color: '#f59e0b', unit: '', chart: 'line', invert: true },
      { key: 'on_time_delivery', label: 'OTD %', color: '#10b981', unit: '%', target: 95, chart: 'line' },
    ],
  },
  quality_disposition: {
    label: 'Quality',
    scope: 'site',
    metrics: [
      { key: 'defect_rate', label: 'Defect Rate %', color: '#ef4444', unit: '%', chart: 'line', invert: true },
      { key: 'hold_qty', label: 'On Hold Qty', color: '#f59e0b', unit: 'units', chart: 'bar' },
      { key: 'inspection_pass', label: 'Pass Rate %', color: '#10b981', unit: '%', target: 98, chart: 'area' },
    ],
  },
  maintenance_scheduling: {
    label: 'Maintenance',
    scope: 'site',
    metrics: [
      { key: 'downtime_pct', label: 'Downtime %', color: '#ef4444', unit: '%', chart: 'line', invert: true },
      { key: 'scheduled_vs_unplanned', label: 'Sched vs Unplanned', color: '#3b82f6', unit: '', chart: 'bar', dual: true },
      { key: 'asset_availability', label: 'Availability %', color: '#10b981', unit: '%', target: 92, chart: 'area' },
    ],
  },
  subcontracting: {
    label: 'Subcontracting',
    scope: 'site',
    metrics: [
      { key: 'make_vs_buy_ratio', label: 'Make vs Buy %', color: '#8b5cf6', unit: '%', chart: 'area' },
      { key: 'external_capacity', label: 'External Capacity', color: '#3b82f6', unit: 'units', chart: 'bar' },
      { key: 'subcon_cost_trend', label: 'Cost Trend', color: '#f59e0b', unit: '$', chart: 'line' },
    ],
  },
  forecast_adjustment: {
    label: 'Forecast Adjustment',
    scope: 'site',
    metrics: [
      { key: 'forecast_error', label: 'Forecast Error %', color: '#ef4444', unit: '%', chart: 'line', invert: true },
      { key: 'signal_count', label: 'Demand Signals', color: '#3b82f6', unit: '', chart: 'bar' },
      { key: 'adjustment_impact', label: 'Adjustment Impact', color: '#10b981', unit: 'units', chart: 'area' },
    ],
  },
};

// ── Synthetic data generator (until real API is wired) ─────────────────

function generateMetricData(metricKey, periods = 12) {
  const data = [];
  const now = new Date();
  let base = 50 + Math.random() * 40;

  for (let i = periods - 1; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i * 7);
    const noise = (Math.random() - 0.5) * base * 0.15;
    base = Math.max(5, base + noise * 0.3);
    data.push({
      date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      value: Math.round(base * 10) / 10,
      value2: metricKey.includes('vs') ? Math.round((base * (0.85 + Math.random() * 0.3)) * 10) / 10 : undefined,
    });
  }
  return data;
}

// ── Mini chart component ──────────────────────────────────────────────

const MiniChart = ({ metric, data, height = 48 }) => {
  const ChartComponent = metric.chart === 'bar' ? BarChart : metric.chart === 'area' ? AreaChart : LineChart;
  const DataComponent = metric.chart === 'bar' ? Bar : metric.chart === 'area' ? Area : Line;

  return (
    <div className="flex-1 min-w-[140px]">
      <div className="flex items-baseline justify-between mb-0.5 px-1">
        <span className="text-[10px] font-medium text-muted-foreground">{metric.label}</span>
        {data.length > 0 && (
          <span className="text-xs font-semibold tabular-nums" style={{ color: metric.color }}>
            {data[data.length - 1]?.value}{metric.unit}
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <ChartComponent data={data} margin={{ top: 2, right: 2, bottom: 0, left: 2 }}>
          {metric.target && (
            <Line type="monotone" dataKey={() => metric.target} stroke="#d1d5db" strokeWidth={1} strokeDasharray="3 3" dot={false} />
          )}
          {metric.chart === 'area' ? (
            <Area type="monotone" dataKey="value" stroke={metric.color} fill={metric.color} fillOpacity={0.15} strokeWidth={1.5} dot={false} />
          ) : metric.chart === 'bar' ? (
            <Bar dataKey="value" fill={metric.color} fillOpacity={0.6} radius={[2, 2, 0, 0]} />
          ) : (
            <Line type="monotone" dataKey="value" stroke={metric.color} strokeWidth={1.5} dot={false} />
          )}
          {metric.dual && (
            <Line type="monotone" dataKey="value2" stroke={metric.color} strokeWidth={1} strokeDasharray="4 2" dot={false} opacity={0.5} />
          )}
          <Tooltip
            contentStyle={{ fontSize: 10, padding: '4px 8px', borderRadius: 6 }}
            formatter={(v) => [`${v}${metric.unit}`, metric.label]}
            labelFormatter={(l) => l}
          />
        </ChartComponent>
      </ResponsiveContainer>
    </div>
  );
};

// ── Main component ────────────────────────────────────────────────────

const RoleTimeSeries = ({ roleKey, configId, siteId, compact = true, className }) => {
  const config = ROLE_METRICS[roleKey];
  const [metricData, setMetricData] = useState({});

  useEffect(() => {
    if (!config) return;
    // TODO: Replace with real API call:
    // api.get(`/role-metrics/${roleKey}`, { params: { config_id: configId, site_id: siteId } })
    const data = {};
    config.metrics.forEach(m => {
      data[m.key] = generateMetricData(m.key);
    });
    setMetricData(data);
  }, [roleKey, configId, siteId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!config) return null;

  return (
    <div className={cn(
      'flex gap-3 p-2.5 rounded-lg border border-border/50 bg-muted/20',
      compact ? 'flex-row flex-wrap' : 'flex-col',
      className,
    )}>
      {config.metrics.map(metric => (
        <MiniChart
          key={metric.key}
          metric={metric}
          data={metricData[metric.key] || []}
          height={compact ? 44 : 64}
        />
      ))}
    </div>
  );
};

export { ROLE_METRICS };
export default RoleTimeSeries;
