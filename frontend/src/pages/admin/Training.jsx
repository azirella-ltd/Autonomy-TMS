import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Card,
  CardContent,
  Button,
  Input,
  Label,
  Alert,
  Switch,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Textarea,
} from '../../components/common';
import PageLayout from '../../components/PageLayout';
import simulationApi from '../../services/api';

const DEFAULT_RANGES = {
  supply_leadtime: [0, 6],
  order_leadtime: [0, 6],
  init_inventory: [4, 60],
  holding_cost: [0.1, 2.0],
  backlog_cost: [0.2, 4.0],
  max_inbound_per_link: [50, 300],
  max_order: [50, 300],
};

const formatRangeLabel = (key) => key.replaceAll('_', ' ');

const TrainingPanel = () => {
  const [serverHost, setServerHost] = useState('aiserver.local');
  const [source, setSource] = useState('sim');
  const [windowSize, setWindowSize] = useState(12);
  const [horizon, setHorizon] = useState(1);
  const [epochs, setEpochs] = useState(10);
  const [device, setDevice] = useState('cpu');
  const [dataPath, setDataPath] = useState('');
  const [stepsTable, setStepsTable] = useState('simulation_steps');
  const [dbUrl, setDbUrl] = useState('');
  const [useSimpy, setUseSimpy] = useState(true);
  const [simAlpha, setSimAlpha] = useState(0.3);
  const [simWipK, setSimWipK] = useState(1.0);
  const [ranges, setRanges] = useState(DEFAULT_RANGES);
  const [job, setJob] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info' });
  const [working, setWorking] = useState({ generate: false, train: false, stop: false });

  const showMessage = useCallback((message, severity = 'info') => {
    setSnackbar({ open: true, message, severity });
    setTimeout(() => setSnackbar((prev) => ({ ...prev, open: false })), 4000);
  }, []);

  const numericValue = useCallback((value, fallback = 0) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }, []);

  const handleRangeChange = useCallback((key, index, value) => {
    setRanges((prev) => {
      const next = [...(prev[key] || [0, 0])];
      next[index] = value;
      return { ...prev, [key]: next };
    });
  }, []);

  const generateDataset = useCallback(async () => {
    setWorking((prev) => ({ ...prev, generate: true }));
    try {
      const param_ranges = Object.fromEntries(
        Object.entries(ranges).map(([key, pair]) => [
          key,
          [numericValue(pair?.[0], 0), numericValue(pair?.[1], 0)],
        ]),
      );

      const payload = {
        num_runs: 64,
        T: 64,
        window: numericValue(windowSize, 12),
        horizon: numericValue(horizon, 1),
        param_ranges,
        use_simpy: useSimpy,
        sim_alpha: numericValue(simAlpha, 0.3),
        sim_wip_k: numericValue(simWipK, 1.0),
      };

      const result = await simulationApi.generateData(payload);
      setDataPath(result?.path || '');
      showMessage(result?.path ? `Dataset generated at ${result.path}` : 'Dataset generated', 'success');
    } catch (error) {
      setDataPath('');
      showMessage(error?.response?.data?.detail || error?.message || 'Failed to generate data', 'error');
    } finally {
      setWorking((prev) => ({ ...prev, generate: false }));
    }
  }, [ranges, windowSize, horizon, useSimpy, simAlpha, simWipK, numericValue, showMessage]);

  const launchTraining = useCallback(async () => {
    setWorking((prev) => ({ ...prev, train: true }));
    try {
      const payload = {
        server_host: serverHost,
        source,
        window: numericValue(windowSize, 12),
        horizon: numericValue(horizon, 1),
        epochs: numericValue(epochs, 10),
        device,
        steps_table: stepsTable,
        db_url: dbUrl || undefined,
      };
      const result = await simulationApi.trainModel(payload);
      setJob(result);
      showMessage(result?.note || 'Training started', 'success');
    } catch (error) {
      showMessage(error?.response?.data?.detail || error?.message || 'Failed to start training', 'error');
    } finally {
      setWorking((prev) => ({ ...prev, train: false }));
    }
  }, [serverHost, source, windowSize, horizon, epochs, device, stepsTable, dbUrl, numericValue, showMessage]);

  const stopTraining = useCallback(async () => {
    if (!job?.job_id) return;
    setWorking((prev) => ({ ...prev, stop: true }));
    try {
      await simulationApi.stopJob(job.job_id);
      showMessage('Training job stopped', 'info');
    } catch (error) {
      showMessage(error?.response?.data?.detail || error?.message || 'Failed to stop job', 'error');
    } finally {
      setWorking((prev) => ({ ...prev, stop: false }));
    }
  }, [job?.job_id, showMessage]);

  useEffect(() => {
    let timer;
    const poll = async () => {
      if (!job?.job_id) return;
      try {
        const status = await simulationApi.getJobStatus(job.job_id);
        setJobStatus(status);
        if (status?.running) {
          timer = setTimeout(poll, 2500);
        }
      } catch (error) {
        setJobStatus(null);
      }
    };
    poll();
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [job?.job_id]);

  const jobActive = Boolean(job?.job_id && jobStatus?.running);

  const datasetSummary = useMemo(() => {
    if (!dataPath) return null;
    return (
      <Alert variant="success" className="mt-4">
        Dataset available at <strong>{dataPath}</strong>
      </Alert>
    );
  }, [dataPath]);

  return (
    <Card>
      <CardContent className="p-6">
        <h2 className="text-xl font-bold mb-1">Autonomy Agent Training</h2>
        <p className="text-sm text-muted-foreground mb-6">
          Generate synthetic datasets and launch training jobs for the Autonomy agent. All actions run on the backend service.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div>
              <Label>Server Host</Label>
              <Input
                value={serverHost}
                onChange={(e) => setServerHost(e.target.value)}
              />
            </div>
            <div>
              <Label>Source</Label>
              <Select value={source} onValueChange={setSource}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="sim">Simulator</SelectItem>
                  <SelectItem value="db">Database</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {source === 'db' && (
              <>
                <div>
                  <Label>Database URL</Label>
                  <Input
                    value={dbUrl}
                    onChange={(e) => setDbUrl(e.target.value)}
                    placeholder="mysql+pymysql://user:pass@host/db"
                  />
                </div>
                <div>
                  <Label>Steps Table</Label>
                  <Input
                    value={stepsTable}
                    onChange={(e) => setStepsTable(e.target.value)}
                  />
                </div>
              </>
            )}
          </div>

          <div className="space-y-4">
            <div>
              <Label>Window</Label>
              <Input
                type="number"
                min={1}
                max={128}
                value={windowSize}
                onChange={(e) => setWindowSize(e.target.value)}
              />
            </div>
            <div>
              <Label>Horizon</Label>
              <Input
                type="number"
                min={1}
                max={8}
                value={horizon}
                onChange={(e) => setHorizon(e.target.value)}
              />
            </div>
            <div>
              <Label>Epochs</Label>
              <Input
                type="number"
                min={1}
                max={500}
                value={epochs}
                onChange={(e) => setEpochs(e.target.value)}
              />
            </div>
            <div>
              <Label>Device</Label>
              <Select value={device} onValueChange={setDevice}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cpu">CPU</SelectItem>
                  <SelectItem value="cuda">GPU</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        <hr className="my-6" />

        <h3 className="font-semibold mb-4">Simulation Settings</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <div className="flex items-center gap-2">
            <Switch checked={useSimpy} onCheckedChange={setUseSimpy} />
            <Label>Use SimPy</Label>
          </div>
          <div>
            <Label>Smoothing Alpha</Label>
            <Input
              type="number"
              step={0.05}
              min={0}
              max={1}
              value={simAlpha}
              onChange={(e) => setSimAlpha(e.target.value)}
            />
          </div>
          <div>
            <Label>WIP Gain</Label>
            <Input
              type="number"
              step={0.1}
              min={0}
              max={5}
              value={simWipK}
              onChange={(e) => setSimWipK(e.target.value)}
            />
          </div>
        </div>

        <h3 className="font-semibold mb-4">Parameter Ranges</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {Object.entries(ranges).map(([key, pair]) => (
            <div key={key} className="flex items-center gap-2">
              <span className="min-w-[160px] capitalize">{formatRangeLabel(key)}</span>
              <Input
                type="number"
                className="w-24"
                placeholder="Min"
                value={pair?.[0] ?? ''}
                onChange={(e) => handleRangeChange(key, 0, e.target.value)}
              />
              <Input
                type="number"
                className="w-24"
                placeholder="Max"
                value={pair?.[1] ?? ''}
                onChange={(e) => handleRangeChange(key, 1, e.target.value)}
              />
            </div>
          ))}
        </div>

        {datasetSummary}

        <div className="flex justify-end gap-2 mt-6">
          <Button
            variant="outline"
            onClick={generateDataset}
            disabled={working.generate}
          >
            {working.generate ? 'Generating…' : 'Generate Data'}
          </Button>
          <Button
            onClick={launchTraining}
            disabled={working.train || !dataPath}
          >
            {working.train ? 'Starting…' : 'Launch Training'}
          </Button>
          {jobActive && (
            <Button
              variant="outline"
              onClick={stopTraining}
              disabled={working.stop}
              className="text-destructive border-destructive"
            >
              {working.stop ? 'Stopping…' : 'Stop'}
            </Button>
          )}
        </div>

        {job && (
          <div className="mt-6">
            <h3 className="font-semibold mb-2">Job Details</h3>
            <p className="text-sm">Job ID: {job.job_id || '—'}</p>
            {job.cmd && (
              <p className="text-sm mt-1">
                Command: <code className="bg-muted px-1 rounded">{job.cmd}</code>
              </p>
            )}
            {job.note && (
              <Alert variant="info" className="mt-2">{job.note}</Alert>
            )}
            {jobStatus && (
              <Card className="mt-4">
                <CardContent className="pt-4">
                  <h4 className="font-semibold mb-2">Status</h4>
                  <p className="text-sm">Running: {String(jobStatus.running)}</p>
                  <p className="text-sm">PID: {jobStatus.pid || '—'}</p>
                  {jobStatus.log_tail && (
                    <div className="mt-4">
                      <Label>Log Tail</Label>
                      <Textarea
                        value={jobStatus.log_tail}
                        readOnly
                        rows={6}
                        className="font-mono text-xs"
                      />
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {snackbar.open && (
          <Alert variant={snackbar.severity === 'error' ? 'destructive' : snackbar.severity} className="mt-4">
            {snackbar.message}
          </Alert>
        )}
      </CardContent>
    </Card>
  );
};

const Training = () => (
  <PageLayout title="Autonomy Agent Training">
    <TrainingPanel />
  </PageLayout>
);

export { TrainingPanel };
export default Training;
