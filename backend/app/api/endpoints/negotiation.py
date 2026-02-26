"""
Negotiation API Endpoints
Phase 7 Sprint 4 - Feature 4: Agent Negotiation

Provides REST API for inter-participant negotiations with AI mediation.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.api.deps import resolve_scenario_user_id
from app.services.negotiation_service import get_negotiation_service

router = APIRouter(prefix="/negotiations", tags=["negotiations"])


# =============================================================================
# REQUEST/RESPONSE SCHEMAS
# =============================================================================

class CreateNegotiationRequest(BaseModel):
    """Request to create a new negotiation."""
    target_scenario_user_id: int = Field(..., description="ScenarioUser receiving the proposal")
    negotiation_type: str = Field(..., description="order_adjustment, lead_time, inventory_share, price_adjustment")
    proposal: dict = Field(..., description="Proposal details")
    message: Optional[str] = Field(None, description="Optional message to recipient")

    class Config:
        json_schema_extra = {
            "example": {
                "target_scenario_user_id": 456,
                "negotiation_type": "inventory_share",
                "proposal": {
                    "units": 30,
                    "direction": "give"
                },
                "message": "I have excess inventory. Would you like some?"
            }
        }


class RespondToNegotiationRequest(BaseModel):
    """Request to respond to a negotiation."""
    action: str = Field(..., description="accept, reject, or counter")
    counter_proposal: Optional[dict] = Field(None, description="Required if action is 'counter'")
    message: Optional[str] = Field(None, description="Optional message")

    class Config:
        json_schema_extra = {
            "example": {
                "action": "accept",
                "message": "Great! This will help reduce my backlog."
            }
        }


class NegotiationResponse(BaseModel):
    """Response containing negotiation details."""
    negotiation_id: int
    status: str
    expires_at: Optional[str]
    proposal: dict
    impact_simulation: Optional[dict]
    created_at: str

    class Config:
        from_attributes = True


class NegotiationListItem(BaseModel):
    """Negotiation item in list."""
    id: int
    negotiation_type: str
    proposal: str
    counter_proposal: Optional[str]
    status: str
    expires_at: Optional[str]
    created_at: Optional[str]
    responded_at: Optional[str]
    initiator_role: str
    target_role: str
    is_initiator: bool
    is_target: bool


class NegotiationsListResponse(BaseModel):
    """Response containing list of negotiations."""
    negotiations: List[NegotiationListItem]
    total_count: int


class NegotiationMessage(BaseModel):
    """Message in negotiation."""
    id: int
    sender_id: int
    sender_role: str
    message: str
    created_at: Optional[str]


class NegotiationMessagesResponse(BaseModel):
    """Response containing negotiation messages."""
    messages: List[NegotiationMessage]
    negotiation_id: int


class NegotiationSuggestionResponse(BaseModel):
    """Response containing AI-generated negotiation suggestion."""
    suggested_type: Optional[str]
    proposal: Optional[dict]
    rationale: str
    confidence: float
    expected_benefit: Optional[dict]


class RespondNegotiationResponse(BaseModel):
    """Response after responding to negotiation."""
    negotiation_id: int
    status: str
    counter_proposal: Optional[dict]
    message: Optional[str]
    responded_at: str


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/scenarios/{scenario_id}/create", response_model=NegotiationResponse)
async def create_negotiation(
    scenario_id: int,
    request: CreateNegotiationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new negotiation proposal.

    **Negotiation Types**:
    - `order_adjustment`: Request to modify order quantity
    - `lead_time`: Request to reduce/increase lead time
    - `inventory_share`: Request to share/reallocate inventory
    - `price_adjustment`: Request for cost modification
    """
    try:
        initiator_id = await resolve_scenario_user_id(scenario_id, current_user, db)
        negotiation_service = get_negotiation_service(db)

        result = await negotiation_service.create_negotiation(
            scenario_id=scenario_id,
            initiator_id=initiator_id,
            target_id=request.target_scenario_user_id,
            negotiation_type=request.negotiation_type,
            proposal=request.proposal,
            message=request.message
        )

        return NegotiationResponse(**result)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create negotiation: {str(e)}"
        )


@router.post("/scenarios/{scenario_id}/{negotiation_id}/respond", response_model=RespondNegotiationResponse)
async def respond_to_negotiation(
    scenario_id: int,
    negotiation_id: int,
    request: RespondToNegotiationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Respond to a negotiation proposal.

    **Actions**:
    - `accept`: Accept the proposal (executes changes)
    - `reject`: Reject the proposal
    - `counter`: Make a counter-offer (requires counter_proposal)
    """
    try:
        responder_id = await resolve_scenario_user_id(scenario_id, current_user, db)
        negotiation_service = get_negotiation_service(db)

        result = await negotiation_service.respond_to_negotiation(
            negotiation_id=negotiation_id,
            responder_id=responder_id,
            action=request.action,
            counter_proposal=request.counter_proposal,
            message=request.message
        )

        return RespondNegotiationResponse(**result)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to respond to negotiation: {str(e)}"
        )


@router.get("/scenarios/{scenario_id}/list", response_model=NegotiationsListResponse)
async def get_scenario_user_negotiations(
    scenario_id: int,
    status_filter: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get negotiations for the current participant in a scenario.

    Returns negotiations where the participant is either the initiator or target.

    **Query Parameters**:
    - `status_filter`: Filter by status (pending, accepted, rejected, countered, expired)
    - `limit`: Maximum negotiations to return (default: 20, max: 100)
    """
    if limit > 100:
        limit = 100

    try:
        scenario_user_id = await resolve_scenario_user_id(scenario_id, current_user, db)
        negotiation_service = get_negotiation_service(db)

        negotiations = await negotiation_service.get_scenario_user_negotiations(
            scenario_id=scenario_id,
            scenario_user_id=scenario_user_id,
            status_filter=status_filter,
            limit=limit
        )

        return NegotiationsListResponse(
            negotiations=[NegotiationListItem(**n) for n in negotiations],
            total_count=len(negotiations)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get negotiations: {str(e)}"
        )


@router.get("/{negotiation_id}/messages", response_model=NegotiationMessagesResponse)
async def get_negotiation_messages(
    negotiation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get messages in a negotiation conversation.

    Returns all messages exchanged between initiator and target.
    """
    try:
        negotiation_service = get_negotiation_service(db)

        messages = await negotiation_service.get_negotiation_messages(
            negotiation_id=negotiation_id
        )

        return NegotiationMessagesResponse(
            messages=[NegotiationMessage(**m) for m in messages],
            negotiation_id=negotiation_id
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get messages: {str(e)}"
        )


@router.get("/scenarios/{scenario_id}/suggest/{target_scenario_user_id}", response_model=NegotiationSuggestionResponse)
async def get_negotiation_suggestion(
    scenario_id: int,
    target_scenario_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get AI-mediated negotiation suggestion.

    Analyzes current scenario state and suggests mutually beneficial proposals.
    """
    try:
        scenario_user_id = await resolve_scenario_user_id(scenario_id, current_user, db)
        negotiation_service = get_negotiation_service(db)

        suggestion = await negotiation_service.generate_negotiation_suggestion(
            scenario_id=scenario_id,
            scenario_user_id=scenario_user_id,
            target_scenario_user_id=target_scenario_user_id
        )

        return NegotiationSuggestionResponse(**suggestion)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate suggestion: {str(e)}"
        )
