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

    Layer 2 of the 4-layer coordination stack:
        Layer 1: Intra-Hive (HiveSignalBus) — <10ms, within site
        Layer 2: tGNN Inter-Hive (this service) — daily, cross-site
        Layer 3: AAP Cross-Authority — seconds-minutes, ad hoc
        Layer 4: S&OP Consensus Board — weekly, policy parameters
    """

    def __init__(self, db: AsyncSession, config_id: int):
        self.db = db
        self.config_id = config_id

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

            sop_svc = SOPInferenceService(self.db, self.config_id)
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

        # --- Step 2: Execution Temporal GNN ---
        exec_output = None
        try:
            from app.services.powell.execution_gnn_inference_service import (
                ExecutionGNNInferenceService,
            )

            exec_svc = ExecutionGNNInferenceService(self.db, self.config_id)
            exec_output = await exec_svc.infer(
                sop_embeddings=sop_embeddings,
                force_recompute=force_recompute,
            )
            result["execution_output"] = {
                "num_sites": exec_output.num_sites,
                "computed_at": (
                    exec_output.computed_at.isoformat()
                    if exec_output.computed_at else None
                ),
            }
            logger.info(
                f"Execution tGNN inference: {exec_output.num_sites} sites"
            )
        except Exception as e:
            logger.warning(f"Execution tGNN inference failed: {e}")
            result["errors"].append(f"execution_inference: {e}")

        # --- Step 3: Merge outputs ---
        gnn_outputs = self._merge_outputs(sop_analysis, exec_output)
        if not gnn_outputs:
            result["errors"].append("No GNN outputs available for broadcast")
            return result

        # --- Step 3.5: Persist directives for human review ---
        try:
            reviews_created = await self._persist_directive_reviews(
                gnn_outputs, sop_analysis, exec_output,
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
        exec_output,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Merge S&OP and Execution GNN outputs into unified per-site dict.

        Format: {site_key: {criticality_score, bottleneck_risk, demand_forecast, ...}}
        This is what DirectiveBroadcastService.generate_directives_from_gnn() expects.
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

        # Overlay Execution tGNN outputs
        if exec_output:
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
        exec_output,
    ) -> int:
        """
        Persist GNN outputs as GNNDirectiveReview rows with status=PROPOSED.

        Creates one row per site per directive scope (sop_policy and/or
        execution_directive), allowing humans to review before application.

        Returns count of review rows created.
        """
        from app.models.gnn_directive_review import GNNDirectiveReview
        from datetime import timedelta

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
                review = GNNDirectiveReview(
                    config_id=self.config_id,
                    site_key=site_key,
                    directive_scope="sop_policy",
                    proposed_values=sop_values,
                    model_type="sop_graphsage",
                    model_confidence=sop_values.get("resilience_score", 0.5),
                    status="PROPOSED",
                    expires_at=now + timedelta(hours=24),
                )
                self.db.add(review)
                count += 1

            # Execution directives (if Execution tGNN was available)
            exec_keys = {
                "demand_forecast", "exception_probability",
                "order_recommendation", "confidence", "propagation_impact",
            }
            exec_values = {k: v for k, v in values.items() if k in exec_keys}
            if exec_values and exec_output:
                review = GNNDirectiveReview(
                    config_id=self.config_id,
                    site_key=site_key,
                    directive_scope="execution_directive",
                    proposed_values=exec_values,
                    model_type="execution_tgnn",
                    model_confidence=exec_values.get("confidence", 0.5),
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
