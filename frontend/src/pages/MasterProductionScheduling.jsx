/**
 * Master Production Scheduling (MPS) Page
 *
 * Comprehensive MPS interface for:
 * - Viewing master production schedules
 * - Creating and managing MPS plans
 * - Approving MPS for execution
 * - Rough-cut capacity planning
 * - MPS pegging and ATP/CTP
 */

import React, { useState, useEffect } from 'react';
import {
  Alert,
  AlertDescription,
  AlertTitle,
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
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../components/common';
import {
  Plus,
  RefreshCw,
  CheckCircle,
  Pencil,
  Trash2,
  Eye,
  BarChart3,
  Calendar,
  AlertTriangle,
  TrendingUp,
  Play,
  Download,
  Factory,
  GitBranch,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useCapabilities } from '../hooks/useCapabilities';
import { api } from '../services/api';
import { getSupplyChainConfigs } from '../services/supplyChainConfigService';

const MasterProductionScheduling = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { hasCapability } = useCapabilities();

  // State
  const [tabValue, setTabValue] = useState('plans');
  const [mpsPlans, setMpsPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [selectedConfig, setSelectedConfig] = useState('');
  const [configs, setConfigs] = useState([]);
  const [generatingOrders, setGeneratingOrders] = useState(false);
  const [generateOrdersDialog, setGenerateOrdersDialog] = useState({ open: false, plan: null });
  const [orderGenerationResult, setOrderGenerationResult] = useState(null);

  // Permissions
  const canManage = hasCapability('manage_mps');
  const canApprove = hasCapability('approve_mps');

  // Load data
  useEffect(() => {
    loadMPSPlans();
    loadConfigs();
  }, []);

  const loadMPSPlans = async () => {
    try {
      setLoading(true);
      const response = await api.get('/mps/plans');
      setMpsPlans(response.data || []);
      setError(null);
    } catch (err) {
      console.error('Error loading MPS plans:', err);
      setError('Failed to load MPS plans. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const loadConfigs = async () => {
    try {
      const configs = await getSupplyChainConfigs();
      setConfigs(configs || []);
    } catch (err) {
      console.error('Error loading configs:', err);
    }
  };

  const handleCreateMPS = async () => {
    if (!selectedConfig) {
      alert('Please select a supply chain configuration');
      return;
    }

    try {
      await api.post('/mps/plans', {
        config_id: selectedConfig,
        planning_horizon: 52,
        user_id: user.id,
      });
      setCreateDialogOpen(false);
      setSelectedConfig('');
      loadMPSPlans();
    } catch (err) {
      console.error('Error creating MPS plan:', err);
      alert('Failed to create MPS plan. Please try again.');
    }
  };

  const handleApprovePlan = async (planId) => {
    if (!window.confirm('Approve this MPS plan? This will release it for execution.')) {
      return;
    }

    try {
      await api.post(`/mps/plans/${planId}/approve`);
      loadMPSPlans();
    } catch (err) {
      console.error('Error approving MPS plan:', err);
      alert('Failed to approve MPS plan. Please try again.');
    }
  };

  const handleGenerateOrders = async () => {
    const { plan } = generateOrdersDialog;
    if (!plan) return;

    try {
      setGeneratingOrders(true);
      const response = await api.post(`/mps/plans/${plan.id}/generate-orders`);
      setOrderGenerationResult(response.data);
      setGenerateOrdersDialog({ open: false, plan: null });
    } catch (err) {
      console.error('Error generating production orders:', err);
      const errorMsg = err.response?.data?.detail || 'Failed to generate production orders. Please try again.';
      alert(errorMsg);
    } finally {
      setGeneratingOrders(false);
    }
  };

  const openGenerateOrdersDialog = (plan) => {
    setGenerateOrdersDialog({ open: true, plan });
    setOrderGenerationResult(null);
  };

  const closeGenerateOrdersDialog = () => {
    setGenerateOrdersDialog({ open: false, plan: null });
  };

  const closeResultDialog = () => {
    setOrderGenerationResult(null);
  };

  const getStatusVariant = (status) => {
    switch (status) {
      case 'DRAFT':
        return 'secondary';
      case 'PENDING_APPROVAL':
        return 'warning';
      case 'APPROVED':
        return 'success';
      case 'IN_EXECUTION':
        return 'info';
      case 'COMPLETED':
        return 'success';
      case 'CANCELLED':
        return 'destructive';
      default:
        return 'secondary';
    }
  };

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Master Production Scheduling (MPS)</h1>
        <p className="text-muted-foreground">
          Plan and manage master production schedules across your supply chain network
        </p>
      </div>

      {/* Action Bar */}
      <div className="flex justify-between items-center mb-6 flex-wrap gap-4">
        <div className="flex gap-2">
          <Button onClick={() => setCreateDialogOpen(true)} disabled={!canManage}>
            <Plus className="h-4 w-4 mr-2" />
            Create MPS Plan
          </Button>
          <Button variant="outline" onClick={loadMPSPlans}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
        <Button variant="outline" disabled={mpsPlans.length === 0}>
          <Download className="h-4 w-4 mr-2" />
          Export
        </Button>
      </div>

      {/* Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Active MPS Plans</p>
            <p className="text-4xl font-bold">
              {mpsPlans.filter(p => p.status === 'APPROVED' || p.status === 'IN_EXECUTION').length}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Pending Approval</p>
            <p className="text-4xl font-bold">
              {mpsPlans.filter(p => p.status === 'PENDING_APPROVAL').length}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Draft Plans</p>
            <p className="text-4xl font-bold">
              {mpsPlans.filter(p => p.status === 'DRAFT').length}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Total Plans</p>
            <p className="text-4xl font-bold">{mpsPlans.length}</p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Card className="mb-6">
        <Tabs value={tabValue} onValueChange={setTabValue}>
          <TabsList className="w-full justify-start border-b rounded-none h-auto p-0">
            <TabsTrigger value="plans" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary gap-2">
              <Calendar className="h-4 w-4" />
              MPS Plans
            </TabsTrigger>
            <TabsTrigger value="capacity" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary gap-2">
              <BarChart3 className="h-4 w-4" />
              Capacity Planning
            </TabsTrigger>
            <TabsTrigger value="metrics" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary gap-2">
              <TrendingUp className="h-4 w-4" />
              Performance Metrics
            </TabsTrigger>
          </TabsList>

          {/* Error Alert */}
          {error && (
            <Alert variant="destructive" className="m-6">
              <AlertTitle>Error</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Tab: MPS Plans */}
          <TabsContent value="plans" className="p-6">
            {loading ? (
              <div className="flex justify-center py-8">
                <Spinner size="lg" />
              </div>
            ) : mpsPlans.length === 0 ? (
              <div className="text-center py-16">
                <Calendar className="h-16 w-16 mx-auto text-muted-foreground mb-4" />
                <h2 className="text-xl font-semibold mb-2">No MPS Plans Yet</h2>
                <p className="text-muted-foreground mb-6">
                  Create your first master production schedule to get started
                </p>
                <Button onClick={() => setCreateDialogOpen(true)} disabled={!canManage}>
                  <Plus className="h-4 w-4 mr-2" />
                  Create MPS Plan
                </Button>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Plan Name</TableHead>
                    <TableHead>Configuration</TableHead>
                    <TableHead>Horizon</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Created By</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {mpsPlans.map((plan) => (
                    <TableRow
                      key={plan.id}
                      className={plan.status === 'APPROVED' ? 'bg-green-50 border-l-4 border-l-green-500' : ''}
                    >
                      <TableCell className="font-medium">
                        <div className="flex items-center gap-2">
                          {plan.name || `MPS Plan ${plan.id}`}
                          {plan.status === 'APPROVED' && (
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-green-100 text-green-700 border border-green-300">
                              ACTIVE
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>{plan.config_name || 'N/A'}</TableCell>
                      <TableCell>{plan.planning_horizon} weeks</TableCell>
                      <TableCell>
                        <Badge variant={getStatusVariant(plan.status)}>
                          {plan.status || 'DRAFT'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {plan.created_at
                          ? new Date(plan.created_at).toLocaleDateString()
                          : 'N/A'}
                      </TableCell>
                      <TableCell>{plan.created_by_name || 'System'}</TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-1">
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => navigate(`/planning/mps/${plan.id}`)}
                                >
                                  <Eye className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>View Details</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>

                          {canManage && plan.status === 'DRAFT' && (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => navigate(`/planning/mps/${plan.id}/edit`)}
                                  >
                                    <Pencil className="h-4 w-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Edit</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          )}

                          {canApprove && plan.status === 'PENDING_APPROVAL' && (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="text-green-600"
                                    onClick={() => handleApprovePlan(plan.id)}
                                  >
                                    <CheckCircle className="h-4 w-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Approve</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          )}

                          {canManage && plan.status === 'APPROVED' && (
                            <>
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="text-purple-600"
                                      onClick={() => navigate(`/execution/mrp?plan_id=${plan.id}`)}
                                    >
                                      <GitBranch className="h-4 w-4" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>Run MRP</TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="text-primary"
                                      onClick={() => openGenerateOrdersDialog(plan)}
                                    >
                                      <Factory className="h-4 w-4" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>Generate Production Orders</TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            </>
                          )}

                          {canManage && plan.status === 'DRAFT' && (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button variant="ghost" size="icon" className="text-destructive">
                                    <Trash2 className="h-4 w-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Delete</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </TabsContent>

          {/* Tab: Capacity Planning */}
          <TabsContent value="capacity" className="p-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Lot Sizing Section */}
              <Card>
                <CardContent className="pt-6">
                  <div className="flex items-center gap-2 mb-4">
                    <BarChart3 className="h-5 w-5 text-primary" />
                    <h3 className="text-lg font-semibold">Lot Sizing Algorithms</h3>
                  </div>
                  <p className="text-muted-foreground mb-4">
                    Optimize production batch sizes to minimize setup and holding costs
                  </p>

                  <hr className="my-4" />

                  <Alert className="mb-4">
                    <AlertTitle>Available Algorithms</AlertTitle>
                    <AlertDescription>
                      <ul className="list-disc list-inside mt-2 space-y-1">
                        <li><strong>LFL</strong> - Lot-for-Lot: Order exact demand each period</li>
                        <li><strong>EOQ</strong> - Economic Order Quantity: Optimal fixed batch size</li>
                        <li><strong>POQ</strong> - Period Order Quantity: EOQ adapted for periods</li>
                        <li><strong>FOQ</strong> - Fixed Order Quantity: Predetermined batch size</li>
                        <li><strong>PPB</strong> - Part Period Balancing: Balance setup vs holding cost</li>
                      </ul>
                    </AlertDescription>
                  </Alert>

                  <Button
                    className="w-full mb-4"
                    disabled={!canManage || mpsPlans.length === 0}
                    onClick={() => navigate('/planning/mps/lot-sizing')}
                  >
                    <Play className="h-4 w-4 mr-2" />
                    Run Lot Sizing Analysis
                  </Button>

                  <div className="bg-muted p-4 rounded-lg">
                    <p className="text-sm font-medium mb-2">Expected Benefits</p>
                    <p className="text-sm text-muted-foreground">
                      • 30-70% reduction in total costs (vs Lot-for-Lot)<br />
                      • Balanced setup and holding costs<br />
                      • Optimized inventory levels<br />
                      • Reduced production setups
                    </p>
                  </div>
                </CardContent>
              </Card>

              {/* Capacity-Constrained MPS Section */}
              <Card>
                <CardContent className="pt-6">
                  <div className="flex items-center gap-2 mb-4">
                    <AlertTriangle className="h-5 w-5 text-amber-500" />
                    <h3 className="text-lg font-semibold">Capacity-Constrained MPS</h3>
                  </div>
                  <p className="text-muted-foreground mb-4">
                    Ensure MPS plans respect capacity constraints with RCCP
                  </p>

                  <hr className="my-4" />

                  <Alert variant="warning" className="mb-4">
                    <AlertTitle>Rough-Cut Capacity Planning (RCCP)</AlertTitle>
                    <AlertDescription>
                      Validates MPS against resource capacity:
                      <ul className="list-disc list-inside mt-2 space-y-1">
                        <li>Machine hours</li>
                        <li>Labor hours</li>
                        <li>Facility space</li>
                        <li>Critical components</li>
                      </ul>
                    </AlertDescription>
                  </Alert>

                  <Button
                    variant="outline"
                    className="w-full mb-4 border-amber-500 text-amber-600 hover:bg-amber-50"
                    disabled={!canManage || mpsPlans.length === 0}
                    onClick={() => navigate('/planning/mps/capacity-check')}
                  >
                    <BarChart3 className="h-4 w-4 mr-2" />
                    Check Capacity Constraints
                  </Button>

                  <div className="bg-muted p-4 rounded-lg">
                    <p className="text-sm font-medium mb-2">Leveling Strategies</p>
                    <p className="text-sm text-muted-foreground">
                      • <strong>Level</strong>: Smooth production across periods<br />
                      • <strong>Shift</strong>: Move production earlier<br />
                      • <strong>Reduce</strong>: Cap at maximum feasible<br /><br />
                      Identifies bottlenecks and recommends actions
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Tab: Performance Metrics */}
          <TabsContent value="metrics" className="p-6">
            <div className="text-center py-16">
              <TrendingUp className="h-16 w-16 mx-auto text-muted-foreground mb-4" />
              <h2 className="text-xl font-semibold mb-2">Performance Metrics</h2>
              <p className="text-muted-foreground">
                MPS performance metrics and KPIs coming soon
              </p>
            </div>
          </TabsContent>
        </Tabs>
      </Card>

      {/* Create MPS Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Master Production Schedule</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <div className="mb-4">
              <Label htmlFor="config-select">Supply Chain Configuration</Label>
              <select
                id="config-select"
                value={selectedConfig}
                onChange={(e) => setSelectedConfig(e.target.value)}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="">Select configuration...</option>
                {configs.map((config) => (
                  <option key={config.id} value={config.id}>
                    {config.name}
                  </option>
                ))}
              </select>
            </div>
            <Alert>
              <AlertTitle>Master Production Scheduling</AlertTitle>
              <AlertDescription>
                This will create a new MPS plan for the selected supply chain configuration.
                You can configure planning horizon, demand sources, and capacity constraints after creation.
              </AlertDescription>
            </Alert>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateMPS} disabled={!selectedConfig}>
              Create MPS Plan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Generate Production Orders Confirmation Dialog */}
      <Dialog open={generateOrdersDialog.open} onOpenChange={(open) => !open && closeGenerateOrdersDialog()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Generate Production Orders</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            {generateOrdersDialog.plan && (
              <>
                <Alert className="mb-4">
                  <AlertTitle>Confirm Order Generation</AlertTitle>
                  <AlertDescription>
                    This will automatically create production orders for all periods in this MPS plan.
                  </AlertDescription>
                </Alert>

                <p className="text-sm font-medium mb-2">MPS Plan Details:</p>
                <div className="bg-muted p-4 rounded-lg mb-4">
                  <p className="text-sm">
                    <strong>Plan Name:</strong> {generateOrdersDialog.plan.name}
                  </p>
                  <p className="text-sm">
                    <strong>Configuration:</strong> {generateOrdersDialog.plan.config_name}
                  </p>
                  <p className="text-sm">
                    <strong>Planning Horizon:</strong> {generateOrdersDialog.plan.planning_horizon_weeks} weeks
                  </p>
                  <p className="text-sm flex items-center gap-2">
                    <strong>Status:</strong>
                    <Badge variant={getStatusVariant(generateOrdersDialog.plan.status)}>
                      {generateOrdersDialog.plan.status}
                    </Badge>
                  </p>
                </div>

                <Alert variant="warning">
                  <AlertDescription>
                    Production orders will be created in PLANNED status. Review and release them to the shop floor when ready.
                  </AlertDescription>
                </Alert>
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeGenerateOrdersDialog} disabled={generatingOrders}>
              Cancel
            </Button>
            <Button onClick={handleGenerateOrders} disabled={generatingOrders}>
              {generatingOrders ? (
                <>
                  <Spinner size="sm" className="mr-2" />
                  Generating...
                </>
              ) : (
                <>
                  <Factory className="h-4 w-4 mr-2" />
                  Generate Orders
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Production Orders Generation Result Dialog */}
      <Dialog open={!!orderGenerationResult} onOpenChange={(open) => !open && closeResultDialog()}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-600" />
              Production Orders Generated Successfully
            </DialogTitle>
          </DialogHeader>
          {orderGenerationResult && (
            <div className="py-4">
              <Alert variant="success" className="mb-4">
                <AlertTitle>Generation Complete</AlertTitle>
                <AlertDescription>
                  Successfully created {orderGenerationResult.total_orders_created} production orders
                  for MPS Plan "{orderGenerationResult.plan_name}"
                </AlertDescription>
              </Alert>

              <p className="text-sm font-medium mb-2">Order Summary:</p>
              <Card className="mb-4">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Order Number</TableHead>
                      <TableHead>Product</TableHead>
                      <TableHead>Site</TableHead>
                      <TableHead className="text-right">Quantity</TableHead>
                      <TableHead>Start Date</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {orderGenerationResult.orders.slice(0, 10).map((order) => (
                      <TableRow key={order.order_id}>
                        <TableCell>{order.order_number}</TableCell>
                        <TableCell>{order.product_name}</TableCell>
                        <TableCell>{order.site_name}</TableCell>
                        <TableCell className="text-right">{order.quantity}</TableCell>
                        <TableCell>
                          {new Date(order.planned_start_date).toLocaleDateString()}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary">{order.status}</Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>

              {orderGenerationResult.orders.length > 10 && (
                <p className="text-sm text-muted-foreground mb-4">
                  Showing first 10 of {orderGenerationResult.total_orders_created} orders
                </p>
              )}

              <hr className="my-4" />

              <p className="text-sm font-medium mb-2">Next Steps:</p>
              <Alert>
                <AlertDescription>
                  <ul className="list-disc list-inside space-y-1">
                    <li>Review production orders in the Production Management module</li>
                    <li>Check capacity requirements and resource availability</li>
                    <li>Release orders to the shop floor when ready</li>
                    <li>Monitor production progress and update actual quantities</li>
                  </ul>
                </AlertDescription>
              </Alert>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={closeResultDialog}>
              Close
            </Button>
            <Button onClick={() => {
              closeResultDialog();
              // navigate('/production/orders');
            }}>
              View Production Orders
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MasterProductionScheduling;
