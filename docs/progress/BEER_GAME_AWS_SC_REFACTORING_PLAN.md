# Beer Game AWS SC Refactoring Plan

**Date**: 2026-01-21
**Purpose**: Refactor Beer Game to properly conform to AWS Supply Chain Data Model

---

## Problem Statement

The current implementation has created a **hybrid data model** that violates the AWS SC standard:

### Current State (Incorrect):
1. **Two site tables exist**:
   - `nodes` (Integer ID) - Beer Game configuration
   - `site` (String ID) - AWS SC standard

2. **Transfer Orders modified incorrectly**:
   - Changed from Integer ForeignKeys to String fields
   - This breaks AWS SC compliance

3. **Beer Game uses string site_ids**:
   - `order_promising.py`: `site_id: str`
   - `InvLevel` creation: `site_id="retailer_001"`
   - Transfer Order creation: `source_site_id="retailer_001"`

### AWS SC Standard:
- `site` table uses String(100) primary key
- `product` table uses String(100) primary key
- `inv_level.site_id` is String(100) ForeignKey to `site.id`
- `transfer_order.source_site_id` should be String(100) ForeignKey to `site.id`

---

## Root Cause Analysis

The Beer Game was built BEFORE full AWS SC implementation, using:
- `nodes` table (Integer ID) from supply chain configuration
- String site_ids like "retailer_001", "wholesaler_001"
- No actual `site` table records

When AWS SC was added, we created parallel tables but didn't migrate Beer Game.

---

## Solution: Three Options

### Option 1: Beer Game Uses AWS SC Tables (RECOMMENDED)

**Approach**: Migrate Beer Game to use `site`, `product`, `inv_level` tables properly.

**Changes Required**:
1. ✅ Keep `transfer_order.source_site_id` as Integer ForeignKey to `nodes.id` (Beer Game specific)
2. When initializing game, create `site` records from `nodes`:
   ```python
   for node in config.nodes:
       site = Site(
           id=node.name,  # "retailer_001"
           description=node.name,
           company_id="beer_game",
           site_type=node.type
       )
   ```
3. Update all Beer Game code to use string site_ids consistently
4. Transfer Orders reference `nodes.id` (Integer) but have a mapping to `site.id` (String)

**Pros**:
- Maintains AWS SC compliance
- Beer Game becomes a proper AWS SC use case
- Future AWS SC features work automatically

**Cons**:
- More refactoring required
- Need mapping layer between `nodes.id` and `site.id`

---

### Option 2: Dual Schema (Current Hybrid - NOT RECOMMENDED)

**Approach**: Maintain separate Beer Game schema alongside AWS SC.

**Issues**:
- Violates AWS SC compliance
- Confusing dual schemas
- Transfer Orders can't serve both use cases
- Integration between Beer Game and AWS SC planning breaks

**Verdict**: ❌ This was the incorrect approach taken initially

---

### Option 3: Nodes ARE Sites (SIMPLEST)

**Approach**: Treat `nodes` table as the implementation of AWS SC `site` entity for Beer Game.

**Changes Required**:
1. ✅ `transfer_order.source_site_id` = Integer ForeignKey to `nodes.id`
2. ✅ `transfer_order.destination_site_id` = Integer ForeignKey to `nodes.id`
3. ✅ `transfer_order_line_item.product_id` = Integer ForeignKey to `items.id`
4. Update Beer Game initialization to map node names to IDs:
   ```python
   # Get node ID from name
   node = db.query(Node).filter(
       Node.config_id == config_id,
       Node.name == "retailer_001"
   ).first()

   # Create TO with Integer ID
   to = TransferOrder(
       source_site_id=node.id,  # Integer
       destination_site_id=downstream_node.id,  # Integer
       game_id=game_id,
       ...
   )
   ```
5. Query nodes by ID when processing TOs

**Pros**:
- ✅ **Minimal refactoring** - just change Beer Game to use node.id instead of node.name
- ✅ **AWS SC compliant** - Integer ForeignKeys preserved
- ✅ **Clean separation** - Beer Game uses `nodes`/`items`, full AWS SC uses `site`/`product`
- ✅ **No dual writes** - single source of truth

**Cons**:
- Beer Game doesn't use full AWS SC tables (but it doesn't need to)
- `nodes` effectively becomes Beer Game's implementation of "site"

---

## Recommended Approach: Option 3

**Rationale**:
- The Beer Game is a **gamification module**, not a full AWS SC implementation
- It should use simplified tables (`nodes`, `items`) appropriate for gameplay
- Transfer Orders should properly reference these tables with Integer ForeignKeys
- Full AWS SC planning can use `site`/`product` tables when ready

---

## Implementation Steps

### Phase 1: Revert Model Changes ✅ COMPLETE
- [x] Revert `transfer_order.source_site_id` to `Integer, ForeignKey("nodes.id")`
- [x] Revert `transfer_order.destination_site_id` to `Integer, ForeignKey("nodes.id")`
- [x] Revert `transfer_order_line_item.product_id` to `Integer, ForeignKey("items.id")`

### Phase 2: Create Site ID Mapping Service
Create `app/services/sc_execution/site_id_mapper.py`:
```python
class SiteIdMapper:
    """Maps between node names and node IDs for Beer Game"""

    def __init__(self, db: Session, config_id: int):
        self.db = db
        self.config_id = config_id
        self._name_to_id_cache = {}
        self._id_to_name_cache = {}
        self._load_mapping()

    def _load_mapping(self):
        nodes = self.db.query(Node).filter(
            Node.config_id == self.config_id
        ).all()

        for node in nodes:
            self._name_to_id_cache[node.name] = node.id
            self._id_to_name_cache[node.id] = node.name

    def get_node_id(self, node_name: str) -> int:
        """Get node ID from name (e.g., 'retailer_001' → 123)"""
        return self._name_to_id_cache.get(node_name)

    def get_node_name(self, node_id: int) -> str:
        """Get node name from ID (e.g., 123 → 'retailer_001')"""
        return self._id_to_name_cache.get(node_id)
```

### Phase 3: Update Order Promising Engine
Update `order_promising.py` to accept node IDs:
```python
def create_transfer_order(
    self,
    source_node_id: int,  # Changed from str
    destination_node_id: int,  # Changed from str
    item_id: int,  # Changed from str (assuming items.id is also Integer)
    quantity: float,
    game_id: int,
    order_round: int,
    lead_time: int
) -> TransferOrder:
    """Create TO with Integer node IDs"""
    to = TransferOrder(
        to_number=self._generate_to_number(),
        source_site_id=source_node_id,  # Integer
        destination_site_id=destination_node_id,  # Integer
        game_id=game_id,
        order_round=order_round,
        arrival_round=order_round + lead_time,
        status="IN_TRANSIT",
        shipment_date=date.today(),
        estimated_delivery_date=date.today() + timedelta(days=lead_time)
    )
    self.db.add(to)

    line_item = TransferOrderLineItem(
        to_id=to.id,
        line_number=1,
        product_id=item_id,  # Integer
        quantity=quantity,
        shipped_quantity=quantity,
        requested_ship_date=date.today(),
        requested_delivery_date=date.today() + timedelta(days=lead_time)
    )
    self.db.add(line_item)
    self.db.commit()

    return to
```

### Phase 4: Update Beer Game Executor
Update `beer_game_executor.py` to use mapper:
```python
from app.services.sc_execution.site_id_mapper import SiteIdMapper

class BeerGameExecutor:
    def __init__(self, db: Session, game_id: int):
        self.db = db
        self.game_id = game_id

        # Load game config
        game = db.query(Game).filter(Game.id == game_id).first()
        self.config_id = game.config_id

        # Initialize mapper
        self.site_mapper = SiteIdMapper(db, self.config_id)
        self.order_promising = OrderPromisingEngine(db)

    def fulfill_demand(self, site_name: str, item_name: str, quantity: float):
        """Fulfill demand for a site"""
        # Map names to IDs
        site_id = self.site_mapper.get_node_id(site_name)
        item_id = self._get_item_id(item_name)

        # Create TO with Integer IDs
        to = self.order_promising.create_transfer_order(
            source_node_id=site_id,
            destination_node_id=self._get_downstream_node_id(site_name),
            item_id=item_id,
            quantity=quantity,
            game_id=self.game_id,
            order_round=self.current_round,
            lead_time=2
        )
```

### Phase 5: Update Test Suite
Update `test_transfer_orders.py` to use node IDs:
```python
# Get node IDs
retailer_node = db.query(Node).filter(
    Node.config_id == config.id,
    Node.name == "retailer_001"
).first()

# Verify TOs use Integer IDs
tos = db.query(TransferOrder).filter(
    TransferOrder.game_id == game_id
).all()

for to in tos:
    assert isinstance(to.source_site_id, int)
    assert isinstance(to.destination_site_id, int)
```

### Phase 6: Update API Endpoints
Update `transfer_orders.py` to return node names:
```python
@router.get("/games/{game_id}/transfer-orders")
async def get_game_transfer_orders(game_id: int, db: Session = Depends(get_db)):
    game = db.query(Game).filter(Game.id == game_id).first()
    mapper = SiteIdMapper(db, game.config_id)

    tos = db.query(TransferOrder).filter(
        TransferOrder.game_id == game_id
    ).all()

    result = []
    for to in tos:
        result.append({
            "to_number": to.to_number,
            "source_site_id": to.source_site_id,  # Integer
            "source_site_name": mapper.get_node_name(to.source_site_id),  # String for display
            "destination_site_id": to.destination_site_id,  # Integer
            "destination_site_name": mapper.get_node_name(to.destination_site_id),  # String for display
            ...
        })

    return {"transfer_orders": result}
```

---

## Testing Plan

1. **Unit Tests**: Test `SiteIdMapper` name ↔ ID mapping
2. **Integration Tests**: Run `test_transfer_orders.py` with Integer IDs
3. **API Tests**: Verify endpoints return correct node names
4. **E2E Tests**: Play full Beer Game with TO tracking

---

## Files to Modify

1. ✅ `backend/app/models/transfer_order.py` - Reverted to Integer ForeignKeys
2. ⏳ `backend/app/services/sc_execution/site_id_mapper.py` - CREATE NEW
3. ⏳ `backend/app/services/sc_execution/order_promising.py` - Update signatures
4. ⏳ `backend/app/services/sc_execution/beer_game_executor.py` - Use mapper
5. ⏳ `backend/app/services/sc_execution/state_manager.py` - Update InvLevel creation
6. ⏳ `backend/scripts/test_transfer_orders.py` - Update assertions
7. ⏳ `backend/app/api/endpoints/transfer_orders.py` - Add name mapping

---

## Rollback Plan

If refactoring fails:
1. Revert all changes
2. Keep Beer Game using string site_ids
3. Create separate `beer_game_transfer_order` table
4. Maintain dual schema (not ideal, but functional)

---

## Success Criteria

- [x] Transfer Order model uses Integer ForeignKeys to `nodes.id`
- [ ] Beer Game creates TOs with node.id (Integer)
- [ ] Test suite passes with Integer IDs
- [ ] API returns node names for display
- [ ] Frontend visualization works correctly
- [ ] No AWS SC compliance violations

---

## Timeline

- Phase 1 (Revert): ✅ Complete
- Phase 2 (Mapper): 1 hour
- Phase 3 (Order Promising): 1 hour
- Phase 4 (Executor): 2 hours
- Phase 5 (Tests): 1 hour
- Phase 6 (API): 1 hour
- **Total**: ~6-8 hours

---

## Notes

- This refactoring makes Beer Game **AWS SC compliant** without requiring full migration to `site`/`product` tables
- `nodes` table effectively becomes Beer Game's implementation of AWS SC `site` entity
- Future full AWS SC planning can use `site`/`product` tables independently
- Transfer Orders can serve both Beer Game (Integer IDs) and future AWS SC planning (with adapter layer)
