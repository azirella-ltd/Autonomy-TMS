"""Utilities for constructing structured payloads for the Autonomy LLM agent."""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.scenario import Scenario
from app.models.scenario_user import ScenarioUser
from app.models.supply_chain import ScenarioUserInventory, ScenarioUserPeriod, ScenarioPeriod

# Aliases for backwards compatibility
ScenarioUser = ScenarioUser
# Mapping between backend role identifiers and the labels expected by the Autonomy LLM
ROLE_NAME_MAP = {
    "manufacturer": "factory",
}

DOWNSTREAM_ROLE_MAP = {
    "retailer": None,
    "wholesaler": "retailer",
    "distributor": "wholesaler",
    "manufacturer": "distributor",
}


def compose_autonomy_payload(
    *,
    action_role_key: str,
    raw_action_role: str,
    round_number: int,
    order_lead: int,
    ship_lead: int,
    prod_lead: int,
    holding_cost: float,
    backlog_cost: float,
    toggles: Dict[str, bool],
    engine_state: Dict[str, Any],
    roles_section: Dict[str, Dict[str, Any]],
    history_by_role: Dict[str, List[Dict[str, Any]]],
    volatility_window: Optional[int],
    visible_history_weeks: Optional[int],
) -> Dict[str, Any]:
    """Compose the Autonomy strategist payload from precomputed state."""

    role_state = roles_section.get(action_role_key, {})
    engine_entry = _coerce_dict(engine_state.get(raw_action_role, {}))

    incoming_order = _select_int(
        engine_entry.get("incoming_orders"),
        role_state.get("incoming_order"),
        default=0,
    )
    on_hand = _select_int(role_state.get("inventory"), default=0)
    backlog = _select_int(role_state.get("backlog"), default=0)
    received_shipment = _select_int(engine_entry.get("last_arrival"), default=0)

    pipeline_orders = engine_entry.get("info_queue")
    if isinstance(pipeline_orders, list):
        pipeline_orders = [int(x) for x in pipeline_orders]
    else:
        pipeline_orders = []
    pipeline_orders = _pad_sequence(pipeline_orders, order_lead)

    inbound_pipeline_raw = engine_entry.get("ship_queue")
    if isinstance(inbound_pipeline_raw, list):
        inbound_pipeline_values = _normalize_pipeline(inbound_pipeline_raw)
    else:
        inbound_pipeline_values = _normalize_pipeline(role_state.get("pipeline", []))
    inbound_pipeline = _pad_sequence(inbound_pipeline_values, ship_lead)

    optional_section: Dict[str, Any] = {}

    retailer_history_records = history_by_role.get("retailer", [])
    retailer_demand_history = [
        entry["customer_demand"] or 0
        for entry in retailer_history_records
        if entry.get("customer_demand") is not None
    ]
    if retailer_demand_history and visible_history_weeks:
        retailer_demand_history = retailer_demand_history[-visible_history_weeks:]

    if toggles.get("customer_demand_history_sharing") and retailer_demand_history:
        optional_section["shared_demand_history"] = retailer_demand_history

    if toggles.get("volatility_signal_sharing") and retailer_demand_history:
        window = (
            retailer_demand_history[-volatility_window:]
            if volatility_window
            else retailer_demand_history
        )
        optional_section["shared_volatility_signal"] = _compute_volatility_signal(window)

    downstream_role = DOWNSTREAM_ROLE_MAP.get(raw_action_role)
    if toggles.get("downstream_inventory_visibility") and downstream_role:
        downstream_key = ROLE_NAME_MAP.get(downstream_role, downstream_role)
        downstream_state = roles_section.get(downstream_key)
        if downstream_state:
            optional_section["visible_downstream"] = {
                "on_hand": int(downstream_state.get("inventory", 0)),
                "backlog": int(downstream_state.get("backlog", 0)),
            }

    local_optional = role_state.get("history", {})
    if local_optional:
        optional_section.setdefault("local_history", local_optional)

    return {
        "role": action_role_key,
        "week": int(round_number),
        "toggles": toggles,
        "parameters": {
            "holding_cost": holding_cost,
            "backlog_cost": backlog_cost,
            "L_order": order_lead,
            "L_ship": ship_lead,
            "L_prod": prod_lead,
        },
        "local_state": {
            "on_hand": on_hand,
            "backlog": backlog,
            "incoming_orders_this_week": incoming_order,
            "received_shipment_this_week": received_shipment,
            "pipeline_orders_upstream": pipeline_orders,
            "pipeline_shipments_inbound": inbound_pipeline,
            "optional": optional_section,
        },
    }


def _coerce_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return {}


def _normalize_pipeline(raw: Any) -> List[int]:
    if not raw:
        return []
    if isinstance(raw, list):
        normalized: List[int] = []
        for item in raw:
            if isinstance(item, (int, float)):
                normalized.append(int(round(item)))
            elif isinstance(item, dict):
                qty = (
                    item.get("quantity")
                    or item.get("qty")
                    or item.get("amount")
                    or item.get("value")
                )
                if qty is not None:
                    try:
                        normalized.append(int(round(float(qty))))
                    except (TypeError, ValueError):
                        continue
        return normalized
    return []


def _pad_sequence(values: List[int], length: int) -> List[int]:
    normalized = [int(x) for x in values[:length]]
    if len(normalized) < length:
        normalized.extend([0] * (length - len(normalized)))
    return normalized


def _coerce_number(value: Any) -> Optional[float]:
    """Best-effort conversion to a numeric value, ignoring blank placeholders."""
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _select_int(*candidates: Any, default: int) -> int:
    """Pick the first candidate that can be coerced to int; otherwise use default."""
    for candidate in candidates:
        number = _coerce_number(candidate)
        if number is not None:
            return int(round(number))
    return default


def _select_float(*candidates: Any, default: float) -> float:
    """Pick the first candidate that can be coerced to float; otherwise use default."""
    for candidate in candidates:
        number = _coerce_number(candidate)
        if number is not None:
            return float(number)
    return default


def _select_toggle(*candidates: Any, default: bool = False) -> bool:
    """Resolve the first meaningful toggle value; fall back to ``default``."""

    truthy_strings = {"true", "1", "yes", "on"}
    falsy_strings = {"false", "0", "no", "off"}

    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, bool):
            return candidate
        if isinstance(candidate, (int, float)):
            return candidate != 0
        if isinstance(candidate, str):
            text = candidate.strip().lower()
            if not text:
                continue
            if text in truthy_strings:
                return True
            if text in falsy_strings:
                return False
            try:
                number = float(text)
            except ValueError:
                return True
            return number != 0
        return bool(candidate)

    return default


def _compute_volatility_signal(history: List[int]) -> Dict[str, Any]:
    if not history:
        return {"sigma": 0.0, "trend": "flat"}

    if len(history) == 1:
        return {"sigma": 0.0, "trend": "flat"}

    mean = sum(history) / len(history)
    variance = sum((value - mean) ** 2 for value in history) / (len(history) - 1)
    sigma = math.sqrt(max(variance, 0.0))

    trend = "flat"
    if history[-1] > history[-2]:
        trend = "up"
    elif history[-1] < history[-2]:
        trend = "down"

    if len(history) >= 3:
        recent = history[-3:]
        if recent[0] <= recent[1] <= recent[2] and recent[2] > recent[1]:
            trend = "up"
        elif recent[0] >= recent[1] >= recent[2] and recent[2] < recent[1]:
            trend = "down"

    return {"sigma": round(sigma, 4), "trend": trend}


def build_llm_decision_payload(
    db: Session,
    scenario: Scenario,
    *,
    round_number: int,
    action_role: str,
    history_window: Optional[int] = None,
) -> Dict[str, Any]:
    """Assemble the structured JSON payload expected by the Autonomy LLM agent."""

    config_raw = _coerce_dict(getattr(scenario, "config", {}))
    sim_params = _coerce_dict(config_raw.get("simulation_parameters", {}))

    demand_pattern_raw = scenario.demand_pattern or config_raw.get("demand_pattern", {})
    demand_pattern = _coerce_dict(demand_pattern_raw)
    demand_params = _coerce_dict(demand_pattern.get("params", {}))

    total_weeks = _select_int(scenario.max_periods, sim_params.get("weeks"), default=40)
    order_lead = max(
        1,
        _select_int(
            sim_params.get("demand_lead_time"),
            sim_params.get("order_leadtime"),
            default=2,
        ),
    )
    ship_lead = max(
        1,
        _select_int(
            sim_params.get("shipping_lead_time"),
            sim_params.get("supply_leadtime"),
            default=2,
        ),
    )
    prod_lead = max(
        1,
        _select_int(
            sim_params.get("production_lead_time"),
            sim_params.get("prod_delay"),
            default=4,
        ),
    )

    holding_cost = _select_float(
        sim_params.get("holding_cost_per_unit"),
        sim_params.get("holding_cost"),
        default=0.5,
    )
    backorder_cost = _select_float(
        sim_params.get("backorder_cost_per_unit"),
        sim_params.get("backorder_cost"),
        default=0.5,
    )

    autonomy_cfg = _coerce_dict(config_raw.get("autonomy_llm", {}))
    autonomy_toggles = _coerce_dict(autonomy_cfg.get("toggles", {}))
    pipeline_cfg = _coerce_dict(config_raw.get("pipeline_signals", {}))

    toggles = {
        "customer_demand_history_sharing": _select_toggle(
            autonomy_toggles.get("customer_demand_history_sharing"),
            config_raw.get("enable_information_sharing"),
            sim_params.get("enable_information_sharing"),
            default=False,
        ),
        "volatility_signal_sharing": _select_toggle(
            autonomy_toggles.get("volatility_signal_sharing"),
            config_raw.get("enable_demand_volatility_signals"),
            sim_params.get("enable_demand_volatility_signals"),
            default=False,
        ),
        "downstream_inventory_visibility": _select_toggle(
            autonomy_toggles.get("downstream_inventory_visibility"),
            config_raw.get("enable_downstream_visibility"),
            sim_params.get("enable_downstream_visibility"),
            pipeline_cfg.get("enabled"),
            default=False,
        ),
    }

    visible_history_weeks = _select_int(
        history_window,
        sim_params.get("historical_weeks"),
        config_raw.get("historical_weeks_to_share"),
        default=30,
    )

    volatility_window = _select_int(
        sim_params.get("volatility_window"),
        config_raw.get("volatility_analysis_window"),
        default=14,
    )

    engine_state = _coerce_dict(config_raw.get("engine_state", {}))

    scenario_user_period_rows = (
        db.query(ScenarioUserPeriod, ScenarioUser, ScenarioPeriod)
        .join(ScenarioUser, ScenarioUserPeriod.scenario_user_id == ScenarioUser.id)
        .join(ScenarioPeriod, ScenarioUserPeriod.scenario_period_id == ScenarioPeriod.id)
        .filter(ScenarioUser.scenario_id == scenario.id)
        .order_by(ScenarioPeriod.round_number.asc())
        .all()
    )

    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    history_by_role: Dict[str, List[Dict[str, Any]]] = {}
    orders_by_role_round: Dict[str, Dict[int, int]] = {}

    for round_rec, scenario_user_obj, scenario_period in scenario_user_period_rows:
        role_name = str(scenario_user_obj.role.value if hasattr(scenario_user_obj.role, "value") else scenario_user_obj.role).lower()
        round_number = _safe_int(getattr(scenario_period, "round_number", 0))

        order_up = _safe_int(
            getattr(round_rec, "order_placed", getattr(round_rec, "order_quantity", 0))
        )
        inventory_before = _safe_int(
            getattr(round_rec, "inventory_before", getattr(round_rec, "inventory", 0))
        )
        backlog_before = _safe_int(
            getattr(round_rec, "backorders_before", getattr(round_rec, "backlog", 0))
        )

        orders_by_role_round.setdefault(role_name, {})[round_number] = order_up

        entry = {
            "round": round_number,
            "order_up": order_up,
            "inventory_before": inventory_before,
            "backlog_before": backlog_before,
            "customer_demand": None,
        }

        if role_name == "retailer":
            demand_value = _safe_int(getattr(scenario_period, "customer_demand", 0))
            entry["customer_demand"] = demand_value

        history_by_role.setdefault(role_name, []).append(entry)

    scenario_users_with_inventory = (
        db.query(ScenarioUser, ScenarioUserInventory)
        .outerjoin(ScenarioUserInventory, ScenarioUserInventory.scenario_user_id == ScenarioUser.id)
        .filter(ScenarioUser.scenario_id == scenario.id)
        .all()
    )

    roles_section: Dict[str, Dict[str, Any]] = {}
    role_key_to_raw: Dict[str, str] = {}
    for scenario_user, inventory in scenario_users_with_inventory:
        if not scenario_user or not getattr(scenario_user, "role", None):
            continue

        role_name_raw = str(scenario_user.role.value if hasattr(scenario_user.role, "value") else scenario_user.role).lower()
        role_key = ROLE_NAME_MAP.get(role_name_raw, role_name_raw)

        inventory_obj = inventory
        current_stock = 0
        current_backlog = 0
        incoming_shipments_raw: Any = []
        if inventory_obj is not None:
            current_stock = int(
                getattr(inventory_obj, "current_stock", getattr(inventory_obj, "current_inventory", 0)) or 0
            )
            current_backlog = int(
                getattr(inventory_obj, "backorders", getattr(inventory_obj, "current_backlog", 0)) or 0
            )
            incoming_shipments_raw = getattr(inventory_obj, "incoming_shipments", [])

        pipeline = _normalize_pipeline(incoming_shipments_raw)

        incoming_order = 0
        engine_entry = engine_state.get(role_name_raw, {})
        if isinstance(engine_entry, dict):
            try:
                incoming_order = int(engine_entry.get("incoming_orders", 0))
            except (TypeError, ValueError):
                incoming_order = 0

        role_records = history_by_role.get(role_name_raw, [])
        if visible_history_weeks and visible_history_weeks > 0:
            role_records = role_records[-visible_history_weeks:]

        orders_history: List[int] = []
        shipments_history: List[int] = []
        demand_history: List[int] = []

        downstream_role = DOWNSTREAM_ROLE_MAP.get(role_name_raw)
        downstream_orders_map = orders_by_role_round.get(downstream_role, {}) if downstream_role else None

        for record in role_records:
            round_id = record["round"]
            order_up_value = record["order_up"]
            on_hand_value = record["inventory_before"]
            backlog_value = record.get("backlog_before", 0)

            if role_name_raw == "retailer":
                order_qty = record["customer_demand"] or 0
                demand_history.append(order_qty)
            elif downstream_orders_map is not None:
                order_qty = downstream_orders_map.get(round_id, 0)
            else:
                order_qty = 0

            total_demand = order_qty + backlog_value
            shipped_qty = min(on_hand_value, total_demand)

            orders_history.append(order_up_value)
            shipments_history.append(_safe_int(shipped_qty))

        history_section: Dict[str, Any] = {
            "shipments_sent": shipments_history,
        }
        if role_name_raw == "manufacturer":
            history_section["production_orders"] = orders_history
        else:
            history_section["orders_placed"] = orders_history
        if role_name_raw == "retailer" and demand_history:
            history_section["demand"] = demand_history

        roles_section[role_key] = {
            "inventory": current_stock,
            "backlog": current_backlog,
            "pipeline": pipeline,
            "incoming_order": incoming_order,
            "history": history_section,
        }
        role_key_to_raw[role_key] = role_name_raw

    action_role_key = ROLE_NAME_MAP.get(action_role.lower(), action_role.lower())

    role_state = roles_section.get(action_role_key, {})
    raw_role = role_key_to_raw.get(action_role_key, action_role.lower())

    return compose_autonomy_payload(
        action_role_key=action_role_key,
        raw_action_role=raw_role,
        round_number=round_number,
        order_lead=order_lead,
        ship_lead=ship_lead,
        prod_lead=prod_lead,
        holding_cost=holding_cost,
        backlog_cost=backorder_cost,
        toggles=toggles,
        engine_state=engine_state,
        roles_section=roles_section,
        history_by_role=history_by_role,
        volatility_window=volatility_window,
        visible_history_weeks=visible_history_weeks,
    )
