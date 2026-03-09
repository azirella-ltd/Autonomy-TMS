"""
API endpoints for the SAP Change Simulator.

Allows starting/stopping the simulator, configuring scenarios,
and triggering individual ticks (simulated days).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.sap_change_simulator import (
    ClockSpeed,
    DisruptionScenario,
    SAPChangeSimulator,
    SimulatorConfig,
    SimulatorManager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sap-simulator", tags=["SAP Change Simulator"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class SimulatorCreateRequest(BaseModel):
    config_id: int = Field(..., description="Supply chain config ID to simulate")
    tenant_id: int = Field(..., description="Tenant ID")
    clock_speed: str = Field("10x", description="Clock speed: 1x, 10x, 100x, 1000x")
    scenario: str = Field("steady_state", description="Disruption scenario")
    orders_per_day: float = Field(15.0, description="Average outbound orders per sim day")
    po_receipts_per_day: float = Field(5.0, description="Average PO receipts per sim day")


class TickRequest(BaseModel):
    num_ticks: int = Field(1, ge=1, le=100, description="Number of simulated days to execute")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/create")
async def create_simulator(
    request: SimulatorCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create and initialize a new SAP Change Simulator instance."""
    try:
        clock = ClockSpeed(request.clock_speed)
    except ValueError:
        raise HTTPException(400, f"Invalid clock_speed: {request.clock_speed}. Use 1x, 10x, 100x, 1000x")

    try:
        scenario = DisruptionScenario(request.scenario)
    except ValueError:
        raise HTTPException(400, f"Invalid scenario: {request.scenario}")

    config = SimulatorConfig(
        config_id=request.config_id,
        tenant_id=request.tenant_id,
        clock_speed=clock,
        scenario=scenario,
        orders_per_day=request.orders_per_day,
        po_receipts_per_day=request.po_receipts_per_day,
    )

    sim = await SimulatorManager.create(db=db, config=config)
    summary = await sim.start()
    return {"status": "created", **summary}


@router.post("/start")
async def start_simulator(db: AsyncSession = Depends(get_db)):
    """Start the existing simulator instance."""
    sim = SimulatorManager.get_instance()
    if not sim:
        raise HTTPException(404, "No simulator instance. Call /create first.")
    result = await sim.start()
    return result


@router.post("/stop")
async def stop_simulator():
    """Stop the running simulator."""
    result = SimulatorManager.stop()
    if not result:
        raise HTTPException(404, "No simulator running")
    return result


@router.get("/status")
async def get_status():
    """Get current simulator status."""
    return SimulatorManager.get_status()


@router.post("/tick")
async def execute_tick(
    request: TickRequest = TickRequest(),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute one or more simulated days (ticks).

    Each tick generates demand orders, supply receipts, inventory updates,
    and disruption events that feed into Autonomy's CDC pipeline.
    """
    sim = SimulatorManager.get_instance()
    if not sim:
        raise HTTPException(404, "No simulator running. Call /create first.")
    if not sim.state.is_running:
        raise HTTPException(400, "Simulator is stopped. Call /start first.")

    # Rebind the DB session for this request
    sim.db = db

    results = []
    for _ in range(request.num_ticks):
        result = await sim.tick()
        results.append(result)

    total_events = sum(r.get("events", 0) for r in results)
    return {
        "ticks_executed": len(results),
        "total_events": total_events,
        "final_sim_date": results[-1]["sim_date"] if results else None,
        "details": results if request.num_ticks <= 10 else results[:5] + [{"...": f"{len(results) - 5} more"}],
    }


@router.post("/scenario")
async def change_scenario(
    scenario: str,
    db: AsyncSession = Depends(get_db),
):
    """Change the active disruption scenario without restarting."""
    sim = SimulatorManager.get_instance()
    if not sim:
        raise HTTPException(404, "No simulator running")

    try:
        new_scenario = DisruptionScenario(scenario)
    except ValueError:
        raise HTTPException(400, f"Invalid scenario: {scenario}")

    sim.config.scenario = new_scenario
    return {"scenario": new_scenario.value, "sim_date": str(sim.state.sim_date)}
