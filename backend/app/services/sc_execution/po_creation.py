"""
Purchase Order Creation - SC Execution

Creates purchase orders based on agent decisions and sourcing rules.
This is how The Beer Game agents place orders upstream.

Reference: SC Purchase Order Creation
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
from app.models.sc_entities import SourcingRules, InvLevel, Product
from app.models.supply_chain_config import Site
from .site_id_mapper import SimulationIdMapper


class PurchaseOrderCreator:
    """
    Purchase Order Creator implementing SC PO creation logic.

    This creator:
    1. Reads sourcing rules to find upstream supplier
    2. Creates purchase order based on agent decision
    3. Updates in_transit_qty in inv_level
    4. Tracks arrival round for Beer Game

    The Beer Game uses this each round when agents decide order quantities.
    """

    def __init__(self, db: Session):
        """
        Initialize PO creator.

        Args:
            db: Database session
        """
        self.db = db

    def create_purchase_order(
        self,
        destination_site_id: int,
        item_id: int,
        order_qty: float,
        order_date: date,
        game_id: Optional[int] = None,
        round_number: Optional[int] = None,
        company_id: str = "company_001",
        auto_approve: bool = True
    ) -> PurchaseOrder:
        """
        Create purchase order to upstream supplier (SC compliant).

        Steps:
        1. Find sourcing rule (who is upstream supplier?)
        2. Calculate arrival date (lead time)
        3. Create PO record
        4. Update in_transit_qty
        5. Create PO line item

        Args:
            destination_site_id: Ordering node ID (Integer from nodes table)
            item_id: Item ID (Integer from items table)
            order_qty: Quantity to order (from agent decision)
            order_date: Order date
            game_id: Game ID (optional)
            round_number: Round number when order is placed (optional)
            company_id: Company ID
            auto_approve: Auto-approve PO (default: True for Beer Game)

        Returns:
            Created PurchaseOrder
        """
        # Find sourcing rule to determine upstream supplier
        sourcing_rule = self._get_sourcing_rule(destination_site_id, item_id)

        if not sourcing_rule:
            raise ValueError(
                f"No sourcing rule found for site {destination_site_id}, "
                f"item {item_id}"
            )

        # Calculate delivery dates
        lead_time_days = sourcing_rule.lead_time_days or 14
        requested_delivery_date = order_date + timedelta(days=lead_time_days)

        # Calculate arrival round (for Beer Game)
        arrival_round = None
        if round_number is not None:
            # Assuming 1 round = 1 week, lead time in weeks
            lead_time_rounds = lead_time_days // 7
            arrival_round = round_number + lead_time_rounds

        # Generate PO number
        po_number = self._generate_po_number(
            game_id, round_number, destination_site_id
        )

        # Create PO
        po = PurchaseOrder(
            po_number=po_number,
            supplier_site_id=sourcing_rule.source_site_id,
            destination_site_id=destination_site_id,
            company_id=company_id,
            order_type="po",
            status="APPROVED" if auto_approve else "DRAFT",
            order_date=order_date,
            requested_delivery_date=requested_delivery_date,
            game_id=game_id,
            round_number=round_number,
            arrival_round=arrival_round,
            created_at=datetime.now()
        )

        if auto_approve:
            po.approved_at = datetime.now()

        self.db.add(po)
        self.db.flush()  # Get PO ID

        # Create PO line item
        po_line = PurchaseOrderLineItem(
            po_id=po.id,
            line_number=1,
            product_id=item_id,
            ordered_quantity=order_qty,
            unit_price=0.0,  # Not tracked in Beer Game
            line_total=0.0,
            requested_delivery_date=requested_delivery_date
        )
        self.db.add(po_line)

        # Update in_transit_qty in inv_level
        self._update_in_transit(destination_site_id, item_id, order_qty)

        self.db.commit()

        return po

    def create_simulation_orders(
        self,
        game_id: int,
        round_number: int,
        order_decisions: Dict[str, float],
        config_id: int
    ) -> List[PurchaseOrder]:
        """
        Create POs for all sites in a simulation based on agent decisions.

        Args:
            game_id: Game ID
            round_number: Current round number
            order_decisions: Dict mapping site_name to order_qty
                Example: {
                    "retailer_001": 12.0,
                    "wholesaler_001": 15.0,
                    "distributor_001": 18.0
                }
            config_id: Supply chain configuration ID

        Returns:
            List of created PurchaseOrders
        """
        pos = []
        order_date = datetime.now().date()

        # Initialize ID mapper
        mapper = SimulationIdMapper(self.db, config_id)

        for site_name, order_qty in order_decisions.items():
            if order_qty <= 0:
                continue  # No order

            # Map site name to site ID
            site_id = mapper.get_site_id(site_name)
            if not site_id:
                print(f"Warning: Site '{site_name}' not found, skipping PO creation")
                continue

            # Check if site is Manufacturer (infinite supply, no PO needed)
            site = self.db.query(Site).filter(Site.id == site_id).first()
            if site and site.master_type == "manufacturer":
                continue  # Manufacturers don't place orders

            # Get product ID (Beer Game uses single product)
            product_id = mapper.get_product_id("Cases")
            if not product_id:
                print(f"Warning: Product 'Cases' not found, skipping PO creation")
                continue

            try:
                po = self.create_purchase_order(
                    destination_site_id=site_id,  # Integer site ID
                    product_id=product_id,  # Integer product ID
                    order_qty=order_qty,
                    order_date=order_date,
                    game_id=game_id,
                    round_number=round_number,
                    auto_approve=True
                )
                pos.append(po)
            except ValueError as e:
                # No sourcing rule (e.g., Factory)
                print(f"Skipping PO for {site_id}: {e}")
                continue

        return pos

    def receive_purchase_order(
        self,
        po: PurchaseOrder
    ) -> None:
        """
        Receive purchase order (shipment arrives).

        Updates:
        1. in_transit_qty decreases
        2. on_hand_qty increases
        3. PO status = RECEIVED

        Args:
            po: Purchase order to receive
        """
        # Get PO line items
        po_lines = self.db.query(PurchaseOrderLineItem).filter(
            PurchaseOrderLineItem.po_id == po.id
        ).all()

        for line in po_lines:
            # Update inv_level
            inv_level = self.db.query(InvLevel).filter(
                and_(
                    InvLevel.site_id == po.destination_site_id,
                    InvLevel.item_id == line.product_id
                )
            ).first()

            if inv_level:
                # Move from in_transit to on_hand
                inv_level.in_transit_qty -= line.ordered_quantity
                inv_level.on_hand_qty += line.ordered_quantity

                # Ensure no negative values
                inv_level.in_transit_qty = max(0.0, inv_level.in_transit_qty)

        # Update PO status
        po.status = "RECEIVED"
        po.actual_delivery_date = datetime.now().date()
        po.received_at = datetime.now()

        self.db.commit()

    def process_arriving_orders(
        self,
        game_id: int,
        round_number: int
    ) -> List[PurchaseOrder]:
        """
        Process all POs arriving in current Beer Game round.

        Receives all POs where arrival_round == current round.

        Args:
            game_id: Game ID
            round_number: Current round number

        Returns:
            List of received PurchaseOrders
        """
        # Get POs that are arriving this round
        arriving_pos = self.db.query(PurchaseOrder).filter(
            and_(
                PurchaseOrder.game_id == game_id,
                PurchaseOrder.arrival_round == round_number,
                PurchaseOrder.status.in_(["APPROVED", "SENT", "SHIPPED"])
            )
        ).all()

        for po in arriving_pos:
            self.receive_purchase_order(po)

        return arriving_pos

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _get_sourcing_rule(
        self,
        destination_site_id: int,
        item_id: int
    ) -> Optional[SourcingRules]:
        """
        Get sourcing rule for destination node and item.

        Args:
            destination_site_id: Node ID (Integer)
            item_id: Item ID (Integer)

        Returns the highest priority sourcing rule.
        """
        sourcing_rule = self.db.query(SourcingRules).filter(
            and_(
                SourcingRules.destination_site_id == destination_site_id,
                SourcingRules.item_id == item_id
            )
        ).order_by(SourcingRules.priority.asc()).first()

        return sourcing_rule

    def _generate_po_number(
        self,
        game_id: Optional[int],
        round_number: Optional[int],
        site_id: int
    ) -> str:
        """Generate unique PO number."""
        timestamp = int(datetime.now().timestamp())

        if game_id and round_number:
            return f"PO-G{game_id}-R{round_number}-N{site_id}-{timestamp}"
        else:
            return f"PO-N{site_id}-{timestamp}"

    def _update_in_transit(
        self,
        site_id: int,
        item_id: int,
        qty: float
    ) -> None:
        """Update in_transit_qty when PO is placed."""
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
            # Create inv_level record if doesn't exist
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

    def get_po_status(
        self,
        game_id: int,
        round_number: Optional[int] = None,
        site_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Get PO status for game/round/site.

        Args:
            game_id: Game ID
            round_number: Round number (optional)
            site_id: Site ID (optional)

        Returns:
            List of PO status dictionaries
        """
        query = self.db.query(PurchaseOrder).filter(
            PurchaseOrder.game_id == game_id
        )

        if round_number is not None:
            query = query.filter(PurchaseOrder.round_number == round_number)

        if site_id:
            query = query.filter(PurchaseOrder.destination_site_id == site_id)

        pos = query.all()

        return [
            {
                "po_number": po.po_number,
                "supplier_site_id": po.supplier_site_id,
                "destination_site_id": po.destination_site_id,
                "quantity": po.quantity,
                "status": po.status,
                "order_date": po.order_date,
                "requested_delivery_date": po.requested_delivery_date,
                "actual_delivery_date": po.actual_delivery_date,
                "round_number": po.round_number,
                "arrival_round": po.arrival_round,
            }
            for po in pos
        ]
