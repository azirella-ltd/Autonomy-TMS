/**
 * Time Series Analyzer Component
 * Phase 6 Sprint 2: Advanced Analytics
 *
 * Features:
 * - Autocorrelation Function (ACF) plots
 * - Partial Autocorrelation Function (PACF) plots
 * - Time series decomposition (trend, seasonal, residual)
 * - Forecast accuracy metrics
 * - Interactive lag selection
 */

import React, { useState } from 'react';
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
  Tabs,
  TabsList,
  Tab,
} from '../common';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
} from 'recharts';
import { Info, Play } from 'lucide-react';
import { api } from '../../services/api';

const TimeSeriesAnalyzer = ({ timeSeriesData, actualData, predictedData }) => {
  const [analysisMode, setAnalysisMode] = useState('acf'); // 'acf', 'decompose', 'forecast'
  const [maxLag, setMaxLag] = useState(20);
  const [confidence, setConfidence] = useState(0.95);
  const [period, setPeriod] = useState(13); // Quarterly for 52 weeks
  const [decompositionModel, setDecompositionModel] = useState('additive');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [acfResults, setAcfResults] = useState(null);
  const [decompositionResults, setDecompositionResults] = useState(null);
  const [forecastResults, setForecastResults] = useState(null);

  // Run ACF/PACF analysis
  const handleRunACF = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.post('/advanced-analytics/time-series/acf', {
        time_series: timeSeriesData || generateMockTimeSeries(),
        max_lag: maxLag,
        confidence: confidence,
      });

      setAcfResults(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to compute ACF');
      console.error('ACF analysis error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Run decomposition
  const handleRunDecomposition = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.post('/advanced-analytics/time-series/decompose', {
        time_series: timeSeriesData || generateMockTimeSeries(),
        period: period,
        model: decompositionModel,
      });

      setDecompositionResults(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to decompose time series');
      console.error('Decomposition error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Run forecast accuracy
  const handleRunForecastAccuracy = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.post('/advanced-analytics/forecast-accuracy', {
        actual: actualData || generateMockTimeSeries(),
        predicted: predictedData || generateMockForecasts(),
      });

      setForecastResults(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to compute forecast accuracy');
      console.error('Forecast accuracy error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Generate mock time series data
  const generateMockTimeSeries = () => {
    const n = 52;
    const data = [];
    let value = 100;

    for (let i = 0; i < n; i++) {
      // AR(1) with trend and seasonality
      const trend = 0.5 * i;
      const seasonal = 10 * Math.sin((2 * Math.PI * i) / 13);
      value = 50 + trend + seasonal + 0.7 * (value - 50) + (Math.random() - 0.5) * 10;
      data.push(value);
    }

    return data;
  };

  // Generate mock forecasts
  const generateMockForecasts = () => {
    const actual = generateMockTimeSeries();
    return actual.map(v => v + (Math.random() - 0.5) * 15);
  };

  // Prepare ACF data for visualization
  const prepareACFData = () => {
    if (!acfResults) return { acf: [], pacf: [] };

    const acfData = acfResults.lags.map((lag, idx) => ({
      lag,
      acf: acfResults.acf_values[idx],
      pacf: acfResults.pacf_values[idx],
      isSignificant:
        idx > 0 &&
        Math.abs(acfResults.acf_values[idx]) > acfResults.confidence_interval[1],
    }));

    return { acf: acfData, pacf: acfData };
  };

  // Prepare decomposition data
  const prepareDecompositionData = () => {
    if (!decompositionResults) return [];

    return decompositionResults.original.map((value, idx) => ({
      time: idx,
      original: value,
      trend: decompositionResults.trend[idx],
      seasonal: decompositionResults.seasonal[idx],
      residual: decompositionResults.residual[idx],
    }));
  };

  return (
    <div>
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center mb-4">
            <h2 className="text-xl font-semibold flex-grow">Time Series Analysis</h2>
            <button
              className="p-1 hover:bg-muted rounded-md transition-colors"
              title="Analyze temporal patterns, trends, and forecast accuracy"
            >
              <Info className="h-5 w-5 text-muted-foreground" />
            </button>
          </div>

          {/* Mode Selection */}
          <div className="mb-6">
            <Tabs
              value={analysisMode}
              onChange={(e, v) => setAnalysisMode(v)}
              className="mb-4"
            >
              <TabsList>
                <Tab value="acf" label="ACF / PACF" />
                <Tab value="decompose" label="Decomposition" />
                <Tab value="forecast" label="Forecast Accuracy" />
              </TabsList>
            </Tabs>

            {/* ACF Controls */}
            {analysisMode === 'acf' && (
              <div className="flex flex-wrap gap-4">
                <div className="w-[150px]">
                  <Label htmlFor="maxLag">Maximum Lag</Label>
                  <Input
                    id="maxLag"
                    type="number"
                    value={maxLag}
                    onChange={(e) => setMaxLag(parseInt(e.target.value))}
                    min={5}
                    max={100}
                  />
                </div>
                <div className="w-[150px]">
                  <Label htmlFor="acfConfidence">Confidence Level</Label>
                  <Input
                    id="acfConfidence"
                    type="number"
                    value={confidence}
                    onChange={(e) => setConfidence(parseFloat(e.target.value))}
                    min={0.8}
                    max={0.99}
                    step={0.01}
                  />
                </div>
                <div className="self-end">
                  <Button
                    onClick={handleRunACF}
                    disabled={loading}
                  >
                    {loading ? <Spinner className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
                    Compute ACF/PACF
                  </Button>
                </div>
              </div>
            )}

            {/* Decomposition Controls */}
            {analysisMode === 'decompose' && (
              <div className="flex flex-wrap gap-4">
                <div className="w-[150px]">
                  <Label htmlFor="period">Seasonal Period</Label>
                  <Input
                    id="period"
                    type="number"
                    value={period}
                    onChange={(e) => setPeriod(parseInt(e.target.value))}
                    min={2}
                    max={52}
                  />
                  <span className="text-xs text-muted-foreground">e.g., 13 for quarterly</span>
                </div>
                <div className="min-w-[150px]">
                  <Label htmlFor="model">Model</Label>
                  <select
                    id="model"
                    value={decompositionModel}
                    onChange={(e) => setDecompositionModel(e.target.value)}
                    className="w-full h-10 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                  >
                    <option value="additive">Additive</option>
                    <option value="multiplicative">Multiplicative</option>
                  </select>
                </div>
                <div className="self-end">
                  <Button
                    onClick={handleRunDecomposition}
                    disabled={loading}
                  >
                    {loading ? <Spinner className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
                    Decompose Series
                  </Button>
                </div>
              </div>
            )}

            {/* Forecast Accuracy Controls */}
            {analysisMode === 'forecast' && (
              <div>
                <Button
                  onClick={handleRunForecastAccuracy}
                  disabled={loading}
                >
                  {loading ? <Spinner className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
                  Compute Accuracy Metrics
                </Button>
                <p className="text-xs text-muted-foreground mt-2">
                  Requires actual and predicted time series data
                </p>
              </div>
            )}
          </div>

          {/* Error Display */}
          {error && (
            <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* ACF/PACF Results */}
          {analysisMode === 'acf' && acfResults && (
            <div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* ACF Plot */}
                <Card>
                  <CardContent className="pt-4">
                    <h3 className="text-lg font-semibold mb-2">
                      Autocorrelation Function (ACF)
                    </h3>
                    <p className="text-sm text-muted-foreground mb-4">
                      Correlation with lagged versions of the series
                    </p>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={prepareACFData().acf}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="lag" label={{ value: 'Lag', position: 'bottom' }} />
                        <YAxis
                          domain={[-1, 1]}
                          label={{ value: 'ACF', angle: -90, position: 'insideLeft' }}
                        />
                        <RechartsTooltip />
                        <ReferenceLine y={0} stroke="#000" />
                        <ReferenceLine
                          y={acfResults.confidence_interval[1]}
                          stroke="#f44336"
                          strokeDasharray="3 3"
                        />
                        <ReferenceLine
                          y={acfResults.confidence_interval[0]}
                          stroke="#f44336"
                          strokeDasharray="3 3"
                        />
                        <Bar dataKey="acf" fill="#8884d8">
                          {prepareACFData().acf.map((entry, index) => (
                            <Cell
                              key={`cell-${index}`}
                              fill={entry.isSignificant ? '#f44336' : '#8884d8'}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                    <p className="text-xs text-muted-foreground mt-2">
                      Red bars indicate significant autocorrelation
                    </p>
                  </CardContent>
                </Card>

                {/* PACF Plot */}
                <Card>
                  <CardContent className="pt-4">
                    <h3 className="text-lg font-semibold mb-2">
                      Partial Autocorrelation (PACF)
                    </h3>
                    <p className="text-sm text-muted-foreground mb-4">
                      Direct correlation after removing intermediate lags
                    </p>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={prepareACFData().pacf}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="lag" label={{ value: 'Lag', position: 'bottom' }} />
                        <YAxis
                          domain={[-1, 1]}
                          label={{ value: 'PACF', angle: -90, position: 'insideLeft' }}
                        />
                        <RechartsTooltip />
                        <ReferenceLine y={0} stroke="#000" />
                        <ReferenceLine
                          y={acfResults.confidence_interval[1]}
                          stroke="#f44336"
                          strokeDasharray="3 3"
                        />
                        <ReferenceLine
                          y={acfResults.confidence_interval[0]}
                          stroke="#f44336"
                          strokeDasharray="3 3"
                        />
                        <Bar dataKey="pacf" fill="#82ca9d" />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                {/* Significant Lags */}
                <div className="md:col-span-2">
                  <Card>
                    <CardContent className="pt-4">
                      <h3 className="text-lg font-semibold mb-2">Significant Lags</h3>
                      {acfResults.significant_lags && acfResults.significant_lags.length > 0 ? (
                        <div className="flex flex-wrap gap-2">
                          {acfResults.significant_lags.map((lag) => (
                            <Badge key={lag} variant="default">
                              Lag {lag}
                            </Badge>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          No significant autocorrelation detected
                        </p>
                      )}
                      <Alert variant="info" className="mt-4">
                        <AlertDescription>
                          Significant lags suggest temporal dependencies. These can guide forecasting model selection
                          (e.g., AR order for ARIMA models).
                        </AlertDescription>
                      </Alert>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </div>
          )}

          {/* Decomposition Results */}
          {analysisMode === 'decompose' && decompositionResults && (
            <div>
              <h3 className="text-lg font-semibold mb-2">
                Time Series Decomposition ({decompositionModel})
              </h3>
              <p className="text-sm text-muted-foreground mb-4">
                {decompositionModel === 'additive'
                  ? 'Y = Trend + Seasonal + Residual'
                  : 'Y = Trend x Seasonal x Residual'}
              </p>

              <div className="space-y-4">
                {/* Original Series */}
                <Card>
                  <CardContent className="pt-4">
                    <p className="text-sm font-medium mb-2">Original Series</p>
                    <ResponsiveContainer width="100%" height={150}>
                      <LineChart data={prepareDecompositionData()}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="time" />
                        <YAxis />
                        <RechartsTooltip />
                        <Line type="monotone" dataKey="original" stroke="#000" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                {/* Trend Component */}
                <Card>
                  <CardContent className="pt-4">
                    <p className="text-sm font-medium mb-2">Trend Component</p>
                    <ResponsiveContainer width="100%" height={150}>
                      <LineChart data={prepareDecompositionData()}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="time" />
                        <YAxis />
                        <RechartsTooltip />
                        <Line type="monotone" dataKey="trend" stroke="#1976d2" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                {/* Seasonal Component */}
                <Card>
                  <CardContent className="pt-4">
                    <p className="text-sm font-medium mb-2">Seasonal Component (Period: {period})</p>
                    <ResponsiveContainer width="100%" height={150}>
                      <LineChart data={prepareDecompositionData()}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="time" />
                        <YAxis />
                        <RechartsTooltip />
                        <ReferenceLine y={0} stroke="#000" />
                        <Line type="monotone" dataKey="seasonal" stroke="#4caf50" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                {/* Residual Component */}
                <Card>
                  <CardContent className="pt-4">
                    <p className="text-sm font-medium mb-2">Residual Component</p>
                    <ResponsiveContainer width="100%" height={150}>
                      <LineChart data={prepareDecompositionData()}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="time" />
                        <YAxis />
                        <RechartsTooltip />
                        <ReferenceLine y={0} stroke="#000" />
                        <Line type="monotone" dataKey="residual" stroke="#f44336" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </div>

              <Alert variant="info" className="mt-4">
                <AlertDescription>
                  <strong>Interpretation:</strong> The trend shows long-term direction, seasonal shows repeating
                  patterns, and residual shows random noise. Smaller residuals indicate better model fit.
                </AlertDescription>
              </Alert>
            </div>
          )}

          {/* Forecast Accuracy Results */}
          {analysisMode === 'forecast' && forecastResults && (
            <div>
              <h3 className="text-lg font-semibold mb-4">Forecast Accuracy Metrics</h3>

              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4">
                <Card>
                  <CardContent className="pt-4 text-center">
                    <p className="text-3xl font-bold text-primary">
                      {forecastResults.mape.toFixed(2)}%
                    </p>
                    <p className="text-sm font-medium text-muted-foreground">MAPE</p>
                    <p className="text-xs text-muted-foreground">
                      Mean Absolute Percentage Error
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="pt-4 text-center">
                    <p className="text-3xl font-bold text-primary">
                      {forecastResults.rmse.toFixed(2)}
                    </p>
                    <p className="text-sm font-medium text-muted-foreground">RMSE</p>
                    <p className="text-xs text-muted-foreground">
                      Root Mean Squared Error
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="pt-4 text-center">
                    <p className="text-3xl font-bold text-primary">
                      {forecastResults.mae.toFixed(2)}
                    </p>
                    <p className="text-sm font-medium text-muted-foreground">MAE</p>
                    <p className="text-xs text-muted-foreground">
                      Mean Absolute Error
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="pt-4 text-center">
                    <p className="text-3xl font-bold text-primary">
                      {forecastResults.mse.toFixed(2)}
                    </p>
                    <p className="text-sm font-medium text-muted-foreground">MSE</p>
                    <p className="text-xs text-muted-foreground">
                      Mean Squared Error
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="pt-4 text-center">
                    <p className="text-3xl font-bold text-primary">
                      {forecastResults.r_squared.toFixed(3)}
                    </p>
                    <p className="text-sm font-medium text-muted-foreground">R-squared</p>
                    <p className="text-xs text-muted-foreground">
                      Coefficient of Determination
                    </p>
                  </CardContent>
                </Card>
              </div>

              <Card className="mt-6">
                <CardContent className="pt-4">
                  <h4 className="text-base font-medium mb-2">Metric Interpretation</h4>
                  <hr className="mb-4" />
                  <p className="text-sm mb-3">
                    <strong>MAPE:</strong> {forecastResults.mape < 10 ? 'Excellent' : forecastResults.mape < 20 ? 'Good' : 'Fair'} forecast accuracy
                    ({forecastResults.mape < 10 ? '<10%' : forecastResults.mape < 20 ? '10-20%' : '>20%'})
                  </p>
                  <p className="text-sm mb-3">
                    <strong>R-squared:</strong> Model explains {(forecastResults.r_squared * 100).toFixed(1)}% of variance
                    ({forecastResults.r_squared > 0.8 ? 'Strong fit' : forecastResults.r_squared > 0.5 ? 'Moderate fit' : 'Weak fit'})
                  </p>
                  <p className="text-sm">
                    <strong>RMSE vs MAE:</strong> RMSE ({forecastResults.rmse.toFixed(2)}) {forecastResults.rmse > forecastResults.mae * 1.5 ? 'significantly' : 'slightly'} larger than MAE
                    suggests {forecastResults.rmse > forecastResults.mae * 1.5 ? 'large outlier errors exist' : 'errors are relatively uniform'}
                  </p>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Loading State */}
          {loading && (
            <div className="flex justify-center items-center min-h-[300px]">
              <div className="text-center">
                <Spinner className="h-8 w-8 mx-auto" />
                <p className="text-sm mt-4">Analyzing time series...</p>
              </div>
            </div>
          )}

          {/* Initial State */}
          {!acfResults && !decompositionResults && !forecastResults && !loading && (
            <div className="text-center py-8">
              <p className="text-muted-foreground">
                Select analysis mode and click the button to begin
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default TimeSeriesAnalyzer;
