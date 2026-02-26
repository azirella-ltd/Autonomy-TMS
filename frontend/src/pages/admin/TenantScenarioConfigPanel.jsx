import { useMemo } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  Spinner,
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
} from '../../components/common';
import { RotateCcw, Pencil, Trash2, Eye } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import { useSnackbar } from 'notistack';
import simulationApi from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { emitStartupNotices } from '../../utils/startupNotices';

const SUPERVISION_BASE_PATH = '/admin?section=supervision';

const buildSupervisionPath = (gameId) => {
  if (!gameId) {
    return SUPERVISION_BASE_PATH;
  }
  return `${SUPERVISION_BASE_PATH}&focusGameId=${gameId}`;
};

const formatDate = (value) => {
  if (!value) return '—';
  try {
    return format(new Date(value), 'MMM d, yyyy HH:mm');
  } catch (error) {
    return String(value);
  }
};

const statusColor = (status = '') => {
  const normalized = String(status).toLowerCase();
  if (normalized === 'created') return 'secondary';
  if (normalized === 'in_progress') return 'info';
  if (normalized === 'completed') return 'success';
  if (normalized === 'paused') return 'warning';
  return 'secondary';
};

const TenantScenarioConfigPanel = ({
  games = [],
  loading = false,
  error = null,
  onRefresh,
  groupId = null,
  currentUserId = null,
  selectedSupplyChainId = 'all',
  onSelectSupplyChain,
  supplyChainOptions = [],
  supplyChainMap = {},
}) => {
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();
  const { isTenantAdmin } = useAuth();
  const restrictLifecycleActions = Boolean(isTenantAdmin);

  const filteredGames = useMemo(() => {
    if (!Array.isArray(games) || games.length === 0) {
      return [];
    }

    const normalizedSupplyChainId = String(selectedSupplyChainId ?? 'all');

    return games.filter((game) => {
      if (!game) return false;
      const targetGroup = game.tenant_id ?? game?.config?.tenant_id ?? null;
      if (groupId != null) {
        if (targetGroup != null) {
          if (Number(targetGroup) !== Number(groupId)) {
            return false;
          }
        } else if (game.created_by != null && Number(game.created_by) !== Number(currentUserId)) {
          return false;
        }
      }
      if (normalizedSupplyChainId !== 'all') {
        const gameConfigId = game.supply_chain_config_id ?? game?.config?.supply_chain_config_id ?? null;
        if (gameConfigId == null) {
          return false;
        }
        if (String(gameConfigId) !== normalizedSupplyChainId) {
          return false;
        }
      }
      return true;
    });
  }, [games, groupId, currentUserId, selectedSupplyChainId]);

  const handleCreateGame = () => {
    navigate('/scenarios/new');
  };

  const handleViewGame = (gameId, status) => {
    if (restrictLifecycleActions) {
      navigate(buildSupervisionPath(gameId));
      return;
    }

    if (String(status || '').toLowerCase() === 'completed') {
      navigate(`/scenarios/${gameId}/report`);
    } else {
      navigate(`/scenarios/${gameId}`);
    }
  };

  const runAction = async (gameId, action, apiCall, successMessage) => {
    try {
      await apiCall(gameId);
      enqueueSnackbar(successMessage, { variant: 'success' });
      if (onRefresh) {
        await onRefresh();
      }
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Action failed';
      enqueueSnackbar(detail, { variant: 'error' });
    }
  };

  const handleRestart = async (gameId) => {
    try {
      await simulationApi.resetGame(gameId);
      const startResponse = await simulationApi.startGame(gameId);
      enqueueSnackbar('Game restarted', { variant: 'success' });
      emitStartupNotices(startResponse, (message) =>
        enqueueSnackbar(message, { variant: 'warning' }),
      );
      if (onRefresh) {
        await onRefresh();
      }
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Unable to restart game';
      enqueueSnackbar(detail, { variant: 'error' });
    }
  };

  const handleDelete = async (gameId, name) => {
    if (!window.confirm(`Delete game "${name}"? This cannot be undone.`)) return;
    await runAction(gameId, 'delete', simulationApi.deleteGame, 'Game deleted');
  };

  const handleEdit = (game) => {
    onRefresh?.();
    navigate(`/scenarios/${game.id}/edit`);
  };

  const supplyChainDisplay = (game) => {
    const rawId = game?.supply_chain_config_id ?? game?.config?.supply_chain_config_id;
    if (rawId != null) {
      const key = String(rawId);
      const entry = supplyChainMap[key];
      if (entry?.name) {
        return entry.name;
      }
    }
    if (game?.supply_chain_name) {
      return game.supply_chain_name;
    }
    if (game?.config?.supply_chain_name) {
      return game.config.supply_chain_name;
    }
    if (rawId != null) {
      return `Config ${rawId}`;
    }
    return '—';
  };

  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
          <div>
            <h2 className="text-lg font-bold">Scenario Configuration</h2>
            <p className="text-sm text-muted-foreground">
              Review recent mixed scenario setups and create new sessions for your organization.
            </p>
          </div>
          <div className="flex flex-col md:flex-row gap-2 items-stretch md:items-center">
            {onRefresh && (
              <Button variant="outline" onClick={onRefresh} disabled={loading}>
                Refresh
              </Button>
            )}
            <Button onClick={handleCreateGame}>New Mixed Scenario</Button>
          </div>
        </div>

        {restrictLifecycleActions && (
          <Alert variant="info" className="mb-4">
            Start, restart, and review actions have moved to the Supervision tab. Open Supervision to
            manage live games.
          </Alert>
        )}

        {error && (
          <Alert variant="destructive" className="mb-4">
            {error}
          </Alert>
        )}

        {loading ? (
          <div className="flex justify-center items-center min-h-[240px]">
            <Spinner size="lg" />
          </div>
        ) : filteredGames.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-muted-foreground mb-2">No scenarios found for your organization yet.</p>
            <p className="text-sm text-muted-foreground">
              Configure a new mixed scenario to get your users started.
            </p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[20%] min-w-[120px]">Name</TableHead>
                <TableHead className="w-[15%] min-w-[80px]">For</TableHead>
                <TableHead className="w-[12%] min-w-[90px]">Mode</TableHead>
                <TableHead className="w-[10%] min-w-[80px]">Status</TableHead>
                <TableHead className="w-[13%] min-w-[90px]">Rounds</TableHead>
                <TableHead className="w-[13%] min-w-[90px]">Last Updated</TableHead>
                <TableHead className="text-right w-[17%] min-w-[140px]">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredGames.map((game) => (
                <TableRow key={game.id}>
                  <TableCell>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className="font-semibold text-sm block truncate">
                            {game.name}
                          </span>
                        </TooltipTrigger>
                        {game.description && (
                          <TooltipContent>{game.description}</TooltipContent>
                        )}
                      </Tooltip>
                    </TooltipProvider>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm">{supplyChainDisplay(game)}</span>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        String(game.progression_mode || game?.config?.progression_mode || 'supervised')
                          .toLowerCase() === 'unsupervised'
                          ? 'info'
                          : 'outline'
                      }
                    >
                      {String(game.progression_mode || game?.config?.progression_mode || 'supervised')
                        .replace(/_/g, ' ')
                        .replace(/^./, (s) => s.toUpperCase())}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={statusColor(game.status)}>
                      {(game.status || '').replace(/_/g, ' ') || 'Unknown'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm">
                      {(() => {
                        const current = Number(game.current_round ?? 0);
                        const max = game.max_rounds;
                        if (max == null) {
                          return current;
                        }
                        return `${current} / ${max}`;
                      })()}
                    </span>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm">{formatDate(game.updated_at)}</span>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1 flex-wrap">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleViewGame(game.id, game.status)}
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            {restrictLifecycleActions ? 'Open in Supervision workspace' : 'View'}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                      {!restrictLifecycleActions && (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleRestart(game.id)}
                              >
                                <RotateCcw className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>Restart</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )}
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="sm" onClick={() => handleEdit(game)}>
                              <Pencil className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Edit</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDelete(game.id, game.name)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Delete</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
};

export default TenantScenarioConfigPanel;
