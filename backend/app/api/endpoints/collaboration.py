"""
Collaboration API Endpoints
Sprint 5: Collaboration Hub

Provides endpoints for:
- Agent-to-Agent (A2A) coordination
- Human-to-Agent (H2A) with explainability
- Human-to-Human (H2H) with rationale capture
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime

from app.api import deps
from app.models.user import User
from app.services.collaboration_service import CollaborationService
from app.core.capabilities import require_capabilities

router = APIRouter()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class A2AMessageSchema(BaseModel):
    """Schema for agent-to-agent message"""
    from_agent: str = Field(..., description="Source agent identifier")
    to_agent: str = Field(..., description="Target agent identifier")
    content: str = Field(..., description="Message content")
    message_type: str = Field("coordination", pattern="^(coordination|negotiation|information|request)$")
    context: Optional[Dict] = Field(None, description="Additional context metadata")
    session_id: Optional[str] = Field(None, description="Optional session identifier")


class A2AMessageResponse(BaseModel):
    """Response schema for A2A message"""
    message_id: int
    from_agent: str
    to_agent: str
    content: str
    message_type: str
    timestamp: datetime
    context: Dict
    requires_response: bool


class A2AThreadResponse(BaseModel):
    """Response schema for A2A conversation thread"""
    agent1: str
    agent2: str
    message_count: int
    messages: List[Dict]


class AgentExplanationResponse(BaseModel):
    """Response schema for agent suggestion explanation"""
    suggestion_id: int
    agent_id: str
    suggested_quantity: int
    confidence: float
    rationale_breakdown: Dict
    alternatives_considered: List[Dict]
    trade_off_analysis: Dict
    confidence_breakdown: Dict
    risks_and_assumptions: Dict


class HumanDecisionSchema(BaseModel):
    """Schema for capturing human decision on agent suggestion"""
    suggestion_id: int = Field(..., description="Agent suggestion ID")
    decision: str = Field(..., pattern="^(accept|reject|modify)$")
    rationale: str = Field(..., description="Human reasoning for decision")
    modified_quantity: Optional[int] = Field(None, description="Modified quantity if decision is 'modify'")
    trade_off_preferences: Optional[Dict] = Field(None, description="Human trade-off priorities")


class HumanDecisionResponse(BaseModel):
    """Response schema for human decision capture"""
    decision_id: int
    suggestion_id: int
    user_id: str
    decision: str
    rationale: str
    timestamp: datetime
    learning_signals: Dict


class ApprovalRequestSchema(BaseModel):
    """Schema for H2H approval request"""
    to_user: str = Field(..., description="User ID to request approval from")
    entity_type: str = Field(..., description="Type of entity (supply_plan, recommendation, etc.)")
    entity_id: str = Field(..., description="ID of entity requiring approval")
    request_message: str = Field(..., description="Request description")
    rationale: str = Field(..., description="Detailed rationale for request")
    trade_offs: Optional[Dict] = Field(None, description="Trade-off analysis")
    urgency: str = Field("normal", pattern="^(low|normal|high|critical)$")


class ApprovalResponseSchema(BaseModel):
    """Schema for H2H approval response"""
    request_id: int = Field(..., description="Approval request ID")
    decision: str = Field(..., pattern="^(approved|rejected|needs_modification)$")
    response_rationale: str = Field(..., description="Detailed rationale for decision")
    alternative_suggestion: Optional[Dict] = Field(None, description="Alternative approach if rejected")


class ApprovalRequestResponse(BaseModel):
    """Response schema for approval request"""
    request_id: int
    from_user: str
    to_user: str
    entity_type: str
    entity_id: str
    request_message: str
    rationale: str
    trade_offs: Dict
    urgency: str
    status: str
    created_at: datetime


class ApprovalResponseResponse(BaseModel):
    """Response schema for approval response"""
    response_id: int
    request_id: int
    user_id: str
    decision: str
    response_rationale: str
    timestamp: datetime
    alternative_suggestion: Optional[Dict]


class TradeOffAnalysisSchema(BaseModel):
    """Schema for trade-off analysis request"""
    decision_context: Dict = Field(..., description="Context for decision (supply_plan, recommendation, etc.)")
    options: List[Dict] = Field(..., description="List of options to analyze")


class TradeOffAnalysisResponse(BaseModel):
    """Response schema for trade-off analysis"""
    decision_context: Dict
    options_analysis: List[Dict]
    recommended_option: Dict
    sensitivity_analysis: Dict


# ============================================================================
# A2A (Agent-to-Agent) Endpoints
# ============================================================================

@router.post("/a2a/message", response_model=A2AMessageResponse)
@require_capabilities(["manage_collaboration"])
async def send_agent_message(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    message: A2AMessageSchema
):
    """
    Send coordination message from one agent to another

    Agent-to-Agent collaboration enables:
    - Coordination between planning agents
    - Negotiation for resource allocation
    - Information sharing across supply chain nodes
    - Multi-agent decision consensus

    Args:
        message: A2A message with from/to agents, content, type, and context

    Returns:
        Created message with metadata
    """
    service = CollaborationService(db)

    try:
        result = await service.send_agent_to_agent_message(
            from_agent=message.from_agent,
            to_agent=message.to_agent,
            content=message.content,
            message_type=message.message_type,
            context=message.context,
            session_id=message.session_id
        )

        return A2AMessageResponse(**result)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send A2A message: {str(e)}"
        )


@router.get("/a2a/thread", response_model=A2AThreadResponse)
@require_capabilities(["view_collaboration"])
async def get_agent_thread(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    agent1: str = Query(..., description="First agent identifier"),
    agent2: str = Query(..., description="Second agent identifier"),
    limit: int = Query(50, le=200)
):
    """
    Get conversation thread between two agents

    Returns chronological message history for A2A coordination analysis

    Args:
        agent1: First agent identifier
        agent2: Second agent identifier
        limit: Maximum messages to return

    Returns:
        Conversation thread with all messages
    """
    service = CollaborationService(db)

    try:
        result = await service.get_agent_coordination_thread(
            agent1=agent1,
            agent2=agent2,
            limit=limit
        )

        return A2AThreadResponse(**result)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve A2A thread: {str(e)}"
        )


# ============================================================================
# H2A (Human-to-Agent) Endpoints
# ============================================================================

@router.get("/h2a/explain/{suggestion_id}", response_model=AgentExplanationResponse)
@require_capabilities(["view_collaboration"])
async def explain_agent_suggestion(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    suggestion_id: int
):
    """
    Get comprehensive explanation for agent suggestion

    Provides explainability for agent decisions including:
    - Rationale breakdown (factors, data sources, assumptions, constraints)
    - Alternatives considered (other options evaluated)
    - Trade-off analysis (service level vs cost, risk vs flexibility)
    - Confidence breakdown (overall confidence, data quality, uncertainty)
    - Risks and assumptions (sensitivity analysis, what could go wrong)

    Args:
        suggestion_id: ID of agent suggestion to explain

    Returns:
        Comprehensive explanation with full transparency
    """
    service = CollaborationService(db)

    try:
        result = await service.explain_agent_suggestion(suggestion_id)

        return AgentExplanationResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate explanation: {str(e)}"
        )


@router.post("/h2a/decide", response_model=HumanDecisionResponse)
@require_capabilities(["manage_collaboration"])
async def capture_human_decision(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    decision: HumanDecisionSchema
):
    """
    Capture human decision on agent suggestion with rationale

    Records human accept/reject/modify decisions with full reasoning and
    trade-off preferences for agent learning and improvement

    Human rationale captures:
    - Decision (accept/reject/modify)
    - Detailed reasoning
    - Trade-off preferences (cost vs service, risk vs flexibility)
    - Modified quantity (if applicable)

    Learning signals extracted:
    - Agreement/disagreement patterns
    - Human preference patterns
    - Context factors influencing decisions

    Args:
        decision: Human decision with rationale and trade-offs

    Returns:
        Captured decision record with extracted learning signals
    """
    service = CollaborationService(db)

    try:
        result = await service.capture_human_decision_rationale(
            suggestion_id=decision.suggestion_id,
            user_id=current_user.id,
            decision=decision.decision,
            rationale=decision.rationale,
            modified_quantity=decision.modified_quantity,
            trade_off_preferences=decision.trade_off_preferences
        )

        return HumanDecisionResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to capture decision: {str(e)}"
        )


# ============================================================================
# H2H (Human-to-Human) Endpoints
# ============================================================================

@router.post("/h2h/request-approval", response_model=ApprovalRequestResponse)
@require_capabilities(["manage_collaboration"])
async def request_approval(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    request: ApprovalRequestSchema
):
    """
    Request approval from another user with full rationale

    Human-to-Human collaboration with emphasis on rationale capture:
    - Detailed request description
    - Complete reasoning for request
    - Trade-off analysis
    - Urgency level

    Use cases:
    - Supply plan approval requests
    - Recommendation approval requests
    - Policy override requests
    - Strategic decision approvals

    Args:
        request: Approval request with rationale and trade-offs

    Returns:
        Created approval request with tracking ID
    """
    service = CollaborationService(db)

    try:
        result = await service.request_approval(
            from_user=current_user.id,
            to_user=request.to_user,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            request_message=request.request_message,
            rationale=request.rationale,
            trade_offs=request.trade_offs,
            urgency=request.urgency
        )

        return ApprovalRequestResponse(**result)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create approval request: {str(e)}"
        )


@router.post("/h2h/respond-approval", response_model=ApprovalResponseResponse)
@require_capabilities(["manage_collaboration"])
async def respond_to_approval(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    response: ApprovalResponseSchema
):
    """
    Respond to approval request with decision rationale

    Captures human decision-making reasoning:
    - Approval decision (approved/rejected/needs_modification)
    - Detailed response rationale
    - Alternative suggestions (if rejected)

    Rationale capture enables:
    - Decision transparency
    - Organizational learning
    - Pattern identification
    - Process improvement

    Args:
        response: Approval response with rationale and alternatives

    Returns:
        Recorded response with metadata
    """
    service = CollaborationService(db)

    try:
        result = await service.respond_to_approval(
            request_id=response.request_id,
            user_id=current_user.id,
            decision=response.decision,
            response_rationale=response.response_rationale,
            alternative_suggestion=response.alternative_suggestion
        )

        return ApprovalResponseResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to respond to approval: {str(e)}"
        )


@router.get("/h2h/my-requests", response_model=List[ApprovalRequestResponse])
@require_capabilities(["view_collaboration"])
async def get_my_approval_requests(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    status_filter: Optional[str] = Query(None, pattern="^(pending|approved|rejected|needs_modification)$"),
    limit: int = Query(50, le=200)
):
    """
    Get approval requests sent by current user

    Args:
        status_filter: Optional filter by status
        limit: Maximum requests to return

    Returns:
        List of approval requests with status
    """
    service = CollaborationService(db)

    try:
        result = await service.get_user_approval_requests(
            user_id=current_user.id,
            sent=True,
            status_filter=status_filter,
            limit=limit
        )

        return [ApprovalRequestResponse(**r) for r in result]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve approval requests: {str(e)}"
        )


@router.get("/h2h/pending-approvals", response_model=List[ApprovalRequestResponse])
@require_capabilities(["view_collaboration"])
async def get_pending_approvals(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    limit: int = Query(50, le=200)
):
    """
    Get pending approval requests assigned to current user

    Args:
        limit: Maximum requests to return

    Returns:
        List of pending approvals requiring user's decision
    """
    service = CollaborationService(db)

    try:
        result = await service.get_user_approval_requests(
            user_id=current_user.id,
            sent=False,
            status_filter="pending",
            limit=limit
        )

        return [ApprovalRequestResponse(**r) for r in result]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve pending approvals: {str(e)}"
        )


# ============================================================================
# Trade-off Analysis Endpoint
# ============================================================================

@router.post("/analyze-tradeoffs", response_model=TradeOffAnalysisResponse)
@require_capabilities(["view_collaboration"])
async def analyze_decision_tradeoffs(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    analysis: TradeOffAnalysisSchema
):
    """
    Analyze trade-offs between multiple decision options

    Multi-criteria analysis across:
    - Cost impact (holding, ordering, shortage costs)
    - Service level impact (fill rate, OTIF)
    - Risk impact (stockout risk, excess inventory risk)
    - Sustainability impact (CO2 emissions, waste)

    For each option, provides:
    - Multi-dimensional scores (0-100)
    - Pros and cons
    - Risk assessment
    - Sensitivity to assumptions

    Also identifies:
    - Recommended option (highest total score)
    - Pareto-optimal options
    - Key trade-off sensitivities

    Args:
        analysis: Decision context and options to analyze

    Returns:
        Comprehensive trade-off analysis with recommendations
    """
    service = CollaborationService(db)

    try:
        result = await service.analyze_decision_tradeoffs(
            decision_context=analysis.decision_context,
            options=analysis.options
        )

        return TradeOffAnalysisResponse(**result)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze trade-offs: {str(e)}"
        )


# ============================================================================
# Collaboration Scenarios (Agentic Authorization Protocol)
# ============================================================================

@router.get("/scenarios")
def list_collaboration_scenarios(
    group_id: Optional[int] = Query(None),
    level: Optional[str] = Query(None, description="Filter by level: sop, tactical, execution"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """List collaboration scenarios for a group."""
    from sqlalchemy import text as sa_text

    gid = group_id or current_user.group_id
    query = "SELECT * FROM collaboration_scenarios WHERE group_id = :gid"
    params = {"gid": gid}

    if level:
        query += " AND level = :level"
        params["level"] = level
    if status_filter:
        query += " AND status = :status"
        params["status"] = status_filter

    query += " ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, created_at DESC"

    result = db.execute(sa_text(query), params)
    rows = result.mappings().all()
    return [dict(r) for r in rows]


@router.get("/scenarios/{scenario_code}")
def get_collaboration_scenario(
    scenario_code: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get a single collaboration scenario by code."""
    from sqlalchemy import text as sa_text

    result = db.execute(
        sa_text("SELECT * FROM collaboration_scenarios WHERE scenario_code = :code"),
        {"code": scenario_code}
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_code} not found")
    return dict(row)
