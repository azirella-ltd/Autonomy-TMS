"""Tests for LiveExceptionService — §3.29 Group A Phase 2 pure-logic
coverage.

The DB-backed ``detect_exceptions`` path is exercised by integration
tests gated on ``TMS_RUN_INTEGRATION_TESTS=1`` (same env-gate pattern
as ProductLaneAggregator); this suite covers the classifier math /
AIIO-mode mapping / edge cases without a live DB.

Loaded via ``importlib`` to bypass the heavy
``app.services.powell.__init__`` side effects (the package
imports SQLAlchemy ORM modules at import time, which the lightweight
unit-test environment doesn't carry).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest


_LES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "app", "services", "powell", "live_exception_service.py",
)


def _load_live_exception_module():
    import types

    for parent in ("app", "app.services", "app.services.powell"):
        if parent not in sys.modules:
            pkg = types.ModuleType(parent)
            pkg.__path__ = []
            sys.modules[parent] = pkg

    spec = importlib.util.spec_from_file_location(
        "live_exception_service_test_loaded", _LES_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_les = _load_live_exception_module()
LiveExceptionService = _les.LiveExceptionService
ExceptionResult = _les.ExceptionResult
ExceptionType = _les.ExceptionType
AIIOMode = _les.AIIOMode
LATE_ARRIVAL_BAND_RISK_THRESHOLD_MIN = _les.LATE_ARRIVAL_BAND_RISK_THRESHOLD_MIN


def _now() -> datetime:
    return datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


class TestServiceConstruction:
    def test_default_init(self):
        svc = LiveExceptionService()
        assert svc.late_arrival_horizon_min == 8 * 60
        assert svc.dwell_breach_horizon_sec == 4 * 3600
        assert svc.automate_threshold == 0.30
        assert svc.inform_threshold == 0.65

    def test_custom_horizons(self):
        svc = LiveExceptionService(
            late_arrival_horizon_min=240,
            dwell_breach_horizon_sec=7200,
            automate_threshold=0.2,
            inform_threshold=0.5,
        )
        assert svc.late_arrival_horizon_min == 240
        assert svc.dwell_breach_horizon_sec == 7200
        assert svc.automate_threshold == 0.2
        assert svc.inform_threshold == 0.5

    def test_invalid_late_arrival_horizon(self):
        with pytest.raises(ValueError, match="late_arrival_horizon_min"):
            LiveExceptionService(late_arrival_horizon_min=0)
        with pytest.raises(ValueError, match="late_arrival_horizon_min"):
            LiveExceptionService(late_arrival_horizon_min=-1)

    def test_invalid_dwell_breach_horizon(self):
        with pytest.raises(ValueError, match="dwell_breach_horizon_sec"):
            LiveExceptionService(dwell_breach_horizon_sec=0)

    def test_invalid_threshold_ordering(self):
        with pytest.raises(ValueError, match="thresholds"):
            LiveExceptionService(automate_threshold=0.7, inform_threshold=0.5)
        with pytest.raises(ValueError, match="thresholds"):
            LiveExceptionService(automate_threshold=0.0)
        with pytest.raises(ValueError, match="thresholds"):
            LiveExceptionService(inform_threshold=1.5)


# ---------------------------------------------------------------------------
# classify_late_arrival — committed-late branch (P50 > promised)
# ---------------------------------------------------------------------------


class TestLateArrivalCommittedLate:
    def test_on_time_returns_none(self):
        svc = LiveExceptionService()
        promised = _now() + timedelta(hours=2)
        # P50 ≤ promised AND P10 ≥ promised → on-track, no exception
        result = svc.classify_late_arrival(
            eta_id=1, tracked_entity_id=10, tenant_id=100,
            promised_at=promised,
            predicted_p50_at=promised - timedelta(minutes=30),
            predicted_p10_at=promised - timedelta(minutes=60),
            predicted_p90_at=promised + timedelta(minutes=15),
        )
        assert result is None

    def test_one_hour_slip_low_urgency(self):
        svc = LiveExceptionService()
        promised = _now() + timedelta(hours=2)
        result = svc.classify_late_arrival(
            eta_id=2, tracked_entity_id=11, tenant_id=100,
            promised_at=promised,
            predicted_p50_at=promised + timedelta(minutes=60),
            predicted_p10_at=promised + timedelta(minutes=20),
            predicted_p90_at=promised + timedelta(minutes=120),
        )
        assert result is not None
        assert result.exception_type == ExceptionType.LATE_ARRIVAL_DETECTED
        # 60 min / 480 min horizon = 0.125
        assert result.urgency == pytest.approx(0.125, abs=0.01)
        assert result.aiio_mode == AIIOMode.AUTOMATE
        assert result.source_eta_id == 2
        assert result.tracked_entity_id == 11
        assert result.metadata["slip_minutes"] == pytest.approx(60.0)

    def test_four_hour_slip_inform_band(self):
        svc = LiveExceptionService()
        promised = _now() + timedelta(hours=2)
        result = svc.classify_late_arrival(
            eta_id=3, tracked_entity_id=12, tenant_id=100,
            promised_at=promised,
            predicted_p50_at=promised + timedelta(hours=4),
            predicted_p10_at=promised + timedelta(hours=2),
            predicted_p90_at=promised + timedelta(hours=6),
        )
        assert result is not None
        # 240 min / 480 min horizon = 0.5 → INFORM band [0.30, 0.65)
        assert result.urgency == pytest.approx(0.5, abs=0.01)
        assert result.aiio_mode == AIIOMode.INFORM

    def test_eight_hour_slip_caps_at_one(self):
        svc = LiveExceptionService()
        promised = _now() + timedelta(hours=2)
        result = svc.classify_late_arrival(
            eta_id=4, tracked_entity_id=13, tenant_id=100,
            promised_at=promised,
            predicted_p50_at=promised + timedelta(hours=12),
            predicted_p10_at=promised + timedelta(hours=10),
            predicted_p90_at=promised + timedelta(hours=14),
        )
        assert result is not None
        # 720 min slip > 480 min horizon → urgency capped at 1.0 → INSPECT
        assert result.urgency == 1.0
        assert result.aiio_mode == AIIOMode.INSPECT


# ---------------------------------------------------------------------------
# classify_late_arrival — at-risk branch (promised inside [P10, P50])
# ---------------------------------------------------------------------------


class TestLateArrivalAtRisk:
    def test_promised_inside_lower_band_surfaces_at_risk(self):
        svc = LiveExceptionService()
        promised = _now() + timedelta(hours=2)
        # P10 < promised <= P50 with band slack ≥ threshold (30 min default)
        result = svc.classify_late_arrival(
            eta_id=5, tracked_entity_id=14, tenant_id=100,
            promised_at=promised,
            predicted_p50_at=promised,  # P50 == promised — at-risk edge
            predicted_p10_at=promised - timedelta(minutes=60),
            predicted_p90_at=promised + timedelta(minutes=60),
        )
        assert result is not None
        assert result.exception_type == ExceptionType.LATE_ARRIVAL_DETECTED
        # At-risk is always AUTOMATE band
        assert result.aiio_mode == AIIOMode.AUTOMATE
        assert result.urgency <= svc.automate_threshold
        assert "at risk" in result.reason_text.lower()
        assert "band_slack_min" in result.metadata

    def test_band_slack_below_threshold_returns_none(self):
        svc = LiveExceptionService()
        promised = _now() + timedelta(hours=2)
        # band_slack = 10 min, below the 30-min default threshold
        result = svc.classify_late_arrival(
            eta_id=6, tracked_entity_id=15, tenant_id=100,
            promised_at=promised,
            predicted_p50_at=promised + timedelta(seconds=0),  # P50 == promised
            predicted_p10_at=promised - timedelta(minutes=10),
            predicted_p90_at=promised + timedelta(minutes=30),
        )
        # P50 == promised → slip == 0 → not committed-late.
        # band_slack = 10 min < threshold → no at-risk either.
        assert result is None

    def test_at_risk_urgency_capped_at_automate_threshold(self):
        svc = LiveExceptionService(automate_threshold=0.3)
        promised = _now() + timedelta(hours=2)
        # band fully consumed: promised == P50, P10 well below
        result = svc.classify_late_arrival(
            eta_id=7, tracked_entity_id=16, tenant_id=100,
            promised_at=promised,
            predicted_p50_at=promised,
            predicted_p10_at=promised - timedelta(hours=2),
            predicted_p90_at=promised + timedelta(hours=2),
        )
        assert result is not None
        # consumed_frac == 1.0 → urgency capped at automate_threshold (0.3)
        assert result.urgency == pytest.approx(0.3, abs=0.001)
        assert result.aiio_mode == AIIOMode.AUTOMATE


# ---------------------------------------------------------------------------
# classify_late_arrival — edge cases
# ---------------------------------------------------------------------------


class TestLateArrivalEdgeCases:
    def test_missing_promised_at_returns_none(self):
        svc = LiveExceptionService()
        result = svc.classify_late_arrival(
            eta_id=8, tracked_entity_id=17, tenant_id=100,
            promised_at=None,
            predicted_p50_at=_now() + timedelta(hours=2),
        )
        assert result is None

    def test_missing_p50_returns_none(self):
        svc = LiveExceptionService()
        result = svc.classify_late_arrival(
            eta_id=9, tracked_entity_id=18, tenant_id=100,
            promised_at=_now() + timedelta(hours=2),
            predicted_p50_at=None,
        )
        assert result is None

    def test_p10_above_promised_no_exception(self):
        svc = LiveExceptionService()
        promised = _now() + timedelta(hours=2)
        # whole band sits before promised → on-track
        result = svc.classify_late_arrival(
            eta_id=10, tracked_entity_id=19, tenant_id=100,
            promised_at=promised,
            predicted_p50_at=promised - timedelta(minutes=15),
            predicted_p10_at=promised - timedelta(minutes=45),
            predicted_p90_at=promised - timedelta(minutes=5),
        )
        assert result is None


# ---------------------------------------------------------------------------
# classify_dwell_breach
# ---------------------------------------------------------------------------


class TestDwellBreach:
    def test_dwell_breach_event_low_urgency(self):
        svc = LiveExceptionService()
        # 30 min over a 60 min threshold → urgency = 1800/14400 = 0.125
        result = svc.classify_dwell_breach(
            event_id=20, tracked_entity_id=30, tenant_id=100,
            event_type="DWELL_BREACH",
            dwell_duration_seconds=5400,
            dwell_threshold_seconds=3600,
            occurred_at=_now(),
        )
        assert result is not None
        assert result.exception_type == ExceptionType.DWELL_BREACH_ALERT
        assert result.urgency == pytest.approx(1800 / (4 * 3600), abs=0.001)
        assert result.aiio_mode == AIIOMode.AUTOMATE
        assert result.source_event_id == 20
        assert result.metadata["breach_seconds"] == 1800

    def test_exit_event_with_breach_classifies(self):
        svc = LiveExceptionService()
        result = svc.classify_dwell_breach(
            event_id=21, tracked_entity_id=31, tenant_id=100,
            event_type="EXIT",
            dwell_duration_seconds=14400,  # 4h
            dwell_threshold_seconds=3600,  # 1h threshold → 3h breach
            occurred_at=_now(),
        )
        assert result is not None
        # 10800 sec / 14400 sec horizon = 0.75 → INSPECT
        assert result.urgency == pytest.approx(0.75, abs=0.001)
        assert result.aiio_mode == AIIOMode.INSPECT
        assert result.metadata["event_type"] == "EXIT"

    def test_exit_event_no_breach_returns_none(self):
        svc = LiveExceptionService()
        result = svc.classify_dwell_breach(
            event_id=22, tracked_entity_id=32, tenant_id=100,
            event_type="EXIT",
            dwell_duration_seconds=1800,  # 30 min
            dwell_threshold_seconds=3600,  # 60 min threshold → no breach
            occurred_at=_now(),
        )
        assert result is None

    def test_entry_event_returns_none(self):
        svc = LiveExceptionService()
        result = svc.classify_dwell_breach(
            event_id=23, tracked_entity_id=33, tenant_id=100,
            event_type="ENTRY",
            dwell_duration_seconds=5400,
            dwell_threshold_seconds=3600,
            occurred_at=_now(),
        )
        assert result is None

    def test_missing_dwell_duration_returns_none(self):
        svc = LiveExceptionService()
        result = svc.classify_dwell_breach(
            event_id=24, tracked_entity_id=34, tenant_id=100,
            event_type="DWELL_BREACH",
            dwell_duration_seconds=None,
            dwell_threshold_seconds=3600,
            occurred_at=_now(),
        )
        assert result is None

    def test_missing_threshold_returns_none(self):
        svc = LiveExceptionService()
        result = svc.classify_dwell_breach(
            event_id=25, tracked_entity_id=35, tenant_id=100,
            event_type="DWELL_BREACH",
            dwell_duration_seconds=5400,
            dwell_threshold_seconds=None,
            occurred_at=_now(),
        )
        assert result is None

    def test_long_breach_caps_at_one(self):
        svc = LiveExceptionService()
        # 24 hours over a 1h threshold → urgency capped at 1.0
        result = svc.classify_dwell_breach(
            event_id=26, tracked_entity_id=36, tenant_id=100,
            event_type="DWELL_BREACH",
            dwell_duration_seconds=86400,
            dwell_threshold_seconds=3600,
            occurred_at=_now(),
        )
        assert result is not None
        assert result.urgency == 1.0
        assert result.aiio_mode == AIIOMode.INSPECT


# ---------------------------------------------------------------------------
# AIIO band classification
# ---------------------------------------------------------------------------


class TestAIIOBands:
    def test_low_urgency_maps_to_automate(self):
        svc = LiveExceptionService()
        assert svc._classify_aiio(0.0) == AIIOMode.AUTOMATE
        assert svc._classify_aiio(0.1) == AIIOMode.AUTOMATE
        assert svc._classify_aiio(0.299) == AIIOMode.AUTOMATE

    def test_mid_urgency_maps_to_inform(self):
        svc = LiveExceptionService()
        assert svc._classify_aiio(0.3) == AIIOMode.INFORM
        assert svc._classify_aiio(0.5) == AIIOMode.INFORM
        assert svc._classify_aiio(0.649) == AIIOMode.INFORM

    def test_high_urgency_maps_to_inspect(self):
        svc = LiveExceptionService()
        assert svc._classify_aiio(0.65) == AIIOMode.INSPECT
        assert svc._classify_aiio(0.9) == AIIOMode.INSPECT
        assert svc._classify_aiio(1.0) == AIIOMode.INSPECT
