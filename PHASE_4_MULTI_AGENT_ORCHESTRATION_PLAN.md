# Phase 4: Multi-Agent Orchestration Plan

**Duration**: 4 weeks (Week 11-14)
**Prerequisites**: Phase 0 ✅, Phase 1 ✅, Phase 2 ✅, Phase 3 ✅
**Start Date**: 2026-01-28
**Target Completion**: 2026-02-25

---

## Executive Summary

Phase 4 implements **Multi-Agent Orchestration** capabilities, enabling dynamic agent mode switching, multi-agent consensus decisions, performance benchmarking, and real-time learning from human overrides (RLHF). This transforms The Beer Game into a sophisticated AI testing and training environment.

### Key Objectives

1. **Dynamic Agent Mode Switching**: Toggle manual ↔ copilot ↔ autonomous mid-game
2. **Multi-Agent Consensus**: Combine LLM + GNN + TRM decisions via voting/averaging
3. **Agent Performance Benchmarking**: Real-time comparison dashboard
4. **RLHF Training Pipeline**: Learn from human overrides to improve agents

### Value Proposition

- **Flexibility**: Human players can experiment with different agent modes during gameplay
- **Robustness**: Multi-agent consensus reduces individual agent failure risk
- **Transparency**: Real-time performance metrics build trust in AI recommendations
- **Continuous Improvement**: Agents learn from human expertise via RLHF

---

## Architecture Overview

### Current State (After Phase 3)

**Agent Mode**:
- Fixed at game creation (player.agent_mode set once)
- Single agent per player (no consensus)
- No performance tracking during gameplay
- No learning from human overrides

**Limitations**:
- Cannot compare agents mid-game
- No redundancy if agent fails
- No visibility into agent performance
- Static agents (no improvement over time)

### Target State (After Phase 4)

**Agent Orchestration System**:
- Dynamic mode switching via API/UI
- Multi-agent ensemble (3+ agents vote on decision)
- Real-time performance dashboard
- RLHF pipeline captures human overrides

**New Capabilities**:
- Switch from manual → copilot → autonomous → back to manual
- Ensemble decision: majority vote or weighted average
- Live agent comparison (cost, service level, bullwhip)
- Continuous learning from human corrections

---

## Implementation Phases

### Week 11: Dynamic Agent Mode Switching

#### Task 11.1: Backend Agent Mode Management (Day 1-2)
**File**: `backend/app/services/agent_mode_service.py` (NEW, ~300 lines)

**Core Methods**:
```python
class AgentModeService:
    def switch_agent_mode(
        self, game_id: int, player_id: int, new_mode: str
    ) -> AgentModeSwitch:
        """
        Switch player's agent mode mid-game.

        Validation:
        - Game must be in RUNNING state
        - Player must exist and belong to game
        - New mode must be valid: manual, copilot, autonomous

        Side effects:
        - Updates player.agent_mode
        - Broadcasts agent_mode_switched WebSocket event
        - Logs mode switch to audit trail

        Returns:
            AgentModeSwitch with old_mode, new_mode, timestamp
        """
        pass

    def get_mode_history(
        self, game_id: int, player_id: int
    ) -> List[AgentModeSwitchRecord]:
        """
        Get history of agent mode switches for player.

        Returns:
            List of switches with timestamp, old_mode, new_mode, switched_by
        """
        pass

    def validate_mode_switch(
        self, player: Player, current_mode: str, new_mode: str
    ) -> ModeValidationResult:
        """
        Validate if mode switch is allowed.

        Rules:
        - Can switch from any mode to any other mode
        - Cannot switch during decision submission (race condition)
        - Admin can force switch, player cannot switch others

        Returns:
            ModeValidationResult with allowed, reason
        """
        pass
```

**Data Structures**:
```python
@dataclass
class AgentModeSwitch:
    game_id: int
    player_id: int
    old_mode: str
    new_mode: str
    switched_by: int  # user_id who initiated switch
    timestamp: str

@dataclass
class AgentModeSwitchRecord:
    id: int
    game_id: int
    player_id: int
    round_number: int
    old_mode: str
    new_mode: str
    switched_by: int
    reason: Optional[str]
    created_at: str
```

#### Task 11.2: Database Migration for Mode History (Day 2)
**File**: `backend/alembic/versions/20260128_agent_mode_history.py` (NEW)

**New Table**:
```sql
CREATE TABLE agent_mode_switches (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    game_id INT NOT NULL,
    player_id INT NOT NULL,
    round_number INT NOT NULL,
    old_mode ENUM('MANUAL', 'COPILOT', 'AUTONOMOUS') NOT NULL,
    new_mode ENUM('MANUAL', 'COPILOT', 'AUTONOMOUS') NOT NULL,
    switched_by INT NOT NULL,  -- user_id
    reason VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (switched_by) REFERENCES users(id),
    INDEX idx_mode_switch_game_player (game_id, player_id),
    INDEX idx_mode_switch_round (game_id, round_number)
);
```

#### Task 11.3: Mode Switching API Endpoints (Day 3)
**File**: `backend/app/api/endpoints/mixed_game.py` (+60 lines)

**New Endpoints**:
```python
@router.post("/mixed-games/{game_id}/players/{player_id}/switch-mode")
def switch_agent_mode(
    game_id: int,
    player_id: int,
    new_mode: str,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    mode_service: AgentModeService = Depends(get_agent_mode_service)
):
    """
    Switch player's agent mode mid-game.

    Request:
    {
        "new_mode": "copilot",
        "reason": "Want to see AI suggestions"
    }

    Returns:
    {
        "game_id": 1,
        "player_id": 3,
        "old_mode": "manual",
        "new_mode": "copilot",
        "switched_by": 5,
        "timestamp": "2026-01-28T12:00:00"
    }
    """
    pass

@router.get("/mixed-games/{game_id}/players/{player_id}/mode-history")
def get_mode_history(
    game_id: int,
    player_id: int,
    current_user: User = Depends(get_current_user),
    mode_service: AgentModeService = Depends(get_agent_mode_service)
):
    """
    Get history of agent mode switches.

    Returns:
    [
        {
            "id": 1,
            "round_number": 5,
            "old_mode": "manual",
            "new_mode": "copilot",
            "switched_by": 5,
            "reason": "Want AI help",
            "created_at": "2026-01-28T12:00:00"
        },
        ...
    ]
    """
    pass
```

#### Task 11.4: WebSocket Mode Switch Event (Day 3)
**File**: `backend/app/api/endpoints/websocket.py` (+40 lines)

**New WebSocket Message**:
```python
async def broadcast_agent_mode_switched(
    game_id: int,
    player_id: int,
    old_mode: str,
    new_mode: str,
    switched_by_name: str
):
    """
    Broadcast when player switches agent mode.

    Args:
        game_id: Game ID
        player_id: Player who switched
        old_mode: Previous mode
        new_mode: New mode
        switched_by_name: User name who initiated switch
    """
    message = {
        "type": "agent_mode_switched",
        "game_id": game_id,
        "player_id": player_id,
        "old_mode": old_mode,
        "new_mode": new_mode,
        "switched_by": switched_by_name,
        "message": f"Player {player_id} switched from {old_mode} to {new_mode} mode",
    }

    # Broadcast to all players in game
    await manager.broadcast_to_game(game_id, message)
```

#### Task 11.5: Frontend Mode Switch UI (Day 4-5)
**File**: `frontend/src/components/game/AgentModeSelector.jsx` (NEW, ~200 lines)

**Component Features**:
- Dropdown menu with 3 modes (Manual, Copilot, Autonomous)
- Current mode indicator chip
- Mode description tooltips
- Confirm dialog for mode switches
- Mode history timeline

**UI Design**:
```jsx
<FormControl fullWidth>
  <FormLabel>Agent Mode</FormLabel>
  <Select value={currentMode} onChange={handleModeChange}>
    <MenuItem value="manual">
      <Stack direction="row" spacing={1} alignItems="center">
        <PersonIcon />
        <Typography>Manual</Typography>
        <Chip label="Full Control" size="small" />
      </Stack>
    </MenuItem>
    <MenuItem value="copilot">
      <Stack direction="row" spacing={1} alignItems="center">
        <AssistantIcon />
        <Typography>Copilot</Typography>
        <Chip label="AI Assisted" size="small" color="warning" />
      </Stack>
    </MenuItem>
    <MenuItem value="autonomous">
      <Stack direction="row" spacing={1} alignItems="center">
        <SmartToyIcon />
        <Typography>Autonomous</Typography>
        <Chip label="AI Controlled" size="small" color="info" />
      </Stack>
    </MenuItem>
  </Select>
  <FormHelperText>
    {currentMode === 'manual' && 'You make all decisions'}
    {currentMode === 'copilot' && 'AI suggests, you decide'}
    {currentMode === 'autonomous' && 'AI makes decisions automatically'}
  </FormHelperText>
</FormControl>
```

---

### Week 12: Multi-Agent Consensus

#### Task 12.1: Multi-Agent Ensemble Service (Day 6-7)
**File**: `backend/app/services/multi_agent_ensemble.py` (NEW, ~400 lines)

**Core Methods**:
```python
class MultiAgentEnsemble:
    def get_consensus_recommendation(
        self,
        game: Game,
        player: Player,
        current_round: GameRound,
        decision_type: str,  # "fulfillment" or "replenishment"
        consensus_method: str = "majority_vote",
        **context
    ) -> ConsensusRecommendation:
        """
        Get consensus recommendation from multiple agents.

        Steps:
        1. Call each agent (LLM, GNN, TRM) for recommendation
        2. Apply consensus method:
           - majority_vote: Most common quantity wins
           - weighted_average: Weight by confidence scores
           - highest_confidence: Use agent with highest confidence
        3. Return consensus with agent breakdown

        Args:
            game, player, current_round: Game context
            decision_type: "fulfillment" or "replenishment"
            consensus_method: "majority_vote", "weighted_average", "highest_confidence"
            **context: Additional context (atp, demand, inventory, etc.)

        Returns:
            ConsensusRecommendation with:
            - consensus_quantity
            - consensus_confidence
            - consensus_method
            - agent_recommendations (LLM, GNN, TRM)
            - agreement_score (0.0-1.0, how aligned agents are)
        """
        pass

    def _call_agent(
        self, agent_type: str, player: Player, context: dict
    ) -> AgentRecommendation:
        """
        Call specific agent for recommendation.

        Args:
            agent_type: "LLM", "GNN", or "TRM"
            player: Player instance
            context: Decision context

        Returns:
            AgentRecommendation with quantity, confidence, reasoning
        """
        pass

    def _apply_consensus(
        self,
        agent_recs: List[AgentRecommendation],
        method: str
    ) -> Tuple[int, float]:
        """
        Apply consensus method to agent recommendations.

        Methods:
        - majority_vote: Round quantities to bins (0-50, 51-100, etc.), pick most common
        - weighted_average: Sum(quantity * confidence) / Sum(confidence)
        - highest_confidence: Use recommendation with highest confidence score

        Returns:
            (consensus_quantity, consensus_confidence)
        """
        pass

    def calculate_agreement_score(
        self, agent_recs: List[AgentRecommendation]
    ) -> float:
        """
        Calculate agreement score (0.0-1.0).

        Score = 1 - (std_dev / mean) if mean > 0, else 0.0
        High score = agents agree, Low score = agents disagree

        Returns:
            Agreement score (0.0 = complete disagreement, 1.0 = perfect agreement)
        """
        pass
```

**Data Structures**:
```python
@dataclass
class AgentRecommendation:
    agent_type: str  # "LLM", "GNN", "TRM"
    quantity: int
    confidence: float  # 0.0-1.0
    reasoning: str
    computation_time_ms: float

@dataclass
class ConsensusRecommendation:
    consensus_quantity: int
    consensus_confidence: float
    consensus_method: str
    agent_recommendations: List[AgentRecommendation]
    agreement_score: float  # 0.0-1.0
    computation_time_ms: float
    timestamp: str
```

#### Task 12.2: Consensus API Endpoint (Day 7)
**File**: `backend/app/api/endpoints/mixed_game.py` (+80 lines)

**New Endpoint**:
```python
@router.get("/mixed-games/{game_id}/consensus-recommendation/{player_id}")
def get_consensus_recommendation(
    game_id: int,
    player_id: int,
    decision_type: str,  # fulfillment or replenishment
    consensus_method: str = "weighted_average",
    current_user: User = Depends(get_current_user),
    ensemble: MultiAgentEnsemble = Depends(get_multi_agent_ensemble)
):
    """
    Get consensus recommendation from multiple agents.

    Query Parameters:
    - decision_type: "fulfillment" or "replenishment"
    - consensus_method: "majority_vote", "weighted_average", "highest_confidence"

    Returns:
    {
        "consensus_quantity": 450,
        "consensus_confidence": 0.88,
        "consensus_method": "weighted_average",
        "agent_recommendations": [
            {
                "agent_type": "LLM",
                "quantity": 460,
                "confidence": 0.92,
                "reasoning": "...",
                "computation_time_ms": 1250.5
            },
            {
                "agent_type": "GNN",
                "quantity": 445,
                "confidence": 0.85,
                "reasoning": "...",
                "computation_time_ms": 85.3
            },
            {
                "agent_type": "TRM",
                "quantity": 440,
                "confidence": 0.86,
                "reasoning": "...",
                "computation_time_ms": 12.7
            }
        ],
        "agreement_score": 0.95,
        "computation_time_ms": 1348.5,
        "timestamp": "2026-01-28T12:00:00"
    }
    """
    pass
```

#### Task 12.3: Frontend Multi-Agent Panel (Day 8-9)
**File**: `frontend/src/components/game/MultiAgentConsensusPanel.jsx` (NEW, ~300 lines)

**Component Features**:
- Consensus recommendation display
- Individual agent recommendations (collapsible cards)
- Agreement score visualization (gauge chart)
- Consensus method selector dropdown
- Agent performance comparison table

**UI Design**:
```
┌────────── Multi-Agent Consensus ──────────┐
│                                            │
│  Consensus: 450 units (88% confidence)    │
│  Method: Weighted Average                  │
│  Agreement: ████████░░ 95%                 │
│                                            │
│  [Agent Breakdown ▼]                       │
│                                            │
│  ┌─ LLM Agent ─────────────────────────┐  │
│  │ Recommendation: 460 units (92%)     │  │
│  │ Reasoning: Based on demand trends...│  │
│  │ Computation: 1250ms                 │  │
│  └─────────────────────────────────────┘  │
│                                            │
│  ┌─ GNN Agent ─────────────────────────┐  │
│  │ Recommendation: 445 units (85%)     │  │
│  │ Reasoning: Graph propagation...     │  │
│  │ Computation: 85ms                   │  │
│  └─────────────────────────────────────┘  │
│                                            │
│  ┌─ TRM Agent ─────────────────────────┐  │
│  │ Recommendation: 440 units (86%)     │  │
│  │ Reasoning: Recursive refinement...  │  │
│  │ Computation: 13ms                   │  │
│  └─────────────────────────────────────┘  │
│                                            │
│  [Accept Consensus] [Modify]              │
└────────────────────────────────────────────┘
```

---

### Week 13: Agent Performance Benchmarking

#### Task 13.1: Agent Performance Tracker (Day 10-11)
**File**: `backend/app/services/agent_performance_tracker.py` (NEW, ~350 lines)

**Core Methods**:
```python
class AgentPerformanceTracker:
    def track_decision(
        self,
        game_id: int,
        player_id: int,
        round_number: int,
        agent_type: str,
        agent_recommendation: int,
        human_decision: int,
        decision_type: str,
    ):
        """
        Track agent recommendation vs human decision.

        Records:
        - Agent recommendation
        - Human decision
        - Override delta (abs difference)
        - Decision type (fulfillment/replenishment)

        Stored in: agent_performance_log table
        """
        pass

    def calculate_agent_metrics(
        self, game_id: int, player_id: int, agent_type: str
    ) -> AgentMetrics:
        """
        Calculate performance metrics for agent.

        Metrics:
        - Recommendation accuracy (1 - abs(agent - human) / human)
        - Override rate (% of times human changed recommendation)
        - Cost performance (total cost vs optimal)
        - Service level (fill rate, backlog)
        - Bullwhip ratio (variance amplification)

        Returns:
            AgentMetrics dataclass
        """
        pass

    def compare_agents(
        self, game_id: int, player_id: int
    ) -> AgentComparison:
        """
        Compare all agents on same player.

        Returns:
            AgentComparison with metrics for LLM, GNN, TRM, Human
        """
        pass
```

**Data Structures**:
```python
@dataclass
class AgentMetrics:
    agent_type: str
    total_decisions: int
    override_rate: float  # 0.0-1.0
    avg_accuracy: float  # 0.0-1.0
    total_cost: float
    avg_service_level: float
    avg_bullwhip_ratio: float
    avg_computation_time_ms: float

@dataclass
class AgentComparison:
    game_id: int
    player_id: int
    current_round: int
    agents: List[AgentMetrics]
    best_agent: str  # Agent with lowest cost
    human_performance: AgentMetrics  # Human as baseline
```

#### Task 13.2: Performance Logging Database (Day 11)
**File**: `backend/alembic/versions/20260128_agent_performance_log.py` (NEW)

**New Table**:
```sql
CREATE TABLE agent_performance_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    game_id INT NOT NULL,
    player_id INT NOT NULL,
    round_number INT NOT NULL,
    agent_type VARCHAR(50) NOT NULL,  -- LLM, GNN, TRM, HUMAN, CONSENSUS
    decision_type VARCHAR(50) NOT NULL,  -- fulfillment, replenishment
    agent_recommendation INT,
    agent_confidence FLOAT,
    human_decision INT NOT NULL,
    override_delta INT,  -- abs(human - agent)
    override_rate FLOAT,  -- Calculated incrementally
    cost_impact FLOAT,  -- Estimated cost delta from override
    computation_time_ms FLOAT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    INDEX idx_perf_game_player_agent (game_id, player_id, agent_type),
    INDEX idx_perf_round (game_id, round_number)
);
```

#### Task 13.3: Benchmarking Dashboard UI (Day 12-13)
**File**: `frontend/src/pages/AgentBenchmarkDashboard.jsx` (NEW, ~500 lines)

**Dashboard Features**:
- Real-time agent comparison table
- Cost performance chart (line chart, per-round)
- Override rate bar chart (per agent)
- Service level comparison (radar chart)
- Computation time comparison (box plot)
- Historical trend analysis

**UI Sections**:
1. **Overview Cards** - Total decisions, avg accuracy, override rate
2. **Cost Comparison Chart** - Cumulative cost over time (LLM vs GNN vs TRM vs Human)
3. **Service Level Radar** - Fill rate, backlog, inventory turns
4. **Override Analysis** - When humans override, by how much, cost impact
5. **Recommendation Distribution** - Histogram of agent quantities
6. **Agent Reliability** - Confidence calibration curve

---

### Week 14: RLHF Training Pipeline

#### Task 14.1: RLHF Data Collection Service (Day 14-15)
**File**: `backend/app/services/rlhf_data_collector.py` (NEW, ~250 lines)

**Core Methods**:
```python
class RLHFDataCollector:
    def collect_training_sample(
        self,
        game_id: int,
        player_id: int,
        round_number: int,
        state: dict,
        agent_action: int,
        human_action: int,
        reward: float,
    ):
        """
        Collect training sample from human override.

        RLHF Dataset Format:
        {
            "state": {
                "inventory": 500,
                "backlog": 20,
                "pipeline": [100, 150],
                "demand_history": [80, 90, 95],
                "role": "wholesaler"
            },
            "agent_action": 120,
            "human_action": 150,
            "reward": -10.5,  # Cost delta (negative = human worse, positive = human better)
            "expert_preference": 1.0 if human better else -1.0
        }

        Stored in: rlhf_training_samples table
        """
        pass

    def export_training_dataset(
        self, game_ids: List[int], output_format: str = "jsonl"
    ) -> str:
        """
        Export RLHF training dataset for offline training.

        Args:
            game_ids: List of game IDs to export
            output_format: "jsonl" or "parquet"

        Returns:
            File path to exported dataset
        """
        pass
```

#### Task 14.2: RLHF Training Database (Day 15)
**File**: `backend/alembic/versions/20260128_rlhf_training_samples.py` (NEW)

**New Table**:
```sql
CREATE TABLE rlhf_training_samples (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    game_id INT NOT NULL,
    player_id INT NOT NULL,
    round_number INT NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    state_json JSON NOT NULL,  -- State representation
    agent_action INT NOT NULL,
    human_action INT NOT NULL,
    reward FLOAT NOT NULL,  -- Cost delta
    expert_preference FLOAT NOT NULL,  -- -1.0 to 1.0
    is_validated BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    INDEX idx_rlhf_game (game_id),
    INDEX idx_rlhf_validated (is_validated, created_at)
);
```

#### Task 14.3: RLHF Training API Endpoints (Day 16)
**File**: `backend/app/api/endpoints/rlhf.py` (NEW, ~150 lines)

**New Endpoints**:
```python
@router.post("/rlhf/collect-sample")
def collect_training_sample(...):
    """Manually collect RLHF training sample"""
    pass

@router.get("/rlhf/export-dataset")
def export_training_dataset(
    game_ids: List[int],
    output_format: str = "jsonl"
):
    """Export RLHF dataset for training"""
    pass

@router.get("/rlhf/dataset-stats")
def get_dataset_stats():
    """
    Get RLHF dataset statistics.

    Returns:
    {
        "total_samples": 1250,
        "validated_samples": 980,
        "games_count": 25,
        "agent_distribution": {
            "LLM": 400,
            "GNN": 420,
            "TRM": 430
        },
        "avg_reward": -5.2,
        "avg_override_delta": 35.8
    }
    """
    pass
```

#### Task 14.4: RLHF Training Script (Day 17)
**File**: `backend/scripts/training/train_rlhf.py` (NEW, ~300 lines)

**Training Script**:
```python
def train_with_rlhf(
    model_type: str,  # "TRM" or "GNN"
    dataset_path: str,
    epochs: int = 10,
    learning_rate: float = 1e-4,
    device: str = "cuda"
):
    """
    Train agent with RLHF dataset.

    Steps:
    1. Load base model (TRM or GNN)
    2. Load RLHF dataset (human overrides)
    3. Train with preference loss:
       - Reward model: predict human preference
       - Policy optimization: PPO or DPO
    4. Evaluate on validation set
    5. Save fine-tuned model

    Args:
        model_type: "TRM" or "GNN"
        dataset_path: Path to RLHF jsonl file
        epochs: Training epochs
        learning_rate: Learning rate
        device: "cuda" or "cpu"
    """
    pass
```

#### Task 14.5: RLHF Dashboard UI (Day 18)
**File**: `frontend/src/pages/RLHFDashboard.jsx` (NEW, ~350 lines)

**Dashboard Features**:
- Dataset statistics cards (total samples, validated, games)
- Agent distribution pie chart
- Reward distribution histogram
- Override delta scatter plot
- Export dataset button
- Training job launcher (trigger training script)

**UI Sections**:
1. **Dataset Overview** - Total samples, coverage, validation status
2. **Sample Distribution** - By agent type, by game, by round
3. **Quality Metrics** - Reward distribution, override analysis
4. **Export & Training** - Export dataset, launch training job
5. **Model Versions** - Track fine-tuned model versions

---

## Integration Points

### Phase 2 Integration (Copilot Mode)
- Dynamic mode switching allows toggling copilot on/off
- Multi-agent consensus provides alternative to single-agent recommendations
- Performance tracking validates copilot effectiveness

### Phase 3 Integration (ATP/CTP)
- Agent benchmarking includes ATP/CTP constraint adherence
- RLHF training includes ATP/CTP awareness in state representation
- Performance metrics track ATP breach frequency per agent

---

## Success Criteria

### Backend ✅
- [ ] Dynamic agent mode switching works mid-game
- [ ] Multi-agent consensus combines 3 agents correctly
- [ ] Agent performance tracking logs all decisions
- [ ] RLHF data collection captures overrides
- [ ] API endpoints functional (<500ms response time)

### Frontend ✅
- [ ] AgentModeSelector dropdown allows mode changes
- [ ] MultiAgentConsensusPanel displays all agent recommendations
- [ ] AgentBenchmarkDashboard shows real-time comparison
- [ ] RLHFDashboard provides dataset export functionality

### Performance ✅
- [ ] Mode switch: <100ms
- [ ] Consensus recommendation: <2000ms (3 agents + consensus)
- [ ] Performance metrics calculation: <200ms
- [ ] RLHF sample collection: <50ms

---

## Testing Strategy

### Unit Tests
- Mode switching validation logic
- Consensus methods (majority vote, weighted average, highest confidence)
- Performance metric calculations (accuracy, override rate, cost)
- RLHF dataset export/import

### Integration Tests
- End-to-end mode switch mid-game
- Multi-agent consensus in copilot mode
- Performance tracking across full game
- RLHF training pipeline (export → train → load)

### User Acceptance Tests
- Human player switches from manual → copilot → autonomous → manual
- Multi-agent consensus disagreement handling (low agreement score)
- Agent benchmark dashboard reflects accurate metrics
- RLHF-trained model improves over baseline

---

## Risk Mitigation

### Risk 1: Multi-Agent Consensus Latency
**Issue**: Calling 3 agents may take 2-5 seconds (LLM bottleneck)
**Mitigation**:
- Call agents in parallel (asyncio)
- Cache agent recommendations (1-minute TTL)
- Timeout agents after 5 seconds, use 2-agent consensus

### Risk 2: Mode Switch Race Condition
**Issue**: Player submits decision while mode is switching
**Mitigation**:
- Lock player during mode switch (block submissions)
- Queue pending submissions, process after switch completes
- WebSocket notification: "Mode switching, please wait..."

### Risk 3: RLHF Dataset Quality
**Issue**: Human overrides may not always be better (noisy labels)
**Mitigation**:
- Validation: Only collect samples where human decision reduced cost
- Expert labeling: Flag uncertain samples for manual review
- Reward shaping: Use multi-objective reward (cost + service level)

---

## Phase 4 Completion Checklist

- [ ] Dynamic Agent Mode Switching (Week 11)
  - [ ] Backend service, API endpoints, WebSocket events
  - [ ] Database migration for mode history
  - [ ] Frontend mode selector UI
- [ ] Multi-Agent Consensus (Week 12)
  - [ ] Ensemble service with 3 consensus methods
  - [ ] API endpoint for consensus recommendations
  - [ ] Frontend multi-agent panel
- [ ] Agent Performance Benchmarking (Week 13)
  - [ ] Performance tracker service
  - [ ] Database logging for decisions
  - [ ] Frontend benchmark dashboard
- [ ] RLHF Training Pipeline (Week 14)
  - [ ] Data collector service
  - [ ] Database for training samples
  - [ ] API endpoints for dataset export
  - [ ] Training script for TRM/GNN fine-tuning
  - [ ] Frontend RLHF dashboard

---

## Next Steps: Phase 5 (Optional)

After Phase 4, potential Phase 5 enhancements:

1. **Adaptive Agent Selection** - Auto-switch agents based on performance
2. **Agent Explainability (SHAP/LIME)** - Visualize agent decision factors
3. **Adversarial Testing** - Stress-test agents with extreme scenarios
4. **Agent Swarm Intelligence** - Coordinate multiple agents across supply chain
5. **Transfer Learning** - Apply learned policies to new supply chain configs

---

## Contact & Timeline

**Start Date**: 2026-01-28
**Target Completion**: 2026-02-25 (4 weeks)
**Phase**: Phase 4 (Multi-Agent Orchestration)
**Prerequisites**: Phase 0 ✅, Phase 1 ✅, Phase 2 ✅, Phase 3 ✅

**Week 11**: Dynamic agent mode switching
**Week 12**: Multi-agent consensus
**Week 13**: Agent performance benchmarking
**Week 14**: RLHF training pipeline
