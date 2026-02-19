from typing import Dict, Optional, List
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .. import models, schemas
from .base_agent import BaseAgent

class SupervisorAgent(BaseAgent):
    """
    Supervisor agent that monitors and can override agent decisions to reduce bullwhip effect.
    Only overrides AI decisions, never human decisions.
    """
    
    def __init__(self, db: Session, game_id: int):
        super().__init__(db, game_id)
        self.bullwhip_threshold = 1.5  # Threshold for bullwhip effect detection
        self.decision_history: List[dict] = []
        self.override_count = 0
        self.max_overrides = 5  # Maximum overrides per game period
        
    async def analyze_bullwhip_effect(self, current_orders: Dict[str, int]) -> float:
        """
        Calculate the bullwhip effect metric based on order variance.
        Returns a value where > 1 indicates bullwhip effect.
        """
        # Get recent orders from all players
        recent_rounds = self.db.query(models.GameRound)\n            .filter(models.GameRound.game_id == self.game_id)\n            .order_by(models.GameRound.round_number.desc())\n            .limit(4)\n            .all()
            
        if len(recent_rounds) < 2:
            return 0.0
            
        # Calculate order variances
        order_sequences = {}
        for role in ['retailer', 'wholesaler', 'distributor', 'manufacturer']:
            orders = [getattr(round, f'{role}_order') for round in recent_rounds]
            order_sequences[role] = orders
        
        # Calculate variance ratio (bullwhip metric)
        downstream_variance = np.var(order_sequences['retailer'])
        upstream_variance = np.var(order_sequences['manufacturer'])
        
        if downstream_variance == 0:
            return 0.0
            
        return upstream_variance / downstream_variance
    
    def should_override_decision(self, 
                               role: str, 
                               proposed_order: int, 
                               current_inventory: int, 
                               incoming_shipment: int,
                               is_human_decision: bool) -> bool:
        """
        Determine if the supervisor should override an agent's decision.
        Never overrides human decisions.
        """
        if is_human_decision or self.override_count >= self.max_overrides:
            return False
            
        # Check for extreme orders
        if proposed_order > current_inventory * 2:
            return True
            
        # Check for large order swings
        if self.decision_history:
            last_order = self.decision_history[-1].get(role, {})
            if abs(proposed_order - last_order.get('order', 0)) > last_order.get('order', 1) * 0.5:
                return True
                
        return False
        
    def get_adjusted_order(self, 
                          role: str, 
                          proposed_order: int, 
                          current_inventory: int, 
                          incoming_shipment: int) -> int:
        """
        Calculate a smoothed order quantity to reduce bullwhip effect.
        """
        if not self.decision_history:
            return proposed_order
            
        # Simple moving average of recent orders
        recent_orders = [d.get('order', 0) for d in self.decision_history[-3:]]
        avg_order = sum(recent_orders) / len(recent_orders)
        
        # Cap the order increase/decrease
        max_increase = current_inventory * 0.3
        smoothed_order = min(proposed_order, avg_order + max_increase)
        
        # Ensure we don't go below zero
        return max(0, int(smoothed_order))
        
    async def review_decision(self, 
                            role: str, 
                            proposed_order: int, 
                            current_inventory: int, 
                            incoming_shipment: int,
                            is_human_decision: bool = False) -> dict:
        """
        Review and potentially modify an order decision.
        Returns a dict with the decision and whether it was overridden.
        """
        bullwhip_metric = await self.analyze_bullwhip_effect({role: proposed_order})
        
        decision = {
            'role': role,
            'proposed_order': proposed_order,
            'final_order': proposed_order,
            'is_overridden': False,
            'is_human_decision': is_human_decision,
            'bullwhip_metric': bullwhip_metric,
            'timestamp': datetime.utcnow()
        }
        
        if not is_human_decision and bullwhip_metric > self.bullwhip_threshold:
            if self.should_override_decision(role, proposed_order, current_inventory, incoming_shipment, is_human_decision):
                decision['final_order'] = self.get_adjusted_order(
                    role, proposed_order, current_inventory, incoming_shipment
                )
                decision['is_overridden'] = True
                self.override_count += 1
                
                # Log the override
                self.db.add(models.SupervisorAction(
                    game_id=self.game_id,
                    role=role,
                    original_order=proposed_order,
                    adjusted_order=decision['final_order'],
                    reason='bullwhip_mitigation',
                    bullwhip_metric=bullwhip_metric
                ))
                self.db.commit()
        
        self.decision_history.append(decision)
        return decision
