/**
 * Production Orders Management Page
 *
 * View and manage production orders created from MPS plans.
 */

import React, { useState, useEffect } from 'react';
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Label,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../../components/common';
import { RefreshCw, Eye, Filter, Download } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useCapabilities } from '../../hooks/useCapabilities';
import { api } from '../../services/api';

const ProductionOrders = () => {
  const navigate = useNavigate();
  const { hasCapability } = useCapabilities();

  // State
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [totalCount, setTotalCount] = useState(0);
  const [filters, setFilters] = useState({
    status: '',
  });
  const [showFilters, setShowFilters] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [detailsDialogOpen, setDetailsDialogOpen] = useState(false);

  // Summary stats
  const [stats, setStats] = useState({
    total: 0,
    planned: 0,
    released: 0,
    in_progress: 0,
    completed: 0,
  });

  // Permissions
  const canManage = hasCapability('manage_mps');

  // Load orders
  useEffect(() => {
    loadOrders();
  }, [filters, page, rowsPerPage]);

  const loadOrders = async () => {
    try {
      setLoading(true);

      // Build query params
      const params = {
        offset: page * rowsPerPage,
        limit: rowsPerPage,
      };

      if (filters.status) {
        params.status = filters.status;
      }

      const response = await api.get('/production-orders', { params });

      setOrders(response.data.orders || []);
      setTotalCount(response.data.total || 0);
      calculateStats(response.data.orders || []);
      setError(null);
    } catch (err) {
      console.error('Error loading production orders:', err);

      // Check if API endpoint exists
      if (err.response?.status === 404) {
        setError('Production Orders API not yet implemented. Orders are being created in the database - check production_orders table.');
      } else {
        setError('Failed to load production orders. Please try again.');
      }

      // Set empty state
      setOrders([]);
      setTotalCount(0);
      calculateStats([]);
    } finally {
      setLoading(false);
    }
  };

  const calculateStats = (ordersList) => {
    const newStats = {
      total: totalCount || ordersList.length,
      planned: ordersList.filter((o) => o.status === 'PLANNED').length,
      released: ordersList.filter((o) => o.status === 'RELEASED').length,
      in_progress: ordersList.filter((o) => o.status === 'IN_PROGRESS').length,
      completed: ordersList.filter((o) => o.status === 'COMPLETED').length,
    };
    setStats(newStats);
  };

  const handleChangePage = (newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleFilterChange = (field, value) => {
    setFilters((prev) => ({
      ...prev,
      [field]: value,
    }));
    setPage(0);
  };

  const clearFilters = () => {
    setFilters({
      status: '',
    });
    setPage(0);
  };

  const handleViewDetails = (order) => {
    setSelectedOrder(order);
    setDetailsDialogOpen(true);
  };

  const handleCloseDetails = () => {
    setDetailsDialogOpen(false);
    setSelectedOrder(null);
  };

  const getStatusVariant = (status) => {
    switch (status) {
      case 'PLANNED':
        return 'secondary';
      case 'RELEASED':
        return 'info';
      case 'IN_PROGRESS':
        return 'warning';
      case 'COMPLETED':
        return 'success';
      case 'CLOSED':
        return 'success';
      case 'CANCELLED':
        return 'destructive';
      default:
        return 'secondary';
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString();
  };

  const totalPages = Math.ceil(totalCount / rowsPerPage);

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Production Orders</h1>
        <p className="text-muted-foreground">
          View and manage production orders created from MPS plans
        </p>
      </div>

      {/* Action Bar */}
      <div className="flex justify-between items-center mb-6 flex-wrap gap-4">
        <div className="flex gap-2">
          <Button variant="outline" onClick={loadOrders}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button
            variant={showFilters ? 'default' : 'outline'}
            onClick={() => setShowFilters(!showFilters)}
          >
            <Filter className="h-4 w-4 mr-2" />
            Filters
          </Button>
        </div>
        <Button variant="outline" disabled={orders.length === 0}>
          <Download className="h-4 w-4 mr-2" />
          Export
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Total Orders</p>
            <p className="text-4xl font-bold">{stats.total}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Planned</p>
            <p className="text-4xl font-bold">{stats.planned}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Released</p>
            <p className="text-4xl font-bold text-blue-500">{stats.released}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">In Progress</p>
            <p className="text-4xl font-bold text-amber-500">{stats.in_progress}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Completed</p>
            <p className="text-4xl font-bold text-green-600">{stats.completed}</p>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      {showFilters && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <h3 className="text-lg font-semibold mb-4">Filters</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <Label htmlFor="status-filter">Status</Label>
                <select
                  id="status-filter"
                  value={filters.status}
                  onChange={(e) => handleFilterChange('status', e.target.value)}
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
            </div>
            <div className="mt-4">
              <Button variant="outline" onClick={clearFilters}>
                Clear Filters
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error Alert */}
      {error && (
        <Alert className="mb-6">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-8">
          <Spinner size="lg" />
        </div>
      )}

      {/* Orders Table */}
      {!loading && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Order Number</TableHead>
                  <TableHead>Product</TableHead>
                  <TableHead>Site</TableHead>
                  <TableHead className="text-right">Planned Qty</TableHead>
                  <TableHead className="text-right">Actual Qty</TableHead>
                  <TableHead>Start Date</TableHead>
                  <TableHead>Completion Date</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>MPS Plan</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={10} className="text-center py-8">
                      <p className="text-muted-foreground mb-4">
                        No production orders found. Generate orders from an approved MPS plan.
                      </p>
                      <Button onClick={() => navigate('/planning/mps')}>
                        Go to MPS Plans
                      </Button>
                    </TableCell>
                  </TableRow>
                ) : (
                  orders.map((order) => (
                    <TableRow key={order.id}>
                      <TableCell className="font-medium">{order.order_number}</TableCell>
                      <TableCell>{order.product_name || `Product ${order.item_id}`}</TableCell>
                      <TableCell>{order.site_name || `Site ${order.site_id}`}</TableCell>
                      <TableCell className="text-right">{order.planned_quantity}</TableCell>
                      <TableCell className="text-right">
                        {order.actual_quantity !== null ? order.actual_quantity : '-'}
                      </TableCell>
                      <TableCell>{formatDate(order.planned_start_date)}</TableCell>
                      <TableCell>{formatDate(order.planned_completion_date)}</TableCell>
                      <TableCell>
                        <Badge variant={getStatusVariant(order.status)}>
                          {order.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {order.mps_plan_id ? (
                          <Button
                            variant="link"
                            size="sm"
                            className="p-0 h-auto"
                            onClick={() => navigate(`/planning/mps/${order.mps_plan_id}`)}
                          >
                            Plan {order.mps_plan_id}
                          </Button>
                        ) : '-'}
                      </TableCell>
                      <TableCell className="text-right">
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => handleViewDetails(order)}
                              >
                                <Eye className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>View Details</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>

            {/* Pagination */}
            {totalCount > 0 && (
              <div className="flex items-center justify-between px-4 py-4 border-t">
                <div className="flex items-center gap-2">
                  <Label htmlFor="rows-per-page">Rows per page:</Label>
                  <select
                    id="rows-per-page"
                    value={rowsPerPage}
                    onChange={handleChangeRowsPerPage}
                    className="h-8 px-2 rounded-md border border-input bg-background text-sm"
                  >
                    <option value={10}>10</option>
                    <option value={25}>25</option>
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">
                    Page {page + 1} of {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleChangePage(page - 1)}
                    disabled={page === 0}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleChangePage(page + 1)}
                    disabled={page >= totalPages - 1}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Order Details Dialog */}
      <Dialog open={detailsDialogOpen} onOpenChange={setDetailsDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Production Order Details</DialogTitle>
          </DialogHeader>
          {selectedOrder && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Order Number</p>
                  <p className="font-medium">{selectedOrder.order_number}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <Badge variant={getStatusVariant(selectedOrder.status)} className="mt-1">
                    {selectedOrder.status}
                  </Badge>
                </div>
              </div>

              <hr />

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Product</p>
                  <p className="font-medium">
                    {selectedOrder.product_name || `Product ${selectedOrder.item_id}`}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Manufacturing Site</p>
                  <p className="font-medium">
                    {selectedOrder.site_name || `Site ${selectedOrder.site_id}`}
                  </p>
                </div>
              </div>

              <hr />

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Planned Quantity</p>
                  <p className="text-2xl font-bold">{selectedOrder.planned_quantity}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Actual Quantity</p>
                  <p className="text-2xl font-bold">
                    {selectedOrder.actual_quantity !== null ? selectedOrder.actual_quantity : '-'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Yield %</p>
                  <p className="text-2xl font-bold">
                    {selectedOrder.yield_percentage
                      ? `${selectedOrder.yield_percentage.toFixed(1)}%`
                      : '-'}
                  </p>
                </div>
              </div>

              <hr />

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Planned Start Date</p>
                  <p className="font-medium">{formatDate(selectedOrder.planned_start_date)}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Planned Completion Date</p>
                  <p className="font-medium">{formatDate(selectedOrder.planned_completion_date)}</p>
                </div>
              </div>

              {selectedOrder.mps_plan_id && (
                <>
                  <hr />
                  <div>
                    <p className="text-sm text-muted-foreground">Source MPS Plan</p>
                    <p className="font-medium mb-2">Plan {selectedOrder.mps_plan_id}</p>
                    <Button
                      size="sm"
                      onClick={() => {
                        navigate(`/planning/mps/${selectedOrder.mps_plan_id}`);
                        handleCloseDetails();
                      }}
                    >
                      View MPS Plan
                    </Button>
                  </div>
                </>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={handleCloseDetails}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ProductionOrders;
