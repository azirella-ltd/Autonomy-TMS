/**
 * Planning Hierarchy Configuration
 *
 * Organization administrator interface for configuring planning hierarchies.
 * Allows setting hierarchy levels for different planning types (S&OP, MPS, MRP, etc.)
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
  Slider,
  Switch,
  FormControlLabel,
  Alert,
  Snackbar,
  Chip,
  Tooltip,
  IconButton,
  Divider,
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
  ContentCopy as CopyIcon,
  Refresh as RefreshIcon,
  Info as InfoIcon,
  AccountTree as HierarchyIcon,
  Timeline as TimelineIcon,
  Settings as SettingsIcon,
  Psychology as AIIcon
} from '@mui/icons-material';
import { api } from '../../services/api';
import AITrainingConfig from '../../components/admin/AITrainingConfig';

// Hierarchy level options
const SITE_HIERARCHY_LEVELS = [
  { value: 'company', label: 'Company', description: 'Enterprise-wide aggregation' },
  { value: 'region', label: 'Region', description: 'Geographic regions (APAC, EMEA, Americas)' },
  { value: 'country', label: 'Country', description: 'Country-level aggregation' },
  { value: 'state', label: 'State/Province', description: 'State or province level' },
  { value: 'site', label: 'Site', description: 'Individual warehouse, DC, or factory' }
];

const PRODUCT_HIERARCHY_LEVELS = [
  { value: 'category', label: 'Category', description: 'Broad product categories' },
  { value: 'family', label: 'Family', description: 'Product families' },
  { value: 'group', label: 'Group', description: 'Product groups' },
  { value: 'product', label: 'Product (SKU)', description: 'Individual SKUs' }
];

const TIME_BUCKET_OPTIONS = [
  { value: 'hour', label: 'Hour', description: 'Real-time execution' },
  { value: 'day', label: 'Day', description: 'Daily planning' },
  { value: 'week', label: 'Week', description: 'Weekly planning' },
  { value: 'month', label: 'Month', description: 'Monthly planning' },
  { value: 'quarter', label: 'Quarter', description: 'Quarterly planning' },
  { value: 'year', label: 'Year', description: 'Annual planning' }
];

const POWELL_POLICY_CLASSES = [
  { value: 'pfa', label: 'PFA', description: 'Policy Function Approximation - Direct state-to-action mapping' },
  { value: 'cfa', label: 'CFA', description: 'Cost Function Approximation - Optimizes policy parameters' },
  { value: 'vfa', label: 'VFA', description: 'Value Function Approximation - Learns state values' },
  { value: 'dla', label: 'DLA', description: 'Direct Lookahead - Model predictive control' }
];

const GNN_MODEL_TYPES = [
  { value: 'sop_graphsage', label: 'S&OP GraphSAGE', description: 'Strategic structural analysis' },
  { value: 'execution_tgnn', label: 'Execution tGNN', description: 'Operational decisions' },
  { value: 'hybrid', label: 'Hybrid', description: 'Combined S&OP + Execution' }
];

const PLANNING_TYPE_INFO = {
  execution: { color: '#4caf50', icon: '⚡', description: 'Real-time ATP/CTP decisions' },
  mrp: { color: '#2196f3', icon: '📦', description: 'Material requirements planning' },
  mps: { color: '#ff9800', icon: '🏭', description: 'Master production scheduling' },
  sop: { color: '#9c27b0', icon: '📊', description: 'Sales & operations planning' },
  capacity: { color: '#f44336', icon: '⚙️', description: 'Capacity planning' },
  inventory: { color: '#00bcd4', icon: '📋', description: 'Inventory optimization' },
  network: { color: '#607d8b', icon: '🌐', description: 'Network design / Strategic' }
};

export default function PlanningHierarchyConfig() {
  const [configs, setConfigs] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [supplyChainConfigs, setSupplyChainConfigs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState(null);
  const [templateDialogOpen, setTemplateDialogOpen] = useState(false);
  const [mainTab, setMainTab] = useState(0);

  // Form state
  const [formData, setFormData] = useState({
    planning_type: 'mps',
    site_hierarchy_level: 'site',
    product_hierarchy_level: 'group',
    time_bucket: 'week',
    horizon_months: 6,
    frozen_periods: 4,
    slushy_periods: 8,
    update_frequency_hours: 168,
    powell_policy_class: 'cfa',
    gnn_model_type: 'hybrid',
    parent_planning_type: '',
    consistency_tolerance: 0.10,
    name: '',
    description: ''
  });

  // Get current user's tenant_id from localStorage or context
  const tenantId = localStorage.getItem('tenantId') || 1;

  const fetchConfigs = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get(`/planning-hierarchy/configs?tenant_id=${tenantId}`);
      setConfigs(response.data);
    } catch (err) {
      setError('Failed to load planning configurations');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  const fetchTemplates = useCallback(async () => {
    try {
      const response = await api.get('/planning-hierarchy/templates');
      setTemplates(response.data);
    } catch (err) {
      console.error('Failed to load templates:', err);
    }
  }, []);

  const fetchSupplyChainConfigs = useCallback(async () => {
    try {
      const response = await api.get(`/supply-chain-config/?tenant_id=${tenantId}`);
      const items = response.data.items || response.data || [];
      // Sort: root baseline configs first
      items.sort((a, b) => {
        const aRoot = !a.parent_config_id && a.scenario_type === 'BASELINE' ? 0 : 1;
        const bRoot = !b.parent_config_id && b.scenario_type === 'BASELINE' ? 0 : 1;
        return aRoot - bRoot;
      });
      setSupplyChainConfigs(items);
    } catch (err) {
      console.error('Failed to load supply chain configs:', err);
    }
  }, [tenantId]);

  useEffect(() => {
    fetchConfigs();
    fetchTemplates();
    fetchSupplyChainConfigs();
  }, [fetchConfigs, fetchTemplates, fetchSupplyChainConfigs]);

  const handleOpenDialog = (config = null) => {
    if (config) {
      setEditingConfig(config);
      setFormData({
        planning_type: config.planning_type,
        site_hierarchy_level: config.site_hierarchy_level,
        product_hierarchy_level: config.product_hierarchy_level,
        time_bucket: config.time_bucket,
        horizon_months: config.horizon_months,
        frozen_periods: config.frozen_periods,
        slushy_periods: config.slushy_periods,
        update_frequency_hours: config.update_frequency_hours,
        powell_policy_class: config.powell_policy_class,
        gnn_model_type: config.gnn_model_type || '',
        parent_planning_type: config.parent_planning_type || '',
        consistency_tolerance: config.consistency_tolerance,
        name: config.name,
        description: config.description || ''
      });
    } else {
      setEditingConfig(null);
      setFormData({
        planning_type: 'mps',
        site_hierarchy_level: 'site',
        product_hierarchy_level: 'group',
        time_bucket: 'week',
        horizon_months: 6,
        frozen_periods: 4,
        slushy_periods: 8,
        update_frequency_hours: 168,
        powell_policy_class: 'cfa',
        gnn_model_type: 'hybrid',
        parent_planning_type: '',
        consistency_tolerance: 0.10,
        name: '',
        description: ''
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
      if (editingConfig) {
        await api.put(`/planning-hierarchy/configs/${editingConfig.id}`, formData);
        setSuccess('Configuration updated successfully');
      } else {
        await api.post(`/planning-hierarchy/configs?tenant_id=${tenantId}`, formData);
        setSuccess('Configuration created successfully');
      }
      handleCloseDialog();
      fetchConfigs();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save configuration');
    }
  };

  const handleDeleteConfig = async (configId) => {
    if (!window.confirm('Are you sure you want to deactivate this configuration?')) {
      return;
    }
    try {
      await api.delete(`/planning-hierarchy/configs/${configId}`);
      setSuccess('Configuration deactivated');
      fetchConfigs();
    } catch (err) {
      setError('Failed to delete configuration');
    }
  };

  const handleApplyTemplate = async (templateCode) => {
    try {
      await api.post(
        `/planning-hierarchy/configs/from-template/${templateCode}?tenant_id=${tenantId}`
      );
      setSuccess(`Template "${templateCode}" applied successfully`);
      setTemplateDialogOpen(false);
      fetchConfigs();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to apply template');
    }
  };

  const handleInitializeDefaults = async () => {
    if (!window.confirm('Initialize all default planning configurations? This will create configurations for all planning types.')) {
      return;
    }
    try {
      const response = await api.post(
        `/planning-hierarchy/configs/initialize-defaults/${tenantId}`
      );
      setSuccess(response.data.message);
      fetchConfigs();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to initialize defaults');
    }
  };

  const renderConfigCard = (config) => {
    const typeInfo = PLANNING_TYPE_INFO[config.planning_type] || {};

    return (
      <Card
        key={config.id}
        sx={{
          height: '100%',
          borderLeft: `4px solid ${typeInfo.color}`,
          '&:hover': { boxShadow: 4 }
        }}
      >
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
            <Typography variant="h6" sx={{ flexGrow: 1 }}>
              {typeInfo.icon} {config.name}
            </Typography>
            <Chip
              label={config.planning_type.toUpperCase()}
              size="small"
              sx={{ backgroundColor: typeInfo.color, color: 'white' }}
            />
          </Box>

          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {config.description || typeInfo.description}
          </Typography>

          <Divider sx={{ my: 1 }} />

          <Grid container spacing={1}>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary">Site Level</Typography>
              <Typography variant="body2">{config.site_hierarchy_level}</Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary">Product Level</Typography>
              <Typography variant="body2">{config.product_hierarchy_level}</Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary">Time Bucket</Typography>
              <Typography variant="body2">{config.time_bucket}</Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary">Horizon</Typography>
              <Typography variant="body2">{config.horizon_months} months</Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary">Policy Class</Typography>
              <Chip label={config.powell_policy_class.toUpperCase()} size="small" color="primary" />
            </Grid>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary">GNN Model</Typography>
              <Typography variant="body2">{config.gnn_model_type || 'None'}</Typography>
            </Grid>
          </Grid>
        </CardContent>
        <CardActions>
          <Button size="small" startIcon={<EditIcon />} onClick={() => handleOpenDialog(config)}>
            Edit
          </Button>
          <Button
            size="small"
            color="error"
            startIcon={<DeleteIcon />}
            onClick={() => handleDeleteConfig(config.id)}
          >
            Delete
          </Button>
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
    <Box sx={{ p: 3 }}>
      {/* Page Header with Tabs */}
      <Paper sx={{ mb: 3 }}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={mainTab} onChange={(e, v) => setMainTab(v)}>
            <Tab icon={<HierarchyIcon />} iconPosition="start" label="Planning Hierarchy" />
            <Tab icon={<AIIcon />} iconPosition="start" label="AI Training" />
          </Tabs>
        </Box>
      </Paper>

      {/* Planning Hierarchy Tab */}
      {mainTab === 0 && (
        <>
          <Paper sx={{ p: 3, mb: 3 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <HierarchyIcon sx={{ mr: 1 }} />
              <Typography variant="h5" sx={{ flexGrow: 1 }}>
                Planning Hierarchy Configuration
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
                variant="outlined"
                startIcon={<CopyIcon />}
                onClick={() => setTemplateDialogOpen(true)}
                sx={{ mr: 1 }}
              >
                From Template
              </Button>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={() => handleOpenDialog()}
              >
                New Configuration
              </Button>
            </Box>

            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Configure hierarchy levels for different planning types. Higher hierarchy levels (Region, Family)
              are used for strategic planning (S&OP), while lower levels (Site, SKU) are used for operational
              planning (MRP, Execution).
            </Typography>

            {configs.length === 0 && (
              <Alert severity="info" sx={{ mb: 2 }}>
                No planning configurations found.
                <Button size="small" onClick={handleInitializeDefaults} sx={{ ml: 2 }}>
                  Initialize Defaults
                </Button>
              </Alert>
            )}
          </Paper>

          <Grid container spacing={3}>
            {configs.map(config => (
              <Grid item xs={12} sm={6} md={4} key={config.id}>
                {renderConfigCard(config)}
              </Grid>
            ))}
          </Grid>
        </>
      )}

      {/* AI Training Tab */}
      {mainTab === 1 && (
        <AITrainingConfig
          tenantId={tenantId}
          hierarchyConfigs={configs}
          supplyChainConfigs={supplyChainConfigs}
        />
      )}

      {/* Edit/Create Dialog */}
      <Dialog open={dialogOpen} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>
          {editingConfig ? 'Edit Planning Configuration' : 'New Planning Configuration'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={3} sx={{ mt: 1 }}>
            {/* Basic Info */}
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
              <FormControl fullWidth>
                <InputLabel>Planning Type</InputLabel>
                <Select
                  value={formData.planning_type}
                  label="Planning Type"
                  onChange={(e) => handleFormChange('planning_type', e.target.value)}
                  disabled={!!editingConfig}
                >
                  {Object.entries(PLANNING_TYPE_INFO).map(([value, info]) => (
                    <MenuItem key={value} value={value}>
                      {info.icon} {value.toUpperCase()} - {info.description}
                    </MenuItem>
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
              <Divider><Chip label="Hierarchy Levels" /></Divider>
            </Grid>

            {/* Hierarchy Levels */}
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Site Hierarchy Level</InputLabel>
                <Select
                  value={formData.site_hierarchy_level}
                  label="Site Hierarchy Level"
                  onChange={(e) => handleFormChange('site_hierarchy_level', e.target.value)}
                >
                  {SITE_HIERARCHY_LEVELS.map(level => (
                    <MenuItem key={level.value} value={level.value}>
                      {level.label} - {level.description}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Product Hierarchy Level</InputLabel>
                <Select
                  value={formData.product_hierarchy_level}
                  label="Product Hierarchy Level"
                  onChange={(e) => handleFormChange('product_hierarchy_level', e.target.value)}
                >
                  {PRODUCT_HIERARCHY_LEVELS.map(level => (
                    <MenuItem key={level.value} value={level.value}>
                      {level.label} - {level.description}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12}>
              <Divider><Chip label="Time Configuration" /></Divider>
            </Grid>

            {/* Time Configuration */}
            <Grid item xs={12} sm={4}>
              <FormControl fullWidth>
                <InputLabel>Time Bucket</InputLabel>
                <Select
                  value={formData.time_bucket}
                  label="Time Bucket"
                  onChange={(e) => handleFormChange('time_bucket', e.target.value)}
                >
                  {TIME_BUCKET_OPTIONS.map(opt => (
                    <MenuItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                fullWidth
                type="number"
                label="Horizon (months)"
                value={formData.horizon_months}
                onChange={(e) => handleFormChange('horizon_months', parseInt(e.target.value))}
                inputProps={{ min: 1, max: 120 }}
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                fullWidth
                type="number"
                label="Update Frequency (hours)"
                value={formData.update_frequency_hours}
                onChange={(e) => handleFormChange('update_frequency_hours', parseInt(e.target.value))}
                inputProps={{ min: 1 }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                type="number"
                label="Frozen Periods"
                value={formData.frozen_periods}
                onChange={(e) => handleFormChange('frozen_periods', parseInt(e.target.value))}
                inputProps={{ min: 0 }}
                helperText="No changes allowed within this window"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                type="number"
                label="Slushy Periods"
                value={formData.slushy_periods}
                onChange={(e) => handleFormChange('slushy_periods', parseInt(e.target.value))}
                inputProps={{ min: 0 }}
                helperText="Changes require approval"
              />
            </Grid>

            <Grid item xs={12}>
              <Divider><Chip label="AI / Decision Hierarchy" /></Divider>
            </Grid>

            {/* Powell Framework Settings */}
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Policy Class</InputLabel>
                <Select
                  value={formData.powell_policy_class}
                  label="Policy Class"
                  onChange={(e) => handleFormChange('powell_policy_class', e.target.value)}
                >
                  {POWELL_POLICY_CLASSES.map(cls => (
                    <MenuItem key={cls.value} value={cls.value}>
                      <Tooltip title={cls.description}>
                        <span>{cls.label} - {cls.description}</span>
                      </Tooltip>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>GNN Model Type</InputLabel>
                <Select
                  value={formData.gnn_model_type}
                  label="GNN Model Type"
                  onChange={(e) => handleFormChange('gnn_model_type', e.target.value)}
                >
                  <MenuItem value="">None</MenuItem>
                  {GNN_MODEL_TYPES.map(model => (
                    <MenuItem key={model.value} value={model.value}>
                      {model.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Parent Planning Type</InputLabel>
                <Select
                  value={formData.parent_planning_type}
                  label="Parent Planning Type"
                  onChange={(e) => handleFormChange('parent_planning_type', e.target.value)}
                >
                  <MenuItem value="">None</MenuItem>
                  {Object.keys(PLANNING_TYPE_INFO).map(type => (
                    <MenuItem key={type} value={type}>
                      {type.toUpperCase()}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Typography gutterBottom>
                Consistency Tolerance: {(formData.consistency_tolerance * 100).toFixed(0)}%
              </Typography>
              <Slider
                value={formData.consistency_tolerance}
                onChange={(e, value) => handleFormChange('consistency_tolerance', value)}
                min={0.01}
                max={0.50}
                step={0.01}
                marks={[
                  { value: 0.05, label: '5%' },
                  { value: 0.10, label: '10%' },
                  { value: 0.15, label: '15%' },
                  { value: 0.20, label: '20%' }
                ]}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancel</Button>
          <Button variant="contained" onClick={handleSaveConfig}>
            {editingConfig ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Template Selection Dialog */}
      <Dialog open={templateDialogOpen} onClose={() => setTemplateDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Select Planning Template</DialogTitle>
        <DialogContent>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Template</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Site Level</TableCell>
                  <TableCell>Product Level</TableCell>
                  <TableCell>Time</TableCell>
                  <TableCell>Horizon</TableCell>
                  <TableCell>Policy Class</TableCell>
                  <TableCell>Action</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {templates.map(template => (
                  <TableRow key={template.code}>
                    <TableCell>
                      <Typography variant="body2" fontWeight="bold">{template.name}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {template.description}
                      </Typography>
                    </TableCell>
                    <TableCell>{template.planning_type}</TableCell>
                    <TableCell>{template.site_hierarchy_level}</TableCell>
                    <TableCell>{template.product_hierarchy_level}</TableCell>
                    <TableCell>{template.time_bucket}</TableCell>
                    <TableCell>{template.horizon_months}m</TableCell>
                    <TableCell>
                      <Chip label={template.powell_policy_class.toUpperCase()} size="small" />
                    </TableCell>
                    <TableCell>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => handleApplyTemplate(template.code)}
                      >
                        Apply
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTemplateDialogOpen(false)}>Cancel</Button>
        </DialogActions>
      </Dialog>

      {/* Notifications */}
      <Snackbar
        open={!!error}
        autoHideDuration={6000}
        onClose={() => setError(null)}
      >
        <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>
      </Snackbar>
      <Snackbar
        open={!!success}
        autoHideDuration={4000}
        onClose={() => setSuccess(null)}
      >
        <Alert severity="success" onClose={() => setSuccess(null)}>{success}</Alert>
      </Snackbar>
    </Box>
  );
}
