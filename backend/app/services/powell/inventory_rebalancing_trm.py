"""
Inventory Rebalancing TRM

Narrow TRM for cross-location inventory rebalancing decisions.
Decides when and how much to transfer between locations.

TRM Scope (narrow):
- Given: inventory levels at multiple sites, demand forecasts, transfer costs/times
- Decide: Should we rebalance? From where to where? How much?

Characteristics that make this suitable for TRM:
- Narrow scope: few variables per decision
- Short horizon: transfers complete in days
- Fast feedback: see impact on fill rates quickly
- Clear objective: balance service vs cost
- Repeatable: happens frequently with similar patterns

References:
- Conversation with Claude on TRM scope
- Powell VFA for narrow execution decisions
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import numpy as np
import logging

from .engines.rebalancing_engine import (
    RebalancingEngine, RebalancingConfig,
    SiteState as EngineSiteState, LaneConstraints,
)

logger = logging.getLogger(__name__)


class RebalanceReason(Enum):
    """Reason for rebalancing recommendation"""
    STOCKOUT_RISK = "stockout_risk"  # Destination at risk of stockout
    EXCESS_INVENTORY = "excess_inventory"  # Source has excess
    DEMAND_SHIFT = "demand_shift"  # Demand pattern shifted
    SERVICE_LEVEL = "service_level"  # Service level imbalance
    COST_OPTIMIZATION = "cost_optimization"  # Reduce holding costs
    PROACTIVE = "proactive"  # Anticipatory rebalance


@dataclass
class SiteInventoryState:
    """Inventory state at a single site"""
    site_id: str
    product_id: str

    # Current state
    on_hand: float
    in_transit: float  # Incoming transfers
    committed: float  # Reserved for orders
    backlog: float

    # Forecast
    demand_forecast: float  # Expected demand for review period
    demand_uncertainty: float  # From conformal prediction

    # Targets
    safety_stock: float
    target_dos: float  # Days of supply target

    # Context from tGNN
    criticality_score: float = 0.5  # How critical is this site
    supply_risk_score: float = 0.0  # Risk of supply disruption

    @property
    def available(self) -> float:
        """Available inventory"""
        return max(0, self.on_hand + self.in_transit - self.committed - self.backlog)

    @property
    def inventory_position(self) -> float:
        """Inventory position"""
        return self.on_hand + self.in_transit - self.committed - self.backlog

    @property
    def days_of_supply(self) -> float:
        """Days of supply based on forecast"""
        if self.demand_forecast <= 0:
            return float('inf')
        return self.available / (self.demand_forecast / 30)  # Assuming monthly forecast

    @property
    def stockout_risk(self) -> float:
        """Probability of stockout (simple heuristic)"""
        if self.available <= 0:
            return 1.0
        if self.demand_uncertainty <= 0:
            return 0.0
        # Simple Z-score based
        z = (self.available - self.demand_forecast) / max(1, self.demand_uncertainty)
        return max(0, min(1, 0.5 - z * 0.2))

    def to_features(self) -> np.ndarray:
        """Convert to feature vector for TRM"""
        return np.array([
            self.on_hand,
            self.in_transit,
            self.committed,
            self.backlog,
            self.demand_forecast,
            self.demand_uncertainty,
            self.safety_stock,
            self.target_dos,
            self.criticality_score,
            self.supply_risk_score,
            self.days_of_supply if self.days_of_supply != float('inf') else 999,
            self.stockout_risk,
        ], dtype=np.float32)


@dataclass
class TransferLane:
    """Transfer lane between two sites"""
    from_site: str
    to_site: str
    transfer_time: float  # Days
    cost_per_unit: float
    min_qty: float = 0.0
    max_qty: float = float('inf')
    is_available: bool = True


@dataclass
class RebalanceRecommendation:
    """Recommendation for inventory rebalancing"""
    from_site: str
    to_site: str
    product_id: str
    quantity: float

    # Context
    reason: RebalanceReason
    urgency: float  # 0-1, higher = more urgent
    confidence: float  # 0-1, TRM confidence

    # Expected impact
    expected_service_improvement: float  # Percentage points
    expected_cost: float
    expected_arrival: float  # Days

    # Source and destination state
    source_dos_before: float
    source_dos_after: float
    dest_dos_before: float
    dest_dos_after: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_site": self.from_site,
            "to_site": self.to_site,
            "product_id": self.product_id,
            "quantity": self.quantity,
            "reason": self.reason.value,
            "urgency": self.urgency,
            "confidence": self.confidence,
            "expected_service_improvement": self.expected_service_improvement,
            "expected_cost": self.expected_cost,
            "expected_arrival": self.expected_arrival,
            "source_dos": {"before": self.source_dos_before, "after": self.source_dos_after},
            "dest_dos": {"before": self.dest_dos_before, "after": self.dest_dos_after},
        }


@dataclass
class RebalancingState:
    """
    State representation for TRM rebalancing decisions.

    Captures the network state at decision time.
    """
    product_id: str
    site_states: Dict[str, SiteInventoryState]
    transfer_lanes: List[TransferLane]

    # Network-level context from tGNN
    network_imbalance_score: float = 0.0  # How imbalanced is the network
    total_network_inventory: float = 0.0
    total_network_demand: float = 0.0

    def get_pair_features(self, from_site: str, to_site: str) -> np.ndarray:
        """Get features for a specific transfer pair"""
        source = self.site_states.get(from_site)
        dest = self.site_states.get(to_site)

        if source is None or dest is None:
            return np.zeros(30, dtype=np.float32)

        # Find lane
        lane = None
        for l in self.transfer_lanes:
            if l.from_site == from_site and l.to_site == to_site:
                lane = l
                break

        source_features = source.to_features()
        dest_features = dest.to_features()

        lane_features = np.array([
            lane.transfer_time if lane else 999,
            lane.cost_per_unit if lane else 999,
            1.0 if lane and lane.is_available else 0.0,
        ], dtype=np.float32)

        network_features = np.array([
            self.network_imbalance_score,
            self.total_network_inventory,
            self.total_network_demand,
        ], dtype=np.float32)

        return np.concatenate([source_features, dest_features, lane_features, network_features])


class InventoryRebalancingTRM:
    """
    TRM-based service for inventory rebalancing decisions.

    Makes narrow decisions about when and how to rebalance inventory
    across locations within a supply chain network.

    Architecture:
    - tGNN provides: network state, criticality scores, demand signals
    - TRM decides: specific transfer recommendations
    """

    def __init__(
        self,
        trm_model: Optional[Any] = None,
        use_heuristic_fallback: bool = True,
        min_transfer_benefit: float = 0.1,  # Minimum DOS improvement to recommend
        max_recommendations_per_run: int = 10,
        rebalancing_engine: Optional[RebalancingEngine] = None,
        db: Optional[Any] = None,
        config_id: Optional[int] = None,
    ):
        """
        Initialize rebalancing TRM.

        Args:
            trm_model: Trained TRM model (optional)
            use_heuristic_fallback: Use heuristic if TRM unavailable
            min_transfer_benefit: Minimum benefit threshold
            max_recommendations_per_run: Limit recommendations per evaluation
            rebalancing_engine: Deterministic rebalancing engine (optional)
            db: Optional SQLAlchemy Session for persisting decisions
            config_id: Optional config_id for DB persistence
        """
        self._engine = rebalancing_engine or RebalancingEngine()
        self.trm_model = trm_model
        self.use_heuristic_fallback = use_heuristic_fallback
        self.min_transfer_benefit = min_transfer_benefit
        self.max_recommendations_per_run = max_recommendations_per_run
        self.db = db
        self.config_id = config_id

        # Decision history for training
        self._decision_history: List[Dict[str, Any]] = []

    def evaluate_rebalancing(
        self,
        state: RebalancingState
    ) -> List[RebalanceRecommendation]:
        """
        Evaluate rebalancing opportunities for a product.

        Args:
            state: Current network state for the product

        Returns:
            List of rebalancing recommendations, sorted by urgency
        """
        recommendations = []

        # Identify potential source-destination pairs
        pairs = self._identify_candidate_pairs(state)

        for from_site, to_site in pairs:
            if self.trm_model is not None:
                rec = self._trm_evaluate_pair(state, from_site, to_site)
            elif self.use_heuristic_fallback:
                rec = self._heuristic_evaluate_pair(state, from_site, to_site)
            else:
                continue

            if rec is not None and rec.quantity > 0:
                recommendations.append(rec)

        # Sort by urgency and limit
        recommendations.sort(key=lambda r: -r.urgency)
        final = recommendations[:self.max_recommendations_per_run]

        # Persist to DB if session available
        self._persist_recommendations(final)

        return final

    def _identify_candidate_pairs(
        self,
        state: RebalancingState
    ) -> List[Tuple[str, str]]:
        """Identify candidate source-destination pairs"""
        pairs = []

        # Find sites with excess (potential sources)
        excess_sites = []
        deficit_sites = []

        for site_id, site_state in state.site_states.items():
            dos = site_state.days_of_supply
            target = site_state.target_dos

            if dos > target * 1.5:  # More than 50% above target
                excess_sites.append((site_id, dos - target))
            elif dos < target * 0.75:  # Less than 75% of target
                deficit_sites.append((site_id, target - dos))

        # Create pairs with available lanes
        for source_id, excess in excess_sites:
            for dest_id, deficit in deficit_sites:
                # Check if lane exists and is available
                for lane in state.transfer_lanes:
                    if (lane.from_site == source_id and
                            lane.to_site == dest_id and
                            lane.is_available):
                        pairs.append((source_id, dest_id))
                        break

        return pairs

    def _trm_evaluate_pair(
        self,
        state: RebalancingState,
        from_site: str,
        to_site: str
    ) -> Optional[RebalanceRecommendation]:
        """Evaluate a pair using TRM"""
        try:
            features = state.get_pair_features(from_site, to_site)

            # TRM outputs dict: transfer_logit, transfer_qty, confidence, value
            output = self.trm_model.predict(features.reshape(1, -1))

            should_transfer = float(output["transfer_logit"][0, 0]) > 0.0
            quantity = max(0, float(output["transfer_qty"][0, 0]))
            confidence = float(np.clip(output["confidence"][0, 0], 0, 1))

            if not should_transfer or quantity <= 0:
                return None

            return self._build_recommendation(
                state, from_site, to_site, quantity,
                RebalanceReason.PROACTIVE, confidence
            )

        except Exception as e:
            logger.warning(f"TRM evaluation failed: {e}")
            return self._heuristic_evaluate_pair(state, from_site, to_site)

    def _heuristic_evaluate_pair(
        self,
        state: RebalancingState,
        from_site: str,
        to_site: str
    ) -> Optional[RebalanceRecommendation]:
        """Evaluate a pair using deterministic engine, then wrap in TRM recommendation."""
        source = state.site_states.get(from_site)
        dest = state.site_states.get(to_site)

        if source is None or dest is None:
            return None

        # Find lane
        lane = None
        for l in state.transfer_lanes:
            if l.from_site == from_site and l.to_site == to_site:
                lane = l
                break

        if lane is None or not lane.is_available:
            return None

        # Delegate to deterministic engine
        engine_from = EngineSiteState(
            site_id=from_site,
            available=source.available,
            safety_stock=source.safety_stock,
            days_of_supply=source.days_of_supply,
            target_dos=source.target_dos,
            stockout_risk=source.stockout_risk,
            demand_forecast=source.demand_forecast,
        )
        engine_to = EngineSiteState(
            site_id=to_site,
            available=dest.available,
            safety_stock=dest.safety_stock,
            days_of_supply=dest.days_of_supply,
            target_dos=dest.target_dos,
            stockout_risk=dest.stockout_risk,
            demand_forecast=dest.demand_forecast,
        )
        engine_lane = LaneConstraints(
            from_site=from_site,
            to_site=to_site,
            min_qty=lane.min_qty,
            max_qty=lane.max_qty,
            transfer_time=lane.transfer_time,
            cost_per_unit=lane.cost_per_unit,
            is_available=lane.is_available,
        )

        engine_result = self._engine.evaluate_pair(engine_from, engine_to, engine_lane)
        if engine_result is None or engine_result.quantity <= 0:
            return None

        # Map engine reason string to TRM enum
        reason_map = {
            "stockout_risk": RebalanceReason.STOCKOUT_RISK,
            "excess_inventory": RebalanceReason.EXCESS_INVENTORY,
            "service_level": RebalanceReason.SERVICE_LEVEL,
        }
        reason = reason_map.get(engine_result.reason, RebalanceReason.SERVICE_LEVEL)

        return self._build_recommendation(
            state, from_site, to_site, engine_result.quantity, reason, 0.8
        )

    def _build_recommendation(
        self,
        state: RebalancingState,
        from_site: str,
        to_site: str,
        quantity: float,
        reason: RebalanceReason,
        confidence: float
    ) -> RebalanceRecommendation:
        """Build a complete recommendation"""
        source = state.site_states[from_site]
        dest = state.site_states[to_site]

        # Find lane for cost/time
        lane = None
        for l in state.transfer_lanes:
            if l.from_site == from_site and l.to_site == to_site:
                lane = l
                break

        transfer_time = lane.transfer_time if lane else 3.0
        cost = quantity * (lane.cost_per_unit if lane else 1.0)

        # Calculate DOS changes
        source_dos_before = source.days_of_supply
        dest_dos_before = dest.days_of_supply

        # After transfer
        source_available_after = source.available - quantity
        dest_available_after = dest.available + quantity

        source_dos_after = (
            source_available_after / (source.demand_forecast / 30)
            if source.demand_forecast > 0 else 999
        )
        dest_dos_after = (
            dest_available_after / (dest.demand_forecast / 30)
            if dest.demand_forecast > 0 else 999
        )

        # Calculate urgency
        urgency = min(1.0, dest.stockout_risk + (1 - dest.days_of_supply / dest.target_dos))

        # Expected service improvement (simple estimate)
        service_improvement = min(0.2, dest.stockout_risk * 0.5)

        return RebalanceRecommendation(
            from_site=from_site,
            to_site=to_site,
            product_id=state.product_id,
            quantity=quantity,
            reason=reason,
            urgency=urgency,
            confidence=confidence,
            expected_service_improvement=service_improvement,
            expected_cost=cost,
            expected_arrival=transfer_time,
            source_dos_before=source_dos_before,
            source_dos_after=source_dos_after,
            dest_dos_before=dest_dos_before,
            dest_dos_after=dest_dos_after,
        )

    def _persist_recommendations(self, recommendations: List[RebalanceRecommendation]):
        """Persist recommendations to powell_rebalance_decisions table."""
        if self.db is None or self.config_id is None:
            return
        try:
            from app.models.powell_decisions import PowellRebalanceDecision
            for rec in recommendations:
                row = PowellRebalanceDecision(
                    config_id=self.config_id,
                    product_id=rec.product_id,
                    from_site=rec.from_site,
                    to_site=rec.to_site,
                    recommended_qty=rec.quantity,
                    reason=rec.reason.value,
                    urgency=rec.urgency,
                    confidence=rec.confidence,
                    source_dos_before=rec.source_dos_before,
                    source_dos_after=rec.source_dos_after,
                    dest_dos_before=rec.dest_dos_before,
                    dest_dos_after=rec.dest_dos_after,
                    expected_cost=rec.expected_cost,
                )
                self.db.add(row)
        except Exception as e:
            logger.warning(f"Failed to persist rebalance decisions: {e}")

    def record_outcome(
        self,
        recommendation: RebalanceRecommendation,
        was_executed: bool,
        actual_outcome: Optional[Dict[str, Any]] = None
    ):
        """
        Record outcome for TRM training.

        Args:
            recommendation: The recommendation that was made
            was_executed: Whether the transfer was executed
            actual_outcome: Actual results (service improvement, etc.)
        """
        record = {
            "recommendation": recommendation.to_dict(),
            "was_executed": was_executed,
            "actual_outcome": actual_outcome,
        }
        self._decision_history.append(record)

        if len(self._decision_history) > 10000:
            self._decision_history = self._decision_history[-10000:]

    def get_training_data(self) -> List[Dict[str, Any]]:
        """Get decision history for TRM training"""
        return self._decision_history
