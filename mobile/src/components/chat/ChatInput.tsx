/**
 * Chat Input Component
 * Message input with send button and typing indicator
 * Phase 7 Sprint 2
 */

import React, { useState, useCallback } from 'react';
import { View, StyleSheet, TextInput as RNTextInput } from 'react-native';
import { TextInput, IconButton, useTheme } from 'react-native-paper';
import { chatService } from '../../services/chat';

interface ChatInputProps {
  gameId: number;
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export default function ChatInput({
  gameId,
  onSend,
  disabled = false,
  placeholder = 'Type a message...',
}: ChatInputProps) {
  const theme = useTheme();
  const [message, setMessage] = useState('');
  const [isTyping, setIsTyping] = useState(false);

  let typingTimeout: NodeJS.Timeout | null = null;

  const handleChangeText = useCallback(
    (text: string) => {
      setMessage(text);

      // Send typing indicator
      if (text.length > 0 && !isTyping) {
        setIsTyping(true);
        chatService.sendTypingIndicator(gameId, true);
      }

      // Clear previous timeout
      if (typingTimeout) {
        clearTimeout(typingTimeout);
      }

      // Stop typing indicator after 2 seconds of no input
      typingTimeout = setTimeout(() => {
        setIsTyping(false);
        chatService.sendTypingIndicator(gameId, false);
      }, 2000);
    },
    [gameId, isTyping]
  );

  const handleSend = useCallback(() => {
    const trimmedMessage = message.trim();
    if (trimmedMessage.length === 0) {
      return;
    }

    // Clear typing indicator
    if (isTyping) {
      setIsTyping(false);
      chatService.sendTypingIndicator(gameId, false);
    }

    // Send message
    onSend(trimmedMessage);

    // Clear input
    setMessage('');
  }, [message, gameId, isTyping, onSend]);

  const handleSubmitEditing = useCallback(() => {
    handleSend();
  }, [handleSend]);

  return (
    <View
      style={[styles.container, { backgroundColor: theme.colors.surface }]}
      accessible={false}
    >
      <TextInput
        value={message}
        onChangeText={handleChangeText}
        onSubmitEditing={handleSubmitEditing}
        placeholder={placeholder}
        mode="outlined"
        disabled={disabled}
        multiline
        maxLength={500}
        style={styles.input}
        contentStyle={styles.inputContent}
        outlineStyle={styles.inputOutline}
        returnKeyType="send"
        blurOnSubmit={false}
        accessibilityLabel="Message input"
        accessibilityHint="Type your message to the agent"
        right={
          <TextInput.Icon
            icon="send"
            disabled={disabled || message.trim().length === 0}
            onPress={handleSend}
            accessibilityLabel="Send message"
            accessibilityHint="Send the message"
            color={
              message.trim().length > 0
                ? theme.colors.primary
                : theme.colors.onSurfaceDisabled
            }
          />
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderTopWidth: 1,
    borderTopColor: 'rgba(0, 0, 0, 0.1)',
  },
  input: {
    backgroundColor: 'transparent',
    maxHeight: 120,
  },
  inputContent: {
    paddingRight: 48,
  },
  inputOutline: {
    borderRadius: 24,
  },
});
