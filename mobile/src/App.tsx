/**
 * Main App Component
 * Phase 7 Sprint 1: Mobile Application
 */

import React, { useEffect } from 'react';
import { Provider as PaperProvider } from 'react-native-paper';
import { Provider as ReduxProvider } from 'react-redux';
import { PersistGate } from 'redux-persist/integration/react';
import { StatusBar, Platform, View, StyleSheet } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { store, persistor } from './store';
import AppNavigator from './navigation/AppNavigator';
import { setNetworkStatus } from './store/slices/uiSlice';
import { theme } from './theme';
import { notificationsService } from './services/notifications';
import { offlineService } from './services/offline';
import { websocketService } from './services/websocket';
import Toast from './components/common/Toast';
import OfflineBanner from './components/common/OfflineBanner';
import ErrorBoundary from './components/common/ErrorBoundary';

// Splash screen component
const SplashScreen = () => {
  return null; // You can add a custom splash screen here
};

export default function App() {
  useEffect(() => {
    // Initialize services
    const initializeServices = async () => {
      try {
        // Initialize offline service
        await offlineService.initialize();

        // Initialize push notifications
        await notificationsService.initialize();

        // Initialize WebSocket (after auth)
        // websocketService will be initialized after login
      } catch (error) {
        console.error('Failed to initialize services:', error);
      }
    };

    initializeServices();

    // Listen to network status changes
    const unsubscribe = NetInfo.addEventListener((state) => {
      const status = state.isConnected ? 'online' : 'offline';
      store.dispatch(setNetworkStatus(status));
    });

    return () => {
      unsubscribe();
      websocketService.disconnect();
    };
  }, []);

  return (
    <ErrorBoundary>
      <ReduxProvider store={store}>
        <PersistGate loading={<SplashScreen />} persistor={persistor}>
          <PaperProvider theme={theme}>
            <View style={styles.container}>
              <StatusBar
                barStyle={Platform.OS === 'ios' ? 'dark-content' : 'light-content'}
                backgroundColor="#1976d2"
              />
              <OfflineBanner />
              <AppNavigator />
              <Toast />
            </View>
          </PaperProvider>
        </PersistGate>
      </ReduxProvider>
    </ErrorBoundary>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
});
