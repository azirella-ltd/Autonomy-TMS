import React, { useEffect, useMemo, useState, useCallback } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../common';
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from '../common/Accordion';
import {
  Database,
  TrendingUp,
  Filter,
  GitBranch,
  Cpu,
  Info,
  Play,
  RefreshCw,
  Save,
  Plus,
  Pencil,
  X,
} from 'lucide-react';
import { api } from '../../services/api';

const CLUSTER_METHODS = [
  'KMeans', 'HDBSCAN', 'Agglomerative', 'OPTICS', 'Birch',
  'GaussianMixture', 'MeanShift', 'Spectral', 'AffinityPropagation',
];

const FEATURE_IMPORTANCE_METHODS = ['LassoCV', 'RandomForest', 'MutualInformation'];
const CHAR_CREATION_METHODS = ['tsfresh', 'classifier', 'both'];
const FORECAST_METRICS = ['wape', 'mae', 'rmse'];
const TIME_BUCKETS = [
  { value: 'D', label: 'Daily' },
  { value: 'W', label: 'Weekly' },
  { value: 'M', label: 'Monthly' },
];

const DEFAULTS = {
  name: '',
  description: '',
  time_bucket: 'W',
  forecast_horizon: 8,
  forecast_metric: 'wape',
  model_type: 'clustered_naive',
  // Dataset & Column Mapping
  demand_item: '',
  demand_point: '',
  target_column: '',
  date_column: '',
  // Forecast Settings
  number_of_items_analyzed: '',
  // Data Quality Thresholds
  min_observations: 12,
  ignore_numeric_columns: '',
  cv_sq_threshold: 0.49,
  adi_threshold: 1.32,
  // Clustering
  min_clusters: 2,
  max_clusters: 8,
  min_cluster_size: 5,
  min_cluster_size_uom: 'items',
  cluster_selection_method: 'KMeans',
  // Feature Engineering
  characteristics_creation_method: 'tsfresh',
  feature_correlation_threshold: 0.8,
  feature_importance_method: 'LassoCV',
  feature_importance_threshold: 0.01,
  pca_variance_threshold: 0.95,
  pca_importance_threshold: 0.01,
};

const InfoTip = ({ text }) => (
  <TooltipProvider delayDuration={200}>
    <Tooltip>
      <TooltipTrigger asChild>
        <Info className="h-3.5 w-3.5 text-muted-foreground ml-1 inline cursor-help" />
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs text-xs">
        {text}
      </TooltipContent>
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

const ForecastPipelineManager = ({ configId, configName }) => {
  const [configs, setConfigs] = useState([]);
  const [runs, setRuns] = useState([]);
  const [selectedConfigId, setSelectedConfigId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Form state
  const [form, setForm] = useState({ ...DEFAULTS });
  const [showForm, setShowForm] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editingConfigId, setEditingConfigId] = useState(null);

  const resolvedConfigId = useMemo(() => {
    if (selectedConfigId) return Number(selectedConfigId);
    return configId || undefined;
  }, [selectedConfigId, configId]);

  const selectedConfig = useMemo(
    () => configs.find((c) => String(c.id) === selectedConfigId),
    [configs, selectedConfigId]
  );

  const updateField = useCallback((field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  }, []);

  // ---- Data Loading ----

  const loadConfigs = async () => {
    try {
      const params = configId ? { config_id: configId } : {};
      const response = await api.get('/forecast-pipeline/configs', { params });
      setConfigs(response.data);
      if (!selectedConfigId && response.data.length > 0) {
        setSelectedConfigId(String(response.data[0].id));
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load pipeline configs');
    }
  };

  const loadRuns = async () => {
    try {
      const params = resolvedConfigId ? { pipeline_config_id: resolvedConfigId } : {};
      const response = await api.get('/forecast-pipeline/runs', { params });
      setRuns(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load pipeline runs');
    }
  };

  useEffect(() => { loadConfigs(); }, [configId]);
  useEffect(() => { loadRuns(); }, [resolvedConfigId]);

  // ---- Config Actions ----

  const openCreateForm = () => {
    setForm({ ...DEFAULTS });
    setEditMode(false);
    setEditingConfigId(null);
    setShowForm(true);
  };

  const openEditForm = () => {
    if (!selectedConfig) return;
    setForm({
      name: selectedConfig.name || '',
      description: selectedConfig.description || '',
      time_bucket: selectedConfig.time_bucket || 'W',
      forecast_horizon: selectedConfig.forecast_horizon || 8,
      forecast_metric: selectedConfig.forecast_metric || 'wape',
      model_type: selectedConfig.model_type || 'clustered_naive',
      demand_item: selectedConfig.demand_item || '',
      demand_point: selectedConfig.demand_point || '',
      target_column: selectedConfig.target_column || '',
      date_column: selectedConfig.date_column || '',
      number_of_items_analyzed: selectedConfig.number_of_items_analyzed || '',
      min_observations: selectedConfig.min_observations || 12,
      ignore_numeric_columns: selectedConfig.ignore_numeric_columns || '',
      cv_sq_threshold: selectedConfig.cv_sq_threshold ?? 0.49,
      adi_threshold: selectedConfig.adi_threshold ?? 1.32,
      min_clusters: selectedConfig.min_clusters || 2,
      max_clusters: selectedConfig.max_clusters || 8,
      min_cluster_size: selectedConfig.min_cluster_size || 5,
      min_cluster_size_uom: selectedConfig.min_cluster_size_uom || 'items',
      cluster_selection_method: selectedConfig.cluster_selection_method || 'KMeans',
      characteristics_creation_method: selectedConfig.characteristics_creation_method || 'tsfresh',
      feature_correlation_threshold: selectedConfig.feature_correlation_threshold ?? 0.8,
      feature_importance_method: selectedConfig.feature_importance_method || 'LassoCV',
      feature_importance_threshold: selectedConfig.feature_importance_threshold ?? 0.01,
      pca_variance_threshold: selectedConfig.pca_variance_threshold ?? 0.95,
      pca_importance_threshold: selectedConfig.pca_importance_threshold ?? 0.01,
    });
    setEditMode(true);
    setEditingConfigId(selectedConfig.id);
    setShowForm(true);
  };

  const cancelForm = () => {
    setShowForm(false);
    setEditMode(false);
    setEditingConfigId(null);
  };

  const buildPayload = () => {
    const payload = { ...form };
    // Convert empty strings to null for optional fields
    if (payload.demand_item === '') payload.demand_item = null;
    if (payload.demand_point === '') payload.demand_point = null;
    if (payload.target_column === '') payload.target_column = null;
    if (payload.date_column === '') payload.date_column = null;
    if (payload.number_of_items_analyzed === '' || payload.number_of_items_analyzed === null) {
      payload.number_of_items_analyzed = null;
    }
    if (payload.ignore_numeric_columns === '') payload.ignore_numeric_columns = null;
    return payload;
  };

  const saveConfig = async () => {
    if (!form.name.trim()) {
      setError('Pipeline name is required');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      if (editMode && editingConfigId) {
        await api.put(`/forecast-pipeline/configs/${editingConfigId}`, buildPayload());
        setSuccess('Pipeline config updated');
      } else {
        if (!configId) {
          setError('Select a supply chain config first');
          setLoading(false);
          return;
        }
        await api.post('/forecast-pipeline/configs', {
          ...buildPayload(),
          config_id: configId,
        });
        setSuccess('Pipeline config created');
      }
      setShowForm(false);
      setEditMode(false);
      setEditingConfigId(null);
      await loadConfigs();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save pipeline config');
    } finally {
      setLoading(false);
    }
  };

  // ---- Run Actions ----

  const startRun = async () => {
    if (!resolvedConfigId) {
      setError('Choose a pipeline config');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.post('/forecast-pipeline/runs', {
        pipeline_config_id: resolvedConfigId,
        auto_start: true,
      });
      setSuccess('Pipeline run started');
      await loadRuns();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start pipeline run');
    } finally {
      setLoading(false);
    }
  };

  const reExecuteRun = async (runId) => {
    setLoading(true);
    setError(null);
    try {
      await api.post(`/forecast-pipeline/runs/${runId}/execute`);
      setSuccess(`Run ${runId} queued`);
      await loadRuns();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to queue run');
    } finally {
      setLoading(false);
    }
  };

  const publishRun = async (runId) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.post(`/forecast-pipeline/runs/${runId}/publish`, {});
      setSuccess(`Published ${response.data.published_records} forecast rows`);
      await loadRuns();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to publish run');
    } finally {
      setLoading(false);
    }
  };

  const statusVariant = (status) => {
    if (status === 'completed' || status === 'published') return 'success';
    if (status === 'failed') return 'destructive';
    if (status === 'running') return 'warning';
    return 'secondary';
  };

  // ---- Render ----

  return (
    <div className="space-y-4">
      {error && <Alert variant="error" onClose={() => setError(null)}>{error}</Alert>}
      {success && <Alert variant="success" onClose={() => setSuccess(null)}>{success}</Alert>}

      {/* ── Card 1: Pipeline Controls ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Pipeline Controls</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
            <div>
              <Label className="text-xs">Pipeline Config</Label>
              <Select value={selectedConfigId} onValueChange={setSelectedConfigId}>
                <SelectTrigger className="mt-1 h-8 text-sm">
                  <SelectValue placeholder="Select config" />
                </SelectTrigger>
                <SelectContent>
                  {configs.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Source Config</Label>
              <Input value={configName || `Config #${configId}`} disabled className="mt-1 h-8 text-sm" />
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={startRun} disabled={loading || !resolvedConfigId}>
                <Play className="h-3.5 w-3.5 mr-1" /> Start Run
              </Button>
              <Button size="sm" variant="outline" onClick={loadRuns} disabled={loading}>
                <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
              </Button>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={openCreateForm}>
                <Plus className="h-3.5 w-3.5 mr-1" /> New Config
              </Button>
              {selectedConfig && (
                <Button size="sm" variant="outline" onClick={openEditForm}>
                  <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Card 2: Pipeline Configuration Form ── */}
      {showForm && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                {editMode ? `Edit: ${form.name || 'Pipeline Config'}` : 'New Pipeline Config'}
              </CardTitle>
              <Button size="sm" variant="ghost" onClick={cancelForm}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Name + Description always visible */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <FieldLabel>Pipeline Name</FieldLabel>
                <Input
                  className="mt-1 h-8 text-sm"
                  value={form.name}
                  onChange={(e) => updateField('name', e.target.value)}
                  placeholder="e.g. Weekly Demand Forecast"
                />
              </div>
              <div>
                <FieldLabel>Description</FieldLabel>
                <Input
                  className="mt-1 h-8 text-sm"
                  value={form.description}
                  onChange={(e) => updateField('description', e.target.value)}
                  placeholder="Brief description of this pipeline"
                />
              </div>
            </div>

            {/* Accordion Sections */}
            <Accordion type="multiple" defaultValue={['forecast-settings', 'clustering']}>
              {/* ── Section 1: Dataset & Column Mapping ── */}
              <AccordionItem value="dataset-mapping">
                <AccordionTrigger className="text-sm py-3">
                  <span className="flex items-center gap-2">
                    <Database className="h-4 w-4 text-blue-500" />
                    Dataset & Column Mapping
                  </span>
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

              {/* ── Section 2: Forecast Settings ── */}
              <AccordionItem value="forecast-settings">
                <AccordionTrigger className="text-sm py-3">
                  <span className="flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-green-500" />
                    Forecast Settings
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div>
                      <FieldLabel tip="Aggregation period: Daily, Weekly, or Monthly">Time Bucket</FieldLabel>
                      <Select value={form.time_bucket} onValueChange={(v) => updateField('time_bucket', v)}>
                        <SelectTrigger className="mt-1 h-8 text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {TIME_BUCKETS.map((b) => (
                            <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>
                          ))}
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
                        <SelectTrigger className="mt-1 h-8 text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {FORECAST_METRICS.map((m) => (
                            <SelectItem key={m} value={m}>{m.toUpperCase()}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </AccordionContent>
              </AccordionItem>

              {/* ── Section 3: Data Quality Thresholds ── */}
              <AccordionItem value="data-quality">
                <AccordionTrigger className="text-sm py-3">
                  <span className="flex items-center gap-2">
                    <Filter className="h-4 w-4 text-amber-500" />
                    Data Quality Thresholds
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div>
                      <FieldLabel tip="Minimum data points required per series to include in forecast">Min Observations</FieldLabel>
                      <NumberInput value={form.min_observations} onChange={(v) => updateField('min_observations', v)} min={3} max={1000} />
                    </div>
                    <div>
                      <FieldLabel tip="CV-squared threshold for demand variability classification (smooth vs erratic). Default 0.49">CV Sq Threshold</FieldLabel>
                      <NumberInput value={form.cv_sq_threshold} onChange={(v) => updateField('cv_sq_threshold', v)} min={0} max={10} step={0.01} />
                    </div>
                    <div>
                      <FieldLabel tip="Average Demand Interval threshold for intermittency classification. Default 1.32">ADI Threshold</FieldLabel>
                      <NumberInput value={form.adi_threshold} onChange={(v) => updateField('adi_threshold', v)} min={0} max={10} step={0.01} />
                    </div>
                    <div className="md:col-span-1">
                      <FieldLabel tip="Comma-separated list of numeric columns to exclude from analysis">Ignore Columns</FieldLabel>
                      <Textarea
                        className="mt-1 text-sm h-8 min-h-[32px]"
                        value={form.ignore_numeric_columns}
                        onChange={(e) => updateField('ignore_numeric_columns', e.target.value)}
                        placeholder="col1, col2, ..."
                      />
                    </div>
                  </div>
                </AccordionContent>
              </AccordionItem>

              {/* ── Section 4: Clustering Configuration ── */}
              <AccordionItem value="clustering">
                <AccordionTrigger className="text-sm py-3">
                  <span className="flex items-center gap-2">
                    <GitBranch className="h-4 w-4 text-purple-500" />
                    Clustering Configuration
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                    <div>
                      <FieldLabel tip="Algorithm for grouping similar demand series">Cluster Method</FieldLabel>
                      <Select value={form.cluster_selection_method} onValueChange={(v) => updateField('cluster_selection_method', v)}>
                        <SelectTrigger className="mt-1 h-8 text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {CLUSTER_METHODS.map((m) => (
                            <SelectItem key={m} value={m}>{m}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <FieldLabel tip="Minimum number of clusters to evaluate">Min Clusters</FieldLabel>
                      <NumberInput value={form.min_clusters} onChange={(v) => updateField('min_clusters', v)} min={1} max={100} />
                    </div>
                    <div>
                      <FieldLabel tip="Maximum number of clusters to evaluate">Max Clusters</FieldLabel>
                      <NumberInput value={form.max_clusters} onChange={(v) => updateField('max_clusters', v)} min={1} max={100} />
                    </div>
                    <div>
                      <FieldLabel tip="Minimum items per cluster; smaller clusters are merged">Min Cluster Size</FieldLabel>
                      <NumberInput value={form.min_cluster_size} onChange={(v) => updateField('min_cluster_size', v)} min={1} />
                    </div>
                    <div>
                      <FieldLabel tip="Unit for min cluster size: absolute item count or percent of total">Size Unit</FieldLabel>
                      <Select value={form.min_cluster_size_uom} onValueChange={(v) => updateField('min_cluster_size_uom', v)}>
                        <SelectTrigger className="mt-1 h-8 text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="items">Items</SelectItem>
                          <SelectItem value="percent">Percent</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </AccordionContent>
              </AccordionItem>

              {/* ── Section 5: Feature Engineering ── */}
              <AccordionItem value="feature-engineering">
                <AccordionTrigger className="text-sm py-3">
                  <span className="flex items-center gap-2">
                    <Cpu className="h-4 w-4 text-red-500" />
                    Feature Engineering
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <FieldLabel tip="Method for creating time-series characteristics: tsfresh (automatic), classifier (ML-based), or both">Characteristics Method</FieldLabel>
                      <Select value={form.characteristics_creation_method} onValueChange={(v) => updateField('characteristics_creation_method', v)}>
                        <SelectTrigger className="mt-1 h-8 text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {CHAR_CREATION_METHODS.map((m) => (
                            <SelectItem key={m} value={m}>{m}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <FieldLabel tip="Correlation threshold to remove redundant features (0-1). Default 0.8">Feature Correlation</FieldLabel>
                      <NumberInput value={form.feature_correlation_threshold} onChange={(v) => updateField('feature_correlation_threshold', v)} min={0} max={1} step={0.01} />
                    </div>
                    <div>
                      <FieldLabel tip="Method for ranking feature importance">Importance Method</FieldLabel>
                      <Select value={form.feature_importance_method} onValueChange={(v) => updateField('feature_importance_method', v)}>
                        <SelectTrigger className="mt-1 h-8 text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {FEATURE_IMPORTANCE_METHODS.map((m) => (
                            <SelectItem key={m} value={m}>{m}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <FieldLabel tip="Minimum importance score to retain a feature. Default 0.01">Importance Threshold</FieldLabel>
                      <NumberInput value={form.feature_importance_threshold} onChange={(v) => updateField('feature_importance_threshold', v)} min={0} max={1} step={0.001} />
                    </div>
                    <div>
                      <FieldLabel tip="PCA variance to retain (0-1). Controls dimensionality reduction. Default 0.95">PCA Variance</FieldLabel>
                      <NumberInput value={form.pca_variance_threshold} onChange={(v) => updateField('pca_variance_threshold', v)} min={0} max={1} step={0.01} />
                    </div>
                    <div>
                      <FieldLabel tip="PCA component loading threshold. Default 0.01">PCA Importance</FieldLabel>
                      <NumberInput value={form.pca_importance_threshold} onChange={(v) => updateField('pca_importance_threshold', v)} min={0} max={1} step={0.001} />
                    </div>
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>

            {/* Save / Cancel */}
            <div className="flex gap-2 pt-2 border-t">
              <Button size="sm" onClick={saveConfig} disabled={loading}>
                <Save className="h-3.5 w-3.5 mr-1" />
                {editMode ? 'Save Changes' : 'Create Config'}
              </Button>
              <Button size="sm" variant="outline" onClick={cancelForm}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Card 3: Run History ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Run History</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run ID</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Records</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Completed</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((run) => (
                <TableRow key={run.id}>
                  <TableCell>{run.id}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
                  </TableCell>
                  <TableCell>{run.model_type}</TableCell>
                  <TableCell>{run.records_processed || 0}</TableCell>
                  <TableCell>{run.started_at ? new Date(run.started_at).toLocaleString() : '\u2014'}</TableCell>
                  <TableCell>{run.completed_at ? new Date(run.completed_at).toLocaleString() : '\u2014'}</TableCell>
                  <TableCell className="space-x-2">
                    <Button size="sm" variant="outline" onClick={() => reExecuteRun(run.id)} disabled={loading}>
                      Run
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => publishRun(run.id)}
                      disabled={loading || !['completed', 'published'].includes(run.status)}
                    >
                      Publish
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {runs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    No runs yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
};

export default ForecastPipelineManager;
