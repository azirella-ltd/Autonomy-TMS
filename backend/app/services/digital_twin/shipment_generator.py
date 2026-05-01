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
against in PR-3. It emits line-item-grain envelope rows — the
simulator samples concrete shipments from those rows and forwards them
to Load Builder.

Parametric design (PR-2):

- Channels are the cartesian of ``candidate_lanes × candidate_products``.
  Per-channel base mean line-item quantity comes from ``base_volumes``
  (or a per-tier default when not given).
- The horizon is ``horizon_buckets`` × the tier-implied bucket size
  (STRATEGIC=monthly, TACTICAL=weekly, EXECUTION=daily).
- Seasonal modulation: when a ``SeasonalEnvelope`` is registered for a
  lane key (``"lane:<origin>->{<dest>}"``), the channel's P10/P50/P90
  are scaled by the envelope's normalised ``(p_low, p_mid, p_high) /
  mean(p_mid)`` at the bucket date. When no envelope is registered, a
  flat triangular spread is used (``envelope_spread``).
- Output is deterministic given the constructor's ``seed`` and the
  envelope inputs — the per-channel base-volume jitter is seeded so
  two runs with identical inputs produce identical envelopes.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import random
from typing import Mapping, Protocol, runtime_checkable

from azirella_data_model.stochastic.seasonal import SeasonalEnvelope
from azirella_demand_planning_contract import Tier
from azirella_transfer_order_envelope_contract import (
    PhaseIndicator,
    TransferOrderEnvelope,
    TransferOrderRow,
)


PARAMETRIC_STUB_PRODUCER_SIGNATURE = "tms:to_arrival_stub:v0.2.0"
"""Signature carried in ``TransferOrderEnvelope.produced_by`` for the
Phase-1 stub. v0.2.0 = parametric distribution + seasonal envelope
adoption (PR-2). Bump the version suffix when the parametric
distribution changes meaningfully so consumers can invalidate caches."""


# ── Tier → bucket size ────────────────────────────────────────────────


_BUCKET_DAYS: dict[Tier, int] = {
    Tier.STRATEGIC: 30,   # monthly
    Tier.TACTICAL: 7,     # weekly
    Tier.EXECUTION: 1,    # daily
}


def _bucket_days(tier: Tier) -> int:
    try:
        return _BUCKET_DAYS[tier]
    except KeyError as exc:
        raise ValueError(f"Unknown tier {tier!r}") from exc


# ── Lane key (matches series_key convention used by SCP) ──────────────


def lane_series_key(origin_site_id: str, destination_site_id: str) -> str:
    """Canonical SeasonalEnvelope ``series_key`` for a TMS lane.

    Format ``"lane:<origin>-><dest>"`` — mirrors SCP's
    ``"site:<id>|product:<id>"`` convention so the same Phase-B fit
    pipeline can persist both kinds.
    """
    return f"lane:{origin_site_id}->{destination_site_id}"


# ── Protocol ─────────────────────────────────────────────────────────


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
        anchor_date: date | None = None,
        horizon_buckets: int | None = None,
    ) -> TransferOrderEnvelope:
        """Emit one envelope for the given (tenant, config, tier) triple.

        Determinism: implementations must be deterministic given a fixed
        seed (set via constructor) and a fixed ``anchor_date``. The
        simulator pins the seed per scenario and the anchor date from
        ``Scenario.rollout_start_date`` so rollouts are reproducible.
        """
        ...


# ── Phase-1 parametric stub ──────────────────────────────────────────


class Phase1ShipmentGenerator:
    """Parametric Phase-1 stub.

    Walks every ``(origin, destination, product)`` channel and every
    bucket in the horizon, emitting one ``TransferOrderRow`` per cell
    with seasonally-modulated P10/P50/P90 line-item quantity.

    Args:
        candidate_lanes: list of ``(origin_site_id, destination_site_id)``
            tuples — the lanes the simulator may dispatch on.
        candidate_products: canonical AWS SC ``product.id`` values.
        candidate_units: canonical UOM strings (e.g. ``each``, ``case``).
            One unit per channel is chosen deterministically from this
            list. PR-3 will read product master to resolve unit per
            product; PR-2 keeps it parametric.
        base_volumes: optional ``(origin, dest, product) → mean line-item
            qty per bucket``. When absent, every channel uses
            ``default_base_volume``.
        default_base_volume: fallback mean qty when ``base_volumes`` has
            no entry for a channel.
        seasonal_envelopes: optional ``lane_series_key → SeasonalEnvelope``.
            When registered, the envelope's per-bucket
            ``(p_low, p_mid, p_high) / mean(p_mid)`` ratio modulates the
            channel's P10/P50/P90.
        envelope_spread: ``(low, high)`` multiplicative spread used when
            no SeasonalEnvelope is registered for the lane. P10 = base ×
            low; P90 = base × high; P50 = base.
        seed: deterministic seed for the per-channel jitter component.
        product_unit_overrides: optional ``product → unit`` map. When
            present, takes priority over the deterministic
            ``candidate_units`` rotation.
    """

    DEFAULT_DEFAULT_BASE_VOLUME = 10.0
    DEFAULT_HORIZON_BUCKETS = 12
    DEFAULT_ENVELOPE_SPREAD: tuple[float, float] = (0.7, 1.3)

    def __init__(
        self,
        *,
        candidate_lanes: list[tuple[str, str]] | None = None,
        candidate_products: list[str] | None = None,
        candidate_units: list[str] | None = None,
        base_volumes: Mapping[tuple[str, str, str], float] | None = None,
        default_base_volume: float = DEFAULT_DEFAULT_BASE_VOLUME,
        seasonal_envelopes: Mapping[str, SeasonalEnvelope] | None = None,
        envelope_spread: tuple[float, float] = DEFAULT_ENVELOPE_SPREAD,
        seed: int = 42,
        product_unit_overrides: Mapping[str, str] | None = None,
    ):
        self.candidate_lanes = list(candidate_lanes or [])
        self.candidate_products = list(candidate_products or [])
        self.candidate_units = list(candidate_units or ["each"])
        self.base_volumes = dict(base_volumes or {})
        self.default_base_volume = float(default_base_volume)
        self.seasonal_envelopes = dict(seasonal_envelopes or {})
        low, high = envelope_spread
        if not (0.0 < low <= 1.0 <= high):
            raise ValueError(
                f"envelope_spread must satisfy 0 < low <= 1 <= high; got {envelope_spread!r}"
            )
        self.envelope_spread = (float(low), float(high))
        self.seed = int(seed)
        self.product_unit_overrides = dict(product_unit_overrides or {})

    # ------------------------------------------------------------------

    def generate_envelope(
        self,
        *,
        tenant_id: int,
        config_id: int,
        tier: Tier,
        produced_at: datetime | None = None,
        anchor_date: date | None = None,
        horizon_buckets: int | None = None,
    ) -> TransferOrderEnvelope:
        bucket_size = _bucket_days(tier)
        horizon = int(
            horizon_buckets if horizon_buckets is not None else self.DEFAULT_HORIZON_BUCKETS
        )
        if horizon < 1:
            raise ValueError(f"horizon_buckets must be >= 1; got {horizon}")
        anchor = anchor_date or date.today()

        rows: list[TransferOrderRow] = []
        for bucket_idx in range(horizon):
            bucket_start = anchor + timedelta(days=bucket_idx * bucket_size)
            for origin_id, destination_id in self.candidate_lanes:
                for product_id in self.candidate_products:
                    rows.append(
                        self._row_for_cell(
                            origin_id=origin_id,
                            destination_id=destination_id,
                            product_id=product_id,
                            bucket_start=bucket_start,
                            tier=tier,
                            config_id=config_id,
                        )
                    )

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

    # ------------------------------------------------------------------
    # Per-cell row construction
    # ------------------------------------------------------------------

    def _row_for_cell(
        self,
        *,
        origin_id: str,
        destination_id: str,
        product_id: str,
        bucket_start: date,
        tier: Tier,
        config_id: int,
    ) -> TransferOrderRow:
        base = float(self.base_volumes.get(
            (origin_id, destination_id, product_id),
            self.default_base_volume,
        ))
        # Deterministic per-cell jitter so different channels look
        # distinct but the same channel is reproducible across runs.
        jitter = self._jitter(
            config_id=config_id,
            origin_id=origin_id,
            destination_id=destination_id,
            product_id=product_id,
        )
        adjusted_base = max(0.0, base * jitter)

        lane_key = lane_series_key(origin_id, destination_id)
        envelope = self.seasonal_envelopes.get(lane_key)
        if envelope is not None:
            p10, p50, p90 = self._apply_envelope(envelope, adjusted_base, bucket_start)
        else:
            spread_low, spread_high = self.envelope_spread
            p50 = adjusted_base
            p10 = adjusted_base * spread_low
            p90 = adjusted_base * spread_high

        # Floor at 0 — line-item quantity can't be negative.
        p10 = max(0.0, p10)
        p50 = max(p10, p50)
        p90 = max(p50, p90)

        unit = self._unit_for_product(product_id)
        return TransferOrderRow(
            bucket_start=bucket_start,
            origin_site_id=str(origin_id),
            destination_site_id=str(destination_id),
            product_id=str(product_id),
            transportation_lane_id=None,
            p10=p10,
            p50=p50,
            p90=p90,
            unit=unit,
        )

    def _apply_envelope(
        self,
        envelope: SeasonalEnvelope,
        base: float,
        bucket_start: date,
    ) -> tuple[float, float, float]:
        """Scale ``base`` by the envelope's normalised shape at ``bucket_start``.

        Normalisation by ``mean(p_mid)`` means a flat envelope (constant
        ``p_mid``) collapses to ``(base × p_low/p_mid, base, base ×
        p_high/p_mid)`` — i.e. the envelope contributes only its spread,
        not its absolute level. The channel's ``base`` controls level.
        """
        p_lo, p_mid, p_hi = envelope.envelope_at(bucket_start)
        mean_mid = sum(envelope.p_mid) / max(1, len(envelope.p_mid))
        if mean_mid <= 0.0:
            # Degenerate envelope — fall back to flat spread.
            spread_low, spread_high = self.envelope_spread
            return base * spread_low, base, base * spread_high
        return (
            base * p_lo / mean_mid,
            base * p_mid / mean_mid,
            base * p_hi / mean_mid,
        )

    def _unit_for_product(self, product_id: str) -> str:
        if product_id in self.product_unit_overrides:
            return self.product_unit_overrides[product_id]
        if not self.candidate_units:
            return "each"
        # Deterministic, stable rotation by product_id hash.
        idx = abs(hash(product_id)) % len(self.candidate_units)
        return self.candidate_units[idx]

    def _jitter(
        self,
        *,
        config_id: int,
        origin_id: str,
        destination_id: str,
        product_id: str,
    ) -> float:
        """Per-cell multiplicative jitter in ~[0.85, 1.15].

        Seeded from ``(self.seed, config_id, channel)`` so distinct
        channels look distinct but every channel is reproducible across
        runs with identical inputs.
        """
        # ``random.Random`` accepts str / int / bytes; tuples raise TypeError.
        # A pipe-delimited string is deterministic across processes (not subject
        # to PYTHONHASHSEED randomisation).
        rng = random.Random(
            f"{self.seed}|{config_id}|{origin_id}|{destination_id}|{product_id}"
        )
        return 0.85 + rng.random() * 0.30


__all__ = [
    "PARAMETRIC_STUB_PRODUCER_SIGNATURE",
    "Phase1ShipmentGenerator",
    "ShipmentGenerator",
    "lane_series_key",
]
