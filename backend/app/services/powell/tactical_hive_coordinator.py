"""
Tactical Hive Coordinator — 3-Parallel tGNN Coordination Layer.

Replaces the single ExecutionGNNInferenceService with three parallel
specialized tGNNs that mutually condition each other via lateral context
exchange (2-iteration lateral cycle).

Architecture:
    Demand Planning tGNN ──────────────────────────┐
    Supply Planning tGNN  ─── lateral context ─────┤ merged_per_site
    Inventory Optimization tGNN ───────────────────┘

Layer 2 of the 5-layer coordination stack:
    Layer 1:   Intra-Hive (HiveSignalBus) — <10ms, within site
    Layer 1.5: Site tGNN — hourly, intra-site cross-TRM coordination
    Layer 2:   Network tGNN Inter-Hive (this coordinator) — daily, cross-site
    Layer 3:   AAP Cross-Authority — seconds-minutes, ad hoc
    Layer 4:   S&OP Consensus Board — weekly, policy parameters

Lateral convergence check:
    Iteration 1: all three tGNNs run in parallel with no lateral context.
    If any signal significantly deviates from default (|signal| > threshold),
    Iteration 2 runs: each tGNN receives the other two's outputs as lateral
    context before re-computing.
    Maximum 2 iterations (time budget for daily cycle).

merged_per_site output is 100% backward-compatible with the format expected
by GNNOrchestrationService._merge_outputs() consumers.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.powell.demand_planning_tgnn_service import (
    DemandPlanningTGNNService, DemandPlanningTGNNOutput,
)
from app.services.powell.supply_planning_tgnn_service import (
    SupplyPlanningTGNNService, SupplyPlanningTGNNOutput,
)
from app.services.powell.inventory_optimization_tgnn_service import (
    InventoryOptimizationTGNNService, InventoryOptimizationTGNNOutput,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lateral context dataclass
# ---------------------------------------------------------------------------

@dataclass
class TacticalHiveLateralContext:
    """Cross-domain signals exchanged between the three tGNNs after iteration 1.

    Demand → Supply + Inventory: forecast and volatility signals.
    Supply → Demand + Inventory: exception probability, pipeline coverage.
    Inventory → Demand + Supply: stockout pressure, buffer adjustment.
    """

    # From Demand Planning tGNN → Supply + Inventory
    demand_forecast_by_site: Dict[str, List[float]] = field(default_factory=dict)
    demand_volatility_by_site: Dict[str, float] = field(default_factory=dict)
    bullwhip_by_site: Dict[str, float] = field(default_factory=dict)

    # From Supply Planning tGNN → Demand + Inventory
    supply_exception_prob_by_site: Dict[str, float] = field(default_factory=dict)
    order_recommendation_by_site: Dict[str, float] = field(default_factory=dict)
    pipeline_coverage_by_site: Dict[str, float] = field(default_factory=dict)

    # From Inventory Optimization tGNN → Demand + Supply
    stockout_probability_by_site: Dict[str, float] = field(default_factory=dict)
    buffer_adjustment_by_site: Dict[str, float] = field(default_factory=dict)
    rebalancing_urgency_by_site: Dict[str, float] = field(default_factory=dict)

    def to_demand_lateral_array(self, site_keys: List[str]) -> Optional[np.ndarray]:
        """Build [num_sites, 6] lateral context array for the Demand tGNN.

        Contains supply and inventory signals relevant to demand forecasting.
        """
        if not site_keys:
            return None
        arr = np.zeros((len(site_keys), 6), dtype=np.float32)
        for i, sk in enumerate(site_keys):
            arr[i, 0] = float(self.supply_exception_prob_by_site.get(sk, 0.0))
            arr[i, 1] = float(self.order_recommendation_by_site.get(sk, 0.0))
            arr[i, 2] = float(self.pipeline_coverage_by_site.get(sk, 0.0))
            arr[i, 3] = float(self.stockout_probability_by_site.get(sk, 0.0))
            arr[i, 4] = float(self.buffer_adjustment_by_site.get(sk, 0.0))
            arr[i, 5] = float(self.rebalancing_urgency_by_site.get(sk, 0.0))
        return arr

    def to_supply_lateral_array(self, site_keys: List[str]) -> Optional[np.ndarray]:
        """Build [num_sites, 6] lateral context array for the Supply tGNN.

        Contains demand and inventory signals relevant to supply planning.
        """
        if not site_keys:
            return None
        arr = np.zeros((len(site_keys), 6), dtype=np.float32)
        for i, sk in enumerate(site_keys):
            demand_fcst = self.demand_forecast_by_site.get(sk, [])
            arr[i, 0] = float(demand_fcst[0]) if demand_fcst else 0.0
            arr[i, 1] = float(self.demand_volatility_by_site.get(sk, 0.0))
            arr[i, 2] = float(self.bullwhip_by_site.get(sk, 1.0))
            arr[i, 3] = float(self.stockout_probability_by_site.get(sk, 0.0))
            arr[i, 4] = float(self.buffer_adjustment_by_site.get(sk, 0.0))
            arr[i, 5] = float(self.rebalancing_urgency_by_site.get(sk, 0.0))
        return arr

    def to_inventory_lateral_array(self, site_keys: List[str]) -> Optional[np.ndarray]:
        """Build [num_sites, 6] lateral context array for the Inventory tGNN.

        Contains demand and supply signals relevant to inventory optimization.
        """
        if not site_keys:
            return None
        arr = np.zeros((len(site_keys), 6), dtype=np.float32)
        for i, sk in enumerate(site_keys):
            demand_fcst = self.demand_forecast_by_site.get(sk, [])
            arr[i, 0] = float(demand_fcst[0]) if demand_fcst else 0.0
            arr[i, 1] = float(self.demand_volatility_by_site.get(sk, 0.0))
            arr[i, 2] = float(self.supply_exception_prob_by_site.get(sk, 0.0))
            arr[i, 3] = float(self.order_recommendation_by_site.get(sk, 0.0))
            arr[i, 4] = float(self.pipeline_coverage_by_site.get(sk, 0.0))
            arr[i, 5] = float(self.bullwhip_by_site.get(sk, 1.0))
        return arr


# ---------------------------------------------------------------------------
# TacticalHiveOutput
# ---------------------------------------------------------------------------

@dataclass
class TacticalHiveOutput:
    """Unified output from the 3-tGNN lateral cycle.

    merged_per_site is 100% backward-compatible with the dict format consumed
    by GNNOrchestrationService._merge_outputs() → DirectiveBroadcastService.
    """

    config_id: int
    site_keys: List[str]
    computed_at: datetime

    demand: DemandPlanningTGNNOutput
    supply: SupplyPlanningTGNNOutput
    inventory: InventoryOptimizationTGNNOutput

    # Merged backward-compatible output (replaces exec_output in orchestrator)
    merged_per_site: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Lateral cycle diagnostics
    lateral_iterations: int = 1
    lateral_convergence: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config_id": self.config_id,
            "site_keys": self.site_keys,
            "computed_at": self.computed_at.isoformat(),
            "lateral_iterations": self.lateral_iterations,
            "lateral_convergence": self.lateral_convergence,
            "demand": self.demand.to_dict(),
            "supply": self.supply.to_dict(),
            "inventory": self.inventory.to_dict(),
            "merged_per_site": self.merged_per_site,
        }


# ---------------------------------------------------------------------------
# TacticalHiveCoordinator
# ---------------------------------------------------------------------------

class TacticalHiveCoordinator:
    """Coordinates three parallel tGNNs with lateral context exchange.

    Each tGNN runs once (iteration 1) with only S&OP embeddings.
    If any signal is significantly non-default, a second iteration runs
    where each tGNN receives the other two's outputs as lateral context.
    Maximum 2 iterations to fit within the daily GNN cycle time budget.
    """

    # Threshold for deciding whether a second iteration is warranted.
    # Any |signal| above this in the first-pass outputs triggers iteration 2.
    LATERAL_CONVERGENCE_THRESHOLD: float = 0.05

    def __init__(self, db: AsyncSession, config_id: int):
        self.db = db
        self.config_id = config_id

    async def run_lateral_cycle(
        self,
        sop_embeddings: Optional[np.ndarray] = None,
        force_recompute: bool = False,
    ) -> TacticalHiveOutput:
        """Run the full 2-iteration lateral coordination cycle.

        Args:
            sop_embeddings: S&OP structural embeddings [num_sites, 64].
                If None, each service loads them independently.
            force_recompute: Pass-through to individual services.

        Returns:
            TacticalHiveOutput with merged_per_site dict ready for broadcast.
        """
        demand_svc = DemandPlanningTGNNService(self.db, self.config_id)
        supply_svc = SupplyPlanningTGNNService(self.db, self.config_id)
        inventory_svc = InventoryOptimizationTGNNService(self.db, self.config_id)

        # --- Iteration 1: parallel inference with no lateral context ---
        logger.info(
            f"TacticalHiveCoordinator: starting iteration 1 for config {self.config_id}"
        )
        demand_out, supply_out, inventory_out = await asyncio.gather(
            demand_svc.infer(sop_embeddings=sop_embeddings, force_recompute=force_recompute),
            supply_svc.infer(sop_embeddings=sop_embeddings, force_recompute=force_recompute),
            inventory_svc.infer(sop_embeddings=sop_embeddings, force_recompute=force_recompute),
        )

        lateral = self._build_lateral_context(demand_out, supply_out, inventory_out)

        site_keys = demand_out.site_keys or supply_out.site_keys or inventory_out.site_keys
        convergence: Dict[str, float] = {sk: 0.0 for sk in site_keys}
        lateral_iterations = 1

        # --- Decide whether iteration 2 is needed ---
        if self._needs_second_iteration(lateral, site_keys):
            logger.info(
                f"TacticalHiveCoordinator: lateral signals non-trivial, starting iteration 2"
            )
            # Build per-domain lateral arrays
            demand_lat = lateral.to_demand_lateral_array(site_keys)
            supply_lat = lateral.to_supply_lateral_array(site_keys)
            inventory_lat = lateral.to_inventory_lateral_array(site_keys)

            demand_out2, supply_out2, inventory_out2 = await asyncio.gather(
                demand_svc.infer(
                    sop_embeddings=sop_embeddings,
                    lateral_context=demand_lat,
                    force_recompute=True,
                ),
                supply_svc.infer(
                    sop_embeddings=sop_embeddings,
                    lateral_context=supply_lat,
                    force_recompute=True,
                ),
                inventory_svc.infer(
                    sop_embeddings=sop_embeddings,
                    lateral_context=inventory_lat,
                    force_recompute=True,
                ),
            )

            convergence = self._compute_convergence(
                demand_out, demand_out2,
                supply_out, supply_out2,
                inventory_out, inventory_out2,
                site_keys,
            )
            demand_out, supply_out, inventory_out = demand_out2, supply_out2, inventory_out2
            lateral_iterations = 2
            logger.info(
                f"TacticalHiveCoordinator: iteration 2 complete. "
                f"Avg convergence delta: {np.mean(list(convergence.values())):.4f}"
            )

        merged = self.merge_outputs(demand_out, supply_out, inventory_out)

        return TacticalHiveOutput(
            config_id=self.config_id,
            site_keys=site_keys,
            computed_at=datetime.utcnow(),
            demand=demand_out,
            supply=supply_out,
            inventory=inventory_out,
            merged_per_site=merged,
            lateral_iterations=lateral_iterations,
            lateral_convergence=convergence,
        )

    def _build_lateral_context(
        self,
        demand_out: DemandPlanningTGNNOutput,
        supply_out: SupplyPlanningTGNNOutput,
        inventory_out: InventoryOptimizationTGNNOutput,
    ) -> TacticalHiveLateralContext:
        """Extract cross-domain signals from iteration 1 outputs."""
        lateral = TacticalHiveLateralContext()

        # Demand → others
        lateral.demand_forecast_by_site = dict(demand_out.demand_forecast)
        lateral.demand_volatility_by_site = dict(demand_out.demand_volatility)
        lateral.bullwhip_by_site = dict(demand_out.bullwhip_coefficient)

        # Supply → others
        lateral.supply_exception_prob_by_site = dict(supply_out.supply_exception_probability)
        lateral.order_recommendation_by_site = dict(supply_out.order_recommendation)
        lateral.pipeline_coverage_by_site = dict(supply_out.pipeline_coverage_days)

        # Inventory → others
        lateral.stockout_probability_by_site = dict(inventory_out.stockout_probability)
        lateral.buffer_adjustment_by_site = dict(inventory_out.buffer_adjustment_signal)
        lateral.rebalancing_urgency_by_site = dict(inventory_out.rebalancing_urgency)

        return lateral

    def _needs_second_iteration(
        self, lateral: TacticalHiveLateralContext, site_keys: List[str]
    ) -> bool:
        """Return True if any cross-domain signal is significantly non-default.

        Checks scalar signals only (forecasts are always non-zero so not checked).
        Uses LATERAL_CONVERGENCE_THRESHOLD as the minimum signal magnitude.
        """
        threshold = self.LATERAL_CONVERGENCE_THRESHOLD

        for sk in site_keys:
            if abs(lateral.supply_exception_prob_by_site.get(sk, 0.0)) > threshold:
                return True
            if abs(lateral.stockout_probability_by_site.get(sk, 0.0)) > threshold:
                return True
            if abs(lateral.buffer_adjustment_by_site.get(sk, 0.0)) > threshold:
                return True
            if abs(lateral.rebalancing_urgency_by_site.get(sk, 0.0)) > threshold:
                return True
            if abs(lateral.demand_volatility_by_site.get(sk, 0.0)) > threshold:
                return True
            bullwhip = lateral.bullwhip_by_site.get(sk, 1.0)
            if abs(bullwhip - 1.0) > threshold:
                return True

        return False

    def _compute_convergence(
        self,
        d1: DemandPlanningTGNNOutput,
        d2: DemandPlanningTGNNOutput,
        s1: SupplyPlanningTGNNOutput,
        s2: SupplyPlanningTGNNOutput,
        i1: InventoryOptimizationTGNNOutput,
        i2: InventoryOptimizationTGNNOutput,
        site_keys: List[str],
    ) -> Dict[str, float]:
        """Compute per-site max absolute change between iterations 1 and 2."""
        convergence: Dict[str, float] = {}
        for sk in site_keys:
            deltas = []

            # Demand forecast delta (first period only)
            d1_f = d1.demand_forecast.get(sk, [0.0])
            d2_f = d2.demand_forecast.get(sk, [0.0])
            if d1_f and d2_f and d1_f[0] > 0:
                deltas.append(abs(d2_f[0] - d1_f[0]) / (abs(d1_f[0]) + 1e-6))

            # Supply exception prob delta
            s1_exc = s1.supply_exception_probability.get(sk, 0.0)
            s2_exc = s2.supply_exception_probability.get(sk, 0.0)
            deltas.append(abs(s2_exc - s1_exc))

            # Inventory buffer adjustment delta
            i1_buf = i1.buffer_adjustment_signal.get(sk, 0.0)
            i2_buf = i2.buffer_adjustment_signal.get(sk, 0.0)
            deltas.append(abs(i2_buf - i1_buf))

            convergence[sk] = float(max(deltas)) if deltas else 0.0

        return convergence

    def merge_outputs(
        self,
        demand_out: DemandPlanningTGNNOutput,
        supply_out: SupplyPlanningTGNNOutput,
        inventory_out: InventoryOptimizationTGNNOutput,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Merge three domain outputs into a unified per-site dict.

        The format is 100% backward-compatible with the dict expected by
        GNNOrchestrationService._merge_outputs() consumers and
        DirectiveBroadcastService.generate_directives_from_gnn().

        Required backward-compatible keys per site:
            demand_forecast: List[float]
            exception_probability: float   (maps from supply_exception_probability)
            order_recommendation: float
            allocation_priority: float     (new — passed through)
            confidence: float              (average of three domain confidences)
            domain_confidence: dict        (new — per-domain confidence breakdown)

        Additional keys provided for new consumers:
            demand_volatility, bullwhip_coefficient,
            lead_time_risk, pipeline_coverage_days,
            buffer_adjustment_signal, rebalancing_urgency,
            stockout_probability, inventory_health,
            rebalancing_candidates
        """
        merged: Dict[str, Dict[str, Any]] = {}

        all_site_keys = set(demand_out.site_keys) | set(supply_out.site_keys) | set(inventory_out.site_keys)

        for site_key in all_site_keys:
            d_conf = demand_out.confidence.get(site_key, 0.5)
            s_conf = supply_out.confidence.get(site_key, 0.5)
            i_conf = inventory_out.confidence.get(site_key, 0.5)
            avg_conf = (d_conf + s_conf + i_conf) / 3.0

            merged[site_key] = {
                # --- Backward-compatible keys ---
                "demand_forecast": demand_out.demand_forecast.get(site_key, []),
                # Map supply exception probability → exception_probability
                # (maintains compatibility with tGNNSiteDirective.exception_probability)
                "exception_probability": supply_out.supply_exception_probability.get(site_key, 0.0),
                "order_recommendation": supply_out.order_recommendation.get(site_key, 0.0),
                "allocation_priority": supply_out.allocation_priority.get(site_key, 0.5),
                "confidence": avg_conf,
                # --- Domain confidence breakdown (new) ---
                "domain_confidence": {
                    "demand": d_conf,
                    "supply": s_conf,
                    "inventory": i_conf,
                },
                # --- Extended demand signals ---
                "demand_volatility": demand_out.demand_volatility.get(site_key, 0.0),
                "bullwhip_coefficient": demand_out.bullwhip_coefficient.get(site_key, 1.0),
                # --- Extended supply signals ---
                "lead_time_risk": supply_out.lead_time_risk.get(site_key, 0.0),
                "pipeline_coverage_days": supply_out.pipeline_coverage_days.get(site_key, 0.0),
                # --- Extended inventory signals ---
                "buffer_adjustment_signal": inventory_out.buffer_adjustment_signal.get(site_key, 0.0),
                "rebalancing_urgency": inventory_out.rebalancing_urgency.get(site_key, 0.0),
                "stockout_probability": inventory_out.stockout_probability.get(site_key, 0.0),
                "inventory_health": inventory_out.inventory_health.get(site_key, 0.5),
                "rebalancing_candidates": inventory_out.rebalancing_candidates.get(site_key, []),
                # --- Reasoning (per-domain) ---
                "reasoning_demand": demand_out.reasoning.get(site_key, ""),
                "reasoning_supply": supply_out.reasoning.get(site_key, ""),
                "reasoning_inventory": inventory_out.reasoning.get(site_key, ""),
            }

        return merged
