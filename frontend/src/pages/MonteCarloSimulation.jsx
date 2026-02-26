import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
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
  XCircle,
  CheckCircle,
  Clock,
  AlertCircle,
  Activity,
  BarChart3,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { getSupplyChainConfigs } from '../services/supplyChainConfigService';
import MonteCarloResultsView from '../components/montecarlo/MonteCarloResultsView';

const MonteCarloSimulation = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [currentTab, setCurrentTab] = useState('list');
  const [runs, setRuns] = useState([]);
  const [configs, setConfigs] = useState([]);
  const [mpsPlans, setMpsPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedRun, setSelectedRun] = useState(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newRun, setNewRun] = useState({
    name: '',
    description: '',
    supply_chain_config_id: '',
    mps_plan_id: null,
    num_scenarios: 1000,
    random_seed: null,
    planning_horizon_weeks: 52,
  });

  useEffect(() => {
    loadRuns();
    loadConfigs();
    loadMpsPlans();

    // Poll for running simulations every 5 seconds
    const intervalId = setInterval(() => {
      loadRuns(false); // Silent refresh
    }, 5000);

    return () => clearInterval(intervalId);
  }, []);

  const loadRuns = async (showLoading = true) => {
    try {
      if (showLoading) setLoading(true);
      const response = await api.get('/monte-carlo/runs?limit=50');
      setRuns(response.data);
    } catch (error) {
      console.error('Error loading Monte Carlo runs:', error);
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  const loadConfigs = async () => {
    try {
      const configs = await getSupplyChainConfigs();
      setConfigs(configs || []);
    } catch (error) {
      console.error('Error loading configs:', error);
    }
  };

  const loadMpsPlans = async () => {
    try {
      const response = await api.get('/mps/plans');
      setMpsPlans(response.data);
    } catch (error) {
      console.error('Error loading MPS plans:', error);
    }
  };

  const handleCreateRun = async () => {
    try {
      const payload = {
        ...newRun,
        tenant_id: user?.tenant_id || 1,
      };

      await api.post('/monte-carlo/runs', payload);
      setCreateDialogOpen(false);
      setNewRun({
        name: '',
        description: '',
        supply_chain_config_id: '',
        mps_plan_id: null,
        num_scenarios: 1000,
        random_seed: null,
        planning_horizon_weeks: 52,
      });
      loadRuns();
    } catch (error) {
      console.error('Error creating Monte Carlo run:', error);
      alert('Failed to create Monte Carlo run: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleCancelRun = async (runId) => {
    if (!window.confirm('Are you sure you want to cancel this simulation?')) return;

    try {
      await api.post(`/monte-carlo/runs/${runId}/cancel`);
      loadRuns();
    } catch (error) {
      console.error('Error cancelling run:', error);
      alert('Failed to cancel run: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleDeleteRun = async (runId) => {
    if (!window.confirm('Are you sure you want to delete this run? This cannot be undone.')) return;

    try {
      await api.delete(`/monte-carlo/runs/${runId}`);
      loadRuns();
    } catch (error) {
      console.error('Error deleting run:', error);
      alert('Failed to delete run: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleViewRun = (run) => {
    setSelectedRun(run);
    setCurrentTab('results');
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'COMPLETED':
        return <CheckCircle className="h-4 w-4 text-green-600" />;
      case 'RUNNING':
        return <Clock className="h-4 w-4 text-primary animate-spin" />;
      case 'QUEUED':
        return <Clock className="h-4 w-4 text-muted-foreground" />;
      case 'FAILED':
        return <AlertCircle className="h-4 w-4 text-destructive" />;
      case 'CANCELLED':
        return <XCircle className="h-4 w-4 text-muted-foreground" />;
      default:
        return null;
    }
  };

  const getStatusVariant = (status) => {
    switch (status) {
      case 'COMPLETED':
        return 'success';
      case 'RUNNING':
        return 'info';
      case 'QUEUED':
        return 'secondary';
      case 'FAILED':
        return 'destructive';
      case 'CANCELLED':
        return 'secondary';
      default:
        return 'secondary';
    }
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleString();
  };

  const formatDuration = (seconds) => {
    if (!seconds) return 'N/A';
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
    return `${(seconds / 3600).toFixed(1)}h`;
  };

  // Summary Statistics Cards
  const renderSummaryCards = () => {
    const completedRuns = runs.filter(r => r.status === 'COMPLETED').length;
    const runningRuns = runs.filter(r => r.status === 'RUNNING').length;
    const queuedRuns = runs.filter(r => r.status === 'QUEUED').length;

    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Total Runs</p>
            <p className="text-4xl font-bold">{runs.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Completed</p>
            <p className="text-4xl font-bold text-green-600">{completedRuns}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Running</p>
            <p className="text-4xl font-bold text-primary">{runningRuns}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-1">Queued</p>
            <p className="text-4xl font-bold">{queuedRuns}</p>
          </CardContent>
        </Card>
      </div>
    );
  };

  // Runs List View
  const renderRunsList = () => (
    <div>
      {renderSummaryCards()}

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Status</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Configuration</TableHead>
                <TableHead className="text-right">Scenarios</TableHead>
                <TableHead className="text-right">Progress</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-8">
                    <p className="text-muted-foreground">
                      No Monte Carlo simulations found. Create your first simulation to get started.
                    </p>
                  </TableCell>
                </TableRow>
              ) : (
                runs.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell>
                      <Badge variant={getStatusVariant(run.status)} className="flex items-center gap-1 w-fit">
                        {getStatusIcon(run.status)}
                        {run.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <p className="font-medium">{run.name}</p>
                      {run.description && (
                        <p className="text-xs text-muted-foreground">{run.description}</p>
                      )}
                    </TableCell>
                    <TableCell>{run.config_name}</TableCell>
                    <TableCell className="text-right">
                      {run.scenarios_completed} / {run.num_scenarios}
                    </TableCell>
                    <TableCell className="text-right">
                      {run.status === 'RUNNING' || run.status === 'QUEUED' ? (
                        <div className="w-full">
                          <div className="w-full bg-secondary rounded-full h-2 mb-1">
                            <div
                              className="bg-primary h-2 rounded-full"
                              style={{ width: `${run.progress_percent}%` }}
                            />
                          </div>
                          <span className="text-xs">{run.progress_percent.toFixed(1)}%</span>
                        </div>
                      ) : (
                        <span>{run.status === 'COMPLETED' ? '100%' : '-'}</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <span className="text-xs">
                        {run.started_at ? formatDate(run.started_at) : '-'}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-xs">{formatDuration(run.execution_time_seconds)}</span>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        {run.status === 'COMPLETED' && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => handleViewRun(run)}
                                >
                                  <BarChart3 className="h-4 w-4 text-primary" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>View Results</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                        {(run.status === 'RUNNING' || run.status === 'QUEUED') && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => handleCancelRun(run.id)}
                                >
                                  <XCircle className="h-4 w-4 text-destructive" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Cancel</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                        {(run.status === 'QUEUED' || run.status === 'FAILED') && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => handleDeleteRun(run.id)}
                                >
                                  <Trash2 className="h-4 w-4 text-destructive" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Delete</TooltipContent>
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
        </CardContent>
      </Card>
    </div>
  );

  // Create Dialog
  const renderCreateDialog = () => (
    <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create Monte Carlo Simulation</DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <div className="col-span-2">
            <Label htmlFor="sim-name">Simulation Name *</Label>
            <Input
              id="sim-name"
              value={newRun.name}
              onChange={(e) => setNewRun({ ...newRun, name: e.target.value })}
              className="mt-1"
            />
          </div>
          <div className="col-span-2">
            <Label htmlFor="sim-desc">Description</Label>
            <Textarea
              id="sim-desc"
              value={newRun.description}
              onChange={(e) => setNewRun({ ...newRun, description: e.target.value })}
              rows={2}
              className="mt-1"
            />
          </div>
          <div className="col-span-2">
            <Label htmlFor="sim-config">Supply Chain Configuration *</Label>
            <select
              id="sim-config"
              value={newRun.supply_chain_config_id}
              onChange={(e) => setNewRun({ ...newRun, supply_chain_config_id: e.target.value })}
              className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
            >
              <option value="">Select configuration</option>
              {configs.map((config) => (
                <option key={config.id} value={config.id}>
                  {config.name}
                </option>
              ))}
            </select>
          </div>
          <div className="col-span-2">
            <Label htmlFor="sim-mps">MPS Plan (Optional)</Label>
            <select
              id="sim-mps"
              value={newRun.mps_plan_id || ''}
              onChange={(e) => setNewRun({ ...newRun, mps_plan_id: e.target.value || null })}
              className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
            >
              <option value="">None</option>
              {mpsPlans.map((plan) => (
                <option key={plan.id} value={plan.id}>
                  {plan.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="sim-scenarios">Number of Scenarios</Label>
            <Input
              id="sim-scenarios"
              type="number"
              value={newRun.num_scenarios}
              onChange={(e) => setNewRun({ ...newRun, num_scenarios: parseInt(e.target.value) })}
              min={100}
              max={10000}
              step={100}
              className="mt-1"
            />
            <p className="text-xs text-muted-foreground mt-1">
              More scenarios = better accuracy but longer execution time
            </p>
          </div>
          <div>
            <Label htmlFor="sim-horizon">Planning Horizon (weeks)</Label>
            <Input
              id="sim-horizon"
              type="number"
              value={newRun.planning_horizon_weeks}
              onChange={(e) => setNewRun({ ...newRun, planning_horizon_weeks: parseInt(e.target.value) })}
              min={4}
              max={104}
              className="mt-1"
            />
          </div>
          <div className="col-span-2">
            <Label htmlFor="sim-seed">Random Seed (Optional)</Label>
            <Input
              id="sim-seed"
              type="number"
              value={newRun.random_seed || ''}
              onChange={(e) => setNewRun({ ...newRun, random_seed: e.target.value ? parseInt(e.target.value) : null })}
              className="mt-1"
            />
            <p className="text-xs text-muted-foreground mt-1">
              Set for reproducible results, leave empty for random
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleCreateRun}
            disabled={!newRun.name || !newRun.supply_chain_config_id}
          >
            Create & Run
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  if (loading) {
    return (
      <div className="container mx-auto py-8 px-4 max-w-7xl">
        <div className="flex justify-center items-center min-h-[400px]">
          <Spinner size="lg" />
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      {/* Header */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <h1 className="text-3xl font-bold mb-2">Monte Carlo Simulation</h1>
          <p className="text-muted-foreground">
            Probabilistic supply chain planning with confidence intervals and risk analysis
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => loadRuns()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button onClick={() => setCreateDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            New Simulation
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={currentTab} onValueChange={setCurrentTab} className="mb-6">
        <TabsList>
          <TabsTrigger value="list" className="flex items-center gap-2">
            <Activity className="h-4 w-4" />
            All Simulations
          </TabsTrigger>
          <TabsTrigger
            value="results"
            disabled={!selectedRun || selectedRun.status !== 'COMPLETED'}
            className="flex items-center gap-2"
          >
            <BarChart3 className="h-4 w-4" />
            Results View
          </TabsTrigger>
        </TabsList>

        <TabsContent value="list">
          {renderRunsList()}
        </TabsContent>

        <TabsContent value="results">
          {selectedRun && (
            <MonteCarloResultsView run={selectedRun} onBack={() => setCurrentTab('list')} />
          )}
        </TabsContent>
      </Tabs>

      {/* Create Dialog */}
      {renderCreateDialog()}
    </div>
  );
};

export default MonteCarloSimulation;
