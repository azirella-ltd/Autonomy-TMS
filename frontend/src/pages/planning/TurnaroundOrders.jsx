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
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';

const TurnaroundOrders = () => {
  const { formatCustomer } = useDisplayPreferences();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newOrder, setNewOrder] = useState({
    return_order_id: '',
    customer_id: '',
    from_site_id: '',
    to_site_id: '',
    return_reason_code: 'DEFECTIVE',
    return_reason_description: '',
    turnaround_type: 'RETURN',
    priority: 'NORMAL',
  });

  useEffect(() => {
    loadOrders();
  }, []);

  const loadOrders = async () => {
    setLoading(true);
    try {
      const response = await api.get('/turnaround-orders/');
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
      await api.post('/turnaround-orders/', newOrder);
      setCreateDialogOpen(false);
      setNewOrder({
        return_order_id: '',
        customer_id: '',
        from_site_id: '',
        to_site_id: '',
        return_reason_code: 'DEFECTIVE',
        return_reason_description: '',
        turnaround_type: 'RETURN',
        priority: 'NORMAL',
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
      await api.post(`/turnaround-orders/${orderId}/approve`);
      loadOrders();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to approve');
    } finally {
      setLoading(false);
    }
  };

  const getStatusVariant = (status) => {
    const variants = {
      INITIATED: 'secondary',
      APPROVED: 'info',
      IN_TRANSIT: 'default',
      RECEIVED: 'warning',
      INSPECTED: 'secondary',
      COMPLETED: 'success',
      REJECTED: 'destructive',
    };
    return variants[status] || 'secondary';
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Turnaround Orders (Returns & Refurbishment)</h1>
        <Button onClick={() => setCreateDialogOpen(true)} leftIcon={<Plus className="h-4 w-4" />}>
          Create Return
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
                <TableHead>RMA</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Disposition</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {orders.map((order) => (
                <TableRow key={order.id}>
                  <TableCell>{order.turnaround_order_number}</TableCell>
                  <TableCell>{order.rma_number}</TableCell>
                  <TableCell>{formatCustomer(order.customer_id, order.customer_name) || '-'}</TableCell>
                  <TableCell><Badge>{order.turnaround_type}</Badge></TableCell>
                  <TableCell>{order.return_reason_code}</TableCell>
                  <TableCell><Badge variant={getStatusVariant(order.status)}>{order.status}</Badge></TableCell>
                  <TableCell>{order.disposition || '-'}</TableCell>
                  <TableCell>
                    {order.status === 'INITIATED' && (
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
        title="Create Turnaround Order"
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
            <Label>Return Order ID</Label>
            <Input
              value={newOrder.return_order_id}
              onChange={(e) => setNewOrder({ ...newOrder, return_order_id: e.target.value })}
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
            <Label>From Site ID *</Label>
            <Input
              value={newOrder.from_site_id}
              onChange={(e) => setNewOrder({ ...newOrder, from_site_id: e.target.value })}
            />
          </div>
          <div>
            <Label>To Site ID *</Label>
            <Input
              value={newOrder.to_site_id}
              onChange={(e) => setNewOrder({ ...newOrder, to_site_id: e.target.value })}
            />
          </div>
          <div>
            <Label>Return Reason</Label>
            <Select
              value={newOrder.return_reason_code}
              onValueChange={(value) => setNewOrder({ ...newOrder, return_reason_code: value })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="DEFECTIVE">Defective</SelectItem>
                <SelectItem value="WRONG_ITEM">Wrong Item</SelectItem>
                <SelectItem value="DAMAGED_IN_TRANSIT">Damaged in Transit</SelectItem>
                <SelectItem value="CUSTOMER_REMORSE">Customer Remorse</SelectItem>
                <SelectItem value="WARRANTY_CLAIM">Warranty Claim</SelectItem>
                <SelectItem value="END_OF_LEASE">End of Lease</SelectItem>
                <SelectItem value="RECALL">Recall</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Turnaround Type</Label>
            <Select
              value={newOrder.turnaround_type}
              onValueChange={(value) => setNewOrder({ ...newOrder, turnaround_type: value })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="RETURN">Return</SelectItem>
                <SelectItem value="REPAIR">Repair</SelectItem>
                <SelectItem value="REFURBISH">Refurbish</SelectItem>
                <SelectItem value="RECYCLE">Recycle</SelectItem>
                <SelectItem value="SCRAP">Scrap</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-2">
            <Label>Return Reason Description</Label>
            <Textarea
              rows={2}
              value={newOrder.return_reason_description}
              onChange={(e) => setNewOrder({ ...newOrder, return_reason_description: e.target.value })}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default TurnaroundOrders;
