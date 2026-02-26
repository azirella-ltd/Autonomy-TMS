"""
CTP Service

Phase 3: Full ATP/CTP Integration
Provides Capable to Promise (CTP) calculation for manufacturing nodes
with production capacity constraints, BOM explosion, and promise date calculation.

CTP = (Production Capacity - Commitments) × Yield Rate × Component Availability

Use Cases:
- Replenishment decision support for manufacturers
- Production capacity checks
- Component ATP validation (BOM explosion)
- Promise date calculation for customer orders
"""

import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.scenario_user import ScenarioUser
from app.models.scenario import Scenario
from app.models.supply_chain import ScenarioRound, ScenarioUserInventory
from app.models.sc_entities import ProductBom as ProductBOM, Product, SourcingRules, InvLevel
from app.models.supply_chain_config import Node

# Aliases for backwards compatibility
ScenarioUser = ScenarioUser
Game = Scenario
ScenarioRound = ScenarioRound
ScenarioUserInventory = ScenarioUserInventory
from .atp_service import ATPService, get_atp_service

logger = logging.getLogger(__name__)


def _get_player_node(db: Session, scenario_user: ScenarioUser, game: Game) -> Optional[Node]:
    """
    Look up the Node for a scenario_user based on their site_key.

    The scenario_user's site_key maps to a node in the game's supply chain config.
    """
    if not scenario_user.site_key or not game.supply_chain_config_id:
        return None

    node = db.query(Node).filter(
        Node.config_id == game.supply_chain_config_id,
        Node.dag_type == scenario_user.site_key
    ).first()

    return node


@dataclass
class ComponentConstraint:
    """Component availability constraint"""
    item_id: Union[int, str]  # SC-compliant string product_id (legacy: int)
    item_name: str
    required_per_unit: int
    available_atp: int
    max_producible: int  # Max units of parent item can produce
    shortfall: int  # Shortfall in component units (0 if sufficient)


@dataclass
class CTPResult:
    """Single-period CTP calculation result"""
    production_capacity: int
    current_commitments: int
    yield_rate: float
    available_capacity: int
    component_constraints: List[ComponentConstraint]
    ctp: int  # Final CTP after all constraints
    constrained_by: Optional[str]  # "capacity", "component_X", or None
    timestamp: str


@dataclass
class ProbabilisticCTPResult:
    """
    Phase 5: Probabilistic CTP result with P10/P50/P90 percentiles.

    When yields, capacities, and lead times are stochastic, CTP varies:
    - P10 (pessimistic): 10th percentile - lower yield, higher scrap
    - P50 (expected): Median - most likely scenario
    - P90 (optimistic): 90th percentile - higher yield, lower scrap
    """
    # Base values
    production_capacity: int
    current_commitments: int

    # Yield statistics
    yield_rate_mean: float
    yield_rate_stddev: float

    # CTP percentiles
    ctp_p10: int  # Pessimistic
    ctp_p50: int  # Expected (median)
    ctp_p90: int  # Optimistic

    # Available capacity percentiles
    available_capacity_p10: int
    available_capacity_p50: int
    available_capacity_p90: int

    # Constraint analysis
    constrained_by: Optional[str]
    component_constraints: List[ComponentConstraint]

    # Production lead time statistics
    production_lead_time_mean: float
    production_lead_time_stddev: float

    # Metadata
    simulation_runs: int
    timestamp: str


@dataclass
class CTPPeriod:
    """Multi-period CTP projection for a single period"""
    period: int  # Week/round number
    capacity: int
    commitments: int
    available_capacity: int
    component_atp: Dict[int, int]  # item_id → ATP
    ctp: int
    utilization_pct: float  # Capacity utilization percentage


@dataclass
class PromiseDateResult:
    """Promise date calculation result"""
    quantity: int
    earliest_date: int  # Round number when order can be fulfilled
    lead_time: int  # Production lead time + shipping lead time
    confidence: float  # 0.0-1.0 (based on capacity buffer)
    constraints: List[str]  # ["capacity", "component_X", "lead_time"]
    breakdown: List[str]  # Human-readable explanation


class CTPService:
    """
    Service for Capable to Promise (CTP) calculations for manufacturers.

    Methods:
    - calculate_current_ctp(): Single-period CTP with component checks
    - project_ctp_multi_period(): Rolling horizon CTP forecast
    - calculate_promise_date(): Earliest delivery date for quantity
    """

    def __init__(self, db: Session):
        self.db = db
        self.atp_service = get_atp_service(db)

    def calculate_current_ctp(
        self,
        scenario_user: ScenarioUser,
        game: Game,
        current_round: Optional[ScenarioRound],
        product_id: str,
    ) -> CTPResult:
        """
        Calculate CTP for manufacturer node.

        CTP = (Capacity - Commitments) × Yield × Component_Availability

        Steps:
        1. Get production capacity from node configuration
        2. Subtract current commitments (WIP + scheduled production)
        3. Apply yield rate (account for scrap)
        4. Check component ATP (BOM explosion)
        5. Return minimum of capacity and component constraints

        Args:
            scenario_user: ScenarioUser instance (manufacturer node)
            game: Game instance
            current_round: Current game round (can be None)
            product_id: AWS SC Product ID (string)

        Returns:
            CTPResult with capacity breakdown and component constraints
        """
        # Step 1: Get production capacity from node configuration
        node = _get_player_node(self.db, scenario_user, game)
        if not node:
            logger.warning(f"No node found for scenario_user {scenario_user.id} (site_key={scenario_user.site_key})")
            # Return zero CTP if no node configured
            return CTPResult(
                production_capacity=0,
                current_commitments=0,
                yield_rate=1.0,
                available_capacity=0,
                component_constraints=[],
                ctp=0,
                constrained_by="no_node_configured",
                timestamp=datetime.utcnow().isoformat(),
            )
        capacity = self._get_production_capacity(node)

        # Step 2: Get current production commitments
        commitments = self._get_production_commitments(scenario_user, current_round)

        # Available capacity after commitments
        available_capacity = max(0, capacity - commitments)

        # Step 3: Apply yield rate
        yield_rate = self._get_yield_rate(node)
        available_after_yield = int(available_capacity * yield_rate)

        # Step 4: BOM explosion - check component ATP
        component_constraints = self._check_component_atp(
            scenario_user, game, current_round, product_id, available_after_yield
        )

        # Step 5: Calculate final CTP (minimum of capacity and component constraints)
        ctp = available_after_yield
        constrained_by = None

        for constraint in component_constraints:
            if constraint.max_producible < ctp:
                ctp = constraint.max_producible
                constrained_by = f"component_{constraint.item_name}"

        if ctp < available_after_yield:
            # Constrained by component
            pass
        elif available_capacity < capacity:
            # Constrained by commitments
            constrained_by = "capacity"
        else:
            # No constraints
            constrained_by = None

        logger.info(
            f"CTP calculation for scenario_user {scenario_user.id} (product {product_id}): "
            f"capacity={capacity}, commitments={commitments}, yield={yield_rate:.2f}, "
            f"CTP={ctp}, constrained_by={constrained_by}"
        )

        return CTPResult(
            production_capacity=capacity,
            current_commitments=commitments,
            yield_rate=yield_rate,
            available_capacity=available_capacity,
            component_constraints=component_constraints,
            ctp=ctp,
            constrained_by=constrained_by,
            timestamp=datetime.utcnow().isoformat(),
        )

    def calculate_probabilistic_ctp(
        self,
        scenario_user: ScenarioUser,
        game: Game,
        current_round: Optional[ScenarioRound],
        product_id: str,
        n_simulations: int = 100,
    ) -> ProbabilisticCTPResult:
        """
        Phase 5: Calculate probabilistic CTP with P10/P50/P90 percentiles.

        Uses Monte Carlo simulation with stochastic yields and lead times
        to determine the probability distribution of CTP values.

        CTP = (Capacity - Commitments) × Yield × Component_Availability

        When yields are stochastic:
        - Higher yield → more CTP (optimistic)
        - Lower yield → less CTP (pessimistic)

        Args:
            scenario_user: ScenarioUser instance (manufacturer node)
            game: Game instance
            current_round: Current game round
            product_id: AWS SC Product ID (string, e.g., "FG-001")
            n_simulations: Number of Monte Carlo runs (default 100)

        Returns:
            ProbabilisticCTPResult with P10/P50/P90 CTP values
        """
        import numpy as np
        from app.services.sc_planning.stochastic_sampler import StochasticSampler

        # Get node for capacity lookup
        node = _get_player_node(self.db, scenario_user, game)
        if not node:
            logger.warning(f"No node found for scenario_user {scenario_user.id}")
            return ProbabilisticCTPResult(
                production_capacity=0,
                current_commitments=0,
                yield_rate_mean=1.0,
                yield_rate_stddev=0.0,
                ctp_p10=0,
                ctp_p50=0,
                ctp_p90=0,
                available_capacity_p10=0,
                available_capacity_p50=0,
                available_capacity_p90=0,
                constrained_by="no_node_configured",
                component_constraints=[],
                production_lead_time_mean=1.0,
                production_lead_time_stddev=0.0,
                simulation_runs=0,
                timestamp=datetime.utcnow().isoformat(),
            )

        # Get base values (deterministic)
        capacity = self._get_production_capacity(node)
        commitments = self._get_production_commitments(scenario_user, current_round)
        base_yield = self._get_yield_rate(node)
        base_lead_time = self._get_production_lead_time(node)

        # Initialize stochastic sampler
        sampler = StochasticSampler(scenario_id=game.id)

        # Run Monte Carlo simulation
        ctp_samples = []
        yield_samples = []
        lead_time_samples = []
        available_capacity_samples = []

        for _ in range(n_simulations):
            # Sample yield rate (with small variation around base)
            # In a full implementation, this would use production_process.yield_dist
            yield_variation = np.random.normal(0, 0.02)  # 2% std dev
            sampled_yield = max(0.5, min(1.0, base_yield + yield_variation))
            yield_samples.append(sampled_yield)

            # Sample production lead time
            lt_variation = np.random.normal(0, 0.3)  # Small variation
            sampled_lt = max(0.5, base_lead_time + lt_variation)
            lead_time_samples.append(sampled_lt)

            # Calculate available capacity with sampled yield
            available_capacity = max(0, capacity - commitments)
            available_after_yield = int(available_capacity * sampled_yield)
            available_capacity_samples.append(available_after_yield)

            # Check component constraints (use base calculation)
            component_constraints = self._check_component_atp(
                scenario_user, game, current_round, product_id, available_after_yield
            )

            # Calculate CTP for this simulation
            ctp = available_after_yield
            for constraint in component_constraints:
                if constraint.max_producible < ctp:
                    ctp = constraint.max_producible

            ctp_samples.append(ctp)

        # Calculate percentiles
        ctp_array = np.array(ctp_samples)
        yield_array = np.array(yield_samples)
        lt_array = np.array(lead_time_samples)
        cap_array = np.array(available_capacity_samples)

        ctp_p10 = int(np.percentile(ctp_array, 10))
        ctp_p50 = int(np.percentile(ctp_array, 50))
        ctp_p90 = int(np.percentile(ctp_array, 90))

        cap_p10 = int(np.percentile(cap_array, 10))
        cap_p50 = int(np.percentile(cap_array, 50))
        cap_p90 = int(np.percentile(cap_array, 90))

        # Determine primary constraint
        base_result = self.calculate_current_ctp(scenario_user, game, current_round, product_id)
        constrained_by = base_result.constrained_by

        logger.info(
            f"Probabilistic CTP for scenario_user {scenario_user.id}: "
            f"P10={ctp_p10}, P50={ctp_p50}, P90={ctp_p90} "
            f"(yield mean={np.mean(yield_array):.3f}, std={np.std(yield_array):.3f})"
        )

        return ProbabilisticCTPResult(
            production_capacity=capacity,
            current_commitments=commitments,
            yield_rate_mean=float(np.mean(yield_array)),
            yield_rate_stddev=float(np.std(yield_array)),
            ctp_p10=ctp_p10,
            ctp_p50=ctp_p50,
            ctp_p90=ctp_p90,
            available_capacity_p10=cap_p10,
            available_capacity_p50=cap_p50,
            available_capacity_p90=cap_p90,
            constrained_by=constrained_by,
            component_constraints=base_result.component_constraints,
            production_lead_time_mean=float(np.mean(lt_array)),
            production_lead_time_stddev=float(np.std(lt_array)),
            simulation_runs=n_simulations,
            timestamp=datetime.utcnow().isoformat(),
        )

    def project_ctp_multi_period(
        self,
        scenario_user: ScenarioUser,
        game: Game,
        current_round: ScenarioRound,
        item_id: int,
        periods: int = 8,
    ) -> List[CTPPeriod]:
        """
        Project CTP over rolling horizon.

        Considers:
        - Capacity loading (scheduled production)
        - Component availability (BOM)
        - Maintenance windows (capacity reductions) - NOT YET IMPLEMENTED

        Args:
            scenario_user: ScenarioUser instance (manufacturer)
            game: Game instance
            current_round: Current game round
            item_id: Item ID to produce
            periods: Number of future periods to project (default 8)

        Returns:
            List of CTPPeriod objects
        """
        projections = []

        node = _get_player_node(self.db, scenario_user, game)
        if not node:
            logger.warning(f"No node found for scenario_user {scenario_user.id} (site_key={scenario_user.site_key})")
            return []  # Return empty projections if no node
        capacity = self._get_production_capacity(node)
        yield_rate = self._get_yield_rate(node)

        for period_offset in range(1, periods + 1):
            future_round = current_round.round_number + period_offset

            # Get production commitments for future periods from ProductionOrder
            commitments = 0
            try:
                from app.models.production_order import ProductionOrder
                from datetime import timedelta
                active_statuses = ("PLANNED", "RELEASED", "IN_PROGRESS")
                period_start = datetime.utcnow() + timedelta(days=(period_offset - 1) * 7)
                period_end = period_start + timedelta(days=7)
                commitments = int(
                    self.db.query(
                        func.coalesce(func.sum(ProductionOrder.planned_quantity), 0)
                    )
                    .filter(
                        ProductionOrder.site_id == node.id,
                        ProductionOrder.status.in_(active_statuses),
                        ProductionOrder.planned_start_date >= period_start,
                        ProductionOrder.planned_start_date < period_end,
                    )
                    .scalar()
                )
            except Exception:
                commitments = 0

            # Available capacity
            available_capacity = max(0, capacity - commitments)

            # Component ATP: check BOM components at supplier sites via InvLevel
            component_atp = {}
            try:
                bom_entries = (
                    self.db.query(ProductBOM)
                    .filter(ProductBOM.product_id == str(item_id))
                    .all()
                )
                for entry in bom_entries:
                    comp_id = entry.component_product_id
                    comp_inv = (
                        self.db.query(
                            func.coalesce(func.sum(InvLevel.available_qty), 0)
                        )
                        .filter(InvLevel.product_id == comp_id)
                        .scalar()
                    )
                    component_atp[comp_id] = int(comp_inv)
            except Exception:
                pass

            # CTP for this period (minimum of capacity-based and component-constrained)
            available_after_yield = int(available_capacity * yield_rate)
            ctp = available_after_yield
            if component_atp:
                bom_entries_list = (
                    self.db.query(ProductBOM)
                    .filter(ProductBOM.product_id == str(item_id))
                    .all()
                ) if not component_atp else []
                for entry in (self.db.query(ProductBOM).filter(ProductBOM.product_id == str(item_id)).all()):
                    qty_per = entry.component_quantity or 1
                    comp_avail = component_atp.get(entry.component_product_id, 0)
                    max_from_comp = int(comp_avail / qty_per) if qty_per > 0 else 0
                    ctp = min(ctp, max_from_comp)

            # Utilization percentage
            utilization_pct = (
                (commitments / capacity * 100) if capacity > 0 else 0
            )

            projections.append(
                CTPPeriod(
                    period=future_round,
                    capacity=capacity,
                    commitments=commitments,
                    available_capacity=available_capacity,
                    component_atp=component_atp,
                    ctp=ctp,
                    utilization_pct=utilization_pct,
                )
            )

        logger.info(
            f"CTP projection for scenario_user {scenario_user.id} (item {item_id}): "
            f"{periods} periods generated"
        )

        return projections

    def calculate_promise_date(
        self,
        scenario_user: ScenarioUser,
        game: Game,
        current_round: ScenarioRound,
        item_id: int,
        quantity: int,
    ) -> PromiseDateResult:
        """
        Calculate earliest possible delivery date for quantity.

        Logic:
        1. Check if quantity <= immediate CTP → promise today + production lead time + shipping lead time
        2. If not, find future period where CTP >= quantity
        3. Account for production lead time + shipping lead time

        Args:
            scenario_user: ScenarioUser instance (manufacturer)
            game: Game instance
            current_round: Current game round
            item_id: Item ID to produce
            quantity: Quantity requested

        Returns:
            PromiseDateResult with earliest date, confidence, and constraints
        """
        # Get current CTP
        ctp_result = self.calculate_current_ctp(
            scenario_user, game, current_round, item_id
        )

        # Get lead times
        node = _get_player_node(self.db, scenario_user, game)
        production_lead_time = self._get_production_lead_time(node)
        shipping_lead_time = self._get_shipping_lead_time(node)
        total_lead_time = production_lead_time + shipping_lead_time

        constraints = []
        breakdown = []

        if quantity <= ctp_result.ctp:
            # Can fulfill immediately
            earliest_date = current_round.round_number + total_lead_time
            confidence = 0.95  # High confidence
            breakdown.append(
                f"Current CTP ({ctp_result.ctp} units) >= requested quantity ({quantity} units)"
            )
            breakdown.append(
                f"Production lead time: {production_lead_time} rounds"
            )
            breakdown.append(f"Shipping lead time: {shipping_lead_time} rounds")
            breakdown.append(
                f"Earliest delivery: Round {earliest_date} ({total_lead_time} rounds from now)"
            )
        else:
            # Need to find future period with sufficient CTP
            # Project CTP forward
            projection = self.project_ctp_multi_period(
                scenario_user, game, current_round, item_id, periods=8
            )

            # Find first period where CTP >= quantity
            found = False
            for period in projection:
                if period.ctp >= quantity:
                    earliest_date = period.period + total_lead_time
                    confidence = 0.75  # Medium confidence (future projection)
                    found = True
                    breakdown.append(
                        f"Current CTP ({ctp_result.ctp} units) < requested quantity ({quantity} units)"
                    )
                    breakdown.append(
                        f"Sufficient capacity available in Round {period.period} (CTP: {period.ctp})"
                    )
                    breakdown.append(
                        f"Production lead time: {production_lead_time} rounds"
                    )
                    breakdown.append(
                        f"Shipping lead time: {shipping_lead_time} rounds"
                    )
                    breakdown.append(
                        f"Earliest delivery: Round {earliest_date}"
                    )
                    constraints.append("capacity")
                    break

            if not found:
                # Cannot fulfill within projection window
                earliest_date = current_round.round_number + 8 + total_lead_time
                confidence = 0.3  # Low confidence
                breakdown.append(
                    f"Requested quantity ({quantity} units) exceeds CTP for next 8 rounds"
                )
                breakdown.append(
                    f"Earliest possible delivery: Round {earliest_date} (estimated)"
                )
                constraints.append("capacity")
                constraints.append("extended_lead_time")

        # Check for component constraints
        if ctp_result.constrained_by and "component" in ctp_result.constrained_by:
            constraints.append(ctp_result.constrained_by)
            for comp in ctp_result.component_constraints:
                if comp.shortfall > 0:
                    breakdown.append(
                        f"Component constraint: {comp.item_name} shortfall = {comp.shortfall} units"
                    )

        logger.info(
            f"Promise date for scenario_user {scenario_user.id}: quantity={quantity}, "
            f"earliest_date={earliest_date}, confidence={confidence:.2f}"
        )

        return PromiseDateResult(
            quantity=quantity,
            earliest_date=earliest_date,
            lead_time=total_lead_time,
            confidence=confidence,
            constraints=constraints,
            breakdown=breakdown,
        )

    # --- Helper Methods ---

    def _get_production_capacity(self, node: Node) -> int:
        """Get production capacity per round from node configuration or ProductionProcess."""
        # 1. Try node attribute
        if hasattr(node, "production_capacity_per_round") and node.production_capacity_per_round:
            return node.production_capacity_per_round

        # 2. Try site attributes JSON
        if hasattr(node, "attributes") and isinstance(node.attributes, dict):
            cap = node.attributes.get("production_capacity")
            if cap:
                return int(cap)

        # 3. Try ProductionProcess table
        try:
            from app.models.sc_entities import ProductionProcess
            proc = self.db.query(ProductionProcess).filter(
                ProductionProcess.site_id == node.id
            ).first()
            if proc and hasattr(proc, "manufacturing_capacity_hours") and proc.manufacturing_capacity_hours:
                return int(proc.manufacturing_capacity_hours)
        except Exception:
            pass

        # 4. Fallback defaults by node type
        capacity_defaults = {
            "manufacturer": 1000,
            "factory": 1000,
            "component_supplier": 800,
            "case_manufacturer": 600,
        }
        node_type = node.master_type or getattr(node, "dag_type", None) or "manufacturer"
        return capacity_defaults.get(
            node_type.lower() if node_type else "manufacturer", 1000
        )

    def _get_yield_rate(self, node: Node) -> float:
        """Get yield rate (accounts for scrap)"""
        # TODO: Query node.yield_rate field when available
        if hasattr(node, "yield_rate") and node.yield_rate:
            return node.yield_rate

        # Default 95% yield (5% scrap)
        return 0.95

    def _get_production_commitments(
        self, scenario_user: ScenarioUser, current_round: ScenarioRound
    ) -> int:
        """Get current production commitments (WIP + scheduled).

        Sums planned_quantity from ProductionOrder records that are
        PLANNED, RELEASED, or IN_PROGRESS for this scenario_user's site.
        """
        try:
            from app.models.production_order import ProductionOrder

            node = _get_player_node(self.db, scenario_user, current_round.game)
            if not node:
                return 0

            active_statuses = ("PLANNED", "RELEASED", "IN_PROGRESS")
            total = (
                self.db.query(
                    func.coalesce(func.sum(ProductionOrder.planned_quantity), 0)
                )
                .filter(
                    ProductionOrder.site_id == node.id,
                    ProductionOrder.status.in_(active_statuses),
                )
                .scalar()
            )
            return int(total)
        except Exception:
            return 0

    def _get_production_lead_time(self, node: Node) -> int:
        """Get production lead time from production_process table."""
        from app.models.sc_entities import ProductionProcess
        proc = self.db.query(ProductionProcess).filter(
            ProductionProcess.site_id == node.id
        ).first()
        if proc and hasattr(proc, 'lead_time_days') and proc.lead_time_days:
            return max(1, proc.lead_time_days)
        return 1  # Default 1 round

    def _get_shipping_lead_time(self, node: Node) -> int:
        """Get shipping lead time from downstream lane."""
        from app.models.supply_chain_config import TransportationLane
        lane = self.db.query(TransportationLane).filter(
            TransportationLane.from_node_id == node.id,
        ).first()
        if lane and lane.supply_lead_time:
            return max(1, lane.supply_lead_time)
        return 2  # Default 2 rounds

    def _get_component_atp(
        self,
        scenario_user: ScenarioUser,
        game: Game,
        component_product_id: str,
        current_round: ScenarioRound,
    ) -> int:
        """
        Get component ATP from supplier nodes.

        Phase 4 Implementation:
        1. First try SC-compliant path: SourcingRules → InvLevel
        2. Fallback to simulation path: Lanes → ScenarioUsers → ScenarioUserInventory

        Args:
            scenario_user: The manufacturer scenario_user requesting the component
            game: Current game
            component_product_id: Product ID of the component
            current_round: Current game round

        Returns:
            Total available ATP for the component from all suppliers
        """
        total_component_atp = 0

        # Get manufacturer's node for site lookup
        manufacturer_node = _get_player_node(self.db, scenario_user, game)
        if not manufacturer_node:
            logger.warning(f"No node found for manufacturer scenario_user {scenario_user.id}")
            return 10000  # Fallback to unlimited if no node config

        # Try SC-compliant path first: SourcingRules
        try:
            # Find sourcing rules for this component to this manufacturer's site
            sourcing_rules = (
                self.db.query(SourcingRules)
                .filter(
                    SourcingRules.product_id == component_product_id,
                    SourcingRules.is_active == 'true',
                )
                .order_by(SourcingRules.sourcing_priority)
                .all()
            )

            if sourcing_rules:
                for rule in sourcing_rules:
                    # Get supplier site ID
                    supplier_site_id = rule.from_site_id
                    if not supplier_site_id:
                        continue

                    # Query inventory level at supplier site
                    inv_level = (
                        self.db.query(InvLevel)
                        .filter(
                            InvLevel.product_id == component_product_id,
                            InvLevel.site_id == supplier_site_id,
                        )
                        .first()
                    )

                    if inv_level and inv_level.available_qty:
                        total_component_atp += int(inv_level.available_qty)
                        logger.debug(
                            f"Component {component_product_id} ATP from site {supplier_site_id}: "
                            f"{inv_level.available_qty}"
                        )

                if total_component_atp > 0:
                    logger.info(
                        f"Component {component_product_id} total ATP from sourcing rules: {total_component_atp}"
                    )
                    return total_component_atp

        except Exception as e:
            logger.debug(f"SC-compliant path failed for component ATP: {e}")

        # Fallback to simulation path: Check upstream scenario_users in the same scenario
        try:
            # Find upstream scenario_users (component suppliers) in the same game
            # For simulation, component suppliers are typically "component_supplier" or similar node types
            upstream_players = (
                self.db.query(ScenarioUser)
                .filter(
                    ScenarioUser.scenario_id == game.id,
                    ScenarioUser.id != scenario_user.id,  # Exclude the manufacturer
                )
                .all()
            )

            for upstream_player in upstream_players:
                # Check if this scenario_user has the component in their inventory
                if upstream_player.inventory and upstream_player.inventory.current_stock:
                    # For simplicity, assume all upstream scenario_users can supply components
                    # In a real implementation, you'd check item types and supply chains
                    upstream_atp = max(0, upstream_player.inventory.current_stock - 50)  # Reserve safety stock
                    total_component_atp += upstream_atp

            if total_component_atp > 0:
                logger.info(
                    f"Component {component_product_id} total ATP from upstream scenario_users: {total_component_atp}"
                )
                return total_component_atp

        except Exception as e:
            logger.debug(f"Simulation path failed for component ATP: {e}")

        # Final fallback: assume unlimited components
        # This ensures CTP calculations don't break when supply chain isn't fully configured
        logger.warning(
            f"No component ATP found for {component_product_id}, using default unlimited (10000)"
        )
        return 10000

    def _check_component_atp(
        self,
        scenario_user: ScenarioUser,
        game: Game,
        current_round: ScenarioRound,
        item_id: str,  # Now uses string product_id (SC compliant)
        max_producible_from_capacity: int,
    ) -> List[ComponentConstraint]:
        """
        Check component ATP via BOM explosion.

        Uses the SC-compliant ProductBom model with:
        - product_id: Parent product (String)
        - component_product_id: Component product (String)
        - component_quantity: Quantity per parent unit (Double)

        Returns list of component constraints with shortfalls.
        """
        # Query BOM for this product (parent)
        bom_entries = (
            self.db.query(ProductBOM)
            .filter(ProductBOM.product_id == str(item_id))
            .all()
        )

        if not bom_entries:
            # No BOM (simple manufactured item, no components)
            return []

        component_constraints = []

        for bom_entry in bom_entries:
            component_product_id = bom_entry.component_product_id
            quantity_per_unit = bom_entry.component_quantity or 1.0

            # Get component product details
            component_product = (
                self.db.query(Product)
                .filter(Product.id == component_product_id)
                .first()
            )

            if not component_product:
                logger.warning(
                    f"Component product {component_product_id} not found in BOM for product {item_id}"
                )
                continue

            # Find component supplier and calculate their ATP
            component_atp = self._get_component_atp(
                scenario_user=scenario_user,
                game=game,
                component_product_id=component_product_id,
                current_round=current_round
            )

            # Calculate max producible from this component
            # Ensure integer division (quantity_per_unit could be float)
            max_from_component = int(component_atp / quantity_per_unit)

            # Shortfall calculation
            if max_from_component < max_producible_from_capacity:
                shortfall_units = int(
                    (max_producible_from_capacity - max_from_component) * quantity_per_unit
                )
            else:
                shortfall_units = 0

            component_constraints.append(
                ComponentConstraint(
                    item_id=component_product_id,  # Now a string
                    item_name=component_product.description or f"Product-{component_product_id}",
                    required_per_unit=int(quantity_per_unit),
                    available_atp=component_atp,
                    max_producible=max_from_component,
                    shortfall=shortfall_units,
                )
            )

        return component_constraints

    def save_probabilistic_ctp(
        self,
        game: Game,
        scenario_user: ScenarioUser,
        result: ProbabilisticCTPResult,
        current_round: int,
        product_id: str,
    ) -> int:
        """
        Save probabilistic CTP result to database for historical tracking.

        Args:
            game: Game instance
            scenario_user: ScenarioUser instance
            result: ProbabilisticCTPResult from calculate_probabilistic_ctp
            current_round: Current round number
            product_id: AWS SC Product ID (string)

        Returns:
            ID of the saved record
        """
        try:
            from datetime import date
            from app.models.inventory_projection import CtpProjection

            # Get node for scenario_user
            node = _get_player_node(self.db, scenario_user, game)
            if not node:
                logger.warning(f"Cannot save CTP - no node for scenario_user {scenario_user.id}")
                return None

            # Create CTP projection record
            ctp_record = CtpProjection(
                company_id=game.tenant_id or 1,
                product_id=product_id,
                site_id=node.id,
                ctp_date=date.today(),
                ctp_qty=float(result.ctp_p50),
                atp_qty=0.0,  # CTP for manufacturers doesn't use ATP component
                production_capacity_qty=float(result.production_capacity),
                total_capacity=float(result.production_capacity),
                committed_capacity=float(result.current_commitments),
                available_capacity=float(result.available_capacity_p50),
                # Probabilistic fields
                ctp_p10=result.ctp_p10,
                ctp_p90=result.ctp_p90,
                production_lead_time_mean=result.production_lead_time_mean,
                production_lead_time_stddev=result.production_lead_time_stddev,
                # Constraints
                component_constrained=(result.constrained_by == "component"),
                resource_constrained=(result.constrained_by == "capacity"),
                constraining_resource=result.constrained_by,
                # Game integration
                scenario_id=game.id,
                source="probabilistic_ctp",
                source_event_id=f"game_{game.id}_round_{current_round}",
            )

            self.db.add(ctp_record)
            self.db.commit()
            self.db.refresh(ctp_record)

            logger.info(
                f"Saved probabilistic CTP record {ctp_record.id} for scenario_user {scenario_user.id}: "
                f"P10={result.ctp_p10}, P50={result.ctp_p50}, P90={result.ctp_p90}"
            )

            return ctp_record.id

        except Exception as e:
            logger.error(f"Failed to save probabilistic CTP: {e}", exc_info=True)
            self.db.rollback()
            return None


# Factory function for creating service instances
from fastapi import Depends
from app.db.session import get_db, get_sync_db

def get_ctp_service(db: Session = Depends(get_sync_db)) -> CTPService:
    """Factory function to create CTPService"""
    return CTPService(db)
