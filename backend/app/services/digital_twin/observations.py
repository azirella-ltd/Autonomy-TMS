"""TMS-shaped (state, action, reward) dataclasses for the lane-flow twin.

Parallel to Autonomy-Core's TwinObservation / TwinAction / TwinReward
(`packages/data-model/src/azirella_data_model/digital_twin/twin_interface.py`).
The Core class is currently SCP-shaped (on_hand, in_transit, backlog,
safety_stock, BOM fields). Per
Autonomy-Core/docs/architecture/TWIN_AND_ENVELOPES.md §9 bullet 3, Core
will slim TwinObservation into a generic base with SCP-specific fields
moved to a subclass. When that lands, LaneFlowObservation migrates to
inherit from the slimmed Core base. Until then the TMS shape lives here.

State node per TWIN_AND_ENVELOPES.md §3: (lane × carrier × equipment ×
hour-or-day). PR-1 captures the fields the lane-flow simulator and
policy network need; the full multi-grain shape is finalised in PR-3
when the simulator's physics is implemented.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LaneFlowObservation:
    """State snapshot for a single (transportation_lane, period) cell.

    Carrier-flow plane only — no on_hand, no inventory, no BOM. The
    upstream supply state is encoded via the shipment generator's
    arrival stream, not in the observation.

    Bucket size follows the simulator's tier (TACTICAL=week,
    EXECUTION=day/hour). The `period` field is the bucket index;
    `plan_date` carries the wall-clock anchor when seasonal
    stratification is enabled.
    """

    transportation_lane_id: str
    period: int

    # Lane-grain in-flight state.
    in_flight_loads: int
    """Loads dispatched on this lane that have not yet arrived."""

    arrivals_this_period: int
    """Line-item shipments emitted by the generator for this lane × period.
    The simulator reads this from the registered TransferOrderEnvelope; the
    observation surfaces it for the policy."""

    # Capacity / equipment state.
    carrier_capacity_remaining: float
    """Remaining contracted carrier capacity on this lane in load units."""

    equipment_available: int
    """Equipment units (trailers / containers) available at the lane's
    origin terminal."""

    dock_queue_depth: int
    """Queue depth at the destination dock for this lane."""

    # Trailing-window performance signals — what the policy and reward fn
    # need to react to recent service quality.
    on_time_pct_trailing: float
    """Fraction of loads delivered on time over the trailing 4 buckets,
    in [0, 1]. Sentinel 1.0 when no loads have completed yet."""

    cost_per_load_trailing: float
    """Mean realised carrier cost per load over the trailing 4 buckets."""

    # Calendar-anchoring (populated when seasonal stratification is on —
    # PR-4 wires this).
    plan_date: Any = None
    as_of: Any = None


@dataclass(frozen=True)
class LaneFlowAction:
    """Decision emitted by the lane-flow policy.

    Multi-discrete: which carrier, which equipment kind, with a
    continuous dispatch-timing offset and an optional reposition
    instruction. Mirrors the action shape in TWIN_AND_ENVELOPES.md §3
    (load assignment + carrier + dock + reposition).
    """

    carrier_id: str
    """Selected carrier (canonical AWS SC trading-partner id)."""

    equipment_kind: str
    """Selected equipment archetype, e.g. ``dry_van_53``, ``reefer_48``,
    ``container_40hc``. Free-text in PR-1; constrained to a tenant's
    `equipment_kind` master in PR-3."""

    dispatch_offset_hours: float
    """Hours from the bucket boundary at which to dispatch. 0.0 means
    dispatch at the start of the bucket."""

    reposition_to_site_id: str | None = None
    """Optional reposition target. ``None`` means no reposition this
    decision."""

    confidence: float = 1.0
    """Policy confidence in [0, 1]. Used by the RL loop for exploration
    schedules and by the AIIO mode for INFORM/INSPECT routing."""

    rationale: str = ""


@dataclass(frozen=True)
class LaneFlowReward:
    """Per-step reward with attribution.

    `total` is what the RL loss sees. The components let training code
    debug which term dominates. Reward axes per TWIN_AND_ENVELOPES.md §3
    (per-plan BSC: OTD%, cost/mile, utilisation, override rate).

    Sign convention follows Core's TwinReward: higher total is better.
    Penalty terms are stored positive but combined as subtractions in
    `total` (the simulator computes `total`; this dataclass only carries
    the values).
    """

    total: float
    on_time_score: float = 0.0
    """Service-quality term in [-1, 1]. Maps OTD% via the same baseline /
    target shape Core's TwinReward uses for fill_rate."""

    cost_per_load: float = 0.0
    """Realised carrier cost per load this step (positive = cost incurred)."""

    dock_utilization: float = 0.0
    """Distance from dock-utilisation target, in [0, 1]. 0.0 means at target."""

    equipment_balance: float = 0.0
    """Net equipment imbalance / fleet size at the lane's origin terminal
    after this step, in [0, 1]."""

    override_churn: float = 0.0
    """|action[t] − action[t−1]| churn signal for stability."""


@dataclass
class LaneFlowTransition:
    """One (s, a, r, s') tuple — the unit a Core RolloutHarness consumes."""

    observation: LaneFlowObservation
    action: LaneFlowAction
    reward: LaneFlowReward
    next_observation: LaneFlowObservation | None
    done: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "LaneFlowAction",
    "LaneFlowObservation",
    "LaneFlowReward",
    "LaneFlowTransition",
]
