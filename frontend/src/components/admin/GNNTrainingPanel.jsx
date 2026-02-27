import React, { useState, useEffect } from 'react';
import { ChevronDown, Play, Square, CheckCircle, XCircle, RefreshCw, Lightbulb } from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Spinner,
  Input,
  Label,
  FormField,
  NativeSelect,
  SelectOption,
  Progress,
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
  H4,
  Text,
  SmallText,
} from '../common';
import { cn } from '../../lib/utils/cn';
import {
  startGNNTraining,
  getGNNTrainingStatus,
  stopGNNTraining,
  listGNNCheckpoints,
} from '../../services/gnnApi';

const GNNTrainingPanel = ({ selectedConfig }) => {
  // Training configuration - config_name comes from parent via selectedConfig prop
  const [config, setConfig] = useState({
    num_runs: 128,
    timesteps: 64,
    window: 52,
    horizon: 1,
    epochs: 10,
    batch_size: 16,
    learning_rate: 0.0001,
    device: 'cuda',
    agent_strategy: 'naive',
    // Advanced settings
    hidden_dims: [256, 128, 64],
    num_gat_layers: 3,
    gat_heads: 8,
    tcn_kernel_size: 3,
    dropout: 0.3,
    weight_decay: 0.00001,
  });

  // Training state
  const [trainingStatus, setTrainingStatus] = useState(null);
  const [isTraining, setIsTraining] = useState(false);
  const [trainingHistory, setTrainingHistory] = useState([]);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  // Config training status for selected config
  const [configStatus, setConfigStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);

  // Poll training status
  useEffect(() => {
    let intervalId;
    if (isTraining) {
      intervalId = setInterval(async () => {
        try {
          const status = await getGNNTrainingStatus();
          setTrainingStatus(status);

          if (status.status === 'completed') {
            setIsTraining(false);
            setSuccess('Training completed successfully!');
            clearInterval(intervalId);
          } else if (status.status === 'failed') {
            setIsTraining(false);
            setError(`Training failed: ${status.error || 'Unknown error'}`);
            clearInterval(intervalId);
          }

          // Update training history
          if (status.train_loss && status.val_loss) {
            setTrainingHistory(prev => {
              const newEntry = {
                epoch: status.epoch,
                train_loss: status.train_loss,
                val_loss: status.val_loss,
                mae: status.mae,
                rmse: status.rmse,
              };
              // Avoid duplicates
              const exists = prev.find(entry => entry.epoch === status.epoch);
              if (!exists) {
                return [...prev, newEntry];
              }
              return prev;
            });
          }
        } catch (err) {
          console.error('Failed to fetch training status:', err);
        }
      }, 2000); // Poll every 2 seconds
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [isTraining]);

  // Load checkpoint status for selected config
  const loadConfigStatus = async () => {
    if (!selectedConfig) {
      setConfigStatus(null);
      setStatusLoading(false);
      return;
    }

    setStatusLoading(true);
    try {
      const response = await listGNNCheckpoints('./checkpoints');
      const checkpoints = response?.checkpoints || [];

      // Normalize config name to match checkpoint naming (e.g., "My Config" -> "my_config")
      const normalized = selectedConfig.toLowerCase().replace(/[\s-]+/g, '_');

      // Find checkpoints that match the selected config
      const matchingCheckpoints = checkpoints.filter(cp =>
        cp.config_name?.toLowerCase().replace(/[\s-]+/g, '_') === normalized
      );

      setConfigStatus({
        trained: matchingCheckpoints.length > 0,
        checkpoints: matchingCheckpoints,
        latestCheckpoint: matchingCheckpoints[0] || null,
      });
    } catch (err) {
      console.error('Failed to load config status:', err);
      setConfigStatus(null);
    } finally {
      setStatusLoading(false);
    }
  };

  // Load config status when selectedConfig changes
  useEffect(() => {
    loadConfigStatus();
  }, [selectedConfig]);

  // Refresh status after training completes
  useEffect(() => {
    if (trainingStatus?.status === 'completed') {
      loadConfigStatus();
    }
  }, [trainingStatus?.status]);

  const handleConfigChange = (field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
  };

  const handleArrayChange = (field, value) => {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) {
        setConfig(prev => ({ ...prev, [field]: parsed }));
      }
    } catch (err) {
      console.error('Invalid array format:', err);
    }
  };

  const handleStartTraining = async () => {
    if (!selectedConfig) {
      setError('Please select a supply chain configuration from the dropdown above.');
      return;
    }

    try {
      setError(null);
      setSuccess(null);
      setTrainingHistory([]);

      // Include selectedConfig in the training request
      const trainingConfig = {
        ...config,
        config_name: selectedConfig,
      };

      const response = await startGNNTraining(trainingConfig);
      setTrainingStatus(response);
      setIsTraining(true);
      setSuccess(`Training started for "${selectedConfig}"`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start training');
    }
  };

  const handleStopTraining = async () => {
    try {
      await stopGNNTraining();
      setIsTraining(false);
      setSuccess('Training stopped');
    } catch (err) {
      setError('Failed to stop training');
    }
  };

  const agentStrategies = [
    { value: 'naive', label: 'Naive (Mirror Demand)' },
    { value: 'pid_heuristic', label: 'PID Heuristic' },
    { value: 'conservative', label: 'Conservative' },
    { value: 'bullwhip', label: 'Bullwhip' },
  ];

  return (
    <div className="p-6">
      <H4 className="mb-2">GNN Model Training</H4>
      <Text className="text-muted-foreground mb-4">
        Train Graph Neural Network using SimPy-based supply chain simulations
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

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Configuration Panel */}
        <Card>
          <CardContent className="pt-6">
            <Text className="text-lg font-semibold mb-4">Training Configuration</Text>

            {/* Supply Chain Config - selected from parent dashboard */}
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

            {/* Agent Strategy */}
            <FormField label="Agent Strategy (for data generation)" className="mb-4">
              <NativeSelect
                value={config.agent_strategy}
                onChange={(e) => handleConfigChange('agent_strategy', e.target.value)}
                disabled={isTraining}
              >
                {agentStrategies.map(strategy => (
                  <SelectOption key={strategy.value} value={strategy.value}>
                    {strategy.label}
                  </SelectOption>
                ))}
              </NativeSelect>
            </FormField>

            {/* Dataset Parameters */}
            <FormField
              label="Number of Simulation Runs"
              helperText="Number of supply chain simulations (default: 128)"
              className="mb-4"
            >
              <Input
                type="number"
                value={config.num_runs}
                onChange={(e) => handleConfigChange('num_runs', parseInt(e.target.value))}
                disabled={isTraining}
              />
            </FormField>

            <FormField
              label="Timesteps per Run"
              helperText="Scenario length in periods (default: 64)"
              className="mb-4"
            >
              <Input
                type="number"
                value={config.timesteps}
                onChange={(e) => handleConfigChange('timesteps', parseInt(e.target.value))}
                disabled={isTraining}
              />
            </FormField>

            <FormField
              label="History Window"
              helperText="Past timesteps to include (default: 52)"
              className="mb-4"
            >
              <Input
                type="number"
                value={config.window}
                onChange={(e) => handleConfigChange('window', parseInt(e.target.value))}
                disabled={isTraining}
              />
            </FormField>

            <FormField
              label="Forecast Horizon"
              helperText="Future steps to predict (default: 1)"
              className="mb-4"
            >
              <Input
                type="number"
                value={config.horizon}
                onChange={(e) => handleConfigChange('horizon', parseInt(e.target.value))}
                disabled={isTraining}
              />
            </FormField>

            {/* Training Parameters */}
            <FormField
              label="Training Epochs"
              helperText="Number of training epochs (default: 10)"
              className="mb-4"
            >
              <Input
                type="number"
                value={config.epochs}
                onChange={(e) => handleConfigChange('epochs', parseInt(e.target.value))}
                disabled={isTraining}
              />
            </FormField>

            <FormField
              label="Batch Size"
              helperText="Graph batching size (default: 16)"
              className="mb-4"
            >
              <Input
                type="number"
                value={config.batch_size}
                onChange={(e) => handleConfigChange('batch_size', parseInt(e.target.value))}
                disabled={isTraining}
              />
            </FormField>

            <FormField
              label="Learning Rate"
              helperText="Adam optimizer learning rate (default: 0.0001)"
              className="mb-4"
            >
              <Input
                type="number"
                value={config.learning_rate}
                onChange={(e) => handleConfigChange('learning_rate', parseFloat(e.target.value))}
                disabled={isTraining}
                step="0.0001"
              />
            </FormField>

            <FormField label="Device" className="mb-4">
              <NativeSelect
                value={config.device}
                onChange={(e) => handleConfigChange('device', e.target.value)}
                disabled={isTraining}
              >
                <SelectOption value="cuda">GPU (CUDA)</SelectOption>
                <SelectOption value="cpu">CPU</SelectOption>
              </NativeSelect>
            </FormField>

            {/* Advanced Settings - Collapsible */}
            <div className="border rounded-md mb-4">
              <button
                type="button"
                onClick={() => setAdvancedOpen(!advancedOpen)}
                className={cn(
                  'flex items-center justify-between w-full px-4 py-3 text-left',
                  'hover:bg-muted/50 transition-colors rounded-md'
                )}
              >
                <Text className="font-medium">Advanced Settings</Text>
                <ChevronDown
                  className={cn(
                    'h-4 w-4 transition-transform',
                    advancedOpen && 'rotate-180'
                  )}
                />
              </button>
              {advancedOpen && (
                <div className="px-4 pb-4 space-y-4">
                  <FormField
                    label="Hidden Dimensions (JSON array)"
                    helperText="e.g., [256, 128, 64]"
                  >
                    <Input
                      value={JSON.stringify(config.hidden_dims)}
                      onChange={(e) => handleArrayChange('hidden_dims', e.target.value)}
                      disabled={isTraining}
                    />
                  </FormField>

                  <FormField
                    label="GAT Layers"
                    helperText="Number of Graph Attention layers (default: 3)"
                  >
                    <Input
                      type="number"
                      value={config.num_gat_layers}
                      onChange={(e) => handleConfigChange('num_gat_layers', parseInt(e.target.value))}
                      disabled={isTraining}
                    />
                  </FormField>

                  <FormField
                    label="GAT Attention Heads"
                    helperText="Multi-head attention (default: 8)"
                  >
                    <Input
                      type="number"
                      value={config.gat_heads}
                      onChange={(e) => handleConfigChange('gat_heads', parseInt(e.target.value))}
                      disabled={isTraining}
                    />
                  </FormField>

                  <FormField
                    label="TCN Kernel Size"
                    helperText="Temporal convolution kernel (default: 3)"
                  >
                    <Input
                      type="number"
                      value={config.tcn_kernel_size}
                      onChange={(e) => handleConfigChange('tcn_kernel_size', parseInt(e.target.value))}
                      disabled={isTraining}
                    />
                  </FormField>

                  <FormField
                    label="Dropout Rate"
                    helperText="Regularization dropout (default: 0.3)"
                  >
                    <Input
                      type="number"
                      value={config.dropout}
                      onChange={(e) => handleConfigChange('dropout', parseFloat(e.target.value))}
                      disabled={isTraining}
                      step="0.1"
                      min="0"
                      max="1"
                    />
                  </FormField>

                  <FormField
                    label="Weight Decay"
                    helperText="L2 regularization (default: 0.00001)"
                  >
                    <Input
                      type="number"
                      value={config.weight_decay}
                      onChange={(e) => handleConfigChange('weight_decay', parseFloat(e.target.value))}
                      disabled={isTraining}
                      step="0.00001"
                    />
                  </FormField>
                </div>
              )}
            </div>

            {/* Training Controls */}
            <div className="flex gap-2 mt-6">
              <Button
                onClick={handleStartTraining}
                disabled={isTraining}
                fullWidth
                leftIcon={isTraining ? <Spinner size="sm" className="text-primary-foreground" /> : <Play className="h-4 w-4" />}
              >
                {isTraining ? 'Training...' : 'Start Training'}
              </Button>
              {isTraining && (
                <Button
                  variant="outline"
                  className="border-destructive text-destructive hover:bg-destructive/10"
                  onClick={handleStopTraining}
                  leftIcon={<Square className="h-4 w-4" />}
                >
                  Stop
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Status & Progress Panel */}
        <div className="space-y-6">
          {/* Quick Start Guide */}
          <Card className="bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
            <CardContent className="pt-6">
              <div className="flex items-center gap-2 mb-3">
                <Lightbulb className="h-5 w-5 text-blue-600" />
                <Text className="text-lg font-semibold">Quick Start Guide</Text>
              </div>
              <ol className="list-decimal list-inside space-y-1.5 text-sm">
                <li><strong>Select Configuration</strong>: Choose the supply chain network to train on</li>
                <li><strong>Select Strategy</strong>: Naive is best for generating diverse training data</li>
                <li><strong>Configure Simulation</strong>: Set runs (128) and timesteps (64) for adequate data</li>
                <li><strong>Start Training</strong>: Model generates data, then trains the GNN</li>
                <li><strong>Monitor Loss</strong>: Watch train/val loss decrease over epochs</li>
                <li><strong>Use Model</strong>: Trained GNN can make predictions for all nodes simultaneously</li>
              </ol>
              <p className="text-xs text-muted-foreground mt-3">
                <strong>Architecture:</strong> GAT (graph attention) + TCN (temporal convolution) for network-wide predictions
              </p>
            </CardContent>
          </Card>

          {/* Current Training Progress */}
          <Card>
            <CardContent className="pt-6">
              <Text className="text-lg font-semibold mb-4">Current Training</Text>

              {trainingStatus ? (
                <div className="space-y-2">
                  <SmallText>
                    <strong>Status:</strong> {trainingStatus.status}
                  </SmallText>
                  <SmallText>
                    <strong>Epoch:</strong> {trainingStatus.epoch} / {trainingStatus.total_epochs}
                  </SmallText>
                  <Progress
                    value={(trainingStatus.epoch / trainingStatus.total_epochs) * 100}
                    className="my-4"
                  />
                  {trainingStatus.train_loss && (
                    <SmallText>
                      <strong>Train Loss:</strong> {trainingStatus.train_loss.toFixed(4)}
                    </SmallText>
                  )}
                  {trainingStatus.val_loss && (
                    <SmallText>
                      <strong>Val Loss:</strong> {trainingStatus.val_loss.toFixed(4)}
                    </SmallText>
                  )}
                  {trainingStatus.mae && (
                    <SmallText>
                      <strong>MAE:</strong> {trainingStatus.mae.toFixed(4)}
                    </SmallText>
                  )}
                  {trainingStatus.rmse && (
                    <SmallText>
                      <strong>RMSE:</strong> {trainingStatus.rmse.toFixed(4)}
                    </SmallText>
                  )}
                  {trainingStatus.eta && (
                    <SmallText>
                      <strong>ETA:</strong> {trainingStatus.eta}
                    </SmallText>
                  )}
                </div>
              ) : (
                <Text className="text-muted-foreground">
                  No training in progress
                </Text>
              )}
            </CardContent>
          </Card>

          {/* Training Status for Selected Configuration */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between mb-4">
                <Text className="text-lg font-semibold">Configuration Status</Text>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={loadConfigStatus}
                  disabled={statusLoading}
                  leftIcon={<RefreshCw className={cn("h-4 w-4", statusLoading && "animate-spin")} />}
                >
                  Refresh
                </Button>
              </div>
              <div className="border rounded-md bg-muted/30">
                {statusLoading ? (
                  <div className="flex justify-center py-4">
                    <Spinner size="sm" />
                  </div>
                ) : !selectedConfig ? (
                  <div className="px-4 py-3 text-sm text-muted-foreground">
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
                            {configStatus.latestCheckpoint.epochs && ` (${configStatus.latestCheckpoint.epochs} epochs)`}
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

          {/* Training Loss Chart */}
          {trainingHistory.length > 0 && (
            <Card>
              <CardContent className="pt-6">
                <Text className="text-lg font-semibold mb-4">Training Progress</Text>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={trainingHistory}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="epoch" label={{ value: 'Epoch', position: 'insideBottom', offset: -5 }} />
                    <YAxis label={{ value: 'Loss', angle: -90, position: 'insideLeft' }} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="train_loss" stroke="#8884d8" name="Train Loss" />
                    <Line type="monotone" dataKey="val_loss" stroke="#82ca9d" name="Val Loss" />
                  </LineChart>
                </ResponsiveContainer>

                {/* Metrics Chart */}
                {trainingHistory.some(h => h.mae) && (
                  <ResponsiveContainer width="100%" height={300} style={{ marginTop: 20 }}>
                    <LineChart data={trainingHistory}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="epoch" label={{ value: 'Epoch', position: 'insideBottom', offset: -5 }} />
                      <YAxis label={{ value: 'Error', angle: -90, position: 'insideLeft' }} />
                      <Tooltip />
                      <Legend />
                      <Line type="monotone" dataKey="mae" stroke="#ff7300" name="MAE" />
                      <Line type="monotone" dataKey="rmse" stroke="#387908" name="RMSE" />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          )}
        </div>

        {/* GNN Architecture Info */}
        <div className="md:col-span-2">
          <Card>
            <CardContent className="pt-6">
              <Text className="text-lg font-semibold mb-4">GNN Architecture Overview</Text>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Component</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Parameters</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell>Node Embedding</TableCell>
                    <TableCell>Encode 12-dimensional node features</TableCell>
                    <TableCell>12 -&gt; 256 dimensions</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>GAT Layers</TableCell>
                    <TableCell>Graph Attention Networks with multi-head attention</TableCell>
                    <TableCell>3 layers x 8 heads</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Message Passing</TableCell>
                    <TableCell>Aggregate neighbor features via attention</TableCell>
                    <TableCell>3 periods</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Temporal CNN</TableCell>
                    <TableCell>Process time series with convolutions</TableCell>
                    <TableCell>4 layers, kernel=3</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Output Layer</TableCell>
                    <TableCell>Predict demand + optimal orders per node</TableCell>
                    <TableCell>256 -&gt; 2 outputs</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-semibold">Total Parameters</TableCell>
                    <TableCell className="font-semibold">Complete model</TableCell>
                    <TableCell className="font-semibold">~128 million</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default GNNTrainingPanel;
