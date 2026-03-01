/**
 * GraphSAGE Dashboard Page
 *
 * S&OP-level GraphSAGE training and analysis.
 * Distinct from the execution tGNN: operates at aggregated hierarchy levels
 * (Country × Family, Monthly) to compute policy parameters θ (CFA).
 *
 * Outputs: criticality_score, bottleneck_risk, concentration_risk,
 *          resilience_score, safety_stock_multiplier, network_risk
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
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
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Progress,
  Spinner,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../../components/common';
import {
  ChevronRight,
  Play,
  RefreshCw,
  Network,
  Shield,
  AlertTriangle,
  Activity,
  Target,
  TrendingUp,
  CheckCircle,
  Clock,
  Cpu,
  Layers,
  Download,
} from 'lucide-react';
import { api } from '../../services/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const formatLoss = (v) => (v != null ? v.toFixed(6) : '—');
const formatScore = (v) => (v != null ? v.toFixed(3) : '—');

const phaseLabel = (phase) => {
  const map = {
    loading_config: 'Loading Config',
    generating_data: 'Generating Data',
    training_sop: 'Training S&OP GraphSAGE',
    training_tgnn: 'Training Execution tGNN',
    training_trm: 'Training TRM Agents',
    completed: 'Completed',
    failed: 'Failed',
  };
  return map[phase] || phase || '—';
};

const statusVariant = (status) => {
  if (status === 'completed') return 'success';
  if (status === 'running' || status === 'training') return 'warning';
  if (status === 'failed') return 'destructive';
  return 'secondary';
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const GraphSAGEDashboard = () => {
  // Config selection
  const [scConfigs, setScConfigs] = useState([]);
  const [selectedScConfig, setSelectedScConfig] = useState('');
  const [powellConfigs, setPowellConfigs] = useState([]);
  const [selectedPowellConfig, setSelectedPowellConfig] = useState(null);

  // Training state
  const [runs, setRuns] = useState([]);
  const [activeRun, setActiveRun] = useState(null);
  const [training, setTraining] = useState(false);

  // Create config form
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createForm, setCreateForm] = useState({
    name: 'S&OP GraphSAGE',
    description: 'S&OP-level network analysis and risk scoring',
    sop_hidden_dim: 128,
    sop_embedding_dim: 64,
    sop_num_layers: 3,
    sop_epochs: 50,
    sop_learning_rate: 0.001,
    num_simulation_runs: 128,
    timesteps_per_run: 64,
    train_sop_graphsage: true,
    train_execution_tgnn: false,
  });

  // UI
  const [tabValue, setTabValue] = useState('train');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Polling ref
  const pollRef = useRef(null);

  // -----------------------------------------------------------------------
  // Data loading
  // -----------------------------------------------------------------------

  const loadScConfigs = useCallback(async () => {
    try {
      const res = await api.get('/supply-chain-config/');
      const items = res.data.items || res.data || [];
      setScConfigs(items);
      if (items.length > 0 && !selectedScConfig) {
        // Auto-select root baseline config (no parent, BASELINE type)
        const root = items.find(c => !c.parent_config_id && c.scenario_type === 'BASELINE')
          || items.find(c => c.is_active)
          || items[0];
        setSelectedScConfig(root.id.toString());
      }
    } catch (err) {
      console.error('Failed to load SC configs:', err);
    }
  }, [selectedScConfig]);

  const loadPowellConfigs = useCallback(async () => {
    if (!selectedScConfig) return;
    try {
      const res = await api.get('/powell-training/configs');
      const all = res.data || [];
      // Filter configs matching the selected SC config
      const matching = all.filter(
        (c) => c.config_id === Number(selectedScConfig) && c.train_sop_graphsage
      );
      setPowellConfigs(matching);
      if (matching.length > 0 && !selectedPowellConfig) {
        setSelectedPowellConfig(matching[0]);
      } else if (matching.length > 0) {
        // Update if the current selection is stale
        const updated = matching.find((c) => c.id === selectedPowellConfig?.id);
        if (updated) setSelectedPowellConfig(updated);
      }
    } catch (err) {
      console.error('Failed to load ADH configs:', err);
    }
  }, [selectedScConfig, selectedPowellConfig]);

  const loadRuns = useCallback(async () => {
    if (!selectedPowellConfig) return;
    try {
      const res = await api.get(`/powell-training/configs/${selectedPowellConfig.id}/runs`);
      const data = res.data || [];
      setRuns(data);
      // Find active run
      const active = data.find((r) => r.status === 'running' || r.status === 'training');
      setActiveRun(active || null);
      setTraining(!!active);
    } catch (err) {
      console.error('Failed to load runs:', err);
    }
  }, [selectedPowellConfig]);

  useEffect(() => { loadScConfigs(); }, [loadScConfigs]);
  useEffect(() => { loadPowellConfigs(); }, [selectedScConfig, loadPowellConfigs]);
  useEffect(() => { loadRuns(); }, [selectedPowellConfig, loadRuns]);

  // Poll for active training
  useEffect(() => {
    if (training && selectedPowellConfig) {
      pollRef.current = setInterval(loadRuns, 5000);
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [training, selectedPowellConfig, loadRuns]);

  // -----------------------------------------------------------------------
  // Actions
  // -----------------------------------------------------------------------

  const createConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.post('/powell-training/configs', {
        ...createForm,
        config_id: Number(selectedScConfig),
      });
      setSuccess('Training configuration created');
      setShowCreateForm(false);
      await loadPowellConfigs();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create training config');
    } finally {
      setLoading(false);
    }
  };

  const startTraining = async () => {
    if (!selectedPowellConfig) return;
    setLoading(true);
    setError(null);
    try {
      await api.post(`/powell-training/configs/${selectedPowellConfig.id}/start-training`);
      setSuccess('S&OP GraphSAGE training started');
      setTraining(true);
      await loadRuns();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start training');
    } finally {
      setLoading(false);
    }
  };

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  const latestCompletedRun = runs.find((r) => r.status === 'completed');

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
        <Link to="/" className="hover:text-foreground">Home</Link>
        <ChevronRight className="h-4 w-4" />
        <Link to="/admin?section=training" className="hover:text-foreground">AI & Agents</Link>
        <ChevronRight className="h-4 w-4" />
        <span className="text-foreground">GraphSAGE Training</span>
      </nav>

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">S&OP GraphSAGE</h1>
        <p className="text-muted-foreground">
          Medium-term network structure analysis at aggregated hierarchy levels.
          Computes policy parameters θ (CFA) — criticality scores, bottleneck risk,
          concentration risk, resilience scores, and safety stock multipliers.
        </p>
      </div>

      {/* Alerts */}
      {error && <Alert variant="error" onClose={() => setError(null)} className="mb-4">{error}</Alert>}
      {success && <Alert variant="success" onClose={() => setSuccess(null)} className="mb-4">{success}</Alert>}

      {/* Config selectors */}
      <Card className="mb-6">
        <CardContent className="pt-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <Label>Supply Chain Config</Label>
              <Select value={selectedScConfig} onValueChange={(v) => { setSelectedScConfig(v); setSelectedPowellConfig(null); }}>
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder="Select configuration" />
                </SelectTrigger>
                <SelectContent>
                  {scConfigs.map((c) => (
                    <SelectItem key={c.id} value={c.id.toString()}>{c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Training Config</Label>
              {powellConfigs.length > 0 ? (
                <Select
                  value={selectedPowellConfig?.id?.toString() || ''}
                  onValueChange={(v) => {
                    const cfg = powellConfigs.find((c) => c.id === Number(v));
                    setSelectedPowellConfig(cfg);
                  }}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder="Select training config" />
                  </SelectTrigger>
                  <SelectContent>
                    {powellConfigs.map((c) => (
                      <SelectItem key={c.id} value={c.id.toString()}>{c.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <div className="mt-1">
                  <Button variant="outline" size="sm" onClick={() => setShowCreateForm(true)}>
                    Create Training Config
                  </Button>
                </div>
              )}
            </div>
            <div className="flex items-end gap-2">
              <Button
                onClick={startTraining}
                disabled={!selectedPowellConfig || training || loading}
                leftIcon={training ? <Spinner className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              >
                {training ? 'Training...' : 'Start Training'}
              </Button>
              <Button variant="outline" onClick={loadRuns} disabled={!selectedPowellConfig}>
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Architecture info cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Policy Class</p>
                <p className="text-lg font-bold">CFA</p>
                <p className="text-xs text-muted-foreground">Cost Function Approximation</p>
              </div>
              <Target className="h-8 w-8 text-primary" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Hierarchy</p>
                <p className="text-lg font-bold">Country × Family</p>
                <p className="text-xs text-muted-foreground">Monthly time buckets</p>
              </div>
              <Layers className="h-8 w-8 text-blue-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Architecture</p>
                <p className="text-lg font-bold">3-Layer GraphSAGE</p>
                <p className="text-xs text-muted-foreground">Neighbor sampling, O(edges)</p>
              </div>
              <Network className="h-8 w-8 text-amber-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Refresh Cadence</p>
                <p className="text-lg font-bold">Weekly</p>
                <p className="text-xs text-muted-foreground">Or on topology changes</p>
              </div>
              <Clock className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs value={tabValue} onValueChange={setTabValue} className="space-y-4">
        <TabsList>
          <TabsTrigger value="train">Training</TabsTrigger>
          <TabsTrigger value="outputs">Model Outputs</TabsTrigger>
          <TabsTrigger value="config">Configuration</TabsTrigger>
        </TabsList>

        {/* ---- TAB: Training ---- */}
        <TabsContent value="train">
          {/* Active training progress */}
          {activeRun && (
            <Card className="mb-4 border-l-4 border-l-blue-500">
              <CardContent className="pt-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Spinner className="h-4 w-4" />
                    <span className="font-medium">Training in progress</span>
                    <Badge variant="warning">{phaseLabel(activeRun.current_phase)}</Badge>
                  </div>
                  <span className="text-sm text-muted-foreground">
                    Run #{activeRun.id}
                  </span>
                </div>
                <Progress value={activeRun.progress_percent || 0} className="mb-2" />
                <div className="flex gap-6 text-sm">
                  <span>Progress: <strong>{(activeRun.progress_percent || 0).toFixed(0)}%</strong></span>
                  {activeRun.sop_epochs_completed > 0 && (
                    <span>S&OP Epochs: <strong>{activeRun.sop_epochs_completed}</strong></span>
                  )}
                  {activeRun.sop_final_loss != null && (
                    <span>Loss: <strong>{formatLoss(activeRun.sop_final_loss)}</strong></span>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Run history */}
          <Card>
            <CardHeader>
              <CardTitle>Training Runs</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Run</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Phase</TableHead>
                    <TableHead>S&OP Epochs</TableHead>
                    <TableHead>S&OP Loss</TableHead>
                    <TableHead>Started</TableHead>
                    <TableHead>Completed</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                        No training runs yet. Create a config and start training.
                      </TableCell>
                    </TableRow>
                  ) : (
                    runs.map((run) => (
                      <TableRow key={run.id}>
                        <TableCell className="font-medium">#{run.id}</TableCell>
                        <TableCell>
                          <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
                        </TableCell>
                        <TableCell>{phaseLabel(run.current_phase)}</TableCell>
                        <TableCell>{run.sop_epochs_completed || '—'}</TableCell>
                        <TableCell className="font-mono">{formatLoss(run.sop_final_loss)}</TableCell>
                        <TableCell className="text-sm">
                          {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                        </TableCell>
                        <TableCell className="text-sm">
                          {run.completed_at ? new Date(run.completed_at).toLocaleString() : '—'}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---- TAB: Model Outputs ---- */}
        <TabsContent value="outputs">
          <Card className="mb-4">
            <CardHeader>
              <CardTitle>S&OP Policy Parameters (θ)</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-4">
                The GraphSAGE model computes these per-node policy parameters at the aggregated
                Country × Family level. These feed downstream to the Execution tGNN and TRM agents.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <Card>
                  <CardContent className="pt-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Activity className="h-5 w-5 text-red-500" />
                      <span className="font-medium">Criticality Score</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Node importance in the supply chain network (0–1).
                      High scores indicate nodes whose disruption cascades widely.
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">Use: Prioritize planning attention and monitoring.</p>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="pt-4">
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle className="h-5 w-5 text-amber-500" />
                      <span className="font-medium">Bottleneck Risk</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Probability of becoming a capacity constraint (0–1).
                      Considers utilization, fan-in degree, and buffer levels.
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">Use: Capacity planning focus and preemptive action.</p>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="pt-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Network className="h-5 w-5 text-blue-500" />
                      <span className="font-medium">Concentration Risk</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Single-source dependency metric (0–1).
                      High values flag nodes with few upstream alternatives.
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">Use: Trigger supplier diversification strategies.</p>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="pt-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Shield className="h-5 w-5 text-green-500" />
                      <span className="font-medium">Resilience Score</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Recovery capability after disruption (0–1).
                      Factors in alternative routes, buffer stock, and lead time flexibility.
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">Use: Buffer stock positioning and network design.</p>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="pt-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Target className="h-5 w-5 text-purple-500" />
                      <span className="font-medium">Safety Stock Multiplier</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Recommended safety stock adjustment factor (0.5–2.0).
                      Below 1.0 reduces stock; above 1.0 increases buffer.
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">Use: Dynamic safety stock calculation per inv_policy.</p>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="pt-4">
                    <div className="flex items-center gap-2 mb-2">
                      <TrendingUp className="h-5 w-5 text-indigo-500" />
                      <span className="font-medium">Network Risk</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Overall network vulnerability decomposed into supply risk,
                      demand risk, and operational risk components.
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">Use: Executive dashboard KPI and S&OP alerts.</p>
                  </CardContent>
                </Card>
              </div>
            </CardContent>
          </Card>

          {/* Data flow diagram */}
          <Card>
            <CardHeader>
              <CardTitle>Data Flow: S&OP → Execution → TRM</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3 font-mono text-sm">
                <div className="p-3 border rounded-lg bg-blue-50 dark:bg-blue-950/20">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant="info">CFA</Badge>
                    <strong>S&OP GraphSAGE</strong>
                    <span className="text-muted-foreground ml-auto">Weekly / Monthly</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Country × Family × Monthly → θ (criticality, risk, safety stock multiplier)
                  </p>
                </div>
                <div className="flex justify-center text-muted-foreground">↓ structural embeddings + policy parameters</div>
                <div className="p-3 border rounded-lg bg-amber-50 dark:bg-amber-950/20">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant="warning">VFA</Badge>
                    <strong>Execution tGNN</strong>
                    <span className="text-muted-foreground ml-auto">Daily</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Site × SKU × Daily → Priority allocations + demand forecasts
                  </p>
                </div>
                <div className="flex justify-center text-muted-foreground">↓ allocations + context</div>
                <div className="p-3 border rounded-lg bg-green-50 dark:bg-green-950/20">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant="success">VFA</Badge>
                    <strong>Narrow TRM Agents</strong>
                    <span className="text-muted-foreground ml-auto">&lt;10ms per decision</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    ATP, Rebalancing, PO Creation, Order Tracking
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---- TAB: Configuration ---- */}
        <TabsContent value="config">
          {selectedPowellConfig ? (
            <Card>
              <CardHeader>
                <CardTitle>Training Configuration: {selectedPowellConfig.name}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Hidden Dimension</p>
                    <p className="text-lg font-bold">{selectedPowellConfig.sop_hidden_dim || 128}</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Embedding Dimension</p>
                    <p className="text-lg font-bold">{selectedPowellConfig.sop_embedding_dim || 64}</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Number of Layers</p>
                    <p className="text-lg font-bold">{selectedPowellConfig.sop_num_layers || 3}</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Training Epochs</p>
                    <p className="text-lg font-bold">{selectedPowellConfig.sop_epochs || 50}</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Learning Rate</p>
                    <p className="text-lg font-bold">{selectedPowellConfig.sop_learning_rate || 0.001}</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Retrain Frequency</p>
                    <p className="text-lg font-bold">{(selectedPowellConfig.sop_retrain_frequency_hours || 168) / 24}d</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Simulation Runs</p>
                    <p className="text-lg font-bold">{selectedPowellConfig.num_simulation_runs || 128}</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">Timesteps per Run</p>
                    <p className="text-lg font-bold">{selectedPowellConfig.timesteps_per_run || 64}</p>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <p className="text-xs text-muted-foreground">S&OP Enabled</p>
                    <p className="text-lg font-bold">
                      {selectedPowellConfig.train_sop_graphsage !== false ? (
                        <Badge variant="success">Yes</Badge>
                      ) : (
                        <Badge variant="secondary">No</Badge>
                      )}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="pt-4 text-center py-8">
                <p className="text-muted-foreground mb-4">
                  No training configuration found for this supply chain config.
                </p>
                <Button onClick={() => setShowCreateForm(true)}>Create Training Config</Button>
              </CardContent>
            </Card>
          )}

          {/* Create config form */}
          {showCreateForm && (
            <Card className="mt-4">
              <CardHeader>
                <CardTitle>New S&OP GraphSAGE Training Configuration</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <div>
                    <Label>Name</Label>
                    <Input
                      className="mt-1"
                      value={createForm.name}
                      onChange={(e) => setCreateForm((p) => ({ ...p, name: e.target.value }))}
                    />
                  </div>
                  <div>
                    <Label>Hidden Dimension</Label>
                    <Input
                      className="mt-1" type="number"
                      value={createForm.sop_hidden_dim}
                      onChange={(e) => setCreateForm((p) => ({ ...p, sop_hidden_dim: Number(e.target.value) }))}
                    />
                  </div>
                  <div>
                    <Label>Embedding Dimension</Label>
                    <Input
                      className="mt-1" type="number"
                      value={createForm.sop_embedding_dim}
                      onChange={(e) => setCreateForm((p) => ({ ...p, sop_embedding_dim: Number(e.target.value) }))}
                    />
                  </div>
                  <div>
                    <Label>Number of Layers</Label>
                    <Input
                      className="mt-1" type="number"
                      value={createForm.sop_num_layers}
                      onChange={(e) => setCreateForm((p) => ({ ...p, sop_num_layers: Number(e.target.value) }))}
                    />
                  </div>
                  <div>
                    <Label>Training Epochs</Label>
                    <Input
                      className="mt-1" type="number"
                      value={createForm.sop_epochs}
                      onChange={(e) => setCreateForm((p) => ({ ...p, sop_epochs: Number(e.target.value) }))}
                    />
                  </div>
                  <div>
                    <Label>Learning Rate</Label>
                    <Input
                      className="mt-1" type="number" step="0.0001"
                      value={createForm.sop_learning_rate}
                      onChange={(e) => setCreateForm((p) => ({ ...p, sop_learning_rate: Number(e.target.value) }))}
                    />
                  </div>
                  <div>
                    <Label>Simulation Runs</Label>
                    <Input
                      className="mt-1" type="number"
                      value={createForm.num_simulation_runs}
                      onChange={(e) => setCreateForm((p) => ({ ...p, num_simulation_runs: Number(e.target.value) }))}
                    />
                  </div>
                  <div>
                    <Label>Timesteps per Run</Label>
                    <Input
                      className="mt-1" type="number"
                      value={createForm.timesteps_per_run}
                      onChange={(e) => setCreateForm((p) => ({ ...p, timesteps_per_run: Number(e.target.value) }))}
                    />
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button onClick={createConfig} disabled={loading}>
                    {loading ? <Spinner className="h-4 w-4 mr-2" /> : null}
                    Create & Save
                  </Button>
                  <Button variant="outline" onClick={() => setShowCreateForm(false)}>Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default GraphSAGEDashboard;
