"""TMS scenario runner API.

Wraps `services/tms_scenario_runner.py` for the three transport-native
scenario types: freight_tender, network_disruption, mode_selection.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.session import get_db
from app.api.endpoints.auth import get_current_active_user
from app.models.user import User
from app.services.tms_scenario_runner import run_tms_scenario

router = APIRouter()


class TMSScenarioRequest(BaseModel):
    scenario_type: str
    params: Optional[Dict[str, Any]] = None


@router.post("/run", response_model=Dict[str, Any])
async def run_scenario(
    body: TMSScenarioRequest,
    db=Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Run a TMS-native scenario synchronously and return the result.

    For long-running scenarios, switch to the async pattern via
    `/scenarios/run-async` (TODO when scenario size warrants it).
    """
    try:
        result = await run_tms_scenario(
            db, current_user.tenant_id, body.scenario_type, body.params or {},
        )
        return {
            "scenario_type": result.scenario_type,
            "tenant_id": result.tenant_id,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "summary": result.summary,
            "rounds": result.rounds,
            "impacts": result.impacts,
            "mode_choices": result.mode_choices,
            "warnings": result.warnings,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
