# AWS Supply Chain Phase 2: Service Layer Integration

**Date**: 2026-01-12
**Status**: 🚧 In Progress
**Phase**: 2 of 4

## Executive Summary

Phase 2 integrates AWS SC planning logic into The Beer Game by creating a dual-mode architecture that supports both legacy `engine.py` and new AWS SC planning modes. This enables gradual migration, A/B testing, and validation of AWS SC planning against existing gameplay.

## Vision Recap

From Phase 1, we established the goal: **Make The Beer Game a special case of AWS Supply Chain Data Model**.

Phase 2 achieves this by:
1. Adding AWS SC planning as an **optional mode** for games
2. Creating an **adapter layer** to translate between Beer Game and AWS SC concepts
3. Enabling **side-by-side comparison** of planning algorithms
4. Providing a **migration path** for existing configs

## Architecture Overview

### Current State (Legacy Mode)

```
┌──────────────────┐
│ mixed_game_      │
│ service.py       │
│                  │
│  start_new_round │
│        │         │
│        ▼         │
│  _initialize_    │
│  round()         │
│        │         │
│        ▼         │
│  _process_node_  │
│  echelon()       │
│        │         │
│        ▼         │
│  _finalize_round │
└──────────────────┘
     Uses engine.py
     embedded logic
```

### Target State (Dual Mode)

```
┌─────────────────────────────────────────────────────────┐
│ mixed_game_service.py                                   │
│                                                          │
│  start_new_round(game)                                  │
│         │                                                │
│         ▼                                                │
│  if game.use_aws_sc_planning:  ◄──── NEW FEATURE FLAG  │
│         │                                                │
│    ┌────┴────┐                                          │
│    │         │                                           │
│    ▼         ▼                                           │
│  TRUE      FALSE                                         │
│    │         │                                           │
│    ▼         ▼                                           │
│ ┌──────┐  ┌──────┐                                      │
│ │ AWS  │  │Legacy│                                      │
│ │  SC  │  │Engine│                                      │
│ │ Mode │  │ Mode │                                      │
│ └──┬───┘  └───┬──┘                                      │
│    │          │                                          │
└────┼──────────┼──────────────────────────────────────────┘
     │          │
     ▼          ▼
┌─────────┐  ┌──────────┐
│ AWS SC  │  │ engine.py│
│ Planner │  │ (legacy) │
└─────────┘  └──────────┘
```

## Implementation Strategy

### 1. Feature Flag (✅ COMPLETE)

**Migration**: `20260112_add_aws_sc_planning_flag.py`
**Model Update**: `backend/app/models/game.py`

Added `use_aws_sc_planning` boolean flag to Game model:
```python
class Game(Base):
    # ... existing fields ...
    use_aws_sc_planning: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
```

**Usage**:
- `False` (default): Use legacy `engine.py` logic
- `True`: Use AWS SC 3-step planning process

### 2. AWS SC Planner Updates (PENDING)

#### 2.1 Add group_id Support

**File**: `backend/app/services/aws_sc_planning/planner.py`

**Current**:
```python
class AWSSupplyChainPlanner:
    def __init__(self, config_id: int, planning_horizon: int = 52):
        self.config_id = config_id
        # ...
```

**Target**:
```python
class AWSSupplyChainPlanner:
    def __init__(
        self,
        config_id: int,
        group_id: int,  # NEW: Multi-tenancy support
        planning_horizon: int = 52
    ):
        self.config_id = config_id
        self.group_id = group_id  # NEW
        # ...
```

#### 2.2 Update Sub-Processors

All sub-processors need `group_id` parameter:
- `DemandProcessor(config_id, group_id)`
- `InventoryTargetCalculator(config_id, group_id)`
- `NetRequirementsCalculator(config_id, group_id, planning_horizon)`

#### 2.3 Update All Queries

Every query to AWS SC planning tables must filter by `(group_id, config_id)`:

**Before**:
```python
result = await db.execute(
    select(InvPolicy).filter(
        InvPolicy.config_id == self.config_id
    )
)
```

**After**:
```python
result = await db.execute(
    select(InvPolicy).filter(
        InvPolicy.group_id == self.group_id,
        InvPolicy.config_id == self.config_id
    )
)
```

### 3. AWS SC Adapter Layer (PENDING)

#### Purpose
Translate between Beer Game concepts and AWS SC concepts:

| Beer Game | AWS SC |
|-----------|--------|
| Node | Site |
| Item | Product |
| Lane | Sourcing Rule / Transportation Lane |
| Player Inventory | InvLevel (on_hand_qty) |
| Player Order | Supply Plan (PO/TO request) |
| Round | Planning Period |

#### Architecture

**File**: `backend/app/services/aws_sc_planning/beer_game_adapter.py`

```python
class BeerGameToAWSSCAdapter:
    """
    Adapter to translate Beer Game state to AWS SC planning inputs
    """

    def __init__(self, game: Game, db: Session):
        self.game = game
        self.db = db
        self.config = game.supply_chain_config
        self.group_id = game.group_id

    async def sync_inventory_levels(self, round_number: int) -> None:
        """
        Sync current game state to inv_level table

        Reads player inventory from game config/state and writes to inv_level
        so AWS SC planner can see current on-hand quantities.
        """
        pass

    async def sync_demand_forecast(self, round_number: int, horizon: int) -> None:
        """
        Sync market demand to forecast table

        Creates forecast records for future rounds based on demand_pattern
        """
        pass

    async def convert_supply_plans_to_orders(
        self,
        supply_plans: List[SupplyPlan]
    ) -> Dict[str, float]:
        """
        Convert AWS SC supply plans to Beer Game player orders

        Maps:
        - po_request (Purchase Order) → Player order to upstream node
        - to_request (Transfer Order) → Player order to upstream DC
        - mo_request (Manufacturing Order) → Production order

        Returns:
            Dict mapping role to order quantity for this round
        """
        pass

    async def get_current_inventory(self, role: str) -> float:
        """Get current inventory for a player/node"""
        pass
```

### 4. Service Integration (PENDING)

#### 4.1 Modify `start_new_round()`

**File**: `backend/app/services/mixed_game_service.py`

**Pseudo-code**:
```python
def start_new_round(self, game: Union[int, Game]) -> Optional[GameRound]:
    # Existing preamble...
    game_obj = self._resolve_game(game)

    # NEW: Route to appropriate planning mode
    if game_obj.use_aws_sc_planning:
        return await self._start_round_aws_sc(game_obj)
    else:
        return self._start_round_legacy(game_obj)  # Existing logic

async def _start_round_aws_sc(self, game: Game) -> Optional[GameRound]:
    """
    Execute round using AWS SC 3-step planning

    Flow:
    1. Sync current game state to AWS SC tables (inv_level, forecast)
    2. Run AWS SC planner
    3. Convert supply plans to player orders
    4. Update game state
    5. Record round history
    """
    # 1. Setup
    adapter = BeerGameToAWSSCAdapter(game, self.db)
    await adapter.sync_inventory_levels(game.current_round)
    await adapter.sync_demand_forecast(game.current_round, horizon=52)

    # 2. Run AWS SC Planning
    planner = AWSSupplyChainPlanner(
        config_id=game.supply_chain_config_id,
        group_id=game.group_id,
        planning_horizon=52
    )

    start_date = game.start_date + timedelta(days=game.current_round * 7)  # Weekly
    supply_plans = await planner.run_planning(
        start_date=start_date,
        game_id=game.id
    )

    # 3. Convert to game orders
    player_orders = await adapter.convert_supply_plans_to_orders(supply_plans)

    # 4. Update game state with recommended orders
    for role, order_qty in player_orders.items():
        self._record_player_order(game, role, order_qty)

    # 5. Process round (shipments, demand, costs)
    self._process_shipments(game)
    self._process_demand(game)
    self._calculate_costs(game)

    # 6. Finalize
    game.current_round += 1
    self.db.commit()

    return game_round

def _start_round_legacy(self, game: Game) -> Optional[GameRound]:
    """Legacy mode - existing implementation (unchanged)"""
    # Move existing start_new_round logic here
    pass
```

### 5. Config Conversion Script (PENDING)

#### Purpose
Convert existing Beer Game configurations to AWS SC format.

**File**: `backend/scripts/convert_beer_game_to_aws_sc.py`

**Functionality**:
1. Read Beer Game `SupplyChainConfig` (nodes, lanes, items)
2. Create AWS SC entities:
   - `InvPolicy` for each node (product, site)
   - `SourcingRules` for each lane
   - `ProductionProcess` for manufacturers
   - `Forecast` records for market demand
3. Link with `(group_id, config_id)`

**Example Conversion**:

**Beer Game Config** (Default TBG):
```
Nodes:
- Factory (manufacturer)
- Distributor (inventory)
- Wholesaler (inventory)
- Retailer (inventory)

Lanes:
- Market → Retailer
- Retailer → Wholesaler
- Wholesaler → Distributor
- Distributor → Factory
```

**AWS SC Entities Created**:
```sql
-- Inventory Policies (4 records)
INSERT INTO inv_policy (group_id, config_id, product_id, site_id, ss_policy, target_qty, ...)
VALUES
    (2, 2, 1, 4, 'abs_level', 12.0, ...),  -- Retailer
    (2, 2, 1, 3, 'abs_level', 12.0, ...),  -- Wholesaler
    (2, 2, 1, 2, 'abs_level', 12.0, ...),  -- Distributor
    (2, 2, 1, 1, 'abs_level', 12.0, ...);  -- Factory

-- Sourcing Rules (4 records)
INSERT INTO sourcing_rules (group_id, config_id, product_id, site_id, supplier_site_id, ...)
VALUES
    (2, 2, 1, 4, 3, ...),  -- Retailer sources from Wholesaler
    (2, 2, 1, 3, 2, ...),  -- Wholesaler sources from Distributor
    (2, 2, 1, 2, 1, ...),  -- Distributor sources from Factory
    (2, 2, 1, 1, NULL, ...);  -- Factory manufactures

-- Forecasts (52 weeks × 1 product × 1 site = 52 records)
INSERT INTO forecast (group_id, config_id, product_id, site_id, forecast_date, forecast_quantity, ...)
VALUES
    (2, 2, 1, 4, '2024-01-01', 4.0, ...),
    (2, 2, 1, 4, '2024-01-08', 4.0, ...),
    -- ... 50 more weeks
```

## Data Flow Diagram

### Legacy Mode (Current)
```
Game State
(config JSON)
     │
     ▼
engine.py
embedded logic
     │
     ▼
Updated Game State
(config JSON)
     │
     ▼
GameRound record
```

### AWS SC Mode (New)
```
Game State          AWS SC Tables
(config JSON)       (inv_level,
     │              forecast, etc.)
     │                    ▲
     ▼                    │
Adapter.sync_*()  ────────┘
                         │
                         ▼
                  AWSSupplyChainPlanner
                         │
                         ├──► DemandProcessor
                         ├──► InventoryTargetCalculator
                         └──► NetRequirementsCalculator
                                │
                                ▼
                          SupplyPlan records
                                │
                                ▼
                  Adapter.convert_to_orders()
                                │
                                ▼
                       Updated Game State
                         (player orders)
                                │
                                ▼
                          GameRound record
```

## Testing Strategy

### Phase 2A: Unit Testing
1. Test `AWSSupplyChainPlanner` with `group_id` filtering
2. Test `BeerGameToAWSSCAdapter` methods in isolation
3. Test config conversion script

### Phase 2B: Integration Testing
1. Create test game with `use_aws_sc_planning=False` → verify legacy still works
2. Create test game with `use_aws_sc_planning=True` → verify AWS SC works
3. Run both modes side-by-side and compare results

### Phase 2C: Validation Testing
1. Convert Default TBG config to AWS SC format
2. Play 10 rounds in legacy mode
3. Play 10 rounds in AWS SC mode (same config)
4. Compare: inventory levels, orders, costs, service levels

**Success Criteria**:
- AWS SC mode produces similar (not identical) results to legacy
- No crashes or errors in AWS SC mode
- Performance acceptable (<2s per round)

## Rollback Plan

If AWS SC mode has issues:

**Option 1: Disable at Game Level**
```sql
UPDATE games SET use_aws_sc_planning = false WHERE use_aws_sc_planning = true;
```

**Option 2: Disable at Code Level**
```python
# In mixed_game_service.py
def start_new_round(self, game):
    # Force legacy mode
    return self._start_round_legacy(game)
```

**Option 3: Rollback Migration**
```bash
docker compose exec backend alembic downgrade 20260111_aws_sc_multi_tenancy
```

## Performance Considerations

### Legacy Mode
- **Round Time**: ~50-100ms (in-memory simulation)
- **Database Queries**: ~5-10 per round (read/write game state)

### AWS SC Mode (Estimated)
- **Round Time**: ~500-1000ms (database-intensive)
- **Database Queries**: ~50-100 per round (read policies, write plans, etc.)

**Optimization Strategies**:
1. **Caching**: Cache `InvPolicy`, `SourcingRules` for duration of game
2. **Batch Operations**: Use bulk insert for `SupplyPlan` records
3. **Async Queries**: Parallelize demand processing, target calculation
4. **Lazy Sync**: Only sync changed inventory (not all nodes every round)

## Dependencies & Risks

### Dependencies
- ✅ Phase 1 complete (multi-tenancy schema)
- ✅ AWS SC planning modules exist (`planner.py`, etc.)
- ⚠️ Need to understand Beer Game state management deeply
- ⚠️ Need mapping logic between concepts

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| AWS SC planning produces incorrect orders | High | Extensive testing, validation against legacy |
| Performance too slow for gameplay | Medium | Caching, async queries, optimization |
| Complex state synchronization bugs | High | Unit tests for adapter, integration tests |
| Existing games break | High | Feature flag default=False, gradual rollout |

## Timeline & Milestones

**Week 3**:
- ✅ Add feature flag to Game model (DONE)
- ⏳ Update `AWSSupplyChainPlanner` with `group_id`
- ⏳ Implement `BeerGameToAWSSCAdapter`
- ⏳ Create conversion script

**Week 4**:
- ⏳ Integrate into `mixed_game_service.py`
- ⏳ Unit & integration testing
- ⏳ Convert Default TBG to AWS SC format
- ⏳ Validation testing (side-by-side comparison)

## Success Metrics

Phase 2 is successful when:
1. ✅ Games can be flagged to use AWS SC planning
2. ✅ AWS SC mode completes 10+ rounds without errors
3. ✅ Results are "reasonable" compared to legacy (within 20% on key metrics)
4. ✅ Performance acceptable for gameplay (<2s per round)
5. ✅ At least one Beer Game config fully converted to AWS SC format

## Next: Phase 3 - UI Extension

Once Phase 2 is stable:
- Build API endpoints for AWS SC entities
- Create React UI for InvPolicy, VendorProduct, SourcingSchedule
- Extend supply chain config UI with AWS SC tabs

## Files To Create/Modify

### New Files:
1. `backend/migrations/versions/20260112_add_aws_sc_planning_flag.py` ✅
2. `backend/app/services/aws_sc_planning/beer_game_adapter.py` ⏳
3. `backend/scripts/convert_beer_game_to_aws_sc.py` ⏳
4. `backend/tests/test_aws_sc_integration.py` ⏳

### Modified Files:
1. `backend/app/models/game.py` ✅ (added `use_aws_sc_planning`)
2. `backend/app/services/aws_sc_planning/planner.py` ⏳ (add `group_id`)
3. `backend/app/services/aws_sc_planning/demand_processor.py` ⏳
4. `backend/app/services/aws_sc_planning/inventory_target_calculator.py` ⏳
5. `backend/app/services/aws_sc_planning/net_requirements_calculator.py` ⏳
6. `backend/app/services/mixed_game_service.py` ⏳ (dual-mode routing)

## Documentation

- [ ] Update CLAUDE.md with Phase 2 architecture
- [ ] Create AWS_SC_PHASE2_COMPLETE.md when done
- [ ] Document conversion process for admins
- [ ] Add API docs for `use_aws_sc_planning` flag

---

**Status**: Phase 2 Started - 2026-01-12
**Next Task**: Update AWSSupplyChainPlanner with group_id support
