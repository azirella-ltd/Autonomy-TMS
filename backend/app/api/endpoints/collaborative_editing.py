"""
Collaborative Editing API

WebSocket-based real-time co-editing for forecasts and plans.
Supports multiple users editing the same document simultaneously.

Phase 3.6: Real-Time Co-Editing
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Set
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import json
import uuid
import asyncio
from collections import defaultdict

from app.db.session import get_db

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class CellEdit(BaseModel):
    """Single cell edit operation."""
    row_id: str
    column_id: str
    old_value: Any
    new_value: Any
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class EditOperation(BaseModel):
    """Edit operation for conflict resolution."""
    operation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str
    user_id: int
    user_name: str
    edit_type: str = Field(..., description="cell_edit, row_add, row_delete, bulk_edit")
    edits: List[CellEdit] = []
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: int = 0


class UserPresence(BaseModel):
    """User presence in a document."""
    user_id: int
    user_name: str
    cursor_position: Optional[Dict[str, str]] = None  # {row_id, column_id}
    selected_cells: List[Dict[str, str]] = []
    color: str = "#3B82F6"
    last_active: datetime = Field(default_factory=datetime.utcnow)


class DocumentSession(BaseModel):
    """Active editing session for a document."""
    document_id: str
    document_type: str  # forecast, supply_plan, mps
    version: int = 0
    users: Dict[int, UserPresence] = {}
    pending_edits: List[EditOperation] = []
    last_modified: datetime = Field(default_factory=datetime.utcnow)


class ConflictResolution(BaseModel):
    """Conflict resolution result."""
    conflict_id: str
    cell_id: str
    conflicting_edits: List[EditOperation]
    resolution: str  # last_write_wins, first_write_wins, merge, manual
    resolved_value: Any
    resolved_by: Optional[int] = None


# ============================================================================
# In-Memory Session Manager (would use Redis in production)
# ============================================================================

class CollaborativeSessionManager:
    """Manages collaborative editing sessions."""

    def __init__(self):
        self.sessions: Dict[str, DocumentSession] = {}
        self.connections: Dict[str, Dict[int, WebSocket]] = defaultdict(dict)
        self.user_colors = [
            "#3B82F6", "#EF4444", "#10B981", "#F59E0B",
            "#8B5CF6", "#EC4899", "#06B6D4", "#84CC16"
        ]
        self.locks: Dict[str, Dict[str, int]] = defaultdict(dict)  # cell_id -> user_id

    def get_session(self, document_id: str) -> Optional[DocumentSession]:
        return self.sessions.get(document_id)

    def create_session(self, document_id: str, document_type: str) -> DocumentSession:
        if document_id not in self.sessions:
            self.sessions[document_id] = DocumentSession(
                document_id=document_id,
                document_type=document_type
            )
        return self.sessions[document_id]

    def get_user_color(self, user_index: int) -> str:
        return self.user_colors[user_index % len(self.user_colors)]

    async def add_user(self, document_id: str, user_id: int, user_name: str, websocket: WebSocket):
        session = self.get_session(document_id)
        if not session:
            return None

        # Assign color
        color = self.get_user_color(len(session.users))

        # Add user presence
        session.users[user_id] = UserPresence(
            user_id=user_id,
            user_name=user_name,
            color=color
        )

        # Store websocket connection
        self.connections[document_id][user_id] = websocket

        # Broadcast user joined
        await self.broadcast(document_id, {
            "type": "user_joined",
            "user": session.users[user_id].model_dump()
        }, exclude_user=user_id)

        return session.users[user_id]

    async def remove_user(self, document_id: str, user_id: int):
        session = self.get_session(document_id)
        if session and user_id in session.users:
            del session.users[user_id]

        if document_id in self.connections and user_id in self.connections[document_id]:
            del self.connections[document_id][user_id]

        # Release any locks held by this user
        if document_id in self.locks:
            cells_to_release = [
                cell_id for cell_id, lock_user in self.locks[document_id].items()
                if lock_user == user_id
            ]
            for cell_id in cells_to_release:
                del self.locks[document_id][cell_id]

        # Broadcast user left
        await self.broadcast(document_id, {
            "type": "user_left",
            "user_id": user_id
        })

        # Clean up empty session
        if session and not session.users:
            del self.sessions[document_id]

    async def broadcast(self, document_id: str, message: dict, exclude_user: Optional[int] = None):
        """Broadcast message to all connected users."""
        if document_id not in self.connections:
            return

        disconnected = []
        for user_id, websocket in self.connections[document_id].items():
            if exclude_user and user_id == exclude_user:
                continue
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(user_id)

        # Clean up disconnected users
        for user_id in disconnected:
            await self.remove_user(document_id, user_id)

    def acquire_lock(self, document_id: str, cell_id: str, user_id: int) -> bool:
        """Try to acquire lock on a cell."""
        current_lock = self.locks[document_id].get(cell_id)
        if current_lock is None or current_lock == user_id:
            self.locks[document_id][cell_id] = user_id
            return True
        return False

    def release_lock(self, document_id: str, cell_id: str, user_id: int) -> bool:
        """Release lock on a cell."""
        if self.locks[document_id].get(cell_id) == user_id:
            del self.locks[document_id][cell_id]
            return True
        return False

    async def apply_edit(self, document_id: str, operation: EditOperation) -> dict:
        """Apply an edit operation with conflict detection."""
        session = self.get_session(document_id)
        if not session:
            return {"success": False, "error": "Session not found"}

        # Check version for conflicts
        if operation.version < session.version:
            # Conflict detected
            return {
                "success": False,
                "error": "Version conflict",
                "current_version": session.version,
                "conflict": True
            }

        # Apply edit
        session.version += 1
        session.last_modified = datetime.utcnow()
        operation.version = session.version

        # Broadcast edit to other users
        await self.broadcast(document_id, {
            "type": "edit_applied",
            "operation": operation.model_dump()
        }, exclude_user=operation.user_id)

        return {
            "success": True,
            "version": session.version,
            "operation_id": operation.operation_id
        }


# Global session manager
session_manager = CollaborativeSessionManager()


# ============================================================================
# REST Endpoints
# ============================================================================

@router.post("/sessions/{document_type}/{document_id}")
async def create_editing_session(
    document_type: str,
    document_id: str,
    db: Session = Depends(get_db)
):
    """Create or get an editing session for a document."""
    if document_type not in ["forecast", "supply_plan", "mps", "demand_plan"]:
        raise HTTPException(status_code=400, detail="Invalid document type")

    session = session_manager.create_session(document_id, document_type)

    return {
        "document_id": document_id,
        "document_type": document_type,
        "session_version": session.version,
        "active_users": len(session.users),
        "websocket_url": f"/api/collaborative-editing/ws/{document_id}"
    }


@router.get("/sessions/{document_id}")
async def get_session_info(
    document_id: str,
    db: Session = Depends(get_db)
):
    """Get information about an editing session."""
    session = session_manager.get_session(document_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "document_id": session.document_id,
        "document_type": session.document_type,
        "version": session.version,
        "users": [u.model_dump() for u in session.users.values()],
        "last_modified": session.last_modified.isoformat()
    }


@router.get("/sessions/{document_id}/users")
async def get_active_users(
    document_id: str,
    db: Session = Depends(get_db)
):
    """Get list of users currently editing a document."""
    session = session_manager.get_session(document_id)
    if not session:
        return {"users": []}

    return {
        "document_id": document_id,
        "users": [
            {
                "user_id": u.user_id,
                "user_name": u.user_name,
                "color": u.color,
                "cursor_position": u.cursor_position,
                "last_active": u.last_active.isoformat()
            }
            for u in session.users.values()
        ]
    }


@router.post("/sessions/{document_id}/lock")
async def acquire_cell_lock(
    document_id: str,
    row_id: str = Query(...),
    column_id: str = Query(...),
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Acquire a lock on a cell for editing."""
    cell_id = f"{row_id}:{column_id}"
    success = session_manager.acquire_lock(document_id, cell_id, user_id)

    if success:
        # Broadcast lock acquisition
        await session_manager.broadcast(document_id, {
            "type": "cell_locked",
            "cell_id": cell_id,
            "user_id": user_id
        }, exclude_user=user_id)

    return {
        "success": success,
        "cell_id": cell_id,
        "locked_by": user_id if success else session_manager.locks[document_id].get(cell_id)
    }


@router.delete("/sessions/{document_id}/lock")
async def release_cell_lock(
    document_id: str,
    row_id: str = Query(...),
    column_id: str = Query(...),
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Release a lock on a cell."""
    cell_id = f"{row_id}:{column_id}"
    success = session_manager.release_lock(document_id, cell_id, user_id)

    if success:
        await session_manager.broadcast(document_id, {
            "type": "cell_unlocked",
            "cell_id": cell_id
        })

    return {"success": success, "cell_id": cell_id}


@router.get("/sessions/{document_id}/locks")
async def get_active_locks(
    document_id: str,
    db: Session = Depends(get_db)
):
    """Get all active cell locks for a document."""
    locks = session_manager.locks.get(document_id, {})

    session = session_manager.get_session(document_id)
    users = session.users if session else {}

    return {
        "document_id": document_id,
        "locks": [
            {
                "cell_id": cell_id,
                "user_id": user_id,
                "user_name": users.get(user_id, UserPresence(user_id=user_id, user_name="Unknown")).user_name,
                "color": users.get(user_id, UserPresence(user_id=user_id, user_name="Unknown")).color
            }
            for cell_id, user_id in locks.items()
        ]
    }


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@router.websocket("/ws/{document_id}")
async def collaborative_editing_websocket(
    websocket: WebSocket,
    document_id: str,
    user_id: int = Query(...),
    user_name: str = Query(...)
):
    """
    WebSocket endpoint for real-time collaborative editing.

    Message types:
    - cursor_move: Update cursor position
    - selection_change: Update selected cells
    - cell_edit: Edit a cell value
    - bulk_edit: Edit multiple cells
    - request_lock: Request lock on cell
    - release_lock: Release lock on cell
    - ping: Keep-alive
    """
    await websocket.accept()

    session = session_manager.get_session(document_id)
    if not session:
        await websocket.close(code=4001, reason="Session not found")
        return

    # Add user to session
    user_presence = await session_manager.add_user(document_id, user_id, user_name, websocket)

    # Send initial state
    await websocket.send_json({
        "type": "session_joined",
        "document_id": document_id,
        "version": session.version,
        "users": [u.model_dump() for u in session.users.values()],
        "locks": [
            {"cell_id": cell_id, "user_id": uid}
            for cell_id, uid in session_manager.locks.get(document_id, {}).items()
        ],
        "your_color": user_presence.color
    })

    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "ping":
                # Update last active time
                if user_id in session.users:
                    session.users[user_id].last_active = datetime.utcnow()
                await websocket.send_json({"type": "pong"})

            elif message_type == "cursor_move":
                # Update cursor position
                position = data.get("position")  # {row_id, column_id}
                if user_id in session.users:
                    session.users[user_id].cursor_position = position
                    session.users[user_id].last_active = datetime.utcnow()

                # Broadcast to others
                await session_manager.broadcast(document_id, {
                    "type": "cursor_moved",
                    "user_id": user_id,
                    "position": position
                }, exclude_user=user_id)

            elif message_type == "selection_change":
                # Update selected cells
                selected = data.get("selected", [])
                if user_id in session.users:
                    session.users[user_id].selected_cells = selected

                await session_manager.broadcast(document_id, {
                    "type": "selection_changed",
                    "user_id": user_id,
                    "selected": selected
                }, exclude_user=user_id)

            elif message_type == "cell_edit":
                # Handle cell edit
                edit_data = data.get("edit")
                version = data.get("version", session.version)

                operation = EditOperation(
                    document_id=document_id,
                    user_id=user_id,
                    user_name=user_name,
                    edit_type="cell_edit",
                    edits=[CellEdit(**edit_data)],
                    version=version
                )

                result = await session_manager.apply_edit(document_id, operation)
                await websocket.send_json({
                    "type": "edit_result",
                    **result
                })

            elif message_type == "bulk_edit":
                # Handle bulk edit
                edits_data = data.get("edits", [])
                version = data.get("version", session.version)

                operation = EditOperation(
                    document_id=document_id,
                    user_id=user_id,
                    user_name=user_name,
                    edit_type="bulk_edit",
                    edits=[CellEdit(**e) for e in edits_data],
                    version=version
                )

                result = await session_manager.apply_edit(document_id, operation)
                await websocket.send_json({
                    "type": "edit_result",
                    **result
                })

            elif message_type == "request_lock":
                cell_id = f"{data.get('row_id')}:{data.get('column_id')}"
                success = session_manager.acquire_lock(document_id, cell_id, user_id)

                await websocket.send_json({
                    "type": "lock_result",
                    "success": success,
                    "cell_id": cell_id
                })

                if success:
                    await session_manager.broadcast(document_id, {
                        "type": "cell_locked",
                        "cell_id": cell_id,
                        "user_id": user_id,
                        "color": session.users[user_id].color if user_id in session.users else "#888"
                    }, exclude_user=user_id)

            elif message_type == "release_lock":
                cell_id = f"{data.get('row_id')}:{data.get('column_id')}"
                success = session_manager.release_lock(document_id, cell_id, user_id)

                if success:
                    await session_manager.broadcast(document_id, {
                        "type": "cell_unlocked",
                        "cell_id": cell_id
                    })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await session_manager.remove_user(document_id, user_id)


# ============================================================================
# Conflict Resolution Endpoints
# ============================================================================

@router.post("/sessions/{document_id}/resolve-conflict")
async def resolve_conflict(
    document_id: str,
    conflict: ConflictResolution,
    db: Session = Depends(get_db)
):
    """Manually resolve an edit conflict."""
    session = session_manager.get_session(document_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Apply the resolution
    operation = EditOperation(
        document_id=document_id,
        user_id=conflict.resolved_by or 0,
        user_name="System",
        edit_type="conflict_resolution",
        edits=[CellEdit(
            row_id=conflict.cell_id.split(":")[0],
            column_id=conflict.cell_id.split(":")[1] if ":" in conflict.cell_id else "",
            old_value=None,
            new_value=conflict.resolved_value
        )],
        version=session.version
    )

    result = await session_manager.apply_edit(document_id, operation)

    return {
        "success": result.get("success"),
        "conflict_id": conflict.conflict_id,
        "resolved_value": conflict.resolved_value,
        "new_version": session.version
    }


# ============================================================================
# Session History Endpoints
# ============================================================================

@router.get("/sessions/{document_id}/history")
async def get_edit_history(
    document_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Get recent edit history for a document."""
    # In production, this would query from a persistent store
    session = session_manager.get_session(document_id)
    if not session:
        return {"edits": []}

    return {
        "document_id": document_id,
        "current_version": session.version,
        "edits": [],  # Would be populated from persistent storage
        "message": "Edit history would be retrieved from database in production"
    }
