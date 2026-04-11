import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { api } from '../../services/api';
import { cn } from '@azirella-ltd/autonomy-frontend';
import {
  Card, CardContent, CardHeader, CardTitle,
  Badge, Button, Spinner, Alert, AlertDescription,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '../../components/common';
import {
  MapPin, RefreshCw, Filter, TrendingUp, TrendingDown, ArrowUpDown,
  DollarSign, Clock, Truck, ChevronDown, ChevronRight,
} from 'lucide-react';

const PERIODS = [
  { label: '7d', value: '7d' },
  { label: '30d', value: '30d' },
  { label: '90d', value: '90d' },
];

const LaneAnalytics = () => {
  const [lanes, setLanes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [period, setPeriod] = useState('30d');
  const [modeFilter, setModeFilter] = useState('All');
  const [minVolume, setMinVolume] = useState('');
  const [sortKey, setSortKey] = useState('volume');
  const [sortDir, setSortDir] = useState('desc');
  const [expandedLane, setExpandedLane] = useState(null);

  const fetchLanes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { period };
      if (modeFilter !== 'All') params.mode = modeFilter;
      if (minVolume) params.min_volume = minVolume;
      const response = await api.get('/lanes/analytics', { params });
      setLanes(response.data?.lanes || response.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to fetch lane analytics');
      setLanes([]);
    } finally {
      setLoading(false);
    }
  }, [period, modeFilter, minVolume]);

  useEffect(() => {
    fetchLanes();
  }, [fetchLanes]);

  const kpis = useMemo(() => {
    if (lanes.length === 0) return null;
    const totalLanes = lanes.length;
    const costPerMileValues = lanes.map((l) => l.cost_per_mile).filter((v) => v != null);
    const otdValues = lanes.map((l) => l.otd_pct).filter((v) => v != null);
    const utilValues = lanes.map((l) => l.utilization_pct).filter((v) => v != null);
    return {
      totalLanes,
      avgCostPerMile: costPerMileValues.length > 0
        ? (costPerMileValues.reduce((a, b) => a + b, 0) / costPerMileValues.length)
        : null,
      avgOtd: otdValues.length > 0
        ? (otdValues.reduce((a, b) => a + b, 0) / otdValues.length)
        : null,
      avgUtilization: utilValues.length > 0
        ? (utilValues.reduce((a, b) => a + b, 0) / utilValues.length)
        : null,
    };
  }, [lanes]);

  const sortedLanes = useMemo(() => {
    const sorted = [...lanes].sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      if (typeof aVal === 'string') {
        return sortDir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
    });
    return sorted;
  }, [lanes, sortKey, sortDir]);

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const toggleExpand = (laneId) => {
    setExpandedLane((prev) => (prev === laneId ? null : laneId));
  };

  const formatCurrency = (val) => (val != null ? `$${Number(val).toFixed(2)}` : '\u2014');
  const formatPct = (val) => (val != null ? `${Number(val).toFixed(1)}%` : '\u2014');

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner className="h-8 w-8" />
        <span className="ml-3 text-sm text-gray-500">Loading lane analytics...</span>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MapPin className="h-5 w-5 text-gray-700" />
          <h1 className="text-xl font-semibold text-gray-900">Lane Analytics</h1>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {PERIODS.map((p) => (
              <button
                key={p.value}
                onClick={() => setPeriod(p.value)}
                className={cn(
                  'px-3 py-1 text-xs font-medium rounded-full border transition-colors',
                  period === p.value
                    ? 'bg-indigo-600 text-white border-indigo-600'
                    : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-100'
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
          <Button variant="outline" size="sm" onClick={fetchLanes}>
            <RefreshCw className="h-4 w-4 mr-1" /> Refresh
          </Button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg border">
        <Filter className="h-4 w-4 text-gray-500" />
        <select
          value={modeFilter}
          onChange={(e) => setModeFilter(e.target.value)}
          className="text-xs border rounded px-2 py-1"
        >
          <option value="All">All Modes</option>
          <option value="FTL">FTL</option>
          <option value="LTL">LTL</option>
          <option value="Intermodal">Intermodal</option>
          <option value="Rail">Rail</option>
          <option value="Ocean">Ocean</option>
          <option value="Air">Air</option>
        </select>
        <input
          type="number"
          value={minVolume}
          onChange={(e) => setMinVolume(e.target.value)}
          placeholder="Min volume"
          className="text-xs border rounded px-2 py-1 w-24"
        />
      </div>

      {/* Error */}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* No Data */}
      {!error && lanes.length === 0 && (
        <Alert>
          <AlertDescription>
            No lane analytics data available for the selected period. Verify that lane and shipment data has been provisioned.
          </AlertDescription>
        </Alert>
      )}

      {/* KPI Summary */}
      {kpis && (
        <div className="grid grid-cols-4 gap-3">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1">
                <MapPin className="h-4 w-4 text-indigo-500" />
                <span className="text-xs text-gray-500">Total Lanes</span>
              </div>
              <div className="text-2xl font-bold">{kpis.totalLanes}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1">
                <DollarSign className="h-4 w-4 text-green-500" />
                <span className="text-xs text-gray-500">Avg Cost/Mile</span>
              </div>
              <div className="text-2xl font-bold">{formatCurrency(kpis.avgCostPerMile)}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1">
                <Clock className="h-4 w-4 text-amber-500" />
                <span className="text-xs text-gray-500">Avg OTD %</span>
              </div>
              <div className="text-2xl font-bold">{formatPct(kpis.avgOtd)}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-1">
                <Truck className="h-4 w-4 text-blue-500" />
                <span className="text-xs text-gray-500">Avg Utilization %</span>
              </div>
              <div className="text-2xl font-bold">{formatPct(kpis.avgUtilization)}</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Lane Table */}
      {sortedLanes.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  {[
                    { key: 'lane', label: 'Lane' },
                    { key: 'mode', label: 'Mode' },
                    { key: 'volume', label: 'Volume' },
                    { key: 'avg_rate', label: 'Avg Rate' },
                    { key: 'cost_per_mile', label: 'Cost/Mile' },
                    { key: 'otd_pct', label: 'OTD %' },
                    { key: 'carrier_count', label: 'Carriers' },
                    { key: 'top_carrier', label: 'Top Carrier' },
                    { key: 'volume_change', label: 'Trend' },
                  ].map((col) => (
                    <TableHead
                      key={col.key}
                      className="cursor-pointer hover:bg-gray-100 text-xs"
                      onClick={() => handleSort(col.key)}
                    >
                      <div className="flex items-center gap-1">
                        {col.label}
                        {sortKey === col.key && (
                          <ArrowUpDown className="h-3 w-3 text-indigo-500" />
                        )}
                      </div>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedLanes.map((lane) => {
                  const laneId = lane.lane_id || lane.id;
                  const isExpanded = expandedLane === laneId;
                  return (
                    <React.Fragment key={laneId}>
                      <TableRow
                        className="cursor-pointer hover:bg-gray-50"
                        onClick={() => toggleExpand(laneId)}
                      >
                        <TableCell className="w-8">
                          {isExpanded
                            ? <ChevronDown className="h-4 w-4 text-gray-400" />
                            : <ChevronRight className="h-4 w-4 text-gray-400" />}
                        </TableCell>
                        <TableCell className="text-xs font-medium">
                          {lane.origin || '\u2014'} → {lane.destination || '\u2014'}
                        </TableCell>
                        <TableCell className="text-xs">{lane.mode || '\u2014'}</TableCell>
                        <TableCell className="text-xs">{lane.volume != null ? lane.volume : '\u2014'}</TableCell>
                        <TableCell className="text-xs">{formatCurrency(lane.avg_rate)}</TableCell>
                        <TableCell className="text-xs">{formatCurrency(lane.cost_per_mile)}</TableCell>
                        <TableCell className="text-xs">{formatPct(lane.otd_pct)}</TableCell>
                        <TableCell className="text-xs">{lane.carrier_count != null ? lane.carrier_count : '\u2014'}</TableCell>
                        <TableCell className="text-xs">{lane.top_carrier || '\u2014'}</TableCell>
                        <TableCell className="text-xs">
                          {lane.volume_change != null ? (
                            lane.volume_change >= 0 ? (
                              <span className="flex items-center gap-1 text-green-600">
                                <TrendingUp className="h-3 w-3" />
                                +{Number(lane.volume_change).toFixed(1)}%
                              </span>
                            ) : (
                              <span className="flex items-center gap-1 text-red-600">
                                <TrendingDown className="h-3 w-3" />
                                {Number(lane.volume_change).toFixed(1)}%
                              </span>
                            )
                          ) : '\u2014'}
                        </TableCell>
                      </TableRow>
                      {isExpanded && lane.carrier_breakdown && (
                        <TableRow>
                          <TableCell colSpan={10} className="bg-gray-50 p-3">
                            <div className="text-xs font-medium mb-2 text-gray-700">Carrier Breakdown</div>
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="text-gray-500">
                                  <th className="text-left py-1 px-2">Carrier</th>
                                  <th className="text-left py-1 px-2">Loads</th>
                                  <th className="text-left py-1 px-2">Avg Rate</th>
                                  <th className="text-left py-1 px-2">OTD %</th>
                                  <th className="text-left py-1 px-2">Share %</th>
                                </tr>
                              </thead>
                              <tbody>
                                {lane.carrier_breakdown.map((cb, idx) => (
                                  <tr key={idx} className="border-t border-gray-200">
                                    <td className="py-1 px-2">{cb.carrier || '\u2014'}</td>
                                    <td className="py-1 px-2">{cb.loads != null ? cb.loads : '\u2014'}</td>
                                    <td className="py-1 px-2">{formatCurrency(cb.avg_rate)}</td>
                                    <td className="py-1 px-2">{formatPct(cb.otd_pct)}</td>
                                    <td className="py-1 px-2">{formatPct(cb.share_pct)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
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

export default LaneAnalytics;
