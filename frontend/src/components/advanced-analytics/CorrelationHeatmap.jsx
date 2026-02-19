/**
 * Correlation Heatmap Component
 * Phase 6 Sprint 2: Advanced Analytics
 *
 * Features:
 * - Correlation matrix heatmap visualization
 * - Multiple correlation methods (Pearson, Spearman, Kendall)
 * - Strong correlation detection and highlighting
 * - Interactive tooltips with p-values
 * - Color-coded by correlation strength
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableHeader,
  Tabs,
  TabsList,
  Tab,
  TabPanel,
} from '../common';
import { Info, Play } from 'lucide-react';
import { api } from '../../services/api';

const CorrelationHeatmap = ({ metricsData }) => {
  const [method, setMethod] = useState('pearson'); // 'pearson', 'spearman', 'kendall'
  const [threshold, setThreshold] = useState(0.7);
  const [pValueThreshold, setPValueThreshold] = useState(0.05);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [results, setResults] = useState(null);
  const [activeTab, setActiveTab] = useState('heatmap');
  const [hoveredCell, setHoveredCell] = useState(null);

  const handleRunAnalysis = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.post('/advanced-analytics/correlation', {
        data: metricsData || generateMockData(),
        method: method,
        threshold: threshold,
        p_value_threshold: pValueThreshold,
      });

      setResults(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to compute correlation matrix');
      console.error('Correlation analysis error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Generate mock metrics data for testing
  const generateMockData = () => {
    const n = 100;
    const totalCost = Array.from({ length: n }, () => 10000 + Math.random() * 2000);
    const inventory = totalCost.map(c => 50 + 0.005 * c + (Math.random() - 0.5) * 20);
    const serviceLevel = totalCost.map(c => 1.0 - 0.00003 * c + (Math.random() - 0.5) * 0.1);
    const backlog = serviceLevel.map(s => 100 * (1 - s) + (Math.random() - 0.5) * 10);

    return {
      total_cost: totalCost,
      inventory: inventory,
      service_level: serviceLevel.map(s => Math.max(0, Math.min(1, s))),
      backlog: backlog.map(b => Math.max(0, b)),
    };
  };

  // Get correlation color based on value
  const getCorrelationColor = (value) => {
    const absValue = Math.abs(value);
    if (absValue >= 0.9) return value > 0 ? '#1565c0' : '#c62828'; // Strong
    if (absValue >= 0.7) return value > 0 ? '#1976d2' : '#d32f2f'; // Moderate-strong
    if (absValue >= 0.5) return value > 0 ? '#42a5f5' : '#ef5350'; // Moderate
    if (absValue >= 0.3) return value > 0 ? '#90caf9' : '#e57373'; // Weak-moderate
    return '#e0e0e0'; // Weak
  };

  // Get correlation strength label
  const getCorrelationStrength = (value) => {
    const absValue = Math.abs(value);
    if (absValue >= 0.9) return 'Very Strong';
    if (absValue >= 0.7) return 'Strong';
    if (absValue >= 0.5) return 'Moderate';
    if (absValue >= 0.3) return 'Weak';
    return 'Very Weak';
  };

  // Format variable name
  const formatVariableName = (name) => {
    return name
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  // Render heatmap cell
  const renderHeatmapCell = (row, col) => {
    if (!results) return null;

    const value = results.correlation_matrix[row][col];
    const pValue = results.p_values[row][col];
    const isSignificant = pValue < pValueThreshold;
    const isDiagonal = row === col;

    return (
      <div
        key={`${row}-${col}`}
        className={`
          w-20 h-20 flex flex-col items-center justify-center border border-border
          transition-all duration-200
          ${isDiagonal ? 'bg-muted cursor-default' : 'cursor-pointer hover:scale-110 hover:z-10 hover:shadow-lg'}
        `}
        style={{
          backgroundColor: isDiagonal ? undefined : getCorrelationColor(value),
        }}
        onMouseEnter={() => !isDiagonal && setHoveredCell({ row, col, value, pValue })}
        onMouseLeave={() => setHoveredCell(null)}
      >
        <span
          className={`text-sm font-bold ${
            isDiagonal ? 'text-muted-foreground' : Math.abs(value) > 0.5 ? 'text-white' : 'text-foreground'
          }`}
        >
          {value.toFixed(2)}
        </span>
        {!isDiagonal && isSignificant && (
          <span className={`text-xs ${Math.abs(value) > 0.5 ? 'text-white' : 'text-muted-foreground'}`}>
            *
          </span>
        )}
      </div>
    );
  };

  return (
    <div>
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center mb-4">
            <h2 className="text-xl font-semibold flex-grow">Correlation Analysis</h2>
            <button
              className="p-1 hover:bg-muted rounded-md transition-colors"
              title="Analyze relationships between performance metrics"
            >
              <Info className="h-5 w-5 text-muted-foreground" />
            </button>
          </div>

          {/* Controls */}
          <div className="flex flex-wrap gap-4 mb-6">
            <div className="min-w-[150px]">
              <Label htmlFor="method">Method</Label>
              <select
                id="method"
                value={method}
                onChange={(e) => setMethod(e.target.value)}
                className="w-full h-10 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              >
                <option value="pearson">Pearson (Linear)</option>
                <option value="spearman">Spearman (Rank)</option>
                <option value="kendall">Kendall (Rank)</option>
              </select>
            </div>

            <div className="w-[180px]">
              <Label htmlFor="threshold">Correlation Threshold</Label>
              <Input
                id="threshold"
                type="number"
                value={threshold}
                onChange={(e) => setThreshold(parseFloat(e.target.value))}
                min={0}
                max={1}
                step={0.1}
              />
              <span className="text-xs text-muted-foreground">For strong correlations</span>
            </div>

            <div className="w-[180px]">
              <Label htmlFor="pValueThreshold">P-Value Threshold</Label>
              <Input
                id="pValueThreshold"
                type="number"
                value={pValueThreshold}
                onChange={(e) => setPValueThreshold(parseFloat(e.target.value))}
                min={0.001}
                max={0.1}
                step={0.01}
              />
              <span className="text-xs text-muted-foreground">Significance level</span>
            </div>

            <div className="self-end">
              <Button
                onClick={handleRunAnalysis}
                disabled={loading}
                className="h-10"
              >
                {loading ? <Spinner className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
                Compute Correlations
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
                  <Tab value="heatmap" label="Heatmap" />
                  <Tab value="strong" label="Strong Correlations" />
                  <Tab value="matrix" label="Correlation Matrix" />
                </TabsList>
              </Tabs>

              {/* Heatmap Tab */}
              {activeTab === 'heatmap' && (
                <div>
                  <h3 className="text-lg font-semibold mb-2">
                    Correlation Heatmap ({method.charAt(0).toUpperCase() + method.slice(1)})
                  </h3>
                  <p className="text-sm text-muted-foreground mb-4">
                    * indicates statistically significant (p &lt; {pValueThreshold})
                  </p>

                  <div className="overflow-x-auto mb-6">
                    <div className="flex flex-col items-start">
                      {/* Column headers */}
                      <div className="flex">
                        <div className="w-[120px]" /> {/* Space for row labels */}
                        {results.variables.map((variable, idx) => (
                          <div
                            key={idx}
                            className="w-20 text-center"
                            style={{
                              transform: 'rotate(-45deg)',
                              transformOrigin: 'left bottom',
                              marginBottom: '8px',
                              marginTop: '24px',
                            }}
                          >
                            <span className="text-xs whitespace-nowrap">
                              {formatVariableName(variable)}
                            </span>
                          </div>
                        ))}
                      </div>

                      {/* Heatmap rows */}
                      {results.variables.map((rowVariable, rowIdx) => (
                        <div key={rowIdx} className="flex items-center">
                          <div className="w-[120px] pr-2">
                            <span className="text-xs whitespace-nowrap">
                              {formatVariableName(rowVariable)}
                            </span>
                          </div>
                          {results.variables.map((colVariable, colIdx) =>
                            renderHeatmapCell(rowIdx, colIdx)
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Hovered cell tooltip */}
                  {hoveredCell && (
                    <Card className="mb-4 bg-muted">
                      <CardContent className="py-3">
                        <p className="font-medium">
                          {formatVariableName(results.variables[hoveredCell.row])} vs{' '}
                          {formatVariableName(results.variables[hoveredCell.col])}
                        </p>
                        <p className="text-sm">
                          Correlation: {hoveredCell.value.toFixed(3)} ({getCorrelationStrength(hoveredCell.value)})
                        </p>
                        <p className="text-sm">
                          P-value: {hoveredCell.pValue.toFixed(4)}{' '}
                          {hoveredCell.pValue < pValueThreshold ? '(Significant)' : '(Not significant)'}
                        </p>
                      </CardContent>
                    </Card>
                  )}

                  {/* Color legend */}
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm mr-4">Color Scale:</span>
                    <Badge className="text-white" style={{ backgroundColor: '#1976d2' }}>
                      Strong Positive (0.7+)
                    </Badge>
                    <Badge className="text-white" style={{ backgroundColor: '#42a5f5' }}>
                      Moderate Positive (0.5-0.7)
                    </Badge>
                    <Badge style={{ backgroundColor: '#90caf9' }}>
                      Weak (0.3-0.5)
                    </Badge>
                    <Badge style={{ backgroundColor: '#e0e0e0' }}>
                      Very Weak (&lt;0.3)
                    </Badge>
                    <Badge className="text-white" style={{ backgroundColor: '#ef5350' }}>
                      Moderate Negative (-0.5 to -0.7)
                    </Badge>
                    <Badge className="text-white" style={{ backgroundColor: '#d32f2f' }}>
                      Strong Negative (-0.7+)
                    </Badge>
                  </div>
                </div>
              )}

              {/* Strong Correlations Tab */}
              {activeTab === 'strong' && (
                <div>
                  <h3 className="text-lg font-semibold mb-2">
                    Strong Correlations (|r| &gt;= {threshold})
                  </h3>
                  <p className="text-sm text-muted-foreground mb-4">
                    Statistically significant correlations (p &lt; {pValueThreshold})
                  </p>

                  {results.strong_correlations && results.strong_correlations.length > 0 ? (
                    <div className="overflow-x-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="font-bold">Variable 1</TableHead>
                            <TableHead className="font-bold">Variable 2</TableHead>
                            <TableHead className="font-bold text-right">Correlation</TableHead>
                            <TableHead className="font-bold text-right">P-Value</TableHead>
                            <TableHead className="font-bold">Strength</TableHead>
                            <TableHead className="font-bold">Direction</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {results.strong_correlations.map((corr, idx) => (
                            <TableRow key={idx}>
                              <TableCell>{formatVariableName(corr.var1)}</TableCell>
                              <TableCell>{formatVariableName(corr.var2)}</TableCell>
                              <TableCell className="text-right">
                                <span
                                  className="font-bold"
                                  style={{ color: getCorrelationColor(corr.correlation) }}
                                >
                                  {corr.correlation.toFixed(3)}
                                </span>
                              </TableCell>
                              <TableCell className="text-right">{corr.p_value.toFixed(4)}</TableCell>
                              <TableCell>
                                <Badge variant={corr.strength === 'strong' ? 'default' : 'secondary'}>
                                  {corr.strength}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <Badge variant={corr.correlation > 0 ? 'success' : 'error'}>
                                  {corr.correlation > 0 ? 'Positive' : 'Negative'}
                                </Badge>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  ) : (
                    <Alert variant="info">
                      <AlertDescription>
                        No strong correlations found with current threshold (|r| &gt;= {threshold})
                      </AlertDescription>
                    </Alert>
                  )}
                </div>
              )}

              {/* Correlation Matrix Tab */}
              {activeTab === 'matrix' && (
                <div>
                  <h3 className="text-lg font-semibold mb-2">Full Correlation Matrix</h3>
                  <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
                    <Table>
                      <TableHeader className="sticky top-0 bg-background">
                        <TableRow>
                          <TableHead className="font-bold">Variable</TableHead>
                          {results.variables.map((variable, idx) => (
                            <TableHead key={idx} className="font-bold text-right">
                              {formatVariableName(variable)}
                            </TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {results.variables.map((rowVariable, rowIdx) => (
                          <TableRow key={rowIdx}>
                            <TableCell className="font-bold">{formatVariableName(rowVariable)}</TableCell>
                            {results.variables.map((colVariable, colIdx) => {
                              const value = results.correlation_matrix[rowIdx][colIdx];
                              const pValue = results.p_values[rowIdx][colIdx];
                              return (
                                <TableCell
                                  key={colIdx}
                                  className="text-right"
                                  style={{
                                    backgroundColor: rowIdx === colIdx ? '#f5f5f5' : getCorrelationColor(value) + '40',
                                  }}
                                >
                                  {value.toFixed(3)}
                                  {rowIdx !== colIdx && pValue < pValueThreshold && '*'}
                                </TableCell>
                              );
                            })}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    * Statistically significant (p &lt; {pValueThreshold})
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Loading State */}
          {loading && (
            <div className="flex justify-center items-center min-h-[300px]">
              <div className="text-center">
                <Spinner className="h-8 w-8 mx-auto" />
                <p className="text-sm mt-4">Computing {method} correlations...</p>
              </div>
            </div>
          )}

          {/* Initial State */}
          {!results && !loading && (
            <div className="text-center py-8">
              <p className="text-muted-foreground">
                Select correlation method and click "Compute Correlations" to begin
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default CorrelationHeatmap;
