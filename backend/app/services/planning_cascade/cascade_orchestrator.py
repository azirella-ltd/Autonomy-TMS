"""
Cascade Orchestrator

Orchestrates the full planning cascade from S&OP through Allocation Commit.
Manages the feed-forward contracts and feed-back signals.

Cascade Flow:
1. S&OP Layer → Policy Envelope (θ_SOP)
2. Supply Baseline Layer → Supply Baseline Pack (SupBP)
3. Supply Agent → Supply Commit (SC)
4. Allocation Solver → Solver Baseline Pack (SBP)
5. Allocation Agent → Allocation Commit (AC)
6. Execution → Feed-back Signals → Re-tune upstream

Supports both FULL mode (all layers) and INPUT mode (agents only).
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import date, datetime
from enum import Enum
import logging

from sqlalchemy.orm import Session

from .sop_service import SOPService, SOPMode, SOPParameters, create_default_sop_parameters_for_food_dist
from .supply_baseline_service import SupplyBaselineService, ProductInventoryState, SupplierInfo
from .supply_agent import SupplyAgent
from .allocation_agent import AllocationAgent

logger = logging.getLogger(__name__)


class CascadeMode(Enum):
    """Operating mode for the cascade"""
    FULL = "full"      # All layers (S&OP simulation + Supply Baseline candidates + Agents)
    INPUT = "input"    # Agents only (customer provides S&OP params + single plan)


@dataclass
class CascadeResult:
    """Result of running the planning cascade"""
    policy_envelope: Dict[str, Any]
    supply_baseline_pack: Dict[str, Any]
    supply_commit: Dict[str, Any]
    allocation_commit: Dict[str, Any]

    # Summary metrics
    total_orders: int = 0
    total_allocations: int = 0
    integrity_violations: int = 0
    risk_flags: int = 0
    requires_review: bool = False


class CascadeOrchestrator:
    """
    Orchestrates the full planning cascade.

    In FULL mode:
    - S&OP simulation generates optimized policy parameters
    - Supply Baseline generates multiple candidate plans (with BOM explosion when applicable)
    - Agents select from candidates and apply policies

    In INPUT mode:
    - Customer provides policy parameters
    - Customer provides single replenishment plan
    - Agents validate, flag risks, and govern execution
    """

    def __init__(
        self,
        db: Session,
        mode: CascadeMode = CascadeMode.INPUT,
        agent_mode: str = "copilot",  # "copilot" or "autonomous"
    ):
        self.db = db
        self.mode = mode
        self.agent_mode = agent_mode

        # Initialize services
        sop_mode = SOPMode.FULL if mode == CascadeMode.FULL else SOPMode.INPUT
        self.sop_service = SOPService(db, sop_mode)
        self.supply_baseline_service = SupplyBaselineService(db, mode="FULL" if mode == CascadeMode.FULL else "INPUT")
        self.supply_agent = SupplyAgent(db)
        self.allocation_agent = AllocationAgent(db)

    def run_cascade(
        self,
        config_id: int,
        group_id: int,
        user_id: Optional[int] = None,
        sop_params: Optional[SOPParameters] = None,
        customer_plan: Optional[List[Dict[str, Any]]] = None,
        inventory_state: Optional[List[ProductInventoryState]] = None,
        supplier_info: Optional[Dict[str, List[SupplierInfo]]] = None,
        demand_forecast: Optional[Dict[str, List[float]]] = None,
        demand_by_segment: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> CascadeResult:
        """
        Run the full planning cascade.

        Args:
            config_id: Supply chain config ID
            group_id: Group ID
            user_id: User running the cascade
            sop_params: S&OP parameters (optional, uses defaults if not provided)
            customer_plan: Customer's replenishment plan (INPUT mode)
            inventory_state: Current inventory state
            supplier_info: Supplier information
            demand_forecast: Daily demand forecast by SKU
            demand_by_segment: Demand by customer segment

        Returns:
            CascadeResult with all artifacts
        """
        logger.info(f"Starting planning cascade in {self.mode.value} mode")

        # =================================================================
        # Step 1: S&OP Layer - Create/Get Policy Envelope
        # =================================================================
        if sop_params is None:
            sop_params = create_default_sop_parameters_for_food_dist()

        policy_envelope = self.sop_service.create_policy_envelope(
            config_id=config_id,
            group_id=group_id,
            params=sop_params,
            user_id=user_id,
        )

        logger.info(f"Step 1 complete: Policy Envelope {policy_envelope['hash'][:8]}")

        # =================================================================
        # Step 2: Supply Baseline Layer - Generate Supply Baseline Pack
        # =================================================================
        if inventory_state is None:
            inventory_state = self._load_inventory_state(config_id)

        if supplier_info is None:
            supplier_info = self._load_supplier_info(config_id)

        if demand_forecast is None:
            demand_forecast = self._load_demand_forecast(config_id, inventory_state)

        supply_baseline_pack = self.supply_baseline_service.generate_supply_baseline_pack(
            config_id=config_id,
            group_id=group_id,
            policy_envelope_id=policy_envelope["id"],
            policy_envelope_hash=policy_envelope["hash"],
            inventory_state=inventory_state,
            supplier_info=supplier_info,
            demand_forecast=demand_forecast,
            customer_plan=customer_plan,
        )

        logger.info(f"Step 2 complete: SupBP {supply_baseline_pack['hash'][:8]} with {len(supply_baseline_pack['candidates'])} candidates")

        # =================================================================
        # Step 3: Supply Agent - Generate Supply Commit
        # =================================================================
        inventory_state_dict = {p.sku: {
            "inventory_position": p.inventory_position,
            "avg_daily_demand": p.avg_daily_demand,
            "demand_std": p.demand_std,
            "unit_cost": p.unit_cost,
            "min_order_qty": p.min_order_qty,
            "category": p.category,
        } for p in inventory_state}

        supply_commit = self.supply_agent.generate_supply_commit(
            config_id=config_id,
            group_id=group_id,
            supply_baseline_pack_id=supply_baseline_pack["id"],
            supply_baseline_pack_hash=supply_baseline_pack["hash"],
            policy_envelope=policy_envelope,
            inventory_state=inventory_state_dict,
            mode=self.agent_mode,
        )

        logger.info(f"Step 3 complete: Supply Commit {supply_commit['hash'][:8]}, status={supply_commit['status']}")

        # =================================================================
        # Step 4: Allocation Agent - Generate Allocation Commit
        # =================================================================
        if demand_by_segment is None:
            demand_by_segment = self._load_demand_by_segment(config_id, inventory_state)

        allocation_commit = self.allocation_agent.generate_allocation_commit(
            config_id=config_id,
            group_id=group_id,
            supply_commit_id=supply_commit["id"],
            supply_commit_hash=supply_commit["hash"],
            policy_envelope=policy_envelope,
            demand_by_segment=demand_by_segment,
            mode=self.agent_mode,
        )

        logger.info(f"Step 4 complete: Allocation Commit {allocation_commit['hash'][:8]}, status={allocation_commit['status']}")

        # =================================================================
        # Build result summary
        # =================================================================
        total_orders = len(supply_commit.get("recommendations", []))
        total_allocations = len(allocation_commit.get("allocations", []))
        integrity_violations = (
            len(supply_commit.get("integrity_violations") or []) +
            len(allocation_commit.get("integrity_violations") or [])
        )
        risk_flags = (
            len(supply_commit.get("risk_flags") or []) +
            len(allocation_commit.get("risk_flags") or [])
        )
        requires_review = (
            supply_commit.get("requires_review", False) or
            allocation_commit.get("requires_review", False)
        )

        logger.info(
            f"Cascade complete: {total_orders} orders, {total_allocations} allocations, "
            f"{integrity_violations} violations, {risk_flags} risk flags"
        )

        return CascadeResult(
            policy_envelope=policy_envelope,
            supply_baseline_pack=supply_baseline_pack,
            supply_commit=supply_commit,
            allocation_commit=allocation_commit,
            total_orders=total_orders,
            total_allocations=total_allocations,
            integrity_violations=integrity_violations,
            risk_flags=risk_flags,
            requires_review=requires_review,
        )

    def run_cascade_for_food_dist(
        self,
        config_id: int,
        group_id: int,
        user_id: Optional[int] = None,
    ) -> CascadeResult:
        """
        Run the cascade with Food Dist distributor defaults.

        Convenience method that uses the Food Dist data model.
        """
        from app.services.food_dist_config_generator import FoodDistCascadeDataGenerator

        # Generate Food Dist data using synchronous helper
        generator = FoodDistCascadeDataGenerator()
        food_dist_data = generator.generate_inventory_and_demand_data()

        # Convert to our data structures
        inventory_state = [
            ProductInventoryState(
                sku=p["sku"],
                category=p["category"],
                on_hand=p["on_hand"],
                in_transit=p["in_transit"],
                committed=p["committed"],
                avg_daily_demand=p["avg_daily_demand"],
                demand_std=p["demand_std"],
                unit_cost=p["unit_cost"],
                min_order_qty=p["min_order_qty"],
                shelf_life_days=p.get("shelf_life_days"),
            )
            for p in food_dist_data["products"]
        ]

        supplier_info = {}
        for sku, suppliers in food_dist_data["suppliers_by_sku"].items():
            supplier_info[sku] = [
                SupplierInfo(
                    supplier_id=s["supplier_id"],
                    lead_time_days=s["lead_time_days"],
                    lead_time_variability=s["lead_time_variability"],
                    reliability=s["reliability"],
                    min_order_value=s["min_order_value"],
                    unit_cost=s["unit_cost"],
                )
                for s in suppliers
            ]

        demand_forecast = food_dist_data["demand_forecast"]
        demand_by_segment = food_dist_data["demand_by_segment"]

        return self.run_cascade(
            config_id=config_id,
            group_id=group_id,
            user_id=user_id,
            inventory_state=inventory_state,
            supplier_info=supplier_info,
            demand_forecast=demand_forecast,
            demand_by_segment=demand_by_segment,
        )

    def get_cascade_status(
        self,
        config_id: int,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get status of recent cascade runs.

        Returns summary of commits by status.
        """
        from app.models.planning_cascade import SupplyCommit, AllocationCommit

        # Query recent commits
        supply_query = self.db.query(SupplyCommit).filter(
            SupplyCommit.config_id == config_id
        )
        alloc_query = self.db.query(AllocationCommit).filter(
            AllocationCommit.config_id == config_id
        )

        if since:
            supply_query = supply_query.filter(SupplyCommit.created_at >= since)
            alloc_query = alloc_query.filter(AllocationCommit.created_at >= since)

        supply_commits = supply_query.order_by(SupplyCommit.created_at.desc()).limit(10).all()
        alloc_commits = alloc_query.order_by(AllocationCommit.created_at.desc()).limit(10).all()

        return {
            "supply_commits": [
                {
                    "id": c.id,
                    "hash": c.hash[:8],
                    "status": c.status.value,
                    "requires_review": c.requires_review,
                    "created_at": c.created_at.isoformat(),
                }
                for c in supply_commits
            ],
            "allocation_commits": [
                {
                    "id": c.id,
                    "hash": c.hash[:8],
                    "status": c.status.value,
                    "requires_review": c.requires_review,
                    "created_at": c.created_at.isoformat(),
                }
                for c in alloc_commits
            ],
            "pending_review_count": sum(
                1 for c in supply_commits if c.requires_review
            ) + sum(
                1 for c in alloc_commits if c.requires_review
            ),
        }

    def record_feed_back_signal(
        self,
        config_id: int,
        group_id: int,
        signal_type: str,
        metric_name: str,
        metric_value: float,
        threshold: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
        supply_commit_id: Optional[int] = None,
        allocation_commit_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Record a feed-back signal from execution.

        These signals inform upstream parameter re-tuning.

        Args:
            config_id: Supply chain config ID
            group_id: Group ID
            signal_type: Type of signal (actual_otif, allocation_shortfall, etc.)
            metric_name: Name of the metric
            metric_value: Measured value
            threshold: Threshold that was breached (if any)
            details: Additional details
            supply_commit_id: Link to Supply Commit
            allocation_commit_id: Link to Allocation Commit

        Returns:
            Created FeedBackSignal as dict
        """
        from app.models.planning_cascade import FeedBackSignal

        # Determine fed_back_to based on signal type
        fed_back_to_map = {
            "actual_otif": "supply_agent",
            "allocation_shortfall": "supply_agent",
            "execution_adherence": "allocation_agent",
            "expedite_frequency": "sop",
            "eo_writeoff": "sop",
            "override_outcome": "sop",
        }
        fed_back_to = fed_back_to_map.get(signal_type, "supply_agent")

        # Calculate deviation if threshold provided
        deviation = None
        if threshold is not None and threshold != 0:
            deviation = (metric_value - threshold) / threshold

        signal = FeedBackSignal(
            config_id=config_id,
            group_id=group_id,
            signal_type=signal_type,
            measured_at_layer="execution",
            fed_back_to=fed_back_to,
            metric_name=metric_name,
            metric_value=metric_value,
            threshold=threshold,
            deviation=deviation,
            details=details,
            supply_commit_id=supply_commit_id,
            allocation_commit_id=allocation_commit_id,
        )

        self.db.add(signal)
        self.db.commit()
        self.db.refresh(signal)

        logger.info(f"Recorded feed-back signal: {signal_type} = {metric_value}")

        return {
            "id": signal.id,
            "signal_type": signal.signal_type,
            "metric_name": signal.metric_name,
            "metric_value": signal.metric_value,
            "fed_back_to": signal.fed_back_to,
            "deviation": signal.deviation,
        }

    def _load_inventory_state(
        self,
        config_id: int
    ) -> List[ProductInventoryState]:
        """
        Load inventory state from DB for a config.

        Queries Product, InvLevel, Forecast, and InvPolicy tables.
        Raises ValueError if no products exist for the config.
        """
        from app.models.sc_entities import Product, InvLevel, InvPolicy, Forecast
        from sqlalchemy import func

        products = self.db.query(Product).filter(
            Product.config_id == config_id,
        ).all()

        if not products:
            raise ValueError(
                f"No products found for config_id={config_id}. "
                "Seed product data via synthetic data generator or supply chain config."
            )

        inventory_state = []
        for product in products:
            # Latest inventory snapshot
            inv = self.db.query(InvLevel).filter(
                InvLevel.product_id == product.id,
                InvLevel.config_id == config_id,
            ).order_by(InvLevel.inventory_date.desc().nullslast()).first()

            on_hand = float(inv.on_hand_qty or 0) if inv else 0.0
            in_transit = float(inv.in_transit_qty or 0) if inv else 0.0
            committed = float(inv.allocated_qty or 0) if inv else 0.0

            # Demand statistics from forecasts
            demand_stats = self.db.query(
                func.avg(Forecast.forecast_quantity).label("avg_demand"),
                func.stddev(Forecast.forecast_quantity).label("demand_std"),
            ).filter(
                Forecast.product_id == product.id,
                Forecast.config_id == config_id,
            ).first()

            avg_demand = float(demand_stats.avg_demand or 0) if demand_stats and demand_stats.avg_demand else 0.0
            demand_std = float(demand_stats.demand_std or 0) if demand_stats and demand_stats.demand_std else 0.0

            # Min order qty from inventory policy
            policy = self.db.query(InvPolicy).filter(
                InvPolicy.product_id == product.id,
                InvPolicy.config_id == config_id,
            ).first()

            min_order_qty = float(policy.min_order_quantity or 1) if policy and policy.min_order_quantity else 1.0

            inventory_state.append(ProductInventoryState(
                sku=product.id,
                category=product.category or "default",
                on_hand=on_hand,
                in_transit=in_transit,
                committed=committed,
                avg_daily_demand=avg_demand,
                demand_std=demand_std,
                unit_cost=float(product.unit_cost or 0),
                min_order_qty=min_order_qty,
            ))

        return inventory_state

    def _load_supplier_info(
        self,
        config_id: int
    ) -> Dict[str, List[SupplierInfo]]:
        """
        Load supplier info from DB for a config.

        Queries VendorProduct and VendorLeadTime tables via SourcingRules.
        Falls back to SourcingRules if vendor tables have no data.
        """
        from app.models.sc_entities import SourcingRules, Product

        products = self.db.query(Product).filter(
            Product.config_id == config_id,
        ).all()

        if not products:
            raise ValueError(
                f"No products found for config_id={config_id}. "
                "Seed product data first."
            )

        supplier_info: Dict[str, List[SupplierInfo]] = {}

        for product in products:
            rules = self.db.query(SourcingRules).filter(
                SourcingRules.product_id == product.id,
                SourcingRules.config_id == config_id,
                SourcingRules.sourcing_rule_type == "buy",
            ).order_by(SourcingRules.sourcing_priority).all()

            if not rules:
                # Try vendor product table
                try:
                    from app.models.supplier import VendorProduct, VendorLeadTime
                    vps = self.db.query(VendorProduct).filter(
                        VendorProduct.product_id == product.id,
                        VendorProduct.is_active == "true",
                    ).all()

                    suppliers = []
                    for vp in vps:
                        lt = self.db.query(VendorLeadTime).filter(
                            VendorLeadTime.tpartner_id == vp.tpartner_id,
                            VendorLeadTime.product_id == product.id,
                        ).first()
                        lead_time = float(lt.lead_time_days) if lt else 7.0
                        variability = float(lt.lead_time_variability_days or 0) / lead_time if lt and lt.lead_time_variability_days and lead_time > 0 else 0.2

                        suppliers.append(SupplierInfo(
                            supplier_id=vp.tpartner_id,
                            lead_time_days=lead_time,
                            lead_time_variability=variability,
                            reliability=0.95,
                            min_order_value=float(vp.minimum_order_quantity or 0) * float(vp.vendor_unit_cost),
                            unit_cost=float(vp.vendor_unit_cost),
                        ))

                    if suppliers:
                        supplier_info[product.id] = suppliers
                except Exception:
                    pass
                continue

            suppliers = []
            for rule in rules:
                supplier_id = rule.tpartner_id or f"from-site-{rule.from_site_id}"
                suppliers.append(SupplierInfo(
                    supplier_id=supplier_id,
                    lead_time_days=7.0,  # Default; refined by VendorLeadTime if available
                    lead_time_variability=0.2,
                    reliability=float(rule.sourcing_ratio or 0.95),
                    min_order_value=float(rule.min_quantity or 0) * float(product.unit_cost or 1),
                    unit_cost=float(product.unit_cost or 0),
                ))

            if suppliers:
                supplier_info[product.id] = suppliers

        if not supplier_info:
            raise ValueError(
                f"No supplier information found for config_id={config_id}. "
                "Seed sourcing rules or vendor product data first."
            )

        return supplier_info

    def _load_demand_forecast(
        self,
        config_id: int,
        inventory_state: List[ProductInventoryState],
        horizon_days: int = 28,
    ) -> Dict[str, List[float]]:
        """
        Load demand forecast from DB, falling back to avg_daily_demand.

        Queries Forecast table; if no forecasts exist, uses avg_daily_demand
        from the inventory state as a flat forecast.
        """
        from app.models.sc_entities import Forecast

        forecast: Dict[str, List[float]] = {}

        for p in inventory_state:
            rows = self.db.query(Forecast).filter(
                Forecast.product_id == p.sku,
                Forecast.config_id == config_id,
            ).order_by(Forecast.forecast_date).limit(horizon_days).all()

            if rows:
                forecast[p.sku] = [float(r.forecast_quantity or 0) for r in rows]
                # Pad if fewer rows than horizon
                while len(forecast[p.sku]) < horizon_days:
                    forecast[p.sku].append(forecast[p.sku][-1] if forecast[p.sku] else p.avg_daily_demand)
            else:
                # Fallback: flat forecast from avg daily demand
                forecast[p.sku] = [p.avg_daily_demand for _ in range(horizon_days)]

        return forecast

    def _load_demand_by_segment(
        self,
        config_id: int,
        inventory_state: List[ProductInventoryState],
    ) -> Dict[str, Dict[str, float]]:
        """
        Load demand by customer segment from DB.

        Queries OutboundOrderLine priority_code to derive segment demand.
        Falls back to proportional split if no order data exists.
        """
        from app.models.sc_entities import OutboundOrderLine
        from sqlalchemy import func

        # Map priority codes to segments
        priority_to_segment = {
            "VIP": "strategic",
            "HIGH": "strategic",
            "STANDARD": "standard",
            "LOW": "transactional",
        }
        segments = ["strategic", "standard", "transactional"]
        result: Dict[str, Dict[str, float]] = {seg: {} for seg in segments}

        has_data = False
        for p in inventory_state:
            rows = self.db.query(
                OutboundOrderLine.priority_code,
                func.sum(OutboundOrderLine.ordered_quantity).label("total_qty"),
            ).filter(
                OutboundOrderLine.product_id == p.sku,
                OutboundOrderLine.config_id == config_id,
            ).group_by(OutboundOrderLine.priority_code).all()

            if rows:
                has_data = True
                for row in rows:
                    seg = priority_to_segment.get(row.priority_code, "standard")
                    result[seg][p.sku] = result[seg].get(p.sku, 0) + float(row.total_qty or 0)
            else:
                # Proportional fallback
                total_demand = p.avg_daily_demand * 7
                result["strategic"][p.sku] = total_demand * 0.30
                result["standard"][p.sku] = total_demand * 0.50
                result["transactional"][p.sku] = total_demand * 0.20

        if not has_data:
            logger.info("No order data found for segment split; using proportional fallback")

        return result
