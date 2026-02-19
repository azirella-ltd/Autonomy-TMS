/**
 * WebSocket Service
 * Phase 7 Sprint 1: Mobile Application
 */

import { io, Socket } from 'socket.io-client';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

const WS_URL = __DEV__
  ? Platform.OS === 'ios'
    ? 'ws://localhost:8000'
    : 'ws://10.0.2.2:8000'
  : 'wss://api.beergame.com';

class WebSocketService {
  private socket: Socket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private listeners: Map<string, Set<Function>> = new Map();

  /**
   * Connect to WebSocket server
   */
  async connect(): Promise<void> {
    if (this.socket?.connected) {
      console.log('WebSocket already connected');
      return;
    }

    try {
      // Get auth token
      const token = await AsyncStorage.getItem('auth_token');

      // Create socket connection
      this.socket = io(WS_URL, {
        transports: ['websocket'],
        auth: {
          token,
        },
        reconnection: true,
        reconnectionDelay: this.reconnectDelay,
        reconnectionAttempts: this.maxReconnectAttempts,
      });

      this.setupEventHandlers();

      console.log('WebSocket connection initiated');
    } catch (error) {
      console.error('Failed to connect to WebSocket:', error);
      throw error;
    }
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect(): void {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
      this.listeners.clear();
      console.log('WebSocket disconnected');
    }
  }

  /**
   * Check if connected
   */
  isConnected(): boolean {
    return this.socket?.connected || false;
  }

  /**
   * Setup socket event handlers
   */
  private setupEventHandlers(): void {
    if (!this.socket) return;

    this.socket.on('connect', () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
      this.emit('connection_status', { connected: true });
    });

    this.socket.on('disconnect', (reason) => {
      console.log('WebSocket disconnected:', reason);
      this.emit('connection_status', { connected: false, reason });
    });

    this.socket.on('connect_error', (error) => {
      console.error('WebSocket connection error:', error);
      this.reconnectAttempts++;
      this.emit('connection_error', { error, attempts: this.reconnectAttempts });
    });

    this.socket.on('reconnect_attempt', (attemptNumber) => {
      console.log(`WebSocket reconnect attempt ${attemptNumber}`);
    });

    this.socket.on('reconnect_failed', () => {
      console.error('WebSocket reconnection failed');
      this.emit('reconnect_failed', {});
    });

    // Game event handlers
    this.socket.on('round_completed', (data) => {
      console.log('Round completed:', data);
      this.emit('round_completed', data);
    });

    this.socket.on('game_started', (data) => {
      console.log('Game started:', data);
      this.emit('game_started', data);
    });

    this.socket.on('game_ended', (data) => {
      console.log('Game ended:', data);
      this.emit('game_ended', data);
    });

    this.socket.on('player_action', (data) => {
      console.log('Player action:', data);
      this.emit('player_action', data);
    });

    this.socket.on('game_state_updated', (data) => {
      console.log('Game state updated:', data);
      this.emit('game_state_updated', data);
    });
  }

  /**
   * Subscribe to a room (game)
   */
  joinGame(gameId: number): void {
    if (this.socket) {
      this.socket.emit('join_game', { game_id: gameId });
      console.log(`Joined game ${gameId}`);
    }
  }

  /**
   * Unsubscribe from a room (game)
   */
  leaveGame(gameId: number): void {
    if (this.socket) {
      this.socket.emit('leave_game', { game_id: gameId });
      console.log(`Left game ${gameId}`);
    }
  }

  /**
   * Subscribe to an event
   */
  on(event: string, callback: Function): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);
  }

  /**
   * Unsubscribe from an event
   */
  off(event: string, callback: Function): void {
    const listeners = this.listeners.get(event);
    if (listeners) {
      listeners.delete(callback);
      if (listeners.size === 0) {
        this.listeners.delete(event);
      }
    }
  }

  /**
   * Emit event to all listeners
   */
  private emit(event: string, data: any): void {
    const listeners = this.listeners.get(event);
    if (listeners) {
      listeners.forEach((callback) => {
        try {
          callback(data);
        } catch (error) {
          console.error(`Error in event listener for ${event}:`, error);
        }
      });
    }
  }

  /**
   * Send a message to the server
   */
  send(event: string, data: any): void {
    if (this.socket?.connected) {
      this.socket.emit(event, data);
    } else {
      console.warn('WebSocket not connected, cannot send message');
    }
  }
}

// Export singleton instance
export const websocketService = new WebSocketService();
export default websocketService;
