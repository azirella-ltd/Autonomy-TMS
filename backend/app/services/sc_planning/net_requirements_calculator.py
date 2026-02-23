"""
Net Requirements Calculator - Step 3 of SC Planning Process

Calculates net requirements and generates supply plans with BOM explosion.

Key Features:
1. Time-phased inventory projection
2. Multi-level BOM explosion
3. Sourcing rule processing (transfer/buy/manufacture)
4. Multi-sourcing with priority and ratio allocation
5. Lead time offsetting
6. Supply plan generation (PO/TO/MO requests)

Reference: https://docs.[removed]
"""

from datetime import date, timedelta
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.sc_entities import (
    SupplyPlan,
    SourcingRules,
    ProductBom,
    ProductionProcess,
    InvLevel,
    SupplyPlanningParameters,
    Reservation
)
from app.models.supplier import VendorLeadTime
from app.models.supply_chain_config import Node
from app.models.sc_entities import Product


class NetRequirementsCalculator:
    """
    Step 3: Net Requirements Calculation with BOM Explosion

    Performs time-phased netting and generates supply plans based on
    sourcing rules. Includes multi-level BOM explosion for manufactured items.
    """

    def __init__(self, config_id: int, group_id: int, planning_horizon: int):
        self.config_id = config_id
        self.group_id = group_id
        self.planning_horizon = planning_horizon
        self._bom_traversal_depth = 0
        self._max_bom_depth = 10  # Prevent infinite loops
        self._visited_boms: Set[Tuple[str, str]] = set()  # For cycle detection

    async def calculate_requirements(
        self,
        net_demand: Dict[Tuple[str, str, date], float],
        target_inventory: Dict[Tuple[str, str], float],
        start_date: date,
        game_id: Optional[int] = None
    ) -> List[SupplyPlan]:
        """
        Calculate net requirements and generate supply plans

        Args:
            net_demand: Net demand by (product_id, site_id, date)
            target_inventory: Target inventory by (product_id, site_id)
            start_date: Planning start date
            game_id: Optional game ID for Beer Game integration

        Returns:
            List of SupplyPlan recommendations (PO/TO/MO requests)
        """
        supply_plans = []

        # Get all product-site combinations
        product_sites = set((prod_id, site_id) for prod_id, site_id, _ in net_demand.keys())

        print(f"  Processing {len(product_sites)} product-site combinations...")

        for product_id, site_id in product_sites:
            # Get current inventory level
            current_inventory = await self.get_current_inventory(
                product_id, site_id, start_date, game_id
            )

            # Get scheduled receipts (inbound orders)
            scheduled_receipts = await self.get_scheduled_receipts(
                product_id, site_id, start_date, game_id
            )

            # Get target inventory
            target = target_inventory.get((product_id, site_id), 0)

            # Time-phased netting
            plans = await self.time_phased_netting(
                product_id, site_id, start_date,
                current_inventory, scheduled_receipts, net_demand,
                target, game_id
            )

            supply_plans.extend(plans)

        print(f"  ✓ Generated {len(supply_plans)} supply plan entries")

        return supply_plans

    async def time_phased_netting(
        self,
        product_id: str,
        site_id: str,
        start_date: date,
        opening_inventory: float,
        scheduled_receipts: Dict[date, float],
        net_demand: Dict[Tuple[str, str, date], float],
        target_inventory: float,
        game_id: Optional[int]
    ) -> List[SupplyPlan]:
        """
        Perform time-phased inventory projection and netting

        Args:
            product_id: Product identifier
            site_id: Site identifier
            start_date: Planning start date
            opening_inventory: Current on-hand inventory
            scheduled_receipts: Scheduled receipts by date
            net_demand: Net demand data
            target_inventory: Target inventory level
            game_id: Optional game ID

        Returns:
            List of SupplyPlan recommendations
        """
        supply_plans = []
        projected_inventory = opening_inventory

        # Project inventory for each period
        for day_offset in range(self.planning_horizon):
            period_date = start_date + timedelta(days=day_offset)

            # Get demand for this period
            period_demand = net_demand.get((product_id, site_id, period_date), 0)

            # Get scheduled receipt for this period
            period_receipt = scheduled_receipts.get(period_date, 0)

            # Project inventory
            projected_inventory = projected_inventory + period_receipt - period_demand

            # Check if replenishment needed
            if projected_inventory < target_inventory:
                net_requirement = target_inventory - projected_inventory

                # Generate supply plan based on sourcing rules
                plan = await self.generate_supply_plan(
                    product_id, site_id, period_date,
                    net_requirement, projected_inventory,
                    target_inventory, game_id
                )

                if plan:
                    supply_plans.append(plan)
                    # Update projected inventory with planned order
                    projected_inventory += plan.planned_order_quantity

        return supply_plans

    async def generate_supply_plan(
        self,
        product_id: str,
        site_id: str,
        plan_date: date,
        net_requirement: float,
        projected_inventory: float,
        target_inventory: float,
        game_id: Optional[int]
    ) -> Optional[SupplyPlan]:
        """
        Generate supply plan based on sourcing rules

        Handles:
        - Priority-based sourcing rule selection
        - Multi-sourcing with ratio allocation
        - Type-specific plan generation (transfer/buy/manufacture)

        Args:
            product_id: Product identifier
            site_id: Site identifier
            plan_date: Planning date
            net_requirement: Net requirement quantity
            projected_inventory: Projected inventory before order
            target_inventory: Target inventory level
            game_id: Optional game ID

        Returns:
            SupplyPlan or None
        """
        # Get sourcing rules for this product-site (with override logic)
        sourcing_rules = await self.get_sourcing_rules(product_id, site_id)

        if not sourcing_rules:
            print(f"      ⚠️  No sourcing rule found for {product_id} @ {site_id}")
            return None

        # Get highest priority rules
        min_priority = min(rule.priority for rule in sourcing_rules)
        top_priority_rules = [r for r in sourcing_rules if r.priority == min_priority]

        # Multi-sourcing allocation
        if len(top_priority_rules) > 1:
            # Allocate by ratio
            print(f"      Multi-sourcing: {len(top_priority_rules)} sources at priority {min_priority}")
            total_ratio = sum(rule.allocation_percent or 1 for rule in top_priority_rules)

            plans = []
            for rule in top_priority_rules:
                rule_ratio = (rule.allocation_percent or 1) / total_ratio
                rule_quantity = net_requirement * rule_ratio

                plan = await self.create_plan_for_sourcing_rule(
                    rule, product_id, site_id, plan_date,
                    rule_quantity, projected_inventory, target_inventory, game_id
                )
                if plan:
                    plans.append(plan)

            return plans[0] if plans else None  # Return first for simplicity

        else:
            # Single source
            rule = top_priority_rules[0]
            return await self.create_plan_for_sourcing_rule(
                rule, product_id, site_id, plan_date,
                net_requirement, projected_inventory, target_inventory, game_id
            )

    async def create_plan_for_sourcing_rule(
        self,
        rule: SourcingRules,
        product_id: str,
        site_id: str,
        plan_date: date,
        order_quantity: float,
        projected_inventory: float,
        target_inventory: float,
        game_id: Optional[int]
    ) -> Optional[SupplyPlan]:
        """
        Create supply plan based on sourcing rule type

        Args:
            rule: Sourcing rule
            product_id: Product identifier
            site_id: Site identifier
            plan_date: Planning date
            order_quantity: Order quantity
            projected_inventory: Projected inventory
            target_inventory: Target inventory
            game_id: Optional game ID

        Returns:
            SupplyPlan
        """
        if rule.sourcing_rule_type == 'manufacture':
            return await self.create_manufacture_plan(
                rule, product_id, site_id, plan_date,
                order_quantity, projected_inventory, target_inventory, game_id
            )

        elif rule.sourcing_rule_type == 'buy':
            return await self.create_buy_plan(
                rule, product_id, site_id, plan_date,
                order_quantity, projected_inventory, target_inventory, game_id
            )

        elif rule.sourcing_rule_type == 'transfer':
            return await self.create_transfer_plan(
                rule, product_id, site_id, plan_date,
                order_quantity, projected_inventory, target_inventory, game_id
            )

        return None

    async def create_manufacture_plan(
        self,
        rule: SourcingRules,
        product_id: str,
        site_id: str,
        plan_date: date,
        order_quantity: float,
        projected_inventory: float,
        target_inventory: float,
        game_id: Optional[int]
    ) -> SupplyPlan:
        """
        Create manufacturing order plan with BOM explosion

        Args:
            rule: Sourcing rule
            product_id: Product identifier
            site_id: Site identifier
            plan_date: Planning date
            order_quantity: Order quantity
            projected_inventory: Projected inventory
            target_inventory: Target inventory
            game_id: Optional game ID

        Returns:
            SupplyPlan for manufacturing order
        """
        async with SessionLocal() as db:
            # Get manufacturing lead time from rule or default
            manufacturing_lead_time = rule.lead_time or 0

            # Lead time offset: plan receipt date, calculate order date
            planned_receipt_date = plan_date
            planned_order_date = plan_date - timedelta(days=manufacturing_lead_time)

            # BOM explosion - generate component requirements
            print(f"      🏭 Manufacturing: {product_id} qty={order_quantity:.1f} @ {site_id}")
            await self.explode_bom(
                product_id, order_quantity, planned_order_date,
                None,  # production_process_id not used in simplified implementation
                site_id, game_id
            )

            # Get planner info
            planner = await self.get_planner(product_id)

            # Create supply plan
            plan = SupplyPlan(
                plan_type='mo_request',
                product_id=product_id,
                destination_site_id=site_id,
                source_site_id=site_id,  # Manufacture at same site
                planned_order_quantity=order_quantity,
                planned_order_date=planned_order_date,
                planned_receipt_date=planned_receipt_date,
                lead_time_days=manufacturing_lead_time,
                config_id=self.config_id,
                game_id=game_id
            )

            db.add(plan)
            await db.commit()
            await db.refresh(plan)

            return plan

    async def explode_bom(
        self,
        product_id: str,
        order_quantity: float,
        planned_start_date: date,
        production_process_id: Optional[str],
        site_id: str,
        game_id: Optional[int]
    ):
        """
        Explode BOM to generate component requirements

        Handles:
        - Multi-level BOM traversal
        - Alternate component groups
        - Scrap percentage
        - Cycle detection

        Args:
            product_id: Finished good product ID
            order_quantity: Production quantity
            planned_start_date: Start date for production
            production_process_id: Production process ID
            site_id: Manufacturing site
            game_id: Optional game ID
        """
        # Cycle detection
        if self._bom_traversal_depth >= self._max_bom_depth:
            print(f"        ⚠️  Max BOM depth reached for {product_id}")
            return

        bom_key = (product_id, production_process_id or 'default')
        if bom_key in self._visited_boms:
            print(f"        ⚠️  Circular BOM detected for {product_id}")
            return

        self._visited_boms.add(bom_key)
        self._bom_traversal_depth += 1

        try:
            async with SessionLocal() as db:
                # Get BOM for this product
                query = select(ProductBom).filter(
                    ProductBom.group_id == self.group_id,
                    ProductBom.config_id == self.config_id,
                    ProductBom.product_id == product_id,
                )

                if production_process_id:
                    query = query.filter(ProductBom.production_process_id == production_process_id)

                result = await db.execute(query)
                bom_entries = result.scalars().all()

                if not bom_entries:
                    print(f"        ℹ️  No BOM found for {product_id}")
                    return

                # Group by alternate group
                alternate_groups = defaultdict(list)
                for entry in bom_entries:
                    alternate_groups[entry.alternate_group or 0].append(entry)

                # For each alternate group, pick highest priority
                for group_id, entries in alternate_groups.items():
                    selected_entry = min(entries, key=lambda e: e.priority or 0)

                    # Calculate component requirement
                    component_requirement = order_quantity * selected_entry.component_quantity

                    # Account for scrap
                    if selected_entry.scrap_percentage:
                        component_requirement *= (1 + selected_entry.scrap_percentage / 100)

                    print(f"        📦 Component: {selected_entry.component_product_id} "
                          f"qty={component_requirement:.1f} (from {product_id})")

                    # Get component site (upstream supplier)
                    component_site = await self.get_component_site(
                        selected_entry.component_product_id, product_id, site_id
                    )

                    # Create demand for component (dependent demand)
                    await self.create_component_reservation(
                        selected_entry.component_product_id,
                        component_site,
                        planned_start_date,
                        component_requirement,
                        game_id
                    )

                    # Recursive BOM explosion for multi-level BOMs
                    component_sourcing = await self.get_sourcing_rules(
                        selected_entry.component_product_id, component_site
                    )
                    if component_sourcing and component_sourcing[0].sourcing_rule_type == 'manufacture':
                        await self.explode_bom(
                            selected_entry.component_product_id,
                            component_requirement,
                            planned_start_date,
                            component_sourcing[0].production_process_id,
                            component_site,
                            game_id
                        )

        finally:
            self._bom_traversal_depth -= 1
            self._visited_boms.discard(bom_key)

    async def create_component_reservation(
        self,
        component_product_id: str,
        component_site_id: str,
        required_date: date,
        required_quantity: float,
        game_id: Optional[int]
    ):
        """
        Create dependent demand reservation for component

        Args:
            component_product_id: Component product ID
            component_site_id: Component site ID
            required_date: Date component is needed
            required_quantity: Quantity required
            game_id: Optional game ID
        """
        async with SessionLocal() as db:
            reservation = Reservation(
                company_id=await self.get_company_id(component_site_id),
                product_id=component_product_id,
                site_id=component_site_id,
                reservation_date=required_date,
                reserved_quantity=required_quantity,
                reservation_type='production_order',
                config_id=self.config_id,
                game_id=game_id
            )
            db.add(reservation)
            await db.commit()

    async def create_buy_plan(
        self,
        rule: SourcingRules,
        product_id: str,
        site_id: str,
        plan_date: date,
        order_quantity: float,
        projected_inventory: float,
        target_inventory: float,
        game_id: Optional[int]
    ) -> SupplyPlan:
        """Create purchase order plan"""
        async with SessionLocal() as db:
            # Get lead time from vendor (SC best practice)
            # Fallback to sourcing rule lead_time if vendor lead time not found
            lead_time = rule.lead_time or 1  # Default fallback
            if rule.tpartner_id:
                vendor_lead_time = await self.get_vendor_lead_time(product_id, site_id, rule.tpartner_id)
                if vendor_lead_time:
                    lead_time = vendor_lead_time

            planned_receipt_date = plan_date
            planned_order_date = plan_date - timedelta(days=lead_time)

            planner = await self.get_planner(product_id)

            # Get unit cost from vendor_product table (SC best practice)
            # Fallback to rule.unit_cost if vendor_product not found
            unit_cost = rule.unit_cost  # Default fallback
            if rule.tpartner_id:
                vendor_cost = await self.get_vendor_unit_cost(product_id, rule.tpartner_id)
                if vendor_cost is not None:
                    unit_cost = vendor_cost

            print(f"      🛒 Purchase: {product_id} qty={order_quantity:.1f} cost={unit_cost} LT={lead_time}d")

            plan = SupplyPlan(
                plan_type='po_request',
                product_id=product_id,
                destination_site_id=site_id,
                planned_order_quantity=order_quantity,
                planned_order_date=planned_order_date,
                planned_receipt_date=planned_receipt_date,
                lead_time_days=lead_time,
                unit_cost=unit_cost,
                config_id=self.config_id,
                game_id=game_id
            )

            db.add(plan)
            await db.commit()
            await db.refresh(plan)

            return plan

    async def create_transfer_plan(
        self,
        rule: SourcingRules,
        product_id: str,
        site_id: str,
        plan_date: date,
        order_quantity: float,
        projected_inventory: float,
        target_inventory: float,
        game_id: Optional[int]
    ) -> SupplyPlan:
        """Create transfer order plan"""
        async with SessionLocal() as db:
            # Get transit time from sourcing rule or default to 1 day
            transit_time = rule.lead_time or 1

            planned_receipt_date = plan_date
            planned_order_date = plan_date - timedelta(days=transit_time)

            planner = await self.get_planner(product_id)

            print(f"      🚚 Transfer: {product_id} qty={order_quantity:.1f} "
                  f"from {rule.supplier_site_id} to {site_id}")

            plan = SupplyPlan(
                plan_type='to_request',
                product_id=product_id,
                destination_site_id=site_id,
                source_site_id=rule.supplier_site_id,
                planned_order_quantity=order_quantity,
                planned_order_date=planned_order_date,
                planned_receipt_date=planned_receipt_date,
                lead_time_days=transit_time,
                unit_cost=rule.unit_cost,
                config_id=self.config_id,
                game_id=game_id
            )

            db.add(plan)
            await db.commit()
            await db.refresh(plan)

            return plan

    async def get_sourcing_rules(
        self, product_id: str, site_id: str
    ) -> List[SourcingRules]:
        """
        Get sourcing rules with 3-level hierarchical override logic

        Override priority (highest to lowest):
        1. product_id + site_id (most specific)
        2. product_group_id + site_id (product category level)
        3. company_id + site_id (company-wide default)

        SC Reference: https://docs.[removed]

        Args:
            product_id: Product identifier
            site_id: Site identifier

        Returns:
            List of sourcing rules ordered by priority (empty if none found)
        """
        async with SessionLocal() as db:
            # Get product and site for hierarchy lookup
            product = await db.get(Product, product_id)
            site = await db.get(Node, site_id)

            if not product or not site:
                return []

            # Level 1: product_id + site_id (highest priority - most specific)
            result = await db.execute(
                select(SourcingRules).filter(
                    SourcingRules.group_id == self.group_id,
                    SourcingRules.config_id == self.config_id,
                    SourcingRules.product_id == product_id,
                    SourcingRules.to_site_id == site_id
                ).order_by(SourcingRules.sourcing_priority)
            )
            rules = list(result.scalars().all())
            if rules:
                return rules

            # Level 2: product_group_id + site_id (product category level)
            if product.product_group_id:
                result = await db.execute(
                    select(SourcingRules).filter(
                        SourcingRules.group_id == self.group_id,
                    SourcingRules.config_id == self.config_id,
                        SourcingRules.product_group_id == product.product_group_id,
                        SourcingRules.to_site_id == site_id,
                        SourcingRules.product_id.is_(None)
                    ).order_by(SourcingRules.sourcing_priority)
                )
                rules = list(result.scalars().all())
                if rules:
                    return rules

            # Level 3: company_id + site_id (company-wide default - lowest priority)
            if site.company_id:
                result = await db.execute(
                    select(SourcingRules).filter(
                        SourcingRules.group_id == self.group_id,
                    SourcingRules.config_id == self.config_id,
                        SourcingRules.company_id == site.company_id,
                        SourcingRules.to_site_id == site_id,
                        SourcingRules.product_id.is_(None),
                        SourcingRules.product_group_id.is_(None)
                    ).order_by(SourcingRules.sourcing_priority)
                )
                rules = list(result.scalars().all())
                return rules

            # No sourcing rules found at any level
            return []

    # Helper methods
    async def get_current_inventory(self, product_id: str, site_id: str,
                                    start_date: date, game_id: Optional[int]) -> float:
        """Get current inventory from inv_level table.

        Queries the most recent inventory snapshot for this product-site
        combination on or before start_date.
        """
        from app.models.sc_entities import InvLevel
        from sqlalchemy import select, and_, desc

        filters = [
            InvLevel.product_id == product_id,
            InvLevel.site_id == site_id,
        ]
        # Prefer snapshot on or before start_date
        if hasattr(InvLevel, 'inventory_date'):
            filters.append(InvLevel.inventory_date <= start_date)

        if game_id is not None and hasattr(InvLevel, 'scenario_id'):
            filters.append(InvLevel.scenario_id == game_id)

        if self.group_id is not None:
            filters.append(InvLevel.company_id == str(self.group_id))

        stmt = (
            select(InvLevel)
            .where(and_(*filters))
            .order_by(desc(InvLevel.inventory_date) if hasattr(InvLevel, 'inventory_date') else desc(InvLevel.id))
            .limit(1)
        )

        result = await self.db.execute(stmt)
        inv = result.scalar_one_or_none()

        if inv is None:
            return 0.0

        return float(inv.on_hand_qty or 0.0)

    async def get_scheduled_receipts(self, product_id: str, site_id: str,
                                     start_date: date, game_id: Optional[int]) -> Dict[date, float]:
        """Get scheduled receipts from supply_plan table.

        Returns time-phased dict of {receipt_date: quantity} for confirmed
        or planned receipts (PO/TO/MO) that haven't arrived yet.
        """
        from app.models.sc_entities import SupplyPlan
        from sqlalchemy import select, and_, func
        from collections import defaultdict

        filters = [
            SupplyPlan.product_id == product_id,
            SupplyPlan.site_id == site_id,
            SupplyPlan.planned_receipt_date >= start_date,
        ]

        if game_id is not None and hasattr(SupplyPlan, 'scenario_id'):
            filters.append(SupplyPlan.scenario_id == game_id)

        if self.group_id is not None:
            filters.append(SupplyPlan.company_id == str(self.group_id))

        stmt = (
            select(
                SupplyPlan.planned_receipt_date,
                func.sum(SupplyPlan.planned_order_quantity),
            )
            .where(and_(*filters))
            .group_by(SupplyPlan.planned_receipt_date)
        )

        result = await self.db.execute(stmt)
        receipts: Dict[date, float] = {}
        for row in result.all():
            receipt_date, qty = row
            if receipt_date is not None and qty is not None:
                receipts[receipt_date] = float(qty)

        return receipts

    async def get_component_site(self, component_id: str, parent_id: str,
                                 parent_site_id: str) -> str:
        """Determine which site supplies the component"""
        # For now, return parent site (manufacture at same site)
        return parent_site_id

    async def get_vendor_lead_time(self, product_id: str, site_id: str,
                                   tpartner_id: int) -> int:
        """
        Get vendor lead time with multiple lookup strategies

        Lookup priority (highest to lowest):
        1. vendor_product.lead_time_days (most direct)
        2. vendor_lead_time with 5-level hierarchical lookup:
           a. product_id + site_id + vendor_id (most specific)
           b. product_group_id + site_id + vendor_id
           c. product_id + geo_id + vendor_id
           d. product_group_id + geo_id + vendor_id
           e. company_id + vendor_id (company-wide default)

        SC Reference: https://docs.[removed]

        Args:
            product_id: Item identifier
            site_id: Node identifier
            tpartner_id: Trading partner (vendor) identifier (INT)

        Returns:
            Lead time in days (default 1)
        """
        async with SessionLocal() as db:
            from app.models.supplier import VendorProduct

            # Priority 1: Check vendor_product table (most direct)
            result = await db.execute(
                select(VendorProduct).filter(
                    VendorProduct.config_id == self.config_id,
                    VendorProduct.product_id == int(product_id),
                    VendorProduct.tpartner_id == tpartner_id,
                    VendorProduct.is_active == 'true'
                ).order_by(VendorProduct.id.desc())
            )
            vendor_product = result.scalar_one_or_none()
            if vendor_product and vendor_product.lead_time_days:
                return int(vendor_product.lead_time_days)

            # Priority 2: Check vendor_lead_time with hierarchical lookup
            # Get product and site for hierarchy
            product = await db.get(Product, product_id)
            site = await db.get(Node, site_id)

            if not product or not site:
                return 1

            # Level 1: product_id + site_id + vendor_id (most specific)
            result = await db.execute(
                select(VendorLeadTime).filter(
                    VendorLeadTime.product_id == product_id,
                    VendorLeadTime.site_id == site_id,
                    VendorLeadTime.vendor_id == tpartner_id
                ).order_by(VendorLeadTime.id.desc())
            )
            lead_time = result.scalar_one_or_none()
            if lead_time:
                return int(lead_time.lead_time_days or 1)

            # Level 2: product_group_id + site_id + vendor_id
            if product.product_group_id:
                result = await db.execute(
                    select(VendorLeadTime).filter(
                        VendorLeadTime.product_group_id == product.product_group_id,
                        VendorLeadTime.site_id == site_id,
                        VendorLeadTime.vendor_id == tpartner_id,
                        VendorLeadTime.product_id.is_(None)
                    ).order_by(VendorLeadTime.id.desc())
                )
                lead_time = result.scalar_one_or_none()
                if lead_time:
                    return int(lead_time.lead_time_days or 1)

            # Level 3: product_id + geo_id + vendor_id
            if site.geo_id:
                result = await db.execute(
                    select(VendorLeadTime).filter(
                        VendorLeadTime.product_id == int(product_id),
                        VendorLeadTime.geo_id == str(site.geo_id),
                        VendorLeadTime.vendor_id == tpartner_id,
                        VendorLeadTime.site_id.is_(None)
                    ).order_by(VendorLeadTime.id.desc())
                )
                lead_time = result.scalar_one_or_none()
                if lead_time:
                    return int(lead_time.lead_time_days or 1)

            # Level 4: product_group_id + geo_id + vendor_id
            if product.product_group_id and site.geo_id:
                result = await db.execute(
                    select(VendorLeadTime).filter(
                        VendorLeadTime.product_group_id == str(product.product_group_id),
                        VendorLeadTime.geo_id == str(site.geo_id),
                        VendorLeadTime.vendor_id == tpartner_id,
                        VendorLeadTime.product_id.is_(None),
                        VendorLeadTime.site_id.is_(None)
                    ).order_by(VendorLeadTime.id.desc())
                )
                lead_time = result.scalar_one_or_none()
                if lead_time:
                    return int(lead_time.lead_time_days or 1)

            # Level 5: company_id + vendor_id (company-wide default)
            if site.company_id:
                result = await db.execute(
                    select(VendorLeadTime).filter(
                        VendorLeadTime.company_id == str(site.company_id),
                        VendorLeadTime.vendor_id == tpartner_id,
                        VendorLeadTime.product_id.is_(None),
                        VendorLeadTime.product_group_id.is_(None),
                        VendorLeadTime.site_id.is_(None),
                        VendorLeadTime.geo_id.is_(None)
                    ).order_by(VendorLeadTime.id.desc())
                )
                lead_time = result.scalar_one_or_none()
                if lead_time:
                    return int(lead_time.lead_time_days or 1)

            # No lead time found - default to 1 day
            return 1

    async def get_vendor_unit_cost(self, product_id: str, tpartner_id: int) -> Optional[float]:
        """
        Get unit cost from vendor_product table

        Looks up the unit cost for a specific product-vendor combination.
        Returns the cost from the most recent active vendor_product record.

        Args:
            product_id: Item identifier
            tpartner_id: Trading partner (vendor) ID

        Returns:
            Unit cost or None if not found
        """
        async with SessionLocal() as db:
            from app.models.supplier import VendorProduct

            result = await db.execute(
                select(VendorProduct).filter(
                    VendorProduct.config_id == self.config_id,
                    VendorProduct.product_id == int(product_id),
                    VendorProduct.tpartner_id == tpartner_id,
                    VendorProduct.is_active == 'true'
                ).order_by(VendorProduct.id.desc())
            )
            vendor_product = result.scalar_one_or_none()

            if vendor_product and vendor_product.unit_cost:
                return float(vendor_product.unit_cost)

            return None

    async def get_planner(self, product_id: str) -> Optional[SupplyPlanningParameters]:
        """Get planner assignment"""
        return None

    async def get_company_id(self, site_id: str) -> str:
        """Get company ID for a site"""
        return "DEFAULT_COMPANY"

    async def is_valid_ordering_day(
        self, product_id: str, site_id: str, check_date: date
    ) -> bool:
        """
        Check if a date is a valid ordering day based on sourcing schedule

        Looks up sourcing schedule for the product-site combination.
        If no schedule exists, returns True (continuous review - can order any day).
        If schedule exists, checks if the date matches the schedule criteria.

        Args:
            product_id: Item identifier
            site_id: Node identifier
            check_date: Date to check

        Returns:
            True if orders can be placed on this date, False otherwise
        """
        async with SessionLocal() as db:
            from app.models.sc_planning import SourcingSchedule, SourcingScheduleDetails

            # Get product and site for hierarchy
            product = await db.get(Product, product_id)
            site = await db.get(Node, site_id)

            if not product or not site:
                return True  # Default to allowing orders if entities not found

            # Look up sourcing schedule for this site
            result = await db.execute(
                select(SourcingSchedule).filter(
                    SourcingSchedule.config_id == self.config_id,
                    SourcingSchedule.to_site_id == site_id,
                    SourcingSchedule.is_active == 'true'
                ).order_by(SourcingSchedule.id.desc())
            )
            schedule = result.scalar_one_or_none()

            if not schedule:
                # No schedule = continuous review (can order any day)
                return True

            # Get schedule details with hierarchical lookup
            # Priority: product_id > product_group_id > company_id
            result = await db.execute(
                select(SourcingScheduleDetails).filter(
                    SourcingScheduleDetails.sourcing_schedule_id == schedule.id,
                    SourcingScheduleDetails.product_id == int(product_id),
                    SourcingScheduleDetails.is_active == 'true'
                ).order_by(SourcingScheduleDetails.id.desc())
            )
            details = result.scalar_one_or_none()

            if not details and product.product_group_id:
                # Try product_group_id level
                result = await db.execute(
                    select(SourcingScheduleDetails).filter(
                        SourcingScheduleDetails.sourcing_schedule_id == schedule.id,
                        SourcingScheduleDetails.product_group_id == str(product.product_group_id),
                        SourcingScheduleDetails.product_id.is_(None),
                        SourcingScheduleDetails.is_active == 'true'
                    ).order_by(SourcingScheduleDetails.id.desc())
                )
                details = result.scalar_one_or_none()

            if not details and site.company_id:
                # Try company_id level (fallback)
                result = await db.execute(
                    select(SourcingScheduleDetails).filter(
                        SourcingScheduleDetails.sourcing_schedule_id == schedule.id,
                        SourcingScheduleDetails.company_id == str(site.company_id),
                        SourcingScheduleDetails.product_id.is_(None),
                        SourcingScheduleDetails.product_group_id.is_(None),
                        SourcingScheduleDetails.is_active == 'true'
                    ).order_by(SourcingScheduleDetails.id.desc())
                )
                details = result.scalar_one_or_none()

            if not details:
                # Schedule exists but no details = no valid ordering days
                return False

            # Check if check_date matches the schedule criteria
            if details.schedule_date:
                # Specific date match
                return check_date == details.schedule_date

            if details.day_of_week is not None:
                # Day of week match (0=Sunday, 1=Monday, ..., 6=Saturday)
                if check_date.weekday() != ((details.day_of_week - 1) % 7):
                    # Convert: Python weekday() returns 0=Monday, need to shift for 0=Sunday
                    return False

                # If week_of_month specified, check that too
                if details.week_of_month is not None:
                    week_num = (check_date.day - 1) // 7 + 1
                    return week_num == details.week_of_month

                return True

            # No criteria specified - allow ordering
            return True
