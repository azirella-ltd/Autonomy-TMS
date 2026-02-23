"""
Authorization Protocol API Endpoints

Exposes the Agentic Authorization Protocol (AAP) for the frontend
Authorization Protocol Board.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.api.deps import get_current_user
from app.services.authorization_protocol import (
    AUTHORITY_MAP,
    ActionCategory,
    AgentRole,
    AuthorizationThread,
)

router = APIRouter(prefix="/authorization-protocol", tags=["authorization-protocol"])

# In-memory thread store (production would use DB)
_threads: Dict[str, AuthorizationThread] = {}


def _seed_demo_threads() -> None:
    """Create sample threads for demo/visualization purposes."""
    if _threads:
        return

    from app.services.authorization_protocol import (
        AuthorizationRequest,
        AuthorizationResponse,
        AuthorizationDecision,
        AuthorizationPriority,
        ProposedAction,
        BalancedScorecard,
        ScorecardDelta,
    )

    # Thread 1: Active — SO/ATP requesting expedite from Logistics
    t1 = AuthorizationThread()
    req1 = AuthorizationRequest(
        requesting_agent=AgentRole.SO_ATP,
        target_agent=AgentRole.LOGISTICS,
        site_key="plant_chicago",
        priority=AuthorizationPriority.HIGH,
        proposed_action=ProposedAction(
            action_type="request_expedite",
            description="Expedite PO-4821 delivery from 5 days to 2 days for priority customer",
            parameters={"po_id": "PO-4821", "original_days": 5, "target_days": 2},
        ),
        balanced_scorecard=BalancedScorecard(metrics=[
            ScorecardDelta(metric="otif_segment_a", quadrant="customer", baseline=0.92, projected=0.97, delta=0.05, weight=1.5, direction=1, unit="%"),
            ScorecardDelta(metric="expedite_cost", quadrant="financial", baseline=0, projected=1200, delta=1200, weight=1.0, direction=-1, unit="USD"),
            ScorecardDelta(metric="carrier_utilization", quadrant="operational", baseline=0.78, projected=0.85, delta=0.07, weight=0.8, direction=1, unit="%"),
        ]),
        benefit_threshold=0.02,
        justification="Priority A customer order at risk of missing SLA. Expedite cost offset by retention value.",
    )
    t1.submit_request(req1)

    # Thread 2: Resolved — Plant requesting overtime from Finance
    t2 = AuthorizationThread()
    req2 = AuthorizationRequest(
        requesting_agent=AgentRole.PLANT,
        target_agent=AgentRole.FINANCE,
        site_key="plant_detroit",
        priority=AuthorizationPriority.MEDIUM,
        proposed_action=ProposedAction(
            action_type="overtime_authorization",
            description="Authorize 40h weekend overtime to clear production backlog",
            parameters={"hours": 40, "cost_per_hour": 85},
        ),
        balanced_scorecard=BalancedScorecard(metrics=[
            ScorecardDelta(metric="backlog_units", quadrant="operational", baseline=1200, projected=400, delta=-800, weight=1.2, direction=-1, unit="units"),
            ScorecardDelta(metric="labor_cost", quadrant="financial", baseline=0, projected=3400, delta=3400, weight=1.0, direction=-1, unit="USD"),
            ScorecardDelta(metric="on_time_delivery", quadrant="customer", baseline=0.88, projected=0.95, delta=0.07, weight=1.3, direction=1, unit="%"),
        ]),
        benefit_threshold=0.01,
        justification="Production backlog growing 200 units/day. Weekend overtime clears 800 units.",
    )
    t2.submit_request(req2)
    resp2 = AuthorizationResponse(
        request_id=req2.request_id,
        decision=AuthorizationDecision.AUTHORIZE,
        responding_agent=AgentRole.FINANCE,
        reason="Within delegation authority. Backlog reduction justifies cost.",
    )
    t2.add_response(resp2)

    # Thread 3: Resolved — Denied cross-DC transfer
    t3 = AuthorizationThread()
    req3 = AuthorizationRequest(
        requesting_agent=AgentRole.INVENTORY,
        target_agent=AgentRole.LOGISTICS,
        site_key="dc_east",
        priority=AuthorizationPriority.LOW,
        proposed_action=ProposedAction(
            action_type="cross_dc_transfer",
            description="Transfer 500 units SKU-A from DC-West to DC-East",
            parameters={"sku": "SKU-A", "from": "dc_west", "to": "dc_east", "qty": 500},
        ),
        balanced_scorecard=BalancedScorecard(metrics=[
            ScorecardDelta(metric="transport_cost", quadrant="financial", baseline=0, projected=2800, delta=2800, weight=1.0, direction=-1, unit="USD"),
            ScorecardDelta(metric="dos_dc_east", quadrant="operational", baseline=8, projected=15, delta=7, weight=0.5, direction=1, unit="days"),
        ]),
        benefit_threshold=0.05,
        justification="DC-East low on SKU-A but demand forecast is moderate.",
    )
    t3.submit_request(req3)
    resp3 = AuthorizationResponse(
        request_id=req3.request_id,
        decision=AuthorizationDecision.DENY,
        responding_agent=AgentRole.LOGISTICS,
        reason="Net benefit below threshold. Demand at DC-East not urgent enough to justify transfer cost.",
    )
    t3.add_response(resp3)

    _threads[t1.thread_id] = t1
    _threads[t2.thread_id] = t2
    _threads[t3.thread_id] = t3


@router.get("/threads")
async def get_threads(
    current_user: User = Depends(get_current_user),
):
    """Get all authorization threads."""
    _seed_demo_threads()
    return {
        "threads": [t.to_dict() for t in _threads.values()],
        "total": len(_threads),
    }


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a single thread by ID."""
    _seed_demo_threads()
    thread = _threads.get(thread_id)
    if not thread:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return thread.to_dict()


@router.get("/authority-map")
async def get_authority_map(
    current_user: User = Depends(get_current_user),
):
    """Get the full authority map for all agent roles."""
    return {
        "authority_map": {
            role.value: {
                action: cat.value
                for action, cat in actions.items()
            }
            for role, actions in AUTHORITY_MAP.items()
        },
    }


@router.get("/stats")
async def get_stats(
    current_user: User = Depends(get_current_user),
):
    """Get aggregated stats for the authorization protocol."""
    _seed_demo_threads()
    all_threads = list(_threads.values())
    resolved = [t for t in all_threads if t.is_resolved]
    active = [t for t in all_threads if not t.is_resolved]

    decisions_by_type: Dict[str, int] = {}
    top_requesters: Dict[str, int] = {}
    total_duration = 0.0
    duration_count = 0

    for t in resolved:
        if t.final_decision:
            d = t.final_decision.value
            decisions_by_type[d] = decisions_by_type.get(d, 0) + 1
        if t.duration_seconds is not None:
            total_duration += t.duration_seconds
            duration_count += 1

    for t in all_threads:
        if t.request:
            agent = t.request.requesting_agent.value
            top_requesters[agent] = top_requesters.get(agent, 0) + 1

    deny_count = decisions_by_type.get("deny", 0)
    total_resolved = len(resolved)

    return {
        "active_threads": len(active),
        "resolved_threads": total_resolved,
        "auto_resolved": sum(1 for t in resolved if t.resolution_source == "agent"),
        "escalated": sum(1 for t in resolved if t.resolution_source == "human"),
        "avg_resolution_seconds": total_duration / duration_count if duration_count > 0 else None,
        "deny_rate": deny_count / total_resolved if total_resolved > 0 else None,
        "decisions_by_type": decisions_by_type,
        "top_requesters": [
            {"agent": agent, "count": count}
            for agent, count in sorted(top_requesters.items(), key=lambda x: -x[1])
        ],
    }
