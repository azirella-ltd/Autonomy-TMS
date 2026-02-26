"""
Decision Service

Planning decision tracking with full audit trail:
- Record decisions (override, accept, reject, defer)
- Link to AI recommendations
- Track approval workflows
- Apply and revert decisions

Part of the Planning Cycle Management system.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.models.planning_decision import (
    PlanningDecision, DecisionHistory, DecisionComment,
    DecisionAction, DecisionCategory, DecisionStatus, DecisionPriority,
    DECISION_REASON_CODES, DEFAULT_APPROVAL_THRESHOLDS
)
from app.models.planning_cycle import (
    PlanningCycle, PlanningSnapshot, SnapshotDelta,
    SnapshotType, DeltaOperation, DeltaEntityType
)

logger = logging.getLogger(__name__)


class DecisionService:
    """
    Service for managing planning decisions with audit trail.

    Tracks all decisions made during planning cycles with full history.
    """

    def __init__(self, db: Session):
        """
        Initialize decision service.

        Args:
            db: Database session
        """
        self.db = db

    def record_decision(
        self,
        cycle_id: int,
        tenant_id: int,
        category: DecisionCategory,
        action: DecisionAction,
        original_value: Dict[str, Any],
        decided_value: Dict[str, Any],
        decided_by: int,
        reason_code: Optional[str] = None,
        reason_text: Optional[str] = None,
        recommendation_id: Optional[str] = None,
        ai_recommended_value: Optional[Dict[str, Any]] = None,
        ai_confidence: Optional[float] = None,
        product_id: Optional[str] = None,
        site_id: Optional[str] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
        priority: DecisionPriority = DecisionPriority.MEDIUM,
        supporting_data: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> PlanningDecision:
        """
        Record a planning decision.

        Args:
            cycle_id: Planning cycle ID
            tenant_id: Customer ID
            category: Decision category
            action: Decision action type
            original_value: Value before decision
            decided_value: Value after decision
            decided_by: User ID making decision
            reason_code: Reason code from DECISION_REASON_CODES
            reason_text: Free-form reason text
            recommendation_id: AI recommendation ID
            ai_recommended_value: What AI recommended
            ai_confidence: AI confidence score
            product_id: Product scope
            site_id: Site scope
            period_start: Period scope start
            period_end: Period scope end
            priority: Decision priority
            supporting_data: Supporting evidence/data
            tags: Tags for classification

        Returns:
            Created PlanningDecision
        """
        # Get current snapshot for the cycle
        cycle = self.db.query(PlanningCycle).filter_by(id=cycle_id).first()
        if not cycle:
            raise ValueError(f"Planning cycle {cycle_id} not found")

        # Generate decision code
        decision_code = self._generate_decision_code(category, action)

        # Calculate value delta
        value_delta = self._calculate_delta(original_value, decided_value)

        # Check if approval is required
        requires_approval, approval_level = self._check_approval_required(
            category, action, value_delta
        )

        # Estimate impact
        estimated_impact = self._estimate_impact(category, original_value, decided_value)

        decision = PlanningDecision(
            cycle_id=cycle_id,
            snapshot_id=cycle.current_snapshot_id,
            tenant_id=tenant_id,
            decision_code=decision_code,
            category=category,
            action=action,
            priority=priority,
            product_id=product_id,
            site_id=site_id,
            period_start=period_start,
            period_end=period_end,
            recommendation_id=recommendation_id,
            ai_recommended_value=ai_recommended_value,
            ai_confidence=ai_confidence,
            original_value=original_value,
            decided_value=decided_value,
            value_delta=value_delta,
            reason_code=reason_code,
            reason_text=reason_text,
            supporting_data=supporting_data,
            estimated_impact=estimated_impact,
            status=DecisionStatus.PENDING_APPROVAL if requires_approval else DecisionStatus.PENDING,
            requires_approval=requires_approval,
            approval_level=approval_level,
            decided_by=decided_by,
            decided_at=datetime.utcnow(),
            tags=tags
        )
        self.db.add(decision)
        self.db.commit()
        self.db.refresh(decision)

        # Record history
        self._record_history(
            decision=decision,
            change_type="created",
            new_status=decision.status.value,
            changed_by=decided_by,
            change_notes=f"Decision recorded: {action.value}"
        )

        logger.info(f"Recorded decision {decision.id}: {decision_code}")

        return decision

    def approve_decision(
        self,
        decision_id: int,
        approved_by: int,
        approval_notes: Optional[str] = None
    ) -> PlanningDecision:
        """
        Approve a pending decision.

        Args:
            decision_id: Decision ID
            approved_by: User ID approving
            approval_notes: Approval notes

        Returns:
            Updated decision
        """
        decision = self.db.query(PlanningDecision).filter_by(id=decision_id).first()
        if not decision:
            raise ValueError(f"Decision {decision_id} not found")

        if decision.status != DecisionStatus.PENDING_APPROVAL:
            raise ValueError(f"Decision is not pending approval (status: {decision.status.value})")

        old_status = decision.status
        decision.status = DecisionStatus.APPROVED
        decision.approved_by = approved_by
        decision.approved_at = datetime.utcnow()
        decision.approval_notes = approval_notes

        self.db.commit()

        # Record history
        self._record_history(
            decision=decision,
            change_type="approved",
            previous_status=old_status.value,
            new_status=decision.status.value,
            changed_by=approved_by,
            change_notes=approval_notes
        )

        logger.info(f"Approved decision {decision_id}")

        return decision

    def reject_decision(
        self,
        decision_id: int,
        rejected_by: int,
        rejection_reason: str
    ) -> PlanningDecision:
        """
        Reject a pending decision.

        Args:
            decision_id: Decision ID
            rejected_by: User ID rejecting
            rejection_reason: Reason for rejection

        Returns:
            Updated decision
        """
        decision = self.db.query(PlanningDecision).filter_by(id=decision_id).first()
        if not decision:
            raise ValueError(f"Decision {decision_id} not found")

        if decision.status not in (DecisionStatus.PENDING, DecisionStatus.PENDING_APPROVAL):
            raise ValueError(f"Decision cannot be rejected (status: {decision.status.value})")

        old_status = decision.status
        decision.status = DecisionStatus.REJECTED
        decision.approved_by = rejected_by
        decision.approved_at = datetime.utcnow()
        decision.rejection_reason = rejection_reason

        self.db.commit()

        # Record history
        self._record_history(
            decision=decision,
            change_type="rejected",
            previous_status=old_status.value,
            new_status=decision.status.value,
            changed_by=rejected_by,
            change_notes=rejection_reason
        )

        logger.info(f"Rejected decision {decision_id}")

        return decision

    def apply_decision(
        self,
        decision_id: int,
        applied_by: int
    ) -> PlanningDecision:
        """
        Apply an approved decision to create a new snapshot.

        Args:
            decision_id: Decision ID
            applied_by: User ID applying

        Returns:
            Updated decision with execution snapshot
        """
        decision = self.db.query(PlanningDecision).filter_by(id=decision_id).first()
        if not decision:
            raise ValueError(f"Decision {decision_id} not found")

        if decision.status not in (DecisionStatus.PENDING, DecisionStatus.APPROVED):
            raise ValueError(f"Decision cannot be applied (status: {decision.status.value})")

        if decision.requires_approval and decision.status != DecisionStatus.APPROVED:
            raise ValueError("Decision requires approval before applying")

        # Create new snapshot with the decision
        from app.services.planning_cycle_service import PlanningCycleService

        planning_service = PlanningCycleService(self.db)

        snapshot = planning_service.create_snapshot(
            cycle_id=decision.cycle_id,
            snapshot_type=SnapshotType.WORKING,
            commit_message=f"Applied decision: {decision.decision_code}",
            created_by=applied_by,
            tags=[f"decision:{decision.id}"]
        )

        # Add delta to snapshot
        entity_type = self._category_to_entity_type(decision.category)
        entity_key = self._build_entity_key(decision)

        planning_service.add_delta(
            snapshot_id=snapshot.id,
            entity_type=entity_type,
            entity_key=entity_key,
            operation=DeltaOperation.UPDATE,
            delta_data=decision.decided_value,
            changed_fields=list(decision.decided_value.keys()) if decision.decided_value else None,
            original_values=decision.original_value,
            change_reason=f"Decision {decision.decision_code}: {decision.reason_code or 'Applied'}",
            decision_id=decision.id,
            created_by=applied_by
        )

        # Update decision
        old_status = decision.status
        decision.status = DecisionStatus.APPLIED
        decision.applied_at = datetime.utcnow()
        decision.applied_by = applied_by
        decision.execution_snapshot_id = snapshot.id

        self.db.commit()

        # Record history
        self._record_history(
            decision=decision,
            change_type="applied",
            previous_status=old_status.value,
            new_status=decision.status.value,
            changed_by=applied_by,
            change_notes=f"Applied in snapshot {snapshot.id}",
            snapshot_id=snapshot.id
        )

        logger.info(f"Applied decision {decision_id} in snapshot {snapshot.id}")

        return decision

    def revert_decision(
        self,
        decision_id: int,
        reverted_by: int,
        revert_reason: str
    ) -> PlanningDecision:
        """
        Revert an applied decision.

        Args:
            decision_id: Decision ID
            reverted_by: User ID reverting
            revert_reason: Reason for reversion

        Returns:
            Updated decision
        """
        decision = self.db.query(PlanningDecision).filter_by(id=decision_id).first()
        if not decision:
            raise ValueError(f"Decision {decision_id} not found")

        if decision.status != DecisionStatus.APPLIED:
            raise ValueError(f"Only applied decisions can be reverted (status: {decision.status.value})")

        # Create reversion snapshot
        from app.services.planning_cycle_service import PlanningCycleService

        planning_service = PlanningCycleService(self.db)

        snapshot = planning_service.create_snapshot(
            cycle_id=decision.cycle_id,
            snapshot_type=SnapshotType.WORKING,
            commit_message=f"Reverted decision: {decision.decision_code}",
            created_by=reverted_by,
            tags=[f"revert:{decision.id}"]
        )

        # Add reversion delta (restore original value)
        entity_type = self._category_to_entity_type(decision.category)
        entity_key = self._build_entity_key(decision)

        planning_service.add_delta(
            snapshot_id=snapshot.id,
            entity_type=entity_type,
            entity_key=entity_key,
            operation=DeltaOperation.UPDATE,
            delta_data=decision.original_value,
            original_values=decision.decided_value,
            change_reason=f"Reverted decision {decision.decision_code}: {revert_reason}",
            decision_id=decision.id,
            created_by=reverted_by
        )

        # Update decision
        old_status = decision.status
        decision.status = DecisionStatus.REVERTED
        decision.reverted_at = datetime.utcnow()
        decision.reverted_by = reverted_by
        decision.revert_reason = revert_reason
        decision.revert_snapshot_id = snapshot.id

        self.db.commit()

        # Record history
        self._record_history(
            decision=decision,
            change_type="reverted",
            previous_status=old_status.value,
            new_status=decision.status.value,
            changed_by=reverted_by,
            change_notes=revert_reason,
            snapshot_id=snapshot.id
        )

        logger.info(f"Reverted decision {decision_id}")

        return decision

    def get_decision_history(self, decision_id: int) -> List[DecisionHistory]:
        """
        Get history for a decision.

        Args:
            decision_id: Decision ID

        Returns:
            List of history records
        """
        return self.db.query(DecisionHistory).filter(
            DecisionHistory.decision_id == decision_id
        ).order_by(DecisionHistory.changed_at).all()

    def get_cycle_decisions(
        self,
        cycle_id: int,
        category: Optional[DecisionCategory] = None,
        action: Optional[DecisionAction] = None,
        status: Optional[DecisionStatus] = None,
        product_id: Optional[str] = None,
        site_id: Optional[str] = None
    ) -> List[PlanningDecision]:
        """
        Get decisions for a planning cycle.

        Args:
            cycle_id: Cycle ID
            category: Filter by category
            action: Filter by action
            status: Filter by status
            product_id: Filter by product
            site_id: Filter by site

        Returns:
            List of decisions
        """
        query = self.db.query(PlanningDecision).filter(
            PlanningDecision.cycle_id == cycle_id
        )

        if category:
            query = query.filter(PlanningDecision.category == category)
        if action:
            query = query.filter(PlanningDecision.action == action)
        if status:
            query = query.filter(PlanningDecision.status == status)
        if product_id:
            query = query.filter(PlanningDecision.product_id == product_id)
        if site_id:
            query = query.filter(PlanningDecision.site_id == site_id)

        return query.order_by(PlanningDecision.created_at.desc()).all()

    def get_pending_approvals(
        self,
        tenant_id: int,
        approval_level: Optional[str] = None
    ) -> List[PlanningDecision]:
        """
        Get decisions pending approval.

        Args:
            tenant_id: Customer ID
            approval_level: Filter by approval level

        Returns:
            List of pending decisions
        """
        query = self.db.query(PlanningDecision).filter(
            and_(
                PlanningDecision.tenant_id == tenant_id,
                PlanningDecision.status == DecisionStatus.PENDING_APPROVAL
            )
        )

        if approval_level:
            query = query.filter(PlanningDecision.approval_level == approval_level)

        return query.order_by(PlanningDecision.created_at).all()

    def add_comment(
        self,
        decision_id: int,
        content: str,
        created_by: int,
        is_internal: bool = False,
        parent_comment_id: Optional[int] = None,
        mentioned_users: Optional[List[int]] = None
    ) -> DecisionComment:
        """
        Add a comment to a decision.

        Args:
            decision_id: Decision ID
            content: Comment content
            created_by: User ID
            is_internal: Internal note flag
            parent_comment_id: Parent comment for threading
            mentioned_users: List of mentioned user IDs

        Returns:
            Created comment
        """
        decision = self.db.query(PlanningDecision).filter_by(id=decision_id).first()
        if not decision:
            raise ValueError(f"Decision {decision_id} not found")

        comment = DecisionComment(
            decision_id=decision_id,
            content=content,
            is_internal=is_internal,
            parent_comment_id=parent_comment_id,
            mentioned_users=mentioned_users,
            created_by=created_by
        )
        self.db.add(comment)

        # Update comment count
        decision.comments_count = (decision.comments_count or 0) + 1

        self.db.commit()
        self.db.refresh(comment)

        return comment

    def get_decision_stats(self, cycle_id: int) -> Dict[str, Any]:
        """
        Get decision statistics for a cycle.

        Args:
            cycle_id: Cycle ID

        Returns:
            Statistics dict
        """
        decisions = self.db.query(PlanningDecision).filter(
            PlanningDecision.cycle_id == cycle_id
        ).all()

        stats = {
            "total": len(decisions),
            "by_action": {},
            "by_category": {},
            "by_status": {},
            "ai_recommendations": {
                "accepted": 0,
                "overridden": 0,
                "rejected": 0
            },
            "pending_approval": 0
        }

        for decision in decisions:
            # By action
            action = decision.action.value
            stats["by_action"][action] = stats["by_action"].get(action, 0) + 1

            # By category
            category = decision.category.value
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1

            # By status
            status = decision.status.value
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

            # AI recommendations
            if decision.recommendation_id:
                if decision.action == DecisionAction.ACCEPT:
                    stats["ai_recommendations"]["accepted"] += 1
                elif decision.action == DecisionAction.OVERRIDE:
                    stats["ai_recommendations"]["overridden"] += 1
                elif decision.action == DecisionAction.REJECT:
                    stats["ai_recommendations"]["rejected"] += 1

            # Pending approval count
            if decision.status == DecisionStatus.PENDING_APPROVAL:
                stats["pending_approval"] += 1

        return stats

    # ==================== Private Methods ====================

    def _generate_decision_code(self, category: DecisionCategory, action: DecisionAction) -> str:
        """Generate unique decision code."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        short_uuid = str(uuid.uuid4())[:8]
        return f"DEC-{category.value[:3].upper()}-{timestamp}-{short_uuid}"

    def _calculate_delta(
        self,
        original: Dict[str, Any],
        decided: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate delta between original and decided values."""
        if not original or not decided:
            return {}

        delta = {}
        for key in set(list(original.keys()) + list(decided.keys())):
            orig_val = original.get(key)
            dec_val = decided.get(key)

            if orig_val != dec_val:
                delta[key] = {
                    "original": orig_val,
                    "decided": dec_val
                }

                # Calculate numeric delta
                if isinstance(orig_val, (int, float)) and isinstance(dec_val, (int, float)):
                    delta[key]["delta"] = dec_val - orig_val
                    if orig_val != 0:
                        delta[key]["delta_percent"] = ((dec_val - orig_val) / orig_val) * 100

        return delta

    def _check_approval_required(
        self,
        category: DecisionCategory,
        action: DecisionAction,
        value_delta: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """Check if approval is required for this decision."""
        thresholds = DEFAULT_APPROVAL_THRESHOLDS.get(category.value, {})

        if not thresholds:
            return False, None

        # Check each approval level
        for level in ["vp", "director", "manager"]:
            level_thresholds = thresholds.get(level, {})

            for field, threshold in level_thresholds.items():
                if field in value_delta:
                    delta_val = value_delta[field].get("delta_percent") or value_delta[field].get("delta", 0)
                    if abs(delta_val) >= threshold:
                        return True, level

        return False, None

    def _estimate_impact(
        self,
        category: DecisionCategory,
        original: Dict[str, Any],
        decided: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Estimate impact of the decision."""
        impact = {
            "financial": {},
            "service_level": {},
            "inventory": {},
            "risk": {"level": "low"}
        }

        # This would integrate with actual impact calculation services
        # For now, return basic structure

        return impact

    def _record_history(
        self,
        decision: PlanningDecision,
        change_type: str,
        changed_by: int,
        previous_status: Optional[str] = None,
        new_status: Optional[str] = None,
        changed_fields: Optional[List[str]] = None,
        previous_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        change_notes: Optional[str] = None,
        snapshot_id: Optional[int] = None
    ) -> DecisionHistory:
        """Record a history entry for decision changes."""
        history = DecisionHistory(
            decision_id=decision.id,
            change_type=change_type,
            previous_status=previous_status,
            new_status=new_status,
            changed_fields=changed_fields,
            previous_values=previous_values,
            new_values=new_values,
            changed_by=changed_by,
            change_notes=change_notes,
            snapshot_id=snapshot_id
        )
        self.db.add(history)
        self.db.commit()

        return history

    def _category_to_entity_type(self, category: DecisionCategory) -> DeltaEntityType:
        """Map decision category to delta entity type."""
        mapping = {
            DecisionCategory.DEMAND_FORECAST: DeltaEntityType.DEMAND_PLAN,
            DecisionCategory.SUPPLY_PLAN: DeltaEntityType.SUPPLY_PLAN,
            DecisionCategory.INVENTORY_TARGET: DeltaEntityType.INVENTORY,
            DecisionCategory.SAFETY_STOCK: DeltaEntityType.SAFETY_STOCK,
            DecisionCategory.SOURCING: DeltaEntityType.SUPPLY_PLAN,
            DecisionCategory.PRODUCTION: DeltaEntityType.SUPPLY_PLAN,
            DecisionCategory.DISTRIBUTION: DeltaEntityType.SUPPLY_PLAN,
            DecisionCategory.PRICING: DeltaEntityType.CONFIG,
            DecisionCategory.CAPACITY: DeltaEntityType.CONFIG,
            DecisionCategory.LEAD_TIME: DeltaEntityType.CONFIG,
            DecisionCategory.ORDER: DeltaEntityType.SUPPLY_PLAN,
        }
        return mapping.get(category, DeltaEntityType.CONFIG)

    def _build_entity_key(self, decision: PlanningDecision) -> str:
        """Build entity key from decision scope."""
        parts = []
        if decision.product_id:
            parts.append(decision.product_id)
        if decision.site_id:
            parts.append(decision.site_id)
        if decision.period_start:
            parts.append(decision.period_start.strftime("%Y%m%d"))

        return "|".join(parts) if parts else str(decision.id)
