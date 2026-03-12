/**
 * AI Training Configuration Component
 *
 * Allows Customer Admin to configure and manage ADH (Adaptive Decision Hierarchy) AI model training:
 * - Create ADH Training Configurations
 * - Link to hierarchy configs for S&OP and Execution levels
 * - Generate synthetic training data
 * - Start and monitor training runs
 * - View training data statistics
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  CardActions,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  Alert,
  Snackbar,
  Chip,
  Tooltip,
  IconButton,
  Divider,
  LinearProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  CircularProgress,
  Tabs,
  Tab
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  PlayArrow as StartIcon,
  Refresh as RefreshIcon,
  Psychology as AIIcon,
  Storage as DataIcon,
  Timeline as TrainingIcon,
  ExpandMore as ExpandMoreIcon,
  CheckCircle as SuccessIcon,
  Error as ErrorIcon,
  HourglassEmpty as PendingIcon,
  Settings as SettingsIcon,
  Assessment as StatsIcon
} from '@mui/icons-material';
import { api } from '../../services/api';

// TRM Types with descriptions
const TRM_TYPES = [
  {
    type: 'atp_executor',
    name: 'ATP Executor',
    description: 'Allocated Available-to-Promise consumption decisions',
    scope: 'Per order, <10ms'
  },
  {
    type: 'rebalancing',
    name: 'Inventory Rebalancing',
    description: 'Cross-location inventory transfer decisions',
    scope: 'Per product-location pair, daily'
  },
  {
    type: 'po_creation',
    name: 'PO Creation',
    description: 'Purchase order timing and quantity decisions',
    scope: 'Per product-location, daily'
  },
  {
    type: 'order_tracking',
    name: 'Order Tracking',
    description: 'Exception detection and recommended resolution actions',
    scope: 'Per order, continuous'
  }
];

const STATUS_COLORS = {
  pending: 'default',
  generating_data: 'info',
  training_sop: 'primary',
  training_tgnn: 'secondary',
  training_trm: 'warning',
  completed: 'success',
  failed: 'error'
};

const STATUS_ICONS = {
  pending: <PendingIcon />,
  completed: <SuccessIcon color="success" />,
  failed: <ErrorIcon color="error" />,
  generating_data: <DataIcon color="info" />,
  training_sop: <AIIcon color="primary" />,
  training_tgnn: <AIIcon color="secondary" />,
  training_trm: <AIIcon color="warning" />
};

export default function AITrainingConfig({ tenantId, hierarchyConfigs = [], supplyChainConfigs = [] }) {
  const [configs, setConfigs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState(null);
  const [statsDialogOpen, setStatsDialogOpen] = useState(false);
  const [selectedConfigStats, setSelectedConfigStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [syntheticDataDialogOpen, setSyntheticDataDialogOpen] = useState(false);
  const [generatingData, setGeneratingData] = useState(false);
  const [activeTab, setActiveTab] = useState(0);

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    config_id: '',
    sop_hierarchy_config_id: '',
    execution_hierarchy_config_id: '',
    num_simulation_runs: 128,
    timesteps_per_run: 64,
    history_window: 52,
    forecast_horizon: 8,
    train_sop_graphsage: true,
    sop_epochs: 50,
    sop_hidden_dim: 128,
    sop_embedding_dim: 64,
    train_execution_tgnn: true,
    tgnn_epochs: 100,
    tgnn_hidden_dim: 128,
    tgnn_window_size: 10,
    trm_training_method: 'hybrid',
    trm_bc_epochs: 20,
    trm_rl_epochs: 80
  });

  // Synthetic data generation form
  const [syntheticDataForm, setSyntheticDataForm] = useState({
    num_days: 365,
    num_orders_per_day: 50,
    num_decisions_per_day: 20,
    seed: ''
  });

  const effectiveTenantId = tenantId || localStorage.getItem('tenantId') || 1;

  const fetchConfigs = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get(`/powell-training/configs?tenant_id=${effectiveTenantId}`);
      setConfigs(response.data);
    } catch (err) {
      setError('Failed to load AI training configurations');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [effectiveTenantId]);

  useEffect(() => {
    fetchConfigs();
  }, [fetchConfigs]);

  const handleOpenDialog = (config = null) => {
    if (config) {
      setEditingConfig(config);
      setFormData({
        name: config.name,
        description: config.description || '',
        config_id: config.config_id,
        sop_hierarchy_config_id: config.sop_hierarchy_config_id || '',
        execution_hierarchy_config_id: config.execution_hierarchy_config_id || '',
        num_simulation_runs: config.num_simulation_runs,
        timesteps_per_run: config.timesteps_per_run,
        history_window: config.history_window,
        forecast_horizon: config.forecast_horizon,
        train_sop_graphsage: config.train_sop_graphsage,
        sop_epochs: config.sop_epochs,
        sop_hidden_dim: config.sop_hidden_dim,
        sop_embedding_dim: config.sop_embedding_dim,
        train_execution_tgnn: config.train_execution_tgnn,
        tgnn_epochs: config.tgnn_epochs,
        tgnn_hidden_dim: config.tgnn_hidden_dim,
        tgnn_window_size: config.tgnn_window_size,
        trm_training_method: config.trm_training_method,
        trm_bc_epochs: config.trm_bc_epochs,
        trm_rl_epochs: config.trm_rl_epochs
      });
    } else {
      setEditingConfig(null);
      setFormData({
        name: '',
        description: '',
        config_id: supplyChainConfigs[0]?.id || '',
        sop_hierarchy_config_id: '',
        execution_hierarchy_config_id: '',
        num_simulation_runs: 128,
        timesteps_per_run: 64,
        history_window: 52,
        forecast_horizon: 8,
        train_sop_graphsage: true,
        sop_epochs: 50,
        sop_hidden_dim: 128,
        sop_embedding_dim: 64,
        train_execution_tgnn: true,
        tgnn_epochs: 100,
        tgnn_hidden_dim: 128,
        tgnn_window_size: 10,
        trm_training_method: 'hybrid',
        trm_bc_epochs: 20,
        trm_rl_epochs: 80
      });
    }
    setDialogOpen(true);
  };

  const handleCloseDialog = () => {
    setDialogOpen(false);
    setEditingConfig(null);
  };

  const handleFormChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSaveConfig = async () => {
    try {
      const payload = {
        ...formData,
        sop_hierarchy_config_id: formData.sop_hierarchy_config_id || null,
        execution_hierarchy_config_id: formData.execution_hierarchy_config_id || null
      };

      if (editingConfig) {
        await api.put(`/powell-training/configs/${editingConfig.id}`, payload);
        setSuccess('Configuration updated successfully');
      } else {
        await api.post(`/powell-training/configs?tenant_id=${effectiveTenantId}`, payload);
        setSuccess('Configuration created successfully');
      }
      handleCloseDialog();
      fetchConfigs();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save configuration');
    }
  };

  const handleStartTraining = async (configId) => {
    try {
      await api.post(`/powell-training/configs/${configId}/start-training`);
      setSuccess('Training job started');
      fetchConfigs();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start training');
    }
  };

  const handleViewStats = async (config) => {
    setStatsLoading(true);
    setSelectedConfigStats(null);
    setStatsDialogOpen(true);

    try {
      const response = await api.get(`/powell-training/configs/${config.id}/training-data-stats`);
      setSelectedConfigStats({
        config,
        stats: response.data
      });
    } catch (err) {
      setError('Failed to load training data statistics');
    } finally {
      setStatsLoading(false);
    }
  };

  const handleGenerateSyntheticData = async (configId) => {
    setGeneratingData(true);
    try {
      const response = await api.post(
        `/powell-training/configs/${configId}/generate-synthetic-data`,
        {
          num_days: syntheticDataForm.num_days,
          num_orders_per_day: syntheticDataForm.num_orders_per_day,
          num_decisions_per_day: syntheticDataForm.num_decisions_per_day,
          seed: syntheticDataForm.seed ? parseInt(syntheticDataForm.seed) : null
        }
      );

      setSuccess(`Generated data: ${response.data.stats.replay_buffer_entries_created} replay buffer entries in ${response.data.duration_seconds.toFixed(1)}s`);
      setSyntheticDataDialogOpen(false);
      fetchConfigs();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to generate synthetic data');
    } finally {
      setGeneratingData(false);
    }
  };

  const renderConfigCard = (config) => {
    const statusInfo = STATUS_COLORS[config.last_training_status] || 'default';
    const statusIcon = STATUS_ICONS[config.last_training_status] || <PendingIcon />;

    const sopHierarchy = hierarchyConfigs.find(h => h.id === config.sop_hierarchy_config_id);
    const execHierarchy = hierarchyConfigs.find(h => h.id === config.execution_hierarchy_config_id);

    return (
      <Card key={config.id} sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <CardContent sx={{ flexGrow: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
            <AIIcon sx={{ mr: 1, color: 'primary.main' }} />
            <Typography variant="h6" sx={{ flexGrow: 1 }}>
              {config.name}
            </Typography>
            {config.last_training_status && (
              <Tooltip title={`Status: ${config.last_training_status}`}>
                <Chip
                  icon={statusIcon}
                  label={config.last_training_status}
                  size="small"
                  color={statusInfo}
                />
              </Tooltip>
            )}
          </Box>

          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {config.description || 'AI training configuration'}
          </Typography>

          <Divider sx={{ my: 1 }} />

          {/* Model Configuration Summary */}
          <Grid container spacing={1}>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary">S&OP Agent</Typography>
              <Typography variant="body2">
                {config.train_sop_graphsage ? (
                  <Chip label="Enabled" size="small" color="success" />
                ) : (
                  <Chip label="Disabled" size="small" />
                )}
              </Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary">Network Agent</Typography>
              <Typography variant="body2">
                {config.train_execution_tgnn ? (
                  <Chip label="Enabled" size="small" color="success" />
                ) : (
                  <Chip label="Disabled" size="small" />
                )}
              </Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary">S&OP Hierarchy</Typography>
              <Typography variant="body2" noWrap>
                {sopHierarchy ? sopHierarchy.name : 'Default'}
              </Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary">Execution Hierarchy</Typography>
              <Typography variant="body2" noWrap>
                {execHierarchy ? execHierarchy.name : 'Default'}
              </Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary">Agent Method</Typography>
              <Typography variant="body2">{config.trm_training_method}</Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary">Sim Runs</Typography>
              <Typography variant="body2">{config.num_simulation_runs}</Typography>
            </Grid>
          </Grid>

          {/* TRM Configs */}
          {config.trm_configs && config.trm_configs.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="caption" color="text.secondary">AI Agents</Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                {config.trm_configs.map(trm => (
                  <Chip
                    key={trm.trm_type}
                    label={trm.trm_type.replace('_', ' ')}
                    size="small"
                    color={trm.enabled ? 'primary' : 'default'}
                    variant={trm.enabled ? 'filled' : 'outlined'}
                  />
                ))}
              </Box>
            </Box>
          )}

          {/* Last Training Info */}
          {config.last_training_completed && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="caption" color="text.secondary">
                Last trained: {new Date(config.last_training_completed).toLocaleDateString()}
              </Typography>
            </Box>
          )}
        </CardContent>

        <CardActions sx={{ justifyContent: 'space-between', pt: 0 }}>
          <Box>
            <Tooltip title="View training data statistics">
              <IconButton size="small" onClick={() => handleViewStats(config)}>
                <StatsIcon />
              </IconButton>
            </Tooltip>
            <Tooltip title="Edit configuration">
              <IconButton size="small" onClick={() => handleOpenDialog(config)}>
                <EditIcon />
              </IconButton>
            </Tooltip>
          </Box>
          <Box>
            <Button
              size="small"
              variant="outlined"
              startIcon={<DataIcon />}
              onClick={() => {
                setEditingConfig(config);
                setSyntheticDataDialogOpen(true);
              }}
              sx={{ mr: 1 }}
            >
              Generate Data
            </Button>
            <Button
              size="small"
              variant="contained"
              startIcon={<StartIcon />}
              onClick={() => handleStartTraining(config.id)}
              disabled={config.last_training_status === 'generating_data' ||
                       config.last_training_status === 'training_sop' ||
                       config.last_training_status === 'training_tgnn' ||
                       config.last_training_status === 'training_trm'}
            >
              Train
            </Button>
          </Box>
        </CardActions>
      </Card>
    );
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      {/* Header */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <AIIcon sx={{ mr: 1, fontSize: 28 }} />
          <Typography variant="h5" sx={{ flexGrow: 1 }}>
            AI Training Configuration
          </Typography>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={fetchConfigs}
            sx={{ mr: 1 }}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => handleOpenDialog()}
          >
            New Training Config
          </Button>
        </Box>

        <Typography variant="body2" color="text.secondary">
          Configure AI model training for the Adaptive Decision Hierarchy. Select hierarchy levels for S&OP (strategic)
          and Execution (operational) models, configure training parameters, and manage synthetic data generation.
        </Typography>

        <Alert severity="info" sx={{ mt: 2 }}>
          <strong>Training Pipeline:</strong> Data Generation → S&OP Agent (aggregated) → Network Agent (detailed) → AI Agents (per-type)
        </Alert>
      </Paper>

      {/* Config Cards */}
      {configs.length === 0 ? (
        <Alert severity="info">
          No AI training configurations found. Create one to start training decision hierarchy models.
        </Alert>
      ) : (
        <Grid container spacing={3}>
          {configs.map(config => (
            <Grid item xs={12} md={6} lg={4} key={config.id}>
              {renderConfigCard(config)}
            </Grid>
          ))}
        </Grid>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>
          {editingConfig ? 'Edit AI Training Configuration' : 'New AI Training Configuration'}
        </DialogTitle>
        <DialogContent>
          <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)} sx={{ mb: 2 }}>
            <Tab label="Basic Settings" />
            <Tab label="S&OP Agent" />
            <Tab label="Network Agent" />
            <Tab label="Agent Settings" />
          </Tabs>

          {activeTab === 0 && (
            <Grid container spacing={3} sx={{ mt: 1 }}>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Name"
                  value={formData.name}
                  onChange={(e) => handleFormChange('name', e.target.value)}
                  required
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth required>
                  <InputLabel>Supply Chain Config</InputLabel>
                  <Select
                    value={formData.config_id}
                    label="Supply Chain Config"
                    onChange={(e) => handleFormChange('config_id', e.target.value)}
                    disabled={!!editingConfig}
                  >
                    {supplyChainConfigs.map(sc => (
                      <MenuItem key={sc.id} value={sc.id}>{sc.name}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Description"
                  value={formData.description}
                  onChange={(e) => handleFormChange('description', e.target.value)}
                  multiline
                  rows={2}
                />
              </Grid>

              <Grid item xs={12}>
                <Divider><Chip label="Hierarchy Configuration" /></Divider>
              </Grid>

              <Grid item xs={12} sm={6}>
                <FormControl fullWidth>
                  <InputLabel>S&OP Hierarchy Level</InputLabel>
                  <Select
                    value={formData.sop_hierarchy_config_id}
                    label="S&OP Hierarchy Level"
                    onChange={(e) => handleFormChange('sop_hierarchy_config_id', e.target.value)}
                  >
                    <MenuItem value="">Default (no aggregation)</MenuItem>
                    {hierarchyConfigs
                      .filter(h => h.planning_type === 'sop')
                      .map(h => (
                        <MenuItem key={h.id} value={h.id}>
                          {h.name} ({h.site_hierarchy_level} / {h.product_hierarchy_level})
                        </MenuItem>
                      ))}
                  </Select>
                </FormControl>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                  Determines aggregation level for S&OP model training
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth>
                  <InputLabel>Execution Hierarchy Level</InputLabel>
                  <Select
                    value={formData.execution_hierarchy_config_id}
                    label="Execution Hierarchy Level"
                    onChange={(e) => handleFormChange('execution_hierarchy_config_id', e.target.value)}
                  >
                    <MenuItem value="">Default (site/product level)</MenuItem>
                    {hierarchyConfigs
                      .filter(h => h.planning_type === 'execution')
                      .map(h => (
                        <MenuItem key={h.id} value={h.id}>
                          {h.name} ({h.site_hierarchy_level} / {h.product_hierarchy_level})
                        </MenuItem>
                      ))}
                  </Select>
                </FormControl>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                  Determines granularity for Execution model training
                </Typography>
              </Grid>

              <Grid item xs={12}>
                <Divider><Chip label="Data Generation" /></Divider>
              </Grid>

              <Grid item xs={6} sm={3}>
                <TextField
                  fullWidth
                  type="number"
                  label="Simulation Runs"
                  value={formData.num_simulation_runs}
                  onChange={(e) => handleFormChange('num_simulation_runs', parseInt(e.target.value))}
                  inputProps={{ min: 10, max: 1000 }}
                />
              </Grid>
              <Grid item xs={6} sm={3}>
                <TextField
                  fullWidth
                  type="number"
                  label="Timesteps/Run"
                  value={formData.timesteps_per_run}
                  onChange={(e) => handleFormChange('timesteps_per_run', parseInt(e.target.value))}
                  inputProps={{ min: 20, max: 500 }}
                />
              </Grid>
              <Grid item xs={6} sm={3}>
                <TextField
                  fullWidth
                  type="number"
                  label="History Window"
                  value={formData.history_window}
                  onChange={(e) => handleFormChange('history_window', parseInt(e.target.value))}
                  inputProps={{ min: 10, max: 100 }}
                />
              </Grid>
              <Grid item xs={6} sm={3}>
                <TextField
                  fullWidth
                  type="number"
                  label="Forecast Horizon"
                  value={formData.forecast_horizon}
                  onChange={(e) => handleFormChange('forecast_horizon', parseInt(e.target.value))}
                  inputProps={{ min: 1, max: 52 }}
                />
              </Grid>
            </Grid>
          )}

          {activeTab === 1 && (
            <Grid container spacing={3} sx={{ mt: 1 }}>
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.train_sop_graphsage}
                      onChange={(e) => handleFormChange('train_sop_graphsage', e.target.checked)}
                    />
                  }
                  label="Train S&OP Agent"
                />
                <Typography variant="body2" color="text.secondary">
                  Strategic model that learns network structure, risk scoring, and bottleneck detection
                </Typography>
              </Grid>

              <Grid item xs={12} sm={4}>
                <TextField
                  fullWidth
                  type="number"
                  label="Hidden Dimensions"
                  value={formData.sop_hidden_dim}
                  onChange={(e) => handleFormChange('sop_hidden_dim', parseInt(e.target.value))}
                  inputProps={{ min: 32, max: 512 }}
                  disabled={!formData.train_sop_graphsage}
                />
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField
                  fullWidth
                  type="number"
                  label="Embedding Dimensions"
                  value={formData.sop_embedding_dim}
                  onChange={(e) => handleFormChange('sop_embedding_dim', parseInt(e.target.value))}
                  inputProps={{ min: 16, max: 256 }}
                  disabled={!formData.train_sop_graphsage}
                />
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField
                  fullWidth
                  type="number"
                  label="Training Epochs"
                  value={formData.sop_epochs}
                  onChange={(e) => handleFormChange('sop_epochs', parseInt(e.target.value))}
                  inputProps={{ min: 1, max: 500 }}
                  disabled={!formData.train_sop_graphsage}
                />
              </Grid>

              <Grid item xs={12}>
                <Alert severity="info">
                  The S&OP model is trained on aggregated data based on the hierarchy level you select.
                  It outputs criticality scores, bottleneck risk, concentration risk, and resilience scores.
                </Alert>
              </Grid>
            </Grid>
          )}

          {activeTab === 2 && (
            <Grid container spacing={3} sx={{ mt: 1 }}>
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.train_execution_tgnn}
                      onChange={(e) => handleFormChange('train_execution_tgnn', e.target.checked)}
                    />
                  }
                  label="Train Network Agent"
                />
                <Typography variant="body2" color="text.secondary">
                  Operational model that generates priority allocations and provides context for AI agent decisions
                </Typography>
              </Grid>

              <Grid item xs={12} sm={4}>
                <TextField
                  fullWidth
                  type="number"
                  label="Hidden Dimensions"
                  value={formData.tgnn_hidden_dim}
                  onChange={(e) => handleFormChange('tgnn_hidden_dim', parseInt(e.target.value))}
                  inputProps={{ min: 32, max: 512 }}
                  disabled={!formData.train_execution_tgnn}
                />
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField
                  fullWidth
                  type="number"
                  label="Window Size"
                  value={formData.tgnn_window_size}
                  onChange={(e) => handleFormChange('tgnn_window_size', parseInt(e.target.value))}
                  inputProps={{ min: 5, max: 50 }}
                  disabled={!formData.train_execution_tgnn}
                />
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField
                  fullWidth
                  type="number"
                  label="Training Epochs"
                  value={formData.tgnn_epochs}
                  onChange={(e) => handleFormChange('tgnn_epochs', parseInt(e.target.value))}
                  inputProps={{ min: 1, max: 500 }}
                  disabled={!formData.train_execution_tgnn}
                />
              </Grid>

              <Grid item xs={12}>
                <Alert severity="info">
                  The execution model consumes S&OP embeddings and transactional data.
                  It outputs Priority x Product x Location allocations for AATP consumption.
                </Alert>
              </Grid>
            </Grid>
          )}

          {activeTab === 3 && (
            <Grid container spacing={3} sx={{ mt: 1 }}>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth>
                  <InputLabel>Training Method</InputLabel>
                  <Select
                    value={formData.trm_training_method}
                    label="Training Method"
                    onChange={(e) => handleFormChange('trm_training_method', e.target.value)}
                  >
                    <MenuItem value="behavioral_cloning">Behavioral Cloning (supervised)</MenuItem>
                    <MenuItem value="td_learning">TD Learning (Q-learning)</MenuItem>
                    <MenuItem value="hybrid">Hybrid (BC warm-start + RL fine-tune)</MenuItem>
                    <MenuItem value="offline_rl">Offline RL (Conservative Q-Learning)</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              <Grid item xs={6} sm={3}>
                <TextField
                  fullWidth
                  type="number"
                  label="BC Epochs"
                  value={formData.trm_bc_epochs}
                  onChange={(e) => handleFormChange('trm_bc_epochs', parseInt(e.target.value))}
                  inputProps={{ min: 1, max: 100 }}
                  helperText="Behavioral cloning"
                />
              </Grid>
              <Grid item xs={6} sm={3}>
                <TextField
                  fullWidth
                  type="number"
                  label="RL Epochs"
                  value={formData.trm_rl_epochs}
                  onChange={(e) => handleFormChange('trm_rl_epochs', parseInt(e.target.value))}
                  inputProps={{ min: 1, max: 500 }}
                  helperText="Reinforcement learning"
                />
              </Grid>

              <Grid item xs={12}>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>Agent Types (4 specialized models)</Typography>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Type</TableCell>
                        <TableCell>Description</TableCell>
                        <TableCell>Scope</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {TRM_TYPES.map(trm => (
                        <TableRow key={trm.type}>
                          <TableCell>
                            <Chip label={trm.name} size="small" color="primary" />
                          </TableCell>
                          <TableCell>{trm.description}</TableCell>
                          <TableCell>{trm.scope}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Grid>
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancel</Button>
          <Button variant="contained" onClick={handleSaveConfig}>
            {editingConfig ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Stats Dialog */}
      <Dialog open={statsDialogOpen} onClose={() => setStatsDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          Training Data Statistics
          {selectedConfigStats && ` - ${selectedConfigStats.config.name}`}
        </DialogTitle>
        <DialogContent>
          {statsLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          ) : selectedConfigStats ? (
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 2 }}>Decision Logs</Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="caption">ATP Decisions</Typography>
                  <Typography variant="h6">{selectedConfigStats.stats.atp_decisions?.toLocaleString() || 0}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption">Rebalancing Decisions</Typography>
                  <Typography variant="h6">{selectedConfigStats.stats.rebalancing_decisions?.toLocaleString() || 0}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption">PO Decisions</Typography>
                  <Typography variant="h6">{selectedConfigStats.stats.po_decisions?.toLocaleString() || 0}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption">Order Tracking Decisions</Typography>
                  <Typography variant="h6">{selectedConfigStats.stats.order_tracking_decisions?.toLocaleString() || 0}</Typography>
                </Grid>
              </Grid>

              <Divider sx={{ my: 2 }} />

              <Typography variant="subtitle2" sx={{ mb: 2 }}>Replay Buffer</Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="caption">Total Entries</Typography>
                  <Typography variant="h6">{selectedConfigStats.stats.replay_buffer_entries?.toLocaleString() || 0}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption">Expert Entries</Typography>
                  <Typography variant="h6">{selectedConfigStats.stats.expert_entries?.toLocaleString() || 0}</Typography>
                </Grid>
              </Grid>

              <Divider sx={{ my: 2 }} />

              <Typography variant="subtitle2" sx={{ mb: 2 }}>Transactional Data</Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="caption">Forecasts</Typography>
                  <Typography variant="h6">{selectedConfigStats.stats.forecasts?.toLocaleString() || 0}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption">Inventory Snapshots</Typography>
                  <Typography variant="h6">{selectedConfigStats.stats.inventory_snapshots?.toLocaleString() || 0}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption">Outbound Orders</Typography>
                  <Typography variant="h6">{selectedConfigStats.stats.outbound_orders?.toLocaleString() || 0}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption">Purchase Orders</Typography>
                  <Typography variant="h6">{selectedConfigStats.stats.purchase_orders?.toLocaleString() || 0}</Typography>
                </Grid>
              </Grid>

              <Alert severity={selectedConfigStats.stats.total_samples > 1000 ? 'success' : 'warning'} sx={{ mt: 2 }}>
                {selectedConfigStats.stats.total_samples > 1000
                  ? `Ready for training with ${selectedConfigStats.stats.total_samples.toLocaleString()} samples`
                  : `Need more data: ${selectedConfigStats.stats.total_samples || 0} samples (min 1000 recommended)`
                }
              </Alert>
            </Box>
          ) : (
            <Alert severity="error">Failed to load statistics</Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStatsDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Synthetic Data Generation Dialog */}
      <Dialog open={syntheticDataDialogOpen} onClose={() => setSyntheticDataDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          Generate Synthetic Training Data
          {editingConfig && ` - ${editingConfig.name}`}
        </DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 3 }}>
            Generate realistic synthetic data including forecasts, inventory levels, orders, TRM decisions,
            outcomes, and replay buffer entries for RL training.
          </Alert>

          <Grid container spacing={3}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                type="number"
                label="Number of Days"
                value={syntheticDataForm.num_days}
                onChange={(e) => setSyntheticDataForm(prev => ({ ...prev, num_days: parseInt(e.target.value) }))}
                inputProps={{ min: 30, max: 730 }}
                helperText="Days of history to simulate"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                type="number"
                label="Orders per Day"
                value={syntheticDataForm.num_orders_per_day}
                onChange={(e) => setSyntheticDataForm(prev => ({ ...prev, num_orders_per_day: parseInt(e.target.value) }))}
                inputProps={{ min: 10, max: 500 }}
                helperText="Average orders per day"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                type="number"
                label="Decisions per Day"
                value={syntheticDataForm.num_decisions_per_day}
                onChange={(e) => setSyntheticDataForm(prev => ({ ...prev, num_decisions_per_day: parseInt(e.target.value) }))}
                inputProps={{ min: 5, max: 200 }}
                helperText="AI agent decisions per day"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                type="number"
                label="Random Seed (optional)"
                value={syntheticDataForm.seed}
                onChange={(e) => setSyntheticDataForm(prev => ({ ...prev, seed: e.target.value }))}
                helperText="For reproducibility"
              />
            </Grid>
          </Grid>

          <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
            Estimated records: ~{(syntheticDataForm.num_days * syntheticDataForm.num_decisions_per_day).toLocaleString()} replay buffer entries
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSyntheticDataDialogOpen(false)} disabled={generatingData}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={() => handleGenerateSyntheticData(editingConfig?.id)}
            disabled={generatingData}
            startIcon={generatingData ? <CircularProgress size={20} /> : <DataIcon />}
          >
            {generatingData ? 'Generating...' : 'Generate Data'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Notifications */}
      <Snackbar open={!!error} autoHideDuration={6000} onClose={() => setError(null)}>
        <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>
      </Snackbar>
      <Snackbar open={!!success} autoHideDuration={4000} onClose={() => setSuccess(null)}>
        <Alert severity="success" onClose={() => setSuccess(null)}>{success}</Alert>
      </Snackbar>
    </Box>
  );
}
