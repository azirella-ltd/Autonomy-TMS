# Chat and A2A Collaboration API Documentation

**Phase 7 Sprint 2 - Real-time A2A Collaboration**

This document provides complete API documentation for the chat, agent suggestions, and what-if analysis endpoints.

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Base URLs](#base-urls)
4. [Chat Messages](#chat-messages)
5. [Agent Suggestions](#agent-suggestions)
6. [What-If Analysis](#what-if-analysis)
7. [WebSocket Events](#websocket-events)
8. [Error Handling](#error-handling)
9. [Data Models](#data-models)
10. [Integration Guide](#integration-guide)

---

## Overview

The Chat and A2A (Agent-to-Agent) Collaboration API enables real-time communication between human participants and AI agents in Autonomy. The system supports:

- **Chat Messages**: Text-based communication between players and agents
- **Agent Suggestions**: AI-generated order recommendations with confidence levels
- **What-If Analysis**: Hypothetical scenario modeling for decision support
- **Real-time Updates**: WebSocket broadcasting for live collaboration

### Key Features

- Read receipts and delivery tracking
- Message metadata for extensibility
- Multi-agent suggestion generation
- Confidence scoring for AI recommendations
- Asynchronous what-if analysis processing

---

## Authentication

All endpoints require JWT authentication via Bearer token or HTTP-only cookie.

### Authentication Methods

**Option 1: Cookie-based (Recommended)**
```http
Cookie: autonomy_access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Option 2: Authorization Header**
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Login Endpoint

**POST** `/api/v1/auth/login`

**Request:**
```http
Content-Type: application/x-www-form-urlencoded

username=systemadmin@autonomy.ai&password=Autonomy@2025
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 44,
    "email": "systemadmin@autonomy.ai",
    "username": "systemadmin",
    "role": "SYSTEM_ADMIN"
  }
}
```

**Note:** Token is also set as HTTP-only cookie `autonomy_access_token`.

---

## Base URLs

| Environment | Base URL |
|------------|----------|
| Local Development | `http://localhost:8088/api/v1` |
| Remote Server (HTTP) | `http://172.29.20.187:8088/api/v1` |
| Remote Server (HTTPS) | `https://172.29.20.187:8443/api/v1` |
| Direct Backend | `http://localhost:8000/api/v1` |

---

## Chat Messages

### 1. Get Chat Messages

Retrieve chat messages for a game with pagination and filtering.

**GET** `/games/{game_id}/chat/messages`

**Path Parameters:**
- `game_id` (integer, required): Game ID

**Query Parameters:**
- `since` (datetime, optional): ISO 8601 timestamp - only return messages after this time
- `limit` (integer, optional): Maximum messages to return (1-200, default: 100)
- `offset` (integer, optional): Pagination offset (default: 0)

**Example Request:**
```http
GET /api/v1/games/1041/chat/messages?limit=20&offset=0
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Example Response:**
```json
{
  "messages": [
    {
      "id": 1,
      "game_id": 1041,
      "sender_id": "player:1",
      "sender_name": "Test Player",
      "sender_type": "PLAYER",
      "recipient_id": null,
      "content": "Hello agents! Can you help me with my order?",
      "type": "TEXT",
      "message_metadata": null,
      "read": true,
      "delivered": true,
      "created_at": "2026-01-14T16:05:20",
      "read_at": "2026-01-14T16:06:15"
    },
    {
      "id": 2,
      "game_id": 1041,
      "sender_id": "agent:wholesaler",
      "sender_name": "Wholesaler Agent",
      "sender_type": "AGENT",
      "recipient_id": "player:1",
      "content": "Based on current trends, I recommend ordering 45 units.",
      "type": "SUGGESTION",
      "message_metadata": {
        "suggestion_id": 12,
        "confidence": 0.85
      },
      "read": false,
      "delivered": true,
      "created_at": "2026-01-14T16:05:45",
      "read_at": null
    }
  ],
  "total": 2,
  "has_more": false
}
```

**Response Fields:**
- `messages`: Array of chat message objects
- `total`: Total count of messages matching filters
- `has_more`: Boolean indicating if more messages are available

---

### 2. Send Chat Message

Send a new chat message in a game.

**POST** `/games/{game_id}/chat/messages`

**Path Parameters:**
- `game_id` (integer, required): Game ID

**Request Body:**
```json
{
  "sender_id": "player:1",
  "sender_name": "Test Player",
  "sender_type": "PLAYER",
  "recipient_id": "agent:wholesaler",
  "content": "What order quantity do you suggest?",
  "type": "QUESTION",
  "message_metadata": {
    "context": "round_5",
    "inventory": 23
  }
}
```

**Request Fields:**
- `sender_id` (string, required): Sender ID format: `"player:{id}"` or `"agent:{role}"`
- `sender_name` (string, required): Display name (1-100 characters)
- `sender_type` (enum, required): `"PLAYER"` or `"AGENT"`
- `recipient_id` (string, optional): Recipient ID (null for broadcast to all)
- `content` (string, required): Message content (1-2000 characters)
- `type` (enum, required): `"TEXT"`, `"SUGGESTION"`, `"QUESTION"`, or `"ANALYSIS"`
- `message_metadata` (object, optional): Additional JSON metadata

**Example Response:**
```json
{
  "id": 3,
  "game_id": 1041,
  "sender_id": "player:1",
  "sender_name": "Test Player",
  "sender_type": "PLAYER",
  "recipient_id": "agent:wholesaler",
  "content": "What order quantity do you suggest?",
  "type": "QUESTION",
  "message_metadata": {
    "context": "round_5",
    "inventory": 23
  },
  "read": false,
  "delivered": true,
  "created_at": "2026-01-14T16:10:30",
  "read_at": null
}
```

**WebSocket Event Emitted:**
```json
{
  "type": "chat:new_message",
  "data": {
    "id": 3,
    "game_id": 1041,
    "sender_id": "player:1",
    "content": "What order quantity do you suggest?",
    ...
  }
}
```

---

### 3. Mark Messages as Read

Mark multiple messages as read (read receipt).

**PUT** `/games/{game_id}/chat/messages/read`

**Path Parameters:**
- `game_id` (integer, required): Game ID

**Request Body:**
```json
[1, 2, 3]
```

**Example Request:**
```http
PUT /api/v1/games/1041/chat/messages/read
Content-Type: application/json
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

[1, 2, 3]
```

**Example Response:**
```json
{
  "count": 2
}
```

**Response Fields:**
- `count`: Number of messages successfully marked as read (excludes already-read messages)

**WebSocket Event Emitted (per message):**
```json
{
  "type": "chat:message_read",
  "data": {
    "message_id": 1,
    "read_at": "2026-01-14T16:12:00"
  }
}
```

---

## Agent Suggestions

### 4. Get Agent Suggestions

Retrieve agent suggestions for a game.

**GET** `/games/{game_id}/chat/suggestions`

**Path Parameters:**
- `game_id` (integer, required): Game ID

**Query Parameters:**
- `agent_name` (string, optional): Filter by specific agent (e.g., "retailer", "wholesaler")
- `pending_only` (boolean, optional): Only return suggestions not yet accepted/declined (default: false)

**Example Request:**
```http
GET /api/v1/games/1041/chat/suggestions?agent_name=wholesaler&pending_only=true
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Example Response:**
```json
{
  "suggestions": [
    {
      "id": 12,
      "game_id": 1041,
      "round": 5,
      "agent_name": "wholesaler",
      "order_quantity": 45,
      "confidence": 0.85,
      "rationale": "Based on current inventory (12 units) and backlog (5 units), ordering 45 units will help reduce backlog while maintaining optimal stock levels. Recent demand trends show a 15% increase over the past 3 rounds.",
      "context": {
        "current_inventory": 12,
        "current_backlog": 5,
        "recent_demand": [35, 38, 42],
        "forecast_demand": 44
      },
      "accepted": null,
      "player_id": null,
      "created_at": "2026-01-14T16:05:45",
      "decided_at": null
    }
  ],
  "total": 1
}
```

**Response Fields:**
- `suggestions`: Array of agent suggestion objects
- `total`: Total count of suggestions
- `accepted`: `null` (pending), `true` (accepted), or `false` (declined)

---

### 5. Request Agent Suggestion

Request an order recommendation from an AI agent.

**POST** `/games/{game_id}/chat/request-suggestion`

**Path Parameters:**
- `game_id` (integer, required): Game ID

**Query Parameters:**
- `agent_name` (string, required): Agent to request from (e.g., "retailer", "wholesaler", "distributor", "factory")

**Request Body (optional):**
```json
{
  "context": {
    "priority": "minimize_cost",
    "risk_tolerance": "conservative"
  }
}
```

**Example Request:**
```http
POST /api/v1/games/1041/chat/request-suggestion?agent_name=wholesaler
Content-Type: application/json
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

{
  "context": {
    "priority": "minimize_cost"
  }
}
```

**Example Response:**
```json
{
  "id": 13,
  "game_id": 1041,
  "round": 5,
  "agent_name": "wholesaler",
  "order_quantity": 42,
  "confidence": 0.78,
  "rationale": "Based on current inventory (12) and backlog (5), recommend ordering 42 units.",
  "context": {
    "current_inventory": 12,
    "current_backlog": 5,
    "recent_demand": [],
    "forecast_demand": 0
  },
  "accepted": null,
  "player_id": null,
  "created_at": "2026-01-14T16:15:22",
  "decided_at": null
}
```

**WebSocket Events Emitted:**

1. **Typing Indicator (Start):**
```json
{
  "type": "chat:agent_typing",
  "data": {
    "agent_id": "agent:wholesaler",
    "is_typing": true
  }
}
```

2. **Typing Indicator (Stop):**
```json
{
  "type": "chat:agent_typing",
  "data": {
    "agent_id": "agent:wholesaler",
    "is_typing": false
  }
}
```

3. **Suggestion Ready:**
```json
{
  "type": "chat:suggestion_ready",
  "data": {
    "id": 13,
    "order_quantity": 42,
    "confidence": 0.78,
    ...
  }
}
```

**Processing Flow:**
1. Retrieves current game state (inventory, backlog, recent rounds)
2. Calls LLM agent for analysis (Phase 7 Sprint 3) or uses heuristic fallback
3. Generates order recommendation with confidence level (0.0-1.0)
4. Returns suggestion with rationale and context

---

### 6. Accept Agent Suggestion

Accept an agent's order recommendation.

**PUT** `/games/{game_id}/chat/suggestions/{suggestion_id}/accept`

**Path Parameters:**
- `game_id` (integer, required): Game ID
- `suggestion_id` (integer, required): Suggestion ID

**Request Body:**
```json
{
  "player_id": 1
}
```

**Example Response:**
```json
{
  "id": 13,
  "game_id": 1041,
  "round": 5,
  "agent_name": "wholesaler",
  "order_quantity": 42,
  "confidence": 0.78,
  "rationale": "Based on current inventory (12) and backlog (5), recommend ordering 42 units.",
  "context": {
    "current_inventory": 12,
    "current_backlog": 5
  },
  "accepted": true,
  "player_id": 1,
  "created_at": "2026-01-14T16:15:22",
  "decided_at": "2026-01-14T16:16:45"
}
```

**WebSocket Event Emitted:**
```json
{
  "type": "chat:suggestion_accepted",
  "data": {
    "id": 13,
    "accepted": true,
    "player_id": 1,
    "decided_at": "2026-01-14T16:16:45",
    ...
  }
}
```

**Next Steps:**
Frontend should pre-fill the order form with `order_quantity` value (42 units).

---

### 7. Decline Agent Suggestion

Decline an agent's order recommendation.

**PUT** `/games/{game_id}/chat/suggestions/{suggestion_id}/decline`

**Path Parameters:**
- `game_id` (integer, required): Game ID
- `suggestion_id` (integer, required): Suggestion ID

**Request Body:**
```json
{
  "player_id": 1
}
```

**Example Response:**
```json
{
  "id": 13,
  "game_id": 1041,
  "round": 5,
  "agent_name": "wholesaler",
  "order_quantity": 42,
  "confidence": 0.78,
  "rationale": "Based on current inventory (12) and backlog (5), recommend ordering 42 units.",
  "context": {
    "current_inventory": 12,
    "current_backlog": 5
  },
  "accepted": false,
  "player_id": 1,
  "created_at": "2026-01-14T16:15:22",
  "decided_at": "2026-01-14T16:17:30"
}
```

**WebSocket Event Emitted:**
```json
{
  "type": "chat:suggestion_declined",
  "data": {
    "id": 13,
    "accepted": false,
    "player_id": 1,
    "decided_at": "2026-01-14T16:17:30",
    ...
  }
}
```

---

## What-If Analysis

### 8. Run What-If Analysis

Run a hypothetical scenario analysis to model decision impacts.

**POST** `/games/{game_id}/chat/what-if`

**Path Parameters:**
- `game_id` (integer, required): Game ID

**Request Body:**
```json
{
  "player_id": 1,
  "question": "What if I order 50 units instead of 40?",
  "scenario": {
    "order_quantity": 50,
    "current_order": 40
  }
}
```

**Request Fields:**
- `player_id` (integer, required): Player requesting the analysis
- `question` (string, required): Hypothetical question
- `scenario` (object, required): Scenario parameters

**Example Questions:**
- "What if I order 50 units instead of 40?"
- "What happens if demand increases by 20%?"
- "How would reducing my order affect inventory next week?"
- "What if the upstream supplier has a 2-week delay?"

**Example Response:**
```json
{
  "id": 5,
  "game_id": 1041,
  "round": 5,
  "player_id": 1,
  "question": "What if I order 50 units instead of 40?",
  "scenario": {
    "order_quantity": 50,
    "current_order": 40
  },
  "result": null,
  "agent_analysis": null,
  "completed": false,
  "created_at": "2026-01-14T16:20:00",
  "completed_at": null
}
```

**WebSocket Event Emitted (when complete):**
```json
{
  "type": "chat:analysis_complete",
  "data": {
    "id": 5,
    "completed": true,
    "result": {
      "projected_inventory": 62,
      "projected_backlog": 0,
      "projected_cost": 124.50,
      "cost_difference": 12.50
    },
    "agent_analysis": "Ordering 50 units instead of 40 will increase your inventory by 10 units, resulting in a cost increase of $12.50. However, this provides a buffer against demand spikes and reduces backlog risk.",
    "completed_at": "2026-01-14T16:20:15"
  }
}
```

**Note:** Analysis processing is asynchronous. Poll the GET endpoint to check for completion.

---

### 9. Get What-If Analysis

Retrieve a what-if analysis by ID.

**GET** `/games/{game_id}/chat/what-if/{analysis_id}`

**Path Parameters:**
- `game_id` (integer, required): Game ID
- `analysis_id` (integer, required): Analysis ID

**Example Request:**
```http
GET /api/v1/games/1041/chat/what-if/5
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Example Response (Completed):**
```json
{
  "id": 5,
  "game_id": 1041,
  "round": 5,
  "player_id": 1,
  "question": "What if I order 50 units instead of 40?",
  "scenario": {
    "order_quantity": 50,
    "current_order": 40
  },
  "result": {
    "projected_inventory": 62,
    "projected_backlog": 0,
    "projected_cost": 124.50,
    "cost_difference": 12.50,
    "service_level": 0.98
  },
  "agent_analysis": "Ordering 50 units instead of 40 will increase your inventory by 10 units, resulting in a cost increase of $12.50. However, this provides a buffer against demand spikes and reduces backlog risk by maintaining a 98% service level.",
  "completed": true,
  "created_at": "2026-01-14T16:20:00",
  "completed_at": "2026-01-14T16:20:15"
}
```

**Example Response (Pending):**
```json
{
  "id": 5,
  "game_id": 1041,
  "round": 5,
  "player_id": 1,
  "question": "What if I order 50 units instead of 40?",
  "scenario": {
    "order_quantity": 50,
    "current_order": 40
  },
  "result": null,
  "agent_analysis": null,
  "completed": false,
  "created_at": "2026-01-14T16:20:00",
  "completed_at": null
}
```

---

## WebSocket Events

The system broadcasts real-time events to all connected players in a game.

### WebSocket Connection

**URL:** `ws://localhost:8088/ws/{game_id}/{player_id}`

**Example:**
```javascript
const ws = new WebSocket('ws://localhost:8088/ws/1041/1');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Event:', message.type, message.data);
};
```

### Event Types

| Event Type | Description | Trigger |
|-----------|-------------|---------|
| `chat:new_message` | New chat message sent | POST `/messages` |
| `chat:message_read` | Message marked as read | PUT `/messages/read` |
| `chat:agent_typing` | Agent typing indicator | POST `/request-suggestion` |
| `chat:suggestion_ready` | Agent suggestion generated | POST `/request-suggestion` |
| `chat:suggestion_accepted` | Suggestion accepted | PUT `/suggestions/{id}/accept` |
| `chat:suggestion_declined` | Suggestion declined | PUT `/suggestions/{id}/decline` |
| `chat:analysis_complete` | What-if analysis complete | Background processing |

### Example Event Payloads

**chat:new_message**
```json
{
  "type": "chat:new_message",
  "data": {
    "id": 1,
    "game_id": 1041,
    "sender_id": "player:1",
    "sender_name": "Test Player",
    "content": "Hello agents!",
    "type": "TEXT",
    "created_at": "2026-01-14T16:05:20"
  }
}
```

**chat:agent_typing**
```json
{
  "type": "chat:agent_typing",
  "data": {
    "agent_id": "agent:wholesaler",
    "is_typing": true
  }
}
```

**chat:suggestion_ready**
```json
{
  "type": "chat:suggestion_ready",
  "data": {
    "id": 13,
    "agent_name": "wholesaler",
    "order_quantity": 42,
    "confidence": 0.78,
    "rationale": "Based on current inventory..."
  }
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Description | Meaning |
|------|-------------|---------|
| 200 | OK | Request succeeded |
| 201 | Created | Resource created successfully |
| 400 | Bad Request | Invalid request data |
| 401 | Unauthorized | Missing or invalid authentication |
| 404 | Not Found | Resource not found |
| 422 | Unprocessable Entity | Validation error |
| 500 | Internal Server Error | Server-side error |

### Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Common Errors

**401 Unauthorized**
```json
{
  "detail": "Not authenticated"
}
```

**404 Not Found**
```json
{
  "detail": "Analysis 5 not found in game 1041"
}
```

**400 Bad Request**
```json
{
  "detail": "No player found for agent wholesaler in game 1041"
}
```

**422 Validation Error**
```json
{
  "detail": [
    {
      "loc": ["body", "content"],
      "msg": "ensure this value has at least 1 characters",
      "type": "value_error.any_str.min_length"
    }
  ]
}
```

---

## Data Models

### ChatMessage

| Field | Type | Description |
|-------|------|-------------|
| id | integer | Unique message ID |
| game_id | integer | Game ID (FK to games.id) |
| sender_id | string | Sender ID format: `"player:{id}"` or `"agent:{role}"` |
| sender_name | string | Display name (1-100 chars) |
| sender_type | enum | `"PLAYER"` or `"AGENT"` |
| recipient_id | string | Recipient ID (null for broadcast) |
| content | string | Message content (1-2000 chars) |
| type | enum | `"TEXT"`, `"SUGGESTION"`, `"QUESTION"`, `"ANALYSIS"` |
| message_metadata | object | Additional JSON metadata |
| read | boolean | Read status |
| delivered | boolean | Delivery status |
| created_at | datetime | ISO 8601 timestamp |
| read_at | datetime | ISO 8601 timestamp (null if unread) |

### AgentSuggestion

| Field | Type | Description |
|-------|------|-------------|
| id | integer | Unique suggestion ID |
| game_id | integer | Game ID (FK to games.id) |
| round | integer | Game round number |
| agent_name | string | Agent name (retailer, wholesaler, etc.) |
| order_quantity | integer | Recommended order quantity |
| confidence | float | Confidence level (0.0-1.0) |
| rationale | string | Explanation of recommendation |
| context | object | Game state context (inventory, backlog, etc.) |
| accepted | boolean | `null` (pending), `true` (accepted), `false` (declined) |
| player_id | integer | Player who accepted/declined (FK to players.id) |
| created_at | datetime | ISO 8601 timestamp |
| decided_at | datetime | ISO 8601 timestamp (null if pending) |

### WhatIfAnalysis

| Field | Type | Description |
|-------|------|-------------|
| id | integer | Unique analysis ID |
| game_id | integer | Game ID (FK to games.id) |
| round | integer | Game round number |
| player_id | integer | Player requesting analysis (FK to players.id) |
| question | string | Hypothetical question |
| scenario | object | Scenario parameters |
| result | object | Analysis results (null if pending) |
| agent_analysis | string | AI-generated analysis text |
| completed | boolean | Completion status |
| created_at | datetime | ISO 8601 timestamp |
| completed_at | datetime | ISO 8601 timestamp (null if pending) |

---

## Integration Guide

### Frontend Integration Steps

#### 1. Authentication Setup

```javascript
// Login
const response = await fetch('/api/v1/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: 'username=user@example.com&password=password123',
  credentials: 'include', // Important: Include cookies
});

const data = await response.json();
console.log('Logged in:', data.user);
```

#### 2. WebSocket Connection

```javascript
// Connect to game WebSocket
const gameId = 1041;
const playerId = 1;
const ws = new WebSocket(`ws://localhost:8088/ws/${gameId}/${playerId}`);

ws.onopen = () => {
  console.log('Connected to game', gameId);
};

ws.onmessage = (event) => {
  const { type, data } = JSON.parse(event.data);

  switch (type) {
    case 'chat:new_message':
      addMessageToUI(data);
      break;
    case 'chat:agent_typing':
      showTypingIndicator(data.agent_id, data.is_typing);
      break;
    case 'chat:suggestion_ready':
      showSuggestion(data);
      break;
    case 'chat:analysis_complete':
      showAnalysisResult(data);
      break;
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Disconnected from game');
};
```

#### 3. Sending Messages

```javascript
async function sendMessage(gameId, content) {
  const response = await fetch(`/api/v1/games/${gameId}/chat/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      sender_id: 'player:1',
      sender_name: 'John Doe',
      sender_type: 'PLAYER',
      content: content,
      type: 'TEXT',
    }),
  });

  if (!response.ok) {
    throw new Error('Failed to send message');
  }

  const message = await response.json();
  console.log('Message sent:', message.id);
  return message;
}
```

#### 4. Loading Messages

```javascript
async function loadMessages(gameId, limit = 50) {
  const response = await fetch(
    `/api/v1/games/${gameId}/chat/messages?limit=${limit}`,
    { credentials: 'include' }
  );

  if (!response.ok) {
    throw new Error('Failed to load messages');
  }

  const { messages, total, has_more } = await response.json();
  console.log(`Loaded ${messages.length} of ${total} messages`);
  return { messages, total, has_more };
}
```

#### 5. Requesting Agent Suggestions

```javascript
async function requestSuggestion(gameId, agentName) {
  const response = await fetch(
    `/api/v1/games/${gameId}/chat/request-suggestion?agent_name=${agentName}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ context: {} }),
    }
  );

  if (!response.ok) {
    throw new Error('Failed to request suggestion');
  }

  const suggestion = await response.json();
  console.log('Suggestion:', suggestion.order_quantity, 'units');
  console.log('Confidence:', (suggestion.confidence * 100).toFixed(0) + '%');
  return suggestion;
}
```

#### 6. Accepting/Declining Suggestions

```javascript
async function acceptSuggestion(gameId, suggestionId, playerId) {
  const response = await fetch(
    `/api/v1/games/${gameId}/chat/suggestions/${suggestionId}/accept`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ player_id: playerId }),
    }
  );

  if (!response.ok) {
    throw new Error('Failed to accept suggestion');
  }

  const suggestion = await response.json();
  // Pre-fill order form with suggestion.order_quantity
  document.getElementById('order-input').value = suggestion.order_quantity;
  return suggestion;
}

async function declineSuggestion(gameId, suggestionId, playerId) {
  const response = await fetch(
    `/api/v1/games/${gameId}/chat/suggestions/${suggestionId}/decline`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ player_id: playerId }),
    }
  );

  if (!response.ok) {
    throw new Error('Failed to decline suggestion');
  }

  return await response.json();
}
```

#### 7. Running What-If Analysis

```javascript
async function runWhatIfAnalysis(gameId, playerId, question, scenario) {
  const response = await fetch(
    `/api/v1/games/${gameId}/chat/what-if`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        player_id: playerId,
        question: question,
        scenario: scenario,
      }),
    }
  );

  if (!response.ok) {
    throw new Error('Failed to create analysis');
  }

  const analysis = await response.json();
  console.log('Analysis created:', analysis.id);

  // Poll for completion or wait for WebSocket event
  return analysis;
}

async function pollAnalysis(gameId, analysisId) {
  const response = await fetch(
    `/api/v1/games/${gameId}/chat/what-if/${analysisId}`,
    { credentials: 'include' }
  );

  if (!response.ok) {
    throw new Error('Failed to get analysis');
  }

  const analysis = await response.json();

  if (analysis.completed) {
    console.log('Analysis complete!');
    console.log('Result:', analysis.result);
    console.log('Agent analysis:', analysis.agent_analysis);
  } else {
    console.log('Analysis still processing...');
  }

  return analysis;
}
```

#### 8. Mark Messages as Read

```javascript
async function markMessagesRead(gameId, messageIds) {
  const response = await fetch(
    `/api/v1/games/${gameId}/chat/messages/read`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(messageIds),
    }
  );

  if (!response.ok) {
    throw new Error('Failed to mark messages as read');
  }

  const { count } = await response.json();
  console.log(`Marked ${count} messages as read`);
  return count;
}
```

### React Component Example

```jsx
import React, { useState, useEffect, useRef } from 'react';

function ChatPanel({ gameId, playerId }) {
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const ws = useRef(null);

  useEffect(() => {
    // Load initial messages
    loadMessages();

    // Connect WebSocket
    ws.current = new WebSocket(`ws://localhost:8088/ws/${gameId}/${playerId}`);

    ws.current.onmessage = (event) => {
      const { type, data } = JSON.parse(event.data);

      if (type === 'chat:new_message') {
        setMessages(prev => [...prev, data]);
      } else if (type === 'chat:suggestion_ready') {
        setSuggestions(prev => [...prev, data]);
      }
    };

    return () => {
      ws.current?.close();
    };
  }, [gameId, playerId]);

  async function loadMessages() {
    const response = await fetch(`/api/v1/games/${gameId}/chat/messages?limit=50`, {
      credentials: 'include',
    });
    const { messages } = await response.json();
    setMessages(messages);
  }

  async function sendMessage() {
    if (!inputText.trim()) return;

    await fetch(`/api/v1/games/${gameId}/chat/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        sender_id: `player:${playerId}`,
        sender_name: 'Player',
        sender_type: 'PLAYER',
        content: inputText,
        type: 'TEXT',
      }),
    });

    setInputText('');
  }

  async function requestSuggestion(agentName) {
    await fetch(`/api/v1/games/${gameId}/chat/request-suggestion?agent_name=${agentName}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ context: {} }),
    });
  }

  return (
    <div className="chat-panel">
      <div className="messages">
        {messages.map(msg => (
          <div key={msg.id} className={`message ${msg.sender_type.toLowerCase()}`}>
            <strong>{msg.sender_name}:</strong> {msg.content}
          </div>
        ))}
      </div>

      <div className="suggestions">
        {suggestions.map(sug => (
          <div key={sug.id} className="suggestion">
            <strong>{sug.agent_name}</strong> suggests ordering {sug.order_quantity} units
            <span className="confidence">({(sug.confidence * 100).toFixed(0)}% confidence)</span>
            <button onClick={() => acceptSuggestion(gameId, sug.id, playerId)}>Accept</button>
          </div>
        ))}
      </div>

      <div className="input-area">
        <input
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="Type a message..."
        />
        <button onClick={sendMessage}>Send</button>
        <button onClick={() => requestSuggestion('wholesaler')}>Get Suggestion</button>
      </div>
    </div>
  );
}

export default ChatPanel;
```

---

## Testing

### Manual Testing with cURL

#### Send Message
```bash
curl -X POST http://localhost:8088/api/v1/games/1041/chat/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "sender_id": "player:1",
    "sender_name": "Test Player",
    "sender_type": "PLAYER",
    "content": "Hello agents!",
    "type": "TEXT"
  }'
```

#### Get Messages
```bash
curl http://localhost:8088/api/v1/games/1041/chat/messages?limit=20 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### Request Suggestion
```bash
curl -X POST "http://localhost:8088/api/v1/games/1041/chat/request-suggestion?agent_name=wholesaler" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"context": {}}'
```

### Test Script

Run the comprehensive test suite:

```bash
cd backend
python scripts/test_chat_api.py
```

---

## Performance Considerations

### Pagination

Always use pagination for message retrieval to avoid loading thousands of messages:

```javascript
// Load 50 messages at a time
const { messages, has_more } = await loadMessages(gameId, limit=50, offset=0);

if (has_more) {
  // Load next page
  const next = await loadMessages(gameId, limit=50, offset=50);
}
```

### WebSocket Best Practices

1. **Reconnection Logic**: Implement exponential backoff for reconnection
2. **Heartbeat**: Send periodic ping/pong to keep connection alive
3. **Event Filtering**: Only subscribe to events for your game
4. **Batching**: Batch read receipts instead of marking each message individually

### Caching

- Cache message lists client-side
- Invalidate cache on `chat:new_message` event
- Cache suggestions for current round
- Don't cache what-if analysis results (one-time use)

---

## Security Considerations

### Authentication

- All endpoints require valid JWT token
- Tokens expire after 24 hours (configurable)
- Use HTTP-only cookies in production (CSRF protection)

### Authorization

- Users can only access games they're participating in
- Validate `game_id` permissions on every request
- Agent suggestions restricted to valid agent roles

### Input Validation

- Message content limited to 2000 characters
- Sender/recipient IDs validated against game participants
- Enum values validated (message type, sender type)

### Rate Limiting

Consider implementing rate limits:
- Messages: 10 per minute per user
- Suggestions: 5 per minute per agent
- What-if analysis: 3 per minute per user

---

## Troubleshooting

### Common Issues

#### Issue: 401 Unauthorized
**Solution:** Ensure token is included in request (cookie or Authorization header)

#### Issue: 404 on chat endpoints
**Solution:** Verify backend is running and chat router is registered in main.py

#### Issue: WebSocket connection fails
**Solution:** Check game_id and player_id are valid, ensure WebSocket URL is correct

#### Issue: Suggestion returns 400 "No player found"
**Solution:** Ensure game has a player with the specified agent role

#### Issue: Messages not updating in real-time
**Solution:** Verify WebSocket connection is established and listening for events

---

## Next Steps

### Phase 7 Sprint 3: LLM Integration

Replace heuristic suggestion generation with LLM-powered analysis:

1. Integrate OpenAI API or Claude API
2. Build prompt templates with game context
3. Parse LLM responses into structured suggestions
4. Implement confidence scoring based on LLM certainty
5. Add what-if analysis processing with LLM reasoning

### Future Enhancements

- **Message Threading**: Group related messages
- **Attachments**: Support images/charts in messages
- **Agent Personas**: Different agent personalities and communication styles
- **Historical Analysis**: Compare agent recommendations vs. actual outcomes
- **Multi-language Support**: Translate messages and suggestions
- **Voice Input**: Voice-to-text for mobile users

---

## Support

For issues or questions:

- **Documentation**: See [CLAUDE.md](CLAUDE.md)
- **Backend Code**: [backend/app/api/endpoints/chat.py](backend/app/api/endpoints/chat.py)
- **Service Logic**: [backend/app/services/chat_service.py](backend/app/services/chat_service.py)
- **Database Models**: [backend/app/models/chat.py](backend/app/models/chat.py)
- **Test Script**: [backend/scripts/test_chat_api.py](backend/scripts/test_chat_api.py)

---

**Phase 7 Sprint 2 Complete**
Backend implementation: ✅ 100%
API testing: ✅ Validated
Documentation: ✅ Complete

Ready for frontend integration and LLM enhancement (Sprint 3).
