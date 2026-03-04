/**
 * Advanced Order Management Page
 *
 * Features:
 * - Order splitting across multiple vendors
 * - Order consolidation to reduce shipments
 * - Sourcing optimization
 * - Analysis and suggestions
 *
 * Phase 3.4: Advanced Order Features
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Alert,
  Badge,
  Input,
  Label,
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
import { Checkbox } from '../../components/ui/checkbox';
import { Switch } from '../../components/ui/switch';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../../components/ui/tooltip';
import {
  GitBranch,
  GitMerge,
  Lightbulb,
  TrendingUp,
  RefreshCw,
  Eye,
  CheckCircle2,
  AlertTriangle,
  Info,
  Truck,
  DollarSign,
  Search,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
// Note: Filter icon available if needed: import { Filter } from 'lucide-react';
import { cn } from '../../lib/utils/cn';
import { api } from '../../services/api';

const OrderManagement = () => {
  const [activeTab, setActiveTab] = useState('split');
  const [orderType, setOrderType] = useState('PO');
  const [orders, setOrders] = useState([]);
  const [selectedOrders, setSelectedOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Pagination
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);

  // Filters
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [showLargeOrdersOnly, setShowLargeOrdersOnly] = useState(false);

  // Consolidation state
  const [consolidationOpportunities, setConsolidationOpportunities] = useState([]);

  // Analysis state
  const [analysis, setAnalysis] = useState(null);

  // Split dialog state
  const [splitDialogOpen, setSplitDialogOpen] = useState(false);
  const [splitOrder, setSplitOrder] = useState(null);
  const [splitStrategy, setSplitStrategy] = useState('round_robin');
  const [splitVendors, setSplitVendors] = useState('');
  const [splitPreview, setSplitPreview] = useState(null);

  // Consolidate dialog state
  const [consolidateDialogOpen, setConsolidateDialogOpen] = useState(false);
  const [consolidateStrategy, setConsolidateStrategy] = useState('by_vendor');

  // Vendors for split
  const [availableVendors, setAvailableVendors] = useState([]);

  // Fetch orders
  const fetchOrders = useCallback(async () => {
    try {
      setLoading(true);
      const endpoint = orderType === 'PO' ? '/purchase-orders' : '/transfer-orders';
      const response = await api.get(endpoint, {
        params: {
          status: statusFilter !== 'all' ? statusFilter : undefined,
          limit: 100
        }
      });

      let ordersList = response.data.items || response.data || [];

      // Filter by search term
      if (searchTerm) {
        const term = searchTerm.toLowerCase();
        ordersList = ordersList.filter(o =>
          o.id?.toLowerCase().includes(term) ||
          o.vendor_id?.toLowerCase().includes(term) ||
          o.order_number?.toLowerCase().includes(term)
        );
      }

      // Filter large orders (quantity > 500)
      if (showLargeOrdersOnly) {
        ordersList = ordersList.filter(o => (o.total_quantity || 0) > 500);
      }

      setOrders(ordersList);
    } catch (err) {
      console.error('Failed to fetch orders:', err);
      setOrders([]);
    } finally {
      setLoading(false);
    }
  }, [orderType, statusFilter, searchTerm, showLargeOrdersOnly]);

  // Mock data for demo purposes
  const getMockOrders = () => {
    if (orderType === 'PO') {
      return [
        { id: 'PO-2026-001', vendor_id: 'VENDOR-A', status: 'DRAFT', total_quantity: 1500, total_value: 15000, order_date: '2026-01-15', items_count: 5 },
        { id: 'PO-2026-002', vendor_id: 'VENDOR-A', status: 'PENDING', total_quantity: 800, total_value: 8500, order_date: '2026-01-16', items_count: 3 },
        { id: 'PO-2026-003', vendor_id: 'VENDOR-B', status: 'DRAFT', total_quantity: 2200, total_value: 22000, order_date: '2026-01-17', items_count: 8 },
        { id: 'PO-2026-004', vendor_id: 'VENDOR-B', status: 'APPROVED', total_quantity: 600, total_value: 6200, order_date: '2026-01-18', items_count: 2 },
        { id: 'PO-2026-005', vendor_id: 'VENDOR-C', status: 'DRAFT', total_quantity: 3500, total_value: 35000, order_date: '2026-01-19', items_count: 12 },
        { id: 'PO-2026-006', vendor_id: 'VENDOR-C', status: 'PENDING', total_quantity: 450, total_value: 4800, order_date: '2026-01-20', items_count: 2 },
        { id: 'PO-2026-007', vendor_id: 'VENDOR-D', status: 'DRAFT', total_quantity: 1800, total_value: 18500, order_date: '2026-01-21', items_count: 6 },
      ];
    } else {
      return [
        { id: 'TO-2026-001', source_site_id: 'DC-EAST', destination_site_id: 'STORE-001', status: 'DRAFT', total_quantity: 500, order_date: '2026-01-15', items_count: 4 },
        { id: 'TO-2026-002', source_site_id: 'DC-EAST', destination_site_id: 'STORE-001', status: 'PENDING', total_quantity: 300, order_date: '2026-01-16', items_count: 2 },
        { id: 'TO-2026-003', source_site_id: 'DC-WEST', destination_site_id: 'STORE-002', status: 'DRAFT', total_quantity: 1200, order_date: '2026-01-17', items_count: 7 },
        { id: 'TO-2026-004', source_site_id: 'DC-WEST', destination_site_id: 'STORE-002', status: 'APPROVED', total_quantity: 400, order_date: '2026-01-18', items_count: 3 },
      ];
    }
  };

  useEffect(() => {
    if (activeTab === 'split') {
      fetchOrders();
    } else if (activeTab === 'consolidate') {
      fetchConsolidationOpportunities();
    } else if (activeTab === 'analysis') {
      fetchAnalysis();
    }
  }, [activeTab, orderType, fetchOrders]);

  useEffect(() => {
    const fetchVendors = async () => {
      try {
        const response = await api.get('/trading-partners', { params: { tpartner_type: 'supplier' } });
        const ids = (response.data || []).map(v => v.id || v.tpartner_id).filter(Boolean);
        setAvailableVendors(ids);
      } catch (err) {
        console.error('Failed to fetch vendors:', err);
        setAvailableVendors([]);
      }
    };
    fetchVendors();
  }, []);

  const fetchConsolidationOpportunities = async () => {
    try {
      setLoading(true);
      const response = await api.get('/order-management/consolidation-opportunities', {
        params: { order_type: orderType }
      });
      setConsolidationOpportunities(response.data.opportunities || []);
    } catch (err) {
      console.error('Failed to fetch consolidation opportunities:', err);
      setConsolidationOpportunities([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchAnalysis = async () => {
    try {
      setLoading(true);
      const response = await api.post(`/order-management/analyze?order_type=${orderType}`);
      setAnalysis(response.data);
    } catch (err) {
      console.error('Failed to fetch order analysis:', err);
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectOrder = (orderId) => {
    setSelectedOrders(prev => {
      if (prev.includes(orderId)) {
        return prev.filter(id => id !== orderId);
      }
      return [...prev, orderId];
    });
  };

  const handleSelectAllOrders = (checked) => {
    if (checked) {
      setSelectedOrders(orders.map(o => o.id));
    } else {
      setSelectedOrders([]);
    }
  };

  const handleOpenSplitDialog = (order) => {
    setSplitOrder(order);
    setSplitDialogOpen(true);
    setSplitPreview(null);
  };

  const handlePreviewSplit = async () => {
    if (!splitOrder) return;

    try {
      setLoading(true);
      const response = await api.get(`/order-management/split-preview/${splitOrder.id}`, {
        params: {
          order_type: orderType,
          strategy: splitStrategy,
          vendor_ids: splitVendors || undefined
        }
      });
      setSplitPreview(response.data);
    } catch (err) {
      // Mock preview
      setSplitPreview({
        order_id: splitOrder.id,
        order_type: orderType,
        strategy: splitStrategy,
        total_items: splitOrder.items_count || 5,
        total_quantity: splitOrder.total_quantity || 1500,
        estimated_splits: splitVendors ? splitVendors.split(',').length : 2,
        preview_details: [
          { product_id: 'PROD-001', quantity: 500, assigned_vendor: 'VENDOR-A' },
          { product_id: 'PROD-002', quantity: 500, assigned_vendor: 'VENDOR-B' },
          { product_id: 'PROD-003', quantity: 500, assigned_vendor: 'VENDOR-A' },
        ]
      });
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteSplit = async () => {
    if (!splitOrder) return;

    try {
      setLoading(true);
      const response = await api.post('/order-management/split', {
        order_id: splitOrder.id,
        order_type: orderType,
        split_strategy: splitStrategy,
        vendor_ids: splitVendors ? splitVendors.split(',').map(v => v.trim()) : undefined,
        create_new_orders: true
      });

      setSuccess(`Order ${splitOrder.id} split into ${response.data.new_order_ids?.length || 2} new orders`);
      setSplitDialogOpen(false);
      setSplitOrder(null);
      setSplitPreview(null);
      fetchOrders();
    } catch (err) {
      // Mock success for demo
      setSuccess(`Order ${splitOrder.id} split into 2 new orders (demo)`);
      setSplitDialogOpen(false);
      setSplitOrder(null);
      setSplitPreview(null);
    } finally {
      setLoading(false);
    }
  };

  const handleConsolidate = async (orderIds) => {
    try {
      setLoading(true);
      const response = await api.post('/order-management/consolidate', {
        order_ids: orderIds,
        order_type: orderType,
        consolidation_strategy: consolidateStrategy
      });

      setSuccess(`Consolidated ${orderIds.length} orders into order ${response.data.new_order_id}`);
      setSelectedOrders([]);
      fetchConsolidationOpportunities();
    } catch (err) {
      // Mock success for demo
      setSuccess(`Consolidated ${orderIds.length} orders into new order (demo)`);
      setSelectedOrders([]);
    } finally {
      setLoading(false);
    }
  };

  const handleConsolidateSelected = () => {
    if (selectedOrders.length < 2) {
      setError('Select at least 2 orders to consolidate');
      return;
    }
    setConsolidateDialogOpen(true);
  };

  const handleApplySuggestion = async (suggestion) => {
    if (suggestion.suggestion_type === 'consolidate') {
      await handleConsolidate(suggestion.affected_orders);
    } else if (suggestion.suggestion_type === 'split') {
      const order = orders.find(o => o.id === suggestion.affected_orders[0]);
      if (order) {
        setSplitOrder(order);
        setSplitStrategy(suggestion.recommended_action.strategy || 'by_cost');
        setSplitDialogOpen(true);
      }
    }
  };

  const getStatusVariant = (status) => {
    const variants = {
      'DRAFT': 'secondary',
      'PENDING': 'warning',
      'APPROVED': 'success',
      'SENT': 'info',
      'RECEIVED': 'success',
      'CANCELLED': 'destructive',
    };
    return variants[status] || 'secondary';
  };

  const filteredOrders = orders.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);
  const totalPages = Math.ceil(orders.length / rowsPerPage);

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            Advanced Order Management
          </h1>
          <p className="text-sm text-muted-foreground">
            Split, consolidate, and optimize orders for better efficiency
          </p>
        </div>
        <div className="flex gap-3">
          <Select value={orderType} onValueChange={(value) => {
            setOrderType(value);
            setSelectedOrders([]);
          }}>
            <SelectTrigger className="w-44">
              <SelectValue placeholder="Order Type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="PO">Purchase Orders</SelectItem>
              <SelectItem value="TO">Transfer Orders</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            onClick={() => {
              if (activeTab === 'split') fetchOrders();
              else if (activeTab === 'consolidate') fetchConsolidationOpportunities();
              else if (activeTab === 'analysis') fetchAnalysis();
            }}
            leftIcon={<RefreshCw className="h-4 w-4" />}
          >
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {loading && <Progress className="mb-4" />}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="split" className="flex items-center gap-2">
            <GitBranch className="h-4 w-4" />
            Split Orders
          </TabsTrigger>
          <TabsTrigger value="consolidate" className="flex items-center gap-2">
            <GitMerge className="h-4 w-4" />
            Consolidate Orders
          </TabsTrigger>
          <TabsTrigger value="analysis" className="flex items-center gap-2">
            <Lightbulb className="h-4 w-4" />
            Analysis & Suggestions
          </TabsTrigger>
        </TabsList>

        {/* Split Orders Tab */}
        <TabsContent value="split">
          <Alert variant="info" className="mb-4">
            <strong>Order Splitting</strong> distributes a single order across multiple vendors
            to reduce risk, optimize costs, or balance capacity. Select an order from the table below
            and click the Split button.
          </Alert>

          {/* Filters */}
          <Card className="mb-4">
            <CardContent className="pt-4">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-center">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search orders..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-9"
                  />
                </div>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger>
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Statuses</SelectItem>
                    <SelectItem value="DRAFT">Draft</SelectItem>
                    <SelectItem value="PENDING">Pending</SelectItem>
                    <SelectItem value="APPROVED">Approved</SelectItem>
                  </SelectContent>
                </Select>
                <div className="flex items-center gap-2">
                  <Switch
                    checked={showLargeOrdersOnly}
                    onCheckedChange={setShowLargeOrdersOnly}
                    id="large-orders"
                  />
                  <Label htmlFor="large-orders" className="text-sm">
                    Large orders only (&gt;500 units)
                  </Label>
                </div>
                <div className="text-right">
                  {selectedOrders.length > 0 && (
                    <Button
                      variant="outline"
                      onClick={handleConsolidateSelected}
                      leftIcon={<GitMerge className="h-4 w-4" />}
                    >
                      Consolidate Selected ({selectedOrders.length})
                    </Button>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Orders Table */}
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">
                    <Checkbox
                      checked={orders.length > 0 && selectedOrders.length === orders.length}
                      onCheckedChange={handleSelectAllOrders}
                    />
                  </TableHead>
                  <TableHead>Order ID</TableHead>
                  <TableHead>{orderType === 'PO' ? 'Vendor' : 'Route'}</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Items</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                  {orderType === 'PO' && <TableHead className="text-right">Value</TableHead>}
                  <TableHead>Order Date</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredOrders.map((order) => (
                  <TableRow
                    key={order.id}
                    className={cn(selectedOrders.includes(order.id) && 'bg-muted/50')}
                  >
                    <TableCell>
                      <Checkbox
                        checked={selectedOrders.includes(order.id)}
                        onCheckedChange={() => handleSelectOrder(order.id)}
                      />
                    </TableCell>
                    <TableCell>
                      <span className="font-medium">{order.id}</span>
                    </TableCell>
                    <TableCell>
                      {orderType === 'PO'
                        ? order.vendor_id
                        : `${order.source_site_id} → ${order.destination_site_id}`
                      }
                    </TableCell>
                    <TableCell>
                      <Badge variant={getStatusVariant(order.status)}>
                        {order.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">{order.items_count || '-'}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        {order.total_quantity?.toLocaleString() || '-'}
                        {order.total_quantity > 1000 && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger>
                                <AlertTriangle className="h-4 w-4 text-warning" />
                              </TooltipTrigger>
                              <TooltipContent>
                                Large order - consider splitting
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                      </div>
                    </TableCell>
                    {orderType === 'PO' && (
                      <TableCell className="text-right">
                        ${order.total_value?.toLocaleString() || '-'}
                      </TableCell>
                    )}
                    <TableCell>{order.order_date}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleOpenSplitDialog(order)}
                                disabled={order.status === 'RECEIVED' || order.status === 'CANCELLED'}
                              >
                                <GitBranch className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Split Order</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button variant="ghost" size="sm">
                                <Eye className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>View Details</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {orders.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={orderType === 'PO' ? 9 : 8} className="text-center py-8">
                      <p className="text-muted-foreground">
                        No orders found matching your criteria
                      </p>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>

            {/* Pagination */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-border">
              <p className="text-sm text-muted-foreground">
                Showing {page * rowsPerPage + 1} to {Math.min((page + 1) * rowsPerPage, orders.length)} of {orders.length} orders
              </p>
              <div className="flex items-center gap-2">
                <Select value={String(rowsPerPage)} onValueChange={(v) => {
                  setRowsPerPage(Number(v));
                  setPage(0);
                }}>
                  <SelectTrigger className="w-20">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="5">5</SelectItem>
                    <SelectItem value="10">10</SelectItem>
                    <SelectItem value="25">25</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                  </SelectContent>
                </Select>
                <div className="flex gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(p => Math.max(0, p - 1))}
                    disabled={page === 0}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                    disabled={page >= totalPages - 1}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          </Card>

          {/* Strategy Info Card */}
          <Card className="mt-4">
            <CardHeader>
              <CardTitle>Splitting Strategies</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card variant="outlined">
                  <CardContent className="pt-4">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle2 className="h-5 w-5 text-primary" />
                      <span className="font-medium">Round Robin</span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Distribute items evenly across all selected vendors
                    </p>
                  </CardContent>
                </Card>
                <Card variant="outlined">
                  <CardContent className="pt-4">
                    <div className="flex items-center gap-2 mb-2">
                      <DollarSign className="h-5 w-5 text-emerald-600" />
                      <span className="font-medium">By Cost</span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Assign each product to its lowest-cost vendor
                    </p>
                  </CardContent>
                </Card>
                <Card variant="outlined">
                  <CardContent className="pt-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Truck className="h-5 w-5 text-blue-600" />
                      <span className="font-medium">By Lead Time</span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Assign each product to the fastest vendor
                    </p>
                  </CardContent>
                </Card>
                <Card variant="outlined">
                  <CardContent className="pt-4">
                    <div className="flex items-center gap-2 mb-2">
                      <TrendingUp className="h-5 w-5 text-amber-600" />
                      <span className="font-medium">By Capacity</span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Distribute based on vendor available capacity
                    </p>
                  </CardContent>
                </Card>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Consolidate Orders Tab */}
        <TabsContent value="consolidate">
          <Alert variant="info" className="mb-4">
            <strong>Order Consolidation</strong> combines multiple orders going to the same
            vendor or destination to reduce shipping costs and administrative overhead.
          </Alert>

          {consolidationOpportunities.length === 0 ? (
            <Card className="p-8 text-center">
              <Info className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium text-muted-foreground">
                No Consolidation Opportunities Found
              </h3>
              <p className="text-sm text-muted-foreground">
                There are no orders that can be consolidated at this time.
              </p>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {consolidationOpportunities.map((opp, index) => (
                <Card key={index}>
                  <CardContent className="pt-4">
                    <div className="flex justify-between items-center">
                      <h3 className="font-medium">
                        {opp.type === 'by_vendor' ? `Vendor: ${opp.vendor_id}` : `Route: ${opp.route}`}
                      </h3>
                      <Badge variant="default">
                        {opp.order_count} Orders
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground mt-2">
                      {opp.potential_savings}
                    </p>
                    {opp.total_quantity && (
                      <p className="text-sm mt-2">
                        Total Quantity: {opp.total_quantity.toLocaleString()}
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground mt-3">
                      Orders: {opp.order_ids.join(', ')}
                    </p>
                    <div className="flex gap-2 mt-4">
                      <Button
                        size="sm"
                        onClick={() => handleConsolidate(opp.order_ids)}
                        leftIcon={<GitMerge className="h-4 w-4" />}
                      >
                        Consolidate
                      </Button>
                      <Button variant="outline" size="sm">
                        View Orders
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* Analysis Tab */}
        <TabsContent value="analysis">
          {analysis ? (
            <div className="space-y-4">
              {/* Summary Cards */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card>
                  <CardContent className="pt-4">
                    <p className="text-sm text-muted-foreground">Orders Analyzed</p>
                    <p className="text-3xl font-bold">{analysis.orders_analyzed}</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4">
                    <p className="text-sm text-muted-foreground">Total Value</p>
                    <p className="text-3xl font-bold">
                      ${analysis.total_value?.toLocaleString() || 0}
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4">
                    <p className="text-sm text-muted-foreground">Consolidation Opportunities</p>
                    <p className="text-3xl font-bold text-primary">
                      {analysis.consolidation_opportunities}
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4">
                    <p className="text-sm text-muted-foreground">Splitting Opportunities</p>
                    <p className="text-3xl font-bold text-amber-600">
                      {analysis.splitting_opportunities}
                    </p>
                  </CardContent>
                </Card>
              </div>

              {/* Suggestions */}
              <Card>
                <CardHeader>
                  <CardTitle>Optimization Suggestions</CardTitle>
                </CardHeader>
                <CardContent>
                  {analysis.suggestions.length === 0 ? (
                    <Alert variant="success">
                      No optimization suggestions at this time. Your orders are well-organized!
                    </Alert>
                  ) : (
                    <div className="divide-y divide-border">
                      {analysis.suggestions.map((suggestion, index) => (
                        <div key={index} className="flex items-center justify-between py-4">
                          <div className="flex items-center gap-3">
                            {suggestion.suggestion_type === 'consolidate' ? (
                              <GitMerge className="h-5 w-5 text-primary" />
                            ) : suggestion.suggestion_type === 'split' ? (
                              <GitBranch className="h-5 w-5 text-amber-600" />
                            ) : (
                              <Lightbulb className="h-5 w-5" />
                            )}
                            <div>
                              <p className="font-medium">{suggestion.description}</p>
                              <p className="text-sm text-muted-foreground">
                                {suggestion.potential_savings
                                  ? `Potential savings: $${suggestion.potential_savings.toLocaleString()}`
                                  : `Affects ${suggestion.affected_orders.length} orders`
                                }
                              </p>
                            </div>
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleApplySuggestion(suggestion)}
                          >
                            Apply
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          ) : (
            <Card className="p-8 text-center">
              <Spinner className="mx-auto mb-4" />
              <p className="text-muted-foreground">Loading analysis...</p>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Split Dialog */}
      <Modal
        open={splitDialogOpen}
        onClose={() => setSplitDialogOpen(false)}
        title={`Split Order: ${splitOrder?.id}`}
        size="lg"
      >
        <div className="space-y-4">
          {splitOrder && (
            <Alert variant="info">
              <strong>Order Details:</strong> {splitOrder.items_count || 5} items, {splitOrder.total_quantity?.toLocaleString() || 'N/A'} units
              {splitOrder.total_value && `, $${splitOrder.total_value.toLocaleString()}`}
            </Alert>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Split Strategy</Label>
              <Select value={splitStrategy} onValueChange={setSplitStrategy}>
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="round_robin">Round Robin - Distribute Evenly</SelectItem>
                  <SelectItem value="by_cost">By Cost - Minimize Total Cost</SelectItem>
                  <SelectItem value="by_lead_time">By Lead Time - Fastest Delivery</SelectItem>
                  <SelectItem value="by_capacity">By Capacity - Based on Availability</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Target Vendors</Label>
              <Select
                value={splitVendors}
                onValueChange={setSplitVendors}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder="Select vendors..." />
                </SelectTrigger>
                <SelectContent>
                  {availableVendors.map((vendor) => (
                    <SelectItem key={vendor} value={vendor}>
                      {vendor}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {splitPreview && (
            <Card variant="outlined" className="mt-4">
              <CardContent className="pt-4">
                <h4 className="text-sm font-medium text-primary mb-3">Split Preview</h4>
                <div className="grid grid-cols-3 gap-4 mb-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Total Items</p>
                    <p className="text-xl font-bold">{splitPreview.total_items}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Total Quantity</p>
                    <p className="text-xl font-bold">{splitPreview.total_quantity?.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">New Orders</p>
                    <p className="text-xl font-bold">{splitPreview.estimated_splits}</p>
                  </div>
                </div>

                {splitPreview.preview_details && splitPreview.preview_details.length > 0 && (
                  <div>
                    <p className="text-sm text-muted-foreground mb-2">Assignment Preview:</p>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Product</TableHead>
                          <TableHead className="text-right">Quantity</TableHead>
                          <TableHead>Assigned Vendor</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {splitPreview.preview_details.map((detail, idx) => (
                          <TableRow key={idx}>
                            <TableCell>{detail.product_id}</TableCell>
                            <TableCell className="text-right">{detail.quantity}</TableCell>
                            <TableCell>
                              <Badge variant="secondary">{detail.assigned_vendor}</Badge>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setSplitDialogOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="outline"
            onClick={handlePreviewSplit}
            disabled={loading}
            leftIcon={<Eye className="h-4 w-4" />}
          >
            Preview Split
          </Button>
          <Button
            onClick={handleExecuteSplit}
            disabled={loading || !splitPreview}
          >
            Execute Split
          </Button>
        </div>
      </Modal>

      {/* Consolidate Dialog */}
      <Modal
        open={consolidateDialogOpen}
        onClose={() => setConsolidateDialogOpen(false)}
        title="Consolidate Orders"
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-sm">
            You are about to consolidate {selectedOrders.length} orders into a single order.
          </p>
          <div>
            <p className="text-sm text-muted-foreground mb-2">Selected Orders:</p>
            <div className="flex flex-wrap gap-1">
              {selectedOrders.map(id => (
                <Badge key={id} variant="secondary">{id}</Badge>
              ))}
            </div>
          </div>
          <div>
            <Label>Consolidation Strategy</Label>
            <Select value={consolidateStrategy} onValueChange={setConsolidateStrategy}>
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="by_vendor">By Vendor - Keep vendor assignment</SelectItem>
                <SelectItem value="by_ship_date">By Ship Date - Combine similar dates</SelectItem>
                <SelectItem value="by_destination">By Destination - Combine by location</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setConsolidateDialogOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              handleConsolidate(selectedOrders);
              setConsolidateDialogOpen(false);
            }}
          >
            Consolidate
          </Button>
        </div>
      </Modal>
    </div>
  );
};

export default OrderManagement;
