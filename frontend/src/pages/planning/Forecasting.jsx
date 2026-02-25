import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Alert,
  Badge,
  Label,
  Input,
  Spinner,
  Progress,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../../components/common';
import {
  Play,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Clock,
  TrendingUp,
  GitBranch,
  BarChart3,
  Upload,
  Eye,
  Plus,
  Pencil,
  Save,
  X,
  Info,
  Database,
  Filter,
  Cpu,
} from 'lucide-react';
import { api } from '../../services/api';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BUCKET_LABELS = { D: 'Daily', W: 'Weekly', M: 'Monthly' };
const TIME_BUCKETS = [
  { value: 'D', label: 'Daily' },
  { value: 'W', label: 'Weekly' },
  { value: 'M', label: 'Monthly' },
];
const CLUSTER_METHODS = [
  'KMeans', 'HDBSCAN', 'Agglomerative', 'OPTICS', 'Birch',
  'GaussianMixture', 'MeanShift', 'Spectral', 'AffinityPropagation',
];
const FEATURE_IMPORTANCE_METHODS = ['LassoCV', 'RandomForest', 'MutualInformation'];
const CHAR_CREATION_METHODS = ['tsfresh', 'classifier', 'both'];
const FORECAST_METRICS = ['wape', 'mae', 'rmse'];

const FORM_DEFAULTS = {
  name: '',
  description: '',
  time_bucket: 'W',
  forecast_horizon: 8,
  forecast_metric: 'wape',
  model_type: 'clustered_naive',
  demand_item: '',
  demand_point: '',
  target_column: '',
  date_column: '',
  number_of_items_analyzed: '',
  min_observations: 12,
  ignore_numeric_columns: '',
  cv_sq_threshold: 0.49,
  adi_threshold: 1.32,
  min_clusters: 2,
  max_clusters: 8,
  min_cluster_size: 5,
  min_cluster_size_uom: 'items',
  cluster_selection_method: 'KMeans',
  characteristics_creation_method: 'tsfresh',
  feature_correlation_threshold: 0.8,
  feature_importance_method: 'LassoCV',
  feature_importance_threshold: 0.01,
  pca_variance_threshold: 0.95,
  pca_importance_threshold: 0.01,
};

const RUN_POLL_INTERVAL = 3000;

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

const InfoTip = ({ text }) => (
  <TooltipProvider delayDuration={200}>
    <Tooltip>
      <TooltipTrigger asChild>
        <Info className="h-3.5 w-3.5 text-muted-foreground ml-1 inline cursor-help" />
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs text-xs">{text}</TooltipContent>
    </Tooltip>
  </TooltipProvider>
);

const FieldLabel = ({ children, tip }) => (
  <Label className="flex items-center text-xs font-medium">
    {children}
    {tip && <InfoTip text={tip} />}
  </Label>
);

const NumberInput = ({ value, onChange, ...props }) => (
  <Input
    type="number"
    className="mt-1 h-8 text-sm"
    value={value}
    onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
    {...props}
  />
);

const getStatusVariant = (status) => {
  const s = (status || '').toLowerCase();
  if (s === 'completed' || s === 'published') return 'success';
  if (s === 'failed') return 'destructive';
  if (s === 'running') return 'warning';
  if (s === 'pending') return 'secondary';
  return 'secondary';
};

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

const Forecasting = () => {
  // -- Supply chain config selector --
  const [scConfigs, setScConfigs] = useState([]);
  const [selectedScConfig, setSelectedScConfig] = useState('');

  // -- Pipeline configs --
  const [pipelineConfigs, setPipelineConfigs] = useState([]);
  const [selectedPipelineId, setSelectedPipelineId] = useState('');

  // -- Pipeline runs --
  const [runs, setRuns] = useState([]);
  const [activeRunId, setActiveRunId] = useState(null);
  const [activeRunStatus, setActiveRunStatus] = useState(null);
  const [polling, setPolling] = useState(false);

  // -- Config form --
  const [showForm, setShowForm] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ ...FORM_DEFAULTS });

  // -- UI state --
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // -- Derived --
  const scConfigId = selectedScConfig ? Number(selectedScConfig) : null;
  const pipelineId = selectedPipelineId ? Number(selectedPipelineId) : null;

  const activePipeline = useMemo(
    () => pipelineConfigs.find((c) => String(c.id) === selectedPipelineId),
    [pipelineConfigs, selectedPipelineId],
  );

  // -----------------------------------------------------------------------
  // Data loading
  // -----------------------------------------------------------------------

  const loadScConfigs = useCallback(async () => {
    try {
      const res = await api.get('/supply-chain-config/');
      const items = res.data.items || res.data || [];
      setScConfigs(items);
      if (items.length > 0 && !selectedScConfig) {
        const root =
          items.find((c) => !c.parent_config_id && c.scenario_type === 'BASELINE') ||
          items.find((c) => c.is_active) ||
          items[0];
        setSelectedScConfig(String(root.id));
      }
    } catch (err) {
      console.error('Failed to load SC configs:', err);
      setError('Failed to load supply chain configurations.');
    }
  }, [selectedScConfig]);

  const loadPipelineConfigs = useCallback(async () => {
    if (!scConfigId) { setPipelineConfigs([]); return; }
    try {
      const res = await api.get('/forecast-pipeline/configs', { params: { config_id: scConfigId } });
      const items = res.data || [];
      setPipelineConfigs(items);
      if (items.length > 0 && !selectedPipelineId) {
        const active = items.find((c) => c.is_active) || items[0];
        setSelectedPipelineId(String(active.id));
      } else if (items.length === 0) {
        setSelectedPipelineId('');
      }
    } catch {
      setPipelineConfigs([]);
    }
  }, [scConfigId, selectedPipelineId]);

  const loadRuns = useCallback(async () => {
    if (!pipelineId) { setRuns([]); return; }
    try {
      const res = await api.get('/forecast-pipeline/runs', { params: { pipeline_config_id: pipelineId } });
      setRuns(res.data || []);
    } catch {
      setRuns([]);
    }
  }, [pipelineId]);

  useEffect(() => { loadScConfigs(); }, [loadScConfigs]);
  useEffect(() => { loadPipelineConfigs(); }, [scConfigId]);
  useEffect(() => { loadRuns(); }, [pipelineId]);

  // -----------------------------------------------------------------------
  // Status polling for active run
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!activeRunId || !polling) return;
    const interval = setInterval(async () => {
      try {
        const res = await api.get(`/forecast-pipeline/runs/${activeRunId}`);
        setActiveRunStatus(res.data);
        if (res.data.status === 'completed' || res.data.status === 'published') {
          clearInterval(interval);
          setPolling(false);
          loadRuns();
          setSuccess(`Run #${activeRunId} completed successfully.`);
        } else if (res.data.status === 'failed') {
          clearInterval(interval);
          setPolling(false);
          loadRuns();
          setError(res.data.error_message || `Run #${activeRunId} failed.`);
        }
      } catch (err) {
        console.error('Poll error:', err);
      }
    }, RUN_POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [activeRunId, polling]);

  // -----------------------------------------------------------------------
  // Run actions
  // -----------------------------------------------------------------------

  const handleStartRun = async () => {
    if (!pipelineId) { setError('Select a pipeline configuration first.'); return; }
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await api.post('/forecast-pipeline/runs', {
        pipeline_config_id: pipelineId,
        auto_start: true,
      });
      setActiveRunId(res.data.id);
      setActiveRunStatus({ status: 'pending' });
      setPolling(true);
      setSuccess('Pipeline run started.');
      await loadRuns();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start pipeline run.');
    } finally {
      setLoading(false);
    }
  };

  const handleReExecute = async (runId) => {
    setLoading(true);
    setError(null);
    try {
      await api.post(`/forecast-pipeline/runs/${runId}/execute`);
      setActiveRunId(runId);
      setActiveRunStatus({ status: 'pending' });
      setPolling(true);
      setSuccess(`Re-executing run #${runId}.`);
      await loadRuns();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to re-execute run.');
    } finally {
      setLoading(false);
    }
  };

  const handlePublish = async (runId) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post(`/forecast-pipeline/runs/${runId}/publish`, {});
      setSuccess(`Published ${res.data.published_records} forecast records from run #${runId}.`);
      await loadRuns();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to publish run.');
    } finally {
      setLoading(false);
    }
  };

  const handleViewRun = async (runId) => {
    setActiveRunId(runId);
    try {
      const res = await api.get(`/forecast-pipeline/runs/${runId}`);
      setActiveRunStatus(res.data);
      if (res.data.status === 'running' || res.data.status === 'pending') {
        setPolling(true);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load run details.');
    }
  };

  // -----------------------------------------------------------------------
  // Config form actions
  // -----------------------------------------------------------------------

  const updateField = useCallback((field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  }, []);

  const openCreateForm = () => {
    setForm({ ...FORM_DEFAULTS });
    setEditMode(false);
    setEditingId(null);
    setShowForm(true);
  };

  const openEditForm = () => {
    if (!activePipeline) return;
    const c = activePipeline;
    setForm({
      name: c.name || '',
      description: c.description || '',
      time_bucket: c.time_bucket || 'W',
      forecast_horizon: c.forecast_horizon || 8,
      forecast_metric: c.forecast_metric || 'wape',
      model_type: c.model_type || 'clustered_naive',
      demand_item: c.demand_item || '',
      demand_point: c.demand_point || '',
      target_column: c.target_column || '',
      date_column: c.date_column || '',
      number_of_items_analyzed: c.number_of_items_analyzed || '',
      min_observations: c.min_observations || 12,
      ignore_numeric_columns: c.ignore_numeric_columns || '',
      cv_sq_threshold: c.cv_sq_threshold ?? 0.49,
      adi_threshold: c.adi_threshold ?? 1.32,
      min_clusters: c.min_clusters || 2,
      max_clusters: c.max_clusters || 8,
      min_cluster_size: c.min_cluster_size || 5,
      min_cluster_size_uom: c.min_cluster_size_uom || 'items',
      cluster_selection_method: c.cluster_selection_method || 'KMeans',
      characteristics_creation_method: c.characteristics_creation_method || 'tsfresh',
      feature_correlation_threshold: c.feature_correlation_threshold ?? 0.8,
      feature_importance_method: c.feature_importance_method || 'LassoCV',
      feature_importance_threshold: c.feature_importance_threshold ?? 0.01,
      pca_variance_threshold: c.pca_variance_threshold ?? 0.95,
      pca_importance_threshold: c.pca_importance_threshold ?? 0.01,
    });
    setEditMode(true);
    setEditingId(c.id);
    setShowForm(true);
  };

  const cancelForm = () => {
    setShowForm(false);
    setEditMode(false);
    setEditingId(null);
  };

  const buildPayload = () => {
    const payload = { ...form };
    const optionalStrings = ['demand_item', 'demand_point', 'target_column', 'date_column', 'ignore_numeric_columns'];
    optionalStrings.forEach((k) => { if (payload[k] === '') payload[k] = null; });
    if (payload.number_of_items_analyzed === '' || payload.number_of_items_analyzed === null) {
      payload.number_of_items_analyzed = null;
    }
    return payload;
  };

  const handleSaveConfig = async () => {
    if (!form.name.trim()) { setError('Pipeline name is required.'); return; }
    setLoading(true);
    setError(null);
    try {
      if (editMode && editingId) {
        await api.put(`/forecast-pipeline/configs/${editingId}`, buildPayload());
        setSuccess('Pipeline configuration updated.');
      } else {
        if (!scConfigId) { setError('Select a supply chain configuration first.'); setLoading(false); return; }
        await api.post('/forecast-pipeline/configs', { ...buildPayload(), config_id: scConfigId });
        setSuccess('Pipeline configuration created.');
      }
      cancelForm();
      await loadPipelineConfigs();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save pipeline configuration.');
    } finally {
      setLoading(false);
    }
  };

  // -----------------------------------------------------------------------
  // Derived display values
  // -----------------------------------------------------------------------

  const modelLabel = activePipeline?.model_type?.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase()) || 'Not Configured';
  const clusterLabel = activePipeline?.cluster_selection_method || '\u2014';
  const cadenceLabel = activePipeline ? (BUCKET_LABELS[activePipeline.time_bucket] || activePipeline.time_bucket) : '\u2014';
  const metricLabel = activePipeline ? (activePipeline.forecast_metric || 'wape').toUpperCase() : '\u2014';

  // -----------------------------------------------------------------------
  // Render: Overview Cards
  // -----------------------------------------------------------------------

  const renderOverviewCards = () => (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Pipeline</p>
              <p className="text-lg font-bold">{modelLabel}</p>
            </div>
            <TrendingUp className="h-8 w-8 text-primary" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Clustering</p>
              <p className="text-lg font-bold">{clusterLabel}</p>
            </div>
            <GitBranch className="h-8 w-8 text-purple-500" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Cadence</p>
              <p className="text-lg font-bold">{cadenceLabel}</p>
            </div>
            <Clock className="h-8 w-8 text-amber-500" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Metric</p>
              <p className="text-lg font-bold">{metricLabel}</p>
            </div>
            <CheckCircle className="h-8 w-8 text-green-500" />
          </div>
        </CardContent>
      </Card>
    </div>
  );

  // -----------------------------------------------------------------------
  // Render: Pipeline Controls
  // -----------------------------------------------------------------------

  const renderControls = () => (
    <Card className="mb-6">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Pipeline Controls</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
          <div>
            <Label className="text-xs">Pipeline Config</Label>
            <Select value={selectedPipelineId} onValueChange={setSelectedPipelineId}>
              <SelectTrigger className="mt-1 h-8 text-sm">
                <SelectValue placeholder="Select pipeline" />
              </SelectTrigger>
              <SelectContent>
                {pipelineConfigs.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={handleStartRun}
              disabled={loading || !pipelineId}
              leftIcon={loading && polling ? <Spinner size="sm" /> : <Play className="h-3.5 w-3.5" />}
            >
              Start Run
            </Button>
            <Button size="sm" variant="outline" onClick={loadRuns} disabled={loading}>
              <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
            </Button>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={openCreateForm}>
              <Plus className="h-3.5 w-3.5 mr-1" /> New Config
            </Button>
            {activePipeline && (
              <Button size="sm" variant="outline" onClick={openEditForm}>
                <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );

  // -----------------------------------------------------------------------
  // Render: Active Run Status
  // -----------------------------------------------------------------------

  const renderActiveRunStatus = () => {
    if (!activeRunId || !activeRunStatus) return null;
    const s = activeRunStatus;
    const isRunning = s.status === 'running' || s.status === 'pending';

    return (
      <Card className="mb-6">
        <CardContent className="pt-4">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-lg font-semibold">Active Run #{activeRunId}</h2>
            <Badge variant={getStatusVariant(s.status)}>{s.status}</Badge>
          </div>
          {isRunning && (
            <>
              <p className="text-sm text-muted-foreground mb-2">
                {s.status === 'pending' ? 'Waiting to start...' : 'Running pipeline...'}
              </p>
              <Progress value={s.status === 'pending' ? 5 : 50} className="mb-2" />
            </>
          )}
          {s.status === 'completed' && s.records_processed != null && (
            <p className="text-sm text-muted-foreground">
              Processed {s.records_processed} records.
              {s.run_log?.wape != null && ` WAPE: ${(s.run_log.wape * 100).toFixed(1)}%`}
            </p>
          )}
          {s.error_message && (
            <Alert variant="destructive" className="mt-3">
              <AlertCircle className="h-4 w-4" />
              {s.error_message}
            </Alert>
          )}
        </CardContent>
      </Card>
    );
  };

  // -----------------------------------------------------------------------
  // Render: Configuration Form
  // -----------------------------------------------------------------------

  const renderConfigForm = () => {
    if (!showForm) return null;

    return (
      <Card className="mb-6">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">
              {editMode ? `Edit: ${form.name || 'Pipeline Config'}` : 'New Pipeline Config'}
            </CardTitle>
            <Button size="sm" variant="ghost" onClick={cancelForm}><X className="h-4 w-4" /></Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <FieldLabel>Pipeline Name</FieldLabel>
              <Input className="mt-1 h-8 text-sm" value={form.name} onChange={(e) => updateField('name', e.target.value)} placeholder="e.g. Weekly Demand Forecast" />
            </div>
            <div>
              <FieldLabel>Description</FieldLabel>
              <Input className="mt-1 h-8 text-sm" value={form.description} onChange={(e) => updateField('description', e.target.value)} placeholder="Brief description" />
            </div>
          </div>

          <Accordion type="multiple" defaultValue={['forecast-settings', 'clustering']}>
            {/* Dataset & Column Mapping */}
            <AccordionItem value="dataset-mapping">
              <AccordionTrigger className="text-sm py-3">
                <span className="flex items-center gap-2"><Database className="h-4 w-4 text-blue-500" /> Dataset & Column Mapping</span>
              </AccordionTrigger>
              <AccordionContent>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div>
                    <FieldLabel tip="Product column name override (default: product_id)">Demand Item</FieldLabel>
                    <Input className="mt-1 h-8 text-sm" placeholder="product_id" value={form.demand_item} onChange={(e) => updateField('demand_item', e.target.value)} />
                  </div>
                  <div>
                    <FieldLabel tip="Site column name override (default: site_id)">Demand Point</FieldLabel>
                    <Input className="mt-1 h-8 text-sm" placeholder="site_id" value={form.demand_point} onChange={(e) => updateField('demand_point', e.target.value)} />
                  </div>
                  <div>
                    <FieldLabel tip="Quantity column override (default: ordered_quantity)">Target Column</FieldLabel>
                    <Input className="mt-1 h-8 text-sm" placeholder="ordered_quantity" value={form.target_column} onChange={(e) => updateField('target_column', e.target.value)} />
                  </div>
                  <div>
                    <FieldLabel tip="Date column override (default: requested_delivery_date)">Date Column</FieldLabel>
                    <Input className="mt-1 h-8 text-sm" placeholder="requested_delivery_date" value={form.date_column} onChange={(e) => updateField('date_column', e.target.value)} />
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>

            {/* Forecast Settings */}
            <AccordionItem value="forecast-settings">
              <AccordionTrigger className="text-sm py-3">
                <span className="flex items-center gap-2"><TrendingUp className="h-4 w-4 text-green-500" /> Forecast Settings</span>
              </AccordionTrigger>
              <AccordionContent>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div>
                    <FieldLabel tip="Aggregation period: Daily, Weekly, or Monthly">Time Bucket</FieldLabel>
                    <Select value={form.time_bucket} onValueChange={(v) => updateField('time_bucket', v)}>
                      <SelectTrigger className="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {TIME_BUCKETS.map((b) => <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <FieldLabel tip="Number of periods to forecast into the future">Forecast Horizon</FieldLabel>
                    <NumberInput value={form.forecast_horizon} onChange={(v) => updateField('forecast_horizon', v)} min={1} max={104} />
                  </div>
                  <div>
                    <FieldLabel tip="Max product-site combinations to analyze (empty = all)">Items Analyzed</FieldLabel>
                    <NumberInput value={form.number_of_items_analyzed} onChange={(v) => updateField('number_of_items_analyzed', v)} min={1} placeholder="All" />
                  </div>
                  <div>
                    <FieldLabel tip="Primary error metric for model evaluation">Forecast Metric</FieldLabel>
                    <Select value={form.forecast_metric} onValueChange={(v) => updateField('forecast_metric', v)}>
                      <SelectTrigger className="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {FORECAST_METRICS.map((m) => <SelectItem key={m} value={m}>{m.toUpperCase()}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>

            {/* Data Quality Thresholds */}
            <AccordionItem value="data-quality">
              <AccordionTrigger className="text-sm py-3">
                <span className="flex items-center gap-2"><Filter className="h-4 w-4 text-amber-500" /> Data Quality Thresholds</span>
              </AccordionTrigger>
              <AccordionContent>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div>
                    <FieldLabel tip="Minimum data points required per series">Min Observations</FieldLabel>
                    <NumberInput value={form.min_observations} onChange={(v) => updateField('min_observations', v)} min={3} max={1000} />
                  </div>
                  <div>
                    <FieldLabel tip="CV-squared threshold for variability classification. Default 0.49">CV Sq Threshold</FieldLabel>
                    <NumberInput value={form.cv_sq_threshold} onChange={(v) => updateField('cv_sq_threshold', v)} min={0} max={10} step={0.01} />
                  </div>
                  <div>
                    <FieldLabel tip="Average Demand Interval threshold for intermittency. Default 1.32">ADI Threshold</FieldLabel>
                    <NumberInput value={form.adi_threshold} onChange={(v) => updateField('adi_threshold', v)} min={0} max={10} step={0.01} />
                  </div>
                  <div>
                    <FieldLabel tip="Comma-separated numeric columns to exclude">Ignore Columns</FieldLabel>
                    <Input className="mt-1 h-8 text-sm" value={form.ignore_numeric_columns} onChange={(e) => updateField('ignore_numeric_columns', e.target.value)} placeholder="col1, col2" />
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>

            {/* Clustering */}
            <AccordionItem value="clustering">
              <AccordionTrigger className="text-sm py-3">
                <span className="flex items-center gap-2"><GitBranch className="h-4 w-4 text-purple-500" /> Clustering Configuration</span>
              </AccordionTrigger>
              <AccordionContent>
                <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                  <div>
                    <FieldLabel tip="Algorithm for grouping similar demand series">Cluster Method</FieldLabel>
                    <Select value={form.cluster_selection_method} onValueChange={(v) => updateField('cluster_selection_method', v)}>
                      <SelectTrigger className="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {CLUSTER_METHODS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <FieldLabel tip="Minimum clusters to evaluate">Min Clusters</FieldLabel>
                    <NumberInput value={form.min_clusters} onChange={(v) => updateField('min_clusters', v)} min={1} max={100} />
                  </div>
                  <div>
                    <FieldLabel tip="Maximum clusters to evaluate">Max Clusters</FieldLabel>
                    <NumberInput value={form.max_clusters} onChange={(v) => updateField('max_clusters', v)} min={1} max={100} />
                  </div>
                  <div>
                    <FieldLabel tip="Minimum items per cluster">Min Cluster Size</FieldLabel>
                    <NumberInput value={form.min_cluster_size} onChange={(v) => updateField('min_cluster_size', v)} min={1} />
                  </div>
                  <div>
                    <FieldLabel tip="Unit for min cluster size: absolute count or percent of total">Size Unit</FieldLabel>
                    <Select value={form.min_cluster_size_uom} onValueChange={(v) => updateField('min_cluster_size_uom', v)}>
                      <SelectTrigger className="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="items">Items</SelectItem>
                        <SelectItem value="percent">Percent</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>

            {/* Feature Engineering */}
            <AccordionItem value="feature-engineering">
              <AccordionTrigger className="text-sm py-3">
                <span className="flex items-center gap-2"><Cpu className="h-4 w-4 text-red-500" /> Feature Engineering</span>
              </AccordionTrigger>
              <AccordionContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <FieldLabel tip="Method for creating time-series characteristics">Characteristics Method</FieldLabel>
                    <Select value={form.characteristics_creation_method} onValueChange={(v) => updateField('characteristics_creation_method', v)}>
                      <SelectTrigger className="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {CHAR_CREATION_METHODS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <FieldLabel tip="Correlation threshold to remove redundant features (0-1)">Feature Correlation</FieldLabel>
                    <NumberInput value={form.feature_correlation_threshold} onChange={(v) => updateField('feature_correlation_threshold', v)} min={0} max={1} step={0.01} />
                  </div>
                  <div>
                    <FieldLabel tip="Method for ranking feature importance">Importance Method</FieldLabel>
                    <Select value={form.feature_importance_method} onValueChange={(v) => updateField('feature_importance_method', v)}>
                      <SelectTrigger className="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {FEATURE_IMPORTANCE_METHODS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <FieldLabel tip="Minimum importance score to retain a feature">Importance Threshold</FieldLabel>
                    <NumberInput value={form.feature_importance_threshold} onChange={(v) => updateField('feature_importance_threshold', v)} min={0} max={1} step={0.001} />
                  </div>
                  <div>
                    <FieldLabel tip="PCA variance to retain (0-1)">PCA Variance</FieldLabel>
                    <NumberInput value={form.pca_variance_threshold} onChange={(v) => updateField('pca_variance_threshold', v)} min={0} max={1} step={0.01} />
                  </div>
                  <div>
                    <FieldLabel tip="PCA component loading threshold">PCA Importance</FieldLabel>
                    <NumberInput value={form.pca_importance_threshold} onChange={(v) => updateField('pca_importance_threshold', v)} min={0} max={1} step={0.001} />
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>

          <div className="flex gap-2 pt-2 border-t">
            <Button size="sm" onClick={handleSaveConfig} disabled={loading}>
              <Save className="h-3.5 w-3.5 mr-1" />
              {editMode ? 'Save Changes' : 'Create Config'}
            </Button>
            <Button size="sm" variant="outline" onClick={cancelForm}>Cancel</Button>
          </div>
        </CardContent>
      </Card>
    );
  };

  // -----------------------------------------------------------------------
  // Render: Run History Table
  // -----------------------------------------------------------------------

  const renderRunHistory = () => (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex justify-between items-center">
          <CardTitle className="text-base">Run History</CardTitle>
          <Button variant="outline" size="sm" onClick={loadRuns} leftIcon={<RefreshCw className="h-3.5 w-3.5" />}>
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Run</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Model</TableHead>
              <TableHead>Metric</TableHead>
              <TableHead className="text-right">Records</TableHead>
              <TableHead>Started</TableHead>
              <TableHead>Completed</TableHead>
              <TableHead className="text-center">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.map((run) => (
              <TableRow key={run.id}>
                <TableCell className="font-mono text-xs">#{run.id}</TableCell>
                <TableCell>
                  <Badge variant={getStatusVariant(run.status)}>{run.status}</Badge>
                </TableCell>
                <TableCell className="text-sm">{run.model_type || '\u2014'}</TableCell>
                <TableCell className="text-sm">{(run.forecast_metric || '').toUpperCase() || '\u2014'}</TableCell>
                <TableCell className="text-right text-sm">{run.records_processed ?? '\u2014'}</TableCell>
                <TableCell className="text-sm">{run.started_at ? new Date(run.started_at).toLocaleString() : '\u2014'}</TableCell>
                <TableCell className="text-sm">{run.completed_at ? new Date(run.completed_at).toLocaleString() : '\u2014'}</TableCell>
                <TableCell className="text-center">
                  <div className="flex justify-center gap-1">
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="ghost" size="sm" onClick={() => handleViewRun(run.id)}>
                            <Eye className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>View Details</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleReExecute(run.id)}
                            disabled={loading || run.status === 'running'}
                          >
                            <RefreshCw className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Re-execute</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handlePublish(run.id)}
                            disabled={loading || !['completed', 'published'].includes(run.status)}
                          >
                            <Upload className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Publish to Forecast Table</TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {runs.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="text-center text-muted-foreground py-8">
                  No pipeline runs yet. Select a pipeline configuration and click Start Run.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );

  // -----------------------------------------------------------------------
  // Main render
  // -----------------------------------------------------------------------

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">Forecasting</h1>
            <p className="text-sm text-muted-foreground">
              ML-based statistical forecast generation, clustering, and publishing
            </p>
          </div>
        </div>
        <Select value={selectedScConfig} onValueChange={(v) => { setSelectedScConfig(v); setSelectedPipelineId(''); }}>
          <SelectTrigger className="w-[220px]">
            <SelectValue placeholder="Select Configuration" />
          </SelectTrigger>
          <SelectContent>
            {scConfigs.map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Alerts */}
      {error && <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>{error}</Alert>}
      {success && <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>{success}</Alert>}

      {/* Content */}
      {scConfigId ? (
        <>
          {renderOverviewCards()}
          {renderControls()}
          {renderConfigForm()}
          {renderActiveRunStatus()}
          {renderRunHistory()}
        </>
      ) : (
        <Card>
          <CardContent className="pt-4 text-center py-8">
            <p className="text-muted-foreground">Select a supply chain configuration to manage forecast pipelines.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default Forecasting;
