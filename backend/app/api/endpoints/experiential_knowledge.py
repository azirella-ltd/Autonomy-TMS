"""Experiential Knowledge API — Structured behavioral knowledge from override patterns.

Manages EK entities: CRUD, lifecycle actions (validate, classify, confirm,
resolve contradictions), pattern detection trigger, and stats.
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_db, require_tenant_admin
from app.models.user import User
from app.models.experiential_knowledge import ExperientialKnowledge
from app.db.session import sync_session_factory

router = APIRouter(prefix="/experiential-knowledge", tags=["Experiential Knowledge"])
logger = logging.getLogger(__name__)


# ── Pydantic Models ─────────────────────────────────────────────────────────

class EKCreateRequest(BaseModel):
    config_id: int
    entity_type: str = Field(..., max_length=50)
    entity_ids: dict
    pattern_type: str = Field(..., max_length=80)
    conditions: dict = Field(default_factory=dict)
    effect: dict
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    knowledge_type: Optional[str] = Field(None, pattern="^(GENUINE|COMPENSATING)$")
    knowledge_type_rationale: Optional[str] = None
    source_type: str = Field(default="MANUAL_ENTRY", max_length=30)
    trm_types_affected: List[str] = Field(default_factory=list)
    state_feature_names: List[str] = Field(default_factory=list)
    reward_shaping_bonus: float = Field(default=0.05, ge=0.0, le=0.1)
    cdt_uncertainty_multiplier: float = Field(default=1.0, ge=1.0, le=3.0)
    stale_after_days: int = Field(default=180, ge=1)
    summary: str = Field(..., min_length=5)


class EKClassifyRequest(BaseModel):
    knowledge_type: str = Field(..., pattern="^(GENUINE|COMPENSATING)$")
    rationale: str = Field(..., min_length=5)


class EKConfirmRequest(BaseModel):
    knowledge_type: Optional[str] = Field(None, pattern="^(GENUINE|COMPENSATING)$")
    rationale: Optional[str] = None


class EKRetireRequest(BaseModel):
    reason: str = Field(..., min_length=5)


class EKResolveRequest(BaseModel):
    winner_id: int
    loser_id: int


class EKResponse(BaseModel):
    id: int
    tenant_id: int
    config_id: int
    entity_type: str
    entity_ids: dict
    pattern_type: str
    conditions: dict
    effect: dict
    confidence: float
    knowledge_type: Optional[str]
    knowledge_type_rationale: Optional[str]
    source_type: str
    evidence: list
    source_user_ids: list
    trm_types_affected: list
    state_feature_names: list
    reward_shaping_bonus: float
    cdt_uncertainty_multiplier: float
    status: str
    stale_after_days: int
    last_validated_at: Optional[str]
    summary: str
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


def _to_response(ek: ExperientialKnowledge) -> dict:
    """Convert EK entity to response dict."""
    return {
        "id": ek.id,
        "tenant_id": ek.tenant_id,
        "config_id": ek.config_id,
        "entity_type": ek.entity_type,
        "entity_ids": ek.entity_ids,
        "pattern_type": ek.pattern_type,
        "conditions": ek.conditions,
        "effect": ek.effect,
        "confidence": ek.confidence,
        "knowledge_type": ek.knowledge_type,
        "knowledge_type_rationale": ek.knowledge_type_rationale,
        "source_type": ek.source_type,
        "evidence": ek.evidence or [],
        "source_user_ids": ek.source_user_ids or [],
        "trm_types_affected": ek.trm_types_affected or [],
        "state_feature_names": ek.state_feature_names or [],
        "reward_shaping_bonus": ek.reward_shaping_bonus,
        "cdt_uncertainty_multiplier": ek.cdt_uncertainty_multiplier,
        "status": ek.status,
        "stale_after_days": ek.stale_after_days,
        "last_validated_at": ek.last_validated_at.isoformat() if ek.last_validated_at else None,
        "summary": ek.summary,
        "created_at": ek.created_at.isoformat() if ek.created_at else None,
        "updated_at": ek.updated_at.isoformat() if ek.updated_at else None,
    }


def _get_service(user: User, config_id: Optional[int] = None):
    """Create sync service instance for the current tenant."""
    from app.services.experiential_knowledge_service import ExperientialKnowledgeService
    db = sync_session_factory()
    return ExperientialKnowledgeService(
        db=db,
        tenant_id=user.tenant_id,
        config_id=config_id,
    ), db


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/")
async def list_entities(
    status: Optional[str] = Query(None),
    pattern_type: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    trm_type: Optional[str] = Query(None),
    config_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_tenant_admin),
):
    svc, db = _get_service(current_user, config_id)
    try:
        entities, total = svc.list_entities(
            status=status, pattern_type=pattern_type,
            entity_type=entity_type, trm_type=trm_type,
            limit=limit, offset=offset,
        )
        return {
            "items": [_to_response(e) for e in entities],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    finally:
        db.close()


@router.get("/candidates")
async def list_candidates(
    config_id: Optional[int] = Query(None),
    current_user: User = Depends(require_tenant_admin),
):
    svc, db = _get_service(current_user, config_id)
    try:
        entities, total = svc.list_entities(status="CANDIDATE")
        return {"items": [_to_response(e) for e in entities], "total": total}
    finally:
        db.close()


@router.get("/stale")
async def list_stale(
    config_id: Optional[int] = Query(None),
    current_user: User = Depends(require_tenant_admin),
):
    svc, db = _get_service(current_user, config_id)
    try:
        entities, total = svc.list_entities(status="STALE")
        return {"items": [_to_response(e) for e in entities], "total": total}
    finally:
        db.close()


@router.get("/contradictions")
async def list_contradictions(
    config_id: Optional[int] = Query(None),
    current_user: User = Depends(require_tenant_admin),
):
    svc, db = _get_service(current_user, config_id)
    try:
        entities, total = svc.list_entities(status="CONTRADICTED")
        return {"items": [_to_response(e) for e in entities], "total": total}
    finally:
        db.close()


@router.get("/stats")
async def get_stats(
    config_id: Optional[int] = Query(None),
    current_user: User = Depends(require_tenant_admin),
):
    svc, db = _get_service(current_user, config_id)
    try:
        return svc.get_stats()
    finally:
        db.close()


@router.get("/{ek_id}")
async def get_entity(
    ek_id: int,
    current_user: User = Depends(require_tenant_admin),
):
    svc, db = _get_service(current_user)
    try:
        ek = svc.get_by_id(ek_id)
        if not ek:
            raise HTTPException(status_code=404, detail="Entity not found")
        return _to_response(ek)
    finally:
        db.close()


@router.post("/")
async def create_entity(
    request: EKCreateRequest,
    current_user: User = Depends(require_tenant_admin),
):
    svc, db = _get_service(current_user, request.config_id)
    try:
        ek = ExperientialKnowledge(
            tenant_id=current_user.tenant_id,
            config_id=request.config_id,
            entity_type=request.entity_type,
            entity_ids=request.entity_ids,
            pattern_type=request.pattern_type,
            conditions=request.conditions,
            effect=request.effect,
            confidence=request.confidence,
            knowledge_type=request.knowledge_type,
            knowledge_type_rationale=request.knowledge_type_rationale,
            source_type=request.source_type,
            evidence=[],
            source_user_ids=[current_user.id],
            trm_types_affected=request.trm_types_affected,
            state_feature_names=request.state_feature_names,
            reward_shaping_bonus=request.reward_shaping_bonus,
            cdt_uncertainty_multiplier=request.cdt_uncertainty_multiplier,
            stale_after_days=request.stale_after_days,
            status="ACTIVE" if request.knowledge_type else "CANDIDATE",
            last_validated_at=datetime.utcnow() if request.knowledge_type else None,
            validated_by_id=current_user.id if request.knowledge_type else None,
            summary=request.summary,
        )
        db.add(ek)
        db.commit()
        db.refresh(ek)
        return _to_response(ek)
    finally:
        db.close()


@router.put("/{ek_id}/validate")
async def validate_entity(
    ek_id: int,
    current_user: User = Depends(require_tenant_admin),
):
    svc, db = _get_service(current_user)
    try:
        ek = svc.validate_entity(ek_id, current_user.id)
        if not ek:
            raise HTTPException(status_code=404, detail="Entity not found")
        return _to_response(ek)
    finally:
        db.close()


@router.put("/{ek_id}/classify")
async def classify_entity(
    ek_id: int,
    request: EKClassifyRequest,
    current_user: User = Depends(require_tenant_admin),
):
    svc, db = _get_service(current_user)
    try:
        ek = svc.classify_entity(ek_id, request.knowledge_type, request.rationale)
        if not ek:
            raise HTTPException(status_code=404, detail="Entity not found")
        return _to_response(ek)
    finally:
        db.close()


@router.post("/{ek_id}/confirm")
async def confirm_candidate(
    ek_id: int,
    request: EKConfirmRequest,
    current_user: User = Depends(require_tenant_admin),
):
    svc, db = _get_service(current_user)
    try:
        ek = svc.confirm_candidate(
            ek_id, current_user.id,
            knowledge_type=request.knowledge_type,
            rationale=request.rationale,
        )
        if not ek:
            raise HTTPException(status_code=404, detail="Entity not found or not CANDIDATE")
        return _to_response(ek)
    finally:
        db.close()


@router.put("/{ek_id}/retire")
async def retire_entity(
    ek_id: int,
    request: EKRetireRequest,
    current_user: User = Depends(require_tenant_admin),
):
    svc, db = _get_service(current_user)
    try:
        ek = svc.retire_entity(ek_id, request.reason)
        if not ek:
            raise HTTPException(status_code=404, detail="Entity not found")
        return _to_response(ek)
    finally:
        db.close()


@router.put("/resolve-contradiction")
async def resolve_contradiction(
    request: EKResolveRequest,
    current_user: User = Depends(require_tenant_admin),
):
    svc, db = _get_service(current_user)
    try:
        winner = svc.resolve_contradiction(request.winner_id, request.loser_id)
        if not winner:
            raise HTTPException(status_code=404, detail="One or both entities not found")
        return _to_response(winner)
    finally:
        db.close()


@router.post("/detect-now")
async def detect_patterns_now(
    config_id: Optional[int] = Query(None),
    lookback_days: int = Query(90, ge=1, le=365),
    current_user: User = Depends(require_tenant_admin),
):
    svc, db = _get_service(current_user, config_id)
    try:
        result = svc.detect_patterns(lookback_days=lookback_days)
        lifecycle = svc.check_lifecycle()
        return {
            "detection": result,
            "lifecycle": lifecycle,
        }
    finally:
        db.close()
