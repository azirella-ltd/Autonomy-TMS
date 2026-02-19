"""
Calibration Feedback Service - AIIO Framework

Implements the feedback loop for tracking actual outcomes against predictions
and recalibrating conformal prediction intervals.

Key Functions:
1. Record actual outcomes for agent actions
2. Update calibration logs for audit trail
3. Recalibrate belief states using adaptive conformal prediction
4. Detect and flag prediction drift

Adaptive Conformal Inference (ACI):
- Maintains rolling window of residuals
- Adjusts quantile based on recent coverage
- Provides coverage guarantees under distribution shift
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
import logging
import math

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc

from app.models.powell import (
    PowellBeliefState, PowellCalibrationLog, ConformalMethod
)
from app.models.agent_action import AgentAction

logger = logging.getLogger(__name__)


# Default configuration
DEFAULT_WINDOW_SIZE = 100  # Number of observations for rolling calibration
DEFAULT_COVERAGE_TARGET = 0.80  # Target coverage probability
DRIFT_THRESHOLD = 0.10  # Coverage deviation threshold for drift detection
RECALIBRATION_INTERVAL_HOURS = 24  # Minimum hours between recalibrations


class CalibrationFeedbackService:
    """
    Service for tracking outcomes and recalibrating predictions.

    Implements adaptive conformal inference for calibrated uncertainty
    quantification with coverage guarantees.
    """

    def __init__(
        self,
        db: AsyncSession,
        window_size: int = DEFAULT_WINDOW_SIZE,
        coverage_target: float = DEFAULT_COVERAGE_TARGET,
    ):
        self.db = db
        self.window_size = window_size
        self.coverage_target = coverage_target

    # =========================================================================
    # Outcome Recording
    # =========================================================================

    async def record_outcome(
        self,
        action_id: int,
        actual_outcome: float,
        outcome_source: str = "observation",
    ) -> AgentAction:
        """
        Record the actual outcome for an agent action.

        This closes the feedback loop by comparing the predicted outcome
        with what actually happened.

        Args:
            action_id: ID of the AgentAction
            actual_outcome: Observed actual value
            outcome_source: Source of the observation

        Returns:
            Updated AgentAction with outcome recorded
        """
        # Get the action
        result = await self.db.execute(
            select(AgentAction).where(AgentAction.id == action_id)
        )
        action = result.scalar_one_or_none()

        if not action:
            raise ValueError(f"AgentAction {action_id} not found")

        # Record the outcome
        action.actual_outcome = actual_outcome
        action.outcome_measured_at = datetime.utcnow()

        # Check if outcome was within prediction interval
        if action.prediction_interval_lower is not None and action.prediction_interval_upper is not None:
            action.outcome_within_interval = (
                action.prediction_interval_lower <= actual_outcome <= action.prediction_interval_upper
            )

            # Log to calibration history if we have a belief state
            if action.belief_state_id:
                await self._log_calibration_event(
                    belief_state_id=action.belief_state_id,
                    action=action,
                    actual_outcome=actual_outcome,
                )

        await self.db.flush()
        return action

    async def _log_calibration_event(
        self,
        belief_state_id: int,
        action: AgentAction,
        actual_outcome: float,
    ) -> PowellCalibrationLog:
        """Log a calibration event for audit trail and analysis."""
        residual = (action.predicted_outcome or 0) - actual_outcome

        log_entry = PowellCalibrationLog(
            belief_state_id=belief_state_id,
            predicted_value=action.predicted_outcome or 0,
            predicted_lower=action.prediction_interval_lower or 0,
            predicted_upper=action.prediction_interval_upper or 0,
            actual_value=actual_outcome,
            in_interval=action.outcome_within_interval or False,
            residual=residual,
            nonconformity_score=action.nonconformity_score,
            action_id=action.id,
            observed_at=datetime.utcnow(),
        )
        self.db.add(log_entry)
        await self.db.flush()
        return log_entry

    # =========================================================================
    # Calibration Analysis
    # =========================================================================

    async def analyze_calibration(
        self,
        belief_state_id: int,
        lookback_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Analyze calibration quality for a belief state.

        Returns metrics on prediction quality including:
        - Empirical coverage rate
        - Average interval width
        - Mean absolute error
        - Drift indicators

        Args:
            belief_state_id: ID of the belief state to analyze
            lookback_days: Number of days to look back

        Returns:
            Dictionary of calibration metrics
        """
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)

        # Get calibration logs
        result = await self.db.execute(
            select(PowellCalibrationLog)
            .where(
                PowellCalibrationLog.belief_state_id == belief_state_id,
                PowellCalibrationLog.observed_at >= cutoff,
            )
            .order_by(desc(PowellCalibrationLog.observed_at))
            .limit(self.window_size)
        )
        logs = result.scalars().all()

        if not logs:
            return {
                "empirical_coverage": None,
                "mean_interval_width": None,
                "mean_absolute_error": None,
                "observation_count": 0,
                "drift_detected": False,
            }

        # Calculate metrics
        in_interval_count = sum(1 for log in logs if log.in_interval)
        empirical_coverage = in_interval_count / len(logs)

        interval_widths = [
            log.predicted_upper - log.predicted_lower
            for log in logs
        ]
        mean_interval_width = sum(interval_widths) / len(interval_widths)

        absolute_errors = [abs(log.residual) for log in logs]
        mae = sum(absolute_errors) / len(absolute_errors)

        # Detect drift (coverage significantly below target)
        drift_detected = abs(empirical_coverage - self.coverage_target) > DRIFT_THRESHOLD

        return {
            "empirical_coverage": empirical_coverage,
            "mean_interval_width": mean_interval_width,
            "mean_absolute_error": mae,
            "observation_count": len(logs),
            "drift_detected": drift_detected,
            "coverage_target": self.coverage_target,
            "coverage_deviation": empirical_coverage - self.coverage_target,
        }

    # =========================================================================
    # Recalibration
    # =========================================================================

    async def recalibrate_belief_state(
        self,
        belief_state_id: int,
        force: bool = False,
    ) -> PowellBeliefState:
        """
        Recalibrate a belief state using adaptive conformal inference.

        Uses recent residuals to adjust the conformal quantile and
        interval width to maintain target coverage.

        Args:
            belief_state_id: ID of the belief state
            force: Force recalibration even if recently done

        Returns:
            Updated PowellBeliefState
        """
        # Get the belief state
        result = await self.db.execute(
            select(PowellBeliefState).where(PowellBeliefState.id == belief_state_id)
        )
        belief_state = result.scalar_one_or_none()

        if not belief_state:
            raise ValueError(f"BeliefState {belief_state_id} not found")

        # Check if recalibration is needed
        if not force and belief_state.last_recalibration:
            hours_since = (datetime.utcnow() - belief_state.last_recalibration).total_seconds() / 3600
            if hours_since < RECALIBRATION_INTERVAL_HOURS:
                logger.info(f"Skipping recalibration for {belief_state_id}, last done {hours_since:.1f}h ago")
                return belief_state

        # Get recent calibration logs
        result = await self.db.execute(
            select(PowellCalibrationLog)
            .where(PowellCalibrationLog.belief_state_id == belief_state_id)
            .order_by(desc(PowellCalibrationLog.observed_at))
            .limit(self.window_size)
        )
        logs = list(result.scalars().all())

        if len(logs) < 10:
            logger.info(f"Insufficient data for recalibration: {len(logs)} observations")
            return belief_state

        # Calculate new interval using adaptive conformal
        residuals = [abs(log.residual) for log in logs]
        coverage_indicators = [1 if log.in_interval else 0 for log in logs]

        # Adaptive quantile adjustment
        empirical_coverage = sum(coverage_indicators) / len(coverage_indicators)
        new_quantile = self._adaptive_quantile(
            current_coverage=empirical_coverage,
            target_coverage=self.coverage_target,
            residuals=residuals,
        )

        # Calculate new interval width
        sorted_residuals = sorted(residuals)
        quantile_idx = int(new_quantile * len(sorted_residuals))
        quantile_idx = min(quantile_idx, len(sorted_residuals) - 1)
        new_half_width = sorted_residuals[quantile_idx]

        # Update belief state
        if belief_state.point_estimate is not None:
            belief_state.conformal_lower = belief_state.point_estimate - new_half_width
            belief_state.conformal_upper = belief_state.point_estimate + new_half_width

        belief_state.empirical_coverage = empirical_coverage
        belief_state.interval_width_mean = 2 * new_half_width
        belief_state.observation_count = len(logs)
        belief_state.last_recalibration = datetime.utcnow()
        belief_state.conformal_method = ConformalMethod.ADAPTIVE

        # Update residuals history (keep last N)
        belief_state.recent_residuals = residuals[:self.window_size]
        belief_state.coverage_history = coverage_indicators[:self.window_size]

        # Check for drift
        belief_state.drift_detected = abs(empirical_coverage - self.coverage_target) > DRIFT_THRESHOLD
        belief_state.drift_score = empirical_coverage - self.coverage_target

        await self.db.flush()

        logger.info(
            f"Recalibrated belief state {belief_state_id}: "
            f"coverage={empirical_coverage:.2%}, width={2*new_half_width:.2f}"
        )

        return belief_state

    def _adaptive_quantile(
        self,
        current_coverage: float,
        target_coverage: float,
        residuals: List[float],
        learning_rate: float = 0.1,
    ) -> float:
        """
        Calculate adaptive quantile using online learning.

        Adjusts the quantile based on coverage error to maintain
        target coverage under distribution shift.

        Args:
            current_coverage: Current empirical coverage
            target_coverage: Target coverage rate
            residuals: List of residual magnitudes
            learning_rate: Step size for adjustment

        Returns:
            New quantile value in [0, 1]
        """
        # Start from target quantile
        base_quantile = target_coverage

        # Adjust based on coverage error
        coverage_error = current_coverage - target_coverage

        # If coverage is too low, increase quantile (wider intervals)
        # If coverage is too high, decrease quantile (narrower intervals)
        adjustment = -learning_rate * coverage_error

        new_quantile = base_quantile + adjustment

        # Clamp to valid range
        return max(0.5, min(0.99, new_quantile))

    # =========================================================================
    # Batch Operations
    # =========================================================================

    async def recalibrate_all_stale(
        self,
        group_id: int,
        max_age_hours: int = RECALIBRATION_INTERVAL_HOURS,
    ) -> List[int]:
        """
        Recalibrate all belief states that haven't been updated recently.

        Args:
            group_id: Group ID to recalibrate
            max_age_hours: Maximum hours since last recalibration

        Returns:
            List of recalibrated belief state IDs
        """
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)

        # Find stale belief states
        result = await self.db.execute(
            select(PowellBeliefState)
            .where(
                PowellBeliefState.group_id == group_id,
                (PowellBeliefState.last_recalibration == None) |  # noqa: E711
                (PowellBeliefState.last_recalibration < cutoff)
            )
        )
        stale_states = result.scalars().all()

        recalibrated_ids = []
        for state in stale_states:
            try:
                await self.recalibrate_belief_state(state.id)
                recalibrated_ids.append(state.id)
            except Exception as e:
                logger.error(f"Failed to recalibrate belief state {state.id}: {e}")

        logger.info(f"Recalibrated {len(recalibrated_ids)} belief states for group {group_id}")
        return recalibrated_ids

    async def get_calibration_summary(
        self,
        group_id: int,
        lookback_days: int = 7,
    ) -> Dict[str, Any]:
        """
        Get calibration summary for a group.

        Provides overall metrics on prediction quality across all
        belief states in the group.

        Args:
            group_id: Group ID
            lookback_days: Days to look back

        Returns:
            Summary dictionary with aggregate metrics
        """
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)

        # Get all calibration logs for the group
        result = await self.db.execute(
            select(PowellCalibrationLog)
            .join(PowellBeliefState)
            .where(
                PowellBeliefState.group_id == group_id,
                PowellCalibrationLog.observed_at >= cutoff,
            )
        )
        logs = result.scalars().all()

        if not logs:
            return {
                "total_observations": 0,
                "overall_coverage": None,
                "mean_interval_width": None,
                "drift_count": 0,
            }

        # Calculate overall metrics
        in_interval_count = sum(1 for log in logs if log.in_interval)
        overall_coverage = in_interval_count / len(logs)

        interval_widths = [
            log.predicted_upper - log.predicted_lower
            for log in logs
        ]
        mean_interval_width = sum(interval_widths) / len(interval_widths)

        # Count belief states with drift
        drift_result = await self.db.execute(
            select(func.count(PowellBeliefState.id))
            .where(
                PowellBeliefState.group_id == group_id,
                PowellBeliefState.drift_detected == True,  # noqa: E712
            )
        )
        drift_count = drift_result.scalar() or 0

        return {
            "total_observations": len(logs),
            "overall_coverage": overall_coverage,
            "coverage_target": self.coverage_target,
            "mean_interval_width": mean_interval_width,
            "drift_count": drift_count,
            "lookback_days": lookback_days,
        }
