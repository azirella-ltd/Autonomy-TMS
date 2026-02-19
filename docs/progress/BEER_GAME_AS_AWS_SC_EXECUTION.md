# The Beer Game as AWS SC Execution Engine

**Date**: 2026-01-21
**Architecture**: The Beer Game is a **specific configuration** of the AWS Supply Chain execution engine
**Key Insight**: Beer Game rounds = iterative execution of order promising + PO creation at each site, period by period

---

## Executive Summary

**Current Problem**: The Beer Game has its own custom engine (`engine.py`) separate from AWS SC planning (`planner.py`), duplicating logic and preventing integration.

**Solution**: Reimplement The Beer Game as **iterative AWS SC execution** where:
1. Market demand is generated each round
2. Each site executes **Order Promising** (AWS SC: `outbound_order_line` → fulfill from `inv_level`)
3. Each site executes **Purchase Order Creation** (AWS SC: `supply_plan` → `purchase_order`)
4. Agents make decisions using AWS SC tables (not custom game state)
5. State is absorbed from AWS SC entities each round (not custom initialization)

**Result**: The Beer Game becomes a **teaching/validation environment** for AWS SC planning, not a separate parallel system.

---

## Current Architecture (Wrong)

### Beer Game as Separate Engine

```
┌──────────────────────────────────────────────────────────────────┐
│                     BEER GAME ENGINE                             │
│  (backend/app/services/engine.py - Custom)                       │
├──────────────────────────────────────────────────────────────────┤
│  class Node:                                                     │
│    • inventory: int         ← Custom field                       │
│    • backlog: int           ← Custom field                       │
│    • pipeline_shipments     ← Custom field                       │
│    • order_pipe             ← Custom field                       │
│    • decide_order()         ← Custom logic                       │
│    • receive_shipment()     ← Custom logic                       │
│    • accrue_costs()         ← Custom logic                       │
│                                                                  │
│  class BeerLine:                                                 │
│    • tick()                 ← Custom round execution             │
│    • nodes: List[Node]      ← Custom data structure              │
└──────────────────────────────────────────────────────────────────┘
                              ↓
                    ❌ NO INTEGRATION
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│                   AWS SC PLANNING ENGINE                         │
│  (backend/app/services/sc_planning/planner.py)                   │
├──────────────────────────────────────────────────────────────────┤
│  class SupplyChainPlanner:                                       │
│    • run_planning()         ← AWS SC 3-step process              │
│    • demand_processor       ← Uses AWS SC entities               │
│    • net_requirements_calc  ← Uses AWS SC entities               │
│                                                                  │
│  AWS SC Entities:                                                │
│    • inv_level              ← Inventory levels                   │
│    • outbound_order_line    ← Customer orders                    │
│    • supply_plan            ← Supply recommendations             │
│    • purchase_order         ← PO execution                       │
│    • sourcing_rules         ← Routing logic                      │
└──────────────────────────────────────────────────────────────────┘
```

**Problems**:
1. ❌ Duplicate logic (Beer Game `Node` vs AWS SC `inv_level`)
2. ❌ Duplicate state (Beer Game `inventory` vs AWS SC `on_hand_qty`)
3. ❌ Can't use AWS SC planning for Beer Game
4. ❌ Can't use Beer Game agents for AWS SC planning
5. ❌ Training data doesn't reflect AWS SC operations

---

## Correct Architecture (Beer Game as AWS SC Config)

### Beer Game as Iterative AWS SC Execution

```
┌──────────────────────────────────────────────────────────────────┐
│                    THE BEER GAME (Round-by-Round)                │
│  Is a SPECIFIC CONFIGURATION of AWS SC Execution Engine          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Round 1:                                                        │
│    1. Generate Market Demand → outbound_order_line               │
│    2. Retailer: Order Promising (ATP check) → ship if available │
│    3. Retailer: PO Creation (agent decides) → purchase_order     │
│    4. Update inv_level tables                                    │
│                                                                  │
│  Round 2:                                                        │
│    1. POs from Round 1 arrive (lead time = 2)                   │
│    2. Retailer: Receive shipments → update inv_level            │
│    3. Generate new Market Demand → outbound_order_line           │
│    4. Retailer: Order Promising → fulfill demand                │
│    5. Retailer: PO Creation → purchase_order                     │
│    6. Wholesaler: Process Retailer's PO → order promising       │
│    7. Wholesaler: PO Creation → purchase_order upstream          │
│    8. Update inv_level tables                                    │
│                                                                  │
│  Round N: Repeat...                                             │
│                                                                  │
│  ✅ Uses AWS SC entities exclusively                             │
│  ✅ Agents read from inv_level, write to purchase_order          │
│  ✅ Order promising uses sourcing_rules for routing              │
│  ✅ State absorbed from AWS SC tables each round                 │
└──────────────────────────────────────────────────────────────────┘
                              ↓
                    ✅ USES AWS SC ENGINE
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│            AWS SC ORDER PROMISING & EXECUTION ENGINE             │
│  (backend/app/services/sc_execution/)                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Order Promising (per site, per round):                      │
│     • Read: outbound_order_line (demand from downstream)         │
│     • Read: inv_level (current on_hand_qty)                      │
│     • Logic: Check ATP, allocate inventory                       │
│     • Write: shipment records, update inv_level                  │
│                                                                  │
│  2. Purchase Order Creation (per site, per round):              │
│     • Read: inv_level (current state)                            │
│     • Read: supply_plan (recommendations from planning)          │
│     • Agent Decision: Order quantity (TRM/GNN/RL/LLM)            │
│     • Write: purchase_order (PO to upstream supplier)            │
│                                                                  │
│  3. State Management:                                            │
│     • Import: Load current state from inv_level                  │
│     • Update: Modify inv_level after each operation              │
│     • Export: Persist final state to database                    │
│                                                                  │
│  ✅ Single execution engine for Beer Game & Production           │
│  ✅ Uses AWS SC entities and operations                          │
│  ✅ Agents operate on real AWS SC tables                         │
└──────────────────────────────────────────────────────────────────┘
```

---

## Mapping: Beer Game Mechanics → AWS SC Operations

### Round Execution Flow (AWS SC Implementation)

| Beer Game Step | AWS SC Entity | AWS SC Operation | Agent Role |
|----------------|---------------|------------------|------------|
| **1. Generate Market Demand** | `outbound_order_line` | Insert customer order | System |
| **2. Receive Shipments** | `inv_level.in_transit_qty` → `on_hand_qty` | Move pipeline to inventory | System |
| **3. Fulfill Demand (Order Promising)** | `outbound_order_line` → `inv_level` | ATP check, allocate, ship | System |
| **4. Calculate Backlog** | `inv_level.backorder_qty` | Unfulfilled demand | System |
| **5. Agent Decision** | `supply_plan` | Calculate order quantity | **Agent** |
| **6. Place Order (PO Creation)** | `purchase_order` | Create PO to upstream | **Agent** |
| **7. Update Pipeline** | `inv_level.in_transit_qty` | Track in-transit qty | System |
| **8. Accrue Costs** | `inv_level` + cost params | Calculate holding/backlog cost | System |

### AWS SC Entity Mapping

| Beer Game Concept | AWS SC Entity | AWS SC Field | Notes |
|-------------------|---------------|--------------|-------|
| **Retailer/Wholesaler/etc.** | `site` | `site_id`, `site_type` | site_type = "INVENTORY" |
| **Cases/Six-Packs/etc.** | `product` | `item_id` | Single item for classic Beer Game |
| **Inventory** | `inv_level` | `on_hand_qty` | Current inventory |
| **Backlog** | `inv_level` | `backorder_qty` | Unfulfilled orders |
| **Pipeline** | `inv_level` | `in_transit_qty` | Orders in transit |
| **Customer Demand** | `outbound_order_line` | `ordered_quantity`, `requested_delivery_date` | Market demand |
| **Upstream Order** | `purchase_order` | `po_number`, quantity | Order to supplier |
| **Shipment** | `inbound_order_line` | `shipped_quantity` | Goods received |
| **Lead Time** | `sourcing_rules` | `lead_time_days` | 2 weeks (classic) |
| **Holding Cost** | `inv_policy` | Extension: `holding_cost_per_unit` | 0.5/unit/week |
| **Backlog Cost** | `inv_policy` | Extension: `backlog_cost_per_unit` | 1.0/unit/week |

---

## Detailed AWS SC Execution Flow

### Round N Execution (Period-by-Period)

```python
# Pseudocode for Beer Game Round Execution using AWS SC

async def execute_beer_game_round(game_id: int, round_number: int):
    """
    Execute Beer Game round N using AWS SC execution engine.

    This is THE CORE: Beer Game is just iterative AWS SC execution.
    """

    # ========================================================================
    # STEP 1: ABSORB CURRENT STATE (AWS SC Pattern)
    # ========================================================================
    # Load current state from AWS SC entities (not custom game state)

    sites = await get_sites_for_game(game_id)  # site table
    items = await get_items_for_game(game_id)  # product table

    for site in sites:
        for item in items:
            # Read current inventory level (AWS SC entity)
            inv_level = await get_inv_level(site.site_id, item.item_id)

            # State is in AWS SC format:
            # - inv_level.on_hand_qty (not inventory)
            # - inv_level.backorder_qty (not backlog)
            # - inv_level.in_transit_qty (not pipeline)


    # ========================================================================
    # STEP 2: RECEIVE SHIPMENTS (Lead Time Completion)
    # ========================================================================
    # Purchase orders placed in round (N - lead_time) arrive now

    # Query POs that are arriving this round
    arriving_pos = await get_arriving_purchase_orders(
        game_id=game_id,
        arrival_round=round_number
    )

    for po in arriving_pos:
        # Move from in_transit_qty to on_hand_qty
        await receive_purchase_order(
            site_id=po.destination_site_id,
            item_id=po.item_id,
            quantity=po.quantity
        )

        # Updates AWS SC inv_level:
        # inv_level.in_transit_qty -= quantity
        # inv_level.on_hand_qty += quantity

        # Mark PO as RECEIVED
        po.status = "RECEIVED"
        po.actual_delivery_date = current_round_date


    # ========================================================================
    # STEP 3: GENERATE MARKET DEMAND (Round 1 Only or Per-Round Pattern)
    # ========================================================================
    if round_number == 1 or is_continuous_demand_game:
        # Generate customer demand using Beer Game pattern
        demand_qty = generate_beer_game_demand(round_number)

        # Create outbound order line (AWS SC entity)
        await create_outbound_order_line(
            site_id="retailer_001",
            item_id="cases",
            ordered_quantity=demand_qty,
            requested_delivery_date=current_round_date,
            order_date=current_round_date
        )


    # ========================================================================
    # STEP 4: ORDER PROMISING (Per Site, Downstream First)
    # ========================================================================
    # Process orders from downstream → upstream
    # Retailer → Wholesaler → Distributor → Factory

    for site in sites_in_downstream_order:
        # Get demand from downstream (outbound orders or POs)
        if site.site_type == "retailer":
            # Demand from market
            demand = await get_outbound_order_lines(
                site_id=site.site_id,
                delivery_date=current_round_date
            )
        else:
            # Demand from downstream site (POs from previous iteration)
            demand = await get_purchase_orders_for_supplier(
                supplier_site_id=site.site_id,
                delivery_date=current_round_date
            )

        # Execute Order Promising (ATP logic)
        for order in demand:
            inv_level = await get_inv_level(site.site_id, order.item_id)

            # ATP (Available to Promise)
            atp = inv_level.on_hand_qty - inv_level.allocated_qty

            if atp >= order.quantity:
                # Full fulfillment
                shipped_qty = order.quantity
                inv_level.on_hand_qty -= shipped_qty
                inv_level.backorder_qty = 0
            else:
                # Partial fulfillment
                shipped_qty = atp
                inv_level.on_hand_qty = 0
                inv_level.backorder_qty = order.quantity - shipped_qty

            # Record shipment
            await create_shipment_record(
                from_site_id=site.site_id,
                to_site_id=order.destination_site_id,
                item_id=order.item_id,
                shipped_quantity=shipped_qty,
                shipment_date=current_round_date,
                arrival_date=current_round_date + lead_time_days
            )

            # Update inv_level (AWS SC entity)
            await update_inv_level(inv_level)


    # ========================================================================
    # STEP 5: AGENT DECISION (Purchase Order Quantity)
    # ========================================================================
    # Each agent reads AWS SC entities, decides order quantity

    for site in sites:
        # Get agent for this site
        agent = await get_agent_for_site(site.site_id, game_id)

        # Agent reads AWS SC state (not custom game state)
        state = {
            "site_id": site.site_id,
            "item_id": "cases",
            "on_hand_qty": inv_level.on_hand_qty,
            "backorder_qty": inv_level.backorder_qty,
            "in_transit_qty": inv_level.in_transit_qty,
            "incoming_demand": recent_demand_qty,
        }

        # Agent decides order quantity
        # (TRM/GNN/RL/LLM agent uses AWS SC fields)
        order_qty = await agent.decide_order(state)

        # Agent returns order quantity (no other game logic)


    # ========================================================================
    # STEP 6: PURCHASE ORDER CREATION
    # ========================================================================
    # Create PO to upstream supplier based on agent decision

    for site in sites:
        if site.site_type == "manufacturer":
            continue  # Factory has infinite supply

        # Get upstream supplier from sourcing_rules
        sourcing_rule = await get_sourcing_rule(
            destination_site_id=site.site_id,
            item_id="cases"
        )

        # Create purchase order (AWS SC entity)
        po = await create_purchase_order(
            po_number=f"PO-{game_id}-{round_number}-{site.site_id}",
            supplier_site_id=sourcing_rule.source_site_id,
            destination_site_id=site.site_id,
            item_id="cases",
            quantity=order_qty,
            order_date=current_round_date,
            requested_delivery_date=current_round_date + sourcing_rule.lead_time_days,
            status="APPROVED",  # Auto-approve in Beer Game
            game_id=game_id,
            round_number=round_number
        )

        # Update in_transit_qty (AWS SC field)
        inv_level.in_transit_qty += order_qty
        await update_inv_level(inv_level)


    # ========================================================================
    # STEP 7: COST ACCRUAL
    # ========================================================================
    # Calculate holding and backlog costs using inv_policy

    for site in sites:
        inv_level = await get_inv_level(site.site_id, "cases")
        inv_policy = await get_inv_policy(site.site_id, "cases")

        # Calculate costs
        holding_cost = inv_level.on_hand_qty * inv_policy.holding_cost_per_unit
        backlog_cost = inv_level.backorder_qty * inv_policy.backlog_cost_per_unit
        total_cost = holding_cost + backlog_cost

        # Store cost (extend inv_level or use separate cost table)
        await record_round_cost(
            game_id=game_id,
            round_number=round_number,
            site_id=site.site_id,
            holding_cost=holding_cost,
            backlog_cost=backlog_cost,
            total_cost=total_cost
        )


    # ========================================================================
    # STEP 8: PERSIST ROUND STATE
    # ========================================================================
    # All state is already in AWS SC entities
    # No custom game state to persist

    await mark_round_complete(game_id, round_number)
```

---

## Database Schema Changes Required

### Extend AWS SC Entities for Beer Game

#### 1. `inv_level` Extensions (Beer Game Costs)

```sql
ALTER TABLE inv_level ADD COLUMN holding_cost_per_unit DOUBLE DEFAULT 0.5;
ALTER TABLE inv_level ADD COLUMN backlog_cost_per_unit DOUBLE DEFAULT 1.0;
ALTER TABLE inv_level ADD COLUMN total_cost_accrued DOUBLE DEFAULT 0.0;

-- Game tracking
ALTER TABLE inv_level ADD COLUMN game_id INTEGER REFERENCES games(id);
ALTER TABLE inv_level ADD COLUMN round_number INTEGER;
```

#### 2. `purchase_order` Extensions (Beer Game Tracking)

```sql
ALTER TABLE purchase_order ADD COLUMN game_id INTEGER REFERENCES games(id);
ALTER TABLE purchase_order ADD COLUMN round_number INTEGER;  -- Round PO was placed
ALTER TABLE purchase_order ADD COLUMN arrival_round INTEGER;  -- Round PO arrives

-- Index for queries
CREATE INDEX idx_po_game_round ON purchase_order(game_id, round_number);
CREATE INDEX idx_po_arrival_round ON purchase_order(game_id, arrival_round);
```

#### 3. `outbound_order_line` Extensions

```sql
ALTER TABLE outbound_order_line ADD COLUMN game_id INTEGER REFERENCES games(id);
ALTER TABLE outbound_order_line ADD COLUMN round_number INTEGER;
CREATE INDEX idx_outbound_game_round ON outbound_order_line(game_id, round_number);
```

#### 4. New Table: `beer_game_round` (Round Summary)

```sql
CREATE TABLE beer_game_round (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER REFERENCES games(id) NOT NULL,
    round_number INTEGER NOT NULL,

    -- Market demand (if generated this round)
    market_demand_qty DOUBLE,

    -- Aggregate metrics
    total_holding_cost DOUBLE DEFAULT 0.0,
    total_backlog_cost DOUBLE DEFAULT 0.0,
    total_cost DOUBLE DEFAULT 0.0,

    -- State snapshot (aggregate)
    total_on_hand_qty DOUBLE,
    total_backorder_qty DOUBLE,
    total_in_transit_qty DOUBLE,

    -- Metadata
    completed_at DATETIME,

    UNIQUE(game_id, round_number)
);

CREATE INDEX idx_beer_game_round ON beer_game_round(game_id, round_number);
```

---

## Agent Interface Changes

### Current Agent Interface (Wrong)

```python
# Current: Agents receive custom game state
class AgentPolicy:
    def order(self, observation: Dict) -> int:
        # observation has custom Beer Game fields:
        # - inventory (custom)
        # - backlog (custom)
        # - pipeline_on_order (custom)
        pass
```

### New Agent Interface (AWS SC Compliant)

```python
# New: Agents receive AWS SC state
class AWSCAgentPolicy:
    async def decide_order(self, state: AWSCState) -> int:
        """
        Agent decides order quantity using AWS SC entities.

        Args:
            state: AWS SC state with fields:
                - site_id: str
                - item_id: str
                - on_hand_qty: float (AWS SC: inv_level.on_hand_qty)
                - backorder_qty: float (AWS SC: inv_level.backorder_qty)
                - in_transit_qty: float (AWS SC: inv_level.in_transit_qty)
                - incoming_demand: float (recent demand qty)
                - lead_time_days: int (AWS SC: sourcing_rules.lead_time_days)

        Returns:
            order_qty: Order quantity to place upstream
        """
        pass


# TRM Agent Example (AWS SC Compliant)
class TRMAgent(AWSCAgentPolicy):
    async def decide_order(self, state: AWSCState) -> int:
        # Read AWS SC fields
        on_hand = state["on_hand_qty"]
        backorder = state["backorder_qty"]
        in_transit = state["in_transit_qty"]
        demand = state["incoming_demand"]

        # TRM model prediction
        order_qty = self.model.predict(
            on_hand_qty=on_hand,
            backorder_qty=backorder,
            in_transit_qty=in_transit,
            demand_qty=demand
        )

        return int(order_qty)


# GNN Agent Example (AWS SC Compliant)
class GNNAgent(AWSCAgentPolicy):
    async def decide_order(self, state: AWSCState) -> int:
        # Build graph from AWS SC entities
        graph = await self.build_supply_chain_graph(state["site_id"])

        # GNN prediction
        order_qty = self.model.predict(graph)

        return int(order_qty)


# RL Agent Example (AWS SC Compliant)
class RLAgent(AWSCAgentPolicy):
    async def decide_order(self, state: AWSCState) -> int:
        # Build observation from AWS SC state
        obs = np.array([
            state["on_hand_qty"],
            state["backorder_qty"],
            state["in_transit_qty"],
            state["incoming_demand"]
        ])

        # RL policy
        action, _ = self.model.predict(obs)

        return int(action)
```

---

## Implementation Plan

### Phase 1: Create AWS SC Execution Engine (Week 1-2)

**New Module**: `backend/app/services/sc_execution/`

```
sc_execution/
├── __init__.py
├── order_promising.py      # Order promising (ATP) logic
├── po_creation.py           # Purchase order creation
├── state_manager.py         # AWS SC state import/export
├── beer_game_executor.py    # Round-by-round Beer Game execution
└── cost_calculator.py       # Holding/backlog cost calculation
```

**Files to Create**:
1. `order_promising.py` - ATP check, inventory allocation, shipment creation
2. `po_creation.py` - PO creation from agent decisions
3. `state_manager.py` - Load/save state from AWS SC entities
4. `beer_game_executor.py` - Round execution orchestrator
5. `cost_calculator.py` - Cost accrual using inv_policy

### Phase 2: Update Database Schema (Week 2)

1. Extend `inv_level` with cost fields
2. Extend `purchase_order` with game tracking
3. Extend `outbound_order_line` with game tracking
4. Create `beer_game_round` summary table

### Phase 3: Refactor Agent Interface (Week 3)

1. Create `AWSCAgentPolicy` base class
2. Update TRM agent to use AWS SC state
3. Update GNN agent to use AWS SC state
4. Update RL agent to use AWS SC state
5. Update LLM agent to use AWS SC state

### Phase 4: Migrate Beer Game to AWS SC Execution (Week 4)

1. Replace `engine.py:BeerLine.tick()` with `beer_game_executor.execute_round()`
2. Update `mixed_game_service.py` to use AWS SC execution
3. Remove custom game state (Node class)
4. Use AWS SC entities exclusively

### Phase 5: Update Training Data Generation (Week 5)

1. Update `generate_simpy_dataset.py` to use AWS SC execution
2. Training data comes from AWS SC entities (not custom schema)
3. Agents trained on AWS SC state format

### Phase 6: Testing & Validation (Week 6)

1. Verify Beer Game results match original implementation
2. Test all agent types with AWS SC state
3. Validate cost calculations
4. End-to-end game execution test

---

## Benefits of This Architecture

### 1. **Single Source of Truth**
✅ All state in AWS SC entities (`inv_level`, `purchase_order`, `outbound_order_line`)
✅ No duplicate state (Beer Game `inventory` vs AWS SC `on_hand_qty`)
✅ Beer Game and production planning use same data model

### 2. **Agents Work in Production**
✅ Agents trained on AWS SC state format
✅ Can deploy Beer Game agents directly to production AWS SC environments
✅ Training data reflects real AWS SC operations

### 3. **Beer Game as Teaching Tool**
✅ Beer Game validates AWS SC execution logic
✅ Demonstrates AWS SC concepts (order promising, PO creation, ATP)
✅ Students learn AWS SC, not custom Beer Game mechanics

### 4. **Eliminates Code Duplication**
❌ Delete: `engine.py:Node` class (375 lines)
❌ Delete: `engine.py:BeerLine` class (200 lines)
✅ Replace with: `beer_game_executor.py` (uses AWS SC operations)

### 5. **AWS SC Compliance**
✅ Uses AWS SC entities: `site`, `product`, `inv_level`, `purchase_order`, `outbound_order_line`
✅ Uses AWS SC fields: `on_hand_qty`, `backorder_qty`, `in_transit_qty`, `lead_time_days`
✅ Uses AWS SC operations: Order promising, PO creation, ATP check

---

## Example: Round 3 Execution (Complete Flow)

```python
# Round 3 of Beer Game using AWS SC execution

# ========== ROUND 3 START ==========

# 1. RECEIVE SHIPMENTS (POs from Round 1 arrive, lead time = 2)
po_round1 = PurchaseOrder.query.filter_by(
    game_id=1,
    arrival_round=3  # Placed in round 1, lead time = 2
).all()

for po in po_round1:
    # Update inv_level (AWS SC entity)
    inv_level = InvLevel.query.filter_by(
        site_id=po.destination_site_id,
        item_id=po.item_id
    ).first()

    inv_level.in_transit_qty -= po.quantity
    inv_level.on_hand_qty += po.quantity
    po.status = "RECEIVED"


# 2. GENERATE MARKET DEMAND (Round 3 pattern)
demand = generate_beer_game_demand(round_number=3)  # e.g., 8 units

outbound_order = OutboundOrderLine(
    order_id="MARKET-GAME1-R3",
    site_id="retailer_001",
    item_id="cases",
    ordered_quantity=demand,
    requested_delivery_date=current_date,
    game_id=1,
    round_number=3
)
db.session.add(outbound_order)


# 3. ORDER PROMISING (Retailer fulfills market demand)
retailer_inv = InvLevel.query.filter_by(
    site_id="retailer_001",
    item_id="cases"
).first()

atp = retailer_inv.on_hand_qty - retailer_inv.allocated_qty

if atp >= demand:
    # Full fulfillment
    shipped = demand
    retailer_inv.on_hand_qty -= shipped
    retailer_inv.backorder_qty = 0
else:
    # Partial fulfillment
    shipped = atp
    retailer_inv.on_hand_qty = 0
    retailer_inv.backorder_qty = demand - shipped

db.session.commit()


# 4. AGENT DECISION (Retailer agent decides order quantity)
retailer_agent = get_agent("retailer_001", game_id=1)

state = {
    "site_id": "retailer_001",
    "item_id": "cases",
    "on_hand_qty": retailer_inv.on_hand_qty,
    "backorder_qty": retailer_inv.backorder_qty,
    "in_transit_qty": retailer_inv.in_transit_qty,
    "incoming_demand": demand
}

order_qty = await retailer_agent.decide_order(state)  # e.g., 12 units


# 5. PURCHASE ORDER CREATION (Retailer orders from Wholesaler)
po = PurchaseOrder(
    po_number="PO-GAME1-R3-RETAILER",
    supplier_site_id="wholesaler_001",
    destination_site_id="retailer_001",
    item_id="cases",
    quantity=order_qty,
    order_date=current_date,
    requested_delivery_date=current_date + timedelta(days=14),  # 2 weeks
    status="APPROVED",
    game_id=1,
    round_number=3,  # Placed in round 3
    arrival_round=5  # Will arrive in round 5 (lead time = 2)
)
db.session.add(po)

retailer_inv.in_transit_qty += order_qty
db.session.commit()


# 6. REPEAT FOR WHOLESALER, DISTRIBUTOR, FACTORY
# (Each site processes demand from downstream, places PO upstream)


# 7. COST ACCRUAL
inv_policy = InvPolicy.query.filter_by(
    site_id="retailer_001",
    item_id="cases"
).first()

holding_cost = retailer_inv.on_hand_qty * inv_policy.holding_cost_per_unit
backlog_cost = retailer_inv.backorder_qty * inv_policy.backlog_cost_per_unit
total_cost = holding_cost + backlog_cost

# Record in beer_game_round table
round_record = BeerGameRound(
    game_id=1,
    round_number=3,
    market_demand_qty=demand,
    total_holding_cost=sum_all_holding_costs,
    total_backlog_cost=sum_all_backlog_costs,
    total_cost=sum_all_costs,
    completed_at=datetime.now()
)
db.session.add(round_record)
db.session.commit()

# ========== ROUND 3 COMPLETE ==========
```

---

## Conclusion

**Key Insight**: The Beer Game is not a separate game engine—it's a **specific configuration** of AWS Supply Chain execution with:
- 4 sites (Retailer, Wholesaler, Distributor, Factory)
- 1 item (Cases)
- 2-week lead times
- Iterative round-by-round execution
- Order promising + PO creation at each site

**Implementation**: Replace custom Beer Game engine with AWS SC execution engine that:
1. Absorbs state from AWS SC entities each round
2. Executes order promising (ATP check, fulfill demand)
3. Agents decide order quantities using AWS SC state
4. Creates purchase orders to upstream suppliers
5. Updates AWS SC entities (inv_level, purchase_order, outbound_order_line)

**Result**: Beer Game becomes a **teaching/validation tool** for AWS SC planning, not a parallel system.

---

**Status**: 🎯 **Architecture Designed**
**Next Phase**: Implement AWS SC execution engine (Week 1-2)
**Timeline**: 6 weeks to complete migration
**Risk**: Low (well-defined AWS SC operations)
