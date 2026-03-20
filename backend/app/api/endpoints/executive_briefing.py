"""
Executive Briefing API Endpoints

LLM-synthesized strategy briefings for senior executives.
Supports async generation, follow-up questions, scheduling, and history.

Endpoints:
- POST /generate: Start async briefing generation
- GET /latest: Most recent completed briefing
- GET /history: Paginated briefing list
- GET /{briefing_id}: Specific briefing with follow-ups
- POST /{briefing_id}/ask: Ask follow-up question
- GET /schedule/config: Get schedule config
- PUT /schedule/config: Update schedule config
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_tenant_id(db: Session, current_user: User) -> int:
    """Resolve effective tenant_id. System admins may lack tenant; fall back to first tenant."""
    if current_user.tenant_id:
        return current_user.tenant_id
    from sqlalchemy import text
    row = db.execute(text("SELECT id FROM tenants ORDER BY id LIMIT 1")).fetchone()
    if row:
        return row[0]
    raise HTTPException(status_code=400, detail="No tenant available. Create a tenant first.")


# =============================================================================
# Request/Response Models
# =============================================================================

class BriefingGenerateRequest(BaseModel):
    briefing_type: str = Field(default="adhoc", description="Briefing type: daily, weekly, monthly, adhoc")
    verbosity: str = Field(default="normal", description="Briefing verbosity: terse, normal, verbose")


class FollowupRequest(BaseModel):
    question: str = Field(..., min_length=5, max_length=2000, description="Follow-up question")


class ScheduleUpdateRequest(BaseModel):
    enabled: bool = Field(default=True)
    briefing_type: str = Field(default="weekly")
    cron_day_of_week: str = Field(default="mon")
    cron_hour: int = Field(default=6, ge=0, le=23)
    cron_minute: int = Field(default=0, ge=0, le=59)


# =============================================================================
# Background task for async generation
# =============================================================================

async def _generate_in_background(briefing_id: int):
    """Run briefing generation as a background task on an existing record."""
    from app.db.session import sync_session_factory
    from app.models.executive_briefing import ExecutiveBriefing
    from app.services.executive_briefing_service import ExecutiveBriefingService

    db = sync_session_factory()
    try:
        briefing = db.query(ExecutiveBriefing).filter(ExecutiveBriefing.id == briefing_id).first()
        if not briefing:
            logger.error("Background generation: briefing %d not found", briefing_id)
            return
        service = ExecutiveBriefingService(db)
        await service.run_generation(briefing)
    except Exception as e:
        logger.error("Background briefing generation failed for %d: %s", briefing_id, e)
    finally:
        db.close()


def _run_generation_background(briefing_id: int):
    """Wrapper to run async generation from sync BackgroundTasks."""
    asyncio.run(_generate_in_background(briefing_id))


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/generate")
async def generate_briefing(
    request: BriefingGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Start executive briefing generation.

    Creates a briefing record immediately and starts LLM synthesis
    in the background. Poll GET /{briefing_id} for completion.
    """
    from app.models.executive_briefing import ExecutiveBriefing

    tenant_id = _resolve_tenant_id(db, current_user)

    # Validate briefing_type
    valid_types = {"daily", "weekly", "monthly", "adhoc"}
    if request.briefing_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"briefing_type must be one of: {valid_types}")

    # Validate verbosity
    valid_verbosities = {"terse", "normal", "verbose"}
    verbosity = request.verbosity if request.verbosity in valid_verbosities else "normal"

    # Create pending record
    briefing = ExecutiveBriefing(
        tenant_id=tenant_id,
        requested_by=current_user.id,
        briefing_type=request.briefing_type,
        status="pending",
    )
    # Store verbosity in data_pack for the background task to read
    briefing.data_pack = {"_verbosity": verbosity}
    db.add(briefing)
    db.flush()
    briefing_id = briefing.id
    db.commit()

    # Schedule background generation
    background_tasks.add_task(_run_generation_background, briefing_id)

    return {
        "success": True,
        "briefing_id": briefing_id,
        "status": "pending",
        "message": "Briefing generation started. Poll GET /{briefing_id} for completion.",
    }


@router.get("/latest")
async def get_latest_briefing(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the most recent completed briefing."""
    from app.services.executive_briefing_service import ExecutiveBriefingService

    tenant_id = _resolve_tenant_id(db, current_user)
    service = ExecutiveBriefingService(db)
    briefing = service.get_latest(tenant_id)

    if not briefing:
        return {"success": True, "data": None, "message": "No briefings found. Generate one first."}

    return {"success": True, "data": briefing}


@router.get("/history")
async def list_briefings(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    briefing_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List past briefings with pagination."""
    from app.services.executive_briefing_service import ExecutiveBriefingService

    tenant_id = _resolve_tenant_id(db, current_user)
    service = ExecutiveBriefingService(db)
    briefings = service.list_briefings(tenant_id, limit, offset, briefing_type)

    return {"success": True, "data": briefings, "count": len(briefings)}


@router.get("/schedule/config")
async def get_schedule(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get briefing schedule configuration."""
    from app.services.executive_briefing_service import ExecutiveBriefingService

    tenant_id = _resolve_tenant_id(db, current_user)
    service = ExecutiveBriefingService(db)
    schedule = service.get_schedule(tenant_id)

    return {"success": True, "data": schedule}


@router.put("/schedule/config")
async def update_schedule(
    request: ScheduleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update briefing schedule configuration."""
    from app.services.executive_briefing_service import ExecutiveBriefingService

    tenant_id = _resolve_tenant_id(db, current_user)
    service = ExecutiveBriefingService(db)

    config = request.model_dump()
    schedule = service.update_schedule(tenant_id, config)

    return {"success": True, "data": schedule, "message": "Schedule updated"}


@router.get("/{briefing_id}")
async def get_briefing(
    briefing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific briefing with follow-ups."""
    from app.services.executive_briefing_service import ExecutiveBriefingService

    tenant_id = _resolve_tenant_id(db, current_user)
    service = ExecutiveBriefingService(db)
    briefing = service.get_briefing(briefing_id, tenant_id)

    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    return {"success": True, "data": briefing}


@router.post("/{briefing_id}/ask")
async def ask_followup(
    briefing_id: int,
    request: FollowupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ask a follow-up question about a briefing."""
    from app.services.executive_briefing_service import ExecutiveBriefingService

    tenant_id = _resolve_tenant_id(db, current_user)
    service = ExecutiveBriefingService(db)

    try:
        followup = await service.ask_followup(
            briefing_id, tenant_id, request.question, current_user.id,
        )
        return {"success": True, "data": followup}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Follow-up failed for briefing %d: %s", briefing_id, e)
        raise HTTPException(status_code=500, detail="Failed to process follow-up question")
