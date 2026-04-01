/**
 * Master Production Scheduling — Agent-generated plan view.
 *
 * Shows the auto-generated supply plan in a time-phased grid.
 * No "Create" button — the agent generates the plan during provisioning.
 * Users inspect the plan and can override specific lines via Decision Stream.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, CardContent, Badge, Button, Alert,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  Tabs, TabsList, TabsTrigger, TabsContent,
} from '../components/common';
import { Calendar, RefreshCw } from 'lucide-react';
import { api } from '../services/api';
import { useActiveConfig } from '../contexts/ActiveConfigContext';
import ScenarioPanel from '../components/planning/ScenarioPanel';

export default function MasterProductionScheduling() {
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
          <Calendar className="h-7 w-7 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">Production & Supply Schedule</h1>
            <p className="text-sm text-muted-foreground">
              Agent-generated plan — inspect and override via Decision Stream
            </p>
          </div>
        </div>
        <div className="flex gap-2">
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

      {/* Summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Plan Records</p>
            <p className="text-2xl font-bold">{summary.total_records?.toLocaleString() || '—'}</p>
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
            <p className="text-sm text-muted-foreground">Time Bucket</p>
            <p className="text-2xl font-bold capitalize">{timeBucket}</p>
          </CardContent>
        </Card>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="plan">Plan View</TabsTrigger>
          <TabsTrigger value="capacity">Capacity</TabsTrigger>
          <TabsTrigger value="metrics">Performance</TabsTrigger>
        </TabsList>

        <TabsContent value="plan">
          {/* Time-phased grid */}
          {series.length > 0 ? (
            <Card>
              <CardContent className="pt-4">
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="sticky left-0 bg-white z-10">Period</TableHead>
                        <TableHead className="text-right">P10 (Low)</TableHead>
                        <TableHead className="text-right font-bold">P50 (Plan)</TableHead>
                        <TableHead className="text-right">P90 (High)</TableHead>
                        <TableHead className="text-right">Actual</TableHead>
                        <TableHead className="text-right">Products</TableHead>
                        <TableHead className="text-right">Sites</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {series.slice(0, 52).map((row) => (
                        <TableRow key={row.date}>
                          <TableCell className="sticky left-0 bg-white font-mono text-xs">{row.date}</TableCell>
                          <TableCell className="text-right text-muted-foreground">{row.p10?.toLocaleString()}</TableCell>
                          <TableCell className="text-right font-bold">{row.p50?.toLocaleString()}</TableCell>
                          <TableCell className="text-right text-muted-foreground">{row.p90?.toLocaleString()}</TableCell>
                          <TableCell className="text-right text-red-600">{row.actual?.toLocaleString() || '—'}</TableCell>
                          <TableCell className="text-right text-xs">{row.products}</TableCell>
                          <TableCell className="text-right text-xs">{row.sites}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Alert className="mt-4">
              {loading ? 'Loading plan...' : 'No plan data. The plan is generated automatically during provisioning.'}
            </Alert>
          )}
        </TabsContent>

        <TabsContent value="capacity">
          <Alert className="mt-4">
            Capacity planning view — shows resource utilization against the production schedule.
            Populated during RCCP validation provisioning step.
          </Alert>
        </TabsContent>

        <TabsContent value="metrics">
          <Alert className="mt-4">
            Performance metrics — plan adherence, schedule stability, on-time delivery.
            Populated from backtest evaluation results.
          </Alert>
        </TabsContent>
      </Tabs>
    </div>
  );
}
