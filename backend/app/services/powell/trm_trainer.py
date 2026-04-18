"""
TRM Training Framework

Re-exports pure training logic from azirella_data_model.powell.trm_training
(Core) and extends with TMS-specific functionality:
- MetricRewardBreakdown (uses TMS metrics_hierarchy)
- RewardCalculator with EK reward shaping and metric breakdown
- TRMTrainer.load_from_corpus() (DB-dependent)

Training Methods:
1. Behavioral Cloning: Learn from expert demonstrations (fast warm-start)
2. RL/VFA: Learn from outcomes via TD learning (can exceed expert)
3. Hybrid: Warm-start with BC, fine-tune with RL
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from enum import Enum
import numpy as np
import logging

from app.models.metrics_hierarchy import (
    TRM_METRIC_MAPPING,
    MetricConfig,
    get_metric_config,
)

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# Re-export all Core classes for backward compatibility
from azirella_data_model.powell.trm_training import (  # noqa: F401
    TrainingMethod,
    TrainingConfig,
    TrainingRecord,
    TrainingResult,
    EconomicCostConfig,
    RewardCalculator as _CoreRewardCalculator,
    TRMTrainer as _CoreTRMTrainer,
)


@dataclass
class MetricRewardBreakdown:
    """
    Named SCOR-level reward decomposition for a single TRM decision.

    Produced by RewardCalculator.calculate_reward_with_breakdown() and logged
    during training so that reward components are traceable to specific Gartner
    L4 metric codes.
    """
    trm_type: str
    components: Dict[str, float]
    total_reward: float
    metric_config: MetricConfig


class RewardCalculator(_CoreRewardCalculator):
    """TMS-specific RewardCalculator with EK reward shaping and metric breakdown.

    Extends the Core RewardCalculator with:
    - calculate_reward_with_breakdown() using TMS MetricConfig
    - EK reward shaping via ExperientialKnowledgeService (DB)
    """

    def __init__(self, reward_shaping_hook=None):
        super().__init__(reward_shaping_hook=reward_shaping_hook)

    def calculate_reward(self, trm_type: str, outcome: Dict[str, Any]) -> float:
        """Calculate scalar reward with EK reward shaping."""
        base_reward = self.calculate_reward_with_breakdown(
            trm_type, outcome, metric_config=None
        ).total_reward

        # Experiential Knowledge reward shaping (GENUINE only, +/-0.05 max)
        ek_bonus = self._get_ek_reward_shaping(trm_type, outcome)
        return base_reward + ek_bonus

    def _get_ek_reward_shaping(self, trm_type: str, outcome: Dict[str, Any]) -> float:
        """Return EK reward shaping bonus. Returns 0.0 if unavailable."""
        try:
            config_id = outcome.get("config_id")
            tenant_id = outcome.get("tenant_id")
            if not config_id or not tenant_id:
                return 0.0
            from app.services.experiential_knowledge_service import ExperientialKnowledgeService
            from app.db.session import sync_session_factory
            db = sync_session_factory()
            try:
                svc = ExperientialKnowledgeService(db=db, tenant_id=tenant_id, config_id=config_id)
                return svc.get_reward_shaping(
                    config_id=config_id,
                    trm_type=trm_type,
                    product_id=outcome.get("product_id"),
                    site_id=outcome.get("site_id") or outcome.get("location_id"),
                )
            finally:
                db.close()
        except Exception:
            return 0.0

    def calculate_reward_with_breakdown(
        self,
        trm_type: str,
        outcome: Dict[str, Any],
        metric_config: Optional[MetricConfig] = None,
    ) -> MetricRewardBreakdown:
        """Calculate reward and return a named Gartner L4 breakdown."""
        cfg = metric_config or get_metric_config(None)
        weights = cfg.get_trm_weights(trm_type)

        # Per-TRM calculators
        legacy_calculators = {
            'atp_executor':      self.atp_reward,
            'atp':               self.atp_reward,
            'rebalancing':       self.rebalancing_reward,
            'po_creation':       self.po_creation_reward,
            'order_tracking':    self.order_tracking_reward,
            'inventory_buffer':  self.inventory_buffer_reward,
            'forecast_baseline': self.forecast_baseline_reward,
            'forecast_adjustment': self.demand_sensing_reward,
            'demand_sensing':      self.demand_sensing_reward,
        }

        calculator = legacy_calculators.get(trm_type, self._generic_reward)
        base_reward = calculator(outcome)

        # Build per-metric components
        metrics = TRM_METRIC_MAPPING.get(trm_type, [])
        components: Dict[str, float] = {}
        if metrics and weights:
            total_weight = sum(weights.get(m, 0.0) for m in metrics) or 1.0
            for m in metrics:
                w = weights.get(m, 1.0 / len(metrics))
                components[m] = base_reward * (w / total_weight)
        else:
            components["base"] = base_reward

        signal_bonus = self.signal_attribution_bonus(outcome)
        total = base_reward + signal_bonus

        return MetricRewardBreakdown(
            trm_type=trm_type,
            components=components,
            total_reward=total,
            metric_config=cfg,
        )


class TRMTrainer(_CoreTRMTrainer):
    """TMS-specific TRMTrainer with corpus loading from DB.

    Extends the Core TRMTrainer with:
    - load_from_corpus() for loading from the unified training corpus (DB)
    - Uses TMS RewardCalculator by default
    """

    def __init__(
        self,
        model: Any,
        config: TrainingConfig,
        reward_calculator: Optional[RewardCalculator] = None,
    ):
        super().__init__(
            model=model,
            config=config,
            reward_calculator=reward_calculator or RewardCalculator(),
        )

    async def load_from_corpus(
        self,
        db,
        config_id: int,
        trm_type: str,
        limit: Optional[int] = None,
    ) -> int:
        """Load Layer 1 samples from the unified training corpus.

        Origin preference (see UNIFIED_TRAINING_CORPUS.md):
          1. origin='historical' — real ERP decisions (primary BC labels)
          2. origin='live'       — post-provisioning real-time outcomes
          3. origin='simulation' — Digital Twin rollouts (augmentation)
        """
        from app.services.training_corpus import TrainingCorpusService

        service = TrainingCorpusService(db)
        corpus_samples = []
        remaining = limit
        for origin_pref in ("historical", "live", "simulation", "perturbation"):
            batch = await service.get_samples(
                config_id=config_id,
                layer=1.0,
                trm_type=trm_type,
                limit=remaining,
                origin=origin_pref,
            )
            corpus_samples.extend(batch)
            if remaining is not None:
                remaining -= len(batch)
                if remaining <= 0:
                    break
        logger.info(
            "TRMTrainer.load_from_corpus trm=%s config=%d: "
            "historical+live+simulation total=%d",
            trm_type, config_id, len(corpus_samples),
        )

        loaded = 0
        for cs in corpus_samples:
            data = cs.get("sample_data", {})
            state = data.get("state_features", {})
            action = data.get("action", {})
            outcome = data.get("reward_components", {})

            state_keys = sorted(state.keys())
            state_array = np.array(
                [float(state[k]) if isinstance(state[k], (int, float)) else 0.0
                 for k in state_keys],
                dtype=np.float32,
            )

            self.add_experience(
                state_features=state_array,
                action=action,
                outcome=outcome,
                trm_type=trm_type,
            )
            loaded += 1

        logger.info(
            "TRMTrainer: loaded %d Layer 1 corpus samples for trm_type=%s config=%d",
            loaded, trm_type, config_id,
        )
        return loaded
