"""
Conformal auto-calibration service for TMS TRMs.

Reads outcome-measured rows from `agent_decisions` (where
`outcome_measured=True` AND `recommended_value IS NOT NULL` AND
`outcome_value IS NOT NULL`), computes nonconformity scores, and updates
the `conformal.active_predictors` / `conformal.observation_log` /
`conformal.calibration_snapshots` tables per Core's conformal schema.

This is **consumer-side glue** only. The conformal math (quantile
computation, Adaptive Conformal Inference) lives in Core's
`azirella_conformal` package per the transport-plane invariant —
nothing in this file reimplements that framework.

## Variable registry

Of the 11 TMS TRMs, only 4 emit a continuous `recommended_value` that
an outcome can meaningfully be compared against:

  * capacity_buffer        → proposed buffer loads vs actual need
  * demand_sensing         → proposed forecast adjustment vs actual
  * equipment_reposition   → proposed quantity to move vs actual shortfall
  * shipment_tracking      → predicted hours-late vs actual hours-late

The other 7 TRMs are pure classification (ACCEPT/REJECT/DEFER/...) and
have no calibratable interval. Those outcomes feed the Override
Classifier (downstream) rather than conformal.

## Calibration cadence

Runs every 12h (matches SCP's conformal cadence). For each (tenant,
config, variable_type, entity_id) group:

  1. Backfill `conformal.observation_log` from `agent_decisions` rows
     not yet logged (dedupe via `source_transaction_id = agent_decision.id`).
  2. Compute the (1-α) quantile of nonconformity scores over the
     calibration window (default 30 days).
  3. Compute empirical coverage: fraction of recent observations whose
     `actual_value` fell within the interval around `predicted_value`
     at the *previous* quantile.
  4. Upsert `conformal.active_predictors` with the new quantile.
  5. Append an immutable `conformal.calibration_snapshots` row.

## No-fallbacks invariant

If a variable has < `MIN_SAMPLES_FOR_CALIBRATION` observations, we
skip it (log at INFO, don't calibrate). We do NOT substitute a default
interval width — silent fallbacks mask data-pipeline problems
(see `feedback_soc2_no_fallback.md`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import Integer, and_, cast, func, select, text
from sqlalchemy.orm import Session

from app.models.conformal import (
    ActivePredictor, CalibrationSnapshot, ObservationLog,
)
from app.models.decision_tracking import AgentDecision, DecisionType

logger = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────

DEFAULT_ALPHA = 0.2  # 80% coverage target (1-α)
DEFAULT_WINDOW_DAYS = 30
MIN_SAMPLES_FOR_CALIBRATION = 20
DRIFT_THRESHOLD = 0.10  # Coverage deviation triggering is_stale=True


# Mapping from TRM decision_type → (variable_type, entity_id_template).
# entity_id_template is currently static (the variable_type itself); a
# per-entity entity_id would come from the agent_decision's item_code,
# but v1 calibrates at the variable level so all TRM decisions of the
# same type share a single predictor. When we need per-lane or per-site
# predictors, swap entity_id_template for a format string keyed on
# AgentDecision.item_code or category.
_CALIBRATABLE = {
    DecisionType.CAPACITY_BUFFER: ("capacity_buffer", "global"),
    DecisionType.DEMAND_SENSING: ("demand_sensing", "global"),
    DecisionType.EQUIPMENT_REPOSITION: ("equipment_reposition", "global"),
    DecisionType.SHIPMENT_TRACKING: ("shipment_tracking_hours_late", "global"),
}


# ── Service ─────────────────────────────────────────────────────────────


class ConformalAutoCalibrateService:
    """Recalibrates conformal predictors from observed TRM outcomes."""

    def __init__(
        self,
        db: Session,
        alpha: float = DEFAULT_ALPHA,
        window_days: int = DEFAULT_WINDOW_DAYS,
    ):
        self.db = db
        self.alpha = alpha
        self.window_days = window_days

    # ── Public entry points ────────────────────────────────────────────

    def calibrate_tenant(self, tenant_id: int, config_id: int) -> Dict[str, Any]:
        """Run calibration for every calibratable TRM variable for (tenant, config).

        Returns a summary dict with per-variable outcomes.
        """
        summary: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "config_id": config_id,
            "started_at": datetime.utcnow().isoformat(),
            "variables": [],
        }
        for decision_type, (variable_type, entity_id) in _CALIBRATABLE.items():
            result = self._calibrate_variable(
                tenant_id=tenant_id,
                config_id=config_id,
                decision_type=decision_type,
                variable_type=variable_type,
                entity_id=entity_id,
            )
            summary["variables"].append(result)

        self.db.commit()
        summary["finished_at"] = datetime.utcnow().isoformat()
        return summary

    def calibrate_all_tenants(self) -> List[Dict[str, Any]]:
        """Enumerate all (tenant_id, config_id) pairs with calibratable
        TRM decisions in the last `window_days` days, and calibrate each.

        This is the entry point the scheduled job calls.
        """
        cutoff = datetime.utcnow() - timedelta(days=self.window_days)
        # Use the SQLAlchemy ORM IN-clause so the enum values are
        # properly cast to decision_type_enum on the Postgres side.
        # context_data is plain JSON (not JSONB), so we use Postgres
        # json_extract_path_text + cast to int for the GROUP BY.
        config_id_expr = cast(
            func.json_extract_path_text(AgentDecision.context_data, "config_id"),
            Integer,
        ).label("config_id")
        pairs = self.db.execute(
            select(AgentDecision.tenant_id, config_id_expr)
            .where(
                AgentDecision.decision_type.in_(list(_CALIBRATABLE.keys())),
                AgentDecision.outcome_measured.is_(True),
                AgentDecision.recommended_value.isnot(None),
                AgentDecision.outcome_value.isnot(None),
                AgentDecision.created_at >= cutoff,
            )
            .distinct()
        ).all()

        summaries: List[Dict[str, Any]] = []
        for row in pairs:
            tenant_id = int(row[0])
            config_id = int(row[1] or 0)
            if config_id == 0:
                # No config — skip (we can't key a predictor without it)
                logger.info(
                    "tenant %s has calibratable decisions without config_id; skipping",
                    tenant_id,
                )
                continue
            try:
                summaries.append(
                    self.calibrate_tenant(tenant_id=tenant_id, config_id=config_id)
                )
            except Exception as e:  # pragma: no cover
                logger.error(
                    "conformal calibration failed for tenant=%s config=%s: %s",
                    tenant_id, config_id, e,
                )
                self.db.rollback()
        return summaries

    # ── Internals ──────────────────────────────────────────────────────

    def _calibrate_variable(
        self,
        tenant_id: int,
        config_id: int,
        decision_type: DecisionType,
        variable_type: str,
        entity_id: str,
    ) -> Dict[str, Any]:
        """Calibrate one variable. Returns a per-variable summary dict."""
        # 1. Backfill observation_log from agent_decisions
        new_obs = self._backfill_observations(
            tenant_id=tenant_id,
            config_id=config_id,
            decision_type=decision_type,
            variable_type=variable_type,
            entity_id=entity_id,
        )

        # 2. Read all in-window observations for this variable
        cutoff = datetime.utcnow() - timedelta(days=self.window_days)
        obs_rows = self.db.execute(
            select(ObservationLog).where(
                ObservationLog.tenant_id == tenant_id,
                ObservationLog.config_id == config_id,
                ObservationLog.variable_type == variable_type,
                ObservationLog.entity_id == entity_id,
                ObservationLog.observed_at >= cutoff,
            )
        ).scalars().all()

        n_samples = len(obs_rows)
        if n_samples < MIN_SAMPLES_FOR_CALIBRATION:
            logger.info(
                "conformal %s tenant=%s config=%s: n_samples=%d < min=%d — skipping",
                variable_type, tenant_id, config_id,
                n_samples, MIN_SAMPLES_FOR_CALIBRATION,
            )
            return {
                "variable_type": variable_type,
                "entity_id": entity_id,
                "n_samples": n_samples,
                "new_observations": new_obs,
                "calibrated": False,
                "reason": "insufficient_samples",
            }

        # 3. Compute nonconformity quantile (split conformal)
        scores = np.array([r.nonconformity_score for r in obs_rows], dtype=float)
        # Conformal quantile: ceil((n+1)(1-α))/n
        quantile_level = np.clip(np.ceil((n_samples + 1) * (1 - self.alpha)) / n_samples, 0, 1)
        new_quantile = float(np.quantile(scores, quantile_level))

        # 4. Empirical coverage from the old predictor's interval
        prev = self.db.execute(
            select(ActivePredictor).where(
                ActivePredictor.tenant_id == tenant_id,
                ActivePredictor.config_id == config_id,
                ActivePredictor.variable_type == variable_type,
                ActivePredictor.entity_id == entity_id,
            )
        ).scalar_one_or_none()
        old_quantile = prev.quantile if prev else None
        empirical_coverage: Optional[float] = None
        if old_quantile is not None:
            covered = [
                1 for r in obs_rows
                if r.was_covered is True
            ]
            empirical_coverage = len(covered) / n_samples

        interval_width_mean = 2.0 * new_quantile  # symmetric interval ±quantile

        # Drift detection: coverage deviation from (1-α)
        drift_score = 0.0
        drift_detected = False
        if empirical_coverage is not None:
            target_coverage = 1.0 - self.alpha
            drift_score = abs(empirical_coverage - target_coverage)
            drift_detected = drift_score > DRIFT_THRESHOLD

        # 5. Upsert ActivePredictor
        if prev is None:
            prev = ActivePredictor(
                tenant_id=tenant_id,
                config_id=config_id,
                variable_type=variable_type,
                entity_id=entity_id,
                alpha=self.alpha,
                quantile=new_quantile,
                empirical_coverage=empirical_coverage,
                coverage_guarantee=1.0 - self.alpha,
                interval_width_mean=interval_width_mean,
                n_samples=n_samples,
                method="split",
                is_stale=False,
                last_calibrated_at=datetime.utcnow(),
                last_observation_at=max(r.observed_at for r in obs_rows),
                drift_detected=drift_detected,
                drift_score=drift_score,
            )
            self.db.add(prev)
        else:
            prev.alpha = self.alpha
            prev.quantile = new_quantile
            prev.empirical_coverage = empirical_coverage
            prev.coverage_guarantee = 1.0 - self.alpha
            prev.interval_width_mean = interval_width_mean
            prev.n_samples = n_samples
            prev.method = "split"
            prev.is_stale = False
            prev.last_calibrated_at = datetime.utcnow()
            prev.last_observation_at = max(r.observed_at for r in obs_rows)
            prev.drift_detected = drift_detected
            prev.drift_score = drift_score

        # 6. Append immutable CalibrationSnapshot
        snapshot = CalibrationSnapshot(
            tenant_id=tenant_id,
            config_id=config_id,
            variable_type=variable_type,
            entity_id=entity_id,
            alpha=self.alpha,
            quantile=new_quantile,
            empirical_coverage=empirical_coverage,
            n_samples=n_samples,
            method="split",
            nonconformity_scores=sorted(float(s) for s in scores)[:200],
            coverage_history=None,
            distribution_fit={
                "mean_score": float(scores.mean()),
                "std_score": float(scores.std()),
                "min_score": float(scores.min()),
                "max_score": float(scores.max()),
            },
            calibrated_at=datetime.utcnow(),
        )
        self.db.add(snapshot)
        self.db.flush()

        logger.info(
            "conformal %s tenant=%s config=%s: quantile=%.3f coverage=%s n=%d drift=%.3f",
            variable_type, tenant_id, config_id,
            new_quantile,
            f"{empirical_coverage:.3f}" if empirical_coverage is not None else "n/a",
            n_samples, drift_score,
        )

        return {
            "variable_type": variable_type,
            "entity_id": entity_id,
            "n_samples": n_samples,
            "new_observations": new_obs,
            "quantile": new_quantile,
            "empirical_coverage": empirical_coverage,
            "drift_detected": drift_detected,
            "drift_score": drift_score,
            "calibrated": True,
        }

    def _backfill_observations(
        self,
        tenant_id: int,
        config_id: int,
        decision_type: DecisionType,
        variable_type: str,
        entity_id: str,
    ) -> int:
        """Mirror outcome-measured agent_decisions into conformal.observation_log.

        Dedupe on (source_transaction_type='agent_decision',
        source_transaction_id=agent_decision.id). Returns count of rows
        newly inserted.
        """
        cutoff = datetime.utcnow() - timedelta(days=self.window_days)

        # Find agent_decisions rows with outcomes that aren't yet in observation_log
        existing_ids = set(
            r[0] for r in self.db.execute(
                select(ObservationLog.source_transaction_id).where(
                    ObservationLog.tenant_id == tenant_id,
                    ObservationLog.config_id == config_id,
                    ObservationLog.variable_type == variable_type,
                    ObservationLog.entity_id == entity_id,
                    ObservationLog.source_transaction_type == "agent_decision",
                    ObservationLog.observed_at >= cutoff,
                )
            ).all()
        )

        candidates = self.db.execute(
            select(AgentDecision).where(
                AgentDecision.tenant_id == tenant_id,
                AgentDecision.decision_type == decision_type,
                AgentDecision.outcome_measured.is_(True),
                AgentDecision.recommended_value.isnot(None),
                AgentDecision.outcome_value.isnot(None),
                AgentDecision.created_at >= cutoff,
            )
        ).scalars().all()

        # Pull the active predictor to flag was_covered on the fly
        prev = self.db.execute(
            select(ActivePredictor).where(
                ActivePredictor.tenant_id == tenant_id,
                ActivePredictor.config_id == config_id,
                ActivePredictor.variable_type == variable_type,
                ActivePredictor.entity_id == entity_id,
            )
        ).scalar_one_or_none()
        prev_quantile = prev.quantile if prev else None

        inserted = 0
        for ad in candidates:
            if str(ad.id) in existing_ids:
                continue

            predicted = float(ad.recommended_value)
            actual = float(ad.outcome_value)
            residual = actual - predicted
            nonconformity = abs(residual)

            interval_lower = interval_upper = None
            was_covered: Optional[bool] = None
            if prev_quantile is not None:
                interval_lower = predicted - prev_quantile
                interval_upper = predicted + prev_quantile
                was_covered = interval_lower <= actual <= interval_upper

            # agent_decisions.action_timestamp is the canonical observe-time;
            # fall back to updated_at, then created_at.
            observed_at = ad.action_timestamp or ad.updated_at or ad.created_at

            self.db.add(
                ObservationLog(
                    tenant_id=tenant_id,
                    config_id=config_id,
                    variable_type=variable_type,
                    entity_id=entity_id,
                    predicted_value=predicted,
                    actual_value=actual,
                    residual=residual,
                    nonconformity_score=nonconformity,
                    was_covered=was_covered,
                    interval_lower=interval_lower,
                    interval_upper=interval_upper,
                    source_transaction_type="agent_decision",
                    source_transaction_id=str(ad.id),
                    observed_at=observed_at or datetime.utcnow(),
                )
            )
            inserted += 1

        if inserted:
            self.db.flush()
        return inserted
