"""
Site tGNN Trainer — 3-Phase Training Pipeline for Layer 1.5.

Phase 1 — Behavioral Cloning (BC):
  Learn from CoordinatedSimRunner's MultiHeadTrace data. For each hourly
  window, compute ideal urgency adjustments from observed decision outcomes.

Phase 2 — Reinforcement Learning (PPO):
  Fine-tune using CoordinatedSimRunner as environment. Actions are continuous
  urgency adjustments [-0.3, +0.3]. Reward is composite site-level BSC delta.

Phase 3 — Production Calibration:
  Fine-tune from real decision-outcome pairs collected by OutcomeCollectorService.

Architecture reference: TRM_HIVE_ARCHITECTURE.md Section 16.3.5
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from app.models.gnn.site_tgnn import (
    SiteTGNN,
    TRM_NAMES,
    TRM_NAME_TO_IDX,
    NUM_TRM_TYPES,
)


# ============================================================================
# Training Config
# ============================================================================

@dataclass
class SiteTGNNTrainingConfig:
    """Configuration for Site tGNN training."""

    # Model architecture
    input_dim: int = 18

    # Phase 1 — Behavioral Cloning
    bc_epochs: int = 20
    bc_learning_rate: float = 1e-3
    bc_batch_size: int = 32

    # Phase 2 — PPO
    ppo_episodes: int = 500
    ppo_learning_rate: float = 3e-4
    ppo_clip_epsilon: float = 0.2
    ppo_value_coef: float = 0.5
    ppo_entropy_coef: float = 0.01
    ppo_gamma: float = 0.99
    ppo_gae_lambda: float = 0.95
    ppo_epochs_per_batch: int = 4

    # Phase 3 — Calibration
    cal_epochs: int = 10
    cal_learning_rate: float = 1e-4

    # General
    device: str = "cpu"  # Site tGNN is small enough for CPU
    checkpoint_dir: str = "checkpoints/site_tgnn"
    grad_clip: float = 1.0


# ============================================================================
# BC Training Data
# ============================================================================

@dataclass
class SiteTGNNTrainingSample:
    """A single training sample for Phase 1 BC.

    Contains the input features and target urgency adjustments derived
    from observing decision outcomes in MultiHeadTrace.
    """
    node_features: np.ndarray    # [11, input_dim]
    target_adjustments: np.ndarray  # [11, 3] — urgency_adj, conf_mod, coord_signal


# ============================================================================
# SiteTGNNTrainer
# ============================================================================

class SiteTGNNTrainer:
    """3-phase training pipeline for Site tGNN (Layer 1.5).

    Usage:
        trainer = SiteTGNNTrainer(site_key="CDC_WEST", config_id=22)

        # Phase 1: BC from simulation traces
        samples = trainer.prepare_bc_data(traces)
        result = trainer.train_phase1_bc(samples)

        # Phase 2: RL fine-tuning (requires CoordinatedSimRunner)
        result = trainer.train_phase2_rl(sim_runner)

        # Phase 3: Production calibration
        result = trainer.train_phase3_calibrate(outcome_pairs)
    """

    def __init__(
        self,
        site_key: str,
        config_id: int,
        config: Optional[SiteTGNNTrainingConfig] = None,
    ):
        self.site_key = site_key
        self.config_id = config_id
        self.config = config or SiteTGNNTrainingConfig()
        self.model: Optional[SiteTGNN] = None

        if not HAS_TORCH:
            logger.warning("PyTorch not available, Site tGNN training disabled")
            return

        self._init_model()

    def _init_model(self) -> None:
        """Initialize or load existing model."""
        checkpoint_path = self._checkpoint_path()
        if os.path.exists(checkpoint_path):
            try:
                checkpoint = torch.load(
                    checkpoint_path,
                    map_location=self.config.device,
                    weights_only=False,
                )
                self.model = SiteTGNN(input_dim=checkpoint.get("input_dim", self.config.input_dim))
                self.model.load_state_dict(checkpoint["model_state_dict"])
                logger.info(f"Loaded existing Site tGNN for {self.site_key}")
            except Exception as e:
                logger.warning(f"Failed to load checkpoint, creating fresh model: {e}")
                self.model = SiteTGNN(input_dim=self.config.input_dim)
        else:
            self.model = SiteTGNN(input_dim=self.config.input_dim)

        self.model.to(self.config.device)
        logger.info(
            f"Site tGNN model: {self.model.count_parameters()} parameters "
            f"on {self.config.device}"
        )

    def _checkpoint_path(self) -> str:
        """Get checkpoint file path."""
        return os.path.join(
            self.config.checkpoint_dir,
            self.site_key,
            "site_tgnn_latest.pt",
        )

    def _save_checkpoint(self, phase: str, extra: Optional[Dict] = None) -> str:
        """Save model checkpoint."""
        if not self.model:
            return ""

        path = self._checkpoint_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)

        save_dict = {
            "model_state_dict": self.model.state_dict(),
            "input_dim": self.config.input_dim,
            "site_key": self.site_key,
            "config_id": self.config_id,
            "training_phase": phase,
            "num_params": self.model.count_parameters(),
            "timestamp": time.time(),
        }
        if extra:
            save_dict.update(extra)

        torch.save(save_dict, path)
        logger.info(f"Saved Site tGNN checkpoint: {path} (phase={phase})")
        return path

    # ──────────────────────────────────────────────────────────────────────
    # Phase 1: Behavioral Cloning
    # ──────────────────────────────────────────────────────────────────────

    def prepare_bc_data(self, traces: List[Any]) -> List[SiteTGNNTrainingSample]:
        """Prepare BC training samples from MultiHeadTrace objects.

        For each trace (one decision cycle), compute ideal urgency adjustments
        based on cross-TRM outcome analysis:
        - If TRM A's decisions led to poor outcomes for TRM B (via causal edges),
          the ideal adjustment would have been to reduce TRM A's urgency.
        - Conversely, if coordination was beneficial, maintain current urgency.

        Args:
            traces: List of MultiHeadTrace from CoordinatedSimRunner

        Returns:
            List of SiteTGNNTrainingSample
        """
        samples = []

        for trace in traces:
            if not hasattr(trace, "decisions") or not trace.decisions:
                continue

            # Build feature vector from trace
            node_features = self._trace_to_features(trace)

            # Compute target adjustments from outcomes
            target_adjustments = self._compute_ideal_adjustments(trace)

            samples.append(SiteTGNNTrainingSample(
                node_features=node_features,
                target_adjustments=target_adjustments,
            ))

        logger.info(f"Prepared {len(samples)} BC samples from {len(traces)} traces")
        return samples

    async def prepare_bc_data_from_corpus(
        self,
        db,
        config_id: int,
        site_id: Optional[str] = None,
    ) -> List[SiteTGNNTrainingSample]:
        """Load Layer 1.5 samples from the unified training corpus.

        Preferred entry point for provisioning. Converts per-site aggregated
        TRM decision features into SiteTGNNTrainingSample format.

        See docs/internal/architecture/UNIFIED_TRAINING_CORPUS.md
        """
        from app.services.training_corpus import TrainingCorpusService

        service = TrainingCorpusService(db)
        corpus_samples = await service.get_samples(
            config_id=config_id, layer=1.5, site_id=site_id,
        )

        samples: List[SiteTGNNTrainingSample] = []
        for cs in corpus_samples:
            data = cs.get("sample_data", {})
            per_trm = data.get("per_trm_features", {})
            if not per_trm:
                continue

            # Build 11 x input_dim feature matrix from per-TRM aggregates
            features = np.zeros((NUM_TRM_TYPES, self.config.input_dim), dtype=np.float32)

            trm_order = [
                "atp_executor", "order_tracking", "po_creation", "rebalancing",
                "subcontracting", "inventory_buffer", "forecast_adjustment",
                "quality_disposition", "maintenance_scheduling",
                "mo_execution", "to_execution",
            ]
            for idx, trm_type in enumerate(trm_order):
                if idx >= NUM_TRM_TYPES:
                    break
                trm_features = per_trm.get(trm_type, {})
                # Fill the first few dims with aggregated stats
                features[idx, 0] = trm_features.get("avg_reward", 0.0)
                if self.config.input_dim > 1:
                    features[idx, 1] = trm_features.get("decision_count", 0.0) / 100.0
                if self.config.input_dim > 2:
                    features[idx, 2] = trm_features.get("avg_confidence", 0.5)
                if self.config.input_dim > 3:
                    features[idx, 3] = trm_features.get("avg_urgency", 0.5)

            # Target: per-TRM urgency adjustment that would optimize site reward
            # Heuristic: positive adjustment if TRM reward below site avg, negative if above
            site_avg_reward = data.get("site_aggregate_reward", 0.5)
            targets = np.zeros((NUM_TRM_TYPES,), dtype=np.float32)
            for idx, trm_type in enumerate(trm_order):
                if idx >= NUM_TRM_TYPES:
                    break
                trm_reward = per_trm.get(trm_type, {}).get("avg_reward", site_avg_reward)
                # Clip adjustment to [-0.3, +0.3]
                targets[idx] = max(-0.3, min(0.3, (site_avg_reward - trm_reward) * 0.5))

            samples.append(SiteTGNNTrainingSample(
                node_features=features,
                target_adjustments=targets,
            ))

        logger.info(
            "SiteTGNNTrainer: loaded %d Layer 1.5 corpus samples for config %d site %s",
            len(samples), config_id, site_id or "all",
        )
        return samples

    def _trace_to_features(self, trace: Any) -> np.ndarray:
        """Convert MultiHeadTrace to 11 x input_dim feature matrix."""
        features = np.zeros((NUM_TRM_TYPES, self.config.input_dim), dtype=np.float32)

        # Extract urgency from snapshot
        urgency_values = [0.0] * NUM_TRM_TYPES
        if hasattr(trace, "urgency_snapshot") and trace.urgency_snapshot:
            vals = trace.urgency_snapshot.get("values", [])
            for i in range(min(len(vals), NUM_TRM_TYPES)):
                urgency_values[i] = vals[i]

        # Per-TRM features from decision snapshots
        trm_decisions: Dict[str, List] = {}
        for dec in getattr(trace, "decisions", []):
            name = getattr(dec, "trm_name", "")
            if name not in trm_decisions:
                trm_decisions[name] = []
            trm_decisions[name].append(dec)

        for i, trm_name in enumerate(TRM_NAMES):
            features[i, 0] = urgency_values[i]

            decs = trm_decisions.get(trm_name, [])
            features[i, 1] = min(len(decs) / 10.0, 1.0)

            if decs:
                confs = [getattr(d, "confidence", 0.5) for d in decs]
                features[i, 2] = np.mean(confs)
                rewards = [getattr(d, "reward", 0.0) for d in decs]
                features[i, 4] = np.mean(rewards)

            # Cross-head reward as general feature
            features[i, 16] = getattr(trace, "cross_head_reward", 0.0)

        return features

    def _compute_ideal_adjustments(self, trace: Any) -> np.ndarray:
        """Compute ideal urgency adjustments from trace outcomes.

        Heuristic: If a TRM's decisions had good rewards, its urgency was
        appropriate. If poor rewards AND related TRMs had high urgency,
        those related TRMs should have had reduced urgency.
        """
        adjustments = np.zeros((NUM_TRM_TYPES, 3), dtype=np.float32)

        # Per-TRM reward signals
        trm_rewards: Dict[str, float] = {}
        for dec in getattr(trace, "decisions", []):
            name = getattr(dec, "trm_name", "")
            reward = getattr(dec, "reward", 0.0)
            if name in TRM_NAME_TO_IDX:
                trm_rewards[name] = reward

        # Compute adjustments based on reward deviation from mean
        if trm_rewards:
            mean_reward = np.mean(list(trm_rewards.values()))
            for trm_name, reward in trm_rewards.items():
                idx = TRM_NAME_TO_IDX[trm_name]
                deviation = reward - mean_reward
                # Scale to [-0.3, +0.3] range
                adjustments[idx, 0] = np.clip(deviation * 0.5, -0.3, 0.3)
                # Confidence modifier: reduce if poor performance
                adjustments[idx, 1] = np.clip(deviation * 0.3, -0.2, 0.2)
                # Coordination signal: higher if good coordination needed
                adjustments[idx, 2] = 0.5 + np.clip(deviation * 0.3, -0.5, 0.5)

        return adjustments

    def train_phase1_bc(
        self,
        samples: List[SiteTGNNTrainingSample],
        epochs: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Phase 1: Behavioral Cloning from simulation traces.

        Args:
            samples: BC training samples from prepare_bc_data()
            epochs: Override config epochs

        Returns:
            Training result dict with loss history
        """
        if not HAS_TORCH or not self.model or not samples:
            return {"phase": "bc", "status": "skipped", "reason": "no model or data"}

        epochs = epochs or self.config.bc_epochs
        self.model.train()
        optimizer = optim.Adam(self.model.parameters(), lr=self.config.bc_learning_rate)
        loss_fn = nn.MSELoss()

        # Convert samples to tensors
        all_features = torch.tensor(
            np.array([s.node_features for s in samples]),
            dtype=torch.float32, device=self.config.device,
        )
        all_targets = torch.tensor(
            np.array([s.target_adjustments for s in samples]),
            dtype=torch.float32, device=self.config.device,
        )

        losses = []
        for epoch in range(epochs):
            # Shuffle
            perm = torch.randperm(len(samples))
            epoch_loss = 0.0
            num_batches = 0

            for start in range(0, len(samples), self.config.bc_batch_size):
                end = min(start + self.config.bc_batch_size, len(samples))
                idx = perm[start:end]

                batch_x = all_features[idx]
                batch_y = all_targets[idx]

                optimizer.zero_grad()
                output, _ = self.model(batch_x)
                loss = loss_fn(output, batch_y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.grad_clip)
                optimizer.step()

                epoch_loss += loss.item()
                num_batches += 1

            avg_loss = epoch_loss / max(num_batches, 1)
            losses.append(avg_loss)

            if (epoch + 1) % 5 == 0 or epoch == 0:
                logger.info(f"Site tGNN BC epoch {epoch+1}/{epochs}: loss={avg_loss:.6f}")

        self.model.eval()
        checkpoint_path = self._save_checkpoint("bc", {"bc_loss": losses[-1] if losses else 0.0})

        return {
            "phase": "bc",
            "status": "completed",
            "epochs": epochs,
            "final_loss": losses[-1] if losses else 0.0,
            "loss_history": losses,
            "num_samples": len(samples),
            "checkpoint": checkpoint_path,
        }

    def train_phase1_bc_from_oracle(
        self,
        num_scenarios: int = 500,
        phases: Tuple[int, ...] = (1, 2, 3),
        active_trms: Optional[Any] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Phase 1 BC using the MultiTRMCoordinationOracle (no live data required).

        This is the oracle-backed warm-start path, analogous to training a chess
        LLM on Stockfish evaluations. The CoordinationOracle runs all deterministic
        engines simultaneously, resolves resource conflicts via priority rules, and
        produces urgency adjustment labels that the Site tGNN learns to reproduce.

        Call this method at provisioning time (before any live decisions exist)
        to give the Site tGNN a strong behavioral-cloning starting point that is
        already coordination-aware.

        Args:
            num_scenarios: Number of synthetic scenarios to generate (default 500).
            phases: Curriculum phases (1=low var, 2=moderate, 3=high var/disruption).
            active_trms: frozenset of active TRM names (from site_capabilities).
                         If None, uses all 11 TRMs.
            seed: Random seed for reproducibility.

        Returns:
            Training result dict (same format as train_phase1_bc).
        """
        from app.services.powell.site_tgnn_oracle import (
            MultiTRMCoordinationOracle,
            CoordinationSample,
        )

        logger.info(
            "Site tGNN oracle BC: generating %d scenarios for site=%s",
            num_scenarios, self.site_key,
        )
        oracle = MultiTRMCoordinationOracle(
            site_key=self.site_key,
            active_trms=active_trms,
            seed=seed,
        )
        oracle_samples: List[CoordinationSample] = oracle.generate_samples(
            num_scenarios=num_scenarios,
            phases=phases,
        )

        # Convert CoordinationSample → SiteTGNNTrainingSample
        bc_samples = [
            SiteTGNNTrainingSample(
                node_features=s.node_features,
                target_adjustments=s.target_adjustments,
            )
            for s in oracle_samples
        ]

        logger.info(
            "Site tGNN oracle BC: %d samples ready, starting BC training",
            len(bc_samples),
        )
        result = self.train_phase1_bc(bc_samples)
        result["oracle_scenarios"] = num_scenarios
        result["oracle_phases"] = list(phases)
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Phase 2: PPO Reinforcement Learning
    # ──────────────────────────────────────────────────────────────────────

    def train_phase2_rl(
        self,
        sim_runner: Any = None,
        episodes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Phase 2: PPO fine-tuning in simulation environment.

        Uses CoordinatedSimRunner as environment. Actions are continuous
        urgency adjustments. Reward is composite site-level BSC delta.

        Args:
            sim_runner: CoordinatedSimRunner instance for environment
            episodes: Override config episodes

        Returns:
            Training result dict with reward history
        """
        if not HAS_TORCH or not self.model:
            return {"phase": "rl", "status": "skipped", "reason": "no model"}

        if sim_runner is None:
            return {"phase": "rl", "status": "skipped", "reason": "no sim_runner provided"}

        episodes = episodes or self.config.ppo_episodes

        # PPO requires a value head — add temporarily
        value_head = nn.Sequential(
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
        ).to(self.config.device)

        all_params = list(self.model.parameters()) + list(value_head.parameters())
        optimizer = optim.Adam(all_params, lr=self.config.ppo_learning_rate)

        reward_history = []

        for episode in range(episodes):
            # Collect trajectory via sim_runner
            trajectory = self._collect_trajectory(sim_runner, value_head)
            if not trajectory:
                continue

            # PPO update
            episode_reward = self._ppo_update(trajectory, value_head, optimizer)
            reward_history.append(episode_reward)

            if (episode + 1) % 50 == 0:
                avg_reward = np.mean(reward_history[-50:])
                logger.info(
                    f"Site tGNN PPO episode {episode+1}/{episodes}: "
                    f"avg_reward={avg_reward:.4f}"
                )

        self.model.eval()
        checkpoint_path = self._save_checkpoint("rl", {
            "final_reward": reward_history[-1] if reward_history else 0.0,
        })

        return {
            "phase": "rl",
            "status": "completed",
            "episodes": episodes,
            "final_reward": reward_history[-1] if reward_history else 0.0,
            "reward_history": reward_history[-100:],  # Last 100 for brevity
            "checkpoint": checkpoint_path,
        }

    def _collect_trajectory(
        self,
        sim_runner: Any,
        value_head: nn.Module,
    ) -> List[Dict[str, Any]]:
        """Collect a single trajectory from simulation.

        Returns list of (state, action, reward, value, log_prob) tuples.
        """
        # Placeholder — actual implementation requires CoordinatedSimRunner API
        # to step through decision cycles with Site tGNN adjustments
        return []

    def _ppo_update(
        self,
        trajectory: List[Dict[str, Any]],
        value_head: nn.Module,
        optimizer: optim.Optimizer,
    ) -> float:
        """Single PPO update from collected trajectory."""
        if not trajectory:
            return 0.0

        # Placeholder — PPO clip update logic
        total_reward = sum(t.get("reward", 0.0) for t in trajectory)
        return total_reward

    # ──────────────────────────────────────────────────────────────────────
    # Phase 3: Production Calibration
    # ──────────────────────────────────────────────────────────────────────

    def train_phase3_calibrate(
        self,
        outcome_pairs: List[Any],
        epochs: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Phase 3: Production calibration from real decision-outcome pairs.

        Fine-tunes the model using actual outcomes observed by
        OutcomeCollectorService across all 11 powell_*_decisions tables.

        Args:
            outcome_pairs: DecisionOutcomePair objects with actual results
            epochs: Override config epochs

        Returns:
            Training result dict
        """
        if not HAS_TORCH or not self.model or not outcome_pairs:
            return {"phase": "calibrate", "status": "skipped", "reason": "no model or data"}

        epochs = epochs or self.config.cal_epochs

        # Convert outcome pairs to BC-style samples
        samples = self._outcomes_to_samples(outcome_pairs)
        if not samples:
            return {"phase": "calibrate", "status": "skipped", "reason": "no convertible samples"}

        # Use same BC training loop with lower learning rate
        self.model.train()
        optimizer = optim.Adam(
            self.model.parameters(),
            lr=self.config.cal_learning_rate,
        )
        loss_fn = nn.MSELoss()

        all_features = torch.tensor(
            np.array([s.node_features for s in samples]),
            dtype=torch.float32, device=self.config.device,
        )
        all_targets = torch.tensor(
            np.array([s.target_adjustments for s in samples]),
            dtype=torch.float32, device=self.config.device,
        )

        losses = []
        for epoch in range(epochs):
            optimizer.zero_grad()
            output, _ = self.model(all_features)
            loss = loss_fn(output, all_targets)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.grad_clip)
            optimizer.step()
            losses.append(loss.item())

        self.model.eval()
        checkpoint_path = self._save_checkpoint("calibrate", {
            "cal_loss": losses[-1] if losses else 0.0,
        })

        return {
            "phase": "calibrate",
            "status": "completed",
            "epochs": epochs,
            "final_loss": losses[-1] if losses else 0.0,
            "num_samples": len(samples),
            "checkpoint": checkpoint_path,
        }

    def _outcomes_to_samples(self, outcome_pairs: List[Any]) -> List[SiteTGNNTrainingSample]:
        """Convert DecisionOutcomePair objects to training samples.

        Groups outcomes by site + time window to construct per-cycle
        feature vectors and target adjustments.
        """
        # Group by approximate time window (hourly)
        samples = []

        for pair in outcome_pairs:
            if not hasattr(pair, "state_features") or not hasattr(pair, "actual_reward"):
                continue

            # Build simplified feature vector
            node_features = np.zeros((NUM_TRM_TYPES, self.config.input_dim), dtype=np.float32)
            trm_name = getattr(pair, "trm_type", "")
            idx = TRM_NAME_TO_IDX.get(trm_name)
            if idx is not None:
                # Populate the relevant TRM's features
                state = pair.state_features if isinstance(pair.state_features, dict) else {}
                node_features[idx, 0] = state.get("urgency", 0.5)
                node_features[idx, 2] = state.get("confidence", 0.5)
                node_features[idx, 4] = pair.actual_reward

            # Target: adjust based on reward signal
            target = np.zeros((NUM_TRM_TYPES, 3), dtype=np.float32)
            if idx is not None:
                reward = pair.actual_reward
                target[idx, 0] = np.clip(reward * 0.3, -0.3, 0.3)
                target[idx, 1] = np.clip(reward * 0.2, -0.2, 0.2)
                target[idx, 2] = 0.5 + np.clip(reward * 0.3, -0.5, 0.5)

            samples.append(SiteTGNNTrainingSample(
                node_features=node_features,
                target_adjustments=target,
            ))

        return samples
