/**
 * Conformal ATP Chart Component
 *
 * Displays ATP predictions with Conformal Prediction intervals.
 * Unlike Monte Carlo which estimates distributions, conformal prediction
 * provides *guaranteed* coverage - if configured for 90% coverage, the
 * interval will contain the true value at least 90% of the time.
 *
 * Features:
 * - Guaranteed coverage intervals (not probabilistic estimates)
 * - Comparison with Monte Carlo P10/P50/P90
 * - Adaptive method visualization showing alpha adjustment
 * - Calibration status indicator
 *
 * Props:
 * - gameId: Game ID
 * - scenarioUserId: ScenarioUser ID
 * - coverage: Target coverage (default 0.90)
 * - method: Conformal method (split, quantile, adaptive)
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Badge,
  Alert,
  AlertTitle,
  AlertDescription,
  Spinner,
  Button,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '../common';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  BarChart,
  Bar,
  Cell,
} from 'recharts';
import {
  AlertTriangle as WarningIcon,
  CheckCircle2 as CheckIcon,
  Info as InfoIcon,
  RefreshCw,
  Shield as ShieldIcon,
  Activity as ActivityIcon,
  Target as TargetIcon,
} from 'lucide-react';
import simulationApi from '../../services/api';
import { cn } from '@azirella-ltd/autonomy-frontend';

const ConformalATPChart = ({
  gameId,
  scenarioUserId,
  coverage: initialCoverage = 0.90,
  method: initialMethod = 'adaptive',
}) => {
  const [conformalData, setConformalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [coverage, setCoverage] = useState(initialCoverage);
  const [method, setMethod] = useState(initialMethod);

  useEffect(() => {
    fetchConformalATP();
  }, [gameId, scenarioUserId, coverage, method]);

  const fetchConformalATP = async () => {
    if (!gameId || !scenarioUserId) return;

    setLoading(true);
    setError(null);

    try {
      const data = await simulationApi.getConformalATP(
        gameId,
        scenarioUserId,
        coverage,
        method
      );
      setConformalData(data);
    } catch (err) {
      console.error('Error fetching conformal ATP:', err);
      setError(err.response?.data?.detail || 'Failed to fetch conformal ATP');
    } finally {
      setLoading(false);
    }
  };

  // Custom tooltip
  const CustomTooltip = ({ active, payload }) => {
    if (!active || !payload || payload.length === 0) {
      return null;
    }

    return (
      <Card className="p-2 bg-white/95 dark:bg-card/95 shadow-lg border">
        <CardContent className="p-2">
          <h4 className="font-semibold text-sm mb-2">Conformal Prediction</h4>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Point Estimate:</span>
              <span className="font-semibold text-primary">
                {conformalData?.atp_point} units
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Lower Bound:</span>
              <span className="font-semibold text-amber-600">
                {conformalData?.atp_lower} units
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Upper Bound:</span>
              <span className="font-semibold text-emerald-600">
                {conformalData?.atp_upper} units
              </span>
            </div>
            <div className="flex justify-between gap-4 pt-1.5 border-t border-border">
              <span className="text-muted-foreground">Guaranteed Coverage:</span>
              <span className="font-semibold">
                {(conformalData?.coverage * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  };

  if (loading) {
    return (
      <div className="flex justify-center p-8">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="error">
        <WarningIcon className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  if (!conformalData) {
    return (
      <Alert variant="info">
        <InfoIcon className="h-4 w-4" />
        <AlertDescription>No conformal ATP data available</AlertDescription>
      </Alert>
    );
  }

  // Build comparison chart data
  const comparisonData = [
    {
      name: 'Monte Carlo',
      lower: conformalData.monte_carlo_comparison?.mc_p10 || 0,
      point: conformalData.monte_carlo_comparison?.mc_p50 || 0,
      upper: conformalData.monte_carlo_comparison?.mc_p90 || 0,
      type: 'mc',
    },
    {
      name: 'Conformal',
      lower: conformalData.atp_lower,
      point: conformalData.atp_point,
      upper: conformalData.atp_upper,
      type: 'conformal',
    },
  ];

  // Coverage statistics
  const coverageStats = conformalData.coverage_stats || {};

  return (
    <Card className="mb-4">
      <CardContent className="pt-4">
        <div className="space-y-4">
          {/* Header */}
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <ShieldIcon className="h-5 w-5 text-primary" />
              Conformal Prediction ATP
            </h3>
            <div className="flex gap-2 items-center">
              {conformalData.is_calibrated ? (
                <Badge variant="success" className="gap-1">
                  <CheckIcon className="h-3 w-3" />
                  Calibrated
                </Badge>
              ) : (
                <Badge variant="warning" className="gap-1">
                  <WarningIcon className="h-3 w-3" />
                  Not Calibrated
                </Badge>
              )}
              <Badge variant="secondary" className="text-xs">
                {method} method
              </Badge>
              <Button
                variant="ghost"
                size="sm"
                onClick={fetchConformalATP}
                className="h-8 w-8 p-0"
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Controls */}
          <div className="flex gap-4 items-center">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Coverage:</span>
              <Select value={coverage.toString()} onValueChange={(v) => setCoverage(parseFloat(v))}>
                <SelectTrigger className="w-24 h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="0.80">80%</SelectItem>
                  <SelectItem value="0.90">90%</SelectItem>
                  <SelectItem value="0.95">95%</SelectItem>
                  <SelectItem value="0.99">99%</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Method:</span>
              <Select value={method} onValueChange={setMethod}>
                <SelectTrigger className="w-32 h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="split">Split</SelectItem>
                  <SelectItem value="quantile">Quantile</SelectItem>
                  <SelectItem value="adaptive">Adaptive</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Main Result Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card className="bg-amber-50 dark:bg-amber-950/30">
              <CardContent className="pt-4 pb-3">
                <p className="text-xs text-amber-600 dark:text-amber-400 font-medium">
                  Lower Bound
                </p>
                <p className="text-2xl font-bold text-amber-700 dark:text-amber-300">
                  {conformalData.atp_lower}
                </p>
                <p className="text-xs text-muted-foreground">units (min)</p>
              </CardContent>
            </Card>

            <Card className="bg-primary/10 border-2 border-primary/30">
              <CardContent className="pt-4 pb-3">
                <p className="text-xs text-primary font-medium">Point Estimate</p>
                <p className="text-2xl font-bold text-primary">
                  {conformalData.atp_point}
                </p>
                <p className="text-xs text-muted-foreground">units (expected)</p>
              </CardContent>
            </Card>

            <Card className="bg-emerald-50 dark:bg-emerald-950/30">
              <CardContent className="pt-4 pb-3">
                <p className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                  Upper Bound
                </p>
                <p className="text-2xl font-bold text-emerald-700 dark:text-emerald-300">
                  {conformalData.atp_upper}
                </p>
                <p className="text-xs text-muted-foreground">units (max)</p>
              </CardContent>
            </Card>

            <Card className="bg-blue-50 dark:bg-blue-950/30">
              <CardContent className="pt-4 pb-3">
                <p className="text-xs text-blue-600 dark:text-blue-400 font-medium">
                  Interval Width
                </p>
                <p className="text-2xl font-bold text-blue-700 dark:text-blue-300">
                  {conformalData.interval_width}
                </p>
                <p className="text-xs text-muted-foreground">units uncertainty</p>
              </CardContent>
            </Card>
          </div>

          {/* Coverage Guarantee Banner */}
          <Alert variant="default" className="bg-primary/5 border-primary/20">
            <ShieldIcon className="h-4 w-4 text-primary" />
            <AlertTitle className="text-primary">Coverage Guarantee</AlertTitle>
            <AlertDescription className="text-xs">
              The interval [{conformalData.atp_lower}, {conformalData.atp_upper}] is
              guaranteed to contain the true ATP value at least{' '}
              <strong>{(conformalData.coverage * 100).toFixed(0)}%</strong> of the time.
              This is a statistical guarantee, not a probabilistic estimate.
            </AlertDescription>
          </Alert>

          {/* Comparison Chart: Monte Carlo vs Conformal */}
          <div className="mt-4">
            <h4 className="text-sm font-semibold mb-2">
              Monte Carlo vs Conformal Comparison
            </h4>
            <div className="w-full h-[180px]">
              <ResponsiveContainer>
                <BarChart
                  data={comparisonData}
                  layout="vertical"
                  margin={{ top: 10, right: 30, left: 80, bottom: 10 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis dataKey="name" type="category" tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="lower" name="Lower" stackId="a" fill="#f59e0b" />
                  <Bar dataKey="point" name="Point" stackId="b" fill="#3b82f6" />
                  <Bar dataKey="upper" name="Upper" stackId="c" fill="#22c55e" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Calibration & Adaptive Stats */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardContent className="pt-4 pb-3">
                <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
                  <TargetIcon className="h-4 w-4 text-primary" />
                  Calibration Status
                </h4>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-muted-foreground">Calibration Points:</span>
                    <span className="ml-2 font-semibold">
                      {conformalData.calibration_size}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Min Required:</span>
                    <span className="ml-2 font-semibold">30</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Method:</span>
                    <span className="ml-2 font-semibold capitalize">{conformalData.method}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Status:</span>
                    <span
                      className={cn(
                        'ml-2 font-semibold',
                        conformalData.is_calibrated ? 'text-emerald-600' : 'text-amber-600'
                      )}
                    >
                      {conformalData.is_calibrated ? 'Ready' : 'Learning'}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {method === 'adaptive' && (
              <Card>
                <CardContent className="pt-4 pb-3">
                  <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
                    <ActivityIcon className="h-4 w-4 text-primary" />
                    Adaptive Statistics
                  </h4>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-muted-foreground">Current Alpha:</span>
                      <span className="ml-2 font-semibold">
                        {conformalData.adaptive_alpha?.toFixed(3) || 'N/A'}
                      </span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Target Alpha:</span>
                      <span className="ml-2 font-semibold">
                        {(1 - conformalData.coverage).toFixed(2)}
                      </span>
                    </div>
                    {coverageStats.empirical_coverage && (
                      <>
                        <div>
                          <span className="text-muted-foreground">Empirical Coverage:</span>
                          <span className="ml-2 font-semibold">
                            {(coverageStats.empirical_coverage * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Coverage Gap:</span>
                          <span
                            className={cn(
                              'ml-2 font-semibold',
                              Math.abs(coverageStats.coverage_gap || 0) < 0.05
                                ? 'text-emerald-600'
                                : 'text-amber-600'
                            )}
                          >
                            {((coverageStats.coverage_gap || 0) * 100).toFixed(1)}%
                          </span>
                        </div>
                      </>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Legend / Explanation */}
          <div className="p-3 bg-muted/50 rounded-lg">
            <h5 className="text-xs font-semibold mb-2">About Conformal Prediction</h5>
            <p className="text-xs text-muted-foreground">
              <strong>Conformal Prediction</strong> provides prediction intervals with
              statistical <em>coverage guarantees</em>. Unlike Monte Carlo simulation
              which estimates probability distributions, conformal prediction learns
              from historical forecast errors to calibrate interval widths that will
              contain the true value with the specified probability.
            </p>
            <ul className="text-xs text-muted-foreground mt-2 space-y-1 list-disc list-inside">
              <li>
                <strong>Split</strong>: Uses absolute residuals |y - ŷ| as nonconformity scores
              </li>
              <li>
                <strong>Quantile</strong>: Conformalized Quantile Regression - better for varying uncertainty
              </li>
              <li>
                <strong>Adaptive</strong>: Automatically adjusts to distribution shift over time
              </li>
            </ul>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default ConformalATPChart;
