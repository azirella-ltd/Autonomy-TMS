"""TMS Lane Volume Forecast tGNN head (GNN-3 first cut).

First TMS-shape tGNN built against
:mod:`azirella_powell_core.gnn.tGNNScaffolding`. Closes the
"GNN-3" stage of [TMS_POWELL_GNN_REWRITE.md §5](../../../../docs/TMS_POWELL_GNN_REWRITE.md)
in scaffolding form — the head module, output dataclass, feature
specs, and training-data adapter contract land here. v2 fills in
the data-adapter ETL.

Architecture (Layer 3 Tactical, daily cadence):

    Input  — sequence of T past per-lane snapshots
    Trunk  — azirella_powell_core.gnn.tGNNScaffolding
             (GraphSAGE per snapshot → Transformer over time)
    Head   — per-(lane, day) (P10, P50, P90) Linear head
    Output — LaneVolumeForecast dataclass per lane

Spec — POWELL_GNN_SUBSTRATE.md §4.2 example block.

Node = lane bucket; node features are 12-dim per
``LANE_VOLUME_NODE_FEATURES``.

Edges connect lanes that share origin, destination, or product —
substitution / contagion signal. Edge features are 4-dim per
``LANE_VOLUME_EDGE_FEATURES``.

torch + torch-geometric required (via the ``[gnn]`` extra of
``azirella-powell-core``). The structural layer above the import
boundary is pure Python so tests can exercise it on a CPU sandbox
without the heavy deps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable, List, Sequence, Tuple

if TYPE_CHECKING:  # pragma: no cover
    import torch
    from torch import Tensor, nn


# ─────────────────────────────────────────────────────────────────────
# Feature catalogue — pinned tuples so tests + data adapter agree on
# the order the trunk receives.
# ─────────────────────────────────────────────────────────────────────


LANE_VOLUME_NODE_FEATURES: Tuple[str, ...] = (
    # Historical volume signal.
    "historical_volume_p50",       # trailing-window median load count
    "volume_cv",                   # coefficient of variation
    # Calendar phase (PR-4 seasonal observation pair).
    "season_sin",
    "season_cos",
    "is_peak_season",              # 0 / 1 indicator
    # Carrier reliability signals.
    "lane_acceptance_rate",        # historical tender accept %
    "carrier_otp_trailing",        # on-time delivery %
    # Lane physical capacity.
    "dock_capacity_target",        # destination dock throughput target
    "equipment_initial_count",     # origin trailer fleet size
    # Mode one-hot (FTL / Intermodal / LTL).
    "mode_ftl",
    "mode_intermodal",
    "mode_ltl",
)


LANE_VOLUME_EDGE_FEATURES: Tuple[str, ...] = (
    "edge_origin_shared",          # same origin site
    "edge_dest_shared",            # same destination site
    "edge_product_shared",         # same product across lanes
    "inverse_distance",            # proximity weight in [0, 1]
)


DEFAULT_HORIZON_DAYS = 8           # TACTICAL tier default
DEFAULT_HIDDEN_DIM = 64
DEFAULT_SPATIAL_LAYERS = 2
DEFAULT_TEMPORAL_LAYERS = 2
DEFAULT_ATTENTION_HEADS = 4


# ─────────────────────────────────────────────────────────────────────
# Output dataclass — pure Python.
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LaneVolumeForecast:
    """Per-lane forecast emitted by the tGNN head."""

    lane_id: str
    horizon_days: Tuple[int, ...]              # offsets from ``produced_at``
    p10: Tuple[float, ...]
    p50: Tuple[float, ...]
    p90: Tuple[float, ...]
    produced_at: datetime
    horizon_steps: int
    # Stamped on every forecast so downstream consumers can route
    # between Phase-1 stub / Phase-2 fitted / GNN-3 quantile outputs.
    producer_signature: str = "tms:lane_volume_forecast_tgnn:v0.1.0"

    def __post_init__(self) -> None:
        if not (len(self.horizon_days) == len(self.p10) == len(self.p50) == len(self.p90)):
            raise ValueError(
                "horizon_days / p10 / p50 / p90 must all have the same length"
            )
        if self.horizon_steps != len(self.horizon_days):
            raise ValueError(
                f"horizon_steps={self.horizon_steps} disagrees with "
                f"len(horizon_days)={len(self.horizon_days)}"
            )
        for p10, p50, p90 in zip(self.p10, self.p50, self.p90):
            if not (p10 <= p50 <= p90):
                raise ValueError(
                    f"Quantile ordering violated: P10={p10}, P50={p50}, P90={p90}"
                )


# ─────────────────────────────────────────────────────────────────────
# Head module factory — torch-gated.
# ─────────────────────────────────────────────────────────────────────


def build_lane_volume_forecast_tgnn(
    horizon_steps: int = DEFAULT_HORIZON_DAYS,
    hidden_dim: int = DEFAULT_HIDDEN_DIM,
    spatial_layers: int = DEFAULT_SPATIAL_LAYERS,
    temporal_layers: int = DEFAULT_TEMPORAL_LAYERS,
    attention_heads: int = DEFAULT_ATTENTION_HEADS,
    dropout: float = 0.1,
) -> "nn.Module":
    """Instantiate the Lane Volume Forecast tGNN.

    Returns an ``nn.Module`` whose ``forward(x_seq, edge_index_seq,
    edge_attr_seq)`` returns a tensor of shape ``(N, horizon, 3)``
    where the trailing axis carries (P10, P50, P90) per lane × day.

    Quantile-ordering enforcement is the caller's concern at inference
    time — the linear head does not enforce ``p10 ≤ p50 ≤ p90``. A
    typical training loss is pinball loss or huberized quantile loss;
    inference clips post-hoc via ``torch.sort`` along the last axis.
    """
    # Import is local so the structural layer above stays import-cheap.
    from azirella_powell_core.gnn import (
        EdgeFeatureSpec,
        NodeFeatureSpec,
        tGNNScaffolding,
    )
    from torch import nn

    node_spec = NodeFeatureSpec(
        node_dim=len(LANE_VOLUME_NODE_FEATURES),
        node_type_vocab=("lane",),
    )
    edge_spec = EdgeFeatureSpec(
        edge_dim=len(LANE_VOLUME_EDGE_FEATURES),
        edge_type_vocab=("origin_shared", "dest_shared", "product_shared"),
    )

    def _quantile_head(hidden: int, _horizon: int) -> "nn.Module":
        # Three quantiles per (lane, day). ``_horizon`` ignored — the
        # tGNNScaffolding broadcasts the head across the horizon axis.
        return nn.Linear(hidden, 3)

    return tGNNScaffolding(
        node_spec=node_spec,
        edge_spec=edge_spec,
        hidden_dim=hidden_dim,
        spatial_layers=spatial_layers,
        temporal_layers=temporal_layers,
        attention_heads=attention_heads,
        horizon_steps=horizon_steps,
        dropout=dropout,
        output_head_factory=_quantile_head,
    )


def tensor_to_forecasts(
    pred: "Tensor",
    lane_ids: Sequence[str],
    *,
    horizon_offset_days: int = 1,
    produced_at: datetime | None = None,
    sort_quantiles: bool = True,
) -> List[LaneVolumeForecast]:
    """Convert raw model output to a list of ``LaneVolumeForecast``.

    Args:
      pred: tensor of shape ``(N, horizon, 3)``.
      lane_ids: ``N``-length sequence of lane identifiers; index in
        the list aligns with the first axis of ``pred``.
      horizon_offset_days: day offset of the first horizon step from
        ``produced_at``. Defaults to ``1`` (forecast starts tomorrow).
      produced_at: timestamp stamped on every forecast. Defaults to
        ``datetime.now(timezone.utc)``.
      sort_quantiles: when ``True`` (default), sorts the last axis so
        ``p10 ≤ p50 ≤ p90`` even if the trained head produced
        crossed quantiles. Set ``False`` to surface crossings as a
        ``ValueError`` from ``LaneVolumeForecast.__post_init__``.
    """
    import torch

    if pred.dim() != 3 or pred.shape[-1] != 3:
        raise ValueError(
            f"pred must have shape (N, horizon, 3); got {tuple(pred.shape)}"
        )
    n, horizon, _ = pred.shape
    if n != len(lane_ids):
        raise ValueError(
            f"pred has N={n}, but lane_ids has length {len(lane_ids)}"
        )
    if produced_at is None:
        produced_at = datetime.now(timezone.utc)

    if sort_quantiles:
        pred = torch.sort(pred, dim=-1).values

    pred_cpu = pred.detach().cpu().tolist()
    horizon_days = tuple(horizon_offset_days + i for i in range(horizon))

    forecasts: List[LaneVolumeForecast] = []
    for lane_idx, lane_id in enumerate(lane_ids):
        per_lane = pred_cpu[lane_idx]
        p10 = tuple(float(row[0]) for row in per_lane)
        p50 = tuple(float(row[1]) for row in per_lane)
        p90 = tuple(float(row[2]) for row in per_lane)
        forecasts.append(LaneVolumeForecast(
            lane_id=lane_id,
            horizon_days=horizon_days,
            p10=p10,
            p50=p50,
            p90=p90,
            produced_at=produced_at,
            horizon_steps=horizon,
        ))
    return forecasts


# ─────────────────────────────────────────────────────────────────────
# Training-data adapter — skeleton.
#
# v1 (this PR) ships the contract: every method raises
# ``NotImplementedError`` with a clear message about what v2 needs to
# do. v2 lands the ETL — query TransferOrderLineItem per lane × bucket,
# build the graph edges, etc.
#
# This is the seam GNN-3.5 wires up. Keeps the head module
# independently mergeable + testable from the ERP-side query work.
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LaneVolumeForecastBatch:
    """One training batch — ready-to-go tensors for the head."""

    x_seq: "Tensor"                 # (T, N, len(LANE_VOLUME_NODE_FEATURES))
    edge_index_seq: "List[Tensor]"  # T-length list of (2, E_t) tensors
    edge_attr_seq: "List[Tensor]"   # T-length list of (E_t, edge_dim)
    y_seq: "Tensor"                 # (N, horizon, 3) — quantile targets
    lane_ids: Tuple[str, ...]
    history_buckets: int            # T
    horizon_buckets: int            # horizon


class LaneVolumeForecastDataAdapter:
    """Pulls TMS-shape training tensors for the tGNN trunk.

    v1 (GNN-3 first cut, 2026-05-11): contract only. Methods raise
    ``NotImplementedError`` with v2-implementation guidance.

    v2 (GNN-3.5, planned): real queries against ``TransferOrderLineItem``
    + ``TransportationLane`` + ``SeasonalEnvelope`` ORMs. Bucket size
    = 1 day (EXECUTION tier) or 7 days (TACTICAL tier).
    """

    def __init__(
        self,
        db: Any,                       # AsyncSession; typed Any so the
                                       # module imports cheap.
        config_id: int,
        tenant_id: int,
        history_buckets: int = 26,     # ~half a year of weeks for tactical
        horizon_buckets: int = DEFAULT_HORIZON_DAYS,
        bucket_size_days: int = 7,     # TACTICAL default
    ) -> None:
        self.db = db
        self.config_id = int(config_id)
        self.tenant_id = int(tenant_id)
        self.history_buckets = int(history_buckets)
        self.horizon_buckets = int(horizon_buckets)
        self.bucket_size_days = int(bucket_size_days)

    async def lane_inventory(self) -> List[str]:
        """Return ``N`` lane_ids in the config.

        v2: ``SELECT id FROM transportation_lane WHERE config_id = :cfg
        ORDER BY id``. Returns ``lane_series_key(origin, dest)`` so
        downstream calls can join back to the canonical key.
        """
        raise NotImplementedError(
            "v1 ships head + contract; lane inventory query lands in GNN-3.5"
        )

    async def history_tensor(self, lane_ids: Sequence[str]) -> "Tensor":
        """Return ``(history_buckets, N, len(LANE_VOLUME_NODE_FEATURES))``
        per-bucket feature tensor.

        v2: per lane × bucket, aggregate ``TransferOrderLineItem``
        rows shipped in that bucket; join carrier scorecard for OTP /
        accept-rate trailing windows; compute conformal volume p50 +
        CV; populate season sin/cos from ``bucket_start.day_of_year``.
        """
        raise NotImplementedError(
            "v1 ships head + contract; history-tensor ETL lands in GNN-3.5"
        )

    async def edge_sequence(
        self,
        lane_ids: Sequence[str],
    ) -> Tuple["List[Tensor]", "List[Tensor]"]:
        """Return paired ``(edge_index_seq, edge_attr_seq)`` lists of
        length ``history_buckets``.

        v2: edges encode origin-sharing / destination-sharing /
        product-sharing per snapshot. Edges are constant across time
        for a static-config network, but the bucketed shape keeps
        the contract uniform with seasonal network reconfigurations
        (e.g. peak-season pop-up DCs).
        """
        raise NotImplementedError(
            "v1 ships head + contract; edge-sequence ETL lands in GNN-3.5"
        )

    async def target_tensor(self, lane_ids: Sequence[str]) -> "Tensor":
        """Return ``(N, horizon_buckets, 3)`` quantile targets for
        the next ``horizon_buckets`` periods.

        v2: per lane × forward bucket, aggregate realised
        ``TransferOrderLineItem`` volume + compute empirical
        quantiles over a rolling window. For backtest mode, query
        the held-out future periods; for forecast mode, return zeros
        (targets unknown — inference only).
        """
        raise NotImplementedError(
            "v1 ships head + contract; target-tensor ETL lands in GNN-3.5"
        )

    async def fetch_batch(self) -> LaneVolumeForecastBatch:
        """Convenience: assembles one ``LaneVolumeForecastBatch`` end
        to end.

        v2: call ``lane_inventory`` → ``history_tensor`` /
        ``edge_sequence`` / ``target_tensor`` and pack.
        """
        raise NotImplementedError(
            "v1 ships head + contract; full-batch assembly lands in GNN-3.5"
        )
