/**
 * Invoices Page with 3-Way Matching
 *
 * Features:
 * - Invoice list with status filtering
 * - Invoice entry form
 * - 3-way match execution (PO, GR, Invoice)
 * - Discrepancy resolution workflow
 * - Match history and audit trail
 */

import React, { useState, useEffect, useCallback } from 'react';
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../../components/ui/tooltip';
import {
  Eye,
  Check,
  CheckCircle,
  XCircle,
  RefreshCw,
  Plus,
  CreditCard,
  AlertTriangle,
  ArrowLeftRight,
} from 'lucide-react';
import { api } from '../../services/api';
import { Conversation } from '@azirella-ltd/autonomy-frontend';

// Match status colors
const getMatchStatusVariant = (status) => {
  const variants = {
    MATCHED: 'success',
    PARTIAL_MATCH: 'warning',
    QUANTITY_MISMATCH: 'destructive',
    PRICE_MISMATCH: 'destructive',
    UNMATCHED: 'secondary',
    PENDING: 'info',
  };
  return variants[status] || 'secondary';
};

// Invoice status colors
const getStatusVariant = (status) => {
  const variants = {
    RECEIVED: 'info',
    VALIDATED: 'default',
    APPROVED: 'success',
    REJECTED: 'destructive',
    PAID: 'success',
    CANCELLED: 'secondary',
  };
  return variants[status] || 'secondary';
};

const formatCurrency = (amount, currency = 'USD') => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency,
  }).format(amount || 0);
};

const formatDate = (dateStr) => {
  if (!dateStr) return 'N/A';
  return new Date(dateStr).toLocaleDateString();
};

const Invoices = () => {
  const { formatSupplier, formatProduct } = useDisplayPreferences();
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [matchStatusFilter, setMatchStatusFilter] = useState('all');
  const [selectedInvoice, setSelectedInvoice] = useState(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [matchDialogOpen, setMatchDialogOpen] = useState(false);
  const [resolveDialogOpen, setResolveDialogOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [tabValue, setTabValue] = useState('details');

  // Create invoice form state
  const [newInvoice, setNewInvoice] = useState({
    vendor_invoice_number: '',
    vendor_id: '',
    vendor_name: '',
    po_id: '',
    invoice_date: new Date().toISOString().split('T')[0],
    due_date: '',
    tax_amount: 0,
    shipping_amount: 0,
    discount_amount: 0,
    payment_terms: 'NET30',
    notes: '',
    line_items: [
      { line_number: 1, product_id: '', description: '', invoiced_qty: 0, unit_price: 0 },
    ],
  });

  // Match settings
  const [matchSettings, setMatchSettings] = useState({
    po_id: '',
    gr_id: '',
    qty_tolerance_pct: 2,
    price_tolerance_pct: 1,
  });

  // Resolution state
  const [resolution, setResolution] = useState({
    resolution: 'ACCEPT',
    notes: '',
    adjusted_amount: null,
  });

  // Match result state
  const [matchResult, setMatchResult] = useState(null);

  const fetchInvoices = useCallback(async () => {
    try {
      setLoading(true);
      const params = {};
      if (statusFilter && statusFilter !== 'all') params.status_filter = statusFilter;
      if (matchStatusFilter && matchStatusFilter !== 'all') params.match_status_filter = matchStatusFilter;

      const response = await api.get('/invoices', { params });
      setInvoices(response.data);
      setError(null);
    } catch (err) {
      console.error('Error fetching invoices:', err);
      setError('Failed to fetch invoices');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, matchStatusFilter]);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  const fetchInvoiceDetail = async (invoiceId) => {
    try {
      setActionLoading(true);
      const response = await api.get(`/invoices/${invoiceId}`);
      setSelectedInvoice(response.data);
      setDetailDialogOpen(true);
    } catch (err) {
      console.error('Error fetching invoice detail:', err);
      setError('Failed to fetch invoice details');
    } finally {
      setActionLoading(false);
    }
  };

  const handleCreateInvoice = async () => {
    try {
      setActionLoading(true);
      await api.post('/invoices', {
        ...newInvoice,
        po_id: newInvoice.po_id ? parseInt(newInvoice.po_id) : null,
      });
      setSuccess('Invoice created successfully');
      setCreateDialogOpen(false);
      setNewInvoice({
        vendor_invoice_number: '',
        vendor_id: '',
        vendor_name: '',
        po_id: '',
        invoice_date: new Date().toISOString().split('T')[0],
        due_date: '',
        tax_amount: 0,
        shipping_amount: 0,
        discount_amount: 0,
        payment_terms: 'NET30',
        notes: '',
        line_items: [
          { line_number: 1, product_id: '', description: '', invoiced_qty: 0, unit_price: 0 },
        ],
      });
      fetchInvoices();
    } catch (err) {
      console.error('Error creating invoice:', err);
      setError(err.response?.data?.detail || 'Failed to create invoice');
    } finally {
      setActionLoading(false);
    }
  };

  const handlePerformMatch = async () => {
    if (!selectedInvoice) return;

    try {
      setActionLoading(true);
      const response = await api.post(`/invoices/${selectedInvoice.id}/match`, {
        po_id: matchSettings.po_id ? parseInt(matchSettings.po_id) : null,
        gr_id: matchSettings.gr_id ? parseInt(matchSettings.gr_id) : null,
        qty_tolerance_pct: matchSettings.qty_tolerance_pct,
        price_tolerance_pct: matchSettings.price_tolerance_pct,
      });
      setMatchResult(response.data);
      setSuccess(`Match completed: ${response.data.overall_status} (Score: ${response.data.match_score.toFixed(1)}%)`);
      fetchInvoices();
      const updatedInvoice = await api.get(`/invoices/${selectedInvoice.id}`);
      setSelectedInvoice(updatedInvoice.data);
    } catch (err) {
      console.error('Error performing match:', err);
      setError(err.response?.data?.detail || 'Failed to perform 3-way match');
    } finally {
      setActionLoading(false);
      setMatchDialogOpen(false);
    }
  };

  const handleResolveDiscrepancy = async () => {
    if (!selectedInvoice) return;

    try {
      setActionLoading(true);
      await api.post(`/invoices/${selectedInvoice.id}/resolve`, resolution);
      setSuccess('Discrepancy resolved successfully');
      setResolveDialogOpen(false);
      fetchInvoices();
      const updatedInvoice = await api.get(`/invoices/${selectedInvoice.id}`);
      setSelectedInvoice(updatedInvoice.data);
    } catch (err) {
      console.error('Error resolving discrepancy:', err);
      setError(err.response?.data?.detail || 'Failed to resolve discrepancy');
    } finally {
      setActionLoading(false);
    }
  };

  const handleApproveInvoice = async (invoiceId) => {
    try {
      setActionLoading(true);
      await api.post(`/invoices/${invoiceId}/approve`);
      setSuccess('Invoice approved for payment');
      fetchInvoices();
      if (selectedInvoice?.id === invoiceId) {
        const updatedInvoice = await api.get(`/invoices/${invoiceId}`);
        setSelectedInvoice(updatedInvoice.data);
      }
    } catch (err) {
      console.error('Error approving invoice:', err);
      setError(err.response?.data?.detail || 'Failed to approve invoice');
    } finally {
      setActionLoading(false);
    }
  };

  const addLineItem = () => {
    setNewInvoice({
      ...newInvoice,
      line_items: [
        ...newInvoice.line_items,
        {
          line_number: newInvoice.line_items.length + 1,
          product_id: '',
          description: '',
          invoiced_qty: 0,
          unit_price: 0,
        },
      ],
    });
  };

  const updateLineItem = (index, field, value) => {
    const updatedItems = [...newInvoice.line_items];
    updatedItems[index] = { ...updatedItems[index], [field]: value };
    setNewInvoice({ ...newInvoice, line_items: updatedItems });
  };

  const calculateTotal = () => {
    const subtotal = newInvoice.line_items.reduce(
      (sum, item) => sum + item.invoiced_qty * item.unit_price,
      0
    );
    return subtotal + newInvoice.tax_amount + newInvoice.shipping_amount - newInvoice.discount_amount;
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Invoices & 3-Way Matching</h1>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={fetchInvoices}
            leftIcon={<RefreshCw className="h-4 w-4" />}
          >
            Refresh
          </Button>
          <Button
            onClick={() => setCreateDialogOpen(true)}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            New Invoice
          </Button>
        </div>
      </div>

      {/* Alerts */}
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

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="pt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>Status</Label>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder="All Statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Statuses</SelectItem>
                  <SelectItem value="RECEIVED">Received</SelectItem>
                  <SelectItem value="VALIDATED">Validated</SelectItem>
                  <SelectItem value="APPROVED">Approved</SelectItem>
                  <SelectItem value="REJECTED">Rejected</SelectItem>
                  <SelectItem value="PAID">Paid</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Match Status</Label>
              <Select value={matchStatusFilter} onValueChange={setMatchStatusFilter}>
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder="All Match Statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Match Statuses</SelectItem>
                  <SelectItem value="PENDING">Pending</SelectItem>
                  <SelectItem value="MATCHED">Matched</SelectItem>
                  <SelectItem value="PARTIAL_MATCH">Partial Match</SelectItem>
                  <SelectItem value="QUANTITY_MISMATCH">Quantity Mismatch</SelectItem>
                  <SelectItem value="PRICE_MISMATCH">Price Mismatch</SelectItem>
                  <SelectItem value="UNMATCHED">Unmatched</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Invoice List */}
      <Card>
        {loading ? (
          <div className="flex justify-center p-8">
            <Spinner size="lg" />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Invoice #</TableHead>
                <TableHead>Vendor</TableHead>
                <TableHead>Invoice Date</TableHead>
                <TableHead>Due Date</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Match Status</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-center">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invoices.map((invoice) => (
                <TableRow key={invoice.id}>
                  <TableCell className="font-medium">{invoice.invoice_number}</TableCell>
                  <TableCell>
                    <div>
                      <p className="text-sm">{formatSupplier(invoice.vendor_id, invoice.vendor_name)}</p>
                      <p className="text-xs text-muted-foreground">{invoice.vendor_invoice_number}</p>
                    </div>
                  </TableCell>
                  <TableCell>{formatDate(invoice.invoice_date)}</TableCell>
                  <TableCell>{formatDate(invoice.due_date)}</TableCell>
                  <TableCell className="text-right">{formatCurrency(invoice.total_amount)}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      {invoice.has_discrepancy && <AlertTriangle className="h-3 w-3 text-amber-500" />}
                      <Badge variant={getMatchStatusVariant(invoice.match_status)}>
                        {invoice.match_status}
                      </Badge>
                    </div>
                    {invoice.match_score > 0 && (
                      <p className="text-xs text-muted-foreground">Score: {invoice.match_score.toFixed(0)}%</p>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={getStatusVariant(invoice.status)}>{invoice.status}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-center gap-1">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="sm" onClick={() => fetchInvoiceDetail(invoice.id)}>
                              <Eye className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>View Details</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                      {invoice.match_status === 'PENDING' && (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  fetchInvoiceDetail(invoice.id);
                                  setMatchDialogOpen(true);
                                }}
                              >
                                <ArrowLeftRight className="h-4 w-4 text-primary" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Perform 3-Way Match</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )}
                      {invoice.status === 'VALIDATED' && (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleApproveInvoice(invoice.id)}
                              >
                                <CheckCircle className="h-4 w-4 text-green-600" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Approve for Payment</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {invoices.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-8">
                    <p className="text-muted-foreground">No invoices found</p>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </Card>

      {/* Invoice Detail Dialog */}
      <Modal
        open={detailDialogOpen}
        onClose={() => setDetailDialogOpen(false)}
        title={`Invoice Details - ${selectedInvoice?.invoice_number || ''}`}
        size="lg"
      >
        {selectedInvoice && (
          <div className="space-y-4">
            <Tabs value={tabValue} onValueChange={setTabValue}>
              <TabsList>
                <TabsTrigger value="details">Details</TabsTrigger>
                <TabsTrigger value="items">Line Items</TabsTrigger>
                <TabsTrigger value="match">Match Results</TabsTrigger>
                <TabsTrigger value="comments">Comments</TabsTrigger>
              </TabsList>

              <TabsContent value="details" className="mt-4">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Vendor</p>
                    <p className="font-medium">{formatSupplier(selectedInvoice.vendor_id, selectedInvoice.vendor_name)}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Vendor Invoice #</p>
                    <p className="font-medium">{selectedInvoice.vendor_invoice_number}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Invoice Date</p>
                    <p className="font-medium">{formatDate(selectedInvoice.invoice_date)}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Due Date</p>
                    <p className="font-medium">{formatDate(selectedInvoice.due_date)}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Subtotal</p>
                    <p className="font-medium">{formatCurrency(selectedInvoice.subtotal)}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Tax</p>
                    <p className="font-medium">{formatCurrency(selectedInvoice.tax_amount)}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Shipping</p>
                    <p className="font-medium">{formatCurrency(selectedInvoice.shipping_amount)}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Total</p>
                    <p className="text-xl font-semibold">{formatCurrency(selectedInvoice.total_amount)}</p>
                  </div>
                </div>

                <div className="border-t my-4" />

                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Match Status</p>
                    <Badge variant={getMatchStatusVariant(selectedInvoice.match_status)}>
                      {selectedInvoice.match_status}
                    </Badge>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Invoice Status</p>
                    <Badge variant={getStatusVariant(selectedInvoice.status)}>
                      {selectedInvoice.status}
                    </Badge>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Match Score</p>
                    <div className="flex items-center gap-2">
                      <Progress
                        value={selectedInvoice.match_score}
                        className={`flex-1 h-2 ${
                          selectedInvoice.match_score >= 80 ? '[&>div]:bg-green-500' :
                          selectedInvoice.match_score >= 50 ? '[&>div]:bg-amber-500' :
                          '[&>div]:bg-destructive'
                        }`}
                      />
                      <span className="text-sm">{selectedInvoice.match_score.toFixed(0)}%</span>
                    </div>
                  </div>
                </div>

                {selectedInvoice.has_discrepancy && (
                  <Alert variant="warning" className="mt-4">
                    Discrepancy detected: {formatCurrency(selectedInvoice.discrepancy_amount)}
                  </Alert>
                )}
              </TabsContent>

              <TabsContent value="items" className="mt-4">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Line #</TableHead>
                      <TableHead>Product</TableHead>
                      <TableHead className="text-right">Invoiced Qty</TableHead>
                      <TableHead className="text-right">Received Qty</TableHead>
                      <TableHead className="text-right">Unit Price</TableHead>
                      <TableHead className="text-right">PO Price</TableHead>
                      <TableHead className="text-right">Line Total</TableHead>
                      <TableHead>Match</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {selectedInvoice.line_items?.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell>{item.line_number}</TableCell>
                        <TableCell>
                          <p className="text-sm">{formatProduct(item.product_id)}</p>
                          {item.description && (
                            <p className="text-xs text-muted-foreground">{item.description}</p>
                          )}
                        </TableCell>
                        <TableCell className="text-right">{item.invoiced_qty}</TableCell>
                        <TableCell className="text-right">
                          {item.received_qty ?? 'N/A'}
                          {item.qty_variance !== 0 && (
                            <p className={`text-xs ${item.qty_variance > 0 ? 'text-destructive' : 'text-amber-500'}`}>
                              {item.qty_variance > 0 ? '+' : ''}{item.qty_variance}
                            </p>
                          )}
                        </TableCell>
                        <TableCell className="text-right">{formatCurrency(item.unit_price)}</TableCell>
                        <TableCell className="text-right">
                          {item.po_unit_price ? formatCurrency(item.po_unit_price) : 'N/A'}
                          {item.price_variance !== 0 && (
                            <p className={`text-xs ${item.price_variance > 0 ? 'text-destructive' : 'text-green-600'}`}>
                              {item.price_variance > 0 ? '+' : ''}{formatCurrency(item.price_variance)}
                            </p>
                          )}
                        </TableCell>
                        <TableCell className="text-right">{formatCurrency(item.line_total)}</TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              item.match_status === 'MATCHED' ? 'success' :
                              item.match_status === 'PENDING' ? 'info' : 'destructive'
                            }
                          >
                            {item.match_status}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TabsContent>

              <TabsContent value="match" className="mt-4">
                {matchResult ? (
                  <Card variant="outlined">
                    <CardContent className="pt-4">
                      <h4 className="font-medium mb-4">Latest Match Result</h4>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                          <p className="text-sm text-muted-foreground">Status</p>
                          <Badge variant={getMatchStatusVariant(matchResult.overall_status)}>
                            {matchResult.overall_status}
                          </Badge>
                        </div>
                        <div>
                          <p className="text-sm text-muted-foreground">Score</p>
                          <p className="text-xl font-semibold">{matchResult.match_score.toFixed(1)}%</p>
                        </div>
                        <div>
                          <p className="text-sm text-muted-foreground">Qty Match %</p>
                          <p className="font-medium">{matchResult.qty_match_pct.toFixed(1)}%</p>
                        </div>
                        <div>
                          <p className="text-sm text-muted-foreground">Price Match %</p>
                          <p className="font-medium">{matchResult.price_match_pct.toFixed(1)}%</p>
                        </div>
                        <div>
                          <p className="text-sm text-muted-foreground">PO Total</p>
                          <p className="font-medium">{formatCurrency(matchResult.po_total)}</p>
                        </div>
                        <div>
                          <p className="text-sm text-muted-foreground">Invoice Total</p>
                          <p className="font-medium">{formatCurrency(matchResult.invoice_total)}</p>
                        </div>
                        <div>
                          <p className="text-sm text-muted-foreground">Variance</p>
                          <p className={`font-medium ${matchResult.total_variance > 0 ? 'text-destructive' : 'text-green-600'}`}>
                            {formatCurrency(matchResult.total_variance)}
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-muted-foreground">Exceptions</p>
                          <p className="font-medium">{matchResult.exceptions_count}</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ) : (
                  <Alert variant="info">
                    No match has been performed yet. Click "Perform 3-Way Match" to match this invoice.
                  </Alert>
                )}
              </TabsContent>

              <TabsContent value="comments" className="mt-4">
                <Conversation
                  entityType="invoice"
                  entityId={selectedInvoice.id}
                  title="Invoice Comments"
                  collapsible={false}
                  defaultExpanded={true}
                />
              </TabsContent>
            </Tabs>
          </div>
        )}
        <div className="flex justify-end gap-2 mt-6">
          {selectedInvoice?.match_status === 'PENDING' && (
            <Button
              variant="outline"
              onClick={() => setMatchDialogOpen(true)}
              leftIcon={<ArrowLeftRight className="h-4 w-4" />}
            >
              Perform 3-Way Match
            </Button>
          )}
          {selectedInvoice?.has_discrepancy && selectedInvoice?.status !== 'APPROVED' && (
            <Button
              variant="outline"
              onClick={() => setResolveDialogOpen(true)}
              leftIcon={<AlertTriangle className="h-4 w-4" />}
            >
              Resolve Discrepancy
            </Button>
          )}
          {selectedInvoice?.status === 'VALIDATED' && (
            <Button
              onClick={() => handleApproveInvoice(selectedInvoice.id)}
              leftIcon={<CheckCircle className="h-4 w-4" />}
            >
              Approve for Payment
            </Button>
          )}
          <Button variant="outline" onClick={() => setDetailDialogOpen(false)}>Close</Button>
        </div>
      </Modal>

      {/* Create Invoice Dialog */}
      <Modal
        open={createDialogOpen}
        onClose={() => setCreateDialogOpen(false)}
        title="Create New Invoice"
        size="lg"
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>Vendor Invoice # *</Label>
              <Input
                value={newInvoice.vendor_invoice_number}
                onChange={(e) => setNewInvoice({ ...newInvoice, vendor_invoice_number: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label>Vendor ID *</Label>
              <Input
                value={newInvoice.vendor_id}
                onChange={(e) => setNewInvoice({ ...newInvoice, vendor_id: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label>Vendor Name</Label>
              <Input
                value={newInvoice.vendor_name}
                onChange={(e) => setNewInvoice({ ...newInvoice, vendor_name: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label>Link to PO ID (optional)</Label>
              <Input
                type="number"
                value={newInvoice.po_id}
                onChange={(e) => setNewInvoice({ ...newInvoice, po_id: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label>Invoice Date *</Label>
              <Input
                type="date"
                value={newInvoice.invoice_date}
                onChange={(e) => setNewInvoice({ ...newInvoice, invoice_date: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label>Due Date</Label>
              <Input
                type="date"
                value={newInvoice.due_date}
                onChange={(e) => setNewInvoice({ ...newInvoice, due_date: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label>Payment Terms</Label>
              <Select
                value={newInvoice.payment_terms}
                onValueChange={(value) => setNewInvoice({ ...newInvoice, payment_terms: value })}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="NET15">Net 15</SelectItem>
                  <SelectItem value="NET30">Net 30</SelectItem>
                  <SelectItem value="NET45">Net 45</SelectItem>
                  <SelectItem value="NET60">Net 60</SelectItem>
                  <SelectItem value="DUE_ON_RECEIPT">Due on Receipt</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="border-t pt-4">
            <h4 className="font-medium mb-3">Line Items</h4>
            {newInvoice.line_items.map((item, index) => (
              <div key={index} className="grid grid-cols-5 gap-2 mb-2">
                <Input
                  placeholder="Product ID"
                  value={item.product_id}
                  onChange={(e) => updateLineItem(index, 'product_id', e.target.value)}
                />
                <Input
                  placeholder="Description"
                  value={item.description}
                  onChange={(e) => updateLineItem(index, 'description', e.target.value)}
                  className="col-span-2"
                />
                <Input
                  type="number"
                  placeholder="Qty"
                  value={item.invoiced_qty}
                  onChange={(e) => updateLineItem(index, 'invoiced_qty', parseFloat(e.target.value) || 0)}
                />
                <Input
                  type="number"
                  placeholder="Unit Price"
                  value={item.unit_price}
                  onChange={(e) => updateLineItem(index, 'unit_price', parseFloat(e.target.value) || 0)}
                />
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={addLineItem}>
              + Add Line Item
            </Button>
          </div>

          <div className="border-t pt-4">
            <div className="grid grid-cols-4 gap-4">
              <div>
                <Label>Tax Amount</Label>
                <Input
                  type="number"
                  value={newInvoice.tax_amount}
                  onChange={(e) => setNewInvoice({ ...newInvoice, tax_amount: parseFloat(e.target.value) || 0 })}
                  className="mt-1"
                />
              </div>
              <div>
                <Label>Shipping Amount</Label>
                <Input
                  type="number"
                  value={newInvoice.shipping_amount}
                  onChange={(e) => setNewInvoice({ ...newInvoice, shipping_amount: parseFloat(e.target.value) || 0 })}
                  className="mt-1"
                />
              </div>
              <div>
                <Label>Discount Amount</Label>
                <Input
                  type="number"
                  value={newInvoice.discount_amount}
                  onChange={(e) => setNewInvoice({ ...newInvoice, discount_amount: parseFloat(e.target.value) || 0 })}
                  className="mt-1"
                />
              </div>
              <div className="flex items-end">
                <p className="text-xl font-semibold">Total: {formatCurrency(calculateTotal())}</p>
              </div>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handleCreateInvoice}
            disabled={actionLoading || !newInvoice.vendor_invoice_number || !newInvoice.vendor_id}
          >
            {actionLoading ? <Spinner size="sm" /> : 'Create Invoice'}
          </Button>
        </div>
      </Modal>

      {/* Match Dialog */}
      <Modal
        open={matchDialogOpen}
        onClose={() => setMatchDialogOpen(false)}
        title="Perform 3-Way Match"
        size="md"
      >
        <div className="space-y-4">
          <Alert variant="info">
            Matching invoice against Purchase Order and Goods Receipt to verify quantities and prices.
          </Alert>
          <div>
            <Label>PO ID</Label>
            <Input
              type="number"
              value={matchSettings.po_id || selectedInvoice?.po_id || ''}
              onChange={(e) => setMatchSettings({ ...matchSettings, po_id: e.target.value })}
              placeholder="Leave blank to use invoice's linked PO"
              className="mt-1"
            />
          </div>
          <div>
            <Label>Goods Receipt ID (optional)</Label>
            <Input
              type="number"
              value={matchSettings.gr_id}
              onChange={(e) => setMatchSettings({ ...matchSettings, gr_id: e.target.value })}
              placeholder="Leave blank to use latest GR for PO"
              className="mt-1"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Qty Tolerance %</Label>
              <Input
                type="number"
                value={matchSettings.qty_tolerance_pct}
                onChange={(e) => setMatchSettings({ ...matchSettings, qty_tolerance_pct: parseFloat(e.target.value) || 0 })}
                min={0}
                max={100}
                step={0.5}
                className="mt-1"
              />
            </div>
            <div>
              <Label>Price Tolerance %</Label>
              <Input
                type="number"
                value={matchSettings.price_tolerance_pct}
                onChange={(e) => setMatchSettings({ ...matchSettings, price_tolerance_pct: parseFloat(e.target.value) || 0 })}
                min={0}
                max={100}
                step={0.5}
                className="mt-1"
              />
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setMatchDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handlePerformMatch}
            disabled={actionLoading}
            leftIcon={actionLoading ? <Spinner size="sm" /> : <Check className="h-4 w-4" />}
          >
            Execute Match
          </Button>
        </div>
      </Modal>

      {/* Resolve Discrepancy Dialog */}
      <Modal
        open={resolveDialogOpen}
        onClose={() => setResolveDialogOpen(false)}
        title="Resolve Discrepancy"
        size="md"
      >
        <div className="space-y-4">
          {selectedInvoice?.has_discrepancy && (
            <Alert variant="warning">
              Discrepancy Amount: {formatCurrency(selectedInvoice.discrepancy_amount)}
            </Alert>
          )}
          <div>
            <Label>Resolution</Label>
            <Select
              value={resolution.resolution}
              onValueChange={(value) => setResolution({ ...resolution, resolution: value })}
            >
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ACCEPT">Accept - Pay full invoice amount</SelectItem>
                <SelectItem value="REJECT">Reject - Return to vendor</SelectItem>
                <SelectItem value="DEBIT_MEMO">Debit Memo - Reduce payment</SelectItem>
                <SelectItem value="CREDIT_MEMO">Credit Memo - Future credit</SelectItem>
                <SelectItem value="ADJUST">Adjust - Change invoice amount</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {resolution.resolution === 'ADJUST' && (
            <div>
              <Label>Adjusted Amount</Label>
              <Input
                type="number"
                value={resolution.adjusted_amount || ''}
                onChange={(e) => setResolution({ ...resolution, adjusted_amount: parseFloat(e.target.value) || null })}
                className="mt-1"
              />
            </div>
          )}
          <div>
            <Label>Notes</Label>
            <Textarea
              value={resolution.notes}
              onChange={(e) => setResolution({ ...resolution, notes: e.target.value })}
              rows={3}
              className="mt-1"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setResolveDialogOpen(false)}>Cancel</Button>
          <Button
            variant={resolution.resolution === 'REJECT' ? 'destructive' : 'default'}
            onClick={handleResolveDiscrepancy}
            disabled={actionLoading}
          >
            {actionLoading ? <Spinner size="sm" /> : 'Resolve'}
          </Button>
        </div>
      </Modal>
    </div>
  );
};

export default Invoices;
