import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Spinner,
} from '../../components/common';
import {
  Warehouse,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  RefreshCw,
  Calendar,
  MapPin,
  ChevronRight,
  Activity,
} from 'lucide-react';
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import MaterialFlowSankey from '../../components/planning/MaterialFlowSankey';

/**
 * Warehouse Capacity Utilization — Time-series view of DC utilization.
 *
 * For inventory-only configs (DCs, no manufacturers):
 *   - Storage utilization: inventory position / estimated warehouse capacity
 *   - Throughput utilization: order volume / estimated max throughput
 *
 * Data sources:
 *   - /demand-plan/aggregated — demand volumes by time bucket
 *   - /demand-plan/hierarchy-dimensions — sites with geography for filtering
 *   - /inventory-projection/projections — inventory levels over time
 */

// --- Time frame helpers ---

function startOfWeek(d) {
  const dt = new Date(d);
  dt.setDate(dt.getDate() - dt.getDay() + 1); // Monday
  return dt;
}

function formatDate(d) {
  return d.toISOString().split('T')[0];
}

function getTimeFrameRange(preset) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  switch (preset) {
    case 'next_week': {
      const start = new Date(today);
      const end = new Date(today);
      end.setDate(end.getDate() + 7);
      return { start: formatDate(start), end: formatDate(end), label: 'Next Week' };
    }
    case 'next_4_weeks': {
      const start = new Date(today);
      const end = new Date(today);
      end.setDate(end.getDate() + 28);
      return { start: formatDate(start), end: formatDate(end), label: 'Next 4 Weeks' };
    }
    case 'calendar_month': {
      const start = new Date(today.getFullYear(), today.getMonth(), 1);
      const end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
      return { start: formatDate(start), end: formatDate(end), label: 'Calendar Month' };
    }
    case 'calendar_quarter': {
      const qStart = Math.floor(today.getMonth() / 3) * 3;
      const start = new Date(today.getFullYear(), qStart, 1);
      const end = new Date(today.getFullYear(), qStart + 3, 0);
      return { start: formatDate(start), end: formatDate(end), label: 'Calendar Quarter' };
    }
    default:
      return null;
  }
}

const TIME_PRESETS = [
  { key: 'next_week', label: 'Next Week' },
  { key: 'next_4_weeks', label: 'Next 4 Weeks' },
  { key: 'calendar_month', label: 'Calendar Month' },
  { key: 'calendar_quarter', label: 'Calendar Quarter' },
  { key: 'custom', label: 'Custom' },
];

// --- Utilization computation ---

/**
 * Estimate warehouse capacity from site data.
 * Since we don't have explicit capacity fields, we estimate from peak inventory.
 * Capacity = peak inventory * 1.25 (assuming 80% target utilization at peak).
 */
function estimateCapacityFromData(inventoryBySite, demandBySite) {
  const caps = {};
  for (const [siteId, records] of Object.entries(inventoryBySite)) {
    const peakInv = Math.max(...records.map(r => r.quantity || 0), 1);
    caps[siteId] = {
      storageCapacity: Math.round(peakInv * 1.25),
      throughputCapacity: null, // set from demand peak
    };
  }
  for (const [siteId, records] of Object.entries(demandBySite)) {
    const peakDemand = Math.max(...records.map(r => r.volume || 0), 1);
    if (!caps[siteId]) caps[siteId] = { storageCapacity: null, throughputCapacity: null };
    caps[siteId].throughputCapacity = Math.round(peakDemand * 1.3);
  }
  return caps;
}

const ResourceCapacity = () => {
  const { effectiveConfigId } = useActiveConfig();

  // Time frame
  const [timePreset, setTimePreset] = useState('next_4_weeks');
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');

  // Geography filter
  const [dimensions, setDimensions] = useState(null);
  const [geoFilter, setGeoFilter] = useState(null); // { level, key, label }
  const [siteFilter, setSiteFilter] = useState(null);

  // Data
  const [demandSeries, setDemandSeries] = useState(null);
  const [inventoryData, setInventoryData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Compute date range
  const dateRange = useMemo(() => {
    if (timePreset === 'custom') {
      if (customStart && customEnd) {
        return { start: customStart, end: customEnd, label: 'Custom' };
      }
      return null;
    }
    return getTimeFrameRange(timePreset);
  }, [timePreset, customStart, customEnd]);

  // Load hierarchy dimensions (sites + geography)
  useEffect(() => {
    if (!effectiveConfigId) return;
    api.get('/demand-plan/hierarchy-dimensions', { params: { config_id: effectiveConfigId } })
      .then(res => setDimensions(res.data))
      .catch(() => setDimensions(null));
  }, [effectiveConfigId]);

  // Sites for geography filter
  const sites = useMemo(() => {
    if (!dimensions?.sites) return [];
    return dimensions.sites;
  }, [dimensions]);

  // Geography tree from dimensions
  const geoTree = useMemo(() => dimensions?.geography || [], [dimensions]);

  // Geo children for current level
  const geoChildren = useMemo(() => {
    if (!geoTree.length) return [];
    if (!geoFilter) {
      // Top level: unique regions
      const regions = [...new Set(geoTree.map(g => g.region).filter(Boolean))].sort();
      return regions.map(r => ({ level: 'region', key: r, label: r }));
    }
    if (geoFilter.level === 'region') {
      const states = [...new Set(
        geoTree.filter(g => g.region === geoFilter.key).map(g => g.state).filter(Boolean)
      )].sort();
      return states.map(s => ({ level: 'state', key: s, label: s }));
    }
    if (geoFilter.level === 'state') {
      const cities = [...new Set(
        geoTree.filter(g => g.state === geoFilter.key).map(g => g.city).filter(Boolean)
      )].sort();
      return cities.map(c => ({ level: 'city', key: c, label: c }));
    }
    return [];
  }, [geoTree, geoFilter]);

  // Breadcrumb trail
  const geoBreadcrumbs = useMemo(() => {
    const crumbs = [{ level: null, key: null, label: 'All Geographies' }];
    if (geoFilter) {
      if (geoFilter.level === 'region' || geoFilter.level === 'state' || geoFilter.level === 'city') {
        // Find parent chain
        if (geoFilter.level === 'state' || geoFilter.level === 'city') {
          const geo = geoTree.find(g =>
            geoFilter.level === 'state' ? g.state === geoFilter.key : g.city === geoFilter.key
          );
          if (geo?.region) crumbs.push({ level: 'region', key: geo.region, label: geo.region });
          if (geoFilter.level === 'city' && geo?.state) {
            crumbs.push({ level: 'state', key: geo.state, label: geo.state });
          }
        }
        crumbs.push(geoFilter);
      }
    }
    return crumbs;
  }, [geoFilter, geoTree]);

  // Filtered site IDs based on geo selection
  const filteredSiteIds = useMemo(() => {
    if (siteFilter) return [siteFilter];
    if (!geoFilter || !geoTree.length) return null; // null = all
    // Find geo IDs matching the filter
    let matchingGeos;
    if (geoFilter.level === 'region') {
      matchingGeos = geoTree.filter(g => g.region === geoFilter.key).map(g => g.id);
    } else if (geoFilter.level === 'state') {
      matchingGeos = geoTree.filter(g => g.state === geoFilter.key).map(g => g.id);
    } else if (geoFilter.level === 'city') {
      matchingGeos = geoTree.filter(g => g.city === geoFilter.key).map(g => g.id);
    } else {
      return null;
    }
    const geoSet = new Set(matchingGeos.map(String));
    return sites.filter(s => geoSet.has(String(s.geo_id))).map(s => s.id);
  }, [geoFilter, siteFilter, geoTree, sites]);

  // Load data
  const fetchData = useCallback(async () => {
    if (!effectiveConfigId || !dateRange) return;
    setLoading(true);
    setError(null);

    try {
      const params = {
        config_id: effectiveConfigId,
        time_bucket: 'week',
        start_date: dateRange.start,
        end_date: dateRange.end,
      };

      // If filtering by specific site via geo drill
      if (siteFilter) {
        params.site_id = siteFilter;
      }

      // Fetch demand and inventory in parallel
      const [demandRes, invRes] = await Promise.allSettled([
        api.get('/demand-plan/aggregated', { params }),
        api.get('/inventory-projection/projections', {
          params: {
            start_date: dateRange.start,
            end_date: dateRange.end,
            page_size: 100,
          },
        }),
      ]);

      if (demandRes.status === 'fulfilled') {
        setDemandSeries(demandRes.value.data);
      } else {
        setDemandSeries(null);
      }

      if (invRes.status === 'fulfilled') {
        setInventoryData(invRes.value.data);
      } else {
        setInventoryData(null);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load capacity data');
    } finally {
      setLoading(false);
    }
  }, [effectiveConfigId, dateRange, siteFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // --- Compute utilization series ---
  const { chartData, siteCards, summaryStats } = useMemo(() => {
    const series = demandSeries?.series || [];
    const invItems = inventoryData?.items || inventoryData || [];

    if (!series.length && !invItems.length) {
      return { chartData: [], siteCards: [], summaryStats: null };
    }

    // Group inventory by date bucket
    const invByDate = {};
    const invBySite = {};
    const invArr = Array.isArray(invItems) ? invItems : [];
    for (const inv of invArr) {
      const d = inv.projection_date || inv.date;
      if (!d) continue;
      const dateKey = d.substring(0, 10);
      if (!invByDate[dateKey]) invByDate[dateKey] = [];
      invByDate[dateKey].push(inv);

      const sid = inv.site_id || 'unknown';
      if (!invBySite[sid]) invBySite[sid] = [];
      invBySite[sid].push({ ...inv, dateKey });
    }

    // Group demand by date
    const demandByDate = {};
    const demandBySite = {};
    for (const pt of series) {
      const d = pt.date;
      if (!d) continue;
      demandByDate[d] = pt;
      // demand series is aggregated, not per-site
    }

    // Estimate capacities from peaks in the data
    const allDates = [...new Set([
      ...Object.keys(invByDate),
      ...Object.keys(demandByDate),
    ])].sort();

    // Peak values for capacity estimation
    const peakInv = Math.max(
      ...Object.values(invByDate).map(arr =>
        arr.reduce((s, i) => s + (i.projected_on_hand || i.on_hand_qty || 0), 0)
      ),
      1
    );
    const peakDemand = Math.max(
      ...series.map(s => s.p50 || 0),
      1
    );

    const estStorageCapacity = Math.round(peakInv * 1.25);
    const estThroughputCapacity = Math.round(peakDemand * 1.3);

    // Build chart data
    const chart = allDates.map(date => {
      const inv = invByDate[date] || [];
      const demand = demandByDate[date];

      const totalInv = inv.reduce((s, i) => s + (i.projected_on_hand || i.on_hand_qty || 0), 0);
      const totalDemand = demand?.p50 || 0;

      const storageUtil = estStorageCapacity > 0
        ? Math.round((totalInv / estStorageCapacity) * 1000) / 10
        : 0;
      const throughputUtil = estThroughputCapacity > 0
        ? Math.round((totalDemand / estThroughputCapacity) * 1000) / 10
        : 0;

      return {
        date,
        dateLabel: new Date(date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        storageUtil: Math.min(storageUtil, 120),
        throughputUtil: Math.min(throughputUtil, 120),
        inventoryUnits: totalInv,
        demandUnits: totalDemand,
        storageCapacity: estStorageCapacity,
        throughputCapacity: estThroughputCapacity,
      };
    });

    // Per-site cards
    const siteMap = {};
    for (const s of sites) {
      siteMap[s.id] = s;
    }

    const sCards = [];
    const invSiteIds = Object.keys(invBySite);

    for (const sid of invSiteIds) {
      const siteInfo = siteMap[sid] || { id: sid, name: `Site ${sid}` };
      const siteInv = invBySite[sid] || [];

      // Sort by date
      siteInv.sort((a, b) => (a.dateKey || '').localeCompare(b.dateKey || ''));

      const currentInv = siteInv.length > 0
        ? siteInv[siteInv.length - 1].projected_on_hand || siteInv[siteInv.length - 1].on_hand_qty || 0
        : 0;
      const prevInv = siteInv.length > 1
        ? siteInv[siteInv.length - 2].projected_on_hand || siteInv[siteInv.length - 2].on_hand_qty || 0
        : currentInv;

      const sitePeak = Math.max(...siteInv.map(i => i.projected_on_hand || i.on_hand_qty || 0), 1);
      const siteCapacity = Math.round(sitePeak * 1.25);
      const utilPct = siteCapacity > 0 ? Math.round((currentInv / siteCapacity) * 100) : 0;
      const trend = currentInv > prevInv ? 'up' : currentInv < prevInv ? 'down' : 'flat';

      // Apply geo filter
      if (filteredSiteIds && !filteredSiteIds.includes(Number(sid)) && !filteredSiteIds.includes(String(sid))) {
        continue;
      }

      sCards.push({
        siteId: sid,
        siteName: siteInfo.name,
        siteType: siteInfo.type,
        currentInventory: currentInv,
        estimatedCapacity: siteCapacity,
        utilization: utilPct,
        trend,
        recordCount: siteInv.length,
      });
    }

    // If no inventory data but we have demand, show demand-based cards per site from dimensions
    if (!sCards.length && series.length) {
      for (const s of sites) {
        if (filteredSiteIds && !filteredSiteIds.includes(Number(s.id)) && !filteredSiteIds.includes(String(s.id))) {
          continue;
        }
        if (s.type === 'MANUFACTURER') continue;
        sCards.push({
          siteId: s.id,
          siteName: s.name,
          siteType: s.type,
          currentInventory: null,
          estimatedCapacity: null,
          utilization: null,
          trend: 'flat',
          recordCount: 0,
        });
      }
    }

    // Summary
    const avgStorage = chart.length > 0
      ? Math.round(chart.reduce((s, c) => s + c.storageUtil, 0) / chart.length)
      : 0;
    const avgThroughput = chart.length > 0
      ? Math.round(chart.reduce((s, c) => s + c.throughputUtil, 0) / chart.length)
      : 0;
    const peakStorageUtil = chart.length > 0
      ? Math.max(...chart.map(c => c.storageUtil))
      : 0;
    const alertCount = chart.filter(c => c.storageUtil >= 95 || c.throughputUtil >= 95).length;

    return {
      chartData: chart,
      siteCards: sCards.sort((a, b) => (b.utilization || 0) - (a.utilization || 0)),
      summaryStats: {
        avgStorage,
        avgThroughput,
        peakStorageUtil,
        alertCount,
        sitesMonitored: sCards.length,
        timeBuckets: chart.length,
      },
    };
  }, [demandSeries, inventoryData, sites, filteredSiteIds]);

  const utilColor = (pct) => {
    if (pct >= 95) return 'text-red-600';
    if (pct >= 85) return 'text-amber-600';
    return 'text-green-600';
  };

  const utilBgColor = (pct) => {
    if (pct >= 95) return 'bg-red-500';
    if (pct >= 85) return 'bg-amber-500';
    return 'bg-green-500';
  };

  const TrendIcon = ({ trend }) => {
    if (trend === 'up') return <TrendingUp className="h-4 w-4 text-amber-500" />;
    if (trend === 'down') return <TrendingDown className="h-4 w-4 text-green-500" />;
    return <Minus className="h-4 w-4 text-muted-foreground" />;
  };

  if (!effectiveConfigId) {
    return (
      <div className="py-16 text-center text-muted-foreground">
        <Warehouse className="h-12 w-12 mx-auto mb-3 opacity-50" />
        <p>No active configuration. Select a supply chain config to view capacity utilization.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <span className="ml-2">{error}</span>
        </Alert>
      )}

      {/* Time Frame Selector */}
      <Card>
        <CardContent className="py-3">
          <div className="flex flex-wrap items-center gap-3">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium text-muted-foreground">Time Frame:</span>
            {TIME_PRESETS.map(p => (
              <Button
                key={p.key}
                size="sm"
                variant={timePreset === p.key ? 'default' : 'outline'}
                onClick={() => setTimePreset(p.key)}
              >
                {p.label}
              </Button>
            ))}
            {timePreset === 'custom' && (
              <div className="flex items-center gap-2 ml-2">
                <input
                  type="date"
                  className="border rounded px-2 py-1 text-sm"
                  value={customStart}
                  onChange={e => setCustomStart(e.target.value)}
                />
                <span className="text-muted-foreground">to</span>
                <input
                  type="date"
                  className="border rounded px-2 py-1 text-sm"
                  value={customEnd}
                  onChange={e => setCustomEnd(e.target.value)}
                />
              </div>
            )}
            <Button size="sm" variant="ghost" onClick={fetchData}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Geography Hierarchy Filter */}
      <Card>
        <CardContent className="py-3">
          <div className="flex flex-wrap items-center gap-2">
            <MapPin className="h-4 w-4 text-muted-foreground" />
            {/* Breadcrumbs */}
            {geoBreadcrumbs.map((crumb, i) => (
              <React.Fragment key={i}>
                {i > 0 && <ChevronRight className="h-3 w-3 text-muted-foreground" />}
                <button
                  className={`text-sm px-2 py-0.5 rounded hover:bg-accent ${
                    i === geoBreadcrumbs.length - 1 ? 'font-semibold text-primary' : 'text-muted-foreground'
                  }`}
                  onClick={() => {
                    if (crumb.level === null) {
                      setGeoFilter(null);
                      setSiteFilter(null);
                    } else {
                      setGeoFilter(crumb);
                      setSiteFilter(null);
                    }
                  }}
                >
                  {crumb.label}
                </button>
              </React.Fragment>
            ))}
            {/* Children chips */}
            {geoChildren.length > 0 && (
              <>
                <ChevronRight className="h-3 w-3 text-muted-foreground" />
                <div className="flex flex-wrap gap-1">
                  {geoChildren.map(child => (
                    <Badge
                      key={child.key}
                      variant="outline"
                      className="cursor-pointer hover:bg-accent"
                      onClick={() => {
                        setGeoFilter(child);
                        setSiteFilter(null);
                      }}
                    >
                      {child.label}
                    </Badge>
                  ))}
                </div>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Summary Stats */}
      {summaryStats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Card>
            <CardContent className="py-3 text-center">
              <p className="text-xs text-muted-foreground">Avg Storage Util</p>
              <p className={`text-2xl font-bold ${utilColor(summaryStats.avgStorage)}`}>
                {summaryStats.avgStorage}%
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3 text-center">
              <p className="text-xs text-muted-foreground">Avg Throughput Util</p>
              <p className={`text-2xl font-bold ${utilColor(summaryStats.avgThroughput)}`}>
                {summaryStats.avgThroughput}%
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3 text-center">
              <p className="text-xs text-muted-foreground">Peak Storage</p>
              <p className={`text-2xl font-bold ${utilColor(summaryStats.peakStorageUtil)}`}>
                {summaryStats.peakStorageUtil}%
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3 text-center">
              <p className="text-xs text-muted-foreground">Critical Periods</p>
              <p className={`text-2xl font-bold ${summaryStats.alertCount > 0 ? 'text-red-600' : 'text-green-600'}`}>
                {summaryStats.alertCount}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-3 text-center">
              <p className="text-xs text-muted-foreground">Sites Monitored</p>
              <p className="text-2xl font-bold">{summaryStats.sitesMonitored}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Time-Series Chart */}
      <Card>
        <CardContent className="pt-4">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Warehouse Capacity Utilization Over Time
            {dateRange && (
              <span className="text-xs font-normal text-muted-foreground">
                ({dateRange.start} to {dateRange.end})
              </span>
            )}
          </h3>
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <Spinner className="h-8 w-8" />
              <span className="ml-3 text-muted-foreground">Loading utilization data...</span>
            </div>
          ) : chartData.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
              <Warehouse className="h-12 w-12 mb-3 opacity-50" />
              <p>No utilization data available for the selected time frame.</p>
              <p className="text-xs mt-1">Ensure inventory projections and demand forecasts have been generated.</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={360}>
              <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis
                  dataKey="dateLabel"
                  tick={{ fontSize: 11 }}
                  interval="preserveStartEnd"
                />
                <YAxis
                  domain={[0, 120]}
                  tick={{ fontSize: 11 }}
                  tickFormatter={v => `${v}%`}
                  label={{ value: 'Utilization %', angle: -90, position: 'insideLeft', style: { fontSize: 11 } }}
                />
                <Tooltip
                  formatter={(value, name) => {
                    const labels = {
                      storageUtil: 'Storage Utilization',
                      throughputUtil: 'Throughput Utilization',
                    };
                    return [`${value}%`, labels[name] || name];
                  }}
                  labelFormatter={(label) => label}
                  contentStyle={{ fontSize: 12 }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <ReferenceLine y={85} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: '85% Warning', position: 'right', style: { fontSize: 10, fill: '#f59e0b' } }} />
                <ReferenceLine y={95} stroke="#ef4444" strokeDasharray="4 4" label={{ value: '95% Critical', position: 'right', style: { fontSize: 10, fill: '#ef4444' } }} />
                <Area
                  type="monotone"
                  dataKey="storageUtil"
                  name="Storage Utilization"
                  stroke="#3b82f6"
                  fill="#3b82f6"
                  fillOpacity={0.1}
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="throughputUtil"
                  name="Throughput Utilization"
                  stroke="#8b5cf6"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Material Flow Sankey */}
      <MaterialFlowSankey />

      {/* Site-Level Breakdown Cards */}
      {siteCards.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Warehouse className="h-4 w-4" />
            Site-Level Breakdown
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {siteCards.map(site => (
              <Card
                key={site.siteId}
                className={`cursor-pointer hover:shadow-md transition-shadow ${
                  site.utilization >= 95 ? 'border-red-300 border-2' :
                  site.utilization >= 85 ? 'border-amber-300' : ''
                }`}
                onClick={() => {
                  if (siteFilter === site.siteId) {
                    setSiteFilter(null);
                  } else {
                    setSiteFilter(site.siteId);
                  }
                }}
              >
                <CardContent className="py-3">
                  <div className="flex justify-between items-start">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm truncate">{site.siteName}</span>
                        {site.siteType && (
                          <Badge variant="outline" className="text-xs shrink-0">{site.siteType}</Badge>
                        )}
                        {siteFilter === site.siteId && (
                          <Badge variant="default" className="text-xs shrink-0">Filtered</Badge>
                        )}
                      </div>
                      {site.utilization !== null ? (
                        <>
                          <div className="flex items-center gap-2 mt-2">
                            <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                              <div
                                className={`h-full ${utilBgColor(site.utilization)} rounded-full transition-all`}
                                style={{ width: `${Math.min(site.utilization, 100)}%` }}
                              />
                            </div>
                            <span className={`text-sm font-mono font-bold ${utilColor(site.utilization)}`}>
                              {site.utilization}%
                            </span>
                            <TrendIcon trend={site.trend} />
                          </div>
                          <div className="flex gap-4 mt-1.5 text-xs text-muted-foreground">
                            <span>Inventory: {site.currentInventory?.toLocaleString()} units</span>
                            <span>Capacity: {site.estimatedCapacity?.toLocaleString()} units</span>
                          </div>
                        </>
                      ) : (
                        <p className="text-xs text-muted-foreground mt-1">No inventory projection data</p>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default ResourceCapacity;
