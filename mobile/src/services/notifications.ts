/**
 * Push Notifications Service
 * Phase 7 Sprint 1: Mobile Application
 */

import messaging, { FirebaseMessagingTypes } from '@react-native-firebase/messaging';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform, Alert } from 'react-native';
import { apiClient } from './api';

const FCM_TOKEN_KEY = 'fcm_token';

class NotificationsService {
  private token: string | null = null;

  /**
   * Initialize push notifications
   */
  async initialize(): Promise<void> {
    try {
      // Request permission
      const hasPermission = await this.requestPermission();
      if (!hasPermission) {
        console.log('Push notification permission denied');
        return;
      }

      // Get FCM token
      await this.getToken();

      // Setup message handlers
      this.setupMessageHandlers();

      console.log('Push notifications initialized');
    } catch (error) {
      console.error('Failed to initialize push notifications:', error);
    }
  }

  /**
   * Request notification permission
   */
  async requestPermission(): Promise<boolean> {
    try {
      const authStatus = await messaging().requestPermission();
      const enabled =
        authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
        authStatus === messaging.AuthorizationStatus.PROVISIONAL;

      if (enabled) {
        console.log('Notification permission granted:', authStatus);
      }

      return enabled;
    } catch (error) {
      console.error('Permission request failed:', error);
      return false;
    }
  }

  /**
   * Get FCM token and register with backend
   */
  async getToken(): Promise<string | null> {
    try {
      // Check if token exists in storage
      const storedToken = await AsyncStorage.getItem(FCM_TOKEN_KEY);
      if (storedToken) {
        this.token = storedToken;
        console.log('Using stored FCM token');
        return storedToken;
      }

      // Get new token from Firebase
      const token = await messaging().getToken();
      if (token) {
        this.token = token;
        await AsyncStorage.setItem(FCM_TOKEN_KEY, token);

        // Register token with backend
        await this.registerToken(token);

        console.log('FCM token obtained:', token);
        return token;
      }

      return null;
    } catch (error) {
      console.error('Failed to get FCM token:', error);
      return null;
    }
  }

  /**
   * Register FCM token with backend
   */
  async registerToken(token: string): Promise<void> {
    try {
      await apiClient.registerFCMToken(token, Platform.OS);
      console.log('FCM token registered with backend');
    } catch (error) {
      console.error('Failed to register FCM token with backend:', error);
    }
  }

  /**
   * Unregister FCM token from backend
   */
  async unregisterToken(): Promise<void> {
    try {
      if (this.token) {
        await apiClient.unregisterFCMToken(this.token);
        await AsyncStorage.removeItem(FCM_TOKEN_KEY);
        this.token = null;
        console.log('FCM token unregistered');
      }
    } catch (error) {
      console.error('Failed to unregister FCM token:', error);
    }
  }

  /**
   * Setup message handlers
   */
  private setupMessageHandlers(): void {
    // Foreground message handler
    messaging().onMessage(async (remoteMessage) => {
      console.log('Foreground notification received:', remoteMessage);
      this.handleForegroundMessage(remoteMessage);
    });

    // Background message handler (already setup in index.js)
    messaging().setBackgroundMessageHandler(async (remoteMessage) => {
      console.log('Background notification received:', remoteMessage);
      // Handle background notification
    });

    // Notification opened app (from quit state)
    messaging()
      .getInitialNotification()
      .then((remoteMessage) => {
        if (remoteMessage) {
          console.log('Notification opened app from quit state:', remoteMessage);
          this.handleNotificationOpen(remoteMessage);
        }
      });

    // Notification opened app (from background)
    messaging().onNotificationOpenedApp((remoteMessage) => {
      console.log('Notification opened app from background:', remoteMessage);
      this.handleNotificationOpen(remoteMessage);
    });

    // Token refresh handler
    messaging().onTokenRefresh(async (token) => {
      console.log('FCM token refreshed:', token);
      this.token = token;
      await AsyncStorage.setItem(FCM_TOKEN_KEY, token);
      await this.registerToken(token);
    });
  }

  /**
   * Handle foreground notification
   */
  private handleForegroundMessage(
    remoteMessage: FirebaseMessagingTypes.RemoteMessage
  ): void {
    const { notification, data } = remoteMessage;

    if (notification) {
      // Show local notification or in-app alert
      Alert.alert(
        notification.title || 'Notification',
        notification.body || '',
        [
          { text: 'Dismiss', style: 'cancel' },
          {
            text: 'View',
            onPress: () => this.handleNotificationOpen(remoteMessage),
          },
        ]
      );
    }

    // Handle data-only message
    if (data) {
      this.handleNotificationData(data);
    }
  }

  /**
   * Handle notification data
   */
  private handleNotificationData(data: { [key: string]: string }): void {
    // Handle different notification types
    switch (data.type) {
      case 'round_completed':
        console.log('Round completed notification:', data);
        // Dispatch Redux action or trigger WebSocket sync
        break;

      case 'game_started':
        console.log('Game started notification:', data);
        break;

      case 'game_ended':
        console.log('Game ended notification:', data);
        break;

      case 'your_turn':
        console.log('Your turn notification:', data);
        break;

      default:
        console.log('Unknown notification type:', data);
    }
  }

  /**
   * Handle notification tap (deep linking)
   */
  private handleNotificationOpen(
    remoteMessage: FirebaseMessagingTypes.RemoteMessage
  ): void {
    const { data } = remoteMessage;

    if (!data) return;

    // Navigate based on notification type
    // This should integrate with React Navigation
    // For now, just log the action
    switch (data.type) {
      case 'round_completed':
      case 'game_started':
      case 'game_ended':
      case 'your_turn':
        console.log('Navigate to game:', data.game_id);
        // navigation.navigate('Games', {
        //   screen: 'GameDetail',
        //   params: { gameId: parseInt(data.game_id) }
        // });
        break;

      case 'new_template':
        console.log('Navigate to templates');
        // navigation.navigate('Templates');
        break;

      default:
        console.log('Navigate to dashboard');
        // navigation.navigate('Dashboard');
    }
  }

  /**
   * Check notification permission status
   */
  async checkPermission(): Promise<boolean> {
    const authStatus = await messaging().hasPermission();
    return (
      authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
      authStatus === messaging.AuthorizationStatus.PROVISIONAL
    );
  }

  /**
   * Get badge count (iOS only)
   */
  async getBadgeCount(): Promise<number> {
    if (Platform.OS === 'ios') {
      return messaging().getAPNSToken() ? 0 : 0; // Placeholder
    }
    return 0;
  }

  /**
   * Set badge count (iOS only)
   */
  async setBadgeCount(count: number): Promise<void> {
    if (Platform.OS === 'ios') {
      // Set badge count via native module
      console.log('Set badge count:', count);
    }
  }

  /**
   * Clear all notifications
   */
  async clearNotifications(): Promise<void> {
    if (Platform.OS === 'android') {
      // Clear Android notifications
      console.log('Clear Android notifications');
    }
  }

  /**
   * Schedule local notification (for reminders)
   */
  async scheduleLocalNotification(
    title: string,
    body: string,
    data?: any,
    scheduledTime?: Date
  ): Promise<void> {
    // This would use a local notification library
    console.log('Schedule local notification:', { title, body, scheduledTime });
  }
}

// Export singleton instance
export const notificationsService = new NotificationsService();
export default notificationsService;
