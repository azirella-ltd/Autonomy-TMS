"""
Tests for Planning Scenarios — ScenarioTreeService + HiveWhatIfEngine.

Covers: branch creation, tree traversal, evaluation, promotion/pruning,
comparison, what-if engine, balanced scorecard computation.
"""

import pytest

from app.models.planning_scenario import (
    PlanningScenario,
    ScenarioDecisionRecord,
    ScenarioStatus,
)
from app.services.scenario_tree_service import ScenarioTreeService
from app.services.hive_what_if_engine import HiveWhatIfEngine, BalancedScorecard


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def service():
    """In-memory ScenarioTreeService."""
    return ScenarioTreeService(db=None)


@pytest.fixture
def populated_tree(service):
    """A tree with root + 3 branches (A, B, C) + 2 sub-branches (B1, B2).

    Structure:
        Root
        ├── A (ss_mult=1.1)
        ├── B (demand_change=10)
        │   ├── B1 (lead_time=+5)
        │   └── B2 (lead_time=-5)
        └── C (ss_mult=0.9)
    """
    root = service.create_root("Baseline", config_id=1)
    a = service.create_branch(root.id, "High Safety Stock", {"safety_stock_multiplier": 1.1})
    b = service.create_branch(root.id, "Demand Surge", {"demand_change_pct": 10})
    c = service.create_branch(root.id, "Low Safety Stock", {"safety_stock_multiplier": 0.9})
    b1 = service.create_branch(b.id, "Surge + Long Lead", {"lead_time_change_pct": 5})
    b2 = service.create_branch(b.id, "Surge + Short Lead", {"lead_time_change_pct": -5})
    return {
        "root": root, "a": a, "b": b, "c": c, "b1": b1, "b2": b2,
        "service": service,
    }


@pytest.fixture
def engine():
    """Synthetic HiveWhatIfEngine (no real TRM executors)."""
    return HiveWhatIfEngine(site_key="test", seed=42)


# ---------------------------------------------------------------------------
# PlanningScenario Model
# ---------------------------------------------------------------------------

class TestPlanningScenarioModel:
    def test_status_enum(self):
        assert ScenarioStatus.DRAFT == "DRAFT"
        assert ScenarioStatus.PROMOTED == "PROMOTED"
        assert len(ScenarioStatus) == 8

    def test_to_dict(self):
        s = PlanningScenario(
            name="Test",
            status=ScenarioStatus.DRAFT,
            variable_deltas={"x": 1},
        )
        d = s.to_dict()
        assert d["name"] == "Test"
        assert d["status"] == "DRAFT"
        assert d["variable_deltas"] == {"x": 1}


# ---------------------------------------------------------------------------
# Branch Operations
# ---------------------------------------------------------------------------

class TestBranchOperations:
    def test_create_root(self, service):
        root = service.create_root("Baseline", config_id=1)
        assert root.id is not None
        assert root.parent_scenario_id is None
        assert root.depth == 0
        assert root.status == ScenarioStatus.DRAFT

    def test_create_branch(self, service):
        root = service.create_root("Baseline")
        branch = service.create_branch(root.id, "Branch A", {"x": 1})
        assert branch.parent_scenario_id == root.id
        assert branch.root_scenario_id == root.id
        assert branch.depth == 1
        assert branch.variable_deltas == {"x": 1}

    def test_nested_branch(self, service):
        root = service.create_root("Baseline")
        a = service.create_branch(root.id, "A")
        b = service.create_branch(a.id, "B")
        assert b.depth == 2
        assert b.root_scenario_id == root.id

    def test_branch_invalid_parent(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.create_branch(999, "Bad", {})


# ---------------------------------------------------------------------------
# Tree Traversal
# ---------------------------------------------------------------------------

class TestTreeTraversal:
    def test_get_tree(self, populated_tree):
        service = populated_tree["service"]
        root = populated_tree["root"]
        tree = service.get_tree(root.id)
        assert len(tree) == 6  # root + A + B + C + B1 + B2

    def test_get_tree_nonexistent(self, service):
        tree = service.get_tree(999)
        assert tree == []

    def test_tree_structure(self, populated_tree):
        service = populated_tree["service"]
        root = populated_tree["root"]
        tree = service.get_tree(root.id)
        names = {t["name"] for t in tree}
        assert "Baseline" in names
        assert "High Safety Stock" in names
        assert "Surge + Long Lead" in names


# ---------------------------------------------------------------------------
# Effective Deltas
# ---------------------------------------------------------------------------

class TestEffectiveDeltas:
    def test_root_deltas_empty(self, populated_tree):
        service = populated_tree["service"]
        root = populated_tree["root"]
        deltas = service._get_effective_deltas(root)
        assert deltas == {}

    def test_single_branch_deltas(self, populated_tree):
        service = populated_tree["service"]
        a = populated_tree["a"]
        deltas = service._get_effective_deltas(a)
        assert deltas == {"safety_stock_multiplier": 1.1}

    def test_nested_deltas_merge(self, populated_tree):
        service = populated_tree["service"]
        b1 = populated_tree["b1"]
        deltas = service._get_effective_deltas(b1)
        assert deltas == {"demand_change_pct": 10, "lead_time_change_pct": 5}

    def test_nested_deltas_override(self, service):
        """Child deltas override parent for same key."""
        root = service.create_root("R")
        parent = service.create_branch(root.id, "P", {"x": 1, "y": 2})
        child = service.create_branch(parent.id, "C", {"x": 10})
        deltas = service._get_effective_deltas(child)
        assert deltas == {"x": 10, "y": 2}


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

class TestEvaluation:
    def test_evaluate_updates_status(self, populated_tree):
        service = populated_tree["service"]
        a = populated_tree["a"]
        service.evaluate(a.id)
        assert a.status == ScenarioStatus.EVALUATED

    def test_evaluate_populates_scorecard(self, populated_tree):
        service = populated_tree["service"]
        a = populated_tree["a"]
        scorecard = service.evaluate(a.id)
        assert "financial" in scorecard
        assert "customer" in scorecard
        assert "operational" in scorecard
        assert "strategic" in scorecard

    def test_evaluate_computes_net_benefit(self, populated_tree):
        service = populated_tree["service"]
        a = populated_tree["a"]
        service.evaluate(a.id)
        assert a.net_benefit is not None
        assert isinstance(a.net_benefit, float)

    def test_evaluate_nonexistent(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.evaluate(999)

    def test_evaluate_with_engine(self, populated_tree, engine):
        service = populated_tree["service"]
        a = populated_tree["a"]
        scorecard = service.evaluate(a.id, engine=engine, num_periods=6)
        assert "financial" in scorecard
        assert a.balanced_scorecard is not None

    def test_different_deltas_different_scorecards(self, populated_tree):
        service = populated_tree["service"]
        a = populated_tree["a"]
        c = populated_tree["c"]
        sc_a = service.evaluate(a.id)
        sc_c = service.evaluate(c.id)
        # Different deltas should produce different scorecards
        assert sc_a != sc_c


# ---------------------------------------------------------------------------
# Promotion & Pruning
# ---------------------------------------------------------------------------

class TestPromotion:
    def test_promote_changes_status(self, populated_tree):
        service = populated_tree["service"]
        a = populated_tree["a"]
        service.promote(a.id, rationale="Best cost reduction")
        assert a.status == ScenarioStatus.PROMOTED

    def test_promote_prunes_siblings(self, populated_tree):
        service = populated_tree["service"]
        a = populated_tree["a"]
        b = populated_tree["b"]
        c = populated_tree["c"]
        service.promote(a.id)
        assert b.status == ScenarioStatus.PRUNED
        assert c.status == ScenarioStatus.PRUNED

    def test_promote_prunes_descendants_of_siblings(self, populated_tree):
        service = populated_tree["service"]
        a = populated_tree["a"]
        b1 = populated_tree["b1"]
        b2 = populated_tree["b2"]
        service.promote(a.id)
        assert b1.status == ScenarioStatus.PRUNED
        assert b2.status == ScenarioStatus.PRUNED

    def test_promote_creates_decision_record(self, populated_tree):
        service = populated_tree["service"]
        a = populated_tree["a"]
        record = service.promote(a.id, rationale="Best", decided_by="admin")
        assert record.promoted_scenario_id == a.id
        assert record.ranking_rationale == "Best"
        assert record.decided_by == "admin"
        assert len(record.pruned_sibling_ids) == 2  # B and C

    def test_promote_nonexistent(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.promote(999)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

class TestComparison:
    def test_compare_evaluated_scenarios(self, populated_tree):
        service = populated_tree["service"]
        a = populated_tree["a"]
        c = populated_tree["c"]
        service.evaluate(a.id)
        service.evaluate(c.id)
        comparison = service.compare([a.id, c.id])
        assert a.id in comparison
        assert c.id in comparison
        assert "scorecard" in comparison[a.id]
        assert "net_benefit" in comparison[a.id]

    def test_compare_unevaluated_excluded(self, populated_tree):
        service = populated_tree["service"]
        a = populated_tree["a"]
        b = populated_tree["b"]
        service.evaluate(a.id)
        # b not evaluated
        comparison = service.compare([a.id, b.id])
        assert a.id in comparison
        assert b.id not in comparison


# ---------------------------------------------------------------------------
# HiveWhatIfEngine
# ---------------------------------------------------------------------------

class TestHiveWhatIfEngine:
    def test_synthetic_evaluation(self, engine):
        scorecard = engine.evaluate({"safety_stock_multiplier": 1.1}, num_periods=12)
        assert "financial" in scorecard
        assert "customer" in scorecard
        assert isinstance(scorecard["financial"]["total_cost"], float)

    def test_cache_hit(self, engine):
        deltas = {"x": 1}
        sc1 = engine.evaluate(deltas)
        sc2 = engine.evaluate(deltas)
        assert sc1 == sc2

    def test_cache_miss_different_deltas(self, engine):
        sc1 = engine.evaluate({"safety_stock_multiplier": 1.2})
        sc2 = engine.evaluate({"safety_stock_multiplier": 0.8})
        assert sc1 != sc2

    def test_clear_cache(self, engine):
        engine.evaluate({"x": 1})
        engine.clear_cache()
        assert len(engine._cache) == 0

    def test_no_deltas(self, engine):
        scorecard = engine.evaluate()
        assert "financial" in scorecard


class TestBalancedScorecard:
    def test_to_dict(self):
        sc = BalancedScorecard(
            financial={"cost": 100},
            customer={"otif": 0.95},
        )
        d = sc.to_dict()
        assert d["financial"]["cost"] == 100
        assert d["customer"]["otif"] == 0.95

    def test_net_benefit(self):
        sc = BalancedScorecard(
            financial={"a": 0.5},
            customer={"b": 0.8},
            operational={"c": 0.6},
            strategic={"d": 0.7},
        )
        nb = sc.net_benefit
        assert isinstance(nb, float)
        assert 0 < nb < 1

    def test_empty_scorecard(self):
        sc = BalancedScorecard()
        assert sc.net_benefit == 0.0


# ---------------------------------------------------------------------------
# Integration: Full Workflow
# ---------------------------------------------------------------------------

class TestFullWorkflow:
    def test_branch_evaluate_promote(self):
        """End-to-end: create tree, evaluate all, promote best."""
        svc = ScenarioTreeService(db=None)
        engine = HiveWhatIfEngine(seed=42)

        # Create tree
        root = svc.create_root("Baseline", config_id=1)
        a = svc.create_branch(root.id, "Option A", {"safety_stock_multiplier": 1.1})
        b = svc.create_branch(root.id, "Option B", {"safety_stock_multiplier": 0.9})

        # Evaluate
        sc_a = svc.evaluate(a.id, engine=engine)
        sc_b = svc.evaluate(b.id, engine=engine)

        # Both should have scorecards
        assert a.balanced_scorecard is not None
        assert b.balanced_scorecard is not None

        # Promote the one with higher net benefit
        winner = a if a.net_benefit >= b.net_benefit else b
        loser = b if winner == a else a

        record = svc.promote(winner.id, rationale="Higher net benefit")
        assert winner.status == ScenarioStatus.PROMOTED
        assert loser.status == ScenarioStatus.PRUNED
        assert loser.id in record.pruned_sibling_ids

        # Tree should reflect statuses
        tree = svc.get_tree(root.id)
        statuses = {t["name"]: t["status"] for t in tree}
        assert statuses[winner.name] == "PROMOTED"
        assert statuses[loser.name] == "PRUNED"
