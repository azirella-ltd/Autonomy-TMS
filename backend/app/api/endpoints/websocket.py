"""
Legacy Scenario-Scoped WebSocket — Replaced by Tenant-Scoped Decision Stream

This module previously provided per-scenario WebSocket connections for real-time
Beer Game updates. It was never registered in main.py (dead code). All real-time
functionality is now served by:

  - Decision Stream WS: /ws/decision-stream/{tenant_id}
    (CDC triggers, condition alerts, decision updates)
  - Collaborative Editing WS: /api/collaborative-editing/ws/{document_id}
    (Co-editing presence, cell locks, cursor tracking)

This file is retained as a no-op stub so that existing imports (in
mixed_scenario.py, chat.py, etc.) don't break. All broadcast functions
are safe no-ops.
"""

from fastapi import APIRouter

router = APIRouter()


class ConnectionManager:
    """No-op connection manager (legacy stub)."""

    def __init__(self):
        self.active_connections = {}

    async def connect(self, *args, **kwargs):
        pass

    def disconnect(self, *args, **kwargs):
        pass

    async def broadcast_game_state(self, *args, **kwargs):
        pass

    async def send_personal_message(self, *args, **kwargs):
        pass

    async def broadcast_to_game(self, *args, **kwargs):
        pass

    async def broadcast_to_scenario(self, *args, **kwargs):
        pass


manager = ConnectionManager()


# No-op broadcast stubs — all previously defined broadcast helpers
async def broadcast_phase_change(*args, **kwargs):
    pass

async def broadcast_scenario_user_action_required(*args, **kwargs):
    pass

async def broadcast_fulfillment_completed(*args, **kwargs):
    pass

async def broadcast_replenishment_completed(*args, **kwargs):
    pass

async def broadcast_round_completed(*args, **kwargs):
    pass

async def broadcast_all_scenario_users_ready(*args, **kwargs):
    pass

async def broadcast_agent_recommendation_ready(*args, **kwargs):
    pass

async def send_override_requires_approval(*args, **kwargs):
    pass

async def broadcast_override_approved(*args, **kwargs):
    pass

async def broadcast_override_rejected(*args, **kwargs):
    pass

async def broadcast_atp_threshold_breach(*args, **kwargs):
    pass

async def broadcast_ctp_capacity_constraint(*args, **kwargs):
    pass

async def broadcast_allocation_conflict(*args, **kwargs):
    pass

async def broadcast_atp_projection_update(*args, **kwargs):
    pass

async def broadcast_component_constraint(*args, **kwargs):
    pass
