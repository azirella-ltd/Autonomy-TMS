"""
Simulation-Based RL Training for TRM Agents (Phase 2)

After Phase 1 (Behavioral Cloning warm-start), TRM agents run INSIDE the
digital twin simulation and learn from their own decisions via PPO.

Architecture:
- Uses existing _DagChain and _SimSite from simulation_calibration_service.py
- Uses existing RewardCalculator from trm_trainer.py
- Uses existing _ConfigLoader from simulation_calibration_service.py
- PPO with clipped objective, GAE advantages, value head loss, entropy bonus

Training Flow:
  1. Load BC checkpoint (v1) for a specific (site, trm_type) pair
  2. Run N episodes inside the digital twin simulation
     - Warmup phase (30 days): heuristic policy (no gradient)
     - Training phase (150 days): TRM policy (collect transitions)
     - Eval phase (30 days): TRM policy (measure performance)
  3. After each episode batch, compute GAE advantages and run PPO epochs
  4. Save RL checkpoint (v2) if improvement over heuristic baseline

Powell Framework Mapping:
  - Phase 1 (BC) = Imitation of PFA/CFA policies
  - Phase 2 (RL/PPO) = True Value Function Approximation (VFA)
  - The narrow TRM scope (single site, single decision type) makes RL tractable:
    small state space, fast feedback, clear reward signal

References:
  - Powell SDAM Chapter on VFA
  - Schulman et al., "Proximal Policy Optimization Algorithms" (2017)
  - Stöckl (2021) "Learning by Watching" — data volume scaling
"""

import logging
import math
import random
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.distributions import Categorical

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Decision Policy Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class DecisionPolicy(Protocol):
    """Abstract base for pluggable decision policies in the simulation.

    Implementations must return a non-negative order quantity given the
    current simulation site state, its config, and tick context.
    """

    def decide(
        self,
        site: Any,  # _SimSite
        cfg: Any,  # _SiteSimConfig
        tick_context: Dict[str, Any],
    ) -> float:
        """Return a non-negative order quantity."""
        ...


# ---------------------------------------------------------------------------
# Heuristic Policy — wraps existing ERP heuristic for backward compat
# ---------------------------------------------------------------------------


class HeuristicPolicy:
    """Wraps the existing heuristic_library.compute_replenishment.

    Used as the baseline during warmup phases and for improvement comparison.
    """

    def decide(
        self,
        site: Any,
        cfg: Any,
        tick_context: Dict[str, Any],
    ) -> float:
        return site.compute_replenishment_order(
            sim_day=tick_context.get("day", 0),
        )


# ---------------------------------------------------------------------------
# Transition dataclass
# ---------------------------------------------------------------------------


@dataclass
class Transition:
    """Single (s, a, r, s', log_prob, value, done) transition for PPO."""

    state: np.ndarray
    action: float
    reward: float
    next_state: np.ndarray
    log_prob: float
    value: float
    done: bool


# ---------------------------------------------------------------------------
# SimStateEncoder — maps _SimSite state to per-TRM feature vectors
# ---------------------------------------------------------------------------


class SimStateEncoder:
    """Maps _SimSite simulation state to normalized feature vectors for TRM inference.

    All features are normalized to approximately [0, 1] using cfg.order_up_to
    as the scale factor for inventory-related dimensions.  This matches the
    normalization used during BC training so that RL fine-tuning starts from
    a compatible feature space.
    """

    @staticmethod
    def _safe_scale(value: float, scale: float) -> float:
        """Normalize value by scale, clamp to [0, 1]."""
        if scale <= 0:
            return 0.0
        return max(0.0, min(1.0, value / scale))

    @staticmethod
    def _pipeline_features(site: Any, scale: float) -> List[float]:
        """Extract pipeline summary: total in-transit, avg days remaining."""
        pipeline = getattr(site, "_pipeline", [])
        if not pipeline:
            return [0.0, 0.0]
        total_qty = sum(qty for qty, _ in pipeline)
        avg_days = sum(days for _, days in pipeline) / len(pipeline) if pipeline else 0.0
        return [
            SimStateEncoder._safe_scale(total_qty, scale),
            min(1.0, avg_days / 30.0),
        ]

    @classmethod
    def encode_po_creation(cls, site: Any, cfg: Any) -> np.ndarray:
        """17-dim state for POCreationTRM."""
        s = cfg.order_up_to or 100.0
        pipeline = cls._pipeline_features(site, s)
        return np.array(
            [
                cls._safe_scale(site.inventory, s),         # on_hand
                pipeline[0],                                 # in_transit
                0.0,                                         # on_order (approx)
                0.0,                                         # committed
                cls._safe_scale(site.backlog, s),            # backlog
                cls._safe_scale(cfg.safety_stock, s),        # safety_stock
                cls._safe_scale(cfg.reorder_point, s),       # reorder_point
                cls._safe_scale(site.inventory, max(site.avg_daily_demand, 0.01) * 7),  # days_of_supply
                min(1.0, cfg.lead_time_days / 30.0),         # lead_time_days
                0.5,                                         # unit_cost (normalized placeholder)
                cls._safe_scale(cfg.min_order_quantity, s),  # min_order_qty
                0.9,                                         # on_time_rate (placeholder)
                1.0,                                         # is_available
                cls._safe_scale(site._forecast * 30, s),     # forecast_next_30_days
                min(1.0, site.demand_cv),                    # forecast_uncertainty
                0.2,                                         # supply_risk_score
                min(1.0, site.demand_cv),                    # demand_volatility_score
            ],
            dtype=np.float32,
        )

    @classmethod
    def encode_atp_executor(cls, site: Any, cfg: Any) -> np.ndarray:
        """15-dim state for ATPExecutorTRM."""
        s = cfg.order_up_to or 100.0
        pipeline = cls._pipeline_features(site, s)
        return np.array(
            [
                cls._safe_scale(site.inventory, s),
                cls._safe_scale(site.backlog, s),
                pipeline[0],
                pipeline[1],
                cls._safe_scale(site.avg_daily_demand, s / 7),
                min(1.0, site.demand_cv),
                cls._safe_scale(site._forecast, s / 7),
                cls._safe_scale(cfg.safety_stock, s),
                cls._safe_scale(cfg.reorder_point, s),
                min(1.0, cfg.lead_time_days / 30.0),
                cls._safe_scale(cfg.holding_cost_daily * s, 1.0),
                cls._safe_scale(cfg.backlog_cost_daily * s, 1.0),
                site.period_fill_rate,
                float(site.period_stockout),
                cls._safe_scale(site.inventory_position, s),
            ],
            dtype=np.float32,
        )

    @classmethod
    def encode_rebalancing(cls, site: Any, cfg: Any) -> np.ndarray:
        """14-dim state for InventoryRebalancingTRM."""
        s = cfg.order_up_to or 100.0
        pipeline = cls._pipeline_features(site, s)
        days_cover = site.inventory / max(site.avg_daily_demand, 0.01)
        return np.array(
            [
                cls._safe_scale(site.inventory, s),
                cls._safe_scale(site.backlog, s),
                pipeline[0],
                pipeline[1],
                cls._safe_scale(site.avg_daily_demand, s / 7),
                min(1.0, site.demand_cv),
                cls._safe_scale(cfg.safety_stock, s),
                min(1.0, days_cover / 30.0),
                min(1.0, cfg.lead_time_days / 30.0),
                site.period_fill_rate,
                float(site.period_stockout),
                cls._safe_scale(cfg.holding_cost_daily * s, 1.0),
                cls._safe_scale(cfg.backlog_cost_daily * s, 1.0),
                cls._safe_scale(site.inventory_position, s),
            ],
            dtype=np.float32,
        )

    @classmethod
    def encode_order_tracking(cls, site: Any, cfg: Any) -> np.ndarray:
        """14-dim state for OrderTrackingTRM."""
        s = cfg.order_up_to or 100.0
        pipeline = cls._pipeline_features(site, s)
        backlog_ratio = site.backlog / max(site.avg_daily_demand * cfg.lead_time_days, 1.0)
        return np.array(
            [
                cls._safe_scale(site.inventory, s),
                cls._safe_scale(site.backlog, s),
                pipeline[0],
                pipeline[1],
                cls._safe_scale(site.avg_daily_demand, s / 7),
                min(1.0, site.demand_cv),
                min(1.0, cfg.lead_time_days / 30.0),
                site.period_fill_rate,
                float(site.period_stockout),
                min(1.0, backlog_ratio),
                cls._safe_scale(site.period_order_qty, s),
                cls._safe_scale(cfg.holding_cost_daily * s, 1.0),
                cls._safe_scale(cfg.backlog_cost_daily * s, 1.0),
                cls._safe_scale(site.inventory_position, s),
            ],
            dtype=np.float32,
        )

    @classmethod
    def encode_inventory_buffer(cls, site: Any, cfg: Any) -> np.ndarray:
        """14-dim state for InventoryBufferTRM."""
        s = cfg.order_up_to or 100.0
        pipeline = cls._pipeline_features(site, s)
        days_cover = site.inventory / max(site.avg_daily_demand, 0.01)
        return np.array(
            [
                cls._safe_scale(site.inventory, s),
                cls._safe_scale(site.backlog, s),
                pipeline[0],
                pipeline[1],
                cls._safe_scale(site.avg_daily_demand, s / 7),
                min(1.0, site.demand_cv),
                cls._safe_scale(cfg.safety_stock, s),
                cls._safe_scale(cfg.reorder_point, s),
                min(1.0, days_cover / 30.0),
                min(1.0, cfg.lead_time_days / 30.0),
                site.period_fill_rate,
                float(site.period_stockout),
                cls._safe_scale(cfg.holding_cost_daily * s, 1.0),
                cls._safe_scale(cfg.backlog_cost_daily * s, 1.0),
            ],
            dtype=np.float32,
        )

    @classmethod
    def encode_mo_execution(cls, site: Any, cfg: Any) -> np.ndarray:
        """14-dim state for MOExecutionTRM."""
        s = cfg.order_up_to or 100.0
        pipeline = cls._pipeline_features(site, s)
        cap_total = getattr(site, "_capacity_total", 100.0)
        cap_used = getattr(site, "_capacity_used", 50.0)
        utilization = cap_used / max(cap_total, 1.0)
        return np.array(
            [
                cls._safe_scale(site.inventory, s),
                cls._safe_scale(site.backlog, s),
                pipeline[0],
                pipeline[1],
                cls._safe_scale(site.avg_daily_demand, s / 7),
                min(1.0, site.demand_cv),
                min(1.0, utilization),
                cls._safe_scale(cfg.safety_stock, s),
                min(1.0, cfg.lead_time_days / 30.0),
                site.period_fill_rate,
                float(site.period_stockout),
                cls._safe_scale(site.period_order_qty, s),
                cls._safe_scale(cfg.holding_cost_daily * s, 1.0),
                cls._safe_scale(cfg.backlog_cost_daily * s, 1.0),
            ],
            dtype=np.float32,
        )

    @classmethod
    def encode_to_execution(cls, site: Any, cfg: Any) -> np.ndarray:
        """14-dim state for TOExecutionTRM."""
        s = cfg.order_up_to or 100.0
        pipeline = cls._pipeline_features(site, s)
        days_cover = site.inventory / max(site.avg_daily_demand, 0.01)
        return np.array(
            [
                cls._safe_scale(site.inventory, s),
                cls._safe_scale(site.backlog, s),
                pipeline[0],
                pipeline[1],
                cls._safe_scale(site.avg_daily_demand, s / 7),
                min(1.0, site.demand_cv),
                cls._safe_scale(cfg.safety_stock, s),
                min(1.0, days_cover / 30.0),
                min(1.0, cfg.lead_time_days / 30.0),
                site.period_fill_rate,
                float(site.period_stockout),
                cls._safe_scale(site.period_order_qty, s),
                cls._safe_scale(cfg.holding_cost_daily * s, 1.0),
                cls._safe_scale(cfg.backlog_cost_daily * s, 1.0),
            ],
            dtype=np.float32,
        )

    @classmethod
    def encode_quality_disposition(cls, site: Any, cfg: Any) -> np.ndarray:
        """14-dim state for QualityDispositionTRM."""
        s = cfg.order_up_to or 100.0
        pipeline = cls._pipeline_features(site, s)
        quality, _ = site.quality_outcome()
        return np.array(
            [
                cls._safe_scale(site.inventory, s),
                cls._safe_scale(site.backlog, s),
                pipeline[0],
                pipeline[1],
                cls._safe_scale(site.avg_daily_demand, s / 7),
                min(1.0, site.demand_cv),
                quality,
                cls._safe_scale(cfg.safety_stock, s),
                min(1.0, cfg.lead_time_days / 30.0),
                site.period_fill_rate,
                float(site.period_stockout),
                cls._safe_scale(site.period_order_qty, s),
                cls._safe_scale(cfg.holding_cost_daily * s, 1.0),
                cls._safe_scale(cfg.backlog_cost_daily * s, 1.0),
            ],
            dtype=np.float32,
        )

    @classmethod
    def encode_maintenance_scheduling(cls, site: Any, cfg: Any) -> np.ndarray:
        """14-dim state for MaintenanceSchedulingTRM."""
        s = cfg.order_up_to or 100.0
        pipeline = cls._pipeline_features(site, s)
        cap_total = getattr(site, "_capacity_total", 100.0)
        cap_used = getattr(site, "_capacity_used", 50.0)
        utilization = cap_used / max(cap_total, 1.0)
        days_since_pm = getattr(site, "_days_since_pm", 0)
        return np.array(
            [
                cls._safe_scale(site.inventory, s),
                cls._safe_scale(site.backlog, s),
                pipeline[0],
                pipeline[1],
                cls._safe_scale(site.avg_daily_demand, s / 7),
                min(1.0, utilization),
                min(1.0, days_since_pm / 90.0),
                cls._safe_scale(cfg.safety_stock, s),
                min(1.0, cfg.lead_time_days / 30.0),
                site.period_fill_rate,
                float(site.period_stockout),
                cls._safe_scale(site.period_order_qty, s),
                cls._safe_scale(cfg.holding_cost_daily * s, 1.0),
                cls._safe_scale(cfg.backlog_cost_daily * s, 1.0),
            ],
            dtype=np.float32,
        )

    @classmethod
    def encode_subcontracting(cls, site: Any, cfg: Any) -> np.ndarray:
        """14-dim state for SubcontractingTRM."""
        s = cfg.order_up_to or 100.0
        pipeline = cls._pipeline_features(site, s)
        cap_total = getattr(site, "_capacity_total", 100.0)
        cap_used = getattr(site, "_capacity_used", 50.0)
        utilization = cap_used / max(cap_total, 1.0)
        return np.array(
            [
                cls._safe_scale(site.inventory, s),
                cls._safe_scale(site.backlog, s),
                pipeline[0],
                pipeline[1],
                cls._safe_scale(site.avg_daily_demand, s / 7),
                min(1.0, site.demand_cv),
                min(1.0, utilization),
                cls._safe_scale(cfg.safety_stock, s),
                min(1.0, cfg.lead_time_days / 30.0),
                site.period_fill_rate,
                float(site.period_stockout),
                cls._safe_scale(site.period_order_qty, s),
                cls._safe_scale(cfg.holding_cost_daily * s, 1.0),
                cls._safe_scale(cfg.backlog_cost_daily * s, 1.0),
            ],
            dtype=np.float32,
        )

    @classmethod
    def encode_forecast_adjustment(cls, site: Any, cfg: Any) -> np.ndarray:
        """14-dim state for ForecastAdjustmentTRM."""
        s = cfg.order_up_to or 100.0
        pipeline = cls._pipeline_features(site, s)
        forecast_error, forecast_val = site.forecast_adjustment_signal()
        return np.array(
            [
                cls._safe_scale(site.inventory, s),
                cls._safe_scale(site.backlog, s),
                pipeline[0],
                pipeline[1],
                cls._safe_scale(site.avg_daily_demand, s / 7),
                min(1.0, site.demand_cv),
                cls._safe_scale(forecast_val, s / 7),
                min(1.0, forecast_error),
                cls._safe_scale(cfg.safety_stock, s),
                min(1.0, cfg.lead_time_days / 30.0),
                site.period_fill_rate,
                float(site.period_stockout),
                cls._safe_scale(cfg.holding_cost_daily * s, 1.0),
                cls._safe_scale(cfg.backlog_cost_daily * s, 1.0),
            ],
            dtype=np.float32,
        )

    # ----- Dispatch by TRM type -----

    _ENCODERS: Dict[str, Callable] = {}

    @classmethod
    def encode(cls, trm_type: str, site: Any, cfg: Any) -> np.ndarray:
        """Dispatch to the correct encoder by TRM type."""
        if not cls._ENCODERS:
            cls._ENCODERS = {
                "atp_executor": cls.encode_atp_executor,
                "rebalancing": cls.encode_rebalancing,
                "po_creation": cls.encode_po_creation,
                "order_tracking": cls.encode_order_tracking,
                "inventory_buffer": cls.encode_inventory_buffer,
                "mo_execution": cls.encode_mo_execution,
                "to_execution": cls.encode_to_execution,
                "quality_disposition": cls.encode_quality_disposition,
                "maintenance_scheduling": cls.encode_maintenance_scheduling,
                "subcontracting": cls.encode_subcontracting,
                "forecast_adjustment": cls.encode_forecast_adjustment,
            }
        encoder = cls._ENCODERS.get(trm_type)
        if encoder is None:
            raise ValueError(
                f"No encoder for TRM type '{trm_type}'. "
                f"Available: {list(cls._ENCODERS.keys())}"
            )
        return encoder(site, cfg)


# ---------------------------------------------------------------------------
# TRM Policy — runs TRM inference on encoded _SimSite state
# ---------------------------------------------------------------------------


class TRMPolicy:
    """Runs TRM model inference on simulation state to produce order quantities.

    For PPO, this also returns log_prob and value estimates needed for the
    policy gradient update.
    """

    def __init__(
        self,
        model: "nn.Module",
        trm_type: str,
        device: str = "cpu",
        order_scale: float = 100.0,
    ):
        self.model = model
        self.trm_type = trm_type
        self.device = device
        self.order_scale = order_scale  # Scale factor for order_qty output

        # These are populated by the last decide() call for PPO collection
        self.last_log_prob: float = 0.0
        self.last_value: float = 0.0

    def decide(
        self,
        site: Any,
        cfg: Any,
        tick_context: Dict[str, Any],
    ) -> float:
        """Run TRM inference and return order quantity."""
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch required for TRM policy")

        state = SimStateEncoder.encode(self.trm_type, site, cfg)
        state_tensor = torch.tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)

        self.model.eval()
        with torch.no_grad():
            output = self.model(state_tensor)

        # Extract order quantity from model output
        if isinstance(output, dict):
            # Standard TRM model output: {action_logits, order_qty, confidence, value}
            order_qty_raw = output["order_qty"].item()
            self.last_value = output["value"].item()

            # For PPO log_prob: use action_logits if available
            if "action_logits" in output:
                logits = output["action_logits"]
                dist = Categorical(logits=logits)
                action = dist.sample()
                self.last_log_prob = dist.log_prob(action).item()
            else:
                self.last_log_prob = 0.0

            order_qty = max(0.0, order_qty_raw * self.order_scale)
        else:
            # Fallback: treat output as raw tensor
            order_qty = max(0.0, output.squeeze().item() * self.order_scale)
            self.last_value = 0.0
            self.last_log_prob = 0.0

        return order_qty

    def decide_with_grad(
        self,
        site: Any,
        cfg: Any,
        tick_context: Dict[str, Any],
    ) -> Tuple[float, "torch.Tensor", "torch.Tensor"]:
        """Run TRM inference WITH gradient tracking for PPO training.

        Returns:
            (order_qty, log_prob_tensor, value_tensor)
        """
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch required for TRM policy")

        state = SimStateEncoder.encode(self.trm_type, site, cfg)
        state_tensor = torch.tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)

        self.model.train()
        output = self.model(state_tensor)

        if isinstance(output, dict):
            order_qty_raw = output["order_qty"]
            value = output["value"].squeeze(-1)

            if "action_logits" in output:
                logits = output["action_logits"]
                dist = Categorical(logits=logits)
                action = dist.sample()
                log_prob = dist.log_prob(action)
                entropy = dist.entropy()
            else:
                log_prob = torch.zeros(1, device=self.device)
                entropy = torch.zeros(1, device=self.device)

            order_qty = max(0.0, order_qty_raw.detach().item() * self.order_scale)
            self.last_log_prob = log_prob.detach().item()
            self.last_value = value.detach().item()

            return order_qty, log_prob, value
        else:
            order_qty = max(0.0, output.squeeze().item() * self.order_scale)
            return (
                order_qty,
                torch.zeros(1, device=self.device),
                torch.zeros(1, device=self.device),
            )


# ---------------------------------------------------------------------------
# SimulationRLTrainer — the main RL training loop
# ---------------------------------------------------------------------------


@dataclass
class RLHyperparameters:
    """PPO hyperparameters for simulation-based RL training."""

    num_episodes: int = 50
    warmup_days: int = 30
    training_days: int = 150
    eval_days: int = 30
    learning_rate: float = 3e-5
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_epsilon: float = 0.2
    ppo_epochs: int = 4
    value_loss_coef: float = 0.5
    entropy_coef: float = 0.01
    max_grad_norm: float = 0.5
    batch_size: int = 64


@dataclass
class RLTrainingResult:
    """Result of RL training run."""

    final_loss: float
    loss_history: List[float]
    mean_episode_reward: float
    mean_episode_cost: float
    improvement_vs_heuristic_pct: float
    episodes_completed: int
    checkpoint_path: Optional[str] = None
    validation_metrics: Dict[str, float] = field(default_factory=dict)


class SimulationRLTrainer:
    """PPO-based RL training for TRM agents inside the digital twin simulation.

    After BC warm-start produces a v1 checkpoint, this trainer loads the model
    and runs it inside _DagChain episodes where the TRM makes real decisions
    and receives rewards based on actual inventory/backlog/cost outcomes.

    The training loop:
      1. Run episode: warmup (heuristic) → training (TRM) → eval (TRM)
      2. Collect transitions: (state, action, reward, next_state, log_prob, value)
      3. Compute GAE advantages
      4. Run PPO epochs on collected batch
      5. Repeat for N episodes
      6. Compare vs heuristic baseline and save if improved
    """

    def __init__(
        self,
        config_id: int,
        tenant_id: int,
        trm_type: str,
        site_id: int,
        checkpoint_path: Optional[str] = None,
        device: str = "cpu",
        hyperparameters: Optional[RLHyperparameters] = None,
    ):
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch is required for RL training")

        self.config_id = config_id
        self.tenant_id = tenant_id
        self.trm_type = trm_type
        self.site_id = site_id
        self.checkpoint_path = checkpoint_path
        self.device = device
        self.hp = hyperparameters or RLHyperparameters()

        # Model and optimizer — initialized in train()
        self.model: Optional[nn.Module] = None
        self.optimizer: Optional[optim.Adam] = None

        # Reward calculator
        from app.services.powell.trm_trainer import RewardCalculator

        self.reward_calc = RewardCalculator()

        # Heuristic baseline for comparison
        self.heuristic_policy = HeuristicPolicy()

    def _load_model(self) -> None:
        """Load TRM model from checkpoint or create fresh."""
        from app.models.trm import MODEL_REGISTRY

        if self.trm_type not in MODEL_REGISTRY:
            raise ValueError(f"Unknown TRM type: {self.trm_type}")

        model_cls, state_dim = MODEL_REGISTRY[self.trm_type]
        self.model = model_cls(state_dim=state_dim)

        if self.checkpoint_path:
            ckpt = torch.load(self.checkpoint_path, map_location=self.device)
            self.model.load_state_dict(ckpt["model_state_dict"], strict=False)
            logger.info(
                "Loaded BC checkpoint from %s for RL fine-tuning",
                self.checkpoint_path,
            )

        self.model = self.model.to(self.device)
        self.optimizer = optim.Adam(
            self.model.parameters(), lr=self.hp.learning_rate
        )

    def _load_dag_chain(self, seed: int) -> Any:
        """Load the supply chain DAG from the config DB."""
        from app.db.session import sync_session_factory
        from app.services.powell.simulation_calibration_service import (
            _ConfigLoader,
            _DagChain,
        )

        db = sync_session_factory()
        try:
            loader = _ConfigLoader(db, self.config_id)
            site_configs, topo_order = loader.load()
            return _DagChain(site_configs, topo_order, seed=seed)
        finally:
            db.close()

    def train(self) -> RLTrainingResult:
        """Run the full PPO training loop.

        Returns:
            RLTrainingResult with metrics and optional checkpoint path.
        """
        start_time = time.monotonic()
        self._load_model()

        trm_policy = TRMPolicy(
            model=self.model,
            trm_type=self.trm_type,
            device=self.device,
            order_scale=100.0,
        )

        all_losses: List[float] = []
        episode_rewards: List[float] = []
        episode_costs: List[float] = []
        heuristic_costs: List[float] = []

        for episode_idx in range(self.hp.num_episodes):
            seed = episode_idx * 1000 + self.config_id

            # Run episode with TRM policy
            transitions, episode_metrics = self._run_episode(
                trm_policy, seed=seed
            )

            episode_rewards.append(episode_metrics["total_reward"])
            episode_costs.append(episode_metrics["total_cost"])

            # Run heuristic baseline for comparison
            heuristic_cost = self._run_heuristic_episode(seed=seed)
            heuristic_costs.append(heuristic_cost)

            # Train PPO on collected transitions
            if len(transitions) >= self.hp.batch_size:
                advantages = self._compute_gae(
                    transitions, self.hp.gamma, self.hp.gae_lambda
                )
                epoch_loss = self._train_ppo_epoch(transitions, advantages)
                all_losses.append(epoch_loss)

            if (episode_idx + 1) % 10 == 0:
                mean_cost = statistics.mean(episode_costs[-10:])
                mean_heur = statistics.mean(heuristic_costs[-10:])
                improvement = (
                    (mean_heur - mean_cost) / max(abs(mean_heur), 1e-6) * 100
                )
                logger.info(
                    "RL Episode %d/%d: cost=%.2f heuristic=%.2f improvement=%.1f%%",
                    episode_idx + 1,
                    self.hp.num_episodes,
                    mean_cost,
                    mean_heur,
                    improvement,
                )

        # Compute overall improvement
        mean_reward = statistics.mean(episode_rewards) if episode_rewards else 0.0
        mean_cost = statistics.mean(episode_costs) if episode_costs else 0.0
        mean_heuristic = statistics.mean(heuristic_costs) if heuristic_costs else 0.0
        improvement_pct = self._evaluate_vs_heuristic(mean_cost, mean_heuristic)

        # Save checkpoint if improved
        checkpoint_saved = None
        if improvement_pct > 0:
            checkpoint_saved = self._save_checkpoint(
                version=2,
                extra_meta={
                    "training_method": "ppo_rl",
                    "episodes": self.hp.num_episodes,
                    "improvement_vs_heuristic_pct": improvement_pct,
                    "mean_episode_cost": mean_cost,
                    "heuristic_baseline_cost": mean_heuristic,
                },
            )
            logger.info(
                "RL training saved v2 checkpoint: %.1f%% improvement over heuristic",
                improvement_pct,
            )
        else:
            logger.warning(
                "RL training did NOT improve over heuristic (%.1f%%), keeping BC checkpoint",
                improvement_pct,
            )

        duration = time.monotonic() - start_time
        return RLTrainingResult(
            final_loss=all_losses[-1] if all_losses else float("inf"),
            loss_history=all_losses,
            mean_episode_reward=mean_reward,
            mean_episode_cost=mean_cost,
            improvement_vs_heuristic_pct=improvement_pct,
            episodes_completed=self.hp.num_episodes,
            checkpoint_path=checkpoint_saved,
            validation_metrics={
                "heuristic_baseline_cost": mean_heuristic,
                "duration_seconds": duration,
            },
        )

    def _run_episode(
        self,
        trm_policy: TRMPolicy,
        seed: int,
    ) -> Tuple[List[Transition], Dict[str, float]]:
        """Run a single simulation episode with warmup/training/eval phases.

        Returns:
            (transitions, episode_metrics)
        """
        chain = self._load_dag_chain(seed)
        total_days = self.hp.warmup_days + self.hp.training_days + self.hp.eval_days

        transitions: List[Transition] = []
        total_reward = 0.0
        total_cost = 0.0
        training_cost = 0.0

        # Find the target site in the chain
        target_node = chain.nodes.get(self.site_id)
        target_cfg = chain.site_configs.get(self.site_id)

        for day in range(total_days):
            tick_context = {
                "day": day,
                "phase": "warmup" if day < self.hp.warmup_days else (
                    "training" if day < self.hp.warmup_days + self.hp.training_days
                    else "eval"
                ),
                "episode_seed": seed,
            }

            is_training = (
                self.hp.warmup_days <= day < self.hp.warmup_days + self.hp.training_days
            )

            # Encode state BEFORE the tick (pre-decision state)
            if target_node and target_cfg and is_training:
                pre_state = SimStateEncoder.encode(
                    self.trm_type, target_node, target_cfg
                )

            # Choose policy for this tick
            policy = trm_policy if day >= self.hp.warmup_days else None

            # Execute tick with optional policy override
            tick_result = chain.tick(policy=policy, policy_site_id=self.site_id)

            day_cost = tick_result["total_cost"]
            total_cost += day_cost

            # Collect transitions during training phase only
            if target_node and target_cfg and is_training:
                post_state = SimStateEncoder.encode(
                    self.trm_type, target_node, target_cfg
                )

                # Reward: negative cost (we want to minimize cost)
                site_cost = (
                    target_node.period_holding_cost
                    + target_node.period_backlog_cost
                )
                reward = -site_cost
                # Bonus for high fill rate
                reward += target_node.period_fill_rate * 0.5
                # Penalty for stockout
                if target_node.period_stockout:
                    reward -= 1.0

                total_reward += reward
                training_cost += site_cost

                is_done = (day == self.hp.warmup_days + self.hp.training_days - 1)

                transitions.append(
                    Transition(
                        state=pre_state,
                        action=target_node.period_order_qty,
                        reward=reward,
                        next_state=post_state,
                        log_prob=trm_policy.last_log_prob,
                        value=trm_policy.last_value,
                        done=is_done,
                    )
                )

        return transitions, {
            "total_reward": total_reward,
            "total_cost": total_cost,
            "training_cost": training_cost,
            "num_transitions": len(transitions),
        }

    def _run_heuristic_episode(self, seed: int) -> float:
        """Run a heuristic-only episode for baseline comparison."""
        chain = self._load_dag_chain(seed)
        total_days = self.hp.warmup_days + self.hp.training_days + self.hp.eval_days

        total_cost = 0.0
        for day in range(total_days):
            tick_result = chain.tick()  # Default heuristic behavior
            total_cost += tick_result["total_cost"]

        return total_cost

    def _compute_gae(
        self,
        transitions: List[Transition],
        gamma: float,
        lambda_: float,
    ) -> np.ndarray:
        """Compute Generalized Advantage Estimation.

        GAE(gamma, lambda) = sum_{l=0}^{T-t} (gamma * lambda)^l * delta_{t+l}
        where delta_t = r_t + gamma * V(s_{t+1}) - V(s_t)

        Returns:
            advantages: np.ndarray of shape (len(transitions),)
        """
        n = len(transitions)
        advantages = np.zeros(n, dtype=np.float32)
        gae = 0.0

        for t in reversed(range(n)):
            if t == n - 1 or transitions[t].done:
                next_value = 0.0
            else:
                next_value = transitions[t + 1].value

            delta = (
                transitions[t].reward
                + gamma * next_value * (1.0 - float(transitions[t].done))
                - transitions[t].value
            )
            gae = delta + gamma * lambda_ * (1.0 - float(transitions[t].done)) * gae
            advantages[t] = gae

        return advantages

    def _train_ppo_epoch(
        self,
        transitions: List[Transition],
        advantages: np.ndarray,
    ) -> float:
        """Run PPO clipped objective training on collected transitions.

        Returns:
            Average loss across PPO epochs.
        """
        # Normalize advantages
        adv_mean = np.mean(advantages)
        adv_std = np.std(advantages) + 1e-8
        advantages = (advantages - adv_mean) / adv_std

        # Prepare tensors
        states = torch.tensor(
            np.array([t.state for t in transitions]),
            dtype=torch.float32,
            device=self.device,
        )
        old_log_probs = torch.tensor(
            np.array([t.log_prob for t in transitions]),
            dtype=torch.float32,
            device=self.device,
        )
        returns = torch.tensor(
            advantages + np.array([t.value for t in transitions]),
            dtype=torch.float32,
            device=self.device,
        )
        advantages_t = torch.tensor(
            advantages, dtype=torch.float32, device=self.device
        )

        n = len(transitions)
        total_loss = 0.0
        num_updates = 0

        for _ in range(self.hp.ppo_epochs):
            # Mini-batch training
            indices = np.random.permutation(n)
            for start in range(0, n, self.hp.batch_size):
                end = min(start + self.hp.batch_size, n)
                batch_idx = indices[start:end]

                batch_states = states[batch_idx]
                batch_old_log_probs = old_log_probs[batch_idx]
                batch_returns = returns[batch_idx]
                batch_advantages = advantages_t[batch_idx]

                # Forward pass
                self.model.train()
                output = self.model(batch_states)

                if isinstance(output, dict):
                    new_values = output["value"].squeeze(-1)
                    if "action_logits" in output:
                        logits = output["action_logits"]
                        dist = Categorical(logits=logits)
                        # Re-sample actions (same distribution, different sample)
                        actions = dist.sample()
                        new_log_probs = dist.log_prob(actions)
                        entropy = dist.entropy().mean()
                    else:
                        new_log_probs = torch.zeros_like(batch_old_log_probs)
                        entropy = torch.tensor(0.0, device=self.device)
                else:
                    new_values = output.squeeze(-1)
                    new_log_probs = torch.zeros_like(batch_old_log_probs)
                    entropy = torch.tensor(0.0, device=self.device)

                # PPO clipped objective
                ratio = torch.exp(new_log_probs - batch_old_log_probs)
                surr1 = ratio * batch_advantages
                surr2 = (
                    torch.clamp(
                        ratio,
                        1.0 - self.hp.clip_epsilon,
                        1.0 + self.hp.clip_epsilon,
                    )
                    * batch_advantages
                )
                policy_loss = -torch.min(surr1, surr2).mean()

                # Value loss
                value_loss = nn.functional.mse_loss(new_values, batch_returns)

                # Total loss: policy + value - entropy bonus
                loss = (
                    policy_loss
                    + self.hp.value_loss_coef * value_loss
                    - self.hp.entropy_coef * entropy
                )

                # Backward + gradient clip
                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(
                    self.model.parameters(), self.hp.max_grad_norm
                )
                self.optimizer.step()

                total_loss += loss.item()
                num_updates += 1

        return total_loss / max(num_updates, 1)

    def _evaluate_vs_heuristic(
        self,
        trm_mean_cost: float,
        heuristic_mean_cost: float,
    ) -> float:
        """Compute improvement percentage of TRM over heuristic baseline.

        Positive = TRM is better (lower cost).
        Negative = heuristic is better.
        """
        if abs(heuristic_mean_cost) < 1e-6:
            return 0.0
        return (heuristic_mean_cost - trm_mean_cost) / abs(heuristic_mean_cost) * 100.0

    def _save_checkpoint(
        self, version: int, extra_meta: Optional[Dict] = None
    ) -> str:
        """Save RL-trained model checkpoint."""
        from app.services.checkpoint_storage_service import checkpoint_dir

        ckpt_dir = checkpoint_dir(self.tenant_id, self.config_id)
        ckpt_dir.mkdir(parents=True, exist_ok=True)

        path = ckpt_dir / f"trm_{self.trm_type}_site{self.site_id}_v{version}.pt"
        meta = {
            "model_state_dict": self.model.state_dict(),
            "trm_type": self.trm_type,
            "site_id": self.site_id,
            "config_id": self.config_id,
            "tenant_id": self.tenant_id,
            "version": version,
            "training_method": "ppo_rl",
        }
        if extra_meta:
            meta.update(extra_meta)

        torch.save(meta, path)
        logger.info("Saved RL checkpoint: %s", path)
        return str(path)
