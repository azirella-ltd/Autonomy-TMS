#!/usr/bin/env python3
"""Seed the default Autonomy tenant, configuration, and scenarios with AI scenario_users."""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from datetime import datetime
import json
import logging
import os
import subprocess
import sys
import re
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

# Ensure the backend package is importable when running via `python backend/scripts/...`
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))

REPO_ROOT = BACKEND_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

SCRIPTS_ROOT = Path(__file__).resolve().parent
TRAINING_SCRIPTS_DIR = SCRIPTS_ROOT / "training"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "-", value.strip().lower()).strip("-")
    return slug or "config"

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base_class import SessionLocal
from app.models import Base as ModelBase
from app.models import (
    AgentConfig,
    Scenario,
    ScenarioStatus,
    Tenant,
    TransportationLane as Lane,  # Import as Lane for backwards compatibility
    Market,
    MarketDemand,
    Site,
    Node,  # Deprecated alias for Site
    NodeType,
    ScenarioUser,
    ScenarioUserAction,
    ScenarioUserRole,
    ScenarioUserStrategy,
    ScenarioUserType,
    Period,
    SupplyChainConfig,
    SupplyChainTrainingArtifact,
    SupervisorAction,
    User,
)
from app.models.supply_chain_config import ConfigLineage
# Use Product instead of Product (AWS SC migration)
from app.models.sc_entities import Product, ProductBom, InvPolicy
from app.models.user import UserTypeEnum
from app.services.supply_chain_config_service import SupplyChainConfigService
from app.core.security import get_password_hash
try:  # pragma: no cover - optional when Autonomy LLM deps are absent
    from app.services.llm_agent import check_autonomy_llm_access
except Exception:
    check_autonomy_llm_access = None
from app.services.engine import DEFAULT_STEADY_STATE_DEMAND
from app.core.time_buckets import TimeBucket, DEFAULT_START_DATE
# Temporarily disabled - requires migration to Product model
# from backend.scripts.create_regional_sc_config import ensure_multi_region_config

DEFAULT_TENANT_NAME = "Beer Scenario"
DEFAULT_TENANT_DESCRIPTION = "Default supply chain simulation scenarios"
DEFAULT_ADMIN_USERNAME = "simulation_admin"
DEFAULT_ADMIN_EMAIL = "simulation_admin@autonomy.ai"
DEFAULT_ADMIN_FULL_NAME = "Simulation Administrator"
DEFAULT_PASSWORD = os.getenv("AUTONOMY_DEFAULT_PASSWORD", "Autonomy@2026")
DEFAULT_CONFIG_NAME = "Default Beer Scenario"
INVENTORY_CONFIG_NAME = "Default Beer Scenario"
DEFAULT_SCENARIO_NAME = "Default Simulation"
DEFAULT_AGENT_TYPE = "pid_heuristic"
DEFAULT_LLM_MODEL = os.getenv("LLM_MODEL_NAME") or os.getenv("AUTONOMY_LLM_MODEL") or "qwen3-8b"
NAIVE_AGENT_SCENARIO_NAME = "Naive Agent Showcase"
NAIVE_AGENT_DESCRIPTION = "Unsupervised benchmark scenario using naive agents for every role."
PID_AGENT_SCENARIO_NAME = "PID Agent Showcase"
PID_AGENT_DESCRIPTION = "Benchmark scenario using the PID heuristic controller for every role."
PID_AGENT_STRATEGY = "pid_heuristic"
TRM_AGENT_SCENARIO_NAME = "TRM Agent Showcase"
TRM_AGENT_DESCRIPTION = "Showcase scenario using TRM (Tiny Recursive Model) agents with 7M parameter neural network and recursive refinement for fast, optimized supply chain decisions."
TRM_AGENT_STRATEGY = "trm"

# Dedicated tenant metadata for alternative DAG templates
SIX_PACK_TENANT_NAME = "Six-Pack Beer Scenario"
SIX_PACK_TENANT_DESCRIPTION = "Six-Pack supply chain simulation template"
SIX_PACK_ADMIN_USERNAME = "sixpack_admin"
SIX_PACK_ADMIN_EMAIL = "sixpack_admin@autonomy.ai"
SIX_PACK_ADMIN_FULL_NAME = "Six-Pack Administrator"

BOTTLE_TENANT_NAME = "Bottle Beer Scenario"
BOTTLE_TENANT_DESCRIPTION = "Bottle supply chain simulation template"
BOTTLE_ADMIN_USERNAME = "bottle_admin"
BOTTLE_ADMIN_EMAIL = "bottle_admin@autonomy.ai"
BOTTLE_ADMIN_FULL_NAME = "Bottle Administrator"

MULTI_ITEM_TENANT_NAME = "Multi-Product SixPack Beer Scenario"
MULTI_ITEM_TENANT_DESCRIPTION = "Multi-item Six-Pack supply chain template"
MULTI_ITEM_ADMIN_USERNAME = "multisix_admin"
MULTI_ITEM_ADMIN_EMAIL = "multisix_admin@autonomy.ai"
MULTI_ITEM_ADMIN_FULL_NAME = "Multi-Product SixPack Administrator"

THREE_FG_TENANT_NAME = "Three FG Beer Scenario"
THREE_FG_TENANT_DESCRIPTION = "Three finished-goods simulation template"
THREE_FG_ADMIN_USERNAME = "ThreeFG_admin"
THREE_FG_ADMIN_EMAIL = "ThreeFG_admin@autonomy.ai"
THREE_FG_ADMIN_FULL_NAME = "Three FG Simulation Administrator"

VARIABLE_BEER_SCENARIO_TENANT_NAME = "Variable Beer Scenario"
VARIABLE_BEER_SCENARIO_TENANT_DESCRIPTION = "Lognormal-demand simulation with three finished goods"
VARIABLE_BEER_SCENARIO_ADMIN_USERNAME = "VarSimulation_admin"
VARIABLE_BEER_SCENARIO_ADMIN_EMAIL = "VarSimulation_admin@autonomy.ai"
VARIABLE_BEER_SCENARIO_ADMIN_FULL_NAME = "Variable Simulation Administrator"

THREE_FG_TENANT_NAME = "Three FG Beer Scenario"
THREE_FG_TENANT_DESCRIPTION = "Three finished-goods simulation template"
THREE_FG_ADMIN_USERNAME = "ThreeFG_admin"
THREE_FG_ADMIN_EMAIL = "ThreeFG_admin@autonomy.ai"
THREE_FG_ADMIN_FULL_NAME = "Three FG Simulation Administrator"

VARIABLE_BEER_SCENARIO_TENANT_NAME = "Variable Beer Scenario"
VARIABLE_BEER_SCENARIO_TENANT_DESCRIPTION = "Lognormal-demand simulation with three finished goods"
VARIABLE_BEER_SCENARIO_ADMIN_USERNAME = "VarSimulation_admin"
VARIABLE_BEER_SCENARIO_ADMIN_EMAIL = "VarSimulation_admin@autonomy.ai"
VARIABLE_BEER_SCENARIO_ADMIN_FULL_NAME = "Variable Simulation Administrator"

COMPLEX_TENANT_NAME = "Complex_SC"
COMPLEX_TENANT_DESCRIPTION = (
    "Complex supply chain scenarios with multi-echelon networks and diverse suppliers."
)
COMPLEX_ADMIN_USERNAME = "complex_sc_admin"
COMPLEX_ADMIN_EMAIL = "complex_sc_admin@autonomy.ai"
COMPLEX_ADMIN_FULL_NAME = "Complex SC Administrator"
COMPLEX_HUMAN_SCENARIO_NAME = "Complex SC Human Scenario"
COMPLEX_HUMAN_SCENARIO_DESCRIPTION = (
    "Multi-region Complex_SC scenario configured for human scenario_users."
)

COMPLEX_SC_CONFIG_NAME = "Complex_SC"
COMPLEX_SC_DESCRIPTION = (
    "Complex supply chain with 10 items, two manufacturing sites, three distribution centers, "
    "three demand regions, and thirty suppliers."
)

DEFAULT_VENDOR_CAPACITY = 0

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)

DEFAULT_SIMULATION_SITE_TYPE_DEFINITIONS = [
    {
        "type": "customer",
        "label": "Customer",
        "order": 0,
        "is_required": True,
        "master_type": "customer",
    },
    {
        "type": "retailer",
        "label": "Retailer",
        "order": 1,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "wholesaler",
        "label": "Wholesaler",
        "order": 2,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "distributor",
        "label": "Distributor",
        "order": 3,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "factory",
        "label": "Factory",
        "order": 4,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "vendor",
        "label": "Vendor",
        "order": 5,
        "is_required": True,
        "master_type": "vendor",
    },
]

def _case_classic_demand_pattern() -> Dict[str, Any]:
    """Return the stepwise case demand (4 → 12 at week 15)."""

    return {
        "demand_type": "classic",
        "variability": {"type": "flat", "value": 4},
        "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
        "trend": {"type": "none", "slope": 0, "intercept": 0},
        "parameters": {
            "initial_demand": 4,
            "change_week": 15,
            "final_demand": 12,
        },
        "params": {
            "initial_demand": 4,
            "change_week": 15,
            "final_demand": 12,
        },
    }

CASE_SIMULATION_NODE_TYPE_DEFINITIONS = [
    {
        "type": "customer",
        "label": "Customer",
        "order": 0,
        "is_required": True,
        "master_type": "customer",
    },
    {
        "type": "retailer",
        "label": "Retailer",
        "order": 1,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "wholesaler",
        "label": "Wholesaler",
        "order": 2,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "distributor",
        "label": "Distributor",
        "order": 3,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "case_mfg",
        "label": "Case Mfg",
        "order": 4,
        "is_required": False,
        "master_type": "manufacturer",
    },
    {
        "type": "vendor",
        "label": "Vendor",
        "order": 5,
        "is_required": True,
        "master_type": "vendor",
    },
]

SIX_PACK_SIMULATION_NODE_TYPE_DEFINITIONS = [
    {
        "type": "customer",
        "label": "Customer",
        "order": 0,
        "is_required": True,
        "master_type": "customer",
    },
    {
        "type": "retailer",
        "label": "Retailer",
        "order": 1,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "wholesaler",
        "label": "Wholesaler",
        "order": 2,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "distributor",
        "label": "Distributor",
        "order": 3,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "case_mfg",
        "label": "Case Mfg",
        "order": 4,
        "is_required": False,
        "master_type": "manufacturer",
    },
    {
        "type": "six_pack_mfg",
        "label": "Six-Pack Mfg",
        "order": 5,
        "is_required": False,
        "master_type": "manufacturer",
    },
    {
        "type": "vendor",
        "label": "Vendor",
        "order": 6,
        "is_required": True,
        "master_type": "vendor",
    },
]

BOTTLE_SIMULATION_NODE_TYPE_DEFINITIONS = [
    {
        "type": "customer",
        "label": "Customer",
        "order": 0,
        "is_required": True,
        "master_type": "customer",
    },
    {
        "type": "retailer",
        "label": "Retailer",
        "order": 1,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "wholesaler",
        "label": "Wholesaler",
        "order": 2,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "distributor",
        "label": "Distributor",
        "order": 3,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "case_mfg",
        "label": "Case Mfg",
        "order": 4,
        "is_required": False,
        "master_type": "manufacturer",
    },
    {
        "type": "six_pack_mfg",
        "label": "Six-Pack Mfg",
        "order": 5,
        "is_required": False,
        "master_type": "manufacturer",
    },
    {
        "type": "bottle_mfg",
        "label": "Bottle Mfg",
        "order": 6,
        "is_required": False,
        "master_type": "manufacturer",
    },
    {
        "type": "vendor",
        "label": "Vendor",
        "order": 7,
        "is_required": True,
        "master_type": "vendor",
    },
]


def _lognormal_pattern_from_median_variance(median: float, variance: float) -> Dict[str, Any]:
    """Generate a lognormal demand pattern from median/variance inputs."""

    try:
        median_val = max(float(median), 1e-6)
    except (TypeError, ValueError):
        median_val = 1.0

    try:
        variance_val = max(float(variance), 0.0)
    except (TypeError, ValueError):
        variance_val = 0.0

    # For a lognormal distribution: variance = median^2 * x * (x - 1) where x = exp(sigma^2)
    ratio = variance_val / (median_val ** 2)
    x = (1.0 + math.sqrt(1.0 + 4.0 * ratio)) / 2.0
    sigma_sq = math.log(max(x, 1e-9))
    mean = median_val * math.exp(sigma_sq / 2.0)
    stddev = math.sqrt(variance_val)
    cov = stddev / mean if mean > 0 else 0.0

    return {
        "demand_type": "lognormal",
        "variability": {
            "type": "lognormal",
            "mean": mean,
            "cov": cov,
        },
        "seasonality": {"type": "none", "amplitude": 0, "period": 52, "phase": 0},
        "trend": {"type": "none", "slope": 0, "intercept": mean},
        "parameters": {"mean": mean, "cov": cov},
        "params": {"mean": mean, "cov": cov},
    }


def _normalize_user_type(value: Any) -> UserTypeEnum:
    if isinstance(value, UserTypeEnum):
        return value
    if isinstance(value, str):
        try:
            return UserTypeEnum(value)
        except ValueError:
            try:
                return UserTypeEnum[value]
            except KeyError:
                return UserTypeEnum.USER
    return UserTypeEnum.USER


def resolve_default_agent_strategy(
    preferred_strategy: Optional[str] = None,
    preferred_llm_model: Optional[str] = None,
) -> Tuple[str, Optional[str], Optional[str]]:
    """Determine which agent strategy to assign to default AI scenario_users."""

    if preferred_strategy:
        strategy = preferred_strategy.strip().lower()
        llm_model = preferred_llm_model or DEFAULT_LLM_MODEL if strategy == "llm" else None
        logger.info(
            "Using caller-specified default agent strategy '%s'%s.",
            strategy,
            f" (LLM model {llm_model})" if llm_model else "",
        )
        return strategy, llm_model, None

    if check_autonomy_llm_access:
        available, detail = check_autonomy_llm_access(model=preferred_llm_model or DEFAULT_LLM_MODEL)
    else:
        available, detail = False, "Autonomy LLM unavailable (dependencies missing)"
    if available:
        llm_model = preferred_llm_model or DEFAULT_LLM_MODEL
        logger.info("Autonomy LLM available; default AI scenario_users will use the LLM strategy (%s).", llm_model)
        return "llm", llm_model, None

    logger.warning(
        "Autonomy LLM unavailable (%s); default AI scenario_users will use '%s' strategy instead.",
        detail,
        DEFAULT_AGENT_TYPE,
    )
    return DEFAULT_AGENT_TYPE, None, detail


AUTONOMY_AGENT_SPECS = [
    {
        "name": "Autonomy DTCE Showcase",
        "agent_type": "autonomy_dtce",
        "description": "Decentralised Autonomy temporal GNN agents running per role.",
        "override_pct": None,
    },
    {
        "name": "Autonomy DTCE Central Showcase",
        "agent_type": "autonomy_dtce_central",
        "description": "Autonomy agents coordinated with a central override (10% adjustment).",
        "override_pct": 0.1,
    },
    {
        "name": "Autonomy DTCE Global Showcase",
        "agent_type": "autonomy_dtce_global",
        "description": "Single Autonomy global controller orchestrating the full supply chain.",
        "override_pct": None,
    },
    {
        "name": "Autonomy LLM Balanced Showcase",
        "agent_type": "llm_balanced",
        "description": "Autonomy LLM (balanced strategy) controlling every role with full information sharing.",
        "override_pct": None,
        "llm_model": DEFAULT_LLM_MODEL,
        "llm_strategy": "balanced",
        "can_see_demand_all": True,
    },
    {
        "name": "Autonomy LLM Conservative Showcase",
        "agent_type": "llm_conservative",
        "description": "Autonomy LLM with conservative ordering strategy for all roles.",
        "override_pct": None,
        "llm_model": DEFAULT_LLM_MODEL,
        "llm_strategy": "conservative",
        "can_see_demand_all": True,
    },
    {
        "name": "Autonomy LLM Aggressive Showcase",
        "agent_type": "llm_aggressive",
        "description": "Autonomy LLM tuned for aggressive ordering behaviour across the supply chain.",
        "override_pct": None,
        "llm_model": DEFAULT_LLM_MODEL,
        "llm_strategy": "aggressive",
        "can_see_demand_all": True,
    },
    {
        "name": "Autonomy LLM Adaptive Showcase",
        "agent_type": "llm_adaptive",
        "description": "Autonomy LLM with adaptive strategy and full supply chain visibility.",
        "override_pct": None,
        "llm_model": DEFAULT_LLM_MODEL,
        "llm_strategy": "adaptive",
        "can_see_demand_all": True,
    },
    {
        "name": "Autonomy LLM Supervised Showcase",
        "agent_type": "llm_supervised",
        "description": "Autonomy LLM agents with centralized override smoothing (10% adjustment).",
        "override_pct": 0.1,
        "llm_model": DEFAULT_LLM_MODEL,
        "llm_strategy": "balanced",
        "can_see_demand_all": True,
    },
    {
        "name": "Autonomy LLM Global Showcase",
        "agent_type": "llm_global",
        "description": "Single Autonomy LLM orchestrating decisions across the full supply chain.",
        "override_pct": None,
        "llm_model": DEFAULT_LLM_MODEL,
        "llm_strategy": "balanced",
        "can_see_demand_all": True,
    },
]

@dataclass(frozen=True)
class NodeSlot:
    key: str
    label: str
    node_type: str
    can_see_demand: bool = False


def _normalise_node_key(value: Any) -> str:
    raw = str(value or "")
    token = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw).strip().lower()
    if not token:
        return ""
    token = re.sub(r"[\s\-]+", "_", token)
    token = re.sub(r"[^0-9a-z_]+", "", token)
    token = re.sub(r"_+", "_", token).strip("_")
    return token


def _canonical_master_type(node_type: NodeType, override: Optional[str] = None) -> str:
    """Return a normalized master node type for persistence."""

    if override:
        return _normalise_node_key(override)

    if node_type == NodeType.MANUFACTURER:
        return NodeType.MANUFACTURER.value.lower()

    inventory_types = {
        NodeType.DISTRIBUTOR,
        NodeType.WHOLESALER,
        NodeType.RETAILER,
        NodeType.SUPPLIER,
        NodeType.INVENTORY,
    }
    if node_type in inventory_types:
        return NodeType.INVENTORY.value.lower()

    if node_type == NodeType.VENDOR:
        return NodeType.VENDOR.value.lower()

    if node_type == NodeType.CUSTOMER:
        return NodeType.CUSTOMER.value.lower()

    return _normalise_node_key(getattr(node_type, "value", node_type))


def _player_role_for_node_type(node_type: Optional[str]) -> ScenarioUserRole:
    mapping = {
        "retailer": ScenarioUserRole.RETAILER,
        "customer": ScenarioUserRole.RETAILER,
        "wholesaler": ScenarioUserRole.WHOLESALER,
        "distributor": ScenarioUserRole.DISTRIBUTOR,
        "manufacturer": ScenarioUserRole.MANUFACTURER,
        "supplier": ScenarioUserRole.SUPPLIER,
        "vendor": ScenarioUserRole.SUPPLIER,
    }
    canonical = (node_type or "").strip().lower()
    return mapping.get(canonical, ScenarioUserRole.MANUFACTURER)


def _player_node_key(scenario_user: ScenarioUser) -> str:
    node_key = getattr(scenario_user, "site_key", None)
    if node_key:
        return _normalise_node_key(node_key)
    role_value = getattr(scenario_user.role, "value", scenario_user.role)
    return _normalise_node_key(role_value)


def _delete_node_type_games_for_config(session: Session, config: SupplyChainConfig) -> None:
    """Remove existing Node Type scenario variants for the given supply chain configuration."""
    if not config or not getattr(config, "id", None):
        return

    node_type_games = (
        session.query(Scenario)
        .filter(Scenario.supply_chain_config_id == config.id)
        .filter(Scenario.name.ilike("%node type%"))
        .all()
    )
    for scenario in node_type_games:
        print(f"[info] Removing Node Type scenario '{scenario.name}' (id={scenario.id}) for config '{config.name}'.")
        session.query(ScenarioUserAction).filter(ScenarioUserAction.scenario_id == scenario.id).delete(synchronize_session=False)
        session.query(SupervisorAction).filter(SupervisorAction.scenario_id == scenario.id).delete(
            synchronize_session=False
        )
        session.query(AgentConfig).filter(AgentConfig.scenario_id == scenario.id).delete(synchronize_session=False)
        session.query(ScenarioUser).filter(ScenarioUser.scenario_id == scenario.id).delete(synchronize_session=False)
        session.query(Period).filter(Period.scenario_id == scenario.id).delete(synchronize_session=False)
        session.delete(scenario)
    if node_type_games:
        session.flush()


def _load_scenario_config_payload(scenario: Scenario) -> Dict[str, Any]:
    payload = scenario.config or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    return dict(payload)


def _node_label_lookup(config_payload: Dict[str, Any]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for node in config_payload.get("nodes") or []:
        name = node.get("name") or node.get("id")
        key = _normalise_node_key(name)
        if key:
            lookup[key] = str(name)
    return lookup


def _node_attributes_lookup(config_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for node in config_payload.get("nodes") or []:
        name = node.get("name") or node.get("id")
        key = _normalise_node_key(name)
        if key:
            lookup[key] = dict(node.get("attributes") or {})
    return lookup


def _iter_node_slots(config_payload: Dict[str, Any]) -> List[NodeSlot]:
    node_policies = config_payload.get("node_policies") or {}
    node_types_raw = config_payload.get("node_types") or {}
    node_types = {
        _normalise_node_key(name): str(node_type).lower()
        for name, node_type in node_types_raw.items()
    }
    label_lookup = _node_label_lookup(config_payload)
    attr_lookup = _node_attributes_lookup(config_payload)

    slots: List[NodeSlot] = []
    for raw_key in node_policies.keys():
        key = _normalise_node_key(raw_key)
        if not key:
            continue
        node_type = node_types.get(key, "")
        if node_type in {"vendor", "customer"}:
            continue
        label = label_lookup.get(key) or str(raw_key).strip() or key
        attributes = dict(attr_lookup.get(key) or {})
        can_see_demand = bool(attributes.get("can_see_demand"))
        if not can_see_demand and node_type == "retailer":
            can_see_demand = True
        slots.append(
            NodeSlot(
                key=key,
                label=label,
                node_type=node_type or "manufacturer",
                can_see_demand=can_see_demand,
            )
        )
    slots.sort(key=lambda slot: slot.label.lower())
    return slots


def _ensure_node_user(session: Session, tenant: Tenant, slot: NodeSlot) -> User:
    local_part = re.sub(r"[^0-9a-z]+", "_", slot.label.lower()).strip("_") or slot.key
    email = f"{local_part}@autonomy.ai"
    user = session.query(User).filter(User.email == email).first()
    username = email
    full_name = slot.label
    if user is None:
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            hashed_password=get_password_hash(DEFAULT_PASSWORD),
            is_active=True,
            is_superuser=False,
            user_type=UserTypeEnum.USER,
            tenant_id=tenant.id,
        )
        session.add(user)
        session.flush()
        print(f"[info] Created node user {email} for {slot.label}")
        return user

    updated = False
    if user.username != username:
        user.username = username
        updated = True
    if user.full_name != full_name:
        user.full_name = full_name
        updated = True
    if user.tenant_id != tenant.id:
        user.tenant_id = tenant.id
        updated = True
    if _normalize_user_type(user.user_type) != UserTypeEnum.USER:
        user.user_type = UserTypeEnum.USER
        updated = True
    if not user.is_active:
        user.is_active = True
        updated = True
    if user.is_superuser:
        user.is_superuser = False
        updated = True
    if updated:
        session.add(user)
        session.flush()
        print(f"[info] Updated node user {email}")
    return user


def _apply_default_lead_times(config_payload: Dict[str, Any]) -> None:
    """Force order leadtime = 1 and supply leadtime = 2 for seeded scenario payloads."""
    if not isinstance(config_payload, dict):
        return
    node_policies = config_payload.get("node_policies", {})
    if not isinstance(node_policies, dict):
        return
    initial_demand = DEFAULT_STEADY_STATE_DEMAND
    node_types = config_payload.get("node_types") or {}

    for node_key, policy in node_policies.items():
        if not isinstance(policy, dict):
            continue
        policy["order_leadtime"] = 1
        policy["supply_leadtime"] = 2
        for legacy_key in ("ship_delay", "shipDelay", "shipping_delay"):
            policy.pop(legacy_key, None)
        node_type = str(node_types.get(node_key, "")).lower()
        if node_type not in {"vendor", "customer"}:
            policy["init_inventory"] = initial_demand

    global_policy = config_payload.get("global_policy")
    if isinstance(global_policy, dict):
        global_policy["order_leadtime"] = 1
        global_policy["supply_leadtime"] = 2
        for legacy_key in ("ship_delay", "shipDelay", "shipping_delay"):
            global_policy.pop(legacy_key, None)

    sim_params = config_payload.get("simulation_parameters")
    if isinstance(sim_params, dict):
        sim_params["demand_lead_time"] = 1
        sim_params["shipping_lead_time"] = 2
        sim_params["supply_leadtime"] = 2
        for legacy_key in ("ship_delay", "shipDelay", "shipping_delay"):
            sim_params.pop(legacy_key, None)

    system_cfg = config_payload.get("system_config")
    if isinstance(system_cfg, dict):
        system_cfg["order_leadtime"] = {"min": 1, "max": 1}
        system_cfg["supply_leadtime"] = {"min": 2, "max": 2}
        for legacy_key in ("ship_delay", "shipDelay", "shipping_delay"):
            system_cfg.pop(legacy_key, None)

    demand_pattern = config_payload.get("demand_pattern", {})
    initial_demand = DEFAULT_STEADY_STATE_DEMAND
    if isinstance(demand_pattern, dict):
        params = demand_pattern.get("params") or {}
        try:
            initial_demand = max(
                0,
                int(params.get("initial_demand", initial_demand)),
            )
        except (TypeError, ValueError):
            initial_demand = DEFAULT_STEADY_STATE_DEMAND

    config_payload["initial_pipeline_shipment"] = initial_demand
    config_payload["initial_pipeline_orders"] = initial_demand

    engine_state = config_payload.get("engine_state")
    if not isinstance(engine_state, dict):
        engine_state = {}
        config_payload["engine_state"] = engine_state

    for node_key, policy in (node_policies or {}).items():
        if not isinstance(policy, dict):
            continue
        node_state = engine_state.setdefault(node_key, {})
        node_state.setdefault("backlog", 0)
        node_state.setdefault("current_step", 0)
        node_type = str(node_types.get(node_key, "")).lower()
        if node_type in {"vendor", "customer"}:
            node_state.setdefault("inventory", int(policy.get("init_inventory", 0)))
        else:
            node_state["inventory"] = int(policy.get("init_inventory", initial_demand))

        order_leadtime = max(0, int(policy.get("order_leadtime", 0)))
        supply_leadtime = max(0, int(policy.get("supply_leadtime", 0)))
        node_type = str(node_types.get(node_key, "")).lower()
        is_market_supply = node_type == "vendor"
        is_market_demand = node_type == "customer"

        if order_leadtime > 0:
            seeded_orders = [initial_demand] * order_leadtime
            node_state["info_queue"] = seeded_orders
            if is_market_demand:
                detail_seed = [{"external_demand": initial_demand}] + [{}] * (order_leadtime - 1)
            else:
                detail_seed = [{} for _ in range(order_leadtime)]
            node_state["info_detail_queue"] = detail_seed
            node_state["incoming_orders"] = initial_demand
        else:
            node_state["info_queue"] = []
            node_state["info_detail_queue"] = []
            node_state["incoming_orders"] = initial_demand if is_market_demand else 0

        if supply_leadtime > 0 and not is_market_supply:
            shipment_queue = [initial_demand] * supply_leadtime
            node_state["ship_queue"] = shipment_queue
            node_state["incoming_shipments"] = list(shipment_queue)
            try:
                base_step = int(node_state.get("current_step", 0))
            except (TypeError, ValueError):
                base_step = 0
            node_state["inbound_supply_future"] = [
                {
                    "step_number": base_step + offset + 1,
                    "quantity": initial_demand,
                }
                for offset in range(supply_leadtime)
            ]
        else:
            if not is_market_supply:
                node_state["ship_queue"] = []
                node_state["incoming_shipments"] = []
                node_state["inbound_supply_future"] = []

    sim_state = config_payload.setdefault("simulation_state", {})
    inventory_state = sim_state.setdefault("inventory", {})
    backlog_state = sim_state.setdefault("backlog", {})
    last_order_state = sim_state.setdefault("last_orders", {})
    incoming_state = sim_state.setdefault("incoming_shipments", {})

    if isinstance(node_policies, dict):
        for raw_node_key, policy in node_policies.items():
            node_key = str(raw_node_key)
            node_type = str(node_types.get(node_key, "")).lower()
            if node_type in {"vendor", "customer"}:
                continue
            order_leadtime = max(0, int(policy.get("order_leadtime", 0)))
            supply_leadtime = max(0, int(policy.get("supply_leadtime", 0)))
            if order_leadtime > 0:
                last_order_state[node_key] = initial_demand
            incoming_state[node_key] = initial_demand if supply_leadtime > 0 else 0
            inventory_state.setdefault(node_key, inventory_state.get(node_key, 0))
            backlog_state.setdefault(node_key, backlog_state.get(node_key, 0))


@dataclass
class SeedOptions:
    reset_games: bool = False
    force_dataset: bool = False
    force_training: bool = False
    run_dataset: bool = True
    run_training: bool = True
    create_autonomy_games: bool = True
    assign_ai_agents: bool = True
    preferred_agent_strategy: Optional[str] = None
    preferred_llm_model: Optional[str] = None


def mask_db_uri(uri: str) -> str:
    """Return a database URI with any password information masked."""
    if not uri:
        return uri

    try:
        url = make_url(uri)
        if url.password:
            url = url.set(password="***")
        return str(url)
    except Exception:
        return uri


def _env_flag(name: str) -> bool:
    value = os.getenv(name)
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def ensure_tenant_with_admin(
    session: Session,
    *,
    tenant_name: str,
    tenant_description: str,
    admin_username: str,
    admin_email: str,
    admin_full_name: str,
    password: str = DEFAULT_PASSWORD,
) -> Tuple[Tenant, bool]:
    """Create or update a tenant and its administrator."""

    existing_tenant = session.query(Tenant).filter(Tenant.name == tenant_name).first()
    admin_user = session.query(User).filter(User.email == admin_email).first()

    admin_created = False
    if admin_user is None:
        admin_user = User(
            username=admin_username,
            email=admin_email,
            full_name=admin_full_name,
            hashed_password=get_password_hash(password),
            is_active=True,
            is_superuser=False,
            user_type=UserTypeEnum.TENANT_ADMIN,
        )
        session.add(admin_user)
        session.flush()
        admin_created = True
    else:
        updated = False
        if admin_user.username != admin_username:
            admin_user.username = admin_username
            updated = True
        if admin_user.full_name != admin_full_name:
            admin_user.full_name = admin_full_name
            updated = True
        if admin_user.is_superuser:
            admin_user.is_superuser = False
            updated = True
        if _normalize_user_type(admin_user.user_type) != UserTypeEnum.TENANT_ADMIN:
            admin_user.user_type = UserTypeEnum.TENANT_ADMIN
            updated = True
        if not admin_user.is_active:
            admin_user.is_active = True
            updated = True
        if updated:
            session.add(admin_user)
            session.flush()

    if existing_tenant:
        if existing_tenant.description != tenant_description:
            existing_tenant.description = tenant_description
        if existing_tenant.admin_id != admin_user.id:
            existing_tenant.admin_id = admin_user.id
        session.add(existing_tenant)
        session.flush()

        if admin_user.tenant_id != existing_tenant.id:
            admin_user.tenant_id = existing_tenant.id
            session.add(admin_user)
            session.flush()

        print(
            f"[info] Tenant '{existing_tenant.name}' already exists (id={existing_tenant.id})."
        )
        return existing_tenant, False

    print(f"[info] Creating tenant '{tenant_name}' and administrator user '{admin_email}'...")

    tenant = Tenant(
        name=tenant_name,
        description=tenant_description,
        admin_id=admin_user.id,
    )
    session.add(tenant)
    session.flush()

    if admin_user.tenant_id != tenant.id:
        admin_user.tenant_id = tenant.id
        session.add(admin_user)
        session.flush()

    print(
        f"[success] Created tenant '{tenant.name}' (id={tenant.id}) and admin "
        f"'{admin_email}'{' (new user)' if admin_created else ''}."
    )

    return tenant, True


def ensure_tenant(session: Session) -> Tuple[Tenant, bool]:
    """Create the default Autonomy tenant and admin user."""

    return ensure_tenant_with_admin(
        session,
        tenant_name=DEFAULT_TENANT_NAME,
        tenant_description=DEFAULT_TENANT_DESCRIPTION,
        admin_username=DEFAULT_ADMIN_USERNAME,
        admin_email=DEFAULT_ADMIN_EMAIL,
        admin_full_name=DEFAULT_ADMIN_FULL_NAME,
        password=DEFAULT_PASSWORD,
    )


def ensure_named_tenant(
    session: Session,
    *,
    name: str,
    description: str,
    admin_username: str,
    admin_email: str,
    admin_full_name: str,
) -> Tenant:
    tenant, _ = ensure_tenant_with_admin(
        session,
        tenant_name=name,
        tenant_description=description,
        admin_username=admin_username,
        admin_email=admin_email,
        admin_full_name=admin_full_name,
        password=DEFAULT_PASSWORD,
    )
    return tenant


def ensure_supply_chain_config(
    session: Session,
    tenant: Tenant,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    demand_pattern_override: Optional[Dict[str, Any]] = None,
    factory_master_type: Optional[str] = None,
    manufacturer_master_type: Optional[str] = None,
) -> SupplyChainConfig:
    """Ensure the default supply chain configuration exists for the tenant."""

    base_query = session.query(SupplyChainConfig).filter(
        SupplyChainConfig.tenant_id == tenant.id
    )

    config: Optional[SupplyChainConfig]
    if name:
        config = base_query.filter(SupplyChainConfig.name == name).first()
    else:
        config = base_query.order_by(SupplyChainConfig.id.asc()).first()

    override_payload = json.loads(json.dumps(demand_pattern_override)) if demand_pattern_override else None

    desired_factory_master_type = (
        factory_master_type or manufacturer_master_type or NodeType.INVENTORY.value
    )
    desired_factory_master_type = (
        _normalise_node_key(desired_factory_master_type) or "inventory"
    )

    if config:
        print(
            f"[info] Supply chain configuration already exists (id={config.id})."
        )
        updated = False
        if config.tenant_id != tenant.id:
            config.tenant_id = tenant.id
            updated = True
        desired_creator = tenant.admin_id
        if desired_creator and config.created_by != desired_creator:
            config.created_by = desired_creator
            updated = True
        if name and config.name != name:
            config.name = name
            updated = True
        if description and config.description != description:
            config.description = description
            updated = True
        _ensure_default_topology(
            session, config, factory_master_type=desired_factory_master_type
        )
        _ensure_factory_node_type_definition(
            session, config, desired_factory_master_type
        )
        items = session.query(Product).filter(Product.config_id == config.id).all()
        market = (
            session.query(Market)
            .filter(Market.config_id == config.id)
            .order_by(Market.id.asc())
            .first()
            or Market(config_id=config.id, name="Default Market", description="Primary demand market")
        )
        session.add(market)
        session.flush()

        # Ensure the Case→Six-Pack BOM stays aligned with the current item ids.
        case_item = next((i for i in items if str(i.name).lower().startswith("case")), None)
        six_pack_item = next((i for i in items if "six-pack" in str(i.name).lower()), None)
        factory_node = next(
            (
                node
                for node in session.query(Node).filter(Node.config_id == config.id).all()
                if _normalise_node_key(getattr(node, "dag_type", None) or node.name)
                in {"factory", "manufacturer", "case_mfg"}
            ),
            None,
        )
        if factory_node and case_item and six_pack_item:
            attrs = dict(getattr(factory_node, "attributes", {}) or {})
            bom = dict(attrs.get("bill_of_materials", {}) or {})
            bom[str(case_item.id)] = {str(six_pack_item.id): 4}
            attrs["bill_of_materials"] = bom
            factory_node.attributes = attrs
            session.add(factory_node)

        zero_pattern = {
            "demand_type": "constant",
            "variability": {"type": "flat", "value": 0},
            "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
            "trend": {"type": "none", "slope": 0, "intercept": 0},
            "parameters": {"value": 0},
            "params": {"value": 0},
        }
        base_pattern = override_payload or {
            "demand_type": "constant",
            "variability": {"type": "flat", "value": 4},
            "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
            "trend": {"type": "none", "slope": 0, "intercept": 0},
            "parameters": {"value": 4},
            "params": {"value": 4},
        }
        demand_items = [itm for itm in items if str(itm.name).lower().startswith("case")]
        if not demand_items and items:
            demand_items = [items[0]]

        demand_item_ids = [itm.id for itm in demand_items]
        for item_obj in items:
            demand_row = (
                session.query(MarketDemand)
                .filter(
                    MarketDemand.config_id == config.id,
                    MarketDemand.product_id == item_obj.id,
                    MarketDemand.market_id == market.id,
                )
                .first()
            )
            if not demand_row:
                demand_row = MarketDemand(
                    config_id=config.id,
                    product_id=item_obj.id,
                    market_id=market.id,
                )
            demand_row.demand_pattern = base_pattern if item_obj.id in demand_item_ids else zero_pattern
            session.add(demand_row)
        _apply_default_supply_chain_settings(session, config)
        _apply_site_type_definitions(session, config, DEFAULT_SIMULATION_SITE_TYPE_DEFINITIONS)
        if override_payload:
            _apply_market_demand_override(session, config, override_payload)
            updated = True
        _reseed_product_site_configs(session, config)
        if updated:
            session.add(config)
            session.flush()
        return config
    # Create a new configuration
    if name == INVENTORY_CONFIG_NAME:
        return _create_inventory_only_config(session, tenant, name=name, description=description, override_payload=override_payload)

    print("[info] Creating default supply chain configuration...")
    config = SupplyChainConfig(
        name=name or DEFAULT_CONFIG_NAME,
        description=description or "Default supply chain configuration",
        created_by=tenant.admin_id,
        tenant_id=tenant.id,
        is_active=True,
        time_bucket=TimeBucket.WEEK,
    )
    session.add(config)
    session.flush()

    # Items: Case is demanded; Six-Pack is supplied from Market Supply into Case manufacturing.
    case_item = Product(
        config_id=config.id,
        id="Case",
        description="Standard case product",
    )
    six_pack_item = Product(
        config_id=config.id,
        id="Six-Pack",
        description="Standard six-pack product",
    )
    session.add(case_item)
    session.add(six_pack_item)
    session.flush()

    # Nodes and master types
    node_specs = [
        ("Vendor", NodeType.VENDOR, "vendor", "vendor"),
        (
            "Factory",
            NodeType.MANUFACTURER,
            "factory",
            _normalise_node_key(desired_factory_master_type) or "inventory",
        ),
        ("Distributor", NodeType.DISTRIBUTOR, "distributor", "inventory"),
        ("Wholesaler", NodeType.WHOLESALER, "wholesaler", "inventory"),
        ("Retailer", NodeType.RETAILER, "retailer", "inventory"),
        ("Customer", NodeType.CUSTOMER, "customer", "customer"),
    ]
    nodes: Dict[NodeType, Node] = {}
    for node_name, node_type, dag_type, master_type in node_specs:
        node = Node(
            config_id=config.id,
            name=node_name,
            type=dag_type,
        )
        node.dag_type = dag_type
        node.master_type = master_type
        session.add(node)
        session.flush()
        nodes[node_type] = node

    market_supply_node = nodes.get(NodeType.VENDOR)
    _ensure_market_supply_attributes(market_supply_node)
    if market_supply_node:
        session.add(market_supply_node)

    factory_node = nodes.get(NodeType.MANUFACTURER)
    if factory_node:
        attrs = dict(getattr(factory_node, "attributes", {}) or {})
        bom = attrs.get("bill_of_materials", {})
        bom[str(case_item.id)] = {str(six_pack_item.id): 4}
        attrs["bill_of_materials"] = bom
        _ensure_manufacturing_metadata(factory_node, [case_item], capacity_hours=7 * 24, leadtime=0)
        factory_node.attributes = attrs
        session.add(factory_node)

    lane_specs = [
        (NodeType.VENDOR, NodeType.MANUFACTURER),
        (NodeType.MANUFACTURER, NodeType.DISTRIBUTOR),
        (NodeType.DISTRIBUTOR, NodeType.WHOLESALER),
        (NodeType.WHOLESALER, NodeType.RETAILER),
        (NodeType.RETAILER, NodeType.CUSTOMER),
    ]
    for upstream_type, downstream_type in lane_specs:
        lane = Lane(
            config_id=config.id,
            from_site_id=nodes[upstream_type].id,
            to_site_id=nodes[downstream_type].id,
            capacity=9999,
            lead_time_days={"min": 1, "max": 5},
            demand_lead_time={"type": "deterministic", "value": 1},
            supply_lead_time={"type": "uniform", "minimum": 1, "maximum": 5},
        )
        session.add(lane)

    session.flush()

    for node in nodes.values():
        if str(node.master_type or "").lower() in {"vendor", "customer"}:
            continue
        for item in (case_item, six_pack_item):
            node_config = InvPolicy(
                product_id=item.id,
                site_id=node.id,
                inventory_target_range={"min": 10, "max": 20},
                initial_inventory_range={"min": 5, "max": 30},
                holding_cost_range={"min": 1.0, "max": 5.0},
                backlog_cost_range={"min": 5.0, "max": 10.0},
                selling_price_range={"min": 25.0, "max": 50.0},
            )
            session.add(node_config)

    market = Market(
        config_id=config.id,
        name="Default Market",
        description="Primary demand market",
    )
    session.add(market)
    session.flush()

    default_pattern = override_payload or {
        "demand_type": "constant",
        "variability": {"type": "flat", "value": 4},
        "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
        "trend": {"type": "none", "slope": 0, "intercept": 0},
        "parameters": {"value": 4},
        "params": {"value": 4},
    }

    # Create demand rows for all items (Case gets real demand; Six-Pack gets zero by default)
    zero_pattern = {
        "demand_type": "constant",
        "variability": {"type": "flat", "value": 0},
        "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
        "trend": {"type": "none", "slope": 0, "intercept": 0},
        "parameters": {"value": 0},
        "params": {"value": 0},
    }
    demand_specs = {
        case_item.id: default_pattern,
        six_pack_item.id: zero_pattern,
    }
    for item_id, pattern in demand_specs.items():
        session.add(
            MarketDemand(
                config_id=config.id,
                product_id=item_id,
                market_id=market.id,
                demand_pattern=pattern,
            )
        )
    session.flush()

    print(
        f"[success] Created supply chain configuration (id={config.id}) for tenant {tenant.id}."
    )
    _apply_default_supply_chain_settings(session, config)
    _apply_site_type_definitions(session, config, DEFAULT_SIMULATION_SITE_TYPE_DEFINITIONS)
    _ensure_factory_node_type_definition(
        session, config, desired_factory_master_type
    )
    if override_payload:
        _apply_market_demand_override(session, config, override_payload)
    _reseed_product_site_configs(session, config)
    return config


def ensure_three_fg_inventory_config(
    session: Session,
    tenant: Tenant,
    *,
    name: str = "Three FG Beer Scenario",
    description: str = "Inventory-only simulation with three finished goods (Lager, IPA, Dark).",
    demand_pattern_override: Optional[Dict[str, Any]] = None,
) -> SupplyChainConfig:
    """Create or update an inventory-only config with three finished goods."""

    config = (
        session.query(SupplyChainConfig)
        .filter(SupplyChainConfig.tenant_id == tenant.id, SupplyChainConfig.name == name)
        .first()
    )
    if not config:
        config = SupplyChainConfig(
            name=name,
            description=description,
            tenant_id=tenant.id,
            time_bucket=TimeBucket.WEEK,
            is_active=True,
        )
        session.add(config)
        session.flush()

    config.description = description
    _ensure_default_topology(session, config, factory_master_type=NodeType.INVENTORY.value)

    desired_items = [
        ("Lager Case", "Lager finished good"),
        ("IPA Case", "IPA finished good"),
        ("Dark Case", "Dark finished good"),
    ]
    desired_names = {nm.lower(): (nm, desc) for nm, desc in desired_items}

    # Remove items not in the desired set
    for item in session.query(Product).filter(Product.config_id == config.id).all():
        if item.name.lower() in desired_names:
            continue
        session.query(MarketDemand).filter(MarketDemand.product_id == item.id).delete(synchronize_session=False)
        session.query(InvPolicy).filter(InvPolicy.product_id == item.id).delete(synchronize_session=False)
        session.delete(item)
    session.flush()

    items: Dict[str, Product] = {}
    for name_val, desc_val in desired_items:
        item = (
            session.query(Product)
            .filter(Product.config_id == config.id, Product.name == name_val)
            .first()
        )
        if not item:
            item = Product(id=name_val, description=desc_val)
            session.add(item)
            session.flush()
        else:
            item.description = desc_val
            session.add(item)
        items[name_val] = item

    nodes = session.query(Node).filter(Node.config_id == config.id).all()
    for node in nodes:
        master = str(node.master_type or "").lower()
        if master in {"vendor", "customer"}:
            continue
        for item in items.values():
            exists = (
                session.query(InvPolicy)
                .filter(InvPolicy.product_id == item.id, InvPolicy.site_id == node.id)
                .first()
            )
            if not exists:
                session.add(InvPolicy(product_id=item.id, site_id=node.id, **DEFAULT_PRODUCT_SITE_RANGES))

    market = (
        session.query(Market)
        .filter(Market.config_id == config.id, Market.name == f"{name} Market")
        .first()
    )
    if not market:
        market = Market(
            config_id=config.id,
            name=f"{name} Market",
            description="Primary demand market",
        )
        session.add(market)
        session.flush()
    else:
        market.description = "Primary demand market"
        session.add(market)
        session.flush()

    pattern = json.loads(json.dumps(demand_pattern_override)) if demand_pattern_override else _case_classic_demand_pattern()
    for item in items.values():
        demand = (
            session.query(MarketDemand)
            .filter(
                MarketDemand.config_id == config.id,
                MarketDemand.product_id == item.id,
                MarketDemand.market_id == market.id,
            )
            .first()
        )
        if not demand:
            demand = MarketDemand(
                config_id=config.id,
                product_id=item.id,
                market_id=market.id,
            )
        demand.demand_pattern = pattern
        session.add(demand)

    session.flush()
    _ensure_lane_lead_times(session, config, overwrite_existing=True)
    _apply_site_type_definitions(session, config, DEFAULT_SIMULATION_SITE_TYPE_DEFINITIONS)
    _ensure_factory_node_type_definition(session, config, NodeType.INVENTORY.value)
    _reseed_product_site_configs(session, config)
    return config


def _create_inventory_only_config(
    session: Session,
    tenant: Tenant,
    *,
    name: Optional[str],
    description: Optional[str],
    override_payload: Optional[Dict[str, Any]],
) -> SupplyChainConfig:
    """Create an inventory-only default simulation config (no BOM; factory acts as inventory).

    This is the ROOT config for the simulation lineage chain.
    Lineage: Default Beer Scenario (ROOT)
    """
    print("[info] Creating inventory-only supply chain configuration...")
    config = SupplyChainConfig(
        name=name or INVENTORY_CONFIG_NAME,
        description=description or "Inventory-only supply chain configuration",
        created_by=tenant.admin_id,
        tenant_id=tenant.id,
        is_active=True,
        time_bucket=TimeBucket.WEEK,
        site_type_definitions=DEFAULT_SIMULATION_SITE_TYPE_DEFINITIONS,
    )
    session.add(config)
    session.flush()

    # Set base_config_id to self (this is the ROOT of the lineage tree)
    config.base_config_id = config.id
    session.add(config)
    session.flush()

    # Populate lineage (just self-reference for root)
    _populate_config_lineage(session, config)

    # Items: only Case
    case_item = Product(
        config_id=config.id,
        id="Case",
        description="Standard case product",
    )
    session.add(case_item)
    session.flush()

    # Nodes: all internal nodes use INVENTORY master/type; Factory keeps DAG identity but uses the inventory master type
    node_specs = [
        ("Vendor", NodeType.VENDOR, "vendor", "vendor"),
        ("Factory", NodeType.MANUFACTURER, "factory", "inventory"),
        ("Distributor", NodeType.DISTRIBUTOR, "distributor", "inventory"),
        ("Wholesaler", NodeType.WHOLESALER, "wholesaler", "inventory"),
        ("Retailer", NodeType.RETAILER, "retailer", "inventory"),
        ("Customer", NodeType.CUSTOMER, "customer", "customer"),
    ]
    nodes: Dict[str, Node] = {}
    for name_val, node_type, master_type, dag_key in node_specs:
        node = Node(
            config_id=config.id,
            name=name_val,
            type=dag_key,
            master_type=master_type,
            dag_type=dag_key,
        )
        session.add(node)
        session.flush()
        nodes[dag_key] = node

    market_supply_node = nodes.get("vendor")
    _ensure_market_supply_attributes(market_supply_node)
    if market_supply_node:
        session.add(market_supply_node)

    # Lanes (linear DAG): Market Supply -> Factory -> Distributor -> Wholesaler -> Retailer -> Market Demand
    lane_order = [
        ("vendor", "factory"),
        ("factory", "distributor"),
        ("distributor", "wholesaler"),
        ("wholesaler", "retailer"),
        ("retailer", "customer"),
    ]
    for upstream_key, downstream_key in lane_order:
        upstream_node = nodes.get(upstream_key)
        downstream_node = nodes.get(downstream_key)
        if not upstream_node or not downstream_node:
            continue
        lane = Lane(
            config_id=config.id,
            from_site_id=upstream_node.id,
            to_site_id=downstream_node.id,
            capacity=9999,
            demand_lead_time={"type": "deterministic", "value": 1},
            supply_lead_time={"type": "deterministic", "value": 2},
        )
        session.add(lane)

    session.flush()

    # Product-node configs: Case for every internal node (excluding Market Supply/Demand)
    for node in nodes.values():
        if str(node.master_type or "").lower() in {"vendor", "customer"}:
            continue
        node_config = InvPolicy(
            product_id=case_item.id,
            site_id=node.id,
            inventory_target_range={"min": 10, "max": 20},
            initial_inventory_range={"min": 5, "max": 30},
            holding_cost_range={"min": 1.0, "max": 5.0},
            backlog_cost_range={"min": 5.0, "max": 10.0},
            selling_price_range={"min": 25.0, "max": 50.0},
        )
        session.add(node_config)

    market = Market(
        config_id=config.id,
        name="Default Market",
        description="Primary demand market",
    )
    session.add(market)
    session.flush()

    demand_pattern = override_payload or {
        "demand_type": "constant",
        "variability": {"type": "flat", "value": 4},
        "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
        "trend": {"type": "none", "slope": 0, "intercept": 0},
        "parameters": {"value": 4},
        "params": {"value": 4},
    }
    session.add(
        MarketDemand(
            config_id=config.id,
            product_id=case_item.id,
            market_id=market.id,
            demand_pattern=demand_pattern,
        )
    )
    session.flush()

    print(f"[success] Created inventory-only supply chain configuration (id={config.id}) for tenant {tenant.id}.")
    _apply_default_supply_chain_settings(session, config)
    _reseed_product_site_configs(session, config)
    return config


def _ensure_default_topology(
    session: Session,
    config: SupplyChainConfig,
    *,
    factory_master_type: str = NodeType.INVENTORY.value,
) -> None:
    """Ensure default simulation config includes Market Demand/Supply nodes and canonical lanes."""

    factory_master_token = _normalise_node_key(factory_master_type) or "inventory"
    allowed_keys = {
        "vendor": ("Vendor", NodeType.VENDOR.value.lower()),
        "factory": ("Factory", factory_master_token),
        "distributor": ("Distributor", NodeType.INVENTORY.value.lower()),
        "wholesaler": ("Wholesaler", NodeType.INVENTORY.value.lower()),
        "retailer": ("Retailer", NodeType.INVENTORY.value.lower()),
        "customer": ("Customer", NodeType.CUSTOMER.value.lower()),
    }
    legacy_aliases = {
        "case_mfg": "factory",
        "manufacturer": "factory",
        NodeType.MANUFACTURER.value.lower(): "factory",
    }
    grouped_nodes: Dict[str, List[Node]] = defaultdict(list)
    for node in session.query(Node).filter(Node.config_id == config.id).all():
        raw_key = _normalise_node_key(getattr(node, "dag_type", None) or node.name)
        canonical_key = legacy_aliases.get(raw_key, raw_key)
        grouped_nodes[canonical_key].append(node)

    for canonical_key, nodes_for_key in grouped_nodes.items():
        if canonical_key not in allowed_keys:
            for node in nodes_for_key:
                session.query(Lane).filter(
                    (Lane.from_site_id == node.id) | (Lane.to_site_id == node.id)
                ).delete(synchronize_session=False)
                session.query(InvPolicy).filter(InvPolicy.site_id == node.id).delete(
                    synchronize_session=False
                )
                session.delete(node)
            continue

        def _priority(node: Node) -> Tuple[int, int]:
            dag_matches = int(_normalise_node_key(getattr(node, "dag_type", None) or "") == canonical_key)
            name_matches = int(_normalise_node_key(node.name) == canonical_key)
            return (dag_matches + name_matches, node.id or 0)

        nodes_for_key.sort(key=_priority, reverse=True)
        keep_node = nodes_for_key[0]
        for duplicate in nodes_for_key[1:]:
            session.query(Lane).filter(
                (Lane.from_site_id == duplicate.id) | (Lane.to_site_id == duplicate.id)
            ).delete(synchronize_session=False)
            session.query(InvPolicy).filter(InvPolicy.site_id == duplicate.id).delete(
                synchronize_session=False
            )
            session.delete(duplicate)

        desired_name, desired_master = allowed_keys[canonical_key]
        current_type = _normalise_node_key(getattr(keep_node, "type", None) or keep_node.name)
        if (
            canonical_key != _normalise_node_key(getattr(keep_node, "dag_type", None) or "")
            or canonical_key != current_type
            or _normalise_node_key(keep_node.name) != _normalise_node_key(desired_name)
            or _normalise_node_key(keep_node.master_type or "") != desired_master
        ):
            keep_node.name = desired_name
            keep_node.type = canonical_key
            keep_node.dag_type = canonical_key
            keep_node.master_type = desired_master
            session.add(keep_node)
    session.flush()

    def _get_or_create(node_type: NodeType, name: str, master_type: str, dag_key: str) -> Node:
        node = (
            session.query(Node)
            .filter(Node.config_id == config.id, Node.dag_type == dag_key)
            .first()
        )
        if not node:
            node = (
                session.query(Node)
                .filter(Node.config_id == config.id, Node.name == name, Node.type == node_type)
                .first()
            )
        if not node:
            node = Node(
                config_id=config.id,
                name=name,
                type=dag_key,
                master_type=master_type,
                dag_type=dag_key,
            )
            session.add(node)
            session.flush()
        else:
            node.name = name
            node.type = dag_key
            node.master_type = master_type
            node.dag_type = dag_key
        session.add(node)
        return node

    market_supply = _get_or_create(
        NodeType.VENDOR,
        "Vendor",
        "vendor",
        "vendor",
    )
    _ensure_market_supply_attributes(market_supply)
    session.add(market_supply)
    factory = _get_or_create(
        NodeType.MANUFACTURER,
        "Factory",
        factory_master_token,
        "factory",
    )
    distributor = _get_or_create(
        NodeType.DISTRIBUTOR,
        "Distributor",
        "inventory",
        "distributor",
    )
    wholesaler = _get_or_create(
        NodeType.WHOLESALER,
        "Wholesaler",
        "inventory",
        "wholesaler",
    )
    retailer = _get_or_create(
        NodeType.RETAILER,
        "Retailer",
        "inventory",
        "retailer",
    )
    market_demand = _get_or_create(
        NodeType.CUSTOMER,
        "Customer",
        "customer",
        "customer",
    )

    # Products: Case only (inventory-only default simulation config)
    # Using AWS SC Product model instead of legacy Product
    case_product = (
        session.query(Product)
        .filter(Product.config_id == config.id, Product.id.in_(["CASE", "Case", "Case of Beer"]))
        .order_by(Product.id.asc())
        .first()
    )
    if not case_product:
        case_product = Product(
            id="CASE",
            description="Standard case product",
            config_id=config.id,
            company_id="DEFAULT",
            product_type="finished_good",
            base_uom="EA",
            unit_cost=10.0,
            unit_price=12.0,
            is_active="true"
        )
        session.add(case_product)
        session.flush()

    desired_lanes = [
        (market_supply.id, factory.id),
        (factory.id, distributor.id),
        (distributor.id, wholesaler.id),
        (wholesaler.id, retailer.id),
        (retailer.id, market_demand.id),
    ]
    existing = {
        (lane.from_site_id, lane.to_site_id)
        for lane in session.query(Lane).filter(Lane.config_id == config.id).all()
    }
    for upstream_id, downstream_id in desired_lanes:
        if (upstream_id, downstream_id) in existing:
            continue
        lane = Lane(
            config_id=config.id,
            from_site_id=upstream_id,
            to_site_id=downstream_id,
            capacity=9999,
            lead_time_days={"min": 1, "max": 5},
            demand_lead_time={"type": "deterministic", "value": 1},
            supply_lead_time={"type": "deterministic", "value": 2},
        )
        session.add(lane)
    session.flush()
    _ensure_lane_lead_times(session, config)


def _apply_default_supply_chain_settings(session: Session, config: SupplyChainConfig) -> None:
    """Normalize supply chain configuration settings to project defaults."""

    config.is_active = True
    config.description = config.description or "Default supply chain configuration"
    session.add(config)

    nodes = session.query(Node).filter(Node.config_id == config.id).all()

    default_inventory_range = {"min": 10, "max": 20}
    initial_inventory_range = {"min": 5, "max": 5}
    holding_cost_range = {"min": 0.5, "max": 0.5}
    backlog_cost_range = {"min": 5.0, "max": 5.0}
    selling_price_range = {"min": 25.0, "max": 25.0}

    for node in nodes:
        for node_config in node.inv_policies:
            node_config.inventory_target_range = dict(default_inventory_range)
            node_config.initial_inventory_range = dict(initial_inventory_range)
            node_config.holding_cost_range = dict(holding_cost_range)
            node_config.backlog_cost_range = dict(backlog_cost_range)
            node_config.selling_price_range = dict(selling_price_range)
            session.add(node_config)

    lanes = session.query(Lane).filter(Lane.config_id == config.id).all()
    for lane in lanes:
        lane.capacity = lane.capacity or 9999
        lane.lead_time_days = {"min": 2, "max": 2}
        lane.demand_lead_time = {"type": "deterministic", "value": 1}
        lane.supply_lead_time = {"type": "deterministic", "value": 2}
        session.add(lane)

    _ensure_lane_lead_times(session, config)

    items_by_id = {
        itm.id: itm for itm in session.query(Product).filter(Product.config_id == config.id).all()
    }
    market_demands = session.query(MarketDemand).filter(MarketDemand.config_id == config.id).all()
    classic_pattern = {
        "demand_type": "classic",
        "variability": {"type": "flat", "value": 4},
        "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
        "trend": {"type": "none", "slope": 0, "intercept": 0},
        "parameters": {
            "initial_demand": 4,
            "change_week": 15,
            "final_demand": 12,
        },
        "params": {
            "initial_demand": 4,
            "change_week": 15,
            "final_demand": 12,
        },
    }
    zero_pattern = {
        "demand_type": "constant",
        "variability": {"type": "flat", "value": 0},
        "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
        "trend": {"type": "none", "slope": 0, "intercept": 0},
        "parameters": {"value": 0},
        "params": {"value": 0},
    }
    for md in market_demands:
        item_obj = items_by_id.get(md.product_id)
        use_classic = item_obj and item_obj.id.lower().startswith("case")
        md.demand_pattern = classic_pattern if use_classic else zero_pattern
        session.add(md)

    session.flush()


def _ensure_lane_lead_times(
    session: Session,
    config: SupplyChainConfig,
    *,
    demand_lead_time: int = 1,
    supply_lead_time: int = 2,
    overwrite_existing: bool = False,
) -> None:
    """Ensure every lane in the config has explicit order/supply lead time payloads."""

    desired_demand = {
        "type": "deterministic",
        "value": demand_lead_time,
    }
    desired_supply = {
        "type": "deterministic",
        "value": supply_lead_time,
    }
    desired_demand_serial = json.dumps(desired_demand, sort_keys=True)
    desired_supply_serial = json.dumps(desired_supply, sort_keys=True)
    desired_legacy = {"min": supply_lead_time, "max": supply_lead_time}

    def _payload_serial(payload: Any) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        try:
            return json.dumps(payload, sort_keys=True)
        except (TypeError, ValueError):
            return None

    any_updates = False
    for lane in session.query(Lane).filter(Lane.config_id == config.id).all():
        lane_updated = False
        current_demand_serial = _payload_serial(getattr(lane, "demand_lead_time", None))
        current_supply_serial = _payload_serial(getattr(lane, "supply_lead_time", None))

        if overwrite_existing:
            if current_demand_serial != desired_demand_serial:
                lane.demand_lead_time = dict(desired_demand)
                lane_updated = True
        elif current_demand_serial is None:
            lane.demand_lead_time = dict(desired_demand)
            lane_updated = True

        if overwrite_existing:
            if current_supply_serial != desired_supply_serial:
                lane.supply_lead_time = dict(desired_supply)
                lane_updated = True
        elif current_supply_serial is None:
            lane.supply_lead_time = dict(desired_supply)
            lane_updated = True

        if overwrite_existing:
            legacy = getattr(lane, "lead_time_days", None) or {}
            if (
                not isinstance(legacy, dict)
                or legacy.get("min") != supply_lead_time
                or legacy.get("max") != supply_lead_time
            ):
                lane.lead_time_days = dict(desired_legacy)
                lane_updated = True

        if lane_updated:
            session.add(lane)
            any_updates = True

    if any_updates:
        session.flush()


def _ensure_factory_node_type_definition(
    session: Session,
    config: SupplyChainConfig,
    master_type: Optional[str] = "inventory",
) -> None:
    """Ensure the Factory DAG node type is present with the desired master type."""

    existing = getattr(config, "site_type_definitions", None)
    base_defs = []
    if isinstance(existing, list):
        base_defs = json.loads(json.dumps(existing))
    else:
        base_defs = json.loads(json.dumps(_default_site_type_definitions()))

    normalized_master = str(master_type or "inventory").strip().lower() or "inventory"
    updated = False
    factory_entry: Optional[Dict[str, Any]] = None
    working: List[Dict[str, Any]] = []
    for entry in base_defs:
        entry_type = str(entry.get("type") or "").strip().lower()
        if entry_type in {"factory", "manufacturer", "case_mfg"}:
            if factory_entry is None:
                factory_entry = dict(entry)
                factory_entry["type"] = "factory"
                factory_entry["label"] = "Factory"
                factory_entry["master_type"] = normalized_master
                updated = updated or factory_entry != entry
                working.append(factory_entry)
            else:
                updated = True
            continue
        working.append(entry)

    if factory_entry is None:
        working.append(
            {
                "type": "factory",
                "label": "Factory",
                "order": len(working),
                "is_required": False,
                "master_type": normalized_master,
            }
        )
        updated = True
    else:
        if str(factory_entry.get("master_type", "")).strip().lower() != normalized_master:
            factory_entry["master_type"] = normalized_master
            updated = True

    if updated:
        config.site_type_definitions = working
        session.add(config)
        session.flush()


def _ensure_manufacturer_master_type_definition(
    session: Session,
    config: SupplyChainConfig,
    master_type: Optional[str] = "manufacturer",
) -> None:
    """Ensure manufacturer-style node types retain the desired master type."""

    existing = getattr(config, "site_type_definitions", None)
    base_defs = []
    if isinstance(existing, list):
        base_defs = json.loads(json.dumps(existing))
    else:
        base_defs = json.loads(json.dumps(_default_site_type_definitions()))

    normalized_master = str(master_type or "manufacturer").strip().lower() or "manufacturer"
    updated = False
    has_manufacturer = False
    working: List[Dict[str, Any]] = []
    for entry in base_defs:
        entry_type = str(entry.get("type") or "").strip().lower()
        if entry_type in {"manufacturer", "case_mfg"}:
            has_manufacturer = True
            if str(entry.get("master_type") or "").strip().lower() != normalized_master:
                entry["master_type"] = normalized_master
                updated = True
            if entry_type == "manufacturer" and str(entry.get("label") or "").strip().lower() != "manufacturer":
                entry["label"] = "Manufacturer"
                updated = True
        working.append(entry)

    if not has_manufacturer:
        working.append(
            {
                "type": "manufacturer",
                "label": "Manufacturer",
                "order": len(working),
                "is_required": False,
                "master_type": normalized_master,
            }
        )
        updated = True

    if updated:
        config.site_type_definitions = working
        session.add(config)
        session.flush()


def _apply_site_type_definitions(
    session: Session,
    config: SupplyChainConfig,
    definitions: Sequence[Dict[str, Any]],
) -> None:
    """Persist the provided node type definitions for the configuration."""

    if not definitions:
        return
    payload = json.loads(json.dumps(definitions))
    if getattr(config, "site_type_definitions", None) == payload:
        return
    config.site_type_definitions = payload
    session.add(config)
    session.flush()


def _ensure_market_supply_attributes(
    node: Optional[Node],
    *,
    default_capacity: int = DEFAULT_VENDOR_CAPACITY,
) -> None:
    """Ensure Market Supply nodes carry required supply capacity metadata."""

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
    node.attributes = attrs


def _ensure_manufacturing_metadata(
    manufacturer: Node,
    finished_items: Sequence[Product],
    capacity_hours: int = 7 * 24,
    leadtime: int = 0,
) -> None:
    """Attach default manufacturing fields to a manufacturer node."""

    attrs = dict(getattr(manufacturer, "attributes", {}) or {})
    attrs.setdefault("manufacturing_leadtime", leadtime)
    attrs.setdefault("manufacturing_capacity_hours", capacity_hours)
    util_map = dict(attrs.get("capacity_utilization_by_item") or {})
    for item in finished_items:
        util_map[str(item.id)] = util_map.get(str(item.id), 0)
    attrs["capacity_utilization_by_item"] = util_map
    manufacturer.attributes = attrs


def _apply_market_demand_override(
    session: Session, config: SupplyChainConfig, pattern: Dict[str, Any]
) -> None:
    """Apply a custom market demand pattern to all retailer demand rows."""

    if not pattern:
        return

    market_demands = session.query(MarketDemand).filter(MarketDemand.config_id == config.id).all()
    for md in market_demands:
        md.demand_pattern = json.loads(json.dumps(pattern))
        session.add(md)

    session.flush()


DEFAULT_PRODUCT_SITE_RANGES = {
    "inventory_target_range": {"min": 5, "max": 20},
    "initial_inventory_range": {"min": 2, "max": 10},
    "holding_cost_range": {"min": 0.5, "max": 5.0},
    "backlog_cost_range": {"min": 5.0, "max": 10.0},
    "selling_price_range": {"min": 25.0, "max": 50.0},
}


def _is_zero_demand_pattern(pattern: Any) -> bool:
    """Return True when a MarketDemand pattern clearly encodes zero demand."""

    if not isinstance(pattern, dict):
        return False

    def _numeric_values(payload: Any) -> List[float]:
        values: List[float] = []
        if isinstance(payload, dict):
            for value in payload.values():
                values.extend(_numeric_values(value))
        elif isinstance(payload, (int, float)):
            try:
                values.append(float(payload))
            except (TypeError, ValueError):
                pass
        return values

    params = pattern.get("parameters", {})
    params_alt = pattern.get("params", {})
    seed_values = _numeric_values(params) + _numeric_values(params_alt)
    if "value" in pattern:
        try:
            seed_values.append(float(pattern.get("value", 0)))
        except (TypeError, ValueError):
            pass

    if not seed_values:
        return False

    return all(abs(val) < 1e-9 for val in seed_values)


def _bill_of_materials_by_node(nodes: List[Node]) -> Dict[int, Dict[int, Dict[int, Any]]]:
    """Parse BOM mappings for manufacturer-like nodes keyed by node id."""

    bom_by_node: Dict[int, Dict[int, Dict[int, Any]]] = {}
    for node in nodes:
        attrs = dict(getattr(node, "attributes", {}) or {})
        raw_bom = attrs.get("bill_of_materials", {}) or {}
        parsed: Dict[int, Dict[int, Any]] = {}
        for produced_key, components in raw_bom.items():
            try:
                produced_id = int(produced_key)
            except (TypeError, ValueError):
                continue
            comp_map: Dict[int, Any] = {}
            for comp_key, ratio in (components or {}).items():
                try:
                    comp_map[int(comp_key)] = ratio
                except (TypeError, ValueError):
                    continue
            parsed[produced_id] = comp_map
        if parsed:
            bom_by_node[node.id] = parsed
    return bom_by_node


def _is_manufacturer_like(node: Node) -> bool:
    """Identify nodes that should split flows via a BOM rather than pass-through."""

    master = str(getattr(node, "master_type", "") or "").lower()
    dag_type = str(getattr(node, "dag_type", "") or "").lower()
    node_type = str(getattr(node, "type", "") or "").lower()
    if master == "manufacturer":
        return True
    return dag_type in {"manufacturer", "case_mfg", "six_pack_mfg", "bottle_mfg"} or "mfg" in dag_type or "mfg" in node_type


def _compute_item_flow_by_node(session: Session, config: SupplyChainConfig) -> Dict[int, Set[int]]:
    """Traverse the DAG from Market Demand upstream to assign items per node."""

    nodes = session.query(Node).filter(Node.config_id == config.id).all()
    if not nodes:
        return {}

    valid_item_ids = {
        item.id
        for item in session.query(Product).filter(Product.config_id == config.id).all()
        if item.id is not None
    }

    node_lookup = {node.id: node for node in nodes if node.id is not None}
    upstream_index: Dict[int, List[int]] = defaultdict(list)
    for lane in session.query(Lane).filter(Lane.config_id == config.id).all():
        upstream_index[lane.to_site_id].append(lane.from_site_id)

    market_demands = (
        session.query(MarketDemand)
        .filter(MarketDemand.config_id == config.id)
        .all()
    )
    demand_item_ids: Set[int] = {
        md.product_id
        for md in market_demands
        if md.product_id is not None and not _is_zero_demand_pattern(md.demand_pattern)
    }
    if not demand_item_ids:
        demand_item_ids = {
            itm.id
            for itm in session.query(Product).filter(Product.config_id == config.id).all()
            if itm.id is not None
        }

    demand_nodes = [
        node.id
        for node in nodes
        if node.id is not None
        and str(getattr(node, "master_type", "") or "").lower() == "customer"
    ]
    if not demand_nodes:
        return {}

    bom_by_node = _bill_of_materials_by_node(nodes)
    items_by_node: Dict[int, Set[int]] = defaultdict(set)
    pending: Dict[int, Set[int]] = defaultdict(set)
    queue: deque[Tuple[int, Set[int]]] = deque(
        (node_id, set(demand_item_ids)) for node_id in demand_nodes
    )

    while queue:
        node_id, needed_items = queue.popleft()
        for upstream_id in upstream_index.get(node_id, []):
            upstream_node = node_lookup.get(upstream_id)
            if upstream_node is None:
                continue

            master = str(getattr(upstream_node, "master_type", "") or "").lower()
            is_manufacturer = _is_manufacturer_like(upstream_node)
            propagate: Set[int] = set(needed_items)

            if is_manufacturer:
                bom = bom_by_node.get(upstream_node.id, {})
                produced_ids = set(bom.keys())
                produced_match = propagate & produced_ids if produced_ids else set()
                if produced_match:
                    items_by_node[upstream_id].update(produced_match)
                    component_requirements: Set[int] = set()
                    for produced_id in produced_match:
                        component_requirements.update(bom.get(produced_id, {}).keys())
                    component_requirements = {
                        requirement
                        for requirement in component_requirements
                        if requirement in valid_item_ids
                    }
                    if component_requirements:
                        items_by_node[upstream_id].update(component_requirements)
                        propagate = component_requirements
                    else:
                        propagate = set(needed_items)
                else:
                    items_by_node[upstream_id].update(propagate)
            else:
                items_by_node[upstream_id].update(propagate)

            if not propagate or master == "vendor":
                continue

            unseen = propagate - pending[upstream_id]
            if unseen:
                pending[upstream_id].update(unseen)
                queue.append((upstream_id, propagate))

    return items_by_node


def _reseed_product_site_configs(session: Session, config: SupplyChainConfig) -> None:
    """Synchronize InvPolicy rows so sites only carry relevant products."""
    items_by_node = _compute_item_flow_by_node(session, config)
    if not items_by_node:
        return

    desired_pairs: Set[Tuple[int, str]] = set()
    node_lookup = {
        node.id: node
        for node in session.query(Node).filter(Node.config_id == config.id).all()
        if node.id is not None
    }

    for node_id, item_ids in items_by_node.items():
        node = node_lookup.get(node_id)
        if not node:
            continue
        master = str(getattr(node, "master_type", "") or "").lower()
        if master in {"vendor", "customer"}:
            continue
        for item_id in item_ids:
            desired_pairs.add((node_id, item_id))

    existing_policies = (
        session.query(InvPolicy)
        .filter(InvPolicy.config_id == config.id)
        .filter(
            (InvPolicy.inventory_target_range.isnot(None))
            | (InvPolicy.holding_cost_range.isnot(None))
            | (InvPolicy.initial_inventory_range.isnot(None))
        )
        .all()
    )
    existing_pairs = {
        (p.site_id, p.product_id)
        for p in existing_policies
        if p.site_id is not None and p.product_id is not None
    }

    for p in existing_policies:
        if (p.site_id, p.product_id) not in desired_pairs:
            session.delete(p)

    for node_id, item_id in sorted(desired_pairs - existing_pairs):
        session.add(
            InvPolicy(
                product_id=item_id,
                site_id=node_id,
                config_id=config.id,
                ss_policy="abs_level",
                is_active="Y",
                **DEFAULT_PRODUCT_SITE_RANGES,
            )
        )

    session.flush()


def _populate_config_lineage(session: Session, config: SupplyChainConfig) -> None:
    """Populate ConfigLineage table for a config and all its ancestors.

    This builds the ancestor tree for efficient delta merging.
    For a config with lineage: config -> parent -> grandparent -> root,
    we create entries:
      (config.id, config.id, 0)       - self
      (config.id, parent.id, 1)       - parent
      (config.id, grandparent.id, 2)  - grandparent
      (config.id, root.id, 3)         - root
    """
    # Delete existing lineage entries for this config
    session.query(ConfigLineage).filter(ConfigLineage.config_id == config.id).delete()

    # Build lineage by walking up the parent chain
    ancestors = []
    current = config
    depth = 0

    while current is not None:
        ancestors.append((current.id, depth))
        if current.parent_config_id is None:
            break
        current = session.query(SupplyChainConfig).filter(
            SupplyChainConfig.id == current.parent_config_id
        ).first()
        depth += 1

    # Insert lineage entries
    for ancestor_id, ancestor_depth in ancestors:
        lineage_entry = ConfigLineage(
            config_id=config.id,
            ancestor_id=ancestor_id,
            depth=ancestor_depth
        )
        session.add(lineage_entry)

    session.flush()


def _get_parent_config(session: Session, tenant: Tenant, parent_name: str) -> Optional[SupplyChainConfig]:
    """Get a parent config by name within the same tenant."""
    return (
        session.query(SupplyChainConfig)
        .filter(
            SupplyChainConfig.tenant_id == tenant.id,
            SupplyChainConfig.name == parent_name
        )
        .first()
    )


def _get_root_config(session: Session, tenant: Tenant) -> Optional[SupplyChainConfig]:
    """Get the root config (Default Beer Scenario) for the tenant by DB lookup name."""
    return _get_parent_config(session, tenant, "Default Beer Scenario")


def ensure_case_config(session: Session, tenant: Tenant) -> SupplyChainConfig:
    """Create or update the Case simulation configuration (Case built from Six-Packs).

    Lineage: Default Beer Scenario -> Case Beer Scenario (DB config names)
    """
    # Get parent config (Default Beer Scenario - DB lookup name)
    parent_config = _get_root_config(session, tenant)
    root_config = parent_config

    config = (
        session.query(SupplyChainConfig)
        .filter(SupplyChainConfig.tenant_id == tenant.id, SupplyChainConfig.name == "Case Beer Scenario")
        .first()
    )
    if not config:
        config = SupplyChainConfig(
            name="Case Beer Scenario",
            description="Case manufacturer consumes Six-Packs (1:4 BOM) using manufacturer master node type.",
            tenant_id=tenant.id,
            time_bucket=TimeBucket.WEEK,
            is_active=True,
            parent_config_id=parent_config.id if parent_config else None,
            base_config_id=root_config.id if root_config else None,
        )
        session.add(config)
        session.flush()
        _ensure_manufacturer_master_type_definition(session, config)
        # Populate lineage for new config
        _populate_config_lineage(session, config)
    elif parent_config and (config.parent_config_id != parent_config.id or config.base_config_id != root_config.id):
        # Update parent/base if not set correctly
        config.parent_config_id = parent_config.id
        config.base_config_id = root_config.id
        session.add(config)
        session.flush()
        _populate_config_lineage(session, config)

    _ensure_manufacturer_master_type_definition(session, config)

    # Items
    items = {item.name: item for item in session.query(Product).filter(Product.config_id == config.id).all()}
    case_item = items.get("Case") or items.get("Case of Beer") or Product(id="Case", description="Standard case product")
    six_pack_item = items.get("Six-Pack") or Product(id="Six-Pack", description="Standard six-pack product")
    for itm in (case_item, six_pack_item):
        if itm.id is None:
            session.add(itm)
            session.flush()

    # Nodes
    node_specs = [
        ("Vendor", NodeType.VENDOR, "vendor"),
        ("Case Mfg", NodeType.MANUFACTURER, "case_mfg"),
        ("Distributor", NodeType.DISTRIBUTOR, "distributor"),
        ("Wholesaler", NodeType.WHOLESALER, "wholesaler"),
        ("Retailer", NodeType.RETAILER, "retailer"),
        ("Customer", NodeType.CUSTOMER, "customer"),
    ]
    allowed_keys = {_normalise_node_key(name) for name, *_ in node_specs}
    existing_nodes = session.query(Node).filter(Node.config_id == config.id).all()
    for node in existing_nodes:
        if _normalise_node_key(node.name) in allowed_keys:
            continue
        session.query(Lane).filter(
            (Lane.from_site_id == node.id) | (Lane.to_site_id == node.id)
        ).delete(synchronize_session=False)
        session.query(InvPolicy).filter(InvPolicy.site_id == node.id).delete(synchronize_session=False)
        session.delete(node)
    session.flush()

    nodes: Dict[str, Node] = {
        _normalise_node_key(n.name): n for n in session.query(Node).filter(Node.config_id == config.id).all()
    }
    for node_name, node_type, dag_key in node_specs:
        key = _normalise_node_key(node_name)
        node = nodes.get(key)
        if node is None:
            node = Node(config_id=config.id, name=node_name, type=dag_key)
            session.add(node)
            session.flush()
            nodes[key] = node
        node.name = node_name
        node.type = dag_key
        node.dag_type = dag_key
        node.master_type = _canonical_master_type(node_type)
        session.add(node)

    manufacturer = nodes.get(_normalise_node_key("Case Mfg"))
    market_supply = nodes.get(_normalise_node_key("Vendor"))
    _ensure_market_supply_attributes(market_supply)
    if market_supply:
        session.add(market_supply)
    if manufacturer:
        attrs = dict(getattr(manufacturer, "attributes", {}) or {})
        bom = attrs.get("bill_of_materials", {})
        bom[str(case_item.id)] = {str(six_pack_item.id): 4}
        attrs["bill_of_materials"] = bom
        _ensure_manufacturing_metadata(manufacturer, [case_item], capacity_hours=7 * 24, leadtime=0)
        manufacturer.attributes = attrs
        session.add(manufacturer)

    desired_lanes = [
        pair
        for pair in [
            (market_supply, manufacturer),
            (manufacturer, nodes[_normalise_node_key("Distributor")]),
            (nodes[_normalise_node_key("Distributor")], nodes[_normalise_node_key("Wholesaler")]),
            (nodes[_normalise_node_key("Wholesaler")], nodes[_normalise_node_key("Retailer")]),
            (nodes[_normalise_node_key("Retailer")], nodes[_normalise_node_key("Customer")]),
        ]
        if pair
    ]
    desired_pairs = {(u.id, d.id) for u, d in desired_lanes if u and d}
    for lane in session.query(Lane).filter(Lane.config_id == config.id).all():
        if (lane.from_site_id, lane.to_site_id) not in desired_pairs:
            session.delete(lane)
    session.flush()

    existing_pairs = {
        (lane.from_site_id, lane.to_site_id)
        for lane in session.query(Lane).filter(Lane.config_id == config.id).all()
    }
    for upstream_node, downstream_node in desired_lanes:
        if not upstream_node or not downstream_node:
            continue
        if (upstream_node.id, downstream_node.id) in existing_pairs:
            continue
        lane = Lane(
            config_id=config.id,
            from_site_id=upstream_node.id,
            to_site_id=downstream_node.id,
            capacity=9999,
            lead_time_days={"min": 1, "max": 5},
            demand_lead_time={"type": "deterministic", "value": 1},
            supply_lead_time={"type": "deterministic", "value": 2},
        )
        session.add(lane)

    session.flush()
    _ensure_lane_lead_times(session, config, overwrite_existing=True)

    # Product node configs
    def _ensure_cfg(item: Product, node: Node) -> None:
        exists = (
            session.query(InvPolicy)
            .filter(InvPolicy.product_id == item.id, InvPolicy.site_id == node.id)
            .first()
        )
        if exists:
            return
        session.add(
            InvPolicy(
                product_id=item.id,
                site_id=node.id,
                inventory_target_range={"min": 5, "max": 20},
                initial_inventory_range={"min": 2, "max": 10},
                holding_cost_range={"min": 0.5, "max": 5.0},
                backlog_cost_range={"min": 5.0, "max": 10.0},
                selling_price_range={"min": 25.0, "max": 50.0},
            )
        )

    for node in session.query(Node).filter(Node.config_id == config.id).all():
        if str(node.master_type or "").lower() in {"vendor", "customer"}:
            continue
        for item in (case_item, six_pack_item):
            _ensure_cfg(item, node)

    # Market and demand (Case gets demand; Six-Pack gets zero for completeness)
    market = (
        session.query(Market)
        .filter(Market.config_id == config.id, Market.name == "Case Market")
        .first()
        or Market(config_id=config.id, name="Case Market", description="Case demand market")
    )
    session.add(market)
    session.flush()

    zero_pattern = {
        "demand_type": "constant",
        "variability": {"type": "flat", "value": 0},
        "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
        "trend": {"type": "none", "slope": 0, "intercept": 0},
        "parameters": {"value": 0},
        "params": {"value": 0},
    }
    case_pattern = _case_classic_demand_pattern()
    demand_specs = {case_item.id: case_pattern, six_pack_item.id: zero_pattern}
    for item_id, pattern in demand_specs.items():
        demand = (
            session.query(MarketDemand)
            .filter(MarketDemand.config_id == config.id, MarketDemand.product_id == item_id, MarketDemand.market_id == market.id)
            .first()
        )
        if not demand:
            demand = MarketDemand(
                config_id=config.id,
                product_id=item_id,
                market_id=market.id,
            )
        demand.demand_pattern = pattern
        session.add(demand)

    session.flush()
    _apply_site_type_definitions(session, config, CASE_SIMULATION_NODE_TYPE_DEFINITIONS)
    _reseed_product_site_configs(session, config)
    return config


def ensure_six_pack_config(session: Session, tenant: Tenant) -> SupplyChainConfig:
    """Create or update the Six-Pack simulation configuration (Case built from Six-Packs).

    Lineage: Default Beer Scenario -> Case Beer Scenario -> Six-Pack Beer Scenario (DB config names)
    """
    # Get parent config (Case Beer Scenario - DB lookup name)
    parent_config = _get_parent_config(session, tenant, "Case Beer Scenario")
    root_config = _get_root_config(session, tenant)

    config = (
        session.query(SupplyChainConfig)
        .filter(SupplyChainConfig.tenant_id == tenant.id, SupplyChainConfig.name == "Six-Pack Beer Scenario")
        .first()
    )
    created = False
    if not config:
        config = SupplyChainConfig(
            name="Six-Pack Beer Scenario",
            description="Case manufacturer consumes Six-Packs built from bottles supplied by Market Supply.",
            tenant_id=tenant.id,
            time_bucket=TimeBucket.WEEK,
            is_active=True,
            parent_config_id=parent_config.id if parent_config else None,
            base_config_id=root_config.id if root_config else None,
        )
        session.add(config)
        session.flush()
        _ensure_manufacturer_master_type_definition(session, config)
        # Populate lineage for new config
        _populate_config_lineage(session, config)
        created = True
    elif parent_config and (config.parent_config_id != parent_config.id or config.base_config_id != (root_config.id if root_config else None)):
        # Update parent/base if not set correctly
        config.parent_config_id = parent_config.id
        config.base_config_id = root_config.id if root_config else None
        session.add(config)
        session.flush()
        _populate_config_lineage(session, config)

    _ensure_manufacturer_master_type_definition(session, config)

    # Items
    items = {item.name: item for item in session.query(Product).filter(Product.config_id == config.id).all()}
    case_item = items.get("Case") or items.get("Case of Beer") or Product(id="Case", description="Standard case product")
    six_pack_item = items.get("Six-Pack") or Product(id="Six-Pack", description="Standard six-pack product")
    bottle_item = items.get("Bottle") or Product(id="Bottle", description="Single bottle")
    for itm in (case_item, six_pack_item, bottle_item):
        if itm.id is None:
            session.add(itm)
            session.flush()

    # Nodes (clean up any obsolete nodes from prior runs)
    node_specs = [
        ("Vendor", NodeType.VENDOR, "vendor"),
        ("Six-Pack Mfg", NodeType.MANUFACTURER, "six_pack_mfg"),
        ("Case Mfg", NodeType.MANUFACTURER, "case_mfg"),
        ("Distributor", NodeType.DISTRIBUTOR, "distributor"),
        ("Wholesaler", NodeType.WHOLESALER, "wholesaler"),
        ("Retailer", NodeType.RETAILER, "retailer"),
        ("Customer", NodeType.CUSTOMER, "customer"),
    ]
    allowed_keys = {_normalise_node_key(name) for name, *_ in node_specs}
    existing_nodes = session.query(Node).filter(Node.config_id == config.id).all()
    for node in existing_nodes:
        key = _normalise_node_key(node.name)
        if key in allowed_keys:
            continue
        session.query(Lane).filter(
            (Lane.from_site_id == node.id) | (Lane.to_site_id == node.id)
        ).delete(synchronize_session=False)
        session.query(InvPolicy).filter(InvPolicy.site_id == node.id).delete(
            synchronize_session=False
        )
        session.delete(node)
    session.flush()

    nodes: Dict[str, Node] = {
        _normalise_node_key(n.name): n for n in session.query(Node).filter(Node.config_id == config.id).all()
    }
    for node_name, node_type, dag_key in node_specs:
        key = _normalise_node_key(node_name)
        node = nodes.get(key)
        if node is None:
            node = Node(config_id=config.id, name=node_name, type=dag_key)
            session.add(node)
            session.flush()
            nodes[key] = node
        node.name = node_name
        node.type = dag_key
        node.dag_type = dag_key
        node.master_type = _canonical_master_type(node_type)
        session.add(node)

    six_pack_manu = nodes.get(_normalise_node_key("Six-Pack Mfg"))
    manufacturer = nodes.get(_normalise_node_key("Case Mfg"))
    market_supply = nodes.get(_normalise_node_key("Vendor"))
    _ensure_market_supply_attributes(market_supply)
    if market_supply:
        session.add(market_supply)
    # BOMs per spec: Six-Pack from Bottle (1:6), Case from Six-Pack (1:4)
    if six_pack_manu:
        attrs = dict(getattr(six_pack_manu, "attributes", {}) or {})
        bom = attrs.get("bill_of_materials", {})
        bom[str(six_pack_item.id)] = {str(bottle_item.id): 6}
        attrs["bill_of_materials"] = bom
        _ensure_manufacturing_metadata(six_pack_manu, [six_pack_item], capacity_hours=7 * 24, leadtime=0)
        six_pack_manu.attributes = attrs
        session.add(six_pack_manu)
    if manufacturer:
        attrs = dict(getattr(manufacturer, "attributes", {}) or {})
        bom = attrs.get("bill_of_materials", {})
        bom[str(case_item.id)] = {str(six_pack_item.id): 4}
        attrs["bill_of_materials"] = bom
        _ensure_manufacturing_metadata(manufacturer, [case_item], capacity_hours=7 * 24, leadtime=0)
        manufacturer.attributes = attrs
        session.add(manufacturer)

    # Lanes (supply chain)
    desired_lanes = [
        pair
        for pair in [
            (market_supply, six_pack_manu),
            (six_pack_manu, manufacturer),
            (manufacturer, nodes[_normalise_node_key("Distributor")]),
            (nodes[_normalise_node_key("Distributor")], nodes[_normalise_node_key("Wholesaler")]),
            (nodes[_normalise_node_key("Wholesaler")], nodes[_normalise_node_key("Retailer")]),
            (nodes[_normalise_node_key("Retailer")], nodes[_normalise_node_key("Customer")]),
        ]
        if pair
    ]
    desired_pairs = {(u.id, d.id) for u, d in desired_lanes if u and d}
    for lane in session.query(Lane).filter(Lane.config_id == config.id).all():
        if (lane.from_site_id, lane.to_site_id) not in desired_pairs:
            session.delete(lane)
    session.flush()

    existing = {
        (lane.from_site_id, lane.to_site_id)
        for lane in session.query(Lane).filter(Lane.config_id == config.id).all()
    }
    for upstream_node, downstream_node in desired_lanes:
        if not upstream_node or not downstream_node:
            continue
        if (upstream_node.id, downstream_node.id) in existing:
            continue
        lane = Lane(
            config_id=config.id,
            from_site_id=upstream_node.id,
            to_site_id=downstream_node.id,
            capacity=9999,
            lead_time_days={"min": 1, "max": 5},
            demand_lead_time={"type": "deterministic", "value": 1},
            supply_lead_time={"type": "deterministic", "value": 2},
        )
        session.add(lane)

    session.flush()
    _ensure_lane_lead_times(session, config, overwrite_existing=True)

    # Product node configs
    def _ensure_node_cfg(item: Product, node: Node) -> None:
        exists = (
            session.query(InvPolicy)
            .filter(InvPolicy.product_id == item.id, InvPolicy.site_id == node.id)
            .first()
        )
        if exists:
            return
        session.add(
            InvPolicy(
                product_id=item.id,
                site_id=node.id,
                inventory_target_range={"min": 5, "max": 20},
                initial_inventory_range={"min": 2, "max": 10},
                holding_cost_range={"min": 0.5, "max": 5.0},
                backlog_cost_range={"min": 5.0, "max": 10.0},
                selling_price_range={"min": 25.0, "max": 50.0},
            )
        )

    for node in session.query(Node).filter(Node.config_id == config.id).all():
        if str(node.master_type or "").lower() in {"vendor", "customer"}:
            continue
        for item in (case_item, six_pack_item, bottle_item):
            _ensure_node_cfg(item, node)

    # Market and demand (Case gets demand; Six-Pack/Bottle get zero demand to satisfy completeness)
    market = (
        session.query(Market)
        .filter(Market.config_id == config.id, Market.name == "Six-Pack Market")
        .first()
        or Market(config_id=config.id, name="Six-Pack Market", description="Case demand market")
    )
    session.add(market)
    session.flush()

    zero_pattern = {
        "demand_type": "constant",
        "variability": {"type": "flat", "value": 0},
        "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
        "trend": {"type": "none", "slope": 0, "intercept": 0},
        "parameters": {"value": 0},
        "params": {"value": 0},
    }
    case_pattern = _case_classic_demand_pattern()
    demand_specs = {
        case_item.id: case_pattern,
        six_pack_item.id: zero_pattern,
        bottle_item.id: zero_pattern,
    }
    for item_id, pattern in demand_specs.items():
        demand = (
            session.query(MarketDemand)
            .filter(MarketDemand.config_id == config.id, MarketDemand.product_id == item_id, MarketDemand.market_id == market.id)
            .first()
        )
        if not demand:
            demand = MarketDemand(
                config_id=config.id,
                product_id=item_id,
                market_id=market.id,
            )
        demand.demand_pattern = pattern
        session.add(demand)
    session.flush()
    _apply_site_type_definitions(session, config, SIX_PACK_SIMULATION_NODE_TYPE_DEFINITIONS)
    _reseed_product_site_configs(session, config)
    return config


def ensure_bottle_config(session: Session, tenant: Tenant) -> SupplyChainConfig:
    """Create or update the Bottle simulation configuration (Case <- Six-Pack <- Bottle <- Ingredients).

    Lineage: Default Beer Scenario -> Case Beer Scenario -> Six-Pack Beer Scenario -> Bottle Beer Scenario (DB config names)
    """
    # Get parent config (Six-Pack Beer Scenario - DB lookup name)
    parent_config = _get_parent_config(session, tenant, "Six-Pack Beer Scenario")
    root_config = _get_root_config(session, tenant)

    config = (
        session.query(SupplyChainConfig)
        .filter(SupplyChainConfig.tenant_id == tenant.id, SupplyChainConfig.name == "Bottle Beer Scenario")
        .first()
    )
    if not config:
        config = SupplyChainConfig(
            name="Bottle Beer Scenario",
            description="Case manufacturer consumes Six-Packs; Six-Packs consume Bottles; Bottles consume Ingredients from Market Supply.",
            tenant_id=tenant.id,
            time_bucket=TimeBucket.WEEK,
            is_active=True,
            parent_config_id=parent_config.id if parent_config else None,
            base_config_id=root_config.id if root_config else None,
        )
        session.add(config)
        session.flush()
        _ensure_manufacturer_master_type_definition(session, config)
        # Populate lineage for new config
        _populate_config_lineage(session, config)
    elif parent_config and (config.parent_config_id != parent_config.id or config.base_config_id != (root_config.id if root_config else None)):
        # Update parent/base if not set correctly
        config.parent_config_id = parent_config.id
        config.base_config_id = root_config.id if root_config else None
        session.add(config)
        session.flush()
        _populate_config_lineage(session, config)

    _ensure_manufacturer_master_type_definition(session, config)

    items = {item.name: item for item in session.query(Product).filter(Product.config_id == config.id).all()}
    case_item = items.get("Case") or Product(id="Case", description="Standard case product")
    six_pack_item = items.get("Six-Pack") or Product(id="Six-Pack", description="Standard six-pack product")
    bottle_item = items.get("Bottle") or Product(id="Bottle", description="Single bottle")
    ingredients_item = items.get("Ingredients") or Product(
        config_id=config.id, id="Ingredients", description="Ingredients for bottles"
    )
    for itm in (case_item, six_pack_item, bottle_item, ingredients_item):
        if itm.id is None:
            session.add(itm)
            session.flush()

    node_specs = [
        ("Vendor", NodeType.VENDOR, "vendor"),
        ("Bottle Mfg", NodeType.MANUFACTURER, "bottle_mfg"),
        ("Six-Pack Mfg", NodeType.MANUFACTURER, "six_pack_mfg"),
        ("Case Mfg", NodeType.MANUFACTURER, "case_mfg"),
        ("Distributor", NodeType.DISTRIBUTOR, "distributor"),
        ("Wholesaler", NodeType.WHOLESALER, "wholesaler"),
        ("Retailer", NodeType.RETAILER, "retailer"),
        ("Customer", NodeType.CUSTOMER, "customer"),
    ]
    allowed_keys = {_normalise_node_key(name) for name, *_ in node_specs}
    existing_nodes = session.query(Node).filter(Node.config_id == config.id).all()
    for node in existing_nodes:
        key = _normalise_node_key(node.name)
        if key in allowed_keys:
            continue
        session.query(Lane).filter(
            (Lane.from_site_id == node.id) | (Lane.to_site_id == node.id)
        ).delete(synchronize_session=False)
        session.query(InvPolicy).filter(InvPolicy.site_id == node.id).delete(
            synchronize_session=False
        )
        session.delete(node)
    session.flush()

    nodes: Dict[str, Node] = {
        _normalise_node_key(n.name): n for n in session.query(Node).filter(Node.config_id == config.id).all()
    }
    for node_name, node_type, dag_key in node_specs:
        key = _normalise_node_key(node_name)
        node = nodes.get(key)
        if node is None:
            node = Node(config_id=config.id, name=node_name, type=dag_key)
            session.add(node)
            session.flush()
            nodes[key] = node
        node.name = node_name
        node.type = dag_key
        node.dag_type = dag_key
        node.master_type = _canonical_master_type(node_type)
        session.add(node)

    # BOMs and manufacturing metadata
    bottle_manu = nodes.get(_normalise_node_key("Bottle Mfg"))
    six_pack_manu = nodes.get(_normalise_node_key("Six-Pack Mfg"))
    case_manu = nodes.get(_normalise_node_key("Case Mfg"))
    market_supply = nodes.get(_normalise_node_key("Vendor"))
    _ensure_market_supply_attributes(market_supply)
    if market_supply:
        session.add(market_supply)
    if bottle_manu:
        attrs = dict(getattr(bottle_manu, "attributes", {}) or {})
        bom = attrs.get("bill_of_materials", {})
        bom[str(bottle_item.id)] = {str(ingredients_item.id): 1}
        attrs["bill_of_materials"] = bom
        _ensure_manufacturing_metadata(bottle_manu, [bottle_item], capacity_hours=7 * 24, leadtime=0)
        bottle_manu.attributes = attrs
        session.add(bottle_manu)
    if six_pack_manu:
        attrs = dict(getattr(six_pack_manu, "attributes", {}) or {})
        bom = attrs.get("bill_of_materials", {})
        bom[str(six_pack_item.id)] = {str(bottle_item.id): 6}
        attrs["bill_of_materials"] = bom
        _ensure_manufacturing_metadata(six_pack_manu, [six_pack_item], capacity_hours=7 * 24, leadtime=0)
        six_pack_manu.attributes = attrs
        session.add(six_pack_manu)
    if case_manu:
        attrs = dict(getattr(case_manu, "attributes", {}) or {})
        bom = attrs.get("bill_of_materials", {})
        bom[str(case_item.id)] = {str(six_pack_item.id): 4}
        attrs["bill_of_materials"] = bom
        _ensure_manufacturing_metadata(case_manu, [case_item], capacity_hours=7 * 24, leadtime=0)
        case_manu.attributes = attrs
        session.add(case_manu)

    # Lanes
    desired_lanes = [
        pair
        for pair in [
            (market_supply, bottle_manu),
            (bottle_manu, six_pack_manu),
            (six_pack_manu, case_manu),
            (case_manu, nodes[_normalise_node_key("Distributor")]),
            (nodes[_normalise_node_key("Distributor")], nodes[_normalise_node_key("Wholesaler")]),
            (nodes[_normalise_node_key("Wholesaler")], nodes[_normalise_node_key("Retailer")]),
            (nodes[_normalise_node_key("Retailer")], nodes[_normalise_node_key("Customer")]),
        ]
        if pair
    ]
    desired_pairs = {(u.id, d.id) for u, d in desired_lanes if u and d}
    for lane in session.query(Lane).filter(Lane.config_id == config.id).all():
        if (lane.from_site_id, lane.to_site_id) not in desired_pairs:
            session.delete(lane)
    session.flush()

    existing = {
        (lane.from_site_id, lane.to_site_id)
        for lane in session.query(Lane).filter(Lane.config_id == config.id).all()
    }
    for upstream_node, downstream_node in desired_lanes:
        if not upstream_node or not downstream_node:
            continue
        if (upstream_node.id, downstream_node.id) in existing:
            continue
        lane = Lane(
            config_id=config.id,
            from_site_id=upstream_node.id,
            to_site_id=downstream_node.id,
            capacity=9999,
            lead_time_days={"min": 1, "max": 5},
            demand_lead_time={"type": "deterministic", "value": 1},
            supply_lead_time={"type": "deterministic", "value": 2},
        )
        session.add(lane)

    session.flush()
    _ensure_lane_lead_times(session, config, overwrite_existing=True)

    # Product node configs
    def _ensure_cfg(item: Product, node: Node) -> None:
        exists = (
            session.query(InvPolicy)
            .filter(InvPolicy.product_id == item.id, InvPolicy.site_id == node.id)
            .first()
        )
        if exists:
            return
        session.add(
            InvPolicy(
                product_id=item.id,
                site_id=node.id,
                inventory_target_range={"min": 5, "max": 20},
                initial_inventory_range={"min": 2, "max": 10},
                holding_cost_range={"min": 0.5, "max": 5.0},
                backlog_cost_range={"min": 5.0, "max": 10.0},
                selling_price_range={"min": 25.0, "max": 50.0},
            )
        )

    for node in session.query(Node).filter(Node.config_id == config.id).all():
        if str(node.master_type or "").lower() in {"vendor", "customer"}:
            continue
        for item in (case_item, six_pack_item, bottle_item, ingredients_item):
            _ensure_cfg(item, node)

    market = (
        session.query(Market)
        .filter(Market.config_id == config.id, Market.name == "Bottle Market")
        .first()
        or Market(config_id=config.id, name="Bottle Market", description="Case demand market")
    )
    session.add(market)
    session.flush()

    # Demand rows for all items (Case demanded; others zero)
    zero_pattern = {
        "demand_type": "constant",
        "variability": {"type": "flat", "value": 0},
        "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
        "trend": {"type": "none", "slope": 0, "intercept": 0},
        "parameters": {"value": 0},
        "params": {"value": 0},
    }
    case_pattern = _case_classic_demand_pattern()
    demand_specs = {
        case_item.id: case_pattern,
        six_pack_item.id: zero_pattern,
        bottle_item.id: zero_pattern,
        ingredients_item.id: zero_pattern,
    }
    for item_id, pattern in demand_specs.items():
        demand = (
            session.query(MarketDemand)
            .filter(MarketDemand.config_id == config.id, MarketDemand.product_id == item_id, MarketDemand.market_id == market.id)
            .first()
        )
        if not demand:
            demand = MarketDemand(
                config_id=config.id,
                product_id=item_id,
                market_id=market.id,
            )
        demand.demand_pattern = pattern
        session.add(demand)
    session.flush()
    _apply_site_type_definitions(session, config, BOTTLE_SIMULATION_NODE_TYPE_DEFINITIONS)
    _reseed_product_site_configs(session, config)
    return config


def ensure_multi_item_six_pack_config(session: Session, tenant: Tenant) -> SupplyChainConfig:
    """Create or update a multi-item Six-Pack simulation variant with mixed sourcing."""

    config = (
        session.query(SupplyChainConfig)
        .filter(SupplyChainConfig.tenant_id == tenant.id, SupplyChainConfig.name == "Multi-Product SixPack Beer Scenario")
        .first()
    )
    if not config:
        config = SupplyChainConfig(
            name="Multi-Product SixPack Beer Scenario",
            description="Multi-item flow where some cases are sourced directly and others via BOM conversions.",
            tenant_id=tenant.id,
            time_bucket=TimeBucket.WEEK,
            is_active=True,
        )
        session.add(config)
        session.flush()

    # Items
    def _get_or_create_item(name: str, desc: str) -> Product:
        itm = session.query(Product).filter(Product.config_id == config.id, Product.name == name).first()
        if not itm:
            itm = Product(id=name, description=desc)
            session.add(itm)
            session.flush()
        return itm

    dark_case = _get_or_create_item("Dark_Case", "Dark Case")
    pilsner_case = _get_or_create_item("Pilsner_Case", "Pilsner Case")
    noalc_case = _get_or_create_item("NoAlc_Case", "Non-alcoholic Case")
    pilsner_six = _get_or_create_item("Pilsner_SixPack", "Pilsner Six-Pack")
    noalc_six = _get_or_create_item("NoAlc_SixPack", "Non-alcoholic Six-Pack")
    noalc_bottle = _get_or_create_item("NoAlc_Bottle", "Non-alcoholic Bottle")

    node_specs = [
        ("Vendor", NodeType.VENDOR, "vendor"),
        ("Six-Pack Manufacturer", NodeType.MANUFACTURER, "six_pack_mfg"),
        ("Case Manufacturer", NodeType.MANUFACTURER, "case_mfg"),
        ("Distributor", NodeType.DISTRIBUTOR, "distributor"),
        ("Wholesaler", NodeType.WHOLESALER, "wholesaler"),
        ("Retailer", NodeType.RETAILER, "retailer"),
        ("Customer", NodeType.CUSTOMER, "customer"),
    ]
    nodes: Dict[str, Node] = {_normalise_node_key(n.name): n for n in session.query(Node).filter(Node.config_id == config.id).all()}
    allowed_keys = {_normalise_node_key(name) for name, *_ in node_specs}
    for node in list(nodes.values()):
        if _normalise_node_key(node.name) not in allowed_keys:
            session.query(Lane).filter((Lane.from_site_id == node.id) | (Lane.to_site_id == node.id)).delete(
                synchronize_session=False
            )
            session.query(InvPolicy).filter(InvPolicy.site_id == node.id).delete(synchronize_session=False)
            session.delete(node)
    session.flush()

    for node_name, node_type, dag_key in node_specs:
        key = _normalise_node_key(node_name)
        node = nodes.get(key)
        if node is None:
            canonical_type = dag_key or (
                node_type.value.lower() if hasattr(node_type, "value") else str(node_type)
            )
            node = Node(config_id=config.id, name=node_name, type=canonical_type)
            session.add(node)
            session.flush()
            nodes[key] = node
        canonical_type = dag_key or (
            node_type.value.lower() if hasattr(node_type, "value") else str(node_type)
        )
        node.name = node_name
        node.type = canonical_type
        node.dag_type = canonical_type
        node.master_type = _canonical_master_type(node_type)
        session.add(node)

    market_supply_node = nodes.get(_normalise_node_key("Vendor"))
    _ensure_market_supply_attributes(market_supply_node)
    if market_supply_node:
        session.add(market_supply_node)

    # BOMs
    case_mfg = nodes[_normalise_node_key("Case Manufacturer")]
    six_mfg = nodes[_normalise_node_key("Six-Pack Manufacturer")]
    def _set_bom(node: Node, produced: Product, components: Dict[Product, int]) -> None:
        attrs = dict(getattr(node, "attributes", {}) or {})
        bom = attrs.get("bill_of_materials", {})
        bom[str(produced.id)] = {str(comp.id): qty for comp, qty in components.items()}
        attrs["bill_of_materials"] = bom
        _ensure_manufacturing_metadata(node, [produced], capacity_hours=7 * 24, leadtime=0)
        node.attributes = attrs
        session.add(node)

    _set_bom(case_mfg, pilsner_case, {pilsner_six: 4})
    _set_bom(case_mfg, noalc_case, {noalc_six: 4})
    _set_bom(six_mfg, noalc_six, {noalc_bottle: 6})

    # Lanes
    lanes = [
        (nodes[_normalise_node_key("Vendor")], six_mfg),
        (six_mfg, case_mfg),
        (case_mfg, nodes[_normalise_node_key("Distributor")]),
        (nodes[_normalise_node_key("Distributor")], nodes[_normalise_node_key("Wholesaler")]),
        (nodes[_normalise_node_key("Wholesaler")], nodes[_normalise_node_key("Retailer")]),
        (nodes[_normalise_node_key("Retailer")], nodes[_normalise_node_key("Customer")]),
    ]
    desired = {(u.id, d.id) for u, d in lanes if u and d}
    for lane in session.query(Lane).filter(Lane.config_id == config.id).all():
        if (lane.from_site_id, lane.to_site_id) not in desired:
            session.delete(lane)
    session.flush()
    existing = {
        (lane.from_site_id, lane.to_site_id)
        for lane in session.query(Lane).filter(Lane.config_id == config.id).all()
    }
    for upstream_node, downstream_node in lanes:
        if not upstream_node or not downstream_node:
            continue
        if (upstream_node.id, downstream_node.id) in existing:
            continue
        session.add(
            Lane(
                config_id=config.id,
                from_site_id=upstream_node.id,
                to_site_id=downstream_node.id,
                capacity=9999,
                lead_time_days={"min": 1, "max": 5},
                demand_lead_time={"type": "deterministic", "value": 1},
                supply_lead_time={"type": "deterministic", "value": 2},
            )
        )

    session.flush()

    # Product node configs
    all_items = [dark_case, pilsner_case, noalc_case, pilsner_six, noalc_six, noalc_bottle]
    for node in session.query(Node).filter(Node.config_id == config.id).all():
        if str(node.master_type or "").lower() in {"vendor", "customer"}:
            continue
        for item in all_items:
            exists = (
                session.query(InvPolicy)
                .filter(InvPolicy.product_id == item.id, InvPolicy.site_id == node.id)
                .first()
            )
            if not exists:
                session.add(
                    InvPolicy(
                        product_id=item.id,
                        site_id=node.id,
                        inventory_target_range={"min": 5, "max": 20},
                        initial_inventory_range={"min": 2, "max": 10},
                        holding_cost_range={"min": 0.5, "max": 5.0},
                        backlog_cost_range={"min": 5.0, "max": 10.0},
                        selling_price_range={"min": 25.0, "max": 50.0},
                    )
                )

    # Markets and demand (three case items)
    market = (
        session.query(Market)
        .filter(Market.config_id == config.id, Market.name == "Multi SixPack Market")
        .first()
        or Market(config_id=config.id, name="Multi SixPack Market", description="Multi-item demand market")
    )
    session.add(market)
    session.flush()
    session.query(MarketDemand).filter(MarketDemand.config_id == config.id).delete()
    demand_items = [dark_case, pilsner_case, noalc_case]
    zero_items = [pilsner_six, noalc_six, noalc_bottle]
    for item in demand_items:
        md = MarketDemand(config_id=config.id, product_id=item.id, market_id=market.id)
        md.demand_pattern = {
            "demand_type": "constant",
            "variability": {"type": "flat", "value": 4},
            "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
            "trend": {"type": "none", "slope": 0, "intercept": 0},
            "parameters": {"value": 4},
            "params": {"value": 4},
        }
        session.add(md)
    for item in zero_items:
        md = MarketDemand(config_id=config.id, product_id=item.id, market_id=market.id)
        md.demand_pattern = {
            "demand_type": "constant",
            "variability": {"type": "flat", "value": 0},
            "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
            "trend": {"type": "none", "slope": 0, "intercept": 0},
            "parameters": {"value": 0},
            "params": {"value": 0},
        }
        session.add(md)
    session.flush()
    _reseed_product_site_configs(session, config)
    return config

def ensure_default_game(
    session: Session,
    tenant: Tenant,
    *,
    config: Optional[SupplyChainConfig] = None,
    config_name: Optional[str] = None,
    config_description: Optional[str] = None,
    demand_pattern_override: Optional[Dict[str, Any]] = None,
    scenario_name: Optional[str] = None,
    manufacturer_master_type: Optional[str] = None,
) -> Scenario:
    """Ensure the primary scenario exists for the supplied tenant."""

    target_name = scenario_name or DEFAULT_SCENARIO_NAME
    scenario = (
        session.query(Scenario)
        .filter(Scenario.tenant_id == tenant.id, Scenario.name == target_name)
        .first()
    )

    sc_config = config or ensure_supply_chain_config(
        session,
        tenant,
        name=config_name,
        description=config_description,
        demand_pattern_override=demand_pattern_override,
        manufacturer_master_type=manufacturer_master_type,
    )

    override_payload = json.loads(json.dumps(demand_pattern_override)) if demand_pattern_override else None

    if scenario:
        print(
            f"[info] Scenario '{target_name}' already exists (id={scenario.id})."
        )
        existing_config = scenario.config or {}
        if isinstance(existing_config, str):
            try:
                existing_config = json.loads(existing_config)
            except json.JSONDecodeError:
                existing_config = {}
        _apply_default_lead_times(existing_config)
        if override_payload:
            existing_config["demand_pattern"] = override_payload
        existing_config["progression_mode"] = "unsupervised"
        scenario.config = json.loads(json.dumps(existing_config))
        scenario.demand_pattern = existing_config.get("demand_pattern", {})
        scenario.supply_chain_config_id = sc_config.id
        scenario.tenant_id = tenant.id
        creator_id = sc_config.created_by or tenant.admin_id
        if creator_id:
            scenario.created_by = creator_id
        session.add(scenario)
        return scenario

    print(f"[info] Creating default scenario '{target_name}' from supply chain configuration...")

    config_service = SupplyChainConfigService(session)
    scenario_config = config_service.create_scenario_from_config(
        sc_config.id,
        {"name": target_name, "max_periods": 40},
    )
    _apply_default_lead_times(scenario_config)
    scenario_config["progression_mode"] = "unsupervised"
    if override_payload:
        scenario_config["demand_pattern"] = override_payload

    creator_id = sc_config.created_by or tenant.admin_id
    scenario = Scenario(
        name=scenario_config.get("name", target_name),
        created_by=creator_id,
        tenant_id=tenant.id,
        status=ScenarioStatus.CREATED,
        max_periods=scenario_config.get("max_periods", 52),
        config=scenario_config,
        demand_pattern=scenario_config.get("demand_pattern", {}),
        supply_chain_config_id=sc_config.id,
    )
    session.add(scenario)
    session.flush()
    print(f"[success] Created scenario '{scenario.name}' (id={scenario.id}).")
    return scenario


def ensure_naive_unsupervised_game(
    session: Session,
    tenant: Tenant,
    config: SupplyChainConfig,
    *,
    demand_pattern_override: Optional[Dict[str, Any]] = None,
    scenario_name: str = NAIVE_AGENT_SCENARIO_NAME,
) -> Scenario:
    """Ensure a dedicated unsupervised scenario powered by naive agents exists."""

    config_service = SupplyChainConfigService(session)

    scenario = (
        session.query(Scenario)
        .filter(Scenario.tenant_id == tenant.id, Scenario.name == scenario_name)
        .first()
    )

    if scenario is None:
        print(f"[info] Creating naive benchmark scenario '{scenario_name}'...")
        base_config = config_service.create_scenario_from_config(
            config.id,
            {
                "name": scenario_name,
                "max_periods": 40,
                "is_public": False,
                "description": NAIVE_AGENT_DESCRIPTION,
            },
        )
        _apply_default_lead_times(base_config)
        base_config["progression_mode"] = "unsupervised"
        if demand_pattern_override:
            base_config["demand_pattern"] = json.loads(json.dumps(demand_pattern_override))

        creator_id = config.created_by or tenant.admin_id
        scenario = Scenario(
            name=scenario_name,
            created_by=creator_id,
            tenant_id=tenant.id,
            status=ScenarioStatus.CREATED,
            max_periods=base_config.get("max_periods", 40),
            config=base_config,
            demand_pattern=base_config.get("demand_pattern", {}),
            description=NAIVE_AGENT_DESCRIPTION,
            supply_chain_config_id=config.id,
        )
        session.add(scenario)
        session.flush()
        print(f"[success] Created scenario '{scenario_name}' (id={scenario.id}).")
    else:
        print(f"[info] Updating naive benchmark scenario '{scenario_name}' (id={scenario.id}).")
        scenario_config = scenario.config or {}
        if isinstance(scenario_config, str):
            try:
                scenario_config = json.loads(scenario_config)
            except json.JSONDecodeError:
                scenario_config = {}
        _apply_default_lead_times(scenario_config)
        scenario_config["progression_mode"] = "unsupervised"
        scenario_config["max_periods"] = scenario_config.get("max_periods", 40)
        if demand_pattern_override:
            scenario_config["demand_pattern"] = json.loads(json.dumps(demand_pattern_override))
        scenario.config = json.loads(json.dumps(scenario_config))
        scenario.description = NAIVE_AGENT_DESCRIPTION
        scenario.status = ScenarioStatus.CREATED
        scenario.supply_chain_config_id = config.id
        scenario.tenant_id = tenant.id
        creator_id = config.created_by or tenant.admin_id
        if creator_id:
            scenario.created_by = creator_id
        session.add(scenario)

    return scenario


def ensure_pid_game(
    session: Session,
    tenant: Tenant,
    config: SupplyChainConfig,
    *,
    demand_pattern_override: Optional[Dict[str, Any]] = None,
    scenario_name: str = PID_AGENT_SCENARIO_NAME,
) -> Scenario:
    """Ensure a PID heuristic showcase scenario exists for the supply chain configuration."""

    config_service = SupplyChainConfigService(session)
    scenario = (
        session.query(Scenario)
        .filter(Scenario.tenant_id == tenant.id, Scenario.name == scenario_name)
        .first()
    )

    if scenario is None:
        print(f"[info] Creating PID showcase scenario '{scenario_name}'...")
        base_config = config_service.create_scenario_from_config(
            config.id,
            {
                "name": scenario_name,
                "max_periods": 40,
                "is_public": False,
                "description": PID_AGENT_DESCRIPTION,
            },
        )
        _apply_default_lead_times(base_config)
        base_config["progression_mode"] = "unsupervised"
        if demand_pattern_override:
            base_config["demand_pattern"] = json.loads(json.dumps(demand_pattern_override))

        creator_id = config.created_by or tenant.admin_id
        scenario = Scenario(
            name=scenario_name,
            created_by=creator_id,
            tenant_id=tenant.id,
            status=ScenarioStatus.CREATED,
            max_periods=base_config.get("max_periods", 40),
            config=base_config,
            demand_pattern=base_config.get("demand_pattern", {}),
            description=PID_AGENT_DESCRIPTION,
            supply_chain_config_id=config.id,
        )
        session.add(scenario)
        session.flush()
        print(f"[success] Created scenario '{scenario_name}' (id={scenario.id}).")
    else:
        print(f"[info] Updating PID showcase scenario '{scenario_name}' (id={scenario.id}).")
        scenario_config = scenario.config or {}
        if isinstance(scenario_config, str):
            try:
                scenario_config = json.loads(scenario_config)
            except json.JSONDecodeError:
                scenario_config = {}
        _apply_default_lead_times(scenario_config)
        scenario_config["progression_mode"] = "unsupervised"
        scenario_config["max_periods"] = scenario_config.get("max_periods", 40)
        if demand_pattern_override:
            scenario_config["demand_pattern"] = json.loads(json.dumps(demand_pattern_override))
        scenario.config = json.loads(json.dumps(scenario_config))
        scenario.description = PID_AGENT_DESCRIPTION
        scenario.status = ScenarioStatus.CREATED
        scenario.supply_chain_config_id = config.id
        scenario.tenant_id = tenant.id
        creator_id = config.created_by or tenant.admin_id
        if creator_id:
            scenario.created_by = creator_id
        session.add(scenario)

    ensure_ai_agents(
        session,
        scenario,
        PID_AGENT_STRATEGY,
        None,
        None,
    )
    return scenario


def ensure_trm_game(
    session: Session,
    tenant: Tenant,
    config: SupplyChainConfig,
    *,
    demand_pattern_override: Optional[Dict[str, Any]] = None,
    scenario_name: str = TRM_AGENT_SCENARIO_NAME,
) -> Scenario:
    """Ensure a TRM (Tiny Recursive Model) showcase scenario exists for the supply chain configuration."""

    config_service = SupplyChainConfigService(session)
    scenario = (
        session.query(Scenario)
        .filter(Scenario.tenant_id == tenant.id, Scenario.name == scenario_name)
        .first()
    )

    if scenario is None:
        print(f"[info] Creating TRM showcase scenario '{scenario_name}'...")
        base_config = config_service.create_scenario_from_config(
            config.id,
            {
                "name": scenario_name,
                "max_periods": 40,
                "is_public": False,
                "description": TRM_AGENT_DESCRIPTION,
            },
        )
        _apply_default_lead_times(base_config)
        base_config["progression_mode"] = "unsupervised"
        if demand_pattern_override:
            base_config["demand_pattern"] = json.loads(json.dumps(demand_pattern_override))

        creator_id = config.created_by or tenant.admin_id
        scenario = Scenario(
            name=scenario_name,
            created_by=creator_id,
            tenant_id=tenant.id,
            status=ScenarioStatus.CREATED,
            max_periods=base_config.get("max_periods", 40),
            config=base_config,
            demand_pattern=base_config.get("demand_pattern", {}),
            description=TRM_AGENT_DESCRIPTION,
            supply_chain_config_id=config.id,
        )
        session.add(scenario)
        session.flush()
        print(f"[success] Created scenario '{scenario_name}' (id={scenario.id}).")
    else:
        print(f"[info] Updating TRM showcase scenario '{scenario_name}' (id={scenario.id}).")
        scenario_config = scenario.config or {}
        if isinstance(scenario_config, str):
            try:
                scenario_config = json.loads(scenario_config)
            except json.JSONDecodeError:
                scenario_config = {}
        _apply_default_lead_times(scenario_config)
        scenario_config["progression_mode"] = "unsupervised"
        scenario_config["max_periods"] = scenario_config.get("max_periods", 40)
        if demand_pattern_override:
            scenario_config["demand_pattern"] = json.loads(json.dumps(demand_pattern_override))
        scenario.config = json.loads(json.dumps(scenario_config))
        scenario.description = TRM_AGENT_DESCRIPTION
        scenario.status = ScenarioStatus.CREATED
        scenario.supply_chain_config_id = config.id
        scenario.tenant_id = tenant.id
        creator_id = config.created_by or tenant.admin_id
        if creator_id:
            scenario.created_by = creator_id
        session.add(scenario)

    ensure_ai_agents(
        session,
        scenario,
        TRM_AGENT_STRATEGY,
        None,
        None,
    )
    return scenario


def configure_human_players_for_game(
    session: Session,
    tenant: Tenant,
    scenario: Scenario,
) -> None:
    """Ensure the default scenario uses human scenario_users mapped to role-specific accounts."""

    config_payload = _load_scenario_config_payload(scenario)
    slots = _iter_node_slots(config_payload)
    if not slots:
        raise ValueError("Scenario configuration does not define any playable nodes.")

    existing_scenario_users: Dict[str, ScenarioUser] = {
        _player_node_key(scenario_user): scenario_user
        for scenario_user in session.query(ScenarioUser).filter(ScenarioUser.scenario_id == scenario.id).all()
    }
    required_keys: Set[str] = {slot.key for slot in slots}
    role_assignments: Dict[str, Dict[str, int | bool | None]] = {}

    for slot in slots:
        user = _ensure_node_user(session, tenant, slot)
        scenario_user = existing_scenario_users.get(slot.key)
        if scenario_user is None:
            scenario_user = ScenarioUser(
                scenario_id=scenario.id,
                role=_player_role_for_node_type(slot.node_type),
                name=slot.label,
                type=ScenarioUserType.HUMAN,
                strategy=ScenarioUserStrategy.MANUAL,
                is_ai=False,
                ai_strategy=None,
                can_see_demand=slot.can_see_demand,
                user_id=user.id,
                site_key=slot.key,
            )
        else:
            scenario_user.role = _player_role_for_node_type(slot.node_type)
            scenario_user.name = slot.label
            scenario_user.type = ScenarioUserType.HUMAN
            scenario_user.strategy = ScenarioUserStrategy.MANUAL
            scenario_user.is_ai = False
            scenario_user.ai_strategy = None
            scenario_user.can_see_demand = slot.can_see_demand
            scenario_user.user_id = user.id
            scenario_user.llm_model = None
            scenario_user.site_key = slot.key
        session.add(scenario_user)
        session.flush()

        role_assignments[slot.key] = {
            "is_ai": False,
            "agent_config_id": None,
            "user_id": user.id,
            "node_type": slot.node_type,
        }

    for key, scenario_user in existing_scenario_users.items():
        if key in required_keys:
            continue
        session.delete(scenario_user)

    # Remove any lingering agent configs from previous runs
    session.query(AgentConfig).filter(AgentConfig.scenario_id == scenario.id).delete(
        synchronize_session=False
    )
    session.flush()
    session.expire_all()

    try:
        config_payload = scenario.config or {}
        if isinstance(config_payload, str):
            config_payload = json.loads(config_payload)
    except json.JSONDecodeError:
        config_payload = {}

    config_payload["progression_mode"] = "unsupervised"
    scenario.config = json.loads(json.dumps(config_payload))
    scenario.role_assignments = role_assignments
    session.add(scenario)
    session.flush()

    print(
        "[success] Configured human scenario_users for nodes: "
        + ", ".join(slot.label for slot in slots)
    )


def ensure_human_scenario_for_config(
    session: Session,
    tenant: Tenant,
    config: SupplyChainConfig,
    *,
    scenario_name: str,
    description: str,
    recreate: bool = False,
) -> Scenario:
    """Create or update a human-playable scenario for the supplied configuration."""

    config_service = SupplyChainConfigService(session)
    scenario = (
        session.query(Scenario)
        .filter(Scenario.tenant_id == tenant.id, Scenario.name == scenario_name)
        .first()
    )

    if scenario and recreate:
        print(f"[info] Recreating human scenario '{scenario_name}' (id={scenario.id}).")
        session.query(AgentConfig).filter(AgentConfig.scenario_id == scenario.id).delete(
            synchronize_session=False
        )
        session.query(ScenarioUser).filter(ScenarioUser.scenario_id == scenario.id).delete(
            synchronize_session=False
        )
        session.delete(scenario)
        session.flush()
        session.expire_all()
        scenario = None

    if scenario is None:
        print(f"[info] Creating human scenario '{scenario_name}' for configuration '{config.name}'...")
        base_config = config_service.create_scenario_from_config(
            config.id,
            {
                "name": scenario_name,
                "max_periods": 40,
                "is_public": False,
                "description": description,
            },
        )
        _apply_default_lead_times(base_config)
        base_config["progression_mode"] = "unsupervised"

        creator_id = config.created_by or tenant.admin_id
        scenario = Scenario(
            name=base_config.get("name", scenario_name),
            created_by=creator_id,
            tenant_id=tenant.id,
            status=ScenarioStatus.CREATED,
            max_periods=base_config.get("max_periods", 40),
            config=base_config,
            demand_pattern=base_config.get("demand_pattern", {}),
            description=description,
            supply_chain_config_id=config.id,
        )
        session.add(scenario)
        session.flush()
    else:
        print(f"[info] Updating human scenario '{scenario_name}' (id={scenario.id}).")
        scenario_config = scenario.config or {}
        if isinstance(scenario_config, str):
            try:
                scenario_config = json.loads(scenario_config)
            except json.JSONDecodeError:
                scenario_config = {}
        _apply_default_lead_times(scenario_config)
        scenario_config["progression_mode"] = "unsupervised"
        scenario.config = json.loads(json.dumps(scenario_config))
        scenario.description = description
        scenario.status = ScenarioStatus.CREATED
        scenario.supply_chain_config_id = config.id
        scenario.tenant_id = tenant.id
        creator_id = config.created_by or tenant.admin_id
        if creator_id:
            scenario.created_by = creator_id
        session.add(scenario)

    configure_human_players_for_game(session, tenant, scenario)
    return scenario


def ensure_hybrid_human_naive_game(
    session: Session,
    tenant: Tenant,
    config: SupplyChainConfig,
    *,
    scenario_name: str,
    description: str,
    human_site_key: str,
    demand_pattern_override: Optional[Dict[str, Any]] = None,
    recreate: bool = False,
) -> Scenario:
    """
    Create a hybrid scenario with one human scenario_user at specified site and Naive AI agents at all other sites.

    Args:
        session: Database session
        tenant: Tenant for the scenario
        config: Supply chain configuration
        scenario_name: Name of the scenario
        description: Scenario description
        human_site_key: Node key where human scenario_user will be assigned (e.g., "retailer", "wholesaler")
        demand_pattern_override: Optional demand pattern override
        recreate: If True, delete and recreate the scenario

    Returns:
        Created Scenario instance
    """
    # Check if scenario exists
    existing = session.query(Scenario).filter(
        Scenario.tenant_id == tenant.id,
        Scenario.name == scenario_name,
    ).first()

    if existing:
        if not recreate:
            print(f"[info] Scenario '{scenario_name}' already exists; skipping creation.")
            return existing
        print(f"[warn] Deleting existing scenario '{scenario_name}' to recreate it.")
        session.delete(existing)
        session.flush()

    # Create scenario
    config_payload = _load_scenario_config_payload_from_config(
        config, demand_pattern_override=demand_pattern_override
    )
    config_payload["progression_mode"] = "supervised"

    scenario = Scenario(
        name=scenario_name,
        tenant_id=tenant.id,
        supply_chain_config_id=config.id,
        config=config_payload,
        description=description or scenario_name,
        status=ScenarioStatus.NOT_STARTED,
    )
    session.add(scenario)
    session.flush()

    # Get all node slots
    slots = _iter_node_slots(config_payload)
    if not slots:
        raise ValueError(f"Scenario configuration for '{scenario_name}' does not define any playable nodes.")

    # Create scenario_users
    print(f"[info] Creating hybrid scenario_users for scenario '{scenario_name}'...")
    for slot in slots:
        # Skip Market Demand and Market Supply sites
        if slot.node_type in [NodeType.CUSTOMER, NodeType.VENDOR]:
            continue

        if slot.key == human_site_key:
            # Create human scenario_user
            user = _ensure_node_user(session, tenant, slot)
            scenario_user = ScenarioUser(
                scenario_id=scenario.id,
                role=_player_role_for_node_type(slot.node_type),
                name=slot.label,
                type=ScenarioUserType.HUMAN,
                strategy=ScenarioUserStrategy.MANUAL,
                is_ai=False,
                user_id=user.id,
                site_key=slot.key,
                can_see_demand=slot.can_see_demand,
            )
            print(f"[success] Created human scenario_user for {slot.label} (user: {user.email})")
        else:
            # Create Naive AI scenario_user
            scenario_user = ScenarioUser(
                scenario_id=scenario.id,
                role=_player_role_for_node_type(slot.node_type),
                name=f"{slot.label} (Naive AI)",
                type=ScenarioUserType.AI,
                strategy=ScenarioUserStrategy.MANUAL,
                is_ai=True,
                ai_strategy="naive",
                user_id=None,
                site_key=slot.key,
                can_see_demand=slot.can_see_demand,
            )
            print(f"[success] Created Naive AI scenario_user for {slot.label}")

        session.add(scenario_user)

    session.flush()
    print(f"[success] Created hybrid scenario '{scenario_name}' with human at {human_site_key}")
    return scenario


def _ensure_default_players(
    session: Session,
    scenario: Scenario,
    agent_type: str,
    llm_model: Optional[str],
    llm_strategy: Optional[str] = None,
) -> None:
    """Create placeholder AI scenario_users if none exist for the scenario."""
    config_payload = _load_scenario_config_payload(scenario)
    slots = _iter_node_slots(config_payload)
    if not slots:
        raise ValueError("Scenario configuration does not define any playable nodes.")

    existing_scenario_users = {
        _player_node_key(scenario_user): scenario_user
        for scenario_user in session.query(ScenarioUser).filter(ScenarioUser.scenario_id == scenario.id).all()
    }

    print("[info] Ensuring AI scenario_users exist for all nodes...")
    for slot in slots:
        scenario_user = existing_scenario_users.get(slot.key)
        if scenario_user is None:
            scenario_user = ScenarioUser(
                scenario_id=scenario.id,
                role=_player_role_for_node_type(slot.node_type),
                name=f"{slot.label} (AI)",
                site_key=slot.key,
            )
        scenario_user.type = ScenarioUserType.AI
        scenario_user.is_ai = True
        scenario_user.ai_strategy = agent_type
        scenario_user.strategy = ScenarioUserStrategy.MANUAL
        scenario_user.user_id = None
        scenario_user.can_see_demand = slot.can_see_demand
        scenario_user.llm_model = llm_model or DEFAULT_LLM_MODEL if agent_type.startswith("llm") else None
        session.add(scenario_user)
    session.flush()


def ensure_ai_agents(
    session: Session,
    scenario: Scenario,
    agent_type: str,
    llm_model: Optional[str],
    llm_strategy: Optional[str] = None,
) -> None:
    """Assign AI agents to each role in the scenario and switch to auto progression."""
    _ensure_default_players(session, scenario, agent_type, llm_model, llm_strategy)

    config_payload = _load_scenario_config_payload(scenario)
    slots = _iter_node_slots(config_payload)
    existing_scenario_users = {
        _player_node_key(scenario_user): scenario_user
        for scenario_user in session.query(ScenarioUser).filter(ScenarioUser.scenario_id == scenario.id).all()
    }
    role_assignments: Dict[str, Dict[str, Any]] = {}

    for slot in slots:
        scenario_user = existing_scenario_users.get(slot.key)
        if scenario_user is None:
            scenario_user = ScenarioUser(
                scenario_id=scenario.id,
                role=_player_role_for_node_type(slot.node_type),
                name=f"{slot.label} ({agent_type})",
                site_key=slot.key,
            )
        scenario_user.is_ai = True
        scenario_user.type = ScenarioUserType.AI
        scenario_user.ai_strategy = agent_type
        scenario_user.strategy = ScenarioUserStrategy.MANUAL
        scenario_user.user_id = None
        scenario_user.llm_model = llm_model or DEFAULT_LLM_MODEL if agent_type.startswith("llm") else None
        scenario_user.can_see_demand = slot.can_see_demand
        scenario_user.role = _player_role_for_node_type(slot.node_type)
        session.add(scenario_user)
        session.flush()

        normalized_slot_key = _normalise_node_key(slot.key)
        agent_config = (
            session.query(AgentConfig)
            .filter(AgentConfig.scenario_id == scenario.id, AgentConfig.role == normalized_slot_key)
            .first()
        )
        if agent_config is None:
            agent_config = AgentConfig(
                scenario_id=scenario.id,
                role=normalized_slot_key,
                agent_type=agent_type,
                config={},
            )
        agent_config.agent_type = agent_type
        agent_config.config = agent_config.config or {}
        if agent_type.startswith("llm"):
            agent_config.config["llm_model"] = llm_model or DEFAULT_LLM_MODEL
            if llm_strategy:
                agent_config.config["llm_strategy"] = llm_strategy
            else:
                agent_config.config.pop("llm_strategy", None)
        else:
            agent_config.config.pop("llm_model", None)
            agent_config.config.pop("llm_strategy", None)
        session.add(agent_config)
        session.flush()

        role_assignments[slot.key] = {
            "is_ai": True,
            "agent_config_id": agent_config.id,
            "user_id": None,
            "strategy": agent_type,
            "node_type": slot.node_type,
        }

    config_payload["progression_mode"] = "unsupervised"
    config_payload.setdefault("autonomy", {})
    config_payload["autonomy"].update({"strategy": agent_type})
    if agent_type.startswith("llm"):
        config_payload["autonomy"]["llm_model"] = llm_model or DEFAULT_LLM_MODEL
        if llm_strategy:
            config_payload["autonomy"]["llm_strategy"] = llm_strategy
        else:
            config_payload["autonomy"].pop("llm_strategy", None)
    else:
        config_payload.get("autonomy", {}).pop("llm_model", None)
        config_payload.get("autonomy", {}).pop("llm_strategy", None)

    scenario.config = json.loads(json.dumps(config_payload))
    scenario.role_assignments = role_assignments
    session.add(scenario)
    session.flush()

    agent_label = agent_type
    if agent_type.startswith("llm"):
        details = [llm_model or DEFAULT_LLM_MODEL]
        if llm_strategy:
            details.append(llm_strategy)
        agent_label += f" ({', '.join(details)})"
    print(
        "[success] Assigned AI agents (%s) to nodes: %s"
        % (agent_label, ", ".join(slot.label for slot in slots))
    )


def ensure_role_users(session: Session, tenant: Tenant) -> None:
    """Legacy helper retained for compatibility; node-scoped accounts are created per scenario."""
    print(
        "[info] Skipping legacy role user bootstrap; node-specific users are created when configuring scenarios."
    )


def _resolve_training_device(preferred: str = "cuda") -> str:
    """Return an available training device, falling back to CPU when needed."""

    try:
        import torch  # type: ignore
    except Exception:
        print("[warn] PyTorch not available; defaulting training to CPU.")
        return "cpu"

    if preferred == "cuda" and torch.cuda.is_available():
        return "cuda"
    if preferred == "cuda":
        print("[warn] CUDA unavailable; training will run on CPU.")
    return "cuda" if torch.cuda.is_available() else "cpu"


def _apply_pid_params_to_games(
    session: Session,
    config_id: int,
    pid_params: Optional[Dict[str, float]],
) -> None:
    """Update all PID agent configs for scenarios using the supplied supply-chain config."""

    if not pid_params:
        return

    scenario_ids = [
        row.id
        for row in session.query(Scenario.id).filter(Scenario.supply_chain_config_id == config_id)
    ]
    if not scenario_ids:
        return

    for scenario_id in scenario_ids:
        agent_rows = session.query(AgentConfig).filter(
            AgentConfig.scenario_id == scenario_id,
            AgentConfig.agent_type == PID_AGENT_STRATEGY,
        )
        for agent_row in agent_rows:
            config = dict(agent_row.config or {})
            config.update(pid_params)
            agent_row.config = config
            session.add(agent_row)


def _run_post_seed_tasks(
    session: Session,
    config: SupplyChainConfig,
    *,
    force_dataset: bool = False,
    force_training: bool = False,
    run_dataset: bool = True,
    run_training: bool = True,
    agent_strategy: Optional[str] = None,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Run data generation and training workflows for the supplied configuration ID."""

    if not run_dataset and not run_training:
        print(f"[info] Skipping dataset generation and training for config '{config.name}'.")
        return {"dataset": None, "model": None, "device": None}

    if not TRAINING_SCRIPTS_DIR.exists():
        print("[warn] Training scripts directory not found; skipping automatic training.")
        return {"dataset": None, "model": None, "device": None}

    config_id = config.id
    slug = _slugify(config.name)

    artifacts: Dict[str, Optional[Dict[str, Any]]] = {
        "dataset": None,
        "model": None,
        "device": None,
    }

    dataset_payload: Optional[Dict[str, Any]] = None
    if run_dataset:
        dataset_cmd = [
            sys.executable,
            str(TRAINING_SCRIPTS_DIR / "generate_simpy_dataset.py"),
            "--config-id",
            str(config_id),
        ]
        if force_dataset:
            dataset_cmd.append("--force")
        if agent_strategy:
            dataset_cmd.extend(["--agent-strategy", str(agent_strategy)])
            if str(agent_strategy).strip().lower() != "llm":
                dataset_cmd.append("--disable-simpy")

        print(f"[info] Generate SimPy dataset (config_id={config_id})...")
        try:
            dataset_completed = subprocess.run(
                dataset_cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            print(f"[warn] Dataset tooling unavailable: {exc}")
        except subprocess.CalledProcessError as exc:
            print(f"[warn] Dataset generation failed (exit={exc.returncode}).")
            if exc.stdout:
                print(exc.stdout.strip())
            if exc.stderr:
                print(exc.stderr.strip(), file=sys.stderr)
        else:
            dataset_stdout = dataset_completed.stdout.strip()
            if dataset_stdout:
                try:
                    dataset_payload = json.loads(dataset_stdout.splitlines()[-1])
                except json.JSONDecodeError:
                    print(dataset_stdout)
            if dataset_completed.stderr:
                print(dataset_completed.stderr.strip(), file=sys.stderr)
    else:
        print(f"[info] SimPy dataset generation skipped for config_id={config_id}.")

    if dataset_payload:
        status = dataset_payload.get("status", "unknown")
        print(f"[success] Generate SimPy dataset: {status}")
        if dataset_payload.get("path"):
            original_path = Path(dataset_payload["path"])
            target_path = original_path.with_name(f"{slug}_dataset{original_path.suffix}")
            if original_path != target_path and original_path.exists():
                if target_path.exists():
                    target_path.unlink()
                original_path.rename(target_path)
                dataset_payload["path"] = str(target_path)
            dataset_payload["filename"] = Path(dataset_payload["path"]).name

        best_dataset_path = dataset_payload.get("best_dataset")
        if best_dataset_path:
            original_best = Path(best_dataset_path)
            target_best = original_best.with_name(f"{slug}_pid_dataset{original_best.suffix}")
            if original_best != target_best and original_best.exists():
                if target_best.exists():
                    target_best.unlink()
                original_best.rename(target_best)
                dataset_payload["best_dataset"] = str(target_best)

        training_dataset = dataset_payload.get("best_dataset") or dataset_payload.get("path")
        if training_dataset:
            dataset_payload["training_dataset"] = training_dataset
            print(f"          Dataset: {training_dataset}")

        pid_tuning = dataset_payload.get("pid_tuning") or {}
        pid_params = pid_tuning.get("best_params")
        if pid_params:
            _apply_pid_params_to_games(session, config_id, pid_params)

        artifacts["dataset"] = dataset_payload

    device = _resolve_training_device()
    artifacts["device"] = {"preferred": "cuda", "resolved": device}

    if not run_training:
        print(f"[info] Temporal GNN training skipped for config_id={config_id}.")
        return artifacts

    training_cmd = [
        sys.executable,
        str(TRAINING_SCRIPTS_DIR / "train_gpu_default.py"),
        "--config-id",
        str(config_id),
        "--device",
        device,
    ]
    dataset_path = (dataset_payload or {}).get("training_dataset")
    if dataset_path:
        training_cmd.extend(["--dataset", dataset_path])
    if force_training:
        training_cmd.append("--force")

    print(f"[info] Train temporal GNN ({device}) (config_id={config_id})...")
    training_completed = None
    training_stdout = ""
    used_device = device

    try:
        training_completed = subprocess.run(
            training_cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        print(f"[warn] Training tooling unavailable: {exc}")
    except subprocess.CalledProcessError as exc:
        if device == "cuda":
            print(f"[warn] CUDA training failed ({exc}); retrying on CPU.")
            if exc.stdout:
                print(exc.stdout.strip())
            if exc.stderr:
                print(exc.stderr.strip(), file=sys.stderr)
            cpu_cmd = list(training_cmd)
            if "--device" in cpu_cmd:
                device_index = cpu_cmd.index("--device") + 1
                cpu_cmd[device_index] = "cpu"
            else:
                cpu_cmd.extend(["--device", "cpu"])
            used_device = "cpu"
            artifacts["device"]["resolved"] = "cpu"
            try:
                training_completed = subprocess.run(
                    cpu_cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as cpu_exc:
                if cpu_exc.stdout:
                    print(cpu_exc.stdout.strip())
                if cpu_exc.stderr:
                    print(cpu_exc.stderr.strip(), file=sys.stderr)
                raise
        else:
            if exc.stdout:
                print(exc.stdout.strip())
            if exc.stderr:
                print(exc.stderr.strip(), file=sys.stderr)
            print("[warn] Training aborted; proceeding without updated model.")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] Training step encountered an unexpected error: {exc}")
    
    training_stdout = training_completed.stdout.strip() if training_completed else ""
    training_payload: Optional[Dict[str, Any]] = None
    if training_stdout:
        try:
            training_payload = json.loads(training_stdout.splitlines()[-1])
        except json.JSONDecodeError:
            print(training_stdout)
    if training_completed and training_completed.stderr:
        print(training_completed.stderr.strip(), file=sys.stderr)

    if training_payload:
        status = training_payload.get("status", "unknown")
        print(f"[success] Train temporal GNN: {status}")
        if training_payload.get("model_path"):
            model_path = Path(training_payload["model_path"])
            target_model_path = model_path.with_name(f"{slug}_temporal_gnn.pt")
            if model_path != target_model_path:
                if target_model_path.exists():
                    target_model_path.unlink()
                model_path.rename(target_model_path)
                training_payload["model_path"] = str(target_model_path)
            print(f"          Model: {training_payload['model_path']}")
        if dataset_payload and training_payload:
            artifact = SupplyChainTrainingArtifact(
                config_id=config_id,
                dataset_name=Path(
                    dataset_payload.get("training_dataset", dataset_payload["path"])
                ).name,
                model_name=Path(training_payload["model_path"]).name,
            )
            session.add(artifact)
            session.commit()
        artifacts["model"] = training_payload

    return artifacts


def _purge_existing_games(session: Session) -> None:
    """Remove all scenario records and related AI configurations."""

    print("[info] Removing existing scenarios, scenario_users, and agent configurations...")
    session.query(ScenarioUserAction).delete(synchronize_session=False)
    session.query(Period).delete(synchronize_session=False)
    session.query(SupervisorAction).delete(synchronize_session=False)
    session.query(AgentConfig).delete(synchronize_session=False)
    session.query(ScenarioUser).delete(synchronize_session=False)
    session.query(Scenario).delete(synchronize_session=False)
    session.flush()
    session.expire_all()


def _configure_scenario_agents(
    session: Session,
    scenario: Scenario,
    agent_type: str,
    *,
    override_pct: Optional[float] = None,
    llm_model: Optional[str] = None,
    llm_strategy: Optional[str] = None,
    can_see_demand_all: bool = False,
    assignment_scope: str = "node",
) -> None:
    """Ensure scenario_users and agent configs exist for a scenario using the specified agent type."""

    config_payload = _load_scenario_config_payload(scenario)
    slots = _iter_node_slots(config_payload)
    existing_assignment_payload = dict(scenario.role_assignments or {})
    player_rows = list(session.query(ScenarioUser).filter(ScenarioUser.scenario_id == scenario.id))
    player_lookup: Dict[int, ScenarioUser] = {scenario_user.id: scenario_user for scenario_user in player_rows}
    existing_scenario_users: Dict[str, ScenarioUser] = {}
    for assignment_key, payload in existing_assignment_payload.items():
        key = _normalise_node_key(assignment_key)
        if not key:
            continue
        pid = payload.get("scenario_user_id")
        if pid is None:
            continue
        scenario_user = player_lookup.get(pid)
        if scenario_user:
            existing_scenario_users[key] = scenario_user
    if not existing_scenario_users:
        existing_scenario_users = {
            _player_node_key(scenario_user): scenario_user
            for scenario_user in player_rows
        }

    assignments: Dict[str, Dict[str, Optional[int]]] = {}
    is_llm_variant = agent_type.startswith("llm")

    scope = (assignment_scope or "node").strip().lower()
    grouped_slots: Dict[str, List[NodeSlot]] = defaultdict(list)
    if scope == "node_type":
        for slot in slots:
            grouped_slots[slot.node_type].append(slot)
        plans: List[Dict[str, Any]] = []
        for node_type, bucket in grouped_slots.items():
            assignment_key = _normalise_node_key(node_type)
            display_label = node_type.replace("_", " ").title()
            plans.append(
                {
                    "assignment_key": assignment_key,
                    "role": _player_role_for_node_type(node_type),
                    "label": f"{display_label} ({agent_type})",
                    "slots": list(bucket),
                    "node_keys": [slot.key for slot in bucket],
                    "can_see_demand": True if can_see_demand_all else any(slot.can_see_demand for slot in bucket),
                }
            )
    else:
        plans = [
            {
                "assignment_key": slot.key,
                "role": _player_role_for_node_type(slot.node_type),
                "label": f"{slot.label} ({agent_type})",
                "slots": [slot],
                "node_keys": [slot.key],
                "can_see_demand": True if can_see_demand_all else slot.can_see_demand,
            }
            for slot in slots
        ]

    player_assignments_payload: List[Dict[str, Any]] = []

    for plan in plans:
        assignment_key = plan["assignment_key"]
        normalised_key = _normalise_node_key(assignment_key)
        if not normalised_key:
            normalised_key = plan["node_keys"][0]
        scenario_user = existing_scenario_users.get(normalised_key)
        if scenario_user is None:
            scenario_user = ScenarioUser(
                scenario_id=scenario.id,
                name=plan["label"],
                role=plan["role"],
                site_key=normalised_key,
            )

        scenario_user.type = ScenarioUserType.AI
        scenario_user.is_ai = True
        scenario_user.ai_strategy = agent_type
        scenario_user.strategy = ScenarioUserStrategy.MANUAL
        scenario_user.user_id = None
        scenario_user.can_see_demand = plan["can_see_demand"]
        scenario_user.llm_model = llm_model or DEFAULT_LLM_MODEL if is_llm_variant else None
        scenario_user.role = plan["role"]
        session.add(scenario_user)
        session.flush()

        agent_config = (
            session.query(AgentConfig)
            .filter(AgentConfig.scenario_id == scenario.id, AgentConfig.role == normalised_key)
            .first()
        )
        if agent_config is None:
            agent_config = AgentConfig(
                scenario_id=scenario.id,
                role=normalised_key,
                agent_type=agent_type,
                config={},
            )
        agent_config.agent_type = agent_type
        agent_config.config = agent_config.config or {}
        if is_llm_variant:
            agent_config.config["llm_model"] = llm_model or DEFAULT_LLM_MODEL
            if llm_strategy:
                agent_config.config["llm_strategy"] = llm_strategy
            else:
                agent_config.config.pop("llm_strategy", None)
        else:
            agent_config.config.pop("llm_model", None)
            agent_config.config.pop("llm_strategy", None)

        session.add(agent_config)
        session.flush()

        assignments[normalised_key] = {
            "is_ai": True,
            "agent_config_id": agent_config.id,
            "user_id": None,
            "strategy": agent_type,
            "node_type": plan["role"].value if hasattr(plan["role"], "value") else str(plan["role"]),
            "node_keys": plan["node_keys"],
            "scenario_user_id": scenario_user.id,
        }

        player_assignments_payload.append(
            {
                "role": plan["role"].value if hasattr(plan["role"], "value") else str(plan["role"]),
                "assignment_key": normalised_key,
                "node_keys": plan["node_keys"],
                "scenario_user_type": ScenarioUserType.AI.value,
                "strategy": agent_type,
                "can_see_demand": plan["can_see_demand"],
                "llm_model": llm_model,
                "autonomy_override_pct": override_pct,
            }
        )

    for key, scenario_user in existing_scenario_users.items():
        if key in assignments:
            continue
        session.delete(scenario_user)

    if override_pct is not None:
        overrides = {plan["assignment_key"]: override_pct for plan in plans}
        config_payload["autonomy_overrides"] = overrides

    if is_llm_variant:
        autonomy_cfg = config_payload.setdefault("autonomy", {})
        autonomy_cfg["llm_model"] = llm_model or DEFAULT_LLM_MODEL
        if llm_strategy:
            autonomy_cfg["llm_strategy"] = llm_strategy
        else:
            autonomy_cfg.pop("llm_strategy", None)

    # Agent-led scenarios should always auto-progress.
    config_payload["progression_mode"] = "unsupervised"
    config_payload["player_assignments"] = player_assignments_payload
    config_payload["player_assignment_scope"] = scope
    scenario.config = json.loads(json.dumps(config_payload))
    scenario.role_assignments = assignments
    session.add(scenario)


def ensure_autonomy_games(
    session: Session,
    tenant: Tenant,
    config: SupplyChainConfig,
    artifacts: Dict[str, Optional[Dict[str, Any]]],
    *,
    recreate: bool,
    name_suffix: Optional[str] = None,
) -> None:
    """Create or update showcase scenarios for the Autonomy agent variants."""

    config_service = SupplyChainConfigService(session)
    dataset_info = artifacts.get("dataset") or {}
    dataset_path_for_agents = (
        dataset_info.get("training_dataset")
        or dataset_info.get("best_dataset")
        or dataset_info.get("path")
    )
    model_info = artifacts.get("model") or {}

    for spec in AUTONOMY_AGENT_SPECS:
        scenario_name = spec["name"] if not name_suffix else f"{spec['name']} ({name_suffix})"
        scenario = (
            session.query(Scenario)
            .filter(Scenario.tenant_id == tenant.id, Scenario.name == scenario_name)
            .first()
        )

        if scenario and recreate:
            print(f"[info] Recreating showcase scenario '{scenario_name}' (id={scenario.id}).")
            # Remove dependent rows before deleting the scenario so the FK constraints stay happy
            session.query(AgentConfig).filter(AgentConfig.scenario_id == scenario.id).delete(
                synchronize_session=False
            )
            session.query(ScenarioUser).filter(ScenarioUser.scenario_id == scenario.id).delete(
                synchronize_session=False
            )
            session.delete(scenario)
            session.flush()
            session.expire_all()
            scenario = None

        if scenario is None:
            print(f"[info] Creating showcase scenario '{scenario_name}'...")
            base_config = config_service.create_scenario_from_config(
                config.id,
                {
                    "name": scenario_name,
                    "max_periods": 40,
                    "is_public": True,
                    "description": spec["description"],
                },
            )
            _apply_default_lead_times(base_config)
            base_config["progression_mode"] = "unsupervised"
            base_config.setdefault("autonomy", {})
            base_config["autonomy"].update(
                {
                    "strategy": spec["agent_type"],
                    "dataset": dataset_path_for_agents,
                    "model_path": model_info.get("model_path"),
                }
            )
            if spec.get("llm_model"):
                base_config["autonomy"]["llm_model"] = spec["llm_model"]
                base_config.setdefault("info_sharing", {}).update({"visibility": "full"})
            if spec.get("llm_strategy"):
                base_config["autonomy"]["llm_strategy"] = spec["llm_strategy"]
            if spec["override_pct"] is not None:
                override_nodes = {
                    slot.key: spec["override_pct"] for slot in _iter_node_slots(base_config)
                }
                base_config.setdefault("autonomy_overrides", {}).update(override_nodes)

            creator_id = config.created_by or tenant.admin_id
            scenario = Scenario(
                name=scenario_name,
                created_by=creator_id,
                tenant_id=tenant.id,
                status=ScenarioStatus.CREATED,
                max_periods=base_config.get("max_periods", 40),
                config=base_config,
                demand_pattern=base_config.get("demand_pattern", {}),
                description=spec["description"],
                supply_chain_config_id=config.id,
            )
            session.add(scenario)
            session.flush()
        else:
            print(
                f"[info] Updating showcase scenario '{scenario_name}' (id={scenario.id}) with latest training artifacts."
            )
            scenario_config = scenario.config or {}
            if isinstance(scenario_config, str):
                try:
                    scenario_config = json.loads(scenario_config)
                except json.JSONDecodeError:
                    scenario_config = {}
            _apply_default_lead_times(scenario_config)
            scenario.supply_chain_config_id = config.id
            scenario.tenant_id = tenant.id
            creator_id = config.created_by or tenant.admin_id
            if creator_id:
                scenario.created_by = creator_id
            scenario_config.setdefault("autonomy", {})
            scenario_config["autonomy"].update(
                {
                    "strategy": spec["agent_type"],
                    "dataset": dataset_path_for_agents,
                    "model_path": model_info.get("model_path"),
                }
            )
            if spec.get("llm_model"):
                scenario_config["autonomy"]["llm_model"] = spec["llm_model"]
                scenario_config.setdefault("info_sharing", {}).update({"visibility": "full"})
            if spec.get("llm_strategy"):
                scenario_config["autonomy"]["llm_strategy"] = spec["llm_strategy"]
            else:
                scenario_config["autonomy"].pop("llm_strategy", None)
            if spec["override_pct"] is not None:
                override_nodes = {
                    slot.key: spec["override_pct"] for slot in _iter_node_slots(scenario_config)
                }
                scenario_config.setdefault("autonomy_overrides", {}).update(override_nodes)
            scenario_config["progression_mode"] = "unsupervised"
            scenario_config["max_periods"] = 40
            scenario.config = json.loads(json.dumps(scenario_config))
            session.add(scenario)

        _configure_scenario_agents(
            session,
            scenario,
            spec["agent_type"],
            override_pct=spec.get("override_pct"),
            llm_model=spec.get("llm_model"),
            llm_strategy=spec.get("llm_strategy"),
        can_see_demand_all=spec.get("can_see_demand_all", False),
    )



def _build_config_specs() -> List[Dict[str, Any]]:
    return [
        {
            "config_name": INVENTORY_CONFIG_NAME,
            "config_description": "Inventory-only default simulation config (no BOM)",
            "demand_pattern": None,
            "scenario_name": DEFAULT_SCENARIO_NAME,
            "naive_scenario_name": NAIVE_AGENT_SCENARIO_NAME,
            "pid_scenario_name": PID_AGENT_SCENARIO_NAME,
            "trm_scenario_name": TRM_AGENT_SCENARIO_NAME,
            "autonomy_suffix": None,
            "tenant_name": DEFAULT_TENANT_NAME,
            "tenant_description": DEFAULT_TENANT_DESCRIPTION,
            "admin_username": DEFAULT_ADMIN_USERNAME,
            "admin_email": DEFAULT_ADMIN_EMAIL,
            "admin_full_name": DEFAULT_ADMIN_FULL_NAME,
            "manufacturer_master_type": NodeType.INVENTORY.value,
        },
        {
            "config_name": "Three FG Beer Scenario",
            "config_description": "Inventory-only simulation with three finished goods (Lager, IPA, Dark).",
            "demand_pattern": None,
            "scenario_name": f"{DEFAULT_SCENARIO_NAME} (Three FG)",
            "naive_scenario_name": f"{NAIVE_AGENT_SCENARIO_NAME} (Three FG)",
            "pid_scenario_name": f"{PID_AGENT_SCENARIO_NAME} (Three FG)",
            "trm_scenario_name": f"{TRM_AGENT_SCENARIO_NAME} (Three FG)",
            "autonomy_suffix": "Three FG Beer Scenario",
            "tenant_name": THREE_FG_TENANT_NAME,
            "tenant_description": THREE_FG_TENANT_DESCRIPTION,
            "admin_username": THREE_FG_ADMIN_USERNAME,
            "admin_email": THREE_FG_ADMIN_EMAIL,
            "admin_full_name": THREE_FG_ADMIN_FULL_NAME,
            "ensure_func": ensure_three_fg_inventory_config,
            "ensure_kwargs": {
                "name": "Three FG Beer Scenario",
                "description": "Inventory-only simulation with three finished goods (Lager, IPA, Dark).",
                "demand_pattern_override": None,
            },
        },
        {
            "config_name": VARIABLE_BEER_SCENARIO_TENANT_NAME,
            "config_description": "Lognormal-demand simulation with three finished goods",
            "demand_pattern": _lognormal_pattern_from_median_variance(8.0, 8.0),
            "scenario_name": f"{DEFAULT_SCENARIO_NAME} (Variable Beer Scenario)",
            "naive_scenario_name": f"{NAIVE_AGENT_SCENARIO_NAME} (Variable Beer Scenario)",
            "pid_scenario_name": f"{PID_AGENT_SCENARIO_NAME} (Variable Beer Scenario)",
            "trm_scenario_name": f"{TRM_AGENT_SCENARIO_NAME} (Variable Beer Scenario)",
            "autonomy_suffix": "Variable Beer Scenario",
            "tenant_name": VARIABLE_BEER_SCENARIO_TENANT_NAME,
            "tenant_description": VARIABLE_BEER_SCENARIO_TENANT_DESCRIPTION,
            "admin_username": VARIABLE_BEER_SCENARIO_ADMIN_USERNAME,
            "admin_email": VARIABLE_BEER_SCENARIO_ADMIN_EMAIL,
            "admin_full_name": VARIABLE_BEER_SCENARIO_ADMIN_FULL_NAME,
            "ensure_func": ensure_three_fg_inventory_config,
            "ensure_kwargs": {
                "name": VARIABLE_BEER_SCENARIO_TENANT_NAME,
                "description": "Lognormal-demand simulation with three finished goods",
                "demand_pattern_override": _lognormal_pattern_from_median_variance(8.0, 8.0),
            },
        },
        {
            "config_name": "Case Beer Scenario",
            "config_description": "Case manufacturer consumes Six-Packs (1:4 BOM) using manufacturer master node type.",
            "demand_pattern": None,
            "scenario_name": f"{DEFAULT_SCENARIO_NAME} (Case Beer Scenario)",
            "naive_scenario_name": f"{NAIVE_AGENT_SCENARIO_NAME} (Case Beer Scenario)",
            "pid_scenario_name": f"{PID_AGENT_SCENARIO_NAME} (Case Beer Scenario)",
            "trm_scenario_name": f"{TRM_AGENT_SCENARIO_NAME} (Case Beer Scenario)",
            "autonomy_suffix": "Case Beer Scenario",
            "tenant_name": DEFAULT_TENANT_NAME,
            "tenant_description": DEFAULT_TENANT_DESCRIPTION,
            "admin_username": DEFAULT_ADMIN_USERNAME,
            "admin_email": DEFAULT_ADMIN_EMAIL,
            "admin_full_name": DEFAULT_ADMIN_FULL_NAME,
            "manufacturer_master_type": NodeType.MANUFACTURER.value,
            "ensure_func": ensure_case_config,
        },
        {
            "config_name": "Six-Pack Beer Scenario",
            "config_description": "Case Mfg assembles Cases (1:4 BOM) fed by Six-Pack Mfg converting Bottles (1:6 BOM).",
            "demand_pattern": None,
            "scenario_name": f"{DEFAULT_SCENARIO_NAME} (Six-Pack Beer Scenario)",
            "naive_scenario_name": f"{NAIVE_AGENT_SCENARIO_NAME} (Six-Pack Beer Scenario)",
            "pid_scenario_name": f"{PID_AGENT_SCENARIO_NAME} (Six-Pack Beer Scenario)",
            "trm_scenario_name": f"{TRM_AGENT_SCENARIO_NAME} (Six-Pack Beer Scenario)",
            "autonomy_suffix": "Six-Pack Beer Scenario",
            "tenant_name": DEFAULT_TENANT_NAME,
            "tenant_description": DEFAULT_TENANT_DESCRIPTION,
            "admin_username": DEFAULT_ADMIN_USERNAME,
            "admin_email": DEFAULT_ADMIN_EMAIL,
            "admin_full_name": DEFAULT_ADMIN_FULL_NAME,
            "ensure_func": ensure_six_pack_config,
        },
        {
            "config_name": "Bottle Beer Scenario",
            "config_description": "Bottle Mfg converts Ingredients to Bottles (1:1), Six-Pack Mfg makes Six-Packs (1:6), and Case Mfg builds Cases (1:4).",
            "demand_pattern": None,
            "scenario_name": f"{DEFAULT_SCENARIO_NAME} (Bottle Beer Scenario)",
            "naive_scenario_name": f"{NAIVE_AGENT_SCENARIO_NAME} (Bottle Beer Scenario)",
            "pid_scenario_name": f"{PID_AGENT_SCENARIO_NAME} (Bottle Beer Scenario)",
            "autonomy_suffix": "Bottle Beer Scenario",
            "tenant_name": DEFAULT_TENANT_NAME,
            "tenant_description": DEFAULT_TENANT_DESCRIPTION,
            "admin_username": DEFAULT_ADMIN_USERNAME,
            "admin_email": DEFAULT_ADMIN_EMAIL,
            "admin_full_name": DEFAULT_ADMIN_FULL_NAME,
            "ensure_func": ensure_bottle_config,
        },
    ]


def get_config_specs(config_names: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    specs = _build_config_specs()
    if config_names is None:
        return specs
    spec_lookup = {spec["config_name"]: spec for spec in specs}
    missing = [name for name in config_names if name not in spec_lookup]
    if missing:
        raise ValueError(f"Unknown config specs requested: {', '.join(missing)}")
    return [spec_lookup[name] for name in config_names]


def seed_default_data(
    session: Session,
    options: Optional[SeedOptions] = None,
    *,
    config_specs_override: Optional[Sequence[Dict[str, Any]]] = None,
    include_complex: bool = True,
) -> None:
    """Run the seeding workflow using the provided session."""

    if options is None:
        options = SeedOptions()

    if options.reset_games:
        _purge_existing_games(session)

    strategy, llm_model, probe_detail = resolve_default_agent_strategy(
        options.preferred_agent_strategy,
        options.preferred_llm_model,
    )

    if options.assign_ai_agents and probe_detail and strategy != "llm":
        print(f"[warn] Autonomy LLM check failed: {probe_detail}")

    config_specs = list(config_specs_override or get_config_specs())

    for spec in config_specs:
        slug = _slugify(spec["config_name"])
        tenant, _ = ensure_tenant_with_admin(
            session,
            tenant_name=spec.get("tenant_name") or spec["config_name"],
            tenant_description=spec.get("tenant_description") or f"{spec['config_name']} tenant",
            admin_username=spec.get("admin_username") or f"{slug}_admin",
            admin_email=spec.get("admin_email") or f"{slug}_admin@autonomy.ai",
            admin_full_name=spec.get("admin_full_name") or f"{spec['config_name']} Administrator",
            password=DEFAULT_PASSWORD,
        )
        ensure_role_users(session, tenant)

        ensure_func = spec.get("ensure_func")
        ensure_kwargs = spec.get("ensure_kwargs") or {}
        config = (
            ensure_func(session, tenant, **ensure_kwargs)
            if ensure_func
            else ensure_supply_chain_config(
                session,
                tenant,
                name=spec["config_name"],
                description=spec["config_description"],
                demand_pattern_override=spec["demand_pattern"],
                manufacturer_master_type=spec.get("manufacturer_master_type"),
            )
        )

        scenario = ensure_default_game(
            session,
            tenant,
            config=config if ensure_func else None,
            config_name=spec["config_name"],
            config_description=spec["config_description"],
            demand_pattern_override=spec["demand_pattern"],
            scenario_name=spec["scenario_name"],
            manufacturer_master_type=spec.get("manufacturer_master_type"),
        )

        if options.assign_ai_agents:
            ensure_ai_agents(
                session,
                scenario,
                strategy,
                llm_model,
                spec.get("llm_strategy"),
            )
        else:
            configure_human_players_for_game(session, tenant, scenario)

        session.flush()
        session.commit()

        artifacts: Dict[str, Optional[Dict[str, Any]]] = {
            "dataset": None,
            "model": None,
            "device": None,
        }

        naive_scenario = ensure_naive_unsupervised_game(
            session,
            tenant,
            config,
            demand_pattern_override=spec["demand_pattern"],
            scenario_name=spec["naive_scenario_name"],
        )
        _configure_scenario_agents(session, naive_scenario, "naive", assignment_scope="node")
        session.flush()
        session.commit()

        # Skip Node Types variant for single-node-per-role configs (e.g., default simulation)

        pid_scenario = ensure_pid_game(
            session,
            tenant,
            config,
            demand_pattern_override=spec["demand_pattern"],
            scenario_name=spec["pid_scenario_name"],
        )
        _configure_scenario_agents(session, pid_scenario, PID_AGENT_STRATEGY, assignment_scope="node")
        session.flush()
        session.commit()

        trm_scenario = ensure_trm_game(
            session,
            tenant,
            config,
            demand_pattern_override=spec["demand_pattern"],
            scenario_name=spec.get("trm_scenario_name", f"{TRM_AGENT_SCENARIO_NAME} ({spec['config_name']})"),
        )
        _configure_scenario_agents(session, trm_scenario, TRM_AGENT_STRATEGY, assignment_scope="node")
        session.flush()
        session.commit()

        # Create hybrid human/naive scenarios for Default Beer Scenario config
        if spec["config_name"] == INVENTORY_CONFIG_NAME:  # "Default Beer Scenario" (DB lookup name)
            print("[info] Creating hybrid human/Naive AI scenarios for default simulation...")

            # Define the 4 hybrid scenarios (one for each playable site)
            hybrid_site_configs = [
                ("retailer", "Retailer Simulation", "Play as Retailer with Naive AI teammates"),
                ("wholesaler", "Wholesaler Simulation", "Play as Wholesaler with Naive AI teammates"),
                ("distributor", "Distributor Simulation", "Play as Distributor with Naive AI teammates"),
                ("factory", "Manufacturer Simulation", "Play as Manufacturer with Naive AI teammates"),
            ]

            for site_key, scenario_name, scenario_desc in hybrid_site_configs:
                hybrid_game = ensure_hybrid_human_naive_game(
                    session,
                    tenant,
                    config,
                    scenario_name=scenario_name,
                    description=scenario_desc,
                    human_site_key=site_key,
                    demand_pattern_override=spec["demand_pattern"],
                    recreate=False,
                )
                session.flush()
                session.commit()
                print(f"[success] Created hybrid scenario: {scenario_name}")

        # Remove any legacy Node Types variants for single-node-per-role configs (e.g., default simulation)
        _delete_node_type_games_for_config(session, config)
        session.commit()

        artifacts = _run_post_seed_tasks(
            session,
            config,
            force_dataset=options.force_dataset,
            force_training=options.force_training,
            run_dataset=options.run_dataset,
            run_training=options.run_training,
            agent_strategy=strategy,
        )

        model_artifact = artifacts.get("model") or {}
        config.needs_training = False
        config.training_status = model_artifact.get("status", "trained")
        config.trained_model_path = model_artifact.get("model_path")
        config.trained_at = datetime.utcnow()
        session.add(config)

        # Only recreate Autonomy showcase scenarios when dataset/training are enabled to
        # avoid stale agent_configs updates in skip-training flows.
        if options.create_autonomy_games and options.run_dataset and options.run_training:
            ensure_autonomy_games(
                session,
                tenant,
                config,
                artifacts,
                recreate=options.reset_games,
                name_suffix=spec["autonomy_suffix"],
            )

    # Ensure the complex multi-region configuration exists under the Complex_SC tenant
    if include_complex:
        try:
            complex_tenant, _ = ensure_tenant_with_admin(
                session,
                tenant_name=COMPLEX_TENANT_NAME,
                tenant_description=COMPLEX_TENANT_DESCRIPTION,
                admin_username=COMPLEX_ADMIN_USERNAME,
                admin_email=COMPLEX_ADMIN_EMAIL,
                admin_full_name=COMPLEX_ADMIN_FULL_NAME,
                password=DEFAULT_PASSWORD,
            )
            ensure_role_users(session, complex_tenant)
            # Temporarily disabled - requires migration to Product model
            try:
                from backend.scripts.create_regional_sc_config import ensure_multi_region_config
                config, created = ensure_multi_region_config(
                    session,
                    tenant=complex_tenant,
                    name=COMPLEX_SC_CONFIG_NAME,
                    description=COMPLEX_SC_DESCRIPTION,
                )
            except ImportError as e:
                print(f"[warn] Skipping multi-region config creation (requires Product model migration): {e}")
                config = None
                created = False

            if config is not None:
                _reseed_product_site_configs(session, config)
                session.flush()
                if created:
                    print(
                        f"[success] Created multi-region supply chain configuration '{COMPLEX_SC_CONFIG_NAME}' "
                        f"for tenant '{complex_tenant.name}'."
                    )
                else:
                    print(
                        f"[info] Multi-region supply chain configuration '{COMPLEX_SC_CONFIG_NAME}' already exists "
                        f"(id={config.id})."
                    )

                complex_artifacts: Dict[str, Optional[Dict[str, Any]]] = {
                    "dataset": None,
                    "model": (
                        {
                            "model_path": config.trained_model_path,
                            "status": config.training_status,
                        }
                        if getattr(config, "trained_model_path", None)
                        else None
                    ),
                    "device": None,
                }

                human_scenario = ensure_human_scenario_for_config(
                    session,
                    complex_tenant,
                    config,
                    scenario_name=COMPLEX_HUMAN_SCENARIO_NAME,
                    description=COMPLEX_HUMAN_SCENARIO_DESCRIPTION,
                    recreate=options.reset_games,
                )
                session.flush()

                complex_naive_scenario = ensure_naive_unsupervised_game(
                    session,
                    complex_tenant,
                    config,
                    scenario_name=f"{NAIVE_AGENT_SCENARIO_NAME} ({config.name})",
                )
                _configure_scenario_agents(session, complex_naive_scenario, "naive", assignment_scope="node")
                session.flush()

                complex_naive_type_scenario = ensure_naive_unsupervised_game(
                    session,
                    complex_tenant,
                    config,
                    scenario_name=f"{NAIVE_AGENT_SCENARIO_NAME} ({config.name}) - Node Types",
                )
                _configure_scenario_agents(session, complex_naive_type_scenario, "naive", assignment_scope="node_type")
                session.flush()

                complex_pid_scenario = ensure_pid_game(
                    session,
                    complex_tenant,
                    config,
                    scenario_name=f"{PID_AGENT_SCENARIO_NAME} ({config.name})",
                )
                _configure_scenario_agents(session, complex_pid_scenario, PID_AGENT_STRATEGY, assignment_scope="node")
                session.flush()

                complex_pid_type_scenario = ensure_pid_game(
                    session,
                    complex_tenant,
                    config,
                    scenario_name=f"{PID_AGENT_SCENARIO_NAME} ({config.name}) - Node Types",
                )
                _configure_scenario_agents(session, complex_pid_type_scenario, PID_AGENT_STRATEGY, assignment_scope="node_type")
                session.flush()

                complex_trm_scenario = ensure_trm_game(
                    session,
                    complex_tenant,
                    config,
                    scenario_name=f"{TRM_AGENT_SCENARIO_NAME} ({config.name})",
                )
                _configure_scenario_agents(session, complex_trm_scenario, TRM_AGENT_STRATEGY, assignment_scope="node")
                session.flush()

                complex_trm_type_scenario = ensure_trm_game(
                    session,
                    complex_tenant,
                    config,
                    scenario_name=f"{TRM_AGENT_SCENARIO_NAME} ({config.name}) - Node Types",
                )
                _configure_scenario_agents(session, complex_trm_type_scenario, TRM_AGENT_STRATEGY, assignment_scope="node_type")
                session.flush()
                session.commit()

                if options.create_autonomy_games:
                    ensure_autonomy_games(
                        session,
                        complex_tenant,
                        config,
                        complex_artifacts,
                        recreate=options.reset_games,
                        name_suffix=config.name,
                    )
                session.flush()
                session.commit()
        except Exception as exc:
            print(f"[warn] Unable to ensure multi-region supply chain config: {exc}")

    # Skip creating legacy Six-Pack/Bottle/Multi-Product configs and scenarios.


def run_seed_with_session(
    session_factory: Callable[[], Session],
    options: SeedOptions,
    *,
    config_specs_override: Optional[Sequence[Dict[str, Any]]] = None,
    include_complex: bool = True,
) -> None:
    """Execute the seeding process using the supplied session factory."""
    session: Session | None = None
    try:
        session = session_factory()
        seed_default_data(
            session,
            options,
            config_specs_override=config_specs_override,
            include_complex=include_complex,
        )
        session.commit()
    except Exception:
        if session is not None:
            session.rollback()
        raise
    finally:
        if session is not None:
            session.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap Autonomy default data and agent scenarios")
    parser.add_argument(
        action="store_true",
        help="Delete all existing scenarios before recreating defaults and showcases.",
    )
    parser.add_argument(
        "--skip-autonomy-scenarios",
        action="store_true",
        help="Skip creation/update of Autonomy showcase scenarios.",
    )
    parser.add_argument(
        "--skip-dataset",
        action="store_true",
        help="Skip generating the SimPy dataset used for GNN training.",
    )
    parser.add_argument(
        "--skip-training",
        action="store_true",
        help="Skip training the temporal GNN model.",
    )
    parser.add_argument(
        "--run-dataset",
        action="store_true",
        help="Generate the SimPy dataset used for GNN training.",
    )
    parser.add_argument(
        "--run-training",
        action="store_true",
        help="Train the temporal GNN model.",
    )
    parser.add_argument(
        "--force-training",
        action="store_true",
        help="Retrain the temporal GNN even if a checkpoint already exists.",
    )
    parser.add_argument(
        "--force-dataset",
        action="store_true",
        help="Regenerate the SimPy dataset even if cached output exists.",
    )
    parser.add_argument(
        "--use-human-scenario_users",
        action="store_true",
        help="Assign the default simulation to human accounts instead of AI agents.",
    )
    parser.add_argument(
        "--agent-strategy",
        default=None,
        help="Override the default AI agent strategy (e.g. llm, pid_heuristic, naive).",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help="LLM model to use when the agent strategy is 'llm'.",
    )
    return parser.parse_args()


def build_seed_options_from_args(args: argparse.Namespace) -> SeedOptions:
    run_dataset_env = _env_flag("AUTONOMY_RUN_DATASET")
    run_training_env = _env_flag("AUTONOMY_RUN_TRAINING")
    skip_dataset = args.skip_dataset or _env_flag("AUTONOMY_SKIP_DATASET")
    skip_training = args.skip_training or _env_flag("AUTONOMY_SKIP_TRAINING")
    run_dataset = args.run_dataset or run_dataset_env
    run_training = args.run_training or run_training_env
    if skip_dataset:
        run_dataset = False
    if skip_training:
        run_training = False
    options = SeedOptions(
        reset_games=args.reset_games,
        force_dataset=(args.force_dataset or args.reset_games) and run_dataset,
        force_training=(args.force_training or args.reset_games) and run_training,
        run_dataset=run_dataset,
        run_training=run_training,
        create_autonomy_games=not args.skip_autonomy_games,
        assign_ai_agents=not args.use_human_players,
        preferred_agent_strategy=args.agent_strategy,
        preferred_llm_model=args.llm_model,
    )
    return options


def session_factory_from_settings() -> Callable[[], Session]:
    # Prefer a synchronous session to avoid async/query API mismatches
    from sqlalchemy.orm import sessionmaker  # delayed import to keep CLI fast
    from app.db.session import sync_engine

    return sessionmaker(bind=sync_engine)


def main() -> None:
    args = parse_args()
    options = build_seed_options_from_args(args)
    print(f"[DEBUG] Database URL from settings: {settings.SQLALCHEMY_DATABASE_URI}")

    configured_uri = settings.SQLALCHEMY_DATABASE_URI
    configured_label = mask_db_uri(configured_uri)
    print(f"[info] Attempting to seed default data using: {configured_label or 'default settings'}")

    try:
        SyncSessionLocal = session_factory_from_settings()
        run_seed_with_session(SyncSessionLocal, options)
        print("[done] Default tenant, users, and scenarios are ready.")
        if configured_label:
            print(f"[info] Data stored in: {configured_label}")
        return
    except Exception as exc:
        print("\n[error] Failed to seed the database. Please check the following:")
        print("1. Make sure the MariaDB container is running")
        print("2. Verify the database credentials in your .env file")
        print("3. Check that the database 'autonomy' exists and is accessible")
        print(f"\nError details: {exc}")
        raise


if __name__ == "__main__":
    main()
