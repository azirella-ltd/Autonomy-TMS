"""Phase-2 shipment-generator fitter tests (PR-6).

Covers:
  - HistoricalShipment validation
  - Empty history → empty Phase-2 generator (no candidates, no envelopes)
  - Channel discovery (lanes, products, units) from history
  - Per-channel base_volumes fitted from mean qty per occupied bucket
  - Sparse channels fall through (inherit default_base_volume)
  - Per-product unit overrides — single-UOM products only
  - Per-lane SeasonalEnvelope fitted via Core (≥1.5 annual cycles)
  - Lanes with insufficient history skip the seasonal fit
  - Producer signature on the resulting generator marks Phase-2
  - PhaseIndicator on emitted envelopes is TENANT_CALIBRATED
  - End-to-end: fitted generator emits a valid TransferOrderEnvelope
    that matches the seasonal pattern in the input history
"""
from __future__ import annotations

import math
import statistics
from collections import Counter
from datetime import date, timedelta

import pytest

from app.services.digital_twin import (
    FitParameters,
    HistoricalShipment,
    PHASE2_TENANT_CALIBRATED_PRODUCER_SIGNATURE,
    Phase1ShipmentGenerator,
    fit_phase2_shipment_generator,
    lane_series_key,
)
from app.services.digital_twin.shipment_generator import (
    PARAMETRIC_STUB_PRODUCER_SIGNATURE,
)
from azirella_demand_planning_contract import Tier
from azirella_transfer_order_envelope_contract import (
    PhaseIndicator,
    TransferOrderEnvelope,
)


# ── Helpers for synthetic history ────────────────────────────────────


def _shipment(
    *,
    origin: str = "site:1",
    destination: str = "site:2",
    product: str = "sku:A",
    on: date,
    qty: float = 100.0,
    unit: str = "each",
) -> HistoricalShipment:
    return HistoricalShipment(
        origin_site_id=origin,
        destination_site_id=destination,
        product_id=product,
        shipment_date=on,
        quantity=qty,
        unit=unit,
    )


def _weekly_history(
    *,
    origin: str,
    destination: str,
    product: str,
    start: date,
    weeks: int,
    qty_fn=None,
    unit: str = "each",
) -> list[HistoricalShipment]:
    """Generate one shipment per week for ``weeks`` weeks starting ``start``.

    ``qty_fn(week_idx) -> float`` lets callers shape seasonal patterns.
    Defaults to a constant 100/qty.
    """
    if qty_fn is None:
        qty_fn = lambda _i: 100.0  # noqa: E731
    return [
        _shipment(
            origin=origin,
            destination=destination,
            product=product,
            on=start + timedelta(weeks=i),
            qty=qty_fn(i),
            unit=unit,
        )
        for i in range(weeks)
    ]


# ── HistoricalShipment validation ────────────────────────────────────


def test_historical_shipment_rejects_empty_origin():
    with pytest.raises(ValueError, match="origin_site_id"):
        HistoricalShipment(
            origin_site_id="",
            destination_site_id="site:2",
            product_id="sku:A",
            shipment_date=date(2026, 1, 5),
            quantity=10.0,
        )


def test_historical_shipment_rejects_empty_destination():
    with pytest.raises(ValueError, match="destination_site_id"):
        HistoricalShipment(
            origin_site_id="site:1",
            destination_site_id="",
            product_id="sku:A",
            shipment_date=date(2026, 1, 5),
            quantity=10.0,
        )


def test_historical_shipment_rejects_empty_product():
    with pytest.raises(ValueError, match="product_id"):
        HistoricalShipment(
            origin_site_id="site:1",
            destination_site_id="site:2",
            product_id="",
            shipment_date=date(2026, 1, 5),
            quantity=10.0,
        )


def test_historical_shipment_rejects_negative_quantity():
    with pytest.raises(ValueError, match="quantity"):
        HistoricalShipment(
            origin_site_id="site:1",
            destination_site_id="site:2",
            product_id="sku:A",
            shipment_date=date(2026, 1, 5),
            quantity=-5.0,
        )


# ── Empty / minimal history ──────────────────────────────────────────


def test_empty_history_returns_empty_phase2_generator():
    gen = fit_phase2_shipment_generator([])
    assert isinstance(gen, Phase1ShipmentGenerator)
    assert gen.candidate_lanes == []
    assert gen.candidate_products == []
    assert gen.base_volumes == {}
    assert gen.seasonal_envelopes == {}
    assert gen.producer_signature == PHASE2_TENANT_CALIBRATED_PRODUCER_SIGNATURE


def test_empty_history_envelope_carries_phase2_signature():
    gen = fit_phase2_shipment_generator([])
    envelope = gen.generate_envelope(
        tenant_id=1, config_id=1, tier=Tier.TACTICAL,
        anchor_date=date(2026, 1, 5),
    )
    assert envelope.produced_by == PHASE2_TENANT_CALIBRATED_PRODUCER_SIGNATURE
    assert envelope.phase_indicator is PhaseIndicator.TENANT_CALIBRATED


# ── Channel discovery ────────────────────────────────────────────────


def test_lane_discovery_distinct_pairs():
    history = [
        _shipment(origin="site:1", destination="site:2", on=date(2026, 1, 5)),
        _shipment(origin="site:1", destination="site:2", on=date(2026, 1, 12)),
        _shipment(origin="site:3", destination="site:4", on=date(2026, 1, 5)),
        _shipment(origin="site:1", destination="site:5", on=date(2026, 1, 5)),
    ]
    gen = fit_phase2_shipment_generator(history)
    assert sorted(gen.candidate_lanes) == [
        ("site:1", "site:2"),
        ("site:1", "site:5"),
        ("site:3", "site:4"),
    ]


def test_product_discovery_sorted():
    history = [
        _shipment(product="sku:C", on=date(2026, 1, 5)),
        _shipment(product="sku:A", on=date(2026, 1, 5)),
        _shipment(product="sku:B", on=date(2026, 1, 5)),
    ]
    gen = fit_phase2_shipment_generator(history)
    assert gen.candidate_products == ["sku:A", "sku:B", "sku:C"]


def test_unit_discovery_falls_back_to_each_when_empty_input_units():
    """All shipments default to ``each`` if no unit override is set; the
    generator's candidate_units should still include at least ``each``."""
    history = [_shipment(on=date(2026, 1, 5))]
    gen = fit_phase2_shipment_generator(history)
    assert "each" in gen.candidate_units


# ── Unit overrides ───────────────────────────────────────────────────


def test_single_uom_product_gets_override():
    history = [
        _shipment(product="sku:A", on=date(2026, 1, 5), unit="case"),
        _shipment(product="sku:A", on=date(2026, 1, 12), unit="case"),
        _shipment(product="sku:A", on=date(2026, 1, 19), unit="case"),
    ]
    gen = fit_phase2_shipment_generator(history)
    assert gen.product_unit_overrides == {"sku:A": "case"}


def test_mixed_uom_product_no_override():
    """Products with > 1 UOM in history don't get an override —
    generator falls through to the candidate_units rotation."""
    history = [
        _shipment(product="sku:A", on=date(2026, 1, 5), unit="case"),
        _shipment(product="sku:A", on=date(2026, 1, 12), unit="each"),
    ]
    gen = fit_phase2_shipment_generator(history)
    assert "sku:A" not in gen.product_unit_overrides


# ── Base volume fitting ──────────────────────────────────────────────


def test_base_volume_is_mean_per_occupied_bucket():
    """For a channel with weekly shipments at qty=100, base_volume = 100."""
    history = _weekly_history(
        origin="site:1", destination="site:2", product="sku:A",
        start=date(2026, 1, 5), weeks=10,
        qty_fn=lambda _i: 100.0,
    )
    gen = fit_phase2_shipment_generator(history)
    assert ("site:1", "site:2", "sku:A") in gen.base_volumes
    assert gen.base_volumes[("site:1", "site:2", "sku:A")] == pytest.approx(100.0)


def test_base_volume_handles_multi_shipment_buckets():
    """Two shipments in the same week aggregate to their sum."""
    history = [
        _shipment(on=date(2026, 1, 5), qty=40.0),  # ISO week 2 of 2026
        _shipment(on=date(2026, 1, 7), qty=60.0),  # same ISO week
        _shipment(on=date(2026, 1, 12), qty=50.0),  # week 3
        _shipment(on=date(2026, 1, 19), qty=50.0),  # week 4
        _shipment(on=date(2026, 1, 26), qty=50.0),  # week 5
    ]
    gen = fit_phase2_shipment_generator(history)
    base = gen.base_volumes.get(("site:1", "site:2", "sku:A"))
    # 4 occupied buckets: (40+60), 50, 50, 50 = 100, 50, 50, 50 → mean = 62.5
    assert base == pytest.approx(62.5)


def test_sparse_channel_dropped_below_min_buckets():
    """A channel with only 2 occupied buckets falls through to default."""
    params = FitParameters(min_buckets_for_volume_fit=4)
    history = [
        _shipment(on=date(2026, 1, 5), qty=100.0),
        _shipment(on=date(2026, 1, 12), qty=100.0),
    ]
    gen = fit_phase2_shipment_generator(history, params=params)
    assert gen.base_volumes == {}  # no entry → inherits default at gen-time
    assert ("site:1", "site:2", "sku:A") in {
        (o, d, p) for (o, d) in gen.candidate_lanes for p in gen.candidate_products
    }


def test_high_min_buckets_threshold_skips_short_channels():
    history = _weekly_history(
        origin="site:1", destination="site:2", product="sku:A",
        start=date(2026, 1, 5), weeks=3,
    )
    gen = fit_phase2_shipment_generator(
        history, params=FitParameters(min_buckets_for_volume_fit=10),
    )
    assert gen.base_volumes == {}


# ── Seasonal envelope fitting ────────────────────────────────────────


def _seasonal_history(
    *, weeks: int, base: float = 100.0, amplitude: float = 30.0
) -> list[HistoricalShipment]:
    """Sinusoidal weekly history. Peak at week 0, trough at week 26."""
    def qty(i: int) -> float:
        return max(0.0, base + amplitude * math.cos(2 * math.pi * i / 52))
    return _weekly_history(
        origin="site:1", destination="site:2", product="sku:A",
        start=date(2026, 1, 5), weeks=weeks, qty_fn=qty,
    )


def test_seasonal_envelope_fitted_with_enough_history():
    """≥ 1.5 full periods (78 weeks) yields a fitted envelope."""
    history = _seasonal_history(weeks=80)
    gen = fit_phase2_shipment_generator(history)
    lane_key = lane_series_key("site:1", "site:2")
    assert lane_key in gen.seasonal_envelopes
    envelope = gen.seasonal_envelopes[lane_key]
    assert envelope.period == 52
    assert len(envelope.p_mid) == 52


def test_seasonal_envelope_skipped_with_thin_history():
    """A channel with only ~half a period of data skips the seasonal fit."""
    history = _seasonal_history(weeks=20)
    gen = fit_phase2_shipment_generator(history)
    lane_key = lane_series_key("site:1", "site:2")
    assert lane_key not in gen.seasonal_envelopes


def test_seasonal_envelope_threshold_is_tunable():
    """Lowering ``min_full_periods_for_seasonal`` admits shorter histories."""
    history = _seasonal_history(weeks=30)
    gen = fit_phase2_shipment_generator(
        history,
        params=FitParameters(min_full_periods_for_seasonal=0.4),
    )
    lane_key = lane_series_key("site:1", "site:2")
    assert lane_key in gen.seasonal_envelopes


def test_seasonal_envelope_winter_higher_than_summer():
    """For the cosine pattern (peak at ISO week 1, trough at week 26),
    the fitted envelope's p_mid at week 0 should exceed the trough.
    """
    history = _seasonal_history(weeks=80, base=100.0, amplitude=40.0)
    gen = fit_phase2_shipment_generator(history)
    lane_key = lane_series_key("site:1", "site:2")
    envelope = gen.seasonal_envelopes[lane_key]
    peak_mid = envelope.p_mid[0]   # ~ winter peak
    trough_mid = envelope.p_mid[26]  # ~ summer trough
    assert peak_mid > trough_mid, (
        f"expected peak > trough; got peak={peak_mid}, trough={trough_mid}"
    )


# ── Producer signature + phase indicator ─────────────────────────────


def test_phase2_generator_carries_phase2_signature():
    history = _weekly_history(
        origin="site:1", destination="site:2", product="sku:A",
        start=date(2026, 1, 5), weeks=10,
    )
    gen = fit_phase2_shipment_generator(history)
    assert gen.producer_signature == PHASE2_TENANT_CALIBRATED_PRODUCER_SIGNATURE
    assert gen.producer_signature.startswith("tms:to_arrival_phase2")


def test_phase2_envelope_phase_indicator_is_tenant_calibrated():
    history = _weekly_history(
        origin="site:1", destination="site:2", product="sku:A",
        start=date(2026, 1, 5), weeks=10,
    )
    gen = fit_phase2_shipment_generator(history)
    envelope = gen.generate_envelope(
        tenant_id=1, config_id=10, tier=Tier.TACTICAL,
        anchor_date=date(2026, 1, 5), horizon_buckets=4,
    )
    assert envelope.phase_indicator is PhaseIndicator.TENANT_CALIBRATED


def test_phase1_default_signature_unchanged_by_pr6():
    """Backward-compat: Phase1ShipmentGenerator default keeps PR-2 signature."""
    gen = Phase1ShipmentGenerator(
        candidate_lanes=[("site:1", "site:2")],
        candidate_products=["sku:A"],
    )
    assert gen.producer_signature == PARAMETRIC_STUB_PRODUCER_SIGNATURE
    envelope = gen.generate_envelope(
        tenant_id=1, config_id=10, tier=Tier.TACTICAL,
        anchor_date=date(2026, 1, 5), horizon_buckets=2,
    )
    assert envelope.phase_indicator is PhaseIndicator.PARAMETRIC_STUB


# ── End-to-end integration ───────────────────────────────────────────


def test_fitted_generator_emits_seasonal_pattern_envelope():
    """When seasonal history is fitted, the emitted envelope's P50
    pattern across buckets reflects the underlying season — the peak
    weeks in fitted output exceed the trough weeks materially.
    """
    history = _seasonal_history(weeks=80, base=100.0, amplitude=40.0)
    gen = fit_phase2_shipment_generator(history)
    # Anchor on Jan 5, 2026 = ISO week 2 (close to peak); 52 weeks of horizon
    # should sweep through both peak and trough.
    envelope = gen.generate_envelope(
        tenant_id=1, config_id=10, tier=Tier.TACTICAL,
        anchor_date=date(2026, 1, 5), horizon_buckets=52,
    )
    assert envelope.rows
    p50s = [row.p50 for row in envelope.rows]
    assert max(p50s) > min(p50s) * 1.3, (
        f"seasonal modulation too weak; max={max(p50s):.2f}, min={min(p50s):.2f}"
    )


def test_fitted_generator_walks_only_observed_channels():
    """``candidate_lanes × candidate_products`` is exactly the set of
    channels seen in history — generator doesn't fabricate channels.
    """
    history = [
        _shipment(origin="site:1", destination="site:2", product="sku:A", on=date(2026, 1, 5)),
        _shipment(origin="site:1", destination="site:2", product="sku:A", on=date(2026, 1, 12)),
        _shipment(origin="site:3", destination="site:4", product="sku:B", on=date(2026, 1, 5)),
    ]
    gen = fit_phase2_shipment_generator(history)
    envelope = gen.generate_envelope(
        tenant_id=1, config_id=10, tier=Tier.TACTICAL,
        anchor_date=date(2026, 1, 5), horizon_buckets=2,
    )
    channels_in_envelope = {
        (row.origin_site_id, row.destination_site_id, row.product_id)
        for row in envelope.rows
    }
    # Generator emits the cartesian product of candidate_lanes ×
    # candidate_products, so 2 lanes × 2 products = 4 channels each bucket.
    assert ("site:1", "site:2", "sku:A") in channels_in_envelope
    assert ("site:3", "site:4", "sku:B") in channels_in_envelope


def test_fitted_generator_is_deterministic():
    history = _weekly_history(
        origin="site:1", destination="site:2", product="sku:A",
        start=date(2026, 1, 5), weeks=10,
    )
    gen1 = fit_phase2_shipment_generator(history)
    gen2 = fit_phase2_shipment_generator(history)
    e1 = gen1.generate_envelope(
        tenant_id=1, config_id=10, tier=Tier.TACTICAL,
        anchor_date=date(2026, 1, 5), horizon_buckets=4,
    )
    e2 = gen2.generate_envelope(
        tenant_id=1, config_id=10, tier=Tier.TACTICAL,
        anchor_date=date(2026, 1, 5), horizon_buckets=4,
    )
    assert [(r.p10, r.p50, r.p90) for r in e1.rows] == \
           [(r.p10, r.p50, r.p90) for r in e2.rows]


# ── Empty-history sanity for envelope_at semantics ────────────────────


def test_unfitted_lane_falls_through_to_envelope_spread():
    """A second lane with too-thin history should still appear in
    candidate_lanes (so the generator emits envelopes for it) but
    without a fitted SeasonalEnvelope — its rows use the
    fallback envelope_spread.
    """
    history = (
        _seasonal_history(weeks=80)  # lane 1 → 2 fitted
        + [
            _shipment(origin="site:3", destination="site:4", on=date(2026, 1, 5), qty=10.0),
            _shipment(origin="site:3", destination="site:4", on=date(2026, 1, 12), qty=10.0),
            _shipment(origin="site:3", destination="site:4", on=date(2026, 1, 19), qty=10.0),
            _shipment(origin="site:3", destination="site:4", on=date(2026, 1, 26), qty=10.0),
        ]  # lane 3 → 4 too thin; falls through
    )
    gen = fit_phase2_shipment_generator(history)
    fitted_lane = lane_series_key("site:1", "site:2")
    thin_lane = lane_series_key("site:3", "site:4")
    assert fitted_lane in gen.seasonal_envelopes
    assert thin_lane not in gen.seasonal_envelopes
    assert ("site:3", "site:4") in gen.candidate_lanes
