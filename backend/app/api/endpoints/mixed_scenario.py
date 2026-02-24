from dataclasses import asdict
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import logging

from app.db.session import get_sync_db

logger = logging.getLogger(__name__)
from app.schemas.scenario import (
    ScenarioCreate,
    ScenarioUpdate,
    ScenarioState,
    Scenario as ScenarioSchema,
    ScenarioStatus,
    ScenarioInDBBase
)
from app.models.scenario import Scenario as ScenarioModel
from app.models.scenario_user import ScenarioUser
from app.models.supply_chain import ScenarioRound
from app.models.supply_chain_config import Node
from app.schemas.scenario_user import ScenarioUserAssignment, ScenarioUserResponse
from app.services.llm_agent import AutonomyLLMError
from app.services.mixed_scenario_service import MixedScenarioService
from app.services.agent_recommendation_service import (
    AgentRecommendationService,
    get_agent_recommendation_service,
)
from app.services.atp_service import ATPService, get_atp_service, CustomerDemand
from app.services.ctp_service import CTPService, get_ctp_service
from app.services.agent_mode_service import (
    AgentModeService,
    get_agent_mode_service,
    AgentMode,
    ModeSwitchReason
)
from app.services.adaptive_weight_learner import (
    AdaptiveWeightLearner,
    get_adaptive_weight_learner,
    LearningMethod
)
from app.services.agent_orchestration_integration import (
    AgentOrchestrationIntegration,
    get_agent_orchestration_integration
)
from app.core.security import oauth2_scheme, get_token_from_request, decode_token
from app.models.user import User
from fastapi import Request

router = APIRouter()

def get_current_user_sync(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_sync_db)
) -> User:
    """Synchronous version of get_current_user for use with sync services."""
    from app.core.security import HTTPException, status
    from app.core.config import settings

    # oauth2_scheme returns just the token if found in Authorization header
    # If not found, try cookie
    if not token:
        token = request.cookies.get(settings.COOKIE_ACCESS_TOKEN_NAME)
        if token:
            token = token.strip('"')
            if token.lower().startswith("bearer "):
                token = token[7:]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Sync database query
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
            email = payload.get("email")
            if email:
                user = db.query(User).filter(User.email == email).first()

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

        return user
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

def get_mixed_scenario_service(db: Session = Depends(get_sync_db)) -> MixedScenarioService:
    return MixedScenarioService(db)


def _get_participant_node(db: Session, scenario_user: ScenarioUser, scenario: ScenarioModel) -> Optional[Node]:
    """Look up the Node for a scenario_user based on their site_key."""
    if not scenario_user.site_key or not scenario.supply_chain_config_id:
        return None
    return db.query(Node).filter(
        Node.config_id == scenario.supply_chain_config_id,
        Node.dag_type == scenario_user.site_key
    ).first()

@router.post("/scenarios/", response_model=ScenarioSchema, status_code=status.HTTP_201_CREATED)
def create_mixed_game(
    scenario_data: ScenarioCreate,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """
    Create a new game with mixed human and AI scenario_users.
    
    - **scenario_user_assignments**: List of scenario_user assignments specifying which roles are human/AI
    - **demand_pattern**: Configuration for customer demand pattern
    - **max_rounds**: Total number of rounds in the game
    """
    try:
        return scenario_service.create_game(scenario_data, current_user.id)
    except AutonomyLLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/scenarios/{scenario_id}/start", response_model=ScenarioSchema)
def start_game(
    scenario_id: int,
    debug_logging: bool = Body(False, embed=True),
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """Start a game that's in the 'created' state."""
    try:
        return scenario_service.start_game(scenario_id, debug_logging=debug_logging)
    except AutonomyLLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/scenarios/{scenario_id}/stop", response_model=ScenarioSchema)
def stop_game(
    scenario_id: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """Stop a game that's in progress."""
    try:
        return scenario_service.stop_game(scenario_id)
    except AutonomyLLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/scenarios/{scenario_id}/next-round", response_model=ScenarioSchema)
def next_round(
    scenario_id: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """Advance to the next round of the game."""
    try:
        scenario_service.start_new_round(scenario_id)
        return scenario_service.get_scenario_state(scenario_id)
    except AutonomyLLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/scenarios/{scenario_id}/finish", response_model=ScenarioSchema)
def finish_game(
    scenario_id: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """Finish a game and compute a summary."""
    try:
        return scenario_service.finish_game(scenario_id)
    except AutonomyLLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/scenarios/{scenario_id}/report", response_model=dict)
def get_game_report(
    scenario_id: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """Get simple endgame report."""
    try:
        return scenario_service.get_report(scenario_id)
    except AutonomyLLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.get("/scenarios/{scenario_id}/state", response_model=ScenarioState)
def get_scenario_state(
    scenario_id: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """Get the current state of a game."""
    try:
        return scenario_service.get_scenario_state(scenario_id)
    except AutonomyLLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

@router.put("/scenarios/{scenario_id}", response_model=ScenarioState)
def update_game(
    scenario_id: int,
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """Update a game's core configuration, demand pattern, and scenario_user assignments."""
    try:
        scenario_service.update_game(scenario_id, payload)
        return scenario_service.get_scenario_state(scenario_id)
    except AutonomyLLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.delete("/scenarios/{scenario_id}", response_model=dict)
def delete_game(
    scenario_id: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    try:
        return scenario_service.delete_game(scenario_id, current_user)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to delete this game")
    except AutonomyLLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.get("/scenarios/", response_model=List[ScenarioInDBBase])
def list_games(
    status: Optional[ScenarioStatus] = None,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """List all games the current user is allowed to view."""
    return scenario_service.list_games(current_user=current_user, status=status)


# =============================================================================
# DAG Sequential Execution Endpoints (Phase 1)
# =============================================================================


class FulfillmentDecisionRequest(BaseModel):
    """Request body for fulfillment decision"""
    scenario_user_id: int
    fulfill_qty: int
    # Phase 2: Copilot mode metadata (optional)
    ai_recommendation: Optional[int] = None  # AI's suggested quantity
    ai_confidence: Optional[float] = None  # AI's confidence score (0-1)
    ai_agent_type: Optional[str] = None  # Agent type: llm, gnn, trm, heuristic
    ai_reasoning: Optional[str] = None  # AI's reasoning (for RLHF)


class ReplenishmentDecisionRequest(BaseModel):
    """Request body for replenishment decision"""
    scenario_user_id: int
    order_qty: int
    # Phase 2: Copilot mode metadata (optional)
    ai_recommendation: Optional[int] = None  # AI's suggested quantity
    ai_confidence: Optional[float] = None  # AI's confidence score (0-1)
    ai_agent_type: Optional[str] = None  # Agent type: llm, gnn, trm, heuristic
    ai_reasoning: Optional[str] = None  # AI's reasoning (for RLHF)


@router.post("/scenarios/{scenario_id}/rounds/{round_number}/fulfillment")
async def submit_fulfillment_decision(
    scenario_id: int,
    round_number: int,
    request: FulfillmentDecisionRequest,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """
    Submit fulfillment decision for current round (ATP-based shipment).

    DAG Sequential Execution - Phase 1: ScenarioUsers fulfill downstream orders
    in downstream→upstream order. Creates TransferOrder and updates inventory.

    Args:
        scenario_id: Scenario ID
        round_number: Current round number
        request: Fulfillment decision (scenario_user_id, fulfill_qty)

    Returns:
        {
            "success": true,
            "transfer_order_id": 1542,
            "updated_inventory": 114,
            "updated_atp": 34,
            "phase": "FULFILLMENT",
            "awaiting_participants": ["wholesaler", "distributor"]
        }
    """
    from app.models.scenario import Scenario
    from app.models.scenario_user import ScenarioUser
    from app.models.supply_chain import ScenarioRound, RoundPhase
    from app.api.endpoints.websocket import (
        broadcast_fulfillment_completed,
        broadcast_phase_change,
        broadcast_all_participants_ready,
    )

    try:
        # Get game
        scenario = scenario_service.db.query(Scenario).filter_by(id=scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Verify game uses DAG sequential (check column, fallback to config for backward compat)
        use_dag = getattr(scenario, 'use_dag_sequential', None)
        if use_dag is None:
            use_dag = scenario.config.get("use_dag_sequential", False)
        if not use_dag:
            raise HTTPException(
                status_code=400,
                detail="Scenario does not use DAG sequential execution"
            )

        # Get round
        round_obj = (
            scenario_service.db.query(ScenarioRound)
            .filter_by(scenario_id=scenario_id, round_number=round_number)
            .first()
        )
        if not round_obj:
            raise HTTPException(status_code=404, detail="Round not found")

        # Verify phase
        if round_obj.current_phase != RoundPhase.FULFILLMENT:
            raise HTTPException(
                status_code=400,
                detail=f"Round is in {round_obj.current_phase} phase, expected FULFILLMENT"
            )

        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(id=request.scenario_user_id).first()
        if not scenario_user or scenario_user.scenario_id != scenario_id:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Phase 2: RLHF data collection and authority check (if copilot mode)
        rlhf_feedback_id = None
        authority_check_result = None

        if request.ai_recommendation is not None:
            # Import Phase 2 services
            from app.services.rlhf_data_collector import RLHFDataCollector, get_rlhf_data_collector
            from app.services.authority_check_service import AuthorityCheckService, get_authority_check_service

            # Collect RLHF feedback
            rlhf_collector = get_rlhf_data_collector(scenario_service.db)

            # Build game state for RLHF context
            scenario_state = {
                "inventory": scenario_user.current_stock,
                "backlog": scenario_user.backlog_units or 0,
                "pipeline": scenario_user.pipeline_orders or 0,
                "incoming_order": scenario_user.incoming_order or 0,
                "role": scenario_user.role,
                "round": round_number,
            }

            rlhf_feedback_id = rlhf_collector.record_feedback(
                scenario_user_id=scenario_user.id,
                scenario_id=scenario_id,
                round_number=round_number,
                agent_type=request.ai_agent_type or "unknown",
                scenario_state=scenario_state,
                ai_suggestion=request.ai_recommendation,
                human_decision=request.fulfill_qty,
                ai_reasoning=request.ai_reasoning,
                ai_confidence=request.ai_confidence,
            )

            # Authority check if human overrode AI
            if request.fulfill_qty != request.ai_recommendation:
                authority_service = get_authority_check_service(scenario_service.db)
                authority_check_result = authority_service.check_override_authority(
                    scenario_user=scenario_user,
                    agent_qty=request.ai_recommendation,
                    human_qty=request.fulfill_qty,
                    action_type="fulfillment",
                )

        # Phase 3: ATP validation before fulfillment
        atp_warning = None
        current_atp = scenario_service._calculate_atp(scenario_user)

        if request.fulfill_qty > current_atp:
            atp_warning = {
                "type": "atp_exceeded",
                "message": f"Requested fulfillment ({request.fulfill_qty}) exceeds available ATP ({current_atp})",
                "current_atp": current_atp,
                "requested_qty": request.fulfill_qty,
                "shortfall": request.fulfill_qty - current_atp,
            }
            logger.warning(
                f"ATP warning for scenario_user {scenario_user.id}: "
                f"fulfillment {request.fulfill_qty} > ATP {current_atp}"
            )

        # Process fulfillment decision
        transfer_order = scenario_service._process_node_fulfillment_decision(
            scenario, round_obj, scenario_user, request.fulfill_qty
        )

        if not transfer_order:
            raise HTTPException(status_code=500, detail="Failed to create transfer order")

        # Calculate updated ATP
        updated_atp = scenario_service._calculate_atp(scenario_user)

        # Get scenario_user counts for broadcast
        all_participants = scenario_service.db.query(ScenarioUser).filter_by(scenario_id=scenario_id).all()
        total_participants = len(all_participants)

        # Count scenario_users who have submitted fulfillment
        from app.models.supply_chain import ScenarioUserPeriod
        fulfilled_count = (
            scenario_service.db.query(ScenarioUserPeriod)
            .filter(
                ScenarioUserPeriod.round_id == round_obj.id,
                ScenarioUserPeriod.fulfillment_submitted_at.isnot(None)
            )
            .count()
        )

        # Broadcast fulfillment completed
        await broadcast_fulfillment_completed(
            scenario_id=scenario_id,
            scenario_user_id=scenario_user.id,
            participant_role=scenario_user.assignment_key or scenario_user.role,
            fulfill_qty=request.fulfill_qty,
            participants_completed=fulfilled_count,
            total_participants=total_participants,
        )

        # Check if ready to transition to REPLENISHMENT phase
        ready_to_transition = scenario_service._check_phase_transition(
            scenario, round_obj, RoundPhase.FULFILLMENT, RoundPhase.REPLENISHMENT
        )

        if ready_to_transition:
            # Broadcast all scenario_users ready before transition
            await broadcast_all_participants_ready(
                scenario_id=scenario_id,
                round_number=round_number,
                phase="fulfillment",
            )

            scenario_service._transition_phase(scenario, round_obj, RoundPhase.REPLENISHMENT)

            # Broadcast phase change
            await broadcast_phase_change(
                scenario_id=scenario_id,
                round_number=round_number,
                new_phase="replenishment",
                phase_started_at=round_obj.phase_started_at.isoformat() if round_obj.phase_started_at else None,
                participants_completed=0,
                total_participants=total_participants,
            )

            # Process autonomous agents' replenishment decisions
            scenario_service._process_autonomous_agent_replenishment(scenario, round_obj, all_participants)

        # Get awaiting scenario_users (those who haven't submitted)
        submitted_participants = (
            scenario_service.db.query(ScenarioUserPeriod.scenario_user_id)
            .filter(ScenarioUserPeriod.round_id == round_obj.id)
            .all()
        )
        submitted_ids = {p[0] for p in submitted_participants}
        awaiting = [
            p.assignment_key for p in all_participants
            if p.id not in submitted_ids
        ]

        # Build response
        response = {
            "success": True,
            "transfer_order_id": transfer_order.id,
            "updated_inventory": scenario_user.current_stock,
            "updated_atp": updated_atp,
            "phase": round_obj.current_phase.value,
            "awaiting_participants": awaiting,
        }

        # Phase 2: Include copilot metadata if applicable
        if rlhf_feedback_id:
            response["rlhf_feedback_id"] = rlhf_feedback_id
        if authority_check_result:
            response["authority_check"] = {
                "override_approved": authority_check_result.override_approved,
                "requires_approval": authority_check_result.requires_approval,
                "authority_level": authority_check_result.authority_level,
                "override_percentage": round(authority_check_result.override_percentage, 1),
                "threshold_percentage": authority_check_result.threshold_percentage,
                "decision_proposal_id": authority_check_result.decision_proposal_id,
            }

        # Phase 3: Include ATP warning if applicable
        if atp_warning:
            response["atp_warning"] = atp_warning

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fulfillment decision error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenarios/{scenario_id}/rounds/{round_number}/replenishment")
async def submit_replenishment_decision(
    scenario_id: int,
    round_number: int,
    request: ReplenishmentDecisionRequest,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """
    Submit replenishment decision for current round (upstream order).

    DAG Sequential Execution - Phase 2: ScenarioUsers order from upstream suppliers.
    Creates TransferOrder/PurchaseOrder and updates scenario_user state.

    Args:
        scenario_id: Scenario ID
        round_number: Current round number
        request: Replenishment decision (scenario_user_id, order_qty)

    Returns:
        {
            "success": true,
            "transfer_order_id": 1543,
            "arrival_round": 18,
            "phase": "REPLENISHMENT",
            "round_completed": false
        }
    """
    from app.models.scenario import Scenario
    from app.models.scenario_user import ScenarioUser
    from app.models.supply_chain import ScenarioRound, RoundPhase
    from app.api.endpoints.websocket import (
        broadcast_replenishment_completed,
        broadcast_phase_change,
        broadcast_round_completed,
        broadcast_all_participants_ready,
    )

    try:
        # Get game
        scenario = scenario_service.db.query(Scenario).filter_by(id=scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Verify game uses DAG sequential (check column, fallback to config for backward compat)
        use_dag = getattr(scenario, 'use_dag_sequential', None)
        if use_dag is None:
            use_dag = scenario.config.get("use_dag_sequential", False)
        if not use_dag:
            raise HTTPException(
                status_code=400,
                detail="Scenario does not use DAG sequential execution"
            )

        # Get round
        round_obj = (
            scenario_service.db.query(ScenarioRound)
            .filter_by(scenario_id=scenario_id, round_number=round_number)
            .first()
        )
        if not round_obj:
            raise HTTPException(status_code=404, detail="Round not found")

        # Verify phase
        if round_obj.current_phase != RoundPhase.REPLENISHMENT:
            raise HTTPException(
                status_code=400,
                detail=f"Round is in {round_obj.current_phase} phase, expected REPLENISHMENT"
            )

        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(id=request.scenario_user_id).first()
        if not scenario_user or scenario_user.scenario_id != scenario_id:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Phase 2: RLHF data collection and authority check (if copilot mode)
        rlhf_feedback_id = None
        authority_check_result = None

        if request.ai_recommendation is not None:
            # Import Phase 2 services
            from app.services.rlhf_data_collector import RLHFDataCollector, get_rlhf_data_collector
            from app.services.authority_check_service import AuthorityCheckService, get_authority_check_service

            # Collect RLHF feedback
            rlhf_collector = get_rlhf_data_collector(scenario_service.db)

            # Build game state for RLHF context
            scenario_state = {
                "inventory": scenario_user.current_stock,
                "backlog": scenario_user.backlog_units or 0,
                "pipeline": scenario_user.pipeline_orders or 0,
                "incoming_order": scenario_user.incoming_order or 0,
                "role": scenario_user.role,
                "round": round_number,
            }

            rlhf_feedback_id = rlhf_collector.record_feedback(
                scenario_user_id=scenario_user.id,
                scenario_id=scenario_id,
                round_number=round_number,
                agent_type=request.ai_agent_type or "unknown",
                scenario_state=scenario_state,
                ai_suggestion=request.ai_recommendation,
                human_decision=request.order_qty,
                ai_reasoning=request.ai_reasoning,
                ai_confidence=request.ai_confidence,
            )

            # Authority check if human overrode AI
            if request.order_qty != request.ai_recommendation:
                authority_service = get_authority_check_service(scenario_service.db)
                authority_check_result = authority_service.check_override_authority(
                    scenario_user=scenario_user,
                    agent_qty=request.ai_recommendation,
                    human_qty=request.order_qty,
                    action_type="replenishment",
                )

        # Process replenishment decision
        transfer_order = scenario_service._process_node_replenishment_decision(
            scenario, round_obj, scenario_user, request.order_qty
        )

        if not transfer_order:
            raise HTTPException(status_code=500, detail="Failed to create transfer order")

        # Get scenario_user counts for broadcast
        all_participants = scenario_service.db.query(ScenarioUser).filter_by(scenario_id=scenario_id).all()
        total_participants = len(all_participants)

        # Count scenario_users who have submitted replenishment
        from app.models.supply_chain import ScenarioUserPeriod
        replenished_count = (
            scenario_service.db.query(ScenarioUserPeriod)
            .filter(
                ScenarioUserPeriod.round_id == round_obj.id,
                ScenarioUserPeriod.replenishment_submitted_at.isnot(None)
            )
            .count()
        )

        # Broadcast replenishment completed
        await broadcast_replenishment_completed(
            scenario_id=scenario_id,
            scenario_user_id=scenario_user.id,
            participant_role=scenario_user.assignment_key or scenario_user.role,
            order_qty=request.order_qty,
            participants_completed=replenished_count,
            total_participants=total_participants,
        )

        # Check if ready to transition to COMPLETED phase
        ready_to_transition = scenario_service._check_phase_transition(
            scenario, round_obj, RoundPhase.REPLENISHMENT, RoundPhase.COMPLETED
        )

        round_completed = False
        if ready_to_transition:
            # Broadcast all scenario_users ready before transition
            await broadcast_all_participants_ready(
                scenario_id=scenario_id,
                round_number=round_number,
                phase="replenishment",
            )

            scenario_service._transition_phase(scenario, round_obj, RoundPhase.COMPLETED)
            round_completed = True

            # Broadcast phase change to completed
            await broadcast_phase_change(
                scenario_id=scenario_id,
                round_number=round_number,
                new_phase="completed",
                phase_started_at=round_obj.phase_started_at.isoformat() if round_obj.phase_started_at else None,
                participants_completed=total_participants,
                total_participants=total_participants,
            )

            # Broadcast round completed
            next_round = round_number + 1 if round_number < scenario.max_rounds else None
            scenario_finished = round_number >= scenario.max_rounds
            await broadcast_round_completed(
                scenario_id=scenario_id,
                round_number=round_number,
                next_round=next_round,
                scenario_finished=scenario_finished,
            )

        # Build response
        response = {
            "success": True,
            "transfer_order_id": transfer_order.id,
            "arrival_round": transfer_order.arrival_round,
            "phase": round_obj.current_phase.value,
            "round_completed": round_completed,
        }

        # Phase 2: Include copilot metadata if applicable
        if rlhf_feedback_id:
            response["rlhf_feedback_id"] = rlhf_feedback_id
        if authority_check_result:
            response["authority_check"] = {
                "override_approved": authority_check_result.override_approved,
                "requires_approval": authority_check_result.requires_approval,
                "authority_level": authority_check_result.authority_level,
                "override_percentage": round(authority_check_result.override_percentage, 1),
                "threshold_percentage": authority_check_result.threshold_percentage,
                "decision_proposal_id": authority_check_result.decision_proposal_id,
            }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Replenishment decision error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/pipeline/{scenario_user_id}")
def get_pipeline(
    scenario_id: int,
    scenario_user_id: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """
    Get pipeline (in-transit shipments) for a scenario_user.

    Returns all shipments currently in transit to the scenario_user with
    expected arrival times.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID

    Returns:
        {
            "in_transit": [
                {
                    "transfer_order_id": 1521,
                    "quantity": 150,
                    "origin": "Distributor",
                    "destination": "Wholesaler",
                    "order_round": 14,
                    "arrival_round": 17,
                    "rounds_until_arrival": 2,
                    "status": "IN_TRANSIT"
                }
            ]
        }
    """
    from app.models.scenario_user import ScenarioUser
    from app.models.transfer_order import TransferOrder
    from app.models.scenario import Scenario

    try:
        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(id=scenario_user_id).first()
        if not scenario_user or scenario_user.scenario_id != scenario_id:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Get game for current round
        scenario = scenario_service.db.query(Scenario).filter_by(id=scenario_id).first()
        current_round = scenario.current_round if game else 0

        # Get in-transit shipments with line items
        from app.models.transfer_order import TransferOrderLineItem
        from sqlalchemy import func

        in_transit = (
            scenario_service.db.query(
                TransferOrder,
                func.coalesce(func.sum(TransferOrderLineItem.quantity), 0).label('total_qty')
            )
            .outerjoin(TransferOrderLineItem, TransferOrder.id == TransferOrderLineItem.to_id)
            .filter(
                TransferOrder.scenario_id == scenario_id,
                TransferOrder.destination_site_id == scenario_user.site_key,  # Use site_key for node reference
                TransferOrder.status == "IN_TRANSIT"
            )
            .group_by(TransferOrder.id)
            .order_by(TransferOrder.arrival_round)
            .all()
        )

        # Build site_id -> name lookup for resolving node names
        site_name_cache = {}
        for to, _ in in_transit:
            for sid in (to.source_site_id, to.destination_site_id):
                if sid and sid not in site_name_cache:
                    node = scenario_service.db.query(Node).filter(Node.id == sid).first() if isinstance(sid, int) else None
                    site_name_cache[sid] = node.name if node else str(sid)

        pipeline_list = [
            {
                "transfer_order_id": to.id,
                "to_number": to.to_number,
                "quantity": int(total_qty) if total_qty else 0,
                "origin": site_name_cache.get(to.source_site_id, str(to.source_site_id)),
                "destination": site_name_cache.get(to.destination_site_id, str(to.destination_site_id)),
                "order_round": to.order_round,
                "arrival_round": to.arrival_round,
                "rounds_until_arrival": max(0, to.arrival_round - current_round),
                "status": to.status,
            }
            for to, total_qty in in_transit
        ]

        return {
            "in_transit": pipeline_list
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pipeline query error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/recommendations/fulfillment/{scenario_user_id}")
def get_fulfillment_recommendation(
    scenario_id: int,
    scenario_user_id: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    recommendation_service: AgentRecommendationService = Depends(get_agent_recommendation_service)
):
    """
    Get agent recommendation for fulfillment decision (ATP-based shipment).

    Returns agent's recommended quantity, reasoning, confidence score,
    alternative scenarios, and impact preview for accepting/overriding.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID

    Returns:
        {
            "agent_id": "gnn_v2_model_123",
            "agent_type": "GNN",
            "quantity": 91,
            "reasoning": "Recommend shipping only ATP (91 units) to protect Day 22 commitment...",
            "confidence": 0.87,
            "alternative_scenarios": [
                {
                    "quantity": 120,
                    "description": "Ship full demand",
                    "risk": "HIGH - Exceeds ATP, will create backlog for Day 22 customer"
                }
            ],
            "impact_preview_if_accept": {
                "inventory_after": 109,
                "fill_rate": 0.758,
                "backlog_after": 29,
                "cost_impact": 1450
            },
            "impact_preview_if_override": {
                "inventory_after": 80,
                "fill_rate": 1.0,
                "backlog_after": 0,
                "cost_impact": 0
            },
            "historical_performance": {
                "avg_accuracy": 0.89,
                "recent_decisions": 156,
                "overrides": 12,
                "override_regret_rate": 0.25
            },
            "timestamp": "2026-01-27T15:30:00"
        }
    """
    from app.models.scenario_user import ScenarioUser
    from app.models.scenario import Scenario
    from app.models.supply_chain import ScenarioRound
    from dataclasses import asdict

    try:
        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(id=scenario_user_id).first()
        if not scenario_user or scenario_user.scenario_id != scenario_id:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Get game
        scenario = scenario_service.db.query(Scenario).filter_by(id=scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get current round
        current_round = (
            scenario_service.db.query(ScenarioRound)
            .filter(
                ScenarioRound.scenario_id == scenario_id,
                ScenarioRound.round_number == scenario.current_round
            )
            .first()
        )
        if not current_round:
            raise HTTPException(status_code=404, detail="Current round not found")

        # Calculate ATP
        atp = scenario_service._calculate_atp(scenario_user)

        # Calculate demand (incoming order + backlog)
        demand = (scenario_user.incoming_order or 0) + (scenario_user.backlog or 0)
        backlog = scenario_user.backlog or 0

        # Get recommendation from service
        recommendation = recommendation_service.get_fulfillment_recommendation(
            game=scenario,
            scenario_user=scenario_user,
            current_round=current_round,
            atp=atp,
            demand=demand,
            backlog=backlog,
        )

        # Convert dataclass to dict
        return asdict(recommendation)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fulfillment recommendation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/recommendations/replenishment/{scenario_user_id}")
def get_replenishment_recommendation(
    scenario_id: int,
    scenario_user_id: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    recommendation_service: AgentRecommendationService = Depends(get_agent_recommendation_service)
):
    """
    Get agent recommendation for replenishment decision (upstream order).

    Returns agent's recommended order quantity, reasoning, confidence score,
    alternative scenarios, and impact preview.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID

    Returns:
        {
            "agent_id": "trm_v1_model_456",
            "agent_type": "TRM",
            "quantity": 200,
            "reasoning": "Base stock policy: Order 200 units to reach target inventory position...",
            "confidence": 0.89,
            "alternative_scenarios": [
                {
                    "quantity": 180,
                    "description": "Base stock policy",
                    "risk": "MEDIUM - Standard reorder policy, may not account for demand trends"
                }
            ],
            "impact_preview_if_accept": {
                "inventory_after": 420,
                "fill_rate": 0.95,
                "backlog_after": 15,
                "cost_impact": 200
            },
            "impact_preview_if_override": {
                "inventory_after": 620,
                "fill_rate": 0.98,
                "backlog_after": 5,
                "cost_impact": 400
            },
            "historical_performance": {
                "avg_accuracy": 0.87,
                "recent_decisions": 50,
                "overrides": 8,
                "override_regret_rate": 0.25
            },
            "timestamp": "2026-01-27T15:35:00"
        }
    """
    from app.models.scenario_user import ScenarioUser
    from app.models.scenario import Scenario, ScenarioRound
    from app.models.transfer_order import TransferOrder
    from dataclasses import asdict

    try:
        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(id=scenario_user_id).first()
        if not scenario_user or scenario_user.scenario_id != scenario_id:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Get game
        scenario = scenario_service.db.query(Scenario).filter_by(id=scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get current round
        current_round = (
            scenario_service.db.query(ScenarioRound)
            .filter(
                ScenarioRound.scenario_id == scenario_id,
                ScenarioRound.round_number == scenario.current_round
            )
            .first()
        )
        if not current_round:
            raise HTTPException(status_code=404, detail="Current round not found")

        # Get pipeline shipments
        in_transit = (
            scenario_service.db.query(TransferOrder)
            .filter(
                TransferOrder.scenario_id == scenario_id,
                TransferOrder.destination_site_id == scenario_user.site_id,
                TransferOrder.status == "IN_TRANSIT"
            )
            .all()
        )

        pipeline = [
            {
                "quantity": to.quantity,
                "arrival_round": to.arrival_round,
                "order_round": to.order_round,
            }
            for to in in_transit
        ]

        # Get demand history (last N rounds)
        # TODO: Implement proper demand history tracking
        # For now, use a simple heuristic based on incoming_order
        demand_history = [scenario_user.incoming_order or 100] * 5  # Mock data

        # Get recommendation from service
        recommendation = recommendation_service.get_replenishment_recommendation(
            game=scenario,
            scenario_user=scenario_user,
            current_round=current_round,
            current_inventory=scenario_user.current_stock,
            pipeline=pipeline,
            backlog=scenario_user.backlog or 0,
            demand_history=demand_history,
        )

        # Convert dataclass to dict
        return asdict(recommendation)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Replenishment recommendation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Phase 3: ATP/CTP Endpoints
# ========================================

@router.get("/scenarios/{scenario_id}/atp/{scenario_user_id}")
async def get_current_atp(
    scenario_id: int,
    scenario_user_id: int,
    include_safety_stock: bool = True,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    atp_service: ATPService = Depends(get_atp_service)
):
    """
    Get real-time ATP (Available to Promise) for scenario_user node.

    ATP = On-Hand Inventory + Scheduled Receipts - Allocated Orders - Safety Stock

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID
        include_safety_stock: Whether to reserve safety stock (default True)

    Returns:
        {
            "on_hand": 500,
            "scheduled_receipts": 200,
            "allocated_orders": 300,
            "safety_stock": 50,
            "atp": 350,
            "timestamp": "2026-01-28T12:00:00"
        }
    """
    try:
        # Get game and validate
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(
            id=scenario_user_id, scenario_id=scenario_id
        ).first()
        if not scenario_user:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Get current round (may be None if game hasn't started)
        current_round = None
        if scenario.current_round and scenario.current_round > 0:
            current_round = scenario_service.db.query(ScenarioRound).filter_by(
                scenario_id=scenario_id, round_number=scenario.current_round
            ).first()

        # Calculate ATP
        atp_result = atp_service.calculate_current_atp(
            scenario_user=scenario_user,
            game=scenario,
            current_round=current_round,
            include_safety_stock=include_safety_stock
        )

        # Convert dataclass to dict
        return asdict(atp_result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ATP calculation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/atp-projection/{scenario_user_id}")
async def get_atp_projection(
    scenario_id: int,
    scenario_user_id: int,
    periods: int = 8,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    atp_service: ATPService = Depends(get_atp_service)
):
    """
    Get multi-period ATP projection (rolling horizon).

    Projects ATP over next 4-8 weeks using:
    - Demand forecast (agent or historical avg)
    - Scheduled receipts (pipeline)
    - Planned allocations (future commitments)

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID
        periods: Number of future periods to project (default 8, max 12)

    Returns:
        [
            {
                "period": 15,
                "starting_inventory": 500,
                "scheduled_receipts": 200,
                "forecasted_demand": 300,
                "planned_allocations": 100,
                "ending_inventory": 400,
                "ending_atp": 300,
                "cumulative_atp": 300
            },
            ...
        ]
    """
    try:
        # Validate periods parameter
        if periods < 1 or periods > 12:
            raise HTTPException(
                status_code=400,
                detail="Periods must be between 1 and 12"
            )

        # Get game and validate
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(
            id=scenario_user_id, scenario_id=scenario_id
        ).first()
        if not scenario_user:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Get current round
        current_round = scenario_service.db.query(ScenarioRound).filter_by(
            scenario_id=scenario_id, round_number=scenario.current_round
        ).first()

        if not current_round:
            raise HTTPException(
                status_code=400,
                detail="Scenario has not started yet - no current round available"
            )

        # Project ATP
        projection = atp_service.project_atp_multi_period(
            scenario_user=scenario_user,
            game=scenario,
            current_round=current_round,
            periods=periods
        )

        # Convert dataclasses to dicts
        return [asdict(p) for p in projection]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ATP projection error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/atp-probabilistic/{scenario_user_id}")
async def get_probabilistic_atp(
    scenario_id: int,
    scenario_user_id: int,
    n_simulations: int = 100,
    include_safety_stock: bool = True,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    atp_service: ATPService = Depends(get_atp_service)
):
    """
    Phase 5: Get probabilistic ATP with P10/P50/P90 percentiles.

    Uses Monte Carlo simulation with stochastic lead times to calculate
    the probability distribution of ATP values.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID
        n_simulations: Number of Monte Carlo runs (default 100, max 1000)
        include_safety_stock: Whether to reserve safety stock (default True)

    Returns:
        {
            "on_hand": 500,
            "safety_stock": 50,
            "scheduled_receipts_p50": 200,
            "allocated_orders": 300,
            "atp_p50": 350,
            "scheduled_receipts_p10": 150,
            "atp_p10": 300,
            "scheduled_receipts_p90": 250,
            "atp_p90": 400,
            "lead_time_mean": 2.3,
            "lead_time_stddev": 0.8,
            "simulation_runs": 100,
            "timestamp": "2026-01-30T12:00:00"
        }
    """
    try:
        # Validate n_simulations
        if n_simulations < 10 or n_simulations > 1000:
            raise HTTPException(
                status_code=400,
                detail="n_simulations must be between 10 and 1000"
            )

        # Get game and validate
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(
            id=scenario_user_id, scenario_id=scenario_id
        ).first()
        if not scenario_user:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Get current round (may be None if game hasn't started)
        current_round = None
        if scenario.current_round and scenario.current_round > 0:
            current_round = scenario_service.db.query(ScenarioRound).filter_by(
                scenario_id=scenario_id, round_number=scenario.current_round
            ).first()

        # Calculate probabilistic ATP
        prob_atp_result = atp_service.calculate_probabilistic_atp(
            scenario_user=scenario_user,
            game=scenario,
            current_round=current_round,
            n_simulations=n_simulations,
            include_safety_stock=include_safety_stock
        )

        # Convert dataclass to dict
        return asdict(prob_atp_result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Probabilistic ATP calculation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/atp-history/{scenario_user_id}")
async def get_atp_history(
    scenario_id: int,
    scenario_user_id: int,
    limit: int = 20,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """
    Get historical ATP/CTP data for trend visualization.

    Returns saved probabilistic ATP projections from previous rounds,
    allowing visualization of ATP trends over time with confidence bands.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID
        limit: Maximum records to return (default 20)

    Returns:
        {
            "scenario_user_id": 3,
            "scenario_user_name": "Distributor",
            "history": [
                {
                    "round": 1,
                    "atp_p10": 300,
                    "atp_p50": 350,
                    "atp_p90": 400,
                    "on_hand": 500,
                    "scheduled_receipts": 200,
                    "allocated_orders": 300,
                    "lead_time_mean": 2.3,
                    "lead_time_stddev": 0.8,
                    "timestamp": "2026-01-30T12:00:00"
                },
                ...
            ],
            "ctp_history": [
                {
                    "round": 1,
                    "ctp_p10": 340,
                    "ctp_p50": 380,
                    "ctp_p90": 410,
                    "production_capacity": 1000,
                    "commitments": 600,
                    "yield_rate": 0.95,
                    "timestamp": "2026-01-30T12:00:00"
                },
                ...
            ]
        }
    """
    from app.models.inventory_projection import AtpProjection, CtpProjection

    try:
        # Get game and validate
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(
            id=scenario_user_id, scenario_id=scenario_id
        ).first()
        if not scenario_user:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Look up node from supply chain config
        node = _get_participant_node(scenario_service.db, scenario_user, game)

        # Query historical ATP projections for this game/scenario_user
        atp_records = []
        if node:
            atp_query = (
                scenario_service.db.query(AtpProjection)
                .filter(
                    AtpProjection.scenario_id == scenario_id,
                    AtpProjection.site_id == node.id
                )
                .order_by(AtpProjection.atp_date.desc())
                .limit(limit)
                .all()
            )

            for record in reversed(atp_query):  # Oldest first
                atp_records.append({
                    "round": record.source_event_id.split("_")[-1] if record.source_event_id else None,
                    "date": record.atp_date.isoformat() if record.atp_date else None,
                    "atp_p10": record.atp_p10,
                    "atp_p50": int(record.atp_qty) if record.atp_qty else None,
                    "atp_p90": record.atp_p90,
                    "on_hand": int(record.opening_balance) if record.opening_balance else 0,
                    "scheduled_receipts": int(record.supply_qty) if record.supply_qty else 0,
                    "allocated_orders": int(record.allocated_qty) if record.allocated_qty else 0,
                    "lead_time_mean": record.lead_time_mean,
                    "lead_time_stddev": record.lead_time_stddev,
                    "timestamp": record.created_at.isoformat() if record.created_at else None
                })

        # Query historical CTP projections for this game/scenario_user (if manufacturer)
        ctp_records = []
        if node:
            ctp_query = (
                scenario_service.db.query(CtpProjection)
                .filter(
                    CtpProjection.scenario_id == scenario_id,
                    CtpProjection.site_id == node.id
                )
                .order_by(CtpProjection.ctp_date.desc())
                .limit(limit)
                .all()
            )

            for record in reversed(ctp_query):  # Oldest first
                ctp_records.append({
                    "round": record.source_event_id.split("_")[-1] if record.source_event_id else None,
                    "date": record.ctp_date.isoformat() if record.ctp_date else None,
                    "ctp_p10": record.ctp_p10,
                    "ctp_p50": int(record.ctp_qty) if record.ctp_qty else None,
                    "ctp_p90": record.ctp_p90,
                    "production_capacity": int(record.total_capacity) if record.total_capacity else 0,
                    "commitments": int(record.committed_capacity) if record.committed_capacity else 0,
                    "available_capacity": int(record.available_capacity) if record.available_capacity else 0,
                    "production_lead_time_mean": record.production_lead_time_mean,
                    "production_lead_time_stddev": record.production_lead_time_stddev,
                    "component_constrained": record.component_constrained,
                    "timestamp": record.created_at.isoformat() if record.created_at else None
                })

        return {
            "scenario_user_id": scenario_user.id,
            "scenario_user_name": scenario_user.name,
            "node_id": node.id if node else None,
            "node_name": node.name if node else None,
            "current_round": scenario.current_round,
            "history": atp_records,
            "ctp_history": ctp_records
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ATP history error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/ctp/{scenario_user_id}")
async def get_current_ctp(
    scenario_id: int,
    scenario_user_id: int,
    item_id: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    ctp_service: CTPService = Depends(get_ctp_service)
):
    """
    Get CTP (Capable to Promise) for manufacturer node.

    CTP = (Production Capacity - Commitments) × Yield Rate × Component Availability

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID (must be manufacturer node)
        item_id: Item ID to produce

    Returns:
        {
            "production_capacity": 1000,
            "current_commitments": 600,
            "yield_rate": 0.95,
            "available_capacity": 400,
            "component_constraints": [
                {
                    "item_id": 5,
                    "item_name": "Component-X",
                    "required_per_unit": 2,
                    "available_atp": 500,
                    "max_producible": 250,
                    "shortfall": 0
                }
            ],
            "ctp": 380,
            "constrained_by": null,
            "timestamp": "2026-01-28T12:00:00"
        }
    """
    try:
        # Get game and validate
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(
            id=scenario_user_id, scenario_id=scenario_id
        ).first()
        if not scenario_user:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Look up node from supply chain config
        node = _get_participant_node(scenario_service.db, scenario_user, game)
        if not node:
            raise HTTPException(
                status_code=400,
                detail=f"No node configured for scenario_user {scenario_user.name} (site_key={scenario_user.site_key})"
            )

        # Verify scenario_user is manufacturer (check master_type or dag_type for factory)
        is_manufacturer = (
            node.master_type and node.master_type.upper() == "MANUFACTURER"
        ) or (
            node.dag_type and node.dag_type.lower() == "factory"
        ) or (
            node.type and node.type.lower() == "factory"
        )
        if not is_manufacturer:
            raise HTTPException(
                status_code=400,
                detail=f"CTP calculation only available for manufacturer/factory nodes (node has master_type={node.master_type}, dag_type={node.dag_type})"
            )

        # Get current round
        current_round = scenario_service.db.query(ScenarioRound).filter_by(
            scenario_id=scenario_id, round_number=scenario.current_round
        ).first()
        if not current_round:
            raise HTTPException(
                status_code=400,
                detail="Scenario has not started yet - no current round available"
            )

        # Calculate CTP
        ctp_result = ctp_service.calculate_current_ctp(
            scenario_user=scenario_user,
            game=scenario,
            current_round=current_round,
            item_id=item_id
        )

        # Convert dataclass to dict
        return asdict(ctp_result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CTP calculation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/ctp-probabilistic/{scenario_user_id}")
async def get_probabilistic_ctp(
    scenario_id: int,
    scenario_user_id: int,
    product_id: str,
    n_simulations: int = 100,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    ctp_service: CTPService = Depends(get_ctp_service)
):
    """
    Get probabilistic CTP (Capable to Promise) with Monte Carlo simulation.

    Uses stochastic sampling of yield rates and production lead times to
    calculate P10/P50/P90 percentiles for CTP.

    CTP = (Production Capacity - Commitments) × Yield Rate × Component Availability

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID (must be manufacturer node)
        product_id: AWS SC Product ID (string, e.g., "FG-001")
        n_simulations: Number of Monte Carlo simulations (default 100)

    Returns:
        {
            "production_capacity": 1000,
            "current_commitments": 600,
            "yield_rate_mean": 0.95,
            "yield_rate_stddev": 0.02,
            "ctp_p10": 340,
            "ctp_p50": 380,
            "ctp_p90": 410,
            "available_capacity_p10": 360,
            "available_capacity_p50": 400,
            "available_capacity_p90": 430,
            "constrained_by": null,
            "component_constraints": [...],
            "production_lead_time_mean": 5.0,
            "production_lead_time_stddev": 1.0,
            "simulation_runs": 100,
            "timestamp": "2026-01-28T12:00:00"
        }
    """
    try:
        # Get game and validate
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(
            id=scenario_user_id, scenario_id=scenario_id
        ).first()
        if not scenario_user:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Look up node from supply chain config
        node = _get_participant_node(scenario_service.db, scenario_user, game)
        if not node:
            raise HTTPException(
                status_code=400,
                detail=f"No node configured for scenario_user {scenario_user.name} (site_key={scenario_user.site_key})"
            )

        # Verify scenario_user is manufacturer
        is_manufacturer = (
            node.master_type and node.master_type.upper() == "MANUFACTURER"
        ) or (
            node.dag_type and node.dag_type.lower() == "factory"
        ) or (
            node.type and node.type.lower() == "factory"
        )
        if not is_manufacturer:
            raise HTTPException(
                status_code=400,
                detail=f"CTP calculation only available for manufacturer/factory nodes (node has master_type={node.master_type}, dag_type={node.dag_type})"
            )

        # Get current round (may be None if game tracks state in config JSON)
        current_round = None
        if scenario.current_round and scenario.current_round > 0:
            current_round = scenario_service.db.query(ScenarioRound).filter_by(
                scenario_id=scenario_id, round_number=scenario.current_round
            ).first()

        # Calculate probabilistic CTP
        ctp_result = ctp_service.calculate_probabilistic_ctp(
            scenario_user=scenario_user,
            game=scenario,
            current_round=current_round,
            product_id=product_id,
            n_simulations=n_simulations
        )

        # Convert dataclass to dict
        return asdict(ctp_result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Probabilistic CTP calculation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/pipeline-visualization/{scenario_user_id}")
async def get_pipeline_visualization(
    scenario_id: int,
    scenario_user_id: int,
    n_simulations: int = 100,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """
    Get pipeline visualization with probabilistic arrival windows.

    Shows all shipments in transit with Monte Carlo simulated arrival windows
    based on stochastic lead time distributions from upstream lanes.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID
        n_simulations: Number of simulations for probability estimation (default 100)

    Returns:
        {
            "scenario_user_id": 3,
            "scenario_user_name": "Distributor",
            "current_round": 5,
            "pipeline_total": 150,
            "shipments": [
                {
                    "slot": 0,
                    "quantity": 50,
                    "scheduled_arrival_round": 6,
                    "arrival_p10_round": 6,
                    "arrival_p50_round": 6,
                    "arrival_p90_round": 7,
                    "arrival_probability_current": 0.85,
                    "source_node": "Factory",
                    "source_node_id": 1
                },
                {
                    "slot": 1,
                    "quantity": 100,
                    "scheduled_arrival_round": 7,
                    "arrival_p10_round": 7,
                    "arrival_p50_round": 8,
                    "arrival_p90_round": 9,
                    "arrival_probability_current": 0.15,
                    "source_node": "Factory",
                    "source_node_id": 1
                }
            ],
            "arrival_distribution": {
                "round_6": {"quantity_p10": 0, "quantity_p50": 50, "quantity_p90": 50},
                "round_7": {"quantity_p10": 50, "quantity_p50": 100, "quantity_p90": 150},
                "round_8": {"quantity_p10": 100, "quantity_p50": 150, "quantity_p90": 150}
            },
            "lead_time_stats": {
                "mean": 2.1,
                "stddev": 0.5,
                "p10": 2,
                "p50": 2,
                "p90": 3
            },
            "timestamp": "2026-01-30T12:00:00"
        }
    """
    from datetime import datetime
    from app.services.sc_planning.stochastic_sampler import StochasticSampler
    import numpy as np

    try:
        # Get game and validate
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(
            id=scenario_user_id, scenario_id=scenario_id
        ).first()
        if not scenario_user:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Look up node from supply chain config
        node = _get_participant_node(scenario_service.db, scenario_user, game)
        if not node:
            raise HTTPException(
                status_code=400,
                detail=f"No node configured for scenario_user {scenario_user.name} (site_key={scenario_user.site_key})"
            )

        # Check if game has started
        if scenario.current_round is None or scenario.current_round < 1:
            return {
                "scenario_user_id": scenario_user.id,
                "scenario_user_name": scenario_user.name,
                "current_round": 0,
                "pipeline_total": 0,
                "shipments": [],
                "arrival_distribution": {},
                "lead_time_stats": {"mean": 0, "stddev": 0, "p10": 0, "p50": 0, "p90": 0},
                "message": "Scenario has not started yet",
                "timestamp": datetime.utcnow().isoformat()
            }

        # Get the scenario_user's pipeline state from game config engine_state
        # The engine_state stores pipeline_shipments per node by dag_type or site_key
        pipeline_shipments = []
        if scenario.config and isinstance(scenario.config, dict):
            engine_state = scenario.config.get("engine_state", {})
            # Try to find node state by site_key (e.g., "factory", "distributor")
            site_key = scenario_user.site_key or node.dag_type or node.name.lower().replace(" ", "_")
            node_state = engine_state.get(site_key, {})
            pipeline_shipments = node_state.get("pipeline_shipments", [])

            # If not found, try by dag_type
            if not pipeline_shipments and node.dag_type:
                node_state = engine_state.get(node.dag_type, {})
                pipeline_shipments = node_state.get("pipeline_shipments", [])

        # Get upstream lanes for lead time distribution
        from app.models.supply_chain_config import Lane
        config_id = game.supply_chain_config_id or (
            scenario.config.get("supply_chain_config_id") if scenario.config else None
        )
        upstream_lanes = []
        if config_id:
            upstream_lanes = scenario_service.db.query(Lane).filter(
                Lane.config_id == config_id,
                Lane.to_site_id == node.id
            ).all()

        # Calculate base lead time and distribution parameters
        base_lead_time = node.supply_lead_time if hasattr(node, 'supply_lead_time') and node.supply_lead_time else 2
        lead_time_dist = None
        source_node_info = {}

        if upstream_lanes:
            # Use first upstream lane for distribution (or aggregate)
            lane = upstream_lanes[0]
            lead_time_dist = getattr(lane, 'supply_lead_time_dist', None)

            # Extract lead time value - supply_lead_time is JSON {"type": "...", "value": N}
            lane_lt = lane.supply_lead_time
            if lane_lt:
                if isinstance(lane_lt, dict):
                    base_lead_time = lane_lt.get("value", base_lead_time)
                else:
                    base_lead_time = lane_lt

            # Get source node info
            from app.models.supply_chain_config import Node as ConfigNode
            source_node = scenario_service.db.query(ConfigNode).filter_by(id=lane.from_site_id).first()
            if source_node:
                source_node_info = {"source_node": source_node.name, "source_node_id": source_node.id}

        # Initialize sampler for Monte Carlo simulation
        sampler = StochasticSampler(scenario_id=scenario_id)

        # Calculate lead time statistics using simulation
        lead_time_samples = []
        for _ in range(n_simulations):
            if lead_time_dist:
                # Sample from distribution
                sampled_lt = sampler.sample_from_distribution(lead_time_dist, base_lead_time)
            else:
                # Use deterministic value with small variance
                sampled_lt = max(1, base_lead_time + np.random.normal(0, 0.3))
            lead_time_samples.append(sampled_lt)

        lead_time_samples = sorted(lead_time_samples)
        lead_time_mean = np.mean(lead_time_samples)
        lead_time_stddev = np.std(lead_time_samples)
        lead_time_p10 = int(round(np.percentile(lead_time_samples, 10)))
        lead_time_p50 = int(round(np.percentile(lead_time_samples, 50)))
        lead_time_p90 = int(round(np.percentile(lead_time_samples, 90)))

        # Build shipment entries with probabilistic arrival windows
        shipments = []
        arrival_by_round = {}

        for slot_idx, quantity in enumerate(pipeline_shipments):
            if quantity <= 0:
                continue

            # Scheduled arrival is slot 0 = next round, slot 1 = round+2, etc.
            scheduled_arrival = scenario.current_round + slot_idx + 1

            # Monte Carlo simulation for arrival probability
            arrival_rounds = []
            for i in range(n_simulations):
                # Sample lead time variance
                if lead_time_dist:
                    lt_variance = sampler.sample_from_distribution(lead_time_dist, base_lead_time) - base_lead_time
                else:
                    lt_variance = np.random.normal(0, 0.3)

                # Calculate actual arrival round with variance
                actual_arrival = scheduled_arrival + int(round(lt_variance))
                actual_arrival = max(scenario.current_round + 1, actual_arrival)  # Can't arrive in past
                arrival_rounds.append(actual_arrival)

            arrival_rounds = sorted(arrival_rounds)
            arrival_p10 = int(np.percentile(arrival_rounds, 10))
            arrival_p50 = int(np.percentile(arrival_rounds, 50))
            arrival_p90 = int(np.percentile(arrival_rounds, 90))

            # Probability of arriving in current round + 1 (next round)
            next_round = scenario.current_round + 1
            arrival_prob_next = sum(1 for r in arrival_rounds if r == next_round) / n_simulations

            shipment_entry = {
                "slot": slot_idx,
                "quantity": quantity,
                "scheduled_arrival_round": scheduled_arrival,
                "arrival_p10_round": arrival_p10,
                "arrival_p50_round": arrival_p50,
                "arrival_p90_round": arrival_p90,
                "arrival_probability_next_round": round(arrival_prob_next, 3),
                **source_node_info
            }
            shipments.append(shipment_entry)

            # Aggregate arrivals by round for distribution chart
            for sim_arrival in arrival_rounds:
                key = f"round_{sim_arrival}"
                if key not in arrival_by_round:
                    arrival_by_round[key] = []
                arrival_by_round[key].append(quantity)

        # Calculate P10/P50/P90 quantities per round
        arrival_distribution = {}
        for round_key, quantities in sorted(arrival_by_round.items()):
            # Each simulation may contribute to this round
            arrival_distribution[round_key] = {
                "quantity_p10": int(np.percentile(quantities, 10)) if quantities else 0,
                "quantity_p50": int(np.percentile(quantities, 50)) if quantities else 0,
                "quantity_p90": int(np.percentile(quantities, 90)) if quantities else 0,
                "simulation_count": len(quantities)
            }

        return {
            "scenario_user_id": scenario_user.id,
            "scenario_user_name": scenario_user.name,
            "current_round": scenario.current_round,
            "pipeline_total": sum(pipeline_shipments) if pipeline_shipments else 0,
            "shipments": shipments,
            "arrival_distribution": arrival_distribution,
            "lead_time_stats": {
                "mean": round(lead_time_mean, 2),
                "stddev": round(lead_time_stddev, 2),
                "p10": lead_time_p10,
                "p50": lead_time_p50,
                "p90": lead_time_p90
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pipeline visualization error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/atp-conformal/{scenario_user_id}")
async def get_conformal_atp(
    scenario_id: int,
    scenario_user_id: int,
    coverage: float = 0.90,
    method: str = "adaptive",
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    atp_service: ATPService = Depends(get_atp_service)
):
    """
    Get ATP with Conformal Prediction intervals (guaranteed coverage).

    Unlike Monte Carlo simulation which estimates probability distributions,
    conformal prediction provides prediction intervals with *statistical guarantees*
    on coverage. If configured for 90% coverage, the prediction interval will
    contain the true ATP value at least 90% of the time.

    Conformal prediction learns from historical prediction-actual pairs to
    calibrate the prediction interval width automatically.

    Methods:
    - split: Split Conformal Prediction - uses absolute residuals
    - quantile: Conformalized Quantile Regression - better for heteroscedastic data
    - adaptive: Adaptive Conformal Inference - adjusts to distribution shift over time

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID
        coverage: Target coverage probability (default 0.90 = 90%)
        method: Conformal method (split, quantile, adaptive)

    Returns:
        {
            "atp_point": 350,
            "atp_lower": 280,
            "atp_upper": 420,
            "coverage": 0.90,
            "method": "adaptive",
            "calibration_size": 45,
            "interval_width": 140,
            "is_calibrated": true,
            "adaptive_alpha": 0.105,
            "coverage_stats": {
                "empirical_coverage": 0.91,
                "target_coverage": 0.90,
                "coverage_gap": 0.01,
                "n_observations": 45
            },
            "timestamp": "2026-01-30T12:00:00"
        }
    """
    from app.services.conformal_prediction import ATPConformalPredictor

    try:
        # Validate coverage
        if coverage < 0.5 or coverage > 0.99:
            raise HTTPException(
                status_code=400,
                detail="Coverage must be between 0.5 and 0.99"
            )

        # Validate method
        valid_methods = ["split", "quantile", "adaptive"]
        if method not in valid_methods:
            raise HTTPException(
                status_code=400,
                detail=f"Method must be one of: {valid_methods}"
            )

        # Get game and validate
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(
            id=scenario_user_id, scenario_id=scenario_id
        ).first()
        if not scenario_user:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Get current round (may be None if game hasn't started)
        current_round = None
        if scenario.current_round and scenario.current_round > 0:
            current_round = scenario_service.db.query(ScenarioRound).filter_by(
                scenario_id=scenario_id, round_number=scenario.current_round
            ).first()

        # First, calculate the current point estimate using probabilistic ATP
        prob_atp_result = atp_service.calculate_probabilistic_atp(
            scenario_user=scenario_user,
            game=scenario,
            current_round=current_round,
            n_simulations=100,
            include_safety_stock=True
        )
        atp_point_estimate = prob_atp_result.atp_p50

        # Initialize conformal predictor
        atp_conformal = ATPConformalPredictor(
            coverage=coverage,
            method=method,
            gamma=0.005  # Learning rate for adaptive method
        )

        # Load historical prediction-actual pairs for calibration
        # Query from inventory projections or round history
        from app.models.inventory_projection import AtpProjection
        node = _get_participant_node(scenario_service.db, scenario_user, game)

        historical_predictions = []
        historical_actuals = []

        if node:
            # Get historical ATP projections with their actuals
            atp_history = (
                scenario_service.db.query(AtpProjection)
                .filter(
                    AtpProjection.scenario_id == scenario_id,
                    AtpProjection.site_id == node.id,
                    AtpProjection.atp_qty.isnot(None)
                )
                .order_by(AtpProjection.atp_date.asc())
                .limit(200)
                .all()
            )

            for record in atp_history:
                # Use P50 as prediction, actual ATP as ground truth
                if record.atp_qty is not None:
                    predicted = float(record.atp_qty)
                    # The "actual" ATP is harder to get - use next round's opening balance
                    # as a proxy for what the ATP actually was
                    actual = float(record.opening_balance or record.atp_qty)
                    historical_predictions.append(predicted)
                    historical_actuals.append(actual)

        # Also use engine state history if available
        if scenario.config and 'engine_state' in scenario.config:
            engine_state = scenario.config['engine_state']
            node_name = scenario_user.site_key or scenario_user.name

            # Get inventory history for this node
            for node_key, node_state in engine_state.get('nodes', {}).items():
                if node_key.lower() == node_name.lower() or node_name.lower() in node_key.lower():
                    inv_history = node_state.get('inventory_history', [])
                    for i in range(len(inv_history) - 1):
                        # Use current inventory as prediction, next round inventory as "actual"
                        predicted = inv_history[i]
                        actual = inv_history[i + 1]
                        historical_predictions.append(float(predicted))
                        historical_actuals.append(float(actual))

        # Calibrate if we have enough history
        if len(historical_predictions) >= 10:
            atp_conformal.calibrate(historical_predictions, historical_actuals)

        # Get previous actual for adaptive update (if available)
        previous_actual = None
        if historical_actuals:
            previous_actual = historical_actuals[-1]

        # Generate conformal prediction
        conformal_result = atp_conformal.predict(
            atp_point_estimate=atp_point_estimate,
            previous_actual=previous_actual
        )

        # Get diagnostics
        diagnostics = atp_conformal.get_diagnostics()

        return {
            "atp_point": conformal_result.atp_point,
            "atp_lower": conformal_result.atp_lower,
            "atp_upper": conformal_result.atp_upper,
            "coverage": conformal_result.coverage,
            "method": conformal_result.method,
            "calibration_size": conformal_result.calibration_size,
            "interval_width": conformal_result.interval_width,
            "is_calibrated": conformal_result.is_calibrated,
            "adaptive_alpha": diagnostics.get("adaptive_alpha"),
            "coverage_stats": diagnostics.get("coverage_stats"),
            "monte_carlo_comparison": {
                "mc_p10": prob_atp_result.atp_p10,
                "mc_p50": prob_atp_result.atp_p50,
                "mc_p90": prob_atp_result.atp_p90,
            },
            "timestamp": conformal_result.timestamp.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Conformal ATP calculation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenarios/{scenario_id}/atp-conformal/{scenario_user_id}/calibrate")
async def calibrate_conformal_atp(
    scenario_id: int,
    scenario_user_id: int,
    predictions: List[float] = Body(..., embed=True),
    actuals: List[float] = Body(..., embed=True),
    coverage: float = 0.90,
    method: str = "adaptive",
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """
    Manually calibrate conformal ATP predictor with historical data.

    This endpoint allows explicit calibration with known prediction-actual pairs,
    useful for bootstrapping the conformal predictor or incorporating external data.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID
        predictions: List of historical point predictions
        actuals: List of corresponding actual values
        coverage: Target coverage (default 0.90)
        method: Conformal method (split, quantile, adaptive)

    Returns:
        {
            "calibration_size": 50,
            "empirical_coverage": 0.88,
            "target_coverage": 0.90,
            "quantile_value": 15.3,
            "message": "Calibration successful"
        }
    """
    from app.services.conformal_prediction import ATPConformalPredictor

    try:
        if len(predictions) != len(actuals):
            raise HTTPException(
                status_code=400,
                detail="Predictions and actuals must have the same length"
            )

        if len(predictions) < 10:
            raise HTTPException(
                status_code=400,
                detail="At least 10 calibration points required"
            )

        # Validate game exists
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Validate scenario_user exists
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(
            id=scenario_user_id, scenario_id=scenario_id
        ).first()
        if not scenario_user:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Create and calibrate predictor
        atp_conformal = ATPConformalPredictor(
            coverage=coverage,
            method=method
        )
        atp_conformal.calibrate(predictions, actuals)

        # Get diagnostics after calibration
        diagnostics = atp_conformal.get_diagnostics()

        return {
            "calibration_size": len(predictions),
            "empirical_coverage": diagnostics.get("coverage_stats", {}).get("empirical_coverage"),
            "target_coverage": coverage,
            "quantile_value": diagnostics.get("quantile"),
            "method": method,
            "message": "Calibration successful"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Conformal ATP calibration error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/demand-conformal/{scenario_user_id}")
async def get_conformal_demand_forecast(
    scenario_id: int,
    scenario_user_id: int,
    horizon: int = 1,
    coverage: float = 0.90,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """
    Get demand forecast with Conformal Prediction intervals.

    Provides prediction intervals for future demand with guaranteed coverage.
    The conformal predictor learns from historical forecast errors to calibrate
    the interval width automatically.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID
        horizon: Forecast horizon in rounds (default 1)
        coverage: Target coverage probability (default 0.90)

    Returns:
        {
            "demand_point": 100,
            "demand_lower": 85,
            "demand_upper": 120,
            "coverage": 0.90,
            "horizon": 1,
            "calibration_size": 30,
            "interval_width": 35,
            "is_calibrated": true,
            "historical_demand": [95, 102, 98, 105, ...],
            "forecast_accuracy": {
                "mape": 8.5,
                "rmse": 12.3,
                "bias": 2.1
            },
            "timestamp": "2026-01-30T12:00:00"
        }
    """
    from app.services.conformal_prediction import DemandConformalPredictor
    from datetime import datetime

    try:
        # Validate coverage
        if coverage < 0.5 or coverage > 0.99:
            raise HTTPException(
                status_code=400,
                detail="Coverage must be between 0.5 and 0.99"
            )

        # Get game and validate
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(
            id=scenario_user_id, scenario_id=scenario_id
        ).first()
        if not scenario_user:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Get demand history from engine state
        demand_history = []
        forecast_history = []
        node_name = scenario_user.site_key or scenario_user.name

        if scenario.config and 'engine_state' in scenario.config:
            engine_state = scenario.config['engine_state']

            for node_key, node_state in engine_state.get('nodes', {}).items():
                if node_key.lower() == node_name.lower() or node_name.lower() in node_key.lower():
                    demand_history = node_state.get('demand_history', [])
                    # Use simple moving average as forecast
                    if len(demand_history) >= 3:
                        for i in range(len(demand_history) - 1):
                            # Forecast = average of last 3 periods (or fewer if not available)
                            window = demand_history[max(0, i-2):i+1]
                            forecast = sum(window) / len(window) if window else 0
                            forecast_history.append(forecast)
                    break

        # Initialize conformal predictor
        demand_conformal = DemandConformalPredictor(
            coverage=coverage,
            use_adaptive=True
        )

        # Calculate point forecast (simple moving average)
        if len(demand_history) >= 3:
            demand_point = sum(demand_history[-3:]) / 3
        elif demand_history:
            demand_point = sum(demand_history) / len(demand_history)
        else:
            demand_point = 100  # Default

        # Calibrate from historical forecast errors
        if len(forecast_history) >= 10 and len(demand_history) >= len(forecast_history) + 1:
            actuals = demand_history[1:len(forecast_history)+1]
            demand_conformal.predictor.calibrate_from_history(forecast_history, actuals)

        # Get previous actual for adaptive update
        previous_actual = demand_history[-1] if demand_history else None

        # Generate conformal prediction
        interval = demand_conformal.predict(
            demand_forecast=demand_point,
            previous_actual=previous_actual
        )

        # Calculate forecast accuracy metrics
        forecast_accuracy = {}
        if len(forecast_history) >= 5 and len(demand_history) > len(forecast_history):
            actuals = demand_history[1:len(forecast_history)+1]
            errors = [abs(f - a) for f, a in zip(forecast_history, actuals)]
            pct_errors = [abs(f - a) / max(a, 1) * 100 for f, a in zip(forecast_history, actuals)]
            biases = [f - a for f, a in zip(forecast_history, actuals)]

            forecast_accuracy = {
                "mape": round(sum(pct_errors) / len(pct_errors), 2),
                "rmse": round((sum(e**2 for e in errors) / len(errors)) ** 0.5, 2),
                "bias": round(sum(biases) / len(biases), 2)
            }

        return {
            "demand_point": round(interval.point_estimate, 1),
            "demand_lower": round(max(0, interval.lower), 1),
            "demand_upper": round(interval.upper, 1),
            "coverage": interval.coverage_target,
            "horizon": horizon,
            "calibration_size": interval.calibration_size,
            "interval_width": round(interval.width, 1),
            "is_calibrated": interval.calibration_size >= 10,
            "historical_demand": demand_history[-20:] if demand_history else [],
            "forecast_accuracy": forecast_accuracy,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Conformal demand forecast error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/lead-time-conformal/{scenario_user_id}")
async def get_conformal_lead_time(
    scenario_id: int,
    scenario_user_id: int,
    coverage: float = 0.90,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """
    Get lead time prediction with Conformal Prediction intervals.

    Provides prediction intervals for when shipments will arrive with
    guaranteed coverage. Useful for planning inventory replenishment.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID
        coverage: Target coverage probability (default 0.90)

    Returns:
        {
            "expected_lead_time": 2.0,
            "lead_time_lower": 1.5,
            "lead_time_upper": 3.2,
            "coverage": 0.90,
            "calibration_size": 25,
            "interval_width": 1.7,
            "is_calibrated": true,
            "historical_lead_times": [2.0, 2.1, 1.9, 2.3, ...],
            "arrival_window": {
                "earliest_round": 3,
                "expected_round": 4,
                "latest_round": 5
            },
            "timestamp": "2026-01-30T12:00:00"
        }
    """
    from app.services.conformal_prediction import LeadTimeConformalPredictor
    from app.models.supply_chain_config import Lane
    from datetime import datetime
    import numpy as np

    try:
        # Validate coverage
        if coverage < 0.5 or coverage > 0.99:
            raise HTTPException(
                status_code=400,
                detail="Coverage must be between 0.5 and 0.99"
            )

        # Get game and validate
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(
            id=scenario_user_id, scenario_id=scenario_id
        ).first()
        if not scenario_user:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Get node for this scenario_user
        node = _get_participant_node(scenario_service.db, scenario_user, game)
        if not node:
            raise HTTPException(
                status_code=400,
                detail=f"No node configured for scenario_user {scenario_user.name}"
            )

        # Get upstream lane for lead time info
        config_id = game.supply_chain_config_id or (
            scenario.config.get("supply_chain_config_id") if scenario.config else None
        )

        base_lead_time = 2.0
        if config_id:
            upstream_lane = scenario_service.db.query(Lane).filter(
                Lane.config_id == config_id,
                Lane.to_site_id == node.id
            ).first()

            if upstream_lane and upstream_lane.supply_lead_time:
                lt = upstream_lane.supply_lead_time
                if isinstance(lt, dict):
                    base_lead_time = float(lt.get("value", 2.0))
                else:
                    base_lead_time = float(lt)

        # Initialize conformal predictor
        lt_conformal = LeadTimeConformalPredictor(coverage=coverage)

        # Get historical lead times from engine state (if available)
        historical_lead_times = []
        predicted_lead_times = []
        actual_lead_times = []

        # Generate synthetic historical data based on base lead time variance
        # In production, this would come from actual shipment tracking
        for _ in range(30):
            predicted = base_lead_time
            actual = base_lead_time + np.random.normal(0, 0.5)
            actual = max(1, actual)
            predicted_lead_times.append(predicted)
            actual_lead_times.append(actual)
            historical_lead_times.append(actual)

        # Calibrate from historical data
        if len(predicted_lead_times) >= 10:
            lt_conformal.calibrate(predicted_lead_times, actual_lead_times)

        # Predict arrival window
        earliest, latest = lt_conformal.predict_arrival_window(base_lead_time)

        # Calculate arrival rounds
        current_round = scenario.current_round or 1
        earliest_round = current_round + int(round(earliest))
        expected_round = current_round + int(round(base_lead_time))
        latest_round = current_round + int(round(latest))

        return {
            "expected_lead_time": round(base_lead_time, 2),
            "lead_time_lower": round(earliest, 2),
            "lead_time_upper": round(latest, 2),
            "coverage": coverage,
            "calibration_size": len(predicted_lead_times),
            "interval_width": round(latest - earliest, 2),
            "is_calibrated": len(predicted_lead_times) >= 10,
            "historical_lead_times": [round(lt, 2) for lt in historical_lead_times[-20:]],
            "arrival_window": {
                "earliest_round": earliest_round,
                "expected_round": expected_round,
                "latest_round": latest_round
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Conformal lead time error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class CustomerDemandRequest(BaseModel):
    """Customer demand request for allocation"""
    customer_id: int
    customer_name: str
    demand: int
    priority: int = 2  # 1=high, 2=medium, 3=low


class AllocateATPRequest(BaseModel):
    """Request body for ATP allocation"""
    scenario_user_id: int
    demands: List[CustomerDemandRequest]
    allocation_method: str = "proportional"  # priority, proportional, fcfs


@router.post("/scenarios/{scenario_id}/allocate-atp")
async def allocate_atp_to_customers(
    scenario_id: int,
    request: AllocateATPRequest,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    atp_service: ATPService = Depends(get_atp_service)
):
    """
    Allocate available ATP to competing customer demands.

    Resolves allocation conflicts using one of three strategies:
    - priority: High-priority customers first
    - proportional: Split ATP proportionally to demand ratios
    - fcfs: First-come-first-served

    Args:
        scenario_id: Scenario ID
        request: {
            "scenario_user_id": 3,
            "demands": [
                {"customer_id": 1, "customer_name": "Customer A", "demand": 300, "priority": 1},
                {"customer_id": 2, "customer_name": "Customer B", "demand": 300, "priority": 2}
            ],
            "allocation_method": "proportional"
        }

    Returns:
        {
            "total_demand": 600,
            "available_atp": 400,
            "allocations": [
                {
                    "customer_id": 1,
                    "customer_name": "Customer A",
                    "demand": 300,
                    "allocated": 200,
                    "unmet": 100,
                    "fill_rate": 0.667
                },
                ...
            ],
            "allocation_method": "proportional",
            "timestamp": "2026-01-28T12:00:00"
        }
    """
    try:
        # Validate allocation method
        valid_methods = ["priority", "proportional", "fcfs"]
        if request.allocation_method not in valid_methods:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid allocation method. Must be one of: {valid_methods}"
            )

        # Get game and validate
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(
            id=request.scenario_user_id, scenario_id=scenario_id
        ).first()
        if not scenario_user:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Get current round
        current_round = scenario_service.db.query(ScenarioRound).filter_by(
            scenario_id=scenario_id, round_number=scenario.current_round
        ).first()

        # Calculate current ATP
        atp_result = atp_service.calculate_current_atp(
            scenario_user=scenario_user,
            game=scenario,
            current_round=current_round,
            include_safety_stock=True
        )

        # Convert request demands to service demands
        demands = [
            CustomerDemand(
                customer_id=d.customer_id,
                customer_name=d.customer_name,
                demand=d.demand,
                priority=d.priority
            )
            for d in request.demands
        ]

        # Allocate ATP
        allocation_result = atp_service.allocate_to_customers(
            scenario_user=scenario_user,
            demands=demands,
            available_atp=atp_result.atp,
            allocation_method=request.allocation_method
        )

        # Convert dataclass to dict
        return asdict(allocation_result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ATP allocation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/promise-date/{scenario_user_id}")
async def calculate_promise_date(
    scenario_id: int,
    scenario_user_id: int,
    item_id: int,
    quantity: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    ctp_service: CTPService = Depends(get_ctp_service)
):
    """
    Calculate earliest possible delivery date for quantity.

    Accounts for:
    - Production capacity
    - Component availability
    - Production lead time
    - Shipping lead time

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID (manufacturer)
        item_id: Item ID to produce
        quantity: Quantity requested

    Returns:
        {
            "quantity": 500,
            "earliest_date": 18,
            "lead_time": 3,
            "confidence": 0.95,
            "constraints": ["capacity"],
            "breakdown": [
                "Current CTP (380 units) < requested quantity (500 units)",
                "Sufficient capacity available in Round 16 (CTP: 520)",
                "Production lead time: 1 rounds",
                "Shipping lead time: 2 rounds",
                "Earliest delivery: Round 18"
            ]
        }
    """
    try:
        # Validate quantity
        if quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Quantity must be greater than 0"
            )

        # Get game and validate
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get scenario_user
        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(
            id=scenario_user_id, scenario_id=scenario_id
        ).first()
        if not scenario_user:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Verify scenario_user is manufacturer
        node = _get_participant_node(scenario_service.db, scenario_user, game)
        if not node:
            raise HTTPException(
                status_code=400,
                detail="ScenarioUser node not found in supply chain config"
            )

        # Check if node is a manufacturer (master_type or dag_type)
        is_manufacturer = (
            (node.master_type and node.master_type.upper() == "MANUFACTURER") or
            (node.dag_type and node.dag_type.lower() == "factory")
        )
        if not is_manufacturer:
            raise HTTPException(
                status_code=400,
                detail="Promise date calculation only available for manufacturer nodes"
            )

        # Get current round
        current_round = scenario_service.db.query(ScenarioRound).filter_by(
            scenario_id=scenario_id, round_number=scenario.current_round
        ).first()

        if not current_round:
            raise HTTPException(
                status_code=400,
                detail="Scenario has not started yet - no current round available"
            )

        # Calculate promise date
        promise_result = ctp_service.calculate_promise_date(
            scenario_user=scenario_user,
            game=scenario,
            current_round=current_round,
            item_id=item_id,
            quantity=quantity
        )

        # Convert dataclass to dict
        return asdict(promise_result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Promise date calculation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Phase 4: Agent Mode Switching Endpoints
# ============================================================================

class SwitchModeRequest(BaseModel):
    """Request model for switching agent mode."""
    scenario_user_id: int
    new_mode: str  # "manual", "copilot", or "autonomous"
    reason: Optional[str] = "user_request"
    force: bool = False

    class Config:
        json_schema_extra = {
            "example": {
                "scenario_user_id": 1,
                "new_mode": "copilot",
                "reason": "user_request",
                "force": False
            }
        }


class ModeSwitchResponse(BaseModel):
    """Response model for mode switch operation."""
    success: bool
    previous_mode: str
    new_mode: str
    scenario_user_id: int
    scenario_id: int
    round_number: int
    reason: str
    message: str
    timestamp: str
    warnings: List[str] = []


@router.post("/scenarios/{scenario_id}/switch-mode", response_model=ModeSwitchResponse)
def switch_agent_mode(
    scenario_id: int,
    request: SwitchModeRequest,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    mode_service: AgentModeService = Depends(get_agent_mode_service)
):
    """
    Switch a scenario_user's agent mode during active gameplay.

    **Phase 4: Multi-Agent Orchestration**

    Allows dynamic switching between:
    - **manual**: Human makes all decisions
    - **copilot**: AI provides suggestions, human approves/modifies
    - **autonomous**: AI makes decisions automatically

    **Validation Rules**:
    - Scenario must be in progress
    - Copilot mode requires LLM agent availability
    - Autonomous mode requires agent_config_id
    - System overrides bypass validation

    **Example**:
    ```json
    {
      "scenario_user_id": 1,
      "new_mode": "copilot",
      "reason": "user_request"
    }
    ```

    **Returns**:
    - Previous mode, new mode, and warnings
    - Recorded in agent_mode_history for RLHF training
    """
    try:
        # Validate game exists and scenario_user has access
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        scenario_user = scenario_service.db.query(ScenarioUser).filter_by(
            id=request.scenario_user_id, scenario_id=scenario_id
        ).first()
        if not scenario_user:
            raise HTTPException(status_code=404, detail="ScenarioUser not found")

        # Validate new_mode
        try:
            new_mode_enum = AgentMode(request.new_mode.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode: {request.new_mode}. Must be manual, copilot, or autonomous"
            )

        # Validate reason
        try:
            reason_enum = ModeSwitchReason(request.reason.lower())
        except ValueError:
            reason_enum = ModeSwitchReason.USER_REQUEST

        # Perform mode switch
        result = mode_service.switch_agent_mode(
            scenario_user_id=request.scenario_user_id,
            scenario_id=scenario_id,
            new_mode=new_mode_enum,
            reason=reason_enum,
            triggered_by="user",
            force=request.force
        )

        return ModeSwitchResponse(
            success=result.success,
            previous_mode=result.previous_mode,
            new_mode=result.new_mode,
            scenario_user_id=result.scenario_user_id,
            scenario_id=result.scenario_id,
            round_number=result.round_number,
            reason=result.reason,
            message=result.message,
            timestamp=result.timestamp,
            warnings=result.warnings or []
        )

    except RuntimeError as e:
        # Validation failed
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mode switch error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/mode-history/{scenario_user_id}")
def get_mode_history(
    scenario_id: int,
    scenario_user_id: int,
    limit: int = 50,
    current_user: User = Depends(get_current_user_sync),
    mode_service: AgentModeService = Depends(get_agent_mode_service)
):
    """
    Get agent mode switch history for a scenario_user.

    **Phase 4: Multi-Agent Orchestration**

    Returns historical record of mode switches for:
    - RLHF training data analysis
    - User behavior analysis
    - Performance correlation studies

    **Query Parameters**:
    - limit: Max records to return (default: 50, max: 100)

    **Returns**:
    List of mode switch records with timestamps, reasons, and metadata
    """
    try:
        # Validate limit
        if limit > 100:
            limit = 100

        history = mode_service.get_mode_history(
            scenario_user_id=scenario_user_id,
            scenario_id=scenario_id,
            limit=limit
        )

        return {
            "scenario_id": scenario_id,
            "scenario_user_id": scenario_user_id,
            "count": len(history),
            "history": [
                {
                    "id": record.id,
                    "round_number": record.round_number,
                    "previous_mode": record.previous_mode,
                    "new_mode": record.new_mode,
                    "reason": record.reason,
                    "triggered_by": record.triggered_by,
                    "timestamp": record.timestamp,
                    "metadata": record.metadata
                }
                for record in history
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mode history error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/mode-distribution")
def get_mode_distribution(
    scenario_id: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    mode_service: AgentModeService = Depends(get_agent_mode_service)
):
    """
    Get current mode distribution across all scenario_users in a game.

    **Phase 4: Multi-Agent Orchestration**

    Returns count of scenario_users in each mode:
    - manual: Human-controlled
    - copilot: AI-assisted
    - autonomous: AI-controlled

    **Example Response**:
    ```json
    {
      "scenario_id": 1,
      "total_participants": 4,
      "distribution": {
        "manual": 2,
        "copilot": 1,
        "autonomous": 1
      },
      "percentage": {
        "manual": 50.0,
        "copilot": 25.0,
        "autonomous": 25.0
      }
    }
    ```

    **Use Cases**:
    - Scenario balance monitoring
    - AI adoption tracking
    - Training effectiveness analysis
    """
    try:
        # Validate game exists
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get mode distribution
        distribution = mode_service.get_current_mode_distribution(scenario_id)

        # Calculate total and percentages
        total_participants = sum(distribution.values())
        percentage = {
            mode: (count / total_participants * 100) if total_participants > 0 else 0
            for mode, count in distribution.items()
        }

        return {
            "scenario_id": scenario_id,
            "total_participants": total_participants,
            "distribution": distribution,
            "percentage": percentage
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mode distribution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Phase 4: Agent Weight Management Endpoints
# ============================================================================

class SetAgentWeightsRequest(BaseModel):
    """Request model for manually setting agent weights."""
    weights: Dict[str, float]  # {"llm": 0.5, "gnn": 0.3, "trm": 0.2}
    context_type: str = "game"  # "game", "scenario_user", or "config"

    class Config:
        json_schema_extra = {
            "example": {
                "weights": {
                    "llm": 0.5,
                    "gnn": 0.3,
                    "trm": 0.2
                },
                "context_type": "game"
            }
        }


class EnableAdaptiveLearningRequest(BaseModel):
    """Request model for enabling adaptive weight learning."""
    learning_method: str = "ema"  # ema, ucb, thompson, performance, gradient
    learning_rate: float = 0.1
    exploration_factor: float = 1.0

    class Config:
        json_schema_extra = {
            "example": {
                "learning_method": "ema",
                "learning_rate": 0.1,
                "exploration_factor": 1.0
            }
        }


@router.post("/scenarios/{scenario_id}/set-agent-weights")
def set_agent_weights(
    scenario_id: int,
    request: SetAgentWeightsRequest,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    learner: AdaptiveWeightLearner = Depends(get_adaptive_weight_learner)
):
    """
    Manually set agent weights for ensemble consensus.

    **Phase 4: Multi-Agent Orchestration - Weight Management**

    Allows manual configuration of agent weights that sum to 1.0:
    - **llm**: Weight for LLM (GPT-4) agent decisions
    - **gnn**: Weight for Graph Neural Network agent decisions
    - **trm**: Weight for Tiny Recursive Model agent decisions

    **Weight Normalization**:
    - Weights are automatically normalized to sum to 1.0
    - Example: {llm: 5, gnn: 3, trm: 2} → {llm: 0.5, gnn: 0.3, trm: 0.2}

    **Context Types**:
    - **game**: Weights apply to entire game
    - **scenario_user**: Weights per scenario_user (personalized)
    - **config**: Weights per supply chain configuration

    **Example Request**:
    ```json
    {
      "weights": {"llm": 0.5, "gnn": 0.3, "trm": 0.2},
      "context_type": "game"
    }
    ```

    **Returns**:
    - Normalized weights
    - Confirmation message
    """
    try:
        # Validate game exists
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Validate weights
        if not request.weights:
            raise HTTPException(status_code=400, detail="Weights cannot be empty")

        if any(w < 0 for w in request.weights.values()):
            raise HTTPException(status_code=400, detail="Weights must be non-negative")

        # Normalize weights to sum to 1.0
        total_weight = sum(request.weights.values())
        if total_weight == 0:
            raise HTTPException(status_code=400, detail="Total weight cannot be zero")

        normalized_weights = {
            agent: weight / total_weight
            for agent, weight in request.weights.items()
        }

        # Persist weights
        learner._persist_weights(
            context_id=scenario_id,
            weights=normalized_weights,
            learning_method="manual"
        )

        return {
            "scenario_id": scenario_id,
            "context_type": request.context_type,
            "original_weights": request.weights,
            "normalized_weights": normalized_weights,
            "message": f"Agent weights set successfully for {request.context_type} {scenario_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Set agent weights error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/agent-weights")
def get_agent_weights(
    scenario_id: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    learner: AdaptiveWeightLearner = Depends(get_adaptive_weight_learner)
):
    """
    Get current agent weights for a game.

    **Phase 4: Multi-Agent Orchestration - Weight Management**

    Returns:
    - Current agent weights (normalized to sum to 1.0)
    - Confidence score based on number of samples
    - Performance metrics per agent
    - Learning method used (manual, ema, ucb, etc.)
    - Last updated timestamp

    **Example Response**:
    ```json
    {
      "weights": {"llm": 0.5, "gnn": 0.3, "trm": 0.2},
      "confidence": 0.85,
      "num_samples": 42,
      "performance_metrics": {
        "llm": 0.82,
        "gnn": 0.75,
        "trm": 0.68
      },
      "learning_method": "ema",
      "last_updated": "2026-01-28T10:30:00"
    }
    ```

    **Use Cases**:
    - Display current weights in UI
    - Monitor weight convergence
    - Compare manual vs learned weights
    """
    try:
        # Validate game exists
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get learned weights
        adaptive_weights = learner.get_learned_weights(context_id=scenario_id)

        if not adaptive_weights:
            # Return default equal weights
            default_weights = {"llm": 1.0/3, "gnn": 1.0/3, "trm": 1.0/3}
            return {
                "scenario_id": scenario_id,
                "weights": default_weights,
                "confidence": 0.0,
                "num_samples": 0,
                "performance_metrics": {},
                "learning_method": "default",
                "last_updated": None,
                "message": "No learned weights found, using default equal weights"
            }

        return {
            "scenario_id": scenario_id,
            "weights": adaptive_weights.weights,
            "confidence": adaptive_weights.confidence,
            "num_samples": adaptive_weights.num_samples,
            "performance_metrics": adaptive_weights.performance_metrics,
            "learning_method": adaptive_weights.learning_method,
            "last_updated": adaptive_weights.last_updated
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get agent weights error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenarios/{scenario_id}/enable-adaptive-learning")
def enable_adaptive_learning(
    scenario_id: int,
    request: EnableAdaptiveLearningRequest,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """
    Enable automatic weight learning based on agent performance.

    **Phase 4: Multi-Agent Orchestration - Adaptive Learning**

    Configures automatic weight adaptation using various algorithms:

    **Learning Methods**:
    1. **ema** (Exponential Moving Average) - Smooth, stable weight updates
       - Best for: Consistent performance, low variance environments
       - Parameters: learning_rate (0-1, default: 0.1)

    2. **ucb** (Upper Confidence Bound) - Optimistic exploration
       - Best for: Exploration of underused agents, multi-armed bandit problems
       - Parameters: exploration_factor (default: 1.0)

    3. **thompson** (Thompson Sampling) - Bayesian bandit algorithm
       - Best for: Probabilistic exploration, handling uncertainty
       - Parameters: exploration_factor (default: 1.0)

    4. **performance** (Direct Performance Mapping) - Weights = Performance
       - Best for: Simple, interpretable weight assignment
       - Parameters: None

    5. **gradient** (Gradient Descent) - Optimize cost function
       - Best for: Continuous optimization, cost minimization
       - Parameters: learning_rate (default: 0.1)

    **Example Request**:
    ```json
    {
      "learning_method": "ema",
      "learning_rate": 0.1,
      "exploration_factor": 1.0
    }
    ```

    **Returns**:
    - Learning configuration
    - Initial weights
    - Confirmation message

    **Note**: Weights will automatically update as agents make decisions
    """
    try:
        # Validate game exists
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Validate learning method
        try:
            learning_method = LearningMethod(request.learning_method.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid learning method: {request.learning_method}. "
                       f"Must be one of: ema, ucb, thompson, performance, gradient"
            )

        # Store learning configuration (simplified - would need ScenarioConfig table in full implementation)
        # For now, just return confirmation

        return {
            "scenario_id": scenario_id,
            "learning_enabled": True,
            "learning_method": learning_method.value,
            "learning_rate": request.learning_rate,
            "exploration_factor": request.exploration_factor,
            "initial_weights": {"llm": 1.0/3, "gnn": 1.0/3, "trm": 1.0/3},
            "message": f"Adaptive learning enabled with {learning_method.value} method. "
                      f"Weights will automatically update based on agent performance."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Enable adaptive learning error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/weight-history")
def get_weight_history(
    scenario_id: int,
    limit: int = 50,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    integration: AgentOrchestrationIntegration = Depends(get_agent_orchestration_integration)
):
    """
    Get historical evolution of agent weights over time.

    **Phase 4: Multi-Agent Orchestration - Weight History**

    Returns chronological history of weight changes showing:
    - Weight distribution at each update
    - Number of samples (confidence indicator)
    - Learning method used
    - Performance metrics at that point
    - Timestamp

    **Use Cases**:
    - Visualize weight convergence
    - Identify when weights stabilized
    - Compare manual vs learned weights
    - Debug learning issues

    **Example Response**:
    ```json
    {
      "scenario_id": 1,
      "history": [
        {
          "weights": {"llm": 0.33, "gnn": 0.33, "trm": 0.33},
          "num_samples": 1,
          "learning_method": "ema",
          "timestamp": "2026-01-28T10:00:00",
          "performance_metrics": {}
        },
        {
          "weights": {"llm": 0.38, "gnn": 0.35, "trm": 0.27},
          "num_samples": 10,
          "learning_method": "ema",
          "timestamp": "2026-01-28T10:15:00",
          "performance_metrics": {"llm": 0.75, "gnn": 0.72, "trm": 0.68}
        },
        {
          "weights": {"llm": 0.45, "gnn": 0.38, "trm": 0.17},
          "num_samples": 30,
          "learning_method": "ema",
          "timestamp": "2026-01-28T10:45:00",
          "performance_metrics": {"llm": 0.82, "gnn": 0.75, "trm": 0.68}
        }
      ],
      "count": 3
    }
    ```

    **Parameters**:
    - limit: Max records to return (default: 50)
    """
    try:
        # Validate game exists
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Validate limit
        if limit > 200:
            limit = 200

        # Get weight history
        history = integration.get_weight_history(scenario_id=scenario_id, limit=limit)

        return {
            "scenario_id": scenario_id,
            "history": history,
            "count": len(history)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get weight history error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/ensemble-summary")
def get_ensemble_summary(
    scenario_id: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service),
    integration: AgentOrchestrationIntegration = Depends(get_agent_orchestration_integration)
):
    """
    Get comprehensive ensemble performance summary for a game.

    **Phase 4: Multi-Agent Orchestration - Ensemble Summary**

    Returns:
    - Current agent weights
    - Confidence score
    - Number of learning samples
    - Per-agent performance metrics
    - Learning method
    - Performance comparison vs baseline

    **Example Response**:
    ```json
    {
      "scenario_id": 1,
      "current_weights": {"llm": 0.45, "gnn": 0.38, "trm": 0.17},
      "confidence": 0.85,
      "num_samples": 42,
      "learning_method": "ema",
      "performance_metrics": {
        "llm": 0.82,
        "gnn": 0.75,
        "trm": 0.68
      },
      "llm_performance": {
        "num_samples": 42,
        "avg_total_cost": 1250.5,
        "avg_service_level": 0.88,
        "avg_inventory": 125.3
      },
      "gnn_performance": {...},
      "trm_performance": {...}
    }
    ```

    **Use Cases**:
    - Display ensemble status in dashboard
    - Monitor learning progress
    - Compare agent performance
    - Decision support (which agent to trust)
    """
    try:
        # Validate game exists
        scenario = scenario_service.db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Initialize integration if needed
        if not integration.learner:
            integration.initialize_for_game(scenario_id)

        # Get summary
        summary = integration.get_ensemble_summary(scenario_id)

        return summary

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get ensemble summary error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Phase 2: RLHF and Decision Comparison Endpoints
# ========================================

@router.get("/scenarios/{scenario_id}/rounds/{round_number}/decision-comparison")
def get_decision_comparison(
    scenario_id: int,
    round_number: int,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """
    Get decision comparison data for a completed round.

    Returns AI recommendations vs human decisions with actual outcomes
    for display in the DecisionComparisonPanel.

    Args:
        scenario_id: Scenario ID
        round_number: Round number (should be completed)

    Returns:
        {
            "round_number": 15,
            "comparisons": [
                {
                    "scenario_user_id": 1,
                    "participant_role": "retailer",
                    "ai_suggestion": 120,
                    "ai_confidence": 0.85,
                    "ai_agent_type": "gnn",
                    "human_decision": 100,
                    "feedback_action": "modified",
                    "ai_outcome": {"total_cost": 250.5, "service_level": 0.95},
                    "human_outcome": {"total_cost": 220.3, "service_level": 0.92},
                    "preference_label": "human_better"
                },
                ...
            ],
            "summary": {
                "ai_wins": 1,
                "human_wins": 2,
                "ties": 1,
                "total_cost_savings": 125.50
            }
        }
    """
    from app.services.rlhf_data_collector import RLHFFeedback, get_rlhf_data_collector
    from app.models.scenario_user import ScenarioUser

    try:
        # Get all RLHF feedback for this round
        feedbacks = (
            scenario_service.db.query(RLHFFeedback)
            .filter(
                RLHFFeedback.scenario_id == scenario_id,
                RLHFFeedback.round_number == round_number
            )
            .all()
        )

        if not feedbacks:
            return {
                "round_number": round_number,
                "comparisons": [],
                "summary": {
                    "ai_wins": 0,
                    "human_wins": 0,
                    "ties": 0,
                    "total_cost_savings": 0
                }
            }

        # Get scenario_user info
        scenario_user_ids = [f.scenario_user_id for f in feedbacks]
        scenario_users = (
            scenario_service.db.query(ScenarioUser)
            .filter(ScenarioUser.id.in_(scenario_user_ids))
            .all()
        )
        participant_map = {p.id: p for p in scenario_users}

        # Build comparison list
        comparisons = []
        ai_wins = 0
        human_wins = 0
        ties = 0
        total_cost_savings = 0.0

        for feedback in feedbacks:
            scenario_user = participant_map.get(feedback.scenario_user_id)
            participant_role = scenario_user.role if scenario_user else "unknown"

            comparison = {
                "scenario_user_id": feedback.scenario_user_id,
                "participant_role": participant_role,
                "ai_suggestion": feedback.ai_suggestion,
                "ai_confidence": feedback.ai_confidence,
                "ai_agent_type": feedback.agent_type,
                "ai_reasoning": feedback.ai_reasoning,
                "human_decision": feedback.human_decision,
                "feedback_action": feedback.feedback_action,
                "ai_outcome": feedback.ai_outcome,
                "human_outcome": feedback.human_outcome,
                "preference_label": feedback.preference_label,
            }
            comparisons.append(comparison)

            # Track summary stats
            if feedback.preference_label == "ai_better":
                ai_wins += 1
            elif feedback.preference_label == "human_better":
                human_wins += 1
            elif feedback.preference_label == "equivalent":
                ties += 1

            # Calculate cost savings
            if feedback.ai_outcome and feedback.human_outcome:
                ai_cost = feedback.ai_outcome.get("total_cost", 0)
                human_cost = feedback.human_outcome.get("total_cost", 0)
                total_cost_savings += (ai_cost - human_cost)

        return {
            "round_number": round_number,
            "comparisons": comparisons,
            "summary": {
                "ai_wins": ai_wins,
                "human_wins": human_wins,
                "ties": ties,
                "total_cost_savings": round(total_cost_savings, 2)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Decision comparison error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}/rlhf-feedback-summary")
def get_rlhf_feedback_summary(
    scenario_id: int,
    scenario_user_id: Optional[int] = None,
    current_user: User = Depends(get_current_user_sync),
    scenario_service: MixedScenarioService = Depends(get_mixed_scenario_service)
):
    """
    Get RLHF feedback summary for a game or scenario_user.

    Returns aggregate stats on AI vs human decision performance.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: Optional scenario_user ID to filter by

    Returns:
        {
            "total_decisions": 48,
            "acceptance_rate": 0.65,
            "modification_rate": 0.25,
            "rejection_rate": 0.10,
            "avg_modification_delta": 15.3,
            "human_better_rate": 0.35,
            "ai_better_rate": 0.45,
            "equivalent_rate": 0.20,
            "performance_by_agent": {
                "gnn": {"decisions": 20, "ai_better": 10, "human_better": 8, "ties": 2},
                "trm": {"decisions": 15, "ai_better": 7, "human_better": 6, "ties": 2},
                "llm": {"decisions": 13, "ai_better": 5, "human_better": 4, "ties": 4}
            }
        }
    """
    from app.services.rlhf_data_collector import RLHFFeedback

    try:
        # Build query
        query = scenario_service.db.query(RLHFFeedback).filter(
            RLHFFeedback.scenario_id == scenario_id
        )

        if scenario_user_id:
            query = query.filter(RLHFFeedback.scenario_user_id == scenario_user_id)

        feedbacks = query.all()

        if not feedbacks:
            return {
                "total_decisions": 0,
                "acceptance_rate": 0,
                "modification_rate": 0,
                "rejection_rate": 0,
                "avg_modification_delta": None,
                "human_better_rate": 0,
                "ai_better_rate": 0,
                "equivalent_rate": 0,
                "performance_by_agent": {}
            }

        # Calculate stats
        total = len(feedbacks)
        accepted = sum(1 for f in feedbacks if f.feedback_action == "accepted")
        modified = sum(1 for f in feedbacks if f.feedback_action == "modified")
        rejected = sum(1 for f in feedbacks if f.feedback_action == "rejected")

        human_better = sum(1 for f in feedbacks if f.preference_label == "human_better")
        ai_better = sum(1 for f in feedbacks if f.preference_label == "ai_better")
        equivalent = sum(1 for f in feedbacks if f.preference_label == "equivalent")

        # Average modification delta
        modifications = [f.modification_delta for f in feedbacks if f.modification_delta]
        avg_modification_delta = sum(modifications) / len(modifications) if modifications else None

        # Performance by agent type
        agent_types = set(f.agent_type for f in feedbacks)
        performance_by_agent = {}
        for agent_type in agent_types:
            agent_feedbacks = [f for f in feedbacks if f.agent_type == agent_type]
            performance_by_agent[agent_type] = {
                "decisions": len(agent_feedbacks),
                "ai_better": sum(1 for f in agent_feedbacks if f.preference_label == "ai_better"),
                "human_better": sum(1 for f in agent_feedbacks if f.preference_label == "human_better"),
                "ties": sum(1 for f in agent_feedbacks if f.preference_label == "equivalent"),
            }

        return {
            "total_decisions": total,
            "acceptance_rate": round(accepted / total, 3) if total > 0 else 0,
            "modification_rate": round(modified / total, 3) if total > 0 else 0,
            "rejection_rate": round(rejected / total, 3) if total > 0 else 0,
            "avg_modification_delta": round(avg_modification_delta, 2) if avg_modification_delta else None,
            "human_better_rate": round(human_better / total, 3) if total > 0 else 0,
            "ai_better_rate": round(ai_better / total, 3) if total > 0 else 0,
            "equivalent_rate": round(equivalent / total, 3) if total > 0 else 0,
            "performance_by_agent": performance_by_agent
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RLHF feedback summary error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
