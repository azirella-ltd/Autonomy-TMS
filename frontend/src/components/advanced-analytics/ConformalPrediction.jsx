/**
 * Conformal Prediction Component
 *
 * Distribution-free uncertainty quantification for supply chain planning.
 * Provides guaranteed prediction intervals without distributional assumptions.
 *
 * Features:
 * - Calibration from historical Plan vs Actual data
 * - Prediction intervals with coverage guarantees
 * - Safety stock calculation with formal service level
 * - Comparison: Conformal vs Traditional (Normal assumption)
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Alert,
  AlertDescription,
  Badge,
  Button,
  Input,
  Label,
  Spinner,
  Slider,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  TabsList,
  Tab,
  TabPanel,
} from '../common';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
  Line,
  ComposedChart,
} from 'recharts';
import { Info, Play, ArrowLeftRight, CheckCircle, AlertTriangle } from 'lucide-react';
import { api } from '../../services/api';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';

const ConformalPrediction = () => {
  const { formatProduct, formatSite, loadLookupsForConfig } = useDisplayPreferences();

  useEffect(() => { loadLookupsForConfig(); }, [loadLookupsForConfig]);
  const [activeTab, setActiveTab] = useState('calibration');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Calibration state
  const [calibrationAlpha, setCalibrationAlpha] = useState(0.1);
  const [calibrationResult, setCalibrationResult] = useState(null);

  // Prediction state
  const [pointForecast, setPointForecast] = useState(100);
  const [predictionResult, setPredictionResult] = useState(null);

  // Safety stock state
  const [safetyStockParams, setSafetyStockParams] = useState({
    expected_demand: 100,
    expected_lead_time: 7,
  });
  const [safetyStockResult, setSafetyStockResult] = useState(null);

  // Comparison state
  const [comparisonParams, setComparisonParams] = useState({
    point_forecast: 100,
    std_dev: 15,
    confidence: 0.9,
  });
  const [comparisonResult, setComparisonResult] = useState(null);

  // Calibrations summary
  const [calibrationsSummary, setCalibrationsSummary] = useState(null);

  // Forecast horizon
  const [horizonForecasts, setHorizonForecasts] = useState([100, 105, 110, 108, 112, 115, 118, 120, 122, 125, 128, 130, 132]);
  const [horizonResults, setHorizonResults] = useState(null);

  useEffect(() => {
    loadCalibrations();
    handleAutoCalibrate();
  }, []);

  const loadCalibrations = async () => {
    try {
      const response = await api.get('/conformal-prediction/calibrations');
      setCalibrationsSummary(response.data);
    } catch (err) {
      console.error('Failed to load calibrations:', err);
    }
  };

  const handleAutoCalibrate = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.post('/conformal-prediction/auto-calibrate', {
        alpha: calibrationAlpha,
      });
      setCalibrationResult(response.data);
      if (response.data.calibrated_count > 0) {
        setSuccess(`Calibrated ${response.data.calibrated_count} predictor(s) from historical data.`);
      }
      loadCalibrations();
    } catch (err) {
      setError(err.response?.data?.detail || 'Calibration failed');
    } finally {
      setLoading(false);
    }
  };

  const handlePredict = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.post('/conformal-prediction/predict', {
        variable: 'demand',
        point_forecast: pointForecast,
        product_id: 'DEMO_PRODUCT',
        site_id: 1,
      });
      setPredictionResult(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Prediction failed. Make sure to calibrate first.');
    } finally {
      setLoading(false);
    }
  };

  const handleSafetyStock = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.post('/conformal-prediction/safety-stock', {
        ...safetyStockParams,
        product_id: 'DEMO_PRODUCT',
        site_id: 1,
      });
      setSafetyStockResult(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Safety stock calculation failed');
    } finally {
      setLoading(false);
    }
  };

  const handleCompare = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get('/conformal-prediction/compare-methods', {
        params: {
          ...comparisonParams,
          product_id: 'DEMO_PRODUCT',
          site_id: 1,
        },
      });
      setComparisonResult(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Comparison failed');
    } finally {
      setLoading(false);
    }
  };

  const handleForecastHorizon = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.post('/conformal-prediction/forecast-horizon', {
        point_forecasts: horizonForecasts,
        product_id: 'DEMO_PRODUCT',
        site_id: 1,
      });
      setHorizonResults(response.data.forecasts);
    } catch (err) {
      setError(err.response?.data?.detail || 'Horizon forecast failed. Calibrate first.');
    } finally {
      setLoading(false);
    }
  };

  const renderCalibrationTab = () => (
    <div>
      <Alert variant="info" className="mb-6">
        <AlertDescription>
          <p className="font-semibold mb-1">What is Conformal Prediction?</p>
          <p className="text-sm">
            Unlike traditional methods that assume a normal distribution, conformal prediction provides
            <strong> guaranteed prediction intervals</strong> using only historical Plan vs Actual data.
            If you set 90% coverage, at least 90% of future actuals will fall within the interval.
          </p>
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 mb-4">
              <h3 className="text-lg font-semibold">Calibration Settings</h3>
              <button
                className="p-1 hover:bg-muted rounded-md transition-colors"
                title="Calibrates from historical Plan vs Actual data in the database"
              >
                <Info className="h-4 w-4 text-muted-foreground" />
              </button>
            </div>

            <p className="text-sm text-muted-foreground mb-4">
              Automatically calibrates from historical forecast vs actual data. Requires at least 10
              forecast-actual pairs per product-site combination.
            </p>

            <div className="space-y-4">
              <div>
                <Label>
                  Coverage Level: {((1 - calibrationAlpha) * 100).toFixed(0)}%
                </Label>
                <div className="mt-2">
                  <Slider
                    value={1 - calibrationAlpha}
                    onChange={(v) => setCalibrationAlpha(1 - v)}
                    min={0.8}
                    max={0.99}
                    step={0.01}
                  />
                </div>
                <div className="flex justify-between text-xs text-muted-foreground mt-1">
                  <span>80%</span>
                  <span>90%</span>
                  <span>95%</span>
                  <span>99%</span>
                </div>
              </div>
              <Button
                className="w-full"
                onClick={handleAutoCalibrate}
                disabled={loading}
              >
                {loading ? <Spinner className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
                Recalibrate
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          {calibrationResult && calibrationResult.calibrated_count > 0 ? (
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-2 mb-4">
                  <h3 className="text-lg font-semibold">Calibration Results</h3>
                  <Badge variant="success" className="flex items-center gap-1">
                    <CheckCircle className="h-3 w-3" />
                    {calibrationResult.calibrated_count} Calibrated
                  </Badge>
                </div>

                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Product / Site</TableCell>
                      <TableCell>Coverage</TableCell>
                      <TableCell>Quantile</TableCell>
                      <TableCell>Samples</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {calibrationResult.calibrations.map((cal, i) => (
                      <TableRow key={i}>
                        <TableCell className="text-sm">{formatProduct(cal.product_id)} / {formatSite(cal.site_id)}</TableCell>
                        <TableCell className="font-semibold">
                          {(cal.empirical_coverage * 100).toFixed(1)}%
                        </TableCell>
                        <TableCell>{cal.quantile.toFixed(2)}</TableCell>
                        <TableCell>{cal.n_samples}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          ) : calibrationResult && calibrationResult.calibrated_count === 0 ? (
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-2 mb-4">
                  <AlertTriangle className="h-5 w-5 text-amber-600" />
                  <h3 className="text-lg font-semibold">No Historical Data</h3>
                </div>
                <p className="text-sm text-muted-foreground">
                  No forecast vs actual data available for calibration. Conformal prediction requires
                  at least 10 historical forecast-actual pairs per product-site. Data accumulates
                  as forecasts are compared to actuals during planning cycles.
                </p>
              </CardContent>
            </Card>
          ) : null}

          {calibrationsSummary && (
            <Card>
              <CardContent className="pt-6">
                <h3 className="text-lg font-semibold mb-2">Active Calibrations</h3>
                <p className="text-sm text-muted-foreground">
                  Total calibrated predictors: {calibrationsSummary.total_calibrated}
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );

  const renderPredictionTab = () => (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <Card>
        <CardContent className="pt-6">
          <h3 className="text-lg font-semibold mb-4">Single Prediction</h3>

          <div className="mb-4">
            <Label htmlFor="point_forecast">Point Forecast</Label>
            <Input
              id="point_forecast"
              type="number"
              value={pointForecast}
              onChange={(e) => setPointForecast(parseFloat(e.target.value))}
            />
          </div>

          <Button
            className="w-full"
            onClick={handlePredict}
            disabled={loading}
          >
            Generate Prediction Interval
          </Button>

          {predictionResult && (
            <div className="mt-4 bg-muted p-4 rounded-lg">
              <p className="text-xl font-semibold">
                [{predictionResult.lower_bound.toFixed(1)}, {predictionResult.upper_bound.toFixed(1)}]
              </p>
              <p className="text-sm text-muted-foreground">
                Coverage Guarantee: {(predictionResult.coverage_guarantee * 100).toFixed(0)}%
              </p>
              <p className="text-sm text-muted-foreground">
                Interval Width: {predictionResult.interval_width.toFixed(1)}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <h3 className="text-lg font-semibold mb-4">Forecast Horizon (13 Weeks)</h3>

          <Button
            className="w-full mb-4"
            onClick={handleForecastHorizon}
            disabled={loading}
          >
            Generate Horizon Forecast
          </Button>

          {horizonResults && (
            <div className="h-[300px]">
              <ResponsiveContainer>
                <ComposedChart data={horizonResults}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="period" label={{ value: 'Week', position: 'bottom' }} />
                  <YAxis />
                  <RechartsTooltip />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="upper_bound"
                    fill="#8884d8"
                    fillOpacity={0.3}
                    stroke="none"
                    name="Upper Bound"
                  />
                  <Area
                    type="monotone"
                    dataKey="lower_bound"
                    fill="#ffffff"
                    fillOpacity={1}
                    stroke="none"
                    name="Lower Bound"
                  />
                  <Line
                    type="monotone"
                    dataKey="point_forecast"
                    stroke="#8884d8"
                    strokeWidth={2}
                    name="Point Forecast"
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );

  const renderSafetyStockTab = () => (
    <div>
      <Alert variant="info" className="mb-6">
        <AlertDescription>
          <p className="font-semibold mb-1">Conformal Safety Stock</p>
          <p className="text-sm">
            Traditional safety stock formulas assume normal distribution (SS = z * sigma * sqrt(LT)).
            Conformal safety stock uses calibrated intervals for <strong>guaranteed service levels</strong>.
          </p>
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardContent className="pt-6">
            <h3 className="text-lg font-semibold mb-4">Calculate Safety Stock</h3>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="expected_demand">Expected Demand (per period)</Label>
                <Input
                  id="expected_demand"
                  type="number"
                  value={safetyStockParams.expected_demand}
                  onChange={(e) => setSafetyStockParams({
                    ...safetyStockParams,
                    expected_demand: parseFloat(e.target.value)
                  })}
                />
              </div>
              <div>
                <Label htmlFor="expected_lead_time">Expected Lead Time (periods)</Label>
                <Input
                  id="expected_lead_time"
                  type="number"
                  value={safetyStockParams.expected_lead_time}
                  onChange={(e) => setSafetyStockParams({
                    ...safetyStockParams,
                    expected_lead_time: parseFloat(e.target.value)
                  })}
                />
              </div>
              <div className="col-span-2">
                <Button
                  className="w-full"
                  onClick={handleSafetyStock}
                  disabled={loading}
                >
                  Calculate
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {safetyStockResult && (
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-2 mb-4">
                <h3 className="text-lg font-semibold">Results</h3>
                <Badge variant="success">
                  {(safetyStockResult.service_level_guarantee * 100).toFixed(0)}% Service Level
                </Badge>
              </div>

              <Table>
                <TableBody>
                  <TableRow className="bg-emerald-50 dark:bg-emerald-950">
                    <TableCell className="font-semibold">Safety Stock</TableCell>
                    <TableCell className="font-semibold">{safetyStockResult.safety_stock.toFixed(1)} units</TableCell>
                  </TableRow>
                  <TableRow className="bg-blue-50 dark:bg-blue-950">
                    <TableCell className="font-semibold">Reorder Point</TableCell>
                    <TableCell className="font-semibold">{safetyStockResult.reorder_point.toFixed(1)} units</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Demand Interval</TableCell>
                    <TableCell>[{safetyStockResult.demand_lower.toFixed(1)}, {safetyStockResult.demand_upper.toFixed(1)}]</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Lead Time Interval</TableCell>
                    <TableCell>[{safetyStockResult.lead_time_lower.toFixed(1)}, {safetyStockResult.lead_time_upper.toFixed(1)}] periods</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Method</TableCell>
                    <TableCell>{safetyStockResult.method}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );

  const renderComparisonTab = () => (
    <div>
      <Alert variant="warning" className="mb-6">
        <AlertDescription>
          <p className="font-semibold mb-1">Traditional vs Conformal Prediction</p>
          <p className="text-sm">
            <strong>Traditional:</strong> Assumes normal distribution (Interval = mu +/- z*sigma). No actual coverage guarantee.
            <br />
            <strong>Conformal:</strong> Uses historical errors. <strong>Guaranteed coverage</strong> without assumptions.
          </p>
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardContent className="pt-6">
            <h3 className="text-lg font-semibold mb-4">Compare Methods</h3>

            <div className="space-y-4">
              <div>
                <Label htmlFor="comp_point_forecast">Point Forecast</Label>
                <Input
                  id="comp_point_forecast"
                  type="number"
                  value={comparisonParams.point_forecast}
                  onChange={(e) => setComparisonParams({
                    ...comparisonParams,
                    point_forecast: parseFloat(e.target.value)
                  })}
                />
              </div>
              <div>
                <Label htmlFor="comp_std_dev">Assumed Std Dev (Traditional)</Label>
                <Input
                  id="comp_std_dev"
                  type="number"
                  value={comparisonParams.std_dev}
                  onChange={(e) => setComparisonParams({
                    ...comparisonParams,
                    std_dev: parseFloat(e.target.value)
                  })}
                />
              </div>
              <div>
                <Label>Confidence: {(comparisonParams.confidence * 100).toFixed(0)}%</Label>
                <div className="mt-2">
                  <Slider
                    value={comparisonParams.confidence}
                    onChange={(v) => setComparisonParams({
                      ...comparisonParams,
                      confidence: v
                    })}
                    min={0.8}
                    max={0.99}
                    step={0.01}
                  />
                </div>
              </div>
              <Button
                className="w-full"
                onClick={handleCompare}
                disabled={loading}
              >
                <ArrowLeftRight className="mr-2 h-4 w-4" />
                Compare
              </Button>
            </div>
          </CardContent>
        </Card>

        {comparisonResult && (
          <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="bg-amber-50 dark:bg-amber-950 border-amber-200 dark:border-amber-800">
              <CardContent className="pt-6">
                <div className="flex items-center gap-2 mb-4">
                  <AlertTriangle className="h-5 w-5 text-amber-600" />
                  <h3 className="text-lg font-semibold">Traditional (Normal)</h3>
                </div>
                <p className="text-2xl font-bold mb-2">
                  [{comparisonResult.traditional_method.lower_bound.toFixed(1)}, {comparisonResult.traditional_method.upper_bound.toFixed(1)}]
                </p>
                <p className="text-sm text-muted-foreground">
                  Width: {comparisonResult.traditional_method.interval_width.toFixed(1)}
                </p>
                <p className="text-sm text-muted-foreground">
                  Z-score: {comparisonResult.traditional_method.z_score.toFixed(2)}
                </p>
                <Alert variant="warning" className="mt-4">
                  <AlertDescription className="text-xs">
                    {comparisonResult.traditional_method.caveat}
                  </AlertDescription>
                </Alert>
              </CardContent>
            </Card>

            <Card className="bg-emerald-50 dark:bg-emerald-950 border-emerald-200 dark:border-emerald-800">
              <CardContent className="pt-6">
                <div className="flex items-center gap-2 mb-4">
                  <CheckCircle className="h-5 w-5 text-emerald-600" />
                  <h3 className="text-lg font-semibold">Conformal (Guaranteed)</h3>
                </div>
                {comparisonResult.conformal_method.status === 'not_calibrated' ? (
                  <Alert variant="info">
                    <AlertDescription className="text-sm">
                      {comparisonResult.conformal_method.message}
                    </AlertDescription>
                  </Alert>
                ) : (
                  <>
                    <p className="text-2xl font-bold mb-2">
                      [{comparisonResult.conformal_method.lower_bound.toFixed(1)}, {comparisonResult.conformal_method.upper_bound.toFixed(1)}]
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Width: {comparisonResult.conformal_method.interval_width.toFixed(1)}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Coverage: {(comparisonResult.conformal_method.coverage_guarantee * 100).toFixed(0)}% GUARANTEED
                    </p>
                  </>
                )}
              </CardContent>
            </Card>

            <div className="md:col-span-2">
              <Alert variant="info">
                <AlertDescription>
                  <strong>Recommendation:</strong> {comparisonResult.recommendation}
                </AlertDescription>
              </Alert>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <h2 className="text-2xl font-semibold">Conformal Prediction</h2>
        <Badge variant="default">Distribution-Free</Badge>
      </div>
      <p className="text-sm text-muted-foreground mb-6">
        Guaranteed prediction intervals without distributional assumptions.
        Uses historical Plan vs Actual data for calibration.
      </p>

      {error && (
        <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {success && (
        <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}

      <Card className="mb-6">
        <CardContent className="p-0">
          <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)}>
            <TabsList>
              <Tab value="calibration" label="Calibration" />
              <Tab value="predictions" label="Predictions" />
              <Tab value="safety-stock" label="Safety Stock" />
              <Tab value="compare" label="Compare Methods" />
            </TabsList>
          </Tabs>
        </CardContent>
      </Card>

      <div className="mt-4">
        {activeTab === 'calibration' && renderCalibrationTab()}
        {activeTab === 'predictions' && renderPredictionTab()}
        {activeTab === 'safety-stock' && renderSafetyStockTab()}
        {activeTab === 'compare' && renderComparisonTab()}
      </div>
    </div>
  );
};

export default ConformalPrediction;
