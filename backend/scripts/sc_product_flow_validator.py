#!/usr/bin/env python3
"""
Supply Chain Product Flow Validator

Validates and enforces correct product-site relationships based on material flow logic:
- Components flow from suppliers through plants (where they're transformed into FG)
- Finished goods flow from plants through DCs to demand regions
- Components should NOT appear downstream of plants
- Finished goods should NOT appear upstream of plants

This ensures proper end-to-end material flow modeling.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.supply_chain_config import (
    Item,
    ProductSiteConfig,
    Lane,
    MarketDemand,
    Node,
    NodeType,
    SupplyChainConfig,
)


@dataclass
class ProductClassification:
    """Classification of products into components and finished goods based on BOM analysis."""

    components: Set[int]  # Item IDs that are components (inputs to manufacturing)
    finished_goods: Set[int]  # Item IDs that are finished goods (outputs from manufacturing)
    component_names: Dict[int, str]  # Component ID -> name mapping
    fg_names: Dict[int, str]  # FG ID -> name mapping


@dataclass
class NodeClassification:
    """Classification of nodes into upstream (component suppliers) and downstream (FG handlers)."""

    market_supply_nodes: Set[int]  # Tier 2 component suppliers (Market Supply nodes)
    tier1_suppliers: Set[int]  # Tier 1 component suppliers
    manufacturers: Set[int]  # Plants that transform components into FG
    distributors: Set[int]  # DCs that handle finished goods
    market_demand_nodes: Set[int]  # Demand regions

    manufacturer_details: Dict[int, Dict[str, any]]  # node_id -> {name, fg_produced, components_consumed}


def classify_products_from_bom(
    session: Session,
    config: SupplyChainConfig
) -> ProductClassification:
    """
    Analyze BOM (Bill of Materials) to classify items as components or finished goods.

    Logic:
    - Finished Goods: Items that appear as OUTPUT in a BOM (manufactured)
    - Components: Items that appear as INPUT in a BOM (consumed during manufacturing)

    Args:
        session: Database session
        config: Supply chain configuration

    Returns:
        ProductClassification with components and finished goods identified
    """
    all_items = session.query(Item).filter(Item.config_id == config.id).all()
    item_id_to_name = {item.id: item.name for item in all_items}

    components: Set[int] = set()
    finished_goods: Set[int] = set()

    # Get all manufacturer/plant nodes (supports custom types like "plant")
    all_nodes = session.query(Node).filter(Node.config_id == config.id).all()
    manufacturers = [
        node for node in all_nodes
        if str(node.type).lower() in {"manufacturer", "plant"}
    ]

    for manufacturer in manufacturers:
        attrs = manufacturer.attributes or {}
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except Exception:
                attrs = {}

        bom = attrs.get("bill_of_materials", {})

        # bom structure: {fg_item_id: {component_item_id: quantity, ...}, ...}
        for fg_item_id_str, component_map in bom.items():
            try:
                fg_item_id = int(fg_item_id_str)
                finished_goods.add(fg_item_id)

                # Add all components consumed in this BOM
                for component_id_str in component_map.keys():
                    try:
                        component_id = int(component_id_str)
                        components.add(component_id)
                    except (ValueError, TypeError):
                        pass

            except (ValueError, TypeError):
                pass

    # If no BOM found, fall back to naming convention
    # Items named like "Component-X", "Part-X", "Raw-X" are components
    # Items named like "FG-X", "Product-X" are finished goods
    if not finished_goods and not components:
        for item in all_items:
            name_lower = item.name.lower()
            if any(prefix in name_lower for prefix in ["component", "part", "raw", "material"]):
                components.add(item.id)
            elif any(prefix in name_lower for prefix in ["fg-", "product", "finished"]):
                finished_goods.add(item.id)

    component_names = {item_id: item_id_to_name.get(item_id, f"Item-{item_id}") for item_id in components}
    fg_names = {item_id: item_id_to_name.get(item_id, f"Item-{item_id}") for item_id in finished_goods}

    return ProductClassification(
        components=components,
        finished_goods=finished_goods,
        component_names=component_names,
        fg_names=fg_names
    )


def classify_nodes_by_role(
    session: Session,
    config: SupplyChainConfig,
    product_classification: ProductClassification
) -> NodeClassification:
    """
    Classify nodes into upstream (component handling) and downstream (FG handling).

    Args:
        session: Database session
        config: Supply chain configuration
        product_classification: Product classification result

    Returns:
        NodeClassification with nodes categorized by role
    """
    market_supply_nodes: Set[int] = set()
    tier1_suppliers: Set[int] = set()
    manufacturers: Set[int] = set()
    distributors: Set[int] = set()
    market_demand_nodes: Set[int] = set()
    manufacturer_details: Dict[int, Dict[str, any]] = {}

    all_nodes = session.query(Node).filter(Node.config_id == config.id).all()

    for node in all_nodes:
        # Get node type as string (supports custom types like "plant", "component_supplier")
        node_type_str = str(node.type).lower() if node.type else ""

        # Market Supply nodes (Tier 2 component sources)
        if node_type_str in {"vendor", "market supply"}:
            market_supply_nodes.add(node.id)

        # Market Demand nodes
        elif node_type_str in {"customer", "market demand"}:
            market_demand_nodes.add(node.id)

        # Manufacturer/Plant nodes
        elif node_type_str in {"manufacturer", "plant"}:
            manufacturers.add(node.id)

            # Extract FG produced and components consumed from BOM
            attrs = node.attributes or {}
            if isinstance(attrs, str):
                try:
                    attrs = json.loads(attrs)
                except Exception:
                    attrs = {}

            bom = attrs.get("bill_of_materials", {})
            fg_produced = set()
            components_consumed = set()

            for fg_id_str, component_map in bom.items():
                try:
                    fg_id = int(fg_id_str)
                    fg_produced.add(fg_id)
                    for comp_id_str in component_map.keys():
                        try:
                            comp_id = int(comp_id_str)
                            components_consumed.add(comp_id)
                        except (ValueError, TypeError):
                            pass
                except (ValueError, TypeError):
                    pass

            manufacturer_details[node.id] = {
                "name": node.name,
                "fg_produced": fg_produced,
                "components_consumed": components_consumed
            }

        # Distributor nodes (DCs, Wholesalers, Retailers)
        elif node_type_str in {"distributor", "wholesaler", "retailer"}:
            distributors.add(node.id)

        # Supplier nodes (Tier 1 component suppliers)
        elif node_type_str in {"supplier", "component_supplier", "component supplier"}:
            tier1_suppliers.add(node.id)

    return NodeClassification(
        market_supply_nodes=market_supply_nodes,
        tier1_suppliers=tier1_suppliers,
        manufacturers=manufacturers,
        distributors=distributors,
        market_demand_nodes=market_demand_nodes,
        manufacturer_details=manufacturer_details
    )


def validate_and_fix_product_site_assignments(
    session: Session,
    config: SupplyChainConfig,
    dry_run: bool = False
) -> Dict[str, any]:
    """
    Validate and fix ProductSiteConfig entries to ensure proper material flow.

    Correct logic:
    1. Market Supply nodes (Tier 2): COMPONENTS only
    2. Suppliers (Tier 1): COMPONENTS only
    3. Manufacturers (Plants): FG they produce + COMPONENTS they consume (per BOM)
    4. Distributors (DCs): FG only
    5. Demand nodes: Covered by MarketDemand, not ProductSiteConfig

    Args:
        session: Database session
        config: Supply chain configuration
        dry_run: If True, report issues without fixing

    Returns:
        Dictionary with validation results and actions taken
    """
    product_class = classify_products_from_bom(session, config)
    node_class = classify_nodes_by_role(session, config, product_class)

    report = {
        "config_id": config.id,
        "config_name": config.name,
        "products": {
            "components": list(product_class.components),
            "component_names": product_class.component_names,
            "finished_goods": list(product_class.finished_goods),
            "fg_names": product_class.fg_names
        },
        "nodes": {
            "vendor": len(node_class.market_supply_nodes),
            "tier1_suppliers": len(node_class.tier1_suppliers),
            "manufacturers": len(node_class.manufacturers),
            "distributors": len(node_class.distributors),
            "customer": len(node_class.market_demand_nodes)
        },
        "issues_found": [],
        "actions_taken": [],
        "dry_run": dry_run
    }

    # Get all existing ProductSiteConfig entries
    existing_configs = (
        session.query(ProductSiteConfig)
        .join(Node, ProductSiteConfig.site_id == Node.id)
        .filter(Node.config_id == config.id)
        .all()
    )

    configs_to_delete = []
    configs_to_add = []

    # Validate existing configurations
    for inc in existing_configs:
        node_id = inc.site_id
        product_id = inc.product_id

        is_component = product_id in product_class.components
        is_fg = product_id in product_class.finished_goods

        should_exist = False
        reason = ""

        # Rule 1: Market Supply nodes (Tier 2) - COMPONENTS only
        if node_id in node_class.market_supply_nodes:
            if is_component:
                should_exist = True
            else:
                reason = f"Market Supply node should not have FG {product_class.fg_names.get(product_id, product_id)}"

        # Rule 2: Tier 1 Suppliers - COMPONENTS only
        elif node_id in node_class.tier1_suppliers:
            if is_component:
                should_exist = True
            else:
                reason = f"Supplier should not have FG {product_class.fg_names.get(product_id, product_id)}"

        # Rule 3: Manufacturers - FG they produce + COMPONENTS they consume
        elif node_id in node_class.manufacturers:
            details = node_class.manufacturer_details.get(node_id, {})
            fg_produced = details.get("fg_produced", set())
            components_consumed = details.get("components_consumed", set())

            if is_fg and product_id in fg_produced:
                should_exist = True
            elif is_component and product_id in components_consumed:
                should_exist = True
            elif is_fg:
                reason = f"Manufacturer {details.get('name', node_id)} does not produce FG {product_class.fg_names.get(product_id, product_id)}"
            else:
                reason = f"Manufacturer {details.get('name', node_id)} does not consume component {product_class.component_names.get(product_id, product_id)}"

        # Rule 4: Distributors (DCs) - FG only
        elif node_id in node_class.distributors:
            if is_fg:
                should_exist = True
            else:
                reason = f"Distributor should not have component {product_class.component_names.get(product_id, product_id)}"

        # Rule 5: Market Demand nodes - should use MarketDemand, not ProductSiteConfig
        elif node_id in node_class.market_demand_nodes:
            should_exist = False
            reason = f"Market Demand node should use MarketDemand, not ProductSiteConfig"

        if not should_exist:
            issue = {
                "type": "invalid_product_site",
                "node_id": node_id,
                "product_id": product_id,
                "reason": reason
            }
            report["issues_found"].append(issue)
            configs_to_delete.append(inc)

    # Check for missing configurations
    # Manufacturers should have configs for FG they produce + components they consume
    for node_id, details in node_class.manufacturer_details.items():
        fg_produced = details.get("fg_produced", set())
        components_consumed = details.get("components_consumed", set())
        required_products = fg_produced | components_consumed

        existing_products = {
            inc.product_id for inc in existing_configs if inc.site_id == node_id
        }

        missing_products = required_products - existing_products
        if missing_products:
            issue = {
                "type": "missing_manufacturer_products",
                "node_id": node_id,
                "node_name": details.get("name", node_id),
                "missing_products": list(missing_products)
            }
            report["issues_found"].append(issue)
            # We'll add these in the fix section

    # Apply fixes if not dry run
    if not dry_run:
        # Delete invalid configurations
        for inc in configs_to_delete:
            session.delete(inc)
            report["actions_taken"].append({
                "action": "deleted",
                "node_id": inc.site_id,
                "product_id": inc.product_id
            })

        session.flush()

        print(f"[fix] Deleted {len(configs_to_delete)} invalid ProductSiteConfig entries for '{config.name}'")
    else:
        print(f"[dry-run] Would delete {len(configs_to_delete)} invalid ProductSiteConfig entries for '{config.name}'")

    report["summary"] = {
        "total_issues": len(report["issues_found"]),
        "configs_deleted": len(configs_to_delete) if not dry_run else 0,
        "configs_added": len(configs_to_add) if not dry_run else 0
    }

    return report


def print_validation_report(report: Dict[str, any]) -> None:
    """Print a human-readable validation report."""

    print(f"\n{'='*80}")
    print(f"Product-Site Validation Report: {report['config_name']} (ID: {report['config_id']})")
    print(f"{'='*80}\n")

    print(f"Product Classification:")
    print(f"  Components: {len(report['products']['components'])}")
    for comp_id in sorted(report['products']['components']):
        name = report['products']['component_names'].get(comp_id, f"Item-{comp_id}")
        print(f"    - {name} (ID: {comp_id})")

    print(f"\n  Finished Goods: {len(report['products']['finished_goods'])}")
    for fg_id in sorted(report['products']['finished_goods']):
        name = report['products']['fg_names'].get(fg_id, f"Item-{fg_id}")
        print(f"    - {name} (ID: {fg_id})")

    print(f"\nNode Distribution:")
    for node_type, count in report['nodes'].items():
        print(f"  {node_type}: {count}")

    print(f"\nIssues Found: {len(report['issues_found'])}")
    if report['issues_found']:
        for issue in report['issues_found']:
            print(f"  - {issue['type']}: {issue.get('reason', json.dumps(issue))}")
    else:
        print("  No issues found! ✅")

    print(f"\nSummary:")
    print(f"  Total issues: {report['summary']['total_issues']}")
    if report['dry_run']:
        print(f"  [DRY RUN] Would delete: {len([i for i in report['issues_found'] if i['type'] == 'invalid_product_site'])}")
    else:
        print(f"  Configs deleted: {report['summary']['configs_deleted']}")
        print(f"  Configs added: {report['summary']['configs_added']}")

    print(f"\n{'='*80}\n")
