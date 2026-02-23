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
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../../components/common';
import {
  Factory,
  Plus,
  RefreshCw,
  Pencil,
  Trash2,
  ArrowUpDown,
  AlertTriangle,
  Search,
  CheckCircle,
} from 'lucide-react';
import { api } from '../../services/api';

/**
 * Production Processes Management
 *
 * Manufacturing process definitions for MPS/MRP planning.
 *
 * Backend API: /api/v1/production-process/*
 * - CRUD for production processes
 * - By-site filtering
 * - MPS/MRP integration (operation time, setup time, yield, capacity)
 */
const ProductionProcesses = () => {
  const [processes, setProcesses] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortField, setSortField] = useState('id');
  const [sortDir, setSortDir] = useState('asc');

  // Create/edit dialog
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [formData, setFormData] = useState({
    id: '',
    description: '',
    site_id: '',
    process_type: 'STANDARD',
    operation_time: '',
    setup_time: '0',
    lot_size: '1',
    yield_percentage: '100',
    manufacturing_leadtime: '',
    manufacturing_capacity_hours: '',
    is_active: 'true',
  });

  const fetchProcesses = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get('/api/v1/production-process/');
      setProcesses(response.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load production processes');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProcesses();
  }, [fetchProcesses]);

  // Summary stats
  const totalProcesses = processes.length;
  const activeProcesses = processes.filter(p => p.is_active === 'true' || p.is_active === true).length;
  const avgOpTime = totalProcesses > 0
    ? (processes.reduce((s, p) => s + (p.operation_time || 0), 0) / totalProcesses).toFixed(1)
    : '0.0';
  const avgYield = totalProcesses > 0
    ? (processes.reduce((s, p) => s + (p.yield_percentage || 100), 0) / totalProcesses).toFixed(1)
    : '0.0';
  const totalCapacity = processes.reduce((s, p) => s + (p.manufacturing_capacity_hours || 0), 0).toFixed(0);

  // Filter + Sort
  const filtered = processes.filter(p => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (p.id || '').toLowerCase().includes(q)
      || (p.description || '').toLowerCase().includes(q)
      || (p.site_id || '').toString().toLowerCase().includes(q);
  });

  const toggleSort = (field) => {
    if (sortField === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortField(field); setSortDir('asc'); }
  };

  const sorted = [...filtered].sort((a, b) => {
    const aVal = a[sortField] ?? '';
    const bVal = b[sortField] ?? '';
    if (typeof aVal === 'number') return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
    return sortDir === 'asc'
      ? String(aVal).localeCompare(String(bVal))
      : String(bVal).localeCompare(String(aVal));
  });

  // CRUD
  const openCreate = () => {
    setEditingItem(null);
    setFormData({
      id: '', description: '', site_id: '', process_type: 'STANDARD',
      operation_time: '', setup_time: '0', lot_size: '1', yield_percentage: '100',
      manufacturing_leadtime: '', manufacturing_capacity_hours: '', is_active: 'true',
    });
    setDialogOpen(true);
  };

  const openEdit = (item) => {
    setEditingItem(item);
    setFormData({
      id: item.id || '',
      description: item.description || '',
      site_id: item.site_id || '',
      process_type: item.process_type || 'STANDARD',
      operation_time: item.operation_time?.toString() || '',
      setup_time: item.setup_time?.toString() || '0',
      lot_size: item.lot_size?.toString() || '1',
      yield_percentage: item.yield_percentage?.toString() || '100',
      manufacturing_leadtime: item.manufacturing_leadtime?.toString() || '',
      manufacturing_capacity_hours: item.manufacturing_capacity_hours?.toString() || '',
      is_active: item.is_active || 'true',
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    try {
      const payload = {
        id: formData.id,
        description: formData.description || null,
        site_id: formData.site_id || null,
        process_type: formData.process_type,
        operation_time: formData.operation_time ? parseFloat(formData.operation_time) : null,
        setup_time: formData.setup_time ? parseFloat(formData.setup_time) : null,
        lot_size: formData.lot_size ? parseFloat(formData.lot_size) : null,
        yield_percentage: formData.yield_percentage ? parseFloat(formData.yield_percentage) : null,
        manufacturing_leadtime: formData.manufacturing_leadtime ? parseInt(formData.manufacturing_leadtime) : null,
        manufacturing_capacity_hours: formData.manufacturing_capacity_hours ? parseFloat(formData.manufacturing_capacity_hours) : null,
        is_active: formData.is_active,
      };

      if (editingItem) {
        await api.put(`/api/v1/production-process/${editingItem.id}`, payload);
      } else {
        await api.post('/api/v1/production-process/', payload);
      }
      setDialogOpen(false);
      fetchProcesses();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save production process');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this production process?')) return;
    try {
      await api.delete(`/api/v1/production-process/${id}`);
      fetchProcesses();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete process');
    }
  };

  const SortHeader = ({ field, children }) => (
    <TableHead className="cursor-pointer select-none" onClick={() => toggleSort(field)}>
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
          <h1 className="text-2xl font-bold">Production Processes</h1>
          <p className="text-sm text-muted-foreground">
            Manufacturing process definitions for MPS/MRP planning
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetchProcesses} leftIcon={<RefreshCw className="h-4 w-4" />}>
            Refresh
          </Button>
          <Button onClick={openCreate} leftIcon={<Plus className="h-4 w-4" />}>
            Add Process
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
        <strong>Key Parameters:</strong> Operation time, setup time, lot size, yield %, lead time, capacity.
        These drive MPS rough-cut capacity checks and MRP BOM explosion.
      </Alert>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total Processes</p>
            <p className="text-3xl font-bold">{totalProcesses}</p>
            <p className="text-xs text-muted-foreground">{activeProcesses} active</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Avg Op Time</p>
            <p className="text-3xl font-bold">{avgOpTime} hrs</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Avg Yield</p>
            <p className="text-3xl font-bold">{avgYield}%</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total Capacity</p>
            <p className="text-3xl font-bold">{totalCapacity} hrs</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Process Types</p>
            <p className="text-3xl font-bold">
              {new Set(processes.map(p => p.process_type).filter(Boolean)).size}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Search */}
      <div className="flex gap-2 mb-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by ID, description, or site..."
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
              <span className="ml-3 text-muted-foreground">Loading processes...</span>
            </div>
          ) : sorted.length === 0 ? (
            <div className="py-16 text-center">
              <Factory className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
              <p className="text-muted-foreground">No production processes found</p>
              <Button className="mt-4" onClick={openCreate} leftIcon={<Plus className="h-4 w-4" />}>
                Add First Process
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <SortHeader field="id">Process ID</SortHeader>
                  <TableHead>Description</TableHead>
                  <TableHead>Type</TableHead>
                  <SortHeader field="operation_time">Op Time (hrs)</SortHeader>
                  <SortHeader field="setup_time">Setup (hrs)</SortHeader>
                  <SortHeader field="yield_percentage">Yield %</SortHeader>
                  <SortHeader field="manufacturing_leadtime">Lead Time (d)</SortHeader>
                  <SortHeader field="manufacturing_capacity_hours">Capacity (hrs)</SortHeader>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium font-mono">{p.id}</TableCell>
                    <TableCell className="max-w-[200px] truncate">{p.description || '-'}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{p.process_type || 'STANDARD'}</Badge>
                    </TableCell>
                    <TableCell className="font-mono">{p.operation_time ?? '-'}</TableCell>
                    <TableCell className="font-mono">{p.setup_time ?? '-'}</TableCell>
                    <TableCell>
                      <span className={`font-mono ${(p.yield_percentage || 100) < 95 ? 'text-amber-600' : ''}`}>
                        {p.yield_percentage ?? 100}%
                      </span>
                    </TableCell>
                    <TableCell className="font-mono">{p.manufacturing_leadtime ?? '-'}</TableCell>
                    <TableCell className="font-mono">{p.manufacturing_capacity_hours ?? '-'}</TableCell>
                    <TableCell>
                      {(p.is_active === 'true' || p.is_active === true) ? (
                        <Badge variant="default"><CheckCircle className="h-3 w-3 mr-1" />Active</Badge>
                      ) : (
                        <Badge variant="secondary">Inactive</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" onClick={() => openEdit(p)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => handleDelete(p.id)}>
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
        title={editingItem ? 'Edit Production Process' : 'Add Production Process'}
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Process ID (required)</Label>
              <Input
                value={formData.id}
                onChange={(e) => setFormData(f => ({ ...f, id: e.target.value }))}
                placeholder="e.g., PROC-CASE-001"
                disabled={!!editingItem}
              />
            </div>
            <div>
              <Label>Site ID</Label>
              <Input
                value={formData.site_id}
                onChange={(e) => setFormData(f => ({ ...f, site_id: e.target.value }))}
                placeholder="Optional"
              />
            </div>
          </div>
          <div>
            <Label>Description</Label>
            <Input
              value={formData.description}
              onChange={(e) => setFormData(f => ({ ...f, description: e.target.value }))}
              placeholder="e.g., Beer Case Assembly Line"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Process Type</Label>
              <select
                className="w-full border rounded-md px-3 py-2 text-sm"
                value={formData.process_type}
                onChange={(e) => setFormData(f => ({ ...f, process_type: e.target.value }))}
              >
                <option value="STANDARD">Standard</option>
                <option value="BATCH">Batch</option>
                <option value="CONTINUOUS">Continuous</option>
                <option value="ASSEMBLY">Assembly</option>
                <option value="PACKAGING">Packaging</option>
              </select>
            </div>
            <div>
              <Label>Status</Label>
              <select
                className="w-full border rounded-md px-3 py-2 text-sm"
                value={formData.is_active}
                onChange={(e) => setFormData(f => ({ ...f, is_active: e.target.value }))}
              >
                <option value="true">Active</option>
                <option value="false">Inactive</option>
              </select>
            </div>
          </div>
          <div className="border-t pt-3">
            <p className="text-sm font-medium mb-2">Manufacturing Parameters</p>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <Label>Operation Time (hrs)</Label>
              <Input
                type="number"
                step="0.1"
                value={formData.operation_time}
                onChange={(e) => setFormData(f => ({ ...f, operation_time: e.target.value }))}
                placeholder="e.g., 2.5"
              />
            </div>
            <div>
              <Label>Setup Time (hrs)</Label>
              <Input
                type="number"
                step="0.1"
                value={formData.setup_time}
                onChange={(e) => setFormData(f => ({ ...f, setup_time: e.target.value }))}
                placeholder="e.g., 0.5"
              />
            </div>
            <div>
              <Label>Lot Size</Label>
              <Input
                type="number"
                value={formData.lot_size}
                onChange={(e) => setFormData(f => ({ ...f, lot_size: e.target.value }))}
                placeholder="e.g., 100"
              />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <Label>Yield %</Label>
              <Input
                type="number"
                step="0.1"
                value={formData.yield_percentage}
                onChange={(e) => setFormData(f => ({ ...f, yield_percentage: e.target.value }))}
                placeholder="e.g., 98.5"
              />
            </div>
            <div>
              <Label>Lead Time (days)</Label>
              <Input
                type="number"
                value={formData.manufacturing_leadtime}
                onChange={(e) => setFormData(f => ({ ...f, manufacturing_leadtime: e.target.value }))}
                placeholder="e.g., 5"
              />
            </div>
            <div>
              <Label>Capacity (hrs/period)</Label>
              <Input
                type="number"
                value={formData.manufacturing_capacity_hours}
                onChange={(e) => setFormData(f => ({ ...f, manufacturing_capacity_hours: e.target.value }))}
                placeholder="e.g., 168"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={!formData.id}>
              {editingItem ? 'Update' : 'Create'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default ProductionProcesses;
