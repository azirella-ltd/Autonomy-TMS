"""
Coordinated Simulation Runner — Multi-Head Trace Generation

Runs full episodes with all 11 TRMs executing through the 6-phase decision cycle,
with a live HiveSignalBus enabling stigmergic coordination between TRM heads.

Each episode produces a MultiHeadTrace capturing:
  - Per-TRM state/action/reward tuples
  - Urgency vector evolution across periods
  - Cross-head reward attribution (which signals improved outcomes)

Used for Sprint 5 of the TRM Hive Implementation Plan.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .hive_signal import HiveSignalBus, UrgencyVector
from .decision_cycle import (
    DecisionCyclePhase,
    CycleResult,
    PhaseResult,
    TRM_PHASE_MAP,
    PHASE_TRM_MAP,
    detect_conflicts,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Volume Guidance (Stöckl 2021, Kaplan scaling law)
# ---------------------------------------------------------------------------
# For 7M-param TRMs, coordinated simulation episodes are the primary data
# source for Phases 2-3 (context learning + RL). Each episode generates
# num_periods × num_active_trms state-action-reward tuples.
#
# Minimum recommendation:
#   5,000 episodes × 52 periods × ~7 TRMs = ~1.8M training tuples
#   This places us in the "medium" data regime from Stöckl 2021 where
#   models learn generalizable rules rather than memorizing patterns.
#
# Below 1,000 episodes, models plateau quickly and fail to generalize
# to novel multi-agent coordination patterns.
RECOMMENDED_MIN_EPISODES = 5_000


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TRMDecisionSnapshot:
    """Snapshot of a single TRM's decision within a coordinated cycle."""
    trm_name: str
    phase: str
    state_features: Optional[List[float]] = None
    action: Optional[Any] = None
    reward: float = 0.0
    confidence: float = 0.0
    signals_read: int = 0
    signals_emitted: int = 0
    urgency_before: float = 0.0
    urgency_after: float = 0.0
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trm_name": self.trm_name,
            "phase": self.phase,
            "action": self.action,
            "reward": self.reward,
            "confidence": self.confidence,
            "signals_read": self.signals_read,
            "signals_emitted": self.signals_emitted,
            "urgency_before": round(self.urgency_before, 4),
            "urgency_after": round(self.urgency_after, 4),
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class MultiHeadTrace:
    """One period's worth of coordinated decisions across all active TRM heads."""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    site_key: str = ""
    period: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Per-TRM snapshots
    decisions: List[TRMDecisionSnapshot] = field(default_factory=list)

    # Urgency vector snapshot at end of cycle
    urgency_snapshot: Optional[Dict[str, Any]] = None

    # Cross-head reward
    cross_head_reward: float = 0.0
    conflicts_detected: int = 0

    # Cycle timing
    cycle_duration_ms: float = 0.0
    total_signals: int = 0

    # Site tGNN (Layer 1.5) training data
    site_tgnn_features: Optional[Dict[str, Any]] = None  # Node features snapshot for BC training

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "trace_id": self.trace_id,
            "site_key": self.site_key,
            "period": self.period,
            "timestamp": self.timestamp.isoformat(),
            "decisions": [d.to_dict() for d in self.decisions],
            "urgency_snapshot": self.urgency_snapshot,
            "cross_head_reward": round(self.cross_head_reward, 4),
            "conflicts_detected": self.conflicts_detected,
            "cycle_duration_ms": round(self.cycle_duration_ms, 2),
            "total_signals": self.total_signals,
        }
        if self.site_tgnn_features:
            d["site_tgnn_features"] = self.site_tgnn_features
        return d


@dataclass
class EpisodeResult:
    """Result of a full multi-period coordinated episode."""
    episode_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    site_key: str = ""
    num_periods: int = 0
    traces: List[MultiHeadTrace] = field(default_factory=list)
    total_cross_head_reward: float = 0.0
    avg_signals_per_period: float = 0.0
    avg_conflicts_per_period: float = 0.0
    wall_time_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "site_key": self.site_key,
            "num_periods": self.num_periods,
            "total_cross_head_reward": round(self.total_cross_head_reward, 4),
            "avg_signals_per_period": round(self.avg_signals_per_period, 2),
            "avg_conflicts_per_period": round(self.avg_conflicts_per_period, 2),
            "wall_time_seconds": round(self.wall_time_seconds, 2),
            "traces_count": len(self.traces),
        }


# ---------------------------------------------------------------------------
# Cross-head reward computation
# ---------------------------------------------------------------------------

def compute_cross_head_reward(
    cycle_result: CycleResult,
    urgency_snapshot: Dict[str, Any],
) -> float:
    """Compute cross-head coordination reward from a decision cycle.

    Rewards:
    - Phase completion without errors: +0.1 per phase
    - Signal utilization (signals emitted > 0): +0.05 per phase with signals
    - Low urgency spread (coordinated response): +0.2 if urgency std < 0.2
    - Conflict-free cycle: +0.3 bonus

    Penalties:
    - Per-phase errors: -0.2 per error
    - High conflict count: -0.1 per conflict
    """
    reward = 0.0

    # Phase completion bonus
    for pr in cycle_result.phases:
        if pr.success:
            reward += 0.1
        else:
            reward -= 0.2 * len(pr.errors)

        if pr.signals_emitted > 0:
            reward += 0.05

    # Urgency spread bonus
    values = urgency_snapshot.get("values", [])
    if values:
        active_values = [v for v in values if v > 0.05]
        if active_values:
            spread = float(np.std(active_values))
            if spread < 0.2:
                reward += 0.2

    # Conflict penalty/bonus
    n_conflicts = len(cycle_result.conflicts_detected)
    if n_conflicts == 0:
        reward += 0.3
    else:
        reward -= 0.1 * n_conflicts

    return reward


# ---------------------------------------------------------------------------
# CoordinatedSimRunner
# ---------------------------------------------------------------------------

class CoordinatedSimRunner:
    """Runs coordinated multi-head episodes for hive trace generation.

    Each episode simulates ``num_periods`` time steps where all 11 TRMs
    execute through the 6-phase decision cycle with a shared signal bus.

    The runner is agnostic to the actual TRM implementations — callers
    provide executor factories that produce per-period callables.
    """

    def __init__(
        self,
        site_key: str,
        signal_bus: Optional[HiveSignalBus] = None,
        seed: Optional[int] = None,
        active_trms: Optional[frozenset] = None,
    ):
        self.site_key = site_key
        self.signal_bus = signal_bus or HiveSignalBus()
        self.rng = np.random.RandomState(seed)
        # When set, only these TRMs participate in decision cycles.
        # None means all 11 TRMs are active (backward compatible).
        self.active_trms: Optional[frozenset] = active_trms

    def run_episode(
        self,
        num_periods: int,
        executor_factory: Callable[[int], Dict[str, Callable]],
    ) -> EpisodeResult:
        """Run a full coordinated episode.

        Args:
            num_periods: Number of time periods to simulate.
            executor_factory: Callable(period) → Dict[trm_name → callable].
                Called once per period to get executors for that period's state.

        Returns:
            EpisodeResult with all traces and aggregate metrics.
        """
        result = EpisodeResult(
            site_key=self.site_key,
            num_periods=num_periods,
        )
        episode_start = time.monotonic()

        total_signals = 0
        total_conflicts = 0

        for period in range(num_periods):
            # Get executors for this period
            executors = executor_factory(period)

            # Run one coordinated cycle
            trace = self._run_cycle(period, executors)
            result.traces.append(trace)
            result.total_cross_head_reward += trace.cross_head_reward
            total_signals += trace.total_signals
            total_conflicts += trace.conflicts_detected

        result.wall_time_seconds = time.monotonic() - episode_start
        result.avg_signals_per_period = total_signals / max(1, num_periods)
        result.avg_conflicts_per_period = total_conflicts / max(1, num_periods)

        return result

    def _run_cycle(
        self,
        period: int,
        executors: Dict[str, Callable],
    ) -> MultiHeadTrace:
        """Execute one decision cycle and capture a MultiHeadTrace."""
        trace = MultiHeadTrace(
            site_key=self.site_key,
            period=period,
        )

        cycle_start = time.monotonic()
        cycle_result = CycleResult()

        for phase in DecisionCyclePhase:
            phase_start = time.monotonic()
            phase_result = PhaseResult(phase=phase)
            trm_names = PHASE_TRM_MAP.get(phase, [])
            signals_before = len(self.signal_bus)

            for trm_name in trm_names:
                # Skip TRMs not active for this site type
                if self.active_trms is not None and trm_name not in self.active_trms:
                    continue
                executor = executors.get(trm_name)
                if executor is None:
                    continue

                # Capture urgency before
                urgency_before, _, _ = self.signal_bus.urgency.read(trm_name)
                trm_start = time.monotonic()
                signals_pre = len(self.signal_bus)

                try:
                    result = executor()
                    phase_result.trms_executed.append(trm_name)

                    # Capture urgency after
                    urgency_after, _, _ = self.signal_bus.urgency.read(trm_name)
                    signals_post = len(self.signal_bus)

                    snapshot = TRMDecisionSnapshot(
                        trm_name=trm_name,
                        phase=phase.name,
                        action=result if isinstance(result, (int, float, str, bool)) else str(type(result).__name__),
                        urgency_before=urgency_before,
                        urgency_after=urgency_after,
                        signals_read=0,  # Would need instrumentation in TRMs
                        signals_emitted=signals_post - signals_pre,
                        duration_ms=(time.monotonic() - trm_start) * 1000.0,
                    )
                    trace.decisions.append(snapshot)

                except Exception as e:
                    phase_result.errors.append(f"{trm_name}: {e}")
                    logger.debug(f"Cycle {period} phase {phase.name} TRM {trm_name}: {e}")

            signals_after = len(self.signal_bus)
            phase_result.signals_emitted = signals_after - signals_before
            phase_result.duration_ms = (time.monotonic() - phase_start) * 1000.0
            cycle_result.phases.append(phase_result)
            cycle_result.total_signals_emitted += phase_result.signals_emitted

            # REFLECT: detect conflicts
            if phase == DecisionCyclePhase.REFLECT:
                try:
                    snapshot = self.signal_bus.urgency.snapshot()
                    cycle_result.conflicts_detected = detect_conflicts(snapshot)
                except Exception:
                    pass

        cycle_result.completed_at = datetime.now(timezone.utc)
        cycle_result.total_duration_ms = (time.monotonic() - cycle_start) * 1000.0

        # Capture final state
        trace.urgency_snapshot = self.signal_bus.urgency.snapshot()
        trace.cross_head_reward = compute_cross_head_reward(
            cycle_result, trace.urgency_snapshot
        )
        trace.conflicts_detected = len(cycle_result.conflicts_detected)
        trace.total_signals = cycle_result.total_signals_emitted
        trace.cycle_duration_ms = cycle_result.total_duration_ms

        return trace

    def run_batch(
        self,
        num_episodes: int,
        num_periods: int,
        executor_factory: Callable[[int], Dict[str, Callable]],
    ) -> List[EpisodeResult]:
        """Run multiple episodes and return all results.

        Data volume guidance (Stöckl 2021):
        - Minimum 5,000 episodes recommended for 7M-param TRMs.
        - Below 1,000, models memorize rather than generalize.
        - See RECOMMENDED_MIN_EPISODES constant.
        """
        if num_episodes < RECOMMENDED_MIN_EPISODES:
            logger.warning(
                f"num_episodes={num_episodes} is below the recommended minimum "
                f"of {RECOMMENDED_MIN_EPISODES} for 7M-param TRMs. Models may "
                f"memorize rather than learn generalizable coordination patterns."
            )
        results = []
        for ep in range(num_episodes):
            # Reset signal bus between episodes
            self.signal_bus.clear()
            self.signal_bus.urgency.reset()

            result = self.run_episode(num_periods, executor_factory)
            results.append(result)

            logger.info(
                f"Episode {ep + 1}/{num_episodes}: "
                f"{result.total_cross_head_reward:.2f} reward, "
                f"{result.avg_signals_per_period:.1f} signals/period"
            )

        return results
