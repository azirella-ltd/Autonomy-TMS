"""
Cost Calculator - SC Execution

Calculates holding and backlog costs using inv_policy parameters.

Reference: SC Cost Management
"""

from typing import Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.sc_entities import InvLevel, InvPolicy, Product


class CostCalculator:
    """
    Cost Calculator for inventory holding and backlog costs.

    Uses SC inv_policy parameters to calculate:
    - Holding cost = on_hand_qty * holding_cost_rate
    - Backlog cost = backorder_qty * backlog_cost_rate

    Cost rates are read from InvPolicy.holding_cost_range / backlog_cost_range JSON
    (min value used as the rate).

    The simulation uses this to accrue costs each round.
    """

    def __init__(self, db: Session):
        self.db = db

    def calculate_site_cost(
        self,
        site_id: int,
        product_id: str
    ) -> Dict[str, float]:
        """
        Calculate cost for a single site.

        Args:
            site_id: Site integer PK
            product_id: Product string PK

        Returns:
            Dictionary with cost breakdown
        """
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == site_id,
                InvLevel.product_id == product_id,
            )
        ).first()

        if not inv_level:
            return {
                "site_id": site_id,
                "product_id": product_id,
                "on_hand_qty": 0.0,
                "backorder_qty": 0.0,
                "holding_cost": 0.0,
                "backlog_cost": 0.0,
                "total_cost": 0.0,
            }

        # Get inv_policy for cost rates
        inv_policy = self.db.query(InvPolicy).filter(
            and_(
                InvPolicy.site_id == site_id,
                InvPolicy.product_id == product_id,
            )
        ).first()

        # Derive cost rates from Product.unit_cost when InvPolicy lacks explicit rates.
        # Holding: 25% annual cost / 52 weeks = unit_cost * 0.25 / 52 per unit per week.
        # Backlog: 4× holding rate (industry standard penalty for unfulfilled demand).
        # This replaces the former Beer Scenario hardcoded defaults (0.5 / 1.0).
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

        on_hand = inv_level.on_hand_qty or 0.0
        backorder = inv_level.backorder_qty or 0.0

        holding_cost = on_hand * holding_cost_rate
        backlog_cost = backorder * backlog_cost_rate
        total_cost = holding_cost + backlog_cost

        return {
            "site_id": site_id,
            "product_id": product_id,
            "on_hand_qty": on_hand,
            "backorder_qty": backorder,
            "holding_cost_rate": holding_cost_rate,
            "backlog_cost_rate": backlog_cost_rate,
            "holding_cost": holding_cost,
            "backlog_cost": backlog_cost,
            "total_cost": total_cost,
        }

    def calculate_scenario_cost(
        self,
        scenario_id: int,
        site_ids: List[int],
        product_id: str,
    ) -> Dict:
        """
        Calculate total cost for all sites in simulation.

        Args:
            scenario_id: Scenario ID
            site_ids: List of site integer PKs
            product_id: Product string PK

        Returns:
            Dictionary with aggregate costs
        """
        site_costs = []
        total_holding_cost = 0.0
        total_backlog_cost = 0.0
        total_cost = 0.0

        for site_id in site_ids:
            site_cost = self.calculate_site_cost(site_id, product_id)
            site_costs.append(site_cost)
            total_holding_cost += site_cost["holding_cost"]
            total_backlog_cost += site_cost["backlog_cost"]
            total_cost += site_cost["total_cost"]

        return {
            "scenario_id": scenario_id,
            "product_id": product_id,
            "site_costs": site_costs,
            "total_holding_cost": total_holding_cost,
            "total_backlog_cost": total_backlog_cost,
            "total_cost": total_cost,
            "num_sites": len(site_ids),
        }

    def record_round_cost(
        self,
        scenario_id: int,
        round_number: int,
        site_costs: Dict
    ) -> None:
        """
        Record costs for a round by updating ScenarioUserPeriod records.

        Args:
            scenario_id: Scenario ID
            round_number: Round number
            site_costs: Cost dictionary from calculate_scenario_cost()
        """
        from app.models.scenario import ScenarioPeriod
        from app.models.participant import ScenarioUserPeriod

        scenario_round = (
            self.db.query(ScenarioPeriod)
            .filter(
                ScenarioPeriod.scenario_id == scenario_id,
                ScenarioPeriod.round_number == round_number,
            )
            .first()
        )
        if not scenario_round:
            return

        for site_cost in site_costs.get("site_costs", []):
            pr = (
                self.db.query(ScenarioUserPeriod)
                .filter(ScenarioUserPeriod.scenario_round_id == scenario_round.id)
                .first()
            )
            if pr:
                pr.holding_cost = site_cost.get("holding_cost", 0.0)
                pr.backorder_cost = site_cost.get("backlog_cost", 0.0)
                pr.total_cost = site_cost.get("total_cost", 0.0)

        self.db.commit()
