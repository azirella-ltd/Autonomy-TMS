"""
Fulfillment Service

Provides order fulfillment logic with FIFO and priority support.
Integrates with OrderManagementService to fulfill customer orders,
process backlogs, and create shipments (TransferOrders).

Used by SimulationExecutionEngine for execution-based order fulfillment.

Powell Integration:
- When enabled, uses allocation-based ATP (AATP) from Powell framework
- Consumption follows priority rules: own tier first, bottom-up from lowest
- All decisions logged for TRM training
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import date, datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from app.models.sc_entities import OutboundOrderLine, InvLevel
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.supply_chain_config import Node
from app.services.order_management_service import OrderManagementService

logger = logging.getLogger(__name__)


class FulfillmentService:
    """Service for fulfilling orders with FIFO and priority support.

    Powell Integration:
        When use_powell=True is passed to methods, fulfillment uses
        allocation-based ATP (AATP) from the Powell framework instead
        of simple FIFO. This provides:
        - Priority-based inventory allocation
        - Consumption tracking for TRM training
        - Configurable auto-execution thresholds
    """

    def __init__(
        self,
        db_session: AsyncSession,
        powell_integration: Optional[Any] = None,
    ):
        self.db = db_session
        self.order_mgmt = OrderManagementService(db_session)
        self._powell_integration = powell_integration

    async def _get_powell_integration(self):
        """Lazy load Powell integration service."""
        if self._powell_integration is None:
            try:
                from app.services.powell.integration_service import (
                    PowellIntegrationService,
                    IntegrationConfig,
                )
                self._powell_integration = PowellIntegrationService(
                    self.db,
                    IntegrationConfig(enable_atp_executor=True),
                )
            except ImportError:
                logger.warning("Powell integration not available")
                self._powell_integration = False  # Mark as unavailable
        return self._powell_integration if self._powell_integration else None

    # ========================================================================
    # ATP (Available-to-Promise) Calculation
    # ========================================================================

    async def calculate_available_to_ship(
        self,
        site_id: int,
        product_id: str,
        config_id: Optional[int] = None,
        scenario_id: Optional[int] = None,
    ) -> float:
        """
        Calculate available-to-ship quantity (ATP).

        ATP = On-hand inventory - Committed/allocated quantities

        Args:
            site_id: Site ID
            product_id: Product ID
            config_id: Supply chain configuration ID
            scenario_id: Scenario ID (if applicable)

        Returns:
            Available-to-ship quantity (ATP)
        """
        # Get current inventory level
        query = select(InvLevel).where(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.product_id == product_id,
            )
        )

        if config_id is not None:
            query = query.where(InvLevel.config_id == config_id)
        if scenario_id is not None:
            query = query.where(InvLevel.scenario_id == scenario_id)

        result = await self.db.execute(query)
        inv_level = result.scalar_one_or_none()

        if not inv_level:
            return 0.0

        on_hand = inv_level.quantity

        # Calculate committed quantity (sum of unfulfilled orders already promised)
        committed_query = select(func.sum(OutboundOrderLine.promised_quantity)).where(
            and_(
                OutboundOrderLine.site_id == site_id,
                OutboundOrderLine.product_id == product_id,
                OutboundOrderLine.status.in_(['CONFIRMED', 'PARTIALLY_FULFILLED']),
                OutboundOrderLine.promised_quantity.isnot(None),
            )
        )

        if scenario_id is not None:
            committed_query = committed_query.where(OutboundOrderLine.scenario_id == scenario_id)

        committed_result = await self.db.execute(committed_query)
        committed_qty = committed_result.scalar() or 0.0

        # ATP = On-hand - Committed
        atp = max(0.0, on_hand - committed_qty)

        return atp

    async def get_inventory_level(
        self,
        site_id: int,
        product_id: str,
        config_id: Optional[int] = None,
        scenario_id: Optional[int] = None,
    ) -> float:
        """
        Get current on-hand inventory level.

        Args:
            site_id: Site ID
            product_id: Product ID
            config_id: Configuration ID
            scenario_id: Game ID

        Returns:
            On-hand inventory quantity
        """
        query = select(InvLevel).where(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.product_id == product_id,
            )
        )

        if config_id is not None:
            query = query.where(InvLevel.config_id == config_id)
        if scenario_id is not None:
            query = query.where(InvLevel.scenario_id == scenario_id)

        result = await self.db.execute(query)
        inv_level = result.scalar_one_or_none()

        return inv_level.quantity if inv_level else 0.0

    async def update_inventory_level(
        self,
        site_id: int,
        product_id: str,
        quantity_change: float,
        config_id: Optional[int] = None,
        scenario_id: Optional[int] = None,
    ) -> InvLevel:
        """
        Update inventory level by adding/subtracting quantity.

        Args:
            site_id: Site ID
            product_id: Product ID
            quantity_change: Positive for receipt, negative for shipment
            config_id: Configuration ID
            scenario_id: Game ID

        Returns:
            Updated InvLevel
        """
        query = select(InvLevel).where(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.product_id == product_id,
            )
        )

        if config_id is not None:
            query = query.where(InvLevel.config_id == config_id)
        if scenario_id is not None:
            query = query.where(InvLevel.scenario_id == scenario_id)

        result = await self.db.execute(query)
        inv_level = result.scalar_one_or_none()

        if not inv_level:
            # Create new inventory level record
            inv_level = InvLevel(
                site_id=site_id,
                product_id=product_id,
                quantity=max(0.0, quantity_change),
                config_id=config_id,
                scenario_id=scenario_id,
                as_of_date=date.today(),
            )
            self.db.add(inv_level)
        else:
            # Update existing record
            inv_level.quantity = max(0.0, inv_level.quantity + quantity_change)
            inv_level.as_of_date = date.today()

        await self.db.flush()
        await self.db.refresh(inv_level)

        return inv_level

    # ========================================================================
    # Customer Order Fulfillment (FIFO with Priority)
    # ========================================================================

    async def fulfill_customer_orders_fifo(
        self,
        site_id: int,
        product_id: str,
        scenario_id: Optional[int] = None,
        config_id: Optional[int] = None,
        current_round: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Fulfill customer orders using FIFO with priority support.

        Process orders in priority order (VIP > HIGH > STANDARD > LOW),
        then FIFO within each priority level. Allocate available inventory
        and create TransferOrders for shipments.

        Args:
            site_id: Fulfillment site ID
            product_id: Product to fulfill
            scenario_id: Scenario ID
            config_id: Supply chain configuration ID
            current_round: Current round number (for TO arrival calculation)

        Returns:
            Dictionary with fulfillment summary:
            {
                'orders_fulfilled': int,
                'quantity_shipped': float,
                'backlog_remaining': float,
                'transfer_orders_created': List[TransferOrder]
            }
        """
        # Get unfulfilled orders (FIFO + priority)
        orders = await self.order_mgmt.get_unfulfilled_customer_orders(
            site_id=site_id,
            scenario_id=scenario_id,
            priority_order=True,
        )

        # Filter by product_id
        orders = [o for o in orders if o.product_id == product_id]

        if not orders:
            return {
                'orders_fulfilled': 0,
                'quantity_shipped': 0.0,
                'backlog_remaining': 0.0,
                'transfer_orders_created': [],
            }

        # Calculate ATP
        atp = await self.calculate_available_to_ship(
            site_id=site_id,
            product_id=product_id,
            config_id=config_id,
            scenario_id=scenario_id,
        )

        orders_fulfilled = 0
        quantity_shipped = 0.0
        transfer_orders_created = []

        # Fulfill orders in FIFO+priority order
        for order in orders:
            if atp <= 0:
                break

            # Calculate unfulfilled quantity
            unfulfilled_qty = order.ordered_quantity - order.shipped_quantity

            if unfulfilled_qty <= 0:
                continue

            # Allocate available quantity
            ship_qty = min(unfulfilled_qty, atp)

            # Update order fulfillment
            updated_order = await self.order_mgmt.update_order_fulfillment(
                order_id=order.id,
                shipped_quantity=ship_qty,
                promised_delivery_date=order.requested_delivery_date,
            )

            # Create TransferOrder for shipment
            to_number = f"TO-{order.order_id}-{order.line_number}-{current_round or 0}"

            # Calculate arrival round (1-week lead time for simulation)
            arrival_round = (current_round + 1) if current_round is not None else None
            estimated_delivery = order.requested_delivery_date or (date.today() + timedelta(weeks=1))

            transfer_order = await self.order_mgmt.create_transfer_order(
                to_number=to_number,
                source_site_id=site_id,
                destination_site_id=order.market_demand_site_id or site_id,
                product_id=product_id,
                quantity=ship_qty,
                estimated_delivery_date=estimated_delivery,
                config_id=config_id,
                scenario_id=scenario_id,
                order_round=current_round,
                arrival_round=arrival_round,
                source_po_id=None,  # Not applicable for customer orders
            )

            transfer_orders_created.append(transfer_order)

            # Reduce inventory
            await self.update_inventory_level(
                site_id=site_id,
                product_id=product_id,
                quantity_change=-ship_qty,
                config_id=config_id,
                scenario_id=scenario_id,
            )

            # Update ATP and counters
            atp -= ship_qty
            quantity_shipped += ship_qty

            if updated_order.status == "FULFILLED":
                orders_fulfilled += 1

        # Calculate remaining backlog
        backlog_remaining = await self.order_mgmt.get_backlog_for_site(
            site_id=site_id,
            product_id=product_id,
            scenario_id=scenario_id,
        )

        return {
            'orders_fulfilled': orders_fulfilled,
            'quantity_shipped': quantity_shipped,
            'backlog_remaining': backlog_remaining,
            'transfer_orders_created': transfer_orders_created,
        }

    async def fulfill_customer_backlog(
        self,
        site_id: int,
        product_id: str,
        scenario_id: Optional[int] = None,
        config_id: Optional[int] = None,
        current_round: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Specifically process backlogged customer orders.

        This is a convenience method that filters for orders with
        backlog_quantity > 0 and attempts fulfillment.

        Args:
            site_id: Fulfillment site ID
            product_id: Product to fulfill
            scenario_id: Scenario ID
            config_id: Supply chain configuration ID
            current_round: Current round number

        Returns:
            Same as fulfill_customer_orders_fifo()
        """
        return await self.fulfill_customer_orders_fifo(
            site_id=site_id,
            product_id=product_id,
            scenario_id=scenario_id,
            config_id=config_id,
            current_round=current_round,
        )

    # ========================================================================
    # Purchase Order Fulfillment (Process POs as Sales Orders)
    # ========================================================================

    async def fulfill_purchase_orders(
        self,
        supplier_site_id: int,
        product_id: str,
        scenario_id: Optional[int] = None,
        config_id: Optional[int] = None,
        current_round: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Fulfill purchase orders from downstream sites.

        In simulation, upstream sites (Wholesaler, Distributor, Manufacturer)
        receive POs from downstream sites. These POs are treated as sales orders
        and fulfilled using available inventory.

        Args:
            supplier_site_id: Supplier site ID (e.g., Wholesaler)
            product_id: Product to fulfill
            scenario_id: Scenario ID
            config_id: Supply chain configuration ID
            current_round: Current round number

        Returns:
            Dictionary with fulfillment summary:
            {
                'pos_fulfilled': int,
                'quantity_shipped': float,
                'transfer_orders_created': List[TransferOrder]
            }
        """
        # Get unfulfilled POs for this supplier
        pos = await self.order_mgmt.get_unfulfilled_purchase_orders(
            supplier_site_id=supplier_site_id,
            scenario_id=scenario_id,
        )

        if not pos:
            return {
                'pos_fulfilled': 0,
                'quantity_shipped': 0.0,
                'transfer_orders_created': [],
            }

        # Calculate ATP
        atp = await self.calculate_available_to_ship(
            site_id=supplier_site_id,
            product_id=product_id,
            config_id=config_id,
            scenario_id=scenario_id,
        )

        pos_fulfilled = 0
        quantity_shipped = 0.0
        transfer_orders_created = []

        # Fulfill POs in FIFO order
        for po in pos:
            if atp <= 0:
                break

            # Get line items
            if not po.line_items:
                continue

            # Simulation: only 1 line item per PO
            po_line = po.line_items[0]

            if po_line.product_id != product_id:
                continue

            # Calculate unfulfilled quantity
            unfulfilled_qty = po_line.quantity - po_line.shipped_quantity

            if unfulfilled_qty <= 0:
                continue

            # Allocate available quantity
            ship_qty = min(unfulfilled_qty, atp)

            # Update PO shipment status
            updated_po = await self.order_mgmt.update_po_shipment(
                po_id=po.id,
                line_number=po_line.line_number,
                shipped_quantity=ship_qty,
                promised_delivery_date=po.requested_delivery_date,
            )

            # Create TransferOrder for shipment
            to_number = f"TO-PO-{po.po_number}-{current_round or 0}"

            # Calculate arrival round (lead time from lane)
            arrival_round = (current_round + 1) if current_round is not None else None
            estimated_delivery = po.requested_delivery_date or (date.today() + timedelta(weeks=1))

            transfer_order = await self.order_mgmt.create_transfer_order(
                to_number=to_number,
                source_site_id=supplier_site_id,
                destination_site_id=po.destination_site_id,
                product_id=product_id,
                quantity=ship_qty,
                estimated_delivery_date=estimated_delivery,
                config_id=config_id,
                scenario_id=scenario_id,
                order_round=current_round,
                arrival_round=arrival_round,
                source_po_id=po.id,
            )

            transfer_orders_created.append(transfer_order)

            # Reduce inventory
            await self.update_inventory_level(
                site_id=supplier_site_id,
                product_id=product_id,
                quantity_change=-ship_qty,
                config_id=config_id,
                scenario_id=scenario_id,
            )

            # Update ATP and counters
            atp -= ship_qty
            quantity_shipped += ship_qty

            if updated_po.status == "SHIPPED":
                pos_fulfilled += 1

        return {
            'pos_fulfilled': pos_fulfilled,
            'quantity_shipped': quantity_shipped,
            'transfer_orders_created': transfer_orders_created,
        }

    # ========================================================================
    # Shipment Receipt (Process Arriving TransferOrders)
    # ========================================================================

    async def receive_shipments(
        self,
        scenario_id: int,
        arrival_round: int,
        config_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Process all arriving TransferOrders for a specific round.

        Updates inventory levels and marks TOs as received.

        Args:
            scenario_id: Scenario ID
            arrival_round: Round number when shipments arrive
            config_id: Supply chain configuration ID

        Returns:
            Dictionary with receipt summary:
            {
                'transfer_orders_received': int,
                'total_quantity_received': float,
                'receipts_by_site': Dict[int, float]
            }
        """
        # Get arriving TOs
        arriving_tos = await self.order_mgmt.get_arriving_transfer_orders(
            scenario_id=scenario_id,
            arrival_round=arrival_round,
        )

        if not arriving_tos:
            return {
                'transfer_orders_received': 0,
                'total_quantity_received': 0.0,
                'receipts_by_site': {},
            }

        tos_received = 0
        total_qty_received = 0.0
        receipts_by_site: Dict[int, float] = {}

        for to in arriving_tos:
            # Get line items
            if not to.line_items:
                continue

            # Simulation: only 1 line item per TO
            to_line = to.line_items[0]

            # Update inventory at destination site
            await self.update_inventory_level(
                site_id=to.destination_site_id,
                product_id=to_line.product_id,
                quantity_change=to_line.quantity,
                config_id=config_id,
                scenario_id=scenario_id,
            )

            # Mark TO as received
            await self.order_mgmt.receive_transfer_order(to_id=to.id)

            # Update counters
            tos_received += 1
            total_qty_received += to_line.quantity

            if to.destination_site_id not in receipts_by_site:
                receipts_by_site[to.destination_site_id] = 0.0
            receipts_by_site[to.destination_site_id] += to_line.quantity

        return {
            'transfer_orders_received': tos_received,
            'total_quantity_received': total_qty_received,
            'receipts_by_site': receipts_by_site,
        }

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

    # ========================================================================
    # Powell Integration Methods (Allocation-Based ATP)
    # ========================================================================

    async def fulfill_with_allocations(
        self,
        site_id: int,
        product_id: str,
        config_id: int,
        scenario_id: Optional[int] = None,
        current_round: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Fulfill customer orders using Powell allocation-based ATP.

        This method uses the Powell AATP (Allocated ATP) approach:
        1. Check allocation availability for each order's priority
        2. Consume from appropriate allocation buckets
        3. Create transfer orders for shipments
        4. Log decisions for TRM training

        Falls back to standard FIFO fulfillment if Powell integration
        is not available.

        Args:
            site_id: Fulfillment site ID
            product_id: Product to fulfill
            config_id: Supply chain configuration ID
            scenario_id: Scenario ID (optional)
            current_round: Current round number

        Returns:
            Dictionary with fulfillment summary including Powell metrics
        """
        powell = await self._get_powell_integration()

        if not powell:
            # Fall back to standard FIFO fulfillment
            logger.debug("Powell integration not available, using standard FIFO")
            return await self.fulfill_customer_orders_fifo(
                site_id=site_id,
                product_id=product_id,
                scenario_id=scenario_id,
                config_id=config_id,
                current_round=current_round,
            )

        # Get unfulfilled orders (FIFO + priority)
        orders = await self.order_mgmt.get_unfulfilled_customer_orders(
            site_id=site_id,
            scenario_id=scenario_id,
            priority_order=True,
        )

        # Filter by product_id
        orders = [o for o in orders if o.product_id == product_id]

        if not orders:
            return {
                'orders_fulfilled': 0,
                'quantity_shipped': 0.0,
                'backlog_remaining': 0.0,
                'transfer_orders_created': [],
                'powell_decisions': [],
            }

        orders_fulfilled = 0
        quantity_shipped = 0.0
        transfer_orders_created = []
        powell_decisions = []

        # Map priority codes to numeric priorities
        priority_map = {
            'VIP': 1,
            'HIGH': 2,
            'STANDARD': 3,
            'LOW': 4,
        }

        # Process each order using Powell allocation-based ATP
        for order in orders:
            # Calculate unfulfilled quantity
            unfulfilled_qty = order.ordered_quantity - order.shipped_quantity

            if unfulfilled_qty <= 0:
                continue

            # Get priority (default to STANDARD if not set)
            priority = priority_map.get(order.priority_code, 3)

            # Check allocation availability using Powell
            atp_result = await powell.check_atp_with_allocations(
                config_id=config_id,
                product_id=product_id,
                location_id=str(site_id),
                requested_qty=unfulfilled_qty,
                order_priority=priority,
                order_id=order.order_id,
            )

            powell_decisions.append({
                'order_id': order.order_id,
                'requested_qty': unfulfilled_qty,
                'priority': priority,
                'can_fulfill': atp_result.success and atp_result.recommendation.can_fulfill if atp_result.recommendation else False,
                'confidence': atp_result.confidence,
                'auto_executed': atp_result.auto_executed,
            })

            if not atp_result.success:
                logger.warning(f"ATP check failed for order {order.order_id}: {atp_result.reason}")
                continue

            response = atp_result.recommendation
            if not response or not response.can_fulfill:
                continue

            # Commit allocation (consume from bucket)
            commit_result = await powell.commit_atp(
                config_id=config_id,
                product_id=product_id,
                location_id=str(site_id),
                order_priority=priority,
                consume_qty=response.promised_qty,
                order_id=order.order_id,
            )

            if not commit_result.success:
                logger.warning(f"ATP commit failed for order {order.order_id}: {commit_result.reason}")
                continue

            # Update order fulfillment
            ship_qty = response.promised_qty
            updated_order = await self.order_mgmt.update_order_fulfillment(
                order_id=order.id,
                shipped_quantity=ship_qty,
                promised_delivery_date=order.requested_delivery_date,
            )

            # Create TransferOrder for shipment
            to_number = f"TO-{order.order_id}-{order.line_number}-{current_round or 0}"
            arrival_round = (current_round + 1) if current_round is not None else None
            estimated_delivery = order.requested_delivery_date or (date.today() + timedelta(weeks=1))

            transfer_order = await self.order_mgmt.create_transfer_order(
                to_number=to_number,
                source_site_id=site_id,
                destination_site_id=order.market_demand_site_id or site_id,
                product_id=product_id,
                quantity=ship_qty,
                estimated_delivery_date=estimated_delivery,
                config_id=config_id,
                scenario_id=scenario_id,
                order_round=current_round,
                arrival_round=arrival_round,
                source_po_id=None,
            )

            transfer_orders_created.append(transfer_order)

            # Reduce inventory
            await self.update_inventory_level(
                site_id=site_id,
                product_id=product_id,
                quantity_change=-ship_qty,
                config_id=config_id,
                scenario_id=scenario_id,
            )

            quantity_shipped += ship_qty

            if updated_order.status == "FULFILLED":
                orders_fulfilled += 1

        # Calculate remaining backlog
        backlog_remaining = await self.order_mgmt.get_backlog_for_site(
            site_id=site_id,
            product_id=product_id,
            scenario_id=scenario_id,
        )

        return {
            'orders_fulfilled': orders_fulfilled,
            'quantity_shipped': quantity_shipped,
            'backlog_remaining': backlog_remaining,
            'transfer_orders_created': transfer_orders_created,
            'powell_decisions': powell_decisions,
            'allocation_based': True,
        }

    async def check_powell_atp(
        self,
        config_id: int,
        site_id: int,
        product_id: str,
        requested_qty: float,
        order_priority: int = 3,
        order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check ATP using Powell allocation-based approach.

        This is a convenience method for ATP checks without fulfillment.
        Useful for order promising and availability inquiries.

        Args:
            config_id: Supply chain configuration ID
            site_id: Site to check
            product_id: Product to check
            requested_qty: Quantity requested
            order_priority: Priority level (1=VIP, 2=HIGH, 3=STANDARD, 4=LOW)
            order_id: Optional order ID for logging

        Returns:
            Dictionary with ATP check result:
            {
                'available': bool,
                'available_qty': float,
                'confidence': float,
                'consumption_breakdown': dict,
                'method': 'powell' or 'standard'
            }
        """
        powell = await self._get_powell_integration()

        if not powell:
            # Fall back to standard ATP calculation
            atp = await self.calculate_available_to_ship(
                site_id=site_id,
                product_id=product_id,
                config_id=config_id,
            )
            return {
                'available': atp >= requested_qty,
                'available_qty': min(atp, requested_qty),
                'confidence': 1.0,
                'consumption_breakdown': {},
                'method': 'standard',
            }

        result = await powell.check_atp_with_allocations(
            config_id=config_id,
            product_id=product_id,
            location_id=str(site_id),
            requested_qty=requested_qty,
            order_priority=order_priority,
            order_id=order_id,
        )

        if result.success and result.recommendation:
            response = result.recommendation
            return {
                'available': response.can_fulfill,
                'available_qty': response.promised_qty,
                'confidence': response.confidence,
                'consumption_breakdown': response.consumption_breakdown,
                'method': 'powell',
            }
        else:
            return {
                'available': False,
                'available_qty': 0.0,
                'confidence': 0.0,
                'consumption_breakdown': {},
                'method': 'powell',
                'error': result.reason,
            }
