"""
Negotiation API Endpoints
Phase 7 Sprint 4 - Feature 4: Agent Negotiation

Provides REST API for inter-player negotiations with AI mediation.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.negotiation_service import get_negotiation_service

router = APIRouter(prefix="/negotiations", tags=["negotiations"])


# =============================================================================
# REQUEST/RESPONSE SCHEMAS
# =============================================================================

class CreateNegotiationRequest(BaseModel):
    """Request to create a new negotiation."""
    target_player_id: int = Field(..., description="Player receiving the proposal")
    negotiation_type: str = Field(..., description="order_adjustment, lead_time, inventory_share, price_adjustment")
    proposal: dict = Field(..., description="Proposal details")
    message: Optional[str] = Field(None, description="Optional message to recipient")

    class Config:
        json_schema_extra = {
            "example": {
                "target_player_id": 456,
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

    **Proposal Formats**:

    *Order Adjustment*:
    ```json
    {
      "quantity_change": 20,
      "commitment_rounds": 3
    }
    ```

    *Inventory Share*:
    ```json
    {
      "units": 30,
      "direction": "give"
    }
    ```

    *Lead Time*:
    ```json
    {
      "lead_time_change": -1,
      "compensation": 10
    }
    ```

    *Price Adjustment*:
    ```json
    {
      "price_change": -5,
      "volume_commitment": 100
    }
    ```

    **Features**:
    - Automatic impact simulation
    - 24-hour expiry (default)
    - Optional message to recipient
    """
    try:
        negotiation_service = get_negotiation_service(db)

        # TODO: Map current_user to player_id properly
        initiator_id = current_user.id

        result = await negotiation_service.create_negotiation(
            game_id=scenario_id,
            initiator_id=initiator_id,
            target_id=request.target_player_id,
            negotiation_type=request.negotiation_type,
            proposal=request.proposal,
            message=request.message
        )

        return NegotiationResponse(**result)

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


@router.post("/{negotiation_id}/respond", response_model=RespondNegotiationResponse)
async def respond_to_negotiation(
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

    **When Accepting**:
    - Proposal is executed immediately
    - Game state is modified (inventory, orders, etc.)
    - Both players are notified

    **When Countering**:
    - Original proposal remains pending
    - Counter-proposal sent back to initiator
    - Initiator can then accept/reject/counter

    **Example Accept**:
    ```json
    {
      "action": "accept",
      "message": "Perfect! This solves my backlog issue."
    }
    ```

    **Example Counter**:
    ```json
    {
      "action": "counter",
      "counter_proposal": {
        "units": 20,
        "direction": "give"
      },
      "message": "I can only spare 20 units, not 30."
    }
    ```

    **Example Reject**:
    ```json
    {
      "action": "reject",
      "message": "Sorry, I need my inventory for upcoming orders."
    }
    ```
    """
    try:
        negotiation_service = get_negotiation_service(db)

        # TODO: Map current_user to player_id properly
        responder_id = current_user.id

        result = await negotiation_service.respond_to_negotiation(
            negotiation_id=negotiation_id,
            responder_id=responder_id,
            action=request.action,
            counter_proposal=request.counter_proposal,
            message=request.message
        )

        return RespondNegotiationResponse(**result)

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
async def get_player_negotiations(
    scenario_id: int,
    status_filter: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get negotiations for the current player.

    Returns negotiations where the player is either the initiator or target.

    **Query Parameters**:
    - `status_filter`: Filter by status (pending, accepted, rejected, countered, expired)
    - `limit`: Maximum negotiations to return (default: 20, max: 100)

    **Use Cases**:
    - View pending proposals requiring action
    - Review negotiation history
    - Track accepted agreements
    - Analyze rejected proposals

    **Example Response**:
    ```json
    {
      "negotiations": [
        {
          "id": 123,
          "negotiation_type": "inventory_share",
          "proposal": "{\"units\": 30}",
          "status": "pending",
          "expires_at": "2026-01-15T12:00:00",
          "initiator_role": "WHOLESALER",
          "target_role": "RETAILER",
          "is_initiator": false,
          "is_target": true
        }
      ],
      "total_count": 1
    }
    ```
    """
    if limit > 100:
        limit = 100

    try:
        negotiation_service = get_negotiation_service(db)

        # TODO: Map current_user to player_id properly
        player_id = current_user.id

        negotiations = await negotiation_service.get_player_negotiations(
            game_id=scenario_id,
            player_id=player_id,
            status_filter=status_filter,
            limit=limit
        )

        return NegotiationsListResponse(
            negotiations=[NegotiationListItem(**n) for n in negotiations],
            total_count=len(negotiations)
        )

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

    **Use Cases**:
    - View negotiation conversation history
    - Understand context of counter-offers
    - Review reasoning for decisions

    **Example Response**:
    ```json
    {
      "messages": [
        {
          "id": 1,
          "sender_id": 123,
          "sender_role": "WHOLESALER",
          "message": "I have excess inventory. Would you like some?",
          "created_at": "2026-01-14T10:00:00"
        },
        {
          "id": 2,
          "sender_id": 124,
          "sender_role": "RETAILER",
          "message": "Yes, but can you spare 20 instead of 30?",
          "created_at": "2026-01-14T10:05:00"
        }
      ],
      "negotiation_id": 123
    }
    ```
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


@router.get("/scenarios/{scenario_id}/suggest/{target_player_id}", response_model=NegotiationSuggestionResponse)
async def get_negotiation_suggestion(
    scenario_id: int,
    target_player_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get AI-mediated negotiation suggestion.

    Analyzes current game state and suggests mutually beneficial proposals.

    **Algorithm**:
    1. Retrieve current state for both players
    2. Identify complementary needs (excess/deficit)
    3. Calculate expected benefits
    4. Generate proposal with rationale

    **Suggestion Scenarios**:
    - **Inventory Imbalance**: One has excess, other has backlog
    - **Cost Reduction**: Coordinated ordering to reduce bullwhip
    - **Lead Time Optimization**: Rush orders with compensation
    - **Volume Discounts**: Commitment-based price adjustments

    **Example Response**:
    ```json
    {
      "suggested_type": "inventory_share",
      "proposal": {
        "units": 30,
        "direction": "give"
      },
      "rationale": "You have excess inventory (70 units) while RETAILER has high backlog (35 units). Sharing inventory can reduce overall costs.",
      "confidence": 0.80,
      "expected_benefit": {
        "cost_reduction": 15,
        "service_improvement": 0.10,
        "goodwill": "high"
      }
    }
    ```

    **No Suggestion Response**:
    ```json
    {
      "suggested_type": null,
      "rationale": "No clear mutual benefit identified in current state.",
      "confidence": 0.30,
      "note": "You can still create manual proposals"
    }
    ```
    """
    try:
        negotiation_service = get_negotiation_service(db)

        # TODO: Map current_user to player_id properly
        player_id = current_user.id

        suggestion = await negotiation_service.generate_negotiation_suggestion(
            game_id=scenario_id,
            player_id=player_id,
            target_player_id=target_player_id
        )

        return NegotiationSuggestionResponse(**suggestion)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate suggestion: {str(e)}"
        )
