/**
 * Legacy WebSocket Context (.js version) — No-op Stub
 *
 * The scenario-scoped WebSocket has been replaced by the tenant-scoped
 * Decision Stream WebSocket (useDecisionStreamWS hook).
 *
 * This stub is retained so existing imports don't break.
 */

import React, { createContext, useContext } from 'react';

const WebSocketContext = createContext(null);

export const WebSocketProvider = ({ children }) => {
  const api = {
    isConnected: false,
    scenarioState: null,
    scenarioUsers: [],
    currentPeriod: 0,
    scenarioStatus: 'idle',
    send: () => {},
    on: () => () => {},
  };

  return (
    <WebSocketContext.Provider value={api}>
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocket = () => {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return context;
};

export default WebSocketContext;
