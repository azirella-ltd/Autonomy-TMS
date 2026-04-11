/**
 * Agent Weight Manager Component
 *
 * Phase 4: Multi-Agent Orchestration - Weight Management
 * Allows manual configuration and monitoring of agent consensus weights.
 *
 * Features:
 * - Manual weight adjustment with sliders
 * - Real-time normalization (sum to 1.0)
 * - Visual weight distribution chart
 * - Enable/disable adaptive learning
 * - Learning method selection
 * - Performance metrics display
 *
 * Props:
 * - scenarioId: Scenario ID
 * - onWeightsChange: Callback when weights are updated
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Chip,
  Select,
  SelectOption,
  Slider,
  Input,
  Label,
  IconButton,
  Progress,
} from '../common';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../ui/tooltip';
import {
  SlidersHorizontal,
  Save,
  RefreshCw,
  Sparkles,
  Settings2,
  Info,
  TrendingUp,
} from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip as RechartsTooltip } from 'recharts';
import { api } from '../../services/api';
import { cn } from '@azirella-ltd/autonomy-frontend';

const COLORS = {
  llm: '#2196f3',
  gnn: '#4caf50',
  trm: '#ff9800',
};

const AGENT_NAMES = {
  llm: 'LLM (GPT-4)',
  gnn: 'Network Agent',
  trm: 'AI Agent',
};

const LEARNING_METHODS = [
  { value: 'ema', label: 'EMA (Exponential Moving Average)', description: 'Smooth, stable updates' },
  { value: 'ucb', label: 'UCB (Upper Confidence Bound)', description: 'Optimistic exploration' },
  { value: 'thompson', label: 'Thompson Sampling', description: 'Bayesian bandit algorithm' },
  { value: 'performance', label: 'Performance-Based', description: 'Direct performance mapping' },
  { value: 'gradient', label: 'Gradient Descent', description: 'Cost function optimization' },
];

const AgentWeightManager = ({ scenarioId, onWeightsChange }) => {
  const [weights, setWeights] = useState({ llm: 1/3, gnn: 1/3, trm: 1/3 });
  const [originalWeights, setOriginalWeights] = useState({ llm: 1/3, gnn: 1/3, trm: 1/3 });
  const [adaptiveLearning, setAdaptiveLearning] = useState(false);
  const [learningMethod, setLearningMethod] = useState('ema');
  const [learningRate, setLearningRate] = useState(0.1);
  const [explorationFactor, setExplorationFactor] = useState(1.0);
  const [confidence, setConfidence] = useState(0.0);
  const [numSamples, setNumSamples] = useState(0);
  const [performanceMetrics, setPerformanceMetrics] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    fetchCurrentWeights();
  }, [scenarioId]);

  useEffect(() => {
    // Check if weights have changed
    const changed = Object.keys(weights).some(
      agent => Math.abs(weights[agent] - originalWeights[agent]) > 0.001
    );
    setHasChanges(changed);
  }, [weights, originalWeights]);

  const fetchCurrentWeights = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.get(`/mixed-scenarios/${scenarioId}/agent-weights`);
      const data = response.data;

      setWeights(data.weights);
      setOriginalWeights(data.weights);
      setConfidence(data.confidence || 0);
      setNumSamples(data.num_samples || 0);
      setPerformanceMetrics(data.performance_metrics || {});
      setAdaptiveLearning(data.learning_method !== 'manual' && data.learning_method !== 'default');
    } catch (err) {
      console.error('Failed to fetch agent weights:', err);
      setError(err.response?.data?.detail || 'Failed to fetch agent weights');
    } finally {
      setLoading(false);
    }
  };

  const handleWeightChange = (agent, value) => {
    // Update weight
    const newWeights = { ...weights, [agent]: value / 100 };

    // Normalize to sum to 1.0
    const total = Object.values(newWeights).reduce((sum, w) => sum + w, 0);
    if (total > 0) {
      Object.keys(newWeights).forEach(key => {
        newWeights[key] = newWeights[key] / total;
      });
    }

    setWeights(newWeights);
  };

  const handleSaveWeights = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      await api.post(`/mixed-scenarios/${scenarioId}/set-agent-weights`, {
        weights: weights,
        context_type: 'scenario',
      });

      setSuccess('Agent weights saved successfully');
      setOriginalWeights(weights);
      setHasChanges(false);

      if (onWeightsChange) {
        onWeightsChange(weights);
      }
    } catch (err) {
      console.error('Failed to save agent weights:', err);
      setError(err.response?.data?.detail || 'Failed to save agent weights');
    } finally {
      setLoading(false);
    }
  };

  const handleResetWeights = () => {
    setWeights(originalWeights);
    setHasChanges(false);
  };

  const handleToggleAdaptiveLearning = async (enabled) => {
    if (enabled) {
      // Enable adaptive learning
      setLoading(true);
      setError(null);

      try {
        await api.post(`/mixed-scenarios/${scenarioId}/enable-adaptive-learning`, {
          learning_method: learningMethod,
          learning_rate: learningRate,
          exploration_factor: explorationFactor,
        });

        setAdaptiveLearning(true);
        setSuccess(`Adaptive learning enabled with ${learningMethod} method`);
      } catch (err) {
        console.error('Failed to enable adaptive learning:', err);
        setError(err.response?.data?.detail || 'Failed to enable adaptive learning');
      } finally {
        setLoading(false);
      }
    } else {
      setAdaptiveLearning(false);
    }
  };

  // Prepare data for pie chart
  const chartData = Object.entries(weights).map(([agent, weight]) => ({
    name: AGENT_NAMES[agent],
    value: weight,
    color: COLORS[agent],
  }));

  return (
    <TooltipProvider>
      <Card className="mb-4">
        <CardContent className="pt-6">
          <div className="flex flex-col gap-6">
            {/* Header */}
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-semibold">Agent Weight Configuration</h3>
              <div className="flex gap-2">
                {confidence > 0 && (
                  <Chip
                    variant={confidence > 0.7 ? 'success' : confidence > 0.4 ? 'warning' : 'secondary'}
                    size="sm"
                    icon={<TrendingUp className="h-3 w-3" />}
                  >
                    Confidence: {(confidence * 100).toFixed(0)}%
                  </Chip>
                )}
                {numSamples > 0 && (
                  <Chip variant="outline" size="sm">
                    {numSamples} samples
                  </Chip>
                )}
              </div>
            </div>

            {/* Error/Success Alerts */}
            {error && (
              <Alert variant="error" onClose={() => setError(null)}>
                {error}
              </Alert>
            )}
            {success && (
              <Alert variant="success" onClose={() => setSuccess(null)}>
                {success}
              </Alert>
            )}

            {/* Adaptive Learning Toggle */}
            <div className="p-4 bg-muted/50 rounded-lg">
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-3">
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={adaptiveLearning}
                      onChange={(e) => handleToggleAdaptiveLearning(e.target.checked)}
                      disabled={loading}
                      className="sr-only peer"
                    />
                    <div className={cn(
                      "w-11 h-6 bg-muted rounded-full peer",
                      "peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-ring peer-focus:ring-offset-2",
                      "peer-checked:after:translate-x-full peer-checked:bg-primary",
                      "after:content-[''] after:absolute after:top-[2px] after:left-[2px]",
                      "after:bg-background after:rounded-full after:h-5 after:w-5 after:transition-all",
                      "peer-disabled:opacity-50 peer-disabled:cursor-not-allowed"
                    )} />
                  </label>
                  <div className="flex items-center gap-2">
                    {adaptiveLearning ? (
                      <Sparkles className="h-4 w-4 text-primary" />
                    ) : (
                      <Settings2 className="h-4 w-4 text-muted-foreground" />
                    )}
                    <span className="text-sm font-medium">
                      {adaptiveLearning ? 'Adaptive Learning Enabled' : 'Manual Weight Control'}
                    </span>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <IconButton variant="ghost" size="sm" className="h-6 w-6">
                          <Info className="h-4 w-4" />
                        </IconButton>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>Adaptive learning automatically adjusts weights based on agent performance over time</p>
                      </TooltipContent>
                    </Tooltip>
                  </div>
                </div>

                {adaptiveLearning && (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div className="sm:col-span-1">
                      <Label className="text-xs mb-1.5 block">Learning Method</Label>
                      <Select
                        value={learningMethod}
                        onChange={(e) => setLearningMethod(e.target.value)}
                        size="sm"
                      >
                        {LEARNING_METHODS.map(method => (
                          <SelectOption key={method.value} value={method.value}>
                            {method.label}
                          </SelectOption>
                        ))}
                      </Select>
                      <p className="text-xs text-muted-foreground mt-1">
                        {LEARNING_METHODS.find(m => m.value === learningMethod)?.description}
                      </p>
                    </div>
                    <div>
                      <Label className="text-xs mb-1.5 block">Learning Rate</Label>
                      <Input
                        type="number"
                        value={learningRate}
                        onChange={(e) => setLearningRate(parseFloat(e.target.value))}
                        min={0.01}
                        max={1.0}
                        step={0.01}
                        className="h-9"
                      />
                    </div>
                    <div>
                      <Label className="text-xs mb-1.5 block">Exploration</Label>
                      <Input
                        type="number"
                        value={explorationFactor}
                        onChange={(e) => setExplorationFactor(parseFloat(e.target.value))}
                        min={0.1}
                        max={5.0}
                        step={0.1}
                        className="h-9"
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>

            <hr className="border-border" />

            {/* Weight Sliders */}
            {!adaptiveLearning && (
              <div>
                <h4 className="text-sm font-medium mb-4">
                  Manual Weight Configuration
                </h4>
                <div className="flex flex-col gap-6 mt-4">
                  {Object.entries(weights).map(([agent, weight]) => (
                    <div key={agent}>
                      <div className="flex justify-between mb-2">
                        <span className="text-sm font-medium">
                          {AGENT_NAMES[agent]}
                        </span>
                        <span className="text-sm text-primary font-medium">
                          {(weight * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="relative">
                        <Slider
                          value={weight * 100}
                          onChange={(value) => handleWeightChange(agent, value)}
                          min={0}
                          max={100}
                          step={1}
                          disabled={loading}
                          colorScheme={agent === 'llm' ? 'blue' : agent === 'gnn' ? 'green' : 'orange'}
                        />
                        <div className="flex justify-between text-xs text-muted-foreground mt-1">
                          <span>0%</span>
                          <span>33%</span>
                          <span>67%</span>
                          <span>100%</span>
                        </div>
                      </div>
                      {performanceMetrics[agent] && (
                        <p className="text-xs text-muted-foreground mt-1">
                          Performance: {(performanceMetrics[agent] * 100).toFixed(1)}%
                        </p>
                      )}
                    </div>
                  ))}
                </div>

                {/* Save/Reset Buttons */}
                <div className="flex justify-end gap-2 mt-4">
                  <Button
                    variant="outline"
                    leftIcon={<RefreshCw className="h-4 w-4" />}
                    onClick={handleResetWeights}
                    disabled={!hasChanges || loading}
                  >
                    Reset
                  </Button>
                  <Button
                    variant="default"
                    leftIcon={<Save className="h-4 w-4" />}
                    onClick={handleSaveWeights}
                    disabled={!hasChanges || loading}
                  >
                    Save Weights
                  </Button>
                </div>
              </div>
            )}

            <hr className="border-border" />

            {/* Pie Chart Visualization */}
            <div>
              <h4 className="text-sm font-medium mb-2">
                Weight Distribution
              </h4>
              <div className="w-full h-[250px]">
                <ResponsiveContainer>
                  <PieChart>
                    <Pie
                      data={chartData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      label={(entry) => `${(entry.value * 100).toFixed(1)}%`}
                    >
                      {chartData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Legend />
                    <RechartsTooltip
                      formatter={(value) => `${(value * 100).toFixed(1)}%`}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Performance Metrics */}
            {Object.keys(performanceMetrics).length > 0 && (
              <>
                <hr className="border-border" />
                <div>
                  <h4 className="text-sm font-medium mb-3">
                    Agent Performance
                  </h4>
                  <div className="flex flex-col gap-3">
                    {Object.entries(performanceMetrics).map(([agent, performance]) => (
                      <div key={agent}>
                        <div className="flex justify-between mb-1">
                          <span className="text-xs">{AGENT_NAMES[agent]}</span>
                          <span className="text-xs font-semibold">
                            {(performance * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-300"
                            style={{
                              width: `${performance * 100}%`,
                              backgroundColor: COLORS[agent],
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    </TooltipProvider>
  );
};

export default AgentWeightManager;
