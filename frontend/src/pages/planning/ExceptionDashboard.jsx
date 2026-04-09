import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { api } from '../../services/api';
import { submitTRMAction } from '../../services/planningCascadeApi';
import { cn } from '../../lib/utils/cn';
import {
  Card, CardContent, CardHeader, CardTitle,
  Badge, Button, Spinner, Alert, AlertDescription,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '../../components/common';
import {
  AlertTriangle, RefreshCw, Filter, Clock, DollarSign,
  ShieldAlert, Pause, Play, Check, XCircle, ArrowUpRight,
  User, Timer,
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

const SEVERITY_WEIGHTS = {
  CRITICAL: 4,
  HIGH: 3,
  MEDIUM: 2,
  LOW: 1,
};

const AUTO_REFRESH_INTERVAL = 30000;

/**
 * Compute impact score for an exception, used for priority sorting.
 * Formula: severity_weight * estimated_cost_impact * (1 / max(delivery_window_remaining_hrs, 1))
 */
const computeImpactScore = (exc) => {
  const severityWeight = SEVERITY_WEIGHTS[exc.severity] ?? 1;
  const costImpact = exc.cost_impact != null ? Number(exc.cost_impact) : 0;
  const windowRemaining = exc.delivery_window_remaining_hrs != null
    ? Number(exc.delivery_window_remaining_hrs)
    : 24;
  return severityWeight * costImpact * (1 / Math.max(windowRemaining, 1));
};

/**
 * Return time-to-resolve color based on hours since detection.
 */
const getTimeToResolveColor = (hoursOpen) => {
  if (hoursOpen == null) return 'text-gray-400';
  if (hoursOpen < 4) return 'text-green-600';
  if (hoursOpen < 12) return 'text-amber-600';
  return 'text-red-600';
};

const ExceptionDashboard = () => {
  const [exceptions, setExceptions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState({});
  const [filters, setFilters] = useState({
    type: '',
    severity: '',
    carrier: '',
    customer: '',
  });
  const [autoRefresh, setAutoRefresh] = useState(true);
  const intervalRef = useRef(null);

  const fetchData = useCallback(async () => {
    setError(null);
    try {
      const params = {};
      if (filters.type) params.type = filters.type;
      if (filters.severity) params.severity = filters.severity;
      if (filters.carrier) params.carrier = filters.carrier;
      if (filters.customer) params.customer = filters.customer;
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

  // Sort exceptions by impact score descending
  const sortedExceptions = useMemo(() => {
    return [...exceptions]
      .map((exc) => ({
        ...exc,
        impact_score: computeImpactScore(exc),
      }))
      .sort((a, b) => b.impact_score - a.impact_score);
  }, [exceptions]);

  // Extract unique carriers and customers for filter dropdowns
  const uniqueCarriers = useMemo(() => {
    const set = new Set();
    exceptions.forEach((exc) => { if (exc.carrier) set.add(exc.carrier); });
    return Array.from(set).sort();
  }, [exceptions]);

  const uniqueCustomers = useMemo(() => {
    const set = new Set();
    exceptions.forEach((exc) => { if (exc.customer) set.add(exc.customer); });
    return Array.from(set).sort();
  }, [exceptions]);

  // Compute most impacted customer from summary or data
  const mostImpactedCustomer = useMemo(() => {
    if (summary?.most_impacted_customer) return summary.most_impacted_customer;
    if (exceptions.length === 0) return null;
    const customerCounts = {};
    exceptions.forEach((exc) => {
      if (exc.customer) {
        customerCounts[exc.customer] = (customerCounts[exc.customer] || 0) + 1;
      }
    });
    const entries = Object.entries(customerCounts);
    if (entries.length === 0) return null;
    entries.sort((a, b) => b[1] - a[1]);
    return entries[0][0];
  }, [exceptions, summary]);

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const handleAction = async (exc, action) => {
    const excId = exc.exception_id || exc.id;
    setActionLoading((prev) => ({ ...prev, [excId]: action }));
    try {
      await submitTRMAction({
        decision_id: exc.decision_id || excId,
        trm_type: 'exception_management',
        action,
        exception_id: excId,
        override_reason: action === 'OVERRIDE' ? 'User override from exception dashboard' : undefined,
      });
      // Refresh data after action
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || `Failed to ${action.toLowerCase()} exception`);
    } finally {
      setActionLoading((prev) => ({ ...prev, [excId]: null }));
    }
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
        <div className="grid grid-cols-6 gap-3">
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
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1">
                <Timer className="h-4 w-4 text-indigo-500" />
                <span className="text-xs text-gray-500">Avg Time to Resolve</span>
              </div>
              <div className="text-2xl font-bold">
                {summary.avg_time_to_resolve_hours != null
                  ? `${Number(summary.avg_time_to_resolve_hours).toFixed(1)}h`
                  : '\u2014'}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1">
                <User className="h-4 w-4 text-orange-500" />
                <span className="text-xs text-gray-500">Most Impacted Customer</span>
              </div>
              <div className="text-lg font-bold truncate">
                {mostImpactedCustomer || '\u2014'}
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
      <div className="flex flex-wrap items-center gap-3 p-3 bg-gray-50 rounded-lg border">
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
        <select
          value={filters.carrier}
          onChange={(e) => handleFilterChange('carrier', e.target.value)}
          className="text-xs border rounded px-2 py-1"
        >
          <option value="">All Carriers</option>
          {uniqueCarriers.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          value={filters.customer}
          onChange={(e) => handleFilterChange('customer', e.target.value)}
          className="text-xs border rounded px-2 py-1"
        >
          <option value="">All Customers</option>
          {uniqueCustomers.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      {/* No Data */}
      {!error && sortedExceptions.length === 0 && (
        <Alert>
          <AlertDescription>
            No exceptions found matching the current filters. Adjust filters or verify exception data is available.
          </AlertDescription>
        </Alert>
      )}

      {/* Exception Table — sorted by impact_score descending */}
      {sortedExceptions.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Impact</TableHead>
                  <TableHead className="text-xs">Exception ID</TableHead>
                  <TableHead className="text-xs">Shipment</TableHead>
                  <TableHead className="text-xs">Type</TableHead>
                  <TableHead className="text-xs">Severity</TableHead>
                  <TableHead className="text-xs">Carrier</TableHead>
                  <TableHead className="text-xs">Customer</TableHead>
                  <TableHead className="text-xs">Time Open</TableHead>
                  <TableHead className="text-xs">Est. Delay</TableHead>
                  <TableHead className="text-xs">Cost Impact</TableHead>
                  <TableHead className="text-xs">Agent Action (AIIO)</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                  <TableHead className="text-xs">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedExceptions.map((exc) => {
                  const excId = exc.exception_id || exc.id;
                  const currentActionLoading = actionLoading[excId];
                  return (
                    <TableRow
                      key={excId}
                      className="hover:bg-gray-50"
                    >
                      {/* Impact Score */}
                      <TableCell className="text-xs font-mono font-semibold">
                        {exc.impact_score > 0 ? exc.impact_score.toFixed(0) : '\u2014'}
                      </TableCell>
                      {/* Exception ID */}
                      <TableCell className="text-xs font-mono">
                        {excId || '\u2014'}
                      </TableCell>
                      {/* Shipment */}
                      <TableCell className="text-xs">
                        {exc.shipment_id || exc.shipment || '\u2014'}
                      </TableCell>
                      {/* Type */}
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn('text-[10px]', TYPE_COLORS[exc.type] || 'bg-gray-100 text-gray-700')}
                        >
                          {exc.type || '\u2014'}
                        </Badge>
                      </TableCell>
                      {/* Severity */}
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn('text-[10px]', SEVERITY_COLORS[exc.severity] || 'bg-gray-100 text-gray-700')}
                        >
                          {exc.severity || '\u2014'}
                        </Badge>
                      </TableCell>
                      {/* Carrier */}
                      <TableCell className="text-xs">{exc.carrier || '\u2014'}</TableCell>
                      {/* Customer */}
                      <TableCell className="text-xs">{exc.customer || '\u2014'}</TableCell>
                      {/* Time Open with color coding */}
                      <TableCell>
                        <span className={cn('text-xs font-medium', getTimeToResolveColor(exc.hours_open))}>
                          {formatHours(exc.hours_open)}
                        </span>
                      </TableCell>
                      {/* Est. Delay */}
                      <TableCell className="text-xs">{formatHours(exc.est_delay_hours)}</TableCell>
                      {/* Cost Impact */}
                      <TableCell className="text-xs">{formatCurrency(exc.cost_impact)}</TableCell>
                      {/* Agent Recommended Action (AIIO) */}
                      <TableCell>
                        {exc.agent_action ? (
                          <div className="space-y-0.5">
                            <Badge
                              variant="outline"
                              className={cn(
                                'text-[10px]',
                                exc.agent_action === 'REROUTE' && 'bg-amber-100 text-amber-800 border-amber-300',
                                exc.agent_action === 'RETENDER' && 'bg-red-100 text-red-800 border-red-300',
                                exc.agent_action === 'HOLD' && 'bg-blue-100 text-blue-800 border-blue-300',
                                exc.agent_action === 'ESCALATE' && 'bg-purple-100 text-purple-800 border-purple-300',
                                exc.agent_action === 'AUTO_RESOLVE' && 'bg-green-100 text-green-800 border-green-300',
                              )}
                            >
                              {exc.agent_action}
                            </Badge>
                            {exc.agent_confidence != null && (
                              <div className="text-[9px] text-gray-400">
                                {(Number(exc.agent_confidence) * 100).toFixed(0)}% conf
                              </div>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-gray-400">{'\u2014'}</span>
                        )}
                      </TableCell>
                      {/* Status */}
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
                      {/* Inline Action Buttons */}
                      <TableCell>
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-[10px] text-green-700 hover:bg-green-50"
                            disabled={!!currentActionLoading || exc.status === 'RESOLVED'}
                            onClick={() => handleAction(exc, 'ACCEPT')}
                            title="Accept agent action"
                          >
                            {currentActionLoading === 'ACCEPT' ? (
                              <Spinner className="h-3 w-3" />
                            ) : (
                              <Check className="h-3 w-3" />
                            )}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-[10px] text-red-700 hover:bg-red-50"
                            disabled={!!currentActionLoading || exc.status === 'RESOLVED'}
                            onClick={() => handleAction(exc, 'OVERRIDE')}
                            title="Override agent action"
                          >
                            {currentActionLoading === 'OVERRIDE' ? (
                              <Spinner className="h-3 w-3" />
                            ) : (
                              <XCircle className="h-3 w-3" />
                            )}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-[10px] text-purple-700 hover:bg-purple-50"
                            disabled={!!currentActionLoading || exc.status === 'RESOLVED'}
                            onClick={() => handleAction(exc, 'ESCALATE')}
                            title="Escalate exception"
                          >
                            {currentActionLoading === 'ESCALATE' ? (
                              <Spinner className="h-3 w-3" />
                            ) : (
                              <ArrowUpRight className="h-3 w-3" />
                            )}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default ExceptionDashboard;
