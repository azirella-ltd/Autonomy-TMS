from fastapi import WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi import APIRouter, status
from typing import Dict, List
import json
import asyncio
from sqlalchemy.orm import Session

from app.db.session import get_sync_db as get_db
from app.models.scenario import Scenario
from app.models.scenario_user import ScenarioUser
from app.schemas.scenario import ScenarioState
from app.services.mixed_scenario_service import MixedScenarioService

router = APIRouter()

class ConnectionManager:
    """Manages WebSocket connections and broadcasts messages to connected clients."""
    
    def __init__(self):
        self.active_connections: Dict[int, Dict[int, WebSocket]] = {}
        self.lock = asyncio.Lock()
    
    async def connect(self, scenario_id: int, scenario_user_id: int, websocket: WebSocket):
        """Register a new WebSocket connection for a scenario_user in a game."""
        await websocket.accept()
        
        async with self.lock:
            if scenario_id not in self.active_connections:
                self.active_connections[scenario_id] = {}
            self.active_connections[scenario_id][scenario_user_id] = websocket
    
    def disconnect(self, scenario_id: int, scenario_user_id: int):
        """Remove a WebSocket connection when a scenario_user disconnects."""
        if scenario_id in self.active_connections:
            if scenario_user_id in self.active_connections[scenario_id]:
                del self.active_connections[scenario_id][scenario_user_id]
                # Clean up empty game rooms
                if not self.active_connections[scenario_id]:
                    del self.active_connections[scenario_id]
    
    async def broadcast_game_state(self, scenario_id: int, scenario_state: ScenarioState):
        """Send the current game state to all connected scenario_users in a game."""
        if scenario_id not in self.active_connections:
            return
            
        message = {
            "type": "game_update",
            "data": scenario_state.dict()
        }
        
        # Create a list of tasks to send messages to all connected clients
        tasks = []
        for scenario_user_id, connection in list(self.active_connections[scenario_id].items()):
            try:
                tasks.append(
                    asyncio.create_task(
                        connection.send_json(message)
                    )
                )
            except Exception as e:
                # If sending fails, the connection is likely dead
                print(f"Error sending to scenario_user {scenario_user_id}: {e}")
                self.disconnect(scenario_id, scenario_user_id)
        
        # Wait for all sends to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def send_personal_message(self, scenario_user_id: int, scenario_id: int, message: dict):
        """Send a message to a specific scenario_user in a game."""
        if scenario_id in self.active_connections:
            if scenario_user_id in self.active_connections[scenario_id]:
                try:
                    await self.active_connections[scenario_id][scenario_user_id].send_json(message)
                except Exception as e:
                    print(f"Error sending to scenario_user {scenario_user_id}: {e}")
                    self.disconnect(scenario_id, scenario_user_id)

    async def broadcast_to_game(self, scenario_id: int, message: dict):
        """Broadcast a message to all connected scenario_users in a game."""
        if scenario_id not in self.active_connections:
            return

        # Create tasks to send messages to all connected clients
        tasks = []
        for scenario_user_id, connection in list(self.active_connections[scenario_id].items()):
            try:
                tasks.append(
                    asyncio.create_task(
                        connection.send_json(message)
                    )
                )
            except Exception as e:
                print(f"Error sending to scenario_user {scenario_user_id}: {e}")
                self.disconnect(scenario_id, scenario_user_id)

        # Wait for all sends to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

# Global connection manager instance
manager = ConnectionManager()


# Phase 1: DAG Sequential Execution - WebSocket Message Helpers

async def broadcast_phase_change(
    scenario_id: int,
    round_number: int,
    new_phase: str,
    phase_started_at: str = None,
    scenario_users_completed: int = 0,
    total_scenario_users: int = 0
):
    """
    Broadcast when round phase changes (FULFILLMENT → REPLENISHMENT → COMPLETED).

    Args:
        scenario_id: Scenario ID
        round_number: Current round number
        new_phase: New phase name ('fulfillment', 'replenishment', 'completed')
        phase_started_at: ISO timestamp when phase started
        scenario_users_completed: Number of scenario_users who have completed current phase
        total_scenario_users: Total scenario_users in scenario
    """
    message = {
        "type": "round_phase_change",
        "scenario_id": scenario_id,
        "round_number": round_number,
        "phase": new_phase,
        "phase_started_at": phase_started_at,
        "players_completed": scenario_users_completed,
        "total_players": total_scenario_users,
    }

    await manager.broadcast_to_game(scenario_id, message)


async def broadcast_scenario_user_action_required(
    scenario_id: int,
    scenario_user_id: int,
    round_number: int,
    phase: str,
    action_type: str,
    context: dict = None
):
    """
    Notify a specific scenario_user that action is required.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser who needs to act
        round_number: Current round
        phase: Current phase
        action_type: 'fulfillment_decision' or 'replenishment_decision'
        context: Additional context (ATP, demand, etc.)
    """
    message = {
        "type": "scenario_user_action_required",
        "scenario_id": scenario_id,
        "scenario_user_id": scenario_user_id,
        "round_number": round_number,
        "phase": phase,
        "action_type": action_type,
        "context": context or {},
    }

    await manager.send_personal_message(scenario_user_id, scenario_id, message)


async def broadcast_fulfillment_completed(
    scenario_id: int,
    scenario_user_id: int,
    participant_role: str,
    fulfill_qty: int,
    scenario_users_completed: int,
    total_scenario_users: int
):
    """
    Broadcast when a scenario_user submits their fulfillment decision.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser who submitted
        participant_role: ScenarioUser's role (e.g., 'Retailer')
        fulfill_qty: Quantity fulfilled
        scenario_users_completed: Total scenario_users who have completed fulfillment
        total_scenario_users: Total scenario_users in scenario
    """
    message = {
        "type": "fulfillment_completed",
        "scenario_id": scenario_id,
        "scenario_user_id": scenario_user_id,
        "participant_role": participant_role,
        "fulfill_qty": fulfill_qty,
        "players_completed": scenario_users_completed,
        "total_players": total_scenario_users,
    }

    await manager.broadcast_to_game(scenario_id, message)


async def broadcast_replenishment_completed(
    scenario_id: int,
    scenario_user_id: int,
    participant_role: str,
    order_qty: int,
    scenario_users_completed: int,
    total_scenario_users: int
):
    """
    Broadcast when a scenario_user submits their replenishment order.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser who submitted
        participant_role: ScenarioUser's role (e.g., 'Wholesaler')
        order_qty: Quantity ordered
        scenario_users_completed: Total scenario_users who have completed replenishment
        total_scenario_users: Total scenario_users in scenario
    """
    message = {
        "type": "replenishment_completed",
        "scenario_id": scenario_id,
        "scenario_user_id": scenario_user_id,
        "participant_role": participant_role,
        "order_qty": order_qty,
        "players_completed": scenario_users_completed,
        "total_players": total_scenario_users,
    }

    await manager.broadcast_to_game(scenario_id, message)


async def broadcast_round_completed(
    scenario_id: int,
    round_number: int,
    next_round: int = None,
    game_finished: bool = False
):
    """
    Broadcast when a round is completed and ready for next round.

    Args:
        scenario_id: Scenario ID
        round_number: Completed round number
        next_round: Next round number (None if game finished)
        game_finished: Whether the game has finished
    """
    message = {
        "type": "round_completed",
        "scenario_id": scenario_id,
        "round_number": round_number,
        "next_round": next_round,
        "game_finished": game_finished,
    }

    await manager.broadcast_to_game(scenario_id, message)


async def broadcast_all_scenario_users_ready(
    scenario_id: int,
    round_number: int,
    phase: str
):
    """
    Broadcast when all scenario_users have completed their actions for a phase.

    Args:
        scenario_id: Scenario ID
        round_number: Current round
        phase: Phase that was just completed ('fulfillment' or 'replenishment')
    """
    message = {
        "type": "all_players_ready",
        "scenario_id": scenario_id,
        "round_number": round_number,
        "phase": phase,
        "message": f"All scenario_users ready. Transitioning from {phase} phase.",
    }

    await manager.broadcast_to_game(scenario_id, message)


# Phase 2: Agent Copilot Mode - WebSocket Message Helpers

async def broadcast_agent_recommendation_ready(
    scenario_id: int,
    scenario_user_id: int,
    phase: str,
    recommendation: dict
):
    """
    Broadcast when agent recommendation is ready.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID who received recommendation
        phase: Phase type ("fulfillment" or "replenishment")
        recommendation: RecommendationResult dict
    """
    message = {
        "type": "agent_recommendation_ready",
        "scenario_id": scenario_id,
        "scenario_user_id": scenario_user_id,
        "phase": phase,
        "recommendation": recommendation,
    }

    # Send only to the specific scenario_user
    await manager.send_personal_message(scenario_user_id, scenario_id, message)


async def send_override_requires_approval(
    scenario_id: int,
    scenario_user_id: int,
    proposal_id: int,
    authority_check: dict
):
    """
    Notify scenario_user that their override requires approval.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID who needs approval
        proposal_id: Decision proposal ID
        authority_check: AuthorityCheckResult dict
    """
    message = {
        "type": "override_requires_approval",
        "scenario_id": scenario_id,
        "scenario_user_id": scenario_user_id,
        "proposal_id": proposal_id,
        "message": "Your override exceeds authority level. Waiting for manager approval.",
        "game_paused": True,
        "authority_check": authority_check,
    }

    # Send to the specific scenario_user
    await manager.send_personal_message(scenario_user_id, scenario_id, message)

    # Notify managers in the game
    await manager.broadcast_to_game(scenario_id, {
        "type": "approval_requested",
        "scenario_id": scenario_id,
        "scenario_user_id": scenario_user_id,
        "proposal_id": proposal_id,
        "message": f"ScenarioUser {scenario_user_id} requested approval for override",
    })


async def broadcast_override_approved(
    scenario_id: int,
    scenario_user_id: int,
    proposal_id: int,
    approved_by: str
):
    """
    Broadcast when manager approves an override.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID whose override was approved
        proposal_id: Decision proposal ID
        approved_by: Manager who approved
    """
    message = {
        "type": "override_approved",
        "scenario_id": scenario_id,
        "scenario_user_id": scenario_user_id,
        "proposal_id": proposal_id,
        "approved_by": approved_by,
        "message": "Override approved. Proceeding with your decision.",
        "game_resumed": True,
    }

    # Broadcast to all scenario_users in the game
    await manager.broadcast_to_game(scenario_id, message)


async def broadcast_override_rejected(
    scenario_id: int,
    scenario_user_id: int,
    proposal_id: int,
    rejected_by: str,
    agent_recommendation: dict
):
    """
    Broadcast when manager rejects an override.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID whose override was rejected
        proposal_id: Decision proposal ID
        rejected_by: Manager who rejected
        agent_recommendation: Agent's original recommendation to use instead
    """
    message = {
        "type": "override_rejected",
        "scenario_id": scenario_id,
        "scenario_user_id": scenario_user_id,
        "proposal_id": proposal_id,
        "rejected_by": rejected_by,
        "message": "Override rejected. Using agent recommendation.",
        "game_resumed": True,
        "fallback_recommendation": agent_recommendation,
    }

    # Broadcast to all scenario_users in the game
    await manager.broadcast_to_game(scenario_id, message)


# Phase 3: ATP/CTP Integration - WebSocket Message Helpers

async def broadcast_atp_threshold_breach(
    scenario_id: int,
    scenario_user_id: int,
    current_atp: int,
    threshold: int,
    severity: str = "warning"
):
    """
    Broadcast when ATP falls below safety threshold.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID with low ATP
        current_atp: Current ATP value
        threshold: Safety stock threshold
        severity: "warning" or "error"
    """
    message = {
        "type": "atp_threshold_breach",
        "scenario_id": scenario_id,
        "scenario_user_id": scenario_user_id,
        "current_atp": current_atp,
        "threshold": threshold,
        "message": f"ATP below safety threshold ({current_atp} < {threshold}). Consider expediting replenishment.",
        "severity": severity,
    }

    # Send only to the specific scenario_user
    await manager.send_personal_message(scenario_user_id, scenario_id, message)


async def broadcast_ctp_capacity_constraint(
    scenario_id: int,
    scenario_user_id: int,
    demand: int,
    available_ctp: int,
    shortfall: int
):
    """
    Broadcast when production capacity is insufficient to meet demand.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID (manufacturer)
        demand: Requested production quantity
        available_ctp: Available CTP
        shortfall: Shortfall (demand - CTP)
    """
    message = {
        "type": "ctp_capacity_constraint",
        "scenario_id": scenario_id,
        "scenario_user_id": scenario_user_id,
        "demand": demand,
        "available_ctp": available_ctp,
        "shortfall": shortfall,
        "message": f"Production capacity insufficient. Demand exceeds CTP by {shortfall} units.",
        "severity": "error",
    }

    # Send only to the specific scenario_user
    await manager.send_personal_message(scenario_user_id, scenario_id, message)


async def broadcast_allocation_conflict(
    scenario_id: int,
    scenario_user_id: int,
    total_demand: int,
    available_atp: int,
    customers: List[dict]
):
    """
    Broadcast when multiple customers request more than available ATP.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID (supplier node)
        total_demand: Total demand from all customers
        available_atp: Available ATP
        customers: List of customer demands [{"customer_id": 1, "demand": 300}, ...]
    """
    message = {
        "type": "allocation_conflict",
        "scenario_id": scenario_id,
        "scenario_user_id": scenario_user_id,
        "total_demand": total_demand,
        "available_atp": available_atp,
        "customers": customers,
        "message": f"Multiple customers requesting {total_demand} units, but only {available_atp} ATP available. Resolution required.",
        "severity": "warning",
    }

    # Send only to the specific scenario_user
    await manager.send_personal_message(scenario_user_id, scenario_id, message)


async def broadcast_atp_projection_update(
    scenario_id: int,
    scenario_user_id: int,
    projection: List[dict]
):
    """
    Broadcast updated ATP projection (e.g., after new order placed).

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID
        projection: List of ATPPeriod dicts
    """
    message = {
        "type": "atp_projection_update",
        "scenario_id": scenario_id,
        "scenario_user_id": scenario_user_id,
        "projection": projection,
    }

    # Send only to the specific scenario_user
    await manager.send_personal_message(scenario_user_id, scenario_id, message)


async def broadcast_component_constraint(
    scenario_id: int,
    scenario_user_id: int,
    component_name: str,
    required: int,
    available: int,
    shortfall: int
):
    """
    Broadcast when component availability constrains production.

    Args:
        scenario_id: Scenario ID
        scenario_user_id: ScenarioUser ID (manufacturer)
        component_name: Name of constrained component
        required: Required quantity
        available: Available component ATP
        shortfall: Shortfall in components
    """
    message = {
        "type": "component_constraint",
        "scenario_id": scenario_id,
        "scenario_user_id": scenario_user_id,
        "component_name": component_name,
        "required": required,
        "available": available,
        "shortfall": shortfall,
        "message": f"Component {component_name} shortage: need {required}, have {available} (shortfall: {shortfall})",
        "severity": "warning",
    }

    # Send only to the specific scenario_user
    await manager.send_personal_message(scenario_user_id, scenario_id, message)


@router.websocket("/ws/games/{scenario_id}/scenario_users/{scenario_user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    scenario_id: int,
    scenario_user_id: int,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time game updates.
    
    - Connects a scenario_user to the game's WebSocket room
    - Sends the current game state on connection
    - Broadcasts updates to all scenario_users when the game state changes
    """
    # Verify the scenario and scenario_user exist
    game = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not game:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    scenario_user = db.query(ScenarioUser).filter(
        ScenarioUser.id == scenario_user_id,
        ScenarioUser.scenario_id == scenario_id
    ).first()
    
    if not scenario_user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Add the connection to the manager
    await manager.connect(scenario_id, scenario_user_id, websocket)
    
    # Send the current game state
    game_service = MixedScenarioService(db)
    try:
        game_state = game_service.get_game_state(scenario_id)
        await manager.send_personal_message(
            scenario_user_id,
            scenario_id,
            {
                "type": "game_state",
                "data": scenario_state.dict()
            }
        )
        
        # Keep the connection alive and handle incoming messages
        while True:
            try:
                # Wait for a message from the client
                data = await websocket.receive_text()
                
                # Parse the message
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid JSON"
                    })
                    continue
                
                # Handle different message types
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                
                # Add more message handlers as needed
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"WebSocket error: {e}")
                break
                
    finally:
        # Clean up the connection when done
        manager.disconnect(scenario_id, scenario_user_id)

# Add the WebSocket router to the API router
router.websocket_route("/ws/games/{scenario_id}/scenario_users/{scenario_user_id}", name="game_ws")(websocket_endpoint)
