"""
Planning Decisions API Endpoints

CRUD operations and management for planning decisions.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.models.planning_cycle import PlanningCycle, CycleStatus
from app.models.planning_decision import (
    PlanningDecision, DecisionHistory, DecisionComment,
    DecisionAction, DecisionCategory, DecisionStatus,
    DECISION_REASON_CODES, DEFAULT_APPROVAL_THRESHOLDS
)
from app.models.user import User
from app.schemas.planning_decision import (
    PlanningDecisionCreate, PlanningDecisionUpdate, PlanningDecisionResponse,
    PlanningDecisionListResponse,
    DecisionHistoryResponse, DecisionHistoryListResponse,
    DecisionCommentCreate, DecisionCommentResponse,
    DecisionApprovalRequest, DecisionRejectRequest, DecisionRevertRequest,
    DecisionStatsResponse, ReasonCodeResponse, ReasonCodesResponse,
    ApprovalThresholdResponse, ApprovalThresholdsResponse,
)
from app.services.decision_service import DecisionService

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Planning Decisions
# ============================================================================

@router.get("", response_model=PlanningDecisionListResponse)
def list_decisions(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    cycle_id: Optional[int] = None,
    category: Optional[DecisionCategory] = None,
    status_filter: Optional[DecisionStatus] = Query(None, alias="status"),
    action: Optional[DecisionAction] = None,
    created_by: Optional[int] = None,
):
    """List planning decisions for the user's customer."""
    query = db.query(PlanningDecision).join(PlanningCycle).filter(
        PlanningCycle.tenant_id == current_user.tenant_id
    )

    if cycle_id:
        query = query.filter(PlanningDecision.cycle_id == cycle_id)
    if category:
        query = query.filter(PlanningDecision.category == category)
    if status_filter:
        query = query.filter(PlanningDecision.status == status_filter)
    if action:
        query = query.filter(PlanningDecision.action == action)
    if created_by:
        query = query.filter(PlanningDecision.created_by_id == created_by)

    total = query.count()
    items = query.order_by(PlanningDecision.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return PlanningDecisionListResponse(
        items=[PlanningDecisionResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("", response_model=PlanningDecisionResponse, status_code=status.HTTP_201_CREATED)
def create_decision(
    decision_in: PlanningDecisionCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Create a new planning decision."""
    # Verify cycle access
    cycle = db.query(PlanningCycle).filter(
        PlanningCycle.id == decision_in.cycle_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning cycle not found"
        )

    if cycle.status in [CycleStatus.CLOSED, CycleStatus.ARCHIVED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create decisions for closed or archived cycles"
        )

    # Validate reason code
    if decision_in.reason_code not in DECISION_REASON_CODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid reason code. Valid codes: {list(DECISION_REASON_CODES.keys())}"
        )

    service = DecisionService(db)
    decision = service.record_decision(
        cycle_id=decision_in.cycle_id,
        category=decision_in.category,
        action=decision_in.action,
        entity_type=decision_in.entity_type,
        entity_id=decision_in.entity_id,
        original_value=decision_in.original_value,
        decided_value=decision_in.decided_value,
        reason_code=decision_in.reason_code,
        reason_text=decision_in.reason_text,
        created_by_id=current_user.id,
        snapshot_id=decision_in.snapshot_id,
        recommendation_id=decision_in.recommendation_id,
        priority=decision_in.priority,
        effective_date=decision_in.effective_date,
        expiry_date=decision_in.expiry_date
    )

    return PlanningDecisionResponse.model_validate(decision)


@router.get("/{decision_id}", response_model=PlanningDecisionResponse)
def get_decision(
    decision_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get a specific planning decision."""
    decision = db.query(PlanningDecision).join(PlanningCycle).filter(
        PlanningDecision.id == decision_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning decision not found"
        )

    return PlanningDecisionResponse.model_validate(decision)


@router.put("/{decision_id}", response_model=PlanningDecisionResponse)
def update_decision(
    decision_id: int,
    decision_in: PlanningDecisionUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Update a planning decision (only draft decisions can be updated)."""
    decision = db.query(PlanningDecision).join(PlanningCycle).filter(
        PlanningDecision.id == decision_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning decision not found"
        )

    if decision.status != DecisionStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft decisions can be updated"
        )

    update_data = decision_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(decision, field, value)

    db.commit()
    db.refresh(decision)

    return PlanningDecisionResponse.model_validate(decision)


@router.delete("/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_decision(
    decision_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Delete a planning decision (only draft decisions can be deleted)."""
    decision = db.query(PlanningDecision).join(PlanningCycle).filter(
        PlanningDecision.id == decision_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning decision not found"
        )

    if decision.status != DecisionStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft decisions can be deleted"
        )

    db.delete(decision)
    db.commit()


# ============================================================================
# Decision Actions
# ============================================================================

@router.post("/{decision_id}/submit", response_model=PlanningDecisionResponse)
def submit_decision(
    decision_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Submit a draft decision for approval."""
    decision = db.query(PlanningDecision).join(PlanningCycle).filter(
        PlanningDecision.id == decision_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning decision not found"
        )

    if decision.status != DecisionStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft decisions can be submitted"
        )

    service = DecisionService(db)
    # Check if approval is needed based on thresholds
    if decision.approval_required:
        decision.status = DecisionStatus.PENDING_APPROVAL
    else:
        decision.status = DecisionStatus.APPROVED

    # Record history
    history = DecisionHistory(
        decision_id=decision.id,
        action="submit",
        old_status=DecisionStatus.DRAFT,
        new_status=decision.status,
        changed_by_id=current_user.id
    )
    db.add(history)
    db.commit()
    db.refresh(decision)

    return PlanningDecisionResponse.model_validate(decision)


@router.post("/{decision_id}/approve", response_model=PlanningDecisionResponse)
def approve_decision(
    decision_id: int,
    approval: DecisionApprovalRequest = None,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Approve a pending decision."""
    decision = db.query(PlanningDecision).join(PlanningCycle).filter(
        PlanningDecision.id == decision_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning decision not found"
        )

    if decision.status != DecisionStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decision is not pending approval"
        )

    service = DecisionService(db)
    comment = approval.comment if approval else None
    decision = service.approve_decision(decision_id, current_user.id, comment)

    return PlanningDecisionResponse.model_validate(decision)


@router.post("/{decision_id}/reject", response_model=PlanningDecisionResponse)
def reject_decision(
    decision_id: int,
    rejection: DecisionRejectRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Reject a pending decision."""
    decision = db.query(PlanningDecision).join(PlanningCycle).filter(
        PlanningDecision.id == decision_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning decision not found"
        )

    if decision.status != DecisionStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decision is not pending approval"
        )

    service = DecisionService(db)
    decision = service.reject_decision(decision_id, current_user.id, rejection.reason)

    return PlanningDecisionResponse.model_validate(decision)


@router.post("/{decision_id}/apply", response_model=PlanningDecisionResponse)
def apply_decision(
    decision_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Apply an approved decision to create a new snapshot."""
    decision = db.query(PlanningDecision).join(PlanningCycle).filter(
        PlanningDecision.id == decision_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning decision not found"
        )

    if decision.status != DecisionStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decision must be approved before applying"
        )

    service = DecisionService(db)
    try:
        decision = service.apply_decision(decision_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    return PlanningDecisionResponse.model_validate(decision)


@router.post("/{decision_id}/revert", response_model=PlanningDecisionResponse)
def revert_decision(
    decision_id: int,
    revert_request: DecisionRevertRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Revert an applied decision."""
    decision = db.query(PlanningDecision).join(PlanningCycle).filter(
        PlanningDecision.id == decision_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning decision not found"
        )

    if decision.status != DecisionStatus.APPLIED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only applied decisions can be reverted"
        )

    service = DecisionService(db)
    try:
        decision = service.revert_decision(decision_id, current_user.id, revert_request.reason)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    return PlanningDecisionResponse.model_validate(decision)


# ============================================================================
# Decision Comments
# ============================================================================

@router.get("/{decision_id}/comments", response_model=List[DecisionCommentResponse])
def list_decision_comments(
    decision_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """List comments for a decision."""
    decision = db.query(PlanningDecision).join(PlanningCycle).filter(
        PlanningDecision.id == decision_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning decision not found"
        )

    comments = db.query(DecisionComment).filter(
        DecisionComment.decision_id == decision_id
    ).order_by(DecisionComment.created_at).all()

    return [DecisionCommentResponse.model_validate(c) for c in comments]


@router.post("/{decision_id}/comments", response_model=DecisionCommentResponse, status_code=status.HTTP_201_CREATED)
def add_decision_comment(
    decision_id: int,
    comment_in: DecisionCommentCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Add a comment to a decision."""
    decision = db.query(PlanningDecision).join(PlanningCycle).filter(
        PlanningDecision.id == decision_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning decision not found"
        )

    service = DecisionService(db)
    comment = service.add_comment(
        decision_id=decision_id,
        content=comment_in.content,
        created_by_id=current_user.id,
        is_internal=comment_in.is_internal
    )

    return DecisionCommentResponse.model_validate(comment)


# ============================================================================
# Decision History
# ============================================================================

@router.get("/{decision_id}/history", response_model=DecisionHistoryListResponse)
def get_decision_history(
    decision_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get the history of a decision."""
    decision = db.query(PlanningDecision).join(PlanningCycle).filter(
        PlanningDecision.id == decision_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning decision not found"
        )

    history = db.query(DecisionHistory).filter(
        DecisionHistory.decision_id == decision_id
    ).order_by(DecisionHistory.created_at).all()

    return DecisionHistoryListResponse(
        items=[DecisionHistoryResponse.model_validate(h) for h in history],
        total=len(history)
    )


# ============================================================================
# Decision Statistics
# ============================================================================

@router.get("/cycle/{cycle_id}/stats", response_model=DecisionStatsResponse)
def get_cycle_decision_stats(
    cycle_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get decision statistics for a cycle."""
    # Verify cycle access
    cycle = db.query(PlanningCycle).filter(
        PlanningCycle.id == cycle_id,
        PlanningCycle.tenant_id == current_user.tenant_id
    ).first()

    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning cycle not found"
        )

    service = DecisionService(db)
    stats = service.get_decision_stats(cycle_id)

    return DecisionStatsResponse(**stats)


# ============================================================================
# Reference Data
# ============================================================================

@router.get("/reference/reason-codes", response_model=ReasonCodesResponse)
def get_reason_codes(
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get available reason codes."""
    reason_codes = [
        ReasonCodeResponse(code=code, description=desc)
        for code, desc in DECISION_REASON_CODES.items()
    ]
    return ReasonCodesResponse(reason_codes=reason_codes)


@router.get("/reference/approval-thresholds", response_model=ApprovalThresholdsResponse)
def get_approval_thresholds(
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get default approval thresholds."""
    thresholds = [
        ApprovalThresholdResponse(
            category=category,
            amount_threshold=config["amount_threshold"],
            percentage_threshold=config["percentage_threshold"],
            requires_approval=True
        )
        for category, config in DEFAULT_APPROVAL_THRESHOLDS.items()
    ]
    return ApprovalThresholdsResponse(thresholds=thresholds)
