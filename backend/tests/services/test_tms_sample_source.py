"""§3.57 Phase D — TmsSampleSource Protocol compliance + smoke.

Verifies:

1. Method-set conformance to Core's ``SampleSource`` Protocol
   (the module-level assertion already enforces this at import).
2. ``otif_samples`` query path is callable with a mock session
   and returns the expected sample shape.
3. ``throughput_samples`` / ``fulfilment_samples`` stub paths return
   empty lists.

Pure-Python — no real DB.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")


from app.services.tms_sample_source import TmsSampleSource  # noqa: E402

from azirella_data_model.master.capacity_observed import OtifSample  # noqa: E402


def test_tms_sample_source_methods_match_protocol() -> None:
    src = TmsSampleSource()
    for name in ("throughput_samples", "fulfilment_samples", "otif_samples"):
        assert callable(getattr(src, name, None)), (
            f"TmsSampleSource missing required method {name!r}"
        )


def test_throughput_samples_stub_returns_empty() -> None:
    src = TmsSampleSource()
    out = src.throughput_samples(
        MagicMock(), tenant_id=1, config_id=1, site_id=42,
        work_center_code="WC-1",
    )
    assert out == []


def test_fulfilment_samples_stub_returns_empty() -> None:
    src = TmsSampleSource()
    out = src.fulfilment_samples(
        MagicMock(), tenant_id=1, config_id=1, supplier_id="SUP-1",
    )
    assert out == []


def test_otif_samples_returns_otif_sample_list() -> None:
    """Query returns rows shaped like ``(ordered_quantity,
    shipped_quantity, promised_delivery_date, last_ship_date,
    first_ship_date)``; each row becomes an :class:`OtifSample`.
    Zero-ordered rows filter out; rows with missing dates filter out."""
    src = TmsSampleSource()
    # Row 1: full data, on-time
    row1 = MagicMock(
        ordered_quantity=100, shipped_quantity=100,
        promised_delivery_date=date(2026, 5, 10),
        last_ship_date=date(2026, 5, 9), first_ship_date=date(2026, 5, 9),
    )
    # Row 2: full data, late
    row2 = MagicMock(
        ordered_quantity=50, shipped_quantity=50,
        promised_delivery_date=date(2026, 5, 1),
        last_ship_date=date(2026, 5, 3), first_ship_date=date(2026, 5, 2),
    )
    # Row 3: zero ordered — filtered out
    row3 = MagicMock(
        ordered_quantity=0, shipped_quantity=0,
        promised_delivery_date=date(2026, 5, 10),
        last_ship_date=date(2026, 5, 9), first_ship_date=date(2026, 5, 9),
    )
    db = MagicMock()
    # ``q.filter().filter()...all()`` chain returns the rows.
    chain = db.query.return_value.filter.return_value
    # No product filter (no extra .filter() call in this test path).
    chain.all.return_value = [row1, row2, row3]

    samples = src.otif_samples(
        db, tenant_id=1, config_id=1, customer_id="42",
    )
    assert len(samples) == 2  # row3 filtered (zero ordered)
    assert all(isinstance(s, OtifSample) for s in samples)
    # row1 should be on-time (actual <= promised).
    assert samples[0].on_time is True
    # row2 should be late.
    assert samples[1].on_time is False


def test_otif_samples_returns_empty_when_customer_id_not_coercible() -> None:
    """A non-numeric customer_id has no site-ID mapping yet (§3.57
    Phase B customer-master mapper will land that). Returns empty."""
    src = TmsSampleSource()
    out = src.otif_samples(
        MagicMock(), tenant_id=1, config_id=1, customer_id="non-numeric-id",
    )
    assert out == []


def test_otif_samples_filters_missing_dates() -> None:
    """A row with promised_delivery_date set but BOTH last_ship_date
    AND first_ship_date null filters out — the conftest query
    already filters on last_ship_date being NOT NULL, but defensive
    in case the query relaxes."""
    src = TmsSampleSource()
    row = MagicMock(
        ordered_quantity=100, shipped_quantity=100,
        promised_delivery_date=date(2026, 5, 10),
        last_ship_date=None, first_ship_date=None,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [row]
    samples = src.otif_samples(
        db, tenant_id=1, config_id=1, customer_id="42",
    )
    assert samples == []
