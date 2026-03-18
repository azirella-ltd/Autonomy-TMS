import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Input,
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
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../../components/ui/tooltip';
import { Plus, CheckCircle, Eye } from 'lucide-react';
import { api } from '../../services/api';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';

const ProjectOrders = () => {
  const { formatCustomer, formatSite } = useDisplayPreferences();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [detailsDialogOpen, setDetailsDialogOpen] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [newOrder, setNewOrder] = useState({
    project_id: '',
    project_name: '',
    customer_id: '',
    customer_name: '',
    site_id: '',
    required_completion_date: '',
    project_type: 'MTO',
    priority: 'NORMAL',
    estimated_cost: 0,
    line_items: [],
  });

  useEffect(() => {
    loadOrders();
  }, []);

  const loadOrders = async () => {
    setLoading(true);
    try {
      const response = await api.get('/project-orders/');
      setOrders(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load project orders');
    } finally {
      setLoading(false);
    }
  };

  const createOrder = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.post('/project-orders/', newOrder);
      setCreateDialogOpen(false);
      setNewOrder({
        project_id: '',
        project_name: '',
        customer_id: '',
        customer_name: '',
        site_id: '',
        required_completion_date: '',
        project_type: 'MTO',
        priority: 'NORMAL',
        estimated_cost: 0,
        line_items: [],
      });
      loadOrders();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create project order');
    } finally {
      setLoading(false);
    }
  };

  const approveOrder = async (orderId) => {
    setLoading(true);
    try {
      await api.post(`/project-orders/${orderId}/approve`);
      loadOrders();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to approve order');
    } finally {
      setLoading(false);
    }
  };

  const viewDetails = async (orderId) => {
    setLoading(true);
    try {
      const response = await api.get(`/project-orders/${orderId}`);
      setSelectedOrder(response.data);
      setDetailsDialogOpen(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load order details');
    } finally {
      setLoading(false);
    }
  };

  const getStatusVariant = (status) => {
    const variants = {
      PLANNED: 'secondary',
      APPROVED: 'info',
      IN_PROGRESS: 'default',
      ON_HOLD: 'warning',
      COMPLETED: 'success',
      CANCELLED: 'destructive',
    };
    return variants[status] || 'secondary';
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Project Orders</h1>
        <Button onClick={() => setCreateDialogOpen(true)} leftIcon={<Plus className="h-4 w-4" />}>
          Create Project Order
        </Button>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Order Number</TableHead>
                <TableHead>Project</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead>Site</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Priority</TableHead>
                <TableHead>Completion Date</TableHead>
                <TableHead>Progress</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {orders.map((order) => (
                <TableRow key={order.id}>
                  <TableCell>{order.project_order_number}</TableCell>
                  <TableCell>
                    <div>
                      {order.project_name}
                      <p className="text-xs text-muted-foreground">{order.project_id}</p>
                    </div>
                  </TableCell>
                  <TableCell>{formatCustomer(order.customer_id, order.customer_name) || '-'}</TableCell>
                  <TableCell>{formatSite(order.site_id, order.site_name)}</TableCell>
                  <TableCell><Badge variant={getStatusVariant(order.status)}>{order.status}</Badge></TableCell>
                  <TableCell>{order.priority}</TableCell>
                  <TableCell>{order.required_completion_date}</TableCell>
                  <TableCell>{order.completion_percentage}%</TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="sm" onClick={() => viewDetails(order.id)}>
                              <Eye className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>View Details</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                      {order.status === 'PLANNED' && (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button variant="ghost" size="sm" onClick={() => approveOrder(order.id)}>
                                <CheckCircle className="h-4 w-4 text-primary" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Approve</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Create Order Modal */}
      <Modal
        isOpen={createDialogOpen}
        onClose={() => setCreateDialogOpen(false)}
        title="Create Project Order"
        size="lg"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
            <Button onClick={createOrder} disabled={loading}>Create</Button>
          </div>
        }
      >
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Project ID *</Label>
            <Input
              value={newOrder.project_id}
              onChange={(e) => setNewOrder({ ...newOrder, project_id: e.target.value })}
            />
          </div>
          <div>
            <Label>Project Name *</Label>
            <Input
              value={newOrder.project_name}
              onChange={(e) => setNewOrder({ ...newOrder, project_name: e.target.value })}
            />
          </div>
          <div>
            <Label>Customer ID</Label>
            <Input
              value={newOrder.customer_id}
              onChange={(e) => setNewOrder({ ...newOrder, customer_id: e.target.value })}
            />
          </div>
          <div>
            <Label>Customer Name</Label>
            <Input
              value={newOrder.customer_name}
              onChange={(e) => setNewOrder({ ...newOrder, customer_name: e.target.value })}
            />
          </div>
          <div>
            <Label>Site ID *</Label>
            <Input
              value={newOrder.site_id}
              onChange={(e) => setNewOrder({ ...newOrder, site_id: e.target.value })}
            />
          </div>
          <div>
            <Label>Required Completion Date *</Label>
            <Input
              type="date"
              value={newOrder.required_completion_date}
              onChange={(e) => setNewOrder({ ...newOrder, required_completion_date: e.target.value })}
            />
          </div>
          <div>
            <Label>Project Type</Label>
            <Select
              value={newOrder.project_type}
              onValueChange={(value) => setNewOrder({ ...newOrder, project_type: value })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ETO">Engineer-to-Order</SelectItem>
                <SelectItem value="MTO">Make-to-Order</SelectItem>
                <SelectItem value="CUSTOM">Custom</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Priority</Label>
            <Select
              value={newOrder.priority}
              onValueChange={(value) => setNewOrder({ ...newOrder, priority: value })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="LOW">Low</SelectItem>
                <SelectItem value="NORMAL">Normal</SelectItem>
                <SelectItem value="HIGH">High</SelectItem>
                <SelectItem value="CRITICAL">Critical</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-2">
            <Label>Estimated Cost</Label>
            <Input
              type="number"
              value={newOrder.estimated_cost}
              onChange={(e) => setNewOrder({ ...newOrder, estimated_cost: parseFloat(e.target.value) })}
            />
          </div>
        </div>
      </Modal>

      {/* Order Details Modal */}
      <Modal
        isOpen={detailsDialogOpen}
        onClose={() => setDetailsDialogOpen(false)}
        title="Project Order Details"
        size="lg"
        footer={
          <Button variant="outline" onClick={() => setDetailsDialogOpen(false)}>Close</Button>
        }
      >
        {selectedOrder && (
          <div className="space-y-4">
            <div>
              <h3 className="text-lg font-semibold">{selectedOrder.project_name}</h3>
              <p className="text-sm text-muted-foreground">{selectedOrder.project_order_number}</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Project ID</p>
                <p>{selectedOrder.project_id}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">Customer</p>
                <p>{formatCustomer(selectedOrder.customer_id, selectedOrder.customer_name) || '-'}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">Status</p>
                <Badge variant={getStatusVariant(selectedOrder.status)}>{selectedOrder.status}</Badge>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">Priority</p>
                <p>{selectedOrder.priority}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">Completion</p>
                <p>{selectedOrder.completion_percentage}%</p>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">Required Date</p>
                <p>{selectedOrder.required_completion_date}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">Estimated Cost</p>
                <p>${selectedOrder.estimated_cost?.toLocaleString() || 0}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">Actual Cost</p>
                <p>${selectedOrder.actual_cost?.toLocaleString() || 0}</p>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default ProjectOrders;
