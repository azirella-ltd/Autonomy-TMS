import React, { useState, useEffect, useCallback } from 'react';
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
} from '../../components/common';
import {
  Clock,
  Plus,
  RefreshCw,
  Pencil,
  Trash2,
  Search,
  ArrowUpDown,
  AlertTriangle,
  CheckCircle,
  Layers,
} from 'lucide-react';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';

/**
 * Vendor Lead Times Management
 *
 * Manages supplier-specific lead times with hierarchical override logic.
 *
 * Backend API: /api/v1/vendor-lead-time/*
 * - Hierarchical resolution: Product > Product Group > Site > Region > Company
 * - Lead time variability for stochastic planning
 * - Effective date ranges
 */
const VendorLeadTimes = () => {
  const { effectiveConfigId } = useActiveConfig();
  const { formatProduct, formatSite, loadLookupsForConfig } = useDisplayPreferences();

  useEffect(() => { if (effectiveConfigId) loadLookupsForConfig(effectiveConfigId); }, [effectiveConfigId, loadLookupsForConfig]);

  const [leadTimes, setLeadTimes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortField, setSortField] = useState('tpartner_id');
  const [sortDir, setSortDir] = useState('asc');

  // Create/edit dialog
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [formData, setFormData] = useState({
    tpartner_id: '',
    lead_time_days: '',
    lead_time_variability_days: '',
    product_id: '',
    product_group_id: '',
    site_id: '',
    region_id: '',
    eff_start_date: new Date().toISOString().split('T')[0],
    eff_end_date: '',
  });

  // Resolve dialog
  const [resolveOpen, setResolveOpen] = useState(false);
  const [resolveForm, setResolveForm] = useState({ tpartner_id: '', product_id: '', site_id: '' });
  const [resolveResult, setResolveResult] = useState(null);

  const fetchLeadTimes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (searchQuery) params.tpartner_id = searchQuery;
      const response = await api.get('/api/v1/vendor-lead-time/', { params });
      setLeadTimes(response.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load vendor lead times');
    } finally {
      setLoading(false);
    }
  }, [searchQuery]);

  useEffect(() => {
    fetchLeadTimes();
  }, [fetchLeadTimes]);

  // Summary stats
  const totalCount = leadTimes.length;
  const avgLeadTime = totalCount > 0
    ? (leadTimes.reduce((s, lt) => s + (lt.lead_time_days || 0), 0) / totalCount).toFixed(1)
    : '0.0';
  const productSpecific = leadTimes.filter(lt => lt.product_id).length;
  const withVariability = leadTimes.filter(lt => lt.lead_time_variability_days > 0).length;

  // Sorting
  const sorted = [...leadTimes].sort((a, b) => {
    const aVal = a[sortField] ?? '';
    const bVal = b[sortField] ?? '';
    if (typeof aVal === 'number') return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
    return sortDir === 'asc'
      ? String(aVal).localeCompare(String(bVal))
      : String(bVal).localeCompare(String(aVal));
  });

  const toggleSort = (field) => {
    if (sortField === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortField(field); setSortDir('asc'); }
  };

  // CRUD
  const openCreate = () => {
    setEditingItem(null);
    setFormData({
      tpartner_id: '', lead_time_days: '', lead_time_variability_days: '',
      product_id: '', product_group_id: '', site_id: '', region_id: '',
      eff_start_date: new Date().toISOString().split('T')[0], eff_end_date: '',
    });
    setDialogOpen(true);
  };

  const openEdit = (item) => {
    setEditingItem(item);
    setFormData({
      tpartner_id: item.tpartner_id || '',
      lead_time_days: item.lead_time_days?.toString() || '',
      lead_time_variability_days: item.lead_time_variability_days?.toString() || '',
      product_id: item.product_id || '',
      product_group_id: item.product_group_id || '',
      site_id: item.site_id?.toString() || '',
      region_id: item.region_id || '',
      eff_start_date: item.eff_start_date ? item.eff_start_date.split('T')[0] : '',
      eff_end_date: item.eff_end_date ? item.eff_end_date.split('T')[0] : '',
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    try {
      const payload = {
        tpartner_id: formData.tpartner_id,
        lead_time_days: parseFloat(formData.lead_time_days),
        lead_time_variability_days: formData.lead_time_variability_days ? parseFloat(formData.lead_time_variability_days) : null,
        product_id: formData.product_id || null,
        product_group_id: formData.product_group_id || null,
        site_id: formData.site_id ? parseInt(formData.site_id) : null,
        region_id: formData.region_id || null,
        eff_start_date: formData.eff_start_date,
        eff_end_date: formData.eff_end_date || null,
      };

      if (editingItem) {
        await api.put(`/api/v1/vendor-lead-time/${editingItem.id}`, payload);
      } else {
        await api.post('/api/v1/vendor-lead-time/', payload);
      }
      setDialogOpen(false);
      fetchLeadTimes();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save lead time');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this vendor lead time?')) return;
    try {
      await api.delete(`/api/v1/vendor-lead-time/${id}`);
      fetchLeadTimes();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete lead time');
    }
  };

  const handleResolve = async () => {
    try {
      const payload = {
        tpartner_id: resolveForm.tpartner_id,
        product_id: resolveForm.product_id || null,
        site_id: resolveForm.site_id ? parseInt(resolveForm.site_id) : null,
      };
      const response = await api.post('/api/v1/vendor-lead-time/resolve', payload);
      setResolveResult(response.data);
    } catch (err) {
      setResolveResult({ error: err.response?.data?.detail || 'Resolution failed' });
    }
  };

  // Hierarchy level badge
  const levelBadge = (lt) => {
    if (lt.product_id) return <Badge variant="default">Product</Badge>;
    if (lt.product_group_id) return <Badge variant="secondary">Product Group</Badge>;
    if (lt.site_id) return <Badge variant="secondary">Site</Badge>;
    if (lt.region_id) return <Badge variant="outline">Region</Badge>;
    return <Badge variant="outline">Company</Badge>;
  };

  const SortHeader = ({ field, children }) => (
    <TableHead
      className="cursor-pointer select-none"
      onClick={() => toggleSort(field)}
    >
      <span className="flex items-center gap-1">
        {children}
        <ArrowUpDown className="h-3 w-3 text-muted-foreground" />
      </span>
    </TableHead>
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Vendor Lead Times</h1>
          <p className="text-sm text-muted-foreground">
            Manage supplier-specific lead times with hierarchical overrides
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => setResolveOpen(true)}
            leftIcon={<Layers className="h-4 w-4" />}
          >
            Resolve
          </Button>
          <Button
            variant="outline"
            onClick={fetchLeadTimes}
            leftIcon={<RefreshCw className="h-4 w-4" />}
          >
            Refresh
          </Button>
          <Button
            onClick={openCreate}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            Add Lead Time
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertTriangle className="h-4 w-4" />
          <span className="ml-2">{error}</span>
        </Alert>
      )}

      <Alert variant="info" className="mb-6">
        <strong>Hierarchical Resolution:</strong> Most specific lead time wins:
        Product-specific &rarr; Product Group &rarr; Site &rarr; Region &rarr; Company
      </Alert>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total Lead Times</p>
            <p className="text-3xl font-bold">{totalCount}</p>
            <Badge variant="default" className="mt-2">Active</Badge>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Avg Lead Time</p>
            <p className="text-3xl font-bold">{avgLeadTime} days</p>
            <p className="text-xs text-muted-foreground">Across all suppliers</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Product-Specific</p>
            <p className="text-3xl font-bold">{productSpecific}</p>
            <p className="text-xs text-muted-foreground">Most granular overrides</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Stochastic</p>
            <p className="text-3xl font-bold">{withVariability}</p>
            <p className="text-xs text-muted-foreground">With variability defined</p>
          </CardContent>
        </Card>
      </div>

      {/* Search */}
      <div className="flex gap-2 mb-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Filter by supplier ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Data Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Spinner className="h-8 w-8" />
              <span className="ml-3 text-muted-foreground">Loading lead times...</span>
            </div>
          ) : sorted.length === 0 ? (
            <div className="py-16 text-center">
              <Clock className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
              <p className="text-muted-foreground">No vendor lead times found</p>
              <Button className="mt-4" onClick={openCreate} leftIcon={<Plus className="h-4 w-4" />}>
                Add First Lead Time
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <SortHeader field="tpartner_id">Supplier</SortHeader>
                  <SortHeader field="lead_time_days">Lead Time (days)</SortHeader>
                  <TableHead>Variability</TableHead>
                  <TableHead>Level</TableHead>
                  <SortHeader field="product_id">Product</SortHeader>
                  <TableHead>Site</TableHead>
                  <SortHeader field="eff_start_date">Effective From</SortHeader>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.map((lt) => (
                  <TableRow key={lt.id}>
                    <TableCell className="font-medium">{lt.tpartner_id}</TableCell>
                    <TableCell>
                      <span className="font-mono">{lt.lead_time_days}</span>
                    </TableCell>
                    <TableCell>
                      {lt.lead_time_variability_days > 0 ? (
                        <span className="text-amber-600 font-mono">
                          +/- {lt.lead_time_variability_days}d
                        </span>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell>{levelBadge(lt)}</TableCell>
                    <TableCell>{formatProduct(lt.product_id) || '-'}</TableCell>
                    <TableCell>{formatSite(lt.site_id) || '-'}</TableCell>
                    <TableCell>
                      {lt.eff_start_date ? new Date(lt.eff_start_date).toLocaleDateString() : '-'}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" onClick={() => openEdit(lt)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => handleDelete(lt.id)}>
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Create / Edit Dialog */}
      <Modal
        isOpen={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editingItem ? 'Edit Vendor Lead Time' : 'Add Vendor Lead Time'}
      >
        <div className="space-y-4">
          <div>
            <Label>Supplier ID (required)</Label>
            <Input
              value={formData.tpartner_id}
              onChange={(e) => setFormData(f => ({ ...f, tpartner_id: e.target.value }))}
              placeholder="e.g., SUP-001"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Lead Time (days)</Label>
              <Input
                type="number"
                value={formData.lead_time_days}
                onChange={(e) => setFormData(f => ({ ...f, lead_time_days: e.target.value }))}
                placeholder="e.g., 7"
              />
            </div>
            <div>
              <Label>Variability (days)</Label>
              <Input
                type="number"
                value={formData.lead_time_variability_days}
                onChange={(e) => setFormData(f => ({ ...f, lead_time_variability_days: e.target.value }))}
                placeholder="e.g., 2 (optional)"
              />
            </div>
          </div>
          <div className="border-t pt-3">
            <p className="text-sm font-medium mb-2">Hierarchy Scope (leave blank for company-level)</p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Product ID</Label>
              <Input
                value={formData.product_id}
                onChange={(e) => setFormData(f => ({ ...f, product_id: e.target.value }))}
                placeholder="Most specific"
              />
            </div>
            <div>
              <Label>Product Group ID</Label>
              <Input
                value={formData.product_group_id}
                onChange={(e) => setFormData(f => ({ ...f, product_group_id: e.target.value }))}
                placeholder="Group level"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Site ID</Label>
              <Input
                value={formData.site_id}
                onChange={(e) => setFormData(f => ({ ...f, site_id: e.target.value }))}
                placeholder="Site level"
              />
            </div>
            <div>
              <Label>Region ID</Label>
              <Input
                value={formData.region_id}
                onChange={(e) => setFormData(f => ({ ...f, region_id: e.target.value }))}
                placeholder="Region level"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Effective Start Date</Label>
              <Input
                type="date"
                value={formData.eff_start_date}
                onChange={(e) => setFormData(f => ({ ...f, eff_start_date: e.target.value }))}
              />
            </div>
            <div>
              <Label>Effective End Date</Label>
              <Input
                type="date"
                value={formData.eff_end_date}
                onChange={(e) => setFormData(f => ({ ...f, eff_end_date: e.target.value }))}
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={!formData.tpartner_id || !formData.lead_time_days}>
              {editingItem ? 'Update' : 'Create'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Resolve Dialog */}
      <Modal
        isOpen={resolveOpen}
        onClose={() => { setResolveOpen(false); setResolveResult(null); }}
        title="Resolve Effective Lead Time"
      >
        <div className="space-y-4">
          <Alert variant="info">
            <strong>Hierarchical Resolution</strong> finds the most specific lead time
            for a given supplier + product + site combination.
          </Alert>
          <div>
            <Label>Supplier ID (required)</Label>
            <Input
              value={resolveForm.tpartner_id}
              onChange={(e) => setResolveForm(f => ({ ...f, tpartner_id: e.target.value }))}
              placeholder="e.g., SUP-001"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Product ID</Label>
              <Input
                value={resolveForm.product_id}
                onChange={(e) => setResolveForm(f => ({ ...f, product_id: e.target.value }))}
                placeholder="Optional"
              />
            </div>
            <div>
              <Label>Site ID</Label>
              <Input
                value={resolveForm.site_id}
                onChange={(e) => setResolveForm(f => ({ ...f, site_id: e.target.value }))}
                placeholder="Optional"
              />
            </div>
          </div>
          <Button onClick={handleResolve} disabled={!resolveForm.tpartner_id} className="w-full">
            Resolve Lead Time
          </Button>

          {resolveResult && !resolveResult.error && (
            <Card className="bg-green-50 border-green-200">
              <CardContent className="pt-4">
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle className="h-5 w-5 text-green-600" />
                  <span className="font-semibold text-green-800">Resolved</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span className="text-muted-foreground">Lead Time:</span>{' '}
                    <strong>{resolveResult.lead_time_days} days</strong>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Variability:</span>{' '}
                    <strong>{resolveResult.lead_time_variability_days ?? 'N/A'} days</strong>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Resolved From:</span>{' '}
                    <Badge>{resolveResult.resolved_from}</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
          {resolveResult?.error && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <span className="ml-2">{resolveResult.error}</span>
            </Alert>
          )}
        </div>
      </Modal>
    </div>
  );
};

export default VendorLeadTimes;
