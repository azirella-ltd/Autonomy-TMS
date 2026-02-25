"""
Decision Governance Service — Impact Scoring, AIIO Mode Assignment, Gating

Core responsibilities:
  1. score_impact()   — Compute composite 0-100 impact score across 5 dimensions
  2. assign_mode()    — Map impact score to AUTOMATE / INFORM / INSPECT
  3. gate_decision()  — Full pipeline: find policy → score → assign → set hold
  4. resolve_decision() — Human approves/rejects/overrides a held decision
  5. get_policy()     — Hierarchical policy lookup with fallback chain
  6. apply_directive() — Apply executive GuardrailDirective to governance policies

See docs/AGENT_GUARDRAILS_AND_AIIO.md for full framework documentation.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc

from app.models.agent_action import AgentAction, ActionMode, ExecutionResult
from app.models.decision_governance import DecisionGovernancePolicy, GuardrailDirective

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reversibility scores by action type (0 = trivially reversible, 100 = permanent)
# ---------------------------------------------------------------------------

REVERSIBILITY_SCORES: Dict[str, float] = {
    "forecast_adjustment": 10.0,
    "order_tracking": 15.0,
    "safety_stock": 20.0,
    "inventory_buffer": 20.0,
    "maintenance_scheduling": 25.0,
    "inventory_rebalance": 30.0,
    "to_execution": 40.0,
    "mo_execution": 50.0,
    "atp_execution": 60.0,
    "quality_disposition": 70.0,
    "subcontracting": 75.0,
    "po_creation": 80.0,
}

# Scope scores by hierarchy level
SCOPE_SCORES: Dict[str, float] = {
    "SITE": 20.0,
    "COUNTRY": 40.0,
    "REGION": 60.0,
    "COMPANY": 90.0,
    # Product hierarchy
    "PRODUCT": 15.0,
    "GROUP": 30.0,
    "FAMILY": 50.0,
    "CATEGORY": 70.0,
    "ALL": 90.0,
}


class DecisionGovernanceService:
    """
    Impact-based AIIO governance for agent decisions.

    Usage:
        service = DecisionGovernanceService()
        service.gate_decision(db, agent_action, customer_id)
        # action.action_mode is now AUTOMATE/INFORM/INSPECT
        # If INSPECT: action.hold_until is set, execution_result = PENDING
    """

    # ------------------------------------------------------------------
    # Impact scoring
    # ------------------------------------------------------------------

    @staticmethod
    def score_impact(
        action_type: str,
        category: str,
        estimated_impact: Optional[Dict],
        confidence_level: Optional[float],
        site_hierarchy_level: str,
        product_hierarchy_level: str,
        customer_id: int,
        db: Session,
        policy: Optional[DecisionGovernancePolicy] = None,
    ) -> Dict[str, Any]:
        """
        Compute composite impact score (0-100) across five dimensions.

        Returns:
            {
                "score": float,      # Composite 0-100
                "financial": float,  # Per-dimension score (0-100)
                "scope": float,
                "reversibility": float,
                "confidence": float,
                "override_rate": float,
            }
        """
        # Weights from policy or defaults
        w_fin = policy.weight_financial if policy else 0.30
        w_scope = policy.weight_scope if policy else 0.20
        w_rev = policy.weight_reversibility if policy else 0.20
        w_conf = policy.weight_confidence if policy else 0.15
        w_over = policy.weight_override_rate if policy else 0.15

        # 1. Financial magnitude (0-100)
        financial = 0.0
        if estimated_impact:
            # Use absolute cost_saved or cost_impact as proxy
            cost = abs(estimated_impact.get("cost_saved", 0) or
                       estimated_impact.get("cost_impact", 0) or
                       estimated_impact.get("value", 0) or 0)
            # Normalize: $0 → 0, $1K → 10, $10K → 30, $100K → 60, $1M+ → 100
            if cost > 0:
                import math
                financial = min(100.0, 20.0 * math.log10(max(1, cost)))

        # 2. Scope / blast radius (0-100)
        site_score = SCOPE_SCORES.get(site_hierarchy_level, 20.0)
        product_score = SCOPE_SCORES.get(product_hierarchy_level, 15.0)
        scope = max(site_score, product_score)

        # 3. Reversibility (0-100)
        reversibility = REVERSIBILITY_SCORES.get(action_type, 50.0)

        # 4. Confidence (inverted: low confidence → high impact)
        if confidence_level is not None and 0 <= confidence_level <= 1:
            confidence = (1.0 - confidence_level) * 100.0
        else:
            confidence = 50.0  # Unknown confidence = moderate concern

        # 5. Override rate (0-100) — historical override frequency
        override_rate = DecisionGovernanceService._get_override_rate(
            db, customer_id, action_type,
        )

        # Weighted composite
        composite = (
            w_fin * financial +
            w_scope * scope +
            w_rev * reversibility +
            w_conf * confidence +
            w_over * override_rate
        )
        # Clamp to 0-100
        composite = max(0.0, min(100.0, composite))

        return {
            "score": round(composite, 2),
            "financial": round(financial, 2),
            "scope": round(scope, 2),
            "reversibility": round(reversibility, 2),
            "confidence": round(confidence, 2),
            "override_rate": round(override_rate, 2),
        }

    # ------------------------------------------------------------------
    # Mode assignment
    # ------------------------------------------------------------------

    @staticmethod
    def assign_mode(
        impact_score: float,
        policy: Optional[DecisionGovernancePolicy],
    ) -> ActionMode:
        """Map impact score to AIIO mode using policy thresholds."""
        automate_below = policy.automate_below if policy else 20.0
        inform_below = policy.inform_below if policy else 50.0

        if impact_score < automate_below:
            return ActionMode.AUTOMATE
        elif impact_score < inform_below:
            return ActionMode.INFORM
        else:
            return ActionMode.INSPECT

    # ------------------------------------------------------------------
    # Full governance gate
    # ------------------------------------------------------------------

    @staticmethod
    def gate_decision(
        db: Session,
        action: AgentAction,
        customer_id: int,
    ) -> AgentAction:
        """
        Full governance pipeline for an AgentAction.

        1. Find matching policy (most specific wins)
        2. Score impact → set impact_score and impact_breakdown
        3. Assign AIIO mode
        4. If INSPECT: set hold_until, execution_result = PENDING
        5. Check for active GuardrailDirectives that match scope

        The action object is mutated in place and returned.
        """
        # Find matching policy
        policy = DecisionGovernanceService.get_policy(
            db, customer_id,
            action.action_type,
            action.category.value if hasattr(action.category, 'value') else str(action.category),
            action.agent_id,
        )

        # Score impact
        breakdown = DecisionGovernanceService.score_impact(
            action_type=action.action_type,
            category=action.category.value if hasattr(action.category, 'value') else str(action.category),
            estimated_impact=action.estimated_impact,
            confidence_level=action.confidence_level,
            site_hierarchy_level=action.site_hierarchy_level.value if hasattr(action.site_hierarchy_level, 'value') else str(action.site_hierarchy_level),
            product_hierarchy_level=action.product_hierarchy_level.value if hasattr(action.product_hierarchy_level, 'value') else str(action.product_hierarchy_level),
            customer_id=customer_id,
            db=db,
            policy=policy,
        )

        action.impact_score = breakdown["score"]
        action.impact_breakdown = breakdown

        if policy:
            action.governance_policy_id = policy.id

        # Assign AIIO mode
        mode = DecisionGovernanceService.assign_mode(breakdown["score"], policy)
        action.action_mode = mode

        # Check for active guardrail directives that might override mode
        directive = DecisionGovernanceService._find_active_directive(
            db, customer_id, action.action_type,
            action.category.value if hasattr(action.category, 'value') else str(action.category),
        )
        if directive:
            action.guardrail_directive_id = directive.id
            # If directive has stricter thresholds, re-evaluate
            if directive.extracted_parameters:
                params = directive.extracted_parameters
                dir_inform = params.get("inform_below")
                dir_automate = params.get("automate_below")
                if dir_inform is not None and breakdown["score"] >= dir_inform:
                    mode = ActionMode.INSPECT
                    action.action_mode = mode
                elif dir_automate is not None and breakdown["score"] >= dir_automate:
                    if mode == ActionMode.AUTOMATE:
                        mode = ActionMode.INFORM
                        action.action_mode = mode

        # Set hold window for INSPECT
        if mode == ActionMode.INSPECT:
            hold_minutes = policy.hold_minutes if policy else 60
            action.hold_until = datetime.utcnow() + timedelta(minutes=hold_minutes)
            action.execution_result = ExecutionResult.PENDING
        # AUTOMATE/INFORM proceed immediately
        # (execution_result stays as whatever the caller set, typically SUCCESS)

        logger.info(
            "Governance gate: action_type=%s impact=%.1f mode=%s hold=%s directive=%s",
            action.action_type, breakdown["score"], mode.value,
            action.hold_until.isoformat() if action.hold_until else "none",
            directive.id if directive else "none",
        )

        return action

    # ------------------------------------------------------------------
    # Decision resolution (human review of INSPECT decisions)
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_decision(
        db: Session,
        action_id: int,
        user_id: int,
        resolution: str,
        reason: Optional[str] = None,
        override_action: Optional[Dict] = None,
        override_reason: Optional[str] = None,
    ) -> AgentAction:
        """
        Resolve a held (INSPECT) decision.

        Args:
            action_id: The AgentAction.id to resolve.
            user_id: The user resolving.
            resolution: "approve" | "reject" | "override"
            reason: Why (mandatory for reject, optional for approve).
            override_action: What the user chose instead (for override).
            override_reason: Why they overrode (mandatory for override).

        Returns:
            Updated AgentAction.

        Raises:
            ValueError: If action not found, not PENDING, or missing required fields.
        """
        action = db.query(AgentAction).filter_by(id=action_id).first()
        if not action:
            raise ValueError(f"AgentAction {action_id} not found")

        if action.execution_result != ExecutionResult.PENDING:
            raise ValueError(
                f"AgentAction {action_id} is not PENDING "
                f"(current: {action.execution_result.value})"
            )

        now = datetime.utcnow()
        action.resolved_by = user_id
        action.resolved_at = now

        if resolution == "approve":
            action.execution_result = ExecutionResult.SUCCESS
            action.hold_until = None  # No longer held
            action.resolution_reason = reason
            logger.info("Governance resolve: action=%d approved by user=%d", action_id, user_id)

        elif resolution == "reject":
            if not reason:
                raise ValueError("Reason is required when rejecting a decision")
            action.execution_result = ExecutionResult.FAILED
            action.hold_until = None
            action.resolution_reason = reason
            logger.info("Governance resolve: action=%d rejected by user=%d reason=%s",
                        action_id, user_id, reason[:100])

        elif resolution == "override":
            if not override_reason:
                raise ValueError("Override reason is required")
            action.execution_result = ExecutionResult.SUCCESS
            action.hold_until = None
            action.resolution_reason = reason
            # Set override fields
            action.is_overridden = True
            action.overridden_by = user_id
            action.overridden_at = now
            action.override_reason = override_reason
            action.override_action = override_action
            logger.info("Governance resolve: action=%d overridden by user=%d", action_id, user_id)

        else:
            raise ValueError(f"Invalid resolution: {resolution}. Must be approve/reject/override")

        db.flush()
        return action

    # ------------------------------------------------------------------
    # Policy lookup
    # ------------------------------------------------------------------

    @staticmethod
    def get_policy(
        db: Session,
        customer_id: int,
        action_type: Optional[str] = None,
        category: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Optional[DecisionGovernancePolicy]:
        """
        Find the most specific active governance policy for this decision.

        Fallback chain (most specific first):
          1. (customer, action_type, category, agent_id)
          2. (customer, action_type, category)
          3. (customer, action_type)
          4. (customer)  — catch-all
        """
        base = db.query(DecisionGovernancePolicy).filter(
            DecisionGovernancePolicy.customer_id == customer_id,
            DecisionGovernancePolicy.is_active == True,
        )

        # Try from most specific to least
        candidates = [
            # Exact match on all three
            base.filter(
                DecisionGovernancePolicy.action_type == action_type,
                DecisionGovernancePolicy.category == category,
                DecisionGovernancePolicy.agent_id == agent_id,
            ),
            # Match type + category
            base.filter(
                DecisionGovernancePolicy.action_type == action_type,
                DecisionGovernancePolicy.category == category,
                DecisionGovernancePolicy.agent_id == None,
            ),
            # Match type only
            base.filter(
                DecisionGovernancePolicy.action_type == action_type,
                DecisionGovernancePolicy.category == None,
                DecisionGovernancePolicy.agent_id == None,
            ),
            # Customer catch-all
            base.filter(
                DecisionGovernancePolicy.action_type == None,
                DecisionGovernancePolicy.category == None,
                DecisionGovernancePolicy.agent_id == None,
            ),
        ]

        for query in candidates:
            policy = query.order_by(DecisionGovernancePolicy.priority).first()
            if policy:
                return policy

        return None  # No policy → caller uses system defaults

    # ------------------------------------------------------------------
    # Governance worklist queries
    # ------------------------------------------------------------------

    @staticmethod
    def get_pending_decisions(
        db: Session,
        customer_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AgentAction]:
        """Get INSPECT decisions awaiting review, ordered by urgency."""
        return db.query(AgentAction).filter(
            AgentAction.customer_id == customer_id,
            AgentAction.action_mode == ActionMode.INSPECT,
            AgentAction.execution_result == ExecutionResult.PENDING,
        ).order_by(
            AgentAction.hold_until.asc(),  # Most urgent first
            AgentAction.impact_score.desc(),
        ).offset(offset).limit(limit).all()

    @staticmethod
    def get_governance_stats(db: Session, customer_id: int) -> Dict[str, Any]:
        """Compute governance metrics for dashboard."""
        base = db.query(AgentAction).filter(
            AgentAction.customer_id == customer_id,
            AgentAction.impact_score != None,
        )

        total = base.count()
        if total == 0:
            return {
                "total_governed": 0,
                "automate_count": 0,
                "inform_count": 0,
                "inspect_count": 0,
                "pending_count": 0,
                "avg_impact_score": 0,
                "auto_apply_count": 0,
                "human_resolved_count": 0,
                "avg_resolution_minutes": None,
                "override_in_review_count": 0,
            }

        automate = base.filter(AgentAction.action_mode == ActionMode.AUTOMATE).count()
        inform = base.filter(AgentAction.action_mode == ActionMode.INFORM).count()
        inspect = base.filter(AgentAction.action_mode == ActionMode.INSPECT).count()
        pending = base.filter(
            AgentAction.action_mode == ActionMode.INSPECT,
            AgentAction.execution_result == ExecutionResult.PENDING,
        ).count()

        avg_impact = db.query(func.avg(AgentAction.impact_score)).filter(
            AgentAction.customer_id == customer_id,
            AgentAction.impact_score != None,
        ).scalar() or 0

        # Resolved by humans (have resolved_by set)
        human_resolved = base.filter(
            AgentAction.resolved_by != None,
        ).count()

        # Auto-applied (INSPECT that became SUCCESS without resolved_by)
        auto_applied = base.filter(
            AgentAction.action_mode == ActionMode.INSPECT,
            AgentAction.execution_result == ExecutionResult.SUCCESS,
            AgentAction.resolved_by == None,
        ).count()

        # Overrides during INSPECT review
        override_in_review = base.filter(
            AgentAction.action_mode == ActionMode.INSPECT,
            AgentAction.is_overridden == True,
        ).count()

        # Average resolution time for human-resolved decisions
        avg_res_minutes = None
        resolved_with_time = db.query(AgentAction).filter(
            AgentAction.customer_id == customer_id,
            AgentAction.resolved_at != None,
            AgentAction.created_at != None,
        ).all()
        if resolved_with_time:
            deltas = []
            for a in resolved_with_time:
                if a.resolved_at and a.created_at:
                    delta = (a.resolved_at - a.created_at).total_seconds() / 60.0
                    deltas.append(delta)
            if deltas:
                avg_res_minutes = round(sum(deltas) / len(deltas), 1)

        return {
            "total_governed": total,
            "automate_count": automate,
            "inform_count": inform,
            "inspect_count": inspect,
            "pending_count": pending,
            "avg_impact_score": round(float(avg_impact), 2),
            "auto_apply_count": auto_applied,
            "human_resolved_count": human_resolved,
            "avg_resolution_minutes": avg_res_minutes,
            "override_in_review_count": override_in_review,
        }

    # ------------------------------------------------------------------
    # Guardrail directive application
    # ------------------------------------------------------------------

    @staticmethod
    def apply_directive(
        db: Session,
        directive_id: int,
        reviewer_user_id: int,
        review_comment: Optional[str] = None,
    ) -> GuardrailDirective:
        """
        Apply a GuardrailDirective by creating/updating governance policies.

        The directive's extracted_parameters are used to create a new
        DecisionGovernancePolicy or update an existing one.
        """
        directive = db.query(GuardrailDirective).filter_by(id=directive_id).first()
        if not directive:
            raise ValueError(f"GuardrailDirective {directive_id} not found")

        if directive.status != "PENDING":
            raise ValueError(f"Directive {directive_id} is not PENDING (status={directive.status})")

        params = directive.extracted_parameters or {}
        if not params:
            raise ValueError("No extracted parameters to apply")

        # Create a new governance policy from the directive
        policy = DecisionGovernancePolicy(
            customer_id=directive.customer_id,
            action_type=params.get("action_type"),
            category=params.get("category"),
            agent_id=params.get("agent_id"),
            automate_below=params.get("automate_below", 20.0),
            inform_below=params.get("inform_below", 50.0),
            hold_minutes=params.get("hold_minutes", 60),
            max_hold_minutes=params.get("max_hold_minutes", 1440),
            auto_apply_on_expiry=params.get("auto_apply_on_expiry", True),
            escalate_after_minutes=params.get("escalate_after_minutes", 480),
            name=f"From directive: {directive.objective[:100]}",
            description=(
                f"Applied from executive directive #{directive.id}\n"
                f"Source: {directive.source_channel} from user #{directive.source_user_id}\n"
                f"Objective: {directive.objective}\n"
                f"Context: {directive.context or 'N/A'}\n"
                f"Reason: {directive.reason or 'N/A'}"
            ),
            is_active=True,
            priority=50,  # Higher priority than defaults
            created_by=reviewer_user_id,
        )
        db.add(policy)
        db.flush()

        # Update directive status
        directive.status = "APPLIED"
        directive.reviewed_by = reviewer_user_id
        directive.reviewed_at = datetime.utcnow()
        directive.review_comment = review_comment
        directive.applied_policy_id = policy.id

        db.flush()

        logger.info(
            "Applied guardrail directive %d → policy %d (customer=%d, user=%d)",
            directive.id, policy.id, directive.customer_id, reviewer_user_id,
        )

        return directive

    @staticmethod
    def reject_directive(
        db: Session,
        directive_id: int,
        reviewer_user_id: int,
        review_comment: str,
    ) -> GuardrailDirective:
        """Reject a GuardrailDirective with mandatory comment."""
        directive = db.query(GuardrailDirective).filter_by(id=directive_id).first()
        if not directive:
            raise ValueError(f"GuardrailDirective {directive_id} not found")

        if directive.status != "PENDING":
            raise ValueError(f"Directive {directive_id} is not PENDING (status={directive.status})")

        directive.status = "REJECTED"
        directive.reviewed_by = reviewer_user_id
        directive.reviewed_at = datetime.utcnow()
        directive.review_comment = review_comment

        db.flush()
        return directive

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_override_rate(
        db: Session,
        customer_id: int,
        action_type: str,
    ) -> float:
        """
        Compute historical override rate for this action type (0-100).

        Looks at recent AgentAction rows to compute:
          override_rate = (overridden_count / total_count) * 100
        """
        total = db.query(func.count(AgentAction.id)).filter(
            AgentAction.customer_id == customer_id,
            AgentAction.action_type == action_type,
        ).scalar() or 0

        if total < 5:
            return 30.0  # Not enough data, assume moderate

        overridden = db.query(func.count(AgentAction.id)).filter(
            AgentAction.customer_id == customer_id,
            AgentAction.action_type == action_type,
            AgentAction.is_overridden == True,
        ).scalar() or 0

        return min(100.0, (overridden / total) * 100.0)

    @staticmethod
    def _find_active_directive(
        db: Session,
        customer_id: int,
        action_type: str,
        category: str,
    ) -> Optional[GuardrailDirective]:
        """
        Find an active (APPLIED) guardrail directive whose scope matches
        this decision.  Used to apply executive overrides on governance.
        """
        now = datetime.utcnow()

        directives = db.query(GuardrailDirective).filter(
            GuardrailDirective.customer_id == customer_id,
            GuardrailDirective.status == "APPLIED",
            or_(
                GuardrailDirective.effective_until == None,
                GuardrailDirective.effective_until > now,
            ),
            or_(
                GuardrailDirective.effective_from == None,
                GuardrailDirective.effective_from <= now,
            ),
        ).order_by(desc(GuardrailDirective.received_at)).all()

        for d in directives:
            scope = d.affected_scope or {}
            # Check if this directive's scope matches
            action_types = scope.get("action_types", [])
            categories = scope.get("categories", [])

            # Empty lists mean "all"
            type_match = not action_types or action_type in action_types
            cat_match = not categories or category in categories

            if type_match and cat_match:
                return d

        return None
