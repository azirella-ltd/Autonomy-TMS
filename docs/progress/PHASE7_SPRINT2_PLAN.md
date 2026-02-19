# Phase 7 Sprint 2 - Real-time A2A Collaboration

**Sprint**: Phase 7 Sprint 2
**Focus**: Agent-to-Agent (A2A) Real-time Collaboration
**Duration**: 1-2 days
**Status**: 🚀 In Progress

---

## Sprint Goal

Enable real-time chat communication between human players and AI agents during gameplay, allowing agents to provide suggestions, insights, and collaborative decision-making support.

---

## User Stories

### 1. Chat with AI Agents
**As a** player
**I want to** chat with AI agents in my supply chain
**So that** I can get real-time advice and understand their decision-making

**Acceptance Criteria**:
- ✅ Chat interface visible in game detail screen
- ✅ Can send messages to specific agents or broadcast to all
- ✅ Agents respond with contextual advice
- ✅ Chat history persisted and scrollable
- ✅ Unread message indicators

### 2. Agent Suggestions
**As a** player
**I want to** receive proactive suggestions from AI agents
**So that** I can make better decisions

**Acceptance Criteria**:
- ✅ Agents provide order quantity suggestions
- ✅ Suggestions based on current game state
- ✅ Confidence level shown for each suggestion
- ✅ Can accept or decline suggestions
- ✅ Rationale provided for each suggestion

### 3. Collaborative Decisions
**As a** player
**I want to** collaborate with agents on decisions
**So that** we can optimize supply chain performance together

**Acceptance Criteria**:
- ✅ Can ask agents "what if" questions
- ✅ Agents explain their reasoning
- ✅ Visual indicators for agent agreement/disagreement
- ✅ Historical decision tracking

### 4. Real-time Updates
**As a** player
**I want to** see agent activity in real-time
**So that** I know what's happening in the supply chain

**Acceptance Criteria**:
- ✅ Typing indicators when agent is responding
- ✅ Notification badges for new messages
- ✅ Real-time delivery status
- ✅ Read receipts

---

## Technical Architecture

### Data Models

#### ChatMessage
```typescript
interface ChatMessage {
  id: string;
  gameId: number;
  senderId: string;        // 'player:1' or 'agent:wholesaler'
  senderName: string;      // Display name
  senderType: 'player' | 'agent';
  recipientId?: string;    // null = broadcast
  content: string;
  type: 'text' | 'suggestion' | 'question' | 'analysis';
  metadata?: {
    suggestion?: {
      orderQuantity: number;
      confidence: number;
      rationale: string;
    };
    analysis?: {
      metric: string;
      value: number;
      trend: 'up' | 'down' | 'stable';
    };
  };
  timestamp: string;
  read: boolean;
  delivered: boolean;
}
```

#### AgentSuggestion
```typescript
interface AgentSuggestion {
  id: string;
  agentName: string;
  orderQuantity: number;
  confidence: number;      // 0-1
  rationale: string;
  context: {
    currentInventory: number;
    currentBacklog: number;
    recentDemand: number[];
    forecastDemand: number;
  };
  accepted?: boolean;
  timestamp: string;
}
```

### WebSocket Events

```typescript
// Client -> Server
'chat:send_message'          // Send message
'chat:mark_read'             // Mark messages as read
'chat:typing'                // Typing indicator
'chat:request_suggestion'    // Request agent suggestion

// Server -> Client
'chat:new_message'           // New message received
'chat:agent_typing'          // Agent is typing
'chat:suggestion_ready'      // Agent suggestion available
'chat:message_delivered'     // Message delivered
'chat:message_read'          // Message read by recipient
```

---

## Component Structure

### Chat Components

```
src/components/chat/
├── ChatContainer.tsx          # Main chat container
├── ChatMessageList.tsx        # Scrollable message list
├── ChatMessage.tsx            # Individual message bubble
├── ChatInput.tsx              # Message input with attachments
├── AgentSuggestionCard.tsx    # Agent suggestion display
├── TypingIndicator.tsx        # "Agent is typing..." indicator
├── AgentAvatar.tsx            # Agent profile picture
└── index.ts                   # Exports
```

### Updated Screens

```
src/screens/Games/
├── GameDetailScreen.tsx       # Add chat panel
└── CollaborativePlayScreen.tsx # New full-screen collaboration view
```

---

## Implementation Plan

### Phase 1: Chat Infrastructure (Day 1 Morning)
1. **Data Models** ✅
   - Define TypeScript interfaces
   - Create Redux slice for chat state
   - Setup WebSocket event handlers

2. **Chat Service** ✅
   - Extend WebSocket service with chat events
   - Message sending/receiving
   - Read receipts and delivery status

3. **Basic Chat UI** ✅
   - ChatContainer component
   - ChatMessageList component
   - ChatMessage component
   - ChatInput component

### Phase 2: Agent Integration (Day 1 Afternoon)
1. **Agent Response System** ✅
   - Backend endpoint for agent chat
   - LLM integration for conversational responses
   - Context-aware suggestion generation

2. **Suggestion UI** ✅
   - AgentSuggestionCard component
   - Accept/Decline actions
   - Confidence visualization

3. **Real-time Indicators** ✅
   - Typing indicator
   - Unread badges
   - Online/offline status

### Phase 3: Collaborative Features (Day 2 Morning)
1. **What-If Analysis** ✅
   - Question parsing
   - Scenario simulation
   - Results visualization

2. **Decision Tracking** ✅
   - History of agent suggestions
   - Acceptance rate tracking
   - Performance impact analysis

3. **Multi-Agent Coordination** ✅
   - Broadcast messages to all agents
   - Agent agreement visualization
   - Consensus building UI

### Phase 4: Polish & Testing (Day 2 Afternoon)
1. **UI Refinements** ✅
   - Animations and transitions
   - Accessibility labels
   - Dark mode support

2. **Testing** ✅
   - Unit tests for chat components
   - Integration tests for WebSocket
   - E2E tests for full flow

3. **Documentation** ✅
   - A2A collaboration guide
   - API documentation
   - User guide

---

## UI/UX Design

### Chat Panel Layout

```
┌─────────────────────────────────────┐
│ Game Detail Screen                  │
├─────────────────────────────────────┤
│                                     │
│  Inventory & Orders                 │
│  ┌─────────────────────────────┐   │
│  │ Current Inventory: 50       │   │
│  │ Backlog: 10                 │   │
│  │ Last Order: 30              │   │
│  └─────────────────────────────┘   │
│                                     │
│  ┌─ Chat ──────────────────────┐   │
│  │ [💬 3 new messages]         │   │
│  │                             │   │
│  │ 🤖 Wholesaler Agent:        │   │
│  │ "I recommend ordering 45    │   │
│  │  units. Here's why..."      │   │
│  │  ┌─────────────────────┐   │   │
│  │  │ Order: 45           │   │   │
│  │  │ Confidence: 85%     │   │   │
│  │  │ [Accept] [Decline]  │   │   │
│  │  └─────────────────────┘   │   │
│  │                             │   │
│  │ You:                        │   │
│  │ "Why 45 instead of 40?"     │   │
│  │                             │   │
│  │ 🤖 Wholesaler Agent is      │   │
│  │    typing...                │   │
│  │                             │   │
│  │ [Type a message...    Send] │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

### Agent Suggestion Card

```
┌─────────────────────────────────┐
│ 🤖 Wholesaler Agent Suggestion  │
├─────────────────────────────────┤
│ Recommended Order: 45 units     │
│                                 │
│ Confidence: ████████░░ 85%      │
│                                 │
│ Rationale:                      │
│ • Recent demand trending up     │
│ • Low current inventory (50)    │
│ • Avoid backlog increase        │
│ • GNN forecast: 48 units        │
│                                 │
│ Context:                        │
│ • Avg recent demand: 42         │
│ • Current pipeline: 20          │
│ • Safety stock target: 60       │
│                                 │
│ [✓ Accept Suggestion]           │
│ [✗ Decline]                     │
└─────────────────────────────────┘
```

---

## Backend Requirements

### API Endpoints

```typescript
// Chat endpoints
POST   /api/v1/games/:id/chat/messages
GET    /api/v1/games/:id/chat/messages?since=timestamp
PUT    /api/v1/games/:id/chat/messages/:messageId/read
POST   /api/v1/games/:id/chat/request-suggestion
GET    /api/v1/games/:id/chat/suggestions

// What-if analysis
POST   /api/v1/games/:id/chat/what-if
  Body: { question: string, scenario: object }
  Response: { answer: string, analysis: object }
```

### Database Schema

```sql
-- Chat messages table
CREATE TABLE chat_messages (
  id SERIAL PRIMARY KEY,
  game_id INTEGER REFERENCES games(id),
  sender_id VARCHAR(50),
  sender_name VARCHAR(100),
  sender_type VARCHAR(10),
  recipient_id VARCHAR(50),
  content TEXT,
  message_type VARCHAR(20),
  metadata JSONB,
  timestamp TIMESTAMP DEFAULT NOW(),
  read BOOLEAN DEFAULT FALSE,
  delivered BOOLEAN DEFAULT FALSE
);

-- Agent suggestions table
CREATE TABLE agent_suggestions (
  id SERIAL PRIMARY KEY,
  game_id INTEGER REFERENCES games(id),
  round INTEGER,
  agent_name VARCHAR(100),
  order_quantity INTEGER,
  confidence DECIMAL(3,2),
  rationale TEXT,
  context JSONB,
  accepted BOOLEAN,
  timestamp TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_chat_messages_game_id ON chat_messages(game_id);
CREATE INDEX idx_chat_messages_timestamp ON chat_messages(timestamp);
CREATE INDEX idx_agent_suggestions_game_id ON agent_suggestions(game_id);
```

---

## Redux State

```typescript
interface ChatState {
  messages: Record<number, ChatMessage[]>;  // gameId -> messages
  unreadCounts: Record<number, number>;     // gameId -> count
  typingIndicators: Record<string, boolean>; // agentId -> isTyping
  suggestions: Record<number, AgentSuggestion[]>; // gameId -> suggestions
  loading: boolean;
  error: string | null;
}
```

---

## Testing Strategy

### Unit Tests
- Chat message rendering
- Suggestion card interactions
- Message parsing and formatting
- Read receipt logic

### Integration Tests
- WebSocket message flow
- Agent response generation
- Suggestion acceptance workflow
- What-if analysis

### E2E Tests
- Complete chat conversation
- Accept agent suggestion
- Broadcast to multiple agents
- Real-time synchronization

---

## Success Metrics

### Functionality
- ✅ Chat messages send/receive with <1s latency
- ✅ Agent responses generated in <3s
- ✅ Suggestions show 70%+ confidence
- ✅ What-if analysis completes in <5s

### UX
- ✅ Chat interface intuitive (no help needed)
- ✅ Agent suggestions helpful (>60% acceptance rate)
- ✅ Real-time indicators clear
- ✅ Mobile-optimized (touch targets, scrolling)

### Performance
- ✅ Smooth scrolling (60fps)
- ✅ No memory leaks
- ✅ Handles 100+ messages
- ✅ Minimal battery impact

---

## Risk Assessment

### Technical Risks
| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| WebSocket instability | High | Medium | Implement reconnection logic |
| LLM latency | Medium | High | Show typing indicator, cache responses |
| Message ordering | Medium | Low | Use timestamp + sequence number |
| Mobile keyboard overlap | Low | Medium | KeyboardAvoidingView |

### UX Risks
| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Chat overwhelming | Medium | High | Collapsible panel, filters |
| Agent too chatty | Low | Medium | Rate limiting, summary mode |
| Suggestion fatigue | Low | Medium | Only suggest when helpful |

---

## Dependencies

### External Libraries
- Already installed:
  - socket.io-client (WebSocket)
  - @react-native-firebase/messaging (notifications)
  - react-native-reanimated (animations)

### Backend Changes Required
- Add chat message endpoints
- Integrate LLM for agent responses
- Add suggestion generation logic
- Add what-if analysis engine

---

## Documentation Deliverables

1. **A2A_COLLABORATION_GUIDE.md** - User guide for chat features
2. **A2A_API_REFERENCE.md** - API documentation for chat endpoints
3. **A2A_ARCHITECTURE.md** - Technical architecture document
4. **PHASE7_SPRINT2_COMPLETE.md** - Sprint completion summary

---

## Out of Scope

- Voice chat
- Video chat
- File attachments (images, documents)
- Message editing/deletion
- Chat with other human players (player-to-player)
- Message encryption
- Group chat rooms

---

## Future Enhancements (Sprint 3+)

- Message reactions (👍, ❤️, etc.)
- Rich text formatting
- Code snippet support
- Chart sharing in chat
- Chat search functionality
- Message threads
- Scheduled messages
- Chat bots for tutorials

---

## Sprint Timeline

### Day 1
- **Morning**: Chat infrastructure + basic UI
- **Afternoon**: Agent integration + suggestions

### Day 2
- **Morning**: Collaborative features + what-if
- **Afternoon**: Polish, testing, documentation

**Estimated Completion**: 2026-01-15 EOD

---

## Getting Started

```bash
# Start backend (if not running)
cd backend
uvicorn main:app --reload

# Start mobile app
cd mobile
npm start

# Run tests
npm test

# Open in simulator
npm run ios     # iOS
npm run android # Android
```

---

**Sprint Status**: 🚀 In Progress
**Progress**: 0% (Planning Complete)
**Next**: Implement chat data models and Redux slice

---

*Let's build amazing A2A collaboration!* 🤖💬🚀
