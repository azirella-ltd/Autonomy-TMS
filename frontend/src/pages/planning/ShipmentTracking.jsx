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
  RefreshCw,
  Truck,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Info,
  Pencil,
  Eye,
  Activity,
  MapPin,
  TrendingUp,
} from 'lucide-react';
import { format } from 'date-fns';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';

const ShipmentTracking = () => {
  const { effectiveConfigId } = useActiveConfig();
  const { formatProduct, formatSite, loadLookupsForConfig } = useDisplayPreferences();

  useEffect(() => { if (effectiveConfigId) loadLookupsForConfig(effectiveConfigId); }, [effectiveConfigId, loadLookupsForConfig]);

  // State management
  const [shipments, setShipments] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Filters
  const [productFilter, setProductFilter] = useState('');
  const [siteFilter, setSiteFilter] = useState('');
  const [riskFilter, setRiskFilter] = useState('all');

  // Dialogs
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [selectedShipment, setSelectedShipment] = useState(null);
  const [statusDialogOpen, setStatusDialogOpen] = useState(false);
  const [statusUpdate, setStatusUpdate] = useState({
    status: 'in_transit',
    current_location: '',
    event_type: '',
    event_description: '',
  });

  // Tab state
  const [tabValue, setTabValue] = useState('shipments');

  // Fetch shipments
  const fetchShipments = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (productFilter) params.product_id = productFilter;
      if (siteFilter) params.site_id = siteFilter;
      if (riskFilter && riskFilter !== 'all') params.risk_level = riskFilter;

      const response = await api.get('/shipment-tracking/in-transit', { params });
      setShipments(response.data);
    } catch (err) {
      console.error('Failed to fetch shipments:', err);
      setError('Failed to load shipments. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Fetch summary
  const fetchSummary = async () => {
    try {
      const response = await api.get('/shipment-tracking/summary');
      setSummary(response.data);
    } catch (err) {
      console.error('Failed to fetch summary:', err);
    }
  };

  // Fetch shipment details
  const fetchShipmentDetails = async (shipmentId) => {
    setLoading(true);
    try {
      const response = await api.get(`/shipment-tracking/${shipmentId}`);
      setSelectedShipment(response.data);
      setDetailDialogOpen(true);
    } catch (err) {
      console.error('Failed to fetch shipment details:', err);
      setError('Failed to load shipment details.');
    } finally {
      setLoading(false);
    }
  };

  // Update shipment status
  const updateShipmentStatus = async () => {
    if (!selectedShipment) return;

    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      await api.put(`/shipment-tracking/${selectedShipment.shipment_id}/status`, statusUpdate);
      setSuccess('Shipment status updated successfully');
      setStatusDialogOpen(false);
      setStatusUpdate({
        status: 'in_transit',
        current_location: '',
        event_type: '',
        event_description: '',
      });
      await fetchShipments();
      await fetchSummary();
    } catch (err) {
      console.error('Failed to update shipment status:', err);
      setError('Failed to update shipment status.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchShipments();
    fetchSummary();
  }, [productFilter, siteFilter, riskFilter]);

  // Helper functions
  const getStatusVariant = (status) => {
    const variants = {
      delivered: 'success',
      in_transit: 'info',
      delayed: 'warning',
      exception: 'destructive',
      cancelled: 'destructive',
    };
    return variants[status] || 'secondary';
  };

  const getRiskIcon = (riskLevel) => {
    switch (riskLevel) {
      case 'CRITICAL':
        return <XCircle className="h-4 w-4 text-destructive" />;
      case 'HIGH':
        return <AlertTriangle className="h-4 w-4 text-amber-500" />;
      case 'MEDIUM':
        return <Info className="h-4 w-4 text-blue-500" />;
      case 'LOW':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      default:
        return null;
    }
  };

  const getRiskVariant = (riskLevel) => {
    const variants = {
      CRITICAL: 'destructive',
      HIGH: 'warning',
      MEDIUM: 'info',
      LOW: 'success',
    };
    return variants[riskLevel] || 'secondary';
  };

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Shipment Tracking</h1>
        <Button
          variant="outline"
          onClick={() => { fetchShipments(); fetchSummary(); }}
          leftIcon={<RefreshCw className="h-4 w-4" />}
        >
          Refresh
        </Button>
      </div>

      {error && (
        <Alert variant="error" onClose={() => setError(null)} className="mb-4">
          {error}
        </Alert>
      )}

      {success && (
        <Alert variant="success" onClose={() => setSuccess(null)} className="mb-4">
          {success}
        </Alert>
      )}

      {loading && <Progress indeterminate className="mb-4" />}

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-3xl font-bold">{summary.total_shipments}</p>
                  <p className="text-sm text-muted-foreground">Total Shipments</p>
                </div>
                <Truck className="h-8 w-8 text-primary" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-3xl font-bold">{summary.at_risk_shipments.HIGH + summary.at_risk_shipments.CRITICAL}</p>
                  <p className="text-sm text-muted-foreground">At-Risk Shipments</p>
                </div>
                <AlertTriangle className="h-8 w-8 text-amber-500" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-3xl font-bold">{summary.on_time_delivery_rate.toFixed(1)}%</p>
                  <p className="text-sm text-muted-foreground">On-Time Delivery</p>
                </div>
                <TrendingUp className="h-8 w-8 text-green-500" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-3xl font-bold">{summary.average_risk_score.toFixed(1)}</p>
                  <p className="text-sm text-muted-foreground">Avg Risk Score</p>
                </div>
                <Activity className="h-8 w-8 text-blue-500" />
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      <Tabs value={tabValue} onValueChange={setTabValue} className="space-y-4">
        <TabsList>
          <TabsTrigger value="shipments">In-Transit Shipments</TabsTrigger>
          <TabsTrigger value="risk">Risk Summary</TabsTrigger>
        </TabsList>

        <TabsContent value="shipments">
          {/* Filters */}
          <Card className="mb-4">
            <CardContent className="pt-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <Label>Product ID</Label>
                  <Input
                    value={productFilter}
                    onChange={(e) => setProductFilter(e.target.value)}
                    placeholder="Filter by product..."
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label>Destination Site</Label>
                  <Input
                    value={siteFilter}
                    onChange={(e) => setSiteFilter(e.target.value)}
                    placeholder="Filter by site..."
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label>Risk Level</Label>
                  <Select value={riskFilter} onValueChange={setRiskFilter}>
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder="All Risk Levels" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Risk Levels</SelectItem>
                      <SelectItem value="LOW">Low</SelectItem>
                      <SelectItem value="MEDIUM">Medium</SelectItem>
                      <SelectItem value="HIGH">High</SelectItem>
                      <SelectItem value="CRITICAL">Critical</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Shipments Table */}
          <Card>
            <CardContent className="pt-4">
              <h3 className="text-lg font-medium mb-4">In-Transit Shipments ({shipments.length})</h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Shipment ID</TableHead>
                    <TableHead>Product</TableHead>
                    <TableHead>Quantity</TableHead>
                    <TableHead>From → To</TableHead>
                    <TableHead>Carrier</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Risk Level</TableHead>
                    <TableHead>Expected Delivery</TableHead>
                    <TableHead>Days in Transit</TableHead>
                    <TableHead className="text-center">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shipments.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={10} className="text-center py-8">
                        <p className="text-muted-foreground">No in-transit shipments found</p>
                      </TableCell>
                    </TableRow>
                  ) : (
                    shipments.map((shipment) => (
                      <TableRow key={shipment.shipment_id}>
                        <TableCell className="font-medium">{shipment.shipment_id}</TableCell>
                        <TableCell>{formatProduct(shipment.product_id, shipment.product_name)}</TableCell>
                        <TableCell>
                          {shipment.quantity.toFixed(2)} {shipment.uom || ''}
                        </TableCell>
                        <TableCell>
                          {formatSite(shipment.from_site_id)} → {formatSite(shipment.to_site_id)}
                        </TableCell>
                        <TableCell>{shipment.carrier_name || 'N/A'}</TableCell>
                        <TableCell>
                          <Badge variant={getStatusVariant(shipment.status)}>{shipment.status}</Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1">
                            {getRiskIcon(shipment.risk_level)}
                            <Badge variant={getRiskVariant(shipment.risk_level)}>
                              {shipment.risk_level || 'N/A'}
                            </Badge>
                          </div>
                        </TableCell>
                        <TableCell>
                          {shipment.expected_delivery_date
                            ? format(new Date(shipment.expected_delivery_date), 'PP')
                            : 'N/A'}
                        </TableCell>
                        <TableCell>{shipment.days_in_transit || 'N/A'}</TableCell>
                        <TableCell>
                          <div className="flex justify-center gap-1">
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => fetchShipmentDetails(shipment.shipment_id)}
                                  >
                                    <Eye className="h-4 w-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>View Details</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => {
                                      setSelectedShipment(shipment);
                                      setStatusDialogOpen(true);
                                    }}
                                  >
                                    <Pencil className="h-4 w-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Update Status</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="risk">
          {summary && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Card>
                <CardContent className="pt-4">
                  <h3 className="text-lg font-medium mb-4">Status Breakdown</h3>
                  <div className="space-y-3">
                    {Object.entries(summary.status_counts).map(([status, count]) => (
                      <div key={status} className="flex items-center gap-3">
                        <Truck className={`h-5 w-5 ${
                          status === 'delivered' ? 'text-green-500' :
                          status === 'in_transit' ? 'text-blue-500' :
                          status === 'delayed' ? 'text-amber-500' :
                          'text-destructive'
                        }`} />
                        <div className="flex-1">
                          <p className="font-medium">{status}</p>
                          <p className="text-sm text-muted-foreground">{count} shipments</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="pt-4">
                  <h3 className="text-lg font-medium mb-4">Risk Level Breakdown</h3>
                  <div className="space-y-3">
                    {Object.entries(summary.at_risk_shipments).map(([level, count]) => (
                      <div key={level} className="flex items-center gap-3">
                        {getRiskIcon(level)}
                        <div className="flex-1">
                          <p className="font-medium">{level}</p>
                          <p className="text-sm text-muted-foreground">{count} shipments</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Shipment Detail Dialog */}
      <Modal
        open={detailDialogOpen}
        onClose={() => setDetailDialogOpen(false)}
        title="Shipment Details"
        size="lg"
      >
        {selectedShipment && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Shipment ID</p>
                <p className="font-medium">{selectedShipment.shipment_id}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Order ID</p>
                <p className="font-medium">{selectedShipment.order_id}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Product</p>
                <p className="font-medium">{formatProduct(selectedShipment.product_id, selectedShipment.product_name)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Quantity</p>
                <p className="font-medium">{selectedShipment.quantity} {selectedShipment.uom || ''}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Carrier</p>
                <p className="font-medium">{selectedShipment.carrier_name || 'N/A'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Tracking Number</p>
                <p className="font-medium">{selectedShipment.tracking_number || 'N/A'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Current Location</p>
                <div className="flex items-center gap-1">
                  <MapPin className="h-4 w-4 text-muted-foreground" />
                  <p className="font-medium">{selectedShipment.current_location || 'N/A'}</p>
                </div>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <Badge variant={getStatusVariant(selectedShipment.status)}>{selectedShipment.status}</Badge>
              </div>
            </div>

            <div>
              <p className="text-sm text-muted-foreground mb-2">Delivery Risk Assessment</p>
              <Card variant="outlined">
                <CardContent className="pt-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-muted-foreground">Risk Score</p>
                      <p className="text-xl font-semibold">
                        {selectedShipment.delivery_risk_score?.toFixed(2) || 'N/A'}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Risk Level</p>
                      <div className="flex items-center gap-1 mt-1">
                        {getRiskIcon(selectedShipment.risk_level)}
                        <Badge variant={getRiskVariant(selectedShipment.risk_level)}>
                          {selectedShipment.risk_level || 'N/A'}
                        </Badge>
                      </div>
                    </div>
                  </div>

                  {selectedShipment.risk_factors && Object.keys(selectedShipment.risk_factors).length > 0 && (
                    <div className="mt-4">
                      <p className="text-xs text-muted-foreground mb-2">Risk Factors:</p>
                      <div className="grid grid-cols-2 gap-2">
                        {Object.entries(selectedShipment.risk_factors).map(([factor, value]) => (
                          <p key={factor} className="text-sm">
                            {factor}: {typeof value === 'number' ? value.toFixed(2) : value}
                          </p>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            {selectedShipment.recommended_actions && selectedShipment.recommended_actions.length > 0 && (
              <div>
                <p className="text-sm text-muted-foreground mb-2">Recommended Actions</p>
                <div className="space-y-2">
                  {selectedShipment.recommended_actions.map((action, index) => (
                    <div key={index} className="p-3 bg-muted rounded-lg">
                      <p className="font-medium">{action.action}</p>
                      <p className="text-sm text-muted-foreground">
                        {action.description} - Priority: {action.priority}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {selectedShipment.tracking_events && selectedShipment.tracking_events.length > 0 && (
              <div>
                <p className="text-sm text-muted-foreground mb-2">Tracking History</p>
                <div className="space-y-2">
                  {selectedShipment.tracking_events.map((event, index) => (
                    <div key={index} className="p-3 border rounded-lg">
                      <p className="font-medium">{event.event_type}</p>
                      <p className="text-sm text-muted-foreground">
                        {event.description} - {event.location || 'N/A'} -{' '}
                        {event.timestamp ? format(new Date(event.timestamp), 'PPpp') : ''}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        <div className="flex justify-end mt-6">
          <Button variant="outline" onClick={() => setDetailDialogOpen(false)}>Close</Button>
        </div>
      </Modal>

      {/* Status Update Dialog */}
      <Modal
        open={statusDialogOpen}
        onClose={() => setStatusDialogOpen(false)}
        title="Update Shipment Status"
        size="md"
      >
        <div className="space-y-4">
          <div>
            <Label>Status</Label>
            <Select
              value={statusUpdate.status}
              onValueChange={(value) => setStatusUpdate({ ...statusUpdate, status: value })}
            >
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="planned">Planned</SelectItem>
                <SelectItem value="in_transit">In Transit</SelectItem>
                <SelectItem value="delivered">Delivered</SelectItem>
                <SelectItem value="delayed">Delayed</SelectItem>
                <SelectItem value="exception">Exception</SelectItem>
                <SelectItem value="cancelled">Cancelled</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Current Location</Label>
            <Input
              value={statusUpdate.current_location}
              onChange={(e) => setStatusUpdate({ ...statusUpdate, current_location: e.target.value })}
              className="mt-1"
            />
          </div>
          <div>
            <Label>Event Type</Label>
            <Input
              value={statusUpdate.event_type}
              onChange={(e) => setStatusUpdate({ ...statusUpdate, event_type: e.target.value })}
              placeholder="e.g., DEPARTURE, ARRIVAL, DELAY"
              className="mt-1"
            />
          </div>
          <div>
            <Label>Event Description</Label>
            <Textarea
              value={statusUpdate.event_description}
              onChange={(e) => setStatusUpdate({ ...statusUpdate, event_description: e.target.value })}
              rows={3}
              className="mt-1"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setStatusDialogOpen(false)}>Cancel</Button>
          <Button onClick={updateShipmentStatus} disabled={loading}>Update</Button>
        </div>
      </Modal>
    </div>
  );
};

export default ShipmentTracking;
