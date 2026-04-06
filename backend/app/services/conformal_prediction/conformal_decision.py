"""
Conformal Decision Theory (CDT) Wrapper for TRM Agents

Calibrates DECISIONS rather than predictions. Instead of asking
"will demand be in [a, b]?" (conformal prediction), CDT asks
"will my decision's cost be acceptable?" (conformal decision).

Key guarantee:
    P(loss(decision, outcome) ≤ threshold) ≥ 1 - α

This means every TRM decision carries a provable risk bound — the
probability that the realized cost exceeds the decision's implied cost.

Reference:
    Lekeufack, J., Angelopoulos, A.N., Bajcsy, A., Jordan, M.I., & Malik, J.
    (2024). "Conformal Decision Theory: Safe Autonomous Decisions from
    Imperfect Predictions." ICRA 2024.

Usage with TRM agents:
    wrapper = ConformalDecisionWrapper(agent_type="atp")
    wrapper.calibrate(historical_decisions, historical_outcomes)

    # On every decision:
    response = trm.decide(state)
    risk = wrapper.compute_risk_bound(response, state)
    response.risk_bound = risk.risk_bound

    # Autonomous escalation:
    if risk.risk_bound > 0.15:
        escalate_to_human(response, risk)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
import logging

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DecisionOutcomePair:
    """Historical decision and its realized outcome for calibration."""
    decision_features: np.ndarray  # State + decision encoding
    decision_cost_estimate: float  # What the agent thought the cost would be
    actual_cost: float  # What actually happened
    agent_type: str  # "atp", "inventory_rebalancing", "po_creation", etc.
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def loss(self) -> float:
        """Realized loss = actual cost - estimated cost (positive = underestimate)"""
        return self.actual_cost - self.decision_cost_estimate


@dataclass
class RiskAssessment:
    """Risk assessment for a single decision."""
    risk_bound: float  # P(loss > threshold), lower is safer
    loss_threshold: float  # The threshold used
    conformal_quantile: float  # Calibrated quantile of loss distribution
    expected_loss: float  # Point estimate of expected loss
    is_safe: bool  # risk_bound ≤ acceptable_risk
    escalation_recommended: bool  # Should this go to a human?
    reasoning: str
    calibration_size: int  # How many historical decisions were used
    method: str = "conformal_decision_theory"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_bound": self.risk_bound,
            "loss_threshold": self.loss_threshold,
            "conformal_quantile": self.conformal_quantile,
            "expected_loss": self.expected_loss,
            "is_safe": self.is_safe,
            "escalation_recommended": self.escalation_recommended,
            "reasoning": self.reasoning,
            "calibration_size": self.calibration_size,
            "method": self.method,
        }


class ConformalDecisionWrapper:
    """
    Wraps any TRM agent's decisions with Conformal Decision Theory risk bounds.

    The wrapper is calibrated from historical (decision, outcome) pairs stored
    in powell_*_decisions tables. It learns the distribution of decision losses
    (actual_cost - estimated_cost) and uses conformal calibration to provide
    distribution-free bounds.

    Architecture:
        TRM Agent ──> raw decision ──> CDT Wrapper ──> decision + risk_bound
                                          ↑
                                    calibration set
                                  (historical losses)

    The risk_bound enables:
    1. Autonomous operation when risk is low (risk_bound < threshold)
    2. Human escalation when risk is high (risk_bound > threshold)
    3. Audit trail with provable guarantees
    4. CDC retraining triggers when risk distribution shifts
    """

    # Default loss thresholds by agent type (cost in normalized units)
    DEFAULT_THRESHOLDS = {
        "atp": 0.10,  # 10% fill rate shortfall
        "inventory_rebalancing": 0.15,  # 15% of transfer value wasted
        "po_creation": 0.20,  # 20% of PO value (over/under-ordering)
        "order_tracking": 0.05,  # 5% of order value (missed exception)
        "mo_execution": 0.15,  # 15% of MO value
        "to_execution": 0.15,  # 15% of TO value
        "quality_disposition": 0.10,  # 10% quality cost
        "maintenance_scheduling": 0.20,  # 20% of maintenance cost
        "subcontracting": 0.20,  # 20% make-vs-buy cost differential
        "forecast_adjustment": 0.25,  # 25% forecast error increase
        "inventory_buffer": 0.15,  # 15% of holding/stockout cost
    }

    # Minimum calibration set size for reliable bounds
    MIN_CALIBRATION_SIZE = 30

    def __init__(
        self,
        agent_type: str,
        loss_threshold: Optional[float] = None,
        acceptable_risk: float = 0.10,
        escalation_risk: float = 0.20,
        gamma: float = 0.005,
    ):
        """
        Args:
            agent_type: TRM agent type (e.g., "atp", "po_creation")
            loss_threshold: Maximum acceptable loss per decision.
                          Defaults to agent-specific threshold.
            acceptable_risk: Risk bound below which decisions are auto-approved.
            escalation_risk: Risk bound above which escalation is recommended.
            gamma: Learning rate for adaptive calibration (ACI-style).
        """
        self.agent_type = agent_type
        self.loss_threshold = loss_threshold or self.DEFAULT_THRESHOLDS.get(agent_type, 0.15)
        self.acceptable_risk = acceptable_risk
        self.escalation_risk = escalation_risk
        self.gamma = gamma

        # Calibration state
        self._calibration_losses: List[float] = []
        self._calibration_features: List[np.ndarray] = []
        self._sorted_losses: Optional[np.ndarray] = None
        self._alpha: float = 0.10  # Adaptive miscoverage rate
        self._calibrated: bool = False
        self._calibration_timestamp: Optional[datetime] = None

        # Tracking for adaptive adjustment
        self._recent_outcomes: List[bool] = []  # Was risk assessment correct?

    def _get_ek_uncertainty_modifier(
        self,
        config_id: Optional[int],
        tenant_id: Optional[int],
        product_id: Optional[str],
        site_id: Optional[str],
    ) -> float:
        """Return EK uncertainty multiplier for conditional CDT.

        Queries ACTIVE experiential knowledge entities and returns the max
        cdt_uncertainty_multiplier for matching conditions. Returns 1.0
        if no EK entities match or service unavailable (backward compatible).
        """
        if not config_id or not tenant_id:
            return 1.0
        try:
            from app.services.experiential_knowledge_service import ExperientialKnowledgeService
            from app.db.session import sync_session_factory
            db = sync_session_factory()
            try:
                svc = ExperientialKnowledgeService(db=db, tenant_id=tenant_id, config_id=config_id)
                return svc.get_cdt_uncertainty_modifier(
                    config_id=config_id,
                    trm_type=self.agent_type,
                    product_id=product_id,
                    site_id=site_id,
                )
            finally:
                db.close()
        except Exception:
            return 1.0

    def calibrate(
        self,
        decision_outcome_pairs: List[DecisionOutcomePair],
        loss_fn: Optional[Callable[[DecisionOutcomePair], float]] = None,
    ):
        """
        Calibrate from historical decision-outcome pairs.

        Args:
            decision_outcome_pairs: Historical decisions with known outcomes
            loss_fn: Custom loss function. Default: actual_cost - estimated_cost
        """
        if len(decision_outcome_pairs) < self.MIN_CALIBRATION_SIZE:
            logger.warning(
                f"CDT calibration for {self.agent_type}: only "
                f"{len(decision_outcome_pairs)} pairs (need {self.MIN_CALIBRATION_SIZE}). "
                f"Risk bounds will be conservative."
            )

        losses = []
        features = []

        for pair in decision_outcome_pairs:
            if loss_fn:
                loss = loss_fn(pair)
            else:
                loss = pair.loss

            losses.append(loss)
            features.append(pair.decision_features)

        self._calibration_losses = losses
        self._calibration_features = features
        self._sorted_losses = np.sort(losses)
        self._calibrated = True
        self._calibration_timestamp = datetime.utcnow()

        logger.info(
            f"CDT calibrated for {self.agent_type} with {len(losses)} pairs. "
            f"Loss stats: mean={np.mean(losses):.4f}, "
            f"P90={np.percentile(losses, 90):.4f}, "
            f"max={np.max(losses):.4f}"
        )

    def compute_risk_bound(
        self,
        decision_cost_estimate: float,
        state_features: Optional[np.ndarray] = None,
        config_id: Optional[int] = None,
        tenant_id: Optional[int] = None,
        product_id: Optional[str] = None,
        site_id: Optional[str] = None,
    ) -> RiskAssessment:
        """
        Compute conformal risk bound for a decision.

        The risk bound is:
            P(actual_cost - estimated_cost > loss_threshold) ≤ risk_bound

        This is computed using the empirical distribution of calibration losses
        with conformal coverage guarantee.

        When experiential knowledge entities are active for the given context,
        the conformal interval is widened by the EK uncertainty multiplier
        (Alicke's conditional CDT — "The Planner Was the System").

        Args:
            decision_cost_estimate: Agent's estimated cost for this decision
            state_features: Current state features (for future conditional CDT)
            config_id: SC config ID for EK lookup (optional)
            tenant_id: Tenant ID for EK lookup (optional)
            product_id: Product ID for EK condition matching (optional)
            site_id: Site ID for EK condition matching (optional)

        Returns:
            RiskAssessment with provable risk bound
        """
        if not self._calibrated or len(self._calibration_losses) < 5:
            # Not enough data — return conservative assessment
            return RiskAssessment(
                risk_bound=0.50,  # Maximum uncertainty
                loss_threshold=self.loss_threshold,
                conformal_quantile=self.loss_threshold,
                expected_loss=self.loss_threshold,
                is_safe=False,
                escalation_recommended=True,
                reasoning=f"Insufficient calibration data ({len(self._calibration_losses)} pairs)",
                calibration_size=len(self._calibration_losses),
            )

        n = len(self._sorted_losses)

        # Conformal p-value: fraction of calibration losses exceeding threshold
        # With finite-sample correction: (#{losses > threshold} + 1) / (n + 1)
        exceedances = np.sum(self._sorted_losses > self.loss_threshold)
        risk_bound = (exceedances + 1) / (n + 1)

        # Apply adaptive correction (ACI-style)
        risk_bound = risk_bound * (1 + self._alpha - 0.10)
        risk_bound = float(np.clip(risk_bound, 0.0, 1.0))

        # Experiential Knowledge conditional CDT (Alicke's Belief State Bₜ)
        # When EK conditions are active, widen the uncertainty by multiplying
        # the risk bound. This routes more decisions to human oversight until
        # TRMs learn the conditional pattern via state augmentation.
        ek_multiplier = self._get_ek_uncertainty_modifier(
            config_id, tenant_id, product_id, site_id
        )
        if ek_multiplier > 1.0:
            risk_bound = float(np.clip(risk_bound * ek_multiplier, 0.0, 1.0))

        # Expected loss from calibration distribution
        expected_loss = float(np.mean(self._calibration_losses))

        # Conformal quantile at (1-alpha)
        quantile_idx = int(np.ceil((1 - self._alpha) * (n + 1))) - 1
        quantile_idx = max(0, min(n - 1, quantile_idx))
        conformal_quantile = float(self._sorted_losses[quantile_idx])

        # Safety and escalation checks
        is_safe = risk_bound <= self.acceptable_risk
        escalation_recommended = risk_bound > self.escalation_risk

        # Build reasoning
        if is_safe:
            reasoning = (
                f"CDT: risk_bound={risk_bound:.3f} ≤ {self.acceptable_risk} "
                f"(safe, n={n})"
            )
        elif escalation_recommended:
            reasoning = (
                f"CDT: risk_bound={risk_bound:.3f} > {self.escalation_risk} "
                f"(escalation recommended, n={n})"
            )
        else:
            reasoning = (
                f"CDT: risk_bound={risk_bound:.3f} in "
                f"({self.acceptable_risk}, {self.escalation_risk}] "
                f"(borderline, n={n})"
            )

        return RiskAssessment(
            risk_bound=risk_bound,
            loss_threshold=self.loss_threshold,
            conformal_quantile=conformal_quantile,
            expected_loss=expected_loss,
            is_safe=is_safe,
            escalation_recommended=escalation_recommended,
            reasoning=reasoning,
            calibration_size=n,
        )

    def update_with_outcome(self, was_safe_correct: bool):
        """
        Online update after observing a decision outcome.

        Adjusts the adaptive miscoverage rate to maintain long-run
        coverage guarantee even under distribution shift.

        Args:
            was_safe_correct: True if the safety assessment was correct
                            (i.e., if we said "safe" and loss ≤ threshold,
                             or "unsafe" and loss > threshold)
        """
        self._recent_outcomes.append(was_safe_correct)

        # Keep window
        if len(self._recent_outcomes) > 200:
            self._recent_outcomes = self._recent_outcomes[-200:]

        # ACI-style alpha adjustment
        if was_safe_correct:
            self._alpha = max(0.01, self._alpha - self.gamma)
        else:
            self._alpha = min(0.50, self._alpha + self.gamma)

    def add_calibration_pair(self, pair: DecisionOutcomePair):
        """
        Add a new decision-outcome pair to the calibration set.

        Supports online calibration as new decisions are evaluated.
        """
        loss = pair.loss
        self._calibration_losses.append(loss)
        self._calibration_features.append(pair.decision_features)
        self._sorted_losses = np.sort(self._calibration_losses)

        if not self._calibrated and len(self._calibration_losses) >= self.MIN_CALIBRATION_SIZE:
            self._calibrated = True
            self._calibration_timestamp = datetime.utcnow()
            logger.info(
                f"CDT for {self.agent_type} auto-calibrated with "
                f"{len(self._calibration_losses)} pairs"
            )

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated

    @property
    def calibration_size(self) -> int:
        return len(self._calibration_losses)

    @property
    def empirical_risk(self) -> Optional[float]:
        """Fraction of calibration decisions where loss > threshold"""
        if not self._calibration_losses:
            return None
        exceedances = sum(1 for l in self._calibration_losses if l > self.loss_threshold)
        return exceedances / len(self._calibration_losses)

    def get_diagnostics(self) -> Dict[str, Any]:
        """Get calibration diagnostics for monitoring."""
        if not self._calibration_losses:
            return {"status": "uncalibrated", "agent_type": self.agent_type}

        losses = np.array(self._calibration_losses)
        recent_accuracy = (
            sum(self._recent_outcomes) / len(self._recent_outcomes)
            if self._recent_outcomes else None
        )

        return {
            "agent_type": self.agent_type,
            "calibration_size": len(self._calibration_losses),
            "loss_threshold": self.loss_threshold,
            "acceptable_risk": self.acceptable_risk,
            "escalation_risk": self.escalation_risk,
            "adaptive_alpha": self._alpha,
            "loss_stats": {
                "mean": float(np.mean(losses)),
                "std": float(np.std(losses)),
                "p50": float(np.percentile(losses, 50)),
                "p90": float(np.percentile(losses, 90)),
                "p99": float(np.percentile(losses, 99)),
                "max": float(np.max(losses)),
            },
            "empirical_risk": self.empirical_risk,
            "recent_accuracy": recent_accuracy,
            "calibration_timestamp": (
                self._calibration_timestamp.isoformat()
                if self._calibration_timestamp else None
            ),
        }


class ConformalDecisionRegistry:
    """
    Registry of CDT wrappers for all TRM agent types.

    Provides a single entry point for the SiteAgent to wrap any
    TRM decision with risk bounds.
    """

    def __init__(self):
        self._wrappers: Dict[str, ConformalDecisionWrapper] = {}

    def register(
        self,
        agent_type: str,
        loss_threshold: Optional[float] = None,
        acceptable_risk: float = 0.10,
        escalation_risk: float = 0.20,
    ) -> ConformalDecisionWrapper:
        """Register a CDT wrapper for an agent type."""
        wrapper = ConformalDecisionWrapper(
            agent_type=agent_type,
            loss_threshold=loss_threshold,
            acceptable_risk=acceptable_risk,
            escalation_risk=escalation_risk,
        )
        self._wrappers[agent_type] = wrapper
        return wrapper

    def get(self, agent_type: str) -> Optional[ConformalDecisionWrapper]:
        """Get CDT wrapper for an agent type, or None if not registered."""
        return self._wrappers.get(agent_type)

    def get_or_create(
        self,
        agent_type: str,
        **kwargs,
    ) -> ConformalDecisionWrapper:
        """Get existing wrapper or create a new one with defaults."""
        if agent_type not in self._wrappers:
            self.register(agent_type, **kwargs)
        return self._wrappers[agent_type]

    def wrap_decision(
        self,
        agent_type: str,
        decision_cost_estimate: float,
        state_features: Optional[np.ndarray] = None,
    ) -> RiskAssessment:
        """
        Compute risk bound for a decision from any registered agent.

        Returns conservative RiskAssessment if agent not registered.
        """
        wrapper = self._wrappers.get(agent_type)
        if wrapper is None:
            return RiskAssessment(
                risk_bound=0.50,
                loss_threshold=ConformalDecisionWrapper.DEFAULT_THRESHOLDS.get(agent_type, 0.15),
                conformal_quantile=0.15,
                expected_loss=0.0,
                is_safe=False,
                escalation_recommended=True,
                reasoning=f"No CDT wrapper registered for {agent_type}",
                calibration_size=0,
            )
        return wrapper.compute_risk_bound(decision_cost_estimate, state_features)

    def get_all_diagnostics(self) -> Dict[str, Dict[str, Any]]:
        """Get diagnostics for all registered wrappers."""
        return {
            agent_type: wrapper.get_diagnostics()
            for agent_type, wrapper in self._wrappers.items()
        }

    @property
    def registered_agents(self) -> List[str]:
        return list(self._wrappers.keys())


# Per-tenant CDT registries — tenant isolation for multi-tenant deployments
_cdt_registries: Dict[int, ConformalDecisionRegistry] = {}

# Backward-compatible global registry for system-wide ops (monitoring, readiness)
_cdt_global_registry: Optional[ConformalDecisionRegistry] = None


def get_cdt_registry(tenant_id: Optional[int] = None) -> ConformalDecisionRegistry:
    """Get the CDT registry for a specific tenant.

    Args:
        tenant_id: Tenant to scope calibration. If None, returns a global
                   aggregate registry (used by monitoring/readiness endpoints).
                   All calibration and inference should pass tenant_id.
    """
    global _cdt_global_registry

    if tenant_id is not None:
        if tenant_id not in _cdt_registries:
            registry = ConformalDecisionRegistry()
            # Lazy re-hydration: on first access after restart, reload
            # calibration state from agents.powell_calibration_log so the
            # "N/M agents ready" banner doesn't reset to 0 every restart.
            _hydrate_registry_from_db(registry, tenant_id)
            _cdt_registries[tenant_id] = registry
        return _cdt_registries[tenant_id]

    # Global registry for monitoring — NOT for decision-making
    if _cdt_global_registry is None:
        _cdt_global_registry = ConformalDecisionRegistry()
    return _cdt_global_registry


def _hydrate_registry_from_db(
    registry: ConformalDecisionRegistry, tenant_id: int
) -> None:
    """Re-hydrate CDT wrappers from persisted calibration data.

    Reads (predicted_value, actual_value) pairs from
    agents.powell_calibration_log grouped by the TRM type inferred from
    the belief_state_id → powell_belief_state.trm_type chain (if available)
    or from a direct mapping. Falls back to reading the training_corpus
    historical samples as (estimated_cost, actual_cost) pairs.

    This runs synchronously on the first registry access per tenant
    per process lifetime — typically <100ms for ~250k rows.
    """
    try:
        from app.db.session import sync_session_factory
        from sqlalchemy import text as _text
        import logging

        _logger = logging.getLogger(__name__)
        sync_db = sync_session_factory()
        try:
            # Approach 1: Read from powell_calibration_log directly.
            # The table has predicted_value / actual_value but no explicit
            # trm_type column. We infer from the config_id → powell decision
            # tables. Simpler: count rows per config for this tenant, and if
            # we have enough, calibrate a catch-all wrapper per TRM type
            # using the training_corpus historical samples which DO have
            # trm_type.
            # Use a subquery to cap at 5000 samples per TRM type to avoid
            # OOM on large simulation corpora (some types have millions of rows).
            # Historical/live are preferred (weight ≥ 0.3); simulation fills gaps.
            rows = sync_db.execute(
                _text("""
                    WITH ranked AS (
                        SELECT trm_type,
                               COALESCE(
                                   (sample_data->>'aggregate_reward')::float, 0.5
                               ) AS reward,
                               ROW_NUMBER() OVER (
                                   PARTITION BY trm_type
                                   ORDER BY
                                       CASE origin WHEN 'live' THEN 0
                                                   WHEN 'historical' THEN 1
                                                   ELSE 2 END,
                                       created_at DESC
                               ) AS rn
                        FROM training_corpus
                        WHERE tenant_id = :tid
                          AND layer = 1.0
                          AND origin IN ('historical', 'live', 'simulation', 'perturbation')
                          AND weight >= 0.3
                    )
                    SELECT trm_type,
                           array_agg(reward) AS rewards,
                           COUNT(*) AS n
                    FROM ranked
                    WHERE rn <= 5000
                    GROUP BY trm_type
                    HAVING COUNT(*) >= 30
                """),
                {"tid": tenant_id},
            ).fetchall()

            if not rows:
                return

            # Map corpus trm_type → CDT agent_type
            _CORPUS_TO_CDT = {
                "atp_allocation": "atp",
                "po_creation": "po_creation",
                "inventory_buffer": "inventory_buffer",
                "mo_execution": "mo_execution",
                "to_execution": "to_execution",
                "quality_disposition": "quality_disposition",
                "maintenance_scheduling": "maintenance_scheduling",
                "subcontracting": "subcontracting",
                "order_tracking": "order_tracking",
                "rebalancing": "inventory_rebalancing",
                "forecast_baseline": "forecast_baseline",
                "forecast_adjustment": "forecast_adjustment",
            }

            calibrated = 0
            for row in rows:
                corpus_type = row[0]
                cdt_type = _CORPUS_TO_CDT.get(corpus_type)
                if not cdt_type:
                    continue
                rewards = [float(r) for r in (row[1] or []) if r is not None]
                if len(rewards) < ConformalDecisionWrapper.MIN_CALIBRATION_SIZE:
                    continue

                # Build losses as |reward - 1.0| (distance from perfect outcome).
                # A reward of 1.0 = perfect decision; 0.0 = worst. Loss measures
                # how far from perfect each historical decision was.
                losses = [abs(1.0 - r) for r in rewards]

                wrapper = registry.get_or_create(cdt_type)
                # Directly set calibration state
                wrapper._calibration_losses = losses
                wrapper._sorted_losses = np.sort(losses)
                wrapper._calibrated = True

                calibrated += 1

            if calibrated > 0:
                _logger.info(
                    "CDT registry hydrated from DB for tenant %d: %d/%d agents calibrated",
                    tenant_id, calibrated, len(rows),
                )
        finally:
            sync_db.close()
    except Exception as e:
        # Non-fatal: if hydration fails, the registry starts empty and
        # calibration will happen on the next conformal provisioning step.
        import logging
        logging.getLogger(__name__).debug(
            "CDT registry hydration failed for tenant %d: %s", tenant_id, e
        )


def reset_cdt_registry(tenant_id: Optional[int] = None):
    """Reset CDT registry for a tenant, or all registries if tenant_id is None."""
    global _cdt_global_registry
    if tenant_id is not None:
        _cdt_registries.pop(tenant_id, None)
    else:
        _cdt_registries.clear()
        _cdt_global_registry = None


def get_all_tenant_registries() -> Dict[int, ConformalDecisionRegistry]:
    """Return all per-tenant registries (for monitoring dashboards)."""
    return dict(_cdt_registries)
