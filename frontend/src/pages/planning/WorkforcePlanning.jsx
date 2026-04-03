/**
 * Workforce Planning — Estimated labor needs based on order volumes and site capacity.
 *
 * Shows labor estimates derived from resource capacity data and supply plan volumes.
 * No synthetic/hardcoded data — displays empty state when no data is provisioned.
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  Card, CardContent, CardHeader, CardTitle, Button, Badge, Alert, Spinner,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '../../components/common';
import {
  Users, RefreshCw, AlertTriangle, Warehouse,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';

export default function WorkforcePlanning() {
  const { effectiveConfigId } = useActiveConfig();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [resources, setResources] = useState([]);

  useEffect(() => {
    if (effectiveConfigId) loadData();
  }, [effectiveConfigId]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/resource-capacity/utilization/analysis', {
        params: { config_id: effectiveConfigId },
      });
      const data = res.data?.utilization || res.data || [];
      setResources(data.map(r => ({
        resource_id: r.resource_id,
        resource_name: r.resource_name || r.resource_id,
        site_name: r.site_name || r.site_id || '—',
        available_hours: r.available_hours || r.total_available || 0,
        utilized_hours: r.required_hours || r.total_utilized || 0,
        utilization_pct: r.utilization_pct || r.utilization || 0,
      })));
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
      setResources([]);
    } finally {
      setLoading(false);
    }
  };

  // Derive labor estimates: assume ~8h per FTE per day, 5 days/week = 40h/week
  const HOURS_PER_FTE_WEEK = 40;

  const laborEstimates = useMemo(() =>
    resources.map(r => ({
      ...r,
      estimated_fte: r.utilized_hours > 0 ? Math.ceil(r.utilized_hours / HOURS_PER_FTE_WEEK) : 0,
      capacity_fte: r.available_hours > 0 ? Math.ceil(r.available_hours / HOURS_PER_FTE_WEEK) : 0,
      gap: r.available_hours > 0
        ? Math.ceil(r.available_hours / HOURS_PER_FTE_WEEK) - Math.ceil(r.utilized_hours / HOURS_PER_FTE_WEEK)
        : 0,
    })),
  [resources]);

  const summary = useMemo(() => ({
    total_capacity_fte: laborEstimates.reduce((s, r) => s + r.capacity_fte, 0),
    total_required_fte: laborEstimates.reduce((s, r) => s + r.estimated_fte, 0),
    total_available_hours: resources.reduce((s, r) => s + r.available_hours, 0),
    total_utilized_hours: resources.reduce((s, r) => s + r.utilized_hours, 0),
    understaffed: laborEstimates.filter(r => r.gap < 0).length,
  }), [laborEstimates, resources]);

  if (loading) return <div className="flex justify-center py-16"><Spinner /></div>;

  if (!loading && resources.length === 0 && !error) {
    return (
      <div className="text-center py-16 text-muted-foreground">
        <Users className="h-10 w-10 mx-auto mb-3 opacity-50" />
        <p className="font-medium">No workforce data available</p>
        <p className="text-sm mt-1">Resource capacity records have not been provisioned for this configuration.</p>
        <p className="text-sm">Labor estimates are derived from resource capacity and utilization data.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && <Alert variant="destructive"><AlertTriangle className="h-4 w-4" />{error}</Alert>}

      {/* Summary Cards */}
      <div className="grid grid-cols-5 gap-3">
        <Card>
          <CardContent className="pt-3 text-center">
            <Users className="h-4 w-4 mx-auto mb-1 text-blue-500" />
            <div className="text-lg font-bold">{summary.total_capacity_fte}</div>
            <div className="text-[10px] text-muted-foreground">Capacity FTEs</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-3 text-center">
            <Users className="h-4 w-4 mx-auto mb-1 text-green-500" />
            <div className="text-lg font-bold">{summary.total_required_fte}</div>
            <div className="text-[10px] text-muted-foreground">Required FTEs</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-3 text-center">
            <Warehouse className="h-4 w-4 mx-auto mb-1 text-muted-foreground" />
            <div className="text-lg font-bold">{Math.round(summary.total_available_hours)}h</div>
            <div className="text-[10px] text-muted-foreground">Total Available</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-3 text-center">
            <Warehouse className="h-4 w-4 mx-auto mb-1 text-amber-500" />
            <div className="text-lg font-bold">{Math.round(summary.total_utilized_hours)}h</div>
            <div className="text-[10px] text-muted-foreground">Total Utilized</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-3 text-center">
            <AlertTriangle className="h-4 w-4 mx-auto mb-1 text-red-500" />
            <div className="text-lg font-bold">{summary.understaffed}</div>
            <div className="text-[10px] text-muted-foreground">Over Capacity</div>
          </CardContent>
        </Card>
      </div>

      {/* FTE Estimate Chart */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm">Estimated FTEs: Capacity vs Required</CardTitle>
            <Button variant="outline" size="sm" onClick={loadData}><RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh</Button>
          </div>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={laborEstimates}>
              <XAxis dataKey="resource_name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={60} />
              <YAxis tick={{ fontSize: 10 }} label={{ value: 'FTEs', angle: -90, position: 'insideLeft', fontSize: 10 }} />
              <Tooltip />
              <Legend />
              <Bar dataKey="capacity_fte" name="Capacity FTEs" fill="#3b82f6" fillOpacity={0.7} radius={[2, 2, 0, 0]} />
              <Bar dataKey="estimated_fte" name="Required FTEs" fill="#ef4444" fillOpacity={0.5} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Detail Table */}
      <Card>
        <CardHeader><CardTitle className="text-sm">Labor Estimate Detail</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Resource</TableHead>
                <TableHead>Site</TableHead>
                <TableHead className="text-right">Available Hours</TableHead>
                <TableHead className="text-right">Utilized Hours</TableHead>
                <TableHead className="text-right">Utilization</TableHead>
                <TableHead className="text-right">Capacity FTEs</TableHead>
                <TableHead className="text-right">Required FTEs</TableHead>
                <TableHead className="text-right">Gap</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {laborEstimates.map(r => (
                <TableRow key={r.resource_id}>
                  <TableCell className="font-medium">{r.resource_name}</TableCell>
                  <TableCell>{r.site_name}</TableCell>
                  <TableCell className="text-right tabular-nums">{Math.round(r.available_hours)}h</TableCell>
                  <TableCell className="text-right tabular-nums">{Math.round(r.utilized_hours)}h</TableCell>
                  <TableCell className="text-right">
                    <Badge variant={r.utilization_pct >= 95 ? 'destructive' : r.utilization_pct >= 85 ? 'warning' : 'secondary'}>
                      {Math.round(r.utilization_pct)}%
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{r.capacity_fte}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.estimated_fte}</TableCell>
                  <TableCell className="text-right">
                    <Badge variant={r.gap < 0 ? 'destructive' : r.gap === 0 ? 'secondary' : 'success'}>
                      {r.gap > 0 ? `+${r.gap}` : r.gap}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
              {laborEstimates.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                    No resource data available
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
