"""
Planning Scenarios API — Branch, evaluate, promote, and compare planning scenarios.

Provides REST endpoints for the scenario tree lifecycle:
  POST /scenarios/root — create root scenario
  POST /scenarios/branch — create branch from parent
  POST /scenarios/{id}/evaluate — run what-if evaluation
  POST /scenarios/{id}/promote — promote winning scenario
  GET  /scenarios/{root_id}/tree — get full scenario tree
  GET  /scenarios/compare — compare balanced scorecards
  GET  /scenarios/{id} — get single scenario
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.scenario_tree_service import ScenarioTreeService
from app.services.hive_what_if_engine import HiveWhatIfEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scenarios", tags=["planning-scenarios"])


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------

class CreateRootRequest(BaseModel):
    name: str
    config_id: Optional[int] = None
    description: Optional[str] = None
    created_by: Optional[str] = None


class CreateBranchRequest(BaseModel):
    parent_id: int
    name: str
    variable_deltas: Optional[dict] = None
    description: Optional[str] = None
    created_by: Optional[str] = None


class EvaluateRequest(BaseModel):
    num_periods: int = Field(default=12, ge=1, le=104)
    site_key: str = "default"


class PromoteRequest(BaseModel):
    rationale: Optional[str] = None
    decided_by: Optional[str] = None


class ScenarioResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    parent_scenario_id: Optional[int] = None
    root_scenario_id: Optional[int] = None
    depth: int = 0
    status: Optional[str] = None
    variable_deltas: Optional[dict] = None
    balanced_scorecard: Optional[dict] = None
    net_benefit: Optional[float] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Service factory (in-memory for now, DB when available)
# ---------------------------------------------------------------------------

def get_tree_service() -> ScenarioTreeService:
    """Factory for ScenarioTreeService.

    Uses in-memory store.  When DB session is available,
    pass it via dependency injection.
    """
    return ScenarioTreeService(db=None)


def get_what_if_engine(site_key: str = "default") -> HiveWhatIfEngine:
    """Factory for HiveWhatIfEngine."""
    return HiveWhatIfEngine(site_key=site_key)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/root", response_model=ScenarioResponse)
def create_root(
    request: CreateRootRequest,
    service: ScenarioTreeService = Depends(get_tree_service),
):
    """Create a root (baseline) planning scenario."""
    scenario = service.create_root(
        name=request.name,
        config_id=request.config_id,
        description=request.description,
        created_by=request.created_by,
    )
    return scenario.to_dict()


@router.post("/branch", response_model=ScenarioResponse)
def create_branch(
    request: CreateBranchRequest,
    service: ScenarioTreeService = Depends(get_tree_service),
):
    """Create a branch from an existing scenario."""
    try:
        scenario = service.create_branch(
            parent_id=request.parent_id,
            name=request.name,
            variable_deltas=request.variable_deltas,
            description=request.description,
            created_by=request.created_by,
        )
        return scenario.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{scenario_id}/evaluate")
def evaluate_scenario(
    scenario_id: int,
    request: EvaluateRequest,
    service: ScenarioTreeService = Depends(get_tree_service),
):
    """Run what-if evaluation on a scenario."""
    engine = get_what_if_engine(request.site_key)
    try:
        scorecard = service.evaluate(
            scenario_id=scenario_id,
            engine=engine,
            num_periods=request.num_periods,
        )
        scenario = service.get(scenario_id)
        return {
            "scenario_id": scenario_id,
            "status": scenario.status.value if scenario else None,
            "balanced_scorecard": scorecard,
            "net_benefit": scenario.net_benefit if scenario else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{scenario_id}/promote")
def promote_scenario(
    scenario_id: int,
    request: PromoteRequest,
    service: ScenarioTreeService = Depends(get_tree_service),
):
    """Promote a scenario and prune its siblings."""
    try:
        record = service.promote(
            scenario_id=scenario_id,
            rationale=request.rationale,
            decided_by=request.decided_by,
        )
        return record.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{root_id}/tree")
def get_tree(
    root_id: int,
    service: ScenarioTreeService = Depends(get_tree_service),
):
    """Get the full scenario tree rooted at root_id."""
    tree = service.get_tree(root_id)
    if not tree:
        raise HTTPException(status_code=404, detail=f"Root scenario {root_id} not found")
    return {"root_id": root_id, "scenarios": tree}


@router.get("/compare")
def compare_scenarios(
    ids: str = Query(..., description="Comma-separated scenario IDs"),
    service: ScenarioTreeService = Depends(get_tree_service),
):
    """Compare balanced scorecards across multiple scenarios."""
    scenario_ids = [int(x.strip()) for x in ids.split(",")]
    comparison = service.compare(scenario_ids)
    return {"comparison": comparison}


@router.get("/{scenario_id}", response_model=ScenarioResponse)
def get_scenario(
    scenario_id: int,
    service: ScenarioTreeService = Depends(get_tree_service),
):
    """Get a single scenario by ID."""
    scenario = service.get(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    return scenario.to_dict()
