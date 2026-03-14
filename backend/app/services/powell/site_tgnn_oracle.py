"""
Site tGNN Coordination Oracle

Generates labeled training data for the Site tGNN (Layer 1.5) via a deterministic
priority scheduler that resolves cross-TRM resource conflicts.

MOTIVATION (oracle training, analogous to chess LLM training):
  The Site tGNN learns to produce urgency adjustments that coordinate the 11 execution
  role agents within a site. But supervised learning requires labeled targets. Where
  do the labels come from?

  Answer: the Coordination Oracle. It runs all 11 deterministic engines simultaneously
  on a shared site state, detects which TRMs are competing for the same constrained
  resource (capacity, inventory, cash), applies deterministic priority rules to resolve
  each conflict, and records the resulting urgency weight vector as the training label.

  The Site tGNN is then trained (Phase 1 BC) to reproduce these urgency labels from
  raw node-level state features alone — exactly as Stockfish labels chess positions to
  train language models to play chess.

PRIORITY HIERARCHY (ISO 9001 / APICS SCOR):
  1. Customer commitments (ATP, Order Tracking) — contractual obligations
  2. Production safety (Quality, Maintenance) — prevent equipment damage / scrap
  3. Supply continuity (PO Creation, MO Execution) — keep production flowing
  4. Lateral flow (TO Execution, Rebalancing) — balance the network
  5. Planning refinement (Forecast Adjustment, Inventory Buffer) — optimise over time

CONFLICT TYPES:
  - Capacity conflict: MO + Subcontracting both claim manufacturing capacity
  - Inventory conflict: ATP + Rebalancing both claim on-hand stock
  - Cash conflict: PO + MO both require budget in same period
  - Maintenance conflict: Maintenance forces MO deferral (resource unavailable)

USAGE:
    oracle = MultiTRMCoordinationOracle(site_key="FOODDIST_DC", active_trms=frozenset(...))
    samples = oracle.generate_samples(num_scenarios=500)
    # samples: List[CoordinationSample]
    # → pass to SiteTGNNTrainer.train_phase1_bc(samples)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple

import numpy as np

from app.services.powell.engines.aatp_engine import AATPEngine, AATPConfig, Order, ATPAllocation, Priority
from app.services.powell.engines.rebalancing_engine import RebalancingEngine, RebalancingConfig, SiteState, LaneConstraints
from app.services.powell.engines.buffer_calculator import BufferCalculator, BufferConfig, BufferPolicy, PolicyType
from app.services.powell.engines.order_tracking_engine import OrderTrackingEngine, OrderTrackingConfig
from app.services.powell.engines.mo_execution_engine import MOExecutionEngine, MOConfig
from app.services.powell.engines.to_execution_engine import TOExecutionEngine, TOConfig
from app.services.powell.engines.quality_engine import QualityEngine, QualityConfig
from app.services.powell.engines.maintenance_engine import MaintenanceEngine, MaintenanceConfig
from app.services.powell.engines.forecast_adjustment_engine import ForecastAdjustmentEngine, ForecastAdjConfig
from app.services.powell.engines.subcontracting_engine import SubcontractingEngine, SubcontractingConfig
from app.services.powell.engines.mrp_engine import MRPEngine, MRPConfig

logger = logging.getLogger(__name__)

# Canonical TRM name → priority tier (lower = higher priority)
TRM_PRIORITY_TIER: Dict[str, int] = {
    "atp_executor":          1,  # Customer commitments
    "order_tracking":        1,  # Customer commitments
    "quality":               2,  # Production safety
    "maintenance":           2,  # Production safety
    "po_creation":           3,  # Supply continuity
    "mo_execution":          3,  # Supply continuity
    "subcontracting":        3,  # Supply continuity
    "to_execution":          4,  # Lateral flow
    "rebalancing":           4,  # Lateral flow
    "forecast_adj":          5,  # Planning refinement
    "inventory_buffer":      5,  # Planning refinement
}

# Resource types a TRM may claim
TRM_RESOURCE_CLAIMS: Dict[str, List[str]] = {
    "atp_executor":     ["on_hand_inventory", "committed_inventory"],
    "order_tracking":   [],                               # Read-only
    "quality":          ["on_hand_inventory", "wip"],
    "maintenance":      ["production_capacity"],
    "po_creation":      ["budget", "supplier_capacity"],
    "mo_execution":     ["production_capacity", "wip"],
    "subcontracting":   ["production_capacity", "budget"],
    "to_execution":     ["transit_capacity", "on_hand_inventory"],
    "rebalancing":      ["on_hand_inventory", "transit_capacity"],
    "forecast_adj":     [],                               # Information only
    "inventory_buffer": [],                               # Policy only
}

# Urgency adjustment bounds for conflict resolution
CONFLICT_PENALTY   = -0.25   # Loser's urgency is reduced by this delta
PRIORITY_BOOST     = +0.15   # Winner's urgency is boosted
MAINTENANCE_PREEMPT = -0.40  # MO urgency when maintenance claims capacity


@dataclass
class SharedSiteState:
    """Snapshot of all resources at a site at a single decision point."""
    site_key: str
    # Inventory resources
    on_hand_inventory: float          # Total on-hand across products (units)
    committed_inventory: float        # Already committed to open orders
    wip: float                        # Work-in-progress (units)
    # Capacity resources
    production_capacity: float        # Available hours this period
    production_capacity_used: float   # Already consumed by locked MOs
    transit_capacity: float           # Available transfer slots
    # Financial
    budget: float                     # Available procurement budget ($)
    supplier_capacity: float          # Available supplier volume (units)
    # Demand signal
    demand_forecast: float
    demand_variability_cv: float
    # Planning state
    service_level_actual: float       # Rolling 4-week
    service_level_target: float
    inventory_dos: float              # Days of supply
    target_dos: float
    # Flags
    has_quality_hold: bool = False
    has_maintenance_due: bool = False
    has_atp_shortfall: bool = False
    num_open_exceptions: int = 0


@dataclass
class TRMEngineOutput:
    """Raw engine output for one TRM before conflict resolution."""
    trm_name: str
    resource_claims: Dict[str, float]   # resource → claimed amount
    recommended_action: str
    raw_urgency: float                  # Engine-assessed urgency [0, 1]
    confidence: float


@dataclass
class ConflictRecord:
    """One detected resource conflict between two TRMs."""
    resource: str
    claimant_a: str
    claimant_b: str
    total_claimed: float
    available: float
    winner: str     # Higher-priority TRM
    loser: str


@dataclass
class CoordinationSample:
    """
    One oracle-generated training sample for the Site tGNN.

    node_features: [11, 18]  per-TRM state features (matches SiteTGNN input_dim)
    target_adjustments: [11, 3] oracle urgency adjustments
        [:, 0] urgency_adjustment   ∈ [-0.3, +0.3]
        [:, 1] confidence_modifier  ∈ [-0.2, +0.2]
        [:, 2] coordination_signal  ∈ [0, 1]  (1 = active conflict involvement)
    conflicts: list of conflicts detected in this scenario
    site_state: the SharedSiteState used
    """
    sample_id: str
    site_key: str
    node_features: np.ndarray         # [11, 18]
    target_adjustments: np.ndarray    # [11, 3]
    conflicts: List[ConflictRecord]
    site_state: SharedSiteState

    # Ordered TRM names matching node index order (must align with SiteTGNN.TRM_NAMES)
    TRM_ORDER: List[str] = field(default_factory=lambda: [
        "atp_executor", "order_tracking", "po_creation", "rebalancing",
        "subcontracting", "inventory_buffer", "forecast_adj", "quality",
        "maintenance", "mo_execution", "to_execution",
    ])


class MultiTRMCoordinationOracle:
    """
    Deterministic coordination oracle for Site tGNN training data generation.

    Generates CoordinationSample objects that pair a shared site state with the
    oracle-computed urgency adjustments. The Site tGNN is trained to reproduce
    these urgency adjustment vectors from raw features alone.
    """

    # TRM index order must match SiteTGNN.TRM_NAMES
    TRM_ORDER: List[str] = [
        "atp_executor", "order_tracking", "po_creation", "rebalancing",
        "subcontracting", "inventory_buffer", "forecast_adj", "quality",
        "maintenance", "mo_execution", "to_execution",
    ]

    def __init__(
        self,
        site_key: str,
        active_trms: Optional[FrozenSet[str]] = None,
        seed: Optional[int] = None,
    ) -> None:
        self.site_key = site_key
        self.active_trms = active_trms or frozenset(self.TRM_ORDER)
        self.rng = np.random.default_rng(seed)

        # Lightweight engine instances (stateless, deterministic)
        self._aatp_engine = AATPEngine(site_key, AATPConfig())
        self._rebalancing_engine = RebalancingEngine(site_key, RebalancingConfig())
        self._buffer_calc = BufferCalculator(site_key, BufferConfig())
        self._order_tracking_engine = OrderTrackingEngine(site_key, OrderTrackingConfig())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_samples(
        self,
        num_scenarios: int = 500,
        phases: Tuple[int, ...] = (1, 2, 3),
    ) -> List[CoordinationSample]:
        """
        Generate num_scenarios oracle-labeled training samples.

        phases controls scenario difficulty:
          1 = low variability (≤15% CV)
          2 = moderate variability (≤40% CV)
          3 = high variability / disruptions (≤75% CV)
        """
        samples: List[CoordinationSample] = []
        per_phase = num_scenarios // len(phases)

        for phase in phases:
            variance_pct = {1: 0.15, 2: 0.40, 3: 0.75}[phase]
            for _ in range(per_phase):
                state = self._sample_site_state(variance_pct)
                sample = self._solve(state)
                samples.append(sample)

        self.rng.shuffle(samples)  # type: ignore[arg-type]
        logger.info(
            "CoordinationOracle generated %d samples for site=%s",
            len(samples), self.site_key,
        )
        return samples

    # ------------------------------------------------------------------
    # Core solver
    # ------------------------------------------------------------------

    def _solve(self, state: SharedSiteState) -> CoordinationSample:
        """Run all engines, detect conflicts, resolve, return labeled sample."""
        # Step 1: Collect raw engine outputs
        raw_outputs = self._run_all_engines(state)

        # Step 2: Detect resource conflicts
        conflicts = self._detect_conflicts(raw_outputs, state)

        # Step 3: Compute urgency adjustments via priority resolution
        adjustments = self._resolve_conflicts(raw_outputs, conflicts)

        # Step 4: Package into training sample
        node_features = self._build_node_features(state, raw_outputs)
        target_adj = self._build_target_adjustments(adjustments, conflicts)

        return CoordinationSample(
            sample_id=str(uuid.uuid4()),
            site_key=self.site_key,
            node_features=node_features,
            target_adjustments=target_adj,
            conflicts=conflicts,
            site_state=state,
        )

    # ------------------------------------------------------------------
    # Engine runner (mock — real integration requires DB-backed state)
    # ------------------------------------------------------------------

    def _run_all_engines(self, state: SharedSiteState) -> Dict[str, TRMEngineOutput]:
        """
        Run each deterministic engine and collect its resource claims and urgency.

        In a full integration this would call the actual engine instances with
        real DB-backed state. Here we compute heuristic urgency scores from the
        shared site state — sufficient for oracle label generation.
        """
        outputs: Dict[str, TRMEngineOutput] = {}

        # --- ATP Executor ---
        atp_shortage = max(0.0, state.committed_inventory - state.on_hand_inventory)
        atp_urgency = min(1.0, atp_shortage / max(state.committed_inventory, 1e-6))
        if state.has_atp_shortfall:
            atp_urgency = min(1.0, atp_urgency + 0.3)
        outputs["atp_executor"] = TRMEngineOutput(
            trm_name="atp_executor",
            resource_claims={"on_hand_inventory": state.committed_inventory, "committed_inventory": state.committed_inventory},
            recommended_action="partial_promise" if atp_shortage > 0 else "full_promise",
            raw_urgency=atp_urgency,
            confidence=0.85 if state.demand_variability_cv < 0.3 else 0.65,
        )

        # --- Order Tracking ---
        ot_urgency = min(1.0, state.num_open_exceptions * 0.15)
        outputs["order_tracking"] = TRMEngineOutput(
            trm_name="order_tracking",
            resource_claims={},
            recommended_action="flag_exceptions" if state.num_open_exceptions > 0 else "monitor",
            raw_urgency=ot_urgency,
            confidence=0.90,
        )

        # --- PO Creation ---
        replenishment_gap = max(0.0, state.target_dos - state.inventory_dos)
        po_urgency = min(1.0, replenishment_gap / max(state.target_dos, 1e-6))
        po_claim = po_urgency * state.budget * 0.4
        outputs["po_creation"] = TRMEngineOutput(
            trm_name="po_creation",
            resource_claims={"budget": po_claim, "supplier_capacity": po_claim},
            recommended_action="create_po" if po_urgency > 0.3 else "hold",
            raw_urgency=po_urgency,
            confidence=0.80,
        )

        # --- Rebalancing ---
        imbalance = abs(state.inventory_dos - state.target_dos) / max(state.target_dos, 1e-6)
        rebal_urgency = min(1.0, imbalance * 0.6)
        rebal_claim = rebal_urgency * state.on_hand_inventory * 0.25
        outputs["rebalancing"] = TRMEngineOutput(
            trm_name="rebalancing",
            resource_claims={"on_hand_inventory": rebal_claim, "transit_capacity": rebal_claim},
            recommended_action="transfer" if rebal_urgency > 0.25 else "hold",
            raw_urgency=rebal_urgency,
            confidence=0.75,
        )

        # --- Subcontracting ---
        capacity_pressure = max(0.0, state.production_capacity_used / max(state.production_capacity, 1e-6) - 0.85)
        sub_urgency = min(1.0, capacity_pressure * 3.0)
        sub_cap_claim = sub_urgency * state.production_capacity * 0.3
        sub_budget_claim = sub_cap_claim * 50.0  # $50/unit subcontracting premium
        outputs["subcontracting"] = TRMEngineOutput(
            trm_name="subcontracting",
            resource_claims={"production_capacity": sub_cap_claim, "budget": sub_budget_claim},
            recommended_action="outsource" if sub_urgency > 0.4 else "internal",
            raw_urgency=sub_urgency,
            confidence=0.70,
        )

        # --- Inventory Buffer ---
        buffer_gap = max(0.0, state.service_level_target - state.service_level_actual)
        buf_urgency = min(1.0, buffer_gap * 5.0)
        outputs["inventory_buffer"] = TRMEngineOutput(
            trm_name="inventory_buffer",
            resource_claims={},
            recommended_action="increase_buffer" if buf_urgency > 0.3 else "maintain",
            raw_urgency=buf_urgency,
            confidence=0.75,
        )

        # --- Forecast Adjustment ---
        fcst_urgency = min(1.0, state.demand_variability_cv * 1.5)
        outputs["forecast_adj"] = TRMEngineOutput(
            trm_name="forecast_adj",
            resource_claims={},
            recommended_action="adjust_forecast" if fcst_urgency > 0.35 else "monitor",
            raw_urgency=fcst_urgency,
            confidence=0.70,
        )

        # --- Quality ---
        quality_urgency = 0.8 if state.has_quality_hold else 0.1
        quality_inv_claim = state.wip * 0.15 if state.has_quality_hold else 0.0
        outputs["quality"] = TRMEngineOutput(
            trm_name="quality",
            resource_claims={"on_hand_inventory": quality_inv_claim, "wip": quality_inv_claim},
            recommended_action="hold_release" if state.has_quality_hold else "pass",
            raw_urgency=quality_urgency,
            confidence=0.90,
        )

        # --- Maintenance ---
        maint_urgency = 0.75 if state.has_maintenance_due else 0.05
        maint_cap_claim = state.production_capacity * 0.20 if state.has_maintenance_due else 0.0
        outputs["maintenance"] = TRMEngineOutput(
            trm_name="maintenance",
            resource_claims={"production_capacity": maint_cap_claim},
            recommended_action="schedule_maintenance" if state.has_maintenance_due else "monitor",
            raw_urgency=maint_urgency,
            confidence=0.85,
        )

        # --- MO Execution ---
        mo_need = max(0.0, state.target_dos - state.inventory_dos) * state.demand_forecast
        mo_urgency = min(1.0, mo_need / max(state.production_capacity, 1e-6))
        mo_cap_claim = mo_urgency * state.production_capacity * 0.6
        outputs["mo_execution"] = TRMEngineOutput(
            trm_name="mo_execution",
            resource_claims={"production_capacity": mo_cap_claim, "wip": mo_cap_claim * 0.5},
            recommended_action="release_mo" if mo_urgency > 0.3 else "defer",
            raw_urgency=mo_urgency,
            confidence=0.80,
        )

        # --- TO Execution ---
        to_urgency = min(1.0, (rebal_urgency + atp_urgency) * 0.4)
        to_transit_claim = to_urgency * state.transit_capacity * 0.5
        to_inv_claim = to_transit_claim
        outputs["to_execution"] = TRMEngineOutput(
            trm_name="to_execution",
            resource_claims={"transit_capacity": to_transit_claim, "on_hand_inventory": to_inv_claim},
            recommended_action="expedite" if to_urgency > 0.5 else "standard",
            raw_urgency=to_urgency,
            confidence=0.75,
        )

        # Filter to active TRMs
        return {name: out for name, out in outputs.items() if name in self.active_trms}

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def _detect_conflicts(
        self,
        outputs: Dict[str, TRMEngineOutput],
        state: SharedSiteState,
    ) -> List[ConflictRecord]:
        """Detect TRM pairs that over-claim a shared resource."""
        resource_pool: Dict[str, float] = {
            "on_hand_inventory":    state.on_hand_inventory,
            "committed_inventory":  state.committed_inventory,
            "wip":                  state.wip,
            "production_capacity":  state.production_capacity * (1.0 - state.production_capacity_used / max(state.production_capacity, 1e-6)),
            "transit_capacity":     state.transit_capacity,
            "budget":               state.budget,
            "supplier_capacity":    state.supplier_capacity,
        }

        # Aggregate claims per resource
        resource_claims: Dict[str, Dict[str, float]] = {}  # resource → {trm: claim}
        for trm_name, output in outputs.items():
            for resource, amount in output.resource_claims.items():
                if amount <= 0:
                    continue
                resource_claims.setdefault(resource, {})[trm_name] = amount

        conflicts: List[ConflictRecord] = []
        for resource, claims_map in resource_claims.items():
            available = resource_pool.get(resource, 0.0)
            total_claimed = sum(claims_map.values())
            if total_claimed <= available * 1.05:   # 5% slack before flagging
                continue

            # All pairs of claimants that are over the limit → conflict
            claimants = list(claims_map.keys())
            for i in range(len(claimants)):
                for j in range(i + 1, len(claimants)):
                    a, b = claimants[i], claimants[j]
                    tier_a = TRM_PRIORITY_TIER.get(a, 5)
                    tier_b = TRM_PRIORITY_TIER.get(b, 5)
                    winner = a if tier_a <= tier_b else b
                    loser = b if winner == a else a
                    conflicts.append(ConflictRecord(
                        resource=resource,
                        claimant_a=a,
                        claimant_b=b,
                        total_claimed=total_claimed,
                        available=available,
                        winner=winner,
                        loser=loser,
                    ))
        return conflicts

    # ------------------------------------------------------------------
    # Conflict resolution → urgency adjustment labels
    # ------------------------------------------------------------------

    def _resolve_conflicts(
        self,
        outputs: Dict[str, TRMEngineOutput],
        conflicts: List[ConflictRecord],
    ) -> Dict[str, float]:
        """
        Apply priority rules to produce urgency delta per TRM.
        Returns dict: trm_name → urgency_adjustment ∈ [-0.3, +0.3]
        """
        adjustments: Dict[str, float] = {name: 0.0 for name in outputs}

        for conflict in conflicts:
            winner = conflict.winner
            loser = conflict.loser

            # Special case: maintenance preempts MO (equipment safety)
            if conflict.resource == "production_capacity":
                if "maintenance" in (winner, loser) and "mo_execution" in (winner, loser):
                    adjustments["maintenance"] = max(adjustments["maintenance"], PRIORITY_BOOST)
                    adjustments["mo_execution"] = min(adjustments["mo_execution"], MAINTENANCE_PREEMPT)
                    continue

            # General case: winner gets small boost, loser gets penalty
            if winner in adjustments:
                adjustments[winner] = np.clip(adjustments[winner] + PRIORITY_BOOST, -0.3, 0.3)
            if loser in adjustments:
                adjustments[loser] = np.clip(adjustments[loser] + CONFLICT_PENALTY, -0.3, 0.3)

        return adjustments

    # ------------------------------------------------------------------
    # Feature construction
    # ------------------------------------------------------------------

    def _build_node_features(
        self,
        state: SharedSiteState,
        outputs: Dict[str, TRMEngineOutput],
    ) -> np.ndarray:
        """
        Build [11, 18] node feature matrix (matches SiteTGNN input_dim=18).

        Features per TRM node (18 total):
         0: raw_urgency (engine-assessed)
         1: confidence
         2: has_resource_claim (binary)
         3: priority_tier (normalised 0-1)
         4: on_hand_inventory (normalised)
         5: committed_inventory (normalised)
         6: wip (normalised)
         7: production_capacity_available (normalised)
         8: transit_capacity (normalised)
         9: budget (normalised)
        10: demand_forecast (normalised)
        11: demand_variability_cv
        12: service_level_actual
        13: service_level_target
        14: inventory_dos (normalised)
        15: target_dos (normalised)
        16: has_quality_hold (binary)
        17: has_maintenance_due (binary)
        """
        inv_norm  = max(state.on_hand_inventory, 1e-6)
        cap_norm  = max(state.production_capacity, 1e-6)
        budget_norm = max(state.budget, 1e-6)
        fcst_norm = max(state.demand_forecast, 1e-6)
        dos_norm  = max(state.target_dos, 1e-6)

        features = np.zeros((11, 18), dtype=np.float32)
        for idx, trm_name in enumerate(self.TRM_ORDER):
            output = outputs.get(trm_name)
            raw_urgency = output.raw_urgency if output else 0.0
            confidence  = output.confidence  if output else 0.0
            has_claim   = 1.0 if (output and output.resource_claims) else 0.0
            tier        = TRM_PRIORITY_TIER.get(trm_name, 5) / 5.0

            features[idx] = [
                raw_urgency,
                confidence,
                has_claim,
                tier,
                min(state.on_hand_inventory / inv_norm, 1.0),
                min(state.committed_inventory / inv_norm, 1.0),
                min(state.wip / inv_norm, 1.0),
                min(max(0.0, cap_norm - state.production_capacity_used) / cap_norm, 1.0),
                min(state.transit_capacity / max(state.transit_capacity, 1e-6), 1.0),
                min(state.budget / budget_norm, 1.0),
                min(state.demand_forecast / fcst_norm, 1.0),
                state.demand_variability_cv,
                state.service_level_actual,
                state.service_level_target,
                min(state.inventory_dos / dos_norm, 3.0) / 3.0,
                1.0,  # target_dos normalised to self = 1
                float(state.has_quality_hold),
                float(state.has_maintenance_due),
            ]
        return features

    def _build_target_adjustments(
        self,
        adjustments: Dict[str, float],
        conflicts: List[ConflictRecord],
    ) -> np.ndarray:
        """
        Build [11, 3] target adjustment matrix.
          [:, 0] urgency_adjustment   ∈ [-0.3, +0.3]
          [:, 1] confidence_modifier  ∈ [-0.2, +0.2]  (proxy: conflict involvement)
          [:, 2] coordination_signal  ∈ [0, 1]         (1 = in a conflict)
        """
        conflict_trms = set()
        for c in conflicts:
            conflict_trms.add(c.claimant_a)
            conflict_trms.add(c.claimant_b)

        targets = np.zeros((11, 3), dtype=np.float32)
        for idx, trm_name in enumerate(self.TRM_ORDER):
            urg_adj = adjustments.get(trm_name, 0.0)
            in_conflict = trm_name in conflict_trms
            conf_mod = -0.1 * abs(urg_adj) / 0.3 if in_conflict else 0.0
            coord_sig = 1.0 if in_conflict else 0.0

            targets[idx] = [
                np.clip(urg_adj, -0.3, 0.3),
                np.clip(conf_mod, -0.2, 0.2),
                coord_sig,
            ]
        return targets

    # ------------------------------------------------------------------
    # Scenario sampling
    # ------------------------------------------------------------------

    def _sample_site_state(self, variance_pct: float) -> SharedSiteState:
        """
        Sample a random (but physically plausible) site state.

        All stochastic variables use shared distributions from
        training_distributions.D to ensure cross-tier consistency.

        variance_pct controls scenario difficulty:
          0.15 = low variability (Phase 1)
          0.40 = moderate variability (Phase 2)
          0.75 = high variability / disruption scenarios (Phase 3)
        """
        from app.services.powell.training_distributions import D
        rng = self.rng

        state = D.sample_site_state_dict(
            rng=rng,
            site_key=self.site_key,
            variance_pct=variance_pct,
        )
        return SharedSiteState(**state)
