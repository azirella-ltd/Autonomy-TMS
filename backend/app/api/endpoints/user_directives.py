"""User Directive API endpoints — "Talk to Me" natural language context capture.

Accepts natural language directives from authenticated users, parses them
with LLM, routes to the appropriate Powell layer based on role, and tracks
effectiveness via Bayesian posteriors.

Two-phase flow:
  1. POST /directives/analyze — LLM parse, return structured result + missing fields
  2. POST /directives/submit  — persist and route (with optional clarifications)
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import get_async_db
from app.models.user import User
from app.services.directive_service import DirectiveService

router = APIRouter(prefix="/directives", tags=["Directives"])
logger = logging.getLogger(__name__)


# ── Request / Response models ────────────────────────────────────────────────

class DirectiveAnalyzeRequest(BaseModel):
    config_id: int
    text: str = Field(..., min_length=3, max_length=5000)


class MissingField(BaseModel):
    field: str
    question: str
    type: str  # "text" | "select" | "number"
    options: Optional[List[str]] = None


class DirectiveAnalyzeResponse(BaseModel):
    # Common fields
    intent: Optional[str] = None  # directive | question | scenario_event | scenario_question | unknown
    confidence: float = 0.0
    target_layer: str = "operational"
    layer_description: str = ""

    # Directive-specific fields
    directive_type: Optional[str] = None
    reason_code: Optional[str] = None
    scope: Optional[dict] = None
    direction: Optional[str] = None
    metric: Optional[str] = None
    magnitude_pct: Optional[float] = None
    missing_fields: List[MissingField] = []
    is_complete: bool = False

    # Question-specific fields
    answer: Optional[str] = None  # LLM-generated answer (question or scenario_question)

    # Ambiguous intent fields
    clarification_needed: bool = False
    question: Optional[str] = None  # Clarification question for the user

    # Scenario event / scenario question fields
    scenario_event: Optional[dict] = None
    question_text: Optional[str] = None  # The question part of a scenario_question
    event_summary: Optional[str] = None
    event_id: Optional[int] = None
    target_config_id: Optional[int] = None
    target_page: Optional[str] = None
    target_page_label: Optional[str] = None
    can_fulfill: Optional[bool] = None
    confidence_note: Optional[str] = None


class DirectiveSubmitRequest(BaseModel):
    config_id: int
    text: str = Field(..., min_length=3, max_length=5000)
    clarifications: Optional[Dict[str, str]] = None
    scenario_event_id: Optional[int] = None  # Skip re-injection if already injected
    target_config_id: Optional[int] = None   # Branched config from prior injection


class DirectiveResponse(BaseModel):
    id: int
    raw_text: str
    directive_type: str
    reason_code: str
    parsed_intent: str
    parsed_scope: dict
    parsed_direction: Optional[str] = None
    parsed_metric: Optional[str] = None
    parsed_magnitude_pct: Optional[float] = None
    parser_confidence: float
    target_layer: str
    target_trm_types: Optional[list] = None
    target_site_keys: Optional[list] = None
    status: str
    routed_actions: Optional[list] = None
    created_at: Optional[str] = None
    user_name: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=DirectiveAnalyzeResponse)
async def analyze_directive(
    request: DirectiveAnalyzeRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Analyze a directive without persisting — returns parsed fields and missing gaps.

    The frontend calls this first. If missing_fields is non-empty, it shows
    clarifying questions. Once all gaps are filled, the frontend calls /submit
    with the original text + clarifications dict.
    """
    service = DirectiveService(db)
    parsed = await service.analyze_directive(
        user=current_user,
        config_id=request.config_id,
        raw_text=request.text,
    )

    intent = parsed.get("intent", "directive")

    # Question flow — return the LLM-generated answer
    if intent == "question":
        return DirectiveAnalyzeResponse(
            intent="question",
            confidence=parsed.get("confidence", 0.5),
            target_layer=parsed.get("target_layer", "operational"),
            layer_description=parsed.get("layer_description", ""),
            answer=parsed.get("answer"),
            target_page=parsed.get("target_page"),
            target_page_label=parsed.get("target_page_label"),
        )

    # Ambiguous — ask the user to clarify
    if intent == "unknown" or parsed.get("clarification_needed"):
        return DirectiveAnalyzeResponse(
            intent="unknown",
            confidence=0.0,
            target_layer=parsed.get("target_layer", "operational"),
            layer_description=parsed.get("layer_description", ""),
            clarification_needed=True,
            question=parsed.get("question"),
        )

    # Scenario event / scenario question flow
    if intent in ("scenario_event", "scenario_question"):
        missing = parsed.get("missing_fields", [])
        return DirectiveAnalyzeResponse(
            intent=intent,
            confidence=parsed.get("confidence", 0.5),
            target_layer=parsed.get("target_layer", "operational"),
            layer_description=parsed.get("layer_description", ""),
            scenario_event=parsed.get("scenario_event"),
            question_text=parsed.get("question_text"),
            missing_fields=[MissingField(**m) for m in missing],
            is_complete=len(missing) == 0,
            # Populated only when event was injected (no missing fields)
            answer=parsed.get("answer"),
            event_summary=parsed.get("event_summary"),
            event_id=parsed.get("event_id"),
            target_config_id=parsed.get("target_config_id"),
            target_page=parsed.get("target_page"),
            target_page_label=parsed.get("target_page_label"),
            can_fulfill=parsed.get("can_fulfill"),
            confidence_note=parsed.get("confidence_note"),
        )

    # Directive flow — structured parse with gap detection
    missing = parsed.get("missing_fields", [])
    return DirectiveAnalyzeResponse(
        intent=intent,
        directive_type=parsed.get("directive_type"),
        reason_code=parsed.get("reason_code"),
        scope=parsed.get("scope"),
        direction=parsed.get("direction"),
        metric=parsed.get("metric"),
        magnitude_pct=parsed.get("magnitude_pct"),
        confidence=parsed.get("confidence", 0.0),
        target_layer=parsed.get("target_layer", "operational"),
        layer_description=parsed.get("layer_description", ""),
        missing_fields=[MissingField(**m) for m in missing],
        is_complete=len(missing) == 0,
    )


@router.post("/submit", response_model=DirectiveResponse)
async def submit_directive(
    request: DirectiveSubmitRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Submit a natural language directive for LLM parsing and Powell routing.

    Accepts optional clarifications dict (field→value) from the clarification
    flow. These are merged into the directive text before LLM parsing so the
    final parse has complete information.
    """
    service = DirectiveService(db)
    directive = await service.submit_directive(
        user=current_user,
        config_id=request.config_id,
        raw_text=request.text,
        clarifications=request.clarifications,
        scenario_event_id=request.scenario_event_id,
        target_config_id=request.target_config_id,
    )
    return DirectiveResponse(**directive.to_dict())


@router.get("/")
async def list_directives(
    config_id: Optional[int] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """List recent directives for the current user's tenant."""
    service = DirectiveService(db)
    directives = await service.get_directives(
        tenant_id=current_user.tenant_id,
        config_id=config_id,
        limit=limit,
    )
    return [d.to_dict() for d in directives]


@router.get("/{directive_id}")
async def get_directive(
    directive_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get a single directive by ID."""
    from sqlalchemy import select
    from app.models.user_directive import UserDirective

    stmt = select(UserDirective).where(
        UserDirective.id == directive_id,
        UserDirective.tenant_id == current_user.tenant_id,
    )
    result = await db.execute(stmt)
    directive = result.scalar_one_or_none()
    if not directive:
        raise HTTPException(status_code=404, detail="Directive not found")
    return directive.to_dict()
