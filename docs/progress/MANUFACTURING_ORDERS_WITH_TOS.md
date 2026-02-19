# Manufacturing Orders with Transfer Order Fulfillment

## Overview

This document extends the Transfer Order implementation to support Manufacturing Orders (MOs), enabling AWS SC-compliant production scenarios where manufactured goods are transferred between sites.

---

## Manufacturing Order Flow

### Standard Manufacturing Process

```
1. MRP/MPS generates requirement for manufactured item
   ↓
2. Create Manufacturing Order at production site
   ↓
3. Allocate raw materials (components) from inventory
   ↓
4. Production process (manufacturing lead time)
   ↓
5. Complete production → increase finished goods inventory
   ↓
6. Create Transfer Order to ship finished goods to destination
   ↓
7. Transfer Order lifecycle (IN_TRANSIT → RECEIVED)
   ↓
8. Destination receives finished goods
```

### Key Difference from Purchase Orders

| Aspect | Purchase Order (PO) | Manufacturing Order (MO) |
|--------|-------------------|-------------------------|
| **Source** | External supplier | Internal production site |
| **Input** | Money → Goods | Raw materials → Finished goods |
| **Lead Time** | Transportation + procurement | Manufacturing + transportation |
| **BOM** | Not applicable | Required (component explosion) |
| **Transfer Order** | Direct shipment from supplier | After production completion |

---

## Data Model Extensions

### Manufacturing Order Entity

**Table**: `manufacturing_order`

```python
class ManufacturingOrder(Base):
    __tablename__ = "manufacturing_order"

    id = Column(Integer, primary_key=True)
    mo_number = Column(String(100), unique=True, nullable=False)

    # Production site
    production_site_id = Column(String(100), ForeignKey("nodes.site_id"))

    # Destination (where finished goods will be shipped)
    destination_site_id = Column(String(100), ForeignKey("nodes.site_id"))

    # Product and quantity
    product_id = Column(String(100), ForeignKey("items.item_id"))
    ordered_quantity = Column(Float, nullable=False)
    produced_quantity = Column(Float, default=0.0)

    # Status lifecycle
    status = Column(String(20))  # DRAFT, RELEASED, IN_PRODUCTION, COMPLETED, SHIPPED

    # Dates
    order_date = Column(Date)
    planned_start_date = Column(Date)
    planned_completion_date = Column(Date)
    actual_start_date = Column(Date)
    actual_completion_date = Column(Date)

    # Lead time
    manufacturing_lead_time_days = Column(Integer)  # Production time

    # Associated TO (for shipping finished goods)
    transfer_order_id = Column(Integer, ForeignKey("transfer_order.id"))

    # Beer Game extensions
    game_id = Column(Integer, ForeignKey("games.id"))
    order_round = Column(Integer)
    completion_round = Column(Integer)
    shipment_round = Column(Integer)

    # Audit
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, onupdate=datetime.now)
```

### Manufacturing Order Component (BOM Consumption)

**Table**: `manufacturing_order_component`

```python
class ManufacturingOrderComponent(Base):
    __tablename__ = "manufacturing_order_component"

    id = Column(Integer, primary_key=True)
    mo_id = Column(Integer, ForeignKey("manufacturing_order.id"))

    component_id = Column(String(100), ForeignKey("items.item_id"))
    required_quantity = Column(Float)  # From BOM
    allocated_quantity = Column(Float, default=0.0)
    consumed_quantity = Column(Float, default=0.0)

    status = Column(String(20))  # PENDING, ALLOCATED, CONSUMED
```

---

## Manufacturing Order Status Lifecycle

```
┌─────────┐
│  DRAFT  │  MO created, not yet approved
└────┬────┘
     │ approve()
     ▼
┌──────────┐
│ RELEASED │  Approved, ready for production
└────┬─────┘
     │ start_production() → allocate components
     ▼
┌────────────────┐
│ IN_PRODUCTION  │  Production in progress
└────────┬───────┘
     │ complete_production() → increase finished goods
     ▼
┌───────────┐
│ COMPLETED │  Production finished, ready to ship
└─────┬─────┘
     │ ship_finished_goods() → create Transfer Order
     ▼
┌──────────┐
│ SHIPPED  │  TO created and in-transit
└──────────┘
```

---

## Implementation: Manufacturing Order Creator

**File**: `backend/app/services/sc_execution/mo_creation.py`

```python
"""
Manufacturing Order Creation - AWS SC Execution

Creates and manages manufacturing orders with component allocation
and finished goods transfer.
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.manufacturing_order import ManufacturingOrder, ManufacturingOrderComponent
from app.models.sc_entities import InvLevel, ProductBOM, SourcingRules
from app.models.transfer_order import TransferOrder, TransferOrderLineItem


class ManufacturingOrderCreator:
    """
    Manufacturing Order Creator implementing AWS SC MO logic.

    Handles:
    1. MO creation based on sourcing rules
    2. Component allocation (BOM explosion)
    3. Production execution
    4. Finished goods transfer via Transfer Orders
    """

    def __init__(self, db: Session):
        self.db = db

    def create_manufacturing_order(
        self,
        production_site_id: str,
        destination_site_id: str,
        product_id: str,
        order_qty: float,
        order_date: date,
        game_id: Optional[int] = None,
        round_number: Optional[int] = None
    ) -> ManufacturingOrder:
        """
        Create manufacturing order.

        Steps:
        1. Get BOM for product
        2. Calculate component requirements
        3. Create MO record
        4. Create component records

        Args:
            production_site_id: Manufacturing site
            destination_site_id: Where finished goods will be shipped
            product_id: Product to manufacture
            order_qty: Quantity to produce
            order_date: Order date
            game_id: Game ID (optional)
            round_number: Round number (optional)

        Returns:
            Created ManufacturingOrder
        """
        # Get BOM
        bom = self._get_bom(product_id)

        if not bom:
            raise ValueError(f"No BOM found for product {product_id}")

        # Get manufacturing lead time
        sourcing_rule = self._get_sourcing_rule(destination_site_id, product_id)
        mfg_lead_time_days = sourcing_rule.lead_time_days if sourcing_rule else 14

        # Calculate dates
        planned_start_date = order_date
        planned_completion_date = order_date + timedelta(days=mfg_lead_time_days)

        # Calculate rounds
        completion_round = None
        shipment_round = None
        if round_number is not None:
            lead_time_rounds = mfg_lead_time_days // 7
            completion_round = round_number + lead_time_rounds

            # Add transport time (default 2 weeks)
            transport_lead_time_rounds = 2
            shipment_round = completion_round + transport_lead_time_rounds

        # Generate MO number
        mo_number = self._generate_mo_number(game_id, round_number, production_site_id)

        # Create MO
        mo = ManufacturingOrder(
            mo_number=mo_number,
            production_site_id=production_site_id,
            destination_site_id=destination_site_id,
            product_id=product_id,
            ordered_quantity=order_qty,
            status="RELEASED",
            order_date=order_date,
            planned_start_date=planned_start_date,
            planned_completion_date=planned_completion_date,
            manufacturing_lead_time_days=mfg_lead_time_days,
            game_id=game_id,
            order_round=round_number,
            completion_round=completion_round,
            shipment_round=shipment_round,
            created_at=datetime.now()
        )
        self.db.add(mo)
        self.db.flush()  # Get MO ID

        # Create component requirements
        for bom_item in bom:
            required_qty = bom_item.component_quantity * order_qty

            component = ManufacturingOrderComponent(
                mo_id=mo.id,
                component_id=bom_item.component_id,
                required_quantity=required_qty,
                status="PENDING"
            )
            self.db.add(component)

        self.db.commit()
        return mo

    def start_production(self, mo: ManufacturingOrder) -> None:
        """
        Start production (allocate components).

        Updates:
        1. MO status: RELEASED → IN_PRODUCTION
        2. Component status: PENDING → ALLOCATED
        3. Inventory allocated_qty increases

        Args:
            mo: Manufacturing Order
        """
        if mo.status != "RELEASED":
            raise ValueError(f"MO {mo.mo_number} not in RELEASED status")

        # Get components
        components = self.db.query(ManufacturingOrderComponent).filter(
            ManufacturingOrderComponent.mo_id == mo.id
        ).all()

        # Allocate each component
        for component in components:
            self._allocate_component(
                mo.production_site_id,
                component.component_id,
                component.required_quantity
            )
            component.allocated_quantity = component.required_quantity
            component.status = "ALLOCATED"

        # Update MO status
        mo.status = "IN_PRODUCTION"
        mo.actual_start_date = datetime.now().date()

        self.db.commit()

    def complete_production(self, mo: ManufacturingOrder) -> None:
        """
        Complete production.

        Updates:
        1. Consume components (reduce on_hand + allocated)
        2. Increase finished goods inventory
        3. MO status: IN_PRODUCTION → COMPLETED

        Args:
            mo: Manufacturing Order
        """
        if mo.status != "IN_PRODUCTION":
            raise ValueError(f"MO {mo.mo_number} not in IN_PRODUCTION status")

        # Get components
        components = self.db.query(ManufacturingOrderComponent).filter(
            ManufacturingOrderComponent.mo_id == mo.id
        ).all()

        # Consume components
        for component in components:
            self._consume_component(
                mo.production_site_id,
                component.component_id,
                component.required_quantity
            )
            component.consumed_quantity = component.required_quantity
            component.status = "CONSUMED"

        # Increase finished goods inventory
        self._produce_finished_goods(
            mo.production_site_id,
            mo.product_id,
            mo.ordered_quantity
        )

        # Update MO
        mo.status = "COMPLETED"
        mo.actual_completion_date = datetime.now().date()
        mo.produced_quantity = mo.ordered_quantity

        self.db.commit()

    def ship_finished_goods(self, mo: ManufacturingOrder) -> TransferOrder:
        """
        Ship finished goods to destination via Transfer Order.

        Creates Transfer Order for finished goods.

        Args:
            mo: Manufacturing Order

        Returns:
            Created TransferOrder
        """
        if mo.status != "COMPLETED":
            raise ValueError(f"MO {mo.mo_number} not in COMPLETED status")

        # Get transport lead time
        sourcing_rule = self._get_sourcing_rule(
            mo.destination_site_id,
            mo.product_id
        )
        transport_lead_time = 14  # Default 2 weeks

        # Calculate arrival
        shipment_date = datetime.now().date()
        estimated_delivery_date = shipment_date + timedelta(days=transport_lead_time)

        arrival_round = None
        if mo.completion_round is not None:
            arrival_round = mo.completion_round + (transport_lead_time // 7)

        # Create Transfer Order
        from app.services.sc_execution.order_promising import OrderPromisingEngine
        order_promising = OrderPromisingEngine(self.db)

        # Generate TO number
        timestamp = int(datetime.now().timestamp())
        to_number = f"TO-MO-{mo.mo_number}-{timestamp}"

        # Create TO
        to = TransferOrder(
            to_number=to_number,
            source_site_id=mo.production_site_id,
            destination_site_id=mo.destination_site_id,
            status="IN_TRANSIT",
            order_date=shipment_date,
            shipment_date=shipment_date,
            estimated_delivery_date=estimated_delivery_date,
            game_id=mo.game_id,
            order_round=mo.completion_round,
            arrival_round=arrival_round,
            created_at=datetime.now()
        )
        self.db.add(to)
        self.db.flush()

        # Create TO line item
        to_line = TransferOrderLineItem(
            to_id=to.id,
            line_number=1,
            product_id=mo.product_id,
            ordered_quantity=mo.produced_quantity,
            shipped_quantity=mo.produced_quantity,
            received_quantity=0.0,
            requested_delivery_date=estimated_delivery_date
        )
        self.db.add(to_line)

        # Update destination in_transit_qty
        dest_inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == mo.destination_site_id,
                InvLevel.item_id == mo.product_id
            )
        ).first()

        if dest_inv_level:
            dest_inv_level.in_transit_qty += mo.produced_quantity
        else:
            # Create inv_level
            dest_inv_level = InvLevel(
                site_id=mo.destination_site_id,
                item_id=mo.product_id,
                on_hand_qty=0.0,
                backorder_qty=0.0,
                in_transit_qty=mo.produced_quantity,
                allocated_qty=0.0,
                available_qty=0.0,
                safety_stock_qty=0.0,
                reorder_point_qty=0.0,
                min_qty=0.0,
                max_qty=1000.0
            )
            self.db.add(dest_inv_level)

        # Reduce on_hand at production site (ship inventory)
        prod_inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == mo.production_site_id,
                InvLevel.item_id == mo.product_id
            )
        ).first()

        if prod_inv_level:
            prod_inv_level.on_hand_qty -= mo.produced_quantity
            prod_inv_level.on_hand_qty = max(0.0, prod_inv_level.on_hand_qty)

        # Update MO
        mo.status = "SHIPPED"
        mo.transfer_order_id = to.id

        self.db.commit()

        return to

    def process_completing_orders(
        self,
        game_id: int,
        round_number: int
    ) -> List[ManufacturingOrder]:
        """
        Process MOs completing in current round.

        Args:
            game_id: Game ID
            round_number: Current round number

        Returns:
            List of completed MOs
        """
        # Get MOs that complete this round
        completing_mos = self.db.query(ManufacturingOrder).filter(
            and_(
                ManufacturingOrder.game_id == game_id,
                ManufacturingOrder.completion_round == round_number,
                ManufacturingOrder.status == "IN_PRODUCTION"
            )
        ).all()

        for mo in completing_mos:
            self.complete_production(mo)
            # Immediately ship finished goods
            self.ship_finished_goods(mo)

        return completing_mos

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _get_bom(self, product_id: str) -> List[ProductBOM]:
        """Get BOM for product."""
        return self.db.query(ProductBOM).filter(
            ProductBOM.product_id == product_id
        ).all()

    def _get_sourcing_rule(
        self,
        destination_site_id: str,
        product_id: str
    ) -> Optional[SourcingRules]:
        """Get sourcing rule."""
        return self.db.query(SourcingRules).filter(
            and_(
                SourcingRules.destination_site_id == destination_site_id,
                SourcingRules.item_id == product_id
            )
        ).order_by(SourcingRules.priority.asc()).first()

    def _allocate_component(
        self,
        site_id: str,
        component_id: str,
        qty: float
    ) -> None:
        """Allocate component inventory."""
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.item_id == component_id
            )
        ).first()

        if inv_level:
            inv_level.allocated_qty += qty

    def _consume_component(
        self,
        site_id: str,
        component_id: str,
        qty: float
    ) -> None:
        """Consume component (reduce inventory)."""
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.item_id == component_id
            )
        ).first()

        if inv_level:
            inv_level.on_hand_qty -= qty
            inv_level.allocated_qty -= qty

            inv_level.on_hand_qty = max(0.0, inv_level.on_hand_qty)
            inv_level.allocated_qty = max(0.0, inv_level.allocated_qty)

    def _produce_finished_goods(
        self,
        site_id: str,
        product_id: str,
        qty: float
    ) -> None:
        """Increase finished goods inventory."""
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.item_id == product_id
            )
        ).first()

        if inv_level:
            inv_level.on_hand_qty += qty
        else:
            # Create inv_level
            inv_level = InvLevel(
                site_id=site_id,
                item_id=product_id,
                on_hand_qty=qty,
                backorder_qty=0.0,
                in_transit_qty=0.0,
                allocated_qty=0.0,
                available_qty=qty,
                safety_stock_qty=0.0,
                reorder_point_qty=0.0,
                min_qty=0.0,
                max_qty=1000.0
            )
            self.db.add(inv_level)

    def _generate_mo_number(
        self,
        game_id: Optional[int],
        round_number: Optional[int],
        site_id: str
    ) -> str:
        """Generate unique MO number."""
        timestamp = int(datetime.now().timestamp())

        if game_id and round_number:
            return f"MO-G{game_id}-R{round_number}-{site_id}-{timestamp}"
        else:
            return f"MO-{site_id}-{timestamp}"
```

---

## Integration with Beer Game Executor

### Updated Round Execution

```python
# In beer_game_executor.py

async def execute_round(
    self,
    game_id: int,
    round_number: int,
    agent_decisions: Dict[str, float],
    market_demand: Optional[float] = None
) -> Dict:
    """Execute Beer Game round with MO support."""

    # STEP 1: RECEIVE SHIPMENTS
    # 1a. Receive Purchase Orders
    arriving_pos = self.po_creator.process_arriving_orders(game_id, round_number)

    # 1b. Receive Transfer Orders
    arriving_tos = self.order_promising.process_arriving_transfers(game_id, round_number)

    # 1c. Complete Manufacturing Orders (NEW!)
    completing_mos = self.mo_creator.process_completing_orders(game_id, round_number)

    # STEP 2: GENERATE MARKET DEMAND
    # ... same as before ...

    # STEP 3: ORDER PROMISING
    # ... same as before ...

    # STEP 4: AGENT DECISIONS
    # ... same as before ...

    # STEP 5: CREATE ORDERS
    # Now includes MOs for manufactured products
    for site_id, order_qty in agent_decisions.items():
        sourcing_rule = self._get_sourcing_rule(site_id, "cases")

        if sourcing_rule.source_type == "manufacture":
            # Create Manufacturing Order
            mo = self.mo_creator.create_manufacturing_order(
                production_site_id=sourcing_rule.source_site_id,
                destination_site_id=site_id,
                product_id="cases",
                order_qty=order_qty,
                order_date=round_date,
                game_id=game_id,
                round_number=round_number
            )

            # Start production immediately
            self.mo_creator.start_production(mo)

        elif sourcing_rule.source_type == "transfer":
            # Create PO (fulfilled with TO later)
            # ... existing logic ...

    # STEP 6: COST ACCRUAL
    # ... same as before ...

    # STEP 7: STATE SNAPSHOT
    # ... same as before ...
```

---

## Example: Multi-Level BOM with TOs

### Scenario

```
Supply Chain:
  [Market] → [Distribution Center] → [Assembly Plant] → [Component Supplier]

Products:
  - Case (finished goods) = 4 Six-Packs
  - Six-Pack (sub-assembly) = 6 Bottles
  - Bottle (component) = purchased

Manufacturing:
  - Assembly Plant manufactures Cases from Six-Packs
  - Assembly Plant manufactures Six-Packs from Bottles
```

### Round Execution Flow

**Round 1**:
1. Market demand: 10 Cases
2. DC fulfills 10 Cases to market (creates TO: DC → Market)
3. DC orders 15 Cases from Assembly Plant
4. Assembly Plant creates MO-001: Manufacture 15 Cases
   - Requires: 15 Cases × 4 Six-Packs = 60 Six-Packs
   - Allocates 60 Six-Packs from inventory
   - MO status: RELEASED → IN_PRODUCTION

**Round 3** (2 rounds later, manufacturing lead time complete):
1. Complete MO-001:
   - Consume 60 Six-Packs
   - Produce 15 Cases
   - MO status: IN_PRODUCTION → COMPLETED
2. Ship finished goods:
   - Create TO-001: Assembly Plant → DC (15 Cases)
   - TO status: IN_TRANSIT
   - DC in_transit_qty += 15

**Round 5** (2 rounds later, transport lead time complete):
1. Receive TO-001:
   - DC in_transit_qty -= 15
   - DC on_hand_qty += 15
   - TO status: RECEIVED

---

## Benefits

1. **AWS SC Compliance**: Full compliance with MO → TO flow
2. **BOM Support**: Multi-level component explosion
3. **Lead Time Management**: Separate manufacturing and transportation lead times
4. **Inventory Tracking**: Component allocation, consumption, and finished goods
5. **Transfer Order Integration**: Seamless TO creation after production
6. **Multi-Echelon Production**: Supports cascading manufacturing across sites

---

## Summary

The Manufacturing Order with Transfer Order fulfillment extends the AWS SC execution engine to support:
- Production planning and execution
- Component allocation and consumption
- Finished goods inventory management
- Inter-site transfer of manufactured goods

This completes the AWS SC execution engine with full support for:
- **Purchase Orders** (external procurement)
- **Transfer Orders** (inter-site transfers)
- **Manufacturing Orders** (production with TO fulfillment)

All three order types now properly integrate with Transfer Orders for complete supply chain visibility and multi-period planning.
