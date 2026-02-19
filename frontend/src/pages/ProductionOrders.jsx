/**
 * Production Orders Page
 *
 * Comprehensive production order management interface for:
 * - Viewing production orders with filtering
 * - Creating and managing production orders
 * - Lifecycle management (release, start, complete, close, cancel)
 * - Component tracking and BOM consumption
 */

import React, { useState, useEffect } from 'react';
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../components/common';
import {
  Plus,
  RefreshCw,
  Pencil,
  Trash2,
  Eye,
  Play,
  CheckCircle,
  XCircle,
  Lock,
  Upload,
  AlertTriangle,
  TrendingUp,
  Factory,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useCapabilities } from '../hooks/useCapabilities';
import { api } from '../services/api';
import { getSupplyChainConfigs } from '../services/supplyChainConfigService';

const ProductionOrders = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { hasCapability } = useCapabilities();

  // State
  const [tabValue, setTabValue] = useState('all');
  const [orders, setOrders] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // Filters
  const [statusFilter, setStatusFilter] = useState('');
  const [itemFilter, setItemFilter] = useState('');
  const [siteFilter, setSiteFilter] = useState('');
  const [overdueOnly, setOverdueOnly] = useState(false);

  // Dialogs
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [actionDialogOpen, setActionDialogOpen] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [actionType, setActionType] = useState('');

  // Master data
  const [items, setItems] = useState([]);
  const [sites, setSites] = useState([]);
  const [mpsPlans, setMpsPlans] = useState([]);
  const [configs, setConfigs] = useState([]);

  // Form state for create/update
  const [formData, setFormData] = useState({
    product_id: '',
    site_id: '',
    config_id: '',
    mps_plan_id: '',
    planned_quantity: '',
    planned_start_date: '',
    planned_completion_date: '',
    priority: 5,
    notes: '',
  });

  // Permissions
  const canView = hasCapability('view_production_orders');
  const canManage = hasCapability('manage_production_orders');
  const canRelease = hasCapability('release_production_orders');

  // Load data
  useEffect(() => {
    if (canView) {
      loadOrders();
      loadSummary();
      loadMasterData();
    }
  }, [page, statusFilter, itemFilter, siteFilter, overdueOnly]);

  const loadOrders = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: '20',
      });

      if (statusFilter) params.append('status', statusFilter);
      if (itemFilter) params.append('product_id', itemFilter);
      if (siteFilter) params.append('site_id', siteFilter);
      if (overdueOnly) params.append('overdue_only', 'true');

      const response = await api.get(`/production-orders?${params.toString()}`);
      setOrders(response.data.items || []);
      setTotalPages(response.data.pages || 1);
      setError(null);
    } catch (err) {
      console.error('Error loading production orders:', err);
      setError('Failed to load production orders. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const loadSummary = async () => {
    try {
      const response = await api.get('/production-orders/summary');
      setSummary(response.data);
    } catch (err) {
      console.error('Error loading summary:', err);
    }
  };

  const loadMasterData = async () => {
    try {
      const [itemsRes, sitesRes, mpsRes, configs] = await Promise.all([
        api.get('/items'),
        api.get('/sites'),
        api.get('/mps/plans'),
        getSupplyChainConfigs(),
      ]);

      setItems(itemsRes.data || []);
      setSites(sitesRes.data || []);
      setMpsPlans(mpsRes.data || []);
      setConfigs(configs || []);
    } catch (err) {
      console.error('Error loading master data:', err);
    }
  };

  const handleCreateOrder = async () => {
    try {
      await api.post('/production-orders', {
        ...formData,
        planned_quantity: parseInt(formData.planned_quantity),
        product_id: parseInt(formData.product_id),
        site_id: parseInt(formData.site_id),
        config_id: parseInt(formData.config_id),
        mps_plan_id: formData.mps_plan_id ? parseInt(formData.mps_plan_id) : null,
      });

      setCreateDialogOpen(false);
      resetFormData();
      loadOrders();
      loadSummary();
    } catch (err) {
      console.error('Error creating production order:', err);
      alert('Failed to create production order. Please try again.');
    }
  };

  const handleOrderAction = async (order, action) => {
    setSelectedOrder(order);
    setActionType(action);
    setActionDialogOpen(true);
  };

  const executeAction = async () => {
    try {
      let endpoint = '';
      let payload = {};

      switch (actionType) {
        case 'release':
          endpoint = `/production-orders/${selectedOrder.id}/release`;
          break;
        case 'start':
          endpoint = `/production-orders/${selectedOrder.id}/start`;
          payload = { actual_start_date: new Date().toISOString() };
          break;
        case 'complete':
          endpoint = `/production-orders/${selectedOrder.id}/complete`;
          payload = {
            actual_quantity: selectedOrder.planned_quantity,
            scrap_quantity: 0,
          };
          break;
        case 'close':
          endpoint = `/production-orders/${selectedOrder.id}/close`;
          break;
        case 'cancel':
          endpoint = `/production-orders/${selectedOrder.id}/cancel`;
          payload = { reason: 'User cancelled' };
          break;
        default:
          throw new Error('Unknown action type');
      }

      await api.post(endpoint, payload);
      setActionDialogOpen(false);
      loadOrders();
      loadSummary();
    } catch (err) {
      console.error(`Error executing ${actionType}:`, err);
      alert(`Failed to ${actionType} production order. Please try again.`);
    }
  };

  const resetFormData = () => {
    setFormData({
      product_id: '',
      site_id: '',
      config_id: '',
      mps_plan_id: '',
      planned_quantity: '',
      planned_start_date: '',
      planned_completion_date: '',
      priority: 5,
      notes: '',
    });
  };

  const getStatusVariant = (status) => {
    const variants = {
      PLANNED: 'secondary',
      RELEASED: 'info',
      IN_PROGRESS: 'warning',
      COMPLETED: 'success',
      CLOSED: 'secondary',
      CANCELLED: 'destructive',
    };
    return variants[status] || 'secondary';
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString();
  };

  const isOverdue = (order) => {
    if (!['RELEASED', 'IN_PROGRESS'].includes(order.status)) return false;
    return new Date(order.planned_completion_date) < new Date();
  };

  if (!canView) {
    return (
      <div className="container mx-auto py-8 px-4 max-w-7xl">
        <Alert variant="destructive">
          <AlertTitle>Access Denied</AlertTitle>
          <AlertDescription>
            You do not have permission to view production orders.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-3">
            <Factory className="h-10 w-10 text-primary" />
            <h1 className="text-3xl font-bold">Production Orders</h1>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => { loadOrders(); loadSummary(); }}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
            {canManage && (
              <Button onClick={() => setCreateDialogOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Create Order
              </Button>
            )}
          </div>
        </div>
        <p className="text-muted-foreground">
          Manage production order lifecycle: release, start, complete, and close orders
        </p>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground mb-1">Total Orders</p>
              <p className="text-4xl font-bold">{summary.total_orders}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground mb-1">In Progress</p>
              <p className="text-4xl font-bold text-blue-500">{summary.in_progress_count}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground mb-1">Overdue</p>
              <p className="text-4xl font-bold text-destructive">{summary.overdue_count}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground mb-1">Avg Yield</p>
              <p className="text-4xl font-bold text-green-600">
                {summary.average_yield_percentage.toFixed(1)}%
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Tabs */}
      <Tabs value={tabValue} onValueChange={setTabValue} className="mb-6">
        <TabsList>
          <TabsTrigger value="all">All Orders</TabsTrigger>
          <TabsTrigger value="active">Active</TabsTrigger>
          <TabsTrigger value="completed">Completed</TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <h3 className="text-lg font-semibold mb-4">Filters</h3>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <Label htmlFor="status-filter">Status</Label>
              <select
                id="status-filter"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="">All</option>
                <option value="PLANNED">Planned</option>
                <option value="RELEASED">Released</option>
                <option value="IN_PROGRESS">In Progress</option>
                <option value="COMPLETED">Completed</option>
                <option value="CLOSED">Closed</option>
                <option value="CANCELLED">Cancelled</option>
              </select>
            </div>
            <div>
              <Label htmlFor="item-filter">Item</Label>
              <select
                id="item-filter"
                value={itemFilter}
                onChange={(e) => setItemFilter(e.target.value)}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="">All</option>
                {items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="site-filter">Site</Label>
              <select
                id="site-filter"
                value={siteFilter}
                onChange={(e) => setSiteFilter(e.target.value)}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="">All</option>
                {sites.map((site) => (
                  <option key={site.id} value={site.id}>
                    {site.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-end">
              <Button
                variant={overdueOnly ? 'default' : 'outline'}
                className={`w-full h-10 ${overdueOnly ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90' : ''}`}
                onClick={() => setOverdueOnly(!overdueOnly)}
              >
                {overdueOnly ? 'Show All' : 'Overdue Only'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Orders Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex justify-center py-8">
              <Spinner size="lg" />
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Order #</TableHead>
                    <TableHead>Item</TableHead>
                    <TableHead>Site</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Planned Qty</TableHead>
                    <TableHead className="text-right">Actual Qty</TableHead>
                    <TableHead>Start Date</TableHead>
                    <TableHead>Due Date</TableHead>
                    <TableHead>Priority</TableHead>
                    <TableHead className="text-center">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {orders.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={10} className="text-center py-8">
                        <p className="text-muted-foreground">No production orders found</p>
                      </TableCell>
                    </TableRow>
                  ) : (
                    orders.map((order) => (
                      <TableRow
                        key={order.id}
                        className={isOverdue(order) ? 'bg-destructive/10' : ''}
                      >
                        <TableCell>
                          <div className="flex items-center gap-2">
                            {order.order_number}
                            {isOverdue(order) && (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger>
                                    <AlertTriangle className="h-4 w-4 text-destructive" />
                                  </TooltipTrigger>
                                  <TooltipContent>Overdue</TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>{order.item?.name || 'N/A'}</TableCell>
                        <TableCell>{order.site?.name || 'N/A'}</TableCell>
                        <TableCell>
                          <Badge variant={getStatusVariant(order.status)}>
                            {order.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">{order.planned_quantity}</TableCell>
                        <TableCell className="text-right">
                          {order.actual_quantity || '-'}
                        </TableCell>
                        <TableCell>{formatDate(order.planned_start_date)}</TableCell>
                        <TableCell>{formatDate(order.planned_completion_date)}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{order.priority}</Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex justify-center gap-1">
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => {
                                      setSelectedOrder(order);
                                      setDetailDialogOpen(true);
                                    }}
                                  >
                                    <Eye className="h-4 w-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>View Details</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>

                            {order.status === 'PLANNED' && canRelease && (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      onClick={() => handleOrderAction(order, 'release')}
                                    >
                                      <Upload className="h-4 w-4 text-primary" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>Release</TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            )}

                            {order.status === 'RELEASED' && canManage && (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      onClick={() => handleOrderAction(order, 'start')}
                                    >
                                      <Play className="h-4 w-4 text-blue-500" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>Start Production</TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            )}

                            {order.status === 'IN_PROGRESS' && canManage && (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      onClick={() => handleOrderAction(order, 'complete')}
                                    >
                                      <CheckCircle className="h-4 w-4 text-green-600" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>Complete</TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            )}

                            {order.status === 'COMPLETED' && canManage && (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      onClick={() => handleOrderAction(order, 'close')}
                                    >
                                      <Lock className="h-4 w-4" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>Close</TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            )}

                            {!['COMPLETED', 'CLOSED', 'CANCELLED'].includes(order.status) && canManage && (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      onClick={() => handleOrderAction(order, 'cancel')}
                                    >
                                      <XCircle className="h-4 w-4 text-destructive" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>Cancel</TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex justify-center items-center gap-2 p-4 border-t">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(page - 1)}
                    disabled={page === 1}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Previous
                  </Button>
                  <span className="text-sm text-muted-foreground">
                    Page {page} of {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(page + 1)}
                    disabled={page >= totalPages}
                  >
                    Next
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Create Order Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Create Production Order</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 mt-4">
            <div>
              <Label htmlFor="product">Product *</Label>
              <select
                id="product"
                value={formData.product_id}
                onChange={(e) => setFormData({ ...formData, product_id: e.target.value })}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="">Select product</option>
                {items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="site">Site *</Label>
              <select
                id="site"
                value={formData.site_id}
                onChange={(e) => setFormData({ ...formData, site_id: e.target.value })}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="">Select site</option>
                {sites.map((site) => (
                  <option key={site.id} value={site.id}>
                    {site.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="config">Config *</Label>
              <select
                id="config"
                value={formData.config_id}
                onChange={(e) => setFormData({ ...formData, config_id: e.target.value })}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="">Select config</option>
                {configs.map((config) => (
                  <option key={config.id} value={config.id}>
                    {config.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="mps-plan">MPS Plan (Optional)</Label>
              <select
                id="mps-plan"
                value={formData.mps_plan_id}
                onChange={(e) => setFormData({ ...formData, mps_plan_id: e.target.value })}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="">None</option>
                {mpsPlans.map((plan) => (
                  <option key={plan.id} value={plan.id}>
                    {plan.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="quantity">Planned Quantity *</Label>
              <Input
                id="quantity"
                type="number"
                value={formData.planned_quantity}
                onChange={(e) => setFormData({ ...formData, planned_quantity: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="priority">Priority</Label>
              <Input
                id="priority"
                type="number"
                min={1}
                max={10}
                value={formData.priority}
                onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) })}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="start-date">Start Date *</Label>
              <Input
                id="start-date"
                type="date"
                value={formData.planned_start_date}
                onChange={(e) => setFormData({ ...formData, planned_start_date: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="completion-date">Completion Date *</Label>
              <Input
                id="completion-date"
                type="date"
                value={formData.planned_completion_date}
                onChange={(e) => setFormData({ ...formData, planned_completion_date: e.target.value })}
                className="mt-1"
              />
            </div>
            <div className="col-span-2">
              <Label htmlFor="notes">Notes</Label>
              <Textarea
                id="notes"
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                rows={3}
                className="mt-1"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreateOrder}
              disabled={
                !formData.product_id ||
                !formData.site_id ||
                !formData.config_id ||
                !formData.planned_quantity ||
                !formData.planned_start_date ||
                !formData.planned_completion_date
              }
            >
              Create Order
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Action Confirmation Dialog */}
      <Dialog open={actionDialogOpen} onOpenChange={setActionDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm {actionType}</DialogTitle>
          </DialogHeader>
          <p>
            Are you sure you want to {actionType} production order {selectedOrder?.order_number}?
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setActionDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={executeAction}>
              Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={detailDialogOpen} onOpenChange={setDetailDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Production Order Details</DialogTitle>
          </DialogHeader>
          {selectedOrder && (
            <div className="space-y-4 mt-4">
              <div>
                <h3 className="text-lg font-semibold">{selectedOrder.order_number}</h3>
                <hr className="my-2" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <Badge variant={getStatusVariant(selectedOrder.status)} className="mt-1">
                    {selectedOrder.status}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Priority</p>
                  <p className="font-medium">{selectedOrder.priority}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Item</p>
                  <p className="font-medium">{selectedOrder.item?.name || 'N/A'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Site</p>
                  <p className="font-medium">{selectedOrder.site?.name || 'N/A'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Planned Quantity</p>
                  <p className="font-medium">{selectedOrder.planned_quantity}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Actual Quantity</p>
                  <p className="font-medium">{selectedOrder.actual_quantity || 'N/A'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Planned Start</p>
                  <p className="font-medium">{formatDate(selectedOrder.planned_start_date)}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Planned Completion</p>
                  <p className="font-medium">{formatDate(selectedOrder.planned_completion_date)}</p>
                </div>
                {selectedOrder.yield_percentage && (
                  <div className="col-span-2">
                    <p className="text-sm text-muted-foreground">Yield %</p>
                    <p className="font-medium">{selectedOrder.yield_percentage.toFixed(1)}%</p>
                  </div>
                )}
                {selectedOrder.notes && (
                  <div className="col-span-2">
                    <p className="text-sm text-muted-foreground">Notes</p>
                    <p className="font-medium">{selectedOrder.notes}</p>
                  </div>
                )}
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDetailDialogOpen(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ProductionOrders;
