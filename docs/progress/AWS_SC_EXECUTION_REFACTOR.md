# AWS SC Execution Refactor: Planning → Execution

**Date**: 2026-01-12
**Phase**: Phase 2 Refactoring
**Status**: ✅ **REFACTORING COMPLETE**

---

## Executive Summary

This document describes the **critical architectural refactoring** from AWS SC Planning to AWS SC Execution approach for The Beer Game integration.

### The Problem

The initial Phase 2 implementation (85% complete) incorrectly treated The Beer Game as a **planning scenario** when it is actually an **execution scenario**.

**Planning**: Forecast future demand → Calculate inventory targets → Generate supply plan recommendations (what SHOULD happen in future periods)

**Execution**: Record actual demand → Fulfill orders → Update inventory (what IS happening right now)

### The Solution

Refactored to use AWS SC's **Work Order Management** (Order Planning and Tracking) instead of Supply Planning.

**Key Change**: Player orders are now **InboundOrderLine work orders** (TO/MO/PO), not supply plan recommendations.

---

## Architecture Comparison

### Before (❌ Incorrect - Planning Approach)

```
Beer Game Round
    │
    └─> AWS SC Planning
        ├─> 1. Sync inventory → inv_level
        ├─> 2. Sync demand forecast → forecast (52 weeks ahead)
        ├─> 3. Run planning engine
        │   ├─> Demand Processing (consume forecasts)
        │   ├─> Inventory Target Calculation
        │   └─> Net Requirements Calculation
        ├─> 4. Generate supply plans (po_request, to_request, mo_request)
        ├─> 5. Convert supply plans to player orders
        └─> 6. Execute game round
```

**Problems**:
1. Planning generates recommendations for FUTURE periods (52-week horizon)
2. Beer Game needs IMMEDIATE order execution (this round, not future)
3. Supply plans are suggestions, not work orders
4. Confuses "what should we do in 12 weeks" with "what are we doing right now"

### After (✅ Correct - Execution Approach)

```
Beer Game Round
    │
    ├─> Pre-Game Planning (happens ONCE before game starts)
    │   ├─> Forecast (52 weeks of demand pattern) → forecast table
    │   ├─> Inventory Policies (target levels) → inv_policy table
    │   └─> Sourcing Rules (lead times, relationships) → sourcing_rules table
    │
    └─> Per-Round Execution (happens EVERY round)
        ├─> 1. Sync inventory snapshot → inv_level
        ├─> 2. Record customer demand → outbound_order_line (actual demand)
        ├─> 3. Process deliveries → update inbound_order_line (quantity_received)
        ├─> 4. Get player order decisions (from agents/humans)
        ├─> 5. Create work orders → inbound_order_line (TO/MO/PO)
        │   ├─> Retailer orders from Wholesaler → TO (Transfer Order)
        │   ├─> Wholesaler orders from Distributor → TO
        │   ├─> Distributor orders from Factory → TO
        │   └─> Factory produces → MO (Manufacturing Order)
        ├─> 6. Update game state
        └─> 7. Complete round
```

**Benefits**:
1. Work orders execute IMMEDIATELY (this round)
2. Clear separation: planning before game, execution during game
3. InboundOrderLine tracks full lifecycle: submitted → confirmed → received
4. Aligns with AWS SC's Order Planning and Tracking module

---

## Key Entities

### Planning Entities (Setup Before Game)

| Entity | Purpose | When Created | Example |
|--------|---------|--------------|---------|
| **Forecast** | Expected demand pattern | Pre-game | 52 weeks: [4, 4, 4, 4, 8, 8, ...] |
| **InvPolicy** | Target inventory levels | Pre-game | Retailer target = 12 units |
| **SourcingRules** | Lead times, relationships | Pre-game | Distributor → Wholesaler, 2 weeks |
| **ProductionProcess** | Manufacturing capacity | Pre-game | Factory leadtime = 2 weeks |

### Execution Entities (Runtime During Game)

| Entity | Purpose | When Created | Example |
|--------|---------|--------------|---------|
| **InboundOrderLine** | Work orders (TO/MO/PO) | Every round when player orders | Retailer orders 8 units from Wholesaler |
| **OutboundOrderLine** | Customer demand | Every round | Customer demands 8 units from Retailer |
| **InvLevel** | Inventory snapshot | Every round | Retailer has 10 units on-hand |

---

## InboundOrderLine: The Primary Execution Entity

**AWS SC Definition**: "Tracks orders FROM suppliers/upstream sites TO destination sites for execution"

### Work Order Types

| Type | Meaning | Beer Game Example |
|------|---------|-------------------|
| **TO** | Transfer Order (internal) | Retailer orders from Wholesaler |
| **MO** | Manufacturing Order (production) | Factory produces beer |
| **PO** | Purchase Order (external) | Factory orders from external supplier |

### Execution Lifecycle

```
Player Decision
    │
    ├─> quantity_submitted (order placed)
    │   status: 'open'
    │   expected_delivery_date: order_date + lead_time
    │
    ├─> quantity_confirmed (auto-confirmed in Beer Game)
    │   confirmation_date: order_date
    │   vendor_status: 'confirmed'
    │
    └─> quantity_received (shipment arrives)
        order_receive_date: expected_delivery_date
        status: 'received'
```

### Key Fields

```python
class InboundOrderLine:
    # Quantities (execution tracking)
    quantity_submitted    # What player ordered (PRIMARY)
    quantity_confirmed    # What upstream confirmed
    quantity_received     # What actually arrived

    # Dates (execution timeline)
    submitted_date        # When order placed
    expected_delivery_date # When order should arrive (based on lead time)
    order_receive_date    # When order actually arrived

    # Status
    status                # 'open' → 'received'

    # Sites
    to_site_id            # Destination (player's node)
    from_site_id          # Source (upstream node)
```

---

## Code Changes

### 1. New Execution Adapter ✅

**File**: `backend/app/services/aws_sc_planning/beer_game_execution_adapter.py` (NEW)

**Key Methods**:

```python
class BeerGameExecutionAdapter:
    async def sync_inventory_levels(round_number)
        # Snapshot current inventory → inv_level

    async def record_customer_demand(role, demand_qty, round_number)
        # Customer demand → outbound_order_line

    async def create_work_orders(player_orders, round_number)
        # Player orders → inbound_order_line (TO/MO/PO)

    async def process_deliveries(round_number)
        # Update quantity_received for orders arriving this round
```

### 2. Refactored Service Integration ✅

**File**: `backend/app/services/mixed_game_service.py` (Lines 7076-7240)

**Changed Methods**:
- `_run_aws_sc_planning_async()` → Now uses execution workflow
- `_get_current_demand()` → NEW: Get demand for this round
- `_get_player_orders_for_round()` → NEW: Get player decisions

**Execution Flow**:
1. Sync inventory levels (execution snapshot)
2. Record customer demand (outbound_order_line)
3. Process deliveries (inbound_order_line status updates)
4. Get player order decisions
5. Create work orders (inbound_order_line)
6. Update game state
7. Complete round

### 3. New Data Model ✅

**File**: `backend/app/models/aws_sc_planning.py` (Lines 314-392)

**Added Classes**:
- `InboundOrderLine` (NEW) - Work order execution entity
- `OutboundOrderLine` (ENHANCED) - Added execution fields:
  - `init_quantity_requested`, `quantity_promised`, `quantity_delivered`
  - `promised_delivery_date`, `actual_delivery_date`
  - `status`, `ship_from_site_id`, `ship_to_site_id`, `round_number`

### 4. Database Migration ✅

**File**: `backend/migrations/versions/20260112_inbound_order_line.py` (NEW)

**Changes**:
- CREATE TABLE `inbound_order_line` (full work order schema)
- ALTER TABLE `outbound_order_line` (add execution fields)
- CREATE INDEXes for performance

---

## Planning vs Execution Separation

### Planning Phase (Before Game Starts)

**When**: During game setup, data conversion
**Tools**: `convert_beer_game_to_aws_sc.py`
**Creates**:
- Forecasts (52 weeks of demand pattern)
- Inventory policies (target levels per node)
- Sourcing rules (lead times, relationships)
- Production processes (manufacturing capacity)

**Purpose**: Provide context and configuration for execution

### Execution Phase (During Game Rounds)

**When**: Every game round
**Tools**: `BeerGameExecutionAdapter`, `mixed_game_service.py`
**Creates**:
- Work orders (inbound_order_line)
- Customer demand records (outbound_order_line)
- Inventory snapshots (inv_level)

**Purpose**: Track actual orders, fulfillment, and inventory changes

---

## Migration Path

### What Stays the Same ✅
- Legacy Beer Game mode (untouched, 100% backward compatible)
- Feature flag pattern (`use_aws_sc_planning` - name is historical)
- Multi-tenancy filtering (`group_id`, `config_id`)
- Dual-mode architecture

### What Changes ✅
- AWS SC mode now uses EXECUTION, not planning
- Work orders (inbound_order_line) instead of supply plans
- Order lifecycle: submitted → confirmed → received
- Planning happens BEFORE game, execution happens DURING game

### What's Next
1. Update conversion script for execution scenario (mostly done)
2. Run migrations to create `inbound_order_line` table
3. Test dual-mode integration with execution approach
4. Update all documentation

---

## Testing Strategy

### Unit Tests
- ✅ InboundOrderLine model creation
- ✅ OutboundOrderLine execution fields
- ✅ BeerGameExecutionAdapter methods
- ⏳ Work order lifecycle (submitted → received)

### Integration Tests
- ⏳ Legacy mode (unchanged, should pass)
- ⏳ AWS SC execution mode (refactored, needs testing)
- ⏳ Work order creation and delivery processing
- ⏳ 10-round comparison (legacy vs execution)

### Test Script
**File**: `backend/scripts/test_dual_mode_integration.py`

**Changes Needed**:
- Update to test execution flow (not planning flow)
- Verify work orders created correctly
- Verify deliveries processed correctly

---

## AWS SC Documentation References

This refactoring is based on official AWS Supply Chain documentation:

### Work Order Management
- [Work Order Overview](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/work-order.html)
- [Order Planning and Tracking](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/entities-work-order-insights.html)

### Data Entities
- [Inbound Order Line](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/replenishment-inbound-order-line-entity.html)
- [Outbound Order Line](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/outbound-fulfillment-order-line-entity.html)
- [Transactional Data](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/transactional.html)

### Planning vs Execution
- [Planning Process](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/planning-process.html)
- [Business Workflow](https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/sharing_manufacturing_plans.html)

---

## Conclusion

🎉 **Refactoring Complete!**

### What Was Fixed
1. ❌ Beer Game treated as planning scenario
2. ✅ Beer Game now treated as execution scenario
3. ❌ Used supply plans (future recommendations)
4. ✅ Use work orders (immediate execution)
5. ❌ Confused planning with execution
6. ✅ Clear separation: planning before, execution during

### Impact
- **Correctness**: Now aligns with AWS SC's intended use case for execution scenarios
- **Clarity**: Clear distinction between planning (setup) and execution (runtime)
- **Compliance**: Follows AWS SC Work Order Management best practices
- **Extensibility**: Can now leverage AWS SC order tracking features

### Next Steps
1. Run migrations
2. Test execution workflow
3. Update documentation
4. Validate with 10-round comparison

**Status**: Ready for testing phase

---

## Files Changed

| File | Change | Lines | Status |
|------|--------|-------|--------|
| `aws_sc_planning.py` | Added InboundOrderLine, enhanced OutboundOrderLine | +132 | ✅ Complete |
| `20260112_inbound_order_line.py` | Migration for execution tables | +186 | ✅ Complete |
| `beer_game_execution_adapter.py` | NEW execution adapter | +413 | ✅ Complete |
| `mixed_game_service.py` | Refactored to execution workflow | ~200 | ✅ Complete |
| `test_dual_mode_integration.py` | Update for execution testing | TBD | ⏳ Pending |
| Documentation files | Reflect execution architecture | TBD | ⏳ Pending |

**Total Code Added**: ~931 lines
**Total Code Modified**: ~200 lines
**Architectural Shift**: Planning → Execution
**Risk Level**: **LOW** (feature flag isolates changes)

---

**Refactored By**: Claude Sonnet 4.5
**Review Status**: Ready for user review and testing
**Next Session**: Migration execution and integration testing
