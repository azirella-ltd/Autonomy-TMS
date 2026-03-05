"""
SC State Manager

Handles state import/export from SC entities.
The simulation absorbs state from SC tables each round.

Reference: SC State Management
"""

import logging
from datetime import datetime
from typing import Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

logger = logging.getLogger(__name__)

from app.models.sc_entities import InvLevel, Product, SourcingRules, InvPolicy
from app.models.supply_chain_config import Site, SupplyChainConfig, TransportationLane


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
        self.db = db

    # =========================================================================
    # Public Methods
    # =========================================================================

    def load_game_state(
        self,
        scenario_id: int,
        round_number: Optional[int] = None,
    ) -> Dict[int, Dict]:
        """
        Load current game state from SC entities for all sites.

        Args:
            scenario_id: Scenario ID
            round_number: Round number (optional, stored in snapshot for reference)

        Returns:
            Dict mapping site.id (int) → state dict
        """
        config = self._get_game_config(scenario_id)
        product_id = self._get_product_id(config.id)

        sites = (
            self.db.query(Site)
            .filter(Site.config_id == config.id)
            .all()
        )

        return {
            site.id: self.load_site_state(site.id, product_id, scenario_id, round_number)
            for site in sites
        }

    def load_site_state(
        self,
        site_id: int,
        product_id: str,
        scenario_id: Optional[int] = None,
        round_number: Optional[int] = None,
    ) -> Dict:
        """
        Load state for a single site from SC entities.

        Args:
            site_id: Site integer PK
            product_id: Product string PK
            scenario_id: Scenario ID (stored in state dict for reference)
            round_number: Round number (stored in state dict for reference)

        Returns:
            State dictionary
        """
        inv_level = (
            self.db.query(InvLevel)
            .filter(
                and_(
                    InvLevel.site_id == site_id,
                    InvLevel.product_id == product_id,
                )
            )
            .first()
        )

        # Highest-priority sourcing rule for this site/product
        sourcing_rule = (
            self.db.query(SourcingRules)
            .filter(
                and_(
                    SourcingRules.to_site_id == site_id,
                    SourcingRules.product_id == product_id,
                )
            )
            .order_by(SourcingRules.sourcing_priority.asc())
            .first()
        )

        inv_policy = (
            self.db.query(InvPolicy)
            .filter(
                and_(
                    InvPolicy.site_id == site_id,
                    InvPolicy.product_id == product_id,
                )
            )
            .first()
        )

        site = self.db.query(Site).filter(Site.id == site_id).first()

        # Lead time: from TransportationLane via sourcing rule FK.
        # supply_lead_time.value is in weeks/rounds (1 round = 1 week).
        lead_time_days = 14  # 2-week fallback when no TransportationLane is configured
        if sourcing_rule and sourcing_rule.transportation_lane_id:
            lane = self.db.query(TransportationLane).filter(
                TransportationLane.id == sourcing_rule.transportation_lane_id
            ).first()
            if lane and lane.supply_lead_time:
                lead_time_days = int(lane.supply_lead_time.get("value", 2)) * 7
        else:
            logger.warning(
                f"No TransportationLane for site {site_id}/product {product_id} — "
                "defaulting to 14-day lead time. Populate TransportationLane for accurate scheduling."
            )

        # Derive cost rates from Product.unit_cost when InvPolicy lacks explicit rates.
        # Holding: 25% annual / 52 weeks per unit per week.
        # Backlog: 4× holding (standard penalty for unfulfilled demand).
        product = self.db.query(Product).filter(Product.id == product_id).first()
        unit_cost = (product.unit_cost or 0.0) if product else 0.0
        default_holding = unit_cost * 0.25 / 52
        default_backlog = default_holding * 4.0

        if inv_policy:
            hcr = inv_policy.holding_cost_range or {}
            bcr = inv_policy.backlog_cost_range or {}
            holding_cost_rate = hcr.get("min", default_holding)
            backlog_cost_rate = bcr.get("min", default_backlog)
        else:
            holding_cost_rate = default_holding
            backlog_cost_rate = default_backlog

        return {
            "site_id": site_id,
            "product_id": product_id,
            "scenario_id": scenario_id,
            "round_number": round_number,

            # inv_level fields
            "on_hand_qty": inv_level.on_hand_qty if inv_level else 0.0,
            "backorder_qty": (inv_level.backorder_qty or 0.0) if inv_level else 0.0,
            "in_transit_qty": (inv_level.in_transit_qty or 0.0) if inv_level else 0.0,
            "allocated_qty": (inv_level.allocated_qty or 0.0) if inv_level else 0.0,
            "available_qty": self._calculate_atp(inv_level) if inv_level else 0.0,
            "safety_stock_qty": (inv_level.safety_stock_qty or 0.0) if inv_level else 0.0,

            # sourcing_rules fields
            "lead_time_days": lead_time_days,
            "source_type": sourcing_rule.sourcing_rule_type if sourcing_rule else "transfer",
            "source_site_id": sourcing_rule.from_site_id if sourcing_rule else None,
            "sourcing_priority": sourcing_rule.sourcing_priority if sourcing_rule else 1,

            # inv_policy fields
            "policy_type": inv_policy.ss_policy if inv_policy else "abs_level",
            "holding_cost_per_unit": holding_cost_rate,
            "backlog_cost_per_unit": backlog_cost_rate,

            # site info
            "site_type": site.type if site else "INVENTORY",
            "site_name": site.name if site else str(site_id),
        }

    def initialize_game_state(
        self,
        scenario_id: int,
        config_id: int,
        initial_inventory: float = 12.0,
    ) -> None:
        """
        Initialize game state in SC entities.

        Creates or resets inv_level records for all sites using the config's product.

        Args:
            scenario_id: Scenario ID
            config_id: Supply chain config ID
            initial_inventory: Initial on_hand_qty for all sites
        """
        config = self.db.query(SupplyChainConfig).filter(
            SupplyChainConfig.id == config_id
        ).first()
        if not config:
            raise ValueError(f"Config {config_id} not found")

        product_id = self._get_product_id(config_id)
        sites = (
            self.db.query(Site)
            .filter(Site.config_id == config_id)
            .all()
        )

        for site in sites:
            # Safety stock from InvPolicy
            inv_policy = (
                self.db.query(InvPolicy)
                .filter(
                    and_(
                        InvPolicy.site_id == site.id,
                        InvPolicy.product_id == product_id,
                    )
                )
                .first()
            )
            safety_stock = (inv_policy.ss_quantity or 0.0) if inv_policy else 0.0

            existing = (
                self.db.query(InvLevel)
                .filter(
                    and_(
                        InvLevel.site_id == site.id,
                        InvLevel.product_id == product_id,
                    )
                )
                .first()
            )

            if existing:
                existing.on_hand_qty = initial_inventory
                existing.backorder_qty = 0.0
                existing.in_transit_qty = 0.0
                existing.allocated_qty = 0.0
                existing.available_qty = initial_inventory
                existing.safety_stock_qty = safety_stock
            else:
                self.db.add(InvLevel(
                    site_id=site.id,
                    product_id=product_id,
                    on_hand_qty=initial_inventory,
                    backorder_qty=0.0,
                    in_transit_qty=0.0,
                    allocated_qty=0.0,
                    available_qty=initial_inventory,
                    reserved_qty=0.0,
                    safety_stock_qty=safety_stock,
                    config_id=config_id,
                    scenario_id=scenario_id,
                ))

        self.db.commit()

    def snapshot_state(self, scenario_id: int, round_number: int) -> Dict:
        """
        Create a snapshot of current state for analysis.

        Returns:
            Dict with 'scenario_id', 'round_number', 'sites', 'timestamp'
        """
        return {
            "scenario_id": scenario_id,
            "round_number": round_number,
            "sites": self.load_game_state(scenario_id, round_number),
            "timestamp": datetime.now().isoformat(),
        }

    # =========================================================================
    # Private Helpers
    # =========================================================================

    def _get_game_config(self, scenario_id: int) -> SupplyChainConfig:
        from app.models.scenario import Scenario

        scenario = self.db.query(Scenario).filter(Scenario.id == scenario_id).first()
        if not scenario:
            raise ValueError(f"Scenario {scenario_id} not found")

        config = self.db.query(SupplyChainConfig).filter(
            SupplyChainConfig.id == scenario.supply_chain_config_id
        ).first()
        if not config:
            raise ValueError(
                f"SupplyChainConfig {scenario.supply_chain_config_id} not found"
            )
        return config

    def _get_product_id(self, config_id: int) -> str:
        """Return the product_id for this config.

        Prefers products that have InvPolicy records (properly seeded for SC
        execution).  Falls back to the first product alphabetically.
        """
        # Prefer a product that has InvPolicy entries (SC execution is set up)
        product = (
            self.db.query(Product)
            .join(InvPolicy, InvPolicy.product_id == Product.id)
            .filter(Product.config_id == config_id)
            .order_by(Product.id)
            .first()
        )
        if product:
            return product.id
        # Fallback: any product for this config
        product = (
            self.db.query(Product)
            .filter(Product.config_id == config_id)
            .order_by(Product.id)
            .first()
        )
        if product:
            return product.id
        raise ValueError(
            f"No product found for supply chain config {config_id}. "
            f"Ensure at least one Product record with a matching InvPolicy exists for this config before executing rounds. "
            f"Run the DB bootstrap or seed the Product and InvPolicy tables for config {config_id}."
        )

    def _calculate_atp(self, inv_level: Optional[InvLevel]) -> float:
        """ATP = on_hand - allocated - safety_stock (floor 0)."""
        if not inv_level:
            return 0.0
        return max(
            0.0,
            (inv_level.on_hand_qty or 0.0)
            - (inv_level.allocated_qty or 0.0)
            - (inv_level.safety_stock_qty or 0.0),
        )
