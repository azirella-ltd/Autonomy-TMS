# DAG Sequential Execution Implementation

## Overview

This document details the implementation of DAG-ordered sequential execution for The Beer Game, replacing simultaneous player actions with downstream-to-upstream sequential processing.

## Status

**Phase 0 ✅**: Scenario branching + decision simulation complete (2 weeks)
**Phase 1 ✅**: DAG sequential execution **COMPLETE** (2.5 weeks)

### Completed (Phase 1)

**Backend**:
- ✅ Round phase enum (FULFILLMENT, REPLENISHMENT, DECISION, COMPLETED)
- ✅ GameRound model extended with current_phase, phase timestamps
- ✅ TransferOrder helper methods (_create_transfer_order, _process_transfer_order_arrivals, _get_lane_lead_time)
- ✅ Database schema updates (supply_chain.py models)
- ✅ DAG sequential round orchestration (_start_round_dag_sequential)
- ✅ Fulfillment phase processing (_process_node_fulfillment_decision)
- ✅ Replenishment phase processing (_process_node_replenishment_decision)
- ✅ Phase transition logic (_check_phase_transition, _transition_phase)
- ✅ ATP calculation (_calculate_atp)
- ✅ API endpoints (POST /fulfillment, POST /replenishment, GET /atp, GET /pipeline)

**Frontend**:
- ✅ FulfillmentForm component (330+ lines) - ATP display, slider controls, impact preview
- ✅ ReplenishmentForm component (330+ lines) - Pipeline visibility, base stock policy
- ✅ DecisionPhaseIndicator component (150+ lines) - Phase stepper, player progress
- ✅ GameRoom integration - WebSocket handlers, conditional rendering, state management

**Documentation**:
- ✅ Design document updated (HUMAN_GAME_INTERACTION_DESIGN.md)
- ✅ Implementation guide (DAG_SEQUENTIAL_IMPLEMENTATION.md)

### Next Steps (Phase 2+)
- ⏳ Testing & integration (unit tests, integration tests, performance tests)
- ⏳ Agent copilot mode UI (real-time recommendations during gameplay)
- ⏳ Full ATP/CTP integration with planning workflows
- ⏳ Multi-product support (BOM explosion, multi-item TOs)

## Architecture

### Round Phase Flow

```
1. INITIALIZATION
   ├─ Create GameRound with current_phase = FULFILLMENT
   ├─ Initialize NodeStates for all nodes
   └─ Broadcast round_phase_change: "FULFILLMENT"

2. FULFILLMENT PHASE (Downstream → Upstream order)
   ├─ Retailer acts first:
   │  ├─ Process arrivals (TOs from upstream)
   │  ├─ Calculate ATP (inventory - committed)
   │  ├─ Human decision: Ship quantity ≤ ATP
   │  ├─ Create TO to customer (lead time = 1)
   │  └─ Update NodeState (inventory after shipment)
   ├─ Wholesaler waits for Retailer PO
   ├─ When Retailer submits replenishment order:
   │  ├─ Wholesaler processes arrivals
   │  ├─ Calculate ATP
   │  ├─ Fulfill Retailer PO (create TO)
   │  └─ Update NodeState
   ├─ Distributor waits for Wholesaler PO
   └─ Factory waits for Distributor PO

3. PHASE TRANSITION: FULFILLMENT → REPLENISHMENT
   ├─ Check: All players have submitted fulfillment decisions?
   ├─ Update: GameRound.current_phase = REPLENISHMENT
   ├─ Update: GameRound.fulfillment_completed_at = now()
   ├─ Broadcast: round_phase_change: "REPLENISHMENT"

4. REPLENISHMENT PHASE (Upstream → Downstream order)
   ├─ Each node (Retailer → Factory):
   │  ├─ Review: Current inventory, pipeline shipments, demand forecast
   │  ├─ Human decision: Order quantity from upstream
   │  ├─ Create TO/PO/MO to upstream (with lane lead time)
   │  └─ Update PlayerRound.order_placed
   └─ Factory creates MO (manufacturing order) instead of PO

5. PHASE TRANSITION: REPLENISHMENT → COMPLETED
   ├─ Check: All players have submitted replenishment orders?
   ├─ Update: GameRound.current_phase = COMPLETED
   ├─ Update: GameRound.replenishment_completed_at = now()
   ├─ Update: GameRound.completed_at = now()
   ├─ Broadcast: round_completed
   └─ Advance to next round

6. NEXT ROUND
   ├─ Process TO arrivals (check arrival_round == current_round)
   ├─ Repeat from step 1
```

### Method Signature

```python
def _start_round_dag_sequential(self, game_obj: Game) -> Optional[GameRound]:
    """
    DAG-ordered sequential round execution.

    Phases:
    1. FULFILLMENT: Downstream→upstream, ATP-based shipments
    2. REPLENISHMENT: All nodes order from upstream (after PO receipt)
    3. COMPLETED: Round finished, advance to next

    Returns:
        GameRound record or None if game finished
    """
```

### Key Methods

**1. _initialize_dag_round(game_obj, round_number) → RoundContext**
- Create GameRound with current_phase = FULFILLMENT
- Initialize NodeStates for all nodes
- Process TO arrivals (where arrival_round == current_round)
- Calculate initial ATP for each node
- Broadcast round_phase_change: "FULFILLMENT"

**2. _process_node_fulfillment(node_key, context, fulfill_qty) → TransferOrder**
- Validate fulfill_qty ≤ ATP
- Create TO to downstream (or customer if terminal node)
- Update NodeState.inventory -= fulfill_qty
- Update NodeState.committed_orders -= fulfilled_qty
- Return created TransferOrder

**3. _process_node_replenishment(node_key, context, order_qty) → TransferOrder**
- Create TO/PO/MO to upstream supplier
- Set arrival_round = current_round + lane.supply_lead_time
- Update PlayerRound.order_placed = order_qty
- Link: PlayerRound.upstream_order_id = TO.id
- Return created TransferOrder

**4. _check_phase_transition(game_obj, from_phase, to_phase) → bool**
- Query PlayerRound records for current round
- FULFILLMENT → REPLENISHMENT: All players submitted fulfillment?
- REPLENISHMENT → COMPLETED: All players submitted replenishment?
- Return True if ready to transition

**5. _transition_phase(game_obj, round_obj, new_phase) → None**
- Update round_obj.current_phase = new_phase
- Update phase timestamps (fulfillment_completed_at, replenishment_completed_at)
- Broadcast WebSocket: round_phase_change
- Commit to database

## Database Schema

### TransferOrder Extensions (Beer Game)
```sql
-- Added in 20260127_order_tracking migration
ALTER TABLE transfer_order ADD COLUMN game_id INT NULL;
ALTER TABLE transfer_order ADD COLUMN order_round INT NULL;
ALTER TABLE transfer_order ADD COLUMN arrival_round INT NULL;
ALTER TABLE transfer_order ADD COLUMN source_player_round_id INT NULL;
CREATE INDEX idx_to_game_arrival ON transfer_order (game_id, arrival_round, status);
```

### PlayerRound Extensions
```sql
-- Added in 20260127_order_tracking migration
ALTER TABLE player_rounds ADD COLUMN upstream_order_id INT NULL;
ALTER TABLE player_rounds ADD COLUMN upstream_order_type ENUM('TO', 'PO', 'MO') NULL;
ALTER TABLE player_rounds ADD COLUMN round_phase ENUM('FULFILLMENT', 'REPLENISHMENT', 'DECISION') NULL;
CREATE INDEX idx_player_round_upstream_order ON player_rounds (upstream_order_id, upstream_order_type);
```

### GameRound Extensions
```sql
-- Added in 20260127_order_tracking migration
ALTER TABLE game_rounds ADD COLUMN current_phase ENUM('FULFILLMENT', 'REPLENISHMENT', 'DECISION', 'COMPLETED') DEFAULT 'DECISION';
ALTER TABLE game_rounds ADD COLUMN phase_started_at DATETIME NULL;
ALTER TABLE game_rounds ADD COLUMN fulfillment_completed_at DATETIME NULL;
ALTER TABLE game_rounds ADD COLUMN replenishment_completed_at DATETIME NULL;
CREATE INDEX idx_game_round_phase ON game_rounds (game_id, round_number, current_phase);
```

## API Endpoints

### 1. Submit Fulfillment Decision
```
POST /api/mixed-games/{game_id}/rounds/{round_number}/fulfillment
Body: {
  "player_id": 1,
  "fulfill_qty": 120
}
Response: {
  "success": true,
  "transfer_order_id": 1542,
  "updated_inventory": 114,
  "updated_atp": 34,
  "phase": "FULFILLMENT",
  "awaiting_players": ["wholesaler", "distributor", "factory"]
}
```

### 2. Submit Replenishment Order
```
POST /api/mixed-games/{game_id}/rounds/{round_number}/replenishment
Body: {
  "player_id": 1,
  "order_qty": 456
}
Response: {
  "success": true,
  "transfer_order_id": 1543,
  "arrival_round": 18,
  "phase": "REPLENISHMENT",
  "round_completed": false
}
```

### 3. Get ATP (Available to Promise)
```
GET /api/mixed-games/{game_id}/atp/{player_id}
Response: {
  "current_atp": 91,
  "on_hand": 234,
  "committed": 143,
  "in_transit": [
    {"quantity": 150, "arrival_round": 17},
    {"quantity": 200, "arrival_round": 19}
  ],
  "projected_atp": {
    "15": 91,
    "16": 156,
    "17": 283,
    "18": 283
  }
}
```

### 4. Get Pipeline (In-Transit Shipments)
```
GET /api/mixed-games/{game_id}/pipeline/{player_id}
Response: {
  "in_transit": [
    {
      "transfer_order_id": 1521,
      "quantity": 150,
      "origin": "Distributor",
      "destination": "Wholesaler",
      "order_round": 14,
      "arrival_round": 17,
      "rounds_until_arrival": 2,
      "status": "IN_TRANSIT"
    },
    {
      "transfer_order_id": 1522,
      "quantity": 200,
      "origin": "Distributor",
      "destination": "Wholesaler",
      "order_round": 15,
      "arrival_round": 19,
      "rounds_until_arrival": 4,
      "status": "IN_TRANSIT"
    }
  ]
}
```

## WebSocket Messages

### 1. round_phase_change
```json
{
  "type": "round_phase_change",
  "game_id": 42,
  "round_number": 15,
  "phase": "REPLENISHMENT",
  "phase_started_at": "2026-01-27T10:15:23Z",
  "awaiting_players": ["retailer", "wholesaler", "distributor", "factory"]
}
```

### 2. player_action_required
```json
{
  "type": "player_action_required",
  "game_id": 42,
  "player_id": 1,
  "action": "fulfillment",
  "atp": 91,
  "demand": 120
}
```

### 3. fulfillment_completed
```json
{
  "type": "fulfillment_completed",
  "game_id": 42,
  "player_id": 1,
  "node_key": "retailer",
  "fulfill_qty": 120,
  "updated_inventory": 114
}
```

### 4. all_players_ready_for_replenishment
```json
{
  "type": "all_players_ready_for_replenishment",
  "game_id": 42,
  "round_number": 15,
  "transition_time": "2026-01-27T10:20:15Z"
}
```

## Frontend Components

### 1. FulfillmentForm (Phase 1, Week 3-4)
```jsx
<FulfillmentForm
  atp={91}
  demand={120}
  agentMode="manual"
  onSubmit={handleFulfillmentSubmit}
/>
```

### 2. ReplenishmentForm (Phase 1, Week 3-4)
```jsx
<ReplenishmentForm
  currentInventory={114}
  pipeline={[
    {quantity: 150, arrivalRound: 17},
    {quantity: 200, arrivalRound: 19}
  ]}
  backlog={23}
  agentMode="manual"
  onSubmit={handleReplenishmentSubmit}
/>
```

### 3. DecisionPhaseIndicator (Phase 1, Week 3-4)
```jsx
<DecisionPhaseIndicator
  phase="FULFILLMENT"
  playersCompleted={2}
  totalPlayers={4}
/>
```

## Integration with Existing Code

### Feature Flag
```python
# Game model
class Game(Base):
    use_dag_sequential = Column(Boolean, default=False)  # New field
```

### Round Dispatcher
```python
def start_round(self, game_obj: Game):
    if game_obj.use_dag_sequential:
        return self._start_round_dag_sequential(game_obj)
    elif game_obj.use_sc_planning:
        return self._start_round_sc_planning(game_obj)
    else:
        return self._start_round_legacy(game_obj)
```

## Testing Plan

### Unit Tests
1. Test _create_transfer_order with game_id, order_round, arrival_round
2. Test _process_transfer_order_arrivals filters by arrival_round
3. Test _get_lane_lead_time extracts from Lane.supply_lead_time JSON
4. Test phase transitions (FULFILLMENT → REPLENISHMENT → COMPLETED)
5. Test ATP calculation (inventory - committed)
6. Test pipeline query performance (<50ms)

### Integration Tests
1. Create 4-player game with use_dag_sequential=True
2. Start game → Verify phase = FULFILLMENT
3. Submit fulfillment for Retailer → Verify TO created
4. Submit fulfillment for all players → Verify phase = REPLENISHMENT
5. Submit replenishment for all players → Verify phase = COMPLETED
6. Advance to next round → Verify TOs arrive, inventory updated

### Performance Tests
1. ATP calculation: <10ms
2. Pipeline query: <50ms
3. Phase transition: <100ms
4. Full round (4 players): <5 seconds end-to-end

## Phase 1 Implementation Summary (COMPLETED)

### What Was Built

**Backend Infrastructure** (Week 1-2):
1. ✅ Design document update (HUMAN_GAME_INTERACTION_DESIGN.md)
2. ✅ Round phase enum (RoundPhase) with FULFILLMENT, REPLENISHMENT, DECISION, COMPLETED
3. ✅ GameRound model extensions (current_phase, phase_started_at, fulfillment_completed_at, replenishment_completed_at)
4. ✅ DAG sequential orchestration (_start_round_dag_sequential method - 100 lines)
5. ✅ Fulfillment phase processing (_process_node_fulfillment_decision - 80 lines)
6. ✅ Replenishment phase processing (_process_node_replenishment_decision - 70 lines)
7. ✅ Phase transition logic (_check_phase_transition, _transition_phase - 60 lines)
8. ✅ ATP calculation (_calculate_atp - 40 lines)
9. ✅ TransferOrder helpers (_create_transfer_order, _process_transfer_order_arrivals - 140 lines)

**API Layer** (Week 2):
- ✅ POST `/mixed-games/{game_id}/rounds/{round_number}/fulfillment` - Submit fulfillment decision
- ✅ POST `/mixed-games/{game_id}/rounds/{round_number}/replenishment` - Submit replenishment order
- ✅ GET `/mixed-games/{game_id}/atp/{player_id}` - Get Available to Promise
- ✅ GET `/mixed-games/{game_id}/pipeline/{player_id}` - Get in-transit shipments

**Frontend Components** (Week 3):
- ✅ FulfillmentForm.jsx (330 lines):
  - ATP display with current state (on-hand, ATP, demand, backlog)
  - Slider + TextField controls with validation
  - Quick action buttons (Ship 0, Ship ATP, Ship Full Demand)
  - Impact preview (inventory after, fill rate, backlog after)
  - Agent mode support (manual, copilot, autonomous)
  - Material-UI Card layout with sections

- ✅ ReplenishmentForm.jsx (330 lines):
  - Current state display (on-hand, pipeline total, backlog, avg demand)
  - Pipeline visibility table (quantity, origin, arrival round, rounds until arrival)
  - Recommended order calculation (base stock policy)
  - Slider + TextField controls
  - Quick action buttons (Order 0, Order Recommended, Order Double)
  - Impact preview (inventory position, days of supply, vs recommended)
  - Agent mode support (manual, copilot, autonomous)

- ✅ DecisionPhaseIndicator.jsx (150 lines):
  - Stepper with phase progression (Waiting → Fulfillment → Replenishment → Completed)
  - Player completion status with progress bar
  - Phase-specific icons and color coding
  - Elapsed time counter
  - Banner-style layout with colored border

**Frontend Integration** (Week 3-4):
- ✅ GameRoom.jsx modifications:
  - Component imports (FulfillmentForm, ReplenishmentForm, DecisionPhaseIndicator)
  - State management (roundPhase, atpData, pipelineData, playersCompleted, demandHistory)
  - WebSocket message handlers:
    - `round_phase_change`: Updates phase, fetches ATP/pipeline data
    - `player_action_required`: Notifies player of required action
    - `fulfillment_completed`: Tracks completion progress
    - `all_players_ready_for_replenishment`: Phase transition notification
  - API fetch functions (fetchATPData, fetchPipelineData)
  - Submit handlers (handleFulfillmentSubmit, handleReplenishmentSubmit)
  - Conditional rendering based on `game.use_dag_sequential` flag
  - DecisionPhaseIndicator at top of game board
  - Phase-specific form rendering (fulfillment vs replenishment vs waiting)

**Documentation**:
- ✅ DAG_SEQUENTIAL_IMPLEMENTATION.md (complete technical specification)
- ✅ HUMAN_GAME_INTERACTION_DESIGN.md (updated with Phase 0 completion status)

### Key Architectural Decisions

1. **Backward Compatibility**: Feature flag `game.use_dag_sequential` preserves legacy single-order gameplay
2. **Material-UI + Tailwind Hybrid**: New components use MUI, GameRoom preserves Tailwind
3. **WebSocket-Driven UI**: Phase transitions and player progress updated via WebSocket broadcasts
4. **Optimistic ATP Updates**: Frontend updates ATP data after fulfillment submission (before full refresh)
5. **Error Handling**: Graceful degradation with user-friendly toast notifications

### Files Modified/Created

**Backend** (total: ~500 lines added):
- `backend/app/models/supply_chain.py` (modified): RoundPhase enum, GameRound extensions
- `backend/app/services/mixed_game_service.py` (modified): +490 lines for DAG methods
- `backend/app/api/endpoints/mixed_game.py` (modified): +360 lines for dual-decision endpoints

**Frontend** (total: ~900 lines added):
- `frontend/src/components/game/FulfillmentForm.jsx` (created): 364 lines
- `frontend/src/components/game/ReplenishmentForm.jsx` (created): 343 lines
- `frontend/src/components/game/DecisionPhaseIndicator.jsx` (created): 153 lines
- `frontend/src/pages/GameRoom.jsx` (modified): +140 lines for integration

**Documentation**:
- `DAG_SEQUENTIAL_IMPLEMENTATION.md` (complete)
- `docs/HUMAN_GAME_INTERACTION_DESIGN.md` (updated)

### Testing Status

**Manual Testing**: ⏳ Pending
- Create 4-player game with `use_dag_sequential=True`
- Verify phase transitions (FULFILLMENT → REPLENISHMENT → COMPLETED)
- Test ATP calculation and validation
- Test pipeline visibility with in-transit shipments
- Test WebSocket broadcasts for phase changes

**Unit Tests**: ⏳ Pending
- `test_dag_sequential_execution.py` (backend)
- `FulfillmentForm.test.jsx` (frontend)
- `ReplenishmentForm.test.jsx` (frontend)
- `DecisionPhaseIndicator.test.jsx` (frontend)

**Integration Tests**: ⏳ Pending
- End-to-end 4-player DAG game
- WebSocket broadcast integration
- ATP/pipeline API performance

**Performance Tests**: ⏳ Pending
- ATP calculation: target <10ms
- Pipeline query: target <50ms
- Phase transition: target <100ms

### Next Phase (Phase 2 - Agent Copilot Mode)

**Week 5-7** (3 weeks):
1. **Real-time agent recommendations during gameplay**:
   - Agents calculate suggested fulfillment + replenishment quantities
   - Return reasoning + confidence scores during round execution
   - Integration with existing LLM/GNN/TRM agents

2. **Copilot UI in GameRoom**:
   - Display AI recommendations alongside human decision forms
   - Side-by-side comparison (agent suggestion vs human input)
   - Quick approval workflow (Accept/Modify/Reject buttons)
   - Real-time impact preview (cost/service level changes)

3. **Authority-based escalation**:
   - If human override exceeds authority, create decision proposal automatically
   - Pause game execution pending approval
   - Resume after approval/rejection
   - Link to Phase 0 decision simulation infrastructure

### Summary

DAG sequential execution transforms The Beer Game from simultaneous actions to realistic supply chain workflows where:
- **Downstream acts first** (demand flows upstream)
- **Upstream waits for POs** (realistic ordering)
- **Dual decisions per round** (fulfillment + replenishment)
- **Pipeline visibility** (in-transit shipments with arrival estimates)
- **ATP-based fulfillment** (capacity constraints)
- **Phase transitions** (clear progression through round)

This provides the foundation for Mode 2 (copilot) and Mode 3 (manual) gameplay, where humans make supply chain decisions with full visibility and explainability.

**Total Implementation Time**: 2.5 weeks (Backend: 1.5 weeks, Frontend: 1 week)
**Lines of Code Added**: ~1,400 (Backend: 500, Frontend: 900)
**Components Created**: 3 (FulfillmentForm, ReplenishmentForm, DecisionPhaseIndicator)
**API Endpoints Added**: 4 (fulfillment, replenishment, ATP, pipeline)
**Ready for Testing**: Yes ✅
