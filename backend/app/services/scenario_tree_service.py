"""
Scenario Tree Service — Branch, evaluate, promote, and compare planning scenarios.

Provides the orchestration layer for planning scenario trees, delegating
what-if evaluation to HiveWhatIfEngine and supply chain config management
to ScenarioBranchingService.

Architecture reference: TRM_HIVE_ARCHITECTURE.md Sections 11-12
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

from app.models.planning_scenario import (
    PlanningScenario,
    ScenarioDecisionRecord,
    ScenarioStatus,
)
from app.services.authorization_protocol import (
    ActionCategory,
    get_action_category,
    AgentRole,
)

logger = logging.getLogger(__name__)


class ScenarioTreeService:
    """Manages planning scenario trees with branching, evaluation, and promotion.

    Works independently of the database when ``db`` is None (for testing
    and in-memory usage).  When a SQLAlchemy session is provided, scenarios
    are persisted.

    Args:
        db: Optional SQLAlchemy session for persistence.
    """

    def __init__(self, db=None):
        self.db = db
        # In-memory store (used when db is None)
        self._scenarios: Dict[int, PlanningScenario] = {}
        self._decisions: List[ScenarioDecisionRecord] = []
        self._next_id = 1

    # ------------------------------------------------------------------
    # Branch operations
    # ------------------------------------------------------------------

    def create_root(
        self,
        name: str,
        config_id: Optional[int] = None,
        description: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> PlanningScenario:
        """Create a root scenario (baseline).

        Args:
            name: Scenario name.
            config_id: Optional supply chain config ID.
            description: Optional description.
            created_by: Optional creator identifier.

        Returns:
            The created root PlanningScenario.
        """
        scenario = PlanningScenario(
            name=name,
            description=description,
            config_id=config_id,
            parent_scenario_id=None,
            root_scenario_id=None,
            depth=0,
            status=ScenarioStatus.DRAFT,
            variable_deltas={},
            created_by=created_by,
            created_at=datetime.utcnow(),
        )
        return self._persist(scenario)

    def create_branch(
        self,
        parent_id: int,
        name: str,
        variable_deltas: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> PlanningScenario:
        """Create a child scenario branching from a parent.

        Args:
            parent_id: ID of the parent scenario.
            name: Name for the new branch.
            variable_deltas: Overrides to apply on top of parent.
            description: Optional description.
            created_by: Optional creator identifier.

        Returns:
            The created branch PlanningScenario.

        Raises:
            ValueError: If parent does not exist.
        """
        parent = self._get(parent_id)
        if parent is None:
            raise ValueError(f"Parent scenario {parent_id} not found")

        root_id = parent.root_scenario_id or parent.id

        scenario = PlanningScenario(
            name=name,
            description=description,
            config_id=parent.config_id,
            parent_scenario_id=parent_id,
            root_scenario_id=root_id,
            depth=parent.depth + 1,
            status=ScenarioStatus.DRAFT,
            variable_deltas=variable_deltas or {},
            created_by=created_by,
            created_at=datetime.utcnow(),
        )
        return self._persist(scenario)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        scenario_id: int,
        engine=None,
        num_periods: int = 12,
    ) -> Dict[str, Any]:
        """Evaluate a scenario using HiveWhatIfEngine.

        Args:
            scenario_id: Scenario to evaluate.
            engine: Optional HiveWhatIfEngine instance.
            num_periods: Number of simulation periods.

        Returns:
            Balanced scorecard dict.
        """
        scenario = self._get(scenario_id)
        if scenario is None:
            raise ValueError(f"Scenario {scenario_id} not found")

        scenario.status = ScenarioStatus.EVALUATING
        self._save(scenario)

        start = time.time()

        # Collect effective deltas (merge up to root)
        effective_deltas = self._get_effective_deltas(scenario)

        # Run what-if engine
        if engine is not None:
            scorecard = engine.evaluate(
                variable_deltas=effective_deltas,
                num_periods=num_periods,
            )
        else:
            # Synthetic scorecard for testing
            scorecard = self._synthetic_scorecard(effective_deltas)

        duration_ms = (time.time() - start) * 1000

        # Compute net benefit (sum of weighted metrics)
        net_benefit = self._compute_net_benefit(scorecard)

        # Update scenario
        scenario.balanced_scorecard = scorecard
        scenario.net_benefit = net_benefit
        scenario.evaluation_duration_ms = duration_ms
        scenario.status = ScenarioStatus.EVALUATED
        self._save(scenario)

        return scorecard

    # ------------------------------------------------------------------
    # Promotion & Pruning
    # ------------------------------------------------------------------

    def promote(
        self,
        scenario_id: int,
        rationale: Optional[str] = None,
        decided_by: Optional[str] = None,
        auth_service=None,
    ) -> ScenarioDecisionRecord:
        """Promote a scenario and prune its siblings.

        When an ``auth_service`` is provided, the promotion is checked
        against authority boundaries.  High net-benefit promotions are
        auto-authorized; borderline ones require human review.

        Args:
            scenario_id: Scenario to promote.
            rationale: Explanation for the selection.
            decided_by: Decision-maker identifier.
            auth_service: Optional AuthorizationService for gating.

        Returns:
            ScenarioDecisionRecord capturing the decision.

        Raises:
            ValueError: If scenario not found, or authorization denied.
        """
        scenario = self._get(scenario_id)
        if scenario is None:
            raise ValueError(f"Scenario {scenario_id} not found")

        # --- Authorization gate ---
        if auth_service is not None:
            auth_result = self._check_promote_authority(
                scenario, auth_service, decided_by,
            )
            if auth_result and auth_result.get("needs_review"):
                raise ValueError(
                    f"Promotion requires human review. "
                    f"Authorization thread: {auth_result.get('thread_id')}"
                )
            if auth_result and auth_result.get("denied"):
                raise ValueError(
                    f"Promotion denied: net_benefit {scenario.net_benefit:.3f} "
                    f"below threshold"
                )

        # Find siblings (same parent, different ID)
        siblings = self._get_siblings(scenario)
        pruned_ids = []

        for sibling in siblings:
            if sibling.id != scenario_id:
                sibling.status = ScenarioStatus.PRUNED
                self._save(sibling)
                pruned_ids.append(sibling.id)
                # Recursively prune children of pruned siblings
                self._prune_descendants(sibling.id)

        scenario.status = ScenarioStatus.PROMOTED
        self._save(scenario)

        # Build scorecard comparison
        scorecard_comparison = {}
        if scenario.balanced_scorecard:
            scorecard_comparison[scenario_id] = scenario.balanced_scorecard
        for sid in pruned_ids:
            pruned = self._get(sid)
            if pruned and pruned.balanced_scorecard:
                scorecard_comparison[sid] = pruned.balanced_scorecard

        record = ScenarioDecisionRecord(
            promoted_scenario_id=scenario_id,
            pruned_sibling_ids=pruned_ids,
            ranking_rationale=rationale,
            scorecard_comparison=scorecard_comparison,
            decided_by=decided_by,
            decided_at=datetime.utcnow(),
        )
        self._persist_decision(record)

        return record

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def get_tree(self, root_id: int) -> List[Dict[str, Any]]:
        """Get the full tree rooted at root_id.

        Returns:
            List of scenario dicts in the tree.
        """
        result = []
        root = self._get(root_id)
        if root is None:
            return result

        result.append(root.to_dict())
        self._collect_descendants(root_id, result)
        return result

    def compare(self, scenario_ids: List[int]) -> Dict[str, Any]:
        """Compare balanced scorecards across scenarios.

        Args:
            scenario_ids: List of scenario IDs to compare.

        Returns:
            Dict mapping scenario_id to balanced scorecard.
        """
        comparison = {}
        for sid in scenario_ids:
            scenario = self._get(sid)
            if scenario and scenario.balanced_scorecard:
                comparison[sid] = {
                    "name": scenario.name,
                    "status": scenario.status.value if scenario.status else None,
                    "net_benefit": scenario.net_benefit,
                    "scorecard": scenario.balanced_scorecard,
                }
        return comparison

    def get(self, scenario_id: int) -> Optional[PlanningScenario]:
        """Get a single scenario by ID."""
        return self._get(scenario_id)

    # ------------------------------------------------------------------
    # Authorization helpers
    # ------------------------------------------------------------------

    def _check_promote_authority(
        self,
        scenario: PlanningScenario,
        auth_service,
        decided_by: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Check whether promoting this scenario requires authorization.

        Uses the authorization service auto-resolution logic:
        - net_benefit >> threshold → auto-authorize (returns None)
        - net_benefit near threshold → needs human review
        - net_benefit << threshold → auto-deny

        Returns:
            None if auto-authorized, or dict with ``needs_review``/``denied`` keys.
        """
        benefit_threshold = 0.05  # Minimum net benefit for auto-promotion

        net_benefit = scenario.net_benefit or 0.0

        # High confidence: auto-authorize
        if net_benefit > benefit_threshold * 2.0:
            logger.info(
                f"Scenario {scenario.id} auto-authorized for promotion "
                f"(net_benefit={net_benefit:.3f} >> threshold={benefit_threshold})"
            )
            return None

        # Low confidence: auto-deny
        if net_benefit < benefit_threshold * 0.5:
            logger.info(
                f"Scenario {scenario.id} auto-denied for promotion "
                f"(net_benefit={net_benefit:.3f} << threshold={benefit_threshold})"
            )
            return {"denied": True}

        # Borderline: create authorization thread for human review
        try:
            thread = auth_service.submit_request(
                requesting_agent=decided_by or "scenario_planner",
                target_agent="planning_director",
                proposed_action={
                    "action_type": "promote_scenario",
                    "scenario_id": scenario.id,
                    "scenario_name": scenario.name,
                },
                balanced_scorecard=scenario.balanced_scorecard,
                net_benefit=net_benefit,
                benefit_threshold=benefit_threshold,
                justification=f"Promote scenario '{scenario.name}' with net_benefit={net_benefit:.3f}",
                priority="MEDIUM",
                scenario_id=scenario.id,
            )
            logger.info(
                f"Scenario {scenario.id} promotion requires review "
                f"(thread_id={thread.thread_id})"
            )
            return {"needs_review": True, "thread_id": thread.thread_id}
        except Exception as e:
            logger.warning(f"Authorization service error: {e}; auto-authorizing")
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_effective_deltas(self, scenario: PlanningScenario) -> Dict[str, Any]:
        """Walk up the tree and merge all variable_deltas."""
        deltas = {}
        current = scenario
        chain = []
        while current is not None:
            chain.append(current)
            if current.parent_scenario_id is not None:
                current = self._get(current.parent_scenario_id)
            else:
                current = None

        # Apply from root down (root first, leaf last)
        for s in reversed(chain):
            if s.variable_deltas:
                deltas.update(s.variable_deltas)
        return deltas

    def _compute_net_benefit(self, scorecard: Dict[str, Any]) -> float:
        """Compute a scalar net benefit from balanced scorecard.

        Uses equal weighting across the four BSC quadrants.
        """
        weights = {
            "financial": 0.3,
            "customer": 0.3,
            "operational": 0.25,
            "strategic": 0.15,
        }
        total = 0.0
        for quadrant, weight in weights.items():
            metrics = scorecard.get(quadrant, {})
            if isinstance(metrics, dict) and metrics:
                # Average normalized metrics in quadrant
                values = [v for v in metrics.values() if isinstance(v, (int, float))]
                if values:
                    total += weight * (sum(values) / len(values))
        return total

    def _synthetic_scorecard(self, deltas: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a synthetic balanced scorecard for testing."""
        import hashlib
        import json
        seed = int(hashlib.md5(json.dumps(deltas, sort_keys=True).encode()).hexdigest()[:8], 16)
        rng_val = (seed % 1000) / 1000.0

        return {
            "financial": {
                "total_cost_reduction": 0.1 + rng_val * 0.2,
                "working_capital_improvement": 0.05 + rng_val * 0.1,
            },
            "customer": {
                "otif_improvement": 0.02 + rng_val * 0.08,
                "fill_rate": 0.92 + rng_val * 0.05,
            },
            "operational": {
                "inventory_turns_improvement": 0.1 + rng_val * 0.15,
                "bullwhip_reduction": 0.05 + rng_val * 0.1,
            },
            "strategic": {
                "flexibility_score": 0.6 + rng_val * 0.3,
                "resilience_score": 0.5 + rng_val * 0.4,
            },
        }

    def _get_siblings(self, scenario: PlanningScenario) -> List[PlanningScenario]:
        """Get all scenarios with the same parent."""
        parent_id = scenario.parent_scenario_id
        if parent_id is None:
            return [scenario]

        if self.db is not None:
            return (
                self.db.query(PlanningScenario)
                .filter(PlanningScenario.parent_scenario_id == parent_id)
                .all()
            )
        return [
            s for s in self._scenarios.values()
            if s.parent_scenario_id == parent_id
        ]

    def _prune_descendants(self, parent_id: int):
        """Recursively prune all descendants of a scenario."""
        children = self._get_children(parent_id)
        for child in children:
            child.status = ScenarioStatus.PRUNED
            self._save(child)
            self._prune_descendants(child.id)

    def _get_children(self, parent_id: int) -> List[PlanningScenario]:
        """Get direct children of a scenario."""
        if self.db is not None:
            return (
                self.db.query(PlanningScenario)
                .filter(PlanningScenario.parent_scenario_id == parent_id)
                .all()
            )
        return [
            s for s in self._scenarios.values()
            if s.parent_scenario_id == parent_id
        ]

    def _collect_descendants(self, parent_id: int, result: List[Dict]):
        """Recursively collect all descendants."""
        for child in self._get_children(parent_id):
            result.append(child.to_dict())
            self._collect_descendants(child.id, result)

    # ------------------------------------------------------------------
    # Persistence helpers (in-memory or DB)
    # ------------------------------------------------------------------

    def _persist(self, scenario: PlanningScenario) -> PlanningScenario:
        if self.db is not None:
            self.db.add(scenario)
            self.db.flush()
        else:
            scenario.id = self._next_id
            self._next_id += 1
            if scenario.root_scenario_id is None and scenario.parent_scenario_id is None:
                scenario.root_scenario_id = scenario.id
            self._scenarios[scenario.id] = scenario
        return scenario

    def _persist_decision(self, record: ScenarioDecisionRecord):
        if self.db is not None:
            self.db.add(record)
            self.db.flush()
        else:
            self._decisions.append(record)

    def _get(self, scenario_id: int) -> Optional[PlanningScenario]:
        if self.db is not None:
            return self.db.query(PlanningScenario).get(scenario_id)
        return self._scenarios.get(scenario_id)

    def _save(self, scenario: PlanningScenario):
        if self.db is not None:
            self.db.add(scenario)
            self.db.flush()
        else:
            self._scenarios[scenario.id] = scenario
