# Execution Capabilities

**Last Updated**: 2026-02-21

---

## Overview

Autonomy provides comprehensive supply chain execution capabilities following AWS Supply Chain standards. The execution engine handles order promising, fulfillment coordination, inventory management, and shipment tracking with real-time visibility.

---

## Order Promising

### Available-to-Promise (ATP)

**Purpose**: Calculate what quantity can be promised to customers considering current inventory, scheduled receipts, and existing commitments.

**ATP Formula**:
```
ATP(period) = On-Hand Inventory
            + Scheduled Receipts (arrivals in period)
            - Demand Already Promised
            - Safety Stock Reserve
```

**Implementation**:

**Files**:
- `backend/app/services/execution/order_promising.py` - ATP/CTP engine
- `backend/app/models/sc_entities.py` - OutboundOrderLine, Reservation (lines 486-535)

**Key Methods**:
```python
async def calculate_atp(
    site_id: int,
    item_id: int,
    requested_qty: float,
    requested_date: date,
    config_id: int
) -> ATPResult:
    """
    Calculate Available-to-Promise quantity.

    Returns:
        ATPResult with:
        - available_qty: How much can be promised
        - promise_date: When it can be delivered
        - source_sites: Which sites can fulfill
        - split_required: If order must be split
    """
```

**Multi-Site ATP**:
- Checks all sites with product availability
- Prioritizes by sourcing rules (priority levels)
- Calculates transportation lead time
- Returns best promise date across network

**ATP Consumption**:
```python
# When order is confirmed, reserve inventory
reservation = Reservation(
    order_id=order_id,
    product_id=item_id,
    site_id=site_id,
    reserved_quantity=promised_qty,
    reservation_date=promise_date
)
```

### Capable-to-Promise (CTP)

**Purpose**: ATP + capacity consideration for manufactured items.

**CTP Formula**:
```
CTP = ATP + Available Capacity × Production Rate
```

**Implementation**:
```python
async def calculate_ctp(
    site_id: int,
    item_id: int,
    requested_qty: float,
    requested_date: date
) -> CTPResult:
    """
    Calculate Capable-to-Promise considering production capacity.

    Checks:
    1. ATP from existing inventory
    2. Available production capacity
    3. Component availability (BOM check)
    4. Lead time for production
    """
```

---

## Transfer Orders (Inter-Site Inventory Movements)

### AWS SC Compliance

Autonomy implements **AWS Supply Chain compliant Transfer Orders** with full in-transit tracking.

**Architecture**: AWS SC Site-Based
- All supply chain locations use AWS SC `Site` entity
- Transfer Orders use Integer ForeignKeys (site.id)
- BeerGameIdMapper provides bidirectional translation (names ↔ IDs)

**Data Model**:

**Files**:
- `backend/app/models/transfer_order.py` - TransferOrder, TransferOrderLine entities
- `backend/app/services/sc_execution/transfer_order_service.py` - Transfer order management
- `backend/app/services/beer_game_execution_adapter.py` - Beer Game adapter

**TransferOrder Entity** (AWS SC compliant):
```python
class TransferOrder(Base):
    __tablename__ = "transfer_order"

    id: int  # Primary key
    transfer_order_number: str  # Human-readable ID

    # AWS SC Site ForeignKeys (Integer)
    origin_site_id: int  # ForeignKey to site.id
    destination_site_id: int  # ForeignKey to site.id

    config_id: int  # Supply chain configuration

    # Status tracking
    status: str  # draft, released, in_transit, received, cancelled

    # Dates
    order_date: date
    ship_date: Optional[date]
    expected_arrival_date: date
    actual_arrival_date: Optional[date]

    # Metadata
    created_at: datetime
    updated_at: datetime
    created_by: str

    # Relationships
    lines: List[TransferOrderLine]  # Line items
```

**TransferOrderLine Entity**:
```python
class TransferOrderLine(Base):
    __tablename__ = "transfer_order_line"

    id: int
    transfer_order_id: int  # ForeignKey to transfer_order.id

    # AWS SC Product ForeignKey (Integer)
    product_id: int  # ForeignKey to items.id

    # Quantities
    ordered_quantity: float
    shipped_quantity: float
    received_quantity: float

    # Status
    line_status: str  # open, shipped, received, cancelled
```

### Transfer Order Lifecycle

**1. Creation** (Status: draft):
```python
# Via Beer Game adapter
transfer_order = await create_transfer_order_from_beer_game(
    origin_name="Wholesaler",  # String name
    destination_name="Retailer",  # String name
    item_name="Beer Case",  # String name
    quantity=100,
    config_id=1,
    expected_arrival_date=date.today() + timedelta(days=7)
)
# Adapter translates names → Integer IDs using BeerGameIdMapper
```

**2. Release** (Status: released):
```python
# Planner approves transfer order
await release_transfer_order(transfer_order_id)
# Status: draft → released
```

**3. Ship** (Status: in_transit):
```python
# Warehouse ships order
await ship_transfer_order(
    transfer_order_id,
    ship_date=date.today(),
    shipped_quantities={line.id: line.ordered_quantity}
)
# Status: released → in_transit
# Inventory decreases at origin site
# In-transit inventory created
```

**4. Receive** (Status: received):
```python
# Destination site receives shipment
await receive_transfer_order(
    transfer_order_id,
    receive_date=date.today(),
    received_quantities={line.id: 95}  # May differ from shipped
)
# Status: in_transit → received
# In-transit inventory cleared
# Inventory increases at destination site
```

### In-Transit Tracking

**In-Transit Inventory**:
```python
# During transit, inventory is neither at origin nor destination
in_transit_qty = await get_in_transit_inventory(
    destination_site_id=retailer_id,
    product_id=beer_case_id
)

# Used in ATP calculations
atp = on_hand + in_transit + scheduled_receipts - reservations
```

**Pipeline Visibility**:
```python
# Get all shipments en route to a site
pipeline = await get_inbound_pipeline(
    site_id=retailer_id,
    product_id=beer_case_id
)
# Returns list of TransferOrders with expected arrival dates
```

### Beer Game Integration

**How Beer Game Uses Transfer Orders**:

```python
# Round execution in Beer Game
async def execute_round(game_id: int, round_number: int):
    # 1. Process incoming shipments (receive transfer orders)
    for node in game.nodes:
        shipments = await get_arriving_shipments(
            destination_site_id=node.id,
            arrival_date=current_date
        )
        for shipment in shipments:
            await receive_transfer_order(shipment.id)
            node.inventory += shipment.quantity

    # 2. Fulfill demand (create outbound orders)
    for node in game.nodes:
        await fulfill_demand(node)

    # 3. Agent decides order quantity
    for node in game.nodes:
        order_qty = agent.compute_order(node)

    # 4. Place order upstream (create transfer order)
        if order_qty > 0:
            await create_transfer_order_from_beer_game(
                origin_name=node.upstream_node_name,
                destination_name=node.name,
                item_name=node.item_name,
                quantity=order_qty,
                expected_arrival_date=current_date + timedelta(weeks=node.lead_time)
            )
```

**This validates that Transfer Orders work in production.**

---

## Purchase Orders (Vendor Order Management)

### Capabilities

**Purpose**: Manage procurement from external suppliers with lead time tracking and vendor performance monitoring.

**Data Model**:

**Files**:
- `backend/app/models/purchase_order.py` - PurchaseOrder, PurchaseOrderLine entities
- `backend/app/services/sc_execution/purchase_order_service.py` - PO management

**PurchaseOrder Entity** (AWS SC compliant):
```python
class PurchaseOrder(Base):
    __tablename__ = "purchase_order"

    id: int
    po_number: str  # Human-readable PO number

    # AWS SC ForeignKeys
    vendor_id: int  # ForeignKey to supplier.id
    destination_site_id: int  # ForeignKey to site.id (receiving site)

    # Status
    status: str  # draft, submitted, acknowledged, shipped, received, cancelled

    # Dates
    order_date: date
    requested_delivery_date: date
    confirmed_delivery_date: Optional[date]
    actual_delivery_date: Optional[date]

    # Financials
    currency: str
    total_amount: float

    # Terms
    payment_terms: str
    incoterms: str

    # Relationships
    lines: List[PurchaseOrderLine]
```

### Purchase Order Lifecycle

**1. Creation** (Triggered by Supply Plan):
```python
# Net requirements calculator generates PO requests
po = await create_purchase_order(
    vendor_id=supplier.id,
    destination_site_id=factory.id,
    requested_delivery_date=need_date,
    lines=[
        PurchaseOrderLine(
            product_id=component.id,
            ordered_quantity=net_requirement,
            unit_price=vendor_product.unit_cost
        )
    ]
)
```

**2. Submission to Vendor**:
```python
await submit_purchase_order(po_id)
# Status: draft → submitted
# Send to vendor via EDI/API integration
```

**3. Vendor Acknowledgment**:
```python
await acknowledge_purchase_order(
    po_id,
    confirmed_delivery_date=date.today() + timedelta(days=14),
    confirmed_quantities={line.id: line.ordered_quantity}
)
# Status: submitted → acknowledged
```

**4. Receipt**:
```python
await receive_purchase_order(
    po_id,
    receive_date=date.today(),
    received_quantities={line.id: 950},  # May differ from ordered (yield loss)
    quality_inspection_passed=True
)
# Status: acknowledged → received
# Inventory increases at destination site
```

### Vendor Performance Tracking

```python
# Calculate vendor metrics
metrics = await calculate_vendor_metrics(vendor_id, period_start, period_end)
# Returns:
# - on_time_delivery_rate: % of POs delivered on time
# - fill_rate: % of ordered quantity delivered
# - quality_rate: % passing inspection
# - average_lead_time: Actual vs promised lead time
```

---

## Manufacturing Orders (Planned)

### Capabilities (In Development)

**Purpose**: Execute production plans from MPS/MRP with shop floor tracking.

**Data Model** (Planned):
```python
class ManufacturingOrder(Base):
    __tablename__ = "manufacturing_order"

    id: int
    mo_number: str

    # AWS SC ForeignKeys
    product_id: int  # ForeignKey to items.id (finished good)
    site_id: int  # ForeignKey to site.id (production site)
    bom_id: int  # ForeignKey to product_bom.id

    # Quantities
    planned_quantity: float
    completed_quantity: float
    scrapped_quantity: float

    # Status
    status: str  # planned, released, in_progress, completed, cancelled

    # Dates
    planned_start_date: date
    planned_completion_date: date
    actual_start_date: Optional[date]
    actual_completion_date: Optional[date]
```

**Planned Features**:
- BOM component consumption tracking
- Yield management (planned vs actual output)
- Work-in-process (WIP) inventory
- Shop floor control integration
- Production reporting

---

## Inventory Management

### Real-Time Inventory Tracking

**Data Model**:

**Files**:
- `backend/app/models/sc_entities.py` - InvLevel entity (lines 536-568)
- `backend/app/services/sc_execution/inventory_service.py` - Inventory operations

**InvLevel Entity** (AWS SC compliant):
```python
class InvLevel(Base):
    __tablename__ = "inv_level"

    id: int

    # AWS SC ForeignKeys
    product_id: int  # ForeignKey to items.id
    site_id: int  # ForeignKey to site.id

    config_id: int

    # Quantities
    on_hand_quantity: float  # Physical inventory
    available_quantity: float  # On-hand - reservations
    reserved_quantity: float  # Committed to orders
    in_transit_quantity: float  # Incoming shipments

    # Metadata
    last_updated: datetime
    location_id: Optional[str]  # Warehouse location
    lot_id: Optional[str]  # Batch/lot tracking
```

### Inventory Operations

**1. Inventory Adjustment**:
```python
await adjust_inventory(
    site_id=warehouse.id,
    product_id=item.id,
    adjustment_qty=100,  # Positive = increase, negative = decrease
    reason="cycle_count_correction",
    location_id="A-15-B"
)
```

**2. Reservation (ATP Consumption)**:
```python
await reserve_inventory(
    site_id=warehouse.id,
    product_id=item.id,
    quantity=50,
    order_id=order.id,
    expiration_date=date.today() + timedelta(days=7)
)
# available_quantity decreases, reserved_quantity increases
```

**3. Release Reservation**:
```python
await release_reservation(reservation_id)
# available_quantity increases, reserved_quantity decreases
```

**4. Inventory Query**:
```python
# Get current levels
levels = await get_inventory_levels(
    site_id=warehouse.id,
    product_ids=[item1.id, item2.id]
)

# Get inventory projection
projection = await project_inventory(
    site_id=warehouse.id,
    product_id=item.id,
    horizon_weeks=12
)
# Returns week-by-week on-hand projection considering:
# - Current inventory
# - Scheduled receipts (PO, TO, MO)
# - Planned demand
```

### Lot Tracking and FEFO/FIFO

**Lot/Batch Tracking**:
```python
class InventoryLot(Base):
    __tablename__ = "inventory_lot"

    id: int
    product_id: int
    site_id: int
    lot_number: str

    # Traceability
    received_date: date
    expiration_date: Optional[date]
    vendor_lot_number: Optional[str]

    # Quantities
    quantity: float

    # Quality
    quality_status: str  # approved, quarantine, rejected
```

**FEFO (First-Expired-First-Out)**:
```python
# Allocate inventory prioritizing soonest expiration
allocation = await allocate_inventory_fefo(
    site_id=warehouse.id,
    product_id=item.id,
    requested_qty=100
)
# Returns list of lots to pick from, oldest expiration first
```

**FIFO (First-In-First-Out)**:
```python
# Allocate inventory prioritizing oldest receipt
allocation = await allocate_inventory_fifo(
    site_id=warehouse.id,
    product_id=item.id,
    requested_qty=100
)
# Returns list of lots to pick from, oldest received_date first
```

---

## Shipment Tracking

### Capabilities

**Purpose**: Track physical movement of goods with carrier integration.

**Data Model** (Planned):
```python
class Shipment(Base):
    __tablename__ = "shipment"

    id: int
    shipment_number: str

    # Links to orders
    transfer_order_id: Optional[int]
    purchase_order_id: Optional[int]

    # Carrier info
    carrier_id: int
    tracking_number: str
    service_level: str  # ground, express, freight

    # Status
    status: str  # picked, packed, shipped, in_transit, delivered, exception

    # Dates
    pickup_date: date
    expected_delivery_date: date
    actual_delivery_date: Optional[date]

    # Tracking events
    events: List[ShipmentEvent]
```

**Tracking Events**:
```python
class ShipmentEvent(Base):
    __tablename__ = "shipment_event"

    id: int
    shipment_id: int

    event_type: str  # picked_up, in_transit, out_for_delivery, delivered, exception
    event_time: datetime
    location: str
    notes: Optional[str]
```

---

## Outbound Order Management

### Capabilities

**Purpose**: Manage customer orders from promise through fulfillment.

**Data Model**:

**Files**:
- `backend/app/models/sc_entities.py` - OutboundOrderLine entity (lines 486-518)

**OutboundOrderLine Entity** (AWS SC compliant):
```python
class OutboundOrderLine(Base):
    __tablename__ = "outbound_order_line"

    id: int
    order_number: str
    line_number: int

    # AWS SC ForeignKeys
    product_id: int  # ForeignKey to items.id
    site_id: int  # ForeignKey to site.id (fulfillment site)
    customer_id: int  # ForeignKey to trading_partner.id

    # Quantities
    ordered_quantity: float
    promised_quantity: float
    shipped_quantity: float

    # Dates
    order_date: date
    requested_delivery_date: date
    promised_delivery_date: Optional[date]
    actual_delivery_date: Optional[date]

    # Status
    line_status: str  # open, promised, released, picked, shipped, delivered, cancelled

    # Pricing
    unit_price: float
    total_amount: float
```

### Order-to-Cash Flow

**1. Order Entry**:
```python
order_line = await create_outbound_order_line(
    product_id=item.id,
    customer_id=customer.id,
    ordered_quantity=100,
    requested_delivery_date=date.today() + timedelta(days=5)
)
# Status: open
```

**2. ATP Check & Promise**:
```python
atp_result = await calculate_atp(
    site_id=warehouse.id,
    item_id=item.id,
    requested_qty=order_line.ordered_quantity,
    requested_date=order_line.requested_delivery_date
)

if atp_result.available_qty >= order_line.ordered_quantity:
    await promise_order_line(
        order_line.id,
        promised_quantity=order_line.ordered_quantity,
        promised_date=atp_result.promise_date
    )
    # Status: open → promised
    # Creates reservation
```

**3. Release to Warehouse**:
```python
await release_order_line(order_line.id)
# Status: promised → released
# Triggers pick wave creation
```

**4. Pick & Ship**:
```python
await pick_order_line(order_line.id, picked_quantity=100)
# Status: released → picked

await ship_order_line(order_line.id, shipped_quantity=100, tracking_number="ABC123")
# Status: picked → shipped
# Inventory decreases
# Shipment created
```

**5. Delivery Confirmation**:
```python
await deliver_order_line(order_line.id, actual_delivery_date=date.today())
# Status: shipped → delivered
```

---

## Beer Game Integration

### How Beer Game Uses Execution Capabilities

**Round Execution Flow**:
```python
async def execute_beer_game_round(game_id: int):
    """
    Beer Game round uses same AWS SC execution services as production.
    """

    # 1. Receive incoming shipments (Transfer Order receipts)
    for node in game.nodes:
        arriving_shipments = await get_arriving_transfer_orders(
            destination_site_id=node.id,
            arrival_date=current_date
        )
        for shipment in arriving_shipments:
            # Use Transfer Order service
            await receive_transfer_order(shipment.id)

            # Update game state
            node.inventory += shipment.quantity

    # 2. Fulfill customer demand (Outbound Order fulfillment)
    for node in game.nodes:
        demand = await get_demand_for_node(node.id, current_date)

        # Use ATP to check availability
        atp = await calculate_atp(
            site_id=node.id,
            item_id=node.item_id,
            requested_qty=demand.quantity,
            requested_date=current_date
        )

        # Fulfill what's available
        fulfilled_qty = min(demand.quantity, atp.available_qty)
        if fulfilled_qty > 0:
            await create_and_fulfill_outbound_order(
                site_id=node.id,
                product_id=node.item_id,
                quantity=fulfilled_qty
            )
            node.inventory -= fulfilled_qty

        # Track backlog
        node.backlog += max(0, demand.quantity - fulfilled_qty)

    # 3. Agent decides order quantity (using Planning services)
    for node in game.nodes:
        order_qty = agent.compute_order(node)

    # 4. Place order upstream (Transfer Order creation)
        if order_qty > 0:
            # Use Transfer Order service
            await create_transfer_order_from_beer_game(
                origin_name=node.upstream_node_name,
                destination_name=node.name,
                item_name=node.item_name,
                quantity=order_qty,
                expected_arrival_date=current_date + timedelta(weeks=node.lead_time)
            )
```

**Key Insight**: The Beer Game is NOT a separate system. It uses the same AWS SC execution services (ATP, Transfer Orders, Inventory Management) that power production supply chain operations. This ensures:
- Validation of core platform capabilities
- Realistic simulation behavior
- Confidence in production readiness

---

## Performance Metrics

### Execution KPIs

**Order Fulfillment**:
- **Fill Rate**: % of ordered quantity delivered
- **OTIF (On-Time-In-Full)**: % of orders delivered on-time and complete
- **Order Cycle Time**: Average time from order to delivery
- **Perfect Order Rate**: % of orders with no errors (wrong item, wrong qty, late, damaged)

**Inventory**:
- **Inventory Turns**: COGS / Average Inventory
- **Days of Supply (DOS)**: Inventory / Daily Demand
- **Stockout Rate**: % of time item is unavailable
- **Obsolescence Rate**: % of inventory expired/obsolete

**Shipment**:
- **On-Time Shipment**: % of shipments leaving on schedule
- **Delivery Accuracy**: % of shipments arriving at promised date
- **Damage Rate**: % of shipments with damage claims
- **Freight Cost per Unit**: Total transportation cost / units shipped

**Vendor**:
- **Vendor Fill Rate**: % of PO quantity delivered
- **Vendor OTIF**: % of POs delivered on-time and in-full
- **Quality Rate**: % of receipts passing inspection
- **Lead Time Variance**: Actual vs promised lead time

### Benchmarks

**Standard Configuration** (10 sites, 100 items, 1000 daily transactions):
- ATP Calculation: <100ms
- Transfer Order Creation: <50ms
- Inventory Update: <20ms
- Outbound Order Processing: <200ms

---

## API Examples

### Create Transfer Order
```bash
POST /api/v1/transfer-orders
{
  "origin_site_id": 2,
  "destination_site_id": 5,
  "config_id": 1,
  "expected_arrival_date": "2026-02-01",
  "lines": [
    {
      "product_id": 10,
      "ordered_quantity": 500
    }
  ]
}
```

### Calculate ATP
```bash
POST /api/v1/order-promising/atp
{
  "site_id": 5,
  "item_id": 10,
  "requested_quantity": 100,
  "requested_date": "2026-01-25"
}

# Response
{
  "available_quantity": 100,
  "promise_date": "2026-01-25",
  "source_sites": [5],
  "split_required": false
}
```

### Get Inventory Levels
```bash
GET /api/v1/inventory/levels?site_id=5&product_id=10

# Response
{
  "product_id": 10,
  "site_id": 5,
  "on_hand_quantity": 250,
  "available_quantity": 150,
  "reserved_quantity": 100,
  "in_transit_quantity": 500
}
```

### Ship Transfer Order
```bash
POST /api/v1/transfer-orders/{id}/ship
{
  "ship_date": "2026-01-25",
  "shipped_quantities": {
    "1": 500
  }
}
```

---

## AI-Powered Execution (Powell TRM Agents)

The execution layer is augmented by **11 Engine-TRM pairs** that combine deterministic baselines with learned adjustments. Each TRM makes decisions in <10ms and logs all decisions for audit and continuous learning.

### Manufacturing Order Execution

**Engine**: `MOExecutionEngine` — Material availability checks (≥95%), capacity validation (≥80%), predecessor sequencing, expedite evaluation
**TRM**: `MOExecutionTRM` — Learned adjustments for customer priority, yield-based quantity buffers
**Decisions**: Release, sequence, split, expedite, defer
**Audit Table**: `powell_mo_decisions`

### Transfer Order Execution

**Engine**: `TOExecutionEngine` — Source inventory validation, timing checks, lane consolidation (groups by route, estimates savings), expedite for destination stockout risk
**TRM**: `TOExecutionTRM` — Transit variability buffers, backlog-driven release acceleration
**Decisions**: Release, consolidate, expedite, defer
**Audit Table**: `powell_to_decisions`

### Quality Disposition

**Engine**: `QualityEngine` — Rule cascade: critical defect → auto reject; low defect → auto accept; high defect → reject/rework/scrap; moderate → use-as-is or conditional accept. Includes service risk assessment based on DOS and safety stock.
**TRM**: `QualityDispositionTRM` — Vendor reject rate learning, use-as-is complaint avoidance, rework success gating
**Decisions**: Accept, reject, rework, scrap, use-as-is, return-to-vendor, conditional-accept
**Audit Table**: `powell_quality_decisions`

### Maintenance Scheduling

**Engine**: `MaintenanceEngine` — Breakdown probability estimation from overdue days, usage ratio, failure history, asset age. Emergency/corrective → expedite; high risk → expedite; deferrable → defer to production gap; outsource if cost-favorable.
**TRM**: `MaintenanceSchedulingTRM` — Historical deferral outcome learning, cost overrun prediction
**Decisions**: Schedule, defer, expedite, outsource
**Audit Table**: `powell_maintenance_decisions`

### Subcontracting

**Engine**: `SubcontractingEngine` — Decision cascade: no vendor → internal; high IP → internal; low quality → internal; capacity-driven → split; cost-driven → external; lead-time-driven → external.
**TRM**: `SubcontractingTRM` — Vendor quality/reliability tracking, critical product quality gating
**Decisions**: Keep internal, route external, split
**Audit Table**: `powell_subcontracting_decisions`

### Forecast Adjustment

**Engine**: `ForecastAdjustmentEngine` — Multi-source signal processing (email, voice, market intelligence, news, customer feedback, weather, etc.) with source reliability scoring, time decay, confidence gating, and auto-apply vs human-review thresholds.
**TRM**: `ForecastAdjustmentTRM` — Learned source reliability, poor-source dampening, volatility gating, trend alignment
**Decisions**: Adjust up, adjust down, no change (with magnitude and confidence)
**Audit Table**: `powell_forecast_adjustment_decisions`

### Signal Input Channels

Two mechanisms feed external signals into the execution layer:

**Azirella (Natural Language Directives)**: Users type directives in the TopNavbar prompt bar (e.g., "Increase SW region revenue by 10% next quarter"). LLM parsing extracts structured fields, gap detection asks clarifying questions, and the completed directive routes to the appropriate Powell layer based on user role. Implementation: `directive_service.py`, `user_directives.py`, `TopNavbar.jsx`. See [TALK_TO_ME.md](TALK_TO_ME.md).

**Email Signal Intelligence (GDPR-Safe Email Ingestion)**: IMAP/Gmail inbox monitoring extracts supply chain signals from customer/supplier emails. PII stripped before persistence (GDPR-safe by design). LLM classifies into 12 signal types and auto-routes to appropriate TRMs. Demand signals → ForecastAdjustmentTRM (`source="email"`), supply disruptions → POCreationTRM, quality issues → QualityDispositionTRM. Implementation: `email_signal_service.py`, `email_pii_scrubber.py`, `email_connector.py`, `EmailSignalsDashboard.jsx`. See [EMAIL_SIGNAL_INTELLIGENCE.md](EMAIL_SIGNAL_INTELLIGENCE.md).

### DB Models for Execution Extensions

| Model | Table | Purpose |
|-------|-------|---------|
| `QualityOrder` | `quality_order` | Quality inspection and disposition tracking |
| `QualityOrderLineItem` | `quality_order_line_item` | Per-characteristic inspection results |
| `SubcontractingOrder` | `subcontracting_order` | External manufacturing lifecycle |
| `SubcontractingOrderLineItem` | `subcontracting_order_line_item` | Component materials sent to subcontractor |

---

## Further Reading

- [PLANNING_CAPABILITIES.md](PLANNING_CAPABILITIES.md) - Demand, supply, MPS, MRP, inventory optimization
- [STOCHASTIC_PLANNING.md](STOCHASTIC_PLANNING.md) - Probabilistic planning framework
- [BEER_GAME_GUIDE.md](BEER_GAME_GUIDE.md) - How Beer Game uses execution services
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) - API usage, data import/export
- [TRM_AGENTS_EXPLAINED.md](TRM_AGENTS_EXPLAINED.md) - Detailed TRM architecture and training
- [POWELL_APPROACH.md](POWELL_APPROACH.md) - Full Powell SDAM framework documentation
