from fastapi import WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.routing import APIRouter
from typing import Optional, Dict, Any
import uuid
import json
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import get_current_user
from ..models.user import User
from ..schemas.websocket import WebSocketMessage
from ..db.session import get_db
from . import manager

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws/games/{scenario_id}/players/{player_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    scenario_id: int,
    player_id: int,
    token: str = None,
    db: AsyncSession = Depends(get_db)
):
    """WebSocket endpoint for real-time game updates"""
    client_id = str(uuid.uuid4())
    user = None
    
    # Log connection attempt
    logger.info(f"WebSocket connection attempt - Game: {scenario_id}, Player: {player_id}, Client: {client_id}")
    
    try:
        # Accept the WebSocket connection first
        await websocket.accept()
        logger.info(f"WebSocket connection accepted - Game: {scenario_id}, Player: {player_id}, Client: {client_id}")
        
        # Authenticate the user using the token if provided
        if token:
            try:
                user = await get_current_user(token)
                logger.info(f"Authenticated WebSocket connection - User: {user.id}, Game: {scenario_id}, Player: {player_id}")
                
                # Verify the player ID matches the authenticated user if needed
                # This is a good place to add additional authorization checks
                
            except Exception as e:
                error_msg = f"WebSocket authentication failed: {str(e)}"
                logger.warning(error_msg, exc_info=True)
                await websocket.close(
                    code=status.WS_1008_POLICY_VIOLATION, 
                    reason=error_msg[:120]  # Reason has a max length
                )
                return
        else:
            logger.warning(f"Unauthenticated WebSocket connection - Game: {scenario_id}, Player: {player_id}")
        
        # Register the connection with the manager
        await manager.connect(websocket, scenario_id, client_id, player_id=player_id, db=db)
        logger.info(f"WebSocket connection registered with manager - Game: {scenario_id}, Player: {player_id}, Client: {client_id}")
        
        # Main message loop
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle different message types
                if message["type"] == "order":
                    # Process order
                    await handle_order_message(scenario_id, client_id, user, message, db)
                    
                elif message["type"] == "chat":
                    # Broadcast chat message
                    await manager.broadcast({
                        "type": "chat",
                        "user_id": user.id if user else None,
                        "username": user.username if user else "Anonymous",
                        "message": message["message"],
                        "timestamp": datetime.utcnow().isoformat()
                    }, scenario_id)
                    
                elif message["type"] == "get_state":
                    # Send current game state to the requesting client
                    await manager.send_game_state(scenario_id, client_id)
                    
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON format",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            except Exception as e:
                logger.error(f"WebSocket error: {e}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "message": "An error occurred",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected")
        
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}", exc_info=True)
        
    finally:
        manager.disconnect(scenario_id, client_id)
        
        # Notify other clients about the disconnection
        await manager.broadcast({
            "type": "player_disconnected",
            "client_id": client_id,
            "user_id": user.id if user else None,
            "timestamp": datetime.utcnow().isoformat()
        }, scenario_id, exclude_client_id=client_id)

async def handle_order_message(scenario_id: int, client_id: str, user: Optional[User], message: dict, db: AsyncSession):
    """Handle order messages from clients"""
    from ..services.mixed_scenario_service import MixedScenarioService
    from sqlalchemy import select
    from ..models.scenario import Scenario as Game
    from ..models.participant import Participant as Player
    
    try:
        game_service = MixedScenarioService(db)
        
        # Get game
        result = await db.execute(select(Game).filter(Game.id == scenario_id))
        game = result.scalars().first()
        if not game:
            logger.error(f"Game {scenario_id} not found")
            return
            
        # Get player
        result = await db.execute(
            select(Player).filter(
                Player.scenario_id == scenario_id,
                Player.user_id == user.id
            )
        )
        player = result.scalars().first()
        
        if not player:
            logger.error(f"Player not found in game {scenario_id}")
            return
            
        order_quantity = message.get("quantity")
        if order_quantity is None:
            logger.error("No quantity provided in order message")
            await manager.send_personal_message({
                "type": "error",
                "message": "No quantity provided in order message",
                "timestamp": datetime.utcnow().isoformat()
            }, scenario_id, client_id)
            return
            
    except Exception as e:
        logger.error(f"Error processing order: {e}", exc_info=True)
        await manager.send_personal_message({
            "type": "error",
            "message": "An error occurred while processing your order",
            "timestamp": datetime.utcnow().isoformat()
        }, scenario_id, client_id)
        
    finally:
        db.close()
