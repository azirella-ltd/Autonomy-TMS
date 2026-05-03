"""§3.41 Phase 3.1 — Training data ETL for the GraphSAGE Movement Planner.

Walks historical ``TransportationPlanItem`` rows joined with
``FreightCharge`` actuals + ``RateCard`` snapshots and emits
``MovementPlannerTrainingExample`` tuples suitable for supervised
training of the Phase 3.2 GraphSAGE model.

## Training-target shape

Each example is a (state, action, observed_outcome) tuple:

- **state**: lane + period + mode + equipment + forecast volume +
  rate-card features (base_rate, rate_basis) + lane geography (origin/
  dest geo, distance) + carrier metadata (status, contract type).
- **action**: which carrier was assigned (one of N candidates).
- **observed_outcome**: actual freight charge total + actual delivery
  on-time? (when ``FreightCharge`` row exists; otherwise NULL).

Phase 3.2 trains a GNN to predict the action (carrier choice) that
minimises observed cost while respecting capacity constraints.

## Training-set construction

The extractor walks ``TransportationPlanItem`` rows where:

1. ``status`` is ``CONFIRMED`` or ``COMPLETED`` (Phase 2A planner
   ran + the load actually shipped).
2. ``carrier_id IS NOT NULL`` (we have a labeled action).
3. ``estimated_cost IS NOT NULL`` (we have at least the planner's
   cost prediction; observed cost via ``FreightCharge`` join is
   optional but preferred).
4. The plan's ``period_start`` is in the requested window.

Per-tenant scoping is mandatory. Cross-tenant model training is a
separate workstream (per CLAUDE.md tenant-isolation requirements).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Iterator, List, Optional

from sqlalchemy.orm import Session

from app.models.tms_planning import (
    PlanStatus,
    PlanItemStatus,
    TransportationPlan,
    TransportationPlanItem,
)


@dataclass(frozen=True)
class MovementPlannerTrainingExample:
    """One (state, action, outcome) tuple for the GraphSAGE Movement
    Planner. Phase 3.2 will batch these into mini-batches and feed
    them into the GNN's training loop.
    """

    # State features (input to the GNN)
    tenant_id: int
    plan_id: int
    item_id: int
    lane_id: int
    period_start: date
    period_days: int
    mode: str
    equipment_type: Optional[str]
    distance_miles: Optional[float]

    # Action — the carrier the planner picked at runtime
    action_carrier_id: int
    action_rate_id: Optional[int]
    action_estimated_cost: Optional[float]

    # Observed outcome (labels for supervised training)
    observed_total_cost: Optional[float]
    """From ``FreightCharge.total_amount`` when the load is invoiced;
    ``None`` for items still in transit or unbilled."""

    observed_on_time: Optional[bool]
    """``True`` when ``planned_delivery_date >= actual_delivery_date``
    (when present); ``None`` when no actual recorded."""

    # Carrier-level context (sparse; resolved at training time when
    # the trainer needs it for graph node features)
    carrier_metadata: Dict[str, Any] = field(default_factory=dict)
    """Sparse dict of carrier facts at planning time: SCAC, type,
    status. Resolved lazily so the extractor doesn't re-query the
    same Carrier row for every item."""

    rate_card_metadata: Dict[str, Any] = field(default_factory=dict)
    """Rate-card snapshot: base_rate, rate_basis, lane_filter,
    effective_window."""


class MovementPlannerTrainingDataExtractor:
    """ETL service that yields training examples from historical
    ``TransportationPlanItem`` rows.

    Design notes:

    - **Streaming via generator**: ``extract()`` returns an iterator,
      not a list, so callers can stream into a training loop without
      loading the whole tenant history into memory.
    - **Tenant-scoped**: cross-tenant training is a separate workstream
      with its own privacy / compliance review. ``extract()`` requires
      ``tenant_id``.
    - **Per-call carrier / rate-card cache**: the extractor caches
      ``Carrier`` + ``RateCard`` lookups across items to avoid N+1
      queries when the same rate card appears across many items.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._carrier_cache: Dict[int, Dict[str, Any]] = {}
        self._rate_card_cache: Dict[int, Dict[str, Any]] = {}

    def extract(
        self,
        *,
        tenant_id: int,
        period_start_min: Optional[date] = None,
        period_start_max: Optional[date] = None,
        only_completed: bool = False,
    ) -> Iterator[MovementPlannerTrainingExample]:
        """Yield training examples for the given tenant.

        Filters:

        - ``period_start_min`` / ``period_start_max``: restrict to
          plans whose ``plan_start_date`` falls in this window.
        - ``only_completed``: when True, only items with status
          ``COMPLETED`` (the load actually delivered) are included.
          When False (default), ``CONFIRMED`` items are also yielded —
          useful for in-flight monitoring or partial-history training.
        """
        query = (
            self.db.query(TransportationPlanItem, TransportationPlan)
            .join(
                TransportationPlan,
                TransportationPlan.id == TransportationPlanItem.plan_id,
            )
            .filter(
                TransportationPlan.tenant_id == tenant_id,
                TransportationPlanItem.carrier_id.isnot(None),
                TransportationPlanItem.estimated_cost.isnot(None),
            )
        )

        if only_completed:
            query = query.filter(
                TransportationPlanItem.status == PlanItemStatus.COMPLETED,
            )
        else:
            query = query.filter(
                TransportationPlanItem.status.in_([
                    PlanItemStatus.CONFIRMED,
                    PlanItemStatus.IN_EXECUTION,
                    PlanItemStatus.COMPLETED,
                ]),
            )

        if period_start_min is not None:
            query = query.filter(
                TransportationPlan.plan_start_date >= period_start_min,
            )
        if period_start_max is not None:
            query = query.filter(
                TransportationPlan.plan_start_date <= period_start_max,
            )

        for item, plan in query.yield_per(500):
            yield self._build_example(item, plan)

    def _build_example(
        self, item: TransportationPlanItem, plan: TransportationPlan,
    ) -> MovementPlannerTrainingExample:
        carrier_metadata = (
            self._carrier_facts(item.carrier_id) if item.carrier_id else {}
        )
        rate_card_metadata = (
            self._rate_card_facts(item.rate_id) if item.rate_id else {}
        )

        observed_cost = self._observed_cost_for_item(item)
        observed_on_time = self._observed_on_time_for_item(item)

        return MovementPlannerTrainingExample(
            tenant_id=item.tenant_id,
            plan_id=item.plan_id,
            item_id=item.id,
            lane_id=item.lane_id or 0,
            period_start=plan.plan_start_date,
            period_days=plan.planning_horizon_days or 7,
            mode=item.mode,
            equipment_type=item.equipment_type,
            distance_miles=(
                float(item.distance_miles) if item.distance_miles else None
            ),
            action_carrier_id=int(item.carrier_id),
            action_rate_id=item.rate_id,
            action_estimated_cost=(
                float(item.estimated_cost) if item.estimated_cost else None
            ),
            observed_total_cost=observed_cost,
            observed_on_time=observed_on_time,
            carrier_metadata=carrier_metadata,
            rate_card_metadata=rate_card_metadata,
        )

    def _carrier_facts(self, carrier_id: int) -> Dict[str, Any]:
        if carrier_id in self._carrier_cache:
            return self._carrier_cache[carrier_id]
        try:
            from azirella_data_model.settlement import Carrier
        except ImportError:
            self._carrier_cache[carrier_id] = {}
            return {}

        carrier = self.db.query(Carrier).filter_by(id=carrier_id).first()
        if carrier is None:
            self._carrier_cache[carrier_id] = {}
            return {}
        facts = {
            "scac": carrier.scac,
            "carrier_type": carrier.carrier_type,
            "status": carrier.status,
        }
        self._carrier_cache[carrier_id] = facts
        return facts

    def _rate_card_facts(self, rate_id: int) -> Dict[str, Any]:
        if rate_id in self._rate_card_cache:
            return self._rate_card_cache[rate_id]
        try:
            from azirella_data_model.settlement import RateCard
        except ImportError:
            self._rate_card_cache[rate_id] = {}
            return {}

        card = self.db.query(RateCard).filter_by(id=rate_id).first()
        if card is None:
            self._rate_card_cache[rate_id] = {}
            return {}
        facts = {
            "rate_basis": card.rate_basis,
            "base_rate": float(card.base_rate),
            "lane_filter": card.lane_filter,
            "currency": card.currency,
            "effective_from": card.effective_from,
            "effective_to": card.effective_to,
        }
        self._rate_card_cache[rate_id] = facts
        return facts

    def _observed_cost_for_item(
        self, item: TransportationPlanItem,
    ) -> Optional[float]:
        """Look up the observed ``FreightCharge.total_amount`` for an
        item, when present. Phase 3.1 simplification: the join key is
        a TBD `plan_item_id` column on FreightCharge (not yet on the
        schema). For now, return None — Phase 3 follow-on will wire
        the join once the schema lands."""
        # TODO Phase 3 follow-on: add plan_item_id FK on FreightCharge
        # (or use a derived join via load_id when the load actually
        # ships). For Phase 3.1 the action_estimated_cost is the only
        # cost label available.
        return None

    def _observed_on_time_for_item(
        self, item: TransportationPlanItem,
    ) -> Optional[bool]:
        """Look up actual delivery date vs planned. Phase 3.1
        simplification: actual delivery is on the ``Load`` table when
        the item ships; we'd join via ``item.load_id`` when present.
        Without that wiring, return None."""
        # TODO Phase 3 follow-on: join via load_id → actual_delivery_date.
        return None


__all__ = [
    "MovementPlannerTrainingDataExtractor",
    "MovementPlannerTrainingExample",
]
