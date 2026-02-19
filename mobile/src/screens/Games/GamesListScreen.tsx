/**
 * Games List Screen
 * Phase 7 Sprint 1: Mobile Application
 */

import React, { useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import {
  Card,
  Text,
  Searchbar,
  Chip,
  FAB,
  ActivityIndicator,
  Avatar,
} from 'react-native-paper';
import { useAppDispatch, useAppSelector } from '../../store';
import { fetchGames } from '../../store/slices/gamesSlice';
import { theme } from '../../theme';

const FILTERS = [
  { label: 'All', value: '' },
  { label: 'Active', value: 'active' },
  { label: 'Pending', value: 'pending' },
  { label: 'Completed', value: 'completed' },
];

interface GameCardProps {
  game: any;
  onPress: () => void;
}

const GameCard = ({ game, onPress }: GameCardProps) => {
  const statusColor =
    game.status === 'active'
      ? theme.colors.success
      : game.status === 'pending'
      ? theme.colors.warning
      : game.status === 'completed'
      ? theme.colors.info
      : theme.colors.textSecondary;

  return (
    <TouchableOpacity onPress={onPress}>
      <Card style={styles.gameCard}>
        <Card.Content>
          <View style={styles.cardHeader}>
            <View style={styles.cardTitleContainer}>
              <Text style={styles.gameName} numberOfLines={1}>
                {game.name}
              </Text>
              <View style={[styles.statusBadge, { backgroundColor: statusColor }]}>
                <Text style={styles.statusText}>{game.status.toUpperCase()}</Text>
              </View>
            </View>
          </View>

          <View style={styles.gameInfo}>
            <View style={styles.infoRow}>
              <Avatar.Icon
                size={24}
                icon="chart-timeline-variant"
                style={styles.infoIcon}
              />
              <Text style={styles.infoText}>
                Round {game.current_round} of {game.max_rounds}
              </Text>
            </View>

            <View style={styles.infoRow}>
              <Avatar.Icon
                size={24}
                icon="account-group"
                style={styles.infoIcon}
              />
              <Text style={styles.infoText}>
                {game.player_count || 0} players
              </Text>
            </View>

            <View style={styles.infoRow}>
              <Avatar.Icon size={24} icon="calendar" style={styles.infoIcon} />
              <Text style={styles.infoText}>
                {new Date(game.created_at).toLocaleDateString()}
              </Text>
            </View>
          </View>

          {game.supply_chain_config && (
            <View style={styles.configChip}>
              <Chip
                icon="sitemap"
                mode="outlined"
                compact
                style={styles.chip}
              >
                {game.supply_chain_config.name}
              </Chip>
            </View>
          )}
        </Card.Content>
      </Card>
    </TouchableOpacity>
  );
};

export default function GamesListScreen({ navigation }: any) {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const dispatch = useAppDispatch();
  const { games, loading, page, totalPages } = useAppSelector(
    (state) => state.games
  );

  useEffect(() => {
    loadGames();
  }, [statusFilter]);

  const loadGames = () => {
    dispatch(fetchGames({ page: 1, status: statusFilter || undefined }));
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadGames();
    setRefreshing(false);
  };

  const handleLoadMore = () => {
    if (!loading && page < totalPages) {
      dispatch(fetchGames({ page: page + 1, status: statusFilter || undefined }));
    }
  };

  const handleGamePress = (gameId: number) => {
    navigation.navigate('GameDetail', { gameId });
  };

  const handleCreateGame = () => {
    navigation.navigate('CreateGame');
  };

  // Filter games by search query
  const filteredGames = games.filter((game) =>
    game.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const renderItem = ({ item }: { item: any }) => (
    <GameCard game={item} onPress={() => handleGamePress(item.id)} />
  );

  const renderEmpty = () => (
    <View style={styles.emptyContainer}>
      <Avatar.Icon
        size={80}
        icon="gamepad-variant-outline"
        style={styles.emptyIcon}
      />
      <Text style={styles.emptyTitle}>No Games Found</Text>
      <Text style={styles.emptySubtitle}>
        {statusFilter
          ? `No ${statusFilter} games`
          : 'Create your first game to get started'}
      </Text>
    </View>
  );

  const renderFooter = () => {
    if (!loading) return null;
    return (
      <View style={styles.footerLoader}>
        <ActivityIndicator size="small" color={theme.colors.primary} />
      </View>
    );
  };

  return (
    <View style={styles.container}>
      {/* Search Bar */}
      <Searchbar
        placeholder="Search games..."
        onChangeText={setSearchQuery}
        value={searchQuery}
        style={styles.searchBar}
      />

      {/* Filter Chips */}
      <View style={styles.filtersContainer}>
        {FILTERS.map((filter) => (
          <Chip
            key={filter.value}
            selected={statusFilter === filter.value}
            onPress={() => setStatusFilter(filter.value)}
            style={styles.filterChip}
          >
            {filter.label}
          </Chip>
        ))}
      </View>

      {/* Games List */}
      <FlatList
        data={filteredGames}
        renderItem={renderItem}
        keyExtractor={(item) => item.id.toString()}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
        }
        onEndReached={handleLoadMore}
        onEndReachedThreshold={0.5}
        ListEmptyComponent={!loading ? renderEmpty : null}
        ListFooterComponent={renderFooter}
      />

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
  searchBar: {
    margin: theme.spacing.md,
    elevation: 2,
  },
  filtersContainer: {
    flexDirection: 'row',
    paddingHorizontal: theme.spacing.md,
    paddingBottom: theme.spacing.sm,
    gap: theme.spacing.sm,
  },
  filterChip: {
    marginRight: theme.spacing.xs,
  },
  listContent: {
    padding: theme.spacing.md,
    paddingBottom: 100,
  },
  gameCard: {
    marginBottom: theme.spacing.md,
    elevation: 2,
  },
  cardHeader: {
    marginBottom: theme.spacing.sm,
  },
  cardTitleContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  gameName: {
    fontSize: 18,
    fontWeight: '600',
    color: theme.colors.text,
    flex: 1,
    marginRight: theme.spacing.sm,
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
  gameInfo: {
    marginVertical: theme.spacing.sm,
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: theme.spacing.xs,
  },
  infoIcon: {
    backgroundColor: 'transparent',
    marginRight: theme.spacing.xs,
  },
  infoText: {
    fontSize: 14,
    color: theme.colors.textSecondary,
  },
  configChip: {
    marginTop: theme.spacing.sm,
  },
  chip: {
    alignSelf: 'flex-start',
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: theme.spacing.xl * 2,
  },
  emptyIcon: {
    backgroundColor: theme.colors.disabled,
    marginBottom: theme.spacing.lg,
  },
  emptyTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: theme.colors.text,
    marginBottom: theme.spacing.xs,
  },
  emptySubtitle: {
    fontSize: 14,
    color: theme.colors.textSecondary,
    textAlign: 'center',
  },
  footerLoader: {
    paddingVertical: theme.spacing.md,
  },
  fab: {
    position: 'absolute',
    margin: theme.spacing.md,
    right: 0,
    bottom: 0,
    backgroundColor: theme.colors.primary,
  },
});
