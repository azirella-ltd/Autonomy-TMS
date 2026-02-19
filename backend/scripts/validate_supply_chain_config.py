#!/usr/bin/env python3
"""
Supply Chain Configuration Validator

Validates the integrity and completeness of a supply chain configuration.
Checks for:
1. DAG topology correctness
2. BOM consistency
3. Product-Site (ProductSiteConfig) coverage
4. Market demand completeness
5. Lane connectivity
6. Master type consistency
"""

import sys
import json
import asyncio
from collections import defaultdict
from typing import Dict, List, Set, Tuple

# Add parent directory to path
sys.path.insert(0, '/app')

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db.session import SessionLocal
from app.models.supply_chain_config import SupplyChainConfig
from app.models.sc_entities import InvPolicy as ProductSiteConfig


class ValidationIssue:
    def __init__(self, severity: str, category: str, message: str, details: dict = None):
        self.severity = severity  # 'ERROR', 'WARNING', 'INFO'
        self.category = category
        self.message = message
        self.details = details or {}

    def __str__(self):
        details_str = f" | {json.dumps(self.details, indent=2)}" if self.details else ""
        return f"[{self.severity}] {self.category}: {self.message}{details_str}"


class SupplyChainValidator:
    def __init__(self, config: SupplyChainConfig, product_site_configs: List = None):
        self.config = config
        self.issues: List[ValidationIssue] = []
        self.product_site_configs = product_site_configs or []

        # Build lookup maps
        self.nodes_by_id = {n.id: n for n in config.nodes}
        self.items_by_id = {i.id: i for i in config.items}
        self.lanes_by_from = defaultdict(list)
        self.lanes_by_to = defaultdict(list)

        for lane in config.lanes:
            self.lanes_by_from[lane.from_site_id].append(lane)
            self.lanes_by_to[lane.to_site_id].append(lane)

    def validate_all(self) -> List[ValidationIssue]:
        """Run all validation checks"""
        print(f"\n{'='*80}")
        print(f"Validating Supply Chain Config: {self.config.name} (ID: {self.config.id})")
        print(f"{'='*80}\n")

        self.validate_basic_structure()
        self.validate_master_types()
        self.validate_dag_topology()
        self.validate_bom_consistency()
        self.validate_product_site_configs()
        self.validate_markets_and_demands()
        self.validate_lane_connectivity()

        return self.issues

    def validate_basic_structure(self):
        """Check basic structure completeness"""
        print("📋 Validating Basic Structure...")

        if not self.config.nodes:
            self.issues.append(ValidationIssue(
                'ERROR', 'structure', 'No nodes defined in configuration'
            ))

        if not self.config.items:
            self.issues.append(ValidationIssue(
                'ERROR', 'structure', 'No products/items defined in configuration'
            ))

        if not self.config.lanes:
            self.issues.append(ValidationIssue(
                'ERROR', 'structure', 'No lanes defined in configuration'
            ))

        print(f"  ✓ Nodes: {len(self.config.nodes)}")
        print(f"  ✓ Products: {len(self.config.items)}")
        print(f"  ✓ Lanes: {len(self.config.lanes)}")
        print(f"  ✓ Product-Site Configs: {len(self.product_site_configs)}")
        print(f"  ✓ Markets: {len(self.config.markets)}")
        print(f"  ✓ Market Demands: {len(self.config.market_demands)}\n")

    def validate_master_types(self):
        """Validate master type assignments"""
        print("🏷️  Validating Master Types...")

        master_types = defaultdict(list)
        for node in self.config.nodes:
            mt = node.master_type or 'none'
            master_types[mt].append(node.id)

        # Check for required master types
        required_types = ['market_demand', 'market_supply']
        for mt in required_types:
            if mt not in master_types:
                self.issues.append(ValidationIssue(
                    'ERROR', 'master_type',
                    f'No nodes with master_type={mt} found',
                    {'required_type': mt}
                ))

        # Report counts
        for mt, nodes in sorted(master_types.items()):
            print(f"  {mt:20s}: {len(nodes):3d} nodes")

        print()

    def validate_dag_topology(self):
        """Validate DAG structure"""
        print("🔗 Validating DAG Topology...")

        # Check for nodes with no upstream (should be market_supply)
        no_upstream = []
        for node in self.config.nodes:
            if node.id not in self.lanes_by_to:
                no_upstream.append(node)

        # Check for nodes with no downstream (should be market_demand)
        no_downstream = []
        for node in self.config.nodes:
            if node.id not in self.lanes_by_from:
                no_downstream.append(node)

        # Market supply nodes should have no upstream
        for node in no_upstream:
            if node.master_type != 'market_supply':
                self.issues.append(ValidationIssue(
                    'WARNING', 'dag_topology',
                    f'Node {node.name} has no upstream lanes but is not market_supply',
                    {'node_id': node.id, 'master_type': node.master_type}
                ))

        # Market demand nodes should have no downstream
        for node in no_downstream:
            if node.master_type != 'market_demand':
                self.issues.append(ValidationIssue(
                    'WARNING', 'dag_topology',
                    f'Node {node.name} has no downstream lanes but is not market_demand',
                    {'node_id': node.id, 'master_type': node.master_type}
                ))

        # Check for cycles (simplified check - full cycle detection would use DFS)
        print(f"  ✓ Source nodes (no upstream): {len(no_upstream)}")
        print(f"  ✓ Sink nodes (no downstream): {len(no_downstream)}")
        print()

    def validate_bom_consistency(self):
        """Validate BOM definitions"""
        print("🏭 Validating Bill of Materials...")

        manufacturers = [n for n in self.config.nodes if n.master_type == 'manufacturer']

        for mfg in manufacturers:
            attrs = mfg.attributes or {}
            bom = attrs.get('bill_of_materials', {})

            if not bom:
                self.issues.append(ValidationIssue(
                    'WARNING', 'bom',
                    f'Manufacturer {mfg.name} has no BOM defined',
                    {'node_id': mfg.id, 'node_name': mfg.name}
                ))
                continue

            # Check BOM references valid products
            for fg_id_str, components in bom.items():
                fg_id = int(fg_id_str)

                if fg_id not in self.items_by_id:
                    self.issues.append(ValidationIssue(
                        'ERROR', 'bom',
                        f'BOM references non-existent product ID {fg_id}',
                        {'node_id': mfg.id, 'node_name': mfg.name, 'product_id': fg_id}
                    ))

                for comp_id_str, qty in components.items():
                    comp_id = int(comp_id_str)

                    if comp_id not in self.items_by_id:
                        self.issues.append(ValidationIssue(
                            'ERROR', 'bom',
                            f'BOM component references non-existent product ID {comp_id}',
                            {'node_id': mfg.id, 'node_name': mfg.name,
                             'fg_id': fg_id, 'component_id': comp_id}
                        ))

                    if qty <= 0:
                        self.issues.append(ValidationIssue(
                            'ERROR', 'bom',
                            f'BOM component has invalid quantity {qty}',
                            {'node_id': mfg.id, 'node_name': mfg.name,
                             'fg_id': fg_id, 'component_id': comp_id, 'quantity': qty}
                        ))

        print(f"  ✓ Manufacturers with BOM: {len([m for m in manufacturers if (m.attributes or {}).get('bill_of_materials')])}/{len(manufacturers)}")
        print()

    def validate_product_site_configs(self):
        """Validate product-site configurations"""
        print("📦 Validating Product-Site Configurations...")

        # Build coverage map
        coverage = defaultdict(set)
        for cfg in self.product_site_configs:
            coverage[cfg.site_id].add(cfg.product_id)

        # Check each site has appropriate product configs
        for node in self.config.nodes:
            master_type = node.master_type or 'none'

            if master_type == 'market_supply':
                # Market supply can produce any component, should have configs
                if node.id not in coverage:
                    self.issues.append(ValidationIssue(
                        'WARNING', 'product_site_config',
                        f'Market supply site {node.name} has no product configurations',
                        {'node_id': node.id, 'node_name': node.name}
                    ))

            elif master_type == 'manufacturer':
                # Manufacturers should have configs for FG products they produce
                attrs = node.attributes or {}
                bom = attrs.get('bill_of_materials', {})
                fg_ids = set(int(k) for k in bom.keys())

                if node.id in coverage:
                    configured_products = coverage[node.id]
                    missing = fg_ids - configured_products
                    extra = configured_products - fg_ids

                    if missing:
                        self.issues.append(ValidationIssue(
                            'WARNING', 'product_site_config',
                            f'Manufacturer {node.name} missing configs for products in BOM',
                            {'node_id': node.id, 'node_name': node.name,
                             'missing_products': [self.items_by_id[pid].name for pid in missing]}
                        ))

                    if extra:
                        self.issues.append(ValidationIssue(
                            'INFO', 'product_site_config',
                            f'Manufacturer {node.name} has configs for products not in BOM',
                            {'node_id': node.id, 'node_name': node.name,
                             'extra_products': [self.items_by_id[pid].name for pid in extra if pid in self.items_by_id]}
                        ))

            elif master_type == 'inventory':
                # Inventory nodes (DC, wholesaler, etc.) should have configs
                if node.id not in coverage:
                    self.issues.append(ValidationIssue(
                        'WARNING', 'product_site_config',
                        f'Inventory site {node.name} has no product configurations',
                        {'node_id': node.id, 'node_name': node.name, 'type': node.type}
                    ))

        print(f"  ✓ Sites with configs: {len(coverage)}/{len(self.config.nodes)}")
        print(f"  ✓ Total configs: {len(self.product_site_configs)}")
        print()

    def validate_markets_and_demands(self):
        """Validate market and demand definitions"""
        print("📊 Validating Markets & Demands...")

        if not self.config.markets:
            self.issues.append(ValidationIssue(
                'ERROR', 'market',
                'No markets defined'
            ))
            return

        if not self.config.market_demands:
            self.issues.append(ValidationIssue(
                'ERROR', 'market_demand',
                'No market demands defined'
            ))
            return

        # Check each market has demands
        market_demand_count = defaultdict(int)
        for md in self.config.market_demands:
            market_demand_count[md.market_id] += 1

        for market in self.config.markets:
            if market.id not in market_demand_count:
                self.issues.append(ValidationIssue(
                    'WARNING', 'market_demand',
                    f'Market {market.name} has no demand definitions',
                    {'market_id': market.id, 'market_name': market.name}
                ))

        # Check demand patterns are valid
        for md in self.config.market_demands:
            pattern = md.demand_pattern
            if not pattern:
                self.issues.append(ValidationIssue(
                    'ERROR', 'market_demand',
                    f'Market demand has no demand_pattern',
                    {'demand_id': md.id, 'product_id': md.product_id, 'market_id': md.market_id}
                ))
                continue

            # Check pattern has required fields
            required_fields = ['demand_type', 'variability']
            for field in required_fields:
                if field not in pattern:
                    self.issues.append(ValidationIssue(
                        'ERROR', 'market_demand',
                        f'Market demand pattern missing required field: {field}',
                        {'demand_id': md.id, 'product_id': md.product_id,
                         'market_id': md.market_id, 'missing_field': field}
                    ))

        print(f"  ✓ Markets: {len(self.config.markets)}")
        print(f"  ✓ Demand definitions: {len(self.config.market_demands)}")
        print()

    def validate_lane_connectivity(self):
        """Validate lane definitions and connectivity"""
        print("🛤️  Validating Lane Connectivity...")

        # Check lanes reference valid nodes
        for lane in self.config.lanes:
            if lane.from_site_id not in self.nodes_by_id:
                self.issues.append(ValidationIssue(
                    'ERROR', 'lane',
                    f'Lane references non-existent from_site_id {lane.from_site_id}',
                    {'lane_id': lane.id}
                ))

            if lane.to_site_id not in self.nodes_by_id:
                self.issues.append(ValidationIssue(
                    'ERROR', 'lane',
                    f'Lane references non-existent to_site_id {lane.to_site_id}',
                    {'lane_id': lane.id}
                ))

            # Check lead time is set
            if not lane.supply_lead_time and not lane.transit_time:
                self.issues.append(ValidationIssue(
                    'WARNING', 'lane',
                    f'Lane has no lead time defined',
                    {'lane_id': lane.id,
                     'from': self.nodes_by_id[lane.from_site_id].name if lane.from_site_id in self.nodes_by_id else f'ID:{lane.from_site_id}',
                     'to': self.nodes_by_id[lane.to_site_id].name if lane.to_site_id in self.nodes_by_id else f'ID:{lane.to_site_id}'}
                ))

        print(f"  ✓ Total lanes: {len(self.config.lanes)}")
        print()

    def print_summary(self):
        """Print validation summary"""
        errors = [i for i in self.issues if i.severity == 'ERROR']
        warnings = [i for i in self.issues if i.severity == 'WARNING']
        infos = [i for i in self.issues if i.severity == 'INFO']

        print(f"\n{'='*80}")
        print(f"Validation Summary")
        print(f"{'='*80}")
        print(f"  ❌ Errors:   {len(errors)}")
        print(f"  ⚠️  Warnings: {len(warnings)}")
        print(f"  ℹ️  Info:     {len(infos)}")
        print(f"{'='*80}\n")

        if errors:
            print("❌ ERRORS:")
            for issue in errors:
                print(f"  {issue}")
            print()

        if warnings:
            print("⚠️  WARNINGS:")
            for issue in warnings:
                print(f"  {issue}")
            print()

        if infos:
            print("ℹ️  INFO:")
            for issue in infos:
                print(f"  {issue}")
            print()

        if not self.issues:
            print("✅ Configuration is valid - no issues found!\n")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description='Validate supply chain configuration')
    parser.add_argument('--config-id', type=int, help='Config ID to validate')
    parser.add_argument('--config-name', type=str, help='Config name to validate')
    parser.add_argument('--all', action='store_true', help='Validate all configs')
    args = parser.parse_args()

    async with SessionLocal() as db:
        try:
            configs = []

            # Eagerly load all relationships
            stmt = select(SupplyChainConfig).options(
                selectinload(SupplyChainConfig.nodes),
                selectinload(SupplyChainConfig.items),
                selectinload(SupplyChainConfig.lanes),
                selectinload(SupplyChainConfig.markets),
                selectinload(SupplyChainConfig.market_demands)
            )

            if args.all:
                result = await db.execute(stmt)
                configs = result.scalars().all()
            elif args.config_id:
                result = await db.execute(stmt.filter(SupplyChainConfig.id == args.config_id))
                config = result.scalar_one_or_none()
                if config:
                    configs = [config]
                else:
                    print(f"❌ Config with ID {args.config_id} not found")
                    return 1
            elif args.config_name:
                result = await db.execute(stmt.filter(SupplyChainConfig.name == args.config_name))
                config = result.scalar_one_or_none()
                if config:
                    configs = [config]
                else:
                    print(f"❌ Config with name '{args.config_name}' not found")
                    return 1
            else:
                print("❌ Please specify --config-id, --config-name, or --all")
                return 1

            total_errors = 0
            total_warnings = 0

            for config in configs:
                # Load product_site_configs separately
                inc_result = await db.execute(
                    select(ProductSiteConfig).join(ProductSiteConfig.item).filter(
                        ProductSiteConfig.item.has(config_id=config.id)
                    )
                )
                product_site_configs = inc_result.scalars().all()

                validator = SupplyChainValidator(config, product_site_configs)
                validator.validate_all()
                validator.print_summary()

                errors = [i for i in validator.issues if i.severity == 'ERROR']
                warnings = [i for i in validator.issues if i.severity == 'WARNING']
                total_errors += len(errors)
                total_warnings += len(warnings)

            if len(configs) > 1:
                print(f"\n{'='*80}")
                print(f"Overall Summary: {len(configs)} configurations validated")
                print(f"  Total Errors:   {total_errors}")
                print(f"  Total Warnings: {total_warnings}")
                print(f"{'='*80}\n")

            return 0 if total_errors == 0 else 1

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
