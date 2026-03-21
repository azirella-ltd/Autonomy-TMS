import React, { useState, useEffect, useCallback } from 'react';
import {
  Alert,
  AlertDescription,
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Spinner,
  Input,
  Label,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from '../../components/common';
import {
  Calendar,
  TrendingUp,
  Users,
  DollarSign,
  Target,
  BarChart3,
  Play,
  RefreshCw,
  CheckCircle,
  AlertTriangle,
  Sparkles,
  ShieldCheck,
  Clock,
  ArrowRight,
  Settings,
} from 'lucide-react';
import { api } from '../../services/api';
import RoleTimeSeries from '../../components/charts/RoleTimeSeries';

/**
 * Sales & Operations Planning (S&OP) - Strategic Planning
 *
 * Integrated with Conformal Prediction for uncertainty quantification.
 *
 * S&OP is a cross-functional planning process that aligns:
 * - Demand plans (from sales/marketing)
 * - Supply plans (from operations)
 * - Financial plans (from finance)
 *
 * Features:
 * - Conformal prediction-based scenario generation
 * - Rolling horizon planning with learning loop
 * - Probabilistic outcomes with coverage guarantees
 *
 * Planning Horizon: Typically 18-36 months
 * Planning Frequency: Monthly cycles
 */
const SalesOperationsPlanning = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  // S&OP State
  const [conformalStatus, setConformalStatus] = useState(null);
  const [sopPerformance, setSopPerformance] = useState(null);
  const [sopHistory, setSopHistory] = useState([]);
  const [learningProgress, setLearningProgress] = useState(null);
  const [latestCycle, setLatestCycle] = useState(null);

  // Form state for running a cycle
  const [planningDate, setPlanningDate] = useState(new Date().toISOString().split('T')[0]);
  const [maxInvestment, setMaxInvestment] = useState('');

  // Load data
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [statusRes, perfRes, historyRes, progressRes] = await Promise.all([
        api.get('/conformal-prediction/suite/status').catch(() => ({ data: null })),
        api.get('/conformal-prediction/sop/performance').catch(() => ({ data: null })),
        api.get('/conformal-prediction/sop/history').catch(() => ({ data: { cycles: [] } })),
        api.get('/conformal-prediction/sop/learning-progress').catch(() => ({ data: null })),
      ]);

      setConformalStatus(statusRes.data);
      setSopPerformance(perfRes.data);
      setSopHistory(historyRes.data?.cycles || []);
      setLearningProgress(progressRes.data);

      if (historyRes.data?.cycles?.length > 0) {
        setLatestCycle(historyRes.data.cycles[0]);
      }
    } catch (err) {
      console.error('Failed to load S&OP data:', err);
      setError('Failed to load S&OP data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRunCycle = async () => {
    setLoading(true);
    setError(null);
    try {
      // Demo data for the cycle
      const response = await api.post('/conformal-prediction/sop/run-cycle', {
        planning_date: planningDate,
        demand_forecasts: {
          "('PROD001', 1)": [100, 105, 110, 108, 112, 115, 118, 120, 125, 122, 128, 130],
          "('PROD002', 2)": [80, 82, 85, 88, 90, 92, 95, 98, 100, 102, 105, 108],
        },
        expected_lead_times: {
          'SUP001': 5,
        },
        max_investment: maxInvestment ? parseFloat(maxInvestment) : null,
      });

      setLatestCycle(response.data);
      setSuccess('S&OP cycle completed successfully!');
      loadData();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleObserveActuals = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.post('/conformal-prediction/sop/observe-actuals', {
        observation_date: planningDate,
        actual_demands: {
          "('PROD001', 1)": 98,
          "('PROD002', 2)": 85,
        },
        forecasts_used: {
          "('PROD001', 1)": 100,
          "('PROD002', 2)": 80,
        },
        actual_lead_times: {
          'SUP001': 6,
        },
        promised_lead_times: {
          'SUP001': 5,
        },
      });

      setSuccess('Actuals observed! Conformal predictors updated.');
      loadData();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const CoverageGuaranteeBadge = ({ value }) => {
    const pct = (value * 100).toFixed(0);
    const variant = pct >= 80 ? 'success' : pct >= 70 ? 'warning' : 'destructive';
    return (
      <Badge variant={variant} className="text-lg px-3 py-1">
        <ShieldCheck className="h-4 w-4 mr-1" />
        {pct}% Coverage
      </Badge>
    );
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      {/* Role time series header */}
      <RoleTimeSeries roleKey="sop" compact className="mb-4" />

      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Calendar className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">Sales & Operations Planning</h1>
            <p className="text-sm text-muted-foreground">
              Rolling horizon planning with conformal prediction
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={loadData} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {/* Key Metrics Summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Joint Coverage</p>
                <p className="text-2xl font-bold">
                  {conformalStatus?.joint_coverage_guarantee
                    ? `${(conformalStatus.joint_coverage_guarantee * 100).toFixed(0)}%`
                    : '--'}
                </p>
              </div>
              <div className="p-2 bg-amber-100 dark:bg-amber-900/30 rounded-lg">
                <ShieldCheck className="h-6 w-6 text-amber-600" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Planning Cycles</p>
                <p className="text-2xl font-bold">{sopHistory.length}</p>
              </div>
              <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                <Clock className="h-6 w-6 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Predictors</p>
                <p className="text-2xl font-bold">
                  {(conformalStatus?.summary?.demand_predictors || 0) +
                    (conformalStatus?.summary?.lead_time_predictors || 0)}
                </p>
              </div>
              <div className="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-lg">
                <Sparkles className="h-6 w-6 text-purple-600" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Learning Progress</p>
                <p className="text-2xl font-bold">
                  {learningProgress?.improvement
                    ? `${learningProgress.improvement > 0 ? '+' : ''}${(learningProgress.improvement * 100).toFixed(0)}%`
                    : '--'}
                </p>
              </div>
              <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
                <TrendingUp className="h-6 w-6 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <Target className="h-4 w-4" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="run-cycle" className="flex items-center gap-2">
            <Play className="h-4 w-4" />
            Run Cycle
          </TabsTrigger>
          <TabsTrigger value="history" className="flex items-center gap-2">
            <Clock className="h-4 w-4" />
            History
          </TabsTrigger>
          <TabsTrigger value="learning" className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Learning
          </TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview">
          <div className="grid grid-cols-2 gap-6">
            {/* S&OP Process Steps */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5" />
                  Monthly S&OP Cycle
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {[
                    { step: 1, name: 'Data Gathering', desc: 'Collect actuals, forecasts, market intelligence', icon: BarChart3 },
                    { step: 2, name: 'Scenario Generation', desc: 'Generate conformal prediction scenarios', icon: Sparkles },
                    { step: 3, name: 'Stochastic Optimization', desc: 'Solve two-stage stochastic program', icon: Target },
                    { step: 4, name: 'Decision Review', desc: 'Review first-stage decisions with coverage', icon: CheckCircle },
                    { step: 5, name: 'Observe Actuals', desc: 'Update predictors with realized outcomes', icon: RefreshCw },
                  ].map((item) => (
                    <div key={item.step} className="flex items-center gap-3 p-3 border rounded-lg">
                      <div className="w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-sm">
                        {item.step}
                      </div>
                      <div className="flex-1">
                        <h3 className="font-medium">{item.name}</h3>
                        <p className="text-xs text-muted-foreground">{item.desc}</p>
                      </div>
                      <item.icon className="h-5 w-5 text-muted-foreground" />
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Latest Cycle Results */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <CheckCircle className="h-5 w-5" />
                  Latest Cycle Results
                </CardTitle>
              </CardHeader>
              <CardContent>
                {latestCycle ? (
                  <div className="space-y-4">
                    <div className="flex justify-between items-center p-3 bg-muted/50 rounded-lg">
                      <span className="text-sm text-muted-foreground">Planning Date</span>
                      <span className="font-medium">{latestCycle.planning_date}</span>
                    </div>

                    <div className="flex justify-between items-center">
                      <span className="text-sm text-muted-foreground">Coverage Guarantee</span>
                      <CoverageGuaranteeBadge value={latestCycle.coverage_guarantee || 0} />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div className="p-3 border rounded-lg">
                        <div className="text-sm text-muted-foreground">Scenarios Generated</div>
                        <div className="text-xl font-bold">{latestCycle.n_scenarios_generated}</div>
                      </div>
                      <div className="p-3 border rounded-lg">
                        <div className="text-sm text-muted-foreground">After Reduction</div>
                        <div className="text-xl font-bold">{latestCycle.n_scenarios_reduced}</div>
                      </div>
                    </div>

                    {latestCycle.first_stage_decisions && (
                      <div>
                        <h4 className="font-medium mb-2">First-Stage Decisions</h4>
                        <div className="space-y-2 text-sm">
                          {Object.entries(latestCycle.first_stage_decisions).slice(0, 3).map(([key, value]) => (
                            <div key={key} className="flex justify-between p-2 border rounded">
                              <span className="text-muted-foreground">{key}</span>
                              <span className="font-medium">{typeof value === 'number' ? value.toFixed(0) : value}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="text-xs text-muted-foreground">
                      Solve time: {latestCycle.solve_time_seconds?.toFixed(2)}s
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <Calendar className="h-12 w-12 mx-auto mb-4 opacity-30" />
                    <p>No planning cycles completed yet</p>
                    <p className="text-sm mt-1">Run a cycle to see results</p>
                    <Button className="mt-4" onClick={() => setActiveTab('run-cycle')}>
                      <Play className="h-4 w-4 mr-2" />
                      Run First Cycle
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Run Cycle Tab */}
        <TabsContent value="run-cycle">
          <div className="grid grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Play className="h-5 w-5" />
                  Run S&OP Planning Cycle
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Alert>
                  <AlertDescription className="text-sm">
                    <strong>Process:</strong>
                    <ol className="list-decimal ml-4 mt-2 space-y-1">
                      <li>Generate scenarios from conformal prediction regions</li>
                      <li>Reduce scenarios using Wasserstein distance</li>
                      <li>Solve two-stage stochastic program</li>
                      <li>Return first-stage decisions with coverage guarantee</li>
                    </ol>
                  </AlertDescription>
                </Alert>

                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="planningDate">Planning Date</Label>
                    <Input
                      id="planningDate"
                      type="date"
                      value={planningDate}
                      onChange={(e) => setPlanningDate(e.target.value)}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="maxInvestment">Max Investment (optional)</Label>
                    <Input
                      id="maxInvestment"
                      type="number"
                      placeholder="e.g., 100000"
                      value={maxInvestment}
                      onChange={(e) => setMaxInvestment(e.target.value)}
                    />
                    <p className="text-xs text-muted-foreground">
                      Upper bound on first-stage investment decisions
                    </p>
                  </div>

                  {conformalStatus && (
                    <div className="p-3 bg-muted/50 rounded-lg text-sm">
                      <div className="flex items-center gap-2 mb-2">
                        <Sparkles className="h-4 w-4 text-amber-500" />
                        <span className="font-medium">Conformal Suite Status</span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div>Demand predictors: {conformalStatus.summary?.demand_predictors || 0}</div>
                        <div>Lead time predictors: {conformalStatus.summary?.lead_time_predictors || 0}</div>
                      </div>
                    </div>
                  )}
                </div>

                <Button
                  onClick={handleRunCycle}
                  disabled={loading}
                  className="w-full"
                  size="lg"
                >
                  {loading ? (
                    <>
                      <Spinner size="sm" className="mr-2" />
                      Running Cycle...
                    </>
                  ) : (
                    <>
                      <Play className="h-4 w-4 mr-2" />
                      Run Planning Cycle
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <RefreshCw className="h-5 w-5" />
                  Observe Actuals (Learning Step)
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Alert variant="info">
                  <AlertDescription className="text-sm">
                    <strong>Learning Loop:</strong> After observing actual outcomes, the conformal
                    predictors recalibrate their uncertainty intervals. This improves future
                    coverage guarantees.
                  </AlertDescription>
                </Alert>

                <div className="space-y-3">
                  <div className="p-3 border rounded-lg">
                    <div className="text-sm font-medium mb-1">How It Works</div>
                    <ul className="text-xs text-muted-foreground space-y-1">
                      <li>• Compare forecasted demand vs actual demand</li>
                      <li>• Compare promised lead times vs actual lead times</li>
                      <li>• Recalibrate nonconformity scores</li>
                      <li>• Update prediction interval widths</li>
                    </ul>
                  </div>

                  <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                    <div className="flex items-center gap-2 text-green-700 dark:text-green-400">
                      <CheckCircle className="h-4 w-4" />
                      <span className="text-sm font-medium">Demo Data Ready</span>
                    </div>
                    <p className="text-xs text-green-600 dark:text-green-500 mt-1">
                      Click below to simulate observing actuals for the current planning date
                    </p>
                  </div>
                </div>

                <Button
                  onClick={handleObserveActuals}
                  disabled={loading}
                  variant="outline"
                  className="w-full"
                >
                  {loading ? (
                    <>
                      <Spinner size="sm" className="mr-2" />
                      Updating...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="h-4 w-4 mr-2" />
                      Observe Actuals (Demo)
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5" />
                S&OP Cycle History
              </CardTitle>
            </CardHeader>
            <CardContent>
              {sopHistory.length > 0 ? (
                <div className="space-y-3">
                  {sopHistory.map((cycle, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/50 transition-colors"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{cycle.planning_date}</span>
                          <Badge variant={cycle.status === 'complete' ? 'success' : 'secondary'}>
                            {cycle.status}
                          </Badge>
                        </div>
                        <div className="text-sm text-muted-foreground mt-1">
                          {cycle.n_scenarios_generated} scenarios → {cycle.n_scenarios_reduced} reduced
                        </div>
                      </div>
                      <div className="text-right">
                        <CoverageGuaranteeBadge value={cycle.coverage_guarantee || 0} />
                        <div className="text-xs text-muted-foreground mt-1">
                          {cycle.solve_time_seconds?.toFixed(2)}s solve time
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 text-muted-foreground">
                  <Clock className="h-12 w-12 mx-auto mb-4 opacity-30" />
                  <p>No planning cycles recorded yet</p>
                  <p className="text-sm mt-1">Run planning cycles to build history</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Learning Tab */}
        <TabsContent value="learning">
          <div className="grid grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5" />
                  Learning Progress
                </CardTitle>
              </CardHeader>
              <CardContent>
                {learningProgress ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-4 border rounded-lg text-center">
                        <div className="text-sm text-muted-foreground mb-1">Early Cycles (1-5)</div>
                        <div className="text-3xl font-bold">
                          {((learningProgress.early_performance?.coverage_hit_rate || 0) * 100).toFixed(0)}%
                        </div>
                        <div className="text-xs text-muted-foreground">Coverage Hit Rate</div>
                      </div>
                      <div className="p-4 border rounded-lg text-center bg-green-50 dark:bg-green-900/20">
                        <div className="text-sm text-muted-foreground mb-1">Recent Cycles</div>
                        <div className="text-3xl font-bold text-green-600">
                          {((learningProgress.late_performance?.coverage_hit_rate || 0) * 100).toFixed(0)}%
                        </div>
                        <div className="text-xs text-muted-foreground">Coverage Hit Rate</div>
                      </div>
                    </div>

                    <div className="p-4 border rounded-lg">
                      <div className="flex justify-between items-center">
                        <span className="font-medium">Improvement</span>
                        <Badge
                          variant={learningProgress.improvement > 0 ? 'success' : 'secondary'}
                          className="text-lg px-3"
                        >
                          {learningProgress.improvement > 0 ? '+' : ''}
                          {(learningProgress.improvement * 100).toFixed(0)}%
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground mt-2">
                        Based on {learningProgress.total_cycles} total cycles
                      </p>
                    </div>

                    <Alert>
                      <Sparkles className="h-4 w-4" />
                      <AlertDescription className="ml-2 text-sm">
                        The conformal learning loop improves predictions by comparing forecasts to actuals
                        and recalibrating uncertainty intervals. More cycles = better coverage.
                      </AlertDescription>
                    </Alert>
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <TrendingUp className="h-12 w-12 mx-auto mb-4 opacity-30" />
                    <p>Not enough cycles for learning analysis</p>
                    <p className="text-sm mt-1">Run at least 5 cycles to see progress</p>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Settings className="h-5 w-5" />
                  Performance Metrics
                </CardTitle>
              </CardHeader>
              <CardContent>
                {sopPerformance ? (
                  <div className="space-y-4">
                    <div className="p-4 border rounded-lg">
                      <div className="text-sm text-muted-foreground mb-1">Average Coverage Hit Rate</div>
                      <div className="text-2xl font-bold">
                        {((sopPerformance.avg_coverage_hit_rate || 0) * 100).toFixed(1)}%
                      </div>
                    </div>

                    <div className="p-4 border rounded-lg">
                      <div className="text-sm text-muted-foreground mb-1">Average Cost Accuracy</div>
                      <div className="text-2xl font-bold">
                        {((sopPerformance.avg_cost_accuracy || 0) * 100).toFixed(1)}%
                      </div>
                    </div>

                    <div className="p-4 border rounded-lg">
                      <div className="text-sm text-muted-foreground mb-1">Total Observations</div>
                      <div className="text-2xl font-bold">
                        {sopPerformance.total_observations || 0}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <BarChart3 className="h-12 w-12 mx-auto mb-4 opacity-30" />
                    <p>No performance data yet</p>
                    <p className="text-sm mt-1">Observe actuals to track performance</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default SalesOperationsPlanning;
