import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Input,
  Spinner,
  Progress,
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
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from '../../components/common';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../../components/ui/tooltip';
import {
  Play,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Clock,
  Download,
  Eye,
  ThumbsUp,
  ThumbsDown,
  ShieldCheck,
} from 'lucide-react';
import { api } from '../../services/api';
import { getSupplyChainConfigs } from '../../services/supplyChainConfigService';

const SupplyPlanGeneration = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [configs, setConfigs] = useState([]);
  const [planRequests, setPlanRequests] = useState([]);

  // Generation parameters
  const [configId, setConfigId] = useState('');
  const [agentStrategy, setAgentStrategy] = useState('ml_forecast');
  const [numScenarios, setNumScenarios] = useState(1000);
  const [planningHorizon, setPlanningHorizon] = useState(52);

  // Stochastic parameters
  const [stochasticParams, setStochasticParams] = useState({
    lead_time_variability: 0.1,
    yield_variability: 0.05,
    demand_variability: 0.15,
    capacity_variability: 0.1,
  });

  // Objectives
  const [objectives, setObjectives] = useState({
    planning_horizon: 52,
    target_service_level: 0.95,
    inventory_target_days: 30,
    minimize_cost: true,
    maximize_otif: true,
  });

  // Active plan tracking
  const [activePlan, setActivePlan] = useState(null);
  const [planStatus, setPlanStatus] = useState(null);
  const [planResult, setPlanResult] = useState(null);
  const [statusPolling, setStatusPolling] = useState(null);

  useEffect(() => {
    loadConfigs();
    loadPlanRequests();
  }, []);

  useEffect(() => {
    setObjectives((prev) => ({ ...prev, planning_horizon: planningHorizon }));
  }, [planningHorizon]);

  useEffect(() => {
    if (activePlan && statusPolling) {
      const interval = setInterval(async () => {
        try {
          const response = await api.get(`/supply-plan/status/${activePlan}`);
          setPlanStatus(response.data);

          if (response.data.status === 'COMPLETED') {
            clearInterval(interval);
            setStatusPolling(false);
            await loadPlanResult(activePlan);
            await loadPlanRequests();
          } else if (response.data.status === 'FAILED') {
            clearInterval(interval);
            setStatusPolling(false);
            setError(response.data.error_message || 'Plan generation failed');
          }
        } catch (err) {
          console.error('Error polling status:', err);
        }
      }, 2000);

      return () => clearInterval(interval);
    }
  }, [activePlan, statusPolling]);

  const loadConfigs = async () => {
    try {
      const configs = await getSupplyChainConfigs();
      setConfigs(configs || []);
    } catch (err) {
      console.error('Error loading configs:', err);
    }
  };

  const loadPlanRequests = async () => {
    try {
      const response = await api.get('/supply-plan/list');
      setPlanRequests(response.data.plans || []);
    } catch (err) {
      console.error('Error loading plan requests:', err);
    }
  };

  const loadPlanResult = async (taskId) => {
    try {
      const response = await api.get(`/supply-plan/result/${taskId}`);
      setPlanResult(response.data);
      setError(null);
    } catch (err) {
      console.error('Error loading plan result:', err);
      setError(err.response?.data?.detail || err.message);
    }
  };

  const handleGeneratePlan = async () => {
    if (!configId) {
      setError('Please select a supply chain configuration');
      return;
    }

    setLoading(true);
    setError(null);
    setPlanResult(null);

    try {
      const response = await api.post('/supply-plan/generate', {
        config_id: parseInt(configId),
        agent_strategy: agentStrategy,
        num_scenarios: numScenarios,
        stochastic_params: stochasticParams,
        objectives: objectives,
      });

      setActivePlan(response.data.task_id);
      setPlanStatus({ status: 'RUNNING', progress: 0.0 });
      setStatusPolling(true);

      alert(response.data.message || 'Supply plan generation started');
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleViewPlan = async (taskId) => {
    setActivePlan(taskId);
    setPlanStatus(null);
    setPlanResult(null);

    try {
      const statusResponse = await api.get(`/supply-plan/status/${taskId}`);
      setPlanStatus(statusResponse.data);

      if (statusResponse.data.status === 'COMPLETED') {
        await loadPlanResult(taskId);
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    }
  };

  const handleApprovePlan = async (taskId) => {
    try {
      await api.post(`/supply-plan/approve/${taskId}`);
      alert('Supply plan approved successfully');
      await loadPlanRequests();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    }
  };

  const handleRejectPlan = async (taskId) => {
    try {
      await api.post(`/supply-plan/reject/${taskId}`);
      alert('Supply plan rejected');
      await loadPlanRequests();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    }
  };

  const getStatusVariant = (status) => {
    switch (status) {
      case 'COMPLETED':
        return 'success';
      case 'RUNNING':
        return 'info';
      case 'FAILED':
        return 'destructive';
      case 'PENDING':
        return 'warning';
      default:
        return 'secondary';
    }
  };

  const renderGenerationForm = () => (
    <Card className="mb-6">
      <CardContent className="pt-4">
        <h2 className="text-lg font-semibold mb-4">Generate New Supply Plan</h2>
        <hr className="mb-4" />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <Label>Supply Chain Configuration</Label>
            <Select value={configId} onValueChange={setConfigId}>
              <SelectTrigger>
                <SelectValue placeholder="Select configuration" />
              </SelectTrigger>
              <SelectContent>
                {configs.map((config) => (
                  <SelectItem key={config.id} value={String(config.id)}>
                    {config.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label>Planning Strategy</Label>
            <Select value={agentStrategy} onValueChange={setAgentStrategy}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="naive">Naive (Baseline)</SelectItem>
                <SelectItem value="conservative">Conservative</SelectItem>
                <SelectItem value="ml_forecast">ML Forecast (Recommended)</SelectItem>
                <SelectItem value="optimizer">Cost Optimizer</SelectItem>
                <SelectItem value="reactive">Reactive</SelectItem>
                <SelectItem value="llm">LLM Agent (GPT-4)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label>Planning Horizon (Weeks)</Label>
            <Input
              type="number"
              value={planningHorizon}
              onChange={(e) => setPlanningHorizon(parseInt(e.target.value))}
              min={1}
              max={104}
            />
          </div>

          <div>
            <Label>Monte Carlo Scenarios</Label>
            <Input
              type="number"
              value={numScenarios}
              onChange={(e) => setNumScenarios(parseInt(e.target.value))}
              min={100}
              max={10000}
            />
          </div>

          <div className="col-span-2">
            <Accordion type="single" collapsible>
              <AccordionItem value="stochastic">
                <AccordionTrigger className="text-sm">
                  Stochastic Parameters (Advanced)
                </AccordionTrigger>
                <AccordionContent>
                  <div className="grid grid-cols-2 gap-4 pt-2">
                    <div>
                      <Label>Lead Time Variability</Label>
                      <Input
                        type="number"
                        value={stochasticParams.lead_time_variability}
                        onChange={(e) =>
                          setStochasticParams({
                            ...stochasticParams,
                            lead_time_variability: parseFloat(e.target.value),
                          })
                        }
                        min={0}
                        max={1}
                        step={0.01}
                      />
                    </div>
                    <div>
                      <Label>Yield Variability</Label>
                      <Input
                        type="number"
                        value={stochasticParams.yield_variability}
                        onChange={(e) =>
                          setStochasticParams({
                            ...stochasticParams,
                            yield_variability: parseFloat(e.target.value),
                          })
                        }
                        min={0}
                        max={1}
                        step={0.01}
                      />
                    </div>
                    <div>
                      <Label>Demand Variability</Label>
                      <Input
                        type="number"
                        value={stochasticParams.demand_variability}
                        onChange={(e) =>
                          setStochasticParams({
                            ...stochasticParams,
                            demand_variability: parseFloat(e.target.value),
                          })
                        }
                        min={0}
                        max={1}
                        step={0.01}
                      />
                    </div>
                    <div>
                      <Label>Capacity Variability</Label>
                      <Input
                        type="number"
                        value={stochasticParams.capacity_variability}
                        onChange={(e) =>
                          setStochasticParams({
                            ...stochasticParams,
                            capacity_variability: parseFloat(e.target.value),
                          })
                        }
                        min={0}
                        max={1}
                        step={0.01}
                      />
                    </div>
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>

          <div className="col-span-2">
            <Button
              className="w-full"
              onClick={handleGeneratePlan}
              disabled={loading || !configId}
              leftIcon={loading ? <Spinner size="sm" /> : <Play className="h-4 w-4" />}
            >
              {loading ? 'Generating...' : 'Generate Supply Plan'}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );

  const renderActiveStatus = () => {
    if (!activePlan || !planStatus) return null;

    return (
      <Card className="mb-6">
        <CardContent className="pt-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">Active Plan Generation</h2>
            <Badge variant={getStatusVariant(planStatus.status)}>{planStatus.status}</Badge>
          </div>

          {planStatus.status === 'RUNNING' && (
            <>
              <p className="text-sm text-muted-foreground mb-2">
                Progress: {(planStatus.progress * 100).toFixed(0)}%
              </p>
              <Progress value={planStatus.progress * 100} className="mb-4" />
            </>
          )}

          {planStatus.error_message && (
            <Alert variant="destructive" className="mt-4">
              {planStatus.error_message}
            </Alert>
          )}
        </CardContent>
      </Card>
    );
  };

  const renderPlanResult = () => {
    if (!planResult || !planResult.scorecard) return null;

    const { scorecard } = planResult;
    const financial = scorecard.financial || {};
    const customer = scorecard.customer || {};
    const operational = scorecard.operational || {};

    return (
      <Card className="mb-6">
        <CardContent className="pt-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">Supply Plan Results</h2>
            <div className="flex gap-1">
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="ghost" size="sm" onClick={() => handleApprovePlan(activePlan)}>
                      <ThumbsUp className="h-4 w-4 text-green-600" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Approve Plan</TooltipContent>
                </Tooltip>
              </TooltipProvider>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="ghost" size="sm" onClick={() => handleRejectPlan(activePlan)}>
                      <ThumbsDown className="h-4 w-4 text-red-600" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Reject Plan</TooltipContent>
                </Tooltip>
              </TooltipProvider>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="ghost" size="sm">
                      <Download className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Download Report</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          </div>

          <hr className="mb-4" />

          <h3 className="text-md font-medium mb-4">Probabilistic Balanced Scorecard</h3>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="border">
              <CardContent className="pt-4">
                <p className="text-xs uppercase text-muted-foreground">Financial</p>
                <p className="text-3xl font-bold text-primary">
                  ${financial.total_cost?.expected?.toFixed(0) || 'N/A'}
                </p>
                <p className="text-sm text-muted-foreground">Expected Total Cost</p>
                {financial.total_cost && (
                  <p className="text-xs text-muted-foreground mt-2">
                    P10: ${financial.total_cost.p10?.toFixed(0)} | P90: ${financial.total_cost.p90?.toFixed(0)}
                  </p>
                )}
              </CardContent>
            </Card>

            <Card className="border">
              <CardContent className="pt-4">
                <p className="text-xs uppercase text-muted-foreground">Customer</p>
                <p className="text-3xl font-bold text-green-600">
                  {customer.otif?.expected ? (customer.otif.expected * 100).toFixed(1) + '%' : 'N/A'}
                </p>
                <p className="text-sm text-muted-foreground">Expected OTIF</p>
                {customer.otif?.probability_above_target && (
                  <div className="mt-2">
                    <Badge variant="success" className="flex items-center gap-1 w-fit">
                      <CheckCircle className="h-3 w-3" />
                      {(customer.otif.probability_above_target * 100).toFixed(0)}% chance &gt; 95%
                    </Badge>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="border">
              <CardContent className="pt-4">
                <p className="text-xs uppercase text-muted-foreground">Operational</p>
                <p className="text-3xl font-bold text-blue-600">
                  {operational.inventory_turns?.expected?.toFixed(2) || 'N/A'}
                </p>
                <p className="text-sm text-muted-foreground">Expected Inventory Turns</p>
                {operational.bullwhip_ratio?.expected && (
                  <p className="text-xs text-muted-foreground mt-2">
                    Bullwhip: {operational.bullwhip_ratio.expected.toFixed(2)}
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          {planResult.recommendations && planResult.recommendations.length > 0 && (
            <div className="mt-6">
              <h3 className="text-md font-medium mb-2">Recommendations</h3>
              {planResult.recommendations.map((rec, idx) => (
                <Alert key={idx} variant="info" className="mb-2">
                  {rec}
                </Alert>
              ))}
            </div>
          )}

          {/* Plan Confidence Score (Conformal Prediction) */}
          {planResult.plan_confidence && (
            <div className="mt-6">
              <h3 className="text-md font-medium mb-4 flex items-center gap-2">
                <ShieldCheck className="h-5 w-5" />
                Plan Confidence
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card className="border">
                  <CardContent className="pt-4">
                    <p className="text-xs uppercase text-muted-foreground">Overall Confidence</p>
                    <p className={`text-3xl font-bold ${
                      planResult.plan_confidence.confidence_level === 'high' ? 'text-green-600' :
                      planResult.plan_confidence.confidence_level === 'moderate' ? 'text-amber-600' :
                      'text-red-600'
                    }`}>
                      {(planResult.plan_confidence.overall * 100).toFixed(0)}%
                    </p>
                    <Badge variant={
                      planResult.plan_confidence.confidence_level === 'high' ? 'success' :
                      planResult.plan_confidence.confidence_level === 'moderate' ? 'warning' :
                      'destructive'
                    } className="mt-1">
                      {planResult.plan_confidence.confidence_level}
                    </Badge>
                  </CardContent>
                </Card>
                <Card className="border">
                  <CardContent className="pt-4">
                    <p className="text-xs uppercase text-muted-foreground">Demand Coverage</p>
                    <p className="text-2xl font-bold">
                      {(planResult.plan_confidence.demand_coverage_score * 100).toFixed(0)}%
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Forecasts with conformal intervals
                    </p>
                  </CardContent>
                </Card>
                <Card className="border">
                  <CardContent className="pt-4">
                    <p className="text-xs uppercase text-muted-foreground">Lead Time Coverage</p>
                    <p className="text-2xl font-bold">
                      {(planResult.plan_confidence.lead_time_coverage_score * 100).toFixed(0)}%
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Plans with LT intervals
                    </p>
                  </CardContent>
                </Card>
                <Card className="border">
                  <CardContent className="pt-4">
                    <p className="text-xs uppercase text-muted-foreground">Safety Stock Adequacy</p>
                    <p className="text-2xl font-bold">
                      {(planResult.plan_confidence.safety_stock_adequacy * 100).toFixed(0)}%
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      SS targets covering demand-during-LT
                    </p>
                  </CardContent>
                </Card>
              </div>
              {planResult.plan_confidence.diagnostics && (
                <p className="text-xs text-muted-foreground mt-2">
                  {Object.values(planResult.plan_confidence.diagnostics).join(' | ')}
                </p>
              )}
            </div>
          )}

          {/* Conformal Interval Summary */}
          {planResult.conformal_summary && (
            <div className="mt-4 p-3 bg-muted/50 rounded-lg">
              <p className="text-sm font-medium mb-1">Conformal Interval Coverage</p>
              <div className="flex gap-4 text-xs text-muted-foreground">
                <span>Plans with demand intervals: {planResult.conformal_summary.plans_with_demand_interval || 0}/{planResult.conformal_summary.total_plans || 0}</span>
                <span>Plans with LT intervals: {planResult.conformal_summary.plans_with_lt_interval || 0}/{planResult.conformal_summary.total_plans || 0}</span>
                {planResult.conformal_summary.avg_demand_coverage && (
                  <span>Avg demand coverage: {(planResult.conformal_summary.avg_demand_coverage * 100).toFixed(0)}%</span>
                )}
                {planResult.conformal_summary.avg_lt_coverage && (
                  <span>Avg LT coverage: {(planResult.conformal_summary.avg_lt_coverage * 100).toFixed(0)}%</span>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    );
  };

  const renderPlanHistory = () => (
    <Card>
      <CardContent className="pt-4">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold">Plan Generation History</h2>
          <Button variant="outline" size="sm" onClick={loadPlanRequests} leftIcon={<RefreshCw className="h-4 w-4" />}>
            Refresh
          </Button>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Configuration</TableHead>
              <TableHead>Strategy</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Progress</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Completed</TableHead>
              <TableHead className="text-center">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {planRequests.map((plan) => (
              <TableRow key={plan.id}>
                <TableCell>{plan.id}</TableCell>
                <TableCell>{plan.config_name}</TableCell>
                <TableCell>
                  <Badge>{plan.agent_strategy}</Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={getStatusVariant(plan.status)}>{plan.status}</Badge>
                </TableCell>
                <TableCell className="text-right">{(plan.progress * 100).toFixed(0)}%</TableCell>
                <TableCell>{new Date(plan.created_at).toLocaleString()}</TableCell>
                <TableCell>{plan.completed_at ? new Date(plan.completed_at).toLocaleString() : 'N/A'}</TableCell>
                <TableCell className="text-center">
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleViewPlan(plan.id)}
                          disabled={plan.status === 'PENDING'}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>View Details</TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-2">
          <Clock className="h-8 w-8 text-primary" />
          <h1 className="text-2xl font-bold">Supply Plan Generation</h1>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {renderGenerationForm()}
      {renderActiveStatus()}
      {renderPlanResult()}
      {renderPlanHistory()}
    </div>
  );
};

export default SupplyPlanGeneration;
