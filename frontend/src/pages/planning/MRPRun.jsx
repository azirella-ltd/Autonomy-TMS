/**
 * MRP Run Page
 *
 * Execute Material Requirements Planning (MRP) from approved MPS plans.
 * Shows BOM explosion, component requirements, and generated orders.
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Input,
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
import { Checkbox } from '../../components/ui/checkbox';
import {
  Play,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  ClipboardList,
  ShoppingCart,
  XCircle,
} from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useCapabilities } from '../../hooks/useCapabilities';
import { api } from '../../services/api';

const MRPRun = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { hasCapability } = useCapabilities();

  // State
  const [mpsPlans, setMpsPlans] = useState([]);
  const [selectedPlanId, setSelectedPlanId] = useState(searchParams.get('plan_id') || '');
  const [bomLevels, setBomLevels] = useState('');
  const [generateOrders, setGenerateOrders] = useState(true);
  const [loading, setLoading] = useState(false);
  const [loadingPlans, setLoadingPlans] = useState(true);
  const [error, setError] = useState(null);
  const [currentTab, setCurrentTab] = useState('requirements');

  // Results
  const [mrpResult, setMrpResult] = useState(null);
  const [showResultDialog, setShowResultDialog] = useState(false);

  // Permissions
  const canManage = hasCapability('manage_mps');

  // Load MPS plans on mount
  useEffect(() => {
    loadMpsPlans();
  }, []);

  const loadMpsPlans = async () => {
    try {
      setLoadingPlans(true);
      const response = await api.get('/mps/plans', {
        params: { status_filter: 'APPROVED' }
      });
      setMpsPlans(response.data || []);
      setError(null);
    } catch (err) {
      console.error('Error loading MPS plans:', err);
      setError('Failed to load MPS plans. Please try again.');
    } finally {
      setLoadingPlans(false);
    }
  };

  const handleRunMrp = async () => {
    if (!selectedPlanId) {
      setError('Please select an MPS plan');
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const payload = {
        mps_plan_id: parseInt(selectedPlanId),
        explode_bom_levels: bomLevels ? parseInt(bomLevels) : null,
        generate_orders: generateOrders,
        run_async: false,
      };

      const response = await api.post('/mrp/run', payload);

      setMrpResult(response.data);
      setShowResultDialog(true);

    } catch (err) {
      console.error('Error running MRP:', err);
      const errorMsg = err.response?.data?.detail || 'Failed to run MRP. Please try again.';
      setError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleCloseResultDialog = () => {
    setShowResultDialog(false);
  };

  const getExceptionSeverityVariant = (severity) => {
    switch (severity) {
      case 'high':
        return 'destructive';
      case 'medium':
        return 'warning';
      case 'low':
        return 'info';
      default:
        return 'secondary';
    }
  };

  const getOrderTypeIcon = (orderType) => {
    switch (orderType) {
      case 'po_request':
        return <ShoppingCart className="h-4 w-4" />;
      case 'to_request':
      case 'mo_request':
        return <ClipboardList className="h-4 w-4" />;
      default:
        return <ClipboardList className="h-4 w-4" />;
    }
  };

  const formatOrderType = (orderType) => {
    switch (orderType) {
      case 'po_request':
        return 'Purchase Order';
      case 'to_request':
        return 'Transfer Order';
      case 'mo_request':
        return 'Manufacturing Order';
      default:
        return orderType;
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString();
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Material Requirements Planning (MRP)</h1>
        <p className="text-muted-foreground">
          Execute MRP from approved MPS plans to explode BOMs and generate component requirements
        </p>
      </div>

      {/* Input Form */}
      <Card className="mb-6">
        <CardContent className="pt-4">
          <h2 className="text-lg font-medium mb-4">Run MRP</h2>

          {error && (
            <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
              {error}
            </Alert>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* MPS Plan Selection */}
            <div className="md:col-span-1">
              <Label>Select MPS Plan</Label>
              <Select
                value={selectedPlanId}
                onValueChange={setSelectedPlanId}
                disabled={loadingPlans || !canManage}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder="-- Select a plan --" />
                </SelectTrigger>
                <SelectContent>
                  {mpsPlans.map((plan) => (
                    <SelectItem key={plan.id} value={String(plan.id)}>
                      {plan.name} (ID: {plan.id}, Status: {plan.status})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {mpsPlans.length === 0 && !loadingPlans && (
                <p className="text-xs text-muted-foreground mt-1">
                  No approved MPS plans found. Create and approve an MPS plan first.
                </p>
              )}
            </div>

            {/* BOM Levels */}
            <div>
              <Label>BOM Explosion Levels</Label>
              <Input
                type="number"
                value={bomLevels}
                onChange={(e) => setBomLevels(e.target.value)}
                placeholder="All levels"
                disabled={!canManage}
                min={1}
                max={10}
                className="mt-1"
              />
              <p className="text-xs text-muted-foreground mt-1">Leave blank for all levels</p>
            </div>

            {/* Generate Orders Checkbox */}
            <div className="flex items-center pt-6">
              <Checkbox
                id="generateOrders"
                checked={generateOrders}
                onCheckedChange={setGenerateOrders}
                disabled={!canManage}
              />
              <Label htmlFor="generateOrders" className="ml-2 cursor-pointer">
                Auto-generate PO/TO/MO orders
              </Label>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-2 mt-6">
            <Button
              onClick={handleRunMrp}
              disabled={!selectedPlanId || loading || !canManage}
              leftIcon={loading ? <Spinner size="sm" /> : <Play className="h-4 w-4" />}
            >
              {loading ? 'Running MRP...' : 'Run MRP'}
            </Button>
            <Button
              variant="outline"
              onClick={loadMpsPlans}
              disabled={loadingPlans}
              leftIcon={<RefreshCw className="h-4 w-4" />}
            >
              Refresh Plans
            </Button>
          </div>

          {loading && (
            <div className="mt-4">
              <Progress indeterminate />
              <p className="text-sm text-muted-foreground mt-2">
                Exploding BOMs and calculating requirements...
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Info Section */}
      <Card>
        <CardContent className="pt-4">
          <h2 className="text-lg font-medium mb-4">What is MRP?</h2>
          <p className="text-sm text-muted-foreground mb-4">
            Material Requirements Planning (MRP) is a planning system that:
          </p>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><strong>Explodes BOMs:</strong> Breaks down finished goods from MPS into component requirements</li>
            <li><strong>Calculates Net Requirements:</strong> Determines what needs to be ordered (gross - on-hand - scheduled receipts)</li>
            <li><strong>Applies Sourcing Rules:</strong> Determines whether to buy, transfer, or manufacture each component</li>
            <li><strong>Generates Orders:</strong> Creates PO/TO/MO requests with proper lead time offsets</li>
            <li><strong>Detects Exceptions:</strong> Identifies stockouts, missing sourcing rules, and capacity issues</li>
          </ul>
        </CardContent>
      </Card>

      {/* Results Dialog */}
      <Modal
        open={showResultDialog}
        onClose={handleCloseResultDialog}
        title={`MRP Results - ${mrpResult?.mps_plan_name || ''}`}
        size="xl"
      >
        {mrpResult && (
          <div className="space-y-4">
            <p className="text-xs text-muted-foreground">Run ID: {mrpResult?.run_id}</p>

            {/* Summary Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Card>
                <CardContent className="pt-4">
                  <p className="text-sm text-muted-foreground">Total Components</p>
                  <p className="text-2xl font-bold">{mrpResult.summary.total_components}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <p className="text-sm text-muted-foreground">Requirements</p>
                  <p className="text-2xl font-bold">{mrpResult.summary.total_requirements}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <p className="text-sm text-muted-foreground">Planned Orders</p>
                  <p className="text-2xl font-bold text-green-600">{mrpResult.summary.total_planned_orders}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <p className="text-sm text-muted-foreground">Exceptions</p>
                  <p className={`text-2xl font-bold ${mrpResult.summary.total_exceptions > 0 ? 'text-destructive' : ''}`}>
                    {mrpResult.summary.total_exceptions}
                  </p>
                </CardContent>
              </Card>
            </div>

            {/* Exceptions Alert */}
            {mrpResult.summary.total_exceptions > 0 && (
              <Alert variant="warning">
                <AlertTriangle className="h-4 w-4" />
                <strong>{mrpResult.summary.total_exceptions} exception(s) detected.</strong> Review the Exceptions tab for details.
              </Alert>
            )}

            {/* Tabs */}
            <Tabs value={currentTab} onValueChange={setCurrentTab}>
              <TabsList>
                <TabsTrigger value="requirements">
                  Requirements ({mrpResult.requirements.length})
                </TabsTrigger>
                <TabsTrigger value="orders">
                  Generated Orders ({mrpResult.generated_orders.length})
                </TabsTrigger>
                <TabsTrigger value="exceptions">
                  Exceptions ({mrpResult.exceptions.length})
                </TabsTrigger>
              </TabsList>

              {/* Tab: Requirements */}
              <TabsContent value="requirements">
                <Card variant="outlined">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Component</TableHead>
                        <TableHead>Parent</TableHead>
                        <TableHead>Level</TableHead>
                        <TableHead>Period</TableHead>
                        <TableHead className="text-right">Gross Req</TableHead>
                        <TableHead className="text-right">Scheduled</TableHead>
                        <TableHead className="text-right">Net Req</TableHead>
                        <TableHead>Source Type</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {mrpResult.requirements.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={8} className="text-center py-6">
                            <p className="text-muted-foreground">
                              No requirements found. Top-level items may not have BOMs defined.
                            </p>
                          </TableCell>
                        </TableRow>
                      ) : (
                        mrpResult.requirements.map((req, idx) => (
                          <TableRow key={idx}>
                            <TableCell>{req.component_name}</TableCell>
                            <TableCell>{req.parent_name || '-'}</TableCell>
                            <TableCell>{req.bom_level}</TableCell>
                            <TableCell>{req.period_number + 1}</TableCell>
                            <TableCell className="text-right">{req.gross_requirement.toFixed(0)}</TableCell>
                            <TableCell className="text-right">{req.scheduled_receipts.toFixed(0)}</TableCell>
                            <TableCell className="text-right font-medium">{req.net_requirement.toFixed(0)}</TableCell>
                            <TableCell>
                              {req.source_type ? (
                                <Badge variant="outline">{req.source_type}</Badge>
                              ) : '-'}
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </Card>
              </TabsContent>

              {/* Tab: Generated Orders */}
              <TabsContent value="orders">
                <Card variant="outlined">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Order Type</TableHead>
                        <TableHead>Component</TableHead>
                        <TableHead>Destination</TableHead>
                        <TableHead>Source</TableHead>
                        <TableHead className="text-right">Quantity</TableHead>
                        <TableHead>Order Date</TableHead>
                        <TableHead>Receipt Date</TableHead>
                        <TableHead className="text-right">Lead Time</TableHead>
                        <TableHead className="text-right">Total Cost</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {mrpResult.generated_orders.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={9} className="text-center py-6">
                            <p className="text-muted-foreground">
                              No orders generated. Check if net requirements are zero or sourcing rules are missing.
                            </p>
                          </TableCell>
                        </TableRow>
                      ) : (
                        mrpResult.generated_orders.map((order, idx) => (
                          <TableRow key={idx}>
                            <TableCell>
                              <div className="flex items-center gap-1">
                                {getOrderTypeIcon(order.order_type)}
                                <span>{formatOrderType(order.order_type)}</span>
                              </div>
                            </TableCell>
                            <TableCell>{order.component_name}</TableCell>
                            <TableCell>{order.destination_site_name}</TableCell>
                            <TableCell>{order.source_site_name || order.vendor_id || '-'}</TableCell>
                            <TableCell className="text-right">{order.quantity.toFixed(0)}</TableCell>
                            <TableCell>{formatDate(order.order_date)}</TableCell>
                            <TableCell>{formatDate(order.receipt_date)}</TableCell>
                            <TableCell className="text-right">{order.lead_time_days} days</TableCell>
                            <TableCell className="text-right">
                              {order.total_cost ? `$${order.total_cost.toFixed(2)}` : '-'}
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </Card>
              </TabsContent>

              {/* Tab: Exceptions */}
              <TabsContent value="exceptions">
                {mrpResult.exceptions.length === 0 ? (
                  <Alert variant="success">
                    <CheckCircle className="h-4 w-4" />
                    <strong>No exceptions found.</strong> MRP run completed successfully with no issues.
                  </Alert>
                ) : (
                  <div className="space-y-3">
                    {mrpResult.exceptions.map((exc, idx) => (
                      <Alert
                        key={idx}
                        variant={exc.severity === 'high' ? 'error' : exc.severity === 'medium' ? 'warning' : 'info'}
                      >
                        <XCircle className="h-4 w-4" />
                        <div>
                          <p className="text-sm font-medium">
                            {exc.exception_type.replace(/_/g, ' ').toUpperCase()}: {exc.message}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            Component: {exc.component_name} | Site: {exc.site_name} | Period: {exc.period_number + 1}
                          </p>
                          {exc.quantity_shortfall && (
                            <p className="text-xs text-muted-foreground">
                              Shortfall: {exc.quantity_shortfall.toFixed(0)} units
                            </p>
                          )}
                          {exc.recommended_action && (
                            <p className="text-xs italic mt-1">
                              Recommended: {exc.recommended_action}
                            </p>
                          )}
                        </div>
                      </Alert>
                    ))}
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </div>
        )}
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={handleCloseResultDialog}>Close</Button>
          <Button onClick={() => navigate(`/planning/mps/${mrpResult?.mps_plan_id}`)}>
            View MPS Plan
          </Button>
        </div>
      </Modal>
    </div>
  );
};

export default MRPRun;
