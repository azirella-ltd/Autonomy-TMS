#!/usr/bin/env python3
"""
Set up demo scenarios for the Food Distribution tenant (tenant_id=3, config_id=22).

Creates three scenarios:
  1. Food Dist - Naive Baseline
  2. Food Dist - PID Controller
  3. Food Dist - TRM Agents

Each scenario is populated with AI agents using the appropriate strategy.
The TRM scenario will use the trained checkpoints in checkpoints/trm_food_dist/.
"""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.orm import sessionmaker
from app.db.session import sync_engine
from app.models.scenario import Scenario, ScenarioStatus
from app.models.participant import ScenarioUser, ScenarioUserRole as PlayerRole, ScenarioUserType
from app.models.agent_config import AgentConfig
from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane
from app.models.sc_entities import Product

# Dynamic lookup — no hardcoded IDs
from scripts.food_dist_lookup import resolve_food_dist_ids as _resolve
_fd = _resolve()
TENANT_ID = _fd["tenant_id"]
CONFIG_ID = _fd["config_id"]

DEMO_SCENARIOS = [
    {
        "name": "Food Dist - Naive Baseline",
        "description": "Baseline simulation using Naive agents (echo incoming demand) for the Food Distribution network.",
        "strategy": "naive",
        "max_periods": 52,
    },
    {
        "name": "Food Dist - PID Controller",
        "description": "PID feedback controller agents managing inventory in the Food Distribution network.",
        "strategy": "pid_heuristic",
        "max_periods": 52,
    },
    {
        "name": "Food Dist - TRM Agents",
        "description": "TRM (Tiny Recursive Model) agents with trained neural network models managing the Food Distribution DC. Uses checkpoints from Phase 1 behavioral cloning.",
        "strategy": "trm",
        "max_periods": 52,
    },
]


def get_admin_user_id(session):
    """Find admin user for tenant 3."""
    from app.models.tenant import Tenant
    from app.models.user import User
    tenant = session.query(Tenant).filter(Tenant.id == TENANT_ID).first()
    if tenant and tenant.admin_id:
        return tenant.admin_id
    user = session.query(User).filter(User.tenant_id == TENANT_ID).first()
    return user.id if user else 1


def build_scenario_config(session, config_id):
    """Build a scenario config JSON directly from supply chain topology."""
    config = session.query(SupplyChainConfig).filter(SupplyChainConfig.id == config_id).first()
    if not config:
        raise ValueError(f"Config {config_id} not found")

    nodes = session.query(Site).filter(Site.config_id == config_id).all()
    lanes = session.query(TransportationLane).filter(TransportationLane.config_id == config_id).all()
    products = session.query(Product).filter(Product.config_id == config_id).all()

    # Build nodes list
    nodes_list = []
    node_types = {}
    node_master_types = {}
    node_policies = {}

    for node in nodes:
        node_type = (node.type or "").lower()
        master_type = (node.master_type or "").lower()

        nodes_list.append({
            "id": node.id,
            "name": node.name,
            "type": node_type,
            "dag_type": master_type,
            "master_type": master_type,
            "priority": node.priority,
            "order_aging": node.order_aging or 0,
            "attributes": node.attributes or {},
        })
        node_types[node.name] = node_type
        node_master_types[node.name] = master_type

        # Only create policies for playable nodes (INVENTORY and MANUFACTURER)
        if master_type in ("inventory", "manufacturer"):
            node_policies[node.name] = {
                "init_inventory": 100,
                "order_leadtime": 1,
                "supply_leadtime": 2,
                "standard_cost": 50.0,
                "variable_cost": 0.0,
                "price": 75.0,
                "min_order_qty": 0,
                "partial_order_fulfillment": True,
                "order_aging": 0,
                "attributes": {},
            }

    # Build lanes list
    lanes_list = []
    for lane in lanes:
        lanes_list.append({
            "from_site_id": lane.from_site_id,
            "to_site_id": lane.to_site_id,
            "lead_time": (lane.supply_lead_time or {}).get("value", 2) if isinstance(lane.supply_lead_time, dict) else 2,
            "transport_cost": 0,
        })

    # Build items list (Product uses string id, no 'name' field)
    items_list = []
    for product in products:
        items_list.append({
            "id": product.id,
            "name": product.id,  # Product id IS the name (e.g., "CFG22_FP001")
            "description": product.description or "",
        })

    # Demand pattern (classic beer game step pattern adapted for food dist)
    demand_pattern = {
        "type": "classic",
        "params": {
            "initial_demand": 40,
            "step_demand": 60,
            "step_week": 5,
            "noise_std": 5,
        },
    }

    return {
        "name": config.name,
        "description": config.description or "",
        "supply_chain_config_id": config_id,
        "max_periods": 52,
        "is_public": True,
        "time_bucket": "week",
        "nodes": nodes_list,
        "lanes": lanes_list,
        "items": items_list,
        "node_types": node_types,
        "node_master_types": node_master_types,
        "node_policies": node_policies,
        "demand_pattern": demand_pattern,
        "progression_mode": "unsupervised",
    }


def create_scenario_with_agents(session, base_config, spec, admin_user_id):
    """Create a scenario and populate with AI agents."""
    name = spec["name"]
    strategy = spec["strategy"]

    # Check if already exists
    existing = (
        session.query(Scenario)
        .filter(Scenario.tenant_id == TENANT_ID, Scenario.name == name)
        .first()
    )
    if existing:
        print(f"[skip] Scenario '{name}' already exists (id={existing.id})")
        return existing

    # Clone and customize config for this scenario
    scenario_config = json.loads(json.dumps(base_config))
    scenario_config["name"] = name
    scenario_config["description"] = spec["description"]
    scenario_config.setdefault("autonomy", {})
    scenario_config["autonomy"]["strategy"] = strategy

    scenario = Scenario(
        name=name,
        description=spec["description"],
        created_by=admin_user_id,
        tenant_id=TENANT_ID,
        status=ScenarioStatus.CREATED,
        max_periods=spec["max_periods"],
        config=scenario_config,
        demand_pattern=scenario_config.get("demand_pattern", {}),
        supply_chain_config_id=CONFIG_ID,
    )
    session.add(scenario)
    session.flush()
    print(f"[created] Scenario '{name}' (id={scenario.id})")

    # Create AI scenario users for each playable node (INVENTORY/MANUFACTURER only)
    node_policies = scenario_config.get("node_policies", {})
    node_types = scenario_config.get("node_types", {})

    role_mapping = {
        "retailer": PlayerRole.RETAILER,
        "customer": PlayerRole.RETAILER,
        "wholesaler": PlayerRole.WHOLESALER,
        "distributor": PlayerRole.DISTRIBUTOR,
        "inventory": PlayerRole.DISTRIBUTOR,
        "distribution center": PlayerRole.DISTRIBUTOR,
        "manufacturer": PlayerRole.MANUFACTURER,
        "vendor": PlayerRole.SUPPLIER,
        "supplier": PlayerRole.SUPPLIER,
    }

    from sqlalchemy import text as sa_text

    for node_name in node_policies:
        node_type = node_types.get(node_name, "").lower()
        role = role_mapping.get(node_type, PlayerRole.DISTRIBUTOR)
        role_val = role.value if hasattr(role, "value") else str(role)

        # Use raw SQL to insert into actual participants table
        # (scenario_users is a view; participants has NOT NULL constraints)
        session.execute(sa_text("""
            INSERT INTO participants
                (scenario_id, name, role, type, is_ai, ai_strategy,
                 user_id, site_key, can_see_demand, strategy,
                 is_ready, agent_mode, created_at, updated_at)
            VALUES
                (:scenario_id, :name, :role, 'AI', true, :ai_strategy,
                 NULL, :site_key, false, 'MANUAL',
                 false, 'MANUAL', NOW(), NOW())
        """), {
            "scenario_id": scenario.id,
            "name": f"{node_name} ({strategy})",
            "role": role_val,
            "ai_strategy": strategy,
            "site_key": node_name,
        })

        # Create agent config
        normalized_key = node_name.lower().replace(" ", "_").replace("-", "_")
        agent_config = AgentConfig(
            scenario_id=scenario.id,
            role=normalized_key,
            agent_type=strategy,
            config={},
        )
        session.add(agent_config)

    session.flush()
    num_users = session.execute(
        sa_text("SELECT COUNT(*) FROM scenario_users WHERE scenario_id = :sid"),
        {"sid": scenario.id},
    ).scalar()
    print(f"  -> Created {num_users} AI scenario users with strategy '{strategy}'")

    return scenario


def main():
    Session = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)
    session = Session()

    try:
        admin_user_id = get_admin_user_id(session)
        print(f"Using admin_user_id={admin_user_id} for tenant {TENANT_ID}")

        # Build base config from supply chain topology
        base_config = build_scenario_config(session, CONFIG_ID)
        print(f"Built scenario config from config_id={CONFIG_ID}")
        print(f"  Nodes: {len(base_config['nodes'])}")
        print(f"  Playable nodes: {len(base_config['node_policies'])}")
        print(f"  Lanes: {len(base_config['lanes'])}")
        print(f"  Products: {len(base_config['items'])}")

        for spec in DEMO_SCENARIOS:
            create_scenario_with_agents(session, base_config, spec, admin_user_id)

        session.commit()
        print("\n[done] All Food Dist demo scenarios created successfully.")

        # List all scenarios for this tenant
        scenarios = (
            session.query(Scenario)
            .filter(Scenario.tenant_id == TENANT_ID)
            .order_by(Scenario.id)
            .all()
        )
        print(f"\nAll scenarios for Food Dist tenant (id={TENANT_ID}):")
        for s in scenarios:
            num_users = session.query(ScenarioUser).filter(
                ScenarioUser.scenario_id == s.id
            ).count()
            print(
                f"  [{s.id}] {s.name} (status={s.status}, "
                f"users={num_users}, config_id={s.supply_chain_config_id})"
            )

    except Exception as e:
        session.rollback()
        print(f"[error] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
