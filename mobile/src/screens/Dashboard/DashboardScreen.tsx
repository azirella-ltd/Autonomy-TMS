/**
 * Dashboard Screen
 * Phase 7 Sprint 1: Mobile Application
 */

import React, { useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import {
  Card,
  Text,
  Button,
  Avatar,
  IconButton,
  ActivityIndicator,
  FAB,
} from 'react-native-paper';
import { useAppDispatch, useAppSelector } from '../../store';
import { fetchGames } from '../../store/slices/gamesSlice';
import { fetchFeaturedTemplates } from '../../store/slices/templatesSlice';
import { theme } from '../../theme';

interface MetricCardProps {
  title: string;
  value: string | number;
  icon: string;
  color: string;
  subtitle?: string;
}

const MetricCard = ({ title, value, icon, color, subtitle }: MetricCardProps) => (
  <Card style={styles.metricCard}>
    <Card.Content style={styles.metricContent}>
      <View style={styles.metricHeader}>
        <Avatar.Icon
          size={48}
          icon={icon}
          style={[styles.metricIcon, { backgroundColor: color }]}
        />
        <View style={styles.metricTextContainer}>
          <Text style={styles.metricValue}>{value}</Text>
          <Text style={styles.metricTitle}>{title}</Text>
          {subtitle && <Text style={styles.metricSubtitle}>{subtitle}</Text>}
        </View>
      </View>
    </Card.Content>
  </Card>
);

interface GameCardProps {
  game: any;
  onPress: () => void;
}

const GameCard = ({ game, onPress }: GameCardProps) => (
  <TouchableOpacity onPress={onPress}>
    <Card style={styles.gameCard}>
      <Card.Content>
        <View style={styles.gameHeader}>
          <Text style={styles.gameName}>{game.name}</Text>
          <View
            style={[
              styles.statusBadge,
              {
                backgroundColor:
                  game.status === 'active'
                    ? theme.colors.success
                    : game.status === 'pending'
                    ? theme.colors.warning
                    : theme.colors.textSecondary,
              },
            ]}
          >
            <Text style={styles.statusText}>{game.status.toUpperCase()}</Text>
          </View>
        </View>
        <View style={styles.gameDetails}>
          <View style={styles.gameDetailRow}>
            <Text style={styles.gameDetailLabel}>Round:</Text>
            <Text style={styles.gameDetailValue}>
              {game.current_round} / {game.max_rounds}
            </Text>
          </View>
          <View style={styles.gameDetailRow}>
            <Text style={styles.gameDetailLabel}>Players:</Text>
            <Text style={styles.gameDetailValue}>{game.player_count || 'N/A'}</Text>
          </View>
        </View>
      </Card.Content>
    </Card>
  </TouchableOpacity>
);

export default function DashboardScreen({ navigation }: any) {
  const [refreshing, setRefreshing] = useState(false);

  const dispatch = useAppDispatch();
  const { user } = useAppSelector((state) => state.auth);
  const { games, loading: gamesLoading } = useAppSelector((state) => state.games);
  const { featuredTemplates } = useAppSelector((state) => state.templates);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = () => {
    dispatch(fetchGames({ page: 1, status: 'active' }));
    dispatch(fetchFeaturedTemplates());
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadDashboardData();
    setRefreshing(false);
  };

  const handleGamePress = (gameId: number) => {
    navigation.navigate('Games', {
      screen: 'GameDetail',
      params: { gameId },
    });
  };

  const handleCreateGame = () => {
    navigation.navigate('Games', {
      screen: 'CreateGame',
    });
  };

  const handleViewAllGames = () => {
    navigation.navigate('Games', {
      screen: 'GamesList',
    });
  };

  const handleViewTemplates = () => {
    navigation.navigate('Templates');
  };

  // Calculate metrics
  const activeGames = games.filter((g) => g.status === 'active').length;
  const completedGames = games.filter((g) => g.status === 'completed').length;
  const totalGames = games.length;

  return (
    <View style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
        }
      >
        {/* Welcome Section */}
        <View style={styles.welcomeSection}>
          <Text style={styles.welcomeText}>
            Welcome back, {user?.first_name || 'User'}!
          </Text>
          <Text style={styles.welcomeSubtext}>
            Here's your supply chain overview
          </Text>
        </View>

        {/* Metrics Grid */}
        <View style={styles.metricsGrid}>
          <MetricCard
            title="Active Games"
            value={activeGames}
            icon="gamepad-variant"
            color={theme.colors.primary}
          />
          <MetricCard
            title="Completed"
            value={completedGames}
            icon="check-circle"
            color={theme.colors.success}
          />
          <MetricCard
            title="Total Games"
            value={totalGames}
            icon="chart-bar"
            color={theme.colors.info}
          />
          <MetricCard
            title="Templates"
            value={featuredTemplates.length}
            icon="file-multiple"
            color={theme.colors.tertiary}
          />
        </View>

        {/* Quick Actions */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Quick Actions</Text>
          <View style={styles.quickActionsContainer}>
            <Button
              mode="contained"
              icon="plus-circle"
              onPress={handleCreateGame}
              style={styles.quickActionButton}
            >
              New Game
            </Button>
            <Button
              mode="outlined"
              icon="file-document"
              onPress={handleViewTemplates}
              style={styles.quickActionButton}
            >
              Browse Templates
            </Button>
          </View>
        </View>

        {/* Active Games Section */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Active Games</Text>
            <Button mode="text" onPress={handleViewAllGames}>
              View All
            </Button>
          </View>

          {gamesLoading ? (
            <ActivityIndicator size="large" color={theme.colors.primary} />
          ) : games.filter((g) => g.status === 'active').length > 0 ? (
            games
              .filter((g) => g.status === 'active')
              .slice(0, 3)
              .map((game) => (
                <GameCard
                  key={game.id}
                  game={game}
                  onPress={() => handleGamePress(game.id)}
                />
              ))
          ) : (
            <Card style={styles.emptyCard}>
              <Card.Content style={styles.emptyContent}>
                <Avatar.Icon
                  size={64}
                  icon="gamepad-variant-outline"
                  style={styles.emptyIcon}
                />
                <Text style={styles.emptyTitle}>No Active Games</Text>
                <Text style={styles.emptySubtitle}>
                  Create a new game to get started
                </Text>
                <Button
                  mode="contained"
                  icon="plus"
                  onPress={handleCreateGame}
                  style={styles.emptyButton}
                >
                  Create Game
                </Button>
              </Card.Content>
            </Card>
          )}
        </View>

        {/* Featured Templates Section */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Featured Templates</Text>
            <Button mode="text" onPress={handleViewTemplates}>
              View All
            </Button>
          </View>

          {featuredTemplates.slice(0, 3).map((template) => (
            <Card key={template.id} style={styles.templateCard}>
              <Card.Content>
                <Text style={styles.templateName}>{template.name}</Text>
                <Text style={styles.templateDescription} numberOfLines={2}>
                  {template.description}
                </Text>
                <View style={styles.templateMeta}>
                  <Text style={styles.templateMetaText}>
                    {template.difficulty}
                  </Text>
                  <Text style={styles.templateMetaText}>
                    {template.usage_count} uses
                  </Text>
                </View>
              </Card.Content>
            </Card>
          ))}
        </View>
      </ScrollView>

      {/* Floating Action Button */}
      <FAB
        icon="plus"
        style={styles.fab}
        onPress={handleCreateGame}
        label="New Game"
      />
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
    paddingBottom: 100,
  },
  welcomeSection: {
    marginBottom: theme.spacing.lg,
  },
  welcomeText: {
    fontSize: 28,
    fontWeight: 'bold',
    color: theme.colors.text,
  },
  welcomeSubtext: {
    fontSize: 16,
    color: theme.colors.textSecondary,
    marginTop: theme.spacing.xs,
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginBottom: theme.spacing.lg,
    gap: theme.spacing.sm,
  },
  metricCard: {
    flex: 1,
    minWidth: '48%',
    marginBottom: theme.spacing.sm,
  },
  metricContent: {
    padding: theme.spacing.sm,
  },
  metricHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  metricIcon: {
    marginRight: theme.spacing.sm,
  },
  metricTextContainer: {
    flex: 1,
  },
  metricValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: theme.colors.text,
  },
  metricTitle: {
    fontSize: 12,
    color: theme.colors.textSecondary,
  },
  metricSubtitle: {
    fontSize: 10,
    color: theme.colors.textSecondary,
  },
  section: {
    marginBottom: theme.spacing.lg,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.md,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: theme.colors.text,
  },
  quickActionsContainer: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  quickActionButton: {
    flex: 1,
  },
  gameCard: {
    marginBottom: theme.spacing.sm,
  },
  gameHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  gameName: {
    fontSize: 18,
    fontWeight: '600',
    color: theme.colors.text,
    flex: 1,
  },
  statusBadge: {
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 10,
    color: '#fff',
    fontWeight: '600',
  },
  gameDetails: {
    marginTop: theme.spacing.sm,
  },
  gameDetailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  gameDetailLabel: {
    fontSize: 14,
    color: theme.colors.textSecondary,
  },
  gameDetailValue: {
    fontSize: 14,
    fontWeight: '600',
    color: theme.colors.text,
  },
  emptyCard: {
    marginVertical: theme.spacing.md,
  },
  emptyContent: {
    alignItems: 'center',
    padding: theme.spacing.xl,
  },
  emptyIcon: {
    backgroundColor: theme.colors.disabled,
    marginBottom: theme.spacing.md,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: theme.colors.text,
    marginBottom: theme.spacing.xs,
  },
  emptySubtitle: {
    fontSize: 14,
    color: theme.colors.textSecondary,
    marginBottom: theme.spacing.md,
  },
  emptyButton: {
    marginTop: theme.spacing.sm,
  },
  templateCard: {
    marginBottom: theme.spacing.sm,
  },
  templateName: {
    fontSize: 16,
    fontWeight: '600',
    color: theme.colors.text,
    marginBottom: theme.spacing.xs,
  },
  templateDescription: {
    fontSize: 14,
    color: theme.colors.textSecondary,
    marginBottom: theme.spacing.sm,
  },
  templateMeta: {
    flexDirection: 'row',
    gap: theme.spacing.md,
  },
  templateMetaText: {
    fontSize: 12,
    color: theme.colors.textSecondary,
  },
  fab: {
    position: 'absolute',
    margin: theme.spacing.md,
    right: 0,
    bottom: 0,
    backgroundColor: theme.colors.primary,
  },
});
