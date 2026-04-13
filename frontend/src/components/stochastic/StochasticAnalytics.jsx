/**
 * Stochastic Analytics Dashboard
 *
 * Visualizes analytics results from stochastic simulations:
 * - Variability analysis (CV, IQR, MAD)
 * - Confidence intervals
 * - Risk metrics (VaR, CVaR)
 * - Distribution fit testing
 * - Scenario comparison
 *
 * Phase 5 Sprint 5: Analytics & Visualization
 */

import React, { useState, useMemo } from 'react';
import {
  Info,
  TrendingUp,
  TrendingDown,
  AlertTriangle
} from 'lucide-react';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
  Cell,
  ReferenceLine
} from 'recharts';
import { Card, CardContent, IconButton, Badge, Alert } from '../common';
import { Tabs, TabsList, Tab, TabPanel } from '../common/Tabs';
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from '../common/Table';
import { Progress } from '../common/Progress';

/**
 * Metric Card Component
 * Displays a single metric with value, label, and optional icon
 */
const MetricCard = ({ label, value, unit = '', color = 'primary', icon, tooltip }) => (
  <Card className="h-full">
    <CardContent>
      <div className="flex justify-between items-start">
        <p className="text-sm text-muted-foreground mb-1">
          {label}
        </p>
        {tooltip && (
          <div className="group relative">
            <IconButton className="h-6 w-6">
              <Info className="h-4 w-4" />
            </IconButton>
            <div className="absolute right-0 top-full mt-1 w-48 p-2 bg-popover text-popover-foreground text-xs rounded shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
              {tooltip}
            </div>
          </div>
        )}
      </div>
      <div className="flex items-center gap-2">
        {icon}
        <span className={`text-xl font-semibold ${color === 'success' ? 'text-emerald-600' : color === 'warning' ? 'text-amber-600' : color === 'error' ? 'text-red-600' : ''}`}>
          {typeof value === 'number' ? value.toFixed(2) : value}
          {unit && <span className="text-sm text-muted-foreground ml-1">{unit}</span>}
        </span>
      </div>
    </CardContent>
  </Card>
);

/**
 * Variability Analysis Component
 * Shows variability metrics: mean, std, CV, IQR, MAD
 */
const VariabilityAnalysis = ({ metrics }) => {
  if (!metrics) return null;

  const variabilityLevel = metrics.cv < 15 ? 'Low' : metrics.cv < 30 ? 'Medium' : 'High';
  const variabilityVariant = metrics.cv < 15 ? 'success' : metrics.cv < 30 ? 'warning' : 'destructive';

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">
        Variability Analysis
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
        <MetricCard
          label="Mean"
          value={metrics.mean}
          tooltip="Average value across all samples"
        />
        <MetricCard
          label="Standard Deviation"
          value={metrics.std}
          tooltip="Measure of spread around the mean"
        />
        <MetricCard
          label="Coefficient of Variation"
          value={metrics.cv}
          unit="%"
          color={variabilityVariant}
          icon={<Badge variant={variabilityVariant} size="sm">{variabilityLevel}</Badge>}
          tooltip="Relative variability (std/mean). <15% = Low, 15-30% = Medium, >30% = High"
        />
        <MetricCard
          label="Range"
          value={metrics.range}
          tooltip="Difference between max and min values"
        />
        <MetricCard
          label="IQR (Interquartile Range)"
          value={metrics.iqr}
          tooltip="Range of middle 50% of data (75th - 25th percentile)"
        />
        <MetricCard
          label="MAD (Median Abs Deviation)"
          value={metrics.mad}
          tooltip="Robust measure of variability around median"
        />
      </div>

      <div className="mt-6">
        <h4 className="text-sm font-medium mb-4">
          Percentile Distribution
        </h4>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart
            data={[
              { label: 'Min', value: metrics.min },
              { label: '25th', value: metrics.p25 || metrics.mean - metrics.std },
              { label: 'Median', value: metrics.median || metrics.mean },
              { label: '75th', value: metrics.p75 || metrics.mean + metrics.std },
              { label: 'Max', value: metrics.max }
            ]}
          >
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" />
            <YAxis />
            <RechartsTooltip />
            <Bar dataKey="value" fill="#8884d8" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

/**
 * Confidence Interval Component
 * Visualizes confidence interval with margin of error
 */
const ConfidenceIntervalView = ({ ci }) => {
  if (!ci) return null;

  const chartData = [
    { label: 'Lower Bound', value: ci.lower },
    { label: 'Mean', value: ci.mean },
    { label: 'Upper Bound', value: ci.upper }
  ];

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">
        Confidence Interval
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard
          label="Mean"
          value={ci.mean}
        />
        <MetricCard
          label="Confidence Interval"
          value={`[${ci.lower.toFixed(2)}, ${ci.upper.toFixed(2)}]`}
          tooltip={`${ci.confidence * 100}% confidence interval`}
        />
        <MetricCard
          label="Margin of Error"
          value={ci.margin_of_error}
          tooltip="+-range around the mean"
        />
      </div>

      <div className="mt-6">
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" />
            <YAxis domain={[ci.lower * 0.95, ci.upper * 1.05]} />
            <RechartsTooltip />
            <Bar dataKey="value" fill="#82ca9d">
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={index === 1 ? '#8884d8' : '#82ca9d'} />
              ))}
            </Bar>
            <ReferenceLine y={ci.mean} stroke="#8884d8" strokeDasharray="3 3" label="Mean" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

/**
 * Risk Metrics Component
 * Shows VaR, CVaR, and max drawdown
 */
const RiskMetricsView = ({ metrics }) => {
  if (!metrics) return null;

  const riskData = [
    { label: 'VaR 95%', value: metrics.var_95, color: '#ffeb3b' },
    { label: 'VaR 99%', value: metrics.var_99, color: '#ff9800' },
    { label: 'CVaR 95%', value: metrics.cvar_95, color: '#ff5722' },
    { label: 'CVaR 99%', value: metrics.cvar_99, color: '#f44336' },
    { label: 'Max Loss', value: metrics.max_drawdown, color: '#b71c1c' }
  ];

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">
        Risk Metrics
      </h3>
      <Alert variant="info" className="mb-4">
        VaR (Value at Risk): Threshold for worst outcomes. CVaR (Conditional VaR): Average of tail losses beyond VaR.
      </Alert>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4">
        <MetricCard
          label="VaR 95%"
          value={metrics.var_95}
          tooltip="95% of outcomes are below this value"
          icon={<AlertTriangle className="h-4 w-4 text-amber-500" />}
        />
        <MetricCard
          label="VaR 99%"
          value={metrics.var_99}
          tooltip="99% of outcomes are below this value"
          icon={<AlertTriangle className="h-4 w-4 text-amber-500" />}
        />
        <MetricCard
          label="CVaR 95%"
          value={metrics.cvar_95}
          tooltip="Average of worst 5% of outcomes"
          icon={<AlertTriangle className="h-4 w-4 text-red-500" />}
        />
        <MetricCard
          label="CVaR 99%"
          value={metrics.cvar_99}
          tooltip="Average of worst 1% of outcomes"
          icon={<AlertTriangle className="h-4 w-4 text-red-500" />}
        />
        <MetricCard
          label="Max Drawdown"
          value={metrics.max_drawdown}
          tooltip="Worst possible outcome observed"
          icon={<AlertTriangle className="h-4 w-4 text-red-700" />}
        />
      </div>

      <div className="mt-6">
        <h4 className="text-sm font-medium mb-4">
          Risk Profile
        </h4>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={riskData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" />
            <YAxis />
            <RechartsTooltip />
            <Bar dataKey="value">
              {riskData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

/**
 * Distribution Fit Component
 * Shows distribution fit test results
 */
const DistributionFitView = ({ fitResults }) => {
  if (!fitResults) return null;

  const getFitStatus = (pValue) => {
    if (pValue > 0.1) return { label: 'Good Fit', variant: 'success' };
    if (pValue > 0.05) return { label: 'Acceptable Fit', variant: 'warning' };
    return { label: 'Poor Fit', variant: 'error' };
  };

  const status = getFitStatus(fitResults.p_value);

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">
        Distribution Fit Test
      </h3>
      <Alert variant={status.variant} className="mb-4">
        {fitResults.test_name} test result: {status.label}
      </Alert>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard
          label="Test Statistic"
          value={fitResults.statistic}
          tooltip="K-S statistic measures distance between empirical and theoretical distribution"
        />
        <MetricCard
          label="p-value"
          value={fitResults.p_value}
          tooltip="Probability of observing this difference by chance. >0.05 = accept fit"
          color={status.variant}
        />
        <MetricCard
          label="Fit Status"
          value={status.label}
          color={status.variant}
          icon={<Badge variant="secondary" size="sm">{fitResults.distribution}</Badge>}
        />
      </div>

      <div className="mt-4">
        <p className="text-sm text-muted-foreground">
          {fitResults.significant
            ? 'Reject null hypothesis: Data does NOT fit the specified distribution'
            : 'Accept null hypothesis: Data fits the specified distribution'}
        </p>
      </div>
    </div>
  );
};

/**
 * Scenario Comparison Component
 * Compares multiple scenarios side-by-side
 */
const ScenarioComparisonView = ({ comparison }) => {
  if (!comparison) return null;

  const { rankings, ...scenarios } = comparison;

  // Prepare data for charts
  const meanData = Object.entries(scenarios).map(([name, metrics]) => ({
    scenario: name,
    mean: metrics.mean,
    lower: metrics.ci_lower,
    upper: metrics.ci_upper
  }));

  const cvData = Object.entries(scenarios).map(([name, metrics]) => ({
    scenario: name,
    cv: metrics.cv
  }));

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">
        Scenario Comparison
      </h3>

      {/* Rankings Summary */}
      <Card className="p-4 mb-6 bg-primary/10">
        <h4 className="text-sm font-medium mb-3">
          Rankings
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <TrendingDown className="h-4 w-4" />
            <span className="text-sm">
              Best Mean: <strong>{rankings.best_mean}</strong>
            </span>
          </div>
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            <span className="text-sm">
              Worst Mean: <strong>{rankings.worst_mean}</strong>
            </span>
          </div>
          <div>
            <span className="text-sm">
              Least Variable: <strong>{rankings.least_variable}</strong>
            </span>
          </div>
          <div>
            <span className="text-sm">
              Most Variable: <strong>{rankings.most_variable}</strong>
            </span>
          </div>
        </div>
      </Card>

      {/* Comparison Table */}
      <Card className="mb-6 overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Scenario</TableHead>
              <TableHead className="text-right">Mean</TableHead>
              <TableHead className="text-right">Std Dev</TableHead>
              <TableHead className="text-right">CV (%)</TableHead>
              <TableHead className="text-right">95% CI</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {Object.entries(scenarios).map(([name, metrics]) => (
              <TableRow key={name}>
                <TableCell className="font-semibold">{name}</TableCell>
                <TableCell className="text-right">{metrics.mean.toFixed(2)}</TableCell>
                <TableCell className="text-right">{metrics.std.toFixed(2)}</TableCell>
                <TableCell className="text-right">
                  <Badge
                    variant={metrics.cv < 15 ? 'success' : metrics.cv < 30 ? 'warning' : 'destructive'}
                    size="sm"
                  >
                    {metrics.cv.toFixed(1)}%
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  [{metrics.ci_lower.toFixed(2)}, {metrics.ci_upper.toFixed(2)}]
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      {/* Mean Comparison Chart */}
      <div className="mb-6">
        <h4 className="text-sm font-medium mb-4">
          Mean Comparison with Confidence Intervals
        </h4>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={meanData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="scenario" />
            <YAxis />
            <RechartsTooltip />
            <Legend />
            <Bar dataKey="mean" fill="#8884d8" name="Mean" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* CV Comparison Chart */}
      <div>
        <h4 className="text-sm font-medium mb-4">
          Variability Comparison (Coefficient of Variation)
        </h4>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={cvData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="scenario" />
            <YAxis label={{ value: 'CV (%)', angle: -90, position: 'insideLeft' }} />
            <RechartsTooltip />
            <Bar dataKey="cv" fill="#82ca9d" name="CV (%)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

/**
 * Main StochasticAnalytics Component
 * Tabbed interface for all analytics views
 */
const StochasticAnalytics = ({ analyticsData }) => {
  const [activeTab, setActiveTab] = useState('variability');

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  if (!analyticsData) {
    return (
      <div className="p-6">
        <Alert variant="info">
          No analytics data available. Run a stochastic simulation first.
        </Alert>
      </div>
    );
  }

  // Determine which tabs to show based on available data
  const tabs = [];
  if (analyticsData.variability) tabs.push({ value: 'variability', label: 'Variability' });
  if (analyticsData.confidenceInterval) tabs.push({ value: 'confidence', label: 'Confidence Interval' });
  if (analyticsData.riskMetrics) tabs.push({ value: 'risk', label: 'Risk Metrics' });
  if (analyticsData.distributionFit) tabs.push({ value: 'fit', label: 'Distribution Fit' });
  if (analyticsData.scenarioComparison) tabs.push({ value: 'comparison', label: 'Scenario Comparison' });

  return (
    <div>
      <Tabs value={activeTab} onChange={handleTabChange}>
        <TabsList className="border-b border-border">
          {tabs.map(tab => (
            <Tab key={tab.value} value={tab.value} label={tab.label} />
          ))}
        </TabsList>

        <div className="p-6">
          <TabPanel value="variability">
            {analyticsData.variability && (
              <VariabilityAnalysis metrics={analyticsData.variability} />
            )}
          </TabPanel>
          <TabPanel value="confidence">
            {analyticsData.confidenceInterval && (
              <ConfidenceIntervalView ci={analyticsData.confidenceInterval} />
            )}
          </TabPanel>
          <TabPanel value="risk">
            {analyticsData.riskMetrics && (
              <RiskMetricsView metrics={analyticsData.riskMetrics} />
            )}
          </TabPanel>
          <TabPanel value="fit">
            {analyticsData.distributionFit && (
              <DistributionFitView fitResults={analyticsData.distributionFit} />
            )}
          </TabPanel>
          <TabPanel value="comparison">
            {analyticsData.scenarioComparison && (
              <ScenarioComparisonView comparison={analyticsData.scenarioComparison} />
            )}
          </TabPanel>
        </div>
      </Tabs>
    </div>
  );
};

export default StochasticAnalytics;
