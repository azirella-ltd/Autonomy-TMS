"""
Hive Feedback Features — Feed-Back Signals for tGNN Input.

Aggregates local hive activity into 10 features that the tGNN consumes
as additional input alongside transactional data. This closes the
feedback loop: tGNN → hive directives → local TRM decisions → feedback → tGNN.

Architecture reference: TRM_HIVE_ARCHITECTURE.md Section 7

Features computed:
  1. avg_urgency                    — Mean urgency across 11 TRM slots
  2. urgency_spread                 — Std dev of active urgency values
  3. signal_rate                    — Signals emitted per cycle (recent)
  4. conflict_rate                  — Conflicts detected per cycle (recent)
  5. cross_head_reward              — Average cross-head coordination reward
  6. dominant_caste                 — One-hot for most active signal caste (5 dims → 1 encoded)
  7. ss_adjustment_dir              — Safety stock adjustment direction (-1/0/+1)
  8. exception_rate                 — Fraction of cycles with order exceptions
  9. site_tgnn_adjustment_magnitude — Mean |urgency adjustment| from last Site tGNN cycle
 10. cross_trm_conflict_rate        — Rate of cross-TRM conflicts detected by Site tGNN
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class HiveFeedbackFeatures:
    """Aggregated hive activity features for tGNN input.

    Computed from recent decision cycle results and the signal bus state.
    These 10 features extend the tGNN's per-site input tensor.
    """

    avg_urgency: float = 0.0           # Mean urgency across 11 TRM slots
    urgency_spread: float = 0.0        # Std dev of active urgency values
    signal_rate: float = 0.0           # Signals emitted per cycle
    conflict_rate: float = 0.0         # Conflicts per cycle
    cross_head_reward: float = 0.0     # Avg coordination reward
    dominant_caste: int = 0            # 0=Scout,1=Forager,2=Nurse,3=Guard,4=Builder
    ss_adjustment_dir: float = 0.0     # -1 (decreased), 0 (unchanged), +1 (increased)
    exception_rate: float = 0.0        # Fraction of cycles with order exceptions
    site_tgnn_adjustment_magnitude: float = 0.0  # Mean |urgency adj| from Site tGNN
    cross_trm_conflict_rate: float = 0.0         # Cross-TRM conflicts from Site tGNN

    def to_tensor(self) -> np.ndarray:
        """Return as a float32 array for tGNN input concatenation (10 dims)."""
        return np.array([
            self.avg_urgency,
            self.urgency_spread,
            self.signal_rate,
            self.conflict_rate,
            self.cross_head_reward,
            float(self.dominant_caste) / 4.0,  # Normalize to [0, 1]
            self.ss_adjustment_dir,
            self.exception_rate,
            self.site_tgnn_adjustment_magnitude,
            self.cross_trm_conflict_rate,
        ], dtype=np.float32)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "avg_urgency": round(self.avg_urgency, 4),
            "urgency_spread": round(self.urgency_spread, 4),
            "signal_rate": round(self.signal_rate, 2),
            "conflict_rate": round(self.conflict_rate, 2),
            "cross_head_reward": round(self.cross_head_reward, 4),
            "dominant_caste": self.dominant_caste,
            "ss_adjustment_dir": self.ss_adjustment_dir,
            "exception_rate": round(self.exception_rate, 4),
            "site_tgnn_adjustment_magnitude": round(self.site_tgnn_adjustment_magnitude, 4),
            "cross_trm_conflict_rate": round(self.cross_trm_conflict_rate, 4),
        }


# Caste-to-index mapping for dominant_caste encoding
_CASTE_NAMES = ["Scout", "Forager", "Nurse", "Guard", "Builder"]


def compute_feedback_features(
    urgency_snapshot: Optional[Dict[str, Any]] = None,
    recent_traces: Optional[Sequence] = None,
    signal_bus=None,
) -> HiveFeedbackFeatures:
    """Compute hive feedback features from current state and recent history.

    Args:
        urgency_snapshot: Output of UrgencyVector.snapshot() — dict with
            "values" (list of 11 floats), "directions" (list of 11 strings).
        recent_traces: List of MultiHeadTrace objects from recent cycles.
        signal_bus: Optional HiveSignalBus to compute signal caste stats.

    Returns:
        HiveFeedbackFeatures populated from the inputs.
    """
    features = HiveFeedbackFeatures()

    # --- 1 & 2: Urgency statistics ---
    if urgency_snapshot and "values" in urgency_snapshot:
        values = urgency_snapshot["values"]
        if values:
            features.avg_urgency = float(np.mean(values))
            active = [v for v in values if v > 0.05]
            if active:
                features.urgency_spread = float(np.std(active))

    # --- 3-5, 7-8: From recent traces ---
    if recent_traces and len(recent_traces) > 0:
        n = len(recent_traces)

        total_signals = sum(getattr(t, "total_signals", 0) for t in recent_traces)
        features.signal_rate = total_signals / n

        total_conflicts = sum(getattr(t, "conflicts_detected", 0) for t in recent_traces)
        features.conflict_rate = total_conflicts / n

        total_reward = sum(getattr(t, "cross_head_reward", 0.0) for t in recent_traces)
        features.cross_head_reward = total_reward / n

        # Exception rate: count traces where at least one order exception signal
        exception_count = 0
        for trace in recent_traces:
            decisions = getattr(trace, "decisions", [])
            for d in decisions:
                if getattr(d, "trm_name", "") == "order_tracking":
                    if getattr(d, "signals_emitted", 0) > 0:
                        exception_count += 1
                        break
        features.exception_rate = exception_count / n

        # Buffer adjustment direction: look at inventory_buffer TRM urgency direction
        ss_dirs = []
        for trace in recent_traces:
            decisions = getattr(trace, "decisions", [])
            for d in decisions:
                if getattr(d, "trm_name", "") == "inventory_buffer":
                    u_after = getattr(d, "urgency_after", 0.0)
                    u_before = getattr(d, "urgency_before", 0.0)
                    if u_after > u_before + 0.01:
                        ss_dirs.append(1.0)
                    elif u_after < u_before - 0.01:
                        ss_dirs.append(-1.0)
                    else:
                        ss_dirs.append(0.0)
        if ss_dirs:
            features.ss_adjustment_dir = float(np.sign(np.mean(ss_dirs)))

    # --- 6: Dominant caste from signal bus ---
    if signal_bus is not None:
        try:
            from .hive_signal import (
                SCOUT_SIGNALS, FORAGER_SIGNALS, NURSE_SIGNALS,
                GUARD_SIGNALS, BUILDER_SIGNALS,
            )
            caste_groups = [
                SCOUT_SIGNALS, FORAGER_SIGNALS, NURSE_SIGNALS,
                GUARD_SIGNALS, BUILDER_SIGNALS,
            ]
            caste_counts = [0] * 5
            all_signals = list(signal_bus._signals) if hasattr(signal_bus, "_signals") else []
            for sig in all_signals:
                sig_type = getattr(sig, "signal_type", None)
                for idx, caste_set in enumerate(caste_groups):
                    if sig_type in caste_set:
                        caste_counts[idx] += 1
                        break
            if any(c > 0 for c in caste_counts):
                features.dominant_caste = int(np.argmax(caste_counts))
        except Exception:
            pass

    return features
