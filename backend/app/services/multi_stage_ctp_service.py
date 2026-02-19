"""
Multi-Stage Capable-to-Promise (CTP) Service

Implements Kinaxis-style full-level CTP with multi-stage traversal through
the supply chain DAG. For any order at site X, traces upstream through
all stages (DCs → factories → suppliers) to determine:
- Available quantity at each stage
- Cumulative lead time through the chain
- Binding constraint (tightest stage)
- Promise date considering all stages
- Pegging preview (proposed demand-supply chain)

Supports:
- Multi-stage manufacturing (product sold as spare AND assembled into another)
- Multi-stage distribution (regional DC → local DCs)
- Convergent topologies (multiple suppliers → one factory)
- Divergent topologies (factory → multiple DCs)
- BOM explosion at manufacturing stages
- Shared component detection
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.supply_chain_config import Site, TransportationLane
from app.models.sc_entities import (
    SourcingRules, InvLevel, InvPolicy, ProductBom, SupplyPlan,
)
from app.models.pegging import SupplyDemandPegging
from app.services.pegging_service import PeggingService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StageResult:
    """Result for a single stage in the CTP traversal"""
    site_id: int
    site_name: str
    site_type: str  # MANUFACTURER, INVENTORY, MARKET_SUPPLY, MARKET_DEMAND
    product_id: str
    available_qty: float
    lead_time_days: int
    cumulative_lead_time_days: int
    constraint: Optional[str] = None  # "capacity", "component_X", "inventory", etc.
    children: List['StageResult'] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "site_id": self.site_id,
            "site_name": self.site_name,
            "site_type": self.site_type,
            "product_id": self.product_id,
            "available_qty": self.available_qty,
            "lead_time_days": self.lead_time_days,
            "cumulative_lead_time_days": self.cumulative_lead_time_days,
            "constraint": self.constraint,
        }
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


@dataclass
class MultiStageCTPResult:
    """Full multi-stage CTP result"""
    product_id: str
    site_id: int
    requested_qty: float
    ctp_qty: float                  # Min across all stages
    promise_date: Optional[date] = None
    cumulative_lead_time_days: int = 0
    binding_stage: Optional[StageResult] = None
    stages: List[StageResult] = field(default_factory=list)
    pegging_preview: List[dict] = field(default_factory=list)
    is_feasible: bool = False
    constraint_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "site_id": self.site_id,
            "requested_qty": self.requested_qty,
            "ctp_qty": self.ctp_qty,
            "promise_date": self.promise_date.isoformat() if self.promise_date else None,
            "cumulative_lead_time_days": self.cumulative_lead_time_days,
            "binding_stage": self.binding_stage.to_dict() if self.binding_stage else None,
            "stages": [s.to_dict() for s in self.stages],
            "pegging_preview": self.pegging_preview,
            "is_feasible": self.is_feasible,
            "constraint_summary": self.constraint_summary,
        }


@dataclass
class OrderPromiseResult:
    """Result of promising an order with pegging"""
    order_id: str
    ctp_result: MultiStageCTPResult
    promised: bool
    promised_qty: float
    promised_date: Optional[date]
    pegging_chain_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Multi-Stage CTP Service
# ---------------------------------------------------------------------------

class MultiStageCTPService:
    """
    Multi-stage CTP engine.

    Traverses the supply chain DAG upstream from the requesting site,
    checking availability at each stage with BOM explosion and lead time
    accumulation.
    """

    def __init__(
        self,
        db: Session,
        config_id: int,
        group_id: int,
        pegging_service: Optional[PeggingService] = None,
    ):
        self.db = db
        self.config_id = config_id
        self.group_id = group_id
        self.pegging_service = pegging_service or PeggingService(db)

        # Caches (valid for one CTP batch)
        self._site_cache: Dict[int, Site] = {}
        self._sourcing_cache: Dict[str, List[SourcingRules]] = {}
        self._bom_cache: Dict[str, List[ProductBom]] = {}
        self._inv_cache: Dict[str, float] = {}  # "product:site" → available qty
        self._committed_cache: Dict[str, float] = {}  # Already-pegged qty

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def calculate_multi_stage_ctp(
        self,
        product_id: str,
        site_id: int,
        quantity: float,
        target_date: Optional[date] = None,
        demand_type: str = "customer_order",
    ) -> MultiStageCTPResult:
        """
        Calculate multi-stage CTP for a product at a site.

        Traverses the supply chain DAG upstream, checking availability
        at each stage with BOM explosion and lead time accumulation.
        """
        if target_date is None:
            target_date = date.today() + timedelta(days=30)

        # Clear caches for fresh calculation
        self._clear_caches()

        # Load site info
        site = self._get_site(site_id)
        if not site:
            return MultiStageCTPResult(
                product_id=product_id,
                site_id=site_id,
                requested_qty=quantity,
                ctp_qty=0,
                constraint_summary="Site not found",
            )

        # Recursive upstream traversal
        visited: Set[Tuple[str, int]] = set()
        stage = self._check_stage(
            product_id=product_id,
            site=site,
            quantity=quantity,
            cumulative_lt=0,
            visited=visited,
        )

        # Build result
        ctp_qty = stage.available_qty
        binding = self._find_binding_stage(stage)
        cumulative_lt = stage.cumulative_lead_time_days

        promise_date_val = None
        if ctp_qty >= quantity:
            promise_date_val = target_date + timedelta(days=cumulative_lt)

        # Build pegging preview
        pegging_preview = self._build_pegging_preview(stage, product_id, site_id, quantity)

        constraint_parts = []
        if binding and binding.constraint:
            constraint_parts.append(
                f"{binding.constraint} at {binding.site_name} "
                f"(available: {binding.available_qty:.0f})"
            )

        return MultiStageCTPResult(
            product_id=product_id,
            site_id=site_id,
            requested_qty=quantity,
            ctp_qty=min(ctp_qty, quantity),
            promise_date=promise_date_val,
            cumulative_lead_time_days=cumulative_lt,
            binding_stage=binding,
            stages=[stage],
            pegging_preview=pegging_preview,
            is_feasible=(ctp_qty >= quantity),
            constraint_summary="; ".join(constraint_parts) if constraint_parts else "No constraints",
        )

    def promise_order(
        self,
        order_id: str,
        product_id: str,
        site_id: int,
        quantity: float,
        target_date: date,
        priority: int = 3,
    ) -> OrderPromiseResult:
        """
        Promise an order with full pegging chain creation.

        1. Calculate multi-stage CTP
        2. If feasible, create pegging chain from demand to upstream supply
        """
        ctp_result = self.calculate_multi_stage_ctp(
            product_id=product_id,
            site_id=site_id,
            quantity=quantity,
            target_date=target_date,
        )

        if not ctp_result.is_feasible:
            return OrderPromiseResult(
                order_id=order_id,
                ctp_result=ctp_result,
                promised=False,
                promised_qty=ctp_result.ctp_qty,
                promised_date=None,
            )

        # Create pegging chain
        import uuid
        chain_id = uuid.uuid4().hex[:64]

        # Create root pegging (order → inventory at requesting site)
        root_pegging = self.pegging_service.peg_order_to_inventory(
            order_id=order_id,
            product_id=product_id,
            site_id=site_id,
            quantity=quantity,
            priority=priority,
            config_id=self.config_id,
            group_id=self.group_id,
            chain_id=chain_id,
        )

        # Create upstream pegging links from pegging preview
        prev_pegging_id = root_pegging.id
        for i, preview in enumerate(ctp_result.pegging_preview[1:], start=1):
            peg = self.pegging_service.peg_inter_site_order(
                inbound_order_id=f"{order_id}-STAGE-{i}",
                product_id=preview.get("product_id", product_id),
                destination_site_id=preview.get("site_id", site_id),
                source_site_id=preview.get("source_site_id", site_id),
                quantity=preview.get("quantity", quantity),
                config_id=self.config_id,
                group_id=self.group_id,
                upstream_pegging_id=prev_pegging_id,
                chain_id=chain_id,
                chain_depth=i,
                order_type=preview.get("order_type", "transfer_order"),
            )
            prev_pegging_id = peg.id

        self.db.commit()

        return OrderPromiseResult(
            order_id=order_id,
            ctp_result=ctp_result,
            promised=True,
            promised_qty=quantity,
            promised_date=ctp_result.promise_date,
            pegging_chain_id=chain_id,
        )

    # -----------------------------------------------------------------------
    # Core CTP traversal
    # -----------------------------------------------------------------------

    def _check_stage(
        self,
        product_id: str,
        site: Site,
        quantity: float,
        cumulative_lt: int,
        visited: Set[Tuple[str, int]],
    ) -> StageResult:
        """
        Check availability at a single stage and recurse upstream.

        Logic depends on site master_type:
        - INVENTORY: Check on-hand - committed - safety_stock
        - MANUFACTURER: Check production capacity, BOM explosion
        - MARKET_SUPPLY: Check vendor capacity/lead time (terminal)
        """
        visit_key = (product_id, site.id)
        if visit_key in visited:
            # Cycle detection
            return StageResult(
                site_id=site.id,
                site_name=site.name,
                site_type=site.master_type or "UNKNOWN",
                product_id=product_id,
                available_qty=0,
                lead_time_days=0,
                cumulative_lead_time_days=cumulative_lt,
                constraint="cycle_detected",
            )
        visited.add(visit_key)

        master_type = (site.master_type or "").upper()

        if master_type == "MARKET_SUPPLY":
            return self._check_vendor_stage(product_id, site, quantity, cumulative_lt)
        elif master_type == "MANUFACTURER":
            return self._check_manufacturer_stage(
                product_id, site, quantity, cumulative_lt, visited
            )
        else:
            # INVENTORY (DC, warehouse, store) or MARKET_DEMAND
            return self._check_inventory_stage(
                product_id, site, quantity, cumulative_lt, visited
            )

    def _check_inventory_stage(
        self,
        product_id: str,
        site: Site,
        quantity: float,
        cumulative_lt: int,
        visited: Set[Tuple[str, int]],
    ) -> StageResult:
        """Check availability at an inventory site (DC, warehouse, store)."""
        available = self._get_available_inventory(product_id, site.id)
        committed = self._get_committed_quantity(product_id, site.id)
        safety_stock = self._get_safety_stock(product_id, site.id)

        net_available = max(0, available - committed - safety_stock)

        constraint = None
        if net_available < quantity:
            constraint = "inventory"

        children = []
        upstream_available = 0.0

        # If not enough locally, check upstream sources
        if net_available < quantity:
            sourcing_rules = self._get_sourcing_rules(product_id, site.id)
            shortfall = quantity - net_available

            for rule in sourcing_rules:
                source_site = self._get_site_by_str_id(rule.from_site_id)
                if not source_site:
                    continue

                lt = self._get_lead_time(rule, site.id)
                child = self._check_stage(
                    product_id=product_id,
                    site=source_site,
                    quantity=shortfall,
                    cumulative_lt=cumulative_lt + lt,
                    visited=visited.copy(),
                )
                children.append(child)
                upstream_available += child.available_qty

                if upstream_available >= shortfall:
                    break

        total_available = net_available + upstream_available
        max_cumulative_lt = cumulative_lt
        if children:
            max_cumulative_lt = max(c.cumulative_lead_time_days for c in children)

        return StageResult(
            site_id=site.id,
            site_name=site.name,
            site_type=site.master_type or "INVENTORY",
            product_id=product_id,
            available_qty=min(total_available, quantity),
            lead_time_days=0,  # No production LT at inventory site
            cumulative_lead_time_days=max_cumulative_lt,
            constraint=constraint if total_available < quantity else None,
            children=children,
        )

    def _check_manufacturer_stage(
        self,
        product_id: str,
        site: Site,
        quantity: float,
        cumulative_lt: int,
        visited: Set[Tuple[str, int]],
    ) -> StageResult:
        """
        Check availability at a manufacturing site.

        1. Check production capacity
        2. BOM explosion: for each component, recurse upstream
        3. CTP = min(capacity, component availability)
        """
        # Production capacity
        capacity = self._get_production_capacity(site)
        production_lt = self._get_production_lead_time(site)

        # Check on-hand finished goods first
        fg_available = self._get_available_inventory(product_id, site.id)
        fg_committed = self._get_committed_quantity(product_id, site.id)
        fg_net = max(0, fg_available - fg_committed)

        if fg_net >= quantity:
            return StageResult(
                site_id=site.id,
                site_name=site.name,
                site_type="MANUFACTURER",
                product_id=product_id,
                available_qty=quantity,
                lead_time_days=0,  # Already in stock
                cumulative_lead_time_days=cumulative_lt,
            )

        # Need to produce: check capacity and components
        need_to_produce = quantity - fg_net
        producible = min(need_to_produce, capacity)

        # BOM explosion
        bom = self._get_bom(product_id)
        children = []
        component_limit = producible

        for comp in bom:
            comp_product_id = comp.component_product_id
            comp_qty_per = comp.component_quantity or 1.0
            scrap = comp.scrap_percentage or 0.0
            required_qty = need_to_produce * comp_qty_per * (1 + scrap / 100)

            # Check component availability (may recurse further upstream)
            comp_stage = self._check_component_availability(
                component_id=comp_product_id,
                site=site,
                required_qty=required_qty,
                cumulative_lt=cumulative_lt + production_lt,
                visited=visited.copy(),
            )
            children.append(comp_stage)

            # How many parent units can we produce from this component
            if comp_qty_per > 0:
                comp_producible = comp_stage.available_qty / (comp_qty_per * (1 + scrap / 100))
            else:
                comp_producible = producible

            component_limit = min(component_limit, comp_producible)

        total_available = fg_net + component_limit
        constraint = None

        if component_limit < need_to_produce:
            # Find the binding component
            for child in children:
                if child.constraint:
                    constraint = f"component_{child.product_id}"
                    break
            if not constraint:
                constraint = "component_shortage"
        elif capacity < need_to_produce:
            constraint = "capacity"

        max_child_lt = cumulative_lt + production_lt
        if children:
            max_child_lt = max(max_child_lt, max(c.cumulative_lead_time_days for c in children))

        return StageResult(
            site_id=site.id,
            site_name=site.name,
            site_type="MANUFACTURER",
            product_id=product_id,
            available_qty=min(total_available, quantity),
            lead_time_days=production_lt,
            cumulative_lead_time_days=max_child_lt,
            constraint=constraint,
            children=children,
        )

    def _check_component_availability(
        self,
        component_id: str,
        site: Site,
        required_qty: float,
        cumulative_lt: int,
        visited: Set[Tuple[str, int]],
    ) -> StageResult:
        """
        Check component availability at a manufacturing site.

        First checks local inventory, then upstream sourcing rules.
        """
        available = self._get_available_inventory(component_id, site.id)
        committed = self._get_committed_quantity(component_id, site.id)
        net_available = max(0, available - committed)

        if net_available >= required_qty:
            return StageResult(
                site_id=site.id,
                site_name=site.name,
                site_type="MANUFACTURER",
                product_id=component_id,
                available_qty=required_qty,
                lead_time_days=0,
                cumulative_lead_time_days=cumulative_lt,
            )

        # Need more: check upstream
        children = []
        upstream_available = 0.0
        shortfall = required_qty - net_available

        sourcing_rules = self._get_sourcing_rules(component_id, site.id)
        for rule in sourcing_rules:
            source_site = self._get_site_by_str_id(rule.from_site_id)
            if not source_site:
                continue

            lt = self._get_lead_time(rule, site.id)
            child = self._check_stage(
                product_id=component_id,
                site=source_site,
                quantity=shortfall - upstream_available,
                cumulative_lt=cumulative_lt + lt,
                visited=visited.copy(),
            )
            children.append(child)
            upstream_available += child.available_qty

            if upstream_available >= shortfall:
                break

        total = net_available + upstream_available

        max_lt = cumulative_lt
        if children:
            max_lt = max(c.cumulative_lead_time_days for c in children)

        return StageResult(
            site_id=site.id,
            site_name=site.name,
            site_type="MANUFACTURER",
            product_id=component_id,
            available_qty=min(total, required_qty),
            lead_time_days=0,
            cumulative_lead_time_days=max_lt,
            constraint="component_shortage" if total < required_qty else None,
            children=children,
        )

    def _check_vendor_stage(
        self,
        product_id: str,
        site: Site,
        quantity: float,
        cumulative_lt: int,
    ) -> StageResult:
        """
        Check availability at a vendor (MARKET_SUPPLY) site.

        Terminal stage — assumes vendor can supply (with lead time).
        Uses vendor capacity if configured, otherwise assumes unlimited.
        """
        vendor_lt = self._get_vendor_lead_time(site, product_id)
        vendor_capacity = self._get_vendor_capacity(site, product_id)

        available = min(quantity, vendor_capacity) if vendor_capacity > 0 else quantity
        constraint = "vendor_capacity" if available < quantity else None

        return StageResult(
            site_id=site.id,
            site_name=site.name,
            site_type="MARKET_SUPPLY",
            product_id=product_id,
            available_qty=available,
            lead_time_days=vendor_lt,
            cumulative_lead_time_days=cumulative_lt + vendor_lt,
            constraint=constraint,
        )

    # -----------------------------------------------------------------------
    # Helper: find binding constraint
    # -----------------------------------------------------------------------

    def _find_binding_stage(self, stage: StageResult) -> Optional[StageResult]:
        """Find the stage with the tightest constraint (lowest available)."""
        binding = None
        min_available = float('inf')

        def _walk(s: StageResult):
            nonlocal binding, min_available
            if s.constraint and s.available_qty < min_available:
                min_available = s.available_qty
                binding = s
            for child in s.children:
                _walk(child)

        _walk(stage)
        return binding

    # -----------------------------------------------------------------------
    # Helper: build pegging preview
    # -----------------------------------------------------------------------

    def _build_pegging_preview(
        self, stage: StageResult, product_id: str, site_id: int, quantity: float
    ) -> List[dict]:
        """Build a pegging preview from the stage tree."""
        preview = []

        def _walk(s: StageResult, depth: int):
            preview.append({
                "depth": depth,
                "site_id": s.site_id,
                "site_name": s.site_name,
                "site_type": s.site_type,
                "product_id": s.product_id,
                "quantity": s.available_qty,
                "source_site_id": s.children[0].site_id if s.children else s.site_id,
                "order_type": self._infer_order_type(s),
                "lead_time_days": s.lead_time_days,
            })
            for child in s.children:
                _walk(child, depth + 1)

        _walk(stage, 0)
        return preview

    def _infer_order_type(self, stage: StageResult) -> str:
        """Infer order type from stage type."""
        st = stage.site_type.upper()
        if st == "MARKET_SUPPLY":
            return "purchase_order"
        elif st == "MANUFACTURER":
            return "manufacturing_order"
        return "transfer_order"

    # -----------------------------------------------------------------------
    # Data access helpers (with caching)
    # -----------------------------------------------------------------------

    def _clear_caches(self):
        self._site_cache.clear()
        self._sourcing_cache.clear()
        self._bom_cache.clear()
        self._inv_cache.clear()
        self._committed_cache.clear()

    def _get_site(self, site_id: int) -> Optional[Site]:
        if site_id not in self._site_cache:
            site = self.db.query(Site).filter(Site.id == site_id).first()
            if site:
                self._site_cache[site_id] = site
        return self._site_cache.get(site_id)

    def _get_site_by_str_id(self, site_id_str: str) -> Optional[Site]:
        """Get site by string ID (SourcingRules uses string FKs)."""
        try:
            site_id = int(site_id_str)
            return self._get_site(site_id)
        except (ValueError, TypeError):
            # Try by name or other lookup
            site = self.db.query(Site).filter(
                and_(Site.config_id == self.config_id, Site.name == site_id_str)
            ).first()
            if site:
                self._site_cache[site.id] = site
            return site

    def _get_sourcing_rules(self, product_id: str, to_site_id: int) -> List[SourcingRules]:
        """Get sourcing rules for a product at a destination site."""
        key = f"{product_id}:{to_site_id}"
        if key not in self._sourcing_cache:
            rules = self.db.query(SourcingRules).filter(
                and_(
                    SourcingRules.product_id == product_id,
                    SourcingRules.to_site_id == to_site_id,
                    SourcingRules.config_id == self.config_id,
                )
            ).order_by(SourcingRules.sourcing_priority).all()
            self._sourcing_cache[key] = rules
        return self._sourcing_cache[key]

    def _get_bom(self, product_id: str) -> List[ProductBom]:
        """Get BOM components for a product."""
        if product_id not in self._bom_cache:
            bom = self.db.query(ProductBom).filter(
                and_(
                    ProductBom.product_id == product_id,
                    ProductBom.config_id == self.config_id,
                )
            ).all()
            self._bom_cache[product_id] = bom
        return self._bom_cache[product_id]

    def _get_available_inventory(self, product_id: str, site_id: int) -> float:
        """Get available inventory for product at site."""
        key = f"{product_id}:{site_id}"
        if key not in self._inv_cache:
            inv = self.db.query(InvLevel).filter(
                and_(
                    InvLevel.product_id == product_id,
                    InvLevel.site_id == site_id,
                    InvLevel.config_id == self.config_id,
                )
            ).order_by(InvLevel.inventory_date.desc()).first()

            if inv:
                self._inv_cache[key] = inv.available_qty or inv.on_hand_qty or 0.0
            else:
                self._inv_cache[key] = 0.0
        return self._inv_cache[key]

    def _get_committed_quantity(self, product_id: str, site_id: int) -> float:
        """Get already-pegged quantity for product at site."""
        key = f"{product_id}:{site_id}"
        if key not in self._committed_cache:
            result = self.db.query(
                SupplyDemandPegging.pegged_quantity
            ).filter(
                and_(
                    SupplyDemandPegging.product_id == product_id,
                    SupplyDemandPegging.site_id == site_id,
                    SupplyDemandPegging.config_id == self.config_id,
                    SupplyDemandPegging.is_active == True,
                    SupplyDemandPegging.supply_type == "on_hand",
                )
            ).all()

            self._committed_cache[key] = sum(r[0] for r in result) if result else 0.0
        return self._committed_cache[key]

    def _get_safety_stock(self, product_id: str, site_id: int) -> float:
        """Get safety stock level for product at site."""
        policy = self.db.query(InvPolicy).filter(
            and_(
                InvPolicy.product_id == product_id,
                InvPolicy.site_id == site_id,
                InvPolicy.config_id == self.config_id,
            )
        ).first()

        if policy and policy.safety_stock_quantity:
            return policy.safety_stock_quantity
        return 0.0

    def _get_lead_time(self, rule: SourcingRules, to_site_id: int) -> int:
        """Get lead time for a sourcing rule."""
        # Try to get from transportation lane
        if rule.transportation_lane_id:
            lane = self.db.query(TransportationLane).filter(
                TransportationLane.id == int(rule.transportation_lane_id)
            ).first()
            if lane and lane.supply_lead_time:
                lt = lane.supply_lead_time
                if isinstance(lt, dict):
                    return int(lt.get("value", 3))
                return int(lt)

        # Default lead time
        return 3

    def _get_production_capacity(self, site: Site) -> float:
        """Get production capacity for a manufacturing site."""
        attrs = site.attributes or {}
        return float(attrs.get("production_capacity", 1000))

    def _get_production_lead_time(self, site: Site) -> int:
        """Get production lead time for a manufacturing site."""
        attrs = site.attributes or {}
        return int(attrs.get("production_lead_time", 3))

    def _get_vendor_lead_time(self, site: Site, product_id: str) -> int:
        """Get vendor lead time."""
        attrs = site.attributes or {}
        return int(attrs.get("lead_time", 7))

    def _get_vendor_capacity(self, site: Site, product_id: str) -> float:
        """Get vendor supply capacity. 0 = unlimited."""
        attrs = site.attributes or {}
        return float(attrs.get("capacity", 0))
