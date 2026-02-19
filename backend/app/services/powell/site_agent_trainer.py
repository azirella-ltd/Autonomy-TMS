"""
SiteAgent Training Pipeline

Multi-task training for shared encoder + task heads.
Supports behavioral cloning, supervised learning, and RL fine-tuning.

Training Phases:
1. Behavioral Cloning: Warmup from expert decisions
2. Multi-task Supervised: Joint training all heads
3. RL Fine-tuning: Optional improvement beyond expert
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from pathlib import Path
import json
import logging

from .site_agent_model import SiteAgentModel, SiteAgentModelConfig

logger = logging.getLogger(__name__)


class TrainingPhase(Enum):
    BEHAVIORAL_CLONING = "bc"
    MULTI_TASK_SUPERVISED = "supervised"
    RL_FINETUNING = "rl"


@dataclass
class TrainingConfig:
    """Configuration for SiteAgent training"""
    # General
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
    seed: int = 42

    # Phase 1: Behavioral cloning
    bc_epochs: int = 10
    bc_lr: float = 1e-3

    # Phase 2: Multi-task supervised
    supervised_epochs: int = 50
    supervised_lr: float = 1e-4

    # Phase 3: RL fine-tuning (optional)
    rl_epochs: int = 20
    rl_lr: float = 1e-5
    gamma: float = 0.99

    # Task weights for multi-task loss
    task_weights: Dict[str, float] = field(default_factory=lambda: {
        'atp': 1.0,
        'inventory': 1.0,
        'po_timing': 1.0
    })

    # Regularization
    weight_decay: float = 1e-4
    gradient_clip: float = 1.0

    # Batch sizes
    batch_size: int = 64
    val_batch_size: int = 128

    # Checkpointing
    checkpoint_dir: str = "checkpoints/site_agent"
    save_every_epochs: int = 10

    # Early stopping
    early_stopping_patience: int = 10
    early_stopping_min_delta: float = 1e-4


class SiteAgentDataset(Dataset):
    """
    Dataset for SiteAgent training.

    Each sample contains:
    - State features (for encoder)
    - Task-specific context and labels
    - Outcomes (for RL)
    """

    def __init__(
        self,
        data: List[Dict],
        config: SiteAgentModelConfig
    ):
        self.data = data
        self.config = config

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx) -> Dict[str, torch.Tensor]:
        sample = self.data[idx]

        # Default dimensions based on config
        n_products = 10  # Default
        history_window = 12
        forecast_horizon = 8
        lead_time_buckets = 4

        return {
            # State features for encoder
            'inventory': torch.tensor(
                sample.get('inventory', [0] * n_products),
                dtype=torch.float32
            ),
            'pipeline': torch.tensor(
                sample.get('pipeline', [[0] * lead_time_buckets] * n_products),
                dtype=torch.float32
            ),
            'backlog': torch.tensor(
                sample.get('backlog', [0] * n_products),
                dtype=torch.float32
            ),
            'demand_history': torch.tensor(
                sample.get('demand_history', [[0] * history_window] * n_products),
                dtype=torch.float32
            ),
            'forecasts': torch.tensor(
                sample.get('forecasts', [[0] * forecast_horizon] * n_products),
                dtype=torch.float32
            ),

            # Task-specific contexts and labels
            'atp_context': torch.tensor(
                sample.get('atp_context', [0] * self.config.order_context_dim),
                dtype=torch.float32
            ),
            'atp_shortage': torch.tensor(
                [sample.get('atp_shortage', 0)],
                dtype=torch.float32
            ),
            'atp_label': torch.tensor(
                sample.get('atp_label', [1, 0, 0, 0]),  # Default: partial fill
                dtype=torch.float32
            ),

            'inv_label': torch.tensor(
                sample.get('inv_label', [1.0, 1.0]),  # Default: no adjustment
                dtype=torch.float32
            ),

            'po_context': torch.tensor(
                sample.get('po_context', [0] * self.config.po_context_dim),
                dtype=torch.float32
            ),
            'po_label': torch.tensor(
                sample.get('po_label', [1, 0, 0]),  # Default: order now
                dtype=torch.float32
            ),

            # Outcomes for RL
            'outcome_service_level': torch.tensor(
                [sample.get('outcome_sl', 0.95)],
                dtype=torch.float32
            ),
            'outcome_cost': torch.tensor(
                [sample.get('outcome_cost', 0)],
                dtype=torch.float32
            ),
        }

    @classmethod
    def from_file(cls, path: str, config: SiteAgentModelConfig) -> 'SiteAgentDataset':
        """Load dataset from JSON file"""
        with open(path) as f:
            data = json.load(f)
        return cls(data, config)


class SiteAgentTrainer:
    """
    Trainer for SiteAgent model.

    Implements multi-phase training:
    1. Behavioral cloning (warmup from expert decisions)
    2. Multi-task supervised (joint training all heads)
    3. RL fine-tuning (optional, improves beyond expert)
    """

    def __init__(
        self,
        model: SiteAgentModel,
        config: TrainingConfig
    ):
        self.model = model.to(config.device)
        self.config = config
        self.device = config.device

        # Optimizers (created per phase)
        self.optimizer: Optional[optim.Optimizer] = None

        # Loss functions
        self.ce_loss = nn.CrossEntropyLoss()
        self.mse_loss = nn.MSELoss()
        self.bce_loss = nn.BCELoss()

        # Metrics tracking
        self.metrics_history: Dict[str, List[float]] = {
            'train_loss': [],
            'val_loss': [],
            'atp_accuracy': [],
            'inv_mae': [],
            'po_accuracy': []
        }

        # Best model tracking
        self.best_val_loss = float('inf')
        self.epochs_without_improvement = 0

    def train(
        self,
        train_data: SiteAgentDataset,
        val_data: Optional[SiteAgentDataset] = None,
        phases: Optional[List[TrainingPhase]] = None
    ) -> Dict[str, Any]:
        """
        Run full training pipeline.

        Args:
            train_data: Training dataset
            val_data: Validation dataset (optional)
            phases: Which phases to run (default: BC + supervised)

        Returns:
            Training results and metrics
        """
        if phases is None:
            phases = [
                TrainingPhase.BEHAVIORAL_CLONING,
                TrainingPhase.MULTI_TASK_SUPERVISED
            ]

        # Set seed for reproducibility
        torch.manual_seed(self.config.seed)

        train_loader = DataLoader(
            train_data,
            batch_size=self.config.batch_size,
            shuffle=True,
            num_workers=0
        )

        val_loader = None
        if val_data:
            val_loader = DataLoader(
                val_data,
                batch_size=self.config.val_batch_size,
                num_workers=0
            )

        results: Dict[str, Any] = {}

        for phase in phases:
            logger.info(f"Starting training phase: {phase.value}")

            if phase == TrainingPhase.BEHAVIORAL_CLONING:
                results['bc'] = self._train_behavioral_cloning(train_loader, val_loader)

            elif phase == TrainingPhase.MULTI_TASK_SUPERVISED:
                results['supervised'] = self._train_multi_task(train_loader, val_loader)

            elif phase == TrainingPhase.RL_FINETUNING:
                results['rl'] = self._train_rl(train_loader)

        # Save final checkpoint
        self._save_checkpoint('final')

        return results

    def _train_behavioral_cloning(
        self,
        train_loader: DataLoader,
        val_loader: Optional[DataLoader]
    ) -> Dict[str, Any]:
        """
        Phase 1: Behavioral cloning from expert decisions.

        Simple supervised learning to warmup the model.
        """
        self.optimizer = optim.Adam(
            self.model.parameters(),
            lr=self.config.bc_lr,
            weight_decay=self.config.weight_decay
        )

        best_val_loss = float('inf')

        for epoch in range(self.config.bc_epochs):
            self.model.train()
            epoch_loss = 0.0

            for batch in train_loader:
                batch = {k: v.to(self.device) for k, v in batch.items()}

                self.optimizer.zero_grad()
                loss = self._compute_supervised_loss(batch)
                loss.backward()

                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(),
                    self.config.gradient_clip
                )

                self.optimizer.step()
                epoch_loss += loss.item()

            avg_loss = epoch_loss / len(train_loader)
            self.metrics_history['train_loss'].append(avg_loss)

            # Validation
            if val_loader:
                val_loss = self._validate(val_loader)
                self.metrics_history['val_loss'].append(val_loss)

                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    self._save_checkpoint('bc_best')

            logger.info(f"BC Epoch {epoch+1}/{self.config.bc_epochs}, Loss: {avg_loss:.4f}")

        return {'final_loss': avg_loss, 'best_val_loss': best_val_loss}

    def _train_multi_task(
        self,
        train_loader: DataLoader,
        val_loader: Optional[DataLoader]
    ) -> Dict[str, Any]:
        """
        Phase 2: Multi-task supervised training.

        Joint training of encoder + all heads with task-weighted loss.
        """
        self.optimizer = optim.Adam(
            self.model.parameters(),
            lr=self.config.supervised_lr,
            weight_decay=self.config.weight_decay
        )

        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer, mode='min', factor=0.5, patience=5
        )

        best_val_loss = float('inf')
        self.epochs_without_improvement = 0

        for epoch in range(self.config.supervised_epochs):
            self.model.train()
            epoch_losses: Dict[str, float] = {'total': 0, 'atp': 0, 'inv': 0, 'po': 0}

            for batch in train_loader:
                batch = {k: v.to(self.device) for k, v in batch.items()}

                self.optimizer.zero_grad()

                # Compute per-task losses
                losses = self._compute_per_task_losses(batch)

                # Weighted sum
                total_loss = sum(
                    self.config.task_weights.get(task, 1.0) * loss
                    for task, loss in losses.items()
                )

                total_loss.backward()

                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(),
                    self.config.gradient_clip
                )

                self.optimizer.step()

                epoch_losses['total'] += total_loss.item()
                for task, loss in losses.items():
                    epoch_losses[task] += loss.item()

            # Average losses
            for key in epoch_losses:
                epoch_losses[key] /= len(train_loader)

            # Validation and scheduling
            if val_loader:
                val_loss = self._validate(val_loader)
                scheduler.step(val_loss)

                if val_loss < best_val_loss - self.config.early_stopping_min_delta:
                    best_val_loss = val_loss
                    self.epochs_without_improvement = 0
                    self._save_checkpoint('supervised_best')
                else:
                    self.epochs_without_improvement += 1

                # Early stopping
                if self.epochs_without_improvement >= self.config.early_stopping_patience:
                    logger.info(f"Early stopping at epoch {epoch+1}")
                    break

            if (epoch + 1) % self.config.save_every_epochs == 0:
                self._save_checkpoint(f'epoch_{epoch+1}')

            logger.info(
                f"Supervised Epoch {epoch+1}/{self.config.supervised_epochs}, "
                f"Loss: {epoch_losses['total']:.4f} "
                f"(ATP: {epoch_losses['atp']:.4f}, "
                f"Inv: {epoch_losses['inv']:.4f}, "
                f"PO: {epoch_losses['po']:.4f})"
            )

        return {'final_loss': epoch_losses['total'], 'best_val_loss': best_val_loss}

    def _compute_supervised_loss(self, batch: Dict[str, torch.Tensor]) -> torch.Tensor:
        """Compute combined supervised loss"""
        losses = self._compute_per_task_losses(batch)
        return sum(losses.values())

    def _compute_per_task_losses(
        self,
        batch: Dict[str, torch.Tensor]
    ) -> Dict[str, torch.Tensor]:
        """Compute loss for each task head"""

        # Encode state (shared)
        state_embedding = self.model.encode_state(
            inventory=batch['inventory'],
            pipeline=batch['pipeline'],
            backlog=batch['backlog'],
            demand_history=batch['demand_history'],
            forecasts=batch['forecasts']
        )

        losses = {}

        # ATP exception head
        atp_output = self.model.forward_atp_exception(
            state_embedding,
            batch['atp_context'],
            batch['atp_shortage']
        )
        losses['atp'] = self.ce_loss(
            atp_output['action_probs'],
            batch['atp_label'].argmax(dim=-1)
        )

        # Inventory planning head
        inv_output = self.model.forward_inventory_planning(state_embedding)
        inv_pred = torch.cat([inv_output['ss_multiplier'], inv_output['rop_multiplier']], dim=-1)
        losses['inv'] = self.mse_loss(inv_pred, batch['inv_label'])

        # PO timing head
        po_output = self.model.forward_po_timing(state_embedding, batch['po_context'])
        losses['po'] = self.ce_loss(
            po_output['timing_probs'],
            batch['po_label'].argmax(dim=-1)
        )

        return losses

    def _validate(self, val_loader: DataLoader) -> float:
        """Run validation and return loss"""
        self.model.eval()
        total_loss = 0.0

        with torch.no_grad():
            for batch in val_loader:
                batch = {k: v.to(self.device) for k, v in batch.items()}
                loss = self._compute_supervised_loss(batch)
                total_loss += loss.item()

        return total_loss / len(val_loader)

    def _train_rl(self, train_loader: DataLoader) -> Dict[str, Any]:
        """
        Phase 3: RL fine-tuning (optional).

        Uses outcome data to improve beyond expert performance.
        """
        logger.info("RL fine-tuning not yet implemented - skipping")
        return {'status': 'skipped'}

    def _save_checkpoint(self, name: str):
        """Save model checkpoint"""
        checkpoint_dir = Path(self.config.checkpoint_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        checkpoint_path = checkpoint_dir / f"{name}.pt"

        torch.save({
            'model_state_dict': self.model.state_dict(),
            'model_config': self.model.config,
            'training_config': self.config,
            'metrics_history': self.metrics_history,
        }, checkpoint_path)

        logger.info(f"Saved checkpoint: {checkpoint_path}")

    @classmethod
    def load_checkpoint(
        cls,
        checkpoint_path: str,
        config: Optional[TrainingConfig] = None
    ) -> Tuple['SiteAgentTrainer', SiteAgentModel]:
        """Load trainer and model from checkpoint"""
        device = config.device if config else ("cuda" if torch.cuda.is_available() else "cpu")
        checkpoint = torch.load(checkpoint_path, map_location=device)

        model_config = checkpoint['model_config']
        model = SiteAgentModel(model_config)
        model.load_state_dict(checkpoint['model_state_dict'])

        training_config = config or checkpoint.get('training_config', TrainingConfig())
        trainer = cls(model, training_config)
        trainer.metrics_history = checkpoint.get('metrics_history', trainer.metrics_history)

        return trainer, model

    def compute_metrics(
        self,
        val_loader: DataLoader
    ) -> Dict[str, float]:
        """Compute detailed metrics on validation set"""
        self.model.eval()

        atp_correct = 0
        atp_total = 0
        inv_mae = 0.0
        po_correct = 0
        po_total = 0

        with torch.no_grad():
            for batch in val_loader:
                batch = {k: v.to(self.device) for k, v in batch.items()}

                state_embedding = self.model.encode_state(
                    inventory=batch['inventory'],
                    pipeline=batch['pipeline'],
                    backlog=batch['backlog'],
                    demand_history=batch['demand_history'],
                    forecasts=batch['forecasts']
                )

                # ATP accuracy
                atp_output = self.model.forward_atp_exception(
                    state_embedding, batch['atp_context'], batch['atp_shortage']
                )
                atp_pred = atp_output['action_probs'].argmax(dim=-1)
                atp_true = batch['atp_label'].argmax(dim=-1)
                atp_correct += (atp_pred == atp_true).sum().item()
                atp_total += len(atp_pred)

                # Inventory MAE
                inv_output = self.model.forward_inventory_planning(state_embedding)
                inv_pred = torch.cat([inv_output['ss_multiplier'], inv_output['rop_multiplier']], dim=-1)
                inv_mae += (inv_pred - batch['inv_label']).abs().mean().item() * len(inv_pred)

                # PO accuracy
                po_output = self.model.forward_po_timing(state_embedding, batch['po_context'])
                po_pred = po_output['timing_probs'].argmax(dim=-1)
                po_true = batch['po_label'].argmax(dim=-1)
                po_correct += (po_pred == po_true).sum().item()
                po_total += len(po_pred)

        return {
            'atp_accuracy': atp_correct / atp_total if atp_total > 0 else 0,
            'inventory_mae': inv_mae / atp_total if atp_total > 0 else 0,
            'po_accuracy': po_correct / po_total if po_total > 0 else 0
        }
