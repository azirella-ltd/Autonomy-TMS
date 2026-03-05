"""
Supply Chain Planner - Main Orchestrator

Implements the 3-step planning process:
1. Demand Processing
2. Inventory Target Calculation
3. Net Requirements Calculation

Orchestrates demand aggregation, safety stock calculation, and supply plan generation.
"""

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
import logging
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.supply_chain_config import SupplyChainConfig
from app.models.sc_entities import SupplyPlan

from .demand_processor import DemandProcessor
from .inventory_target_calculator import InventoryTargetCalculator
from .net_requirements_calculator import NetRequirementsCalculator
from .planning_types import DemandEstimateDict

logger = logging.getLogger(__name__)


class SupplyChainPlanner:
    """
    Main planning orchestrator following SC 3-step process

    This class coordinates the end-to-end planning workflow:
    - Loads configuration data
    - Executes 3-step planning algorithm
    - Generates supply plan recommendations
    """

    def __init__(self, config_id: int, tenant_id: int, planning_horizon: int = 52):
        """
        Initialize planner

        Args:
            config_id: Supply chain configuration ID
            tenant_id: Customer ID for multi-tenancy (Phase 2)
            planning_horizon: Number of days to plan ahead (default: 52)
        """
        self.config_id = config_id
        self.tenant_id = tenant_id
        self.planning_horizon = planning_horizon

        # Initialize sub-processors
        self.demand_processor = DemandProcessor(config_id, tenant_id)
        self.inventory_target_calculator = InventoryTargetCalculator(config_id, tenant_id)
        self.net_requirements_calculator = NetRequirementsCalculator(config_id, tenant_id, planning_horizon)

    async def run_planning(
        self,
        start_date: date,
        scenario_id: Optional[int] = None
    ) -> List[SupplyPlan]:
        """
        Execute full SC planning process

        Args:
            start_date: Planning start date
            scenario_id: Optional game ID for scenario integration

        Returns:
            List of SupplyPlan recommendations (PO/TO/MO requests)
        """
        print(f"🚀 Starting SC Planning Process")
        print(f"   Config ID: {self.config_id}")
        print(f"   Start Date: {start_date}")
        print(f"   Planning Horizon: {self.planning_horizon} days")
        print(f"   Game ID: {scenario_id or 'N/A'}")
        print()

        # ========================================================================
        # STEP 1: DEMAND PROCESSING
        # ========================================================================
        print("📊 STEP 1: Demand Processing")
        print("-" * 80)

        net_demand = await self.demand_processor.process_demand(
            start_date, self.planning_horizon
        )

        print(f"✓ Processed demand for {len(net_demand)} product-site-date combinations")
        print()

        # ========================================================================
        # STEP 2: INVENTORY TARGET CALCULATION
        # ========================================================================
        print("🎯 STEP 2: Inventory Target Calculation")
        print("-" * 80)

        target_inventory = await self.inventory_target_calculator.calculate_targets(
            net_demand, start_date
        )

        print(f"✓ Calculated targets for {len(target_inventory)} product-site combinations")
        print()

        # ========================================================================
        # STEP 3: NET REQUIREMENTS CALCULATION
        # ========================================================================
        print("📦 STEP 3: Net Requirements Calculation")
        print("-" * 80)

        supply_plans = await self.net_requirements_calculator.calculate_requirements(
            net_demand, target_inventory, start_date, scenario_id
        )

        print(f"✓ Generated {len(supply_plans)} supply plan recommendations")
        print()

        # ========================================================================
        # SUMMARY
        # ========================================================================
        print("=" * 80)
        print(f"✅ Planning Complete")
        print("=" * 80)

        # Count by plan type
        plan_types = {}
        for plan in supply_plans:
            plan_types[plan.plan_type] = plan_types.get(plan.plan_type, 0) + 1

        print("Supply Plans Generated:")
        for plan_type, count in plan_types.items():
            print(f"  • {plan_type}: {count}")
        print()

        return supply_plans

    async def run_planning_with_intervals(
        self,
        start_date: date,
        scenario_id: Optional[int] = None,
        include_confidence: bool = True,
    ) -> Tuple[List[SupplyPlan], Optional[dict], DemandEstimateDict]:
        """
        Execute SC planning with conformal prediction intervals propagated
        through all 3 steps.

        Returns:
            Tuple of:
            - List of SupplyPlan recommendations (enriched with conformal metadata)
            - Optional plan confidence score dict
            - DemandEstimateDict for downstream consumers
        """
        logger.info("Starting SC Planning with Conformal Intervals")
        logger.info(f"  Config ID: {self.config_id}, Start: {start_date}, "
                     f"Horizon: {self.planning_horizon} days")

        # ====================================================================
        # STEP 1: DEMAND PROCESSING (with intervals)
        # ====================================================================
        demand_estimates = await self.demand_processor.process_demand_with_intervals(
            start_date, self.planning_horizon
        )

        # Extract scalar dict for backward-compatible Steps 2 & 3
        net_demand = {k: v.point for k, v in demand_estimates.items()}

        interval_count = sum(1 for v in demand_estimates.values() if v.has_interval)
        logger.info(f"Step 1 complete: {len(demand_estimates)} entries "
                     f"({interval_count} with conformal intervals)")

        # ====================================================================
        # STEP 2: INVENTORY TARGET CALCULATION (unchanged — already supports conformal policies)
        # ====================================================================
        target_inventory = await self.inventory_target_calculator.calculate_targets(
            net_demand, start_date
        )
        logger.info(f"Step 2 complete: {len(target_inventory)} targets")

        # ====================================================================
        # STEP 3: NET REQUIREMENTS CALCULATION (with interval metadata)
        # ====================================================================
        supply_plans = await self.net_requirements_calculator.calculate_requirements_with_intervals(
            net_demand, demand_estimates, target_inventory, start_date, scenario_id
        )
        logger.info(f"Step 3 complete: {len(supply_plans)} supply plans")

        # ====================================================================
        # STEP 4: PLAN CONFIDENCE SCORE (optional)
        # ====================================================================
        plan_confidence = None
        if include_confidence:
            try:
                from .plan_confidence import PlanConfidenceCalculator
                from ..conformal_prediction.suite import get_conformal_suite

                calculator = PlanConfidenceCalculator()
                confidence = calculator.compute(
                    demand_estimates=demand_estimates,
                    supply_plans=supply_plans,
                    target_inventory=target_inventory,
                    suite=get_conformal_suite(),
                )
                plan_confidence = confidence.to_dict()
                logger.info(f"Plan confidence: {confidence.overall:.2f} ({confidence.confidence_level})")
            except Exception as e:
                logger.warning(f"Plan confidence computation failed: {e}")

        return supply_plans, plan_confidence, demand_estimates

    async def get_config(self) -> SupplyChainConfig:
        """Load supply chain configuration"""
        async with SessionLocal() as db:
            result = await db.execute(
                select(SupplyChainConfig)
                .options(
                    selectinload(SupplyChainConfig.nodes),
                    selectinload(SupplyChainConfig.items),
                    selectinload(SupplyChainConfig.lanes),
                    selectinload(SupplyChainConfig.markets),
                    selectinload(SupplyChainConfig.market_demands)
                )
                .filter(SupplyChainConfig.id == self.config_id)
            )
            config = result.scalar_one_or_none()

            if not config:
                raise ValueError(f"Supply chain config {self.config_id} not found")

            return config

    async def validate_configuration(self) -> Tuple[bool, List[str]]:
        """
        Validate supply chain configuration before planning

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        config = await self.get_config()

        # Check for required entities
        if not config.nodes:
            errors.append("No sites defined in configuration")

        if not config.items:
            errors.append("No products defined in configuration")

        if not config.lanes:
            errors.append("No transportation lanes defined in configuration")

        # Check for manufacturers with BOMs
        manufacturers = [n for n in config.nodes if n.master_type == 'manufacturer']
        for mfg in manufacturers:
            bom = (mfg.attributes or {}).get('bill_of_materials', {})
            if not bom:
                errors.append(f"Manufacturer {mfg.name} has no BOM defined")

        # Check for market demand
        if not config.market_demands:
            errors.append("No demand forecasts defined in configuration")

        is_valid = len(errors) == 0
        return is_valid, errors
