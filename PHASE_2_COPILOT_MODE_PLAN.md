# Phase 2: Agent Copilot Mode - Implementation Plan

## Overview

**Duration**: 3 weeks (Week 5-7)
**Goal**: Add real-time AI recommendations during gameplay with copilot UI and authority-based escalation
**Foundation**: Built on Phase 0 (decision simulation) and Phase 1 (DAG sequential execution)

**Status**: 🚀 STARTING (2026-01-27)

---

## Architecture Overview

### Copilot Mode Flow

```
1. FULFILLMENT PHASE
   ├─ Human opens FulfillmentForm
   ├─ System calls agent recommendation API
   ├─ Agent calculates suggested fulfillment quantity
   ├─ Returns: quantity, reasoning, confidence, impact preview
   ├─ UI displays recommendation alongside human input
   ├─ Human can: Accept / Modify / Override
   └─ Submit decision (with override tracking)

2. REPLENISHMENT PHASE
   ├─ Human opens ReplenishmentForm
   ├─ System calls agent recommendation API
   ├─ Agent calculates suggested replenishment quantity
   ├─ Returns: quantity, reasoning, confidence, impact preview
   ├─ UI displays recommendation with base stock policy
   ├─ Human can: Accept / Modify / Override
   └─ Submit decision (with override tracking)

3. AUTHORITY CHECK (if override exceeds threshold)
   ├─ Detect: Human quantity differs from agent by >X%
   ├─ Check: Does override exceed authority level?
   ├─ If yes → Create decision proposal automatically
   ├─ Pause game execution pending approval
   ├─ Manager reviews probabilistic business case
   ├─ Approve → Resume game with human decision
   └─ Reject → Revert to agent recommendation
```

---

## Phase 2 Breakdown

### Week 5: Backend Agent Recommendation API (5 days)

**Day 1-2: Agent Recommendation Service**
- File: `backend/app/services/agent_recommendation_service.py` (NEW)
- Methods:
  - `get_fulfillment_recommendation(player, game_context) → RecommendationResult`
  - `get_replenishment_recommendation(player, game_context) → RecommendationResult`
  - `calculate_confidence_score(agent_type, historical_performance) → float`
  - `generate_reasoning(agent_decision, context) → str`

**Day 2-3: API Endpoints**
- File: `backend/app/api/endpoints/mixed_game.py` (extend)
- Endpoints:
  - `GET /mixed-games/{game_id}/recommendations/fulfillment/{player_id}`
  - `GET /mixed-games/{game_id}/recommendations/replenishment/{player_id}`
  - `POST /mixed-games/{game_id}/override-tracking`

**Day 3-4: Agent Integration**
- Integrate with existing agents:
  - LLM agents (`llm_agent.py`)
  - GNN agents (`gnn/` models)
  - TRM agents (tiny recursive model)
  - Heuristic agents (`agents.py`)
- Add recommendation mode to agent interfaces

**Day 4-5: Authority Check Integration**
- File: `backend/app/services/authority_check_service.py` (NEW)
- Methods:
  - `check_override_authority(player, agent_qty, human_qty, action_type) → AuthorityCheckResult`
  - `create_override_proposal(player, decision_data) → DecisionProposal`
  - `calculate_override_threshold(player_authority_level) → float`
- Link to Phase 0 decision proposal system

**Deliverable**: Backend APIs functional, agents returning recommendations

---

### Week 6: Frontend Copilot UI Components (5 days)

**Day 6-7: AgentRecommendationPanel Component**
- File: `frontend/src/components/game/AgentRecommendationPanel.jsx` (NEW)
- Features:
  - Display agent recommendation with reasoning
  - Show confidence score (visual indicator)
  - Quick action buttons (Accept / Modify / Override)
  - Impact comparison (agent vs human decision)
  - Agent type indicator (LLM / GNN / TRM / Heuristic)

**Day 7-8: Update FulfillmentForm for Copilot**
- File: `frontend/src/components/game/FulfillmentForm.jsx` (modify)
- Changes:
  - Fetch agent recommendation on mount (if agentMode === 'copilot')
  - Display AgentRecommendationPanel
  - Track human modifications vs agent suggestion
  - Highlight differences (color-coded)
  - Add "Why did I override?" note field (optional)

**Day 8-9: Update ReplenishmentForm for Copilot**
- File: `frontend/src/components/game/ReplenishmentForm.jsx` (modify)
- Changes:
  - Fetch agent recommendation on mount
  - Display AgentRecommendationPanel with base stock comparison
  - Side-by-side view (agent | base stock | human)
  - Track override reasoning

**Day 9-10: OverrideApprovalDialog Component**
- File: `frontend/src/components/game/OverrideApprovalDialog.jsx` (NEW)
- Features:
  - Modal dialog when authority check fails
  - Show override impact (cost/service level delta)
  - Request approval from manager
  - Display pending status (game paused)
  - Auto-refresh on approval/rejection

**Deliverable**: Copilot UI components integrated into game forms

---

### Week 7: Integration & Testing (5 days)

**Day 11-12: GameRoom Integration**
- File: `frontend/src/pages/GameRoom.jsx` (modify)
- Changes:
  - Add override tracking state
  - Add authority check handlers
  - Add approval workflow UI
  - WebSocket handlers for override approval events

**Day 12-13: WebSocket Messages**
- File: `backend/app/api/endpoints/websocket.py` (extend)
- New messages:
  - `agent_recommendation_ready`: Notify when recommendation calculated
  - `override_requires_approval`: Notify player of authority check failure
  - `override_approved`: Manager approved override
  - `override_rejected`: Manager rejected override, use agent recommendation

**Day 13-14: Testing**
- Unit tests:
  - `test_agent_recommendation_service.py`
  - `test_authority_check_service.py`
  - `AgentRecommendationPanel.test.jsx`
  - `OverrideApprovalDialog.test.jsx`
- Integration tests:
  - End-to-end copilot game (human with AI recommendations)
  - Authority check workflow (override → proposal → approval)
  - Agent recommendation accuracy

**Day 14-15: Documentation & Polish**
- Update user guide with copilot mode instructions
- Create training materials (how to use copilot effectively)
- Performance optimization (recommendation caching)
- Error handling improvements

**Deliverable**: Complete copilot mode functional, tested, and documented

---

## Technical Specifications

### 1. Agent Recommendation Data Structure

**Request**:
```json
GET /mixed-games/{game_id}/recommendations/fulfillment/{player_id}
```

**Response**:
```json
{
  "agent_id": "gnn_v2_model_123",
  "agent_type": "GNN",
  "recommendation": {
    "quantity": 91,
    "reasoning": "Recommend shipping only ATP (91 units) to protect Day 22 commitment. Demand is 120 units, but shipping full demand would exceed ATP by 29 units, risking future service level.",
    "confidence": 0.87,
    "alternative_scenarios": [
      {
        "quantity": 120,
        "description": "Ship full demand",
        "risk": "HIGH - Exceeds ATP, will create backlog for Day 22 customer"
      },
      {
        "quantity": 80,
        "description": "Conservative shipment",
        "risk": "LOW - Preserves buffer, but increases current backlog"
      }
    ]
  },
  "impact_preview": {
    "if_accept": {
      "inventory_after": 109,
      "fill_rate": 0.758,
      "backlog_after": 29,
      "cost_impact": 1450
    },
    "if_override_to_120": {
      "inventory_after": 80,
      "fill_rate": 1.0,
      "backlog_after": 0,
      "cost_impact": 0,
      "risk": "Future ATP shortage on Day 22"
    }
  },
  "historical_performance": {
    "avg_accuracy": 0.89,
    "recent_decisions": 156,
    "overrides": 12,
    "override_regret_rate": 0.25
  }
}
```

### 2. Authority Check Data Structure

**Request**:
```json
POST /mixed-games/{game_id}/override-tracking
{
  "player_id": 1,
  "agent_quantity": 91,
  "human_quantity": 120,
  "action_type": "fulfillment",
  "reasoning": "Customer urgency - willing to risk future shortage"
}
```

**Response**:
```json
{
  "override_approved": false,
  "requires_approval": true,
  "authority_check": {
    "player_authority_level": "OPERATOR",
    "threshold_exceeded": true,
    "override_percentage": 31.9,
    "threshold_percentage": 20.0
  },
  "decision_proposal_id": 543,
  "approval_status": "PENDING",
  "estimated_wait_time": "2-5 minutes",
  "escalated_to": "MANAGER",
  "business_case_preview": {
    "expected_cost_increase": 2500,
    "expected_fill_rate_improvement": 0.032,
    "recommendation": "APPROVE WITH CAUTION"
  }
}
```

### 3. WebSocket Messages

**agent_recommendation_ready**:
```json
{
  "type": "agent_recommendation_ready",
  "game_id": 42,
  "player_id": 1,
  "phase": "fulfillment",
  "recommendation": { /* same as API response */ }
}
```

**override_requires_approval**:
```json
{
  "type": "override_requires_approval",
  "game_id": 42,
  "player_id": 1,
  "proposal_id": 543,
  "message": "Your override exceeds authority level. Waiting for manager approval.",
  "game_paused": true
}
```

**override_approved**:
```json
{
  "type": "override_approved",
  "game_id": 42,
  "player_id": 1,
  "proposal_id": 543,
  "approved_by": "manager_001",
  "message": "Override approved. Proceeding with your decision.",
  "game_resumed": true
}
```

---

## Key Design Decisions

### 1. Recommendation Timing
- **Option A**: Fetch on form mount (eager)
- **Option B**: Fetch on user request (lazy)
- **Decision**: **Option A** - Eager loading provides instant feedback

### 2. Override Tracking
- **Option A**: Track all overrides (even minor)
- **Option B**: Only track significant overrides (>20% delta)
- **Decision**: **Option B** - Reduce noise, focus on meaningful deviations

### 3. Agent Selection
- **Option A**: Fixed agent per player (set at game creation)
- **Option B**: Dynamic agent selection (player chooses)
- **Decision**: **Option A** (Phase 2) - Simplifies implementation, defer Option B to Phase 4

### 4. Approval Workflow
- **Option A**: Synchronous (block game until approval)
- **Option B**: Asynchronous (player continues, retroactive adjustment)
- **Decision**: **Option A** - Clearer workflow, enforces authority boundaries

### 5. Recommendation Caching
- **Option A**: Cache recommendations (1-minute TTL)
- **Option B**: Always compute fresh (no cache)
- **Decision**: **Option A** - Performance optimization, especially for LLM agents (expensive API calls)

---

## Integration with Phase 0 & Phase 1

### Phase 0 Integration (Decision Simulation)
- Use `decision_proposals` table for override proposals
- Use `business_impact_service.py` for probabilistic impact calculation
- Use `authority_definitions` table for authority checks
- Link override proposals to game execution context

### Phase 1 Integration (DAG Sequential)
- Copilot mode works within FULFILLMENT and REPLENISHMENT phases
- Agent recommendations called at phase entry
- Override tracking integrated into phase submission
- Authority checks pause phase progression

---

## Success Criteria

### Backend ✅
- [ ] Agent recommendation service returns valid recommendations
- [ ] API endpoints functional (2 new endpoints)
- [ ] Authority check service validates overrides correctly
- [ ] Integration with LLM/GNN/TRM agents working
- [ ] Decision proposal creation on authority failure

### Frontend ✅
- [ ] AgentRecommendationPanel displays recommendations
- [ ] FulfillmentForm shows copilot mode
- [ ] ReplenishmentForm shows copilot mode
- [ ] OverrideApprovalDialog appears on authority failure
- [ ] WebSocket integration for approval events

### Integration ✅
- [ ] End-to-end copilot game playable
- [ ] Authority checks trigger correctly (>20% override)
- [ ] Manager approval workflow functional
- [ ] Override regret tracking working
- [ ] Performance: Recommendation API <500ms

### Testing ✅
- [ ] Unit tests passing (>85% coverage)
- [ ] Integration tests passing (copilot game)
- [ ] Manual testing complete (all scenarios)

---

## Known Limitations (Phase 2 Scope)

### In Scope
- ✅ Copilot mode for human players
- ✅ Single agent recommendation per decision
- ✅ Authority-based approval workflow
- ✅ Override tracking and regret analysis

### Out of Scope (Future Phases)
- ❌ Multi-agent consensus (e.g., LLM + GNN voting)
- ❌ Dynamic agent switching mid-game
- ❌ Real-time agent training from human overrides
- ❌ Explainable AI (SHAP/LIME for GNN decisions)
- ❌ Agent performance benchmarking dashboard

---

## Risk Mitigation

### Risk 1: LLM API Latency
**Issue**: OpenAI API calls may take 2-5 seconds
**Mitigation**:
- Cache recommendations (1-minute TTL)
- Show loading spinner immediately
- Fallback to heuristic agent if timeout (>10s)

### Risk 2: Agent Recommendation Quality
**Issue**: Agent may give poor recommendations, users lose trust
**Mitigation**:
- Display confidence score (transparency)
- Show historical performance metrics
- Always allow human override
- Track override regret (learn from mistakes)

### Risk 3: Authority Check Complexity
**Issue**: Authority definitions may be unclear or overly restrictive
**Mitigation**:
- Start with simple percentage threshold (20%)
- Provide clear messaging on why approval needed
- Allow system admin to adjust thresholds
- Log all authority checks for tuning

---

## Next Steps (After Phase 2)

### Phase 3: Full ATP/CTP Integration (3 weeks)
- Connect ATP calculation to planning workflows
- Real-time capacity constraint checking
- Multi-period ATP projection
- Allocation conflict resolution

### Phase 4: Multi-Agent Orchestration (4 weeks)
- Dynamic agent mode switching
- Multi-agent consensus (voting/averaging)
- Agent performance benchmarking
- Real-time agent training from overrides (RLHF)

---

## Contact & Timeline

**Start Date**: 2026-01-27
**Target Completion**: 2026-02-17 (3 weeks)
**Phase**: Phase 2 (Agent Copilot Mode)
**Prerequisites**: Phase 0 ✅, Phase 1 ✅

**Week 5**: Backend agent recommendation API
**Week 6**: Frontend copilot UI components
**Week 7**: Integration, testing, documentation
