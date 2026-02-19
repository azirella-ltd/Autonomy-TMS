# The Beer Game Guide

**Last Updated**: 2026-01-22

---

## Overview

The Beer Game is MIT's classic supply chain simulation that demonstrates the **bullwhip effect** - how small variations in retail demand amplify exponentially as you move upstream through the supply chain. Autonomy's implementation combines the classic game mechanics with AI agents, real-time analytics, and full integration with AWS Supply Chain services.

**Key Insight**: The Beer Game is NOT a separate system. It uses the same AWS SC planning and execution services (demand planning, inventory optimization, transfer orders, ATP) that power production supply chains. This validates that the core platform works in real scenarios.

---

## Why Play The Beer Game?

### Business Value

**1. Employee Training** (3-5x engagement vs. traditional)
- Hands-on supply chain learning
- Safe environment to make mistakes
- Immediate feedback and analytics
- Competitive leaderboards
- Understand bullwhip effect viscerally

**2. Agent Validation** (Risk-free testing)
- Test AI agents before production deployment
- Compare agent strategies (TRM vs. GNN vs. LLM)
- Identify edge cases and failure modes
- Build confidence in AI performance
- Benchmark against human planners

**3. Confidence Building** (Demonstrate AI value)
- Human vs. AI competitions
- Show 20-35% cost improvements
- Executive demonstrations
- Stakeholder buy-in
- Quantify ROI of AI agents

**4. Continuous Improvement** (RLHF)
- Human gameplay generates training data
- Learn from expert planners
- Improve agent strategies iteratively
- Crowdsource supply chain knowledge
- Discover new heuristics

---

## Game Mechanics

### Supply Chain Structure

**Classic 4-Echelon Topology**:
```
Market (Customer Demand)
    ↓
Retailer (0-1 week lead time)
    ↓ (2 weeks lead time)
Wholesaler
    ↓ (2 weeks lead time)
Distributor
    ↓ (2 weeks lead time)
Factory (infinite supply)
```

**Roles**:
- **Retailer**: Serves end customers, orders from Wholesaler
- **Wholesaler**: Serves Retailer, orders from Distributor
- **Distributor**: Serves Wholesaler, orders from Factory
- **Factory**: Produces product (no upstream supplier)

### Round Execution Flow

**Each round (1 week of game time)**:

**1. Receive Shipments**
```python
# Incoming shipments arrive after lead time
for node in [Retailer, Wholesaler, Distributor, Factory]:
    arriving_shipments = node.pipeline[current_round]
    node.inventory += arriving_shipments
```

**2. Fulfill Demand**
```python
# Serve downstream customers/nodes
for node in [Retailer, Wholesaler, Distributor, Factory]:
    demand = node.incoming_demand
    fulfilled = min(node.inventory, demand + node.backlog)

    node.inventory -= fulfilled
    node.backlog = max(0, demand + node.backlog - fulfilled)

    # Ship fulfilled quantity downstream
    shipment = create_shipment(quantity=fulfilled, lead_time=node.outbound_lead_time)
```

**3. Receive Orders**
```python
# Downstream node places order
for node in [Wholesaler, Distributor, Factory]:
    incoming_order = downstream_node.order_quantity
    node.incoming_demand = incoming_order  # Will be fulfilled next round
```

**4. Decide Order Quantity** (Player/Agent Decision)
```python
# Player or AI agent decides how much to order upstream
for node in [Retailer, Wholesaler, Distributor]:
    if node.player_type == "human":
        # Wait for player input via UI
        order_qty = await wait_for_player_decision(node.player_id)
    else:
        # AI agent decides
        order_qty = agent.compute_order(node)

    # Place order upstream
    create_transfer_order(
        from_node=node.upstream_node,
        to_node=node,
        quantity=order_qty,
        expected_arrival=current_round + node.inbound_lead_time
    )
```

**5. Update Costs**
```python
# Accumulate costs
for node in [Retailer, Wholesaler, Distributor, Factory]:
    node.holding_cost += 0.50 * max(0, node.inventory)  # $0.50/unit/week
    node.shortage_cost += 1.00 * node.backlog  # $1.00/unit/week
```

### Demand Pattern

**Classic Beer Game Demand**:
- Rounds 1-4: 4 units/week (stable)
- Rounds 5-52: 8 units/week (step increase)

**Why This Pattern?**:
- Tests response to demand shock
- Reveals over-ordering and under-ordering
- Demonstrates information delay effects
- Shows bullwhip amplification

**Variations** (configurable):
- Seasonal demand (sine wave)
- Random demand (stochastic)
- Promotional spikes
- Gradual ramp-up

---

## The Bullwhip Effect

### What It Is

**Definition**: Demand variability amplifies as you move upstream through the supply chain.

**Measurement**:
```python
bullwhip_ratio = variance(orders) / variance(demand)

# Example:
# Retailer sees customer demand variance = 10
# Wholesaler sees Retailer order variance = 30
# Distributor sees Wholesaler order variance = 90
# Factory sees Distributor order variance = 270
#
# Bullwhip ratios:
# - Wholesaler: 30/10 = 3.0
# - Distributor: 90/10 = 9.0
# - Factory: 270/10 = 27.0
```

### Why It Happens

**1. Information Delay**:
- Retailer doesn't share customer demand with upstream nodes
- Wholesaler only sees Retailer's orders (not true demand)
- Each node amplifies uncertainty by ordering extra "just in case"

**2. Lead Time Delay**:
- 2-week lead times mean decisions made today affect inventory 2 weeks later
- Players over-order when inventory is low, not realizing shipments are already in pipeline
- By the time shipments arrive, too much was ordered

**3. Batching**:
- Ordering in large batches instead of matching demand
- "Order 100 units every 5 weeks" instead of "Order 20 units every week"
- Creates artificial demand spikes

**4. Shortage Gaming**:
- When supplier has stockouts, customers over-order to get priority
- "I need 50, but I'll order 100 to ensure I get at least 50"
- Supplier sees inflated demand signal

### How to Mitigate

**1. Information Sharing**:
- Share true customer demand with all nodes (demand visibility)
- Use point-of-sale (POS) data instead of order history
- Collaborative forecasting

**2. Reduce Lead Times**:
- Faster transportation (air freight vs. ocean)
- Local sourcing
- Drop-shipping

**3. Order Smoothing**:
- Use exponential smoothing for order decisions
- Avoid over-reacting to single data points
- Order based on average demand, not last week's spike

**4. Base-Stock Policy**:
- Target inventory level = Expected demand over (lead time + review period) + safety stock
- Order up to target every period
- Reduces variance in orders

---

## Game Setup

### Creating a Game

**Via UI** ([frontend/src/pages/CreateMixedGame.jsx](frontend/src/pages/CreateMixedGame.jsx)):

1. Navigate to http://localhost:8088/games/create
2. Configure game settings:
   - **Name**: "My First Beer Game"
   - **Supply Chain Config**: "Default TBG" (or custom config)
   - **Max Rounds**: 52 (1 year)
   - **Demand Pattern**: Step increase, seasonal, random, etc.
3. Assign players to roles:
   - **Retailer**: Human (select user) or AI agent (select strategy)
   - **Wholesaler**: Human or AI
   - **Distributor**: Human or AI
   - **Factory**: Human or AI
4. Click "Create Game"

**Via API**:
```bash
POST /api/v1/mixed-games
{
  "name": "Training Game - Cohort 2024",
  "config_id": 1,  # Default TBG config
  "max_rounds": 52,
  "demand_pattern": {
    "type": "step",
    "initial_demand": 4,
    "step_round": 5,
    "step_demand": 8
  },
  "players": [
    {
      "role_name": "Retailer",
      "player_type": "human",
      "user_id": 10
    },
    {
      "role_name": "Wholesaler",
      "player_type": "human",
      "user_id": 11
    },
    {
      "role_name": "Distributor",
      "player_type": "agent",
      "agent_config": {
        "strategy": "conservative"
      }
    },
    {
      "role_name": "Factory",
      "player_type": "agent",
      "agent_config": {
        "strategy": "llm",
        "enable_supervisor": true
      }
    }
  ]
}
```

### Supply Chain Configurations

**Files**:
- `backend/app/models/supply_chain_config.py` - SupplyChainConfig model
- `backend/app/api/endpoints/supply_chain_config.py` - Config CRUD API

**Default Configurations**:

1. **Default TBG** (Classic Beer Game - Inventory Only)
   - **Topology**: Market Supply → Factory → Distributor → Wholesaler → Retailer → Market Demand
   - **Product**: Case (single finished good)
   - **Factory Type**: Inventory node (no manufacturing/BOM)
   - **Description**: Classic MIT Beer Game with inventory-only nodes

2. **Case TBG** (Single-Level Manufacturing)
   - **Topology**: Market Supply → Case Mfg → Distributor → Wholesaler → Retailer → Market Demand
   - **Products**: Case (FG), Six-Pack (component)
   - **BOM**: 1 Case = 4 Six-Packs
   - **Factory**: Case Mfg (MANUFACTURER master type)
   - **Description**: Case manufacturer consumes Six-Packs supplied by Market Supply

3. **Six-Pack TBG** (Two-Level Manufacturing)
   - **Topology**: Market Supply → Six-Pack Mfg → Case Mfg → Distributor → Wholesaler → Retailer → Market Demand
   - **Products**: Case (FG), Six-Pack (intermediate), Bottle (component)
   - **BOMs**:
     - 1 Case = 4 Six-Packs
     - 1 Six-Pack = 6 Bottles
   - **Factories**: Six-Pack Mfg, Case Mfg (both MANUFACTURER master type)
   - **Description**: Two-stage manufacturing: Bottles → Six-Packs → Cases

4. **Bottle TBG** (Three-Level Manufacturing)
   - **Topology**: Market Supply → Bottle Mfg → Six-Pack Mfg → Case Mfg → Distributor → Wholesaler → Retailer → Market Demand
   - **Products**: Case (FG), Six-Pack (intermediate), Bottle (intermediate), Ingredients (raw material)
   - **BOMs**:
     - 1 Case = 4 Six-Packs
     - 1 Six-Pack = 6 Bottles
     - 1 Bottle = 1 Ingredients
   - **Factories**: Bottle Mfg, Six-Pack Mfg, Case Mfg (all MANUFACTURER master type)
   - **Description**: Three-stage manufacturing with raw materials

5. **Three FG TBG** (Three Finished Goods - Inventory Only)
   - **Topology**: Market Supply → Factory → Distributor → Wholesaler → Retailer → Market Demand
   - **Products**: Lager Case, IPA Case, Dark Case (three finished goods)
   - **Factory Type**: Inventory node (no manufacturing/BOM)
   - **Demand Pattern**: Classic step increase (4 → 8 units/week at round 5)
   - **Description**: Three parallel product lines with inventory-only nodes

6. **Variable TBG** (Three Finished Goods with Stochastic Demand)
   - **Topology**: Market Supply → Factory → Distributor → Wholesaler → Retailer → Market Demand
   - **Products**: Lager Case, IPA Case, Dark Case (three finished goods)
   - **Factory Type**: Inventory node (no manufacturing/BOM)
   - **Demand Pattern**: LogNormal distribution (median=8.0, variance=8.0)
   - **Description**: Three FG with probabilistic demand instead of deterministic step increase

**Custom Configurations**:
```bash
POST /api/v1/supply-chain-configs
{
  "config_name": "My Custom Network",
  "description": "3-echelon with 2 DCs",
  "group_id": 1,
  "nodes": [
    {"node_name": "DC East", "sc_node_type": "DC", "master_type": "INVENTORY"},
    {"node_name": "DC West", "sc_node_type": "DC", "master_type": "INVENTORY"},
    {"node_name": "Factory", "sc_node_type": "Factory", "master_type": "MANUFACTURER"},
    ...
  ],
  "lanes": [
    {"origin_name": "Factory", "destination_name": "DC East", "lead_time_days": 7},
    {"origin_name": "Factory", "destination_name": "DC West", "lead_time_days": 10},
    ...
  ],
  "items": [
    {"item_name": "Product A", "item_type": "finished_good"},
    ...
  ]
}
```

---

## Assigning AI Agents

### Available Agent Strategies

**Files**: `backend/app/services/agents.py`

**Strategy Options**:
1. **naive**: Mirror incoming demand (baseline for comparison)
2. **bullwhip**: Intentionally over-order to demonstrate bullwhip effect
3. **conservative**: High safety stock, stable orders (risk-averse)
4. **ml_forecast**: ML-based demand prediction (TRM or GNN)
5. **optimizer**: Mathematical optimization (near-optimal)
6. **reactive**: Rapid response to inventory changes
7. **llm**: GPT-4 multi-agent system (strategic, explainable)

### How to Assign Agents

**Method 1: During Game Creation** (UI or API)
```bash
POST /api/v1/mixed-games
{
  "players": [
    {
      "role_name": "Retailer",
      "player_type": "agent",
      "agent_config": {
        "strategy": "ml_forecast",
        "model_path": "checkpoints/gnn/best_model.pth"
      }
    },
    ...
  ]
}
```

**Method 2: Pure Agent Game** (No humans)
```bash
POST /api/v1/agent-games
{
  "name": "Agent Benchmark",
  "config_id": 1,
  "max_rounds": 52,
  "agent_configs": [
    {"role_name": "Retailer", "strategy": "naive"},
    {"role_name": "Wholesaler", "strategy": "conservative"},
    {"role_name": "Distributor", "strategy": "ml_forecast"},
    {"role_name": "Factory", "strategy": "llm"}
  ]
}
```

**Method 3: Assign After Creation**
```bash
# Update player assignment
PUT /api/v1/mixed-games/{game_id}/players/{player_id}
{
  "player_type": "agent",
  "agent_config": {
    "strategy": "llm",
    "enable_supervisor": true,
    "enable_global_agent": false
  }
}
```

### Agent Configuration Options

**TRM/GNN Agents**:
```json
{
  "strategy": "ml_forecast",
  "model_path": "checkpoints/gnn/best_model.pth",  // or trm/best_model.pth
  "inference_device": "cuda"  // or "cpu"
}
```

**LLM Agent**:
```json
{
  "strategy": "llm",
  "model": "gpt-4",  // or gpt-5-mini, gpt-4o, etc.
  "enable_supervisor": true,  // Supervisor agent reviews decisions
  "enable_global_agent": false,  // Global planner provides guidance
  "temperature": 0.7,  // Randomness (0=deterministic, 1=creative)
  "max_tokens": 500
}
```

**Optimizer Agent**:
```json
{
  "strategy": "optimizer",
  "optimization_method": "linear_programming",  // or "dynamic_programming"
  "cost_weights": {
    "holding": 0.50,
    "shortage": 1.00,
    "ordering": 0.10
  }
}
```

---

## Playing the Game

### Human Player Workflow

**1. Join Game**:
- Navigate to http://localhost:8088/games
- Click on assigned game
- Wait for game to start

**2. View Game State** (Game Board UI):
- **Inventory**: Current stock on-hand
- **Backlog**: Unfulfilled demand (red alert if > 0)
- **Pipeline**: Incoming shipments by week
  - Example: "Week +1: 50 units, Week +2: 75 units"
- **Demand History**: Chart of recent downstream orders
- **Costs**: Cumulative holding cost + shortage cost

**3. Make Ordering Decision**:
- Enter order quantity in input field
- Submit decision
- System validates (non-negative, reasonable)
- Order is placed upstream

**4. Wait for Other Players**:
- Real-time WebSocket updates
- See when other players submit decisions
- Progress bar shows "3/4 players ready"

**5. Round Completes**:
- All outcomes calculated (shipments, fulfillment, costs)
- Updated game state displayed
- Charts updated
- Next round begins

**6. Game Ends**:
- After max_rounds (e.g., 52 weeks)
- Final scorecard displayed
- Leaderboard updated
- Detailed analytics available

### Real-Time Multiplayer

**Technology**: WebSocket connections via Socket.IO

**Files**:
- `backend/app/api/endpoints/websocket.py` - WebSocket handlers
- `frontend/src/services/gameService.js` - WebSocket client

**How It Works**:
```python
# Backend broadcasts to all players in game
await websocket_manager.broadcast_to_game(game_id, {
    "type": "round_completed",
    "round_number": 15,
    "game_state": {
        "Retailer": {"inventory": 45, "backlog": 12, ...},
        "Wholesaler": {"inventory": 120, "backlog": 0, ...},
        ...
    }
})
```

```javascript
// Frontend listens for updates
socket.on('round_completed', (data) => {
  setRoundNumber(data.round_number);
  setGameState(data.game_state);
  updateCharts(data.game_state);
});
```

**Benefits**:
- No page refresh needed
- Instant updates when round completes
- See other players' actions in real-time
- Live leaderboard updates

---

## Analytics & Reporting

### In-Game Analytics

**Real-Time Metrics** (visible during gameplay):
- **Inventory Level**: Line chart over time
- **Backlog**: Bar chart by round
- **Costs**: Stacked area chart (holding vs. shortage)
- **Orders Placed**: Line chart showing order quantities
- **Pipeline**: Sankey diagram showing in-transit inventory

**Network View**:
- Sankey diagram of supply chain flow
- Node sizes = inventory levels
- Edge widths = shipment quantities
- Color coding: Green (healthy), Yellow (low stock), Red (backlog)

### Post-Game Analytics

**Files**:
- `backend/app/api/endpoints/mixed_game.py` - Analytics endpoints
- `frontend/src/pages/GameReport.jsx` - Analytics dashboard

**Game Summary**:
```bash
GET /api/v1/mixed-games/{game_id}/summary

# Response
{
  "game_id": 123,
  "total_rounds": 52,
  "total_cost": 10500,
  "cost_breakdown": {
    "Retailer": {"holding": 500, "shortage": 1200, "total": 1700},
    "Wholesaler": {"holding": 800, "shortage": 400, "total": 1200},
    "Distributor": {"holding": 1200, "shortage": 0, "total": 1200},
    "Factory": {"holding": 6000, "shortage": 400, "total": 6400}
  },
  "bullwhip_metrics": {
    "Retailer": 1.2,  # Orders are 1.2x more variable than demand
    "Wholesaler": 2.8,
    "Distributor": 5.5,
    "Factory": 12.3
  },
  "service_levels": {
    "Retailer": 0.88,
    "Wholesaler": 0.93,
    "Distributor": 0.97,
    "Factory": 0.95
  }
}
```

**Round-by-Round History**:
```bash
GET /api/v1/mixed-games/{game_id}/history

# Response
{
  "rounds": [
    {
      "round_number": 1,
      "Retailer": {
        "inventory": 12,
        "backlog": 0,
        "incoming_shipment": 0,
        "demand": 4,
        "fulfilled": 4,
        "order_placed": 4,
        "holding_cost": 6.0,
        "shortage_cost": 0
      },
      ...
    },
    ...
  ]
}
```

**Visualizations**:
- **Bullwhip Chart**: Order variance by echelon
- **Inventory Oscillation**: Boom-bust cycles
- **Service Level Timeline**: % fulfilled by round
- **Cost Attribution**: Who contributed most to total cost?
- **Decision Quality**: Compare player orders to optimal

---

## Training Workflows

### Workflow 1: Onboarding New Planners

**Objective**: Teach supply chain fundamentals through hands-on gameplay.

**Process**:
1. **Baseline Game** (All naive agents)
   - Show typical bullwhip behavior
   - Observe high costs (~$15,000)

2. **Human Training Game** (Human players, AI coach)
   - Humans play all roles
   - AI agents provide hints in chat (future feature)
   - Debrief: Why did costs spike? Where did we over-order?

3. **Best Practices Game** (Humans vs. AI)
   - Humans play alongside optimal agent
   - Observe AI strategies
   - Learn: order smoothing, information sharing, base-stock

4. **Certification Game** (Human solo with AI opponents)
   - Human plays one role (e.g., Retailer)
   - AI agents play other roles
   - Must achieve <$8,000 total cost to pass

**Metrics**:
- Training time: 2-3 hours (4 games × 30 min each)
- Engagement: 4.5/5 (vs. 2.8/5 for traditional training)
- Knowledge retention: 85% at 3 months (vs. 45% traditional)

### Workflow 2: Agent Validation Before Production

**Objective**: Test AI agents in safe environment before deploying to real supply chains.

**Process**:
1. **Agent vs. Agent Benchmark** (100 games)
   ```bash
   # Run 100 games with each agent strategy
   for strategy in ["naive", "conservative", "ml_forecast", "llm", "optimizer"]:
       run_agent_games(strategy, num_games=100, config_id=1)
   ```

2. **Statistical Analysis**:
   ```python
   # Compare performance
   results = {
       "naive": {"mean_cost": 10500, "std": 1200, "service_level": 0.85},
       "conservative": {"mean_cost": 9200, "std": 800, "service_level": 0.92},
       "ml_forecast": {"mean_cost": 7800, "std": 600, "service_level": 0.93},
       "llm": {"mean_cost": 7500, "std": 700, "service_level": 0.94},
       "optimizer": {"mean_cost": 7200, "std": 400, "service_level": 0.95}
   }

   # Statistical significance test (t-test)
   p_value = ttest(ml_forecast.costs, naive.costs)
   # p < 0.001 → ml_forecast is significantly better
   ```

3. **Edge Case Testing**:
   - Demand spike (10x increase)
   - Supplier disruption (lead time doubles)
   - Quality issue (30% yield loss)
   - Does agent handle gracefully or crash?

4. **Human Review**:
   - Show executives best-performing agents
   - Demo LLM agent with natural language reasoning
   - Build confidence in AI decisions

5. **Production Deployment**:
   - If agent passes validation, deploy to real supply chain
   - Monitor performance vs. Beer Game predictions
   - Continuous learning from production data

**Metrics**:
- Validation games: 100-500 per agent
- Time to production: 2-4 weeks (vs. 6-12 months traditional AI validation)
- Confidence level: 95% (statistical significance)

### Workflow 3: Executive Demonstrations

**Objective**: Convince executives to invest in AI-powered planning.

**Process**:
1. **Setup**:
   - 30-minute demo session
   - Executive plays Retailer role
   - AI agents play other 3 roles

2. **Round 1-10** (Baseline):
   - Executive plays with typical strategies (order what you see)
   - Costs accumulate, bullwhip emerges
   - Highlight: "Your total cost is $4,200"

3. **Switch to AI Agent**:
   - AI agent takes over Retailer role
   - Executive observes agent decisions
   - Agent achieves $2,800 cost (33% improvement)

4. **Explainability** (LLM agent):
   - Show natural language reasoning for each decision
   - Example: "I'm ordering 95 units because demand is 100, I have 80 in pipeline, and I want 2 weeks safety stock"
   - Executive understands WHY agent is better

5. **ROI Calculation**:
   - "If we reduce supply chain costs by 30%, that's $15M annual savings"
   - "AI agent deployment cost: $500K"
   - "ROI: 30x in year 1"

**Metrics**:
- Demo time: 30 minutes
- Executive engagement: 9/10
- Follow-up meetings scheduled: 80%
- Investment approval rate: 65%

---

## Leaderboards & Competitions

### Leaderboard Types

**1. Individual Performance**:
- Rank players by total cost (lowest wins)
- Filter by role (best Retailer, best Wholesaler, etc.)
- Filter by time period (last 30 days, all time)

**2. Team Performance**:
- Rank game sessions by network-wide cost
- Best human team
- Best mixed human-AI team

**3. Agent Performance**:
- Rank AI agent strategies
- Filter by configuration
- Filter by game conditions (stable demand, volatile demand, etc.)

### Competition Formats

**1. Weekly Challenge**:
- All players play same game configuration
- Standard demand pattern
- Lowest cost wins
- Prizes: bragging rights, leaderboard badge

**2. Tournament**:
- Bracket-style elimination
- Players compete head-to-head (same game, compare costs)
- Semi-finals and finals
- Prizes: gift cards, recognition

**3. Human vs. AI Showdown**:
- Best human player vs. best AI agent
- Live-streamed to company
- Demonstrates AI capabilities
- Educational and entertaining

---

## Integration with AWS SC Services

### How Beer Game Uses Core Platform

**Demand Planning**:
```python
# Beer Game market demand → Forecast entity
forecast = Forecast(
    product_id=beer_case_id,
    site_id=market_id,
    forecast_date=current_date,
    forecast_quantity=8.0,  # Step increase to 8 units
    forecast_p50=8.0,
    forecast_p10=6.0,
    forecast_p90=10.0
)
```

**Inventory Target Calculation**:
```python
# Retailer's inventory policy
inv_policy = InvPolicy(
    product_id=beer_case_id,
    site_id=retailer_id,
    policy_type="doc_dem",  # Days of coverage based on demand
    target_value=14.0  # 14 days of coverage
)

# Calculate target inventory
target = await calculate_inventory_target(
    site_id=retailer_id,
    item_id=beer_case_id,
    demand_history=retailer.demand_history,
    policy=inv_policy
)
```

**Net Requirements Calculation**:
```python
# Agent ordering decision
net_requirement = max(
    target_inventory - on_hand - pipeline + backlog,
    0
)

order_quantity = net_requirement  # Or agent.compute_order(node)
```

**Transfer Orders**:
```python
# Place order upstream
transfer_order = await create_transfer_order_from_beer_game(
    origin_name="Wholesaler",
    destination_name="Retailer",
    item_name="Beer Case",
    quantity=order_quantity,
    expected_arrival_date=current_date + timedelta(weeks=2)
)
```

**Order Promising (ATP)**:
```python
# Check if Wholesaler can fulfill Retailer's order
atp_result = await calculate_atp(
    site_id=wholesaler_id,
    item_id=beer_case_id,
    requested_qty=order_quantity,
    requested_date=current_date
)

promised_qty = min(order_quantity, atp_result.available_qty)
```

**This ensures Beer Game validates production capabilities.**

---

## API Reference

### Create Mixed Game
```bash
POST /api/v1/mixed-games
{
  "name": "string",
  "config_id": int,
  "max_rounds": int,
  "players": [
    {
      "role_name": "string",
      "player_type": "human" | "agent",
      "user_id": int,  # If human
      "agent_config": {...}  # If agent
    }
  ]
}
```

### Start Game
```bash
POST /api/v1/mixed-games/{game_id}/start
```

### Play Round (Human Decision)
```bash
POST /api/v1/mixed-games/{game_id}/play-round
{
  "player_id": int,
  "order_quantity": float
}
```

### Get Game State
```bash
GET /api/v1/mixed-games/{game_id}/state

# Response
{
  "game_id": int,
  "current_round": int,
  "status": "in_progress" | "completed",
  "nodes": {
    "Retailer": {
      "inventory": float,
      "backlog": float,
      "pipeline": [float, float, ...],
      "last_order": float
    },
    ...
  }
}
```

### Get Game History
```bash
GET /api/v1/mixed-games/{game_id}/history
```

### Get Analytics
```bash
GET /api/v1/mixed-games/{game_id}/analytics

# Response includes:
# - Cost breakdown by node
# - Bullwhip metrics
# - Service levels
# - Inventory oscillation charts
```

---

## Troubleshooting

### Common Issues

**1. Players Not Synchronized**:
- **Symptom**: Round doesn't advance, stuck waiting
- **Cause**: One player disconnected or didn't submit
- **Fix**: Check player connection status, skip player or restart round

**2. Negative Inventory**:
- **Symptom**: Inventory < 0 displayed
- **Cause**: Bug in fulfillment logic
- **Fix**: Should be impossible (inventory can't go negative), check logs

**3. Bullwhip Ratio > 50**:
- **Symptom**: Extreme order amplification
- **Cause**: Player is over-reacting to demand changes
- **Fix**: This is expected behavior (demonstrates bullwhip), debrief with player

**4. LLM Agent Timeout**:
- **Symptom**: Agent decision takes >10s, round stalls
- **Cause**: OpenAI API slow or rate limited
- **Fix**: Fallback to heuristic agent, check OPENAI_API_KEY and quota

**5. Game Won't Start**:
- **Symptom**: Start button disabled
- **Cause**: Not all players assigned
- **Fix**: Ensure all 4 roles have player assignments

---

## Further Reading

- [AI_AGENTS.md](AI_AGENTS.md) - How AI agents work in Beer Game
- [PLANNING_CAPABILITIES.md](PLANNING_CAPABILITIES.md) - Planning services used by Beer Game
- [EXECUTION_CAPABILITIES.md](EXECUTION_CAPABILITIES.md) - Execution services used by Beer Game
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) - API usage and integration

---

## Academic References

**Original Beer Game**:
- Sterman, J. D. (1989). "Modeling Managerial Behavior: Misperceptions of Feedback in a Dynamic Decision Making Experiment". *Management Science*, 35(3), 321-339.

**Bullwhip Effect**:
- Lee, H. L., Padmanabhan, V., & Whang, S. (1997). "The Bullwhip Effect in Supply Chains". *Sloan Management Review*, 38(3), 93-102.

**Available in**: `docs/Knowledge/` folder
