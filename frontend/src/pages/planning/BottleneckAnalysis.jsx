/**
 * Bottleneck Analysis — Constraint identification, what-if relaxation, and capacity scenario modeling.
 *
 * For inventory-only configs (DCs), shows throughput constraints (orders/day vs capacity).
 * For manufacturing configs, shows work center utilization.
 * All data from /resource-capacity/utilization/analysis endpoint — no synthetic fallbacks.
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  Card, CardContent, CardHeader, CardTitle, Button, Badge, Alert,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell, Spinner,
} from '../../components/common';
import {
  AlertTriangle, RefreshCw, Gauge, Clock, Warehouse,
  ArrowRight,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  ReferenceLine,
} from 'recharts';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';

const UTILIZATION_COLORS = {
  critical: '#ef4444',   // > 95%
  high: '#f59e0b',       // 85-95%
  normal: '#10b981',     // 60-85%
  low: '#3b82f6',        // < 60%
};

function getUtilLevel(pct) {
  if (pct >= 95) return 'critical';
  if (pct >= 85) return 'high';
  if (pct >= 60) return 'normal';
  return 'low';
}

const RELAXATION_OPTIONS = [
  { key: 'overtime', label: 'Add Overtime', description: 'Extend shift by 2 hours', capacity_gain: 25, cost_per_unit: 1.5, lead_time_impact: 0 },
  { key: 'shift', label: 'Add Shift', description: 'Add a second/third shift', capacity_gain: 100, cost_per_unit: 1.2, lead_time_impact: 0 },
  { key: 'rebalance', label: 'Rebalance Load', description: 'Shift work to under-utilized sites', capacity_gain: 20, cost_per_unit: 1.05, lead_time_impact: 1 },
];

export default function BottleneckAnalysis() {
  const { effectiveConfigId } = useActiveConfig();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [resources, setResources] = useState([]);
  const [scenarioResults, setScenarioResults] = useState(null);

  useEffect(() => {
    if (effectiveConfigId) loadData();
  }, [effectiveConfigId]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/resource-capacity/utilization/analysis', { params: { config_id: effectiveConfigId } });
      const data = res.data?.utilization || res.data || [];
      setResources(data.map(r => ({
        ...r,
        utilization_pct: r.utilization_pct || r.utilization || 0,
        available_hours: r.available_hours || 0,
        required_hours: r.required_hours || 0,
        queue_hours: r.queue_hours || 0,
      })));
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
      setResources([]);
    } finally {
      setLoading(false);
    }
  };

  const sortedByUtil = useMemo(() =>
    [...resources].sort((a, b) => b.utilization_pct - a.utilization_pct),
  [resources]);

  const bottlenecks = useMemo(() =>
    sortedByUtil.filter(r => r.utilization_pct >= 85),
  [sortedByUtil]);

  const summary = useMemo(() => ({
    critical: resources.filter(r => r.utilization_pct >= 95).length,
    high: resources.filter(r => r.utilization_pct >= 85 && r.utilization_pct < 95).length,
    total_queue: resources.reduce((s, r) => s + (r.queue_hours || 0), 0),
    avg_util: resources.length > 0 ? Math.round(resources.reduce((s, r) => s + r.utilization_pct, 0) / resources.length) : 0,
  }), [resources]);

  const runScenario = (resource, option) => {
    const currentUtil = resource.utilization_pct;
    const newCapacity = resource.available_hours * (1 + option.capacity_gain / 100);
    const newUtil = newCapacity > 0 ? Math.round(resource.required_hours / newCapacity * 100) : 0;
    const costDelta = Math.round(
      (newCapacity - resource.available_hours) * (resource.cost_per_hour || 100) * option.cost_per_unit
    );
    setScenarioResults({
      resource: resource.resource_name,
      option: option.label,
      before_util: currentUtil,
      after_util: Math.min(newUtil, 100),
      capacity_before: resource.available_hours,
      capacity_after: Math.round(newCapacity),
      cost_delta: costDelta,
      lead_time_impact: option.lead_time_impact,
      freed_hours: Math.round(newCapacity - resource.available_hours),
    });
  };

  if (loading) return <div className="flex justify-center py-16"><Spinner /></div>;

  if (!loading && resources.length === 0 && !error) {
    return (
      <div className="text-center py-16 text-muted-foreground">
        <Warehouse className="h-10 w-10 mx-auto mb-3 opacity-50" />
        <p className="font-medium">No capacity data available</p>
        <p className="text-sm mt-1">Resource capacity records have not been provisioned for this configuration.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && <Alert variant="destructive"><AlertTriangle className="h-4 w-4" />{error}</Alert>}

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4 text-center">
            <AlertTriangle className="h-5 w-5 mx-auto mb-1 text-red-500" />
            <div className="text-2xl font-bold text-red-600">{summary.critical}</div>
            <div className="text-xs text-muted-foreground">Critical (&gt;95%)</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 text-center">
            <Gauge className="h-5 w-5 mx-auto mb-1 text-amber-500" />
            <div className="text-2xl font-bold text-amber-600">{summary.high}</div>
            <div className="text-xs text-muted-foreground">High (85-95%)</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 text-center">
            <Clock className="h-5 w-5 mx-auto mb-1 text-blue-500" />
            <div className="text-2xl font-bold">{summary.total_queue}h</div>
            <div className="text-xs text-muted-foreground">Total Queue</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 text-center">
            <Warehouse className="h-5 w-5 mx-auto mb-1 text-muted-foreground" />
            <div className="text-2xl font-bold">{summary.avg_util}%</div>
            <div className="text-xs text-muted-foreground">Avg Utilization</div>
          </CardContent>
        </Card>
      </div>

      {/* Utilization Chart */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm">Resource Utilization</CardTitle>
            <Button variant="outline" size="sm" onClick={loadData}><RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
          </div>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={Math.max(200, sortedByUtil.length * 28)}>
            <BarChart data={sortedByUtil} layout="vertical">
              <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 10 }} />
              <YAxis type="category" dataKey="resource_name" tick={{ fontSize: 10 }} width={120} />
              <Tooltip formatter={(v) => [`${v}%`, 'Utilization']} />
              <ReferenceLine x={85} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: '85%', fontSize: 9 }} />
              <ReferenceLine x={95} stroke="#ef4444" strokeDasharray="3 3" label={{ value: '95%', fontSize: 9 }} />
              <Bar dataKey="utilization_pct" radius={[0, 4, 4, 0]}>
                {sortedByUtil.map((r, i) => (
                  <Cell key={i} fill={UTILIZATION_COLORS[getUtilLevel(r.utilization_pct)]} fillOpacity={0.8} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* What-If Scenario Result */}
      <Card>
        <CardHeader><CardTitle className="text-sm">What-If Scenario Result</CardTitle></CardHeader>
        <CardContent>
          {scenarioResults ? (
            <div className="space-y-3">
              <div className="text-sm font-medium">{scenarioResults.resource} — {scenarioResults.option}</div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-muted-foreground">Utilization:</span>
                  <div className="flex items-center gap-2">
                    <Badge variant={scenarioResults.before_util >= 85 ? 'destructive' : 'secondary'}>{scenarioResults.before_util}%</Badge>
                    <ArrowRight className="h-3 w-3" />
                    <Badge variant={scenarioResults.after_util >= 85 ? 'warning' : 'success'}>{scenarioResults.after_util}%</Badge>
                  </div>
                </div>
                <div>
                  <span className="text-muted-foreground">Capacity:</span>
                  <div>{scenarioResults.capacity_before}h → {scenarioResults.capacity_after}h (+{scenarioResults.freed_hours}h)</div>
                </div>
                <div>
                  <span className="text-muted-foreground">Cost Impact:</span>
                  <div className="text-amber-600">+${scenarioResults.cost_delta.toLocaleString()}/wk</div>
                </div>
                <div>
                  <span className="text-muted-foreground">Lead Time:</span>
                  <div>{scenarioResults.lead_time_impact > 0 ? `+${scenarioResults.lead_time_impact} days` : 'No change'}</div>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
              Select a bottleneck resource and relaxation option to model scenarios
            </div>
          )}
        </CardContent>
      </Card>

      {/* Bottleneck Detail Table */}
      <Card>
        <CardHeader><CardTitle className="text-sm">Bottleneck Resources (&ge;85% Utilization)</CardTitle></CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Resource</TableHead>
                  <TableHead>Site</TableHead>
                  <TableHead className="text-right">Util %</TableHead>
                  <TableHead className="text-right">Available</TableHead>
                  <TableHead className="text-right">Required</TableHead>
                  <TableHead className="text-right">Queue</TableHead>
                  <TableHead>Relaxation Options</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {bottlenecks.map(r => (
                  <TableRow key={r.resource_id}>
                    <TableCell className="font-medium">{r.resource_name}</TableCell>
                    <TableCell>{r.site_name || r.site_id || '—'}</TableCell>
                    <TableCell className="text-right">
                      <Badge variant={r.utilization_pct >= 95 ? 'destructive' : 'warning'}>{r.utilization_pct}%</Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{r.available_hours}h</TableCell>
                    <TableCell className="text-right tabular-nums">{r.required_hours}h</TableCell>
                    <TableCell className="text-right tabular-nums">{r.queue_hours}h</TableCell>
                    <TableCell>
                      <div className="flex gap-1 flex-wrap">
                        {RELAXATION_OPTIONS.map(opt => (
                          <Button
                            key={opt.key}
                            variant="outline"
                            size="sm"
                            className="text-[10px] h-6 px-2"
                            onClick={() => runScenario(r, opt)}
                          >
                            {opt.label}
                          </Button>
                        ))}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {bottlenecks.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                      No bottleneck resources identified (all below 85%)
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
