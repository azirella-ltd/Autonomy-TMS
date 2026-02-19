/**
 * Planning Method Comparison Component
 *
 * Compares Stochastic Optimization vs Deterministic + Sensitivity Analysis
 *
 * Features:
 * - Side-by-side comparison of both approaches
 * - Run same scenario with both methods
 * - Visualize differences in outputs and risk profiles
 * - Recommendations based on decision type
 */

import React, { useState, useEffect } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
  LineChart,
  Line,
  ReferenceLine,
} from 'recharts';
import {
  Info,
  Play,
  ArrowLeftRight,
  ChevronDown,
  Dice5,
  SlidersHorizontal,
  AlertTriangle,
  CheckCircle,
} from 'lucide-react';
import {
  Card,
  CardContent,
} from '../common/Card';
import { Button, IconButton } from '../common/Button';
import { Alert } from '../common/Alert';
import { Badge } from '../common/Badge';
import { Input, Label } from '../common/Input';
import { Progress } from '../common/Progress';
import {
  Table,
  TableBody,
  TableCell,
  TableRow,
} from '../common/Table';
import { Spinner } from '../common/Loading';

const PlanningMethodComparison = () => {
  const [loading, setLoading] = useState(false);
  const [deterministicResults, setDeterministicResults] = useState(null);
  const [stochasticResults, setStochasticResults] = useState(null);
  const [comparisonData, setComparisonData] = useState(null);

  // Scenario parameters
  const [scenario, setScenario] = useState({
    demand_mean: 100,
    demand_std: 15,
    lead_time_mean: 7,
    lead_time_std: 2,
    holding_cost: 2,
    shortage_cost: 10,
    order_cost: 50,
    initial_inventory: 150,
    planning_horizon: 12,
    monte_carlo_runs: 1000,
  });

  // Sensitivity analysis parameters
  const [sensitivityParams] = useState({
    parameter: 'demand_mean',
    range_min: 80,
    range_max: 120,
    steps: 10,
  });

  const runDeterministicAnalysis = () => {
    setLoading(true);

    // Simulate deterministic analysis
    setTimeout(() => {
      const { demand_mean, lead_time_mean, holding_cost } = scenario;

      // Simple EOQ-based calculation
      const annual_demand = demand_mean * 52;
      const eoq = Math.sqrt((2 * annual_demand * scenario.order_cost) / holding_cost);
      const reorder_point = demand_mean * lead_time_mean;
      const safety_stock = 1.65 * scenario.demand_std * Math.sqrt(lead_time_mean); // 95% service level

      // Cost calculation (deterministic)
      const avg_inventory = eoq / 2 + safety_stock;
      const holding_cost_total = avg_inventory * holding_cost * scenario.planning_horizon;
      const order_cost_total = (demand_mean * scenario.planning_horizon / eoq) * scenario.order_cost;
      const total_cost = holding_cost_total + order_cost_total;

      // Sensitivity analysis
      const sensitivityData = [];
      const { range_min, range_max, steps } = sensitivityParams;
      const step_size = (range_max - range_min) / steps;

      for (let i = 0; i <= steps; i++) {
        const param_value = range_min + i * step_size;
        let modified_cost;

        if (sensitivityParams.parameter === 'demand_mean') {
          modified_cost = total_cost * (param_value / demand_mean);
        } else if (sensitivityParams.parameter === 'holding_cost') {
          modified_cost = total_cost * (1 + (param_value - holding_cost) / holding_cost * 0.5);
        } else {
          modified_cost = total_cost * (1 + (param_value - lead_time_mean) / lead_time_mean * 0.3);
        }

        sensitivityData.push({
          parameter_value: param_value,
          total_cost: modified_cost,
          change_percent: ((modified_cost - total_cost) / total_cost * 100),
        });
      }

      setDeterministicResults({
        method: 'Deterministic + Sensitivity',
        eoq: eoq,
        reorder_point: reorder_point,
        safety_stock: safety_stock,
        total_cost: total_cost,
        holding_cost: holding_cost_total,
        order_cost: order_cost_total,
        service_level: 0.95, // Assumed
        sensitivity_data: sensitivityData,
        computation_time: 50, // ms
        assumptions: [
          'Normal demand distribution',
          'Fixed lead time',
          'Constant cost parameters',
          '95% service level target',
        ],
        limitations: [
          'No actual guarantee on service level',
          'Ignores demand/lead time correlation',
          'Single-point optimization (not risk-aware)',
          'Sensitivity shows range, not probability',
        ],
      });

      setLoading(false);
    }, 500);
  };

  const runStochasticAnalysis = () => {
    setLoading(true);

    // Simulate stochastic analysis (Monte Carlo)
    setTimeout(() => {
      const { demand_mean, demand_std, lead_time_mean, lead_time_std, holding_cost, shortage_cost, monte_carlo_runs } = scenario;

      // Run Monte Carlo simulation
      const results = [];
      for (let i = 0; i < monte_carlo_runs; i++) {
        // Sample from distributions
        const demand = demand_mean + (Math.random() - 0.5) * 2 * demand_std * 1.5;
        const lead_time = Math.max(1, lead_time_mean + (Math.random() - 0.5) * 2 * lead_time_std * 1.5);

        // Calculate costs for this scenario
        const safety_stock = 1.65 * demand_std * Math.sqrt(lead_time);
        const avg_inventory = scenario.initial_inventory / 2 + safety_stock;
        const holding = avg_inventory * holding_cost * scenario.planning_horizon;
        const shortage = Math.max(0, demand * lead_time - scenario.initial_inventory) * shortage_cost;
        const total = holding + shortage;

        results.push({
          demand,
          lead_time,
          total_cost: total,
          holding_cost: holding,
          shortage_cost: shortage,
          service_level: shortage === 0 ? 1 : Math.max(0, 1 - shortage / (demand * shortage_cost)),
        });
      }

      // Calculate statistics
      const costs = results.map(r => r.total_cost);
      const service_levels = results.map(r => r.service_level);

      const mean_cost = costs.reduce((a, b) => a + b, 0) / costs.length;
      const sorted_costs = [...costs].sort((a, b) => a - b);
      const p10_cost = sorted_costs[Math.floor(costs.length * 0.1)];
      const p50_cost = sorted_costs[Math.floor(costs.length * 0.5)];
      const p90_cost = sorted_costs[Math.floor(costs.length * 0.9)];
      const p95_cost = sorted_costs[Math.floor(costs.length * 0.95)];

      const mean_service = service_levels.reduce((a, b) => a + b, 0) / service_levels.length;
      const prob_above_95 = service_levels.filter(s => s >= 0.95).length / service_levels.length;

      // Cost distribution for histogram
      const cost_bins = 20;
      const cost_min = Math.min(...costs);
      const cost_max = Math.max(...costs);
      const bin_width = (cost_max - cost_min) / cost_bins;
      const histogram = [];
      for (let i = 0; i < cost_bins; i++) {
        const bin_start = cost_min + i * bin_width;
        const bin_end = bin_start + bin_width;
        const count = costs.filter(c => c >= bin_start && c < bin_end).length;
        histogram.push({
          bin: bin_start,
          count: count,
          percentage: (count / costs.length * 100),
        });
      }

      setStochasticResults({
        method: 'Stochastic (Monte Carlo)',
        monte_carlo_runs: monte_carlo_runs,
        cost_statistics: {
          mean: mean_cost,
          p10: p10_cost,
          p50: p50_cost,
          p90: p90_cost,
          p95: p95_cost,
          std: Math.sqrt(costs.reduce((a, c) => a + Math.pow(c - mean_cost, 2), 0) / costs.length),
        },
        service_level: {
          mean: mean_service,
          prob_above_95: prob_above_95,
        },
        histogram: histogram,
        scatter_data: results.slice(0, 200).map((r, i) => ({
          id: i,
          demand: r.demand,
          lead_time: r.lead_time,
          total_cost: r.total_cost,
        })),
        computation_time: 2500, // ms
        advantages: [
          'Produces probability distributions for KPIs',
          'Captures uncertainty in both demand and lead time',
          'Provides risk metrics (VaR, CaR)',
          'Can optimize under different risk preferences',
        ],
        outputs: [
          `P(Cost < $${p50_cost.toFixed(0)}) = 50%`,
          `P(Service Level > 95%) = ${(prob_above_95 * 100).toFixed(1)}%`,
          `Cost-at-Risk (95%): $${p95_cost.toFixed(0)}`,
        ],
      });

      setLoading(false);
    }, 1500);
  };

  const runComparison = () => {
    runDeterministicAnalysis();
    runStochasticAnalysis();
  };

  useEffect(() => {
    if (deterministicResults && stochasticResults) {
      setComparisonData({
        cost_comparison: [
          {
            metric: 'Expected Cost',
            deterministic: deterministicResults.total_cost,
            stochastic: stochasticResults.cost_statistics.mean,
          },
          {
            metric: 'P90 Cost',
            deterministic: deterministicResults.total_cost * 1.2, // Estimated
            stochastic: stochasticResults.cost_statistics.p90,
          },
          {
            metric: 'P95 Cost (CaR)',
            deterministic: deterministicResults.total_cost * 1.3, // Estimated
            stochastic: stochasticResults.cost_statistics.p95,
          },
        ],
        service_comparison: [
          {
            metric: 'Expected Service Level',
            deterministic: deterministicResults.service_level * 100,
            stochastic: stochasticResults.service_level.mean * 100,
          },
          {
            metric: 'P(Service > 95%)',
            deterministic: 50, // Unknown for deterministic
            stochastic: stochasticResults.service_level.prob_above_95 * 100,
          },
        ],
      });
    }
  }, [deterministicResults, stochasticResults]);

  const renderScenarioSetup = () => (
    <Card>
      <CardContent>
        <h6 className="text-lg font-semibold mb-4">Scenario Parameters</h6>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="space-y-1">
            <Label htmlFor="demand_mean">Demand Mean</Label>
            <Input
              id="demand_mean"
              type="number"
              value={scenario.demand_mean}
              onChange={(e) => setScenario({ ...scenario, demand_mean: parseFloat(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="demand_std">Demand Std Dev</Label>
            <Input
              id="demand_std"
              type="number"
              value={scenario.demand_std}
              onChange={(e) => setScenario({ ...scenario, demand_std: parseFloat(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="lead_time_mean">Lead Time Mean</Label>
            <Input
              id="lead_time_mean"
              type="number"
              value={scenario.lead_time_mean}
              onChange={(e) => setScenario({ ...scenario, lead_time_mean: parseFloat(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="lead_time_std">Lead Time Std Dev</Label>
            <Input
              id="lead_time_std"
              type="number"
              value={scenario.lead_time_std}
              onChange={(e) => setScenario({ ...scenario, lead_time_std: parseFloat(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="holding_cost">Holding Cost</Label>
            <Input
              id="holding_cost"
              type="number"
              value={scenario.holding_cost}
              onChange={(e) => setScenario({ ...scenario, holding_cost: parseFloat(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="shortage_cost">Shortage Cost</Label>
            <Input
              id="shortage_cost"
              type="number"
              value={scenario.shortage_cost}
              onChange={(e) => setScenario({ ...scenario, shortage_cost: parseFloat(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="monte_carlo_runs">Monte Carlo Runs</Label>
            <Input
              id="monte_carlo_runs"
              type="number"
              value={scenario.monte_carlo_runs}
              onChange={(e) => setScenario({ ...scenario, monte_carlo_runs: parseInt(e.target.value) })}
            />
          </div>
          <div className="flex items-end">
            <Button
              fullWidth
              onClick={runComparison}
              disabled={loading}
              leftIcon={loading ? <Spinner size="sm" /> : <ArrowLeftRight className="h-4 w-4" />}
              className="h-10"
            >
              Run Comparison
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );

  const renderDeterministicResults = () => (
    <Card>
      <CardContent>
        <div className="flex items-center gap-2 mb-4">
          <SlidersHorizontal className="h-5 w-5" />
          <h6 className="text-lg font-semibold">Deterministic + Sensitivity Analysis</h6>
          <Badge variant="info" size="sm">Fast</Badge>
        </div>

        {deterministicResults ? (
          <>
            <Table>
              <TableBody>
                <TableRow hoverable={false}>
                  <TableCell>EOQ</TableCell>
                  <TableCell>{deterministicResults.eoq.toFixed(0)} units</TableCell>
                </TableRow>
                <TableRow hoverable={false}>
                  <TableCell>Reorder Point</TableCell>
                  <TableCell>{deterministicResults.reorder_point.toFixed(0)} units</TableCell>
                </TableRow>
                <TableRow hoverable={false}>
                  <TableCell>Safety Stock</TableCell>
                  <TableCell>{deterministicResults.safety_stock.toFixed(0)} units</TableCell>
                </TableRow>
                <TableRow hoverable={false} className="bg-muted/50">
                  <TableCell><strong>Total Cost</strong></TableCell>
                  <TableCell><strong>${deterministicResults.total_cost.toFixed(0)}</strong></TableCell>
                </TableRow>
                <TableRow hoverable={false}>
                  <TableCell>Assumed Service Level</TableCell>
                  <TableCell>{(deterministicResults.service_level * 100).toFixed(0)}%</TableCell>
                </TableRow>
                <TableRow hoverable={false}>
                  <TableCell>Computation Time</TableCell>
                  <TableCell>{deterministicResults.computation_time}ms</TableCell>
                </TableRow>
              </TableBody>
            </Table>

            <hr className="my-4 border-border" />

            <p className="text-sm font-medium mb-2">Sensitivity Analysis</p>
            <div className="h-52">
              <ResponsiveContainer>
                <LineChart data={deterministicResults.sensitivity_data}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="parameter_value" />
                  <YAxis />
                  <RechartsTooltip />
                  <Line type="monotone" dataKey="total_cost" stroke="#8884d8" />
                  <ReferenceLine y={deterministicResults.total_cost} stroke="red" strokeDasharray="3 3" />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <Alert variant="warning" className="mt-4">
              <span className="text-xs">
                <strong>Limitations:</strong> {deterministicResults.limitations.join('; ')}
              </span>
            </Alert>
          </>
        ) : (
          <p className="text-muted-foreground">Run comparison to see results</p>
        )}
      </CardContent>
    </Card>
  );

  const renderStochasticResults = () => (
    <Card>
      <CardContent>
        <div className="flex items-center gap-2 mb-4">
          <Dice5 className="h-5 w-5" />
          <h6 className="text-lg font-semibold">Stochastic (Monte Carlo)</h6>
          <Badge variant="success" size="sm">Risk-Aware</Badge>
        </div>

        {stochasticResults ? (
          <>
            <Table>
              <TableBody>
                <TableRow hoverable={false}>
                  <TableCell>Scenarios Simulated</TableCell>
                  <TableCell>{stochasticResults.monte_carlo_runs.toLocaleString()}</TableCell>
                </TableRow>
                <TableRow hoverable={false}>
                  <TableCell>E[Cost]</TableCell>
                  <TableCell>${stochasticResults.cost_statistics.mean.toFixed(0)}</TableCell>
                </TableRow>
                <TableRow hoverable={false}>
                  <TableCell>P10 / P50 / P90</TableCell>
                  <TableCell>
                    ${stochasticResults.cost_statistics.p10.toFixed(0)} /
                    ${stochasticResults.cost_statistics.p50.toFixed(0)} /
                    ${stochasticResults.cost_statistics.p90.toFixed(0)}
                  </TableCell>
                </TableRow>
                <TableRow hoverable={false} className="bg-warning/20">
                  <TableCell><strong>Cost-at-Risk (95%)</strong></TableCell>
                  <TableCell><strong>${stochasticResults.cost_statistics.p95.toFixed(0)}</strong></TableCell>
                </TableRow>
                <TableRow hoverable={false}>
                  <TableCell>E[Service Level]</TableCell>
                  <TableCell>{(stochasticResults.service_level.mean * 100).toFixed(1)}%</TableCell>
                </TableRow>
                <TableRow hoverable={false} className="bg-emerald-50 dark:bg-emerald-950">
                  <TableCell><strong>P(Service &gt; 95%)</strong></TableCell>
                  <TableCell><strong>{(stochasticResults.service_level.prob_above_95 * 100).toFixed(1)}%</strong></TableCell>
                </TableRow>
                <TableRow hoverable={false}>
                  <TableCell>Computation Time</TableCell>
                  <TableCell>{stochasticResults.computation_time}ms</TableCell>
                </TableRow>
              </TableBody>
            </Table>

            <hr className="my-4 border-border" />

            <p className="text-sm font-medium mb-2">Cost Distribution</p>
            <div className="h-52">
              <ResponsiveContainer>
                <BarChart data={stochasticResults.histogram}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="bin" tickFormatter={(v) => `$${v.toFixed(0)}`} />
                  <YAxis />
                  <RechartsTooltip formatter={(v) => `${v.toFixed(1)}%`} />
                  <Bar dataKey="percentage" fill="#82ca9d" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <Alert variant="success" className="mt-4">
              <span className="text-xs">
                <strong>Advantages:</strong> {stochasticResults.advantages.join('; ')}
              </span>
            </Alert>
          </>
        ) : (
          <p className="text-muted-foreground">Run comparison to see results</p>
        )}
      </CardContent>
    </Card>
  );

  const renderComparisonSummary = () => (
    <Card>
      <CardContent>
        <div className="flex items-center gap-2 mb-4">
          <ArrowLeftRight className="h-5 w-5" />
          <h6 className="text-lg font-semibold">Side-by-Side Comparison</h6>
        </div>

        {comparisonData ? (
          <>
            <div className="h-64">
              <ResponsiveContainer>
                <BarChart data={comparisonData.cost_comparison}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="metric" />
                  <YAxis />
                  <RechartsTooltip formatter={(v) => `$${v.toFixed(0)}`} />
                  <Legend />
                  <Bar dataKey="deterministic" fill="#8884d8" name="Deterministic" />
                  <Bar dataKey="stochastic" fill="#82ca9d" name="Stochastic" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <hr className="my-4 border-border" />

            <h6 className="text-lg font-semibold mb-4">Recommendation</h6>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card variant="outlined" padding="sm">
                <CardContent>
                  <p className="text-sm font-medium text-primary mb-2">
                    Use Deterministic + Sensitivity When:
                  </p>
                  <ul className="list-disc pl-5 m-0 text-sm space-y-1">
                    <li>Quick "what-if" analysis needed</li>
                    <li>Communicating to non-technical stakeholders</li>
                    <li>Low-value or routine decisions</li>
                    <li>Uncertainty is small or well-controlled</li>
                  </ul>
                </CardContent>
              </Card>
              <Card variant="outlined" padding="sm" className="border-emerald-500">
                <CardContent>
                  <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400 mb-2">
                    Use Stochastic Planning When:
                  </p>
                  <ul className="list-disc pl-5 m-0 text-sm space-y-1">
                    <li>High-value decisions (safety stock, network design)</li>
                    <li>Significant uncertainty in parameters</li>
                    <li>Need risk metrics (VaR, P(stockout))</li>
                    <li>Optimizing under different risk preferences</li>
                  </ul>
                </CardContent>
              </Card>
            </div>
          </>
        ) : (
          <p className="text-muted-foreground">Run comparison to see results</p>
        )}
      </CardContent>
    </Card>
  );

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <h5 className="text-xl font-semibold">Stochastic vs Deterministic Planning</h5>
        <IconButton
          variant="ghost"
          size="icon"
          title="Compare two fundamental approaches to planning under uncertainty"
        >
          <Info className="h-4 w-4" />
        </IconButton>
      </div>

      <Alert variant="info" className="mb-6">
        <div className="text-sm">
          <strong>Deterministic:</strong> Uses single-point estimates + sensitivity analysis.
          Fast but no risk quantification.
          <br />
          <strong>Stochastic:</strong> Uses probability distributions + Monte Carlo.
          Provides risk metrics but computationally intensive.
        </div>
      </Alert>

      {loading && <Progress value={50} className="mb-4" />}

      <div className="grid grid-cols-1 gap-6">
        <div>
          {renderScenarioSetup()}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {renderDeterministicResults()}
          {renderStochasticResults()}
        </div>

        <div>
          {renderComparisonSummary()}
        </div>
      </div>
    </div>
  );
};

export default PlanningMethodComparison;
