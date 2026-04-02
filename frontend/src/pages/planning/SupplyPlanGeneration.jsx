/**
 * Supply Plan View — Shows the agent-generated Plan of Record.
 *
 * No manual generation — the plan is created automatically during provisioning
 * from conformal-calibrated forecast P50. Uncertainty is quantified by
 * conformal P10/P90 intervals, NOT Monte Carlo simulation.
 *
 * Users inspect the plan and override via Decision Stream.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, CardContent, Badge, Button, Alert,
  Tabs, TabsList, TabsTrigger, TabsContent,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '../../components/common';
import {
  Clock, RefreshCw, Package, TrendingUp,
} from 'lucide-react';
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import ScenarioPanel from '../../components/planning/ScenarioPanel';
import ERPComparisonPanel from '../../components/planning/ERPComparisonPanel';

export default function SupplyPlanGeneration() {
  const { effectiveConfigId } = useActiveConfig();
  const [planData, setPlanData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [timeBucket, setTimeBucket] = useState('week');
  const [tab, setTab] = useState('plan');
  const cfgId = effectiveConfigId || 129;

  const loadPlan = useCallback(async () => {
    if (!cfgId) return;
    setLoading(true);
    try {
      const res = await api.get('/demand-plan/aggregated', {
        params: { config_id: cfgId, time_bucket: timeBucket },
      });
      setPlanData(res.data);
    } catch (err) {
      console.error('Failed to load plan:', err);
    } finally {
      setLoading(false);
    }
  }, [cfgId, timeBucket]);

  useEffect(() => { loadPlan(); }, [loadPlan]);

  const series = planData?.series || [];
  const summary = planData?.summary || {};

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-2">
          <Package className="h-7 w-7 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">Supply Plan</h1>
            <p className="text-sm text-muted-foreground">
              Plan of Record — generated from conformal-calibrated forecasts (P50)
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="success" className="text-xs">
            <TrendingUp className="h-3 w-3 mr-1" />
            Conformal P10/P50/P90
          </Badge>
          <select className="border rounded px-2 py-1.5 text-sm"
            value={timeBucket} onChange={e => setTimeBucket(e.target.value)}>
            <option value="day">Daily</option>
            <option value="week">Weekly</option>
            <option value="month">Monthly</option>
          </select>
          <Button variant="outline" onClick={loadPlan} disabled={loading}
            leftIcon={<RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />}>
            Refresh
          </Button>
        </div>
      </div>

      <ScenarioPanel className="mb-4" />
      <ERPComparisonPanel className="mb-4" />

      {/* Summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Plan Records</p>
            <p className="text-2xl font-bold">{summary.total_records?.toLocaleString() || '—'}</p>
            <p className="text-xs text-muted-foreground">Plan of Record (live)</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Products</p>
            <p className="text-2xl font-bold">{summary.total_products || '—'}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Sites</p>
            <p className="text-2xl font-bold">{summary.total_sites || '—'}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Uncertainty Method</p>
            <p className="text-lg font-bold text-green-600">Conformal Prediction</p>
            <p className="text-xs text-muted-foreground">Not Monte Carlo</p>
          </CardContent>
        </Card>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="plan">Plan View</TabsTrigger>
          <TabsTrigger value="directives">Agent Directives</TabsTrigger>
          <TabsTrigger value="sourcing">Sourcing</TabsTrigger>
          <TabsTrigger value="netting">Net Requirements</TabsTrigger>
          <TabsTrigger value="capacity">Capacity Check</TabsTrigger>
        </TabsList>

        <TabsContent value="plan">
          {/* Confidence band chart */}
          {series.length > 0 && (
            <Card className="mb-4">
              <CardContent className="pt-4">
                <h3 className="text-sm font-semibold mb-2">
                  Supply Plan — Conformal Prediction Intervals
                </h3>
                <ResponsiveContainer width="100%" height={300}>
                  <ComposedChart data={series}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip contentStyle={{ fontSize: 11 }} />
                    <Legend wrapperStyle={{ fontSize: 10 }} />
                    <Area type="monotone" dataKey="p90" stroke="none" fill="#8884d8" fillOpacity={0.12} name="P90 (High)" />
                    <Area type="monotone" dataKey="p10" stroke="none" fill="#ffffff" fillOpacity={1} name="P10 (Low)" />
                    <Line type="monotone" dataKey="p50" stroke="#6366f1" strokeWidth={2.5} name="Plan of Record (P50)" dot={false} />
                    <Line type="monotone" dataKey="p10" stroke="#86efac" strokeWidth={1} strokeDasharray="4 3" name="P10" dot={false} />
                    <Line type="monotone" dataKey="p90" stroke="#fbbf24" strokeWidth={1} strokeDasharray="4 3" name="P90" dot={false} />
                    {series[0]?.actual != null && (
                      <Line type="monotone" dataKey="actual" stroke="#ef4444" strokeWidth={2} name="Actual" dot={{ r: 2 }} connectNulls={false} />
                    )}
                  </ComposedChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Time-phased grid */}
          {series.length > 0 && (
            <Card>
              <CardContent className="pt-4">
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="sticky left-0 bg-white">Period</TableHead>
                        <TableHead className="text-right">P10</TableHead>
                        <TableHead className="text-right font-bold">P50 (Plan)</TableHead>
                        <TableHead className="text-right">P90</TableHead>
                        <TableHead className="text-right">Actual</TableHead>
                        <TableHead className="text-right">Products</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {series.slice(0, 52).map(row => (
                        <TableRow key={row.date}>
                          <TableCell className="sticky left-0 bg-white font-mono text-xs">{row.date}</TableCell>
                          <TableCell className="text-right text-muted-foreground">{row.p10?.toLocaleString()}</TableCell>
                          <TableCell className="text-right font-bold">{row.p50?.toLocaleString()}</TableCell>
                          <TableCell className="text-right text-muted-foreground">{row.p90?.toLocaleString()}</TableCell>
                          <TableCell className="text-right text-red-600">{row.actual?.toLocaleString() || '—'}</TableCell>
                          <TableCell className="text-right text-xs">{row.products}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          )}

          {series.length === 0 && !loading && (
            <Alert className="mt-4">
              No plan data. The plan is generated automatically during provisioning from conformal P50 forecasts.
            </Alert>
          )}
        </TabsContent>

        <TabsContent value="directives">
          <Alert className="mt-4">
            Agent directives — tactical GNN allocation and rebalancing recommendations.
            View and override in the Decision Stream.
          </Alert>
        </TabsContent>

        <TabsContent value="sourcing">
          <Alert className="mt-4">
            Sourcing rules — vendor selection and allocation by product.
            These are scenario parameters that can be tested via What-If scenarios.
          </Alert>
        </TabsContent>

        <TabsContent value="netting">
          <Alert className="mt-4">
            Net requirements — gross demand minus on-hand minus on-order = net requirement.
            Calculated from the Plan of Record and current inventory position.
          </Alert>
        </TabsContent>

        <TabsContent value="capacity">
          <Alert className="mt-4">
            RCCP capacity check — validates the plan against resource constraints.
            Populated during the RCCP validation provisioning step.
          </Alert>
        </TabsContent>
      </Tabs>
    </div>
  );
}
