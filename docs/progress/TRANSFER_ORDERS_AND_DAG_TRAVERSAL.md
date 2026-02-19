# Transfer Orders and DAG Traversal in AWS SC Execution

## Overview

This document explains how the Beer Game execution engine creates Transfer Orders (TOs) during order promising, traverses the supply chain DAG, and manages multi-period progression with lead times.

## Critical Gap Identified

**Current Implementation**: `order_promising.py` creates in-memory `ShipmentRecord` objects but does NOT persist `TransferOrder` entities to the database.

**Required Implementation**: Order promising must create `TransferOrder` entities following AWS SC data model to ensure:
- Audit trail of all inter-site movements
- Proper in-transit inventory tracking
- Multi-period lead time management
- Status lifecycle tracking (DRAFT → RELEASED → SHIPPED → IN_TRANSIT → RECEIVED)

---

## 1. Transfer Order vs Purchase Order

### Transfer Order (TO)
- **Definition**: Inter-site inventory movement within the same organization
- **Example**: Wholesaler → Retailer (both sites owned by same company)
- **AWS SC Entity**: `transfer_order` table
- **Key Fields**:
  - `source_site_id`: Sending site (e.g., "wholesaler_001")
  - `destination_site_id`: Receiving site (e.g., "retailer_001")
  - `status`: DRAFT, RELEASED, SHIPPED, IN_TRANSIT, RECEIVED
  - `shipment_date`: When shipment leaves source site
  - `estimated_delivery_date`: Expected arrival (based on lead time)
  - `actual_delivery_date`: When shipment actually arrives

### Purchase Order (PO)
- **Definition**: External procurement from suppliers outside the organization
- **Example**: Factory → External Supplier (buying raw materials)
- **AWS SC Entity**: `purchase_order` table
- **Key Fields**:
  - `supplier_site_id`: External vendor
  - `destination_site_id`: Receiving site
  - `status`: DRAFT, APPROVED, SENT, RECEIVED
  - `order_date`: When PO is placed
  - `requested_delivery_date`: Expected arrival

### Decision Logic
```python
def create_order_upstream(site_id, item_id, order_qty):
    sourcing_rule = get_sourcing_rule(site_id, item_id)

    if sourcing_rule.source_type == "transfer":
        # Inter-site movement → Create TransferOrder
        create_transfer_order(
            source_site_id=sourcing_rule.source_site_id,
            destination_site_id=site_id,
            quantity=order_qty
        )
    elif sourcing_rule.source_type == "buy":
        # External procurement → Create PurchaseOrder
        create_purchase_order(
            supplier_site_id=sourcing_rule.source_site_id,
            destination_site_id=site_id,
            quantity=order_qty
        )
    elif sourcing_rule.source_type == "manufacture":
        # Production → Create ManufacturingOrder
        create_manufacturing_order(
            site_id=site_id,
            item_id=item_id,
            quantity=order_qty
        )
```

---

## 2. Supply Chain DAG Traversal

### Beer Game Supply Chain Structure

```
[Market Demand] → [Retailer] → [Wholesaler] → [Distributor] → [Factory] → [Market Supply]
      (sink)        (INVENTORY)   (INVENTORY)    (INVENTORY)   (MANUF)      (source)
```

### DAG Properties
- **Directed**: Material flows one direction (upstream supplies downstream)
- **Acyclic**: No circular dependencies
- **Multi-Level**: Multiple echelons from source to sink
- **Master Node Types**:
  - `MARKET_SUPPLY`: Infinite source (upstream boundary)
  - `MARKET_DEMAND`: Demand sink (downstream boundary)
  - `INVENTORY`: Storage/fulfillment nodes
  - `MANUFACTURER`: Transform nodes with BOM

### Order Promising Traversal (Downstream → Upstream)

**Execution Flow for Round N**:

```
ROUND N EXECUTION
├── 1. RECEIVE SHIPMENTS (Upstream → Downstream)
│   ├── Process arriving TOs (arrival_round == N)
│   ├── Process arriving POs (arrival_round == N)
│   └── Update inv_level: in_transit_qty → on_hand_qty
│
├── 2. GENERATE MARKET DEMAND (Downstream Boundary)
│   └── Create outbound_order_line at Retailer
│
├── 3. ORDER PROMISING (Downstream → Upstream Cascade)
│   ├── Level 1: Retailer promises to Market Demand
│   │   ├── Calculate ATP: on_hand - allocated - safety_stock
│   │   ├── Allocate inventory: allocated_qty += promised_qty
│   │   ├── Create TransferOrder: DRAFT status
│   │   └── Ship inventory: on_hand_qty -= promised_qty, TO status → SHIPPED
│   │
│   ├── Level 2: Wholesaler promises to Retailer
│   │   ├── Retailer's order triggers demand at Wholesaler
│   │   ├── Wholesaler calculates ATP
│   │   ├── Create TransferOrder: Wholesaler → Retailer
│   │   └── Update Wholesaler inventory
│   │
│   ├── Level 3: Distributor promises to Wholesaler
│   │   └── (same pattern)
│   │
│   └── Level 4: Factory promises to Distributor
│       └── (same pattern)
│
├── 4. AGENT DECISIONS (Upstream → Downstream Orders)
│   ├── Retailer decides order qty → places order to Wholesaler
│   ├── Wholesaler decides order qty → places order to Distributor
│   ├── Distributor decides order qty → places order to Factory
│   └── Factory decides order qty → (infinite supply, no order needed)
│
├── 5. CREATE TRANSFER ORDERS (Agent Decisions → Upstream Orders)
│   ├── Retailer's order → TO: Wholesaler → Retailer (arrival_round = N + lead_time)
│   ├── Wholesaler's order → TO: Distributor → Wholesaler
│   ├── Distributor's order → TO: Factory → Distributor
│   └── Update in_transit_qty at destination sites
│
└── 6. COST ACCRUAL
    └── Calculate holding + backlog costs for all sites
```

### Key Insight: Two Separate Traversals

1. **Order Promising (Step 3)**: Downstream → Upstream
   - Fulfills existing demand from downstream
   - Creates TOs for outbound shipments
   - Decreases `on_hand_qty`, increases `allocated_qty`

2. **Order Placement (Steps 4-5)**: Downstream → Upstream
   - Agents decide replenishment orders
   - Creates TOs for inbound future shipments
   - Increases `in_transit_qty` at destination

### Multi-Site Coordination

Each site operates independently but is coordinated through TOs:

```python
# Retailer (Round N)
retailer_demand = 8  # From market
retailer_on_hand = 12
retailer_promised = 8  # Can fulfill
# Creates TO: Retailer → Customer (8 units, arrives Round N+1)
# on_hand_qty: 12 → 4

retailer_order_qty = 10  # Agent decision
# Creates TO: Wholesaler → Retailer (10 units, arrives Round N+2)
# in_transit_qty: 0 → 10

# Wholesaler (Round N)
wholesaler_demand = 10  # From Retailer's order
wholesaler_on_hand = 12
wholesaler_promised = 10  # Can fulfill
# Creates TO: Wholesaler → Retailer (10 units, arrives Round N+2)
# on_hand_qty: 12 → 2

wholesaler_order_qty = 15  # Agent decision
# Creates TO: Distributor → Wholesaler (15 units, arrives Round N+2)
# in_transit_qty: 0 → 15
```

---

## 3. Multi-Period Progression

### Lead Time Management

**Lead Time Types**:
- **Transportation Lead Time**: Time for shipment to travel between sites
- **Processing Lead Time**: Time to process order at source site
- **Total Lead Time**: `lead_time_days` in `sourcing_rules`

**Beer Game Standard Lead Times**:
- Retailer → Customer: 0 days (instant)
- Wholesaler → Retailer: 2 weeks (14 days)
- Distributor → Wholesaler: 2 weeks (14 days)
- Factory → Distributor: 2 weeks (14 days)

### Arrival Round Calculation

```python
def calculate_arrival_round(order_round: int, lead_time_days: int) -> int:
    """
    Calculate which round a TO will arrive.

    Assumption: 1 round = 1 week = 7 days
    """
    lead_time_rounds = lead_time_days // 7
    arrival_round = order_round + lead_time_rounds
    return arrival_round

# Example
order_placed_round = 5
lead_time_days = 14  # 2 weeks
arrival_round = 5 + (14 // 7) = 5 + 2 = 7  # Arrives in Round 7
```

### In-Transit Inventory Tracking

**Three Inventory States**:
1. **On-Hand**: Physical inventory at site (`on_hand_qty`)
2. **In-Transit**: Shipments not yet arrived (`in_transit_qty`)
3. **Allocated**: Committed to orders (`allocated_qty`)

**Available-to-Promise (ATP)**:
```python
ATP = on_hand_qty - allocated_qty - safety_stock_qty
```

**Lifecycle of a Transfer Order**:

```
ROUND 5: Order Placed
├── Retailer orders 10 units from Wholesaler
├── Create TO: Wholesaler → Retailer
│   ├── status = DRAFT
│   ├── order_round = 5
│   ├── arrival_round = 7 (5 + 2)
│   └── estimated_delivery_date = date(Round 7)
├── Wholesaler inv_level.in_transit_qty += 10  # NO, this is wrong!
└── Retailer inv_level.in_transit_qty += 10    # YES, at destination

ROUND 5 (continued): Order Released
├── TO status: DRAFT → RELEASED
└── Ready for fulfillment

ROUND 5 (continued): Order Shipped
├── Wholesaler calculates ATP
├── Wholesaler.on_hand_qty -= 10
├── Wholesaler.allocated_qty += 10 (then -= 10 when shipped)
├── TO status: RELEASED → SHIPPED
├── TO.shipment_date = date(Round 5)
└── TO status: SHIPPED → IN_TRANSIT

ROUND 6: In Transit
├── TO status = IN_TRANSIT
├── Retailer.in_transit_qty = 10
└── (no changes, waiting for arrival)

ROUND 7: Arrival
├── TO.arrival_round == 7 (matches current round)
├── Receive TO:
│   ├── Retailer.in_transit_qty -= 10
│   ├── Retailer.on_hand_qty += 10
│   ├── TO status: IN_TRANSIT → RECEIVED
│   └── TO.actual_delivery_date = date(Round 7)
└── TO lifecycle complete
```

### Multi-Period Planning Horizon

**Example: 4-Round Planning Horizon**

```
State at Start of Round 5:

Site: Retailer
├── on_hand_qty: 12
├── in_transit_qty: 20 (10 arriving R6 + 10 arriving R7)
├── allocated_qty: 5
├── backorder_qty: 3
└── ATP: 12 - 5 - 0 = 7

Expected Inventory Projection:
├── Round 5 (current): 12 on_hand
├── Round 6: 12 - 8 (demand) + 10 (arrival) = 14 on_hand
├── Round 7: 14 - 8 (demand) + 10 (arrival) = 16 on_hand
├── Round 8: 16 - 8 (demand) + 0 (arrival) = 8 on_hand
└── Round 9: 8 - 8 (demand) + 15 (arrival) = 15 on_hand

In-Transit Schedule (by arrival_round):
├── Round 6: TO-G1-R3-WS-RT (10 units, from Wholesaler)
├── Round 7: TO-G1-R4-WS-RT (10 units, from Wholesaler)
└── Round 9: TO-G1-R5-WS-RT (15 units, from Wholesaler)
```

---

## 4. Transfer Order Data Model

### AWS SC TransferOrder Entity

```python
class TransferOrder(Base):
    __tablename__ = "transfer_order"

    id = Column(Integer, primary_key=True)
    to_number = Column(String(100), unique=True, nullable=False)

    # Sites
    source_site_id = Column(Integer, ForeignKey("nodes.id"))
    destination_site_id = Column(Integer, ForeignKey("nodes.id"))

    # Company/Config
    company_id = Column(Integer, ForeignKey("groups.id"))
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))

    # Status
    status = Column(String(20))  # DRAFT, RELEASED, SHIPPED, IN_TRANSIT, RECEIVED

    # Dates
    order_date = Column(Date)
    shipment_date = Column(Date)
    estimated_delivery_date = Column(Date)
    actual_delivery_date = Column(Date)

    # Beer Game Extensions (for gamification module)
    game_id = Column(Integer, ForeignKey("games.id"))
    order_round = Column(Integer)      # Round when TO was created
    arrival_round = Column(Integer)    # Round when TO arrives

    # Audit
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, onupdate=datetime.now)
```

### TransferOrderLineItem Entity

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

### Status Lifecycle

```
DRAFT
  ↓ (validate ATP, allocate inventory)
RELEASED
  ↓ (ship inventory, set shipment_date)
SHIPPED
  ↓ (set status to in-transit)
IN_TRANSIT
  ↓ (arrival_round matches current round)
RECEIVED
  ↓ (update destination on_hand_qty)
COMPLETED
```

---

## 5. Implementation Requirements

### Modified Order Promising Engine

**Current Issue**: `order_promising.py` creates `ShipmentRecord` (in-memory) instead of `TransferOrder` (database entity).

**Required Changes**:

1. **Replace ShipmentRecord with TransferOrder creation**:
```python
# OLD (current implementation)
shipment = ShipmentRecord(
    from_site_id=site_id,
    to_site_id=to_site_id or "customer",
    item_id=item_id,
    shipped_qty=atp_result.promised_qty,
    shipment_date=datetime.now().date(),
    arrival_date=requested_date + timedelta(days=lead_time_days),
    order_id=order_id,
    shipment_id=f"SHIP-{order_id}-{datetime.now().timestamp()}"
)

# NEW (required implementation)
transfer_order = TransferOrder(
    to_number=f"TO-G{game_id}-R{round_number}-{site_id}-{timestamp}",
    source_site_id=site_id,
    destination_site_id=to_site_id,
    order_date=datetime.now().date(),
    shipment_date=datetime.now().date(),
    estimated_delivery_date=requested_date + timedelta(days=lead_time_days),
    status="SHIPPED",  # Immediately shipped in Beer Game
    game_id=game_id,
    order_round=round_number,
    arrival_round=round_number + (lead_time_days // 7)
)
self.db.add(transfer_order)

# Create line item
to_line = TransferOrderLineItem(
    to_id=transfer_order.id,
    line_number=1,
    product_id=item_id,
    ordered_quantity=atp_result.promised_qty,
    shipped_quantity=atp_result.promised_qty,
    requested_delivery_date=requested_date + timedelta(days=lead_time_days)
)
self.db.add(to_line)
self.db.commit()
```

2. **Update arrival processing to use TransferOrder**:
```python
def process_arriving_transfers(game_id: int, round_number: int):
    """
    Process all TOs arriving in current round.
    """
    arriving_tos = self.db.query(TransferOrder).filter(
        and_(
            TransferOrder.game_id == game_id,
            TransferOrder.arrival_round == round_number,
            TransferOrder.status == "IN_TRANSIT"
        )
    ).all()

    for to in arriving_tos:
        self.receive_transfer_order(to)

    return arriving_tos

def receive_transfer_order(to: TransferOrder):
    """
    Receive transfer order at destination site.
    """
    # Get line items
    to_lines = self.db.query(TransferOrderLineItem).filter(
        TransferOrderLineItem.to_id == to.id
    ).all()

    for line in to_lines:
        # Update inv_level at destination
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == to.destination_site_id,
                InvLevel.item_id == line.product_id
            )
        ).first()

        if inv_level:
            # Move from in_transit to on_hand
            inv_level.in_transit_qty -= line.shipped_quantity
            inv_level.on_hand_qty += line.shipped_quantity

            # Ensure no negative values
            inv_level.in_transit_qty = max(0.0, inv_level.in_transit_qty)

    # Update TO status
    to.status = "RECEIVED"
    to.actual_delivery_date = datetime.now().date()

    self.db.commit()
```

3. **Integrate with BeerGameExecutor**:
```python
# In beer_game_executor.py:execute_round()

# STEP 1: Receive shipments
arriving_pos = self.po_creator.process_arriving_orders(game_id, round_number)
arriving_tos = self.order_promising.process_arriving_transfers(game_id, round_number)

# STEP 3: Order promising (now creates TOs)
atp_results = self.order_promising.process_round_demand(
    game_id, round_number
)  # This now creates TransferOrder entities
```

---

## 6. Complete Round Execution Flow with Transfer Orders

### Round N Detailed Execution

```python
def execute_round_n(game_id, round_number, agent_decisions, market_demand):
    """
    Complete round execution with Transfer Orders.
    """

    # ====================================================================
    # STEP 1: RECEIVE SHIPMENTS (Lead Time Completion)
    # ====================================================================
    # 1a. Process arriving Purchase Orders
    arriving_pos = process_arriving_purchase_orders(game_id, round_number)
    # Example: Factory ordered raw materials in Round N-2, now arriving
    # - PO.arrival_round == N
    # - PO.status: APPROVED → RECEIVED
    # - destination_site.in_transit_qty -= qty
    # - destination_site.on_hand_qty += qty

    # 1b. Process arriving Transfer Orders
    arriving_tos = process_arriving_transfer_orders(game_id, round_number)
    # Example: Wholesaler shipped to Retailer in Round N-2, now arriving
    # - TO.arrival_round == N
    # - TO.status: IN_TRANSIT → RECEIVED
    # - destination_site.in_transit_qty -= qty
    # - destination_site.on_hand_qty += qty

    # ====================================================================
    # STEP 2: GENERATE MARKET DEMAND (Downstream Boundary)
    # ====================================================================
    market_order = create_outbound_order_line(
        order_id=f"MARKET-G{game_id}-R{round_number}",
        site_id="retailer_001",
        product_id="cases",
        quantity=market_demand,
        requested_delivery_date=get_round_date(round_number)
    )

    # ====================================================================
    # STEP 3: ORDER PROMISING (Downstream → Upstream Fulfillment)
    # ====================================================================
    # Process all outbound_order_lines for this round
    orders = get_outbound_orders(game_id, round_number)

    for order in orders:
        # 3a. Calculate ATP at source site
        atp_result = calculate_atp(
            site_id=order.site_id,
            item_id=order.product_id,
            requested_qty=order.ordered_quantity
        )
        # ATP = on_hand_qty - allocated_qty - safety_stock_qty

        # 3b. Allocate inventory
        if atp_result.can_fulfill:
            inv_level.allocated_qty += atp_result.promised_qty

        # 3c. Create Transfer Order (NEW!)
        to = create_transfer_order(
            source_site_id=order.site_id,
            destination_site_id=get_downstream_site(order.order_id),
            product_id=order.product_id,
            quantity=atp_result.promised_qty,
            game_id=game_id,
            order_round=round_number,
            arrival_round=round_number + calculate_lead_time_rounds(...)
        )
        # TO.status = DRAFT

        # 3d. Ship inventory (fulfill order)
        inv_level.on_hand_qty -= atp_result.promised_qty
        inv_level.allocated_qty -= atp_result.promised_qty
        to.status = "SHIPPED"
        to.shipment_date = get_round_date(round_number)
        to.status = "IN_TRANSIT"

        # 3e. Update in-transit at destination
        destination_inv_level.in_transit_qty += atp_result.promised_qty

        # 3f. Handle backorders
        if atp_result.backorder_qty > 0:
            inv_level.backorder_qty += atp_result.backorder_qty

    # ====================================================================
    # STEP 4: AGENT DECISIONS (Compute Order Quantities)
    # ====================================================================
    # Agents observe state and decide order quantities
    # agent_decisions = {
    #     "retailer_001": 12.0,
    #     "wholesaler_001": 15.0,
    #     "distributor_001": 18.0
    # }
    # (provided as input parameter)

    # ====================================================================
    # STEP 5: CREATE REPLENISHMENT ORDERS (Upstream Orders)
    # ====================================================================
    for site_id, order_qty in agent_decisions.items():
        if order_qty <= 0:
            continue

        # Get sourcing rule
        sourcing_rule = get_sourcing_rule(site_id, "cases")

        if sourcing_rule.source_type == "transfer":
            # Inter-site transfer → Create TO
            to = create_transfer_order(
                source_site_id=sourcing_rule.source_site_id,
                destination_site_id=site_id,
                product_id="cases",
                quantity=order_qty,
                game_id=game_id,
                order_round=round_number,
                arrival_round=round_number + (sourcing_rule.lead_time_days // 7),
                status="RELEASED"  # Released, awaiting fulfillment
            )

            # Update in-transit at destination
            destination_inv_level.in_transit_qty += order_qty

        elif sourcing_rule.source_type == "buy":
            # External procurement → Create PO
            po = create_purchase_order(
                supplier_site_id=sourcing_rule.source_site_id,
                destination_site_id=site_id,
                product_id="cases",
                quantity=order_qty,
                game_id=game_id,
                order_round=round_number,
                arrival_round=round_number + (sourcing_rule.lead_time_days // 7)
            )

            # Update in-transit at destination
            destination_inv_level.in_transit_qty += order_qty

    # ====================================================================
    # STEP 6: COST ACCRUAL
    # ====================================================================
    costs = calculate_round_costs(game_id)
    # holding_cost = on_hand_qty * holding_cost_per_unit
    # backlog_cost = backorder_qty * backlog_cost_per_unit

    # ====================================================================
    # STEP 7: STATE SNAPSHOT
    # ====================================================================
    snapshot = create_state_snapshot(game_id, round_number)

    return {
        "game_id": game_id,
        "round_number": round_number,
        "shipments_received": {
            "purchase_orders": len(arriving_pos),
            "transfer_orders": len(arriving_tos)
        },
        "market_demand": market_demand,
        "agent_decisions": agent_decisions,
        "costs": costs,
        "state": snapshot
    }
```

---

## 7. Example Walkthrough: 3-Round Simulation

### Configuration
- **Sites**: Retailer, Wholesaler, Factory
- **Lead Times**:
  - Wholesaler → Retailer: 2 weeks (14 days, 2 rounds)
  - Factory → Wholesaler: 2 weeks (14 days, 2 rounds)
- **Initial Inventory**: 12 units at each site

### Round 1

**State Before Round 1**:
```
Retailer:     on_hand=12, in_transit=0, backorder=0
Wholesaler:   on_hand=12, in_transit=0, backorder=0
Factory:      on_hand=12, in_transit=0, backorder=0
```

**Execution**:
1. Receive shipments: None
2. Market demand: 8 units
3. Order promising:
   - Retailer promises 8 units to Market
   - Creates TO-R1-RT-CUST: Retailer → Customer (8 units, arrival R1)
   - Retailer: on_hand=12→4
4. Agent decisions:
   - Retailer orders 10 units
   - Wholesaler orders 12 units
5. Create TOs:
   - TO-R1-WS-RT: Wholesaler → Retailer (10 units, arrival R3)
   - TO-R1-FC-WS: Factory → Wholesaler (12 units, arrival R3)
6. Costs: Retailer holding=2.0, others holding=6.0 each

**State After Round 1**:
```
Retailer:     on_hand=4, in_transit=10 (arriving R3), backorder=0
Wholesaler:   on_hand=12, in_transit=12 (arriving R3), backorder=0
Factory:      on_hand=12, in_transit=0, backorder=0
```

### Round 2

**Execution**:
1. Receive shipments: None (TOs arrive R3)
2. Market demand: 8 units
3. Order promising:
   - Retailer promises 4 units to Market (only has 4 on-hand!)
   - Backorder: 4 units
   - Creates TO-R2-RT-CUST: Retailer → Customer (4 units, arrival R2)
   - Retailer: on_hand=4→0, backorder=4
4. Agent decisions:
   - Retailer orders 15 units (sees low inventory!)
   - Wholesaler orders 12 units
5. Create TOs:
   - TO-R2-WS-RT: Wholesaler → Retailer (15 units, arrival R4)
   - TO-R2-FC-WS: Factory → Wholesaler (12 units, arrival R4)
6. Costs: Retailer backlog=4.0, Wholesaler holding=6.0, Factory holding=6.0

**State After Round 2**:
```
Retailer:     on_hand=0, in_transit=25 (10 arriving R3, 15 arriving R4), backorder=4
Wholesaler:   on_hand=12, in_transit=24 (12 arriving R3, 12 arriving R4), backorder=0
Factory:      on_hand=12, in_transit=0, backorder=0
```

### Round 3

**Execution**:
1. Receive shipments:
   - TO-R1-WS-RT arrives: Retailer receives 10 units
   - TO-R1-FC-WS arrives: Wholesaler receives 12 units
   - Retailer: in_transit=25→15, on_hand=0→10
   - Wholesaler: in_transit=24→12, on_hand=12→24
2. Market demand: 8 units
3. Order promising:
   - Retailer promises 8 units to Market
   - Fulfills 4 units of backorder from Round 2
   - Retailer: on_hand=10→6 (8 current + 4 backorder - 10 fulfilled), backorder=4→0
   - Actually: on_hand=10, fulfill 8 to market + 4 backorder = 12 needed, only have 10
   - Corrected: fulfill 8 to market, fulfill 2 of backorder
   - on_hand=10→0, backorder=4→2
4. Agent decisions:
   - Retailer orders 20 units (still recovering)
   - Wholesaler orders 15 units
5. Create TOs:
   - TO-R3-WS-RT: Wholesaler → Retailer (20 units, arrival R5)
   - TO-R3-FC-WS: Factory → Wholesaler (15 units, arrival R5)

**State After Round 3**:
```
Retailer:     on_hand=0, in_transit=35 (15 arriving R4, 20 arriving R5), backorder=2
Wholesaler:   on_hand=4, in_transit=27 (12 arriving R4, 15 arriving R5), backorder=0
Factory:      on_hand=12, in_transit=0, backorder=0
```

---

## 8. Summary

### Key Principles

1. **Transfer Orders = AWS SC Compliance**: All inter-site movements must be tracked as TransferOrder entities in the database, not in-memory objects.

2. **Two Separate Traversals**:
   - **Order Promising (Fulfillment)**: Downstream → Upstream, processes existing demand
   - **Order Placement (Replenishment)**: Downstream → Upstream, creates future demand

3. **Multi-Period Lead Times**: TOs track `order_round` and `arrival_round` to manage in-transit inventory across multiple periods.

4. **Status Lifecycle**: TOs follow DRAFT → RELEASED → SHIPPED → IN_TRANSIT → RECEIVED status progression.

5. **In-Transit Tracking**: `in_transit_qty` updated when TO is created, decremented when TO is received.

6. **DAG Topology**: Supply chain structure determines order promising and sourcing rules.

### Implementation Checklist

- [ ] Modify `order_promising.py` to create `TransferOrder` entities instead of `ShipmentRecord`
- [ ] Implement `process_arriving_transfers()` method
- [ ] Add `receive_transfer_order()` method
- [ ] Create `TransferOrderLineItem` entities
- [ ] Update `beer_game_executor.py` to process arriving TOs
- [ ] Add TO tracking to state snapshots
- [ ] Update cost calculator to handle in-transit costs (if needed)
- [ ] Add TO status tracking to game analytics
- [ ] Test multi-round TO lifecycle (creation → in-transit → receipt)
- [ ] Validate in_transit_qty updates at both source and destination sites

---

## Next Steps

1. Implement Transfer Order creation in `order_promising.py`
2. Test with 3-round Beer Game simulation
3. Validate in-transit inventory tracking
4. Add TO analytics to game reports
5. Document TO lifecycle in user guide
