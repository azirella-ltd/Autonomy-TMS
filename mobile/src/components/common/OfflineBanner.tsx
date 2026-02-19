/**
 * Offline Banner Component
 * Phase 7 Sprint 1: Mobile Application
 */

import React, { useEffect, useState } from 'react';
import { View, StyleSheet, Animated } from 'react-native';
import { Banner, Text } from 'react-native-paper';
import { useAppSelector } from '../../store';
import { theme } from '../../theme';
import { offlineService } from '../../services/offline';

export default function OfflineBanner() {
  const [visible, setVisible] = useState(false);
  const [queueSize, setQueueSize] = useState(0);
  const slideAnim = useState(new Animated.Value(-100))[0];

  const networkStatus = useAppSelector((state) => state.ui.networkStatus);

  useEffect(() => {
    const isOffline = networkStatus === 'offline';
    setVisible(isOffline);

    if (isOffline) {
      // Update queue size
      const size = offlineService.getQueueSize();
      setQueueSize(size);

      // Slide down animation
      Animated.spring(slideAnim, {
        toValue: 0,
        useNativeDriver: true,
        tension: 50,
        friction: 7,
      }).start();
    } else {
      // Slide up animation
      Animated.timing(slideAnim, {
        toValue: -100,
        duration: 300,
        useNativeDriver: true,
      }).start(() => {
        setQueueSize(0);
      });
    }
  }, [networkStatus, slideAnim]);

  if (!visible && queueSize === 0) {
    return null;
  }

  return (
    <Animated.View
      style={[
        styles.container,
        {
          transform: [{ translateY: slideAnim }],
        },
      ]}
    >
      <Banner
        visible={true}
        icon="wifi-off"
        style={styles.banner}
        contentStyle={styles.content}
      >
        <View style={styles.textContainer}>
          <Text style={styles.title}>You're offline</Text>
          <Text style={styles.subtitle}>
            {queueSize > 0
              ? `${queueSize} action${queueSize > 1 ? 's' : ''} will sync when reconnected`
              : 'Changes will sync when you reconnect'}
          </Text>
        </View>
      </Banner>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 1000,
    elevation: 1000,
  },
  banner: {
    backgroundColor: theme.colors.warning,
  },
  content: {
    paddingVertical: theme.spacing.sm,
  },
  textContainer: {
    flex: 1,
  },
  title: {
    fontSize: 14,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 2,
  },
  subtitle: {
    fontSize: 12,
    color: '#fff',
    opacity: 0.9,
  },
});
