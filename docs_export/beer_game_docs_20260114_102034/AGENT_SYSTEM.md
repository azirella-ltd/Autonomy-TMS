# Beer Game Agent System

This document provides comprehensive documentation for the AI agent system in The Beer Game, including configuration, strategies, and API usage.

## 🎯 Overview

The agent system enables automated gameplay with configurable AI agents that can:
- Participate in games alongside human players
- Use various decision-making strategies
- Adapt to different supply chain scenarios
- Provide insights into supply chain dynamics

### New OpenAI Agent Stack

The Autonomy LLM strategies now run on top of a multi-agent OpenAI Responses stack:

- **Node Agents** (retailer/wholesaler/distributor/factory) emit structured order
  proposals following `llm_agent/beer_game_openai_agents.py`'s JSON schema.
- A **Supervisor Agent** reviews those proposals and can clamp or rewrite orders
  before they reach the simulator.
- An optional **Global Planner Agent** publishes rolling base-stock and variance
  targets that the supervisor enforces.

All tiers are wired through the new `BeerGameAgentsOrchestrator` helper and use
strict JSON schemas with `response_format={'type': 'json_schema', 'strict': True}`.
The orchestrator also exposes a tool registry so you can plug simulator/forecast
functions as OpenAI tools without changing the agent prompts.

#### Using a Custom GPT

Set `AUTONOMY_CUSTOM_GPT` (or `BEER_GAME_CUSTOM_GPT`) to the model ID of your
Custom GPT and it will be preferred over `AUTONOMY_LLM_MODEL`.  You can also pass
the `custom_gpt` argument to `call_beer_game_gpt` or directly to the
`AutonomyStrategistSession` constructor.

```bash
export AUTONOMY_CUSTOM_GPT="user:my-custom-gpt"
```

Supervisor and global planners default to on/off via environment toggles:

- `AUTONOMY_ENABLE_SUPERVISOR` (default: `true`)
- `AUTONOMY_ENABLE_GLOBAL_AGENT` (default: `false`)

Override them per-request by supplying `supervisor=` or `global_agent=` when you
call `call_beer_game_gpt`.

## 🧠 Agent Strategies

### Available Strategies

| Strategy | Description | Best For |
|----------|-------------|----------|
| **naive** | Orders exactly the incoming demand | Baseline testing |
| **bullwhip** | Over-orders when demand increases | Demonstrating supply chain volatility |
| **conservative** | Maintains stable order quantities | Minimizing inventory costs |
| **ml_forecast** | Uses machine learning for demand prediction | Realistic demand planning |
| **optimizer** | Optimizes orders based on cost functions | Cost optimization |
| **reactive** | Reacts quickly to inventory changes | Volatile markets |

### Strategy Configuration

Each agent can be configured with strategy-specific parameters:

```json
{
  "strategy": "ml_forecast",
  "params": {
    "lookback_period": 5,
    "safety_stock": 2.0,
    "forecast_horizon": 3
  }
}
```

## 🔌 API Endpoints

### Base URL
All endpoints are relative to: `http://localhost:8000/api/v1`

### Authentication
Include JWT token in the `Authorization` header:
```
Authorization: Bearer <your_jwt_token>
```

### 1. Create Agent Game
```http
POST /agent-games/
```
**Request Body:**
```json
{
  "name": "AI Simulation",
  "max_rounds": 20,
  "player_count": 4,
  "demand_pattern": {
    "type": "step",
    "params": {
      "initial_demand": 4,
      "step_round": 5,
      "step_size": 2
    }
  },
  "agent_configs": [
    {
      "node_id": "retailer",
      "strategy": "ml_forecast",
      "params": {"lookback_period": 5}
    },
    {
      "node_id": "wholesaler",
      "strategy": "conservative",
      "params": {"safety_factor": 1.5}
    }
  ]
}
```

### 2. Start Game
```http
POST /agent-games/{game_id}/start
```
**Response:**
```json
{
  "status": "started",
  "current_round": 1,
  "game_state": { ... }
}
```

### 3. Play Round
```http
POST /agent-games/{game_id}/play-round
```
**Response:**
```json
{
  "round_completed": 2,
  "game_state": { ... },
  "metrics": {
    "inventory_costs": 120.50,
    "backlog_costs": 45.00,
    "service_level": 0.95
  }
}
```

### 4. Get Game State
```http
GET /agent-games/{game_id}
```

### 5. Update Agent Strategy
```http
PATCH /agent-games/{game_id}/agents/{agent_id}
```
**Request Body:**
```json
{
  "strategy": "bullwhip",
  "params": {"aggressiveness": 1.8}
}
```

## 🔄 WebSocket API

Connect to `ws://localhost:8000/ws/game/{game_id}` for real-time updates:

```javascript
const socket = new WebSocket('ws://localhost:8000/ws/game/123');

socket.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log('Game update:', update);
};
```

## 📊 Monitoring and Analytics

### Available Metrics
- Inventory levels
- Order history
- Backlog amounts
- Costs (holding, backlog, total)
- Service level
- Bullwhip effect metrics

### Exporting Data
```http
GET /agent-games/{game_id}/export
```

## 🔧 Configuration

### Environment Variables
```env
# Agent System
AGENT_STRATEGY_DEFAULT=ml_forecast
AGENT_UPDATE_INTERVAL=1000  # ms
MAX_CONCURRENT_AGENTS=10
```

### Strategy Parameters
Each strategy supports different parameters:

**ML Forecast**
- `lookback_period`: Number of previous rounds to consider
- `safety_stock`: Multiplier for safety stock calculation
- `forecast_horizon`: Number of rounds to forecast

**Bullwhip**
- `aggressiveness`: How much to over-order (1.0-3.0)
- `volatility_threshold`: Demand change that triggers over-ordering

**Conservative**
- `safety_factor`: Base safety stock multiplier
- `max_order_change`: Maximum change in order quantity per round
```http
PUT /api/v1/agent-games/{game_id}/agent-strategy?role=retailer&strategy=bullwhip
```

### Toggle demand visibility
```http
PUT /api/v1/agent-games/{game_id}/demand-visibility?visible=true
```

### Get game state
```http
GET /api/v1/agent-games/{game_id}/state
```

## Running the Demo

1. Start the backend server:
   ```bash
   cd backend
   uvicorn main:app --reload
   ```

2. In a new terminal, run the demo script:
   ```bash
   cd backend
   python3 -m scripts.demo_agents
   ```

## Customizing the Demo

Edit `backend/scripts/demo_agents.py` to:
- Change agent strategies
- Modify the number of rounds
- Adjust demand patterns
- Toggle demand visibility

## Implementation Details

- Agents are implemented in `backend/app/services/agents.py`
- The game service is in `backend/app/services/agent_game_service.py`
- API endpoints are defined in `backend/app/api/endpoints/agent_game.py`

## Training controls and hyperparameters

### Admin-facing controls

- **Dataset generation sliders.** The Autonomy Agent Training panel lets admins trigger synthetic dataset builds with custom simulator settings (lead times, inventory ranges, costs, inbound capacity, maximum order, SimPy smoothing). The UI sends these selections to `/model/generate-data`, which passes them directly into `generate_sim_training_windows` when assembling `.npz` corpora.
- **Training job launch knobs.** From the same panel an admin can choose data source (simulator or database), history window, forecast horizon, epoch count, device, and optional database connection/table. These values are converted into CLI arguments for `scripts/training/train_gnn.py`, so each run reflects the panel selections.
- **Job monitoring.** Running jobs can be stopped and their recent log output reviewed, providing manual lifecycle control without shell access.

### Backend-only configuration

- **Additional CLI switches.** The trainer supports extra flags—dataset paths, mixed-precision toggles, and custom checkpoint locations—but the admin UI does not surface them. They must be supplied when invoking the script directly.
- **Model architecture & normalization.** `SupplyChainTemporalGNN` fixes feature dimensions, hidden size, number of temporal layers, dropout, and normalization behaviour. Changing these requires code edits or a custom instantiation path.
- **Agent learning dynamics.** `SupplyChainAgent` exposes learning-rate, replay-buffer capacity, batch size, target-network sync cadence, policy-loss weighting, discount factor, and gradient clipping parameters. Defaults are hard-coded where agents are created and are not linked to admin selections.
- **Legacy trainer options.** The `train_tgnn.py` CLI offers additional arguments (batch size, sequence length, learning rate), but because the admin panel invokes the lightweight trainer, these knobs remain unavailable unless you run the script manually.

### Hyperparameters worth tuning

- **Architecture.** Hidden dimensions, number of temporal layers/attention heads, dropout, and sequence length balance model capacity against overfitting.
- **Training loop.** Optimizer choice, base learning rate (default `1e-3`), loss discount factor (`γ = 0.95`), mixed-precision usage, and epoch count govern convergence. Only the epoch count and device are exposed via the admin UI.
- **Reinforcement signals.** Replay-buffer size, mini-batch size, target-network update interval, policy/value loss weighting, discount factor, and gradient clipping control RL stability and are set in code.
- **Simulator parameters.** Lead-time, cost, and capacity ranges—as well as SimPy smoothing toggles—shape the training distribution. Because these are available in the admin dataset generator, they are practical levers for experimentation.

### Hyperparameter tuning support

At present the tooling launches a single training run with whichever parameters are supplied. There is no automated search over hyperparameter grids or Bayesian priors; any tuning requires orchestrating multiple runs externally (manual relaunches or a bespoke wrapper around `train_gnn.py`).

## Troubleshooting

- Ensure the backend server is running before starting the demo
- Check that your database is properly configured
- Verify that all required Python packages are installed
- Check the backend logs for any error messages
