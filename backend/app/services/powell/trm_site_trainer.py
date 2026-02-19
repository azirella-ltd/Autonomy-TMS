"""
Per-Site TRM Trainer — Learning-Depth Curriculum

Trains one TRM model for one (site, trm_type) pair through 3 phases:
  Phase 1: Engine Imitation (BC) — match deterministic engine baselines
  Phase 2: Context Learning (Supervised) — learn from expert override logs
  Phase 3: Outcome Optimization (RL/VFA) — improve beyond expert from replay buffer

Usage:
    trainer = TRMSiteTrainer(
        trm_type="atp_executor", site_id=42, site_name="SLC DC",
        master_type="INVENTORY", group_id=1, config_id=1, device="cpu"
    )
    result = await trainer.train_phase1(epochs=20)
    result = await trainer.train_phase2(db, epochs=50)
    result = await trainer.train_phase3(db, epochs=80)
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

import numpy as np

logger = logging.getLogger(__name__)

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
        group_id: int,
        config_id: int,
        device: str = "cpu",
        checkpoint_dir: Optional[Path] = None,
    ):
        self.trm_type = trm_type
        self.site_id = site_id
        self.site_name = site_name
        self.master_type = master_type
        self.group_id = group_id
        self.config_id = config_id
        self.device = device
        self.checkpoint_dir = checkpoint_dir or CHECKPOINT_DIR

        self.model = None
        self.model_cls = None
        self.state_dim = None

    def _ensure_model(self):
        """Lazily create the TRM model on first use."""
        if self.model is not None:
            return

        try:
            import torch
            from app.models.trm import MODEL_REGISTRY
        except ImportError:
            raise RuntimeError("PyTorch not available for TRM training")

        if self.trm_type not in MODEL_REGISTRY:
            raise ValueError(f"Unknown TRM type: {self.trm_type}")

        self.model_cls, self.state_dim = MODEL_REGISTRY[self.trm_type]
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

            states_t = torch.tensor(data.state_vectors, dtype=torch.float32).to(self.device)
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
        states_t = torch.tensor(expert_data["states"], dtype=torch.float32).to(self.device)
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

        states_t = torch.tensor(replay_data["states"], dtype=torch.float32).to(self.device)
        next_states_t = torch.tensor(replay_data["next_states"], dtype=torch.float32).to(self.device)
        rewards_t = torch.tensor(replay_data["rewards"], dtype=torch.float32).to(self.device)
        dones_t = torch.tensor(replay_data["dones"], dtype=torch.float32).to(self.device)

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

                # TD loss
                td_loss = torch.nn.functional.mse_loss(q_values, target_q)

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
            "epochs": epochs,
            "final_loss": best_loss,
            "outcome_samples": num_samples,
            "reward_mean": float(rewards_t.mean()),
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
            "safety_stock": (
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

        return {
            "states": np.array(states, dtype=np.float32) if states else np.empty((0,)),
            "actions": np.array(actions, dtype=np.float32) if actions else np.empty((0,)),
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
        for row in rows:
            if row.state_vector and row.next_state_vector:
                states.append(row.state_vector)
                next_states.append(row.next_state_vector)
                rewards.append(row.reward)
                dones.append(1.0 if row.done else 0.0)

        return {
            "states": np.array(states, dtype=np.float32) if states else np.empty((0,)),
            "next_states": np.array(next_states, dtype=np.float32) if next_states else np.empty((0,)),
            "rewards": np.array(rewards, dtype=np.float32) if rewards else np.empty((0,)),
            "dones": np.array(dones, dtype=np.float32) if dones else np.empty((0,)),
        }

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


def find_best_checkpoint(
    trm_type: str,
    site_id: int,
    master_type: str = "",
    config_id: int = 0,
    checkpoint_dir: Optional[Path] = None,
) -> Optional[str]:
    """
    Checkpoint fallback resolution:
    1. Site-specific: trm_{type}_site{site_id}_v*.pt (latest version)
    2. Base model: trm_{type}_base_{master_type}.pt
    3. Legacy: trm_{type}_{config_id}.pt (backward compat)
    """
    cdir = checkpoint_dir or CHECKPOINT_DIR

    # 1. Site-specific (latest version)
    site_checkpoints = sorted(
        cdir.glob(f"trm_{trm_type}_site{site_id}_v*.pt"),
        reverse=True,
    )
    if site_checkpoints:
        return str(site_checkpoints[0])

    # 2. Base model for master type
    base_path = cdir / f"trm_{trm_type}_base_{master_type.lower()}.pt"
    if base_path.exists():
        return str(base_path)

    # 3. Legacy config-level checkpoint
    if config_id:
        legacy_path = cdir / f"trm_{trm_type}_{config_id}.pt"
        if legacy_path.exists():
            return str(legacy_path)

    return None
