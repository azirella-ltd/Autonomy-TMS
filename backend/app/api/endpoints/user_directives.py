"""User Directive API endpoints — "Talk to Me" natural language context capture.

Accepts natural language directives from authenticated users, parses them
with LLM, routes to the appropriate Powell layer based on role, and tracks
effectiveness via Bayesian posteriors.

Three endpoints:
  1. POST /directives/analyze       — LLM parse, return structured result + missing fields
  2. POST /directives/submit        — persist and route (standard directives)
  3. POST /directives/submit-stream — persist and route compound actions with SSE progress
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import get_async_db
from app.models.user import User
from app.services.directive_service import DirectiveService

router = APIRouter(prefix="/directives", tags=["Directives"])
logger = logging.getLogger(__name__)


def _sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """Format a Server-Sent Event line pair."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# ── Request / Response models ────────────────────────────────────────────────

class DirectiveAnalyzeRequest(BaseModel):
    config_id: int
    text: str = Field(..., min_length=3, max_length=5000)


class MissingField(BaseModel):
    field: str
    question: str
    type: str  # "text" | "select" | "number"
    options: Optional[List[str]] = None


class CompoundAction(BaseModel):
    """A single action within a compound intent (demand signal or directive)."""
    action_type: str  # "demand_signal" | "directive"
    demand_signal_type: Optional[str] = None  # "order" | "forecast_change"
    scenario_event: Optional[dict] = None
    directive_type: Optional[str] = None
    reason_code: Optional[str] = None
    direction: Optional[str] = None
    metric: Optional[str] = None
    magnitude_pct: Optional[float] = None
    scope: Optional[dict] = None
    target_trm_types: Optional[list] = None
    confidence: Optional[float] = None
    missing_fields: List[MissingField] = []


class DirectiveAnalyzeResponse(BaseModel):
    # Common fields
    intent: Optional[str] = None  # directive | question | scenario_event | scenario_question | compound | unknown
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

    # Rephrased prompt — shown as editable text when fields are missing
    # Contains the user's input rewritten with canonical names and "?" for gaps
    rephrased_prompt: Optional[str] = None

    # Compound action fields
    actions: Optional[List[CompoundAction]] = None

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

    # Compound flow — demand signal + directive
    if intent == "compound":
        actions_raw = parsed.get("actions", [])
        all_missing = parsed.get("missing_fields", [])
        compound_actions = []
        for a in actions_raw:
            action_missing = a.get("missing_fields", [])
            compound_actions.append(CompoundAction(
                action_type=a.get("action_type", "unknown"),
                demand_signal_type=a.get("demand_signal_type"),
                scenario_event=a.get("scenario_event"),
                directive_type=a.get("directive_type"),
                reason_code=a.get("reason_code"),
                direction=a.get("direction"),
                metric=a.get("metric"),
                magnitude_pct=a.get("magnitude_pct"),
                scope=a.get("scope"),
                target_trm_types=a.get("target_trm_types"),
                confidence=a.get("confidence"),
                missing_fields=[MissingField(**m) for m in action_missing],
            ))
        return DirectiveAnalyzeResponse(
            intent="compound",
            confidence=parsed.get("confidence", 0.7),
            target_layer=parsed.get("target_layer", "operational"),
            layer_description=parsed.get("layer_description", ""),
            actions=compound_actions,
            missing_fields=[MissingField(**m) for m in all_missing],
            is_complete=parsed.get("is_complete", len(all_missing) == 0),
            rephrased_prompt=parsed.get("rephrased_prompt"),
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
        rephrased_prompt=parsed.get("rephrased_prompt"),
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


class CompoundSubmitRequest(BaseModel):
    """Request body for compound submit with SSE streaming."""
    config_id: int
    text: str = Field(..., min_length=3, max_length=5000)
    actions: List[dict]  # Pre-parsed action specs from analyze
    clarifications: Optional[Dict[str, str]] = None


@router.post("/submit-stream")
async def submit_directive_stream(
    request: CompoundSubmitRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Submit a compound directive with SSE progress streaming.

    Executes each action sequentially (demand signal first, then directive)
    and streams status events to the frontend for progressive display.
    Returns text/event-stream with events: status, action_complete, complete, error.
    """
    service = DirectiveService(db)

    async def event_generator():
        try:
            actions = request.actions
            total_steps = len(actions) + 1  # N actions + summary

            yield _sse_event("status", {
                "message": f"Processing {len(actions)} actions...",
                "step": 0,
                "total": total_steps,
            })

            results = []
            for idx, action in enumerate(actions):
                action_type = action.get("action_type", "unknown")

                if action_type == "demand_signal":
                    signal_type = action.get("demand_signal_type", "order")
                    label = "new order" if signal_type == "order" else "forecast change"
                    yield _sse_event("status", {
                        "message": f"Creating {label}...",
                        "step": idx + 1,
                        "total": total_steps,
                    })

                    result = await service.execute_demand_signal_action(
                        user=current_user,
                        config_id=request.config_id,
                        action=action,
                        clarifications=request.clarifications,
                    )
                    results.append(result)

                    # Apply display name resolution to summary
                    summary = result.get("summary", "")
                    summary = await service.resolve_display_names(
                        summary, request.config_id,
                    )
                    yield _sse_event("action_complete", {
                        "action_index": idx,
                        "action_type": action_type,
                        "message": summary,
                        "result": result,
                    })

                elif action_type == "directive":
                    yield _sse_event("status", {
                        "message": f"Routing directive: {action.get('direction', '')} {action.get('metric', '')}...",
                        "step": idx + 1,
                        "total": total_steps,
                    })

                    result = await service.execute_directive_action(
                        user=current_user,
                        config_id=request.config_id,
                        action=action,
                        raw_text=request.text,
                        clarifications=request.clarifications,
                    )
                    results.append(result)

                    trm_types = result.get("target_trm_types", [])
                    trm_list = ", ".join(
                        t.replace("_", " ").title() for t in (trm_types or [])
                    )
                    yield _sse_event("action_complete", {
                        "action_index": idx,
                        "action_type": action_type,
                        "message": f"Routed to {result.get('target_layer', 'operational')} layer"
                                   + (f" — TRMs: {trm_list}" if trm_list else ""),
                        "result": result,
                    })

            yield _sse_event("complete", {
                "message": f"{len(actions)} actions completed — see Decision Stream",
                "step": total_steps,
                "total": total_steps,
                "results": results,
            })

        except Exception as e:
            logger.exception("Compound submit-stream error")
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class StrategyCompareRequest(BaseModel):
    """Request body for strategy comparison with SSE streaming."""
    config_id: int
    text: str = Field(..., min_length=3, max_length=5000)
    actions: List[dict]  # Pre-parsed compound actions from analyze
    clarifications: Optional[Dict[str, str]] = None


@router.post("/submit-strategy-stream")
async def submit_strategy_stream(
    request: StrategyCompareRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Submit a compound action with Kinaxis-style multi-scenario strategy comparison.

    Creates the demand event, runs baseline ATP, generates 2-3 candidate strategies
    via Claude Skills, evaluates each on a scenario branch, and streams the comparison
    results via Server-Sent Events.
    """
    from app.services.scenario_strategy_service import ScenarioStrategyService

    strategy_service = ScenarioStrategyService(db=db, tenant_id=current_user.tenant_id)

    # Extract demand signal and directive specs from the compound actions
    demand_action = next((a for a in request.actions if a.get("action_type") == "demand_signal"), None)
    directive_action = next((a for a in request.actions if a.get("action_type") == "directive"), None)

    if not demand_action:
        async def error_gen():
            yield _sse_event("error", {"message": "No demand signal found in compound actions"})
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    event_spec = demand_action.get("scenario_event", {})
    if not event_spec.get("event_type"):
        event_spec["event_type"] = "drop_in_order"

    async def event_generator():
        async def on_progress(event_type: str, data: Dict[str, Any]):
            """Non-yielding progress tracker — we collect events and yield them."""
            pass  # We use direct yield in the loop below instead

        try:
            # We drive the orchestration step-by-step, yielding SSE events
            # between each major step for progressive feedback.

            yield _sse_event("status", {"message": "Starting strategy comparison...", "step": 0, "total": 7})

            comparison = await strategy_service.run_strategy_comparison(
                config_id=request.config_id,
                user_id=current_user.id,
                event_spec=event_spec,
                directive_spec=directive_action,
                on_progress=_make_sse_yielder(),
            )

            # The service emits events via on_progress which we can't yield from.
            # So we run it and yield the final comparison.
            yield _sse_event("comparison_ready", comparison)
            yield _sse_event("complete", {
                "message": "Strategy comparison ready — select a strategy to execute.",
            })

        except Exception as e:
            logger.exception("Strategy stream error")
            yield _sse_event("error", {"message": str(e)})

    # Since we can't yield from within the on_progress callback (it's not a generator),
    # we use a simpler approach: collect all events, then yield them.
    # For true progressive streaming, we need a queue-based approach.
    import asyncio

    event_queue: asyncio.Queue = asyncio.Queue()

    async def queued_progress(event_type: str, data: Dict[str, Any]):
        await event_queue.put((event_type, data))

    async def stream_generator():
        # Start the comparison in a background task
        task = asyncio.create_task(
            strategy_service.run_strategy_comparison(
                config_id=request.config_id,
                user_id=current_user.id,
                event_spec=event_spec,
                directive_spec=directive_action,
                on_progress=queued_progress,
            )
        )

        # Yield events from the queue as they arrive
        try:
            while not task.done() or not event_queue.empty():
                try:
                    event_type, data = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                    yield _sse_event(event_type, data)
                except asyncio.TimeoutError:
                    continue

            # Drain any remaining events
            while not event_queue.empty():
                event_type, data = event_queue.get_nowait()
                yield _sse_event(event_type, data)

            # Check for exceptions
            if task.exception():
                yield _sse_event("error", {"message": str(task.exception())})

        except Exception as e:
            logger.exception("Strategy stream generator error")
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/promote-strategy/{scenario_id}")
async def promote_strategy(
    scenario_id: int,
    rationale: str = "",
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Promote the selected strategy — apply its changes to the active config."""
    from app.services.scenario_strategy_service import ScenarioStrategyService

    service = ScenarioStrategyService(db=db, tenant_id=current_user.tenant_id)
    result = await service.promote_strategy(
        scenario_id=scenario_id,
        rationale=rationale,
        user_id=current_user.id,
    )
    return result


def _make_sse_yielder():
    """Placeholder — not used in queue-based approach."""
    async def noop(event_type, data):
        pass
    return noop


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
