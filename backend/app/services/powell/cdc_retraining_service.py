"""
CDC Retraining Service

Bridges CDC triggers to TRM model retraining, closing the Powell SDAM loop:
  CDC detects deviation → evaluate retraining need → train model → checkpoint → reload

Pipeline:
1. CDC fires a trigger (TriggerEvent with FULL_CFA)
2. Check if retraining is warranted (enough decisions with outcomes)
3. Load decisions via SiteAgentDecisionTracker.get_decisions_for_training()
4. Convert to TrainingRecords and feed to TRMTrainer.add_experience()
5. Execute TRMTrainer.train() (Offline RL / CQL for safety)
6. Save checkpoint to filesystem + powell_site_agent_checkpoints
7. Reload model in SiteAgent

Safety:
- Offline RL (CQL) prevents distribution shift from logged data
- New model loss compared to current — skip if regression > 10%
- Cooldown prevents excessive training (min 6 hours between runs)
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import uuid
import os
import logging

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.models.powell_decision import (
    SiteAgentDecision,
    SiteAgentCheckpoint,
    CDCTriggerLog,
)
from app.services.powell.trm_trainer import (
    TRMTrainer,
    TrainingConfig,
    TrainingMethod,
    TrainingResult,
    RewardCalculator,
)
from app.services.powell.integration.decision_integration import SiteAgentDecisionTracker
from app.services.powell.cdc_monitor import TriggerEvent

logger = logging.getLogger(__name__)

# Minimum decisions with outcomes before retraining is considered
MIN_TRAINING_EXPERIENCES = 100

# Minimum hours between training runs for the same site
RETRAIN_COOLDOWN_HOURS = 6

# Maximum regression in loss before rejecting a new model
MAX_REGRESSION_PCT = 0.10

# Default checkpoint directory
CHECKPOINT_DIR = "checkpoints"


class CDCRetrainingService:
    """
    Bridges CDC triggers to TRM model retraining.

    Evaluates whether enough new experiences have accumulated to warrant
    retraining, then executes the full pipeline from data loading to
    checkpoint deployment.
    """

    def __init__(self, db: Session, site_key: str, group_id: int):
        self.db = db
        self.site_key = site_key
        self.group_id = group_id
        self.decision_tracker = SiteAgentDecisionTracker(db)
        self.reward_calculator = RewardCalculator()

    def evaluate_retraining_need(self, skip_trigger_check: bool = False) -> bool:
        """
        Check if enough new experiences exist to justify retraining.

        Criteria:
        1. At least MIN_TRAINING_EXPERIENCES decisions with outcomes
           since the last training checkpoint
        2. At least one CDC trigger in the last 24 hours (unless skip_trigger_check)
        3. No training run in the last RETRAIN_COOLDOWN_HOURS
        """
        now = datetime.utcnow()

        # Check cooldown: when was the last checkpoint created?
        latest_checkpoint = (
            self.db.query(SiteAgentCheckpoint)
            .filter(
                SiteAgentCheckpoint.site_key == self.site_key,
                SiteAgentCheckpoint.is_active == True,
            )
            .order_by(desc(SiteAgentCheckpoint.created_at))
            .first()
        )

        if latest_checkpoint and latest_checkpoint.created_at:
            elapsed = now - latest_checkpoint.created_at
            if elapsed < timedelta(hours=RETRAIN_COOLDOWN_HOURS):
                logger.debug(
                    f"Retraining cooldown: {elapsed.total_seconds() / 3600:.1f}h "
                    f"since last training for {self.site_key}"
                )
                return False

        # Count decisions with outcomes since last checkpoint
        since = latest_checkpoint.created_at if latest_checkpoint else now - timedelta(days=90)
        experience_count = (
            self.db.query(func.count(SiteAgentDecision.id))
            .filter(
                SiteAgentDecision.site_key == self.site_key,
                SiteAgentDecision.actual_outcome.isnot(None),
                SiteAgentDecision.reward_signal.isnot(None),
                SiteAgentDecision.timestamp > since,
            )
            .scalar()
        ) or 0

        if experience_count < MIN_TRAINING_EXPERIENCES:
            logger.debug(
                f"Not enough experiences for {self.site_key}: "
                f"{experience_count}/{MIN_TRAINING_EXPERIENCES}"
            )
            return False

        # Check for recent CDC trigger
        recent_trigger_count = (
            self.db.query(func.count(CDCTriggerLog.id))
            .filter(
                CDCTriggerLog.site_key == self.site_key,
                CDCTriggerLog.triggered == True,
                CDCTriggerLog.timestamp > now - timedelta(hours=24),
            )
            .scalar()
        ) or 0

        if recent_trigger_count == 0 and not skip_trigger_check:
            logger.debug(f"No recent CDC triggers for {self.site_key}")
            return False

        logger.info(
            f"Retraining warranted for {self.site_key}: "
            f"{experience_count} experiences, {recent_trigger_count} recent triggers"
        )
        return True

    def execute_retraining(
        self,
        trigger_event: Optional[TriggerEvent] = None,
        training_method: TrainingMethod = TrainingMethod.OFFLINE_RL,
    ) -> Optional[TrainingResult]:
        """
        Execute the full retraining pipeline.

        Steps:
        1. Load decisions with outcomes from DB
        2. Convert to training experiences
        3. Feed to TRMTrainer
        4. Train model
        5. Compare loss vs current checkpoint
        6. Save checkpoint if improved
        7. Record in DB

        Returns:
            TrainingResult if training succeeded, None if skipped/failed.
        """
        logger.info(f"Starting CDC retraining for {self.site_key}")

        # Step 1: Load decisions
        decisions = self.decision_tracker.get_decisions_for_training(
            site_key=self.site_key,
            with_outcomes=True,
            limit=5000,
        )

        if len(decisions) < MIN_TRAINING_EXPERIENCES:
            logger.info(
                f"Skipping retraining: only {len(decisions)} decisions "
                f"(need {MIN_TRAINING_EXPERIENCES})"
            )
            return None

        # Step 2: Get or create model
        model = self._get_or_create_model()
        if model is None:
            logger.warning(f"Could not create model for {self.site_key}")
            return None

        # Step 3: Create trainer and feed experiences
        config = TrainingConfig(
            method=training_method,
            learning_rate=1e-4,
            batch_size=min(64, len(decisions) // 4),
            epochs=50,
        )
        trainer = TRMTrainer(model=model, config=config, reward_calculator=self.reward_calculator)

        import numpy as np

        for decision in decisions:
            input_state = decision.get("input_state", {})
            # Extract feature vector — use stored features or construct from state
            features = input_state.get("features")
            if features is None:
                # Construct minimal feature vector from available state
                features = self._extract_features(input_state)

            state_features = np.array(features, dtype=np.float32)
            final_result = decision.get("final_result", {})
            outcome = decision.get("actual_outcome", {})
            trm_type = decision.get("decision_type", "").replace("_exception", "")

            # Determine action value
            action = final_result.get("action_value", 0)
            if isinstance(action, (list, tuple)):
                action = action[0] if action else 0

            trainer.add_experience(
                state_features=state_features,
                action=action,
                outcome=outcome,
                trm_type=trm_type,
                expert_action=final_result.get("expert_action"),
            )

        # Step 4: Train
        try:
            result = trainer.train()
        except Exception as e:
            logger.error(f"Training failed for {self.site_key}: {e}")
            return None

        if result.final_loss == float("inf"):
            logger.warning(f"Training produced infinite loss for {self.site_key}")
            return None

        # Step 5: Compare loss vs current checkpoint
        current_loss = self._get_current_loss()
        if current_loss is not None and current_loss < float("inf"):
            regression = (result.final_loss - current_loss) / max(current_loss, 1e-6)
            if regression > MAX_REGRESSION_PCT:
                logger.warning(
                    f"New model regression for {self.site_key}: "
                    f"current={current_loss:.4f}, new={result.final_loss:.4f} "
                    f"(+{regression:.1%}). Keeping current model."
                )
                return result

        # Step 6: Save checkpoint
        checkpoint_path = self._save_checkpoint(model, result, trigger_event, len(decisions))

        # Step 7: Mark previous checkpoints as inactive
        self._deactivate_old_checkpoints()

        # Step 8: Record new checkpoint in DB
        self._record_checkpoint(checkpoint_path, result, len(decisions))

        logger.info(
            f"CDC retraining complete for {self.site_key}: "
            f"loss={result.final_loss:.4f}, epochs={result.epochs_completed}, "
            f"samples={len(decisions)}"
        )

        return result

    def _get_or_create_model(self):
        """Get the current model or create a new one."""
        try:
            from app.services.powell.site_agent_model import SiteAgentModel, SiteAgentModelConfig

            # Try to load from latest checkpoint
            latest = (
                self.db.query(SiteAgentCheckpoint)
                .filter(
                    SiteAgentCheckpoint.site_key == self.site_key,
                    SiteAgentCheckpoint.is_active == True,
                )
                .order_by(desc(SiteAgentCheckpoint.created_at))
                .first()
            )

            model_config = SiteAgentModelConfig()
            if latest and latest.model_config:
                try:
                    model_config = SiteAgentModelConfig(**latest.model_config)
                except Exception:
                    pass

            model = SiteAgentModel(model_config)

            # Load weights if checkpoint exists
            if latest and latest.checkpoint_path and os.path.exists(latest.checkpoint_path):
                try:
                    import torch
                    checkpoint = torch.load(latest.checkpoint_path, map_location="cpu")
                    if "model_state_dict" in checkpoint:
                        model.load_state_dict(checkpoint["model_state_dict"])
                        logger.info(f"Loaded model weights from {latest.checkpoint_path}")
                except Exception as e:
                    logger.warning(f"Could not load model weights: {e}")

            return model
        except Exception as e:
            logger.error(f"Failed to create model: {e}")
            return None

    def _extract_features(self, input_state: Dict[str, Any]) -> List[float]:
        """Extract a feature vector from decision input state.

        Returns a 26-dimensional vector: 10 physical state features,
        11 urgency vector values, and 5 signal summary features.
        """
        # 10 physical state features
        features = [
            float(input_state.get("inventory_on_hand", 0)),
            float(input_state.get("inventory_target", 0)),
            float(input_state.get("backlog", 0)),
            float(input_state.get("demand", 0)),
            float(input_state.get("forecast", 0)),
            float(input_state.get("pipeline_supply", 0)),
            float(input_state.get("lead_time", 0)),
            float(input_state.get("service_level", 0.95)),
            float(input_state.get("safety_stock", 0)),
            float(input_state.get("reorder_point", 0)),
        ]

        # 11 urgency vector values (from signal_context if available)
        signal_ctx = input_state.get("signal_context") or {}
        urgency_values = signal_ctx.get("urgency_vector", {}).get("values", [])
        for i in range(11):
            features.append(float(urgency_values[i]) if i < len(urgency_values) else 0.0)

        # 5 aggregated signal features
        features.append(float(signal_ctx.get("active_signal_count", 0)) / 20.0)
        summary = signal_ctx.get("summary", {})
        features.append(float(len(summary)))  # distinct signal types active
        features.append(float(input_state.get("urgency_at_time", 0.0)))
        features.append(1.0 if input_state.get("triggered_by") else 0.0)
        features.append(float(len(input_state.get("signals_emitted", []) or [])))

        return features[:26]

    def _get_current_loss(self) -> Optional[float]:
        """Get the training loss of the currently active checkpoint."""
        latest = (
            self.db.query(SiteAgentCheckpoint)
            .filter(
                SiteAgentCheckpoint.site_key == self.site_key,
                SiteAgentCheckpoint.is_active == True,
            )
            .order_by(desc(SiteAgentCheckpoint.created_at))
            .first()
        )
        return latest.training_loss if latest else None

    def _save_checkpoint(
        self,
        model,
        result: TrainingResult,
        trigger_event: Optional[TriggerEvent],
        num_samples: int,
    ) -> str:
        """Save model checkpoint to filesystem."""
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"trm_cdc_{self.site_key}_{timestamp}.pt"
        checkpoint_path = os.path.join(CHECKPOINT_DIR, filename)

        try:
            import torch
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "training_result": {
                        "final_loss": result.final_loss,
                        "epochs_completed": result.epochs_completed,
                        "method_used": result.method_used.value,
                    },
                    "trigger_event": trigger_event.message if trigger_event else None,
                    "site_key": self.site_key,
                    "timestamp": timestamp,
                    "num_samples": num_samples,
                },
                checkpoint_path,
            )
            logger.info(f"Saved checkpoint to {checkpoint_path}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

        return checkpoint_path

    def _deactivate_old_checkpoints(self):
        """Mark all existing active checkpoints for this site as inactive."""
        try:
            self.db.query(SiteAgentCheckpoint).filter(
                SiteAgentCheckpoint.site_key == self.site_key,
                SiteAgentCheckpoint.is_active == True,
            ).update({"is_active": False, "retired_at": datetime.utcnow()})
            self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to deactivate old checkpoints: {e}")

    def _record_checkpoint(
        self, checkpoint_path: str, result: TrainingResult, num_samples: int
    ):
        """Record the new checkpoint in the database."""
        try:
            checkpoint = SiteAgentCheckpoint(
                checkpoint_id=f"cdc_{uuid.uuid4().hex[:8]}",
                site_key=self.site_key,
                model_version=f"cdc_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                checkpoint_path=checkpoint_path,
                training_phase=result.method_used.value,
                training_samples=num_samples,
                training_epochs=result.epochs_completed,
                training_loss=result.final_loss,
                is_active=True,
                is_validated=False,
                created_at=datetime.utcnow(),
            )
            self.db.add(checkpoint)
            self.db.commit()
            logger.info(f"Recorded checkpoint {checkpoint.checkpoint_id}")
        except Exception as e:
            logger.error(f"Failed to record checkpoint: {e}")
            self.db.rollback()
