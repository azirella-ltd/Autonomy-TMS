import React, { useEffect, useState } from 'react';
import { Button, Card, CardContent } from './common';
import { useWebSocket } from '../contexts/WebSocketContext';
import { useAuth } from '../contexts/AuthContext';
import { toast } from 'sonner';

export const WebSocketTester = ({ gameId }) => {
  const { isConnected, send, on } = useWebSocket();
  const { accessToken } = useAuth();
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    // Subscribe to WebSocket messages
    const unsubscribe = on('message', (message) => {
      setMessages(prev => [...prev.slice(-9), message]); // Keep last 10 messages
      console.log('WebSocket message:', message);
    });

    return () => {
      if (unsubscribe) unsubscribe();
    };
  }, [on]);

  const handlePing = () => {
    try {
      send('ping', { timestamp: Date.now() });
      toast.success('Ping sent');
    } catch (error) {
      console.error('Failed to send ping:', error);
      toast.error('Failed to send ping', {
        description: error.message,
      });
    }
  };

  return (
    <Card>
      <CardContent className="p-4">
        <div className="space-y-4">
          <h3 className="text-lg font-bold">WebSocket Connection Test</h3>

          <div className="space-y-1">
            <p>
              Status:{' '}
              <span className={`font-bold ${isConnected ? 'text-green-500' : 'text-red-500'}`}>
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
            </p>
            <p>Game ID: {gameId || 'Not set'}</p>
            <p>Access Token: {accessToken ? 'Present' : 'Missing'}</p>
          </div>

          <Button
            onClick={handlePing}
            disabled={!isConnected}
          >
            Send Ping
          </Button>

          <div className="mt-4">
            <p className="font-bold">Last Messages:</p>
            <div className="mt-2 p-2 bg-muted rounded-md min-h-[100px] max-h-[200px] overflow-y-auto">
              {messages.length === 0 ? (
                <p className="text-muted-foreground">No messages received yet</p>
              ) : (
                messages.map((msg, i) => (
                  <pre key={i} className="text-sm font-mono whitespace-pre-wrap">
                    {JSON.stringify(msg, null, 2)}
                  </pre>
                ))
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default WebSocketTester;
