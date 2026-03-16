import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  AlertDescription,
  Badge,
  Label,
  Spinner,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableContainer,
  Tabs,
  TabsList,
  TabsTrigger,
} from '../../components/common';
import {
  LayoutDashboard,
  RefreshCw,
  AlertTriangle,
  TrendingUp,
  Package,
  ShoppingCart,
  ShieldAlert,
  ChevronRight,
  MapPin,
  Calendar,
} from 'lucide-react';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import ScenarioContextBar from '../../components/planning/ScenarioContextBar';
import {
  ComposedChart,
  Area,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { cn } from '../../lib/utils/cn';


const fmt = (v) => {
  if (v == null) return '-';
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
};


// ─── Hierarchy dimension config ────────────────────────────────────────────
const DIMENSION_META = {
  site: { label: 'Geography', icon: MapPin, color: 'text-blue-600', allLabel: 'All Sites' },
  product: { label: 'Product', icon: Package, color: 'text-green-600', allLabel: 'All Products' },
  time: { label: 'Time', icon: Calendar, color: 'text-amber-600', allLabel: 'All Periods' },
};

// ─── KPI Card ──────────────────────────────────────────────────────────────
const KPICard = ({ icon: Icon, title, value, subtitle, color }) => (
  <Card className="flex-1 min-w-[200px]">
    <CardContent className="p-4">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg bg-${color}-100 dark:bg-${color}-900/30`}>
          <Icon className={`h-5 w-5 text-${color}-600 dark:text-${color}-400`} />
        </div>
        <div className="min-w-0">
          <p className="text-sm text-muted-foreground truncate">{title}</p>
          <p className="text-2xl font-bold">{value}</p>
          {subtitle && (
            <p className="text-xs text-muted-foreground">{subtitle}</p>
          )}
        </div>
      </div>
    </CardContent>
  </Card>
);


const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="bg-popover border border-border rounded-lg shadow-lg p-3 text-sm max-w-xs">
      <p className="font-semibold mb-2">{label}</p>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="flex justify-between gap-4">
          <span style={{ color: entry.color || entry.stroke }}>
            {entry.name}
          </span>
          <span className="font-mono">{fmt(entry.value)}</span>
        </div>
      ))}
    </div>
  );
};


const SupplyBreakdownTooltip = ({ po, to, mo }) => {
  if (!po && !to && !mo) return null;
  return (
    <span className="text-xs text-muted-foreground ml-1" title={`PO: ${fmt(po)} | TO: ${fmt(to)} | MO: ${fmt(mo)}`}>
      (PO:{fmt(po)} TO:{fmt(to)} MO:{fmt(mo)})
    </span>
  );
};


const inventoryCellClass = (closing, safety) => {
  if (closing == null || safety == null) return '';
  if (closing < safety) return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300';
  if (closing < safety * 1.5) return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300';
  return 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300';
};


// ─── Hierarchy Navigation Row ──────────────────────────────────────────────
// Combines breadcrumb trail + filter dropdown for one dimension.
// The breadcrumbs show the current aggregation path; the dropdown shows
// children at the current level for filtering within that level.
const HierarchyRow = ({ dimension, crumbs, childItems, onBreadcrumbClick, onDrillDown }) => {
  const meta = DIMENSION_META[dimension];
  const Icon = meta.icon;

  return (
    <div className="flex items-center gap-2 min-w-0 flex-wrap">
      {/* Dimension icon & label */}
      <Icon className={cn('h-4 w-4 flex-shrink-0', meta.color)} />
      <span className="text-xs font-medium text-muted-foreground flex-shrink-0 w-16">
        {meta.label}:
      </span>

      {/* Breadcrumb trail */}
      <div className="flex items-center gap-1 min-w-0 flex-wrap">
        {crumbs.map((crumb, i) => (
          <React.Fragment key={`${crumb.level}-${crumb.key}`}>
            {i > 0 && <ChevronRight className="h-3 w-3 text-muted-foreground flex-shrink-0" />}
            {crumb.is_current ? (
              <Badge variant="default" className="text-xs px-2 py-0.5">
                {crumb.label}
              </Badge>
            ) : (
              <button
                onClick={() => onBreadcrumbClick(dimension, crumb.level, crumb.key)}
                className="text-xs text-primary hover:underline cursor-pointer"
              >
                {crumb.label}
              </button>
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Filter dropdown (shows children at current level) */}
      {childItems && childItems.length > 0 && (
        <div className="flex items-center gap-1.5 ml-2">
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
          <Select
            value="__all__"
            onValueChange={(val) => {
              if (val !== '__all__') {
                const child = childItems.find((c) => c.key === val);
                if (child) onDrillDown(dimension, child.level, child.key);
              }
            }}
          >
            <SelectTrigger className="h-7 text-xs min-w-[140px] max-w-[220px]">
              <SelectValue placeholder={`Filter ${meta.label.toLowerCase()}...`} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">
                {meta.allLabel} ({childItems.length})
              </SelectItem>
              {childItems.map((child) => (
                <SelectItem key={child.key} value={child.key}>
                  {child.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
    </div>
  );
};


// ─── Main Component ────────────────────────────────────────────────────────

const PlanningBoard = () => {
  const { effectiveConfigId, activeConfig } = useActiveConfig();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [timelineData, setTimelineData] = useState(null);

  // Hierarchy state: level + key per dimension
  const [siteLevel, setSiteLevel] = useState('company');
  const [siteKey, setSiteKey] = useState('ALL');
  const [productLevel, setProductLevel] = useState('category');
  const [productKey, setProductKey] = useState('ALL');
  const [timeLevel, setTimeLevel] = useState('year');
  const [timeKey, setTimeKey] = useState(null); // null = default to current year
  const [planVersion, setPlanVersion] = useState('');

  // Active group tab (when multiple groups returned)
  const [activeGroupIdx, setActiveGroupIdx] = useState(0);

  // Fetch netting timeline with current hierarchy position
  const loadTimeline = useCallback(async () => {
    if (!effectiveConfigId) return;
    setLoading(true);
    setError(null);
    try {
      const params = {
        config_id: effectiveConfigId,
        site_level: siteLevel,
        site_key: siteKey,
        product_level: productLevel,
        product_key: productKey,
        time_level: timeLevel,
      };
      if (timeKey) params.time_key = timeKey;
      if (planVersion) params.plan_version = planVersion;

      const res = await api.get('/planning-board/netting-timeline', { params });
      setTimelineData(res.data);
      setActiveGroupIdx(0);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load netting timeline');
      setTimelineData(null);
    } finally {
      setLoading(false);
    }
  }, [effectiveConfigId, siteLevel, siteKey, productLevel, productKey, timeLevel, timeKey, planVersion]);

  useEffect(() => {
    if (effectiveConfigId) loadTimeline();
  }, [loadTimeline]);

  // ─── Hierarchy navigation handlers ───────────────────────────────────
  const handleDrillDown = useCallback((dimension, level, key) => {
    if (dimension === 'site') { setSiteLevel(level); setSiteKey(key); }
    else if (dimension === 'product') { setProductLevel(level); setProductKey(key); }
    else if (dimension === 'time') { setTimeLevel(level); setTimeKey(key); }
  }, []);

  const handleBreadcrumbClick = useCallback((dimension, level, key) => {
    handleDrillDown(dimension, level, key);
  }, [handleDrillDown]);

  // ─── Derived data from active group ──────────────────────────────────
  const activeGroup = useMemo(() => {
    if (!timelineData?.groups?.length) return null;
    const idx = Math.min(activeGroupIdx, timelineData.groups.length - 1);
    return timelineData.groups[idx];
  }, [timelineData, activeGroupIdx]);

  const buckets = useMemo(() => activeGroup?.buckets || [], [activeGroup]);

  const chartData = useMemo(
    () =>
      buckets.map((b) => ({
        period: b.period_label,
        closing_inventory: b.closing_inventory,
        safety_stock: b.safety_stock,
        gross_demand: b.gross_demand,
        planned_orders: b.planned_orders,
        projected_inv_low: b.projected_inv_low,
        projected_inv_high: b.projected_inv_high,
      })),
    [buckets],
  );

  const kpis = useMemo(() => {
    if (!buckets.length)
      return { totalDemand: 0, totalSupply: 0, avgClosing: 0, stockoutRisk: 0 };
    const totalDemand = buckets.reduce((s, b) => s + (b.gross_demand || 0), 0);
    const totalSupply = buckets.reduce((s, b) => s + (b.planned_orders || 0), 0);
    const avgClosing =
      buckets.reduce((s, b) => s + (b.closing_inventory || 0), 0) / buckets.length;
    const stockoutRisk = buckets.filter(
      (b) => b.closing_inventory != null && b.safety_stock != null && b.closing_inventory < b.safety_stock,
    ).length;
    return { totalDemand, totalSupply, avgClosing, stockoutRisk };
  }, [buckets]);

  const nettingRows = useMemo(() => [
    { key: 'opening_inventory', label: 'Opening Inventory' },
    { key: 'gross_demand', label: 'Gross Demand' },
    { key: 'scheduled_receipts', label: 'Scheduled Receipts' },
    { key: 'net_requirement', label: 'Net Requirement' },
    { key: 'planned_orders', label: 'Planned Orders' },
    { key: 'closing_inventory', label: 'Closing Inventory' },
    { key: 'safety_stock', label: 'Safety Stock' },
  ], []);

  const cellClassName = (rowKey, bucket) => {
    if (rowKey === 'closing_inventory') {
      return inventoryCellClass(bucket.closing_inventory, bucket.safety_stock);
    }
    if (rowKey === 'net_requirement' && bucket.net_requirement > 0) {
      return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300';
    }
    return '';
  };

  const hasData = timelineData?.groups?.length > 0;
  const breadcrumbs = timelineData?.breadcrumbs;
  const childrenNav = timelineData?.children;

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <LayoutDashboard className="h-7 w-7 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">Planning Board</h1>
            <p className="text-sm text-muted-foreground">
              Unified demand-supply matching with hierarchical drill-down
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {activeConfig && (
            <Badge variant="outline" className="text-sm">
              {activeConfig.name}
            </Badge>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={loadTimeline}
            disabled={loading || !effectiveConfigId}
            className="flex items-center gap-2"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Scenario Context — always-visible branch indicator + tree popover */}
      {effectiveConfigId && <ScenarioContextBar />}

      {/* Hierarchy Navigation — breadcrumbs + level-appropriate filter dropdowns */}
      {breadcrumbs && (
        <Card>
          <CardContent className="py-3 space-y-2.5">
            {['site', 'product', 'time'].map((dim) => (
              <HierarchyRow
                key={dim}
                dimension={dim}
                crumbs={breadcrumbs[dim] || []}
                childItems={childrenNav?.[dim] || []}
                onBreadcrumbClick={handleBreadcrumbClick}
                onDrillDown={handleDrillDown}
              />
            ))}
          </CardContent>
        </Card>
      )}

      {/* Plan Version filter (if versions exist from previous loads) */}
      {timelineData?.groups?.some(g => g.buckets?.length > 0) && (
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span>
            Bucket: <strong>{timelineData.bucket_type}</strong>
          </span>
          <span>
            Horizon: <strong>{timelineData.horizon_weeks} weeks</strong>
          </span>
        </div>
      )}

      {/* Error */}
      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-16">
          <Spinner className="h-8 w-8" />
          <span className="ml-3 text-muted-foreground">Loading planning data...</span>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && !hasData && (
        <Card>
          <CardContent className="p-12 text-center">
            <Package className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-2">No supply plan data available</h3>
            <p className="text-muted-foreground">
              Generate a supply plan first via Supply Planning, or try a different hierarchy level.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Data content */}
      {!loading && hasData && (
        <>
          {/* KPI Summary Cards */}
          <div className="flex flex-wrap gap-4">
            <KPICard
              icon={ShoppingCart}
              title="Total Demand"
              value={fmt(kpis.totalDemand)}
              subtitle={`${buckets.length} ${timelineData.bucket_type === 'weekly' ? 'weeks' : 'months'}`}
              color="orange"
            />
            <KPICard
              icon={TrendingUp}
              title="Total Supply"
              value={fmt(kpis.totalSupply)}
              subtitle="Planned orders"
              color="green"
            />
            <KPICard
              icon={Package}
              title="Avg Closing Inventory"
              value={fmt(Math.round(kpis.avgClosing))}
              subtitle="Across horizon"
              color="blue"
            />
            <KPICard
              icon={ShieldAlert}
              title="Stockout Risk"
              value={`${kpis.stockoutRisk} / ${buckets.length}`}
              subtitle="Buckets below safety stock"
              color="red"
            />
          </div>

          {/* Group Tabs (when multiple groups returned — e.g. multiple families or regions) */}
          {timelineData.groups.length > 1 && (
            <Tabs
              value={String(activeGroupIdx)}
              onValueChange={(v) => setActiveGroupIdx(Number(v))}
            >
              <TabsList className="flex-wrap h-auto gap-1">
                {timelineData.groups.map((g, idx) => (
                  <TabsTrigger key={g.group_key} value={String(idx)} className="text-xs">
                    {g.group_label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          )}

          {/* Active Group Label (single group) */}
          {timelineData.groups.length === 1 && activeGroup && (
            <div className="flex items-center gap-2">
              <Badge variant="secondary">{activeGroup.group_label}</Badge>
            </div>
          )}

          {/* Fan Chart — Inventory Projection */}
          <Card>
            <CardContent className="p-4">
              <h3 className="text-sm font-semibold mb-4">Inventory Projection</h3>
              <ResponsiveContainer width="100%" height={400}>
                <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis
                    dataKey="period"
                    tick={{ fontSize: 11 }}
                    angle={-30}
                    textAnchor="end"
                    height={60}
                  />
                  <YAxis tick={{ fontSize: 11 }} />
                  <RechartsTooltip content={<CustomTooltip />} />
                  <Legend verticalAlign="top" height={36} />

                  <Area
                    dataKey="projected_inv_high"
                    name="Projection Band (High)"
                    stroke="none"
                    fill="#3b82f6"
                    fillOpacity={0.1}
                    connectNulls
                  />
                  <Area
                    dataKey="projected_inv_low"
                    name="Projection Band (Low)"
                    stroke="none"
                    fill="#ffffff"
                    fillOpacity={1}
                    connectNulls
                  />

                  <Bar
                    dataKey="gross_demand"
                    name="Gross Demand"
                    fill="#f97316"
                    fillOpacity={0.4}
                    barSize={14}
                  />
                  <Bar
                    dataKey="planned_orders"
                    name="Planned Orders"
                    fill="#22c55e"
                    fillOpacity={0.4}
                    barSize={14}
                  />

                  <Line
                    dataKey="closing_inventory"
                    name="Closing Inventory"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    connectNulls
                  />
                  <Line
                    dataKey="safety_stock"
                    name="Safety Stock"
                    stroke="#ef4444"
                    strokeWidth={2}
                    strokeDasharray="6 3"
                    dot={false}
                    connectNulls
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Netting Grid */}
          <Card>
            <CardContent className="p-4">
              <h3 className="text-sm font-semibold mb-4">Time-Phased Netting Grid</h3>
              <TableContainer className="max-h-[480px]">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="sticky left-0 z-20 bg-background min-w-[180px]">
                        Key Figure
                      </TableHead>
                      {buckets.map((b, i) => (
                        <TableHead
                          key={i}
                          className="text-center whitespace-nowrap min-w-[100px] text-xs"
                        >
                          {b.period_label}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {nettingRows.map((row) => (
                      <TableRow key={row.key}>
                        <TableCell className="sticky left-0 z-10 bg-background font-medium text-sm">
                          {row.label}
                        </TableCell>
                        {buckets.map((b, i) => (
                          <TableCell
                            key={i}
                            className={`text-center font-mono text-sm ${cellClassName(row.key, b)}`}
                          >
                            {fmt(b[row.key])}
                            {row.key === 'planned_orders' && (b.po_quantity || b.to_quantity || b.mo_quantity) ? (
                              <SupplyBreakdownTooltip
                                po={b.po_quantity}
                                to={b.to_quantity}
                                mo={b.mo_quantity}
                              />
                            ) : null}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>

          {/* Generated timestamp */}
          {timelineData.generated_at && (
            <p className="text-xs text-muted-foreground text-right">
              Generated: {new Date(timelineData.generated_at).toLocaleString()}
            </p>
          )}
        </>
      )}
    </div>
  );
};

export default PlanningBoard;
