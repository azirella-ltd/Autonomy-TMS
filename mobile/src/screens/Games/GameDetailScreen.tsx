/**
 * Game Detail Screen
 * Phase 7 Sprint 1: Mobile Application
 */

import React, { useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  RefreshControl,
} from 'react-native';
import {
  Card,
  Text,
  Button,
  DataTable,
  Divider,
  ActivityIndicator,
  Chip,
  ProgressBar,
} from 'react-native-paper';
import { useAppDispatch, useAppSelector } from '../../store';
import {
  fetchGame,
  fetchGameState,
  startGame,
  playRound,
} from '../../store/slices/gamesSlice';
import { theme } from '../../theme';

export default function GameDetailScreen({ route, navigation }: any) {
  const { gameId } = route.params;
  const [refreshing, setRefreshing] = useState(false);

  const dispatch = useAppDispatch();
  const { currentGame, gameState, loading } = useAppSelector(
    (state) => state.games
  );

  useEffect(() => {
    loadGameData();
  }, [gameId]);

  const loadGameData = () => {
    dispatch(fetchGame(gameId));
    dispatch(fetchGameState(gameId));
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadGameData();
    setRefreshing(false);
  };

  const handleStartGame = () => {
    dispatch(startGame(gameId));
  };

  const handlePlayRound = () => {
    // Navigate to play round interface or trigger auto-play
    dispatch(playRound({ id: gameId }));
  };

  if (loading && !currentGame) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
      </View>
    );
  }

  if (!currentGame) {
    return (
      <View style={styles.errorContainer}>
        <Text style={styles.errorText}>Game not found</Text>
      </View>
    );
  }

  const progress = currentGame.max_rounds > 0
    ? currentGame.current_round / currentGame.max_rounds
    : 0;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.scrollContent}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
      }
    >
      {/* Game Header */}
      <Card style={styles.headerCard}>
        <Card.Content>
          <Text style={styles.gameName}>{currentGame.name}</Text>
          <View style={styles.statusRow}>
            <Chip
              icon={
                currentGame.status === 'active'
                  ? 'play-circle'
                  : currentGame.status === 'completed'
                  ? 'check-circle'
                  : 'clock'
              }
              style={[
                styles.statusChip,
                {
                  backgroundColor:
                    currentGame.status === 'active'
                      ? theme.colors.success
                      : currentGame.status === 'completed'
                      ? theme.colors.info
                      : theme.colors.warning,
                },
              ]}
              textStyle={styles.statusChipText}
            >
              {currentGame.status.toUpperCase()}
            </Chip>
          </View>

          <Divider style={styles.divider} />

          {/* Progress Bar */}
          <View style={styles.progressContainer}>
            <View style={styles.progressHeader}>
              <Text style={styles.progressLabel}>Round Progress</Text>
              <Text style={styles.progressValue}>
                {currentGame.current_round} / {currentGame.max_rounds}
              </Text>
            </View>
            <ProgressBar
              progress={progress}
              color={theme.colors.primary}
              style={styles.progressBar}
            />
          </View>

          {/* Game Actions */}
          {currentGame.status === 'pending' && (
            <Button
              mode="contained"
              icon="play"
              onPress={handleStartGame}
              style={styles.actionButton}
            >
              Start Game
            </Button>
          )}

          {currentGame.status === 'active' && (
            <Button
              mode="contained"
              icon="skip-next"
              onPress={handlePlayRound}
              loading={loading}
              disabled={loading}
              style={styles.actionButton}
            >
              Play Next Round
            </Button>
          )}
        </Card.Content>
      </Card>

      {/* Supply Chain Configuration */}
      {currentGame.supply_chain_config && (
        <Card style={styles.card}>
          <Card.Title
            title="Supply Chain Configuration"
            titleStyle={styles.cardTitle}
            left={(props) => <Card.Title {...props} />}
          />
          <Card.Content>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>Configuration:</Text>
              <Text style={styles.configValue}>
                {currentGame.supply_chain_config.name}
              </Text>
            </View>
            {currentGame.supply_chain_config.description && (
              <View style={styles.configRow}>
                <Text style={styles.configLabel}>Description:</Text>
                <Text style={styles.configValue}>
                  {currentGame.supply_chain_config.description}
                </Text>
              </View>
            )}
          </Card.Content>
        </Card>
      )}

      {/* Game State Overview */}
      {gameState && (
        <Card style={styles.card}>
          <Card.Title
            title="Current State"
            titleStyle={styles.cardTitle}
          />
          <Card.Content>
            <DataTable>
              <DataTable.Header>
                <DataTable.Title>Node</DataTable.Title>
                <DataTable.Title numeric>Inventory</DataTable.Title>
                <DataTable.Title numeric>Backlog</DataTable.Title>
              </DataTable.Header>

              {gameState.nodes?.map((node: any, index: number) => (
                <DataTable.Row key={index}>
                  <DataTable.Cell>{node.name}</DataTable.Cell>
                  <DataTable.Cell numeric>{node.inventory}</DataTable.Cell>
                  <DataTable.Cell numeric>{node.backlog}</DataTable.Cell>
                </DataTable.Row>
              ))}
            </DataTable>
          </Card.Content>
        </Card>
      )}

      {/* Metrics Summary */}
      {gameState && gameState.metrics && (
        <Card style={styles.card}>
          <Card.Title
            title="Performance Metrics"
            titleStyle={styles.cardTitle}
          />
          <Card.Content>
            <View style={styles.metricsGrid}>
              <View style={styles.metricBox}>
                <Text style={styles.metricLabel}>Total Cost</Text>
                <Text style={styles.metricValue}>
                  ${gameState.metrics.total_cost?.toFixed(2) || '0.00'}
                </Text>
              </View>
              <View style={styles.metricBox}>
                <Text style={styles.metricLabel}>Service Level</Text>
                <Text style={styles.metricValue}>
                  {(gameState.metrics.service_level * 100)?.toFixed(1) || '0'}%
                </Text>
              </View>
              <View style={styles.metricBox}>
                <Text style={styles.metricLabel}>Bullwhip Effect</Text>
                <Text style={styles.metricValue}>
                  {gameState.metrics.bullwhip_ratio?.toFixed(2) || 'N/A'}
                </Text>
              </View>
              <View style={styles.metricBox}>
                <Text style={styles.metricLabel}>Avg Inventory</Text>
                <Text style={styles.metricValue}>
                  {gameState.metrics.avg_inventory?.toFixed(0) || '0'}
                </Text>
              </View>
            </View>
          </Card.Content>
        </Card>
      )}

      {/* Players List */}
      {currentGame.players && currentGame.players.length > 0 && (
        <Card style={styles.card}>
          <Card.Title
            title="Players"
            titleStyle={styles.cardTitle}
          />
          <Card.Content>
            {currentGame.players.map((player: any, index: number) => (
              <View key={index} style={styles.playerRow}>
                <View style={styles.playerInfo}>
                  <Text style={styles.playerName}>{player.node_name}</Text>
                  <Text style={styles.playerType}>
                    {player.is_human ? 'Human' : `AI (${player.agent_strategy})`}
                  </Text>
                </View>
                <Chip
                  icon={player.is_human ? 'account' : 'robot'}
                  compact
                >
                  {player.is_human ? 'Human' : 'AI'}
                </Chip>
              </View>
            ))}
          </Card.Content>
        </Card>
      )}

      {/* Game Info */}
      <Card style={styles.card}>
        <Card.Title
          title="Game Information"
          titleStyle={styles.cardTitle}
        />
        <Card.Content>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Created:</Text>
            <Text style={styles.infoValue}>
              {new Date(currentGame.created_at).toLocaleString()}
            </Text>
          </View>
          {currentGame.started_at && (
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>Started:</Text>
              <Text style={styles.infoValue}>
                {new Date(currentGame.started_at).toLocaleString()}
              </Text>
            </View>
          )}
          {currentGame.completed_at && (
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>Completed:</Text>
              <Text style={styles.infoValue}>
                {new Date(currentGame.completed_at).toLocaleString()}
              </Text>
            </View>
          )}
        </Card.Content>
      </Card>
    </ScrollView>
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
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: theme.spacing.xl,
  },
  errorText: {
    fontSize: 16,
    color: theme.colors.error,
  },
  headerCard: {
    marginBottom: theme.spacing.md,
  },
  gameName: {
    fontSize: 24,
    fontWeight: 'bold',
    color: theme.colors.text,
    marginBottom: theme.spacing.sm,
  },
  statusRow: {
    flexDirection: 'row',
    marginBottom: theme.spacing.sm,
  },
  statusChip: {
    alignSelf: 'flex-start',
  },
  statusChipText: {
    color: '#fff',
    fontWeight: '600',
  },
  divider: {
    marginVertical: theme.spacing.md,
  },
  progressContainer: {
    marginBottom: theme.spacing.md,
  },
  progressHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.xs,
  },
  progressLabel: {
    fontSize: 14,
    color: theme.colors.textSecondary,
  },
  progressValue: {
    fontSize: 14,
    fontWeight: '600',
    color: theme.colors.text,
  },
  progressBar: {
    height: 8,
    borderRadius: 4,
  },
  actionButton: {
    marginTop: theme.spacing.sm,
  },
  card: {
    marginBottom: theme.spacing.md,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: '600',
  },
  configRow: {
    marginBottom: theme.spacing.sm,
  },
  configLabel: {
    fontSize: 14,
    color: theme.colors.textSecondary,
    marginBottom: 4,
  },
  configValue: {
    fontSize: 14,
    color: theme.colors.text,
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  metricBox: {
    flex: 1,
    minWidth: '48%',
    padding: theme.spacing.md,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.roundness,
    borderWidth: 1,
    borderColor: theme.colors.disabled,
  },
  metricLabel: {
    fontSize: 12,
    color: theme.colors.textSecondary,
    marginBottom: 4,
  },
  metricValue: {
    fontSize: 20,
    fontWeight: 'bold',
    color: theme.colors.primary,
  },
  playerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: theme.spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.disabled,
  },
  playerInfo: {
    flex: 1,
  },
  playerName: {
    fontSize: 16,
    fontWeight: '600',
    color: theme.colors.text,
  },
  playerType: {
    fontSize: 12,
    color: theme.colors.textSecondary,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.sm,
  },
  infoLabel: {
    fontSize: 14,
    color: theme.colors.textSecondary,
  },
  infoValue: {
    fontSize: 14,
    color: theme.colors.text,
    fontWeight: '500',
  },
});
