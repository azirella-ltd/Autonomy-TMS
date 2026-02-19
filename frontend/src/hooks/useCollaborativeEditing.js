/**
 * useCollaborativeEditing Hook
 *
 * React hook for real-time collaborative editing via WebSocket.
 * Provides presence awareness, cursor tracking, cell locking, and edit synchronization.
 *
 * Phase 3.6: Real-Time Co-Editing
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../contexts/AuthContext';

const WS_BASE_URL = process.env.REACT_APP_WS_URL || `ws://${window.location.host}`;

export const useCollaborativeEditing = (documentId, documentType) => {
  const { user } = useAuth();
  const [isConnected, setIsConnected] = useState(false);
  const [sessionVersion, setSessionVersion] = useState(0);
  const [activeUsers, setActiveUsers] = useState([]);
  const [cursorPositions, setCursorPositions] = useState({});
  const [selections, setSelections] = useState({});
  const [lockedCells, setLockedCells] = useState({});
  const [pendingEdits, setPendingEdits] = useState([]);
  const [myColor, setMyColor] = useState('#3B82F6');
  const [error, setError] = useState(null);

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const pingIntervalRef = useRef(null);

  // Initialize session
  const initSession = useCallback(async () => {
    if (!documentId || !documentType) return;

    try {
      const response = await fetch(`/api/collaborative-editing/sessions/${documentType}/${documentId}`, {
        method: 'POST',
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error('Failed to create session');
      }

      const data = await response.json();
      setSessionVersion(data.session_version);
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    }
  }, [documentId, documentType]);

  // Connect to WebSocket
  const connect = useCallback(async () => {
    if (!documentId || !user) return;

    // Initialize session first
    await initSession();

    const wsUrl = `${WS_BASE_URL}/api/collaborative-editing/ws/${documentId}?user_id=${user.id}&user_name=${encodeURIComponent(user.email || user.username || 'User')}`;

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('Collaborative editing connected');
        setIsConnected(true);
        setError(null);

        // Start ping interval
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        handleMessage(message);
      };

      ws.onclose = (event) => {
        console.log('Collaborative editing disconnected', event.code);
        setIsConnected(false);
        clearInterval(pingIntervalRef.current);

        // Attempt reconnect if not intentional close
        if (event.code !== 1000) {
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, 3000);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setError('Connection error');
      };

      wsRef.current = ws;
    } catch (err) {
      setError(err.message);
    }
  }, [documentId, user, initSession]);

  // Handle incoming messages
  const handleMessage = useCallback((message) => {
    switch (message.type) {
      case 'session_joined':
        setSessionVersion(message.version);
        setActiveUsers(message.users || []);
        setMyColor(message.your_color);
        // Set initial locks
        const initialLocks = {};
        (message.locks || []).forEach(lock => {
          initialLocks[lock.cell_id] = lock.user_id;
        });
        setLockedCells(initialLocks);
        break;

      case 'user_joined':
        setActiveUsers(prev => [...prev.filter(u => u.user_id !== message.user.user_id), message.user]);
        break;

      case 'user_left':
        setActiveUsers(prev => prev.filter(u => u.user_id !== message.user_id));
        // Clear cursor and selection for this user
        setCursorPositions(prev => {
          const next = { ...prev };
          delete next[message.user_id];
          return next;
        });
        setSelections(prev => {
          const next = { ...prev };
          delete next[message.user_id];
          return next;
        });
        break;

      case 'cursor_moved':
        setCursorPositions(prev => ({
          ...prev,
          [message.user_id]: message.position
        }));
        break;

      case 'selection_changed':
        setSelections(prev => ({
          ...prev,
          [message.user_id]: message.selected
        }));
        break;

      case 'cell_locked':
        setLockedCells(prev => ({
          ...prev,
          [message.cell_id]: { user_id: message.user_id, color: message.color }
        }));
        break;

      case 'cell_unlocked':
        setLockedCells(prev => {
          const next = { ...prev };
          delete next[message.cell_id];
          return next;
        });
        break;

      case 'edit_applied':
        // Apply remote edit
        setSessionVersion(message.operation.version);
        // Notify parent component of remote edit
        break;

      case 'edit_result':
        if (message.success) {
          setSessionVersion(message.version);
          // Remove from pending edits
          setPendingEdits(prev => prev.filter(e => e.operation_id !== message.operation_id));
        } else if (message.conflict) {
          // Handle conflict
          console.warn('Edit conflict detected', message);
        }
        break;

      case 'pong':
        // Keep-alive acknowledged
        break;

      default:
        console.log('Unknown message type:', message.type);
    }
  }, []);

  // Disconnect
  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close(1000, 'User disconnected');
      wsRef.current = null;
    }
    clearTimeout(reconnectTimeoutRef.current);
    clearInterval(pingIntervalRef.current);
    setIsConnected(false);
  }, []);

  // Send cursor position
  const sendCursorPosition = useCallback((position) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'cursor_move',
        position
      }));
    }
  }, []);

  // Send selection change
  const sendSelectionChange = useCallback((selected) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'selection_change',
        selected
      }));
    }
  }, []);

  // Request cell lock
  const requestLock = useCallback((rowId, columnId) => {
    return new Promise((resolve) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        const handleLockResult = (event) => {
          const message = JSON.parse(event.data);
          if (message.type === 'lock_result' && message.cell_id === `${rowId}:${columnId}`) {
            wsRef.current.removeEventListener('message', handleLockResult);
            resolve(message.success);
          }
        };
        wsRef.current.addEventListener('message', handleLockResult);
        wsRef.current.send(JSON.stringify({
          type: 'request_lock',
          row_id: rowId,
          column_id: columnId
        }));

        // Timeout after 5 seconds
        setTimeout(() => {
          wsRef.current?.removeEventListener('message', handleLockResult);
          resolve(false);
        }, 5000);
      } else {
        resolve(false);
      }
    });
  }, []);

  // Release cell lock
  const releaseLock = useCallback((rowId, columnId) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'release_lock',
        row_id: rowId,
        column_id: columnId
      }));
    }
  }, []);

  // Send cell edit
  const sendEdit = useCallback((edit) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const operation = {
        type: 'cell_edit',
        edit,
        version: sessionVersion
      };
      wsRef.current.send(JSON.stringify(operation));
      setPendingEdits(prev => [...prev, { ...edit, operation_id: Date.now().toString() }]);
    }
  }, [sessionVersion]);

  // Send bulk edit
  const sendBulkEdit = useCallback((edits) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'bulk_edit',
        edits,
        version: sessionVersion
      }));
    }
  }, [sessionVersion]);

  // Check if cell is locked by another user
  const isCellLockedByOther = useCallback((rowId, columnId) => {
    const cellId = `${rowId}:${columnId}`;
    const lock = lockedCells[cellId];
    return lock && lock.user_id !== user?.id;
  }, [lockedCells, user]);

  // Get lock info for a cell
  const getCellLockInfo = useCallback((rowId, columnId) => {
    const cellId = `${rowId}:${columnId}`;
    return lockedCells[cellId] || null;
  }, [lockedCells]);

  // Get user color
  const getUserColor = useCallback((userId) => {
    const user = activeUsers.find(u => u.user_id === userId);
    return user?.color || '#888';
  }, [activeUsers]);

  // Auto-connect on mount
  useEffect(() => {
    if (documentId && user) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [documentId, user, connect, disconnect]);

  return {
    // Connection state
    isConnected,
    error,
    connect,
    disconnect,

    // Session state
    sessionVersion,
    activeUsers,
    myColor,

    // Presence
    cursorPositions,
    selections,
    sendCursorPosition,
    sendSelectionChange,

    // Locking
    lockedCells,
    requestLock,
    releaseLock,
    isCellLockedByOther,
    getCellLockInfo,

    // Editing
    sendEdit,
    sendBulkEdit,
    pendingEdits,

    // Helpers
    getUserColor,
  };
};

export default useCollaborativeEditing;
