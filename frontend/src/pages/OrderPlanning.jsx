/**
 * Order Planning & Tracking Dashboard
 *
 * Unified order management view combining inbound (PO), outbound (Customer/Fulfillment),
 * transfer (TO), and production (MO) orders with KPIs, timeline, and vendor performance.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Label,
  Input,
  Modal,
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
} from '../components/common';
import {
  Truck,
  Filter,
  Download,
  RefreshCw,
  Package,
  Factory,
  ShoppingCart,
  ArrowRightLeft,
  Clock,
  AlertTriangle,
  CheckCircle,
  TrendingUp,
  TrendingDown,
  Eye,
  Search,
  Calendar,
} from 'lucide-react';
import api from '../services/api';

// --- Mock Data ---

const generateMockOrders = () => {
  const types = ['PO', 'TO', 'CO', 'MO'];
  const statuses = ['draft', 'confirmed', 'in_transit', 'processing', 'delivered', 'delayed', 'cancelled'];
  const sites = ['Factory-East', 'Factory-West', 'DC-Central', 'DC-North', 'Wholesaler-A', 'Retailer-Main', 'Supplier-Alpha', 'Supplier-Beta'];
  const products = ['SKU-001', 'SKU-002', 'SKU-003', 'SKU-004', 'SKU-005'];

  return Array.from({ length: 40 }, (_, i) => {
    const type = types[i % types.length];
    const status = statuses[Math.floor(Math.random() * statuses.length)];
    const qty = Math.floor(Math.random() * 500) + 10;
    const created = new Date(Date.now() - Math.random() * 30 * 86400000);
    const due = new Date(created.getTime() + (Math.random() * 14 + 2) * 86400000);
    return {
      id: `${type}-${String(1000 + i).slice(1)}`,
      type,
      product: products[i % products.length],
      from_site: sites[Math.floor(Math.random() * sites.length)],
      to_site: sites[Math.floor(Math.random() * sites.length)],
      quantity: qty,
      status,
      priority: Math.floor(Math.random() * 5) + 1,
      created_at: created.toISOString(),
      due_date: due.toISOString(),
      eta: status === 'delivered' ? 'Completed' : `${Math.floor(Math.random() * 10) + 1} days`,
      value: qty * (Math.random() * 50 + 10),
      vendor: type === 'PO' ? `Vendor-${String.fromCharCode(65 + (i % 5))}` : null,
    };
  });
};

const generateVendorPerformance = () => [
  { vendor: 'Vendor-A', otd: 96.2, quality: 98.5, avgLeadDays: 12, orders: 45, onTimeOrders: 43, lateOrders: 2, trend: 'improving' },
  { vendor: 'Vendor-B', otd: 91.8, quality: 97.1, avgLeadDays: 15, orders: 32, onTimeOrders: 29, lateOrders: 3, trend: 'stable' },
  { vendor: 'Vendor-C', otd: 88.5, quality: 99.2, avgLeadDays: 8, orders: 28, onTimeOrders: 25, lateOrders: 3, trend: 'degrading' },
  { vendor: 'Vendor-D', otd: 94.7, quality: 96.8, avgLeadDays: 10, orders: 19, onTimeOrders: 18, lateOrders: 1, trend: 'improving' },
  { vendor: 'Vendor-E', otd: 85.3, quality: 95.4, avgLeadDays: 18, orders: 15, onTimeOrders: 13, lateOrders: 2, trend: 'degrading' },
];

// --- Helpers ---

const getStatusVariant = (status) => {
  const variants = {
    draft: 'secondary',
    confirmed: 'info',
    in_transit: 'info',
    processing: 'warning',
    delivered: 'success',
    delayed: 'destructive',
    cancelled: 'secondary',
  };
  return variants[status] || 'secondary';
};

const getTypeIcon = (type) => {
  const icons = { PO: Package, TO: ArrowRightLeft, CO: ShoppingCart, MO: Factory };
  const Icon = icons[type] || Package;
  return <Icon className="h-4 w-4" />;
};

const getTypeLabel = (type) => {
  const labels = { PO: 'Purchase Order', TO: 'Transfer Order', CO: 'Customer Order', MO: 'Manufacturing Order' };
  return labels[type] || type;
};

const formatDate = (iso) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

const formatCurrency = (val) => `$${Number(val).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

// --- Sub-components ---

const OrdersTable = ({ orders, onViewDetail }) => (
  <Table>
    <TableHeader>
      <TableRow>
        <TableHead>Order ID</TableHead>
        <TableHead>Type</TableHead>
        <TableHead>Product</TableHead>
        <TableHead>From</TableHead>
        <TableHead>To</TableHead>
        <TableHead className="text-right">Qty</TableHead>
        <TableHead>Priority</TableHead>
        <TableHead>Status</TableHead>
        <TableHead>Due Date</TableHead>
        <TableHead>ETA</TableHead>
        <TableHead>Actions</TableHead>
      </TableRow>
    </TableHeader>
    <TableBody>
      {orders.length === 0 ? (
        <TableRow>
          <TableCell colSpan={11} className="text-center text-muted-foreground py-8">
            No orders match the current filters.
          </TableCell>
        </TableRow>
      ) : (
        orders.map((order) => (
          <TableRow key={order.id}>
            <TableCell className="font-semibold font-mono">{order.id}</TableCell>
            <TableCell>
              <div className="flex items-center gap-1">
                {getTypeIcon(order.type)}
                <span className="text-xs">{order.type}</span>
              </div>
            </TableCell>
            <TableCell>{order.product}</TableCell>
            <TableCell className="text-sm">{order.from_site}</TableCell>
            <TableCell className="text-sm">{order.to_site}</TableCell>
            <TableCell className="text-right font-mono">{order.quantity}</TableCell>
            <TableCell>
              <Badge variant={order.priority <= 2 ? 'destructive' : order.priority <= 3 ? 'warning' : 'secondary'}>
                P{order.priority}
              </Badge>
            </TableCell>
            <TableCell>
              <Badge variant={getStatusVariant(order.status)}>
                {order.status.replace('_', ' ')}
              </Badge>
            </TableCell>
            <TableCell className="text-sm">{formatDate(order.due_date)}</TableCell>
            <TableCell className="text-sm">{order.eta}</TableCell>
            <TableCell>
              <Button variant="ghost" size="sm" onClick={() => onViewDetail(order)}>
                <Eye className="h-4 w-4" />
              </Button>
            </TableCell>
          </TableRow>
        ))
      )}
    </TableBody>
  </Table>
);

const VendorPerformanceTab = ({ vendors }) => (
  <div className="space-y-6">
    <Card>
      <CardContent className="pt-6">
        <h3 className="text-lg font-semibold mb-4">Vendor Scorecard</h3>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Vendor</TableHead>
              <TableHead className="text-right">On-Time Delivery</TableHead>
              <TableHead className="text-right">Quality Rate</TableHead>
              <TableHead className="text-right">Avg Lead Time</TableHead>
              <TableHead className="text-right">Total Orders</TableHead>
              <TableHead className="text-right">Late Orders</TableHead>
              <TableHead>Trend</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {vendors.map((v) => (
              <TableRow key={v.vendor}>
                <TableCell className="font-medium">{v.vendor}</TableCell>
                <TableCell className={`text-right font-mono ${v.otd >= 95 ? 'text-green-600' : v.otd >= 90 ? 'text-amber-600' : 'text-red-600'}`}>
                  {v.otd}%
                </TableCell>
                <TableCell className="text-right font-mono">{v.quality}%</TableCell>
                <TableCell className="text-right font-mono">{v.avgLeadDays} days</TableCell>
                <TableCell className="text-right font-mono">{v.orders}</TableCell>
                <TableCell className="text-right font-mono">{v.lateOrders}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    {v.trend === 'improving' && <TrendingUp className="h-4 w-4 text-green-600" />}
                    {v.trend === 'degrading' && <TrendingDown className="h-4 w-4 text-red-600" />}
                    {v.trend === 'stable' && <span className="text-muted-foreground">—</span>}
                    <span className="text-xs text-muted-foreground">{v.trend}</span>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  </div>
);

// --- Main Component ---

const OrderPlanning = () => {
  const [orders, setOrders] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [currentTab, setCurrentTab] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [detailOrder, setDetailOrder] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [ordersRes, vendorsRes] = await Promise.allSettled([
        api.get('/api/v1/orders'),
        api.get('/api/v1/orders/vendor-performance'),
      ]);
      setOrders(ordersRes.status === 'fulfilled' ? ordersRes.value.data : generateMockOrders());
      setVendors(vendorsRes.status === 'fulfilled' ? vendorsRes.value.data : generateVendorPerformance());
    } catch {
      setOrders(generateMockOrders());
      setVendors(generateVendorPerformance());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleExport = () => {
    const csv = ['Order ID,Type,Product,From,To,Qty,Status,Due Date,Value'];
    filteredOrders.forEach((o) => {
      csv.push(`${o.id},${o.type},${o.product},${o.from_site},${o.to_site},${o.quantity},${o.status},${formatDate(o.due_date)},${o.value.toFixed(2)}`);
    });
    const blob = new Blob([csv.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `orders_export_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Filter logic
  const typeFilter = currentTab === 'all' ? null : currentTab.toUpperCase();
  const filteredOrders = orders.filter((o) => {
    if (typeFilter && o.type !== typeFilter) return false;
    if (filterStatus !== 'all' && o.status !== filterStatus) return false;
    if (searchTerm && !o.id.toLowerCase().includes(searchTerm.toLowerCase()) && !o.product.toLowerCase().includes(searchTerm.toLowerCase())) return false;
    return true;
  });

  // KPI calculations
  const kpis = {
    total: orders.length,
    inTransit: orders.filter((o) => o.status === 'in_transit').length,
    processing: orders.filter((o) => o.status === 'processing').length,
    delayed: orders.filter((o) => o.status === 'delayed').length,
    delivered: orders.filter((o) => o.status === 'delivered').length,
    totalValue: orders.reduce((sum, o) => sum + (o.value || 0), 0),
    avgPriority: orders.length > 0 ? (orders.reduce((sum, o) => sum + o.priority, 0) / orders.length).toFixed(1) : '—',
    onTimeRate: orders.length > 0
      ? ((orders.filter((o) => o.status === 'delivered').length / Math.max(orders.filter((o) => ['delivered', 'delayed'].includes(o.status)).length, 1)) * 100).toFixed(1)
      : '—',
  };

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      <div className="mb-8 flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Truck className="h-10 w-10 text-primary" />
          <div>
            <h1 className="text-3xl font-bold">Order Planning & Tracking</h1>
            <p className="text-sm text-muted-foreground">Unified view of all order types across the supply chain</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={loadData} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button variant="outline" onClick={handleExport}>
            <Download className="h-4 w-4 mr-2" />
            Export CSV
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-8 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4 pb-4 text-center">
            <p className="text-xs text-muted-foreground mb-1">Total</p>
            <p className="text-2xl font-bold">{kpis.total}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4 text-center">
            <p className="text-xs text-muted-foreground mb-1">In Transit</p>
            <p className="text-2xl font-bold text-blue-500">{kpis.inTransit}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4 text-center">
            <p className="text-xs text-muted-foreground mb-1">Processing</p>
            <p className="text-2xl font-bold text-amber-500">{kpis.processing}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4 text-center">
            <p className="text-xs text-muted-foreground mb-1">Delayed</p>
            <p className="text-2xl font-bold text-red-500">{kpis.delayed}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4 text-center">
            <p className="text-xs text-muted-foreground mb-1">Delivered</p>
            <p className="text-2xl font-bold text-green-600">{kpis.delivered}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4 text-center">
            <p className="text-xs text-muted-foreground mb-1">Total Value</p>
            <p className="text-2xl font-bold">{formatCurrency(kpis.totalValue)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4 text-center">
            <p className="text-xs text-muted-foreground mb-1">Avg Priority</p>
            <p className="text-2xl font-bold">{kpis.avgPriority}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4 text-center">
            <p className="text-xs text-muted-foreground mb-1">On-Time %</p>
            <p className="text-2xl font-bold text-primary">{kpis.onTimeRate}%</p>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="pt-4 pb-4">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2 flex-1 min-w-[200px]">
              <Search className="h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search by order ID or product..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="max-w-sm"
              />
            </div>
            <div className="min-w-[160px]">
              <Label htmlFor="status-filter" className="sr-only">Status</Label>
              <select
                id="status-filter"
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="w-full h-9 px-3 rounded-md border border-input bg-background text-sm"
              >
                <option value="all">All Statuses</option>
                <option value="draft">Draft</option>
                <option value="confirmed">Confirmed</option>
                <option value="in_transit">In Transit</option>
                <option value="processing">Processing</option>
                <option value="delivered">Delivered</option>
                <option value="delayed">Delayed</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>
            <span className="text-sm text-muted-foreground">{filteredOrders.length} orders</span>
          </div>
        </CardContent>
      </Card>

      {/* Order Tabs */}
      <Tabs value={currentTab} onValueChange={setCurrentTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="all">All Orders ({orders.length})</TabsTrigger>
          <TabsTrigger value="po">Purchase ({orders.filter((o) => o.type === 'PO').length})</TabsTrigger>
          <TabsTrigger value="to">Transfer ({orders.filter((o) => o.type === 'TO').length})</TabsTrigger>
          <TabsTrigger value="co">Customer ({orders.filter((o) => o.type === 'CO').length})</TabsTrigger>
          <TabsTrigger value="mo">Manufacturing ({orders.filter((o) => o.type === 'MO').length})</TabsTrigger>
          <TabsTrigger value="vendor">Vendor Performance</TabsTrigger>
        </TabsList>

        {['all', 'po', 'to', 'co', 'mo'].map((tab) => (
          <TabsContent key={tab} value={tab}>
            <Card>
              <CardContent className="p-0">
                <OrdersTable
                  orders={filteredOrders}
                  onViewDetail={(order) => { setDetailOrder(order); setDetailOpen(true); }}
                />
              </CardContent>
            </Card>
          </TabsContent>
        ))}

        <TabsContent value="vendor">
          <VendorPerformanceTab vendors={vendors} />
        </TabsContent>
      </Tabs>

      {/* Order Detail Modal */}
      <Modal
        isOpen={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={detailOrder ? `Order ${detailOrder.id}` : 'Order Details'}
        maxWidth="lg"
      >
        {detailOrder && (
          <div className="space-y-4">
            <div className="flex items-center gap-3 mb-4">
              {getTypeIcon(detailOrder.type)}
              <Badge>{getTypeLabel(detailOrder.type)}</Badge>
              <Badge variant={getStatusVariant(detailOrder.status)}>
                {detailOrder.status.replace('_', ' ')}
              </Badge>
              <Badge variant={detailOrder.priority <= 2 ? 'destructive' : 'secondary'}>
                Priority {detailOrder.priority}
              </Badge>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Product</p>
                <p className="font-medium">{detailOrder.product}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Quantity</p>
                <p className="font-medium">{detailOrder.quantity} units</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">From Site</p>
                <p className="font-medium">{detailOrder.from_site}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">To Site</p>
                <p className="font-medium">{detailOrder.to_site}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Created</p>
                <p className="font-medium">{formatDate(detailOrder.created_at)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Due Date</p>
                <p className="font-medium">{formatDate(detailOrder.due_date)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">ETA</p>
                <p className="font-medium">{detailOrder.eta}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Order Value</p>
                <p className="font-medium">{formatCurrency(detailOrder.value)}</p>
              </div>
              {detailOrder.vendor && (
                <div>
                  <p className="text-sm text-muted-foreground">Vendor</p>
                  <p className="font-medium">{detailOrder.vendor}</p>
                </div>
              )}
            </div>

            {/* Timeline */}
            <div className="mt-4">
              <h4 className="font-semibold mb-3">Order Timeline</h4>
              <div className="space-y-3">
                {[
                  { label: 'Created', date: detailOrder.created_at, done: true },
                  { label: 'Confirmed', date: null, done: ['confirmed', 'in_transit', 'processing', 'delivered'].includes(detailOrder.status) },
                  { label: 'In Transit / Processing', date: null, done: ['in_transit', 'processing', 'delivered'].includes(detailOrder.status) },
                  { label: 'Delivered', date: detailOrder.status === 'delivered' ? detailOrder.due_date : null, done: detailOrder.status === 'delivered' },
                ].map((step, idx) => (
                  <div key={idx} className="flex items-center gap-3">
                    <div className={`w-6 h-6 rounded-full flex items-center justify-center ${step.done ? 'bg-green-100' : 'bg-muted'}`}>
                      {step.done ? (
                        <CheckCircle className="h-4 w-4 text-green-600" />
                      ) : (
                        <Clock className="h-4 w-4 text-muted-foreground" />
                      )}
                    </div>
                    <span className={step.done ? 'font-medium' : 'text-muted-foreground'}>{step.label}</span>
                    {step.date && <span className="text-xs text-muted-foreground ml-auto">{formatDate(step.date)}</span>}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
        <div className="flex justify-end mt-6">
          <Button variant="outline" onClick={() => setDetailOpen(false)}>Close</Button>
        </div>
      </Modal>
    </div>
  );
};

export default OrderPlanning;
