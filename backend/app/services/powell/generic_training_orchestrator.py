"""
Generic Training Orchestrator — Config-Driven Model Training Pipeline

Derives everything from the SC config's topology (sites, lanes, products,
master types) and trains all model tiers:

  1. TRM Phase 1 (BC) per site — trains all active TRMs based on site_capabilities
  2. Site tGNN per site — Layer 1.5 intra-site coordination
  3. S&OP GraphSAGE — network-wide structure analysis
  4. Execution tGNN — daily operational inference model

Checkpoint paths are namespaced by config_id:
  checkpoints/config_{id}/trm/{site_key}/trm_{type}_v{N}.pt
  checkpoints/config_{id}/site_tgnn/{site_key}/site_tgnn_latest.pt
  checkpoints/config_{id}/sop_graphsage_best.pt
  checkpoints/config_{id}/execution_tgnn_best.pt

Usage:
    orchestrator = GenericTrainingOrchestrator(config_id=60)
    result = await orchestrator.train_all()

    # Or train individual tiers:
    result = await orchestrator.train_trms(epochs=10)
    result = await orchestrator.train_site_tgnns(epochs=5)
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).parent.parent.parent.parent
CHECKPOINTS_ROOT = BACKEND_ROOT / "checkpoints"


def config_checkpoint_dir(config_id: int) -> Path:
    """Return the checkpoint directory for a specific SC config.

    All models trained for a config live under:
        checkpoints/config_{id}/
    """
    d = CHECKPOINTS_ROOT / f"config_{config_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_slug(config_name: str) -> str:
    """Convert a config name to a filesystem-safe slug."""
    return re.sub(r"[^a-z0-9]+", "_", config_name.lower()).strip("_")


@dataclass
class SiteInfo:
    """Minimal site descriptor derived from the SC config."""
    site_id: int
    site_key: str       # Site.site_id (AWS SC identifier) or name
    site_name: str      # Human-readable name
    site_type: str      # NodeType e.g. "DISTRIBUTOR", "RETAILER"
    master_type: str    # "manufacturer", "inventory", "vendor", "customer"
    active_trms: FrozenSet[str] = field(default_factory=frozenset)


@dataclass
class TrainingResult:
    """Summary of a training run."""
    config_id: int
    tier: str                          # "trm", "site_tgnn", "sop_graphsage", "execution_tgnn"
    sites_trained: int = 0
    models_trained: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


class GenericTrainingOrchestrator:
    """Config-driven training pipeline for all AI model tiers.

    Reads the SC config's topology from the database and trains every
    applicable model.  No hardcoded config IDs, site keys, or tenant
    references — everything is derived from the DAG.
    """

    def __init__(
        self,
        config_id: int,
        device: str = "cpu",
    ):
        self.config_id = config_id
        self.device = device
        self.checkpoint_dir = config_checkpoint_dir(config_id)
        self._sites: Optional[List[SiteInfo]] = None
        self._tenant_id: Optional[int] = None

    # =========================================================================
    # Topology Discovery
    # =========================================================================

    def _load_topology(self) -> Tuple[int, List[SiteInfo]]:
        """Load sites and tenant from the SC config.

        Uses a sync session because TRM training is CPU-bound and the
        callers (provisioning background tasks) already run outside the
        async request context.
        """
        from app.db.session import sync_session_factory
        from app.services.powell.site_capabilities import get_active_trms
        from sqlalchemy import text

        db = sync_session_factory()
        try:
            # Get tenant
            row = db.execute(
                text("SELECT tenant_id FROM supply_chain_configs WHERE id = :c"),
                {"c": self.config_id},
            ).fetchone()
            if not row:
                raise ValueError(f"SC config {self.config_id} not found")
            tenant_id = row[0]

            # Get all non-market sites
            # site table: id, name, type, master_type, config_id
            sites_rows = db.execute(
                text("""
                    SELECT id, name, type, master_type
                    FROM site
                    WHERE config_id = :c
                      AND LOWER(master_type) NOT IN ('market_demand', 'market_supply', 'vendor', 'customer')
                """),
                {"c": self.config_id},
            ).fetchall()

            sites = []
            for db_id, name, site_type, master_type in sites_rows:
                mt = (master_type or "inventory").lower()
                st = (site_type or "").upper()
                active = get_active_trms(master_type=mt, sc_site_type=st)

                sk = name or f"site_{db_id}"

                sites.append(SiteInfo(
                    site_id=db_id,
                    site_key=str(sk),
                    site_name=str(sk),
                    site_type=st,
                    master_type=mt,
                    active_trms=active,
                ))
            return tenant_id, sites
        finally:
            db.close()

    @property
    def sites(self) -> List[SiteInfo]:
        if self._sites is None:
            self._tenant_id, self._sites = self._load_topology()
        return self._sites

    @property
    def tenant_id(self) -> int:
        if self._tenant_id is None:
            self._tenant_id, self._sites = self._load_topology()
        return self._tenant_id

    # =========================================================================
    # TRM Training — Phase 1 BC for all active TRMs at all sites
    # =========================================================================

    async def train_trms(
        self,
        epochs: int = 10,
        num_samples: int = 2000,
    ) -> TrainingResult:
        """Train TRM Phase 1 (BC) for every active TRM at every non-market site.

        Checkpoint paths: config_{id}/trm/trm_{type}_site{site_id}_v1.pt
        """
        from app.services.powell.trm_site_trainer import TRMSiteTrainer

        start = time.time()
        trm_dir = self.checkpoint_dir / "trm"
        trm_dir.mkdir(exist_ok=True)

        result = TrainingResult(config_id=self.config_id, tier="trm")
        site_results: Dict[str, Dict[str, Any]] = {}

        for site in self.sites:
            if not site.active_trms:
                continue

            site_detail: Dict[str, Any] = {}
            for trm_type in sorted(site.active_trms):
                try:
                    trainer = TRMSiteTrainer(
                        trm_type=trm_type,
                        site_id=site.site_id,
                        site_name=site.site_name,
                        master_type=site.master_type,
                        tenant_id=self.tenant_id,
                        config_id=self.config_id,
                        device=self.device,
                        checkpoint_dir=trm_dir,
                    )
                    train_result = await trainer.train_phase1(
                        epochs=epochs, num_samples=num_samples,
                    )
                    # Save checkpoint
                    trainer.save_checkpoint(version=1, extra_meta={
                        "phase": "bc",
                        "site_key": site.site_key,
                    })
                    site_detail[trm_type] = {
                        "status": "ok",
                        "loss": train_result.get("final_loss"),
                    }
                    result.models_trained += 1
                    logger.info(
                        "TRM BC: %s @ %s (site %d, config %d) — loss %.4f",
                        trm_type, site.site_key, site.site_id,
                        self.config_id, train_result.get("final_loss", 0),
                    )
                except Exception as e:
                    logger.warning(
                        "TRM BC failed: %s @ %s (site %d): %s",
                        trm_type, site.site_key, site.site_id, e,
                    )
                    site_detail[trm_type] = {"status": "error", "error": str(e)[:200]}
                    result.errors += 1

            site_results[site.site_key] = site_detail
            result.sites_trained += 1

        result.duration_seconds = time.time() - start
        result.details = site_results
        logger.info(
            "TRM training complete for config %d: %d models, %d errors, %.1fs",
            self.config_id, result.models_trained, result.errors, result.duration_seconds,
        )
        return result

    # =========================================================================
    # Site tGNN Training — Layer 1.5 per site
    # =========================================================================

    async def train_site_tgnns(self, epochs: int = 5) -> TrainingResult:
        """Train Site tGNN (Layer 1.5) for every non-market site.

        Checkpoint paths: config_{id}/site_tgnn/{site_key}/site_tgnn_latest.pt
        """
        from app.services.powell.site_tgnn_trainer import (
            SiteTGNNTrainer,
            SiteTGNNTrainingConfig,
        )

        start = time.time()
        tgnn_dir = str(self.checkpoint_dir / "site_tgnn")

        result = TrainingResult(config_id=self.config_id, tier="site_tgnn")
        site_results: Dict[str, Any] = {}

        for site in self.sites:
            if not site.active_trms:
                continue
            try:
                cfg = SiteTGNNTrainingConfig(
                    bc_epochs=epochs,
                    device=self.device,
                    checkpoint_dir=tgnn_dir,
                )
                trainer = SiteTGNNTrainer(
                    site_key=site.site_key,
                    config_id=self.config_id,
                    config=cfg,
                )
                # Phase 1 BC with synthetic traces
                samples = self._generate_synthetic_site_tgnn_samples(site)
                train_result = trainer.train_phase1_bc(samples, epochs=epochs)
                site_results[site.site_key] = {
                    "status": "ok",
                    "loss": train_result.get("final_loss"),
                }
                result.models_trained += 1
                result.sites_trained += 1
                logger.info(
                    "Site tGNN BC: %s (config %d) — loss %.4f",
                    site.site_key, self.config_id,
                    train_result.get("final_loss", 0),
                )
            except Exception as e:
                logger.warning(
                    "Site tGNN failed: %s (config %d): %s",
                    site.site_key, self.config_id, e,
                )
                site_results[site.site_key] = {"status": "error", "error": str(e)[:200]}
                result.errors += 1

        result.duration_seconds = time.time() - start
        result.details = site_results
        logger.info(
            "Site tGNN training complete for config %d: %d sites, %d errors, %.1fs",
            self.config_id, result.models_trained, result.errors, result.duration_seconds,
        )
        return result

    def _generate_synthetic_site_tgnn_samples(
        self, site: SiteInfo, n_samples: int = 200,
    ) -> list:
        """Generate synthetic training samples for Site tGNN Phase 1 BC.

        Creates plausible node features and target urgency adjustments
        without requiring a SimPy simulation run.
        """
        import numpy as np
        from app.services.powell.site_tgnn_trainer import SiteTGNNTrainingSample
        from app.models.gnn.site_tgnn import NUM_TRM_TYPES

        samples = []
        input_dim = 18  # Default Site tGNN input dimension

        for _ in range(n_samples):
            # Node features: [11, 18] — one row per TRM type
            node_features = np.random.randn(NUM_TRM_TYPES, input_dim).astype(np.float32) * 0.3

            # Target adjustments: [11, 3]
            # urgency_adj ∈ [-0.3, 0.3], conf_mod ∈ [-0.2, 0.2], coord ∈ [0, 1]
            targets = np.zeros((NUM_TRM_TYPES, 3), dtype=np.float32)
            targets[:, 0] = np.clip(np.random.randn(NUM_TRM_TYPES) * 0.1, -0.3, 0.3)
            targets[:, 1] = np.clip(np.random.randn(NUM_TRM_TYPES) * 0.05, -0.2, 0.2)
            targets[:, 2] = np.clip(np.random.rand(NUM_TRM_TYPES), 0.0, 1.0)

            # Mask inactive TRMs (zero features, zero targets)
            from app.services.powell.site_capabilities import get_active_trm_indices
            active_idx = set(get_active_trm_indices(site.master_type, site.site_type))
            for i in range(NUM_TRM_TYPES):
                if i not in active_idx:
                    node_features[i] = 0.0
                    targets[i] = 0.0

            samples.append(SiteTGNNTrainingSample(
                node_features=node_features,
                target_adjustments=targets,
            ))

        return samples

    # =========================================================================
    # GNN Training — S&OP GraphSAGE + Execution tGNN
    # =========================================================================

    async def train_sop_graphsage(self) -> TrainingResult:
        """Train S&OP GraphSAGE using the GNN orchestration service.

        Delegates to GNNOrchestrationService which handles model loading,
        inference, and checkpoint management.
        """
        start = time.time()
        result = TrainingResult(config_id=self.config_id, tier="sop_graphsage")

        try:
            from app.db.session import async_session_factory as AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                from app.services.powell.gnn_orchestration_service import GNNOrchestrationService
                service = GNNOrchestrationService(db, self.config_id)
                cycle_result = await service.run_full_cycle(force_recompute=True)
                result.models_trained = 1
                result.details = {
                    "directives_generated": cycle_result.get("directives_generated", 0),
                    "sop_analysis": cycle_result.get("sop_analysis"),
                }
        except Exception as e:
            logger.warning("S&OP GraphSAGE training error for config %d: %s", self.config_id, e)
            result.errors = 1
            result.details = {"error": str(e)[:200]}

        result.duration_seconds = time.time() - start
        return result

    async def train_execution_tgnn(self) -> TrainingResult:
        """Train Execution tGNN using the GNN orchestration service."""
        start = time.time()
        result = TrainingResult(config_id=self.config_id, tier="execution_tgnn")

        try:
            from app.db.session import async_session_factory as AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                from app.services.powell.gnn_orchestration_service import GNNOrchestrationService
                service = GNNOrchestrationService(db, self.config_id)
                cycle_result = await service.run_full_cycle()
                result.models_trained = 1
                result.details = {
                    "execution_output": cycle_result.get("execution_output"),
                }
        except Exception as e:
            logger.warning("Execution tGNN training error for config %d: %s", self.config_id, e)
            result.errors = 1
            result.details = {"error": str(e)[:200]}

        result.duration_seconds = time.time() - start
        return result

    # =========================================================================
    # Full Pipeline
    # =========================================================================

    async def train_all(
        self,
        trm_epochs: int = 10,
        trm_samples: int = 2000,
        site_tgnn_epochs: int = 5,
    ) -> Dict[str, TrainingResult]:
        """Run the full training pipeline for a config.

        Order matches the provisioning dependency chain:
        1. TRMs (per site) — foundational execution models
        2. Site tGNN — requires TRM context understanding
        3. S&OP GraphSAGE — network-wide analysis
        4. Execution tGNN — daily operational model
        """
        total_start = time.time()
        results = {}

        logger.info("Starting full training pipeline for config %d (%d sites)",
                     self.config_id, len(self.sites))

        results["trm"] = await self.train_trms(epochs=trm_epochs, num_samples=trm_samples)
        results["site_tgnn"] = await self.train_site_tgnns(epochs=site_tgnn_epochs)
        results["sop_graphsage"] = await self.train_sop_graphsage()
        results["execution_tgnn"] = await self.train_execution_tgnn()

        total_duration = time.time() - total_start
        total_models = sum(r.models_trained for r in results.values())
        total_errors = sum(r.errors for r in results.values())
        logger.info(
            "Full training pipeline complete for config %d: "
            "%d models trained, %d errors, %.1fs total",
            self.config_id, total_models, total_errors, total_duration,
        )
        return results
