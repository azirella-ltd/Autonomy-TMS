"""
Cost Calculator - SC Execution

Calculates holding and backlog costs using inv_policy parameters.

Reference: SC Cost Management
"""

from datetime import datetime
from typing import Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.sc_entities import InvLevel, InvPolicy
from app.models.compatibility import Item, ProductSiteConfig  # Temporary compat


class CostCalculator:
    """
    Cost Calculator for inventory holding and backlog costs.

    Uses SC inv_policy parameters to calculate:
    - Holding cost = on_hand_qty * holding_cost_per_unit
    - Backlog cost = backorder_qty * backlog_cost_per_unit

    The Beer Game uses this to accrue costs each round.
    """

    def __init__(self, db: Session):
        """
        Initialize cost calculator.

        Args:
            db: Database session
        """
        self.db = db

    def calculate_site_cost(
        self,
        site_id: str,
        item_id: str
    ) -> Dict[str, float]:
        """
        Calculate cost for a single site.

        Args:
            site_id: Site identifier
            item_id: Item identifier

        Returns:
            Dictionary with cost breakdown
        """
        # Get inv_level
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.item_id == item_id
            )
        ).first()

        if not inv_level:
            return {
                "site_id": site_id,
                "item_id": item_id,
                "on_hand_qty": 0.0,
                "backorder_qty": 0.0,
                "holding_cost": 0.0,
                "backlog_cost": 0.0,
                "total_cost": 0.0
            }

        # Get inv_policy for cost rates
        inv_policy = self.db.query(InvPolicy).filter(
            and_(
                InvPolicy.site_id == site_id,
                InvPolicy.item_id == item_id
            )
        ).first()

        # Default cost rates (Beer Game standard)
        holding_cost_rate = 0.5
        backlog_cost_rate = 1.0

        if inv_policy:
            holding_cost_rate = getattr(inv_policy, "holding_cost_per_unit", 0.5)
            backlog_cost_rate = getattr(inv_policy, "backlog_cost_per_unit", 1.0)

        # Calculate costs
        holding_cost = inv_level.on_hand_qty * holding_cost_rate
        backlog_cost = inv_level.backorder_qty * backlog_cost_rate
        total_cost = holding_cost + backlog_cost

        return {
            "site_id": site_id,
            "item_id": item_id,
            "on_hand_qty": inv_level.on_hand_qty,
            "backorder_qty": inv_level.backorder_qty,
            "holding_cost_rate": holding_cost_rate,
            "backlog_cost_rate": backlog_cost_rate,
            "holding_cost": holding_cost,
            "backlog_cost": backlog_cost,
            "total_cost": total_cost
        }

    def calculate_game_cost(
        self,
        game_id: int,
        site_ids: List[str],
        item_id: str = "cases"
    ) -> Dict:
        """
        Calculate total cost for all sites in Beer Game.

        Args:
            game_id: Game ID
            site_ids: List of site IDs
            item_id: Item ID (default: "cases")

        Returns:
            Dictionary with aggregate costs
        """
        site_costs = []
        total_holding_cost = 0.0
        total_backlog_cost = 0.0
        total_cost = 0.0

        for site_id in site_ids:
            site_cost = self.calculate_site_cost(site_id, item_id)
            site_costs.append(site_cost)

            total_holding_cost += site_cost["holding_cost"]
            total_backlog_cost += site_cost["backlog_cost"]
            total_cost += site_cost["total_cost"]

        return {
            "game_id": game_id,
            "item_id": item_id,
            "site_costs": site_costs,
            "total_holding_cost": total_holding_cost,
            "total_backlog_cost": total_backlog_cost,
            "total_cost": total_cost,
            "num_sites": len(site_ids)
        }

    def record_round_cost(
        self,
        game_id: int,
        round_number: int,
        site_costs: Dict
    ) -> None:
        """
        Record costs for a round in beer_game_round table.

        Args:
            game_id: Game ID
            round_number: Round number
            site_costs: Cost dictionary from calculate_game_cost()
        """
        # TODO: Insert into beer_game_round table
        # This will be implemented after beer_game_round table is created
        pass
