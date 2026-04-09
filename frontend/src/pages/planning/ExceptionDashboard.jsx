import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';
import {
  Card, CardContent, CardHeader, CardTitle,
  Badge, Button, Spinner, Alert, AlertDescription,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '../../components/common';
import {
  AlertTriangle, RefreshCw, Filter, Clock, DollarSign,
  ShieldAlert, Pause, Play, ExternalLink,
} from 'lucide-react';

const EXCEPTION_TYPES = ['DELAY', 'DAMAGE', 'REFUSED', 'ROLLED', 'TEMPERATURE', 'CUSTOMS'];
const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];

const TYPE_COLORS = {
  DELAY: 'bg-amber-100 text-amber-800 border-amber-300',
  DAMAGE: 'bg-red-100 text-red-800 border-red-300',
  REFUSED: 'bg-orange-100 text-orange-800 border-orange-300',
  ROLLED: 'bg-purple-100 text-purple-800 border-purple-300',
  TEMPERATURE: 'bg-blue-100 text-blue-800 border-blue-300',
  CUSTOMS: 'bg-gray-100 text-gray-800 border-gray-300',
};

const SEVERITY_COLORS = {
  CRITICAL: 'bg-red-100 text-red-800 border-red-300',
  HIGH: 'bg-orange-100 text-orange-800 border-orange-300',
  MEDIUM: 'bg-amber-100 text-amber-800 border-amber-300',
  LOW: 'bg-blue-100 text-blue-800 border-blue-300',
};

const AUTO_REFRESH_INTERVAL = 30000;

const ExceptionDashboard = () => {
  const [exceptions, setExceptions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({ type: '', severity: '' });
  const [autoRefresh, setAutoRefresh] = useState(true);
  const intervalRef = useRef(null);

  const fetchData = useCallback(async () => {
    setError(null);
    try {
      const params = {};
      if (filters.type) params.type = filters.type;
      if (filters.severity) params.severity = filters.severity;
      const [exceptionsRes, summaryRes] = await Promise.all([
        api.get('/exceptions', { params }),
        api.get('/exceptions/summary', { params }),
      ]);
      setExceptions(exceptionsRes.data?.exceptions || exceptionsRes.data || []);
      setSummary(summaryRes.data || null);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to fetch exceptions');
      setExceptions([]);
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    setLoading(true);
    fetchData();
  }, [fetchData]);

  // Auto-refresh
  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(fetchData, AUTO_REFRESH_INTERVAL);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh, fetchData]);

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const formatCurrency = (val) => (val != null ? `$${Number(val).toLocaleString()}` : '\u2014');
  const formatHours = (val) => (val != null ? `${Number(val).toFixed(1)}h` : '\u2014');

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner className="h-8 w-8" />
        <span className="ml-3 text-sm text-gray-500">Loading exceptions...</span>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-gray-700" />
          <h1 className="text-xl font-semibold text-gray-900">Exception Dashboard</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAutoRefresh((v) => !v)}
            className={cn(autoRefresh && 'border-green-400 text-green-700')}
          >
            {autoRefresh ? <Pause className="h-4 w-4 mr-1" /> : <Play className="h-4 w-4 mr-1" />}
            {autoRefresh ? 'Auto-refresh ON' : 'Auto-refresh OFF'}
          </Button>
          <Button variant="outline" size="sm" onClick={fetchData}>
            <RefreshCw className="h-4 w-4 mr-1" /> Refresh
          </Button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* KPI Summary */}
      {summary ? (
        <div className="grid grid-cols-4 gap-3">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                <span className="text-xs text-gray-500">Open Exceptions</span>
              </div>
              <div className="text-2xl font-bold">
                {summary.open_count != null ? summary.open_count : '\u2014'}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1">
                <ShieldAlert className="h-4 w-4 text-red-500" />
                <span className="text-xs text-gray-500">Critical</span>
              </div>
              <div className="text-2xl font-bold text-red-600">
                {summary.critical_count != null ? summary.critical_count : '\u2014'}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1">
                <Clock className="h-4 w-4 text-blue-500" />
                <span className="text-xs text-gray-500">Avg Resolution Hours</span>
              </div>
              <div className="text-2xl font-bold">
                {summary.avg_resolution_hours != null
                  ? `${Number(summary.avg_resolution_hours).toFixed(1)}h`
                  : '\u2014'}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1">
                <DollarSign className="h-4 w-4 text-green-500" />
                <span className="text-xs text-gray-500">Total Cost Impact</span>
              </div>
              <div className="text-2xl font-bold">
                {summary.total_cost_impact != null
                  ? formatCurrency(summary.total_cost_impact)
                  : '\u2014'}
              </div>
            </CardContent>
          </Card>
        </div>
      ) : !error ? (
        <Alert>
          <AlertDescription>
            No exception summary data available. Verify that exception tracking is configured for this tenant.
          </AlertDescription>
        </Alert>
      ) : null}

      {/* Filter Bar */}
      <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg border">
        <Filter className="h-4 w-4 text-gray-500" />
        <select
          value={filters.type}
          onChange={(e) => handleFilterChange('type', e.target.value)}
          className="text-xs border rounded px-2 py-1"
        >
          <option value="">All Types</option>
          {EXCEPTION_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select
          value={filters.severity}
          onChange={(e) => handleFilterChange('severity', e.target.value)}
          className="text-xs border rounded px-2 py-1"
        >
          <option value="">All Severities</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      {/* No Data */}
      {!error && exceptions.length === 0 && (
        <Alert>
          <AlertDescription>
            No exceptions found matching the current filters. Adjust filters or verify exception data is available.
          </AlertDescription>
        </Alert>
      )}

      {/* Exception Table */}
      {exceptions.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Exception ID</TableHead>
                  <TableHead className="text-xs">Shipment</TableHead>
                  <TableHead className="text-xs">Type</TableHead>
                  <TableHead className="text-xs">Severity</TableHead>
                  <TableHead className="text-xs">Carrier</TableHead>
                  <TableHead className="text-xs">Hours Open</TableHead>
                  <TableHead className="text-xs">Est. Delay</TableHead>
                  <TableHead className="text-xs">Cost Impact</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                  <TableHead className="text-xs">Resolution</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {exceptions.map((exc) => (
                  <TableRow
                    key={exc.id || exc.exception_id}
                    className="cursor-pointer hover:bg-gray-50"
                  >
                    <TableCell className="text-xs font-mono">
                      {exc.exception_id || exc.id || '\u2014'}
                    </TableCell>
                    <TableCell className="text-xs">
                      {exc.shipment_id || exc.shipment || '\u2014'}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={cn('text-[10px]', TYPE_COLORS[exc.type] || 'bg-gray-100 text-gray-700')}
                      >
                        {exc.type || '\u2014'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={cn('text-[10px]', SEVERITY_COLORS[exc.severity] || 'bg-gray-100 text-gray-700')}
                      >
                        {exc.severity || '\u2014'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs">{exc.carrier || '\u2014'}</TableCell>
                    <TableCell className="text-xs">{formatHours(exc.hours_open)}</TableCell>
                    <TableCell className="text-xs">{formatHours(exc.est_delay_hours)}</TableCell>
                    <TableCell className="text-xs">{formatCurrency(exc.cost_impact)}</TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={cn(
                          'text-[10px]',
                          exc.status === 'RESOLVED'
                            ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
                            : exc.status === 'INVESTIGATING'
                            ? 'bg-blue-100 text-blue-800 border-blue-300'
                            : 'bg-amber-100 text-amber-800 border-amber-300'
                        )}
                      >
                        {exc.status || '\u2014'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs max-w-[150px] truncate">
                      {exc.resolution || '\u2014'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default ExceptionDashboard;
