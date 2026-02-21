/**
 * Demo System Builder
 *
 * MUI Stepper wizard for the 7-step deployment pipeline:
 *   1. Config Template selection
 *   2. Simulation parameters
 *   3. Training configuration
 *   4. SAP Export options
 *   5. Review summary
 *   6. Execute pipeline (live progress)
 *   7. Results & downloads
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box,
  Paper,
  Typography,
  Button,
  Stepper,
  Step,
  StepLabel,
  Card,
  CardContent,
  Grid,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Slider,
  Switch,
  FormControlLabel,
  Alert,
  AlertTitle,
  LinearProgress,
  Chip,
  Divider,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableRow,
} from '@mui/material';
import {
  PlayArrow as PlayIcon,
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  Schedule as PendingIcon,
  Refresh as RefreshIcon,
  Download as DownloadIcon,
  ArrowBack as BackIcon,
  ArrowForward as NextIcon,
  Settings as SettingsIcon,
} from '@mui/icons-material';
import { api } from '../../services/api';

const WIZARD_STEPS = [
  { key: 'config', label: 'Config Template' },
  { key: 'simulation', label: 'Simulation' },
  { key: 'training', label: 'Training' },
  { key: 'export', label: 'SAP Export' },
  { key: 'review', label: 'Review' },
  { key: 'execute', label: 'Execute' },
  { key: 'results', label: 'Results' },
];

const PIPELINE_STEPS = {
  1: 'Seed Config',
  2: 'Deterministic Simulation',
  3: 'Stochastic Monte Carlo',
  4: 'Convert Training Data',
  5: 'Train Models',
  6: 'Generate Day 1 CSVs',
  7: 'Generate Day 2 CSVs',
};

const DAY2_PROFILES = [
  { value: 'mixed', label: 'Mixed (All Disruptions)', description: 'Demand spike + lead time delay + rush orders + inventory shrink' },
  { value: 'demand_spike', label: 'Demand Spike', description: '40% demand increase for selected customers' },
  { value: 'lead_time_delay', label: 'Lead Time Delay', description: 'Extended lead times for selected suppliers' },
  { value: 'rush_orders', label: 'Rush Orders', description: 'High-priority urgent orders' },
  { value: 'inventory_shrink', label: 'Inventory Shrink', description: 'Reduced inventory at selected locations' },
];

export default function DemoSystemBuilder() {
  const [activeStep, setActiveStep] = useState(0);
  const [pipelineId, setPipelineId] = useState(null);
  const [pipelineData, setPipelineData] = useState(null);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  // Form state
  const [config, setConfig] = useState({
    config_template: 'Food Distribution',
    periods: 52,
    monte_carlo_runs: 128,
    epochs: 50,
    device: 'cpu',
    seed: 42,
    demand_noise_cv: 0.15,
    day2_profile: 'mixed',
  });

  // Poll pipeline status
  const pollStatus = useCallback(async () => {
    if (!pipelineId) return;
    try {
      const res = await api.get(`/v1/deployment/pipelines/${pipelineId}`);
      setPipelineData(res.data);
      if (res.data.status === 'completed') {
        setPolling(false);
        setActiveStep(6); // Results step
      } else if (res.data.status === 'failed' || res.data.status === 'cancelled') {
        setPolling(false);
      }
    } catch (err) {
      console.error('Poll error:', err);
    }
  }, [pipelineId]);

  useEffect(() => {
    if (polling && pipelineId) {
      pollRef.current = setInterval(pollStatus, 2000);
      return () => clearInterval(pollRef.current);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [polling, pipelineId, pollStatus]);

  const handleStartPipeline = async () => {
    setError(null);
    try {
      const res = await api.post('/v1/deployment/pipelines', config);
      setPipelineId(res.data.id);
      setPipelineData(res.data);
      setPolling(true);
      setActiveStep(5); // Execute step
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start pipeline');
    }
  };

  const handleCancel = async () => {
    if (!pipelineId) return;
    try {
      await api.post(`/v1/deployment/pipelines/${pipelineId}/cancel`);
      setPolling(false);
      await pollStatus();
    } catch (err) {
      console.error('Cancel error:', err);
    }
  };

  const handleDownload = async (csvType) => {
    try {
      const res = await api.get(`/v1/deployment/csvs/${pipelineId}/${csvType}`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${csvType}_sap_csvs.zip`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      setError(`Download failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  const canProceed = () => {
    switch (activeStep) {
      case 0: return config.config_template.length > 0;
      case 1: return config.periods >= 4 && config.monte_carlo_runs >= 1;
      case 2: return config.epochs >= 1;
      case 3: return config.day2_profile.length > 0;
      case 4: return true; // Review
      default: return false;
    }
  };

  // Step content renderers
  const renderConfigStep = () => (
    <Box sx={{ maxWidth: 600, mx: 'auto' }}>
      <Typography variant="h6" gutterBottom>Select Config Template</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Choose a supply chain topology to deploy. The pipeline will create or load the configuration,
        then simulate, train, and export SAP-format data.
      </Typography>
      <FormControl fullWidth sx={{ mb: 2 }}>
        <InputLabel>Config Template</InputLabel>
        <Select
          value={config.config_template}
          label="Config Template"
          onChange={(e) => setConfig({ ...config, config_template: e.target.value })}
        >
          <MenuItem value="Food Distribution">Food Distribution (21 sites, 25 products)</MenuItem>
          <MenuItem value="Default TBG" disabled>Default TBG (4 sites) - Coming Soon</MenuItem>
        </Select>
      </FormControl>
      <Card variant="outlined" sx={{ mt: 2 }}>
        <CardContent>
          <Typography variant="subtitle2" gutterBottom>Food Distribution Network</Typography>
          <Typography variant="body2" color="text.secondary">
            Hub-and-spoke topology: 1 Distribution Center, 10 Suppliers, 10 Customers.
            25 food products across 5 categories (dairy, produce, frozen, bakery, beverages).
            Realistic lead times, costs, and demand patterns.
          </Typography>
          <Box sx={{ mt: 1, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            <Chip label="21 Sites" size="small" color="primary" variant="outlined" />
            <Chip label="25 Products" size="small" color="primary" variant="outlined" />
            <Chip label="20 Lanes" size="small" color="primary" variant="outlined" />
            <Chip label="Hub & Spoke" size="small" color="primary" variant="outlined" />
          </Box>
        </CardContent>
      </Card>
    </Box>
  );

  const renderSimulationStep = () => (
    <Box sx={{ maxWidth: 600, mx: 'auto' }}>
      <Typography variant="h6" gutterBottom>Simulation Parameters</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Configure deterministic and stochastic (Monte Carlo) simulation runs.
      </Typography>
      <Grid container spacing={3}>
        <Grid item xs={6}>
          <TextField
            fullWidth
            label="Periods (weeks)"
            type="number"
            value={config.periods}
            onChange={(e) => setConfig({ ...config, periods: parseInt(e.target.value) || 52 })}
            inputProps={{ min: 4, max: 104 }}
            helperText="Deterministic simulation horizon"
          />
        </Grid>
        <Grid item xs={6}>
          <TextField
            fullWidth
            label="Monte Carlo Runs"
            type="number"
            value={config.monte_carlo_runs}
            onChange={(e) => setConfig({ ...config, monte_carlo_runs: parseInt(e.target.value) || 128 })}
            inputProps={{ min: 1, max: 1000 }}
            helperText="Stochastic runs for uncertainty"
          />
        </Grid>
        <Grid item xs={6}>
          <TextField
            fullWidth
            label="Random Seed"
            type="number"
            value={config.seed}
            onChange={(e) => setConfig({ ...config, seed: parseInt(e.target.value) || 42 })}
            helperText="For reproducibility"
          />
        </Grid>
        <Grid item xs={6}>
          <Typography variant="body2" gutterBottom>
            Demand Noise CV: {config.demand_noise_cv.toFixed(2)}
          </Typography>
          <Slider
            value={config.demand_noise_cv}
            onChange={(_, v) => setConfig({ ...config, demand_noise_cv: v })}
            min={0}
            max={0.5}
            step={0.01}
            valueLabelDisplay="auto"
          />
          <Typography variant="caption" color="text.secondary">
            Coefficient of variation for demand noise
          </Typography>
        </Grid>
      </Grid>
    </Box>
  );

  const renderTrainingStep = () => (
    <Box sx={{ maxWidth: 600, mx: 'auto' }}>
      <Typography variant="h6" gutterBottom>Training Configuration</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Configure model training for S&OP GraphSAGE, Execution tGNN, and 11 narrow TRMs.
      </Typography>
      <Grid container spacing={3}>
        <Grid item xs={6}>
          <TextField
            fullWidth
            label="Training Epochs"
            type="number"
            value={config.epochs}
            onChange={(e) => setConfig({ ...config, epochs: parseInt(e.target.value) || 50 })}
            inputProps={{ min: 1, max: 500 }}
            helperText="Epochs for GNN training"
          />
        </Grid>
        <Grid item xs={6}>
          <FormControl fullWidth>
            <InputLabel>Device</InputLabel>
            <Select
              value={config.device}
              label="Device"
              onChange={(e) => setConfig({ ...config, device: e.target.value })}
            >
              <MenuItem value="cpu">CPU</MenuItem>
              <MenuItem value="cuda">GPU (CUDA)</MenuItem>
            </Select>
          </FormControl>
        </Grid>
      </Grid>
      <Card variant="outlined" sx={{ mt: 3 }}>
        <CardContent>
          <Typography variant="subtitle2" gutterBottom>Training Pipeline</Typography>
          <Typography variant="body2" color="text.secondary">
            1. S&OP GraphSAGE: Network structure analysis and criticality scoring<br />
            2. Execution tGNN: Priority allocation generation with S&OP embeddings<br />
            3. Narrow TRMs: Behavioral cloning from heuristic decisions (11 agent types)
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );

  const renderExportStep = () => (
    <Box sx={{ maxWidth: 600, mx: 'auto' }}>
      <Typography variant="h6" gutterBottom>SAP CSV Export</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Configure Day 2 scenario profile for delta CSV generation.
        Day 1 CSVs (full master data + current state) are always generated.
      </Typography>
      <FormControl fullWidth sx={{ mb: 3 }}>
        <InputLabel>Day 2 Scenario Profile</InputLabel>
        <Select
          value={config.day2_profile}
          label="Day 2 Scenario Profile"
          onChange={(e) => setConfig({ ...config, day2_profile: e.target.value })}
        >
          {DAY2_PROFILES.map((p) => (
            <MenuItem key={p.value} value={p.value}>{p.label}</MenuItem>
          ))}
        </Select>
      </FormControl>
      {DAY2_PROFILES.filter(p => p.value === config.day2_profile).map(p => (
        <Alert key={p.value} severity="info" sx={{ mb: 2 }}>
          <AlertTitle>{p.label}</AlertTitle>
          {p.description}
        </Alert>
      ))}
      <Card variant="outlined">
        <CardContent>
          <Typography variant="subtitle2" gutterBottom>SAP Tables Generated (19)</Typography>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            {['MARA', 'MARC', 'MARD', 'T001W', 'LFA1', 'KNA1', 'STPO', 'EKKO', 'EKPO',
              'VBAK', 'VBAP', 'LIKP', 'LIPS', 'AFKO', 'AFPO', 'EKET', 'RESB',
              '/SAPAPO/LOC', '/SAPAPO/SNPFC'].map(t => (
              <Chip key={t} label={t} size="small" variant="outlined" />
            ))}
          </Box>
        </CardContent>
      </Card>
    </Box>
  );

  const renderReviewStep = () => (
    <Box sx={{ maxWidth: 600, mx: 'auto' }}>
      <Typography variant="h6" gutterBottom>Review Configuration</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Verify settings before starting the pipeline. Execution may take several minutes.
      </Typography>
      <Card variant="outlined">
        <Table size="small">
          <TableBody>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Config Template</TableCell>
              <TableCell>{config.config_template}</TableCell>
            </TableRow>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Simulation Periods</TableCell>
              <TableCell>{config.periods} weeks</TableCell>
            </TableRow>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Monte Carlo Runs</TableCell>
              <TableCell>{config.monte_carlo_runs} runs</TableCell>
            </TableRow>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Demand Noise CV</TableCell>
              <TableCell>{config.demand_noise_cv}</TableCell>
            </TableRow>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Training Epochs</TableCell>
              <TableCell>{config.epochs}</TableCell>
            </TableRow>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Device</TableCell>
              <TableCell>{config.device.toUpperCase()}</TableCell>
            </TableRow>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Random Seed</TableCell>
              <TableCell>{config.seed}</TableCell>
            </TableRow>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Day 2 Profile</TableCell>
              <TableCell>{DAY2_PROFILES.find(p => p.value === config.day2_profile)?.label}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </Card>
      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}
    </Box>
  );

  const renderExecuteStep = () => {
    if (!pipelineData) {
      return (
        <Box sx={{ textAlign: 'center', py: 4 }}>
          <CircularProgress />
          <Typography sx={{ mt: 2 }}>Starting pipeline...</Typography>
        </Box>
      );
    }

    const { status, current_step, total_steps, step_statuses, error_message } = pipelineData;
    const progress = total_steps > 0 ? (current_step / total_steps) * 100 : 0;

    return (
      <Box sx={{ maxWidth: 700, mx: 'auto' }}>
        <Typography variant="h6" gutterBottom>Pipeline Execution</Typography>

        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="body2">
              Step {current_step} of {total_steps}
            </Typography>
            <Chip
              label={status}
              size="small"
              color={
                status === 'completed' ? 'success' :
                status === 'running' ? 'primary' :
                status === 'failed' ? 'error' :
                'default'
              }
            />
          </Box>
          <LinearProgress
            variant="determinate"
            value={progress}
            sx={{ height: 8, borderRadius: 4 }}
          />
        </Box>

        {error_message && (
          <Alert severity="error" sx={{ mb: 2 }}>
            <AlertTitle>Pipeline Failed</AlertTitle>
            {error_message}
          </Alert>
        )}

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {Object.entries(PIPELINE_STEPS).map(([stepNum, stepName]) => {
            const stepInfo = (step_statuses || {})[stepNum] || {};
            const stepStatus = stepInfo.status || 'pending';
            const isActive = parseInt(stepNum) === current_step && status === 'running';

            return (
              <Card
                key={stepNum}
                variant="outlined"
                sx={{
                  borderColor: isActive ? 'primary.main' : undefined,
                  bgcolor: stepStatus === 'completed' ? 'success.50' :
                           stepStatus === 'failed' ? 'error.50' : undefined,
                }}
              >
                <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {stepStatus === 'completed' ? (
                      <CheckIcon fontSize="small" color="success" />
                    ) : stepStatus === 'failed' ? (
                      <ErrorIcon fontSize="small" color="error" />
                    ) : isActive ? (
                      <CircularProgress size={18} />
                    ) : (
                      <PendingIcon fontSize="small" color="disabled" />
                    )}
                    <Typography variant="body2" sx={{ fontWeight: isActive ? 600 : 400, flex: 1 }}>
                      Step {stepNum}: {stepName}
                    </Typography>
                    {stepInfo.elapsed && (
                      <Typography variant="caption" color="text.secondary">
                        {stepInfo.elapsed.toFixed(1)}s
                      </Typography>
                    )}
                  </Box>
                  {stepInfo.details && (
                    <Typography variant="caption" color="text.secondary" sx={{ ml: 4 }}>
                      {typeof stepInfo.details === 'string'
                        ? stepInfo.details
                        : JSON.stringify(stepInfo.details)}
                    </Typography>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </Box>

        {status === 'running' && (
          <Box sx={{ mt: 2, textAlign: 'center' }}>
            <Button variant="outlined" color="error" onClick={handleCancel}>
              Cancel Pipeline
            </Button>
          </Box>
        )}
      </Box>
    );
  };

  const renderResultsStep = () => {
    if (!pipelineData) return null;

    const { results, status } = pipelineData;

    return (
      <Box sx={{ maxWidth: 700, mx: 'auto' }}>
        <Alert severity="success" sx={{ mb: 3 }}>
          <AlertTitle>Pipeline Completed</AlertTitle>
          All 7 steps finished successfully. Download your SAP CSV files below.
        </Alert>

        <Grid container spacing={2}>
          <Grid item xs={6}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="subtitle2" gutterBottom>Day 1 CSVs</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Full master data + current state. All 19 SAP tables.
                </Typography>
                <Button
                  variant="contained"
                  startIcon={<DownloadIcon />}
                  onClick={() => handleDownload('day1')}
                  fullWidth
                >
                  Download Day 1 ZIP
                </Button>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={6}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="subtitle2" gutterBottom>Day 2 CSVs</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Delta records with disruptions to trigger CDC.
                </Typography>
                <Button
                  variant="contained"
                  startIcon={<DownloadIcon />}
                  onClick={() => handleDownload('day2')}
                  fullWidth
                >
                  Download Day 2 ZIP
                </Button>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {results && Object.keys(results).length > 0 && (
          <Card variant="outlined" sx={{ mt: 3 }}>
            <CardContent>
              <Typography variant="subtitle2" gutterBottom>Pipeline Results</Typography>
              <Table size="small">
                <TableBody>
                  {results.config_id && (
                    <TableRow>
                      <TableCell sx={{ fontWeight: 600 }}>Config ID</TableCell>
                      <TableCell>{results.config_id}</TableCell>
                    </TableRow>
                  )}
                  {results.step_2 && (
                    <TableRow>
                      <TableCell sx={{ fontWeight: 600 }}>Deterministic Sim</TableCell>
                      <TableCell>
                        {results.step_2.strategies?.length || 0} strategies,{' '}
                        Fill rate: {((results.step_2.avg_fill_rate || 0) * 100).toFixed(1)}%
                      </TableCell>
                    </TableRow>
                  )}
                  {results.step_3 && (
                    <TableRow>
                      <TableCell sx={{ fontWeight: 600 }}>Monte Carlo</TableCell>
                      <TableCell>
                        {results.step_3.total_runs || 0} runs completed
                      </TableCell>
                    </TableRow>
                  )}
                  {results.step_5 && (
                    <TableRow>
                      <TableCell sx={{ fontWeight: 600 }}>Training</TableCell>
                      <TableCell>
                        Models trained: {results.step_5.models_trained?.join(', ') || 'N/A'}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        <Box sx={{ mt: 3, textAlign: 'center' }}>
          <Button
            variant="outlined"
            onClick={() => {
              setPipelineId(null);
              setPipelineData(null);
              setActiveStep(0);
              setError(null);
            }}
          >
            Start New Pipeline
          </Button>
        </Box>
      </Box>
    );
  };

  const stepRenderers = [
    renderConfigStep,
    renderSimulationStep,
    renderTrainingStep,
    renderExportStep,
    renderReviewStep,
    renderExecuteStep,
    renderResultsStep,
  ];

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: 'auto' }}>
      <Typography variant="h5" gutterBottom>
        Demo System Builder
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Build a complete demo environment: simulate supply chain operations, train AI agents,
        and export SAP-format CSV files for deployment.
      </Typography>

      <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
        {WIZARD_STEPS.map((step) => (
          <Step key={step.key}>
            <StepLabel>{step.label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      <Paper sx={{ p: 3, mb: 3 }}>
        {stepRenderers[activeStep]()}
      </Paper>

      {activeStep < 5 && (
        <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
          <Button
            disabled={activeStep === 0}
            onClick={() => setActiveStep((s) => s - 1)}
            startIcon={<BackIcon />}
          >
            Back
          </Button>
          {activeStep === 4 ? (
            <Button
              variant="contained"
              color="primary"
              onClick={handleStartPipeline}
              startIcon={<PlayIcon />}
            >
              Start Pipeline
            </Button>
          ) : (
            <Button
              variant="contained"
              disabled={!canProceed()}
              onClick={() => setActiveStep((s) => s + 1)}
              endIcon={<NextIcon />}
            >
              Next
            </Button>
          )}
        </Box>
      )}
    </Box>
  );
}
