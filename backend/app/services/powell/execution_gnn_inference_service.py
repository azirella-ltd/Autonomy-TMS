"""
Execution Temporal GNN Inference Service

Loads trained ExecutionTemporalGNN checkpoints and provides runtime inference:
- Per-site demand forecasts (short-term, daily)
- Exception probability predictions
- Order recommendations for downstream TRM consumption
- Propagation impact estimates for inter-hive signaling

Consumes S&OP structural embeddings from SOPInferenceService cache.

Usage:
    svc = ExecutionGNNInferenceService(db, config_id)
    outputs = await svc.infer(force_recompute=False)
    # outputs.demand_forecast[site_key] -> List[float]
    # outputs.exception_probability[site_key] -> float
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path(__file__).parent.parent.parent / "checkpoints"


@dataclass
class ExecutionGNNOutput:
    """Result of ExecutionTemporalGNN inference."""

    config_id: int
    num_sites: int
    checkpoint_path: str

    # Per-site outputs (site_key -> value)
    demand_forecast: Dict[str, List[float]] = field(default_factory=dict)
    exception_probability: Dict[str, float] = field(default_factory=dict)
    order_recommendation: Dict[str, float] = field(default_factory=dict)
    propagation_impact: Dict[str, List[float]] = field(default_factory=dict)
    confidence: Dict[str, float] = field(default_factory=dict)

    # Conformal prediction intervals on demand forecasts (site_key -> per-period intervals)
    demand_interval: Dict[str, List[Dict[str, float]]] = field(default_factory=dict)
    # Conformal interval on order recommendation (site_key -> {lower, upper, coverage, method})
    allocation_interval: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Ordered list of site keys (matches tensor index order)
    site_keys: List[str] = field(default_factory=list)

    # Metadata
    computed_at: Optional[datetime] = None

    # Per-site plain-English reasoning (site_key -> reasoning string)
    reasoning: Dict[str, str] = field(default_factory=dict)

    def generate_reasoning(self) -> None:
        """Populate per-site reasoning strings from output data."""
        from app.services.powell.decision_reasoning import execution_tgnn_reasoning
        for site_key in self.site_keys:
            forecast = self.demand_forecast.get(site_key, [])
            demand_next = forecast[0] if forecast else None
            # Get first-period demand interval if available
            demand_ivs = self.demand_interval.get(site_key, [])
            demand_iv = demand_ivs[0] if demand_ivs else None
            # Identify sites affected by propagation
            prop_impact = self.propagation_impact.get(site_key, [])
            prop_sites = [
                sk for sk in self.site_keys
                if sk != site_key and self.propagation_impact.get(sk)
            ][:5]
            self.reasoning[site_key] = execution_tgnn_reasoning(
                site_key=site_key,
                demand_forecast_next=demand_next,
                exception_probability=self.exception_probability.get(site_key, 0.0),
                order_recommendation=self.order_recommendation.get(site_key, 0.0),
                confidence=self.confidence.get(site_key, 0.0),
                demand_interval=demand_iv,
                allocation_interval=self.allocation_interval.get(site_key),
                propagation_sites=prop_sites if prop_sites else None,
            )

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "config_id": self.config_id,
            "num_sites": self.num_sites,
            "checkpoint_path": self.checkpoint_path,
            "demand_forecast": self.demand_forecast,
            "exception_probability": self.exception_probability,
            "order_recommendation": self.order_recommendation,
            "propagation_impact": self.propagation_impact,
            "confidence": self.confidence,
            "demand_interval": self.demand_interval,
            "allocation_interval": self.allocation_interval,
            "site_keys": self.site_keys,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
        }
        if self.reasoning:
            d["reasoning"] = self.reasoning
        return d


class ExecutionGNNInferenceService:
    """
    Runtime inference for trained ExecutionTemporalGNN models.

    Responsibilities:
    1. Load checkpoint for config_id
    2. Build transactional feature tensors from DB (inventory, orders, shipments)
    3. Combine with S&OP structural embeddings
    4. Run forward pass to get demand forecasts + exception probabilities
    5. Return per-site results for directive generation
    """

    def __init__(self, db: AsyncSession, config_id: int):
        self.db = db
        self.config_id = config_id
        self._model = None
        self._device = "cpu"

    async def infer(
        self,
        sop_embeddings: Optional[np.ndarray] = None,
        force_recompute: bool = False,
    ) -> ExecutionGNNOutput:
        """
        Run Execution tGNN inference.

        Args:
            sop_embeddings: S&OP structural embeddings [num_sites, 64].
                If None, fetches from SOPInferenceService cache.
            force_recompute: If True, skip cache.

        Returns:
            ExecutionGNNOutput with per-site forecasts and exception probs.
        """
        # Load topology to get site ordering
        topology = await self._load_topology()
        if not topology:
            raise ValueError(f"Could not load topology for config {self.config_id}")

        site_keys = [s["site_key"] for s in topology["sites"]]

        # Build transactional features
        x_temporal = await self._build_transactional_features(site_keys)

        # Get S&OP embeddings if not provided
        if sop_embeddings is None:
            sop_embeddings = await self._load_sop_embeddings()

        # Load model and run inference
        checkpoint_path = self._find_checkpoint()
        model = self._load_model(checkpoint_path, x_temporal, sop_embeddings)

        output = self._run_inference(
            model, x_temporal, sop_embeddings, site_keys, str(checkpoint_path),
        )

        # Enrich with conformal prediction intervals
        self._enrich_with_conformal_intervals(output)

        logger.info(
            f"Execution tGNN inference complete for config {self.config_id}: "
            f"{output.num_sites} sites"
        )
        return output

    async def _load_topology(self) -> Optional[Dict]:
        """Load network topology from DB."""
        from app.models.supply_chain_config import (
            SupplyChainConfig, Site, TransportationLane,
        )

        result = await self.db.execute(
            select(SupplyChainConfig).where(
                SupplyChainConfig.id == self.config_id
            )
        )
        config = result.scalar_one_or_none()
        if not config:
            return None

        sites_result = await self.db.execute(
            select(Site).where(Site.config_id == self.config_id)
        )
        sites = sites_result.scalars().all()

        lanes_result = await self.db.execute(
            select(TransportationLane).where(
                TransportationLane.config_id == self.config_id
            )
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
                    "lead_time": getattr(l, "lead_time", 2),
                }
                for l in lanes
            ],
        }

    async def _build_transactional_features(
        self, site_keys: List[str],
    ) -> np.ndarray:
        """
        Build transactional feature tensor [window_size, num_sites, features].

        Queries recent inventory levels, backlogs, orders, and shipments.
        Uses reasonable defaults when data is unavailable (cold start).
        """
        window_size = 10
        num_features = 8  # inventory, backlog, orders_in, orders_out, shipments, lead_time, capacity, demand
        num_sites = len(site_keys)

        # Initialize with defaults
        features = np.zeros((window_size, num_sites, num_features), dtype=np.float32)

        # Try to load from DB
        try:
            from app.models.powell_decision import SiteAgentDecision

            for site_idx, site_key in enumerate(site_keys):
                result = await self.db.execute(
                    select(SiteAgentDecision)
                    .where(
                        SiteAgentDecision.site_key == site_key,
                        SiteAgentDecision.input_state.isnot(None),
                    )
                    .order_by(SiteAgentDecision.timestamp.desc())
                    .limit(window_size)
                )
                decisions = result.scalars().all()

                for t_idx, d in enumerate(reversed(decisions)):
                    state = d.input_state or {}
                    features[t_idx, site_idx, 0] = float(state.get("inventory_level", 0))
                    features[t_idx, site_idx, 1] = float(state.get("backlog", 0))
                    features[t_idx, site_idx, 2] = float(state.get("pipeline", 0))
                    features[t_idx, site_idx, 3] = float(state.get("order_qty", 0))
                    features[t_idx, site_idx, 4] = float(state.get("in_transit", 0))
                    features[t_idx, site_idx, 5] = float(state.get("lead_time", 3))
                    features[t_idx, site_idx, 6] = float(state.get("capacity_utilization", 0.8))
                    features[t_idx, site_idx, 7] = float(state.get("demand", 0))

        except Exception as e:
            logger.warning(f"Could not load transactional features: {e}")
            # Use synthetic baseline features
            for t in range(window_size):
                for s in range(num_sites):
                    features[t, s, :] = [100, 10, 50, 30, 20, 3, 0.8, 50]

        return features

    async def _load_sop_embeddings(self) -> Optional[np.ndarray]:
        """Load cached S&OP embeddings from SOPInferenceService."""
        try:
            from app.services.powell.sop_inference_service import SOPInferenceService
            sop_svc = SOPInferenceService(self.db, self.config_id)
            return await sop_svc.get_embeddings_tensor()
        except Exception as e:
            logger.warning(f"Could not load S&OP embeddings: {e}")
            return None

    def _find_checkpoint(self) -> Path:
        """Find latest ExecutionTemporalGNN checkpoint."""
        ckpt_patterns = [
            f"execution_tgnn_config_{self.config_id}_*.pt",
            f"execution_tgnn_*.pt",
            "execution_gnn_*.pt",
        ]

        for pattern in ckpt_patterns:
            matches = sorted(CHECKPOINT_DIR.glob(pattern))
            if matches:
                return matches[-1]

        # No checkpoint found — use synthetic inference
        return Path("synthetic")

    def _load_model(self, checkpoint_path: Path, x_temporal, sop_embeddings):
        """Load ExecutionTemporalGNN from checkpoint."""
        if str(checkpoint_path) == "synthetic":
            return None  # Synthetic inference mode

        try:
            import torch
            from app.models.gnn.planning_execution_gnn import ExecutionTemporalGNN

            num_sites = x_temporal.shape[1]
            num_features = x_temporal.shape[2]
            sop_dim = sop_embeddings.shape[1] if sop_embeddings is not None else 64

            model = ExecutionTemporalGNN(
                transactional_dim=num_features,
                structural_dim=sop_dim,
                hidden_dim=64,
                forecast_horizon=4,
                num_heads=4,
            )
            state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
            model.load_state_dict(state["model_state_dict"])
            model.eval()
            return model
        except Exception as e:
            logger.warning(f"Could not load ExecutionTemporalGNN: {e}")
            return None

    def _run_inference(
        self, model, x_temporal, sop_embeddings, site_keys, checkpoint_path,
    ) -> ExecutionGNNOutput:
        """Run forward pass or generate synthetic outputs."""
        num_sites = len(site_keys)
        now = datetime.utcnow()

        if model is not None:
            try:
                import torch

                x_t = torch.tensor(x_temporal, dtype=torch.float32).unsqueeze(0)
                x_s = (
                    torch.tensor(sop_embeddings, dtype=torch.float32).unsqueeze(0)
                    if sop_embeddings is not None
                    else None
                )

                with torch.no_grad():
                    out = model(x_t, structural_embeddings=x_s)

                # Extract per-site results
                output = ExecutionGNNOutput(
                    config_id=self.config_id,
                    num_sites=num_sites,
                    checkpoint_path=checkpoint_path,
                    site_keys=site_keys,
                    computed_at=now,
                )

                for i, site_key in enumerate(site_keys):
                    output.demand_forecast[site_key] = out["demand_forecast"][0, i].tolist()
                    output.exception_probability[site_key] = float(
                        out["exception_probability"][0, i].max()
                    )
                    output.order_recommendation[site_key] = float(
                        out["order_recommendation"][0, i]
                    )
                    output.confidence[site_key] = float(out["confidence"][0, i])

                    if "propagation_impact" in out:
                        output.propagation_impact[site_key] = (
                            out["propagation_impact"][0, i].tolist()
                        )

                output.generate_reasoning()
                return output

            except Exception as e:
                logger.warning(f"Model inference failed, using synthetic: {e}")

        # Synthetic inference (when no checkpoint or model fails)
        synth = self._synthetic_inference(site_keys, x_temporal, checkpoint_path, now)
        synth.generate_reasoning()
        return synth

    def _enrich_with_conformal_intervals(self, output: ExecutionGNNOutput) -> None:
        """
        Enrich tGNN outputs with conformal prediction intervals.

        For each site's demand forecast and order recommendation, queries the
        SupplyChainConformalSuite for calibrated intervals. This propagates
        conformal coverage guarantees from the operational level up to the
        tactical tGNN level.
        """
        try:
            from app.services.conformal_orchestrator import get_conformal_suite
            suite = get_conformal_suite()
        except Exception:
            return

        for site_key in output.site_keys:
            # Demand forecast intervals — one per forecast period
            forecasts = output.demand_forecast.get(site_key, [])
            if forecasts:
                intervals = []
                for point_val in forecasts:
                    try:
                        result = suite.predict_demand(site_key, float(point_val))
                        intervals.append({
                            "lower": result.lower,
                            "upper": result.upper,
                            "point": float(point_val),
                            "coverage": result.coverage,
                            "method": result.method,
                        })
                    except Exception:
                        intervals.append({
                            "lower": float(point_val),
                            "upper": float(point_val),
                            "point": float(point_val),
                            "coverage": None,
                            "method": "none",
                        })
                output.demand_interval[site_key] = intervals

            # Allocation interval — conformal bound on recommended order qty
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
        self, site_keys, x_temporal, checkpoint_path, now,
    ) -> ExecutionGNNOutput:
        """Generate plausible synthetic outputs when no model is available."""
        output = ExecutionGNNOutput(
            config_id=self.config_id,
            num_sites=len(site_keys),
            checkpoint_path=checkpoint_path,
            site_keys=site_keys,
            computed_at=now,
        )

        rng = np.random.default_rng(42)

        for i, site_key in enumerate(site_keys):
            # Use recent demand as base for forecast
            recent_demand = float(x_temporal[-1, i, 7]) if x_temporal.shape[0] > 0 else 50.0
            trend = rng.normal(0, 0.05, 4)

            output.demand_forecast[site_key] = [
                max(0, recent_demand * (1 + t)) for t in trend
            ]

            # Exception probability from inventory/demand ratio
            inv = float(x_temporal[-1, i, 0]) if x_temporal.shape[0] > 0 else 100.0
            demand = max(recent_demand, 1.0)
            inv_ratio = inv / demand
            output.exception_probability[site_key] = float(
                np.clip(1.0 - inv_ratio / 5.0, 0.0, 1.0)
            )

            output.order_recommendation[site_key] = recent_demand * 1.05
            output.confidence[site_key] = float(
                np.clip(0.5 + inv_ratio * 0.1, 0.3, 0.95)
            )
            output.propagation_impact[site_key] = [0.0] * 4

        return output
