import React, { useState, useEffect, useCallback } from 'react';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Input,
  Spinner,
  Modal,
  Textarea,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../../components/common';
import {
  Package,
  RefreshCw,
  Edit3,
  Save,
  X,
  AlertTriangle,
  CheckCircle,
  Users,
  BarChart3,
  Layers,
} from 'lucide-react';
import { api } from '../../services/api';

/* ------------------------------------------------------------------ */
/*  Allocation Override Page (AIIO model — agent already allocated)    */
/* ------------------------------------------------------------------ */

const ATPCTPView = () => {
  const { effectiveConfigId } = useActiveConfig();

  // Data
  const [allocations, setAllocations] = useState([]);
  const [atpData, setAtpData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Hierarchy filters
  const [dimensions, setDimensions] = useState(null);
  const [productNodeId, setProductNodeId] = useState('');
  const [geoFilter, setGeoFilter] = useState('');

  // Override state
  const [overrideRowIdx, setOverrideRowIdx] = useState(null);
  const [overrideQty, setOverrideQty] = useState('');
  const [overridePriority, setOverridePriority] = useState('');
  const [overrideReason, setOverrideReason] = useState('');
  const [saving, setSaving] = useState(false);

  // ---- Load hierarchy dimensions ----
  useEffect(() => {
    if (!effectiveConfigId) return;
    api.get('/demand-plan/hierarchy-dimensions', { params: { config_id: effectiveConfigId } })
      .then(res => setDimensions(res.data))
      .catch(() => setDimensions(null));
  }, [effectiveConfigId]);

  // ---- Load allocations + ATP data ----
  const loadData = useCallback(async () => {
    if (!effectiveConfigId) return;
    setLoading(true);
    setError(null);
    try {
      const params = { config_id: effectiveConfigId };
      if (productNodeId) params.product_node_id = productNodeId;
      if (geoFilter) params.geo_id = geoFilter;

      const [atpRes] = await Promise.all([
        api.get('/inventory-projection/atp/availability', { params }),
      ]);

      const atp = atpRes.data;
      setAtpData(atp);

      // Build allocation rows from ATP response
      // The ATP endpoint returns allocations per customer/product/site
      const rows = atp.allocations || atp.future_atp || [];
      setAllocations(rows.map((r, i) => ({
        id: r.id || i,
        customer: r.customer_name || r.customer_id || `Customer ${r.customer_id || i + 1}`,
        customer_id: r.customer_id,
        product: r.product_name || r.product_id || 'N/A',
        product_id: r.product_id,
        site: r.site_name || r.site_id || 'N/A',
        site_id: r.site_id,
        allocated_qty: r.allocated_qty ?? r.cumulative_atp ?? r.discrete_atp ?? 0,
        requested_qty: r.requested_qty ?? r.demand_qty ?? 0,
        fill_pct: r.fill_pct ?? (r.requested_qty ? ((r.allocated_qty || 0) / r.requested_qty * 100) : 100),
        priority: r.priority ?? r.priority_tier ?? 'P3',
        status: r.status || 'ACTIONED',
        date: r.date || r.allocation_date,
      })));
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load allocation data');
      setAllocations([]);
    } finally {
      setLoading(false);
    }
  }, [effectiveConfigId, productNodeId, geoFilter]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ---- Computed summary metrics ----
  const totalAllocated = allocations.reduce((s, a) => s + (a.allocated_qty || 0), 0);
  const totalRequested = allocations.reduce((s, a) => s + (a.requested_qty || 0), 0);
  const availableToPromise = atpData?.current_atp ?? atpData?.total_available ?? 0;
  const customersServed = new Set(allocations.map(a => a.customer_id || a.customer)).size;
  const overallFillRate = totalRequested > 0 ? (totalAllocated / totalRequested * 100) : 0;

  // ---- Override handlers ----
  const startOverride = (idx) => {
    const row = allocations[idx];
    setOverrideRowIdx(idx);
    setOverrideQty(String(row.allocated_qty));
    setOverridePriority(row.priority || 'P3');
    setOverrideReason('');
  };

  const cancelOverride = () => {
    setOverrideRowIdx(null);
    setOverrideQty('');
    setOverridePriority('');
    setOverrideReason('');
  };

  const saveOverride = async () => {
    if (!overrideReason.trim()) {
      setError('Reasoning is required for allocation overrides (AIIO: OVERRIDDEN).');
      return;
    }
    const row = allocations[overrideRowIdx];
    setSaving(true);
    setError(null);
    try {
      await api.post('/demand-plan/override', {
        config_id: effectiveConfigId,
        product_id: row.product_id,
        site_id: row.site_id,
        customer_id: row.customer_id,
        plan_version: 'decision_action',
        override_type: 'allocation',
        new_value: parseFloat(overrideQty),
        priority: overridePriority,
        reason: overrideReason.trim(),
        status: 'OVERRIDDEN',
      });
      setSuccess('Allocation override saved as decision_action.');
      cancelOverride();
      await loadData();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to save override');
    } finally {
      setSaving(false);
    }
  };

  // ---- Hierarchy filter helpers ----
  const renderProductFilter = () => {
    if (!dimensions?.product_tree?.length) return null;
    const tree = dimensions.product_tree;
    const childrenOf = (parentId) => tree.filter(n => n.parent_id === parentId);
    const findNode = (id) => tree.find(n => n.id === id);

    const breadcrumb = [];
    let cur = productNodeId ? findNode(parseInt(productNodeId)) : null;
    while (cur) {
      breadcrumb.unshift(cur);
      cur = cur.parent_id ? findNode(cur.parent_id) : null;
    }
    const children = productNodeId
      ? childrenOf(parseInt(productNodeId))
      : tree.filter(n => !n.parent_id);

    return (
      <div>
        <label className="text-xs font-medium text-muted-foreground block mb-1">Product</label>
        {breadcrumb.length > 0 && (
          <div className="flex items-center gap-1 mb-1 text-xs">
            <button className="text-primary hover:underline" onClick={() => setProductNodeId('')}>
              All
            </button>
            {breadcrumb.map((n, i) => (
              <span key={n.id} className="flex items-center gap-1">
                <span className="text-muted-foreground">/</span>
                <button
                  className={i === breadcrumb.length - 1 ? 'font-semibold' : 'text-primary hover:underline'}
                  onClick={() => setProductNodeId(String(n.id))}
                >
                  {n.name}
                </button>
              </span>
            ))}
          </div>
        )}
        {children.length > 0 && (
          <select
            className="border rounded px-2 py-1.5 text-sm w-52"
            value=""
            onChange={e => { if (e.target.value) setProductNodeId(e.target.value); }}
          >
            <option value="">
              {productNodeId ? `Drill into ${findNode(parseInt(productNodeId))?.name || ''}...` : 'Select product group...'}
            </option>
            {children.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
          </select>
        )}
      </div>
    );
  };

  const renderGeoFilter = () => {
    if (!dimensions?.geography?.length) return null;
    const childrenOf = (parentId) => dimensions.geography.filter(g => g.parent_id === parentId);
    const findGeo = (id) => dimensions.geography.find(g => g.id === id);

    const breadcrumb = [];
    let current = geoFilter ? findGeo(geoFilter) : null;
    while (current) {
      breadcrumb.unshift(current);
      current = current.parent_id ? findGeo(current.parent_id) : null;
    }
    const children = geoFilter ? childrenOf(geoFilter) : dimensions.geography.filter(g => !g.parent_id);

    return (
      <div>
        <label className="text-xs font-medium text-muted-foreground block mb-1">Geography</label>
        {breadcrumb.length > 0 && (
          <div className="flex items-center gap-1 mb-1 text-xs">
            <button className="text-primary hover:underline" onClick={() => setGeoFilter('')}>
              All
            </button>
            {breadcrumb.map((g, i) => (
              <span key={g.id} className="flex items-center gap-1">
                <span className="text-muted-foreground">/</span>
                <button
                  className={i === breadcrumb.length - 1 ? 'font-semibold' : 'text-primary hover:underline'}
                  onClick={() => setGeoFilter(g.id)}
                >
                  {g.name}
                </button>
              </span>
            ))}
          </div>
        )}
        {children.length > 0 && (
          <select
            className="border rounded px-2 py-1.5 text-sm w-52"
            value=""
            onChange={e => { if (e.target.value) setGeoFilter(e.target.value); }}
          >
            <option value="">
              {geoFilter ? `Drill into ${findGeo(geoFilter)?.name || ''}...` : 'Select region...'}
            </option>
            {children.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        )}
      </div>
    );
  };

  // ---- Render ----
  const formatNum = (n) => (n != null ? Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 }) : '--');
  const formatPct = (n) => (n != null ? `${Number(n).toFixed(1)}%` : '--');

  const getPriorityColor = (p) => {
    const s = String(p).toUpperCase();
    if (s === 'P1' || s === '1') return 'destructive';
    if (s === 'P2' || s === '2') return 'warning';
    return 'secondary';
  };

  const getStatusColor = (s) => {
    if (s === 'OVERRIDDEN') return 'warning';
    if (s === 'ACTIONED') return 'success';
    return 'secondary';
  };

  const getFillColor = (pct) => {
    if (pct >= 95) return 'text-green-600';
    if (pct >= 80) return 'text-yellow-600';
    return 'text-red-600';
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <div className="flex items-center gap-2">
            <Layers className="h-7 w-7 text-primary" />
            <h1 className="text-2xl font-bold">Allocation Override</h1>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Review agent-generated ATP allocations and override with reasoning
          </p>
        </div>
        <Button
          variant="outline"
          onClick={loadData}
          disabled={loading}
          leftIcon={<RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />}
        >
          Refresh
        </Button>
      </div>

      {/* Alerts */}
      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>
          <CheckCircle className="h-4 w-4 inline mr-1" />
          {success}
        </Alert>
      )}

      {/* Hierarchy Filters */}
      {dimensions && (
        <Card className="mb-6">
          <CardContent className="pt-4">
            <div className="flex flex-wrap items-end gap-6">
              {renderProductFilter()}
              {renderGeoFilter()}
              {(productNodeId || geoFilter) && (
                <Button variant="ghost" size="sm" onClick={() => { setProductNodeId(''); setGeoFilter(''); }}>
                  Clear Filters
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-1">
              <Package className="h-4 w-4 text-blue-500" />
              <p className="text-sm text-muted-foreground">Total Allocated</p>
            </div>
            <p className="text-3xl font-bold text-blue-600">{formatNum(totalAllocated)}</p>
            <p className="text-xs text-muted-foreground mt-1">
              of {formatNum(totalRequested)} requested
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-1">
              <BarChart3 className="h-4 w-4 text-green-500" />
              <p className="text-sm text-muted-foreground">Available to Promise</p>
            </div>
            <p className="text-3xl font-bold text-green-600">{formatNum(availableToPromise)}</p>
            <p className="text-xs text-muted-foreground mt-1">Remaining ATP</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-1">
              <Users className="h-4 w-4 text-purple-500" />
              <p className="text-sm text-muted-foreground">Customers Served</p>
            </div>
            <p className="text-3xl font-bold text-purple-600">{customersServed}</p>
            <p className="text-xs text-muted-foreground mt-1">Unique customers</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle className="h-4 w-4 text-emerald-500" />
              <p className="text-sm text-muted-foreground">Fill Rate</p>
            </div>
            <p className={`text-3xl font-bold ${getFillColor(overallFillRate)}`}>
              {formatPct(overallFillRate)}
            </p>
            <p className="text-xs text-muted-foreground mt-1">Overall allocation fill</p>
          </CardContent>
        </Card>
      </div>

      {/* Allocation Table */}
      {loading ? (
        <div className="flex justify-center p-12">
          <Spinner size="lg" />
        </div>
      ) : allocations.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <AlertTriangle className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">
              No allocation data available.
              {!effectiveConfigId && ' No active configuration detected.'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Current Allocations</h3>
              <span className="text-sm text-muted-foreground">{allocations.length} allocations</span>
            </div>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Customer</TableHead>
                    <TableHead>Product</TableHead>
                    <TableHead>Site</TableHead>
                    <TableHead className="text-right">Allocated</TableHead>
                    <TableHead className="text-right">Requested</TableHead>
                    <TableHead className="text-right">Fill %</TableHead>
                    <TableHead>Priority</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {allocations.map((row, idx) => (
                    <React.Fragment key={row.id}>
                      <TableRow className={overrideRowIdx === idx ? 'bg-amber-50' : ''}>
                        <TableCell className="font-medium">{row.customer}</TableCell>
                        <TableCell>{row.product}</TableCell>
                        <TableCell>{row.site}</TableCell>
                        <TableCell className="text-right font-mono">{formatNum(row.allocated_qty)}</TableCell>
                        <TableCell className="text-right font-mono">{formatNum(row.requested_qty)}</TableCell>
                        <TableCell className={`text-right font-mono ${getFillColor(row.fill_pct)}`}>
                          {formatPct(row.fill_pct)}
                        </TableCell>
                        <TableCell>
                          <Badge variant={getPriorityColor(row.priority)}>{row.priority}</Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant={getStatusColor(row.status)}>{row.status}</Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          {overrideRowIdx !== idx && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => startOverride(idx)}
                              leftIcon={<Edit3 className="h-3 w-3" />}
                            >
                              Override
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>

                      {/* Inline override controls */}
                      {overrideRowIdx === idx && (
                        <TableRow className="bg-amber-50 border-t-0">
                          <TableCell colSpan={9}>
                            <div className="py-3 px-2 space-y-3">
                              <div className="flex items-center gap-2 text-sm font-medium text-amber-700">
                                <AlertTriangle className="h-4 w-4" />
                                Override Allocation — AIIO: OVERRIDDEN
                              </div>
                              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div className="space-y-1">
                                  <Label htmlFor="override-qty">Adjusted Quantity</Label>
                                  <Input
                                    id="override-qty"
                                    type="number"
                                    value={overrideQty}
                                    onChange={e => setOverrideQty(e.target.value)}
                                    min={0}
                                  />
                                  <p className="text-xs text-muted-foreground">
                                    Remaining ATP: {formatNum(availableToPromise + row.allocated_qty - (parseFloat(overrideQty) || 0))}
                                  </p>
                                </div>
                                <div className="space-y-1">
                                  <Label htmlFor="override-priority">Priority Override</Label>
                                  <select
                                    id="override-priority"
                                    className="border rounded px-2 py-1.5 text-sm w-full"
                                    value={overridePriority}
                                    onChange={e => setOverridePriority(e.target.value)}
                                  >
                                    <option value="P1">P1 - Critical</option>
                                    <option value="P2">P2 - High</option>
                                    <option value="P3">P3 - Standard</option>
                                    <option value="P4">P4 - Low</option>
                                    <option value="P5">P5 - Opportunistic</option>
                                  </select>
                                </div>
                                <div className="space-y-1">
                                  <Label htmlFor="override-reason">
                                    Reasoning <span className="text-red-500">*</span>
                                  </Label>
                                  <Textarea
                                    id="override-reason"
                                    value={overrideReason}
                                    onChange={e => setOverrideReason(e.target.value)}
                                    placeholder="Required: explain why this override is needed..."
                                    rows={2}
                                  />
                                </div>
                              </div>
                              <div className="flex items-center gap-2 justify-end">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={cancelOverride}
                                  disabled={saving}
                                  leftIcon={<X className="h-3 w-3" />}
                                >
                                  Cancel
                                </Button>
                                <Button
                                  size="sm"
                                  onClick={saveOverride}
                                  disabled={saving || !overrideReason.trim()}
                                  leftIcon={saving ? <Spinner size="sm" /> : <Save className="h-3 w-3" />}
                                >
                                  {saving ? 'Saving...' : 'Save Override'}
                                </Button>
                              </div>
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default ATPCTPView;
