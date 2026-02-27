import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  Modal,
  Progress,
  Spinner,
  Switch,
  Label,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '../../components/common';
import {
  Play,
  Square,
  SkipForward,
  Eye,
  CheckCircle,
  RotateCcw,
} from 'lucide-react';
import { useSnackbar } from 'notistack';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import simulationApi from '../../services/api';
import { emitStartupNotices } from '../../utils/startupNotices';

const formatDate = (value) => {
  if (!value) return '—';
  try {
    return format(new Date(value), 'MMM d, yyyy HH:mm');
  } catch (error) {
    return String(value);
  }
};

const statusLabel = (status = '') => (status || 'unknown').replace(/_/g, ' ');

const statusColor = (status = '') => {
  const normalized = String(status).toLowerCase();
  if (normalized === 'created') return 'secondary';
  if (normalized === 'in_progress') return 'info';
  if (normalized === 'completed') return 'success';
  if (normalized === 'paused') return 'warning';
  if (normalized === 'failed' || normalized === 'error') return 'destructive';
  return 'secondary';
};

const TenantScenarioSupervisionPanel = ({
  games = [],
  loading = false,
  error = null,
  onRefresh,
  tenantId = null,
  currentUserId = null,
  selectedSupplyChainId = 'all',
}) => {
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();
  const [actionState, setActionState] = useState({});
  const [autoProgress, setAutoProgress] = useState(null);
  const [autoDialogOpen, setAutoDialogOpen] = useState(false);
  const [resetPopoverOpen, setResetPopoverOpen] = useState(false);
  const [pendingResetGame, setPendingResetGame] = useState(null);
  const [debugLoggingEnabled, setDebugLoggingEnabled] = useState(false);
  const autoStopRef = useRef(new Set());

  const supervisedGames = useMemo(() => {
    if (!Array.isArray(games)) {
      return [];
    }

    const normalizedSupplyChainId = String(selectedSupplyChainId ?? 'all');
    const normalizedTenantId = tenantId != null ? Number(tenantId) : null;
    const normalizedUserId = currentUserId != null ? Number(currentUserId) : null;

    return games.filter((game) => {
      if (!game) return false;

      if (normalizedTenantId != null) {
        const targetTenant = game.tenant_id ?? game?.config?.tenant_id ?? null;
        if (targetTenant != null) {
          if (Number(targetTenant) !== normalizedTenantId) {
            return false;
          }
        } else if (game.created_by != null) {
          if (normalizedUserId == null || Number(game.created_by) !== normalizedUserId) {
            return false;
          }
        } else {
          return false;
        }
      }

      if (normalizedSupplyChainId !== 'all') {
        const gameSupplyChainId =
          game.supply_chain_config_id ?? game?.config?.supply_chain_config_id ?? null;
        if (gameSupplyChainId == null) {
          return false;
        }
        if (String(gameSupplyChainId) !== normalizedSupplyChainId) {
          return false;
        }
      }

      return true;
    });
  }, [games, tenantId, currentUserId, selectedSupplyChainId]);

  const setGameActionState = (gameId, state) => {
    setActionState((prev) => ({ ...prev, [gameId]: state }));
  };

  const runAction = useCallback(
    async (gameId, action, apiCall, successMessage) => {
      setGameActionState(gameId, action);
      try {
        const result = await apiCall(gameId);
        enqueueSnackbar(successMessage, { variant: 'success' });
        if (onRefresh) {
          await onRefresh();
        }
        return result;
      } catch (err) {
        const detail = err?.response?.data?.detail || err?.message || 'Action failed';
        enqueueSnackbar(detail, { variant: 'error' });
        return undefined;
      } finally {
        setGameActionState(gameId, null);
      }
    },
    [enqueueSnackbar, onRefresh],
  );

  const handleStart = async (game) => {
    if (!game) return;
    const result = await runAction(
      game.id,
      'start',
      (id) => simulationApi.startGame(id, { debugLogging: debugLoggingEnabled }),
      'Game started',
    );
    if (!result) {
      return;
    }

    emitStartupNotices(result, (message) => enqueueSnackbar(message, { variant: 'warning' }));

    const mode = String(
      result?.progression_mode ||
        game.progression_mode ||
        game?.config?.progression_mode ||
        'supervised',
    ).toLowerCase();

    if (mode === 'unsupervised') {
      setAutoProgress({
        gameId: game.id,
        name: game.name,
        currentRound: result?.current_round ?? game.current_round ?? 0,
        maxRounds: result?.max_rounds ?? game.max_rounds ?? 0,
        status: result?.status ?? game.status,
        lastUpdated: new Date().toISOString(),
        done: false,
        error: null,
        history: Array.isArray(result?.config?.history) ? result.config.history : [],
      });
      setAutoDialogOpen(true);
    }
  };

  const handleStop = (gameId) => runAction(gameId, 'stop', simulationApi.stopGame, 'Game stopped');
  const handleNextRound = (gameId) =>
    runAction(gameId, 'next_round', simulationApi.nextRound, 'Advanced to next round');

  const handleResetClick = (game) => {
    if (!game) return;
    setPendingResetGame(game);
    setResetPopoverOpen(true);
  };

  const handleResetConfirm = async () => {
    if (!pendingResetGame) return;
    const game = pendingResetGame;
    setResetPopoverOpen(false);
    setPendingResetGame(null);

    const result = await runAction(
      game.id,
      'reset',
      simulationApi.resetGame,
      'Game reset to initial state',
    );

    if (result !== undefined) {
      setAutoProgress((prev) => {
        if (prev?.gameId === game.id) {
          setAutoDialogOpen(false);
          return null;
        }
        return prev;
      });
    }
  };

  const handleResetCancel = () => {
    setResetPopoverOpen(false);
    setPendingResetGame(null);
  };

  const monitoringGameId = autoProgress?.gameId;
  const monitoringDone = autoProgress?.done;

  useEffect(() => {
    if (!monitoringGameId || monitoringDone) {
      return undefined;
    }

    let cancelled = false;

    const poll = async () => {
      try {
        const state = await simulationApi.getGameState(monitoringGameId);
        const gameData = state?.game || {};
        if (cancelled) return;

        const statusRaw = String(gameData?.status || '').toLowerCase();
        const currentRound = state?.round ?? gameData?.current_round ?? 0;
        const maxRoundsFromData = gameData?.max_rounds ?? 0;
        const history = Array.isArray(state?.history) ? state.history : [];

        let finished = false;
        setAutoProgress((prev) => {
          if (!prev || prev.gameId !== monitoringGameId) {
            return prev;
          }

          const nextMaxRounds = maxRoundsFromData || prev.maxRounds || 0;
          const done =
            statusRaw === 'completed' ||
            statusRaw === 'finished' ||
            (nextMaxRounds > 0 && currentRound >= nextMaxRounds);
          if (done && !prev.done) {
            finished = true;
          }

          return {
            ...prev,
            currentRound,
            maxRounds: nextMaxRounds,
            status: gameData?.status ?? prev.status,
            lastUpdated: new Date().toISOString(),
            error: null,
            done,
            history,
          };
        });

        if (finished && onRefresh) {
          await onRefresh();
        }
      } catch (err) {
        if (cancelled) return;
        const detail = err?.response?.data?.detail || err?.message || 'Unable to update progress right now';
        setAutoProgress((prev) => {
          if (!prev || prev.gameId !== monitoringGameId) {
            return prev;
          }
          return {
            ...prev,
            error: detail,
            lastUpdated: new Date().toISOString(),
          };
        });
      }
    };

    const interval = setInterval(poll, 1500);
    poll();

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [monitoringGameId, monitoringDone, onRefresh]);

  useEffect(() => {
    if (!autoProgress?.done) {
      return undefined;
    }

    const timeout = setTimeout(() => {
      setAutoDialogOpen(false);
      setAutoProgress(null);
    }, 1200);

    return () => clearTimeout(timeout);
  }, [autoProgress?.done]);

  useEffect(() => {
    const monitoringGameId = autoProgress?.gameId;
    if (!monitoringGameId || !autoProgress?.done) {
      return;
    }

    if (autoStopRef.current.has(monitoringGameId)) {
      return;
    }

    autoStopRef.current.add(monitoringGameId);
    runAction(
      monitoringGameId,
      'stop',
      simulationApi.stopGame,
      'Game stopped automatically',
    ).catch(() => {
      autoStopRef.current.delete(monitoringGameId);
    });
  }, [autoProgress?.done, autoProgress?.gameId, runAction]);

  useEffect(() => {
    if (!Array.isArray(games)) {
      return;
    }

    games.forEach((game) => {
      if (!game || !game.id) {
        return;
      }
      const status = String(game.status || '').toLowerCase();
      if (status !== 'in_progress') {
        autoStopRef.current.delete(game.id);
        return;
      }

      const maxRounds = Number(game.max_rounds ?? 0);
      const currentRound = Number(game.current_round ?? 0);
      if (maxRounds > 0 && currentRound >= maxRounds && !autoStopRef.current.has(game.id)) {
        autoStopRef.current.add(game.id);
        runAction(game.id, 'stop', simulationApi.stopGame, 'Game stopped automatically').catch(() => {
          autoStopRef.current.delete(game.id);
        });
      }
    });
  }, [games, runAction]);

  useEffect(() => {
    if (!autoProgress) {
      setAutoDialogOpen(false);
    }
  }, [autoProgress]);

  const checkModelRequirements = (game) => {
    const scenarioUsers = game.scenarioUsers || [];
    const gnnStrategies = ['ml_forecast', 'gnn', 'autonomy', 'dtce'];
    const trmStrategies = ['trm', 'tiny_recursive'];
    const llmStrategies = ['llm', 'llm_balanced', 'llm_conservative', 'llm_aggressive',
                          'llm_adaptive', 'llm_supervised', 'llm_global'];

    const agentsRequiringTraining = scenarioUsers
      .filter(scenarioUser => scenarioUser.is_ai)
      .filter(scenarioUser => {
        const strategy = String(scenarioUser.ai_strategy || '').toLowerCase();
        const requiresGNN = gnnStrategies.some(s => strategy.includes(s));
        const requiresTRM = trmStrategies.some(s => strategy.includes(s));
        const isLLM = llmStrategies.some(s => strategy.includes(s));
        return (requiresGNN || requiresTRM) && !isLLM;
      });

    if (agentsRequiringTraining.length === 0) {
      return {
        requiresModel: false,
        modelTrained: true,
        modelType: null,
        untrainedAgents: []
      };
    }

    const needsGNN = agentsRequiringTraining.some(scenarioUser => {
      const strategy = String(scenarioUser.ai_strategy || '').toLowerCase();
      return gnnStrategies.some(s => strategy.includes(s));
    });

    const needsTRM = agentsRequiringTraining.some(scenarioUser => {
      const strategy = String(scenarioUser.ai_strategy || '').toLowerCase();
      return trmStrategies.some(s => strategy.includes(s));
    });

    const supplyChainConfig = game.supply_chain_config || {};
    const trainedAt = supplyChainConfig.trained_at;
    const modelTrained = Boolean(trainedAt);

    const modelTypes = [];
    if (needsGNN) modelTypes.push('GNN');
    if (needsTRM) modelTypes.push('TRM');

    return {
      requiresModel: true,
      modelTrained,
      modelType: modelTypes.join(' & '),
      untrainedAgents: modelTrained ? [] : agentsRequiringTraining.map(p => ({
        role: p.role,
        strategy: p.ai_strategy
      }))
    };
  };

  const renderActions = (game) => {
    const status = String(game.status || '').toLowerCase();
    const mode = String(game.progression_mode || game?.config?.progression_mode || 'supervised').toLowerCase();
    const busy = Boolean(actionState[game.id]);
    const viewTarget = status === 'completed' ? `/scenarios/${game.id}/report` : `/scenarios/${game.id}`;

    const isCompleted = status === 'completed' || status === 'finished';
    const { requiresModel, modelTrained, modelType, untrainedAgents } = checkModelRequirements(game);

    if (isCompleted) {
      return (
        <div className="flex flex-wrap gap-2 justify-end items-center">
          <Button
            size="sm"
            variant="outline"
            onClick={() => navigate(viewTarget)}
            leftIcon={<Eye className="h-4 w-4" />}
          >
            View
          </Button>
          <Popover open={resetPopoverOpen && pendingResetGame?.id === game.id} onOpenChange={(open) => {
            if (!open) handleResetCancel();
          }}>
            <PopoverTrigger asChild>
              <Button
                size="sm"
                variant="outline"
                className="text-amber-600 border-amber-600"
                onClick={() => handleResetClick(game)}
                disabled={busy}
                leftIcon={<RotateCcw className="h-4 w-4" />}
              >
                {busy && actionState[game.id] === 'reset' ? 'Resetting…' : 'Reset'}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-80">
              <div className="space-y-4">
                <h4 className="font-bold">Confirm reset</h4>
                <p className="text-sm text-muted-foreground">
                  {pendingResetGame?.name
                    ? `Reset "${pendingResetGame.name}"? This will clear all recorded rounds and return the game to its initial setup.`
                    : 'Reset this game? This will clear all recorded rounds.'}
                </p>
                <div className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={handleResetCancel}>Cancel</Button>
                  <Button
                    size="sm"
                    className="bg-amber-600 hover:bg-amber-700"
                    onClick={handleResetConfirm}
                    leftIcon={<RotateCcw className="h-4 w-4" />}
                  >
                    Reset
                  </Button>
                </div>
              </div>
            </PopoverContent>
          </Popover>
        </div>
      );
    }

    if (status === 'created' || status === 'paused') {
      const canStart = !busy && (!requiresModel || modelTrained);

      let disabledReason = '';
      if (requiresModel && !modelTrained) {
        const agentList = untrainedAgents
          .map(a => `${a.role} (${a.strategy})`)
          .join(', ');
        disabledReason = `${modelType} model must be trained first. Agents requiring training: ${agentList}. Go to Supply Chains tab and train the model.`;
      }

      return (
        <div className="flex flex-wrap gap-2 justify-end items-center">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button
                    size="sm"
                    className="bg-green-600 hover:bg-green-700"
                    onClick={() => handleStart(game)}
                    disabled={!canStart}
                    leftIcon={<Play className="h-4 w-4" />}
                  >
                    {busy ? 'Starting…' : 'Start'}
                  </Button>
                </span>
              </TooltipTrigger>
              {disabledReason && <TooltipContent className="max-w-xs">{disabledReason}</TooltipContent>}
            </Tooltip>
          </TooltipProvider>
        </div>
      );
    }

    if (status === 'in_progress') {
      const maxRounds = Number(game.max_rounds ?? 0);
      const currentRound = Number(game.current_round ?? 0);
      const reachedEnd = maxRounds > 0 && currentRound >= maxRounds;
      const monitoringThisGame = autoProgress?.gameId === game.id;
      const hideStopButton =
        reachedEnd || (mode === 'unsupervised' && monitoringThisGame && autoProgress?.done);

      return (
        <div className="flex flex-wrap gap-2 justify-end items-center">
          {mode === 'unsupervised' ? (
            <Badge
              variant="info"
              className="cursor-pointer"
              onClick={() => {
                if (monitoringThisGame) {
                  setAutoDialogOpen(true);
                }
              }}
            >
              Auto
            </Badge>
          ) : (
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleNextRound(game.id)}
              disabled={busy}
              leftIcon={<SkipForward className="h-4 w-4" />}
            >
              {busy && actionState[game.id] === 'next_round' ? 'Advancing…' : 'Next Round'}
            </Button>
          )}
          {!hideStopButton && (
            <Button
              size="sm"
              variant="outline"
              className="text-destructive border-destructive"
              onClick={() => handleStop(game.id)}
              disabled={busy}
              leftIcon={<Square className="h-4 w-4" />}
            >
              {busy && actionState[game.id] === 'stop' ? 'Stopping…' : 'Stop'}
            </Button>
          )}
        </div>
      );
    }

    return null;
  };

  const formatQuantity = (value) => {
    const numeric = Number(value ?? 0);
    if (!Number.isFinite(numeric)) {
      return '0';
    }
    return numeric.toLocaleString();
  };

  return (
    <>
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
            <div>
              <h2 className="text-lg font-bold">Scenario Supervision</h2>
              <p className="text-sm text-muted-foreground">
                Monitor live sessions and orchestrate progress across your organization's scenarios.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row gap-3 items-center">
              <div className="flex items-center gap-2">
                <Switch
                  checked={debugLoggingEnabled}
                  onCheckedChange={setDebugLoggingEnabled}
                  id="debug-logging"
                />
                <Label htmlFor="debug-logging" className="text-sm">Enable debug logging</Label>
              </div>
              {onRefresh && (
                <Button variant="outline" onClick={onRefresh} disabled={loading}>
                  Refresh
                </Button>
              )}
            </div>
          </div>

          {error && (
            <Alert variant="destructive" className="mb-4">
              {error}
            </Alert>
          )}

          {loading ? (
            <div className="flex justify-center items-center min-h-[240px]">
              <Spinner size="lg" />
            </div>
          ) : supervisedGames.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground mb-2">
                There are no games to supervise right now.
              </p>
              <p className="text-sm text-muted-foreground">
                Create a new mixed game or wait for a session to begin.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table className="table-fixed w-full min-w-[700px]">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[30%]">Name</TableHead>
                    <TableHead className="w-[12%]">Status</TableHead>
                    <TableHead className="w-[15%]">Round</TableHead>
                    <TableHead className="w-[18%]">Last Updated</TableHead>
                    <TableHead className="text-right w-[25%]">Controls</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {supervisedGames.map((game) => (
                    <TableRow key={game.id}>
                      <TableCell className="max-w-0">
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <div className="cursor-default">
                                <p className="font-semibold truncate">{game.name}</p>
                                <p className="text-sm text-muted-foreground line-clamp-2">
                                  {game.description || 'No description provided'}
                                </p>
                              </div>
                            </TooltipTrigger>
                            <TooltipContent side="bottom" align="start" className="max-w-sm">
                              <p className="font-semibold">{game.name}</p>
                              <p className="text-sm">{game.description || 'No description provided'}</p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusColor(game.status)}>
                          {statusLabel(game.status)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <p className="text-sm">
                            {game.current_round ?? 0} / {game.max_rounds ?? '—'}
                          </p>
                          <Progress
                            value={(() => {
                              const current = Number(game.current_round ?? 0);
                              const total = Number(game.max_rounds ?? 0);
                              if (!total || Number.isNaN(total) || total <= 0) {
                                return 0;
                              }
                              const pct = (current / total) * 100;
                              return Math.max(0, Math.min(100, pct));
                            })()}
                            className="h-1.5"
                          />
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm">{formatDate(game.updated_at)}</span>
                      </TableCell>
                      <TableCell className="text-right">{renderActions(game)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Modal
        isOpen={Boolean(autoProgress) && autoDialogOpen}
        onClose={() => setAutoDialogOpen(false)}
        title="Running unsupervised game"
        size="sm"
      >
        {autoProgress && (
          <div className="flex flex-col items-center gap-4 py-4">
            {autoProgress.done ? (
              <CheckCircle className="h-12 w-12 text-green-600" />
            ) : (
              <Spinner size="lg" />
            )}
            <div className="text-center">
              <p className="font-semibold">{autoProgress.name}</p>
              <p className="text-sm text-muted-foreground">
                Round {autoProgress.currentRound ?? 0} / {autoProgress.maxRounds || '—'}
              </p>
              <p className="text-xs text-muted-foreground">
                Status: {statusLabel(autoProgress.status)}
              </p>
            </div>
            {autoProgress.maxRounds > 0 && (
              <div className="w-full">
                <Progress
                  value={(() => {
                    const total = Number(autoProgress.maxRounds);
                    const current = Number(autoProgress.currentRound ?? 0);
                    if (!total || Number.isNaN(total) || total <= 0) {
                      return 0;
                    }
                    const pct = (current / total) * 100;
                    return Math.max(0, Math.min(100, pct));
                  })()}
                  className="h-1.5"
                />
                <p className="text-xs text-muted-foreground mt-1 text-center">
                  {(() => {
                    const total = Number(autoProgress.maxRounds);
                    const current = Number(autoProgress.currentRound ?? 0);
                    if (!total || Number.isNaN(total) || total <= 0) {
                      return 'Progress unavailable';
                    }
                    const pct = Math.max(0, Math.min(100, Math.round((current / total) * 100)));
                    return `${pct}% complete`;
                  })()}
                </p>
              </div>
            )}
            {autoProgress.error && (
              <p className="text-sm text-destructive text-center">{autoProgress.error}</p>
            )}
            {!autoProgress.done && (
              <p className="text-sm text-muted-foreground text-center">
                We&apos;re advancing each round automatically. You can close this dialog at any time.
              </p>
            )}
            {autoProgress.done && (
              <p className="text-sm text-green-600 text-center">
                All rounds complete. Preparing summary…
              </p>
            )}
            {(() => {
              const history = Array.isArray(autoProgress.history) ? autoProgress.history : [];
              if (!history.length) {
                return (
                  <p className="text-xs text-muted-foreground text-center">
                    Waiting for first round results…
                  </p>
                );
              }
              const latest = history[history.length - 1];
              const currentNodeKey = latest?.current_node || latest?.node_sequence?.[0] || null;
              const nodeStates =
                latest?.node_states && typeof latest.node_states === 'object' ? latest.node_states : {};
              const nodeState = currentNodeKey ? nodeStates[currentNodeKey] : null;
              const summaries =
                latest?.node_type_summaries &&
                typeof latest.node_type_summaries === 'object'
                  ? latest.node_type_summaries
                  : {};
              const demandOrder = [
                "market_demand",
                "retailer",
                "wholesaler",
                "distributor",
                "manufacturer",
                "supplier",
                "market_supply",
              ];
              const entries = Object.entries(summaries).sort((a, b) => {
                const ia = demandOrder.indexOf(String(a[0]).toLowerCase());
                const ib = demandOrder.indexOf(String(b[0]).toLowerCase());
                if (ia === -1 && ib === -1) return String(a[0]).localeCompare(String(b[0]));
                if (ia === -1) return 1;
                if (ib === -1) return -1;
                return ia - ib;
              });
              const nodeOrders =
                latest?.node_orders && typeof latest.node_orders === 'object'
                  ? latest.node_orders
                  : {};

              return (
                <div className="w-full">
                  {currentNodeKey && (
                    <>
                      <hr className="my-3" />
                      <h4 className="font-semibold text-sm mb-2">Evaluating node</h4>
                      <Card variant="outline" className="p-3">
                        <p className="font-semibold text-sm mb-1">
                          {currentNodeKey.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())}
                        </p>
                        {(() => {
                          if (!nodeState) return null;
                          const rawName = nodeState.scenario_user_name || nodeState.display_name;
                          const role = nodeState.scenario_user_role
                            ? nodeState.scenario_user_role.toLowerCase().replace(/_/g, ' ')
                            : null;
                          const isAi = Boolean(nodeState.is_ai);
                          const strategy = nodeState.scenario_user_strategy
                            ? nodeState.scenario_user_strategy.replace(/_/g, ' ')
                            : null;
                          const parts = [];
                          if (rawName) {
                            parts.push(rawName);
                          }
                          if (role) {
                            parts.push(role.replace(/\b\w/g, (char) => char.toUpperCase()));
                          }
                          if (isAi && strategy) {
                            parts.push(`${strategy} AI`);
                          } else if (isAi) {
                            parts.push('AI');
                          }
                          if (!isAi) {
                            parts.push('Human');
                          }
                          if (!parts.length) {
                            return null;
                          }
                          return (
                            <p className="text-xs text-muted-foreground mb-2">
                              Acting scenarioUser: {parts.join(' • ')}
                            </p>
                          );
                        })()}
                        {nodeState ? (
                          <div className="space-y-1 text-xs">
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Inventory</span>
                              <span className="font-semibold">{formatQuantity(nodeState.inventory)}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Backlog</span>
                              <span className="font-semibold">{formatQuantity(nodeState.backlog)}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Order queue</span>
                              <span className="font-semibold">
                                {Array.isArray(nodeState.info_queue)
                                  ? nodeState.info_queue.map((qty) => formatQuantity(qty)).join(', ')
                                  : '—'}
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Shipment queue</span>
                              <span className="font-semibold">
                                {Array.isArray(nodeState.ship_queue)
                                  ? nodeState.ship_queue.map((qty) => formatQuantity(qty)).join(', ')
                                  : '—'}
                              </span>
                            </div>
                          </div>
                        ) : (
                          <p className="text-xs text-muted-foreground">
                            Node state not available yet.
                          </p>
                        )}
                      </Card>
                    </>
                  )}
                  {entries.length > 0 && (
                    <>
                      <hr className="my-3" />
                      <h4 className="font-semibold text-sm mb-2">
                        Latest orders (Round {latest?.round ?? autoProgress.currentRound ?? '—'})
                      </h4>
                      <div className="space-y-2">
                        {entries.map(([typeKey, details]) => {
                          const quantity = details?.orders ?? details?.quantity ?? details?.value ?? 0;
                          const typeLabel = String(typeKey || '')
                            .replace(/_/g, ' ')
                            .replace(/\b\w/g, (char) => char.toUpperCase());
                          const commentsForType = Object.entries(nodeOrders)
                            .filter(([_, orderDetails]) => {
                              const orderType = String(orderDetails?.type ?? '').toLowerCase();
                              return orderType === String(typeKey).toLowerCase() && orderDetails?.comment;
                            })
                            .map(([_, orderDetails]) => orderDetails.comment)
                            .filter(Boolean);
                          return (
                            <div
                              key={typeKey}
                              className="flex justify-between items-start gap-2"
                            >
                              <span className="text-sm font-semibold capitalize">{typeLabel}</span>
                              <div className="text-right">
                                <p className="text-sm">{`${formatQuantity(quantity)} units`}</p>
                                {commentsForType.length > 0 && (
                                  <p className="text-xs text-muted-foreground">
                                    {commentsForType[0]}
                                    {commentsForType.length > 1
                                      ? ` (+${commentsForType.length - 1} more)`
                                      : ''}
                                  </p>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </>
                  )}
                </div>
              );
            })()}
          </div>
        )}
      </Modal>
    </>
  );
};

export default TenantScenarioSupervisionPanel;
