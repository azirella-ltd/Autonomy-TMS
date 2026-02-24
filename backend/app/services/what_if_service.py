"""
What-If Analysis Service
Phase 7 Sprint 3

Provides asynchronous what-if scenario analysis using LLM interpretation.
"""

import asyncio
import logging
from typing import Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.models.chat import WhatIfAnalysis
from app.models.scenario import Scenario
from app.models.scenario_user import ScenarioUser
from app.models.supply_chain import ScenarioUserPeriod


logger = logging.getLogger(__name__)


class WhatIfAnalysisService:
    """Service for running what-if scenario analysis."""

    def __init__(self, db: Session):
        self.db = db

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
        current_round = round_result.scalars().first()

        if not current_round:
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
        projected_demand = sum(recent_demand) / len(recent_demand) if recent_demand else current_round.demand

        # Current state
        inventory = current_round.current_inventory
        backlog = current_round.current_backlog

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

        # Calculate costs
        inventory_cost = new_inventory * 0.50  # $0.50 per unit per round
        backlog_cost = new_backlog * 1.00     # $1.00 per unit per round
        total_cost = inventory_cost + backlog_cost

        # Baseline cost (with current order)
        baseline_incoming = current_order
        baseline_available = inventory + baseline_incoming
        baseline_fulfilled = min(baseline_available, backlog + demand_next)
        baseline_inventory = max(0, baseline_available - baseline_fulfilled)
        baseline_backlog = max(0, (backlog + demand_next) - baseline_fulfilled)
        baseline_cost = (baseline_inventory * 0.50) + (baseline_backlog * 1.00)

        # Cost difference
        cost_difference = total_cost - baseline_cost

        # Service level
        service_level = fulfilled / (backlog + demand_next) if (backlog + demand_next) > 0 else 1.0

        # Build result
        result = {
            "projected_inventory": new_inventory,
            "projected_backlog": new_backlog,
            "projected_cost": total_cost,
            "cost_difference": cost_difference,
            "service_level": service_level,
            "order_quantity": order_quantity,
            "current_order": current_order,
            "demand_assumption": projected_demand,
            "baseline_inventory": baseline_inventory,
            "baseline_backlog": baseline_backlog,
            "baseline_cost": baseline_cost,
            "inventory_cost": inventory_cost,
            "backlog_cost": backlog_cost,
        }

        logger.debug(f"Simulation result: {result}")

        return result

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

            # Retrieve RAG context relevant to the what-if question
            kb_context = await get_rag_context(question, top_k=3, max_tokens=2000)
            kb_section = ""
            if kb_context:
                kb_section = f"\nRelevant Supply Chain Knowledge:\n{kb_context}\nUse the above knowledge to inform your analysis.\n"

            # Build analysis prompt
            prompt = f"""You are a supply chain advisor analyzing a "what-if" scenario for a scenario_user in a supply chain simulation.

User Question: {question}
{kb_section}
Scenario Parameters:
- Proposed Order Quantity: {scenario.get('order_quantity', 'N/A')} units
- Baseline Order: {scenario.get('current_order', 'N/A')} units
- Difference: {scenario.get('order_quantity', 0) - scenario.get('current_order', 0):+d} units

Projected Results (1 round ahead):
- Projected Inventory: {result['projected_inventory']} units
- Projected Backlog: {result['projected_backlog']} units
- Projected Cost: ${result['projected_cost']:.2f}
- Cost Difference: ${result['cost_difference']:+.2f} (vs. baseline)
- Service Level: {result['service_level']:.1%}

Baseline Comparison (with current order):
- Baseline Inventory: {result['baseline_inventory']} units
- Baseline Backlog: {result['baseline_backlog']} units
- Baseline Cost: ${result['baseline_cost']:.2f}

Analysis Requirements:
Provide a concise 2-3 sentence analysis that:
1. Explains what the projected results mean
2. States whether this strategy is recommended (yes/no/depends)
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

            # Fallback to template analysis
            cost_impact = "increase" if result['cost_difference'] > 0 else "decrease"
            recommendation = "not recommended" if result['cost_difference'] > 5 else "recommended"

            fallback = (
                f"Ordering {result['order_quantity']} units instead of {result['current_order']} "
                f"will result in a projected cost {cost_impact} of ${abs(result['cost_difference']):.2f}. "
                f"This strategy is {recommendation} based on cost optimization. "
                f"Service level is projected at {result['service_level']:.0%}."
            )

            return fallback


def get_what_if_service(db: Session) -> WhatIfAnalysisService:
    """
    Get what-if analysis service.

    Args:
        db: Database session

    Returns:
        WhatIfAnalysisService instance
    """
    return WhatIfAnalysisService(db)
