from typing import List, Dict, Optional, Any, Sequence, Set, Tuple, Union, Callable, Mapping
from datetime import datetime, timedelta, date
import time
from enum import Enum
import logging
import random
import secrets
import json
import re
import math
import heapq
from collections import defaultdict, deque

from types import SimpleNamespace
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.models.scenario import Scenario, ScenarioStatus as ScenarioStatusDB
from app.models.scenario_user import ScenarioUser, ScenarioUserRole, ScenarioUserType as ScenarioUserTypeDB, ScenarioUserStrategy as ScenarioUserStrategyDB
from app.models.supply_chain import ScenarioUserInventory, Order, ScenarioRound, ScenarioUserPeriod

# Aliases for backwards compatibility
Game = Scenario
GameStatus = ScenarioStatusDB
GameStatusDB = ScenarioStatusDB
ScenarioUser = ScenarioUser
ScenarioUserRole = ScenarioUserRole
ScenarioUserTypeDB = ScenarioUserTypeDB
ScenarioUserStrategyDB = ScenarioUserStrategyDB
ScenarioUserInventory = ScenarioUserInventory
ScenarioRound = ScenarioRound
ScenarioUserPeriod = ScenarioUserPeriod
from app.models.supply_chain_config import SupplyChainConfig, TransportationLane, Site
from app.models.sc_entities import InvPolicy, Product, InvLevel
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.agent_config import AgentConfig
from app.models.user import User, UserTypeEnum
# Note: Item/ProductSiteConfig are compatibility shims proxying to Product model (SC compliant)
from app.models.compatibility import Item, ProductSiteConfig
from app.core.time_buckets import (
    TimeBucket,
    DEFAULT_START_DATE,
    normalize_time_bucket,
    compute_period_start,
    compute_period_end,
)
from app.schemas.scenario import (
    ScenarioCreate,
    ScenarioUserCreate,
    ScenarioState,
    ScenarioUserState,
    ScenarioStatus,
    ScenarioInDBBase,
)
from app.schemas.scenario_user import ScenarioUserAssignment, ScenarioUserType, ScenarioUserStrategy

# Aliases for backwards compatibility
GameCreate = ScenarioCreate
ScenarioUserCreate = ScenarioUserCreate
GameState = ScenarioState
ScenarioUserState = ScenarioUserState
GameStatus = ScenarioStatus
GameInDBBase = ScenarioInDBBase
ScenarioUserAssignment = ScenarioUserAssignment
ScenarioUserType = ScenarioUserType
ScenarioUserStrategy = ScenarioUserStrategy
from app.schemas.simulation import (
    OrderRequest,
    Shipment,
    NodeState,
    TopologyConfig,
    RoundContext,
    LaneConfig,
)
from app.services.agents import (
    AgentDecision,
    AgentManager,
    AgentType,
    AgentStrategy as AgentStrategyEnum,
)
from app.services.llm_payload import build_llm_decision_payload
try:  # pragma: no cover - optional when OpenAI deps absent
    from app.services.llm_agent import check_autonomy_llm_access
except Exception:  # pragma: no cover - during tests without OpenAI deps
    check_autonomy_llm_access = None  # type: ignore[assignment]
# Default market demand (units/period) — defined locally, not imported from engine.py
DEFAULT_STEADY_STATE_DEMAND: int = 4
from app.core.demand_patterns import (
    normalize_demand_pattern,
    DEFAULT_DEMAND_PATTERN,
    DEFAULT_CLASSIC_PARAMS,
    normalize_lognormal_params,
    DemandPatternType,
    DemandGenerator,
    estimate_demand_stats,
)
from app.simulation.helpers import (
    normalize_inbound_supply_queue,
    partition_inbound_supply_queue,
    summarise_inbound_supply_queue,
    summarise_inbound_supply_detail,
    sort_inbound_supply_queue,
)
from app.simulation.debug_logging import (
    ensure_debug_log_file,
    append_debug_round_log,
    append_debug_error,
    normalize_debug_config,
    split_debug_log_file,
)
import asyncio


logger = logging.getLogger(__name__)


def read_system_cfg():
    """Return the persisted system configuration if available."""

    try:
        from app.api.endpoints.config import _read_cfg
    except Exception:
        return None

    try:
        return _read_cfg()
    except Exception:
        return None

class MixedScenarioService:
    """Service for managing games with mixed human and AI scenario_users."""
    
    def __init__(self, db: Session):
        self.db = db
        self.agent_manager = AgentManager()
        self._game_columns_cache: Optional[Sequence[str]] = None
        self._autonomy_probe_cache: Dict[str, Tuple[bool, str]] = {}

    def _get_cost_rates_sync(self, config_id: int) -> tuple:
        """Load holding and backlog cost rates from InvPolicy for a supply chain config.

        Uses InvPolicy.holding_cost_range['min'] and backlog_cost_range['min'] for
        the first product with an InvPolicy in the config. Falls back to
        product.unit_cost * 0.25/52 (holding) and * 4 (backlog) when InvPolicy is absent.

        Raises:
            ValueError: If no product is found for the given config_id, with a descriptive
                        message for debugging.
        """
        product = (
            self.db.query(Product)
            .join(InvPolicy, InvPolicy.product_id == Product.id)
            .filter(Product.config_id == config_id)
            .order_by(Product.id)
            .first()
        )
        if not product:
            product = (
                self.db.query(Product)
                .filter(Product.config_id == config_id)
                .order_by(Product.id)
                .first()
            )
        if not product:
            raise ValueError(
                f"No product found for supply chain config {config_id}. "
                f"Cannot compute cost rates without a Product record. "
                f"Seed the Product table for config {config_id} before running scenarios."
            )

        unit_cost = float(product.unit_cost or 0.0)
        default_holding = unit_cost * 0.25 / 52
        default_backlog = default_holding * 4.0

        site = (
            self.db.query(Site)
            .filter(Site.config_id == config_id)
            .first()
        )
        inv_policy = None
        if site:
            inv_policy = (
                self.db.query(InvPolicy)
                .filter(InvPolicy.site_id == site.id, InvPolicy.product_id == product.id)
                .first()
            )
        if inv_policy:
            hcr = inv_policy.holding_cost_range or {}
            bcr = inv_policy.backlog_cost_range or {}
            holding = hcr.get("min", default_holding)
            backlog = bcr.get("min", default_backlog)
        else:
            holding = default_holding
            backlog = default_backlog
        return holding, backlog

    @staticmethod
    def _coerce_dict(value: Any) -> Dict[str, Any]:
        """Best-effort conversion to a plain dict."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
                return {}
            except Exception:
                return {}
        if value is None:
            return {}
        try:
            return dict(value)
        except Exception:
            return {}

    @staticmethod
    def _record_startup_notice(
        cfg: Dict[str, Any],
        game: Game,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        notices = cfg.get("startup_notices")
        if not isinstance(notices, list):
            notices = []
        notices.append(message)
        cfg["startup_notices"] = notices

        try:
            ensure_debug_log_file(cfg, game)
        except Exception:
            logger.debug(
                "Unable to prepare debug log for startup notice in game %s", getattr(game, "id", "?")
            )

        try:
            append_debug_error(cfg, game, message, details=details)
        except Exception:
            logger.debug(
                "Unable to append startup notice for game %s", getattr(game, "id", "?"), exc_info=True
            )

    @staticmethod
    def _market_supply_capacity(policy: Mapping[str, Any], state: NodeState) -> Optional[Dict[str, int]]:
        """
        Derive per-item max supply for a Market Supply node.

        Returns:
            - None when supply is effectively infinite (max_supply <= 0 or missing).
            - Dict[product_id, capacity] when finite per-period supply is configured.
        """
        max_supply_raw = policy.get("max_supply") if isinstance(policy, Mapping) else None
        if isinstance(max_supply_raw, Mapping):
            cap_map: Dict[str, int] = {}
            for raw_key, raw_val in max_supply_raw.items():
                try:
                    val = int(raw_val)
                except (TypeError, ValueError):
                    continue
                if val <= 0:
                    continue
                product_id = MixedScenarioService._normalise_product_id(raw_key)
                if product_id:
                    cap_map[product_id] = val
            return cap_map or None

        try:
            scalar_cap = int(max_supply_raw) if max_supply_raw is not None else 0
        except (TypeError, ValueError):
            scalar_cap = 0
        if scalar_cap <= 0:
            return None

        # Apply scalar capacity to known items (fall back to a placeholder if none).
        observed_items = set(state.inventory_by_item.keys()) | set(state.backlog_by_item.keys())
        for order in state.backlog_orders or []:
            observed_items.add(MixedScenarioService._normalise_product_id(order.product_id))
        if not observed_items:
            observed_items.add("1")

        return {item: scalar_cap for item in observed_items if item}

    @staticmethod
    def _log_initialisation_debug(
        cfg: Dict[str, Any],
        game: Game,
        *,
        node_label: str,
        calculation_details: Dict[str, Any],
        state: Dict[str, Any],
    ) -> None:
        """Write initial-condition snapshots to the debug log."""
        debug_cfg = normalize_debug_config(cfg)
        if not debug_cfg.get("enabled"):
            cfg["debug_logging"] = debug_cfg
            return

        cfg["debug_logging"] = debug_cfg
        ensure_debug_log_file(cfg, game)
        debug_cfg = normalize_debug_config(cfg)
        file_path = debug_cfg.get("file_path")
        if not file_path:
            return

        node_types = cfg.get("node_types") or {}
        payload = {
            "node_type": node_types.get(node_label),
            "calculations": dict(calculation_details or {}),
            "pipelines": {
                "inbound_demand": state.get("inbound_demand", []),
                "info_queue": state.get("info_queue", []),
                "info_detail_queue": state.get("info_detail_queue", []),
                "incoming_orders": state.get("incoming_orders"),
            },
            "shipments": {
                "ship_queue": state.get("ship_queue", []),
                "incoming_shipments": state.get("incoming_shipments", []),
                "inbound_supply": state.get("inbound_supply", []),
            },
            "starting_state": {
                "inventory": state.get("inventory"),
                "inventory_by_item": state.get("inventory_by_item", {}),
                "finished_inventory_by_item": state.get("finished_inventory_by_item", {}),
                "component_inventory_by_item": state.get("component_inventory_by_item", {}),
                "on_order": state.get("on_order"),
                "base_stock": state.get("base_stock"),
                "current_step": state.get("current_step", 0),
                "backlog": state.get("backlog", 0),
                "on_order_by_item": state.get("on_order_by_item", {}),
                "base_stock_by_item": state.get("base_stock_by_item", {}),
                "backlog_by_item": state.get("backlog_by_item", {}),
            },
        }

        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(f"\nInitial Conditions — Node '{node_label}'\n")
                f.write(json.dumps(payload, indent=2))
                f.write("\n")
        except Exception:
            logger.debug("Unable to write initialisation debug log for %s", node_label)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_game_columns(self) -> Sequence[str]:
        if self._game_columns_cache is not None:
            return self._game_columns_cache

        try:
            inspector = inspect(self.db.bind)
            columns = inspector.get_columns(Game.__tablename__)
            self._game_columns_cache = [column['name'] for column in columns]
        except Exception:
            # Fallback to model metadata if inspection fails
            self._game_columns_cache = [column.name for column in Game.__table__.columns]
        return self._game_columns_cache

    def _ensure_autonomy_llm_ready(self, model: Optional[str]) -> None:
        """Verify Autonomy LLM availability once per model and raise with detail when unavailable."""

        cache_key = (model or "").strip().lower() or "default"
        cached = self._autonomy_probe_cache.get(cache_key)
        if cached is not None:
            available, detail = cached
            if available:
                return
            detail_text = detail or "unknown error"
            raise RuntimeError(
                f"Autonomy LLM unavailable for model '{cache_key}' (previous probe: {detail_text})"
            )

        if check_autonomy_llm_access is None:
            detail_text = "OpenAI Autonomy dependencies not installed"
            self._autonomy_probe_cache[cache_key] = (False, detail_text)
            raise RuntimeError(
                f"Autonomy LLM unavailable for model '{cache_key}' ({detail_text})"
            )

        try:
            available, detail = check_autonomy_llm_access(model=model)
        except Exception as exc:  # pragma: no cover - depends on network
            available = False
            detail = str(exc)

        self._autonomy_probe_cache[cache_key] = (available, detail)
        if not available:
            detail_text = detail or "no additional detail"
            raise RuntimeError(
                f"Autonomy LLM unavailable for model '{cache_key}' ({detail_text})"
            )

    def _upgrade_json_value(
        self,
        raw_value: Any,
        expected_type: Union[type, Tuple[type, ...]],
        *,
        default_factory: Callable[[], Any],
        context: str,
        field_name: Optional[str] = None,
        game: Optional[Game] = None,
        allow_map_to_list: bool = False,
        auto_commit: bool = False,
    ) -> Tuple[Any, bool]:
        """Normalize legacy JSON payloads by updating stored data instead of coercing."""

        def _persist(updated: Any) -> None:
            if game is not None and field_name:
                setattr(game, field_name, updated)
                flag_modified(game, field_name)
                if auto_commit:
                    try:
                        self.db.commit()
                    except Exception:
                        logger.exception(
                            "%s: failed to persist %s after upgrade", context, field_name
                        )

        if isinstance(raw_value, expected_type):
            return raw_value, False

        if allow_map_to_list and isinstance(raw_value, dict) and list in (expected_type if isinstance(expected_type, tuple) else (expected_type,)):
            logger.info(
                "%s: migrating %s mapping into a single-element list", context, field_name or "value"
            )
            upgraded = [raw_value]
            _persist(upgraded)
            return upgraded, True

        if isinstance(raw_value, str):
            try:
                decoded = json.loads(raw_value)
            except json.JSONDecodeError:
                logger.error(
                    "%s: %s contains invalid JSON: %r",
                    context,
                    field_name or "value",
                    raw_value,
                )
                replacement = default_factory()
                _persist(replacement)
                return replacement, True

            if isinstance(decoded, expected_type):
                logger.info(
                    "%s: upgraded legacy JSON string for %s", context, field_name or "value"
                )
                _persist(decoded)
                return decoded, True

            if allow_map_to_list and isinstance(decoded, dict) and list in (expected_type if isinstance(expected_type, tuple) else (expected_type,)):
                logger.info(
                    "%s: wrapped decoded mapping for %s into list", context, field_name or "value"
                )
                upgraded = [decoded]
                _persist(upgraded)
                return upgraded, True

            logger.error(
                "%s: decoded %s JSON but received %s instead of %s: %r",
                context,
                field_name or "value",
                type(decoded).__name__,
                getattr(expected_type, "__name__", str(expected_type)),
                raw_value,
            )
            replacement = default_factory()
            _persist(replacement)
            return replacement, True

        if raw_value is None:
            return default_factory(), False

        logger.error(
            "%s: unexpected %s type %s for %r",
            context,
            field_name or "value",
            type(raw_value).__name__,
            raw_value,
        )
        replacement = default_factory()
        _persist(replacement)
        return replacement, True

    def _upgrade_config_entry(
        self,
        cfg: Dict[str, Any],
        key: str,
        *,
        expected_type: Union[type, Tuple[type, ...]],
        context: str,
        default_factory: Callable[[], Any],
        allow_map_to_list: bool = False,
    ) -> Tuple[Any, bool]:
        value, changed = self._upgrade_json_value(
            cfg.get(key),
            expected_type,
            default_factory=default_factory,
            context=f"{context} config['{key}']",
            field_name=key,
            allow_map_to_list=allow_map_to_list,
        )
        if changed or cfg.get(key) is None:
            cfg[key] = value
        return value, changed

    def _get_supply_chain_config(
        self, config_id: Optional[Any]
    ) -> Optional[SupplyChainConfig]:
        if not config_id:
            return None
        try:
            config_id_int = int(config_id)
        except (TypeError, ValueError):
            return None
        return (
            self.db.query(SupplyChainConfig)
            .filter(SupplyChainConfig.id == config_id_int)
            .first()
        )

    def _resolve_supply_chain_name(self, config_id: Optional[Any]) -> Optional[str]:
        record = self._get_supply_chain_config(config_id)
        return record.name if record else None

    def _build_supply_chain_config_service(self):
        from app.services.supply_chain_config_service import SupplyChainConfigService

        return SupplyChainConfigService(self.db)

    def _resolve_time_bucket(self, config_id: Optional[Any]) -> TimeBucket:
        record = self._get_supply_chain_config(config_id)
        if not record:
            return TimeBucket.WEEK
        return normalize_time_bucket(getattr(record, "time_bucket", TimeBucket.WEEK))

    def _fallback_game_config_from_supply_chain(
        self,
        cfg: Dict[str, Any],
        game: Game,
        *,
        snapshot: Optional[Dict[str, Any]],
        sc_service_factory: Optional[Callable[[Session], Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        supply_chain_id: Optional[Any] = None
        if snapshot and isinstance(snapshot, dict):
            supply_chain_id = snapshot.get("id")
        if not supply_chain_id:
            supply_chain_id = cfg.get("supply_chain_config_id")

        if not supply_chain_id:
            return None

        try:
            supply_chain_id_int = int(supply_chain_id)
        except (TypeError, ValueError):
            logger.warning(
                "Unable to rebuild node_policies: invalid supply chain id %s",
                supply_chain_id,
            )
            return None

        service_builder = sc_service_factory or self._build_supply_chain_config_service
        try:
            sc_service = service_builder(self.db)
            return sc_service.create_game_from_config(
                supply_chain_id_int,
                {
                    "name": getattr(game, "name", "") or "",
                    "description": getattr(game, "description", "") or "",
                    "max_rounds": getattr(game, "max_rounds", 40) or 40,
                    "is_public": getattr(game, "is_public", True),
                },
            )
        except Exception:
            logger.warning(
                "Failed to rebuild node_policies from supply chain %s during start_game",
                supply_chain_id_int,
                exc_info=True,
            )
            return None

    def _supply_chain_snapshot(self, config_id: Optional[Any]) -> Optional[Dict[str, Any]]:
        if not config_id:
            return None
        try:
            config_id_int = int(config_id)
        except (TypeError, ValueError):
            return None

        config = (
            self.db.query(SupplyChainConfig)
            .options(
                selectinload(SupplyChainConfig.items),
                selectinload(SupplyChainConfig.nodes).selectinload("item_configs").selectinload("suppliers"),
                selectinload(SupplyChainConfig.lanes),
                selectinload(SupplyChainConfig.markets),
                selectinload(SupplyChainConfig.market_demands).selectinload("market"),
            )
            .filter(SupplyChainConfig.id == config_id_int)
            .first()
        )
        if not config:
            return None

        def _normalise_range(payload: Any) -> Optional[Dict[str, Any]]:
            if isinstance(payload, dict):
                return {"min": payload.get("min"), "max": payload.get("max")}
            return None

        items = [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "unit_cost_range": _normalise_range(item.unit_cost_range),
            }
            for item in getattr(config, "items", [])
        ]

        nodes = []
        market_demand_nodes: List[str] = []
        demand_node_entries: List[Tuple[str, Set[str]]] = []
        bill_of_materials: Dict[str, Dict[str, Dict[str, int]]] = {}
        for node in getattr(config, "nodes", []):
            node_payload: Dict[str, Any] = {
                "id": node.id,
                "name": node.name,
                "type": str(getattr(node, "dag_type", None) or getattr(node, "type", "")).lower(),
            }
            node_attrs = getattr(node, "attributes", {}) or {}
            node_payload["attributes"] = node_attrs
            item_cfgs = []
            for inc in getattr(node, "item_configs", []) or []:
                suppliers = []
                for supplier in getattr(inc, "suppliers", []) or []:
                    suppliers.append({
                        "id": supplier.id,
                        "supplier_site_id": supplier.supplier_site_id,
                        "priority": supplier.priority,
                    })

                item_cfgs.append(
                    {
                        "id": inc.id,
                        "product_id": inc.product_id,
                        "site_id": inc.site_id,
                        "inventory_target_range": _normalise_range(inc.inventory_target_range),
                        "initial_inventory_range": _normalise_range(inc.initial_inventory_range),
                        "holding_cost_range": _normalise_range(inc.holding_cost_range),
                        "backlog_cost_range": _normalise_range(inc.backlog_cost_range),
                        "selling_price_range": _normalise_range(inc.selling_price_range),
                        "suppliers": suppliers,
                    }
                )
            node_payload["item_configs"] = item_cfgs
            nodes.append(node_payload)
            bom_payload = node_attrs.get("bill_of_materials")
            if isinstance(bom_payload, dict) and node.name:
                node_key = MixedScenarioService._normalise_key(node.name)
                node_entry = bill_of_materials.setdefault(node_key, {})
                for product_id, components in bom_payload.items():
                    if not isinstance(components, dict):
                        continue
                    item_key = str(product_id)
                    component_map: Dict[str, int] = {}
                    for component_id, qty in components.items():
                        try:
                            qty_int = int(qty)
                        except (TypeError, ValueError):
                            continue
                        if qty_int <= 0:
                            continue
                        component_map[MixedScenarioService._normalise_key(component_id)] = qty_int
                    if component_map:
                        node_entry[item_key] = component_map
            node_type_value = MixedScenarioService._normalise_node_type(node_payload["type"])
            normalized_name = MixedScenarioService._normalise_key(node.name)
            if node_type_value == "market_demand" and normalized_name:
                market_demand_nodes.append(normalized_name)
                demand_node_entries.append(
                    (
                        normalized_name,
                        MixedScenarioService._tokenise_label(node.name),
                    )
                )

        lanes = [
            {
                "id": lane.id,
                "from_site_id": lane.from_site_id,
                "to_site_id": lane.to_site_id,
                "capacity": lane.capacity,
                "lead_time_days": _normalise_range(lane.lead_time_days),
            }
            for lane in getattr(config, "lanes", [])
        ]

        def _tokenise(value: Any) -> Set[str]:
            return MixedScenarioService._tokenise_label(value)

        market_payload: List[Dict[str, Any]] = []
        market_lookup: Dict[str, str] = {}
        used_nodes: Set[str] = set()
        for market in getattr(config, "markets", []):
            market_id = MixedScenarioService._normalise_market_id(market.id)
            entry = {
                "id": market.id,
                "name": market.name,
                "description": market.description,
                "company": getattr(market, "company", None),
            }
            tokens = _tokenise(market.name)
            best_node = None
            best_score = -1
            for node_key, node_tokens in demand_node_entries:
                if node_key in used_nodes and len(demand_node_entries) > 1:
                    continue
                overlap = len(tokens & node_tokens)
                if overlap > best_score:
                    best_score = overlap
                    best_node = node_key
            if best_node is None and demand_node_entries:
                best_node = demand_node_entries[0][0]
            if best_node:
                entry["node_key"] = best_node
                if market_id:
                    market_lookup[market_id] = best_node
                used_nodes.add(best_node)
            market_payload.append(entry)

        market_demands = []
        for md in getattr(config, "market_demands", []):
            market_id = MixedScenarioService._normalise_market_id(md.market_id)
            entry = {
                "id": md.id,
                "product_id": md.product_id,
                "market_id": md.market_id,
                "market_name": getattr(md.market, "name", None),
                "demand_pattern": md.demand_pattern,
            }
            node_key = market_lookup.get(market_id or "")
            if node_key:
                entry["market_node"] = node_key
            market_demands.append(entry)

        site_type_definitions_raw = getattr(config, "site_type_definitions", None)
        site_type_definitions, site_type_labels = MixedScenarioService._normalise_site_type_definitions(
            site_type_definitions_raw
        )

        time_bucket_value = (
            getattr(getattr(config, "time_bucket", None), "value", None)
            or getattr(config, "time_bucket", None)
        )

        return {
            "id": config.id,
            "name": config.name,
            "description": config.description,
            "tenant_id": config.tenant_id,
            "is_active": bool(config.is_active),
            "created_at": config.created_at,
            "updated_at": config.updated_at,
            "needs_training": getattr(config, "needs_training", True),
            "training_status": getattr(config, "training_status", None),
            "trained_at": getattr(config, "trained_at", None),
            "trained_model_path": getattr(config, "trained_model_path", None),
            "last_trained_config_hash": getattr(config, "last_trained_config_hash", None),
            "items": items,
            "sites": nodes,
            "lanes": lanes,
            "markets": market_payload,
            "market_demands": market_demands,
            "market_nodes": market_demand_nodes,
            "bill_of_materials": bill_of_materials,
            "site_type_definitions": site_type_definitions,
            "site_type_labels": site_type_labels,
            "time_bucket": time_bucket_value,
        }

    # Canonical role names used for DAG identity (do not collapse retailer/wholesaler/distributor).
    ROLE_ALIASES: Dict[str, str] = {}
    # Master logic types used to share processing logic across DAG nodes.
    MASTER_TYPE_ALIASES: Dict[str, str] = {}

    @staticmethod
    def _normalise_node_type(value: Any) -> str:
        """Return a canonical representation for a node type value."""

        raw = str(value or "")
        token = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw).strip().lower()
        if not token:
            return ""
        token = re.sub(r"[\s\-]+", "_", token)
        token = re.sub(r"[^0-9a-z_]+", "", token)
        token = re.sub(r"_+", "_", token).strip("_")
        return token

    @staticmethod
    def _normalise_site_type_definitions(
        payload: Any,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """Return an ordered list of node type definitions and a label lookup map."""

        definitions: List[Dict[str, Any]] = []
        label_map: Dict[str, str] = {}

        def _canonical_master(master: Any, node_type: str) -> str:
            token = MixedScenarioService._canonical_role(master)
            if token in {"market_demand", "market"}:
                return "market_demand"
            if token == "market_supply":
                return "market_supply"
            if token == "manufacturer":
                return "manufacturer"
            if node_type in {"retailer", "wholesaler", "distributor", "inventory", "supplier"}:
                return "inventory"
            return "market_demand"

        if not payload:
            return definitions, label_map

        entries: Sequence[Any]
        if isinstance(payload, list):
            entries = payload
        else:
            entries = [payload]

        for index, entry in enumerate(entries):
            if isinstance(entry, dict):
                node_type = str(entry.get("type") or "").strip().lower()
                label = (
                    str(entry.get("label") or "").strip()
                    or node_type.replace("_", " ").title()
                )
                order = entry.get("order")
                is_required = bool(
                    entry.get(
                        "is_required",
                        node_type in {"market_supply", "market_demand"},
                    )
                )
                master_type = _canonical_master(entry.get("master_type"), node_type)
            else:
                node_type = str(getattr(entry, "type", "") or "").strip().lower()
                label = (
                    str(getattr(entry, "label", "") or "").strip()
                    or node_type.replace("_", " ").title()
                )
                order = getattr(entry, "order", None)
                is_required = bool(
                    getattr(
                        entry,
                        "is_required",
                        node_type in {"market_supply", "market_demand"},
                    )
                )
                master_type = _canonical_master(getattr(entry, "master_type", None), node_type)

            if not node_type:
                continue

            if not isinstance(order, int):
                order = index

            definition = {
                "type": node_type,
                "label": label,
                "order": order,
                "is_required": is_required,
                "master_type": master_type,
            }
            definitions.append(definition)
            label_map[node_type] = label

        definitions.sort(key=lambda entry: entry.get("order", 0))
        return definitions, label_map

    @staticmethod
    def _extract_node_types(cfg: Dict[str, Any]) -> Dict[str, str]:
        node_types: Dict[str, str] = {}
        for node in cfg.get("nodes", []) or []:
            name = node.get("name") or node.get("id")
            if not name:
                continue
            key = MixedScenarioService._normalise_key(name)
            if not key:
                continue
            node_type_raw = node.get("dag_type") or node.get("type")
            if node_type_raw is None:
                raise ValueError(f"Node '{name}' is missing dag_type/type in configuration.")
            if isinstance(node_type_raw, dict):
                node_type_value = (
                    node_type_raw.get("value")
                    or node_type_raw.get("name")
                    or node_type_raw.get("type")
                )
            elif hasattr(node_type_raw, "value"):
                node_type_value = getattr(node_type_raw, "value")
            else:
                node_type_value = node_type_raw
            node_type = MixedScenarioService._normalise_node_type(node_type_value)
            if not node_type:
                raise ValueError(f"Node '{name}' has an invalid dag_type/type.")
            node_types[key] = node_type
        return node_types

    @staticmethod
    def _extract_node_master_types(cfg: Dict[str, Any]) -> Dict[str, str]:
        master_types: Dict[str, str] = {}
        # Explicit map wins
        for key, val in (cfg.get("node_master_types") or {}).items():
            norm_key = MixedScenarioService._normalise_key(key)
            if not norm_key:
                continue
            master_value = MixedScenarioService._master_node_type(val)
            if not master_value:
                raise ValueError(f"Node '{key}' has an invalid master_type.")
            master_types[norm_key] = master_value

        # Populate from node definitions if present
        for node in cfg.get("nodes", []) or []:
            name = node.get("name") or node.get("id")
            if not name:
                continue
            key = MixedScenarioService._normalise_key(name)
            if not key:
                continue
            master_raw = node.get("master_type")
            if master_raw is None:
                if key in master_types:
                    continue
                raise ValueError(f"Node '{name}' is missing master_type in configuration.")
            if isinstance(master_raw, dict):
                master_value = (
                    master_raw.get("value")
                    or master_raw.get("name")
                    or master_raw.get("type")
                )
            elif hasattr(master_raw, "value"):
                master_value = getattr(master_raw, "value")
            else:
                master_value = master_raw
            canonical = MixedScenarioService._master_node_type(master_value)
            if not canonical:
                raise ValueError(f"Node '{name}' has an invalid master_type.")
            master_types.setdefault(key, canonical)
        return master_types

    @staticmethod
    def _canonical_role(value: Any) -> str:
        raw = str(value or "")
        token = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw).strip().lower()
        if not token:
            return ""

        # Normalise delimiters so variants like "Market Supply", "market_supply",
        # or "Market-Supply" map to the same canonical key.  This prevents
        # configuration mismatches where lane definitions and node policies use
        # different spacing conventions.
        token = re.sub(r"[\s\-]+", "_", token)
        token = re.sub(r"[^0-9a-z_]+", "", token)
        token = re.sub(r"_+", "_", token).strip("_")

        if not token:
            return ""

        return MixedScenarioService.ROLE_ALIASES.get(token, token)

    @staticmethod
    def _master_node_type(value: Any) -> str:
        """Return the master processing type for a DAG node (groups inventory-like nodes)."""
        canonical = MixedScenarioService._canonical_role(value)
        return canonical

    @staticmethod
    def _scenario_user_node_key(scenario_user: ScenarioUser) -> str:
        if scenario_user is None:
            return ""
        site_key = getattr(scenario_user, "site_key", None)
        if site_key:
            return MixedScenarioService._canonical_role(site_key)
        role_value = getattr(scenario_user.role, "value", scenario_user.role)
        return MixedScenarioService._canonical_role(role_value)

    @staticmethod
    def _agent_type_for_node(node_type: Optional[str]) -> AgentType:
        canonical = MixedScenarioService._normalise_node_type(node_type or "")
        mapping = {
            "retailer": AgentType.RETAILER,
            "market_demand": AgentType.RETAILER,
            "wholesaler": AgentType.WHOLESALER,
            "distributor": AgentType.DISTRIBUTOR,
            "manufacturer": AgentType.MANUFACTURER,
            "supplier": AgentType.SUPPLIER,
            "market_supply": AgentType.SUPPLIER,
        }
        return mapping.get(canonical, AgentType.MANUFACTURER)

    @staticmethod
    def _normalise_key(value: Any) -> str:
        return MixedScenarioService._canonical_role(value)

    @staticmethod
    def _policy_for_node(node_policies: Dict[str, Any], node: str) -> Dict[str, Any]:
        canonical = MixedScenarioService._canonical_role(node)
        if canonical in node_policies:
            return node_policies.get(canonical, {})

        # Fall back to any policy entry whose canonicalised key matches the
        # requested node. This catches variants like "market demand" vs
        # "market_demand" that would otherwise return an empty policy.
        for key, value in node_policies.items():
            if MixedScenarioService._canonical_role(key) == canonical:
                return value if isinstance(value, dict) else {}

        for alias, target in MixedScenarioService.ROLE_ALIASES.items():
            if target == canonical and alias in node_policies:
                return node_policies.get(alias, {})

        return node_policies.get(node, {})

    @staticmethod
    def _validate_lanes(node_policies: Dict[str, Any], lanes: List[Dict[str, Any]]) -> None:
        if not lanes:
            return
        known_nodes = {MixedScenarioService._normalise_key(name) for name in node_policies.keys()}
        missing: List[str] = []
        for lane in lanes:
            upstream = MixedScenarioService._normalise_key(lane.get("from") or lane.get("upstream"))
            downstream = MixedScenarioService._normalise_key(lane.get("to") or lane.get("downstream"))
            if upstream not in known_nodes:
                missing.append(upstream)
            if downstream not in known_nodes:
                missing.append(downstream)
        if missing:
            unique_missing = sorted(set(missing))
            raise ValueError(
                "Transportation lane configuration references unknown sites: "
                + ", ".join(unique_missing)
            )

    @staticmethod
    def _coerce_leadtime_value(raw: Any) -> Optional[int]:
        """Return a non-negative integer for mixed lead-time payloads."""

        if raw is None:
            return None

        if isinstance(raw, (int, float)):
            try:
                return max(0, int(round(float(raw))))
            except (TypeError, ValueError):
                return None

        if isinstance(raw, str):
            try:
                numeric = float(raw.strip())
            except (ValueError, AttributeError):
                return None
            return max(0, int(round(numeric)))

        if isinstance(raw, dict):
            for key in ("value", "mean", "minimum", "min", "maximum", "max", "steps", "days"):
                if key in raw and raw[key] is not None:
                    coerced = MixedScenarioService._coerce_leadtime_value(raw[key])
                    if coerced is not None:
                        return coerced
            params = raw.get("params") if isinstance(raw.get("params"), dict) else None
            if params:
                for key in ("value", "mean", "minimum", "min"):
                    if key in params and params[key] is not None:
                        coerced = MixedScenarioService._coerce_leadtime_value(params[key])
                        if coerced is not None:
                            return coerced
            return None

        return None

    @staticmethod
    def _topological_order(
        shipments_map: Dict[str, List[str]],
        nodes: Sequence[str],
        priority_lookup: Optional[Mapping[str, Optional[int]]] = None,
    ) -> List[str]:
        indegree: Dict[str, int] = {node: 0 for node in nodes}
        for upstream, downstreams in shipments_map.items():
            for downstream in downstreams:
                indegree.setdefault(downstream, 0)
                indegree[downstream] += 1
                indegree.setdefault(upstream, 0)
        heap: List[Tuple[int, int, str]] = []
        for node, deg in indegree.items():
            if deg == 0:
                heapq.heappush(heap, MixedScenarioService._priority_sort_key(node, priority_lookup or {}))

        order: List[str] = []
        while heap:
            _, _, node = heapq.heappop(heap)
            order.append(node)
            for neighbour in shipments_map.get(node, []):
                indegree[neighbour] -= 1
                if indegree[neighbour] == 0:
                    heapq.heappush(heap, MixedScenarioService._priority_sort_key(neighbour, priority_lookup or {}))
        if len(order) != len(indegree):
            # Cycle detected – fall back to existing node order to avoid crashing.
            return list(nodes)
        return order

    @staticmethod
    def _build_lane_views(node_policies: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
        lanes = cfg.get("lanes") or []
        node_keys = [MixedScenarioService._normalise_key(k) for k in node_policies.keys()]
        node_types = MixedScenarioService._extract_node_types(cfg)
        node_master_types = MixedScenarioService._extract_node_master_types(cfg)
        raw_types = cfg.get("node_types") or {}
        priority_lookup: Dict[str, Optional[int]] = {}
        for name, policy in (node_policies or {}).items():
            if not isinstance(policy, Mapping):
                continue
            key = MixedScenarioService._normalise_key(name)
            if key:
                priority_lookup[key] = policy.get("priority")
        for name, node_type in raw_types.items():
            key = MixedScenarioService._normalise_key(name)
            if not key:
                continue
            node_types[key] = MixedScenarioService._normalise_node_type(node_type)
            if key not in node_master_types:
                node_master_types[key] = MixedScenarioService._master_node_type(node_type)
        if not lanes:
            raise ValueError("Supply chain configuration is missing lanes; cannot infer defaults.")

        node_alias_lookup: Dict[str, str] = {}
        for node_entry in cfg.get("nodes") or []:
            if not isinstance(node_entry, Mapping):
                continue
            canonical = MixedScenarioService._normalise_key(
                node_entry.get("key")
                or node_entry.get("name")
                or node_entry.get("type")
                or node_entry.get("dag_type")
            )
            if not canonical:
                continue
            alias_candidates = [
                node_entry.get("id"),
                node_entry.get("site_id"),
                node_entry.get("key"),
                node_entry.get("name"),
                node_entry.get("type"),
                node_entry.get("dag_type"),
            ]
            for alias in alias_candidates:
                if alias is None:
                    continue
                alias_key = str(alias).strip().lower()
                if not alias_key:
                    continue
                node_alias_lookup.setdefault(alias_key, canonical)

        shipments_map: Dict[str, List[str]] = defaultdict(list)
        orders_map: Dict[str, List[str]] = defaultdict(list)
        lane_records: List[Dict[str, Any]] = []
        lanes_by_upstream: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        lane_lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
        all_nodes = set(node_keys)
        for lane in lanes:
            upstream_raw = lane.get("from") or lane.get("upstream")
            downstream_raw = lane.get("to") or lane.get("downstream")
            if upstream_raw is None:
                upstream_id = lane.get("from_node_id") or lane.get("from_site_id")
                if upstream_id is not None:
                    alias_key = str(upstream_id).strip().lower()
                    upstream_raw = node_alias_lookup.get(alias_key, upstream_id)
            else:
                alias_key = str(upstream_raw).strip().lower()
                upstream_raw = node_alias_lookup.get(alias_key, upstream_raw)

            if downstream_raw is None:
                downstream_id = lane.get("to_node_id") or lane.get("to_site_id")
                if downstream_id is not None:
                    alias_key = str(downstream_id).strip().lower()
                    downstream_raw = node_alias_lookup.get(alias_key, downstream_id)
            else:
                alias_key = str(downstream_raw).strip().lower()
                downstream_raw = node_alias_lookup.get(alias_key, downstream_raw)

            if upstream_raw is None or downstream_raw is None:
                continue
            upstream = MixedScenarioService._normalise_key(upstream_raw)
            downstream = MixedScenarioService._normalise_key(downstream_raw)
            if upstream == downstream:
                # Ignore self-loops; they create cycles in demand/supply graphs.
                continue
            order_delay = lane.get("demand_lead_time")
            order_delay_int = MixedScenarioService._coerce_leadtime_value(order_delay)

            supply_delay = lane.get("supply_lead_time")
            supply_delay_int = MixedScenarioService._coerce_leadtime_value(supply_delay)

            lane_record = {
                "from": upstream,
                "to": downstream,
                "capacity": lane.get("capacity"),
                "lead_time_days": lane.get("lead_time_days"),
                "demand_lead_time": order_delay_int,
            }
            if order_delay is not None:
                lane_record.setdefault("demand_lead_time", order_delay)
            if supply_delay_int is not None:
                lane_record["supply_lead_time"] = supply_delay_int
            if supply_delay is not None:
                lane_record.setdefault("supply_lead_time", supply_delay)
            shipments_map[upstream].append(downstream)
            orders_map[downstream].append(upstream)
            lane_records.append(lane_record)
            lanes_by_upstream[upstream].append(lane_record)
            lane_lookup[(upstream, downstream)] = lane_record
            all_nodes.add(upstream)
            all_nodes.add(downstream)

        market_nodes = [
            MixedScenarioService._normalise_key(n)
            for n in cfg.get("market_demand_nodes", [])
            if n
        ]
        explicit_market_nodes = [
            MixedScenarioService._normalise_key(node)
            for node, node_type in node_types.items()
            if str(node_type).lower() == "market_demand"
        ]
        market_nodes = [n for n in market_nodes if n] or [n for n in explicit_market_nodes if n]
        if not market_nodes:
            raise ValueError("Supply chain configuration must include an explicit Market Demand node.")
        for md in market_nodes:
            if md not in all_nodes:
                all_nodes.add(md)
            node_types.setdefault(md, "market_demand")

        source_nodes = []
        for node in sorted(all_nodes):
            if orders_map.get(node):
                continue
            source_nodes.append(node)
        if not source_nodes:
            raise ValueError("Supply chain DAG has no source nodes; Market Demand nodes are required.")
        if not any(str(node_types.get(node, "")).lower() == "market_supply" for node in source_nodes):
            raise ValueError("Supply chain DAG must include at least one Market Supply source node.")
        invalid_sources = [
            node
            for node in source_nodes
            if str(node_types.get(node, "")).lower()
            not in {"market_supply", "market_demand", "supplier", "component_supplier"}
        ]
        if invalid_sources:
            logger.warning(
                "Supply chain DAG sources should be Market Supply / Market Demand / Supplier; proceeding with sources: %s",
                ", ".join(sorted(source_nodes)),
            )

        sink_nodes = [node for node in sorted(all_nodes) if not shipments_map.get(node)]
        if not sink_nodes:
            raise ValueError("Supply chain DAG has no sink nodes; Market Demand nodes are required.")
        if not any(str(node_types.get(node, "")).lower() == "market_demand" for node in sink_nodes):
            raise ValueError("Supply chain DAG must include at least one Market Demand sink node.")

        for node in sorted(all_nodes):
            if node not in node_types:
                raise ValueError(f"Node '{node}' is missing a node type in configuration.")
            if node not in node_master_types:
                raise ValueError(f"Node '{node}' is missing a master_type in configuration.")

        sorted_nodes = sorted(
            all_nodes,
            key=lambda n: MixedScenarioService._priority_sort_key(n, priority_lookup),
        )
        node_sequence = (
            MixedScenarioService._topological_order(shipments_map, sorted_nodes, priority_lookup)
            if all_nodes
            else []
        )
        return {
            "lanes": lane_records,
            "shipments_map": shipments_map,
            "orders_map": orders_map,
            "market_nodes": market_nodes,
            "all_nodes": sorted_nodes,
            "node_sequence": node_sequence,
            "lanes_by_upstream": lanes_by_upstream,
            "node_types": node_types,
            "node_master_types": node_master_types,
            "lane_lookup": lane_lookup,
        }

    @staticmethod
    def _resolve_node_master_type(topology: TopologyConfig, node_key: str) -> str:
        master_types = getattr(topology, "node_master_types", {}) or {}
        node_types = getattr(topology, "node_types", {}) or {}
        master_type = master_types.get(node_key)
        if master_type:
            return master_type
        node_type = node_types.get(node_key) or node_key
        return MixedScenarioService._master_node_type(node_type)

    @staticmethod
    def _normalise_market_id(value: Any) -> Optional[str]:
        """Return a comparable identifier for market references."""

        if value is None:
            return None
        if isinstance(value, (int, float)):
            try:
                return str(int(value))
            except (TypeError, ValueError):
                return str(value)
        token = str(value).strip().lower()
        return token or None

    @staticmethod
    def _json_clone(value: Any) -> Any:
        """Return a JSON-serialisable clone of arbitrary ORM payloads."""

        if isinstance(value, dict):
            return {str(k): MixedScenarioService._json_clone(v) for k, v in value.items()}
        if isinstance(value, list):
            return [MixedScenarioService._json_clone(item) for item in value]
        if isinstance(value, (int, float, str, bool)) or value is None:
            return value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        try:
            return float(value)
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _priority_sort_key(identifier: str, priority_lookup: Mapping[str, Optional[int]]) -> Tuple[int, int, str]:
        """Return a stable sort key that prefers explicit priorities then alphabetical order."""

        if not isinstance(priority_lookup, Mapping):
            priority_lookup = {}

        priority = priority_lookup.get(identifier)
        missing = 1 if priority is None else 0
        value = priority if priority is not None else 0
        return (missing, value, str(identifier))

    @staticmethod
    def _tokenise_label(value: Any) -> Set[str]:
        if value is None:
            return set()
        raw = str(value).lower()
        parts = re.split(r"[^0-9a-z]+", raw)
        return {part for part in parts if part}

    @staticmethod
    def _candidate_market_nodes(
        cfg: Dict[str, Any],
        lane_views: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        candidates: List[str] = []
        if lane_views:
            for node in lane_views.get("market_nodes") or []:
                key = MixedScenarioService._normalise_key(node)
                if key:
                    candidates.append(key)
        for node in cfg.get("market_demand_nodes") or []:
            key = MixedScenarioService._normalise_key(node)
            if key:
                candidates.append(key)
        node_types = cfg.get("node_types") or {}
        for node, node_type in node_types.items():
            if str(node_type).lower() == "market_demand":
                key = MixedScenarioService._normalise_key(node)
                if key:
                    candidates.append(key)
        if not candidates:
            node_policies = cfg.get("node_policies") or {}
            for node in node_policies.keys():
                if "market" in str(node).lower():
                    key = MixedScenarioService._normalise_key(node)
                    if key:
                        candidates.append(key)
        # Preserve order but deduplicate
        deduped: List[str] = []
        seen: Set[str] = set()
        for node in candidates:
            if node and node not in seen:
                seen.add(node)
                deduped.append(node)
        return deduped

    @staticmethod
    def _match_market_to_node(
        market_tokens: Set[str],
        candidates: List[str],
        used: Optional[Set[str]] = None,
        candidate_tokens: Optional[Dict[str, Set[str]]] = None,
    ) -> Optional[str]:
        if not candidates:
            return None
        candidate_tokens = candidate_tokens or {
            node: MixedScenarioService._tokenise_label(node) for node in candidates
        }
        best_node: Optional[str] = None
        best_score = -1.0
        for node in candidates:
            if not node:
                continue
            tokens = candidate_tokens.get(node, set())
            overlap = len(market_tokens & tokens) if market_tokens else 0
            score = overlap
            if market_tokens and market_tokens.issubset(tokens):
                score += 0.5
            if used and node in used:
                score -= 0.25
            if score > best_score:
                best_score = score
                best_node = node
        if best_node:
            return best_node
        if used:
            for node in candidates:
                if node not in used:
                    return node
        return candidates[0]

    @staticmethod
    def _market_node_lookup(
        cfg: Dict[str, Any],
        lane_views: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build lookup dictionaries that map markets to node keys."""

        markets_payload = cfg.get("markets") or []
        lookup_by_id: Dict[str, str] = {}
        lookup_by_name: Dict[str, str] = {}

        for market in markets_payload:
            if not isinstance(market, dict):
                continue
            market_id = MixedScenarioService._normalise_market_id(market.get("id"))
            node_hint = (
                market.get("node_key")
                or market.get("node")
                or market.get("market_node")
                or market.get("market_node_key")
            )
            node_key = MixedScenarioService._normalise_key(node_hint) if node_hint else ""
            if market_id and node_key:
                lookup_by_id[market_id] = node_key
            name_key = MixedScenarioService._normalise_key(market.get("name"))
            if name_key and node_key:
                lookup_by_name[name_key] = node_key

        candidates = MixedScenarioService._candidate_market_nodes(cfg, lane_views)
        candidate_tokens = {
            node: MixedScenarioService._tokenise_label(node) for node in candidates
        }

        used: Set[str] = set(lookup_by_id.values())

        for market in markets_payload:
            if not isinstance(market, dict):
                continue
            market_id = MixedScenarioService._normalise_market_id(market.get("id"))
            if market_id and market_id in lookup_by_id:
                continue
            market_name = market.get("name")
            market_tokens = MixedScenarioService._tokenise_label(market_name)
            matched = MixedScenarioService._match_market_to_node(
                market_tokens,
                candidates,
                used=used,
                candidate_tokens=candidate_tokens,
            )
            if not matched and candidates:
                matched = candidates[0]
            if matched and market_id:
                lookup_by_id[market_id] = matched
                used.add(matched)
                name_key = MixedScenarioService._normalise_key(market_name)
                if name_key:
                    lookup_by_name[name_key] = matched

        return {
            "by_id": lookup_by_id,
            "by_name": lookup_by_name,
            "candidates": candidates,
            "candidate_tokens": candidate_tokens,
        }

    @staticmethod
    def _resolve_market_node_key(
        entry: Dict[str, Any],
        market_lookup: Dict[str, Any],
    ) -> str:
        """Resolve the node key for a market demand entry."""

        if not isinstance(entry, dict):
            return ""

        node_hint = entry.get("market_node")
        if node_hint:
            node_key = MixedScenarioService._normalise_key(node_hint)
            if node_key:
                return node_key

        market_id = MixedScenarioService._normalise_market_id(entry.get("market_id"))
        if market_id:
            node_key = (market_lookup.get("by_id") or {}).get(market_id)
            if node_key:
                return node_key

        market_name = entry.get("market_name") or entry.get("market") or entry.get("name")
        if market_name:
            name_key = MixedScenarioService._normalise_key(market_name)
            node_key = (market_lookup.get("by_name") or {}).get(name_key)
            if node_key:
                return node_key
            market_tokens = MixedScenarioService._tokenise_label(market_name)
        else:
            market_tokens = set()

        candidates = market_lookup.get("candidates") or []
        candidate_tokens = market_lookup.get("candidate_tokens") or {}
        fallback = MixedScenarioService._match_market_to_node(
            market_tokens,
            candidates,
            candidate_tokens=candidate_tokens,
        )
        if fallback:
            return fallback

        if market_name is None and entry.get("market_id") is not None:
            market_name = entry.get("market_id")
        return MixedScenarioService._normalise_key(market_name)

    @staticmethod
    def _build_market_item_profiles(
        cfg: Dict[str, Any],
        lane_views: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, int]]:
        profiles: Dict[str, Dict[str, int]] = defaultdict(dict)
        market_lookup = MixedScenarioService._market_node_lookup(cfg, lane_views)
        market_demands = cfg.get("market_demands") or []
        for entry in market_demands:
            if not isinstance(entry, dict):
                continue
            node_key = MixedScenarioService._resolve_market_node_key(entry, market_lookup)
            if not node_key:
                continue
            product_id = entry.get("product_id") or entry.get("item_id") or entry.get("item") or entry.get("sku")
            if product_id is None:
                continue
            pattern = entry.get("demand_pattern")
            mean, _ = estimate_demand_stats(pattern)
            baseline = MixedScenarioService._baseline_flow(mean)
            if baseline <= 0:
                baseline = DEFAULT_STEADY_STATE_DEMAND
            profiles[node_key][str(product_id)] = profiles[node_key].get(str(product_id), 0) + int(baseline)
        return {node: dict(items) for node, items in profiles.items()}

    @staticmethod
    def _propagate_item_profiles(
        orders_map: Dict[str, List[str]],
        market_profiles: Dict[str, Dict[str, int]],
    ) -> Dict[str, Dict[str, int]]:
        node_item_map: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        def _propagate(node: str, item: str, quantity: int, visited: Set[str]) -> None:
            if quantity <= 0:
                return
            node_item_map[node][item] += quantity
            for upstream in orders_map.get(node, []):
                if upstream in visited:
                    continue
                visited.add(upstream)
                _propagate(upstream, item, quantity, visited)
                visited.remove(upstream)

        for market_node, item_map in market_profiles.items():
            for product_id, qty in item_map.items():
                _propagate(market_node, product_id, int(qty), {market_node})

        # Convert defaultdicts to plain dicts
        return {node: dict(items) for node, items in node_item_map.items()}

    @staticmethod
    def _normalise_product_id(value: Any) -> str:
        """Return a stable string identifier for product ids, including None fallbacks."""

        token = str(value).strip() if value is not None else ""
        return token

    @staticmethod
    def _bom_for_node(cfg: Mapping[str, Any], node_key: str) -> Dict[str, Dict[str, int]]:
        """
        Return a normalised bill of materials mapping for a specific node.

        The returned structure is {finished_item_id: {component_key: qty}} with
        canonicalised keys so downstream logic can reliably match sources.
        """

        bom_map_raw = cfg.get("bill_of_materials") if isinstance(cfg, Mapping) else {}
        if not bom_map_raw:
            return {}

        node_norm = MixedScenarioService._normalise_key(node_key)
        bom_for_node: Dict[str, Dict[str, int]] = {}

        for raw_node, item_map in bom_map_raw.items():
            if MixedScenarioService._normalise_key(raw_node) != node_norm:
                continue
            if not isinstance(item_map, Mapping):
                continue
            for raw_item, components in item_map.items():
                if not isinstance(components, Mapping):
                    continue
                product_id = MixedScenarioService._normalise_product_id(raw_item)
                comp_payload: Dict[str, int] = {}
                for comp_id, qty in components.items():
                    try:
                        qty_int = int(qty)
                    except (TypeError, ValueError):
                        continue
                    if qty_int <= 0:
                        continue
                    comp_payload[MixedScenarioService._normalise_product_id(comp_id)] = qty_int
                if comp_payload:
                    bom_for_node[product_id] = comp_payload

        return bom_for_node

    @staticmethod
    def _manufacturing_leadtime(policy: Mapping[str, Any], product_id: str) -> int:
        """
        Resolve a manufacturing lead time for a given finished item at a manufacturer node.
        """

        lt_map = {}
        if isinstance(policy, Mapping):
            lt_map = policy.get("manufacturing_leadtime_by_item") or {}
        item_key = MixedScenarioService._normalise_product_id(product_id)
        leadtime = None
        if isinstance(lt_map, Mapping):
            leadtime = lt_map.get(item_key)
            if leadtime is None:
                leadtime = lt_map.get(str(item_key))
        if leadtime is None and isinstance(policy, Mapping):
            leadtime = policy.get("manufacturing_leadtime")
        try:
            return int(leadtime) if leadtime is not None else 0
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _manufacturing_capacity_hours(policy: Mapping[str, Any], cfg: Mapping[str, Any], node_key: str) -> int:
        """
        Resolve per-period manufacturing capacity in hours for a manufacturer.
        Default = time_bucket (days) * 24.
        """

        if isinstance(policy, Mapping):
            raw = policy.get("manufacturing_capacity_hours")
            try:
                if raw is not None:
                    return max(0, int(raw))
            except (TypeError, ValueError):
                pass
        # Fallback to node attributes
        for node in cfg.get("nodes") or []:
            name = node.get("name") or node.get("id")
            if MixedScenarioService._normalise_key(name) != MixedScenarioService._normalise_key(node_key):
                continue
            attrs = node.get("attributes") or {}
            raw = attrs.get("manufacturing_capacity_hours")
            try:
                if raw is not None:
                    return max(0, int(raw))
            except (TypeError, ValueError):
                pass

        bucket = normalize_time_bucket(cfg.get("time_bucket"))
        days = {"day": 1, "week": 7, "month": 30}.get(bucket.value, 7)
        return max(0, int(days * 24))

    @staticmethod
    def _capacity_utilization(policy: Mapping[str, Any], product_id: str) -> float:
        """
        Return hours required per unit of the finished item. Default 0 (no capacity consumption).
        """
        item_key = MixedScenarioService._normalise_product_id(product_id)
        util_map = {}
        if isinstance(policy, Mapping):
            util_map = policy.get("capacity_utilization_by_item") or {}
        util_val = None
        if isinstance(util_map, Mapping):
            util_val = util_map.get(item_key)
            if util_val is None:
                util_val = util_map.get(str(item_key))
        if util_val is None and isinstance(policy, Mapping):
            util_val = policy.get("capacity_utilization")
        if util_val is None:
            # Fallback to node attributes (if present on cfg.nodes)
            # This helper does not have direct access to cfg; callers should prefer passing values via policy.
            pass
        try:
            return float(util_val) if util_val is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _build_item_catalog(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        catalog: Dict[str, Dict[str, Any]] = {}
        for entry in cfg.get("items") or []:
            if not isinstance(entry, dict):
                continue
            product_id = entry.get("id")
            if product_id is None:
                continue
            catalog[MixedScenarioService._normalise_product_id(product_id)] = dict(entry)
        return catalog

    @staticmethod
    def _initialise_item_ledgers(
        state: Dict[str, Any],
        baseline: Optional[Dict[str, int]] = None,
    ) -> None:
        """Ensure per-item inventory/backlog collections exist for the node state."""

        baseline = baseline or {}
        inventory_by_item: Dict[str, int] = {}
        for product_id, qty in baseline.items():
            try:
                quantity = int(qty)
            except (TypeError, ValueError):
                continue
            if quantity < 0:
                quantity = 0
            item_token = MixedScenarioService._normalise_product_id(product_id)
            if not item_token:
                continue
            inventory_by_item[item_token] = quantity

        state["inventory_by_item"] = inventory_by_item
        state["backlog_by_item"] = state.get("backlog_by_item") or {}
        on_order_by_item: Dict[str, int] = {}
        raw_on_order = state.get("on_order_by_item")
        if isinstance(raw_on_order, dict):
            for key, value in raw_on_order.items():
                try:
                    qty_val = int(value)
                except (TypeError, ValueError):
                    continue
                if qty_val < 0:
                    qty_val = 0
                token = MixedScenarioService._normalise_product_id(key)
                on_order_by_item[token] = on_order_by_item.get(token, 0) + qty_val
        if not on_order_by_item:
            try:
                on_order_total = int(state.get("on_order", 0) or 0)
            except (TypeError, ValueError):
                on_order_total = 0
            if on_order_total and inventory_by_item:
                default_key = next(iter(inventory_by_item.keys()))
                on_order_by_item[default_key] = on_order_total
        state["on_order_by_item"] = on_order_by_item
        state["base_stock_by_item"] = state.get("base_stock_by_item") or dict(inventory_by_item)
        state["order_sequence"] = int(state.get("order_sequence") or 0)
        state["inventory"] = sum(inventory_by_item.values())
        state["backlog"] = sum(int(value) for value in state.get("backlog_by_item", {}).values())

    @staticmethod
    def _derive_component_metadata(
        lane_views: Dict[str, Any],
        configured_bom: Mapping[str, Mapping[str, Mapping[str, Any]]],
        node_item_baselines: Dict[str, Dict[str, int]],
    ) -> Tuple[Dict[str, Dict[str, Dict[str, int]]], Dict[str, str], Dict[str, str]]:
        """Normalise the configured BOM and map components to suppliers when possible.

        The tuple returned is (bill_of_materials, component_registry, component_sources)
        where:
            * bill_of_materials[node][product_id] -> {component_id: qty}
            * component_registry[node] -> component_id (for supplier nodes)
            * component_sources[component_id] -> supplier node key
        """

        node_types = lane_views.get("node_types") or {}
        orders_map = lane_views.get("orders_map") or {}
        bom: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
        component_registry: Dict[str, str] = {}
        component_sources: Dict[str, str] = {}

        for node_key, item_map in configured_bom.items():
            normalised_node = MixedScenarioService._normalise_key(node_key)
            if not normalised_node or not isinstance(item_map, Mapping):
                continue
            for product_id, components in item_map.items():
                if not isinstance(components, Mapping):
                    continue
                item_key = MixedScenarioService._normalise_product_id(product_id)
                component_payload: Dict[str, int] = {}
                for component_id, qty in components.items():
                    try:
                        qty_int = int(qty)
                    except (TypeError, ValueError):
                        continue
                    if qty_int <= 0:
                        continue
                    component_key = MixedScenarioService._normalise_product_id(component_id)
                    component_payload[component_key] = qty_int
                if component_payload:
                    bom[normalised_node][item_key] = component_payload

        for node, node_type in node_types.items():
            if node_type != "manufacturer":
                continue
            upstream_suppliers = [
                upstream
                for upstream in orders_map.get(node, [])
                if node_types.get(upstream) == "supplier"
            ]
            if len(upstream_suppliers) != 1:
                continue
            supplier = upstream_suppliers[0]
            for component_map in bom.get(node, {}).values():
                for component_id in component_map.keys():
                    component_registry.setdefault(supplier, component_id)
                    component_sources.setdefault(component_id, supplier)
                    node_item_baselines.setdefault(supplier, {}).setdefault(component_id, 0)

        # Fallback: map supplier nodes directly to their own component ids when present in BOM keys.
        for node, node_type in node_types.items():
            if node_type != "supplier":
                continue
            comp_id = MixedScenarioService._normalise_key(node)
            if not comp_id:
                continue
            component_registry.setdefault(node, comp_id)
            component_sources.setdefault(comp_id, node)
            node_item_baselines.setdefault(node, {}).setdefault(comp_id, 0)

        return (
            {node: {item: dict(components) for item, components in item_map.items()} for node, item_map in bom.items()},
            component_registry,
            component_sources,
        )

    @staticmethod
    def _make_order_request(
        state: Dict[str, Any],
        *,
        product_id: Any,
        quantity: int,
        downstream: Optional[str],
        due_round: int,
        priority: int,
        source: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a normalised order request payload."""

        try:
            qty_int = int(quantity)
        except (TypeError, ValueError):
            qty_int = 0
        if qty_int <= 0:
            return None
        order_sequence = int(state.get("order_sequence") or 0) + 1
        state["order_sequence"] = order_sequence
        return {
            "product_id": MixedScenarioService._normalise_product_id(product_id),
            "quantity": qty_int,
            "downstream": MixedScenarioService._normalise_key(downstream) if downstream else None,
            "due_round": int(due_round),
            "order_priority": max(1, int(priority)),
            "source": source,
            "sequence": order_sequence,
        }

    @staticmethod
    def _expand_order_breakdown(
        state: Dict[str, Any],
        entry: Dict[str, Any],
        *,
        current_round: int,
    ) -> List[Dict[str, Any]]:
        """Expand a queue entry into per-item order requests."""

        results: List[Dict[str, Any]] = []
        breakdown = entry.get("breakdown") or {}
        base_item = MixedScenarioService._normalise_product_id(entry.get("product_id"))
        downstream_default = entry.get("downstream")
        priority = entry.get("order_priority", 1)
        due_round = entry.get("step_number", current_round)

        if isinstance(breakdown, dict) and breakdown:
            for downstream, payload in breakdown.items():
                if isinstance(payload, dict):
                    for product_id, qty in payload.items():
                        order = MixedScenarioService._make_order_request(
                            state,
                            product_id=product_id,
                            quantity=qty,
                            downstream=downstream,
                            due_round=due_round,
                            priority=priority,
                            source=entry.get("source"),
                        )
                        if order:
                            results.append(order)
                else:
                    order = MixedScenarioService._make_order_request(
                        state,
                        product_id=base_item,
                        quantity=payload,
                        downstream=downstream,
                        due_round=due_round,
                        priority=priority,
                        source=entry.get("source"),
                    )
                    if order:
                        results.append(order)
        else:
            order = MixedScenarioService._make_order_request(
                state,
                product_id=base_item,
                quantity=entry.get("quantity", 0),
                downstream=downstream_default,
                due_round=due_round,
                priority=priority,
                source=entry.get("source"),
            )
            if order:
                results.append(order)

        return results

    @staticmethod
    def _can_build_item(
        node_key: str,
        product_id: str,
        quantity: int,
        bom_map: Mapping[str, Mapping[str, Mapping[str, int]]],
        inventory_by_item: Dict[str, int],
    ) -> bool:
        components = bom_map.get(node_key, {}).get(product_id)
        if not components:
            return True
        for component_id, component_qty in components.items():
            required = max(0, int(component_qty)) * quantity
            if required <= 0:
                continue
            if inventory_by_item.get(component_id, 0) < required:
                return False
        return True

    @staticmethod
    def _consume_components(
        node_key: str,
        product_id: str,
        quantity: int,
        bom_map: Mapping[str, Mapping[str, Mapping[str, int]]],
        inventory_by_item: Dict[str, int],
    ) -> None:
        components = bom_map.get(node_key, {}).get(product_id)
        if not components:
            return
        for component_id, component_qty in components.items():
            required = max(0, int(component_qty)) * quantity
            if required <= 0:
                continue
            current = inventory_by_item.get(component_id, 0)
            inventory_by_item[component_id] = max(0, current - required)

    @staticmethod
    def _max_buildable_quantity(
        node_key: str,
        product_id: str,
        inventory_by_item: Dict[str, int],
        bom_map: Mapping[str, Mapping[str, Mapping[str, int]]],
    ) -> int:
        components = bom_map.get(node_key, {}).get(product_id)
        if not components:
            return 0
        capacity: Optional[int] = None
        for component_id, component_qty in components.items():
            required = max(1, int(component_qty))
            available = inventory_by_item.get(component_id, 0)
            if required <= 0:
                continue
            candidate = available // required
            if capacity is None or candidate < capacity:
                capacity = candidate
        return max(0, capacity or 0)

    @staticmethod
    def _produce_manufactured_item(
        node_key: str,
        product_id: str,
        quantity: int,
        inventory_by_item: Dict[str, int],
        bom_map: Mapping[str, Mapping[str, Mapping[str, int]]],
    ) -> int:
        if quantity <= 0:
            return 0
        buildable = MixedScenarioService._max_buildable_quantity(
            node_key,
            product_id,
            inventory_by_item,
            bom_map,
        )
        build_qty = min(quantity, buildable)
        if build_qty <= 0:
            return 0
        MixedScenarioService._consume_components(
            node_key,
            product_id,
            build_qty,
            bom_map,
            inventory_by_item,
        )
        inventory_by_item[product_id] = inventory_by_item.get(product_id, 0) + build_qty
        return build_qty

    @staticmethod
    def _split_quantity(total: int, parts: int) -> List[int]:
        if parts <= 0:
            return []
        base = total // parts
        remainder = total % parts
        allocation: List[int] = []
        for idx in range(parts):
            allocation.append(base + (1 if idx < remainder else 0))
        return allocation

    @staticmethod
    def _draw_demand_value(
        pattern_source: Optional[Dict[str, Any]],
        round_number: int,
    ) -> Tuple[int, Dict[str, Any]]:
        pattern = normalize_demand_pattern(pattern_source or {})
        params = pattern.get("params", {}) if isinstance(pattern.get("params", {}), dict) else {}

        try:
            pattern_type = DemandPatternType(pattern.get("type", DemandPatternType.CLASSIC.value))
        except ValueError:
            pattern_type = DemandPatternType.CLASSIC

        if pattern_type == DemandPatternType.CLASSIC:
            initial = int(params.get("initial_demand", DEFAULT_CLASSIC_PARAMS["initial_demand"]))
            final = int(params.get("final_demand", DEFAULT_CLASSIC_PARAMS["final_demand"]))
            change_week = int(params.get("change_week", DEFAULT_CLASSIC_PARAMS["change_week"]))
            demand_value = final if round_number >= change_week else initial
            return max(0, int(demand_value)), pattern

        if pattern_type == DemandPatternType.RANDOM:
            try:
                min_demand = int(round(float(params.get("min_demand", 1))))
            except (TypeError, ValueError):
                min_demand = 1
            try:
                max_demand = int(round(float(params.get("max_demand", min_demand))))
            except (TypeError, ValueError):
                max_demand = min_demand
            if max_demand < min_demand:
                max_demand = min_demand
            return random.randint(min_demand, max_demand), pattern

        if pattern_type == DemandPatternType.CONSTANT:
            candidate = None
            for key in ("demand", "value", "mean"):
                candidate = params.get(key)
                if candidate is not None:
                    break
            if candidate is None:
                return DEFAULT_CLASSIC_PARAMS["initial_demand"], pattern
            try:
                return max(0, int(round(float(candidate)))), pattern
            except (TypeError, ValueError):
                return DEFAULT_CLASSIC_PARAMS["initial_demand"], pattern

        if pattern_type == DemandPatternType.SEASONAL:
            try:
                base = float(params.get("base_demand", DEFAULT_CLASSIC_PARAMS["initial_demand"]))
            except (TypeError, ValueError):
                base = float(DEFAULT_CLASSIC_PARAMS["initial_demand"])
            try:
                amplitude = float(params.get("amplitude", 0.0))
            except (TypeError, ValueError):
                amplitude = 0.0
            try:
                period = int(round(float(params.get("period", 12))))
            except (TypeError, ValueError):
                period = 12
            period = max(1, period)
            angle = 2.0 * math.pi * ((round_number - 1) % period) / period
            demand_value = base + amplitude * math.sin(angle)
            return max(0, int(round(demand_value))), pattern

        if pattern_type == DemandPatternType.LOGNORMAL:
            log_params = normalize_lognormal_params(params)
            seed = log_params.get("seed")
            if seed is None:
                seed = secrets.randbits(32)
                log_params["seed"] = seed
            else:
                try:
                    seed = int(seed)
                except (TypeError, ValueError):
                    seed = secrets.randbits(32)
                    log_params["seed"] = seed

            draw_seed = seed + max(0, round_number - 1)
            samples = DemandGenerator.generate_lognormal(
                num_rounds=1,
                mean=log_params.get("mean", DEFAULT_CLASSIC_PARAMS["initial_demand"]),
                cov=log_params.get("cov", 1.0),
                min_demand=log_params.get("min_demand"),
                max_demand=log_params.get("max_demand"),
                stddev=log_params.get("stddev"),
                seed=draw_seed,
            )
            pattern["params"] = log_params
            return (samples[0] if samples else DEFAULT_CLASSIC_PARAMS["initial_demand"]), pattern

        return DEFAULT_CLASSIC_PARAMS["initial_demand"], pattern

    @staticmethod
    def _compute_market_round_demand(
        game: Game,
        cfg: Dict[str, Any],
        round_number: int,
        lane_views: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Dict[str, int]], int]:
        result: Dict[str, Dict[str, int]] = defaultdict(dict)
        market_entries = cfg.get("market_demands")
        updated_entries: List[Dict[str, Any]] = []
        market_lookup = MixedScenarioService._market_node_lookup(cfg, lane_views)

        if isinstance(market_entries, list) and market_entries:
            for entry in market_entries:
                if not isinstance(entry, dict):
                    continue
                node_key = MixedScenarioService._resolve_market_node_key(entry, market_lookup)
                if not node_key:
                    raise ValueError("Market demand entry is missing a market_node mapping")
                product_id = entry.get("product_id") or entry.get("item_id") or entry.get("item") or entry.get("sku")
                if product_id is None:
                    raise ValueError(f"Market demand entry missing product_id: {entry.keys()}")
                demand_value, normalised_pattern = MixedScenarioService._draw_demand_value(
                    entry.get("demand_pattern"),
                    round_number,
                )
                updated_entry = dict(entry)
                updated_entry["demand_pattern"] = normalised_pattern
                updated_entries.append(updated_entry)
                result[node_key][str(product_id)] = result[node_key].get(str(product_id), 0) + max(0, int(demand_value))

            if updated_entries:
                cfg["market_demands"] = updated_entries
                total = sum(sum(items.values()) for items in result.values())
                return {node: dict(items) for node, items in result.items()}, int(total)

        raise ValueError("No market_demands configured; market demand must be explicitly defined on Market Demand nodes")

    def _preprocess_queues(self, context: RoundContext) -> None:
        """Process global queues to determine arrivals and matured orders for the round."""
        current_round = context.round_number
        node_policies = context.node_policies
        
        # Use a stable node order for logging: downstream-to-upstream if possible.
        node_order = list(context.topology.node_sequence or [])
        if not node_order:
            node_order = list(context.node_states.keys())
        else:
            # If sequence appears upstream->downstream (e.g., market_supply first), reverse it for downstream-first logs.
            if node_order and node_order[0].startswith("market_supply"):
                node_order = list(reversed(node_order))

        for node_key in node_order:
            state = context.node_states.get(node_key)
            if not state:
                continue
            policy = node_policies.get(node_key, {})
            # Ensure inbound demand/supply collections exist
            if not hasattr(state, "inbound_demand"):
                state.inbound_demand = []
            if not hasattr(state, "inbound_supply"):
                state.inbound_supply = []
            if not hasattr(state, "inbound_supply_future"):
                state.inbound_supply_future = []

            def _order_queue_sort(order: OrderRequest) -> Tuple[int, int, str, int, int, int]:
                item_key = MixedScenarioService._normalise_product_id(order.product_id)
                priority_key = MixedScenarioService._priority_sort_key(
                    item_key, context.item_priorities or {}
                )
                due_step = order.step_number if order.step_number is not None else order.due_round
                seq = order.sequence if order.sequence is not None else 0
                ord_priority = order.order_priority if order.order_priority is not None else 0
                return (*priority_key, due_step or current_round, ord_priority, seq)

            # Ensure inbound orders and backlog orders respect item priority before maturity
            state.inbound_demand.sort(key=_order_queue_sort)
            state.backlog_orders.sort(key=_order_queue_sort)
            
            # 1. Process Orders Queue
            # Identify orders that are due to be processed in this round (step_number <= current_round)
            matured_orders = []
            remaining_orders = []
            orders_count_by_item: Dict[str, int] = defaultdict(int)
            
            for order in state.inbound_demand:
                # Use step_number or due_round. The model has due_round, but logic uses step_number alias often.
                # Let's assume due_round is the source of truth for "when to process".
                # The original code uses 'step_number'.
                due_step = order.step_number if order.step_number is not None else order.due_round
                
                if due_step <= current_round:
                    matured_orders.append(order)
                    item_key = MixedScenarioService._normalise_product_id(order.product_id)
                    orders_count_by_item[item_key] += 1
                else:
                    remaining_orders.append(order)
            
            state.matured_orders = matured_orders
            state.debug_matured_counts = dict(orders_count_by_item)
            state.debug_matured_orders_snapshot = list(matured_orders)
            # Preserve individual orders so source-level priorities remain intact.
            remaining_orders.sort(key=_order_queue_sort)
            state.inbound_demand = remaining_orders
            
            # 2. Process Arrivals Queue
            # Identify shipments that have arrived (arrival_round <= current_round)
            supply_leadtime = max(0, int(policy.get('supply_leadtime', 0)))
            
            due_arrivals = []
            remaining_arrivals = []
            arrival_count_by_item: Dict[str, int] = defaultdict(int)
            
            # Note: The original code normalizes arrivals queue with fallback to ship_queue.
            # Here we assume inbound_supply_future is already populated correctly from state.
            
            for shipment in state.inbound_supply_future:
                if shipment.arrival_round <= current_round:
                    due_arrivals.append(shipment)
                    item_key = MixedScenarioService._normalise_product_id(shipment.product_id)
                    arrival_count_by_item[item_key] += 1
                else:
                    remaining_arrivals.append(shipment)
            
            state.inbound_supply = due_arrivals
            state.debug_due_arrivals_counts = dict(arrival_count_by_item)
            state.debug_due_arrivals_snapshot = list(due_arrivals)
            # Preserve distinct shipments; do not merge similar entries.
            state.inbound_supply_future = remaining_arrivals

            # Do not cap queues; retain full order/arrival history for lead-time processing

    def _node_processing_order(self, context: RoundContext) -> List[str]:
        sequence = list(context.topology.node_sequence or [])
        # Process nodes in DAG order from downstream to upstream (market_demand -> ... -> market_supply)
        base_order = list(reversed(sequence)) if sequence else list(context.node_states.keys())
        node_types = context.topology.node_types or {}
        node_priority_map = context.node_priorities or {}

        ordered: List[str] = []
        idx = 0
        while idx < len(base_order):
            node = base_order[idx]
            node_type = node_types.get(node, "")
            same_type: List[str] = [node]
            idx += 1
            while idx < len(base_order) and node_types.get(base_order[idx], "") == node_type:
                same_type.append(base_order[idx])
                idx += 1
            same_type.sort(key=lambda n: MixedScenarioService._priority_sort_key(n, node_priority_map))
            ordered.extend(same_type)

        return ordered

    def _process_node_echelon(self, context: RoundContext) -> None:
        """Process nodes in reverse topological order (downstream to upstream)."""
        # Initialize demand tracking
        demand_inputs: Dict[str, int] = defaultdict(int)
        demand_item_inputs: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        # Identify nodes controlled by AI scenario_users so we don't double-plan orders:
        # deterministic replenishment here plus agent decisions later can over-order.
        ai_nodes: Set[str] = set()
        for assignment in context.config.get("player_assignments", []) or []:
            if not isinstance(assignment, Mapping):
                continue
            scenario_user_type = assignment.get("scenario_user_type") or assignment.get("type") or assignment.get("strategy")
            is_ai = str(scenario_user_type or "").upper() in {"AI", "AGENT"} or bool(assignment.get("is_ai"))
            if not is_ai:
                continue
            keys = assignment.get("node_keys") or [assignment.get("assignment_key") or assignment.get("role")]
            for key in keys or []:
                node_key = MixedScenarioService._normalise_key(key)
                if node_key:
                    ai_nodes.add(node_key)
        
        # Pre-populate demand from market demands (if any)
        # Note: In original code, this is done via _compute_market_round_demand which returns a map.
        # We should call that or similar logic before this loop or inside.
        # Let's assume context has the market demand info.
        # We need to implement _apply_market_demand to populate demand_inputs initially.
        self._apply_market_demand(context, demand_inputs, demand_item_inputs)

        for node_key in self._node_processing_order(context):
            if node_key not in context.node_states:
                continue
            
            state = context.node_states[node_key]
            # Reset per-round debug trace
            state.debug_trace = []

            # Trace: Start (before processing arrivals)
            def _count_by_item(queue: List[Any]) -> Dict[str, int]:
                counts: Dict[str, int] = defaultdict(int)
                for entry in queue or []:
                    item_token = MixedScenarioService._normalise_product_id(getattr(entry, "product_id", None) or entry.get("product_id") if isinstance(entry, Mapping) else None)
                    if item_token:
                        counts[item_token] += 1
                return dict(counts)

            # Prefer the precomputed matured/arrival counts from preprocessing; fall back to live queues.
            start_orders_count = {}
            try:
                dbg_orders = getattr(state, "debug_matured_counts", None)
                if isinstance(dbg_orders, dict) and dbg_orders:
                    start_orders_count = {MixedScenarioService._normalise_product_id(k): int(v) for k, v in dbg_orders.items()}
            except Exception:
                start_orders_count = {}
            if not start_orders_count:
                start_orders_count = _count_by_item(getattr(state, "matured_orders", []))
            if not start_orders_count:
                start_orders_count = _count_by_item(getattr(state, "inbound_demand", []))

            start_supply_count = {}
            try:
                dbg_supply = getattr(state, "debug_due_arrivals_counts", None)
                if isinstance(dbg_supply, dict) and dbg_supply:
                    start_supply_count = {MixedScenarioService._normalise_product_id(k): int(v) for k, v in dbg_supply.items()}
            except Exception:
                start_supply_count = {}
            if not start_supply_count:
                start_supply_count = _count_by_item(getattr(state, "inbound_supply", []))
            if not start_supply_count:
                start_supply_count = _count_by_item(getattr(state, "inbound_supply_future", []))
            try:
                state.debug_start_inventory = sum(state.inventory_by_item.values())
            except Exception:
                state.debug_start_inventory = None
            state.debug_trace.append(
                {
                    "step": "Start",
                    "inventory": state.debug_start_inventory,
                    "inventory_by_item": dict(state.inventory_by_item or {}),
                    "inbound_demand": start_orders_count,
                    "inbound_supply": start_supply_count,
                }
            )

            # 1. Calculate Demand (from downstream orders + market demand)
            self._calculate_node_demand(node_key, state, context, demand_inputs, demand_item_inputs)

            # 2. Fulfill Orders (create shipments, update backlog)
            # Capture inbound demand/arrival counts before fulfillment
            inbound_demand_count_before = len(getattr(state, "matured_orders", []) or [])
            inbound_supply_count_before = len(getattr(state, "inbound_supply", []) or [])
            self._fulfill_node_orders(node_key, state, context)
            supply_pending_after_demand = _count_by_item(getattr(state, "inbound_supply", []))
            try:
                state.debug_post_demand_inventory = sum(state.inventory_by_item.values())
            except Exception:
                state.debug_post_demand_inventory = None
            state.debug_trace.append(
                {
                    "step": "Process Demand",
                    "inbound_demand": getattr(state, "debug_post_demand_queue", len(getattr(state, "matured_orders", []) or [])),
                    "inbound_supply_pending": supply_pending_after_demand,
                    "inventory_after": state.debug_post_demand_inventory,
                    "inventory_by_item": dict(state.inventory_by_item or {}),
                }
            )

            # 3. Update Inventory from Arrivals
            self._update_node_inventory(node_key, state, context)
            # Snapshot inventory after arrivals (start-of-round)
            try:
                state.debug_start_inventory = sum(state.inventory_by_item.values())
            except Exception:
                state.debug_start_inventory = None
            # Supply already processed in _update_node_inventory; capture what was received this round
            supply_received = dict(getattr(state, "supply_received_by_item", {}) or {})
            state.debug_trace.append(
                {
                    "step": "Process Supply",
                    "inbound_supply": _count_by_item(getattr(state, "debug_post_supply_queue", [])) or len(getattr(state, "inbound_supply", []) or []),
                    "supply_received": supply_received,
                    "inventory_by_item": dict(state.inventory_by_item or {}),
                }
            )

            # 4. Replenishment orders are deferred to scenario_users/agents; no automatic orders here.
            # End trace placeholder; final inventory will be set in history block
            state.debug_trace.append(
                {
                    "step": "End",
                    "inventory": sum(state.inventory_by_item.values()),
                    "backlog": sum((state.backlog_by_item or {}).values()),
                    "inventory_by_item": dict(state.inventory_by_item or {}),
                }
            )

    def _apply_market_demand(self, context: RoundContext, demand_inputs: Dict[str, int], demand_item_inputs: Dict[str, Dict[str, int]]) -> None:
        """
        Inject external customer demand.

        Rules:
        - The Market Demand node owns the demand (so reporting shows demand at that node).
        - Orders to satisfy that demand are placed on the upstream supplier(s) (e.g., retailer) as current-round orders.
        """
        if not context.market_demand_map:
            return

        shipments_map = context.topology.shipments_map or {}
        orders_map = context.topology.orders_map or {}
        current_round = context.round_number

        for market_node, item_map in context.market_demand_map.items():
            market_key = MixedScenarioService._normalise_key(market_node)
            if not market_key:
                market_key = market_node
            # 1) Record demand on the market node itself for reporting
            item_detail_market = demand_item_inputs.setdefault(market_key, {})
            node_total = 0
            for key, value in item_map.items():
                qty = int(value)
                if qty <= 0:
                    continue
                item_key = MixedScenarioService._normalise_product_id(key)
                node_total += qty
                item_detail_market[item_key] = item_detail_market.get(item_key, 0) + qty
            if node_total > 0:
                demand_inputs[market_key] += node_total

            # 2) Identify upstream suppliers that must satisfy this market demand
            suppliers = list(orders_map.get(market_key) or orders_map.get(market_node) or [])
            if not suppliers:
                suppliers = [
                    upstream
                    for upstream, downstreams in shipments_map.items()
                    if market_key in [MixedScenarioService._normalise_key(d) for d in downstreams]
                ]
            if not suppliers:
                # Fallback: assume the market node's immediate upstream is itself (no supply chain)
                suppliers = [market_key]

            # 3) Push orders to suppliers as actual orders with the lane-specific lead time.
            for supplier in suppliers:
                if supplier not in context.node_states:
                    continue
                supplier_state = context.node_states[supplier]
                lane = (
                    context.topology.lane_lookup.get((supplier, market_key))
                    or context.topology.lane_lookup.get((supplier, market_node))
                )
                order_lead: Optional[int] = None
                if lane is not None:
                    order_lead = getattr(lane, "demand_lead_time", None) or getattr(lane, "order_leadtime", None)
                if order_lead is None:
                    policy_cfg = context.node_policies.get(supplier, {}) or {}
                    if isinstance(policy_cfg, Mapping):
                        order_lead = policy_cfg.get("order_leadtime")
                    else:
                        order_lead = getattr(policy_cfg, "order_leadtime", None)
                lead_steps = MixedScenarioService._coerce_leadtime_value(order_lead)
                if lead_steps is None or lead_steps < 1:
                    lead_steps = 1

                for key, value in item_map.items():
                    qty = int(value)
                    if qty <= 0:
                        continue
                    product_id = MixedScenarioService._normalise_product_id(key)
                    due_round = current_round + lead_steps
                    order_req = OrderRequest(
                        product_id=product_id,
                        quantity=qty,
                        downstream=market_node,
                        due_round=due_round,
                        step_number=due_round,
                        source=market_key,
                    )
                    queue = list(getattr(supplier_state, "inbound_demand", []) or [])
                    queue.append(order_req)
                    supplier_state.inbound_demand = queue
                    market_state = context.node_states.get(market_key) or context.node_states.get(market_node)
                    if market_state:
                        backlog_queue = list(getattr(market_state, "backlog_orders", []) or [])
                        market_order = OrderRequest(**order_req.dict())
                        backlog_queue.append(market_order)
                        market_state.backlog_orders = backlog_queue
                        qty_units = max(0, int(market_order.quantity))
                        if qty_units > 0:
                            market_state.otif_total_orders = getattr(market_state, "otif_total_orders", 0) + 1
                            market_state.otif_total_units = getattr(market_state, "otif_total_units", 0) + qty_units

    def _update_node_inventory(self, node_key: str, state: NodeState, context: RoundContext) -> None:
        # Update inventory based on state.inbound_supply (matured arrivals)
        node_type = context.topology.node_types.get(node_key, '')
        master_type = MixedScenarioService._resolve_node_master_type(context.topology, node_key)
        policy = context.node_policies.get(node_key, {})

        # Ensure ledgers exist
        if state.inventory_by_item is None:
            state.inventory_by_item = {}
        if state.on_order_by_item is None:
            state.on_order_by_item = {}

        supply_received: Dict[str, int] = defaultdict(int)

        if master_type == "market_demand":
            self._process_market_demand_shipments(node_key, state, context)
            return

        if master_type == "market_supply":
            for shipment in state.inbound_supply:
                qty_val = max(0, int(shipment.quantity))
                if qty_val <= 0:
                    continue
                item_token = MixedScenarioService._normalise_product_id(shipment.product_id)
                supply_received[item_token] += qty_val

            state.supply_received_by_item = dict(supply_received)
            cap_map = MixedScenarioService._market_supply_capacity(policy, state)
            if cap_map:
                state.inventory_by_item = dict(cap_map)
                state.inventory = sum(cap_map.values())
            else:
                state.inventory_by_item = {}
                state.inventory = 0
            state.on_order_by_item = {}
            backlog_summary: Dict[str, int] = defaultdict(int)
            for order in state.backlog_orders or []:
                product_id = MixedScenarioService._normalise_product_id(order.product_id)
                backlog_summary[product_id] += max(0, int(order.quantity))
            state.backlog_by_item = dict(backlog_summary)
            state.backlog = sum(backlog_summary.values())
            state.inbound_supply = []
            return

        # Manufacturers treat component and finished inventories separately and may also process
        # internal manufacturing supply.
        if master_type == "manufacturer":
            cfg = context.config or {}
            bom_for_node = MixedScenarioService._bom_for_node(cfg, node_key)
            current_round = context.round_number

            finished_inventory = dict(getattr(state, "finished_inventory_by_item", {}) or {})
            component_inventory = dict(getattr(state, "component_inventory_by_item", {}) or {})

            if not finished_inventory and not component_inventory and state.inventory_by_item:
                for raw_item, qty in state.inventory_by_item.items():
                    item_token = MixedScenarioService._normalise_product_id(raw_item)
                    try:
                        qty_val = int(qty)
                    except (TypeError, ValueError):
                        qty_val = 0
                    if item_token in bom_for_node:
                        finished_inventory[item_token] = max(0, qty_val)
                    else:
                        component_inventory[item_token] = max(0, qty_val)

            # Process completed manufacturing supply (internal arrivals to finished inventory).
            manufacturing_supply_queue = list(getattr(state, "manufacturing_supply_queue", []) or [])
            due_manufacturing: List[Shipment] = []
            remaining_manufacturing: List[Shipment] = []
            manufactured_received: Dict[str, int] = defaultdict(int)

            for shipment in manufacturing_supply_queue:
                try:
                    arrival_round = getattr(shipment, "arrival_round", None)
                except Exception:
                    arrival_round = None
                if arrival_round is None:
                    arrival_round = current_round
                if arrival_round <= current_round:
                    due_manufacturing.append(shipment)
                else:
                    remaining_manufacturing.append(shipment)

            for shipment in due_manufacturing:
                qty_val = max(0, int(getattr(shipment, "quantity", 0) or 0))
                if qty_val <= 0:
                    continue
                item_token = MixedScenarioService._normalise_product_id(getattr(shipment, "product_id", None))
                manufactured_received[item_token] += qty_val
                finished_inventory[item_token] = finished_inventory.get(item_token, 0) + qty_val

            state.due_manufacturing = due_manufacturing
            state.manufacturing_supply_queue = remaining_manufacturing

            # Apply component arrivals to component inventory
            for shipment in state.inbound_supply:
                qty_val = max(0, int(shipment.quantity))
                if qty_val <= 0:
                    continue
                src_key = MixedScenarioService._normalise_key(getattr(shipment, "source", None))
                item_token = MixedScenarioService._normalise_product_id(shipment.product_id)
                component_key = None
                if bom_for_node and src_key:
                    for comp_map in bom_for_node.values():
                        if src_key in comp_map:
                            component_key = src_key
                            break
                inv_key = component_key or item_token
                component_inventory[inv_key] = component_inventory.get(inv_key, 0) + qty_val
                state.on_order_by_item[inv_key] = max(0, state.on_order_by_item.get(inv_key, 0) - qty_val)
                supply_received[inv_key] += qty_val

            combined_received: Dict[str, int] = {}
            for k, v in supply_received.items():
                combined_received[k] = v
            for k, v in manufactured_received.items():
                combined_received[k] = combined_received.get(k, 0) + v
            state.supply_received_by_item = combined_received

            # Backlog summaries reflect existing backlog orders (finished goods only) before fulfillment
            backlog_summary: Dict[str, int] = defaultdict(int)
            for order in state.backlog_orders:
                backlog_summary[MixedScenarioService._normalise_product_id(order.product_id)] += max(0, int(order.quantity))
            state.backlog_by_item = dict(backlog_summary)
            state.backlog = sum(backlog_summary.values())

            state.finished_inventory_by_item = {k: max(0, int(v)) for k, v in finished_inventory.items()}
            state.component_inventory_by_item = {k: max(0, int(v)) for k, v in component_inventory.items()}

            combined_inventory: Dict[str, int] = {}
            combined_inventory.update(state.finished_inventory_by_item)
            for k, v in state.component_inventory_by_item.items():
                combined_inventory[k] = combined_inventory.get(k, 0) + v

            state.inventory_by_item = combined_inventory
            state.inventory = sum(combined_inventory.values())
            state.inbound_supply = []
            state.debug_post_supply_queue = {}
            return

        # Apply arrivals to inventory and on-order
        for shipment in state.inbound_supply:
            qty_val = max(0, int(shipment.quantity))
            if qty_val <= 0:
                continue
            item_token = MixedScenarioService._normalise_product_id(shipment.product_id)
            supply_received[item_token] += qty_val
            if master_type != 'market_supply':
                state.inventory_by_item[item_token] = state.inventory_by_item.get(item_token, 0) + qty_val
                state.on_order_by_item[item_token] = max(0, state.on_order_by_item.get(item_token, 0) - qty_val)

        # Recompute aggregate fields
        for product_id, qty in state.inventory_by_item.items():
            state.inventory_by_item[product_id] = max(0, int(qty))
        # Backlog summaries reflect existing backlog orders before this round's fulfillment
        backlog_summary: Dict[str, int] = defaultdict(int)
        for order in state.backlog_orders:
            backlog_summary[MixedScenarioService._normalise_product_id(order.product_id)] += max(0, int(order.quantity))
        state.backlog_by_item = dict(backlog_summary)
        state.backlog = sum(backlog_summary.values())
        state.inventory = sum(state.inventory_by_item.values())
        state.supply_received_by_item = dict(supply_received)
        state.inbound_supply = []
        state.debug_post_supply_queue = {}

    def _market_demand_late_threshold(
        self,
        context: RoundContext,
        node_key: str,
        policy: Dict[str, Any],
    ) -> int:
        raw_threshold = policy.get("late_threshold")
        threshold = MixedScenarioService._coerce_leadtime_value(raw_threshold)
        if threshold is not None and threshold >= 0:
            return max(1, threshold)

        lane_lookup = getattr(context.topology, "lane_lookup", {}) or {}
        max_lead = 1
        for lane_rec in lane_lookup.values():
            if isinstance(lane_rec, dict):
                lane_data = lane_rec
            elif hasattr(lane_rec, "dict"):
                lane_data = lane_rec.dict()
            else:
                lane_data = {
                    "to": getattr(lane_rec, "to", None),
                    "supply_lead_time": getattr(lane_rec, "supply_lead_time", None),
                }
            to_node = lane_data.get("to")
            lead_val = MixedScenarioService._coerce_leadtime_value(lane_data.get("supply_lead_time"))
            if to_node != node_key:
                continue
            if lead_val is not None and lead_val > max_lead:
                max_lead = lead_val
        return max(1, 2 * max_lead)

    def _process_market_demand_shipments(
        self,
        node_key: str,
        state: NodeState,
        context: RoundContext,
    ) -> None:
        policy = context.node_policies.get(node_key, {}) or {}
        late_threshold = self._market_demand_late_threshold(context, node_key, policy)
        raw_cost = policy.get("lost_sale_cost")
        try:
            lost_sale_rate = float(raw_cost) if raw_cost is not None else 100.0
        except (TypeError, ValueError):
            lost_sale_rate = 100.0
        current_round = context.round_number

        pending_entries: List[Dict[str, Any]] = []
        for order in list(state.backlog_orders or []):
            qty = max(0, int(order.quantity or 0))
            if qty <= 0:
                continue
            due_round = order.step_number if order.step_number is not None else order.due_round
            if due_round is None:
                due_round = current_round
            item_token = MixedScenarioService._normalise_product_id(order.product_id) or str(order.product_id or "")
            pending_entries.append(
                {
                    "order": order,
                    "item": item_token,
                    "due_round": due_round,
                    "remaining": qty,
                    "total_quantity": qty,
                    "late": False,
                }
            )

        pending_by_item: Dict[str, deque] = defaultdict(deque)
        for entry in pending_entries:
            pending_by_item[entry["item"]].append(entry)

        fulfilled_by_item: Dict[str, int] = defaultdict(int)
        orders_completed: List[Dict[str, Any]] = []
        for shipment in list(getattr(state, "inbound_supply", []) or []):
            qty = max(0, int(shipment.quantity or 0))
            if qty <= 0:
                continue
            item_token = MixedScenarioService._normalise_product_id(shipment.product_id) or str(shipment.product_id or "")
            queue = pending_by_item.get(item_token)
            while queue and qty > 0:
                entry = queue[0]
                if entry["remaining"] <= 0:
                    queue.popleft()
                    continue
                allocate = min(entry["remaining"], qty)
                entry["remaining"] -= allocate
                qty -= allocate
                fulfilled_by_item[item_token] += allocate
                arrival_round = current_round
                if arrival_round - entry["due_round"] > late_threshold:
                    entry["late"] = True
                if entry["remaining"] == 0:
                    queue.popleft()
                    orders_completed.append(entry)
            if qty > 0:
                fulfilled_by_item[item_token] += qty

        lost_entries: List[Dict[str, Any]] = []
        for item_token, queue in list(pending_by_item.items()):
            preserved = deque()
            while queue:
                entry = queue.popleft()
                if entry["remaining"] <= 0:
                    continue
                if current_round - entry["due_round"] > late_threshold:
                    entry["late"] = True
                    lost_entries.append(entry)
                else:
                    preserved.append(entry)
            pending_by_item[item_token] = preserved

        backlog_summary: Dict[str, int] = defaultdict(int)
        remaining_orders: List[OrderRequest] = []
        for item_token, queue in pending_by_item.items():
            for entry in queue:
                backlog_summary[item_token] += entry["remaining"]
                entry["order"].quantity = entry["remaining"]
                remaining_orders.append(entry["order"])

        state.backlog_orders = remaining_orders
        state.backlog_by_item = dict(backlog_summary)
        state.backlog = sum(backlog_summary.values())
        state.inventory_by_item = {}
        state.inventory = 0
        state.on_order_by_item = {}
        existing_lost = dict(state.lost_sales_by_item or {})
        for entry in lost_entries:
            item = entry["item"]
            qty = entry["remaining"]
            if qty <= 0:
                continue
            existing_lost[item] = existing_lost.get(item, 0) + qty
            state.otif_late_units += entry["total_quantity"]
            state.otif_late_orders += 1
            state.otif_lost_sale_cost += lost_sale_rate * qty
        state.lost_sales_by_item = existing_lost

        for entry in orders_completed:
            qty = entry["total_quantity"]
            if entry["late"]:
                state.otif_late_units += qty
                state.otif_late_orders += 1
            else:
                state.otif_on_time_in_full_units += qty

        state.current_round_fulfillment = dict(fulfilled_by_item)
        state.supply_received_by_item = dict(fulfilled_by_item)
        state.debug_post_supply_queue = dict(fulfilled_by_item)
        state.inbound_supply = []

    # =========================================================================
    # Transfer Order Creation Helpers (Phase 1: DAG Execution)
    # =========================================================================

    def _create_transfer_order(
        self,
        scenario_id: int,
        scenario_user_id: int,
        source_site_id: int,
        destination_site_id: int,
        quantity: int,
        lead_time: int,
        round_number: int,
        source_scenario_user_period_id: Optional[int] = None,
        product_id: str = "DEFAULT",
    ) -> TransferOrder:
        """
        Create a TransferOrder for simulation execution.

        Uses AWS SC TransferOrder model with simulation extensions.
        Lead time comes from TransportationLane.supply_lead_time (AWS SC compliant).

        Args:
            scenario_id: Game ID
            scenario_user_id: ScenarioUser placing order (destination scenario_user)
            source_site_id: Source site ID
            destination_site_id: Destination site ID
            quantity: Order quantity
            lead_time: Lead time in rounds (from TransportationLane.supply_lead_time['value'])
            round_number: Current round number
            source_scenario_user_period_id: ScenarioUserPeriod ID that created this TO (bidirectional link)
            product_id: Product ID (default: "DEFAULT")

        Returns:
            Created TransferOrder with line items

        Notes:
            - arrival_round = order_round + lead_time
            - Status progression: DRAFT → SENT → IN_TRANSIT → RECEIVED
            - Uses TransportationLane.supply_lead_time for travel time (AWS SC compliant)
        """
        # Calculate arrival round
        arrival_round = round_number + lead_time

        # Get current date for timestamps
        current_date = date.today()

        # Generate unique TO number
        import uuid
        to_number = f"TO-G{scenario_id}-R{round_number}-{uuid.uuid4().hex[:8].upper()}"

        # Create TransferOrder
        transfer_order = TransferOrder(
            # AWS SC Standard Fields
            to_number=to_number,  # Required unique identifier
            source_site_id=source_site_id,
            destination_site_id=destination_site_id,
            status="IN_TRANSIT",  # Skip DRAFT/SENT for simulation simplicity
            shipment_date=current_date,
            estimated_delivery_date=current_date + timedelta(days=lead_time),
            transportation_mode="GROUND",
            carrier="Default Carrier",
            transportation_cost=0.0,  # Calculated post-hoc from TransportationLane.cost_per_unit if needed

            # Simulation Extensions (clearly marked)
            scenario_id=scenario_id,
            order_round=round_number,
            arrival_round=arrival_round,
            source_scenario_user_period_id=source_scenario_user_period_id,
        )

        self.db.add(transfer_order)
        self.db.flush()  # Get transfer_order.id

        # Create line item
        line_item = TransferOrderLineItem(
            to_id=transfer_order.id,
            line_number=1,  # Single line item for simulation simplicity
            product_id=product_id,
            quantity=quantity,
            requested_ship_date=current_date,
            requested_delivery_date=current_date + timedelta(days=lead_time),
        )

        self.db.add(line_item)
        self.db.flush()

        return transfer_order

    def _process_transfer_order_arrivals(
        self,
        scenario_id: int,
        current_round: int,
    ) -> List[TransferOrder]:
        """
        Process TransferOrders arriving in the current round.

        Queries all TOs where:
        - scenario_id matches
        - arrival_round == current_round
        - status == 'IN_TRANSIT'

        Updates:
        - Status → 'RECEIVED'
        - actual_delivery_date → current date
        - ScenarioUserPeriod.order_received += quantity (handled by caller)

        Args:
            scenario_id: Game ID
            current_round: Current round number

        Returns:
            List of arrived TransferOrders

        Notes:
            - Uses idx_to_game_arrival index for fast queries
            - Caller must update ScenarioUserPeriod.order_received
        """
        # Query arriving TOs using index-optimized query
        arriving_orders = (
            self.db.query(TransferOrder)
            .filter(
                TransferOrder.scenario_id == scenario_id,
                TransferOrder.arrival_round == current_round,
                TransferOrder.status == "IN_TRANSIT",
            )
            .all()
        )

        # Update status to RECEIVED
        current_date = date.today()
        for order in arriving_orders:
            order.status = "RECEIVED"
            order.actual_delivery_date = current_date

        # Commit updates
        if arriving_orders:
            self.db.flush()

        return arriving_orders

    def _get_lane_lead_time(
        self,
        config_id: int,
        source_site_id: int,
        destination_site_id: int,
    ) -> int:
        """
        Get lead time from TransportationLane.supply_lead_time (AWS SC compliant).

        Args:
            config_id: Supply chain configuration ID
            source_site_id: Source site ID
            destination_site_id: Destination site ID

        Returns:
            Lead time in rounds (from TransportationLane.supply_lead_time['value'])

        Raises:
            ValueError: If transportation lane not found

        Notes:
            - Uses TransportationLane.supply_lead_time (material flow lead time)
            - Format: {"type": "deterministic", "value": 2}
            - AWS SC compliant (no duplicate storage)
        """
        lane = (
            self.db.query(TransportationLane)
            .filter(
                TransportationLane.config_id == config_id,
                TransportationLane.from_site_id == source_site_id,
                TransportationLane.to_site_id == destination_site_id,
            )
            .first()
        )

        if not lane:
            raise ValueError(
                f"Transportation lane not found: config={config_id}, from={source_site_id}, to={destination_site_id}"
            )

        # Extract lead time value from JSON
        supply_lead_time = lane.supply_lead_time or {"type": "deterministic", "value": 2}
        lead_time_value = supply_lead_time.get("value", 2)

        return int(lead_time_value)

    # =========================================================================

    def _calculate_node_demand(self, node_key: str, state: NodeState, context: RoundContext, demand_inputs: Dict[str, int], demand_item_inputs: Dict[str, Dict[str, int]]) -> None:
        # Aggregate demand from demand_inputs and state.matured_orders

        orders_received: Dict[str, int] = defaultdict(int)
        node_type = context.topology.node_types.get(node_key, "")
        cfg = context.config or {}
        master_type = MixedScenarioService._resolve_node_master_type(context.topology, node_key)
        bom_for_node = MixedScenarioService._bom_for_node(cfg, node_key) if master_type == "manufacturer" else {}

        # 1. Add matured orders to demand inputs
        for order in state.matured_orders:
            qty = order.quantity
            if qty <= 0:
                continue
            demand_inputs[node_key] += qty

            # Track item detail
            product_id = MixedScenarioService._normalise_product_id(order.product_id)
            demand_item_inputs[node_key][product_id] = demand_item_inputs[node_key].get(product_id, 0) + qty
            orders_received[product_id] += qty

            # If order has parts (BOM explosion or similar), handle them?
            # Original code handles 'parts' in matured orders.
            # For now assuming simple orders.

        # 2. Merge market demand directly into the node's received orders where applicable
        market_orders = context.market_demand_map.get(node_key, {}) if context.market_demand_map else {}
        for raw_item, qty in market_orders.items():
            try:
                qty_val = int(qty)
            except (TypeError, ValueError):
                continue
            if qty_val <= 0:
                continue
            product_id = MixedScenarioService._normalise_product_id(raw_item)
            orders_received[product_id] += qty_val

        # 3. Merge pre-seeded demand (e.g., market demand injected upstream)
        # 4. Store total demand in state for visibility (no synthetic default item)
        state.current_round_demand = dict(demand_item_inputs.get(node_key, {}))
        state.orders_received_by_item = {k: max(0, int(v)) for k, v in orders_received.items()}

        # Expand manufacturer demand into component requirements so production is gated by available parts.
        if master_type == "manufacturer" and bom_for_node:
            component_requirements: Dict[str, int] = defaultdict(int)
            demand_basis: Dict[str, int] = defaultdict(int)
            for product_id, qty in state.orders_received_by_item.items():
                demand_basis[product_id] += max(0, int(qty))
            for product_id, qty in state.backlog_by_item.items():
                demand_basis[product_id] += max(0, int(qty))

            for finished_id, qty in demand_basis.items():
                comp_map = bom_for_node.get(finished_id)
                if not comp_map:
                    continue
                for comp_id, comp_qty in comp_map.items():
                    if comp_qty <= 0:
                        continue
                    component_requirements[comp_id] += qty * comp_qty

            inventory_snapshot = dict(state.inventory_by_item or {})
            buildable_from_components: Dict[str, int] = {}
            for finished_id, comp_map in bom_for_node.items():
                if not comp_map:
                    continue
                cap = min(
                    (inventory_snapshot.get(comp_id, 0) // comp_qty) if comp_qty > 0 else 0
                    for comp_id, comp_qty in comp_map.items()
                )
                buildable_from_components[finished_id] = max(0, int(cap))

            state.component_demand_by_item = {k: max(0, int(v)) for k, v in component_requirements.items()}
            state.buildable_by_item = buildable_from_components
        else:
            state.component_demand_by_item = {}
            state.buildable_by_item = {}

    def _fulfill_node_orders(self, node_key: str, state: NodeState, context: RoundContext) -> None:
        # Fulfill demand from inventory, create shipments, update backlog
        node_type = context.topology.node_types.get(node_key, '')
        master_type = MixedScenarioService._resolve_node_master_type(context.topology, node_key)
        policy = context.node_policies.get(node_key, {})
        cfg = context.config or {}
        bom_for_node = MixedScenarioService._bom_for_node(cfg, node_key) if master_type == "manufacturer" else {}

        # Market demand is a pure sink/source of demand; it does not ship or hold inventory.
        if master_type == "market_demand":
            # Market Demand handles fulfillment when supply arrivals are processed.
            state.current_round_fulfillment = dict(getattr(state, "current_round_fulfillment", {}) or {})
            return

        # Work with current inventory; apply arrivals after fulfilling orders (inventory nodes) or before manufacturing (manufacturers)
        inventory = dict(state.inventory_by_item or {})
        node_norm = MixedScenarioService._normalise_key(node_key)
        arrivals_to_apply = list(getattr(state, "inbound_supply", []) or [])

        # Gather all pending orders (backlog + new demand)
        # We need to construct a list of pending orders to process against inventory.
        # New demand is in state.matured_orders AND demand_inputs (which includes market demand).
        # But demand_inputs is just counters. We need the actual order objects or equivalent to know downstream destinations.
        
        # Wait, market demand doesn't have a specific downstream (it's the node itself or "market").
        # Matured orders have downstream.

        # Market Supply: finite (or infinite) source that ships by downstream priority.
        if master_type == "market_supply":
            cap_map = MixedScenarioService._market_supply_capacity(policy, state)
            infinite_supply = cap_map is None
            available_by_item = dict(cap_map or {})

            pending_orders: List[OrderRequest] = []
            pending_orders.extend(state.backlog_orders or [])
            pending_orders.extend(state.matured_orders or [])

            # Group by item and sort orders by downstream node priority then chronological fields.
            orders_by_item: Dict[str, List[OrderRequest]] = defaultdict(list)
            for order in pending_orders:
                product_id = MixedScenarioService._normalise_product_id(order.product_id)
                if not product_id:
                    continue
                orders_by_item[product_id].append(order)

            def _downstream_priority_key(order: OrderRequest) -> Tuple[int, int, int, int]:
                downstream = order.downstream or ""
                node_pri = context.node_priorities.get(downstream) if context.node_priorities else None
                pri = node_pri if node_pri is not None else 1_000_000
                due_step = order.step_number if order.step_number is not None else order.due_round
                seq = order.sequence if order.sequence is not None else 0
                ord_priority = order.order_priority if order.order_priority is not None else 0
                return (due_step or context.round_number, pri, ord_priority, seq)

            shipments_created: List[Shipment] = []
            fulfillment_by_item: Dict[str, int] = defaultdict(int)
            carry_over: List[OrderRequest] = []

            for product_id, item_orders in orders_by_item.items():
                item_orders.sort(key=_downstream_priority_key)
                available = None if infinite_supply else available_by_item.get(product_id, 0)

                for order in item_orders:
                    qty = max(0, int(order.quantity))
                    if qty <= 0:
                        continue

                    ship_qty = qty if infinite_supply else min(qty, available or 0)
                    if ship_qty > 0:
                        lane_config = context.topology.lane_lookup.get((node_key, order.downstream))
                        lead_time = getattr(lane_config, "supply_lead_time", 0) if lane_config else 0
                        shipment = Shipment(
                            product_id=product_id,
                            quantity=ship_qty,
                            source=node_key,
                            destination=order.downstream,
                            arrival_round=context.round_number + lead_time,
                        )
                        shipments_created.append(shipment)
                        fulfillment_by_item[product_id] += ship_qty
                        if not infinite_supply:
                            available = max(0, (available or 0) - ship_qty)

                    remainder = qty - ship_qty
                    if remainder > 0:
                        pending = order.copy()
                        pending.quantity = remainder
                        pending.step_number = (context.round_number + 1)
                        pending.due_round = pending.step_number
                        carry_over.append(pending)

                if not infinite_supply:
                    available_by_item[product_id] = max(0, int(available or 0))

            # Preserve future orders already queued beyond the current round.
            future_orders = list(getattr(state, "inbound_demand", []) or [])
            future_orders.extend(carry_over)
            future_orders.sort(
                key=lambda o: (
                    o.step_number if o.step_number is not None else (o.due_round or context.round_number),
                    o.order_priority if o.order_priority is not None else 0,
                    o.sequence if o.sequence is not None else 0,
                )
            )
            state.inbound_demand = future_orders

            backlog_summary: Dict[str, int] = defaultdict(int)
            for o in future_orders:
                item_key = MixedScenarioService._normalise_product_id(o.product_id)
                backlog_summary[item_key] += max(0, int(o.quantity))
            state.backlog_by_item = dict(backlog_summary)
            state.backlog = sum(backlog_summary.values())
            state.backlog_orders = []

            # Remaining supply after shipments is treated as on-hand for reporting.
            if infinite_supply:
                state.inventory_by_item = {}
                state.inventory = 0
            else:
                state.inventory_by_item = {k: max(0, int(v)) for k, v in available_by_item.items()}
                state.inventory = sum(state.inventory_by_item.values())

            state.lost_sales_by_item = {}
            state.current_round_fulfillment = {k: max(0, int(v)) for k, v in fulfillment_by_item.items()}
            context.inbound_supply.extend(shipments_created)
            # After shipping, apply any arrivals due this round to inventory
            for shipment in arrivals_to_apply:
                qty = max(0, int(getattr(shipment, "quantity", 0) or 0))
                if qty <= 0:
                    continue
                item_token = MixedScenarioService._normalise_product_id(getattr(shipment, "product_id", None))
                inventory[item_token] = max(0, int(inventory.get(item_token, 0))) + qty
            state.inventory_by_item = {k: max(0, int(v)) for k, v in inventory.items()}
            state.inventory = sum(state.inventory_by_item.values())
            state.debug_post_demand_queue = {}
            state.debug_post_supply_queue = {}
            state.matured_orders = []
            state.inbound_supply = []
            return

        if master_type == "manufacturer":
            current_round = context.round_number
            supply_lead = int(policy.get("supply_leadtime", 0) or 0)
            finished_inventory: Dict[str, int] = {}
            component_inventory: Dict[str, int] = {}
            for raw_item, qty in (state.inventory_by_item or {}).items():
                token = MixedScenarioService._normalise_product_id(raw_item)
                if token in bom_for_node:
                    finished_inventory[token] = max(0, int(qty))
                else:
                    component_inventory[token] = max(0, int(qty))

            # 1) Fulfill downstream demand using finished goods only
            pending_orders: List[OrderRequest] = list(state.backlog_orders or [])
            pending_orders.extend(state.matured_orders or [])
            shipments_created: List[Shipment] = []
            fulfillment_by_item: Dict[str, int] = defaultdict(int)
            next_backlog: List[OrderRequest] = []

            for order in pending_orders:
                product_id = MixedScenarioService._normalise_product_id(order.product_id)
                if not product_id:
                    continue
                qty = max(0, int(order.quantity))
                available = finished_inventory.get(product_id, 0)
                ship_qty = min(qty, available)
                if ship_qty > 0:
                    finished_inventory[product_id] = max(0, available - ship_qty)
                    if order.downstream:
                        lane = context.topology.lane_lookup.get((node_key, order.downstream))
                        lead_time = getattr(lane, "supply_lead_time", supply_lead) if lane else supply_lead
                        arrival_round = current_round + max(0, int(lead_time))
                        shipments_created.append(
                            Shipment(
                                product_id=product_id,
                                quantity=ship_qty,
                                source=node_key,
                                destination=order.downstream,
                                arrival_round=arrival_round,
                            )
                        )
                    fulfillment_by_item[product_id] += ship_qty
                remainder = qty - ship_qty
                if remainder > 0:
                    bo = order.copy()
                    bo.quantity = remainder
                    bo.step_number = current_round + 1
                    bo.due_round = bo.step_number
                    next_backlog.append(bo)

            # 2) Produce finished goods equal to shipments (gated by component inventory)
            produced_by_item: Dict[str, int] = defaultdict(int)
            consumed_by_item: Dict[str, int] = defaultdict(int)
            for finished_id, shipped_qty in fulfillment_by_item.items():
                bom = bom_for_node.get(finished_id, {})
                if not bom or shipped_qty <= 0:
                    continue
                cap_from_components = min(
                    (component_inventory.get(comp_id, 0) // comp_qty) if comp_qty > 0 else 0
                    for comp_id, comp_qty in bom.items()
                ) if bom else 0
                build_qty = min(shipped_qty, cap_from_components)
                if build_qty <= 0:
                    continue
                for comp_id, comp_qty in bom.items():
                    component_inventory[comp_id] = max(
                        0, int(component_inventory.get(comp_id, 0)) - comp_qty * build_qty
                    )
                    consumed_by_item[comp_id] += comp_qty * build_qty
                finished_inventory[finished_id] = finished_inventory.get(finished_id, 0) + build_qty
                produced_by_item[finished_id] += build_qty

            # 3) Apply component arrivals for this round
            for shipment in list(getattr(state, "inbound_supply", []) or []):
                qty_val = max(0, int(getattr(shipment, "quantity", 0) or 0))
                if qty_val <= 0:
                    continue
                item_token = MixedScenarioService._normalise_product_id(getattr(shipment, "product_id", None))
                if not item_token:
                    continue
                component_inventory[item_token] = component_inventory.get(item_token, 0) + qty_val

            # 4) Persist state and emit debug traces
            state.backlog_orders = next_backlog
            state.finished_inventory_by_item = {k: max(0, int(v)) for k, v in finished_inventory.items()}
            state.component_inventory_by_item = {k: max(0, int(v)) for k, v in component_inventory.items()}
            combined_inventory: Dict[str, int] = {}
            combined_inventory.update(state.finished_inventory_by_item)
            for k, v in state.component_inventory_by_item.items():
                combined_inventory[k] = combined_inventory.get(k, 0) + v
            state.inventory_by_item = combined_inventory
            state.inventory = sum(combined_inventory.values())

            backlog_summary = defaultdict(int)
            for bo in next_backlog:
                item_key = MixedScenarioService._normalise_product_id(bo.product_id)
                backlog_summary[item_key] += max(0, int(bo.quantity))
            state.backlog_by_item = dict(backlog_summary)
            state.backlog = sum(backlog_summary.values())

            state.current_round_fulfillment = {k: max(0, int(v)) for k, v in fulfillment_by_item.items()}
            state.lost_sales_by_item = {}
            state.debug_manufacture_output = dict(produced_by_item)
            state.component_demand_by_item = {
                comp_id: consumed_by_item.get(comp_id, 0) for comp_id in consumed_by_item.keys()
            }

            if getattr(state, "debug_trace", None) is not None:
                if produced_by_item:
                    state.debug_trace.append(
                        {
                            "step": "Produce",
                            "output_by_item": dict(produced_by_item),
                            "finished_inventory": dict(state.finished_inventory_by_item),
                        }
                    )
                if consumed_by_item:
                    state.debug_trace.append(
                        {
                            "step": "Consume",
                            "consumed_by_item": dict(consumed_by_item),
                            "component_inventory": dict(state.component_inventory_by_item),
                        }
                    )

            context.inbound_supply.extend(shipments_created)
            state.debug_post_demand_queue = {}
            state.debug_post_supply_queue = {}
            state.matured_orders = []
            state.inbound_supply = []
            return

        pending_orders: List[OrderRequest] = list(state.backlog_orders)

        # Add new orders from matured_orders
        pending_orders.extend(state.matured_orders)

        orders_by_item: Dict[str, List[OrderRequest]] = defaultdict(list)
        for order in pending_orders:
            product_id = MixedScenarioService._normalise_product_id(order.product_id)
            if not product_id:
                continue
            orders_by_item[product_id].append(order)

        for queue in orders_by_item.values():
            queue.sort(
                key=lambda x: (
                    x.step_number if x.step_number is not None else (x.due_round or context.round_number),
                    x.order_priority,
                    x.sequence if x.sequence is not None else 0,
                )
            )

        sorted_items = sorted(
            orders_by_item.keys(),
            key=lambda item: MixedScenarioService._priority_sort_key(item, context.item_priorities or {}),
        )

        next_backlog: List[OrderRequest] = []
        shipments_created: List[Shipment] = []
        fulfillment_by_item: Dict[str, int] = defaultdict(int)
        lost_sales: Dict[str, int] = defaultdict(int)
        orders_created_counter = 0

        infinite_supply = (node_type in {'market_supply', 'supplier'})

        for product_id in sorted_items:
            item_orders = orders_by_item[product_id]
            available = None if infinite_supply else inventory.get(product_id, 0)

            for idx, order in enumerate(item_orders):
                qty = max(0, int(order.quantity))
                if qty <= 0:
                    continue

                if master_type == "manufacturer":
                    bom_requirements = bom_for_node.get(product_id) if bom_for_node else None
                    if bom_requirements:
                        # How many finished units can we build from components?
                        component_cap = min(
                            (inventory.get(comp_id, 0) // comp_qty) if comp_qty > 0 else 0
                            for comp_id, comp_qty in bom_requirements.items()
                        ) if bom_requirements else 0
                        effective_available = (available or 0) + component_cap
                    else:
                        effective_available = (available or 0)
                    ship_qty = qty if infinite_supply else min(qty, effective_available)
                else:
                    ship_qty = qty if infinite_supply else min(qty, available or 0)

                if ship_qty > 0:
                    if not infinite_supply:
                        if master_type == "manufacturer":
                            # Consume finished inventory first
                            use_finished = min(available or 0, ship_qty)
                            available = max(0, (available or 0) - use_finished)
                            remaining_to_build = ship_qty - use_finished
                            if remaining_to_build > 0 and bom_for_node:
                                bom_requirements = bom_for_node.get(product_id, {})
                                for comp_id, comp_qty in bom_requirements.items():
                                    if comp_qty <= 0:
                                        continue
                                    inventory[comp_id] = max(
                                        0,
                                        int(inventory.get(comp_id, 0)) - comp_qty * remaining_to_build,
                                    )
                        else:
                            available = max(0, (available or 0) - ship_qty)

                    if order.downstream:
                        lane_config = context.topology.lane_lookup.get((node_key, order.downstream))
                        lead_time = 0
                        if lane_config:
                            lead_time = lane_config.supply_lead_time
                        else:
                            lead_time = int(policy.get('supply_leadtime', 0))

                        arrival_round = context.round_number + lead_time

                        shipment = Shipment(
                            product_id=product_id,
                            quantity=ship_qty,
                            source=node_key,
                            destination=order.downstream,
                            arrival_round=arrival_round
                        )
                        shipments_created.append(shipment)

                    fulfillment_by_item[product_id] += ship_qty

                remainder = qty - ship_qty
                if remainder > 0:
                    backlog_order = order.copy()
                    backlog_order.quantity = remainder
                    next_backlog.append(backlog_order)
                    for leftover in item_orders[idx + 1:]:
                        next_backlog.append(leftover)
                    if not infinite_supply:
                        available = 0
                    break

            if not infinite_supply:
                inventory[product_id] = max(0, int(available or 0))

        order_aging = max(0, int(policy.get("order_aging", 0) or 0))
        filtered_backlog: List[OrderRequest] = []
        current_round = context.round_number
        for order in next_backlog:
            product_id = MixedScenarioService._normalise_product_id(order.product_id)
            arrival_round = order.step_number if order.step_number is not None else order.due_round
            if arrival_round is None:
                arrival_round = current_round
            if order_aging > 0 and (current_round - arrival_round) > order_aging:
                lost_sales[product_id] += max(0, int(order.quantity))
                continue
            filtered_backlog.append(order)

        next_backlog = filtered_backlog

        state.inventory_by_item = inventory
        state.backlog_orders = next_backlog

        context.inbound_supply.extend(shipments_created)

        new_backlog_summary = defaultdict(int)
        for bo in next_backlog:
            item_key = MixedScenarioService._normalise_product_id(bo.product_id)
            arrival_round = bo.step_number if bo.step_number is not None else bo.due_round
            if arrival_round is None:
                arrival_round = current_round
            if arrival_round <= current_round:
                new_backlog_summary[item_key] += max(0, int(bo.quantity))

        state.backlog_by_item = dict(new_backlog_summary)
        state.backlog = sum(new_backlog_summary.values())
        # Market supply has infinite supply and does not hold stock.
        if master_type == "market_supply":
            state.inventory_by_item = {}
            state.inventory = 0
        else:
            state.inventory = sum(state.inventory_by_item.values())
        state.lost_sales_by_item = {k: max(0, int(v)) for k, v in lost_sales.items()}
        state.current_round_fulfillment = {k: max(0, int(v)) for k, v in fulfillment_by_item.items()}
        try:
            state.debug_orders_created = orders_created_counter
        except Exception:
            state.debug_orders_created = None
        state.debug_post_demand_queue = {}
        state.debug_post_supply_queue = {}
        state.matured_orders = []

    def _record_round_history(self, game: Game, context: RoundContext) -> None:
        """Append a concise history/debug snapshot for the completed round."""
        cfg = game.config or {}
        round_record = context.round_record
        round_index = getattr(round_record, "round_number", None) or context.round_number

        # Build base entry
        history_entry: Dict[str, Any] = {
            "round": round_index,
            "demand": int(getattr(round_record, "customer_demand", 0) or 0),
            "orders": {},
            "node_orders": {},
            "node_states": {},
            "inventory_positions": {},
            "inventory_positions_with_pipeline": {},
            "backlogs": {},
            "total_cost": 0.0,
            "period_start": None,
            "period_end": None,
            "agent_fallbacks": getattr(context, "agent_fallbacks", {}) or {},
        }
        try:
            period_start = getattr(round_record, "period_start", None)
            history_entry["period_start"] = period_start.isoformat() if period_start else None
        except Exception:
            history_entry["period_start"] = None
        try:
            period_end = getattr(round_record, "period_end", None)
            history_entry["period_end"] = period_end.isoformat() if period_end else None
        except Exception:
            history_entry["period_end"] = None

        node_types = context.topology.node_types or {}
        raw_display_names = (cfg.get("node_display_names") or {}) if isinstance(cfg, Mapping) else {}
        node_display_names: Dict[str, str] = {}
        for raw_key, label in raw_display_names.items():
            normalized_key = MixedScenarioService._normalise_key(raw_key)
            if not normalized_key:
                continue
            try:
                node_display_names[normalized_key] = str(label)
            except Exception:
                node_display_names[normalized_key] = str(raw_key)
        debug_payload: List[Dict[str, Any]] = []
        agent_comments = getattr(context, "agent_comments", {}) or {}

        items = cfg.get("items") or []
        item_name_by_id: Dict[str, str] = {}
        item_name_by_token: Dict[str, str] = {}
        for itm in items:
            itm_id = None
            itm_name = None
            if isinstance(itm, dict):
                itm_id = itm.get("id") or itm.get("product_id")
                itm_name = itm.get("name") or itm.get("description")
            else:
                itm_id = getattr(itm, "id", None)
                itm_name = getattr(itm, "name", None) or getattr(itm, "description", None)
            if itm_id is not None and itm_name:
                item_name_by_id[str(itm_id)] = str(itm_name)
            if itm_name:
                token = MixedScenarioService._canonical_role(itm_name)
                if token:
                    item_name_by_token.setdefault(token, str(itm_name))

        def _resolve_item_name(raw_id: Any) -> Optional[str]:
            if raw_id is None:
                return None
            if str(raw_id) in item_name_by_id:
                return item_name_by_id[str(raw_id)]
            token = MixedScenarioService._canonical_role(raw_id)
            if token and token in item_name_by_token:
                return item_name_by_token[token]
            return None

        def _with_item_names(queue: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            enriched: List[Dict[str, Any]] = []
            for entry in queue:
                if not isinstance(entry, dict):
                    continue
                clone = dict(entry)
                itm = clone.get("product_id")
                if itm is not None:
                    clone["item_name"] = _resolve_item_name(itm)
                enriched.append(clone)
            return enriched

        def _with_item_names_map(map_obj: Dict[str, Any]) -> Dict[str, Any]:
            enriched: Dict[str, Any] = {}
            for key, value in (map_obj or {}).items():
                try:
                    qty_val = int(value)
                except (TypeError, ValueError):
                    qty_val = value
                name = _resolve_item_name(key)
                if name:
                    enriched[name] = qty_val
                else:
                    enriched[key] = qty_val
            return enriched

        def _as_dict(entry: Any) -> Dict[str, Any]:
            if entry is None:
                return {}
            if isinstance(entry, dict):
                return dict(entry)
            if hasattr(entry, "dict"):
                try:
                    return dict(entry.dict())
                except Exception:
                    pass
            payload: Dict[str, Any] = {}
            for attr in ("product_id", "quantity", "source", "destination", "arrival_round", "due_round", "shipment_id"):
                value = getattr(entry, attr, None)
                if value is not None:
                    payload[attr] = value
            return payload

        def _collect_supply_entries(state_obj: NodeState, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
            combined: List[Dict[str, Any]] = []
            inbound_supply = snapshot.get("inbound_supply", []) or []
            future_supply = getattr(state_obj, "inbound_supply_future", []) or []
            for entry in inbound_supply:
                combined.append(_as_dict(entry))
            for entry in future_supply:
                combined.append(_as_dict(entry))
            return combined

        log_order = self._node_processing_order(context)

        for node_key in log_order:
            state = context.node_states.get(node_key)
            if not state:
                continue
            node_master_type = MixedScenarioService._resolve_node_master_type(context.topology, node_key)
            inventory_total = sum(max(0, int(v)) for v in state.inventory_by_item.values())
            backlog_total = sum(max(0, int(v)) for v in state.backlog_by_item.values())
            on_order_total = sum(max(0, int(v)) for v in state.on_order_by_item.values()) if state.on_order_by_item else 0
            order_total = sum(max(0, int(v)) for v in state.current_round_demand.values()) if state.current_round_demand else 0

            # Per-unit holding/backlog cost rates from InvPolicy (config-derived, not hardcoded)
            config_id = getattr(game, "supply_chain_config_id", None)
            if config_id:
                try:
                    holding_rate, backlog_rate = self._get_cost_rates_sync(config_id)
                except ValueError as _cost_err:
                    raise ValueError(
                        f"Cannot compute round costs for scenario {game.id}: {_cost_err}"
                    ) from _cost_err
            else:
                raise ValueError(
                    f"Scenario {game.id} has no supply_chain_config_id. "
                    f"Cannot load cost rates from InvPolicy. "
                    f"Ensure the scenario is linked to a supply chain config."
                )
            policy = context.node_policies.get(node_key, {}) if hasattr(context, "node_policies") else {}
            lost_sales_total = sum(max(0, int(v)) for v in getattr(state, "lost_sales_by_item", {}).values())
            policy_lost_sale_rate = policy.get("lost_sale_cost") if isinstance(policy, Mapping) else None
            try:
                lost_sale_rate = float(policy_lost_sale_rate) if policy_lost_sale_rate is not None else backlog_rate * 2
            except (TypeError, ValueError):
                lost_sale_rate = backlog_rate * 2
            holding_cost = inventory_total * holding_rate
            backlog_cost = backlog_total * backlog_rate + lost_sales_total * lost_sale_rate
            if node_types.get(node_key) == "market_supply":
                holding_cost = 0.0
                backlog_cost = 0.0
            elif node_types.get(node_key) == "market_demand":
                holding_cost = 0.0

            inbound_snapshot_orders = getattr(state, "debug_matured_orders_snapshot", None) or state.matured_orders
            inbound_snapshot_supply = getattr(state, "debug_due_arrivals_snapshot", None) or getattr(state, "inbound_supply", [])

            inventory_net = inventory_total - backlog_total
            inventory_with_pipeline = inventory_total + on_order_total - backlog_total

            node_snapshot = {
                "inventory": inventory_total,
                "backlog": backlog_total,
                "inventory_after": inventory_total,
                "backlog_after": backlog_total,
                "inventory_position": inventory_net,
                "inventory_position_with_pipeline": inventory_with_pipeline,
                "lost_sales": lost_sales_total,
                "holding_cost": holding_cost,
                "backlog_cost": backlog_cost,
                "total_cost": holding_cost + backlog_cost,
                "orders": order_total,
                "inventory_by_item": MixedScenarioService._json_clone(state.inventory_by_item),
                "backlog_by_item": MixedScenarioService._json_clone(state.backlog_by_item),
                "lost_sales_by_item": MixedScenarioService._json_clone(getattr(state, "lost_sales_by_item", {})),
                "inbound_demand": [o.dict() for o in inbound_snapshot_orders],
                "inbound_supply": [s.dict() for s in inbound_snapshot_supply],
                "type": node_types.get(node_key),
            }
            otif_total_units = getattr(state, "otif_total_units", 0)
            otif_details: Dict[str, Any] = {
                "total_orders": getattr(state, "otif_total_orders", 0),
                "total_units": otif_total_units,
                "on_time_in_full_units": getattr(state, "otif_on_time_in_full_units", 0),
                "late_units": getattr(state, "otif_late_units", 0),
                "late_orders": getattr(state, "otif_late_orders", 0),
                "lost_sale_cost": getattr(state, "otif_lost_sale_cost", 0.0),
            }
            if otif_total_units > 0:
                otif_details["percent_on_time"] = (
                    otif_details["on_time_in_full_units"] / otif_total_units
                )
            node_snapshot["otif"] = otif_details
            history_entry["node_states"][node_key] = node_snapshot
            history_entry["inventory_positions"][node_key] = inventory_net
            history_entry.setdefault("inventory_positions_with_pipeline", {})[node_key] = inventory_with_pipeline
            history_entry["backlogs"][node_key] = backlog_total
            history_entry["total_cost"] = float(history_entry.get("total_cost", 0.0)) + holding_cost + backlog_cost
            display_name_value = (
                node_display_names.get(node_key)
                or node_display_names.get(MixedScenarioService._normalise_key(node_key))
                or node_key.replace("_", " ").title()
            )
            comment_text = agent_comments.get(node_key)
            if order_total or comment_text:
                if order_total:
                    history_entry["orders"][node_key] = order_total
                order_payload: Dict[str, Any] = {
                    "quantity": order_total,
                    "type": node_types.get(node_key),
                    "display_name": display_name_value,
                    "node_name": display_name_value,
                }
                if comment_text:
                    order_payload["comment"] = comment_text
                history_entry["node_orders"][node_key] = order_payload

            node_type = node_types.get(node_key)
            if node_type:
                type_entry = history_entry.setdefault("node_type_summaries", {}).setdefault(
                    node_type, {"orders": 0, "inventory": 0, "backlog": 0, "holding_cost": 0.0, "backlog_cost": 0.0, "total_cost": 0.0}
                )
                type_entry["orders"] = type_entry.get("orders", 0) + order_total
                type_entry["inventory"] = type_entry.get("inventory", 0) + inventory_total
                type_entry["backlog"] = type_entry.get("backlog", 0) + backlog_total
                type_entry["holding_cost"] = type_entry.get("holding_cost", 0.0) + holding_cost
                type_entry["backlog_cost"] = type_entry.get("backlog_cost", 0.0) + backlog_cost
                type_entry["total_cost"] = type_entry.get("total_cost", 0.0) + holding_cost + backlog_cost

            # Compose debug block for file logging with step trace
            start_inv = getattr(state, "debug_start_inventory", inventory_total)
            post_demand_inv = getattr(state, "debug_post_demand_inventory", inventory_total)
            orders_count_map = {}
            try:
                raw_orders_count = getattr(state, "debug_matured_counts", None)
                if isinstance(raw_orders_count, dict):
                    orders_count_map = {str(k): int(v) for k, v in raw_orders_count.items()}
            except Exception:
                orders_count_map = {}
            supply_count_map = {}
            try:
                raw_supply_count = getattr(state, "debug_due_arrivals_counts", None) or getattr(state, "debug_post_supply_queue", None)
                if isinstance(raw_supply_count, dict):
                    supply_count_map = {str(k): int(v) for k, v in raw_supply_count.items()}
            except Exception:
                supply_count_map = {}
            # `orders_count_map` and `supply_count_map` already hold the totals we need for logging.
            total_supply_entries = _collect_supply_entries(state, node_snapshot)
            created_orders_details = getattr(state, "debug_created_orders", []) or []
            created_orders_count: Dict[str, int] = defaultdict(int)
            for detail in created_orders_details:
                item_key = MixedScenarioService._normalise_product_id(detail.get("product_id"))
                if not item_key:
                    continue
                qty = max(0, int(detail.get("quantity") or 0))
                created_orders_count[item_key] += qty
            created_orders_entries = _with_item_names(created_orders_details)
            step_trace: List[Dict[str, Any]] = [
                {
                    "step": "Start",
                    "inventory": start_inv,
                    "inventory_after": start_inv,
                    "inventory_by_item": _with_item_names_map(state.inventory_by_item),
                    "inbound_demand": _with_item_names_map(orders_count_map),
                    "inbound_supply": _with_item_names(total_supply_entries),
                    "inbound_supply_counts": _with_item_names_map(supply_count_map),
                },
                {
                    "step": "Process Demand",
                    "inbound_demand": _with_item_names_map(orders_count_map),
                    "inventory_after": post_demand_inv,
                },
                {
                    "step": "Process Supply",
                    "inbound_supply": _with_item_names_map(supply_count_map),
                    "inventory_after": inventory_total,
                },
            ]
            if node_master_type == "manufacturer":
                step_trace.append(
                    {
                        "step": "Manufacture",
                        "output": _with_item_names_map(getattr(state, "debug_manufacture_output", {}) or {}),
                        "component_inventory": _with_item_names_map(getattr(state, "component_inventory_by_item", {}) or {}),
                        "inventory_after": inventory_total,
                    }
                )
            step_trace.extend(
                [
                {
                    "step": "Create Order",
                    "orders_created": getattr(state, "debug_orders_created", None),
                    "orders_created_detail": _with_item_names_map(created_orders_count),
                    "orders_created_items": created_orders_entries,
                    "inventory_after": inventory_total,
                },
                {
                    "step": "End",
                    "inventory": inventory_total,
                    "backlog": backlog_total,
                    "inventory_by_item": _with_item_names_map(node_snapshot["inventory_by_item"]),
                    "inventory_after": inventory_total,
                },
                ],
            )
            debug_payload.append(
                {
                    "node": node_key,
                    "info_sent": {
                        "demand": _with_item_names_map(state.current_round_demand or {}),
                    },
                    "reply": {
                        "inbound_demand": _with_item_names(node_snapshot.get("inbound_demand", [])),
                        "inbound_supply": _with_item_names(node_snapshot["inbound_supply"]),
                    },
                    "step_trace": step_trace,
                "ending_state": {
                    "inventory_by_item": _with_item_names_map(node_snapshot.get("inventory_by_item") or {}),
                    "backlog_by_item": _with_item_names_map(node_snapshot.get("backlog_by_item") or {}),
                    "inventory": inventory_total,
                    "backlog": backlog_total,
                    "inventory_after": inventory_total,
                    "otif": node_snapshot.get("otif"),
                },
                }
            )

        # Summarise shipments generated this round (by source -> destination).
        shipments_summary: Dict[str, Dict[str, int]] = defaultdict(dict)
        try:
            shipments_iter = list(getattr(context, "inbound_supply", []) or [])
        except Exception:
            shipments_iter = []

        for shipment in shipments_iter:
            try:
                qty = int(getattr(shipment, "quantity", 0) or 0)
            except (TypeError, ValueError):
                qty = 0
            if qty <= 0:
                continue

            source = MixedScenarioService._normalise_key(
                getattr(shipment, "source", None) or getattr(shipment, "origin", None)
            )
            dest = MixedScenarioService._normalise_key(
                getattr(shipment, "destination", None) or getattr(shipment, "dest", None)
            )
            if not source or not dest:
                continue

            current_total = shipments_summary[source].get(dest, 0)
            shipments_summary[source][dest] = current_total + qty

        if shipments_summary:
            # Attach to the per-round history entry for Sankey diagrams and summaries.
            shipments_map = {src: dict(targets) for src, targets in shipments_summary.items()}
            history_entry["shipments"] = shipments_map

            sankey_history = cfg.get("sankey_history")
            if not isinstance(sankey_history, list):
                sankey_history = []
            else:
                sankey_history = [entry for entry in sankey_history if entry.get("round") != round_index]
            sankey_history.append(
                {
                    "round": round_index,
                    "shipments": MixedScenarioService._json_clone(shipments_map),
                    "demand": history_entry.get("demand"),
                    "period_start": history_entry.get("period_start"),
                    "period_end": history_entry.get("period_end"),
                }
            )
            sankey_history.sort(key=lambda item: item.get("round", 0))
            cfg["sankey_history"] = sankey_history

        # Persist history on config
        history_payload = cfg.get("history")
        if not isinstance(history_payload, list):
            history_payload = []
        else:
            history_payload = [entry for entry in history_payload if entry.get("round") != round_index]
        history_payload.append(history_entry)
        history_payload.sort(key=lambda item: item.get("round", 0))
        cfg["history"] = history_payload
        game.config = dict(cfg)
        flag_modified(game, "config")

        # Write round debug log to file if enabled
        debug_cfg = normalize_debug_config(cfg)
        cfg["debug_logging"] = debug_cfg
        if debug_cfg.get("enabled") and debug_payload:
            append_debug_round_log(
                cfg,
                game,
                round_number=round_index,
                timestamp=datetime.utcnow(),
                entries=debug_payload,
            )
            # If game finished, auto-split the log for convenience
            try:
                should_split = debug_cfg.get("split_logs")
                finished = getattr(game, "current_round", 0) >= getattr(game, "max_rounds", 0) or getattr(game, "status", None) == GameStatusDB.FINISHED
                if should_split and finished:
                    path = ensure_debug_log_file(cfg, game)
                    if path:
                        split_debug_log_file(path, cfg=cfg)
            except Exception:
                logger.debug("Auto-split of debug log failed for game %s", getattr(game, 'id', '?'))

    def _finalize_round(self, game: Game, context: RoundContext) -> None:
        # Persist state and finalize round
        if not game.config:
            game.config = {}
        cfg: Dict[str, Any] = dict(game.config)

        # 1. Update Engine State in Config
        engine_state = cfg.get('engine_state', {})

        items = cfg.get("items") or []
        item_name_by_id: Dict[str, str] = {}
        item_name_by_token: Dict[str, str] = {}
        for itm in items:
            itm_id = None
            itm_name = None
            if isinstance(itm, dict):
                itm_id = itm.get("id") or itm.get("product_id")
                itm_name = itm.get("name") or itm.get("description")
            else:
                itm_id = getattr(itm, "id", None)
                itm_name = getattr(itm, "name", None) or getattr(itm, "description", None)
            if itm_id is not None and itm_name:
                item_name_by_id[str(itm_id)] = str(itm_name)
            if itm_name:
                token = MixedScenarioService._canonical_role(itm_name)
                if token:
                    item_name_by_token.setdefault(token, str(itm_name))

        def _resolve_item_name(raw_id: Any) -> Optional[str]:
            if raw_id is None:
                return None
            if str(raw_id) in item_name_by_id:
                return item_name_by_id[str(raw_id)]
            token = MixedScenarioService._canonical_role(raw_id)
            if token and token in item_name_by_token:
                return item_name_by_token[token]
            return None

        def _with_item_names(queue: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            enriched: List[Dict[str, Any]] = []
            for entry in queue:
                if not isinstance(entry, dict):
                    continue
                clone = dict(entry)
                itm = clone.get("product_id")
                if itm is not None:
                    clone["item_name"] = _resolve_item_name(itm)
                enriched.append(clone)
            return enriched

        for node_key, state in context.node_states.items():
            # Convert NodeState back to dict and capture future queues before shipment distribution
            state_dict = state.dict()
            inbound_demand = [o.dict() for o in getattr(state, "inbound_demand", [])]
            inbound_supply = [
                s.dict()
                for s in getattr(state, "inbound_supply_future", getattr(state, "inbound_supply", []))
            ]
            state_dict["inbound_demand"] = inbound_demand
            state_dict["inbound_supply"] = inbound_supply

            # Remove transient fields
            state_dict.pop("matured_orders", None)
            # Drop unused legacy pipelines
            for key in (
                "orders_queue",
                "backlog_orders",
                "info_queue",
                "info_detail_queue",
                "ship_queue",
                "incoming_shipments",
            ):
                state_dict.pop(key, None)

            engine_state[node_key] = state_dict

        game.config["engine_state"] = engine_state

        # 2. Distribute new shipments (from context.inbound_supply) to destination nodes
        shipments_for_history: List[Shipment] = list(getattr(context, "inbound_supply", []) or [])
        for shipment in shipments_for_history:
            dest = shipment.destination
            if dest in context.node_states:
                future_queue = getattr(context.node_states[dest], "inbound_supply_future", None)
                if future_queue is None:
                    future_queue = []
                    context.node_states[dest].inbound_supply_future = future_queue
                exists = any(
                    getattr(existing, "product_id", None) == shipment.product_id
                    and getattr(existing, "quantity", None) == shipment.quantity
                    and getattr(existing, "source", None) == shipment.source
                    and getattr(existing, "destination", None) == shipment.destination
                    and getattr(existing, "arrival_round", None) == shipment.arrival_round
                    for existing in future_queue
                )
                if not exists:
                    future_queue.append(shipment)

        # Preserve the original shipment list for logging/reporting.
        context.inbound_supply = shipments_for_history
                
        # 3. Serialize NodeStates to engine_state after distribution
        for node_key, state in context.node_states.items():
            existing = engine_state.get(node_key)
            state_dict = existing if isinstance(existing, dict) else {}

            # Preserve previously captured inbound_demand (future orders) and refresh inbound_supply
            state_dict["inbound_supply"] = [
                s.dict()
                for s in getattr(state, "inbound_supply_future", getattr(state, "inbound_supply", []))
            ]

            for key in (
                'orders_queue',
                'backlog_orders',
                'matured_orders',
                'info_queue',
                'info_detail_queue',
                'ship_queue',
                'incoming_shipments',
            ):
                state_dict.pop(key, None)
            engine_state[node_key] = state_dict
            
        game.config['engine_state'] = engine_state

        # 4. Mark round completion metadata
        timestamp = datetime.utcnow()
        round_record = context.round_record
        if round_record:
            round_record.is_completed = True
            round_record.completed_at = round_record.completed_at or timestamp
            round_record.ended_at = round_record.ended_at or timestamp
            self.db.add(round_record)

        # 5. Record history and per-round debug log
        self._record_round_history(game, context)
        
        # 6. Update game status when finished
        total_rounds = game.max_rounds or 50
        if (round_record and round_record.round_number >= total_rounds) or (game.current_round or 0) >= total_rounds:
            game.status = GameStatusDB.FINISHED
            game.current_round = total_rounds
        else:
            game.status = GameStatusDB.STARTED
        # Ensure SQLAlchemy notices JSON mutations
        game.config = dict(game.config or {})
        flag_modified(game, "config")

        # 7. Commit changes so the round, config, and history persist
        self.db.add(game)
        self.db.commit()

    def _initialize_round(self, game: Game, *, round_number: Optional[int] = None) -> Optional[RoundContext]:
        """Initialize the round context, loading configuration and state."""
        if not game or not game.config:
            return None

        cfg = game.config
        round_number = round_number if round_number is not None else (game.current_round or 0) + 1

        # Rotate debug log per game run so each start creates a fresh file
        debug_cfg = normalize_debug_config(cfg)
        if debug_cfg.get("enabled") and round_number == 1:
            debug_cfg.pop("file_path", None)
            cfg["debug_logging"] = debug_cfg
            ensure_debug_log_file(cfg, game)
        
        # 1. Build Topology
        node_policies = cfg.get("node_policies", {})
        lane_views = self._build_lane_views(node_policies, cfg)
        node_master_types_map = lane_views.get("node_master_types", {})
        node_sequence = lane_views.get("node_sequence") or cfg.get("node_sequence") or []
        if not node_sequence:
            raise ValueError(
                "Supply chain configuration is missing a node sequence (DAG). "
                "Ensure nodes, node types, lanes, and node_sequence are persisted before starting rounds."
            )
        cfg["node_sequence"] = node_sequence
        
        # Convert lane_views to TopologyConfig
        # Note: We need to handle the dictionary keys for lane_lookup carefully as Pydantic expects strings
        # We'll skip lane_lookup in the Pydantic model for now or handle it separately if needed
        # For now, we construct the TopologyConfig from the dict
        
        # Helper to convert lane dicts to LaneConfig objects
        def _normalise_lane_payload(lane_payload: Dict[str, Any]) -> Dict[str, Any]:
            payload = dict(lane_payload)
            for key in ("lead_time_days", "demand_lead_time", "supply_lead_time"):
                if key in payload:
                    coerced = MixedScenarioService._coerce_leadtime_value(payload[key])
                    if coerced is not None:
                        payload[key] = coerced
                    elif key in {"demand_lead_time", "supply_lead_time"}:
                        payload.pop(key, None)
            return payload

        lanes = [LaneConfig(**_normalise_lane_payload(l)) for l in lane_views.get("lanes", [])]
        lanes_by_upstream = {
            k: [LaneConfig(**_normalise_lane_payload(l)) for l in v]
            for k, v in lane_views.get("lanes_by_upstream", {}).items()
        }
        lane_lookup_payload = lane_views.get("lane_lookup", {})
        lane_lookup: Dict[Any, LaneConfig] = {}
        for key, lane_data in lane_lookup_payload.items():
            try:
                upstream, downstream = key
            except Exception:
                upstream = lane_data.get("from") or lane_data.get("upstream")
                downstream = lane_data.get("to") or lane_data.get("downstream")
            lane_payload = dict(lane_data or {})
            lane_payload.setdefault("from", upstream)
            lane_payload.setdefault("to", downstream)
            lane_lookup[(MixedScenarioService._normalise_key(upstream), MixedScenarioService._normalise_key(downstream))] = LaneConfig(
                **_normalise_lane_payload(lane_payload)
            )
        
        topology = TopologyConfig(
            lanes=lanes,
            shipments_map=lane_views.get("shipments_map", {}),
            orders_map=lane_views.get("orders_map", {}),
            market_nodes=lane_views.get("market_nodes", []),
            all_nodes=lane_views.get("all_nodes", []),
            node_sequence=node_sequence,
            lanes_by_upstream=lanes_by_upstream,
            node_types=lane_views.get("node_types", {}),
            lane_lookup=lane_lookup
        )

        # 2. Load Engine State
        engine_state = cfg.get("engine_state", {})
        node_states: Dict[str, NodeState] = {}

        primary_item_id: Optional[str] = None
        for entry in cfg.get("items") or []:
            candidate = entry.get("id") if isinstance(entry, dict) else getattr(entry, "id", None)
            token = MixedScenarioService._normalise_product_id(candidate)
            if token:
                primary_item_id = token
                break
        
        for node in topology.all_nodes:
            upstream_sources = [u for u, downs in topology.shipments_map.items() if node in downs]
            default_upstream = upstream_sources[0] if upstream_sources else "__upstream__"

            self._ensure_engine_node(
                engine_state,
                node_policies,
                node,
                default_item_id=primary_item_id,
                default_source=default_upstream,
            )
            raw_state = engine_state.get(node, {})
            
            # Convert raw state to NodeState
            # We need to be careful about list/dict types
            inbound_orders_raw = raw_state.get("inbound_demand")
            if inbound_orders_raw is None:
                inbound_orders_raw = raw_state.get("inbound_orders")
                if inbound_orders_raw is not None:
                    raw_state["inbound_demand"] = inbound_orders_raw
                    raw_state.pop("inbound_orders", None)
            if inbound_orders_raw is None:
                inbound_orders_raw = []
                raw_state["inbound_demand"] = inbound_orders_raw
            if not isinstance(inbound_orders_raw, list):
                raise ValueError(
                    f"Node '{node}' inbound_demand must be a list"
                )

            combined_orders = list(inbound_orders_raw)
            normalised_orders = self._normalise_order_queue(
                combined_orders,
                current_step=round_number,
                default_lead_time=0,
                default_item_id=primary_item_id,
            )
            node_type = topology.node_types.get(node)
            master_type = node_master_types_map.get(node) or MixedScenarioService._master_node_type(node_type)
            if (
                not normalised_orders
                and master_type not in {"market_supply", "market_demand"}
                and round_number == 1
            ):
                raise ValueError(f"Engine state missing inbound_demand for node '{node}' at round {round_number}")
            inbound_supply_raw = raw_state.get("inbound_supply")
            if inbound_supply_raw is None:
                inbound_supply_raw = []
                raw_state["inbound_supply"] = inbound_supply_raw
            if not isinstance(inbound_supply_raw, list):
                raise ValueError(
                    f"Node '{node}' inbound_supply must be a list"
                )

            combined_shipments = list(inbound_supply_raw)
            normalised_shipments = self._normalise_shipment_queue(
                combined_shipments,
                current_round=round_number,
                destination=node,
            )
            if (
                not normalised_shipments
                and master_type not in {"market_supply", "market_demand", "manufacturer"}
                and round_number == 1
            ):
                raise ValueError(
                    f"Engine state missing inbound_supply for node '{node}' "
                    f"(master_type={master_type}) at round {round_number}. "
                    f"Raw entries: {len(inbound_supply_raw)}, "
                    f"After normalization: {len(normalised_shipments)}"
                )
            
            # Note: _normalise_order_queue returns dicts, we need to convert to OrderRequest if we want strict typing
            # But wait, OrderRequest expects specific fields. _normalise_order_queue output matches mostly.
            # Let's trust Pydantic to coerce or we might need to adjust.
            
            # Actually, let's keep it simple for now and populate basic fields.
            # The complex queues might be better left as dicts in NodeState if they are too dynamic, 
            # but we defined them as lists of models.
            
            # Let's try to populate what we can.
            node_state = NodeState(
                inventory_by_item=raw_state.get("inventory_by_item", {}),
                backlog_by_item=raw_state.get("backlog_by_item", {}),
                base_stock_by_item=raw_state.get("base_stock_by_item", {}),
                on_order_by_item=raw_state.get("on_order_by_item", {}),
                backlog_orders=[],
                inbound_demand=[OrderRequest(**o) for o in normalised_orders],
                inbound_supply_future=[Shipment(**s) for s in normalised_shipments],
            )
            node_states[node] = node_state

        item_priority_map: Dict[str, Optional[int]] = {}
        for entry in cfg.get("items") or []:
            if not isinstance(entry, Mapping):
                continue
            item_token = MixedScenarioService._normalise_product_id(entry.get("id") or entry.get("name"))
            if not item_token:
                continue
            priority_val = entry.get("priority")
            try:
                item_priority_map[item_token] = int(priority_val) if priority_val is not None else None
            except (TypeError, ValueError):
                item_priority_map[item_token] = None

        node_priority_map: Dict[str, Optional[int]] = {}
        for name, policy in node_policies.items():
            if not isinstance(policy, Mapping):
                continue
            key = MixedScenarioService._normalise_key(name)
            if not key:
                continue
            priority_val = policy.get("priority")
            try:
                node_priority_map[key] = int(priority_val) if priority_val is not None else None
            except (TypeError, ValueError):
                node_priority_map[key] = None

        # 3. Calculate Market Demand (Initial)
        # This is needed to populate market_demand_map and create the round record with demand info
        demand_map, demand_value = self._compute_market_round_demand(
            game,
            cfg,
            round_number,
            lane_views
        )
        
        # 4. Create or reuse ScenarioRound record
        # We need to calculate period start/end
        bucket = normalize_time_bucket(getattr(game, "time_bucket", TimeBucket.WEEK))
        start_date = getattr(game, "start_date", None)
        if isinstance(start_date, str):
            try:
                start_date = date.fromisoformat(start_date)
            except ValueError:
                start_date = None
        if start_date is None:
            start_date = DEFAULT_START_DATE
            game.start_date = start_date
            
        period_start = compute_period_start(start_date, round_number - 1, bucket)
        period_end = compute_period_end(period_start, bucket)
        game.current_period_start = period_start
        
        round_record = (
            self.db.query(ScenarioRound)
            .filter(ScenarioRound.scenario_id == game.id, ScenarioRound.round_number == round_number)
            .first()
        )
        if not round_record:
            round_record = ScenarioRound(
                scenario_id=game.id,
                round_number=round_number,
                customer_demand=demand_value,
                started_at=datetime.utcnow(),
                period_start=period_start,
                period_end=period_end,
            )
            self.db.add(round_record)
            self.db.flush()
        else:
            # Ensure timing/demand fields are populated when reusing an existing record
            if not round_record.started_at:
                round_record.started_at = datetime.utcnow()
            round_record.customer_demand = demand_value
            if not round_record.period_start:
                round_record.period_start = period_start
            if not round_record.period_end:
                round_record.period_end = period_end

        context = RoundContext(
            round_number=round_number,
            scenario_id=game.id,
            topology=topology,
            config=cfg,
            node_states=node_states,
            inbound_supply=[], # To be populated
            node_policies=node_policies,
            market_demand_map=demand_map,
            round_record=round_record,
            item_priorities=item_priority_map,
            node_priorities=node_priority_map,
        )
        
        return context

    @staticmethod
    def _normalise_order_queue(
        queue: Any,
        *,
        current_step: int,
        default_lead_time: int,
        default_item_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not isinstance(queue, list):
            return []

        normalised: List[Dict[str, Any]] = []
        try:
            base_step = int(current_step)
        except (TypeError, ValueError):
            base_step = 0
        try:
            lead = max(0, int(default_lead_time or 0))
        except (TypeError, ValueError):
            lead = 0
        fallback_step = base_step + lead

        for entry in queue:
            if not isinstance(entry, dict):
                continue

            step_raw = entry.get("step_number")
            if step_raw is None:
                step_raw = (
                    entry.get("due_round")
                    or entry.get("order_date")
                    or entry.get("round")
                    or entry.get("due")
                )
            try:
                step_number = int(step_raw)
            except (TypeError, ValueError):
                step_number = fallback_step
                fallback_step += 1
            due_round = step_number

            qty_raw = entry.get("quantity")
            if qty_raw is None:
                qty_raw = entry.get("qty")
            try:
                quantity = int(qty_raw)
            except (TypeError, ValueError):
                quantity = 0
            if quantity <= 0:
                continue

            priority_raw = entry.get("order_priority") or entry.get("priority")
            try:
                order_priority = int(priority_raw)
            except (TypeError, ValueError):
                order_priority = 1
            if order_priority <= 0:
                order_priority = 1

            breakdown_raw = entry.get("breakdown") or entry.get("detail") or {}
            breakdown: Dict[str, int] = {}
            if isinstance(breakdown_raw, dict):
                for key, value in breakdown_raw.items():
                    try:
                        qty_val = int(value)
                    except (TypeError, ValueError):
                        continue
                    if qty_val <= 0:
                        continue
                    breakdown[str(key)] = breakdown.get(str(key), 0) + qty_val

            if breakdown and sum(breakdown.values()) != quantity:
                quantity = sum(breakdown.values())

            source = entry.get("source") or entry.get("order_source")
            if source is None:
                raise ValueError(f"Order queue entry missing source: {entry}")
            source = str(source)

            downstream = entry.get("downstream")
            if downstream is None:
                downstream = source
            else:
                downstream = str(downstream)

            product_id = entry.get("product_id") or entry.get("sku") or entry.get("item") or default_item_id
            item_token = MixedScenarioService._normalise_product_id(product_id)
            if not item_token or item_token == "default":
                fallback_token = MixedScenarioService._normalise_product_id(default_item_id or "")
                if fallback_token:
                    item_token = fallback_token
                else:
                    raise ValueError(f"Order queue entry has invalid product_id: {entry}")

            normalised.append(
                {
                    "step_number": step_number,
                    "due_round": due_round,
                    "quantity": quantity,
                    "order_priority": order_priority,
                    "breakdown": breakdown,
                    "downstream": downstream,
                    "source": source,
                    "product_id": item_token,
                }
            )

        normalised.sort(
            key=lambda item: (
                item.get("step_number", current_step),
                item.get("order_priority", 1),
            )
        )
        return normalised

    @staticmethod
    def _order_pipeline_snapshot(queue: List[Dict[str, Any]], current_round: int) -> List[int]:
        future_entries: List[Dict[str, Any]] = []
        for entry in queue:
            try:
                step_number = int(entry.get("step_number", current_round))
                quantity = int(entry.get("quantity", 0))
            except (TypeError, ValueError):
                continue
            if quantity <= 0:
                continue
            if step_number > current_round:
                future_entries.append({"step_number": step_number, "quantity": quantity})

        if not future_entries:
            return []

        max_offset = max(entry["step_number"] - current_round for entry in future_entries)
        if max_offset <= 0:
            return []

        buckets = [0] * max_offset
        for entry in future_entries:
            offset = entry["step_number"] - current_round
            if offset <= 0:
                continue
            idx = offset - 1
            if idx >= len(buckets):
                buckets.extend([0] * (idx + 1 - len(buckets)))
            buckets[idx] += entry.get("quantity", 0)
        return buckets

    @staticmethod
    def _order_detail_pipeline_snapshot(
        queue: List[Dict[str, Any]], current_round: int
    ) -> List[Dict[str, Dict[str, int]]]:
        future_entries: List[Dict[str, Any]] = []
        for entry in queue:
            try:
                step_number = int(entry.get("step_number", current_round))
            except (TypeError, ValueError):
                continue
            if step_number <= current_round:
                continue
            try:
                quantity = int(entry.get("quantity", 0))
            except (TypeError, ValueError):
                quantity = 0
            if quantity <= 0:
                continue
            future_entries.append(entry)

        if not future_entries:
            return []

        max_offset = max(int(entry.get("step_number", current_round)) - current_round for entry in future_entries)
        if max_offset <= 0:
            return []

        buckets: List[Dict[str, Dict[str, int]]] = [
            {} for _ in range(max_offset)
        ]
        for entry in future_entries:
            try:
                step_number = int(entry.get("step_number", current_round))
            except (TypeError, ValueError):
                continue
            offset = step_number - current_round
            if offset <= 0:
                continue
            idx = offset - 1
            breakdown = entry.get("breakdown") or {}
            bucket = buckets[idx]
            if isinstance(breakdown, dict) and breakdown:
                for key, value in breakdown.items():
                    downstream_key = str(key)
                    item_map = bucket.setdefault(downstream_key, {})
                    if isinstance(value, dict):
                        for product_id, raw_qty in value.items():
                            try:
                                qty_val = int(raw_qty)
                            except (TypeError, ValueError):
                                continue
                            if qty_val <= 0:
                                continue
                        item_token = MixedScenarioService._normalise_product_id(product_id)
                        if not item_token:
                            continue
                        item_map[item_token] = item_map.get(item_token, 0) + qty_val
                    else:
                        try:
                            qty_val = int(value)
                        except (TypeError, ValueError):
                            continue
                        if qty_val <= 0:
                            continue
                        item_token = MixedScenarioService._normalise_product_id(entry.get("product_id"))
                        if not item_token:
                            continue
                        item_map[item_token] = item_map.get(item_token, 0) + qty_val
            else:
                downstream = entry.get("downstream")
                if downstream:
                    qty_val = int(entry.get("quantity", 0) or 0)
                    if qty_val <= 0:
                        continue
                    downstream_key = str(downstream)
                    item_map = bucket.setdefault(downstream_key, {})
                    item_token = MixedScenarioService._normalise_product_id(entry.get("product_id"))
                    item_map[item_token] = item_map.get(item_token, 0) + qty_val
        return [
            {downstream: dict(items) for downstream, items in bucket.items()}
            for bucket in buckets
        ]

    @staticmethod
    def _normalise_pipeline_length(values: List[Any], length: int) -> List[int]:
        """Pad or trim pipeline snapshots so they align with configured lead times."""

        if length <= 0:
            return []

        cleaned: List[int] = []
        for value in values or []:
            try:
                qty_val = max(0, int(value))
            except (TypeError, ValueError):
                continue
            cleaned.append(qty_val)
            if len(cleaned) == length:
                break

        if len(cleaned) < length:
            cleaned.extend([0] * (length - len(cleaned)))

        if not cleaned:
            return [0] * length

        return cleaned[:length]

    @staticmethod
    def _append_order_to_queue(
        queue: List[Dict[str, Any]],
        *,
        step_number: int,
        downstream: str,
        quantity: int,
        source: Optional[str] = None,
        product_id: Optional[str] = None,
        order_priority: Optional[int] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        qty = int(quantity)
        if qty <= 0:
            return queue

        downstream_key = str(downstream)
        if order_priority is None:
            order_priority = 1
        try:
            order_priority = int(order_priority)
        except (TypeError, ValueError):
            order_priority = 1
        if order_priority <= 0:
            order_priority = 1

        sequence = None
        if state is not None:
            sequence = int(state.get("order_sequence") or 0) + 1
            state["order_sequence"] = sequence

        item_token = MixedScenarioService._normalise_product_id(product_id)
        breakdown_payload = {downstream_key: {item_token: qty}}

        entry: Dict[str, Any] = {
            "step_number": int(step_number),
            "quantity": qty,
            "order_priority": order_priority,
            "breakdown": breakdown_payload,
            "downstream": downstream_key,
        }

        if source is not None:
            entry["source"] = str(source)
        if product_id is not None:
            entry["product_id"] = str(product_id)
        if sequence is not None:
            entry["sequence"] = sequence

        queue.append(entry)
        queue.sort(
            key=lambda item: (
                item.get("step_number", 0),
                item.get("order_priority", 1),
            )
        )
        return queue

    @staticmethod
    def _normalise_shipment_queue(
        queue: Any,
        *,
        current_round: int,
        destination: str,
    ) -> List[Dict[str, Any]]:
        """Coerce arbitrary shipment payloads into the required Shipment fields."""

        if not isinstance(queue, list):
            return []

        shipments: List[Dict[str, Any]] = []
        for entry in queue:
            if not isinstance(entry, dict):
                continue

            qty_raw = entry.get("quantity") or entry.get("qty")
            try:
                quantity = int(qty_raw)
            except (TypeError, ValueError):
                continue
            if quantity <= 0:
                continue

            arrival_raw = (
                entry.get("arrival_round")
                or entry.get("step_number")
                or entry.get("due_round")
                or entry.get("step")
            )
            try:
                arrival_round = int(arrival_raw)
            except (TypeError, ValueError):
                arrival_round = current_round

            source = entry.get("source") or entry.get("from") or entry.get("upstream")
            if source is None:
                raise ValueError(
                    "Shipment queue entry must include a source upstream node"
                )
            destination_token = entry.get("destination") or entry.get("to") or destination
            item_token = MixedScenarioService._normalise_product_id(
                entry.get("product_id") or entry.get("item_id") or entry.get("item") or entry.get("sku")
            )
            if not item_token:
                raise ValueError(
                    f"Shipment queue entry missing product_id: {entry.keys()}"
                )

            destination_token = entry.get("destination") or entry.get("to") or destination
            if destination_token is None:
                raise ValueError("Shipment queue entry missing destination")

            payload: Dict[str, Any] = {
                "product_id": item_token,
                "quantity": quantity,
                "source": str(source),
                "destination": str(destination_token),
                "arrival_round": arrival_round,
            }
            if entry.get("shipment_id") is not None:
                payload["shipment_id"] = entry.get("shipment_id")
            shipments.append(payload)

        return shipments

    @staticmethod
    def _compact_order_queue(queue: List[Dict[str, Any]], max_len: int) -> List[Dict[str, Any]]:
        """Merge same-due orders and cap queue length."""

        if not isinstance(queue, list) or max_len <= 0:
            return []

        merged: Dict[int, Dict[str, Any]] = {}
        for entry in queue:
            try:
                due = int(entry.get("step_number") or entry.get("due_round") or 0)
            except (TypeError, ValueError):
                continue
            qty = entry.get("quantity")
            try:
                qty_int = int(qty)
            except (TypeError, ValueError):
                qty_int = 0
            if qty_int <= 0:
                continue
            product_id = MixedScenarioService._normalise_product_id(entry.get("product_id") or entry.get("item"))
            if not product_id:
                continue
            key = due
            bucket = merged.setdefault(
                key,
                {
                    "step_number": due,
                    "due_round": due,
                    "quantity": 0,
                    "order_priority": int(entry.get("order_priority") or 1),
                    "downstream": entry.get("downstream"),
                    "source": entry.get("source"),
                    "breakdown": {},  # drop nested structures to avoid validation issues
                    "product_id": product_id,
                },
            )
            bucket["quantity"] += qty_int

        compacted = sorted(merged.values(), key=lambda x: x.get("due_round", 0))
        return compacted[:max_len]

    @staticmethod
    def _compact_shipment_queue(queue: List[Dict[str, Any]], max_len: int) -> List[Dict[str, Any]]:
        """Merge same-arrival shipments and cap queue length."""

        if not isinstance(queue, list) or max_len <= 0:
            return []

        merged: Dict[int, Dict[str, Any]] = {}
        for entry in queue:
            try:
                arr = int(entry.get("arrival_round") or entry.get("step_number") or 0)
            except (TypeError, ValueError):
                continue
            qty = entry.get("quantity")
            try:
                qty_int = int(qty)
            except (TypeError, ValueError):
                qty_int = 0
            if qty_int <= 0:
                continue
            product_id = MixedScenarioService._normalise_product_id(entry.get("product_id") or entry.get("item"))
            if not product_id:
                continue
            key = arr
            bucket = merged.setdefault(
                key,
                {
                    "arrival_round": arr,
                    "step_number": arr,
                    "quantity": 0,
                    "destination": entry.get("destination") or "__self__",
                    "source": entry.get("source") or "__upstream__",
                    "product_id": product_id,
                    "shipment_id": entry.get("shipment_id"),
                },
            )
            bucket["quantity"] += qty_int

        compacted = sorted(merged.values(), key=lambda x: x.get("arrival_round", 0))
        return compacted[:max_len]

    @staticmethod
    def _collapse_item_map(raw: Dict[str, int]) -> Dict[str, int]:
        """Merge multiple item keys into a single normalized item key."""
        collapsed: Dict[str, int] = {}
        if not isinstance(raw, dict):
            return {}
        for key, value in raw.items():
            try:
                qty = int(value)
            except (TypeError, ValueError):
                continue
            if qty <= 0:
                continue
            norm = MixedScenarioService._normalise_product_id(key)
            collapsed[norm] = collapsed.get(norm, 0) + qty
        return collapsed

    @staticmethod
    def _merge_orders(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge orders by due_round and product_id to avoid duplicate entries."""
        merged: Dict[Tuple[int, str, Optional[str], Optional[str]], Dict[str, Any]] = {}
        for entry in orders or []:
            if not isinstance(entry, dict):
                continue
            product_id = MixedScenarioService._normalise_product_id(entry.get("product_id") or entry.get("item"))
            try:
                due = int(entry.get("step_number") or entry.get("due_round") or 0)
            except (TypeError, ValueError):
                due = 0
            downstream = entry.get("downstream")
            source = entry.get("source")
            try:
                qty = int(entry.get("quantity") or 0)
            except (TypeError, ValueError):
                qty = 0
            if qty <= 0:
                continue
            key = (due, product_id, downstream, source)
            bucket = merged.setdefault(
                key,
                {
                    "product_id": product_id,
                    "quantity": 0,
                    "downstream": downstream,
                    "due_round": due,
                    "order_priority": entry.get("order_priority") or 1,
                    "source": source,
                    "sequence": entry.get("sequence"),
                    "breakdown": {},  # collapse any nested structures
                    "step_number": due,
                },
            )
            bucket["quantity"] += qty
        return sorted(merged.values(), key=lambda x: x.get("due_round", 0))

    @staticmethod
    def _merge_shipments(shipments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge shipments by arrival_round and product_id."""
        merged: Dict[Tuple[int, str, Optional[str], Optional[str]], Dict[str, Any]] = {}
        for entry in shipments or []:
            if not isinstance(entry, dict):
                continue
            product_id = MixedScenarioService._normalise_product_id(entry.get("product_id") or entry.get("item"))
            try:
                arr = int(entry.get("arrival_round") or entry.get("step_number") or 0)
            except (TypeError, ValueError):
                arr = 0
            dest = entry.get("destination") or "__self__"
            source = entry.get("source") or "__upstream__"
            try:
                qty = int(entry.get("quantity") or 0)
            except (TypeError, ValueError):
                qty = 0
            if qty <= 0:
                continue
            key = (arr, product_id, dest, source)
            bucket = merged.setdefault(
                key,
                {
                    "arrival_round": arr,
                    "step_number": arr,
                    "quantity": 0,
                    "destination": dest,
                    "source": source,
                    "product_id": product_id,
                    "shipment_id": entry.get("shipment_id"),
                },
            )
            bucket["quantity"] += qty
        return sorted(merged.values(), key=lambda x: x.get("arrival_round", 0))

    @staticmethod
    def _resolve_lane_order_delay(
        lane_lookup: Dict[Tuple[str, str], Dict[str, Any]],
        upstream: str,
        downstream: str,
        default_delay: int,
    ) -> int:
        record = lane_lookup.get((upstream, downstream))
        if record:
            value: Any = None
            if isinstance(record, Mapping):
                value = record.get("demand_lead_time")
                if value is None:
                    value = record.get("order_leadtime")
                if value is None:
                    value = record.get("order_lead_time")
            else:
                value = getattr(record, "demand_lead_time", None)
                if value is None:
                    value = getattr(record, "order_leadtime", None)
                if value is None:
                    value = getattr(record, "order_lead_time", None)
            if value is not None:
                coerced = MixedScenarioService._coerce_leadtime_value(value)
                if coerced is not None:
                    return coerced
        return max(0, int(default_delay))

    @staticmethod
    def _resolve_lane_ship_delay(
        lane_lookup: Dict[Tuple[str, str], Dict[str, Any]],
        upstream: str,
        downstream: str,
        default_delay: int,
    ) -> int:
        record = lane_lookup.get((upstream, downstream))
        if record:
            candidate: Any = None
            if isinstance(record, Mapping):
                candidate = record.get("lead_time_days")
            else:
                candidate = getattr(record, "lead_time_days", None)
            if candidate is not None:
                coerced = MixedScenarioService._coerce_leadtime_value(candidate)
                if coerced is not None:
                    return coerced
            value: Any = None
            if isinstance(record, Mapping):
                value = record.get("supply_lead_time")
                if value is None:
                    value = record.get("supply_leadtime")
            else:
                value = getattr(record, "supply_lead_time", None)
                if value is None:
                    value = getattr(record, "supply_leadtime", None)
            if value is not None:
                coerced = MixedScenarioService._coerce_leadtime_value(value)
                if coerced is not None:
                    return coerced
        return max(0, int(default_delay))

    @staticmethod
    def _coerce_legacy_supply_entries(
        queue: Any,
        *,
        current_step: int,
        default_item_id: Optional[str],
        default_source: Optional[str],
    ) -> Any:
        """
        Legacy coercion is no longer supported. If inbound_supply is not a list of
        dict entries, treat it as a fatal validation error so the game does not
        proceed with ambiguous state.
        """
        if not isinstance(queue, list) or not all(isinstance(entry, dict) for entry in queue):
            logger.error(
                "Encountered legacy inbound_supply format (non-dict entries) at step %s; stopping.",
                current_step,
            )
            raise ValueError(
                "Legacy inbound_supply detected; expected list of dict entries with step_number, quantity, product_id, source"
            )
        return queue

    @staticmethod
    def _ensure_engine_node(
        engine: Dict[str, Dict[str, Any]],
        node_policies: Dict[str, Any],
        node: str,
        default_item_id: Optional[str] = None,
        *,
        default_source: Optional[str] = None,
    ) -> Dict[str, Any]:
        policy = MixedScenarioService._policy_for_node(node_policies, node)
        order_leadtime = max(0, int(policy.get("order_leadtime", 0)))
        supply_leadtime = max(0, int(policy.get("supply_leadtime", 0)))
        state = engine.setdefault(node, {})
        state.setdefault("inventory", int(policy.get("init_inventory", 12)))
        state.setdefault("backlog", 0)
        state.setdefault("on_order", 0)
        current_step = int(state.get("current_step", 0))
        state["current_step"] = current_step
        # Reject legacy queue keys entirely to avoid stale data.
        for legacy_key in (
            "orders_queue",
            "backlog_orders",
            "order_queue",
            "ship_queue",
            "incoming_shipments",
            "incoming_supply",
            "info_queue",
            "info_detail_queue",
            "incoming_orders",
        ):
            if state.get(legacy_key):
                raise ValueError(
                    f"Node '{node}' contains legacy queue '{legacy_key}'. Only inbound_demand and inbound_supply are supported."
                )
            state.pop(legacy_key, None)

        def _ensure_item_breakdown(
            *,
            target_key: str,
            aggregate_key: str,
            default_item: Optional[str],
            value_name: str,
        ) -> Dict[str, int]:
            mapping_raw = state.get(target_key)
            if isinstance(mapping_raw, dict) and mapping_raw:
                normalised: Dict[str, int] = {}
                for raw_key, raw_value in mapping_raw.items():
                    token = MixedScenarioService._normalise_product_id(raw_key)
                    if not token:
                        raise ValueError(
                            f"Node '{node}' has an undefined item id in {target_key}: {raw_key}"
                        )
                    normalised[token] = max(0, int(raw_value or 0))
                return normalised

            aggregate_raw = state.get(aggregate_key, 0)
            try:
                aggregate_value = max(0, int(aggregate_raw or 0))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Node '{node}' has non-numeric {aggregate_key} ({aggregate_raw});"
                    f" unable to derive {target_key}"
                ) from exc

            token = MixedScenarioService._normalise_product_id(default_item or "")
            if not token:
                raise ValueError(
                    f"Node '{node}' is missing an item id to map {value_name};"
                    " provide default_item_id or per-item breakdown"
                )

            return {token: aggregate_value}

        # Normalise demand queue; prefer inbound_demand but allow legacy inbound_orders for backward compatibility.
        if "inbound_demand" not in state and "inbound_orders" in state:
            state["inbound_demand"] = state.pop("inbound_orders")
        if "inbound_demand" not in state:
            raise ValueError(f"Node '{node}' is missing required inbound_demand queue")
        orders_raw = state.get("inbound_demand")
        if not isinstance(orders_raw, list):
            raise ValueError(f"Inbound demand for node '{node}' must be a list")
        try:
            orders_normalised = MixedScenarioService._normalise_order_queue(
                orders_raw,
                current_step=current_step,
                default_lead_time=order_leadtime,
                default_item_id=default_item_id,
            )
        except ValueError as exc:
            raise ValueError(
                f"Invalid inbound_demand for node '{node}': {exc}"
            ) from exc
        state["inbound_demand"] = [dict(o) for o in orders_normalised]

        if "inbound_supply" not in state or not isinstance(state.get("inbound_supply"), list):
            state["inbound_supply"] = []
        supply_raw = state.get("inbound_supply")
        try:
            supply_normalised = MixedScenarioService._coerce_legacy_supply_entries(
                supply_raw,
                current_step=current_step,
                default_item_id=default_item_id,
                default_source=default_source,
            )
            supply_schedule = normalize_inbound_supply_queue(
                supply_normalised,
                current_step=current_step,
                fallback=None,
                supply_leadtime=supply_leadtime,
            )
        except ValueError as exc:
            raise ValueError(
                f"Invalid inbound_supply for node '{node}': {exc}"
            ) from exc

        sort_inbound_supply_queue(supply_schedule)
        state["inbound_supply_future"] = supply_schedule
        state["inbound_supply"] = [dict(a) for a in supply_schedule]

        state["demand_lead_time"] = order_leadtime
        state["shipment_lead_time"] = supply_leadtime

        order_pipeline = MixedScenarioService._order_pipeline_snapshot(
            state.get("inbound_demand", []),
            current_round=current_step,
        )
        state["order_pipe"] = MixedScenarioService._normalise_pipeline_length(
            order_pipeline,
            order_leadtime,
        )

        supply_pipeline = summarise_inbound_supply_queue(
            state.get("inbound_supply", []),
            current_step=current_step,
            supply_leadtime=supply_leadtime,
        )
        state["pipeline_shipments"] = MixedScenarioService._normalise_pipeline_length(
            supply_pipeline,
            supply_leadtime,
        )
        state.setdefault("immediate_order_buffer", 0)
        if state["order_pipe"]:
            state["last_incoming_order"] = int(state["order_pipe"][0])
        else:
            state.setdefault("last_incoming_order", 0)

        state["inventory_by_item"] = _ensure_item_breakdown(
            target_key="inventory_by_item",
            aggregate_key="inventory",
            default_item=default_item_id,
            value_name="inventory",
        )
        state["backlog_by_item"] = _ensure_item_breakdown(
            target_key="backlog_by_item",
            aggregate_key="backlog",
            default_item=default_item_id,
            value_name="backlog",
        )

        # Drop legacy fields so they are not persisted in engine_state.
        for key in (
            "ship_queue",
            "ship_detail_queue",
            "incoming_shipments",
            "info_queue",
            "info_detail_queue",
            "incoming_orders",
            "order_queue",
            "backlog_orders",
        ):
            state.pop(key, None)
        state.setdefault("last_order", 0)
        state.setdefault("holding_cost", 0.0)
        state.setdefault("backorder_cost", 0.0)
        state.setdefault("total_cost", 0.0)
        state.setdefault("last_shipment_planned", 0)
        state.setdefault("last_arrival", 0)
        state.setdefault("backlog_breakdown", {})
        return state

    @staticmethod
    def _baseline_flow(mean_demand: float) -> int:
        try:
            quantity = int(round(float(mean_demand)))
        except (TypeError, ValueError):
            quantity = DEFAULT_STEADY_STATE_DEMAND
        if quantity <= 0 and (isinstance(mean_demand, (int, float)) and mean_demand > 0):
            return 1
        return max(0, quantity)

    @staticmethod
    def _compute_initial_conditions(
        mean_demand: float,
        variance: float,
        *,
        order_leadtime: int,
        supply_leadtime: int,
        debug_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, int]:
        baseline = MixedScenarioService._baseline_flow(mean_demand)
        std_dev = math.sqrt(max(0.0, float(variance)))
        total_lead = max(0, int(order_leadtime)) + max(0, int(supply_leadtime))
        z = 0.5  # ~69% coverage (reduced from 1.645 for lower initial inventory)
        safety_stock = 0.0 if total_lead <= 0 else z * std_dev * math.sqrt(total_lead)
        # Cycle stock now based on order lead time only (not supply lead time).
        effective_order_horizon = max(int(order_leadtime), 0)
        effective_supply = max(int(supply_leadtime), 0)
        cycle_stock = max(0.0, float(mean_demand)) * effective_order_horizon
        raw_initial_inventory = cycle_stock + safety_stock
        initial_inventory = int(round(raw_initial_inventory))
        if initial_inventory < baseline:
            initial_inventory = baseline
        on_order = int(round(max(0.0, float(mean_demand)) * max(0, int(order_leadtime))))
        base_stock = int(
            round(max(0.0, float(mean_demand)) * (max(0, int(order_leadtime))) + safety_stock)
        )
        if base_stock < initial_inventory:
            base_stock = initial_inventory

        if callable(debug_hook):
            debug_hook(
                {
                    "mean_demand": float(mean_demand),
                    "variance": float(variance),
                    "order_leadtime": int(order_leadtime),
                    "supply_leadtime": int(supply_leadtime),
                    "baseline_flow": baseline,
                    "std_dev": std_dev,
                    "total_lead": total_lead,
                    "safety_stock": safety_stock,
                    "effective_supply_horizon": effective_supply,
                    "cycle_stock": cycle_stock,
                    "raw_initial_inventory": raw_initial_inventory,
                    "initial_inventory": initial_inventory,
                    "on_order": on_order,
                    "base_stock": base_stock,
                }
            )

        return {
            "steady_quantity": baseline,
            "initial_inventory": max(0, initial_inventory),
            "on_order": max(0, on_order),
            "base_stock": max(0, base_stock),
            "safety_stock": int(round(max(0.0, safety_stock))),
        }

    def _reseed_engine_state(
        self,
        cfg: Dict[str, Any],
        lane_views: Dict[str, Any],
        mean_demand: float,
        variance: float,
        game: Optional[Game] = None,
    ) -> Dict[str, Any]:
        """Reset engine_state with per-item seeding along demand lanes."""

        engine: Dict[str, Dict[str, Any]] = {}
        node_policies = cfg.get("node_policies", {})
        node_types_map = lane_views.get("node_types", {})
        node_master_types = lane_views.get("node_master_types") or MixedScenarioService._extract_node_master_types(cfg)
        orders_map = lane_views.get("orders_map", {})
        shipments_map = lane_views.get("shipments_map", {})
        lane_lookup = lane_views.get("lane_lookup", {})
        node_item_baselines = cfg.get("initial_node_item_baselines") or {}
        bom_map = cfg.get("bill_of_materials") or {}

        cfg_items = cfg.get("items") or []
        primary_item_id: Optional[str] = None
        for entry in cfg_items:
            candidate = entry.get("id") if isinstance(entry, dict) else getattr(entry, "id", None)
            token = MixedScenarioService._normalise_product_id(candidate)
            if token:
                primary_item_id = token
                break
        if primary_item_id is None:
            raise ValueError("Supply-chain config must define at least one item id to seed pipelines")

        demand_seeds: Dict[str, Dict[str, float]] = defaultdict(dict)
        for md in cfg.get("market_demands") or []:
            if not isinstance(md, Mapping):
                continue
            item_token = MixedScenarioService._normalise_product_id(md.get("product_id") or md.get("item"))
            market_node = MixedScenarioService._normalise_key(md.get("market_node") or md.get("node") or md.get("node_key"))
            if not item_token or not market_node:
                continue
            pattern = md.get("demand_pattern") or md.get("pattern") or cfg.get("demand_pattern")
            try:
                md_mean, _ = estimate_demand_stats(pattern)
            except Exception:
                md_mean = mean_demand or DEFAULT_STEADY_STATE_DEMAND
            demand_seeds[market_node][item_token] = max(0.0, float(md_mean))

        upstream_cache: Dict[str, List[str]] = {}
        # Prefer the explicit orders_map (downstream -> [upstream]) so we don't
        # accidentally mix supply/shipment edges into the demand propagation
        # graph. Fall back to reversing shipments_map if orders_map is empty.
        if orders_map:
            for down, ups in orders_map.items():
                down_key = MixedScenarioService._normalise_key(down)
                upstream_cache[down_key] = [
                    MixedScenarioService._normalise_key(up) for up in ups if up
                ]
        else:
            for upstream, downs in shipments_map.items():
                for down in downs:
                    key = MixedScenarioService._normalise_key(down)
                    upstream_cache.setdefault(key, []).append(MixedScenarioService._normalise_key(upstream))

        bill_of_materials: Dict[str, Dict[str, Dict[str, int]]] = {}
        for node_key, items in (bom_map or {}).items():
            node_norm = MixedScenarioService._normalise_key(node_key)
            if not isinstance(items, Mapping):
                continue
            node_bom: Dict[str, Dict[str, int]] = bill_of_materials.setdefault(node_norm, {})
            for raw_item, components in items.items():
                finished_id = MixedScenarioService._normalise_product_id(raw_item)
                if not finished_id or not isinstance(components, Mapping):
                    continue
                comp_map: Dict[str, int] = {}
                for comp_id, qty in components.items():
                    try:
                        qty_int = int(qty)
                    except (TypeError, ValueError):
                        continue
                    if qty_int <= 0:
                        continue
                    comp_map[MixedScenarioService._normalise_product_id(comp_id)] = qty_int
                if comp_map:
                    node_bom[finished_id] = comp_map

        demand_totals: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        visited_pairs: Set[Tuple[str, str]] = set()
        revisit_events: List[Tuple[str, str, float]] = []

        def propagate(node: str, item: str, qty: float) -> None:
            """Accumulate demand upstream while avoiding cycles."""
            if qty <= 0:
                return
            key = (node, item)
            if key in visited_pairs:
                revisit_events.append((node, item, qty))
                return
            visited_pairs.add(key)

            demand_totals[node][item] += qty
            for upstream in upstream_cache.get(node, []):
                if not upstream:
                    continue
                bom = bill_of_materials.get(node, {})
                if item in bom:
                    for comp_id, comp_qty in bom[item].items():
                        propagate(upstream, MixedScenarioService._normalise_product_id(comp_id), qty * comp_qty)
                else:
                    propagate(upstream, item, qty)

        for md_node, items in demand_seeds.items():
            for product_id, qty in items.items():
                propagate(md_node, product_id, qty)

        if revisit_events and game is not None:
            try:
                dbg_cfg = normalize_debug_config(dict(cfg or {}))
                dbg_cfg["enabled"] = True
                ensure_debug_log_file(dbg_cfg, game)
                append_debug_error(
                    dbg_cfg,
                    game,
                    "Cycle detected while reseeding demand",
                    details={
                        "revisit_count": len(revisit_events),
                        "examples": [
                            {"node": n, "item": itm, "qty": q}
                            for (n, itm, q) in revisit_events[:5]
                        ],
                    },
                )
            except Exception:
                logger.debug(
                    "Unable to log demand reseed cycle for game %s", getattr(game, "id", "?")
                )

        for node in lane_views.get("all_nodes", []):
            policy = MixedScenarioService._policy_for_node(node_policies, node)
            node_role = node_master_types.get(node) or MixedScenarioService._master_node_type(node_types_map.get(node) or node)
            upstream_sources = [u for u, downs in shipments_map.items() if node in downs and u != node]
            default_upstream = upstream_sources[0] if upstream_sources else "__upstream__"
            downstream_customers = [downstream for downstream, upstreams in orders_map.items() if node in upstreams]
            if not downstream_customers:
                downstream_customers = shipments_map.get(node, [])
            default_downstream = downstream_customers[0] if downstream_customers else None

            inbound_lanes = []
            for upstream in upstream_sources:
                lane_rec = lane_lookup.get(
                    (MixedScenarioService._normalise_key(upstream), MixedScenarioService._normalise_key(node))
                )
                if lane_rec:
                    inbound_lanes.append(lane_rec)

            def _lane_lead(rec: Mapping[str, Any], key: str) -> Optional[int]:
                raw = rec.get(key)
                if raw is None:
                    return None
                return MixedScenarioService._coerce_leadtime_value(raw)

            lane_order_leads = [
                lead for lane in inbound_lanes for lead in (
                    _lane_lead(lane, "demand_lead_time"),
                    _lane_lead(lane, "order_leadtime"),
                ) if lead is not None
            ]
            lane_supply_leads = [
                lead for lane in inbound_lanes for lead in (
                    _lane_lead(lane, "supply_lead_time"),
                    _lane_lead(lane, "supply_leadtime"),
                ) if lead is not None
            ]

            order_leadtime = int(policy.get("order_leadtime", 0) or 0)
            if not order_leadtime:
                order_leadtime = max(0, max(lane_order_leads) if lane_order_leads else 0)
            supply_leadtime = int(policy.get("supply_leadtime", 0) or 0)
            if not supply_leadtime:
                supply_leadtime = max(0, max(lane_supply_leads) if lane_supply_leads else 0)
            if supply_leadtime <= 0 and node_role not in {"market_supply", "market_demand"}:
                # Default to 2 if nothing is configured for non-market nodes.
                supply_leadtime = 2
            if order_leadtime <= 0:
                raise ValueError(
                    f"Node '{node}' is missing order_leadtime in policy or lane configuration; cannot seed."
                )
            if supply_leadtime <= 0 and node_role not in {"market_supply", "market_demand"}:
                raise ValueError(
                    f"Node '{node}' is missing supply_leadtime in policy or lane configuration; cannot seed."
                )

            item_demands_orders = demand_totals.get(node) or {}
            if not item_demands_orders:
                item_demands_orders = {primary_item_id: max(0.0, float(mean_demand or 0.0))}
            else:
                # Ensure baseline demand is at least the mean demand for primary item so seeding stays consistent.
                current_primary = item_demands_orders.get(primary_item_id, 0.0)
                baseline_primary = max(0.0, float(mean_demand or 0.0))
                if baseline_primary > current_primary:
                    item_demands_orders[primary_item_id] = baseline_primary

            # Split finished vs component demand for manufacturers.
            finished_demands: Dict[str, float] = dict(item_demands_orders)
            component_demands: Dict[str, float] = {}
            if node_role == "manufacturer":
                bom = MixedScenarioService._bom_for_node(cfg, node)
                if not bom:
                    raise ValueError(f"Manufacturer '{node}' is missing a bill_of_materials; cannot seed.")
                comp_accum: Dict[str, float] = defaultdict(float)
                for finished_id, qty in finished_demands.items():
                    demand_qty = max(0.0, float(qty))
                    components = bom.get(finished_id)
                    if components:
                        for comp_id, comp_qty in components.items():
                            comp_accum[MixedScenarioService._normalise_product_id(comp_id)] += demand_qty * comp_qty
                    else:
                        comp_accum[finished_id] += demand_qty
                component_demands = dict(comp_accum)
                if not component_demands:
                    raise ValueError(f"Manufacturer '{node}' BOM did not yield component demand; check item ids and BOM mapping.")

            # Manufacturers must always seed component pipelines if a BOM exists.
            supply_demands: Dict[str, float] = dict(component_demands) if component_demands else dict(item_demands_orders)

            inventory_by_item: Dict[str, int] = {}
            backlog_by_item: Dict[str, int] = {}
            on_order_by_item: Dict[str, int] = {}
            base_stock_by_item: Dict[str, int] = {}
            finished_inventory_by_item: Dict[str, int] = {}
            component_inventory_by_item: Dict[str, int] = {}

            inbound_supply: List[Dict[str, Any]] = []
            inbound_demand_entries: List[Dict[str, Any]] = []
            steady_by_item: Dict[str, int] = {}

            bom_for_node = bill_of_materials.get(node, {}) or {}

            def _simple_seed(
                product_id: str,
                demand_mean_val: float,
                *,
                create_shipments: bool = True,
                ledger: str = "inventory",
                cover_weeks: Optional[int] = None,
            ) -> float:
                """
                Seed using demand * supply_leadtime (cycle stock) with steady flow demand_mean.

                The steady quantity and inventory are never allowed to drop below the default
                steady-state demand so every node starts with at least one order and one arrival.
                Shipments can be suppressed for finished goods at manufacturers so their inbound
                supply only contains components.
                """
                if demand_mean_val is None:
                    raise ValueError(f"Cannot seed item '{product_id}' without a demand mean")
                steady_qty = float(demand_mean_val)
                if steady_qty <= 0:
                    raise ValueError(f"Cannot seed item '{product_id}' with non-positive demand mean ({steady_qty})")
                steady_qty_int = int(steady_qty)
                coverage_weeks = cover_weeks
                if coverage_weeks is None:
                    coverage_weeks = supply_leadtime
                try:
                    coverage_weeks_int = int(coverage_weeks)
                except (TypeError, ValueError):
                    coverage_weeks_int = supply_leadtime
                coverage_weeks_int = max(1, coverage_weeks_int)
                inv_seed = steady_qty_int * coverage_weeks_int
                if ledger == "finished":
                    finished_inventory_by_item[product_id] = inv_seed + int(
                        finished_inventory_by_item.get(product_id, 0)
                    )
                elif ledger == "component":
                    component_inventory_by_item[product_id] = inv_seed + int(
                        component_inventory_by_item.get(product_id, 0)
                    )
                inventory_by_item[product_id] = inv_seed + int(inventory_by_item.get(product_id, 0))
                on_order_by_item[product_id] = inv_seed + int(on_order_by_item.get(product_id, 0))
                base_stock_by_item[product_id] = inv_seed + int(base_stock_by_item.get(product_id, 0))
                steady_by_item[product_id] = steady_qty_int
                if create_shipments:
                    for offset in range(max(0, coverage_weeks_int)):
                        arrival_round = offset + 1
                        inbound_supply.append(
                            {
                                "arrival_round": arrival_round,
                                "step_number": arrival_round,
                                "quantity": steady_qty,
                                "product_id": product_id,
                                "source": default_upstream,
                                "destination": node,
                            }
                        )
                return steady_qty

            node_type_slug = MixedScenarioService._normalise_node_type(node_types_map.get(node)) if node_types_map else ""
            component_supplier_node = node_type_slug in {"component_supplier", "supplier", "tier1_supplier"}
            node_seed_cover_weeks = supply_leadtime
            if component_supplier_node:
                node_seed_cover_weeks = max(1, supply_leadtime // 2)

            # Seed finished goods inventory separately for manufacturers (no inbound shipments for finished SKUs).
            finished_seed_source = finished_demands if node_role == "manufacturer" else supply_demands
            for product_id, demand_mean in finished_seed_source.items():
                demand_mean_val = max(0.0, float(demand_mean))
                _simple_seed(
                    product_id,
                    demand_mean_val,
                    create_shipments=node_role != "manufacturer",
                    ledger="finished" if node_role == "manufacturer" else "inventory",
                    cover_weeks=node_seed_cover_weeks,
                )

            # Seed component inventory and inbound supply for manufacturers using BOM-defined component demands.
            if node_role == "manufacturer":
                bom_map = MixedScenarioService._bom_for_node(cfg, node)
                for finished_id, components in bom_map.items():
                    demand_mean_val = max(0.0, float(finished_demands.get(finished_id, 0)))
                    if demand_mean_val <= 0:
                        # Fall back to supply_demands entry if present
                        demand_mean_val = max(0.0, float(supply_demands.get(finished_id, 0)))
                    if demand_mean_val <= 0:
                        continue
                    for comp_id, comp_qty in components.items():
                        try:
                            comp_qty_int = int(comp_qty)
                        except (TypeError, ValueError):
                            continue
                        if comp_qty_int <= 0:
                            continue
                        comp_demand = demand_mean_val * comp_qty_int
                        _simple_seed(
                            MixedScenarioService._normalise_product_id(comp_id),
                            comp_demand,
                            create_shipments=True,
                            ledger="component",
                            cover_weeks=node_seed_cover_weeks,
                        )

            # For manufacturers, ensure inbound_supply only contains component shipments (no finished goods arrivals).
            if node_role == "manufacturer":
                inbound_supply = [entry for entry in inbound_supply if MixedScenarioService._normalise_product_id(entry.get("product_id")) not in finished_demands]

            if node_role == "market_supply":
                inventory_by_item = {product_id: 0 for product_id in item_demands_orders}
                on_order_by_item = {product_id: 0 for product_id in item_demands_orders}
                base_stock_by_item = {product_id: 0 for product_id in item_demands_orders}
                inbound_supply = []
                inbound_demand_entries = []
            elif node_role == "market_demand":
                inventory_by_item = {product_id: 0 for product_id in item_demands_orders}
                on_order_by_item = {product_id: 0 for product_id in item_demands_orders}
                base_stock_by_item = {product_id: 0 for product_id in item_demands_orders}
                inbound_demand_entries = []
            else:
                # Seed just one steady-state order so round one matches the baseline flow.
                if default_downstream and order_leadtime > 0:
                    for product_id, steady_qty in item_demands_orders.items():
                        seed_qty = int(
                            steady_by_item.get(
                                product_id,
                                max(int(DEFAULT_STEADY_STATE_DEMAND), int(steady_qty or 0)),
                            )
                        )
                        inbound_demand_entries.append(
                            {
                                "step_number": 1,
                                "due_round": 1,
                                "quantity": seed_qty,
                                "order_priority": 1,
                                "downstream": default_downstream,
                                "source": default_downstream,
                                "product_id": product_id,
                            }
                        )

            inventory_total = sum(inventory_by_item.values())
            on_order_total = sum(on_order_by_item.values())

            state: Dict[str, Any] = {
                "current_step": 0,
                "inventory": inventory_total if node_role not in {"market_supply", "market_demand"} else 0,
                "backlog": 0,
                "on_order": on_order_total if node_role not in {"market_supply", "market_demand"} else 0,
                "base_stock": sum(base_stock_by_item.values()) if node_role not in {"market_supply", "market_demand"} else 0,
                "backlog_breakdown": {},
                "inventory_by_item": inventory_by_item,
                "backlog_by_item": backlog_by_item,
                "on_order_by_item": on_order_by_item,
                "inbound_demand": inbound_demand_entries if node_role not in {"market_supply", "market_demand"} else [],
                "inbound_supply": inbound_supply if node_role != "market_supply" else [],
                "incoming_orders": 0,
            }

            state["demand_lead_time"] = order_leadtime
            state["shipment_lead_time"] = supply_leadtime

            order_pipeline = MixedScenarioService._order_pipeline_snapshot(
                state.get("inbound_demand", []),
                current_round=0,
            )
            state["order_pipe"] = MixedScenarioService._normalise_pipeline_length(
                order_pipeline,
                order_leadtime,
            )

            supply_pipeline = summarise_inbound_supply_queue(
                state.get("inbound_supply", []),
                current_step=0,
                supply_leadtime=supply_leadtime,
            )
            state["pipeline_shipments"] = MixedScenarioService._normalise_pipeline_length(
                supply_pipeline,
                supply_leadtime,
            )
            state.setdefault("immediate_order_buffer", 0)
            if state["order_pipe"]:
                state["last_incoming_order"] = int(state["order_pipe"][0])
            else:
                state["last_incoming_order"] = 0

            if node_role == "manufacturer":
                state["finished_inventory_by_item"] = dict(finished_inventory_by_item)
                state["component_inventory_by_item"] = dict(component_inventory_by_item)

            if node_role == "market_supply":
                state["inventory"] = 0
                state["on_order"] = 0

            engine[node] = state

        cfg["engine_state"] = engine
        cfg["history"] = []
        return cfg

    @staticmethod
    def _seed_order_queue(
        state: Dict[str, Any],
        *,
        current_step: int,
        order_leadtime: int,
        quantity: int,
        detail_breakdown: Optional[Dict[str, int]] = None,
        default_downstream: Optional[str] = None,
        product_id: Optional[str] = None,
    ) -> None:
        try:
            baseline_quantity = int(quantity)
        except (TypeError, ValueError):
            baseline_quantity = DEFAULT_STEADY_STATE_DEMAND

        if baseline_quantity <= 0:
            baseline_quantity = DEFAULT_STEADY_STATE_DEMAND

        if order_leadtime <= 0 or baseline_quantity <= 0:
            state["inbound_demand"] = []
            return

        # Do not create self-referential orders; if there is no upstream target, skip seeding.
        if not default_downstream:
            state["inbound_demand"] = []
            return

        if not product_id or MixedScenarioService._normalise_product_id(product_id) == "default":
            raise ValueError("Cannot seed order queue without a valid product_id")

        # Warm-up with a single steady-state order so round-one demand matches baseline flow.
        state["inbound_demand"] = [
            {
                "step_number": current_step + 1,
                "quantity": baseline_quantity,
                "order_priority": 1,
                "downstream": default_downstream,
                "product_id": product_id,
            }
        ]

    @staticmethod
    def _initialise_shipment_pipeline(
        state: Dict[str, Any],
        *,
        supply_leadtime: int,
        default_quantity: int,
        product_id: str,
    ) -> None:
        # Legacy shipment pipeline removed; rely solely on inbound_supply.
        state.pop("ship_queue", None)
        state.pop("incoming_shipments", None)
        state.pop("inbound_supply_future", None)
        state.pop("ship_detail_queue", None)
        return

    @staticmethod
    def _initialise_order_pipeline(
        state: Dict[str, Any],
        *,
        order_leadtime: int,
        default_quantity: int,
        detail_breakdown: Optional[Dict[str, int]] = None,
    ) -> None:
        # Legacy info/demand pipeline removed; rely solely on inbound_demand.
        state.pop("info_queue", None)
        state.pop("info_detail_queue", None)
        state["incoming_orders"] = 0
        return

    @staticmethod
    def _calculate_order_quantity(
        *,
        node_type: str,
        policy: Dict[str, Any],
        total_demand: int,
        state: Dict[str, Any],
        cfg: Dict[str, Any],
        global_policy: Dict[str, Any],
    ) -> int:
        """Compute the order quantity for a node after fulfilling local demand."""

        if node_type == "market_demand":
            return 0

        strategy = MixedScenarioService._infer_node_strategy(policy, cfg, global_policy)
        if strategy in {"naive", "naiive"}:
            demand_val = max(0, int(total_demand))
            backlog_val = max(0, int(state.get("backlog", 0)))
            inventory_val = max(0, int(state.get("inventory", 0)))
            pipeline_val = max(0, int(state.get("on_order", 0)))

            uncovered_backlog = max(0, backlog_val - inventory_val - pipeline_val)
            planned_order = demand_val + uncovered_backlog
            return max(0, int(planned_order))

        supply_leadtime = int(policy.get("supply_leadtime", 2))
        target_inventory = int(policy.get("init_inventory", 12) + 2 * supply_leadtime)

        backlog = int(state.get("backlog", 0))
        inventory = int(state.get("inventory", 0))
        on_order = int(state.get("on_order", 0))

        desired = target_inventory + backlog - inventory - on_order
        return max(0, int(desired))

    @staticmethod
    def _infer_node_strategy(policy: Dict[str, Any], cfg: Dict[str, Any], global_policy: Dict[str, Any]) -> str:
        """
        Resolve a strategy token for a node from policy/global settings.
        Falls back to 'naive' if nothing is configured.
        """
        for source in (policy, cfg, global_policy):
            if not isinstance(source, Mapping):
                continue
            val = source.get("strategy") or source.get("node_strategy") or source.get("policy")
            if val:
                return str(val).lower()
        return "naive"

    @staticmethod
    def _resolve_user_type(user: Optional[User]) -> Optional[UserTypeEnum]:
        user_type = getattr(user, "user_type", None)
        if isinstance(user_type, UserTypeEnum):
            return user_type
        if isinstance(user_type, Enum):
            try:
                return UserTypeEnum(user_type.value)
            except ValueError:
                return None
        if isinstance(user_type, str):
            try:
                return UserTypeEnum(user_type)
            except ValueError:
                return None
        return None

    @staticmethod
    def _schema_status_to_db_values(status: GameStatus) -> List[str]:
        mapping = {
            GameStatus.CREATED: [GameStatusDB.CREATED.value],
            GameStatus.IN_PROGRESS: [
                GameStatusDB.STARTED.value,
                getattr(GameStatusDB, "IN_PROGRESS", GameStatusDB.STARTED).value
                if hasattr(GameStatusDB, "IN_PROGRESS")
                else GameStatusDB.STARTED.value,
                getattr(GameStatusDB, "ROUND_IN_PROGRESS", GameStatusDB.STARTED).value,
                getattr(GameStatusDB, "ROUND_COMPLETED", GameStatusDB.STARTED).value,
                GameStatus.IN_PROGRESS.value,
            ],
            GameStatus.COMPLETED: [
                getattr(GameStatusDB, "FINISHED", GameStatusDB.CREATED).value,
                GameStatus.COMPLETED.value,
            ],
            GameStatus.PAUSED: [GameStatus.PAUSED.value, "PAUSED", "paused"],
        }
        return mapping.get(status, [status.value])

    @staticmethod
    def _map_status_to_schema(status_value: Any) -> GameStatus:
        if isinstance(status_value, GameStatus):
            return status_value
        if isinstance(status_value, GameStatusDB):
            raw = status_value.value
        elif isinstance(status_value, Enum):
            raw = status_value.value
        else:
            raw = str(status_value or "")

        mapping = {
            GameStatusDB.CREATED.value: GameStatus.CREATED,
            "CREATED": GameStatus.CREATED,
            "created": GameStatus.CREATED,
            GameStatusDB.STARTED.value: GameStatus.IN_PROGRESS,
            getattr(GameStatusDB, "IN_PROGRESS", GameStatusDB.STARTED).value: GameStatus.IN_PROGRESS,
            getattr(GameStatusDB, "ROUND_IN_PROGRESS", GameStatusDB.STARTED).value: GameStatus.IN_PROGRESS,
            getattr(GameStatusDB, "ROUND_COMPLETED", GameStatusDB.STARTED).value: GameStatus.IN_PROGRESS,
            "started": GameStatus.IN_PROGRESS,
            "IN_PROGRESS": GameStatus.IN_PROGRESS,
            "in_progress": GameStatus.IN_PROGRESS,
            (GameStatusDB.FINISHED.value if hasattr(GameStatusDB, "FINISHED") else "FINISHED"): GameStatus.COMPLETED,
            "finished": GameStatus.COMPLETED,
            "completed": GameStatus.COMPLETED,
            "COMPLETED": GameStatus.COMPLETED,
            "PAUSED": GameStatus.PAUSED,
            "paused": GameStatus.PAUSED,
        }

        for token in {raw, raw.upper(), raw.lower()}:
            normalized = mapping.get(token)
            if normalized:
                return normalized

        if raw in GameStatus.__members__:
            return GameStatus[raw]

        if raw in GameStatus._value2member_map_:
            return GameStatus(raw)

        return GameStatus.CREATED

    @staticmethod
    def _compute_updated_at(game: Game) -> datetime:
        for attr in ("updated_at", "finished_at", "completed_at", "started_at", "created_at"):
            value = getattr(game, attr, None)
            if value:
                return value
        return datetime.utcnow()

    def _serialize_game(self, game: Any) -> GameInDBBase:
        config, _config_upgraded = self._upgrade_json_value(
            getattr(game, "config", {}) or {},
            dict,
            default_factory=dict,
            context="MixedScenarioService._serialize_game",
            field_name="config",
            game=game if isinstance(game, Game) else None,
            auto_commit=True,
        )
        demand_pattern_source = getattr(game, "demand_pattern", None) or config.get("demand_pattern") or DEFAULT_DEMAND_PATTERN
        try:
            demand_pattern = normalize_demand_pattern(demand_pattern_source)
        except Exception:
            demand_pattern = normalize_demand_pattern(DEFAULT_DEMAND_PATTERN)

        tenant_id = getattr(game, "tenant_id", None) or config.get("tenant_id")
        if tenant_id is not None and "tenant_id" not in config:
            config["tenant_id"] = tenant_id

        progression_mode = config.get("progression_mode")
        if not progression_mode:
            progression_mode = "supervised"
            config.setdefault("progression_mode", progression_mode)

        supply_chain_config_id = config.get("supply_chain_config_id") or getattr(game, "supply_chain_config_id", None)
        if supply_chain_config_id is not None:
            try:
                supply_chain_config_id = int(supply_chain_config_id)
            except (TypeError, ValueError):
                pass
            else:
                config.setdefault("supply_chain_config_id", supply_chain_config_id)

        supply_chain_name = (
            config.get("supply_chain_name")
            or getattr(game, "supply_chain_name", None)
        )
        if not supply_chain_name and supply_chain_config_id is not None:
            supply_chain_name = self._resolve_supply_chain_name(supply_chain_config_id)
        if supply_chain_name:
            config["supply_chain_name"] = supply_chain_name

        payload: Dict[str, Any] = {
            "id": game.id,
            "name": getattr(game, "name", f"Game {game.id}") or f"Game {game.id}",
            "status": self._map_status_to_schema(getattr(game, "status", None)),
            "current_round": getattr(game, "current_round", 0) or 0,
            "max_rounds": getattr(game, "max_rounds", 0) or 0,
            "demand_pattern": demand_pattern,
            "created_at": getattr(game, "created_at", datetime.utcnow()),
            "updated_at": self._compute_updated_at(game),
            "started_at": getattr(game, "started_at", None),
            "completed_at": getattr(game, "completed_at", None) or getattr(game, "finished_at", None),
            "created_by": getattr(game, "created_by", None),
            "tenant_id": tenant_id,
            "config": config,
            "progression_mode": progression_mode,
            "scenario_users": [],
        }

        if supply_chain_config_id is not None:
            payload["supply_chain_config_id"] = supply_chain_config_id
        if supply_chain_name:
            payload["supply_chain_name"] = supply_chain_name

        if config.get("pricing_config"):
            payload["pricing_config"] = config["pricing_config"]
        if config.get("node_policies"):
            payload["node_policies"] = config["node_policies"]
        if config.get("system_config"):
            payload["system_config"] = config["system_config"]
        if config.get("global_policy"):
            payload["global_policy"] = config["global_policy"]
        if config.get("autonomy_llm"):
            payload["autonomy_llm"] = config["autonomy_llm"]

        try:
            return GameInDBBase.model_validate(payload)
        except Exception:
            # Fallback to minimal payload if custom config fails validation
            for key in ("pricing_config", "node_policies", "system_config", "global_policy"):
                payload.pop(key, None)
            payload["demand_pattern"] = normalize_demand_pattern(DEFAULT_DEMAND_PATTERN)
            return GameInDBBase.model_validate(payload)
    
    def create_game(self, game_data: GameCreate, created_by: int = None) -> Game:
        """Create a new game with mixed human/agent scenario_users.

        Persists extended configuration into Game.config JSON to avoid schema changes.
        """
        # Create the game
        normalized_pattern = (
            normalize_demand_pattern(game_data.demand_pattern.dict())
            if game_data.demand_pattern
            else normalize_demand_pattern(DEFAULT_DEMAND_PATTERN)
        )

        config: Dict[str, Any] = {
            "demand_pattern": normalized_pattern,
            "pricing_config": game_data.pricing_config.dict() if hasattr(game_data, 'pricing_config') else {},
            "node_policies": (game_data.node_policies or {}),
            "system_config": (game_data.system_config or {}),
            "global_policy": (game_data.global_policy or {}),
            "progression_mode": getattr(game_data, "progression_mode", "supervised"),
        }
        if getattr(game_data, "autonomy_llm", None):
            config["autonomy_llm"] = game_data.autonomy_llm.model_dump()
        supply_chain_id = getattr(game_data, "supply_chain_config_id", None)
        if supply_chain_id is None:
            raise ValueError("supply_chain_config_id is required to create a game from a supply chain configuration")
        try:
            config["supply_chain_config_id"] = int(supply_chain_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("supply_chain_config_id must be an integer") from exc
        config_record = self._get_supply_chain_config(config["supply_chain_config_id"])
        if not config_record:
            raise ValueError(
                f"Supply chain configuration with ID {config['supply_chain_config_id']} not found"
            )

        supply_chain_name = (
            getattr(game_data, "supply_chain_name", None)
            or getattr(config_record, "name", None)
            or self._resolve_supply_chain_name(config["supply_chain_config_id"])
        )
        if supply_chain_name:
            config["supply_chain_name"] = supply_chain_name

        config_tenant_id = getattr(config_record, "tenant_id", None)
        if config_tenant_id is not None:
            config["tenant_id"] = config_tenant_id

        time_bucket = normalize_time_bucket(
            getattr(config_record, "time_bucket", TimeBucket.WEEK)
        )
        config["time_bucket"] = time_bucket.value
        config["start_date"] = DEFAULT_START_DATE.isoformat()
        game = Game(
            name=game_data.name,
            max_rounds=game_data.max_rounds,
            status=GameStatus.CREATED,
            config=config,
            supply_chain_config_id=config["supply_chain_config_id"],
            time_bucket=time_bucket.value,
            start_date=DEFAULT_START_DATE,
            tenant_id=config_tenant_id,
        )
        self.db.add(game)
        self.db.flush()

        # Persist creator/metadata into columns if present in schema (fallback-safe via raw SQL)
        try:
            from sqlalchemy import text
            dp = json.dumps(normalized_pattern) if getattr(game_data, 'demand_pattern', None) else None
            desc = getattr(game_data, 'description', None)
            is_public = getattr(game_data, 'is_public', True)
            self.db.execute(
                text(
                    "UPDATE games SET description = :desc, is_public = :is_public, demand_pattern = :dp, created_by = :creator WHERE id = :id"
                ),
                {
                    "desc": desc,
                    "is_public": bool(is_public),
                    "dp": dp,
                    "creator": created_by if created_by is not None else None,
                    "id": game.id,
                },
            )
        except Exception as _e:
            # Non-fatal: older schemas may not have these columns
            pass
        
        # Create scenario_users based on assignments
        # Validate node policies against system ranges (if provided/persisted)
        sys_cfg = read_system_cfg()
        rng = sys_cfg.dict() if sys_cfg else {}
        def _check_range(key: str, val: float):
            r = rng.get(key)
            if not r:
                return
            lo, hi = r.get('min'), r.get('max')
            if lo is not None and val < lo: 
                raise ValueError(f"{key} below minimum {lo}")
            if hi is not None and val > hi:
                raise ValueError(f"{key} above maximum {hi}")
        for node, pol in (game_data.node_policies or {}).items():
            _check_range('order_leadtime', getattr(pol, 'order_leadtime', 0))
            _check_range('supply_leadtime', getattr(pol, 'supply_leadtime', 0))
            _check_range('init_inventory', pol.init_inventory)
            _check_range('price', pol.price)
            _check_range('standard_cost', pol.standard_cost)
            _check_range('variable_cost', pol.variable_cost)
            _check_range('min_order_qty', pol.min_order_qty)

        cfg = game.config if game.config else {}

        for i, assignment in enumerate(game_data.player_assignments):
            is_ai = assignment.scenario_user_type == ScenarioUserType.AGENT
            scenario_user = ScenarioUser(
                scenario_id=game.id,
                role=assignment.role,
                name=f"{assignment.role.capitalize()} ({'AI' if is_ai else 'Human'})",
                is_ai=is_ai,
                ai_strategy=(assignment.strategy.value if hasattr(assignment.strategy, 'value') else str(assignment.strategy)) if is_ai else None,
                can_see_demand=assignment.can_see_demand,
                llm_model=assignment.llm_model if is_ai else None,
                user_id=assignment.user_id if not is_ai else None
            )
            self.db.add(scenario_user)

            # Initialize inventory for the scenario_user
            inventory = ScenarioUserInventory(
                scenario_user=scenario_user,
                current_stock=12,
                incoming_shipments=[],
                backorders=0
            )
            self.db.add(inventory)

            # Initialize AI agent if this is an AI scenario_user
            if is_ai:
                try:
                    agent_type = AgentType(assignment.role.lower())
                    strategy_value = (
                        assignment.strategy.value
                        if hasattr(assignment.strategy, "value")
                        else str(assignment.strategy)
                    )
                    normalized_strategy = strategy_value.lower()
                    llm_strategy_token: Optional[str] = None
                    llm_variants = {
                        "llm": None,
                        "llm_balanced": "balanced",
                        "llm_conservative": "conservative",
                        "llm_aggressive": "aggressive",
                        "llm_adaptive": "adaptive",
                    }

                    if normalized_strategy in llm_variants:
                        strategy = AgentStrategyEnum.LLM
                        variant = llm_variants[normalized_strategy]
                        if variant is not None:
                            llm_strategy_token = variant
                    elif normalized_strategy == "llm_supervised":
                        strategy = AgentStrategyEnum.LLM_SUPERVISED
                    elif normalized_strategy == "llm_global":
                        strategy = AgentStrategyEnum.LLM_GLOBAL
                    else:
                        try:
                            strategy = AgentStrategyEnum(normalized_strategy)
                        except ValueError:
                            if normalized_strategy.startswith("llm"):
                                suffix = normalized_strategy.split("_", 1)[1] if "_" in normalized_strategy else None
                                if suffix:
                                    llm_strategy_token = suffix
                                strategy = AgentStrategyEnum.LLM
                            else:
                                raise
                    override_pct = None
                    if strategy in (
                        AgentStrategyEnum.AUTONOMY_DTCE_CENTRAL,
                        AgentStrategyEnum.LLM_SUPERVISED,
                    ):
                        override_pct = assignment.autonomy_override_pct
                        if override_pct is not None:
                            overrides = cfg.setdefault("autonomy_overrides", {})
                            overrides[assignment.role.value] = override_pct
                    if strategy in (
                        AgentStrategyEnum.LLM_SUPERVISED,
                        AgentStrategyEnum.LLM_GLOBAL,
                    ) and llm_strategy_token is None:
                        llm_strategy_token = "balanced"
                    self.agent_manager.set_agent_strategy(
                        agent_type,
                        strategy,
                        llm_model=assignment.llm_model,
                        override_pct=override_pct,
                        llm_strategy=llm_strategy_token,
                    )
                except Exception:
                    # Fallback: ignore if mapping not supported
                    pass

        game.config = cfg

        self.db.commit()
        self.db.refresh(game)
        return game

    def add_scenario_user(self, scenario_id: int, scenario_user_data: ScenarioUserCreate) -> ScenarioUser:
        """Add a human or AI scenario_user to an existing game."""

        game = self.db.query(Game).filter(Game.id == scenario_id).first()
        if not game:
            raise ValueError("Game not found")

        existing = (
            self.db.query(ScenarioUser)
            .filter(ScenarioUser.scenario_id == scenario_id, ScenarioUser.role == ScenarioUserRole[scenario_user_data.role.name])
            .first()
        )
        if existing:
            raise ValueError(f"A {scenario_user_data.role.value.lower()} is already registered for this game")

        is_ai = bool(scenario_user_data.is_ai)
        db_role = ScenarioUserRole[scenario_user_data.role.name]
        scenario_user = ScenarioUser(
            scenario_id=scenario_id,
            user_id=scenario_user_data.user_id,
            role=db_role,
            name=scenario_user_data.name,
            type=ScenarioUserTypeDB.AI if is_ai else ScenarioUserTypeDB.HUMAN,
            strategy=ScenarioUserStrategyDB.FIXED if is_ai else ScenarioUserStrategyDB.MANUAL,
            is_ai=is_ai,
            ai_strategy=("naive" if is_ai else None),
        )
        self.db.add(scenario_user)

        cfg = dict(getattr(game, "config", {}) or {})
        node_policies = cfg.get("node_policies") or {}
        role_key = self._normalise_key(scenario_user_data.role.value)
        policy = node_policies.get(role_key, {})
        raw_init = policy.get("init_inventory")
        if raw_init is not None:
            try:
                initial_inventory = int(raw_init)
            except (TypeError, ValueError):
                raise ValueError(
                    f"init_inventory for role '{role_key}' in scenario {scenario_id} config "
                    f"could not be parsed as an integer (got {raw_init!r}). "
                    f"Fix the node_policies.init_inventory value in the scenario config."
                )
        else:
            # No init_inventory in scenario config — load from InvLevel for this config
            config_id = getattr(game, "supply_chain_config_id", None)
            if config_id:
                _inv_site = (
                    self.db.query(Site)
                    .filter(Site.config_id == config_id)
                    .filter(Site.master_type.in_(["INVENTORY", "MANUFACTURER"]))
                    .order_by(Site.id)
                    .first()
                )
                _inv_level = None
                if _inv_site:
                    _product = (
                        self.db.query(Product)
                        .filter(Product.config_id == config_id)
                        .order_by(Product.id)
                        .first()
                    )
                    if _product:
                        _inv_level = (
                            self.db.query(InvLevel)
                            .filter(
                                InvLevel.site_id == _inv_site.id,
                                InvLevel.product_id == _product.id,
                            )
                            .first()
                        )
                if _inv_level and _inv_level.on_hand_qty is not None:
                    initial_inventory = int(_inv_level.on_hand_qty)
                else:
                    raise ValueError(
                        f"No init_inventory configured for role '{role_key}' in scenario {scenario_id}, "
                        f"and no InvLevel record found for config {config_id}. "
                        f"Set init_inventory in the node_policies config or seed InvLevel records "
                        f"for supply chain config {config_id}."
                    )
            else:
                raise ValueError(
                    f"Scenario {scenario_id} has no supply_chain_config_id and no init_inventory "
                    f"in node_policies for role '{role_key}'. "
                    f"Cannot initialize inventory without either a node_policies.init_inventory value "
                    f"or a linked supply chain config with InvLevel records."
                )

        inventory = ScenarioUserInventory(
            scenario_user=scenario_user,
            current_stock=initial_inventory,
            incoming_shipments=[],
            backorders=0,
            cost=0.0,
        )
        self.db.add(inventory)

        assignments = list(cfg.get("player_assignments") or [])
        assignments.append(
            {
                "role": scenario_user_data.role.value,
                "scenario_user_type": "AGENT" if is_ai else "HUMAN",
                "user_id": scenario_user_data.user_id,
                "strategy": "NAIVE" if is_ai else None,
                "can_see_demand": False,
                "llm_model": None,
                "autonomy_override_pct": None,
            }
        )
        cfg["player_assignments"] = assignments

        role_assignments, assignments_upgraded = self._upgrade_json_value(
            getattr(game, "role_assignments", {}) or {},
            dict,
            default_factory=dict,
            context="MixedScenarioService.add_scenario_user role_assignments",
            field_name="role_assignments",
            game=game,
        )
        role_assignments[role_key] = {
            "is_ai": is_ai,
            "agent_config_id": None,
            "user_id": None if is_ai else scenario_user_data.user_id,
        }
        game.role_assignments = role_assignments
        game.config = cfg
        if assignments_upgraded:
            flag_modified(game, "role_assignments")

        if is_ai:
            try:
                agent_role = AgentType(role_key)
                self.agent_manager.set_agent_strategy(agent_role, AgentStrategyEnum.NAIVE)
            except Exception:
                pass

        self.db.commit()
        self.db.refresh(scenario_user)
        return scenario_user

    def update_game(self, scenario_id: int, payload: Dict[str, Any]) -> Game:
        game = (
            self.db.query(Game)
            .filter(Game.id == scenario_id)
            .first()
        )
        if not game:
            raise ValueError("Game not found")

        cfg: Dict[str, Any] = dict(game.config or {})
        sys_cfg = read_system_cfg()
        ranges = sys_cfg.dict() if sys_cfg else {}

        if game.tenant_id is None:
            existing_config = self._get_supply_chain_config(
                cfg.get("supply_chain_config_id") or game.supply_chain_config_id
            )
            if existing_config and getattr(existing_config, "tenant_id", None) is not None:
                game.tenant_id = existing_config.tenant_id
                cfg.setdefault("tenant_id", existing_config.tenant_id)

        def _check_range(key: str, value: Optional[Any]) -> None:
            if value is None:
                return
            window = ranges.get(key)
            if not window:
                return
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be numeric") from exc
            lo, hi = window.get("min"), window.get("max")
            if lo is not None and numeric < lo:
                raise ValueError(f"{key} below minimum {lo}")
            if hi is not None and numeric > hi:
                raise ValueError(f"{key} above maximum {hi}")

        # --- Update simple fields ---
        if "name" in payload and payload["name"]:
            game.name = str(payload["name"]).strip()

        if "description" in payload:
            game.description = payload.get("description")

        if "is_public" in payload:
            game.is_public = bool(payload.get("is_public"))

        if "max_rounds" in payload and payload["max_rounds"] is not None:
            try:
                game.max_rounds = int(payload["max_rounds"])
            except (TypeError, ValueError) as exc:
                raise ValueError("max_rounds must be an integer") from exc

        if "progression_mode" in payload and payload["progression_mode"]:
            cfg["progression_mode"] = payload["progression_mode"]

        # Demand pattern update
        if payload.get("demand_pattern"):
            try:
                normalized_pattern = normalize_demand_pattern(payload["demand_pattern"])
            except Exception as exc:
                raise ValueError(f"Invalid demand pattern: {exc}") from exc
            cfg["demand_pattern"] = normalized_pattern
            game.demand_pattern = normalized_pattern

        # Config blocks
        node_policies = payload.get("node_policies")
        if node_policies is not None:
            for pol in node_policies.values():
                if not isinstance(pol, dict):
                    continue
                for key in [
                    "order_leadtime",
                    "supply_leadtime",
                    "init_inventory",
                    "price",
                    "standard_cost",
                    "variable_cost",
                    "min_order_qty",
                ]:
                    if key in pol:
                        _check_range(key, pol[key])
            cfg["node_policies"] = node_policies

        system_config = payload.get("system_config")
        if system_config is not None:
            cfg["system_config"] = system_config

        pricing_config = payload.get("pricing_config")
        if pricing_config is not None:
            cfg["pricing_config"] = pricing_config

        global_policy = payload.get("global_policy")
        if global_policy is not None:
            for key, value in global_policy.items():
                _check_range(key, value)
            cfg["global_policy"] = global_policy

        if "supply_chain_config_id" in payload:
            supply_id = payload.get("supply_chain_config_id")
            if supply_id is None:
                raise ValueError("supply_chain_config_id cannot be null")
            try:
                supply_id_int = int(supply_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("supply_chain_config_id must be an integer") from exc

            config_record = self._get_supply_chain_config(supply_id_int)
            if not config_record:
                raise ValueError(
                    f"Supply chain configuration with ID {supply_id_int} not found"
                )

            cfg["supply_chain_config_id"] = supply_id_int
            game.supply_chain_config_id = supply_id_int

            supply_name = (
                payload.get("supply_chain_name")
                or getattr(config_record, "name", None)
                or self._resolve_supply_chain_name(supply_id_int)
            )
            if supply_name:
                cfg["supply_chain_name"] = supply_name
            else:
                cfg.pop("supply_chain_name", None)

            config_tenant_id = getattr(config_record, "tenant_id", None)
            if config_tenant_id is not None:
                game.tenant_id = config_tenant_id
                cfg["tenant_id"] = config_tenant_id

            time_bucket = normalize_time_bucket(
                getattr(config_record, "time_bucket", TimeBucket.WEEK)
            )
            game.time_bucket = time_bucket.value
            cfg["time_bucket"] = time_bucket.value
        elif "supply_chain_name" in payload and cfg.get("supply_chain_config_id") is not None:
            supply_name = payload.get("supply_chain_name")
            if supply_name:
                cfg["supply_chain_name"] = supply_name
            else:
                cfg.pop("supply_chain_name", None)

        autonomy_llm = payload.get("autonomy_llm")
        if autonomy_llm is not None:
            cfg["autonomy_llm"] = autonomy_llm

        scenario_user_assignments_payload = payload.get("player_assignments")
        if scenario_user_assignments_payload is not None:
            self._apply_scenario_user_updates(game, cfg, scenario_user_assignments_payload)

        game.config = cfg
        self.db.add(game)
        self.db.commit()
        self.db.refresh(game)
        return game

    def submit_order(
        self,
        scenario_id: int,
        scenario_user_id: int,
        order_quantity: int,
        comment: Optional[str] = None,
    ) -> ScenarioUserPeriod:
        """Record or update a scenario_user's order for the active round."""

        game = self.db.query(Game).filter(Game.id == scenario_id).first()
        if not game or MixedScenarioService._map_status_to_schema(game.status) != GameStatus.IN_PROGRESS:
            raise ValueError("Game is not in progress")

        scenario_user = (
            self.db.query(ScenarioUser)
            .filter(ScenarioUser.id == scenario_user_id, ScenarioUser.scenario_id == scenario_id)
            .first()
        )
        if not scenario_user:
            raise ValueError("ScenarioUser not found for this game")

        current_round = (
            self.db.query(ScenarioRound)
            .filter(
                ScenarioRound.scenario_id == scenario_id,
                ScenarioRound.round_number == game.current_round,
            )
            .first()
        )
        if not current_round:
            raise ValueError("No active round to submit an order to")

        if order_quantity < 0:
            raise ValueError("Order quantity must be non-negative")

        inventory = (
            self.db.query(ScenarioUserInventory)
            .filter(ScenarioUserInventory.scenario_user_id == scenario_user_id)
            .first()
        )

        scenario_user_period = (
            self.db.query(ScenarioUserPeriod)
            .filter(
                ScenarioUserPeriod.scenario_user_id == scenario_user_id,
                ScenarioUserPeriod.round_id == current_round.id,
            )
            .first()
        )

        comment = self._truncate_comment(comment)

        if scenario_user_period:
            scenario_user_period.order_placed = order_quantity
            scenario_user_period.comment = comment
        else:
            starting_stock = getattr(inventory, "current_stock", 0) if inventory else 0
            starting_backlog = getattr(inventory, "backorders", 0) if inventory else 0
            scenario_user_period = ScenarioUserPeriod(
                scenario_user_id=scenario_user_id,
                round_id=current_round.id,
                order_placed=order_quantity,
                order_received=0,
                inventory_before=starting_stock,
                inventory_after=starting_stock,
                backorders_before=starting_backlog,
                backorders_after=starting_backlog,
                comment=comment,
            )
            self.db.add(scenario_user_period)

        scenario_user.last_order = order_quantity

        self.db.commit()
        self.db.refresh(scenario_user_period)
        return scenario_user_period

    def _apply_scenario_user_updates(
        self,
        game: Game,
        cfg: Dict[str, Any],
        assignments_payload: Any,
    ) -> None:
        try:
            assignments = [
                ScenarioUserAssignment.model_validate(entry)
                for entry in assignments_payload
            ]
        except ValidationError as exc:
            raise ValueError(f"Invalid scenario_user assignments: {exc}") from exc

        if not assignments:
            raise ValueError("At least one scenario_user assignment is required")

        scenario_user_lookup: Dict[int, ScenarioUser] = {scenario_user.id: scenario_user for scenario_user in list(game.scenario_users or [])}
        prior_assignments, role_assignments_upgraded = self._upgrade_json_value(
            getattr(game, "role_assignments", {}) or {},
            dict,
            default_factory=dict,
            context="MixedScenarioService._apply_scenario_user_updates role_assignments",
            field_name="role_assignments",
            game=game,
        )
        assignment_to_scenario_user: Dict[str, ScenarioUser] = {}
        for assignment_key, payload in prior_assignments.items():
            scenario_user_id = payload.get("scenario_user_id")
            if not scenario_user_id:
                continue
            scenario_user = scenario_user_lookup.get(scenario_user_id)
            if scenario_user:
                assignment_to_scenario_user[self._normalise_key(assignment_key)] = scenario_user
        if not assignment_to_scenario_user:
            assignment_to_scenario_user = {
                self._normalise_key(getattr(scenario_user.role, "value", scenario_user.role)):
                    scenario_user
                for scenario_user in list(game.scenario_users or [])
            }

        seen_assignments: Set[str] = set()
        config_assignments: List[Dict[str, Any]] = []
        role_assignments: Dict[str, Dict[str, Any]] = {}
        overrides, overrides_upgraded = self._upgrade_json_value(
            cfg.get("autonomy_overrides") or {},
            dict,
            default_factory=dict,
            context="MixedScenarioService._apply_scenario_user_updates autonomy_overrides",
            field_name="config",
            game=game,
        )

        for assignment in assignments:
            role_key = self._normalise_key(assignment.role.value)
            assignment_key_raw = assignment.assignment_key or assignment.role.value
            assignment_key = self._normalise_key(assignment_key_raw)
            if not assignment_key:
                assignment_key = role_key if role_key else f"assignment_{len(role_assignments) + 1}"
            seen_assignments.add(assignment_key)

            coverage_nodes: List[str] = []
            for node_token in assignment.node_keys or []:
                canonical = self._normalise_key(node_token)
                if canonical:
                    coverage_nodes.append(canonical)
            if not coverage_nodes and role_key:
                coverage_nodes = [role_key]

            config_assignments.append(
                {
                    "role": assignment.role.value,
                    "assignment_key": assignment_key,
                    "node_keys": coverage_nodes,
                    "scenario_user_type": assignment.scenario_user_type.value,
                    "user_id": assignment.user_id,
                    "strategy": assignment.strategy.value if assignment.strategy else None,
                    "can_see_demand": assignment.can_see_demand,
                    "llm_model": assignment.llm_model,
                    "autonomy_override_pct": assignment.autonomy_override_pct,
                }
            )

            db_role = ScenarioUserRole[assignment.role.name]
            is_ai = assignment.scenario_user_type == ScenarioUserType.AGENT
            strategy_value = (
                assignment.strategy.value
                if assignment.strategy is not None
                else None
            )

            scenario_user = assignment_to_scenario_user.get(assignment_key)
            if scenario_user is None:
                scenario_user = ScenarioUser(
                    scenario_id=game.id,
                    role=db_role,
                    name=f"{assignment.role.value.title()} ({'AI' if is_ai else 'Human'})",
                    is_ai=is_ai,
                    ai_strategy=strategy_value if is_ai else None,
                    can_see_demand=assignment.can_see_demand,
                    llm_model=assignment.llm_model if is_ai else None,
                    user_id=assignment.user_id if not is_ai else None,
                    type=ScenarioUserTypeDB.AI if is_ai else ScenarioUserTypeDB.HUMAN,
                )
                scenario_user.strategy = (
                    ScenarioUserStrategyDB.MANUAL if not is_ai else scenario_user.strategy
                )
                self.db.add(scenario_user)
                self.db.flush()
                assignment_to_scenario_user[assignment_key] = scenario_user
            else:
                scenario_user.role = db_role
                scenario_user.name = f"{assignment.role.value.title()} ({'AI' if is_ai else 'Human'})"
                scenario_user.is_ai = is_ai
                scenario_user.type = ScenarioUserTypeDB.AI if is_ai else ScenarioUserTypeDB.HUMAN
                scenario_user.ai_strategy = strategy_value if is_ai else None
                scenario_user.can_see_demand = assignment.can_see_demand
                scenario_user.llm_model = assignment.llm_model if is_ai else None
                scenario_user.user_id = assignment.user_id if not is_ai else None
                if not is_ai:
                    scenario_user.strategy = ScenarioUserStrategyDB.MANUAL

            scenario_user.node_key = coverage_nodes[0] if coverage_nodes else None

            if not scenario_user.inventory:
                inventory = ScenarioUserInventory(
                    scenario_user=scenario_user,
                    current_stock=12,
                    incoming_shipments=[],
                    backorders=0,
                )
                self.db.add(inventory)

            role_assignments[assignment_key] = {
                "scenario_user_id": scenario_user.id,
                "scenario_user_type": assignment.scenario_user_type.value,
                "strategy": strategy_value if is_ai else None,
                "user_id": assignment.user_id if not is_ai else None,
                "can_see_demand": assignment.can_see_demand,
                "llm_model": assignment.llm_model if is_ai else None,
                "autonomy_override_pct": assignment.autonomy_override_pct,
                "role": assignment.role.value,
                "node_keys": coverage_nodes,
            }

            if is_ai:
                agent_type = AgentType(role_key)
                strategy_token = (strategy_value or "naive").lower()
                try:
                    strategy_enum = AgentStrategyEnum(strategy_token)
                except ValueError:
                    if strategy_token.startswith("llm"):
                        strategy_enum = AgentStrategyEnum.LLM
                    else:
                        strategy_enum = AgentStrategyEnum.NAIVE

                override_pct = (
                    assignment.autonomy_override_pct
                    if strategy_enum
                    in (
                        AgentStrategyEnum.AUTONOMY_DTCE_CENTRAL,
                        AgentStrategyEnum.LLM_SUPERVISED,
                    )
                    else None
                )
                if override_pct is not None:
                    overrides[assignment_key] = override_pct
                else:
                    overrides.pop(assignment_key, None)

                self.agent_manager.set_agent_strategy(
                    agent_type,
                    strategy_enum,
                    llm_model=assignment.llm_model,
                    override_pct=override_pct,
                )
            else:
                overrides.pop(assignment_key, None)

        # Remove scenario_users no longer present (only for games not yet started)
        for assignment_key, scenario_user in list(assignment_to_scenario_user.items()):
            if assignment_key in seen_assignments:
                continue
            overrides.pop(assignment_key, None)
            if game.status == GameStatusDB.CREATED:
                self.db.delete(scenario_user)

        cfg["player_assignments"] = config_assignments
        if overrides:
            cfg["autonomy_overrides"] = overrides
        else:
            cfg.pop("autonomy_overrides", None)
        if overrides_upgraded:
            flag_modified(game, "config")

        game.role_assignments = role_assignments
        if role_assignments_upgraded:
            flag_modified(game, "role_assignments")
    
    def start_game(self, scenario_id: int, debug_logging: bool = False) -> Game:
        """Start a game, initializing the first round."""
        game = self.db.query(Game).filter(Game.id == scenario_id).first()
        if not game:
            raise ValueError("Game not found")
            
        if MixedScenarioService._map_status_to_schema(game.status) != GameStatus.CREATED:
            raise ValueError("Game has already started")
            
        # Update game status
        game.status = GameStatusDB.STARTED
        game.current_round = 0  # Will be incremented in start_new_round
        game.started_at = datetime.utcnow()

        # Initialize simple engine state if not present
        cfg = self._coerce_dict(getattr(game, "config", {}) or {})
        previous_notices = cfg.get("startup_notices")
        cfg["startup_notices"] = []
        config_upgraded = previous_notices not in (None, [])
        debug_cfg = cfg.get("debug_logging")
        if not isinstance(debug_cfg, dict):
            debug_cfg = {}
        previous_enabled = bool(debug_cfg.get("enabled"))
        debug_cfg["enabled"] = bool(debug_logging)
        if previous_enabled != debug_cfg["enabled"]:
            config_upgraded = True
        cfg["debug_logging"] = debug_cfg
        if debug_cfg.get("enabled"):
            # Ensure a debug log file is prepared up-front so initial conditions are captured consistently.
            try:
                ensure_debug_log_file(cfg, game)
            except Exception:
                logger.debug("Unable to prepare debug log file during start_game for game %s", game.id)

        # If the game was restarted but has lingering rounds/history, clear them.
        existing_rounds = (
            self.db.query(ScenarioRound).filter(ScenarioRound.scenario_id == game.id).all()
        )
        if existing_rounds:
            for r in existing_rounds:
                self.db.delete(r)
            cfg["history"] = []
            game.current_round = 0
            flag_modified(game, "config")

        demand_pattern_cfg, demand_pattern_changed = self._upgrade_config_entry(
            cfg,
            'demand_pattern',
            expected_type=dict,
            default_factory=dict,
            context="MixedScenarioService.start_game",
        )
        if not demand_pattern_cfg:
            demand_pattern_cfg, pattern_upgraded = self._upgrade_json_value(
                getattr(game, 'demand_pattern', {}) or DEFAULT_DEMAND_PATTERN,
                dict,
                default_factory=lambda: dict(DEFAULT_DEMAND_PATTERN),
                context="MixedScenarioService.start_game demand_pattern fallback",
                field_name="demand_pattern",
                game=game,
            )
            demand_pattern_changed = demand_pattern_changed or pattern_upgraded
        cfg['demand_pattern'] = demand_pattern_cfg or dict(DEFAULT_DEMAND_PATTERN)

        sc_snapshot: Optional[Dict[str, Any]] = None

        def _ensure_snapshot() -> Optional[Dict[str, Any]]:
            nonlocal sc_snapshot
            if sc_snapshot is None:
                sc_snapshot = self._supply_chain_snapshot(cfg.get('supply_chain_config_id'))
            return sc_snapshot

        if not cfg.get('market_demands'):
            snapshot = _ensure_snapshot()
            if snapshot:
                market_payload = snapshot.get('market_demands')
                if market_payload:
                    cfg['market_demands'] = MixedScenarioService._json_clone(market_payload)
                if not cfg.get('market_demand_nodes') and snapshot.get('market_nodes'):
                    cfg['market_demand_nodes'] = list(snapshot.get('market_nodes') or [])
        if not cfg.get('items'):
            snapshot = _ensure_snapshot()
            if snapshot and snapshot.get('items'):
                cfg['items'] = MixedScenarioService._json_clone(snapshot.get('items'))
        if not cfg.get('markets'):
            snapshot = _ensure_snapshot()
            if snapshot and snapshot.get('markets'):
                cfg['markets'] = MixedScenarioService._json_clone(snapshot.get('markets'))

        raw_policies, policies_upgraded = self._upgrade_config_entry(
            cfg,
            'node_policies',
            expected_type=dict,
            default_factory=dict,
            context="MixedScenarioService.start_game",
        )
        if not raw_policies:
            fallback_config = self._fallback_game_config_from_supply_chain(
                cfg,
                game,
                snapshot=_ensure_snapshot(),
            )

            if fallback_config and fallback_config.get("node_policies"):
                raw_policies = fallback_config.get("node_policies") or {}
                policies_upgraded = True
                try:
                    MixedScenarioService._record_startup_notice(
                        cfg,
                        game,
                        "Node policies were regenerated from the linked supply chain configuration because they were missing from the game setup.",
                        details={
                            "supply_chain_config_id": cfg.get("supply_chain_config_id"),
                            "supply_chain_name": cfg.get("supply_chain_name"),
                            "using_snapshot": bool(_ensure_snapshot()),
                            "fallback_keys": sorted(fallback_config.keys()),
                        },
                    )
                except Exception:
                    logger.debug(
                        "Unable to record startup fallback notice for game %s", getattr(game, "id", "?")
                    )
                for key in (
                    "lanes",
                    "node_types",
                    "node_sequence",
                    "market_demands",
                    "items",
                    "markets",
                    "market_demand_nodes",
                ):
                    if not cfg.get(key) and fallback_config.get(key):
                        cfg[key] = MixedScenarioService._json_clone(fallback_config.get(key))
            else:
                error_message = (
                    "Game configuration is missing node_policies; reseed the supply-chain configuration "
                    "so every node includes lead times and inventory parameters."
                )
                try:
                    MixedScenarioService._record_startup_notice(
                        cfg,
                        game,
                        error_message,
                        details={
                            "supply_chain_config_id": cfg.get("supply_chain_config_id"),
                            "supply_chain_name": cfg.get("supply_chain_name"),
                            "using_snapshot": bool(_ensure_snapshot()),
                        },
                    )
                except Exception:
                    logger.debug(
                        "Unable to record startup failure notice for game %s", getattr(game, "id", "?")
                    )
                raise ValueError(error_message)
        node_policies = {}
        for name, policy in raw_policies.items():
            normalised = dict(policy)
            if 'partial_order_fulfillment' not in normalised:
                normalised['partial_order_fulfillment'] = True
            node_policies[self._normalise_key(name)] = normalised
        cfg['node_policies'] = node_policies

        node_types = self._extract_node_types(cfg)
        raw_types, node_types_upgraded = self._upgrade_config_entry(
            cfg,
            'node_types',
            expected_type=dict,
            default_factory=dict,
            context="MixedScenarioService.start_game",
        )
        for name, node_type in raw_types.items():
            key = self._normalise_key(name)
            if not key:
                continue
            node_types[key] = self._normalise_node_type(node_type)
        cfg['node_types'] = node_types

        lanes_raw, lanes_upgraded = self._upgrade_config_entry(
            cfg,
            'lanes',
            expected_type=list,
            default_factory=list,
            context="MixedScenarioService.start_game",
            allow_map_to_list=True,
        )
        lanes = [lane for lane in lanes_raw if isinstance(lane, dict)]
        cfg['lanes'] = lanes
        self._validate_lanes(node_policies, lanes)

        engine: Dict[str, Dict[str, Any]] = {}
        lane_views = self._build_lane_views(node_policies, cfg)
        cfg['node_types'] = lane_views.get('node_types', node_types)
        node_types_map = lane_views.get('node_types', {})
        node_sequence_raw, node_sequence_upgraded = self._upgrade_config_entry(
            cfg,
            'node_sequence',
            expected_type=list,
            default_factory=list,
            context="MixedScenarioService.start_game",
            allow_map_to_list=True,
        )
        node_sequence = lane_views.get("node_sequence") or node_sequence_raw
        if node_sequence:
            cfg["node_sequence"] = node_sequence

        if any([
            config_upgraded,
            demand_pattern_changed,
            policies_upgraded,
            node_types_upgraded,
            lanes_upgraded,
            node_sequence_upgraded,
        ]):
            flag_modified(game, "config")
        pattern_for_stats = cfg.get('demand_pattern') or DEFAULT_DEMAND_PATTERN
        mean_demand, variance = estimate_demand_stats(pattern_for_stats)
        steady_quantity = MixedScenarioService._baseline_flow(mean_demand)
        cfg['demand_statistics'] = {
            'mean': mean_demand,
            'variance': variance,
        }
        seed_quantity = max(1, int(round(mean_demand))) if mean_demand is not None else steady_quantity
        cfg['initial_pipeline_shipment'] = steady_quantity
        cfg['initial_pipeline_orders'] = steady_quantity
        market_item_profiles = MixedScenarioService._build_market_item_profiles(cfg, lane_views)
        node_item_baselines = MixedScenarioService._propagate_item_profiles(
            lane_views.get('orders_map', {}),
            market_item_profiles,
        )
        cfg['initial_node_item_baselines'] = MixedScenarioService._json_clone(node_item_baselines)
        configured_bom = cfg.get('bill_of_materials') if isinstance(cfg.get('bill_of_materials'), dict) else {}
        (
            normalised_bom,
            component_registry,
            component_sources,
        ) = MixedScenarioService._derive_component_metadata(
            lane_views,
            configured_bom,
            node_item_baselines,
        )
        cfg['bill_of_materials'] = normalised_bom
        cfg['component_registry'] = component_registry
        cfg['component_sources'] = component_sources
        orders_map = lane_views.get('orders_map', {})
        shipments_map = lane_views.get('shipments_map', {})
        lane_lookup = lane_views.get('lane_lookup', {})

        # Reseed using unified inbound queues and log initial conditions only
        cfg = self._reseed_engine_state(cfg, lane_views, mean_demand, variance, game)
        engine = cfg.get("engine_state", {})
        cfg['initial_state'] = {}

        # Emit initial-condition snapshots in DAG / node_sequence order so logs
        # follow the material flow (upstream → downstream).
        nodes_to_log: List[str] = []
        if lane_views.get("node_sequence"):
            nodes_to_log = list(lane_views["node_sequence"])
        else:
            nodes_to_log = list(lane_views.get("all_nodes", []))

        for node in nodes_to_log:
            policy = MixedScenarioService._policy_for_node(node_policies, node)
            supply_leadtime = max(0, int(policy.get('supply_leadtime', 0)))
            order_leadtime = max(0, int(policy.get('order_leadtime', 0)))

            calc_debug: Dict[str, Any] = {}

            def _capture_initial(details: Dict[str, Any]) -> None:
                if isinstance(details, dict):
                    calc_debug.update(details)

            MixedScenarioService._compute_initial_conditions(
                mean_demand,
                variance,
                order_leadtime=order_leadtime,
                supply_leadtime=supply_leadtime,
                debug_hook=_capture_initial,
            )

            state = engine.get(node, {})
            self._log_initialisation_debug(
                cfg,
                game,
                node_label=node,
                calculation_details=calc_debug,
                state=state,
            )

            cfg['initial_state'][node] = {
                "inventory": int(state.get("inventory", 0) or 0),
                "backlog": int(state.get("backlog", 0) or 0),
                "on_order": int(state.get("on_order", 0) or 0),
                "base_stock": int(state.get("base_stock", 0) or 0),
                "inventory_by_item": MixedScenarioService._json_clone(state.get("inventory_by_item") or {}),
                "backlog_by_item": MixedScenarioService._json_clone(state.get("backlog_by_item") or {}),
                "on_order_by_item": MixedScenarioService._json_clone(state.get("on_order_by_item") or {}),
                "base_stock_by_item": MixedScenarioService._json_clone(state.get("base_stock_by_item") or {}),
                "inbound_demand": MixedScenarioService._json_clone(state.get("inbound_demand") or state.get("inbound_orders") or []),
                "inbound_supply": MixedScenarioService._json_clone(state.get("inbound_supply") or []),
            }

        # Emit a round-0 snapshot so initial conditions always appear in debug logs.
        try:
            items = cfg.get("items") or []
            item_name_by_id = {
                str(itm.get("id") if isinstance(itm, dict) else getattr(itm, "id", None)): (
                    itm.get("name") if isinstance(itm, dict) else getattr(itm, "name", None)
                )
                for itm in items
                if (itm.get("id") if isinstance(itm, dict) else getattr(itm, "id", None)) is not None
            }

            def _name_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
                if not isinstance(entry, dict):
                    return entry
                clone = dict(entry)
                itm = clone.get("product_id")
                if itm is not None and str(itm) in item_name_by_id:
                    clone["item_name"] = item_name_by_id[str(itm)]
                return clone

            initial_entries: List[Dict[str, Any]] = []
            for node in lane_views["all_nodes"]:
                state = engine.get(node, {})
                initial_entries.append(
                    {
                        "node": node,
                        "info_sent": {"initial_state": True},
                        "reply": {
                            "inbound_demand": [_name_entry(o) for o in state.get("inbound_demand") or state.get("inbound_orders") or []],
                            "inbound_supply": [_name_entry(s) for s in state.get("inbound_supply") or []],
                        },
                        "ending_state": {
                            "inventory": state.get("inventory"),
                            "backlog": state.get("backlog"),
                            "inventory_by_item": state.get("inventory_by_item"),
                            "backlog_by_item": state.get("backlog_by_item"),
                        },
                    }
                )
            append_debug_round_log(
                cfg,
                game,
                round_number=0,
                timestamp=datetime.utcnow(),
                entries=initial_entries,
            )
        except Exception:
            logger.debug("Unable to write initial debug snapshot for game %s", game.id)
        game.config = cfg
        
        progression_mode = str(cfg.get("progression_mode") or "supervised").lower()

        # If every scenario_user is an AI but the progression mode was not set to
        # unsupervised, automatically enable auto-play so seeded showcase games
        # don't stall after the first round.
        if progression_mode != "unsupervised":
            scenario_users = (
                self.db.query(ScenarioUser)
                .filter(ScenarioUser.scenario_id == game.id)
                .all()
            )
            if scenario_users and all(p.is_ai for p in scenario_users):
                progression_mode = "unsupervised"
                cfg["progression_mode"] = progression_mode
                flag_modified(game, "config")

        # Persist the initialized engine state before optionally auto-playing
        self.db.commit()
        self.db.refresh(game)

        if progression_mode == "unsupervised":
            try:
                self._auto_play_unsupervised(game)
                self.db.refresh(game)
            except Exception:  # noqa: BLE001
                logger.exception("Auto-play failed for game %s", scenario_id)

        return game
    
    def stop_game(self, scenario_id: int) -> Game:
        """Stop a game that is in progress."""
        game = self.db.query(Game).filter(Game.id == scenario_id).first()
        if not game:
            raise ValueError("Game not found")
            
        if MixedScenarioService._map_status_to_schema(game.status) != GameStatus.IN_PROGRESS:
            raise ValueError("Game is not in progress")
            
        game.status = GameStatusDB.FINISHED
        game.completed_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(game)
        return game

    def delete_game(self, scenario_id: int, current_user: User) -> Dict[str, Any]:
        """Delete a game if the requester is allowed to manage it."""
        game = self.db.query(Game).filter(Game.id == scenario_id).first()
        if not game:
            raise ValueError("Game not found")

        user_type = self._resolve_user_type(current_user)
        if not current_user.is_superuser and user_type != UserTypeEnum.SYSTEM_ADMIN:
            tenant_id = getattr(current_user, "tenant_id", None)
            owns_tenant = tenant_id and tenant_id == getattr(game, "tenant_id", tenant_id)
            config_tenant = None
            cfg, _ = self._upgrade_json_value(
                getattr(game, "config", {}) or {},
                dict,
                default_factory=dict,
                context="MixedScenarioService.delete_game config",
                field_name="config",
                game=game,
            )
            if cfg:
                config_tenant = cfg.get("tenant_id")
            if not owns_tenant and config_tenant not in (tenant_id, None):
                raise PermissionError("Not enough permissions to delete this game")

        self.db.delete(game)
        self.db.commit()
        return {"status": "deleted", "scenario_id": scenario_id}

    def _auto_play_unsupervised(
        self,
        game: Game,
        *,
        sleep_seconds: float = 0.05,
        iteration_limit: int = 2048,
    ) -> None:
        """Advance an AI-only unsupervised game until completion."""

        scenario_users = (
            self.db.query(ScenarioUser)
            .filter(ScenarioUser.scenario_id == game.id)
            .all()
        )
        if any(not scenario_user.is_ai for scenario_user in scenario_users):
            return

        iterations = 0
        while True:
            iterations += 1
            if iteration_limit and iterations > iteration_limit:
                logger.warning(
                    "Auto-play stopped for game %s after reaching the iteration limit",
                    game.id,
                )
                break

            self.db.expire_all()
            current = self.db.query(Game).filter(Game.id == game.id).first()
            if not current:
                break
            if current.status == GameStatusDB.FINISHED:
                break

            round_record = self.start_new_round(current)
            if round_record is None:
                break

            self.db.refresh(current)
            if current.status == GameStatusDB.FINISHED:
                break

            if sleep_seconds:
                time.sleep(sleep_seconds)
    
    def start_new_round(self, game: Union[int, Game]) -> Optional[ScenarioRound]:
        """
        Advance the game to the next round.

        This method orchestrates the simulation logic for a single round using:
        - SC Planning Mode (if use_sc_planning=True) - Full AWS SC integration
        - DAG Sequential Mode (if use_dag_sequential=True) - Dual-decision gameplay
        - Legacy Simulation Engine (default) - Original single-decision mode

        DAG Sequential Mode (Phase 1):
        1. Initialize round in FULFILLMENT phase
        2. ScenarioUsers fulfill downstream orders (ATP-based) in downstream→upstream order
        3. Transition to REPLENISHMENT phase when all fulfilled
        4. ScenarioUsers order from upstream
        5. Transition to COMPLETED, advance round

        SC Mode:
        1. Sync game state to SC tables (inventory, forecast)
        2. Run SC 3-step planning process
        3. Convert supply plans to scenario_user orders
        4. Update game state

        Legacy Mode:
        1. Initialize round context and load state
        2. Preprocess queues (arrivals, matured orders)
        3. Process node echelon (demand, fulfillment, replenishment)
        4. Trigger AI scenario_users
        5. Finalize round (persist state)
        """
        # 1. Resolve Game Object
        if isinstance(game, int):
            game_obj = self.db.query(Game).filter(Game.id == game).first()
        else:
            game_obj = game

        if not game_obj:
            return None

        # 2. Check Game Status
        if game_obj.status == GameStatusDB.FINISHED:
            return None

        # 3. Route to appropriate execution mode
        # Priority: SC Execution > SC Planning > DAG Sequential > Legacy
        use_sc_execution = (game_obj.config or {}).get('use_sc_execution', False)
        if use_sc_execution:
            return self._start_round_sc_execution(game_obj)
        elif game_obj.use_sc_planning:
            return self._start_round_sc_planning(game_obj)
        elif game_obj.use_dag_sequential:
            return self._start_round_dag_sequential(game_obj)
        else:
            return self._start_round_legacy(game_obj)

    def _start_round_sc_execution(self, game_obj: Game) -> Optional[ScenarioRound]:
        """
        SC Execution Mode round processing.

        Drives round execution entirely through standard AWS SC entities:
        InvLevel, InboundOrderLine, OutboundOrderLine, SourcingRules, PurchaseOrder.

        This replaces engine.py logic — the Beer Game is just a special case of
        iterative SC execution over a 4-site linear DAG.
        """
        from app.services.sc_execution.simulation_executor import SimulationExecutor

        if not game_obj.supply_chain_config_id:
            logger.error(
                f"Game {game_obj.id} has no supply_chain_config_id - cannot use SC execution"
            )
            return None

        total_rounds = game_obj.max_rounds or 52

        latest_round: Optional[ScenarioRound] = (
            self.db.query(ScenarioRound)
            .filter(ScenarioRound.scenario_id == game_obj.id)
            .order_by(ScenarioRound.round_number.desc())
            .first()
        )
        if latest_round:
            if latest_round.completed_at or latest_round.ended_at or latest_round.is_completed:
                target_round = latest_round.round_number + 1
            else:
                target_round = latest_round.round_number
        else:
            current_round_value = game_obj.current_round or 0
            target_round = current_round_value if current_round_value > 0 else 1

        if target_round > total_rounds:
            game_obj.status = GameStatusDB.FINISHED
            self.db.commit()
            return None

        game_obj.current_round = target_round
        self.db.add(game_obj)
        self.db.commit()

        logger.info(f"🚀 SC Execution Mode - Game {game_obj.id}, Round {target_round}")

        # Initialize SC state on round 1 (create InvLevel records)
        if target_round == 1:
            from app.services.sc_execution.simulation_executor import SimulationExecutor as _SE
            _init_executor = _SE(db=self.db, scenario=game_obj)
            _init_executor._load_config()
            _init_executor.initialize_game(
                scenario_id=game_obj.id,
                config_id=game_obj.supply_chain_config_id,
            )
            logger.info(f"  Initialized SC state for game {game_obj.id}")

        # Market demand for this round
        market_demand = self._get_current_demand(game_obj, target_round)

        # Agent order decisions (one qty per role/site)
        agent_decisions = self._get_sc_execution_agent_decisions(game_obj, target_round)

        # Execute round via SC execution layer
        executor = SimulationExecutor(db=self.db, scenario=game_obj)
        executor._load_config()
        round_result = executor.execute_round(
            round_number=target_round,
            agent_decisions=agent_decisions,
            market_demand=market_demand,
        )

        # Create ScenarioRound record
        round_record = ScenarioRound(
            scenario_id=game_obj.id,
            round_number=target_round,
            customer_demand=int(market_demand),
            is_completed=True,
            started_at=datetime.datetime.utcnow(),
            completed_at=datetime.datetime.utcnow(),
            ended_at=datetime.datetime.utcnow(),
        )
        self.db.add(round_record)
        self.db.flush()

        # Persist per-user period records from round result
        self._persist_sc_execution_period(game_obj, round_record, round_result)

        self.db.commit()
        logger.info(f"✅ SC Execution Round {target_round} Complete")
        return round_record

    def _get_sc_execution_agent_decisions(
        self, game_obj: Game, round_number: int
    ) -> Dict[str, float]:
        """
        Compute agent order quantities for an SC execution round.

        Uses a base-stock policy: order = demand + max(0, safety_stock - on_hand).
        For each ScenarioUser, matches their role to a Site by name (case-insensitive)
        and reads current InvLevel to compute the order quantity.

        Args:
            game_obj: Game/Scenario instance
            round_number: Current round number

        Returns:
            Dict mapping site name → order quantity
        """
        from app.models.sc_entities import InvLevel
        from app.models.supply_chain_config import Site

        demand = self._get_current_demand(game_obj, round_number)

        scenario_users = (
            self.db.query(ScenarioUser)
            .filter(ScenarioUser.scenario_id == game_obj.id)
            .all()
        )

        sites = (
            self.db.query(Site)
            .filter(Site.config_id == game_obj.supply_chain_config_id)
            .all()
        )
        site_by_name_upper = {s.name.upper(): s for s in sites}

        agent_decisions: Dict[str, float] = {}
        for su in scenario_users:
            role_str = su.role.value if hasattr(su.role, 'value') else str(su.role)
            site = site_by_name_upper.get(role_str.upper())

            order_qty = demand
            if site:
                inv = (
                    self.db.query(InvLevel)
                    .filter(InvLevel.site_id == site.id)
                    .order_by(InvLevel.inventory_date.desc())
                    .first()
                )
                if inv and inv.on_hand_qty is not None:
                    # Base-stock: fill gap to safety stock then cover demand
                    safety_stock = getattr(inv, 'safety_stock_qty', None) or 4.0
                    gap = max(0.0, safety_stock - (inv.on_hand_qty or 0.0))
                    order_qty = demand + gap

            # Key is the site name (as used by SimulationExecutor)
            site_name = site.name if site else role_str.capitalize()
            agent_decisions[site_name] = float(order_qty)

        return agent_decisions

    def _persist_sc_execution_period(
        self,
        game_obj: Game,
        round_record: ScenarioRound,
        round_result: Dict,
    ) -> None:
        """
        Persist ScenarioUserPeriod records from a SimulationExecutor round result.

        Maps site-level cost/inventory data back to ScenarioUser rows so the
        standard analytics (costs, inventory charts, bullwhip metrics) work
        without changes.

        Args:
            game_obj: Game/Scenario instance
            round_record: The ScenarioRound just created for this round
            round_result: Dict returned by SimulationExecutor.execute_round()
        """
        from app.models.supply_chain_config import Site

        scenario_users = (
            self.db.query(ScenarioUser)
            .filter(ScenarioUser.scenario_id == game_obj.id)
            .all()
        )

        sites = (
            self.db.query(Site)
            .filter(Site.config_id == game_obj.supply_chain_config_id)
            .all()
        )
        site_by_id = {s.id: s for s in sites}
        site_by_name_upper = {s.name.upper(): s for s in sites}

        # Build cost lookup: site_id (int) → cost dict
        site_costs_by_id: Dict[int, Dict] = {}
        for sc in round_result.get("steps", {}).get("costs", {}).get("site_costs", []):
            try:
                site_costs_by_id[int(sc["site_id"])] = sc
            except (KeyError, TypeError, ValueError):
                pass

        # Build inventory snapshot lookup: site_id (str) → state dict
        state_sites = round_result.get("state_snapshot", {}).get("sites", {})

        agent_decisions = round_result.get("steps", {}).get("agent_decisions", {})

        for su in scenario_users:
            role_str = su.role.value if hasattr(su.role, 'value') else str(su.role)
            site = site_by_name_upper.get(role_str.upper())
            if not site:
                continue

            site_cost = site_costs_by_id.get(site.id, {})
            site_state = state_sites.get(str(site.id), state_sites.get(site.id, {}))

            on_hand = float(site_state.get("on_hand_qty", 0.0))
            backorder = float(site_state.get("backorder_qty", 0.0))
            order_placed = int(agent_decisions.get(site.name, 0))

            period = ScenarioUserPeriod(
                scenario_user_id=su.id,
                scenario_round_id=round_record.id,
                order_placed=order_placed,
                order_received=0,
                inventory_before=int(on_hand),
                inventory_after=int(on_hand),
                backorders_before=int(backorder),
                backorders_after=int(backorder),
                holding_cost=float(site_cost.get("holding_cost", 0.0)),
                backorder_cost=float(site_cost.get("backlog_cost", 0.0)),
                total_cost=float(site_cost.get("total_cost", 0.0)),
            )
            self.db.add(period)

    def _start_round_legacy(self, game_obj: Game) -> Optional[ScenarioRound]:
        """
        Legacy Simulation Engine round processing.

        Uses the original engine.py logic with SupplyChainLine and Node classes.
        """
        total_rounds = game_obj.max_rounds or 50  # Default

        # Determine target round based on existing round records
        latest_round: Optional[ScenarioRound] = (
            self.db.query(ScenarioRound)
            .filter(ScenarioRound.scenario_id == game_obj.id)
            .order_by(ScenarioRound.round_number.desc())
            .first()
        )
        if latest_round:
            if latest_round.completed_at or latest_round.ended_at or latest_round.is_completed:
                target_round = latest_round.round_number + 1
            else:
                target_round = latest_round.round_number
        else:
            # If a caller already primed current_round, respect it; otherwise start at 1
            current_round_value = game_obj.current_round or 0
            target_round = current_round_value if current_round_value > 0 else 1

        if target_round > total_rounds:
            game_obj.status = GameStatusDB.FINISHED
            self.db.commit()
            return None

        game_obj.current_round = target_round
        self.db.add(game_obj)

        # When starting from round 1 (or reset), reseed a clean engine state
        if target_round == 1:
            cfg = game_obj.config or {}
            node_policies = cfg.get("node_policies", {})
            lane_views = self._build_lane_views(node_policies, cfg)
            stats = cfg.get("demand_statistics") or {}
            mean_demand = stats.get("mean")
            variance = stats.get("variance", 0.0)
            if mean_demand is None:
                pattern = cfg.get("demand_pattern") or game_obj.demand_pattern or DEFAULT_DEMAND_PATTERN
                mean_demand, variance = estimate_demand_stats(pattern)
            cfg = self._reseed_engine_state(cfg, lane_views, mean_demand, variance, game_obj)
            game_obj.config = cfg
            flag_modified(game_obj, "config")

        # Initialize Round
        context = self._initialize_round(game_obj, round_number=target_round)
        if not context:
            return None

        # Preprocess Queues
        self._preprocess_queues(context)

        # Process Node Echelon
        self._process_node_echelon(context)

        # AI ScenarioUsers
        if context.round_record:
            self.process_ai_scenario_users(game_obj, context.round_record, context)

        # Finalize Round
        self._finalize_round(game_obj, context)

        return context.round_record

    def _start_round_sc_planning(self, game_obj: Game) -> Optional[ScenarioRound]:
        """
        Supply Chain Planning Mode round processing.

        Uses SC 3-step planning process instead of legacy engine:
        1. Sync game state to SC tables (inventory, forecast)
        2. Run SupplyChainPlanner (demand → targets → net requirements)
        3. Convert supply plans to scenario_user orders
        4. Update game state and persist

        This method bridges simulation concepts to SC Data Model using
        the SimulationToSCAdapter.
        """
        # Import here to avoid circular dependencies
        from app.services.sc_planning.planner import SupplyChainPlanner
        from app.services.sc_planning.simulation_adapter import SimulationToSCAdapter
        from app.db.session import SessionLocal

        # Validate required fields
        if not game_obj.tenant_id:
            logger.error(f"Game {game_obj.id} has no tenant_id - cannot use SC planning")
            return None

        if not game_obj.supply_chain_config_id:
            logger.error(f"Game {game_obj.id} has no supply_chain_config_id - cannot use SC planning")
            return None

        # Determine target round
        total_rounds = game_obj.max_rounds or 50
        latest_round: Optional[ScenarioRound] = (
            self.db.query(ScenarioRound)
            .filter(ScenarioRound.scenario_id == game_obj.id)
            .order_by(ScenarioRound.round_number.desc())
            .first()
        )

        if latest_round:
            if latest_round.completed_at or latest_round.ended_at or latest_round.is_completed:
                target_round = latest_round.round_number + 1
            else:
                target_round = latest_round.round_number
        else:
            current_round_value = game_obj.current_round or 0
            target_round = current_round_value if current_round_value > 0 else 1

        if target_round > total_rounds:
            game_obj.status = GameStatusDB.FINISHED
            self.db.commit()
            return None

        game_obj.current_round = target_round
        self.db.add(game_obj)
        self.db.commit()

        logger.info(f"🚀 SC Planning Mode - Game {game_obj.id}, Round {target_round}")

        # Run async planning logic
        round_record = asyncio.run(self._run_sc_planning_async(game_obj, target_round))

        return round_record

    async def _run_sc_planning_async(self, game_obj: Game, target_round: int) -> Optional[ScenarioRound]:
        """
        Async helper for SC EXECUTION workflow (REFACTORED for execution, not planning).

        Simulation is an EXECUTION scenario, not a planning scenario.
        Planning (forecasts, inv policies) happens BEFORE the game starts.
        Execution (work orders, fulfillment) happens DURING game rounds.

        This method runs the full SC execution cycle:
        1. Sync current game state (inventory, backlog) → inv_level
        2. Record customer demand → outbound_order_line
        3. Process deliveries from previous orders → update inventory
        4. Get scenario_user orders from agents/humans → inbound_order_line (work orders)
        5. Execute simulation round with simulation engine
        6. Create work orders for next round
        """
        from app.services.sc_planning.simulation_execution_adapter import SimulationExecutionAdapter
        from app.db.session import async_session_factory

        async with async_session_factory() as db:
            # Refresh game object in async session
            from sqlalchemy import select
            result = await db.execute(select(Game).filter(Game.id == game_obj.id))
            game = result.scalar_one()

            logger.info(f"🚀 SC Execution Mode - Game {game.id}, Round {target_round}")

            # Step 1: Initialize Execution Adapter (Phase 3: with cache enabled)
            logger.info(f"  Step 1: Initializing SimulationExecutionAdapter (with cache)...")
            adapter = SimulationExecutionAdapter(game, db, use_cache=True)

            # Load cache once at game start (Phase 3 optimization)
            cache_counts = await adapter.cache.load()
            logger.info(f"  ✓ Cache loaded: {cache_counts}")

            # Phase 3 Sprint 2: Reset capacity at start of new period
            use_capacity = game.config.get('use_capacity_constraints', False)
            if use_capacity and target_round % game.config.get('capacity_reset_period', 1) == 0:
                reset_count = await adapter.reset_period_capacity()
                logger.info(f"  ✓ Reset {reset_count} capacity counters for new period")

            # Step 2: Sync Inventory Levels (execution snapshot)
            logger.info(f"  Step 2: Syncing inventory levels...")
            inv_records = await adapter.sync_inventory_levels(target_round)
            logger.info(f"  ✓ Synced {inv_records} inventory records")

            # Step 3: Record Customer Demand (outbound orders)
            logger.info(f"  Step 3: Recording customer demand...")
            # Get demand from demand pattern or game state
            demand_qty = self._get_current_demand(game, target_round)
            if demand_qty > 0:
                await adapter.record_customer_demand('Retailer', demand_qty, target_round)
                logger.info(f"  ✓ Recorded customer demand: {demand_qty}")

            # Step 4: Process Deliveries (inbound orders arriving this round)
            logger.info(f"  Step 4: Processing deliveries...")
            deliveries = await adapter.process_deliveries(target_round)
            logger.info(f"  ✓ Processed {len(deliveries)} deliveries")

            # Step 5: Run Legacy Simulation Engine (for now)
            # This calculates new orders based on current state
            # In future, this could be replaced with SC logic
            logger.info(f"  Step 5: Running game simulation...")

            # Get scenario_user orders (from agents/humans)
            # For now, use naive strategy as placeholder
            # TODO: Replace with actual agent/human decision logic
            scenario_user_orders = await self._get_scenario_user_orders_for_round(game, target_round, db)
            logger.info(f"  ✓ Got {len(scenario_user_orders)} scenario_user orders")

            # Step 6: Create Work Orders (Phase 3: Sprint 1 batch + Sprint 2 capacity + Sprint 3 aggregation)
            # Check game configuration flags
            use_capacity = game.config.get('use_capacity_constraints', False)
            use_aggregation = game.config.get('use_order_aggregation', False)

            if use_aggregation:
                # Sprint 3: Order aggregation (with optional capacity enforcement)
                logger.info(f"  Step 6: Creating work orders (AGGREGATION{' + CAPACITY' if use_capacity else ''})...")
                result = await adapter.create_work_orders_with_aggregation(
                    scenario_user_orders,
                    target_round,
                    use_capacity=use_capacity
                )
                work_orders_created = len(result['created'])

                # Log aggregation details
                if result['aggregated']:
                    logger.info(f"    🔀 Aggregated {len(result['aggregated'])} order groups")
                if result['cost_savings'] > 0:
                    logger.info(f"    💰 Cost savings: ${result['cost_savings']:.2f}")
                if result['queued']:
                    logger.warning(f"    ⚠️  {len(result['queued'])} orders queued")
                if result['capacity_used']:
                    logger.info(f"    Capacity used: {result['capacity_used']}")

                logger.info(f"  ✓ Created {work_orders_created} work orders (AGGREGATION{' + CAPACITY' if use_capacity else ''})")

            elif use_capacity:
                # Sprint 2: Capacity constraints only
                logger.info(f"  Step 6: Creating work orders (BATCH + CAPACITY)...")
                result = await adapter.create_work_orders_with_capacity(scenario_user_orders, target_round)
                work_orders_created = len(result['created'])

                # Log capacity details
                if result['queued']:
                    logger.warning(f"    ⚠️  {len(result['queued'])} orders queued due to capacity constraints")
                if result['capacity_used']:
                    logger.info(f"    Capacity used: {result['capacity_used']}")

                logger.info(f"  ✓ Created {work_orders_created} work orders (BATCH + CAPACITY)")
            else:
                # Sprint 1: Batch operations only
                logger.info(f"  Step 6: Creating work orders (BATCH)...")
                work_orders_created = await adapter.create_work_orders_batch(scenario_user_orders, target_round)
                logger.info(f"  ✓ Created {work_orders_created} work orders (BATCH)")

            # Step 7: Create ScenarioRound record
            logger.info(f"  Step 7: Creating ScenarioRound record...")
            from app.models.supply_chain import ScenarioRound as ScenarioRoundModel

            game_round = ScenarioRoundModel(
                scenario_id=game.id,
                round_number=target_round,
                started_at=datetime.utcnow(),
                is_completed=False,
                notes=f"SC Execution Mode - {work_orders_created} work orders created"
            )
            db.add(game_round)
            await db.flush()

            # Step 8: Apply Orders to Game State
            logger.info(f"  Step 8: Applying orders to game state...")
            await self._apply_sc_planning_orders_to_game(game, scenario_user_orders, target_round, db)

            # Step 9: Mark round complete
            game_round.completed_at = datetime.utcnow()
            game_round.ended_at = datetime.utcnow()
            game_round.is_completed = True

            await db.commit()

            logger.info(f"✅ SC Execution Round {target_round} Complete")

            # Return the game round (sync session will need to re-query it)
            return game_round

    def _start_round_dag_sequential(self, game_obj: Game) -> Optional[ScenarioRound]:
        """
        DAG-ordered sequential round execution (Phase 1 implementation).

        Replaces simultaneous scenario_user actions with sequential downstream→upstream processing:
        1. FULFILLMENT phase: ScenarioUsers fulfill downstream orders (ATP-based), downstream acts first
        2. REPLENISHMENT phase: ScenarioUsers order from upstream (after receiving POs)
        3. COMPLETED phase: Round finished, advance to next round

        This mirrors real supply chain workflows where demand flows upstream and
        upstream suppliers wait for purchase orders before acting.

        Args:
            game_obj: Game instance with use_dag_sequential=True

        Returns:
            ScenarioRound record or None if game finished
        """
        from app.models.supply_chain import RoundPhase

        total_rounds = game_obj.max_rounds or 50

        # Determine target round
        latest_round: Optional[ScenarioRound] = (
            self.db.query(ScenarioRound)
            .filter(ScenarioRound.scenario_id == game_obj.id)
            .order_by(ScenarioRound.round_number.desc())
            .first()
        )

        if latest_round:
            if latest_round.is_completed and latest_round.current_phase == RoundPhase.COMPLETED:
                target_round = latest_round.round_number + 1
            else:
                # Round in progress - return existing round
                target_round = latest_round.round_number
                return latest_round
        else:
            target_round = 1

        if target_round > total_rounds:
            game_obj.status = GameStatusDB.FINISHED
            self.db.commit()
            return None

        game_obj.current_round = target_round

        # Create new round with FULFILLMENT phase
        round_record = ScenarioRound(
            scenario_id=game_obj.id,
            round_number=target_round,
            customer_demand=0,  # Will be set later
            is_completed=False,
            started_at=datetime.datetime.utcnow(),
            current_phase=RoundPhase.FULFILLMENT,
            phase_started_at=datetime.datetime.utcnow(),
        )
        self.db.add(round_record)
        self.db.flush()  # Get round_record.id

        # Process transfer order arrivals for this round
        self._process_transfer_order_arrivals(game_obj.id, target_round)

        # Initialize scenario_user rounds (create skeleton records)
        scenario_users = self.db.query(ScenarioUser).filter(ScenarioUser.scenario_id == game_obj.id).all()
        for scenario_user in scenario_users:
            scenario_user_period = ScenarioUserPeriod(
                scenario_user_id=scenario_user.id,
                round_id=round_record.id,
                order_placed=0,
                order_received=0,
                inventory_before=scenario_user.current_stock,
                inventory_after=scenario_user.current_stock,
                backorders_before=scenario_user.backorders,
                backorders_after=scenario_user.backorders,
            )
            self.db.add(scenario_user_period)

        self.db.commit()

        logger.info(f"✅ DAG Sequential Round {target_round} initialized - Phase: FULFILLMENT")

        # Auto-process autonomous agents' fulfillment decisions
        self._process_autonomous_agent_fulfillment(game_obj, round_record, scenario_users)

        # Broadcast phase change via WebSocket (best-effort, non-blocking)
        try:
            from app.api.endpoints.websocket import manager
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(manager.broadcast_to_scenario(game_obj.id, {
                    "type": "round_phase_change",
                    "scenario_id": game_obj.id,
                    "round_number": target_round,
                    "phase": "FULFILLMENT",
                }))
        except Exception:
            pass  # WebSocket broadcast is best-effort

        return round_record

    def _process_autonomous_agent_fulfillment(
        self,
        game_obj: Game,
        round_obj: ScenarioRound,
        scenario_users: List[ScenarioUser]
    ) -> None:
        """
        Auto-process fulfillment decisions for autonomous AI agents.

        Called during round initialization to immediately submit fulfillment
        decisions for agents in AUTONOMOUS mode, allowing the game to progress
        without waiting for manual input.

        Args:
            game_obj: Game instance
            round_obj: Current round
            scenario_users: List of scenario_users in the game
        """
        from app.models.scenario_user import AgentMode
        from app.services.agents import SimulationAgent, AgentType, AgentStrategy

        for scenario_user in scenario_users:
            # Check if scenario_user is autonomous AI
            if scenario_user.agent_mode != AgentMode.AUTONOMOUS:
                continue

            if not scenario_user.is_ai:
                continue

            # Get agent strategy from config
            strategy = self._get_agent_strategy(game_obj, scenario_user)
            if not strategy:
                strategy = AgentStrategy.NAIVE  # Default fallback

            # Create agent instance with config-specific model path
            agent_type = self._get_agent_type_from_role(scenario_user.role)
            # Get the trained model path from the supply chain config
            config_model_path = getattr(
                game_obj.supply_chain_config, "trained_model_path", None
            ) if game_obj.supply_chain_config else None
            agent = SimulationAgent(
                agent_id=scenario_user.id,
                agent_type=agent_type,
                strategy=strategy,
                initial_inventory=scenario_user.current_stock,
                initial_backlog=scenario_user.backorders,
                model_path=config_model_path,
            )

            # Calculate fulfillment decision based on available inventory (ATP)
            atp = self._calculate_atp(scenario_user)
            # Simple fulfillment: ship whatever we can to meet downstream demand
            fulfill_qty = min(atp, scenario_user.backorders) if scenario_user.backorders > 0 else 0

            # If no backlog, still process the decision with zero fulfillment
            # This marks the scenario_user as having submitted their fulfillment
            self._process_node_fulfillment_decision(
                game_obj, round_obj, scenario_user, fulfill_qty
            )

            logger.info(
                f"🤖 Autonomous agent {scenario_user.role} auto-fulfilled {fulfill_qty} units"
            )

        # Check if all scenario_users have submitted and transition phase
        self._check_and_transition_fulfillment_phase(game_obj, round_obj)

    def _process_autonomous_agent_replenishment(
        self,
        game_obj: Game,
        round_obj: ScenarioRound,
        scenario_users: List[ScenarioUser]
    ) -> None:
        """
        Auto-process replenishment decisions for autonomous AI agents.

        Called during phase transition to REPLENISHMENT to immediately submit
        replenishment orders for agents in AUTONOMOUS mode.

        Args:
            game_obj: Game instance
            round_obj: Current round
            scenario_users: List of scenario_users in the game
        """
        from app.models.scenario_user import AgentMode
        from app.services.agents import SimulationAgent, AgentType, AgentStrategy

        for scenario_user in scenario_users:
            # Check if scenario_user is autonomous AI
            if scenario_user.agent_mode != AgentMode.AUTONOMOUS:
                continue

            if not scenario_user.is_ai:
                continue

            # Get agent strategy from config
            strategy = self._get_agent_strategy(game_obj, scenario_user)
            if not strategy:
                strategy = AgentStrategy.NAIVE

            # Create agent instance with config-specific model path
            agent_type = self._get_agent_type_from_role(scenario_user.role)
            # Get the trained model path from the supply chain config
            config_model_path = getattr(
                game_obj.supply_chain_config, "trained_model_path", None
            ) if game_obj.supply_chain_config else None
            agent = SimulationAgent(
                agent_id=scenario_user.id,
                agent_type=agent_type,
                strategy=strategy,
                initial_inventory=scenario_user.current_stock,
                initial_backlog=scenario_user.backorders,
                model_path=config_model_path,
            )

            # Get scenario_user's local state for decision making
            local_state = {
                "inventory": scenario_user.current_stock,
                "backlog": scenario_user.backorders,
                "incoming_shipments": list(getattr(scenario_user, 'pipeline_shipments', None) or []),
                "node_key": scenario_user.assignment_key,
            }

            # Make agent decision
            decision = agent.make_decision(
                current_round=round_obj.round_number,
                current_demand=None,  # Not visible to upstream nodes
                upstream_data=None,
                local_state=local_state,
            )

            # Process replenishment order
            self._process_node_replenishment_decision(
                game_obj, round_obj, scenario_user, decision.quantity
            )

            logger.info(
                f"🤖 Autonomous agent {scenario_user.role} auto-ordered {decision.quantity} units "
                f"(reason: {decision.reason})"
            )

        # Check if all scenario_users have submitted and transition to COMPLETED
        self._check_and_transition_replenishment_phase(game_obj, round_obj)

    def _get_agent_strategy(self, game_obj: Game, scenario_user: ScenarioUser):
        """Get the agent strategy for a scenario_user from game config."""
        from app.services.agents import AgentStrategy

        # Check scenario_user's ai_strategy field
        if scenario_user.ai_strategy:
            try:
                return AgentStrategy(scenario_user.ai_strategy.lower())
            except ValueError:
                pass

        # Check game config role assignments
        config = game_obj.config or {}
        assignments = config.get("player_assignments", [])
        for assignment in assignments:
            if assignment.get("role") == scenario_user.role:
                strategy_str = assignment.get("strategy") or assignment.get("ai_strategy")
                if strategy_str:
                    try:
                        return AgentStrategy(strategy_str.lower())
                    except ValueError:
                        pass

        return None

    def _get_agent_type_from_role(self, role: str):
        """Convert scenario_user role to AgentType enum."""
        from app.services.agents import AgentType

        role_map = {
            "retailer": AgentType.RETAILER,
            "wholesaler": AgentType.WHOLESALER,
            "distributor": AgentType.DISTRIBUTOR,
            "manufacturer": AgentType.MANUFACTURER,
            "factory": AgentType.MANUFACTURER,
            "supplier": AgentType.SUPPLIER,
        }
        return role_map.get(role.lower(), AgentType.RETAILER)

    def _check_and_transition_fulfillment_phase(
        self,
        game_obj: Game,
        round_obj: ScenarioRound
    ) -> None:
        """Check if all scenario_users completed fulfillment and transition to replenishment."""
        from app.models.supply_chain import RoundPhase

        if self._check_phase_transition(
            game_obj, round_obj,
            RoundPhase.FULFILLMENT, RoundPhase.REPLENISHMENT
        ):
            self._transition_phase(game_obj, round_obj, RoundPhase.REPLENISHMENT)

            # Process autonomous agents' replenishment decisions
            scenario_users = self.db.query(ScenarioUser).filter(ScenarioUser.scenario_id == game_obj.id).all()
            self._process_autonomous_agent_replenishment(game_obj, round_obj, scenario_users)

    def _check_and_transition_replenishment_phase(
        self,
        game_obj: Game,
        round_obj: ScenarioRound
    ) -> None:
        """Check if all scenario_users completed replenishment and transition to completed."""
        from app.models.supply_chain import RoundPhase

        if self._check_phase_transition(
            game_obj, round_obj,
            RoundPhase.REPLENISHMENT, RoundPhase.COMPLETED
        ):
            self._transition_phase(game_obj, round_obj, RoundPhase.COMPLETED)

    def _process_node_fulfillment_decision(
        self,
        game_obj: Game,
        round_obj: ScenarioRound,
        scenario_user: ScenarioUser,
        fulfill_qty: int
    ) -> Optional[TransferOrder]:
        """
        Process a scenario_user's fulfillment decision (ATP-based shipment).

        Called when human/agent submits fulfillment quantity for downstream customer.
        Creates TransferOrder and updates scenario_user state.

        Args:
            game_obj: Game instance
            round_obj: Current round
            scenario_user: ScenarioUser making decision
            fulfill_qty: Quantity to ship downstream

        Returns:
            Created TransferOrder or None if validation fails
        """
        from app.models.transfer_order import TransferOrder, TransferOrderLineItem
        from app.models.supply_chain_config import TransportationLane

        # Validate ATP
        current_atp = self._calculate_atp(scenario_user)
        if fulfill_qty > current_atp:
            logger.warning(
                f"ScenarioUser {scenario_user.id} attempted to ship {fulfill_qty} but ATP is {current_atp}"
            )
            # Allow but log warning (business decision to allow over-commitment)

        # Get downstream site ID from topology
        config = game_obj.supply_chain_config
        node_key = scenario_user.assignment_key  # e.g., "retailer", "wholesaler"

        # Find downstream transportation lane
        downstream_lane = (
            self.db.query(TransportationLane)
            .filter(
                TransportationLane.config_id == config.id,
                TransportationLane.from_site_id == scenario_user.site_id
            )
            .first()
        )

        if not downstream_lane:
            logger.error(f"No downstream transportation lane found for scenario_user {scenario_user.id}")
            return None

        # Get lead time
        lead_time = self._get_lane_lead_time(
            config.id,
            scenario_user.site_id,
            downstream_lane.to_site_id
        )

        # Create transfer order
        transfer_order = self._create_transfer_order(
            scenario_id=game_obj.id,
            scenario_user_id=scenario_user.id,
            source_site_id=scenario_user.site_id,
            destination_site_id=downstream_lane.to_site_id,
            quantity=fulfill_qty,
            lead_time=lead_time,
            round_number=round_obj.round_number,
            source_scenario_user_period_id=None,  # Will link ScenarioUserPeriod after creation
        )

        # Update scenario_user state
        scenario_user.current_stock -= fulfill_qty

        # Update scenario_user round record
        scenario_user_period = (
            self.db.query(ScenarioUserPeriod)
            .filter(
                ScenarioUserPeriod.scenario_user_id == scenario_user.id,
                ScenarioUserPeriod.round_id == round_obj.id
            )
            .first()
        )

        if scenario_user_period:
            scenario_user_period.inventory_after = scenario_user.current_stock
            scenario_user_period.fulfillment_qty = fulfill_qty
            scenario_user_period.fulfillment_submitted_at = datetime.datetime.utcnow()
            # Link transfer order back to scenario_user round for bidirectional tracking
            if transfer_order:
                transfer_order.source_scenario_user_period_id = scenario_user_period.id

        self.db.commit()

        logger.info(
            f"✅ ScenarioUser {scenario_user.id} fulfilled {fulfill_qty} units → "
            f"TO {transfer_order.id} (arrives round {transfer_order.arrival_round})"
        )

        return transfer_order

    def _process_node_replenishment_decision(
        self,
        game_obj: Game,
        round_obj: ScenarioRound,
        scenario_user: ScenarioUser,
        order_qty: int
    ) -> Optional[TransferOrder]:
        """
        Process a scenario_user's replenishment decision (upstream order).

        Called when human/agent submits order quantity for upstream supplier.
        Creates TransferOrder/PurchaseOrder and updates scenario_user state.

        Args:
            game_obj: Game instance
            round_obj: Current round
            scenario_user: ScenarioUser making decision
            order_qty: Quantity to order from upstream

        Returns:
            Created TransferOrder or None if validation fails
        """
        from app.models.transfer_order import TransferOrder
        from app.models.supply_chain_config import TransportationLane
        from app.models.supply_chain import UpstreamOrderType

        config = game_obj.supply_chain_config

        # Find upstream transportation lane
        upstream_lane = (
            self.db.query(TransportationLane)
            .filter(
                TransportationLane.config_id == config.id,
                TransportationLane.to_site_id == scenario_user.site_id
            )
            .first()
        )

        if not upstream_lane:
            logger.error(f"No upstream lane found for scenario_user {scenario_user.id} (likely terminal supplier)")
            return None

        # Get lead time
        lead_time = self._get_lane_lead_time(
            config.id,
            upstream_lane.from_site_id,
            scenario_user.site_id
        )

        # Create transfer order (represents PO/MO)
        transfer_order = self._create_transfer_order(
            scenario_id=game_obj.id,
            scenario_user_id=scenario_user.id,
            source_site_id=upstream_lane.from_site_id,
            destination_site_id=scenario_user.site_id,
            quantity=order_qty,
            lead_time=lead_time,
            round_number=round_obj.round_number,
            source_scenario_user_period_id=None,
        )

        # Update scenario_user round record
        scenario_user_period = (
            self.db.query(ScenarioUserPeriod)
            .filter(
                ScenarioUserPeriod.scenario_user_id == scenario_user.id,
                ScenarioUserPeriod.round_id == round_obj.id
            )
            .first()
        )

        if scenario_user_period:
            scenario_user_period.order_placed = order_qty
            scenario_user_period.replenishment_qty = order_qty
            scenario_user_period.replenishment_submitted_at = datetime.datetime.utcnow()
            scenario_user_period.upstream_order_id = transfer_order.id
            scenario_user_period.upstream_order_type = UpstreamOrderType.TO

        self.db.commit()

        logger.info(
            f"✅ ScenarioUser {scenario_user.id} ordered {order_qty} units → "
            f"TO {transfer_order.id} (arrives round {transfer_order.arrival_round})"
        )

        return transfer_order

    def _calculate_atp(self, scenario_user: ScenarioUser) -> int:
        """
        Calculate Available to Promise (ATP) for a scenario_user.

        ATP = Current Inventory - Committed Orders

        Args:
            scenario_user: ScenarioUser instance

        Returns:
            ATP quantity (can be negative if over-committed)
        """
        # Simple ATP calculation for Phase 1
        # Phase 3 will integrate full ATP/CTP from planning workflows
        atp = scenario_user.current_stock

        # Subtract committed TOs not yet shipped (Phase 1: from scenario_user pipeline)
        committed = sum(getattr(scenario_user, 'pipeline_shipments', None) or [])
        atp -= committed

        return max(0, atp)

    def _check_phase_transition(
        self,
        game_obj: Game,
        round_obj: ScenarioRound,
        from_phase: str,
        to_phase: str
    ) -> bool:
        """
        Check if round is ready to transition from one phase to another.

        Uses explicit submission timestamps for reliable phase transition detection.

        Args:
            game_obj: Game instance
            round_obj: Current round
            from_phase: Current phase
            to_phase: Target phase

        Returns:
            True if ready to transition, False otherwise
        """
        from app.models.supply_chain import RoundPhase

        # Get all scenario_users in game
        scenario_users = self.db.query(ScenarioUser).filter(ScenarioUser.scenario_id == game_obj.id).all()
        scenario_user_count = len(scenario_users)

        if from_phase == RoundPhase.FULFILLMENT and to_phase == RoundPhase.REPLENISHMENT:
            # Check if all scenario_users have submitted fulfillment decisions
            # Using explicit fulfillment_submitted_at timestamp
            fulfilled_count = (
                self.db.query(ScenarioUserPeriod)
                .filter(
                    ScenarioUserPeriod.round_id == round_obj.id,
                    ScenarioUserPeriod.fulfillment_submitted_at.isnot(None)
                )
                .count()
            )
            return fulfilled_count >= scenario_user_count

        elif from_phase == RoundPhase.REPLENISHMENT and to_phase == RoundPhase.COMPLETED:
            # Check if all scenario_users have submitted replenishment orders
            # Using explicit replenishment_submitted_at timestamp
            replenished_count = (
                self.db.query(ScenarioUserPeriod)
                .filter(
                    ScenarioUserPeriod.round_id == round_obj.id,
                    ScenarioUserPeriod.replenishment_submitted_at.isnot(None)
                )
                .count()
            )
            return replenished_count >= scenario_user_count

        return False

    def _transition_phase(
        self,
        game_obj: Game,
        round_obj: ScenarioRound,
        new_phase: str
    ) -> None:
        """
        Transition round to a new phase.

        Updates round record and broadcasts WebSocket message.

        Args:
            game_obj: Game instance
            round_obj: Current round
            new_phase: Target phase (FULFILLMENT, REPLENISHMENT, COMPLETED)
        """
        from app.models.supply_chain import RoundPhase

        old_phase = round_obj.current_phase
        round_obj.current_phase = new_phase
        round_obj.phase_started_at = datetime.datetime.utcnow()

        # Update phase completion timestamps
        if new_phase == RoundPhase.REPLENISHMENT:
            round_obj.fulfillment_completed_at = datetime.datetime.utcnow()
        elif new_phase == RoundPhase.COMPLETED:
            round_obj.replenishment_completed_at = datetime.datetime.utcnow()
            round_obj.completed_at = datetime.datetime.utcnow()
            round_obj.is_completed = True

            # Phase 2: Update RLHF preference labels now that outcomes are known
            self._update_rlhf_preference_labels(game_obj, round_obj)

        self.db.commit()

        logger.info(
            f"✅ Round {round_obj.round_number} phase transition: {old_phase} → {new_phase}"
        )

        # Broadcast WebSocket message (best-effort, non-blocking)
        try:
            from app.api.endpoints.websocket import manager
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(manager.broadcast_to_scenario(game_obj.id, {
                    "type": "round_phase_change",
                    "scenario_id": game_obj.id,
                    "round_number": round_obj.round_number,
                    "phase": new_phase,
                    "phase_started_at": round_obj.phase_started_at.isoformat() if round_obj.phase_started_at else None,
                }))
        except Exception:
            pass  # WebSocket broadcast is best-effort

    def _update_rlhf_preference_labels(
        self,
        game_obj: Game,
        round_obj: ScenarioRound
    ) -> None:
        """
        Phase 2: Update RLHF preference labels after round completes.

        Compares AI recommendations vs human decisions based on actual outcomes
        (cost, service level) and updates the preference labels in RLHF feedback.

        Args:
            game_obj: Game instance
            round_obj: Completed round
        """
        try:
            from app.services.rlhf_data_collector import RLHFFeedback, get_rlhf_data_collector

            # Find all RLHF feedback records for this round
            feedbacks = (
                self.db.query(RLHFFeedback)
                .filter(
                    RLHFFeedback.scenario_id == game_obj.id,
                    RLHFFeedback.round_number == round_obj.round_number,
                    RLHFFeedback.preference_label == "unknown"
                )
                .all()
            )

            if not feedbacks:
                return

            logger.info(
                f"📊 Updating RLHF preference labels for round {round_obj.round_number}: "
                f"{len(feedbacks)} feedback records"
            )

            # Get scenario_user round results for outcome comparison
            from app.models.supply_chain import ScenarioUserPeriod
            scenario_user_periods = (
                self.db.query(ScenarioUserPeriod)
                .filter(ScenarioUserPeriod.round_id == round_obj.id)
                .all()
            )
            scenario_user_period_map = {pr.scenario_user_id: pr for pr in scenario_user_periods}

            rlhf_collector = get_rlhf_data_collector(self.db)

            for feedback in feedbacks:
                scenario_user_period = scenario_user_period_map.get(feedback.scenario_user_id)
                if not scenario_user_period:
                    continue

                # Calculate outcomes for both AI and human decisions
                # Human outcome: actual results from the scenario_user round
                human_outcome = {
                    "total_cost": scenario_user_period.cost or 0,
                    "service_level": self._calculate_service_level(scenario_user_period),
                    "inventory_after": scenario_user_period.inventory_after_shipments or 0,
                    "backlog_after": scenario_user_period.backlog or 0,
                }

                # AI outcome: simulate what would have happened with AI suggestion
                # For simplicity, use a heuristic based on the difference
                ai_suggestion = feedback.ai_suggestion
                human_decision = feedback.human_decision

                # Estimate AI outcome (simplified - real impl would simulate)
                # If human ordered more, AI would have had more backlog but lower holding cost
                # If human ordered less, AI would have had less backlog but higher holding cost
                order_diff = human_decision - ai_suggestion

                # Load cost rates from InvPolicy for the scenario's config
                _feedback_config_id = getattr(game, "supply_chain_config_id", None)
                if _feedback_config_id:
                    holding_cost_rate, backlog_cost_rate = self._get_cost_rates_sync(_feedback_config_id)
                else:
                    raise ValueError(
                        f"Cannot compute RLHF counterfactual costs for scenario {game.id}: "
                        f"no supply_chain_config_id found. Ensure the scenario is linked to a supply chain config."
                    )

                ai_outcome = {
                    "total_cost": human_outcome["total_cost"] + (order_diff * holding_cost_rate),
                    "service_level": max(0, human_outcome["service_level"] - (order_diff * 0.01)),
                    "inventory_after": human_outcome["inventory_after"] - order_diff,
                    "backlog_after": max(0, human_outcome["backlog_after"] + order_diff) if order_diff < 0 else human_outcome["backlog_after"],
                }

                # Update preference label
                rlhf_collector.update_preference_label(
                    feedback_id=feedback.id,
                    ai_outcome=ai_outcome,
                    human_outcome=human_outcome
                )

            logger.info(f"✅ Updated RLHF preference labels for round {round_obj.round_number}")

        except Exception as e:
            logger.error(f"Failed to update RLHF preference labels: {e}", exc_info=True)
            # Don't fail the round completion due to RLHF errors

    def _calculate_service_level(self, scenario_user_period: "ScenarioUserPeriod") -> float:
        """Calculate service level for a scenario_user round."""
        demand = scenario_user_period.demand_received or 0
        if demand == 0:
            return 1.0
        fulfilled = scenario_user_period.quantity_shipped or 0
        return min(1.0, fulfilled / demand) if demand > 0 else 1.0

    def _get_current_demand(self, game: Game, round_number: int) -> float:
        """
        Get current customer demand for this round

        Args:
            game: Game instance
            round_number: Current round

        Returns:
            Demand quantity
        """
        demand_pattern = game.demand_pattern or game.config.get('demand_pattern', {})

        if not demand_pattern:
            return 4.0  # Default simulation demand

        pattern_type = demand_pattern.get('type', 'constant')

        if pattern_type == 'step':
            initial = demand_pattern.get('initial', 4)
            step_week = demand_pattern.get('step_week', 5)
            step_value = demand_pattern.get('step_value', 8)
            return float(step_value if round_number >= step_week else initial)
        elif pattern_type == 'constant':
            return float(demand_pattern.get('value', 4))
        elif 'weeks' in demand_pattern:
            weeks = demand_pattern['weeks']
            if round_number < len(weeks):
                return float(weeks[round_number])
            else:
                return float(weeks[-1]) if weeks else 4.0
        else:
            return 4.0

    async def _get_scenario_user_orders_for_round(
        self,
        game: Game,
        round_number: int,
        db
    ) -> Dict[str, float]:
        """
        Get scenario_user order decisions for this round

        This is a placeholder that uses naive strategy.
        TODO: Integrate with actual agent/human decision logic

        Args:
            game: Game instance
            round_number: Current round
            db: Database session

        Returns:
            Dict mapping role → order quantity
        """
        from sqlalchemy import select
        from app.models.scenario_user import ScenarioUser as ScenarioUser

        result = await db.execute(
            select(ScenarioUser).filter(ScenarioUser.scenario_id == game.id)
        )
        scenario_users = result.scalars().all()

        scenario_user_orders = {}
        demand = self._get_current_demand(game, round_number)

        # Naive strategy: order = demand
        for scenario_user in scenario_users:
            scenario_user_orders[scenario_user.role] = demand

        return scenario_user_orders

    async def _apply_sc_planning_orders_to_game(
        self,
        game: Game,
        scenario_user_orders: Dict[str, float],
        round_number: int,
        db
    ) -> None:
        """
        Apply SC supply plan orders to game state.

        Updates game.config JSON with the orders determined by SC planner.

        Args:
            game: Game instance
            scenario_user_orders: Dict mapping role → order quantity
            round_number: Current round number
            db: Async database session
        """
        logger.info(f"    Applying {len(scenario_user_orders)} orders to game state...")

        # Get current config
        cfg = game.config or {}
        nodes_state = cfg.get("nodes", {})

        # Apply orders to each node
        for role, order_qty in scenario_user_orders.items():
            if role not in nodes_state:
                logger.warning(f"    ⚠️  Role {role} not found in game config")
                continue

            node_state = nodes_state[role]

            # Update order history
            order_history = node_state.get("order_history", [])
            order_history.append({
                "round": round_number,
                "quantity": int(order_qty),
                "source": "sc_planner"
            })
            node_state["order_history"] = order_history

            # Set current order
            node_state["current_order"] = int(order_qty)

            logger.info(f"    ✓ {role}: order={int(order_qty)}")

        # Update game config
        cfg["nodes"] = nodes_state
        game.config = cfg

        # Mark as modified for SQLAlchemy
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(game, "config")

        await db.flush()

        logger.info(f"    ✓ Applied all orders to game config")






    def process_ai_scenario_users(self, game: Game, game_round: ScenarioRound, context: RoundContext) -> None:
        """Process AI scenario_users' moves for the current round."""
        scenario_users = self.db.query(ScenarioUser).filter(
            ScenarioUser.scenario_id == game.id,
            ScenarioUser.is_ai == True
        ).all()

        if not scenario_users:
            return

        # 1. Resolve ScenarioUser Mappings
        node_to_scenario_users = self._resolve_scenario_user_mappings(game, scenario_users, context)
        
        # 2. Determine Processing Order (Downstream to Upstream)
        # This ensures downstream demand is available for upstream agents
        processing_nodes = []
        for node in reversed(context.topology.node_sequence):
            if node not in processing_nodes:
                processing_nodes.append(node)
                
        # 3. Process Each Node
        for node_key in processing_nodes:
            # Skip if not assigned to any scenario_user
            assigned_scenario_users = node_to_scenario_users.get(node_key)
            if not assigned_scenario_users:
                continue
                
            # Skip special nodes (though they shouldn't be in node_to_scenario_users usually)
            node_type = context.topology.node_types.get(node_key, "")
            if node_type in {"market_demand", "market_supply"}:
                continue
                
            # Process for each scenario_user assigned (usually one)
            for scenario_user in assigned_scenario_users:
                self._process_single_agent(
                    node_key, 
                    scenario_user, 
                    game, 
                    game_round, 
                    context
                )

    def _process_single_agent(
        self, 
        node_key: str, 
        scenario_user: ScenarioUser, 
        game: Game, 
        game_round: ScenarioRound, 
        context: RoundContext
    ) -> None:
        """Process decision for a single AI agent."""
        agent_type = self._agent_type_for_node(context.topology.node_types.get(node_key))
        agent = self.agent_manager.get_agent(agent_type)
        desired_strategy = scenario_user.ai_strategy or getattr(scenario_user, "strategy", None)
        if agent and desired_strategy:
            try:
                strategy_enum = (
                    desired_strategy
                    if isinstance(desired_strategy, AgentStrategyEnum)
                    else AgentStrategyEnum(str(desired_strategy).lower())
                )
                self.agent_manager.set_agent_strategy(
                    agent_type,
                    strategy_enum,
                    llm_model=getattr(scenario_user, "llm_model", None),
                )
            except Exception:  # noqa: BLE001
                logger.debug(
                    "Unable to set strategy %s for agent %s (scenario_user %s)",
                    desired_strategy,
                    agent_type,
                    getattr(scenario_user, "id", "?"),
                )

        if not agent:
            logger.warning(f"No agent found for scenario_user {scenario_user.id} (role={scenario_user.role})")
            return

        # Build state for agent
        node_state = context.node_states.get(node_key)
        if not node_state:
            return

        # Prepare upstream data for agent context
        upstream_data = {}
        
        # 1. Downstream orders (current demand)
        upstream_data["downstream_orders"] = node_state.current_round_demand
        
        # 2. Historical context from previous rounds and demand smoothing
        history = (game.config or {}).get("history", [])
        policy = context.node_policies.get(node_key, {}) if hasattr(context, "node_policies") else {}
        order_lead = int(policy.get("order_leadtime", 0) or 0)
        supply_lead = policy.get("supply_leadtime")
        try:
            supply_lead = int(supply_lead) if supply_lead is not None else None
        except (TypeError, ValueError):
            supply_lead = None
        if supply_lead is None or supply_lead <= 0:
            # Fall back to lane configuration or order lead time when explicit supply lead is missing.
            upstream_nodes = context.topology.orders_map.get(node_key, [])
            lane_lookup = getattr(context.topology, "lane_lookup", {}) or {}
            inferred = None
            for upstream in upstream_nodes or []:
                lane = lane_lookup.get((upstream, node_key))
                lead_val = getattr(lane, "supply_lead_time", None) if lane else None
                try:
                    lead_int = int(lead_val) if lead_val is not None else None
                except (TypeError, ValueError):
                    lead_int = None
                if lead_int and lead_int > 0:
                    inferred = lead_int if inferred is None else max(inferred, lead_int)
            if inferred is None or inferred <= 0:
                inferred = max(1, order_lead or 1)
            supply_lead = inferred

        bleed_factor = None
        try:
            bleed_factor = float(policy.get("bleed_factor", 0.75))
        except (TypeError, ValueError):
            bleed_factor = 0.75
        avg_demand: Optional[float] = None
        if history:
            horizon = max(1, order_lead + 1)
            samples: List[float] = []
            for entry in history[-horizon:]:
                node_states = entry.get("node_states", {}) if isinstance(entry, dict) else {}
                node_snapshot = node_states.get(node_key, {}) if isinstance(node_states, dict) else {}
                orders_val = node_snapshot.get("orders")
                try:
                    val = float(orders_val)
                except (TypeError, ValueError):
                    val = None
                if val is not None:
                    samples.append(val)
            if samples:
                avg_demand = sum(samples) / len(samples)
        stats = (context.config or {}).get("demand_statistics", {})
        stats_mean = None
        try:
            stats_mean = float(stats.get("mean"))
        except (TypeError, ValueError):
            stats_mean = None
        if avg_demand is None and stats_mean is not None:
            avg_demand = stats_mean
        if avg_demand is None:
            avg_demand = DEFAULT_STEADY_STATE_DEMAND
        if stats_mean is not None:
            avg_demand = min(avg_demand, stats_mean)

        try:
            variance = float((context.config or {}).get("demand_statistics", {}).get("variance", 0.0))
            z = 1.645
            safety = z * (variance ** 0.5) * (order_lead ** 0.5)
        except Exception:
            safety = 0.0
        target_inventory = avg_demand * supply_lead + safety
        if history:
            # Previous orders by role (for global/network awareness)
            last_round_entry = history[-1]
            node_orders = last_round_entry.get("node_orders", {})
            previous_orders_by_role = {}
            for n_key, order_val in node_orders.items():
                n_type = context.topology.node_types.get(n_key)
                if n_type:
                    agent_type_enum = self._agent_type_for_node(n_type)
                    role_name = agent_type_enum.value
                    qty_val = order_val.get("quantity") if isinstance(order_val, Mapping) else order_val
                    try:
                        previous_orders_by_role[role_name] = float(qty_val)
                    except (TypeError, ValueError):
                        continue
            upstream_data["previous_orders_by_role"] = previous_orders_by_role
            
            # Upstream node history (orders placed by our supplier)
            upstream_nodes = context.topology.orders_map.get(node_key, [])
            if upstream_nodes:
                upstream_node = upstream_nodes[0]
                upstream_node_history = []
                for entry in history:
                    orders = entry.get("node_orders", {})
                    val = orders.get(upstream_node)
                    if val is not None:
                        qty_val = val.get("quantity") if isinstance(val, Mapping) else val
                        try:
                            upstream_node_history.append(float(qty_val))
                        except (TypeError, ValueError):
                            continue
                upstream_data["previous_orders"] = upstream_node_history

        # Make decision
        current_round_number = getattr(context.round_record, "round_number", None) or context.round_number
        aggregate_demand = sum(node_state.current_round_demand.values())
        local_state = {
            "inventory": sum(node_state.inventory_by_item.values()),
            "backlog": sum(node_state.backlog_by_item.values()),
            "on_order": sum(node_state.on_order_by_item.values()),
            "target_inventory": target_inventory,
            "avg_demand": avg_demand,
            "order_leadtime": order_lead,
            "bleed_factor": bleed_factor,
            "debug_inventory": {
                "start_inventory": getattr(node_state, "debug_start_inventory", None),
                "post_demand_inventory": getattr(node_state, "debug_post_demand_inventory", None),
                "inbound_received": sum(getattr(node_state, "supply_received_by_item", {}).values()) if getattr(node_state, "supply_received_by_item", None) else 0,
                "ending_inventory": sum(node_state.inventory_by_item.values()),
                "target_inventory": target_inventory,
                "bleed_factor": bleed_factor,
                "net_available": (sum(node_state.inventory_by_item.values()) + sum(node_state.on_order_by_item.values()) - sum(node_state.backlog_by_item.values())),
            },
        }
        decision = agent.make_decision(
            current_round=current_round_number,
            current_demand=aggregate_demand,
            upstream_data=upstream_data,
            local_state=local_state,
        )

        comment_value = MixedScenarioService._truncate_comment(getattr(decision, "reason", None))
        if comment_value:
            context.agent_comments[node_key] = comment_value

        # Track fallback warnings for AI agents
        if getattr(decision, "fallback_used", False):
            context.agent_fallbacks[node_key] = {
                "fallback_used": True,
                "original_strategy": getattr(decision, "original_strategy", None),
                "fallback_reason": getattr(decision, "fallback_reason", None),
                "node_name": node_key,
            }

        # Apply decision (place order)
        if decision and decision.quantity > 0:
            # Resolve which item is being ordered
            primary_item_id: Optional[str] = None
            for entry in (context.config or {}).get("items", []):
                candidate = entry.get("id") if isinstance(entry, dict) else getattr(entry, "id", None)
                token = MixedScenarioService._normalise_product_id(candidate)
                if token:
                    primary_item_id = token
                    break
            if not primary_item_id:
                # Fallback: use first available item from upstream inventory
                upstream_nodes = context.topology.orders_map.get(node_key, [])
                for upstream_node in upstream_nodes:
                    upstream_state = context.node_states.get(upstream_node)
                    if upstream_state and upstream_state.inventory_by_item:
                        primary_item_id = next(iter(upstream_state.inventory_by_item.keys()))
                        break
            if not primary_item_id:
                # Final fallback: log warning and skip order (no valid product ID available)
                logger.warning(
                    f"Agent order for node {node_key}: Cannot determine product ID. "
                    f"No products in config items list and no upstream inventory. Skipping order."
                )
                return  # Exit early, skip placing order

            # Find ProductSiteConfig for this item at this node to get supplier preferences
            product_site_config = None
            for node_data in (context.config or {}).get("nodes", []):
                if MixedScenarioService._normalise_key(node_data.get("name", "")) == node_key:
                    for inc in node_data.get("item_configs", []):
                        if str(inc.get("product_id")) == str(primary_item_id):
                            product_site_config = inc
                            break
                    break

            # Get suppliers sorted by priority
            suppliers = []
            if product_site_config and product_site_config.get("suppliers"):
                # Build supplier list with priorities from ItemNodeSupplier
                for supplier_info in product_site_config["suppliers"]:
                    supplier_site_id = supplier_info.get("supplier_site_id")
                    priority = supplier_info.get("priority", 0)

                    # Find the node name for this supplier_site_id
                    for node_data in (context.config or {}).get("nodes", []):
                        if node_data.get("id") == supplier_site_id:
                            supplier_node_name = MixedScenarioService._normalise_key(node_data.get("name", ""))
                            suppliers.append({
                                "node": supplier_node_name,
                                "priority": priority,
                                "site_id": supplier_site_id,
                            })
                            break

                # Sort by priority (lower number = higher priority)
                suppliers.sort(key=lambda x: x["priority"])

            # If no suppliers defined in ItemNodeSupplier, fall back to topology
            if not suppliers:
                upstream_nodes = context.topology.orders_map.get(node_key, [])
                for upstream_node in upstream_nodes:
                    suppliers.append({
                        "node": upstream_node,
                        "priority": 0,
                        "site_id": None,
                    })

            if not suppliers:
                # No suppliers available at all
                return

            # NODE-LEVEL AGENTS: Always use priority 0 (highest priority) supplier
            # All agents in _process_single_agent are node-level (naive, PID, LLM, GNN)
            # They have no visibility to alternate suppliers or inventory levels
            preferred_suppliers = [s for s in suppliers if s["priority"] == 0]
            if preferred_suppliers:
                upstream_node = preferred_suppliers[0]["node"]
            else:
                # No priority 0 supplier, use first available
                upstream_node = suppliers[0]["node"]

            # FUTURE: Supervisory/Global agents would check inventory availability here
            # and fall back to alternate suppliers based on inventory position
            # if not enough_inventory_at_preferred:
            #     # Sort alternates by inventory level
            #     alternate_suppliers = [s for s in suppliers if s["priority"] > 0]
            #     alternate_suppliers.sort(key=lambda s: get_inventory_level(s["node"]), reverse=True)
            #     upstream_node = alternate_suppliers[0]["node"]
            self._place_single_order(
                context=context,
                node_key=node_key,
                node_state=node_state,
                upstream_node=upstream_node,
                quantity=decision.quantity,
                game_round=game_round,
                current_round_number=current_round_number
            )

    def _place_single_order(
        self,
        context: RoundContext,
        node_key: str,
        node_state: NodeState,
        upstream_node: str,
        quantity: int,
        game_round: ScenarioRound,
        current_round_number: int,
    ) -> None:
        """Place a single order to a specific upstream supplier.

        This helper method handles the order placement logic for one upstream node,
        including item resolution, lead time calculation, and pipeline tracking.
        """
        # Calculate lead time
        lane = context.topology.lane_lookup.get((upstream_node, node_key))
        lead_time = getattr(lane, "demand_lead_time", 0) if lane else 0

        # Resolve a concrete item id (no "default" placeholder)
        primary_item_id: Optional[str] = None
        for entry in (context.config or {}).get("items", []):
            candidate = entry.get("id") if isinstance(entry, dict) else getattr(entry, "id", None)
            token = MixedScenarioService._normalise_product_id(candidate)
            if token:
                primary_item_id = token
                break
        if not primary_item_id:
            upstream_state = context.node_states.get(upstream_node)
            if upstream_state and upstream_state.inventory_by_item:
                primary_item_id = next(iter(upstream_state.inventory_by_item.keys()))
        if not primary_item_id:
            # Final fallback: log warning and return without placing order
            logger.warning(
                f"ScenarioUser order from {node_key} to {upstream_node}: Cannot determine product ID. "
                f"No products in config items list and no upstream inventory. Skipping order."
            )
            return  # Exit early without placing order

        # Create order
        order = OrderRequest(
            product_id=primary_item_id,
            source=node_key,
            quantity=quantity,
            due_round=game_round.round_number + lead_time,
            downstream=node_key,  # The one placing the order
            step_number=current_round_number,
        )

        # Add to upstream's order queue
        upstream_state = context.node_states.get(upstream_node)
        if upstream_state is None:
            upstream_state = NodeState()
            context.node_states[upstream_node] = upstream_state
        queue = list(getattr(upstream_state, "inbound_demand", []) or [])
        queue.append(order)
        upstream_state.inbound_demand = queue

        # Track pipeline for the ordering node so future decisions see on-order inventory
        node_state.on_order_by_item[primary_item_id] = node_state.on_order_by_item.get(primary_item_id, 0) + quantity
        node_state.on_order = sum(max(0, int(v)) for v in node_state.on_order_by_item.values())

        # Capture order details for debug traces/history so logs reflect scenario_user/agent actions
        created_entries = list(getattr(node_state, "debug_created_orders", []) or [])
        created_entries.append({"product_id": primary_item_id, "quantity": quantity})
        node_state.debug_created_orders = created_entries
        node_state.debug_orders_created = getattr(node_state, "debug_orders_created", 0) + quantity
        node_state.debug_trace.append(
            {
                "step": "ScenarioUser Order",
                "orders_created": quantity,
                "orders_created_detail": list(created_entries),
            }
        )

    def _resolve_scenario_user_mappings(self, game: Game, scenario_users: List[ScenarioUser], context: RoundContext) -> Dict[str, List[ScenarioUser]]:
        """Map scenario_users to nodes based on configuration and assignments."""
        cfg = game.config or {}
        
        # 1. Build Assignment Lookup (Role -> [Node])
        # This logic mimics the original _resolve_scenario_user_mappings but uses context/cfg
        node_assignment_lookup: Dict[str, List[str]] = defaultdict(list)
        for entry in cfg.get("player_assignments") or []:
            assignment_key = MixedScenarioService._canonical_role(
                entry.get("assignment_key") or entry.get("role")
            )
            if not assignment_key:
                continue
            coverage: List[str] = []
            for raw in entry.get("node_keys") or []:
                canonical = MixedScenarioService._canonical_role(raw)
                if canonical:
                    coverage.append(canonical)
            for node_key in coverage:
                node_assignment_lookup[node_key].append(assignment_key)

        # 2. Build ScenarioUser Lookup (Role -> [ScenarioUser])
        scenario_user_index: Dict[int, ScenarioUser] = {scenario_user.id: scenario_user for scenario_user in scenario_users}
        assignment_scenario_users: Dict[str, List[ScenarioUser]] = defaultdict(list)
        for raw_key, payload in (getattr(game, "role_assignments", {}) or {}).items():
            assignment_key = MixedScenarioService._canonical_role(raw_key)
            if not assignment_key:
                continue
            scenario_user_id = payload.get("scenario_user_id")
            if not scenario_user_id:
                continue
            scenario_user = scenario_user_index.get(scenario_user_id)
            if scenario_user:
                assignment_scenario_users[assignment_key].append(scenario_user)

        # 3. Map Nodes to ScenarioUsers
        captured_scenario_user_ids: Set[int] = {
            scenario_user.id
            for bundle in assignment_scenario_users.values()
            for scenario_user in bundle
        }
        legacy_node_to_scenario_users: Dict[str, List[ScenarioUser]] = defaultdict(list)
        for scenario_user in scenario_users:
            if scenario_user.id in captured_scenario_user_ids:
                continue
            node_key = MixedScenarioService._scenario_user_node_key(scenario_user)
            if node_key:
                legacy_node_to_scenario_users[node_key].append(scenario_user)

        node_to_scenario_users: Dict[str, List[ScenarioUser]] = defaultdict(list)
        for node in context.topology.all_nodes:
            canonical_node = MixedScenarioService._canonical_role(node)
            if not canonical_node:
                continue
            assignment_keys = node_assignment_lookup.get(canonical_node, [])
            for assignment_key in assignment_keys:
                node_to_scenario_users[canonical_node].extend(
                    assignment_scenario_users.get(assignment_key, [])
                )
            if not node_to_scenario_users.get(canonical_node) and legacy_node_to_scenario_users.get(canonical_node):
                node_to_scenario_users[canonical_node].extend(legacy_node_to_scenario_users[canonical_node])

        # Deduplicate
        for node_key, assigned in list(node_to_scenario_users.items()):
            if not assigned:
                continue
            unique: List[ScenarioUser] = []
            seen_ids: Set[int] = set()
            for scenario_user in assigned:
                if scenario_user.id in seen_ids:
                    continue
                seen_ids.add(scenario_user.id)
                unique.append(scenario_user)
            node_to_scenario_users[node_key] = unique
        return node_to_scenario_users
    
    def complete_round(self, game_round: ScenarioRound) -> None:
        """Complete the current round, updating scenario_user inventories and costs."""
        # Get all scenario_user rounds for this game round
        scenario_user_periods = self.db.query(ScenarioUserPeriod).filter(
            ScenarioUserPeriod.round_id == game_round.id
        ).all()
        
        for pr in scenario_user_periods:
            # Get scenario_user's inventory
            inventory = self.db.query(ScenarioUserInventory).filter(
                ScenarioUserInventory.scenario_user_id == pr.scenario_user_id
            ).first()
            
            # Update inventory based on orders received
            # (This is a simplified version - actual implementation would consider lead times)
            pr.inventory_after = inventory.current_stock - pr.order_placed
            if pr.inventory_after < 0:
                pr.backorders_after = abs(pr.inventory_after)
                pr.inventory_after = 0
            
            # Calculate costs using InvPolicy rates for the scenario's config
            scenario_user_obj = self.db.query(ScenarioUser).filter(
                ScenarioUser.id == pr.scenario_user_id
            ).first()
            config_id = None
            if scenario_user_obj and scenario_user_obj.scenario_id:
                from app.models.scenario import Scenario as _Scenario
                _scenario = self.db.query(_Scenario).filter(
                    _Scenario.id == scenario_user_obj.scenario_id
                ).first()
                config_id = getattr(_scenario, "supply_chain_config_id", None)
            if config_id:
                _holding_rate, _backlog_rate = self._get_cost_rates_sync(config_id)
            else:
                raise ValueError(
                    f"Cannot compute period costs for scenario_user {pr.scenario_user_id}: "
                    f"no supply_chain_config_id found on the scenario. "
                    f"Ensure the scenario is linked to a supply chain config."
                )
            pr.holding_cost = pr.inventory_after * _holding_rate
            pr.backorder_cost = pr.backorders_after * _backlog_rate
            pr.total_cost = pr.holding_cost + pr.backorder_cost
            
            # Update inventory for next round
            inventory.current_stock = pr.inventory_after
            inventory.backorders = pr.backorders_after
        
        timestamp = datetime.utcnow()
        game_round.ended_at = timestamp
        game_round.completed_at = timestamp
        self.db.commit()
    
    def get_current_round(self, scenario_id: int) -> Optional[ScenarioRound]:
        """Get the current round for a game."""
        return self.db.query(ScenarioRound).filter(
            ScenarioRound.scenario_id == scenario_id,
            ScenarioRound.ended_at.is_(None)
        ).first()

    @staticmethod
    def _truncate_comment(value: Optional[str]) -> Optional[str]:
        """Clamp agent comments to the 255-character column limit."""

        if not value:
            return None

        comment = str(value).strip()
        if not comment:
            return None

        limit = 180  # keep well under the 255 byte column limit, even with UTF-8 escapes
        if len(comment) > limit:
            comment = comment[: limit - 3] + "..."

        return comment

    def finish_game(self, scenario_id: int) -> Game:
        game = self.db.query(Game).filter(Game.id == scenario_id).first()
        if not game:
            raise ValueError("Game not found")
        game.status = GameStatusDB.FINISHED
        self.db.commit(); self.db.refresh(game)
        return game

    def get_report(self, scenario_id: int) -> Dict[str, Any]:
        game = self.db.query(Game).filter(Game.id == scenario_id).first()
        if not game:
            raise ValueError("Game not found")

        cfg = dict(game.config or {})
        supply_chain_config_id = (
            cfg.get("supply_chain_config_id")
            or getattr(game, "supply_chain_config_id", None)
        )

        snapshot_cache: Optional[Dict[str, Any]] = None

        def _ensure_snapshot() -> Dict[str, Any]:
            nonlocal snapshot_cache
            if snapshot_cache is None and supply_chain_config_id is not None:
                snapshot_cache = self._supply_chain_snapshot(supply_chain_config_id) or {}
            return snapshot_cache or {}

        if supply_chain_config_id is not None and "supply_chain_config_id" not in cfg:
            cfg["supply_chain_config_id"] = supply_chain_config_id

        if not cfg.get("nodes"):
            raise ValueError("Supply chain configuration is missing nodes.")

        if not cfg.get("lanes"):
            raise ValueError("Supply chain configuration is missing lanes.")

        if not cfg.get("items"):
            raise ValueError("Supply chain configuration is missing items.")

        if not cfg.get("bill_of_materials"):
            raise ValueError("Supply chain configuration is missing bill_of_materials.")

        site_type_definitions_snapshot: List[Dict[str, Any]] = []
        site_type_labels_snapshot: Dict[str, str] = {}
        snapshot = _ensure_snapshot() if not cfg.get("site_type_definitions") or not cfg.get("site_type_labels") else {}
        if snapshot:
            site_type_definitions_snapshot = snapshot.get("site_type_definitions") or []
            site_type_labels_snapshot = snapshot.get("site_type_labels") or {}

        if not cfg.get("site_type_definitions") and site_type_definitions_snapshot:
            cfg["site_type_definitions"] = MixedScenarioService._json_clone(
                site_type_definitions_snapshot
            )

        if not cfg.get("site_type_labels") and site_type_labels_snapshot:
            cfg["site_type_labels"] = MixedScenarioService._json_clone(
                site_type_labels_snapshot
            )

        if not cfg.get("time_bucket"):
            snapshot = snapshot or _ensure_snapshot()
            snapshot_bucket = snapshot.get("time_bucket")
            if snapshot_bucket:
                if hasattr(snapshot_bucket, "value"):
                    cfg["time_bucket"] = snapshot_bucket.value
                else:
                    cfg["time_bucket"] = snapshot_bucket

        if not cfg.get("start_date"):
            start_date_value = getattr(game, "start_date", None)
            if isinstance(start_date_value, str):
                cfg["start_date"] = start_date_value
            elif start_date_value is not None:
                try:
                    cfg["start_date"] = start_date_value.isoformat()
                except AttributeError:
                    cfg["start_date"] = start_date_value

        node_policies = cfg.get("node_policies") or {}
        lane_views = self._build_lane_views(node_policies, cfg)
        lane_nodes = lane_views.get("all_nodes") or []
        extracted_types = MixedScenarioService._extract_node_types(cfg)
        node_sequence = lane_views.get("node_sequence") or cfg.get("node_sequence") or []
        if not node_sequence:
            raise ValueError(
                "Supply chain configuration is missing node sequence; ensure nodes/types/lanes are saved in the DB."
            )
        cfg["node_sequence"] = node_sequence
        node_types_map = {
            MixedScenarioService._normalise_key(key): MixedScenarioService._normalise_node_type(value)
            for key, value in extracted_types.items()
            if MixedScenarioService._normalise_key(key)
        }
        for raw_key, node_type in (lane_views.get("node_types") or {}).items():
            canonical_key = MixedScenarioService._normalise_key(raw_key)
            if canonical_key:
                node_types_map[canonical_key] = MixedScenarioService._normalise_node_type(node_type)
        raw_sequence = lane_views.get("node_sequence") or []
        ordered_sequence: List[str] = []
        seen_nodes: Set[str] = set()
        for bucket in (lane_nodes, raw_sequence, node_types_map.keys()):
            for candidate in bucket:
                key = MixedScenarioService._normalise_key(candidate)
                if not key or key in seen_nodes:
                    continue
                ordered_sequence.append(key)
                seen_nodes.add(key)
        if not ordered_sequence:
            ordered_sequence = sorted(node_types_map.keys())
        node_sequence = ordered_sequence
        site_type_definitions = cfg.get("site_type_definitions") or site_type_definitions_snapshot or []
        site_type_labels = cfg.get("site_type_labels") or site_type_labels_snapshot or {}
        normalized_type_labels: Dict[str, str] = {}
        for definition in site_type_definitions:
            slug = MixedScenarioService._normalise_node_type(definition.get("type"))
            if not slug:
                continue
            label_value = definition.get("label") or definition.get("type") or slug.replace("_", " ").title()
            normalized_type_labels[slug] = label_value
        for slug, label_value in normalized_type_labels.items():
            site_type_labels.setdefault(slug, label_value)

        nodes_payload = cfg.get("nodes") or []
        node_display_names: Dict[str, str] = dict(cfg.get("node_display_names") or {})
        for node in nodes_payload:
            label = node.get("name") or node.get("id")
            key = MixedScenarioService._normalise_key(label)
            display_label = (
                node.get("display_name")
                or node.get("label")
                or node.get("name")
                or node.get("id")
            )
            if key:
                node_display_names.setdefault(key, str(display_label))
                node_type_value = node.get("type")
                if node_type_value and key not in node_types_map:
                    node_types_map[key] = MixedScenarioService._normalise_node_type(node_type_value)
        for raw_label in node_policies.keys():
            key = MixedScenarioService._normalise_key(raw_label)
            if key and key not in node_display_names:
                node_display_names[key] = str(raw_label).replace("_", " ").title()

        type_to_nodes: Dict[str, List[str]] = defaultdict(list)
        for node_key, node_type in node_types_map.items():
            if node_type:
                type_to_nodes[node_type].append(node_key)

        node_catalog: List[Dict[str, Any]] = [
            {
                "key": key,
                "type": node_types_map.get(key, "unknown"),
                "display_name": node_display_names.get(key, key.replace("_", " ").title()),
            }
            for key in node_sequence
        ]

        config_history_payload = MixedScenarioService._json_clone(cfg.get("history") or [])
        config_history_observed_types: Set[str] = set()
        rounds = (
            self.db.query(ScenarioRound)
            .filter(ScenarioRound.scenario_id == scenario_id)
            .order_by(ScenarioRound.round_number.asc())
            .all()
        )

        history_map: Dict[int, Dict[str, Any]] = {}
        def ensure_history_entry(round_number: int) -> Dict[str, Any]:
            if round_number in history_map:
                return history_map[round_number]
            entry = {
                "round": round_number,
                "demand": None,
                "orders": {},
                "node_orders": {},
                "node_states": {},
                "inventory_positions": {},
                "inventory_positions_with_pipeline": {},
                "backlogs": {},
                "total_cost": 0.0,
                "period_start": None,
                "period_end": None,
            }
            history_map[round_number] = entry
            return entry
        demand_series: List[Dict[str, Any]] = []
        bucket = normalize_time_bucket(getattr(game, "time_bucket", TimeBucket.WEEK))
        start_date = getattr(game, "start_date", DEFAULT_START_DATE) or DEFAULT_START_DATE
        order_series: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        role_totals: Dict[str, Dict[str, Any]] = {}
        observed_node_types: Set[str] = set()

        # Ensure reports always start at round 1 by inserting a placeholder if the
        # first stored round begins later (legacy runs).
        if rounds and rounds[0].round_number > 1:
            first = rounds[0]
            placeholder_start = compute_period_start(start_date, 0, bucket)
            placeholder_end = compute_period_end(placeholder_start, bucket)
            placeholder = ScenarioRound(
                scenario_id=first.scenario_id,
                round_number=1,
                customer_demand=first.customer_demand,
                period_start=placeholder_start,
                period_end=placeholder_end,
            )
            rounds = [placeholder] + rounds

        for round_obj in rounds:
            period_start = round_obj.period_start or compute_period_start(
                start_date,
                max(0, round_obj.round_number - 1),
                bucket,
            )
            period_end = round_obj.period_end or compute_period_end(period_start, bucket)

            history_map[round_obj.round_number] = {
                "round": round_obj.round_number,
                "demand": round_obj.customer_demand,
                "orders": {},
                "node_orders": {},
                "node_states": {},
                "inventory_positions": {},
                "inventory_positions_with_pipeline": {},
                "backlogs": {},
                "total_cost": 0.0,
                "period_start": period_start.isoformat() if period_start else None,
                "period_end": period_end.isoformat() if period_end else None,
            }
            demand_series.append(
                {
                    "round": round_obj.round_number,
                    "demand": round_obj.customer_demand,
                    "period_start": period_start.isoformat() if period_start else None,
                    "period_end": period_end.isoformat() if period_end else None,
                }
            )

        scenario_user_period_records = (
            self.db.query(ScenarioUserPeriod, ScenarioRound, ScenarioUser)
            .join(ScenarioRound, ScenarioUserPeriod.round_id == ScenarioRound.id)
            .join(ScenarioUser, ScenarioUserPeriod.scenario_user_id == ScenarioUser.id)
            .filter(ScenarioRound.scenario_id == scenario_id)
            .order_by(ScenarioRound.round_number.asc())
            .all()
        )

        for scenario_user_period, round_obj, scenario_user in scenario_user_period_records:
            entry = ensure_history_entry(round_obj.round_number)
            entry.setdefault("orders", {})
            entry.setdefault("node_orders", {})
            entry.setdefault("node_states", {})
            entry.setdefault("inventory_positions", {})
            entry.setdefault("inventory_positions_with_pipeline", {})
            entry.setdefault("backlogs", {})
            if entry.get("demand") is None:
                entry["demand"] = round_obj.customer_demand
            if entry.get("period_start") is None and round_obj.period_start:
                entry["period_start"] = round_obj.period_start.isoformat()
            if entry.get("period_end") is None and round_obj.period_end:
                entry["period_end"] = round_obj.period_end.isoformat()

            node_key = MixedScenarioService._scenario_user_node_key(scenario_user)
            if not node_key:
                node_key = MixedScenarioService._normalise_key(getattr(scenario_user.role, "value", scenario_user.role))
            node_type = node_types_map.get(node_key) or MixedScenarioService._normalise_node_type(
                getattr(scenario_user.role, "value", scenario_user.role)
            )
            if node_type:
                observed_node_types.add(node_type)
            display_name = getattr(scenario_user, "name", None) or node_display_names.get(
                node_key, node_key.replace("_", " ").title()
            )

            comment_value = scenario_user_period.comment
            if isinstance(comment_value, dict):
                comment_text = comment_value.get("text")
                if not comment_text:
                    comment_text = json.dumps(comment_value)
            elif comment_value is None:
                comment_text = ""
            else:
                comment_text = str(comment_value)

            order_info = {
                "quantity": scenario_user_period.order_placed,
                "received": scenario_user_period.order_received,
                "inventory_before": scenario_user_period.inventory_before,
                "inventory_after": scenario_user_period.inventory_after,
                "backorders_before": scenario_user_period.backorders_before,
                "backorders_after": scenario_user_period.backorders_after,
                "holding_cost": float(scenario_user_period.holding_cost or 0.0),
                "backorder_cost": float(scenario_user_period.backorder_cost or 0.0),
                "total_cost": float(scenario_user_period.total_cost or 0.0),
                "comment": comment_text,
                "submitted_at": getattr(scenario_user_period, "updated_at", None),
            }

            entry["orders"][node_key] = order_info
            entry.setdefault("node_orders", {})[node_key] = dict(order_info)
            # ScenarioUserPeriod does not track on-order quantities; approximate inventory
            # position as on-hand minus backlog to reflect negative positions when backlogged.
            ip_net = int(scenario_user_period.inventory_after or 0) - int(scenario_user_period.backorders_after or 0)
            entry["inventory_positions"][node_key] = ip_net
            entry.setdefault("inventory_positions_with_pipeline", {})[node_key] = ip_net
            entry["backlogs"][node_key] = scenario_user_period.backorders_after
            entry["total_cost"] = float(entry.get("total_cost", 0.0)) + order_info["total_cost"]

            entry.setdefault("node_states", {})[node_key] = {
                "inventory_before": scenario_user_period.inventory_before,
                "inventory_after": scenario_user_period.inventory_after,
                "backlog_before": scenario_user_period.backorders_before,
                "backlog_after": scenario_user_period.backorders_after,
                "holding_cost": order_info["holding_cost"],
                "backlog_cost": order_info["backorder_cost"],
                "total_cost": order_info["total_cost"],
                "type": node_type,
                "display_name": display_name,
                "scenario_user_id": scenario_user.id,
                "scenario_user_name": getattr(scenario_user, "name", None),
                "player_role": getattr(scenario_user.role, "value", getattr(scenario_user.role, "name", None)),
                "is_ai": bool(getattr(scenario_user, "is_ai", False)),
                "player_strategy": getattr(scenario_user, "ai_strategy", None) or getattr(scenario_user, "strategy", None),
                "player_label": f"{getattr(scenario_user, 'name', display_name)}",
            }

            order_series[node_type or node_key].append(
                {"round": round_obj.round_number, "quantity": scenario_user_period.order_placed}
            )

            totals_entry = role_totals.setdefault(
                node_type or node_key,
                {
                    "inventory": 0,
                    "backlog": 0,
                    "holding_cost": 0.0,
                    "backorder_cost": 0.0,
                    "total_cost": 0.0,
                    "orders": 0.0,
                    "nodes": set(),
                },
            )
            totals_entry["inventory"] = scenario_user_period.inventory_after
            totals_entry["backlog"] = scenario_user_period.backorders_after
            totals_entry["holding_cost"] += order_info["holding_cost"]
            totals_entry["backorder_cost"] += order_info["backorder_cost"]
            totals_entry["total_cost"] += order_info["total_cost"]
            totals_entry["orders"] += order_info["quantity"]
            totals_entry["nodes"].add(node_key)

        if isinstance(config_history_payload, list):
            for entry in config_history_payload:
                if not isinstance(entry, dict):
                    continue
                round_number = entry.get("round")
                try:
                    round_index = int(round_number)
                except (TypeError, ValueError):
                    continue
                history_entry = ensure_history_entry(round_index)
                for key in ("period_start", "period_end", "demand"):
                    if entry.get(key) is not None:
                        history_entry[key] = entry.get(key)
                for key in ("orders", "node_orders"):
                    payload = entry.get(key)
                    if isinstance(payload, dict):
                        cloned = history_entry.setdefault(key, {})
                        cloned.update(MixedScenarioService._json_clone(payload))
                node_states_payload = entry.get("node_states")
                if isinstance(node_states_payload, dict):
                    target_states = history_entry.setdefault("node_states", {})
                    for raw_key, snapshot in node_states_payload.items():
                        canonical_key = MixedScenarioService._normalise_key(raw_key) or raw_key
                        target_states[canonical_key] = MixedScenarioService._json_clone(snapshot)
                inventory_positions = entry.get("inventory_positions")
                if isinstance(inventory_positions, dict):
                    history_entry["inventory_positions"] = MixedScenarioService._json_clone(inventory_positions)
                inv_pipeline = entry.get("inventory_positions_with_pipeline")
                if isinstance(inv_pipeline, dict):
                    history_entry["inventory_positions_with_pipeline"] = MixedScenarioService._json_clone(inv_pipeline)
                backlogs_payload = entry.get("backlogs")
                if isinstance(backlogs_payload, dict):
                    history_entry["backlogs"] = MixedScenarioService._json_clone(backlogs_payload)
                type_summary_payload = entry.get("node_type_summaries")
                if isinstance(type_summary_payload, dict):
                    history_entry["node_type_summaries"] = MixedScenarioService._json_clone(type_summary_payload)
                    for type_key, summary in type_summary_payload.items():
                        canonical_type = MixedScenarioService._normalise_node_type(type_key) or type_key
                        summary_entry = role_totals.setdefault(
                            canonical_type,
                            {
                                "inventory": 0,
                                "backlog": 0,
                                "holding_cost": 0.0,
                                "backorder_cost": 0.0,
                                "total_cost": 0.0,
                                "orders": 0.0,
                                "nodes": set(),
                            },
                        )
                        if summary_entry.get("nodes"):
                            continue
                        try:
                            summary_entry["orders"] += float(summary.get("orders", 0.0) or 0.0)
                        except (TypeError, ValueError):
                            pass
                        try:
                            summary_entry["inventory"] += float(summary.get("inventory", 0.0) or 0.0)
                        except (TypeError, ValueError):
                            pass
                        try:
                            summary_entry["backlog"] += float(summary.get("backlog", 0.0) or 0.0)
                        except (TypeError, ValueError):
                            pass
                        try:
                            summary_entry["holding_cost"] += float(summary.get("holding_cost", 0.0) or 0.0)
                        except (TypeError, ValueError):
                            pass
                        try:
                            summary_entry["backorder_cost"] += float(summary.get("backlog_cost", 0.0) or 0.0)
                        except (TypeError, ValueError):
                            pass
                        try:
                            summary_entry["total_cost"] += float(summary.get("total_cost", 0.0) or 0.0)
                        except (TypeError, ValueError):
                            pass
                # If we still have no role_totals for a given node_type, derive from node_states
                if isinstance(entry.get("node_states"), dict):
                    for node_key, snapshot in entry["node_states"].items():
                        node_type = node_types_map.get(node_key) or node_key
                        summary_entry = role_totals.setdefault(
                            node_type,
                            {
                                "inventory": 0,
                                "backlog": 0,
                                "holding_cost": 0.0,
                                "backorder_cost": 0.0,
                                "total_cost": 0.0,
                                "orders": 0.0,
                                "nodes": set(),
                            },
                        )
                        summary_entry["inventory"] += float(snapshot.get("inventory", 0) or 0)
                        summary_entry["backlog"] += float(snapshot.get("backlog", 0) or 0)
                        summary_entry["orders"] += float(snapshot.get("orders", 0) or 0)
                        summary_entry["nodes"].add(node_key)
                        nodes_payload = summary.get("nodes")
                        if isinstance(nodes_payload, (list, tuple, set)):
                            for site_id in nodes_payload:
                                canonical_node = MixedScenarioService._normalise_key(site_id)
                                if canonical_node:
                                    summary_entry["nodes"].add(canonical_node)
                        summary_entry["node_count"] = len(summary_entry["nodes"])
                observed_payload = entry.get("observed_node_types")
                if isinstance(observed_payload, (list, tuple, set)):
                    for token in observed_payload:
                        canonical = MixedScenarioService._normalise_node_type(token)
                        if canonical:
                            config_history_observed_types.add(canonical)
                try:
                    history_entry["total_cost"] = float(entry.get("total_cost", history_entry.get("total_cost", 0.0)))
                except (TypeError, ValueError):
                    pass
                if round_index not in {item.get("round") for item in demand_series}:
                    period_start = history_entry.get("period_start")
                    period_end = history_entry.get("period_end")
                    demand_series.append(
                        {
                            "round": round_index,
                            "demand": history_entry.get("demand"),
                            "period_start": period_start,
                            "period_end": period_end,
                        }
                    )

        history = [history_map[round_no] for round_no in sorted(history_map.keys())]

        sankey_history_lookup: Dict[int, Dict[str, Any]] = {}
        sankey_history_raw = cfg.get("sankey_history") if isinstance(cfg, dict) else None
        if isinstance(sankey_history_raw, list):
            for entry in sankey_history_raw:
                if not isinstance(entry, dict):
                    continue
                round_token = entry.get("round")
                try:
                    round_index = int(round_token)
                except (TypeError, ValueError):
                    continue
                sankey_history_lookup[round_index] = entry

        if sankey_history_lookup and history:
            for entry in history:
                round_number = entry.get("round")
                try:
                    round_index = int(round_number)
                except (TypeError, ValueError):
                    continue
                sankey_entry = sankey_history_lookup.get(round_index)
                if not sankey_entry:
                    continue
                shipments_payload = sankey_entry.get("shipments")
                if isinstance(shipments_payload, dict):
                    entry["shipments"] = shipments_payload
                demand_token = sankey_entry.get("demand")
                if demand_token is not None and entry.get("demand") is None:
                    entry["demand"] = demand_token

        for entry in history:
            shipments_payload = entry.get("shipments")
            has_shipments = False
            if isinstance(shipments_payload, Mapping):
                has_shipments = any(
                    isinstance(targets, Mapping) and targets
                    for targets in shipments_payload.values()
                )
            if has_shipments:
                continue
            node_states_snapshot = entry.get("node_states") or {}
            reconstructed: Dict[str, Dict[str, int]] = defaultdict(dict)
            for dest_key, snapshot in node_states_snapshot.items():
                inbound_supply = []
                if isinstance(snapshot, Mapping):
                    inbound_supply = snapshot.get("inbound_supply") or []
                if not isinstance(inbound_supply, (list, tuple)):
                    continue
                dest_canonical = MixedScenarioService._normalise_key(dest_key)
                if not dest_canonical:
                    continue
                for shipment in inbound_supply:
                    if not isinstance(shipment, Mapping):
                        continue
                    source_key = MixedScenarioService._normalise_key(shipment.get("source"))
                    if not source_key:
                        continue
                    try:
                        qty = int(shipment.get("quantity") or 0)
                    except (TypeError, ValueError):
                        qty = 0
                    if qty <= 0:
                        continue
                    current = reconstructed[source_key].get(dest_canonical, 0)
                    reconstructed[source_key][dest_canonical] = current + qty
            if reconstructed:
                entry["shipments"] = {src: dict(targets) for src, targets in reconstructed.items()}

        for entry in history:
            round_number = entry.get("round")
            try:
                round_index = int(round_number)
            except (TypeError, ValueError):
                continue
            node_states = entry.get("node_states") or {}
            node_orders_entry = entry.get("node_orders") or entry.get("orders") or {}
            if isinstance(node_orders_entry, dict):
                for node_key, quantity in node_orders_entry.items():
                    target_key = node_types_map.get(node_key) or node_key
                    if isinstance(quantity, dict):
                        qty_candidate = quantity.get("quantity")
                    else:
                        qty_candidate = quantity
                    try:
                        qty_val = int(qty_candidate)
                    except (TypeError, ValueError):
                        continue
                    series = order_series[target_key]
                    if any(item.get("round") == round_index for item in series):
                        continue
                    series.append({"round": round_index, "quantity": qty_val})

            for node_key, state in node_states.items():
                type_key = node_types_map.get(node_key) or MixedScenarioService._normalise_node_type(node_key)
                if type_key:
                    observed_node_types.add(type_key)
                totals_entry = role_totals.setdefault(
                    type_key or node_key,
                    {
                        "inventory": 0,
                        "backlog": 0,
                        "holding_cost": 0.0,
                        "backorder_cost": 0.0,
                        "total_cost": 0.0,
                        "orders": 0.0,
                        "nodes": set(),
                    },
                )
                if node_key in totals_entry["nodes"]:
                    continue
                totals_entry["inventory"] = state.get("inventory", totals_entry.get("inventory", 0))
                totals_entry["backlog"] = state.get("backlog", totals_entry.get("backlog", 0))
                try:
                    totals_entry["holding_cost"] += float(state.get("holding_cost", 0.0) or 0.0)
                except (TypeError, ValueError):
                    pass
                try:
                    totals_entry["backorder_cost"] += float(state.get("backorder_cost", 0.0) or 0.0)
                except (TypeError, ValueError):
                    pass
                try:
                    totals_entry["total_cost"] += float(state.get("total_cost", 0.0) or 0.0)
                except (TypeError, ValueError):
                    pass
                totals_entry["nodes"].add(node_key)
                last_order = state.get("last_order")
                try:
                    totals_entry["orders"] += float(last_order or 0.0)
                except (TypeError, ValueError):
                    pass

        # Merge any engine-derived totals so we retain upstream metrics if present.
        engine = cfg.get("engine_state", {})
        if engine:
            for node_name, state in engine.items():
                node_key = MixedScenarioService._normalise_key(node_name)
                type_key = node_types_map.get(node_key) or MixedScenarioService._normalise_node_type(node_name)
                if type_key:
                    observed_node_types.add(type_key)
                totals_entry = role_totals.setdefault(
                    type_key or node_key,
                    {
                        "inventory": 0,
                        "backlog": 0,
                        "holding_cost": 0.0,
                        "backorder_cost": 0.0,
                        "total_cost": 0.0,
                        "orders": 0.0,
                        "nodes": set(),
                    },
                )
            totals_entry.setdefault("inventory", state.get("inventory", totals_entry.get("inventory", 0)))
            totals_entry.setdefault("backlog", state.get("backlog", totals_entry.get("backlog", 0)))
            totals_entry.setdefault(
                "holding_cost",
                float(state.get("holding_cost_total", state.get("holding_cost", totals_entry.get("holding_cost", 0.0))))
            )
            totals_entry.setdefault(
                "backorder_cost",
                float(
                    state.get(
                        "backorder_cost_total",
                        state.get("backorder_cost", totals_entry.get("backorder_cost", 0.0)),
                    )
                )
            )
            totals_entry.setdefault(
                "total_cost", float(state.get("total_cost", totals_entry.get("total_cost", 0.0)))
            )
            totals_entry["nodes"].add(node_key)

        total_cost = sum(float(v.get("total_cost", 0.0)) for v in role_totals.values())
        config_payload = MixedScenarioService._json_clone(cfg)
        supply_chain_name = config_payload.get("supply_chain_name")
        if not supply_chain_name:
            supply_chain_obj = getattr(game, "supply_chain_config", None)
            if supply_chain_obj is not None:
                supply_chain_name = getattr(supply_chain_obj, "name", None)
                if supply_chain_name:
                    config_payload.setdefault("supply_chain_name", supply_chain_name)

        formatted_totals: Dict[str, Dict[str, Any]] = {}
        for type_key, values in role_totals.items():
            nodes_list = sorted(values.get("nodes", []))
            formatted_totals[type_key] = {
                "inventory": values.get("inventory", 0),
                "backlog": values.get("backlog", 0),
                "holding_cost": values.get("holding_cost", 0.0),
                "backorder_cost": values.get("backorder_cost", 0.0),
                "total_cost": values.get("total_cost", 0.0),
                "orders": values.get("orders", 0.0),
                "nodes": nodes_list,
                "node_count": len(nodes_list) if nodes_list else 0,
            }

        if config_history_observed_types:
            observed_node_types.update(config_history_observed_types)
        observed_payload = (
            observed_node_types
            if observed_node_types
            else {MixedScenarioService._normalise_node_type(key) for key in formatted_totals.keys()}
        )

        # Build canonical lane summary so the UI always shows configured connections.
        lane_defs = cfg.get("lanes") or []
        lane_totals: Dict[Tuple[str, str], int] = defaultdict(int)
        for entry in config_history_payload:
            shipments = entry.get("shipments") or {}
            if not isinstance(shipments, Mapping):
                continue
            for raw_source, targets in shipments.items():
                source_key = MixedScenarioService._normalise_key(raw_source)
                if not source_key:
                    continue
                if not isinstance(targets, Mapping):
                    continue
                for raw_dest, qty in targets.items():
                    dest_key = MixedScenarioService._normalise_key(raw_dest)
                    if not dest_key:
                        continue
                    try:
                        qty_val = int(qty or 0)
                    except (TypeError, ValueError):
                        continue
                    if qty_val <= 0:
                        continue
                    lane_totals[(source_key, dest_key)] += qty_val

        node_display_names = node_display_names or {}
        lane_payloads: List[Dict[str, Any]] = []
        for lane in lane_defs:
            upstream = MixedScenarioService._canonical_role(lane.get("from") or lane.get("upstream") or lane.get("from_node_id"))
            downstream = MixedScenarioService._canonical_role(lane.get("to") or lane.get("downstream") or lane.get("to_node_id"))
            if not upstream or not downstream:
                continue
            total_shipped = lane_totals.get((upstream, downstream), 0)
            lane_payloads.append(
                {
                    "from": node_display_names.get(upstream, upstream.replace("_", " ").title()),
                    "to": node_display_names.get(downstream, downstream.replace("_", " ").title()),
                    "total_shipped": total_shipped,
                }
            )

        return {
            "scenario_id": scenario_id,
            "name": game.name,
            "status": str(game.status),
            "progression_mode": cfg.get("progression_mode", "supervised"),
            "supply_chain_config_id": supply_chain_config_id,
            "supply_chain_name": supply_chain_name,
            "totals": formatted_totals,
            "total_cost": total_cost,
            "history": history,
            "sankey_history": MixedScenarioService._json_clone(cfg.get("sankey_history") or []),
            "order_series": {
                role: sorted(series, key=lambda item: item["round"])
                for role, series in order_series.items()
            },
            "demand_series": demand_series,
            "rounds_completed": len(history),
            "time_bucket": bucket.value,
            "start_date": start_date.isoformat() if start_date else None,
            "node_catalog": node_catalog,
            "site_type_definitions": site_type_definitions,
            "site_type_labels": site_type_labels,
            "node_types_normalized": node_types_map,
            "observed_node_types": sorted(observed_payload),
            "node_display_names": node_display_names,
            "lanes": lane_payloads,
            "config": config_payload,
        }
    
    def calculate_demand(self, game: Game, round_number: int) -> int:
        """Calculate demand for a given round based on the game's demand pattern."""

        cfg = dict(getattr(game, "config", {}) or {})

        sc_snapshot: Optional[Dict[str, Any]] = None

        def _ensure_snapshot() -> Optional[Dict[str, Any]]:
            nonlocal sc_snapshot
            if sc_snapshot is None:
                sc_snapshot = self._supply_chain_snapshot(cfg.get('supply_chain_config_id'))
            return sc_snapshot

        if not cfg.get('market_demands'):
            snapshot = _ensure_snapshot()
            if snapshot and snapshot.get('market_demands'):
                cfg['market_demands'] = MixedScenarioService._json_clone(snapshot.get('market_demands'))
        if not cfg.get('items'):
            snapshot = _ensure_snapshot()
            if snapshot and snapshot.get('items'):
                cfg['items'] = MixedScenarioService._json_clone(snapshot.get('items'))
        if not cfg.get('markets'):
            snapshot = _ensure_snapshot()
            if snapshot and snapshot.get('markets'):
                cfg['markets'] = MixedScenarioService._json_clone(snapshot.get('markets'))

        node_policies = cfg.get('node_policies', {})
        lane_views = self._build_lane_views(node_policies, cfg)

        demand_map, total = MixedScenarioService._compute_market_round_demand(
            game,
            cfg,
            round_number,
            lane_views,
        )

        game.config = cfg
        try:
            if cfg.get('demand_pattern'):
                game.demand_pattern = cfg.get('demand_pattern')
        except AttributeError:
            pass
        return int(total)
    
    def list_games(
        self,
        current_user: User,
        status: Optional[GameStatus] = None,
    ) -> List[GameInDBBase]:
        """Return games visible to the requesting user, handling legacy schemas."""

        columns = set(self._get_game_columns())
        base_projection = [
            ("id", "id"),
            ("name", "name"),
            ("description", "description"),
            ("status", "status"),
            ("current_round", "current_round"),
            ("max_rounds", "max_rounds"),
            ("created_at", "created_at"),
            ("updated_at", "updated_at"),
            ("started_at", "started_at"),
            ("completed_at", "completed_at"),
            ("finished_at", "finished_at"),
            ("demand_pattern", "demand_pattern"),
            ("config", "config"),
            ("created_by", "created_by"),
            ("tenant_id", "tenant_id"),
            ("supply_chain_config_id", "supply_chain_config_id"),
            ("time_bucket", "time_bucket"),
            ("start_date", "start_date"),
            ("current_period_start", "current_period_start"),
        ]

        select_parts: List[str] = []
        for column_name, alias in base_projection:
            if column_name in columns:
                select_parts.append(f"g.{column_name} AS {alias}")
            else:
                select_parts.append(f"NULL AS {alias}")

        select_clause = ", ".join(select_parts)
        query = f"SELECT {select_clause} FROM games g"

        filters: List[str] = []
        params: Dict[str, Any] = {}

        if status:
            status_values = [
                value
                for value in self._schema_status_to_db_values(status)
                if value is not None
            ]
            if status_values:
                placeholders = []
                for idx, value in enumerate(status_values):
                    key = f"status_{idx}"
                    placeholders.append(f":{key}")
                    params[key] = value
                filters.append(f"g.status IN ({', '.join(placeholders)})")

        user_type = self._resolve_user_type(current_user)
        if not current_user.is_superuser and user_type != UserTypeEnum.SYSTEM_ADMIN:
            tenant_id = getattr(current_user, "tenant_id", None)
            if user_type == UserTypeEnum.TENANT_ADMIN and tenant_id and "tenant_id" in columns:
                filters.append("g.tenant_id = :tenant_id")
                params["tenant_id"] = tenant_id
            elif "created_by" in columns:
                filters.append("g.created_by = :created_by")
                params["created_by"] = current_user.id

        if filters:
            query += " WHERE " + " AND ".join(filters)

        order_column = "created_at" if "created_at" in columns else "id"
        query += f" ORDER BY g.{order_column} DESC"

        from sqlalchemy import text

        result = self.db.execute(text(query), params)

        games: List[GameInDBBase] = []
        for row in result:
            record = dict(row._mapping)
            if record.get("completed_at") is None and record.get("finished_at") is not None:
                record["completed_at"] = record.get("finished_at")
            games.append(self._serialize_game(SimpleNamespace(**record)))

        return games
    
    def get_game_state(self, scenario_id: int) -> GameState:
        """Get the current state of a game."""
        from sqlalchemy import text
        
        # Get the game
        game_query = """
            SELECT g.id,
                   g.name,
                   g.status,
                   g.current_round,
                   g.max_rounds,
                   g.created_at,
                   g.updated_at,
                   g.demand_pattern,
                   g.config,
                   g.role_assignments,
                   g.supply_chain_config_id,
                   g.time_bucket,
                   g.start_date,
                   g.current_period_start,
                   sc.name AS supply_chain_name
            FROM games AS g
            LEFT JOIN supply_chain_configs AS sc
                ON g.supply_chain_config_id = sc.id
            WHERE g.id = :scenario_id
        """
        game_result = self.db.execute(text(game_query), {"scenario_id": scenario_id}).first()

        if not game_result:
            raise ValueError("Game not found")

        game_record = dict(game_result._mapping)
        game_obj = self.db.query(Game).filter(Game.id == scenario_id).first()
        bucket = normalize_time_bucket(game_record.get("time_bucket", TimeBucket.WEEK))
        start_date = game_record.get("start_date") or DEFAULT_START_DATE
        current_period_start = game_record.get("current_period_start")
        
        # Get all scenario_users for the game, including node mappings and strategies
        scenario_users_query = """
            SELECT p.id,
                   p.name,
                   p.role,
                   p.is_ai,
                   p.ai_strategy,
                   p.node_key,
                   COALESCE(pi.current_stock, 0) as current_stock,
                   COALESCE(pi.incoming_shipments, '[]') as incoming_shipments,
                   COALESCE(pi.backorders, 0) as backorders
            FROM scenario_users p
            LEFT JOIN player_inventories pi ON p.id = pi.scenario_user_id
            WHERE p.scenario_id = :scenario_id
        """
        scenario_users_rows = list(self.db.execute(text(scenario_users_query), {"scenario_id": scenario_id}).mappings())

        scenario_user_states = []
        node_scenario_user_map: Dict[str, Dict[str, Any]] = {}
        scenario_user_lookup: Dict[int, Dict[str, Any]] = {}
        for row in scenario_users_rows:
            incoming_shipments_raw = row.get("incoming_shipments")
            if isinstance(incoming_shipments_raw, str):
                try:
                    incoming_shipments = json.loads(incoming_shipments_raw)
                except json.JSONDecodeError:
                    incoming_shipments = []
            else:
                incoming_shipments = incoming_shipments_raw or []

            role_token = row.get("role")
            try:
                role_value = ScenarioUserRole(role_token) if role_token else ScenarioUserRole.RETAILER
            except Exception:
                role_value = ScenarioUserRole.RETAILER

            node_key = MixedScenarioService._normalise_key(row.get("node_key") or role_token)
            meta_payload = {
                "scenario_user_id": row.get("id"),
                "scenario_user_name": row.get("name"),
                "player_role": role_token,
                "player_strategy": row.get("ai_strategy"),
                "is_ai": bool(row.get("is_ai")),
            }
            if meta_payload["scenario_user_id"] is not None:
                scenario_user_lookup[meta_payload["scenario_user_id"]] = meta_payload
            if node_key and node_key not in node_scenario_user_map:
                node_scenario_user_map[node_key] = meta_payload

            scenario_user_states.append(ScenarioUserState(
                id=row.get("id"),
                name=row.get("name"),
                role=role_value,
                is_ai=bool(row.get("is_ai")),
                current_stock=row.get("current_stock", 0),
                incoming_shipments=incoming_shipments,
                backorders=row.get("backorders", 0),
                total_cost=0,  # Placeholder until detailed costing is added
                node_key=node_key,
            ))

        current_round = self.get_current_round(scenario_id)
        
        # Create a default demand pattern if none exists
        try:
            raw_pattern = (
                json.loads(game_record.get("demand_pattern"))
                if game_record.get("demand_pattern")
                else DEFAULT_DEMAND_PATTERN.copy()
            )
        except (json.JSONDecodeError, TypeError):
            raw_pattern = DEFAULT_DEMAND_PATTERN.copy()
        demand_pattern = normalize_demand_pattern(raw_pattern)

        # Unpack optional config
        node_policies = {}
        system_config = {}
        pricing_config = {}
        global_policy = {}
        progression_mode = "supervised"
        supply_chain_config_id: Optional[int] = None
        supply_chain_name: Optional[str] = None
        cfg, cfg_upgraded = self._upgrade_json_value(
            game_record.get("config") or {},
            dict,
            default_factory=dict,
            context="MixedScenarioService.get_game_state config",
            field_name="config",
            game=game_obj,
            auto_commit=True,
        )
        config_payload = MixedScenarioService._json_clone(cfg)
        role_assignments_raw, roles_upgraded = self._upgrade_json_value(
            game_record.get("role_assignments") or {},
            dict,
            default_factory=dict,
            context="MixedScenarioService.get_game_state role_assignments",
            field_name="role_assignments",
            game=game_obj,
            auto_commit=True,
        )
        if role_assignments_raw:
            config_payload.setdefault("role_assignments", role_assignments_raw)
        try:
            if isinstance(cfg, dict):
                progression_mode = cfg.get("progression_mode", progression_mode) or "supervised"
                node_policies = cfg.get('node_policies', {})
                system_config = cfg.get('system_config', {})
                pricing_config = cfg.get('pricing_config', {})
                global_policy = cfg.get('global_policy', {})
                supply_chain_config_id = cfg.get('supply_chain_config_id')
                supply_chain_name = cfg.get('supply_chain_name')
            # Also surface nested in demand_pattern.params if present
            if not node_policies:
                node_policies = demand_pattern.get('params', {}).get('node_policies', {}) if isinstance(demand_pattern, dict) else {}
            if not system_config:
                system_config = demand_pattern.get('params', {}).get('system_config', {}) if isinstance(demand_pattern, dict) else {}
        except Exception:
            pass

        if supply_chain_config_id is None:
            supply_chain_config_id = game_record.get("supply_chain_config_id")
        if not supply_chain_name:
            supply_chain_name = game_record.get("supply_chain_name")

        supply_chain_snapshot = self._supply_chain_snapshot(supply_chain_config_id)

        lane_views = self._build_lane_views(node_policies, cfg)
        node_types_map = lane_views.get("node_types", {})
        node_sequence = lane_views.get("node_sequence") or []
        engine_state = cfg.get("engine_state") or {}

        node_display_names: Dict[str, str] = {}
        for node in cfg.get("nodes") or []:
            label = node.get("name") or node.get("id")
            key = MixedScenarioService._normalise_key(label)
            if key:
                node_display_names.setdefault(key, str(label))

        def _resolve_scenario_user_meta(node_key: str) -> Optional[Dict[str, Any]]:
            canonical = MixedScenarioService._normalise_key(node_key)
            if not canonical:
                return None
            direct = node_scenario_user_map.get(canonical)
            if direct:
                return direct
            assignment = role_assignments_raw.get(canonical)
            if assignment:
                scenario_user_id = assignment.get("scenario_user_id")
                if scenario_user_id in scenario_user_lookup:
                    return scenario_user_lookup[scenario_user_id]
            return None

        history_payload: List[Dict[str, Any]] = []
        current_round_number = (
            current_round.round_number if current_round is not None else game_record.get("current_round", 0)
        )

        if isinstance(engine_state, dict) and engine_state:
            node_states_payload: Dict[str, Dict[str, Any]] = {}
            for raw_node, snapshot in engine_state.items():
                node_key = MixedScenarioService._normalise_key(raw_node)
                if not node_key:
                    continue
                actor_meta = _resolve_scenario_user_meta(node_key) or {}
                state_payload = {
                    "inventory": snapshot.get("inventory"),
                    "backlog": snapshot.get("backlog"),
                    "info_queue": list(snapshot.get("info_queue") or []),
                    "ship_queue": list(snapshot.get("ship_queue") or []),
                    "incoming_shipments": list(snapshot.get("incoming_shipments") or []),
                    "inbound_demand": list(snapshot.get("inbound_demand") or []),
                    "on_order": snapshot.get("on_order"),
                    "display_name": node_display_names.get(node_key, raw_node.replace("_", " ").title()),
                    "type": node_types_map.get(node_key),
                }
                if actor_meta:
                    state_payload.update(actor_meta)
                node_states_payload[node_key] = state_payload

            effective_sequence = list(node_sequence) or list(node_states_payload.keys())
            history_payload.append(
                {
                    "round": current_round_number,
                    "node_sequence": effective_sequence,
                    "current_node": effective_sequence[0] if effective_sequence else None,
                    "node_states": node_states_payload,
                }
            )

        if not history_payload:
            fallback_sequence = list(node_sequence) or list(node_display_names.keys())
            if not fallback_sequence:
                fallback_sequence = [ps.node_key for ps in scenario_user_states if ps.node_key]
            node_states_payload: Dict[str, Dict[str, Any]] = {}
            for raw_node in fallback_sequence:
                node_key = MixedScenarioService._normalise_key(raw_node)
                if not node_key:
                    continue
                actor_meta = _resolve_scenario_user_meta(node_key) or {}
                node_states_payload[node_key] = {
                    "inventory": None,
                    "backlog": None,
                    "info_queue": [],
                    "ship_queue": [],
                    "incoming_shipments": [],
                    "inbound_demand": [],
                    "on_order": None,
                    "display_name": node_display_names.get(node_key, node_key.replace("_", " ").title()),
                    "type": node_types_map.get(node_key),
                    **actor_meta,
                }
            history_payload.append(
                {
                    "round": current_round_number,
                    "node_sequence": fallback_sequence,
                    "current_node": fallback_sequence[0] if fallback_sequence else None,
                    "node_states": node_states_payload,
                }
            )

        return GameState(
            id=game_record["id"],
            name=game_record["name"],
            status=game_record["status"],
            current_round=game_record["current_round"],
            max_rounds=game_record["max_rounds"],
            progression_mode=progression_mode,
            scenario_users=scenario_user_states,
            current_demand=None,  # Will be set by the round
            round_started_at=None,  # Will be set by the round
            round_ends_at=None,  # Will be set by the round
            created_at=game_record["created_at"],
            updated_at=game_record["updated_at"],
            started_at=None,
            completed_at=None,
            created_by=None,
            is_public=False,
            description="",
            demand_pattern=demand_pattern,
            supply_chain_config_id=supply_chain_config_id,
            supply_chain_name=supply_chain_name,
            node_policies=node_policies,
            system_config=system_config,
            pricing_config=pricing_config,
            global_policy=global_policy,
            config=config_payload,
            supply_chain_config=supply_chain_snapshot,
            time_bucket=bucket,
            start_date=start_date,
            current_period_start=current_period_start,
            history=history_payload,
        )
        # Validate optional global policy if provided
        if getattr(game_data, 'global_policy', None):
            gp = game_data.global_policy
            for k in ['order_leadtime','supply_leadtime','init_inventory','holding_cost','backlog_cost','max_inbound_per_link','max_order']:
                if k in gp and gp[k] is not None:
                    _check_range(k, float(gp[k]))
