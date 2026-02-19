/**
 * Sensitivity Analysis Component
 * Phase 6 Sprint 2: Advanced Analytics
 *
 * Features:
 * - Tornado diagram for OAT sensitivity analysis
 * - Sobol indices visualization with confidence intervals
 * - Parameter importance ranking
 * - Interactive controls for analysis parameters
 */

import React, { useState } from 'react';
import {
  Card,
  CardContent,
  Alert,
  AlertDescription,
  Button,
  Input,
  Label,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableHeader,
  Tabs,
  TabsList,
  Tab,
} from '../common';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { Info, Play } from 'lucide-react';
import { api } from '../../services/api';

const SensitivityAnalysis = ({ gameId, simulationData }) => {
  const [analysisType, setAnalysisType] = useState('oat'); // 'oat' or 'sobol'
  const [numSamples, setNumSamples] = useState(10);
  const [confidence, setConfidence] = useState(0.95);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [results, setResults] = useState(null);
  const [activeTab, setActiveTab] = useState('visualization');

  // Default parameter ranges (can be customized)
  const [paramRanges, setParamRanges] = useState({
    lead_time_mean: [5, 10],
    holding_cost: [1, 5],
    backlog_cost: [5, 15],
  });

  const [baseParams, setBaseParams] = useState({
    lead_time_mean: 7,
    holding_cost: 2,
    backlog_cost: 10,
  });

  const handleRunAnalysis = async () => {
    setLoading(true);
    setError(null);

    try {
      let response;

      if (analysisType === 'oat') {
        // Run OAT sensitivity analysis
        response = await api.post('/advanced-analytics/sensitivity', {
          base_params: baseParams,
          param_ranges: paramRanges,
          simulation_data: simulationData || generateMockData(),
          num_samples: numSamples,
          analysis_type: 'oat',
        });
      } else {
        // Run Sobol analysis
        response = await api.post('/advanced-analytics/sensitivity/sobol', {
          param_ranges: paramRanges,
          simulation_data: simulationData || generateMockData(),
          num_samples: numSamples * 10, // Sobol needs more samples
          confidence: confidence,
        });
      }

      setResults(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to run sensitivity analysis');
      console.error('Sensitivity analysis error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Generate mock simulation data for testing
  const generateMockData = () => {
    const data = [];
    Object.keys(paramRanges).forEach(param => {
      const [min, max] = paramRanges[param];
      for (let i = 0; i < numSamples; i++) {
        const value = min + (max - min) * (i / (numSamples - 1));
        data.push({
          params: { [param]: value },
          output: 10000 + Math.random() * 2000, // Mock total cost
        });
      }
    });
    return data;
  };

  // Prepare tornado diagram data
  const prepareTornadoData = () => {
    if (!results || analysisType !== 'oat') return [];

    return results.map(result => ({
      parameter: formatParameterName(result.parameter),
      low: result.min_output,
      high: result.max_output,
      range: result.output_range,
      sensitivity: result.sensitivity,
    }));
  };

  // Prepare Sobol indices data
  const prepareSobolData = () => {
    if (!results || analysisType !== 'sobol') return [];

    return results.map(result => ({
      parameter: formatParameterName(result.parameter),
      firstOrder: result.first_order,
      totalOrder: result.total_order,
      ciLower: result.confidence_interval[0],
      ciUpper: result.confidence_interval[1],
    }));
  };

  const formatParameterName = (param) => {
    return param
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  // Custom tooltip for tornado diagram
  const TornadoTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <Card className="p-3 shadow-lg">
          <CardContent className="p-0">
            <p className="font-medium">{data.parameter}</p>
            <p className="text-sm">
              Output Range: {data.range.toFixed(0)}
            </p>
            <p className="text-sm">
              Sensitivity: {data.sensitivity.toFixed(3)}
            </p>
            <p className="text-sm text-muted-foreground">
              Min: {data.low.toFixed(0)}
            </p>
            <p className="text-sm text-muted-foreground">
              Max: {data.high.toFixed(0)}
            </p>
          </CardContent>
        </Card>
      );
    }
    return null;
  };

  return (
    <div>
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center mb-4">
            <h2 className="text-xl font-semibold flex-grow">Sensitivity Analysis</h2>
            <button
              className="p-1 hover:bg-muted rounded-md transition-colors"
              title="Identify which parameters have the biggest impact on simulation outcomes"
            >
              <Info className="h-5 w-5 text-muted-foreground" />
            </button>
          </div>

          {/* Controls */}
          <div className="flex flex-wrap gap-4 mb-6">
            <div className="min-w-[150px]">
              <Label htmlFor="analysisType">Analysis Type</Label>
              <select
                id="analysisType"
                value={analysisType}
                onChange={(e) => setAnalysisType(e.target.value)}
                className="w-full h-10 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              >
                <option value="oat">One-At-a-Time (OAT)</option>
                <option value="sobol">Sobol Indices</option>
              </select>
            </div>

            <div className="w-[150px]">
              <Label htmlFor="numSamples">Number of Samples</Label>
              <Input
                id="numSamples"
                type="number"
                value={numSamples}
                onChange={(e) => setNumSamples(parseInt(e.target.value))}
                min={5}
                max={100}
              />
            </div>

            {analysisType === 'sobol' && (
              <div className="w-[150px]">
                <Label htmlFor="confidence">Confidence Level</Label>
                <Input
                  id="confidence"
                  type="number"
                  value={confidence}
                  onChange={(e) => setConfidence(parseFloat(e.target.value))}
                  min={0.8}
                  max={0.99}
                  step={0.01}
                />
              </div>
            )}

            <div className="self-end">
              <Button
                onClick={handleRunAnalysis}
                disabled={loading}
                className="h-10"
              >
                {loading ? <Spinner className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
                Run Analysis
              </Button>
            </div>
          </div>

          {/* Error Display */}
          {error && (
            <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Results Tabs */}
          {results && (
            <div>
              <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)} className="mb-4">
                <TabsList>
                  <Tab value="visualization" label="Visualization" />
                  <Tab value="table" label="Data Table" />
                  <Tab value="interpretation" label="Interpretation" />
                </TabsList>
              </Tabs>

              {/* Visualization Tab */}
              {activeTab === 'visualization' && (
                <div>
                  {analysisType === 'oat' ? (
                    <div>
                      <h3 className="text-lg font-semibold mb-2">Tornado Diagram</h3>
                      <p className="text-sm text-muted-foreground mb-4">
                        Parameters are sorted by their impact on the output. Wider bars indicate greater sensitivity.
                      </p>
                      <ResponsiveContainer width="100%" height={400}>
                        <BarChart
                          data={prepareTornadoData()}
                          layout="vertical"
                          margin={{ top: 20, right: 30, left: 120, bottom: 20 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis type="number" label={{ value: 'Output Value', position: 'bottom' }} />
                          <YAxis type="category" dataKey="parameter" />
                          <RechartsTooltip content={<TornadoTooltip />} />
                          <Legend />
                          <Bar dataKey="low" fill="#82ca9d" name="Low Value" />
                          <Bar dataKey="high" fill="#8884d8" name="High Value" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <div>
                      <h3 className="text-lg font-semibold mb-2">Sobol Sensitivity Indices</h3>
                      <p className="text-sm text-muted-foreground mb-4">
                        First-order indices show direct effects. Total-order indices include interactions.
                      </p>
                      <ResponsiveContainer width="100%" height={400}>
                        <BarChart
                          data={prepareSobolData()}
                          margin={{ top: 20, right: 30, left: 120, bottom: 20 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis
                            type="number"
                            domain={[0, 1]}
                            label={{ value: 'Sensitivity Index', position: 'bottom' }}
                          />
                          <YAxis type="category" dataKey="parameter" />
                          <RechartsTooltip />
                          <Legend />
                          <Bar dataKey="firstOrder" fill="#8884d8" name="First Order (Main Effect)" />
                          <Bar dataKey="totalOrder" fill="#82ca9d" name="Total Order (Total Effect)" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              )}

              {/* Data Table Tab */}
              {activeTab === 'table' && (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="font-bold">Parameter</TableHead>
                        {analysisType === 'oat' ? (
                          <>
                            <TableHead className="font-bold text-right">Sensitivity</TableHead>
                            <TableHead className="font-bold text-right">Output Range</TableHead>
                            <TableHead className="font-bold text-right">Min Output</TableHead>
                            <TableHead className="font-bold text-right">Max Output</TableHead>
                          </>
                        ) : (
                          <>
                            <TableHead className="font-bold text-right">First-Order Index</TableHead>
                            <TableHead className="font-bold text-right">Total-Order Index</TableHead>
                            <TableHead className="font-bold text-right">95% CI</TableHead>
                          </>
                        )}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {analysisType === 'oat'
                        ? results.map((row, idx) => (
                            <TableRow key={idx}>
                              <TableCell>{formatParameterName(row.parameter)}</TableCell>
                              <TableCell className="text-right">{row.sensitivity.toFixed(3)}</TableCell>
                              <TableCell className="text-right">{row.output_range.toFixed(0)}</TableCell>
                              <TableCell className="text-right">{row.min_output.toFixed(0)}</TableCell>
                              <TableCell className="text-right">{row.max_output.toFixed(0)}</TableCell>
                            </TableRow>
                          ))
                        : results.map((row, idx) => (
                            <TableRow key={idx}>
                              <TableCell>{formatParameterName(row.parameter)}</TableCell>
                              <TableCell className="text-right">{row.first_order.toFixed(3)}</TableCell>
                              <TableCell className="text-right">{row.total_order.toFixed(3)}</TableCell>
                              <TableCell className="text-right">
                                [{row.confidence_interval[0].toFixed(3)}, {row.confidence_interval[1].toFixed(3)}]
                              </TableCell>
                            </TableRow>
                          ))}
                    </TableBody>
                  </Table>
                </div>
              )}

              {/* Interpretation Tab */}
              {activeTab === 'interpretation' && (
                <div>
                  <h3 className="text-lg font-semibold mb-4">Interpretation Guide</h3>

                  {analysisType === 'oat' ? (
                    <div>
                      <h4 className="text-base font-medium mb-2">
                        One-At-a-Time (OAT) Sensitivity Analysis
                      </h4>
                      <p className="text-sm mb-4">
                        This analysis varies each parameter independently while holding others constant.
                      </p>
                      <div className="text-sm">
                        <p className="font-semibold mb-2">Key Metrics:</p>
                        <ul className="list-disc list-inside space-y-1 ml-2">
                          <li><strong>Sensitivity:</strong> Change in output per unit change in parameter (delta_output/delta_input)</li>
                          <li><strong>Output Range:</strong> Difference between maximum and minimum output</li>
                          <li><strong>Higher values:</strong> Indicate greater parameter importance</li>
                        </ul>
                      </div>
                      <Alert variant="info" className="mt-4">
                        <AlertDescription>
                          <strong>Recommendation:</strong> Focus optimization efforts on parameters with highest sensitivity values.
                        </AlertDescription>
                      </Alert>
                    </div>
                  ) : (
                    <div>
                      <h4 className="text-base font-medium mb-2">
                        Sobol Sensitivity Indices
                      </h4>
                      <p className="text-sm mb-4">
                        Variance-based global sensitivity analysis that accounts for parameter interactions.
                      </p>
                      <div className="text-sm">
                        <p className="font-semibold mb-2">Key Metrics:</p>
                        <ul className="list-disc list-inside space-y-1 ml-2">
                          <li><strong>First-Order Index (S<sub>i</sub>):</strong> Direct contribution to output variance (main effect)</li>
                          <li><strong>Total-Order Index (S<sub>Ti</sub>):</strong> Total contribution including interactions</li>
                          <li><strong>Difference (S<sub>Ti</sub> - S<sub>i</sub>):</strong> Interaction effects</li>
                        </ul>
                      </div>
                      <Alert variant="info" className="mt-4">
                        <AlertDescription>
                          <strong>Recommendation:</strong> Parameters with high total-order indices should be carefully controlled,
                          especially if they show large interaction effects.
                        </AlertDescription>
                      </Alert>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Loading State */}
          {loading && (
            <div className="flex justify-center items-center min-h-[300px]">
              <div className="text-center">
                <Spinner className="h-8 w-8 mx-auto" />
                <p className="text-sm mt-4">
                  Running {analysisType === 'oat' ? 'OAT' : 'Sobol'} sensitivity analysis...
                </p>
              </div>
            </div>
          )}

          {/* Initial State */}
          {!results && !loading && (
            <div className="text-center py-8">
              <p className="text-muted-foreground">
                Configure parameters and click "Run Analysis" to begin
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default SensitivityAnalysis;
