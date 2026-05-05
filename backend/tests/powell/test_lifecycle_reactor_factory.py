"""Tests for §3.45 production wire-up — RouterLifecycleAdjustmentProvider + factory.

Covers the production bridge between DP's cross-plane skill and TMS's
reactor Protocol. The reactor itself stays Protocol-typed (tested with
fake providers in test_lane_volume_lifecycle_reactor.py); this file
exercises the *concrete* implementation that wraps
:class:`azirella_router.RouterClient`.

AD-12 v3 cutover (CONSUMER_ADOPTION_LOG 2026-05-04, §3.48): the prior
implementation wrapped ``azirella_a2a_client.Client`` directly; tests
correspondingly faked that. Post-cutover, the provider wraps
:class:`RouterClient` and tests fake that instead.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

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
RouterLifecycleAdjustmentProvider = factory_module.RouterLifecycleAdjustmentProvider
make_lifecycle_reactor = factory_module.make_lifecycle_reactor


# ---------------------------------------------------------------------------
# Helpers — fake RouterClient + sys.modules surgery
# ---------------------------------------------------------------------------


class _FakeRouterClient:
    """Minimal stand-in for ``azirella_router.RouterClient``.

    Records calls in ``calls`` and returns a configurable response.
    The response can be a dict (HEURISTIC-style), an envelope dict
    (``{"result": {...}}``), or a Task-like object exposing
    ``artifacts[0].parts[0].data``.
    """

    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list = []

    def call_skill(self, **kwargs):
        self.calls.append(dict(kwargs))
        if callable(self.response):
            return self.response(**kwargs)
        return self.response


def _install_router_stub(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: _FakeRouterClient,
) -> types.ModuleType:
    """Install a minimal ``azirella_router`` stub module exposing
    ``RouterClient`` whose ``call_skill`` proxies to ``fake_client``.

    Uses ``monkeypatch.setitem(sys.modules, ...)`` for every write so
    pytest auto-tears-down at test end. Earlier revisions wrote
    ``sys.modules`` directly and only restored ``"azirella_router"``;
    that left ``"app"``, ``"app.services"``, ``"app.services.powell"``,
    and ``"app.services.powell.lane_volume_lifecycle_reactor"`` polluted
    permanently. Subsequent test modules
    (notably ``backend/tests/a2a/test_tms_agent_card.py``) hit the
    stubbed ``app`` package and fail collection. monkeypatch closes
    that gap.
    """
    stub = types.ModuleType("azirella_router")

    class _StubRouterClient:
        @staticmethod
        def call_skill(**kwargs):
            return fake_client.call_skill(**kwargs)

    stub.RouterClient = _StubRouterClient
    monkeypatch.setitem(sys.modules, "azirella_router", stub)

    # Pre-load the reactor module so the factory's lazy import resolves
    # without pulling in the real powell/__init__.
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
        monkeypatch.setitem(sys.modules, reactor_key, reactor_mod)
        for parent in ("app", "app.services", "app.services.powell"):
            if parent not in sys.modules:
                pkg = types.ModuleType(parent)
                pkg.__path__ = []
                monkeypatch.setitem(sys.modules, parent, pkg)
        spec.loader.exec_module(reactor_mod)
        # Hang the loaded module on the parent — the parent itself was
        # monkeypatched in, so this attribute is torn down with it.
        sys.modules["app.services.powell"].lane_volume_lifecycle_reactor = (
            reactor_mod
        )

    return stub


def _task_with_payload(payload: dict):
    """Build a Task envelope with ``payload`` at
    ``task.artifacts[0].parts[0].data`` — the modern A2A shape."""
    part = SimpleNamespace(data=payload)
    artifact = SimpleNamespace(parts=[part])
    return SimpleNamespace(artifacts=[artifact])


# ---------------------------------------------------------------------------
# RouterLifecycleAdjustmentProvider — happy path
# ---------------------------------------------------------------------------


class TestProviderHappyPath:
    def test_calls_correct_skill_id(self, monkeypatch):
        fake = _FakeRouterClient({"adjustments": [], "count": 0})
        _install_router_stub(monkeypatch, fake)
        provider = RouterLifecycleAdjustmentProvider(db=MagicMock())
        provider.list_lifecycle_adjustments(tenant_id=42)
        assert len(fake.calls) == 1
        assert fake.calls[0]["skill_id"] == "forecast.adjustment.list_lifecycle"

    def test_passes_tenant_id_in_payload_and_kwarg(self, monkeypatch):
        fake = _FakeRouterClient({"adjustments": []})
        _install_router_stub(monkeypatch, fake)
        provider = RouterLifecycleAdjustmentProvider(db=MagicMock())
        provider.list_lifecycle_adjustments(tenant_id=42)
        call = fake.calls[0]
        assert call["tenant_id"] == 42
        assert call["inp"]["tenant_id"] == 42

    def test_passes_config_id_when_set(self, monkeypatch):
        fake = _FakeRouterClient({"adjustments": []})
        _install_router_stub(monkeypatch, fake)
        provider = RouterLifecycleAdjustmentProvider(
            db=MagicMock(), config_id=7,
        )
        provider.list_lifecycle_adjustments(tenant_id=42)
        assert fake.calls[0]["config_id"] == 7

    def test_passes_optional_filters(self, monkeypatch):
        fake = _FakeRouterClient({"adjustments": []})
        _install_router_stub(monkeypatch, fake)
        provider = RouterLifecycleAdjustmentProvider(db=MagicMock())
        since = datetime(2026, 5, 1, tzinfo=timezone.utc)
        provider.list_lifecycle_adjustments(
            tenant_id=42,
            since=since,
            reason_codes=["lifecycle_npi_introduction"],
            limit=500,
        )
        inp = fake.calls[0]["inp"]
        assert inp["since"] == "2026-05-01T00:00:00+00:00"
        assert inp["reason_codes"] == ["lifecycle_npi_introduction"]
        assert inp["limit"] == 500

    def test_extracts_adjustments_list(self, monkeypatch):
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
        fake = _FakeRouterClient({"adjustments": adjustments, "count": 2})
        _install_router_stub(monkeypatch, fake)
        provider = RouterLifecycleAdjustmentProvider(db=MagicMock())
        result = provider.list_lifecycle_adjustments(tenant_id=42)
        assert result == adjustments

    def test_heuristic_stamped_response_handled(self, monkeypatch):
        """HEURISTIC-tier response carries warning markers alongside the
        adjustments dict — provider should still extract cleanly."""
        fake = _FakeRouterClient({
            "adjustments": [{"id": 99}],
            "count": 1,
            "producer_tier": "HEURISTIC",
            "producer_signature": "autonomy-dp-heuristics:list_lifecycle:v0.1.0",
            "heuristic_warning": "AZIRELLA-STUB-WARNING: ...",
            "heuristic_plane": "autonomy-dp-heuristics",
        })
        _install_router_stub(monkeypatch, fake)
        provider = RouterLifecycleAdjustmentProvider(db=MagicMock())
        result = provider.list_lifecycle_adjustments(tenant_id=42)
        assert result == [{"id": 99}]


# ---------------------------------------------------------------------------
# RouterLifecycleAdjustmentProvider — error handling
# ---------------------------------------------------------------------------


class TestProviderErrorHandling:
    def test_router_call_failure_returns_empty_list(self, monkeypatch):
        def _raise(**kwargs):
            raise RuntimeError("router endpoint unreachable")

        fake = _FakeRouterClient(_raise)
        _install_router_stub(monkeypatch, fake)
        provider = RouterLifecycleAdjustmentProvider(db=MagicMock())
        result = provider.list_lifecycle_adjustments(tenant_id=42)
        # Must NOT raise — reactor expects []-on-failure contract.
        assert result == []

    def test_unrecognised_response_shape_returns_empty(
        self, monkeypatch,
    ):
        # Empty SimpleNamespace — no artifacts, no message, not a dict.
        fake = _FakeRouterClient(SimpleNamespace())
        _install_router_stub(monkeypatch, fake)
        provider = RouterLifecycleAdjustmentProvider(db=MagicMock())
        assert provider.list_lifecycle_adjustments(tenant_id=42) == []

    def test_adjustments_not_a_list_returns_empty(
        self, monkeypatch,
    ):
        fake = _FakeRouterClient({"adjustments": "not-a-list"})
        _install_router_stub(monkeypatch, fake)
        provider = RouterLifecycleAdjustmentProvider(db=MagicMock())
        assert provider.list_lifecycle_adjustments(tenant_id=42) == []

    def test_dict_envelope_with_result_key_unwraps(
        self, monkeypatch,
    ):
        """Some A2A spec versions return ``{"result": {...}}`` directly
        rather than wrapping in a Task-like object."""
        fake = _FakeRouterClient(
            {"result": {"adjustments": [{"id": 1}]}}
        )
        _install_router_stub(monkeypatch, fake)
        provider = RouterLifecycleAdjustmentProvider(db=MagicMock())
        result = provider.list_lifecycle_adjustments(tenant_id=42)
        assert result == [{"id": 1}]

    def test_task_envelope_with_artifacts_unwraps(
        self, monkeypatch,
    ):
        """AZIRELLA-tier dispatches may return a Task-like object; the
        provider walks artifacts → parts → data."""
        fake = _FakeRouterClient(
            _task_with_payload({"adjustments": [{"id": 7}], "count": 1}),
        )
        _install_router_stub(monkeypatch, fake)
        provider = RouterLifecycleAdjustmentProvider(db=MagicMock())
        result = provider.list_lifecycle_adjustments(tenant_id=42)
        assert result == [{"id": 7}]

    def test_router_not_installed_returns_empty(self, monkeypatch):
        """Stripped-down deployments without azirella-router get a
        graceful [] from the provider rather than an ImportError.
        ``sys.modules['azirella_router'] = None`` makes the lazy
        import raise ImportError per CPython import semantics."""
        monkeypatch.setitem(sys.modules, "azirella_router", None)
        provider = RouterLifecycleAdjustmentProvider(db=MagicMock())
        assert provider.list_lifecycle_adjustments(tenant_id=42) == []


# ---------------------------------------------------------------------------
# make_lifecycle_reactor factory
# ---------------------------------------------------------------------------


class TestFactoryReturnsNoneWhenRouterUnavailable:
    def test_router_not_installed_returns_none(self, monkeypatch):
        """Production environments without azirella-router (e.g. a
        stripped-down deployment) get a graceful None — reactor opt-out
        is automatic."""
        monkeypatch.setitem(sys.modules, "azirella_router", None)
        result = make_lifecycle_reactor(db=MagicMock(), tenant_id=42)
        assert result is None


class TestFactoryConstructsReactorOnHappyPath:
    def test_factory_returns_reactor_when_router_importable(
        self, monkeypatch,
    ):
        fake = _FakeRouterClient({"adjustments": []})
        _install_router_stub(monkeypatch, fake)
        reactor = make_lifecycle_reactor(db=MagicMock(), tenant_id=42)
        assert reactor is not None
        assert reactor.provider is not None
        assert isinstance(reactor.provider, RouterLifecycleAdjustmentProvider)

    def test_factory_threads_coverage_threshold_override(
        self, monkeypatch,
    ):
        fake = _FakeRouterClient({"adjustments": []})
        _install_router_stub(monkeypatch, fake)
        reactor = make_lifecycle_reactor(
            db=MagicMock(), tenant_id=42,
            coverage_threshold=0.0,
        )
        assert reactor is not None
        assert reactor.coverage_threshold == 0.0

    def test_factory_propagates_config_id_to_provider(
        self, monkeypatch,
    ):
        """``config_id`` is stored on the provider and forwarded to
        every router dispatch."""
        fake = _FakeRouterClient({"adjustments": []})
        _install_router_stub(monkeypatch, fake)
        reactor = make_lifecycle_reactor(
            db=MagicMock(), tenant_id=42, config_id=99,
        )
        assert reactor is not None
        # Drive a call through the provider and verify config_id
        # propagation through to the router stub.
        reactor.provider.list_lifecycle_adjustments(tenant_id=42)
        assert fake.calls[0]["config_id"] == 99
