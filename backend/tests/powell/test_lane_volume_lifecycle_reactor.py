"""Tests for LaneVolumeLifecycleReactor — §3.45.

Covers the volume-share-weighted aggregation of DP's per-product
lifecycle adjustments into per-lane overlays:

  - Single-product / single-lane → trivial pass-through scaled by share
  - Multi-product / single-lane → weighted sum
  - Coverage threshold → low-coverage overlays dropped
  - Mixed NPI + EOL on same lane → "MIXED" signal_type
  - Date coercion (string / date / datetime inputs)
  - apply_to_state contract — refuses to clobber non-lifecycle
    signals; sets lifecycle signals when overlay matches

Imports the reactor module directly via importlib to avoid triggering
``app.services.powell.__init__`` (which drags in DB-bound code that
expects production engine settings). The reactor itself only depends
on Core's ``azirella_data_model.transport_plan`` and SQLAlchemy — both
of which work fine against an in-memory SQLite for the substrate
checks here.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest


_REACTOR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "app", "services", "powell", "lane_volume_lifecycle_reactor.py",
)


def _load_reactor_module():
    """Load the reactor module directly without going through
    ``app.services.powell.__init__`` (which has heavy side-effects)."""
    spec = importlib.util.spec_from_file_location(
        "lane_volume_lifecycle_reactor_test_loaded", _REACTOR_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


reactor_module = _load_reactor_module()
LaneVolumeLifecycleReactor = reactor_module.LaneVolumeLifecycleReactor
LaneOverlay = reactor_module.LaneOverlay


@dataclass
class FakeLaneVolumeForecastState:
    """Minimal stand-in for LaneVolumeForecastState — only the fields
    the reactor's apply_to_state touches. Avoids importing the full
    TMS heuristic library into the test module."""

    lane_id: int = 0
    period_start: Optional[date] = None
    signal_type: str = ""
    signal_magnitude: float = 0.0
    signal_confidence: float = 0.0


class FakeProvider:
    """Inline stub for LifecycleAdjustmentProvider — returns the
    canned adjustment list verbatim."""

    def __init__(self, adjustments: List[Dict[str, Any]]) -> None:
        self.adjustments = adjustments

    def list_lifecycle_adjustments(
        self,
        *,
        tenant_id: int,
        since: Optional[datetime] = None,
        reason_codes: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        return list(self.adjustments)


@pytest.fixture
def db():
    """In-memory SQLite session with ProductLane + the tables it FKs.

    ProductLane has FKs to ``tenants``, ``transportation_lane``, and
    ``product``. We stub these as minimal id-only tables so
    ``create_all`` can build the schema; tests don't insert into the
    stub tables (the FKs aren't enforced in SQLite by default for our
    use case)."""
    from sqlalchemy import Column, Integer, String, Table, create_engine
    from sqlalchemy.orm import Session

    from azirella_data_model.base import Base
    from azirella_data_model.transport_plan import ProductLane  # noqa: F401

    # Stub FK targets if not already in the metadata.
    metadata = Base.metadata
    if "tenants" not in metadata.tables:
        Table("tenants", metadata, Column("id", Integer, primary_key=True))
    if "transportation_lane" not in metadata.tables:
        Table(
            "transportation_lane", metadata, Column("id", Integer, primary_key=True)
        )
    if "product" not in metadata.tables:
        Table("product", metadata, Column("id", String(50), primary_key=True))

    engine = create_engine("sqlite://")
    metadata.create_all(
        engine,
        tables=[
            metadata.tables["tenants"],
            metadata.tables["transportation_lane"],
            metadata.tables["product"],
            ProductLane.__table__,
        ],
    )
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def _seed_product_lane(
    db,
    *,
    tenant_id: int,
    lane_id: int,
    product_id: str,
    period_start: date,
    period_end: date,
    volume_share: float,
    volume_units: float = 100.0,
    confidence: float = 1.0,
):
    from azirella_data_model.transport_plan import (
        ProductLane,
        ProductLaneSource,
    )
    db.add(
        ProductLane(
            tenant_id=tenant_id,
            lane_id=lane_id,
            product_id=product_id,
            period_start=period_start,
            period_end=period_end,
            volume_units=volume_units,
            volume_share=volume_share,
            source=ProductLaneSource.OBSERVED_HISTORY,
            confidence=confidence,
        )
    )
    db.flush()


# ---------------------------------------------------------------------------
# Single product / single lane — share-scaled pass-through
# ---------------------------------------------------------------------------


def test_single_product_single_lane_scales_by_share(db):
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    _seed_product_lane(
        db,
        tenant_id=42,
        lane_id=10,
        product_id="SKU-A",
        period_start=ps,
        period_end=pe,
        volume_share=0.30,
    )
    provider = FakeProvider([
        {
            "product_id": "SKU-A",
            "period_start": ps.isoformat(),
            "period_end": pe.isoformat(),
            "reason_code": "lifecycle_npi_introduction",
            "adjustment_value": 0.50,
        },
    ])
    reactor = LaneVolumeLifecycleReactor(provider=provider, coverage_threshold=0.10)
    overlays = reactor.compute_overlays(db, tenant_id=42)

    assert (10, ps) in overlays
    overlay = overlays[(10, ps)]
    assert overlay.signal_type == "NPI"
    assert overlay.signal_magnitude == pytest.approx(0.30 * 0.50)
    assert overlay.coverage_share == pytest.approx(0.30)
    assert overlay.contributing_products == ["SKU-A"]
    assert overlay.reason_codes == ["lifecycle_npi_introduction"]


# ---------------------------------------------------------------------------
# Multiple products on same lane — weighted sum
# ---------------------------------------------------------------------------


def test_multi_product_weighted_sum(db):
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    _seed_product_lane(db, tenant_id=42, lane_id=10, product_id="A",
                       period_start=ps, period_end=pe, volume_share=0.40)
    _seed_product_lane(db, tenant_id=42, lane_id=10, product_id="B",
                       period_start=ps, period_end=pe, volume_share=0.30)
    provider = FakeProvider([
        {
            "product_id": "A", "period_start": ps, "period_end": pe,
            "reason_code": "lifecycle_npi_introduction",
            "adjustment_value": 1.00,
        },
        {
            "product_id": "B", "period_start": ps, "period_end": pe,
            "reason_code": "lifecycle_npi_ramp",
            "adjustment_value": 0.20,
        },
    ])
    reactor = LaneVolumeLifecycleReactor(provider=provider)
    overlays = reactor.compute_overlays(db, tenant_id=42)

    overlay = overlays[(10, ps)]
    # 0.40 × 1.00 + 0.30 × 0.20 = 0.46
    assert overlay.signal_magnitude == pytest.approx(0.46)
    assert overlay.coverage_share == pytest.approx(0.70)
    assert set(overlay.contributing_products) == {"A", "B"}
    assert set(overlay.reason_codes) == {
        "lifecycle_npi_introduction", "lifecycle_npi_ramp",
    }
    assert overlay.signal_type == "NPI"


# ---------------------------------------------------------------------------
# Coverage threshold — low coverage drops the overlay
# ---------------------------------------------------------------------------


def test_low_coverage_overlay_dropped(db):
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    _seed_product_lane(db, tenant_id=42, lane_id=10, product_id="A",
                       period_start=ps, period_end=pe, volume_share=0.05)
    provider = FakeProvider([{
        "product_id": "A", "period_start": ps, "period_end": pe,
        "reason_code": "lifecycle_npi_introduction",
        "adjustment_value": 0.50,
    }])
    # Default threshold 0.10; share 0.05 → dropped.
    reactor = LaneVolumeLifecycleReactor(provider=provider)
    overlays = reactor.compute_overlays(db, tenant_id=42)
    assert overlays == {}


def test_coverage_threshold_can_be_relaxed(db):
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    _seed_product_lane(db, tenant_id=42, lane_id=10, product_id="A",
                       period_start=ps, period_end=pe, volume_share=0.05)
    provider = FakeProvider([{
        "product_id": "A", "period_start": ps, "period_end": pe,
        "reason_code": "lifecycle_npi_introduction",
        "adjustment_value": 0.50,
    }])
    reactor = LaneVolumeLifecycleReactor(provider=provider, coverage_threshold=0.0)
    overlays = reactor.compute_overlays(db, tenant_id=42)
    assert (10, ps) in overlays


# ---------------------------------------------------------------------------
# Mixed NPI + EOL on same lane → MIXED signal type
# ---------------------------------------------------------------------------


def test_mixed_npi_and_eol_on_same_lane(db):
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    _seed_product_lane(db, tenant_id=42, lane_id=10, product_id="NEW",
                       period_start=ps, period_end=pe, volume_share=0.30)
    _seed_product_lane(db, tenant_id=42, lane_id=10, product_id="OLD",
                       period_start=ps, period_end=pe, volume_share=0.40)
    provider = FakeProvider([
        {"product_id": "NEW", "period_start": ps, "period_end": pe,
         "reason_code": "lifecycle_npi_introduction",
         "adjustment_value": 0.80},
        {"product_id": "OLD", "period_start": ps, "period_end": pe,
         "reason_code": "lifecycle_eol_phaseout",
         "adjustment_value": -0.50},
    ])
    reactor = LaneVolumeLifecycleReactor(provider=provider)
    overlays = reactor.compute_overlays(db, tenant_id=42)
    overlay = overlays[(10, ps)]
    assert overlay.signal_type == "MIXED"
    # 0.30 × 0.80 + 0.40 × −0.50 = 0.24 − 0.20 = 0.04
    assert overlay.signal_magnitude == pytest.approx(0.04)


# ---------------------------------------------------------------------------
# Date coercion — string / date / datetime inputs
# ---------------------------------------------------------------------------


def test_date_string_input_coerced(db):
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    _seed_product_lane(db, tenant_id=42, lane_id=10, product_id="A",
                       period_start=ps, period_end=pe, volume_share=0.50)
    provider = FakeProvider([{
        "product_id": "A",
        "period_start": "2026-05-04",
        "period_end": "2026-05-11",
        "reason_code": "lifecycle_npi_introduction",
        "adjustment_value": 1.00,
    }])
    reactor = LaneVolumeLifecycleReactor(provider=provider)
    overlays = reactor.compute_overlays(db, tenant_id=42)
    assert (10, ps) in overlays


def test_datetime_input_coerced(db):
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    _seed_product_lane(db, tenant_id=42, lane_id=10, product_id="A",
                       period_start=ps, period_end=pe, volume_share=0.50)
    provider = FakeProvider([{
        "product_id": "A",
        "period_start": "2026-05-04T00:00:00Z",
        "period_end": "2026-05-11T00:00:00Z",
        "reason_code": "lifecycle_npi_introduction",
        "adjustment_value": 1.00,
    }])
    reactor = LaneVolumeLifecycleReactor(provider=provider)
    overlays = reactor.compute_overlays(db, tenant_id=42)
    assert (10, ps) in overlays


# ---------------------------------------------------------------------------
# Empty inputs / no-data fallthrough
# ---------------------------------------------------------------------------


def test_no_adjustments_returns_empty(db):
    reactor = LaneVolumeLifecycleReactor(provider=FakeProvider([]))
    assert reactor.compute_overlays(db, tenant_id=42) == {}


def test_no_product_lane_rows_returns_empty(db):
    ps, pe = date(2026, 5, 4), date(2026, 5, 11)
    provider = FakeProvider([{
        "product_id": "A", "period_start": ps, "period_end": pe,
        "reason_code": "lifecycle_npi_introduction",
        "adjustment_value": 0.50,
    }])
    reactor = LaneVolumeLifecycleReactor(provider=provider)
    overlays = reactor.compute_overlays(db, tenant_id=42)
    assert overlays == {}


def test_invalid_period_window_skipped(db):
    """Rows with malformed periods (start >= end, missing dates) are
    skipped silently rather than raising."""
    provider = FakeProvider([
        {"product_id": "A", "period_start": None, "period_end": None,
         "reason_code": "lifecycle_npi_introduction", "adjustment_value": 0.5},
        {"product_id": "B", "period_start": "2026-05-11",
         "period_end": "2026-05-04",  # start > end
         "reason_code": "lifecycle_npi_introduction", "adjustment_value": 0.5},
    ])
    reactor = LaneVolumeLifecycleReactor(provider=provider)
    overlays = reactor.compute_overlays(db, tenant_id=42)
    assert overlays == {}


# ---------------------------------------------------------------------------
# apply_to_state — won't clobber non-lifecycle signals
# ---------------------------------------------------------------------------


def test_apply_to_state_sets_lifecycle_signal():
    ps = date(2026, 5, 4)
    state = FakeLaneVolumeForecastState(lane_id=10, period_start=ps)
    overlays = {
        (10, ps): LaneOverlay(
            lane_id=10, period_start=ps, period_end=date(2026, 5, 11),
            signal_type="NPI", signal_magnitude=0.15, signal_confidence=0.8,
        ),
    }
    reactor = LaneVolumeLifecycleReactor(provider=FakeProvider([]))
    reactor.apply_to_state(state, overlays)
    assert state.signal_type == "NPI"
    assert state.signal_magnitude == 0.15
    assert state.signal_confidence == 0.8


def test_apply_to_state_no_overlay_leaves_state_alone():
    ps = date(2026, 5, 4)
    state = FakeLaneVolumeForecastState(
        lane_id=10, period_start=ps,
        signal_type="PROMO_LIFT", signal_magnitude=0.20, signal_confidence=0.9,
    )
    reactor = LaneVolumeLifecycleReactor(provider=FakeProvider([]))
    reactor.apply_to_state(state, overlays={})
    # Pre-existing PROMO_LIFT untouched.
    assert state.signal_type == "PROMO_LIFT"
    assert state.signal_magnitude == 0.20


def test_apply_to_state_refuses_to_clobber_non_lifecycle_signal():
    ps = date(2026, 5, 4)
    state = FakeLaneVolumeForecastState(
        lane_id=10, period_start=ps,
        signal_type="PROMO_LIFT",
        signal_magnitude=0.20, signal_confidence=0.9,
    )
    overlays = {
        (10, ps): LaneOverlay(
            lane_id=10, period_start=ps, period_end=date(2026, 5, 11),
            signal_type="NPI", signal_magnitude=0.15, signal_confidence=0.8,
        ),
    }
    reactor = LaneVolumeLifecycleReactor(provider=FakeProvider([]))
    reactor.apply_to_state(state, overlays)
    # Lifecycle signal must NOT clobber the upstream PROMO_LIFT.
    assert state.signal_type == "PROMO_LIFT"
    assert state.signal_magnitude == 0.20


# ---------------------------------------------------------------------------
# Reactor construction — coverage_threshold validation
# ---------------------------------------------------------------------------


def test_invalid_coverage_threshold_raises():
    with pytest.raises(ValueError, match="coverage_threshold"):
        LaneVolumeLifecycleReactor(provider=FakeProvider([]), coverage_threshold=-0.1)
    with pytest.raises(ValueError, match="coverage_threshold"):
        LaneVolumeLifecycleReactor(provider=FakeProvider([]), coverage_threshold=1.5)
