/**
 * Chat Message List Component
 * Scrollable list of chat messages with date separators
 * Phase 7 Sprint 2
 */

import React, { useRef, useEffect } from 'react';
import { FlatList, View, StyleSheet } from 'react-native';
import { Text, Divider, useTheme } from 'react-native-paper';
import { ChatMessage as ChatMessageType } from '../../store/slices/chatSlice';
import ChatMessage from './ChatMessage';
import TypingIndicator from './TypingIndicator';

interface ChatMessageListProps {
  messages: ChatMessageType[];
  currentUserId: string;
  typingAgents?: string[];
  onLoadMore?: () => void;
  loading?: boolean;
}

export default function ChatMessageList({
  messages,
  currentUserId,
  typingAgents = [],
  onLoadMore,
  loading = false,
}: ChatMessageListProps) {
  const theme = useTheme();
  const flatListRef = useRef<FlatList>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: true });
      }, 100);
    }
  }, [messages.length]);

  const groupedMessages = groupMessagesByDate(messages);

  const renderDateSeparator = (date: string) => (
    <View
      style={styles.dateSeparatorContainer}
      accessible={true}
      accessibilityRole="header"
      accessibilityLabel={`Messages from ${date}`}
    >
      <Divider style={styles.dateSeparatorLine} />
      <Text style={[styles.dateSeparatorText, { color: theme.colors.onSurfaceVariant }]}>
        {date}
      </Text>
      <Divider style={styles.dateSeparatorLine} />
    </View>
  );

  const renderMessage = ({ item }: { item: ChatMessageType }) => {
    const isCurrentUser = item.senderId === currentUserId;
    return <ChatMessage message={item} isCurrentUser={isCurrentUser} />;
  };

  const renderItem = ({ item, index }: { item: any; index: number }) => {
    if (item.type === 'date') {
      return renderDateSeparator(item.date);
    }
    return renderMessage({ item });
  };

  const renderFooter = () => {
    if (typingAgents.length > 0) {
      return <TypingIndicator agents={typingAgents} />;
    }
    return null;
  };

  const renderEmpty = () => (
    <View style={styles.emptyContainer}>
      <Text style={[styles.emptyText, { color: theme.colors.onSurfaceVariant }]}>
        💬 Start a conversation with the AI agents
      </Text>
      <Text style={[styles.emptySubtext, { color: theme.colors.onSurfaceVariant }]}>
        Ask for suggestions, advice, or analysis
      </Text>
    </View>
  );

  // Flatten grouped messages with date separators
  const flattenedMessages: any[] = [];
  Object.entries(groupedMessages).forEach(([date, msgs]) => {
    flattenedMessages.push({ type: 'date', date, id: `date-${date}` });
    msgs.forEach((msg) => flattenedMessages.push(msg));
  });

  return (
    <FlatList
      ref={flatListRef}
      data={flattenedMessages}
      renderItem={renderItem}
      keyExtractor={(item) => item.id}
      contentContainerStyle={styles.listContent}
      onEndReached={onLoadMore}
      onEndReachedThreshold={0.5}
      ListFooterComponent={renderFooter}
      ListEmptyComponent={renderEmpty}
      showsVerticalScrollIndicator={true}
      maintainVisibleContentPosition={{
        minIndexForVisible: 0,
        autoscrollToTopThreshold: 10,
      }}
      accessibilityLabel="Chat messages"
    />
  );
}

// Helper function to group messages by date
function groupMessagesByDate(messages: ChatMessageType[]): Record<string, ChatMessageType[]> {
  const grouped: Record<string, ChatMessageType[]> = {};

  messages.forEach((message) => {
    const date = formatDate(new Date(message.timestamp));
    if (!grouped[date]) {
      grouped[date] = [];
    }
    grouped[date].push(message);
  });

  return grouped;
}

// Helper function to format date
function formatDate(date: Date): string {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  if (date.toDateString() === today.toDateString()) {
    return 'Today';
  } else if (date.toDateString() === yesterday.toDateString()) {
    return 'Yesterday';
  } else {
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: date.getFullYear() !== today.getFullYear() ? 'numeric' : undefined,
    });
  }
}

const styles = StyleSheet.create({
  listContent: {
    paddingVertical: 8,
    flexGrow: 1,
  },
  dateSeparatorContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 16,
    marginHorizontal: 16,
  },
  dateSeparatorLine: {
    flex: 1,
  },
  dateSeparatorText: {
    marginHorizontal: 12,
    fontSize: 12,
    fontWeight: '600',
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 32,
    paddingVertical: 64,
  },
  emptyText: {
    fontSize: 16,
    fontWeight: '600',
    textAlign: 'center',
    marginBottom: 8,
  },
  emptySubtext: {
    fontSize: 14,
    textAlign: 'center',
  },
});
