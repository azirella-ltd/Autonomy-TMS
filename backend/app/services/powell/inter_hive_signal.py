"""
Inter-Hive Signal Primitives — Layer 2 of the Coordination Stack.

While HiveSignal (hive_signal.py) handles intra-hive coordination between
the 11 TRMs within a single site, InterHiveSignal handles the tGNN-to-hive
communication channel: signals that flow between sites via the tGNN layer.

Architecture reference: TRM_HIVE_ARCHITECTURE.md Section 6

Key differences from intra-hive signals:
- Longer half-lives (hours vs minutes) — network effects are slower
- Richer payload (source_site, propagation_depth, confidence)
- Unidirectional: tGNN → local hive (not TRM → TRM)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# InterHiveSignalType
# ---------------------------------------------------------------------------

class InterHiveSignalType(str, Enum):
    """Signal types that flow between hives via the tGNN.

    These map to tGNN output features that inform local TRM decisions.
    """

    # Network supply/demand imbalances
    NETWORK_SHORTAGE = "network_shortage"          # Upstream shortage propagating
    NETWORK_SURPLUS = "network_surplus"            # Upstream surplus available
    DEMAND_PROPAGATION = "demand_propagation"      # Demand wave propagating through network

    # Risk signals from S&OP GraphSAGE
    BOTTLENECK_RISK = "bottleneck_risk"            # Site is becoming a bottleneck
    CONCENTRATION_RISK = "concentration_risk"      # Sourcing concentration risk detected
    RESILIENCE_ALERT = "resilience_alert"          # Network resilience degradation

    # Allocation and priority signals
    ALLOCATION_REFRESH = "allocation_refresh"      # tGNN has recomputed allocations
    PRIORITY_SHIFT = "priority_shift"              # Priority rankings changed

    # Forecast/planning signals from S&OP layer
    FORECAST_REVISION = "forecast_revision"        # Network-level forecast revision
    POLICY_PARAMETER_UPDATE = "policy_param_update"  # S&OP policy parameters updated

    # Site tGNN (Layer 1.5) signals — intra-site cross-TRM coordination
    CROSS_TRM_BOTTLENECK = "cross_trm_bottleneck"  # Capacity starvation cascade detected
    CROSS_TRM_SYNERGY = "cross_trm_synergy"        # Positive feedback loop detected
    URGENCY_REBALANCE = "urgency_rebalance"        # Urgency redistribution recommended

    # Tactical lateral hive signals (Layer 2, TacticalHiveCoordinator)
    DEMAND_SIGNAL_TO_SUPPLY = "demand_signal_to_supply"       # Demand tGNN → Supply tGNN
    SUPPLY_SIGNAL_TO_INVENTORY = "supply_signal_to_inventory"  # Supply tGNN → Inventory tGNN
    INVENTORY_SIGNAL_TO_DEMAND = "inventory_signal_to_demand"  # Inventory tGNN → Demand tGNN
    TACTICAL_CONVERGENCE = "tactical_convergence"              # Lateral cycle converged


# ---------------------------------------------------------------------------
# InterHiveSignal
# ---------------------------------------------------------------------------

@dataclass
class InterHiveSignal:
    """A signal from the tGNN layer to a local site hive.

    Longer-lived than intra-hive signals (default 12-hour half-life).
    Carries source_site for provenance tracking.
    """

    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    signal_type: InterHiveSignalType = InterHiveSignalType.NETWORK_SHORTAGE
    source_site: str = ""                # Originating site key
    target_site: str = ""                # Destination site key
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Signal characteristics
    urgency: float = 0.5                 # 0.0–1.0
    direction: str = "neutral"           # shortage | surplus | risk | relief | neutral
    magnitude: float = 0.0              # Normalized impact
    confidence: float = 0.5             # tGNN confidence in this signal

    # Propagation tracking
    propagation_depth: int = 0          # Hops from original source
    half_life_hours: float = 12.0       # Decay in hours (slower than intra-hive)

    # Optional payload
    product_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type.value,
            "source_site": self.source_site,
            "target_site": self.target_site,
            "timestamp": self.timestamp.isoformat(),
            "urgency": round(self.urgency, 4),
            "direction": self.direction,
            "magnitude": round(self.magnitude, 4),
            "confidence": round(self.confidence, 4),
            "propagation_depth": self.propagation_depth,
            "half_life_hours": self.half_life_hours,
            "product_id": self.product_id,
        }


# ---------------------------------------------------------------------------
# tGNNSiteDirective
# ---------------------------------------------------------------------------

@dataclass
class tGNNSiteDirective:
    """Directive from the tGNN layer to a specific site hive.

    Contains both inter-hive signals and S&OP policy parameters that
    the SiteAgent uses to modulate local TRM behavior.

    Created by the execution tGNN or S&OP GraphSAGE after each inference.
    """

    directive_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    site_key: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Inter-hive signals to inject into local bus
    inter_hive_signals: List[InterHiveSignal] = field(default_factory=list)

    # S&OP policy parameters (from GraphSAGE)
    safety_stock_multiplier: float = 1.0     # Modulates SS bounds (0.5–2.0)
    criticality_score: float = 0.5           # Site criticality in network (0–1)
    bottleneck_risk: float = 0.0             # Bottleneck probability (0–1)
    resilience_score: float = 0.5            # Network resilience at this site (0–1)

    # Execution tGNN outputs
    demand_forecast: Optional[float] = None  # Network-adjusted demand forecast
    exception_probability: float = 0.0       # Expected exception rate (0–1)

    # Tactical Hive Coordinator extended outputs (Feb 2026)
    # These fields carry per-domain signals from TacticalHiveCoordinator.
    demand_volatility: Optional[float] = None           # Demand volatility estimate from Demand tGNN
    buffer_adjustment_signal: Optional[float] = None    # Buffer adj direction [-1,+1] from Inventory tGNN
    supply_exception_probability: Optional[float] = None  # Supply-domain exception prob from Supply tGNN

    # Priority allocations (from tGNN allocation layer)
    allocation_refresh: bool = False         # Whether allocations were updated
    allocation_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "directive_id": self.directive_id,
            "site_key": self.site_key,
            "timestamp": self.timestamp.isoformat(),
            "inter_hive_signals_count": len(self.inter_hive_signals),
            "safety_stock_multiplier": round(self.safety_stock_multiplier, 4),
            "criticality_score": round(self.criticality_score, 4),
            "bottleneck_risk": round(self.bottleneck_risk, 4),
            "resilience_score": round(self.resilience_score, 4),
            "demand_forecast": self.demand_forecast,
            "exception_probability": round(self.exception_probability, 4),
            "allocation_refresh": self.allocation_refresh,
            "allocation_version": self.allocation_version,
        }

    @classmethod
    def from_gnn_output(
        cls,
        site_key: str,
        gnn_embeddings: Dict[str, float],
        inter_hive_signals: Optional[List[InterHiveSignal]] = None,
    ) -> "tGNNSiteDirective":
        """Construct a directive from tGNN inference output.

        Args:
            site_key: Target site.
            gnn_embeddings: Dict of named GNN output values.
            inter_hive_signals: Optional list of inter-hive signals.

        Returns:
            Populated tGNNSiteDirective.
        """
        return cls(
            site_key=site_key,
            inter_hive_signals=inter_hive_signals or [],
            safety_stock_multiplier=gnn_embeddings.get("safety_stock_multiplier", 1.0),
            criticality_score=gnn_embeddings.get("criticality_score", 0.5),
            bottleneck_risk=gnn_embeddings.get("bottleneck_risk", 0.0),
            resilience_score=gnn_embeddings.get("resilience_score", 0.5),
            demand_forecast=gnn_embeddings.get("demand_forecast"),
            exception_probability=gnn_embeddings.get("exception_probability", 0.0),
        )
