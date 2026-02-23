"""
Hive Health Metrics for TRM Colony Monitoring.

Captures aggregate health of a site's TRM hive for logging, dashboards,
and tGNN feedback features. Computed at the REFLECT phase of each
decision cycle.

Architecture reference: TRM_HIVE_ARCHITECTURE.md Section 2.4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .hive_signal import HiveSignalBus, UrgencyVector


@dataclass
class HiveHealthMetrics:
    """Snapshot of hive health at a point in time.

    Aggregated from UrgencyVector and HiveSignalBus state.
    Used for:
      - Decision cycle REFLECT phase logging
      - tGNN feedback features (Section 16.6)
      - Dashboard visualization
      - Training data enrichment
    """

    # Identity
    site_key: str = ""
    cycle_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Urgency summary
    mean_urgency: float = 0.0         # Mean across 11 TRM slots
    max_urgency: float = 0.0          # Peak urgency
    max_urgency_trm: str = ""         # Which TRM has peak urgency
    max_urgency_direction: str = ""   # Direction of peak urgency
    urgency_values: List[float] = field(default_factory=lambda: [0.0] * 11)

    # Signal bus summary
    active_signal_count: int = 0      # Signals above decay threshold
    total_signals_in_buffer: int = 0  # Total signals in ring buffer
    signal_counts_by_type: Dict[str, int] = field(default_factory=dict)

    # Conflict indicators
    shortage_count: int = 0           # TRMs reporting shortage direction
    surplus_count: int = 0            # TRMs reporting surplus direction
    has_conflict: bool = False        # Opposing directions detected

    # Cycle stats
    decisions_this_cycle: int = 0
    signals_emitted_this_cycle: int = 0

    @classmethod
    def from_signal_bus(
        cls,
        bus: HiveSignalBus,
        site_key: str = "",
        cycle_id: Optional[str] = None,
        decisions_this_cycle: int = 0,
        signals_emitted_this_cycle: int = 0,
    ) -> "HiveHealthMetrics":
        """Build health metrics from the current state of a HiveSignalBus."""
        uv = bus.urgency
        values = uv.values_array()
        snapshot = uv.snapshot()
        directions = snapshot["directions"]

        max_trm, max_val, max_dir = uv.max_urgency()

        shortage = sum(1 for d in directions if d == "shortage")
        surplus = sum(1 for d in directions if d == "surplus")
        has_conflict = shortage > 0 and surplus > 0

        bus_stats = bus.stats()

        return cls(
            site_key=site_key,
            cycle_id=cycle_id,
            mean_urgency=sum(values) / len(values) if values else 0.0,
            max_urgency=max_val,
            max_urgency_trm=max_trm,
            max_urgency_direction=max_dir,
            urgency_values=values,
            active_signal_count=bus_stats["alive"],
            total_signals_in_buffer=bus_stats["total_in_buffer"],
            signal_counts_by_type=bus.signal_summary(),
            shortage_count=shortage,
            surplus_count=surplus,
            has_conflict=has_conflict,
            decisions_this_cycle=decisions_this_cycle,
            signals_emitted_this_cycle=signals_emitted_this_cycle,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON logging / DB storage."""
        return {
            "site_key": self.site_key,
            "cycle_id": self.cycle_id,
            "timestamp": self.timestamp.isoformat(),
            "mean_urgency": round(self.mean_urgency, 4),
            "max_urgency": round(self.max_urgency, 4),
            "max_urgency_trm": self.max_urgency_trm,
            "max_urgency_direction": self.max_urgency_direction,
            "urgency_values": [round(v, 4) for v in self.urgency_values],
            "active_signal_count": self.active_signal_count,
            "total_signals_in_buffer": self.total_signals_in_buffer,
            "signal_counts_by_type": self.signal_counts_by_type,
            "shortage_count": self.shortage_count,
            "surplus_count": self.surplus_count,
            "has_conflict": self.has_conflict,
            "decisions_this_cycle": self.decisions_this_cycle,
            "signals_emitted_this_cycle": self.signals_emitted_this_cycle,
        }

    @property
    def is_stressed(self) -> bool:
        """Heuristic: hive is stressed if mean urgency > 0.6 or conflict present."""
        return self.mean_urgency > 0.6 or self.has_conflict

    @property
    def is_quiet(self) -> bool:
        """Heuristic: hive is quiet if no active signals and max urgency < 0.1."""
        return self.active_signal_count == 0 and self.max_urgency < 0.1
