/**
 * SAP Config Builder
 *
 * Step-by-step wizard for building a SupplyChainConfig from SAP data.
 * 9-step process: Setup → Validation → Geography → Sites → Products →
 * Lanes → Partners → BOM → Planning Data
 *
 * After each step the user can Stop, Continue to Next, or Continue to End.
 * Anomalies and Z-tables are shown per step with suggested actions.
 */

import React, { useState, useEffect, useCallback } from 'react';
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
  Alert,
  AlertTitle,
  Chip,
  Divider,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Collapse,
  IconButton,
  Switch,
  FormControlLabel,
} from '@mui/material';
import {
  Settings as SettingsIcon,
  VerifiedUser as VerifiedIcon,
  Map as MapIcon,
  Factory as FactoryIcon,
  Inventory as InventoryIcon,
  Route as RouteIcon,
  Handshake as HandshakeIcon,
  AccountTree as AccountTreeIcon,
  TrendingUp as TrendingUpIcon,
  ArrowBack as BackIcon,
  ArrowForward as NextIcon,
  PlayArrow as PlayIcon,
  Stop as StopIcon,
  FastForward as FastForwardIcon,
  CheckCircle as CheckIcon,
  Warning as WarningIcon,
  Error as ErrorIcon,
  Info as InfoIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Refresh as RefreshIcon,
  Delete as DeleteIcon,
} from '@mui/icons-material';
import { api } from '../../services/api';

const WIZARD_STEPS = [
  { key: 'setup', label: 'Connection & Setup' },
  { key: 'validate', label: 'Data Validation' },
  { key: 'geography', label: 'Geography' },
  { key: 'sites', label: 'Sites' },
  { key: 'products', label: 'Products' },
  { key: 'lanes', label: 'Transportation Lanes' },
  { key: 'partners', label: 'Partners & Sourcing' },
  { key: 'bom', label: 'BOM & Manufacturing' },
  { key: 'planning', label: 'Planning Data' },
];

const MASTER_TYPES = [
  { value: 'MANUFACTURER', label: 'Manufacturer' },
  { value: 'INVENTORY', label: 'Inventory (DC/Warehouse)' },
  { value: 'MARKET_SUPPLY', label: 'Market Supply (Vendor)' },
  { value: 'MARKET_DEMAND', label: 'Market Demand (Customer)' },
];

const INV_POLICY_TYPES = [
  { value: 'doc_dem', label: 'Days of Coverage (Demand)' },
  { value: 'doc_fcst', label: 'Days of Coverage (Forecast)' },
  { value: 'abs_level', label: 'Absolute Level' },
  { value: 'sl', label: 'Service Level' },
];

// Severity icon mapping
function SeverityIcon({ severity }) {
  switch (severity) {
    case 'error': return <ErrorIcon color="error" fontSize="small" />;
    case 'warning': return <WarningIcon color="warning" fontSize="small" />;
    default: return <InfoIcon color="info" fontSize="small" />;
  }
}

// Anomaly panel component
function AnomalyPanel({ anomalies }) {
  const [expanded, setExpanded] = useState(true);
  if (!anomalies || anomalies.length === 0) return null;

  const errorCount = anomalies.filter(a => a.severity === 'error').length;
  const warnCount = anomalies.filter(a => a.severity === 'warning').length;

  return (
    <Card variant="outlined" sx={{ mt: 2 }}>
      <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
          onClick={() => setExpanded(!expanded)}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <WarningIcon color="warning" fontSize="small" />
            <Typography variant="subtitle2">
              Anomalies & Suggestions
            </Typography>
            {errorCount > 0 && <Chip label={`${errorCount} errors`} size="small" color="error" />}
            {warnCount > 0 && <Chip label={`${warnCount} warnings`} size="small" color="warning" />}
          </Box>
          <IconButton size="small">{expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}</IconButton>
        </Box>
        <Collapse in={expanded}>
          <Box sx={{ mt: 1 }}>
            {anomalies.map((a, i) => (
              <Alert
                key={i}
                severity={a.severity === 'error' ? 'error' : a.severity === 'warning' ? 'warning' : 'info'}
                variant="outlined"
                sx={{ mb: 1 }}
                icon={<SeverityIcon severity={a.severity} />}
              >
                <AlertTitle sx={{ fontSize: '0.85rem' }}>{a.message}</AlertTitle>
                {a.suggested_action && (
                  <Typography variant="caption" color="text.secondary">
                    Suggestion: {a.suggested_action}
                  </Typography>
                )}
              </Alert>
            ))}
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  );
}

// Z-table panel component
function ZTablePanel({ zTables }) {
  const [expanded, setExpanded] = useState(true);
  if (!zTables || zTables.length === 0) return null;

  return (
    <Card variant="outlined" sx={{ mt: 2, borderColor: 'secondary.main' }}>
      <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
          onClick={() => setExpanded(!expanded)}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AccountTreeIcon color="secondary" fontSize="small" />
            <Typography variant="subtitle2">Z-Tables Detected ({zTables.length})</Typography>
          </Box>
          <IconButton size="small">{expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}</IconButton>
        </Box>
        <Collapse in={expanded}>
          <Table size="small" sx={{ mt: 1 }}>
            <TableHead>
              <TableRow>
                <TableCell>Table</TableCell>
                <TableCell>Rows</TableCell>
                <TableCell>Fields</TableCell>
                <TableCell>Suggested Entity</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {zTables.map((zt, i) => (
                <TableRow key={i}>
                  <TableCell sx={{ fontFamily: 'monospace', fontWeight: 600 }}>{zt.table_name}</TableCell>
                  <TableCell>{zt.row_count}</TableCell>
                  <TableCell>{zt.field_count}</TableCell>
                  <TableCell>
                    {zt.suggested_entity ? (
                      <Chip label={zt.suggested_entity} size="small" color="secondary" variant="outlined" />
                    ) : (
                      <Typography variant="caption" color="text.secondary">Unknown</Typography>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Collapse>
      </CardContent>
    </Card>
  );
}

// Sample data table
function SampleDataTable({ data, title }) {
  if (!data || data.length === 0) return null;
  const columns = Object.keys(data[0]);

  return (
    <Card variant="outlined" sx={{ mt: 2 }}>
      <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>{title || 'Sample Data'}</Typography>
        <Table size="small">
          <TableHead>
            <TableRow>
              {columns.map(col => (
                <TableCell key={col} sx={{ fontWeight: 600, fontSize: '0.75rem' }}>
                  {col}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {data.map((row, i) => (
              <TableRow key={i}>
                {columns.map(col => (
                  <TableCell key={col} sx={{ fontSize: '0.75rem' }}>
                    {String(row[col] ?? '')}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}


export default function SAPConfigBuilder() {
  const [activeStep, setActiveStep] = useState(0);
  const [configId, setConfigId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Connection state
  const [connections, setConnections] = useState([]);
  const [loadingConnections, setLoadingConnections] = useState(true);

  // Form state
  const [formData, setFormData] = useState({
    connection_id: '',
    config_name: 'SAP Import',
    company_filter: '',
    plant_filter: '',
  });

  // Step results (indexed by step number)
  const [stepResults, setStepResults] = useState({});
  const [completedSteps, setCompletedSteps] = useState([]);

  // Site master type overrides (step 3)
  const [masterTypeOverrides, setMasterTypeOverrides] = useState({});

  // Planning options (step 8)
  const [planningOptions, setPlanningOptions] = useState({
    include_forecasts: true,
    include_inventory: true,
    forecast_horizon_weeks: 52,
    default_inv_policy: 'doc_dem',
    default_safety_days: 14,
  });

  // Fetch connections on mount
  useEffect(() => {
    const fetchConnections = async () => {
      try {
        const res = await api.get('/v1/sap-data/connections');
        setConnections(res.data.connections || []);
      } catch (err) {
        console.error('Failed to load connections:', err);
      }
      setLoadingConnections(false);
    };
    fetchConnections();
  }, []);

  // Build the request body for step endpoints
  const buildStepRequest = useCallback(() => ({
    connection_id: formData.connection_id,
    company_filter: formData.company_filter || null,
    plant_filter: formData.plant_filter ? formData.plant_filter.split(',').map(s => s.trim()).filter(Boolean) : null,
    master_type_overrides: Object.keys(masterTypeOverrides).length > 0 ? masterTypeOverrides : null,
    options: planningOptions,
  }), [formData, masterTypeOverrides, planningOptions]);

  // Step 1: Start build
  const handleStartBuild = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post('/v1/sap-data/build-config/start', {
        connection_id: formData.connection_id,
        config_name: formData.config_name,
        company_filter: formData.company_filter || null,
        plant_filter: formData.plant_filter ? formData.plant_filter.split(',').map(s => s.trim()).filter(Boolean) : null,
      });
      const data = res.data;
      setConfigId(data.config_id);
      setStepResults(prev => ({ ...prev, 1: data }));
      setCompletedSteps(data.completed_steps || [1]);
      setActiveStep(1);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start build');
    }
    setLoading(false);
  };

  // Execute a single step
  const handleExecuteStep = async (stepNum) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post(
        `/v1/sap-data/build-config/${configId}/step/${stepNum}`,
        buildStepRequest(),
      );
      const data = res.data;
      setStepResults(prev => ({ ...prev, [stepNum]: data }));
      setCompletedSteps(data.completed_steps || []);
      setActiveStep(stepNum); // Stay on current step to show results
    } catch (err) {
      setError(err.response?.data?.detail || `Failed to execute step ${stepNum}`);
    }
    setLoading(false);
  };

  // Continue to next step
  const handleContinueNext = async () => {
    const nextStep = activeStep + 1;
    if (nextStep > 8) return;
    await handleExecuteStep(nextStep);
  };

  // Continue to end (run all remaining)
  const handleContinueToEnd = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post(
        `/v1/sap-data/build-config/${configId}/complete`,
        buildStepRequest(),
      );
      setCompletedSteps([1, 2, 3, 4, 5, 6, 7, 8]);
      setStepResults(prev => ({ ...prev, complete: res.data }));
      setActiveStep(8);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to complete build');
    }
    setLoading(false);
  };

  // Stop and go to summary
  const handleStop = () => {
    setActiveStep(8); // Jump to last step to show summary
  };

  // Delete build
  const handleDeleteBuild = async () => {
    if (!configId) return;
    try {
      await api.delete(`/v1/sap-data/build-config/${configId}`);
      setConfigId(null);
      setStepResults({});
      setCompletedSteps([]);
      setActiveStep(0);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete build');
    }
  };

  // Can proceed from step 0 (setup)?
  const canStartBuild = formData.connection_id && formData.config_name;

  // Current step result
  const currentResult = stepResults[activeStep] || null;

  // Render setup step (step 0)
  const renderSetup = () => (
    <Box>
      <Typography variant="h6" sx={{ mb: 2 }}>Connection & Setup</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Select an SAP connection and configure filters for the config build.
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} sm={6}>
          <FormControl fullWidth>
            <InputLabel>SAP Connection</InputLabel>
            <Select
              value={formData.connection_id}
              onChange={(e) => setFormData(prev => ({ ...prev, connection_id: e.target.value }))}
              label="SAP Connection"
            >
              {loadingConnections ? (
                <MenuItem disabled>Loading...</MenuItem>
              ) : connections.length === 0 ? (
                <MenuItem disabled>No connections configured</MenuItem>
              ) : (
                connections.map(c => (
                  <MenuItem key={c.id} value={c.id}>
                    {c.name} ({c.system_type} / {c.connection_method})
                  </MenuItem>
                ))
              )}
            </Select>
          </FormControl>
        </Grid>

        <Grid item xs={12} sm={6}>
          <TextField
            fullWidth
            label="Config Name"
            value={formData.config_name}
            onChange={(e) => setFormData(prev => ({ ...prev, config_name: e.target.value }))}
          />
        </Grid>

        <Grid item xs={12} sm={6}>
          <TextField
            fullWidth
            label="Company Filter (optional)"
            value={formData.company_filter}
            onChange={(e) => setFormData(prev => ({ ...prev, company_filter: e.target.value }))}
            placeholder="e.g. 1000"
            helperText="Filter by SAP company code"
          />
        </Grid>

        <Grid item xs={12} sm={6}>
          <TextField
            fullWidth
            label="Plant Filter (optional)"
            value={formData.plant_filter}
            onChange={(e) => setFormData(prev => ({ ...prev, plant_filter: e.target.value }))}
            placeholder="e.g. 1000, 2000, 3000"
            helperText="Comma-separated plant codes"
          />
        </Grid>
      </Grid>
    </Box>
  );

  // Render validation step (step 1)
  const renderValidation = () => {
    const result = stepResults[1];
    if (!result) return <CircularProgress />;

    return (
      <Box>
        <Typography variant="h6" sx={{ mb: 1 }}>Data Validation</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Config created (ID: {result.config_id}). Review available tables and detected issues.
        </Typography>

        {/* Table inventory */}
        <Card variant="outlined" sx={{ mb: 2 }}>
          <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Table Inventory ({(result.table_inventory || []).length} tables loaded)
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600 }}>Table</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Rows</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Columns</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(result.table_inventory || []).map((t, i) => (
                  <TableRow key={i}>
                    <TableCell sx={{ fontFamily: 'monospace', fontWeight: 600 }}>{t.table_name}</TableCell>
                    <TableCell>{t.row_count}</TableCell>
                    <TableCell>{(t.columns || []).length}</TableCell>
                    <TableCell>
                      {t.status === 'z_table' ? (
                        <Chip label="Z-Table" size="small" color="secondary" />
                      ) : t.status === 'custom' ? (
                        <Chip label="Custom" size="small" color="warning" variant="outlined" />
                      ) : (
                        <Chip label="Standard" size="small" color="success" variant="outlined" />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <AnomalyPanel anomalies={result.anomalies} />
        <ZTablePanel zTables={result.z_tables} />

        {result.warnings && result.warnings.length > 0 && (
          <Alert severity="warning" sx={{ mt: 2 }}>
            {result.warnings.map((w, i) => <div key={i}>{w}</div>)}
          </Alert>
        )}
      </Box>
    );
  };

  // Render a build step result (steps 2-8)
  const renderBuildStep = (stepNum) => {
    const result = stepResults[stepNum];
    const stepName = WIZARD_STEPS[stepNum]?.label || `Step ${stepNum}`;
    const isExecuted = completedSteps.includes(stepNum);

    if (!isExecuted && !loading) {
      return (
        <Box>
          <Typography variant="h6" sx={{ mb: 1 }}>{stepName}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            This step has not been executed yet. Click "Execute Step" to proceed.
          </Typography>

          {/* Step 3 special: master type override options */}
          {stepNum === 3 && stepResults[1] && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Site master types will be inferred from SAP data. You can override them after execution.
            </Alert>
          )}

          {/* Step 8 special: planning options */}
          {stepNum === 8 && renderPlanningOptions()}

          <Button
            variant="contained"
            startIcon={<PlayIcon />}
            onClick={() => handleExecuteStep(stepNum)}
            disabled={loading}
          >
            Execute Step
          </Button>
        </Box>
      );
    }

    if (loading && !result) {
      return (
        <Box sx={{ textAlign: 'center', py: 4 }}>
          <CircularProgress />
          <Typography sx={{ mt: 2 }}>Executing {stepName}...</Typography>
        </Box>
      );
    }

    if (!result) return null;

    return (
      <Box>
        <Typography variant="h6" sx={{ mb: 1 }}>{stepName}</Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
          <Chip
            icon={<CheckIcon />}
            label={`${result.entities_created} entities created`}
            color="success"
            size="small"
          />
          <Chip label={result.entity_type} size="small" variant="outlined" />
        </Box>

        {/* Step 3 special: editable master types */}
        {stepNum === 3 && result.sample_data && result.sample_data.length > 0 && (
          <Card variant="outlined" sx={{ mt: 2, mb: 2 }}>
            <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>Sites — Master Type Override</Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 600 }}>Key</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Name</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Inferred Type</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Override</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {result.sample_data.map((site, i) => (
                    <TableRow key={i}>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{site.key}</TableCell>
                      <TableCell>{site.name}</TableCell>
                      <TableCell>
                        <Chip label={site.master_type} size="small" />
                      </TableCell>
                      <TableCell>
                        <FormControl size="small" sx={{ minWidth: 180 }}>
                          <Select
                            value={masterTypeOverrides[site.key] || ''}
                            onChange={(e) => {
                              setMasterTypeOverrides(prev => {
                                const next = { ...prev };
                                if (e.target.value) {
                                  next[site.key] = e.target.value;
                                } else {
                                  delete next[site.key];
                                }
                                return next;
                              });
                            }}
                            displayEmpty
                          >
                            <MenuItem value="">
                              <em>Keep inferred</em>
                            </MenuItem>
                            {MASTER_TYPES.map(mt => (
                              <MenuItem key={mt.value} value={mt.value}>{mt.label}</MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {/* Normal sample data (non-site steps) */}
        {stepNum !== 3 && (
          <SampleDataTable data={result.sample_data} title="Sample Data" />
        )}

        <AnomalyPanel anomalies={result.anomalies} />
        <ZTablePanel zTables={result.z_tables} />

        {result.warnings && result.warnings.length > 0 && (
          <Alert severity="warning" sx={{ mt: 2 }}>
            {result.warnings.map((w, i) => <div key={i}>{w}</div>)}
          </Alert>
        )}
      </Box>
    );
  };

  // Planning options form (step 8)
  const renderPlanningOptions = () => (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="subtitle2" sx={{ mb: 2 }}>Planning Configuration</Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}>
            <FormControlLabel
              control={
                <Switch
                  checked={planningOptions.include_forecasts}
                  onChange={(e) => setPlanningOptions(prev => ({ ...prev, include_forecasts: e.target.checked }))}
                />
              }
              label="Include Forecasts"
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <FormControlLabel
              control={
                <Switch
                  checked={planningOptions.include_inventory}
                  onChange={(e) => setPlanningOptions(prev => ({ ...prev, include_inventory: e.target.checked }))}
                />
              }
              label="Include Inventory"
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <FormControl fullWidth size="small">
              <InputLabel>Inventory Policy Type</InputLabel>
              <Select
                value={planningOptions.default_inv_policy}
                onChange={(e) => setPlanningOptions(prev => ({ ...prev, default_inv_policy: e.target.value }))}
                label="Inventory Policy Type"
              >
                {INV_POLICY_TYPES.map(p => (
                  <MenuItem key={p.value} value={p.value}>{p.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField
              fullWidth
              size="small"
              type="number"
              label="Forecast Horizon (weeks)"
              value={planningOptions.forecast_horizon_weeks}
              onChange={(e) => setPlanningOptions(prev => ({ ...prev, forecast_horizon_weeks: parseInt(e.target.value) || 52 }))}
            />
          </Grid>
          <Grid item xs={12}>
            <Typography variant="caption" gutterBottom display="block">
              Safety Days: {planningOptions.default_safety_days}
            </Typography>
            <Slider
              value={planningOptions.default_safety_days}
              onChange={(_, val) => setPlanningOptions(prev => ({ ...prev, default_safety_days: val }))}
              min={0}
              max={60}
              step={1}
              marks={[
                { value: 0, label: '0' },
                { value: 14, label: '14' },
                { value: 30, label: '30' },
                { value: 60, label: '60' },
              ]}
            />
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );

  // Step controls (shown after each completed step 1-7)
  const renderStepControls = () => {
    if (activeStep < 1 || activeStep >= 8) return null;
    const nextStep = activeStep + 1;
    const hasResult = stepResults[activeStep];

    if (!hasResult) return null;

    return (
      <Box sx={{ display: 'flex', gap: 2, mt: 3, justifyContent: 'space-between' }}>
        <Button
          variant="outlined"
          color="inherit"
          startIcon={<StopIcon />}
          onClick={handleStop}
        >
          Stop Here
        </Button>
        <Box sx={{ display: 'flex', gap: 2 }}>
          {nextStep <= 8 && (
            <Button
              variant="contained"
              startIcon={<NextIcon />}
              onClick={handleContinueNext}
              disabled={loading}
            >
              Continue to {WIZARD_STEPS[nextStep]?.label || `Step ${nextStep}`}
            </Button>
          )}
          <Button
            variant="contained"
            color="secondary"
            startIcon={<FastForwardIcon />}
            onClick={handleContinueToEnd}
            disabled={loading}
          >
            Continue to End
          </Button>
        </Box>
      </Box>
    );
  };

  // Render active step content
  const renderStepContent = () => {
    if (activeStep === 0) return renderSetup();
    if (activeStep === 1) return renderValidation();
    return renderBuildStep(activeStep);
  };

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h5">SAP Config Builder</Typography>
          <Typography variant="body2" color="text.secondary">
            Build a SupplyChainConfig from SAP data step-by-step
          </Typography>
        </Box>
        {configId && (
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Chip label={`Config #${configId}`} color="primary" size="small" />
            <Button
              variant="outlined"
              color="error"
              size="small"
              startIcon={<DeleteIcon />}
              onClick={handleDeleteBuild}
            >
              Cancel Build
            </Button>
          </Box>
        )}
      </Box>

      {/* Stepper */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Stepper activeStep={activeStep} alternativeLabel>
          {WIZARD_STEPS.map((step, index) => (
            <Step key={step.key} completed={
              index === 0 ? configId != null :
              completedSteps.includes(index)
            }>
              <StepLabel
                onClick={() => {
                  // Allow clicking on completed steps to review
                  if (index === 0 || completedSteps.includes(index) || index === activeStep) {
                    setActiveStep(index);
                  }
                }}
                sx={{ cursor: (index === 0 || completedSteps.includes(index)) ? 'pointer' : 'default' }}
              >
                {step.label}
              </StepLabel>
            </Step>
          ))}
        </Stepper>
      </Paper>

      {/* Error display */}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Step content */}
      <Paper sx={{ p: 3 }}>
        {renderStepContent()}

        {/* Navigation for step 0 */}
        {activeStep === 0 && (
          <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 3 }}>
            <Button
              variant="contained"
              startIcon={loading ? <CircularProgress size={20} /> : <PlayIcon />}
              onClick={handleStartBuild}
              disabled={!canStartBuild || loading}
            >
              Validate & Start Build
            </Button>
          </Box>
        )}

        {/* Step controls for steps 1-7 */}
        {renderStepControls()}

        {/* Summary for step 8 (final) */}
        {activeStep === 8 && completedSteps.includes(8) && stepResults.complete && (
          <Box sx={{ mt: 3 }}>
            <Alert severity="success">
              <AlertTitle>Build Complete</AlertTitle>
              Config "{stepResults.complete.config_name}" (ID: {stepResults.complete.config_id}) created successfully.
            </Alert>
            {stepResults.complete.summary && (
              <Card variant="outlined" sx={{ mt: 2 }}>
                <CardContent>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>Summary</Typography>
                  <Table size="small">
                    <TableBody>
                      {Object.entries(stepResults.complete.summary).map(([key, val]) => (
                        <TableRow key={key}>
                          <TableCell sx={{ fontWeight: 600 }}>{key}</TableCell>
                          <TableCell>{String(val)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            )}
          </Box>
        )}
      </Paper>
    </Box>
  );
}
