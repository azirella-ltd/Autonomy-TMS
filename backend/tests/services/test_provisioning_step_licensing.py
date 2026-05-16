"""§1.17 Phase 3 — TMS provisioning service consumes Core's
``ConfigProvisioningStatus.STEP_REQUIRED_PLANES`` map.

Before this Phase, TMS's provisioning service had NO plane-licensing
gate at all — a DP-only or SCP-only tenant invoking it would have run
TMS-only steps regardless. Phase 3 adds the gate via Core's canonical
``step_is_licensed`` classmethod (same source of truth SCP's Phase 2
adopted).

These tests pin the integration: the canonical class is importable
from TMS's app layer + the substrate / SCP-only / TMS-only step
classifications behave correctly through it.

Pure-Python: no DB or mapper init needed.
"""

from __future__ import annotations

import os
import pathlib

# TMS's app.core.config requires a DATABASE_URL to import — set a
# benign placeholder so the test can import the canonical class.
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")


def test_provisioning_service_imports_canonical_classmethods() -> None:
    """The gate goes through Core's classmethods, not a local map."""
    from app.models.user_directive import ConfigProvisioningStatus

    assert hasattr(ConfigProvisioningStatus, "step_required_planes")
    assert hasattr(ConfigProvisioningStatus, "step_is_licensed")
    assert hasattr(ConfigProvisioningStatus, "STEP_REQUIRED_PLANES")


def test_provisioning_service_no_local_step_required_planes_dict() -> None:
    """TMS never carried a local map (this is the prevent-drift guard
    that would catch a regression where someone re-adds one)."""
    src = pathlib.Path(
        "/home/trevor/Documents/Autonomy-TMS/backend/app/services/provisioning_service.py"
    ).read_text()
    assert "_STEP_REQUIRED_PLANES" not in src, (
        "TMS provisioning_service contains a local _STEP_REQUIRED_PLANES "
        "symbol — must consume Core's canonical map via "
        "ConfigProvisioningStatus.step_is_licensed instead."
    )


def test_tms_only_tenant_runs_multi_plane_steps() -> None:
    """OR-semantics: multi-plane steps run when any required plane is
    licensed. A TMS-only tenant must be able to run
    `trm_load_pretrained`, `backtest_evaluation`, `decision_seed`,
    `site_tgnn` (each tagged with TMS in Core's map)."""
    from app.models.user_directive import ConfigProvisioningStatus

    tms_only = frozenset({"tms"})
    for step in [
        "trm_load_pretrained", "backtest_evaluation",
        "decision_seed", "site_tgnn",
    ]:
        assert ConfigProvisioningStatus.step_is_licensed(step, tms_only), step


def test_tms_only_tenant_skips_dp_forecast_steps() -> None:
    """A TMS-only tenant must NOT run DP-scoped forecast-pipeline
    steps — those are DP-exclusive."""
    from app.models.user_directive import ConfigProvisioningStatus

    tms_only = frozenset({"tms"})
    assert not ConfigProvisioningStatus.step_is_licensed(
        "lgbm_forecast", tms_only,
    )
    assert not ConfigProvisioningStatus.step_is_licensed(
        "demand_features", tms_only,
    )


def test_tms_only_tenant_skips_scp_supply_steps() -> None:
    """A TMS-only tenant must NOT run SCP-scoped supply-planning
    steps — those are SCP-exclusive (TMS doesn't have a supply
    planning model)."""
    from app.models.user_directive import ConfigProvisioningStatus

    tms_only = frozenset({"tms"})
    for step in [
        "supply_tgnn", "inventory_tgnn", "capacity_tgnn",
        "supply_plan", "rccp_validation",
    ]:
        assert not ConfigProvisioningStatus.step_is_licensed(step, tms_only), step


def test_substrate_steps_always_run_for_tms() -> None:
    """Substrate steps (warm_start, training_corpus, conformal,
    sop_graphsage, etc.) run regardless of plane licensing — they're
    cross-plane infrastructure."""
    from app.models.user_directive import ConfigProvisioningStatus

    tms_only = frozenset({"tms"})
    for step in [
        "warm_start", "training_corpus", "sop_graphsage",
        "cfa_optimization", "conformal", "briefing",
        "scenario_bootstrap", "market_intelligence",
    ]:
        assert ConfigProvisioningStatus.step_is_licensed(step, tms_only), step
