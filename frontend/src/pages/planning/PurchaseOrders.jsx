import React, { useState, useEffect } from 'react';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Input,
  Textarea,
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
  Check,
  Trash2,
  RefreshCw,
  Plus,
  Send,
  ThumbsUp,
  CheckCircle,
  Clock,
  Truck,
  Package,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../services/api';
import { Conversation } from '@azirella-ltd/autonomy-frontend';

const PurchaseOrders = () => {
  const navigate = useNavigate();
  const { formatSupplier, formatProduct } = useDisplayPreferences();
  const [purchaseOrders, setPurchaseOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedPO, setSelectedPO] = useState(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [poToDelete, setPoToDelete] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [ackDialogOpen, setAckDialogOpen] = useState(false);
  const [ackNotes, setAckNotes] = useState('');
  const [ackAction, setAckAction] = useState(null);
  const [success, setSuccess] = useState(null);

  useEffect(() => {
    fetchPurchaseOrders();
  }, [statusFilter]);

  const fetchPurchaseOrders = async () => {
    try {
      setLoading(true);
      const params = statusFilter && statusFilter !== 'all' ? { status_filter: statusFilter } : {};
      const response = await api.get('/purchase-orders/', { params });
      setPurchaseOrders(response.data);
      setError(null);
    } catch (err) {
      console.error('Error fetching purchase orders:', err);
      setError(err.response?.data?.detail || 'Failed to fetch purchase orders');
    } finally {
      setLoading(false);
    }
  };

  const fetchPODetail = async (poId) => {
    try {
      setActionLoading(true);
      const response = await api.get(`/purchase-orders/${poId}`);
      setSelectedPO(response.data);
      setDetailDialogOpen(true);
    } catch (err) {
      console.error('Error fetching PO detail:', err);
      setError(err.response?.data?.detail || 'Failed to fetch PO detail');
    } finally {
      setActionLoading(false);
    }
  };

  const handleApprovePO = async (poId) => {
    try {
      setActionLoading(true);
      await api.post(`/purchase-orders/${poId}/approve`);
      await fetchPurchaseOrders();
      setError(null);
      setSuccess('PO approved successfully');
    } catch (err) {
      console.error('Error approving PO:', err);
      setError(err.response?.data?.detail || 'Failed to approve PO');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSendPO = async (poId) => {
    try {
      setActionLoading(true);
      await api.post(`/purchase-orders/${poId}/send`);
      await fetchPurchaseOrders();
      setError(null);
      setSuccess('PO sent to supplier');
    } catch (err) {
      console.error('Error sending PO:', err);
      setError(err.response?.data?.detail || 'Failed to send PO');
    } finally {
      setActionLoading(false);
    }
  };

  const openAckDialog = (po, action) => {
    setSelectedPO(po);
    setAckAction(action);
    setAckNotes('');
    setAckDialogOpen(true);
  };

  const handleAcknowledge = async () => {
    if (!selectedPO || !ackAction) return;

    try {
      setActionLoading(true);
      await api.post(`/purchase-orders/${selectedPO.id}/${ackAction}`, {
        notes: ackNotes,
        acknowledged_by: 'Supplier',
        acknowledged_at: new Date().toISOString(),
      });
      await fetchPurchaseOrders();
      setAckDialogOpen(false);
      setError(null);
      setSuccess(`PO ${ackAction === 'acknowledge' ? 'acknowledged' : 'confirmed'} successfully`);
    } catch (err) {
      console.error(`Error ${ackAction}ing PO:`, err);
      setError(err.response?.data?.detail || `Failed to ${ackAction} PO`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeletePO = async () => {
    if (!poToDelete) return;

    try {
      setActionLoading(true);
      await api.delete(`/purchase-orders/${poToDelete.id}`);
      await fetchPurchaseOrders();
      setDeleteDialogOpen(false);
      setPoToDelete(null);
      setError(null);
    } catch (err) {
      console.error('Error deleting PO:', err);
      setError(err.response?.data?.detail || 'Failed to delete PO');
    } finally {
      setActionLoading(false);
    }
  };

  const openDeleteDialog = (po) => {
    setPoToDelete(po);
    setDeleteDialogOpen(true);
  };

  const getStatusVariant = (status) => {
    const variants = {
      DRAFT: 'secondary',
      APPROVED: 'info',
      SENT: 'warning',
      ACKNOWLEDGED: 'secondary',
      CONFIRMED: 'success',
      SHIPPED: 'default',
      RECEIVED: 'success',
      CANCELLED: 'destructive',
    };
    return variants[status] || 'secondary';
  };

  const getWorkflowStep = (status) => {
    const steps = ['DRAFT', 'APPROVED', 'SENT', 'ACKNOWLEDGED', 'CONFIRMED', 'SHIPPED', 'RECEIVED'];
    return steps.indexOf(status);
  };

  const workflowSteps = [
    { label: 'Draft', icon: Clock },
    { label: 'Approved', icon: Check },
    { label: 'Sent to Supplier', icon: Send },
    { label: 'Acknowledged', icon: ThumbsUp },
    { label: 'Confirmed', icon: CheckCircle },
    { label: 'Shipped', icon: Truck },
    { label: 'Received', icon: Package },
  ];

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(amount);
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString();
  };

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Purchase Orders</h1>
        <div className="flex gap-3">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-48">
              <SelectValue placeholder="Status Filter" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              <SelectItem value="DRAFT">Draft</SelectItem>
              <SelectItem value="APPROVED">Approved</SelectItem>
              <SelectItem value="SENT">Sent to Supplier</SelectItem>
              <SelectItem value="ACKNOWLEDGED">Acknowledged</SelectItem>
              <SelectItem value="CONFIRMED">Confirmed</SelectItem>
              <SelectItem value="SHIPPED">Shipped</SelectItem>
              <SelectItem value="RECEIVED">Received</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            onClick={fetchPurchaseOrders}
            disabled={loading}
            leftIcon={<RefreshCw className="h-4 w-4" />}
          >
            Refresh
          </Button>
          <Button
            onClick={() => navigate('/planning/purchase-orders/create')}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            Create PO
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

      <Card>
        {loading ? (
          <div className="flex justify-center p-8">
            <Spinner size="lg" />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>PO Number</TableHead>
                <TableHead>Vendor ID</TableHead>
                <TableHead>Destination Site</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Ack Status</TableHead>
                <TableHead className="text-right">Total Amount</TableHead>
                <TableHead>Order Date</TableHead>
                <TableHead>Expected Delivery</TableHead>
                <TableHead className="text-center">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {purchaseOrders.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-8">
                    <p className="text-muted-foreground">No purchase orders found</p>
                  </TableCell>
                </TableRow>
              ) : (
                purchaseOrders.map((po) => (
                  <TableRow key={po.id}>
                    <TableCell>
                      <span className="font-medium">{po.po_number}</span>
                    </TableCell>
                    <TableCell>{formatSupplier(po.vendor_id, po.vendor_name)}</TableCell>
                    <TableCell>{po.destination_site_name}</TableCell>
                    <TableCell>
                      <Badge variant={getStatusVariant(po.status)}>{po.status}</Badge>
                    </TableCell>
                    <TableCell>
                      {po.status === 'SENT' && (
                        <Badge variant="warning" className="flex items-center gap-1 w-fit">
                          <Clock className="h-3 w-3" />
                          Awaiting Ack
                        </Badge>
                      )}
                      {po.status === 'ACKNOWLEDGED' && (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Badge variant="info" className="flex items-center gap-1 w-fit">
                                <ThumbsUp className="h-3 w-3" />
                                Acknowledged
                              </Badge>
                            </TooltipTrigger>
                            <TooltipContent>Acknowledged: {formatDate(po.acknowledged_at)}</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )}
                      {['CONFIRMED', 'SHIPPED', 'RECEIVED'].includes(po.status) && (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Badge variant="success" className="flex items-center gap-1 w-fit">
                                <CheckCircle className="h-3 w-3" />
                                Confirmed
                              </Badge>
                            </TooltipTrigger>
                            <TooltipContent>Confirmed: {formatDate(po.confirmed_at)}</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )}
                      {['DRAFT', 'APPROVED'].includes(po.status) && (
                        <Badge variant="outline">N/A</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right">{formatCurrency(po.total_amount)}</TableCell>
                    <TableCell>{formatDate(po.order_date)}</TableCell>
                    <TableCell>{formatDate(po.expected_delivery_date)}</TableCell>
                    <TableCell>
                      <div className="flex justify-center gap-1">
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => fetchPODetail(po.id)}
                                disabled={actionLoading}
                              >
                                <Eye className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>View Details</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                        {po.status === 'DRAFT' && (
                          <>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => handleApprovePO(po.id)}
                                    disabled={actionLoading}
                                  >
                                    <Check className="h-4 w-4 text-green-600" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Approve</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => openDeleteDialog(po)}
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
                        {po.status === 'APPROVED' && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleSendPO(po.id)}
                                  disabled={actionLoading}
                                >
                                  <Send className="h-4 w-4 text-primary" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Send to Supplier</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                        {po.status === 'SENT' && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => openAckDialog(po, 'acknowledge')}
                                  disabled={actionLoading}
                                >
                                  <ThumbsUp className="h-4 w-4 text-blue-600" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Record Acknowledgment</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                        {po.status === 'ACKNOWLEDGED' && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => openAckDialog(po, 'confirm')}
                                  disabled={actionLoading}
                                >
                                  <CheckCircle className="h-4 w-4 text-green-600" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Confirm Order</TooltipContent>
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
        )}
      </Card>

      {/* Detail Dialog */}
      <Modal
        open={detailDialogOpen}
        onClose={() => setDetailDialogOpen(false)}
        title="Purchase Order Details"
        size="lg"
      >
        {selectedPO && (
          <div className="space-y-4">
            {/* Workflow Progress */}
            <Card variant="outlined">
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground mb-3">Order Workflow Progress</p>
                <div className="flex items-center justify-between">
                  {workflowSteps.map((step, index) => {
                    const StepIcon = step.icon;
                    const isActive = index === getWorkflowStep(selectedPO.status);
                    const isCompleted = index < getWorkflowStep(selectedPO.status);
                    return (
                      <div key={step.label} className="flex flex-col items-center flex-1">
                        <div className={`
                          w-8 h-8 rounded-full flex items-center justify-center mb-1
                          ${isActive ? 'bg-primary text-primary-foreground' :
                            isCompleted ? 'bg-green-600 text-white' : 'bg-muted text-muted-foreground'}
                        `}>
                          <StepIcon className="h-4 w-4" />
                        </div>
                        <span className={`text-xs text-center ${isActive ? 'font-medium' : ''}`}>
                          {step.label}
                        </span>
                        {index < workflowSteps.length - 1 && (
                          <div className={`
                            absolute h-0.5 w-full top-4 left-1/2
                            ${isCompleted ? 'bg-green-600' : 'bg-muted'}
                          `} />
                        )}
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">PO Number</p>
                <p className="font-medium">{selectedPO.po_number}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <Badge variant={getStatusVariant(selectedPO.status)}>{selectedPO.status}</Badge>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Vendor</p>
                <p className="font-medium">{formatSupplier(selectedPO.vendor_id, selectedPO.vendor_name)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Order Date</p>
                <p className="font-medium">{formatDate(selectedPO.order_date)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Supplier Site</p>
                <p className="font-medium">{selectedPO.supplier_site_name}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Destination Site</p>
                <p className="font-medium">{selectedPO.destination_site_name}</p>
              </div>
              <div className="col-span-2">
                <p className="text-sm text-muted-foreground">Total Amount</p>
                <p className="text-xl font-semibold">{formatCurrency(selectedPO.total_amount)}</p>
              </div>
              {selectedPO.notes && (
                <div className="col-span-2">
                  <p className="text-sm text-muted-foreground">Notes</p>
                  <p className="font-medium">{selectedPO.notes}</p>
                </div>
              )}
            </div>

            <div>
              <h4 className="font-medium mb-3">Line Items</h4>
              <Card variant="outlined">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Line #</TableHead>
                      <TableHead>Product</TableHead>
                      <TableHead className="text-right">Quantity</TableHead>
                      <TableHead className="text-right">Unit Price</TableHead>
                      <TableHead className="text-right">Total</TableHead>
                      <TableHead>Delivery Date</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {selectedPO.line_items.map((item) => (
                      <TableRow key={item.line_number}>
                        <TableCell>{item.line_number}</TableCell>
                        <TableCell>
                          {formatProduct(item.product_id, item.product_name)}
                        </TableCell>
                        <TableCell className="text-right">{item.quantity}</TableCell>
                        <TableCell className="text-right">{formatCurrency(item.unit_price)}</TableCell>
                        <TableCell className="text-right">{formatCurrency(item.line_total)}</TableCell>
                        <TableCell>{formatDate(item.requested_delivery_date)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            </div>

            {/* Conversation thread */}
            <Conversation
              entityType="purchase_order"
              entityId={selectedPO.id}
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
        title="Delete Purchase Order"
        size="sm"
      >
        <p className="text-sm">
          Are you sure you want to delete PO {poToDelete?.po_number}? This action cannot be undone.
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
            onClick={handleDeletePO}
            disabled={actionLoading}
          >
            {actionLoading ? <Spinner size="sm" /> : 'Delete'}
          </Button>
        </div>
      </Modal>

      {/* Acknowledgment/Confirmation Dialog */}
      <Modal
        open={ackDialogOpen}
        onClose={() => setAckDialogOpen(false)}
        title={ackAction === 'acknowledge' ? 'Record Supplier Acknowledgment' : 'Confirm Order'}
        size="md"
      >
        <div className="space-y-4">
          <Alert variant="info">
            {ackAction === 'acknowledge' ? (
              <>
                Recording supplier acknowledgment for <strong>PO {selectedPO?.po_number}</strong>.
                This indicates the supplier has received and acknowledged the order.
              </>
            ) : (
              <>
                Confirming order for <strong>PO {selectedPO?.po_number}</strong>.
                This indicates the supplier has confirmed they can fulfill the order as specified.
              </>
            )}
          </Alert>
          <div>
            <Label htmlFor="ackNotes">Notes (optional)</Label>
            <Textarea
              id="ackNotes"
              value={ackNotes}
              onChange={(e) => setAckNotes(e.target.value)}
              rows={3}
              placeholder={
                ackAction === 'acknowledge'
                  ? 'e.g., Supplier confirmed via email on 01/15/2026'
                  : 'e.g., Confirmed delivery date: 01/25/2026, all items available'
              }
              className="mt-1"
            />
          </div>
          <div>
            <p className="text-sm text-muted-foreground mb-2">What happens next:</p>
            <p className="text-sm">
              {ackAction === 'acknowledge' ? (
                <>
                  The PO status will change to <Badge variant="info" className="mx-1">ACKNOWLEDGED</Badge>.
                  You can then confirm the order once the supplier provides final confirmation.
                </>
              ) : (
                <>
                  The PO status will change to <Badge variant="success" className="mx-1">CONFIRMED</Badge>.
                  The order is now locked and awaiting shipment from the supplier.
                </>
              )}
            </p>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button
            variant="outline"
            onClick={() => setAckDialogOpen(false)}
            disabled={actionLoading}
          >
            Cancel
          </Button>
          <Button
            variant={ackAction === 'acknowledge' ? 'default' : 'default'}
            onClick={handleAcknowledge}
            disabled={actionLoading}
            leftIcon={ackAction === 'acknowledge' ? <ThumbsUp className="h-4 w-4" /> : <CheckCircle className="h-4 w-4" />}
          >
            {actionLoading ? (
              <Spinner size="sm" />
            ) : ackAction === 'acknowledge' ? (
              'Record Acknowledgment'
            ) : (
              'Confirm Order'
            )}
          </Button>
        </div>
      </Modal>
    </div>
  );
};

export default PurchaseOrders;
