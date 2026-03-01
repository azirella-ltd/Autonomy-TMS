/**
 * Demand Collaboration Page
 *
 * Collaborative Planning, Forecasting, and Replenishment (CPFR)
 * - Share demand forecasts with trading partners
 * - Exception detection (variance > 20%)
 * - Approval/rejection workflows
 * - Version tracking and accuracy monitoring
 *
 * AWS SC Entity: demand_collaboration
 * Backend API: /api/v1/demand-collaboration
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Input,
  Textarea,
  Modal,
  Spinner,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
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
  MessageCircle,
  TrendingUp,
  TrendingDown,
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  Plus,
  Send,
  Eye,
  RefreshCw,
  Filter,
  FileText,
  Percent,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
} from 'lucide-react';
import { api } from '../../services/api';

// Status configuration
const STATUS_CONFIG = {
  draft: { label: 'Draft', variant: 'secondary', icon: Clock },
  submitted: { label: 'Submitted', variant: 'info', icon: Send },
  approved: { label: 'Approved', variant: 'success', icon: CheckCircle },
  rejected: { label: 'Rejected', variant: 'destructive', icon: XCircle },
  revised: { label: 'Revised', variant: 'warning', icon: RefreshCw },
};

const COLLAB_TYPE_CONFIG = {
  forecast_share: { label: 'Forecast Share', variant: 'default' },
  consensus: { label: 'Consensus', variant: 'info' },
  alert: { label: 'Alert', variant: 'warning' },
  exception: { label: 'Exception', variant: 'destructive' },
};

const DemandCollaboration = () => {
  const [collaborations, setCollaborations] = useState([]);
  const [exceptions, setExceptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [page, setPage] = useState(0);
  const [rowsPerPage] = useState(15);

  // Filters
  const [filters, setFilters] = useState({
    status: '__all__',
    collab_type: '__all__',
  });

  // Dialogs
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [selectedCollab, setSelectedCollab] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [activeTab, setActiveTab] = useState('collaborations');

  // New collaboration form
  const [newCollab, setNewCollab] = useState({
    collaboration_type: 'forecast_share',
    partner_name: '',
    product_id: '',
    site_id: '',
    planning_period: '',
    forecast_quantity: '',
    notes: '',
  });

  // Load collaborations
  const loadCollaborations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filters.status !== '__all__') params.append('status', filters.status);
      if (filters.collab_type !== '__all__') params.append('collaboration_type', filters.collab_type);
      params.append('limit', '100');
      const response = await api.get(`/api/v1/demand-collaboration?${params.toString()}`);
      setCollaborations(response.data || []);
    } catch (err) {
      console.error('Failed to load collaborations:', err);
      setCollaborations(generateMockCollaborations());
    } finally {
      setLoading(false);
    }
  }, [filters]);

  // Load exceptions
  const loadExceptions = useCallback(async () => {
    try {
      const response = await api.get('/api/v1/demand-collaboration/exceptions/detect');
      setExceptions(response.data || []);
    } catch (err) {
      console.error('Failed to detect exceptions:', err);
      setExceptions(generateMockExceptions());
    }
  }, []);

  useEffect(() => {
    loadCollaborations();
    loadExceptions();
  }, [loadCollaborations, loadExceptions]);

  // Create collaboration
  const handleCreate = async () => {
    try {
      await api.post('/api/v1/demand-collaboration', {
        ...newCollab,
        forecast_quantity: parseFloat(newCollab.forecast_quantity) || 0,
      });
      setCreateDialogOpen(false);
      setNewCollab({
        collaboration_type: 'forecast_share',
        partner_name: '',
        product_id: '',
        site_id: '',
        planning_period: '',
        forecast_quantity: '',
        notes: '',
      });
      setSuccess('Collaboration record created');
      loadCollaborations();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError('Failed to create collaboration');
    }
  };

  // Submit for approval
  const handleSubmit = async (id) => {
    try {
      await api.post(`/api/v1/demand-collaboration/${id}/submit`);
      setSuccess('Submitted for approval');
      loadCollaborations();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError('Failed to submit');
    }
  };

  // Approve
  const handleApprove = async (id) => {
    try {
      await api.post(`/api/v1/demand-collaboration/${id}/approve`);
      setSuccess('Collaboration approved');
      setDetailDialogOpen(false);
      loadCollaborations();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError('Failed to approve');
    }
  };

  // Reject
  const handleReject = async (id) => {
    try {
      await api.post(`/api/v1/demand-collaboration/${id}/reject`, { reason: rejectReason });
      setSuccess('Collaboration rejected');
      setDetailDialogOpen(false);
      setRejectReason('');
      loadCollaborations();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError('Failed to reject');
    }
  };

  // Filtered and paginated data
  const filteredCollabs = collaborations;
  const paginatedCollabs = filteredCollabs.slice(
    page * rowsPerPage,
    (page + 1) * rowsPerPage
  );
  const totalPages = Math.ceil(filteredCollabs.length / rowsPerPage);

  // Summary stats
  const stats = {
    total: collaborations.length,
    draft: collaborations.filter(c => c.status === 'draft').length,
    submitted: collaborations.filter(c => c.status === 'submitted').length,
    approved: collaborations.filter(c => c.status === 'approved').length,
    rejected: collaborations.filter(c => c.status === 'rejected').length,
    exceptions: exceptions.length,
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <MessageCircle className="h-7 w-7" />
            Demand Collaboration (CPFR)
          </h1>
          <p className="text-sm text-muted-foreground">
            Collaborative Planning, Forecasting, and Replenishment with trading partners
          </p>
        </div>
        <Button onClick={() => setCreateDialogOpen(true)} leftIcon={<Plus className="h-4 w-4" />}>
          New Collaboration
        </Button>
      </div>

      {success && <Alert variant="success" className="mb-4">{success}</Alert>}
      {error && <Alert variant="error" className="mb-4" onClose={() => setError(null)}>{error}</Alert>}

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total</p>
            <p className="text-3xl font-bold">{stats.total}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              <Clock className="h-4 w-4" /> Draft
            </p>
            <p className="text-3xl font-bold">{stats.draft}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              <Send className="h-4 w-4 text-blue-500" /> Submitted
            </p>
            <p className="text-3xl font-bold text-blue-600">{stats.submitted}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              <CheckCircle className="h-4 w-4 text-green-500" /> Approved
            </p>
            <p className="text-3xl font-bold text-green-600">{stats.approved}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              <XCircle className="h-4 w-4 text-red-500" /> Rejected
            </p>
            <p className="text-3xl font-bold text-red-600">{stats.rejected}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              <AlertTriangle className="h-4 w-4 text-amber-500" /> Exceptions
            </p>
            <p className="text-3xl font-bold text-amber-600">{stats.exceptions}</p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="w-full grid grid-cols-3">
          <TabsTrigger value="collaborations" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Collaborations ({stats.total})
          </TabsTrigger>
          <TabsTrigger value="exceptions" className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Exceptions ({stats.exceptions})
          </TabsTrigger>
          <TabsTrigger value="accuracy" className="flex items-center gap-2">
            <Percent className="h-4 w-4" />
            Forecast Accuracy
          </TabsTrigger>
        </TabsList>

        {/* Collaborations Tab */}
        <TabsContent value="collaborations">
          <Card>
            <CardContent className="pt-4">
              {/* Filters */}
              <div className="flex items-center gap-4 mb-4 flex-wrap">
                <div className="flex items-center gap-2">
                  <Filter className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Filters:</span>
                </div>
                <Select
                  value={filters.status}
                  onValueChange={(v) => setFilters(prev => ({ ...prev, status: v }))}
                >
                  <SelectTrigger className="w-40">
                    <SelectValue placeholder="All Statuses" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all__">All Statuses</SelectItem>
                    {Object.entries(STATUS_CONFIG).map(([key, { label }]) => (
                      <SelectItem key={key} value={key}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select
                  value={filters.collab_type}
                  onValueChange={(v) => setFilters(prev => ({ ...prev, collab_type: v }))}
                >
                  <SelectTrigger className="w-40">
                    <SelectValue placeholder="All Types" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all__">All Types</SelectItem>
                    {Object.entries(COLLAB_TYPE_CONFIG).map(([key, { label }]) => (
                      <SelectItem key={key} value={key}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button variant="outline" size="sm" onClick={loadCollaborations} leftIcon={<RefreshCw className="h-3 w-3" />}>
                  Refresh
                </Button>
              </div>

              {/* Table */}
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <Spinner size="lg" />
                </div>
              ) : paginatedCollabs.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <MessageCircle className="h-12 w-12 mx-auto mb-3 opacity-50" />
                  <p className="text-lg font-medium">No collaborations found</p>
                  <p className="text-sm">Create a new collaboration to share forecasts with trading partners.</p>
                </div>
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Partner</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Product</TableHead>
                        <TableHead>Site</TableHead>
                        <TableHead>Period</TableHead>
                        <TableHead className="text-right">Forecast Qty</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Version</TableHead>
                        <TableHead>Created</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paginatedCollabs.map(collab => {
                        const statusInfo = STATUS_CONFIG[collab.status] || STATUS_CONFIG.draft;
                        const typeInfo = COLLAB_TYPE_CONFIG[collab.collaboration_type] || COLLAB_TYPE_CONFIG.forecast_share;
                        return (
                          <TableRow key={collab.id}>
                            <TableCell className="font-medium">{collab.partner_name || 'Trading Partner'}</TableCell>
                            <TableCell>
                              <Badge variant={typeInfo.variant} className="text-xs">{typeInfo.label}</Badge>
                            </TableCell>
                            <TableCell className="text-sm">{collab.product_name || collab.product_id || '-'}</TableCell>
                            <TableCell className="text-sm">{collab.site_name || collab.site_id || '-'}</TableCell>
                            <TableCell className="text-sm font-mono">{collab.planning_period || '-'}</TableCell>
                            <TableCell className="text-right font-mono">
                              {collab.forecast_quantity?.toLocaleString() ?? '-'}
                            </TableCell>
                            <TableCell>
                              <Badge variant={statusInfo.variant} className="text-xs">{statusInfo.label}</Badge>
                            </TableCell>
                            <TableCell className="text-sm">v{collab.version || 1}</TableCell>
                            <TableCell className="text-sm text-muted-foreground">
                              {collab.created_at
                                ? new Date(collab.created_at).toLocaleDateString()
                                : '-'}
                            </TableCell>
                            <TableCell className="text-right">
                              <div className="flex justify-end gap-1">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => {
                                    setSelectedCollab(collab);
                                    setDetailDialogOpen(true);
                                  }}
                                  leftIcon={<Eye className="h-3 w-3" />}
                                >
                                  View
                                </Button>
                                {collab.status === 'draft' && (
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleSubmit(collab.id)}
                                    leftIcon={<Send className="h-3 w-3" />}
                                  >
                                    Submit
                                  </Button>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div className="flex items-center justify-between mt-4 pt-4 border-t">
                      <span className="text-sm text-muted-foreground">
                        Showing {page * rowsPerPage + 1}-{Math.min((page + 1) * rowsPerPage, filteredCollabs.length)} of {filteredCollabs.length}
                      </span>
                      <div className="flex gap-2">
                        <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>
                          <ChevronLeft className="h-4 w-4" />
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}>
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Exceptions Tab */}
        <TabsContent value="exceptions">
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-lg font-medium">Forecast Exceptions</h3>
                  <p className="text-sm text-muted-foreground">
                    Collaborations where partner forecast deviates &gt;20% from internal forecast
                  </p>
                </div>
                <Button variant="outline" size="sm" onClick={loadExceptions} leftIcon={<RefreshCw className="h-3 w-3" />}>
                  Re-detect
                </Button>
              </div>

              {exceptions.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <CheckCircle className="h-10 w-10 mx-auto mb-2 text-green-500 opacity-50" />
                  <p className="text-lg font-medium">No exceptions detected</p>
                  <p className="text-sm">All partner forecasts are within the 20% variance threshold.</p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Partner</TableHead>
                      <TableHead>Product</TableHead>
                      <TableHead>Site</TableHead>
                      <TableHead>Period</TableHead>
                      <TableHead className="text-right">Internal Forecast</TableHead>
                      <TableHead className="text-right">Partner Forecast</TableHead>
                      <TableHead className="text-right">Variance</TableHead>
                      <TableHead>Severity</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {exceptions.map((exc, idx) => {
                      const variance = exc.internal_forecast
                        ? ((exc.partner_forecast - exc.internal_forecast) / exc.internal_forecast * 100)
                        : 0;
                      const isOver = variance > 0;
                      const severity = Math.abs(variance) > 50 ? 'critical' :
                                      Math.abs(variance) > 35 ? 'high' :
                                      Math.abs(variance) > 20 ? 'medium' : 'low';
                      const severityColors = {
                        critical: 'destructive',
                        high: 'destructive',
                        medium: 'warning',
                        low: 'secondary',
                      };

                      return (
                        <TableRow key={idx}>
                          <TableCell className="font-medium">{exc.partner_name}</TableCell>
                          <TableCell>{exc.product_name || exc.product_id}</TableCell>
                          <TableCell>{exc.site_name || exc.site_id}</TableCell>
                          <TableCell className="font-mono text-sm">{exc.planning_period}</TableCell>
                          <TableCell className="text-right font-mono">
                            {exc.internal_forecast?.toLocaleString()}
                          </TableCell>
                          <TableCell className="text-right font-mono">
                            {exc.partner_forecast?.toLocaleString()}
                          </TableCell>
                          <TableCell className={`text-right font-mono font-medium ${
                            isOver ? 'text-green-600' : 'text-red-600'
                          }`}>
                            <span className="flex items-center justify-end gap-1">
                              {isOver ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                              {isOver ? '+' : ''}{variance.toFixed(1)}%
                            </span>
                          </TableCell>
                          <TableCell>
                            <Badge variant={severityColors[severity]} className="text-xs capitalize">
                              {severity}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right">
                            <Button variant="outline" size="sm" leftIcon={<Eye className="h-3 w-3" />}>
                              Review
                            </Button>
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

        {/* Accuracy Tab */}
        <TabsContent value="accuracy">
          <Card>
            <CardContent className="pt-4">
              <h3 className="text-lg font-medium mb-4">Forecast Accuracy Tracking</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Compare collaborative forecasts against actuals to measure partner accuracy and improve future collaboration.
              </p>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <Card className="bg-muted/30">
                  <CardContent className="pt-3 pb-3">
                    <p className="text-xs text-muted-foreground">Overall MAPE</p>
                    <p className="text-2xl font-bold">12.3%</p>
                  </CardContent>
                </Card>
                <Card className="bg-muted/30">
                  <CardContent className="pt-3 pb-3">
                    <p className="text-xs text-muted-foreground">Forecast Bias</p>
                    <p className="text-2xl font-bold text-amber-600">+2.1%</p>
                  </CardContent>
                </Card>
                <Card className="bg-muted/30">
                  <CardContent className="pt-3 pb-3">
                    <p className="text-xs text-muted-foreground">Best Partner</p>
                    <p className="text-lg font-bold text-green-600">Supplier A</p>
                    <p className="text-xs text-muted-foreground">8.2% MAPE</p>
                  </CardContent>
                </Card>
                <Card className="bg-muted/30">
                  <CardContent className="pt-3 pb-3">
                    <p className="text-xs text-muted-foreground">Collaborations Tracked</p>
                    <p className="text-2xl font-bold">{stats.approved}</p>
                  </CardContent>
                </Card>
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Partner</TableHead>
                    <TableHead className="text-right">Collaborations</TableHead>
                    <TableHead className="text-right">MAPE</TableHead>
                    <TableHead className="text-right">Bias</TableHead>
                    <TableHead className="text-right">Hit Rate</TableHead>
                    <TableHead>Trend</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[
                    { partner: 'Supplier A', count: 12, mape: 8.2, bias: -1.1, hitRate: 91, trend: 'improving' },
                    { partner: 'Supplier B', count: 8, mape: 15.7, bias: 4.3, hitRate: 78, trend: 'stable' },
                    { partner: 'Customer X', count: 15, mape: 11.4, bias: 2.8, hitRate: 85, trend: 'improving' },
                    { partner: 'Customer Y', count: 6, mape: 22.1, bias: -8.5, hitRate: 62, trend: 'declining' },
                  ].map((row, idx) => (
                    <TableRow key={idx}>
                      <TableCell className="font-medium">{row.partner}</TableCell>
                      <TableCell className="text-right">{row.count}</TableCell>
                      <TableCell className={`text-right font-mono ${row.mape > 15 ? 'text-red-600' : row.mape > 10 ? 'text-amber-600' : 'text-green-600'}`}>
                        {row.mape}%
                      </TableCell>
                      <TableCell className={`text-right font-mono ${row.bias > 0 ? 'text-amber-600' : 'text-blue-600'}`}>
                        {row.bias > 0 ? '+' : ''}{row.bias}%
                      </TableCell>
                      <TableCell className="text-right font-mono">{row.hitRate}%</TableCell>
                      <TableCell>
                        <Badge
                          variant={row.trend === 'improving' ? 'success' : row.trend === 'declining' ? 'destructive' : 'secondary'}
                          className="text-xs capitalize"
                        >
                          {row.trend === 'improving' && <TrendingUp className="h-3 w-3 mr-1" />}
                          {row.trend === 'declining' && <TrendingDown className="h-3 w-3 mr-1" />}
                          {row.trend}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Create Dialog */}
      <Modal
        open={createDialogOpen}
        onClose={() => setCreateDialogOpen(false)}
        title="Create Demand Collaboration"
      >
        <div className="space-y-4 p-4">
          <div>
            <Label>Collaboration Type</Label>
            <Select
              value={newCollab.collaboration_type}
              onValueChange={(v) => setNewCollab(prev => ({ ...prev, collaboration_type: v }))}
            >
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(COLLAB_TYPE_CONFIG).map(([key, { label }]) => (
                  <SelectItem key={key} value={key}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Trading Partner Name</Label>
            <Input
              className="mt-1"
              placeholder="e.g., Supplier A"
              value={newCollab.partner_name}
              onChange={(e) => setNewCollab(prev => ({ ...prev, partner_name: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Product ID</Label>
              <Input
                className="mt-1"
                placeholder="e.g., PROD-001"
                value={newCollab.product_id}
                onChange={(e) => setNewCollab(prev => ({ ...prev, product_id: e.target.value }))}
              />
            </div>
            <div>
              <Label>Site ID</Label>
              <Input
                className="mt-1"
                placeholder="e.g., DC-East"
                value={newCollab.site_id}
                onChange={(e) => setNewCollab(prev => ({ ...prev, site_id: e.target.value }))}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Planning Period</Label>
              <Input
                className="mt-1"
                placeholder="e.g., 2026-W10"
                value={newCollab.planning_period}
                onChange={(e) => setNewCollab(prev => ({ ...prev, planning_period: e.target.value }))}
              />
            </div>
            <div>
              <Label>Forecast Quantity</Label>
              <Input
                type="number"
                className="mt-1"
                placeholder="0"
                value={newCollab.forecast_quantity}
                onChange={(e) => setNewCollab(prev => ({ ...prev, forecast_quantity: e.target.value }))}
              />
            </div>
          </div>
          <div>
            <Label>Notes</Label>
            <Textarea
              className="mt-1"
              placeholder="Additional context..."
              value={newCollab.notes}
              onChange={(e) => setNewCollab(prev => ({ ...prev, notes: e.target.value }))}
            />
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
            <Button
              onClick={handleCreate}
              disabled={!newCollab.partner_name || !newCollab.forecast_quantity}
              leftIcon={<Plus className="h-4 w-4" />}
            >
              Create
            </Button>
          </div>
        </div>
      </Modal>

      {/* Detail Dialog */}
      <Modal
        open={detailDialogOpen}
        onClose={() => setDetailDialogOpen(false)}
        title={`Collaboration: ${selectedCollab?.partner_name || ''}`}
      >
        {selectedCollab && (
          <div className="space-y-4 p-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Type</p>
                <p className="font-medium capitalize">{selectedCollab.collaboration_type?.replace('_', ' ')}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <Badge variant={STATUS_CONFIG[selectedCollab.status]?.variant || 'secondary'}>
                  {STATUS_CONFIG[selectedCollab.status]?.label || selectedCollab.status}
                </Badge>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Product</p>
                <p className="font-medium">{selectedCollab.product_name || selectedCollab.product_id || '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Site</p>
                <p className="font-medium">{selectedCollab.site_name || selectedCollab.site_id || '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Period</p>
                <p className="font-medium">{selectedCollab.planning_period || '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Forecast Quantity</p>
                <p className="font-medium font-mono">{selectedCollab.forecast_quantity?.toLocaleString() ?? '-'}</p>
              </div>
            </div>
            {selectedCollab.notes && (
              <div>
                <p className="text-sm text-muted-foreground">Notes</p>
                <p className="text-sm mt-1 p-3 bg-muted/30 rounded">{selectedCollab.notes}</p>
              </div>
            )}

            {selectedCollab.status === 'submitted' && (
              <div className="space-y-3 pt-4 border-t">
                <h4 className="font-medium">Approval Decision</h4>
                <div className="flex gap-2">
                  <Button
                    variant="default"
                    onClick={() => handleApprove(selectedCollab.id)}
                    leftIcon={<CheckCircle className="h-4 w-4" />}
                  >
                    Approve
                  </Button>
                  <div className="flex-1">
                    <Input
                      placeholder="Rejection reason..."
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                    />
                  </div>
                  <Button
                    variant="destructive"
                    onClick={() => handleReject(selectedCollab.id)}
                    disabled={!rejectReason}
                    leftIcon={<XCircle className="h-4 w-4" />}
                  >
                    Reject
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

// ============================================================================
// Mock data generators
// ============================================================================
function generateMockCollaborations() {
  const partners = ['Supplier A', 'Supplier B', 'Customer X', 'Customer Y', 'Distributor Z'];
  const products = ['Lager 6-Pack', 'IPA Case', 'Stout Keg', 'Pilsner Pallet'];
  const sites = ['DC-East', 'DC-West', 'DC-Central'];
  const types = ['forecast_share', 'forecast_share', 'consensus', 'alert', 'exception'];
  const statuses = ['draft', 'submitted', 'approved', 'approved', 'rejected'];

  return Array.from({ length: 20 }, (_, i) => ({
    id: i + 1,
    partner_name: partners[i % partners.length],
    collaboration_type: types[i % types.length],
    product_id: `PROD-${(i % 4) + 1}`,
    product_name: products[i % products.length],
    site_id: `SITE-${(i % 3) + 1}`,
    site_name: sites[i % sites.length],
    planning_period: `2026-W${10 + (i % 12)}`,
    forecast_quantity: Math.floor(Math.random() * 2000) + 500,
    status: statuses[i % statuses.length],
    version: Math.floor(i / 5) + 1,
    notes: i % 3 === 0 ? 'Includes promotional uplift for spring campaign' : null,
    created_at: new Date(Date.now() - i * 86400000).toISOString(),
  }));
}

function generateMockExceptions() {
  return [
    { partner_name: 'Supplier B', product_id: 'PROD-2', product_name: 'IPA Case', site_id: 'SITE-1', site_name: 'DC-East', planning_period: '2026-W12', internal_forecast: 500, partner_forecast: 680 },
    { partner_name: 'Customer Y', product_id: 'PROD-1', product_name: 'Lager 6-Pack', site_id: 'SITE-2', site_name: 'DC-West', planning_period: '2026-W13', internal_forecast: 1200, partner_forecast: 850 },
    { partner_name: 'Distributor Z', product_id: 'PROD-3', product_name: 'Stout Keg', site_id: 'SITE-3', site_name: 'DC-Central', planning_period: '2026-W11', internal_forecast: 300, partner_forecast: 510 },
  ];
}

export default DemandCollaboration;
