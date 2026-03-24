"""
Scenario Engine API — Machine-Speed What-If Planning Endpoints

Provides REST endpoints for creating, evaluating, comparing, promoting,
and rejecting scenario branches. These endpoints support both autonomous
agent use (triggered by TRM decisions) and manual human-initiated what-if
analysis via Azirella.

See docs/internal/SCENARIO_ENGINE.md for full architecture.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User

router = APIRouter(prefix="/scenarios", tags=["Scenario Engine"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ScenarioEvaluateRequest(BaseModel):
    """Request to create and evaluate a scenario (manual what-if)."""
    config_id: int
    trm_type: str = Field(..., description="TRM type that triggered this scenario")
    decision_level: str = Field(
        default="human_requested",
        description="execution/tactical/strategic/human_requested",
    )
    max_candidates: Optional[int] = Field(
        default=None,
        description="Max candidates to evaluate (defaults to level cap)",
    )

    # Trigger context
    product_id: Optional[str] = None
    site_id: Optional[int] = None
    quantity: Optional[float] = None
    shortfall: Optional[float] = None
    urgency: float = Field(default=0.5, ge=0.0, le=1.0)
    economic_impact: float = Field(default=10000.0, ge=0.0)
    risk_bound: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    # Context weights for BSC
    revenue_pressure_factor: float = Field(default=0.0, ge=0.0, le=1.0)
    customer_importance_factor: float = Field(default=0.0, ge=0.0, le=1.0)
    capacity_utilization_factor: float = Field(default=0.0, ge=0.0, le=1.0)
    product_importance_factor: float = Field(default=0.0, ge=0.0, le=1.0)


class ScenarioPromoteRequest(BaseModel):
    """Request to promote a winning scenario."""
    pass  # No body needed; scenario_id is in the path


class ScenarioRejectRequest(BaseModel):
    """Request to reject a scenario."""
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper: get sync session
# ---------------------------------------------------------------------------

def _get_sync_session():
    """Get a synchronous DB session for the scenario engine.

    The scenario engine uses the simulation infrastructure which requires
    synchronous DB access (reads DAG topology, writes scenario records).
    """
    from app.db.session import sync_session_factory
    db = sync_session_factory()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/evaluate")
async def evaluate_scenario(
    request: ScenarioEvaluateRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    """Create and evaluate a scenario (for manual what-if analysis).

    Generates candidate action sets from templates, simulates each via
    the digital twin, and returns BSC-scored results ranked by final score.
    """
    from app.db.session import sync_session_factory
    from app.services.powell.scenario_engine import ScenarioEngine

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with user")

    db = sync_session_factory()
    try:
        engine = ScenarioEngine(
            db=db,
            config_id=request.config_id,
            tenant_id=tenant_id,
        )

        trigger_decision = {
            "trm_type": request.trm_type,
            "risk_bound": request.risk_bound,
            "confidence": request.confidence,
            "decision_id": None,
        }

        trigger_context = {
            "product_id": request.product_id,
            "site_id": request.site_id,
            "quantity": request.quantity,
            "shortfall": request.shortfall or request.quantity,
            "urgency": request.urgency,
            "economic_impact": request.economic_impact,
            "unit_cost": 1.0,
            "unit_value": 1.5,
            "revenue_pressure_factor": request.revenue_pressure_factor,
            "customer_importance_factor": request.customer_importance_factor,
            "capacity_utilization_factor": request.capacity_utilization_factor,
            "product_importance_factor": request.product_importance_factor,
        }

        scenario, scored = engine.run_scenario_evaluation(
            trigger_decision=trigger_decision,
            trigger_context=trigger_context,
            decision_level=request.decision_level,
            max_candidates=request.max_candidates,
        )

        return {
            "scenario": scenario.to_dict(),
            "candidates": [
                {
                    "template_key": s.candidate.template_key,
                    "template_name": s.candidate.template_name,
                    "prior_likelihood": s.candidate.prior_likelihood,
                    "bsc": s.bsc.to_dict(),
                    "simulation_ticks": s.simulation_ticks,
                    "simulation_time_ms": round(s.simulation_time_ms, 1),
                }
                for s in scored
            ],
            "best_score": scored[0].bsc.final_score if scored else 0.0,
            "candidates_evaluated": len(scored),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Scenario evaluation failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/{config_id}")
async def list_scenarios(
    config_id: int,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(deps.get_current_active_user),
):
    """List recent scenarios for a config."""
    from app.db.session import sync_session_factory
    from app.services.powell.scenario_engine import ScenarioEngine

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with user")

    db = sync_session_factory()
    try:
        engine = ScenarioEngine(db=db, config_id=config_id, tenant_id=tenant_id)
        scenarios = engine.list_scenarios(status=status, limit=limit)
        return {
            "scenarios": [s.to_dict() for s in scenarios],
            "count": len(scenarios),
        }
    finally:
        db.close()


@router.get("/{scenario_id}/compare")
async def compare_scenarios(
    scenario_id: int,
    current_user: User = Depends(deps.get_current_active_user),
):
    """Compare a scenario and its siblings (alternatives from same trigger).

    Returns BSC comparison table across all scenarios that share the same
    trigger decision.
    """
    from app.db.session import sync_session_factory
    from app.models.agent_scenario import AgentScenario
    from app.services.powell.scenario_engine import ScenarioEngine

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with user")

    db = sync_session_factory()
    try:
        # Get the target scenario
        scenario = db.query(AgentScenario).filter(
            AgentScenario.id == scenario_id,
            AgentScenario.tenant_id == tenant_id,
        ).first()

        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Find sibling scenarios (same config, same trigger trm_type, recent)
        siblings = (
            db.query(AgentScenario)
            .filter(
                AgentScenario.config_id == scenario.config_id,
                AgentScenario.tenant_id == tenant_id,
                AgentScenario.trigger_trm_type == scenario.trigger_trm_type,
                AgentScenario.status.in_(["SCORED", "PROMOTED", "REJECTED"]),
            )
            .order_by(AgentScenario.created_at.desc())
            .limit(10)
            .all()
        )

        scenario_ids = list({s.id for s in siblings} | {scenario_id})

        engine = ScenarioEngine(
            db=db, config_id=scenario.config_id, tenant_id=tenant_id,
        )
        comparison = engine.compare_scenarios(scenario_ids)

        return {
            "target_scenario_id": scenario_id,
            "comparison": comparison,
            "count": len(comparison),
        }
    finally:
        db.close()


@router.post("/{scenario_id}/promote")
async def promote_scenario(
    scenario_id: int,
    current_user: User = Depends(deps.get_current_active_user),
):
    """Promote the winning scenario.

    Extracts decisions from the scenario and routes them to responsible
    agents via status change. Marks scenario as PROMOTED.
    """
    from app.db.session import sync_session_factory
    from app.services.powell.scenario_engine import ScenarioEngine
    from app.models.agent_scenario import AgentScenario

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with user")

    db = sync_session_factory()
    try:
        scenario = db.query(AgentScenario).filter(
            AgentScenario.id == scenario_id,
            AgentScenario.tenant_id == tenant_id,
        ).first()

        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        engine = ScenarioEngine(
            db=db, config_id=scenario.config_id, tenant_id=tenant_id,
        )
        promoted = engine.promote_scenario(scenario_id)
        db.commit()

        return promoted.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


@router.post("/{scenario_id}/reject")
async def reject_scenario(
    scenario_id: int,
    request: ScenarioRejectRequest = None,
    current_user: User = Depends(deps.get_current_active_user),
):
    """Reject a scenario. Retains for training data.

    Rejected scenarios are preserved — their outcomes feed back into
    template prior calibration (Beta posterior updates).
    """
    from app.db.session import sync_session_factory
    from app.services.powell.scenario_engine import ScenarioEngine
    from app.models.agent_scenario import AgentScenario

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with user")

    db = sync_session_factory()
    try:
        scenario = db.query(AgentScenario).filter(
            AgentScenario.id == scenario_id,
            AgentScenario.tenant_id == tenant_id,
        ).first()

        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        engine = ScenarioEngine(
            db=db, config_id=scenario.config_id, tenant_id=tenant_id,
        )
        rejected = engine.reject_scenario(scenario_id)
        db.commit()

        return rejected.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


@router.get("/trigger-weights/{tenant_id}")
async def get_trigger_weights(
    tenant_id: int,
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get current scenario trigger weights for a tenant."""
    from app.services.powell.scenario_trigger import ScenarioTrigger

    return ScenarioTrigger.get_trigger_weights(tenant_id)
