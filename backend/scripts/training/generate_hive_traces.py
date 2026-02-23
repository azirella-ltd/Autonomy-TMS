#!/usr/bin/env python3
"""
Generate Hive Coordination Traces

Runs the CoordinatedSimRunner to produce multi-head traces where all 11 TRMs
execute through the 6-phase decision cycle with a live HiveSignalBus.

Output: JSON file with episode results for downstream training.

Usage:
    python scripts/training/generate_hive_traces.py --site-key SITE001 --episodes 10 --periods 52
    python scripts/training/generate_hive_traces.py --site-key SITE001 --episodes 50 --output data/hive_traces.json
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.powell.hive_signal import HiveSignalBus, HiveSignalType, HiveSignal
from app.services.powell.coordinated_sim_runner import CoordinatedSimRunner, EpisodeResult
from app.services.powell.decision_cycle import PHASE_TRM_MAP, DecisionCyclePhase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# All 11 TRM names
ALL_TRM_NAMES = [
    "atp_executor",
    "rebalancing",
    "po_creation",
    "order_tracking",
    "mo_execution",
    "to_execution",
    "quality",
    "maintenance",
    "subcontracting",
    "forecast_adj",
    "safety_stock",
]


# ---------------------------------------------------------------------------
# Synthetic executor factory
# ---------------------------------------------------------------------------

class SyntheticTRMExecutor:
    """Synthetic TRM executor that emits realistic signals and returns actions.

    Used when no trained TRM models are available. Simulates plausible
    decisions and signal emissions for trace generation.
    """

    def __init__(self, trm_name: str, signal_bus: HiveSignalBus, rng: np.random.RandomState):
        self.trm_name = trm_name
        self.signal_bus = signal_bus
        self.rng = rng

    def __call__(self):
        """Execute a synthetic decision, optionally emitting signals."""
        # Read current urgency for this TRM
        urgency, _, _ = self.signal_bus.urgency.read(self.trm_name)

        # Higher urgency → more likely to emit signals
        emit_prob = 0.3 + urgency * 0.5

        # Emit signals based on TRM type
        if self.rng.random() < emit_prob:
            signal_type = self._pick_signal_type()
            if signal_type is not None:
                urg = 0.3 + self.rng.random() * 0.7
                signal = HiveSignal(
                    signal_type=signal_type,
                    source_trm=self.trm_name,
                    urgency=urg,
                )
                self.signal_bus.emit(signal)

        # Update urgency based on "decision outcome"
        delta = self.rng.uniform(-0.1, 0.15)
        new_urgency = max(0.0, min(1.0, urgency + delta))
        direction = "risk" if delta > 0 else "relief"
        self.signal_bus.urgency.update(self.trm_name, new_urgency, direction)

        # Return a synthetic action index
        return int(self.rng.randint(0, 5))

    def _pick_signal_type(self):
        """Pick a signal type appropriate for this TRM."""
        signal_map = {
            "atp_executor": [HiveSignalType.ATP_SHORTAGE, HiveSignalType.DEMAND_SURGE],
            "rebalancing": [HiveSignalType.REBALANCE_INBOUND, HiveSignalType.REBALANCE_OUTBOUND],
            "po_creation": [HiveSignalType.PO_EXPEDITE, HiveSignalType.PO_DEFERRED],
            "order_tracking": [HiveSignalType.ORDER_EXCEPTION],
            "mo_execution": [HiveSignalType.MO_RELEASED, HiveSignalType.MO_DELAYED],
            "to_execution": [HiveSignalType.TO_RELEASED, HiveSignalType.TO_DELAYED],
            "quality": [HiveSignalType.QUALITY_REJECT, HiveSignalType.QUALITY_HOLD],
            "maintenance": [HiveSignalType.MAINTENANCE_DEFERRED, HiveSignalType.MAINTENANCE_URGENT],
            "subcontracting": [HiveSignalType.SUBCONTRACT_ROUTED],
            "forecast_adj": [HiveSignalType.FORECAST_ADJUSTED],
            "safety_stock": [HiveSignalType.SS_INCREASED, HiveSignalType.SS_DECREASED],
        }
        types = signal_map.get(self.trm_name, [])
        if not types:
            return None
        return self.rng.choice(types)


def build_executor_factory(signal_bus: HiveSignalBus, seed: int):
    """Build an executor factory that creates synthetic executors per period."""
    rng = np.random.RandomState(seed)

    def factory(period: int):
        executors = {}
        for trm_name in ALL_TRM_NAMES:
            executors[trm_name] = SyntheticTRMExecutor(trm_name, signal_bus, rng)
        return executors

    return factory


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Generate Hive Coordination Traces")
    parser.add_argument("--site-key", type=str, default="SITE001",
                        help="Site key for trace generation")
    parser.add_argument("--episodes", type=int, default=10,
                        help="Number of episodes to run")
    parser.add_argument("--periods", type=int, default=52,
                        help="Periods per episode")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON file (default: data/hive_traces_{site_key}.json)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable debug logging")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    output_path = args.output or f"data/hive_traces_{args.site_key}.json"
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"Generating hive traces: site={args.site_key}, "
        f"episodes={args.episodes}, periods={args.periods}, seed={args.seed}"
    )

    signal_bus = HiveSignalBus()
    runner = CoordinatedSimRunner(
        site_key=args.site_key,
        signal_bus=signal_bus,
        seed=args.seed,
    )

    executor_factory = build_executor_factory(signal_bus, args.seed)

    start = time.monotonic()
    results = runner.run_batch(
        num_episodes=args.episodes,
        num_periods=args.periods,
        executor_factory=executor_factory,
    )
    elapsed = time.monotonic() - start

    # Aggregate stats
    total_traces = sum(len(r.traces) for r in results)
    total_reward = sum(r.total_cross_head_reward for r in results)
    avg_signals = np.mean([r.avg_signals_per_period for r in results])
    avg_conflicts = np.mean([r.avg_conflicts_per_period for r in results])

    logger.info(f"Generation complete in {elapsed:.1f}s")
    logger.info(f"  Episodes: {len(results)}")
    logger.info(f"  Total traces: {total_traces}")
    logger.info(f"  Total cross-head reward: {total_reward:.2f}")
    logger.info(f"  Avg signals/period: {avg_signals:.1f}")
    logger.info(f"  Avg conflicts/period: {avg_conflicts:.2f}")

    # Serialize
    output_data = {
        "site_key": args.site_key,
        "episodes": args.episodes,
        "periods_per_episode": args.periods,
        "seed": args.seed,
        "generation_time_seconds": round(elapsed, 2),
        "summary": {
            "total_traces": total_traces,
            "total_cross_head_reward": round(total_reward, 4),
            "avg_signals_per_period": round(float(avg_signals), 2),
            "avg_conflicts_per_period": round(float(avg_conflicts), 2),
        },
        "episodes_summary": [r.to_dict() for r in results],
        "traces": [],
    }

    # Include all traces for training
    for result in results:
        for trace in result.traces:
            output_data["traces"].append(trace.to_dict())

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2, default=str)

    logger.info(f"Traces written to {output_file} ({output_file.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
