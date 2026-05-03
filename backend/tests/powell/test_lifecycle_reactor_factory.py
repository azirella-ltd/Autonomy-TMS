"""Tests for §3.45 production wire-up — A2ALifecycleAdjustmentProvider + factory.

Covers the production bridge between DP's A2A skill and TMS's reactor
Protocol. The reactor itself stays Protocol-typed (tested with fake
providers in test_lane_volume_lifecycle_reactor.py); this file
exercises the *concrete* implementation that wraps the A2A client.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


_FACTORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "app", "services", "powell", "lifecycle_reactor_factory.py",
)


def _load_factory_module():
    spec = importlib.util.spec_from_file_location(
        "lifecycle_reactor_factory_test_loaded", _FACTORY_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


factory_module = _load_factory_module()
A2ALifecycleAdjustmentProvider = factory_module.A2ALifecycleAdjustmentProvider
make_lifecycle_reactor = factory_module.make_lifecycle_reactor


# ---------------------------------------------------------------------------
# A2ALifecycleAdjustmentProvider — sync wrapper around async A2A client
# ---------------------------------------------------------------------------


class _FakeAsyncClient:
    """Minimal async-compatible client stub."""

    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list = []

    async def send_task(
        self, *, skill_id: str, input: dict, tenant_id=None,
    ):
        self.calls.append({
            "skill_id": skill_id,
            "input": dict(input),
            "tenant_id": tenant_id,
        })
        return self.response


def _task_with_payload(payload: dict):
    """Build a Task envelope with ``payload`` at
    ``task.artifacts[0].parts[0].data`` — the modern shape."""
    part = SimpleNamespace(data=payload)
    artifact = SimpleNamespace(parts=[part])
    return SimpleNamespace(artifacts=[artifact])


class TestProviderHappyPath:
    def test_calls_correct_skill_id(self):
        client = _FakeAsyncClient(
            _task_with_payload({"adjustments": [], "count": 0}),
        )
        provider = A2ALifecycleAdjustmentProvider(client)
        provider.list_lifecycle_adjustments(tenant_id=42)
        assert len(client.calls) == 1
        assert client.calls[0]["skill_id"] == "forecast.adjustment.list_lifecycle"

    def test_passes_tenant_id_in_payload_and_metadata(self):
        client = _FakeAsyncClient(
            _task_with_payload({"adjustments": []}),
        )
        provider = A2ALifecycleAdjustmentProvider(client)
        provider.list_lifecycle_adjustments(tenant_id=42)
        call = client.calls[0]
        assert call["input"]["tenant_id"] == 42
        assert call["tenant_id"] == 42

    def test_passes_optional_filters(self):
        client = _FakeAsyncClient(
            _task_with_payload({"adjustments": []}),
        )
        provider = A2ALifecycleAdjustmentProvider(client)
        since = datetime(2026, 5, 1, tzinfo=timezone.utc)
        provider.list_lifecycle_adjustments(
            tenant_id=42,
            since=since,
            reason_codes=["lifecycle_npi_introduction"],
            limit=500,
        )
        call = client.calls[0]
        assert call["input"]["since"] == "2026-05-01T00:00:00+00:00"
        assert call["input"]["reason_codes"] == [
            "lifecycle_npi_introduction"
        ]
        assert call["input"]["limit"] == 500

    def test_extracts_adjustments_list(self):
        adjustments = [
            {
                "id": 1, "product_id": "SKU-A",
                "reason_code": "lifecycle_npi_introduction",
                "adjustment_value": 0.50,
            },
            {
                "id": 2, "product_id": "SKU-B",
                "reason_code": "lifecycle_eol_phaseout",
                "adjustment_value": -0.30,
            },
        ]
        client = _FakeAsyncClient(
            _task_with_payload({"adjustments": adjustments, "count": 2}),
        )
        provider = A2ALifecycleAdjustmentProvider(client)
        result = provider.list_lifecycle_adjustments(tenant_id=42)
        assert result == adjustments


# ---------------------------------------------------------------------------
# Provider error handling — failures return [] rather than raise
# ---------------------------------------------------------------------------


class TestProviderErrorHandling:
    def test_a2a_failure_returns_empty_list(self):
        async def _raise(**kwargs):
            raise RuntimeError("A2A endpoint unreachable")

        client = MagicMock()
        client.send_task = _raise
        provider = A2ALifecycleAdjustmentProvider(client)
        result = provider.list_lifecycle_adjustments(tenant_id=42)
        # Must NOT raise — reactor expects []-on-failure contract.
        assert result == []

    def test_unrecognised_response_shape_returns_empty(self):
        # Task with no artifacts and no message — _extract_skill_result
        # returns None, which the provider coerces to [].
        client = _FakeAsyncClient(SimpleNamespace())
        provider = A2ALifecycleAdjustmentProvider(client)
        assert provider.list_lifecycle_adjustments(tenant_id=42) == []

    def test_adjustments_not_a_list_returns_empty(self):
        client = _FakeAsyncClient(
            _task_with_payload({"adjustments": "not-a-list"}),
        )
        provider = A2ALifecycleAdjustmentProvider(client)
        assert provider.list_lifecycle_adjustments(tenant_id=42) == []

    def test_dict_response_with_result_key(self):
        """Some A2A spec versions return ``{"result": {...}}`` directly
        rather than wrapping in a Task."""
        client = _FakeAsyncClient(
            {"result": {"adjustments": [{"id": 1}]}}
        )
        provider = A2ALifecycleAdjustmentProvider(client)
        result = provider.list_lifecycle_adjustments(tenant_id=42)
        assert result == [{"id": 1}]


# ---------------------------------------------------------------------------
# make_lifecycle_reactor factory
# ---------------------------------------------------------------------------


class TestFactoryReturnsNoneWhenA2AClientUnavailable:
    def test_a2a_client_not_installed_returns_none(self):
        """Production environments without azirella_a2a_client (e.g.
        a stripped-down deployment) get a graceful None — reactor
        opt-out is automatic."""
        with patch.dict("sys.modules", {"azirella_a2a_client": None}):
            result = make_lifecycle_reactor(db=MagicMock(), tenant_id=42)
        assert result is None


def _install_a2a_stub(for_plane_impl):
    """Install a minimal ``azirella_a2a_client`` stub module with the
    given ``Client.for_plane`` callable.

    The factory also lazy-imports
    ``app.services.powell.lane_volume_lifecycle_reactor`` which would
    pull in the heavy ``app.services.powell.__init__``. We pre-load
    the reactor module via importlib (bypassing the package init)
    and inject it under both possible import keys so the factory
    finds it without triggering the package-init side effects.
    """
    import importlib
    import importlib.util
    import types

    stub = types.ModuleType("azirella_a2a_client")

    class StubClient:
        for_plane = staticmethod(for_plane_impl)

    stub.Client = StubClient
    sys.modules["azirella_a2a_client"] = stub

    # Pre-load the reactor module via importlib if it's not already
    # in sys.modules under the production key.
    reactor_key = "app.services.powell.lane_volume_lifecycle_reactor"
    if reactor_key not in sys.modules:
        reactor_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)
            ))),
            "app", "services", "powell", "lane_volume_lifecycle_reactor.py",
        )
        spec = importlib.util.spec_from_file_location(
            reactor_key, reactor_path
        )
        reactor_mod = importlib.util.module_from_spec(spec)
        sys.modules[reactor_key] = reactor_mod
        # Pre-register the parent packages so ``from
        # app.services.powell.lane_volume_lifecycle_reactor import ...``
        # doesn't trigger the real powell/__init__.
        for parent in ("app", "app.services", "app.services.powell"):
            if parent not in sys.modules:
                pkg = types.ModuleType(parent)
                pkg.__path__ = []
                sys.modules[parent] = pkg
        spec.loader.exec_module(reactor_mod)
        # Hang the loaded module on the parent so attribute access
        # works.
        sys.modules["app.services.powell"].lane_volume_lifecycle_reactor = (
            reactor_mod
        )

    return stub


class TestFactoryReturnsNoneWhenPlaneResolutionFails:
    def test_no_dp_producer_registered_returns_none(self):
        """When PlaneRegistry has no DP producer for the tenant,
        Client.for_plane raises and we return None."""
        def _raise(*a, **kw):
            raise Exception("no DP producer registered")
        prev = sys.modules.get("azirella_a2a_client")
        _install_a2a_stub(_raise)
        try:
            result = make_lifecycle_reactor(db=MagicMock(), tenant_id=42)
        finally:
            if prev is not None:
                sys.modules["azirella_a2a_client"] = prev
            else:
                sys.modules.pop("azirella_a2a_client", None)
        assert result is None


class TestFactoryConstructsReactorOnHappyPath:
    def test_factory_returns_reactor_when_dp_resolved(self):
        fake_client = MagicMock()
        prev = sys.modules.get("azirella_a2a_client")
        _install_a2a_stub(lambda *a, **kw: fake_client)
        try:
            reactor = make_lifecycle_reactor(db=MagicMock(), tenant_id=42)
        finally:
            if prev is not None:
                sys.modules["azirella_a2a_client"] = prev
            else:
                sys.modules.pop("azirella_a2a_client", None)
        assert reactor is not None
        assert reactor.provider is not None
        assert isinstance(reactor.provider, A2ALifecycleAdjustmentProvider)

    def test_factory_threads_coverage_threshold_override(self):
        fake_client = MagicMock()
        prev = sys.modules.get("azirella_a2a_client")
        _install_a2a_stub(lambda *a, **kw: fake_client)
        try:
            reactor = make_lifecycle_reactor(
                db=MagicMock(), tenant_id=42,
                coverage_threshold=0.0,
            )
        finally:
            if prev is not None:
                sys.modules["azirella_a2a_client"] = prev
            else:
                sys.modules.pop("azirella_a2a_client", None)
        assert reactor is not None
        assert reactor.coverage_threshold == 0.0
