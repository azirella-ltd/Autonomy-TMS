# Beer Game AWS SC Refactoring - Progress Report

**Date**: 2026-01-21
**Status**: Phase 3 In Progress

---

## Completed Work ✅

### Phase 1: Revert Model Changes ✅
- [x] Reverted `transfer_order.source_site_id` to `Integer, ForeignKey("nodes.id")`
- [x] Reverted `transfer_order.destination_site_id` to `Integer, ForeignKey("nodes.id")`
- [x] Reverted `transfer_order_line_item.product_id` to `Integer, ForeignKey("items.id")`
- [x] Model now AWS SC compliant with Integer ForeignKeys

**Files Modified**:
- `backend/app/models/transfer_order.py` ✅

### Phase 2: Create ID Mapping Service ✅
- [x] Created `SiteIdMapper` class (node name ↔ node ID)
- [x] Created `ItemIdMapper` class (item name ↔ item ID)
- [x] Created `BeerGameIdMapper` convenience wrapper

**Files Created**:
- `backend/app/services/sc_execution/site_id_mapper.py` ✅

### Phase 3: Update Order Promising Engine ✅
- [x] Updated all type hints from `str` to `int` for site_id/item_id
- [x] Updated `ATPResult` dataclass to use Integer IDs
- [x] Updated `ShipmentRecord` dataclass to use Integer IDs
- [x] Updated `calculate_atp()` signature
- [x] Updated `promise_order()` signature
- [x] Updated `fulfill_market_demand()` signature
- [x] Updated `_create_transfer_order()` to use Integer IDs
- [x] Updated all helper methods (`_allocate_inventory`, `_ship_inventory`, etc.)
- [x] Updated `get_inventory_status()` signature

**Files Modified**:
- `backend/app/services/sc_execution/order_promising.py` ✅

### Phase 4: Update Beer Game Executor (Partial) ⏳
- [x] Added `BeerGameIdMapper` import
- [x] Added `_get_id_mapper()` helper method
- [ ] Update round execution to map site names to IDs
- [ ] Update PO creation to use mapper
- [ ] Update state manager to use mapper

**Files Modified**:
- `backend/app/services/sc_execution/beer_game_executor.py` (partial)

---

## Remaining Work ⏳

### Phase 4: Complete Beer Game Executor
**Priority**: HIGH

The executor currently receives `agent_decisions: Dict[str, float]` where keys are site names like "retailer_001". Need to:

1. Map site names to node IDs when calling order promising
2. Update PO creator to use Integer IDs
3. Update state manager to use Integer IDs

**Key Decision**: Keep high-level interface string-based for usability.
- External interface: `agent_decisions["retailer_001"] = 12.0`
- Internal AWS SC calls: Use Integer node IDs

**Files to Update**:
- `backend/app/services/sc_execution/beer_game_executor.py`
- `backend/app/services/sc_execution/po_creation.py`
- `backend/app/services/sc_execution/state_manager.py`

### Phase 5: Update Test Suite
**Priority**: HIGH

The test suite (`test_transfer_orders.py`) currently:
- Creates TOs with string site_ids
- Validates using string site_ids

Need to:
1. Get node IDs from node names
2. Create TOs with Integer node IDs
3. Validate Integer IDs in assertions
4. Update validation checks

**Files to Update**:
- `backend/scripts/test_transfer_orders.py`

### Phase 6: Update API Endpoints
**Priority**: MEDIUM

API endpoints return Transfer Orders but need to include human-readable names for display.

Current response:
```json
{
  "source_site_id": 123,  // Integer
  "destination_site_id": 456  // Integer
}
```

Desired response:
```json
{
  "source_site_id": 123,
  "source_site_name": "retailer_001",  // Added for display
  "destination_site_id": 456,
  "destination_site_name": "wholesaler_001"  // Added for display
}
```

**Files to Update**:
- `backend/app/api/endpoints/transfer_orders.py`

---

## Architecture Decisions

### Decision 1: Nodes ARE Sites (for Beer Game)
**Rationale**: Beer Game uses simplified `nodes`/`items` tables. Full AWS SC uses `site`/`product` tables. Transfer Orders reference `nodes` table.

**Implications**:
- ✅ Beer Game conformsto AWS SC data model (Integer ForeignKeys)
- ✅ Minimal refactoring required
- ✅ Clean separation between Beer Game and full AWS SC
- ✅ Transfer Orders are AWS SC compliant

### Decision 2: String Interface, Integer Implementation
**Rationale**: Beer Game users think in terms of "retailer_001", not node ID 123.

**Implementation**:
- External API: String site names
- Internal AWS SC: Integer node IDs
- Mapper translates at the boundary

**Example**:
```python
# User provides
agent_decisions = {"retailer_001": 12.0}

# Executor maps to IDs
mapper = self._get_id_mapper(game_id)
node_id = mapper.get_node_id("retailer_001")  # → 123

# Order promising uses Integer
self.order_promising.promise_order(
    site_id=node_id,  # Integer
    item_id=item_id,  # Integer
    ...
)
```

### Decision 3: Two-Table Architecture
**Current State**:
- `nodes` table (Integer ID) - Beer Game configuration
- `site` table (String ID) - Full AWS SC (future)

**Why This Works**:
- Beer Game doesn't need full `site` table complexity
- Transfer Orders reference `nodes` table (Integer FK)
- Full AWS SC planning can use `site` table when ready
- No data duplication or sync issues

---

## Data Model Diagram

```
Beer Game Architecture:

┌─────────────────┐
│ supply_chain_   │
│    configs      │
└────────┬────────┘
         │
         ├─────────────┐
         │             │
    ┌────▼─────┐  ┌────▼────┐
    │  nodes   │  │  items  │
    │  (Int)   │  │  (Int)  │
    └────┬─────┘  └────┬────┘
         │             │
         │             │
    ┌────▼─────────────▼────┐
    │   transfer_order      │
    │                       │
    │  source_site_id: FK → nodes.id    │
    │  dest_site_id: FK → nodes.id      │
    │  product_id: FK → items.id (line) │
    └───────────────────────┘

Full AWS SC (Future):

┌──────────┐  ┌───────────┐
│   site   │  │  product  │
│ (String) │  │ (String)  │
└──────────┘  └───────────┘
     │             │
     │             │
┌────▼─────────────▼────┐
│   inv_level           │
│   sourcing_rules      │
│   supply_plan         │
└───────────────────────┘
```

---

## Critical Files Status

| File | Status | Changes Needed |
|------|--------|----------------|
| `transfer_order.py` | ✅ Complete | None - reverted to Integer FKs |
| `site_id_mapper.py` | ✅ Complete | None - mapper service created |
| `order_promising.py` | ✅ Complete | None - all signatures updated |
| `beer_game_executor.py` | ⏳ Partial | Map site names to IDs in execution |
| `po_creation.py` | ❌ Not Started | Update to use Integer IDs |
| `state_manager.py` | ❌ Not Started | Update InvLevel creation |
| `test_transfer_orders.py` | ❌ Not Started | Update to use node IDs |
| `transfer_orders.py` (API) | ❌ Not Started | Add name mapping for display |

---

## Testing Plan

1. **Unit Tests**: Test `BeerGameIdMapper` name ↔ ID mapping
2. **Integration Tests**: Run `test_transfer_orders.py` with Integer IDs
3. **API Tests**: Verify endpoints return correct node names
4. **E2E Tests**: Play full Beer Game with TO tracking

---

## Next Steps (Prioritized)

1. ✅ **Complete beer_game_executor.py**
   - Add site name → ID mapping in `execute_round()`
   - Update calls to order promising

2. **Update po_creation.py**
   - Accept mapper or use Integer IDs directly
   - Create POs with Integer node IDs

3. **Update state_manager.py**
   - Handle Integer node IDs for InvLevel
   - Or create mapping layer for InvLevel

4. **Update test_transfer_orders.py**
   - Query nodes to get IDs
   - Create TOs with Integer IDs
   - Validate Integer IDs

5. **Update transfer_orders.py API**
   - Add mapper to return node names
   - Provide both ID and name in response

6. **End-to-End Testing**
   - Run full Beer Game
   - Verify TOs created correctly
   - Check frontend visualization

---

## Rollback Plan

If refactoring causes issues:
1. Revert model changes (String IDs)
2. Keep Beer Game using string site_ids
3. Accept non-AWS-SC-compliance for Beer Game
4. Create separate beer_game_transfer_order table

**Not Recommended**: Defeats AWS SC compliance goal.

---

## Success Metrics

- [x] Transfer Order model uses Integer ForeignKeys ✅
- [ ] Test suite passes with Integer IDs
- [ ] Beer Game plays successfully end-to-end
- [ ] API returns correct node names for display
- [ ] Frontend visualization works
- [ ] No AWS SC compliance violations
- [ ] Performance acceptable (< 1s per round)

---

## Open Questions

1. **InvLevel Table**: Should InvLevel also reference `nodes.id` (Integer) instead of `site.id` (String)?
   - **Current**: InvLevel.site_id is String FK to site.id
   - **Beer Game Uses**: String site_ids when creating InvLevel
   - **Issue**: Mismatch between Transfer Orders (Integer) and InvLevel (String)
   - **Solution**: Either:
     a) Create `inv_level_game` table for Beer Game (Integer FK to nodes)
     b) Store both node.id and node.name in InvLevel queries
     c) Always query by node.id and accept InvLevel uses strings

2. **PurchaseOrder Table**: Does PurchaseOrder also need Integer site_ids?
   - **Current**: PO likely uses string site_ids
   - **Compatibility**: Need to verify PO ↔ TO compatibility

---

## Documentation

- [x] Created BEER_GAME_AWS_SC_REFACTORING_PLAN.md
- [x] Created REFACTORING_PROGRESS.md
- [ ] Update TRANSFER_ORDER_INTEGRATION_GUIDE.md with Integer ID approach
- [ ] Update API documentation
- [ ] Update developer guide

---

**Last Updated**: 2026-01-21 15:30 UTC
**Next Review**: After completing beer_game_executor.py
