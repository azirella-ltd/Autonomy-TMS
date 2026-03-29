"""
Convert a debug log (per-round/per-node text) into a CSV summary.

Columns: round, node, activity, item, N(inbound_demand), N(inbound_supply), inventory
Activities emitted:
  - Start: inventory carried into the round (from previous ending or initial_state)
  - Process Demand: count of inbound_demand for the round
  - Process Supply: count of inbound_supply for the round
  - Create Order: placeholder (counts 0 – current debug log does not expose outbound order detail)
  - End: ending inventory reported in the log for the round
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
from pathlib import Path
from typing import Dict, Tuple, Any

from app.db.session import SessionLocal
from app.models.scenario import Scenario

round_re = re.compile(r"^Round\s+(\d+)")
node_re = re.compile(r"^\s*Node:\s*(.+)$")


async def fetch_initial_state(scenario_id: int) -> Dict[str, Dict[str, Any]]:
    async with SessionLocal() as session:
        scenario = await session.get(Scenario, scenario_id)
        if not scenario or not scenario.config:
            return {}
        cfg = dict(scenario.config)
        return cfg.get("initial_state") or {}


def parse_log(log_path: Path) -> Dict[Tuple[int, str], Dict[str, Any]]:
    """
    Parse the debug log into a dict keyed by (round, node) with reply/ending data.
    """
    data: Dict[Tuple[int, str], Dict[str, Any]] = {}
    current_period = None
    current_node = None
    in_reply = False
    in_ending = False
    reply_lines = []
    ending_lines = []
    for raw in log_path.read_text().splitlines():
        m_round = round_re.match(raw)
        if m_round:
            current_period = int(m_round.group(1))
            current_node = None
            in_reply = False
            in_ending = False
            reply_lines = []
            ending_lines = []
            continue
        m_node = node_re.match(raw)
        if m_node:
            current_node = m_node.group(1).strip()
            in_reply = False
            in_ending = False
            reply_lines = []
            ending_lines = []
            continue
        if current_node is None or current_period is None:
            continue
        if raw.strip().startswith('"inbound_demand"') or '"inbound_supply"' in raw:
            in_reply = True
            in_ending = False
        if raw.strip().startswith('"backlog"') and not in_reply:
            in_ending = True
        if in_reply:
            reply_lines.append(raw)
        if in_ending:
            ending_lines.append(raw)
        if raw.strip() == "}":
            if in_reply:
                try:
                    blob = json.loads("{\n" + "\n".join(reply_lines) + "\n}")
                except Exception:
                    blob = {}
                data.setdefault((current_period, current_node), {})["reply"] = blob
                in_reply = False
                reply_lines = []
            if in_ending:
                try:
                    blob = json.loads("{\n" + "\n".join(ending_lines) + "\n}")
                except Exception:
                    blob = {}
                data.setdefault((current_period, current_node), {})["ending"] = blob
                in_ending = False
                ending_lines = []
    return data


def build_csv(
    parsed: Dict[Tuple[int, str], Dict[str, Any]],
    initial_state: Dict[str, Dict[str, Any]],
    csv_path: Path,
) -> None:
    # Track carried inventory per node
    carry_inventory: Dict[str, int] = {
        node: int(state.get("inventory", 0) or 0) for node, state in initial_state.items()
    }
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["round", "node", "activity", "item", "N(inbound_demand)", "N(inbound_supply)", "inventory"])
        for (round_no, node) in sorted(parsed.keys()):
            entry = parsed[(round_no, node)]
            reply = entry.get("reply", {})
            ending = entry.get("ending", {})
            inbound_demand = reply.get("inbound_demand", [])
            inbound_supply = reply.get("inbound_supply", [])
            end_inv = int(ending.get("inventory", 0) or sum((ending.get("inventory_by_item") or {}).values() or [0]))

            # Start
            writer.writerow([round_no, node, "Start", "", len(inbound_demand), len(inbound_supply), carry_inventory.get(node, 0)])
            # Process Demand
            writer.writerow([round_no, node, "Process Demand", "", len(inbound_demand), 0, carry_inventory.get(node, 0)])
            # Process Supply
            writer.writerow([round_no, node, "Process Supply", "", 0, len(inbound_supply), end_inv])
            # Create Order (placeholder)
            writer.writerow([round_no, node, "Create Order", "", 0, 0, end_inv])
            # End
            writer.writerow([round_no, node, "End", "", len(inbound_demand), len(inbound_supply), end_inv])

            carry_inventory[node] = end_inv


async def main() -> None:
    parser = argparse.ArgumentParser(description="Convert debug log to CSV summary.")
    parser.add_argument("log_path", type=Path, help="Path to debug log")
    parser.add_argument("--scenario-id", type=int, default=None, help="Scenario ID to pull initial_state")
    parser.add_argument("--out", type=Path, default=None, help="Output CSV path (default: log_path with .csv)")
    args = parser.parse_args()

    initial_state: Dict[str, Dict[str, Any]] = {}
    if args.scenario_id is not None:
        initial_state = await fetch_initial_state(args.scenario_id)

    parsed = parse_log(args.log_path)
    out_path = args.out or args.log_path.with_suffix(".csv")
    build_csv(parsed, initial_state, out_path)
    print(f"Wrote CSV to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
