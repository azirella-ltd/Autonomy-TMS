#!/usr/bin/env python3
"""
Fix Complex SC Product-Site Assignments

This script corrects the product-site relationships in Complex_SC to ensure proper material flow:
- Components (consumed by plants) should only appear in suppliers and plants
- Finished goods (produced by plants) should only appear in plants, DCs, and markets
"""

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))

from app.core.config import settings
from app.models import Tenant
from app.models.supply_chain_config import (
    Item,
    ProductSiteConfig,
    Node,
    NodeType,
    SupplyChainConfig,
)
from sc_product_flow_validator import (
    classify_products_from_bom,
    classify_nodes_by_role,
    validate_and_fix_product_site_assignments,
    print_validation_report,
)


def fix_complex_sc_configuration(session: Session, config: SupplyChainConfig, dry_run: bool = False) -> None:
    """
    Fix Complex SC configuration by:
    1. Identifying components vs. finished goods from BOMs
    2. Removing invalid product-site relationships
    3. Adding missing product-site relationships

    Args:
        session: Database session
        config: Supply chain configuration to fix
        dry_run: If True, only report issues without fixing
    """
    print(f"\n{'='*80}")
    print(f"Fixing Complex SC Product-Site Assignments: {config.name} (ID: {config.id})")
    print(f"Mode: {'DRY RUN' if dry_run else 'FIXING'}")
    print(f"{'='*80}\n")

    # Step 1: Classify products based on BOM
    product_class = classify_products_from_bom(session, config)
    node_class = classify_nodes_by_role(session, config, product_class)

    print(f"Product Classification:")
    print(f"  Components: {len(product_class.components)}")
    for comp_id in sorted(product_class.components):
        name = product_class.component_names.get(comp_id, f"Item-{comp_id}")
        print(f"    - {name} (ID: {comp_id})")

    print(f"\n  Finished Goods: {len(product_class.finished_goods)}")
    for fg_id in sorted(product_class.finished_goods):
        name = product_class.fg_names.get(fg_id, f"Item-{fg_id}")
        print(f"    - {name} (ID: {fg_id})")

    if not product_class.finished_goods:
        print("\n[error] No BOMs found! Cannot distinguish components from finished goods.")
        print("        Complex SC requires manufacturer nodes with bill_of_materials in their attributes.")
        return

    # Step 2: Get all existing ProductSiteConfig entries
    existing_configs = (
        session.query(ProductSiteConfig)
        .join(Node, ProductSiteConfig.site_id == Node.id)
        .filter(Node.config_id == config.id)
        .all()
    )

    print(f"\nExisting ProductSiteConfig entries: {len(existing_configs)}")

    # Step 3: Identify invalid entries
    configs_to_delete = []
    issues = []

    for inc in existing_configs:
        node_id = inc.site_id
        product_id = inc.product_id

        # Get node details
        node = session.query(Node).filter(Node.id == node_id).first()
        if not node:
            continue

        is_component = product_id in product_class.components
        is_fg = product_id in product_class.finished_goods

        should_exist = False
        reason = ""

        product_name = product_class.component_names.get(product_id) or product_class.fg_names.get(product_id, f"Item-{product_id}")

        # Rule 1: Market Supply nodes (Tier 2) - No products (they're just sources)
        if node_id in node_class.market_supply_nodes:
            should_exist = False
            reason = f"Market Supply '{node.name}' should not have ProductSiteConfig for {product_name}"

        # Rule 2: Tier 1 Suppliers - COMPONENTS only
        elif node_id in node_class.tier1_suppliers:
            if is_component:
                should_exist = True
            else:
                reason = f"Supplier '{node.name}' should not have FG {product_name}"

        # Rule 3: Manufacturers - FG they produce + COMPONENTS they consume (per BOM)
        elif node_id in node_class.manufacturers:
            details = node_class.manufacturer_details.get(node_id, {})
            fg_produced = details.get("fg_produced", set())
            components_consumed = details.get("components_consumed", set())

            if is_fg and product_id in fg_produced:
                should_exist = True
            elif is_component and product_id in components_consumed:
                should_exist = True
            elif is_fg:
                reason = f"Manufacturer '{node.name}' does not produce FG {product_name}"
            else:
                reason = f"Manufacturer '{node.name}' does not consume component {product_name}"

        # Rule 4: Distributors (DCs) - FG only
        elif node_id in node_class.distributors:
            if is_fg:
                should_exist = True
            else:
                reason = f"DC '{node.name}' should not have component {product_name}"

        # Rule 5: Market Demand nodes - should use MarketDemand, not ProductSiteConfig
        elif node_id in node_class.market_demand_nodes:
            should_exist = False
            reason = f"Demand node '{node.name}' should use MarketDemand, not ProductSiteConfig"

        if not should_exist:
            issue = {
                "node_name": node.name,
                "node_type": str(node.type),
                "product_name": product_name,
                "product_id": product_id,
                "reason": reason
            }
            issues.append(issue)
            configs_to_delete.append(inc)

    print(f"\nIssues Found: {len(issues)}")
    for idx, issue in enumerate(issues, 1):
        print(f"  {idx}. {issue['node_name']} ({issue['node_type']}) + {issue['product_name']}")
        print(f"      → {issue['reason']}")

    # Step 4: Check for missing manufacturer configurations
    missing_configs = []
    for node_id, details in node_class.manufacturer_details.items():
        fg_produced = details.get("fg_produced", set())
        components_consumed = details.get("components_consumed", set())
        required_products = fg_produced | components_consumed

        existing_products = {
            inc.product_id for inc in existing_configs
            if inc.site_id == node_id
        }

        missing_products = required_products - existing_products
        if missing_products:
            missing_configs.append({
                "node_id": node_id,
                "node_name": details.get("name"),
                "missing_products": list(missing_products)
            })

    if missing_configs:
        print(f"\nMissing Manufacturer Configurations: {len(missing_configs)}")
        for cfg in missing_configs:
            print(f"  - {cfg['node_name']}: {len(cfg['missing_products'])} missing products")

    # Step 5: Apply fixes
    if not dry_run:
        print(f"\nApplying Fixes...")

        # Delete invalid configurations
        deleted_count = 0
        for inc in configs_to_delete:
            session.delete(inc)
            deleted_count += 1

        session.flush()

        print(f"  ✓ Deleted {deleted_count} invalid ProductSiteConfig entries")

        # Note: We don't auto-create missing configs because we need proper range values
        # The create_regional_sc_config script should be updated to avoid creating them in the first place

        session.commit()
        print(f"\n✅ Fixes applied successfully!")

    else:
        print(f"\n[DRY RUN] Would delete {len(configs_to_delete)} invalid ProductSiteConfig entries")

    print(f"\n{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(description="Fix Complex SC product-site assignments")
    parser.add_argument("--config-name", default="Complex_SC", help="Supply chain configuration name")
    parser.add_argument("--dry-run", action="store_true", help="Report issues without fixing")
    parser.add_argument("--validate-only", action="store_true", help="Run validation report only")
    args = parser.parse_args()

    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as session:
        config = (
            session.query(SupplyChainConfig)
            .filter(SupplyChainConfig.name == args.config_name)
            .first()
        )

        if not config:
            print(f"[error] Supply chain configuration '{args.config_name}' not found.")
            sys.exit(1)

        if args.validate_only:
            # Run validation and print report
            report = validate_and_fix_product_site_assignments(session, config, dry_run=True)
            print_validation_report(report)
        else:
            # Run the fix
            fix_complex_sc_configuration(session, config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
