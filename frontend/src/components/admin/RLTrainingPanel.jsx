import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Spinner,
  NativeSelect,
  SelectOption,
  Slider,
  Input,
  Label,
  FormField,
  Progress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  H5,
  Text,
} from '../common';
import {
  Play,
  Square,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Trash2,
  BarChart3,
  Download,
  CheckCircle,
  XCircle,
  Lightbulb,
} from 'lucide-react';
import { cn } from '@azirella-ltd/autonomy-frontend';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as ChartTooltip, Legend, ResponsiveContainer } from 'recharts';
import rlApi from '../../services/rlApi';

// RL algorithms available - PPO is recommended default
const RL_ALGORITHMS = [
  { id: 'PPO', name: 'PPO', description: 'Proximal Policy Optimization (recommended)' },
  { id: 'SAC', name: 'SAC', description: 'Soft Actor-Critic (off-policy)' },
  { id: 'A2C', name: 'A2C', description: 'Advantage Actor-Critic (fast)' }
];

// Simple collapsible section component
const CollapsibleSection = ({ title, children, defaultOpen = false }) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border border-input rounded-md">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between px-4 py-3 text-left font-medium hover:bg-muted/50 transition-colors"
      >
        <span>{title}</span>
        {isOpen ? (
          <ChevronUp className="h-4 w-4" />
        ) : (
          <ChevronDown className="h-4 w-4" />
        )}
      </button>
      {isOpen && (
        <div className="border-t border-input px-4 py-4">
          {children}
        </div>
      )}
    </div>
  );
};

const RLTrainingPanel = ({ selectedConfig }) => {
  // Training config - supply_chain_config comes from parent via selectedConfig prop
  const [trainingConfig, setTrainingConfig] = useState({
    algorithm: 'PPO',  // PPO is recommended default
    total_timesteps: 100000,
    device: 'cuda',  // GPU as default
    n_envs: 4,
    learning_rate: 0.0003,
    batch_size: 64,
    ent_coef: 0.01,
    gamma: 0.99,
    max_periods: 52,
    max_order: 100,
    holding_cost: 1.0,
    backlog_cost: 2.0
  });

  const [trainingStatus, setTrainingStatus] = useState(null);
  const [checkpoints, setCheckpoints] = useState([]);
  const [loading, setLoading] = useState(false);
  const [checkpointsLoading, setCheckpointsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [statusPollInterval, setStatusPollInterval] = useState(null);
  const [metricsHistory, setMetricsHistory] = useState([]);
  const [evaluationResults, setEvaluationResults] = useState(null);
  const [configStatus, setConfigStatus] = useState({});

  // Load checkpoints when selectedConfig changes
  useEffect(() => {
    loadCheckpoints();
  }, [selectedConfig]);

  // Poll training status
  useEffect(() => {
    const pollStatus = async () => {
      try {
        const status = await rlApi.getTrainingStatus();
        setTrainingStatus(status);

        // Update metrics history for chart
        if (status.metrics && status.timesteps) {
          setMetricsHistory(prev => {
            const newHistory = [...prev];
            const existing = newHistory.find(h => h.timesteps === status.timesteps);
            if (!existing) {
              newHistory.push({
                timesteps: status.timesteps,
                mean_reward: status.metrics.mean_reward || 0,
                mean_cost: status.metrics.mean_cost || 0,
                episode_length: status.metrics.episode_length || 0
              });
            }
            return newHistory.slice(-100); // Keep last 100 data points
          });
        }

        // Stop polling if training completed or failed
        if (status.status === 'completed' || status.status === 'failed') {
          if (statusPollInterval) {
            clearInterval(statusPollInterval);
            setStatusPollInterval(null);
          }
          // Reload checkpoints
          loadCheckpoints();
        }
      } catch (err) {
        console.error('Failed to fetch training status:', err);
      }
    };

    if (statusPollInterval) {
      pollStatus(); // Poll immediately
      const interval = setInterval(pollStatus, 2000); // Then every 2 seconds
      return () => clearInterval(interval);
    }
  }, [statusPollInterval]);

  const loadCheckpoints = async () => {
    setCheckpointsLoading(true);
    try {
      const response = await rlApi.listCheckpoints('./checkpoints/rl');
      const cpList = Array.isArray(response?.checkpoints) ? response.checkpoints : [];

      // Filter checkpoints by selectedConfig
      if (selectedConfig) {
        const normalizedSelected = selectedConfig.toLowerCase().replace(/[\s-]+/g, '_');
        const filtered = cpList.filter(cp => {
          if (!cp.config) return false;
          const cpConfig = cp.config.toLowerCase().replace(/[\s-]+/g, '_');
          return cpConfig === normalizedSelected;
        });
        setCheckpoints(filtered);

        // Update config status for selected config
        setConfigStatus({
          trained: filtered.length > 0,
          checkpoints: filtered,
          latestCheckpoint: filtered[0] || null,
        });
      } else {
        setCheckpoints(cpList);
        setConfigStatus(null);
      }
    } catch (err) {
      console.error('Failed to load checkpoints:', err);
      setCheckpoints([]);
      setConfigStatus(null);
    } finally {
      setCheckpointsLoading(false);
    }
  };

  const handleConfigChange = (field, value) => {
    setTrainingConfig(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleStartTraining = async () => {
    if (!selectedConfig) {
      setError('Please select a supply chain configuration from the dropdown above.');
      return;
    }

    setError(null);
    setSuccess(null);
    setLoading(true);
    setMetricsHistory([]);

    try {
      // Include selectedConfig in the training request
      const trainingPayload = {
        ...trainingConfig,
        supply_chain_config: selectedConfig,
      };
      const status = await rlApi.startTraining(trainingPayload);
      setTrainingStatus(status);
      setSuccess(`Started ${trainingConfig.algorithm} training for "${selectedConfig}"`);

      // Start polling for status updates
      if (!statusPollInterval) {
        setStatusPollInterval(true);
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to start training');
    } finally {
      setLoading(false);
    }
  };

  const handleStopTraining = async () => {
    try {
      await rlApi.stopTraining();
      if (statusPollInterval) {
        setStatusPollInterval(null);
      }
      setSuccess('Training stopped');
    } catch (err) {
      setError('Failed to stop training');
    }
  };

  const handleLoadCheckpoint = async (checkpointPath) => {
    try {
      await rlApi.loadModel(checkpointPath, trainingConfig.device);
      setSuccess(`Loaded checkpoint: ${checkpointPath}`);
    } catch (err) {
      setError(`Failed to load checkpoint: ${err.message}`);
    }
  };

  const handleEvaluateCheckpoint = async (checkpointPath) => {
    setLoading(true);
    setError(null);
    try {
      const results = await rlApi.evaluateModel(checkpointPath, 20, trainingConfig.device);
      setEvaluationResults(results);
      setSuccess(`Evaluated checkpoint: ${checkpointPath}`);
    } catch (err) {
      setError(`Failed to evaluate checkpoint: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteCheckpoint = async (checkpointPath) => {
    if (!window.confirm(`Delete checkpoint: ${checkpointPath}?`)) {
      return;
    }

    try {
      await rlApi.deleteCheckpoint(checkpointPath);
      setSuccess(`Deleted checkpoint: ${checkpointPath}`);
      loadCheckpoints();
    } catch (err) {
      setError(`Failed to delete checkpoint: ${err.message}`);
    }
  };

  const getStatusVariant = (status) => {
    switch (status) {
      case 'training': return 'default';
      case 'completed': return 'success';
      case 'failed': return 'destructive';
      default: return 'secondary';
    }
  };

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const formatNumber = (num) => {
    if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
  };

  return (
    <div>
      <H5 className="mb-2">Reinforcement Learning Agent Training</H5>
      <Text className="text-muted-foreground mb-4">
        Train RL agents (PPO, SAC, A2C) for supply chain decision-making. Agents learn optimal ordering policies
        through trial-and-error interaction with the supply chain environment.
      </Text>

      {error && (
        <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Training Configuration - Left Column */}
        <Card>
          <CardContent className="pt-6">
            <h6 className="text-lg font-semibold mb-4">Training Configuration</h6>

            {/* Supply Chain Configuration - selected from parent dashboard */}
            <FormField label="Supply Chain Configuration" className="mb-4">
              {selectedConfig ? (
                <div className="flex items-center gap-2 py-2 px-3 bg-muted rounded-md">
                  <CheckCircle className="h-4 w-4 text-primary" />
                  <span className="font-medium">{selectedConfig}</span>
                </div>
              ) : (
                <Alert variant="warning">No supply chain configuration selected. Select one from the dropdown above.</Alert>
              )}
            </FormField>

            {/* Algorithm Dropdown - PPO default */}
            <FormField label="Algorithm" className="mb-4">
              <NativeSelect
                value={trainingConfig.algorithm}
                onChange={(e) => handleConfigChange('algorithm', e.target.value)}
                disabled={trainingStatus?.status === 'training'}
              >
                {RL_ALGORITHMS.map(algo => (
                  <SelectOption key={algo.id} value={algo.id}>
                    {algo.name} - {algo.description}
                  </SelectOption>
                ))}
              </NativeSelect>
            </FormField>

            {/* Device Dropdown - GPU default */}
            <FormField label="Device" className="mb-4">
              <NativeSelect
                value={trainingConfig.device}
                onChange={(e) => handleConfigChange('device', e.target.value)}
                disabled={trainingStatus?.status === 'training'}
              >
                <SelectOption value="cuda">GPU (CUDA)</SelectOption>
                <SelectOption value="cpu">CPU</SelectOption>
              </NativeSelect>
            </FormField>

            {/* Parallel Environments with stepper */}
            <FormField
              label="Parallel Environments"
              helperText="Number of parallel environments for data collection"
              className="mb-4"
            >
              <Input
                type="number"
                value={trainingConfig.n_envs}
                onChange={(e) => handleConfigChange('n_envs', parseInt(e.target.value) || 1)}
                disabled={trainingStatus?.status === 'training'}
                min={1}
                max={16}
                step={1}
              />
            </FormField>

            <div className="mb-4">
              <Label className="mb-2 block">
                Total Timesteps: {formatNumber(trainingConfig.total_timesteps)}
              </Label>
              <Slider
                value={trainingConfig.total_timesteps}
                onChange={(value) => handleConfigChange('total_timesteps', value)}
                disabled={trainingStatus?.status === 'training'}
                min={10000}
                max={10000000}
                step={10000}
              />
            </div>

            <CollapsibleSection title="Algorithm Hyperparameters">
              <div className="space-y-4">
                <FormField label="Learning Rate">
                  <Input
                    type="number"
                    value={trainingConfig.learning_rate}
                    onChange={(e) => handleConfigChange('learning_rate', parseFloat(e.target.value))}
                    disabled={trainingStatus?.status === 'training'}
                    step={0.0001}
                  />
                </FormField>
                <FormField label="Batch Size">
                  <Input
                    type="number"
                    value={trainingConfig.batch_size}
                    onChange={(e) => handleConfigChange('batch_size', parseInt(e.target.value))}
                    disabled={trainingStatus?.status === 'training'}
                  />
                </FormField>
                <FormField
                  label="Entropy Coefficient"
                  helperText="Encourages exploration (higher = more random)"
                >
                  <Input
                    type="number"
                    value={trainingConfig.ent_coef}
                    onChange={(e) => handleConfigChange('ent_coef', parseFloat(e.target.value))}
                    disabled={trainingStatus?.status === 'training'}
                    step={0.01}
                  />
                </FormField>
                <FormField
                  label="Gamma (Discount Factor)"
                  helperText="Future reward discount (0.99 = long-term planning)"
                >
                  <Input
                    type="number"
                    value={trainingConfig.gamma}
                    onChange={(e) => handleConfigChange('gamma', parseFloat(e.target.value))}
                    disabled={trainingStatus?.status === 'training'}
                    step={0.01}
                    min={0}
                    max={1}
                  />
                </FormField>
              </div>
            </CollapsibleSection>

            <div className="mt-4">
              <CollapsibleSection title="Environment Parameters">
                <div className="space-y-4">
                  <FormField label="Max Rounds" helperText="Maximum rounds per episode">
                    <Input
                      type="number"
                      value={trainingConfig.max_periods}
                      onChange={(e) => handleConfigChange('max_periods', parseInt(e.target.value))}
                      disabled={trainingStatus?.status === 'training'}
                    />
                  </FormField>
                  <FormField label="Max Order" helperText="Maximum order quantity">
                    <Input
                      type="number"
                      value={trainingConfig.max_order}
                      onChange={(e) => handleConfigChange('max_order', parseInt(e.target.value))}
                      disabled={trainingStatus?.status === 'training'}
                    />
                  </FormField>
                  <FormField label="Holding Cost" helperText="Cost per unit held in inventory">
                    <Input
                      type="number"
                      value={trainingConfig.holding_cost}
                      onChange={(e) => handleConfigChange('holding_cost', parseFloat(e.target.value))}
                      disabled={trainingStatus?.status === 'training'}
                      step={0.1}
                    />
                  </FormField>
                  <FormField label="Backlog Cost" helperText="Cost per unit backordered">
                    <Input
                      type="number"
                      value={trainingConfig.backlog_cost}
                      onChange={(e) => handleConfigChange('backlog_cost', parseFloat(e.target.value))}
                      disabled={trainingStatus?.status === 'training'}
                      step={0.1}
                    />
                  </FormField>
                </div>
              </CollapsibleSection>
            </div>

            <div className="mt-6 flex gap-2">
              {trainingStatus?.status === 'training' ? (
                <Button
                  variant="outline"
                  className="flex-1 border-destructive text-destructive hover:bg-destructive hover:text-destructive-foreground"
                  leftIcon={<Square className="h-4 w-4" />}
                  onClick={handleStopTraining}
                >
                  Stop Training
                </Button>
              ) : (
                <Button
                  leftIcon={<Play className="h-4 w-4" />}
                  onClick={handleStartTraining}
                  disabled={loading}
                  fullWidth
                >
                  Start Training
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Right Column - Quick Start Guide, Training Progress, Current Status */}
        <div className="space-y-6">
          {/* Quick Start Guide - Top of Right Side */}
          <Card className="bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
            <CardContent className="pt-6">
              <div className="flex items-center gap-2 mb-3">
                <Lightbulb className="h-5 w-5 text-blue-600" />
                <h6 className="text-lg font-semibold">Quick Start Guide</h6>
              </div>
              <ol className="list-decimal list-inside space-y-1.5 text-sm">
                <li><strong>Select Configuration</strong>: Choose the supply chain network to train on</li>
                <li><strong>Select Algorithm</strong>: PPO (recommended), SAC (data-efficient), or A2C (fast)</li>
                <li><strong>Configure Training</strong>: Set timesteps (1M recommended for good performance)</li>
                <li><strong>Start Training</strong>: Progress updates every 2 seconds</li>
                <li><strong>Monitor</strong>: Watch mean reward increase and mean cost decrease</li>
                <li><strong>Evaluate</strong>: Test the trained model on 20 episodes</li>
              </ol>
              <p className="text-xs text-muted-foreground mt-3">
                <strong>Estimated Training Time:</strong> ~30 min (GPU) or ~90 min (CPU) for 1M timesteps
              </p>
            </CardContent>
          </Card>

          {/* Training Status for Selected Configuration */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between mb-3">
                <h6 className="text-lg font-semibold">Configuration Status</h6>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={loadCheckpoints}
                  disabled={checkpointsLoading}
                  className="h-7 px-2"
                  leftIcon={<RefreshCw className={cn("h-3 w-3", checkpointsLoading && "animate-spin")} />}
                >
                  Refresh
                </Button>
              </div>
              <div className="border rounded-md bg-muted/30">
                {checkpointsLoading ? (
                  <div className="flex justify-center py-4">
                    <Progress value={50} className="w-24" />
                  </div>
                ) : !selectedConfig ? (
                  <div className="px-3 py-4 text-sm text-muted-foreground text-center">
                    Select a supply chain configuration to view training status.
                  </div>
                ) : (
                  <div className="px-4 py-3">
                    <div className="flex items-center justify-between text-sm mb-2">
                      <span className="font-medium">{selectedConfig}</span>
                      {configStatus?.trained ? (
                        <CheckCircle className="h-4 w-4 text-green-500" />
                      ) : (
                        <XCircle className="h-4 w-4 text-muted-foreground/30" />
                      )}
                    </div>
                    {configStatus?.trained ? (
                      <div className="text-xs text-muted-foreground">
                        <p>Model trained: {configStatus.checkpoints?.length || 0} checkpoint(s) available</p>
                        {configStatus.latestCheckpoint && (
                          <p className="mt-1">
                            Latest: {configStatus.latestCheckpoint.name}
                            {configStatus.latestCheckpoint.algorithm && ` (${configStatus.latestCheckpoint.algorithm})`}
                          </p>
                        )}
                      </div>
                    ) : (
                      <div className="text-xs text-muted-foreground">
                        No trained model found. Start training to create a checkpoint.
                      </div>
                    )}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Current Training Status */}
          <Card>
            <CardContent className="pt-6">
              <h6 className="text-lg font-semibold mb-4">Current Training Status</h6>

              {trainingStatus ? (
                <div>
                  <div className="mb-4">
                    <Badge variant={getStatusVariant(trainingStatus.status)} className="mb-2">
                      {trainingStatus.status}
                    </Badge>
                    <Text className="text-sm">
                      <strong>Algorithm:</strong> {trainingStatus.algorithm || 'N/A'}
                    </Text>
                    <Text className="text-sm">
                      <strong>Config:</strong> {trainingStatus.config || 'N/A'}
                    </Text>
                    <Text className="text-sm">
                      <strong>Timesteps:</strong> {formatNumber(trainingStatus.timesteps || 0)} / {formatNumber(trainingStatus.total_timesteps || 0)}
                    </Text>
                    {trainingStatus.metrics && (
                      <>
                        <Text className="text-sm">
                          <strong>Mean Reward:</strong> {trainingStatus.metrics.mean_reward?.toFixed(2) || 'N/A'}
                        </Text>
                        <Text className="text-sm">
                          <strong>Mean Cost:</strong> {trainingStatus.metrics.mean_cost?.toFixed(2) || 'N/A'}
                        </Text>
                        <Text className="text-sm">
                          <strong>Episode Length:</strong> {trainingStatus.metrics.episode_length?.toFixed(1) || 'N/A'}
                        </Text>
                      </>
                    )}
                  </div>

                  {trainingStatus.status === 'training' && trainingStatus.total_timesteps > 0 && (
                    <Progress
                      value={(trainingStatus.timesteps / trainingStatus.total_timesteps) * 100}
                      className="mb-4"
                    />
                  )}

                  {metricsHistory.length > 0 && (
                    <div className="mt-6">
                      <Text className="text-sm font-medium mb-2">Training Metrics</Text>
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={metricsHistory}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis
                            dataKey="timesteps"
                            tickFormatter={formatNumber}
                          />
                          <YAxis />
                          <ChartTooltip />
                          <Legend />
                          <Line type="monotone" dataKey="mean_reward" stroke="#8884d8" name="Mean Reward" />
                          <Line type="monotone" dataKey="mean_cost" stroke="#ff7300" name="Mean Cost" />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              ) : (
                <Alert variant="info">
                  No training in progress. Configure parameters and click Start Training.
                </Alert>
              )}
            </CardContent>
          </Card>

          {/* Evaluation Results */}
          {evaluationResults && (
            <Card>
              <CardContent className="pt-6">
                <h6 className="text-lg font-semibold mb-4">Evaluation Results</h6>
                <Text className="text-sm">
                  <strong>Episodes:</strong> {evaluationResults.n_episodes}
                </Text>
                <Text className="text-sm">
                  <strong>Mean Reward:</strong> {evaluationResults.mean_reward?.toFixed(2)} +/- {evaluationResults.std_reward?.toFixed(2)}
                </Text>
                <Text className="text-sm">
                  <strong>Mean Episode Length:</strong> {evaluationResults.mean_episode_length?.toFixed(1)}
                </Text>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Checkpoint Management */}
        <div className="lg:col-span-2">
          <Card>
            <CardContent className="pt-6">
              <div className="flex justify-between items-center mb-4">
                <h6 className="text-lg font-semibold">Saved Checkpoints</h6>
                <Button
                  variant="ghost"
                  size="sm"
                  leftIcon={<RefreshCw className="h-4 w-4" />}
                  onClick={loadCheckpoints}
                >
                  Refresh
                </Button>
              </div>

              {checkpointsLoading ? (
                <div className="flex justify-center p-6">
                  <Progress value={100} className="w-full" />
                </div>
              ) : checkpoints.length === 0 ? (
                <Alert variant="info">
                  No checkpoints found. Start training to generate checkpoints.
                </Alert>
              ) : (
                <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell className="font-semibold">Checkpoint Name</TableCell>
                        <TableCell className="font-semibold">Algorithm</TableCell>
                        <TableCell className="font-semibold">Config</TableCell>
                        <TableCell className="font-semibold text-right">Size</TableCell>
                        <TableCell className="font-semibold">Date</TableCell>
                        <TableCell className="font-semibold text-center">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {checkpoints.map((checkpoint, index) => (
                        <TableRow key={index}>
                          <TableCell>
                            <span className="font-mono text-sm">
                              {checkpoint.name}
                            </span>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">
                              {checkpoint.algorithm || 'Unknown'}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Text className="text-sm">
                              {checkpoint.config || 'N/A'}
                            </Text>
                          </TableCell>
                          <TableCell className="text-right">
                            <Text className="text-sm">
                              {formatBytes(checkpoint.size || 0)}
                            </Text>
                          </TableCell>
                          <TableCell>
                            <Text className="text-sm">
                              {checkpoint.modified ? new Date(checkpoint.modified).toLocaleString() : 'N/A'}
                            </Text>
                          </TableCell>
                          <TableCell>
                            <div className="flex justify-center gap-1">
                              <Button
                                size="sm"
                                variant="ghost"
                                leftIcon={<Download className="h-4 w-4" />}
                                onClick={() => handleLoadCheckpoint(checkpoint.path)}
                                title="Load Model"
                              >
                                Load
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                leftIcon={<BarChart3 className="h-4 w-4" />}
                                onClick={() => handleEvaluateCheckpoint(checkpoint.path)}
                                title="Evaluate Model"
                              >
                                Eval
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="text-destructive hover:text-destructive"
                                leftIcon={<Trash2 className="h-4 w-4" />}
                                onClick={() => handleDeleteCheckpoint(checkpoint.path)}
                                title="Delete Checkpoint"
                              >
                                Delete
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </CardContent>
          </Card>
        </div>

        {/* RL Algorithms Info */}
        <div className="lg:col-span-2">
          <Card>
            <CardContent className="pt-6">
              <h6 className="text-lg font-semibold mb-4">RL Algorithms Comparison</h6>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell className="font-semibold">Algorithm</TableCell>
                      <TableCell className="font-semibold">Type</TableCell>
                      <TableCell className="font-semibold">Action Space</TableCell>
                      <TableCell className="font-semibold">Characteristics</TableCell>
                      <TableCell className="font-semibold">Best For</TableCell>
                      <TableCell className="font-semibold">Training Speed</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    <TableRow>
                      <TableCell>PPO</TableCell>
                      <TableCell>On-policy</TableCell>
                      <TableCell>Discrete/Continuous</TableCell>
                      <TableCell>Stable, clipped objective, easy to tune</TableCell>
                      <TableCell>General-purpose, default choice</TableCell>
                      <TableCell>Medium</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>SAC</TableCell>
                      <TableCell>Off-policy</TableCell>
                      <TableCell>Continuous</TableCell>
                      <TableCell>Sample-efficient, entropy regularization</TableCell>
                      <TableCell>Continuous control, data efficiency</TableCell>
                      <TableCell>Fast</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>A2C</TableCell>
                      <TableCell>On-policy</TableCell>
                      <TableCell>Discrete/Continuous</TableCell>
                      <TableCell>Synchronous, advantage estimation</TableCell>
                      <TableCell>Fast prototyping, simpler problems</TableCell>
                      <TableCell>Very Fast</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default RLTrainingPanel;
