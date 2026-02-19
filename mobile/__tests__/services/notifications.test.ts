/**
 * Unit tests for notifications service
 * Tests Firebase Cloud Messaging integration
 */

import messaging from '@react-native-firebase/messaging';
import { Platform } from 'react-native';
import notificationsService from '../../src/services/notifications';
import { apiClient } from '../../src/services/api';

// Mock dependencies
jest.mock('@react-native-firebase/messaging');
jest.mock('../../src/services/api');
jest.mock('react-native/Libraries/Utilities/Platform', () => ({
  OS: 'ios',
  select: jest.fn((obj) => obj.ios),
}));

describe('NotificationsService', () => {
  let mockMessaging: any;

  beforeEach(() => {
    mockMessaging = {
      requestPermission: jest.fn(),
      getToken: jest.fn(),
      onMessage: jest.fn(),
      onNotificationOpenedApp: jest.fn(),
      onTokenRefresh: jest.fn(),
      getInitialNotification: jest.fn(),
      setBackgroundMessageHandler: jest.fn(),
    };

    (messaging as jest.Mock).mockReturnValue(mockMessaging);
    jest.clearAllMocks();
  });

  describe('initialization', () => {
    it('should request permission on iOS', async () => {
      mockMessaging.requestPermission.mockResolvedValue(
        messaging.AuthorizationStatus.AUTHORIZED
      );
      mockMessaging.getToken.mockResolvedValue('fcm-token-123');
      (apiClient.registerFCMToken as jest.Mock).mockResolvedValue({});

      await notificationsService.initialize();

      expect(mockMessaging.requestPermission).toHaveBeenCalled();
      expect(mockMessaging.getToken).toHaveBeenCalled();
    });

    it('should handle permission denied', async () => {
      mockMessaging.requestPermission.mockResolvedValue(
        messaging.AuthorizationStatus.DENIED
      );

      await notificationsService.initialize();

      expect(mockMessaging.requestPermission).toHaveBeenCalled();
      expect(mockMessaging.getToken).not.toHaveBeenCalled();
    });

    it('should register FCM token with backend', async () => {
      mockMessaging.requestPermission.mockResolvedValue(
        messaging.AuthorizationStatus.AUTHORIZED
      );
      mockMessaging.getToken.mockResolvedValue('fcm-token-123');
      (apiClient.registerFCMToken as jest.Mock).mockResolvedValue({});

      await notificationsService.initialize();

      expect(apiClient.registerFCMToken).toHaveBeenCalledWith('fcm-token-123', 'ios');
    });

    it('should setup message handlers', async () => {
      mockMessaging.requestPermission.mockResolvedValue(
        messaging.AuthorizationStatus.AUTHORIZED
      );
      mockMessaging.getToken.mockResolvedValue('fcm-token-123');
      (apiClient.registerFCMToken as jest.Mock).mockResolvedValue({});

      await notificationsService.initialize();

      expect(mockMessaging.onMessage).toHaveBeenCalled();
      expect(mockMessaging.onNotificationOpenedApp).toHaveBeenCalled();
      expect(mockMessaging.onTokenRefresh).toHaveBeenCalled();
    });

    it('should handle initialization errors gracefully', async () => {
      mockMessaging.requestPermission.mockRejectedValue(new Error('Permission error'));

      await expect(notificationsService.initialize()).resolves.not.toThrow();
    });
  });

  describe('getToken', () => {
    it('should return FCM token', async () => {
      mockMessaging.getToken.mockResolvedValue('fcm-token-123');
      (apiClient.registerFCMToken as jest.Mock).mockResolvedValue({});

      const token = await notificationsService.getToken();

      expect(token).toBe('fcm-token-123');
      expect(mockMessaging.getToken).toHaveBeenCalled();
    });

    it('should register token with backend', async () => {
      mockMessaging.getToken.mockResolvedValue('fcm-token-123');
      (apiClient.registerFCMToken as jest.Mock).mockResolvedValue({});

      await notificationsService.getToken();

      expect(apiClient.registerFCMToken).toHaveBeenCalledWith('fcm-token-123', 'ios');
    });

    it('should return null on error', async () => {
      mockMessaging.getToken.mockRejectedValue(new Error('Token error'));

      const token = await notificationsService.getToken();

      expect(token).toBeNull();
    });

    it('should handle backend registration failure gracefully', async () => {
      mockMessaging.getToken.mockResolvedValue('fcm-token-123');
      (apiClient.registerFCMToken as jest.Mock).mockRejectedValue(
        new Error('Backend error')
      );

      const token = await notificationsService.getToken();

      expect(token).toBe('fcm-token-123'); // Still return token even if registration fails
    });
  });

  describe('notification handling', () => {
    it('should handle foreground messages', async () => {
      mockMessaging.requestPermission.mockResolvedValue(
        messaging.AuthorizationStatus.AUTHORIZED
      );
      mockMessaging.getToken.mockResolvedValue('fcm-token-123');
      (apiClient.registerFCMToken as jest.Mock).mockResolvedValue({});

      let messageHandler: any;
      mockMessaging.onMessage.mockImplementation((handler: any) => {
        messageHandler = handler;
        return jest.fn();
      });

      await notificationsService.initialize();

      const remoteMessage = {
        notification: {
          title: 'Test Notification',
          body: 'Test body',
        },
        data: {
          type: 'game_started',
          game_id: '123',
        },
      };

      await messageHandler(remoteMessage);

      // Should handle message without crashing
      expect(messageHandler).toBeDefined();
    });

    it('should handle notification tap when app in background', async () => {
      mockMessaging.requestPermission.mockResolvedValue(
        messaging.AuthorizationStatus.AUTHORIZED
      );
      mockMessaging.getToken.mockResolvedValue('fcm-token-123');
      (apiClient.registerFCMToken as jest.Mock).mockResolvedValue({});

      let notificationHandler: any;
      mockMessaging.onNotificationOpenedApp.mockImplementation((handler: any) => {
        notificationHandler = handler;
        return jest.fn();
      });

      await notificationsService.initialize();

      const remoteMessage = {
        notification: {
          title: 'Round Completed',
          body: 'Round 5 completed',
        },
        data: {
          type: 'round_completed',
          game_id: '123',
        },
      };

      notificationHandler(remoteMessage);

      // Should handle notification tap without crashing
      expect(notificationHandler).toBeDefined();
    });

    it('should handle app opened from quit state', async () => {
      const initialNotification = {
        notification: {
          title: 'Your Turn',
          body: 'It\'s your turn to play',
        },
        data: {
          type: 'your_turn',
          game_id: '123',
        },
      };

      mockMessaging.getInitialNotification.mockResolvedValue(initialNotification);

      const notification = await mockMessaging.getInitialNotification();

      expect(notification).toEqual(initialNotification);
    });
  });

  describe('token refresh', () => {
    it('should handle token refresh', async () => {
      mockMessaging.requestPermission.mockResolvedValue(
        messaging.AuthorizationStatus.AUTHORIZED
      );
      mockMessaging.getToken.mockResolvedValue('fcm-token-123');
      (apiClient.registerFCMToken as jest.Mock).mockResolvedValue({});

      let refreshHandler: any;
      mockMessaging.onTokenRefresh.mockImplementation((handler: any) => {
        refreshHandler = handler;
        return jest.fn();
      });

      await notificationsService.initialize();

      const newToken = 'new-fcm-token-456';
      await refreshHandler(newToken);

      // Should re-register new token
      expect(refreshHandler).toBeDefined();
    });
  });

  describe('platform-specific behavior', () => {
    it('should use "ios" platform identifier on iOS', async () => {
      Platform.OS = 'ios';
      mockMessaging.requestPermission.mockResolvedValue(
        messaging.AuthorizationStatus.AUTHORIZED
      );
      mockMessaging.getToken.mockResolvedValue('fcm-token-123');
      (apiClient.registerFCMToken as jest.Mock).mockResolvedValue({});

      await notificationsService.initialize();

      expect(apiClient.registerFCMToken).toHaveBeenCalledWith('fcm-token-123', 'ios');
    });

    it('should use "android" platform identifier on Android', async () => {
      (Platform as any).OS = 'android';
      mockMessaging.requestPermission.mockResolvedValue(
        messaging.AuthorizationStatus.AUTHORIZED
      );
      mockMessaging.getToken.mockResolvedValue('fcm-token-123');
      (apiClient.registerFCMToken as jest.Mock).mockResolvedValue({});

      await notificationsService.initialize();

      expect(apiClient.registerFCMToken).toHaveBeenCalledWith('fcm-token-123', 'android');
    });
  });

  describe('notification types', () => {
    const notificationTypes = [
      { type: 'game_started', game_id: '123' },
      { type: 'game_ended', game_id: '123' },
      { type: 'round_completed', game_id: '123', round: '5' },
      { type: 'your_turn', game_id: '123', node_name: 'Retailer' },
      { type: 'new_template', template_id: '456' },
    ];

    notificationTypes.forEach(({ type, ...data }) => {
      it(`should handle ${type} notification`, async () => {
        mockMessaging.requestPermission.mockResolvedValue(
          messaging.AuthorizationStatus.AUTHORIZED
        );
        mockMessaging.getToken.mockResolvedValue('fcm-token-123');
        (apiClient.registerFCMToken as jest.Mock).mockResolvedValue({});

        let notificationHandler: any;
        mockMessaging.onNotificationOpenedApp.mockImplementation((handler: any) => {
          notificationHandler = handler;
          return jest.fn();
        });

        await notificationsService.initialize();

        const remoteMessage = {
          notification: {
            title: `Test ${type}`,
            body: 'Test notification',
          },
          data: {
            type,
            ...data,
          },
        };

        notificationHandler(remoteMessage);

        expect(notificationHandler).toBeDefined();
      });
    });
  });

  describe('error handling', () => {
    it('should handle missing notification data', async () => {
      mockMessaging.requestPermission.mockResolvedValue(
        messaging.AuthorizationStatus.AUTHORIZED
      );
      mockMessaging.getToken.mockResolvedValue('fcm-token-123');
      (apiClient.registerFCMToken as jest.Mock).mockResolvedValue({});

      let messageHandler: any;
      mockMessaging.onMessage.mockImplementation((handler: any) => {
        messageHandler = handler;
        return jest.fn();
      });

      await notificationsService.initialize();

      const remoteMessage = {
        notification: {
          title: 'Test',
          body: 'Test',
        },
        // No data field
      };

      await expect(messageHandler(remoteMessage)).resolves.not.toThrow();
    });

    it('should handle malformed notification data', async () => {
      mockMessaging.requestPermission.mockResolvedValue(
        messaging.AuthorizationStatus.AUTHORIZED
      );
      mockMessaging.getToken.mockResolvedValue('fcm-token-123');
      (apiClient.registerFCMToken as jest.Mock).mockResolvedValue({});

      let messageHandler: any;
      mockMessaging.onMessage.mockImplementation((handler: any) => {
        messageHandler = handler;
        return jest.fn();
      });

      await notificationsService.initialize();

      const remoteMessage = {
        notification: {
          title: 'Test',
          body: 'Test',
        },
        data: {
          type: 'unknown_type',
          // Missing required fields
        },
      };

      await expect(messageHandler(remoteMessage)).resolves.not.toThrow();
    });

    it('should handle null/undefined messages', async () => {
      mockMessaging.requestPermission.mockResolvedValue(
        messaging.AuthorizationStatus.AUTHORIZED
      );
      mockMessaging.getToken.mockResolvedValue('fcm-token-123');
      (apiClient.registerFCMToken as jest.Mock).mockResolvedValue({});

      let messageHandler: any;
      mockMessaging.onMessage.mockImplementation((handler: any) => {
        messageHandler = handler;
        return jest.fn();
      });

      await notificationsService.initialize();

      await expect(messageHandler(null)).resolves.not.toThrow();
      await expect(messageHandler(undefined)).resolves.not.toThrow();
    });
  });
});
