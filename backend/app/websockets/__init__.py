from fastapi import WebSocket
from typing import Dict, List, Optional, Any, cast
import json
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.scenario import Scenario as Game, ScenarioStatus as GameStatus
from ..models.participant import Participant as Player
from ..services.mixed_scenario_service import MixedScenarioService
from ..db.session import get_db

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, Dict[str, WebSocket]] = {}
        self.game_rooms: Dict[int, set] = {}

    async def connect(self, websocket: WebSocket, scenario_id: int, client_id: str, player_id: int = None, db: AsyncSession = None):
        await websocket.accept()
        if scenario_id not in self.active_connections:
            self.active_connections[scenario_id] = {}
            self.game_rooms[scenario_id] = set()
        
        self.active_connections[scenario_id][client_id] = {
            'websocket': websocket,
            'player_id': player_id
        }
        self.game_rooms[scenario_id].add(client_id)
        
        try:
            # Send current game state to the new connection if database is available
            if db:
                await self.send_game_state(scenario_id, client_id, db)
            
            # Notify other clients about the new connection
            await self.broadcast({
                "type": "player_connected",
                "client_id": client_id,
                "player_id": player_id,
                "timestamp": datetime.utcnow().isoformat()
            }, scenario_id, exclude_client_id=client_id)
            
        except Exception as e:
            logger.error(f"Error in WebSocket connect: {e}", exc_info=True)
            await websocket.close(code=1011, reason=f"Server error: {str(e)}")
            raise

    def disconnect(self, scenario_id: int, client_id: str):
        if scenario_id in self.active_connections and client_id in self.active_connections[scenario_id]:
            del self.active_connections[scenario_id][client_id]
            if client_id in self.game_rooms[scenario_id]:
                self.game_rooms[scenario_id].remove(client_id)

    async def send_personal_message(self, message: dict, scenario_id: int, client_id: str):
        if scenario_id in self.active_connections and client_id in self.active_connections[scenario_id]:
            connection = self.active_connections[scenario_id][client_id]
            if 'websocket' in connection and not connection['websocket'].client_state.is_disconnected:
                await connection['websocket'].send_json(message)

    async def broadcast(self, message: dict, scenario_id: int, exclude_client_id: str = None):
        if scenario_id in self.active_connections:
            for client_id, connection in self.active_connections[scenario_id].items():
                if client_id != exclude_client_id and 'websocket' in connection:
                    try:
                        if not connection['websocket'].client_state.is_disconnected:
                            await connection['websocket'].send_json(message)
                    except Exception as e:
                        logger.error(f"Error broadcasting to {client_id}: {e}", exc_info=True)
                        self.disconnect(scenario_id, client_id)

    async def send_game_state(self, scenario_id: int, client_id: str, db: AsyncSession):
        """Send the current game state to a specific client"""
        try:
            game_service = MixedScenarioService(db)
            game_state = await game_service.get_game_state(scenario_id)
            await self.send_personal_message({
                "type": "game_state",
                "data": game_state.dict()
            }, scenario_id, client_id)
        except Exception as e:
            print(f"Error sending game state: {e}")
            await self.send_personal_message({
                "type": "error",
                "message": f"Failed to load game state: {str(e)}"
            }, scenario_id, client_id)
        finally:
            db.close()

    async def broadcast_game_state(self, scenario_id: int, game_state = None):
        """Broadcast the current game state to all connected clients"""
        try:
            if game_state is None:
                async with get_db() as db:
                    game_service = MixedScenarioService(db)
                    game_state = await game_service.get_game_state(scenario_id)
            
            await self.broadcast({
                "type": "game_state",
                "data": game_state.dict() if hasattr(game_state, 'dict') else game_state
            }, scenario_id)
        except Exception as e:
            print(f"Error broadcasting game state: {e}")
            # Try to send error to all clients
            try:
                await self.broadcast({
                    "type": "error",
                    "message": f"Failed to update game state: {str(e)}"
                }, scenario_id)
            except:
                pass

# Create a singleton instance
manager = ConnectionManager()
