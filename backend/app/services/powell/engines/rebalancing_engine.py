"""
Rebalancing Engine - 100% Deterministic

Implements cross-location inventory rebalancing rules:
- Identify excess/deficit sites by days-of-supply thresholds
- Calculate transfer quantities (min of source excess, dest deficit)
- Apply lane constraints (min/max quantity, availability)
- Classify reason: stockout risk, excess inventory, service level

This engine handles the mathematically defined operations.
TRM heads handle urgency prioritization and quantity refinement.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class RebalancingConfig:
    """Rebalancing engine configuration"""
    excess_threshold: float = 1.5   # DOS > target * 1.5 = excess
    deficit_threshold: float = 0.75  # DOS < target * 0.75 = deficit
    stockout_risk_threshold: float = 0.5  # Risk above this = STOCKOUT_RISK reason
    excess_dos_multiplier: float = 2.0  # DOS > target * 2.0 = EXCESS_INVENTORY reason
    min_transfer_benefit: float = 0.1  # Minimum DOS improvement to recommend


@dataclass
class SiteState:
    """Site inventory state for rebalancing evaluation"""
    site_id: str
    available: float       # on_hand + in_transit - committed - backlog
    safety_stock: float
    days_of_supply: float
    target_dos: float
    stockout_risk: float   # 0-1 probability
    demand_forecast: float  # For DOS recalculation after transfer


@dataclass
class LaneConstraints:
    """Transfer lane constraints"""
    from_site: str
    to_site: str
    min_qty: float = 0.0
    max_qty: float = float('inf')
    transfer_time: float = 3.0  # Days
    cost_per_unit: float = 1.0
    is_available: bool = True


@dataclass
class TransferRecommendation:
    """Deterministic transfer recommendation"""
    from_site: str
    to_site: str
    quantity: float
    reason: str   # "stockout_risk", "excess_inventory", "service_level"

    # Pre/post state
    source_dos_before: float
    source_dos_after: float
    dest_dos_before: float
    dest_dos_after: float

    # Cost/time
    expected_cost: float
    transfer_time: float

    # Urgency (deterministic: higher stockout risk = higher urgency)
    urgency: float  # 0-1


class RebalancingEngine:
    """
    Inventory rebalancing engine.

    100% deterministic - same inputs always produce same outputs.
    No neural networks, no learned components.
    """

    def __init__(self, site_key: str = "", config: Optional[RebalancingConfig] = None):
        self.site_key = site_key
        self.config = config or RebalancingConfig()

    def identify_candidate_pairs(
        self,
        site_states: Dict[str, SiteState],
        lanes: List[LaneConstraints]
    ) -> List[Tuple[str, str]]:
        """
        Identify candidate source-destination pairs.

        Sources: sites with DOS > target * excess_threshold
        Destinations: sites with DOS < target * deficit_threshold
        """
        excess_sites = []
        deficit_sites = []

        for site_id, state in site_states.items():
            if state.days_of_supply > state.target_dos * self.config.excess_threshold:
                excess_sites.append((site_id, state.days_of_supply - state.target_dos))
            elif state.days_of_supply < state.target_dos * self.config.deficit_threshold:
                deficit_sites.append((site_id, state.target_dos - state.days_of_supply))

        # Match pairs with available lanes
        lane_lookup = {(l.from_site, l.to_site): l for l in lanes if l.is_available}
        pairs = []
        for source_id, _ in excess_sites:
            for dest_id, _ in deficit_sites:
                if (source_id, dest_id) in lane_lookup:
                    pairs.append((source_id, dest_id))

        return pairs

    def evaluate_pair(
        self,
        from_state: SiteState,
        to_state: SiteState,
        lane: LaneConstraints
    ) -> Optional[TransferRecommendation]:
        """
        Evaluate a single source-destination pair.

        Algorithm:
        1. source_excess = available - safety_stock
        2. dest_deficit = safety_stock - available
        3. quantity = min(source_excess, dest_deficit)
        4. Apply lane constraints
        5. Classify reason
        """
        if not lane.is_available:
            return None

        # Calculate optimal transfer quantity
        source_excess = from_state.available - from_state.safety_stock
        dest_deficit = to_state.safety_stock - to_state.available

        if source_excess <= 0 or dest_deficit <= 0:
            return None

        # Transfer enough to bring dest to safety stock, limited by source excess
        quantity = min(source_excess, dest_deficit)

        # Apply lane constraints
        quantity = max(lane.min_qty, min(quantity, lane.max_qty))

        if quantity <= 0:
            return None

        # Determine reason based on conditions
        if to_state.stockout_risk > self.config.stockout_risk_threshold:
            reason = "stockout_risk"
        elif from_state.days_of_supply > from_state.target_dos * self.config.excess_dos_multiplier:
            reason = "excess_inventory"
        else:
            reason = "service_level"

        # Calculate DOS after transfer
        source_available_after = from_state.available - quantity
        dest_available_after = to_state.available + quantity

        source_daily = from_state.demand_forecast / 30 if from_state.demand_forecast > 0 else 1e-6
        dest_daily = to_state.demand_forecast / 30 if to_state.demand_forecast > 0 else 1e-6

        source_dos_after = source_available_after / source_daily
        dest_dos_after = dest_available_after / dest_daily

        # Urgency: higher stockout risk and lower DOS = more urgent
        urgency = min(1.0, to_state.stockout_risk + max(0, 1 - to_state.days_of_supply / to_state.target_dos))

        return TransferRecommendation(
            from_site=from_state.site_id,
            to_site=to_state.site_id,
            quantity=quantity,
            reason=reason,
            source_dos_before=from_state.days_of_supply,
            source_dos_after=source_dos_after,
            dest_dos_before=to_state.days_of_supply,
            dest_dos_after=dest_dos_after,
            expected_cost=quantity * lane.cost_per_unit,
            transfer_time=lane.transfer_time,
            urgency=urgency,
        )

    def evaluate_network(
        self,
        site_states: Dict[str, SiteState],
        lanes: List[LaneConstraints],
        max_recommendations: int = 10
    ) -> List[TransferRecommendation]:
        """
        Evaluate all candidate pairs and return sorted recommendations.
        """
        pairs = self.identify_candidate_pairs(site_states, lanes)
        lane_lookup = {(l.from_site, l.to_site): l for l in lanes}

        recommendations = []
        for from_id, to_id in pairs:
            from_state = site_states[from_id]
            to_state = site_states[to_id]
            lane = lane_lookup.get((from_id, to_id))

            if lane is None:
                continue

            rec = self.evaluate_pair(from_state, to_state, lane)
            if rec is not None and rec.quantity > 0:
                recommendations.append(rec)

        # Sort by urgency (highest first)
        recommendations.sort(key=lambda r: -r.urgency)
        return recommendations[:max_recommendations]
