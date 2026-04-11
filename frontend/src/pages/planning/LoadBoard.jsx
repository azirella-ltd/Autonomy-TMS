import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { api } from '../../services/api';
import { cn } from '@azirella-ltd/autonomy-frontend';
import {
  Card, CardContent, CardHeader, CardTitle,
  Badge, Button, Spinner, Alert, AlertDescription,
} from '../../components/common';
import {
  Truck, RefreshCw, Filter, Search, Package, MapPin, Calendar,
  ArrowRight, DollarSign, Clock, TrendingUp,
} from 'lucide-react';

const STATUSES = ['PLANNING', 'TENDERING', 'ACCEPTED', 'IN_TRANSIT', 'DELIVERED'];

const STATUS_COLORS = {
  PLANNING: 'bg-slate-100 border-slate-300 text-slate-700',
  TENDERING: 'bg-amber-50 border-amber-300 text-amber-700',
  ACCEPTED: 'bg-blue-50 border-blue-300 text-blue-700',
  IN_TRANSIT: 'bg-indigo-50 border-indigo-300 text-indigo-700',
  DELIVERED: 'bg-emerald-50 border-emerald-300 text-emerald-700',
};

const STATUS_HEADER_COLORS = {
  PLANNING: 'bg-slate-500',
  TENDERING: 'bg-amber-500',
  ACCEPTED: 'bg-blue-500',
  IN_TRANSIT: 'bg-indigo-500',
  DELIVERED: 'bg-emerald-500',
};

const MODES = ['All', 'FTL', 'LTL', 'Intermodal'];

const TIER_LABELS = {
  1: 'Tier 1 (Primary)',
  2: 'Tier 2 (Backup)',
  3: 'Tier 3 (Spot)',
  4: 'Broker',
};

const TENDER_RESPONSE_COLORS = {
  ACCEPTED: 'bg-green-100 text-green-800 border-green-300',
  REJECTED: 'bg-red-100 text-red-800 border-red-300',
  TIMEOUT: 'bg-gray-100 text-gray-600 border-gray-300',
  PENDING: 'bg-amber-100 text-amber-800 border-amber-300',
};

const formatDate = (dateStr) => {
  if (!dateStr) return '\u2014';
  try {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric',
    });
  } catch {
    return '\u2014';
  }
};

const formatDateTime = (dateStr) => {
  if (!dateStr) return '\u2014';
  try {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return '\u2014';
  }
};

const formatWeight = (weight) => {
  if (weight == null) return '\u2014';
  return `${Number(weight).toLocaleString()} lbs`;
};

const formatCurrency = (val) => {
  if (val == null) return '\u2014';
  return `$${Number(val).toLocaleString()}`;
};

const LoadBoard = () => {
  const [loads, setLoads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedTender, setExpandedTender] = useState(null);
  const [filters, setFilters] = useState({
    mode: 'All',
    dateFrom: '',
    dateTo: '',
    laneSearch: '',
  });

  const fetchLoads = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (filters.mode !== 'All') params.mode = filters.mode;
      if (filters.dateFrom) params.date_from = filters.dateFrom;
      if (filters.dateTo) params.date_to = filters.dateTo;
      if (filters.laneSearch) params.lane_search = filters.laneSearch;
      const response = await api.get('/loads', { params });
      setLoads(response.data?.loads || response.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to fetch loads');
      setLoads([]);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchLoads();
  }, [fetchLoads]);

  const loadsByStatus = useMemo(() => {
    const grouped = {};
    STATUSES.forEach((s) => { grouped[s] = []; });
    loads.forEach((load) => {
      const status = load.status || 'PLANNING';
      if (grouped[status]) {
        grouped[status].push(load);
      }
    });
    return grouped;
  }, [loads]);

  const statusCounts = useMemo(() => {
    const counts = {};
    STATUSES.forEach((s) => { counts[s] = loadsByStatus[s].length; });
    return counts;
  }, [loadsByStatus]);

  // Summary metrics computed from data
  const summaryMetrics = useMemo(() => {
    if (loads.length === 0) return null;

    // Tender accept rate: accepted / (accepted + tendering with responses)
    const tenderedLoads = loads.filter((l) =>
      l.status === 'TENDERING' || l.status === 'ACCEPTED' || l.tender_responses
    );
    const acceptedCount = loads.filter((l) => l.status === 'ACCEPTED' || l.status === 'IN_TRANSIT' || l.status === 'DELIVERED').length;
    const tenderAcceptRate = tenderedLoads.length > 0
      ? ((acceptedCount / Math.max(tenderedLoads.length, acceptedCount)) * 100)
      : null;

    // Average cost per load
    const loadsWithCost = loads.filter((l) => l.total_cost != null);
    const avgCostPerLoad = loadsWithCost.length > 0
      ? loadsWithCost.reduce((sum, l) => sum + Number(l.total_cost), 0) / loadsWithCost.length
      : null;

    return { tenderAcceptRate, avgCostPerLoad };
  }, [loads]);

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const toggleTenderPanel = (loadId) => {
    setExpandedTender((prev) => (prev === loadId ? null : loadId));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner className="h-8 w-8" />
        <span className="ml-3 text-sm text-gray-500">Loading load board...</span>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Truck className="h-5 w-5 text-gray-700" />
          <h1 className="text-xl font-semibold text-gray-900">Load Board</h1>
        </div>
        <Button variant="outline" size="sm" onClick={fetchLoads}>
          <RefreshCw className="h-4 w-4 mr-1" /> Refresh
        </Button>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap items-center gap-3 p-3 bg-gray-50 rounded-lg border">
        <Filter className="h-4 w-4 text-gray-500" />
        <div className="flex gap-1">
          {MODES.map((mode) => (
            <button
              key={mode}
              onClick={() => handleFilterChange('mode', mode)}
              className={cn(
                'px-3 py-1 text-xs font-medium rounded-full border transition-colors',
                filters.mode === mode
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-100'
              )}
            >
              {mode}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-gray-400" />
          <input
            type="date"
            value={filters.dateFrom}
            onChange={(e) => handleFilterChange('dateFrom', e.target.value)}
            className="text-xs border rounded px-2 py-1"
            placeholder="From"
          />
          <span className="text-gray-400">to</span>
          <input
            type="date"
            value={filters.dateTo}
            onChange={(e) => handleFilterChange('dateTo', e.target.value)}
            className="text-xs border rounded px-2 py-1"
          />
        </div>
        <div className="flex items-center gap-1 ml-auto">
          <Search className="h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={filters.laneSearch}
            onChange={(e) => handleFilterChange('laneSearch', e.target.value)}
            placeholder="Search lane..."
            className="text-xs border rounded px-2 py-1 w-40"
          />
        </div>
      </div>

      {/* Error State */}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Empty State */}
      {!error && loads.length === 0 && (
        <Alert>
          <AlertDescription>
            No loads found. Adjust filters or verify that load data has been provisioned for this tenant.
          </AlertDescription>
        </Alert>
      )}

      {/* Kanban Board */}
      {loads.length > 0 && (
        <div className="grid grid-cols-5 gap-3 min-h-[400px]">
          {STATUSES.map((status) => (
            <div key={status} className="flex flex-col rounded-lg border bg-gray-50 overflow-hidden">
              <div className={cn('px-3 py-2 flex items-center justify-between', STATUS_HEADER_COLORS[status])}>
                <span className="text-xs font-semibold text-white uppercase tracking-wide">
                  {status.replace('_', ' ')}
                </span>
                <Badge variant="secondary" className="bg-white/20 text-white text-xs">
                  {statusCounts[status]}
                </Badge>
              </div>
              <div className="flex-1 p-2 space-y-2 overflow-y-auto max-h-[500px]">
                {loadsByStatus[status].map((load) => {
                  const loadId = load.load_id || load.id;
                  const isTendering = status === 'TENDERING';
                  const isExpanded = expandedTender === loadId;
                  return (
                    <div key={loadId}>
                      <div
                        className={cn(
                          'p-2 rounded border text-xs space-y-1 shadow-sm cursor-pointer',
                          STATUS_COLORS[status]
                        )}
                        onClick={() => isTendering && toggleTenderPanel(loadId)}
                      >
                        {/* Load ID + Urgency */}
                        <div className="flex items-center justify-between">
                          <span className="font-semibold truncate">{loadId || '\u2014'}</span>
                          {load.urgency && (
                            <Badge
                              variant="outline"
                              className={cn(
                                'text-[9px]',
                                load.urgency === 'HOT' && 'bg-red-100 text-red-700 border-red-300',
                                load.urgency === 'EXPEDITE' && 'bg-orange-100 text-orange-700 border-orange-300',
                                load.urgency === 'STANDARD' && 'bg-gray-100 text-gray-600 border-gray-200',
                              )}
                            >
                              {load.urgency}
                            </Badge>
                          )}
                        </div>
                        {/* Origin > Destination */}
                        <div className="flex items-center gap-1 text-gray-600">
                          <MapPin className="h-3 w-3" />
                          <span className="truncate">
                            {load.origin || '\u2014'} <ArrowRight className="h-2 w-2 inline" /> {load.destination || '\u2014'}
                          </span>
                        </div>
                        {/* Commodity + Mode + Equipment */}
                        <div className="flex items-center justify-between">
                          <span className="truncate text-gray-500">{load.commodity || load.mode || '\u2014'}</span>
                          <span>{load.equipment_type || '\u2014'}</span>
                        </div>
                        {/* Pickup / Delivery Windows */}
                        <div className="flex items-center justify-between text-gray-500">
                          <span title="Pickup window">P: {formatDateTime(load.pickup_window_start || load.pickup_date)}</span>
                          <span title="Delivery window">D: {formatDateTime(load.delivery_window_end || load.delivery_date)}</span>
                        </div>
                        {/* Weight + Rate Comparison */}
                        <div className="flex items-center justify-between">
                          <span>{formatWeight(load.weight)}</span>
                          {load.total_cost != null && (
                            <span className="font-medium text-indigo-700">{formatCurrency(load.total_cost)}</span>
                          )}
                        </div>
                        {/* Rate Comparison Row */}
                        {(load.contract_rate != null || load.spot_rate != null || load.benchmark_rate != null) && (
                          <div className="flex items-center gap-2 pt-1 border-t border-gray-200/50 text-[10px]">
                            {load.contract_rate != null && (
                              <span className="text-blue-600">Contract: {formatCurrency(load.contract_rate)}</span>
                            )}
                            {load.spot_rate != null && (
                              <span className="text-amber-600">Spot: {formatCurrency(load.spot_rate)}</span>
                            )}
                            {load.benchmark_rate != null && (
                              <span className="text-gray-500">DAT: {formatCurrency(load.benchmark_rate)}</span>
                            )}
                          </div>
                        )}
                        {/* Carrier (for accepted/in-transit/delivered) */}
                        {load.carrier && (
                          <div className="text-indigo-700 font-medium truncate">
                            {load.carrier}
                          </div>
                        )}
                      </div>

                      {/* Waterfall Tender Panel (expanded for TENDERING loads) */}
                      {isTendering && isExpanded && (
                        <div className="mt-1 p-2 rounded border border-amber-200 bg-amber-50/50 text-xs space-y-1.5">
                          <div className="font-semibold text-amber-800 text-[10px] uppercase tracking-wider">
                            Tender Waterfall
                          </div>
                          {load.tender_waterfall && load.tender_waterfall.length > 0 ? (
                            load.tender_waterfall.map((tier, tierIdx) => {
                              const tierNum = tier.tier || (tierIdx + 1);
                              const isActive = tier.is_active === true;
                              return (
                                <div
                                  key={tierIdx}
                                  className={cn(
                                    'p-1.5 rounded border',
                                    isActive ? 'bg-amber-100 border-amber-300' : 'bg-white border-gray-200'
                                  )}
                                >
                                  <div className="flex items-center justify-between mb-0.5">
                                    <span className={cn('font-medium', isActive && 'text-amber-800')}>
                                      {TIER_LABELS[tierNum] || `Tier ${tierNum}`}
                                      {isActive && ' (Active)'}
                                    </span>
                                  </div>
                                  {tier.carriers && tier.carriers.length > 0 ? (
                                    tier.carriers.map((c, cIdx) => (
                                      <div key={cIdx} className="flex items-center justify-between pl-2 py-0.5">
                                        <span className="truncate">{c.carrier_name || c.carrier || '\u2014'}</span>
                                        <div className="flex items-center gap-2">
                                          {c.rate != null && (
                                            <span className="text-gray-500">{formatCurrency(c.rate)}</span>
                                          )}
                                          <Badge
                                            variant="outline"
                                            className={cn(
                                              'text-[9px]',
                                              TENDER_RESPONSE_COLORS[c.response] || TENDER_RESPONSE_COLORS.PENDING
                                            )}
                                          >
                                            {c.response || 'PENDING'}
                                          </Badge>
                                          {c.response_time && (
                                            <span className="text-gray-400 text-[9px]">{c.response_time}</span>
                                          )}
                                        </div>
                                      </div>
                                    ))
                                  ) : (
                                    <div className="text-gray-400 pl-2">{'\u2014'}</div>
                                  )}
                                </div>
                              );
                            })
                          ) : (
                            <div className="text-gray-400 py-1">
                              No waterfall tender data available for this load.
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Bottom Summary */}
      {loads.length > 0 && (
        <div className="flex flex-wrap items-center gap-4 p-3 bg-gray-50 rounded-lg border text-xs text-gray-600">
          <span className="font-medium">Total: {loads.length} loads</span>
          <span className="text-gray-300">|</span>
          {STATUSES.map((status) => (
            <span key={status}>
              {status.replace('_', ' ')}: {statusCounts[status]}
            </span>
          ))}
          <span className="text-gray-300">|</span>
          <span className="flex items-center gap-1">
            <TrendingUp className="h-3 w-3" />
            Tender Accept Rate: {summaryMetrics?.tenderAcceptRate != null
              ? `${summaryMetrics.tenderAcceptRate.toFixed(1)}%`
              : '\u2014'}
          </span>
          <span className="flex items-center gap-1">
            <DollarSign className="h-3 w-3" />
            Avg Cost/Load: {summaryMetrics?.avgCostPerLoad != null
              ? formatCurrency(summaryMetrics.avgCostPerLoad)
              : '\u2014'}
          </span>
        </div>
      )}
    </div>
  );
};

export default LoadBoard;
