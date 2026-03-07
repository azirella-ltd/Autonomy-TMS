/**
 * Legacy WebSocket Context — No-op Stub
 *
 * The scenario-scoped WebSocket has been replaced by the tenant-scoped
 * Decision Stream WebSocket (useDecisionStreamWS hook).
 *
 * This stub is retained so that ScenarioBoard and other components
 * that reference WebSocketProvider/useWebSocket don't break.
 */

import { createContext, useContext } from 'react';

export const WebSocketContext = createContext({
  isConnected: false,
  connect: () => false,
  disconnect: () => {},
  sendMessage: () => false,
  subscribe: () => () => {},
});

export const WebSocketProvider = ({ children }) => {
  return (
    <WebSocketContext.Provider
      value={{
        isConnected: false,
        connect: () => false,
        disconnect: () => {},
        sendMessage: () => false,
        subscribe: () => () => {},
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
