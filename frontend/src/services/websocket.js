class WebSocketService {
  constructor() {
    this.socket = null;
    this.callbacks = [];
    this.connected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10; // Increased max reconnection attempts
    this.reconnectDelay = 1000; // Start with 1 second delay
    this.maxReconnectDelay = 30000; // Max 30 seconds delay between reconnections
    this.reconnectTimeout = null;
    this.connectionParams = null;
  }

  /**
   * Connect to the WebSocket server
   * @param {string} gameId - The ID of the scenario to connect to
   * @param {string} accessToken - The user's access token for authentication
   * @param {string} scenarioUserId - The ID of the scenarioUser connecting
   */
  connect(scenarioId, accessToken, scenarioUserId = '1') {
    console.log('[WebSocket] Initializing connection...', { scenarioId, scenarioUserId });

    // Clear any existing reconnection timeout
    if (this.reconnectTimeout) {
      console.log('[WebSocket] Clearing existing reconnection timeout');
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    // Disconnect existing connection if any
    if (this.socket) {
      console.log('[WebSocket] Disconnecting existing socket');
      this.disconnect();
    }

    if (!accessToken) {
      throw new Error('Access token is required to connect to WebSocket');
    }

    if (!scenarioUserId) {
      console.warn('No scenarioUser ID provided, using default (1)');
      scenarioUserId = '1';
    }

    // Store connection parameters for reconnection
    this.connectionParams = { scenarioId, accessToken, scenarioUserId };
    
    try {
      // Use relative URL for WebSocket connection
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsHost = window.location.host;
      const wsPath = `/ws/scenarios/${scenarioId}/scenarioUsers/${scenarioUserId}`;
      
      // Encode the token to handle special characters
      const encodedToken = encodeURIComponent(accessToken);
      const wsUrl = `${wsProtocol}//${wsHost}${wsPath}?token=${encodedToken}`;
      
      console.log('[WebSocket] Connecting to:', wsUrl);
      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = () => {
        console.log('[WebSocket] Connection established');
        this.connected = true;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.notifyCallbacks('connected', { 
          connected: true,
          url: wsUrl,
          timestamp: new Date().toISOString()
        });
      };

      this.socket.onmessage = (event) => {
        try {
          console.log('[WebSocket] Message received:', event.data);
          const data = JSON.parse(event.data);
          this.notifyCallbacks('message', data);
        } catch (error) {
          console.error('[WebSocket] Error parsing message:', error, 'Raw data:', event.data);
          this.notifyCallbacks('error', { 
            error: 'Failed to parse message',
            rawData: event.data,
            timestamp: new Date().toISOString()
          });
        }
      };

      this.socket.onclose = (event) => {
        console.log('[WebSocket] Connection closed:', {
          code: event.code,
          reason: event.reason,
          wasClean: event.wasClean,
          timestamp: new Date().toISOString()
        });
        
        this.connected = false;
        this.notifyCallbacks('disconnected', { 
          reason: event.reason, 
          code: event.code,
          wasClean: event.wasClean,
          timestamp: new Date().toISOString()
        });
        
        // Don't attempt to reconnect if this was a normal closure or unauthorized
        if (event.code !== 1000 && event.code !== 1008) {
          console.log(`[WebSocket] Will attempt to reconnect (code: ${event.code})`);
          this.attemptReconnect();
        } else {
          console.log('[WebSocket] Normal closure, will not reconnect');
        }
      };

      this.socket.onerror = (error) => {
        console.error('[WebSocket] Error:', {
          error: error,
          readyState: this.socket?.readyState,
          url: this.socket?.url,
          timestamp: new Date().toISOString()
        });
        this.notifyCallbacks('error', { 
          error: 'WebSocket error',
          details: error,
          timestamp: new Date().toISOString()
        });
      };
      
    } catch (error) {
      console.error('Error creating WebSocket connection:', error);
      this.attemptReconnect();
    }
  }

  attemptReconnect() {
    if (!this.connectionParams) {
      console.error('No connection parameters available for reconnection');
      return;
    }

    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = Math.min(
        this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
        this.maxReconnectDelay
      );
      
      console.log(`[WebSocket] Will attempt to reconnect in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
      
      this.reconnectTimeout = setTimeout(() => {
        if (!this.connected) {
          console.log(`[WebSocket] Attempting to reconnect (attempt ${this.reconnectAttempts})`);
          this.connect(
            this.connectionParams.gameId,
            this.connectionParams.accessToken,
            this.connectionParams.scenarioUserId
          );
        }
      }, delay);
    } else {
      console.error('Max reconnection attempts reached');
      this.notifyCallbacks('reconnect_failed', { message: 'Max reconnection attempts reached' });
    }
  }

  disconnect() {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
      this.connected = false;
    }
    
    // Clear any pending reconnection
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
  }
  

  send(message) {
    if (this.socket && this.connected) {
      this.socket.send(JSON.stringify(message));
      return true;
    }
    console.error('WebSocket is not connected');
    return false;
  }

  subscribe(callback) {
    this.callbacks.push(callback);
    // Return unsubscribe function
    return () => {
      this.callbacks = this.callbacks.filter(cb => cb !== callback);
    };
  }

  notifyCallbacks(event, data) {
    this.callbacks.forEach(callback => {
      try {
        callback(event, data);
      } catch (error) {
        console.error('Error in WebSocket callback:', error);
      }
    });
  }

  isConnected() {
    return this.connected;
  }
}

// Create a singleton instance
export const webSocketService = new WebSocketService();
