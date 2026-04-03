"""
GNN Orchestration Service — Layer 2 Multi-Site Coordination

Ties together:
    1. S&OP GraphSAGE inference (weekly/monthly, cached)
    2. Execution Temporal GNN inference (daily)
    3. Directive broadcast to all SiteAgents

This is the orchestration layer that converts GNN model outputs into
tGNNSiteDirectives and injects them into the intra-hive signal buses.

Usage:
    orchestrator = GNNOrchestrationService(db, config_id)
    result = await orchestrator.run_full_cycle()
    # result["directives_generated"] = 5
    # result["broadcast_success"] = 5
    # result["feedback"] = {site_key: HiveFeedbackFeatures}

Scheduled: Daily via APScheduler (registered in relearning_jobs.py).
Also callable via POST /site-agent/gnn/run-cycle API.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class GNNOrchestrationService:
    """
    Orchestrates the full GNN inference → directive broadcast cycle.

    Layer 2 (Network tGNN) of the 5-layer coordination stack:
        Layer 1:   Intra-Hive (HiveSignalBus) — <10ms, within site
        Layer 1.5: Site tGNN — hourly, intra-site cross-TRM coordination
        Layer 2:   Network tGNN Inter-Hive (this service) — daily, cross-site
        Layer 3:   AAP Cross-Authority — seconds-minutes, ad hoc
        Layer 4:   S&OP Consensus Board — weekly, policy parameters
    """

    def __init__(self, db: AsyncSession, config_id: int, tenant_id: int = 0):
        self.db = db
        self.config_id = config_id
        self.tenant_id = tenant_id

    async def run_full_cycle(
        self,
        force_recompute: bool = False,
    ) -> Dict[str, Any]:
        """
        Run complete GNN → Directive → Broadcast → Feedback cycle.

        Steps:
            1. Run S&OP GraphSAGE analysis (may use cache)
            2. Run Execution tGNN inference with S&OP embeddings
            3. Merge outputs into unified gnn_outputs dict
            4. Generate tGNNSiteDirectives via DirectiveBroadcastService
            5. Broadcast directives to all registered SiteAgents
            6. Collect feedback from hives

        Returns:
            Dict with cycle results and timing.
        """
        cycle_start = datetime.utcnow()
        result = {
            "config_id": self.config_id,
            "cycle_start": cycle_start.isoformat(),
            "sop_analysis": None,
            "execution_output": None,
            "directives_generated": 0,
            "broadcast_success": 0,
            "broadcast_failed": 0,
            "feedback": {},
            "errors": [],
        }

        # --- Step 1: S&OP GraphSAGE ---
        sop_analysis = None
        sop_embeddings = None
        try:
            from app.services.powell.sop_inference_service import SOPInferenceService

            sop_svc = SOPInferenceService(self.db, self.config_id, tenant_id=self.tenant_id)
            sop_analysis = await sop_svc.analyze_network(
                force_recompute=force_recompute,
            )
            sop_embeddings = await sop_svc.get_embeddings_tensor()
            result["sop_analysis"] = {
                "num_sites": sop_analysis.num_sites,
                "computed_at": (
                    sop_analysis.computed_at.isoformat()
                    if sop_analysis.computed_at else None
                ),
            }
            logger.info(
                f"S&OP analysis: {sop_analysis.num_sites} sites, "
                f"network risk = {sop_analysis.network_risk}"
            )
        except Exception as e:
            logger.warning(f"S&OP inference failed (continuing with defaults): {e}")
            result["errors"].append(f"sop_inference: {e}")

        # --- Step 2: Tactical Hive Coordinator (3-parallel tGNNs) ---
        # DEPRECATED import kept for backward compatibility — use TacticalHiveCoordinator below.
        # from app.services.powell.execution_gnn_inference_service import ExecutionGNNInferenceService
        tactical_output = None
        exec_output = None  # kept for _persist_directive_reviews compatibility
        try:
            from app.services.powell.tactical_hive_coordinator import TacticalHiveCoordinator

            coordinator = TacticalHiveCoordinator(self.db, self.config_id, tenant_id=self.tenant_id)
            tactical_output = await coordinator.run_lateral_cycle(
                sop_embeddings=sop_embeddings,
                force_recompute=force_recompute,
            )
            result["execution_output"] = {
                "num_sites": len(tactical_output.site_keys),
                "lateral_iterations": tactical_output.lateral_iterations,
                "computed_at": tactical_output.computed_at.isoformat(),
                "demand_checkpoint": tactical_output.demand.checkpoint_path,
                "supply_checkpoint": tactical_output.supply.checkpoint_path,
                "inventory_checkpoint": tactical_output.inventory.checkpoint_path,
            }
            # Expose sub-outputs for _persist_directive_reviews
            exec_output = tactical_output.supply  # supply tGNN carries exception_probability
            logger.info(
                f"Tactical Hive Coordinator: {len(tactical_output.site_keys)} sites, "
                f"{tactical_output.lateral_iterations} lateral iteration(s)"
            )
        except Exception as e:
            logger.warning(f"Tactical Hive Coordinator failed: {e}")
            result["errors"].append(f"tactical_hive: {e}")

        # --- Step 3: Merge outputs ---
        gnn_outputs = self._merge_outputs(sop_analysis, tactical_output)
        if not gnn_outputs:
            result["errors"].append("No GNN outputs available for broadcast")
            return result

        # --- Step 3.7: Apply Planning TRM adjustments ---
        # Each domain TRM applies in-cycle corrections to the GNN baseline output.
        # GNN generates the baseline plan; Planning TRM adjusts for short-term context
        # (recent forecast bias, capacity signals, supplier confirmation rates, etc.)
        try:
            trm_stats = self._apply_planning_trm_adjustments(gnn_outputs, tactical_output)
            result["planning_trm_adjustments"] = trm_stats
            logger.info(
                f"Planning TRM adjustments applied: "
                f"{trm_stats.get('demand_adjusted', 0)} demand, "
                f"{trm_stats.get('inventory_adjusted', 0)} inventory, "
                f"{trm_stats.get('supply_adjusted', 0)} supply sites adjusted"
            )
        except Exception as e:
            logger.warning(f"Planning TRM adjustments failed (non-blocking): {e}")
            result["errors"].append(f"planning_trm: {e}")

        # --- Step 3.5: Persist directives for human review ---
        try:
            reviews_created = await self._persist_directive_reviews(
                gnn_outputs, sop_analysis, tactical_output,
            )
            result["reviews_created"] = reviews_created
            logger.info(f"Persisted {reviews_created} GNN directive reviews for human review")
        except Exception as e:
            logger.warning(f"Failed to persist directive reviews: {e}")
            result["errors"].append(f"review_persistence: {e}")

        # --- Step 4+5: Generate directives and broadcast ---
        try:
            from app.services.powell.directive_broadcast_service import (
                DirectiveBroadcastService,
            )

            # Build network topology adjacency from config
            topology = await self._build_topology_adjacency()

            broadcast_svc = DirectiveBroadcastService()

            # Register site agents if available
            await self._register_site_agents(broadcast_svc)

            cycle_result = broadcast_svc.run_cycle(
                gnn_outputs=gnn_outputs,
                network_topology=topology,
            )

            result["directives_generated"] = cycle_result.get("directives_generated", 0)
            result["broadcast_success"] = cycle_result.get("broadcast_success", 0)
            result["broadcast_failed"] = cycle_result.get("broadcast_failed", 0)

            logger.info(
                f"Directive broadcast: {result['directives_generated']} generated, "
                f"{result['broadcast_success']} delivered"
            )

        except Exception as e:
            logger.error(f"Directive broadcast failed: {e}")
            result["errors"].append(f"broadcast: {e}")

        # --- Step 6: Collect feedback ---
        try:
            if hasattr(broadcast_svc, "collect_feedback"):
                feedback = broadcast_svc.collect_feedback()
                result["feedback"] = {
                    k: v.to_dict() if hasattr(v, "to_dict") else v
                    for k, v in feedback.items()
                }
        except Exception as e:
            logger.warning(f"Feedback collection failed: {e}")

        result["cycle_duration_ms"] = int(
            (datetime.utcnow() - cycle_start).total_seconds() * 1000
        )
        return result

    def _merge_outputs(
        self,
        sop_analysis,
        tactical_output,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Merge S&OP and TacticalHiveOutput into unified per-site dict.

        Format: {site_key: {criticality_score, bottleneck_risk, demand_forecast, ...}}
        This is what DirectiveBroadcastService.generate_directives_from_gnn() expects.

        When tactical_output is a TacticalHiveOutput, the merged_per_site dict
        produced by TacticalHiveCoordinator.merge_outputs() is used directly and
        overlaid on top of the S&OP values. This preserves 100% backward
        compatibility with DirectiveBroadcastService consumers.
        """
        merged: Dict[str, Dict[str, Any]] = {}

        # Populate from S&OP analysis
        if sop_analysis:
            for site_key in sop_analysis.site_keys:
                merged[site_key] = {
                    "criticality_score": sop_analysis.criticality.get(site_key, 0.5),
                    "bottleneck_risk": sop_analysis.bottleneck_risk.get(site_key, 0.3),
                    "concentration_risk": sop_analysis.concentration_risk.get(site_key, 0.2),
                    "resilience_score": sop_analysis.resilience.get(site_key, 0.7),
                    "safety_stock_multiplier": sop_analysis.safety_stock_multiplier.get(site_key, 1.0),
                }

        # Overlay TacticalHiveOutput (3-parallel tGNNs)
        if tactical_output is not None:
            from app.services.powell.tactical_hive_coordinator import TacticalHiveOutput
            if isinstance(tactical_output, TacticalHiveOutput):
                for site_key, values in tactical_output.merged_per_site.items():
                    if site_key not in merged:
                        merged[site_key] = {
                            "criticality_score": 0.5,
                            "bottleneck_risk": 0.3,
                            "concentration_risk": 0.2,
                            "resilience_score": 0.7,
                            "safety_stock_multiplier": 1.0,
                        }
                    # merged_per_site already has backward-compatible keys
                    merged[site_key].update(values)
            else:
                # Legacy ExecutionGNNOutput path (should not be reached after migration)
                exec_output = tactical_output
                for site_key in exec_output.site_keys:
                    if site_key not in merged:
                        merged[site_key] = {
                            "criticality_score": 0.5,
                            "bottleneck_risk": 0.3,
                            "concentration_risk": 0.2,
                            "resilience_score": 0.7,
                            "safety_stock_multiplier": 1.0,
                        }
                    merged[site_key].update({
                        "demand_forecast": exec_output.demand_forecast.get(site_key, []),
                        "exception_probability": exec_output.exception_probability.get(site_key, 0.1),
                        "order_recommendation": exec_output.order_recommendation.get(site_key, 0),
                        "confidence": exec_output.confidence.get(site_key, 0.5),
                        "propagation_impact": exec_output.propagation_impact.get(site_key, []),
                    })

        return merged

    async def _build_topology_adjacency(self) -> Dict[str, List[str]]:
        """Build {site_key: [neighbor_site_keys]} from supply chain config."""
        from app.models.supply_chain_config import Site, TransportationLane

        sites_result = await self.db.execute(
            Site.__table__.select().where(Site.config_id == self.config_id)
        )
        sites = {row.id: row.site_key or f"site_{row.id}" for row in sites_result}

        lanes_result = await self.db.execute(
            TransportationLane.__table__.select().where(
                TransportationLane.config_id == self.config_id
            )
        )

        adjacency: Dict[str, List[str]] = {sk: [] for sk in sites.values()}

        for lane in lanes_result:
            src = sites.get(lane.source_site_id)
            tgt = sites.get(lane.target_site_id)
            if src and tgt:
                if tgt not in adjacency.get(src, []):
                    adjacency.setdefault(src, []).append(tgt)
                if src not in adjacency.get(tgt, []):
                    adjacency.setdefault(tgt, []).append(src)

        return adjacency

    async def _persist_directive_reviews(
        self,
        gnn_outputs: Dict[str, Dict[str, Any]],
        sop_analysis,
        tactical_output,
    ) -> int:
        """
        Persist GNN outputs as GNNDirectiveReview rows with status=PROPOSED.

        Creates one row per site per directive scope (sop_policy and/or
        tactical_directive), allowing humans to review before application.

        Accepts TacticalHiveOutput (new) or legacy ExecutionGNNOutput.

        Returns count of review rows created.
        """
        from app.models.gnn_directive_review import GNNDirectiveReview
        from datetime import timedelta

        # Resolve per-site reasoning from tactical output
        # For TacticalHiveOutput, compose a merged reasoning string per site.
        tactical_reasoning_map: Dict[str, Optional[str]] = {}
        tactical_confidence_map: Dict[str, float] = {}

        if tactical_output is not None:
            from app.services.powell.tactical_hive_coordinator import TacticalHiveOutput
            if isinstance(tactical_output, TacticalHiveOutput):
                for sk in tactical_output.site_keys:
                    parts = []
                    dr = tactical_output.demand.reasoning.get(sk)
                    sr = tactical_output.supply.reasoning.get(sk)
                    ir = tactical_output.inventory.reasoning.get(sk)
                    if dr:
                        parts.append(f"[Demand] {dr}")
                    if sr:
                        parts.append(f"[Supply] {sr}")
                    if ir:
                        parts.append(f"[Inventory] {ir}")
                    tactical_reasoning_map[sk] = " | ".join(parts) if parts else None
                    # Average confidence across three domains
                    confs = [
                        tactical_output.demand.confidence.get(sk, 0.5),
                        tactical_output.supply.confidence.get(sk, 0.5),
                        tactical_output.inventory.confidence.get(sk, 0.5),
                    ]
                    tactical_confidence_map[sk] = sum(confs) / len(confs)
            else:
                # Legacy ExecutionGNNOutput
                exec_output = tactical_output
                if hasattr(exec_output, "reasoning") and exec_output.reasoning:
                    for sk in getattr(exec_output, "site_keys", []):
                        tactical_reasoning_map[sk] = exec_output.reasoning.get(sk)
                        tactical_confidence_map[sk] = exec_output.confidence.get(sk, 0.5)

        count = 0
        now = datetime.utcnow()

        for site_key, values in gnn_outputs.items():
            # S&OP policy parameters (if S&OP analysis was available)
            sop_keys = {
                "criticality_score", "bottleneck_risk", "concentration_risk",
                "resilience_score", "safety_stock_multiplier",
            }
            sop_values = {k: v for k, v in values.items() if k in sop_keys}
            if sop_values and sop_analysis:
                # Get plain-English reasoning from S&OP GraphSAGE output
                sop_reasoning = None
                if hasattr(sop_analysis, "reasoning") and sop_analysis.reasoning:
                    sop_reasoning = sop_analysis.reasoning.get(site_key)
                review = GNNDirectiveReview(
                    config_id=self.config_id,
                    site_key=site_key,
                    directive_scope="sop_policy",
                    proposed_values=sop_values,
                    proposed_reasoning=sop_reasoning,
                    model_type="sop_graphsage",
                    model_confidence=sop_values.get("resilience_score", 0.5),
                    status="PROPOSED",
                    expires_at=now + timedelta(hours=24),
                )
                self.db.add(review)
                count += 1

            # Tactical directives (from TacticalHiveCoordinator or legacy ExecutionGNN)
            exec_keys = {
                "demand_forecast", "exception_probability",
                "order_recommendation", "confidence",
            }
            exec_values = {k: v for k, v in values.items() if k in exec_keys}
            if exec_values and tactical_output is not None:
                exec_reasoning = tactical_reasoning_map.get(site_key)
                confidence = tactical_confidence_map.get(site_key, exec_values.get("confidence", 0.5))
                # Determine model_type based on output type
                from app.services.powell.tactical_hive_coordinator import TacticalHiveOutput
                model_type = (
                    "tactical_hive"
                    if isinstance(tactical_output, TacticalHiveOutput)
                    else "execution_tgnn"
                )
                review = GNNDirectiveReview(
                    config_id=self.config_id,
                    site_key=site_key,
                    directive_scope="execution_directive",
                    proposed_values=exec_values,
                    proposed_reasoning=exec_reasoning,
                    model_type=model_type,
                    model_confidence=confidence,
                    status="PROPOSED",
                    expires_at=now + timedelta(hours=12),
                )
                self.db.add(review)
                count += 1

        try:
            self.db.flush()
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to persist directive reviews: {e}")
            self.db.rollback()
            raise

        return count

    async def _register_site_agents(self, broadcast_svc) -> None:
        """Register any active SiteAgents with the broadcast service."""
        # In production, SiteAgents are long-lived objects.
        # For demo/testing, we skip registration — broadcast_svc
        # will generate directives but won't deliver them to agents.
        # Agents that are already running pick up directives via
        # the next decision cycle's apply_directive() call.
        pass

    async def run_site_tgnn_cycle(
        self,
        site_agent: Any,
    ) -> Dict[str, Any]:
        """Run Site tGNN (Layer 1.5) hourly inference for a single site.

        This is called hourly by the scheduler for each active SiteAgent
        that has Site tGNN initialized. The Site tGNN modulates the
        UrgencyVector before the next decision cycle.

        Args:
            site_agent: SiteAgent instance with signal_bus and urgency_vector

        Returns:
            Dict with inference results
        """
        if not hasattr(site_agent, "_site_tgnn_service") or not site_agent._site_tgnn_service:
            return {"status": "skipped", "reason": "site_tgnn not enabled"}

        try:
            from app.services.powell.hive_feedback import compute_feedback_features

            feedback = compute_feedback_features(
                urgency_snapshot=(
                    site_agent.signal_bus.urgency.snapshot()
                    if site_agent.signal_bus and hasattr(site_agent.signal_bus, "urgency")
                    else None
                ),
                signal_bus=site_agent.signal_bus,
            )

            output = site_agent._site_tgnn_service.infer(
                hive_signal_bus=site_agent.signal_bus,
                urgency_vector=(
                    site_agent.signal_bus.urgency
                    if site_agent.signal_bus and hasattr(site_agent.signal_bus, "urgency")
                    else None
                ),
                recent_decisions=getattr(site_agent, "_recent_decisions_cache", {}),
                hive_feedback=feedback,
            )

            return {
                "status": "completed",
                "site_key": site_agent.site_key,
                "output": output.to_dict(),
            }
        except Exception as e:
            logger.warning(f"Site tGNN cycle failed for {site_agent.site_key}: {e}")
            return {"status": "error", "error": str(e)}

    def _apply_planning_trm_adjustments(
        self,
        gnn_outputs: Dict[str, Dict[str, Any]],
        tactical_output,
    ) -> Dict[str, Any]:
        """
        Apply Planning TRM in-cycle corrections to GNN baseline outputs.

        For each site, instantiates the three domain Planning TRMs
        (Demand, Inventory, Supply) and applies their adjustment factors
        to the corresponding GNN signals in gnn_outputs (in-place).

        Uses GNN output signals as state proxies so that no additional DB
        queries are required in the daily cycle. Full per-product TRM
        evaluation is performed by the domain planning services when they
        generate detailed plans.

        Returns a stats dict summarising how many sites were adjusted per domain.
        """
        from app.services.powell.demand_adjustment_trm import (
            DemandAdjustmentTRM, DemandAdjustmentState,
        )
        from app.services.powell.inventory_adjustment_trm import (
            InventoryAdjustmentTRM, InventoryAdjustmentState,
        )
        from app.services.powell.supply_adjustment_trm import (
            SupplyAdjustmentTRM, SupplyAdjustmentState,
        )
        import datetime as _dt

        demand_adjusted = 0
        inventory_adjusted = 0
        supply_adjusted = 0

        week_of_year = _dt.date.today().isocalendar()[1]
        week_normalised = (week_of_year - 1) / 51.0

        for site_key, signals in gnn_outputs.items():
            # ----------------------------------------------------------------
            # Demand Adjustment TRM
            # State built from GNN demand signals + heuristic proxies
            # ----------------------------------------------------------------
            try:
                d_conf = signals.get("domain_confidence", {}).get("demand", 0.8)
                d_forecast = signals.get("demand_forecast", [1.0])
                d_volatility = float(signals.get("demand_volatility", 0.0))
                bullwhip = float(signals.get("bullwhip_coefficient", 1.0))

                demand_trm = DemandAdjustmentTRM(site_key=site_key)
                demand_state = DemandAdjustmentState(
                    product_id="aggregate",
                    site_id=site_key,
                    gnn_p50_forecast=float(d_forecast[0]) if d_forecast else 1.0,
                    gnn_confidence=float(d_conf),
                    # Use demand volatility as mape proxy (normalised)
                    recent_bias=float(bullwhip - 1.0) * 0.1,
                    recent_mape=float(d_volatility),
                    inventory_weeks_cover=float(
                        signals.get("pipeline_coverage_days", 14.0)
                    ) / 7.0,
                    backlog_flag=1.0 if signals.get("stockout_probability", 0.0) > 0.3 else 0.0,
                    email_signal_adj_factor=1.0,
                    email_signal_age_days=7.0,
                    lifecycle_stage=0.67,  # assume mature — no product-level data here
                    promotion_active=0.0,
                    week_of_year_normalised=week_normalised,
                    demand_trend_4w=float(bullwhip - 1.0) * 0.05,
                )
                demand_rec = demand_trm.evaluate(demand_state)

                if demand_rec.adjustment_factor != 1.0:
                    # Apply to demand_forecast list in place
                    adjusted = [
                        v * demand_rec.adjustment_factor
                        for v in signals.get("demand_forecast", [])
                    ]
                    gnn_outputs[site_key]["demand_forecast"] = adjusted
                    gnn_outputs[site_key]["demand_trm_factor"] = demand_rec.adjustment_factor
                    gnn_outputs[site_key]["demand_trm_confidence"] = demand_rec.confidence
                    if demand_rec.adjustment_factor != 1.0:
                        demand_adjusted += 1
            except Exception as exc:
                logger.debug(f"DemandAdjustmentTRM skipped for {site_key}: {exc}")

            # ----------------------------------------------------------------
            # Inventory Adjustment TRM
            # State built from GNN inventory signals + heuristic proxies
            # ----------------------------------------------------------------
            try:
                i_conf = signals.get("domain_confidence", {}).get("inventory", 0.8)
                ss_multiplier = float(signals.get("safety_stock_multiplier", 1.0))
                stockout_prob = float(signals.get("stockout_probability", 0.0))
                buffer_adj = float(signals.get("buffer_adjustment_signal", 0.0))
                lead_time_risk = float(signals.get("lead_time_risk", 0.0))

                inv_trm = InventoryAdjustmentTRM(site_key=site_key)
                inv_state = InventoryAdjustmentState(
                    product_id="aggregate",
                    site_id=site_key,
                    gnn_ss_quantity=ss_multiplier * 100.0,  # relative units
                    gnn_confidence=float(i_conf),
                    actual_stockout_rate_4w=stockout_prob * 0.5,
                    supplier_reliability_trend=0.0,
                    oee_trend=0.0,
                    on_hand_weeks_cover=float(
                        signals.get("pipeline_coverage_days", 14.0)
                    ) / 7.0,
                    lead_time_trend=lead_time_risk,
                    demand_cv_trend=float(signals.get("demand_volatility", 0.0)),
                    holding_cost_pressure=0.0,
                    ss_multiplier=ss_multiplier,
                )
                inv_rec = inv_trm.evaluate(inv_state)

                if inv_rec.ss_adjustment_delta != 0.0:
                    gnn_outputs[site_key]["safety_stock_multiplier"] = max(
                        0.5,
                        ss_multiplier + inv_rec.ss_adjustment_delta,
                    )
                    gnn_outputs[site_key]["inventory_trm_delta"] = inv_rec.ss_adjustment_delta
                    gnn_outputs[site_key]["inventory_trm_confidence"] = inv_rec.confidence
                    inventory_adjusted += 1
            except Exception as exc:
                logger.debug(f"InventoryAdjustmentTRM skipped for {site_key}: {exc}")

            # ----------------------------------------------------------------
            # Supply Adjustment TRM
            # State built from GNN supply signals + heuristic proxies
            # ----------------------------------------------------------------
            try:
                s_conf = signals.get("domain_confidence", {}).get("supply", 0.8)
                order_rec = float(signals.get("order_recommendation", 0.0))
                exc_prob = float(signals.get("exception_probability", 0.0))
                pipeline_cov = float(signals.get("pipeline_coverage_days", 14.0))
                alloc_prio = float(signals.get("allocation_priority", 0.5))

                supply_trm = SupplyAdjustmentTRM(site_key=site_key)
                supply_state = SupplyAdjustmentState(
                    product_id="aggregate",
                    site_id=site_key,
                    gnn_supply_plan_qty=order_rec,
                    gnn_confidence=float(s_conf),
                    rccp_feasibility_flag=1.0 if exc_prob < 0.2 else 0.0,
                    supplier_confirmation_rate=max(0.5, 1.0 - exc_prob),
                    open_po_coverage=min(1.0, pipeline_cov / 14.0),
                    lead_time_deviation=float(signals.get("lead_time_risk", 0.0)),
                    available_to_promise=alloc_prio,
                    exception_probability=exc_prob,
                    demand_plan_change=float(
                        gnn_outputs[site_key].get("demand_trm_factor", 1.0) - 1.0
                    ),
                    inventory_target_change=float(
                        gnn_outputs[site_key].get("inventory_trm_delta", 0.0)
                    ),
                    frozen_horizon_flag=0.0,
                )
                supply_rec = supply_trm.evaluate(supply_state)

                if supply_rec.adjustment_factor != 1.0:
                    gnn_outputs[site_key]["order_recommendation"] = (
                        order_rec * supply_rec.adjustment_factor
                    )
                    gnn_outputs[site_key]["supply_trm_factor"] = supply_rec.adjustment_factor
                    gnn_outputs[site_key]["supply_trm_confidence"] = supply_rec.confidence
                    supply_adjusted += 1
            except Exception as exc:
                logger.debug(f"SupplyAdjustmentTRM skipped for {site_key}: {exc}")

        return {
            "demand_adjusted": demand_adjusted,
            "inventory_adjusted": inventory_adjusted,
            "supply_adjusted": supply_adjusted,
            "sites_processed": len(gnn_outputs),
        }
