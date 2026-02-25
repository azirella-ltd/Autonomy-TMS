#!/usr/bin/env python3
"""Create a multi-region supply chain configuration with suppliers, plants, and markets."""

from __future__ import annotations

import argparse
import json
import os
import re
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from collections import defaultdict

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in os.sys.path:  # type: ignore[attr-defined]
    os.sys.path.append(str(BACKEND_ROOT))  # type: ignore[attr-defined]

from app.core.config import settings
from app.core.time_buckets import TimeBucket
from app.models import Customer
from app.models.supply_chain_config import (
    Item,
    ProductSiteConfig,
    Lane,
    Market,
    MarketDemand,
    Node,
    NodeType,
    SupplyChainConfig,
)


@dataclass(frozen=True)
class ItemAssignment:
    item: Item
    manufacturer: Node
    suppliers: Tuple[Node, ...]


INVENTORY_TARGET_RANGE = {"min": 40, "max": 80}
INITIAL_INVENTORY_RANGE = {"min": 30, "max": 45}
DC_INVENTORY_TARGET_RANGE = {"min": 50, "max": 90}
DC_INITIAL_INVENTORY_RANGE = {"min": 40, "max": 55}
HOLDING_COST_RANGE = {"min": 0.5, "max": 1.5}
BACKLOG_COST_RANGE = {"min": 5.0, "max": 12.0}
SELLING_PRICE_RANGE = {"min": 55.0, "max": 95.0}
MANUFACTURING_PRICE_RANGE = {"min": 45.0, "max": 80.0}
DEFAULT_MARKET_SUPPLY_CAPACITY = 0
SUPPLIER_INVENTORY_TARGET_RANGE = {"min": 12, "max": 24}
SUPPLIER_INITIAL_INVENTORY_RANGE = {"min": 8, "max": 16}
SUPPLIER_HOLDING_COST_RANGE = {"min": 0.3, "max": 0.9}
SUPPLIER_BACKLOG_COST_RANGE = {"min": 3.0, "max": 7.0}
SUPPLIER_SELLING_PRICE_RANGE = {"min": 30.0, "max": 55.0}


def _node_dag_type(node: Node) -> str:
    return str(getattr(node, "dag_type", None) or getattr(node, "type", "")).strip().lower()


def _master_from_enum(node_type: NodeType) -> str:
    if node_type in {NodeType.MARKET_SUPPLY}:
        return "market_supply"
    if node_type in {NodeType.MARKET_DEMAND}:
        return "market_demand"
    if node_type in {NodeType.MANUFACTURER}:
        return "manufacturer"
    return "inventory"


def _lead_time_payload(mean_weeks: float, cov: float) -> Dict[str, float]:
    return {
        "distribution": "lognormal",
        "mean_weeks": mean_weeks,
        "cov": cov,
        "min": mean_weeks,
        "max": mean_weeks,
    }


def _lognormal_demand_pattern(mean: float, cov: float) -> Dict[str, object]:
    return {
        "demand_type": "lognormal",
        "variability": {
            "type": "lognormal",
            "mean": mean,
            "cov": cov,
        },
        "seasonality": {
            "type": "none",
            "amplitude": 0,
            "period": 52,
            "phase": 0,
        },
        "trend": {"type": "none", "slope": 0, "intercept": mean},
        "parameters": {"mean": mean, "cov": cov},
        "params": {"mean": mean, "cov": cov},
    }


def _create_items(session: Session, config: SupplyChainConfig) -> List[Item]:
    items: List[Item] = []
    for idx in range(1, 11):
        item = Item(
            config_id=config.id,
            name=f"FG-{idx:02d}",
            description="Finished good for the multi-region supply chain",
            unit_cost_range={"min": 35.0, "max": 75.0},
        )
        session.add(item)
        session.flush()
        items.append(item)
    return items


def _ensure_market_supply_attributes(
    node: Optional[Node],
    *,
    default_capacity: int = DEFAULT_MARKET_SUPPLY_CAPACITY,
) -> None:
    """Ensure Market Supply nodes expose the required capacity metadata."""

    if not node:
        return
    attrs = getattr(node, "attributes", {}) or {}
    if isinstance(attrs, str):
        try:
            attrs = json.loads(attrs)
        except Exception:
            attrs = {}
    if not isinstance(attrs, dict):
        attrs = {}
    capacity_value = attrs.get("supply_capacity")
    numeric_capacity: Optional[int] = None
    if capacity_value is not None:
        try:
            numeric_capacity = int(float(capacity_value))
        except (TypeError, ValueError):
            numeric_capacity = None
    if numeric_capacity is None or numeric_capacity < 0:
        numeric_capacity = default_capacity
    attrs["supply_capacity"] = numeric_capacity
    attrs["inventory_capacity_max"] = max(
        numeric_capacity, attrs.get("inventory_capacity_max") or 0
    )
    attrs.setdefault("inventory_capacity_min", 0)
    node.attributes = attrs


def _create_markets(session: Session, config: SupplyChainConfig) -> Dict[str, Market]:
    markets: Dict[str, Market] = {}
    descriptions = {
        "A": "Demand Region A (Coastal)",
        "B": "Demand Region B (Central)",
        "C": "Demand Region C (Mountain)",
    }
    for code in ("A", "B", "C"):
        market = Market(config_id=config.id, name=f"Demand Region {code}", description=descriptions[code])
        session.add(market)
        session.flush()
        markets[code] = market
    return markets


def _create_nodes(
    session: Session, config: SupplyChainConfig
) -> Tuple[Dict[str, Node], List[Tuple[Node, str]], Dict[str, Node]]:
    nodes: Dict[str, Node] = {}
    suppliers: List[Tuple[Node, str]] = []

    tier2_nodes: Dict[str, Node] = {}
    for code in ("A", "B", "C"):
        tier2_node = Node(
            config_id=config.id,
            name=f"Tier2-{code}",
            type=NodeType.MARKET_SUPPLY,
        )
        session.add(tier2_node)
        session.flush()
        _ensure_market_supply_attributes(tier2_node)
        session.add(tier2_node)
        tier2_nodes[code] = tier2_node
        nodes[f"tier2-{code.lower()}"] = tier2_node

    # Market demand nodes
    for code in ("A", "B", "C"):
        node = Node(config_id=config.id, name=f"Demand Region {code}", type=NodeType.MARKET_DEMAND)
        session.add(node)
        session.flush()
        nodes[f"market-{code}"] = node

    # Distribution centers (one per market)
    for code in ("A", "B", "C"):
        node = Node(config_id=config.id, name=f"DC {code}", type=NodeType.DISTRIBUTOR)
        session.add(node)
        session.flush()
        nodes[f"dc-{code}"] = node

    # Manufacturing plants (both located in region B)
    for idx in range(1, 3):
        node = Node(config_id=config.id, name=f"Plant B{idx}", type=NodeType.MANUFACTURER)
        session.add(node)
        session.flush()
        nodes[f"plant-b{idx}"] = node

    # Suppliers (30 total, spread across markets)
    supplier_specs: List[Tuple[str, str]] = []
    supplier_specs.extend(((_format_component_supplier_name("A", idx), "A")) for idx in range(1, 13))
    supplier_specs.extend(((_format_component_supplier_name("B", idx), "B")) for idx in range(1, 9))
    supplier_specs.extend(((_format_component_supplier_name("C", idx), "C")) for idx in range(1, 11))

    for name, region in supplier_specs:
        node = Node(config_id=config.id, name=name, type=NodeType.SUPPLIER)
        session.add(node)
        session.flush()
        nodes[f"supplier-{name.lower().replace(' ', '-')}"] = node
        suppliers.append((node, region))

    return nodes, suppliers, tier2_nodes


def _connect_suppliers_to_market_supply(
    session: Session,
    config: SupplyChainConfig,
    supplier_nodes: Sequence[Tuple[Node, str]],
    tier2_nodes: Mapping[str, Node],
) -> None:
    for supplier_node, region in supplier_nodes:
        region_code = (region or "").upper()
        supply_node = tier2_nodes.get(region_code) or next(iter(tier2_nodes.values()))
        same_region = region_code == "B"
        mean_weeks = 2.0 if same_region else 3.0
        lane = Lane(
            config_id=config.id,
            from_site_id=supply_node.id,
            to_site_id=supplier_node.id,
            capacity=350,
            lead_time_days=_lead_time_payload(mean_weeks=mean_weeks, cov=1.1),
            demand_lead_time={"type": "deterministic", "value": 1},
            supply_lead_time={"type": "deterministic", "value": mean_weeks},
        )
        session.add(lane)


def _assign_items_to_manufacturers(
    session: Session,
    config: SupplyChainConfig,
    items: Sequence[Item],
    nodes: Dict[str, Node],
    supplier_nodes: Sequence[Tuple[Node, str]],
) -> List[ItemAssignment]:
    assignments: List[ItemAssignment] = []
    suppliers_per_item = 3
    expected_suppliers = len(items) * suppliers_per_item
    if len(supplier_nodes) < expected_suppliers:
        raise RuntimeError(f"Expected at least {expected_suppliers} supplier nodes to be created")

    for idx, item in enumerate(items):
        item_number = idx + 1
        plant_key = "plant-b1" if item_number <= 5 else "plant-b2"
        plant = nodes[plant_key]

        supplier_slice = supplier_nodes[idx * suppliers_per_item : idx * suppliers_per_item + suppliers_per_item]
        if len(supplier_slice) != suppliers_per_item:
            raise RuntimeError("Each item must be assigned to exactly three suppliers")

        supplier_nodes_only: List[Node] = []
        for lane_supplier, region in supplier_slice:
            same_region = region == "B"
            mean_weeks = 2.0 if same_region else 3.0
            lane = Lane(
                config_id=config.id,
                from_site_id=lane_supplier.id,
                to_site_id=plant.id,
                capacity=400,
                lead_time_days=_lead_time_payload(mean_weeks, cov=1.25),
                demand_lead_time={"type": "deterministic", "value": 1},
                supply_lead_time={"type": "deterministic", "value": mean_weeks},
            )
            session.add(lane)
            supplier_nodes_only.append(lane_supplier)

        range_payload = {
            "inventory_target_range": dict(INVENTORY_TARGET_RANGE),
            "initial_inventory_range": dict(INITIAL_INVENTORY_RANGE),
            "holding_cost_range": dict(HOLDING_COST_RANGE),
            "backlog_cost_range": dict(BACKLOG_COST_RANGE),
            "selling_price_range": dict(MANUFACTURING_PRICE_RANGE),
        }
        item_cfg = ProductSiteConfig(product_id=item.id, site_id=plant.id, **range_payload)
        session.add(item_cfg)
        assignments.append(
            ItemAssignment(
                item=item,
                manufacturer=plant,
                suppliers=tuple(supplier_nodes_only),
            )
        )

    session.flush()
    _annotate_manufacturer_bom(assignments)
    return assignments


def _annotate_manufacturer_bom(assignments: Sequence[ItemAssignment]) -> None:
    """Attach bill-of-material metadata to manufacturer node attributes."""

    bom_by_node: Dict[int, Dict[str, Dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
    for assignment in assignments:
        manufacturer = assignment.manufacturer
        item_key = str(assignment.item.id)
        component_map = bom_by_node[manufacturer.id].setdefault(item_key, {})
        for supplier in assignment.suppliers:
            supplier_id = getattr(supplier, "id", None)
            if not supplier_id:
                continue
            component_key = str(supplier_id)
            component_map[component_key] = component_map.get(component_key, 0) + 1

    for assignment in assignments:
        manufacturer = assignment.manufacturer
        item_map = bom_by_node.get(manufacturer.id)
        if not item_map:
            continue
        attrs = dict(getattr(manufacturer, "attributes", {}) or {})
        current = attrs.get("bill_of_materials", {})
        for item_id, components in item_map.items():
            current[item_id] = components
        attrs["bill_of_materials"] = current
        attrs.setdefault("manufacturing_leadtime", 0)
        attrs.setdefault("manufacturing_capacity_hours", 7 * 24)  # default 1-week bucket
        util_map = dict(attrs.get("capacity_utilization_by_item") or {})
        for item_id in item_map.keys():
            util_map[item_id] = util_map.get(item_id, 0)
        attrs["capacity_utilization_by_item"] = util_map
        manufacturer.attributes = attrs


def _configure_distribution(session: Session, config: SupplyChainConfig, nodes: Dict[str, Node]) -> None:
    for market_code in ("A", "B", "C"):
        dc_node = nodes[f"dc-{market_code}"]
        market_node = nodes[f"market-{market_code}"]
        lane = Lane(
            config_id=config.id,
            from_site_id=dc_node.id,
            to_site_id=market_node.id,
            capacity=600,
            lead_time_days=_lead_time_payload(mean_weeks=2.0, cov=1.0),
            demand_lead_time={"type": "deterministic", "value": 1},
            supply_lead_time={"type": "deterministic", "value": 2.0},
        )
        session.add(lane)


def _connect_plants_to_dcs(session: Session, config: SupplyChainConfig, nodes: Dict[str, Node]) -> None:
    for plant_idx in (1, 2):
        plant = nodes[f"plant-b{plant_idx}"]
        for market_code in ("A", "B", "C"):
            dc_node = nodes[f"dc-{market_code}"]
            mean_weeks = 2.0 if market_code == "B" else 3.0
            lane = Lane(
                config_id=config.id,
                from_site_id=plant.id,
                to_site_id=dc_node.id,
                capacity=500,
                lead_time_days=_lead_time_payload(mean_weeks=mean_weeks, cov=1.0),
                demand_lead_time={"type": "deterministic", "value": 1},
                supply_lead_time={"type": "deterministic", "value": mean_weeks},
            )
            session.add(lane)


def _configure_dc_item_settings(session: Session, items: Sequence[Item], nodes: Dict[str, Node]) -> None:
    for market_code in ("A", "B", "C"):
        dc_node = nodes[f"dc-{market_code}"]
        for item in items:
            cfg = ProductSiteConfig(
                product_id=item.id,
                site_id=dc_node.id,
                inventory_target_range=dict(DC_INVENTORY_TARGET_RANGE),
                initial_inventory_range=dict(DC_INITIAL_INVENTORY_RANGE),
                holding_cost_range=dict(HOLDING_COST_RANGE),
                backlog_cost_range=dict(BACKLOG_COST_RANGE),
                selling_price_range=dict(SELLING_PRICE_RANGE),
            )
            session.add(cfg)
    session.flush()


def _ensure_supplier_item_configs(
    session: Session,
    items: Sequence[Item],
    nodes: Sequence[Node],
) -> None:
    """Ensure every supplier node exposes inventory/cost settings for each item."""

    supplier_nodes = [
        node for node in nodes if "supplier" in _node_dag_type(node)
    ]
    if not supplier_nodes or not items:
        return

    supplier_ids = [node.id for node in supplier_nodes if node.id]
    if not supplier_ids:
        return

    existing_pairs = {
        (item_id, node_id)
        for item_id, node_id in session.query(
            ProductSiteConfig.product_id, ProductSiteConfig.site_id
        )
        .filter(ProductSiteConfig.site_id.in_(supplier_ids))
        .all()
    }

    for supplier_node in supplier_nodes:
        if not supplier_node.id:
            continue
        for item in items:
            pair = (item.id, supplier_node.id)
            if pair in existing_pairs:
                continue
            range_payload = {
                "inventory_target_range": dict(SUPPLIER_INVENTORY_TARGET_RANGE),
                "initial_inventory_range": dict(SUPPLIER_INITIAL_INVENTORY_RANGE),
                "holding_cost_range": dict(SUPPLIER_HOLDING_COST_RANGE),
                "backlog_cost_range": dict(SUPPLIER_BACKLOG_COST_RANGE),
                "selling_price_range": dict(SUPPLIER_SELLING_PRICE_RANGE),
            }
            session.add(
                ProductSiteConfig(
                    product_id=item.id,
                    site_id=supplier_node.id,
                    **range_payload,
                )
            )
            existing_pairs.add(pair)
    session.flush()


def _configure_demand(
    session: Session,
    config: SupplyChainConfig,
    items: Sequence[Item],
    markets: Dict[str, Market],
) -> None:
    """Assign explicit demand items to each market covering every item/market combination."""
    market_codes = list(markets.keys())
    if not market_codes or not items:
        return

    session.query(MarketDemand).filter(MarketDemand.config_id == config.id).delete()
    session.flush()

    rng = random.Random(config.id or 0)
    for market_code in market_codes:
        for idx, item in enumerate(items):
            base_mean = 10.0 + (idx % 5) * 3.5
            market_multiplier = {"A": 0.9, "B": 1.1, "C": 1.0}.get(market_code, 1.0)
            noise = rng.uniform(-1.0, 1.0)
            mean = max(4.0, base_mean * market_multiplier + noise)
            cov = max(0.4, min(1.8, 0.6 + (idx % 4) * 0.2 + rng.uniform(-0.05, 0.05)))
            pattern = _lognormal_demand_pattern(mean=mean, cov=cov)
            session.add(
                MarketDemand(
                    config_id=config.id,
                    product_id=item.id,
                    market_id=markets[market_code].id,
                    demand_pattern=pattern,
                )
            )
    session.flush()


def ensure_multi_region_config(
    session: Session,
    *,
    customer: Customer,
    name: str,
    description: Optional[str] = None,
) -> Tuple[SupplyChainConfig, bool]:
    existing = (
        session.query(SupplyChainConfig)
        .filter(SupplyChainConfig.customer_id == customer.id, SupplyChainConfig.name == name)
        .first()
    )
    if existing:
        print(
            f"[info] Supply chain configuration '{name}' already exists (id={existing.id})."
        )
        _ensure_component_supplier_metadata(session, existing)
        _ensure_complex_market_nodes(session, existing)
        items = session.query(Item).filter(Item.config_id == existing.id).order_by(Item.id.asc()).all()
        nodes = session.query(Node).filter(Node.config_id == existing.id).all()
        markets = {}
        for m in session.query(Market).filter(Market.config_id == existing.id).all():
            key = m.name.split()[-1].upper()
            markets[key] = m
        _ensure_supplier_item_configs(session, items, nodes)
        _configure_demand(session, existing, items, markets)
        if description and existing.description != description:
            existing.description = description
            session.add(existing)
            session.flush()
        _apply_inventory_capacity_attributes(session, existing)
        return existing, False

    config = SupplyChainConfig(
        name=name,
        description=description or "Multi-region, multi-echelon supply chain",
        customer_id=customer.id,
        created_by=customer.admin_id,
        is_active=True,
        time_bucket=TimeBucket.WEEK,
    )
    config.site_type_definitions = _component_supplier_site_type_definitions()
    session.add(config)
    session.flush()

    items = _create_items(session, config)
    markets = _create_markets(session, config)
    nodes, suppliers, tier2_nodes = _create_nodes(session, config)
    _connect_suppliers_to_market_supply(session, config, suppliers, tier2_nodes)
    assignments = _assign_items_to_manufacturers(session, config, items, nodes, suppliers)
    _connect_plants_to_dcs(session, config, nodes)
    _configure_distribution(session, config, nodes)
    _configure_dc_item_settings(session, items, nodes)
    _ensure_supplier_item_configs(session, items, nodes.values())
    _configure_demand(session, config, items, markets)
    _ensure_component_supplier_metadata(session, config)
    _ensure_complex_market_nodes(session, config)
    _apply_inventory_capacity_attributes(session, config)

    session.add(config)
    session.flush()

    print(json.dumps(
        {
            "config_id": config.id,
            "items": len(items),
            "markets": list(markets.keys()),
            "nodes": len(nodes),
            "assignments": [
                {
                    "item": assignment.item.name,
                    "plant": assignment.manufacturer.name,
                    "suppliers": [supplier.name for supplier in assignment.suppliers],
                }
                for assignment in assignments
            ],
        },
        indent=2,
    ))

    return config, True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a multi-region SC config")
    parser.add_argument("--customer-name", default="Beer Game", help="Customer to attach the configuration to")
    parser.add_argument("--config-name", default="Complex_SC", help="Name of the configuration")
    parser.add_argument(
        "--description",
        default="Complex supply chain with multi-region network and 30 suppliers.",
        help="Description for the configuration",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as session:
        customer = session.query(Customer).filter(Customer.name == args.customer_name).first()
        if customer is None:
            raise RuntimeError(f"Customer '{args.customer_name}' not found.")
        config, created = ensure_multi_region_config(
            session,
            customer=customer,
            name=args.config_name,
            description=args.description,
        )
        session.commit()
        if created:
            print(f"[success] Created configuration '{config.name}' (id={config.id}) for customer '{customer.name}'.")
        else:
            print(f"[info] Configuration '{config.name}' already present (id={config.id}).")


def _component_supplier_site_type_definitions() -> List[Dict[str, object]]:
    """Return the desired node type definition payload for component suppliers."""

    blueprint: Tuple[Tuple[str, str, bool, str], ...] = (
        ("market_demand", "Demand Region", True, "market_demand"),
        ("distributor", "Distributor", False, "inventory"),
        ("plant", "Plant", False, "manufacturer"),
        ("component_supplier", "Tier1 Supplier", False, "inventory"),
        ("market_supply", "Supply Region", True, "market_supply"),
    )

    definitions: List[Dict[str, object]] = []
    for order, (node_type, label, is_required, master_type) in enumerate(blueprint):
        definitions.append(
            {
                "type": node_type,
                "label": label,
                "order": order,
                "is_required": is_required,
                "master_type": master_type,
            }
        )
    return definitions


def _format_component_supplier_name(region: str, index: int) -> str:
    """Return a consistent display name for component suppliers."""

    return f"Tier1-{region.upper()}{index:02d}"


def _normalize_existing_supplier_name(name: str) -> str:
    """Upgrade legacy supplier names to the Tier1 naming convention."""

    match = re.match(r"(?:component\s+supplier|tier1|supplier)\s+([A-Z])[-\s]*(\d+)", name.strip(), re.IGNORECASE)
    if match:
        region = match.group(1).upper()
        try:
            number = int(match.group(2))
        except ValueError:
            number = 0
        return _format_component_supplier_name(region, number or 1)

    if name.lower().startswith("supplier"):
        return name.replace("Supplier", "Tier1 Supplier", 1)
    return name


def _ensure_component_supplier_metadata(session: Session, config: SupplyChainConfig) -> None:
    """Ensure node type definitions and supplier nodes use the component supplier role."""

    config.site_type_definitions = _component_supplier_site_type_definitions()
    session.add(config)

    nodes = session.query(Node).filter(Node.config_id == config.id).all()

    def _apply(node: Node, node_type: str, master_type: str) -> None:
        node.type = node_type
        node.dag_type = node_type
        node.master_type = master_type
        session.add(node)

    for node in nodes:
        normalized_name = (node.name or "").strip().lower()
        dag_type = _node_dag_type(node)

        if normalized_name.startswith("tier2-") or normalized_name.startswith("market supply"):
            if not normalized_name.startswith("tier2-"):
                node.name = "Tier2-A"
            _apply(node, "market_supply", "market_supply")
            continue

        if normalized_name.startswith("market demand") or normalized_name.startswith("demand region"):
            _apply(node, "market_demand", "market_demand")
            continue

        if normalized_name.startswith("dc ") or normalized_name.startswith("dc-"):
            _apply(node, "distributor", "inventory")
            continue

        if normalized_name.startswith("plant"):
            _apply(node, "plant", "manufacturer")
            continue

        if (
            "supplier" in dag_type
            or normalized_name.startswith("component supplier")
            or normalized_name.startswith("supplier")
            or normalized_name.startswith("tier1-")
        ):
            node.name = _normalize_existing_supplier_name(node.name)
            _apply(node, "component_supplier", "inventory")
            continue

    session.flush()


def _apply_inventory_capacity_attributes(session: Session, config: SupplyChainConfig) -> None:
    """Populate inventory_capacity metadata on nodes based on item-node target ranges."""

    node_totals: Dict[int, float] = defaultdict(float)
    configs = (
        session.query(ProductSiteConfig)
        .filter(ProductSiteConfig.site_id.isnot(None), ProductSiteConfig.product_id.isnot(None))
        .join(Node, Node.id == ProductSiteConfig.site_id)
        .filter(Node.config_id == config.id)
        .all()
    )
    for cfg in configs:
        target_range = cfg.inventory_target_range or {}
        max_value = None
        if isinstance(target_range, dict):
            for key in ("max", "maximum", "high"):
                if key in target_range:
                    try:
                        max_value = float(target_range[key])
                    except (TypeError, ValueError):
                        max_value = None
                    if max_value is not None:
                        break
        if max_value is None:
            continue
        node_totals[cfg.site_id] += max(0.0, max_value)

    if not node_totals:
        return

    nodes = (
        session.query(Node)
        .filter(Node.config_id == config.id, Node.id.in_(node_totals.keys()))
        .all()
    )
    for node in nodes:
        total_capacity = node_totals.get(node.id)
        if total_capacity is None:
            continue
        attrs = dict(getattr(node, "attributes", {}) or {})
        existing_max = attrs.get("inventory_capacity_max")
        if existing_max is None or total_capacity > float(existing_max):
            attrs["inventory_capacity_max"] = total_capacity
        attrs.setdefault("inventory_capacity_min", 0)
        node.attributes = attrs
        session.add(node)
    session.flush()


def _ensure_complex_market_nodes(session: Session, config: SupplyChainConfig) -> None:
    """Ensure Complex_SC has Demand/Supply Regions and tiered lanes."""

    nodes = session.query(Node).filter(Node.config_id == config.id).all()
    nodes_by_name = {node.name.strip().lower(): node for node in nodes}

    def _get_or_create(name: str, node_type: NodeType) -> Node:
        key = name.strip().lower()
        canonical_type = node_type.value.lower()
        master_type = _master_from_enum(node_type)
        lookup_keys = [key]
        if "demand region" in key:
            lookup_keys.append(key.replace("demand region", "market demand"))
        if "market demand" in key:
            lookup_keys.append(key.replace("market demand", "demand region"))
        node = None
        for candidate in lookup_keys:
            node = nodes_by_name.get(candidate)
            if node:
                key = candidate
                break
        if node:
            if _node_dag_type(node) != canonical_type:
                node.type = canonical_type
                node.dag_type = canonical_type
                node.master_type = master_type
                session.add(node)
            if node.name.strip().lower() != name.strip().lower():
                node.name = name
            nodes_by_name[name.strip().lower()] = node
            return node
        node = Node(
            config_id=config.id,
            name=name,
            type=canonical_type,
            dag_type=canonical_type,
            master_type=master_type,
        )
        session.add(node)
        session.flush()
        nodes_by_name[key] = node
        return node

    tier2_nodes: Dict[str, Node] = {}
    legacy_supply = nodes_by_name.get("market supply")
    for idx, code in enumerate(("A", "B", "C")):
        desired_name = f"Tier2-{code}"
        key = desired_name.strip().lower()
        node = nodes_by_name.get(key)
        if not node and legacy_supply and idx == 0:
            node = legacy_supply
            node.name = desired_name
            nodes_by_name[key] = node
            nodes_by_name.pop("market supply", None)
        if not node:
            node = Node(
                config_id=config.id,
                name=desired_name,
                type=NodeType.MARKET_SUPPLY.value.lower(),
                dag_type=NodeType.MARKET_SUPPLY.value.lower(),
                master_type=_master_from_enum(NodeType.MARKET_SUPPLY),
            )
            session.add(node)
            session.flush()
            nodes.append(node)
            nodes_by_name[key] = node
        _ensure_market_supply_attributes(node)
        session.add(node)
        tier2_nodes[code] = node

    market_demand_nodes = [
        _get_or_create(f"Demand Region {code}", NodeType.MARKET_DEMAND)
        for code in ("A", "B", "C")
    ]

    dc_nodes = {
        code: nodes_by_name.get(f"dc {code}".strip().lower())
        or nodes_by_name.get(f"dc-{code}".strip().lower())
        for code in ("A", "B", "C")
    }

    supplier_nodes = [node for node in nodes if "supplier" in _node_dag_type(node)]

    existing_lanes = {
        (lane.from_site_id, lane.to_site_id)
        for lane in session.query(Lane).filter(Lane.config_id == config.id).all()
    }

    def _infer_supplier_region(node: Node) -> str:
        name = (node.name or "").upper()
        match = re.search(r"TIER1[-\s]*([ABC])", name)
        if match:
            return match.group(1)
        match = re.search(r"COMPONENT SUPPLIER\s+([ABC])", name)
        if match:
            return match.group(1)
        return "A"

    tier2_id_map = {code: node.id for code, node in tier2_nodes.items() if node.id}
    tier2_ids = list(tier2_id_map.values())
    supplier_ids = [node.id for node in supplier_nodes if node.id]
    if tier2_ids and supplier_ids:
        supply_lanes = (
            session.query(Lane)
            .filter(
                Lane.config_id == config.id,
                Lane.from_site_id.in_(tier2_ids),
                Lane.to_site_id.in_(supplier_ids),
            )
            .all()
        )
        for lane in supply_lanes:
            supplier_node = next((node for node in supplier_nodes if node.id == lane.to_site_id), None)
            if not supplier_node:
                continue
            region = _infer_supplier_region(supplier_node)
            desired_node = tier2_nodes.get(region) or next(iter(tier2_nodes.values()))
            if lane.from_site_id != desired_node.id:
                existing_lanes.discard((lane.from_site_id, lane.to_site_id))
                lane.from_site_id = desired_node.id
                existing_lanes.add((lane.from_site_id, lane.to_site_id))
                session.add(lane)

    # Ensure Tier2 → Tier1 suppliers
    for supplier in supplier_nodes:
        region = _infer_supplier_region(supplier)
        upstream = tier2_nodes.get(region) or next(iter(tier2_nodes.values()))
        key = (upstream.id, supplier.id)
        if key in existing_lanes:
            continue
        lane = Lane(
            config_id=config.id,
            from_site_id=upstream.id,
            to_site_id=supplier.id,
            capacity=350,
            lead_time_days=_lead_time_payload(mean_weeks=3.0, cov=1.1),
            demand_lead_time={"type": "deterministic", "value": 1},
            supply_lead_time={"type": "deterministic", "value": 3.0},
        )
        session.add(lane)

    # Ensure DC → Market Demand lanes
    for code, md_node in zip(("A", "B", "C"), market_demand_nodes):
        dc_node = dc_nodes.get(code)
        if not dc_node:
            continue
        key = (dc_node.id, md_node.id)
        if key in existing_lanes:
            continue
        lane = Lane(
            config_id=config.id,
            from_site_id=dc_node.id,
            to_site_id=md_node.id,
            capacity=600,
            lead_time_days=_lead_time_payload(mean_weeks=2.0, cov=1.0),
            demand_lead_time={"type": "deterministic", "value": 1},
            supply_lead_time={"type": "deterministic", "value": 2.0},
        )
        session.add(lane)

    session.flush()


if __name__ == "__main__":
    main()
