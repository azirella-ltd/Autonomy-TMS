# Phase 1 DAG Sequential Execution - Verification Checklist

## Overview
This checklist provides step-by-step verification procedures for testing the Phase 1 DAG Sequential Execution implementation.

**Status**: Ready for Testing ✅
**Implementation Completed**: 2026-01-27
**Backend Lines Added**: ~500
**Frontend Lines Added**: ~900

---

## Pre-Testing Setup

### 1. Environment Check
```bash
# Ensure services are running
make up

# Check backend is healthy
curl http://localhost:8000/health

# Check frontend is accessible
curl http://localhost:8088

# Check database connection
docker compose exec backend python -c "from app.db.session import SessionLocal; db = SessionLocal(); print('DB OK')"
```

### 2. Database Schema Verification
```bash
# Connect to database
docker compose exec db mysql -u beer_user -pbeer_password beer_game

# Verify GameRound has new fields
DESCRIBE game_rounds;
# Should show: current_phase, phase_started_at, fulfillment_completed_at, replenishment_completed_at

# Verify RoundPhase enum values
SHOW COLUMNS FROM game_rounds LIKE 'current_phase';
# Should show: ENUM('FULFILLMENT', 'REPLENISHMENT', 'DECISION', 'COMPLETED')
```

### 3. Code Verification
```bash
# Check backend methods exist
grep -n "_start_round_dag_sequential" backend/app/services/mixed_game_service.py
grep -n "_process_node_fulfillment_decision" backend/app/services/mixed_game_service.py
grep -n "_process_node_replenishment_decision" backend/app/services/mixed_game_service.py
grep -n "_calculate_atp" backend/app/services/mixed_game_service.py

# Check API endpoints exist
grep -n "/fulfillment" backend/app/api/endpoints/mixed_game.py
grep -n "/replenishment" backend/app/api/endpoints/mixed_game.py
grep -n "/atp" backend/app/api/endpoints/mixed_game.py
grep -n "/pipeline" backend/app/api/endpoints/mixed_game.py

# Check frontend components exist
ls -lh frontend/src/components/game/FulfillmentForm.jsx
ls -lh frontend/src/components/game/ReplenishmentForm.jsx
ls -lh frontend/src/components/game/DecisionPhaseIndicator.jsx
```

---

## Backend Testing

### 1. Unit Tests (To Be Implemented)

**File**: `backend/tests/test_dag_sequential_execution.py`

Create and run:
```python
# Test ATP calculation
def test_calculate_atp():
    # Given: Player with inventory=100, committed=30
    # When: Calculate ATP
    # Then: ATP = 70

# Test phase transitions
def test_phase_transition():
    # Given: Round in FULFILLMENT phase, all players submitted
    # When: Check transition
    # Then: Phase = REPLENISHMENT

# Test fulfillment decision
def test_fulfillment_decision():
    # Given: Player with ATP=50, demand=60
    # When: Submit fulfill_qty=40
    # Then: TO created, inventory updated

# Test replenishment decision
def test_replenishment_decision():
    # Given: Player with inventory=20
    # When: Submit order_qty=100
    # Then: TO created with arrival_round = current + lead_time
```

Run tests:
```bash
cd backend
pytest tests/test_dag_sequential_execution.py -v
```

### 2. API Endpoint Testing

**A. Create Test Game**
```bash
# Create game with DAG sequential flag
curl -X POST http://localhost:8000/api/v1/mixed-games/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name": "DAG Test Game",
    "use_dag_sequential": true,
    "max_players": 4,
    "time_bucket": "WEEKLY",
    "max_rounds": 10
  }'

# Save game_id from response
GAME_ID=<your_game_id>
```

**B. Start Game**
```bash
# Start game
curl -X POST http://localhost:8000/api/v1/mixed-games/${GAME_ID}/start \
  -H "Authorization: Bearer YOUR_TOKEN"

# Verify game status
curl http://localhost:8000/api/v1/mixed-games/${GAME_ID} \
  -H "Authorization: Bearer YOUR_TOKEN"

# Check round phase = FULFILLMENT
```

**C. Test ATP Endpoint**
```bash
# Get ATP for player 1
curl http://localhost:8000/api/v1/mixed-games/${GAME_ID}/atp/1 \
  -H "Authorization: Bearer YOUR_TOKEN"

# Expected response:
# {
#   "current_atp": 100,
#   "on_hand": 150,
#   "committed": 50,
#   "in_transit": []
# }
```

**D. Test Fulfillment Endpoint**
```bash
# Submit fulfillment decision
curl -X POST http://localhost:8000/api/v1/mixed-games/${GAME_ID}/rounds/1/fulfillment \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "player_id": 1,
    "fulfill_qty": 45
  }'

# Expected response:
# {
#   "success": true,
#   "transfer_order_id": 1234,
#   "updated_inventory": 105,
#   "updated_atp": 55,
#   "phase": "FULFILLMENT",
#   "awaiting_players": ["wholesaler", "distributor", "factory"]
# }
```

**E. Test Pipeline Endpoint**
```bash
# Get pipeline for player 1
curl http://localhost:8000/api/v1/mixed-games/${GAME_ID}/pipeline/1 \
  -H "Authorization: Bearer YOUR_TOKEN"

# Expected response:
# {
#   "in_transit": [
#     {
#       "transfer_order_id": 1520,
#       "quantity": 150,
#       "origin": "Distributor",
#       "destination": "Wholesaler",
#       "order_round": 14,
#       "arrival_round": 17,
#       "rounds_until_arrival": 3,
#       "status": "IN_TRANSIT"
#     }
#   ]
# }
```

**F. Test Replenishment Endpoint**
```bash
# Submit all fulfillments first (to trigger phase transition)
# ... submit for all players ...

# Submit replenishment decision
curl -X POST http://localhost:8000/api/v1/mixed-games/${GAME_ID}/rounds/1/replenishment \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "player_id": 1,
    "order_qty": 200
  }'

# Expected response:
# {
#   "success": true,
#   "transfer_order_id": 1235,
#   "arrival_round": 3,
#   "phase": "REPLENISHMENT",
#   "round_completed": false
# }
```

---

## Frontend Testing

### 1. Component Visual Testing

**A. FulfillmentForm Component**
1. Navigate to http://localhost:8088
2. Login as systemadmin@autonomy.ai / Autonomy@2025
3. Create new game with `use_dag_sequential=true`
4. Start game
5. Verify FulfillmentForm appears:
   - ✅ Current state section (on-hand, ATP, demand, backlog)
   - ✅ Slider control (0 to max)
   - ✅ TextField input
   - ✅ Quick action buttons (Ship 0, Ship ATP, Ship Full Demand)
   - ✅ Impact preview (inventory after, fill rate, backlog after)
   - ✅ Submit button

**B. ReplenishmentForm Component**
1. Complete fulfillment phase (all players submit)
2. Verify ReplenishmentForm appears:
   - ✅ Current state section (on-hand, pipeline, backlog, avg demand)
   - ✅ Pipeline visibility table (if shipments exist)
   - ✅ Slider control
   - ✅ TextField input
   - ✅ Quick action buttons (Order 0, Order Recommended, Order Double)
   - ✅ Impact preview (inventory position, days of supply, vs recommended)
   - ✅ Submit button

**C. DecisionPhaseIndicator Component**
1. Observe phase indicator at top of game board:
   - ✅ Stepper with 4 phases (Waiting → Fulfillment → Replenishment → Completed)
   - ✅ Current phase highlighted
   - ✅ Phase icon and color coding
   - ✅ Player completion status ("2/4 players submitted")
   - ✅ Progress bar
   - ✅ Elapsed time counter

### 2. WebSocket Integration Testing

**A. Open Browser Console**
```javascript
// In browser dev tools, monitor WebSocket messages
const ws = new WebSocket('ws://localhost:8088/ws/game/YOUR_GAME_ID/');
ws.onmessage = (e) => console.log('WS:', JSON.parse(e.data));
```

**B. Verify Messages**
1. Start game → Expect `round_phase_change` with phase="FULFILLMENT"
2. Submit fulfillment → Expect `fulfillment_completed`
3. All players submit fulfillment → Expect `all_players_ready_for_replenishment`
4. Phase transition → Expect `round_phase_change` with phase="REPLENISHMENT"

### 3. State Management Testing

**A. ATP Data Updates**
1. Observe ATP value in FulfillmentForm
2. Submit fulfillment decision
3. Verify ATP updates immediately (optimistic update)
4. Verify ATP matches server response

**B. Pipeline Data Updates**
1. Place replenishment order
2. Verify pipeline table updates
3. Check arrival_round calculation
4. Verify "rounds until arrival" countdown

**C. Phase Transitions**
1. Observe roundPhase state in React DevTools
2. Submit fulfillment → Verify roundPhase stays "fulfillment"
3. All players submit → Verify roundPhase transitions to "replenishment"
4. All players submit replenishment → Verify roundPhase transitions to "completed"

---

## Integration Testing

### End-to-End 4-Player Game Test

**Setup**:
1. Create game with 4 players (Retailer, Wholesaler, Distributor, Factory)
2. Set `use_dag_sequential=true`
3. Configure weekly time bucket, 10 rounds

**Round 1 Execution**:

1. **Initialize Round**:
   - ✅ GameRound created with current_phase="FULFILLMENT"
   - ✅ phase_started_at timestamp set
   - ✅ WebSocket broadcast: round_phase_change

2. **Fulfillment Phase**:
   - ✅ Retailer sees FulfillmentForm
   - ✅ ATP calculated correctly (inventory - committed)
   - ✅ Retailer submits fulfill_qty=45
   - ✅ TransferOrder created to customer
   - ✅ Retailer inventory updated
   - ✅ WebSocket broadcast: fulfillment_completed
   - ✅ Repeat for Wholesaler, Distributor, Factory

3. **Phase Transition (FULFILLMENT → REPLENISHMENT)**:
   - ✅ All 4 players submitted fulfillment
   - ✅ fulfillment_completed_at timestamp set
   - ✅ current_phase updated to "REPLENISHMENT"
   - ✅ WebSocket broadcast: all_players_ready_for_replenishment
   - ✅ WebSocket broadcast: round_phase_change

4. **Replenishment Phase**:
   - ✅ All players see ReplenishmentForm
   - ✅ Pipeline data fetched (GET /pipeline)
   - ✅ Recommended order calculated (base stock policy)
   - ✅ Retailer submits order_qty=200
   - ✅ TransferOrder created to Wholesaler with arrival_round=3
   - ✅ PlayerRound.order_placed updated
   - ✅ Repeat for Wholesaler, Distributor, Factory

5. **Phase Transition (REPLENISHMENT → COMPLETED)**:
   - ✅ All 4 players submitted replenishment
   - ✅ replenishment_completed_at timestamp set
   - ✅ current_phase updated to "COMPLETED"
   - ✅ WebSocket broadcast: round_completed

6. **Round 2 Initialization**:
   - ✅ Process transfer order arrivals (arrival_round==2)
   - ✅ Update player inventories
   - ✅ Create new GameRound with phase="FULFILLMENT"
   - ✅ Repeat cycle

**Verification**:
```sql
-- Check GameRound records
SELECT round_number, current_phase, phase_started_at,
       fulfillment_completed_at, replenishment_completed_at
FROM game_rounds
WHERE game_id = YOUR_GAME_ID
ORDER BY round_number;

-- Check TransferOrder creation
SELECT id, game_id, order_round, arrival_round, quantity, status
FROM transfer_order
WHERE game_id = YOUR_GAME_ID
ORDER BY order_round, id;

-- Check PlayerRound updates
SELECT player_id, round_number, order_placed, upstream_order_id
FROM player_rounds
WHERE game_id = YOUR_GAME_ID
ORDER BY round_number, player_id;
```

---

## Performance Testing

### 1. ATP Calculation Performance
```python
# backend/tests/test_performance.py
import time

def test_atp_calculation_performance():
    start = time.time()
    atp = game_service._calculate_atp(player)
    elapsed = (time.time() - start) * 1000  # ms
    assert elapsed < 10, f"ATP calculation took {elapsed}ms (target: <10ms)"
```

### 2. Pipeline Query Performance
```python
def test_pipeline_query_performance():
    start = time.time()
    pipeline = db.query(TransferOrder).filter(
        TransferOrder.game_id == game_id,
        TransferOrder.destination_site_id == player.site_id,
        TransferOrder.status == "IN_TRANSIT"
    ).all()
    elapsed = (time.time() - start) * 1000
    assert elapsed < 50, f"Pipeline query took {elapsed}ms (target: <50ms)"
```

### 3. Phase Transition Performance
```python
def test_phase_transition_performance():
    start = time.time()
    game_service._transition_phase(game, round_obj, RoundPhase.REPLENISHMENT)
    elapsed = (time.time() - start) * 1000
    assert elapsed < 100, f"Phase transition took {elapsed}ms (target: <100ms)"
```

### 4. Full Round Performance
```bash
# Time a complete 4-player round
time curl -X POST http://localhost:8000/api/v1/mixed-games/${GAME_ID}/rounds/1/play-round \
  -H "Authorization: Bearer YOUR_TOKEN"

# Target: <5 seconds end-to-end
```

---

## Known Issues & Limitations

### Current Implementation
- ✅ Backend DAG execution logic complete
- ✅ Frontend UI components complete
- ✅ WebSocket integration complete
- ⏳ Unit tests not yet implemented
- ⏳ Integration tests not yet implemented
- ⏳ Performance benchmarks not yet run

### Phase 1 Scope
- ✅ Manual mode (Mode 3) fully implemented
- ⏳ Autonomous mode (Mode 1) - backend complete, needs frontend testing
- ❌ Copilot mode (Mode 2) - deferred to Phase 2

### Known Limitations
1. **Single Product Only**: Multi-product support deferred to Phase 4
2. **Fixed Lead Times**: Stochastic lead times deferred to Phase 5
3. **No Mid-Game Mode Switching**: Agent mode fixed at game creation
4. **Basic Base Stock Policy**: Advanced inventory policies deferred to Phase 3

---

## Success Criteria

### Backend ✅
- [x] RoundPhase enum with 4 states
- [x] GameRound extended with phase tracking fields
- [x] DAG sequential orchestration method implemented
- [x] Fulfillment phase processing implemented
- [x] Replenishment phase processing implemented
- [x] Phase transition logic implemented
- [x] ATP calculation method implemented
- [x] 4 API endpoints functional

### Frontend ✅
- [x] FulfillmentForm component (330+ lines)
- [x] ReplenishmentForm component (330+ lines)
- [x] DecisionPhaseIndicator component (150+ lines)
- [x] GameRoom integration complete
- [x] WebSocket message handlers implemented
- [x] State management for phase/ATP/pipeline
- [x] Conditional rendering (DAG vs legacy)

### Documentation ✅
- [x] DAG_SEQUENTIAL_IMPLEMENTATION.md complete
- [x] HUMAN_GAME_INTERACTION_DESIGN.md updated
- [x] Phase 1 verification checklist created

### Testing ⏳
- [ ] Unit tests passing (>90% coverage)
- [ ] Integration tests passing (4-player game)
- [ ] Performance tests passing (<100ms API responses)
- [ ] Manual testing complete (all scenarios verified)

---

## Next Steps

1. **Immediate** (1-2 days):
   - Implement unit tests (`test_dag_sequential_execution.py`)
   - Run manual verification using this checklist
   - Fix any bugs discovered during testing

2. **Short Term** (1 week):
   - Implement integration tests (4-player game end-to-end)
   - Run performance benchmarks
   - Document any edge cases or limitations

3. **Phase 2** (3 weeks):
   - Implement agent copilot mode UI
   - Real-time AI recommendations during gameplay
   - Authority-based escalation with decision proposals

---

## Contact & Support

**Implementation Date**: 2026-01-27
**Phase**: Phase 1 (DAG Sequential Execution)
**Status**: Ready for Testing ✅

For issues or questions:
1. Check [DAG_SEQUENTIAL_IMPLEMENTATION.md](DAG_SEQUENTIAL_IMPLEMENTATION.md) for technical details
2. Check [HUMAN_GAME_INTERACTION_DESIGN.md](docs/HUMAN_GAME_INTERACTION_DESIGN.md) for design rationale
3. Review [DECISION_SIMULATION.md](DECISION_SIMULATION.md) for Phase 0 foundation
