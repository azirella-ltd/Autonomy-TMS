import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import (
    ACTION_LEVELS,
    SimulationParams,
    NODE_FEATURES,
)

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
# the 4 AWS SC site master_type categories).
_MASTER_TYPES = ["vendor", "customer", "inventory", "manufacturer"]


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
        config_id: SC config ID. Topology (site list + TransportationLane edges) is
                   loaded dynamically from the DB for the given config, enabling
                   training on any N-node supply chain topology. Required.
    """
    if config_id is None:
        raise ValueError(
            "config_id is required. Pass the SC config ID so the topology can be "
            "loaded from the database (Site + TransportationLane records)."
        )

    engine: Engine = create_engine(cfg.database_url)
    sql, bind = _build_select_sql(cfg, scenario_ids)

    with engine.connect() as conn:
        rows = conn.execute(text(sql), bind).mappings().all()

    # -----------------------------------------------------------------
    # Load topology from SC config
    # -----------------------------------------------------------------
    with engine.connect() as sc_conn:
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

    # -----------------------------------------------------------------
    # Bucket rows by (scenario_id, week)
    # -----------------------------------------------------------------
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
