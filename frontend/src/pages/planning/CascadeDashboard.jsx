/**
 * Planning Cascade Dashboard
 *
 * Comprehensive view of the full planning cascade:
 * S&OP → MPS → Supply Agent → Allocation Agent → Execution
 *
 * Enhanced with layer mode awareness for modular selling.
 * Shows feed-forward contracts, feed-back signals, and per-layer purchase status.
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Button,
  Chip,
  Alert,
  Card,
  CardContent,
  CardHeader,
  CardActions,
  CircularProgress,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Divider,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemSecondaryAction,
} from '@mui/material';
import {
  PlayArrow as RunIcon,
  Refresh as RefreshIcon,
  CheckCircle as SuccessIcon,
  Warning as WarningIcon,
  ArrowForward as ArrowIcon,
  ArrowBack as BackArrowIcon,
  Settings as SettingsIcon,
  Assignment as AssignmentIcon,
  LocalShipping as ShippingIcon,
  Category as CategoryIcon,
  TrendingUp as TrendingUpIcon,
  Timeline as TimelineIcon,
  Edit as InputIcon,
  Block as DisabledIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { api } from '../../services/api';
import { getLayerLicenses, getCascadeStatus, getFeedbackSignals } from '../../services/planningCascadeApi';
import LayerModeIndicator from '../../components/cascade/LayerModeIndicator';

const LAYER_KEYS = ['sop', 'mps', 'supply_agent', 'allocation_agent', 'execution'];

const CASCADE_STEPS = [
  {
    label: 'S&OP Policy Envelope',
    description: 'Policy parameters governing the cascade',
    icon: <SettingsIcon />,
    path: '/planning/sop-policy',
    feedForward: 'θ_SOP',
    layerKey: 'sop',
    inputLabel: 'Enter S&OP Parameters',
    activeLabel: 'View S&OP Parameters',
  },
  {
    label: 'MPS / Supply Baseline Pack',
    description: 'Candidate supply plans (5 methods)',
    icon: <AssignmentIcon />,
    path: '/planning/mps-candidates',
    feedForward: 'SupBP',
    layerKey: 'mps',
    inputLabel: 'Upload Supply Plan',
    activeLabel: 'View Candidates',
  },
  {
    label: 'Supply Agent',
    description: 'Supply Commit with integrity/risk checks',
    icon: <ShippingIcon />,
    path: '/planning/supply-worklist',
    feedForward: 'SC',
    layerKey: 'supply_agent',
    inputLabel: 'Manual PO Entry',
    activeLabel: 'Supply Worklist',
  },
  {
    label: 'Allocation Agent',
    description: 'Allocation Commit across segments',
    icon: <CategoryIcon />,
    path: '/planning/allocation-worklist',
    feedForward: 'AC',
    layerKey: 'allocation_agent',
    inputLabel: 'Manual Allocation Rules',
    activeLabel: 'Allocation Worklist',
  },
  {
    label: 'Execution',
    description: 'Feed-back signals for re-tuning',
    icon: <TrendingUpIcon />,
    path: '/planning/execution',
    feedForward: 'Feedback',
    layerKey: 'execution',
    inputLabel: 'View Execution',
    activeLabel: 'View Execution',
  },
];

const TIER_LABELS = {
  foundation: 'Foundation',
  ai_execution: 'AI Execution',
  planning: 'Planning',
  enterprise: 'Enterprise',
};

const CascadeDashboard = ({ configId, tenantId, mode: propMode }) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [cascadeStatus, setCascadeStatus] = useState(null);
  const [feedbackSignals, setFeedbackSignals] = useState([]);
  const [layerModes, setLayerModes] = useState({});
  const [packageTier, setPackageTier] = useState(null);
  const [activeStep, setActiveStep] = useState(0);
  const [runDialogOpen, setRunDialogOpen] = useState(false);

  // Derive mode from layer licenses (if no prop)
  const hasActiveSOPLayer = layerModes.sop === 'active';
  const isFullMode = propMode === 'FULL' || hasActiveSOPLayer;
  const isInputMode = !isFullMode;

  useEffect(() => {
    loadAll();
  }, [configId, tenantId]);

  const loadAll = async () => {
    setLoading(true);
    await Promise.all([
      loadLayerLicenses(),
      loadCascadeStatus(),
      loadFeedbackSignals(),
    ]);
    setLoading(false);
  };

  const loadLayerLicenses = async () => {
    if (!tenantId) return;
    try {
      const data = await getLayerLicenses(tenantId);
      const modes = {};
      let tier = null;
      for (const [key, val] of Object.entries(data.layers || {})) {
        modes[key] = val.mode;
        if (val.package_tier) tier = val.package_tier;
      }
      setLayerModes(modes);
      setPackageTier(tier);
    } catch (error) {
      console.error('Failed to load layer licenses', error);
      // Default: execution active, rest input
      setLayerModes({
        sop: 'input', mps: 'input', supply_agent: 'input',
        allocation_agent: 'input', execution: 'active',
      });
    }
  };

  const loadCascadeStatus = async () => {
    if (!configId) return;
    try {
      const data = await getCascadeStatus(configId);
      setCascadeStatus(data);
      if (data.allocation_commits?.length > 0) setActiveStep(3);
      else if (data.supply_commits?.length > 0) setActiveStep(2);
      else setActiveStep(0);
    } catch (error) {
      console.error('Failed to load cascade status', error);
    }
  };

  const loadFeedbackSignals = async () => {
    if (!configId) return;
    try {
      const data = await getFeedbackSignals(configId, { limit: 10 });
      setFeedbackSignals(data.signals || []);
    } catch (error) {
      console.error('Failed to load feedback signals', error);
    }
  };

  const handleRunCascade = async () => {
    try {
      setRunning(true);
      await api.post('/planning-cascade/cascade/run', {
        config_id: configId,
        tenant_id: tenantId,
        mode: isFullMode ? 'FULL' : 'INPUT',
      });
      setRunDialogOpen(false);
      loadAll();
    } catch (error) {
      console.error('Failed to run cascade', error);
    } finally {
      setRunning(false);
    }
  };

  const getStepStatus = (stepIndex) => {
    if (!cascadeStatus) return 'pending';
    switch (stepIndex) {
      case 0: return cascadeStatus.policy_envelope ? 'completed' : 'pending';
      case 1: return cascadeStatus.supply_baseline_pack ? 'completed' : 'pending';
      case 2: {
        const sc = cascadeStatus.supply_commits?.[0];
        if (!sc) return 'pending';
        if (sc.status === 'submitted') return 'completed';
        if (sc.requires_review) return 'review';
        return 'active';
      }
      case 3: {
        const ac = cascadeStatus.allocation_commits?.[0];
        if (!ac) return 'pending';
        if (ac.status === 'submitted') return 'completed';
        if (ac.requires_review) return 'review';
        return 'active';
      }
      case 4: return feedbackSignals.length > 0 ? 'active' : 'pending';
      default: return 'pending';
    }
  };

  const getStepIcon = (stepIndex) => {
    const status = getStepStatus(stepIndex);
    switch (status) {
      case 'completed': return <SuccessIcon color="success" />;
      case 'review': return <WarningIcon color="warning" />;
      case 'active': return <CircularProgress size={20} />;
      default: return CASCADE_STEPS[stepIndex].icon;
    }
  };

  const getLayerMode = (layerKey) => layerModes[layerKey] || 'input';

  const getPendingReviewCount = () => cascadeStatus?.pending_review_count || 0;

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={4}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5">Planning Cascade Dashboard</Typography>
          <Typography variant="body2" color="textSecondary">
            {isInputMode
              ? 'Customer provides parameters for non-purchased layers. Agents govern execution.'
              : 'Autonomy simulation optimizes all purchased layers.'}
          </Typography>
        </Box>
        <Box display="flex" gap={1} alignItems="center">
          {packageTier && (
            <Chip
              label={`${TIER_LABELS[packageTier] || packageTier} Package`}
              color="primary"
              variant="outlined"
            />
          )}
          {getPendingReviewCount() > 0 && (
            <Chip
              icon={<WarningIcon />}
              label={`${getPendingReviewCount()} Pending Review`}
              color="warning"
            />
          )}
          <Button
            variant="contained"
            startIcon={<RunIcon />}
            onClick={() => setRunDialogOpen(true)}
            disabled={running}
          >
            Run Cascade
          </Button>
          <IconButton onClick={loadAll}>
            <RefreshIcon />
          </IconButton>
        </Box>
      </Box>

      <Grid container spacing={3}>
        {/* Cascade Flow */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardHeader
              title="Cascade Flow"
              subheader="Feed-forward contracts link each layer"
              action={
                <Tooltip title="Each artifact is hash-linked to its upstream source">
                  <IconButton><TimelineIcon /></IconButton>
                </Tooltip>
              }
            />
            <CardContent>
              <Stepper activeStep={activeStep} orientation="vertical">
                {CASCADE_STEPS.map((step, index) => {
                  const mode = getLayerMode(step.layerKey);
                  return (
                    <Step key={step.label}>
                      <StepLabel
                        icon={getStepIcon(index)}
                        optional={
                          <Box display="flex" alignItems="center" gap={1}>
                            <Typography variant="caption" color="textSecondary">
                              {step.feedForward}
                            </Typography>
                            <LayerModeIndicator
                              layer={step.layerKey}
                              mode={mode}
                              showLabel={false}
                              size="small"
                            />
                            {index < CASCADE_STEPS.length - 1 && (
                              <ArrowIcon fontSize="small" color="action" />
                            )}
                          </Box>
                        }
                      >
                        <Typography
                          variant="subtitle1"
                          sx={{ cursor: 'pointer' }}
                          onClick={() => navigate(step.path)}
                        >
                          {step.label}
                        </Typography>
                      </StepLabel>
                      <StepContent>
                        <Typography variant="body2" color="textSecondary" paragraph>
                          {step.description}
                        </Typography>
                        <Box display="flex" gap={1}>
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => navigate(step.path)}
                          >
                            {mode === 'active' ? step.activeLabel : step.inputLabel}
                          </Button>
                          {getStepStatus(index) === 'review' && (
                            <Chip size="small" label="Needs Review" color="warning" />
                          )}
                          {mode === 'disabled' && (
                            <Chip size="small" label="Not Purchased" variant="outlined" />
                          )}
                        </Box>
                      </StepContent>
                    </Step>
                  );
                })}
              </Stepper>
            </CardContent>
          </Card>
        </Grid>

        {/* Status Summary */}
        <Grid item xs={12} md={4}>
          {/* Layer Status */}
          <Card sx={{ mb: 2 }}>
            <CardHeader title="Layer Status" />
            <CardContent>
              {LAYER_KEYS.map((key) => (
                <Box key={key} display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <LayerModeIndicator layer={key} mode={getLayerMode(key)} size="small" />
                </Box>
              ))}
            </CardContent>
          </Card>

          {/* Latest Commits */}
          <Card sx={{ mb: 2 }}>
            <CardHeader title="Latest Commits" />
            <CardContent>
              <List dense>
                {cascadeStatus?.supply_commits?.slice(0, 3).map((commit) => (
                  <ListItem key={commit.id}>
                    <ListItemIcon><ShippingIcon /></ListItemIcon>
                    <ListItemText
                      primary={`SC-${commit.hash}`}
                      secondary={new Date(commit.created_at).toLocaleString()}
                    />
                    <ListItemSecondaryAction>
                      <Chip
                        size="small"
                        label={commit.status}
                        color={
                          commit.status === 'submitted' ? 'success' :
                          commit.requires_review ? 'warning' : 'default'
                        }
                      />
                    </ListItemSecondaryAction>
                  </ListItem>
                ))}
                {cascadeStatus?.allocation_commits?.slice(0, 3).map((commit) => (
                  <ListItem key={commit.id}>
                    <ListItemIcon><CategoryIcon /></ListItemIcon>
                    <ListItemText
                      primary={`AC-${commit.hash}`}
                      secondary={new Date(commit.created_at).toLocaleString()}
                    />
                    <ListItemSecondaryAction>
                      <Chip
                        size="small"
                        label={commit.status}
                        color={
                          commit.status === 'submitted' ? 'success' :
                          commit.requires_review ? 'warning' : 'default'
                        }
                      />
                    </ListItemSecondaryAction>
                  </ListItem>
                ))}
              </List>
              {(!cascadeStatus?.supply_commits?.length && !cascadeStatus?.allocation_commits?.length) && (
                <Typography variant="body2" color="textSecondary" textAlign="center">
                  No commits yet. Run the cascade to generate.
                </Typography>
              )}
            </CardContent>
          </Card>

          {/* Feed-back Signals */}
          <Card>
            <CardHeader
              title="Feed-back Signals"
              subheader="Execution outcomes for re-tuning"
              action={
                <Tooltip title="Signals inform upstream parameter adjustments">
                  <BackArrowIcon color="action" />
                </Tooltip>
              }
            />
            <CardContent>
              {feedbackSignals.length > 0 ? (
                <List dense>
                  {feedbackSignals.slice(0, 5).map((signal, i) => (
                    <ListItem key={i}>
                      <ListItemIcon>
                        {signal.deviation && signal.deviation > 0.1 ? (
                          <WarningIcon color="warning" />
                        ) : (
                          <TrendingUpIcon color="info" />
                        )}
                      </ListItemIcon>
                      <ListItemText
                        primary={signal.signal_type}
                        secondary={`${signal.metric_name}: ${signal.metric_value?.toFixed(2)}${signal.threshold ? ` (target: ${signal.threshold})` : ''}`}
                      />
                      <ListItemSecondaryAction>
                        <Typography variant="caption" color="textSecondary">
                          → {signal.fed_back_to}
                        </Typography>
                      </ListItemSecondaryAction>
                    </ListItem>
                  ))}
                </List>
              ) : (
                <Typography variant="body2" color="textSecondary" textAlign="center">
                  No feed-back signals yet. Execute commits to generate.
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Quick Actions */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="Quick Actions" />
            <CardContent>
              <Grid container spacing={2}>
                {CASCADE_STEPS.map((step) => {
                  const mode = getLayerMode(step.layerKey);
                  return (
                    <Grid item xs={12} sm={6} md={2.4} key={step.layerKey}>
                      <Button
                        fullWidth
                        variant="outlined"
                        startIcon={step.icon}
                        onClick={() => navigate(step.path)}
                        disabled={mode === 'disabled'}
                        color={mode === 'active' ? 'primary' : 'inherit'}
                      >
                        {mode === 'active' ? step.activeLabel : step.inputLabel}
                      </Button>
                    </Grid>
                  );
                })}
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Run Cascade Dialog */}
      <Dialog open={runDialogOpen} onClose={() => setRunDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Run Planning Cascade</DialogTitle>
        <DialogContent>
          <Box py={2}>
            <Typography variant="body1" paragraph>
              This will run the planning cascade with your current layer configuration:
            </Typography>
            <List dense>
              {CASCADE_STEPS.map((step) => {
                const mode = getLayerMode(step.layerKey);
                return (
                  <ListItem key={step.layerKey}>
                    <ListItemIcon>{step.icon}</ListItemIcon>
                    <ListItemText primary={step.label} />
                    <ListItemSecondaryAction>
                      <Chip
                        size="small"
                        label={mode === 'active' ? 'AI' : mode === 'input' ? 'Manual' : 'Skip'}
                        color={mode === 'active' ? 'success' : mode === 'input' ? 'info' : 'default'}
                        variant="outlined"
                      />
                    </ListItemSecondaryAction>
                  </ListItem>
                );
              })}
            </List>
            <Alert severity="warning" sx={{ mt: 2 }}>
              Commits with integrity violations will be flagged for review.
              Risk flags will be marked for your attention.
            </Alert>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRunDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleRunCascade}
            disabled={running}
            startIcon={running ? <CircularProgress size={20} /> : <RunIcon />}
          >
            {running ? 'Running...' : 'Run Cascade'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default CascadeDashboard;
