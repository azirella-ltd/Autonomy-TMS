import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';
import {
  Card, CardContent, CardHeader, CardTitle,
  Badge, Button, Spinner, Alert, AlertDescription,
} from '../../components/common';
import {
  Truck, RefreshCw, Filter, Search, Package, MapPin, Calendar,
} from 'lucide-react';

const STATUSES = ['PLANNING', 'TENDERED', 'ACCEPTED', 'IN_TRANSIT', 'DELIVERED'];

const STATUS_COLORS = {
  PLANNING: 'bg-slate-100 border-slate-300 text-slate-700',
  TENDERED: 'bg-amber-50 border-amber-300 text-amber-700',
  ACCEPTED: 'bg-blue-50 border-blue-300 text-blue-700',
  IN_TRANSIT: 'bg-indigo-50 border-indigo-300 text-indigo-700',
  DELIVERED: 'bg-emerald-50 border-emerald-300 text-emerald-700',
};

const STATUS_HEADER_COLORS = {
  PLANNING: 'bg-slate-500',
  TENDERED: 'bg-amber-500',
  ACCEPTED: 'bg-blue-500',
  IN_TRANSIT: 'bg-indigo-500',
  DELIVERED: 'bg-emerald-500',
};

const MODES = ['All', 'FTL', 'LTL', 'Intermodal'];

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

const formatWeight = (weight) => {
  if (weight == null) return '\u2014';
  return `${Number(weight).toLocaleString()} lbs`;
};

const LoadBoard = () => {
  const [loads, setLoads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
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

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
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
                {loadsByStatus[status].map((load) => (
                  <div
                    key={load.id || load.load_id}
                    className={cn(
                      'p-2 rounded border text-xs space-y-1 shadow-sm',
                      STATUS_COLORS[status]
                    )}
                  >
                    <div className="font-semibold truncate">
                      {load.load_id || load.id || '\u2014'}
                    </div>
                    <div className="flex items-center gap-1 text-gray-600">
                      <MapPin className="h-3 w-3" />
                      <span className="truncate">
                        {load.origin || '\u2014'} → {load.destination || '\u2014'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>{load.mode || '\u2014'}</span>
                      <span>{load.equipment_type || '\u2014'}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>{formatWeight(load.weight)}</span>
                      <span>{formatDate(load.pickup_date)}</span>
                    </div>
                    {load.carrier && (
                      <div className="text-indigo-700 font-medium truncate">
                        {load.carrier}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Bottom Summary */}
      {loads.length > 0 && (
        <div className="flex items-center gap-4 p-3 bg-gray-50 rounded-lg border text-xs text-gray-600">
          <span className="font-medium">Total: {loads.length} loads</span>
          <span className="text-gray-300">|</span>
          {STATUSES.map((status) => (
            <span key={status}>
              {status.replace('_', ' ')}: {statusCounts[status]}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

export default LoadBoard;
