/**
 * Weight History Chart Component
 *
 * Phase 4: Multi-Agent Orchestration - Weight Convergence Visualization
 * Shows how agent weights evolved over time during adaptive learning.
 *
 * Features:
 * - Line chart showing weight evolution
 * - Color-coded lines per agent (LLM, GNN, TRM)
 * - Confidence score overlay
 * - Performance metrics tooltip
 * - Convergence indicators
 *
 * Props:
 * - scenarioId: Scenario ID
 * - refreshInterval: Auto-refresh interval in ms (optional)
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Spinner,
} from '../common';
import { cn } from '../../lib/utils/cn';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  Area,
  ComposedChart,
} from 'recharts';
import {
  TrendingUp,
  CheckCircle,
  RefreshCw,
  Activity,
} from 'lucide-react';
import { api } from '../../services/api';

const COLORS = {
  llm: '#2196f3',
  gnn: '#4caf50',
  trm: '#ff9800',
  confidence: '#9c27b0',
};

const AGENT_NAMES = {
  llm: 'LLM (GPT-4)',
  gnn: 'Network Agent',
  trm: 'AI Agent',
};

const WeightHistoryChart = ({ scenarioId, refreshInterval = null }) => {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [converged, setConverged] = useState(false);
  const [convergencePoint, setConvergencePoint] = useState(null);

  useEffect(() => {
    fetchWeightHistory();

    if (refreshInterval) {
      const interval = setInterval(fetchWeightHistory, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [scenarioId, refreshInterval]);

  const fetchWeightHistory = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.get(`/mixed-scenarios/${scenarioId}/weight-history?limit=100`);
      const data = response.data;

      // Transform data for chart
      const transformedData = data.history.map((record, index) => ({
        sample: index + 1,
        llm: record.weights.llm || 0,
        gnn: record.weights.gnn || 0,
        trm: record.weights.trm || 0,
        confidence: record.num_samples >= 30 ? 1.0 : record.num_samples / 30,
        timestamp: record.timestamp,
        num_samples: record.num_samples,
        performance_metrics: record.performance_metrics || {}
      }));

      setHistory(transformedData);

      // Detect convergence (when weight changes < 0.01 for 5+ consecutive samples)
      if (transformedData.length >= 10) {
        const recentData = transformedData.slice(-10);
        const weightVariances = {
          llm: calculateVariance(recentData.map(d => d.llm)),
          gnn: calculateVariance(recentData.map(d => d.gnn)),
          trm: calculateVariance(recentData.map(d => d.trm))
        };

        const maxVariance = Math.max(...Object.values(weightVariances));
        if (maxVariance < 0.001) {
          setConverged(true);
          // Find convergence point (first point where variance dropped below threshold)
          for (let i = 10; i < transformedData.length; i++) {
            const windowData = transformedData.slice(i - 10, i);
            const windowVariance = Math.max(
              calculateVariance(windowData.map(d => d.llm)),
              calculateVariance(windowData.map(d => d.gnn)),
              calculateVariance(windowData.map(d => d.trm))
            );
            if (windowVariance < 0.001) {
              setConvergencePoint(i);
              break;
            }
          }
        } else {
          setConverged(false);
          setConvergencePoint(null);
        }
      }
    } catch (err) {
      console.error('Failed to fetch weight history:', err);
      setError(err.response?.data?.detail || 'Failed to fetch weight history');
    } finally {
      setLoading(false);
    }
  };

  const calculateVariance = (values) => {
    if (values.length === 0) return 0;
    const mean = values.reduce((sum, val) => sum + val, 0) / values.length;
    const variance = values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length;
    return variance;
  };

  // Custom tooltip
  const CustomTooltip = ({ active, payload }) => {
    if (!active || !payload || payload.length === 0) {
      return null;
    }

    const data = payload[0].payload;

    return (
      <Card className="p-1 bg-white/95 border border-gray-300" padding="none">
        <CardContent className="p-2">
          <p className="text-xs font-bold mb-1">
            Sample {data.sample}
          </p>
          <hr className="my-1 border-gray-200" />
          <div className="space-y-1">
            <div className="flex justify-between gap-2">
              <span className="text-xs" style={{ color: COLORS.llm }}>
                LLM:
              </span>
              <span className="text-xs font-bold">
                {(data.llm * 100).toFixed(1)}%
              </span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-xs" style={{ color: COLORS.gnn }}>
                Network Agent:
              </span>
              <span className="text-xs font-bold">
                {(data.gnn * 100).toFixed(1)}%
              </span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-xs" style={{ color: COLORS.trm }}>
                AI Agent:
              </span>
              <span className="text-xs font-bold">
                {(data.trm * 100).toFixed(1)}%
              </span>
            </div>
            <hr className="my-1 border-gray-200" />
            <div className="flex justify-between gap-2">
              <span className="text-xs text-gray-500">
                Confidence:
              </span>
              <span className="text-xs font-bold">
                {(data.confidence * 100).toFixed(0)}%
              </span>
            </div>
            {Object.keys(data.performance_metrics).length > 0 && (
              <>
                <hr className="my-1 border-gray-200" />
                <p className="text-xs text-gray-500">
                  Performance:
                </p>
                {Object.entries(data.performance_metrics).map(([agent, perf]) => (
                  <div key={agent} className="flex justify-between gap-2 pl-2">
                    <span className="text-xs">
                      {agent.toUpperCase()}:
                    </span>
                    <span className="text-xs font-bold">
                      {(perf * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </>
            )}
          </div>
        </CardContent>
      </Card>
    );
  };

  if (loading && history.length === 0) {
    return (
      <Card className="mb-4" padding="none">
        <CardContent className="p-6">
          <div className="flex justify-center p-8">
            <Spinner size="lg" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="mb-4" padding="none">
        <CardContent className="p-6">
          <Alert variant="error">
            {error}
          </Alert>
        </CardContent>
      </Card>
    );
  }

  if (history.length === 0) {
    return (
      <Card className="mb-4" padding="none">
        <CardContent className="p-6">
          <Alert variant="info" icon={Activity}>
            No weight history yet. Weights will be recorded as the scenario progresses and adaptive learning runs.
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="mb-4" padding="none">
      <CardContent className="p-6">
        <div className="space-y-6">
          {/* Header */}
          <div className="flex justify-between items-center">
            <h6 className="text-lg font-semibold">Weight Evolution Over Time</h6>
            <div className="flex flex-row items-center gap-2">
              {converged && (
                <span title={`Weights converged at sample ${convergencePoint}`}>
                  <Badge
                    variant="success"
                    size="sm"
                    icon={<CheckCircle className="h-3 w-3" />}
                  >
                    Converged
                  </Badge>
                </span>
              )}
              <Badge
                variant="outline"
                size="sm"
              >
                {history.length} samples
              </Badge>
              <Button
                size="sm"
                variant="outline"
                leftIcon={<RefreshCw className="h-4 w-4" />}
                onClick={fetchWeightHistory}
                disabled={loading}
              >
                Refresh
              </Button>
            </div>
          </div>

          {/* Chart */}
          <div className="w-full h-[400px]">
            <ResponsiveContainer>
              <ComposedChart
                data={history}
                margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis
                  dataKey="sample"
                  label={{ value: 'Learning Sample', position: 'insideBottom', offset: -10 }}
                  tick={{ fontSize: 12 }}
                />
                <YAxis
                  label={{ value: 'Weight', angle: -90, position: 'insideLeft' }}
                  tick={{ fontSize: 12 }}
                  domain={[0, 1]}
                  ticks={[0, 0.2, 0.4, 0.6, 0.8, 1.0]}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend
                  verticalAlign="top"
                  height={36}
                  wrapperStyle={{ fontSize: '12px' }}
                />

                {/* Equal weights reference line */}
                <ReferenceLine
                  y={0.333}
                  stroke="#ccc"
                  strokeDasharray="3 3"
                  label={{
                    value: 'Equal (33.3%)',
                    position: 'right',
                    fill: '#999',
                    fontSize: 10,
                  }}
                />

                {/* Convergence point marker */}
                {converged && convergencePoint && (
                  <ReferenceLine
                    x={convergencePoint}
                    stroke="#4caf50"
                    strokeDasharray="5 5"
                    label={{
                      value: 'Converged',
                      position: 'top',
                      fill: '#4caf50',
                      fontSize: 11,
                    }}
                  />
                )}

                {/* Weight lines */}
                <Line
                  type="monotone"
                  dataKey="llm"
                  stroke={COLORS.llm}
                  strokeWidth={2}
                  dot={{ fill: COLORS.llm, r: 3 }}
                  activeDot={{ r: 5 }}
                  name="LLM Weight"
                />
                <Line
                  type="monotone"
                  dataKey="gnn"
                  stroke={COLORS.gnn}
                  strokeWidth={2}
                  dot={{ fill: COLORS.gnn, r: 3 }}
                  activeDot={{ r: 5 }}
                  name="Network Agent Weight"
                />
                <Line
                  type="monotone"
                  dataKey="trm"
                  stroke={COLORS.trm}
                  strokeWidth={2}
                  dot={{ fill: COLORS.trm, r: 3 }}
                  activeDot={{ r: 5 }}
                  name="AI Agent Weight"
                />

                {/* Confidence area (background) */}
                <Area
                  type="monotone"
                  dataKey="confidence"
                  fill={COLORS.confidence}
                  fillOpacity={0.1}
                  stroke="none"
                  name="Confidence"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Convergence Status */}
          {history.length >= 10 && (
            <div className={cn(
              'p-4 rounded-lg',
              converged ? 'bg-emerald-50 dark:bg-emerald-950' : 'bg-gray-100 dark:bg-gray-800'
            )}>
              <h6 className="text-sm font-semibold mb-1">
                {converged ? '\u2713 Weight Convergence Detected' : 'Learning In Progress'}
              </h6>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {converged
                  ? `Weights have stabilized after ${convergencePoint} samples. The ensemble has converged to optimal weights based on agent performance.`
                  : `Weights are still adapting. Convergence expected after ~30 samples when variance drops below 0.1%.`
                }
              </p>
            </div>
          )}

          {/* Current Weights Summary */}
          {history.length > 0 && (
            <div className="p-4 bg-card rounded-lg border border-border">
              <h6 className="text-sm font-semibold mb-3">
                Current Weights (Latest Sample)
              </h6>
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1">
                  <span className="text-xs" style={{ color: COLORS.llm }}>
                    LLM
                  </span>
                  <p className="text-xl font-semibold" style={{ color: COLORS.llm }}>
                    {(history[history.length - 1].llm * 100).toFixed(1)}%
                  </p>
                </div>
                <div className="space-y-1">
                  <span className="text-xs" style={{ color: COLORS.gnn }}>
                    Network Agent
                  </span>
                  <p className="text-xl font-semibold" style={{ color: COLORS.gnn }}>
                    {(history[history.length - 1].gnn * 100).toFixed(1)}%
                  </p>
                </div>
                <div className="space-y-1">
                  <span className="text-xs" style={{ color: COLORS.trm }}>
                    TRM
                  </span>
                  <p className="text-xl font-semibold" style={{ color: COLORS.trm }}>
                    {(history[history.length - 1].trm * 100).toFixed(1)}%
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default WeightHistoryChart;
