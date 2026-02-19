"""
Order Promising Engine - SC Execution

Implements Available-to-Promise (ATP) logic for order fulfillment.
This is the core execution logic that The Beer Game uses to fulfill demand.

Reference: SC Order Promising
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.sc_entities import InvLevel, Product, OutboundOrderLine, SourcingRules
from app.models.supply_chain_config import Site
from app.models.purchase_order import PurchaseOrder
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.compatibility import Item, ProductSiteConfig  # Temporary compat


@dataclass
class ATPResult:
    """Available-to-Promise calculation result"""
    site_id: int  # Changed to int (node.id) for SC compliance
    item_id: int  # Changed to int (item.id) for SC compliance
    requested_qty: float
    available_qty: float
    promised_qty: float
    shortfall_qty: float
    can_fulfill: bool
    allocated_qty: float = 0.0
    backorder_qty: float = 0.0


@dataclass
class ShipmentRecord:
    """Record of a shipment from one site to another"""
    from_site_id: int  # Changed to int (node.id) for SC compliance
    to_site_id: int  # Changed to int (node.id) for SC compliance
    item_id: int  # Changed to int (item.id) for SC compliance
    shipped_qty: float
    shipment_date: date
    arrival_date: date
    order_id: str
    shipment_id: Optional[str] = None


class OrderPromisingEngine:
    """
    Order Promising Engine implementing ATP (Available-to-Promise) logic.

    This engine fulfills demand by:
    1. Checking inventory availability (ATP)
    2. Allocating inventory to orders
    3. Creating shipment records
    4. Updating backorders for unfulfilled demand

    The Beer Game uses this engine each round to fulfill:
    - Market demand (for Retailer)
    - Downstream POs (for Wholesaler/Distributor/Factory)
    """

    def __init__(self, db: Session):
        """
        Initialize order promising engine.

        Args:
            db: Database session
        """
        self.db = db

    def calculate_atp(
        self,
        site_id: int,
        item_id: int,
        requested_qty: float
    ) -> ATPResult:
        """
        Calculate Available-to-Promise for a site-item combination.

        ATP = on_hand_qty - allocated_qty - safety_stock_qty

        Args:
            site_id: Node ID (Integer from nodes table)
            item_id: Item ID (Integer from items table)
            requested_qty: Quantity requested

        Returns:
            ATPResult with fulfillment details
        """
        # Get current inventory level
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.item_id == item_id
            )
        ).first()

        if not inv_level:
            # No inventory record exists
            return ATPResult(
                site_id=site_id,
                item_id=item_id,
                requested_qty=requested_qty,
                available_qty=0.0,
                promised_qty=0.0,
                shortfall_qty=requested_qty,
                can_fulfill=False,
                backorder_qty=requested_qty
            )

        # Calculate ATP (Available-to-Promise)
        # ATP = on_hand - allocated - safety_stock
        atp = (
            inv_level.on_hand_qty
            - inv_level.allocated_qty
            - inv_level.safety_stock_qty
        )
        atp = max(0.0, atp)  # Cannot be negative

        # Determine how much can be promised
        if atp >= requested_qty:
            # Full fulfillment
            promised_qty = requested_qty
            shortfall_qty = 0.0
            can_fulfill = True
        else:
            # Partial fulfillment
            promised_qty = atp
            shortfall_qty = requested_qty - atp
            can_fulfill = False

        return ATPResult(
            site_id=site_id,
            item_id=item_id,
            requested_qty=requested_qty,
            available_qty=atp,
            promised_qty=promised_qty,
            shortfall_qty=shortfall_qty,
            can_fulfill=can_fulfill,
            allocated_qty=inv_level.allocated_qty,
            backorder_qty=shortfall_qty
        )

    def promise_order(
        self,
        site_id: int,
        item_id: int,
        order_id: str,
        requested_qty: float,
        requested_date: date,
        to_site_id: Optional[int] = None,
        lead_time_days: int = 0,
        game_id: Optional[int] = None,
        round_number: Optional[int] = None
    ) -> Tuple[ATPResult, Optional[TransferOrder]]:
        """
        Promise an order and create Transfer Order if fulfilled.

        This method:
        1. Calculates ATP
        2. Allocates inventory
        3. Creates TransferOrder entity (SC compliance)
        4. Updates inventory levels
        5. Records backorder if needed

        Args:
            site_id: Fulfilling node ID (Integer from nodes table)
            item_id: Item ID (Integer from items table)
            order_id: Order identifier
            requested_qty: Quantity requested
            requested_date: Requested delivery date
            to_site_id: Destination node ID (Integer, optional)
            lead_time_days: Shipment lead time (default: 0)
            game_id: Game ID (optional)
            round_number: Round number (optional)

        Returns:
            Tuple of (ATPResult, TransferOrder or None)
        """
        # Calculate ATP
        atp_result = self.calculate_atp(site_id, item_id, requested_qty)

        if atp_result.promised_qty == 0:
            # Cannot fulfill any quantity
            self._update_backorder(site_id, item_id, requested_qty)
            return atp_result, None

        # Allocate inventory
        self._allocate_inventory(
            site_id, item_id, atp_result.promised_qty
        )

        # Create Transfer Order (SC entity)
        # Note: destination defaults to None for market demand (no physical destination node)
        transfer_order = self._create_transfer_order(
            source_site_id=site_id,
            destination_site_id=to_site_id,  # Integer node ID or None for market
            item_id=item_id,
            quantity=atp_result.promised_qty,
            order_date=datetime.now().date(),
            shipment_date=datetime.now().date(),
            estimated_delivery_date=requested_date + timedelta(days=lead_time_days),
            game_id=game_id,
            order_round=round_number,
            arrival_round=round_number + (lead_time_days // 7) if round_number else None
        )

        # Update inventory (reduce on-hand, reduce allocated)
        self._ship_inventory(site_id, item_id, atp_result.promised_qty)

        # Update in-transit at destination (if destination exists)
        if to_site_id:
            self._update_in_transit(to_site_id, item_id, atp_result.promised_qty)

        # Update backorder if partial fulfillment
        if atp_result.shortfall_qty > 0:
            self._update_backorder(site_id, item_id, atp_result.shortfall_qty)
        else:
            # Clear backorder if fully fulfilled
            self._clear_backorder(site_id, item_id)

        return atp_result, transfer_order

    def fulfill_market_demand(
        self,
        site_id: int,
        item_id: int,
        demand_qty: float,
        demand_date: date,
        game_id: Optional[int] = None,
        round_number: Optional[int] = None
    ) -> Tuple[ATPResult, Optional[TransferOrder]]:
        """
        Fulfill market demand (Beer Game: Retailer fulfilling customer orders).

        Args:
            site_id: Retailer node ID (Integer from nodes table)
            item_id: Item ID (Integer from items table)
            demand_qty: Market demand quantity
            demand_date: Demand date
            game_id: Game ID (optional)
            round_number: Round number (optional)

        Returns:
            Tuple of (ATPResult, TransferOrder or None)
        """
        order_id = f"MARKET-{game_id or 0}-R{round_number or 0}"

        return self.promise_order(
            site_id=site_id,
            item_id=item_id,
            order_id=order_id,
            requested_qty=demand_qty,
            requested_date=demand_date,
            to_site_id="MARKET",
            lead_time_days=0,  # Immediate delivery to market
            game_id=game_id,
            round_number=round_number
        )

    def fulfill_purchase_order(
        self,
        po: PurchaseOrder
    ) -> Tuple[ATPResult, Optional[TransferOrder]]:
        """
        Fulfill a purchase order from downstream site.

        Args:
            po: Purchase order to fulfill

        Returns:
            Tuple of (ATPResult, TransferOrder or None)
        """
        # Get lead time from PO or default
        if po.requested_delivery_date and po.order_date:
            lead_time_days = (po.requested_delivery_date - po.order_date).days
        else:
            lead_time_days = 14  # Default 2 weeks

        return self.promise_order(
            site_id=po.supplier_site_id,
            item_id=po.product_id,
            order_id=po.po_number,
            requested_qty=po.quantity,
            requested_date=po.requested_delivery_date or datetime.now().date(),
            to_site_id=po.destination_site_id,
            lead_time_days=lead_time_days,
            game_id=po.game_id,
            round_number=po.round_number
        )

    def process_round_demand(
        self,
        game_id: int,
        round_number: int
    ) -> List[Tuple[ATPResult, Optional[TransferOrder]]]:
        """
        Process all demand for a Beer Game round.

        This executes order promising for:
        1. Market demand (Retailer)
        2. All POs due this round (Wholesaler/Distributor/Factory)

        Args:
            game_id: Game ID
            round_number: Current round number

        Returns:
            List of (ATPResult, TransferOrder) tuples
        """
        results = []

        # 1. Process market demand (outbound orders)
        outbound_orders = self.db.query(OutboundOrderLine).filter(
            and_(
                OutboundOrderLine.game_id == game_id,
                OutboundOrderLine.round_number == round_number
            )
        ).all()

        for order in outbound_orders:
            atp_result, transfer_order = self.fulfill_market_demand(
                site_id=order.site_id,
                item_id=order.product_id,
                demand_qty=order.ordered_quantity,
                demand_date=order.requested_delivery_date,
                game_id=game_id,
                round_number=round_number
            )
            results.append((atp_result, transfer_order))

        # 2. Process upstream POs (inter-site orders)
        # Get POs that should be fulfilled this round
        purchase_orders = self.db.query(PurchaseOrder).filter(
            and_(
                PurchaseOrder.game_id == game_id,
                PurchaseOrder.round_number == round_number,
                PurchaseOrder.status == "APPROVED"
            )
        ).all()

        for po in purchase_orders:
            atp_result, transfer_order = self.fulfill_purchase_order(po)

            # Update PO status
            if atp_result.can_fulfill:
                po.status = "SHIPPED"
                po.sent_at = datetime.now()
            else:
                po.status = "PARTIAL"  # Partially fulfilled

            results.append((atp_result, transfer_order))

        self.db.commit()
        return results

    def process_arriving_transfers(
        self,
        game_id: int,
        round_number: int
    ) -> List[TransferOrder]:
        """
        Process all Transfer Orders arriving in current round.

        Args:
            game_id: Game ID
            round_number: Current round number

        Returns:
            List of received TransferOrders
        """
        # Get TOs that are arriving this round
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

    def receive_transfer_order(self, to: TransferOrder) -> None:
        """
        Receive transfer order at destination site.

        Updates:
        1. in_transit_qty decreases at destination
        2. on_hand_qty increases at destination
        3. TO status = RECEIVED

        Args:
            to: Transfer order to receive
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

            # Mark line as received
            line.received_quantity = line.shipped_quantity

        # Update TO status
        to.status = "RECEIVED"
        to.actual_delivery_date = datetime.now().date()

        self.db.commit()

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _create_transfer_order(
        self,
        source_site_id: int,
        destination_site_id: Optional[int],
        item_id: int,
        quantity: float,
        order_date: date,
        shipment_date: date,
        estimated_delivery_date: date,
        game_id: Optional[int] = None,
        order_round: Optional[int] = None,
        arrival_round: Optional[int] = None
    ) -> TransferOrder:
        """
        Create Transfer Order entity (SC compliant).

        Args:
            source_site_id: Source node ID (Integer from nodes table)
            destination_site_id: Destination node ID (Integer from nodes table, None for market)
            item_id: Item ID (Integer from items table)
            quantity: Quantity to transfer
            order_date: Order date
            shipment_date: Shipment date
            estimated_delivery_date: Estimated delivery date
            game_id: Game ID (optional)
            order_round: Round when TO created (optional)
            arrival_round: Round when TO arrives (optional)

        Returns:
            Created TransferOrder
        """
        # Generate TO number
        timestamp = int(datetime.now().timestamp())
        to_number = f"TO-G{game_id or 0}-R{order_round or 0}-N{source_site_id}-{timestamp}"

        # Create TO with Integer IDs
        to = TransferOrder(
            to_number=to_number,
            source_site_id=source_site_id,  # Integer node ID
            destination_site_id=destination_site_id,  # Integer node ID or None
            status="IN_TRANSIT",  # Immediately in transit for Beer Game
            order_date=order_date,
            shipment_date=shipment_date,
            estimated_delivery_date=estimated_delivery_date,
            game_id=game_id,
            order_round=order_round,
            arrival_round=arrival_round,
            created_at=datetime.now()
        )
        self.db.add(to)
        self.db.flush()  # Get TO ID

        # Create TO line item
        to_line = TransferOrderLineItem(
            to_id=to.id,
            line_number=1,
            product_id=item_id,
            ordered_quantity=quantity,
            shipped_quantity=quantity,
            received_quantity=0.0,
            requested_delivery_date=estimated_delivery_date
        )
        self.db.add(to_line)
        self.db.commit()

        return to

    def _allocate_inventory(
        self,
        site_id: int,
        item_id: int,
        qty: float
    ) -> None:
        """Allocate inventory (reserve for shipment)."""
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.item_id == item_id
            )
        ).first()

        if inv_level:
            inv_level.allocated_qty += qty
            self.db.commit()

    def _ship_inventory(
        self,
        site_id: int,
        item_id: int,
        qty: float
    ) -> None:
        """
        Ship inventory (reduce on-hand and allocated).

        When shipment is created:
        - on_hand_qty decreases (inventory leaves)
        - allocated_qty decreases (no longer reserved)
        """
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.item_id == item_id
            )
        ).first()

        if inv_level:
            inv_level.on_hand_qty -= qty
            inv_level.allocated_qty -= qty

            # Ensure no negative values
            inv_level.on_hand_qty = max(0.0, inv_level.on_hand_qty)
            inv_level.allocated_qty = max(0.0, inv_level.allocated_qty)

            self.db.commit()

    def _update_backorder(
        self,
        site_id: int,
        item_id: int,
        qty: float
    ) -> None:
        """Update backorder quantity."""
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.item_id == item_id
            )
        ).first()

        if inv_level:
            inv_level.backorder_qty += qty
            self.db.commit()

    def _update_in_transit(
        self,
        site_id: int,
        item_id: int,
        qty: float
    ) -> None:
        """Update in-transit quantity at destination site."""
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.item_id == item_id
            )
        ).first()

        if inv_level:
            inv_level.in_transit_qty += qty
            self.db.commit()
        else:
            # Create inv_level if doesn't exist
            inv_level = InvLevel(
                site_id=site_id,
                item_id=item_id,
                on_hand_qty=0.0,
                backorder_qty=0.0,
                in_transit_qty=qty,
                allocated_qty=0.0,
                available_qty=0.0,
                safety_stock_qty=0.0,
                reorder_point_qty=0.0,
                min_qty=0.0,
                max_qty=1000.0
            )
            self.db.add(inv_level)
            self.db.commit()

    def _clear_backorder(
        self,
        site_id: int,
        item_id: int
    ) -> None:
        """Clear backorder (set to zero)."""
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.item_id == item_id
            )
        ).first()

        if inv_level:
            inv_level.backorder_qty = 0.0
            self.db.commit()

    def get_inventory_status(
        self,
        site_id: int,
        item_id: int
    ) -> Dict:
        """
        Get current inventory status for a site-item.

        Returns:
            Dictionary with SC inv_level fields
        """
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.item_id == item_id
            )
        ).first()

        if not inv_level:
            return {
                "site_id": site_id,
                "item_id": item_id,
                "on_hand_qty": 0.0,
                "backorder_qty": 0.0,
                "in_transit_qty": 0.0,
                "allocated_qty": 0.0,
                "available_qty": 0.0,
                "safety_stock_qty": 0.0,
            }

        # Calculate available quantity (ATP)
        available_qty = max(
            0.0,
            inv_level.on_hand_qty
            - inv_level.allocated_qty
            - inv_level.safety_stock_qty
        )

        return {
            "site_id": site_id,
            "item_id": item_id,
            "on_hand_qty": inv_level.on_hand_qty,
            "backorder_qty": inv_level.backorder_qty,
            "in_transit_qty": inv_level.in_transit_qty,
            "allocated_qty": inv_level.allocated_qty,
            "available_qty": available_qty,
            "safety_stock_qty": inv_level.safety_stock_qty,
            "reorder_point_qty": inv_level.reorder_point_qty,
            "min_qty": inv_level.min_qty,
            "max_qty": inv_level.max_qty,
        }
