/**
 * Capacity Planning Page
 *
 * Comprehensive capacity planning interface (RCCP) for:
 * - Creating and managing capacity plans
 * - Defining capacity resources (labor, machines, facilities)
 * - Calculating capacity requirements from production orders
 * - Identifying bottlenecks and overloaded resources
 * - What-if scenario analysis
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
  Checkbox,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
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
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../components/common';
import {
  Plus,
  RefreshCw,
  Trash2,
  Eye,
  Calculator,
  AlertTriangle,
  Gauge,
  Users,
  Settings,
  Building2,
  Zap,
  Wrench,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useCapabilities } from '../hooks/useCapabilities';
import { api } from '../services/api';
import { useActiveConfig } from '../contexts/ActiveConfigContext';
import { useDisplayPreferences } from '../contexts/DisplayPreferencesContext';

const CapacityPlanning = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { hasCapability } = useCapabilities();
  const { effectiveConfigId, activeConfig } = useActiveConfig();
  const { formatSite, loadLookupsForConfig } = useDisplayPreferences();

  useEffect(() => { if (effectiveConfigId) loadLookupsForConfig(effectiveConfigId); }, [effectiveConfigId, loadLookupsForConfig]);

  // State
  const [tabValue, setTabValue] = useState('plans');
  const [plans, setPlans] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // Selected plan for detail view
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [resources, setResources] = useState([]);
  const [requirements, setRequirements] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [bottlenecks, setBottlenecks] = useState([]);

  // Filters
  const [statusFilter, setStatusFilter] = useState('');
  const [configFilter, setConfigFilter] = useState('');
  const [scenarioFilter, setScenarioFilter] = useState('all');

  // Dialogs
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [resourceDialogOpen, setResourceDialogOpen] = useState(false);

  // Form data
  const [planForm, setPlanForm] = useState({
    name: '',
    description: '',
    supply_chain_config_id: '',
    planning_horizon_weeks: 13,
    bucket_size_days: 7,
    start_date: '',
    end_date: '',
    is_scenario: false,
    scenario_description: '',
    base_plan_id: null,
  });

  const [resourceForm, setResourceForm] = useState({
    resource_name: '',
    resource_type: 'MACHINE',
    site_id: '',
    available_capacity: 160,
    capacity_unit: 'hours',
    efficiency_percent: 85.0,
    utilization_target_percent: 85.0,
    cost_per_hour: 0,
    shifts_per_day: 2,
    hours_per_shift: 8,
    working_days_per_week: 5,
  });

  // Reference data
  const [sites, setSites] = useState([]);

  // Permissions
  const canView = hasCapability('view_capacity_planning');
  const canManage = hasCapability('manage_capacity_planning');

  useEffect(() => {
    if (!canView) {
      navigate('/');
      return;
    }
    fetchPlans();
    fetchSummary();
    fetchSites();
  }, [page, statusFilter, configFilter, scenarioFilter]);

  const fetchPlans = async () => {
    try {
      setLoading(true);
      const params = {
        page,
        page_size: 20,
        status: statusFilter || undefined,
        config_id: configFilter || undefined,
        is_scenario: scenarioFilter === 'all' ? undefined : scenarioFilter === 'scenarios',
      };
      const response = await api.get('/capacity-plans', { params });
      setPlans(response.data.items);
      setTotalPages(response.data.pages);
      setError(null);
    } catch (err) {
      setError('Failed to fetch capacity plans: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchSummary = async () => {
    try {
      const response = await api.get('/capacity-plans/summary');
      setSummary(response.data);
    } catch (err) {
      console.error('Failed to fetch summary:', err);
    }
  };


  const fetchSites = async () => {
    try {
      const response = await api.get('/sites');
      setSites(response.data || []);
    } catch (err) {
      console.error('Failed to fetch sites:', err);
    }
  };

  const fetchPlanDetails = async (planId) => {
    try {
      const [planRes, resourcesRes, requirementsRes, analysisRes, bottlenecksRes] = await Promise.all([
        api.get(`/capacity-plans/${planId}`),
        api.get(`/capacity-plans/${planId}/resources`),
        api.get(`/capacity-plans/${planId}/requirements`),
        api.get(`/capacity-plans/${planId}/analysis`),
        api.get(`/capacity-plans/${planId}/bottlenecks`),
      ]);
      setSelectedPlan(planRes.data);
      setResources(resourcesRes.data);
      setRequirements(requirementsRes.data);
      setAnalysis(analysisRes.data);
      setBottlenecks(bottlenecksRes.data);
      setTabValue('details');
    } catch (err) {
      setError('Failed to fetch plan details: ' + err.message);
    }
  };

  const handleCreatePlan = async () => {
    try {
      await api.post('/capacity-plans', { ...planForm, supply_chain_config_id: effectiveConfigId });
      setCreateDialogOpen(false);
      fetchPlans();
      fetchSummary();
      setPlanForm({
        name: '',
        description: '',
        supply_chain_config_id: '',
        planning_horizon_weeks: 13,
        bucket_size_days: 7,
        start_date: '',
        end_date: '',
        is_scenario: false,
        scenario_description: '',
        base_plan_id: null,
      });
    } catch (err) {
      setError('Failed to create capacity plan: ' + err.message);
    }
  };

  const handleDeletePlan = async (planId) => {
    if (!window.confirm('Are you sure you want to delete this capacity plan?')) return;
    try {
      await api.delete(`/capacity-plans/${planId}`);
      fetchPlans();
      fetchSummary();
      if (selectedPlan?.id === planId) {
        setSelectedPlan(null);
        setTabValue('plans');
      }
    } catch (err) {
      setError('Failed to delete capacity plan: ' + err.message);
    }
  };

  const handleCalculateRequirements = async (planId) => {
    try {
      await api.post(`/capacity-plans/${planId}/calculate`, {
        plan_id: planId,
        source_type: 'PRODUCTION_ORDER',
        recalculate: true,
      });
      fetchPlanDetails(planId);
      fetchSummary();
    } catch (err) {
      setError('Failed to calculate requirements: ' + err.message);
    }
  };

  const handleCreateResource = async () => {
    if (!selectedPlan) return;
    try {
      await api.post(`/capacity-plans/${selectedPlan.id}/resources`, resourceForm);
      setResourceDialogOpen(false);
      fetchPlanDetails(selectedPlan.id);
      setResourceForm({
        resource_name: '',
        resource_type: 'MACHINE',
        site_id: '',
        available_capacity: 160,
        capacity_unit: 'hours',
        efficiency_percent: 85.0,
        utilization_target_percent: 85.0,
        cost_per_hour: 0,
        shifts_per_day: 2,
        hours_per_shift: 8,
        working_days_per_week: 5,
      });
    } catch (err) {
      setError('Failed to create resource: ' + err.message);
    }
  };

  const handleDeleteResource = async (resourceId) => {
    if (!window.confirm('Are you sure you want to delete this resource?')) return;
    try {
      await api.delete(`/capacity-plans/resources/${resourceId}`);
      fetchPlanDetails(selectedPlan.id);
    } catch (err) {
      setError('Failed to delete resource: ' + err.message);
    }
  };

  const getStatusVariant = (status) => {
    switch (status) {
      case 'DRAFT': return 'secondary';
      case 'ACTIVE': return 'success';
      case 'SCENARIO': return 'info';
      case 'ARCHIVED': return 'secondary';
      default: return 'secondary';
    }
  };

  const getResourceIcon = (type) => {
    switch (type) {
      case 'LABOR': return <Users className="h-4 w-4" />;
      case 'MACHINE': return <Settings className="h-4 w-4" />;
      case 'FACILITY': return <Building2 className="h-4 w-4" />;
      case 'UTILITY': return <Zap className="h-4 w-4" />;
      case 'TOOL': return <Wrench className="h-4 w-4" />;
      default: return <Gauge className="h-4 w-4" />;
    }
  };

  const getUtilizationVariant = (utilization) => {
    if (utilization > 100) return 'destructive';
    if (utilization >= 95) return 'warning';
    if (utilization >= 80) return 'success';
    return 'info';
  };

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between flex-wrap gap-4 mb-2">
          <div className="flex items-center gap-3">
            <Gauge className="h-10 w-10 text-primary" />
            <h1 className="text-3xl font-bold">Capacity Planning (RCCP)</h1>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => { fetchPlans(); fetchSummary(); }}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
            {canManage && (
              <Button onClick={() => setCreateDialogOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Create Plan
              </Button>
            )}
          </div>
        </div>
        <p className="text-muted-foreground">
          Rough-Cut Capacity Planning (RCCP) validates production feasibility by comparing resource requirements against available capacity.
        </p>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
          <Button variant="ghost" size="sm" className="absolute top-2 right-2" onClick={() => setError(null)}>
            ×
          </Button>
        </Alert>
      )}

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground mb-1">Total Plans</p>
              <p className="text-4xl font-bold">{summary.total_plans}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground mb-1">Active Plans</p>
              <p className="text-4xl font-bold text-green-600">{summary.active_plans}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground mb-1">Feasible Plans</p>
              <p className="text-4xl font-bold text-blue-500">{summary.feasible_plans}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground mb-1">Avg Utilization</p>
              <p className={`text-4xl font-bold ${
                summary.avg_utilization > 100 ? 'text-red-500' :
                summary.avg_utilization >= 95 ? 'text-amber-500' :
                summary.avg_utilization >= 80 ? 'text-green-600' : 'text-blue-500'
              }`}>
                {summary.avg_utilization ? `${summary.avg_utilization.toFixed(1)}%` : 'N/A'}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tabs */}
      <Card>
        <Tabs value={tabValue} onValueChange={setTabValue}>
          <TabsList className="w-full justify-start border-b rounded-none h-auto p-0">
            <TabsTrigger value="plans" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
              All Plans
            </TabsTrigger>
            <TabsTrigger value="details" disabled={!selectedPlan} className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
              Plan Details
            </TabsTrigger>
            <TabsTrigger value="resources" disabled={!selectedPlan} className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
              Resources
            </TabsTrigger>
            <TabsTrigger value="requirements" disabled={!selectedPlan} className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
              Requirements
            </TabsTrigger>
            <TabsTrigger value="analysis" disabled={!selectedPlan} className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
              Analysis
            </TabsTrigger>
          </TabsList>

          {/* Tab: All Plans */}
          <TabsContent value="plans" className="p-6">
            {/* Filters */}
            <div className="flex gap-4 mb-6 flex-wrap">
              <div className="min-w-[200px]">
                <Label htmlFor="status-filter">Status</Label>
                <select
                  id="status-filter"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
                >
                  <option value="">All</option>
                  <option value="DRAFT">Draft</option>
                  <option value="ACTIVE">Active</option>
                  <option value="SCENARIO">Scenario</option>
                  <option value="ARCHIVED">Archived</option>
                </select>
              </div>
              <div className="min-w-[200px]">
                <Label htmlFor="config-filter">Config</Label>
                <p className="mt-1 h-10 flex items-center text-sm text-muted-foreground">
                  {activeConfig?.name || 'Loading...'}
                </p>
              </div>
              <div className="min-w-[200px]">
                <Label htmlFor="type-filter">Type</Label>
                <select
                  id="type-filter"
                  value={scenarioFilter}
                  onChange={(e) => setScenarioFilter(e.target.value)}
                  className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
                >
                  <option value="all">All</option>
                  <option value="base">Base Plans Only</option>
                  <option value="scenarios">Scenarios Only</option>
                </select>
              </div>
            </div>

            {loading ? (
              <div className="flex justify-center py-8">
                <Spinner size="lg" />
              </div>
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Config</TableHead>
                      <TableHead>Start Date</TableHead>
                      <TableHead>End Date</TableHead>
                      <TableHead className="text-right">Horizon (weeks)</TableHead>
                      <TableHead className="text-right">Utilization</TableHead>
                      <TableHead className="text-right">Bottlenecks</TableHead>
                      <TableHead className="text-center">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {plans.map((plan) => (
                      <TableRow key={plan.id}>
                        <TableCell>
                          <div>
                            <p className="font-medium">{plan.name}</p>
                            {plan.is_scenario && (
                              <Badge variant="info" className="mt-1">Scenario</Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant={getStatusVariant(plan.status)}>{plan.status}</Badge>
                        </TableCell>
                        <TableCell>{plan.config_name || 'N/A'}</TableCell>
                        <TableCell>{plan.start_date ? new Date(plan.start_date).toLocaleDateString() : 'N/A'}</TableCell>
                        <TableCell>{plan.end_date ? new Date(plan.end_date).toLocaleDateString() : 'N/A'}</TableCell>
                        <TableCell className="text-right">{plan.planning_horizon_weeks}</TableCell>
                        <TableCell className="text-right">
                          {plan.avg_utilization_percent ? (
                            <Badge variant={getUtilizationVariant(plan.avg_utilization_percent)}>
                              {plan.avg_utilization_percent.toFixed(1)}%
                            </Badge>
                          ) : 'N/A'}
                        </TableCell>
                        <TableCell className="text-right">
                          {plan.overloaded_resources > 0 ? (
                            <Badge variant="destructive" className="gap-1">
                              <AlertTriangle className="h-3 w-3" />
                              {plan.overloaded_resources}
                            </Badge>
                          ) : (
                            <Badge variant="success">0</Badge>
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex justify-center gap-1">
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button variant="ghost" size="icon" onClick={() => fetchPlanDetails(plan.id)}>
                                    <Eye className="h-4 w-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>View Details</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                            {canManage && (
                              <>
                                <TooltipProvider>
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <Button variant="ghost" size="icon" className="text-primary" onClick={() => handleCalculateRequirements(plan.id)}>
                                        <Calculator className="h-4 w-4" />
                                      </Button>
                                    </TooltipTrigger>
                                    <TooltipContent>Calculate Requirements</TooltipContent>
                                  </Tooltip>
                                </TooltipProvider>
                                <TooltipProvider>
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <Button variant="ghost" size="icon" className="text-destructive" onClick={() => handleDeletePlan(plan.id)}>
                                        <Trash2 className="h-4 w-4" />
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
                    ))}
                  </TableBody>
                </Table>
                <div className="flex justify-center mt-6">
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                      disabled={page === 1}
                    >
                      Previous
                    </Button>
                    <span className="flex items-center px-4 text-sm text-muted-foreground">
                      Page {page} of {totalPages}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                      disabled={page >= totalPages}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              </>
            )}
          </TabsContent>

          {/* Tab: Plan Details */}
          <TabsContent value="details" className="p-6">
            {selectedPlan && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Card>
                  <CardContent className="pt-6">
                    <h3 className="text-lg font-semibold mb-4">Plan Information</h3>
                    <hr className="mb-4" />
                    <div className="space-y-4">
                      <div>
                        <p className="text-sm text-muted-foreground">Name</p>
                        <p className="font-medium">{selectedPlan.name}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Description</p>
                        <p>{selectedPlan.description || 'N/A'}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Status</p>
                        <Badge variant={getStatusVariant(selectedPlan.status)}>{selectedPlan.status}</Badge>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Planning Horizon</p>
                        <p>{selectedPlan.planning_horizon_weeks} weeks</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Bucket Size</p>
                        <p>{selectedPlan.bucket_size_days} days</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <h3 className="text-lg font-semibold mb-4">Capacity Metrics</h3>
                    <hr className="mb-4" />
                    <div className="space-y-4">
                      <div>
                        <p className="text-sm text-muted-foreground">Is Feasible</p>
                        <Badge variant={selectedPlan.is_feasible ? 'success' : 'destructive'}>
                          {selectedPlan.is_feasible ? 'YES' : 'NO'}
                        </Badge>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Average Utilization</p>
                        <p>{selectedPlan.avg_utilization_percent ? `${selectedPlan.avg_utilization_percent.toFixed(1)}%` : 'N/A'}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Max Utilization</p>
                        <p>{selectedPlan.max_utilization_percent ? `${selectedPlan.max_utilization_percent.toFixed(1)}%` : 'N/A'}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Overloaded Resources</p>
                        <Badge variant={selectedPlan.overloaded_resources > 0 ? 'destructive' : 'success'}>
                          {selectedPlan.overloaded_resources || 0}
                        </Badge>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Bottleneck Identified</p>
                        <Badge variant={selectedPlan.bottleneck_identified ? 'warning' : 'success'}>
                          {selectedPlan.bottleneck_identified ? 'YES' : 'NO'}
                        </Badge>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}
          </TabsContent>

          {/* Tab: Resources */}
          <TabsContent value="resources" className="p-6">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-semibold">Capacity Resources</h3>
              {canManage && (
                <Button onClick={() => setResourceDialogOpen(true)}>
                  <Plus className="h-4 w-4 mr-2" />
                  Add Resource
                </Button>
              )}
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Resource Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Site</TableHead>
                  <TableHead className="text-right">Available Capacity</TableHead>
                  <TableHead className="text-right">Efficiency</TableHead>
                  <TableHead className="text-right">Target Utilization</TableHead>
                  <TableHead className="text-right">Cost/Hour</TableHead>
                  {canManage && <TableHead className="text-center">Actions</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {resources.map((resource) => (
                  <TableRow key={resource.id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {getResourceIcon(resource.resource_type)}
                        <span>{resource.resource_name}</span>
                      </div>
                    </TableCell>
                    <TableCell>{resource.resource_type}</TableCell>
                    <TableCell>{resource.site_name || 'N/A'}</TableCell>
                    <TableCell className="text-right">{resource.available_capacity} {resource.capacity_unit}</TableCell>
                    <TableCell className="text-right">{resource.efficiency_percent}%</TableCell>
                    <TableCell className="text-right">{resource.utilization_target_percent}%</TableCell>
                    <TableCell className="text-right">${resource.cost_per_hour || 0}</TableCell>
                    {canManage && (
                      <TableCell className="text-center">
                        <Button variant="ghost" size="icon" className="text-destructive" onClick={() => handleDeleteResource(resource.id)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TabsContent>

          {/* Tab: Requirements */}
          <TabsContent value="requirements" className="p-6">
            <h3 className="text-lg font-semibold mb-6">Capacity Requirements (Time-Phased)</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Period</TableHead>
                  <TableHead>Start Date</TableHead>
                  <TableHead>Resource</TableHead>
                  <TableHead className="text-right">Required</TableHead>
                  <TableHead className="text-right">Available</TableHead>
                  <TableHead className="text-right">Utilization</TableHead>
                  <TableHead className="text-center">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {requirements.map((req) => (
                  <TableRow key={req.id}>
                    <TableCell>{req.period_number}</TableCell>
                    <TableCell>{new Date(req.period_start).toLocaleDateString()}</TableCell>
                    <TableCell>{req.resource_name || 'N/A'}</TableCell>
                    <TableCell className="text-right">{req.required_capacity.toFixed(1)}</TableCell>
                    <TableCell className="text-right">{req.available_capacity.toFixed(1)}</TableCell>
                    <TableCell className="text-right">
                      <Badge variant={getUtilizationVariant(req.utilization_percent)}>
                        {req.utilization_percent.toFixed(1)}%
                      </Badge>
                    </TableCell>
                    <TableCell className="text-center">
                      {req.is_overloaded && <Badge variant="destructive">OVERLOAD</Badge>}
                      {req.is_bottleneck && !req.is_overloaded && <Badge variant="warning">BOTTLENECK</Badge>}
                      {!req.is_overloaded && !req.is_bottleneck && <Badge variant="success">OK</Badge>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TabsContent>

          {/* Tab: Analysis */}
          <TabsContent value="analysis" className="p-6">
            <div className="space-y-6">
              <Card>
                <CardContent className="pt-6">
                  <h3 className="text-lg font-semibold mb-4">Bottleneck Resources</h3>
                  <hr className="mb-4" />
                  {bottlenecks.length === 0 ? (
                    <Alert>
                      <AlertTitle>No Bottlenecks Detected</AlertTitle>
                      <AlertDescription>
                        All resources are operating within acceptable utilization levels (&lt;95%).
                      </AlertDescription>
                    </Alert>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Resource</TableHead>
                          <TableHead>Site</TableHead>
                          <TableHead className="text-right">Max Utilization</TableHead>
                          <TableHead className="text-right">Avg Utilization</TableHead>
                          <TableHead className="text-right">Overloaded Periods</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {bottlenecks.map((bottleneck) => (
                          <TableRow key={bottleneck.resource_id}>
                            <TableCell>
                              <div className="flex items-center gap-2">
                                <AlertTriangle className="h-4 w-4 text-amber-500" />
                                <span>{bottleneck.resource_name}</span>
                              </div>
                            </TableCell>
                            <TableCell>{bottleneck.site_name || 'N/A'}</TableCell>
                            <TableCell className="text-right">
                              <Badge variant={getUtilizationVariant(bottleneck.max_utilization_percent)}>
                                {bottleneck.max_utilization_percent.toFixed(1)}%
                              </Badge>
                            </TableCell>
                            <TableCell className="text-right">{bottleneck.avg_utilization_percent.toFixed(1)}%</TableCell>
                            <TableCell className="text-right">
                              <Badge variant={bottleneck.overloaded_periods > 0 ? 'destructive' : 'success'}>
                                {bottleneck.overloaded_periods}
                              </Badge>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
              {analysis && (
                <Card>
                  <CardContent className="pt-6">
                    <h3 className="text-lg font-semibold mb-4">Recommendations</h3>
                    <hr className="mb-4" />
                    {analysis.recommendations && analysis.recommendations.length > 0 ? (
                      <div className="space-y-2">
                        {analysis.recommendations.map((rec, idx) => (
                          <Alert key={idx}>
                            <AlertDescription>{rec}</AlertDescription>
                          </Alert>
                        ))}
                      </div>
                    ) : (
                      <p className="text-muted-foreground">No recommendations at this time.</p>
                    )}
                  </CardContent>
                </Card>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </Card>

      {/* Create Plan Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Create Capacity Plan</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="plan-name">Plan Name *</Label>
              <Input
                id="plan-name"
                value={planForm.name}
                onChange={(e) => setPlanForm({ ...planForm, name: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="plan-desc">Description</Label>
              <Textarea
                id="plan-desc"
                value={planForm.description}
                onChange={(e) => setPlanForm({ ...planForm, description: e.target.value })}
                rows={3}
                className="mt-1"
              />
            </div>
            <div>
              <Label>Supply Chain Config</Label>
              <p className="mt-1 text-sm text-muted-foreground">
                {activeConfig?.name || 'Loading...'}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="plan-horizon">Planning Horizon (weeks) *</Label>
                <Input
                  id="plan-horizon"
                  type="number"
                  value={planForm.planning_horizon_weeks}
                  onChange={(e) => setPlanForm({ ...planForm, planning_horizon_weeks: parseInt(e.target.value) })}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="plan-bucket">Bucket Size (days) *</Label>
                <Input
                  id="plan-bucket"
                  type="number"
                  value={planForm.bucket_size_days}
                  onChange={(e) => setPlanForm({ ...planForm, bucket_size_days: parseInt(e.target.value) })}
                  className="mt-1"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="plan-start">Start Date *</Label>
                <Input
                  id="plan-start"
                  type="date"
                  value={planForm.start_date}
                  onChange={(e) => setPlanForm({ ...planForm, start_date: e.target.value })}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="plan-end">End Date *</Label>
                <Input
                  id="plan-end"
                  type="date"
                  value={planForm.end_date}
                  onChange={(e) => setPlanForm({ ...planForm, end_date: e.target.value })}
                  className="mt-1"
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="is-scenario"
                checked={planForm.is_scenario}
                onCheckedChange={(checked) => setPlanForm({ ...planForm, is_scenario: checked })}
              />
              <Label htmlFor="is-scenario">This is a what-if scenario</Label>
            </div>
            {planForm.is_scenario && (
              <>
                <div>
                  <Label htmlFor="scenario-desc">Scenario Description</Label>
                  <Textarea
                    id="scenario-desc"
                    value={planForm.scenario_description}
                    onChange={(e) => setPlanForm({ ...planForm, scenario_description: e.target.value })}
                    rows={2}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor="base-plan">Base Plan</Label>
                  <select
                    id="base-plan"
                    value={planForm.base_plan_id || ''}
                    onChange={(e) => setPlanForm({ ...planForm, base_plan_id: e.target.value })}
                    className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
                  >
                    <option value="">None</option>
                    {plans.filter(p => !p.is_scenario).map((plan) => (
                      <option key={plan.id} value={plan.id}>{plan.name}</option>
                    ))}
                  </select>
                </div>
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleCreatePlan} disabled={!planForm.name || !effectiveConfigId}>
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Resource Dialog */}
      <Dialog open={resourceDialogOpen} onOpenChange={setResourceDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Add Capacity Resource</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="resource-name">Resource Name *</Label>
              <Input
                id="resource-name"
                value={resourceForm.resource_name}
                onChange={(e) => setResourceForm({ ...resourceForm, resource_name: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="resource-type">Resource Type *</Label>
              <select
                id="resource-type"
                value={resourceForm.resource_type}
                onChange={(e) => setResourceForm({ ...resourceForm, resource_type: e.target.value })}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="LABOR">Labor</option>
                <option value="MACHINE">Machine</option>
                <option value="FACILITY">Facility</option>
                <option value="UTILITY">Utility</option>
                <option value="TOOL">Tool</option>
              </select>
            </div>
            <div>
              <Label htmlFor="resource-site">Site *</Label>
              <select
                id="resource-site"
                value={resourceForm.site_id}
                onChange={(e) => setResourceForm({ ...resourceForm, site_id: e.target.value })}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="">Select site...</option>
                {sites.map((site) => (
                  <option key={site.id} value={site.id}>{site.name}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="available-capacity">Available Capacity *</Label>
                <Input
                  id="available-capacity"
                  type="number"
                  value={resourceForm.available_capacity}
                  onChange={(e) => setResourceForm({ ...resourceForm, available_capacity: parseFloat(e.target.value) })}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="capacity-unit">Capacity Unit *</Label>
                <Input
                  id="capacity-unit"
                  value={resourceForm.capacity_unit}
                  onChange={(e) => setResourceForm({ ...resourceForm, capacity_unit: e.target.value })}
                  className="mt-1"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="efficiency">Efficiency (%)</Label>
                <Input
                  id="efficiency"
                  type="number"
                  value={resourceForm.efficiency_percent}
                  onChange={(e) => setResourceForm({ ...resourceForm, efficiency_percent: parseFloat(e.target.value) })}
                  min={0}
                  max={100}
                  step={0.1}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="target-util">Target Utilization (%)</Label>
                <Input
                  id="target-util"
                  type="number"
                  value={resourceForm.utilization_target_percent}
                  onChange={(e) => setResourceForm({ ...resourceForm, utilization_target_percent: parseFloat(e.target.value) })}
                  min={0}
                  max={100}
                  step={0.1}
                  className="mt-1"
                />
              </div>
            </div>
            <div>
              <Label htmlFor="cost-hour">Cost per Hour</Label>
              <Input
                id="cost-hour"
                type="number"
                value={resourceForm.cost_per_hour}
                onChange={(e) => setResourceForm({ ...resourceForm, cost_per_hour: parseFloat(e.target.value) })}
                min={0}
                step={0.01}
                className="mt-1"
              />
            </div>
            <hr />
            <p className="text-sm font-medium">Shift Configuration</p>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <Label htmlFor="shifts-day">Shifts per Day</Label>
                <Input
                  id="shifts-day"
                  type="number"
                  value={resourceForm.shifts_per_day}
                  onChange={(e) => setResourceForm({ ...resourceForm, shifts_per_day: parseInt(e.target.value) })}
                  min={1}
                  max={3}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="hours-shift">Hours per Shift</Label>
                <Input
                  id="hours-shift"
                  type="number"
                  value={resourceForm.hours_per_shift}
                  onChange={(e) => setResourceForm({ ...resourceForm, hours_per_shift: parseInt(e.target.value) })}
                  min={1}
                  max={24}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="days-week">Working Days/Week</Label>
                <Input
                  id="days-week"
                  type="number"
                  value={resourceForm.working_days_per_week}
                  onChange={(e) => setResourceForm({ ...resourceForm, working_days_per_week: parseInt(e.target.value) })}
                  min={1}
                  max={7}
                  className="mt-1"
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResourceDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleCreateResource} disabled={!resourceForm.resource_name || !resourceForm.site_id}>
              Add Resource
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default CapacityPlanning;
