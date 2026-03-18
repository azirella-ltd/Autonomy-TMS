import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Button,
  NativeSelect,
  SelectOption,
  FormField,
  Input,
  Alert,
  Badge,
  Progress,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHead,
  TableRow,
} from '../common';
import { cn } from '../../lib/utils/cn';
import {
  Play as PlayIcon,
  Square as StopIcon,
  RefreshCw as RefreshIcon,
  ChevronDown as ExpandMoreIcon,
  CheckCircle as CheckCircleIcon,
  XCircle as ErrorIcon,
  Clock as ScheduleIcon,
  Hourglass as PendingIcon,
  Lightbulb,
  Minus as DashIcon,
} from 'lucide-react';
import trmApi from '../../services/trmApi';
import { api } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';

// Simple tooltip wrapper
const Tooltip = ({ children, title }) => (
  <div className="group relative inline-block">
    {children}
    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 text-xs bg-foreground text-background rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-10">
      {title}
    </div>
  </div>
);

// Phase dot indicator: ● done, ◐ training, ○ pending, — N/A
const PhaseDot = ({ status }) => {
  switch (status) {
    case 'completed':
      return <span className="text-emerald-500 text-lg" title="Completed">●</span>;
    case 'training':
      return <span className="text-blue-500 text-lg animate-pulse" title="Training">◐</span>;
    case 'failed':
      return <span className="text-red-500 text-lg" title="Failed">●</span>;
    case 'not_applicable':
      return <span className="text-muted-foreground" title="N/A">—</span>;
    default:
      return <span className="text-muted-foreground text-lg" title="Pending">○</span>;
  }
};

// TRM type display names
const TRM_LABELS = {
  atp_executor: 'ATP',
  po_creation: 'PO',
  inventory_buffer: 'IB',
  rebalancing: 'Rebal',
  order_tracking: 'OT',
};

const TRM_FULL_NAMES = {
  atp_executor: 'ATP Executor',
  po_creation: 'PO Creation',
  inventory_buffer: 'Inventory Buffer',
  rebalancing: 'Inventory Rebalancing',
  order_tracking: 'Order Tracking',
};

const TRMTrainingPanelEnhanced = () => {
  const { user } = useAuth();
  // ADH training configs
  const [powellConfigs, setPowellConfigs] = useState([]);
  const [selectedConfigId, setSelectedConfigId] = useState(null);
  const [configsLoading, setConfigsLoading] = useState(true);

  // Per-site training data
  const [sites, setSites] = useState([]);
  const [sitesLoading, setSitesLoading] = useState(false);

  // Training controls
  const [scope, setScope] = useState('all'); // 'all' or 'selected'
  const [selectedSiteId, setSelectedSiteId] = useState(null);
  const [phaseFilter, setPhaseFilter] = useState('all'); // 'all', '1', '2', '3'
  const [epochs, setEpochs] = useState(20);

  // Status
  const [training, setTraining] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Load ADH training configs on mount
  useEffect(() => {
    const loadConfigs = async () => {
      setConfigsLoading(true);
      try {
        // Load from ADH training configs API
        const tenantId = user?.tenant_id || 1;
        const response = await api.get('/powell-training/configs', {
          params: { tenant_id: tenantId, include_inactive: false }
        });
        const configs = response.data || [];
        setPowellConfigs(configs);
        if (configs.length > 0) {
          setSelectedConfigId(configs[0].id);
        }
      } catch (err) {
        console.error('Failed to load ADH configs:', err);
        // Fallback: try loading supply chain configs directly
        try {
          const fallbackResponse = await api.get('/supply-chain-config/');
          const scConfigs = fallbackResponse.data.items || fallbackResponse.data || [];
          // Convert to minimal ADH config shape
          setPowellConfigs(scConfigs.map(sc => ({
            id: sc.id,
            name: sc.name,
            config_id: sc.id,
          })));
          if (scConfigs.length > 0) {
            // Auto-select root baseline config (no parent, BASELINE type)
            const root = scConfigs.find(c => !c.parent_config_id && c.scenario_type === 'BASELINE')
              || scConfigs.find(c => c.is_active)
              || scConfigs[0];
            setSelectedConfigId(root.id);
          }
        } catch {
          setError('Failed to load training configurations');
        }
      } finally {
        setConfigsLoading(false);
      }
    };
    loadConfigs();
  }, [user?.tenant_id]);

  // Load sites when config changes
  const loadSites = useCallback(async () => {
    if (!selectedConfigId) return;
    setSitesLoading(true);
    try {
      const data = await trmApi.listTrainingSites(selectedConfigId);
      setSites(data || []);
    } catch (err) {
      console.error('Failed to load training sites:', err);
      setSites([]);
    } finally {
      setSitesLoading(false);
    }
  }, [selectedConfigId]);

  useEffect(() => {
    loadSites();
  }, [loadSites]);

  // Calculate overall progress for a site
  const getSiteOverall = (site) => {
    if (!site.trm_configs || site.trm_configs.length === 0) return 0;
    let total = 0;
    let completed = 0;
    for (const tc of site.trm_configs) {
      for (const phase of ['phase1_status', 'phase2_status', 'phase3_status']) {
        if (tc[phase] !== 'not_applicable') {
          total++;
          if (tc[phase] === 'completed') completed++;
        }
      }
    }
    return total > 0 ? Math.round((completed / total) * 100) : 0;
  };

  const handleStartTraining = async () => {
    setError(null);
    setSuccess(null);
    setTraining(true);

    const config = {
      phases: phaseFilter === 'all' ? null : [parseInt(phaseFilter)],
      epochs: epochs,
    };

    try {
      let result;
      if (scope === 'selected' && selectedSiteId) {
        result = await trmApi.trainSite(selectedConfigId, selectedSiteId, config);
        setSuccess(`Training completed for site ${selectedSiteId}`);
      } else {
        result = await trmApi.trainAllSites(selectedConfigId, config);
        setSuccess(`Training completed: ${result.completed}/${result.total_pairs} site-agent pairs`);
      }
      // Refresh site data
      await loadSites();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Training failed');
    } finally {
      setTraining(false);
    }
  };

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Per-Site Agent Training
      </Typography>
      <Typography variant="body2" color="textSecondary" className="mb-4">
        Train AI agents for each site using the 3-phase learning-depth curriculum.
        Each site gets models tailored to its specific patterns and scale.
      </Typography>

      {error && (
        <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Training Controls */}
        <Card padding="default">
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Training Controls
            </Typography>

            <FormField label="Training Configuration" className="mb-4">
              {configsLoading ? (
                <div className="flex items-center gap-2 py-2">
                  <Spinner size="sm" />
                  <span className="text-sm text-muted-foreground">Loading...</span>
                </div>
              ) : (
                <NativeSelect
                  value={selectedConfigId || ''}
                  onChange={(e) => setSelectedConfigId(parseInt(e.target.value))}
                  disabled={training}
                >
                  {powellConfigs.map(cfg => (
                    <SelectOption key={cfg.id} value={cfg.id}>
                      {cfg.name}
                    </SelectOption>
                  ))}
                </NativeSelect>
              )}
            </FormField>

            <FormField label="Scope" className="mb-4">
              <NativeSelect
                value={scope}
                onChange={(e) => setScope(e.target.value)}
                disabled={training}
              >
                <SelectOption value="all">All Sites</SelectOption>
                <SelectOption value="selected">Selected Site</SelectOption>
              </NativeSelect>
            </FormField>

            {scope === 'selected' && (
              <FormField label="Site" className="mb-4">
                <NativeSelect
                  value={selectedSiteId || ''}
                  onChange={(e) => setSelectedSiteId(parseInt(e.target.value))}
                  disabled={training}
                >
                  <SelectOption value="">Select a site...</SelectOption>
                  {sites.map(site => (
                    <SelectOption key={site.site_id} value={site.site_id}>
                      {site.site_name} ({site.master_type})
                    </SelectOption>
                  ))}
                </NativeSelect>
              </FormField>
            )}

            <FormField label="Phase" className="mb-4">
              <NativeSelect
                value={phaseFilter}
                onChange={(e) => setPhaseFilter(e.target.value)}
                disabled={training}
              >
                <SelectOption value="all">All Phases</SelectOption>
                <SelectOption value="1">Phase 1: Engine Imitation (BC)</SelectOption>
                <SelectOption value="2">Phase 2: Context Learning (Supervised)</SelectOption>
                <SelectOption value="3">Phase 3: Outcome Optimization (RL)</SelectOption>
              </NativeSelect>
            </FormField>

            <FormField label="Epochs" className="mb-4">
              <Input
                type="number"
                value={epochs}
                onChange={(e) => setEpochs(parseInt(e.target.value))}
                disabled={training}
                min={1}
                max={200}
              />
            </FormField>

            <div className="mt-6">
              <Button
                variant="default"
                leftIcon={training ? <Spinner size="sm" /> : <PlayIcon className="h-4 w-4" />}
                onClick={handleStartTraining}
                disabled={training || !selectedConfigId}
                fullWidth
              >
                {training ? 'Training...' : scope === 'all' ? 'Train All Sites' : 'Train Selected Site'}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Quick Start Guide */}
        <Card className="bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 mb-3">
              <Lightbulb className="h-5 w-5 text-blue-600" />
              <Typography variant="h6">Learning-Depth Curriculum</Typography>
            </div>
            <Typography variant="body2" className="mb-3">
              Each site-agent pair trains through 3 progressive phases based on data availability:
            </Typography>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Phase</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Data Source</TableHead>
                  <TableHead>Prereq</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell><Badge variant="secondary">1</Badge></TableCell>
                  <TableCell>Engine Imitation</TableCell>
                  <TableCell>Curriculum generator + deterministic engines</TableCell>
                  <TableCell>Always available</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Badge variant="secondary">2</Badge></TableCell>
                  <TableCell>Context Learning</TableCell>
                  <TableCell>Human expert override decision logs</TableCell>
                  <TableCell>≥500 expert decisions</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Badge variant="secondary">3</Badge></TableCell>
                  <TableCell>Outcome Optimization</TableCell>
                  <TableCell>Replay buffer with measured outcomes</TableCell>
                  <TableCell>≥1000 outcome records</TableCell>
                </TableRow>
              </TableBody>
            </Table>
            <Typography variant="caption" className="text-muted-foreground mt-3 block">
              <strong>Agent Applicability:</strong> Inventory sites get all 5 agents.
              Manufacturer sites get 4 (no Rebalancing).
              Market sites don&apos;t use agents.
            </Typography>
          </CardContent>
        </Card>

        {/* Per-Site Progress Grid */}
        <div className="lg:col-span-2">
          <Card padding="default">
            <CardContent>
              <div className="flex justify-between items-center mb-4">
                <Typography variant="h6">Per-Site Training Progress</Typography>
                <Button
                  variant="ghost"
                  size="sm"
                  leftIcon={<RefreshIcon className="h-4 w-4" />}
                  onClick={loadSites}
                  disabled={sitesLoading}
                >
                  Refresh
                </Button>
              </div>

              {sitesLoading ? (
                <div className="flex justify-center p-6">
                  <Spinner size="md" />
                </div>
              ) : sites.length === 0 ? (
                <Alert variant="info">
                  No operational sites found. Generate synthetic data first, then sites will auto-populate here.
                </Alert>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Site</TableHead>
                        <TableHead>Type</TableHead>
                        {Object.entries(TRM_LABELS).map(([key, label]) => (
                          <TableHead key={key} className="text-center">
                            <Tooltip title={TRM_FULL_NAMES[key]}>
                              <span>{label}</span>
                            </Tooltip>
                          </TableHead>
                        ))}
                        <TableHead className="text-center">Overall</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {sites.map(site => {
                        const overall = getSiteOverall(site);
                        // Build a map of trm_type -> config for quick lookup
                        const trmMap = {};
                        for (const tc of (site.trm_configs || [])) {
                          trmMap[tc.trm_type] = tc;
                        }

                        return (
                          <TableRow
                            key={site.site_id}
                            className={cn(
                              "cursor-pointer hover:bg-muted/50",
                              selectedSiteId === site.site_id && "bg-muted/30"
                            )}
                            onClick={() => {
                              setSelectedSiteId(site.site_id);
                              setScope('selected');
                            }}
                          >
                            <TableCell>
                              <Typography variant="body2" className="font-semibold">
                                {site.site_name}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline" className="text-xs">
                                {site.master_type}
                              </Badge>
                            </TableCell>
                            {Object.keys(TRM_LABELS).map(trmType => {
                              const tc = trmMap[trmType];
                              if (!tc) {
                                // TRM not applicable for this site
                                return (
                                  <TableCell key={trmType} className="text-center">
                                    <span className="text-muted-foreground">—</span>
                                  </TableCell>
                                );
                              }
                              return (
                                <TableCell key={trmType} className="text-center">
                                  <Tooltip title={`P1:${tc.phase1_status} P2:${tc.phase2_status} P3:${tc.phase3_status}`}>
                                    <span className="inline-flex gap-0.5">
                                      <PhaseDot status={tc.phase1_status} />
                                      <PhaseDot status={tc.phase2_status} />
                                      <PhaseDot status={tc.phase3_status} />
                                    </span>
                                  </Tooltip>
                                </TableCell>
                              );
                            })}
                            <TableCell className="text-center">
                              <div className="flex items-center gap-2">
                                <Progress value={overall} className="flex-grow h-2" size="sm" />
                                <Typography variant="caption">{overall}%</Typography>
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default TRMTrainingPanelEnhanced;
