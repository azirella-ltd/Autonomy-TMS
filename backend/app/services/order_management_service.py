"""
Order Management Service

Provides CRUD operations and business logic for order management entities:
- OutboundOrderLine (customer orders/sales orders)
- PurchaseOrder (replenishment from vendors/upstream sites)
- TransferOrder (inter-site movements)

Used by SimulationExecutionEngine for execution-based game flow.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.orm import selectinload

from app.models.sc_entities import OutboundOrderLine
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.supply_chain_config import Node

logger = logging.getLogger(__name__)


class OrderManagementService:
    """Service for managing orders in simulation execution."""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    # ========================================================================
    # OutboundOrderLine (Customer Orders) Operations
    # ========================================================================

    async def create_customer_order(
        self,
        order_id: str,
        line_number: int,
        product_id: str,
        site_id: int,
        ordered_quantity: float,
        requested_delivery_date: date,
        market_demand_site_id: Optional[int] = None,
        priority_code: str = "STANDARD",
        config_id: Optional[int] = None,
        scenario_id: Optional[int] = None,
        group_id: Optional[int] = None,
    ) -> OutboundOrderLine:
        """
        Create a customer order (OutboundOrderLine).

        Args:
            order_id: Unique order identifier
            line_number: Line number within order
            product_id: Product being ordered
            site_id: Fulfillment site (e.g., Retailer)
            ordered_quantity: Quantity ordered
            requested_delivery_date: Customer's requested date
            market_demand_site_id: Customer site (simulation)
            priority_code: VIP, HIGH, STANDARD, LOW
            config_id: Supply chain configuration ID
            scenario_id: Scenario ID (if applicable)
            group_id: Group ID (enables conformal prediction feedback)

        Returns:
            Created OutboundOrderLine
        """
        order = OutboundOrderLine(
            order_id=order_id,
            line_number=line_number,
            product_id=product_id,
            site_id=site_id,
            ordered_quantity=ordered_quantity,
            requested_delivery_date=requested_delivery_date,
            order_date=date.today(),
            market_demand_site_id=market_demand_site_id,
            priority_code=priority_code,
            status="DRAFT",
            shipped_quantity=0.0,
            backlog_quantity=0.0,
            config_id=config_id,
            scenario_id=scenario_id,
        )

        self.db.add(order)
        await self.db.flush()
        await self.db.refresh(order)

        # Feed into conformal prediction calibration loop
        if group_id is not None:
            try:
                from app.services.conformal_orchestrator import ConformalOrchestrator
                orchestrator = ConformalOrchestrator.get_instance()
                await orchestrator.on_actual_demand_observed(
                    db=self.db,
                    product_id=product_id,
                    site_id=site_id,
                    ordered_quantity=ordered_quantity,
                    order_date=requested_delivery_date,
                    group_id=group_id,
                )
            except Exception as e:
                logger.warning(f"Conformal actuals hook failed: {e}")

        return order

    async def get_unfulfilled_customer_orders(
        self,
        site_id: int,
        scenario_id: Optional[int] = None,
        priority_order: bool = True,
    ) -> List[OutboundOrderLine]:
        """
        Get all unfulfilled customer orders for a site.

        Args:
            site_id: Site fulfilling the orders
            scenario_id: Filter by game ID
            priority_order: If True, sort by order_date ASC, priority DESC (FIFO with priority)

        Returns:
            List of unfulfilled OutboundOrderLine records
        """
        query = select(OutboundOrderLine).where(
            and_(
                OutboundOrderLine.site_id == site_id,
                OutboundOrderLine.status.in_(['DRAFT', 'CONFIRMED', 'PARTIALLY_FULFILLED']),
                OutboundOrderLine.backlog_quantity > 0 or OutboundOrderLine.shipped_quantity < OutboundOrderLine.ordered_quantity
            )
        )

        if scenario_id is not None:
            query = query.where(OutboundOrderLine.scenario_id == scenario_id)

        if priority_order:
            # FIFO with priority: oldest first, then VIP > HIGH > STANDARD > LOW
            query = query.order_by(
                OutboundOrderLine.order_date.asc(),
                OutboundOrderLine.priority_code.desc()
            )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_order_fulfillment(
        self,
        order_id: int,
        shipped_quantity: float,
        promised_delivery_date: Optional[date] = None,
        group_id: Optional[int] = None,
    ) -> OutboundOrderLine:
        """
        Update order fulfillment status.

        Args:
            order_id: OutboundOrderLine ID
            shipped_quantity: Additional quantity shipped
            promised_delivery_date: ATP-promised delivery date
            group_id: Group ID (enables conformal service level feedback)

        Returns:
            Updated OutboundOrderLine
        """
        order = await self.db.get(OutboundOrderLine, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Update shipped quantity
        order.shipped_quantity += shipped_quantity

        # Update backlog
        order.backlog_quantity = max(0, order.ordered_quantity - order.shipped_quantity)

        # Update status
        if order.shipped_quantity >= order.ordered_quantity:
            order.status = "FULFILLED"
            order.last_ship_date = date.today()

            # Feed service level observation into conformal prediction
            if group_id is not None and order.ordered_quantity > 0:
                try:
                    from app.services.conformal_orchestrator import ConformalOrchestrator
                    actual_fill = float(order.shipped_quantity) / float(order.ordered_quantity)
                    orchestrator = ConformalOrchestrator.get_instance()
                    await orchestrator.on_service_level_observed(
                        db=self.db,
                        product_id=order.product_id,
                        site_id=order.site_id,
                        expected_fill_rate=1.0,
                        actual_fill_rate=actual_fill,
                        group_id=group_id,
                    )
                except Exception as e:
                    logger.warning(f"Conformal service level hook failed: {e}")

        elif order.shipped_quantity > 0:
            order.status = "PARTIALLY_FULFILLED"
            if order.first_ship_date is None:
                order.first_ship_date = date.today()
        else:
            order.status = "CONFIRMED"

        # Update promised date if provided
        if promised_delivery_date:
            order.promised_delivery_date = promised_delivery_date

        await self.db.flush()
        await self.db.refresh(order)

        return order

    async def get_backlog_for_site(
        self,
        site_id: int,
        product_id: Optional[str] = None,
        scenario_id: Optional[int] = None,
    ) -> float:
        """
        Calculate total backlog quantity for a site.

        Args:
            site_id: Site ID
            product_id: Optional product filter
            scenario_id: Optional game filter

        Returns:
            Total backlog quantity
        """
        query = select(func.sum(OutboundOrderLine.backlog_quantity)).where(
            and_(
                OutboundOrderLine.site_id == site_id,
                OutboundOrderLine.status.in_(['CONFIRMED', 'PARTIALLY_FULFILLED'])
            )
        )

        if product_id:
            query = query.where(OutboundOrderLine.product_id == product_id)

        if scenario_id is not None:
            query = query.where(OutboundOrderLine.scenario_id == scenario_id)

        result = await self.db.execute(query)
        backlog = result.scalar()

        return float(backlog) if backlog else 0.0

    # ========================================================================
    # PurchaseOrder Operations
    # ========================================================================

    async def create_purchase_order(
        self,
        po_number: str,
        supplier_site_id: int,
        destination_site_id: int,
        product_id: str,
        quantity: float,
        requested_delivery_date: date,
        vendor_id: Optional[str] = None,
        config_id: Optional[int] = None,
        group_id: Optional[int] = None,
        scenario_id: Optional[int] = None,
        order_round: Optional[int] = None,
    ) -> PurchaseOrder:
        """
        Create a purchase order.

        Args:
            po_number: Unique PO number
            supplier_site_id: Supplying site
            destination_site_id: Receiving site
            product_id: Product being ordered
            quantity: Order quantity
            requested_delivery_date: Requested delivery date
            vendor_id: External vendor ID (if applicable)
            config_id: Supply chain configuration
            group_id: Group ID
            scenario_id: Scenario ID
            order_round: Round when PO was created

        Returns:
            Created PurchaseOrder with line item
        """
        po = PurchaseOrder(
            po_number=po_number,
            vendor_id=vendor_id,
            supplier_site_id=supplier_site_id,
            destination_site_id=destination_site_id,
            config_id=config_id,
            group_id=group_id,
            status="APPROVED",  # Auto-approve in simulation
            order_date=date.today(),
            requested_delivery_date=requested_delivery_date,
            scenario_id=scenario_id,
            order_round=order_round,
        )

        self.db.add(po)
        await self.db.flush()

        # Add line item
        po_line = PurchaseOrderLineItem(
            po_id=po.id,
            line_number=1,
            product_id=product_id,
            quantity=quantity,
            shipped_quantity=0.0,
            received_quantity=0.0,
            unit_price=10.0,  # Fixed for simulation
            line_total=quantity * 10.0,
        )

        self.db.add(po_line)
        await self.db.flush()
        await self.db.refresh(po)

        return po

    async def get_unfulfilled_purchase_orders(
        self,
        supplier_site_id: int,
        scenario_id: Optional[int] = None,
    ) -> List[PurchaseOrder]:
        """
        Get all unfulfilled POs for a supplier site.

        Args:
            supplier_site_id: Supplier site ID
            scenario_id: Optional game filter

        Returns:
            List of unfulfilled PurchaseOrders
        """
        query = select(PurchaseOrder).where(
            and_(
                PurchaseOrder.supplier_site_id == supplier_site_id,
                PurchaseOrder.status.in_(['APPROVED', 'ACKNOWLEDGED', 'PARTIALLY_SHIPPED'])
            )
        ).options(selectinload(PurchaseOrder.line_items))

        if scenario_id is not None:
            query = query.where(PurchaseOrder.scenario_id == scenario_id)

        query = query.order_by(PurchaseOrder.order_date.asc())  # FIFO

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_po_shipment(
        self,
        po_id: int,
        line_number: int,
        shipped_quantity: float,
        promised_delivery_date: Optional[date] = None,
    ) -> PurchaseOrder:
        """
        Update PO line item shipment status.

        Args:
            po_id: PurchaseOrder ID
            line_number: Line item number
            shipped_quantity: Additional quantity shipped
            promised_delivery_date: Vendor-promised delivery date

        Returns:
            Updated PurchaseOrder
        """
        po = await self.db.get(PurchaseOrder, po_id)
        if not po:
            raise ValueError(f"PurchaseOrder {po_id} not found")

        # Get line item
        result = await self.db.execute(
            select(PurchaseOrderLineItem).where(
                and_(
                    PurchaseOrderLineItem.po_id == po_id,
                    PurchaseOrderLineItem.line_number == line_number
                )
            )
        )
        po_line = result.scalar_one_or_none()

        if not po_line:
            raise ValueError(f"PO line {line_number} not found")

        # Update shipped quantity
        po_line.shipped_quantity += shipped_quantity

        # Update PO status
        if po_line.shipped_quantity >= po_line.quantity:
            po.status = "SHIPPED"
            po.promised_delivery_date = promised_delivery_date
        elif po_line.shipped_quantity > 0:
            po.status = "PARTIALLY_SHIPPED"
        else:
            po.status = "ACKNOWLEDGED"

        await self.db.flush()
        await self.db.refresh(po)

        return po

    # ========================================================================
    # TransferOrder Operations
    # ========================================================================

    async def create_transfer_order(
        self,
        to_number: str,
        source_site_id: int,
        destination_site_id: int,
        product_id: str,
        quantity: float,
        estimated_delivery_date: date,
        config_id: Optional[int] = None,
        scenario_id: Optional[int] = None,
        order_round: Optional[int] = None,
        arrival_round: Optional[int] = None,
        source_po_id: Optional[int] = None,
    ) -> TransferOrder:
        """
        Create a transfer order.

        Args:
            to_number: Unique TO number
            source_site_id: Source site
            destination_site_id: Destination site
            product_id: Product being transferred
            quantity: Transfer quantity
            estimated_delivery_date: Estimated delivery date
            config_id: Supply chain configuration
            scenario_id: Scenario ID
            order_round: Round when TO was created
            arrival_round: Round when TO arrives
            source_po_id: Link to originating PO (if applicable)

        Returns:
            Created TransferOrder with line item
        """
        to = TransferOrder(
            to_number=to_number,
            source_site_id=source_site_id,
            destination_site_id=destination_site_id,
            config_id=config_id,
            order_date=date.today(),
            shipment_date=date.today(),
            estimated_delivery_date=estimated_delivery_date,
            status="IN_TRANSIT",
            scenario_id=scenario_id,
            order_round=order_round,
            arrival_round=arrival_round,
            source_po_id=source_po_id,
        )

        self.db.add(to)
        await self.db.flush()

        # Add line item
        to_line = TransferOrderLineItem(
            to_id=to.id,
            line_number=1,
            product_id=product_id,
            quantity=quantity,
            uom="CASE",
        )

        self.db.add(to_line)
        await self.db.flush()
        await self.db.refresh(to)

        return to

    async def get_arriving_transfer_orders(
        self,
        scenario_id: int,
        arrival_round: int,
    ) -> List[TransferOrder]:
        """
        Get all TOs arriving in a specific round.

        Args:
            scenario_id: Scenario ID
            arrival_round: Round number

        Returns:
            List of arriving TransferOrders
        """
        result = await self.db.execute(
            select(TransferOrder)
            .where(
                and_(
                    TransferOrder.scenario_id == scenario_id,
                    TransferOrder.arrival_round == arrival_round,
                    TransferOrder.status == "IN_TRANSIT"
                )
            )
            .options(selectinload(TransferOrder.line_items))
        )

        return list(result.scalars().all())

    async def receive_transfer_order(
        self,
        to_id: int,
    ) -> TransferOrder:
        """
        Mark transfer order as received.

        Args:
            to_id: TransferOrder ID

        Returns:
            Updated TransferOrder
        """
        to = await self.db.get(TransferOrder, to_id)
        if not to:
            raise ValueError(f"TransferOrder {to_id} not found")

        to.status = "RECEIVED"
        to.actual_delivery_date = date.today()
        to.received_at = datetime.utcnow()

        # Feed lead time observation into conformal prediction
        if getattr(to, 'group_id', None) is not None and to.order_date and to.actual_delivery_date:
            try:
                from app.services.conformal_orchestrator import ConformalOrchestrator
                actual_lt = (to.actual_delivery_date - to.order_date).days
                expected_lt = (
                    (to.estimated_delivery_date - to.order_date).days
                    if to.estimated_delivery_date else actual_lt
                )
                if expected_lt > 0:
                    orchestrator = ConformalOrchestrator.get_instance()
                    await orchestrator.on_lead_time_observed(
                        db=self.db,
                        supplier_id=str(to.source_site_id),
                        expected_lead_time_days=float(expected_lt),
                        actual_lead_time_days=float(actual_lt),
                        group_id=to.group_id,
                        source_order_type="TO",
                        source_order_id=to.id,
                    )
            except Exception as e:
                logger.warning(f"Conformal lead time hook failed: {e}")

        # Update associated PO if exists
        if to.source_po_id:
            po = await self.db.get(PurchaseOrder, to.source_po_id)
            if po:
                po.status = "RECEIVED"
                po.actual_delivery_date = date.today()
                po.received_at = datetime.utcnow()

                # Feed PO lead time + price into conformal prediction
                if getattr(po, 'group_id', None) is not None:
                    try:
                        from app.services.conformal_orchestrator import ConformalOrchestrator
                        orchestrator = ConformalOrchestrator.get_instance()

                        # Lead time from PO
                        if po.order_date and po.actual_delivery_date:
                            actual_lt = (po.actual_delivery_date - po.order_date).days
                            expected_lt = (
                                (po.requested_delivery_date - po.order_date).days
                                if po.requested_delivery_date else actual_lt
                            )
                            if expected_lt > 0:
                                supplier_id = po.vendor_id or str(po.supplier_site_id)
                                await orchestrator.on_lead_time_observed(
                                    db=self.db,
                                    supplier_id=supplier_id,
                                    expected_lead_time_days=float(expected_lt),
                                    actual_lead_time_days=float(actual_lt),
                                    group_id=po.group_id,
                                    source_order_type="PO",
                                    source_order_id=po.id,
                                )

                        # Price from PO line items vs catalog
                        from app.models.purchase_order import PurchaseOrderLineItem
                        from app.models.supplier import VendorProduct
                        po_lines_result = await self.db.execute(
                            select(PurchaseOrderLineItem).where(
                                PurchaseOrderLineItem.po_id == po.id
                            )
                        )
                        for po_line in po_lines_result.scalars().all():
                            if po_line.unit_price is not None:
                                vendor_id = po.vendor_id or str(po.supplier_site_id)
                                vp_result = await self.db.execute(
                                    select(VendorProduct).where(
                                        and_(
                                            VendorProduct.tpartner_id == vendor_id,
                                            VendorProduct.product_id == po_line.product_id,
                                            VendorProduct.is_active == "true",
                                        )
                                    ).limit(1)
                                )
                                vp = vp_result.scalar_one_or_none()
                                if vp and vp.vendor_unit_cost:
                                    await orchestrator.on_price_observed(
                                        db=self.db,
                                        material_id=po_line.product_id,
                                        expected_price=float(vp.vendor_unit_cost),
                                        actual_price=float(po_line.unit_price),
                                        group_id=po.group_id,
                                        source_po_id=po.id,
                                    )
                    except Exception as e:
                        logger.warning(f"Conformal PO hooks failed: {e}")

        await self.db.flush()
        await self.db.refresh(to)

        return to

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def get_site_by_id(self, site_id: int) -> Optional[Node]:
        """Get site by ID."""
        return await self.db.get(Node, site_id)

    async def commit(self):
        """Commit the current transaction."""
        await self.db.commit()

    async def rollback(self):
        """Rollback the current transaction."""
        await self.db.rollback()
