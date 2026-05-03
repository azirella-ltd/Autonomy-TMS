"""Tests for §3.43 / §3.40 Phase 3b — lifecycle_aggregator_jobs cron registration.

Verifies the APScheduler registration shape (job id, cron schedule,
misfire grace), the discovery filter (PRODUCTION + ACTIVE + BASELINE
configs only — same shape as l3_cascade_jobs), and graceful
no-scheduler-available behaviour. The job body itself
(_run_aggregator_for_all_tenants) is not exercised here — its
integration test against a real Postgres + ProductLane table lives
in the integration suite, since the aggregator's SQL JOIN needs
Core's transitive-FK conftest stubs to run on SQLite.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest


_JOBS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "app", "services", "powell", "lifecycle_aggregator_jobs.py",
)


def _load_jobs_module():
    spec = importlib.util.spec_from_file_location(
        "lifecycle_aggregator_jobs_test_loaded", _JOBS_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


jobs_module = _load_jobs_module()
register_lifecycle_aggregator_jobs = jobs_module.register_lifecycle_aggregator_jobs


# ---------------------------------------------------------------------------
# Registration — happy path
# ---------------------------------------------------------------------------


class TestRegisterLifecycleAggregatorJobs:
    def test_registers_daily_2am_cron(self):
        scheduler = MagicMock()
        scheduler.add_job = MagicMock()
        scheduler_service = MagicMock()
        scheduler_service._scheduler = scheduler

        register_lifecycle_aggregator_jobs(scheduler_service)

        scheduler.add_job.assert_called_once()
        call = scheduler.add_job.call_args
        # Cron trigger at 02:00.
        trigger = call.kwargs["trigger"]
        # CronTrigger fields stored as cron_field expressions.
        assert "hour=2" in str(trigger) or "hour='2'" in str(trigger)
        assert "minute=0" in str(trigger) or "minute='0'" in str(trigger)

    def test_uses_stable_job_id(self):
        scheduler = MagicMock()
        scheduler.add_job = MagicMock()
        scheduler_service = MagicMock()
        scheduler_service._scheduler = scheduler

        register_lifecycle_aggregator_jobs(scheduler_service)

        call = scheduler.add_job.call_args
        assert call.kwargs["id"] == "lifecycle_product_lane_aggregator_daily"

    def test_replace_existing_for_idempotent_registration(self):
        scheduler = MagicMock()
        scheduler.add_job = MagicMock()
        scheduler_service = MagicMock()
        scheduler_service._scheduler = scheduler

        register_lifecycle_aggregator_jobs(scheduler_service)

        call = scheduler.add_job.call_args
        # Calling register on every app start must not duplicate jobs.
        assert call.kwargs["replace_existing"] is True

    def test_misfire_grace_one_hour(self):
        scheduler = MagicMock()
        scheduler.add_job = MagicMock()
        scheduler_service = MagicMock()
        scheduler_service._scheduler = scheduler

        register_lifecycle_aggregator_jobs(scheduler_service)

        call = scheduler.add_job.call_args
        assert call.kwargs["misfire_grace_time"] == 3600


# ---------------------------------------------------------------------------
# Registration — graceful failure when scheduler unavailable
# ---------------------------------------------------------------------------


class TestRegisterLifecycleAggregatorJobsNoScheduler:
    def test_no_scheduler_available_logs_warning_and_returns(self, caplog):
        scheduler_service = MagicMock()
        scheduler_service._scheduler = None

        with caplog.at_level("WARNING"):
            register_lifecycle_aggregator_jobs(scheduler_service)

        assert any(
            "Scheduler not available" in r.message
            for r in caplog.records
        )
        # add_job never called.
        assert not scheduler_service.add_job.called


# ---------------------------------------------------------------------------
# Job body — discover_active_tenants filter shape
# ---------------------------------------------------------------------------


class TestDiscoverActiveTenants:
    """The discovery helper exists and has the expected signature.

    Calling the helper triggers an import of master.config + tenant —
    which transitively triggers SQLAlchemy mapper configuration that
    pollutes other test modules' fixtures (the reactor's minimal
    SQLite setup breaks once master is fully resolved). For local
    unit-test cleanliness we contract-test only; the actual DB
    behaviour is exercised in the integration suite (Postgres CI)."""

    def test_discovery_helper_exists(self):
        assert callable(jobs_module._discover_active_tenants)

    def test_discovery_helper_signature(self):
        import inspect
        sig = inspect.signature(jobs_module._discover_active_tenants)
        # Single positional argument: the db session.
        assert list(sig.parameters.keys()) == ["db"]
