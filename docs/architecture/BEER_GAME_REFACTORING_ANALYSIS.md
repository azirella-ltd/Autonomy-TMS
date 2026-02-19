# Beer Game Refactoring: Using AWS SC Execution Capabilities

**Document Version**: 1.0
**Date**: January 24, 2026
**Status**: Analysis & Design
**Author**: AI Architecture Team

---

## Executive Summary

This document proposes refactoring The Beer Game implementation to use the platform's native AWS Supply Chain execution capabilities (ATP/CTP, order management, fulfillment) instead of the simplified node-based simulation logic. This change will:

1. **Align with AWS SC Standards**: Use proper sales orders, purchase orders, transfer orders, and ATP/CTP
2. **Leverage Existing Capabilities**: Reuse battle-tested execution code across gamification and production planning
3. **Demonstrate Real-World Execution**: The Beer Game becomes a realistic demonstration of supply chain execution
4. **Support Future Features**: Enable capabilities like backlog management, partial fulfillment, priority allocation

---

## Table of Contents

1. [Current Implementation Analysis](#1-current-implementation-analysis)
2. [Existing AWS SC Execution Capabilities](#2-existing-aws-sc-execution-capabilities)
3. [Backlog Handling Analysis](#3-backlog-handling-analysis)
4. [Proposed Refactored Architecture](#4-proposed-refactored-architecture)
5. [Implementation Plan](#5-implementation-plan)
6. [Migration Strategy](#6-migration-strategy)

---

## 1. Current Implementation Analysis

### 1.1 Current Beer Game Architecture

**File**: [backend/app/services/engine.py](../../backend/app/services/engine.py)

**Key Components**:

1. **Node Class**: Represents a supply chain role (Retailer, Wholesaler, Distributor, Manufacturer)
   - Tracks: inventory, backlog, pipeline_shipments, order_pipe
   - Methods: receive_shipment(), decide_order(), accrue_costs()

2. **BeerLine Class**: Orchestrates the 4-node supply chain
   - Material flows downstream: Manufacturer → Distributor → Wholesaler → Retailer
   - Orders flow upstream: Retailer → Wholesaler → Distributor → Manufacturer

3. **Order Flow** (Simplified):
   ```python
   # Current implementation (engine.py)
   def tick(self):
       # 1. Receive shipments from upstream
       for node in self.nodes:
           node.receive_shipment()  # Pipeline advances

       # 2. Fulfill demand (downstream orders)
       for node in self.nodes:
           shipment_qty = fulfill_demand(node.inventory, node.backlog)
           downstream_node.schedule_inbound_shipment(shipment_qty)

       # 3. Agents decide orders
       for node in self.nodes:
           order_qty = node.decide_order()  # Agent policy
           node.schedule_order(order_qty)  # Add to order_pipe

       # 4. Accrue costs
       for node in self.nodes:
           node.accrue_costs()
   ```

**Problems with Current Approach**:

❌ **Not using ATP/CTP**: Fulfillment logic is hardcoded, doesn't respect real ATP calculations
❌ **No proper order objects**: Orders are just integers in pipelines, not database entities
❌ **Missing order lifecycle**: No DRAFT → APPROVED → FULFILLED status tracking
❌ **Backlog is a single number**: No line-item tracking, no FIFO/LIFO, no order priority
❌ **Can't reuse for production**: Separate logic for gamification vs. planning

### 1.2 Market Demand and Market Supply

**Current Implementation**:

- **Market Demand**: Generates weekly demand integers (e.g., 4 units/week)
- **Market Supply**: Infinite supply with fixed lead time

**Problems**:

❌ Market Demand doesn't create actual customer orders (OutboundOrderLine)
❌ Market Supply doesn't act like a real vendor with promise dates
❌ No integration with order promising or ATP capabilities

---

## 2. Existing AWS SC Execution Capabilities

### 2.1 Order Management Models

#### A. OutboundOrderLine (Customer Orders / Sales Orders)

**File**: [backend/app/models/sc_entities.py#L696](../../backend/app/models/sc_entities.py#L696)

```python
class OutboundOrderLine(Base):
    """Customer orders (actual demand)"""
    __tablename__ = "outbound_order_line"

    id = Column(Integer, primary_key=True)
    order_id = Column(String(100), nullable=False)
    line_number = Column(Integer, nullable=False)
    product_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    site_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    ordered_quantity = Column(Double, nullable=False)
    requested_delivery_date = Column(Date, nullable=False)
    order_date = Column(Date)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
    game_id = Column(Integer, ForeignKey("games.id"))
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
```

**Usage**: Represents customer demand that needs to be promised and fulfilled.

#### B. PurchaseOrder (Replenishment from Vendors)

**File**: [backend/app/models/purchase_order.py](../../backend/app/models/purchase_order.py)

```python
class PurchaseOrder(Base):
    """Purchase order header"""
    __tablename__ = "purchase_order"

    id = Column(Integer, primary_key=True)
    po_number = Column(String(100), unique=True)

    # Vendor and sites
    vendor_id = Column(String(100))  # External vendor
    supplier_site_id = Column(Integer, ForeignKey("nodes.id"))
    destination_site_id = Column(Integer, ForeignKey("nodes.id"))

    # Status lifecycle
    status = Column(String(20), default="DRAFT")
    # DRAFT, APPROVED, SENT, ACKNOWLEDGED, RECEIVED, CANCELLED

    # Dates
    order_date = Column(Date, nullable=False)
    requested_delivery_date = Column(Date)
    promised_delivery_date = Column(Date)
    actual_delivery_date = Column(Date)

    # Financial
    total_amount = Column(Double, default=0.0)
```

**Usage**: Represents replenishment orders to vendors or upstream sites.

#### C. TransferOrder (Inter-Site Movement)

**File**: [backend/app/models/transfer_order.py](../../backend/app/models/transfer_order.py)

```python
class TransferOrder(Base):
    """Transfer order header"""
    __tablename__ = "transfer_order"

    id = Column(Integer, primary_key=True)
    to_number = Column(String(100), unique=True)

    # Sites
    source_site_id = Column(Integer, ForeignKey("nodes.id"))
    destination_site_id = Column(Integer, ForeignKey("nodes.id"))

    # Status lifecycle
    status = Column(String(20), default="DRAFT")
    # DRAFT, RELEASED, PICKED, SHIPPED, IN_TRANSIT, RECEIVED, CANCELLED

    # Dates
    order_date = Column(Date)
    shipment_date = Column(Date, nullable=False)
    estimated_delivery_date = Column(Date, nullable=False)
    actual_ship_date = Column(Date)
    actual_delivery_date = Column(Date)

    # Beer Game extensions
    game_id = Column(Integer, ForeignKey("games.id"))
    order_round = Column(Integer)  # Round when TO created
    arrival_round = Column(Integer)  # Round when TO arrives
```

**Usage**: Represents inventory movement between sites (e.g., Wholesaler → Retailer).

#### D. Shipment (Material Visibility)

**File**: [backend/app/models/sc_entities.py#L721](../../backend/app/models/sc_entities.py#L721)

```python
class Shipment(Base):
    """Shipment tracking for in-transit inventory"""
    __tablename__ = "shipment"

    id = Column(String(100), primary_key=True)
    order_id = Column(String(100), nullable=False)
    order_line_number = Column(Integer)

    # Product and quantity
    product_id = Column(String(100), nullable=False)
    quantity = Column(Double, nullable=False)

    # Sites
    from_site_id = Column(String(100), ForeignKey("site.id"))
    to_site_id = Column(String(100), ForeignKey("site.id"))

    # Status tracking
    status = Column(String(20), nullable=False)
    # planned, in_transit, delivered, delayed, exception, cancelled

    ship_date = Column(DateTime)
    expected_delivery_date = Column(DateTime)
    actual_delivery_date = Column(DateTime)
```

**Usage**: Tracks in-transit inventory (pipeline shipments).

### 2.2 ATP/CTP Capabilities

**File**: [backend/app/api/endpoints/atp_ctp_view.py](../../backend/app/api/endpoints/atp_ctp_view.py)

**ATP Calculation**:
```
ATP = On-Hand + Scheduled Receipts - Allocated - Backlog
```

**CTP Calculation**:
```
CTP = ATP + Planned Production Capacity
```

**Key Features**:
- Time-phased ATP/CTP projections (by week)
- Cumulative ATP/CTP for order promising
- Probabilistic projections (P10/P50/P90)
- Risk metrics (stockout probability, days of supply)

**API Endpoints**:
- `POST /calculate` - Calculate ATP/CTP for product-site-date
- `POST /bulk-calculate` - Bulk ATP/CTP calculation
- `GET /timeline` - Time-phased ATP/CTP view
- `GET /summary` - Aggregated ATP/CTP availability

---

## 3. Backlog Handling Analysis

### 3.1 Current Backlog Implementation

**Current Beer Game** ([engine.py](../../backend/app/services/engine.py)):

```python
class Node:
    def __init__(self, ...):
        self.backlog = int(backlog)  # Single integer

    def fulfill_demand(self, demand_qty):
        # Add to backlog if can't fulfill
        available = self.inventory
        fulfilled = min(available, demand_qty)
        self.inventory -= fulfilled
        self.backlog += (demand_qty - fulfilled)
        return fulfilled
```

**Problems**:

❌ **Single number backlog**: No tracking of which orders are backlogged
❌ **No FIFO/LIFO**: Can't ensure oldest orders fulfilled first
❌ **No order priority**: VIP orders treated same as standard
❌ **No partial fulfillment tracking**: Can't track progress on multi-line orders
❌ **No aging metrics**: Can't report "10% of backlog >2 weeks old"

### 3.2 Proposed Backlog Handling

**Use OutboundOrderLine with status tracking**:

```python
class OutboundOrderLine(Base):
    # Existing fields...

    # Add fulfillment tracking
    promised_quantity = Column(Double)  # ATP-promised quantity
    shipped_quantity = Column(Double, default=0.0)  # Fulfilled so far
    backlog_quantity = Column(Double, default=0.0)  # Unfulfilled

    # Status
    status = Column(String(20), default="DRAFT")
    # DRAFT, CONFIRMED, PARTIALLY_FULFILLED, FULFILLED, CANCELLED

    # Dates
    order_date = Column(Date)
    requested_delivery_date = Column(Date)
    promised_delivery_date = Column(Date)
    first_ship_date = Column(Date)
    last_ship_date = Column(Date)

    # Priority
    priority_code = Column(String(20), default="STANDARD")
    # VIP, HIGH, STANDARD, LOW
```

**Backlog Calculation**:

```python
def calculate_backlog(site_id: int, product_id: str) -> float:
    """Calculate total backlog for a product at a site."""
    result = db.query(
        func.sum(OutboundOrderLine.backlog_quantity)
    ).filter(
        OutboundOrderLine.site_id == site_id,
        OutboundOrderLine.product_id == product_id,
        OutboundOrderLine.status.in_(['CONFIRMED', 'PARTIALLY_FULFILLED'])
    ).scalar()

    return result or 0.0
```

**Fulfillment with FIFO**:

```python
def fulfill_backlog(site_id: int, product_id: str, available_qty: float):
    """Fulfill backlog in FIFO order (oldest first)."""
    backlogged_orders = db.query(OutboundOrderLine).filter(
        OutboundOrderLine.site_id == site_id,
        OutboundOrderLine.product_id == product_id,
        OutboundOrderLine.backlog_quantity > 0
    ).order_by(
        OutboundOrderLine.order_date.asc(),  # FIFO
        OutboundOrderLine.priority_code.desc()  # VIP first if same date
    ).all()

    remaining = available_qty
    for order in backlogged_orders:
        if remaining <= 0:
            break

        fulfill_qty = min(remaining, order.backlog_quantity)

        # Create shipment
        shipment = create_shipment(
            order_id=order.order_id,
            line_number=order.line_number,
            quantity=fulfill_qty,
            from_site_id=site_id
        )

        # Update order
        order.shipped_quantity += fulfill_qty
        order.backlog_quantity -= fulfill_qty
        remaining -= fulfill_qty

        # Update status
        if order.backlog_quantity == 0:
            order.status = "FULFILLED"
            order.last_ship_date = date.today()
        else:
            order.status = "PARTIALLY_FULFILLED"
            if order.first_ship_date is None:
                order.first_ship_date = date.today()

    db.commit()
    return available_qty - remaining  # Fulfilled quantity
```

**Benefits**:

✅ **Line-item tracking**: Know exactly which orders are backlogged
✅ **FIFO/Priority**: Oldest orders fulfilled first, VIP orders prioritized
✅ **Partial fulfillment**: Track progress on multi-line orders
✅ **Aging metrics**: Report backlog aging, SLA violations
✅ **Audit trail**: Full history of order fulfillment

---

## 4. Proposed Refactored Architecture

### 4.1 Beer Game Execution Flow (New)

**Order Flow Using AWS SC Capabilities**:

```
Week N:

1. MARKET DEMAND GENERATION
   Market Demand sites → Create OutboundOrderLine (customer orders)

2. RETAILER RECEIVES CUSTOMER ORDERS
   - Retailer ATP engine calculates available-to-promise
   - Promise orders (full or partial, with delivery dates)
   - Create TransferOrder (TO) to fulfill customer orders
   - Update OutboundOrderLine status: CONFIRMED

3. RETAILER REPLENISHMENT DECISION
   - Agent evaluates inventory position
   - Decides replenishment quantity
   - Create PurchaseOrder (PO) to Wholesaler
   - PO status: DRAFT → APPROVED

4. WHOLESALER RECEIVES RETAILER PO
   - Wholesaler treats Retailer's PO as inbound demand (like a sales order)
   - Wholesaler ATP engine calculates availability
   - Promise PO with delivery date
   - Create TransferOrder (TO) to fulfill Retailer's PO
   - Update PO status: ACKNOWLEDGED

5. WHOLESALER REPLENISHMENT DECISION
   - Agent evaluates inventory position
   - Create PurchaseOrder (PO) to Distributor

6. CASCADE CONTINUES UP THE CHAIN
   Distributor → Manufacturer (same process)
   Manufacturer → Market Supply (vendor)

7. MARKET SUPPLY PROMISES
   - Market Supply (vendor) receives Manufacturer's PO
   - Vendor promises delivery date (simulated vendor lead time)
   - Update PO status: ACKNOWLEDGED, promised_delivery_date set

8. SHIPMENTS ARRIVE (Lead Time Delay)
   - TransferOrders created in Week N arrive in Week N+2
   - Upon arrival:
     - Update TO status: IN_TRANSIT → RECEIVED
     - Update Shipment status: delivered
     - Update destination site inventory (InvLevel)
     - Update source PO status: RECEIVED

9. FULFILLMENT & BACKLOG PROCESSING
   - Each site fulfills backlog (FIFO)
   - Create new shipments for backlogged orders
   - Update OutboundOrderLine: PARTIALLY_FULFILLED or FULFILLED
```

### 4.2 Refactored Engine Architecture

**New BeerGameExecutionEngine** (replaces simplified Node-based engine):

```python
class BeerGameExecutionEngine:
    """
    Refactored Beer Game engine using AWS SC execution capabilities.
    """

    def __init__(
        self,
        config_id: int,
        game_id: int,
        db_session: AsyncSession
    ):
        self.config_id = config_id
        self.game_id = game_id
        self.db = db_session

        # Load supply chain configuration
        self.config = await self.load_config()

        # Initialize services
        self.atp_service = ATPCalculationService(db_session)
        self.order_service = OrderManagementService(db_session)
        self.fulfillment_service = FulfillmentService(db_session)

        # Identify node types from config
        self.market_demand_sites = self.get_sites_by_type("MARKET_DEMAND")
        self.retailer_sites = self.get_sites_by_type("RETAILER")
        self.wholesaler_sites = self.get_sites_by_type("WHOLESALER")
        self.distributor_sites = self.get_sites_by_type("DISTRIBUTOR")
        self.manufacturer_sites = self.get_sites_by_type("MANUFACTURER")
        self.market_supply_sites = self.get_sites_by_type("MARKET_SUPPLY")

    async def execute_round(self, round_number: int):
        """Execute a single Beer Game round using SC execution capabilities."""

        # Step 1: Receive shipments (update inventory for arrived orders)
        await self.receive_shipments(round_number)

        # Step 2: Market Demand generates customer orders
        await self.generate_customer_orders(round_number)

        # Step 3: Fulfill customer demand (Retailer)
        await self.fulfill_customer_orders(round_number)

        # Step 4: Agents decide replenishment orders
        await self.generate_replenishment_orders(round_number)

        # Step 5: Fulfill replenishment orders (upstream sites)
        await self.fulfill_replenishment_orders(round_number)

        # Step 6: Market Supply promises delivery
        await self.process_vendor_promises(round_number)

        # Step 7: Calculate costs and metrics
        await self.calculate_round_metrics(round_number)

        # Step 8: Save round state
        await self.save_round_state(round_number)

    async def receive_shipments(self, round_number: int):
        """
        Process all shipments arriving this round.
        Update inventory levels, PO status, TO status.
        """
        # Get all TransferOrders with arrival_round == round_number
        arriving_orders = await self.db.query(TransferOrder).filter(
            TransferOrder.game_id == self.game_id,
            TransferOrder.arrival_round == round_number,
            TransferOrder.status == "IN_TRANSIT"
        ).all()

        for to in arriving_orders:
            # Update inventory at destination site
            await self.update_inventory(
                site_id=to.destination_site_id,
                quantity_delta=to.total_quantity,
                reason=f"Received TO {to.to_number}"
            )

            # Update TO status
            to.status = "RECEIVED"
            to.actual_delivery_date = date.today()
            to.received_at = datetime.utcnow()

            # Update associated PO status (if any)
            if to.source_po_id:
                po = await self.db.get(PurchaseOrder, to.source_po_id)
                po.status = "RECEIVED"
                po.actual_delivery_date = date.today()

        await self.db.commit()

    async def generate_customer_orders(self, round_number: int):
        """
        Market Demand sites generate customer orders for this round.
        Creates OutboundOrderLine records.
        """
        for site in self.market_demand_sites:
            # Get demand quantity for this round (from demand plan or pattern)
            demand_qty = await self.get_demand_quantity(site.id, round_number)

            # Create customer order (OutboundOrderLine)
            order = OutboundOrderLine(
                order_id=f"CUST-{self.game_id}-{round_number}-{site.id}",
                line_number=1,
                product_id=self.get_product_id(),  # Beer product
                site_id=site.destination_site_id,  # Retailer site
                ordered_quantity=demand_qty,
                order_date=date.today(),
                requested_delivery_date=date.today() + timedelta(weeks=1),
                config_id=self.config_id,
                game_id=self.game_id,
                status="DRAFT",
                priority_code="STANDARD"
            )

            self.db.add(order)

        await self.db.commit()

    async def fulfill_customer_orders(self, round_number: int):
        """
        Retailer fulfills customer orders using ATP calculation.
        Creates TransferOrders for delivery.
        """
        for retailer_site in self.retailer_sites:
            # Get all unfulfilled customer orders for this retailer
            orders = await self.db.query(OutboundOrderLine).filter(
                OutboundOrderLine.site_id == retailer_site.id,
                OutboundOrderLine.status.in_(["DRAFT", "CONFIRMED", "PARTIALLY_FULFILLED"]),
                OutboundOrderLine.game_id == self.game_id
            ).order_by(
                OutboundOrderLine.order_date.asc(),  # FIFO
                OutboundOrderLine.priority_code.desc()  # Priority
            ).all()

            # Calculate ATP
            atp_result = await self.atp_service.calculate_atp(
                product_id=self.get_product_id(),
                site_id=retailer_site.id,
                projection_date=date.today(),
                planning_horizon_weeks=4
            )

            available_qty = atp_result.atp_qty

            # Fulfill orders in FIFO order
            for order in orders:
                unfulfilled_qty = order.ordered_quantity - order.shipped_quantity

                if available_qty <= 0:
                    # No ATP remaining, update backlog
                    order.backlog_quantity = unfulfilled_qty
                    order.status = "CONFIRMED"  # Confirmed but backlogged
                    continue

                # Fulfill (full or partial)
                fulfill_qty = min(available_qty, unfulfilled_qty)

                # Create TransferOrder to customer (Market Demand site)
                to = TransferOrder(
                    to_number=f"TO-{self.game_id}-{round_number}-{order.id}",
                    source_site_id=retailer_site.id,
                    destination_site_id=order.market_demand_site_id,  # Customer site
                    config_id=self.config_id,
                    game_id=self.game_id,
                    order_date=date.today(),
                    shipment_date=date.today(),
                    estimated_delivery_date=date.today() + timedelta(weeks=2),
                    status="IN_TRANSIT",
                    order_round=round_number,
                    arrival_round=round_number + 2  # 2-week lead time
                )

                # Add line items to TO
                to_line = TransferOrderLineItem(
                    to_id=to.id,
                    line_number=1,
                    product_id=self.get_product_id(),
                    quantity=fulfill_qty,
                    uom="CASE"
                )

                self.db.add(to)
                self.db.add(to_line)

                # Update order
                order.shipped_quantity += fulfill_qty
                order.backlog_quantity = unfulfilled_qty - fulfill_qty
                available_qty -= fulfill_qty

                # Update status
                if order.backlog_quantity == 0:
                    order.status = "FULFILLED"
                    order.promised_delivery_date = to.estimated_delivery_date
                else:
                    order.status = "PARTIALLY_FULFILLED"

                # Update retailer inventory (allocated)
                await self.update_inventory(
                    site_id=retailer_site.id,
                    quantity_delta=-fulfill_qty,
                    reason=f"Shipped to customer via TO {to.to_number}"
                )

        await self.db.commit()

    async def generate_replenishment_orders(self, round_number: int):
        """
        Each site (Retailer, Wholesaler, Distributor, Manufacturer)
        decides replenishment quantity and creates PurchaseOrder to upstream site.
        """
        # Process each echelon
        await self._generate_replenishment_for_sites(
            self.retailer_sites,
            upstream_sites=self.wholesaler_sites,
            round_number=round_number
        )

        await self._generate_replenishment_for_sites(
            self.wholesaler_sites,
            upstream_sites=self.distributor_sites,
            round_number=round_number
        )

        await self._generate_replenishment_for_sites(
            self.distributor_sites,
            upstream_sites=self.manufacturer_sites,
            round_number=round_number
        )

        await self._generate_replenishment_for_sites(
            self.manufacturer_sites,
            upstream_sites=self.market_supply_sites,
            round_number=round_number
        )

    async def _generate_replenishment_for_sites(
        self,
        sites: List[Node],
        upstream_sites: List[Node],
        round_number: int
    ):
        """Helper to generate replenishment POs for a list of sites."""
        for site in sites:
            # Get agent policy for this site
            agent_policy = await self.get_agent_policy(site.id)

            # Calculate observation for agent
            observation = await self.get_agent_observation(site.id, round_number)

            # Agent decides order quantity
            order_qty = agent_policy.order(observation)

            if order_qty <= 0:
                continue  # No order needed

            # Determine upstream site (supplier)
            upstream_site = self.get_upstream_site(site, upstream_sites)

            # Create PurchaseOrder
            po = PurchaseOrder(
                po_number=f"PO-{self.game_id}-{round_number}-{site.id}",
                vendor_id=upstream_site.vendor_id if upstream_site.is_vendor else None,
                supplier_site_id=upstream_site.id,
                destination_site_id=site.id,
                config_id=self.config_id,
                group_id=self.config.group_id,
                company_id=self.config.company_id,
                status="APPROVED",  # Auto-approve in Beer Game
                order_date=date.today(),
                requested_delivery_date=date.today() + timedelta(weeks=2),
                game_id=self.game_id,
                order_round=round_number
            )

            # Add line item
            po_line = PurchaseOrderLineItem(
                po_id=po.id,
                line_number=1,
                product_id=self.get_product_id(),
                quantity=order_qty,
                uom="CASE",
                unit_price=10.0  # Fixed for Beer Game
            )

            self.db.add(po)
            self.db.add(po_line)

        await self.db.commit()

    async def fulfill_replenishment_orders(self, round_number: int):
        """
        Upstream sites fulfill PurchaseOrders from downstream sites.
        Similar logic to fulfill_customer_orders, but fulfills POs instead.
        """
        # Process each echelon (upstream fulfills downstream POs)
        await self._fulfill_pos_for_sites(self.wholesaler_sites, round_number)
        await self._fulfill_pos_for_sites(self.distributor_sites, round_number)
        await self._fulfill_pos_for_sites(self.manufacturer_sites, round_number)

    async def _fulfill_pos_for_sites(self, sites: List[Node], round_number: int):
        """Helper to fulfill POs for a list of sites."""
        for site in sites:
            # Get all unfulfilled POs directed to this site
            pos = await self.db.query(PurchaseOrder).filter(
                PurchaseOrder.supplier_site_id == site.id,
                PurchaseOrder.status.in_(["APPROVED", "ACKNOWLEDGED"]),
                PurchaseOrder.game_id == self.game_id
            ).order_by(
                PurchaseOrder.order_date.asc()  # FIFO
            ).all()

            # Calculate ATP
            atp_result = await self.atp_service.calculate_atp(
                product_id=self.get_product_id(),
                site_id=site.id,
                projection_date=date.today(),
                planning_horizon_weeks=4
            )

            available_qty = atp_result.atp_qty

            # Fulfill POs
            for po in pos:
                po_line = await self.db.query(PurchaseOrderLineItem).filter(
                    PurchaseOrderLineItem.po_id == po.id
                ).first()

                unfulfilled_qty = po_line.quantity - po_line.shipped_quantity

                if available_qty <= 0:
                    # No ATP, PO remains acknowledged but not shipped
                    po.status = "ACKNOWLEDGED"
                    continue

                # Fulfill (full or partial)
                fulfill_qty = min(available_qty, unfulfilled_qty)

                # Create TransferOrder to destination site
                to = TransferOrder(
                    to_number=f"TO-{self.game_id}-{round_number}-{po.id}",
                    source_site_id=site.id,
                    destination_site_id=po.destination_site_id,
                    config_id=self.config_id,
                    game_id=self.game_id,
                    order_date=date.today(),
                    shipment_date=date.today(),
                    estimated_delivery_date=date.today() + timedelta(weeks=2),
                    status="IN_TRANSIT",
                    order_round=round_number,
                    arrival_round=round_number + 2,  # 2-week lead time
                    source_po_id=po.id  # Link TO to PO
                )

                # Add line item to TO
                to_line = TransferOrderLineItem(
                    to_id=to.id,
                    line_number=1,
                    product_id=self.get_product_id(),
                    quantity=fulfill_qty,
                    uom="CASE"
                )

                self.db.add(to)
                self.db.add(to_line)

                # Update PO line
                po_line.shipped_quantity += fulfill_qty
                available_qty -= fulfill_qty

                # Update PO status
                if po_line.shipped_quantity >= po_line.quantity:
                    po.status = "SHIPPED"  # Fully shipped
                    po.promised_delivery_date = to.estimated_delivery_date
                else:
                    po.status = "PARTIALLY_SHIPPED"

                # Update site inventory (allocated)
                await self.update_inventory(
                    site_id=site.id,
                    quantity_delta=-fulfill_qty,
                    reason=f"Shipped via TO {to.to_number} for PO {po.po_number}"
                )

            await self.db.commit()

    async def process_vendor_promises(self, round_number: int):
        """
        Market Supply sites (vendors) promise delivery dates for Manufacturer POs.
        Simulates vendor lead time.
        """
        for vendor_site in self.market_supply_sites:
            # Get all POs directed to this vendor
            pos = await self.db.query(PurchaseOrder).filter(
                PurchaseOrder.supplier_site_id == vendor_site.id,
                PurchaseOrder.status == "APPROVED",
                PurchaseOrder.game_id == self.game_id
            ).all()

            for po in pos:
                # Vendor promises delivery (infinite supply in Beer Game)
                lead_time_weeks = vendor_site.default_lead_time_weeks or 2

                po.status = "ACKNOWLEDGED"
                po.promised_delivery_date = date.today() + timedelta(weeks=lead_time_weeks)
                po.acknowledged_at = datetime.utcnow()

                # Create TransferOrder (shipment from vendor)
                to = TransferOrder(
                    to_number=f"TO-VENDOR-{self.game_id}-{round_number}-{po.id}",
                    source_site_id=vendor_site.id,
                    destination_site_id=po.destination_site_id,
                    config_id=self.config_id,
                    game_id=self.game_id,
                    order_date=date.today(),
                    shipment_date=date.today(),
                    estimated_delivery_date=po.promised_delivery_date,
                    status="IN_TRANSIT",
                    order_round=round_number,
                    arrival_round=round_number + lead_time_weeks,
                    source_po_id=po.id
                )

                # Add line items from PO
                po_lines = await self.db.query(PurchaseOrderLineItem).filter(
                    PurchaseOrderLineItem.po_id == po.id
                ).all()

                for po_line in po_lines:
                    to_line = TransferOrderLineItem(
                        to_id=to.id,
                        line_number=po_line.line_number,
                        product_id=po_line.product_id,
                        quantity=po_line.quantity,
                        uom=po_line.uom
                    )
                    self.db.add(to_line)

                self.db.add(to)

            await self.db.commit()

    async def calculate_round_metrics(self, round_number: int):
        """
        Calculate costs and KPIs for this round.
        - Holding costs (inventory * holding_cost_per_unit)
        - Backlog costs (backlog * backlog_cost_per_unit)
        - Total costs per site
        - Service levels, fill rates, etc.
        """
        for site in self.get_all_sites():
            # Get current inventory
            inv_level = await self.db.query(InvLevel).filter(
                InvLevel.site_id == site.id,
                InvLevel.product_id == self.get_product_id()
            ).first()

            inventory = inv_level.on_hand_qty if inv_level else 0.0

            # Get current backlog (unfulfilled orders)
            if site.node_type == "RETAILER":
                # Backlog from customer orders
                backlog = await self.db.query(
                    func.sum(OutboundOrderLine.backlog_quantity)
                ).filter(
                    OutboundOrderLine.site_id == site.id,
                    OutboundOrderLine.game_id == self.game_id,
                    OutboundOrderLine.status.in_(["CONFIRMED", "PARTIALLY_FULFILLED"])
                ).scalar() or 0.0
            else:
                # Backlog from unfulfilled POs to this site
                backlog = await self.db.query(
                    func.sum(PurchaseOrderLineItem.quantity - PurchaseOrderLineItem.shipped_quantity)
                ).join(PurchaseOrder).filter(
                    PurchaseOrder.destination_site_id == site.id,
                    PurchaseOrder.game_id == self.game_id,
                    PurchaseOrder.status.in_(["APPROVED", "ACKNOWLEDGED", "PARTIALLY_SHIPPED"])
                ).scalar() or 0.0

            # Calculate costs
            holding_cost = inventory * site.holding_cost_per_unit
            backlog_cost = backlog * site.backlog_cost_per_unit
            total_cost = holding_cost + backlog_cost

            # Save round metrics
            round_metric = RoundMetric(
                game_id=self.game_id,
                round_number=round_number,
                site_id=site.id,
                inventory=inventory,
                backlog=backlog,
                holding_cost=holding_cost,
                backlog_cost=backlog_cost,
                total_cost=total_cost
            )

            self.db.add(round_metric)

        await self.db.commit()

    async def save_round_state(self, round_number: int):
        """
        Save complete round state for history/replay.
        - All orders (OutboundOrderLine, PurchaseOrder, TransferOrder)
        - Inventory levels
        - Shipments
        - Metrics
        """
        # Already saved throughout the round, just mark round as complete
        round_record = Round(
            game_id=self.game_id,
            round_number=round_number,
            status="COMPLETED",
            completed_at=datetime.utcnow()
        )

        self.db.add(round_record)
        await self.db.commit()
```

### 4.3 Database Schema Additions

**Add missing fields to OutboundOrderLine**:

```sql
ALTER TABLE outbound_order_line
ADD COLUMN promised_quantity DOUBLE DEFAULT 0.0,
ADD COLUMN shipped_quantity DOUBLE DEFAULT 0.0,
ADD COLUMN backlog_quantity DOUBLE DEFAULT 0.0,
ADD COLUMN status VARCHAR(20) DEFAULT 'DRAFT',
ADD COLUMN priority_code VARCHAR(20) DEFAULT 'STANDARD',
ADD COLUMN promised_delivery_date DATE,
ADD COLUMN first_ship_date DATE,
ADD COLUMN last_ship_date DATE,
ADD COLUMN market_demand_site_id INTEGER REFERENCES nodes(id);
```

**Add fields to PurchaseOrder**:

```sql
ALTER TABLE purchase_order
ADD COLUMN game_id INTEGER REFERENCES games(id),
ADD COLUMN order_round INTEGER;
```

**Add fields to PurchaseOrderLineItem**:

```sql
ALTER TABLE purchase_order_line_item
ADD COLUMN shipped_quantity DOUBLE DEFAULT 0.0;
```

**Add TransferOrder link to PO**:

```sql
ALTER TABLE transfer_order
ADD COLUMN source_po_id INTEGER REFERENCES purchase_order(id);
```

**New table: RoundMetric** (for cost tracking):

```sql
CREATE TABLE round_metric (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL REFERENCES games(id),
    round_number INTEGER NOT NULL,
    site_id INTEGER NOT NULL REFERENCES nodes(id),

    -- Metrics
    inventory DOUBLE NOT NULL DEFAULT 0.0,
    backlog DOUBLE NOT NULL DEFAULT 0.0,
    pipeline_qty DOUBLE NOT NULL DEFAULT 0.0,

    -- Costs
    holding_cost DOUBLE NOT NULL DEFAULT 0.0,
    backlog_cost DOUBLE NOT NULL DEFAULT 0.0,
    total_cost DOUBLE NOT NULL DEFAULT 0.0,

    -- KPIs
    fill_rate DOUBLE,
    service_level DOUBLE,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(game_id, round_number, site_id)
);
```

---

## 5. Implementation Plan

### Phase 1: Database Schema Updates (Week 1)

**Tasks**:
1. Create Alembic migration for OutboundOrderLine additions
2. Create Alembic migration for PurchaseOrder/TransferOrder Beer Game fields
3. Create RoundMetric table
4. Add indexes for performance

**Success Criteria**:
- All migrations run successfully
- No breaking changes to existing data
- Test migrations on dev database

### Phase 2: Core Services (Week 2-3)

**Tasks**:
1. Create `OrderManagementService` (CRUD for OutboundOrderLine, PurchaseOrder, TransferOrder)
2. Create `FulfillmentService` (FIFO fulfillment logic, backlog processing)
3. Enhance `ATPCalculationService` (integrate with fulfillment)
4. Create `ShipmentTrackingService` (track in-transit inventory)

**Success Criteria**:
- Unit tests for all services (>80% coverage)
- Integration tests for order lifecycle
- Performance tests (handle 1000+ orders/round)

### Phase 3: Refactored Engine (Week 4-5)

**Tasks**:
1. Implement `BeerGameExecutionEngine` class
2. Migrate round execution logic to use services
3. Update agent observation calculation to use new data model
4. Implement cost calculation from order tracking

**Success Criteria**:
- Beer Game round executes successfully using new engine
- Metrics match old engine (holding cost, backlog cost)
- Agent decisions match old engine (same observation data)

### Phase 4: API Endpoints (Week 6)

**Tasks**:
1. Create `/api/v1/games/{game_id}/orders` endpoints (list customer orders, POs, TOs)
2. Create `/api/v1/games/{game_id}/backlog` endpoint (backlog report)
3. Create `/api/v1/games/{game_id}/shipments` endpoint (in-transit inventory)
4. Update existing game endpoints to use new engine

**Success Criteria**:
- API endpoints return correct data
- Frontend can display order details
- Backlog report shows aging, priority, etc.

### Phase 5: Migration & Testing (Week 7-8)

**Tasks**:
1. Create migration script to convert old games to new format
2. Run parallel testing (old engine vs. new engine)
3. Performance benchmarking
4. Bug fixes and optimization

**Success Criteria**:
- Existing games migrated without data loss
- New engine produces same results as old engine (validation test suite)
- Performance: <1 second per round execution

### Phase 6: Documentation & Rollout (Week 9)

**Tasks**:
1. Update CLAUDE.md with new execution flow
2. Create developer guide for Beer Game execution
3. Update frontend documentation
4. Deploy to production

**Success Criteria**:
- All documentation updated
- No breaking changes for existing users
- Smooth rollout with monitoring

---

## 6. Migration Strategy

### 6.1 Backward Compatibility

**Goal**: Support both old and new engines during transition period.

**Strategy**:

```python
class BeerGameService:
    """Main Beer Game orchestration service."""

    async def execute_round(self, game_id: int, round_number: int):
        game = await self.db.get(Game, game_id)

        # Check which engine to use
        if game.use_execution_engine:
            # New execution-based engine
            engine = BeerGameExecutionEngine(
                config_id=game.config_id,
                game_id=game_id,
                db_session=self.db
            )
            await engine.execute_round(round_number)
        else:
            # Old Node-based engine (deprecated)
            engine = BeerLine(...)  # Old implementation
            engine.tick()
```

**Migration Flag**:

```sql
ALTER TABLE games
ADD COLUMN use_execution_engine BOOLEAN DEFAULT FALSE;
```

**Gradual Rollout**:
1. Week 1-2: New games use new engine (opt-in)
2. Week 3-4: Migrate existing games (manual approval)
3. Week 5+: All new games use new engine by default
4. Week 8: Deprecate old engine (keep for backward compat only)

### 6.2 Data Migration Script

```python
async def migrate_game_to_execution_model(game_id: int):
    """Migrate an existing Beer Game to use the execution model."""

    game = await db.get(Game, game_id)

    if game.use_execution_engine:
        print(f"Game {game_id} already using execution engine")
        return

    # 1. Get all rounds for this game
    rounds = await db.query(Round).filter(Round.game_id == game_id).order_by(Round.round_number).all()

    for round in rounds:
        # 2. Reconstruct orders from PlayerRound data
        player_rounds = await db.query(PlayerRound).filter(
            PlayerRound.round_id == round.id
        ).all()

        for pr in player_rounds:
            site = await db.get(Node, pr.site_id)

            # 3. Create OutboundOrderLine for customer demand (if Retailer)
            if site.node_type == "RETAILER":
                order = OutboundOrderLine(
                    order_id=f"MIGRATED-{game_id}-{round.round_number}-{site.id}",
                    line_number=1,
                    product_id=game.product_id,
                    site_id=site.id,
                    ordered_quantity=pr.incoming_demand,
                    requested_delivery_date=round.round_date,
                    order_date=round.round_date,
                    game_id=game_id,
                    status="FULFILLED" if pr.shipment_qty >= pr.incoming_demand else "PARTIALLY_FULFILLED",
                    shipped_quantity=pr.shipment_qty,
                    backlog_quantity=max(0, pr.incoming_demand - pr.shipment_qty)
                )
                db.add(order)

            # 4. Create PurchaseOrder for replenishment
            if pr.order_qty > 0:
                upstream_site = get_upstream_site(site)

                po = PurchaseOrder(
                    po_number=f"MIGRATED-PO-{game_id}-{round.round_number}-{site.id}",
                    supplier_site_id=upstream_site.id,
                    destination_site_id=site.id,
                    order_date=round.round_date,
                    requested_delivery_date=round.round_date + timedelta(weeks=2),
                    status="SHIPPED",
                    game_id=game_id,
                    order_round=round.round_number
                )

                po_line = PurchaseOrderLineItem(
                    po_id=po.id,
                    line_number=1,
                    product_id=game.product_id,
                    quantity=pr.order_qty,
                    shipped_quantity=pr.order_qty  # Assume fully shipped
                )

                db.add(po)
                db.add(po_line)

            # 5. Create TransferOrder for shipments
            if pr.shipment_qty > 0:
                downstream_site = get_downstream_site(site)

                to = TransferOrder(
                    to_number=f"MIGRATED-TO-{game_id}-{round.round_number}-{site.id}",
                    source_site_id=site.id,
                    destination_site_id=downstream_site.id,
                    shipment_date=round.round_date,
                    estimated_delivery_date=round.round_date + timedelta(weeks=2),
                    status="RECEIVED",
                    game_id=game_id,
                    order_round=round.round_number,
                    arrival_round=round.round_number + 2
                )

                to_line = TransferOrderLineItem(
                    to_id=to.id,
                    line_number=1,
                    product_id=game.product_id,
                    quantity=pr.shipment_qty
                )

                db.add(to)
                db.add(to_line)

    # 6. Mark game as migrated
    game.use_execution_engine = True

    await db.commit()
    print(f"Game {game_id} successfully migrated to execution model")
```

---

## 7. Benefits Summary

### For The Beer Game

| Aspect | Before (Node-based) | After (Execution-based) |
|--------|---------------------|-------------------------|
| **Order Tracking** | Integer in pipeline | Full OutboundOrderLine with status |
| **Backlog** | Single number | Line-item tracking with FIFO |
| **ATP/CTP** | Hardcoded fulfillment | Real ATP calculation engine |
| **Order Lifecycle** | N/A | DRAFT → CONFIRMED → FULFILLED |
| **Partial Fulfillment** | Not supported | Tracked per order line |
| **Priority Orders** | Not supported | VIP vs. STANDARD |
| **Vendor Promises** | Fixed lead time | Promised delivery dates |
| **Audit Trail** | Limited | Full order/shipment history |

### For Platform

| Benefit | Description |
|---------|-------------|
| **Code Reuse** | Order management, ATP, fulfillment used in both gamification and planning |
| **Consistency** | Same data model across all modules |
| **Feature Parity** | Beer Game demonstrates real AWS SC capabilities |
| **Testing** | Beer Game serves as integration test for execution logic |
| **Learning** | Users learn real order management workflows through gamification |
| **Extensibility** | Easy to add production features (batch orders, reservations, etc.) |

---

## Next Steps

1. **Review & Approval**: Stakeholder review of this proposal
2. **Proof of Concept**: Implement Phase 1-2 in sandbox environment (2 weeks)
3. **Parallel Testing**: Run old vs. new engine side-by-side (1 week)
4. **Full Implementation**: Execute Phases 3-6 (6 weeks)
5. **Migration**: Convert existing games (1 week)
6. **Deprecation**: Remove old engine code (after 3 months of stable operation)

**Total Timeline**: ~10 weeks for complete refactoring

**Risk Mitigation**:
- Backward compatibility during transition
- Extensive testing before rollout
- Gradual migration (opt-in → default → mandatory)
- Rollback plan if issues discovered

---

**Document Status**: Ready for Review
**Next Review**: Architecture team meeting
**Questions**: Contact AI Architecture Team
