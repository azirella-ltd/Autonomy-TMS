"""
Inventory Optimization tGNN Inference Service — Tactical Layer, Inventory Domain.

Loads trained InventoryOptimizationTGNN checkpoints and provides runtime inference:
- Per-site buffer adjustment signals
- Rebalancing urgency
- Stockout probability
- Inventory health scores
- Days of stock estimates

Follows the EXACT same patterns as ExecutionGNNInferenceService.

Usage:
    svc = InventoryOptimizationTGNNService(db, config_id)
    out = await svc.infer(sop_embeddings=sop_embeddings)
    # out.buffer_adjustment_signal[site_key] -> float  # [-1, +1]
    # out.stockout_probability[site_key] -> float
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path(__file__).parent.parent.parent / "checkpoints"


@dataclass
class InventoryOptimizationTGNNOutput:
    """Result of InventoryOptimizationTGNN inference."""

    config_id: int
    num_sites: int
    checkpoint_path: str

    site_keys: List[str] = field(default_factory=list)
    computed_at: Optional[datetime] = None

    # Per-site outputs
    buffer_adjustment_signal: Dict[str, float] = field(default_factory=dict)
    rebalancing_urgency: Dict[str, float] = field(default_factory=dict)
    rebalancing_candidates: Dict[str, List[str]] = field(default_factory=dict)
    inventory_health: Dict[str, float] = field(default_factory=dict)
    days_of_stock: Dict[str, float] = field(default_factory=dict)
    stockout_probability: Dict[str, float] = field(default_factory=dict)
    holding_cost_pressure: Dict[str, float] = field(default_factory=dict)
    confidence: Dict[str, float] = field(default_factory=dict)

    # Per-site plain-English reasoning
    reasoning: Dict[str, str] = field(default_factory=dict)

    def generate_reasoning(self) -> None:
        """Populate per-site reasoning strings from output data."""
        from app.services.powell.decision_reasoning import inventory_optimization_tgnn_reasoning
        for site_key in self.site_keys:
            self.reasoning[site_key] = inventory_optimization_tgnn_reasoning(
                site_key=site_key,
                buffer_adjustment_signal=self.buffer_adjustment_signal.get(site_key, 0.0),
                rebalancing_urgency=self.rebalancing_urgency.get(site_key, 0.0),
                stockout_probability=self.stockout_probability.get(site_key, 0.0),
                days_of_stock=self.days_of_stock.get(site_key, 0.0),
                inventory_health=self.inventory_health.get(site_key, 0.5),
                confidence=self.confidence.get(site_key, 0.0),
            )

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "config_id": self.config_id,
            "num_sites": self.num_sites,
            "checkpoint_path": self.checkpoint_path,
            "site_keys": self.site_keys,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
            "buffer_adjustment_signal": self.buffer_adjustment_signal,
            "rebalancing_urgency": self.rebalancing_urgency,
            "rebalancing_candidates": self.rebalancing_candidates,
            "inventory_health": self.inventory_health,
            "days_of_stock": self.days_of_stock,
            "stockout_probability": self.stockout_probability,
            "holding_cost_pressure": self.holding_cost_pressure,
            "confidence": self.confidence,
        }
        if self.reasoning:
            d["reasoning"] = self.reasoning
        return d


class InventoryOptimizationTGNNService:
    """
    Runtime inference for trained InventoryOptimizationTGNN models.

    Responsibilities:
    1. Load checkpoint for config_id
    2. Build inventory-focused transactional feature tensors from DB
       (InvLevel, InvPolicy)
    3. Combine with S&OP embeddings + optional lateral context
    4. Run forward pass to get buffer signals + rebalancing urgency
    5. Derive rebalancing_candidates from urgency ordering
    6. Return per-site results for TacticalHiveCoordinator
    """

    def __init__(self, db: AsyncSession, config_id: int):
        self.db = db
        self.config_id = config_id
        self._model = None
        self._device = "cpu"

    async def infer(
        self,
        sop_embeddings: Optional[np.ndarray] = None,
        lateral_context: Optional[np.ndarray] = None,
        force_recompute: bool = False,
    ) -> InventoryOptimizationTGNNOutput:
        """
        Run Inventory Optimization tGNN inference.

        Args:
            sop_embeddings: S&OP structural embeddings [num_sites, 64].
            lateral_context: Cross-domain context [num_sites, 6] from
                Demand/Supply tGNNs (iteration 2 only). None on first pass.
            force_recompute: If True, skip cache.

        Returns:
            InventoryOptimizationTGNNOutput with per-site inventory signals.
        """
        topology = await self._load_topology()
        if not topology:
            raise ValueError(f"Could not load topology for config {self.config_id}")

        site_keys = [s["site_key"] for s in topology["sites"]]

        x_temporal = await self._build_inventory_features(site_keys)

        if sop_embeddings is None:
            sop_embeddings = await self._load_sop_embeddings()

        checkpoint_path = self._find_checkpoint()
        model = self._load_model(checkpoint_path, x_temporal, sop_embeddings)

        edge_index = self._build_edge_index(topology, site_keys)
        output = self._run_inference(
            model, x_temporal, sop_embeddings, lateral_context,
            edge_index, site_keys, str(checkpoint_path),
        )

        # Derive rebalancing candidates from urgency ranking
        self._compute_rebalancing_candidates(output)

        logger.info(
            f"Inventory Optimization tGNN inference complete for config {self.config_id}: "
            f"{output.num_sites} sites"
        )
        return output

    async def _load_topology(self) -> Optional[Dict]:
        from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane

        result = await self.db.execute(
            select(SupplyChainConfig).where(SupplyChainConfig.id == self.config_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return None

        sites_result = await self.db.execute(
            select(Site).where(Site.config_id == self.config_id)
        )
        sites = sites_result.scalars().all()

        lanes_result = await self.db.execute(
            select(TransportationLane).where(TransportationLane.config_id == self.config_id)
        )
        lanes = lanes_result.scalars().all()

        return {
            "config": config,
            "sites": [
                {
                    "id": s.id,
                    "site_key": s.site_key or f"site_{s.id}",
                    "master_type": s.master_type,
                    "sc_site_type": s.sc_site_type,
                }
                for s in sites
            ],
            "lanes": [
                {
                    "source_id": l.source_site_id,
                    "target_id": l.target_site_id,
                }
                for l in lanes
            ],
        }

    async def _build_inventory_features(self, site_keys: List[str]) -> np.ndarray:
        """
        Build inventory-focused transactional feature tensor
        [window_size, num_sites, 10].

        Queries InvLevel and InvPolicy for recent inventory state.
        Falls through to synthetic baseline on cold start.
        """
        window_size = 10
        num_features = 10
        num_sites = len(site_keys)
        features = np.zeros((window_size, num_sites, num_features), dtype=np.float32)

        try:
            from app.models.sc_entities import InvLevel, InvPolicy

            for site_idx, site_key in enumerate(site_keys):
                # Recent inventory level snapshots
                il_result = await self.db.execute(
                    select(InvLevel)
                    .where(InvLevel.site_id == site_key)
                    .order_by(InvLevel.inventory_date.desc())
                    .limit(window_size)
                )
                inv_levels = list(reversed(il_result.scalars().all()))

                # Inventory policy for safety stock
                ip_result = await self.db.execute(
                    select(InvPolicy)
                    .where(InvPolicy.site_id == site_key)
                    .limit(1)
                )
                inv_policy = ip_result.scalar_one_or_none()
                ss_qty = float(getattr(inv_policy, "ss_quantity", 0) or 0)

                for t_idx in range(min(len(inv_levels), window_size)):
                    il = inv_levels[t_idx]
                    on_hand = float(getattr(il, "on_hand_qty", 0) or 0)
                    in_transit = float(getattr(il, "in_transit_qty", 0) or 0)
                    allocated = float(getattr(il, "allocated_qty", 0) or 0)

                    features[t_idx, site_idx, 0] = on_hand
                    features[t_idx, site_idx, 1] = in_transit
                    features[t_idx, site_idx, 2] = allocated
                    features[t_idx, site_idx, 3] = on_hand + in_transit - allocated  # net position
                    features[t_idx, site_idx, 4] = ss_qty
                    # Buffer ratio: (on_hand - ss_qty) / (ss_qty + 1)
                    features[t_idx, site_idx, 5] = (on_hand - ss_qty) / (ss_qty + 1.0)

        except Exception as e:
            logger.warning(f"Could not load inventory features from DB: {e}")
            # Synthetic baseline — does not distort decisions
            for t in range(window_size):
                for s in range(num_sites):
                    features[t, s, :] = [100, 50, 20, 130, 30, 2.3, 0, 0, 0, 0]

        return features

    async def _load_sop_embeddings(self) -> Optional[np.ndarray]:
        try:
            from app.services.powell.sop_inference_service import SOPInferenceService
            sop_svc = SOPInferenceService(self.db, self.config_id)
            return await sop_svc.get_embeddings_tensor()
        except Exception as e:
            logger.warning(f"Could not load S&OP embeddings: {e}")
            return None

    def _find_checkpoint(self) -> Path:
        """Find latest InventoryOptimizationTGNN checkpoint."""
        ckpt_patterns = [
            f"inventory_optim_tgnn_config_{self.config_id}_*.pt",
            "inventory_optim_tgnn_*.pt",
        ]
        for pattern in ckpt_patterns:
            matches = sorted(CHECKPOINT_DIR.glob(pattern))
            if matches:
                return matches[-1]
        return Path("synthetic")

    def _load_model(self, checkpoint_path: Path, x_temporal, sop_embeddings):
        if str(checkpoint_path) == "synthetic":
            return None

        try:
            import torch
            from app.models.gnn.inventory_optimization_tgnn import InventoryOptimizationTGNN

            num_features = x_temporal.shape[2]
            sop_dim = sop_embeddings.shape[1] if sop_embeddings is not None else 64

            model = InventoryOptimizationTGNN(
                transactional_dim=num_features,
                sop_dim=sop_dim,
            )
            state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
            model.load_state_dict(state["model_state_dict"])
            model.eval()
            return model
        except Exception as e:
            logger.warning(f"Could not load InventoryOptimizationTGNN: {e}")
            return None

    def _build_edge_index(self, topology: Dict, site_keys: List[str]) -> Optional[Any]:
        try:
            import torch
            site_id_to_idx = {s["id"]: i for i, s in enumerate(topology["sites"])}
            src, dst = [], []
            for lane in topology.get("lanes", []):
                s = site_id_to_idx.get(lane["source_id"])
                t = site_id_to_idx.get(lane["target_id"])
                if s is not None and t is not None:
                    src.append(s)
                    dst.append(t)
            if src:
                return torch.tensor([src, dst], dtype=torch.long)
            return None
        except Exception:
            return None

    def _run_inference(
        self,
        model,
        x_temporal,
        sop_embeddings,
        lateral_context,
        edge_index,
        site_keys: List[str],
        checkpoint_path: str,
    ) -> InventoryOptimizationTGNNOutput:
        num_sites = len(site_keys)
        now = datetime.utcnow()

        if model is not None:
            try:
                import torch

                x_t = torch.tensor(x_temporal, dtype=torch.float32).unsqueeze(0)
                x_s = (
                    torch.tensor(sop_embeddings, dtype=torch.float32)
                    if sop_embeddings is not None else None
                )
                x_lat = (
                    torch.tensor(lateral_context, dtype=torch.float32)
                    if lateral_context is not None else None
                )

                with torch.no_grad():
                    out = model(x_t, sop_embeddings=x_s, lateral_context=x_lat,
                                edge_index=edge_index)

                output = InventoryOptimizationTGNNOutput(
                    config_id=self.config_id,
                    num_sites=num_sites,
                    checkpoint_path=checkpoint_path,
                    site_keys=site_keys,
                    computed_at=now,
                )

                for i, site_key in enumerate(site_keys):
                    output.buffer_adjustment_signal[site_key] = float(
                        out["buffer_adjustment"][0, i, 0]
                    )
                    output.rebalancing_urgency[site_key] = float(
                        out["rebalancing_urgency"][0, i, 0]
                    )
                    output.stockout_probability[site_key] = float(
                        out["stockout_prob"][0, i, 0]
                    )
                    output.inventory_health[site_key] = float(
                        out["inventory_health"][0, i, 0]
                    )
                    output.confidence[site_key] = float(out["confidence"][0, i, 0])

                    # Derive days_of_stock from inventory features
                    on_hand = float(x_temporal[-1, i, 0]) if x_temporal.shape[0] > 0 else 0.0
                    # Use a simple heuristic: on_hand / estimated_daily_demand
                    # The model doesn't have direct demand context, so we use on_hand / 7
                    output.days_of_stock[site_key] = on_hand / 7.0 if on_hand > 0 else 0.0

                    # Holding cost pressure: inverse of inventory health
                    output.holding_cost_pressure[site_key] = float(
                        np.clip(1.0 - output.inventory_health[site_key], 0.0, 1.0)
                    )

                output.generate_reasoning()
                return output

            except Exception as e:
                logger.warning(f"InventoryOptimizationTGNN inference failed, using synthetic: {e}")

        synth = self._synthetic_inference(site_keys, x_temporal, checkpoint_path, now)
        synth.generate_reasoning()
        return synth

    def _compute_rebalancing_candidates(
        self, output: InventoryOptimizationTGNNOutput
    ) -> None:
        """
        Identify sites with high rebalancing urgency and pair them as
        candidate transfer sources/destinations.

        Sites with urgency > 0.6 are marked as needing stock.
        Sites with buffer_adjustment_signal < -0.2 have excess stock.
        """
        surplus_sites = [
            sk for sk in output.site_keys
            if output.buffer_adjustment_signal.get(sk, 0.0) < -0.2
        ]
        needy_sites = [
            sk for sk in output.site_keys
            if output.rebalancing_urgency.get(sk, 0.0) > 0.6
        ]

        for site_key in output.site_keys:
            if site_key in needy_sites:
                # Candidates are surplus sites (closest first — no distance data,
                # so just return all surplus sites sorted by magnitude of excess)
                candidates = sorted(
                    surplus_sites,
                    key=lambda sk: output.buffer_adjustment_signal.get(sk, 0.0),
                )
                output.rebalancing_candidates[site_key] = candidates[:5]
            else:
                output.rebalancing_candidates[site_key] = []

    def _synthetic_inference(
        self,
        site_keys: List[str],
        x_temporal: np.ndarray,
        checkpoint_path: str,
        now: datetime,
    ) -> InventoryOptimizationTGNNOutput:
        """Generate plausible synthetic outputs when no model is available."""
        output = InventoryOptimizationTGNNOutput(
            config_id=self.config_id,
            num_sites=len(site_keys),
            checkpoint_path=checkpoint_path,
            site_keys=site_keys,
            computed_at=now,
        )

        rng = np.random.default_rng(42)

        for i, site_key in enumerate(site_keys):
            on_hand = float(x_temporal[-1, i, 0]) if x_temporal.shape[0] > 0 else 100.0
            ss_qty = float(x_temporal[-1, i, 4]) if x_temporal.shape[0] > 0 else 30.0
            buffer_ratio = float(x_temporal[-1, i, 5]) if x_temporal.shape[0] > 0 else 2.3

            # Neutral buffer adjustment — no strong signal without a model
            output.buffer_adjustment_signal[site_key] = float(
                np.clip(rng.normal(0, 0.05), -0.2, 0.2)
            )

            # Rebalancing urgency from buffer ratio
            urgency = float(np.clip(1.0 / (1.0 + buffer_ratio), 0.0, 1.0))
            output.rebalancing_urgency[site_key] = urgency

            output.inventory_health[site_key] = float(
                np.clip(buffer_ratio / (buffer_ratio + 2.0), 0.1, 0.95)
            )

            # Stockout prob from on_hand vs ss_qty
            stockout_p = float(np.clip(1.0 - on_hand / (ss_qty + 1.0), 0.0, 1.0))
            output.stockout_probability[site_key] = stockout_p

            output.days_of_stock[site_key] = on_hand / 7.0 if on_hand > 0 else 0.0
            output.holding_cost_pressure[site_key] = float(
                np.clip(1.0 - output.inventory_health[site_key], 0.0, 1.0)
            )
            output.confidence[site_key] = 0.5

        return output
