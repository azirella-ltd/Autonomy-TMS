"""
Decision Cycle — 6-phase ordered execution for TRM hive coordination.

Each decision cycle runs through 6 phases so that earlier phases'
signals are available to later phases within the same cycle.

Phase ordering (from TRM_HIVE_ARCHITECTURE.md Section 2.2):
  1. SENSE    — Demand-side scouts observe (ATP, OrderTracking)
  2. ASSESS   — Health/risk assessment (InventoryBuffer, ForecastAdj, Quality)
  3. ACQUIRE  — Supply-side foragers act (PO, Subcontracting)
  4. PROTECT  — Guards secure constraints (Maintenance)
  5. BUILD    — Builders execute (MO, TO)
  6. REFLECT  — Rebalancing + conflict detection

This ordering ensures:
- Scouts see demand before foragers place orders
- Quality/maintenance signals reach builders before they release MOs
- Rebalancing has visibility into all prior decisions

Zero runtime impact when signal_bus is None — SiteAgent can still call
individual TRM methods directly (backward compatible).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DecisionCyclePhase — ordered phases
# ---------------------------------------------------------------------------

class DecisionCyclePhase(IntEnum):
    """Six-phase decision cycle for TRM hive coordination.

    IntEnum so phases can be compared and sorted numerically.
    """
    SENSE = 1     # Demand-side scouts observe
    ASSESS = 2    # Health/risk assessment
    ACQUIRE = 3   # Supply-side foragers act
    PROTECT = 4   # Guards secure constraints
    BUILD = 5     # Builders execute
    REFLECT = 6   # Rebalancing + conflict detection


# Canonical TRM names → decision cycle phase (used for PHASE_TRM_MAP)
_CANONICAL_PHASE_MAP: Dict[str, DecisionCyclePhase] = {
    # SENSE — demand-side scouts
    "atp_executor": DecisionCyclePhase.SENSE,
    "order_tracking": DecisionCyclePhase.SENSE,

    # ASSESS — health and risk
    "inventory_buffer": DecisionCyclePhase.ASSESS,
    "forecast_adjustment": DecisionCyclePhase.ASSESS,
    "quality_disposition": DecisionCyclePhase.ASSESS,

    # ACQUIRE — supply-side foragers
    "po_creation": DecisionCyclePhase.ACQUIRE,
    "subcontracting": DecisionCyclePhase.ACQUIRE,

    # PROTECT — guards
    "maintenance_scheduling": DecisionCyclePhase.PROTECT,

    # BUILD — builders
    "mo_execution": DecisionCyclePhase.BUILD,
    "to_execution": DecisionCyclePhase.BUILD,

    # REFLECT — rebalancing
    "rebalancing": DecisionCyclePhase.REFLECT,
}

# Full lookup map includes canonical + short aliases
TRM_PHASE_MAP: Dict[str, DecisionCyclePhase] = {
    **_CANONICAL_PHASE_MAP,
    # Short aliases for backward compatibility
    "forecast_adj": DecisionCyclePhase.ASSESS,
    "quality": DecisionCyclePhase.ASSESS,
    "maintenance": DecisionCyclePhase.PROTECT,
}

# Reverse: phase → list of CANONICAL TRM names (no duplicates)
PHASE_TRM_MAP: Dict[DecisionCyclePhase, List[str]] = {}
for _trm, _phase in sorted(_CANONICAL_PHASE_MAP.items()):
    PHASE_TRM_MAP.setdefault(_phase, []).append(_trm)


def get_phase_for_trm(trm_name: str) -> DecisionCyclePhase:
    """Return the decision cycle phase for a given TRM name.

    Raises ValueError if the TRM name is not recognized.
    """
    phase = TRM_PHASE_MAP.get(trm_name)
    if phase is None:
        raise ValueError(
            f"Unknown TRM: {trm_name!r}. Valid: {list(TRM_PHASE_MAP)}"
        )
    return phase


def get_trms_for_phase(phase: DecisionCyclePhase) -> List[str]:
    """Return TRM names that execute in a given phase."""
    return list(PHASE_TRM_MAP.get(phase, []))


# ---------------------------------------------------------------------------
# PhaseResult / CycleResult — execution result tracking
# ---------------------------------------------------------------------------

@dataclass
class PhaseResult:
    """Result of executing a single phase within a decision cycle."""
    phase: DecisionCyclePhase
    trms_executed: List[str] = field(default_factory=list)
    signals_emitted: int = 0
    duration_ms: float = 0.0
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase.name,
            "phase_number": int(self.phase),
            "trms_executed": self.trms_executed,
            "signals_emitted": self.signals_emitted,
            "duration_ms": round(self.duration_ms, 2),
            "errors": self.errors,
            "success": self.success,
        }


@dataclass
class CycleResult:
    """Result of a complete 6-phase decision cycle."""
    cycle_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    phases: List[PhaseResult] = field(default_factory=list)
    total_signals_emitted: int = 0
    total_duration_ms: float = 0.0
    conflicts_detected: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return all(p.success for p in self.phases)

    @property
    def phases_completed(self) -> int:
        return len(self.phases)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "phases": [p.to_dict() for p in self.phases],
            "phases_completed": self.phases_completed,
            "total_signals_emitted": self.total_signals_emitted,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "conflicts_detected": self.conflicts_detected,
            "success": self.success,
        }


# ---------------------------------------------------------------------------
# Conflict detection (REFLECT phase utility)
# ---------------------------------------------------------------------------

def detect_conflicts(
    urgency_snapshot: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Detect conflicting urgency directions across TRM slots.

    A conflict exists when two TRMs have opposing directions
    (shortage vs surplus, or risk vs relief) with both above
    urgency threshold 0.3.

    Args:
        urgency_snapshot: Output from UrgencyVector.snapshot()

    Returns:
        List of conflict dicts with involved TRMs and details.
    """
    from .hive_signal import UrgencyVector

    values = urgency_snapshot.get("values", [])
    directions = urgency_snapshot.get("directions", [])

    idx_to_name = {v: k for k, v in UrgencyVector.TRM_INDICES.items()}
    conflicts = []

    # Opposition pairs
    opposing = {
        ("shortage", "surplus"),
        ("surplus", "shortage"),
        ("risk", "relief"),
        ("relief", "risk"),
    }

    threshold = 0.3
    active = []
    for i in range(min(len(values), len(directions))):
        if values[i] >= threshold and directions[i] != "neutral":
            active.append((i, idx_to_name.get(i, f"slot_{i}"), values[i], directions[i]))

    for i, (idx_a, name_a, val_a, dir_a) in enumerate(active):
        for idx_b, name_b, val_b, dir_b in active[i + 1:]:
            if (dir_a, dir_b) in opposing:
                conflicts.append({
                    "trm_a": name_a,
                    "direction_a": dir_a,
                    "urgency_a": round(val_a, 3),
                    "trm_b": name_b,
                    "direction_b": dir_b,
                    "urgency_b": round(val_b, 3),
                    "type": f"{dir_a}_vs_{dir_b}",
                })

    return conflicts
