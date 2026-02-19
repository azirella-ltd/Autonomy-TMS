/**
 * Analytics Screen
 * Phase 7 Sprint 1: Mobile Application
 */

import React, { useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  RefreshControl,
  Dimensions,
} from 'react-native';
import {
  Card,
  Text,
  Button,
  SegmentedButtons,
  ActivityIndicator,
  Chip,
  ProgressBar,
} from 'react-native-paper';
import { useAppDispatch, useAppSelector } from '../../store';
import {
  fetchAdvancedMetrics,
  fetchStochasticMetrics,
  runMonteCarloSimulation,
} from '../../store/slices/analyticsSlice';
import { fetchGames } from '../../store/slices/gamesSlice';
import { theme } from '../../theme';
import { LineChart, BarChart, PieChart } from '../../components/charts';

const { width } = Dimensions.get('window');

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  color?: string;
}

const MetricCard = ({ title, value, subtitle, color }: MetricCardProps) => (
  <Card style={styles.metricCard}>
    <Card.Content>
      <Text style={styles.metricTitle}>{title}</Text>
      <Text style={[styles.metricValue, color && { color }]}>{value}</Text>
      {subtitle && <Text style={styles.metricSubtitle}>{subtitle}</Text>}
    </Card.Content>
  </Card>
);

interface PercentileCardProps {
  title: string;
  data: {
    percentile_10: number;
    percentile_50: number;
    percentile_90: number;
    mean: number;
    std_dev: number;
  };
}

const PercentileCard = ({ title, data }: PercentileCardProps) => (
  <Card style={styles.percentileCard}>
    <Card.Title title={title} titleStyle={styles.cardTitle} />
    <Card.Content>
      <View style={styles.percentileRow}>
        <Text style={styles.percentileLabel}>10th Percentile:</Text>
        <Text style={styles.percentileValue}>{data.percentile_10.toFixed(2)}</Text>
      </View>
      <View style={styles.percentileRow}>
        <Text style={styles.percentileLabel}>Median (50th):</Text>
        <Text style={[styles.percentileValue, styles.medianValue]}>
          {data.percentile_50.toFixed(2)}
        </Text>
      </View>
      <View style={styles.percentileRow}>
        <Text style={styles.percentileLabel}>90th Percentile:</Text>
        <Text style={styles.percentileValue}>{data.percentile_90.toFixed(2)}</Text>
      </View>
      <View style={styles.percentileRow}>
        <Text style={styles.percentileLabel}>Mean:</Text>
        <Text style={styles.percentileValue}>{data.mean.toFixed(2)}</Text>
      </View>
      <View style={styles.percentileRow}>
        <Text style={styles.percentileLabel}>Std Dev:</Text>
        <Text style={styles.percentileValue}>{data.std_dev.toFixed(2)}</Text>
      </View>
    </Card.Content>
  </Card>
);

export default function AnalyticsScreen({ navigation }: any) {
  const [selectedGameId, setSelectedGameId] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState('overview');
  const [refreshing, setRefreshing] = useState(false);

  const dispatch = useAppDispatch();
  const { games } = useAppSelector((state) => state.games);
  const {
    advancedMetrics,
    stochasticMetrics,
    monteCarloResults,
    loading,
    simulationProgress,
  } = useAppSelector((state) => state.analytics);

  useEffect(() => {
    // Load completed games for analysis
    dispatch(fetchGames({ page: 1, status: 'completed' }));
  }, [dispatch]);

  useEffect(() => {
    // Auto-select first game if available
    if (games.length > 0 && !selectedGameId) {
      setSelectedGameId(games[0].id);
    }
  }, [games]);

  useEffect(() => {
    // Load analytics when game is selected
    if (selectedGameId) {
      loadAnalytics();
    }
  }, [selectedGameId]);

  const loadAnalytics = () => {
    if (selectedGameId) {
      dispatch(fetchAdvancedMetrics(selectedGameId));
      dispatch(fetchStochasticMetrics(selectedGameId));
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadAnalytics();
    setRefreshing(false);
  };

  const handleRunMonteCarlo = () => {
    if (selectedGameId) {
      dispatch(
        runMonteCarloSimulation({
          gameId: selectedGameId,
          numSimulations: 1000,
          varianceLevel: 0.2,
        })
      );
    }
  };

  const completedGames = games.filter((g) => g.status === 'completed');

  return (
    <View style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
        }
      >
        {/* Game Selection */}
        <Card style={styles.selectionCard}>
          <Card.Title title="Select Game" titleStyle={styles.cardTitle} />
          <Card.Content>
            {completedGames.length === 0 ? (
              <View style={styles.emptyState}>
                <Text style={styles.emptyText}>
                  No completed games available for analysis
                </Text>
                <Button
                  mode="outlined"
                  icon="gamepad-variant"
                  onPress={() => navigation.navigate('Games')}
                  style={styles.emptyButton}
                >
                  View Games
                </Button>
              </View>
            ) : (
              <View style={styles.gameChips}>
                {completedGames.slice(0, 5).map((game) => (
                  <Chip
                    key={game.id}
                    selected={selectedGameId === game.id}
                    onPress={() => setSelectedGameId(game.id)}
                    style={styles.gameChip}
                  >
                    {game.name}
                  </Chip>
                ))}
              </View>
            )}
          </Card.Content>
        </Card>

        {selectedGameId && (
          <>
            {/* View Mode Selector */}
            <SegmentedButtons
              value={viewMode}
              onValueChange={setViewMode}
              buttons={[
                { value: 'overview', label: 'Overview' },
                { value: 'stochastic', label: 'Stochastic' },
                { value: 'monte-carlo', label: 'Monte Carlo' },
              ]}
              style={styles.segmentedButtons}
            />

            {/* Overview Tab */}
            {viewMode === 'overview' && advancedMetrics && (
              <View>
                {/* Key Metrics Grid */}
                <View style={styles.metricsGrid}>
                  <MetricCard
                    title="Total Cost"
                    value={`$${advancedMetrics.total_cost.toFixed(2)}`}
                    color={theme.colors.error}
                  />
                  <MetricCard
                    title="Service Level"
                    value={`${(advancedMetrics.service_level * 100).toFixed(1)}%`}
                    color={theme.colors.success}
                  />
                  <MetricCard
                    title="Bullwhip Effect"
                    value={advancedMetrics.bullwhip_effect.toFixed(2)}
                    subtitle="Lower is better"
                    color={theme.colors.warning}
                  />
                  <MetricCard
                    title="Avg Inventory"
                    value={advancedMetrics.avg_inventory.toFixed(0)}
                    subtitle="units"
                    color={theme.colors.info}
                  />
                  <MetricCard
                    title="Avg Backlog"
                    value={advancedMetrics.avg_backlog.toFixed(0)}
                    subtitle="units"
                    color={theme.colors.error}
                  />
                </View>

                {/* Cost Breakdown */}
                <Card style={styles.card}>
                  <Card.Title title="Cost Breakdown" titleStyle={styles.cardTitle} />
                  <Card.Content>
                    <View style={styles.costRow}>
                      <Text style={styles.costLabel}>Holding Cost:</Text>
                      <Text style={styles.costValue}>
                        ${advancedMetrics.cost_breakdown.holding_cost.toFixed(2)}
                      </Text>
                    </View>
                    <View style={styles.costRow}>
                      <Text style={styles.costLabel}>Backlog Cost:</Text>
                      <Text style={styles.costValue}>
                        ${advancedMetrics.cost_breakdown.backlog_cost.toFixed(2)}
                      </Text>
                    </View>
                    <View style={styles.costRow}>
                      <Text style={styles.costLabel}>Ordering Cost:</Text>
                      <Text style={styles.costValue}>
                        ${advancedMetrics.cost_breakdown.ordering_cost.toFixed(2)}
                      </Text>
                    </View>
                  </Card.Content>
                </Card>

                {/* Cost Breakdown Pie Chart */}
                <Card style={styles.card}>
                  <Card.Title
                    title="Cost Distribution"
                    titleStyle={styles.cardTitle}
                  />
                  <Card.Content>
                    <PieChart
                      data={[
                        {
                          x: 'Holding',
                          y: advancedMetrics.cost_breakdown.holding_cost,
                        },
                        {
                          x: 'Backlog',
                          y: advancedMetrics.cost_breakdown.backlog_cost,
                        },
                        {
                          x: 'Ordering',
                          y: advancedMetrics.cost_breakdown.ordering_cost,
                        },
                      ]}
                      height={250}
                      showLegend={true}
                      showLabels={true}
                    />
                  </Card.Content>
                </Card>

                {/* Node Performance Bar Chart */}
                <Card style={styles.card}>
                  <Card.Title
                    title="Node Comparison"
                    titleStyle={styles.cardTitle}
                  />
                  <Card.Content>
                    <BarChart
                      series={[
                        {
                          name: 'Service Level (%)',
                          data: advancedMetrics.node_metrics.map((node) => ({
                            x: node.node_name,
                            y: node.service_level * 100,
                          })),
                        },
                      ]}
                      yLabel="Service Level (%)"
                      height={250}
                      showTooltip={true}
                    />
                  </Card.Content>
                </Card>

                {/* Node-level Metrics */}
                <Card style={styles.card}>
                  <Card.Title
                    title="Node Performance"
                    titleStyle={styles.cardTitle}
                  />
                  <Card.Content>
                    {advancedMetrics.node_metrics.map((node, index) => (
                      <View key={index} style={styles.nodeCard}>
                        <Text style={styles.nodeName}>{node.node_name}</Text>
                        <View style={styles.nodeMetrics}>
                          <View style={styles.nodeMetricItem}>
                            <Text style={styles.nodeMetricLabel}>Bullwhip:</Text>
                            <Text style={styles.nodeMetricValue}>
                              {node.bullwhip_ratio.toFixed(2)}
                            </Text>
                          </View>
                          <View style={styles.nodeMetricItem}>
                            <Text style={styles.nodeMetricLabel}>Service:</Text>
                            <Text style={styles.nodeMetricValue}>
                              {(node.service_level * 100).toFixed(1)}%
                            </Text>
                          </View>
                          <View style={styles.nodeMetricItem}>
                            <Text style={styles.nodeMetricLabel}>Avg Inv:</Text>
                            <Text style={styles.nodeMetricValue}>
                              {node.avg_inventory.toFixed(0)}
                            </Text>
                          </View>
                        </View>
                      </View>
                    ))}
                  </Card.Content>
                </Card>
              </View>
            )}

            {/* Stochastic Tab */}
            {viewMode === 'stochastic' && stochasticMetrics && (
              <View>
                <Card style={styles.infoCard}>
                  <Card.Content>
                    <Text style={styles.infoText}>
                      Stochastic analysis shows the distribution of outcomes across
                      multiple scenarios
                    </Text>
                  </Card.Content>
                </Card>

                <PercentileCard title="Total Cost" data={stochasticMetrics.total_cost} />
                <PercentileCard
                  title="Service Level"
                  data={stochasticMetrics.service_level}
                />
                <PercentileCard
                  title="Bullwhip Ratio"
                  data={stochasticMetrics.bullwhip_ratio}
                />
                <PercentileCard
                  title="Inventory Variance"
                  data={stochasticMetrics.inventory_variance}
                />
              </View>
            )}

            {/* Monte Carlo Tab */}
            {viewMode === 'monte-carlo' && (
              <View>
                <Card style={styles.infoCard}>
                  <Card.Content>
                    <Text style={styles.infoText}>
                      Run Monte Carlo simulation to analyze uncertainty and risk across
                      thousands of scenarios
                    </Text>
                  </Card.Content>
                </Card>

                {/* Simulation Controls */}
                <Card style={styles.card}>
                  <Card.Title
                    title="Run Simulation"
                    titleStyle={styles.cardTitle}
                  />
                  <Card.Content>
                    <Button
                      mode="contained"
                      icon="play"
                      onPress={handleRunMonteCarlo}
                      loading={simulationProgress.status === 'running'}
                      disabled={simulationProgress.status === 'running'}
                      style={styles.simulationButton}
                    >
                      {simulationProgress.status === 'running'
                        ? 'Running Simulation...'
                        : 'Run Monte Carlo (1000 runs)'}
                    </Button>

                    {simulationProgress.status === 'running' && (
                      <View style={styles.progressContainer}>
                        <Text style={styles.progressText}>
                          {simulationProgress.current} / {simulationProgress.total}
                        </Text>
                        <ProgressBar
                          progress={
                            simulationProgress.total > 0
                              ? simulationProgress.current / simulationProgress.total
                              : 0
                          }
                          color={theme.colors.primary}
                        />
                      </View>
                    )}
                  </Card.Content>
                </Card>

                {/* Results */}
                {monteCarloResults && (
                  <Card style={styles.card}>
                    <Card.Title title="Results" titleStyle={styles.cardTitle} />
                    <Card.Content>
                      <Text style={styles.resultsText}>
                        Monte Carlo simulation completed with {monteCarloResults.num_runs}{' '}
                        runs
                      </Text>
                      {/* Display results here - expand as needed */}
                    </Card.Content>
                  </Card>
                )}
              </View>
            )}

            {loading && !advancedMetrics && (
              <View style={styles.loadingContainer}>
                <ActivityIndicator size="large" color={theme.colors.primary} />
                <Text style={styles.loadingText}>Loading analytics...</Text>
              </View>
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  scrollContent: {
    padding: theme.spacing.md,
    paddingBottom: theme.spacing.xl,
  },
  selectionCard: {
    marginBottom: theme.spacing.md,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: '600',
  },
  emptyState: {
    alignItems: 'center',
    padding: theme.spacing.lg,
  },
  emptyText: {
    fontSize: 14,
    color: theme.colors.textSecondary,
    textAlign: 'center',
    marginBottom: theme.spacing.md,
  },
  emptyButton: {
    marginTop: theme.spacing.sm,
  },
  gameChips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  gameChip: {
    marginRight: theme.spacing.xs,
    marginBottom: theme.spacing.xs,
  },
  segmentedButtons: {
    marginBottom: theme.spacing.md,
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.md,
  },
  metricCard: {
    flex: 1,
    minWidth: (width - theme.spacing.md * 3) / 2,
  },
  metricTitle: {
    fontSize: 12,
    color: theme.colors.textSecondary,
    marginBottom: 4,
  },
  metricValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: theme.colors.text,
  },
  metricSubtitle: {
    fontSize: 10,
    color: theme.colors.textSecondary,
    marginTop: 2,
  },
  card: {
    marginBottom: theme.spacing.md,
  },
  costRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  costLabel: {
    fontSize: 14,
    color: theme.colors.textSecondary,
  },
  costValue: {
    fontSize: 14,
    fontWeight: '600',
    color: theme.colors.text,
  },
  nodeCard: {
    marginBottom: theme.spacing.md,
    padding: theme.spacing.sm,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.roundness,
    borderWidth: 1,
    borderColor: theme.colors.disabled,
  },
  nodeName: {
    fontSize: 16,
    fontWeight: '600',
    color: theme.colors.text,
    marginBottom: theme.spacing.sm,
  },
  nodeMetrics: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  nodeMetricItem: {
    flex: 1,
  },
  nodeMetricLabel: {
    fontSize: 12,
    color: theme.colors.textSecondary,
    marginBottom: 2,
  },
  nodeMetricValue: {
    fontSize: 14,
    fontWeight: '600',
    color: theme.colors.text,
  },
  infoCard: {
    marginBottom: theme.spacing.md,
    backgroundColor: theme.colors.info + '20',
  },
  infoText: {
    fontSize: 14,
    color: theme.colors.text,
    lineHeight: 20,
  },
  percentileCard: {
    marginBottom: theme.spacing.md,
  },
  percentileRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  percentileLabel: {
    fontSize: 14,
    color: theme.colors.textSecondary,
  },
  percentileValue: {
    fontSize: 14,
    fontWeight: '600',
    color: theme.colors.text,
  },
  medianValue: {
    color: theme.colors.primary,
    fontWeight: 'bold',
  },
  simulationButton: {
    marginVertical: theme.spacing.sm,
  },
  progressContainer: {
    marginTop: theme.spacing.md,
  },
  progressText: {
    fontSize: 12,
    color: theme.colors.textSecondary,
    marginBottom: theme.spacing.xs,
    textAlign: 'center',
  },
  resultsText: {
    fontSize: 14,
    color: theme.colors.text,
  },
  loadingContainer: {
    alignItems: 'center',
    padding: theme.spacing.xl,
  },
  loadingText: {
    marginTop: theme.spacing.md,
    fontSize: 14,
    color: theme.colors.textSecondary,
  },
});
