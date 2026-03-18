import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Alert,
  Badge,
  Label,
  Input,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Progress,
  Spinner,
  Modal,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../../components/common';
import {
  RefreshCw,
  Package,
  AlertTriangle,
  CheckCircle,
  XCircle,
  TrendingUp,
  TrendingDown,
  MapPin,
  BarChart3,
  Eye,
  ArrowUpDown,
  ShieldAlert,
  Warehouse,
  Activity,
} from 'lucide-react';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import BranchPicker from '../../components/planning/BranchPicker';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';

// ---------------------------------------------------------------------------
// Risk helpers
// ---------------------------------------------------------------------------

const getRiskVariant = (level) => {
  const map = { CRITICAL: 'destructive', HIGH: 'warning', MEDIUM: 'info', LOW: 'success' };
  return map[level] || 'secondary';
};

const getRiskIcon = (level) => {
  switch (level) {
    case 'CRITICAL': return <XCircle className="h-4 w-4 text-destructive" />;
    case 'HIGH':     return <AlertTriangle className="h-4 w-4 text-amber-500" />;
    case 'MEDIUM':   return <Activity className="h-4 w-4 text-blue-500" />;
    case 'LOW':      return <CheckCircle className="h-4 w-4 text-green-500" />;
    default:         return null;
  }
};

const getRiskAction = (row) => {
  if (row.risk_level === 'CRITICAL') return 'Expedite reorder — stockout imminent';
  if (row.risk_level === 'HIGH' && row.in_transit_qty > 0) return 'Monitor in-transit shipment';
  if (row.risk_level === 'HIGH') return 'Create emergency purchase order';
  if (row.overstock) return 'Consider rebalancing to deficit sites';
  return null;
};

const formatCurrency = (v) => {
  if (v == null) return '$0';
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}k`;
  return `$${v.toFixed(0)}`;
};

const formatNumber = (v) => {
  if (v == null) return '0';
  return v.toLocaleString(undefined, { maximumFractionDigits: 1 });
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const InventoryVisibility = () => {
  const { effectiveConfigId } = useActiveConfig();
  const { formatProduct, formatSite } = useDisplayPreferences();

  // Data
  const [snapshot, setSnapshot] = useState([]);
  const [summary, setSummary] = useState(null);
  const [siteHealth, setSiteHealth] = useState([]);

  // UI state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [tabValue, setTabValue] = useState('by-product');

  // Filters
  const [siteFilter, setSiteFilter] = useState('all');
  const [productFilter, setProductFilter] = useState('');
  const [riskFilter, setRiskFilter] = useState('all');

  // Sort
  const [sortField, setSortField] = useState('risk_level');
  const [sortAsc, setSortAsc] = useState(true);

  // Detail modal
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedRow, setSelectedRow] = useState(null);

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchData = useCallback(async () => {
    if (!effectiveConfigId) return;
    setLoading(true);
    setError(null);
    try {
      const params = { config_id: effectiveConfigId };
      if (siteFilter && siteFilter !== 'all') params.site_id = siteFilter;
      if (productFilter) params.product_id = productFilter;
      if (riskFilter && riskFilter !== 'all') params.risk_level = riskFilter;

      const [snapRes, summRes, healthRes] = await Promise.all([
        api.get('/inventory-visibility/snapshot', { params }),
        api.get('/inventory-visibility/summary', { params: { config_id: effectiveConfigId } }),
        api.get('/inventory-visibility/site-health', { params: { config_id: effectiveConfigId } }),
      ]);

      setSnapshot(snapRes.data);
      setSummary(summRes.data);
      setSiteHealth(healthRes.data);
    } catch (err) {
      console.error('Failed to fetch inventory data:', err);
      setError('Failed to load inventory visibility data. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [effectiveConfigId, siteFilter, productFilter, riskFilter]);

  useEffect(() => { if (effectiveConfigId) fetchData(); }, [effectiveConfigId, fetchData]);

  // -----------------------------------------------------------------------
  // Sorting
  // -----------------------------------------------------------------------

  const handleSort = (field) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  const riskOrder = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

  const sortedSnapshot = [...snapshot].sort((a, b) => {
    let va = a[sortField];
    let vb = b[sortField];
    if (sortField === 'risk_level') {
      va = riskOrder[va] ?? 4;
      vb = riskOrder[vb] ?? 4;
    }
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === 'string') {
      return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
    }
    return sortAsc ? va - vb : vb - va;
  });

  // Risk alerts: CRITICAL + HIGH items
  const riskAlerts = snapshot.filter((r) => r.risk_level === 'CRITICAL' || r.risk_level === 'HIGH');

  // Unique sites for filter dropdown
  const uniqueSites = [...new Map(snapshot.map((r) => [r.site_id, { id: r.site_id, name: r.site_name }])).values()];

  // -----------------------------------------------------------------------
  // Sortable header helper
  // -----------------------------------------------------------------------

  const SortableHead = ({ field, children }) => (
    <TableHead
      className="cursor-pointer select-none hover:bg-muted/50"
      onClick={() => handleSort(field)}
    >
      <div className="flex items-center gap-1">
        {children}
        {sortField === field && (
          <ArrowUpDown className="h-3 w-3 opacity-60" />
        )}
      </div>
    </TableHead>
  );

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Inventory Visibility</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Stock positions, risk detection, and rebalancing recommendations
          </p>
        </div>
        <div className="flex items-center gap-3">
          <BranchPicker />
          <Button
            variant="outline"
            onClick={fetchData}
            leftIcon={<RefreshCw className="h-4 w-4" />}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <Alert variant="error" onClose={() => setError(null)} className="mb-4">
          {error}
        </Alert>
      )}
      {loading && <Progress indeterminate className="mb-4" />}

      {/* Summary KPI Cards */}
      {summary && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-3xl font-bold">{formatCurrency(summary.total_inventory_value)}</p>
                  <p className="text-sm text-muted-foreground">Total Inventory Value</p>
                </div>
                <Package className="h-8 w-8 text-primary" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-3xl font-bold text-amber-500">{summary.at_risk_count}</p>
                  <p className="text-sm text-muted-foreground">At-Risk SKU-Sites</p>
                </div>
                <AlertTriangle className="h-8 w-8 text-amber-500" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-3xl font-bold text-red-500">{summary.stockout_count}</p>
                  <p className="text-sm text-muted-foreground">Stockout Risk</p>
                </div>
                <ShieldAlert className="h-8 w-8 text-red-500" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-3xl font-bold">
                    {summary.avg_days_of_supply > 0 ? `${summary.avg_days_of_supply}d` : '—'}
                  </p>
                  <p className="text-sm text-muted-foreground">Avg Days of Supply</p>
                </div>
                <TrendingUp className="h-8 w-8 text-green-500" />
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tabs */}
      <Tabs value={tabValue} onValueChange={setTabValue} className="space-y-4">
        <TabsList>
          <TabsTrigger value="by-product">By Product</TabsTrigger>
          <TabsTrigger value="by-location">By Location</TabsTrigger>
          <TabsTrigger value="risk-alerts">
            Risk Alerts
            {riskAlerts.length > 0 && (
              <Badge variant="destructive" className="ml-2 text-xs">{riskAlerts.length}</Badge>
            )}
          </TabsTrigger>
        </TabsList>

        {/* ---- TAB: By Product ---- */}
        <TabsContent value="by-product">
          {/* Filters */}
          <Card className="mb-4">
            <CardContent className="pt-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <Label>Site</Label>
                  <Select value={siteFilter} onValueChange={setSiteFilter}>
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder="All Sites" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Sites</SelectItem>
                      {uniqueSites.map((s) => (
                        <SelectItem key={s.id} value={s.id.toString()}>
                          {s.name || `Site ${s.id}`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Product ID</Label>
                  <Input
                    value={productFilter}
                    onChange={(e) => setProductFilter(e.target.value)}
                    placeholder="Filter by product..."
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label>Risk Level</Label>
                  <Select value={riskFilter} onValueChange={setRiskFilter}>
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder="All Risk Levels" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Risk Levels</SelectItem>
                      <SelectItem value="CRITICAL">Critical</SelectItem>
                      <SelectItem value="HIGH">High</SelectItem>
                      <SelectItem value="MEDIUM">Medium</SelectItem>
                      <SelectItem value="LOW">Low</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Data Table */}
          <Card>
            <CardContent className="pt-4">
              <h3 className="text-lg font-medium mb-4">
                Inventory Positions ({sortedSnapshot.length})
              </h3>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <SortableHead field="product_id">Product</SortableHead>
                      <SortableHead field="site_name">Site</SortableHead>
                      <SortableHead field="on_hand_qty">On Hand</SortableHead>
                      <SortableHead field="in_transit_qty">In Transit</SortableHead>
                      <SortableHead field="allocated_qty">Allocated</SortableHead>
                      <SortableHead field="available_qty">Available</SortableHead>
                      <SortableHead field="days_of_supply">DOS</SortableHead>
                      <SortableHead field="inventory_value">Value</SortableHead>
                      <SortableHead field="risk_level">Risk</SortableHead>
                      <TableHead className="text-center">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sortedSnapshot.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={10} className="text-center py-8">
                          <p className="text-muted-foreground">
                            {loading ? 'Loading...' : 'No inventory data found for this configuration'}
                          </p>
                        </TableCell>
                      </TableRow>
                    ) : (
                      sortedSnapshot.map((row, idx) => (
                        <TableRow key={`${row.product_id}-${row.site_id}-${idx}`} className="hover:bg-muted/30">
                          <TableCell>
                            <div>
                              <span className="font-medium">{formatProduct(row.product_id, row.product_name)}</span>
                              {row.product_description && (
                                <p className="text-xs text-muted-foreground">{row.product_description}</p>
                              )}
                            </div>
                          </TableCell>
                          <TableCell>
                            <div>
                              <span>{formatSite(row.site_id, row.site_name)}</span>
                              {row.site_type && (
                                <p className="text-xs text-muted-foreground">{row.site_type}</p>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="text-right font-mono">
                            {formatNumber(row.on_hand_qty)}
                          </TableCell>
                          <TableCell className="text-right font-mono">
                            {formatNumber(row.in_transit_qty)}
                          </TableCell>
                          <TableCell className="text-right font-mono">
                            {formatNumber(row.allocated_qty)}
                          </TableCell>
                          <TableCell className="text-right font-mono">
                            {formatNumber(row.available_qty)}
                          </TableCell>
                          <TableCell className="text-right">
                            {row.days_of_supply != null ? (
                              <span className={
                                row.days_of_supply >= 30 ? 'text-green-600 font-medium' :
                                row.days_of_supply >= 14 ? 'text-amber-600 font-medium' :
                                'text-red-600 font-bold'
                              }>
                                {row.days_of_supply}d
                              </span>
                            ) : '—'}
                          </TableCell>
                          <TableCell className="text-right font-mono">
                            {formatCurrency(row.inventory_value)}
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-1">
                              {getRiskIcon(row.risk_level)}
                              <Badge variant={getRiskVariant(row.risk_level)}>
                                {row.risk_level}
                              </Badge>
                              {row.overstock && (
                                <Badge variant="outline" className="ml-1 text-xs">Overstock</Badge>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="text-center">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => { setSelectedRow(row); setDetailOpen(true); }}
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---- TAB: By Location ---- */}
        <TabsContent value="by-location">
          {siteHealth.length === 0 ? (
            <Card>
              <CardContent className="pt-4 text-center py-8">
                <p className="text-muted-foreground">No site health data available</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {siteHealth.map((site) => (
                <Card key={site.site_id} className="hover:shadow-md transition-shadow">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base flex items-center gap-2">
                        <Warehouse className="h-4 w-4 text-muted-foreground" />
                        {site.site_name}
                      </CardTitle>
                      <Badge
                        variant={
                          site.health_score >= 80 ? 'success' :
                          site.health_score >= 50 ? 'warning' :
                          'destructive'
                        }
                      >
                        {site.health_score}%
                      </Badge>
                    </div>
                    {site.site_type && (
                      <p className="text-xs text-muted-foreground">{site.site_type}</p>
                    )}
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Inventory Value</span>
                        <span className="font-medium">{formatCurrency(site.total_value)}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">SKU Count</span>
                        <span className="font-medium">{site.sku_count}</span>
                      </div>

                      {/* Risk breakdown bar */}
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Risk Breakdown</p>
                        <div className="flex gap-0.5 h-3 rounded overflow-hidden">
                          {site.risk_breakdown.CRITICAL > 0 && (
                            <div
                              className="bg-red-500"
                              style={{ flex: site.risk_breakdown.CRITICAL }}
                              title={`Critical: ${site.risk_breakdown.CRITICAL}`}
                            />
                          )}
                          {site.risk_breakdown.HIGH > 0 && (
                            <div
                              className="bg-amber-500"
                              style={{ flex: site.risk_breakdown.HIGH }}
                              title={`High: ${site.risk_breakdown.HIGH}`}
                            />
                          )}
                          {site.risk_breakdown.MEDIUM > 0 && (
                            <div
                              className="bg-blue-400"
                              style={{ flex: site.risk_breakdown.MEDIUM }}
                              title={`Medium: ${site.risk_breakdown.MEDIUM}`}
                            />
                          )}
                          {site.risk_breakdown.LOW > 0 && (
                            <div
                              className="bg-green-500"
                              style={{ flex: site.risk_breakdown.LOW }}
                              title={`Low: ${site.risk_breakdown.LOW}`}
                            />
                          )}
                        </div>
                        <div className="flex gap-3 mt-1 text-xs text-muted-foreground flex-wrap">
                          {site.risk_breakdown.CRITICAL > 0 && (
                            <span className="flex items-center gap-1">
                              <span className="w-2 h-2 rounded-full bg-red-500" /> {site.risk_breakdown.CRITICAL} Critical
                            </span>
                          )}
                          {site.risk_breakdown.HIGH > 0 && (
                            <span className="flex items-center gap-1">
                              <span className="w-2 h-2 rounded-full bg-amber-500" /> {site.risk_breakdown.HIGH} High
                            </span>
                          )}
                          {site.risk_breakdown.MEDIUM > 0 && (
                            <span className="flex items-center gap-1">
                              <span className="w-2 h-2 rounded-full bg-blue-400" /> {site.risk_breakdown.MEDIUM} Medium
                            </span>
                          )}
                          {site.risk_breakdown.LOW > 0 && (
                            <span className="flex items-center gap-1">
                              <span className="w-2 h-2 rounded-full bg-green-500" /> {site.risk_breakdown.LOW} Low
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* ---- TAB: Risk Alerts ---- */}
        <TabsContent value="risk-alerts">
          {riskAlerts.length === 0 ? (
            <Card>
              <CardContent className="pt-4 text-center py-8">
                <div className="flex flex-col items-center gap-2">
                  <CheckCircle className="h-12 w-12 text-green-500" />
                  <p className="text-lg font-medium">No Critical or High Risk Items</p>
                  <p className="text-sm text-muted-foreground">All inventory positions are within acceptable levels</p>
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {riskAlerts.map((row, idx) => (
                <Card
                  key={`alert-${row.product_id}-${row.site_id}-${idx}`}
                  className={`border-l-4 ${
                    row.risk_level === 'CRITICAL' ? 'border-l-red-500' : 'border-l-amber-500'
                  }`}
                >
                  <CardContent className="pt-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          {getRiskIcon(row.risk_level)}
                          <Badge variant={getRiskVariant(row.risk_level)}>{row.risk_level}</Badge>
                          <span className="font-medium">{formatProduct(row.product_id, row.product_name)}</span>
                          {row.product_description && (
                            <span className="text-muted-foreground">— {row.product_description}</span>
                          )}
                        </div>
                        <div className="text-sm text-muted-foreground mb-2">
                          <MapPin className="h-3 w-3 inline mr-1" />
                          {formatSite(row.site_id, row.site_name)}
                          {row.site_type && ` (${row.site_type})`}
                        </div>
                        {row.risk_reason && (
                          <p className="text-sm mb-2">{row.risk_reason}</p>
                        )}
                        <div className="flex gap-4 text-sm">
                          <span>On Hand: <strong>{formatNumber(row.on_hand_qty)}</strong></span>
                          <span>In Transit: <strong>{formatNumber(row.in_transit_qty)}</strong></span>
                          <span>DOS: <strong>{row.days_of_supply != null ? `${row.days_of_supply}d` : '—'}</strong></span>
                          <span>Value: <strong>{formatCurrency(row.inventory_value)}</strong></span>
                        </div>
                        {getRiskAction(row) && (
                          <div className="mt-2 flex items-center gap-2">
                            <Badge variant="outline" className="text-xs">
                              Recommended Action
                            </Badge>
                            <span className="text-sm font-medium">{getRiskAction(row)}</span>
                          </div>
                        )}
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => { setSelectedRow(row); setDetailOpen(true); }}
                      >
                        <Eye className="h-4 w-4 mr-1" /> Details
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Detail Modal */}
      <Modal
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title="Inventory Position Detail"
        maxWidth="lg"
      >
        {selectedRow && (
          <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold">{formatProduct(selectedRow.product_id, selectedRow.product_name)}</h3>
                {selectedRow.product_description && (
                  <p className="text-sm text-muted-foreground">{selectedRow.product_description}</p>
                )}
              </div>
              <div className="flex items-center gap-2">
                {getRiskIcon(selectedRow.risk_level)}
                <Badge variant={getRiskVariant(selectedRow.risk_level)} className="text-sm">
                  {selectedRow.risk_level}
                </Badge>
                {selectedRow.overstock && <Badge variant="outline">Overstock</Badge>}
              </div>
            </div>

            {/* Location */}
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <MapPin className="h-4 w-4" />
              {formatSite(selectedRow.site_id, selectedRow.site_name)}
              {selectedRow.site_type && ` (${selectedRow.site_type})`}
            </div>

            {/* Inventory breakdown */}
            <Card>
              <CardContent className="pt-4">
                <h4 className="font-medium mb-3">Inventory Breakdown</h4>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">On Hand</p>
                    <p className="text-xl font-bold">{formatNumber(selectedRow.on_hand_qty)}</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">In Transit</p>
                    <p className="text-xl font-bold">{formatNumber(selectedRow.in_transit_qty)}</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">On Order</p>
                    <p className="text-xl font-bold">{formatNumber(selectedRow.on_order_qty)}</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Allocated</p>
                    <p className="text-xl font-bold">{formatNumber(selectedRow.allocated_qty)}</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Available</p>
                    <p className="text-xl font-bold text-green-600">{formatNumber(selectedRow.available_qty)}</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Reserved</p>
                    <p className="text-xl font-bold">{formatNumber(selectedRow.reserved_qty)}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Policy & metrics */}
            <Card>
              <CardContent className="pt-4">
                <h4 className="font-medium mb-3">Policy & Metrics</h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Days of Supply</p>
                    <p className="text-xl font-bold">
                      {selectedRow.days_of_supply != null ? `${selectedRow.days_of_supply}d` : '—'}
                    </p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Inventory Value</p>
                    <p className="text-xl font-bold">{formatCurrency(selectedRow.inventory_value)}</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Safety Stock Days</p>
                    <p className="text-xl font-bold">
                      {selectedRow.safety_stock_days != null ? `${selectedRow.safety_stock_days}d` : '—'}
                    </p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Unit Cost</p>
                    <p className="text-xl font-bold">
                      {selectedRow.unit_cost != null ? `$${selectedRow.unit_cost.toFixed(2)}` : '—'}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Risk reason */}
            {selectedRow.risk_reason && (
              <Alert variant={selectedRow.risk_level === 'CRITICAL' ? 'error' : selectedRow.risk_level === 'HIGH' ? 'warning' : 'info'}>
                <strong>Risk Assessment: </strong>{selectedRow.risk_reason}
              </Alert>
            )}

            {/* Recommended action */}
            {getRiskAction(selectedRow) && (
              <Card>
                <CardContent className="pt-4">
                  <h4 className="font-medium mb-2">Recommended Action</h4>
                  <p className="text-sm">{getRiskAction(selectedRow)}</p>
                </CardContent>
              </Card>
            )}

            {selectedRow.inventory_date && (
              <p className="text-xs text-muted-foreground text-right">
                Data as of {selectedRow.inventory_date}
              </p>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default InventoryVisibility;
