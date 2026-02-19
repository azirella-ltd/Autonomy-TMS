# Phase 7 Sprint 2 - Integration & Deployment Guide

**Date**: 2026-01-14
**Sprint**: Phase 7 Sprint 2 - Real-time A2A Collaboration
**Status**: Ready for Integration & Testing

---

## Overview

This guide walks through integrating the frontend mobile app with the backend API, running tests, and deploying the A2A collaboration system to production.

---

## Prerequisites

### Backend Requirements
- Docker & Docker Compose
- Python 3.10+
- MariaDB 10.11+
- Redis (for WebSocket sessions)

### Frontend Requirements
- Node.js 18+
- React Native CLI
- iOS Simulator (Mac) or Android Emulator

### Development Tools
- Git
- curl or Postman (for API testing)
- wscat (for WebSocket testing)

---

## Step-by-Step Integration

### Phase 1: Backend Setup (30 minutes)

#### 1.1 Start Backend Services

```bash
cd /home/trevor/Projects/The_Beer_Game

# Start all services (proxy, backend, database, frontend)
make up

# Or start with GPU support
make up FORCE_GPU=1
```

**Expected Output:**
```
✓ Database started
✓ Backend started on http://localhost:8000
✓ Frontend started on http://localhost:3000
✓ Proxy started on http://localhost:8088
```

#### 1.2 Run Database Migration

```bash
# Apply chat tables migration
docker compose exec backend alembic upgrade head
```

**Expected Output:**
```
INFO  [alembic.runtime.migration] Running upgrade 20260113_performance_indexes -> 20260114_chat, Create chat and A2A collaboration tables
```

**Verify Tables Created:**
```bash
docker compose exec db mysql -u beer_user -pbeer_password beer_game -e "SHOW TABLES LIKE '%chat%';"
```

**Expected Output:**
```
+----------------------------+
| Tables_in_beer_game (chat) |
+----------------------------+
| chat_messages              |
| agent_suggestions          |
| what_if_analyses           |
+----------------------------+
```

#### 1.3 Verify Backend API

```bash
# Check API is running
curl http://localhost:8088/api/v1/health

# View API documentation
open http://localhost:8000/docs
```

**Look for:**
- New "chat" tag in Swagger UI
- 8 chat endpoints listed

#### 1.4 Test Authentication

```bash
# Login to get access token
curl -X POST http://localhost:8088/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "systemadmin@autonomy.ai",
    "password": "Autonomy@2025"
  }' | jq -r '.access_token'
```

**Save the token:**
```bash
export TOKEN="eyJ0eXAiOiJKV1QiLCJhbGc..."
```

---

### Phase 2: Backend Testing (20 minutes)

#### 2.1 Run Automated Test Script

```bash
cd backend
python scripts/test_chat_api.py
```

**Expected Output:**
```
============================================================
CHAT API TEST SUITE
Phase 7 Sprint 2 - A2A Collaboration
============================================================

=== Logging in ===
✓ Logged in successfully

=== Getting first game ===
✓ Using game ID: 5
  Game: Test Game

=== Testing send message ===
✓ Message sent successfully
  Message ID: 1
  Content: Hello agents! Can you help me with my order?
  Created at: 2026-01-14T13:45:00Z

=== Testing get messages ===
✓ Retrieved messages successfully
  Total messages: 1
  Returned: 1
  Has more: False

  Latest message:
    From: Test Player (player)
    Content: Hello agents! Can you help me with my order?...
    Read: False

=== Testing mark messages as read ===
✓ Marked 1 messages as read

=== Testing request suggestion ===
✓ Suggestion generated successfully
  Suggestion ID: 1
  Agent: wholesaler
  Order quantity: 45 units
  Confidence: 70.0%
  Rationale: Based on current inventory (12) and backlog (8), recommend ordering 45 units.

  Context:
    Current inventory: 12
    Current backlog: 8

=== Testing get suggestions ===
✓ Retrieved suggestions successfully
  Total suggestions: 1

  Suggestion 1:
    Agent: wholesaler
    Order: 45 units
    Confidence: 70.0%
    Status: Pending

=== Testing accept suggestion ===
✓ Suggestion accepted successfully
  Suggestion ID: 1
  Accepted: True
  Decided at: 2026-01-14T13:46:00Z

=== Testing request suggestion ===
✓ Suggestion generated successfully
  Suggestion ID: 2
  Agent: wholesaler
  Order quantity: 45 units
  Confidence: 70.0%
  Rationale: Based on current inventory (12) and backlog (8), recommend ordering 45 units.

=== Testing decline suggestion ===
✓ Suggestion declined successfully
  Suggestion ID: 2
  Accepted: False
  Decided at: 2026-01-14T13:46:15Z

=== Testing what-if analysis ===
✓ What-if analysis created successfully
  Analysis ID: 1
  Question: What if I order 50 units instead of 40?
  Completed: False

============================================================
TEST SUITE COMPLETE
============================================================
```

#### 2.2 Manual API Testing

**Send a Message:**
```bash
curl -X POST http://localhost:8088/api/v1/games/5/chat/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sender_id": "player:1",
    "sender_name": "Alice",
    "sender_type": "player",
    "content": "Can you suggest an order quantity?",
    "type": "question"
  }' | jq
```

**Get Messages:**
```bash
curl http://localhost:8088/api/v1/games/5/chat/messages?limit=20 \
  -H "Authorization: Bearer $TOKEN" | jq '.messages[] | {id, sender_name, content, created_at}'
```

**Request Suggestion:**
```bash
curl -X POST "http://localhost:8088/api/v1/games/5/chat/request-suggestion?agent_name=wholesaler" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"context": {}}' | jq
```

**Accept Suggestion:**
```bash
curl -X PUT http://localhost:8088/api/v1/games/5/chat/suggestions/1/accept \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"player_id": 1}' | jq
```

#### 2.3 Test WebSocket Connection

**Install wscat (if needed):**
```bash
npm install -g wscat
```

**Connect to WebSocket:**
```bash
wscat -c "ws://localhost:8000/ws?token=$TOKEN"
```

**Join Game Chat:**
```json
{"type": "chat:join_game", "data": {"game_id": 5}}
```

**Send Typing Indicator:**
```json
{"type": "chat:typing", "data": {"game_id": 5, "is_typing": true}}
```

**Expected Server Messages:**
```json
{"type": "chat:new_message", "data": {...}}
{"type": "chat:agent_typing", "data": {"agent_id": "agent:wholesaler", "is_typing": true}}
{"type": "chat:suggestion_ready", "data": {...}}
```

---

### Phase 3: Frontend Setup (20 minutes)

#### 3.1 Install Mobile Dependencies

```bash
cd mobile
npm install
```

**Verify Dependencies:**
```bash
npm list | grep -E "(redux|socket|paper|navigation)"
```

**Should show:**
- @reduxjs/toolkit
- socket.io-client
- react-native-paper
- @react-navigation/native

#### 3.2 Configure API Endpoint

**Edit `mobile/src/services/api.ts`:**

```typescript
const API_BASE_URL = __DEV__
  ? 'http://localhost:8088/api/v1'  // Development
  : 'https://your-production-domain.com/api/v1';  // Production

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  timeout: 10000,
});
```

#### 3.3 Start Mobile App

**iOS:**
```bash
npm run ios
```

**Android:**
```bash
npm run android
```

**Expo (if using):**
```bash
npm start
```

---

### Phase 4: Frontend Testing (30 minutes)

#### 4.1 Manual UI Testing

**Test Flow 1: Login & Navigate**
1. Launch app
2. Login with systemadmin@autonomy.ai / Autonomy@2025
3. Navigate to Dashboard
4. Tap on a game
5. Verify game detail screen loads

**Test Flow 2: Open Chat**
1. On game detail screen
2. Tap FAB (floating action button with message icon)
3. Verify chat modal opens
4. Verify ChatContainer renders
5. Check for "Request Suggestion" button

**Test Flow 3: Send Message**
1. In chat modal
2. Type "Hello agents!" in ChatInput
3. Tap send button
4. Verify message appears in ChatMessageList
5. Verify message shows sender name
6. Verify timestamp shows "Just now"

**Test Flow 4: Request Suggestion**
1. Tap "Request Suggestion" button (robot icon)
2. Verify typing indicator appears
3. Wait 1-2 seconds
4. Verify AgentSuggestionCard appears
5. Check suggestion shows:
   - Agent emoji (🏭 for wholesaler)
   - Order quantity
   - Confidence bar (color-coded)
   - Rationale text
   - Context metrics (inventory, backlog)

**Test Flow 5: Accept Suggestion**
1. Review suggestion card
2. Tap "Accept Suggestion" button
3. Verify button changes to "Accepted" (green)
4. Verify decided timestamp appears
5. (Future) Verify order form pre-fills with quantity

**Test Flow 6: Decline Suggestion**
1. Request another suggestion
2. Tap "Decline" button
3. Verify button changes to "Declined" (red)
4. Verify decided timestamp appears

**Test Flow 7: Real-time Updates**
1. Open chat on two devices/emulators
2. Send message from device 1
3. Verify message appears on device 2 within 1 second
4. Check typing indicator shows on device 2 when typing on device 1

#### 4.2 Automated Testing (Future)

**Run Unit Tests:**
```bash
cd mobile
npm test
```

**Run Component Tests:**
```bash
npm test -- --testPathPattern=components/chat
```

**Run Integration Tests:**
```bash
npm test -- --testPathPattern=integration
```

---

### Phase 5: Integration Verification (15 minutes)

#### 5.1 End-to-End Workflow

**Complete User Journey:**
1. ✅ Login successful
2. ✅ Navigate to game detail
3. ✅ Open chat modal
4. ✅ Send text message
5. ✅ Message appears in list
6. ✅ Request agent suggestion
7. ✅ Typing indicator shows
8. ✅ Suggestion card renders
9. ✅ Confidence bar displays correctly
10. ✅ Accept suggestion
11. ✅ Suggestion marked as accepted
12. ✅ WebSocket events received

#### 5.2 Performance Check

**Metrics to Verify:**
- Message send latency: <500ms
- WebSocket message receive: <1s
- Suggestion generation: <3s (heuristic), <5s (future LLM)
- UI responsiveness: 60fps scrolling
- Memory usage: <100MB for chat state

**Check Backend Logs:**
```bash
docker compose logs -f backend | grep -E "(chat|suggestion)"
```

**Expected:**
```
INFO: Created chat message 42 in game 5 from Alice
INFO: Created suggestion 10 from wholesaler in game 5: 45 units (70% confidence)
INFO: Player 1 accepted suggestion 10 in game 5
```

#### 5.3 Database Verification

**Check Messages:**
```bash
docker compose exec db mysql -u beer_user -pbeer_password beer_game -e "
  SELECT id, game_id, sender_name, LEFT(content, 50) as content, created_at
  FROM chat_messages
  ORDER BY created_at DESC
  LIMIT 5;
"
```

**Check Suggestions:**
```bash
docker compose exec db mysql -u beer_user -pbeer_password beer_game -e "
  SELECT id, game_id, agent_name, order_quantity, confidence, accepted
  FROM agent_suggestions
  ORDER BY created_at DESC
  LIMIT 5;
"
```

---

## Troubleshooting

### Backend Issues

#### Issue: Migration Fails
**Error:** `alembic.util.exc.CommandError: Can't locate revision identified by '20260113_performance_indexes'`

**Solution:**
```bash
# Check current revision
docker compose exec backend alembic current

# If missing, run all migrations
docker compose exec backend alembic upgrade head

# Or create new migration
docker compose exec backend alembic revision --autogenerate -m "chat_tables"
```

#### Issue: Chat Endpoints Return 404
**Error:** `{"detail": "Not Found"}`

**Solution:**
1. Check router is registered:
   ```bash
   grep -r "chat_router" backend/app/api/
   ```
2. Restart backend:
   ```bash
   docker compose restart backend
   ```
3. Verify logs:
   ```bash
   docker compose logs backend | grep -i "chat"
   ```

#### Issue: WebSocket Not Connecting
**Error:** `WebSocket connection failed`

**Solution:**
1. Check WebSocket endpoint exists:
   ```bash
   curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
     -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: test" \
     http://localhost:8000/ws
   ```
2. Check Redis is running (if using Redis for WebSocket state)
3. Verify CORS settings in backend config

### Frontend Issues

#### Issue: API Calls Return CORS Error
**Error:** `Access-Control-Allow-Origin header is missing`

**Solution:**
Edit `backend/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8088"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### Issue: Chat Modal Not Opening
**Error:** Modal doesn't appear when tapping FAB

**Solution:**
1. Check Redux store has chatReducer:
   ```typescript
   // mobile/src/store/index.ts
   import chatReducer from './slices/chatSlice';
   const rootReducer = combineReducers({
     // ...
     chat: chatReducer,  // Must be present
   });
   ```
2. Verify FAB onPress handler:
   ```typescript
   <FAB onPress={toggleChat} />  // Should call setChatVisible(true)
   ```

#### Issue: Messages Not Appearing
**Error:** Messages sent but not showing in ChatMessageList

**Solution:**
1. Check Redux state:
   ```typescript
   const messages = useAppSelector(state => state.chat.messages[gameId]);
   console.log('Messages:', messages);
   ```
2. Verify WebSocket connection:
   ```typescript
   useEffect(() => {
     chatService.initialize();
     chatService.joinGameChat(gameId);
   }, [gameId]);
   ```
3. Check WebSocket events:
   ```typescript
   websocketService.on('chat:new_message', (data) => {
     console.log('New message received:', data);
   });
   ```

#### Issue: Typing Indicator Stuck
**Error:** Typing indicator doesn't disappear

**Solution:**
1. Check timeout in ChatInput:
   ```typescript
   const typingTimeout = setTimeout(() => {
     chatService.sendTypingIndicator(gameId, false);
   }, 2000);  // Should clear after 2s
   ```
2. Verify cleanup in useEffect:
   ```typescript
   useEffect(() => {
     return () => clearTimeout(typingTimeout);
   }, []);
   ```

---

## Performance Optimization

### Backend Optimizations

#### 1. Add Redis Caching
```python
# backend/app/services/chat_service.py
import redis

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

def get_messages(self, game_id: int, ...):
    # Try cache first
    cache_key = f"chat:messages:{game_id}"
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # Query database
    messages = ...

    # Cache for 5 minutes
    redis_client.setex(cache_key, 300, json.dumps(messages))
    return messages
```

#### 2. Add Database Indexes
```sql
-- Already created in migration, but verify:
CREATE INDEX idx_chat_messages_game_created ON chat_messages(game_id, created_at DESC);
CREATE INDEX idx_agent_suggestions_game_pending ON agent_suggestions(game_id, accepted) WHERE accepted IS NULL;
```

#### 3. Optimize WebSocket Broadcasting
```python
# Only broadcast to game participants
async def broadcast_to_game(self, game_id: int, data: dict):
    room = f"game:{game_id}"
    for connection_id in self.game_rooms.get(room, []):
        await self.send_message(connection_id, data)
```

### Frontend Optimizations

#### 1. Virtualize Long Message Lists
```typescript
// mobile/src/components/chat/ChatMessageList.tsx
import { VirtualizedList } from 'react-native';

<VirtualizedList
  data={messages}
  getItem={(data, index) => data[index]}
  getItemCount={data => data.length}
  keyExtractor={item => item.id.toString()}
  renderItem={({ item }) => <ChatMessage message={item} />}
/>
```

#### 2. Memoize Expensive Components
```typescript
import React, { memo } from 'react';

const ChatMessage = memo(({ message, isCurrentUser }) => {
  // Component logic
}, (prevProps, nextProps) => {
  return prevProps.message.id === nextProps.message.id &&
         prevProps.message.read === nextProps.message.read;
});
```

#### 3. Debounce Typing Indicators
```typescript
import { debounce } from 'lodash';

const sendTypingIndicator = debounce((gameId, isTyping) => {
  chatService.sendTypingIndicator(gameId, isTyping);
}, 500);  // Wait 500ms before sending
```

---

## Production Deployment

### Backend Deployment

#### 1. Environment Configuration

**`.env.production`:**
```env
# Database
MARIADB_HOST=your-db-host.rds.amazonaws.com
MARIADB_DATABASE=beer_game_prod
MARIADB_USER=beer_user_prod
MARIADB_PASSWORD=<strong-password>

# Redis (for WebSocket state)
REDIS_HOST=your-redis-cluster.cache.amazonaws.com
REDIS_PORT=6379

# API
API_BASE_URL=https://api.yourdomain.com
CORS_ORIGINS=https://app.yourdomain.com,https://yourdomain.com

# LLM (Phase 7 Sprint 3)
OPENAI_API_KEY=sk-prod-...
OPENAI_PROJECT=proj_prod_...
```

#### 2. Deploy Backend

**Using Docker:**
```bash
# Build production image
docker build -f backend/Dockerfile.prod -t beer-game-backend:latest backend/

# Push to registry
docker tag beer-game-backend:latest your-registry/beer-game-backend:latest
docker push your-registry/beer-game-backend:latest

# Deploy to ECS/EKS/Cloud Run
kubectl apply -f k8s/backend-deployment.yaml
```

**Using Gunicorn:**
```bash
cd backend
gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
```

#### 3. Run Production Migration

```bash
# On production database
alembic upgrade head
```

### Frontend Deployment

#### 1. Build Mobile App

**iOS:**
```bash
cd mobile/ios
pod install
cd ..
npx react-native run-ios --configuration Release
```

**Android:**
```bash
cd mobile/android
./gradlew assembleRelease
```

#### 2. Configure Production API

**`mobile/.env.production`:**
```env
API_BASE_URL=https://api.yourdomain.com/api/v1
WS_BASE_URL=wss://api.yourdomain.com/ws
```

#### 3. Submit to App Stores

**iOS:**
1. Archive in Xcode
2. Upload to App Store Connect
3. Submit for review

**Android:**
1. Generate signed APK/AAB
2. Upload to Google Play Console
3. Submit for review

---

## Monitoring & Logging

### Backend Monitoring

#### 1. Add Prometheus Metrics

```python
# backend/app/core/metrics.py
from prometheus_client import Counter, Histogram

chat_messages_sent = Counter('chat_messages_sent_total', 'Total chat messages sent')
suggestion_requests = Counter('suggestion_requests_total', 'Total suggestion requests')
suggestion_latency = Histogram('suggestion_latency_seconds', 'Suggestion generation latency')

# In chat_service.py
chat_messages_sent.inc()
with suggestion_latency.time():
    suggestion = self.request_suggestion(...)
```

#### 2. Configure Logging

```python
# backend/app/core/logging_config.py
import logging
import structlog

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = structlog.get_logger()
```

#### 3. Set Up Alerts

**Prometheus Alerts:**
```yaml
groups:
  - name: chat_alerts
    rules:
      - alert: HighChatMessageLatency
        expr: histogram_quantile(0.95, chat_message_latency_seconds) > 2
        for: 5m
        annotations:
          summary: "Chat message latency is high"

      - alert: SuggestionGenerationFailed
        expr: rate(suggestion_errors_total[5m]) > 0.1
        for: 5m
        annotations:
          summary: "Suggestion generation failing"
```

### Frontend Monitoring

#### 1. Add Analytics

```typescript
// mobile/src/services/analytics.ts
import analytics from '@react-native-firebase/analytics';

export const trackChatEvent = (event: string, params: any) => {
  analytics().logEvent(`chat_${event}`, params);
};

// In ChatContainer.tsx
trackChatEvent('message_sent', { gameId, messageLength: content.length });
trackChatEvent('suggestion_requested', { gameId, agentName });
trackChatEvent('suggestion_accepted', { gameId, suggestionId, confidence });
```

#### 2. Error Tracking

```typescript
// mobile/src/services/errorTracking.ts
import Sentry from '@sentry/react-native';

Sentry.init({
  dsn: 'https://your-sentry-dsn',
  environment: __DEV__ ? 'development' : 'production',
});

// In chatSlice.ts
export const sendMessage = createAsyncThunk(
  'chat/sendMessage',
  async (message, { rejectWithValue }) => {
    try {
      const response = await apiClient.sendChatMessage(...);
      return response.data;
    } catch (error) {
      Sentry.captureException(error);
      return rejectWithValue(error.message);
    }
  }
);
```

---

## Success Checklist

### Pre-Deployment
- [ ] All backend tests pass
- [ ] All frontend tests pass
- [ ] Database migration successful
- [ ] WebSocket connection works
- [ ] API endpoints respond correctly
- [ ] Chat messages send/receive
- [ ] Agent suggestions generate
- [ ] Accept/decline suggestions work
- [ ] Typing indicators work
- [ ] Read receipts work

### Deployment
- [ ] Production environment configured
- [ ] Database backup created
- [ ] Migration run on production
- [ ] Backend deployed and healthy
- [ ] Frontend deployed to app stores
- [ ] Monitoring/alerts configured
- [ ] Error tracking enabled

### Post-Deployment
- [ ] Smoke tests pass
- [ ] Performance within SLAs
- [ ] No critical errors in logs
- [ ] User feedback collected
- [ ] Analytics tracking working

---

## Next Phase: LLM Integration (Sprint 3)

**After successful deployment, enhance with:**

1. **Intelligent Suggestions** - Replace heuristic with OpenAI agent
2. **Natural Conversations** - Multi-turn chat with context
3. **What-If Processing** - Async scenario analysis
4. **Agent Personalities** - Different agent strategies and tones
5. **Multi-Agent Coordination** - Agents discuss and reach consensus

**See:** `PHASE7_SPRINT3_PLAN.md` (to be created)

---

## Support & Resources

### Documentation
- [A2A_COLLABORATION_GUIDE.md](mobile/A2A_COLLABORATION_GUIDE.md) - User guide
- [A2A_API_REFERENCE.md](mobile/A2A_API_REFERENCE.md) - Developer API docs
- [PHASE7_SPRINT2_BACKEND_COMPLETE.md](PHASE7_SPRINT2_BACKEND_COMPLETE.md) - Backend docs
- [PHASE7_SPRINT2_SUMMARY.md](PHASE7_SPRINT2_SUMMARY.md) - Sprint summary

### API Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Contact
- Technical Issues: Create GitHub issue
- Questions: Check documentation first
- Emergency: Contact system admin

---

**Ready to integrate and deploy!** 🚀✨

---

*Phase 7 Sprint 2 - Real-time A2A Collaboration Complete* 🤖💬
