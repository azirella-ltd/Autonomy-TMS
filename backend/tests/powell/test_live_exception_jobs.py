"""Tests for live_exception_jobs — cron registration + signal-bus
emission.

Loaded via ``importlib`` to bypass the heavy
``app.services.powell.__init__`` import side effects.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from datetime import datetime, timezone

import pytest


_LES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "app", "services", "powell", "live_exception_service.py",
)
_JOBS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "app", "services", "powell", "live_exception_jobs.py",
)
_HIVE_SIGNAL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "app", "services", "powell", "hive_signal.py",
)


def _ensure_parent_pkgs() -> None:
    for parent in ("app", "app.services", "app.services.powell"):
        if parent not in sys.modules:
            pkg = types.ModuleType(parent)
            pkg.__path__ = []
            sys.modules[parent] = pkg


def _load(path: str, name: str):
    _ensure_parent_pkgs()
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load LES + hive_signal first so jobs can import them via the
# canonical path (the parent package is a stub from _ensure_parent_pkgs;
# importlib.exec_module registers the loaded module under its
# canonical name so subsequent `from app.services.powell.X import ...`
# resolves cleanly).
_hive = _load(_HIVE_SIGNAL_PATH, "app.services.powell.hive_signal")
_les = _load(_LES_PATH, "app.services.powell.live_exception_service")
_jobs = _load(_JOBS_PATH, "app.services.powell.live_exception_jobs")

LiveExceptionService = _les.LiveExceptionService
ExceptionResult = _les.ExceptionResult
ExceptionType = _les.ExceptionType
AIIOMode = _les.AIIOMode

register_live_exception_jobs = _jobs.register_live_exception_jobs
_emit_signals = _jobs._emit_signals
_LIVE_EXCEPTION_JOB_ID = _jobs._LIVE_EXCEPTION_JOB_ID
_TICK_INTERVAL_MINUTES = _jobs._TICK_INTERVAL_MINUTES


def _now() -> datetime:
    return datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Cron registration
# ---------------------------------------------------------------------------


class FakeScheduler:
    def __init__(self):
        self.jobs = []

    def add_job(self, **kwargs):
        self.jobs.append(kwargs)


class FakeSchedulerService:
    def __init__(self, scheduler):
        self._scheduler = scheduler


class TestCronRegistration:
    def test_registers_with_15min_cadence(self):
        sched = FakeScheduler()
        register_live_exception_jobs(FakeSchedulerService(sched))
        assert len(sched.jobs) == 1
        job = sched.jobs[0]
        assert job["id"] == _LIVE_EXCEPTION_JOB_ID
        assert "every 15 min" in job["name"].lower()
        assert job["replace_existing"] is True
        # CronTrigger with minute=*/15 — verify the field
        trigger = job["trigger"]
        minute_field = next(f for f in trigger.fields if f.name == "minute")
        assert "*/15" in str(minute_field)

    def test_no_scheduler_logs_and_skips(self, caplog):
        # scheduler_service._scheduler is None → registration becomes a
        # no-op with a warning, not an exception.
        svc = FakeSchedulerService(None)
        with caplog.at_level("WARNING"):
            register_live_exception_jobs(svc)
        assert any(
            "scheduler not available" in r.message.lower()
            for r in caplog.records
        )

    def test_idempotent_replace_existing(self):
        # Two calls register the same job ID — replace_existing=True
        # makes this safe; we just verify both calls land.
        sched = FakeScheduler()
        register_live_exception_jobs(FakeSchedulerService(sched))
        register_live_exception_jobs(FakeSchedulerService(sched))
        assert len(sched.jobs) == 2
        assert sched.jobs[0]["id"] == sched.jobs[1]["id"]
        assert all(j["replace_existing"] for j in sched.jobs)


# ---------------------------------------------------------------------------
# HiveSignal emission
# ---------------------------------------------------------------------------


class FakeSignalBus:
    def __init__(self):
        self.emitted = []

    def emit(self, signal):
        self.emitted.append(signal)


class TestSignalEmission:
    def test_emits_hive_signal_per_late_arrival(self, monkeypatch):
        # Patch _get_process_signal_bus to return our fake bus.
        bus = FakeSignalBus()
        monkeypatch.setattr(_jobs, "_get_process_signal_bus", lambda: bus)

        # Stub HiveSignal + HiveSignalType so jobs can import them
        # without dragging the real module (its module-load is fine
        # but the emission test wants to inspect what was emitted).
        from app.services.powell.hive_signal import HiveSignal, HiveSignalType

        excs = [
            ExceptionResult(
                exception_type=ExceptionType.LATE_ARRIVAL_DETECTED,
                tracked_entity_id=10, tenant_id=100,
                detected_at=_now(), urgency=0.5, aiio_mode=AIIOMode.INFORM,
                reason_text="Late arrival",
                source_eta_id=42,
                metadata={"slip_minutes": 240.0},
            ),
        ]
        _emit_signals(excs)

        assert len(bus.emitted) == 1
        sig = bus.emitted[0]
        assert sig.signal_type == HiveSignalType.LATE_ARRIVAL_DETECTED
        assert sig.urgency == 0.5
        assert sig.direction == "risk"
        assert sig.source_trm == "live_exception_service"
        assert sig.payload["tracked_entity_id"] == 10
        assert sig.payload["source_eta_id"] == 42
        assert sig.payload["aiio_mode"] == "INFORM"
        # 15-min half-life matches cron cadence
        assert sig.half_life_minutes == 15.0

    def test_emits_dwell_breach_signal(self, monkeypatch):
        bus = FakeSignalBus()
        monkeypatch.setattr(_jobs, "_get_process_signal_bus", lambda: bus)
        from app.services.powell.hive_signal import HiveSignalType

        excs = [
            ExceptionResult(
                exception_type=ExceptionType.DWELL_BREACH_ALERT,
                tracked_entity_id=20, tenant_id=100,
                detected_at=_now(), urgency=0.85, aiio_mode=AIIOMode.INSPECT,
                reason_text="Dwell breach",
                source_event_id=99,
                metadata={"breach_seconds": 12000},
            ),
        ]
        _emit_signals(excs)
        assert len(bus.emitted) == 1
        assert bus.emitted[0].signal_type == HiveSignalType.DWELL_BREACH_ALERT
        assert bus.emitted[0].payload["source_event_id"] == 99

    def test_no_bus_is_no_op(self, monkeypatch):
        # _get_process_signal_bus returns None → emission silently skips,
        # no HiveSignal import overhead, no errors.
        monkeypatch.setattr(_jobs, "_get_process_signal_bus", lambda: None)
        excs = [
            ExceptionResult(
                exception_type=ExceptionType.LATE_ARRIVAL_DETECTED,
                tracked_entity_id=1, tenant_id=100,
                detected_at=_now(), urgency=0.5, aiio_mode=AIIOMode.INFORM,
                reason_text="...", source_eta_id=1, metadata={},
            ),
        ]
        # Must not raise.
        _emit_signals(excs)

    def test_emit_failure_does_not_propagate(self, monkeypatch, caplog):
        # If bus.emit raises, the cron must continue with the next
        # exception — failure-isolated, logged at ERROR.
        class BadBus:
            def emit(self, _):
                raise RuntimeError("bus down")

        monkeypatch.setattr(_jobs, "_get_process_signal_bus", lambda: BadBus())
        excs = [
            ExceptionResult(
                exception_type=ExceptionType.LATE_ARRIVAL_DETECTED,
                tracked_entity_id=1, tenant_id=100,
                detected_at=_now(), urgency=0.5, aiio_mode=AIIOMode.INFORM,
                reason_text="...", source_eta_id=1, metadata={},
            ),
        ]
        with caplog.at_level("ERROR"):
            _emit_signals(excs)
        assert any(
            "failed to emit hivesignal" in r.message.lower()
            for r in caplog.records
        )

    def test_empty_list_is_no_op(self, monkeypatch):
        called = []
        def fake_bus():
            called.append(1)
            return FakeSignalBus()
        monkeypatch.setattr(_jobs, "_get_process_signal_bus", fake_bus)
        _emit_signals([])
        # Bus lookup only happens once and we don't emit anything;
        # we just verify no error.
