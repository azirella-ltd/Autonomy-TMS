"""
CDC Retraining Service

Bridges CDC triggers to TRM model retraining, closing the Powell SDAM loop:
  CDC detects deviation → evaluate retraining need → train model → checkpoint → reload

Pipeline:
1. CDC fires a trigger (TriggerEvent with FULL_CFA)
2. Check if retraining is warranted (enough decisions with outcomes)
3. Load decisions via SiteAgentDecisionTracker.get_decisions_for_training()
4. Group decisions by TRM type and train each narrow model separately
5. Use MODEL_REGISTRY narrow models (ATPTRMModel, POCreationTRMModel, etc.)
6. Save checkpoint to filesystem + powell_site_agent_checkpoints
7. Reload model in SiteAgent

Safety:
- Offline RL (CQL) prevents distribution shift from logged data
- New model loss compared to current — skip if regression > 10%
- Cooldown prevents excessive training (min 6 hours between runs)
"""

from collections import defaultdict
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

from app.services.checkpoint_storage_service import checkpoint_dir as _ckpt_dir

logger = logging.getLogger(__name__)

# Minimum decisions with outcomes before retraining is considered
MIN_TRAINING_EXPERIENCES = 100

# Minimum hours between training runs for the same site
RETRAIN_COOLDOWN_HOURS = 6

# Maximum regression in loss before rejecting a new model
MAX_REGRESSION_PCT = 0.10


class CDCRetrainingService:
    """
    Bridges CDC triggers to TRM model retraining.

    Evaluates whether enough new experiences have accumulated to warrant
    retraining, then executes the full pipeline from data loading to
    checkpoint deployment.
    """

    def __init__(self, db: Session, site_key: str, tenant_id: int, config_id: int = 0):
        self.db = db
        self.site_key = site_key
        self.tenant_id = tenant_id
        self.config_id = config_id
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

        Groups decisions by TRM type and trains each narrow model separately
        using MODEL_REGISTRY (ATPTRMModel, POCreationTRMModel, etc.).

        Steps:
        1. Load decisions with outcomes from DB
        2. Group by TRM type
        3. For each type with enough data: get narrow model, train, checkpoint
        4. Compare loss vs current — skip if regression > 10%

        Returns:
            TrainingResult for the best-performing type, None if skipped/failed.
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

        # Step 2: Group decisions by TRM type
        import numpy as np

        decisions_by_type: Dict[str, list] = defaultdict(list)
        for decision in decisions:
            trm_type = decision.get("decision_type", "").replace("_exception", "")
            if trm_type:
                decisions_by_type[trm_type].append(decision)

        # Step 3: Train each TRM type with enough data
        best_result: Optional[TrainingResult] = None

        for trm_type, type_decisions in decisions_by_type.items():
            if len(type_decisions) < MIN_TRAINING_EXPERIENCES:
                logger.debug(
                    f"Skipping {trm_type}: only {len(type_decisions)} decisions "
                    f"(need {MIN_TRAINING_EXPERIENCES})"
                )
                continue

            model = self._get_or_create_model(trm_type)
            if model is None:
                continue

            # Create trainer and feed experiences
            config = TrainingConfig(
                method=training_method,
                learning_rate=1e-4,
                batch_size=min(64, len(type_decisions) // 4),
                epochs=50,
            )
            trainer = TRMTrainer(
                model=model, config=config,
                reward_calculator=self.reward_calculator,
            )

            for decision in type_decisions:
                input_state = decision.get("input_state", {})
                features = input_state.get("features")
                if features is None:
                    features = self._extract_features(input_state)

                state_features = np.array(features, dtype=np.float32)
                final_result = decision.get("final_result", {})
                outcome = decision.get("actual_outcome", {})

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

                # Also append to the unified training corpus so the outcome
                # flows up through aggregation to tactical and strategic layers.
                # See docs/internal/architecture/UNIFIED_TRAINING_CORPUS.md
                try:
                    self._append_to_corpus(
                        decision=decision,
                        state_features=state_features,
                        action=action,
                        outcome=outcome,
                        trm_type=trm_type,
                    )
                except Exception as e:
                    logger.debug("Corpus append failed (non-fatal): %s", e)

            # Train
            try:
                result = trainer.train()
            except Exception as e:
                logger.error(f"Training failed for {self.site_key}/{trm_type}: {e}")
                continue

            if result.final_loss == float("inf"):
                logger.warning(
                    f"Training produced infinite loss for {self.site_key}/{trm_type}"
                )
                continue

            # Compare loss vs current checkpoint
            current_loss = self._get_current_loss()
            if current_loss is not None and current_loss < float("inf"):
                regression = (result.final_loss - current_loss) / max(current_loss, 1e-6)
                if regression > MAX_REGRESSION_PCT:
                    logger.warning(
                        f"New model regression for {self.site_key}/{trm_type}: "
                        f"current={current_loss:.4f}, new={result.final_loss:.4f} "
                        f"(+{regression:.1%}). Keeping current model."
                    )
                    continue

            # Save checkpoint
            checkpoint_path = self._save_checkpoint(
                model, result, trigger_event, len(type_decisions),
            )
            self._deactivate_old_checkpoints()
            self._record_checkpoint(checkpoint_path, result, len(type_decisions))

            logger.info(
                f"CDC retraining complete for {self.site_key}/{trm_type}: "
                f"loss={result.final_loss:.4f}, epochs={result.epochs_completed}, "
                f"samples={len(type_decisions)}"
            )

            if best_result is None or result.final_loss < best_result.final_loss:
                best_result = result

        return best_result

    def _get_or_create_model(self, trm_type: str = "atp_executor"):
        """Get a narrow TRM model from MODEL_REGISTRY for the given type.

        Uses MODEL_REGISTRY narrow models (ATPTRMModel, POCreationTRMModel,
        etc.) which have simple forward(x) signatures compatible with
        TRMTrainer. Falls back to the first available model type if the
        requested type is not in the registry.
        """
        try:
            import torch
            from app.models.trm import MODEL_REGISTRY

            if trm_type not in MODEL_REGISTRY:
                logger.warning(
                    f"TRM type '{trm_type}' not in MODEL_REGISTRY, "
                    f"available: {list(MODEL_REGISTRY.keys())}"
                )
                return None

            model_cls, state_dim = MODEL_REGISTRY[trm_type]
            model = model_cls(state_dim=state_dim)

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

            if latest and latest.checkpoint_path and os.path.exists(latest.checkpoint_path):
                try:
                    checkpoint = torch.load(latest.checkpoint_path, map_location="cpu")
                    if "model_state_dict" in checkpoint:
                        model.load_state_dict(
                            checkpoint["model_state_dict"], strict=False,
                        )
                        logger.info(f"Loaded model weights from {latest.checkpoint_path}")
                except Exception as e:
                    logger.warning(f"Could not load model weights: {e}")

            return model
        except Exception as e:
            logger.error(f"Failed to create model for {trm_type}: {e}")
            return None

    def _append_to_corpus(
        self,
        decision: Dict[str, Any],
        state_features: "np.ndarray",
        action: Any,
        outcome: Dict[str, Any],
        trm_type: str,
    ) -> None:
        """Append a real decision outcome to the unified training corpus.

        The outcome becomes a new Layer 1 sample with origin='real'. The
        aggregator will re-roll it into Layer 1.5, 2, 4 on the next pass.
        """
        try:
            from app.models.training_corpus import TrainingCorpusSample

            # Convert numpy array state to serializable dict
            state_dict = {
                f"f_{i}": float(state_features[i])
                for i in range(min(len(state_features), 32))
            }

            # Compute reward from outcome
            reward = 0.0
            if outcome:
                cost_delta = outcome.get("cost_delta", 0)
                fill_rate = outcome.get("fill_rate", 0)
                service_level = outcome.get("service_level", 0)
                reward = max(0.0, min(1.0,
                    0.4 * (fill_rate or 0) +
                    0.4 * (service_level or 0) +
                    0.2 * (1.0 - max(0, -cost_delta / 10000.0))
                ))

            sample = TrainingCorpusSample(
                tenant_id=self.tenant_id,
                config_id=self.config_id,
                layer=1.0,
                scenario_id=f"real_{decision.get('decision_id', 'unknown')}",
                origin="real",
                trm_type=trm_type,
                product_id=decision.get("product_id"),
                site_id=self.site_key,
                sample_data={
                    "state_features": state_dict,
                    "action": {"value": action} if not isinstance(action, dict) else action,
                    "reward_components": outcome or {},
                    "aggregate_reward": reward,
                    "trm_type": trm_type,
                },
                reward=reward,
                weight=2.0,  # Real outcomes weighted higher than perturbations
                decision_id=decision.get("decision_id"),
            )
            self.db.add(sample)
            self.db.flush()
        except Exception as e:
            logger.debug("Corpus append helper failed: %s", e)

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
        ckpt = _ckpt_dir(self.tenant_id, self.config_id)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"trm_cdc_{self.site_key}_{timestamp}.pt"
        checkpoint_path = os.path.join(str(ckpt), filename)

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
