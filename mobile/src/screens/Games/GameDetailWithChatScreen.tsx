/**
 * Game Detail Screen with A2A Chat
 * Enhanced version with real-time agent collaboration
 * Phase 7 Sprint 2
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
  FAB,
  Badge,
  Portal,
  Modal,
  useTheme,
  ActivityIndicator,
  Chip,
  ProgressBar,
} from 'react-native-paper';
import { useAppDispatch, useAppSelector } from '../../store';
import {
  fetchGameById,
} from '../../store/slices/gamesSlice';
import { ChatContainer } from '../../components/chat';

const { height: SCREEN_HEIGHT } = Dimensions.get('window');

export default function GameDetailWithChatScreen({ route, navigation }: any) {
  const { gameId } = route.params;
  const theme = useTheme();
  const dispatch = useAppDispatch();

  const [refreshing, setRefreshing] = useState(false);
  const [chatVisible, setChatVisible] = useState(false);

  const game = useAppSelector((state) =>
    state.games.games.find((g) => g.id === gameId)
  );
  const user = useAppSelector((state) => state.auth.user);
  const unreadCount = useAppSelector(
    (state) => state.chat.unreadCounts[gameId] || 0
  );
  const loading = useAppSelector((state) => state.games.loading);

  useEffect(() => {
    loadGameData();
  }, [gameId]);

  const loadGameData = () => {
    dispatch(fetchGameById(gameId));
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadGameData();
    setRefreshing(false);
  };

  const toggleChat = () => {
    setChatVisible(!chatVisible);
  };

  if (loading && !game) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
      </View>
    );
  }

  if (!game) {
    return (
      <View style={styles.errorContainer}>
        <Text style={styles.errorText}>Game not found</Text>
      </View>
    );
  }

  const progress =
    game.max_rounds > 0 ? game.current_round / game.max_rounds : 0;

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
        }
      >
        {/* Game Header */}
        <Card style={styles.headerCard}>
          <Card.Content>
            <Text style={styles.gameName}>{game.name}</Text>
            <View style={styles.statusRow}>
              <Chip
                icon={
                  game.status === 'active'
                    ? 'play-circle'
                    : game.status === 'completed'
                    ? 'check-circle'
                    : 'pause-circle'
                }
                style={styles.statusChip}
              >
                {game.status}
              </Chip>
              <Text style={styles.roundText}>
                Round {game.current_round} of {game.max_rounds}
              </Text>
            </View>
            <ProgressBar
              progress={progress}
              color={theme.colors.primary}
              style={styles.progressBar}
            />
          </Card.Content>
        </Card>

        {/* Supply Chain Config */}
        <Card style={styles.card}>
          <Card.Title
            title="Supply Chain Configuration"
            titleStyle={styles.cardTitle}
          />
          <Card.Content>
            <Text style={styles.configName}>{game.config.name}</Text>
            <Text style={styles.configDesc}>{game.config.description}</Text>
          </Card.Content>
        </Card>

        {/* Players */}
        <Card style={styles.card}>
          <Card.Title title="Players" titleStyle={styles.cardTitle} />
          <Card.Content>
            {game.players.map((player, index) => (
              <View key={index} style={styles.playerRow}>
                <View style={styles.playerInfo}>
                  <Text style={styles.playerNode}>
                    {player.is_ai ? '🤖' : '👤'} {player.node_name}
                  </Text>
                  <Text style={styles.playerType}>
                    {player.is_ai ? 'AI Agent' : 'Human Player'}
                  </Text>
                </View>
              </View>
            ))}
          </Card.Content>
        </Card>

        {/* Game Actions */}
        <Card style={styles.card}>
          <Card.Content>
            <Button
              mode="contained"
              onPress={() => {
                /* Handle play round */
              }}
              disabled={game.status !== 'active'}
              style={styles.actionButton}
            >
              Play Round
            </Button>
            <Button
              mode="outlined"
              onPress={() => navigation.navigate('Analytics', { gameId })}
              style={styles.actionButton}
            >
              View Analytics
            </Button>
          </Card.Content>
        </Card>

        {/* Chat Hint */}
        <Card style={styles.hintCard}>
          <Card.Content>
            <Text style={styles.hintText}>
              💬 Need advice? Chat with AI agents for real-time suggestions!
            </Text>
          </Card.Content>
        </Card>
      </ScrollView>

      {/* Chat FAB */}
      <FAB
        icon="message"
        style={[
          styles.fab,
          { backgroundColor: theme.colors.primary },
        ]}
        onPress={toggleChat}
        label={unreadCount > 0 ? `${unreadCount}` : undefined}
        accessibilityLabel="Open chat with AI agents"
        accessibilityHint="Chat with AI agents for suggestions and advice"
      />

      {/* Chat Modal */}
      <Portal>
        <Modal
          visible={chatVisible}
          onDismiss={toggleChat}
          contentContainerStyle={[
            styles.modalContent,
            { backgroundColor: theme.colors.background },
          ]}
        >
          <ChatContainer
            gameId={gameId}
            currentUserId={`player:${user?.id}`}
            onClose={toggleChat}
          />
        </Modal>
      </Portal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 80, // Space for FAB
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
    padding: 32,
  },
  errorText: {
    fontSize: 16,
    textAlign: 'center',
  },
  headerCard: {
    margin: 12,
  },
  gameName: {
    fontSize: 24,
    fontWeight: '700',
    marginBottom: 8,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  statusChip: {
    marginRight: 8,
  },
  roundText: {
    fontSize: 14,
  },
  progressBar: {
    height: 8,
    borderRadius: 4,
  },
  card: {
    margin: 12,
    marginTop: 0,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: '600',
  },
  configName: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 4,
  },
  configDesc: {
    fontSize: 14,
    opacity: 0.7,
  },
  playerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 8,
  },
  playerInfo: {
    flex: 1,
  },
  playerNode: {
    fontSize: 16,
    fontWeight: '600',
  },
  playerType: {
    fontSize: 12,
    opacity: 0.7,
  },
  actionButton: {
    marginVertical: 4,
  },
  hintCard: {
    margin: 12,
    marginTop: 0,
    backgroundColor: 'rgba(33, 150, 243, 0.1)',
  },
  hintText: {
    fontSize: 14,
    textAlign: 'center',
  },
  fab: {
    position: 'absolute',
    margin: 16,
    right: 0,
    bottom: 0,
  },
  modalContent: {
    margin: 20,
    height: SCREEN_HEIGHT * 0.8,
    borderRadius: 8,
    overflow: 'hidden',
  },
});
