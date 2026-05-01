"""Shipment generator — exogenous TransferOrderEnvelope source for the twin.

Per Autonomy-Core/docs/architecture/TWIN_AND_ENVELOPES.md §6, every
envelope has three implementations stacked behind it. The lane-flow
simulator never knows which is registered; it just consumes whatever
the registered ``ShipmentGenerator`` emits.

Phase 1 (this module): parametric stochastic stub. Lives in TMS.
    Always available; broad coverage; no upstream dependency.
Phase 2 (PR-6): same stub, parameters fitted to the tenant's own
    ``TransferOrderLineItem`` history.
Phase 3 (later, SCP-side): SCP's full inventory simulator produces
    the envelope. TMS code is unchanged — only the registered provider
    swaps.

The Phase-1 stub registered here is what ``Load Builder`` trains
against in PR-2. It emits line-item-grain shipments — Load Builder's
canonical input.

PR-1 (this commit): the public surface and a degenerate stub that
returns an empty envelope (zero rows). PR-2 fills in the parametric
distributions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from azirella_demand_planning_contract import Tier
from azirella_transfer_order_envelope_contract import (
    PhaseIndicator,
    TransferOrderEnvelope,
    TransferOrderRow,
)


PARAMETRIC_STUB_PRODUCER_SIGNATURE = "tms:to_arrival_stub:v0.1.0"
"""Signature carried in ``TransferOrderEnvelope.produced_by`` for the
Phase-1 stub. Bump the version suffix when the parametric distribution
changes meaningfully so consumers can invalidate caches."""


@runtime_checkable
class ShipmentGenerator(Protocol):
    """Protocol every Phase 1 / 2 / 3 implementation honours.

    The simulator depends only on this protocol, never on a concrete
    implementation. Phase swaps are runtime registration changes.
    """

    def generate_envelope(
        self,
        *,
        tenant_id: int,
        config_id: int,
        tier: Tier,
        produced_at: datetime | None = None,
    ) -> TransferOrderEnvelope:
        """Emit one envelope for the given (tenant, config, tier) triple.

        Determinism: implementations must be deterministic given a fixed
        seed (passed via constructor or set_seed). The simulator pins
        the seed per scenario so rollouts are reproducible.
        """
        ...


class Phase1ShipmentGenerator:
    """Parametric stub. PR-1 returns an empty envelope; PR-2 implements
    the parametric distribution (lane / mode mix, weight + volume,
    weekly cadence, seasonal modulation via Core's SeasonalEnvelope).

    Constructor takes the candidate lanes / sites / products the stub
    will sample from. PR-1 stores them but does not use them; PR-2
    drives sampling off these lists.
    """

    def __init__(
        self,
        *,
        candidate_lanes: list[tuple[str, str]] | None = None,
        candidate_products: list[str] | None = None,
        candidate_units: list[str] | None = None,
        seed: int = 42,
    ):
        self.candidate_lanes = candidate_lanes or []
        self.candidate_products = candidate_products or []
        self.candidate_units = candidate_units or ["each"]
        self.seed = seed

    def generate_envelope(
        self,
        *,
        tenant_id: int,
        config_id: int,
        tier: Tier,
        produced_at: datetime | None = None,
    ) -> TransferOrderEnvelope:
        rows: list[TransferOrderRow] = []  # PR-2 populates.
        return TransferOrderEnvelope(
            tenant_id=tenant_id,
            config_id=config_id,
            tier=tier,
            rows=rows,
            phase_indicator=PhaseIndicator.PARAMETRIC_STUB,
            upstream_supply_plan_signature=None,
            produced_at=produced_at or datetime.now(timezone.utc),
            produced_by=PARAMETRIC_STUB_PRODUCER_SIGNATURE,
        )


__all__ = [
    "PARAMETRIC_STUB_PRODUCER_SIGNATURE",
    "Phase1ShipmentGenerator",
    "ShipmentGenerator",
]
