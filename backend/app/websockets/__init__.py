"""
Legacy WebSocket module — replaced by tenant-scoped Decision Stream WS.

See backend/app/api/endpoints/decision_stream_ws.py for the active implementation.
This module is retained as a no-op stub for backward compatibility.
"""

from fastapi import WebSocket


class ConnectionManager:
    """No-op connection manager (legacy stub)."""

    def __init__(self):
        self.active_connections = {}
        self.scenario_rooms = {}

    async def connect(self, *args, **kwargs):
        pass

    def disconnect(self, *args, **kwargs):
        pass

    async def send_personal_message(self, *args, **kwargs):
        pass

    async def broadcast(self, *args, **kwargs):
        pass

    async def send_scenario_state(self, *args, **kwargs):
        pass

    async def broadcast_scenario_state(self, *args, **kwargs):
        pass

    async def broadcast_to_scenario(self, *args, **kwargs):
        pass


manager = ConnectionManager()
