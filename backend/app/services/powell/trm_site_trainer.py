"""
Per-Site TRM Trainer — Learning-Depth Curriculum

Trains one TRM model for one (site, trm_type) pair through 3 phases:
  Phase 1: Engine Imitation (BC) — match deterministic engine baselines
  Phase 2: Context Learning (Supervised) — learn from expert override logs
  Phase 3: Outcome Optimization (RL/VFA) — improve beyond expert from replay buffer

Stigmergic signal enrichment adds an orthogonal dimension:
  Signal Phase 1 (NO_SIGNALS): Original state vectors only — backward compatible
  Signal Phase 2 (URGENCY_ONLY): Append 11-dim urgency vector to states
  Signal Phase 3 (FULL_SIGNALS): Append 11-dim urgency + 22-dim signal summary

Usage:
    trainer = TRMSiteTrainer(
        trm_type="atp_executor", site_id=42, site_name="SLC DC",
        master_type="INVENTORY", tenant_id=1, config_id=1, device="cpu"
    )
    result = await trainer.train_phase1(epochs=20)
    result = await trainer.train_phase2(db, epochs=50)
    result = await trainer.train_phase3(db, epochs=80)

    # Full stigmergic curriculum (all signal phases × learning phases)
    result = await trainer.train_stigmergic_curriculum(db, epochs_per_phase=30)
"""

import enum
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stigmergic Signal Phase
# ---------------------------------------------------------------------------

class StigmergicPhase(enum.IntEnum):
    """Signal enrichment level — orthogonal to the 3 learning-depth phases."""
    NO_SIGNALS = 0      # Original state only
    URGENCY_ONLY = 1    # + 11-dim urgency vector
    FULL_SIGNALS = 2    # + 11-dim urgency + 22-dim signal summary

    @property
    def extra_dims(self) -> int:
        """Number of extra dimensions added to the state vector."""
        return {0: 0, 1: 11, 2: 33}[self.value]

CHECKPOINT_DIR = Path(__file__).parent.parent.parent.parent / "checkpoints"
CHECKPOINT_DIR.mkdir(exist_ok=True)


class TRMSiteTrainer:
    """
    Trains a single TRM model for a specific (site, trm_type) pair.

    The 3-phase learning-depth curriculum:
    1. Engine Imitation (BC): Generate data from curriculum generators using
       deterministic engines, train via supervised behavioral cloning.
    2. Context Learning (Supervised): Load expert decision logs for this
       site from DB, fine-tune on human override patterns.
    3. Outcome Optimization (RL/VFA): Load replay buffer entries for this
       site, run TD-learning / CQL to discover better-than-expert policies.
    """

    def __init__(
        self,
        trm_type: str,
        site_id: int,
        site_name: str,
        master_type: str,
        tenant_id: int,
        config_id: int,
        device: str = "cpu",
        checkpoint_dir: Optional[Path] = None,
        stigmergic_phase: StigmergicPhase = StigmergicPhase.NO_SIGNALS,
        cross_head_reward_weight: float = 0.05,
        het_gat_enabled: bool = False,
    ):
        self.trm_type = trm_type
        self.site_id = site_id
        self.site_name = site_name
        self.master_type = master_type
        self.tenant_id = tenant_id
        self.config_id = config_id
        self.device = device
        self.checkpoint_dir = checkpoint_dir or CHECKPOINT_DIR
        self.stigmergic_phase = stigmergic_phase
        self.cross_head_reward_weight = cross_head_reward_weight
        self.het_gat_enabled = het_gat_enabled

        self.model = None
        self.model_cls = None
        self.state_dim = None

    @staticmethod
    def cgar_refinement_steps(epoch: int, total_epochs: int, max_R: int = 3) -> int:
        """Compute progressive refinement depth for CGAR curriculum.

        Curriculum-Guided Adaptive Recursion:
          0-30% of training:  R=1 (learn basic mappings)
          30-60% of training: R=2 (learn refinement)
          60-100% of training: R=3 (full recursive reasoning)
        """
        progress = epoch / max(1, total_epochs)
        if progress < 0.3:
            return 1
        elif progress < 0.6:
            return min(2, max_R)
        return max_R

    def _ensure_model(self):
        """Lazily create (or rebuild) the TRM model for current stigmergic phase.

        The model's input dimension must match base state_dim + any extra dims
        added by the current stigmergic phase (urgency vector, signal summary).
        If the phase changes after model creation, the model is rebuilt with
        the new input dimension.
        """
        try:
            import torch
            from app.models.trm import MODEL_REGISTRY
        except ImportError:
            raise RuntimeError("PyTorch not available for TRM training")

        if self.trm_type not in MODEL_REGISTRY:
            raise ValueError(f"Unknown TRM type: {self.trm_type}")

        self.model_cls, base_dim = MODEL_REGISTRY[self.trm_type]
        self._base_state_dim = base_dim
        needed_dim = base_dim + self.stigmergic_phase.extra_dims

        if self.model is not None and self.state_dim == needed_dim:
            return

        self.state_dim = needed_dim
        self.model = self.model_cls(state_dim=self.state_dim)
        self.model = self.model.to(self.device)

    def from_base_model(self, base_checkpoint_path: str):
        """Initialize model weights from a base model checkpoint (cold start)."""
        import torch
        self._ensure_model()
        ckpt = torch.load(base_checkpoint_path, map_location=self.device)
        self.model.load_state_dict(ckpt["model_state_dict"], strict=False)
        logger.info(f"Loaded base model from {base_checkpoint_path} for site {self.site_name}")

    def from_checkpoint(self, checkpoint_path: str):
        """Resume from an existing site-specific checkpoint."""
        import torch
        self._ensure_model()
        ckpt = torch.load(checkpoint_path, map_location=self.device)
        self.model.load_state_dict(ckpt["model_state_dict"])
        logger.info(f"Resumed from {checkpoint_path} for site {self.site_name}")

    def _checkpoint_path(self, version: int) -> Path:
        """Naming: trm_{type}_site{site_id}_v{N}.pt"""
        return self.checkpoint_dir / f"trm_{self.trm_type}_site{self.site_id}_v{version}.pt"

    def save_checkpoint(self, version: int, extra_meta: Optional[Dict] = None) -> str:
        """Save model checkpoint with site metadata."""
        import torch
        path = self._checkpoint_path(version)
        meta = {
            "model_state_dict": self.model.state_dict(),
            "trm_type": self.trm_type,
            "site_id": self.site_id,
            "site_name": self.site_name,
            "master_type": self.master_type,
            "state_dim": self.state_dim,
            "model_class": self.model_cls.__name__,
            "config_id": self.config_id,
            "version": version,
            "saved_at": datetime.utcnow().isoformat(),
        }
        if extra_meta:
            meta.update(extra_meta)
        torch.save(meta, path)
        logger.info(f"Saved checkpoint: {path}")
        return str(path)

    # =========================================================================
    # Signal Augmentation Helpers
    # =========================================================================

    def _augment_states_synthetic(self, states: "np.ndarray") -> "np.ndarray":
        """Augment state vectors with synthetic signal features.

        Used during Phase 1 (BC) where no real signal context exists.
        Generates plausible urgency/signal patterns that correlate with
        the physical state to help the model learn signal-state associations.
        """
        n = len(states)
        extra_dims = self.stigmergic_phase.extra_dims
        if extra_dims == 0 or n == 0:
            return states

        # Generate synthetic urgency vector (11 slots)
        urgency = np.zeros((n, 11), dtype=np.float32)
        if n > 0 and states.shape[1] > 0:
            # Use physical state features to create correlated urgency
            state_mean = np.mean(np.abs(states), axis=1, keepdims=True)
            noise = np.random.randn(n, 11).astype(np.float32) * 0.15
            urgency = np.clip(state_mean * 0.3 + noise, 0.0, 1.0)

        if self.stigmergic_phase == StigmergicPhase.URGENCY_ONLY:
            return np.concatenate([states, urgency], axis=1)

        # FULL_SIGNALS: add 22-dim signal summary (synthetic)
        signal_summary = np.zeros((n, 22), dtype=np.float32)
        # First 11: signal type presence (binary-ish, correlated with urgency)
        signal_summary[:, :11] = (urgency > 0.3).astype(np.float32) * np.random.uniform(
            0.5, 1.0, size=(n, 11)
        ).astype(np.float32)
        # Next 11: signal strengths (scaled urgency with noise)
        signal_summary[:, 11:] = urgency * np.random.uniform(
            0.2, 0.8, size=(n, 11)
        ).astype(np.float32)

        return np.concatenate([states, urgency, signal_summary], axis=1)

    def _augment_states_from_context(
        self,
        states: "np.ndarray",
        signal_contexts: List[Optional[Dict[str, Any]]],
    ) -> "np.ndarray":
        """Augment state vectors with real signal context from decision logs.

        Used in Phases 2-3 where decision records may include stored
        signal_context from the HiveSignalBus.
        """
        n = len(states)
        extra_dims = self.stigmergic_phase.extra_dims
        if extra_dims == 0 or n == 0:
            return states

        urgency_block = np.zeros((n, 11), dtype=np.float32)
        for i, ctx in enumerate(signal_contexts):
            if ctx and "urgency_vector" in ctx:
                uv = ctx["urgency_vector"]
                vals = uv.get("values", [])
                for j in range(min(11, len(vals))):
                    urgency_block[i, j] = float(vals[j])

        if self.stigmergic_phase == StigmergicPhase.URGENCY_ONLY:
            return np.concatenate([states, urgency_block], axis=1)

        # FULL_SIGNALS: extract 22-dim signal summary
        signal_block = np.zeros((n, 22), dtype=np.float32)
        for i, ctx in enumerate(signal_contexts):
            if not ctx:
                continue
            summary = ctx.get("summary", {})
            # Encode up to 11 signal type counts (normalized)
            for j, (stype, count) in enumerate(list(summary.items())[:11]):
                signal_block[i, j] = min(float(count) / 10.0, 1.0)
            # Encode signal strengths (from active_signals if available)
            active = ctx.get("active_signals", [])
            for j, sig in enumerate(active[:11]):
                if isinstance(sig, dict):
                    signal_block[i, 11 + j] = float(sig.get("strength", 0.0))

        return np.concatenate([states, urgency_block, signal_block], axis=1)

    # =========================================================================
    # Phase 1: Engine Imitation (Behavioral Cloning)
    # =========================================================================

    async def train_phase1(
        self,
        epochs: int = 20,
        num_samples: int = 5000,
        learning_rate: float = 1e-4,
        batch_size: int = 64,
    ) -> Dict[str, Any]:
        """
        Phase 1: Train via behavioral cloning from curriculum generator + engines.

        Always available — no real data required. The curriculum generator creates
        synthetic scenarios and the deterministic engines provide expert labels.
        """
        import torch
        from app.services.powell.trm_curriculum import CURRICULUM_REGISTRY, SCConfigData

        self._ensure_model()

        if self.trm_type not in CURRICULUM_REGISTRY:
            return {"skipped": True, "reason": f"No curriculum for {self.trm_type}"}

        start = time.time()
        sc_config = SCConfigData()
        curriculum = CURRICULUM_REGISTRY[self.trm_type](sc_config)

        loss_fn = self._create_loss_fn()
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=learning_rate, weight_decay=0.01)

        best_loss = float("inf")
        loss_history = []

        # 3 sub-phases of increasing complexity (simple → moderate → full)
        for sub_phase in [1, 2, 3]:
            data = curriculum.generate(phase=sub_phase, num_samples=num_samples)

            # Signal augmentation: extend state vectors with synthetic signal features
            augmented_states = self._augment_states_synthetic(data.state_vectors)
            states_t = torch.tensor(augmented_states, dtype=torch.float32).to(self.device)
            act_disc_t = torch.tensor(data.action_discrete, dtype=torch.long).to(self.device)
            act_cont_t = torch.tensor(data.action_continuous, dtype=torch.float32).to(self.device)
            rewards_t = torch.tensor(data.rewards, dtype=torch.float32).to(self.device)

            phase_epochs = max(1, epochs // 3)
            for epoch in range(phase_epochs):
                self.model.train()
                total_loss = 0.0
                n_batches = 0
                indices = np.random.permutation(len(states_t))

                for i in range(0, len(states_t), batch_size):
                    batch_idx = indices[i:i + batch_size]
                    optimizer.zero_grad()

                    outputs = self.model(states_t[batch_idx])
                    targets = {
                        "action_discrete": act_disc_t[batch_idx],
                        "action_continuous": act_cont_t[batch_idx],
                        "rewards": rewards_t[batch_idx],
                    }
                    loss = loss_fn(outputs, targets)
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                    optimizer.step()

                    total_loss += loss.item()
                    n_batches += 1

                avg_loss = total_loss / max(1, n_batches)
                loss_history.append(avg_loss)
                if avg_loss < best_loss:
                    best_loss = avg_loss

        duration = time.time() - start
        logger.info(
            f"Phase 1 complete for {self.trm_type}@site{self.site_id}: "
            f"loss={best_loss:.4f}, {duration:.1f}s"
        )

        return {
            "phase": "engine_imitation",
            "stigmergic_phase": self.stigmergic_phase.name,
            "epochs": epochs,
            "final_loss": best_loss,
            "samples": num_samples * 3,
            "duration_seconds": duration,
            "loss_history": loss_history,
        }

    # =========================================================================
    # Phase 2: Context Learning (Supervised from expert overrides)
    # =========================================================================

    async def train_phase2(
        self,
        db,
        epochs: int = 50,
        learning_rate: float = 5e-5,
        batch_size: int = 32,
        min_samples: int = 500,
    ) -> Dict[str, Any]:
        """
        Phase 2: Fine-tune on human expert decision logs for this site.

        Requires ≥min_samples expert decisions. Loads from the per-TRM decision
        log tables filtered by site_id and is_expert/source=EXPERT_HUMAN.
        """
        import torch
        from sqlalchemy import select, func

        self._ensure_model()

        # Load expert decisions from the appropriate decision log table
        expert_data = await self._load_expert_decisions(db)
        num_expert = len(expert_data.get("states", []))

        if num_expert < min_samples:
            return {
                "skipped": True,
                "reason": f"Insufficient expert data ({num_expert} < {min_samples})",
                "expert_samples": num_expert,
            }

        start = time.time()

        # Signal augmentation: extend states with real signal context
        signal_contexts = expert_data.get("signal_contexts", [None] * num_expert)
        augmented = self._augment_states_from_context(expert_data["states"], signal_contexts)
        states_t = torch.tensor(augmented, dtype=torch.float32).to(self.device)
        actions_t = torch.tensor(expert_data["actions"], dtype=torch.float32).to(self.device)

        loss_fn = torch.nn.MSELoss()
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=learning_rate, weight_decay=0.01)

        best_loss = float("inf")
        loss_history = []

        for epoch in range(epochs):
            self.model.train()
            total_loss = 0.0
            n_batches = 0
            indices = np.random.permutation(len(states_t))

            for i in range(0, len(states_t), batch_size):
                batch_idx = indices[i:i + batch_size]
                optimizer.zero_grad()

                outputs = self.model(states_t[batch_idx])
                # Supervised loss on action outputs
                if "action_continuous" in outputs:
                    loss = loss_fn(outputs["action_continuous"], actions_t[batch_idx])
                elif "action_logits" in outputs:
                    loss = torch.nn.functional.cross_entropy(
                        outputs["action_logits"], actions_t[batch_idx].long()
                    )
                else:
                    # Fallback: use value head
                    loss = loss_fn(outputs["value"].squeeze(-1), actions_t[batch_idx, 0])

                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()

                total_loss += loss.item()
                n_batches += 1

            avg_loss = total_loss / max(1, n_batches)
            loss_history.append(avg_loss)
            if avg_loss < best_loss:
                best_loss = avg_loss

        duration = time.time() - start
        logger.info(
            f"Phase 2 complete for {self.trm_type}@site{self.site_id}: "
            f"loss={best_loss:.4f}, {num_expert} expert samples, {duration:.1f}s"
        )

        return {
            "phase": "context_learning",
            "stigmergic_phase": self.stigmergic_phase.name,
            "epochs": epochs,
            "final_loss": best_loss,
            "expert_samples": num_expert,
            "duration_seconds": duration,
            "loss_history": loss_history,
        }

    # =========================================================================
    # Phase 3: Outcome Optimization (RL/VFA from replay buffer)
    # =========================================================================

    async def train_phase3(
        self,
        db,
        epochs: int = 80,
        learning_rate: float = 1e-5,
        batch_size: int = 64,
        min_samples: int = 1000,
        gamma: float = 0.99,
        tau: float = 0.005,
    ) -> Dict[str, Any]:
        """
        Phase 3: RL fine-tuning from replay buffer with TD learning.

        Requires ≥min_samples outcome records. Uses Conservative Q-Learning
        (CQL) to prevent overestimation from logged data.
        """
        import torch

        self._ensure_model()

        # Load replay buffer entries for this site + trm_type
        replay_data = await self._load_replay_buffer(db)
        num_samples = len(replay_data.get("states", []))

        if num_samples < min_samples:
            return {
                "skipped": True,
                "reason": f"Insufficient replay data ({num_samples} < {min_samples})",
                "outcome_samples": num_samples,
            }

        start = time.time()

        # Signal augmentation for states and next_states
        signal_contexts = replay_data.get("signal_contexts", [None] * num_samples)
        next_signal_contexts = replay_data.get("next_signal_contexts", [None] * num_samples)
        augmented_s = self._augment_states_from_context(replay_data["states"], signal_contexts)
        augmented_ns = self._augment_states_from_context(replay_data["next_states"], next_signal_contexts)

        states_t = torch.tensor(augmented_s, dtype=torch.float32).to(self.device)
        next_states_t = torch.tensor(augmented_ns, dtype=torch.float32).to(self.device)
        rewards_t = torch.tensor(replay_data["rewards"], dtype=torch.float32).to(self.device)
        dones_t = torch.tensor(replay_data["dones"], dtype=torch.float32).to(self.device)

        # Cross-head reward augments the base reward when signal context is present
        cross_head_rewards = replay_data.get("cross_head_rewards")
        if cross_head_rewards is not None and self.cross_head_reward_weight > 0:
            xhr_t = torch.tensor(cross_head_rewards, dtype=torch.float32).to(self.device)
            rewards_t = rewards_t + self.cross_head_reward_weight * xhr_t

        # Compute outcome-gated sample weights (Bayesian posterior when DB available)
        is_expert_list = replay_data.get("is_expert", [False] * num_samples)
        override_eff_list = replay_data.get("override_effectiveness", [None] * num_samples)
        override_uid_list = replay_data.get("override_user_ids", [None] * num_samples)
        sample_weights = self._compute_sample_weights(
            is_expert_list, override_eff_list,
            override_user_ids=override_uid_list,
            trm_type=self.trm_type,
            db=db,
        )
        sample_weights_t = torch.tensor(sample_weights, dtype=torch.float32).to(self.device)

        # Target network for stable Q-learning
        import copy
        target_model = copy.deepcopy(self.model)
        target_model.eval()

        optimizer = torch.optim.AdamW(self.model.parameters(), lr=learning_rate, weight_decay=0.01)

        best_loss = float("inf")
        loss_history = []
        mean_rewards = []

        for epoch in range(epochs):
            self.model.train()
            total_loss = 0.0
            n_batches = 0
            indices = np.random.permutation(len(states_t))

            for i in range(0, len(states_t), batch_size):
                batch_idx = indices[i:i + batch_size]

                optimizer.zero_grad()

                # Current Q-values
                outputs = self.model(states_t[batch_idx])
                q_values = outputs["value"].squeeze(-1)

                # Target Q-values (Bellman)
                with torch.no_grad():
                    next_outputs = target_model(next_states_t[batch_idx])
                    next_q = next_outputs["value"].squeeze(-1)
                    target_q = rewards_t[batch_idx] + gamma * next_q * (1 - dones_t[batch_idx])

                # Weighted TD loss (outcome-gated sample weights)
                td_errors = (q_values - target_q) ** 2
                td_loss = (td_errors * sample_weights_t[batch_idx]).mean()

                # CQL penalty: penalize high Q-values on out-of-distribution actions
                cql_penalty = 0.1 * (q_values ** 2).mean()

                loss = td_loss + cql_penalty
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()

                # Soft update target network
                for param, target_param in zip(self.model.parameters(), target_model.parameters()):
                    target_param.data.copy_(tau * param.data + (1 - tau) * target_param.data)

                total_loss += loss.item()
                n_batches += 1

            avg_loss = total_loss / max(1, n_batches)
            loss_history.append(avg_loss)
            mean_rewards.append(float(rewards_t.mean()))
            if avg_loss < best_loss:
                best_loss = avg_loss

        duration = time.time() - start
        logger.info(
            f"Phase 3 complete for {self.trm_type}@site{self.site_id}: "
            f"loss={best_loss:.4f}, {num_samples} replay samples, {duration:.1f}s"
        )

        return {
            "phase": "outcome_optimization",
            "stigmergic_phase": self.stigmergic_phase.name,
            "epochs": epochs,
            "final_loss": best_loss,
            "outcome_samples": num_samples,
            "reward_mean": float(rewards_t.mean()),
            "cross_head_reward_weight": self.cross_head_reward_weight,
            "duration_seconds": duration,
            "loss_history": loss_history,
        }

    # =========================================================================
    # Data Loading Helpers
    # =========================================================================

    async def _load_expert_decisions(self, db) -> Dict[str, Any]:
        """Load expert decisions from the per-TRM decision log table for this site."""
        from sqlalchemy import select, text
        from app.models.trm_training_data import (
            ATPDecisionLog, RebalancingDecisionLog, PODecisionLog,
            OrderTrackingDecisionLog, SafetyStockDecisionLog,
            DecisionSource,
        )

        # Map TRM type → (log table model, state fields, action fields)
        table_map = {
            "atp_executor": (
                ATPDecisionLog,
                ["state_inventory", "state_pipeline", "state_backlog",
                 "state_demand_forecast", "state_available_atp",
                 "state_requested_qty", "state_priority"],
                ["qty_fulfilled"],
            ),
            "po_creation": (
                PODecisionLog,
                ["state_inventory", "state_pipeline", "state_backlog",
                 "state_reorder_point", "state_safety_stock",
                 "state_days_of_supply", "state_demand_forecast"],
                ["order_qty"],
            ),
            "inventory_buffer": (
                SafetyStockDecisionLog,
                ["state_baseline_ss", "state_current_dos",
                 "state_current_on_hand", "state_demand_cv",
                 "state_avg_daily_demand", "state_demand_trend",
                 "state_seasonal_index", "state_lead_time_days"],
                ["action_multiplier"],
            ),
            "order_tracking": (
                OrderTrackingDecisionLog,
                ["state_order_qty", "state_inventory_position",
                 "state_other_pending_orders", "days_from_expected",
                 "qty_variance"],
                [],  # discrete action — loaded separately
            ),
            "rebalancing": (
                RebalancingDecisionLog,
                [],  # Uses JSON state_features
                [],
            ),
        }

        if self.trm_type not in table_map:
            return {"states": [], "actions": []}

        model_cls, state_fields, action_fields = table_map[self.trm_type]

        query = select(model_cls).where(
            model_cls.source == DecisionSource.EXPERT_HUMAN,
        )
        # Filter by site_id if the model has it
        if hasattr(model_cls, "site_id"):
            query = query.where(model_cls.site_id == self.site_id)

        query = query.limit(10000)
        result = await db.execute(query)
        rows = result.scalars().all()

        states = []
        actions = []
        signal_contexts = []
        for row in rows:
            state = []
            for f in state_fields:
                val = getattr(row, f, 0) or 0
                state.append(float(val))
            states.append(state)

            action = []
            for f in action_fields:
                val = getattr(row, f, 0) or 0
                action.append(float(val))
            if not action:
                action = [0.0]
            actions.append(action)

            # Load signal context if available (Sprint 4 schema extension)
            signal_contexts.append(getattr(row, "signal_context", None))

        return {
            "states": np.array(states, dtype=np.float32) if states else np.empty((0,)),
            "actions": np.array(actions, dtype=np.float32) if actions else np.empty((0,)),
            "signal_contexts": signal_contexts,
        }

    async def _load_replay_buffer(self, db) -> Dict[str, Any]:
        """Load replay buffer entries for this site + trm_type."""
        from sqlalchemy import select
        from app.models.trm_training_data import TRMReplayBuffer

        query = select(TRMReplayBuffer).where(
            TRMReplayBuffer.site_id == self.site_id,
            TRMReplayBuffer.trm_type == self.trm_type,
        ).order_by(TRMReplayBuffer.priority.desc()).limit(50000)

        result = await db.execute(query)
        rows = result.scalars().all()

        states, next_states, rewards, dones = [], [], [], []
        signal_contexts, next_signal_contexts, cross_head_rewards = [], [], []
        is_expert_flags, override_effectiveness_flags, override_user_ids = [], [], []
        for row in rows:
            if row.state_vector and row.next_state_vector:
                states.append(row.state_vector)
                next_states.append(row.next_state_vector)
                rewards.append(row.reward)
                dones.append(1.0 if row.done else 0.0)
                signal_contexts.append(getattr(row, "signal_context", None))
                next_signal_contexts.append(getattr(row, "next_signal_context", None))
                cross_head_rewards.append(getattr(row, "cross_head_reward", 0.0) or 0.0)
                is_expert_flags.append(getattr(row, "is_expert", False))
                override_effectiveness_flags.append(
                    getattr(row, "override_effectiveness", None)
                )
                override_user_ids.append(
                    getattr(row, "override_user_id", None)
                )

        return {
            "states": np.array(states, dtype=np.float32) if states else np.empty((0,)),
            "next_states": np.array(next_states, dtype=np.float32) if next_states else np.empty((0,)),
            "rewards": np.array(rewards, dtype=np.float32) if rewards else np.empty((0,)),
            "dones": np.array(dones, dtype=np.float32) if dones else np.empty((0,)),
            "signal_contexts": signal_contexts,
            "next_signal_contexts": next_signal_contexts,
            "cross_head_rewards": np.array(cross_head_rewards, dtype=np.float32) if cross_head_rewards else np.empty((0,)),
            "is_expert": is_expert_flags,
            "override_effectiveness": override_effectiveness_flags,
            "override_user_ids": override_user_ids,
        }

    # =========================================================================
    # Outcome-Gated Sample Weights
    # =========================================================================

    @staticmethod
    def _compute_sample_weights(
        is_expert: list,
        override_effectiveness: list,
        override_user_ids: list = None,
        trm_type: str = None,
        db=None,
    ) -> "np.ndarray":
        """Compute per-sample weights using Bayesian posteriors when available.

        When a database session is provided, fetches the Beta posterior
        for each (user, trm_type) pair to derive training weights that
        reflect accumulated causal evidence across observability tiers.

        Fallback (no DB): uses hard-coded label mapping:
          - BENEFICIAL: 2.0  (proven good)
          - NEUTRAL: 1.0     (no measurable difference)
          - DETRIMENTAL: 0.3 (proven bad)
          - None: 0.5        (pending outcome)

        Non-expert samples always get weight 1.0.

        See docs/OVERRIDE_EFFECTIVENESS_METHODOLOGY.md for full rationale.
        """
        n = len(is_expert)
        weights = np.ones(n, dtype=np.float32)

        # Try Bayesian posterior lookup if we have the needed context
        use_bayesian = (
            db is not None
            and override_user_ids is not None
            and trm_type is not None
        )

        if use_bayesian:
            try:
                from app.services.override_effectiveness_service import (
                    OverrideEffectivenessService,
                )
                for i in range(n):
                    if is_expert[i]:
                        uid = override_user_ids[i] if i < len(override_user_ids) else None
                        weights[i] = OverrideEffectivenessService.get_training_weight(
                            db=db, user_id=uid, trm_type=trm_type,
                        )
                return weights
            except Exception:
                pass  # Fall through to hard-coded mapping

        # Hard-coded fallback (used when no DB or import fails)
        for i in range(n):
            if is_expert[i]:
                eff = override_effectiveness[i]
                if eff == "BENEFICIAL":
                    weights[i] = 2.0
                elif eff == "NEUTRAL":
                    weights[i] = 1.0
                elif eff == "DETRIMENTAL":
                    weights[i] = 0.3
                else:  # None — no outcome yet
                    weights[i] = 0.5
        return weights

    # =========================================================================
    # Loss Function (reused from powell_training_service)
    # =========================================================================

    def _create_loss_fn(self):
        """Create the appropriate loss function for this TRM type."""
        import torch.nn as nn

        class _MultiHeadLoss(nn.Module):
            def __init__(self, discrete_key="action_logits", use_bce=False):
                super().__init__()
                self.ce = nn.CrossEntropyLoss()
                self.bce = nn.BCEWithLogitsLoss()
                self.mse = nn.MSELoss()
                self.discrete_key = discrete_key
                self.use_bce = use_bce

            def forward(self, outputs, targets):
                if self.use_bce:
                    disc_loss = self.bce(
                        outputs[self.discrete_key].squeeze(-1),
                        targets["action_discrete"].float()
                    )
                else:
                    disc_loss = self.ce(outputs[self.discrete_key], targets["action_discrete"])
                value_loss = self.mse(outputs["value"].squeeze(-1), targets["rewards"])
                return disc_loss + 0.3 * value_loss

        if self.trm_type == "rebalancing":
            return _MultiHeadLoss(discrete_key="transfer_logit", use_bce=True)
        elif self.trm_type == "order_tracking":
            class _OTLoss(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.ce = nn.CrossEntropyLoss()
                    self.mse = nn.MSELoss()
                def forward(self, outputs, targets):
                    exc = self.ce(outputs["exception_logits"], targets["action_discrete"])
                    sev = self.ce(outputs["severity_logits"], targets["action_continuous"][:, 0].long())
                    act = self.ce(outputs["action_logits"], targets["action_continuous"][:, 1].long())
                    val = self.mse(outputs["value"].squeeze(-1), targets["rewards"])
                    return exc + 0.7 * sev + 0.8 * act + 0.3 * val
            return _OTLoss()
        else:
            return _MultiHeadLoss(discrete_key="action_logits")


    # =========================================================================
    # Stigmergic Curriculum Orchestrator
    # =========================================================================

    async def train_stigmergic_curriculum(
        self,
        db=None,
        epochs_per_phase: int = 30,
        num_samples: int = 5000,
    ) -> Dict[str, Any]:
        """Execute the full stigmergic curriculum: signal phases × learning phases.

        Schedule (3 × 3 = 9 stages, but we skip combinations where data is absent):

        Signal Phase 1 (NO_SIGNALS):
            → Learning Phase 1 (BC): Baseline behavioral cloning
        Signal Phase 2 (URGENCY_ONLY):
            → Learning Phase 1 (BC): BC with urgency-augmented states
            → Learning Phase 2 (Expert): Expert overrides with urgency context
        Signal Phase 3 (FULL_SIGNALS):
            → Learning Phase 1 (BC): BC with full signal features
            → Learning Phase 2 (Expert): Expert overrides with full signal context
            → Learning Phase 3 (RL): TD learning with cross-head reward

        Returns:
            Combined results dict with per-stage outcomes.
        """
        all_results = []
        total_start = time.time()

        # --- Signal Phase 1: NO_SIGNALS (warm-start baseline) ---
        self.stigmergic_phase = StigmergicPhase.NO_SIGNALS
        logger.info(f"Stigmergic curriculum: NO_SIGNALS × Phase 1 for {self.trm_type}@site{self.site_id}")
        r = await self.train_phase1(epochs=epochs_per_phase, num_samples=num_samples)
        all_results.append(r)

        version = 1
        self.save_checkpoint(version, extra_meta={"stigmergic_phase": "NO_SIGNALS", "learning_phase": 1})

        # --- Signal Phase 2: URGENCY_ONLY ---
        self.stigmergic_phase = StigmergicPhase.URGENCY_ONLY

        logger.info(f"Stigmergic curriculum: URGENCY_ONLY × Phase 1 for {self.trm_type}@site{self.site_id}")
        r = await self.train_phase1(epochs=epochs_per_phase, num_samples=num_samples)
        all_results.append(r)

        if db is not None:
            logger.info(f"Stigmergic curriculum: URGENCY_ONLY × Phase 2 for {self.trm_type}@site{self.site_id}")
            r = await self.train_phase2(db, epochs=epochs_per_phase)
            all_results.append(r)

        version = 2
        self.save_checkpoint(version, extra_meta={"stigmergic_phase": "URGENCY_ONLY", "learning_phase": 2})

        # --- Signal Phase 3: FULL_SIGNALS ---
        self.stigmergic_phase = StigmergicPhase.FULL_SIGNALS

        logger.info(f"Stigmergic curriculum: FULL_SIGNALS × Phase 1 for {self.trm_type}@site{self.site_id}")
        r = await self.train_phase1(epochs=epochs_per_phase, num_samples=num_samples)
        all_results.append(r)

        if db is not None:
            logger.info(f"Stigmergic curriculum: FULL_SIGNALS × Phase 2 for {self.trm_type}@site{self.site_id}")
            r = await self.train_phase2(db, epochs=epochs_per_phase)
            all_results.append(r)

            logger.info(f"Stigmergic curriculum: FULL_SIGNALS × Phase 3 for {self.trm_type}@site{self.site_id}")
            r = await self.train_phase3(db, epochs=epochs_per_phase)
            all_results.append(r)

        version = 3
        self.save_checkpoint(version, extra_meta={"stigmergic_phase": "FULL_SIGNALS", "learning_phase": 3})

        total_duration = time.time() - total_start
        logger.info(
            f"Stigmergic curriculum complete for {self.trm_type}@site{self.site_id}: "
            f"{len(all_results)} stages, {total_duration:.1f}s"
        )

        return {
            "trm_type": self.trm_type,
            "site_id": self.site_id,
            "stages": all_results,
            "total_stages": len(all_results),
            "total_duration_seconds": total_duration,
        }


def find_best_checkpoint(
    trm_type: str,
    site_id: int,
    master_type: str = "",
    config_id: int = 0,
    checkpoint_dir: Optional[Path] = None,
) -> Optional[str]:
    """
    Checkpoint fallback resolution (searches config-namespaced first):
    1. Config-namespaced site-specific: config_{id}/trm/trm_{type}_site{site_id}_v*.pt
    2. Flat site-specific: trm_{type}_site{site_id}_v*.pt (legacy)
    3. Base model: trm_{type}_base_{master_type}.pt
    4. Legacy: trm_{type}_{config_id}.pt (backward compat)
    5. Legacy subdir: trm_*/trm_{type}.pt (e.g. trm_food_dist/)
    """
    cdir = checkpoint_dir or CHECKPOINT_DIR

    # 1. Config-namespaced site-specific (latest version)
    if config_id:
        config_trm_dir = cdir / f"config_{config_id}" / "trm"
        if config_trm_dir.exists():
            site_checkpoints = sorted(
                config_trm_dir.glob(f"trm_{trm_type}_site{site_id}_v*.pt"),
                reverse=True,
            )
            if site_checkpoints:
                return str(site_checkpoints[0])

    # 2. Flat site-specific (legacy)
    site_checkpoints = sorted(
        cdir.glob(f"trm_{trm_type}_site{site_id}_v*.pt"),
        reverse=True,
    )
    if site_checkpoints:
        return str(site_checkpoints[0])

    # 3. Base model for master type
    base_path = cdir / f"trm_{trm_type}_base_{master_type.lower()}.pt"
    if base_path.exists():
        return str(base_path)

    # 4. Legacy config-level checkpoint
    if config_id:
        legacy_path = cdir / f"trm_{trm_type}_{config_id}.pt"
        if legacy_path.exists():
            return str(legacy_path)

    # 5. Legacy subdir (e.g. trm_food_dist/trm_atp_executor.pt)
    for subdir in sorted(cdir.glob("trm_*/")):
        legacy = subdir / f"trm_{trm_type}.pt"
        if legacy.exists():
            return str(legacy)

    return None
