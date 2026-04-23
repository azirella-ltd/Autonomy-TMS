"""Debug logging helpers for supply chain simulations."""

from __future__ import annotations

import json
import csv
import re
import logging
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from textwrap import indent

logger = logging.getLogger(__name__)

DEBUG_LOG_DIR = Path(
    os.getenv("AUTONOMY_DEBUG_DIR")
    or (Path(__file__).resolve().parents[2] / "debug_logs")
)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        token = value.strip().lower()
        return token in {"1", "true", "yes", "on", "enabled"}
    return False


def normalize_debug_config(config: Dict[str, Any]) -> Dict[str, Any]:
    raw = config.get("debug_logging")
    if isinstance(raw, dict):
        cfg = dict(raw)
    elif isinstance(raw, bool):
        cfg = {"enabled": raw}
    else:
        cfg = {}
    enabled_token = cfg.get("enabled", cfg.get("active", cfg.get("debug")))
    cfg["enabled"] = _to_bool(enabled_token)
    split_token = cfg.get("split_logs", cfg.get("split_nodes", cfg.get("split")))
    cfg["split_logs"] = _to_bool(split_token) if split_token is not None else False
    return cfg


def ensure_debug_log_file(config: Dict[str, Any], scenario: Any) -> Optional[Path]:
    cfg = normalize_debug_config(config)
    if not cfg.get("enabled"):
        config["debug_logging"] = {"enabled": False}
        return None

    path_value = cfg.get("file_path")
    start_time = getattr(scenario, "started_at", None) or getattr(scenario, "created_at", None)
    if isinstance(start_time, datetime):
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        timestamp = start_time.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S")
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    name_token = (getattr(scenario, "name", None) or f"scenario_{getattr(scenario, 'id', 'unknown')}")
    safe_token = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_" for char in name_token
    )[:48]
    filename = (
        f"{timestamp}_scenario_{getattr(scenario, 'id', 'unknown')}_{safe_token}.txt"
        if safe_token
        else f"{timestamp}_scenario_{getattr(scenario, 'id', 'unknown')}.txt"
    )

    preferred_path = Path(path_value) if path_value else DEBUG_LOG_DIR / filename
    fallback_path = DEBUG_LOG_DIR / filename if preferred_path != DEBUG_LOG_DIR / filename else None

    def _prepare(target: Path) -> Optional[Path]:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.parent.chmod(0o777)
            except Exception:
                pass
            if not target.exists():
                with target.open("w", encoding="utf-8") as handle:
                    handle.write(f"Scenario {getattr(scenario, 'id', 'unknown')} Debug Log\n")
                    name_value = getattr(scenario, "name", None)
                    if name_value:
                        handle.write(f"Name: {name_value}\n")
                    created_ts = None
                    if isinstance(start_time := getattr(scenario, "started_at", None), datetime):
                        created_ts = start_time
                    elif isinstance(start_time := getattr(scenario, "created_at", None), datetime):
                        created_ts = start_time
                    if created_ts:
                        if created_ts.tzinfo is None:
                            created_ts = created_ts.replace(tzinfo=timezone.utc)
                        created_str = created_ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    else:
                        created_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    handle.write(f"Created: {created_str}\n\n")
                try:
                    target.chmod(0o666)
                except Exception:
                    pass
            return target
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to prepare debug log at %s for scenario %s: %s",
                target,
                getattr(scenario, "id", "?"),
                exc,
            )
            return None

    path = _prepare(preferred_path)
    if path is None and fallback_path:
        path = _prepare(fallback_path)

    if path is None:
        cfg["enabled"] = False
        cfg["last_error"] = f"Unable to prepare debug log at {preferred_path}"
        config["debug_logging"] = cfg
        return None

    cfg["file_path"] = str(path)
    cfg.pop("last_error", None)

    config["debug_logging"] = cfg
    return path


def _format_debug_block(data: Any, *, indent: str = "      ") -> str:
    if data is None:
        return f"{indent}None"
    try:
        text = json.dumps(data, indent=2, sort_keys=True, default=str, ensure_ascii=False)
    except TypeError:
        text = json.dumps(str(data), ensure_ascii=False)
    return "\n".join(f"{indent}{line}" for line in text.splitlines())


def append_debug_round_log(
    config: Dict[str, Any],
    scenario: Any,
    *,
    round_number: int,
    timestamp: datetime,
    entries: List[Dict[str, Any]],
) -> None:
    if not entries:
        return

    path = ensure_debug_log_file(config, scenario)
    if not path:
        return

    iso_timestamp = timestamp.isoformat() + "Z"
    lines: List[str] = [f"Round {round_number} @ {iso_timestamp}"]
    for entry in entries:
        node_name = entry.get("node") or "unknown"
        lines.append(f"  Node: {node_name}")
        player_info = entry.get("scenario_user") or {}
        if player_info:
            player_label = player_info.get("name") or "Unnamed scenario_user"
            scenario_user_id = player_info.get("id")
            scenario_user_type = "AI" if player_info.get("is_ai") else "Human"
            if scenario_user_id is not None:
                lines.append(f"    ScenarioUser: {player_label} (ID: {scenario_user_id}, {scenario_user_type})")
            else:
                lines.append(f"    ScenarioUser: {player_label} ({scenario_user_type})")
        info_sent = entry.get("info_sent")
        lines.append("    Info provided:")
        lines.append(_format_debug_block(info_sent))
        reply = entry.get("reply")
        lines.append("    Reply:")
        lines.append(_format_debug_block(reply))
        step_trace = entry.get("step_trace")
        if step_trace:
            lines.append("    Step trace:")
            for step in step_trace:
                label = step.get("step", "Step")
                lines.append(f"      - {label}:")
                details = {k: v for k, v in step.items() if k != "step"}
                if details:
                    lines.append(_format_debug_block(details, indent="        "))
                else:
                    lines.append("        (no details)")
        ending_state = entry.get("ending_state")
        lines.append("    Ending state:")
        lines.append(_format_debug_block(ending_state))
    lines.append("")

    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to append debug log for scenario %s: %s", getattr(scenario, "id", "?"), exc)


def _append_debug_round_csv(
    config: Dict[str, Any],
    scenario: Any,
    *,
    round_number: int,
    entries: List[Dict[str, Any]],
) -> None:
    # CSV writing disabled
    return

    log_path = ensure_debug_log_file(config, scenario)
    if not log_path:
        return
    csv_path = log_path.with_suffix(".csv")

    item_name_map: Dict[str, str] = {}
    items_cfg = config.get("items") if isinstance(config, dict) else None
    if isinstance(items_cfg, list):
        for itm in items_cfg:
            if isinstance(itm, dict):
                itm_id = itm.get("id")
                itm_name = itm.get("name")
                if itm_id is not None and itm_name:
                    item_name_map[str(itm_id)] = str(itm_name)

    header = ["round", "node", "activity", "item", "N(inbound_demand)", "N(inbound_supply)", "inventory"]
    try:
        new_file = not csv_path.exists()
        with csv_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            if new_file:
                writer.writerow(header)
            for entry in entries:
                node = entry.get("node")
                reply = entry.get("reply") or {}
                ending_state = entry.get("ending_state") or {}
                inbound_demand = reply.get("inbound_demand") or []
                inbound_supply = reply.get("inbound_supply") or []
                inv_map = ending_state.get("inventory_by_item") or {}
                step_trace = entry.get("step_trace") or []

                def _coerce_counts(raw: Any) -> (Dict[str, int], int):
                    if isinstance(raw, dict):
                        counts = {str(k): int(v) for k, v in raw.items()}
                        return counts, sum(counts.values())
                    try:
                        total = int(raw or 0)
                    except Exception:
                        total = 0
                    return {}, total

                start_orders_counts: Dict[str, int] = {}
                start_supply_counts: Dict[str, int] = {}
                start_orders_total = 0
                start_supply_total = 0

                orders_counts: Dict[str, int] = {}
                supply_counts: Dict[str, int] = {}
                orders_total = 0
                supply_total = 0

                manufacture_finished: Dict[str, int] = {}
                manufacture_components: Dict[str, int] = {}
                consume_components: Dict[str, int] = {}
                produce_finished: Dict[str, int] = {}

                start_inv_total = None
                start_inv_map: Dict[str, int] = {}
                post_demand_inv_map: Dict[str, int] = {}
                post_supply_inv_map: Dict[str, int] = {}
                demand_supply_pending: Dict[str, int] = {}

                for step in step_trace:
                    if not isinstance(step, dict):
                        continue
                    label = step.get("step")
                    if label == "Start":
                        start_orders_counts, start_orders_total = _coerce_counts(step.get("inbound_demand"))
                        start_supply_counts, start_supply_total = _coerce_counts(step.get("inbound_supply"))
                        start_inv_total = step.get("inventory", start_inv_total)
                        inv_by_item = step.get("inventory_by_item")
                        if isinstance(inv_by_item, dict):
                            start_inv_map = {str(k): int(v) for k, v in inv_by_item.items()}
                    elif label == "Process Demand":
                        orders_counts, orders_total = _coerce_counts(step.get("inbound_demand"))
                        inv_by_item = step.get("inventory_by_item")
                        if isinstance(inv_by_item, dict):
                            post_demand_inv_map = {str(k): int(v) for k, v in inv_by_item.items()}
                        pending_supply = step.get("inbound_supply_pending")
                        if isinstance(pending_supply, dict):
                            demand_supply_pending = {str(k): int(v) for k, v in pending_supply.items()}
                        elif pending_supply is not None:
                            try:
                                demand_supply_pending = {"": int(pending_supply)}
                            except Exception:
                                demand_supply_pending = {}
                    elif label == "Process Supply":
                        supply_counts, supply_total = _coerce_counts(step.get("inbound_supply"))
                        inv_by_item = step.get("inventory_by_item")
                        if isinstance(inv_by_item, dict):
                            post_supply_inv_map = {str(k): int(v) for k, v in inv_by_item.items()}
                    elif label == "Manufacture":
                        fin = step.get("finished_inventory") or {}
                        comp = step.get("component_inventory") or {}
                        if isinstance(fin, dict):
                            manufacture_finished = {str(k): int(v) for k, v in fin.items()}
                        if isinstance(comp, dict):
                            manufacture_components = {str(k): int(v) for k, v in comp.items()}
                    elif label == "Produce":
                        fin = step.get("finished_inventory") or {}
                        if isinstance(fin, dict):
                            produce_finished = {str(k): int(v) for k, v in fin.items()}
                    elif label == "Consume":
                        comp = step.get("component_inventory") or {}
                        if isinstance(comp, dict):
                            consume_components = {str(k): int(v) for k, v in comp.items()}

                # Build per-item counts
                items = set(inv_map.keys())
                items.update(orders_counts.keys())
                items.update(supply_counts.keys())
                items.update(start_orders_counts.keys())
                items.update(start_supply_counts.keys())
                items.update(post_demand_inv_map.keys())
                items.update(post_supply_inv_map.keys())
                items.update(manufacture_finished.keys())
                items.update(manufacture_components.keys())
                for o in inbound_demand:
                    if isinstance(o, dict) and o.get("product_id"):
                        items.add(str(o["product_id"]))
                for s in inbound_supply:
                    if isinstance(s, dict) and s.get("product_id"):
                        items.add(str(s["product_id"]))
                if not items:
                    items = {""}

                if start_inv_total is None:
                    start_inv_total = sum(inv_map.values()) if isinstance(inv_map, dict) else ending_state.get("inventory", 0) or 0

                for item in items:
                    item_key = str(item)
                    start_orders = start_orders_counts.get(item_key, start_orders_total if start_orders_counts == {} else 0)
                    start_supply = start_supply_counts.get(item_key, start_supply_total if start_supply_counts == {} else 0)
                    post_orders = orders_counts.get(item_key, orders_total if orders_counts == {} else 0)
                    pending_supply = demand_supply_pending.get(item_key, demand_supply_pending.get("", supply_total if supply_counts == {} else 0))
                    post_supply = supply_counts.get(item_key, supply_total if supply_counts == {} else 0)

                    start_inv_item = start_inv_map.get(item_key, start_inv_total or 0)
                    post_demand_inv_item = post_demand_inv_map.get(item_key, start_inv_item)
                    post_supply_inv_item = post_supply_inv_map.get(item_key, inv_map.get(item_key, post_demand_inv_item) if isinstance(inv_map, dict) else post_demand_inv_item)
                    end_inv_item = inv_map.get(item_key, post_supply_inv_item) if isinstance(inv_map, dict) else post_supply_inv_item

                    display_item = item_name_map.get(str(item), item)
                    writer.writerow([round_number, node, "Start", display_item, start_orders, start_supply, start_inv_item])
                    writer.writerow([round_number, node, "Process Demand", display_item, post_orders, pending_supply, post_demand_inv_item])
                    # Produce/Consume (optional)
                    if produce_finished or manufacture_finished:
                        man_inv = produce_finished.get(item_key)
                        if man_inv is None:
                            man_inv = manufacture_finished.get(item_key, post_demand_inv_item)
                        writer.writerow([round_number, node, "Produce", display_item, post_orders, pending_supply, man_inv])
                    if consume_components or manufacture_components:
                        cons_inv = consume_components.get(item_key)
                        if cons_inv is None:
                            cons_inv = manufacture_components.get(item_key, post_demand_inv_item)
                        writer.writerow([round_number, node, "Consume", display_item, post_orders, pending_supply, cons_inv])
                    writer.writerow([round_number, node, "Process Supply", display_item, post_orders, post_supply, post_supply_inv_item])
                    writer.writerow([round_number, node, "Create Order", display_item, 0, 0, end_inv_item])
                    writer.writerow([round_number, node, "End", display_item, post_orders, post_supply, end_inv_item])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to append CSV debug for scenario %s: %s", getattr(scenario, "id", "?"), exc)


def split_debug_log_file(log_path: Path, *, cfg: Dict[str, Any]) -> None:
    """
    Split a combined debug log into per-node files (simple inline implementation).
    """
    if not log_path.exists():
        return
    initial_state = cfg.get("initial_state") or {}
    engine_state = cfg.get("engine_state") or {}
    out_dir = log_path.with_name(log_path.stem + "_split")
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        out_dir.chmod(0o777)
    except Exception:
        pass

    round_re = re.compile(r"^Round\s+(\d+)")
    node_re = re.compile(r"^\s*Node:\s*(.+)$")
    per_node_blocks: Dict[str, List[str]] = {}
    current_node = None
    current_period = None
    buffer: List[str] = []

    def flush():
        nonlocal buffer, current_node, current_period
        if current_node and buffer:
            header = f"Round {current_period}" if current_period else "Round ?"
            per_node_blocks.setdefault(current_node, []).append(header + "\n" + "\n".join(buffer).rstrip() + "\n")
        buffer.clear()

    for line in log_path.read_text().splitlines():
        m_round = round_re.match(line)
        if m_round:
            current_period = m_round.group(1)
            continue
        m_node = node_re.match(line)
        if m_node:
            flush()
            current_node = m_node.group(1).strip()
            buffer = [f"Node: {current_node}"]
            continue
        if current_node:
            buffer.append(line)
    flush()

    for node, blocks in per_node_blocks.items():
        fname = out_dir / f"{node.replace(' ', '_')}.txt"
        init_simple = initial_state.get(node) or initial_state.get(node.lower()) or {}
        engine = engine_state.get(node) or engine_state.get(node.lower()) or {}
        with fname.open("w", encoding="utf-8") as f:
            f.write(f"{log_path.name} — Node {node}\n")
            f.write("Initial state (config.initial_state):\n")
            f.write(indent(json.dumps(init_simple, indent=2), "  "))
            f.write("\n\n")
            if engine:
                f.write("Current engine_state snapshot (may be after play, for reference):\n")
                f.write(indent(json.dumps(engine, indent=2), "  "))
                f.write("\n\n")
            for blk in blocks:
                f.write(blk)
                f.write("\n")


def append_debug_error(
    config: Dict[str, Any],
    scenario: Any,
    message: str,
    *,
    details: Optional[Dict[str, Any]] = None,
    exc: Optional[BaseException] = None,
) -> None:
    """Write an error block to the debug log if enabled."""

    cfg = normalize_debug_config(config)
    if exc:
        logger.exception(
            "Debug log error for scenario %s: %s",
            getattr(scenario, "id", "?"),
            message,
            exc_info=(type(exc), exc, getattr(exc, "__traceback__", None)),
        )
    else:
        logger.error("Debug log note for scenario %s: %s", getattr(scenario, "id", "?"), message)

    if not cfg.get("enabled"):
        config["debug_logging"] = cfg
        return

    path = ensure_debug_log_file(config, scenario)
    if not path:
        return

    lines = [
        f"ERROR @ {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
        f"  Message: {message}",
    ]

    if details:
        lines.append("  Details:")
        try:
            encoded = json.dumps(details, indent=2, ensure_ascii=False, default=str)
        except TypeError:
            encoded = json.dumps(str(details), ensure_ascii=False)
        lines.extend(f"    {line}" for line in encoded.splitlines())

    if exc:
        lines.append("  Exception:")
        trace_lines = traceback.format_exception(type(exc), exc, getattr(exc, "__traceback__", None))
        lines.extend(f"    {line.rstrip()}" for line in trace_lines)

    lines.append("")

    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to append debug error for scenario %s: %s", getattr(scenario, "id", "?"), exc)
