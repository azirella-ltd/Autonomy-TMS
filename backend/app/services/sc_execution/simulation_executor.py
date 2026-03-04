"""
simulation Executor - SC Execution

Period-by-period execution of The simulation using SC operations.

**Key Insight**: The simulation is just iterative SC execution:
1. Absorb state from SC entities
2. Execute order promising (fulfill demand)
3. Agents decide order quantities
4. Create purchase orders
5. Update SC entities
6. Accrue costs

Reference: SC Execution
"""

from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from .order_promising import OrderPromisingEngine, ATPResult, ShipmentRecord
from .po_creation import PurchaseOrderCreator
from .state_manager import SCStateManager
from .cost_calculator import CostCalculator
from .site_id_mapper import SimulationIdMapper

from app.models.sc_entities import OutboundOrderLine
from app.models.supply_chain_config import Site
from app.models.purchase_order import PurchaseOrder
from app.models.scenario import Scenario

# Aliases for backwards compatibility
Game = Scenario


class SimulationExecutor:
    """
    simulation Executor - Orchestrates round-by-round SC execution.

    This executor replaces the custom simulation engine (engine.py) with
    SC operations. Each round:

    1. **Receive Shipments**: Process arriving POs (lead time completion)
    2. **Generate Market Demand**: Create outbound_order_line
    3. **Order Promising**: Fulfill demand (ATP check)
    4. **Agent Decisions**: Agents decide order quantities
    5. **PO Creation**: Create purchase_orders upstream
    6. **Cost Accrual**: Calculate holding/backlog costs
    7. **State Persistence**: All state in SC entities

    The simulation becomes a teaching/validation tool for SC execution.
    """

    def __init__(self, db: Session, scenario: Optional[Scenario] = None):
        """
        Initialize simulation executor.

        Args:
            db: Database session
            scenario: Scenario (Game) instance. Required for config-aware execution.
        """
        self.db = db
        self.scenario = scenario
        self.config_id = scenario.supply_chain_config_id if scenario else None
        self._product = None
        self._sites: List[Site] = []

        # Initialize SC execution components
        self.order_promising = OrderPromisingEngine(db)
        self.po_creator = PurchaseOrderCreator(db)
        self.state_manager = SCStateManager(db)
        self.cost_calculator = CostCalculator(db)

    def _load_config(self) -> None:
        """
        Load product and sites from DB for this scenario's SC config.
        Must be called before execute_round() when scenario is provided.
        """
        if not self.config_id:
            return
        from app.models.sc_entities import Product as ProductModel, InvPolicy
        # Prefer a product that has InvPolicy records (properly seeded)
        self._product = (
            self.db.query(ProductModel)
            .join(InvPolicy, InvPolicy.product_id == ProductModel.id)
            .filter(ProductModel.config_id == self.config_id)
            .order_by(ProductModel.id)
            .first()
        )
        if not self._product:
            # Fallback: any product for this config
            self._product = (
                self.db.query(ProductModel)
                .filter(ProductModel.config_id == self.config_id)
                .order_by(ProductModel.id)
                .first()
            )
        self._sites = (
            self.db.query(Site)
            .filter(Site.config_id == self.config_id)
            .all()
        )

    def _get_site_by_role(self, role: str) -> Optional[Site]:
        """Get site matching a role name (e.g. 'Retailer')."""
        return next(
            (s for s in self._sites if s.name == role or (s.site_type or '').lower() == role.lower()),
            None
        )

    def _get_retailer_site(self) -> Optional[Site]:
        """Return the most downstream INVENTORY site (Retailer)."""
        return next(
            (s for s in self._sites if 'retail' in (s.name or '').lower()),
            self._sites[0] if self._sites else None
        )

    def _get_product_id(self) -> str:
        """Return the product ID for this config, falling back to 'TBG-CASES'."""
        return self._product.id if self._product else "TBG-CASES"

    def _get_retailer_site_id(self) -> Optional[int]:
        """Return the site_id (int) of the retailer site."""
        site = self._get_retailer_site()
        return site.id if site else None

    def execute_round(
        self,
        round_number: int,
        agent_decisions: Dict[str, float],
        market_demand: Optional[float] = None,
        scenario_id: Optional[int] = None,
    ) -> Dict:
        """
        Execute complete simulation round using SC operations.

        This is the CORE method that replaces SupplyChainLine.tick().

        Args:
            round_number: Current round number
            agent_decisions: Dict mapping role/site_id to order_qty
                Example: {"Retailer": 12.0, "Wholesaler": 15.0}
            market_demand: Market demand qty (if generated this round)
            scenario_id: Deprecated — use self.scenario.id instead.

        Returns:
            Round execution summary
        """
        _scenario_id = self.scenario.id if self.scenario else (scenario_id or 0)

        print(f"\n{'='*80}")
        print(f"SIMULATION ROUND {round_number} - SC EXECUTION")
        print(f"Game ID: {_scenario_id}")
        print(f"{'='*80}\n")

        # Get current round date
        round_date = self._get_round_date(_scenario_id, round_number)

        # Track round execution
        round_summary = {
            "scenario_id": _scenario_id,
            "round_number": round_number,
            "round_date": round_date,
            "steps": {}
        }

        # ====================================================================
        # STEP 1: RECEIVE SHIPMENTS (Lead Time Completion)
        # ====================================================================
        print("📦 STEP 1: Receiving Shipments (POs and TOs arriving this round)")
        print("-" * 80)

        # 1a. Process arriving Purchase Orders
        arriving_pos = self.po_creator.process_arriving_orders(_scenario_id, round_number)

        print(f"✓ Received {len(arriving_pos)} purchase orders")
        for po in arriving_pos:
            print(f"  • PO {po.po_number} → site {po.destination_site_id}")

        # 1b. Process arriving Transfer Orders
        arriving_tos = self.order_promising.process_arriving_transfers(_scenario_id, round_number)

        print(f"✓ Received {len(arriving_tos)} transfer orders")
        for to in arriving_tos:
            print(f"  • TO {to.to_number}: "
                  f"{to.source_site_id} → {to.destination_site_id}")

        round_summary["steps"]["shipments_received"] = {
            "purchase_orders": {
                "count": len(arriving_pos),
                "pos": [po.po_number for po in arriving_pos]
            },
            "transfer_orders": {
                "count": len(arriving_tos),
                "tos": [to.to_number for to in arriving_tos]
            }
        }

        # ====================================================================
        # STEP 2: GENERATE MARKET DEMAND (If applicable)
        # ====================================================================
        if market_demand is not None and market_demand > 0:
            print(f"\n📊 STEP 2: Generating Market Demand")
            print("-" * 80)

            # Create outbound order line (SC entity)
            retailer_site_id = self._get_retailer_site_id()
            outbound_order = OutboundOrderLine(
                order_id=f"MARKET-G{_scenario_id}-R{round_number}",
                line_number=1,
                product_id=self._get_product_id(),
                site_id=retailer_site_id,
                ordered_quantity=market_demand,
                requested_delivery_date=round_date,
                order_date=round_date,
                config_id=self.config_id or self._get_game_config_id(_scenario_id),
                scenario_id=_scenario_id
            )
            self.db.add(outbound_order)
            self.db.commit()

            print(f"✓ Market demand: {market_demand} units → Retailer")

            round_summary["steps"]["market_demand"] = {
                "quantity": market_demand,
                "order_id": outbound_order.order_id
            }

        # ====================================================================
        # STEP 3: ORDER PROMISING (Fulfill Demand)
        # ====================================================================
        print(f"\n🎯 STEP 3: Order Promising (Fulfilling Demand)")
        print("-" * 80)

        atp_results = self.order_promising.process_round_demand(
            _scenario_id, round_number
        )

        print(f"✓ Processed {len(atp_results)} order promising operations")
        for atp, transfer_order in atp_results:
            if atp.can_fulfill:
                status = "FULL"
            elif atp.promised_qty > 0:
                status = "PARTIAL"
            else:
                status = "NONE"

            to_info = f"TO: {transfer_order.to_number}" if transfer_order else "No TO"
            print(f"  • {atp.site_id}: {status} fulfillment "
                  f"({atp.promised_qty}/{atp.requested_qty} units) - {to_info}")

        round_summary["steps"]["order_promising"] = {
            "operations": len(atp_results),
            "results": [
                {
                    "site_id": atp.site_id,
                    "requested": atp.requested_qty,
                    "fulfilled": atp.promised_qty,
                    "backorder": atp.backorder_qty,
                    "transfer_order": to.to_number if to else None
                }
                for atp, to in atp_results
            ]
        }

        # ====================================================================
        # STEP 4: AGENT DECISIONS (Already provided in agent_decisions dict)
        # ====================================================================
        print(f"\n🤖 STEP 4: Agent Decisions")
        print("-" * 80)

        print(f"✓ Agents decided order quantities:")
        for site_id, order_qty in agent_decisions.items():
            print(f"  • {site_id}: {order_qty} units")

        round_summary["steps"]["agent_decisions"] = agent_decisions

        # ====================================================================
        # STEP 5: PURCHASE ORDER CREATION
        # ====================================================================
        print(f"\n📝 STEP 5: Creating Purchase Orders")
        print("-" * 80)

        # Get config ID for ID mapping
        config_id = self.config_id or self._get_game_config_id(_scenario_id)

        created_pos = self.po_creator.create_simulation_orders(
            _scenario_id, round_number, agent_decisions, config_id
        )

        print(f"✓ Created {len(created_pos)} purchase orders")
        for po in created_pos:
            print(f"  • {po.po_number}: site {po.destination_site_id} → "
                  f"{po.supplier_site_id} (arrives round {po.arrival_round})")

        round_summary["steps"]["purchase_orders"] = {
            "count": len(created_pos),
            "pos": [
                {
                    "po_number": po.po_number,
                    "from_site": po.destination_site_id,
                    "to_site": po.supplier_site_id,
                    "arrival_round": po.arrival_round
                }
                for po in created_pos
            ]
        }

        # ====================================================================
        # STEP 6: COST ACCRUAL
        # ====================================================================
        print(f"\n💰 STEP 6: Cost Accrual")
        print("-" * 80)

        # Get all sites
        sites = self._sites if self._sites else self._get_game_sites(_scenario_id)
        site_ids = [site.id for site in sites]

        # Calculate costs
        cost_summary = self.cost_calculator.calculate_game_cost(
            _scenario_id, site_ids, self._get_product_id()
        )

        print(f"✓ Total Holding Cost: ${cost_summary['total_holding_cost']:.2f}")
        print(f"✓ Total Backlog Cost: ${cost_summary['total_backlog_cost']:.2f}")
        print(f"✓ Total Cost: ${cost_summary['total_cost']:.2f}")

        print(f"\n  Site Breakdown:")
        for site_cost in cost_summary["site_costs"]:
            print(f"  • {site_cost['site_id']}: "
                  f"${site_cost['total_cost']:.2f} "
                  f"(holding: ${site_cost['holding_cost']:.2f}, "
                  f"backlog: ${site_cost['backlog_cost']:.2f})")

        round_summary["steps"]["costs"] = cost_summary

        # ====================================================================
        # STEP 7: STATE SNAPSHOT
        # ====================================================================
        print(f"\n📸 STEP 7: State Snapshot")
        print("-" * 80)

        state_snapshot = self.state_manager.snapshot_state(_scenario_id, round_number)

        print(f"✓ State snapshot captured")
        print(f"  Sites: {len(state_snapshot['sites'])}")

        round_summary["state_snapshot"] = state_snapshot

        # ====================================================================
        # ROUND COMPLETE
        # ====================================================================
        print(f"\n{'='*80}")
        print(f"✅ ROUND {round_number} COMPLETE")
        print(f"{'='*80}\n")

        round_summary["status"] = "completed"
        round_summary["completed_at"] = datetime.now().isoformat()

        return round_summary

    def initialize_game(
        self,
        scenario_id: int,
        config_id: int,
        initial_inventory: float = 12.0
    ) -> None:
        """
        Initialize simulation state using SC entities.

        Creates inv_level records for all sites.

        Args:
            scenario_id: Game ID
            config_id: Supply chain config ID
            initial_inventory: Initial inventory for all sites
        """
        print(f"\n{'='*80}")
        print(f"INITIALIZING SIMULATION {scenario_id}")
        print(f"{'='*80}\n")

        self.state_manager.initialize_game_state(
            scenario_id, config_id, initial_inventory
        )

        print(f"✓ Game initialized with SC state")
        print(f"  Initial inventory: {initial_inventory} units per site")

    def get_game_status(self, scenario_id: int) -> Dict:
        """
        Get current game status from SC entities.

        Args:
            scenario_id: Game ID

        Returns:
            Game status dictionary
        """
        # Get current round
        game = self.db.query(Game).filter(Game.id == scenario_id).first()
        if not game:
            raise ValueError(f"Game {scenario_id} not found")

        # Load current state
        current_state = self.state_manager.load_game_state(scenario_id)

        # Get sites
        sites = self._get_game_sites(scenario_id)

        # Calculate current costs
        cost_summary = self.cost_calculator.calculate_game_cost(
            scenario_id,
            [site.id for site in sites],
            self._get_product_id(),
        )

        return {
            "scenario_id": scenario_id,
            "current_round": game.current_round or 0,
            "max_rounds": game.max_rounds or 52,
            "status": game.status,
            "state": current_state,
            "costs": cost_summary
        }

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _get_round_date(self, scenario_id: int, round_number: int) -> date:
        """Get date for round (1 round = 1 week)."""
        game = self.db.query(Game).filter(Game.id == scenario_id).first()
        if not game:
            raise ValueError(f"Game {scenario_id} not found")

        # Start date (default: today)
        start_date = game.created_at.date() if game.created_at else date.today()

        # Calculate round date (1 round = 7 days)
        round_date = start_date + timedelta(days=(round_number - 1) * 7)

        return round_date

    def _get_game_config_id(self, scenario_id: int) -> int:
        """Get config ID for game."""
        if self.config_id:
            return self.config_id
        game = self.db.query(Game).filter(Game.id == scenario_id).first()
        if not game:
            raise ValueError(f"Game {scenario_id} not found")
        return game.supply_chain_config_id

    def _get_id_mapper(self, scenario_id: int) -> SimulationIdMapper:
        """
        Get ID mapper for translating between node names and node IDs.

        Args:
            scenario_id: Game ID

        Returns:
            SimulationIdMapper instance
        """
        config_id = self._get_game_config_id(scenario_id)
        return SimulationIdMapper(self.db, config_id)

    def _get_game_sites(self, scenario_id: int) -> List[Site]:
        """Get all sites for game. Uses cached self._sites if available."""
        if self._sites:
            return self._sites
        config_id = self._get_game_config_id(scenario_id)
        sites = self.db.query(Site).filter(Site.config_id == config_id).all()
        return sites
