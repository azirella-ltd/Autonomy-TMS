import argparse
import asyncio
import json
import re
from pathlib import Path
from textwrap import indent

from app.db.session import SessionLocal
from app.models.scenario import Scenario


round_re = re.compile(r"^Round\s+(\d+)")
node_re = re.compile(r"^\s*Node:\s*(.+)$")


async def fetch_states(game_id: int):
    """Fetch initial_state and engine_state for a scenario if available."""
    async with SessionLocal() as session:
        scenario = await session.get(Scenario, game_id)
        if not scenario or not scenario.config:
            return {}, {}
        cfg = dict(scenario.config)
        return cfg.get("initial_state") or {}, cfg.get("engine_state") or {}


def split_log(
    log_path: Path,
    out_dir: Path,
    initial_state=None,
    engine_state=None,
) -> None:
    """Split a full debug log into per-node files with round numbers."""
    initial_state = initial_state or {}
    engine_state = engine_state or {}

    per_node_blocks: dict[str, list[str]] = {}
    current_node: str | None = None
    current_round: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer, current_node, current_round
        if current_node and buffer:
            header = f"Round {current_round}" if current_round else "Round ?"
            payload = header + "\n" + "\n".join(buffer).rstrip() + "\n"
            per_node_blocks.setdefault(current_node, []).append(payload)
        buffer = []

    for line in log_path.read_text().splitlines():
        m_round = round_re.match(line)
        if m_round:
            current_round = m_round.group(1)
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

    out_dir.mkdir(parents=True, exist_ok=True)
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


async def main() -> None:
    parser = argparse.ArgumentParser(description="Split a debug log into per-node files.")
    parser.add_argument("log_path", type=Path, help="Path to the debug log file")
    parser.add_argument(
        "--game-id",
        type=int,
        default=None,
        help="Game id to pull initial_state/engine_state (optional)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: <log_path>_split)",
    )
    args = parser.parse_args()

    initial_state: dict = {}
    engine_state: dict = {}
    if args.game_id is not None:
        initial_state, engine_state = await fetch_states(args.game_id)

    out_dir = args.out_dir or args.log_path.with_name(args.log_path.stem + "_split")
    split_log(args.log_path, out_dir, initial_state=initial_state, engine_state=engine_state)
    print(f"Wrote per-node logs to {out_dir}")


if __name__ == "__main__":
    asyncio.run(main())
