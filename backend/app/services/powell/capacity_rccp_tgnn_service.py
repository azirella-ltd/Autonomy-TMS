"""
Capacity/RCCP tGNN Inference Service — Tactical Layer, Capacity Domain.

Loads trained CapacityRCCPTGNN checkpoints and provides runtime inference:
- Per-site planned utilization targets
- Capacity buffer recommendations
- Plan feasibility scores
- Bottleneck risk assessments
- RCCP validation against MPS

Follows the EXACT same patterns as InventoryOptimizationTGNNService.

Usage:
    svc = CapacityRCCPTGNNService(db, config_id, tenant_id=tenant_id)
    out = await svc.infer(sop_embeddings=sop_embeddings)
    # out.planned_utilization[site_key] -> float  # [0, 1]
    # out.bottleneck_risk[site_key] -> float
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from sqlalchemy import select, text as sqt
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.checkpoint_storage_service import checkpoint_dir as _ckpt_dir

logger = logging.getLogger(__name__)


@dataclass
class CapacityRCCPTGNNOutput:
    """Result of CapacityRCCPTGNN inference."""

    config_id: int
    num_sites: int
    checkpoint_path: str

    site_keys: List[str] = field(default_factory=list)
    computed_at: Optional[datetime] = None

    # Per-site outputs
    planned_utilization: Dict[str, float] = field(default_factory=dict)
    capacity_buffer_pct: Dict[str, float] = field(default_factory=dict)
    feasibility_score: Dict[str, float] = field(default_factory=dict)
    bottleneck_risk: Dict[str, float] = field(default_factory=dict)
    available_capacity_hours: Dict[str, float] = field(default_factory=dict)
    planned_load_hours: Dict[str, float] = field(default_factory=dict)
    overtime_exposure: Dict[str, float] = field(default_factory=dict)
    confidence: Dict[str, float] = field(default_factory=dict)

    # Per-site plain-English reasoning
    reasoning: Dict[str, str] = field(default_factory=dict)

    # RCCP validation results (populated by validate_rccp)
    rccp_feasibility_by_period: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    rccp_overloaded_resources: Dict[str, List[str]] = field(default_factory=dict)
    rccp_suggested_adjustments: Dict[str, List[str]] = field(default_factory=dict)

    def generate_reasoning(self) -> None:
        """Populate per-site reasoning strings from output data."""
        from app.services.powell.decision_reasoning import capacity_rccp_tgnn_reasoning
        for site_key in self.site_keys:
            self.reasoning[site_key] = capacity_rccp_tgnn_reasoning(
                site_key=site_key,
                planned_utilization=self.planned_utilization.get(site_key, 0.0),
                capacity_buffer_pct=self.capacity_buffer_pct.get(site_key, 0.0),
                feasibility_score=self.feasibility_score.get(site_key, 0.0),
                bottleneck_risk=self.bottleneck_risk.get(site_key, 0.0),
                overtime_exposure=self.overtime_exposure.get(site_key, 0.0),
                confidence=self.confidence.get(site_key, 0.0),
            )

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "config_id": self.config_id,
            "num_sites": self.num_sites,
            "checkpoint_path": self.checkpoint_path,
            "site_keys": self.site_keys,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
            "planned_utilization": self.planned_utilization,
            "capacity_buffer_pct": self.capacity_buffer_pct,
            "feasibility_score": self.feasibility_score,
            "bottleneck_risk": self.bottleneck_risk,
            "available_capacity_hours": self.available_capacity_hours,
            "planned_load_hours": self.planned_load_hours,
            "overtime_exposure": self.overtime_exposure,
            "confidence": self.confidence,
            "rccp_feasibility_by_period": self.rccp_feasibility_by_period,
            "rccp_overloaded_resources": self.rccp_overloaded_resources,
            "rccp_suggested_adjustments": self.rccp_suggested_adjustments,
        }
        if self.reasoning:
            d["reasoning"] = self.reasoning
        return d


class CapacityRCCPTGNNService:
    """
    Runtime inference for trained CapacityRCCPTGNN models.

    Responsibilities:
    1. Load checkpoint for config_id
    2. Build capacity-focused transactional feature tensors from DB
       (ProductionOrder, Site capacity, ManufacturingOrder)
    3. Combine with S&OP embeddings + optional lateral context
    4. Run forward pass to get utilization targets + feasibility
    5. Run RCCP validation against MPS
    6. Return per-site results for TacticalHiveCoordinator
    """

    def __init__(self, db: AsyncSession, config_id: int, tenant_id: int = 0):
        self.db = db
        self.config_id = config_id
        self.tenant_id = tenant_id
        self._model = None
        self._device = "cpu"

    async def infer(
        self,
        sop_embeddings: Optional[np.ndarray] = None,
        lateral_context: Optional[np.ndarray] = None,
        force_recompute: bool = False,
    ) -> CapacityRCCPTGNNOutput:
        """
        Run Capacity/RCCP tGNN inference.

        Args:
            sop_embeddings: S&OP structural embeddings [num_sites, 64].
            lateral_context: Cross-domain context [num_sites, 6] from
                Inventory tGNN (iteration 2 only). None on first pass.
            force_recompute: If True, skip cache.

        Returns:
            CapacityRCCPTGNNOutput with per-site capacity signals.
        """
        topology = await self._load_topology()
        if not topology:
            raise ValueError(f"Could not load topology for config {self.config_id}")

        site_keys = [s["site_key"] for s in topology["sites"]]

        x_temporal = await self._build_capacity_features(site_keys)

        if sop_embeddings is None:
            sop_embeddings = await self._load_sop_embeddings()

        checkpoint_path = self._find_checkpoint()
        model = self._load_model(checkpoint_path, x_temporal, sop_embeddings)

        edge_index = self._build_edge_index(topology, site_keys)
        output = self._run_inference(
            model, x_temporal, sop_embeddings, lateral_context,
            edge_index, site_keys, str(checkpoint_path),
        )

        logger.info(
            f"Capacity/RCCP tGNN inference complete for config {self.config_id}: "
            f"{output.num_sites} sites"
        )
        return output

    async def validate_rccp(
        self, output: CapacityRCCPTGNNOutput
    ) -> CapacityRCCPTGNNOutput:
        """Run RCCP validation against MPS (supply_plan with plan_version='live').

        For each site:
        1. Loads MPS planned orders from supply_plan (plan_version='live')
        2. Explodes via planning BOM to get component production requirements
        3. Loads against available capacity (from site throughput or capacity resources)
        4. Returns feasibility per period, overloaded resources, suggested adjustments
        """
        from app.models.supply_chain_config import Site

        sites_result = await self.db.execute(
            select(Site).where(Site.config_id == self.config_id)
        )
        sites = {
            (s.site_key or f"site_{s.id}"): s
            for s in sites_result.scalars().all()
        }

        for site_key in output.site_keys:
            site = sites.get(site_key)
            if not site:
                continue

            # Load MPS (live plan) for this site
            mps_rows = await self._load_mps_for_site(site.id)
            if not mps_rows:
                output.rccp_feasibility_by_period[site_key] = []
                output.rccp_overloaded_resources[site_key] = []
                output.rccp_suggested_adjustments[site_key] = []
                continue

            # Estimate capacity from site throughput or production orders
            available_hours = output.available_capacity_hours.get(site_key, 160.0)
            planned_hours = output.planned_load_hours.get(site_key, 0.0)

            # RCCP: check each period's load against capacity
            period_feasibility = []
            overloaded = []
            adjustments = []

            # Group MPS by period (plan_date)
            from collections import defaultdict
            by_period: Dict[str, float] = defaultdict(float)
            for row in mps_rows:
                plan_date = str(row[0])
                qty = float(row[1] or 0)
                # Estimate hours: assume 1 unit = 0.5 hours (will be replaced by
                # real resource-to-product routing when capacity_resource table exists)
                hours_per_unit = 0.5
                by_period[plan_date] += qty * hours_per_unit

            for period_date, load_hours in sorted(by_period.items()):
                utilization = load_hours / max(available_hours, 1.0)
                feasible = utilization <= 1.0
                period_feasibility.append({
                    "period": period_date,
                    "load_hours": round(load_hours, 1),
                    "available_hours": round(available_hours, 1),
                    "utilization": round(utilization, 3),
                    "feasible": feasible,
                })
                if not feasible:
                    overloaded.append(f"{site_key} @ {period_date} ({utilization:.0%})")
                    excess = load_hours - available_hours
                    adjustments.append(
                        f"Reduce load at {site_key} on {period_date} by "
                        f"{excess:.0f}h or add {excess:.0f}h overtime/outsourcing"
                    )

            output.rccp_feasibility_by_period[site_key] = period_feasibility
            output.rccp_overloaded_resources[site_key] = overloaded
            output.rccp_suggested_adjustments[site_key] = adjustments

        return output

    async def _load_mps_for_site(self, site_id: int) -> list:
        """Load MPS (supply_plan with plan_version='live') for a site."""
        try:
            rows = await self.db.execute(
                sqt(
                    "SELECT sp.plan_date, sp.planned_order_quantity "
                    "FROM supply_plan sp "
                    "WHERE sp.site_id = :sid AND sp.plan_version = 'live' "
                    "ORDER BY sp.plan_date"
                ),
                {"sid": site_id},
            )
            return rows.fetchall()
        except Exception as e:
            logger.warning(f"Could not load MPS for site {site_id}: {e}")
            return []

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

    async def _build_capacity_features(self, site_keys: List[str]) -> np.ndarray:
        """
        Build capacity-focused transactional feature tensor
        [window_size, num_sites, 10].

        Feature indices:
          [0] resource_utilization_pct
          [1] available_capacity_hours
          [2] planned_load_hours
          [3] overtime_cost_ratio
          [4] setup_time_ratio
          [5] efficiency_factor (OEE)
          [6] utilization_trend
          [7] seasonal_capacity_idx
          [8] changeover_frequency
          [9] maintenance_downtime_pct

        Queries ManufacturingOrder and ProductionOrder for capacity signals.
        Falls through to synthetic baseline on cold start.
        """
        window_size = 10
        num_features = 10
        num_sites = len(site_keys)
        features = np.zeros((window_size, num_sites, num_features), dtype=np.float32)

        try:
            # Try to derive capacity features from manufacturing/production orders
            for site_idx, site_key in enumerate(site_keys):
                # Query recent manufacturing orders to estimate utilization
                mo_result = await self.db.execute(
                    sqt(
                        "SELECT mo.planned_start_date, mo.quantity, mo.status "
                        "FROM manufacturing_order mo "
                        "JOIN site s ON mo.site_id = s.id "
                        "WHERE (s.site_key = :sk OR s.name = :sk) AND s.config_id = :c "
                        "ORDER BY mo.planned_start_date DESC "
                        "LIMIT :w"
                    ),
                    {"sk": site_key, "c": self.config_id, "w": window_size},
                )
                mo_rows = list(reversed(mo_result.fetchall()))

                if mo_rows:
                    # Estimate capacity metrics from MO data
                    total_qty = sum(float(r[1] or 0) for r in mo_rows)
                    avg_qty = total_qty / max(len(mo_rows), 1)
                    # Assume ~160 hours available per period (1 week)
                    assumed_capacity = 160.0
                    hours_per_unit = 0.5

                    for t_idx in range(min(len(mo_rows), window_size)):
                        qty = float(mo_rows[t_idx][1] or 0)
                        load = qty * hours_per_unit
                        util = load / max(assumed_capacity, 1.0)

                        features[t_idx, site_idx, 0] = float(np.clip(util, 0, 1.5))
                        features[t_idx, site_idx, 1] = assumed_capacity
                        features[t_idx, site_idx, 2] = load
                        features[t_idx, site_idx, 3] = 1.5  # overtime ratio
                        features[t_idx, site_idx, 4] = 0.08  # setup ratio
                        features[t_idx, site_idx, 5] = 0.85  # OEE
                        features[t_idx, site_idx, 7] = 1.0  # seasonal idx
                else:
                    # Cold start: fill with neutral baseline
                    for t in range(window_size):
                        features[t, site_idx, :] = [
                            0.70,   # utilization 70%
                            160.0,  # available hours
                            112.0,  # planned load hours
                            1.5,    # overtime ratio
                            0.08,   # setup ratio
                            0.85,   # OEE
                            0.0,    # flat trend
                            1.0,    # no seasonal adjustment
                            3.0,    # changeover frequency
                            0.05,   # 5% maintenance downtime
                        ]

            # Compute utilization trend (feature index 6) from utilization history
            for site_idx in range(num_sites):
                util_series = features[:, site_idx, 0]
                if window_size >= 3:
                    # Simple linear trend: slope over last N periods
                    x_vals = np.arange(window_size, dtype=np.float32)
                    if np.std(util_series) > 1e-6:
                        slope = np.polyfit(x_vals, util_series, 1)[0]
                        for t in range(window_size):
                            features[t, site_idx, 6] = float(slope)

        except Exception as e:
            logger.warning(f"Could not load capacity features from DB: {e}")
            # Synthetic baseline
            for t in range(window_size):
                for s in range(num_sites):
                    features[t, s, :] = [
                        0.70, 160.0, 112.0, 1.5, 0.08, 0.85, 0.0, 1.0, 3.0, 0.05,
                    ]

        return features

    async def _load_sop_embeddings(self) -> Optional[np.ndarray]:
        try:
            from app.services.powell.sop_inference_service import SOPInferenceService
            sop_svc = SOPInferenceService(self.db, self.config_id, tenant_id=self.tenant_id)
            return await sop_svc.get_embeddings_tensor()
        except Exception as e:
            logger.warning(f"Could not load S&OP embeddings: {e}")
            return None

    def _find_checkpoint(self) -> Path:
        """Find latest CapacityRCCPTGNN checkpoint."""
        ckpt_patterns = [
            f"capacity_rccp_tgnn_config_{self.config_id}_*.pt",
            "capacity_rccp_tgnn_*.pt",
        ]
        for pattern in ckpt_patterns:
            matches = sorted(_ckpt_dir(self.tenant_id, self.config_id).glob(pattern))
            if matches:
                return matches[-1]
        return Path("synthetic")

    def _load_model(self, checkpoint_path: Path, x_temporal, sop_embeddings):
        if str(checkpoint_path) == "synthetic":
            return None

        try:
            import torch
            from app.models.gnn.capacity_rccp_tgnn import CapacityRCCPTGNN

            num_features = x_temporal.shape[2]
            sop_dim = sop_embeddings.shape[1] if sop_embeddings is not None else 64

            model = CapacityRCCPTGNN(
                transactional_dim=num_features,
                sop_dim=sop_dim,
            )
            state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
            model.load_state_dict(state["model_state_dict"])
            model.eval()
            return model
        except Exception as e:
            logger.warning(f"Could not load CapacityRCCPTGNN: {e}")
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
    ) -> CapacityRCCPTGNNOutput:
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

                output = CapacityRCCPTGNNOutput(
                    config_id=self.config_id,
                    num_sites=num_sites,
                    checkpoint_path=checkpoint_path,
                    site_keys=site_keys,
                    computed_at=now,
                )

                for i, site_key in enumerate(site_keys):
                    output.planned_utilization[site_key] = float(
                        out["planned_utilization"][0, i, 0]
                    )
                    output.capacity_buffer_pct[site_key] = float(
                        out["capacity_buffer_pct"][0, i, 0]
                    )
                    output.feasibility_score[site_key] = float(
                        out["feasibility_score"][0, i, 0]
                    )
                    output.bottleneck_risk[site_key] = float(
                        out["bottleneck_risk"][0, i, 0]
                    )
                    output.confidence[site_key] = float(out["confidence"][0, i, 0])

                    # Derive capacity hours from features
                    output.available_capacity_hours[site_key] = float(
                        x_temporal[-1, i, 1]
                    )
                    output.planned_load_hours[site_key] = float(
                        x_temporal[-1, i, 2]
                    )
                    overtime_ratio = float(x_temporal[-1, i, 3])
                    util = output.planned_utilization[site_key]
                    output.overtime_exposure[site_key] = float(
                        np.clip(util - 1.0, 0.0, 1.0) * overtime_ratio
                    ) if util > 1.0 else 0.0

                output.generate_reasoning()
                return output

            except Exception as e:
                logger.warning(f"CapacityRCCPTGNN inference failed, using synthetic: {e}")

        synth = self._synthetic_inference(site_keys, x_temporal, checkpoint_path, now)
        synth.generate_reasoning()
        return synth

    def _synthetic_inference(
        self,
        site_keys: List[str],
        x_temporal: np.ndarray,
        checkpoint_path: str,
        now: datetime,
    ) -> CapacityRCCPTGNNOutput:
        """Generate plausible synthetic outputs when no model is available."""
        output = CapacityRCCPTGNNOutput(
            config_id=self.config_id,
            num_sites=len(site_keys),
            checkpoint_path=checkpoint_path,
            site_keys=site_keys,
            computed_at=now,
        )

        rng = np.random.default_rng(42)

        for i, site_key in enumerate(site_keys):
            # Use utilization from features
            util = float(x_temporal[-1, i, 0]) if x_temporal.shape[0] > 0 else 0.70
            avail = float(x_temporal[-1, i, 1]) if x_temporal.shape[0] > 0 else 160.0
            load = float(x_temporal[-1, i, 2]) if x_temporal.shape[0] > 0 else 112.0
            oee = float(x_temporal[-1, i, 5]) if x_temporal.shape[0] > 0 else 0.85

            # Target utilization: slightly above current (pull toward 80%)
            target = float(np.clip(0.5 * util + 0.5 * 0.80, 0.3, 0.95))
            output.planned_utilization[site_key] = target

            # Capacity buffer: higher when utilization is high
            buffer = float(np.clip(1.0 - target, 0.05, 0.5))
            output.capacity_buffer_pct[site_key] = buffer

            # Feasibility: lower when utilization is very high
            feas = float(np.clip(1.0 - max(util - 0.85, 0.0) * 3.0, 0.0, 1.0))
            output.feasibility_score[site_key] = feas

            # Bottleneck risk: increases with utilization
            bn_risk = float(np.clip((util - 0.7) * 2.5, 0.0, 1.0))
            output.bottleneck_risk[site_key] = bn_risk

            output.available_capacity_hours[site_key] = avail
            output.planned_load_hours[site_key] = load

            # Overtime exposure
            if util > 1.0:
                overtime_ratio = float(x_temporal[-1, i, 3]) if x_temporal.shape[0] > 0 else 1.5
                output.overtime_exposure[site_key] = float(
                    np.clip(util - 1.0, 0.0, 1.0) * overtime_ratio
                )
            else:
                output.overtime_exposure[site_key] = 0.0

            output.confidence[site_key] = 0.5

        return output
