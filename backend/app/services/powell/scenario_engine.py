"""
Scenario Engine — Machine-Speed What-If Planning

Core engine that enables agents to test decision cascades in simulation
before committing. When a TRM agent encounters a situation it cannot resolve
within its authority, it creates a scenario branch — a lightweight fork of
the digital twin — injects proposed actions, simulates the consequences,
and compares alternatives using a risk-adjusted Balanced Scorecard.

Analogous to Git branching: the Plan of Record is 'main', agents create
feature branches to test alternatives, the best branch is merged (promoted),
and rejected branches are retained for training.

Key principle: Agents don't just make decisions — they test decision cascades
and present the best option with full BSC impact analysis.

Architecture (SCENARIO_ENGINE.md):
    - Reuses _DagChain from simulation_calibration_service for simulation
    - Reuses _ConfigLoader for DAG topology loading
    - Pure computation: templates -> simulation -> BSC scoring (no LLM)
    - Three-tier anytime execution: TRM Solo -> Template Search -> MCTS

Integration points:
    - TRM SiteAgent calls ScenarioTrigger before solo action
    - Promoted scenarios route decisions to responsible agents via AAP
    - Decision Stream surfaces scenario comparisons with BSC tables
    - CDC Relearning uses promoted scenarios as training data
"""

import copy
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.agent_scenario import (
    AgentScenario,
    AgentScenarioAction,
)
from app.services.powell.contextual_bsc import (
    BSCScore,
    ContextualBSC,
    compute_compound_likelihood,
    compute_urgency_discount,
)
from app.services.powell.scenario_candidates import CandidateActions, CandidateGenerator
from app.services.powell.scenario_trigger import LEVEL_CAPS, ScenarioTrigger

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BSCScoredScenario — result of evaluating one candidate
# ---------------------------------------------------------------------------

@dataclass
class BSCScoredScenario:
    """A scenario that has been simulated and scored."""
    scenario: AgentScenario
    bsc: BSCScore
    candidate: CandidateActions
    simulation_ticks: int = 0
    simulation_time_ms: float = 0.0


# ---------------------------------------------------------------------------
# ScenarioEngine
# ---------------------------------------------------------------------------

class ScenarioEngine:
    """Core scenario engine for machine-speed what-if planning.

    Creates, evaluates, compares, promotes, and rejects scenario branches.
    Uses the existing digital twin simulation (_DagChain) for forward
    simulation and ContextualBSC for risk-adjusted scoring.
    """

    # Default simulation parameters
    DEFAULT_HORIZON_DAYS = 14
    DEFAULT_SEED = 42
    MIN_IMPROVEMENT_THRESHOLD = 0.01  # Stop if next candidate improves < 1%

    def __init__(
        self,
        db: Session,
        config_id: int,
        tenant_id: int,
    ):
        self.db = db
        self.config_id = config_id
        self.tenant_id = tenant_id
        self._bsc = ContextualBSC()

    # -----------------------------------------------------------------------
    # Create scenario
    # -----------------------------------------------------------------------

    def create_scenario(
        self,
        trigger_decision: Dict[str, Any],
        trigger_context: Dict[str, Any],
        decision_level: str = "execution",
        parent_scenario_id: Optional[int] = None,
    ) -> AgentScenario:
        """Create a new scenario branch.

        Args:
            trigger_decision: The TRM decision that triggered this scenario.
                Keys: trm_type, risk_bound, confidence, decision_id
            trigger_context: Business context.
                Keys: product_id, site_id, quantity, shortfall, urgency,
                      economic_impact, ...
            decision_level: execution/tactical/strategic/human_requested
            parent_scenario_id: Optional parent for nested scenarios

        Returns:
            Persisted AgentScenario in CREATED status.
        """
        scenario = AgentScenario(
            config_id=self.config_id,
            tenant_id=self.tenant_id,
            parent_scenario_id=parent_scenario_id,
            trigger_decision_id=trigger_decision.get("decision_id"),
            trigger_trm_type=trigger_decision.get("trm_type", "unknown"),
            trigger_context=trigger_context,
            decision_level=decision_level,
            status="CREATED",
            simulation_days=self.DEFAULT_HORIZON_DAYS,
            simulation_seed=self.DEFAULT_SEED,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        self.db.add(scenario)
        self.db.flush()  # Get the ID

        logger.info(
            "Created scenario %d for config=%d trm=%s level=%s",
            scenario.id, self.config_id,
            trigger_decision.get("trm_type"), decision_level,
        )
        return scenario

    # -----------------------------------------------------------------------
    # Evaluate scenario with candidates
    # -----------------------------------------------------------------------

    def evaluate_scenario(
        self,
        scenario: AgentScenario,
        candidate_actions: List[CandidateActions],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[BSCScoredScenario]:
        """Evaluate a scenario by simulating each candidate.

        Forks current _DagChain state, injects proposed actions, simulates
        forward N days, computes BSC score.

        Implements diminishing returns stopping: if the next candidate's
        improvement is below MIN_IMPROVEMENT_THRESHOLD, stop early.

        Args:
            scenario: The AgentScenario to evaluate
            candidate_actions: Candidate action sets to test
            context: Business context for BSC weight adjustment

        Returns:
            List of BSCScoredScenario, sorted by final_score DESC.
        """
        context = context or scenario.trigger_context or {}

        scenario.status = "EVALUATING"
        self.db.flush()

        # Load the DAG chain
        chain, topo_order = self._load_dag_chain()

        # Determine simulation parameters
        horizon_days = scenario.simulation_days or self.DEFAULT_HORIZON_DAYS
        seed = scenario.simulation_seed or self.DEFAULT_SEED
        decision_level = scenario.decision_level or "execution"
        caps = LEVEL_CAPS.get(decision_level, LEVEL_CAPS["execution"])

        # Compute baseline (do nothing)
        baseline_result = self._simulate_branch(
            chain, topo_order, actions=[], horizon_days=horizon_days, seed=seed,
        )

        # Evaluate candidates with diminishing returns stopping
        scored: List[BSCScoredScenario] = []
        best_final_score = -float("inf")
        urgency = float(context.get("urgency", 0.0))

        for i, candidate in enumerate(candidate_actions):
            if i >= caps.max_candidates:
                logger.debug("Hit max_candidates cap (%d) for level=%s", caps.max_candidates, decision_level)
                break

            start_ms = time.monotonic() * 1000

            # Simulate this candidate
            sim_result = self._simulate_branch(
                chain, topo_order,
                actions=candidate.actions,
                horizon_days=horizon_days,
                seed=seed + i + 1,  # Different seed per candidate
            )

            elapsed_ms = time.monotonic() * 1000 - start_ms

            # Compute BSC score
            bsc = self._bsc.compute_bsc(sim_result, baseline_result, context)

            # Compute compound likelihood from action CDT bounds
            action_likelihoods = [
                a.get("decision_likelihood") for a in candidate.actions
            ]
            bsc.compound_likelihood = compute_compound_likelihood(action_likelihoods)

            # Compute urgency discount
            estimated_execution_days = self._estimate_execution_days(candidate.actions)
            bsc.urgency_discount = compute_urgency_discount(
                urgency, estimated_execution_days,
            )

            # Risk-adjusted final score
            bsc.final_score = self._bsc.risk_adjust(
                bsc.raw_bsc_value, bsc.compound_likelihood, bsc.urgency_discount,
            )

            # Persist actions to the scenario
            for action_dict in candidate.actions:
                action = AgentScenarioAction(
                    scenario_id=scenario.id,
                    trm_type=action_dict.get("trm_type", ""),
                    action_type=action_dict.get("action_type", ""),
                    action_params=action_dict.get("action_params"),
                    responsible_agent=action_dict.get("responsible_agent"),
                    decision_likelihood=action_dict.get("decision_likelihood"),
                    estimated_cost=action_dict.get("estimated_cost"),
                    estimated_benefit=action_dict.get("estimated_benefit"),
                    status="PROPOSED",
                )
                self.db.add(action)

            scored_scenario = BSCScoredScenario(
                scenario=scenario,
                bsc=bsc,
                candidate=candidate,
                simulation_ticks=horizon_days,
                simulation_time_ms=elapsed_ms,
            )
            scored.append(scored_scenario)

            # Check diminishing returns
            improvement = bsc.final_score - best_final_score
            if i > 0 and improvement < self.MIN_IMPROVEMENT_THRESHOLD:
                logger.debug(
                    "Stopping early: improvement %.4f < threshold %.4f",
                    improvement, self.MIN_IMPROVEMENT_THRESHOLD,
                )
                break

            best_final_score = max(best_final_score, bsc.final_score)

            # Check satisficing
            if self._bsc.satisfices(bsc.final_score, baseline_score=0.0):
                logger.debug(
                    "Satisficing threshold met at candidate %d (score=%.4f)",
                    i, bsc.final_score,
                )
                break

        # Sort by final_score DESC
        scored.sort(key=lambda s: s.bsc.final_score, reverse=True)

        # Update scenario with best score
        if scored:
            best = scored[0]
            scenario.raw_bsc_score = best.bsc.raw_bsc_value
            scenario.compound_likelihood = best.bsc.compound_likelihood
            scenario.urgency_discount = best.bsc.urgency_discount
            scenario.final_score = best.bsc.final_score
            scenario.bsc_breakdown = best.bsc.to_dict()
            scenario.context_weights = self._bsc.compute_context_weights(context)

        scenario.status = "SCORED"
        scenario.scored_at = datetime.utcnow()
        self.db.flush()

        logger.info(
            "Evaluated scenario %d: %d candidates scored, best=%.4f",
            scenario.id, len(scored),
            scored[0].bsc.final_score if scored else 0.0,
        )
        return scored

    # -----------------------------------------------------------------------
    # Compare scenarios
    # -----------------------------------------------------------------------

    def compare_scenarios(
        self,
        scenario_ids: List[int],
    ) -> List[Dict[str, Any]]:
        """Compare multiple scenarios with BSC comparison table.

        Args:
            scenario_ids: List of AgentScenario IDs to compare

        Returns:
            List of scenario summaries sorted by final_score DESC,
            each containing BSC breakdown and action list.
        """
        scenarios = (
            self.db.query(AgentScenario)
            .filter(AgentScenario.id.in_(scenario_ids))
            .all()
        )

        comparison = []
        for s in scenarios:
            actions = (
                self.db.query(AgentScenarioAction)
                .filter(AgentScenarioAction.scenario_id == s.id)
                .all()
            )
            comparison.append({
                "scenario_id": s.id,
                "status": s.status,
                "trigger_trm_type": s.trigger_trm_type,
                "decision_level": s.decision_level,
                "raw_bsc_score": s.raw_bsc_score,
                "compound_likelihood": s.compound_likelihood,
                "urgency_discount": s.urgency_discount,
                "final_score": s.final_score,
                "bsc_breakdown": s.bsc_breakdown,
                "context_weights": s.context_weights,
                "actions": [a.to_dict() for a in actions],
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "scored_at": s.scored_at.isoformat() if s.scored_at else None,
            })

        comparison.sort(key=lambda c: c.get("final_score") or 0, reverse=True)
        return comparison

    # -----------------------------------------------------------------------
    # Promote / Reject
    # -----------------------------------------------------------------------

    def promote_scenario(self, scenario_id: int) -> AgentScenario:
        """Promote a winning scenario.

        Extracts decisions from the scenario and marks them for routing
        to responsible agents. Marks scenario as PROMOTED.

        Args:
            scenario_id: ID of the scenario to promote

        Returns:
            Updated AgentScenario

        Raises:
            ValueError: if scenario not found or not in SCORED status
        """
        scenario = self.db.query(AgentScenario).filter(
            AgentScenario.id == scenario_id,
        ).first()

        if not scenario:
            raise ValueError(f"Scenario {scenario_id} not found")
        if scenario.status not in ("SCORED", "CREATED"):
            raise ValueError(
                f"Cannot promote scenario in status {scenario.status} "
                f"(expected SCORED or CREATED)"
            )

        # Mark all actions as ACTIONED
        actions = (
            self.db.query(AgentScenarioAction)
            .filter(AgentScenarioAction.scenario_id == scenario_id)
            .all()
        )
        for action in actions:
            action.status = "ACTIONED"

        scenario.status = "PROMOTED"
        scenario.resolved_at = datetime.utcnow()

        # Update template priors (success)
        self._update_template_priors(actions, success=True)

        self.db.flush()
        logger.info(
            "Promoted scenario %d with %d actions",
            scenario_id, len(actions),
        )
        return scenario

    def reject_scenario(self, scenario_id: int) -> AgentScenario:
        """Reject a scenario. Retains for training data.

        Args:
            scenario_id: ID of the scenario to reject

        Returns:
            Updated AgentScenario

        Raises:
            ValueError: if scenario not found
        """
        scenario = self.db.query(AgentScenario).filter(
            AgentScenario.id == scenario_id,
        ).first()

        if not scenario:
            raise ValueError(f"Scenario {scenario_id} not found")

        # Mark all actions as REJECTED
        actions = (
            self.db.query(AgentScenarioAction)
            .filter(AgentScenarioAction.scenario_id == scenario_id)
            .all()
        )
        for action in actions:
            action.status = "REJECTED"

        scenario.status = "REJECTED"
        scenario.resolved_at = datetime.utcnow()

        # Update template priors (failure)
        self._update_template_priors(actions, success=False)

        self.db.flush()
        logger.info("Rejected scenario %d", scenario_id)
        return scenario

    # -----------------------------------------------------------------------
    # Full workflow: trigger -> candidates -> evaluate -> rank
    # -----------------------------------------------------------------------

    def run_scenario_evaluation(
        self,
        trigger_decision: Dict[str, Any],
        trigger_context: Dict[str, Any],
        decision_level: str = "execution",
        max_candidates: Optional[int] = None,
    ) -> Tuple[AgentScenario, List[BSCScoredScenario]]:
        """Full end-to-end scenario evaluation workflow.

        1. Create scenario
        2. Generate candidates from templates
        3. Evaluate each candidate via simulation
        4. Return ranked results

        Args:
            trigger_decision: TRM decision that triggered this
            trigger_context: Business context
            decision_level: Powell hierarchy level
            max_candidates: Override for max candidates (from level caps if None)

        Returns:
            Tuple of (scenario, scored_candidates)
        """
        # Create
        scenario = self.create_scenario(
            trigger_decision, trigger_context, decision_level,
        )

        # Generate candidates
        caps = LEVEL_CAPS.get(decision_level, LEVEL_CAPS["execution"])
        n_candidates = max_candidates or caps.max_candidates
        trm_type = trigger_decision.get("trm_type", "unknown")

        generator = CandidateGenerator(self.db, self.tenant_id)
        candidates = generator.generate_candidates(
            trm_type=trm_type,
            context=trigger_context,
            max_candidates=n_candidates,
        )

        if not candidates:
            scenario.status = "SCORED"
            scenario.scored_at = datetime.utcnow()
            scenario.final_score = 0.0
            self.db.flush()
            return scenario, []

        # Evaluate
        scored = self.evaluate_scenario(scenario, candidates, trigger_context)

        self.db.commit()
        return scenario, scored

    # -----------------------------------------------------------------------
    # Simulation helpers
    # -----------------------------------------------------------------------

    def _load_dag_chain(self):
        """Load the DAG chain from the SC config.

        Returns:
            Tuple of (site_configs, topo_order) for _DagChain construction.
        """
        from app.services.powell.simulation_calibration_service import _ConfigLoader

        loader = _ConfigLoader(self.db, self.config_id)
        site_configs, topo_order = loader.load()
        return site_configs, topo_order

    def _simulate_branch(
        self,
        site_configs: list,
        topo_order: list,
        actions: List[Dict[str, Any]],
        horizon_days: int,
        seed: int,
    ) -> Dict[str, Any]:
        """Simulate a branch by constructing a fresh _DagChain, injecting
        actions, and running forward for horizon_days.

        Args:
            site_configs: _SiteSimConfig list from _ConfigLoader
            topo_order: Topological site ordering
            actions: List of action dicts to inject
            horizon_days: Number of days to simulate
            seed: Random seed for reproducibility

        Returns:
            Aggregated simulation result dict.
        """
        from app.services.powell.simulation_calibration_service import _DagChain

        # Build a fresh chain for this branch
        chain = _DagChain(site_configs, topo_order, seed=seed)

        # Inject actions into the simulation state
        self._inject_actions(chain, actions)

        # Run simulation
        cumulative = {
            "total_cost": 0.0,
            "total_holding": 0.0,
            "total_backlog": 0.0,
            "fill_rates": [],
            "stockout_days": 0,
            "days_cover_list": [],
        }

        for day in range(horizon_days):
            tick_result = chain.tick()

            cumulative["total_cost"] += tick_result["total_cost"]
            cumulative["total_holding"] += tick_result["total_holding"]
            cumulative["total_backlog"] += tick_result["total_backlog"]
            cumulative["fill_rates"].append(tick_result["avg_fill_rate"])
            if tick_result.get("any_stockout", False):
                cumulative["stockout_days"] += 1
            cumulative["days_cover_list"].append(tick_result["network_avg_days_cover"])

        # Aggregate results
        import statistics
        fill_rates = cumulative["fill_rates"]
        days_cover = cumulative["days_cover_list"]

        return {
            "total_cost": cumulative["total_cost"],
            "total_holding": cumulative["total_holding"],
            "total_backlog": cumulative["total_backlog"],
            "avg_fill_rate": statistics.mean(fill_rates) if fill_rates else 1.0,
            "any_stockout": cumulative["stockout_days"] > 0,
            "network_avg_days_cover": statistics.mean(days_cover) if days_cover else 15.0,
            "stockout_days": cumulative["stockout_days"],
            "horizon_days": horizon_days,
        }

    def _inject_actions(
        self,
        chain: Any,  # _DagChain
        actions: List[Dict[str, Any]],
    ) -> None:
        """Inject proposed actions into the simulation chain state.

        Actions modify the _DagChain's initial conditions:
        - CREATE_PO / RELEASE_TO: Add to pipeline (in-transit)
        - PARTIAL_FULFILL / BACKORDER: Adjust initial inventory/backlog
        - TRANSFER: Move units between sites
        - DELAY_PROMISE: Reduce immediate demand pressure
        - RELEASE_MO: Add planned production to pipeline
        - SUBCONTRACT: Add external supply to pipeline
        """
        for action in actions:
            action_type = action.get("action_type", "")
            params = action.get("action_params") or {}

            site_id = params.get("site_id")
            quantity = float(params.get("quantity", 0))

            if quantity <= 0:
                continue

            if action_type in ("CREATE_PO", "RELEASE_MO", "SUBCONTRACT"):
                # Add supply to the pipeline at the relevant site
                node = self._find_node(chain, site_id)
                if node:
                    # Estimate lead time based on action type
                    if action_type == "CREATE_PO":
                        lt = max(1, int(node.cfg.lead_time_days))
                        if params.get("expedite"):
                            lt = max(1, lt // 2)
                    elif action_type == "RELEASE_MO":
                        lt = max(1, int(node.cfg.lead_time_days * 0.7))
                    else:  # SUBCONTRACT
                        lt = max(2, int(node.cfg.lead_time_days * 1.3))
                    node._pipeline.append((quantity, lt))

            elif action_type == "RELEASE_TO" or action_type == "CONSOLIDATE_TO":
                # Transfer: add to pipeline of destination site
                to_site_id = params.get("to_site_id")
                from_site_id = params.get("from_site_id")
                to_node = self._find_node(chain, to_site_id)
                from_node = self._find_node(chain, from_site_id)
                if to_node:
                    lt = max(1, int(to_node.cfg.lead_time_days))
                    if params.get("mode") == "expedited":
                        lt = max(1, lt // 2)
                    to_node._pipeline.append((quantity, lt))
                if from_node:
                    from_node.inventory = max(0, from_node.inventory - quantity)

            elif action_type == "TRANSFER":
                # Rebalancing transfer
                to_site_id = params.get("to_site_id")
                from_site_id = params.get("from_site_id")
                to_node = self._find_node(chain, to_site_id)
                from_node = self._find_node(chain, from_site_id)
                if to_node:
                    lt = max(1, int(to_node.cfg.lead_time_days))
                    if params.get("expedite"):
                        lt = max(1, lt // 2)
                    to_node._pipeline.append((quantity, lt))
                if from_node:
                    from_node.inventory = max(0, from_node.inventory - quantity)

            elif action_type == "PARTIAL_FULFILL":
                # Immediately reduce inventory (fulfill from stock)
                node = self._find_node(chain, site_id)
                if node:
                    node.inventory = max(0, node.inventory - quantity)

            elif action_type == "BACKORDER":
                # Add to backlog
                node = self._find_node(chain, site_id)
                if node:
                    node.backlog += quantity

            elif action_type == "DELAY_PROMISE":
                # Reduce effective demand pressure by clearing some backlog
                node = self._find_node(chain, site_id)
                if node:
                    delay_relief = min(node.backlog, quantity * 0.3)
                    node.backlog = max(0, node.backlog - delay_relief)

    def _find_node(self, chain: Any, site_id: Optional[int]) -> Optional[Any]:
        """Find a simulation node by site_id, with fallback."""
        if site_id is None:
            return None

        # Try integer lookup
        if isinstance(site_id, int):
            node = chain.nodes.get(site_id)
            if node:
                return node

        # Try string-to-int conversion
        try:
            sid = int(site_id)
            return chain.nodes.get(sid)
        except (ValueError, TypeError):
            pass

        return None

    def _estimate_execution_days(self, actions: List[Dict[str, Any]]) -> int:
        """Estimate total execution time for a set of actions.

        Sum of estimated lead times for all supply-generating actions.
        """
        total_days = 0
        for action in actions:
            action_type = action.get("action_type", "")
            params = action.get("action_params") or {}

            if action_type in ("CREATE_PO", "RELEASE_MO", "SUBCONTRACT"):
                total_days = max(total_days, 7)  # Typical PO/MO lead time
            elif action_type in ("RELEASE_TO", "TRANSFER", "CONSOLIDATE_TO"):
                total_days = max(total_days, 3)  # Typical transfer time
            elif action_type == "DELAY_PROMISE":
                total_days = max(total_days, params.get("delay_days", 5))

        return total_days

    def _update_template_priors(
        self,
        actions: List[AgentScenarioAction],
        success: bool,
    ) -> None:
        """Update Beta posteriors on templates used by scenario actions.

        Looks up the template_key from action_params and updates the
        corresponding ScenarioTemplate.
        """
        from app.models.agent_scenario import ScenarioTemplate

        seen_templates = set()
        for action in actions:
            params = action.action_params or {}
            # The template_id might be stashed in action_params by the generator
            template_key = params.get("template_key")
            if not template_key or template_key in seen_templates:
                continue
            seen_templates.add(template_key)

            template = (
                self.db.query(ScenarioTemplate)
                .filter(
                    ScenarioTemplate.template_key == template_key,
                    (ScenarioTemplate.tenant_id == self.tenant_id)
                    | (ScenarioTemplate.tenant_id.is_(None)),
                )
                .first()
            )
            if template:
                if success:
                    template.alpha = (template.alpha or 1.0) + 1.0
                else:
                    template.beta_param = (template.beta_param or 1.0) + 1.0

    # -----------------------------------------------------------------------
    # Query helpers
    # -----------------------------------------------------------------------

    def list_scenarios(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[AgentScenario]:
        """List scenarios for this config, optionally filtered by status."""
        query = self.db.query(AgentScenario).filter(
            AgentScenario.config_id == self.config_id,
            AgentScenario.tenant_id == self.tenant_id,
        )
        if status:
            query = query.filter(AgentScenario.status == status)
        return query.order_by(AgentScenario.created_at.desc()).limit(limit).all()

    def get_scenario(self, scenario_id: int) -> Optional[AgentScenario]:
        """Get a single scenario by ID."""
        return self.db.query(AgentScenario).filter(
            AgentScenario.id == scenario_id,
            AgentScenario.tenant_id == self.tenant_id,
        ).first()
