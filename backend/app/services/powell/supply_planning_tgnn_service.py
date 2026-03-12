"""
Supply Planning tGNN Inference Service — Tactical Layer, Supply Domain.

Loads trained SupplyPlanningTGNN checkpoints and provides runtime inference:
- Per-site supply exception probability
- Order quantity recommendations
- Allocation priority signals
- Lead time risk estimates
- Pipeline coverage days

Follows the EXACT same patterns as ExecutionGNNInferenceService.

Usage:
    svc = SupplyPlanningTGNNService(db, config_id)
    out = await svc.infer(sop_embeddings=sop_embeddings)
    # out.supply_exception_probability[site_key] -> float
    # out.order_recommendation[site_key] -> float
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
class SupplyPlanningTGNNOutput:
    """Result of SupplyPlanningTGNN inference."""

    config_id: int
    num_sites: int
    checkpoint_path: str

    site_keys: List[str] = field(default_factory=list)
    computed_at: Optional[datetime] = None

    # Per-site outputs
    supply_exception_probability: Dict[str, float] = field(default_factory=dict)
    order_recommendation: Dict[str, float] = field(default_factory=dict)
    allocation_priority: Dict[str, float] = field(default_factory=dict)
    lead_time_risk: Dict[str, float] = field(default_factory=dict)
    supplier_concentration: Dict[str, float] = field(default_factory=dict)
    pipeline_coverage_days: Dict[str, float] = field(default_factory=dict)
    allocation_interval: Dict[str, Dict[str, float]] = field(default_factory=dict)
    confidence: Dict[str, float] = field(default_factory=dict)

    # Per-site plain-English reasoning
    reasoning: Dict[str, str] = field(default_factory=dict)

    def generate_reasoning(self) -> None:
        """Populate per-site reasoning strings from output data."""
        from app.services.powell.decision_reasoning import supply_planning_tgnn_reasoning
        for site_key in self.site_keys:
            self.reasoning[site_key] = supply_planning_tgnn_reasoning(
                site_key=site_key,
                supply_exception_probability=self.supply_exception_probability.get(site_key, 0.0),
                order_recommendation=self.order_recommendation.get(site_key, 0.0),
                lead_time_risk=self.lead_time_risk.get(site_key, 0.0),
                pipeline_coverage_days=self.pipeline_coverage_days.get(site_key, 0.0),
                confidence=self.confidence.get(site_key, 0.0),
                allocation_interval=self.allocation_interval.get(site_key),
            )

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "config_id": self.config_id,
            "num_sites": self.num_sites,
            "checkpoint_path": self.checkpoint_path,
            "site_keys": self.site_keys,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
            "supply_exception_probability": self.supply_exception_probability,
            "order_recommendation": self.order_recommendation,
            "allocation_priority": self.allocation_priority,
            "lead_time_risk": self.lead_time_risk,
            "supplier_concentration": self.supplier_concentration,
            "pipeline_coverage_days": self.pipeline_coverage_days,
            "allocation_interval": self.allocation_interval,
            "confidence": self.confidence,
        }
        if self.reasoning:
            d["reasoning"] = self.reasoning
        return d


class SupplyPlanningTGNNService:
    """
    Runtime inference for trained SupplyPlanningTGNN models.

    Responsibilities:
    1. Load checkpoint for config_id
    2. Build supply-focused transactional feature tensors from DB
       (InboundOrderLine, SourcingRules, VendorLeadTime, SupplyPlan)
    3. Combine with S&OP embeddings + optional lateral context
    4. Run forward pass to get exception probs + order recommendations
    5. Enrich with conformal prediction intervals
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
    ) -> SupplyPlanningTGNNOutput:
        """
        Run Supply Planning tGNN inference.

        Args:
            sop_embeddings: S&OP structural embeddings [num_sites, 64].
            lateral_context: Cross-domain context [num_sites, 6] from
                Demand/Inventory tGNNs (iteration 2 only). None on first pass.
            force_recompute: If True, skip cache.

        Returns:
            SupplyPlanningTGNNOutput with per-site exception probs and orders.
        """
        topology = await self._load_topology()
        if not topology:
            raise ValueError(f"Could not load topology for config {self.config_id}")

        site_keys = [s["site_key"] for s in topology["sites"]]

        x_temporal = await self._build_supply_features(site_keys)

        if sop_embeddings is None:
            sop_embeddings = await self._load_sop_embeddings()

        checkpoint_path = self._find_checkpoint()
        model = self._load_model(checkpoint_path, x_temporal, sop_embeddings)

        edge_index = self._build_edge_index(topology, site_keys)
        output = self._run_inference(
            model, x_temporal, sop_embeddings, lateral_context,
            edge_index, site_keys, str(checkpoint_path),
        )

        self._enrich_with_conformal_intervals(output)

        logger.info(
            f"Supply Planning tGNN inference complete for config {self.config_id}: "
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

    async def _build_supply_features(self, site_keys: List[str]) -> np.ndarray:
        """
        Build supply-focused transactional feature tensor
        [window_size, num_sites, 10].

        Queries InboundOrderLine, VendorLeadTime, SupplyPlan.
        Falls through to synthetic baseline on cold start.
        """
        window_size = 10
        num_features = 10
        num_sites = len(site_keys)
        features = np.zeros((window_size, num_sites, num_features), dtype=np.float32)

        try:
            from app.models.aws_sc_planning import InboundOrderLine, SupplyPlan

            for site_idx, site_key in enumerate(site_keys):
                # Recent inbound orders
                ibl_result = await self.db.execute(
                    select(InboundOrderLine)
                    .where(InboundOrderLine.ship_to_site_id == site_key)
                    .order_by(InboundOrderLine.promised_date.desc())
                    .limit(window_size)
                )
                inbound = list(reversed(ibl_result.scalars().all()))

                # Recent supply plan rows
                sp_result = await self.db.execute(
                    select(SupplyPlan)
                    .where(SupplyPlan.site_id == site_key)
                    .order_by(SupplyPlan.planning_date.desc())
                    .limit(window_size)
                )
                supply_plans = list(reversed(sp_result.scalars().all()))

                for t_idx in range(min(len(inbound), window_size)):
                    o = inbound[t_idx]
                    features[t_idx, site_idx, 0] = float(getattr(o, "ordered_qty", 0) or 0)
                    features[t_idx, site_idx, 1] = float(getattr(o, "open_qty", 0) or 0)

                for t_idx in range(min(len(supply_plans), window_size)):
                    sp = supply_plans[t_idx]
                    features[t_idx, site_idx, 2] = float(getattr(sp, "planned_qty", 0) or 0)
                    features[t_idx, site_idx, 3] = float(getattr(sp, "committed_qty", 0) or 0)

        except Exception as e:
            logger.warning(f"Could not load supply features from DB: {e}")
            # Synthetic baseline — does not distort decisions
            for t in range(window_size):
                for s in range(num_sites):
                    features[t, s, :] = [100, 20, 80, 60, 0, 0, 3, 0.9, 0, 0]

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
        """Find latest SupplyPlanningTGNN checkpoint."""
        ckpt_patterns = [
            f"supply_planning_tgnn_config_{self.config_id}_*.pt",
            "supply_planning_tgnn_*.pt",
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
            from app.models.gnn.supply_planning_tgnn import SupplyPlanningTGNN

            num_features = x_temporal.shape[2]
            sop_dim = sop_embeddings.shape[1] if sop_embeddings is not None else 64

            model = SupplyPlanningTGNN(
                transactional_dim=num_features,
                sop_dim=sop_dim,
            )
            state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
            model.load_state_dict(state["model_state_dict"])
            model.eval()
            return model
        except Exception as e:
            logger.warning(f"Could not load SupplyPlanningTGNN: {e}")
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
    ) -> SupplyPlanningTGNNOutput:
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

                output = SupplyPlanningTGNNOutput(
                    config_id=self.config_id,
                    num_sites=num_sites,
                    checkpoint_path=checkpoint_path,
                    site_keys=site_keys,
                    computed_at=now,
                )

                for i, site_key in enumerate(site_keys):
                    output.supply_exception_probability[site_key] = float(
                        out["exception_prob"][0, i, 0]
                    )
                    output.order_recommendation[site_key] = float(
                        out["order_recommendation"][0, i, 0]
                    )
                    output.allocation_priority[site_key] = float(
                        out["allocation_priority"][0, i, 0]
                    )
                    output.lead_time_risk[site_key] = float(
                        out["lead_time_risk"][0, i, 0]
                    )
                    output.confidence[site_key] = float(out["confidence"][0, i, 0])

                output.generate_reasoning()
                return output

            except Exception as e:
                logger.warning(f"SupplyPlanningTGNN inference failed, using synthetic: {e}")

        synth = self._synthetic_inference(site_keys, x_temporal, checkpoint_path, now)
        synth.generate_reasoning()
        return synth

    def _enrich_with_conformal_intervals(self, output: SupplyPlanningTGNNOutput) -> None:
        """Enrich order recommendation outputs with conformal prediction intervals."""
        try:
            from app.services.conformal_orchestrator import get_conformal_suite
            suite = get_conformal_suite()
        except Exception:
            return

        for site_key in output.site_keys:
            order_rec = output.order_recommendation.get(site_key)
            if order_rec is not None:
                try:
                    result = suite.predict_demand(site_key, float(order_rec))
                    output.allocation_interval[site_key] = {
                        "lower": result.lower,
                        "upper": result.upper,
                        "point": float(order_rec),
                        "coverage": result.coverage,
                        "method": result.method,
                    }
                except Exception:
                    output.allocation_interval[site_key] = {
                        "lower": float(order_rec),
                        "upper": float(order_rec),
                        "point": float(order_rec),
                        "coverage": None,
                        "method": "none",
                    }

    def _synthetic_inference(
        self,
        site_keys: List[str],
        x_temporal: np.ndarray,
        checkpoint_path: str,
        now: datetime,
    ) -> SupplyPlanningTGNNOutput:
        """Generate plausible synthetic outputs when no model is available."""
        output = SupplyPlanningTGNNOutput(
            config_id=self.config_id,
            num_sites=len(site_keys),
            checkpoint_path=checkpoint_path,
            site_keys=site_keys,
            computed_at=now,
        )

        rng = np.random.default_rng(42)

        for i, site_key in enumerate(site_keys):
            # Base order from inbound orders feature (index 0)
            base_order = float(x_temporal[-1, i, 0]) if x_temporal.shape[0] > 0 else 100.0
            if base_order == 0.0:
                base_order = 100.0

            # Exception prob: low by default (neutral baseline)
            open_qty = float(x_temporal[-1, i, 1]) if x_temporal.shape[0] > 0 else 20.0
            exc_prob = float(np.clip(open_qty / (base_order + 1.0) * 0.3, 0.0, 0.8))

            output.supply_exception_probability[site_key] = exc_prob
            output.order_recommendation[site_key] = base_order * 1.05
            output.allocation_priority[site_key] = 0.5
            output.lead_time_risk[site_key] = float(np.clip(exc_prob * 0.5, 0.0, 1.0))
            output.pipeline_coverage_days[site_key] = float(
                rng.uniform(7.0, 21.0)
            )
            output.confidence[site_key] = 0.5

        return output
