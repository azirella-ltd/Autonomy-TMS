import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  NativeSelect,
  SelectOption,
  Alert,
  Badge,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableContainer,
  Input,
  Label,
  FormField,
  Progress,
  H5,
  H6,
  Text,
  SmallText,
} from '../common';
import {
  Play,
  RefreshCw,
  Lightbulb,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import trmApi from '../../services/trmApi';
import { getSupplyChainConfigs } from '../../services/supplyChainConfigService';

const TRMTrainingPanel = () => {
  // Supply chain configs loaded from API (filtered by user's group)
  const [supplyChainConfigs, setSupplyChainConfigs] = useState([]);
  const [configsLoading, setConfigsLoading] = useState(true);
  const [configsError, setConfigsError] = useState(null);

  const [selectedConfig, setSelectedConfig] = useState('');
  const [trainingConfig, setTrainingConfig] = useState({
    supply_chain_config: '',
    phase: 'all',  // String, not number (backend expects str)
    epochs: 10,
    device: 'cuda',
    batch_size: 32,
    learning_rate: 0.0001,
    num_samples: 10000,
    d_model: 512,
    nhead: 8,
    num_layers: 2,
    refinement_steps: 3,
    checkpoint_dir: './checkpoints',
    resume_checkpoint: null
  });

  // Load supply chain configs for user's group on mount
  useEffect(() => {
    const loadConfigs = async () => {
      setConfigsLoading(true);
      setConfigsError(null);
      try {
        const configs = await getSupplyChainConfigs();
        const formattedConfigs = configs.map(cfg => ({
          id: cfg.name.toLowerCase().replace(/\s+/g, '_'),
          dbId: cfg.id,
          name: cfg.name,
          description: cfg.description || ''
        }));
        setSupplyChainConfigs(formattedConfigs);

        if (formattedConfigs.length > 0) {
          setSelectedConfig(formattedConfigs[0].id);
          setTrainingConfig(prev => ({
            ...prev,
            supply_chain_config: formattedConfigs[0].id
          }));
        }
      } catch (err) {
        console.error('Failed to load supply chain configs:', err);
        setConfigsError('Failed to load supply chain configurations');
      } finally {
        setConfigsLoading(false);
      }
    };
    loadConfigs();
  }, []);

  const [trainingStatus, setTrainingStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [statusPollInterval, setStatusPollInterval] = useState(null);
  const [lossHistory, setLossHistory] = useState([]);

  // Poll training status
  useEffect(() => {
    const pollStatus = async () => {
      try {
        const status = await trmApi.getTrainingStatus();
        setTrainingStatus(status);

        // Update loss history for chart
        if (status.train_loss !== null && status.val_loss !== null && status.epoch) {
          setLossHistory(prev => {
            const newHistory = [...prev];
            const existing = newHistory.find(h => h.epoch === status.epoch);
            if (!existing) {
              newHistory.push({
                epoch: status.epoch,
                train_loss: status.train_loss,
                val_loss: status.val_loss
              });
            }
            return newHistory.slice(-50); // Keep last 50 epochs
          });
        }

        // Stop polling if training completed or failed
        if (status.status === 'completed' || status.status === 'failed') {
          if (statusPollInterval) {
            clearInterval(statusPollInterval);
            setStatusPollInterval(null);
          }
        }
      } catch (err) {
        console.error('Failed to fetch training status:', err);
      }
    };

    if (statusPollInterval) {
      return () => clearInterval(statusPollInterval);
    }

    // Initial fetch
    pollStatus();
  }, [statusPollInterval]);

  const handleConfigChange = (field, value) => {
    setTrainingConfig(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleStartTraining = async () => {
    setError(null);
    setLoading(true);
    setLossHistory([]);

    try {
      const status = await trmApi.startTraining(trainingConfig);
      setTrainingStatus(status);

      // Start polling for status updates
      const interval = setInterval(async () => {
        try {
          const updatedStatus = await trmApi.getTrainingStatus();
          setTrainingStatus(updatedStatus);
        } catch (err) {
          console.error('Status poll error:', err);
        }
      }, 3000); // Poll every 3 seconds

      setStatusPollInterval(interval);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start training');
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshStatus = async () => {
    try {
      const status = await trmApi.getTrainingStatus();
      setTrainingStatus(status);
    } catch (err) {
      setError('Failed to refresh status');
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

  const phases = [
    { value: '1', label: 'Phase 1: Single-node base stock' },
    { value: '2', label: 'Phase 2: 2-node supply chain' },
    { value: '3', label: 'Phase 3: 4-node Supply Chain' },
    { value: '4', label: 'Phase 4: Multi-echelon variations' },
    { value: '5', label: 'Phase 5: Production scenarios' },
    { value: 'all', label: 'All Phases (Curriculum)' }
  ];

  return (
    <div>
      <H5 className="mb-2">TRM Model Training</H5>
      <Text className="text-muted-foreground mb-4">
        Train Tiny Recursive Models using curriculum learning. The model will learn progressively
        from simple single-node scenarios to complex multi-echelon supply chains.
      </Text>

      {error && (
        <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Quick Start Guide */}
      <Card className="mb-6 bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
        <CardContent className="pt-6">
          <div className="flex items-center gap-2 mb-3">
            <Lightbulb className="h-5 w-5 text-blue-600" />
            <H6>Quick Start Guide</H6>
          </div>
          <ol className="list-decimal list-inside space-y-1.5 text-sm">
            <li><strong>Select Configuration</strong>: Choose the supply chain network to train on</li>
            <li><strong>Select Phase</strong>: "All Phases" recommended for complete curriculum learning</li>
            <li><strong>Start Training</strong>: Model learns progressively from simple to complex</li>
            <li><strong>Monitor Progress</strong>: Watch train/val loss decrease across phases</li>
            <li><strong>Complete Training</strong>: All 5 phases for best generalization</li>
            <li><strong>Use Model</strong>: TRM provides fast (&lt;10ms) per-node decisions</li>
          </ol>
          <p className="text-xs text-muted-foreground mt-3">
            <strong>Architecture:</strong> 7M parameter transformer with 3-step recursive refinement for optimal ordering decisions
          </p>
        </CardContent>
      </Card>

      {/* Training Status */}
      {trainingStatus && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <div className="flex justify-between items-center mb-4">
              <H6>Training Status</H6>
              <div className="flex items-center gap-2">
                <Badge
                  variant={getStatusVariant(trainingStatus.status)}
                  size="sm"
                >
                  {trainingStatus.status.toUpperCase()}
                </Badge>
                <Button
                  size="sm"
                  variant="ghost"
                  leftIcon={<RefreshCw className="h-4 w-4" />}
                  onClick={handleRefreshStatus}
                >
                  Refresh
                </Button>
              </div>
            </div>

            {trainingStatus.status === 'training' && (
              <>
                <div className="mb-4">
                  <div className="flex justify-between mb-2">
                    <SmallText>
                      Phase {trainingStatus.phase} - Epoch {trainingStatus.epoch}/{trainingStatus.total_epochs}
                    </SmallText>
                    <SmallText>
                      {trainingStatus.epoch && trainingStatus.total_epochs
                        ? `${Math.round((trainingStatus.epoch / trainingStatus.total_epochs) * 100)}%`
                        : '0%'}
                    </SmallText>
                  </div>
                  <Progress
                    value={
                      trainingStatus.epoch && trainingStatus.total_epochs
                        ? (trainingStatus.epoch / trainingStatus.total_epochs) * 100
                        : 0
                    }
                    size="md"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <SmallText className="text-muted-foreground">
                      Train Loss
                    </SmallText>
                    <H6>
                      {trainingStatus.train_loss?.toFixed(4) || 'N/A'}
                    </H6>
                  </div>
                  <div>
                    <SmallText className="text-muted-foreground">
                      Validation Loss
                    </SmallText>
                    <H6>
                      {trainingStatus.val_loss?.toFixed(4) || 'N/A'}
                    </H6>
                  </div>
                </div>
              </>
            )}

            {trainingStatus.message && (
              <Alert variant={trainingStatus.status === 'failed' ? 'error' : 'info'} className="mt-4">
                {trainingStatus.message}
              </Alert>
            )}
          </CardContent>
        </Card>
      )}

      {/* Loss Chart */}
      {lossHistory.length > 0 && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <H6 className="mb-4">Training Loss History</H6>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={lossHistory}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="epoch" label={{ value: 'Epoch', position: 'insideBottom', offset: -5 }} />
                <YAxis label={{ value: 'Loss', angle: -90, position: 'insideLeft' }} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="train_loss" stroke="#8884d8" name="Train Loss" />
                <Line type="monotone" dataKey="val_loss" stroke="#82ca9d" name="Val Loss" />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Training Configuration */}
      <Card>
        <CardContent className="pt-6">
          <H6 className="mb-4">Training Configuration</H6>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Supply Chain Configuration Selection */}
            <FormField label="Supply Chain Configuration">
              {configsLoading ? (
                <div className="flex items-center gap-2 py-2">
                  <Spinner size="sm" />
                  <span className="text-sm text-muted-foreground">Loading configurations...</span>
                </div>
              ) : configsError ? (
                <Alert variant="error">{configsError}</Alert>
              ) : supplyChainConfigs.length === 0 ? (
                <Alert variant="warning">No supply chain configurations available for your organization.</Alert>
              ) : (
                <NativeSelect
                  value={trainingConfig.supply_chain_config}
                  onChange={(e) => handleConfigChange('supply_chain_config', e.target.value)}
                  disabled={trainingStatus?.status === 'training'}
                >
                  {supplyChainConfigs.map(config => (
                    <SelectOption key={config.id} value={config.id}>
                      {config.name} - {config.description}
                    </SelectOption>
                  ))}
                </NativeSelect>
              )}
            </FormField>

            {/* Phase Selection */}
            <FormField label="Training Phase">
              <NativeSelect
                value={trainingConfig.phase}
                onChange={(e) => handleConfigChange('phase', e.target.value)}
                disabled={trainingStatus?.status === 'training'}
              >
                {phases.map(phase => (
                  <SelectOption key={phase.value} value={phase.value}>
                    {phase.label}
                  </SelectOption>
                ))}
              </NativeSelect>
            </FormField>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
            {/* Device Selection */}
            <FormField label="Device">
              <NativeSelect
                value={trainingConfig.device}
                onChange={(e) => handleConfigChange('device', e.target.value)}
                disabled={trainingStatus?.status === 'training'}
              >
                <SelectOption value="cuda">CUDA (GPU)</SelectOption>
                <SelectOption value="cpu">CPU</SelectOption>
              </NativeSelect>
            </FormField>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
            {/* Epochs */}
            <FormField label="Epochs per Phase">
              <Input
                type="number"
                value={trainingConfig.epochs}
                onChange={(e) => handleConfigChange('epochs', parseInt(e.target.value))}
                disabled={trainingStatus?.status === 'training'}
                min={1}
                max={500}
              />
            </FormField>

            {/* Batch Size */}
            <FormField label="Batch Size">
              <Input
                type="number"
                value={trainingConfig.batch_size}
                onChange={(e) => handleConfigChange('batch_size', parseInt(e.target.value))}
                disabled={trainingStatus?.status === 'training'}
                min={1}
                max={256}
              />
            </FormField>

            {/* Learning Rate */}
            <FormField label="Learning Rate">
              <Input
                type="number"
                value={trainingConfig.learning_rate}
                onChange={(e) => handleConfigChange('learning_rate', parseFloat(e.target.value))}
                disabled={trainingStatus?.status === 'training'}
                min={0.00001}
                max={0.01}
                step={0.00001}
              />
            </FormField>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
            {/* Number of Samples */}
            <FormField label="Samples per Phase">
              <Input
                type="number"
                value={trainingConfig.num_samples}
                onChange={(e) => handleConfigChange('num_samples', parseInt(e.target.value))}
                disabled={trainingStatus?.status === 'training'}
                min={1000}
                max={100000}
              />
            </FormField>

            {/* Model Dimension */}
            <FormField label="Model Dimension">
              <Input
                type="number"
                value={trainingConfig.d_model}
                onChange={(e) => handleConfigChange('d_model', parseInt(e.target.value))}
                disabled={trainingStatus?.status === 'training'}
                min={128}
                max={1024}
                step={64}
              />
            </FormField>

            {/* Attention Heads */}
            <FormField label="Attention Heads">
              <Input
                type="number"
                value={trainingConfig.nhead}
                onChange={(e) => handleConfigChange('nhead', parseInt(e.target.value))}
                disabled={trainingStatus?.status === 'training'}
                min={2}
                max={16}
              />
            </FormField>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
            {/* Number of Layers */}
            <FormField label="Transformer Layers">
              <Input
                type="number"
                value={trainingConfig.num_layers}
                onChange={(e) => handleConfigChange('num_layers', parseInt(e.target.value))}
                disabled={trainingStatus?.status === 'training'}
                min={1}
                max={4}
              />
            </FormField>

            {/* Refinement Steps */}
            <FormField label="Refinement Steps">
              <Input
                type="number"
                value={trainingConfig.refinement_steps}
                onChange={(e) => handleConfigChange('refinement_steps', parseInt(e.target.value))}
                disabled={trainingStatus?.status === 'training'}
                min={1}
                max={5}
              />
            </FormField>
          </div>

          {/* Checkpoint Directory */}
          <div className="mt-4">
            <FormField label="Checkpoint Directory">
              <Input
                value={trainingConfig.checkpoint_dir}
                onChange={(e) => handleConfigChange('checkpoint_dir', e.target.value)}
                disabled={trainingStatus?.status === 'training'}
              />
            </FormField>
          </div>

          <hr className="my-6 border-border" />

          {/* Action Buttons */}
          <div className="flex justify-end gap-2">
            <Button
              variant="default"
              leftIcon={<Play className="h-4 w-4" />}
              onClick={handleStartTraining}
              disabled={loading || trainingStatus?.status === 'training'}
              loading={loading}
            >
              {loading ? 'Starting...' : 'Start Training'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Info Section */}
      <Card className="mt-6">
        <CardContent className="pt-6">
          <H6 className="mb-4">Curriculum Learning Phases</H6>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Phase</TableCell>
                  <TableCell>Name</TableCell>
                  <TableCell>Description</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                <TableRow>
                  <TableCell>1</TableCell>
                  <TableCell>Single-node base stock</TableCell>
                  <TableCell>Simple inventory management with optimal policy</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>2</TableCell>
                  <TableCell>2-node supply chain</TableCell>
                  <TableCell>Basic upstream/downstream relationships</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>3</TableCell>
                  <TableCell>4-node Supply Chain</TableCell>
                  <TableCell>Classic supply chain configuration</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>4</TableCell>
                  <TableCell>Multi-echelon variations</TableCell>
                  <TableCell>Different network topologies and complexities</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>5</TableCell>
                  <TableCell>Production scenarios</TableCell>
                  <TableCell>Manufacturing constraints and production planning</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    </div>
  );
};

export default TRMTrainingPanel;
