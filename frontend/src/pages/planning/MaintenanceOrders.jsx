import React, { useState, useEffect } from 'react';
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
import { Plus, CheckCircle } from 'lucide-react';
import { api } from '../../services/api';

const MaintenanceOrders = () => {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newOrder, setNewOrder] = useState({
    asset_id: '',
    asset_name: '',
    site_id: '',
    maintenance_type: 'PREVENTIVE',
    work_description: '',
    priority: 'NORMAL',
    downtime_required: 'Y',
  });

  useEffect(() => {
    loadOrders();
  }, []);

  const loadOrders = async () => {
    setLoading(true);
    try {
      const response = await api.get('/maintenance-orders/');
      setOrders(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load orders');
    } finally {
      setLoading(false);
    }
  };

  const createOrder = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.post('/maintenance-orders/', newOrder);
      setCreateDialogOpen(false);
      setNewOrder({
        asset_id: '',
        asset_name: '',
        site_id: '',
        maintenance_type: 'PREVENTIVE',
        work_description: '',
        priority: 'NORMAL',
        downtime_required: 'Y',
      });
      loadOrders();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create order');
    } finally {
      setLoading(false);
    }
  };

  const approveOrder = async (orderId) => {
    setLoading(true);
    try {
      await api.post(`/maintenance-orders/${orderId}/approve`);
      loadOrders();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to approve');
    } finally {
      setLoading(false);
    }
  };

  const getStatusVariant = (status) => {
    const variants = {
      PLANNED: 'secondary',
      APPROVED: 'info',
      SCHEDULED: 'default',
      IN_PROGRESS: 'warning',
      COMPLETED: 'success',
      CANCELLED: 'destructive',
    };
    return variants[status] || 'secondary';
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Maintenance Orders</h1>
        <Button onClick={() => setCreateDialogOpen(true)} leftIcon={<Plus className="h-4 w-4" />}>
          Create Order
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
                <TableHead>Asset</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Priority</TableHead>
                <TableHead>Scheduled Date</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {orders.map((order) => (
                <TableRow key={order.id}>
                  <TableCell>{order.maintenance_order_number}</TableCell>
                  <TableCell>{order.asset_name || order.asset_id}</TableCell>
                  <TableCell><Badge>{order.maintenance_type}</Badge></TableCell>
                  <TableCell><Badge variant={getStatusVariant(order.status)}>{order.status}</Badge></TableCell>
                  <TableCell>{order.priority}</TableCell>
                  <TableCell>{order.scheduled_start_date || '-'}</TableCell>
                  <TableCell>
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
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Modal
        isOpen={createDialogOpen}
        onClose={() => setCreateDialogOpen(false)}
        title="Create Maintenance Order"
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
            <Label>Asset ID *</Label>
            <Input
              value={newOrder.asset_id}
              onChange={(e) => setNewOrder({ ...newOrder, asset_id: e.target.value })}
            />
          </div>
          <div>
            <Label>Asset Name</Label>
            <Input
              value={newOrder.asset_name}
              onChange={(e) => setNewOrder({ ...newOrder, asset_name: e.target.value })}
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
            <Label>Maintenance Type</Label>
            <Select
              value={newOrder.maintenance_type}
              onValueChange={(value) => setNewOrder({ ...newOrder, maintenance_type: value })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="PREVENTIVE">Preventive</SelectItem>
                <SelectItem value="CORRECTIVE">Corrective</SelectItem>
                <SelectItem value="PREDICTIVE">Predictive</SelectItem>
                <SelectItem value="EMERGENCY">Emergency</SelectItem>
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
                <SelectItem value="EMERGENCY">Emergency</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Downtime Required</Label>
            <Select
              value={newOrder.downtime_required}
              onValueChange={(value) => setNewOrder({ ...newOrder, downtime_required: value })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Y">Yes</SelectItem>
                <SelectItem value="N">No</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-2">
            <Label>Work Description *</Label>
            <Textarea
              rows={3}
              value={newOrder.work_description}
              onChange={(e) => setNewOrder({ ...newOrder, work_description: e.target.value })}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default MaintenanceOrders;
