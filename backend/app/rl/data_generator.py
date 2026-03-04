import json
import logging
import math
import copy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
import os as _os
try:
    import simpy  # type: ignore
except Exception:
    simpy = None
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import (
    ACTION_LEVELS,
    SimulationParams,
    NODE_FEATURES,
)
from app.services.agents import AgentDecision, AgentStrategy, AgentType, SimulationAgent
from app.services.llm_payload import (
    DOWNSTREAM_ROLE_MAP,
    ROLE_NAME_MAP,
    compose_autonomy_payload,
)
from app.core.db_urls import resolve_sync_database_url

logger = logging.getLogger(__name__)

# ---------- Action indexing helpers ------------------------------------------

def order_units_to_action_idx(units: int) -> int:
    """
    Map a raw order quantity to the nearest discrete ACTION_LEVEL index.
    """
    units = max(0, units)
    diffs = [abs(u - units) for u in ACTION_LEVELS]
    return int(np.argmin(diffs))

def action_idx_to_order_units(idx: int) -> int:
    idx = int(np.clip(idx, 0, len(ACTION_LEVELS) - 1))
    return ACTION_LEVELS[idx]

# ---------- Feature wiring ----------------------------------------------------

# AWS SC master_type one-hot encoding — topology-agnostic (always 4 values, matching
# the 4 AWS SC site master_type categories). Replaces Beer Game role one-hots.
_MASTER_TYPES = ["market_supply", "market_demand", "inventory", "manufacturer"]


def site_type_onehot(master_type: str) -> List[float]:
    """
    One-hot encode an AWS SC site master_type.

    Maps to NODE_FEATURES entries:
      site_type_market_supply, site_type_market_demand,
      site_type_inventory, site_type_manufacturer

    Works for any supply chain topology — not tied to Beer Game roles.
    """
    mt = (master_type or "inventory").lower()
    return [1.0 if mt == t else 0.0 for t in _MASTER_TYPES]


def assemble_node_features(
    master_type: str,
    inventory: int,
    backlog: int,
    incoming_orders: int,
    incoming_shipments: int,
    on_order: int,
    params: SimulationParams,
) -> np.ndarray:
    """
    Build the 11-element node feature vector for GNN training.

    master_type: AWS SC site master_type (market_supply/market_demand/inventory/manufacturer).
    Feature order matches NODE_FEATURES in config.py — feature count is stable at 11
    regardless of topology size.
    """
    return np.array(
        [
            float(inventory),
            float(backlog),
            float(incoming_orders),
            float(incoming_shipments),
            float(on_order),
            *site_type_onehot(master_type),
            float(params.order_leadtime),
            float(params.supply_leadtime),
        ],
        dtype=np.float32,
    )


# DEPRECATED: role_onehot() was tied to the 4-node Beer Game topology.
# Use site_type_onehot(master_type) for new training runs.
def role_onehot(role: str) -> List[float]:  # DEPRECATED
    from .config import NODES, NODE_INDEX  # lazy import — legacy path only
    oh = [0.0] * len(NODES)
    if role in NODE_INDEX:
        oh[NODE_INDEX[role]] = 1.0
    return oh

# ---------- DB loader (exact lookup function) --------------------------------

@dataclass
class DbLookupConfig:
    """Configuration for database lookup of game state sequences."""
    database_url: str
    steps_table: str = "simulation_steps"
    column_map: Dict[str, str] = None

    def __post_init__(self):
        if self.column_map is None:
            self.column_map = {
                "scenario_id": "scenario_id",
                "week": "week",
                "role": "role",
                "inventory": "inventory",
                "backlog": "backlog",
                "incoming_orders": "incoming_orders",
                "incoming_shipments": "incoming_shipments",
                "on_order": "on_order",
                "placed_order": "placed_order",
            }

def _build_select_sql(cfg: DbLookupConfig, scenario_ids: Optional[List[int]]) -> Tuple[str, Dict]:
    cols = cfg.column_map
    table = cfg.steps_table
    base = f"""
      SELECT
        {cols['scenario_id']}     AS scenario_id,
        {cols['week']}        AS week,
        {cols['role']}        AS role,
        {cols['inventory']}   AS inventory,
        {cols['backlog']}     AS backlog,
        {cols['incoming_orders']}    AS incoming_orders,
        {cols['incoming_shipments']} AS incoming_shipments,
        {cols['on_order']}    AS on_order,
        {cols['placed_order']} AS placed_order
      FROM {table}
    """
    params: Dict = {}
    if scenario_ids:
        ph = ", ".join([f":gid_{i}" for i in range(len(scenario_ids))])
        where = f" WHERE {cols['scenario_id']} IN ({ph})"
        params = {f"gid_{i}": gid for i, gid in enumerate(scenario_ids)}
        return base + where + " ORDER BY scenario_id, week, role", params
    else:
        return base + " ORDER BY scenario_id, week, role", params

def load_sequences_from_db(
    cfg: DbLookupConfig,
    params: SimulationParams,
    scenario_ids: Optional[List[int]] = None,
    window: int = 12,
    horizon: int = 1,
    config_id: Optional[int] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Load sequences of game states from the database.

    Returns (X, A, P, Y):
      X: [num_windows, T=window, N, F] node features  (N = site count from config)
      A: [2, N, N] adjacency matrices (0: shipments, 1: orders)
      P: [num_windows, C] global context (optional), here empty placeholder
      Y: [num_windows, N, T=horizon] action indices (discrete) to imitate

    Args:
        config_id: If provided, topology (site list + TransportationLane edges) is
                   loaded dynamically from the DB for the given SC config.
                   This enables training on any N-node supply chain topology.
                   If None, falls back to the deprecated 4-node Beer Game constants.
    """
    engine: Engine = create_engine(cfg.database_url)
    sql, bind = _build_select_sql(cfg, scenario_ids)

    with engine.connect() as conn:
        rows = conn.execute(text(sql), bind).mappings().all()

    # -----------------------------------------------------------------
    # Determine topology: dynamic (config_id provided) or legacy (4-node)
    # -----------------------------------------------------------------
    if config_id is not None:
        # Load sites and transportation lanes from the SC config
        sc_engine: Engine = create_engine(cfg.database_url)
        with sc_engine.connect() as sc_conn:
            site_rows = sc_conn.execute(
                text("SELECT id, name, master_type FROM site WHERE config_id = :cid ORDER BY id"),
                {"cid": config_id},
            ).mappings().all()
            lane_rows = sc_conn.execute(
                text("SELECT from_site_id, to_site_id FROM transportation_lane WHERE config_id = :cid"),
                {"cid": config_id},
            ).mappings().all()

        site_names: List[str] = [r["name"] for r in site_rows]
        site_master_types: Dict[str, str] = {r["name"]: (r["master_type"] or "inventory") for r in site_rows}
        site_index: Dict[str, int] = {name: i for i, name in enumerate(site_names)}
        n = len(site_names)

        # Build N×N adjacency matrices from TransportationLane records
        # Shipment: from_site → to_site direction
        # Order: opposite direction (demand signal flows upstream)
        site_id_to_name = {r["id"]: r["name"] for r in site_rows}
        A_ship = np.zeros((n, n), dtype=np.float32)
        A_order = np.zeros((n, n), dtype=np.float32)
        for lane in lane_rows:
            from_name = site_id_to_name.get(lane["from_site_id"])
            to_name = site_id_to_name.get(lane["to_site_id"])
            if from_name in site_index and to_name in site_index:
                u, v = site_index[from_name], site_index[to_name]
                A_ship[u, v] = 1.0   # shipments: from_site → to_site
                A_order[v, u] = 1.0  # orders:    to_site → from_site

        def _node_feature(role_name: str, rec: dict) -> np.ndarray:
            return assemble_node_features(
                master_type=site_master_types.get(role_name, "inventory"),
                inventory=int(rec["inventory"]),
                backlog=int(rec["backlog"]),
                incoming_orders=int(rec["incoming_orders"]),
                incoming_shipments=int(rec["incoming_shipments"]),
                on_order=int(rec["on_order"]),
                params=params,
            )
    else:
        # DEPRECATED: legacy 4-node Beer Game fallback
        from .config import NODES, NODE_INDEX, SHIPMENT_EDGES, ORDER_EDGES
        site_names = NODES
        site_index = NODE_INDEX
        n = len(NODES)
        site_master_types = {
            "retailer": "inventory", "wholesaler": "inventory",
            "distributor": "inventory", "manufacturer": "manufacturer",
        }

        A_ship = np.zeros((n, n), dtype=np.float32)
        A_order = np.zeros((n, n), dtype=np.float32)
        for u, v in SHIPMENT_EDGES:
            A_ship[u, v] = 1.0
        for u, v in ORDER_EDGES:
            A_order[u, v] = 1.0

        def _node_feature(role_name: str, rec: dict) -> np.ndarray:
            return assemble_node_features(
                master_type=site_master_types.get(role_name, "inventory"),
                inventory=int(rec["inventory"]),
                backlog=int(rec["backlog"]),
                incoming_orders=int(rec["incoming_orders"]),
                incoming_shipments=int(rec["incoming_shipments"]),
                on_order=int(rec["on_order"]),
                params=params,
            )

    # -----------------------------------------------------------------
    # Bucket rows by (scenario_id, week)
    # -----------------------------------------------------------------
    # Bucket rows by (scenario_id, week) to form N nodes per week
    by_gw: Dict[Tuple[int, int], Dict[str, dict]] = {}
    for r in rows:
        key = (int(r["scenario_id"]), int(r["week"]))
        by_gw.setdefault(key, {})[r["role"]] = dict(r)

    # Build ordered timelines per scenario_id
    by_game: Dict[int, List[Dict[str, dict]]] = {}
    for (gid, wk), role_map in by_gw.items():
        by_game.setdefault(gid, []).append({"week": wk, "roles": role_map})
    for gid in by_game:
        by_game[gid].sort(key=lambda e: e["week"])

    # Convert to arrays
    X_windows: List[np.ndarray] = []
    Y_windows: List[np.ndarray] = []
    P_windows: List[np.ndarray] = []

    A = np.stack([A_ship, A_order], axis=0)  # [2, N, N]

    for gid, timeline in by_game.items():
        # Require all sites to have records per week
        weeks = [w for w in timeline if all(s in w["roles"] for s in site_names)]
        if len(weeks) < window + horizon:
            continue

        # Slide windows
        for start in range(0, len(weeks) - (window + horizon) + 1):
            obs_block = weeks[start : start + window]
            fut_block = weeks[start + window : start + window + horizon]

            # X[t, n, f]
            X_block = np.zeros((window, n, len(NODE_FEATURES)), dtype=np.float32)
            for t, w in enumerate(obs_block):
                for site_name in site_names:
                    rec = w["roles"][site_name]
                    X_block[t, site_index[site_name]] = _node_feature(site_name, rec)

            # Y[t, n] (action indices) — imitate the placed orders in the future block
            Y_block = np.zeros((horizon, n), dtype=np.int64)
            for t, w in enumerate(fut_block):
                for site_name in site_names:
                    rec = w["roles"][site_name]
                    Y_block[t, site_index[site_name]] = order_units_to_action_idx(int(rec["placed_order"]))

            X_windows.append(X_block)
            Y_windows.append(Y_block)
            P_windows.append(np.zeros((0,), dtype=np.float32))  # no globals for now

    if not X_windows:
        raise RuntimeError(
            "No training windows built from DB — check steps_table name and column_map!"
        )

    X = np.stack(X_windows, axis=0)  # [B, T, N, F]
    Y = np.stack(Y_windows, axis=0)  # [B, H, N]
    Y = np.swapaxes(Y, 1, 2)  # expose nodes on axis 1 for downstream consumers
    P = np.stack(P_windows, axis=0)  # [B, 0]
    return X, A, P, Y


def _load_param_ranges_from_config(
    supply_chain_config_id: int,
    db_url: Optional[str] = None,
) -> Dict[str, Tuple[float, float]]:
    """Derive simulator parameter ranges from a stored supply chain config."""

    resolved_url = db_url or resolve_sync_database_url()
    if not resolved_url:
        logger.warning(
            "No database URL available when loading config %s; using defaults.",
            supply_chain_config_id,
        )
        return {}

    def _parse_range(raw) -> Optional[Tuple[float, float]]:
        if raw is None:
            return None
        if isinstance(raw, str):
            raw = raw.strip()
            if not raw:
                return None
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON range: %s", raw)
                return None
        if isinstance(raw, dict):
            lo = raw.get("min")
            hi = raw.get("max", lo)
            if lo is None and hi is None:
                return None
            if lo is None:
                lo = hi
            if hi is None:
                hi = lo
            try:
                return float(lo), float(hi)
            except (TypeError, ValueError):
                return None
        if isinstance(raw, (list, tuple)) and raw:
            try:
                return float(raw[0]), float(raw[-1])
            except (TypeError, ValueError):
                return None
        if isinstance(raw, (int, float)):
            val = float(raw)
            return val, val
        return None

    def _merge_range(
        bucket: Dict[str, Tuple[float, float]],
        name: str,
        candidate: Optional[Tuple[float, float]],
        *,
        as_int: bool = False,
    ) -> None:
        if not candidate:
            return
        lo, hi = candidate
        if lo is None or hi is None:
            return
        if as_int:
            lo = int(math.floor(lo))
            hi = int(math.ceil(hi))
        existing = bucket.get(name)
        if existing:
            lo = min(lo, existing[0])
            hi = max(hi, existing[1])
        bucket[name] = (lo, hi)

    ranges: Dict[str, Tuple[float, float]] = {}

    engine: Optional[Engine] = None
    try:
        engine = create_engine(resolved_url)
        with engine.connect() as conn:
            node_rows = conn.execute(
                text(
                    """
                    SELECT
                        inc.initial_inventory_range AS initial_inventory_range,
                        inc.inventory_target_range AS inventory_target_range,
                        inc.holding_cost_range AS holding_cost_range,
                        inc.backlog_cost_range AS backlog_cost_range
                    FROM item_node_configs inc
                    JOIN nodes n ON inc.site_id = n.id
                    WHERE n.config_id = :cfg_id
                    """
                ),
                {"cfg_id": supply_chain_config_id},
            ).mappings().all()

            for row in node_rows:
                init_range = _parse_range(row.get("initial_inventory_range"))
                _merge_range(ranges, "init_inventory", init_range, as_int=True)

                target_range = _parse_range(row.get("inventory_target_range"))
                _merge_range(ranges, "max_order", target_range, as_int=True)

                holding_range = _parse_range(row.get("holding_cost_range"))
                _merge_range(ranges, "holding_cost", holding_range)

                backlog_range = _parse_range(row.get("backlog_cost_range"))
                _merge_range(ranges, "backlog_cost", backlog_range)

            lane_rows = conn.execute(
                text(
                    """
                    SELECT capacity, lead_time_days
                    FROM lanes
                    WHERE config_id = :cfg_id
                    """
                ),
                {"cfg_id": supply_chain_config_id},
            ).mappings().all()

            for row in lane_rows:
                capacity = row.get("capacity")
                if capacity is not None:
                    _merge_range(
                        ranges,
                        "max_inbound_per_link",
                        (float(capacity), float(capacity)),
                        as_int=True,
                    )

                lead_range = _parse_range(row.get("lead_time_days"))
                if lead_range:
                    week_lo = max(0.0, lead_range[0] / 7.0)
                    week_hi = max(week_lo, lead_range[1] / 7.0)
                    _merge_range(
                        ranges,
                        "supply_leadtime",
                        (week_lo, week_hi),
                        as_int=True,
                    )

    except Exception as exc:
        logger.warning(
            "Failed to derive parameter ranges for config %s: %s",
            supply_chain_config_id,
            exc,
        )
        return {}
    finally:
        if engine is not None:
            engine.dispose()

    return ranges


def _coerce_agent_strategy(strategy: Union[AgentStrategy, str]) -> AgentStrategy:
    """Normalise user provided strategy tokens to an AgentStrategy enum."""

    if isinstance(strategy, AgentStrategy):
        return strategy

    token = str(strategy).strip().lower()
    if not token:
        return AgentStrategy.LLM

    try:
        return AgentStrategy(token)
    except ValueError:
        try:
            return AgentStrategy[token.upper()]
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise ValueError(f"Unsupported agent strategy: {strategy}") from exc

# ---------- Simulator (synthetic data) ----------------------------------------

@dataclass
class SimDemand:
    """Simple piecewise-constant demand with an optional step change."""
    base: int = 4
    step_to: int = 12
    step_week: int = 4

    def __call__(self, t: int) -> int:
        return self.base if t < self.step_week else self.step_to

def simulate_supply_chain(
    T: int,
    params: SimulationParams,
    demand_fn=SimDemand(),
    *,
    agent_strategy: Union[AgentStrategy, str] = AgentStrategy.LLM,
    llm_model: Optional[str] = "qwen3-8b",
    history_window: Optional[int] = None,
    pid_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, List[int]]]:
    """
    Simulate a supply chain run with the given parameters.
    
    Returns a dict per role with time series:
        inventory, backlog, incoming_orders, incoming_shipments, on_order, placed_order
    """
    roles = NODES
    strategy_enum = _coerce_agent_strategy(agent_strategy)
    llm_enabled_strategies = {
        AgentStrategy.LLM,
        AgentStrategy.LLM_SUPERVISED,
        AgentStrategy.LLM_GLOBAL,
    }
    agents = {
        role: SimulationAgent(
            agent_id=index,
            agent_type=AgentType[role.upper()],
            strategy=strategy_enum,
            can_see_demand=True,
            initial_inventory=params.init_inventory,
            initial_orders=4,
            llm_model=llm_model if strategy_enum in llm_enabled_strategies else None,
        )
        for index, role in enumerate(roles)
    }

    if strategy_enum == AgentStrategy.PID and pid_params:
        for agent in agents.values():
            agent.configure_pid(**pid_params)
    # state
    inv = {r: [params.init_inventory] for r in roles}
    back = {r: [0] for r in roles}
    in_ord = {r: [0] for r in roles}
    in_ship = {r: [0] for r in roles}
    on_ord = {r: [0] for r in roles}
    placed = {r: [] for r in roles}

    history_by_role: Dict[str, List[Dict[str, Any]]] = {r: [] for r in roles}
    orders_by_role_round: Dict[str, Dict[int, int]] = {r: {} for r in roles}

    visible_history_weeks = history_window if history_window is not None else 30
    volatility_window = 14
    prod_lead = 4
    toggles = {
        "customer_demand_history_sharing": False,
        "volatility_signal_sharing": False,
        "downstream_inventory_visibility": False,
    }

    try:
        initial_demand = max(0, int(demand_fn(0)))
    except (TypeError, ValueError):
        initial_demand = 0

    # pipelines for delays (FIFO queues)
    info_pipes = {
        r: [initial_demand] * params.order_leadtime if params.order_leadtime > 0 else []
        for r in roles
    }
    ship_pipes = {
        r: [initial_demand] * params.supply_leadtime if params.supply_leadtime > 0 else []
        for r in roles
    }

    def clip_ship(x):  # shipping capacity
        return min(x, params.max_inbound_per_link)

    def _trim_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if visible_history_weeks and visible_history_weeks > 0:
            return records[-visible_history_weeks:]
        return records[:]

    def _history_section(role: str) -> Dict[str, Any]:
        records = _trim_records(history_by_role.get(role, []))
        downstream_role = DOWNSTREAM_ROLE_MAP.get(role)
        downstream_orders_map = (
            orders_by_role_round.get(downstream_role, {}) if downstream_role else {}
        )

        shipments_history: List[int] = []
        orders_history: List[int] = []
        demand_history: List[int] = []

        for entry in records:
            round_id = entry.get("round", 0)
            order_up_value = int(entry.get("order_up", 0))
            inventory_before = int(entry.get("inventory_before", 0))
            backlog_before = int(entry.get("backlog_before", 0))

            if role == "retailer":
                demand_val = int(entry.get("customer_demand") or 0)
                demand_history.append(demand_val)
            else:
                demand_val = int(downstream_orders_map.get(round_id, 0))

            total_demand = demand_val + backlog_before
            shipped_qty = min(inventory_before, total_demand)

            orders_history.append(order_up_value)
            shipments_history.append(int(shipped_qty))

        history_section: Dict[str, Any] = {
            "shipments_sent": shipments_history,
        }
        if role == "manufacturer":
            history_section["production_orders"] = orders_history
        else:
            history_section["orders_placed"] = orders_history
        if role == "retailer" and demand_history:
            history_section["demand"] = demand_history
        return history_section

    def _assemble_roles_section() -> Dict[str, Dict[str, Any]]:
        section: Dict[str, Dict[str, Any]] = {}
        for role in roles:
            role_key = ROLE_NAME_MAP.get(role, role)
            section[role_key] = {
                "inventory": inv[role][-1],
                "backlog": back[role][-1],
                "pipeline": [int(x) for x in ship_pipes[role]],
                "incoming_order": in_ord[role][-1],
                "history": _history_section(role),
            }
        return section

    def _snapshot_history() -> Dict[str, List[Dict[str, Any]]]:
        return {
            role: _trim_records(history_by_role.get(role, []))
            for role in roles
        }

    def _engine_state_snapshot() -> Dict[str, Dict[str, Any]]:
        snapshot: Dict[str, Dict[str, Any]] = {}
        for role in roles:
            snapshot[role] = {
                "incoming_orders": in_ord[role][-1],
                "info_queue": [int(x) for x in info_pipes[role]],
                "ship_queue": [int(x) for x in ship_pipes[role]],
                "last_arrival": int(in_ship[role][-1] if in_ship[role] else 0),
            }
        return snapshot

    for t in range(T):
        # incoming orders at retailer = external demand
        in_ord["retailer"].append(demand_fn(t))

        # propagate orders upstream with order leadtime
        for dn, up in ORDER_EDGES:  # (downstream -> upstream)
            src_role = NODES[dn]
            dst_role = NODES[up]
            # downstream placed orders enter info pipe towards upstream
            outgoing = placed[src_role][-1] if placed[src_role] else 0
            pipe = info_pipes[dst_role]
            arriving = pipe.pop(0) if pipe else 0
            pipe.append(outgoing)
            in_ord[dst_role].append(arriving)

        # shipments downstream with supply lead time
        for up, dn in SHIPMENT_EDGES:
            src_role = NODES[up]
            dst_role = NODES[dn]
            outgoing = 0
            # can only ship what you have
            demand_here = in_ord[dst_role][-1] + back[dst_role][-1]
            outgoing = clip_ship(min(inv[src_role][-1], demand_here))
            pipe = ship_pipes[dst_role]
            arriving = pipe.pop(0) if pipe else 0
            pipe.append(outgoing)
            in_ship[dst_role].append(arriving)

        # update inventories/backlogs after shipments arrive & demand realized
        for r in roles:
            inv_r = inv[r][-1]
            incoming = in_ship[r][-1]
            demand = in_ord[r][-1] + back[r][-1]
            shipped = min(inv_r + incoming, demand)
            new_inv = max(0, inv_r + incoming - shipped)
            new_back = max(0, demand - (inv_r + incoming))
            inv[r].append(new_inv)
            back[r].append(new_back)

        # simple heuristic ordering (base-stock vibe) for behavior traces
        previous_orders_by_role = {
            role: placed[role][-1] if placed[role] else 0 for role in roles
        }

        roles_section_snapshot = _assemble_roles_section()
        history_snapshot = _snapshot_history()
        engine_state_snapshot = _engine_state_snapshot()

        downstream_orders_map: Dict[str, Dict[str, int]] = {role: {} for role in roles}
        for dn_idx, up_idx in ORDER_EDGES:
            downstream_role = NODES[dn_idx]
            upstream_role = NODES[up_idx]
            order_value = placed[downstream_role][-1] if placed[downstream_role] else 0
            downstream_orders_map[upstream_role][downstream_role] = order_value

        for r in roles:
            agent = agents[r]
            inventory_before = inv[r][-1]
            backlog_before = back[r][-1]
            agent.inventory = inventory_before
            agent.backlog = backlog_before
            agent.pipeline = list(ship_pipes[r])
            local_state = {
                "inventory": inventory_before,
                "backlog": backlog_before,
                "incoming_shipments": ship_pipes[r],
                "pipeline": on_ord[r][-1],
            }
            downstream_orders = {
                child: downstream_orders_map.get(r, {}).get(child, 0)
                for child in downstream_orders_map.get(r, {})
            }
            upstream_data = {
                "previous_orders_by_role": previous_orders_by_role,
                "previous_orders": placed[r][-3:] if len(placed[r]) >= 3 else placed[r],
                "downstream_orders": downstream_orders,
            }
            if strategy_enum in llm_enabled_strategies:
                action_role_key = ROLE_NAME_MAP.get(r, r)
                payload = compose_autonomy_payload(
                    action_role_key=action_role_key,
                    raw_action_role=r,
                    round_number=t,
                    order_lead=params.order_leadtime,
                    ship_lead=params.supply_leadtime,
                    prod_lead=prod_lead,
                    holding_cost=params.holding_cost,
                    backlog_cost=params.backlog_cost,
                    toggles=toggles,
                    engine_state=engine_state_snapshot,
                    roles_section=roles_section_snapshot,
                    history_by_role=history_snapshot,
                    volatility_window=volatility_window,
                    visible_history_weeks=visible_history_weeks,
                )
                upstream_data["llm_payload"] = payload
            current_demand = in_ord[r][-1] if in_ord[r] else None
            try:
                decision = agent.make_decision(
                    current_round=t,
                    current_demand=current_demand,
                    upstream_data=upstream_data,
                    local_state=local_state,
                )
                if isinstance(decision, AgentDecision):
                    order_units = decision.quantity
                else:
                    order_units = int(decision)
            except Exception:
                target = params.init_inventory + params.supply_leadtime * 2
                desired = target + back[r][-1] - inv[r][-1] - on_ord[r][-1]
                order_units = int(np.clip(desired, 0, params.max_order))
            order_units = max(0, int(order_units))
            order_units = min(order_units, params.max_order)
            act_idx = order_units_to_action_idx(order_units)
            order_units = action_idx_to_order_units(act_idx)
            history_by_role[r].append(
                {
                    "round": t,
                    "order_up": order_units,
                    "inventory_before": inventory_before,
                    "backlog_before": backlog_before,
                    "customer_demand": current_demand if r == "retailer" else None,
                }
            )
            orders_by_role_round[r][t] = order_units
            placed[r].append(order_units)
            on_ord[r].append(max(0, on_ord[r][-1] + order_units - in_ship[r][-1]))

    # trim first seed element to align lengths
    def trim(series: List[int]) -> List[int]:
        return series[1:] if len(series) and len(series[1:]) == T else series[:T]

    out = {}
    for r in roles:
        out[r] = {
            "inventory": trim(inv[r]),
            "backlog": trim(back[r]),
            "incoming_orders": trim(in_ord[r]),
            "incoming_shipments": trim(in_ship[r]),
            "on_order": trim(on_ord[r]),
            "placed_order": placed[r][:T],
        }
    return out


def simulate_supply_chain_simpy(
    T: int,
    params: SimulationParams,
    demand_fn=SimDemand(),
    alpha: float = 0.3,
    wip_k: float = 1.0,
) -> Dict[str, Dict[str, List[int]]]:
    """
    SimPy-backed week-stepped simulation with a smoother ordering policy to reduce bullwhip.
    Default demand pattern is classic simulation: flat base, then a step up that stays flat.
    """
    if simpy is None:
        # If SimPy isn't available, fall back to the discrete simulator
        return simulate_supply_chain(T=T, params=params, demand_fn=demand_fn)

    env = simpy.Environment()

    roles = list(NODES)
    inv = {r: [params.init_inventory] for r in roles}
    back = {r: [0] for r in roles}
    in_ord = {r: [0] for r in roles}
    in_ship = {r: [0] for r in roles}
    on_ord = {r: [0] for r in roles}
    placed = {r: [] for r in roles}

    try:
        initial_demand = max(0, int(demand_fn(0)))
    except (TypeError, ValueError):
        initial_demand = 0

    info_pipes = {
        r: [initial_demand] * params.order_leadtime if params.order_leadtime > 0 else []
        for r in roles
    }
    ship_pipes = {
        r: [initial_demand] * params.supply_leadtime if params.supply_leadtime > 0 else []
        for r in roles
    }
    # Simple per-role demand/throughput forecast to dampen swings
    forecast = {r: float(params.init_inventory) / max(1, params.supply_leadtime + 1) for r in roles}

    def clip_ship(x: int) -> int:
        return int(min(max(0, x), params.max_inbound_per_link))

    def step():
        # External demand hits retailer
        in_ord["retailer"].append(demand_fn(len(placed["retailer"])) )

        # Orders propagate upstream (info delay)
        for dn, up in ORDER_EDGES:
            src_role = NODES[dn]
            dst_role = NODES[up]
            outgoing = placed[src_role][-1] if placed[src_role] else 0
            pipe = info_pipes[dst_role]
            arriving = pipe.pop(0) if pipe else 0
            pipe.append(outgoing)
            in_ord[dst_role].append(arriving)

        # Shipments propagate downstream (supply lead time)
        for up, dn in SHIPMENT_EDGES:
            src_role = NODES[up]
            dst_role = NODES[dn]
            demand_here = in_ord[dst_role][-1] + back[dst_role][-1]
            outgoing = clip_ship(min(inv[src_role][-1], demand_here))
            pipe = ship_pipes[dst_role]
            arriving = pipe.pop(0) if pipe else 0
            pipe.append(outgoing)
            in_ship[dst_role].append(arriving)

        # Update inventory/backlog after shipments
        for r in roles:
            inv_r = inv[r][-1]
            incoming = in_ship[r][-1]
            demand = in_ord[r][-1] + back[r][-1]
            shipped = min(inv_r + incoming, demand)
            new_inv = max(0, inv_r + incoming - shipped)
            new_back = max(0, demand - (inv_r + incoming))
            inv[r].append(new_inv)
            back[r].append(new_back)

        # Smoother order policy (order-up-to with forecast + WIP correction)
        for r in roles:
            obs = float(in_ord[r][-1])
            forecast[r] = alpha * obs + (1.0 - alpha) * forecast[r]
            target_inv = params.init_inventory + params.supply_leadtime * 2
            order_up_to = target_inv + forecast[r] * params.supply_leadtime
            current_wip = inv[r][-1] + on_ord[r][-1]
            desired = max(0.0, order_up_to - current_wip + back[r][-1])
            raw_order = int(np.clip(wip_k * desired, 0, params.max_order))
            act_idx = order_units_to_action_idx(raw_order)
            order_units = action_idx_to_order_units(act_idx)
            placed[r].append(order_units)
            on_ord[r].append(max(0, on_ord[r][-1] + order_units - in_ship[r][-1]))

    def weekly(env):
        for _ in range(T):
            step()
            yield env.timeout(1)

    env.process(weekly(env))
    env.run()

    def trim(series: List[int]) -> List[int]:
        return series[1:] if len(series) and len(series[1:]) == T else series[:T]

    out = {}
    for r in roles:
        out[r] = {
            "inventory": trim(inv[r]),
            "backlog": trim(back[r]),
            "incoming_orders": trim(in_ord[r]),
            "incoming_shipments": trim(in_ship[r]),
            "on_order": trim(on_ord[r]),
            "placed_order": placed[r][:T],
        }
    return out

def _sample_params_uniform(base: SimulationParams, ranges: Optional[Dict[str, Tuple[float, float]]] = None) -> SimulationParams:
    """Sample simulation params uniformly within provided ranges (inclusive)."""
    rng = ranges or {}
    def pick(name: str, cur):
        if name not in rng:
            return cur
        lo, hi = rng[name]
        # integers for discrete params
        if isinstance(cur, int):
            return int(np.random.uniform(lo, hi + 1))
        else:
            return float(np.random.uniform(lo, hi))

    return SimulationParams(
        order_leadtime=pick(
            "order_leadtime",
            getattr(base, "order_leadtime", 0),
        ),
        supply_leadtime=pick(
            "supply_leadtime",
            getattr(base, "supply_leadtime", 0),
        ),
        init_inventory=pick("init_inventory", base.init_inventory),
        holding_cost=pick("holding_cost", base.holding_cost),
        backlog_cost=pick("backlog_cost", base.backlog_cost),
        max_inbound_per_link=pick("max_inbound_per_link", base.max_inbound_per_link),
        max_order=pick("max_order", base.max_order),
    )

def generate_sim_training_windows(
    num_runs: int,
    T: int,
    window: int = 52,
    horizon: int = 1,
    params: SimulationParams = SimulationParams(),
    param_ranges: Optional[Dict[str, Tuple[float, float]]] = None,
    randomize: bool = True,
    supply_chain_config_id: Optional[int] = None,
    db_url: Optional[str] = None,
    use_simpy: Optional[bool] = None,
    sim_alpha: float = 0.3,
    sim_wip_k: float = 1.0,
    agent_strategy: Union[AgentStrategy, str] = AgentStrategy.LLM,
    pid_params: Optional[Dict[str, Any]] = None,
    return_run_params: bool = False,
    run_params: Optional[Sequence[SimulationParams]] = None,
) -> Union[
    Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[SimulationParams]],
]:
    """
    Create imitation-learning windows from the simulator.

    If `randomize` is True, each run samples parameters uniformly within
    `param_ranges` (or sensible defaults if not provided).
    """
    Xs, Ys, Ps = [], [], []
    A_ship = np.zeros((4, 4), dtype=np.float32)
    A_order = np.zeros((4, 4), dtype=np.float32)
    for u, v in SHIPMENT_EDGES:
        A_ship[u, v] = 1.0
    for u, v in ORDER_EDGES:
        A_order[u, v] = 1.0
    A = np.stack([A_ship, A_order], axis=0)

    # Default ranges (broad but sane for simulation)
    default_ranges: Dict[str, Tuple[float, float]] = {
        "order_leadtime": (0, 6),
        "supply_leadtime": (0, 6),
        "init_inventory": (4, 60),
        "holding_cost": (0.1, 2.0),
        "backlog_cost": (0.2, 4.0),
        "max_inbound_per_link": (50, 300),
        "max_order": (50, 300),
    }

    cfg_ranges: Dict[str, Tuple[float, float]] = {}
    if supply_chain_config_id is not None:
        cfg_ranges = _load_param_ranges_from_config(
            supply_chain_config_id,
            db_url=db_url,
        )

    ranges = default_ranges.copy()
    ranges.update(cfg_ranges)
    if param_ranges:
        ranges.update(param_ranges)

    # Decide simulator backend; default to SimPy unless USE_SIMPY="0"
    if use_simpy is None:
        use_simpy = (_os.getenv("USE_SIMPY", "1") != "0")
    use_simpy = bool(use_simpy and simpy is not None)
    if use_simpy is False and simpy is None:
        logger.debug("SimPy not available; using discrete simulator")

    strategy_enum = _coerce_agent_strategy(agent_strategy)
    if use_simpy and strategy_enum != AgentStrategy.LLM:
        logger.info(
            "SimPy backend ignores agent strategy '%s'; switching to discrete simulator.",
            strategy_enum.value,
        )
        use_simpy = False

    def _safe_lookup(role: str, key: str, index: int, default: int = 0) -> int:
        try:
            sequence = trace[role][key]
            if index < 0 or index >= len(sequence):
                return default
            return int(sequence[index])
        except (KeyError, TypeError, ValueError):
            return default

    run_params_used: List[SimulationParams] = []

    if run_params is not None and len(run_params) < num_runs:
        raise ValueError("run_params length must be >= num_runs when provided")

    for run_index in range(num_runs):
        if run_params is not None:
            sim_params = copy.deepcopy(run_params[run_index])
        else:
            sim_params = _sample_params_uniform(params, ranges) if randomize else params
        run_params_used.append(copy.deepcopy(sim_params))
        demand = SimDemand()  # flat, then step up (classic simulation)
        if use_simpy:
            trace = simulate_supply_chain_simpy(
                T=T,
                params=sim_params,
                demand_fn=demand,
                alpha=sim_alpha,
                wip_k=sim_wip_k,
            )
        else:
            trace = simulate_supply_chain(
                T=T,
                params=sim_params,
                demand_fn=demand,
                agent_strategy=strategy_enum,
                pid_params=pid_params if strategy_enum == AgentStrategy.PID else None,
            )
        # slide windows
        for start in range(0, T - (window + horizon) + 1):
            X = np.zeros((window, 4, len(NODE_FEATURES)), dtype=np.float32)
            Y = np.zeros((horizon, 4), dtype=np.int64)

            for t in range(window):
                for role in NODES:
                    X[t, NODE_INDEX[role]] = assemble_node_features(
                        role=role,
                        inventory=_safe_lookup(role, "inventory", start + t),
                        backlog=_safe_lookup(role, "backlog", start + t),
                        incoming_orders=_safe_lookup(role, "incoming_orders", start + t),
                        incoming_shipments=_safe_lookup(role, "incoming_shipments", start + t),
                        on_order=_safe_lookup(role, "on_order", start + t),
                        params=sim_params,
                    )

            for t in range(horizon):
                for role in NODES:
                    order_val = _safe_lookup(role, "placed_order", start + window + t)
                    Y[t, NODE_INDEX[role]] = order_units_to_action_idx(order_val)

            Xs.append(X)
            Ys.append(Y)
            Ps.append(np.zeros((0,), dtype=np.float32))

    X_arr = np.stack(Xs, axis=0)
    P_arr = np.stack(Ps, axis=0)
    Y_arr = np.stack(Ys, axis=0)
    Y_arr = np.swapaxes(Y_arr, 1, 2)  # [B, N, H]

    data_tuple = (X_arr, A, P_arr, Y_arr)

    if return_run_params:
        return (*data_tuple, run_params_used)

    return data_tuple
