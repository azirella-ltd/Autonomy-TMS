import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
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
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../../components/ui/tooltip';
import {
  Eye,
  Send,
  Trash2,
  RefreshCw,
  Plus,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../services/api';
import InlineComments from '../../components/common/InlineComments';

const TransferOrders = () => {
  const navigate = useNavigate();
  const [transferOrders, setTransferOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedTO, setSelectedTO] = useState(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [toToDelete, setToToDelete] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    fetchTransferOrders();
  }, [statusFilter]);

  const fetchTransferOrders = async () => {
    try {
      setLoading(true);
      const params = statusFilter && statusFilter !== 'all' ? { status_filter: statusFilter } : {};
      const response = await api.get('/transfer-orders/', { params });
      setTransferOrders(response.data);
      setError(null);
    } catch (err) {
      console.error('Error fetching transfer orders:', err);
      setError(err.response?.data?.detail || 'Failed to fetch transfer orders');
    } finally {
      setLoading(false);
    }
  };

  const fetchTODetail = async (toId) => {
    try {
      setActionLoading(true);
      const response = await api.get(`/transfer-orders/${toId}`);
      setSelectedTO(response.data);
      setDetailDialogOpen(true);
    } catch (err) {
      console.error('Error fetching TO detail:', err);
      setError(err.response?.data?.detail || 'Failed to fetch TO detail');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReleaseTO = async (toId) => {
    try {
      setActionLoading(true);
      await api.post(`/transfer-orders/${toId}/release`);
      await fetchTransferOrders();
      setError(null);
    } catch (err) {
      console.error('Error releasing TO:', err);
      setError(err.response?.data?.detail || 'Failed to release TO');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteTO = async () => {
    if (!toToDelete) return;

    try {
      setActionLoading(true);
      await api.delete(`/transfer-orders/${toToDelete.id}`);
      await fetchTransferOrders();
      setDeleteDialogOpen(false);
      setToToDelete(null);
      setError(null);
    } catch (err) {
      console.error('Error deleting TO:', err);
      setError(err.response?.data?.detail || 'Failed to delete TO');
    } finally {
      setActionLoading(false);
    }
  };

  const openDeleteDialog = (to) => {
    setToToDelete(to);
    setDeleteDialogOpen(true);
  };

  const getStatusVariant = (status) => {
    const variants = {
      DRAFT: 'secondary',
      RELEASED: 'info',
      IN_TRANSIT: 'warning',
      RECEIVED: 'success',
    };
    return variants[status] || 'secondary';
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString();
  };

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Transfer Orders</h1>
        <div className="flex gap-3">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="Status Filter" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              <SelectItem value="DRAFT">Draft</SelectItem>
              <SelectItem value="RELEASED">Released</SelectItem>
              <SelectItem value="IN_TRANSIT">In Transit</SelectItem>
              <SelectItem value="RECEIVED">Received</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            onClick={fetchTransferOrders}
            disabled={loading}
            leftIcon={<RefreshCw className="h-4 w-4" />}
          >
            Refresh
          </Button>
          <Button
            onClick={() => navigate('/planning/transfer-orders/create')}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            Create TO
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Card>
        {loading ? (
          <div className="flex justify-center p-8">
            <Spinner size="lg" />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>TO Number</TableHead>
                <TableHead>Source Site</TableHead>
                <TableHead>Destination Site</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Shipment Date</TableHead>
                <TableHead>Est. Delivery</TableHead>
                <TableHead className="text-center">Line Items</TableHead>
                <TableHead>Transport Mode</TableHead>
                <TableHead className="text-center">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {transferOrders.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-8">
                    <p className="text-muted-foreground">No transfer orders found</p>
                  </TableCell>
                </TableRow>
              ) : (
                transferOrders.map((to) => (
                  <TableRow key={to.id}>
                    <TableCell>
                      <span className="font-medium">{to.to_number}</span>
                    </TableCell>
                    <TableCell>{to.source_site_name}</TableCell>
                    <TableCell>{to.destination_site_name}</TableCell>
                    <TableCell>
                      <Badge variant={getStatusVariant(to.status)}>{to.status}</Badge>
                    </TableCell>
                    <TableCell>{formatDate(to.shipment_date)}</TableCell>
                    <TableCell>{formatDate(to.estimated_delivery_date)}</TableCell>
                    <TableCell className="text-center">{to.line_items_count}</TableCell>
                    <TableCell>{to.transportation_mode || 'N/A'}</TableCell>
                    <TableCell>
                      <div className="flex justify-center gap-1">
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => fetchTODetail(to.id)}
                                disabled={actionLoading}
                              >
                                <Eye className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>View Details</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                        {to.status === 'DRAFT' && (
                          <>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => handleReleaseTO(to.id)}
                                    disabled={actionLoading}
                                  >
                                    <Send className="h-4 w-4 text-primary" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Release for Shipment</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => openDeleteDialog(to)}
                                    disabled={actionLoading}
                                  >
                                    <Trash2 className="h-4 w-4 text-destructive" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Delete</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          </>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        )}
      </Card>

      {/* Detail Dialog */}
      <Modal
        open={detailDialogOpen}
        onClose={() => setDetailDialogOpen(false)}
        title="Transfer Order Details"
        size="lg"
      >
        {selectedTO && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">TO Number</p>
                <p className="font-medium">{selectedTO.to_number}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <Badge variant={getStatusVariant(selectedTO.status)}>
                  {selectedTO.status}
                </Badge>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Source Site</p>
                <p className="font-medium">{selectedTO.source_site_name}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Destination Site</p>
                <p className="font-medium">{selectedTO.destination_site_name}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Shipment Date</p>
                <p className="font-medium">{formatDate(selectedTO.shipment_date)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Estimated Delivery</p>
                <p className="font-medium">{formatDate(selectedTO.estimated_delivery_date)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Transportation Mode</p>
                <p className="font-medium">{selectedTO.transportation_mode || 'N/A'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Carrier</p>
                <p className="font-medium">{selectedTO.carrier || 'N/A'}</p>
              </div>
            </div>

            {selectedTO.notes && (
              <div>
                <p className="text-sm text-muted-foreground">Notes</p>
                <p className="font-medium">{selectedTO.notes}</p>
              </div>
            )}

            <div>
              <h4 className="font-medium mb-3">Line Items</h4>
              <Card variant="outlined">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Line #</TableHead>
                      <TableHead>Product</TableHead>
                      <TableHead className="text-right">Quantity</TableHead>
                      <TableHead>Requested Ship Date</TableHead>
                      <TableHead>Requested Delivery</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {selectedTO.line_items.map((item) => (
                      <TableRow key={item.line_number}>
                        <TableCell>{item.line_number}</TableCell>
                        <TableCell>
                          {item.product_name} (ID: {item.product_id})
                        </TableCell>
                        <TableCell className="text-right">{item.quantity}</TableCell>
                        <TableCell>{formatDate(item.requested_ship_date)}</TableCell>
                        <TableCell>{formatDate(item.requested_delivery_date)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            </div>

            {/* Inline Comments Section */}
            <InlineComments
              entityType="transfer_order"
              entityId={selectedTO.id}
              title="Order Comments"
              collapsible={true}
              defaultExpanded={true}
            />
          </div>
        )}
        <div className="flex justify-end mt-6">
          <Button variant="outline" onClick={() => setDetailDialogOpen(false)}>Close</Button>
        </div>
      </Modal>

      {/* Delete Confirmation Dialog */}
      <Modal
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        title="Delete Transfer Order"
        size="sm"
      >
        <p className="text-sm">
          Are you sure you want to delete TO {toToDelete?.to_number}? This action cannot be undone.
        </p>
        <div className="flex justify-end gap-2 mt-6">
          <Button
            variant="outline"
            onClick={() => setDeleteDialogOpen(false)}
            disabled={actionLoading}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDeleteTO}
            disabled={actionLoading}
          >
            {actionLoading ? <Spinner size="sm" /> : 'Delete'}
          </Button>
        </div>
      </Modal>
    </div>
  );
};

export default TransferOrders;
