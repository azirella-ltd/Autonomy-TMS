import random
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.participant import Participant, ParticipantRole
from app.models.supply_chain import ParticipantInventory, ScenarioRound, ParticipantRound
from app.schemas.scenario import ParticipantState, ScenarioState

# Aliases for backwards compatibility
Player = Participant
PlayerRole = ParticipantRole
PlayerInventory = ParticipantInventory
GameRound = ScenarioRound
PlayerRound = ParticipantRound
PlayerState = ParticipantState
GameState = ScenarioState

class AIService:
    """Service for AI player decision making in the Beer Game."""
    
    # AI difficulty levels
    class Difficulty:
        EASY = "easy"        # Makes random decisions
        MEDIUM = "medium"    # Basic strategy
        HARD = "hard"        # Advanced strategy with forecasting
    
    def __init__(self, db: Session):
        self.db = db
    
    def make_decision(self, player: Player, game_state: GameState) -> int:
        """
        Make a decision on how many units to order based on the current game state.
        
        Args:
            player: The AI player making the decision
            game_state: Current state of the game
            
        Returns:
            int: Number of units to order
        """
        # Get the player's state
        player_state = next((p for p in game_state.players if p.id == player.id), None)
        if not player_state:
            return 0
            
        # Get the current round
        current_round = self._get_current_round(player.game_id)
        if not current_round:
            return 0
            
        # Get historical data
        history = self._get_player_history(player.id, current_round.round_number)
        
        # Make decision based on difficulty level
        if player.is_ai == "easy":
            return self._easy_ai(player_state, history)
        elif player.is_ai == "hard":
            return self._hard_ai(player_state, history, game_state)
        else:  # medium is default
            return self._medium_ai(player_state, history)
    
    def _easy_ai(self, player_state: PlayerState, history: List[Dict]) -> int:
        """Easy AI: Makes random decisions within a reasonable range."""
        # Random order between 0 and 2x the average of last 3 orders
        if len(history) >= 3:
            last_orders = [h.get('order_placed', 4) for h in history[-3:]]
            avg_order = sum(last_orders) / len(last_orders)
            return random.randint(0, int(avg_order * 2))
        return random.randint(0, 8)  # Default range if not enough history
    
    def _medium_ai(self, player_state: PlayerState, history: List[Dict]) -> int:
        """
        Medium AI: Uses a basic strategy considering current inventory and recent demand.
        Implements a simple base stock policy.
        """
        # Base stock level depends on role (further upstream needs to keep more inventory)
        role_multiplier = {
            PlayerRole.RETAILER: 1.0,
            PlayerRole.WHOLESALER: 1.2,
            PlayerRole.DISTRIBUTOR: 1.5,
            PlayerRole.MANUFACTURER: 2.0
        }
        
        base_stock = 12 * role_multiplier.get(player_state.role, 1.0)
        
        # Calculate average of last 3 orders received
        if len(history) >= 3:
            avg_demand = sum(h.get('order_received', 4) for h in history[-3:]) / 3
        else:
            avg_demand = 4  # Default average demand
        
        # Calculate target inventory position
        target_inventory = base_stock + avg_demand
        
        # Calculate order quantity
        current_inventory = player_state.current_stock
        incoming_shipments = sum(shipment.get('quantity', 0) for shipment in player_state.incoming_shipments)
        backorders = player_state.backorders
        
        # Inventory position = on-hand + in-transit - backorders
        inventory_position = current_inventory + incoming_shipments - backorders
        
        # Order quantity = target inventory - inventory position + avg_demand
        order_quantity = max(0, int(target_inventory - inventory_position + avg_demand))
        
        return order_quantity
    
    def _hard_ai(self, player_state: PlayerState, history: List[Dict], game_state: GameState) -> int:
        """
        Hard AI: Implements an advanced strategy with demand forecasting and bullwhip effect mitigation.
        Uses exponential smoothing for demand forecasting and considers supply chain position.
        """
        # Get more historical data for better forecasting
        full_history = self._get_player_history(player_state.id, game_state.current_round)
        
        # Calculate demand forecast using exponential smoothing (alpha = 0.3)
        alpha = 0.3
        forecast = self._calculate_demand_forecast(full_history, alpha)
        
        # Adjust forecast based on position in supply chain (bullwhip effect)
        position_factor = self._get_position_factor(player_state.role)
        adjusted_forecast = forecast * position_factor
        
        # Calculate safety stock based on demand variability
        safety_stock = self._calculate_safety_stock(full_history)
        
        # Calculate target inventory level
        lead_time = 2  # Assuming 2 rounds lead time
        target_inventory = (adjusted_forecast * lead_time) + safety_stock
        
        # Calculate current inventory position
        current_inventory = player_state.current_stock
        incoming_shipments = sum(shipment.get('quantity', 0) for shipment in player_state.incoming_shipments)
        backorders = player_state.backorders
        inventory_position = current_inventory + incoming_shipments - backorders
        
        # Calculate order quantity using (s, S) policy
        order_quantity = max(0, int(target_inventory - inventory_position + adjusted_forecast))
        
        # Add some randomness to make it less predictable (but still smart)
        order_quantity = random.randint(
            max(0, int(order_quantity * 0.8)),
            int(order_quantity * 1.2)
        )
        
        return order_quantity
    
    def _calculate_demand_forecast(self, history: List[Dict], alpha: float) -> float:
        """Calculate demand forecast using exponential smoothing."""
        if not history:
            return 4.0  # Default forecast if no history
        
        # Start with the first actual demand
        forecast = history[0].get('order_received', 4)
        
        # Apply exponential smoothing
        for h in history[1:]:
            actual = h.get('order_received', 4)
            forecast = alpha * actual + (1 - alpha) * forecast
            
        return forecast
    
    def _get_position_factor(self, role: PlayerRole) -> float:
        """Get a factor based on position in supply chain to adjust for bullwhip effect."""
        return {
            PlayerRole.RETAILER: 1.0,
            PlayerRole.WHOLESALER: 1.1,
            PlayerRole.DISTRIBUTOR: 1.3,
            PlayerRole.MANUFACTURER: 1.5
        }.get(role, 1.0)
    
    def _calculate_safety_stock(self, history: List[Dict]) -> float:
        """Calculate safety stock based on demand variability."""
        if len(history) < 3:
            return 4.0  # Default safety stock
            
        # Calculate standard deviation of demand
        demands = [h.get('order_received', 4) for h in history]
        mean_demand = sum(demands) / len(demands)
        variance = sum((x - mean_demand) ** 2 for x in demands) / len(demands)
        std_dev = variance ** 0.5
        
        # Safety stock = z * std_dev * sqrt(lead_time)
        # Using z = 1.65 for 95% service level
        lead_time = 2
        return 1.65 * std_dev * (lead_time ** 0.5)
    
    def _get_current_round(self, game_id: int) -> Optional[GameRound]:
        """Get the current round for a game."""
        return self.db.query(GameRound).join(Game).filter(
            Game.id == game_id
        ).order_by(
            GameRound.round_number.desc()
        ).first()
    
    def _get_player_history(self, player_id: int, current_round: int, limit: int = 10) -> List[Dict]:
        """Get the player's order history."""
        history = self.db.query(PlayerRound, GameRound).join(
            GameRound, PlayerRound.round_id == GameRound.id
        ).filter(
            PlayerRound.player_id == player_id,
            GameRound.round_number < current_round
        ).order_by(
            GameRound.round_number.desc()
        ).limit(limit).all()
        
        return [
            {
                'round_number': gr.round_number,
                'order_placed': pr.order_placed,
                'order_received': pr.order_received,
                'inventory_before': pr.inventory_before,
                'inventory_after': pr.inventory_after,
                'backorders_before': pr.backorders_before,
                'backorders_after': pr.backorders_after,
                'total_cost': pr.total_cost
            }
            for pr, gr in history
        ]
