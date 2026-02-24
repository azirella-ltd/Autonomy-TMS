import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { webSocketService } from '../services/websocket';
import { toast } from 'sonner';
import { useAuth } from './AuthContext';

const WebSocketContext = createContext(null);

export const WebSocketProvider = ({ children }) => {
  const [isConnected, setIsConnected] = useState(false);
  const [gameState, setGameState] = useState(null);
  const [scenarioUsers, setPlayers] = useState([]);
  const [currentRound, setCurrentRound] = useState(0);
  const [gameStatus, setGameStatus] = useState('idle');
  const callbacks = useRef(new Map());
  const params = useParams();
  const { accessToken } = useAuth();

  // Register a callback for specific message types
  const on = (eventType, callback) => {
    callbacks.current.set(eventType, callback);

    // Return cleanup function
    return () => {
      callbacks.current.delete(eventType);
    };
  };

  // Send a message through the WebSocket
  const send = useCallback((type, data = {}) => {
    return webSocketService.send({ type, ...data });
  }, []);

  // Handle incoming WebSocket messages
  const handleIncomingMessage = useCallback((event, data = {}) => {
    // Handle both direct event and message objects with type/data
    const message = typeof event === 'string' ? { type: event, ...data } : event;
    const { type, ...messageData } = message;

    // Check for registered callbacks first
    const callback = callbacks.current.get(type);
    if (callback) {
      callback(messageData);
    }

    // Handle known message types
    switch (type) {
      case 'game_state':
        setGameState(messageData.state || messageData);
        setPlayers(messageData.scenarioUsers || []);
        setCurrentRound(messageData.current_round || messageData.currentRound || 0);
        setGameStatus(messageData.status || 'idle');
        break;

      case 'round_started':
        setCurrentRound(messageData.round_number || messageData.roundNumber);
        setGameStatus('in_progress');
        toast.info(`Round ${messageData.round_number || messageData.roundNumber} Started`, {
          description: messageData.message || 'A new round has begun!',
        });
        break;

      case 'round_ended':
        setGameStatus('round_ended');
        toast.info(`Round ${messageData.round_number || messageData.roundNumber} Ended`, {
          description: messageData.message || 'The round has ended.',
        });
        break;

      case 'game_ended':
        setGameStatus('completed');
        toast.success('Game Over', {
          description: messageData.message || 'The game has ended.',
          duration: Infinity,
        });
        break;

      case 'player_joined':
        toast.info('ScenarioUser Joined', {
          description: `${messageData.scenario_user_name} has joined the game.`,
        });
        break;

      case 'player_left':
        toast.warning('ScenarioUser Left', {
          description: `${messageData.scenario_user_name} has left the game.`,
        });
        break;

      case 'error':
        toast.error('Error', {
          description: messageData.message || 'An error occurred',
        });
        break;

      default:
        console.log('Unhandled WebSocket message type:', type);
        break;
    }
  }, []);

  // Initialize WebSocket connection
  useEffect(() => {
    const gameId = params.gameId;
    if (!gameId || !accessToken) return;

    const handleWebSocketMessage = (event, data) => {
      switch (event) {
        case 'connected':
          setIsConnected(true);
          // Request the current game state when connected
          send('get_state');
          break;

        case 'disconnected':
          setIsConnected(false);
          break;

        case 'message':
          // Handle incoming message using the useCallback handler
          handleIncomingMessage(data.type, data.data || data);
          break;

        case 'error':
          console.error('WebSocket error:', data);
          toast.error('Connection Error', {
            description: data.message || 'There was a problem with the game connection.',
          });
          break;

        case 'reconnect_failed':
          toast.error('Connection Lost', {
            description: 'Unable to reconnect to the game server.',
            duration: Infinity,
          });
          break;

        default:
          console.log('Unhandled WebSocket event:', event, data);
          break;
      }
    };

    const connectWebSocket = async () => {
      try {
        // Connect to WebSocket with the current access token
        webSocketService.connect(gameId, accessToken);
        const unsubscribe = webSocketService.subscribe(handleWebSocketMessage);

        // Cleanup on unmount
        return () => {
          unsubscribe();
          webSocketService.disconnect();
        };
      } catch (error) {
        console.error('Failed to connect to WebSocket:', error);
        toast.error('Connection Error', {
          description: 'Failed to connect to the game server. Please try again.',
        });
      }
    };

    connectWebSocket();

    // Cleanup on unmount
    return () => {
      webSocketService.disconnect();
    };
  }, [params.gameId, accessToken, handleIncomingMessage, send]);


  // Expose the WebSocket API to child components
  const api = {
    isConnected,
    gameState,
    scenarioUsers,
    currentRound,
    gameStatus,
    send,
    on,
  };

  return (
    <WebSocketContext.Provider value={api}>
      {children}
    </WebSocketContext.Provider>
  );
};

// Custom hook to use the WebSocket context
export const useWebSocket = () => {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return context;
};

export default WebSocketContext;
