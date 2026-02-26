import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  CardContent,
  Checkbox,
  Progress,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../components/common';
import { format } from 'date-fns';
import simulationApi from '../../services/api';

const formatDate = (value) => {
  if (!value) return '—';
  try {
    return format(new Date(value), 'MMM d, yyyy HH:mm');
  } catch (error) {
    return String(value);
  }
};

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

const formatCurrency = (value) => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return '—';
  }
  return currencyFormatter.format(parsed);
};

const TenantScenarioComparisonPanel = ({
  games = [],
  loading = false,
  error = null,
  onRefresh,
  groupId = null,
  currentUserId = null,
  selectedSupplyChainId = 'all',
}) => {
  const [selectedIds, setSelectedIds] = useState([]);
  const [summaryRows, setSummaryRows] = useState([]);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState(null);

  const completedGames = useMemo(() => {
    if (!Array.isArray(games)) {
      return [];
    }

    const normalizedSupplyChainId = String(selectedSupplyChainId ?? 'all');

    const filteredByGroup = games.filter((game) => {
      if (!game) return false;
      const targetGroup = game.tenant_id ?? game?.config?.tenant_id ?? null;
      if (groupId != null) {
        if (targetGroup != null && Number.isFinite(Number(targetGroup))) {
          return Number(targetGroup) === Number(groupId);
        }
        if (game.created_by != null && Number.isFinite(Number(currentUserId))) {
          return Number(game.created_by) === Number(currentUserId);
        }
      }
      return true;
    });

    const filteredBySupplyChain = filteredByGroup.filter((game) => {
      if (normalizedSupplyChainId === 'all') {
        return true;
      }

      const gameSupplyChainId =
        game.supply_chain_config_id ?? game?.config?.supply_chain_config_id ?? null;
      if (gameSupplyChainId == null) {
        return false;
      }

      return String(gameSupplyChainId) === normalizedSupplyChainId;
    });

    const completedStatuses = new Set(['completed', 'finished']);

    return filteredBySupplyChain
      .filter((game) => completedStatuses.has(String(game?.status || '').toLowerCase()))
      .map((game) => ({
        ...game,
        completed_at: game?.completed_at || game?.finished_at || null,
      }))
      .sort((a, b) => {
        const dateA = a.completed_at ? new Date(a.completed_at).getTime() : 0;
        const dateB = b.completed_at ? new Date(b.completed_at).getTime() : 0;
        return dateB - dateA;
      });
  }, [games, groupId, currentUserId, selectedSupplyChainId]);

  useEffect(() => {
    setSelectedIds((prev) => {
      const completedIds = completedGames.map((game) => game.id);
      if (prev.length === completedIds.length && prev.every((id) => completedIds.includes(id))) {
        return prev;
      }
      return completedIds;
    });
  }, [completedGames]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const allSelected = completedGames.length > 0 && selectedIds.length === completedGames.length;
  const someSelected = selectedIds.length > 0 && !allSelected;

  const handleToggleAll = (checked) => {
    if (checked) {
      setSelectedIds(completedGames.map((game) => game.id));
    } else {
      setSelectedIds([]);
    }
  };

  const handleToggleGame = (gameId) => () => {
    setSelectedIds((prev) => {
      const set = new Set(prev);
      if (set.has(gameId)) {
        set.delete(gameId);
      } else {
        set.add(gameId);
      }
      return Array.from(set);
    });
  };

  const handleGenerateSummary = useCallback(async () => {
    if (selectedIds.length === 0) {
      setSummaryRows([]);
      return;
    }

    setSummaryLoading(true);
    setSummaryError(null);

    try {
      const requests = selectedIds.map(async (gameId) => {
        try {
          const report = await simulationApi.getReport(gameId);
          const totals = report?.totals ?? {};

          let holdingCost = 0;
          let backlogCost = 0;
          let totalCost = 0;

          Object.values(totals).forEach((roleTotals) => {
            if (!roleTotals) return;
            holdingCost += Number(roleTotals?.holding_cost ?? 0);
            backlogCost += Number(roleTotals?.backorder_cost ?? roleTotals?.backlog_cost ?? 0);
            totalCost += Number(roleTotals?.total_cost ?? 0);
          });

          const fallbackTotal = Number(report?.total_cost ?? totalCost);
          totalCost = Number.isFinite(fallbackTotal) ? fallbackTotal : totalCost;

          const referenceGame = completedGames.find((game) => game.id === gameId);

          return {
            gameId,
            gameName: report?.name || referenceGame?.name || `Game #${gameId}`,
            holdingCost,
            backlogCost,
            totalCost,
          };
        } catch (innerError) {
          throw innerError;
        }
      });

      const rows = await Promise.all(requests);
      const sortedRows = rows
        .filter((row) => row != null)
        .sort((a, b) => (a.totalCost ?? 0) - (b.totalCost ?? 0));
      setSummaryRows(sortedRows);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Unable to generate summary right now.';
      setSummaryError(detail);
      setSummaryRows([]);
    } finally {
      setSummaryLoading(false);
    }
  }, [selectedIds, completedGames]);

  return (
    <Card>
      <CardContent className="p-4 md:p-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
          <div>
            <h2 className="text-lg font-bold">Completed Scenario Comparison</h2>
            <p className="text-sm text-muted-foreground">
              Select completed scenarios and generate a ranked cost summary to review performance across sessions.
            </p>
          </div>
          <div className="flex gap-2">
            {onRefresh && (
              <Button variant="outline" onClick={onRefresh} disabled={loading}>
                Refresh Games
              </Button>
            )}
            <Button
              onClick={handleGenerateSummary}
              disabled={selectedIds.length === 0 || summaryLoading}
            >
              Generate Summary
            </Button>
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
        ) : completedGames.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-muted-foreground mb-2">No completed scenarios yet.</p>
            <p className="text-sm text-muted-foreground">
              Once scenarios are completed, you can compare their cost performance here.
            </p>
          </div>
        ) : (
          <Table className="mb-6">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[50px]">
                  <Checkbox
                    checked={allSelected}
                    indeterminate={someSelected}
                    onCheckedChange={handleToggleAll}
                    aria-label="Select all completed games"
                  />
                </TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Rounds</TableHead>
                <TableHead>Completed</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {completedGames.map((game) => (
                <TableRow key={game.id}>
                  <TableCell>
                    <Checkbox
                      checked={selectedSet.has(game.id)}
                      onCheckedChange={handleToggleGame(game.id)}
                      aria-label={`Select ${game.name}`}
                    />
                  </TableCell>
                  <TableCell>{game.name}</TableCell>
                  <TableCell className="capitalize">
                    {String(game.status || '').replace(/_/g, ' ')}
                  </TableCell>
                  <TableCell>{game.current_round ?? game.max_rounds ?? '—'}</TableCell>
                  <TableCell>{formatDate(game.completed_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {summaryError && (
          <Alert variant="destructive" className="mb-4">
            {summaryError}
          </Alert>
        )}

        {summaryLoading && <Progress className="mb-4" />}

        {summaryRows.length > 0 && (
          <Card variant="outline">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Game Name</TableHead>
                  <TableHead className="text-right">Holding Cost</TableHead>
                  <TableHead className="text-right">Backlog Cost</TableHead>
                  <TableHead className="text-right">Total Cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {summaryRows.map((row) => (
                  <TableRow key={row.gameId}>
                    <TableCell>{row.gameName}</TableCell>
                    <TableCell className="text-right">{formatCurrency(row.holdingCost)}</TableCell>
                    <TableCell className="text-right">{formatCurrency(row.backlogCost)}</TableCell>
                    <TableCell className="text-right">{formatCurrency(row.totalCost)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
      </CardContent>
    </Card>
  );
};

export default TenantScenarioComparisonPanel;
