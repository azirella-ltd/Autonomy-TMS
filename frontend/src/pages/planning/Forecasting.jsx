import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Card,
  CardContent,
  Alert,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '../../components/common';
import {
  TrendingUp,
  CheckCircle,
  Clock,
  BarChart3,
  GitBranch,
} from 'lucide-react';
import ForecastPipelineManager from '../../components/demand-planning/ForecastPipelineManager';
import { api } from '../../services/api';

const BUCKET_LABELS = { D: 'Daily', W: 'Weekly', M: 'Monthly' };

const Forecasting = () => {
  const [configs, setConfigs] = useState([]);
  const [selectedConfig, setSelectedConfig] = useState('');
  const [pipelineConfigs, setPipelineConfigs] = useState([]);
  const [error, setError] = useState(null);

  const loadConfigs = useCallback(async () => {
    try {
      const res = await api.get('/supply-chain-config/');
      const items = res.data.items || res.data || [];
      setConfigs(items);
      if (items.length > 0 && !selectedConfig) {
        const root = items.find(c => !c.parent_config_id && c.scenario_type === 'BASELINE')
          || items.find(c => c.is_active)
          || items[0];
        setSelectedConfig(root.id.toString());
      }
    } catch (err) {
      console.error('Failed to load configs:', err);
      setError('Failed to load supply chain configurations.');
    }
  }, [selectedConfig]);

  useEffect(() => { loadConfigs(); }, [loadConfigs]);

  // Fetch pipeline configs for the selected SC config to populate overview cards
  useEffect(() => {
    if (!selectedConfig) { setPipelineConfigs([]); return; }
    api.get('/forecast-pipeline/configs', { params: { config_id: Number(selectedConfig) } })
      .then((res) => setPipelineConfigs(res.data || []))
      .catch(() => setPipelineConfigs([]));
  }, [selectedConfig]);

  // Use the first active pipeline config for overview cards
  const activePipeline = useMemo(() => {
    if (pipelineConfigs.length === 0) return null;
    return pipelineConfigs.find(c => c.is_active) || pipelineConfigs[0];
  }, [pipelineConfigs]);

  const selectedConfigObj = useMemo(
    () => configs.find(c => c.id.toString() === selectedConfig),
    [configs, selectedConfig]
  );

  const modelLabel = activePipeline?.model_type?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) || 'Not Configured';
  const clusterLabel = activePipeline?.cluster_selection_method || '\u2014';
  const cadenceLabel = activePipeline ? (BUCKET_LABELS[activePipeline.time_bucket] || activePipeline.time_bucket) : '\u2014';
  const metricLabel = activePipeline ? (activePipeline.forecast_metric || 'wape').toUpperCase() : '\u2014';

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Forecasting</h1>
          <p className="text-sm text-muted-foreground mt-1">
            ML-based statistical forecast generation, clustering, and publishing
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Select value={selectedConfig} onValueChange={setSelectedConfig}>
            <SelectTrigger className="w-[220px]">
              <SelectValue placeholder="Select Configuration" />
            </SelectTrigger>
            <SelectContent>
              {configs.map((c) => (
                <SelectItem key={c.id} value={c.id.toString()}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {error && (
        <Alert variant="error" onClose={() => setError(null)} className="mb-4">
          {error}
        </Alert>
      )}

      {/* Overview cards — driven by active pipeline config */}
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

      {/* Pipeline Manager */}
      {selectedConfig ? (
        <ForecastPipelineManager
          configId={Number(selectedConfig)}
          configName={selectedConfigObj?.name}
        />
      ) : (
        <Card>
          <CardContent className="pt-4 text-center py-8">
            <p className="text-muted-foreground">Select a supply chain configuration to manage forecast pipelines</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default Forecasting;
