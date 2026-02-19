import { createContext, useContext, useEffect, useRef, useCallback } from 'react';
import { useAuth } from './AuthContext';
import { webSocketService } from '../services/websocket';

export const WebSocketContext = createContext({
  isConnected: false,
  connect: () => {},
  disconnect: () => {},
  sendMessage: () => {},
  subscribe: () => () => {},
});

export const WebSocketProvider = ({ children }) => {
  const { accessToken, isAuthenticated } = useAuth();
  const callbacksRef = useRef(new Set());
  const isConnectedRef = useRef(false);
  const gameIdRef = useRef(null);

  // Notify all registered callbacks
  const notifyCallbacks = useCallback((event, data) => {
    callbacksRef.current.forEach(cb => {
      try {
        cb(event, data);
      } catch (error) {
        console.error('Error in WebSocket callback:', error);
      }
    });
  }, []);

  // Handle WebSocket connection
  const connect = useCallback((gameId, playerId) => {
    if (!isAuthenticated || !accessToken) {
      console.error('Cannot connect to WebSocket: User is not authenticated');
      return false;
    }

    if (webSocketService.isConnected() && gameIdRef.current === gameId) {
      console.log('Already connected to this game');
      return true;
    }

    // Disconnect from previous connection if any
    if (webSocketService.isConnected()) {
      webSocketService.disconnect();
    }

    try {
      gameIdRef.current = gameId;
      webSocketService.connect(gameId, accessToken, playerId);
      return true;
    } catch (error) {
      console.error('Failed to connect to WebSocket:', error);
      return false;
    }
  }, [accessToken, isAuthenticated]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    webSocketService.disconnect();
    isConnectedRef.current = false;
    gameIdRef.current = null;
  }, []);

  // Send a message through WebSocket
  const sendMessage = useCallback((type, data = {}) => {
    if (!webSocketService.isConnected()) {
      console.error('Cannot send message: WebSocket is not connected');
      return false;
    }

    try {
      webSocketService.send({ type, ...data });
      return true;
    } catch (error) {
      console.error('Failed to send WebSocket message:', error);
      return false;
    }
  }, []);

  // Subscribe to WebSocket events
  const subscribe = useCallback((callback) => {
    callbacksRef.current.add(callback);
    return () => {
      callbacksRef.current.delete(callback);
    };
  }, []);

  // Set up WebSocket event listeners
  useEffect(() => {
    const handleConnected = () => {
      isConnectedRef.current = true;
      notifyCallbacks('connected', { gameId: gameIdRef.current });
    };

    const handleDisconnected = () => {
      isConnectedRef.current = false;
      notifyCallbacks('disconnected', { gameId: gameIdRef.current });
    };

    const handleMessage = (data) => {
      notifyCallbacks('message', data);
    };

    const handleError = (error) => {
      console.error('WebSocket error:', error);
      notifyCallbacks('error', { error });
    };

    const handleReconnectFailed = (data) => {
      console.error('WebSocket reconnection failed:', data);
      notifyCallbacks('reconnect_failed', data);
    };

    // Subscribe to WebSocket service events
    const unsubscribe = webSocketService.subscribe((event, data) => {
      switch (event) {
        case 'connected':
          handleConnected();
          break;
        case 'disconnected':
          handleDisconnected();
          break;
        case 'message':
          handleMessage(data);
          break;
        case 'error':
          handleError(data);
          break;
        case 'reconnect_failed':
          handleReconnectFailed(data);
          break;
        default:
          console.warn('Unknown WebSocket event:', event, data);
      }
    });

    // Clean up on unmount
    return () => {
      unsubscribe();
      if (webSocketService.isConnected()) {
        webSocketService.disconnect();
      }
    };
  }, [notifyCallbacks]);

  // Disconnect when user logs out
  useEffect(() => {
    if (!isAuthenticated && webSocketService.isConnected()) {
      webSocketService.disconnect();
      isConnectedRef.current = false;
      gameIdRef.current = null;
    }
  }, [isAuthenticated]);

  return (
    <WebSocketContext.Provider
      value={{
        isConnected: isConnectedRef.current,
        connect,
        disconnect,
        sendMessage,
        subscribe,
      }}
    >
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocket = () => {
  const context = useContext(WebSocketContext);
  if (context === undefined) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return context;
};
