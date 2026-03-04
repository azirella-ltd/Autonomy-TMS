"""
Order Promising Engine - SC Execution

Implements Available-to-Promise (ATP) logic for order fulfillment.
The simulation uses this core execution logic to fulfill demand.

Reference: SC Order Promising
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.sc_entities import InvLevel, OutboundOrderLine
from app.models.supply_chain_config import Site
from app.models.purchase_order import PurchaseOrder
from app.models.transfer_order import TransferOrder, TransferOrderLineItem


@dataclass
class ATPResult:
    """Available-to-Promise calculation result"""
    site_id: int
    product_id: str
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
    from_site_id: int
    to_site_id: Optional[int]
    product_id: str
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
    3. Creating Transfer Order entities for inter-site movements
    4. Updating backorders for unfulfilled demand

    For market demand (Retailer → customer), inventory is shipped directly
    without creating a TransferOrder (no physical destination site needed).

    The simulation uses this engine each round to fulfill:
    - Market demand (for Retailer)
    - Downstream POs (for Wholesaler/Distributor/Factory)
    """

    def __init__(self, db: Session):
        self.db = db

    def calculate_atp(
        self,
        site_id: int,
        product_id: str,
        requested_qty: float,
    ) -> ATPResult:
        """
        Calculate Available-to-Promise for a site-product combination.

        ATP = on_hand_qty - allocated_qty - safety_stock_qty

        Args:
            site_id: Site integer PK
            product_id: Product string PK
            requested_qty: Quantity requested

        Returns:
            ATPResult with fulfillment details
        """
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.product_id == product_id,
            )
        ).first()

        if not inv_level:
            return ATPResult(
                site_id=site_id,
                product_id=product_id,
                requested_qty=requested_qty,
                available_qty=0.0,
                promised_qty=0.0,
                shortfall_qty=requested_qty,
                can_fulfill=False,
                backorder_qty=requested_qty,
            )

        # ATP = on_hand - allocated - safety_stock (floor 0)
        atp = max(
            0.0,
            (inv_level.on_hand_qty or 0.0)
            - (inv_level.allocated_qty or 0.0)
            - (inv_level.safety_stock_qty or 0.0),
        )

        if atp >= requested_qty:
            promised_qty = requested_qty
            shortfall_qty = 0.0
            can_fulfill = True
        else:
            promised_qty = atp
            shortfall_qty = requested_qty - atp
            can_fulfill = False

        return ATPResult(
            site_id=site_id,
            product_id=product_id,
            requested_qty=requested_qty,
            available_qty=atp,
            promised_qty=promised_qty,
            shortfall_qty=shortfall_qty,
            can_fulfill=can_fulfill,
            allocated_qty=inv_level.allocated_qty or 0.0,
            backorder_qty=shortfall_qty,
        )

    def fulfill_market_demand(
        self,
        site_id: int,
        product_id: str,
        demand_qty: float,
        demand_date: date,
        scenario_id: Optional[int] = None,
        round_number: Optional[int] = None,
    ) -> ATPResult:
        """
        Fulfill market demand (e.g., Retailer fulfilling customer orders).

        For market demand there is no physical destination site, so we
        directly update inventory without creating a TransferOrder.

        Args:
            site_id: Retailer site integer PK
            product_id: Product string PK
            demand_qty: Market demand quantity
            demand_date: Demand date
            scenario_id: Scenario ID (optional)
            round_number: Round number (optional)

        Returns:
            ATPResult with fulfillment details
        """
        atp_result = self.calculate_atp(site_id, product_id, demand_qty)

        if atp_result.promised_qty > 0:
            # Allocate then ship (no TO for market demand)
            self._allocate_inventory(site_id, product_id, atp_result.promised_qty)
            self._ship_inventory(site_id, product_id, atp_result.promised_qty)

        if atp_result.shortfall_qty > 0:
            self._update_backorder(site_id, product_id, atp_result.shortfall_qty)
        else:
            self._clear_backorder(site_id, product_id)

        return atp_result

    def promise_order(
        self,
        site_id: int,
        product_id: str,
        order_id: str,
        requested_qty: float,
        requested_date: date,
        to_site_id: Optional[int] = None,
        lead_time_days: int = 0,
        scenario_id: Optional[int] = None,
        round_number: Optional[int] = None,
    ) -> Tuple[ATPResult, Optional[TransferOrder]]:
        """
        Promise an order and create Transfer Order if fulfilled (inter-site).

        This method:
        1. Calculates ATP
        2. Allocates inventory
        3. Creates TransferOrder entity (SC compliance)
        4. Updates inventory levels
        5. Records backorder if needed

        Args:
            site_id: Fulfilling site integer PK
            product_id: Product string PK
            order_id: Order identifier
            requested_qty: Quantity requested
            requested_date: Requested delivery date
            to_site_id: Destination site integer PK (required for inter-site)
            lead_time_days: Shipment lead time (default: 0)
            scenario_id: Scenario ID (optional)
            round_number: Round number (optional)

        Returns:
            Tuple of (ATPResult, TransferOrder or None)
        """
        atp_result = self.calculate_atp(site_id, product_id, requested_qty)

        if atp_result.promised_qty == 0:
            self._update_backorder(site_id, product_id, requested_qty)
            return atp_result, None

        # Allocate inventory
        self._allocate_inventory(site_id, product_id, atp_result.promised_qty)

        # Create Transfer Order (SC entity) for inter-site shipment
        transfer_order = self._create_transfer_order(
            source_site_id=site_id,
            destination_site_id=to_site_id,
            product_id=product_id,
            quantity=atp_result.promised_qty,
            order_date=datetime.now().date(),
            shipment_date=datetime.now().date(),
            estimated_delivery_date=requested_date + timedelta(days=lead_time_days),
            scenario_id=scenario_id,
            order_round=round_number,
            arrival_round=(round_number + (lead_time_days // 7)) if round_number is not None else None,
        )

        # Ship inventory (reduce on-hand and allocated)
        self._ship_inventory(site_id, product_id, atp_result.promised_qty)

        # Update in-transit at destination
        if to_site_id:
            self._update_in_transit(to_site_id, product_id, atp_result.promised_qty)

        # Handle backorders
        if atp_result.shortfall_qty > 0:
            self._update_backorder(site_id, product_id, atp_result.shortfall_qty)
        else:
            self._clear_backorder(site_id, product_id)

        return atp_result, transfer_order

    def fulfill_purchase_order(
        self,
        po: PurchaseOrder,
    ) -> Tuple[ATPResult, Optional[TransferOrder]]:
        """
        Fulfill a purchase order from downstream site.

        Args:
            po: Purchase order to fulfill (inter-site movement)

        Returns:
            Tuple of (ATPResult, TransferOrder or None)
        """
        # Determine product_id from first PO line item
        from app.models.purchase_order import PurchaseOrderLineItem
        line = (
            self.db.query(PurchaseOrderLineItem)
            .filter(PurchaseOrderLineItem.po_id == po.id)
            .order_by(PurchaseOrderLineItem.line_number)
            .first()
        )
        if not line:
            # Nothing to fulfill
            return ATPResult(
                site_id=po.supplier_site_id,
                product_id="",
                requested_qty=0.0,
                available_qty=0.0,
                promised_qty=0.0,
                shortfall_qty=0.0,
                can_fulfill=True,
            ), None

        order_qty = line.quantity or 0.0

        if po.requested_delivery_date and po.order_date:
            lead_time_days = (po.requested_delivery_date - po.order_date).days
        else:
            lead_time_days = 14

        return self.promise_order(
            site_id=po.supplier_site_id,
            product_id=line.product_id,
            order_id=po.po_number,
            requested_qty=order_qty,
            requested_date=po.requested_delivery_date or datetime.now().date(),
            to_site_id=po.destination_site_id,
            lead_time_days=lead_time_days,
            scenario_id=po.scenario_id,
            round_number=po.order_round,
        )

    def process_round_demand(
        self,
        scenario_id: int,
        round_number: int,
    ) -> List[Tuple[ATPResult, Optional[TransferOrder]]]:
        """
        Process all demand for a simulation round.

        This executes order promising for:
        1. Market demand (OutboundOrderLines for this scenario/round)
        2. Approved POs due this round (inter-site orders)

        Args:
            scenario_id: Scenario ID
            round_number: Current round number

        Returns:
            List of (ATPResult, TransferOrder or None) tuples
        """
        results = []

        # 1. Process market demand (outbound orders for this round)
        # OutboundOrderLine has no round_number field; filter by order_id pattern.
        # Idempotency guard: skip orders already FULFILLED or PARTIALLY_FULFILLED.
        order_id_prefix = f"MARKET-G{scenario_id}-R{round_number}"
        outbound_orders = self.db.query(OutboundOrderLine).filter(
            and_(
                OutboundOrderLine.scenario_id == scenario_id,
                OutboundOrderLine.order_id.like(f"{order_id_prefix}%"),
                OutboundOrderLine.status.notin_(["FULFILLED", "PARTIALLY_FULFILLED", "CANCELLED"]),
            )
        ).all()

        for order in outbound_orders:
            atp_result = self.fulfill_market_demand(
                site_id=order.site_id,
                product_id=order.product_id,
                demand_qty=order.ordered_quantity or 0.0,
                demand_date=order.requested_delivery_date or datetime.now().date(),
                scenario_id=scenario_id,
                round_number=round_number,
            )
            # Mark order as processed (idempotency guard)
            order.promised_quantity = atp_result.promised_qty
            order.shipped_quantity = atp_result.promised_qty
            order.backlog_quantity = atp_result.shortfall_qty
            order.status = "FULFILLED" if atp_result.can_fulfill else "PARTIALLY_FULFILLED"
            results.append((atp_result, None))

        # 2. Process approved POs (inter-site orders created this round)
        purchase_orders = self.db.query(PurchaseOrder).filter(
            and_(
                PurchaseOrder.scenario_id == scenario_id,
                PurchaseOrder.order_round == round_number,
                PurchaseOrder.status == "APPROVED",
            )
        ).all()

        for po in purchase_orders:
            atp_result, transfer_order = self.fulfill_purchase_order(po)

            if atp_result.can_fulfill:
                po.status = "SHIPPED"
                po.sent_at = datetime.now()
            else:
                po.status = "PARTIAL"

            results.append((atp_result, transfer_order))

        self.db.commit()
        return results

    def process_arriving_transfers(
        self,
        scenario_id: int,
        round_number: int,
    ) -> List[TransferOrder]:
        """
        Process all Transfer Orders arriving in current round.
        """
        arriving_tos = self.db.query(TransferOrder).filter(
            and_(
                TransferOrder.scenario_id == scenario_id,
                TransferOrder.arrival_round == round_number,
                TransferOrder.status == "IN_TRANSIT",
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
        """
        to_lines = self.db.query(TransferOrderLineItem).filter(
            TransferOrderLineItem.to_id == to.id
        ).all()

        for line in to_lines:
            if not to.destination_site_id:
                continue
            inv_level = self.db.query(InvLevel).filter(
                and_(
                    InvLevel.site_id == to.destination_site_id,
                    InvLevel.product_id == line.product_id,
                )
            ).first()

            if inv_level:
                shipped = line.shipped_quantity or 0.0
                inv_level.in_transit_qty = max(
                    0.0, (inv_level.in_transit_qty or 0.0) - shipped
                )
                inv_level.on_hand_qty = (inv_level.on_hand_qty or 0.0) + shipped

            line.received_quantity = line.shipped_quantity or 0.0

        to.status = "RECEIVED"
        to.actual_delivery_date = datetime.now().date()

        self.db.commit()

    def get_inventory_status(
        self,
        site_id: int,
        product_id: str,
    ) -> Dict:
        """
        Get current inventory status for a site-product.
        """
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.product_id == product_id,
            )
        ).first()

        if not inv_level:
            return {
                "site_id": site_id,
                "product_id": product_id,
                "on_hand_qty": 0.0,
                "backorder_qty": 0.0,
                "in_transit_qty": 0.0,
                "allocated_qty": 0.0,
                "available_qty": 0.0,
                "safety_stock_qty": 0.0,
            }

        available_qty = max(
            0.0,
            (inv_level.on_hand_qty or 0.0)
            - (inv_level.allocated_qty or 0.0)
            - (inv_level.safety_stock_qty or 0.0),
        )

        return {
            "site_id": site_id,
            "product_id": product_id,
            "on_hand_qty": inv_level.on_hand_qty or 0.0,
            "backorder_qty": inv_level.backorder_qty or 0.0,
            "in_transit_qty": inv_level.in_transit_qty or 0.0,
            "allocated_qty": inv_level.allocated_qty or 0.0,
            "available_qty": available_qty,
            "safety_stock_qty": inv_level.safety_stock_qty or 0.0,
        }

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _create_transfer_order(
        self,
        source_site_id: int,
        destination_site_id: Optional[int],
        product_id: str,
        quantity: float,
        order_date: date,
        shipment_date: date,
        estimated_delivery_date: date,
        scenario_id: Optional[int] = None,
        order_round: Optional[int] = None,
        arrival_round: Optional[int] = None,
    ) -> TransferOrder:
        """
        Create Transfer Order entity (SC compliant).

        If destination_site_id is None (market demand), returns without creating
        a TO since TransferOrder.destination_site_id is NOT NULL.
        """
        if destination_site_id is None:
            raise ValueError(
                "destination_site_id required for TransferOrder; "
                "use fulfill_market_demand() for market shipments."
            )

        timestamp = int(datetime.now().timestamp())
        to_number = (
            f"TO-G{scenario_id or 0}-R{order_round or 0}"
            f"-N{source_site_id}-{timestamp}"
        )

        to = TransferOrder(
            to_number=to_number,
            source_site_id=source_site_id,
            destination_site_id=destination_site_id,
            status="IN_TRANSIT",
            order_date=order_date,
            shipment_date=shipment_date,
            estimated_delivery_date=estimated_delivery_date,
            scenario_id=scenario_id,
            order_round=order_round,
            arrival_round=arrival_round,
            created_at=datetime.now(),
        )
        self.db.add(to)
        self.db.flush()

        to_line = TransferOrderLineItem(
            to_id=to.id,
            line_number=1,
            product_id=product_id,
            quantity=quantity,
            shipped_quantity=quantity,
            received_quantity=0.0,
            requested_ship_date=shipment_date,
            requested_delivery_date=estimated_delivery_date,
        )
        self.db.add(to_line)
        self.db.commit()

        return to

    def _allocate_inventory(self, site_id: int, product_id: str, qty: float) -> None:
        """Allocate inventory (reserve for shipment)."""
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.product_id == product_id,
            )
        ).first()
        if inv_level:
            inv_level.allocated_qty = (inv_level.allocated_qty or 0.0) + qty
            self.db.commit()

    def _ship_inventory(self, site_id: int, product_id: str, qty: float) -> None:
        """Ship inventory (reduce on-hand and allocated)."""
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.product_id == product_id,
            )
        ).first()
        if inv_level:
            inv_level.on_hand_qty = max(
                0.0, (inv_level.on_hand_qty or 0.0) - qty
            )
            inv_level.allocated_qty = max(
                0.0, (inv_level.allocated_qty or 0.0) - qty
            )
            self.db.commit()

    def _update_backorder(self, site_id: int, product_id: str, qty: float) -> None:
        """Accumulate backorder quantity."""
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.product_id == product_id,
            )
        ).first()
        if inv_level:
            inv_level.backorder_qty = (inv_level.backorder_qty or 0.0) + qty
            self.db.commit()

    def _clear_backorder(self, site_id: int, product_id: str) -> None:
        """Clear backorder (set to zero when fully fulfilled)."""
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.product_id == product_id,
            )
        ).first()
        if inv_level:
            inv_level.backorder_qty = 0.0
            self.db.commit()

    def _update_in_transit(self, site_id: int, product_id: str, qty: float) -> None:
        """Update in-transit quantity at destination site."""
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.product_id == product_id,
            )
        ).first()

        if inv_level:
            inv_level.in_transit_qty = (inv_level.in_transit_qty or 0.0) + qty
            self.db.commit()
        else:
            inv_level = InvLevel(
                site_id=site_id,
                product_id=product_id,
                on_hand_qty=0.0,
                backorder_qty=0.0,
                in_transit_qty=qty,
                allocated_qty=0.0,
                available_qty=0.0,
                reserved_qty=0.0,
                safety_stock_qty=0.0,
            )
            self.db.add(inv_level)
            self.db.commit()
