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
  BarChart3,
  Plus,
  RefreshCw,
  Pencil,
  Trash2,
  AlertTriangle,
  ArrowUpDown,
  Gauge,
  Search,
} from 'lucide-react';
import { api } from '../../services/api';

/**
 * Resource Capacity Management
 *
 * Tracks resource availability, utilization, and bottleneck analysis.
 *
 * Backend API: /api/v1/resource-capacity/*
 * - CRUD for capacity records
 * - Utilization analysis (GET /utilization/analysis)
 * - Bottleneck identification (GET /bottlenecks/identify)
 */
const ResourceCapacity = () => {
  const [activeTab, setActiveTab] = useState('records');
  const [capacities, setCapacities] = useState([]);
  const [utilization, setUtilization] = useState([]);
  const [bottlenecks, setBottlenecks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortField, setSortField] = useState('resource_id');
  const [sortDir, setSortDir] = useState('asc');

  // Create/edit dialog
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [formData, setFormData] = useState({
    resource_id: '',
    resource_name: '',
    resource_type: 'MACHINE',
    site_id: '',
    capacity_date: new Date().toISOString().split('T')[0],
    available_capacity_hours: '',
    utilized_capacity_hours: '0',
    capacity_efficiency: '1.0',
    planned_downtime_hours: '0',
    unplanned_downtime_hours: '0',
    overtime_hours: '0',
  });

  const fetchCapacities = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (searchQuery) params.resource_id = searchQuery;
      const response = await api.get('/api/v1/resource-capacity/', { params });
      setCapacities(response.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load resource capacities');
    } finally {
      setLoading(false);
    }
  }, [searchQuery]);

  const fetchUtilization = useCallback(async () => {
    try {
      const response = await api.get('/api/v1/resource-capacity/utilization/analysis');
      setUtilization(response.data || []);
    } catch (err) {
      // silently fail - tab may not be active
    }
  }, []);

  const fetchBottlenecks = useCallback(async () => {
    try {
      const response = await api.get('/api/v1/resource-capacity/bottlenecks/identify');
      setBottlenecks(response.data || []);
    } catch (err) {
      // silently fail
    }
  }, []);

  useEffect(() => {
    fetchCapacities();
  }, [fetchCapacities]);

  useEffect(() => {
    if (activeTab === 'utilization') fetchUtilization();
    if (activeTab === 'bottlenecks') fetchBottlenecks();
  }, [activeTab, fetchUtilization, fetchBottlenecks]);

  // Summary stats
  const totalResources = new Set(capacities.map(c => c.resource_id)).size;
  const avgUtil = capacities.length > 0
    ? (capacities.reduce((s, c) => {
        const avail = c.available_capacity_hours || 1;
        return s + (c.utilized_capacity_hours / avail) * 100;
      }, 0) / capacities.length).toFixed(1)
    : '0.0';
  const bottleneckCount = bottlenecks.filter(b => b.bottleneck_severity === 'high' || b.bottleneck_severity === 'critical').length;
  const totalAvail = capacities.reduce((s, c) => s + (c.remaining_capacity_hours || 0), 0).toFixed(0);

  // Sorting
  const toggleSort = (field) => {
    if (sortField === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortField(field); setSortDir('asc'); }
  };

  const sorted = [...capacities].sort((a, b) => {
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
      resource_id: '', resource_name: '', resource_type: 'MACHINE', site_id: '',
      capacity_date: new Date().toISOString().split('T')[0],
      available_capacity_hours: '', utilized_capacity_hours: '0',
      capacity_efficiency: '1.0', planned_downtime_hours: '0',
      unplanned_downtime_hours: '0', overtime_hours: '0',
    });
    setDialogOpen(true);
  };

  const openEdit = (item) => {
    setEditingItem(item);
    setFormData({
      resource_id: item.resource_id || '',
      resource_name: item.resource_name || '',
      resource_type: item.resource_type || 'MACHINE',
      site_id: item.site_id || '',
      capacity_date: item.capacity_date || '',
      available_capacity_hours: item.available_capacity_hours?.toString() || '',
      utilized_capacity_hours: item.utilized_capacity_hours?.toString() || '0',
      capacity_efficiency: item.capacity_efficiency?.toString() || '1.0',
      planned_downtime_hours: item.planned_downtime_hours?.toString() || '0',
      unplanned_downtime_hours: item.unplanned_downtime_hours?.toString() || '0',
      overtime_hours: item.overtime_hours?.toString() || '0',
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    try {
      const payload = {
        resource_id: formData.resource_id,
        resource_name: formData.resource_name || null,
        resource_type: formData.resource_type,
        site_id: formData.site_id || null,
        capacity_date: formData.capacity_date,
        available_capacity_hours: parseFloat(formData.available_capacity_hours),
        utilized_capacity_hours: parseFloat(formData.utilized_capacity_hours || '0'),
        capacity_efficiency: parseFloat(formData.capacity_efficiency || '1.0'),
        planned_downtime_hours: parseFloat(formData.planned_downtime_hours || '0'),
        unplanned_downtime_hours: parseFloat(formData.unplanned_downtime_hours || '0'),
        overtime_hours: parseFloat(formData.overtime_hours || '0'),
      };
      if (editingItem) {
        await api.put(`/api/v1/resource-capacity/${editingItem.id}`, payload);
      } else {
        await api.post('/api/v1/resource-capacity/', payload);
      }
      setDialogOpen(false);
      fetchCapacities();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save capacity record');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this capacity record?')) return;
    try {
      await api.delete(`/api/v1/resource-capacity/${id}`);
      fetchCapacities();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete record');
    }
  };

  // Utilization bar color
  const utilColor = (pct) => {
    if (pct >= 95) return 'bg-red-500';
    if (pct >= 80) return 'bg-amber-500';
    return 'bg-green-500';
  };

  const severityBadge = (severity) => {
    const variants = { critical: 'destructive', high: 'destructive', medium: 'secondary', low: 'outline' };
    return <Badge variant={variants[severity] || 'outline'}>{severity}</Badge>;
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
          <h1 className="text-2xl font-bold">Resource Capacity</h1>
          <p className="text-sm text-muted-foreground">Capacity tracking, utilization analysis, and bottleneck detection</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => { fetchCapacities(); fetchUtilization(); fetchBottlenecks(); }} leftIcon={<RefreshCw className="h-4 w-4" />}>
            Refresh
          </Button>
          <Button onClick={openCreate} leftIcon={<Plus className="h-4 w-4" />}>
            Add Capacity
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertTriangle className="h-4 w-4" />
          <span className="ml-2">{error}</span>
        </Alert>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total Resources</p>
            <p className="text-3xl font-bold">{totalResources}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Avg Utilization</p>
            <p className="text-3xl font-bold">{avgUtil}%</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Bottlenecks</p>
            <p className={`text-3xl font-bold ${bottleneckCount > 0 ? 'text-red-600' : ''}`}>
              {bottleneckCount}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Available Capacity</p>
            <p className="text-3xl font-bold">{totalAvail} hrs</p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="records">
            <BarChart3 className="h-4 w-4 mr-1" /> Records ({capacities.length})
          </TabsTrigger>
          <TabsTrigger value="utilization">
            <Gauge className="h-4 w-4 mr-1" /> Utilization
          </TabsTrigger>
          <TabsTrigger value="bottlenecks">
            <AlertTriangle className="h-4 w-4 mr-1" /> Bottlenecks
            {bottleneckCount > 0 && (
              <Badge variant="destructive" className="ml-1">{bottleneckCount}</Badge>
            )}
          </TabsTrigger>
        </TabsList>

        {/* Records Tab */}
        <TabsContent value="records">
          <div className="flex gap-2 mb-4">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Filter by resource ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>
          </div>
          <Card>
            <CardContent className="p-0">
              {loading ? (
                <div className="flex items-center justify-center py-16">
                  <Spinner className="h-8 w-8" />
                  <span className="ml-3 text-muted-foreground">Loading...</span>
                </div>
              ) : sorted.length === 0 ? (
                <div className="py-16 text-center">
                  <BarChart3 className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
                  <p className="text-muted-foreground">No capacity records found</p>
                  <Button className="mt-4" onClick={openCreate} leftIcon={<Plus className="h-4 w-4" />}>
                    Add First Record
                  </Button>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <SortHeader field="resource_id">Resource</SortHeader>
                      <TableHead>Type</TableHead>
                      <SortHeader field="capacity_date">Date</SortHeader>
                      <SortHeader field="available_capacity_hours">Available (hrs)</SortHeader>
                      <SortHeader field="utilized_capacity_hours">Utilized (hrs)</SortHeader>
                      <TableHead>Utilization</TableHead>
                      <SortHeader field="remaining_capacity_hours">Remaining</SortHeader>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sorted.map((c) => {
                      const utilPct = c.available_capacity_hours > 0
                        ? ((c.utilized_capacity_hours / c.available_capacity_hours) * 100).toFixed(1)
                        : 0;
                      return (
                        <TableRow key={c.id}>
                          <TableCell>
                            <div>
                              <span className="font-medium">{c.resource_id}</span>
                              {c.resource_name && (
                                <p className="text-xs text-muted-foreground">{c.resource_name}</p>
                              )}
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">{c.resource_type || 'N/A'}</Badge>
                          </TableCell>
                          <TableCell>{c.capacity_date}</TableCell>
                          <TableCell className="font-mono">{c.available_capacity_hours}</TableCell>
                          <TableCell className="font-mono">{c.utilized_capacity_hours}</TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <div className="w-20 h-2 bg-gray-200 rounded-full overflow-hidden">
                                <div
                                  className={`h-full ${utilColor(utilPct)} rounded-full`}
                                  style={{ width: `${Math.min(utilPct, 100)}%` }}
                                />
                              </div>
                              <span className="text-xs font-mono">{utilPct}%</span>
                            </div>
                          </TableCell>
                          <TableCell className="font-mono">{c.remaining_capacity_hours}</TableCell>
                          <TableCell className="text-right">
                            <div className="flex justify-end gap-1">
                              <Button size="sm" variant="ghost" onClick={() => openEdit(c)}>
                                <Pencil className="h-4 w-4" />
                              </Button>
                              <Button size="sm" variant="ghost" onClick={() => handleDelete(c.id)}>
                                <Trash2 className="h-4 w-4 text-red-500" />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Utilization Tab */}
        <TabsContent value="utilization">
          <Card>
            <CardContent className="p-0">
              {utilization.length === 0 ? (
                <div className="py-16 text-center">
                  <Gauge className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
                  <p className="text-muted-foreground">No utilization data available</p>
                  <p className="text-xs text-muted-foreground mt-1">Add capacity records to see utilization analysis</p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Resource</TableHead>
                      <TableHead>Total Available (hrs)</TableHead>
                      <TableHead>Total Utilized (hrs)</TableHead>
                      <TableHead>Utilization</TableHead>
                      <TableHead>Bottleneck Score</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {utilization.map((u, i) => (
                      <TableRow key={i}>
                        <TableCell>
                          <div>
                            <span className="font-medium">{u.resource_id}</span>
                            {u.resource_name && (
                              <p className="text-xs text-muted-foreground">{u.resource_name}</p>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="font-mono">{u.total_available_hours?.toFixed(1)}</TableCell>
                        <TableCell className="font-mono">{u.total_utilized_hours?.toFixed(1)}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <div className="w-24 h-3 bg-gray-200 rounded-full overflow-hidden">
                              <div
                                className={`h-full ${utilColor(u.utilization_pct)} rounded-full`}
                                style={{ width: `${Math.min(u.utilization_pct, 100)}%` }}
                              />
                            </div>
                            <span className="font-mono text-sm">{u.utilization_pct?.toFixed(1)}%</span>
                          </div>
                        </TableCell>
                        <TableCell>
                          <span className={`font-mono ${u.bottleneck_score >= 80 ? 'text-red-600 font-bold' : ''}`}>
                            {u.bottleneck_score?.toFixed(0)}/100
                          </span>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Bottlenecks Tab */}
        <TabsContent value="bottlenecks">
          {bottlenecks.length === 0 ? (
            <Card>
              <CardContent className="py-16 text-center">
                <AlertTriangle className="h-12 w-12 text-green-500 mx-auto mb-3" />
                <p className="text-lg font-medium text-green-700">No bottlenecks detected</p>
                <p className="text-sm text-muted-foreground mt-1">All resources are operating within capacity limits</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {bottlenecks.map((b, i) => (
                <Card key={i} className={
                  b.bottleneck_severity === 'critical' ? 'border-red-500 border-2' :
                  b.bottleneck_severity === 'high' ? 'border-red-300' : ''
                }>
                  <CardContent className="pt-4">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-semibold">{b.resource_id}</span>
                          {b.resource_name && <span className="text-muted-foreground">({b.resource_name})</span>}
                          {severityBadge(b.bottleneck_severity)}
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Avg utilization: <strong>{b.avg_utilization_pct?.toFixed(1)}%</strong>
                          {' | '}
                          Days at capacity (&gt;95%): <strong>{b.days_at_capacity}</strong>
                        </p>
                      </div>
                      <div className="w-16 h-16 rounded-full border-4 flex items-center justify-center"
                        style={{ borderColor: b.bottleneck_severity === 'critical' ? '#ef4444' : b.bottleneck_severity === 'high' ? '#f97316' : '#eab308' }}
                      >
                        <span className="text-sm font-bold">{b.avg_utilization_pct?.toFixed(0)}%</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Create / Edit Dialog */}
      <Modal
        isOpen={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editingItem ? 'Edit Capacity Record' : 'Add Capacity Record'}
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Resource ID (required)</Label>
              <Input
                value={formData.resource_id}
                onChange={(e) => setFormData(f => ({ ...f, resource_id: e.target.value }))}
                placeholder="e.g., MACH-001"
              />
            </div>
            <div>
              <Label>Resource Name</Label>
              <Input
                value={formData.resource_name}
                onChange={(e) => setFormData(f => ({ ...f, resource_name: e.target.value }))}
                placeholder="e.g., CNC Mill #1"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Resource Type</Label>
              <select
                className="w-full border rounded-md px-3 py-2 text-sm"
                value={formData.resource_type}
                onChange={(e) => setFormData(f => ({ ...f, resource_type: e.target.value }))}
              >
                <option value="MACHINE">Machine</option>
                <option value="LABOR">Labor</option>
                <option value="FACILITY">Facility</option>
                <option value="UTILITY">Utility</option>
                <option value="TOOL">Tool</option>
              </select>
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
            <Label>Capacity Date</Label>
            <Input
              type="date"
              value={formData.capacity_date}
              onChange={(e) => setFormData(f => ({ ...f, capacity_date: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Available Capacity (hrs)</Label>
              <Input
                type="number"
                value={formData.available_capacity_hours}
                onChange={(e) => setFormData(f => ({ ...f, available_capacity_hours: e.target.value }))}
                placeholder="e.g., 8"
              />
            </div>
            <div>
              <Label>Utilized Capacity (hrs)</Label>
              <Input
                type="number"
                value={formData.utilized_capacity_hours}
                onChange={(e) => setFormData(f => ({ ...f, utilized_capacity_hours: e.target.value }))}
                placeholder="e.g., 6"
              />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <Label>Efficiency</Label>
              <Input
                type="number"
                step="0.01"
                value={formData.capacity_efficiency}
                onChange={(e) => setFormData(f => ({ ...f, capacity_efficiency: e.target.value }))}
              />
            </div>
            <div>
              <Label>Planned Downtime (hrs)</Label>
              <Input
                type="number"
                value={formData.planned_downtime_hours}
                onChange={(e) => setFormData(f => ({ ...f, planned_downtime_hours: e.target.value }))}
              />
            </div>
            <div>
              <Label>Overtime (hrs)</Label>
              <Input
                type="number"
                value={formData.overtime_hours}
                onChange={(e) => setFormData(f => ({ ...f, overtime_hours: e.target.value }))}
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={!formData.resource_id || !formData.available_capacity_hours}>
              {editingItem ? 'Update' : 'Create'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default ResourceCapacity;
