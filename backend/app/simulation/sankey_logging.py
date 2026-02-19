"""Utilities for writing Sankey diagram debug logs."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence, Tuple

from app.simulation.debug_logging import DEBUG_LOG_DIR

_SANKEY_LOG_DIR = Path(
    os.getenv("AUTONOMY_SANKEY_LOG_DIR")
    or (DEBUG_LOG_DIR / "sankey")
)

_MIN_LINK_VALUE = 0.0001


def _coerce_number(value: Any) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if number != number:  # NaN check
        return 0.0
    return number


def _coerce_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, MutableMapping):
        return value
    return {}


def _link_value(value: float) -> float:
    return max(_MIN_LINK_VALUE, max(0.0, value))


def _ensure_log_path(game: Any) -> Path:
    identifier = getattr(game, "id", None)
    suffix = f"game_{identifier}" if identifier is not None else "game_unknown"
    filename = f"{suffix}_sankey.json"
    path = _SANKEY_LOG_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _build_round_numbers(history: Iterable[Mapping[str, Any]]) -> Sequence[int]:
    rounds = []
    for entry in history:
        round_value = entry.get("round")
        if isinstance(round_value, int):
            rounds.append(round_value)
        else:
            try:
                coerced = int(round_value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            rounds.append(coerced)
    return rounds


def build_sankey_snapshot(history: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    processed_history = [entry for entry in history if isinstance(entry, Mapping)]
    return _build_snapshot_from_shipments(processed_history)


def _format_node_label(value: str) -> str:
    token = (value or "").strip()
    if not token:
        return "Unknown"
    cleaned = token.replace("_", " ").replace("-", " ")
    return " ".join(part.capitalize() if part else "" for part in cleaned.split())


def _build_snapshot_from_shipments(history: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    lane_totals: Dict[Tuple[str, str], float] = defaultdict(float)
    node_shipments: Dict[str, float] = defaultdict(float)
    node_meta: Dict[str, Dict[str, Any]] = {}
    inventory_totals: Dict[str, float] = defaultdict(float)
    inventory_counts: Dict[str, int] = defaultdict(int)
    rounds_with_data = 0
    total_demand = 0.0

    for entry in history:
        shipments_map = _coerce_mapping(entry.get("shipments"))
        if shipments_map:
            rounds_with_data += 1
        total_demand += _coerce_number(entry.get("demand"))

        node_states = _coerce_mapping(entry.get("node_states"))
        for raw_node, state in node_states.items():
            site_id = str(raw_node)
            if not site_id:
                continue
            meta = node_meta.setdefault(site_id, {})
            display_name = state.get("display_name") or state.get("name")
            if display_name:
                meta.setdefault("name", display_name)
            node_type = state.get("type") or state.get("role")
            if node_type:
                meta.setdefault("role", str(node_type))

            inv_value = state.get("inventory_after")
            if inv_value is None:
                inv_value = state.get("inventory")
            if inv_value is not None:
                inventory_totals[site_id] += _coerce_number(inv_value)
                inventory_counts[site_id] += 1

        inventory_positions = _coerce_mapping(entry.get("inventory_positions"))
        for raw_node, value in inventory_positions.items():
            site_id = str(raw_node)
            if not site_id:
                continue
            inventory_totals[site_id] += _coerce_number(value)
            inventory_counts[site_id] += 1

        for raw_source, targets in shipments_map.items():
            source = str(raw_source)
            target_map = _coerce_mapping(targets)
            if not source or not target_map:
                continue
            node_meta.setdefault(source, {})
            for raw_target, qty in target_map.items():
                target = str(raw_target)
                if not target:
                    continue
                amount = _coerce_number(qty)
                if amount <= 0:
                    continue
                lane_totals[(source, target)] += amount
                node_shipments[source] += amount
                node_shipments[target] += amount
                node_meta.setdefault(target, {})

    node_ids = sorted(node_meta.keys())
    nodes_payload = []
    for site_id in node_ids:
        meta = node_meta.get(site_id, {})
        avg_inventory = 0.0
        if inventory_counts.get(site_id):
            avg_inventory = inventory_totals.get(site_id, 0.0) / float(inventory_counts[site_id])
        nodes_payload.append(
            {
                "id": site_id,
                "name": meta.get("name") or _format_node_label(site_id),
                "role": meta.get("role") or "inventory",
                "shipments": max(node_shipments.get(site_id, 0.0), 0.0),
                "average_inventory": avg_inventory,
                "observations": inventory_counts.get(site_id, 0),
            }
        )

    links_payload = [
        {
            "id": f"{source}-{target}",
            "source": source,
            "target": target,
            "raw_value": max(value, 0.0),
            "value": _link_value(value),
        }
        for (source, target), value in sorted(lane_totals.items())
    ]

    lane_totals_payload = {
        f"{source}→{target}": max(value, 0.0)
        for (source, target), value in lane_totals.items()
    }
    inventory_totals_payload = {
        site_id: inventory_totals.get(site_id, 0.0)
        for site_id in node_ids
    }
    rounds = _build_round_numbers(history)
    avg_demand = (total_demand / rounds_with_data) if rounds_with_data else 0.0

    return {
        "rounds_analyzed": rounds_with_data,
        "round_numbers": rounds,
        "lane_totals": lane_totals_payload,
        "inventory_totals": inventory_totals_payload,
        "average_inventory": {node["id"]: node["average_inventory"] for node in nodes_payload},
        "total_demand": max(0.0, total_demand),
        "average_demand": max(0.0, avg_demand),
        "sites": nodes_payload,
        "links": links_payload,
    }




def write_sankey_log(game: Any, history: Sequence[Mapping[str, Any]]) -> Path:
    """Persist a debug snapshot for Sankey diagram generation."""

    path = _ensure_log_path(game)
    snapshot = build_sankey_snapshot(history or [])
    payload = {
        "game_id": getattr(game, "id", None),
        "game_name": getattr(game, "name", None),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "snapshot": snapshot,
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
    return path
