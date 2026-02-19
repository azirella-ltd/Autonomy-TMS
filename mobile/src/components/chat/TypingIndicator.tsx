/**
 * Typing Indicator Component
 * Shows when agents are typing
 * Phase 7 Sprint 2
 */

import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated } from 'react-native';
import { Text, useTheme } from 'react-native-paper';
import { chatService } from '../../services/chat';

interface TypingIndicatorProps {
  agents: string[];
}

export default function TypingIndicator({ agents }: TypingIndicatorProps) {
  const theme = useTheme();
  const dot1 = useRef(new Animated.Value(0)).current;
  const dot2 = useRef(new Animated.Value(0)).current;
  const dot3 = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const animations = [
      Animated.loop(
        Animated.sequence([
          Animated.timing(dot1, {
            toValue: 1,
            duration: 400,
            useNativeDriver: true,
          }),
          Animated.timing(dot1, {
            toValue: 0,
            duration: 400,
            useNativeDriver: true,
          }),
        ])
      ),
      Animated.loop(
        Animated.sequence([
          Animated.delay(200),
          Animated.timing(dot2, {
            toValue: 1,
            duration: 400,
            useNativeDriver: true,
          }),
          Animated.timing(dot2, {
            toValue: 0,
            duration: 400,
            useNativeDriver: true,
          }),
        ])
      ),
      Animated.loop(
        Animated.sequence([
          Animated.delay(400),
          Animated.timing(dot3, {
            toValue: 1,
            duration: 400,
            useNativeDriver: true,
          }),
          Animated.timing(dot3, {
            toValue: 0,
            duration: 400,
            useNativeDriver: true,
          }),
        ])
      ),
    ];

    Animated.parallel(animations).start();

    return () => {
      animations.forEach((anim) => anim.stop());
    };
  }, [dot1, dot2, dot3]);

  if (agents.length === 0) {
    return null;
  }

  const agentNames = agents.map((agentId) => chatService.getAgentDisplayName(agentId)).join(', ');
  const agentEmojis = agents.map((agentId) => {
    const name = chatService.getAgentDisplayName(agentId);
    return chatService.getAgentEmoji(name);
  });

  return (
    <View
      style={styles.container}
      accessible={true}
      accessibilityLabel={`${agentNames} ${agents.length === 1 ? 'is' : 'are'} typing`}
      accessibilityLiveRegion="polite"
    >
      <View style={styles.content}>
        <Text style={[styles.text, { color: theme.colors.onSurfaceVariant }]}>
          {agentEmojis.join(' ')} {agentNames} {agents.length === 1 ? 'is' : 'are'} typing
        </Text>
        <View style={styles.dotsContainer}>
          <Animated.View
            style={[
              styles.dot,
              {
                backgroundColor: theme.colors.onSurfaceVariant,
                opacity: dot1,
              },
            ]}
          />
          <Animated.View
            style={[
              styles.dot,
              {
                backgroundColor: theme.colors.onSurfaceVariant,
                opacity: dot2,
              },
            ]}
          />
          <Animated.View
            style={[
              styles.dot,
              {
                backgroundColor: theme.colors.onSurfaceVariant,
                opacity: dot3,
              },
            ]}
          />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  text: {
    fontSize: 14,
    fontStyle: 'italic',
    marginRight: 8,
  },
  dotsContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginHorizontal: 2,
  },
});
