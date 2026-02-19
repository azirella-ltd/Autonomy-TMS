import React, { useEffect, useMemo, useState } from 'react';
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
} from '../common';
import { api } from '../../services/api';

const defaultConfig = {
  name: 'Default Forecast Pipeline',
  description: 'Cluster + forecast + publish',
  time_bucket: 'W',
  forecast_horizon: 8,
  min_clusters: 2,
  max_clusters: 8,
  min_observations: 12,
};

const ForecastPipelineManager = ({ configId }) => {
  const [configs, setConfigs] = useState([]);
  const [runs, setRuns] = useState([]);
  const [selectedConfigId, setSelectedConfigId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [createForm, setCreateForm] = useState(defaultConfig);

  const resolvedConfigId = useMemo(() => {
    if (selectedConfigId) return Number(selectedConfigId);
    return configId || undefined;
  }, [selectedConfigId, configId]);

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

  useEffect(() => {
    loadConfigs();
  }, [configId]);

  useEffect(() => {
    loadRuns();
  }, [resolvedConfigId]);

  const createPipelineConfig = async () => {
    if (!configId) {
      setError('Select a supply chain config first');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.post('/forecast-pipeline/configs', {
        ...createForm,
        config_id: configId,
      });
      setSuccess('Pipeline config created');
      setCreateForm(defaultConfig);
      await loadConfigs();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create pipeline config');
    } finally {
      setLoading(false);
    }
  };

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

  return (
    <div className="space-y-4">
      {error && <Alert variant="error" onClose={() => setError(null)}>{error}</Alert>}
      {success && <Alert variant="success" onClose={() => setSuccess(null)}>{success}</Alert>}

      <Card>
        <CardHeader>
          <CardTitle>Pipeline Controls</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <Label>Pipeline Config</Label>
              <Select value={selectedConfigId} onValueChange={setSelectedConfigId}>
                <SelectTrigger className="mt-1">
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
              <Label>Source Config ID</Label>
              <Input value={configId || ''} disabled className="mt-1" />
            </div>
            <div className="flex items-end">
              <Button onClick={startRun} disabled={loading}>Start Run</Button>
            </div>
            <div className="flex items-end">
              <Button variant="outline" onClick={loadRuns} disabled={loading}>Refresh Runs</Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {configs.length === 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Create Pipeline Config</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <Label>Name</Label>
              <Input
                className="mt-1"
                value={createForm.name}
                onChange={(e) => setCreateForm((p) => ({ ...p, name: e.target.value }))}
              />
            </div>
            <div>
              <Label>Time Bucket (D/W/M)</Label>
              <Input
                className="mt-1"
                value={createForm.time_bucket}
                onChange={(e) => setCreateForm((p) => ({ ...p, time_bucket: e.target.value.toUpperCase() }))}
              />
            </div>
            <div>
              <Label>Forecast Horizon</Label>
              <Input
                className="mt-1"
                type="number"
                value={createForm.forecast_horizon}
                onChange={(e) => setCreateForm((p) => ({ ...p, forecast_horizon: Number(e.target.value) }))}
              />
            </div>
            <div>
              <Label>Min Clusters</Label>
              <Input
                className="mt-1"
                type="number"
                value={createForm.min_clusters}
                onChange={(e) => setCreateForm((p) => ({ ...p, min_clusters: Number(e.target.value) }))}
              />
            </div>
            <div>
              <Label>Max Clusters</Label>
              <Input
                className="mt-1"
                type="number"
                value={createForm.max_clusters}
                onChange={(e) => setCreateForm((p) => ({ ...p, max_clusters: Number(e.target.value) }))}
              />
            </div>
            <div className="flex items-end">
              <Button onClick={createPipelineConfig} disabled={loading}>Create</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Run History</CardTitle>
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
                  <TableCell>{run.started_at ? new Date(run.started_at).toLocaleString() : '—'}</TableCell>
                  <TableCell>{run.completed_at ? new Date(run.completed_at).toLocaleString() : '—'}</TableCell>
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
