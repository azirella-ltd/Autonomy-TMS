"""
Purchase Order Creation - SC Execution

Creates purchase orders based on agent decisions and sourcing rules.
Simulation agents use this to place orders upstream.

Reference: SC Purchase Order Creation
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
from app.models.sc_entities import SourcingRules, InvLevel, Product, InvPolicy
from app.models.supply_chain_config import Site, TransportationLane
from .site_id_mapper import SimulationIdMapper


class PurchaseOrderCreator:
    """
    Purchase Order Creator implementing SC PO creation logic.

    This creator:
    1. Reads sourcing rules to find upstream supplier
    2. Creates purchase order based on agent decision
    3. Updates in_transit_qty in inv_level
    4. Tracks arrival_round for simulation

    The simulation uses this each round when agents decide order quantities.
    """

    def __init__(self, db: Session):
        self.db = db

    def create_purchase_order(
        self,
        destination_site_id: int,
        product_id: str,
        order_qty: float,
        order_date: date,
        scenario_id: Optional[int] = None,
        round_number: Optional[int] = None,
        company_id: str = "company_001",
        auto_approve: bool = True
    ) -> PurchaseOrder:
        """
        Create purchase order to upstream supplier (SC compliant).

        Steps:
        1. Find sourcing rule (who is upstream supplier?)
        2. Calculate arrival date (lead time from TransportationLane)
        3. Create PO record
        4. Update in_transit_qty
        5. Create PO line item

        Args:
            destination_site_id: Receiving site integer PK
            product_id: Product string PK
            order_qty: Quantity to order (from agent decision)
            order_date: Order date
            scenario_id: Scenario ID (optional)
            round_number: Round number when order is placed (optional)
            company_id: Company ID
            auto_approve: Auto-approve PO (default: True for simulation)

        Returns:
            Created PurchaseOrder
        """
        # Find sourcing rule to determine upstream supplier
        sourcing_rule = self._get_sourcing_rule(destination_site_id, product_id)

        if not sourcing_rule:
            raise ValueError(
                f"No sourcing rule found for site {destination_site_id}, "
                f"product {product_id}"
            )

        # Lead time from TransportationLane (via sourcing_rule FK)
        # supply_lead_time.value is in weeks/rounds (1 round = 1 week)
        lead_time_rounds = 2  # fallback when no TransportationLane configured — populate lane for accurate scheduling
        if sourcing_rule.transportation_lane_id:
            lane = self.db.query(TransportationLane).filter(
                TransportationLane.id == sourcing_rule.transportation_lane_id
            ).first()
            if lane and lane.supply_lead_time:
                lead_time_rounds = int(lane.supply_lead_time.get("value", 2))

        lead_time_days = lead_time_rounds * 7

        # Calculate delivery dates
        requested_delivery_date = order_date + timedelta(days=lead_time_days)

        # Calculate arrival round
        arrival_round = None
        if round_number is not None:
            arrival_round = round_number + lead_time_rounds

        # Generate PO number
        po_number = self._generate_po_number(scenario_id, round_number, destination_site_id)

        # Create PO
        po = PurchaseOrder(
            po_number=po_number,
            supplier_site_id=sourcing_rule.from_site_id,
            destination_site_id=destination_site_id,
            company_id=company_id,
            order_type="po",
            status="APPROVED" if auto_approve else "DRAFT",
            order_date=order_date,
            requested_delivery_date=requested_delivery_date,
            scenario_id=scenario_id,
            order_round=round_number,
            arrival_round=arrival_round,
            created_at=datetime.now(),
        )

        if auto_approve:
            po.approved_at = datetime.now()

        self.db.add(po)
        self.db.flush()  # Get PO ID

        # Create PO line item
        po_line = PurchaseOrderLineItem(
            po_id=po.id,
            line_number=1,
            product_id=product_id,
            quantity=order_qty,
            unit_price=0.0,
            line_total=0.0,
            requested_delivery_date=requested_delivery_date,
        )
        self.db.add(po_line)

        # Update in_transit_qty in inv_level
        self._update_in_transit(destination_site_id, product_id, order_qty)

        self.db.commit()

        return po

    def create_simulation_orders(
        self,
        scenario_id: int,
        round_number: int,
        order_decisions: Dict[str, float],
        config_id: int
    ) -> List[PurchaseOrder]:
        """
        Create POs for all sites in a simulation based on agent decisions.

        Args:
            scenario_id: Scenario ID
            round_number: Current round number
            order_decisions: Dict mapping site_name (or str site_id) to order_qty
            config_id: Supply chain configuration ID

        Returns:
            List of created PurchaseOrders
        """
        pos = []
        order_date = datetime.now().date()

        # ID mapper for name → integer site_id resolution
        mapper = SimulationIdMapper(self.db, config_id)

        # Resolve config product_id — prefer products with InvPolicy (seeded for SC execution)
        product = (
            self.db.query(Product)
            .join(InvPolicy, InvPolicy.product_id == Product.id)
            .filter(Product.config_id == config_id)
            .order_by(Product.id)
            .first()
        )
        if not product:
            product = (
                self.db.query(Product)
                .filter(Product.config_id == config_id)
                .order_by(Product.id)
                .first()
            )
        if not product:
            print(f"Warning: No product found for config {config_id}, skipping PO creation")
            return pos

        product_id = product.id

        for site_key, order_qty in order_decisions.items():
            if order_qty <= 0:
                continue

            # Resolve site_key (name or str int) → integer site_id
            site_id = mapper.get_site_id(str(site_key))
            if not site_id:
                # Try interpreting as integer directly
                try:
                    site_id = int(site_key)
                except (ValueError, TypeError):
                    print(f"Warning: Site '{site_key}' not found, skipping PO creation")
                    continue

            # Check if site is Manufacturer (infinite supply, no PO needed)
            site = self.db.query(Site).filter(Site.id == site_id).first()
            if site and (site.master_type or "").lower() == "manufacturer":
                continue

            try:
                po = self.create_purchase_order(
                    destination_site_id=site_id,
                    product_id=product_id,
                    order_qty=order_qty,
                    order_date=order_date,
                    scenario_id=scenario_id,
                    round_number=round_number,
                    auto_approve=True,
                )
                pos.append(po)
            except ValueError as e:
                # No sourcing rule (e.g., Factory has no upstream)
                print(f"Skipping PO for site {site_id}: {e}")
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
        """
        po_lines = self.db.query(PurchaseOrderLineItem).filter(
            PurchaseOrderLineItem.po_id == po.id
        ).all()

        for line in po_lines:
            inv_level = self.db.query(InvLevel).filter(
                and_(
                    InvLevel.site_id == po.destination_site_id,
                    InvLevel.product_id == line.product_id,
                )
            ).first()

            if inv_level:
                # Move from in_transit to on_hand
                inv_level.in_transit_qty = max(
                    0.0, (inv_level.in_transit_qty or 0.0) - (line.quantity or 0.0)
                )
                inv_level.on_hand_qty = (inv_level.on_hand_qty or 0.0) + (line.quantity or 0.0)

        po.status = "RECEIVED"
        po.actual_delivery_date = datetime.now().date()
        po.received_at = datetime.now()

        self.db.commit()

    def process_arriving_orders(
        self,
        scenario_id: int,
        round_number: int
    ) -> List[PurchaseOrder]:
        """
        Process all POs arriving in current simulation round.

        Receives all POs where arrival_round == current round.
        """
        arriving_pos = self.db.query(PurchaseOrder).filter(
            and_(
                PurchaseOrder.scenario_id == scenario_id,
                PurchaseOrder.arrival_round == round_number,
                PurchaseOrder.status.in_(["APPROVED", "SENT", "SHIPPED"]),
            )
        ).all()

        for po in arriving_pos:
            self.receive_purchase_order(po)

        return arriving_pos

    def get_po_status(
        self,
        scenario_id: int,
        round_number: Optional[int] = None,
        site_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Get PO status for scenario/round/site.
        """
        query = self.db.query(PurchaseOrder).filter(
            PurchaseOrder.scenario_id == scenario_id
        )

        if round_number is not None:
            query = query.filter(PurchaseOrder.order_round == round_number)

        if site_id is not None:
            query = query.filter(PurchaseOrder.destination_site_id == site_id)

        pos = query.all()

        return [
            {
                "po_number": po.po_number,
                "supplier_site_id": po.supplier_site_id,
                "destination_site_id": po.destination_site_id,
                "status": po.status,
                "order_date": po.order_date,
                "requested_delivery_date": po.requested_delivery_date,
                "actual_delivery_date": po.actual_delivery_date,
                "order_round": po.order_round,
                "arrival_round": po.arrival_round,
            }
            for po in pos
        ]

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _get_sourcing_rule(
        self,
        destination_site_id: int,
        product_id: str,
    ) -> Optional[SourcingRules]:
        """
        Get highest-priority sourcing rule for destination site and product.
        """
        return (
            self.db.query(SourcingRules)
            .filter(
                and_(
                    SourcingRules.to_site_id == destination_site_id,
                    SourcingRules.product_id == product_id,
                )
            )
            .order_by(SourcingRules.sourcing_priority.asc())
            .first()
        )

    def _generate_po_number(
        self,
        scenario_id: Optional[int],
        round_number: Optional[int],
        site_id: int
    ) -> str:
        """Generate unique PO number."""
        timestamp = int(datetime.now().timestamp())
        if scenario_id and round_number is not None:
            return f"PO-G{scenario_id}-R{round_number}-N{site_id}-{timestamp}"
        return f"PO-N{site_id}-{timestamp}"

    def _update_in_transit(
        self,
        site_id: int,
        product_id: str,
        qty: float,
    ) -> None:
        """Update in_transit_qty when PO is placed."""
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
            # Create minimal inv_level record
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
