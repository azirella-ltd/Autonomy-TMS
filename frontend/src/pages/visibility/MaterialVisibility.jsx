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
import {
  Truck,
  AlertTriangle,
  CheckCircle,
  AlertCircle,
  Info,
  RefreshCw,
  Filter,
  MapPin,
  ChevronUp,
  ChevronDown,
} from 'lucide-react';
import { api } from '../../services/api';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';

const MaterialVisibility = () => {
  const { formatProduct } = useDisplayPreferences();
  // State management
  const [shipments, setShipments] = useState([]);
  const [filteredShipments, setFilteredShipments] = useState([]);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedShipment, setSelectedShipment] = useState(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);

  // Filter state
  const [filters, setFilters] = useState({
    status: 'all',
    riskLevel: 'all',
    productId: 'all',
  });

  // Sorting state
  const [orderBy, setOrderBy] = useState('expected_delivery_date');
  const [order, setOrder] = useState('asc');

  // Fetch data on mount
  useEffect(() => {
    fetchData();
  }, []);

  // Apply filters when shipments or filters change
  useEffect(() => {
    applyFilters();
  }, [shipments, filters]);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch in-transit shipments and summary in parallel
      const [shipmentsResponse, summaryResponse] = await Promise.all([
        api.get('/shipment-tracking/in-transit'),
        api.get('/shipment-tracking/summary'),
      ]);

      setShipments(shipmentsResponse.data);
      setSummary(summaryResponse.data);
    } catch (err) {
      console.error('Error fetching shipment data:', err);
      setError(err.response?.data?.detail || 'Failed to load shipment data');
    } finally {
      setLoading(false);
    }
  };

  const applyFilters = () => {
    let filtered = [...shipments];

    if (filters.status !== 'all') {
      filtered = filtered.filter(s => s.status === filters.status);
    }

    if (filters.riskLevel !== 'all') {
      filtered = filtered.filter(s => s.risk_level === filters.riskLevel);
    }

    if (filters.productId !== 'all') {
      filtered = filtered.filter(s => s.product_id === filters.productId);
    }

    setFilteredShipments(filtered);
  };

  const handleSort = (property) => {
    const isAsc = orderBy === property && order === 'asc';
    setOrder(isAsc ? 'desc' : 'asc');
    setOrderBy(property);

    const sorted = [...filteredShipments].sort((a, b) => {
      if (a[property] < b[property]) return isAsc ? -1 : 1;
      if (a[property] > b[property]) return isAsc ? 1 : -1;
      return 0;
    });

    setFilteredShipments(sorted);
  };

  const handleShipmentClick = async (shipmentId) => {
    try {
      const response = await api.get(`/shipment-tracking/${shipmentId}`);
      setSelectedShipment(response.data);
      setDetailModalOpen(true);
    } catch (err) {
      console.error('Error fetching shipment details:', err);
      setError('Failed to load shipment details');
    }
  };

  const handleCloseDetail = () => {
    setDetailModalOpen(false);
    setSelectedShipment(null);
  };

  const getRiskVariant = (riskLevel) => {
    switch (riskLevel) {
      case 'CRITICAL':
        return 'destructive';
      case 'HIGH':
        return 'warning';
      case 'MEDIUM':
        return 'info';
      case 'LOW':
      default:
        return 'success';
    }
  };

  const getStatusVariant = (status) => {
    switch (status) {
      case 'delivered':
        return 'success';
      case 'in_transit':
        return 'info';
      case 'delayed':
        return 'warning';
      case 'exception':
        return 'destructive';
      case 'planned':
      default:
        return 'secondary';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'delivered':
        return <CheckCircle className="h-3 w-3" />;
      case 'in_transit':
        return <Truck className="h-3 w-3" />;
      case 'delayed':
        return <AlertTriangle className="h-3 w-3" />;
      case 'exception':
        return <AlertCircle className="h-3 w-3" />;
      case 'planned':
      default:
        return <Info className="h-3 w-3" />;
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Get unique product IDs for filter
  const uniqueProducts = [...new Set(shipments.map(s => s.product_id))];

  const SortButton = ({ column, children }) => (
    <button
      onClick={() => handleSort(column)}
      className="flex items-center gap-1 hover:text-primary"
    >
      {children}
      {orderBy === column && (
        order === 'asc' ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />
      )}
    </button>
  );

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Material Visibility</h1>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" onClick={fetchData}>
                <RefreshCw className="h-5 w-5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Refresh Data</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Total Shipments</p>
            <p className="text-4xl font-bold">{summary.total_shipments || 0}</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">At Risk</p>
            <p className="text-4xl font-bold text-amber-500">
              {(summary.at_risk_shipments?.HIGH || 0) + (summary.at_risk_shipments?.CRITICAL || 0)}
            </p>
            <p className="text-xs text-muted-foreground">
              High: {summary.at_risk_shipments?.HIGH || 0} | Critical: {summary.at_risk_shipments?.CRITICAL || 0}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Avg Risk Score</p>
            <p className={`text-4xl font-bold ${summary.average_risk_score > 50 ? 'text-destructive' : 'text-green-600'}`}>
              {summary.average_risk_score?.toFixed(1) || 0}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">On-Time Rate</p>
            <p className="text-4xl font-bold text-green-600">
              {summary.on_time_delivery_rate?.toFixed(1) || 0}%
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-center gap-4">
            <Filter className="h-5 w-5 text-muted-foreground" />

            <div className="min-w-[150px]">
              <Label htmlFor="status-filter">Status</Label>
              <select
                id="status-filter"
                value={filters.status}
                onChange={(e) => setFilters({ ...filters, status: e.target.value })}
                className="w-full mt-1 h-9 px-3 rounded-md border border-input bg-background text-sm"
              >
                <option value="all">All Statuses</option>
                <option value="planned">Planned</option>
                <option value="in_transit">In Transit</option>
                <option value="delayed">Delayed</option>
                <option value="delivered">Delivered</option>
                <option value="exception">Exception</option>
              </select>
            </div>

            <div className="min-w-[150px]">
              <Label htmlFor="risk-filter">Risk Level</Label>
              <select
                id="risk-filter"
                value={filters.riskLevel}
                onChange={(e) => setFilters({ ...filters, riskLevel: e.target.value })}
                className="w-full mt-1 h-9 px-3 rounded-md border border-input bg-background text-sm"
              >
                <option value="all">All Risk Levels</option>
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
                <option value="CRITICAL">Critical</option>
              </select>
            </div>

            <div className="min-w-[150px]">
              <Label htmlFor="product-filter">Product</Label>
              <select
                id="product-filter"
                value={filters.productId}
                onChange={(e) => setFilters({ ...filters, productId: e.target.value })}
                className="w-full mt-1 h-9 px-3 rounded-md border border-input bg-background text-sm"
              >
                <option value="all">All Products</option>
                {uniqueProducts.map(product => (
                  <option key={product} value={product}>{product}</option>
                ))}
              </select>
            </div>

            <div className="flex items-end">
              <Button
                variant="outline"
                onClick={() => setFilters({ status: 'all', riskLevel: 'all', productId: 'all' })}
                className="mt-5"
              >
                Clear Filters
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Shipments Table */}
      <Card>
        <CardContent className="pt-6">
          <h3 className="text-lg font-semibold mb-4">
            In-Transit Shipments ({filteredShipments.length})
          </h3>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>
                  <SortButton column="shipment_id">Shipment ID</SortButton>
                </TableHead>
                <TableHead>Product</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Carrier</TableHead>
                <TableHead>From → To</TableHead>
                <TableHead>
                  <SortButton column="expected_delivery_date">Expected Delivery</SortButton>
                </TableHead>
                <TableHead>Days in Transit</TableHead>
                <TableHead>
                  <SortButton column="delivery_risk_score">Risk</SortButton>
                </TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredShipments.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-8">
                    <p className="text-muted-foreground">
                      No shipments found matching the selected filters
                    </p>
                  </TableCell>
                </TableRow>
              ) : (
                filteredShipments.map((shipment) => (
                  <TableRow
                    key={shipment.shipment_id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleShipmentClick(shipment.shipment_id)}
                  >
                    <TableCell className="font-medium">{shipment.shipment_id}</TableCell>
                    <TableCell>{formatProduct(shipment.product_id, shipment.product_name)}</TableCell>
                    <TableCell>
                      <Badge variant={getStatusVariant(shipment.status)} className="flex items-center gap-1 w-fit">
                        {getStatusIcon(shipment.status)}
                        {shipment.status.replace('_', ' ').toUpperCase()}
                      </Badge>
                    </TableCell>
                    <TableCell>{shipment.carrier_name || 'N/A'}</TableCell>
                    <TableCell>
                      <span className="text-xs">
                        {shipment.from_site_id} → {shipment.to_site_id}
                      </span>
                    </TableCell>
                    <TableCell>{formatDate(shipment.expected_delivery_date)}</TableCell>
                    <TableCell>
                      {shipment.days_in_transit !== null ? `${shipment.days_in_transit} days` : 'N/A'}
                    </TableCell>
                    <TableCell>
                      <Badge variant={getRiskVariant(shipment.risk_level)}>
                        {shipment.risk_level} ({shipment.delivery_risk_score?.toFixed(0) || 0})
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleShipmentClick(shipment.shipment_id);
                        }}
                      >
                        Details
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Shipment Detail Modal */}
      <Dialog open={detailModalOpen} onOpenChange={setDetailModalOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          {selectedShipment && (
            <>
              <DialogHeader>
                <DialogTitle className="flex justify-between items-center">
                  <span>Shipment Details: {selectedShipment.shipment_id}</span>
                  <Badge variant={getRiskVariant(selectedShipment.risk_level)}>
                    {selectedShipment.risk_level}
                  </Badge>
                </DialogTitle>
              </DialogHeader>

              <div className="space-y-6 mt-4">
                {/* Basic Information */}
                <div className="grid grid-cols-2 gap-4">
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
                    <p className="font-medium">{selectedShipment.quantity} {selectedShipment.uom}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Carrier</p>
                    <p className="font-medium">{selectedShipment.carrier_name}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Tracking Number</p>
                    <p className="font-medium">{selectedShipment.tracking_number}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Status</p>
                    <Badge variant={getStatusVariant(selectedShipment.status)} className="flex items-center gap-1 w-fit mt-1">
                      {getStatusIcon(selectedShipment.status)}
                      {selectedShipment.status.replace('_', ' ').toUpperCase()}
                    </Badge>
                  </div>
                </div>

                {/* Risk Factors */}
                {selectedShipment.risk_factors && Object.keys(selectedShipment.risk_factors).length > 0 && (
                  <div>
                    <h4 className="font-semibold mb-2">Risk Factors</h4>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(selectedShipment.risk_factors).map(([factor, score]) => (
                        <div key={factor} className="flex justify-between text-sm">
                          <span className="text-muted-foreground">
                            {factor.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                          </span>
                          <span className="font-medium">
                            {typeof score === 'number' ? score.toFixed(1) : score}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Recommended Actions */}
                {selectedShipment.recommended_actions && selectedShipment.recommended_actions.length > 0 && (
                  <div>
                    <h4 className="font-semibold mb-2">Recommended Actions</h4>
                    {selectedShipment.recommended_actions.map((action, index) => (
                      <Card key={index} className="mb-2 bg-amber-50 dark:bg-amber-950 border-amber-200">
                        <CardContent className="p-4">
                          <p className="font-medium">
                            {action.action.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                          </p>
                          <p className="text-sm text-muted-foreground mt-1">
                            {action.description}
                          </p>
                          <div className="flex justify-between text-xs mt-2">
                            <span>Impact: {action.impact}</span>
                            <span>Cost: {action.estimated_cost}</span>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}

                {/* Tracking Timeline */}
                {selectedShipment.tracking_events && selectedShipment.tracking_events.length > 0 && (
                  <div>
                    <h4 className="font-semibold mb-2">Tracking History</h4>
                    <div className="space-y-4">
                      {selectedShipment.tracking_events.map((event, index) => (
                        <div key={index} className="flex gap-3">
                          <MapPin className="h-5 w-5 text-primary mt-0.5" />
                          <div className="flex-1">
                            <div className="flex justify-between items-start">
                              <p className="font-medium text-sm">
                                {event.event_type?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                              </p>
                              <span className="text-xs text-muted-foreground">
                                {formatDate(event.timestamp)}
                              </span>
                            </div>
                            <p className="text-sm text-muted-foreground">{event.description}</p>
                            {event.location && (
                              <p className="text-xs text-muted-foreground">{event.location}</p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={handleCloseDetail}>Close</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MaterialVisibility;
