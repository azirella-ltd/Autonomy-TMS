# Transfer Order Implementation Summary

## Overview

This document summarizes the implementation of Transfer Order (TO) generation in the AWS SC execution engine, replacing in-memory `ShipmentRecord` objects with persistent `TransferOrder` entities for full AWS SC compliance.

---

## Problem Statement

**Critical Gap Identified**: The order promising engine (`order_promising.py`) was creating in-memory `ShipmentRecord` dataclass objects instead of persisting `TransferOrder` entities to the database. This violated the AWS SC data model principle that all inter-site inventory movements must be tracked as database entities.

**Impact**:
- No audit trail of shipments
- Cannot track in-transit inventory across multiple periods
- No status lifecycle tracking (DRAFT → RELEASED → SHIPPED → IN_TRANSIT → RECEIVED)
- Incomplete multi-period planning capabilities

---

## Solution Architecture

### 1. Modified Order Promising Engine

**File**: `backend/app/services/sc_execution/order_promising.py`

**Key Changes**:

#### a. Added TransferOrder Imports
```python
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
```

#### b. Updated `promise_order()` Method
**Before**:
- Created `ShipmentRecord` (in-memory dataclass)
- No database persistence
- No status tracking

**After**:
- Creates `TransferOrder` entity in database
- Creates `TransferOrderLineItem` for line-level tracking
- Sets status to "IN_TRANSIT"
- Updates `in_transit_qty` at destination site
- Tracks `order_round` and `arrival_round` for Beer Game

**Method Signature Change**:
```python
# OLD
def promise_order(...) -> Tuple[ATPResult, Optional[ShipmentRecord]]:

# NEW
def promise_order(..., game_id: Optional[int], round_number: Optional[int]) -> Tuple[ATPResult, Optional[TransferOrder]]:
```

#### c. Added Transfer Order Creation Method
```python
def _create_transfer_order(
    self,
    source_site_id: str,
    destination_site_id: str,
    item_id: str,
    quantity: float,
    order_date: date,
    shipment_date: date,
    estimated_delivery_date: date,
    game_id: Optional[int] = None,
    order_round: Optional[int] = None,
    arrival_round: Optional[int] = None
) -> TransferOrder:
    """
    Create Transfer Order entity with line items.

    Status: IN_TRANSIT (immediately shipped in Beer Game)
    TO Number Format: TO-G{game_id}-R{order_round}-{source_site_id}-{timestamp}
    """
```

**Key Features**:
- Generates unique TO number with game/round tracking
- Creates TO header record
- Creates TransferOrderLineItem for each product
- Sets status to "IN_TRANSIT" (Beer Game assumes immediate shipment)
- Persists to database via SQLAlchemy

#### d. Added In-Transit Inventory Update
```python
def _update_in_transit(
    self,
    site_id: str,
    item_id: str,
    qty: float
) -> None:
    """
    Update in-transit quantity at destination site.

    Called when TO is created to track pending arrivals.
    """
```

**Logic**:
- Increases `in_transit_qty` at destination site
- Creates `InvLevel` record if doesn't exist
- Enables multi-period inventory projection

#### e. Added Transfer Order Receipt Methods
```python
def process_arriving_transfers(
    self,
    game_id: int,
    round_number: int
) -> List[TransferOrder]:
    """
    Process all Transfer Orders arriving in current round.

    Query: WHERE game_id = X AND arrival_round = N AND status = 'IN_TRANSIT'
    """

def receive_transfer_order(self, to: TransferOrder) -> None:
    """
    Receive transfer order at destination site.

    Updates:
    1. in_transit_qty decreases
    2. on_hand_qty increases
    3. TO status: IN_TRANSIT → RECEIVED
    4. actual_delivery_date set
    """
```

**Lifecycle Management**:
- Queries TOs with matching `arrival_round`
- Moves inventory from in-transit to on-hand
- Updates TO status to "RECEIVED"
- Records `actual_delivery_date`

### 2. Updated Beer Game Executor

**File**: `backend/app/services/sc_execution/beer_game_executor.py`

**Changes in `execute_round()` Method**:

#### Step 1: Receive Shipments
**Before**:
```python
arriving_pos = self.po_creator.process_arriving_orders(game_id, round_number)
```

**After**:
```python
# 1a. Process arriving Purchase Orders
arriving_pos = self.po_creator.process_arriving_orders(game_id, round_number)

# 1b. Process arriving Transfer Orders (NEW!)
arriving_tos = self.order_promising.process_arriving_transfers(game_id, round_number)
```

**Output**:
```
📦 STEP 1: Receiving Shipments (POs and TOs arriving this round)
✓ Received 2 purchase orders
  • PO-G1-R3-factory_001: 15 units → distributor_001
✓ Received 3 transfer orders
  • TO-G1-R3-wholesaler_001-1234567890: wholesaler_001 → retailer_001
  • TO-G1-R3-distributor_001-1234567891: distributor_001 → wholesaler_001
```

#### Step 3: Order Promising
**Updated to show TO numbers**:
```python
for atp, transfer_order in atp_results:
    to_info = f"TO: {transfer_order.to_number}" if transfer_order else "No TO"
    print(f"  • {atp.site_id}: {status} fulfillment - {to_info}")
```

**Round Summary Now Includes TOs**:
```python
round_summary["steps"]["shipments_received"] = {
    "purchase_orders": {
        "count": len(arriving_pos),
        "pos": [po.po_number for po in arriving_pos]
    },
    "transfer_orders": {
        "count": len(arriving_tos),
        "tos": [to.to_number for to in arriving_tos]
    }
}

round_summary["steps"]["order_promising"]["results"] = [
    {
        "site_id": atp.site_id,
        "requested": atp.requested_qty,
        "fulfilled": atp.promised_qty,
        "backorder": atp.backorder_qty,
        "transfer_order": to.to_number if to else None  # NEW!
    }
    for atp, to in atp_results
]
```

---

## Transfer Order Data Model

### TransferOrder Entity

**Table**: `transfer_order`

```python
class TransferOrder(Base):
    __tablename__ = "transfer_order"

    id = Column(Integer, primary_key=True)
    to_number = Column(String(100), unique=True, nullable=False)

    # Sites
    source_site_id = Column(String(100), ForeignKey("nodes.site_id"))
    destination_site_id = Column(String(100), ForeignKey("nodes.site_id"))

    # Status Lifecycle
    status = Column(String(20))  # DRAFT, RELEASED, SHIPPED, IN_TRANSIT, RECEIVED

    # Dates
    order_date = Column(Date)
    shipment_date = Column(Date)
    estimated_delivery_date = Column(Date)
    actual_delivery_date = Column(Date)

    # Beer Game Extensions
    game_id = Column(Integer, ForeignKey("games.id"))
    order_round = Column(Integer)      # Round when TO was created
    arrival_round = Column(Integer)    # Round when TO arrives

    # Audit
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, onupdate=datetime.now)
```

### TransferOrderLineItem Entity

**Table**: `transfer_order_line_item`

```python
class TransferOrderLineItem(Base):
    __tablename__ = "transfer_order_line_item"

    id = Column(Integer, primary_key=True)
    to_id = Column(Integer, ForeignKey("transfer_order.id"))

    line_number = Column(Integer)
    product_id = Column(String(100), ForeignKey("items.item_id"))

    ordered_quantity = Column(Float)
    shipped_quantity = Column(Float)
    received_quantity = Column(Float)

    requested_delivery_date = Column(Date)
```

---

## Transfer Order Lifecycle

### Status Progression

```
┌─────────┐
│  DRAFT  │  Order created but not approved
└────┬────┘
     │ approve()
     ▼
┌──────────┐
│ RELEASED │  Approved, ready for fulfillment
└────┬─────┘
     │ fulfill_order() → allocate inventory
     ▼
┌──────────┐
│ SHIPPED  │  Inventory shipped from source
└────┬─────┘
     │ set_in_transit()
     ▼
┌────────────┐
│ IN_TRANSIT │  Shipment traveling to destination
└─────┬──────┘
     │ arrival_round reached → receive_transfer_order()
     ▼
┌──────────┐
│ RECEIVED │  Shipment arrived at destination
└──────────┘
```

**Beer Game Simplification**: TOs are created directly in "IN_TRANSIT" status since the game assumes immediate shipment after ATP allocation.

### Inventory Updates

**1. When TO is Created (promise_order)**:
```python
# At source site
inv_level.allocated_qty += promised_qty  # Reserve inventory

# Ship inventory
inv_level.on_hand_qty -= promised_qty    # Inventory leaves
inv_level.allocated_qty -= promised_qty  # No longer allocated

# At destination site
inv_level.in_transit_qty += promised_qty # Track pending arrival
```

**2. When TO is Received (receive_transfer_order)**:
```python
# At destination site
inv_level.in_transit_qty -= shipped_quantity  # Remove from transit
inv_level.on_hand_qty += shipped_quantity     # Add to on-hand
```

---

## DAG Traversal Logic

### Supply Chain Structure

```
[Market Demand] → [Retailer] → [Wholesaler] → [Distributor] → [Factory] → [Market Supply]
      (sink)      (INVENTORY)   (INVENTORY)    (INVENTORY)   (MANUF)      (source)
```

### Round Execution Flow

**Round N**:

1. **Receive Shipments** (Upstream → Downstream):
   - Process TOs with `arrival_round == N`
   - Move inventory from in-transit to on-hand
   - Update TO status to RECEIVED

2. **Generate Market Demand** (Downstream Boundary):
   - Create `OutboundOrderLine` at Retailer
   - Market demand quantity provided by game logic

3. **Order Promising** (Downstream → Upstream Fulfillment):
   - **Retailer** promises to Market Demand
     - Calculate ATP: `on_hand - allocated - safety_stock`
     - Create TO: Retailer → MARKET (immediate delivery)
     - Update Retailer inventory

   - **Wholesaler** promises to Retailer (if Retailer ordered previous round)
     - Calculate ATP at Wholesaler
     - Create TO: Wholesaler → Retailer (arrival_round = N + 2)
     - Update Wholesaler inventory
     - Update Retailer in_transit_qty

   - **Distributor** promises to Wholesaler
   - **Factory** promises to Distributor

4. **Agent Decisions** (Compute Order Quantities):
   - Agents observe state: `on_hand_qty`, `in_transit_qty`, `backorder_qty`
   - Agents decide order quantities
   - Decisions passed to next step

5. **Create Purchase Orders** (Downstream → Upstream Orders):
   - Retailer's decision → PO: Wholesaler → Retailer
   - Wholesaler's decision → PO: Distributor → Wholesaler
   - Distributor's decision → PO: Factory → Distributor
   - Update `in_transit_qty` at ordering sites

6. **Cost Accrual**:
   - Calculate holding costs: `on_hand_qty * holding_cost_per_unit`
   - Calculate backlog costs: `backorder_qty * backlog_cost_per_unit`

7. **State Snapshot**:
   - Capture current state for analytics

---

## Example: 3-Round Execution

### Configuration
- **Sites**: Retailer, Wholesaler, Factory
- **Lead Times**:
  - Wholesaler → Retailer: 2 weeks (2 rounds)
  - Factory → Wholesaler: 2 weeks (2 rounds)
- **Initial Inventory**: 12 units each

### Round 1

**Before**:
```
Retailer:   on_hand=12, in_transit=0, backorder=0
Wholesaler: on_hand=12, in_transit=0, backorder=0
Factory:    on_hand=12, in_transit=0, backorder=0
```

**Execution**:
1. Receive shipments: None
2. Market demand: 8 units
3. Order promising:
   - Retailer promises 8 → MARKET
   - Creates TO-G1-R1-retailer-12345: Retailer → MARKET (8 units, arrival R1)
   - Retailer: `on_hand=12→4`
4. Agent decisions:
   - Retailer orders 10
   - Wholesaler orders 12
5. Create POs:
   - PO-G1-R1-retailer: Wholesaler → Retailer (10 units, arrival R3)
   - PO-G1-R1-wholesaler: Factory → Wholesaler (12 units, arrival R3)
   - Retailer: `in_transit=0→10`
   - Wholesaler: `in_transit=0→12`

**After**:
```
Retailer:   on_hand=4, in_transit=10 (arriving R3), backorder=0
Wholesaler: on_hand=12, in_transit=12 (arriving R3), backorder=0
Factory:    on_hand=12, in_transit=0, backorder=0
```

### Round 2

**Before**:
```
Retailer:   on_hand=4, in_transit=10, backorder=0
Wholesaler: on_hand=12, in_transit=12, backorder=0
Factory:    on_hand=12, in_transit=0, backorder=0
```

**Execution**:
1. Receive shipments: None (TOs arrive R3)
2. Market demand: 8 units
3. Order promising:
   - Retailer has only 4 on-hand
   - Retailer promises 4 → MARKET (partial fulfillment)
   - Backorder: 4 units
   - Retailer: `on_hand=4→0, backorder=0→4`
4. Agent decisions:
   - Retailer orders 15 (panic!)
   - Wholesaler orders 12
5. Create POs:
   - PO-G1-R2-retailer: Wholesaler → Retailer (15 units, arrival R4)
   - PO-G1-R2-wholesaler: Factory → Wholesaler (12 units, arrival R4)
   - Retailer: `in_transit=10→25`
   - Wholesaler: `in_transit=12→24`

**After**:
```
Retailer:   on_hand=0, in_transit=25 (10@R3, 15@R4), backorder=4
Wholesaler: on_hand=12, in_transit=24 (12@R3, 12@R4), backorder=0
Factory:    on_hand=12, in_transit=0, backorder=0
```

### Round 3

**Before**:
```
Retailer:   on_hand=0, in_transit=25, backorder=4
Wholesaler: on_hand=12, in_transit=24, backorder=0
Factory:    on_hand=12, in_transit=0, backorder=0
```

**Execution**:
1. Receive shipments:
   - **PO-G1-R1-retailer arrives**: Wholesaler → Retailer (10 units)
     - Wholesaler fulfills with TO-G1-R3-wholesaler-XXX
     - Retailer: `in_transit=25→15, on_hand=0→10`
   - **PO-G1-R1-wholesaler arrives**: Factory → Wholesaler (12 units)
     - Wholesaler: `in_transit=24→12, on_hand=12→24`

2. Market demand: 8 units
3. Order promising:
   - Retailer has 10 on-hand
   - Fulfills 8 to market + attempts backorder fulfillment
   - Can fulfill 2 of 4 backorder units
   - Retailer: `on_hand=10→0, backorder=4→2`

4. Agent decisions:
   - Retailer orders 20
   - Wholesaler orders 15

5. Create POs:
   - PO-G1-R3-retailer: Wholesaler → Retailer (20 units, arrival R5)
   - PO-G1-R3-wholesaler: Factory → Wholesaler (15 units, arrival R5)

**After**:
```
Retailer:   on_hand=0, in_transit=35 (15@R4, 20@R5), backorder=2
Wholesaler: on_hand=4, in_transit=27 (12@R4, 15@R5), backorder=0
Factory:    on_hand=12, in_transit=0, backorder=0
```

**Bullwhip Effect Visible**: Retailer's panic order (10→15→20) propagates upstream.

---

## Multi-Period In-Transit Tracking

### In-Transit Schedule

**Query**: Get all in-transit TOs for a site:
```sql
SELECT
    to_number,
    source_site_id,
    quantity,
    order_round,
    arrival_round,
    estimated_delivery_date
FROM transfer_order
WHERE destination_site_id = 'retailer_001'
  AND status = 'IN_TRANSIT'
ORDER BY arrival_round ASC;
```

**Result (Round 3)**:
```
| to_number              | source       | qty | order_round | arrival_round | est_delivery   |
|------------------------|--------------|-----|-------------|---------------|----------------|
| TO-G1-R2-wholesaler-XX | wholesaler   | 15  | 2           | 4             | 2026-02-01     |
| TO-G1-R3-wholesaler-YY | wholesaler   | 20  | 3           | 5             | 2026-02-08     |
```

### Inventory Projection

**Formula**:
```python
def project_inventory(site_id: str, item_id: str, future_rounds: int) -> Dict[int, float]:
    """
    Project inventory levels across future rounds.

    Returns: {round_number: projected_on_hand}
    """
    current_inv = get_inv_level(site_id, item_id)

    # Get in-transit schedule
    in_transit = query_transfer_orders(
        destination_site_id=site_id,
        status="IN_TRANSIT"
    ).order_by(arrival_round)

    # Get historical demand average
    avg_demand = calculate_avg_demand(site_id, item_id, window=4)

    projection = {}
    projected_on_hand = current_inv.on_hand_qty

    for round_num in range(current_round + 1, current_round + future_rounds + 1):
        # Expected demand
        projected_on_hand -= avg_demand

        # Expected arrivals
        arrivals = [to for to in in_transit if to.arrival_round == round_num]
        for to in arrivals:
            projected_on_hand += to.quantity

        projection[round_num] = max(0, projected_on_hand)

    return projection
```

**Example Output (Round 3 for Retailer)**:
```python
{
    4: 8.0,   # 0 current + 15 arriving - 8 demand = 7 (but had 0, so backorder reduced)
    5: 19.0,  # 7 + 20 arriving - 8 demand = 19
    6: 11.0,  # 19 + 0 arriving - 8 demand = 11
    7: 3.0,   # 11 + 0 arriving - 8 demand = 3
}
```

**Reorder Signal**: When projected inventory falls below reorder point in any period, agent should order.

---

## AWS SC Compliance Checklist

### ✅ Implemented
- [x] TransferOrder entity creation
- [x] TransferOrderLineItem for line-level tracking
- [x] Status lifecycle (IN_TRANSIT → RECEIVED)
- [x] In-transit inventory tracking at destination
- [x] Multi-period arrival scheduling via `arrival_round`
- [x] Arrival processing with `process_arriving_transfers()`
- [x] Inventory updates (in_transit → on_hand)
- [x] Integration with BeerGameExecutor
- [x] Round summary includes TO tracking
- [x] TO number generation with game/round context

### 🔄 Partially Implemented
- [ ] Full TO status lifecycle (currently skips DRAFT/RELEASED/SHIPPED states)
- [ ] Transportation lead time from sourcing rules (currently hardcoded in arrival_round calculation)
- [ ] TO approval workflow (currently auto-approved)

### ❌ Not Yet Implemented
- [ ] TO modification/cancellation
- [ ] Partial shipment handling (multiple TOs per PO)
- [ ] TO consolidation (multiple line items)
- [ ] Cross-docking scenarios
- [ ] Transportation cost tracking
- [ ] Carrier assignment
- [ ] Route optimization

---

## Testing Recommendations

### Unit Tests

**Test 1: Transfer Order Creation**
```python
def test_create_transfer_order():
    """Test TO creation with proper fields."""
    to = order_promising._create_transfer_order(
        source_site_id="wholesaler_001",
        destination_site_id="retailer_001",
        item_id="cases",
        quantity=10.0,
        order_date=date(2026, 1, 15),
        shipment_date=date(2026, 1, 15),
        estimated_delivery_date=date(2026, 1, 29),
        game_id=1,
        order_round=5,
        arrival_round=7
    )

    assert to.to_number == "TO-G1-R5-wholesaler_001-*"
    assert to.source_site_id == "wholesaler_001"
    assert to.destination_site_id == "retailer_001"
    assert to.status == "IN_TRANSIT"
    assert to.order_round == 5
    assert to.arrival_round == 7
```

**Test 2: In-Transit Update**
```python
def test_in_transit_update():
    """Test in_transit_qty increases at destination."""
    initial_inv = get_inv_level("retailer_001", "cases")
    initial_in_transit = initial_inv.in_transit_qty

    order_promising._update_in_transit("retailer_001", "cases", 10.0)

    updated_inv = get_inv_level("retailer_001", "cases")
    assert updated_inv.in_transit_qty == initial_in_transit + 10.0
```

**Test 3: Transfer Order Receipt**
```python
def test_receive_transfer_order():
    """Test TO receipt moves inventory from in-transit to on-hand."""
    # Create TO
    to = create_test_transfer_order(
        source="wholesaler_001",
        destination="retailer_001",
        quantity=10.0,
        arrival_round=7
    )

    # Mark as in-transit
    to.status = "IN_TRANSIT"
    db.commit()

    # Update destination in_transit
    order_promising._update_in_transit("retailer_001", "cases", 10.0)

    initial_inv = get_inv_level("retailer_001", "cases")
    initial_on_hand = initial_inv.on_hand_qty
    initial_in_transit = initial_inv.in_transit_qty

    # Receive TO
    order_promising.receive_transfer_order(to)

    updated_inv = get_inv_level("retailer_001", "cases")
    assert updated_inv.in_transit_qty == initial_in_transit - 10.0
    assert updated_inv.on_hand_qty == initial_on_hand + 10.0
    assert to.status == "RECEIVED"
    assert to.actual_delivery_date is not None
```

**Test 4: Multi-Round Arrival Processing**
```python
def test_process_arriving_transfers():
    """Test processing multiple TOs arriving in same round."""
    # Create 3 TOs arriving in Round 7
    create_test_transfer_order(arrival_round=7, quantity=10)
    create_test_transfer_order(arrival_round=7, quantity=15)
    create_test_transfer_order(arrival_round=7, quantity=12)

    # Create 1 TO arriving in Round 8 (should not process)
    create_test_transfer_order(arrival_round=8, quantity=20)

    arriving_tos = order_promising.process_arriving_transfers(game_id=1, round_number=7)

    assert len(arriving_tos) == 3
    assert all(to.status == "RECEIVED" for to in arriving_tos)
```

### Integration Tests

**Test 5: Full Round Execution with TOs**
```python
def test_full_round_execution_with_tos():
    """Test complete round execution creates and receives TOs."""
    # Setup game
    game_id = create_test_game()
    initialize_game_state(game_id, initial_inventory=12.0)

    # Round 1
    executor.execute_round(
        game_id=game_id,
        round_number=1,
        agent_decisions={"retailer_001": 10, "wholesaler_001": 12},
        market_demand=8.0
    )

    # Verify TOs created
    tos_r1 = query_transfer_orders(game_id=game_id, order_round=1)
    assert len(tos_r1) == 1  # Retailer → MARKET
    assert tos_r1[0].source_site_id == "retailer_001"
    assert tos_r1[0].destination_site_id == "MARKET"

    # Round 3 (arrivals)
    executor.execute_round(
        game_id=game_id,
        round_number=3,
        agent_decisions={"retailer_001": 15, "wholesaler_001": 15},
        market_demand=8.0
    )

    # Verify POs fulfilled with TOs
    tos_r3 = query_transfer_orders(game_id=game_id, order_round=3, status="IN_TRANSIT")
    assert len(tos_r3) >= 2  # Wholesaler → Retailer, Distributor → Wholesaler

    # Verify arrivals received
    arrived_tos = query_transfer_orders(game_id=game_id, arrival_round=3, status="RECEIVED")
    assert len(arrived_tos) > 0
```

---

## Performance Considerations

### Database Queries

**Concern**: Each TO creation involves multiple database writes:
1. Insert TransferOrder
2. Insert TransferOrderLineItem
3. Update InvLevel (source allocated_qty)
4. Update InvLevel (source on_hand_qty)
5. Update InvLevel (destination in_transit_qty)

**Optimization**: Batch commits in `process_round_demand()`:
```python
# Current: Commits after each promise_order()
def promise_order(...):
    # ... allocate, ship, create TO ...
    self.db.commit()  # ❌ Multiple commits per round

# Optimized: Single commit per round
def process_round_demand(...):
    results = []
    for order in orders:
        atp_result, to = self.promise_order(...)  # No commit
        results.append((atp_result, to))

    self.db.commit()  # ✅ Single commit
    return results
```

### Indexing Recommendations

```sql
-- Speed up arrival processing
CREATE INDEX idx_to_arrival_lookup
ON transfer_order (game_id, arrival_round, status);

-- Speed up in-transit queries
CREATE INDEX idx_to_destination_status
ON transfer_order (destination_site_id, status);

-- Speed up TO number lookups
CREATE UNIQUE INDEX idx_to_number
ON transfer_order (to_number);
```

---

## Future Enhancements

### 1. Full Status Lifecycle
Implement DRAFT → RELEASED → SHIPPED progression for more realistic TO management:
```python
def release_transfer_order(to_id: int):
    """Approve TO for fulfillment."""
    to = db.query(TransferOrder).filter(TransferOrder.id == to_id).first()
    to.status = "RELEASED"
    db.commit()

def ship_transfer_order(to_id: int):
    """Ship TO (allocate and reduce on-hand)."""
    to = db.query(TransferOrder).filter(TransferOrder.id == to_id).first()
    # ... allocate and ship inventory ...
    to.status = "SHIPPED"
    to.shipment_date = date.today()
    to.status = "IN_TRANSIT"
    db.commit()
```

### 2. Transportation Lead Time from Sourcing Rules
Read lead times from `sourcing_rules.lead_time_days`:
```python
def _calculate_arrival_round(
    self,
    source_site_id: str,
    destination_site_id: str,
    item_id: str,
    order_round: int
) -> int:
    """Calculate arrival round using sourcing rule lead time."""
    sourcing_rule = self.db.query(SourcingRules).filter(
        and_(
            SourcingRules.source_site_id == source_site_id,
            SourcingRules.destination_site_id == destination_site_id,
            SourcingRules.item_id == item_id
        )
    ).first()

    lead_time_days = sourcing_rule.lead_time_days if sourcing_rule else 14
    lead_time_rounds = lead_time_days // 7
    return order_round + lead_time_rounds
```

### 3. Partial Shipments
Support splitting POs into multiple TOs:
```python
def fulfill_purchase_order_partial(po: PurchaseOrder, fulfill_qty: float):
    """Fulfill PO with partial quantity."""
    to = create_transfer_order(quantity=fulfill_qty)

    # Update PO status
    po.fulfilled_quantity += fulfill_qty
    if po.fulfilled_quantity >= po.quantity:
        po.status = "FULLY_SHIPPED"
    else:
        po.status = "PARTIALLY_SHIPPED"
```

### 4. TO Consolidation
Combine multiple PO line items into single TO:
```python
def create_consolidated_transfer_order(pos: List[PurchaseOrder]):
    """Create single TO for multiple POs."""
    to = TransferOrder(...)

    for i, po in enumerate(pos):
        to_line = TransferOrderLineItem(
            to_id=to.id,
            line_number=i + 1,
            product_id=po.product_id,
            ordered_quantity=po.quantity,
            ...
        )
        db.add(to_line)
```

---

## Summary

### Key Achievements

1. **AWS SC Compliance**: All inter-site inventory movements now persisted as `TransferOrder` entities
2. **Multi-Period Tracking**: In-transit inventory tracked across multiple planning periods via `arrival_round`
3. **Status Lifecycle**: TO status progression from IN_TRANSIT → RECEIVED
4. **Audit Trail**: Complete history of all shipments in database
5. **Integration**: Seamless integration with Beer Game executor

### Benefits

- **Visibility**: Real-time tracking of all in-transit shipments
- **Planning**: Multi-period inventory projection based on scheduled arrivals
- **Debugging**: Full audit trail for troubleshooting game issues
- **Analytics**: Query TO history for bullwhip analysis, lead time analysis
- **Compliance**: Follows AWS SC data model standards

### Next Steps

1. Test with full 52-round Beer Game simulation
2. Validate in-transit inventory projections
3. Add TO analytics to game report (TO count, average lead time, on-time delivery %)
4. Implement TO visualization in frontend (shipment timeline)
5. Extend to production scenarios (Manufacturing Orders with TOs)

---

## Related Documentation

- [TRANSFER_ORDERS_AND_DAG_TRAVERSAL.md](TRANSFER_ORDERS_AND_DAG_TRAVERSAL.md) - Comprehensive guide to Transfer Orders, DAG traversal, and multi-period planning
- [AWS_SC_EXECUTION_ENGINE_COMPLETE.md](AWS_SC_EXECUTION_ENGINE_COMPLETE.md) - Complete AWS SC execution engine documentation
- [BEER_GAME_AS_AWS_SC_EXECUTION.md](BEER_GAME_AS_AWS_SC_EXECUTION.md) - Architectural design document
