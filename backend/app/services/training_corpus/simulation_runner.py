"""
Simulation Runner — Executes the Digital Twin with all 12 TRMs active.

For each perturbation scenario, runs a full planning horizon simulation,
captures every in-scope TRM decision via the deterministic teacher layer,
and produces a list of Level 1 training samples.

Failure policy (see docs/internal/architecture/UNIFIED_TRAINING_CORPUS.md §6b):

  Case A — Out of topology
    Silently skip TRMs that are not valid for the site's master_type.
    Resolved before any engine call via topology.valid_trms_for_site_type().

  Case B — Transient infrastructure (DB drop, pool exhaustion, deadlock)
    Catch sqlalchemy OperationalError / DBAPIError. Checkpoint the scenario
    cursor, raise TransientCorpusError. Caller pauses the provisioning step
    with a tenant-admin-visible message, retries with backoff, resumes from
    the last completed scenario.

  Case C — Missing master data for an in-scope TRM
    Teacher raises MissingMasterDataError. Propagated up unchanged. The
    provisioning step must mark itself as failed with the site + TRM +
    missing-data details (SOC II: no swallowing).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
from sqlalchemy import text as sql_text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from . import teacher
from .erp_baseline_extractor import ERPBaselineSnapshot
from .exceptions import MissingMasterDataError, TransientCorpusError
from .perturbation_generator import PerturbationParams
from .topology import is_in_scope, valid_trms_for_site_type

logger = logging.getLogger(__name__)


class SimulationRunner:
    """Runs Digital Twin simulations for perturbation scenarios.

    The simulator is a weekly-period model. For each period at each site:
      1. Realize demand and lead times from the perturbed baseline
      2. Advance inventory state
      3. For each TRM that is in-scope for the site's master_type, call the
         deterministic teacher (real engine where integrated, heuristic
         bridge otherwise) and record a Layer-1 sample
      4. Compute scenario-end rewards

    Teacher failures are classified into Case A/B/C per the policy above.
    """

    def __init__(self, db: AsyncSession, focus_trms: Optional[frozenset] = None):
        """
        Args:
            db: async session
            focus_trms: if set, only emit samples for these TRM types. Used by
                the two-stream corpus build to run simulation as targeted
                augmentation for thin historical TRMs, rather than generating
                samples across all 12. None = emit all in-topology TRMs.
        """
        self.db = db
        self._site_type: Dict[str, str] = {}
        self._site_trms: Dict[str, frozenset] = {}
        self._focus_trms = focus_trms

    # ────────────────────────────────────────────────────────────────
    # Topology resolution (Case A)
    # ────────────────────────────────────────────────────────────────
    def _resolve_topology(self, baseline: ERPBaselineSnapshot) -> None:
        """Build the site_id -> master_type -> valid TRM set map.

        Out-of-topology TRMs are silently skipped (Case A).
        """
        self._site_type.clear()
        self._site_trms.clear()
        for site in baseline.sites:
            self._site_type[site.site_id] = site.master_type
            self._site_trms[site.site_id] = valid_trms_for_site_type(site.master_type)
        skipped_count = sum(1 for s in self._site_trms.values() if not s)
        if skipped_count:
            logger.info(
                "Topology resolution: %d external (vendor/customer) sites "
                "will be skipped entirely.",
                skipped_count,
            )

    def _trm_valid(self, site_id: str, trm_type: str) -> bool:
        if self._focus_trms is not None and trm_type not in self._focus_trms:
            return False
        return trm_type in self._site_trms.get(site_id, frozenset())

    # ────────────────────────────────────────────────────────────────
    # Checkpoint (Case B)
    # ────────────────────────────────────────────────────────────────
    async def _save_checkpoint(
        self,
        corpus_id: int,
        tenant_id: int,
        config_id: int,
        last_scenario_completed: int,
        total_scenarios: int,
        trm_decisions_written: int,
        status: str,
        paused_reason: Optional[str] = None,
        failed_reason: Optional[str] = None,
    ) -> None:
        """Upsert the corpus build checkpoint row."""
        await self.db.execute(
            sql_text("""
                INSERT INTO training_corpus_checkpoint (
                    corpus_id, tenant_id, config_id,
                    last_scenario_completed, total_scenarios,
                    trm_decisions_written, status,
                    paused_reason, failed_reason, created_at, updated_at
                ) VALUES (
                    :corpus_id, :tenant_id, :config_id,
                    :last, :total, :written, :status,
                    :paused, :failed, NOW(), NOW()
                )
                ON CONFLICT (corpus_id) DO UPDATE SET
                    last_scenario_completed = EXCLUDED.last_scenario_completed,
                    total_scenarios = EXCLUDED.total_scenarios,
                    trm_decisions_written = EXCLUDED.trm_decisions_written,
                    status = EXCLUDED.status,
                    paused_reason = EXCLUDED.paused_reason,
                    failed_reason = EXCLUDED.failed_reason,
                    updated_at = NOW()
            """),
            {
                "corpus_id": corpus_id,
                "tenant_id": tenant_id,
                "config_id": config_id,
                "last": last_scenario_completed,
                "total": total_scenarios,
                "written": trm_decisions_written,
                "status": status,
                "paused": paused_reason,
                "failed": failed_reason,
            },
        )
        await self.db.commit()

    async def _load_checkpoint(self, corpus_id: int) -> Optional[Dict[str, Any]]:
        result = await self.db.execute(
            sql_text("""
                SELECT last_scenario_completed, trm_decisions_written, status
                FROM training_corpus_checkpoint
                WHERE corpus_id = :cid
            """),
            {"cid": corpus_id},
        )
        row = result.fetchone()
        if row is None:
            return None
        return {
            "last_scenario_completed": row.last_scenario_completed,
            "trm_decisions_written": row.trm_decisions_written,
            "status": row.status,
        }

    # ────────────────────────────────────────────────────────────────
    # Multi-scenario driver with checkpoint/resume
    # ────────────────────────────────────────────────────────────────
    async def run_all_scenarios(
        self,
        corpus_id: int,
        tenant_id: int,
        config_id: int,
        baseline: ERPBaselineSnapshot,
        scenarios: List[PerturbationParams],
        planning_horizon_weeks: int = 26,
        sample_sink=None,
    ) -> int:
        """Run every scenario with checkpoint/resume and failure classification.

        Samples are streamed to `sample_sink(samples: List[dict]) -> awaitable`
        per-scenario so large runs do not accumulate millions of rows in memory.
        The sink is responsible for persisting / flushing. If no sink is given,
        samples are discarded after the scenario completes (simulation-only mode).

        Returns the total number of samples produced. On transient failure,
        raises TransientCorpusError (Case B). On missing master data,
        raises MissingMasterDataError (Case C).
        """
        self._resolve_topology(baseline)

        # Resume from checkpoint if present
        ckpt = await self._load_checkpoint(corpus_id)
        start_idx = 0
        written = 0
        if ckpt and ckpt["status"] in ("running", "paused"):
            start_idx = ckpt["last_scenario_completed"] + 1
            written = ckpt["trm_decisions_written"]
            logger.info(
                "Resuming corpus build corpus_id=%d from scenario %d/%d "
                "(%d samples already written)",
                corpus_id, start_idx, len(scenarios), written,
            )

        last_completed = start_idx - 1

        try:
            for idx in range(start_idx, len(scenarios)):
                perturbation = scenarios[idx]
                scenario_id = f"scenario_{idx:04d}"
                samples = self._run_single_scenario(
                    baseline=baseline,
                    perturbation=perturbation,
                    scenario_id=scenario_id,
                    planning_horizon_weeks=planning_horizon_weeks,
                )
                written += len(samples)
                last_completed = idx

                # Stream samples to the sink immediately, then drop the
                # reference so memory doesn't grow unbounded. A 500×26 run
                # at Food Dist scale produces ~4M samples — accumulating
                # in-memory OOMs the container.
                if sample_sink is not None:
                    await sample_sink(samples)
                del samples

                # Periodic checkpoint (every 10 scenarios)
                if (idx + 1) % 10 == 0 or idx == len(scenarios) - 1:
                    await self._save_checkpoint(
                        corpus_id=corpus_id,
                        tenant_id=tenant_id,
                        config_id=config_id,
                        last_scenario_completed=last_completed,
                        total_scenarios=len(scenarios),
                        trm_decisions_written=written,
                        status="running",
                    )

            # Finalize
            await self._save_checkpoint(
                corpus_id=corpus_id,
                tenant_id=tenant_id,
                config_id=config_id,
                last_scenario_completed=last_completed,
                total_scenarios=len(scenarios),
                trm_decisions_written=written,
                status="completed",
            )
            return written

        except (OperationalError, DBAPIError) as e:
            # Case B — transient infra failure
            logger.error(
                "Transient DB failure during corpus build corpus_id=%d "
                "at scenario %d: %s",
                corpus_id, last_completed + 1, e,
            )
            try:
                await self._save_checkpoint(
                    corpus_id=corpus_id,
                    tenant_id=tenant_id,
                    config_id=config_id,
                    last_scenario_completed=last_completed,
                    total_scenarios=len(scenarios),
                    trm_decisions_written=written,
                    status="paused",
                    paused_reason=f"Transient DB failure: {type(e).__name__}",
                )
            except Exception:
                logger.exception(
                    "Failed to write pause checkpoint; corpus will restart from %d",
                    start_idx,
                )
            raise TransientCorpusError(e, last_completed) from e

        except MissingMasterDataError as e:
            # Case C — in-scope TRM lacks required master data. Hard fail.
            logger.error(
                "Corpus build failed — missing master data: site=%s trm=%s missing=%s",
                e.site_id, e.trm_type, e.missing,
            )
            try:
                await self._save_checkpoint(
                    corpus_id=corpus_id,
                    tenant_id=tenant_id,
                    config_id=config_id,
                    last_scenario_completed=last_completed,
                    total_scenarios=len(scenarios),
                    trm_decisions_written=written,
                    status="failed",
                    failed_reason=str(e),
                )
            except Exception:
                logger.exception("Failed to write fail checkpoint")
            raise

    # ────────────────────────────────────────────────────────────────
    # Single-scenario simulation
    # ────────────────────────────────────────────────────────────────
    def _run_single_scenario(
        self,
        baseline: ERPBaselineSnapshot,
        perturbation: PerturbationParams,
        scenario_id: str,
        planning_horizon_weeks: int,
    ) -> List[Dict[str, Any]]:
        samples: List[Dict[str, Any]] = []
        state = self._initialize_state(baseline, perturbation)
        rng = np.random.default_rng(
            hash((scenario_id, perturbation.scenario_index)) & 0xFFFFFFFF
        )
        for week in range(planning_horizon_weeks):
            samples.extend(
                self._simulate_period(
                    state=state,
                    baseline=baseline,
                    perturbation=perturbation,
                    week=week,
                    rng=rng,
                    scenario_id=scenario_id,
                )
            )
        return self._compute_rewards(samples, state)

    # ────────────────────────────────────────────────────────────────
    # State init
    # ────────────────────────────────────────────────────────────────
    def _initialize_state(
        self,
        baseline: ERPBaselineSnapshot,
        perturbation: PerturbationParams,
    ) -> Dict[str, Dict[str, Any]]:
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
                "pending_orders": [],
                "total_stockouts": 0,
                "total_holding_cost": 0,
            }
        # No forecast-padding: we only simulate (product, site) pairs that
        # exist in real inventory. Forecast-only synthetic keys inflate the
        # corpus and do not correspond to operationally meaningful decisions.
        return state

    # ────────────────────────────────────────────────────────────────
    # Period simulation with topology-aware teacher calls
    # ────────────────────────────────────────────────────────────────
    def _simulate_period(
        self,
        state: Dict[str, Dict[str, Any]],
        baseline: ERPBaselineSnapshot,
        perturbation: PerturbationParams,
        week: int,
        rng: np.random.Generator,
        scenario_id: str,
    ) -> List[Dict[str, Any]]:
        samples: List[Dict[str, Any]] = []

        forecast_lookup: Dict[str, float] = {}
        for fc in baseline.forecast:
            key = f"{fc.product_id}:{fc.site_id}"
            if key not in forecast_lookup:
                forecast_lookup[key] = fc.quantity_p50

        for key, s in state.items():
            site_id = s["site_id"]
            product_id = s["product_id"]
            # Case A — skip entire site if no TRMs apply (external nodes)
            if not self._site_trms.get(site_id):
                continue

            base_demand = forecast_lookup.get(key, 20.0)
            demand_scale = perturbation.demand_scale_by_product.get(product_id, 1.0)
            mean_demand = base_demand * demand_scale
            cv = 0.3 * perturbation.demand_cv_scale
            realized_demand = max(0, rng.normal(mean_demand, mean_demand * cv))

            # Inventory dynamics
            arriving = [q for (w, q) in s["pending_orders"] if w <= week]
            s["on_hand"] += sum(arriving)
            s["pending_orders"] = [(w, q) for (w, q) in s["pending_orders"] if w > week]
            fulfilled = min(s["on_hand"], realized_demand)
            stockout = realized_demand - fulfilled
            s["on_hand"] -= fulfilled
            s["total_stockouts"] += stockout
            s["total_holding_cost"] += s["on_hand"] * 0.002

            # ─── Teacher-driven TRM decisions (topology-gated) ───

            # ATP emission policy: decision-worthy (constrained/partial fill)
            # OR monthly periodic tick. This brings the dominant per-period
            # emitter from ~1 sample/key/week to ~1 sample/key/month on
            # well-stocked keys, with full density on interesting cases.
            atp_fill_rate = (fulfilled / realized_demand) if realized_demand > 0 else 1.0
            atp_constrained = atp_fill_rate < 1.0 or stockout > 0
            if self._trm_valid(site_id, "atp_allocation") and (atp_constrained or week % 4 == 0):
                teach = teacher.teach_atp_allocation(
                    product_id, site_id, s["on_hand"] + fulfilled,
                    realized_demand, s["safety_stock"],
                )
                samples.append(self._build_sample(
                    "atp_allocation", s, week, scenario_id, teach,
                    state_features={
                        "on_hand": s["on_hand"] + fulfilled,
                        "demand": realized_demand,
                        "safety_stock": s["safety_stock"],
                        "in_transit": sum(q for _, q in s["pending_orders"]),
                    },
                ))

            if (
                self._trm_valid(site_id, "po_creation")
                and s["on_hand"] <= s["reorder_point"]
                and not s["pending_orders"]
            ):
                lane_key = f"VENDOR->{site_id}"
                lt_scale = perturbation.lead_time_scale_by_lane.get(lane_key, 1.0)
                lead_time_weeks = max(1, int(2 * lt_scale))
                teach = teacher.teach_po_creation(
                    product_id, site_id, s["on_hand"],
                    sum(q for _, q in s["pending_orders"]),
                    mean_demand, s["reorder_point"], s["max_stock"],
                    lead_time_weeks,
                )
                order_qty = teach["action"]["order_quantity"]
                if order_qty > 0:
                    s["pending_orders"].append((week + lead_time_weeks, order_qty))
                samples.append(self._build_sample(
                    "po_creation", s, week, scenario_id, teach,
                    state_features={
                        "on_hand": s["on_hand"],
                        "mean_demand": mean_demand,
                        "reorder_point": s["reorder_point"],
                        "lead_time_weeks": lead_time_weeks,
                    },
                ))

            if self._trm_valid(site_id, "inventory_buffer") and week % 4 == 0:
                teach = teacher.teach_inventory_buffer(
                    product_id, site_id,
                    mean_daily_demand=mean_demand / 7.0,
                    demand_cv=cv,
                    lead_time_days=14.0,
                    current_ss=s["safety_stock"],
                )
                samples.append(self._build_sample(
                    "inventory_buffer", s, week, scenario_id, teach,
                    state_features={
                        "current_ss": s["safety_stock"],
                        "mean_demand": mean_demand,
                        "demand_cv": cv,
                        "on_hand": s["on_hand"],
                    },
                ))

            if self._trm_valid(site_id, "forecast_baseline") and week % 4 == 0 and week >= 4:
                teach = teacher.teach_forecast_baseline(
                    product_id, mean_demand, cv, observation_count=week + 1,
                )
                samples.append(self._build_sample(
                    "forecast_baseline", s, week, scenario_id, teach,
                    state_features={
                        "mean_demand": mean_demand,
                        "demand_cv": cv,
                        "observation_count": week + 1,
                    },
                ))

            if self._trm_valid(site_id, "forecast_adjustment") and (
                week % 4 == 0 or abs(realized_demand - mean_demand) > mean_demand * 0.3
            ):
                teach = teacher.teach_forecast_adjustment(
                    mean_demand, realized_demand, cv,
                )
                samples.append(self._build_sample(
                    "forecast_adjustment", s, week, scenario_id, teach,
                    state_features={
                        "baseline_forecast": mean_demand,
                        "recent_actual": realized_demand,
                        "demand_cv": cv,
                    },
                ))

            if self._trm_valid(site_id, "rebalancing") and (
                s["on_hand"] > s["max_stock"] * 1.1 or stockout > 0
            ):
                teach = teacher.teach_rebalancing(
                    s["on_hand"], s["max_stock"], stockout, mean_demand,
                )
                samples.append(self._build_sample(
                    "rebalancing", s, week, scenario_id, teach,
                    state_features={
                        "on_hand": s["on_hand"],
                        "max_stock": s["max_stock"],
                        "stockout": stockout,
                        "mean_demand": mean_demand,
                    },
                ))

            if self._trm_valid(site_id, "to_execution") and stockout > 0 and not s["pending_orders"]:
                teach = teacher.teach_to_execution(stockout, week)
                samples.append(self._build_sample(
                    "to_execution", s, week, scenario_id, teach,
                    state_features={"stockout": stockout, "on_hand": s["on_hand"]},
                ))

            if (
                self._trm_valid(site_id, "mo_execution")
                and s["on_hand"] <= s["reorder_point"] * 0.5
                and week % 2 == 0
            ):
                teach = teacher.teach_mo_execution(s["on_hand"], s["max_stock"], week)
                samples.append(self._build_sample(
                    "mo_execution", s, week, scenario_id, teach,
                    state_features={
                        "on_hand": s["on_hand"],
                        "max_stock": s["max_stock"],
                        "mean_demand": mean_demand,
                    },
                ))

            if self._trm_valid(site_id, "quality_disposition") and arriving and rng.random() < 0.02:
                teach = teacher.teach_quality_disposition(sum(arriving))
                samples.append(self._build_sample(
                    "quality_disposition", s, week, scenario_id, teach,
                    state_features={"incoming_qty": sum(arriving)},
                ))

            if self._trm_valid(site_id, "maintenance_scheduling") and week % 4 == 0:
                teach = teacher.teach_maintenance(week)
                samples.append(self._build_sample(
                    "maintenance_scheduling", s, week, scenario_id, teach,
                    state_features={"period": week},
                ))

            if self._trm_valid(site_id, "subcontracting") and mean_demand > 200 and week % 4 == 0:
                teach = teacher.teach_subcontracting(mean_demand)
                samples.append(self._build_sample(
                    "subcontracting", s, week, scenario_id, teach,
                    state_features={"mean_demand": mean_demand, "on_hand": s["on_hand"]},
                ))

            # Order-tracking emission policy: only when status is "delayed"
            # (exception fired) OR monthly periodic tick per open order. This
            # eliminates the dense per-period "on_track" acknowledgements that
            # carry no training signal.
            if self._trm_valid(site_id, "order_tracking"):
                for (arrival_week, qty) in s["pending_orders"][:2]:
                    teach = teacher.teach_order_tracking(arrival_week, week, qty)
                    is_delayed = teach["action"]["alert"]
                    if is_delayed or week % 4 == 0:
                        samples.append(self._build_sample(
                            "order_tracking", s, week, scenario_id, teach,
                            state_features={
                                "qty": qty,
                                "planned_arrival": arrival_week,
                                "weeks_remaining": max(0, arrival_week - week),
                            },
                        ))

        return samples

    # ────────────────────────────────────────────────────────────────
    # Sample assembly
    # ────────────────────────────────────────────────────────────────
    def _build_sample(
        self,
        trm_type: str,
        s: Dict[str, Any],
        week: int,
        scenario_id: str,
        teach: Dict[str, Any],
        state_features: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "trm_type": trm_type,
            "product_id": s["product_id"],
            "site_id": s["site_id"],
            "scenario_id": scenario_id,
            "period": week,
            "state_features": state_features,
            "action": teach["action"],
            "teacher_source": teach["teacher_source"],
            "engine": teach["engine"],
            "reward_components": {},
            "aggregate_reward": 0.5,  # refined in _compute_rewards
        }

    # ────────────────────────────────────────────────────────────────
    # Retrospective reward assignment
    # ────────────────────────────────────────────────────────────────
    def _compute_rewards(
        self,
        samples: List[Dict[str, Any]],
        state: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        for sample in samples:
            key = f"{sample['product_id']}:{sample['site_id']}"
            if key not in state:
                continue
            s = state[key]
            total_demand_est = 20 * 26
            stockout_rate = s["total_stockouts"] / max(total_demand_est, 1)
            holding_ratio = s["total_holding_cost"] / max(total_demand_est * 10, 1)
            scenario_score = max(
                0, 1.0 - stockout_rate - 0.5 * max(0, holding_ratio - 0.5)
            )
            sample["aggregate_reward"] = (
                0.5 * sample.get("aggregate_reward", 0.5) + 0.5 * scenario_score
            )
        return samples

    # ────────────────────────────────────────────────────────────────
    # Backward-compatible single-scenario entry point
    # ────────────────────────────────────────────────────────────────
    async def run_scenario(
        self,
        tenant_id: int,
        config_id: int,
        baseline: ERPBaselineSnapshot,
        perturbation: PerturbationParams,
        scenario_id: str,
        planning_horizon_weeks: int = 26,
    ) -> List[Dict[str, Any]]:
        """Legacy single-scenario entry point.

        Prefer run_all_scenarios for new code (handles checkpointing and
        failure classification). This method remains for existing callers.
        """
        if not self._site_type:
            self._resolve_topology(baseline)
        return self._run_single_scenario(
            baseline=baseline,
            perturbation=perturbation,
            scenario_id=scenario_id,
            planning_horizon_weeks=planning_horizon_weeks,
        )
