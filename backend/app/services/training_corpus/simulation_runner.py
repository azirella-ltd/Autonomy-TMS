"""
Simulation Runner — Executes the Digital Twin with all 12 TRMs active.

For each perturbation scenario, runs a full planning horizon simulation,
captures every TRM decision, and produces a list of Level 1 training samples.

This is the core of the unified training corpus generation pipeline. Instead
of generating synthetic training data independently per layer, all layers
derive their training data from TRM decisions made during these simulations.
"""

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

import numpy as np

from sqlalchemy.ext.asyncio import AsyncSession

from .erp_baseline_extractor import ERPBaselineSnapshot
from .perturbation_generator import PerturbationParams

logger = logging.getLogger(__name__)


class SimulationRunner:
    """Runs Digital Twin simulations for perturbation scenarios.

    The simulator is a lightweight weekly-period model that:
      1. Initializes inventory from the perturbed ERP baseline
      2. For each period: realizes demand, realizes lead times,
         runs TRM decision logic (or a fast heuristic proxy),
         records decisions with state/action/reward
      3. Returns the list of TRM decision samples

    For the corpus pipeline we use a FAST heuristic proxy instead of
    full TRM inference, because running real TRMs during training data
    generation would be circular (they haven't been trained yet). The
    heuristic reproduces the behavior the deterministic engines would
    produce given the state, which is what BC training needs.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_scenario(
        self,
        tenant_id: int,
        config_id: int,
        baseline: ERPBaselineSnapshot,
        perturbation: PerturbationParams,
        scenario_id: str,
        planning_horizon_weeks: int = 26,
    ) -> List[Dict[str, Any]]:
        """Run one perturbation scenario and return TRM decision samples.

        Args:
            tenant_id: Tenant scope
            config_id: Config scope
            baseline: ERP baseline snapshot
            perturbation: Perturbation parameters for this scenario
            scenario_id: UUID for this scenario
            planning_horizon_weeks: Number of weeks to simulate

        Returns:
            List of TRM decision samples (Layer 1 format)
        """
        samples: List[Dict[str, Any]] = []

        # Build initial state: per (product, site) inventory + policy
        state = self._initialize_state(baseline, perturbation)

        # Draw demand realizations for the full horizon (seeded)
        rng = np.random.default_rng(
            hash((config_id, perturbation.scenario_index)) & 0xFFFFFFFF
        )

        # Simulate each period
        for week in range(planning_horizon_weeks):
            period_samples = self._simulate_period(
                state=state,
                baseline=baseline,
                perturbation=perturbation,
                week=week,
                rng=rng,
                scenario_id=scenario_id,
            )
            samples.extend(period_samples)

        # Compute final per-decision rewards (retrospective: did it help?)
        samples = self._compute_rewards(samples, state, baseline)

        return samples

    def _initialize_state(
        self,
        baseline: ERPBaselineSnapshot,
        perturbation: PerturbationParams,
    ) -> Dict[str, Dict[str, Any]]:
        """Initialize per (product, site) state from baseline."""
        state = {}
        for inv in baseline.inventory:
            key = f"{inv.product_id}:{inv.site_id}"
            state[key] = {
                "product_id": inv.product_id,
                "site_id": inv.site_id,
                "on_hand": inv.on_hand,
                "in_transit": inv.in_transit,
                "allocated": inv.allocated,
                "safety_stock": inv.safety_stock,
                "reorder_point": inv.reorder_point,
                "max_stock": inv.max_stock,
                "pending_orders": [],  # [(arrival_week, qty), ...]
                "total_stockouts": 0,
                "total_ordering_cost": 0,
                "total_holding_cost": 0,
            }

        # Add products-without-inventory entries for forecast coverage
        for fc in baseline.forecast[:500]:  # cap for perf
            key = f"{fc.product_id}:{fc.site_id}"
            if key not in state:
                state[key] = {
                    "product_id": fc.product_id,
                    "site_id": fc.site_id,
                    "on_hand": 100.0,  # default starting inventory
                    "in_transit": 0,
                    "allocated": 0,
                    "safety_stock": 50.0,
                    "reorder_point": 75.0,
                    "max_stock": 300.0,
                    "pending_orders": [],
                    "total_stockouts": 0,
                    "total_ordering_cost": 0,
                    "total_holding_cost": 0,
                }

        return state

    def _simulate_period(
        self,
        state: Dict[str, Dict[str, Any]],
        baseline: ERPBaselineSnapshot,
        perturbation: PerturbationParams,
        week: int,
        rng: np.random.Generator,
        scenario_id: str,
    ) -> List[Dict[str, Any]]:
        """Simulate one period for all (product, site) pairs. Return TRM samples."""
        samples = []

        # Build forecast lookup by (product, site) at this week
        forecast_lookup: Dict[str, float] = {}
        for fc in baseline.forecast:
            key = f"{fc.product_id}:{fc.site_id}"
            if key not in forecast_lookup:
                forecast_lookup[key] = fc.quantity_p50

        for key, s in state.items():
            # Get base demand (from forecast or default)
            base_demand = forecast_lookup.get(key, 20.0)

            # Apply perturbation scale
            demand_scale = perturbation.demand_scale_by_product.get(s["product_id"], 1.0)
            mean_demand = base_demand * demand_scale

            # Realize demand with perturbed CV
            cv = 0.3 * perturbation.demand_cv_scale
            realized_demand = max(0, rng.normal(mean_demand, mean_demand * cv))

            # Arrive pending orders whose arrival_week <= week
            arriving = [q for (w, q) in s["pending_orders"] if w <= week]
            s["on_hand"] += sum(arriving)
            s["pending_orders"] = [(w, q) for (w, q) in s["pending_orders"] if w > week]

            # Fulfill demand
            fulfilled = min(s["on_hand"], realized_demand)
            stockout = realized_demand - fulfilled
            s["on_hand"] -= fulfilled
            s["total_stockouts"] += stockout

            # Holding cost
            s["total_holding_cost"] += s["on_hand"] * 0.002  # 0.2% weekly carry cost

            # ─── TRM Decisions (heuristic proxies) ───

            # 1. ATP Allocation decision (every period)
            atp_sample = self._atp_decision(s, realized_demand, fulfilled, week, scenario_id, perturbation)
            if atp_sample:
                samples.append(atp_sample)

            # 2. PO Creation decision (when inventory hits reorder point)
            if s["on_hand"] <= s["reorder_point"] and len(s["pending_orders"]) == 0:
                po_sample = self._po_decision(s, mean_demand, week, scenario_id, perturbation)
                samples.append(po_sample)

            # 3. Inventory Buffer decision (weekly review)
            if week % 4 == 0:
                buffer_sample = self._buffer_decision(s, mean_demand, cv, week, scenario_id)
                samples.append(buffer_sample)

            # 4. Forecast Baseline decision (weekly)
            if week % 4 == 0:
                fb_sample = self._forecast_baseline_decision(s, mean_demand, cv, week, scenario_id)
                samples.append(fb_sample)

        return samples

    def _atp_decision(self, s, demand, fulfilled, week, scenario_id, perturbation):
        """ATP allocation TRM decision sample."""
        fill_rate = fulfilled / demand if demand > 0 else 1.0
        return {
            "trm_type": "atp_allocation",
            "product_id": s["product_id"],
            "site_id": s["site_id"],
            "scenario_id": scenario_id,
            "period": week,
            "state_features": {
                "on_hand": s["on_hand"],
                "demand": demand,
                "safety_stock": s["safety_stock"],
                "reorder_point": s["reorder_point"],
                "in_transit": sum(q for _, q in s["pending_orders"]),
            },
            "action": {
                "allocated_qty": fulfilled,
                "fill_rate": fill_rate,
            },
            "reward_components": {
                "fill_rate": fill_rate,
                "stockout": demand - fulfilled,
                "service_level_achieved": 1.0 if fill_rate >= 0.95 else fill_rate,
            },
            "aggregate_reward": fill_rate,
        }

    def _po_decision(self, s, mean_demand, week, scenario_id, perturbation):
        """PO creation TRM decision sample. Also records lead time and order-up-to policy."""
        # Heuristic: order up to max_stock or 4 weeks of demand, whichever is higher
        target = max(s["max_stock"], mean_demand * 4)
        order_qty = max(0, target - s["on_hand"] - sum(q for _, q in s["pending_orders"]))

        # Lead time with perturbation
        lane_key = f"VENDOR->{s['site_id']}"
        lt_scale = perturbation.lead_time_scale_by_lane.get(lane_key, 1.0)
        lead_time_weeks = max(1, int(2 * lt_scale))

        # Schedule arrival
        if order_qty > 0:
            s["pending_orders"].append((week + lead_time_weeks, order_qty))
            s["total_ordering_cost"] += 100  # flat ordering cost

        # Days of supply at reorder
        dos = (s["on_hand"] / max(mean_demand, 1)) * 7

        return {
            "trm_type": "po_creation",
            "product_id": s["product_id"],
            "site_id": s["site_id"],
            "scenario_id": scenario_id,
            "period": week,
            "state_features": {
                "on_hand": s["on_hand"],
                "mean_demand": mean_demand,
                "reorder_point": s["reorder_point"],
                "days_of_supply": dos,
                "lead_time_weeks": lead_time_weeks,
            },
            "action": {
                "order_quantity": order_qty,
                "target_days_of_supply": (target / max(mean_demand, 1)) * 7,
            },
            "reward_components": {
                "ordering_cost": 100 if order_qty > 0 else 0,
            },
            "aggregate_reward": 0.7,  # tentative; will be refined in _compute_rewards
        }

    def _buffer_decision(self, s, mean_demand, cv, week, scenario_id):
        """Inventory buffer TRM decision sample. Records the safety stock multiplier."""
        # Heuristic: safety stock = z * sigma * sqrt(lead_time)
        z = 1.645  # 95% service level
        ss_target = z * (mean_demand * cv) * np.sqrt(2)
        current_ss = s["safety_stock"]
        multiplier = ss_target / max(current_ss, 1) if current_ss > 0 else 1.0

        return {
            "trm_type": "inventory_buffer",
            "product_id": s["product_id"],
            "site_id": s["site_id"],
            "scenario_id": scenario_id,
            "period": week,
            "state_features": {
                "current_ss": current_ss,
                "mean_demand": mean_demand,
                "demand_cv": cv,
                "on_hand": s["on_hand"],
                "stockout_count": s["total_stockouts"],
            },
            "action": {
                "target_ss": ss_target,
                "multiplier": multiplier,
                "service_level": 0.95,
            },
            "reward_components": {
                "holding_cost_delta": (ss_target - current_ss) * 0.1,
            },
            "aggregate_reward": 0.8 if abs(multiplier - 1.0) < 0.2 else 0.5,
        }

    def _forecast_baseline_decision(self, s, mean_demand, cv, week, scenario_id):
        """Forecast baseline TRM decision sample."""
        return {
            "trm_type": "forecast_baseline",
            "product_id": s["product_id"],
            "site_id": s["site_id"],
            "scenario_id": scenario_id,
            "period": week,
            "state_features": {
                "mean_demand": mean_demand,
                "demand_cv": cv,
                "observation_count": week + 1,
            },
            "action": {
                "forecast_p50": mean_demand,
                "forecast_p10": max(0, mean_demand * (1 - 1.28 * cv)),
                "forecast_p90": mean_demand * (1 + 1.28 * cv),
                "recommended_model": "lgbm" if cv < 0.5 else "lgbm_volatility",
            },
            "reward_components": {
                "mape_proxy": cv,  # lower cv = better forecast accuracy
            },
            "aggregate_reward": max(0, 1.0 - cv),
        }

    def _compute_rewards(
        self,
        samples: List[Dict[str, Any]],
        state: Dict[str, Dict[str, Any]],
        baseline: ERPBaselineSnapshot,
    ) -> List[Dict[str, Any]]:
        """Refine per-decision rewards using scenario-end outcomes.

        For PO and buffer decisions, the quality depends on whether
        the subsequent periods had stockouts or excess holding cost.
        """
        for sample in samples:
            key = f"{sample['product_id']}:{sample['site_id']}"
            if key not in state:
                continue
            s = state[key]
            total_demand_est = 20 * 26  # rough
            stockout_rate = s["total_stockouts"] / max(total_demand_est, 1)
            holding_ratio = s["total_holding_cost"] / max(total_demand_est * 10, 1)

            # Lower stockout rate + reasonable holding = higher reward
            scenario_score = max(0, 1.0 - stockout_rate - 0.5 * max(0, holding_ratio - 0.5))
            # Blend scenario score with per-decision aggregate
            sample["aggregate_reward"] = 0.5 * sample.get("aggregate_reward", 0.5) + 0.5 * scenario_score

        return samples
