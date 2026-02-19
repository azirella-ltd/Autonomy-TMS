import React, { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { isGroupAdmin as isGroupAdminUser } from '../utils/authUtils';
import simulationApi from '../services/api';
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
  Gamepad2,
  User,
  RotateCcw,
  RefreshCw,
  Eye,
} from 'lucide-react';
import { cn } from '../lib/utils/cn';

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

// Terminology (Feb 2026): Game -> Scenario, Player -> User (in UI)
const ScenariosList = () => {
  const [scenarios, setScenarios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' });
  const [modelStatus, setModelStatus] = useState({ is_trained: false });
  const [loadingModelStatus, setLoadingModelStatus] = useState(true);
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const isGroupAdmin = isGroupAdminUser(user);
  const restrictLifecycleActions = isGroupAdmin;
  const scConfigBasePath = isGroupAdmin ? '/admin/group/supply-chain-configs' : '/supply-chain-config';
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
      const list = await simulationApi.getGames();  // API uses scenarios endpoint
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
      const response = await simulationApi.startGame(scenarioId);  // API uses scenarios endpoint
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
      await simulationApi.resetGame(scenarioId);  // API uses scenarios endpoint
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
      await simulationApi.resetGame(scenarioId);
      const response = await simulationApi.startGame(scenarioId);
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
      await simulationApi.deleteGame(scenarioId);  // API uses scenarios endpoint
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
            <Gamepad2 className="h-4 w-4 mr-2" />
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
            <Gamepad2 className="h-4 w-4 mr-2" />
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
              <TableHead>Current Round</TableHead>
              <TableHead>Max Rounds</TableHead>
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
                    <TableCell>{scenario.current_round}</TableCell>
                    <TableCell>{scenario.max_rounds}</TableCell>
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
                              <Gamepad2 className="h-3 w-3 mr-1" />
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
                              title="Reset scenario back to round 0"
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
    </div>
  );
};

export default ScenariosList;
