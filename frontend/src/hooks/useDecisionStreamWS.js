/**
 * useDecisionStreamWS — Real-time WebSocket hook for Decision Stream
 *
 * Connects to the backend WebSocket and provides:
 * - alerts: CDC triggers and condition monitor alerts
 * - newDecisions: decision status changes from other users
 * - isConnected: connection status
 */

import { useState, useEffect, useRef, useCallback } from 'react';

const WS_RECONNECT_DELAY = 3000;

const useDecisionStreamWS = (tenantId) => {
  const [alerts, setAlerts] = useState([]);
  const [newDecisions, setNewDecisions] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);

  const connect = useCallback(() => {
    if (!tenantId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws/decision-stream/${tenantId}`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        // Start ping interval
        ws._pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          switch (msg.type) {
            case 'cdc_trigger':
            case 'condition_alert':
              setAlerts((prev) => [msg.data, ...prev].slice(0, 20));
              break;
            case 'decision_update':
              setNewDecisions((prev) => [msg.data, ...prev].slice(0, 10));
              break;
            case 'pong':
              // Heartbeat response
              break;
            default:
              break;
          }
        } catch (e) {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        clearInterval(ws._pingInterval);
        // Auto-reconnect
        reconnectTimer.current = setTimeout(connect, WS_RECONNECT_DELAY);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch (e) {
      // WebSocket creation failed — retry
      reconnectTimer.current = setTimeout(connect, WS_RECONNECT_DELAY);
    }
  }, [tenantId]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        clearInterval(wsRef.current._pingInterval);
        wsRef.current.close();
      }
    };
  }, [connect]);

  const clearAlerts = useCallback(() => setAlerts([]), []);
  const clearNewDecisions = useCallback(() => setNewDecisions([]), []);

  return { alerts, newDecisions, isConnected, clearAlerts, clearNewDecisions };
};

export default useDecisionStreamWS;
