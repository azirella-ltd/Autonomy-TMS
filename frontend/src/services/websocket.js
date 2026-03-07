/**
 * Legacy WebSocket Service — No-op Stub
 *
 * The scenario-scoped WebSocket has been replaced by the tenant-scoped
 * Decision Stream WebSocket (useDecisionStreamWS hook in hooks/).
 *
 * This stub is retained for backward compatibility with ScenarioBoard
 * and other components that import webSocketService.
 */

class WebSocketService {
  constructor() {
    this.connected = false;
  }

  connect() {}
  disconnect() {}
  send() {}

  isConnected() {
    return false;
  }

  subscribe() {
    return () => {};
  }
}

export const webSocketService = new WebSocketService();
export default webSocketService;
