"""
Cascade Orchestrator

Orchestrates the full planning cascade from S&OP through Allocation Commit.
Manages the feed-forward contracts and feed-back signals.

Cascade Flow:
1. S&OP Layer → Policy Envelope (θ_SOP)
2. MRS Layer → Supply Baseline Pack (SupBP)
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
from .mrs_service import MRSService, ProductInventoryState, SupplierInfo
from .supply_agent import SupplyAgent
from .allocation_agent import AllocationAgent

logger = logging.getLogger(__name__)


class CascadeMode(Enum):
    """Operating mode for the cascade"""
    FULL = "full"      # All layers (S&OP simulation + MRS candidates + Agents)
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
    - MRS generates multiple candidate plans
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
        self.mrs_service = MRSService(db, mode="FULL" if mode == CascadeMode.FULL else "INPUT")
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
        # Step 2: MRS Layer - Generate Supply Baseline Pack
        # =================================================================
        if inventory_state is None:
            inventory_state = self._get_default_inventory_state(config_id)

        if supplier_info is None:
            supplier_info = self._get_default_supplier_info(config_id)

        if demand_forecast is None:
            demand_forecast = self._get_default_demand_forecast(inventory_state)

        supply_baseline_pack = self.mrs_service.generate_supply_baseline_pack(
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
            demand_by_segment = self._get_default_demand_by_segment(inventory_state)

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

    def _get_default_inventory_state(
        self,
        config_id: int
    ) -> List[ProductInventoryState]:
        """Get default inventory state for a config"""
        # In production, would query from database
        # For now, return sample data
        return [
            ProductInventoryState(
                sku=f"SKU-{i:03d}",
                category="default",
                on_hand=500,
                in_transit=100,
                committed=50,
                avg_daily_demand=30,
                demand_std=10,
                unit_cost=10.0,
                min_order_qty=50,
            )
            for i in range(1, 11)
        ]

    def _get_default_supplier_info(
        self,
        config_id: int
    ) -> Dict[str, List[SupplierInfo]]:
        """Get default supplier info"""
        return {
            f"SKU-{i:03d}": [
                SupplierInfo(
                    supplier_id="SUPPLIER-001",
                    lead_time_days=5,
                    lead_time_variability=0.2,
                    reliability=0.95,
                    min_order_value=1000,
                    unit_cost=10.0,
                )
            ]
            for i in range(1, 11)
        }

    def _get_default_demand_forecast(
        self,
        inventory_state: List[ProductInventoryState]
    ) -> Dict[str, List[float]]:
        """Generate default demand forecast"""
        return {
            p.sku: [p.avg_daily_demand for _ in range(28)]
            for p in inventory_state
        }

    def _get_default_demand_by_segment(
        self,
        inventory_state: List[ProductInventoryState]
    ) -> Dict[str, Dict[str, float]]:
        """Generate default demand by segment"""
        segments = ["strategic", "standard", "transactional"]
        segment_shares = [0.30, 0.50, 0.20]

        result = {seg: {} for seg in segments}

        for p in inventory_state:
            total_demand = p.avg_daily_demand * 7  # Weekly demand
            for seg, share in zip(segments, segment_shares):
                result[seg][p.sku] = total_demand * share

        return result
