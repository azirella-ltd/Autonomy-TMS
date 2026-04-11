import React, { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { isTenantAdmin as isTenantAdminUser } from '../utils/authUtils';
import simulationApi, { collaborationApi } from '../services/api';
import { getModelStatus } from '../services/modelService';
import { emitStartupNotices } from '../utils/startupNotices';
import {
  Card,
  CardContent,
  Button,
  Badge,
  Spinner,
  Alert,
  AlertTitle,
  AlertDescription,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableContainer,
  useToast,
} from '../components/common';
import {
  Play,
  Pencil,
  Trash2,
  Plus,
  Settings,
  Download,
  FlaskConical,
  User,
  RotateCcw,
  RefreshCw,
  Eye,
  Shield,
  ChevronDown,
  ChevronRight,
  Bot,
  ArrowRight,
  CheckCircle,
  Clock,
  AlertTriangle,
  DollarSign,
} from 'lucide-react';
import { cn } from '@azirella-ltd/autonomy-frontend';

const DEFAULT_CLASSIC_PARAMS = {
  initial_demand: 4,
  change_week: 6,
  final_demand: 8,
};

const normalizeClassicSummary = (pattern = {}) => {
  const params = pattern.params || {};
  const safeNumber = (value, fallback) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  };

  const initial = safeNumber(params.initial_demand, DEFAULT_CLASSIC_PARAMS.initial_demand);
  const changeWeek = safeNumber(params.change_week, DEFAULT_CLASSIC_PARAMS.change_week);
  const final = safeNumber(params.final_demand, DEFAULT_CLASSIC_PARAMS.final_demand);
  return ` (Initial: ${initial}, Change Week: ${changeWeek}, Final: ${final})`;
};

// Terminology (Feb 2026): Game -> Scenario, ScenarioUser -> User (in UI)
const ScenariosList = () => {
  const [scenarios, setScenarios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' });
  const [modelStatus, setModelStatus] = useState({ is_trained: false });
  const [loadingModelStatus, setLoadingModelStatus] = useState(true);
  const [collabScenarios, setCollabScenarios] = useState([]);
  const [collabLoading, setCollabLoading] = useState(true);
  const [expandedCollab, setExpandedCollab] = useState(null);
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const isTenantAdmin = isTenantAdminUser(user);
  const restrictLifecycleActions = isTenantAdmin;
  const scConfigBasePath = isTenantAdmin ? '/admin/tenant/supply-chain-configs' : '/supply-chain-config';
  const supervisionPathBase = '/admin?section=supervision';
  const toast = useToast();

  const goToSupervision = useCallback(
    (scenarioId) => {
      const focusParam = scenarioId ? `&focusScenarioId=${scenarioId}` : '';
      navigate(`${supervisionPathBase}${focusParam}`);
    },
    [navigate, supervisionPathBase],
  );

  const showSnackbar = useCallback((message, severity = 'info') => {
    setSnackbar({ open: true, message, severity });
    toast({ title: message, status: severity, duration: 5000 });
  }, [toast]);

  const redirectLifecycleAction = useCallback(
    (scenarioId) => {
      if (!restrictLifecycleActions) {
        return false;
      }
      goToSupervision(scenarioId);
      showSnackbar('Use the Supervision tab to start, restart, or review this scenario.', 'info');
      return true;
    },
    [restrictLifecycleActions, goToSupervision, showSnackbar],
  );

  const handleCloseSnackbar = useCallback(() => {
    setSnackbar((prev) => ({ ...prev, open: false }));
  }, []);

  useEffect(() => {
    const loadModelStatus = async () => {
      try {
        const status = await getModelStatus();
        setModelStatus(status);
      } catch (err) {
        console.error('Failed to fetch model status:', err);
      } finally {
        setLoadingModelStatus(false);
      }
    };
    loadModelStatus();
  }, []);

  const fetchScenarios = useCallback(async () => {
    try {
      setLoading(true);
      const list = await simulationApi.getScenarios();  // API uses scenarios endpoint
      setScenarios(Array.isArray(list) ? list : []);
      setError(null);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Unable to load scenarios right now.';
      setError(detail);
      setScenarios([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchScenarios();
  }, [fetchScenarios]);

  useEffect(() => {
    const fetchCollabScenarios = async () => {
      try {
        setCollabLoading(true);
        const tenantId = user?.tenant_id;
        const data = await collaborationApi.getScenarios(tenantId);
        setCollabScenarios(Array.isArray(data) ? data : []);
      } catch (err) {
        console.error('Failed to load collaboration scenarios:', err);
        setCollabScenarios([]);
      } finally {
        setCollabLoading(false);
      }
    };
    fetchCollabScenarios();
  }, [user?.tenant_id]);

  useEffect(() => {
    if (location.state?.refresh) {
      fetchScenarios();
      navigate(`${location.pathname}${location.search}`, { replace: true, state: null });
    }
  }, [location, fetchScenarios, navigate]);

  const handleStartScenario = async (scenarioId) => {
    if (redirectLifecycleAction(scenarioId)) {
      return;
    }
    try {
      const response = await simulationApi.startScenario(scenarioId);  // API uses scenarios endpoint
      showSnackbar('Scenario started successfully', 'success');
      emitStartupNotices(response, (message) => showSnackbar(message, 'warning'));
      fetchScenarios();
    } catch (error) {
      const detail = error?.response?.data?.detail || error?.message || 'Failed to start scenario';
      showSnackbar(detail, 'error');
    }
  };

  const handleResetScenario = async (scenarioId) => {
    if (redirectLifecycleAction(scenarioId)) {
      return;
    }
    try {
      await simulationApi.resetScenario(scenarioId);  // API uses scenarios endpoint
      showSnackbar('Scenario reset successfully', 'success');
      fetchScenarios();
    } catch (error) {
      const detail = error?.response?.data?.detail || error?.message || 'Unable to reset scenario';
      showSnackbar(detail, 'error');
    }
  };

  const handleRestartScenario = async (scenarioId) => {
    if (redirectLifecycleAction(scenarioId)) {
      return;
    }
    try {
      await simulationApi.resetScenario(scenarioId);
      const response = await simulationApi.startScenario(scenarioId);
      showSnackbar('Scenario restarted', 'success');
      emitStartupNotices(response, (message) => showSnackbar(message, 'warning'));
      fetchScenarios();
    } catch (error) {
      const detail = error?.response?.data?.detail || error?.message || 'Unable to restart scenario';
      showSnackbar(detail, 'error');
    }
  };

  const handleDeleteScenario = async (scenarioId) => {
    if (!window.confirm('Delete this scenario? This cannot be undone.')) {
      return;
    }
    try {
      await simulationApi.deleteScenario(scenarioId);  // API uses scenarios endpoint
      showSnackbar('Scenario deleted', 'success');
      fetchScenarios();
    } catch (error) {
      const detail = error?.response?.data?.detail || error?.message || 'Failed to delete scenario';
      showSnackbar(detail, 'error');
    }
  };

  const handleOpenEditor = (scenario) => {
    if (scenario) {
      navigate(`/scenarios/${scenario.id}/edit`);
    } else {
      navigate('/scenarios/new');
    }
  };

  useEffect(() => {
    const editId = searchParams.get('edit');
    if (!editId) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete('edit');
    setSearchParams(next, { replace: true });
    navigate(`/scenarios/${editId}/edit`);
  }, [searchParams, setSearchParams, navigate]);

  const formatDate = (dateString) => {
    if (!dateString) return '—';
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) {
      return String(dateString);
    }
    return date.toLocaleString();
  };

  const getStatusVariant = (status) => {
    switch (String(status || '').toLowerCase()) {
      case 'created':
        return 'default';
      case 'in_progress':
      case 'round_in_progress':
        return 'warning';
      case 'finished':
      case 'completed':
        return 'success';
      default:
        return 'secondary';
    }
  };

  const AutonomyAlert = () => {
    if (loadingModelStatus || !modelStatus || modelStatus.is_trained) return null;
    return (
      <Alert variant="error" className="mb-4">
        <AlertTitle>Autonomy agent not trained</AlertTitle>
        <AlertDescription>
          The Autonomy agent has not yet been trained. Train the model before assigning
          Autonomy strategies.
        </AlertDescription>
      </Alert>
    );
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[200px]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="flex gap-2 mb-4 justify-end flex-wrap">
          <Button variant="outline" onClick={() => navigate('/system-config')}>
            <Settings className="h-4 w-4 mr-2" />
            Supply Chain Config
          </Button>
          <Button variant="outline" onClick={() => navigate(scConfigBasePath)}>
            <FlaskConical className="h-4 w-4 mr-2" />
            Simulation Configuration
          </Button>
          <Button variant="outline" onClick={() => navigate('/users')}>
            <User className="h-4 w-4 mr-2" />
            Users
          </Button>
          <Button variant="outline" onClick={() => navigate('/admin/training')}>
            <Settings className="h-4 w-4 mr-2" />
            Training
          </Button>
        </div>

        <AutonomyAlert />
        <Alert variant="error">
          <AlertTitle>Unable to load scenarios</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
          <h1 className="text-xl font-bold">Scenarios</h1>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" size="sm" onClick={() => navigate('/system-config')}>
            <Settings className="h-4 w-4 mr-2" />
            Supply Chain Config
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigate(scConfigBasePath)}>
            <FlaskConical className="h-4 w-4 mr-2" />
            Simulation Configuration
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigate('/users')}>
            <User className="h-4 w-4 mr-2" />
            Users
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigate('/admin/training')}>
            Training
          </Button>
          <Button variant="ghost" size="sm" title="Export">
            <Download className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <hr className="mb-4 border-border" />

      {restrictLifecycleActions && (
        <Alert variant="info" className="mb-4">
          <AlertDescription>
            Start, restart, and review controls are available from the Supervision tab.
          </AlertDescription>
        </Alert>
      )}

      <AutonomyAlert />

      <div className="flex justify-end mb-4">
        <Button onClick={() => handleOpenEditor(null)}>
          <Plus className="h-4 w-4 mr-2" />
          New Scenario
        </Button>
      </div>

      <TableContainer>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Mode</TableHead>
              <TableHead>Current Period</TableHead>
              <TableHead>Max Periods</TableHead>
              <TableHead>Demand Pattern</TableHead>
              <TableHead>Created At</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {scenarios.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                  No scenarios found. Create a new scenario to get started.
                </TableCell>
              </TableRow>
            ) : (
              scenarios.map((scenario) => {
                const paramsSummary = scenario.demand_pattern?.type === 'classic'
                  ? normalizeClassicSummary(scenario.demand_pattern)
                  : '';
                const modeLabel = String(scenario.progression_mode || scenario?.config?.progression_mode || 'supervised');
                const statusLower = String(scenario.status || '').toLowerCase();

                const canEdit = true;
                const canStart = statusLower === 'created';

                return (
                  <TableRow key={scenario.id}>
                    <TableCell>
                      <span
                        className="truncate max-w-[320px] block"
                        title={scenario.description || scenario.name}
                      >
                        {scenario.name}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge variant={getStatusVariant(scenario.status)}>
                        {String(scenario.status || '').replace(/_/g, ' ').toUpperCase()}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={modeLabel.toLowerCase() === 'unsupervised' ? 'info' : 'secondary'}
                      >
                        {modeLabel.replace(/_/g, ' ').replace(/^./, (s) => s.toUpperCase())}
                      </Badge>
                    </TableCell>
                    <TableCell>{scenario.current_period}</TableCell>
                    <TableCell>{scenario.max_periods}</TableCell>
                    <TableCell>
                      <span
                        className="truncate max-w-[260px] block"
                        title={scenario.demand_pattern?.type || 'classic'}
                      >
                        {(scenario.demand_pattern?.type || 'classic')}{paramsSummary}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span
                        className="truncate max-w-[220px] block"
                        title={formatDate(scenario.created_at)}
                      >
                        {formatDate(scenario.created_at)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1 flex-wrap">
                        {!restrictLifecycleActions ? (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => navigate(`/scenarios/${scenario.id}`)}
                            >
                              <FlaskConical className="h-3 w-3 mr-1" />
                              Board
                            </Button>
                            {(statusLower === 'finished' || statusLower === 'completed') && (
                              <>
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  onClick={() => navigate(`/scenarios/${scenario.id}/report`)}
                                >
                                  Report
                                </Button>
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  onClick={() => navigate(`/scenarios/${scenario.id}/visualizations`)}
                                >
                                  3D View
                                </Button>
                              </>
                            )}
                            <Button
                              size="sm"
                              onClick={() => handleStartScenario(scenario.id)}
                              disabled={!canStart}
                            >
                              <Play className="h-3 w-3 mr-1" />
                              Start
                            </Button>
                          </>
                        ) : (
                          <Button
                            size="sm"
                            onClick={() => goToSupervision(scenario.id)}
                          >
                            <Eye className="h-3 w-3 mr-1" />
                            Supervise
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleOpenEditor(scenario)}
                          disabled={!canEdit}
                        >
                          <Pencil className="h-3 w-3 mr-1" />
                          Edit
                        </Button>
                        {!restrictLifecycleActions && (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleResetScenario(scenario.id)}
                              disabled={statusLower === 'created'}
                              title="Reset scenario back to period 0"
                            >
                              <RefreshCw className="h-3 w-3 mr-1" />
                              Reset
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleRestartScenario(scenario.id)}
                              title="Reset and immediately start the scenario"
                            >
                              <RotateCcw className="h-3 w-3 mr-1" />
                              Restart
                            </Button>
                          </>
                        )}
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => handleDeleteScenario(scenario.id)}
                        >
                          <Trash2 className="h-3 w-3 mr-1" />
                          Delete
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Collaboration Scenarios (Agentic Authorization Protocol) */}
      <div className="mt-8">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="h-5 w-5 text-blue-500" />
          <h2 className="text-lg font-bold">Collaboration Scenarios</h2>
          <Badge variant="info">{collabScenarios.length}</Badge>
        </div>
        <p className="text-sm text-muted-foreground mb-4">
          Cross-functional agent authorization decisions via the Agentic Authorization Protocol (AAP).
        </p>

        {collabLoading ? (
          <div className="flex justify-center py-8"><Spinner /></div>
        ) : collabScenarios.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              No collaboration scenarios found for this group.
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {collabScenarios.map((cs) => {
              const isExpanded = expandedCollab === cs.scenario_code;
              const authRequests = cs.authorization_requests || [];
              const timeline = cs.timeline || [];
              const scorecard = cs.balanced_scorecard || {};

              const priorityColors = {
                critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
                high: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
                medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
                low: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
              };
              const levelColors = {
                sop: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
                tactical: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
                execution: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-300',
              };

              return (
                <Card key={cs.scenario_code} className="overflow-hidden">
                  <div
                    className="flex items-center gap-3 p-4 cursor-pointer hover:bg-accent/50 transition-colors"
                    onClick={() => setExpandedCollab(isExpanded ? null : cs.scenario_code)}
                  >
                    {isExpanded ? (
                      <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs text-muted-foreground">{cs.scenario_code}</span>
                        <span className={cn('px-2 py-0.5 rounded-full text-xs font-medium', levelColors[cs.level] || '')}>
                          {cs.level?.toUpperCase()}
                        </span>
                        <span className={cn('px-2 py-0.5 rounded-full text-xs font-medium', priorityColors[cs.priority] || '')}>
                          {cs.priority?.toUpperCase()}
                        </span>
                        <Badge variant={cs.status === 'resolved' ? 'success' : 'secondary'}>
                          {cs.status?.toUpperCase()}
                        </Badge>
                      </div>
                      <h3 className="font-semibold mt-1 truncate">{cs.title}</h3>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-sm font-semibold text-green-600 dark:text-green-400">
                        +${cs.net_benefit?.toLocaleString()}
                      </div>
                      <div className="text-xs text-muted-foreground">net benefit</div>
                    </div>
                    <div className="text-right shrink-0 ml-2">
                      <div className="text-sm font-medium">{authRequests.length}</div>
                      <div className="text-xs text-muted-foreground">auth requests</div>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="border-t px-4 pb-4">
                      {/* Description */}
                      <p className="text-sm text-muted-foreground mt-3 mb-4">{cs.description}</p>

                      {/* Agent Flow */}
                      <div className="flex items-center gap-2 mb-4 flex-wrap">
                        <div className="flex items-center gap-1 bg-blue-50 dark:bg-blue-900/20 px-2 py-1 rounded text-xs">
                          <Bot className="h-3 w-3" />
                          {cs.originating_agent}
                        </div>
                        <ArrowRight className="h-3 w-3 text-muted-foreground" />
                        {(cs.target_agents || []).map((a, i) => (
                          <div key={i} className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded text-xs">
                            <Bot className="h-3 w-3" />
                            {a}
                          </div>
                        ))}
                      </div>

                      {/* Authorization Requests */}
                      <h4 className="font-semibold text-sm mb-2">Authorization Requests</h4>
                      <div className="space-y-2 mb-4">
                        {authRequests.map((ar, i) => (
                          <div key={i} className="border rounded-lg p-3 bg-card">
                            <div className="flex items-center justify-between mb-1">
                              <div className="flex items-center gap-2">
                                <span className="font-mono text-xs">{ar.id}</span>
                                <ArrowRight className="h-3 w-3 text-muted-foreground" />
                                <span className="text-sm font-medium">{ar.target_agent}</span>
                              </div>
                              <Badge variant={ar.decision === 'AUTHORIZE' ? 'success' : 'destructive'}>
                                <CheckCircle className="h-3 w-3 mr-1" />
                                {ar.decision}
                              </Badge>
                            </div>
                            <p className="text-xs text-muted-foreground mb-2">{ar.proposed_action?.type?.replace(/_/g, ' ')}</p>
                            <p className="text-sm">{ar.justification}</p>
                            {ar.decision_reason && (
                              <p className="text-xs text-green-600 dark:text-green-400 mt-1">
                                {ar.decision_reason}
                              </p>
                            )}

                            {/* Scorecard Impact */}
                            {ar.scorecard_impact && (
                              <div className="grid grid-cols-4 gap-2 mt-2">
                                {Object.entries(ar.scorecard_impact).map(([quad, metrics]) => (
                                  <div key={quad} className="bg-accent/30 rounded p-2">
                                    <div className="text-xs font-medium capitalize mb-1">{quad}</div>
                                    {Object.entries(metrics || {}).map(([k, v]) => (
                                      <div key={k} className="text-xs flex justify-between">
                                        <span className="text-muted-foreground truncate mr-1">{k.replace(/_/g, ' ')}</span>
                                        <span className={cn(
                                          'font-mono shrink-0',
                                          v?.status === 'GREEN' ? 'text-green-600' :
                                          v?.status === 'YELLOW' ? 'text-yellow-600' :
                                          v?.status === 'RED' ? 'text-red-600' : ''
                                        )}>
                                          {v?.status || ''}
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>

                      {/* Timeline */}
                      {timeline.length > 0 && (
                        <>
                          <h4 className="font-semibold text-sm mb-2">Timeline</h4>
                          <div className="relative pl-4 border-l-2 border-blue-200 dark:border-blue-800 space-y-2 mb-4">
                            {timeline.map((evt, i) => (
                              <div key={i} className="relative">
                                <div className="absolute -left-[21px] w-2.5 h-2.5 rounded-full bg-blue-500 mt-1.5" />
                                <div className="flex items-baseline gap-2">
                                  <span className="text-xs font-mono text-muted-foreground shrink-0">
                                    {evt.timestamp?.split('T')[1]?.slice(0, 8) || evt.timestamp}
                                  </span>
                                  <span className="text-sm">{evt.description || evt.event}</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </>
                      )}

                      {/* Aggregate Balanced Scorecard */}
                      {Object.keys(scorecard).length > 0 && (
                        <>
                          <h4 className="font-semibold text-sm mb-2">Balanced Scorecard (Aggregate)</h4>
                          <div className="grid grid-cols-4 gap-3">
                            {Object.entries(scorecard).map(([quad, metrics]) => (
                              <Card key={quad} className="p-3">
                                <div className="text-xs font-semibold capitalize mb-2">{quad}</div>
                                {Object.entries(metrics || {}).map(([k, v]) => (
                                  <div key={k} className="flex justify-between text-xs mb-1">
                                    <span className="text-muted-foreground">{k.replace(/_/g, ' ')}</span>
                                    <span className={cn(
                                      'font-medium',
                                      v?.status === 'GREEN' ? 'text-green-600' :
                                      v?.status === 'YELLOW' ? 'text-yellow-600' :
                                      v?.status === 'RED' ? 'text-red-600' : ''
                                    )}>
                                      {typeof v === 'object' ? v?.status || JSON.stringify(v) : String(v)}
                                    </span>
                                  </div>
                                ))}
                              </Card>
                            ))}
                          </div>
                        </>
                      )}

                      {/* Resolution */}
                      {cs.resolution && (
                        <div className="mt-3 p-3 bg-green-50 dark:bg-green-900/10 rounded-lg border border-green-200 dark:border-green-800">
                          <div className="flex items-center gap-1 text-sm font-semibold text-green-700 dark:text-green-400 mb-1">
                            <CheckCircle className="h-4 w-4" />
                            Resolution: {cs.resolution.outcome}
                          </div>
                          <p className="text-sm">{cs.resolution.summary}</p>
                          {cs.resolution.total_cost != null && (
                            <div className="flex gap-4 mt-2 text-xs">
                              <span>Total Cost: <strong>${cs.resolution.total_cost?.toLocaleString()}</strong></span>
                              <span>Revenue Protected: <strong>${cs.resolution.revenue_protected?.toLocaleString()}</strong></span>
                              <span className="text-green-600 dark:text-green-400 font-semibold">
                                Net Benefit: +${cs.resolution.net_benefit?.toLocaleString()}
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default ScenariosList;
