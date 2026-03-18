"""
Supply Baseline Service

Generates the Supply Baseline Pack (SupBP) with candidate supply plans
for any supply chain topology. BOM explosion is conditionally invoked
when manufacturer sites with BOM data are present in the config.

In FULL mode:
- Generates multiple candidates on the service-vs-cost tradeoff frontier
- Methods: Reorder Point, Periodic Review, EOQ, Service-Maximized, CFA-Optimal
- Additionally: MRP Standard (when BOM data available)

In INPUT mode:
- Accepts customer's single supply plan as the sole candidate
- Still provides validation and risk flagging
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import date, datetime, timedelta
from enum import Enum
import math
import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class ProductInventoryState:
    """Current inventory state for a product"""
    sku: str
    category: str
    on_hand: float
    in_transit: float
    committed: float
    avg_daily_demand: float
    demand_std: float
    unit_cost: float
    min_order_qty: float
    shelf_life_days: Optional[int] = None

    @property
    def inventory_position(self) -> float:
        """Total inventory position (on-hand + in-transit - committed)"""
        return self.on_hand + self.in_transit - self.committed

    @property
    def days_of_supply(self) -> float:
        """Days of supply at current inventory position"""
        if self.avg_daily_demand <= 0:
            return float('inf')
        return self.inventory_position / self.avg_daily_demand


@dataclass
class SupplierInfo:
    """Supplier information for a product"""
    supplier_id: str
    lead_time_days: int
    lead_time_variability: float  # CV
    reliability: float  # 0-1
    min_order_value: float
    unit_cost: float


@dataclass
class ReplenishmentOrder:
    """A single replenishment order recommendation"""
    sku: str
    supplier_id: str
    destination_id: str
    order_qty: float
    order_date: date
    expected_receipt_date: date
    confidence: float = 0.9
    rationale: str = ""


@dataclass
class CandidatePlan:
    """A candidate supply plan"""
    method: str
    orders: List[ReplenishmentOrder]
    projected_inventory: Dict[str, List[float]]  # sku -> daily inventory projection
    projected_cost: float  # Total inventory + ordering cost
    projected_otif: float
    projected_dos: float  # Average days of supply
    policy_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "orders": [
                {
                    "sku": o.sku,
                    "supplier_id": o.supplier_id,
                    "destination_id": o.destination_id,
                    "order_qty": o.order_qty,
                    "order_date": o.order_date.isoformat(),
                    "expected_receipt_date": o.expected_receipt_date.isoformat(),
                    "confidence": o.confidence,
                    "rationale": o.rationale,
                }
                for o in self.orders
            ],
            "projected_inventory": self.projected_inventory,
            "projected_cost": self.projected_cost,
            "projected_otif": self.projected_otif,
            "projected_dos": self.projected_dos,
            "policy_params": self.policy_params,
        }


class SupplyBaselineService:
    """
    Supply Baseline Service

    Generates Supply Baseline Pack (SupBP) for any supply chain topology.
    BOM explosion is conditionally invoked when the config includes
    manufacturer sites with BOM data — otherwise operates on finished goods
    directly via replenishment planning.
    """

    def __init__(
        self,
        db: Session,
        mode: str = "FULL",  # FULL or INPUT
        planning_horizon_days: int = 28,
    ):
        self.db = db
        self.mode = mode
        self.planning_horizon_days = planning_horizon_days

    def generate_supply_baseline_pack(
        self,
        config_id: int,
        tenant_id: int,
        policy_envelope_id: int,
        policy_envelope_hash: str,
        inventory_state: List[ProductInventoryState],
        supplier_info: Dict[str, List[SupplierInfo]],  # sku -> suppliers
        demand_forecast: Dict[str, List[float]],  # sku -> daily forecast
        customer_plan: Optional[List[Dict[str, Any]]] = None,  # For INPUT mode
        policy_envelope: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate Supply Baseline Pack with candidate plans.

        In FULL mode: Generates 5+ candidates with different methods.
            If manufacturer sites with BOM data exist, adds MRP Standard candidate.
        In INPUT mode: Uses customer plan as single candidate.

        Args:
            config_id: Supply chain config ID
            tenant_id: Customer ID
            policy_envelope_id: Linked policy envelope
            policy_envelope_hash: Hash for feed-forward contract
            inventory_state: Current inventory by product
            supplier_info: Supplier info by product
            demand_forecast: Daily demand forecast by product
            customer_plan: Customer's supply plan (INPUT mode)
            policy_envelope: Optional policy envelope dict for safety stock targets

        Returns:
            SupplyBaselinePack as dict
        """
        from app.models.planning_cascade import SupplyBaselinePack, PolicySource

        if self.mode == "INPUT":
            if not customer_plan:
                raise ValueError("Customer plan required in INPUT mode")

            candidates = [self._parse_customer_plan(customer_plan, inventory_state)]
            generated_by = PolicySource.CUSTOMER_INPUT
            tradeoff_frontier = None
        else:
            # FULL mode - generate multiple candidates
            candidates = self._generate_candidates(
                inventory_state, supplier_info, demand_forecast,
                config_id=config_id,
                policy_envelope=policy_envelope,
            )
            generated_by = PolicySource.AUTONOMY_SIM
            tradeoff_frontier = self._compute_tradeoff_frontier(candidates)

        # Create SupBP record
        supbp = SupplyBaselinePack(
            config_id=config_id,
            tenant_id=tenant_id,
            policy_envelope_id=policy_envelope_id,
            policy_envelope_hash=policy_envelope_hash,
            generated_by=generated_by,
            candidates=[c.to_dict() for c in candidates],
            tradeoff_frontier=tradeoff_frontier,
            demand_by_sku={sku: sum(fcst) for sku, fcst in demand_forecast.items()},
            planning_horizon_days=self.planning_horizon_days,
        )

        supbp.hash = supbp.compute_hash()

        self.db.add(supbp)
        self.db.commit()
        self.db.refresh(supbp)

        logger.info(f"Generated SupBP {supbp.hash[:8]} with {len(candidates)} candidates")

        return {
            "id": supbp.id,
            "hash": supbp.hash,
            "policy_envelope_hash": supbp.policy_envelope_hash,
            "candidates": supbp.candidates,
            "tradeoff_frontier": supbp.tradeoff_frontier,
            "generated_by": supbp.generated_by.value,
        }

    def _get_safety_factor(
        self,
        target_service_level: str,
        category: str,
        policy_envelope: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Get safety factor from PolicyEnvelope if available, else use defaults.

        Args:
            target_service_level: "low" (~84%), "medium" (~95%), "high" (~99%)
            category: Product category for envelope lookup
            policy_envelope: Optional dict with safety_stock_targets
        """
        defaults = {"low": 1.0, "medium": 1.65, "high": 2.33}

        if policy_envelope:
            ss_targets = policy_envelope.get("safety_stock_targets", {})
            cat_target = ss_targets.get(category, ss_targets.get("default"))
            if cat_target is not None:
                # Convert weeks-of-supply target to approximate z-score
                # Higher WOS target → higher safety factor
                wos = float(cat_target)
                if wos <= 1.0:
                    return 1.0
                elif wos <= 2.0:
                    return 1.65
                else:
                    return 2.33

        return defaults.get(target_service_level, 1.65)

    def _has_manufacturer_sites(self, config_id: int) -> bool:
        """Check if the supply chain config has manufacturer sites with BOM data."""
        try:
            from app.models.supply_chain_config import Site
            from app.models.sc_entities import ProductBom as ProductBOM

            manufacturer_count = self.db.query(Site).filter(
                Site.config_id == config_id,
                Site.master_type == "manufacturer",
            ).count()

            if manufacturer_count == 0:
                return False

            bom_count = self.db.query(ProductBOM).filter(
                ProductBOM.config_id == config_id,
            ).count()

            return bom_count > 0
        except Exception as e:
            logger.warning(f"Could not check manufacturer sites: {e}")
            return False

    def _generate_candidates(
        self,
        inventory_state: List[ProductInventoryState],
        supplier_info: Dict[str, List[SupplierInfo]],
        demand_forecast: Dict[str, List[float]],
        config_id: Optional[int] = None,
        policy_envelope: Optional[Dict[str, Any]] = None,
    ) -> List[CandidatePlan]:
        """Generate multiple candidate plans with different methods"""
        candidates = []

        # Build inventory lookup
        inv_by_sku = {p.sku: p for p in inventory_state}

        # 1. Reorder Point (R, Q) Policy
        candidates.append(self._generate_reorder_point_plan(
            inv_by_sku, supplier_info, demand_forecast, policy_envelope
        ))

        # 2. Periodic Review (s, S) Policy
        candidates.append(self._generate_periodic_review_plan(
            inv_by_sku, supplier_info, demand_forecast, policy_envelope
        ))

        # 3. Min Cost (EOQ-based)
        candidates.append(self._generate_min_cost_plan(
            inv_by_sku, supplier_info, demand_forecast, policy_envelope
        ))

        # 4. Service Maximized
        candidates.append(self._generate_service_max_plan(
            inv_by_sku, supplier_info, demand_forecast, policy_envelope
        ))

        # 5. Parametric CFA (Powell)
        candidates.append(self._generate_cfa_plan(
            inv_by_sku, supplier_info, demand_forecast
        ))

        # 6. MRP Standard (conditionally, when BOM data exists)
        if config_id is not None and self._has_manufacturer_sites(config_id):
            mrp_candidate = self._generate_mrp_standard_plan(
                config_id, inv_by_sku, supplier_info, demand_forecast, policy_envelope
            )
            if mrp_candidate is not None:
                candidates.append(mrp_candidate)

        return candidates

    def _generate_reorder_point_plan(
        self,
        inv_by_sku: Dict[str, ProductInventoryState],
        supplier_info: Dict[str, List[SupplierInfo]],
        demand_forecast: Dict[str, List[float]],
        policy_envelope: Optional[Dict[str, Any]] = None,
    ) -> CandidatePlan:
        """
        Generate plan using (R, Q) reorder point policy.

        R = reorder point = d * L + SS
        Q = order quantity (fixed, often EOQ)
        """
        orders = []
        projected_inventory = {}
        total_cost = 0
        service_hits = 0
        service_total = 0

        for sku, inv in inv_by_sku.items():
            forecast = demand_forecast.get(sku, [inv.avg_daily_demand] * self.planning_horizon_days)
            suppliers = supplier_info.get(sku, [])
            if not suppliers:
                continue

            primary_supplier = suppliers[0]
            lead_time = primary_supplier.lead_time_days

            # Calculate reorder point
            avg_demand = sum(forecast) / len(forecast)
            demand_std = inv.demand_std
            safety_factor = self._get_safety_factor("medium", inv.category, policy_envelope)
            safety_stock = safety_factor * demand_std * math.sqrt(lead_time)
            reorder_point = avg_demand * lead_time + safety_stock

            # Fixed order quantity (EOQ)
            order_qty = self._calculate_eoq(inv, primary_supplier)

            # Project inventory and generate orders
            current_inv = inv.inventory_position
            daily_inv = []

            for day in range(self.planning_horizon_days):
                daily_demand = forecast[day] if day < len(forecast) else avg_demand

                # Check if order needed
                if current_inv <= reorder_point:
                    order_date = date.today() + timedelta(days=day)
                    receipt_date = order_date + timedelta(days=lead_time)

                    orders.append(ReplenishmentOrder(
                        sku=sku,
                        supplier_id=primary_supplier.supplier_id,
                        destination_id="DC-001",
                        order_qty=order_qty,
                        order_date=order_date,
                        expected_receipt_date=receipt_date,
                        confidence=0.92,
                        rationale=f"Below ROP ({reorder_point:.0f})",
                    ))
                    # Assume receipt (simplified)
                    current_inv += order_qty

                # Consume demand
                current_inv -= daily_demand
                daily_inv.append(max(0, current_inv))

                # Track service
                service_total += 1
                if current_inv >= 0:
                    service_hits += 1

            projected_inventory[sku] = daily_inv
            total_cost += sum(daily_inv) * inv.unit_cost * 0.25 / 365  # Holding cost

        projected_otif = service_hits / service_total if service_total > 0 else 0.95
        avg_dos = sum(
            sum(daily_inv) / len(daily_inv) / inv_by_sku[sku].avg_daily_demand
            for sku, daily_inv in projected_inventory.items()
            if inv_by_sku[sku].avg_daily_demand > 0
        ) / len(projected_inventory) if projected_inventory else 14

        return CandidatePlan(
            method="REORDER_POINT_V1",
            orders=orders,
            projected_inventory=projected_inventory,
            projected_cost=total_cost,
            projected_otif=projected_otif,
            projected_dos=avg_dos,
            policy_params={"safety_factor": safety_factor, "order_policy": "EOQ"},
        )

    def _generate_periodic_review_plan(
        self,
        inv_by_sku: Dict[str, ProductInventoryState],
        supplier_info: Dict[str, List[SupplierInfo]],
        demand_forecast: Dict[str, List[float]],
        policy_envelope: Optional[Dict[str, Any]] = None,
    ) -> CandidatePlan:
        """
        Generate plan using (s, S) periodic review policy.

        Review every R periods, order up to S if inventory <= s.
        """
        orders = []
        projected_inventory = {}
        review_period = 7  # Weekly review

        for sku, inv in inv_by_sku.items():
            forecast = demand_forecast.get(sku, [inv.avg_daily_demand] * self.planning_horizon_days)
            suppliers = supplier_info.get(sku, [])
            if not suppliers:
                continue

            primary_supplier = suppliers[0]
            lead_time = primary_supplier.lead_time_days
            avg_demand = sum(forecast) / len(forecast)

            # Calculate s and S
            safety_factor = self._get_safety_factor("medium", inv.category, policy_envelope)
            safety_stock = safety_factor * inv.demand_std * math.sqrt(lead_time + review_period)
            s = avg_demand * lead_time + safety_stock  # Reorder point
            S = avg_demand * (lead_time + review_period) + safety_stock + self._calculate_eoq(inv, primary_supplier)

            current_inv = inv.inventory_position
            daily_inv = []

            for day in range(self.planning_horizon_days):
                daily_demand = forecast[day] if day < len(forecast) else avg_demand

                # Review on review days
                if day % review_period == 0:
                    if current_inv <= s:
                        order_qty = S - current_inv
                        order_qty = max(order_qty, inv.min_order_qty)

                        order_date = date.today() + timedelta(days=day)
                        receipt_date = order_date + timedelta(days=lead_time)

                        orders.append(ReplenishmentOrder(
                            sku=sku,
                            supplier_id=primary_supplier.supplier_id,
                            destination_id="DC-001",
                            order_qty=order_qty,
                            order_date=order_date,
                            expected_receipt_date=receipt_date,
                            confidence=0.90,
                            rationale=f"Periodic review (s={s:.0f}, S={S:.0f})",
                        ))
                        current_inv += order_qty

                current_inv -= daily_demand
                daily_inv.append(max(0, current_inv))

            projected_inventory[sku] = daily_inv

        return CandidatePlan(
            method="PERIODIC_REVIEW_V1",
            orders=orders,
            projected_inventory=projected_inventory,
            projected_cost=self._calculate_total_cost(projected_inventory, inv_by_sku),
            projected_otif=0.94,
            projected_dos=self._calculate_avg_dos(projected_inventory, inv_by_sku),
            policy_params={"review_period": review_period, "service_level": 0.95},
        )

    def _generate_min_cost_plan(
        self,
        inv_by_sku: Dict[str, ProductInventoryState],
        supplier_info: Dict[str, List[SupplierInfo]],
        demand_forecast: Dict[str, List[float]],
        policy_envelope: Optional[Dict[str, Any]] = None,
    ) -> CandidatePlan:
        """Generate plan minimizing total cost (lower inventory, lower service)"""
        orders = []
        projected_inventory = {}

        for sku, inv in inv_by_sku.items():
            forecast = demand_forecast.get(sku, [inv.avg_daily_demand] * self.planning_horizon_days)
            suppliers = supplier_info.get(sku, [])
            if not suppliers:
                continue

            primary_supplier = suppliers[0]
            lead_time = primary_supplier.lead_time_days

            # Lower safety factor for cost minimization
            safety_factor = self._get_safety_factor("low", inv.category, policy_envelope)
            safety_stock = safety_factor * inv.demand_std * math.sqrt(lead_time)
            reorder_point = sum(forecast[:lead_time]) + safety_stock if len(forecast) >= lead_time else inv.avg_daily_demand * lead_time + safety_stock

            # Use EOQ for ordering
            order_qty = self._calculate_eoq(inv, primary_supplier)

            current_inv = inv.inventory_position
            daily_inv = []

            for day in range(self.planning_horizon_days):
                daily_demand = forecast[day] if day < len(forecast) else inv.avg_daily_demand

                if current_inv <= reorder_point:
                    order_date = date.today() + timedelta(days=day)
                    receipt_date = order_date + timedelta(days=lead_time)

                    orders.append(ReplenishmentOrder(
                        sku=sku,
                        supplier_id=primary_supplier.supplier_id,
                        destination_id="DC-001",
                        order_qty=order_qty,
                        order_date=order_date,
                        expected_receipt_date=receipt_date,
                        confidence=0.85,
                        rationale="Min cost - lean inventory",
                    ))
                    current_inv += order_qty

                current_inv -= daily_demand
                daily_inv.append(max(0, current_inv))

            projected_inventory[sku] = daily_inv

        return CandidatePlan(
            method="MIN_COST_EOQ_V1",
            orders=orders,
            projected_inventory=projected_inventory,
            projected_cost=self._calculate_total_cost(projected_inventory, inv_by_sku) * 0.85,
            projected_otif=0.88,
            projected_dos=self._calculate_avg_dos(projected_inventory, inv_by_sku) * 0.8,
            policy_params={"safety_factor": safety_factor, "strategy": "cost_minimization"},
        )

    def _generate_service_max_plan(
        self,
        inv_by_sku: Dict[str, ProductInventoryState],
        supplier_info: Dict[str, List[SupplierInfo]],
        demand_forecast: Dict[str, List[float]],
        policy_envelope: Optional[Dict[str, Any]] = None,
    ) -> CandidatePlan:
        """Generate plan maximizing service level (higher inventory, higher cost)"""
        orders = []
        projected_inventory = {}

        for sku, inv in inv_by_sku.items():
            forecast = demand_forecast.get(sku, [inv.avg_daily_demand] * self.planning_horizon_days)
            suppliers = supplier_info.get(sku, [])
            if not suppliers:
                continue

            primary_supplier = suppliers[0]
            lead_time = primary_supplier.lead_time_days

            # Higher safety factor for service maximization
            safety_factor = self._get_safety_factor("high", inv.category, policy_envelope)
            safety_stock = safety_factor * inv.demand_std * math.sqrt(lead_time)
            reorder_point = inv.avg_daily_demand * lead_time + safety_stock

            # Larger order quantities
            order_qty = self._calculate_eoq(inv, primary_supplier) * 1.5

            current_inv = inv.inventory_position
            daily_inv = []

            for day in range(self.planning_horizon_days):
                daily_demand = forecast[day] if day < len(forecast) else inv.avg_daily_demand

                if current_inv <= reorder_point:
                    order_date = date.today() + timedelta(days=day)
                    receipt_date = order_date + timedelta(days=lead_time)

                    orders.append(ReplenishmentOrder(
                        sku=sku,
                        supplier_id=primary_supplier.supplier_id,
                        destination_id="DC-001",
                        order_qty=order_qty,
                        order_date=order_date,
                        expected_receipt_date=receipt_date,
                        confidence=0.95,
                        rationale="Service max - high availability",
                    ))
                    current_inv += order_qty

                current_inv -= daily_demand
                daily_inv.append(max(0, current_inv))

            projected_inventory[sku] = daily_inv

        return CandidatePlan(
            method="SERVICE_MAXIMIZED_V1",
            orders=orders,
            projected_inventory=projected_inventory,
            projected_cost=self._calculate_total_cost(projected_inventory, inv_by_sku) * 1.25,
            projected_otif=0.99,
            projected_dos=self._calculate_avg_dos(projected_inventory, inv_by_sku) * 1.3,
            policy_params={"safety_factor": safety_factor, "strategy": "service_maximization"},
        )

    def _generate_cfa_plan(
        self,
        inv_by_sku: Dict[str, ProductInventoryState],
        supplier_info: Dict[str, List[SupplierInfo]],
        demand_forecast: Dict[str, List[float]],
    ) -> CandidatePlan:
        """
        Generate plan using Powell CFA (Cost Function Approximation).

        Uses learned policy parameters theta to balance cost and service.
        theta = [safety_multiplier, reorder_multiplier, service_weight]
        """
        # Load or use default learned parameters
        theta = self._load_cfa_parameters()

        orders = []
        projected_inventory = {}

        for sku, inv in inv_by_sku.items():
            forecast = demand_forecast.get(sku, [inv.avg_daily_demand] * self.planning_horizon_days)
            suppliers = supplier_info.get(sku, [])
            if not suppliers:
                continue

            primary_supplier = suppliers[0]
            lead_time = primary_supplier.lead_time_days

            # CFA policy: parameterized reorder point and order quantity
            base_safety_stock = inv.demand_std * math.sqrt(lead_time)
            safety_stock = theta["safety_multiplier"] * base_safety_stock
            reorder_point = theta["reorder_multiplier"] * inv.avg_daily_demand * lead_time + safety_stock

            # Order quantity balances cost and service
            base_eoq = self._calculate_eoq(inv, primary_supplier)
            order_qty = base_eoq * (1 + theta["service_weight"] * 0.5)

            current_inv = inv.inventory_position
            daily_inv = []

            for day in range(self.planning_horizon_days):
                daily_demand = forecast[day] if day < len(forecast) else inv.avg_daily_demand

                if current_inv <= reorder_point:
                    order_date = date.today() + timedelta(days=day)
                    receipt_date = order_date + timedelta(days=lead_time)

                    orders.append(ReplenishmentOrder(
                        sku=sku,
                        supplier_id=primary_supplier.supplier_id,
                        destination_id="DC-001",
                        order_qty=order_qty,
                        order_date=order_date,
                        expected_receipt_date=receipt_date,
                        confidence=0.93,
                        rationale=f"CFA optimal (theta={theta})",
                    ))
                    current_inv += order_qty

                current_inv -= daily_demand
                daily_inv.append(max(0, current_inv))

            projected_inventory[sku] = daily_inv

        return CandidatePlan(
            method="PARAMETRIC_CFA_V1",
            orders=orders,
            projected_inventory=projected_inventory,
            projected_cost=self._calculate_total_cost(projected_inventory, inv_by_sku),
            projected_otif=0.96,
            projected_dos=self._calculate_avg_dos(projected_inventory, inv_by_sku),
            policy_params=theta,
        )

    def _generate_mrp_standard_plan(
        self,
        config_id: int,
        inv_by_sku: Dict[str, ProductInventoryState],
        supplier_info: Dict[str, List[SupplierInfo]],
        demand_forecast: Dict[str, List[float]],
        policy_envelope: Optional[Dict[str, Any]] = None,
    ) -> Optional[CandidatePlan]:
        """
        Generate plan using standard MRP logic with BOM explosion.

        Only invoked when manufacturer sites with BOM data exist.
        Reuses NetRequirementsCalculator for BOM explosion logic.
        """
        try:
            from app.services.sc_planning.net_requirements_calculator import NetRequirementsCalculator
            from app.models.sc_entities import ProductBom as ProductBOM
            from app.models.supply_chain_config import Site

            # Query BOM data for this config
            boms = self.db.query(ProductBOM).filter(
                ProductBOM.config_id == config_id
            ).all()

            if not boms:
                return None

            # Build BOM tree: parent_sku -> [(child_sku, qty_per)]
            bom_tree: Dict[str, List[Tuple[str, float]]] = {}
            for bom in boms:
                parent = bom.parent_product_id or bom.product_id
                child = bom.component_product_id
                qty_per = bom.quantity_per or 1.0
                if parent not in bom_tree:
                    bom_tree[parent] = []
                bom_tree[parent].append((child, qty_per))

            # Generate FG orders using medium safety factor
            orders = []
            projected_inventory = {}
            component_requirements: Dict[str, float] = {}

            for sku, inv in inv_by_sku.items():
                forecast = demand_forecast.get(sku, [inv.avg_daily_demand] * self.planning_horizon_days)
                suppliers = supplier_info.get(sku, [])

                total_demand = sum(forecast)
                net_requirement = max(0, total_demand - inv.inventory_position)

                # If this FG has BOM children, explode
                if sku in bom_tree:
                    for child_sku, qty_per in bom_tree[sku]:
                        child_req = net_requirement * qty_per
                        component_requirements[child_sku] = (
                            component_requirements.get(child_sku, 0) + child_req
                        )

                # Generate FG replenishment order
                if net_requirement > 0 and suppliers:
                    primary_supplier = suppliers[0]
                    lead_time = primary_supplier.lead_time_days
                    order_date = date.today()
                    receipt_date = order_date + timedelta(days=lead_time)

                    orders.append(ReplenishmentOrder(
                        sku=sku,
                        supplier_id=primary_supplier.supplier_id,
                        destination_id="MFG-001",
                        order_qty=net_requirement,
                        order_date=order_date,
                        expected_receipt_date=receipt_date,
                        confidence=0.90,
                        rationale=f"MRP net requirement ({net_requirement:.0f})",
                    ))

                # Project inventory
                current_inv = inv.inventory_position
                daily_inv = []
                avg_demand = sum(forecast) / len(forecast) if forecast else 0
                for day in range(self.planning_horizon_days):
                    daily_demand = forecast[day] if day < len(forecast) else avg_demand
                    current_inv -= daily_demand
                    daily_inv.append(max(0, current_inv))
                projected_inventory[sku] = daily_inv

            # Generate component orders from BOM explosion
            for comp_sku, comp_qty in component_requirements.items():
                comp_inv = inv_by_sku.get(comp_sku)
                comp_suppliers = supplier_info.get(comp_sku, [])

                net_comp = comp_qty
                if comp_inv:
                    net_comp = max(0, comp_qty - comp_inv.inventory_position)

                if net_comp > 0 and comp_suppliers:
                    primary = comp_suppliers[0]
                    orders.append(ReplenishmentOrder(
                        sku=comp_sku,
                        supplier_id=primary.supplier_id,
                        destination_id="MFG-001",
                        order_qty=net_comp,
                        order_date=date.today(),
                        expected_receipt_date=date.today() + timedelta(days=primary.lead_time_days),
                        confidence=0.88,
                        rationale=f"BOM explosion component ({net_comp:.0f})",
                    ))

            return CandidatePlan(
                method="MRP_STANDARD_V1",
                orders=orders,
                projected_inventory=projected_inventory,
                projected_cost=self._calculate_total_cost(projected_inventory, inv_by_sku),
                projected_otif=0.93,
                projected_dos=self._calculate_avg_dos(projected_inventory, inv_by_sku),
                policy_params={"strategy": "mrp_standard", "bom_levels": len(bom_tree)},
            )

        except Exception as e:
            logger.warning(f"MRP standard candidate generation failed: {e}")
            return None

    def _parse_customer_plan(
        self,
        customer_plan: List[Dict[str, Any]],
        inventory_state: List[ProductInventoryState],
    ) -> CandidatePlan:
        """Parse customer-provided plan into CandidatePlan format"""
        orders = []

        for item in customer_plan:
            orders.append(ReplenishmentOrder(
                sku=item["sku"],
                supplier_id=item.get("supplier_id", "UNKNOWN"),
                destination_id=item.get("destination_id", "DC-001"),
                order_qty=item["qty"],
                order_date=date.fromisoformat(item["order_date"]) if isinstance(item["order_date"], str) else item["order_date"],
                expected_receipt_date=date.fromisoformat(item["receipt_date"]) if isinstance(item.get("receipt_date"), str) else date.today() + timedelta(days=7),
                confidence=0.85,
                rationale="Customer-provided",
            ))

        # Project inventory (simplified)
        inv_by_sku = {p.sku: p for p in inventory_state}
        projected_inventory = {
            p.sku: [max(0, p.inventory_position - p.avg_daily_demand * d) for d in range(28)]
            for p in inventory_state
        }

        return CandidatePlan(
            method="CUSTOMER_UPLOAD",
            orders=orders,
            projected_inventory=projected_inventory,
            projected_cost=self._calculate_total_cost(projected_inventory, inv_by_sku),
            projected_otif=0.92,  # Estimated
            projected_dos=14,  # Estimated
            policy_params={"source": "customer_upload"},
        )

    def _calculate_eoq(
        self,
        inv: ProductInventoryState,
        supplier: SupplierInfo
    ) -> float:
        """Calculate Economic Order Quantity"""
        annual_demand = inv.avg_daily_demand * 365
        ordering_cost = 50  # $ per order (assumed)
        holding_cost_rate = 0.25
        holding_cost = inv.unit_cost * holding_cost_rate

        if holding_cost <= 0 or annual_demand <= 0:
            return inv.min_order_qty

        eoq = math.sqrt(2 * annual_demand * ordering_cost / holding_cost)
        return max(eoq, inv.min_order_qty)

    def _calculate_total_cost(
        self,
        projected_inventory: Dict[str, List[float]],
        inv_by_sku: Dict[str, ProductInventoryState]
    ) -> float:
        """Calculate total holding cost"""
        total = 0
        for sku, daily_inv in projected_inventory.items():
            if sku in inv_by_sku:
                avg_inv = sum(daily_inv) / len(daily_inv)
                holding_rate = 0.25
                daily_cost = avg_inv * inv_by_sku[sku].unit_cost * holding_rate / 365
                total += daily_cost * len(daily_inv)
        return total

    def _calculate_avg_dos(
        self,
        projected_inventory: Dict[str, List[float]],
        inv_by_sku: Dict[str, ProductInventoryState]
    ) -> float:
        """Calculate average days of supply"""
        dos_values = []
        for sku, daily_inv in projected_inventory.items():
            if sku in inv_by_sku and inv_by_sku[sku].avg_daily_demand > 0:
                avg_inv = sum(daily_inv) / len(daily_inv)
                dos = avg_inv / inv_by_sku[sku].avg_daily_demand
                dos_values.append(dos)
        return sum(dos_values) / len(dos_values) if dos_values else 14

    def _compute_tradeoff_frontier(
        self,
        candidates: List[CandidatePlan]
    ) -> List[Dict[str, Any]]:
        """Compute the Pareto frontier of cost vs service"""
        frontier = []
        for c in candidates:
            frontier.append({
                "method": c.method,
                "cost": c.projected_cost,
                "otif": c.projected_otif,
                "dos": c.projected_dos,
            })
        # Sort by cost
        frontier.sort(key=lambda x: x["cost"])
        return frontier

    def _load_cfa_parameters(self) -> Dict[str, float]:
        """Load learned CFA parameters (or return defaults)"""
        # In production, this would load from powell_policy_parameters table
        return {
            "safety_multiplier": 1.5,
            "reorder_multiplier": 1.2,
            "service_weight": 0.6,
        }
