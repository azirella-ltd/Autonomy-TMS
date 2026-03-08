"""
Hive Signal Primitives for TRM Coordination.

Implements stigmergic (pheromone-based) coordination between the 11 TRM agents
within a single site hive. Signals decay over time like biological pheromones,
enabling emergent coordination without direct inter-TRM communication.

Architecture reference: TRM_HIVE_ARCHITECTURE.md Sections 2.1-2.3

Zero runtime impact when signal_bus is None — all consumers must guard with
`if self.signal_bus:` before reading/emitting.
"""

from __future__ import annotations

import collections
import math
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# HiveSignalType — 25 typed signals across 5 castes + tGNN
# ---------------------------------------------------------------------------

class HiveSignalType(str, Enum):
    """Typed signals emitted by TRM workers for consumption by others.

    Organized by biological caste (see TRM_HIVE_ARCHITECTURE.md Section 2.3):
      Scout (demand-side), Forager (supply-side), Nurse (health),
      Guard (integrity), Builder (execution), tGNN (inter-hive).
    """

    # -- Scout signals (demand-side) --
    DEMAND_SURGE = "demand_surge"
    DEMAND_DROP = "demand_drop"
    ATP_SHORTAGE = "atp_shortage"
    ATP_EXCESS = "atp_excess"
    ORDER_EXCEPTION = "order_exception"

    # -- Forager signals (supply-side) --
    PO_EXPEDITE = "po_expedite"
    PO_DEFERRED = "po_deferred"
    REBALANCE_INBOUND = "rebalance_inbound"
    REBALANCE_OUTBOUND = "rebalance_outbound"
    SUBCONTRACT_ROUTED = "subcontract_routed"

    # -- Nurse signals (health) --
    BUFFER_INCREASED = "buffer_increased"
    BUFFER_DECREASED = "buffer_decreased"
    # Backward-compatible aliases
    SS_INCREASED = "buffer_increased"
    SS_DECREASED = "buffer_decreased"
    FORECAST_ADJUSTED = "forecast_adjusted"

    # -- Guard signals (integrity) --
    QUALITY_REJECT = "quality_reject"
    QUALITY_HOLD = "quality_hold"
    MAINTENANCE_DEFERRED = "maintenance_deferred"
    MAINTENANCE_URGENT = "maintenance_urgent"

    # -- Builder signals (execution) --
    MO_RELEASED = "mo_released"
    MO_DELAYED = "mo_delayed"
    TO_RELEASED = "to_released"
    TO_DELAYED = "to_delayed"

    # -- tGNN signals (from inter-hive layer) --
    NETWORK_SHORTAGE = "network_shortage"
    NETWORK_SURPLUS = "network_surplus"
    PROPAGATION_ALERT = "propagation_alert"
    ALLOCATION_REFRESH = "allocation_refresh"


# Convenience sets for caste-based filtering
SCOUT_SIGNALS: FrozenSet[HiveSignalType] = frozenset({
    HiveSignalType.DEMAND_SURGE, HiveSignalType.DEMAND_DROP,
    HiveSignalType.ATP_SHORTAGE, HiveSignalType.ATP_EXCESS,
    HiveSignalType.ORDER_EXCEPTION,
})
FORAGER_SIGNALS: FrozenSet[HiveSignalType] = frozenset({
    HiveSignalType.PO_EXPEDITE, HiveSignalType.PO_DEFERRED,
    HiveSignalType.REBALANCE_INBOUND, HiveSignalType.REBALANCE_OUTBOUND,
    HiveSignalType.SUBCONTRACT_ROUTED,
})
NURSE_SIGNALS: FrozenSet[HiveSignalType] = frozenset({
    HiveSignalType.BUFFER_INCREASED, HiveSignalType.BUFFER_DECREASED,
    HiveSignalType.FORECAST_ADJUSTED,
})
GUARD_SIGNALS: FrozenSet[HiveSignalType] = frozenset({
    HiveSignalType.QUALITY_REJECT, HiveSignalType.QUALITY_HOLD,
    HiveSignalType.MAINTENANCE_DEFERRED, HiveSignalType.MAINTENANCE_URGENT,
})
BUILDER_SIGNALS: FrozenSet[HiveSignalType] = frozenset({
    HiveSignalType.MO_RELEASED, HiveSignalType.MO_DELAYED,
    HiveSignalType.TO_RELEASED, HiveSignalType.TO_DELAYED,
})
TGNN_SIGNALS: FrozenSet[HiveSignalType] = frozenset({
    HiveSignalType.NETWORK_SHORTAGE, HiveSignalType.NETWORK_SURPLUS,
    HiveSignalType.PROPAGATION_ALERT, HiveSignalType.ALLOCATION_REFRESH,
})


# ---------------------------------------------------------------------------
# HiveSignal — a single pheromone-like signal
# ---------------------------------------------------------------------------

# Decay math: strength(t) = urgency * exp(-0.693 * elapsed_min / half_life_min)
_LN2 = 0.693147180559945

# Signals weaker than this are filtered out by read()
DECAY_THRESHOLD = 0.05


@dataclass(frozen=False)
class HiveSignal:
    """A signal emitted by one TRM worker for consumption by others.

    Signals decay over time following exponential (pheromone) decay:
      current_strength = urgency * exp(-ln2 * elapsed / half_life)

    At half_life minutes, strength = 50% of original urgency.
    Signals with current_strength < DECAY_THRESHOLD (0.05) are filtered out.
    """

    # Identity
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_trm: str = ""              # e.g. "atp_executor", "po_creation"
    signal_type: HiveSignalType = HiveSignalType.ATP_SHORTAGE
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Payload
    urgency: float = 0.0              # 0.0 (routine) to 1.0 (critical)
    direction: str = "neutral"        # shortage | surplus | risk | relief
    magnitude: float = 0.0            # Normalized impact magnitude
    product_id: Optional[str] = None  # Product context (if applicable)

    # Decay
    half_life_minutes: float = 30.0   # Configurable per signal

    # Metadata
    payload: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0           # Source TRM confidence [0.0-1.0]

    @property
    def current_strength(self) -> float:
        """Pheromone-like decay: strength diminishes over time."""
        now = datetime.now(timezone.utc)
        ts = self.timestamp if self.timestamp.tzinfo else self.timestamp.replace(
            tzinfo=timezone.utc
        )
        elapsed = (now - ts).total_seconds() / 60.0
        if elapsed < 0:
            return self.urgency
        if self.half_life_minutes <= 0:
            return self.urgency
        return self.urgency * math.exp(-_LN2 * elapsed / self.half_life_minutes)

    @property
    def is_alive(self) -> bool:
        """True if signal strength exceeds the decay threshold."""
        return self.current_strength > DECAY_THRESHOLD

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON logging / DB storage."""
        return {
            "signal_id": self.signal_id,
            "source_trm": self.source_trm,
            "signal_type": self.signal_type.value,
            "timestamp": self.timestamp.isoformat(),
            "urgency": self.urgency,
            "direction": self.direction,
            "magnitude": self.magnitude,
            "product_id": self.product_id,
            "half_life_minutes": self.half_life_minutes,
            "confidence": self.confidence,
            "current_strength": round(self.current_strength, 4),
            "payload": self.payload,
        }


# ---------------------------------------------------------------------------
# UrgencyVector — 11-slot shared urgency state
# ---------------------------------------------------------------------------

class UrgencyVector:
    """Pheromone-like shared urgency state. All TRMs read, each TRM writes its slot.

    Thread-safe via a threading.Lock. Operations are O(1) for update/read,
    O(11) for snapshot (trivial).
    """

    TRM_INDICES: Dict[str, int] = {
        "atp_executor": 0,
        "order_tracking": 1,
        "po_creation": 2,
        "rebalancing": 3,
        "subcontracting": 4,
        "inventory_buffer": 5,
        "forecast_adj": 6,
        "quality": 7,
        "maintenance": 8,
        "mo_execution": 9,
        "to_execution": 10,
        # Canonical name aliases (used by decision_cycle.py and training)
        "forecast_adjustment": 6,
        "quality_disposition": 7,
        "maintenance_scheduling": 8,
    }

    # Valid direction values
    VALID_DIRECTIONS = frozenset({"neutral", "shortage", "surplus", "risk", "relief"})
    NUM_SLOTS = 11

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: List[float] = [0.0] * self.NUM_SLOTS
        self._directions: List[str] = ["neutral"] * self.NUM_SLOTS
        self._last_updated: List[Optional[datetime]] = [None] * self.NUM_SLOTS

    def update(
        self,
        trm_name: str,
        urgency: float,
        direction: str = "neutral",
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Update a single TRM's urgency slot. Only the owning TRM should call this."""
        idx = self.TRM_INDICES.get(trm_name)
        if idx is None:
            raise ValueError(f"Unknown TRM: {trm_name!r}. Valid: {list(self.TRM_INDICES)}")
        urgency = max(0.0, min(1.0, urgency))  # clamp [0, 1]
        if direction not in self.VALID_DIRECTIONS:
            raise ValueError(
                f"Invalid direction: {direction!r}. Valid: {self.VALID_DIRECTIONS}"
            )
        ts = timestamp or datetime.now(timezone.utc)
        with self._lock:
            self._values[idx] = urgency
            self._directions[idx] = direction
            self._last_updated[idx] = ts

    def read(self, trm_name: str) -> Tuple[float, str, Optional[datetime]]:
        """Read a single TRM's urgency (value, direction, last_updated)."""
        idx = self.TRM_INDICES.get(trm_name)
        if idx is None:
            raise ValueError(f"Unknown TRM: {trm_name!r}")
        with self._lock:
            return (self._values[idx], self._directions[idx], self._last_updated[idx])

    def snapshot(self) -> Dict[str, Any]:
        """Return a frozen copy of all 11 slots for logging/training."""
        with self._lock:
            return {
                "values": list(self._values),
                "directions": list(self._directions),
                "last_updated": [
                    t.isoformat() if t else None for t in self._last_updated
                ],
            }

    def values_array(self) -> List[float]:
        """Return a copy of the 11 urgency values (for tensor input)."""
        with self._lock:
            return list(self._values)

    def max_urgency(self) -> Tuple[str, float, str]:
        """Return (trm_name, urgency, direction) of the most urgent slot."""
        idx_to_name = {v: k for k, v in self.TRM_INDICES.items()}
        with self._lock:
            max_idx = 0
            max_val = self._values[0]
            for i in range(1, self.NUM_SLOTS):
                if self._values[i] > max_val:
                    max_val = self._values[i]
                    max_idx = i
            return (idx_to_name[max_idx], max_val, self._directions[max_idx])

    def adjust(self, trm_name: str, delta: float) -> None:
        """Apply a delta adjustment to a TRM's urgency, clamped to [0, 1].

        Used by Site tGNN (Layer 1.5) to modulate urgency before the
        decision cycle. Does not change the direction.

        Args:
            trm_name: TRM name (e.g. "atp_executor")
            delta: Adjustment value (typically [-0.3, +0.3])
        """
        idx = self.TRM_INDICES.get(trm_name)
        if idx is None:
            return  # Silently ignore unknown TRM names for robustness
        with self._lock:
            self._values[idx] = max(0.0, min(1.0, self._values[idx] + delta))
            self._last_updated[idx] = datetime.now(timezone.utc)

    def reset(self) -> None:
        """Reset all slots to neutral zero. Used at cycle boundaries."""
        with self._lock:
            self._values = [0.0] * self.NUM_SLOTS
            self._directions = ["neutral"] * self.NUM_SLOTS
            self._last_updated = [None] * self.NUM_SLOTS

    def to_dict(self) -> Dict[str, Any]:
        """Alias for snapshot() — used for JSON serialization."""
        return self.snapshot()


# ---------------------------------------------------------------------------
# HiveSignalBus — ring buffer of typed signals with pheromone decay
# ---------------------------------------------------------------------------

class HiveSignalBus:
    """Ring buffer of typed signals with pheromone decay.

    Fixed-capacity deque (default 200 signals). Oldest signals auto-evict
    on overflow. Read operations filter by time, type, decay threshold,
    and exclude self-signals.

    Thread-safe via a threading.Lock for emit/read.
    """

    def __init__(self, max_signals: int = 200) -> None:
        self._lock = threading.Lock()
        self._signals: collections.deque = collections.deque(maxlen=max_signals)
        self.urgency: UrgencyVector = UrgencyVector()
        self._emit_count: int = 0
        self._read_count: int = 0

    @property
    def max_signals(self) -> int:
        return self._signals.maxlen  # type: ignore[return-value]

    def __len__(self) -> int:
        with self._lock:
            return len(self._signals)

    def __bool__(self) -> bool:
        """Always truthy — use `is None` to check for absent bus."""
        return True

    def emit(self, signal: HiveSignal) -> None:
        """Emit a signal into the bus. O(1) append to deque."""
        with self._lock:
            self._signals.append(signal)
            self._emit_count += 1

    def read(
        self,
        consumer_trm: str,
        since: Optional[datetime] = None,
        types: Optional[Set[HiveSignalType]] = None,
        min_strength: float = DECAY_THRESHOLD,
    ) -> List[HiveSignal]:
        """TRM reads relevant signals before making a decision.

        Filters:
          - Temporal: signal.timestamp > since (if provided)
          - Decay: signal.current_strength > min_strength
          - Type: signal.signal_type in types (if provided)
          - Self-exclusion: signal.source_trm != consumer_trm
        """
        results = []
        with self._lock:
            self._read_count += 1
            for s in self._signals:
                if since and s.timestamp <= since:
                    continue
                if s.source_trm == consumer_trm:
                    continue
                if types and s.signal_type not in types:
                    continue
                if s.current_strength <= min_strength:
                    continue
                results.append(s)
        return results

    def read_latest_by_type(
        self,
        signal_type: HiveSignalType,
        consumer_trm: str = "",
    ) -> Optional[HiveSignal]:
        """Return the most recent alive signal of a given type, or None."""
        with self._lock:
            for s in reversed(self._signals):
                if s.signal_type != signal_type:
                    continue
                if s.source_trm == consumer_trm:
                    continue
                if s.current_strength > DECAY_THRESHOLD:
                    return s
        return None

    def active_signals(self) -> List[HiveSignal]:
        """Return all signals that are still alive (above decay threshold)."""
        with self._lock:
            return [s for s in self._signals if s.current_strength > DECAY_THRESHOLD]

    def signal_summary(self) -> Dict[str, int]:
        """Return count of active signals by type — useful for tensor features."""
        counts: Dict[str, int] = {}
        with self._lock:
            for s in self._signals:
                if s.current_strength > DECAY_THRESHOLD:
                    key = s.signal_type.value
                    counts[key] = counts.get(key, 0) + 1
        return counts

    def clear(self) -> None:
        """Clear all signals and reset urgency vector."""
        with self._lock:
            self._signals.clear()
        self.urgency.reset()

    def stats(self) -> Dict[str, Any]:
        """Return bus statistics for monitoring."""
        with self._lock:
            total = len(self._signals)
            alive = sum(1 for s in self._signals if s.current_strength > DECAY_THRESHOLD)
        return {
            "total_in_buffer": total,
            "alive": alive,
            "decayed": total - alive,
            "capacity": self.max_signals,
            "total_emitted": self._emit_count,
            "total_reads": self._read_count,
        }

    def to_context_dict(self) -> Dict[str, Any]:
        """Build signal context for decision logging and training data."""
        active = self.active_signals()
        return {
            "active_signal_count": len(active),
            "signals": [s.to_dict() for s in active],
            "urgency_vector": self.urgency.snapshot(),
            "summary": self.signal_summary(),
        }
