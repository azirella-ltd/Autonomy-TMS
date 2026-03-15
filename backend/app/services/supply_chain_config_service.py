"""
Service for managing supply chain configurations and their integration with game initialization.
"""
from typing import Dict, Any, List, Optional, Tuple, Set
from sqlalchemy.orm import Session
from datetime import datetime
import json
import math
import re
import logging

from sqlalchemy.orm import Session, joinedload

from app.core.demand_patterns import (
    DEFAULT_LOGNORMAL_PARAMS,
    DemandPatternType,
    normalize_demand_pattern,
)
from app.models.supply_chain_config import (
    SupplyChainConfig,
    Site,
    TransportationLane,  # AWS SC DM standard
    Market,
    MarketDemand,
    NodeType,
)
from app.models.sc_entities import Product, ProductBom
# Temporary compatibility layer during migration
from app.models.compatibility import Item, ProductSiteConfig
from app.core.time_buckets import normalize_time_bucket, TimeBucket, DEFAULT_START_DATE
from app.services.mixed_scenario_service import MixedScenarioService
from app.schemas.scenario import ScenarioCreate, NodePolicy, DemandPattern

# Aliases for backwards compatibility
GameCreate = ScenarioCreate
from app.schemas.supply_chain_config import (
    SupplyChainConfigCreate,
    # ItemCreate, ProductSiteConfigCreate - REMOVED: use Product schemas
    SiteCreate,
    TransportationLaneCreate,  # AWS SC DM standard
    MarketDemandCreate,
)

DEFAULT_ROLE_PRICING: Dict[str, Dict[str, float]] = {
    "retailer": {"selling_price": 100.0, "standard_cost": 80.0},
    "wholesaler": {"selling_price": 75.0, "standard_cost": 60.0},
    "distributor": {"selling_price": 60.0, "standard_cost": 45.0},
    "manufacturer": {"selling_price": 45.0, "standard_cost": 30.0},
    "inventory": {"selling_price": 90.0, "standard_cost": 72.0},
}

logger = logging.getLogger(__name__)


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _coerce_pattern_dict(payload: Any) -> Dict[str, Any]:
    """Convert stored demand pattern payloads into dictionaries."""

    if isinstance(payload, dict):
        if "demand_type" in payload and "type" not in payload:
            converted = {
                "type": payload.get("demand_type", DemandPatternType.CLASSIC.value),
                "params": payload.get("parameters") or payload.get("params") or {},
            }
            for key in ("variability", "seasonality", "trend", "parameters", "params"):
                if key in payload:
                    converted[key] = payload[key]
            return converted
        return payload
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
            if isinstance(data, dict):
                return data
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return {}


def _range_bounds(range_value: Any) -> Tuple[Optional[float], Optional[float]]:
    if isinstance(range_value, dict):
        return _to_float(range_value.get("min")), _to_float(range_value.get("max"))
    value = _to_float(range_value)
    return value, value


def _range_midpoint(range_value: Any, fallback: float) -> float:
    low, high = _range_bounds(range_value)
    if low is None and high is None:
        return fallback
    if low is None:
        return high if high is not None else fallback
    if high is None:
        return low
    return (low + high) / 2.0


def _distribution_expected_value(distribution: Any, fallback: float) -> float:
    """Return the expected value for a distribution payload."""

    if distribution is None:
        return fallback
    if isinstance(distribution, str):
        try:
            distribution = json.loads(distribution)
        except (TypeError, ValueError, json.JSONDecodeError):
            return fallback
    if not isinstance(distribution, dict):
        return fallback

    dtype = str(distribution.get("type") or "deterministic").lower()

    if dtype == "deterministic":
        value = _to_float(distribution.get("value"))
        return value if value is not None else fallback
    if dtype == "uniform":
        minimum = _to_float(distribution.get("minimum"))
        maximum = _to_float(distribution.get("maximum"))
        if minimum is not None and maximum is not None:
            return (minimum + maximum) / 2.0
        if minimum is not None:
            return minimum
        if maximum is not None:
            return maximum
    if dtype == "normal":
        mean = _to_float(distribution.get("mean"))
        if mean is not None:
            return mean
    if dtype == "lognormal":
        mean = _to_float(distribution.get("mean"))
        if mean is not None:
            return mean
    if dtype == "triangular":
        minimum = _to_float(distribution.get("minimum"))
        mode = _to_float(distribution.get("value"))
        maximum = _to_float(distribution.get("maximum"))
        if None not in (minimum, mode, maximum):
            return (minimum + mode + maximum) / 3.0

    return fallback


def _distribution_bounds(distribution: Any) -> Tuple[Optional[float], Optional[float]]:
    """Return approximate lower and upper bounds for a distribution payload."""

    if distribution is None:
        return None, None
    if isinstance(distribution, str):
        try:
            distribution = json.loads(distribution)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None, None
    if not isinstance(distribution, dict):
        return None, None

    dtype = str(distribution.get("type") or "deterministic").lower()

    if dtype == "deterministic":
        value = _to_float(distribution.get("value"))
        return value, value
    if dtype == "uniform":
        return (
            _to_float(distribution.get("minimum")),
            _to_float(distribution.get("maximum")),
        )
    if dtype == "normal":
        mean = _to_float(distribution.get("mean"))
        std = _to_float(distribution.get("standard_deviation"))
        if mean is not None and std is not None:
            return mean - 3.0 * std, mean + 3.0 * std
        if mean is not None:
            return mean, mean
    if dtype == "lognormal":
        mean = _to_float(distribution.get("mean"))
        sigma = _to_float(distribution.get("sigma"))
        if mean is not None and sigma is not None:
            upper = max(mean * (1.0 + 3.0 * sigma), mean)
            return 0.0, upper
        if mean is not None:
            return 0.0, max(mean * 2.0, mean)
    if dtype == "triangular":
        minimum = _to_float(distribution.get("minimum"))
        maximum = _to_float(distribution.get("maximum"))
        return minimum, maximum

    return None, None


def _time_bucket_to_days(bucket: TimeBucket) -> float:
    if bucket == TimeBucket.DAY:
        return 1.0
    if bucket == TimeBucket.WEEK:
        return 7.0
    if bucket == TimeBucket.MONTH:
        # Approximate monthly buckets as 30 days in line with Supply Chain guidance.
        return 30.0
    return 1.0


def _leadtime_to_buckets(value: Optional[float], bucket: TimeBucket) -> Optional[float]:
    if value is None:
        return None
    days_per_bucket = _time_bucket_to_days(bucket)
    if days_per_bucket <= 0:
        return float(value)
    return float(value) / days_per_bucket


def _update_min(current: Optional[float], value: Optional[float]) -> Optional[float]:
    if value is None:
        return current
    if current is None or value < current:
        return value
    return current


def _update_max(current: Optional[float], value: Optional[float]) -> Optional[float]:
    if value is None:
        return current
    if current is None or value > current:
        return value
    return current


def _clone_json(payload: Any) -> Any:
    """Return a deep JSON-serialisable clone of a payload."""

    try:
        return json.loads(json.dumps(payload))
    except (TypeError, ValueError):
        return payload


def _normalize_site_type_definitions(payload: Any) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Normalise site type definitions into serialisable dicts and lookup map."""

    def _canonical_master(master: Any, node_type: str) -> str:
        token = str(master or "").strip().lower()
        node_type_lower = str(node_type or "").strip().lower()
        if token in {"market_demand", "market", "demand"}:
            return "market_demand"
        if token in {"market_supply", "supply"}:
            return "market_supply"
        if token == "manufacturer":
            return "manufacturer"
        # Playable nodes default to inventory master type
        if node_type_lower in {"retailer", "wholesaler", "distributor", "inventory", "supplier"}:
            return "inventory"
        return "market_demand"

    if not payload:
        raise ValueError("Supply chain configuration must include site type definitions persisted in the database")

    definitions: List[Dict[str, Any]] = []
    label_map: Dict[str, str] = {}

    if isinstance(payload, list):
        for index, entry in enumerate(payload):
            if isinstance(entry, dict):
                node_type = str(entry.get("type") or "")
                label = str(entry.get("label") or "").strip() or node_type.replace("_", " ").title()
                order = entry.get("order")
                is_required = bool(entry.get("is_required", node_type in {"market_supply", "market_demand"}))
                master_type = _canonical_master(entry.get("master_type"), node_type)
            else:
                node_type = str(getattr(entry, "type", "") or "")
                label = str(getattr(entry, "label", "") or "").strip() or node_type.replace("_", " ").title()
                order = getattr(entry, "order", None)
                is_required = bool(getattr(entry, "is_required", node_type in {"market_supply", "market_demand"}))
                master_type = _canonical_master(getattr(entry, "master_type", None), node_type)

            if not node_type:
                continue

            if not isinstance(order, int):
                order = index

            payload_entry = {
                "type": node_type,
                "label": label,
                "order": order,
                "is_required": is_required,
                "master_type": master_type,
            }
            definitions.append(payload_entry)
            label_map[node_type] = label

    if not definitions:
        raise ValueError("Supply chain configuration must include at least one site type definition")

    return definitions, label_map


class SupplyChainConfigService:
    """Service for managing supply chain configurations and game integration."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_game_from_config(self, config_id: int, game_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a game configuration based on a supply chain configuration.
        
        Args:
            config_id: ID of the supply chain configuration
            game_data: Base game data (name, description, etc.)
            
        Returns:
            Dict containing the game configuration
        """
        # Get the supply chain configuration
        config = self.db.query(SupplyChainConfig).filter(
            SupplyChainConfig.id == config_id
        ).first()

        if not config:
            raise ValueError(f"Supply chain configuration with ID {config_id} not found")

        time_bucket = normalize_time_bucket(getattr(config, "time_bucket", TimeBucket.WEEK))
        
        # Get all related data
        products = self.db.query(Product).filter(Product.config_id == config_id).all()
        nodes = self.db.query(Site).filter(Site.config_id == config_id).all()
        lanes = self.db.query(TransportationLane).filter(TransportationLane.config_id == config_id).all()
        markets = self.db.query(Market).filter(Market.config_id == config_id).all()
        # Note: ProductSiteConfig functionality migrated to InvPolicy (SC)
        # product_site_configs = self.db.query(ProductSiteConfig).filter(...).all()
        market_demand_query = self.db.query(MarketDemand)
        options_method = getattr(market_demand_query, "options", None)
        if callable(options_method):
            try:
                market_demand_query = options_method(joinedload(MarketDemand.market))
            except AttributeError:
                # Basic stubs used in tests may not implement SQLAlchemy's full API
                pass
        market_demands = (
            market_demand_query
            .filter(MarketDemand.config_id == config_id)
            .all()
        )

        if not markets:
            raise ValueError("Supply chain configuration must define at least one market")
        if not market_demands:
            raise ValueError("Supply chain configuration must define demand patterns for all item/market pairs")

        demand_lookup = {(md.product_id, md.market_id): md for md in market_demands}
        missing_pairs = [
            (item_obj.name, market.name)
            for item_obj in items
            for market in markets
            if (item_obj.id, market.id) not in demand_lookup
        ]

        if missing_pairs:
            missing_str = ", ".join(f"{item_name} → {market_name}" for item_name, market_name in missing_pairs)
            raise ValueError(
                "Missing demand patterns for item/market pairs: " + missing_str
            )
        
        # Map site types to scenario_user roles
        role_mapping = {
            "retailer": "retailer",
            "wholesaler": "wholesaler",
            "distributor": "distributor",
            "factory": "manufacturer",
            "manufacturer": "manufacturer",
            "inventory": "inventory",
            "case_mfg": "manufacturer",
            "six_pack_mfg": "manufacturer",
            "bottle_mfg": "manufacturer",
        }

        lanes_by_downstream: Dict[int, List[TransportationLane]] = {}
        for lane in lanes:
            lanes_by_downstream.setdefault(lane.to_site_id, []).append(lane)

        # Aggregate inventory and cost ranges
        if not product_site_configs:
            raise ValueError("Supply chain configuration must include item-node configurations with inventory and cost ranges")
        min_init_inventory: Optional[float] = None
        max_init_inventory: Optional[float] = None
        min_holding_cost: Optional[float] = None
        max_holding_cost: Optional[float] = None
        min_backlog_cost: Optional[float] = None
        max_backlog_cost: Optional[float] = None
        init_midpoints: List[float] = []
        holding_midpoints: List[float] = []
        backlog_midpoints: List[float] = []

        for inc in product_site_configs:
            init_lo, init_hi = _range_bounds(inc.initial_inventory_range)
            if None in (init_lo, init_hi):
                raise ValueError(f"Initial inventory range must include min and max for item {inc.product_id} on node {inc.site_id}")
            min_init_inventory = _update_min(min_init_inventory, init_lo)
            max_init_inventory = _update_max(max_init_inventory, init_hi)
            init_midpoints.append(_range_midpoint(inc.initial_inventory_range, init_lo))

            hold_lo, hold_hi = _range_bounds(inc.holding_cost_range)
            if None in (hold_lo, hold_hi):
                raise ValueError(f"Holding cost range must include min and max for item {inc.product_id} on node {inc.site_id}")
            min_holding_cost = _update_min(min_holding_cost, hold_lo)
            max_holding_cost = _update_max(max_holding_cost, hold_hi)
            holding_midpoints.append(_range_midpoint(inc.holding_cost_range, hold_lo))

            back_lo, back_hi = _range_bounds(inc.backlog_cost_range)
            if None in (back_lo, back_hi):
                raise ValueError(f"Backlog cost range must include min and max for item {inc.product_id} on node {inc.site_id}")
            min_backlog_cost = _update_min(min_backlog_cost, back_lo)
            max_backlog_cost = _update_max(max_backlog_cost, back_hi)
            backlog_midpoints.append(_range_midpoint(inc.backlog_cost_range, back_lo))

        if not init_midpoints or not holding_midpoints or not backlog_midpoints:
            raise ValueError("Inventory, holding cost, and backlog cost ranges must be provided for item-node configurations")

        default_init_inventory = sum(init_midpoints) / len(init_midpoints)
        default_holding_cost = sum(holding_midpoints) / len(holding_midpoints)
        default_backlog_cost = sum(backlog_midpoints) / len(backlog_midpoints)
        if any(
            value is None
            for value in (
                min_init_inventory,
                max_init_inventory,
                min_holding_cost,
                max_holding_cost,
                min_backlog_cost,
                max_backlog_cost,
            )
        ):
            raise ValueError("Inventory and cost ranges must include min and max values for all item-node configurations")

        min_supply_lead_days: Optional[float] = None
        max_supply_lead_days: Optional[float] = None
        min_order_lead_days: Optional[float] = None
        max_order_lead_days: Optional[float] = None
        max_lane_capacity: Optional[float] = None
        supply_midpoints_days: List[float] = []
        order_midpoints_days: List[float] = []
        for lane in lanes:
            capacity_val = _to_float(lane.capacity)
            if capacity_val is None or capacity_val <= 0:
                raise ValueError(f"Transportation lane {lane.id} must define a positive capacity value")
            max_lane_capacity = _update_max(max_lane_capacity, capacity_val)

            supply_bounds = _distribution_bounds(getattr(lane, "supply_lead_time", None))
            if supply_bounds == (None, None):
                supply_bounds = _range_bounds(getattr(lane, "lead_time_days", None))
            if supply_bounds == (None, None):
                raise ValueError(f"Transportation lane {lane.id} must include supply lead time distribution or range")
            lead_lo_days, lead_hi_days = supply_bounds
            if lead_lo_days is None or lead_hi_days is None:
                raise ValueError(f"Transportation lane {lane.id} supply lead time must include both minimum and maximum values")
            min_supply_lead_days = _update_min(min_supply_lead_days, lead_lo_days)
            max_supply_lead_days = _update_max(max_supply_lead_days, lead_hi_days)
            fallback_supply_days = _range_midpoint({"min": lead_lo_days, "max": lead_hi_days}, lead_lo_days)
            expected_supply_days = _distribution_expected_value(
                getattr(lane, "supply_lead_time", None),
                fallback_supply_days,
            )
            supply_midpoints_days.append(expected_supply_days)

            order_bounds = _distribution_bounds(getattr(lane, "demand_lead_time", None))
            if order_bounds == (None, None):
                raise ValueError(f"Transportation lane {lane.id} must include demand lead time distribution")
            order_lo_days, order_hi_days = order_bounds
            if order_lo_days is None or order_hi_days is None:
                raise ValueError(f"Transportation lane {lane.id} demand lead time must include both minimum and maximum values")
            min_order_lead_days = _update_min(min_order_lead_days, order_lo_days)
            max_order_lead_days = _update_max(max_order_lead_days, order_hi_days)
            order_midpoints_days.append(
                _distribution_expected_value(getattr(lane, "demand_lead_time", None), order_lo_days)
            )

        if not supply_midpoints_days or not order_midpoints_days:
            raise ValueError("Supply and demand lead times must be defined for all lanes")
        if any(
            value is None
            for value in (
                min_supply_lead_days,
                max_supply_lead_days,
                min_order_lead_days,
                max_order_lead_days,
                max_lane_capacity,
            )
        ):
            raise ValueError("Supply chain configuration must define lead time bounds and capacities for all lanes")

        average_supply_leadtime_days = sum(supply_midpoints_days) / len(supply_midpoints_days)
        average_order_leadtime_days = sum(order_midpoints_days) / len(order_midpoints_days)

        average_supply_leadtime_steps = _leadtime_to_buckets(
            average_supply_leadtime_days,
            time_bucket,
        )
        if average_supply_leadtime_steps is None:
            raise ValueError("Supply lead times must be convertible to time bucket units")

        average_order_leadtime_steps = _leadtime_to_buckets(
            average_order_leadtime_days,
            time_bucket,
        )
        if average_order_leadtime_steps is None:
            raise ValueError("Order lead times must be convertible to time bucket units")

        min_supply_lead_steps = _leadtime_to_buckets(min_supply_lead_days, time_bucket)
        max_supply_lead_steps = _leadtime_to_buckets(max_supply_lead_days, time_bucket)
        min_order_lead_steps = _leadtime_to_buckets(min_order_lead_days, time_bucket)
        max_order_lead_steps = _leadtime_to_buckets(max_order_lead_days, time_bucket)

        if min_supply_lead_steps is None or min_supply_lead_steps <= 0:
            raise ValueError("Supply lead time ranges must include positive minimum values for all lanes")
        if max_supply_lead_steps is None or max_supply_lead_steps <= 0:
            raise ValueError("Supply lead time ranges must include positive maximum values for all lanes")
        if max_supply_lead_steps < min_supply_lead_steps:
            raise ValueError("Supply lead time maximum must be greater than or equal to the minimum")

        if min_order_lead_steps is None or min_order_lead_steps < 0:
            raise ValueError("Demand lead time ranges must include non-negative minimum values for all lanes")
        if max_order_lead_steps is None or max_order_lead_steps < min_order_lead_steps:
            raise ValueError("Demand lead time ranges must include maximum values for all lanes")

        supply_lead_time_default = max(1, int(math.ceil(average_supply_leadtime_steps)))
        default_order_lead = max(0, int(math.ceil(average_order_leadtime_steps)))

        default_supply_lead_days = average_supply_leadtime_days
        default_order_lead_days = average_order_leadtime_days
        default_supply_lead_steps = average_supply_leadtime_steps
        default_order_lead_steps = average_order_leadtime_steps

        min_demand: Optional[float] = None
        max_demand: Optional[float] = None

        def record_demand(value: Any) -> None:
            nonlocal min_demand, max_demand
            numeric = _to_float(value)
            if numeric is None:
                return
            min_demand = _update_min(min_demand, numeric)
            max_demand = _update_max(max_demand, numeric)

        for md in market_demands:
            pattern_dict = _coerce_pattern_dict(getattr(md, "demand_pattern", {}))
            if not pattern_dict:
                raise ValueError(f"Demand pattern is missing or empty for item {md.product_id} and market {md.market_id}")
            params = pattern_dict.get('params', {}) if isinstance(pattern_dict.get('params', {}), dict) else {}

            if params:
                for key in ("initial_demand", "final_demand", "mean", "min", "max", "demand"):
                    record_demand(params.get(key))
            elif pattern_dict:
                for key in ("mean", "min", "max", "demand", "value"):
                    record_demand(pattern_dict.get(key))
            else:
                record_demand(getattr(md, "demand_pattern", None))

        node_policies: Dict[str, Dict[str, Any]] = {}
        node_types: Dict[str, str] = {}
        node_master_types: Dict[str, str] = {}
        pricing_config: Dict[str, Dict[str, float]] = {}

        for node in nodes:
            node_item_configs = [inc for inc in product_site_configs if inc.site_id == node.id]
            node_name = getattr(node, "name", None) or f"node-{node.id}"
            node_key = MixedScenarioService._normalise_key(node_name)
            # Normalised keys keep downstream graph operations consistent regardless of spacing/punctuation.
            dag_type_value = str(getattr(node, "dag_type", None) or node.type or "").lower()
            node_types[node_key] = dag_type_value

            master_type_value = (
                getattr(node, "master_type", None)
                or (getattr(node, "dag_type", None))
                or dag_type_value
            )
            if hasattr(master_type_value, "value"):
                master_type_value = getattr(master_type_value, "value")
            node_master_types[node_key] = str(master_type_value).lower() if master_type_value else dag_type_value
            node_attrs = getattr(node, "attributes", {}) or {}
            node_priority = getattr(node, "priority", None)
            node_order_aging = getattr(node, "order_aging", 0) or 0
            node_lost_sale_cost = getattr(node, "lost_sale_cost", None)

            normalized_master = node_master_types.get(node_key)
            role = role_mapping.get(dag_type_value) or role_mapping.get(normalized_master, normalized_master)
            defaults = DEFAULT_ROLE_PRICING.get(role, {"selling_price": 0.0, "standard_cost": 0.0})
            selling_price = defaults["selling_price"]
            if node_item_configs:
                selling_price = _range_midpoint(node_item_configs[0].selling_price_range, selling_price)
            standard_cost = defaults["standard_cost"]
            if selling_price and standard_cost == 0.0:
                standard_cost = max(selling_price * 0.8, 0.0)

            inbound_lanes = lanes_by_downstream.get(node.id, [])
            is_market_node = (normalized_master in {"market_supply", "market_demand"})

            if not is_market_node and not node_item_configs:
                raise ValueError(f"Node {node.name} must include item-node configuration data")

            if inbound_lanes:
                inbound_supply_days = [
                    _distribution_expected_value(
                        getattr(lane, "supply_lead_time", None),
                        _range_midpoint(getattr(lane, "lead_time_days", None), default_supply_lead_days),
                    )
                    for lane in inbound_lanes
                ]
                inbound_supply_steps = []
                for value in inbound_supply_days:
                    steps = _leadtime_to_buckets(value, time_bucket)
                    if steps is None:
                        raise ValueError(f"Inbound supply lead time missing for node {node.name}")
                    inbound_supply_steps.append(steps)
                inbound_order_days = [
                    _distribution_expected_value(
                        getattr(lane, "demand_lead_time", None),
                        default_order_lead_days,
                    )
                    for lane in inbound_lanes
                ]
                inbound_order_steps = []
                for value in inbound_order_days:
                    steps = _leadtime_to_buckets(value, time_bucket)
                    if steps is None:
                        raise ValueError(f"Inbound demand lead time missing for node {node.name}")
                    inbound_order_steps.append(steps)
                supply_leadtime = sum(inbound_supply_steps) / len(inbound_supply_steps)
                inbound_order_value = sum(inbound_order_steps) / len(inbound_order_steps)
            elif is_market_node:
                inbound_order_value = 0
                supply_leadtime = 0
            else:
                raise ValueError(f"Node {node.name} must include inbound lanes for lead time calculations")

            init_inventory_value = default_init_inventory
            if node_item_configs:
                init_inventory_value = _range_midpoint(
                    node_item_configs[0].initial_inventory_range,
                    default_init_inventory,
                )

            if is_market_node:
                order_lead = 0
                supply_lead = 0
            else:
                order_lead = max(0, int(math.ceil(inbound_order_value)))
                supply_lead = max(1, int(math.ceil(supply_leadtime)))
            node_policy = {
                "order_leadtime": order_lead,
                "supply_leadtime": supply_lead,
                "init_inventory": 0 if is_market_node else int(round(init_inventory_value)),
                "min_order_qty": 0 if is_market_node else 0,
                "variable_cost": 0.0,
                "price": 0.0 if is_market_node else round(float(selling_price or 0.0), 2),
                "standard_cost": 0.0 if is_market_node else round(float(standard_cost or 0.0), 2),
                "partial_order_fulfillment": True,
                "attributes": _clone_json(node_attrs),
                "priority": node_priority,
                "order_aging": node_order_aging,
                "lost_sale_cost": node_lost_sale_cost,
            }
            if normalized_master == "market_supply":
                capacity_val = None
                if isinstance(node_attrs, dict):
                    capacity_val = _to_float(node_attrs.get("supply_capacity"))
                if capacity_val is None:
                    raise ValueError(f"Market Supply node {node.name} must define a numeric supply_capacity attribute")
                node_policy["max_supply"] = int(capacity_val)
            if isinstance(node_attrs, dict):
                capacity_volume = _to_float(node_attrs.get("warehouse_capacity_volume"))
                if capacity_volume is not None:
                    node_policy["warehouse_capacity_volume"] = capacity_volume

                inventory_target_value = _to_float(node_attrs.get("inventory_target_value"))
                if inventory_target_value is not None:
                    node_policy["inventory_target_value"] = inventory_target_value

            node_policies[node_key] = node_policy

            if role and role not in pricing_config:
                pricing_config[role] = {
                    "selling_price": round(float(selling_price or 0.0), 2),
                    "standard_cost": round(float(standard_cost or 0.0), 2),
                }

        for role, defaults in DEFAULT_ROLE_PRICING.items():
            pricing_config.setdefault(role, {
                "selling_price": defaults["selling_price"],
                "standard_cost": defaults["standard_cost"],
            })

        def _normalise_key(value: Any) -> str:
            return str(value or "").strip().lower()

        bill_of_materials: Dict[str, Dict[str, Dict[str, int]]] = {}

        def _tokenise(value: Any) -> List[str]:
            if not value:
                return []
            return [token for token in re.split(r"[^0-9a-z]+", str(value).lower()) if token]

        demand_node_entries: List[Tuple[Site, str, Set[str]]] = []
        for node in nodes:
            node_type_canonical = MixedScenarioService._normalise_node_type(getattr(node, "type", None))
            if node_type_canonical == "market_demand":
                node_key = MixedScenarioService._normalise_key(node.name)
                demand_node_entries.append((node, node_key, set(_tokenise(node.name))))

        market_node_lookup: Dict[int, str] = {}
        for market in markets:
            token_list = _tokenise(market.name)
            token_set = set(token_list)
            matched_key: Optional[str] = None
            for _, node_key, node_tokens in demand_node_entries:
                if token_set and token_set.issubset(node_tokens):
                    matched_key = node_key
                    break
            if not matched_key and token_list:
                code_token = token_list[-1]
                for _, node_key, node_tokens in demand_node_entries:
                    if code_token in node_tokens:
                        matched_key = node_key
                        break
            if matched_key:
                market_node_lookup[market.id] = matched_key

        market_demand_payload: List[Dict[str, Any]] = []
        for md in market_demands:
            entry = {
                "id": md.id,
                "product_id": md.product_id,
                "market_id": md.market_id,
                "market_name": getattr(md.market, "name", None),
                "demand_pattern": _coerce_pattern_dict(getattr(md, "demand_pattern", {})),
            }
            node_hint = market_node_lookup.get(md.market_id)
            if node_hint:
                entry["market_node"] = node_hint
            market_demand_payload.append(entry)

        lane_payload: List[Dict[str, Any]] = []
        for lane in lanes:
            upstream = (
                MixedScenarioService._normalise_key(lane.upstream_node.name)
                if lane.upstream_node
                else None
            )
            downstream = (
                MixedScenarioService._normalise_key(lane.downstream_node.name)
                if lane.downstream_node
                else None
            )
            if not upstream or not downstream:
                continue
            lane_payload.append(
                {
                    "from": upstream,
                    "to": downstream,
                    "capacity": lane.capacity,
                    "lead_time_days": lane.lead_time_days,
                    "demand_lead_time": getattr(lane, "demand_lead_time", None),
                    "supply_lead_time": getattr(lane, "supply_lead_time", None),
                }
            )

        item_payload: List[Dict[str, Any]] = [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "unit_cost_range": dict(item.unit_cost_range or {}),
                "priority": getattr(item, "priority", None),
            }
            for item in items
        ]

        market_nodes: List[str] = []

        market_demand_node_ids: Set[int] = {
            node.id
            for node in nodes
            if MixedScenarioService._normalise_node_type(getattr(node, "type", None)) == "market_demand"
        }
        market_feeders: Set[str] = set()
        if market_demand_node_ids:
            for lane in lanes:
                if lane.to_site_id in market_demand_node_ids and lane.downstream_node is not None:
                    market_feeders.add(MixedScenarioService._normalise_key(lane.downstream_node.name))

        if market_feeders:
            market_nodes = sorted(market_feeders)
        elif market_demands:
            for md in market_demands:
                market_obj = getattr(md, "market", None)
                market_name = market_obj.name.lower() if market_obj else None
                if market_name:
                    normalised = MixedScenarioService._normalise_key(market_name)
                    if normalised not in market_nodes:
                        market_nodes.append(normalised)

        if not market_nodes:
            explicit_market = [
                name
                for name, ntype in node_types.items()
                if ntype == NodeType.MARKET_DEMAND.value.lower() or ntype == "market_demand"
            ]
            market_nodes = sorted(explicit_market)

        if not market_nodes:
            raise ValueError("Supply chain config must include at least one Market Demand node.")

        market_supply_nodes = [
            name
            for name, ntype in node_types.items()
            if ntype == NodeType.MARKET_SUPPLY.value.lower() or ntype == "market_supply"
        ]
        if not market_supply_nodes:
            raise ValueError("Supply chain DAG must include at least one Market Supply node persisted in the database")

        all_node_keys = {
            MixedScenarioService._normalise_key(node.name.lower()) for node in nodes if node and node.name
        }
        all_node_keys.update({MixedScenarioService._normalise_key(n) for n in market_nodes})
        lane_nodes = {entry["from"] for entry in lane_payload if entry.get("from")} | {
            entry["to"] for entry in lane_payload if entry.get("to")
        }
        all_node_keys.update(lane_nodes)
        all_node_keys.update({MixedScenarioService._normalise_key(key) for key in node_types.keys() if key})
        upstreams = {entry["from"] for entry in lane_payload if entry.get("from")}
        downstreams = {entry["to"] for entry in lane_payload if entry.get("to")}
        sources = []
        for node in sorted(all_node_keys):
            if node not in downstreams:
                sources.append(node)
                continue
            node_type = node_types.get(node)
            if node_type in {NodeType.MARKET_SUPPLY.value.lower(), "market_supply", NodeType.MARKET_DEMAND.value.lower(), "market_demand"}:
                sources.append(node)
        sinks = sorted([node for node in all_node_keys if node not in upstreams])
        def _normalize_node_type(node_key: str) -> Optional[str]:
            node_type_raw = node_types.get(node_key)
            if node_type_raw is not None:
                if hasattr(node_type_raw, "value"):
                    node_type_raw = node_type_raw.value
                return MixedScenarioService._normalise_node_type(node_type_raw)

            token = MixedScenarioService._normalise_key(node_key)
            if "market_supply" in token:
                return "market_supply"
            if "market_demand" in token or token == "market":
                return "market_demand"
            if "supplier" in token:
                return "supplier"
            return None

        allowed_source_types = {
            MixedScenarioService._normalise_node_type(NodeType.MARKET_SUPPLY.value),
            "market_supply",
            MixedScenarioService._normalise_node_type(NodeType.MARKET_DEMAND.value),
            "market_demand",
            MixedScenarioService._normalise_node_type(NodeType.SUPPLIER.value),
            "supplier",
            "component_supplier",
            MixedScenarioService._normalise_node_type(NodeType.INVENTORY.value),
            "inventory",
            MixedScenarioService._normalise_node_type(NodeType.MANUFACTURER.value),
            "manufacturer",
        }
        invalid_sources = []
        for node in sources:
            node_type_norm = _normalize_node_type(node)
            if node_type_norm not in allowed_source_types:
                invalid_sources.append(node)
        if invalid_sources:
            raise ValueError(
                "Supply chain DAG sources must be Supplier / Component Supplier / Market Supply / Market Demand nodes; invalid sources: "
                + ", ".join(invalid_sources)
            )
        if not any(_normalize_node_type(node) in {NodeType.MARKET_SUPPLY.value.lower(), "market_supply"} for node in sources):
            raise ValueError("Supply chain DAG must include at least one Market Supply source node.")
        if not any(_normalize_node_type(node) in {NodeType.MARKET_DEMAND.value.lower(), "market_demand"} for node in sinks):
            raise ValueError("Supply chain DAG must include at least one Market Demand sink node.")

        md = market_demands[0]
        raw_pattern = _coerce_pattern_dict(getattr(md, "demand_pattern", {}))
        normalized_pattern = normalize_demand_pattern(raw_pattern)
        if not normalized_pattern:
            raise ValueError("Demand pattern payload is missing or invalid for the supply chain configuration")
        demand_pattern = normalized_pattern
        params = normalized_pattern.get("params", {})
        pattern_type_value = normalized_pattern.get("type", DemandPatternType.CLASSIC.value)

        if pattern_type_value == DemandPatternType.CLASSIC.value:
            record_demand(params.get("initial_demand"))
            record_demand(params.get("final_demand"))
            if min_demand is None or max_demand is None:
                raise ValueError("Classic demand patterns must define initial and final demand values")
        elif pattern_type_value == DemandPatternType.LOGNORMAL.value:
            mean_val = _to_float(params.get("mean")) or DEFAULT_LOGNORMAL_PARAMS["mean"]
            cov_val = _to_float(params.get("cov")) or DEFAULT_LOGNORMAL_PARAMS["cov"]
            stddev_val = _to_float(params.get("stddev")) or (mean_val * cov_val)
            clip_min = _to_float(params.get("min_demand")) or _to_float(params.get("clip_min"))
            clip_max = _to_float(params.get("max_demand")) or _to_float(params.get("clip_max"))
            approx_min = max(0.0, clip_min if clip_min is not None else mean_val - 3.0 * stddev_val)
            approx_max = max(approx_min, clip_max if clip_max is not None else mean_val + 3.0 * stddev_val)
            record_demand(approx_min)
            record_demand(approx_max)
            min_demand = approx_min
            max_demand = approx_max
        else:
            for key in ("min_demand", "max_demand", "mean", "min", "max", "value", "demand"):
                record_demand(params.get(key))
            if min_demand is None or max_demand is None:
                raise ValueError("Demand patterns must include minimum and maximum demand values")

        if min_demand is None or max_demand is None:
            raise ValueError("Demand patterns must define demand bounds for all item/market combinations")
        if min_demand > max_demand:
            raise ValueError("Demand pattern minimum demand cannot exceed maximum demand")

        if max_init_inventory is None or max_lane_capacity is None:
            raise ValueError("Order limits require maximum initial inventory and transportation lane capacity values")
        max_order_quantity = int(round(max(max_init_inventory, max_lane_capacity)))

        order_lead_range = {
            "min": max(0, int(math.ceil(min_order_lead_steps))),
            "max": max(0, int(math.ceil(max_order_lead_steps))),
        }
        supply_lead_range = {
            "min": max(1, int(math.ceil(min_supply_lead_steps))) if min_supply_lead_steps > 0 else supply_lead_time_default,
            "max": max(1, int(math.ceil(max_supply_lead_steps))) if max_supply_lead_steps > 0 else supply_lead_time_default,
        }

        system_config = {
            "min_order_quantity": 0,
            "max_order_quantity": max_order_quantity,
            "min_holding_cost": round(float(min_holding_cost), 2),
            "max_holding_cost": round(float(max_holding_cost), 2),
            "min_backlog_cost": round(float(min_backlog_cost), 2),
            "max_backlog_cost": round(float(max_backlog_cost), 2),
            "min_demand": int(round(min_demand)),
            "max_demand": int(round(max_demand)),
            "min_lead_time": supply_lead_range["min"],
            "max_lead_time": supply_lead_range["max"],
            "min_starting_inventory": int(round(min_init_inventory)),
            "max_starting_inventory": int(round(max_init_inventory)),
        }

        system_config["demand_leadtime"] = dict(order_lead_range)
        system_config["supply_leadtime"] = dict(supply_lead_range)
        system_config["ship_order_leadtimedelay"] = dict(supply_lead_range)

        initial_demand_value = _to_float(params.get("initial_demand"))
        final_demand_value = _to_float(params.get("final_demand"))
        change_week_value = params.get("change_week")
        if pattern_type_value == DemandPatternType.CLASSIC.value and change_week_value is None:
            raise ValueError("Classic demand patterns must include a change_week parameter")

        simulation_parameters = {
            "weeks": 40,
            "demand_lead_time": default_order_lead,
            "shipping_lead_time": supply_lead_time_default,
            "production_lead_time": supply_lead_time_default,
            "initial_inventory": int(round(default_init_inventory)),
            "holding_cost_per_unit": round(default_holding_cost, 2),
            "backorder_cost_per_unit": round(default_backlog_cost, 2),
            "initial_demand": int(round(initial_demand_value if initial_demand_value is not None else min_demand)),
            "demand_change_week": change_week_value,
            "new_demand": int(round(final_demand_value if final_demand_value is not None else max_demand)),
            "historical_weeks": 30,
            "volatility_window": 14,
            "enable_information_sharing": True,
            "enable_demand_volatility_signals": True,
            "enable_pipeline_signals": True,
            "enable_downstream_visibility": True,
        }

        if pattern_type_value == DemandPatternType.LOGNORMAL.value:
            mean_val = _to_float(demand_pattern['params'].get('mean')) or DEFAULT_LOGNORMAL_PARAMS['mean']
            simulation_parameters["initial_demand"] = int(round(mean_val))
            simulation_parameters["demand_change_week"] = 1
            simulation_parameters["new_demand"] = int(round(mean_val))

        global_policy = {
            "demand_leadtime": simulation_parameters["demand_lead_time"],
            "supply_leadtime": simulation_parameters["shipping_lead_time"],
            "init_inventory": simulation_parameters["initial_inventory"],
            "holding_cost": simulation_parameters["holding_cost_per_unit"],
            "backlog_cost": simulation_parameters["backorder_cost_per_unit"],
            "max_inbound_per_link": int(round(max_lane_capacity)),
            "max_order": system_config["max_order_quantity"],
            "production_lead_time": simulation_parameters["production_lead_time"],
        }

        site_type_definitions, node_type_labels = _normalize_site_type_definitions(
            getattr(config, "site_type_definitions", None)
        )
        defined_types = {
            MixedScenarioService._normalise_node_type(defn.get("type"))
            for defn in site_type_definitions
            if defn.get("type") is not None
        }
        node_types_present = {
            MixedScenarioService._normalise_node_type(getattr(node, "type", None)) for node in nodes
        }
        missing_node_types = sorted(ntype for ntype in node_types_present if ntype and ntype not in defined_types)
        if missing_node_types:
            raise ValueError(
                "Node type definitions must be provided for all site types in the configuration: "
                + ", ".join(missing_node_types)
            )

        for node in nodes:
            attrs = dict(getattr(node, "attributes", {}) or {})
            bom_payload = attrs.get("bill_of_materials")
            if isinstance(bom_payload, dict) and bom_payload:
                node_key = _normalise_key(node.name or node.id)
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
                        component_map[MixedScenarioService._normalise_product_id(component_id)] = qty_int
                    if component_map:
                        node_entry[item_key] = component_map

        node_payload = [
            {
                "id": node.id,
                "name": node.name,
                "type": str(getattr(node, "dag_type", None) or getattr(node, "type", "")).lower(),
                "dag_type": str(getattr(node, "dag_type", None) or getattr(node, "type", "")).lower(),
                "master_type": str(getattr(node, "master_type", None) or "").lower() or None,
                "attributes": dict(getattr(node, "attributes", {}) or {}),
                "priority": getattr(node, "priority", None),
                "order_aging": getattr(node, "order_aging", 0),
                "lost_sale_cost": getattr(node, "lost_sale_cost", None),
            }
            for node in nodes
        ]

        node_type_sequence = [
            MixedScenarioService._normalise_node_type(defn.get("type"))
            for defn in site_type_definitions
            if MixedScenarioService._normalise_node_type(defn.get("type"))
        ]

        game_config = {
            "name": game_data.get('name', f"Game - {config.name}"),
            "description": game_data.get('description', config.description or ""),
            "max_rounds": game_data.get('max_rounds', 40),
            "is_public": game_data.get('is_public', True),
            "node_policies": node_policies,
            "demand_pattern": demand_pattern,
            "supply_chain_config_id": config_id,
            "pricing_config": pricing_config,
            "system_config": system_config,
            "global_policy": global_policy,
            "markets": [
                {
                    "id": market.id,
                    "name": market.name,
                    "description": market.description,
                    "company": getattr(market, "company", None),
                    "node_key": market_node_lookup.get(market.id),
                }
                for market in markets
            ],
            "simulation_parameters": simulation_parameters,
            "time_bucket": time_bucket.value,
            "start_date": DEFAULT_START_DATE.isoformat(),
            "items": item_payload,
            "info_sharing": {
                "enabled": True,
                "historical_weeks": 30,
            },
            "demand_volatility": {
                "enabled": True,
                "window": 14,
            },
            "pipeline_signals": {
                "enabled": True,
            },
            "downstream_visibility": {
                "enabled": True,
            },
            "progression_mode": game_data.get(
                'progression_mode',
                'unsupervised' if game_data.get('name', '').lower().startswith('autonomy') else 'supervised',
            ),
            "enable_information_sharing": True,
            "enable_demand_volatility_signals": True,
            "enable_pipeline_signals": True,
            "enable_downstream_visibility": True,
            "historical_weeks_to_share": 30,
            "volatility_analysis_window": 14,
            "lanes": lane_payload,
            "node_types": node_types,
            "node_master_types": node_master_types,
            "site_type_definitions": site_type_definitions,
            "node_type_labels": node_type_labels,
            "node_type_sequence": node_type_sequence,
            "market_demand_nodes": market_nodes,
            "market_demand_nodes_count": len(market_nodes) if market_nodes else 1,
            "market_demands": market_demand_payload,
            "bill_of_materials": bill_of_materials,
            "sites": node_payload,
        }

        return game_config
    
    def create_config_from_game(self, scenario_id: int, config_name: str) -> SupplyChainConfig:
        """
        Create a supply chain configuration from an existing game.
        
        Args:
            scenario_id: ID of the game to create a configuration from
            config_name: Name for the new configuration
            
        Returns:
            The created SupplyChainConfig object
        """
        # This would query the game and create a configuration from its settings
        # Implementation would be similar to the reverse of create_game_from_config
        raise NotImplementedError("This feature is not yet implemented")
        item_payload: List[Dict[str, Any]] = [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "unit_cost_range": item.unit_cost_range,
            }
            for item in items
        ]

    def validate_config(self, config_id: int) -> tuple[bool, List[str]]:
        """
        Validate supply chain configuration for source priority conflicts.

        Returns (is_valid, error_messages) tuple.

        Validation Rules:
        - For each item at each node, there must not be multiple suppliers with the same priority.
        - Priority 0 (highest) must be unique per item per node.
        """
        import datetime
        from collections import defaultdict

        config = self.db.query(SupplyChainConfig).filter(SupplyChainConfig.id == config_id).first()
        if not config:
            return False, ["Configuration not found"]

        errors: List[str] = []

        # Get all nodes and products
        from app.models.supply_chain_config import Site as SCNode
        from app.models.sc_entities import Product

        nodes = self.db.query(SCNode).filter(SCNode.config_id == config_id).all()
        # Products are now tracked in SC product table with config_id
        products = self.db.query(Product).filter(Product.config_id == config_id).all()
        # Note: ProductSiteConfig functionality migrated to InvPolicy (SC)

        # Build lookups
        node_by_id = {node.id: node for node in nodes}
        item_by_id = {item.id: item for item in items}

        # Validate: For each product-site config, check for duplicate supplier priorities
        for inc in product_site_configs:
            node = node_by_id.get(inc.site_id)
            item = item_by_id.get(inc.product_id)

            if not node or not item:
                continue

            # Get suppliers for this item-node configuration
            suppliers = self.db.query(ItemNodeSupplier).filter(
                ItemNodeSupplier.item_node_config_id == inc.id
            ).all()

            if len(suppliers) <= 1:
                # No conflict possible with 0 or 1 supplier
                continue

            # Check for duplicate priorities
            priority_to_suppliers = defaultdict(list)
            for supplier in suppliers:
                supplier_node = node_by_id.get(supplier.supplier_site_id)
                if supplier_node:
                    priority_to_suppliers[supplier.priority].append(supplier_node.name)

            # Report errors for duplicate priorities
            for priority, supplier_names in priority_to_suppliers.items():
                if len(supplier_names) > 1:
                    errors.append(
                        f"{node.name}: Item '{item.name}' has multiple suppliers "
                        f"with priority {priority}: {', '.join(supplier_names)}"
                    )

        # Update validation status
        is_valid = len(errors) == 0
        config.validation_status = "valid" if is_valid else "invalid"
        config.validation_errors = errors if errors else None
        config.validated_at = datetime.datetime.utcnow()
        self.db.commit()

        return is_valid, errors
