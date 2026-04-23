"""
ATP Service

Phase 3: Full ATP/CTP Integration
Provides real-time Available to Promise (ATP) calculation for inventory nodes
with multi-period projection and allocation conflict resolution.

ATP = On-Hand Inventory + Scheduled Receipts - Allocated Orders - Safety Stock Reserve

Use Cases:
- Fulfillment decision support (check ATP before shipment)
- Multi-period projection (4-8 week rolling horizon)
- Allocation conflict resolution (competing customer demands)
"""

import logging
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.scenario_user import ScenarioUser
from app.models.scenario import Scenario
from app.models.supply_chain import ScenarioPeriod, ScenarioUserPeriod

# Aliases for backwards compatibility
ScenarioUser = ScenarioUser
Game = Scenario
ScenarioUserPeriod = ScenarioUserPeriod
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.supply_chain_config import TransportationLane

logger = logging.getLogger(__name__)


@dataclass
class ATPResult:
    """Single-period ATP calculation result"""
    on_hand: int
    scheduled_receipts: int
    allocated_orders: int
    safety_stock: int
    atp: int
    timestamp: str


@dataclass
class ATPAlert:
    """Alert for ATP risk conditions"""
    level: str  # "warning", "critical"
    message: str
    threshold: int
    actual: int
    recommendation: str


@dataclass
class ProbabilisticATPResult:
    """
    Phase 5: Probabilistic ATP result with P10/P50/P90 percentiles

    When lead times are stochastic, scheduled receipts may arrive earlier or later
    than expected. This affects ATP calculations:
    - P10 (pessimistic): 10th percentile - receipts arrive late
    - P50 (expected): Median - most likely scenario
    - P90 (optimistic): 90th percentile - receipts arrive early
    """
    # Base values
    on_hand: int
    safety_stock: int

    # Expected (P50) values
    scheduled_receipts_p50: int
    allocated_orders: int
    atp_p50: int

    # Pessimistic (P10) values
    scheduled_receipts_p10: int
    atp_p10: int

    # Optimistic (P90) values
    scheduled_receipts_p90: int
    atp_p90: int

    # Lead time statistics
    lead_time_mean: float
    lead_time_stddev: float

    # Metadata
    simulation_runs: int
    timestamp: str

    # Alerts (auto-generated)
    alerts: List[ATPAlert] = field(default_factory=list)

    def __post_init__(self):
        """Generate alerts based on ATP risk conditions"""
        # Note: alerts is already initialized as empty list via field(default_factory=list)

        # Check for critical stockout risk (P10 <= 0)
        if self.atp_p10 <= 0:
            self.alerts.append(ATPAlert(
                level="critical",
                message="Critical stockout risk: 10% probability ATP could be zero or negative",
                threshold=0,
                actual=self.atp_p10,
                recommendation="Expedite replenishment orders immediately. Consider safety stock increase."
            ))
        # Check for warning (P10 < safety stock)
        elif self.atp_p10 < self.safety_stock:
            self.alerts.append(ATPAlert(
                level="warning",
                message=f"ATP at risk: P10 ({self.atp_p10}) below safety stock ({self.safety_stock})",
                threshold=self.safety_stock,
                actual=self.atp_p10,
                recommendation="Monitor closely. Consider expediting or increasing order quantities."
            ))

        # Check for high variance (potential supply chain instability)
        if self.lead_time_stddev > 0.5 * self.lead_time_mean:
            self.alerts.append(ATPAlert(
                level="warning",
                message=f"High lead time variance: stddev={self.lead_time_stddev:.2f} vs mean={self.lead_time_mean:.2f}",
                threshold=int(0.5 * self.lead_time_mean),
                actual=int(self.lead_time_stddev),
                recommendation="Consider supplier diversification or safety stock adjustment."
            ))


@dataclass
class ATPPeriod:
    """Multi-period ATP projection for a single period"""
    period: int  # Week/round number
    starting_inventory: int
    scheduled_receipts: int
    forecasted_demand: int
    planned_allocations: int
    ending_inventory: int
    ending_atp: int
    cumulative_atp: int


@dataclass
class CustomerDemand:
    """Customer demand for allocation"""
    customer_id: int
    customer_name: str
    demand: int
    priority: int  # 1=high, 2=medium, 3=low


@dataclass
class CustomerAllocation:
    """Allocation result for single customer"""
    customer_id: int
    customer_name: str
    demand: int
    allocated: int
    unmet: int
    fill_rate: float


@dataclass
class AllocationResult:
    """Complete allocation result for all customers"""
    total_demand: int
    available_atp: int
    allocations: List[CustomerAllocation]
    allocation_method: str  # "priority", "proportional", "fcfs"
    timestamp: str


class ATPService:
    """
    Service for Available to Promise (ATP) calculations.

    Methods:
    - calculate_current_atp(): Single-period ATP
    - project_atp_multi_period(): Rolling horizon ATP forecast
    - allocate_to_customers(): Resolve allocation conflicts
    """

    def __init__(self, db: Session):
        self.db = db

    def calculate_current_atp(
        self,
        scenario_user: ScenarioUser,
        game: Game,
        current_period: ScenarioPeriod,
        include_safety_stock: bool = True,
        use_sap_bridge: bool = False,
        sap_bridge: Optional[Any] = None,
    ) -> ATPResult:
        """
        Calculate single-period ATP for scenario_user node.

        ATP = On-Hand + Scheduled Receipts - Allocated - Safety Stock

        Args:
            scenario_user: ScenarioUser instance (inventory node)
            game: Game instance
            current_period: Current game round
            include_safety_stock: Whether to reserve safety stock (default True)
            use_sap_bridge: Whether to use SAP ATP Bridge for real-time data (default False)
            sap_bridge: Optional SAPATPBridge instance for SAP integration

        Returns:
            ATPResult with breakdown of ATP components
        """
        # SAP Bridge integration: If enabled, query SAP for real-time ATP
        if use_sap_bridge and sap_bridge:
            try:
                # Get SAP plant and material mapping from scenario_user/node
                sap_plant = self._get_sap_plant(scenario_user, game)
                sap_material = self._get_sap_material(scenario_user, game)

                if sap_plant and sap_material:
                    from app.core.clock import tenant_today_sync
                    sap_result = sap_bridge.check_atp_realtime(
                        plant=sap_plant,
                        material=sap_material,
                        check_date=tenant_today_sync(getattr(game, "tenant_id", None), self.db)
                    )
                    logger.info(f"SAP ATP result for {sap_material}@{sap_plant}: ATP={sap_result.atp.atp}")
                    return sap_result.atp
            except Exception as e:
                logger.warning(f"SAP ATP check failed, falling back to local: {e}")
                # Fall through to local calculation

        # On-hand inventory
        on_hand = scenario_user.inventory.current_stock if scenario_user.inventory else 0 or 0

        # Handle case where game hasn't started (no current round)
        round_number = current_period.round_number if current_period else 0

        # Scheduled receipts = in-transit shipments arriving this round
        scheduled_receipts = self._get_scheduled_receipts(
            scenario_user, round_number, game
        )

        # Allocated orders = downstream commitments already promised
        allocated_orders = self._get_allocated_orders(
            scenario_user, round_number, game
        )

        # Safety stock from inventory policy
        safety_stock = self._get_safety_stock(scenario_user, game) if include_safety_stock else 0

        # Calculate ATP (cannot be negative)
        atp = max(0, on_hand + scheduled_receipts - allocated_orders - safety_stock)

        logger.debug(
            f"ATP calculation for scenario_user {scenario_user.id} (round {round_number}): "
            f"on_hand={on_hand}, receipts={scheduled_receipts}, allocated={allocated_orders}, "
            f"safety_stock={safety_stock}, ATP={atp}"
        )

        return ATPResult(
            on_hand=on_hand,
            scheduled_receipts=scheduled_receipts,
            allocated_orders=allocated_orders,
            safety_stock=safety_stock,
            atp=atp,
            timestamp=datetime.utcnow().isoformat(),
        )

    def calculate_probabilistic_atp(
        self,
        scenario_user: ScenarioUser,
        game: Game,
        current_period: ScenarioPeriod,
        n_simulations: int = 100,
        include_safety_stock: bool = True,
    ) -> ProbabilisticATPResult:
        """
        Phase 5: Calculate probabilistic ATP with P10/P50/P90 percentiles.

        Uses Monte Carlo simulation with stochastic lead times to determine
        the probability distribution of ATP values.

        When lead times are stochastic:
        - Some shipments may arrive earlier → higher ATP (optimistic)
        - Some shipments may arrive later → lower ATP (pessimistic)

        Args:
            scenario_user: ScenarioUser instance (inventory node)
            game: Game instance
            current_period: Current game round
            n_simulations: Number of Monte Carlo runs (default 100)
            include_safety_stock: Whether to reserve safety stock (default True)

        Returns:
            ProbabilisticATPResult with P10/P50/P90 ATP values
        """
        import numpy as np
        from app.services.sc_planning.stochastic_sampler import StochasticSampler

        # On-hand inventory (deterministic)
        on_hand = scenario_user.inventory.current_stock if scenario_user.inventory else 0 or 0

        # Handle case where game hasn't started
        round_number = current_period.round_number if current_period else 0

        # Allocated orders (deterministic - already committed)
        allocated_orders = self._get_allocated_orders(scenario_user, round_number, game)

        # Safety stock (deterministic policy)
        safety_stock = self._get_safety_stock(scenario_user, game) if include_safety_stock else 0

        # Initialize stochastic sampler with game seed
        sampler = StochasticSampler(scenario_id=game.id)

        # Get lanes feeding into this scenario_user's node for lead time distributions
        lanes = self._get_upstream_lanes(scenario_user, game)

        # Run Monte Carlo simulation
        receipt_samples = []
        lead_time_samples = []

        for _ in range(n_simulations):
            # Sample lead times for each upstream lane
            total_receipts = 0
            for lane in lanes:
                # Sample the supply lead time
                base_lt = self._get_lane_default_lead_time(lane)
                sampled_lt = sampler.sample_lane_supply_lead_time(lane, base_lt)
                lead_time_samples.append(sampled_lt)

                # Calculate arrival round with sampled lead time
                # If lead time is shorter, receipts may arrive this round
                # If lead time is longer, they may not arrive yet
                # This is a simplified model - in reality you'd track individual shipments
                if sampled_lt <= 1:  # Arriving this round
                    receipts = self._get_scheduled_receipts(scenario_user, round_number, game)
                    total_receipts += receipts
                else:
                    # Partial receipt based on lead time distribution
                    base_receipts = self._get_scheduled_receipts(scenario_user, round_number, game)
                    # Scale receipts by probability of arrival
                    arrival_prob = max(0.0, 1.0 - (sampled_lt - 1) * 0.2)
                    total_receipts += int(base_receipts * arrival_prob)

            receipt_samples.append(total_receipts)

        # Calculate percentiles
        receipt_array = np.array(receipt_samples)
        receipts_p10 = int(np.percentile(receipt_array, 10))
        receipts_p50 = int(np.percentile(receipt_array, 50))
        receipts_p90 = int(np.percentile(receipt_array, 90))

        # Calculate ATP for each percentile
        atp_p10 = max(0, on_hand + receipts_p10 - allocated_orders - safety_stock)
        atp_p50 = max(0, on_hand + receipts_p50 - allocated_orders - safety_stock)
        atp_p90 = max(0, on_hand + receipts_p90 - allocated_orders - safety_stock)

        # Lead time statistics
        lt_array = np.array(lead_time_samples) if lead_time_samples else np.array([1.0])
        lt_mean = float(np.mean(lt_array))
        lt_stddev = float(np.std(lt_array))

        logger.info(
            f"Probabilistic ATP for scenario_user {scenario_user.id}: "
            f"P10={atp_p10}, P50={atp_p50}, P90={atp_p90} "
            f"(LT mean={lt_mean:.2f}, std={lt_stddev:.2f})"
        )

        return ProbabilisticATPResult(
            on_hand=on_hand,
            safety_stock=safety_stock,
            scheduled_receipts_p50=receipts_p50,
            allocated_orders=allocated_orders,
            atp_p50=atp_p50,
            scheduled_receipts_p10=receipts_p10,
            atp_p10=atp_p10,
            scheduled_receipts_p90=receipts_p90,
            atp_p90=atp_p90,
            lead_time_mean=lt_mean,
            lead_time_stddev=lt_stddev,
            simulation_runs=n_simulations,
            timestamp=datetime.utcnow().isoformat(),
        )

    def _get_upstream_lanes(self, scenario_user: ScenarioUser, game: Game) -> List[TransportationLane]:
        """Get transportation lanes feeding into this scenario_user's site"""
        try:
            from app.models.supply_chain_config import Site

            # Get scenario_user's site
            if not scenario_user.site_key or not game.supply_chain_config_id:
                return []

            node = self.db.query(Site).filter(
                Site.config_id == game.supply_chain_config_id,
                Site.dag_type == scenario_user.site_key
            ).first()

            if not node:
                return []

            # Get upstream transportation lanes (where this site is the destination)
            lanes = self.db.query(TransportationLane).filter(
                TransportationLane.to_site_id == node.id,
                TransportationLane.config_id == game.supply_chain_config_id
            ).all()

            return lanes
        except Exception as e:
            logger.warning(f"Error getting upstream transportation lanes: {e}")
            return []

    def _get_lane_default_lead_time(self, lane: TransportationLane) -> float:
        """Get default lead time from lane configuration"""
        try:
            # Try supply_lead_time JSON field first
            supply_lt = getattr(lane, 'supply_lead_time', None)
            if supply_lt and isinstance(supply_lt, dict):
                return float(supply_lt.get('min', 1))

            # Fall back to lead_time_days
            lt_days = getattr(lane, 'lead_time_days', None)
            if lt_days and isinstance(lt_days, dict):
                return float(lt_days.get('min', 1))

            return 1.0
        except Exception:
            return 1.0

    def project_atp_multi_period(
        self,
        scenario_user: ScenarioUser,
        game: Game,
        current_period: ScenarioPeriod,
        periods: int = 8,
    ) -> List[ATPPeriod]:
        """
        Project ATP over rolling horizon (4-8 weeks).

        Uses:
        - Demand forecast (from agent or historical avg)
        - Scheduled receipts (pipeline shipments)
        - Planned allocations (future commitments)

        Args:
            scenario_user: ScenarioUser instance
            game: Game instance
            current_period: Current game round
            periods: Number of future periods to project (default 8)

        Returns:
            List of ATPPeriod objects with week-by-week breakdown
        """
        projections = []

        # Initialize with current inventory
        current_inventory = scenario_user.inventory.current_stock if scenario_user.inventory else 0 or 0
        cumulative_atp = 0

        # Get safety stock once (constant across periods)
        safety_stock = self._get_safety_stock(scenario_user)

        for period_offset in range(1, periods + 1):
            future_round = current_period.round_number + period_offset

            # Get scheduled receipts for this period
            receipts = self._get_scheduled_receipts(scenario_user, future_round)

            # Forecast demand for this period
            forecasted_demand = self._forecast_demand_for_period(
                scenario_user, game, current_period, period_offset
            )

            # Get planned allocations (future confirmed orders)
            planned_allocations = self._get_allocated_orders(scenario_user, future_round)

            # Calculate ending inventory (starting + receipts - demand)
            ending_inventory = current_inventory + receipts - forecasted_demand

            # ATP = ending inventory - allocations - safety stock (cannot be negative)
            ending_atp = max(
                0, ending_inventory - planned_allocations - safety_stock
            )
            cumulative_atp += ending_atp

            projections.append(
                ATPPeriod(
                    period=future_round,
                    starting_inventory=current_inventory,
                    scheduled_receipts=receipts,
                    forecasted_demand=forecasted_demand,
                    planned_allocations=planned_allocations,
                    ending_inventory=ending_inventory,
                    ending_atp=ending_atp,
                    cumulative_atp=cumulative_atp,
                )
            )

            # Update for next iteration
            current_inventory = ending_inventory

        logger.info(
            f"ATP projection for scenario_user {scenario_user.id}: {periods} periods generated, "
            f"cumulative ATP = {cumulative_atp}"
        )

        return projections

    def allocate_to_customers(
        self,
        scenario_user: ScenarioUser,
        demands: List[CustomerDemand],
        available_atp: int,
        allocation_method: str = "proportional",
    ) -> AllocationResult:
        """
        Allocate available ATP to competing customer demands.

        Allocation Strategies:
        1. Priority-based: High-priority customers first (FCFS within priority)
        2. Proportional: Split ATP proportionally to demand ratios
        3. FCFS: First-come-first-served (order of demands list)

        Args:
            scenario_user: ScenarioUser instance (supplier node)
            demands: List of CustomerDemand objects
            available_atp: Total ATP to allocate
            allocation_method: "priority", "proportional", or "fcfs"

        Returns:
            AllocationResult with customer_id → allocated_qty mapping
        """
        total_demand = sum(d.demand for d in demands)

        if total_demand <= available_atp:
            # Sufficient ATP to fulfill all demands
            allocations = [
                CustomerAllocation(
                    customer_id=d.customer_id,
                    customer_name=d.customer_name,
                    demand=d.demand,
                    allocated=d.demand,
                    unmet=0,
                    fill_rate=1.0,
                )
                for d in demands
            ]
        else:
            # Conflict: total demand exceeds ATP, need allocation logic
            if allocation_method == "priority":
                allocations = self._allocate_by_priority(demands, available_atp)
            elif allocation_method == "fcfs":
                allocations = self._allocate_fcfs(demands, available_atp)
            else:  # proportional (default)
                allocations = self._allocate_proportionally(demands, available_atp)

        logger.info(
            f"Allocated {available_atp} ATP to {len(demands)} customers using "
            f"{allocation_method} method. Total demand: {total_demand}, "
            f"Total allocated: {sum(a.allocated for a in allocations)}"
        )

        return AllocationResult(
            total_demand=total_demand,
            available_atp=available_atp,
            allocations=allocations,
            allocation_method=allocation_method,
            timestamp=datetime.utcnow().isoformat(),
        )

    # --- Helper Methods ---

    def _get_scenario_user_node_id(self, scenario_user: ScenarioUser, game: Game) -> Optional[int]:
        """Look up the Node ID for a scenario_user based on their site_key."""
        from app.models.supply_chain_config import Site
        if not scenario_user.site_key or not game.supply_chain_config_id:
            return None
        node = self.db.query(Site).filter(
            Site.config_id == game.supply_chain_config_id,
            Site.dag_type == scenario_user.site_key
        ).first()
        return node.id if node else None

    def _get_scheduled_receipts(self, scenario_user: ScenarioUser, round_number: int, game: Game = None, product_id: str = None) -> int:
        """
        Get total scheduled receipts arriving in specified round.

        For multi-product support, queries TransferOrderLineItem table to sum
        quantities from TOs with multiple items.

        Args:
            scenario_user: ScenarioUser instance
            round_number: Round number to check
            game: Game instance (optional, used for node lookup)
            product_id: Optional product ID to filter by (for multi-product ATP)

        Returns:
            Total quantity scheduled to arrive in this round
        """
        try:
            # Get node ID for this scenario_user
            node_id = self._get_scenario_user_node_id(scenario_user, game) if game else None
            if not node_id:
                return 0  # No node configured, return 0 receipts

            from sqlalchemy import func

            # Query TransferOrderLineItem joined with TransferOrder
            # Sum quantities from line items where TO is in transit and arriving this round
            query = (
                self.db.query(func.coalesce(func.sum(TransferOrderLineItem.quantity), 0))
                .join(TransferOrder, TransferOrderLineItem.to_id == TransferOrder.id)
                .filter(
                    TransferOrder.destination_site_id == node_id,
                    TransferOrder.arrival_round == round_number,
                    TransferOrder.status == "IN_TRANSIT",
                )
            )

            # Optional product filter for multi-product ATP
            if product_id:
                query = query.filter(TransferOrderLineItem.product_id == product_id)

            total = query.scalar() or 0
            return int(total)
        except Exception as e:
            logger.warning(f"Error getting scheduled receipts: {e}")
            return 0  # Return 0 on error (e.g., schema mismatch)

    def _get_allocated_orders(self, scenario_user: ScenarioUser, round_number: int, game: Game = None, product_id: str = None) -> int:
        """
        Get total allocated orders (downstream commitments) for specified round.

        For multi-product support, queries TransferOrderLineItem table to sum
        quantities from TOs with multiple items.

        Args:
            scenario_user: ScenarioUser instance
            round_number: Round number to check
            game: Game instance (optional, used for node lookup)
            product_id: Optional product ID to filter by (for multi-product ATP)

        Returns:
            Total quantity allocated/committed from this node
        """
        try:
            # Get node ID for this scenario_user
            node_id = self._get_scenario_user_node_id(scenario_user, game) if game else None
            if not node_id:
                return 0  # No node configured, return 0 allocated

            from sqlalchemy import func

            # Query TransferOrderLineItem joined with TransferOrder
            # Sum quantities from line items where TO is confirmed/in-transit
            query = (
                self.db.query(func.coalesce(func.sum(TransferOrderLineItem.quantity), 0))
                .join(TransferOrder, TransferOrderLineItem.to_id == TransferOrder.id)
                .filter(
                    TransferOrder.source_site_id == node_id,
                    TransferOrder.order_round <= round_number,
                    TransferOrder.status.in_(["CONFIRMED", "IN_TRANSIT", "SHIPPED"]),
                )
            )

            # Optional product filter for multi-product ATP
            if product_id:
                query = query.filter(TransferOrderLineItem.product_id == product_id)

            total = query.scalar() or 0
            return int(total)
        except Exception as e:
            logger.warning(f"Error getting allocated orders: {e}")
            return 0  # Return 0 on error (e.g., schema mismatch)

    def _get_safety_stock(self, scenario_user: ScenarioUser, game: Game = None) -> int:
        """
        Get safety stock reserve for scenario_user node.

        Logic:
        1. Try to find InvPolicy for the node (site_id match)
        2. If policy type is 'abs_level', use ss_quantity
        3. If policy type is 'doc_dem' or 'doc_fcst', calculate from historical demand
        4. If no policy found, use default 10% of current stock or 100 units minimum

        Args:
            scenario_user: ScenarioUser instance

        Returns:
            Safety stock quantity (integer)
        """
        try:
            # Try to get inventory policy for this node
            from app.models.sc_entities import InvPolicy

            # Query by site_id (node_id maps to site in AWS SC model)
            node_id = self._get_scenario_user_node_id(scenario_user, game) if game else None
            policy = None
            if node_id:
                policy = (
                    self.db.query(InvPolicy)
                    .filter(
                        InvPolicy.site_id == str(node_id),
                        InvPolicy.is_active == "Y",
                    )
                    .first()
                )

            if policy:
                if policy.ss_policy == "abs_level" and policy.ss_quantity:
                    # Absolute level - fixed quantity
                    ss = int(policy.ss_quantity)
                    logger.debug(f"Safety stock for scenario_user {scenario_user.id}: {ss} (abs_level policy)")
                    return ss

                elif policy.ss_policy in ("doc_dem", "doc_fcst") and policy.ss_days:
                    # Days of coverage - calculate from average demand
                    historical = self._get_historical_demand(scenario_user, periods=4)
                    if historical:
                        avg_daily_demand = sum(historical) / len(historical)
                        ss = int(avg_daily_demand * policy.ss_days)
                        logger.debug(
                            f"Safety stock for scenario_user {scenario_user.id}: {ss} "
                            f"({policy.ss_days} days coverage)"
                        )
                        return ss

                elif policy.ss_policy == "sl" and policy.service_level:
                    # Service level based - use z-score calculation
                    # For simplicity, use linear approximation: 95% SL ≈ 1.65 std devs
                    historical = self._get_historical_demand(scenario_user, periods=8)
                    if historical and len(historical) >= 2:
                        import statistics
                        std_dev = statistics.stdev(historical)
                        z_score = {
                            0.90: 1.28, 0.95: 1.65, 0.98: 2.05, 0.99: 2.33
                        }.get(round(policy.service_level, 2), 1.65)
                        ss = int(z_score * std_dev)
                        logger.debug(
                            f"Safety stock for scenario_user {scenario_user.id}: {ss} "
                            f"(service level {policy.service_level})"
                        )
                        return ss

        except Exception as e:
            logger.warning(f"Error getting safety stock policy: {e}")

        # Fallback: 10% of current stock or 100 units minimum
        default_ss = max(100, int((scenario_user.inventory.current_stock if scenario_user.inventory else 0 or 0) * 0.1))
        logger.debug(f"Safety stock for scenario_user {scenario_user.id}: {default_ss} (default)")
        return default_ss

    def _forecast_demand_for_period(
        self,
        scenario_user: ScenarioUser,
        game: Game,
        current_period: ScenarioPeriod,
        period_offset: int,
    ) -> int:
        """
        Forecast demand for future period.

        Logic:
        1. If agent has forecasting capability, use agent forecast
        2. Otherwise, use historical average demand
        3. If insufficient history, use baseline demand from config

        Args:
            scenario_user: ScenarioUser instance
            game: Game instance
            current_period: Current game round
            period_offset: How many periods ahead to forecast

        Returns:
            Forecasted demand (integer)
        """
        # Get historical demand (last 4 rounds)
        historical_demand = self._get_historical_demand(scenario_user, periods=4)

        if historical_demand:
            # Use simple moving average
            avg_demand = sum(historical_demand) / len(historical_demand)
            return int(avg_demand)

        # Fallback: try to get baseline demand from MarketDemand config
        try:
            from app.models.supply_chain_config import MarketDemand
            config_id = getattr(game, "config_id", None)
            if config_id:
                md = (
                    self.db.query(MarketDemand)
                    .filter(MarketDemand.config_id == config_id)
                    .first()
                )
                if md and md.demand_pattern:
                    params = md.demand_pattern.get("parameters") or md.demand_pattern.get("params", {})
                    final = params.get("final_demand")
                    initial = params.get("initial_demand")
                    if final is not None:
                        return int(final)
                    if initial is not None:
                        return int(initial)
        except Exception as e:
            logger.debug(f"Could not load MarketDemand baseline: {e}")

        # Last resort: 0 (no data available)
        return 0

    def _get_historical_demand(self, scenario_user: ScenarioUser, periods: int = 4) -> List[int]:
        """
        Get historical demand for scenario_user (last N periods).

        Queries scenario_user_periods table for order_received values (incoming demand
        from downstream nodes) for the most recent N completed rounds.

        Args:
            scenario_user: ScenarioUser instance
            periods: Number of historical periods to retrieve

        Returns:
            List of demand values (order_received) from recent rounds
        """
        try:
            # Query ScenarioUserPeriod joined with ScenarioPeriod to get historical demand
            # order_received = incoming orders from downstream (demand)
            historical_rounds = (
                self.db.query(ScenarioUserPeriod)
                .join(ScenarioPeriod, ScenarioUserPeriod.scenario_period_id == ScenarioPeriod.id)
                .filter(
                    ScenarioUserPeriod.scenario_user_id == scenario_user.id,
                    ScenarioPeriod.is_completed == True,  # Only completed rounds
                )
                .order_by(ScenarioPeriod.round_number.desc())
                .limit(periods)
                .all()
            )

            if not historical_rounds:
                logger.debug(f"No historical demand data for scenario_user {scenario_user.id}")
                return []

            # Extract order_received values (demand from downstream)
            demands = [pr.order_received or 0 for pr in historical_rounds]

            # Reverse to get chronological order (oldest first)
            demands.reverse()

            logger.debug(
                f"Historical demand for scenario_user {scenario_user.id}: {demands} "
                f"(last {len(demands)} periods)"
            )

            return demands

        except Exception as e:
            logger.warning(
                f"Error getting historical demand for scenario_user {scenario_user.id}: {e}",
                exc_info=True
            )
            return []

    def _allocate_by_priority(
        self, demands: List[CustomerDemand], available_atp: int
    ) -> List[CustomerAllocation]:
        """
        Allocate ATP by customer priority (high priority first, FCFS within priority).

        Algorithm:
        1. Sort customers by priority (1=high, 2=medium, 3=low)
        2. Allocate full demand to high-priority customers first
        3. Allocate remaining ATP to medium-priority customers
        4. Allocate remaining ATP to low-priority customers
        5. Within same priority, FCFS
        """
        # Sort by priority (ascending) then by order in list (FCFS)
        sorted_demands = sorted(demands, key=lambda d: (d.priority, demands.index(d)))

        allocations = []
        remaining_atp = available_atp

        for demand in sorted_demands:
            if remaining_atp >= demand.demand:
                # Fulfill completely
                allocated = demand.demand
            else:
                # Partial fulfillment
                allocated = remaining_atp

            unmet = demand.demand - allocated
            fill_rate = allocated / demand.demand if demand.demand > 0 else 1.0

            allocations.append(
                CustomerAllocation(
                    customer_id=demand.customer_id,
                    customer_name=demand.customer_name,
                    demand=demand.demand,
                    allocated=allocated,
                    unmet=unmet,
                    fill_rate=fill_rate,
                )
            )

            remaining_atp -= allocated
            if remaining_atp <= 0:
                break

        # Add zero allocations for remaining customers (if any)
        allocated_ids = {a.customer_id for a in allocations}
        for demand in sorted_demands:
            if demand.customer_id not in allocated_ids:
                allocations.append(
                    CustomerAllocation(
                        customer_id=demand.customer_id,
                        customer_name=demand.customer_name,
                        demand=demand.demand,
                        allocated=0,
                        unmet=demand.demand,
                        fill_rate=0.0,
                    )
                )

        return allocations

    def _allocate_proportionally(
        self, demands: List[CustomerDemand], available_atp: int
    ) -> List[CustomerAllocation]:
        """
        Allocate ATP proportionally to demand ratios.

        Algorithm:
        Customer A demand: 300, Customer B demand: 300 (total 600)
        ATP available: 400
        Ratio: 1:1
        Allocation: A=200 (50% of 400), B=200 (50% of 400)
        """
        total_demand = sum(d.demand for d in demands)
        allocations = []

        for demand in demands:
            ratio = demand.demand / total_demand if total_demand > 0 else 0
            allocated = int(available_atp * ratio)
            unmet = demand.demand - allocated
            fill_rate = allocated / demand.demand if demand.demand > 0 else 1.0

            allocations.append(
                CustomerAllocation(
                    customer_id=demand.customer_id,
                    customer_name=demand.customer_name,
                    demand=demand.demand,
                    allocated=allocated,
                    unmet=unmet,
                    fill_rate=fill_rate,
                )
            )

        return allocations

    def _allocate_fcfs(
        self, demands: List[CustomerDemand], available_atp: int
    ) -> List[CustomerAllocation]:
        """
        Allocate ATP first-come-first-served (order of demands list).

        Algorithm:
        Process demands in list order, fulfill completely until ATP exhausted.
        """
        allocations = []
        remaining_atp = available_atp

        for demand in demands:
            if remaining_atp >= demand.demand:
                # Fulfill completely
                allocated = demand.demand
            else:
                # Partial or zero fulfillment
                allocated = remaining_atp

            unmet = demand.demand - allocated
            fill_rate = allocated / demand.demand if demand.demand > 0 else 1.0

            allocations.append(
                CustomerAllocation(
                    customer_id=demand.customer_id,
                    customer_name=demand.customer_name,
                    demand=demand.demand,
                    allocated=allocated,
                    unmet=unmet,
                    fill_rate=fill_rate,
                )
            )

            remaining_atp -= allocated
            if remaining_atp <= 0:
                remaining_atp = 0  # Prevent negative

        return allocations

    def save_probabilistic_atp(
        self,
        game: Game,
        scenario_user: ScenarioUser,
        result: ProbabilisticATPResult,
        current_period: int,
    ) -> int:
        """
        Save probabilistic ATP result to database for historical tracking.

        Args:
            game: Game instance
            scenario_user: ScenarioUser instance
            result: ProbabilisticATPResult from calculate_probabilistic_atp
            current_period: Current round number

        Returns:
            ID of the saved record
        """
        try:
            from app.core.clock import tenant_today_sync
            from app.models.inventory_projection import AtpProjection

            # Get node ID for scenario_user
            node_id = self._get_scenario_user_node_id(scenario_user, game)
            if not node_id:
                logger.warning(f"Cannot save ATP - no node ID for scenario_user {scenario_user.id}")
                return None

            # Get product ID (default to "CASE" for simulation)
            product_id = "CASE"

            # Create ATP projection record
            atp_record = AtpProjection(
                company_id=game.tenant_id or 1,
                product_id=product_id,
                site_id=node_id,
                atp_date=tenant_today_sync(getattr(game, "tenant_id", None), self.db),
                atp_qty=float(result.atp_p50),
                cumulative_atp_qty=float(result.atp_p50),
                opening_balance=float(result.on_hand),
                supply_qty=float(result.scheduled_receipts_p50),
                demand_qty=0.0,
                allocated_qty=float(result.allocated_orders),
                # Probabilistic fields
                atp_p10=result.atp_p10,
                atp_p90=result.atp_p90,
                lead_time_mean=result.lead_time_mean,
                lead_time_stddev=result.lead_time_stddev,
                # Game integration
                scenario_id=game.id,
                source="probabilistic_atp",
                source_event_id=f"game_{game.id}_round_{current_period}",
            )

            self.db.add(atp_record)
            self.db.commit()
            self.db.refresh(atp_record)

            logger.info(
                f"Saved probabilistic ATP record {atp_record.id} for scenario_user {scenario_user.id}: "
                f"P10={result.atp_p10}, P50={result.atp_p50}, P90={result.atp_p90}"
            )

            return atp_record.id

        except Exception as e:
            logger.error(f"Failed to save probabilistic ATP: {e}", exc_info=True)
            self.db.rollback()
            return None

    # =========================================================================
    # SAP Integration Helper Methods
    # =========================================================================

    def _get_sap_plant(self, scenario_user: ScenarioUser, game: Game) -> Optional[str]:
        """
        Get SAP plant code for scenario_user node.

        Looks up the Node model for sap_plant_code field.
        Falls back to site_key if SAP mapping not configured.

        Args:
            scenario_user: ScenarioUser instance
            game: Game instance

        Returns:
            SAP plant code or None
        """
        try:
            from app.models.supply_chain_config import Site

            # Get node from scenario_user's site_key and game config
            if not game or not game.supply_chain_config_id:
                return None

            node = (
                self.db.query(Site)
                .filter(
                    Site.supply_chain_config_id == game.supply_chain_config_id,
                    Site.node_key == scenario_user.site_key
                )
                .first()
            )

            if node:
                # Try SAP plant code first, fall back to node_key
                return getattr(node, 'sap_plant_code', None) or node.node_key

            return scenario_user.site_key

        except Exception as e:
            logger.debug(f"Could not get SAP plant for scenario_user {scenario_user.id}: {e}")
            return None

    def _get_sap_material(self, scenario_user: ScenarioUser, game: Game) -> Optional[str]:
        """
        Get SAP material number for scenario_user's primary item.

        For simulation, this is typically "CASE" or the primary finished good.

        Args:
            scenario_user: ScenarioUser instance
            game: Game instance

        Returns:
            SAP material number or None
        """
        try:
            from app.models.supply_chain_config import Item

            # Get primary item from game config
            if not game or not game.supply_chain_config_id:
                return "CASE"  # Default simulation item

            # Get the first/primary item for this config
            item = (
                self.db.query(Item)
                .filter(Item.supply_chain_config_id == game.supply_chain_config_id)
                .first()
            )

            if item:
                # Try SAP material number, fall back to item_key
                return getattr(item, 'sap_material_number', None) or item.item_key

            return "CASE"  # Default

        except Exception as e:
            logger.debug(f"Could not get SAP material for game {game.id if game else 'N/A'}: {e}")
            return "CASE"


# Factory function for creating service instances
from fastapi import Depends
from app.db.session import get_db, get_sync_db

def get_atp_service(db: Session = Depends(get_sync_db)) -> ATPService:
    """Factory function to create ATPService"""
    return ATPService(db)
