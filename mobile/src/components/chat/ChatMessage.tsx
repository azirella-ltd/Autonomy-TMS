/**
 * Chat Message Component
 * Individual message bubble for player or agent messages
 * Phase 7 Sprint 2
 */

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Text, Avatar, useTheme } from 'react-native-paper';
import { ChatMessage as ChatMessageType } from '../../store/slices/chatSlice';
import { chatService } from '../../services/chat';

interface ChatMessageProps {
  message: ChatMessageType;
  isCurrentUser: boolean;
}

export default function ChatMessage({ message, isCurrentUser }: ChatMessageProps) {
  const theme = useTheme();

  const agentEmoji = message.senderType === 'agent'
    ? chatService.getAgentEmoji(message.senderName)
    : null;

  const messageStyle = isCurrentUser
    ? [styles.messageBubble, styles.userMessage, { backgroundColor: theme.colors.primary }]
    : [styles.messageBubble, styles.agentMessage, { backgroundColor: theme.colors.surfaceVariant }];

  const textStyle = isCurrentUser
    ? [styles.messageText, { color: theme.colors.onPrimary }]
    : [styles.messageText, { color: theme.colors.onSurface }];

  return (
    <View
      style={[
        styles.container,
        isCurrentUser ? styles.userContainer : styles.agentContainer,
      ]}
      accessible={true}
      accessibilityLabel={`Message from ${message.senderName}: ${message.content}`}
      accessibilityRole="text"
    >
      {/* Agent Avatar */}
      {!isCurrentUser && message.senderType === 'agent' && (
        <Avatar.Text
          size={32}
          label={agentEmoji || '🤖'}
          style={[styles.avatar, { backgroundColor: theme.colors.secondaryContainer }]}
        />
      )}

      {/* Message Bubble */}
      <View style={messageStyle}>
        {/* Sender Name (for agents) */}
        {!isCurrentUser && (
          <Text style={[styles.senderName, { color: theme.colors.primary }]}>
            {agentEmoji} {message.senderName}
          </Text>
        )}

        {/* Message Content */}
        <Text style={textStyle}>{chatService.formatMessage(message)}</Text>

        {/* Metadata (for suggestions and analysis) */}
        {message.metadata && message.type === 'suggestion' && message.metadata.suggestion && (
          <View style={styles.metadata}>
            <Text style={[styles.metadataText, textStyle]}>
              Order: {message.metadata.suggestion.orderQuantity} units
            </Text>
            <Text style={[styles.metadataText, textStyle]}>
              Confidence: {chatService.formatConfidence(message.metadata.suggestion.confidence)}
            </Text>
          </View>
        )}

        {message.metadata && message.type === 'analysis' && message.metadata.analysis && (
          <View style={styles.metadata}>
            <Text style={[styles.metadataText, textStyle]}>
              {message.metadata.analysis.metric}: {message.metadata.analysis.value}
            </Text>
            <Text style={[styles.metadataText, textStyle]}>
              Trend: {message.metadata.analysis.trend === 'up' ? '📈' : message.metadata.analysis.trend === 'down' ? '📉' : '➡️'}
            </Text>
          </View>
        )}

        {/* Timestamp and Status */}
        <View style={styles.footer}>
          <Text style={[styles.timestamp, textStyle]}>
            {chatService.getRelativeTime(message.timestamp)}
          </Text>

          {isCurrentUser && (
            <Text style={[styles.status, textStyle]}>
              {message.read ? '✓✓' : message.delivered ? '✓' : '⏳'}
            </Text>
          )}
        </View>
      </View>

      {/* User Avatar (placeholder) */}
      {isCurrentUser && (
        <Avatar.Text
          size={32}
          label="You"
          style={[styles.avatar, { backgroundColor: theme.colors.primaryContainer }]}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    marginVertical: 4,
    marginHorizontal: 12,
    alignItems: 'flex-end',
  },
  userContainer: {
    justifyContent: 'flex-end',
  },
  agentContainer: {
    justifyContent: 'flex-start',
  },
  avatar: {
    marginHorizontal: 4,
  },
  messageBubble: {
    maxWidth: '70%',
    borderRadius: 16,
    padding: 12,
  },
  userMessage: {
    borderBottomRightRadius: 4,
  },
  agentMessage: {
    borderBottomLeftRadius: 4,
  },
  senderName: {
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 4,
  },
  messageText: {
    fontSize: 15,
    lineHeight: 20,
  },
  metadata: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.3)',
  },
  metadataText: {
    fontSize: 12,
    marginTop: 2,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 4,
  },
  timestamp: {
    fontSize: 10,
    opacity: 0.7,
  },
  status: {
    fontSize: 10,
    opacity: 0.7,
    marginLeft: 4,
  },
});
