"""
What-If Analysis Service
Phase 7 Sprint 3

Provides asynchronous what-if scenario analysis using LLM interpretation.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.models.chat import WhatIfAnalysis
from app.models.scenario import Scenario
from app.models.scenario_user import ScenarioUser
from app.models.supply_chain import ScenarioUserPeriod
from app.models.sc_entities import InvPolicy, Product
from app.models.supply_chain_config import Site


logger = logging.getLogger(__name__)


class WhatIfAnalysisService:
    """Service for running what-if scenario analysis."""

    def __init__(self, db: Session, tenant_id: Optional[int] = None):
        self.db = db
        self.tenant_id = tenant_id

    async def process_analysis(self, analysis_id: int):
        """
        Process a what-if analysis asynchronously.

        This method:
        1. Loads the analysis request
        2. Runs simulation with scenario parameters
        3. Calls LLM for interpretation
        4. Updates analysis with results
        5. Broadcasts completion via WebSocket

        Args:
            analysis_id: Analysis ID to process
        """
        try:
            # Get analysis
            result = await self.db.execute(
                select(WhatIfAnalysis).filter(WhatIfAnalysis.id == analysis_id)
            )
            analysis = result.scalars().first()

            if not analysis:
                logger.error(f"Analysis {analysis_id} not found")
                return

            logger.info(f"Processing what-if analysis {analysis_id}")

            # Run simulation
            sim_result = await self._simulate_scenario(
                scenario_id=analysis.scenario_id,
                round=analysis.round,
                scenario_user_id=analysis.scenario_user_id,
                scenario=analysis.scenario,
            )

            # Get LLM interpretation
            llm_analysis = await self._analyze_with_llm(
                question=analysis.question,
                scenario=analysis.scenario,
                result=sim_result,
            )

            # Update analysis
            analysis.result = sim_result
            analysis.agent_analysis = llm_analysis
            analysis.completed = True
            analysis.completed_at = datetime.utcnow()

            await self.db.commit()
            await self.db.refresh(analysis)

            logger.info(f"Completed what-if analysis {analysis_id}")

            # Broadcast completion via WebSocket
            try:
                from app.api.endpoints.websocket import manager
                await manager.broadcast_to_scenario(
                    analysis.scenario_id,
                    {
                        "type": "chat:analysis_complete",
                        "data": {
                            "id": analysis.id,
                            "completed": True,
                            "result": sim_result,
                            "agent_analysis": llm_analysis,
                            "completed_at": analysis.completed_at.isoformat(),
                        }
                    }
                )
                logger.info(f"Broadcasted analysis {analysis_id} completion")
            except Exception as e:
                logger.error(f"Failed to broadcast analysis completion: {e}")

        except Exception as e:
            logger.error(f"Failed to process analysis {analysis_id}: {e}", exc_info=True)

            # Mark as completed with error
            try:
                result = await self.db.execute(
                    select(WhatIfAnalysis).filter(WhatIfAnalysis.id == analysis_id)
                )
                analysis = result.scalars().first()

                if analysis:
                    analysis.completed = True
                    analysis.agent_analysis = f"Analysis failed: {str(e)}"
                    analysis.completed_at = datetime.utcnow()
                    await self.db.commit()
            except Exception as db_error:
                logger.error(f"Failed to update analysis error state: {db_error}")

    async def _simulate_scenario(
        self,
        scenario_id: int,
        round: int,
        scenario_user_id: int,
        scenario: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Simulate scenario and calculate projected metrics.

        For now, this uses a simplified projection based on current state.
        In future, integrate with full SimPy simulation engine.

        Args:
            scenario_id: Scenario ID
            round: Current period
            scenario_user_id: ScenarioUser ID
            scenario: Scenario parameters (order_quantity, etc.)

        Returns:
            Dictionary with projected metrics
        """
        # Get scenario state
        scenario_result = await self.db.execute(select(Scenario).filter(Scenario.id == scenario_id))
        scenario_obj = scenario_result.scalars().first()

        if not scenario_obj:
            raise ValueError(f"Scenario {scenario_id} not found")

        # Get scenario_user
        participant_result = await self.db.execute(
            select(ScenarioUser).filter(ScenarioUser.id == scenario_user_id)
        )
        scenario_user = participant_result.scalars().first()

        if not scenario_user:
            raise ValueError(f"ScenarioUser {scenario_user_id} not found")

        # Get latest scenario_user period
        round_result = await self.db.execute(
            select(ScenarioUserPeriod)
            .filter(ScenarioUserPeriod.scenario_user_id == scenario_user.id)
            .order_by(desc(ScenarioUserPeriod.round))
            .limit(1)
        )
        current_period = round_result.scalars().first()

        if not current_period:
            raise ValueError(f"No periods found for scenario_user {scenario_user.id}")

        # Extract scenario parameters
        order_quantity = scenario.get('order_quantity', 0)
        current_order = scenario.get('current_order', 0)

        # Get recent demand for projection
        recent_rounds_result = await self.db.execute(
            select(ScenarioUserPeriod)
            .filter(ScenarioUserPeriod.scenario_user_id == scenario_user.id)
            .order_by(desc(ScenarioUserPeriod.round))
            .limit(5)
        )
        recent_rounds = list(recent_rounds_result.scalars().all())

        # Calculate average demand
        recent_demand = [r.demand for r in recent_rounds if hasattr(r, 'demand') and r.demand is not None]
        projected_demand = sum(recent_demand) / len(recent_demand) if recent_demand else current_period.demand

        # Load cost rates from InvPolicy for the scenario's config
        holding_cost_rate, backlog_cost_rate = await self._get_cost_rates(
            scenario_obj, scenario_user
        )

        # Current state
        inventory = current_period.current_inventory
        backlog = current_period.current_backlog

        # Simple projection (1-round ahead)
        # Assumes order arrives with lead time and demand continues at projected rate
        lead_time = scenario_user.lead_time if hasattr(scenario_user, 'lead_time') else 2

        # Calculate next round state
        incoming = order_quantity  # Simplified: ignoring lead time for what-if
        demand_next = projected_demand

        # Fulfillment logic
        available = inventory + incoming
        fulfilled = min(available, backlog + demand_next)
        new_inventory = max(0, available - fulfilled)
        new_backlog = max(0, (backlog + demand_next) - fulfilled)

        # Calculate costs (legacy linear accrual; kept as a reporting
        # axis on the result. The recommendation gate downstream uses
        # the BSC delta below, not raw cost.)
        inventory_cost = new_inventory * holding_cost_rate
        backlog_cost = new_backlog * backlog_cost_rate
        total_cost = inventory_cost + backlog_cost

        # Baseline cost (with current order)
        baseline_incoming = current_order
        baseline_available = inventory + baseline_incoming
        baseline_fulfilled = min(baseline_available, backlog + demand_next)
        baseline_inventory = max(0, baseline_available - baseline_fulfilled)
        baseline_backlog = max(0, (backlog + demand_next) - baseline_fulfilled)
        baseline_cost = (baseline_inventory * holding_cost_rate) + (baseline_backlog * backlog_cost_rate)

        # Cost difference (kept for backward-compat / reporting; no
        # longer the decision gate)
        cost_difference = total_cost - baseline_cost

        # Service level
        service_level = fulfilled / (backlog + demand_next) if (backlog + demand_next) > 0 else 1.0
        baseline_service_level = (
            baseline_fulfilled / (backlog + demand_next)
            if (backlog + demand_next) > 0 else 1.0
        )

        # BSC: compute multi-dimensional utility for both proposed and
        # baseline. Returns None for both when the tenant hasn't
        # configured BSC weights/goals; callers fall back to the
        # cost-only path in that case.
        bsc = await self._bsc_score_pair(
            proposed={
                "total_cost": total_cost,
                "service_level": service_level,
                "inventory_qty": new_inventory,
                "backlog_qty": new_backlog,
            },
            baseline={
                "total_cost": baseline_cost,
                "service_level": baseline_service_level,
                "inventory_qty": baseline_inventory,
                "backlog_qty": baseline_backlog,
            },
        )

        # Build result
        result = {
            "projected_inventory": new_inventory,
            "projected_backlog": new_backlog,
            "projected_cost": total_cost,
            "cost_difference": cost_difference,
            "service_level": service_level,
            "baseline_service_level": baseline_service_level,
            "order_quantity": order_quantity,
            "current_order": current_order,
            "demand_assumption": projected_demand,
            "baseline_inventory": baseline_inventory,
            "baseline_backlog": baseline_backlog,
            "baseline_cost": baseline_cost,
            "inventory_cost": inventory_cost,
            "backlog_cost": backlog_cost,
            # BSC fields — None when tenant hasn't seeded BSC config
            "bsc_proposed_utility": bsc.get("proposed_utility"),
            "bsc_baseline_utility": bsc.get("baseline_utility"),
            "bsc_delta": bsc.get("delta"),
            "bsc_per_perspective_proposed": bsc.get("proposed_per_perspective"),
            "bsc_per_perspective_baseline": bsc.get("baseline_per_perspective"),
            "bsc_missing_metrics": bsc.get("missing_metrics") or [],
            "bsc_status": bsc.get("status"),  # "ok" | "not_configured" | "error"
        }

        logger.debug(f"Simulation result: {result}")

        return result

    async def _get_cost_rates(self, scenario_obj, scenario_user) -> tuple:
        """Load holding and backlog cost rates from InvPolicy for the scenario's config.

        Falls back to product.unit_cost * 0.25/52 (holding) and * 4 (backlog).

        Raises:
            ValueError: If the scenario has no supply_chain_config_id or no product
                        is found for the config — includes a descriptive message for debugging.
        """
        config_id = getattr(scenario_obj, 'supply_chain_config_id', None)
        if not config_id:
            raise ValueError(
                f"Scenario {scenario_obj.id} has no supply_chain_config_id. "
                f"Cannot load cost rates from InvPolicy. "
                f"Ensure the scenario is linked to a supply chain config."
            )

        # Find the product for this config (prefer one with InvPolicy)
        product_result = await self.db.execute(
            select(Product)
            .join(InvPolicy, InvPolicy.product_id == Product.id)
            .filter(Product.config_id == config_id)
            .order_by(Product.id)
            .limit(1)
        )
        product = product_result.scalars().first()
        if not product:
            product_result2 = await self.db.execute(
                select(Product).filter(Product.config_id == config_id).order_by(Product.id).limit(1)
            )
            product = product_result2.scalars().first()
        if not product:
            raise ValueError(
                f"No product found for supply chain config {config_id}. "
                f"Cannot load cost rates. Seed the Product table for config {config_id}."
            )

        unit_cost = float(product.unit_cost or 0.0)
        default_holding = unit_cost * 0.25 / 52
        default_backlog = default_holding * 4.0

        # Find the first site for this config to look up InvPolicy
        site_result = await self.db.execute(
            select(Site).filter(Site.config_id == config_id).limit(1)
        )
        site = site_result.scalars().first()

        inv_policy = None
        if site:
            ip_result = await self.db.execute(
                select(InvPolicy).filter(
                    InvPolicy.site_id == site.id,
                    InvPolicy.product_id == product.id,
                ).limit(1)
            )
            inv_policy = ip_result.scalars().first()

        if inv_policy:
            hcr = inv_policy.holding_cost_range or {}
            bcr = inv_policy.backlog_cost_range or {}
            holding_cost_rate = hcr.get("min", default_holding)
            backlog_cost_rate = bcr.get("min", default_backlog)
        else:
            holding_cost_rate = default_holding
            backlog_cost_rate = default_backlog

        return holding_cost_rate, backlog_cost_rate

    async def _bsc_score_pair(
        self,
        *,
        proposed: Dict[str, float],
        baseline: Dict[str, float],
    ) -> Dict[str, Any]:
        """Compute BSC total-utility for both the proposed and baseline
        scenarios and return the delta + per-perspective breakdown.

        The mapping ``actuals[metric_code] → value`` follows the BSC
        framework's per-tenant goal definitions; only metrics the
        tenant has seeded will contribute. Missing metrics are
        reported back so the LLM analysis can surface "BSC coverage
        is partial" rather than producing a misleadingly precise
        score.

        Returns a flat dict; "status" indicates whether BSC scoring
        actually fired:
          * "ok"             — both scenarios scored
          * "not_configured" — tenant has no BSC weights/goals seeded
          * "error"          — call failed; falls back to cost-only
        """
        if self.tenant_id is None:
            return {"status": "not_configured"}

        try:
            from azirella_data_model.governance.bsc_attainment import (
                compute_total_utility,
            )
            from app.db.session import sync_session_factory
        except Exception as imp_err:
            logger.warning(
                "BSC compute_total_utility unavailable (likely older "
                "Core pin): %s", imp_err,
            )
            return {"status": "error"}

        def _score(actuals: Dict[str, float]) -> Dict[str, Any]:
            sync_db = sync_session_factory()
            try:
                return compute_total_utility(
                    sync_db, self.tenant_id, actuals,
                )
            finally:
                sync_db.close()

        try:
            # Wrap the sync calls in to_thread so the event loop isn't
            # blocked by the per-call DB I/O.
            proposed_result, baseline_result = await asyncio.gather(
                asyncio.to_thread(_score, proposed),
                asyncio.to_thread(_score, baseline),
            )
        except Exception as call_err:
            # The BSC helper reads from `tenant_bsc_weights` /
            # `tenant_bsc_metric_goals`. On TMS DBs that haven't
            # adopted the BSC schema yet, the SQL throws
            # UndefinedTable; treat that as "not configured" rather
            # than a hard error so the caller falls through cleanly.
            msg = str(call_err).lower()
            if "tenant_bsc_weights" in msg or "tenant_bsc_metric_goals" in msg:
                logger.debug(
                    "BSC tables not present on this DB — treating as not_configured: %s",
                    call_err,
                )
                return {"status": "not_configured"}
            logger.warning("BSC score pair failed: %s", call_err)
            return {"status": "error"}

        # If either side is missing the perspective weights or goals,
        # treat as not-configured rather than a hard error — the
        # tenant just hasn't seeded BSC yet.
        for r in (proposed_result, baseline_result):
            if r.get("error") in {"no_bsc_weights", "no_metric_goals"}:
                return {"status": "not_configured"}

        proposed_util = proposed_result.get("total_utility")
        baseline_util = baseline_result.get("total_utility")
        if proposed_util is None or baseline_util is None:
            return {"status": "not_configured"}

        # Aggregate the missing-metric set across both calls so the
        # LLM analysis can flag partial coverage.
        missing = sorted(set(
            list(proposed_result.get("missing_metric_actuals") or [])
            + list(baseline_result.get("missing_metric_actuals") or [])
        ))

        return {
            "status": "ok",
            "proposed_utility": proposed_util,
            "baseline_utility": baseline_util,
            "delta": proposed_util - baseline_util,
            "proposed_per_perspective": proposed_result.get(
                "per_perspective_attainment"
            ),
            "baseline_per_perspective": baseline_result.get(
                "per_perspective_attainment"
            ),
            "missing_metrics": missing,
        }

    async def _analyze_with_llm(
        self,
        question: str,
        scenario: Dict[str, Any],
        result: Dict[str, Any],
    ) -> str:
        """
        Get LLM interpretation of simulation results.

        Args:
            question: User's what-if question
            scenario: Scenario parameters
            result: Simulation results

        Returns:
            LLM-generated analysis text
        """
        try:
            from app.services.llm_suggestion_service import get_llm_service
            from app.services.rag_context import get_rag_context

            llm_service = get_llm_service()

            # Retrieve RAG context relevant to the what-if question (tenant-scoped)
            kb_context = ""
            if self.tenant_id is not None:
                kb_context = await get_rag_context(question, tenant_id=self.tenant_id, top_k=3, max_tokens=2000)
            kb_section = ""
            if kb_context:
                kb_section = f"\nRelevant Supply Chain Knowledge:\n{kb_context}\nUse the above knowledge to inform your analysis.\n"

            # Build analysis prompt. BSC block included only when the
            # tenant has seeded BSC weights/goals — otherwise the
            # prompt falls back to the cost-only framing.
            bsc_block = ""
            if result.get("bsc_status") == "ok":
                delta = result["bsc_delta"]
                p_persp = result.get("bsc_per_perspective_proposed") or {}
                b_persp = result.get("bsc_per_perspective_baseline") or {}
                missing = result.get("bsc_missing_metrics") or []
                missing_note = (
                    f" (BSC coverage partial: missing actuals for "
                    f"{', '.join(missing)})"
                    if missing else ""
                )
                persp_lines = []
                for k in ("FINANCIAL", "CUSTOMER", "INTERNAL", "LEARNING"):
                    p_val = p_persp.get(k, 0.0)
                    b_val = b_persp.get(k, 0.0)
                    persp_lines.append(
                        f"  - {k}: {b_val:+.3f} → {p_val:+.3f} "
                        f"(Δ {p_val - b_val:+.3f})"
                    )
                bsc_block = (
                    f"\nBSC Multi-Dimensional Score{missing_note}:\n"
                    f"- Total utility (baseline → proposed): "
                    f"{result['bsc_baseline_utility']:+.3f} → "
                    f"{result['bsc_proposed_utility']:+.3f} "
                    f"(Δ {delta:+.3f}; positive is better)\n"
                    f"- Per-perspective attainment:\n"
                    + "\n".join(persp_lines)
                    + "\n"
                )

            prompt = f"""You are a supply chain advisor analyzing a "what-if" scenario for a scenario_user in a supply chain simulation.

User Question: {question}
{kb_section}
Scenario Parameters:
- Proposed Order Quantity: {scenario.get('order_quantity', 'N/A')} units
- Baseline Order: {scenario.get('current_order', 'N/A')} units
- Difference: {scenario.get('order_quantity', 0) - scenario.get('current_order', 0):+d} units

Projected Results (1 period ahead):
- Projected Inventory: {result['projected_inventory']} units
- Projected Backlog: {result['projected_backlog']} units
- Projected Cost: ${result['projected_cost']:.2f}
- Cost Difference: ${result['cost_difference']:+.2f} (vs. baseline)
- Service Level: {result['service_level']:.1%}

Baseline Comparison (with current order):
- Baseline Inventory: {result['baseline_inventory']} units
- Baseline Backlog: {result['baseline_backlog']} units
- Baseline Cost: ${result['baseline_cost']:.2f}
{bsc_block}
Analysis Requirements:
Provide a concise 2-3 sentence analysis that:
1. Explains what the projected results mean
2. States whether this strategy is recommended (yes/no/depends).
   When a BSC delta is present above, weight your recommendation on
   the BSC delta (positive = recommended). When BSC is absent, fall
   back to weighing cost vs. service level explicitly.
3. Highlights key risks or benefits

Be direct, actionable, and clear. Use specific numbers from the results.
"""

            # Call LLM
            if llm_service.provider == "openai":
                response = await llm_service._call_openai(prompt)
            else:
                response = await llm_service._call_anthropic(prompt)

            analysis_text = response.strip()

            logger.info(f"Generated LLM analysis: {analysis_text[:100]}...")

            return analysis_text

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")

            # Fallback to template analysis. Prefer the BSC delta as
            # the gate when the tenant has it configured; otherwise
            # fall back to the cost-only rule (preserves prior
            # behaviour for un-seeded tenants).
            cost_impact = "increase" if result['cost_difference'] > 0 else "decrease"
            if result.get("bsc_status") == "ok" and result.get("bsc_delta") is not None:
                bsc_delta = result["bsc_delta"]
                recommendation = "recommended" if bsc_delta > 0 else "not recommended"
                rationale = (
                    f"BSC utility delta {bsc_delta:+.3f} "
                    f"(baseline {result['bsc_baseline_utility']:+.3f} → "
                    f"proposed {result['bsc_proposed_utility']:+.3f})"
                )
            else:
                recommendation = (
                    "not recommended" if result['cost_difference'] > 5
                    else "recommended"
                )
                rationale = "based on cost optimization"

            fallback = (
                f"Ordering {result['order_quantity']} units instead of {result['current_order']} "
                f"will result in a projected cost {cost_impact} of ${abs(result['cost_difference']):.2f}. "
                f"This strategy is {recommendation} ({rationale}). "
                f"Service level is projected at {result['service_level']:.0%}."
            )

            return fallback


def get_what_if_service(db: Session, tenant_id: Optional[int] = None) -> WhatIfAnalysisService:
    """
    Get what-if analysis service.

    Args:
        db: Database session
        tenant_id: Tenant ID for RAG context scoping

    Returns:
        WhatIfAnalysisService instance
    """
    return WhatIfAnalysisService(db, tenant_id=tenant_id)
