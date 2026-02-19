# AWS SC Execution Architecture for The Beer Game

**Date**: 2026-01-12
**Phase**: Phase 2 - Execution Integration
**Status**: ✅ **REFACTORED AND READY FOR TESTING**

---

## Overview

The Beer Game integration with AWS Supply Chain uses **Work Order Management** for execution tracking, not planning. This document describes the execution architecture.

---

## Core Principle: Planning vs Execution

### Planning (Happens BEFORE Game)

**Purpose**: Set up configuration and expectations

**Entities**:
- `forecast` - 52 weeks of expected demand
- `inv_policy` - Target inventory levels per node
- `sourcing_rules` - Lead times and sourcing relationships
- `production_process` - Manufacturing capacity and lead times

**Created By**: `convert_beer_game_to_aws_sc.py` during game setup

**Example**:
```
Before game starts:
- Forecast: Weeks 1-4 = 4 units, Weeks 5+ = 8 units
- InvPolicy: Retailer target = 12 units
- SourcingRules: Wholesaler → Retailer, 2-week lead time
```

### Execution (Happens DURING Game)

**Purpose**: Track actual orders, fulfillment, and inventory

**Entities**:
- `inbound_order_line` - Work orders (TO/MO/PO)
- `outbound_order_line` - Customer demand records
- `inv_level` - Inventory snapshots per round

**Created By**: `BeerGameExecutionAdapter` during each game round

**Example**:
```
Round 5:
- Customer demands 8 units from Retailer (outbound_order_line)
- Retailer orders 8 units from Wholesaler (inbound_order_line, TO)
- Retailer inventory snapshot: 10 units (inv_level)
- Order arrives in 2 weeks (round 7)
```

---

## Work Order Types

The Beer Game uses three types of work orders:

### TO (Transfer Order)
**Definition**: Internal transfer between sites
**Beer Game Use**: Most orders (Retailer ← Wholesaler ← Distributor ← Factory)

**Example**:
```sql
INSERT INTO inbound_order_line (
    order_type, quantity_submitted, to_site_id, from_site_id,
    expected_delivery_date, status
) VALUES (
    'TO', 8, retailer_id, wholesaler_id,
    current_date + INTERVAL 2 WEEK, 'open'
);
```

### MO (Manufacturing Order)
**Definition**: Production at factory
**Beer Game Use**: Factory produces beer

**Example**:
```sql
INSERT INTO inbound_order_line (
    order_type, quantity_submitted, to_site_id, from_site_id,
    expected_delivery_date, status
) VALUES (
    'MO', 8, factory_id, factory_id,
    current_date + INTERVAL 2 WEEK, 'open'
);
```

### PO (Purchase Order)
**Definition**: Purchase from external supplier
**Beer Game Use**: Only if market_supply node exists

**Example**:
```sql
INSERT INTO inbound_order_line (
    order_type, quantity_submitted, to_site_id, tpartner_id,
    expected_delivery_date, status
) VALUES (
    'PO', 8, factory_id, external_supplier_id,
    current_date + INTERVAL 3 WEEK, 'open'
);
```

---

## Execution Workflow (Per Round)

### Step 1: Sync Inventory Snapshot

**Action**: Read player inventory from game state → `inv_level`

**Purpose**: AWS SC can see current on-hand quantities

**Code**:
```python
adapter.sync_inventory_levels(round_number)
```

**Result**:
```sql
inv_level table:
+--------+---------+----------+-------------+
| site   | product | on_hand  | in_transit  |
+--------+---------+----------+-------------+
| Retailer | Cases | 10       | 8           |
| Wholesaler | Cases | 12     | 8           |
| ...
```

### Step 2: Record Customer Demand

**Action**: Create `outbound_order_line` for customer demand

**Purpose**: Track actual demand hitting the retailer

**Code**:
```python
adapter.record_customer_demand('Retailer', demand_qty, round_number)
```

**Result**:
```sql
outbound_order_line table:
+-----------+-----------+---------------------------+-------------------+
| order_id  | site      | final_quantity_requested  | quantity_delivered|
+-----------+-----------+---------------------------+-------------------+
| GAME_1_R5 | Retailer  | 8                         | 8                 |
```

### Step 3: Process Deliveries

**Action**: Find work orders arriving this round, mark as received

**Purpose**: Shipments arrive after lead time

**Code**:
```python
deliveries = adapter.process_deliveries(round_number)
```

**Result**:
```sql
inbound_order_line table:
+-----------+-----------+-------------------+-------------------+----------+
| order_id  | to_site   | quantity_submitted| quantity_received | status   |
+-----------+-----------+-------------------+-------------------+----------+
| GAME_1_R3_Retailer | Retailer | 8          | 8                 | received |
```

### Step 4: Get Player Order Decisions

**Action**: Players (agents/humans) decide how much to order

**Purpose**: Get order quantities for this round

**Code**:
```python
player_orders = await _get_player_orders_for_round(game, round_number, db)
```

**Result**:
```python
{
    'Retailer': 8,
    'Wholesaler': 8,
    'Distributor': 8,
    'Factory': 8
}
```

### Step 5: Create Work Orders

**Action**: Convert player orders → `inbound_order_line`

**Purpose**: Create TO/MO work orders for execution

**Code**:
```python
adapter.create_work_orders(player_orders, round_number)
```

**Result**:
```sql
inbound_order_line table (new orders):
+-----------------+-----------+-----------+-------------------+------------------------+--------+
| order_id        | to_site   | from_site | quantity_submitted| expected_delivery_date | status |
+-----------------+-----------+-----------+-------------------+------------------------+--------+
| GAME_1_R5_Retailer    | Retailer  | Wholesaler| 8           | 2026-02-02             | open   |
| GAME_1_R5_Wholesaler  | Wholesaler| Distributor| 8         | 2026-02-02             | open   |
| GAME_1_R5_Distributor | Distributor| Factory  | 8          | 2026-02-02             | open   |
| GAME_1_R5_Factory     | Factory   | Factory   | 8          | 2026-02-02             | open   |
```

### Step 6: Update Game State

**Action**: Apply orders to `game.config` JSON

**Purpose**: Keep game state in sync with work orders

**Code**:
```python
await _apply_aws_sc_orders_to_game(game, player_orders, round_number, db)
```

### Step 7: Complete Round

**Action**: Mark `GameRound` as completed

**Purpose**: Finalize round execution

---

## Work Order Lifecycle

### State Transitions

```
Order Placed
    │ quantity_submitted = 8
    │ status = 'open'
    │ expected_delivery_date = order_date + lead_time
    ▼
Order in Transit (2 weeks)
    │ status = 'open'
    │ quantity_received = NULL
    ▼
Order Arrives
    │ quantity_received = 8
    │ order_receive_date = expected_delivery_date
    │ status = 'received'
    ▼
Shipment Delivered
```

### Key Fields Tracking

| Field | When Set | Meaning |
|-------|----------|---------|
| `quantity_submitted` | Order placed | What player ordered |
| `quantity_confirmed` | Order confirmed | What upstream confirmed (auto in Beer Game) |
| `quantity_received` | Order arrives | What actually arrived |
| `submitted_date` | Order placed | When order was placed |
| `expected_delivery_date` | Order placed | When order should arrive (order_date + lead_time) |
| `order_receive_date` | Order arrives | When order actually arrived |
| `status` | Changes over time | 'open' → 'received' |

---

## Database Schema

### Core Execution Tables

#### inbound_order_line (Work Orders)
```sql
CREATE TABLE inbound_order_line (
    id INT PRIMARY KEY AUTO_INCREMENT,
    order_id VARCHAR(100) NOT NULL,
    order_type VARCHAR(20) NOT NULL,  -- 'TO', 'MO', 'PO'

    -- Sites and products
    product_id INT NOT NULL,
    to_site_id INT NOT NULL,           -- Destination
    from_site_id INT,                  -- Source (for TO/MO)
    tpartner_id INT,                   -- Vendor (for PO)

    -- Quantities (execution tracking)
    quantity_submitted DOUBLE NOT NULL,
    quantity_confirmed DOUBLE,
    quantity_received DOUBLE,

    -- Dates (execution timeline)
    submitted_date DATE,
    expected_delivery_date DATE,
    order_receive_date DATE,

    -- Status
    status VARCHAR(50),                -- 'open', 'received'
    lead_time_days INT,

    -- Multi-tenancy
    group_id INT,
    config_id INT,
    game_id INT,
    round_number INT,

    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Indexes
    INDEX idx_inbound_order_lookup (product_id, to_site_id, expected_delivery_date),
    INDEX idx_inbound_order_game_round (game_id, round_number),
    INDEX idx_inbound_order_status (status)
);
```

#### outbound_order_line (Customer Demand)
```sql
CREATE TABLE outbound_order_line (
    id INT PRIMARY KEY AUTO_INCREMENT,
    order_id VARCHAR(100) NOT NULL,
    product_id INT NOT NULL,
    site_id INT NOT NULL,

    -- Quantities (execution tracking)
    init_quantity_requested DOUBLE,
    final_quantity_requested DOUBLE NOT NULL,
    quantity_promised DOUBLE,
    quantity_delivered DOUBLE,

    -- Dates
    order_date DATE,
    requested_delivery_date DATE NOT NULL,
    actual_delivery_date DATE,

    -- Status
    status VARCHAR(50),

    -- Multi-tenancy
    group_id INT,
    config_id INT,
    game_id INT,
    round_number INT,

    -- Indexes
    INDEX idx_outbound_order_game_round (game_id, round_number)
);
```

#### inv_level (Inventory Snapshots)
```sql
CREATE TABLE inv_level (
    id INT PRIMARY KEY AUTO_INCREMENT,
    product_id INT NOT NULL,
    site_id INT NOT NULL,

    -- Quantities
    on_hand_qty DECIMAL(10,2) DEFAULT 0,
    available_qty DECIMAL(10,2) DEFAULT 0,
    in_transit_qty DECIMAL(10,2) DEFAULT 0,
    backorder_qty DECIMAL(10,2) DEFAULT 0,

    -- Multi-tenancy
    group_id INT,
    config_id INT,

    -- Snapshot time
    snapshot_date DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## Code Architecture

### Service Layer

**File**: `backend/app/services/mixed_game_service.py`

**Key Methods**:
- `start_new_round()` - Dual-mode routing
- `_start_round_legacy()` - Legacy Beer Game engine
- `_start_round_aws_sc()` - AWS SC execution mode
- `_run_aws_sc_planning_async()` - Execution workflow orchestrator
- `_get_current_demand()` - Get demand for this round
- `_get_player_orders_for_round()` - Get player order decisions

### Adapter Layer

**File**: `backend/app/services/aws_sc_planning/beer_game_execution_adapter.py`

**Class**: `BeerGameExecutionAdapter`

**Key Methods**:
```python
class BeerGameExecutionAdapter:
    async def sync_inventory_levels(round_number: int) -> int
        """Snapshot inventory → inv_level"""

    async def record_customer_demand(role: str, demand_qty: float, round_number: int) -> None
        """Customer demand → outbound_order_line"""

    async def create_work_orders(player_orders: Dict[str, float], round_number: int) -> int
        """Player orders → inbound_order_line (TO/MO/PO)"""

    async def process_deliveries(round_number: int) -> Dict[str, float]
        """Mark orders as received when they arrive"""

    async def get_current_inventory(role: str) -> float
        """Get player's current inventory"""
```

### Data Models

**File**: `backend/app/models/aws_sc_planning.py`

**Classes**:
- `InboundOrderLine` - Work order entity
- `OutboundOrderLine` - Customer demand entity
- `InvLevel` - Inventory snapshot entity
- `Forecast` - Demand forecast (planning)
- `InvPolicy` - Inventory policy (planning)
- `SourcingRules` - Sourcing rules (planning)

---

## Dual-Mode Operation

### Legacy Mode (Default)

**Flag**: `game.use_aws_sc_planning = False`

**Behavior**: Original `engine.py` simulation (unchanged)

**Performance**: Fast (50-100ms per round)

**Use Case**: Standard Beer Game, existing functionality

### AWS SC Execution Mode (Opt-In)

**Flag**: `game.use_aws_sc_planning = True`

**Behavior**: Work order execution via AWS SC

**Performance**: Slower (500-2000ms per round, database-intensive)

**Use Case**: AWS SC integration, order tracking, inventory management

---

## Testing Workflow

### 1. Run Migrations

```bash
docker compose exec backend alembic upgrade head
```

This creates the `inbound_order_line` table and updates `outbound_order_line`.

### 2. Convert Config to AWS SC Format

```bash
docker compose exec backend python scripts/convert_beer_game_to_aws_sc.py \
  --config-name "Default TBG" \
  --group-name "Default Group"
```

This creates planning entities (forecast, inv_policy, sourcing_rules).

### 3. Test Dual-Mode Integration

```bash
docker compose exec backend python scripts/test_dual_mode_integration.py
```

This tests both legacy and AWS SC execution modes.

### 4. Observe Work Orders

```sql
-- View all work orders for a game
SELECT order_id, order_type, to_site_id, quantity_submitted,
       expected_delivery_date, status
FROM inbound_order_line
WHERE game_id = 1
ORDER BY round_number, order_id;

-- View customer demand
SELECT order_id, site_id, final_quantity_requested, quantity_delivered
FROM outbound_order_line
WHERE game_id = 1
ORDER BY round_number;

-- View inventory snapshots
SELECT site_id, on_hand_qty, in_transit_qty, backorder_qty, snapshot_date
FROM inv_level
WHERE game_id = 1;
```

---

## Troubleshooting

### Issue: Work orders not created

**Check**: Are player orders being generated?
```python
player_orders = await _get_player_orders_for_round(game, round_number, db)
print(player_orders)  # Should have entries like {'Retailer': 8}
```

### Issue: Deliveries not processed

**Check**: Are orders marked as 'received'?
```sql
SELECT * FROM inbound_order_line
WHERE game_id = ? AND status = 'received';
```

### Issue: Inventory not updating

**Check**: Is `sync_inventory_levels()` being called?
```sql
SELECT * FROM inv_level
WHERE group_id = ? AND config_id = ?;
```

---

## Next Steps

1. ✅ Run migrations (`alembic upgrade head`)
2. ⏳ Test dual-mode integration
3. ⏳ Validate work order creation and delivery
4. ⏳ Compare legacy vs execution mode results
5. ⏳ Performance testing
6. ⏳ Update all documentation

---

## References

### AWS Supply Chain Documentation

- [Work Order Overview](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/work-order.html)
- [Inbound Order Line Entity](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/replenishment-inbound-order-line-entity.html)
- [Outbound Order Line Entity](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/outbound-fulfillment-order-line-entity.html)
- [Transactional Data](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/transactional.html)

### Internal Documentation

- `AWS_SC_EXECUTION_REFACTOR.md` - Detailed refactoring notes
- `AWS_SC_DATA_SETUP_GUIDE.md` - Data setup instructions
- `CLAUDE.md` - Project overview

---

**Architecture Status**: ✅ **EXECUTION-READY**
**Next Phase**: Testing and validation
