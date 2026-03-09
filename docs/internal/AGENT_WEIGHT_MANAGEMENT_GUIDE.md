# Agent Weight Management Guide

## Overview

The Multi-Agent Orchestration system allows you to control how multiple AI agents (LLM, GNN, TRM) collaborate to make consensus decisions. This guide explains how to manage agent weights **manually** and how to enable **automatic learning** of optimal weights over time.

---

## Manual Weight Management

### Setting Weights That Sum to 1.0

**Yes**, you can manually set agent weights using ratios that sum to 1.0. The system automatically normalizes any weights you provide.

### How It Works

```javascript
// Example: Set weights manually
POST /api/mixed-games/{game_id}/set-agent-weights
{
  "weights": {
    "llm": 0.5,   // 50% weight to LLM (GPT-4)
    "gnn": 0.3,   // 30% weight to GNN
    "trm": 0.2    // 20% weight to TRM
  }
}
```

**Automatic Normalization**:
- If you provide `{llm: 5, gnn: 3, trm: 2}`, the system normalizes to `{llm: 0.5, gnn: 0.3, trm: 0.2}`
- Any ratios work: `{llm: 1, gnn: 1, trm: 1}` → equal weights (33.3% each)
- Zero weights are allowed: `{llm: 1, gnn: 0, trm: 0}` → use only LLM

### Manual Configuration Options

**Three Levels of Control**:

1. **Game-Level Weights** (default)
   - Applies to entire game
   - All players use same ensemble weights

2. **Player-Level Weights** (personalized)
   - Each player can have custom weights
   - Useful for personalized AI assistance

3. **Config-Level Weights** (supply chain specific)
   - Different weights per supply chain configuration
   - Optimized for specific network topologies

### UI Component

Use the `AgentWeightManager` component to adjust weights visually:

```jsx
<AgentWeightManager
  gameId={gameId}
  onWeightsChange={(newWeights) => {
    console.log('Weights updated:', newWeights);
  }}
/>
```

**Features**:
- Sliders for each agent (auto-normalizing)
- Pie chart visualization
- Real-time weight distribution preview
- Save/Reset buttons

---

## Automatic Weight Learning

### Yes, Weights Can Be Learned Over Time!

The system supports **5 adaptive learning algorithms** that automatically adjust weights based on agent performance.

### Learning Algorithms

#### 1. **EMA (Exponential Moving Average)**
**Best for**: Smooth, stable weight updates

**How it works**:
```
new_weight = old_weight + learning_rate × (performance - old_weight)
```

**Parameters**:
- `learning_rate`: 0.1 (default) - How quickly to adapt
  - Higher = faster adaptation (0.3-0.5)
  - Lower = more stable (0.05-0.1)

**Use case**: General-purpose, consistent environments

**Example**:
```javascript
POST /api/mixed-games/{game_id}/enable-adaptive-learning
{
  "learning_method": "ema",
  "learning_rate": 0.1
}
```

---

#### 2. **UCB (Upper Confidence Bound)**
**Best for**: Exploration of underused agents

**How it works**:
```
UCB = avg_reward + exploration_factor × sqrt(ln(total_trials) / agent_trials)
```

**Parameters**:
- `exploration_factor`: 1.0 (default) - Exploration vs exploitation tradeoff
  - Higher = more exploration (1.5-2.0)
  - Lower = more exploitation (0.5-0.8)

**Use case**: When you want to discover if underperforming agents improve in certain scenarios

**Example**:
```javascript
{
  "learning_method": "ucb",
  "exploration_factor": 1.5
}
```

---

#### 3. **Thompson Sampling**
**Best for**: Probabilistic exploration, handling uncertainty

**How it works**:
- Maintains Beta distribution for each agent
- Samples from distributions to choose weights
- Bayesian updating based on success/failure

**Parameters**:
- `exploration_factor`: 1.0 (default)

**Use case**: When outcomes are stochastic and you need robust exploration

**Example**:
```javascript
{
  "learning_method": "thompson",
  "exploration_factor": 1.0
}
```

---

#### 4. **Performance-Based (Direct Mapping)**
**Best for**: Simple, interpretable weight assignment

**How it works**:
```
weight[agent] = performance[agent] / sum(all_performances)
```

**Parameters**: None

**Use case**: When you want weights to directly reflect recent performance

**Example**:
```javascript
{
  "learning_method": "performance"
}
```

---

#### 5. **Gradient Descent**
**Best for**: Continuous optimization of cost function

**How it works**:
```
gradient = -(performance - avg_performance)
new_weight = old_weight - learning_rate × gradient
```

**Parameters**:
- `learning_rate`: 0.1 (default)

**Use case**: When optimizing a specific objective (e.g., minimize supply chain cost)

**Example**:
```javascript
{
  "learning_method": "gradient",
  "learning_rate": 0.15
}
```

---

## How Learning Works in Practice

### Step-by-Step Process

1. **Initialize with Equal Weights**
   ```
   {llm: 0.333, gnn: 0.333, trm: 0.333}
   ```

2. **Agents Make Decisions**
   - Each agent proposes an order quantity
   - Ensemble aggregates using current weights

3. **Measure Performance**
   - Calculate cost, service level, inventory metrics
   - Compare agent's suggestion vs actual outcome

4. **Update Weights**
   - Learning algorithm adjusts weights
   - Better-performing agents get higher weights

5. **Persist Learned Weights**
   - Weights saved to database
   - Used for next decision

### Example Scenario

**Initial State** (Round 1):
```
Weights: {llm: 0.33, gnn: 0.33, trm: 0.33}
```

**Round 5 Performance**:
```
LLM: 85% accuracy (cost = $1200)
GNN: 78% accuracy (cost = $1500)
TRM: 72% accuracy (cost = $1800)
```

**Updated Weights** (after learning):
```
Weights: {llm: 0.42, gnn: 0.35, trm: 0.23}
```

**Round 20 Performance** (after more learning):
```
LLM: 88% accuracy
GNN: 82% accuracy (improved!)
TRM: 70% accuracy
```

**Final Weights** (converged):
```
Weights: {llm: 0.45, gnn: 0.38, trm: 0.17}
```

---

## Database Persistence

### LearnedWeightConfig Table

Weights are automatically persisted to the database:

```sql
CREATE TABLE learned_weight_configs (
    id INT PRIMARY KEY,
    context_id INT NOT NULL,  -- Game/player/config ID
    context_type VARCHAR(20),  -- 'game', 'player', or 'config'
    weights JSON NOT NULL,  -- {"llm": 0.45, "gnn": 0.35, "trm": 0.20}
    learning_method VARCHAR(20),  -- 'ema', 'ucb', 'thompson', etc.
    num_samples INT,  -- Number of decisions used to learn
    performance_metrics JSON,  -- Per-agent performance scores
    metadata JSON,  -- Algorithm-specific data (UCB stats, beta params, etc.)
    is_active BOOLEAN,
    created_at DATETIME,
    updated_at DATETIME
);
```

### Confidence Score

The system calculates a **confidence score** based on sample size:

```python
confidence = min(1.0, num_samples / 30)
```

- **< 30 samples**: Low confidence (0.0 - 0.99)
- **≥ 30 samples**: Full confidence (1.0)

This prevents premature convergence on suboptimal weights.

---

## API Endpoints

### 1. Set Weights Manually

```http
POST /api/mixed-games/{game_id}/set-agent-weights
Content-Type: application/json

{
  "weights": {
    "llm": 0.5,
    "gnn": 0.3,
    "trm": 0.2
  },
  "context_type": "game"
}
```

**Response**:
```json
{
  "game_id": 1,
  "original_weights": {"llm": 5, "gnn": 3, "trm": 2},
  "normalized_weights": {"llm": 0.5, "gnn": 0.3, "trm": 0.2},
  "message": "Agent weights set successfully"
}
```

---

### 2. Get Current Weights

```http
GET /api/mixed-games/{game_id}/agent-weights
```

**Response**:
```json
{
  "weights": {"llm": 0.45, "gnn": 0.38, "trm": 0.17},
  "confidence": 0.85,
  "num_samples": 42,
  "performance_metrics": {
    "llm": 0.82,
    "gnn": 0.75,
    "trm": 0.68
  },
  "learning_method": "ema",
  "last_updated": "2026-01-28T10:30:00"
}
```

---

### 3. Enable Adaptive Learning

```http
POST /api/mixed-games/{game_id}/enable-adaptive-learning
Content-Type: application/json

{
  "learning_method": "ema",
  "learning_rate": 0.1,
  "exploration_factor": 1.0
}
```

**Response**:
```json
{
  "learning_enabled": true,
  "learning_method": "ema",
  "learning_rate": 0.1,
  "initial_weights": {"llm": 0.333, "gnn": 0.333, "trm": 0.333},
  "message": "Adaptive learning enabled. Weights will automatically update based on agent performance."
}
```

---

## Code Examples

### Backend: Using AdaptiveWeightLearner

```python
from app.services.adaptive_weight_learner import AdaptiveWeightLearner, LearningMethod

# Initialize learner
learner = AdaptiveWeightLearner(
    db=db_session,
    learning_method=LearningMethod.EMA,
    learning_rate=0.1
)

# After each agent decision
new_weights = learner.learn_weights(
    agent_type="llm",
    performance_score=0.85,  # 85% accuracy
    current_weights={"llm": 0.33, "gnn": 0.33, "trm": 0.33},
    context_id=game_id  # Persist to database
)

print(new_weights)  # {"llm": 0.38, "gnn": 0.31, "trm": 0.31}
```

---

### Backend: Using MultiAgentEnsemble with Learned Weights

```python
from app.services.multi_agent_ensemble import MultiAgentEnsemble, ConsensusMethod

# Get learned weights
adaptive_weights = learner.get_learned_weights(context_id=game_id)

# Create ensemble with learned weights
ensemble = MultiAgentEnsemble(
    agent_weights=adaptive_weights.weights,  # {"llm": 0.45, "gnn": 0.35, "trm": 0.20}
    consensus_method=ConsensusMethod.AVERAGING
)

# Make consensus decision
decisions = [
    AgentDecision(agent_type="llm", order_quantity=45, confidence=0.85),
    AgentDecision(agent_type="gnn", order_quantity=42, confidence=0.78),
    AgentDecision(agent_type="trm", order_quantity=48, confidence=0.72)
]

result = ensemble.make_consensus_decision(decisions)
print(result.final_decision)  # 44 (weighted average)
print(result.confidence)      # 0.89
print(result.agreement_score) # 0.95
```

---

### Frontend: Using AgentWeightManager

```jsx
import AgentWeightManager from './components/game/AgentWeightManager';

function GameRoom() {
  const [gameId, setGameId] = useState(1);

  const handleWeightsChange = (newWeights) => {
    console.log('Ensemble weights updated:', newWeights);
    // Update your game state or show confirmation
  };

  return (
    <Box>
      <AgentWeightManager
        gameId={gameId}
        onWeightsChange={handleWeightsChange}
      />
    </Box>
  );
}
```

---

## Best Practices

### When to Use Manual Weights

1. **Known Performance**: You have historical data showing which agents perform best
2. **Domain Knowledge**: You know certain agents excel in specific scenarios
3. **Testing**: You want to test specific weight configurations
4. **Explainability**: You need to explain why decisions were made

### When to Use Adaptive Learning

1. **Unknown Environment**: You're unsure which agents work best
2. **Dynamic Scenarios**: Performance varies across different game states
3. **Continuous Improvement**: You want the system to self-optimize
4. **A/B Testing**: Compare different learning algorithms

### Choosing a Learning Algorithm

| Algorithm | Best For | Parameters | Speed | Exploration |
|-----------|----------|------------|-------|-------------|
| **EMA** | General use, stable environments | learning_rate | Fast | Low |
| **UCB** | Unknown environments, discovery | exploration_factor | Medium | High |
| **Thompson** | Stochastic outcomes, uncertainty | exploration_factor | Medium | High |
| **Performance** | Simple, interpretable | None | Fast | None |
| **Gradient** | Cost minimization | learning_rate | Fast | None |

### Recommended Settings

**Conservative Learning** (safe, slow adaptation):
```json
{
  "learning_method": "ema",
  "learning_rate": 0.05
}
```

**Balanced Learning** (default):
```json
{
  "learning_method": "ema",
  "learning_rate": 0.1
}
```

**Aggressive Learning** (fast adaptation, higher risk):
```json
{
  "learning_method": "ucb",
  "learning_rate": 0.2,
  "exploration_factor": 1.5
}
```

---

## Monitoring & Debugging

### Check Weight Convergence

```http
GET /api/mixed-games/{game_id}/agent-weights
```

Look for:
- **High confidence** (>0.7) indicates stable weights
- **Large num_samples** (>30) indicates sufficient data
- **Performance metrics** show which agents perform best

### Visualize Weight Evolution

Track weights over time:

| Round | LLM | GNN | TRM | Confidence |
|-------|-----|-----|-----|------------|
| 1     | 0.33 | 0.33 | 0.33 | 0.03 |
| 10    | 0.38 | 0.35 | 0.27 | 0.33 |
| 20    | 0.42 | 0.36 | 0.22 | 0.67 |
| 30    | 0.45 | 0.38 | 0.17 | 1.00 |

**Convergence**: Weights stabilize around round 25-30

---

## Troubleshooting

### Weights Not Changing

**Problem**: Adaptive learning enabled but weights remain constant

**Solutions**:
1. Check if enough decisions have been made (need >5 samples minimum)
2. Verify learning_rate is not too small (<0.01)
3. Confirm agents have different performance scores

---

### Weights Oscillating

**Problem**: Weights fluctuate wildly, never converge

**Solutions**:
1. Lower learning_rate (try 0.05 instead of 0.2)
2. Switch from UCB/Thompson to EMA for stability
3. Check if performance metrics are noisy

---

### One Agent Dominates

**Problem**: One agent gets 90%+ weight, others near 0%

**Solutions**:
1. Enable exploration (use UCB with higher exploration_factor)
2. Check if other agents have bugs/issues
3. Consider if environment favors certain agent types

---

## Future Enhancements

1. **Per-Player Personalization**: Learn individual user preferences
2. **Contextual Weighting**: Different weights for different game states
3. **Meta-Learning**: Learn to choose the best learning algorithm
4. **Ensemble of Ensembles**: Combine multiple learning methods
5. **Counterfactual Evaluation**: Estimate "what if" for unused agents

---

## Summary

**Manual Weight Control**: ✅ **YES**
- Set ratios that sum to 1.0 (auto-normalized)
- Three context levels (game, player, config)
- UI component with sliders and visualization

**Automatic Weight Learning**: ✅ **YES**
- 5 learning algorithms (EMA, UCB, Thompson, Performance, Gradient)
- Automatic performance-based adaptation
- Database persistence with confidence scoring
- Convergence typically in 25-35 decisions

**Key Takeaway**: Start with manual weights if you know what works, or enable adaptive learning to discover optimal weights automatically. Both approaches are fully supported and can be switched at any time.
