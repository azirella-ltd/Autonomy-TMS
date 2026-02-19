/**
 * Chat Container Component
 * Main chat interface combining message list, input, and suggestions
 * Phase 7 Sprint 2
 */

import React, { useEffect, useState, useCallback } from 'react';
import { View, StyleSheet, KeyboardAvoidingView, Platform } from 'react-native';
import { useTheme, Badge, IconButton } from 'react-native-paper';
import { useAppDispatch, useAppSelector } from '../../store';
import {
  fetchMessages,
  sendMessage,
  markAllRead,
  acceptSuggestion,
  declineSuggestion,
  requestSuggestion,
} from '../../store/slices/chatSlice';
import { chatService } from '../../services/chat';
import ChatMessageList from './ChatMessageList';
import ChatInput from './ChatInput';
import AgentSuggestionCard from './AgentSuggestionCard';

interface ChatContainerProps {
  gameId: number;
  currentUserId: string;
  onClose?: () => void;
}

export default function ChatContainer({
  gameId,
  currentUserId,
  onClose,
}: ChatContainerProps) {
  const theme = useTheme();
  const dispatch = useAppDispatch();

  const messages = useAppSelector((state) => state.chat.messages[gameId] || []);
  const unreadCount = useAppSelector((state) => state.chat.unreadCounts[gameId] || 0);
  const typingIndicators = useAppSelector((state) => state.chat.typingIndicators);
  const suggestions = useAppSelector((state) => state.chat.suggestions[gameId] || []);
  const loading = useAppSelector((state) => state.chat.loading);

  const [showSuggestions, setShowSuggestions] = useState(true);

  // Initialize chat service and fetch messages
  useEffect(() => {
    chatService.initialize();
    chatService.joinGameChat(gameId);

    dispatch(fetchMessages({ gameId }));

    return () => {
      chatService.leaveGameChat(gameId);
    };
  }, [gameId, dispatch]);

  // Mark all messages as read when component mounts or messages change
  useEffect(() => {
    if (unreadCount > 0) {
      dispatch(markAllRead(gameId));
    }
  }, [unreadCount, gameId, dispatch]);

  // Get typing agents
  const typingAgents = Object.entries(typingIndicators)
    .filter(([_, isTyping]) => isTyping)
    .map(([agentId, _]) => agentId);

  // Get pending suggestions (not accepted or declined)
  const pendingSuggestions = suggestions.filter((s) => s.accepted === undefined);

  const handleSendMessage = useCallback(
    (content: string) => {
      dispatch(
        sendMessage({
          gameId,
          senderId: currentUserId,
          senderName: 'You',
          senderType: 'player',
          content,
          type: 'text',
        })
      );
    },
    [gameId, currentUserId, dispatch]
  );

  const handleAcceptSuggestion = useCallback(
    (suggestionId: string) => {
      dispatch(acceptSuggestion({ gameId, suggestionId }));
    },
    [gameId, dispatch]
  );

  const handleDeclineSuggestion = useCallback(
    (suggestionId: string) => {
      dispatch(declineSuggestion({ gameId, suggestionId }));
    },
    [gameId, dispatch]
  );

  const handleRequestSuggestion = useCallback(() => {
    dispatch(requestSuggestion({ gameId }));
  }, [gameId, dispatch]);

  const toggleSuggestions = useCallback(() => {
    setShowSuggestions(!showSuggestions);
  }, [showSuggestions]);

  return (
    <KeyboardAvoidingView
      style={[styles.container, { backgroundColor: theme.colors.background }]}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
    >
      {/* Header */}
      <View style={[styles.header, { backgroundColor: theme.colors.surface }]}>
        <View style={styles.headerLeft}>
          <IconButton
            icon="robot"
            size={24}
            onPress={handleRequestSuggestion}
            disabled={loading}
            accessibilityLabel="Request agent suggestion"
            accessibilityHint="Ask AI agents for order recommendations"
          />
          {pendingSuggestions.length > 0 && (
            <Badge
              style={styles.suggestionBadge}
              accessibilityLabel={`${pendingSuggestions.length} pending suggestions`}
            >
              {pendingSuggestions.length}
            </Badge>
          )}
          <IconButton
            icon={showSuggestions ? 'lightbulb' : 'lightbulb-outline'}
            size={24}
            onPress={toggleSuggestions}
            accessibilityLabel={
              showSuggestions ? 'Hide suggestions' : 'Show suggestions'
            }
          />
        </View>
        {onClose && (
          <IconButton
            icon="close"
            size={24}
            onPress={onClose}
            accessibilityLabel="Close chat"
          />
        )}
      </View>

      {/* Suggestions */}
      {showSuggestions && pendingSuggestions.length > 0 && (
        <View style={styles.suggestionsContainer}>
          {pendingSuggestions.map((suggestion) => (
            <AgentSuggestionCard
              key={suggestion.id}
              suggestion={suggestion}
              onAccept={() => handleAcceptSuggestion(suggestion.id)}
              onDecline={() => handleDeclineSuggestion(suggestion.id)}
              disabled={loading}
            />
          ))}
        </View>
      )}

      {/* Messages */}
      <View style={styles.messagesContainer}>
        <ChatMessageList
          messages={messages}
          currentUserId={currentUserId}
          typingAgents={typingAgents}
          loading={loading}
        />
      </View>

      {/* Input */}
      <ChatInput
        gameId={gameId}
        onSend={handleSendMessage}
        disabled={loading}
      />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 4,
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0, 0, 0, 0.1)',
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  suggestionBadge: {
    position: 'absolute',
    top: 4,
    right: 4,
  },
  suggestionsContainer: {
    maxHeight: '40%',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0, 0, 0, 0.1)',
  },
  messagesContainer: {
    flex: 1,
  },
});
