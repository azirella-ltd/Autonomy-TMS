"""
Decision Stream WebSocket Endpoint

Provides real-time push notifications for:
- CDC trigger events
- Condition monitor alerts
- Decision status changes

Tenant-scoped: clients only receive events for their own tenant.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from typing import Dict, Set
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class DecisionStreamConnectionManager:
    """Manages WebSocket connections per tenant for decision stream events."""

    def __init__(self):
        # tenant_id -> set of WebSocket connections
        self.connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, tenant_id: int, websocket: WebSocket):
        await websocket.accept()
        if tenant_id not in self.connections:
            self.connections[tenant_id] = set()
        self.connections[tenant_id].add(websocket)
        logger.info(f"Decision stream WS connected for tenant {tenant_id}")

    def disconnect(self, tenant_id: int, websocket: WebSocket):
        if tenant_id in self.connections:
            self.connections[tenant_id].discard(websocket)
            if not self.connections[tenant_id]:
                del self.connections[tenant_id]
        logger.info(f"Decision stream WS disconnected for tenant {tenant_id}")

    async def broadcast_to_tenant(self, tenant_id: int, message: dict):
        """Push an event to all connected clients for a tenant."""
        if tenant_id not in self.connections:
            return
        dead = []
        for ws in self.connections[tenant_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections[tenant_id].discard(ws)


# Singleton
ds_manager = DecisionStreamConnectionManager()


@router.websocket("/ws/decision-stream/{tenant_id}")
async def decision_stream_ws(
    websocket: WebSocket,
    tenant_id: int,
):
    """
    WebSocket endpoint for real-time decision stream events.

    Clients connect with their tenant_id and receive:
    - cdc_trigger: New CDC trigger fired
    - condition_alert: Condition monitor threshold breach
    - decision_update: Decision status changed (another user acted)
    """
    await ds_manager.connect(tenant_id, websocket)
    try:
        while True:
            # Keep connection alive; handle client pings
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ds_manager.disconnect(tenant_id, websocket)
    except Exception as e:
        logger.error(f"Decision stream WS error: {e}")
        ds_manager.disconnect(tenant_id, websocket)
