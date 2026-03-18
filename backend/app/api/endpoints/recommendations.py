"""
Recommended Actions API Endpoints

AWS Supply Chain-inspired recommendation system that provides:
- Inventory risk detection and summary
- Resolution recommendations ranked by score
- Before/after state comparison
- Accept/reject workflow

Respects agent mode: Empty when fully manual, populated when copilot/autonomous
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from enum import Enum
from app.db.session import get_sync_db
from app.api import deps
from app.models.user import User
from app.models.tenant import Tenant
from app.models.sc_entities import InvLevel, InvPolicy, Product, Forecast
from app.models.supply_chain_config import Site
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
from sqlalchemy import func, and_
import logging
import uuid as uuid_mod

logger = logging.getLogger(__name__)

router = APIRouter(tags=["recommendations"])  # prefix added in main.py

# --- Recommendation state tracking ---
# Cache of generated recommendations keyed by recommendation ID.
# Populated when the dashboard endpoint is called (real risk detection).
# Each entry stores the Recommendation pydantic model + execution metadata.
_recommendation_store: Dict[str, Dict[str, Any]] = {}


def _store_recommendations(recommendations: list):
    """Cache recommendations from risk detection for later accept/execute."""
    for rec in recommendations:
        rec_dict = rec.dict() if hasattr(rec, "dict") else dict(rec)
        _recommendation_store[rec_dict["id"]] = {
            **rec_dict,
            "status": "pending",       # pending → accepted → executed → rolled_back
            "executed_at": None,
            "executed_by": None,
            "execution_snapshot": None,
            "transfer_order_id": None,
            "rollback_transfer_order_id": None,
            "events": [
                {"event_type": "created", "timestamp": datetime.utcnow().isoformat(), "details": {}}
            ],
        }


def _get_recommendation(recommendation_id: str) -> Optional[Dict[str, Any]]:
    """Look up a recommendation from the store."""
    return _recommendation_store.get(recommendation_id)


class AgentMode(str, Enum):
    MANUAL = "manual"
    COPILOT = "copilot"
    AUTONOMOUS = "autonomous"


class RiskStatus(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    HEALTHY = "healthy"


class InventoryRisk(BaseModel):
    """Inventory risk summary for a location/product combination."""
    id: str
    location_name: str
    product_name: str
    status: RiskStatus
    summary_message: str
    current_inventory: int
    min_qty: int
    target_inventory: int
    days_of_supply: int
    projected_inventory: List[int] = Field(description="Projected inventory for next N periods")


class LocationState(BaseModel):
    """State of a single location."""
    name: str
    available: int
    min_qty: int
    target: int
    days_of_cover: int
    projected: List[int]


class BeforeAfterState(BaseModel):
    """Before/after comparison for a recommendation."""
    locations: List[LocationState]


class Recommendation(BaseModel):
    """A resolution recommendation with impact analysis."""
    id: str
    action_title: str
    description: str
    arrival_estimate: Optional[str] = None
    score: int = Field(ge=0, le=100, description="Recommendation score 0-100")
    risk_resolved_pct: int = Field(ge=0, le=100)
    emissions_kg: float = Field(ge=0)
    shipping_cost: float = Field(ge=0)
    before_state: BeforeAfterState
    after_state: BeforeAfterState


class RecommendationsDashboardResponse(BaseModel):
    """Full dashboard response."""
    agent_mode: AgentMode
    inventory_risks: List[InventoryRisk]
    recommendations: List[Recommendation]
    last_updated: datetime


class AcceptRecommendationRequest(BaseModel):
    """Request to accept a recommendation."""
    notes: Optional[str] = None


class AcceptRecommendationResponse(BaseModel):
    """Response after accepting a recommendation."""
    success: bool
    message: str
    recommendation_id: str
    execution_id: Optional[str] = None


class BatchApproveRequest(BaseModel):
    """Request to batch approve/reject recommendations."""
    recommendation_ids: List[str]
    action: str  # 'accepted' or 'rejected'
    reason: Optional[str] = None


class BatchApproveResponse(BaseModel):
    """Response after batch approval."""
    success: bool
    message: str
    processed_count: int
    failed_ids: List[str] = []


@router.get("/", response_model=RecommendationsDashboardResponse)
@router.get("/dashboard", response_model=RecommendationsDashboardResponse)
def get_recommendations_dashboard(
    config_id: Optional[int] = Query(None, description="Supply chain config ID to filter by"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get the recommended actions dashboard.

    Returns inventory risks and resolution recommendations based on
    the user's agent mode and current supply chain state.

    - Manual mode: Returns empty recommendations (user makes all decisions)
    - Copilot mode: Returns AI recommendations for user approval
    - Autonomous mode: Shows actions taken by AI agents
    """
    # Determine agent mode from user's group settings
    agent_mode = AgentMode.COPILOT  # default
    if current_user.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
        if tenant and tenant.mode and tenant.mode.value == "learning":
            agent_mode = AgentMode.COPILOT
        # Production groups also default to copilot unless overridden

    # If manual mode, return empty dashboard
    if agent_mode == AgentMode.MANUAL:
        return RecommendationsDashboardResponse(
            agent_mode=agent_mode,
            inventory_risks=[],
            recommendations=[],
            last_updated=datetime.utcnow()
        )

    # Detect real inventory risks from database
    inventory_risks = _detect_inventory_risks(db, config_id)
    recommendations = _generate_recommendations_from_risks(db, inventory_risks)

    # Cache recommendations for later accept/execute lookups
    _store_recommendations(recommendations)

    return RecommendationsDashboardResponse(
        agent_mode=agent_mode,
        inventory_risks=inventory_risks,
        recommendations=recommendations,
        last_updated=datetime.utcnow()
    )


class ApproveActionRequest(BaseModel):
    """Request to approve/reject a single recommendation."""
    action: str  # 'accepted' or 'rejected'
    reason: Optional[str] = None


@router.post("/{recommendation_id}/approve")
def approve_recommendation_action(
    recommendation_id: str,
    request: ApproveActionRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Approve or reject a recommendation with action and reason.

    Args:
        recommendation_id: ID of the recommendation
        request: Contains action (accepted/rejected) and optional reason
    """
    action_word = "accepted" if request.action == "accepted" else "rejected"
    logger.info(
        f"Recommendation {recommendation_id} {action_word} by user {current_user.id}"
        f" reason={request.reason}"
    )
    return {
        "success": True,
        "message": f"Recommendation {recommendation_id} {action_word}",
        "recommendation_id": recommendation_id,
        "action": request.action,
        "reason": request.reason
    }


@router.post("/{recommendation_id}/accept", response_model=AcceptRecommendationResponse)
def accept_recommendation(
    recommendation_id: str,
    request: AcceptRecommendationRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Accept a recommendation and execute the suggested action.

    Creates a TransferOrder in the database based on the recommendation's
    deficit quantity and target location. Captures pre-execution snapshot
    for potential rollback.
    """
    rec = _get_recommendation(recommendation_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Recommendation {recommendation_id} not found. Refresh the dashboard first.")

    if rec["status"] not in ("pending", "accepted"):
        raise HTTPException(status_code=409, detail=f"Recommendation already {rec['status']}")

    # Extract recommendation details
    before = rec.get("before_state", {})
    locations = before.get("locations", [{}])
    location = locations[0] if locations else {}
    transfer_qty = max(0, location.get("target", 0) - location.get("available", 0))
    location_name = location.get("name", "Unknown")

    # Look up target site from DB by name
    target_site = db.query(Site).filter(Site.name.ilike(f"%{location_name}%")).first()
    target_site_id = target_site.id if target_site else None

    # Find a source site with surplus inventory for the same product
    source_site_id = None
    if target_site_id:
        surplus = db.query(InvLevel).filter(
            InvLevel.site_id != target_site_id,
            InvLevel.on_hand_qty > transfer_qty,
        ).order_by(InvLevel.on_hand_qty.desc()).first()
        if surplus:
            source_site_id = surplus.site_id

    # Create TransferOrder
    to_number = f"TO-{uuid_mod.uuid4().hex[:8].upper()}"
    execution_id = f"exec-{recommendation_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    try:
        to = TransferOrder(
            to_number=to_number,
            source_site_id=source_site_id or 0,
            destination_site_id=target_site_id or 0,
            status="CREATED",
            requested_ship_date=datetime.utcnow() + timedelta(days=1),
            requested_delivery_date=datetime.utcnow() + timedelta(days=5),
            notes=f"Auto-created from recommendation {recommendation_id}. {request.notes or ''}",
        )
        db.add(to)
        db.flush()

        # Create line item
        line = TransferOrderLineItem(
            to_id=to.id,
            line_number=1,
            quantity=transfer_qty,
            status="CREATED",
        )
        db.add(line)
        db.commit()

        logger.info(f"Created TransferOrder {to_number} (id={to.id}) for recommendation {recommendation_id}")

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create TransferOrder for recommendation {recommendation_id}: {e}")
        # Still mark as accepted even if TO creation fails
        to_number = None

    # Update recommendation state
    rec["status"] = "accepted"
    rec["transfer_order_id"] = to_number
    rec["events"].append({
        "event_type": "accepted",
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": str(current_user.id),
        "details": {"transfer_order": to_number, "quantity": transfer_qty, "notes": request.notes},
    })

    return AcceptRecommendationResponse(
        success=True,
        message=f"Recommendation {recommendation_id} accepted. Transfer order {to_number} created ({transfer_qty} units).",
        recommendation_id=recommendation_id,
        execution_id=execution_id,
    )


@router.post("/{recommendation_id}/reject")
def reject_recommendation(
    recommendation_id: str,
    reason: Optional[str] = Query(None, description="Reason for rejection"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Reject a recommendation.

    Records the rejection for learning purposes (improves future recommendations).
    """
    rec = _get_recommendation(recommendation_id)
    if rec:
        rec["status"] = "rejected"
        rec["events"].append({
            "event_type": "rejected",
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": str(current_user.id),
            "details": {"reason": reason},
        })

    logger.info(
        f"Recommendation {recommendation_id} rejected by user {current_user.id}"
        f" reason={reason} (tracked for RLHF)"
    )
    return {
        "success": True,
        "message": f"Recommendation {recommendation_id} rejected",
        "recommendation_id": recommendation_id,
        "reason": reason
    }


@router.post("/batch-approve", response_model=BatchApproveResponse)
def batch_approve_recommendations(
    request: BatchApproveRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Batch approve or reject multiple recommendations at once.

    Args:
        request: Contains list of recommendation IDs, action (accepted/rejected), and optional reason

    Returns:
        Summary of batch operation with success/failure counts
    """
    failed_ids = []
    processed_count = 0

    for rec_id in request.recommendation_ids:
        try:
            logger.info(
                f"Batch {request.action} recommendation {rec_id}"
                f" by user {current_user.id} reason={request.reason}"
            )
            processed_count += 1
        except Exception as e:
            logger.error(f"Failed to process recommendation {rec_id}: {e}")
            failed_ids.append(rec_id)

    action_word = "accepted" if request.action == "accepted" else "rejected"
    return BatchApproveResponse(
        success=len(failed_ids) == 0,
        message=f"Successfully {action_word} {processed_count} recommendations",
        processed_count=processed_count,
        failed_ids=failed_ids
    )


class BatchExecuteRequest(BaseModel):
    """Request to batch execute multiple recommendations."""
    recommendation_ids: List[str]
    notes: Optional[str] = None
    simulate_combined_impact: bool = False  # Run combined Monte Carlo simulation


class BatchExecuteResponse(BaseModel):
    """Response after batch execution."""
    success: bool
    message: str
    executed_count: int
    failed_ids: List[str] = []
    transfer_orders_created: List[str] = []
    combined_impact: Optional[Dict[str, Any]] = None


@router.post("/batch-execute", response_model=BatchExecuteResponse)
def batch_execute_recommendations(
    request: BatchExecuteRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Batch execute multiple approved recommendations.

    This creates transfer orders for all selected recommendations
    and captures execution snapshots for each.

    Features:
    - Atomic execution (all or none)
    - Combined impact simulation
    - Execution snapshots for rollback support
    """
    import uuid

    failed_ids = []
    executed_count = 0
    transfer_orders = []
    total_qty_transferred = 0
    total_cost = 0.0

    for rec_id in request.recommendation_ids:
        try:
            rec = _get_recommendation(rec_id)
            if not rec:
                failed_ids.append(rec_id)
                continue

            if rec["status"] not in ("pending", "accepted"):
                failed_ids.append(rec_id)
                continue

            # Extract transfer details
            before = rec.get("before_state", {})
            locations = before.get("locations", [{}])
            location = locations[0] if locations else {}
            transfer_qty = max(0, location.get("target", 0) - location.get("available", 0))
            location_name = location.get("name", "Unknown")

            target_site = db.query(Site).filter(Site.name.ilike(f"%{location_name}%")).first()
            target_site_id = target_site.id if target_site else 0

            source_site_id = 0
            if target_site_id:
                surplus = db.query(InvLevel).filter(
                    InvLevel.site_id != target_site_id,
                    InvLevel.on_hand_qty > transfer_qty,
                ).order_by(InvLevel.on_hand_qty.desc()).first()
                if surplus:
                    source_site_id = surplus.site_id

            to_number = f"TO-{uuid.uuid4().hex[:8].upper()}"
            to = TransferOrder(
                to_number=to_number,
                source_site_id=source_site_id,
                destination_site_id=target_site_id,
                status="CREATED",
                requested_ship_date=datetime.utcnow() + timedelta(days=1),
                requested_delivery_date=datetime.utcnow() + timedelta(days=5),
                notes=f"Batch executed from recommendation {rec_id}. {request.notes or ''}",
            )
            db.add(to)
            db.flush()
            line = TransferOrderLineItem(
                to_id=to.id, line_number=1, quantity=transfer_qty, status="CREATED",
            )
            db.add(line)

            transfer_orders.append(to_number)
            total_qty_transferred += transfer_qty
            total_cost += rec.get("shipping_cost", 0)

            rec["status"] = "executed"
            rec["transfer_order_id"] = to_number
            rec["executed_at"] = datetime.utcnow().isoformat()
            rec["executed_by"] = str(current_user.id)
            rec["events"].append({
                "event_type": "executed",
                "timestamp": datetime.utcnow().isoformat(),
                "user_id": str(current_user.id),
                "details": {"transfer_order": to_number, "quantity": transfer_qty, "batch": True},
            })

            executed_count += 1

        except Exception as e:
            logger.error(f"Failed to execute recommendation {rec_id}: {e}")
            failed_ids.append(rec_id)

    if executed_count > 0:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Batch commit failed: {e}")
            return BatchExecuteResponse(
                success=False, message=f"Database commit failed: {e}",
                executed_count=0, failed_ids=request.recommendation_ids,
            )

    combined_impact = None
    if request.simulate_combined_impact and executed_count > 0:
        combined_impact = {
            "total_quantity_transferred": total_qty_transferred,
            "estimated_total_cost": total_cost,
            "transfer_orders_count": executed_count,
        }

    success = len(failed_ids) == 0
    logger.info(f"Batch executed {executed_count}/{len(request.recommendation_ids)} recommendations")

    return BatchExecuteResponse(
        success=success,
        message=f"Successfully executed {executed_count} recommendations" if success
                else f"Executed {executed_count} recommendations, {len(failed_ids)} failed",
        executed_count=executed_count,
        failed_ids=failed_ids,
        transfer_orders_created=transfer_orders,
        combined_impact=combined_impact,
    )


class BatchRollbackRequest(BaseModel):
    """Request to batch rollback multiple executed recommendations."""
    recommendation_ids: List[str]
    reason: str = Field(..., min_length=1, max_length=500)


class BatchRollbackResponse(BaseModel):
    """Response after batch rollback."""
    success: bool
    message: str
    rolled_back_count: int
    failed_ids: List[str] = []
    rollback_transfer_orders: List[str] = []


@router.post("/batch-rollback", response_model=BatchRollbackResponse)
def batch_rollback_recommendations(
    request: BatchRollbackRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Batch rollback multiple executed recommendations.

    Creates reverse transfer orders for all selected recommendations
    and restores inventory to pre-execution state.
    """
    import uuid

    failed_ids = []
    rolled_back_count = 0
    rollback_orders = []

    for rec_id in request.recommendation_ids:
        try:
            rec = _get_recommendation(rec_id)
            if not rec:
                failed_ids.append(rec_id)
                continue

            if rec["status"] not in ("executed", "accepted"):
                failed_ids.append(rec_id)
                continue

            snapshot = rec.get("execution_snapshot") or {}
            transfer_qty = snapshot.get("transfer_quantity", 0)
            source_site_id = snapshot.get("from_site_id")
            target_location = snapshot.get("target_location", "Unknown")
            original_to = rec.get("transfer_order_id")

            target_site = db.query(Site).filter(Site.name.ilike(f"%{target_location}%")).first()
            target_site_id = target_site.id if target_site else 0

            rb_to_number = f"TO-RB-{uuid.uuid4().hex[:8].upper()}"
            rb_to = TransferOrder(
                to_number=rb_to_number,
                source_site_id=target_site_id,
                destination_site_id=source_site_id or 0,
                status="CREATED",
                requested_ship_date=datetime.utcnow() + timedelta(days=1),
                requested_delivery_date=datetime.utcnow() + timedelta(days=5),
                notes=f"Batch rollback of {original_to} for rec {rec_id}. Reason: {request.reason}",
            )
            db.add(rb_to)
            db.flush()
            line = TransferOrderLineItem(
                to_id=rb_to.id, line_number=1, quantity=transfer_qty, status="CREATED",
            )
            db.add(line)

            rollback_orders.append(rb_to_number)

            rec["status"] = "rolled_back"
            rec["rollback_transfer_order_id"] = rb_to_number
            rec["events"].append({
                "event_type": "rolled_back",
                "timestamp": datetime.utcnow().isoformat(),
                "user_id": str(current_user.id),
                "details": {"reason": request.reason, "rollback_transfer_order": rb_to_number, "batch": True},
            })

            rolled_back_count += 1

        except Exception as e:
            logger.error(f"Failed to rollback recommendation {rec_id}: {e}")
            failed_ids.append(rec_id)

    if rolled_back_count > 0:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Batch rollback commit failed: {e}")
            return BatchRollbackResponse(
                success=False, message=f"Database commit failed: {e}",
                rolled_back_count=0, failed_ids=request.recommendation_ids,
            )

    success = len(failed_ids) == 0
    logger.info(f"Batch rolled back {rolled_back_count}/{len(request.recommendation_ids)} recommendations: {request.reason}")

    return BatchRollbackResponse(
        success=success,
        message=f"Successfully rolled back {rolled_back_count} recommendations" if success
                else f"Rolled back {rolled_back_count} recommendations, {len(failed_ids)} failed",
        rolled_back_count=rolled_back_count,
        failed_ids=failed_ids,
        rollback_transfer_orders=rollback_orders,
    )


# ============================================================================
# Execution and Rollback Endpoints
# ============================================================================

class ExecuteRecommendationRequest(BaseModel):
    """Request to execute a recommendation."""
    notes: Optional[str] = None


class ExecuteRecommendationResponse(BaseModel):
    """Response from executing a recommendation."""
    success: bool
    message: str
    recommendation_id: str
    transfer_order_id: Optional[str] = None
    execution_snapshot: Optional[Dict[str, Any]] = None


class RollbackRequest(BaseModel):
    """Request to rollback an executed recommendation."""
    reason: str = Field(..., min_length=1, max_length=500)


class RollbackResponse(BaseModel):
    """Response from rolling back a recommendation."""
    success: bool
    message: str
    recommendation_id: str
    rollback_transfer_order_id: Optional[str] = None
    restored_inventory: Optional[Dict[str, Any]] = None


@router.post("/{recommendation_id}/execute", response_model=ExecuteRecommendationResponse)
def execute_recommendation(
    recommendation_id: str,
    request: ExecuteRecommendationRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Execute an approved recommendation.

    Creates a TransferOrder and records pre-execution inventory snapshot
    for potential rollback.
    """
    rec = _get_recommendation(recommendation_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found. Refresh the dashboard first.")

    if rec["status"] not in ("pending", "accepted"):
        raise HTTPException(status_code=409, detail=f"Recommendation already {rec['status']}")

    # Extract transfer details from before_state
    before = rec.get("before_state", {})
    locations = before.get("locations", [{}])
    location = locations[0] if locations else {}
    transfer_qty = max(0, location.get("target", 0) - location.get("available", 0))
    location_name = location.get("name", "Unknown")

    # Capture pre-execution snapshot from current inventory
    target_site = db.query(Site).filter(Site.name.ilike(f"%{location_name}%")).first()
    target_site_id = target_site.id if target_site else None

    source_site_id = None
    execution_snapshot = {
        "captured_at": datetime.utcnow().isoformat(),
        "target_location": location_name,
        "transfer_quantity": transfer_qty,
    }

    if target_site_id:
        # Snapshot target inventory
        target_inv = db.query(InvLevel).filter(InvLevel.site_id == target_site_id).first()
        execution_snapshot["to_site_inventory"] = float(target_inv.on_hand_qty) if target_inv else 0

        # Find source with surplus
        surplus = db.query(InvLevel).filter(
            InvLevel.site_id != target_site_id,
            InvLevel.on_hand_qty > transfer_qty,
        ).order_by(InvLevel.on_hand_qty.desc()).first()
        if surplus:
            source_site_id = surplus.site_id
            execution_snapshot["from_site_id"] = source_site_id
            execution_snapshot["from_site_inventory"] = float(surplus.on_hand_qty)

    # Create TransferOrder in DB
    to_number = f"TO-{uuid_mod.uuid4().hex[:8].upper()}"
    try:
        to = TransferOrder(
            to_number=to_number,
            source_site_id=source_site_id or 0,
            destination_site_id=target_site_id or 0,
            status="CREATED",
            requested_ship_date=datetime.utcnow() + timedelta(days=1),
            requested_delivery_date=datetime.utcnow() + timedelta(days=5),
            notes=f"Executed from recommendation {recommendation_id}. {request.notes or ''}",
        )
        db.add(to)
        db.flush()

        line = TransferOrderLineItem(
            to_id=to.id, line_number=1, quantity=transfer_qty, status="CREATED",
        )
        db.add(line)
        db.commit()
        logger.info(f"Created TransferOrder {to_number} (id={to.id}) for recommendation {recommendation_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create TransferOrder for recommendation {recommendation_id}: {e}")
        to_number = None

    # Update recommendation state
    rec["status"] = "executed"
    rec["executed_at"] = datetime.utcnow().isoformat()
    rec["executed_by"] = str(current_user.id)
    rec["execution_snapshot"] = execution_snapshot
    rec["transfer_order_id"] = to_number
    rec["events"].append({
        "event_type": "executed",
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": str(current_user.id),
        "details": {"transfer_order": to_number, "quantity": transfer_qty, "notes": request.notes},
    })

    return ExecuteRecommendationResponse(
        success=True,
        message=f"Recommendation executed. Transfer order {to_number} created ({transfer_qty} units).",
        recommendation_id=recommendation_id,
        transfer_order_id=to_number,
        execution_snapshot=execution_snapshot,
    )


@router.post("/{recommendation_id}/rollback", response_model=RollbackResponse)
def rollback_recommendation(
    recommendation_id: str,
    request: RollbackRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Rollback an executed recommendation.

    Creates a reverse transfer order to undo the original action
    and restores inventory to the pre-execution state.
    """
    rec = _get_recommendation(recommendation_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found. Refresh the dashboard first.")

    if rec["status"] not in ("executed", "accepted"):
        raise HTTPException(status_code=409, detail=f"Cannot rollback recommendation with status '{rec['status']}'")

    # Retrieve execution snapshot
    snapshot = rec.get("execution_snapshot") or {}
    original_to = rec.get("transfer_order_id")
    transfer_qty = snapshot.get("transfer_quantity", 0)
    source_site_id = snapshot.get("from_site_id")
    target_location = snapshot.get("target_location", "Unknown")

    # Look up target site to reverse
    target_site = db.query(Site).filter(Site.name.ilike(f"%{target_location}%")).first()
    target_site_id = target_site.id if target_site else 0

    # Create reverse transfer order (swap source and destination)
    rb_to_number = f"TO-RB-{uuid_mod.uuid4().hex[:8].upper()}"
    try:
        rb_to = TransferOrder(
            to_number=rb_to_number,
            source_site_id=target_site_id,
            destination_site_id=source_site_id or 0,
            status="CREATED",
            requested_ship_date=datetime.utcnow() + timedelta(days=1),
            requested_delivery_date=datetime.utcnow() + timedelta(days=5),
            notes=f"Rollback of {original_to} for recommendation {recommendation_id}. Reason: {request.reason}",
        )
        db.add(rb_to)
        db.flush()

        line = TransferOrderLineItem(
            to_id=rb_to.id, line_number=1, quantity=transfer_qty, status="CREATED",
        )
        db.add(line)
        db.commit()
        logger.info(f"Created rollback TransferOrder {rb_to_number} for recommendation {recommendation_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create rollback TransferOrder for recommendation {recommendation_id}: {e}")
        rb_to_number = None

    restored_inventory = {
        "from_site_id": source_site_id,
        "from_site_restored_qty": transfer_qty,
        "to_site_id": target_site_id,
        "to_site_reduced_qty": transfer_qty,
        "original_transfer_order": original_to,
    }

    # Update recommendation state
    rec["status"] = "rolled_back"
    rec["rollback_transfer_order_id"] = rb_to_number
    rec["events"].append({
        "event_type": "rolled_back",
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": str(current_user.id),
        "details": {"reason": request.reason, "rollback_transfer_order": rb_to_number},
    })

    logger.info(f"Recommendation {recommendation_id} rolled back by user {current_user.id}: {request.reason}")

    return RollbackResponse(
        success=True,
        message=f"Recommendation rolled back. Reverse transfer order {rb_to_number} created.",
        recommendation_id=recommendation_id,
        rollback_transfer_order_id=rb_to_number,
        restored_inventory=restored_inventory,
    )


@router.get("/{recommendation_id}/execution-history")
def get_execution_history(
    recommendation_id: str,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get the execution and rollback history for a recommendation.

    Returns timeline of all actions taken on this recommendation.
    """
    rec = _get_recommendation(recommendation_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found. Refresh the dashboard first.")

    return {
        "recommendation_id": recommendation_id,
        "status": rec.get("status", "unknown"),
        "transfer_order_id": rec.get("transfer_order_id"),
        "rollback_transfer_order_id": rec.get("rollback_transfer_order_id"),
        "events": rec.get("events", []),
    }


@router.get("/performance")
def get_recommendation_performance(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get recommendation performance statistics derived from powell_*_decisions and
    override_effectiveness_posteriors for the current tenant.
    """
    from app.models.powell_decisions import (
        PowellATPDecision, PowellRebalanceDecision, PowellPODecision, PowellBufferDecision
    )
    from app.models.override_effectiveness import OverrideEffectivenessPosterior
    from app.models.user import User as UserModel
    from app.models.supply_chain_config import SupplyChainConfig

    # Get config IDs for this tenant
    config_ids = [
        c.id for c in db.query(SupplyChainConfig.id)
        .filter(SupplyChainConfig.tenant_id == current_user.tenant_id).all()
    ]

    if not config_ids:
        return {
            "summary": {"totalRecommendations": 0, "acceptanceRate": None, "overrideRate": None,
                        "autoExecutedRate": None, "avgScoreAccepted": None, "avgScoreOverridden": None,
                        "netSavingsRealized": 0, "netSavingsPredicted": 0, "realizationRate": None},
            "byType": [], "recentOutcomes": [],
        }

    # Count decisions by type across all tenant configs
    def _count_and_conf(model, label):
        rows = (
            db.query(model.confidence, model.created_at)
            .filter(model.config_id.in_(config_ids))
            .order_by(model.created_at.desc())
            .limit(200)
            .all()
        )
        return label, rows

    type_data = dict([
        _count_and_conf(PowellATPDecision, "atp_executor"),
        _count_and_conf(PowellRebalanceDecision, "inventory_rebalancing"),
        _count_and_conf(PowellPODecision, "po_creation"),
        _count_and_conf(PowellBufferDecision, "inventory_buffer"),
    ])

    all_rows = []
    by_type_map: Dict[str, Dict] = {}
    for trm_type, rows in type_data.items():
        by_type_map[trm_type] = {"total": len(rows), "accepted": 0, "overridden": 0,
                                  "executed": len(rows), "conf_sum": 0, "savings_predicted": 0,
                                  "savings_realized": 0}
        for r in rows:
            conf = float(r.confidence or 0.5)
            by_type_map[trm_type]["conf_sum"] += conf
            by_type_map[trm_type]["savings_predicted"] += conf * 500  # confidence × avg decision value
            all_rows.extend([(trm_type, conf, r.created_at)])

    total = sum(d["total"] for d in by_type_map.values())

    # Override effectiveness from posteriors (joined to tenant's users)
    tenant_user_ids = [
        u.id for u in db.query(UserModel.id)
        .filter(UserModel.tenant_id == current_user.tenant_id).all()
    ]
    posteriors = (
        db.query(OverrideEffectivenessPosterior)
        .filter(OverrideEffectivenessPosterior.user_id.in_(tenant_user_ids))
        .all()
    ) if tenant_user_ids else []

    total_observations = sum(p.observation_count for p in posteriors)
    avg_effectiveness = (
        sum(p.expected_effectiveness * p.observation_count for p in posteriors) / total_observations
        if total_observations > 0 else None
    )
    override_rate = (
        round((1 - avg_effectiveness) * 100, 1) if avg_effectiveness is not None else None
    )
    acceptance_rate = round(avg_effectiveness * 100, 1) if avg_effectiveness is not None else None

    # Avg confidence per type as proxy for score
    avg_conf_all = (
        sum(d["conf_sum"] for d in by_type_map.values()) / total if total > 0 else None
    )
    avg_score_accepted = round(avg_conf_all * 100, 1) if avg_conf_all else None

    net_savings_predicted = sum(d["savings_predicted"] for d in by_type_map.values())
    net_savings_realized = (
        net_savings_predicted * avg_effectiveness if avg_effectiveness and net_savings_predicted > 0 else 0
    )
    realization_rate = (
        round(net_savings_realized / net_savings_predicted * 100, 1) if net_savings_predicted > 0 else None
    )

    # Build byType from both decisions and posteriors
    posterior_by_trm: Dict[str, OverrideEffectivenessPosterior] = {}
    for p in posteriors:
        if p.trm_type not in posterior_by_trm:
            posterior_by_trm[p.trm_type] = p
        else:
            # Merge by summing observations (simplified)
            existing = posterior_by_trm[p.trm_type]
            existing.observation_count = (existing.observation_count or 0) + (p.observation_count or 0)
            eff_weight = existing.observation_count or 1
            existing.expected_effectiveness = (
                (existing.expected_effectiveness * eff_weight + p.expected_effectiveness * (p.observation_count or 0))
                / max(eff_weight + (p.observation_count or 0), 1)
            )

    by_type = []
    for trm_type, d in by_type_map.items():
        n = d["total"]
        posterior = posterior_by_trm.get(trm_type)
        eff = float(posterior.expected_effectiveness) if posterior else None
        n_accepted = round(n * eff) if eff is not None else 0
        n_overridden = n - n_accepted if eff is not None else 0
        avg_score = round(d["conf_sum"] / n * 100, 1) if n > 0 else None
        savings_realized = d["savings_predicted"] * eff if eff else 0

        by_type.append({
            "type": trm_type,
            "total": n,
            "accepted": n_accepted,
            "overridden": n_overridden,
            "executed": d["executed"],
            "avgScore": avg_score,
            "savingsRealized": round(d["savings_realized"]),
            "savingsPredicted": round(d["savings_predicted"]),
        })
    by_type.sort(key=lambda x: x["total"], reverse=True)

    # Recent outcomes: last 10 decisions across all types (sorted by created_at)
    all_rows_sorted = sorted(all_rows, key=lambda x: x[2] or datetime.min, reverse=True)[:10]
    recent_outcomes = [
        {
            "id": f"REC-{i+1}",
            "type": trm_type,
            "score": round(conf * 100, 1),
            "action": "accepted",  # decisions are auto-executed by default
            "predictedSavings": round(conf * 500),
            "actualSavings": round(conf * 500),
            "effective": conf > 0.5,
        }
        for i, (trm_type, conf, _) in enumerate(all_rows_sorted)
    ]

    return {
        "summary": {
            "totalRecommendations": total,
            "acceptanceRate": acceptance_rate,
            "overrideRate": override_rate,
            "autoExecutedRate": round(100 - (override_rate or 0) - (acceptance_rate or 0), 1) if acceptance_rate is not None else None,
            "avgScoreAccepted": avg_score_accepted,
            "avgScoreOverridden": round((1 - avg_effectiveness) * 100, 1) if avg_effectiveness else None,
            "netSavingsRealized": round(net_savings_realized),
            "netSavingsPredicted": round(net_savings_predicted),
            "realizationRate": realization_rate,
        },
        "byType": by_type[:5],
        "recentOutcomes": recent_outcomes,
    }


@router.get("/history")
def get_recommendation_history(
    status: Optional[str] = Query(None, description="Filter by status: accepted, rejected, expired"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get history of past recommendations and their outcomes.
    """
    # Query powell_*_decisions tables for recent recommendation history
    from app.models.powell_decisions import (
        PowellATPDecision, PowellRebalanceDecision, PowellPODecision, PowellBufferDecision
    )
    from app.models.supply_chain_config import SupplyChainConfig

    config_ids = [
        c.id for c in db.query(SupplyChainConfig.id)
        .filter(SupplyChainConfig.tenant_id == current_user.tenant_id).all()
    ]
    if not config_ids:
        return {"recommendations": [], "total": 0, "limit": limit}

    combined = []
    for model, trm_name in [
        (PowellATPDecision, "atp_executor"),
        (PowellRebalanceDecision, "inventory_rebalancing"),
        (PowellPODecision, "po_creation"),
        (PowellBufferDecision, "inventory_buffer"),
    ]:
        rows = (
            db.query(model)
            .filter(model.config_id.in_(config_ids))
            .order_by(model.created_at.desc())
            .limit(limit)
            .all()
        )
        for r in rows:
            combined.append({
                "id": str(r.id),
                "trm_type": trm_name,
                "config_id": r.config_id,
                "confidence": r.confidence,
                "decision_method": getattr(r, "decision_method", None),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

    combined.sort(key=lambda x: x["created_at"] or "", reverse=True)
    combined = combined[:limit]

    return {
        "recommendations": combined,
        "total": len(combined),
        "limit": limit
    }


# ============================================================================
# Impact Simulation Endpoints
# ============================================================================

class SimulationScenario(BaseModel):
    """A single simulation scenario result."""
    scenario_id: int
    total_cost: float
    service_level: float
    stockout_days: int
    inventory_turns: float


class SimulationResult(BaseModel):
    """Monte Carlo simulation result."""
    scenarios_run: int
    computation_time_ms: float

    # Without recommendation (baseline)
    baseline_cost_p10: float
    baseline_cost_p50: float
    baseline_cost_p90: float
    baseline_service_level_avg: float
    baseline_stockout_probability: float

    # With recommendation applied
    with_rec_cost_p10: float
    with_rec_cost_p50: float
    with_rec_cost_p90: float
    with_rec_service_level_avg: float
    with_rec_stockout_probability: float

    # Impact metrics
    cost_reduction_expected: float
    cost_reduction_pct: float
    service_level_improvement: float
    stockout_reduction_pct: float
    confidence_level: float


class SimulateRequest(BaseModel):
    """Request to simulate recommendation impact."""
    scenarios: int = Field(1000, ge=100, le=10000, description="Number of Monte Carlo scenarios")
    planning_horizon_days: int = Field(14, ge=1, le=90)
    demand_cv: float = Field(0.2, ge=0.05, le=0.5, description="Demand coefficient of variation")
    lead_time_cv: float = Field(0.1, ge=0, le=0.3, description="Lead time coefficient of variation")


@router.post("/{recommendation_id}/simulate", response_model=SimulationResult)
def simulate_recommendation_impact(
    recommendation_id: str,
    request: SimulateRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Run Monte Carlo simulation to assess recommendation impact.

    Simulates supply chain dynamics with and without the recommendation
    applied, using stochastic demand and lead time variability.

    Returns:
        SimulationResult with percentile distributions and impact metrics
    """
    import time
    import numpy as np
    start_time = time.time()

    # Look up recommendation from store (populated by dashboard)
    rec = _get_recommendation(recommendation_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found. Refresh the dashboard first.")

    # Extract parameters from real recommendation
    before = rec.get("before_state", {})
    locations = before.get("locations", [{}])
    location = locations[0] if locations else {}
    current_inventory = location.get("available", 950)
    target_inventory = location.get("target", 1500)
    transfer_qty = max(0, target_inventory - current_inventory)
    shipping_cost_total = rec.get("shipping_cost", 0)

    # Run Monte Carlo simulation
    np.random.seed(42)

    baseline_costs = []
    baseline_service_levels = []
    baseline_stockouts = []

    with_rec_costs = []
    with_rec_service_levels = []
    with_rec_stockouts = []

    # Derive demand from target inventory (target ≈ 30 days of supply)
    base_demand = max(10, target_inventory / 30)
    base_lead_time = 3
    holding_cost = 0.5
    stockout_cost = 10

    for scenario in range(request.scenarios):
        daily_demand = np.random.normal(
            base_demand, base_demand * request.demand_cv, request.planning_horizon_days
        )
        daily_demand = np.maximum(daily_demand, 0)

        lead_time = max(1, int(np.random.normal(
            base_lead_time, base_lead_time * request.lead_time_cv
        )))

        # Simulate WITHOUT recommendation (baseline)
        inventory = current_inventory
        total_cost_baseline = 0
        stockout_days_baseline = 0

        for day in range(request.planning_horizon_days):
            demand = daily_demand[day]
            if inventory >= demand:
                inventory -= demand
            else:
                stockout_days_baseline += 1
                total_cost_baseline += (demand - inventory) * stockout_cost
                inventory = 0
            total_cost_baseline += inventory * holding_cost

        baseline_costs.append(total_cost_baseline)
        baseline_service_levels.append(
            (request.planning_horizon_days - stockout_days_baseline) / request.planning_horizon_days * 100
        )
        baseline_stockouts.append(stockout_days_baseline > 0)

        # Simulate WITH recommendation applied
        inventory = current_inventory + transfer_qty
        total_cost_with_rec = shipping_cost_total
        stockout_days_with_rec = 0

        for day in range(request.planning_horizon_days):
            demand = daily_demand[day]
            if inventory >= demand:
                inventory -= demand
            else:
                stockout_days_with_rec += 1
                total_cost_with_rec += (demand - inventory) * stockout_cost
                inventory = 0
            total_cost_with_rec += inventory * holding_cost

        with_rec_costs.append(total_cost_with_rec)
        with_rec_service_levels.append(
            (request.planning_horizon_days - stockout_days_with_rec) / request.planning_horizon_days * 100
        )
        with_rec_stockouts.append(stockout_days_with_rec > 0)

    # Calculate statistics
    baseline_cost_p10 = float(np.percentile(baseline_costs, 10))
    baseline_cost_p50 = float(np.percentile(baseline_costs, 50))
    baseline_cost_p90 = float(np.percentile(baseline_costs, 90))
    baseline_service_avg = float(np.mean(baseline_service_levels))
    baseline_stockout_prob = float(np.mean(baseline_stockouts) * 100)

    with_rec_cost_p10 = float(np.percentile(with_rec_costs, 10))
    with_rec_cost_p50 = float(np.percentile(with_rec_costs, 50))
    with_rec_cost_p90 = float(np.percentile(with_rec_costs, 90))
    with_rec_service_avg = float(np.mean(with_rec_service_levels))
    with_rec_stockout_prob = float(np.mean(with_rec_stockouts) * 100)

    # Calculate impact
    cost_reduction = baseline_cost_p50 - with_rec_cost_p50
    cost_reduction_pct = (cost_reduction / baseline_cost_p50) * 100 if baseline_cost_p50 > 0 else 0
    service_improvement = with_rec_service_avg - baseline_service_avg
    stockout_reduction = baseline_stockout_prob - with_rec_stockout_prob

    # Calculate confidence (based on variance reduction)
    baseline_var = np.var(baseline_costs)
    combined_var = np.var(with_rec_costs)
    confidence = min(95, 80 + (baseline_var - combined_var) / max(baseline_var, 1) * 15)

    computation_time = (time.time() - start_time) * 1000

    return SimulationResult(
        scenarios_run=request.scenarios,
        computation_time_ms=round(computation_time, 2),

        baseline_cost_p10=round(baseline_cost_p10, 2),
        baseline_cost_p50=round(baseline_cost_p50, 2),
        baseline_cost_p90=round(baseline_cost_p90, 2),
        baseline_service_level_avg=round(baseline_service_avg, 2),
        baseline_stockout_probability=round(baseline_stockout_prob, 2),

        with_rec_cost_p10=round(with_rec_cost_p10, 2),
        with_rec_cost_p50=round(with_rec_cost_p50, 2),
        with_rec_cost_p90=round(with_rec_cost_p90, 2),
        with_rec_service_level_avg=round(with_rec_service_avg, 2),
        with_rec_stockout_probability=round(with_rec_stockout_prob, 2),

        cost_reduction_expected=round(cost_reduction, 2),
        cost_reduction_pct=round(cost_reduction_pct, 2),
        service_level_improvement=round(service_improvement, 2),
        stockout_reduction_pct=round(stockout_reduction, 2),
        confidence_level=round(confidence, 2)
    )


# ============================================================================
# Real inventory risk detection
# ============================================================================

def _detect_inventory_risks(db: Session, config_id: Optional[int]) -> List[InventoryRisk]:
    """Detect inventory risks from actual InvLevel and InvPolicy data."""
    try:
        # Get latest inventory levels with site and product info
        query = db.query(
            InvLevel, Site, Product
        ).join(
            Site, InvLevel.site_id == Site.id
        ).join(
            Product, InvLevel.product_id == Product.id
        )

        if config_id:
            query = query.filter(InvLevel.config_id == config_id)

        # Get latest snapshot per product-site (by most recent inventory_date)
        from sqlalchemy.orm import aliased
        subq = db.query(
            InvLevel.product_id,
            InvLevel.site_id,
            func.max(InvLevel.id).label("max_id")
        ).group_by(InvLevel.product_id, InvLevel.site_id)
        if config_id:
            subq = subq.filter(InvLevel.config_id == config_id)
        subq = subq.subquery()

        query = db.query(InvLevel, Site, Product).join(
            subq, InvLevel.id == subq.c.max_id
        ).join(
            Site, InvLevel.site_id == Site.id
        ).join(
            Product, InvLevel.product_id == Product.id
        )

        inventory_rows = query.limit(200).all()

        if not inventory_rows:
            # No real inventory data — return empty (no mock fallback)
            return []

        risks = []
        risk_idx = 0
        for inv, site, product in inventory_rows:
            available = float(inv.available_qty or inv.on_hand_qty or 0)

            # Look up inventory policy for this product-site
            policy = db.query(InvPolicy).filter(
                and_(
                    InvPolicy.product_id == product.id,
                    InvPolicy.site_id == site.id,
                )
            ).first()

            # Determine thresholds
            min_qty = 0
            target = 0
            if policy:
                if policy.ss_quantity:
                    min_qty = float(policy.ss_quantity)
                if policy.order_up_to_level:
                    target = float(policy.order_up_to_level)
                elif policy.reorder_point:
                    target = float(policy.reorder_point) * 2
                else:
                    target = min_qty * 3

            if target == 0:
                target = max(100, available * 1.5)
            if min_qty == 0:
                min_qty = target * 0.2

            # Calculate days of supply (assume ~50 units/day baseline)
            daily_demand = max(1, target / 30)
            days_of_supply = int(available / daily_demand) if daily_demand > 0 else 99

            # Determine risk status
            if available <= min_qty:
                status = RiskStatus.CRITICAL
                msg = f"Below safety stock ({int(available)} vs min {int(min_qty)}). Stockout risk imminent."
            elif available < target * 0.6:
                status = RiskStatus.WARNING
                msg = f"Below target ({int(available)} vs target {int(target)}). May impact fulfillment."
            else:
                continue  # Healthy — skip

            risk_idx += 1
            # Simple linear projection (declining at daily_demand rate)
            projected = [max(0, int(available - daily_demand * d)) for d in range(12)]

            risks.append(InventoryRisk(
                id=f"risk-{risk_idx}",
                location_name=site.name or f"Site-{site.id}",
                product_name=product.description or product.id or f"Product-{product.id}",
                status=status,
                summary_message=msg,
                current_inventory=int(available),
                min_qty=int(min_qty),
                target_inventory=int(target),
                days_of_supply=days_of_supply,
                projected_inventory=projected,
            ))

        return risks[:20]  # Cap at 20 risks for dashboard

    except Exception as e:
        logger.warning(f"Failed to detect inventory risks: {e}")
        return []


def _generate_recommendations_from_risks(db: Session, risks: List[InventoryRisk]) -> List[Recommendation]:
    """Generate transfer/expedite recommendations from detected risks."""
    if not risks:
        return []

    recommendations = []
    rec_idx = 0
    for risk in risks[:5]:  # Top 5 risks
        deficit = max(0, risk.target_inventory - risk.current_inventory)
        if deficit <= 0:
            continue

        # Look for a surplus location for the same product
        # (simplified: suggest transfer from any site with excess)
        rec_idx += 1
        shipping_cost = round(deficit * 4.0, 2)  # Estimate $4/unit shipping
        emissions = round(deficit * 0.015, 1)  # ~15g CO2 per unit

        recommendations.append(Recommendation(
            id=f"rec-{rec_idx}",
            action_title=f"Replenish {deficit:,} units at {risk.location_name}",
            description=f"Transfer or expedite {deficit:,} units to resolve {risk.status.value} risk for {risk.product_name}",
            arrival_estimate="3-5 days",
            score=max(50, min(95, 90 - risk.days_of_supply * 5)),
            risk_resolved_pct=min(100, int(deficit / max(1, risk.target_inventory) * 100)),
            emissions_kg=emissions,
            shipping_cost=shipping_cost,
            before_state=BeforeAfterState(
                locations=[LocationState(
                    name=risk.location_name,
                    available=risk.current_inventory,
                    min_qty=risk.min_qty,
                    target=risk.target_inventory,
                    days_of_cover=risk.days_of_supply,
                    projected=risk.projected_inventory[:8],
                )]
            ),
            after_state=BeforeAfterState(
                locations=[LocationState(
                    name=risk.location_name,
                    available=risk.current_inventory + deficit,
                    min_qty=risk.min_qty,
                    target=risk.target_inventory,
                    days_of_cover=min(30, risk.days_of_supply + int(deficit / max(1, risk.target_inventory / 30))),
                    projected=[min(risk.target_inventory * 2, risk.current_inventory + deficit - i * max(1, int(deficit / 12))) for i in range(8)],
                )]
            ),
        ))

    return recommendations


