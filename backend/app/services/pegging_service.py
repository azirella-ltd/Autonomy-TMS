"""
Full-Level Pegging Service

Implements Kinaxis-style supply-demand pegging with multi-stage chain tracking.
Provides creation hooks (called by AATP, MRP, SupplyCommit services) and
query methods for tracing demand→supply and supply→demand.

Key concepts:
- chain_id: UUID grouping all pegging links in one end-to-end chain
- chain_depth: 0 = terminal demand (customer order), increasing upstream
- upstream_pegging_id: self-FK linking each stage to its upstream supply
"""

import uuid
import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models.pegging import (
    SupplyDemandPegging, AATPConsumptionRecord,
    DemandType, SupplyType, PeggingStatus,
)
from app.models.mrp import MRPRequirement
from app.models.supply_chain_config import Site

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes for query results
# ---------------------------------------------------------------------------

@dataclass
class PeggingLink:
    """Single link in a pegging chain"""
    pegging_id: int
    depth: int
    product_id: str
    demand_type: str
    demand_id: str
    supply_type: str
    supply_id: str
    site_id: int
    site_name: str
    supply_site_id: Optional[int]
    supply_site_name: Optional[str]
    pegged_quantity: float
    status: str
    lead_time_days: Optional[int] = None


@dataclass
class PeggingChain:
    """Complete end-to-end pegging chain"""
    chain_id: str
    demand_type: str
    demand_id: str
    demand_product: str
    demand_site_id: int
    demand_site_name: str
    demand_quantity: float
    demand_priority: int
    links: List[PeggingLink] = field(default_factory=list)
    total_stages: int = 0
    is_fully_pegged: bool = False
    unpegged_quantity: float = 0.0


@dataclass
class PeggingSummary:
    """Summary of pegging state for a product at a site"""
    product_id: str
    site_id: int
    site_name: str
    total_demand: float
    pegged_demand: float
    unpegged_demand: float
    total_supply: float
    pegged_supply: float
    unpegged_supply: float
    chains: List[PeggingChain] = field(default_factory=list)
    demand_by_type: Dict[str, float] = field(default_factory=dict)
    supply_by_type: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pegging Service
# ---------------------------------------------------------------------------

class PeggingService:
    """
    Full-level pegging service.

    Provides hooks for other services to create pegging links, and query
    methods for tracing supply-demand relationships through the network.
    """

    def __init__(self, db: Session):
        self.db = db
        self._site_cache: Dict[int, str] = {}  # site_id → name cache

    # -----------------------------------------------------------------------
    # Creation hooks
    # -----------------------------------------------------------------------

    def peg_order_to_inventory(
        self,
        order_id: str,
        product_id: str,
        site_id: int,
        quantity: float,
        priority: int,
        config_id: int,
        customer_id: int,
        demand_type: str = "customer_order",
        chain_id: Optional[str] = None,
    ) -> SupplyDemandPegging:
        """
        Create a pegging link from a customer order to on-hand inventory.

        Called by AATP engine after committing consumption.
        This is typically depth=0 (terminal demand).
        """
        if chain_id is None:
            chain_id = uuid.uuid4().hex[:64]

        pegging = SupplyDemandPegging(
            customer_id=customer_id,
            config_id=config_id,
            product_id=product_id,
            site_id=site_id,
            demand_type=demand_type,
            demand_id=order_id,
            demand_priority=priority,
            demand_quantity=quantity,
            supply_type=SupplyType.ON_HAND.value,
            supply_id=f"INV-{site_id}-{product_id}",
            supply_site_id=site_id,
            pegged_quantity=quantity,
            pegging_date=date.today(),
            pegging_status=PeggingStatus.FIRM.value,
            chain_id=chain_id,
            chain_depth=0,
            created_by="aatp_engine",
        )
        self.db.add(pegging)
        self.db.flush()

        logger.info(
            f"Pegged order {order_id} → inventory at site {site_id}, "
            f"qty={quantity}, chain={chain_id[:8]}.."
        )
        return pegging

    def peg_inter_site_order(
        self,
        inbound_order_id: str,
        product_id: str,
        destination_site_id: int,
        source_site_id: int,
        quantity: float,
        config_id: int,
        customer_id: int,
        upstream_pegging_id: Optional[int] = None,
        chain_id: Optional[str] = None,
        chain_depth: int = 1,
        order_type: str = "transfer_order",
    ) -> SupplyDemandPegging:
        """
        Create a pegging link for inter-site replenishment.

        Used when a DC orders from a factory (transfer order) or
        a factory orders from a vendor (purchase order).
        """
        if chain_id is None:
            chain_id = uuid.uuid4().hex[:64]

        supply_type_map = {
            "transfer_order": SupplyType.TRANSFER_ORDER.value,
            "purchase_order": SupplyType.PURCHASE_ORDER.value,
            "manufacturing_order": SupplyType.MANUFACTURING_ORDER.value,
        }

        pegging = SupplyDemandPegging(
            customer_id=customer_id,
            config_id=config_id,
            product_id=product_id,
            site_id=destination_site_id,
            demand_type=DemandType.INTER_SITE_ORDER.value,
            demand_id=inbound_order_id,
            demand_priority=3,  # Default medium for inter-site
            demand_quantity=quantity,
            supply_type=supply_type_map.get(order_type, SupplyType.TRANSFER_ORDER.value),
            supply_id=inbound_order_id,
            supply_site_id=source_site_id,
            pegged_quantity=quantity,
            pegging_date=date.today(),
            pegging_status=PeggingStatus.PLANNED.value,
            upstream_pegging_id=upstream_pegging_id,
            chain_id=chain_id,
            chain_depth=chain_depth,
            created_by="pegging_service",
        )
        self.db.add(pegging)
        self.db.flush()

        logger.info(
            f"Pegged inter-site {order_type} {inbound_order_id}: "
            f"site {source_site_id} → site {destination_site_id}, qty={quantity}"
        )
        return pegging

    def peg_mrp_requirement(
        self,
        mrp_requirement_id: int,
        component_id: str,
        parent_product_id: str,
        site_id: int,
        quantity: float,
        config_id: int,
        customer_id: int,
        parent_demand_type: str = "customer_order",
        parent_demand_id: str = "",
        upstream_pegging_id: Optional[int] = None,
        chain_id: Optional[str] = None,
        chain_depth: int = 1,
        source_site_id: Optional[int] = None,
    ) -> SupplyDemandPegging:
        """
        Create a pegging link for MRP-generated component requirement.

        Called during BOM explosion. Links parent product demand to
        component supply requirement.
        """
        if chain_id is None:
            chain_id = uuid.uuid4().hex[:64]

        pegging = SupplyDemandPegging(
            customer_id=customer_id,
            config_id=config_id,
            product_id=component_id,
            site_id=site_id,
            demand_type=parent_demand_type,
            demand_id=parent_demand_id or f"MRP-{mrp_requirement_id}",
            demand_priority=3,
            demand_quantity=quantity,
            supply_type=SupplyType.PLANNED_ORDER.value,
            supply_id=f"MRP-REQ-{mrp_requirement_id}",
            supply_site_id=source_site_id or site_id,
            pegged_quantity=quantity,
            pegging_date=date.today(),
            pegging_status=PeggingStatus.PLANNED.value,
            upstream_pegging_id=upstream_pegging_id,
            chain_id=chain_id,
            chain_depth=chain_depth,
            created_by="mrp_explosion",
        )
        self.db.add(pegging)
        self.db.flush()

        return pegging

    def peg_supply_plan_to_demand(
        self,
        supply_plan_id: int,
        plan_type: str,
        product_id: str,
        site_id: int,
        source_site_id: Optional[int],
        quantity: float,
        config_id: int,
        customer_id: int,
        demand_pegging_ids: Optional[List[int]] = None,
        chain_id: Optional[str] = None,
        chain_depth: int = 1,
    ) -> SupplyDemandPegging:
        """
        Create pegging link when a supply plan action is generated.

        Links the supply plan (PO/TO/MO) to the demand it fulfills.
        """
        if chain_id is None:
            chain_id = uuid.uuid4().hex[:64]

        supply_type_map = {
            "po_request": SupplyType.PURCHASE_ORDER.value,
            "to_request": SupplyType.TRANSFER_ORDER.value,
            "mo_request": SupplyType.MANUFACTURING_ORDER.value,
        }

        # Link to upstream pegging if provided
        upstream_id = None
        if demand_pegging_ids:
            upstream_id = demand_pegging_ids[0]

        pegging = SupplyDemandPegging(
            customer_id=customer_id,
            config_id=config_id,
            product_id=product_id,
            site_id=site_id,
            demand_type=DemandType.INTER_SITE_ORDER.value,
            demand_id=f"SP-{supply_plan_id}",
            demand_priority=3,
            demand_quantity=quantity,
            supply_type=supply_type_map.get(plan_type, SupplyType.PLANNED_ORDER.value),
            supply_id=f"SP-{supply_plan_id}",
            supply_site_id=source_site_id,
            pegged_quantity=quantity,
            pegging_date=date.today(),
            pegging_status=PeggingStatus.PLANNED.value,
            upstream_pegging_id=upstream_id,
            chain_id=chain_id,
            chain_depth=chain_depth,
            created_by="supply_planning",
        )
        self.db.add(pegging)
        self.db.flush()

        return pegging

    def peg_shipment(
        self,
        shipment_id: str,
        product_id: str,
        from_site_id: int,
        to_site_id: int,
        quantity: float,
        config_id: int,
        customer_id: int,
        upstream_pegging_id: Optional[int] = None,
        chain_id: Optional[str] = None,
        chain_depth: int = 1,
    ) -> SupplyDemandPegging:
        """
        Create pegging link when a shipment is created.
        """
        if chain_id is None:
            chain_id = uuid.uuid4().hex[:64]

        pegging = SupplyDemandPegging(
            customer_id=customer_id,
            config_id=config_id,
            product_id=product_id,
            site_id=to_site_id,
            demand_type=DemandType.INTER_SITE_ORDER.value,
            demand_id=f"SHIP-{shipment_id}",
            demand_priority=3,
            demand_quantity=quantity,
            supply_type=SupplyType.IN_TRANSIT.value,
            supply_id=shipment_id,
            supply_site_id=from_site_id,
            pegged_quantity=quantity,
            pegging_date=date.today(),
            pegging_status=PeggingStatus.FIRM.value,
            upstream_pegging_id=upstream_pegging_id,
            chain_id=chain_id,
            chain_depth=chain_depth,
            created_by="shipment_service",
        )
        self.db.add(pegging)
        self.db.flush()

        return pegging

    def record_aatp_consumption(
        self,
        order_id: str,
        product_id: str,
        location_id: str,
        customer_id: str,
        requested_qty: float,
        fulfilled_qty: float,
        priority: int,
        consumption_detail: List[Dict],
        config_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        pegging_id: Optional[int] = None,
    ) -> AATPConsumptionRecord:
        """
        Persist an AATP consumption decision to the database.
        """
        record = AATPConsumptionRecord(
            order_id=order_id,
            product_id=product_id,
            location_id=location_id,
            customer_id=customer_id,
            requested_qty=requested_qty,
            fulfilled_qty=fulfilled_qty,
            priority=priority,
            consumption_detail=consumption_detail,
            pegging_id=pegging_id,
            config_id=config_id,
            customer_id=customer_id,
        )
        self.db.add(record)
        self.db.flush()

        return record

    # -----------------------------------------------------------------------
    # Query methods
    # -----------------------------------------------------------------------

    def _get_site_name(self, site_id: int) -> str:
        """Get site name with caching"""
        if site_id not in self._site_cache:
            site = self.db.query(Site).filter(Site.id == site_id).first()
            self._site_cache[site_id] = site.name if site else f"Site-{site_id}"
        return self._site_cache[site_id]

    def trace_demand_to_supply(
        self, demand_type: str, demand_id: str, config_id: Optional[int] = None
    ) -> List[PeggingChain]:
        """
        Trace from demand to all supply backing it.

        Follow chain: demand → supply → upstream supply → ... → vendor
        Returns list of chains (one demand may have multiple chains for
        partial pegging from different sources).
        """
        # Find all root pegging links for this demand
        query = self.db.query(SupplyDemandPegging).filter(
            and_(
                SupplyDemandPegging.demand_type == demand_type,
                SupplyDemandPegging.demand_id == demand_id,
                SupplyDemandPegging.is_active == True,
                SupplyDemandPegging.chain_depth == 0,
            )
        )
        if config_id:
            query = query.filter(SupplyDemandPegging.config_id == config_id)

        root_peggings = query.all()

        chains = []
        seen_chains = set()
        for root in root_peggings:
            if root.chain_id not in seen_chains:
                seen_chains.add(root.chain_id)
                chain = self.rebuild_pegging_chain(root.chain_id)
                if chain:
                    chains.append(chain)

        return chains

    def trace_supply_to_demand(
        self, supply_type: str, supply_id: str, config_id: Optional[int] = None
    ) -> List[PeggingChain]:
        """
        Trace from supply to all demand it backs.

        Follow chain upstream: supply → what demand does this serve?
        """
        query = self.db.query(SupplyDemandPegging).filter(
            and_(
                SupplyDemandPegging.supply_type == supply_type,
                SupplyDemandPegging.supply_id == supply_id,
                SupplyDemandPegging.is_active == True,
            )
        )
        if config_id:
            query = query.filter(SupplyDemandPegging.config_id == config_id)

        supply_peggings = query.all()

        chains = []
        seen_chains = set()
        for peg in supply_peggings:
            if peg.chain_id not in seen_chains:
                seen_chains.add(peg.chain_id)
                chain = self.rebuild_pegging_chain(peg.chain_id)
                if chain:
                    chains.append(chain)

        return chains

    def get_product_site_pegging(
        self, product_id: str, site_id: int, config_id: int
    ) -> PeggingSummary:
        """
        Summary of pegging state for a product at a site.

        Shows how much demand is pegged vs unpegged, broken down by type.
        """
        peggings = self.db.query(SupplyDemandPegging).filter(
            and_(
                SupplyDemandPegging.product_id == product_id,
                SupplyDemandPegging.site_id == site_id,
                SupplyDemandPegging.config_id == config_id,
                SupplyDemandPegging.is_active == True,
            )
        ).all()

        site_name = self._get_site_name(site_id)
        demand_by_type: Dict[str, float] = {}
        supply_by_type: Dict[str, float] = {}
        total_pegged_demand = 0.0
        total_pegged_supply = 0.0

        chain_ids = set()
        for peg in peggings:
            dt = peg.demand_type
            st = peg.supply_type
            demand_by_type[dt] = demand_by_type.get(dt, 0) + peg.demand_quantity
            supply_by_type[st] = supply_by_type.get(st, 0) + peg.pegged_quantity
            total_pegged_demand += peg.pegged_quantity
            total_pegged_supply += peg.pegged_quantity
            chain_ids.add(peg.chain_id)

        # Build chains
        chains = []
        for cid in list(chain_ids)[:50]:  # Limit to avoid huge queries
            chain = self.rebuild_pegging_chain(cid)
            if chain:
                chains.append(chain)

        return PeggingSummary(
            product_id=product_id,
            site_id=site_id,
            site_name=site_name,
            total_demand=sum(demand_by_type.values()),
            pegged_demand=total_pegged_demand,
            unpegged_demand=0.0,  # Would require cross-referencing demand tables
            total_supply=sum(supply_by_type.values()),
            pegged_supply=total_pegged_supply,
            unpegged_supply=0.0,
            chains=chains,
            demand_by_type=demand_by_type,
            supply_by_type=supply_by_type,
        )

    def rebuild_pegging_chain(self, chain_id: str) -> Optional[PeggingChain]:
        """
        Reconstruct a full pegging chain from chain_id.

        Returns PeggingChain with links ordered from demand (depth=0)
        to upstream vendor (max depth).
        """
        peggings = self.db.query(SupplyDemandPegging).filter(
            and_(
                SupplyDemandPegging.chain_id == chain_id,
                SupplyDemandPegging.is_active == True,
            )
        ).order_by(SupplyDemandPegging.chain_depth).all()

        if not peggings:
            return None

        root = peggings[0]
        links = []

        for peg in peggings:
            site_name = self._get_site_name(peg.site_id)
            supply_site_name = (
                self._get_site_name(peg.supply_site_id)
                if peg.supply_site_id else None
            )

            links.append(PeggingLink(
                pegging_id=peg.id,
                depth=peg.chain_depth,
                product_id=peg.product_id,
                demand_type=peg.demand_type,
                demand_id=peg.demand_id,
                supply_type=peg.supply_type,
                supply_id=peg.supply_id,
                site_id=peg.site_id,
                site_name=site_name,
                supply_site_id=peg.supply_site_id,
                supply_site_name=supply_site_name,
                pegged_quantity=peg.pegged_quantity,
                status=peg.pegging_status,
            ))

        total_pegged = sum(l.pegged_quantity for l in links if l.depth == 0)

        return PeggingChain(
            chain_id=chain_id,
            demand_type=root.demand_type,
            demand_id=root.demand_id,
            demand_product=root.product_id,
            demand_site_id=root.site_id,
            demand_site_name=self._get_site_name(root.site_id),
            demand_quantity=root.demand_quantity,
            demand_priority=root.demand_priority,
            links=links,
            total_stages=len(links),
            is_fully_pegged=(total_pegged >= root.demand_quantity),
            unpegged_quantity=max(0, root.demand_quantity - total_pegged),
        )

    def get_unpegged_demand(
        self, config_id: int, customer_id: int
    ) -> List[Dict]:
        """
        Find all demand that is not yet pegged to supply.

        Returns list of unpegged demand records for planning action list.
        This is a simplified version that checks for demand_type entries
        without corresponding pegging records.
        """
        # Get all pegged demand IDs for this config
        pegged = self.db.query(
            SupplyDemandPegging.demand_type,
            SupplyDemandPegging.demand_id,
        ).filter(
            and_(
                SupplyDemandPegging.config_id == config_id,
                SupplyDemandPegging.is_active == True,
                SupplyDemandPegging.chain_depth == 0,
            )
        ).all()

        pegged_set = {(dt, did) for dt, did in pegged}

        return [{
            "pegged_count": len(pegged_set),
            "config_id": config_id,
            "customer_id": customer_id,
        }]

    # -----------------------------------------------------------------------
    # Cascade integration
    # -----------------------------------------------------------------------

    def populate_supply_commit_pegging(
        self, supply_commit_id: int, config_id: int
    ) -> dict:
        """
        Build JSON for SupplyCommit.supply_pegging from pegging links.

        Returns a dict suitable for storing in the supply_pegging JSON column.
        """
        from app.models.planning_cascade import SupplyCommit

        commit = self.db.query(SupplyCommit).filter(
            SupplyCommit.id == supply_commit_id
        ).first()

        if not commit or not commit.recommendations:
            return {}

        pegging_data = {
            "supply_commit_id": supply_commit_id,
            "generated_at": datetime.utcnow().isoformat(),
            "links": [],
        }

        # For each recommendation in the supply commit, find pegging links
        for rec in commit.recommendations:
            sku = rec.get("sku", "")
            destination = rec.get("destination_id", "")

            links = self.db.query(SupplyDemandPegging).filter(
                and_(
                    SupplyDemandPegging.config_id == config_id,
                    SupplyDemandPegging.product_id == sku,
                    SupplyDemandPegging.is_active == True,
                )
            ).limit(100).all()

            for link in links:
                pegging_data["links"].append({
                    "pegging_id": link.id,
                    "sku": link.product_id,
                    "demand_type": link.demand_type,
                    "demand_id": link.demand_id,
                    "supply_type": link.supply_type,
                    "supply_id": link.supply_id,
                    "pegged_qty": link.pegged_quantity,
                    "chain_id": link.chain_id,
                    "depth": link.chain_depth,
                })

        # Update the commit
        commit.supply_pegging = pegging_data
        self.db.flush()

        return pegging_data

    def populate_allocation_pegging(
        self, allocation_commit_id: int, config_id: int
    ) -> dict:
        """
        Build JSON for AllocationCommit.pegging_summary from pegging links.
        """
        from app.models.planning_cascade import AllocationCommit

        commit = self.db.query(AllocationCommit).filter(
            AllocationCommit.id == allocation_commit_id
        ).first()

        if not commit or not commit.allocations:
            return {}

        summary = {
            "allocation_commit_id": allocation_commit_id,
            "generated_at": datetime.utcnow().isoformat(),
            "segments": {},
        }

        # Group pegging by demand segment
        for alloc in commit.allocations:
            segment = alloc.get("segment", "unknown")
            sku = alloc.get("sku", "")

            if segment not in summary["segments"]:
                summary["segments"][segment] = {
                    "total_allocated": 0,
                    "total_pegged": 0,
                    "pegging_links": [],
                }

            summary["segments"][segment]["total_allocated"] += alloc.get("entitlement_qty", 0)

            # Find pegging links for this SKU
            links = self.db.query(SupplyDemandPegging).filter(
                and_(
                    SupplyDemandPegging.config_id == config_id,
                    SupplyDemandPegging.product_id == sku,
                    SupplyDemandPegging.is_active == True,
                    SupplyDemandPegging.chain_depth == 0,
                )
            ).limit(50).all()

            for link in links:
                summary["segments"][segment]["total_pegged"] += link.pegged_quantity
                summary["segments"][segment]["pegging_links"].append({
                    "demand_id": link.demand_id,
                    "supply_type": link.supply_type,
                    "pegged_qty": link.pegged_quantity,
                    "chain_id": link.chain_id,
                })

        commit.pegging_summary = summary
        self.db.flush()

        return summary
