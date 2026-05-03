"""GraphSAGE Movement Planner — §3.38 Phase 3 scaffold.

This module ships the **interface scaffold** for the Phase 3
GraphSAGE-based Movement Planner specified in
``docs/TMS_DECISION_HIERARCHY.md`` §4.2:

    *Movement Planner GraphSAGE — analog of SCP's supply_planning_tgnn
    but with transport semantics: nodes = lanes + hubs, edges = mode
    alternatives, features = rate-card + distance + transit time.*

**The actual model is not trained here.** GraphSAGE training is a
multi-day workstream that requires:

1. **Training data**: tenant historical (lane, period, mode-split,
   carrier-assignment, observed-cost) tuples joined with rate-card
   snapshots. Data prep is in ``backend/scripts/pretraining/``.
2. **Model architecture**: PyTorch GNN with 2-3 GraphSAGE conv layers,
   mean-aggregator, sum-readout for plan-level cost prediction; or
   GATv2 for attention-weighted edge importance.
3. **Training loop**: minibatch sampling per (tenant, period); MSE
   loss on observed-cost vs. predicted; teacher-forced rollouts on
   the digital twin for policy-gradient finetune.
4. **Compute budget**: GPU training (~hours per tenant), checkpointed
   per ``training_run`` (Core's `powell_training_config` substrate).
5. **Evaluation**: held-out-period MAPE on cost prediction, mode-split
   accuracy, downstream plan utilisation.
6. **Deployment**: `inference_service` wired into
   ``MovementPlannerService.plan_movement(model_id=...)``.

This scaffold defines the **public interface** that the trained
model will plug into, so:

- The Phase 2A heuristic Movement Planner has a stable upgrade path
- Tests can exercise the scaffold's contract without GPU dependencies
- Phase 3 ML work is genuinely a separate workstream (model training
  + evaluation + deployment), not "code waiting to be written"

## Phase 3 work plan

1. **§3.41 Phase 3.1 — training data ETL**: build
   ``MovementPlannerTrainingDataExtractor`` that walks
   ``transportation_plan_item`` history joined with ``freight_charge``
   actuals + ``rate_card`` snapshots; emits training tuples.
2. **§3.41 Phase 3.2 — model architecture**: write
   ``GraphSAGEMovementPlannerModel`` (PyTorch). 2 conv layers, mean
   aggregator, MLP head per (mode, equipment) pair.
3. **§3.41 Phase 3.3 — training pipeline**: integrate with
   ``trm_trainer.py`` patterns; checkpoint per training run.
4. **§3.41 Phase 3.4 — inference service**: wire into MovementPlanner
   under a feature flag; A/B against Phase 2A heuristic.
5. **§3.41 Phase 3.5 — production rollout**: per-tenant calibration,
   monitoring (forecast drift, plan-utilisation regression), fall-back
   to Phase 2A on infrastructure failure.

Per CLAUDE.md the model code lives in ``packages/data-model/.../trm/``
(Core, with PyTorch-optional dependency) when its training matures
to cross-product utility; for Phase 3.1-3.4 it lives in this TMS
repo since the TRM is plane-specific.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class GraphSAGEPredictionInput:
    """Input batch for a single inference call.

    The Phase 3 GraphSAGE model takes a transport-graph snapshot
    (nodes = lanes + hubs; edges = mode alternatives) plus the
    forecast volumes per (lane, period) and returns recommended
    mode + equipment + carrier per item.
    """

    tenant_id: int
    config_id: int
    period_start: date
    period_days: int
    """Forecast period scope."""

    lane_volume_forecasts: List[Dict[str, Any]]
    """Per-lane forecast rows from §3.37 LaneVolumePlan, with
    (lane_id, mode, equipment_type, forecast_loads_p50, ...).
    Phase 3 will preprocess these into node features."""

    available_carriers: List[Dict[str, Any]]
    """List of (carrier_id, contract_id, rate_card_id, equipment_type,
    base_rate, capacity_remaining) tuples."""

    transit_time_distribution: Optional[Dict[int, Dict[str, float]]] = None
    """Per-lane transit-time distribution (p10/p50/p90 hours). Phase 3
    will read this from `LaneProfile` historical data."""


@dataclass(frozen=True)
class GraphSAGEPredictionOutput:
    """One prediction per plan item.

    The Phase 3 model emits, per item: a recommended (carrier_id,
    rate_id) pair and a confidence score; the Phase 2A heuristic gets
    a structurally compatible result so it can be the fallback when
    the model's confidence is low.
    """

    item_id: int
    carrier_id: Optional[int]
    rate_id: Optional[int]
    estimated_cost: Optional[float]
    confidence: float
    """Model's confidence in the assignment (0-1). When ``< threshold``
    the planner falls back to the Phase 2A heuristic."""

    rationale: Dict[str, Any] = field(default_factory=dict)
    """Model-emitted explanations: top-K node attentions, alternative
    carriers considered, etc. Useful for AIIO override-with-reasoning."""


class GraphSAGEMovementPlannerModel(ABC):
    """Abstract Phase 3 model interface.

    Real implementations live under ``packages/data-model/.../trm/``
    (PyTorch GNN; Phase 3.2 deliverable). Phase 2A consumers can
    instantiate ``NotYetImplementedModel`` to exercise the scaffold's
    contract without a trained model.
    """

    @abstractmethod
    def fit(self, training_data: List[Dict[str, Any]]) -> None:
        """Train the model on historical (lane, period, observed-cost)
        tuples. Phase 3.3 deliverable."""

    @abstractmethod
    def predict(
        self, inputs: GraphSAGEPredictionInput,
    ) -> List[GraphSAGEPredictionOutput]:
        """Score per-item assignment recommendations. Phase 3.4
        deliverable."""

    @abstractmethod
    def model_version(self) -> str:
        """Unique version identifier (typically a checkpoint hash)
        persisted on `TransportationPlan.optimization_metadata` so
        consumers can audit which model version produced a plan."""


class NotYetImplementedModel(GraphSAGEMovementPlannerModel):
    """Phase 3 scaffold sentinel.

    Raises ``NotImplementedError`` on every method. Used in tests to
    verify the scaffold's contract. Phase 3.2 will replace this with
    the real PyTorch GNN.
    """

    def fit(self, training_data: List[Dict[str, Any]]) -> None:
        raise NotImplementedError(
            "GraphSAGE Phase 3 model — training not yet implemented. "
            "See MIGRATION_REGISTER.md §3.38 'Phase 3 work plan'."
        )

    def predict(
        self, inputs: GraphSAGEPredictionInput,
    ) -> List[GraphSAGEPredictionOutput]:
        raise NotImplementedError(
            "GraphSAGE Phase 3 model — inference not yet implemented. "
            "Use MovementPlannerService Phase 2A heuristic until §3.41 "
            "Phase 3.4 deliverable lands."
        )

    def model_version(self) -> str:
        return "graphsage_not_yet_implemented"


# ===========================================================================
# §3.41 Phase 3.2 — Real PyTorch GraphSAGE implementation
# ===========================================================================


class TorchGraphSAGEMovementPlanner(GraphSAGEMovementPlannerModel):
    """Real PyTorch GraphSAGE model for the Movement Planner.

    Architecture:

    - 2 ``SAGEConv`` layers (``torch_geometric.nn.SAGEConv``) with mean
      aggregator, ``relu`` between, hidden_dim=64.
    - Per-(item, carrier) MLP scoring head: takes (item-node embedding
      + carrier-node embedding + edge feature) → cost-prediction
      scalar.
    - Loss: MSE on (predicted_cost − observed_cost) when observed cost
      available; falls back to MSE on (predicted − action_estimated)
      for items without observed actuals (semi-supervised).

    Graph construction (per inference call):

    - Nodes: union of (lanes appearing in the forecast) + (carriers in
      the candidate set).
    - Edges: lane↔carrier when the carrier has at least one rate card
      that matches the lane (an "this carrier could serve this lane"
      relationship).
    - Edge features: (rate_basis_one_hot, base_rate, distance_miles,
      mode_compatibility_one_hot).

    Phase 3.2 is the model **class** + training/inference plumbing.
    Production training (multi-day GPU run, hyperparameter search,
    held-out evaluation) is §3.41 Phase 3.5.

    Dependencies:

    - ``torch>=2.0`` — already in TMS requirements.
    - ``torch_geometric>=2.5`` — already in TMS requirements (used
      elsewhere; see e.g. SCP supply_planning_tgnn).

    Imports are lazy so test fixtures without GPU + torch_geometric
    can still load the rest of this module.
    """

    HIDDEN_DIM = 64
    NUM_CONV_LAYERS = 2
    DEFAULT_LR = 1e-3
    DEFAULT_BATCH_SIZE = 64

    def __init__(
        self,
        *,
        hidden_dim: int = HIDDEN_DIM,
        num_conv_layers: int = NUM_CONV_LAYERS,
        learning_rate: float = DEFAULT_LR,
        device: Optional[str] = None,
    ) -> None:
        self.hidden_dim = hidden_dim
        self.num_conv_layers = num_conv_layers
        self.learning_rate = learning_rate
        self.device = device  # 'cuda' / 'cpu' / None (auto)
        self._model = None  # Built lazily during fit()
        self._version = "graphsage_untrained"
        self._optimizer = None
        self._loss_history: List[float] = []

    # ------------------------------------------------------------------
    # Build the underlying torch.nn.Module lazily
    # ------------------------------------------------------------------

    def _build_model(self, num_node_features: int, num_edge_features: int):
        """Construct the GNN. Lazy import of torch / torch_geometric so
        the module loads in environments that don't have them."""
        import torch
        import torch.nn as nn
        from torch_geometric.nn import SAGEConv

        class _GraphSAGEModel(nn.Module):
            def __init__(self, in_dim: int, hidden_dim: int, edge_dim: int, n_layers: int):
                super().__init__()
                self.convs = nn.ModuleList()
                self.convs.append(SAGEConv(in_dim, hidden_dim, aggr="mean"))
                for _ in range(n_layers - 1):
                    self.convs.append(
                        SAGEConv(hidden_dim, hidden_dim, aggr="mean"),
                    )
                # Per-(item, carrier) MLP head
                self.scorer = nn.Sequential(
                    nn.Linear(hidden_dim * 2 + edge_dim, hidden_dim),
                    nn.ReLU(),
                    nn.Linear(hidden_dim, 1),
                )

            def forward(self, x, edge_index, edge_attr, item_idx, carrier_idx):
                """``x``: node features ``[N, in_dim]``;
                ``edge_index``: ``[2, E]``; ``edge_attr``: ``[E, edge_dim]``;
                ``item_idx``: ``[B]`` indices of items in the batch;
                ``carrier_idx``: ``[B]`` indices of carriers in the batch.

                Returns predicted cost ``[B, 1]`` per (item, carrier)
                pair.
                """
                h = x
                for conv in self.convs:
                    h = conv(h, edge_index)
                    h = torch.relu(h)
                # Per-pair edge feature is selected by aligning item_idx
                # / carrier_idx with edge_index. Phase 3.2 simplification:
                # callers pass edge_attr matching the item/carrier
                # ordering; production training will use a proper
                # bipartite-batch loader.
                pair_features = torch.cat([
                    h[item_idx],
                    h[carrier_idx],
                    edge_attr,
                ], dim=-1)
                return self.scorer(pair_features)

        return _GraphSAGEModel(
            in_dim=num_node_features,
            hidden_dim=self.hidden_dim,
            edge_dim=num_edge_features,
            n_layers=self.num_conv_layers,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fit(self, training_data: List[Dict[str, Any]]) -> None:
        """Train the model on a list of training examples.

        Phase 3.2 expects ``training_data`` to be a list of dicts with
        ``node_features``, ``edge_index``, ``edge_attr``,
        ``item_carrier_pairs``, ``observed_costs``. Phase 3.3 wires the
        :class:`MovementPlannerTrainingDataExtractor` output into this
        shape via a ``MovementPlannerTrainer`` orchestrator.

        For Phase 3.2 (this commit), training is single-batch full-graph
        SGD. Production training uses minibatch sampling + held-out
        validation; that's Phase 3.3 / 3.5.
        """
        if not training_data:
            self._version = "graphsage_no_training_data"
            return

        import torch

        # Pull dimensions from the first example so the model knows its
        # input/edge feature widths.
        first = training_data[0]
        node_features = first["node_features"]
        edge_attr = first["edge_attr"]
        if hasattr(node_features, "shape"):
            num_node_features = node_features.shape[-1]
        else:
            num_node_features = len(node_features[0])
        if hasattr(edge_attr, "shape"):
            num_edge_features = edge_attr.shape[-1]
        else:
            num_edge_features = len(edge_attr[0])

        self._model = self._build_model(num_node_features, num_edge_features)
        self._optimizer = torch.optim.Adam(
            self._model.parameters(), lr=self.learning_rate,
        )

        device = self.device
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model.to(device)

        self._model.train()
        loss_history: List[float] = []

        for example in training_data:
            x = self._as_tensor(example["node_features"]).to(device)
            edge_index = self._as_tensor(
                example["edge_index"], dtype=torch.long,
            ).to(device)
            edge_attr_t = self._as_tensor(example["edge_attr"]).to(device)
            pairs = example["item_carrier_pairs"]
            item_idx = self._as_tensor(
                [p[0] for p in pairs], dtype=torch.long,
            ).to(device)
            carrier_idx = self._as_tensor(
                [p[1] for p in pairs], dtype=torch.long,
            ).to(device)
            observed = self._as_tensor(example["observed_costs"]).to(device)

            self._optimizer.zero_grad()
            pred = self._model(
                x, edge_index, edge_attr_t, item_idx, carrier_idx,
            ).squeeze(-1)
            loss = torch.nn.functional.mse_loss(pred, observed)
            loss.backward()
            self._optimizer.step()
            loss_history.append(float(loss.item()))

        self._loss_history = loss_history
        # Version-stamp by the final loss + step count (Phase 3.5 will
        # use a proper checkpoint hash).
        if loss_history:
            final_loss = loss_history[-1]
            self._version = (
                f"graphsage_trained_steps={len(loss_history)}_"
                f"final_loss={final_loss:.4f}"
            )
        else:
            self._version = "graphsage_no_training_steps"

    def predict(
        self, inputs: GraphSAGEPredictionInput,
    ) -> List[GraphSAGEPredictionOutput]:
        """Score per-item assignment recommendations.

        Phase 3.2 runs a single forward pass over the constructed
        graph. ``inputs.lane_volume_forecasts`` + ``inputs.available_
        carriers`` are converted into node + edge tensors via
        :meth:`_inputs_to_graph_tensors`. The MLP scoring head emits
        a predicted cost per (item, carrier) pair; we pick the
        argmin-cost carrier per item.

        For tests / production scenarios where training hasn't run,
        the model returns the Phase 2A-heuristic carrier choice with
        ``confidence=0.0`` so consumers can detect the untrained
        state.
        """
        if self._model is None:
            return [
                GraphSAGEPredictionOutput(
                    item_id=int(forecast.get("item_id", i)),
                    carrier_id=None,
                    rate_id=None,
                    estimated_cost=None,
                    confidence=0.0,
                    rationale={
                        "reason": "model_not_trained",
                        "fallback": "use_phase_2a_heuristic",
                    },
                )
                for i, forecast in enumerate(inputs.lane_volume_forecasts)
            ]

        import torch

        graph = self._inputs_to_graph_tensors(inputs)
        if graph is None:
            return []

        device = next(self._model.parameters()).device
        x, edge_index, edge_attr, pair_idx_pairs, item_id_per_pair = graph
        x = x.to(device)
        edge_index = edge_index.to(device)
        edge_attr = edge_attr.to(device)
        item_idx = torch.tensor(
            [p[0] for p in pair_idx_pairs], dtype=torch.long, device=device,
        )
        carrier_idx = torch.tensor(
            [p[1] for p in pair_idx_pairs], dtype=torch.long, device=device,
        )

        self._model.eval()
        with torch.no_grad():
            pred = self._model(
                x, edge_index, edge_attr, item_idx, carrier_idx,
            ).squeeze(-1)
        costs = pred.cpu().numpy()

        # Group by item, pick min-cost carrier per item
        from collections import defaultdict
        per_item: Dict[int, List[tuple]] = defaultdict(list)
        for k, (item_node, carrier_node) in enumerate(pair_idx_pairs):
            per_item[item_id_per_pair[k]].append(
                (float(costs[k]), inputs.available_carriers[carrier_node - len(inputs.lane_volume_forecasts)]),
            )

        outputs: List[GraphSAGEPredictionOutput] = []
        for item_id, candidates in per_item.items():
            if not candidates:
                continue
            candidates.sort(key=lambda pair: pair[0])
            best_cost, best_carrier = candidates[0]
            outputs.append(GraphSAGEPredictionOutput(
                item_id=item_id,
                carrier_id=int(best_carrier["carrier_id"]),
                rate_id=best_carrier.get("rate_card_id"),
                estimated_cost=best_cost,
                confidence=self._confidence_score(candidates),
                rationale={
                    "model_version": self._version,
                    "alternatives": [
                        {"carrier_id": int(c["carrier_id"]), "predicted_cost": float(p)}
                        for p, c in candidates[:3]
                    ],
                },
            ))
        return outputs

    def model_version(self) -> str:
        return self._version

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _inputs_to_graph_tensors(self, inputs: GraphSAGEPredictionInput):
        """Convert the prediction-input dataclass to graph tensors.

        Phase 3.2 graph: bipartite (items × carriers).
        Items are nodes [0, n_items); carriers are nodes [n_items, n_items + n_carriers).
        """
        if not inputs.lane_volume_forecasts or not inputs.available_carriers:
            return None
        try:
            import torch
        except ImportError:
            return None

        n_items = len(inputs.lane_volume_forecasts)
        n_carriers = len(inputs.available_carriers)
        # Node features: simple 4-feature embedding
        # (loads_p50, mode_idx, equipment_idx, is_item)
        node_features = torch.zeros((n_items + n_carriers, 4))
        for i, forecast in enumerate(inputs.lane_volume_forecasts):
            node_features[i, 0] = float(forecast.get("forecast_loads_p50", 0))
            node_features[i, 1] = self._mode_to_idx(forecast.get("mode"))
            node_features[i, 2] = self._equipment_to_idx(
                forecast.get("equipment_type"),
            )
            node_features[i, 3] = 1.0  # is_item flag
        for j, carrier in enumerate(inputs.available_carriers):
            node_features[n_items + j, 0] = float(carrier.get("capacity_remaining", 0))
            node_features[n_items + j, 3] = 0.0  # is_carrier flag (not item)

        # Edges: every item ↔ every carrier (Phase 3.2 fully-connected
        # bipartite; Phase 3.5 prunes by rate-card existence).
        edge_index = torch.zeros((2, n_items * n_carriers * 2), dtype=torch.long)
        edge_attr = torch.zeros((n_items * n_carriers * 2, 3))
        # Edge features: (base_rate, capacity_remaining, _padding)
        pair_idx_pairs = []
        item_id_per_pair = []
        e = 0
        for i, forecast in enumerate(inputs.lane_volume_forecasts):
            for j, carrier in enumerate(inputs.available_carriers):
                # Forward edge i → carrier_node
                edge_index[0, e] = i
                edge_index[1, e] = n_items + j
                edge_attr[e, 0] = float(carrier.get("base_rate", 0))
                edge_attr[e, 1] = float(carrier.get("capacity_remaining", 0))
                e += 1
                # Reverse edge for SAGEConv message-passing symmetry
                edge_index[0, e] = n_items + j
                edge_index[1, e] = i
                edge_attr[e, 0] = float(carrier.get("base_rate", 0))
                edge_attr[e, 1] = float(carrier.get("capacity_remaining", 0))
                e += 1
                # Track (item_node_idx, carrier_node_idx) for scoring
                pair_idx_pairs.append((i, n_items + j))
                item_id_per_pair.append(int(forecast.get("item_id", i)))

        return node_features, edge_index, edge_attr, pair_idx_pairs, item_id_per_pair

    @staticmethod
    def _mode_to_idx(mode) -> float:
        return {
            "FTL": 0.0, "LTL": 1.0, "PARCEL": 2.0, "INTERMODAL": 3.0,
            "OCEAN": 4.0, "RAIL": 5.0, "AIR": 6.0,
        }.get(mode or "FTL", 0.0)

    @staticmethod
    def _equipment_to_idx(equipment_type) -> float:
        return {
            "DRY_VAN": 0.0, "REEFER": 1.0, "FLATBED": 2.0, "TANKER": 3.0,
            "CONTAINER_20": 4.0, "CONTAINER_40": 5.0,
        }.get(equipment_type, -1.0)

    @staticmethod
    def _as_tensor(x, dtype=None):
        import torch
        if hasattr(x, "shape"):  # already a tensor or numpy array
            t = torch.as_tensor(x)
        else:
            t = torch.tensor(x)
        if dtype is not None:
            t = t.to(dtype=dtype)
        else:
            if t.dtype not in (torch.float32, torch.float64):
                t = t.float()
        return t

    @staticmethod
    def _confidence_score(candidates: List[tuple]) -> float:
        """Confidence proxy: 1 − (best_cost / second_best_cost). When
        cheapest candidate is much better than runner-up, confidence
        is near 1.0; when they're tied, near 0.0.
        """
        if len(candidates) < 2:
            return 0.5  # No alternative to compare against
        best = candidates[0][0]
        second = candidates[1][0]
        if second <= 0:
            return 0.5
        return max(0.0, min(1.0, 1.0 - best / second))


__all__ = [
    "GraphSAGEMovementPlannerModel",
    "GraphSAGEPredictionInput",
    "GraphSAGEPredictionOutput",
    "NotYetImplementedModel",
    "TorchGraphSAGEMovementPlanner",
]
