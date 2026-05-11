"""Tests for the Lane Volume Forecast tGNN head (GNN-3 first cut).

Structural tests run pure-Python (no torch / no torch-geometric / no
azirella-powell-core required). Trunk + forward-pass tests gate on
the full ML stack — they skip cleanly in the CPU sandbox.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest


_BACKEND = Path(__file__).resolve().parents[3]
_WORKSPACE = _BACKEND.parent.parent
for p in (
    str(_BACKEND),
    str(_BACKEND.parent / "packages" / "autonomy-tms-heuristics" / "src"),
    str(_WORKSPACE / "Autonomy-Core" / "packages" / "azirella-heuristics-common" / "src"),
    str(_WORKSPACE / "Autonomy-Core" / "packages" / "data-model" / "src"),
    str(_WORKSPACE / "Autonomy-Core" / "packages" / "azirella-demand-planning-contract" / "src"),
    str(_WORKSPACE / "Autonomy-Core" / "packages" / "azirella-transfer-order-envelope-contract" / "src"),
    str(_WORKSPACE / "Autonomy-Core" / "packages" / "powell-core" / "src"),
):
    if p not in sys.path:
        sys.path.insert(0, p)


# Other test modules in the suite stub ``app`` / ``app.services`` /
# ``app.services.powell`` in ``sys.modules`` to bypass the heavy powell
# package init. We need the real ``app.services.powell`` namespace to
# resolve our module under test — pop any leftover stubs so the lazy
# loader below sees a clean slate.
for _stale in ("app", "app.services", "app.services.powell"):
    mod = sys.modules.get(_stale)
    if mod is not None and not hasattr(mod, "__path__"):
        sys.modules.pop(_stale, None)


# Load the module under test directly to avoid the heavy
# ``app.services.powell.__init__`` triggering on collection.
_MODULE_PATH = (
    _BACKEND / "app" / "services" / "powell" / "lane_volume_forecast_tgnn.py"
)
for _stub in ("app", "app.services", "app.services.powell"):
    sys.modules.setdefault(_stub, ModuleType(_stub))
_spec = importlib.util.spec_from_file_location(
    "app.services.powell.lane_volume_forecast_tgnn", _MODULE_PATH,
)
_module = importlib.util.module_from_spec(_spec)
sys.modules["app.services.powell.lane_volume_forecast_tgnn"] = _module
_spec.loader.exec_module(_module)


LANE_VOLUME_NODE_FEATURES = _module.LANE_VOLUME_NODE_FEATURES
LANE_VOLUME_EDGE_FEATURES = _module.LANE_VOLUME_EDGE_FEATURES
DEFAULT_HORIZON_DAYS = _module.DEFAULT_HORIZON_DAYS
LaneVolumeForecast = _module.LaneVolumeForecast
LaneVolumeForecastBatch = _module.LaneVolumeForecastBatch
LaneVolumeForecastDataAdapter = _module.LaneVolumeForecastDataAdapter
build_lane_volume_forecast_tgnn = _module.build_lane_volume_forecast_tgnn
tensor_to_forecasts = _module.tensor_to_forecasts


# ─────────────────────────────────────────────────────────────────────
# Pure-Python feature-catalogue invariants
# ─────────────────────────────────────────────────────────────────────


def test_node_feature_catalogue_size() -> None:
    """12 node features per the substrate spec's example block."""
    assert len(LANE_VOLUME_NODE_FEATURES) == 12


def test_node_feature_catalogue_contents() -> None:
    """Pin the names so the data adapter and tests can't drift."""
    assert "historical_volume_p50" in LANE_VOLUME_NODE_FEATURES
    assert "season_sin" in LANE_VOLUME_NODE_FEATURES
    assert "season_cos" in LANE_VOLUME_NODE_FEATURES
    assert "carrier_otp_trailing" in LANE_VOLUME_NODE_FEATURES
    # Mode one-hot fields all present.
    for mode_field in ("mode_ftl", "mode_intermodal", "mode_ltl"):
        assert mode_field in LANE_VOLUME_NODE_FEATURES


def test_edge_feature_catalogue_size() -> None:
    """4 edge features per design."""
    assert len(LANE_VOLUME_EDGE_FEATURES) == 4


def test_default_horizon_is_tactical_week_count() -> None:
    """TACTICAL tier default = 8 days."""
    assert DEFAULT_HORIZON_DAYS == 8


# ─────────────────────────────────────────────────────────────────────
# LaneVolumeForecast dataclass invariants
# ─────────────────────────────────────────────────────────────────────


def test_lane_volume_forecast_constructs() -> None:
    f = LaneVolumeForecast(
        lane_id="LANE-1",
        horizon_days=(1, 2, 3),
        p10=(10.0, 11.0, 12.0),
        p50=(15.0, 16.0, 17.0),
        p90=(20.0, 21.0, 22.0),
        produced_at=datetime.now(timezone.utc),
        horizon_steps=3,
    )
    assert f.lane_id == "LANE-1"
    assert f.horizon_steps == 3


def test_lane_volume_forecast_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="must all have the same length"):
        LaneVolumeForecast(
            lane_id="LANE-1",
            horizon_days=(1, 2, 3),
            p10=(10.0,),
            p50=(15.0,),
            p90=(20.0,),
            produced_at=datetime.now(timezone.utc),
            horizon_steps=3,
        )


def test_lane_volume_forecast_rejects_horizon_step_mismatch() -> None:
    with pytest.raises(ValueError, match="disagrees with"):
        LaneVolumeForecast(
            lane_id="LANE-1",
            horizon_days=(1, 2, 3),
            p10=(10.0, 11.0, 12.0),
            p50=(15.0, 16.0, 17.0),
            p90=(20.0, 21.0, 22.0),
            produced_at=datetime.now(timezone.utc),
            horizon_steps=7,  # wrong
        )


def test_lane_volume_forecast_rejects_crossed_quantiles() -> None:
    with pytest.raises(ValueError, match="Quantile ordering violated"):
        LaneVolumeForecast(
            lane_id="LANE-1",
            horizon_days=(1, 2),
            p10=(10.0, 15.0),
            p50=(20.0, 10.0),     # P50 < P10 at index 1
            p90=(30.0, 30.0),
            produced_at=datetime.now(timezone.utc),
            horizon_steps=2,
        )


def test_producer_signature_stamped() -> None:
    f = LaneVolumeForecast(
        lane_id="LANE-1",
        horizon_days=(1,),
        p10=(0.0,), p50=(0.0,), p90=(0.0,),
        produced_at=datetime.now(timezone.utc),
        horizon_steps=1,
    )
    assert f.producer_signature == "tms:lane_volume_forecast_tgnn:v0.1.0"


# ─────────────────────────────────────────────────────────────────────
# Data adapter — v1 ships contract only; every fetch raises
# ─────────────────────────────────────────────────────────────────────


def test_data_adapter_constructs() -> None:
    adapter = LaneVolumeForecastDataAdapter(
        db=None, config_id=1, tenant_id=1,
    )
    assert adapter.config_id == 1
    assert adapter.tenant_id == 1
    assert adapter.history_buckets == 26
    assert adapter.horizon_buckets == DEFAULT_HORIZON_DAYS
    assert adapter.bucket_size_days == 7


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_data_adapter_v1_raises_for_lane_inventory() -> None:
    adapter = LaneVolumeForecastDataAdapter(db=None, config_id=1, tenant_id=1)
    with pytest.raises(NotImplementedError, match="GNN-3.5"):
        _run(adapter.lane_inventory())


def test_data_adapter_v1_raises_for_history_tensor() -> None:
    adapter = LaneVolumeForecastDataAdapter(db=None, config_id=1, tenant_id=1)
    with pytest.raises(NotImplementedError, match="GNN-3.5"):
        _run(adapter.history_tensor(["LANE-1"]))


def test_data_adapter_v1_raises_for_edge_sequence() -> None:
    adapter = LaneVolumeForecastDataAdapter(db=None, config_id=1, tenant_id=1)
    with pytest.raises(NotImplementedError, match="GNN-3.5"):
        _run(adapter.edge_sequence(["LANE-1"]))


def test_data_adapter_v1_raises_for_target_tensor() -> None:
    adapter = LaneVolumeForecastDataAdapter(db=None, config_id=1, tenant_id=1)
    with pytest.raises(NotImplementedError, match="GNN-3.5"):
        _run(adapter.target_tensor(["LANE-1"]))


def test_data_adapter_v1_raises_for_fetch_batch() -> None:
    adapter = LaneVolumeForecastDataAdapter(db=None, config_id=1, tenant_id=1)
    with pytest.raises(NotImplementedError, match="GNN-3.5"):
        _run(adapter.fetch_batch())


# ─────────────────────────────────────────────────────────────────────
# Trunk + forward — gate on the full ML stack.
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def gnn_stack_available() -> bool:
    try:
        import torch  # noqa: F401
        import torch_geometric  # noqa: F401
        import azirella_powell_core  # noqa: F401
        return True
    except ImportError:
        return False


def test_build_lane_volume_forecast_tgnn(gnn_stack_available: bool) -> None:
    if not gnn_stack_available:
        pytest.skip("torch + torch-geometric + azirella-powell-core not installed")
    import torch
    model = build_lane_volume_forecast_tgnn(horizon_steps=4, hidden_dim=32)
    assert model is not None
    # Forward-pass with toy tensors.
    T, N, F_node = 6, 5, len(LANE_VOLUME_NODE_FEATURES)
    F_edge = len(LANE_VOLUME_EDGE_FEATURES)
    E = 8
    x_seq = torch.randn(T, N, F_node)
    edge_index_seq = [torch.randint(0, N, (2, E)) for _ in range(T)]
    edge_attr_seq = [torch.randn(E, F_edge) for _ in range(T)]
    with torch.no_grad():
        out = model(x_seq, edge_index_seq, edge_attr_seq)
    # (N, horizon, 3)
    assert out.shape == (N, 4, 3)


def test_tensor_to_forecasts_round_trip(gnn_stack_available: bool) -> None:
    if not gnn_stack_available:
        pytest.skip("torch + torch-geometric + azirella-powell-core not installed")
    import torch
    pred = torch.tensor([
        # lane 0: (P10, P50, P90) per day, 2 horizon days
        [[10.0, 15.0, 20.0], [11.0, 16.0, 21.0]],
        # lane 1
        [[5.0, 8.0, 12.0], [6.0, 9.0, 13.0]],
    ])
    forecasts = tensor_to_forecasts(
        pred, ["LANE-A", "LANE-B"],
        horizon_offset_days=1,
        produced_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )
    assert len(forecasts) == 2
    assert forecasts[0].lane_id == "LANE-A"
    assert forecasts[0].horizon_days == (1, 2)
    assert forecasts[0].p10 == (10.0, 11.0)
    assert forecasts[0].p90 == (20.0, 21.0)
    assert forecasts[1].lane_id == "LANE-B"


def test_tensor_to_forecasts_sorts_crossed_quantiles(gnn_stack_available: bool) -> None:
    """Even if the head produces P10 > P50 (untrained / regression artefact),
    ``sort_quantiles=True`` (default) should clip to valid order."""
    if not gnn_stack_available:
        pytest.skip("torch + torch-geometric + azirella-powell-core not installed")
    import torch
    # Quantile crossings: P10=20, P50=15, P90=10 at index 0; valid at index 1.
    pred = torch.tensor([[[20.0, 15.0, 10.0], [10.0, 15.0, 20.0]]])
    forecasts = tensor_to_forecasts(pred, ["LANE-X"])
    assert forecasts[0].p10[0] == 10.0
    assert forecasts[0].p50[0] == 15.0
    assert forecasts[0].p90[0] == 20.0


def test_tensor_to_forecasts_rejects_wrong_shape(gnn_stack_available: bool) -> None:
    if not gnn_stack_available:
        pytest.skip("torch + torch-geometric + azirella-powell-core not installed")
    import torch
    with pytest.raises(ValueError, match="shape"):
        tensor_to_forecasts(torch.randn(3, 4), ["L1", "L2", "L3"])
    with pytest.raises(ValueError, match="shape"):
        tensor_to_forecasts(torch.randn(3, 4, 5), ["L1", "L2", "L3"])


def test_tensor_to_forecasts_rejects_lane_id_count_mismatch(
    gnn_stack_available: bool,
) -> None:
    if not gnn_stack_available:
        pytest.skip("torch + torch-geometric + azirella-powell-core not installed")
    import torch
    pred = torch.randn(3, 4, 3)
    with pytest.raises(ValueError, match="length"):
        tensor_to_forecasts(pred, ["LANE-1"])   # only 1 id for 3 lanes
