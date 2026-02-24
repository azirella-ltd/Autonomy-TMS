"""
SC State Manager

Handles state import/export from SC entities.
The simulation absorbs state from SC tables each round.

Reference: SC State Management
"""

from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.sc_entities import InvLevel, Product, SourcingRules, InvPolicy
from app.models.supply_chain_config import Site, SupplyChainConfig


class SCStateManager:
    """
    Supply Chain State Manager.

    Manages state absorption and persistence for SC execution:
    - Load current state from inv_level, purchase_order, etc.
    - Initialize new games with SC state
    - Export state snapshots for analysis

    The simulation engine uses this to absorb state each round (not custom initialization).
    """

    def __init__(self, db: Session):
        """
        Initialize state manager.

        Args:
            db: Database session
        """
        self.db = db

    def load_game_state(
        self,
        scenario_id: int,
        round_number: Optional[int] = None
    ) -> Dict[str, Dict]:
        """
        Load current game state from SC entities.

        Returns state for all sites in the game.

        Args:
            scenario_id: Game ID
            round_number: Round number (optional, for filtering)

        Returns:
            Dictionary mapping site_id to state dict
        """
        # Get sites for this game
        config = self._get_game_config(scenario_id)
        sites = self.db.query(Site).filter(
            Site.config_id == config.id
        ).all()

        game_state = {}

        for site in sites:
            site_state = self.load_site_state(
                site.site_id,
                "cases",  # simulation may use single item
                scenario_id,
                round_number
            )
            game_state[site.site_id] = site_state

        return game_state

    def load_site_state(
        self,
        site_id: str,
        item_id: str,
        scenario_id: Optional[int] = None,
        round_number: Optional[int] = None
    ) -> Dict:
        """
        Load state for a single site from SC entities.

        Args:
            site_id: Site identifier
            item_id: Item identifier
            scenario_id: Game ID (optional)
            round_number: Round number (optional)

        Returns:
            State dictionary with SC fields
        """
        # Get inv_level
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.item_id == item_id
            )
        ).first()

        # Get sourcing rule
        sourcing_rule = self.db.query(SourcingRules).filter(
            and_(
                SourcingRules.destination_site_id == site_id,
                SourcingRules.item_id == item_id
            )
        ).order_by(SourcingRules.priority.asc()).first()

        # Get inv_policy
        inv_policy = self.db.query(InvPolicy).filter(
            and_(
                InvPolicy.site_id == site_id,
                InvPolicy.item_id == item_id
            )
        ).first()

        # Get site info
        site = self.db.query(Site).filter(Site.site_id == site_id).first()

        # Build state dict (SC format)
        state = {
            "site_id": site_id,
            "item_id": item_id,
            "scenario_id": scenario_id,
            "round_number": round_number,

            # SC inv_level fields
            "on_hand_qty": inv_level.on_hand_qty if inv_level else 0.0,
            "backorder_qty": inv_level.backorder_qty if inv_level else 0.0,
            "in_transit_qty": inv_level.in_transit_qty if inv_level else 0.0,
            "allocated_qty": inv_level.allocated_qty if inv_level else 0.0,
            "available_qty": self._calculate_atp(inv_level) if inv_level else 0.0,
            "safety_stock_qty": inv_level.safety_stock_qty if inv_level else 0.0,
            "reorder_point_qty": inv_level.reorder_point_qty if inv_level else 0.0,
            "min_qty": inv_level.min_qty if inv_level else 0.0,
            "max_qty": inv_level.max_qty if inv_level else 1000.0,

            # SC sourcing_rules fields
            "lead_time_days": sourcing_rule.lead_time_days if sourcing_rule else 14,
            "source_type": sourcing_rule.source_type if sourcing_rule else "transfer",
            "source_site_id": sourcing_rule.source_site_id if sourcing_rule else None,
            "priority": sourcing_rule.priority if sourcing_rule else 1,

            # SC inv_policy fields (extensions)
            "policy_type": inv_policy.policy_type if inv_policy else "abs_level",
            "holding_cost_per_unit": getattr(inv_policy, "holding_cost_per_unit", 0.5) if inv_policy else 0.5,
            "backlog_cost_per_unit": getattr(inv_policy, "backlog_cost_per_unit", 1.0) if inv_policy else 1.0,

            # Site info
            "site_type": site.site_type if site else "INVENTORY",
            "site_name": site.name if site else site_id,
        }

        return state

    def initialize_game_state(
        self,
        scenario_id: int,
        config_id: int,
        initial_inventory: float = 12.0
    ) -> None:
        """
        Initialize game state in SC entities.

        Creates inv_level records for all sites in the config.

        Args:
            scenario_id: Game ID
            config_id: Supply chain config ID
            initial_inventory: Initial on_hand_qty for all sites
        """
        # Get config
        config = self.db.query(SupplyChainConfig).filter(
            SupplyChainConfig.id == config_id
        ).first()

        if not config:
            raise ValueError(f"Config {config_id} not found")

        # Get sites from config
        sites = self.db.query(Site).filter(
            Site.config_id == config_id
        ).all()

        # Create inv_level for each site
        for site in sites:
            # Check if inv_level exists
            existing = self.db.query(InvLevel).filter(
                and_(
                    InvLevel.site_id == site.site_id,
                    InvLevel.item_id == "cases"
                )
            ).first()

            if not existing:
                inv_level = InvLevel(
                    site_id=site.site_id,
                    item_id="cases",
                    on_hand_qty=initial_inventory,
                    backorder_qty=0.0,
                    in_transit_qty=0.0,
                    allocated_qty=0.0,
                    available_qty=initial_inventory,
                    safety_stock_qty=0.0,
                    reorder_point_qty=0.0,
                    min_qty=0.0,
                    max_qty=1000.0
                )
                self.db.add(inv_level)
            else:
                # Reset existing inv_level
                existing.on_hand_qty = initial_inventory
                existing.backorder_qty = 0.0
                existing.in_transit_qty = 0.0
                existing.allocated_qty = 0.0
                existing.available_qty = initial_inventory

        self.db.commit()

    def snapshot_state(
        self,
        scenario_id: int,
        round_number: int
    ) -> Dict:
        """
        Create snapshot of current state for analysis.

        Args:
            scenario_id: Game ID
            round_number: Round number

        Returns:
            Complete state snapshot
        """
        snapshot = {
            "scenario_id": scenario_id,
            "round_number": round_number,
            "sites": self.load_game_state(scenario_id, round_number),
            "timestamp": datetime.now().isoformat()
        }

        return snapshot

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _get_game_config(self, scenario_id: int) -> SupplyChainConfig:
        """Get supply chain config for game."""
        from app.models.scenario import Scenario as Game

        game = self.db.query(Game).filter(Game.id == scenario_id).first()
        if not game:
            raise ValueError(f"Game {scenario_id} not found")

        config = self.db.query(SupplyChainConfig).filter(
            SupplyChainConfig.id == game.config_id
        ).first()

        if not config:
            raise ValueError(f"Config {game.config_id} not found")

        return config

    def _calculate_atp(self, inv_level: Optional[InvLevel]) -> float:
        """Calculate Available-to-Promise."""
        if not inv_level:
            return 0.0

        atp = (
            inv_level.on_hand_qty
            - inv_level.allocated_qty
            - inv_level.safety_stock_qty
        )
        return max(0.0, atp)


from datetime import datetime  # Import at module level
