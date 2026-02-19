# A2A API Reference

**Agent-to-Agent Collaboration API Documentation**

Complete API reference for developers integrating A2A chat functionality.

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [REST Endpoints](#rest-endpoints)
4. [WebSocket Events](#websocket-events)
5. [Data Models](#data-models)
6. [Error Handling](#error-handling)
7. [Rate Limiting](#rate-limiting)
8. [Examples](#examples)

---

## Overview

### Base URL

```
Production: https://api.beergame.com
Development: http://localhost:8000
```

### API Version

Current version: **v1**

All endpoints prefixed with `/api/v1/`

### Content Type

```
Content-Type: application/json
```

---

## Authentication

### Bearer Token

All requests require JWT authentication:

```http
Authorization: Bearer <access_token>
```

### Token Refresh

```http
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "string"
}
```

**Response:**
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "expires_in": 3600
}
```

---

## REST Endpoints

### Get Chat Messages

Retrieve chat messages for a game.

```http
GET /api/v1/games/{game_id}/chat/messages
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| game_id | integer | Yes | Game ID |
| since | string | No | ISO timestamp for messages after this time |
| limit | integer | No | Max messages to return (default: 50) |

**Response:**
```json
{
  "messages": [
    {
      "id": "msg_123",
      "game_id": 1,
      "sender_id": "agent:wholesaler",
      "sender_name": "Wholesaler",
      "sender_type": "agent",
      "recipient_id": null,
      "content": "I recommend ordering 45 units",
      "type": "suggestion",
      "metadata": {
        "suggestion": {
          "order_quantity": 45,
          "confidence": 0.85,
          "rationale": "Recent demand trending up..."
        }
      },
      "timestamp": "2026-01-14T12:00:00Z",
      "read": false,
      "delivered": true
    }
  ],
  "pagination": {
    "total": 150,
    "page": 1,
    "page_size": 50,
    "has_more": true
  }
}
```

---

### Send Chat Message

Send a new chat message.

```http
POST /api/v1/games/{game_id}/chat/messages
Content-Type: application/json

{
  "sender_id": "player:1",
  "sender_name": "John Doe",
  "sender_type": "player",
  "recipient_id": "agent:wholesaler",
  "content": "What should I order this round?",
  "type": "question"
}
```

**Response:**
```json
{
  "id": "msg_124",
  "game_id": 1,
  "sender_id": "player:1",
  "sender_name": "John Doe",
  "sender_type": "player",
  "recipient_id": "agent:wholesaler",
  "content": "What should I order this round?",
  "type": "question",
  "timestamp": "2026-01-14T12:01:00Z",
  "read": false,
  "delivered": true
}
```

---

### Mark Messages as Read

Mark messages as read.

```http
PUT /api/v1/games/{game_id}/chat/messages/read
Content-Type: application/json

{
  "message_ids": ["msg_123", "msg_124"]
}
```

**Response:**
```json
{
  "success": true,
  "marked_count": 2
}
```

---

### Request Agent Suggestion

Request an order suggestion from an agent.

```http
POST /api/v1/games/{game_id}/chat/request-suggestion
Content-Type: application/json

{
  "context": {
    "current_round": 5,
    "player_node": "retailer",
    "preferences": {
      "risk_tolerance": "moderate",
      "strategy": "balanced"
    }
  }
}
```

**Response:**
```json
{
  "id": "sug_456",
  "game_id": 1,
  "round": 5,
  "agent_name": "Wholesaler",
  "order_quantity": 45,
  "confidence": 0.85,
  "rationale": "Recent demand trending up from 40 to 48 units. Your current inventory of 50 won't cover forecasted demand.",
  "context": {
    "current_inventory": 50,
    "current_backlog": 10,
    "recent_demand": [38, 42, 45, 48],
    "forecast_demand": 48
  },
  "timestamp": "2026-01-14T12:02:00Z"
}
```

---

### Get Agent Suggestions

Retrieve all suggestions for a game.

```http
GET /api/v1/games/{game_id}/chat/suggestions
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| game_id | integer | Yes | Game ID |
| round | integer | No | Filter by round number |
| accepted | boolean | No | Filter by acceptance status |

**Response:**
```json
{
  "suggestions": [
    {
      "id": "sug_456",
      "game_id": 1,
      "round": 5,
      "agent_name": "Wholesaler",
      "order_quantity": 45,
      "confidence": 0.85,
      "rationale": "...",
      "context": {...},
      "accepted": true,
      "timestamp": "2026-01-14T12:02:00Z"
    }
  ]
}
```

---

### Accept Suggestion

Accept an agent suggestion.

```http
PUT /api/v1/games/{game_id}/chat/suggestions/{suggestion_id}/accept
```

**Response:**
```json
{
  "id": "sug_456",
  "accepted": true,
  "accepted_at": "2026-01-14T12:03:00Z"
}
```

---

### Decline Suggestion

Decline an agent suggestion.

```http
PUT /api/v1/games/{game_id}/chat/suggestions/{suggestion_id}/decline
Content-Type: application/json

{
  "reason": "Too high, I prefer 40 units"
}
```

**Response:**
```json
{
  "id": "sug_456",
  "accepted": false,
  "declined_at": "2026-01-14T12:03:00Z",
  "decline_reason": "Too high, I prefer 40 units"
}
```

---

### Run What-If Analysis

Run a what-if scenario analysis.

```http
POST /api/v1/games/{game_id}/chat/what-if
Content-Type: application/json

{
  "question": "What if I order 50 units instead of 40?",
  "scenario": {
    "order_quantity": 50,
    "current_order": 40,
    "rounds_ahead": 3
  }
}
```

**Response:**
```json
{
  "question": "What if I order 50 units instead of 40?",
  "answer": "Ordering 50 vs 40 would result in...",
  "analysis": {
    "scenario": {
      "order_quantity": 50,
      "delta": 10
    },
    "outcome": {
      "inventory_change": 10,
      "backlog_change": -8,
      "service_level_change": 0.03,
      "cost_change": 150
    },
    "recommendation": "Recommended if demand continues to trend upward"
  },
  "timestamp": "2026-01-14T12:04:00Z"
}
```

---

## WebSocket Events

### Connection

```javascript
import io from 'socket.io-client';

const socket = io('wss://api.beergame.com', {
  auth: {
    token: 'Bearer <access_token>'
  }
});
```

### Join Game Chat

```javascript
socket.emit('join_game', { game_id: 1 });
```

### Leave Game Chat

```javascript
socket.emit('leave_game', { game_id: 1 });
```

---

### Client → Server Events

#### Send Message

```javascript
socket.emit('chat:send_message', {
  game_id: 1,
  sender_id: 'player:1',
  sender_name: 'John Doe',
  sender_type: 'player',
  content: 'What should I order?',
  type: 'question'
});
```

#### Send Typing Indicator

```javascript
socket.emit('chat:typing', {
  game_id: 1,
  is_typing: true
});
```

#### Mark Messages as Read

```javascript
socket.emit('chat:mark_read', {
  game_id: 1,
  message_ids: ['msg_123', 'msg_124']
});
```

#### Request Suggestion

```javascript
socket.emit('chat:request_suggestion', {
  game_id: 1,
  context: {}
});
```

---

### Server → Client Events

#### New Message

```javascript
socket.on('chat:new_message', (data) => {
  console.log('New message:', data);
  // data = ChatMessage object
});
```

**Payload:**
```json
{
  "id": "msg_125",
  "game_id": 1,
  "sender_id": "agent:wholesaler",
  "sender_name": "Wholesaler",
  "sender_type": "agent",
  "content": "I recommend 45 units",
  "type": "suggestion",
  "timestamp": "2026-01-14T12:05:00Z",
  "read": false,
  "delivered": true
}
```

#### Agent Typing

```javascript
socket.on('chat:agent_typing', (data) => {
  console.log('Agent typing:', data);
});
```

**Payload:**
```json
{
  "agent_id": "agent:wholesaler",
  "is_typing": true
}
```

#### Suggestion Ready

```javascript
socket.on('chat:suggestion_ready', (data) => {
  console.log('Suggestion ready:', data);
  // data = AgentSuggestion object
});
```

#### Message Delivered

```javascript
socket.on('chat:message_delivered', (data) => {
  console.log('Message delivered:', data);
});
```

**Payload:**
```json
{
  "message_id": "msg_125",
  "delivered": true,
  "delivered_at": "2026-01-14T12:05:01Z"
}
```

#### Message Read

```javascript
socket.on('chat:message_read', (data) => {
  console.log('Message read:', data);
});
```

**Payload:**
```json
{
  "message_id": "msg_125",
  "read": true,
  "read_at": "2026-01-14T12:05:05Z"
}
```

---

## Data Models

### ChatMessage

```typescript
interface ChatMessage {
  id: string;                    // Unique message ID
  game_id: number;               // Game ID
  sender_id: string;             // 'player:1' or 'agent:wholesaler'
  sender_name: string;           // Display name
  sender_type: 'player' | 'agent';
  recipient_id?: string;         // null = broadcast
  content: string;               // Message text
  type: 'text' | 'suggestion' | 'question' | 'analysis';
  metadata?: ChatMessageMetadata;
  timestamp: string;             // ISO 8601
  read: boolean;
  delivered: boolean;
}
```

### ChatMessageMetadata

```typescript
interface ChatMessageMetadata {
  suggestion?: {
    order_quantity: number;
    confidence: number;          // 0-1
    rationale: string;
  };
  analysis?: {
    metric: string;
    value: number;
    trend: 'up' | 'down' | 'stable';
  };
}
```

### AgentSuggestion

```typescript
interface AgentSuggestion {
  id: string;
  game_id: number;
  round: number;
  agent_name: string;
  order_quantity: number;
  confidence: number;            // 0-1
  rationale: string;
  context: {
    current_inventory: number;
    current_backlog: number;
    recent_demand: number[];
    forecast_demand: number;
  };
  accepted?: boolean;
  timestamp: string;
}
```

### WhatIfAnalysis

```typescript
interface WhatIfAnalysis {
  question: string;
  answer: string;
  analysis: {
    scenario: any;
    outcome: any;
    recommendation: string;
  };
  timestamp: string;
}
```

---

## Error Handling

### Error Response Format

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid message content",
    "details": {
      "field": "content",
      "reason": "Content cannot be empty"
    }
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| VALIDATION_ERROR | 400 | Invalid request data |
| UNAUTHORIZED | 401 | Missing or invalid auth token |
| FORBIDDEN | 403 | Insufficient permissions |
| NOT_FOUND | 404 | Resource not found |
| RATE_LIMIT_EXCEEDED | 429 | Too many requests |
| INTERNAL_ERROR | 500 | Server error |
| SERVICE_UNAVAILABLE | 503 | Service temporarily down |

### Common Errors

#### Invalid Game ID

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Game not found",
    "details": {
      "game_id": 999
    }
  }
}
```

#### Unauthorized Access

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "You are not a player in this game"
  }
}
```

#### Rate Limit Exceeded

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests. Please try again in 60 seconds.",
    "retry_after": 60
  }
}
```

---

## Rate Limiting

### Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| GET /messages | 100 requests | 1 minute |
| POST /messages | 30 requests | 1 minute |
| POST /request-suggestion | 10 requests | 5 minutes |
| POST /what-if | 5 requests | 5 minutes |

### Headers

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1705238400
```

### Handling Rate Limits

```javascript
try {
  const response = await fetch('/api/v1/games/1/chat/messages', {
    method: 'POST',
    body: JSON.stringify(message)
  });

  if (response.status === 429) {
    const retryAfter = response.headers.get('Retry-After');
    console.log(`Rate limited. Retry after ${retryAfter}s`);
  }
} catch (error) {
  console.error('Request failed:', error);
}
```

---

## Examples

### Complete Chat Flow

```typescript
import { io } from 'socket.io-client';
import axios from 'axios';

// 1. Connect to WebSocket
const socket = io('wss://api.beergame.com', {
  auth: { token: 'Bearer <token>' }
});

// 2. Join game chat
socket.emit('join_game', { game_id: 1 });

// 3. Listen for messages
socket.on('chat:new_message', (message) => {
  console.log('New message:', message);
  displayMessage(message);
});

// 4. Listen for agent typing
socket.on('chat:agent_typing', ({ agent_id, is_typing }) => {
  showTypingIndicator(agent_id, is_typing);
});

// 5. Send message
function sendMessage(content: string) {
  socket.emit('chat:send_message', {
    game_id: 1,
    sender_id: 'player:1',
    sender_name: 'John',
    sender_type: 'player',
    content,
    type: 'text'
  });
}

// 6. Request suggestion
async function requestSuggestion() {
  const response = await axios.post(
    '/api/v1/games/1/chat/request-suggestion',
    { context: {} }
  );

  return response.data;
}

// 7. Accept suggestion
async function acceptSuggestion(suggestionId: string) {
  await axios.put(
    `/api/v1/games/1/chat/suggestions/${suggestionId}/accept`
  );
}

// 8. Cleanup
function cleanup() {
  socket.emit('leave_game', { game_id: 1 });
  socket.disconnect();
}
```

### React Integration

```typescript
import React, { useEffect, useState } from 'react';
import { useAppDispatch } from './store';
import { addMessage } from './store/slices/chatSlice';
import { chatService } from './services/chat';

function ChatComponent({ gameId }: { gameId: number }) {
  const dispatch = useAppDispatch();
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  useEffect(() => {
    // Initialize chat service
    chatService.initialize();
    chatService.joinGameChat(gameId);

    // Listen for new messages
    const handleMessage = (message: ChatMessage) => {
      dispatch(addMessage(message));
    };

    // Subscribe to WebSocket events
    socket.on('chat:new_message', handleMessage);

    return () => {
      chatService.leaveGameChat(gameId);
      socket.off('chat:new_message', handleMessage);
    };
  }, [gameId, dispatch]);

  const handleSend = (content: string) => {
    chatService.sendMessage({
      gameId,
      senderId: 'player:1',
      senderName: 'You',
      senderType: 'player',
      content,
      type: 'text'
    });
  };

  return (
    <div>
      <MessageList messages={messages} />
      <ChatInput onSend={handleSend} />
    </div>
  );
}
```

---

## Webhooks (Optional)

### Configure Webhook

```http
POST /api/v1/games/{game_id}/webhooks
Content-Type: application/json

{
  "url": "https://your-app.com/webhooks/chat",
  "events": [
    "chat.message.created",
    "chat.suggestion.ready"
  ],
  "secret": "your_webhook_secret"
}
```

### Webhook Payload

```json
{
  "event": "chat.message.created",
  "timestamp": "2026-01-14T12:00:00Z",
  "game_id": 1,
  "data": {
    "message": { /* ChatMessage object */ }
  },
  "signature": "sha256=..."
}
```

---

## SDK Support

### JavaScript/TypeScript

```bash
npm install @beergame/chat-sdk
```

```typescript
import { ChatClient } from '@beergame/chat-sdk';

const client = new ChatClient({
  apiKey: 'your_api_key',
  baseURL: 'https://api.beergame.com'
});

await client.connect(gameId);
const messages = await client.getMessages();
await client.sendMessage('Hello!');
```

### Python

```bash
pip install beergame-chat
```

```python
from beergame import ChatClient

client = ChatClient(api_key='your_api_key')
client.connect(game_id=1)

messages = client.get_messages()
client.send_message('Hello!')
```

---

## Testing

### Mock Server

```bash
npm install @beergame/chat-mock-server
```

```typescript
import { MockChatServer } from '@beergame/chat-mock-server';

const server = new MockChatServer();
server.start(8000);

// Use http://localhost:8000 as base URL for testing
```

### Test Data

```typescript
// Mock messages
const mockMessages = [
  {
    id: 'msg_1',
    game_id: 1,
    sender_id: 'agent:wholesaler',
    content: 'Test message',
    type: 'text',
    timestamp: new Date().toISOString(),
    read: false,
    delivered: true
  }
];
```

---

## Changelog

### v1.0.0 (2026-01-14)
- Initial release
- REST API endpoints
- WebSocket events
- Agent suggestions
- What-if analysis

---

## Support

- **Documentation**: https://docs.beergame.com/api
- **GitHub**: https://github.com/beergame/api
- **Email**: api-support@beergame.com
- **Discord**: https://discord.gg/beergame

---

**API Reference v1.0**
**Last Updated**: 2026-01-14

---

*Build amazing A2A experiences!* 🚀📡🤖
