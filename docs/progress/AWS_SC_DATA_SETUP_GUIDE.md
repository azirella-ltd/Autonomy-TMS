# AWS SC Data Setup Guide

This guide shows you how to set up the AWS SC planning data for The Beer Game.

## Quick Start

### Step 1: Convert a Config to AWS SC Format

```bash
# Convert "Default TBG" config to AWS SC entities
docker compose exec backend python scripts/convert_beer_game_to_aws_sc.py

# Or specify a different config
docker compose exec backend python scripts/convert_beer_game_to_aws_sc.py \
  --config-name "Three FG TBG" \
  --group-name "Default Group" \
  --horizon 52
```

**What This Does**:
- Creates `InvPolicy` records for each node (target inventory = 12 units)
- Creates `SourcingRules` for each lane (transfer/manufacture relationships)
- Creates `ProductionProcess` for manufacturer nodes
- Creates `Forecast` records for 52 weeks (based on demand pattern)

**Output Example**:
```
==================================================
Beer Game → AWS SC Conversion
==================================================

1. Loading configuration: Default TBG
   ✓ Config ID: 2
   ✓ Nodes: 4
   ✓ Lanes: 3
   ✓ Items: 1

2. Creating InvPolicy records...
   ✓ Retailer: target=12, safety_stock=0
   ✓ Wholesaler: target=12, safety_stock=0
   ✓ Distributor: target=12, safety_stock=0
   ✓ Factory: target=12, safety_stock=0

   ✅ Created 4 InvPolicy records

3. Creating SourcingRules records...
   ✓ Factory → Distributor: transfer, lead_time=2w
   ✓ Distributor → Wholesaler: transfer, lead_time=2w
   ✓ Wholesaler → Retailer: transfer, lead_time=2w

   ✅ Created 3 SourcingRules records

4. Creating ProductionProcess records...
   ✓ Factory: leadtime=2w, capacity=9999h

   ✅ Created 1 ProductionProcess record

5. Creating Forecast records (52 weeks)...
   Week  0:   4.0 units (date: 2026-01-12)
   Week  1:   4.0 units (date: 2026-01-19)
   Week  2:   4.0 units (date: 2026-01-26)
   Week  3:   4.0 units (date: 2026-02-02)
   Week  4:   4.0 units (date: 2026-02-09)
   ... (45 more weeks)
   Week 50:   8.0 units (date: 2026-12-20)
   Week 51:   8.0 units (date: 2026-12-27)

   ✅ Created 52 Forecast records

==================================================
Conversion Summary
==================================================
Config:              Default TBG (ID: 2)
Group:               Default Group (ID: 2)
InvPolicy:           4 records
SourcingRules:       3 records
ProductionProcess:   1 records
Forecast:            52 records

✅ Conversion complete! Config is ready for AWS SC planning.
==================================================
```

### Step 2: Verify the Conversion

```bash
# Verify that all entities were created correctly
docker compose exec backend python scripts/convert_beer_game_to_aws_sc.py \
  --verify-only \
  --config-name "Default TBG" \
  --group-name "Default Group"
```

**Output Example**:
```
==================================================
Verification
==================================================

Config: Default TBG (ID: 2)
Group:  Default Group (ID: 2)

InvPolicy:           4 records
SourcingRules:       3 records
ProductionProcess:   1 records
Forecast:           52 records

✅ All required AWS SC entities are present
✅ Config is ready for AWS SC planning mode
==================================================
```

### Step 3: Test Dual-Mode Integration

```bash
# Run the dual-mode integration test
docker compose exec backend python scripts/test_dual_mode_integration.py
```

**Expected Output**:
```
╔══════════════════════════════════════════════════════════════════╗
║                    DUAL-MODE INTEGRATION TEST                    ║
╚══════════════════════════════════════════════════════════════════╝

==================================================
TEST 1: Legacy Beer Game Engine Mode
==================================================

Using config: Default TBG (ID: 2)
Using group: Test Group (ID: 3)

✓ Created game: Test Legacy Mode (ID: 123)
  use_aws_sc_planning: False

Running round 1 with legacy engine...
✅ Legacy mode SUCCESS
   Round 1 completed
   Started: 2026-01-12 10:30:00
   Completed: 2026-01-12 10:30:01

==================================================
TEST 2: AWS SC Planning Mode
==================================================

Using config: Default TBG (ID: 2)
Using group: Test Group (ID: 3)

✓ Created game: Test AWS SC Mode (ID: 124)
  use_aws_sc_planning: True

Running round 1 with AWS SC planner...
🚀 AWS SC Planning Mode - Game 124, Round 1
  Step 1: Initializing BeerGameToAWSSCAdapter...
  Step 2: Syncing inventory levels...
  ✓ Synced 4 inventory records
  Step 3: Syncing demand forecast...
  ✓ Synced 52 forecast records
  Step 4: Running AWS SC Planning...
  ✓ Generated 3 supply plans
  Step 5: Converting supply plans to player orders...
  ✓ Converted to 3 player orders
  Step 6: Creating GameRound record...
  Step 7: Applying orders to game state...
  ✓ Applied all orders to game config
✅ AWS SC Planning Round 1 Complete
✅ AWS SC mode SUCCESS
   Round 1 completed
   Started: 2026-01-12 10:30:02
   Completed: 2026-01-12 10:30:05
   Notes: AWS SC Planning Mode - 3 supply plans generated

==================================================
TEST SUMMARY
==================================================
Legacy Mode:   ✅ PASS
AWS SC Mode:   ✅ PASS

🎉 All tests passed! Dual-mode integration is working correctly.
```

## Entity Details

### InvPolicy (Inventory Policy)

Defines target inventory levels for each node.

**Fields**:
- `policy_type`: `abs_level` (absolute level policy)
- `target_qty`: Target inventory level (default: 12 for Beer Game)
- `safety_stock_qty`: Safety stock (default: 0)
- `reorder_point_qty`: Reorder point (default: 0)
- `review_period_days`: 7 (weekly review for Beer Game)

**Example**:
```sql
INSERT INTO inv_policy (group_id, config_id, product_id, site_id, policy_type, target_qty)
VALUES (2, 2, 1, 4, 'abs_level', 12.0);  -- Retailer
```

### SourcingRules (Sourcing Relationships)

Defines how materials flow between nodes.

**Fields**:
- `sourcing_type`:
  - `transfer` - Internal transfer between sites
  - `manufacture` - Manufacturing at factory
  - `purchase` - Purchase from external supplier
- `allocation_percentage`: 100 (single sourcing for Beer Game)
- `lead_time_days`: Lead time in days (weeks * 7 for Beer Game)

**Example**:
```sql
INSERT INTO sourcing_rules (group_id, config_id, product_id, site_id, supplier_site_id, sourcing_type, lead_time_days)
VALUES (2, 2, 1, 3, 2, 'transfer', 14);  -- Wholesaler ← Distributor, 2 weeks
```

### ProductionProcess (Manufacturing)

Defines manufacturing capabilities for factory nodes.

**Fields**:
- `manufacturing_leadtime`: Production lead time in weeks
- `capacity_hours`: Available capacity (9999 = unlimited for Beer Game)
- `yield_pct`: 100 (no loss in production)

**Example**:
```sql
INSERT INTO production_process (group_id, config_id, product_id, site_id, manufacturing_leadtime, capacity_hours)
VALUES (2, 2, 1, 1, 2, 9999);  -- Factory: 2 weeks leadtime, unlimited capacity
```

### Forecast (Demand Forecast)

Defines expected demand for future periods.

**Fields**:
- `forecast_date`: Date of the forecast period
- `forecast_quantity`: Expected demand
- `forecast_p50`: Median forecast (same as forecast_quantity for deterministic)
- `forecast_p10`: Pessimistic (80% of forecast_quantity)
- `forecast_p90`: Optimistic (120% of forecast_quantity)

**Example**:
```sql
INSERT INTO forecast (group_id, config_id, product_id, site_id, forecast_date, forecast_quantity)
VALUES
  (2, 2, 1, 4, '2026-01-12', 4.0),  -- Week 0: 4 units
  (2, 2, 1, 4, '2026-01-19', 4.0),  -- Week 1: 4 units
  (2, 2, 1, 4, '2026-02-02', 8.0);  -- Week 3: 8 units (after step change)
```

## Demand Pattern Mapping

The conversion script handles different Beer Game demand patterns:

### Constant Demand
```json
{
  "type": "constant",
  "value": 4
}
```
→ All weeks get `forecast_quantity = 4.0`

### Step Demand
```json
{
  "type": "step",
  "initial": 4,
  "step_week": 5,
  "step_value": 8
}
```
→ Weeks 0-4 get `forecast_quantity = 4.0`
→ Weeks 5+ get `forecast_quantity = 8.0`

### Weekly Pattern
```json
{
  "weeks": [4, 4, 4, 4, 8, 8, 8, 8, 4, 4]
}
```
→ Each week gets the corresponding value from the array
→ Last value repeats for remaining weeks

## Troubleshooting

### Issue: "Config not found"
```bash
# List available configs
docker compose exec backend python -c "
from app.db.session import SessionLocal
from app.models.supply_chain_config import SupplyChainConfig

with SessionLocal() as db:
    configs = db.query(SupplyChainConfig).all()
    for c in configs:
        print(f'{c.id}: {c.name}')
"
```

### Issue: "Group not found"
```bash
# List available groups
docker compose exec backend python -c "
from app.db.session import SessionLocal
from app.models.group import Group

with SessionLocal() as db:
    groups = db.query(Group).all()
    for g in groups:
        print(f'{g.id}: {g.name}')
"
```

### Issue: "Already converted" (duplicate data)
```bash
# Clear existing AWS SC data for a config
docker compose exec backend python -c "
from app.db.session import SessionLocal
from app.models.aws_sc_planning import InvPolicy, SourcingRules, ProductionProcess, Forecast

config_id = 2
group_id = 2

with SessionLocal() as db:
    db.query(InvPolicy).filter_by(group_id=group_id, config_id=config_id).delete()
    db.query(SourcingRules).filter_by(group_id=group_id, config_id=config_id).delete()
    db.query(ProductionProcess).filter_by(group_id=group_id, config_id=config_id).delete()
    db.query(Forecast).filter_by(group_id=group_id, config_id=config_id).delete()
    db.commit()
    print('Cleared AWS SC data for config_id={}, group_id={}'.format(config_id, group_id))
"

# Then re-run the conversion
docker compose exec backend python scripts/convert_beer_game_to_aws_sc.py
```

## Next Steps

After converting a config:

1. **Create a game with AWS SC mode**:
   ```python
   game = Game(
       name="AWS SC Test Game",
       group_id=2,  # Match the group used in conversion
       supply_chain_config_id=2,  # Match the converted config
       use_aws_sc_planning=True,  # Enable AWS SC mode
       max_rounds=10
   )
   ```

2. **Start the game**:
   ```python
   service = MixedGameService(db)
   game_round = service.start_new_round(game)
   ```

3. **Observe AWS SC planning**:
   - Check the logs for AWS SC planning output
   - Inspect `supply_plan` table for generated plans
   - Compare orders to legacy mode

4. **Run multiple rounds**:
   ```python
   for round_num in range(1, 11):
       game_round = service.start_new_round(game)
       print(f"Round {round_num} complete")
   ```

## Reference

**Conversion Script**: `backend/scripts/convert_beer_game_to_aws_sc.py`
**Test Script**: `backend/scripts/test_dual_mode_integration.py`
**Architecture Doc**: `AWS_SC_PHASE2_ARCHITECTURE.md`
**Progress Doc**: `AWS_SC_PHASE2_PROGRESS.md`

**AWS SC Tables**:
- `inv_policy` - Inventory policies
- `sourcing_rules` - Sourcing relationships
- `production_process` - Manufacturing processes
- `forecast` - Demand forecasts
- `supply_plan` - Generated supply plans (output)
- `inv_level` - Inventory snapshots (runtime)
