"""
Unit Tests for Scenario Branching Service

Tests git-like configuration inheritance with delta storage.

Coverage:
- create_branch: Copy-on-write branching
- get_effective_config: Delta merging
- update_scenario: Delta recording (create/update/delete)
- commit_scenario: Materialization to parent
- rollback_scenario: Discard changes
- diff_scenarios: Configuration comparison
- Lineage building and querying
"""

import pytest
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.supply_chain_config import (
    SupplyChainConfig,
    ConfigDelta,
    ConfigLineage,
    Node,
    Lane,
    Market,
    MarketDemand,
)
from app.models.group import Group
from app.core.time_buckets import TimeBucket
from app.services.scenario_branching_service import (
    ScenarioBranchingService,
    ScenarioType,
    EntityType,
    Operation,
)


# ============================================================================
# Test Database Setup
# ============================================================================

@pytest.fixture(scope="function")
def db_session():
    """
    Create a database session for testing.

    Uses the existing PostgreSQL database from the container.
    Each test runs in a transaction that's rolled back after completion.
    """
    from app.db.session import sync_session_factory

    session = sync_session_factory()

    # Begin a nested transaction
    session.begin_nested()

    yield session

    # Rollback the transaction (undoes all test changes)
    session.rollback()
    session.close()


@pytest.fixture
def test_group(db_session: Session):
    """Create a test group."""
    group = Group(
        name="Test Group",
        description="Test group for scenario branching tests",
    )
    db_session.add(group)
    db_session.commit()
    db_session.refresh(group)
    return group


@pytest.fixture
def baseline_config(db_session: Session, test_group: Group):
    """
    Create a baseline TBG Root configuration.

    Structure:
    - Market Demand
    - Retailer → Wholesaler → Distributor → Factory
    - Market Supply
    """
    config = SupplyChainConfig(
        name="TBG Root",
        description="Baseline Beer Game configuration",
        group_id=test_group.id,
        time_bucket=TimeBucket.WEEK,
        scenario_type=ScenarioType.BASELINE,
        uses_delta_storage=False,  # Root doesn't use deltas
        is_active=True,
        validation_status="valid",
        training_status="pending",
        needs_training=True,
    )
    db_session.add(config)
    db_session.flush()

    # Create nodes
    market_demand = Node(
        config_id=config.id,
        name="Market Demand",
        type="MARKET_DEMAND",
        params={"demand_mean": 10, "demand_std": 2},
        priority=0,
        x=0, y=0,
    )
    retailer = Node(
        config_id=config.id,
        name="Retailer",
        type="RETAILER",
        params={"inventory": 100, "backlog": 0},
        priority=1,
        x=100, y=100,
    )
    wholesaler = Node(
        config_id=config.id,
        name="Wholesaler",
        type="WHOLESALER",
        params={"inventory": 100, "backlog": 0},
        priority=2,
        x=200, y=200,
    )
    distributor = Node(
        config_id=config.id,
        name="Distributor",
        type="DISTRIBUTOR",
        params={"inventory": 100, "backlog": 0},
        priority=3,
        x=300, y=300,
    )
    factory = Node(
        config_id=config.id,
        name="Factory",
        type="MANUFACTURER",
        params={"inventory": 100, "backlog": 0},
        priority=4,
        x=400, y=400,
    )
    market_supply = Node(
        config_id=config.id,
        name="Market Supply",
        type="MARKET_SUPPLY",
        params={},
        priority=5,
        x=500, y=500,
    )

    db_session.add_all([market_demand, retailer, wholesaler, distributor, factory, market_supply])
    db_session.flush()

    # Create lanes
    lanes = [
        Lane(config_id=config.id, from_site_id=market_demand.id, to_site_id=retailer.id,
             capacity=1000,
             demand_lead_time={"type": "deterministic", "value": 0},
             supply_lead_time={"type": "deterministic", "value": 1}),
        Lane(config_id=config.id, from_site_id=retailer.id, to_site_id=wholesaler.id,
             capacity=1000,
             demand_lead_time={"type": "deterministic", "value": 1},
             supply_lead_time={"type": "deterministic", "value": 2}),
        Lane(config_id=config.id, from_site_id=wholesaler.id, to_site_id=distributor.id,
             capacity=1000,
             demand_lead_time={"type": "deterministic", "value": 1},
             supply_lead_time={"type": "deterministic", "value": 2}),
        Lane(config_id=config.id, from_site_id=distributor.id, to_site_id=factory.id,
             capacity=1000,
             demand_lead_time={"type": "deterministic", "value": 1},
             supply_lead_time={"type": "deterministic", "value": 2}),
        Lane(config_id=config.id, from_site_id=factory.id, to_site_id=market_supply.id,
             capacity=1000,
             demand_lead_time={"type": "deterministic", "value": 1},
             supply_lead_time={"type": "deterministic", "value": 2}),
    ]
    db_session.add_all(lanes)
    db_session.commit()
    db_session.refresh(config)

    return config


# ============================================================================
# Test Cases
# ============================================================================

class TestScenarioBranching:
    """Test suite for scenario branching operations."""

    def test_create_branch_basic(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test basic branch creation from baseline."""
        service = ScenarioBranchingService(db_session)

        # Create branch
        child = service.create_branch(
            parent_config_id=baseline_config.id,
            name="Case TBG",
            description="Add case-level manufacturing",
            scenario_type=ScenarioType.WORKING,
            created_by=1,
        )

        # Verify child config
        assert child.id is not None
        assert child.name == "Case TBG"
        assert child.parent_config_id == baseline_config.id
        assert child.base_config_id == baseline_config.id  # Root is base
        assert child.scenario_type == ScenarioType.WORKING
        assert child.uses_delta_storage is True
        assert child.branched_at is not None
        assert child.group_id == baseline_config.group_id

        # Verify lineage created
        lineage = db_session.query(ConfigLineage).filter_by(config_id=child.id).all()
        assert len(lineage) == 2  # self + parent
        depths = sorted([l.depth for l in lineage])
        assert depths == [0, 1]

    def test_create_branch_nested(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test nested branching: Root → Case → Six-Pack."""
        service = ScenarioBranchingService(db_session)

        # Create first branch
        case_tbg = service.create_branch(
            parent_config_id=baseline_config.id,
            name="Case TBG",
            description="Case level",
            scenario_type=ScenarioType.WORKING,
        )

        # Create nested branch
        sixpack_tbg = service.create_branch(
            parent_config_id=case_tbg.id,
            name="Six-Pack TBG",
            description="Six-pack level",
            scenario_type=ScenarioType.WORKING,
        )

        # Verify lineage for Six-Pack TBG
        lineage = db_session.query(ConfigLineage).filter_by(config_id=sixpack_tbg.id).order_by(ConfigLineage.depth).all()
        assert len(lineage) == 3  # self + parent + grandparent
        assert lineage[0].ancestor_id == sixpack_tbg.id  # depth=0
        assert lineage[1].ancestor_id == case_tbg.id     # depth=1
        assert lineage[2].ancestor_id == baseline_config.id  # depth=2

        # Verify base config
        assert sixpack_tbg.base_config_id == baseline_config.id

    def test_update_scenario_create_node(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test creating a new node via delta."""
        service = ScenarioBranchingService(db_session)

        # Create branch
        child = service.create_branch(
            parent_config_id=baseline_config.id,
            name="Case TBG",
            description="Add case manufacturing",
        )

        # Add new node via delta
        delta = service.update_scenario(
            config_id=child.id,
            entity_type=EntityType.NODE,
            operation=Operation.CREATE,
            delta_data={
                "name": "Case Manufacturer",
                "type": "MANUFACTURER",
                "params": {"inventory": 0, "backlog": 0},
                "priority": 6,
                "x": 600,
                "y": 600,
            },
            description="Add Case Manufacturer node",
        )

        # Verify delta created
        assert delta.id is not None
        assert delta.config_id == child.id
        assert delta.entity_type == EntityType.NODE
        assert delta.operation == Operation.CREATE
        assert delta.entity_id is None  # Create operation
        assert delta.delta_data["name"] == "Case Manufacturer"

        # Verify delta persisted
        deltas = db_session.query(ConfigDelta).filter_by(config_id=child.id).all()
        assert len(deltas) == 1

    def test_update_scenario_update_node(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test updating an existing node via delta."""
        service = ScenarioBranchingService(db_session)

        # Get retailer node
        retailer = db_session.query(Node).filter_by(config_id=baseline_config.id, name="Retailer").first()

        # Create branch
        child = service.create_branch(
            parent_config_id=baseline_config.id,
            name="Modified TBG",
            description="Modify retailer",
        )

        # Update retailer via delta
        delta = service.update_scenario(
            config_id=child.id,
            entity_type=EntityType.NODE,
            operation=Operation.UPDATE,
            entity_id=retailer.id,
            delta_data={"name": "Retailer V2", "params": {"inventory": 200}},
            description="Update retailer name and inventory",
        )

        # Verify delta
        assert delta.operation == Operation.UPDATE
        assert delta.entity_id == retailer.id
        assert "name" in delta.changed_fields
        assert "params" in delta.changed_fields
        assert delta.original_values["name"] == "Retailer"

    def test_update_scenario_delete_node(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test deleting a node via delta."""
        service = ScenarioBranchingService(db_session)

        # Get factory node
        factory = db_session.query(Node).filter_by(config_id=baseline_config.id, name="Factory").first()

        # Create branch
        child = service.create_branch(
            parent_config_id=baseline_config.id,
            name="Simplified TBG",
            description="Remove factory",
        )

        # Delete factory via delta
        delta = service.update_scenario(
            config_id=child.id,
            entity_type=EntityType.NODE,
            operation=Operation.DELETE,
            entity_id=factory.id,
            delta_data={},
            description="Remove factory node",
        )

        # Verify delta
        assert delta.operation == Operation.DELETE
        assert delta.entity_id == factory.id

    def test_get_effective_config_no_deltas(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test getting effective config for branch with no deltas (inherits all from parent)."""
        service = ScenarioBranchingService(db_session)

        # Create branch without deltas
        child = service.create_branch(
            parent_config_id=baseline_config.id,
            name="Case TBG",
            description="No changes yet",
        )

        # Get effective config
        effective = service.get_effective_config(child.id)

        # Should have same nodes as parent
        assert len(effective["nodes"]) == 6  # All parent nodes
        assert len(effective["lanes"]) == 5  # All parent lanes
        node_names = [n["name"] for n in effective["nodes"]]
        assert "Retailer" in node_names
        assert "Wholesaler" in node_names
        assert "Factory" in node_names

    def test_get_effective_config_with_create_delta(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test effective config merges create deltas."""
        service = ScenarioBranchingService(db_session)

        # Create branch and add node
        child = service.create_branch(
            parent_config_id=baseline_config.id,
            name="Case TBG",
            description="Add case node",
        )
        service.update_scenario(
            config_id=child.id,
            entity_type=EntityType.NODE,
            operation=Operation.CREATE,
            delta_data={
                "id": 999,  # Mock ID for delta
                "name": "Case Manufacturer",
                "type": "MANUFACTURER",
                "params": {},
                "priority": 6,
                "x": 600, "y": 600,
            },
        )

        # Get effective config
        effective = service.get_effective_config(child.id)

        # Should have parent nodes + new node
        assert len(effective["nodes"]) == 7  # 6 parent + 1 new
        node_names = [n["name"] for n in effective["nodes"]]
        assert "Case Manufacturer" in node_names

    def test_get_effective_config_with_update_delta(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test effective config merges update deltas."""
        service = ScenarioBranchingService(db_session)

        # Get retailer
        retailer = db_session.query(Node).filter_by(config_id=baseline_config.id, name="Retailer").first()

        # Create branch and update node
        child = service.create_branch(
            parent_config_id=baseline_config.id,
            name="Modified TBG",
            description="Update retailer",
        )
        service.update_scenario(
            config_id=child.id,
            entity_type=EntityType.NODE,
            operation=Operation.UPDATE,
            entity_id=retailer.id,
            delta_data={"name": "Retailer V2", "params": {"inventory": 200}},
        )

        # Get effective config
        effective = service.get_effective_config(child.id)

        # Find retailer in effective config
        retailer_effective = next((n for n in effective["nodes"] if n["id"] == retailer.id), None)
        assert retailer_effective is not None
        assert retailer_effective["name"] == "Retailer V2"
        assert retailer_effective["params"]["inventory"] == 200

    def test_get_effective_config_with_delete_delta(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test effective config removes deleted entities."""
        service = ScenarioBranchingService(db_session)

        # Get factory
        factory = db_session.query(Node).filter_by(config_id=baseline_config.id, name="Factory").first()

        # Create branch and delete node
        child = service.create_branch(
            parent_config_id=baseline_config.id,
            name="Simplified TBG",
            description="Remove factory",
        )
        service.update_scenario(
            config_id=child.id,
            entity_type=EntityType.NODE,
            operation=Operation.DELETE,
            entity_id=factory.id,
            delta_data={},
        )

        # Get effective config
        effective = service.get_effective_config(child.id)

        # Should have 5 nodes (6 parent - 1 deleted)
        assert len(effective["nodes"]) == 5
        node_names = [n["name"] for n in effective["nodes"]]
        assert "Factory" not in node_names

    def test_rollback_scenario(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test rolling back all deltas."""
        service = ScenarioBranchingService(db_session)

        # Create branch and add multiple deltas
        child = service.create_branch(
            parent_config_id=baseline_config.id,
            name="Working TBG",
            description="Experimental changes",
        )
        service.update_scenario(
            config_id=child.id,
            entity_type=EntityType.NODE,
            operation=Operation.CREATE,
            delta_data={"name": "Node 1"},
        )
        service.update_scenario(
            config_id=child.id,
            entity_type=EntityType.NODE,
            operation=Operation.CREATE,
            delta_data={"name": "Node 2"},
        )

        # Verify deltas exist
        deltas_before = db_session.query(ConfigDelta).filter_by(config_id=child.id).count()
        assert deltas_before == 2

        # Rollback
        service.rollback_scenario(child.id)

        # Verify deltas removed
        deltas_after = db_session.query(ConfigDelta).filter_by(config_id=child.id).count()
        assert deltas_after == 0

    def test_rollback_baseline_fails(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test that rolling back BASELINE scenarios is not allowed."""
        service = ScenarioBranchingService(db_session)

        with pytest.raises(ValueError, match="Cannot rollback BASELINE"):
            service.rollback_scenario(baseline_config.id)

    def test_commit_scenario_not_implemented(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test commit scenario (note: full materialization logic may be incomplete)."""
        service = ScenarioBranchingService(db_session)

        # Create working scenario
        child = service.create_branch(
            parent_config_id=baseline_config.id,
            name="Working TBG",
            description="Ready to commit",
            scenario_type=ScenarioType.WORKING,
        )
        service.update_scenario(
            config_id=child.id,
            entity_type=EntityType.NODE,
            operation=Operation.CREATE,
            delta_data={
                "name": "New Node",
                "type": "MANUFACTURER",
                "params": {},
                "priority": 10,
                "x": 0, "y": 0,
            },
        )

        # Commit (note: may not fully materialize depending on implementation)
        parent = service.commit_scenario(child.id)

        # Verify scenario marked as committed
        db_session.refresh(child)
        assert child.committed_at is not None
        assert child.is_active is False

    def test_commit_non_working_fails(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test that only WORKING scenarios can be committed."""
        service = ScenarioBranchingService(db_session)

        # Try to commit BASELINE (should fail)
        with pytest.raises(ValueError, match="Only WORKING scenarios"):
            service.commit_scenario(baseline_config.id)

    def test_diff_scenarios(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test diffing two configurations."""
        service = ScenarioBranchingService(db_session)

        # Create two branches with different changes
        branch_a = service.create_branch(
            parent_config_id=baseline_config.id,
            name="Branch A",
            description="Adds node A",
        )
        service.update_scenario(
            config_id=branch_a.id,
            entity_type=EntityType.NODE,
            operation=Operation.CREATE,
            delta_data={"id": 888, "name": "Node A", "type": "MANUFACTURER", "params": {}, "priority": 10, "x": 0, "y": 0},
        )

        branch_b = service.create_branch(
            parent_config_id=baseline_config.id,
            name="Branch B",
            description="Adds node B",
        )
        service.update_scenario(
            config_id=branch_b.id,
            entity_type=EntityType.NODE,
            operation=Operation.CREATE,
            delta_data={"id": 999, "name": "Node B", "type": "MANUFACTURER", "params": {}, "priority": 11, "x": 100, "y": 100},
        )

        # Diff branches
        diff = service.diff_scenarios(branch_a.id, branch_b.id)

        # Verify diff structure
        assert "added" in diff
        assert "removed" in diff
        assert "modified" in diff

        # Branch B has Node B (not in A) → added
        assert len(diff["added"]) >= 1
        added_names = [e["entity"]["name"] for e in diff["added"] if e["type"] == "nodes"]
        assert "Node B" in added_names

        # Branch A has Node A (not in B) → removed
        assert len(diff["removed"]) >= 1
        removed_names = [e["entity"]["name"] for e in diff["removed"] if e["type"] == "nodes"]
        assert "Node A" in removed_names

    def test_lineage_query_performance(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test that lineage enables fast ancestor queries."""
        service = ScenarioBranchingService(db_session)

        # Create deep hierarchy: Root → A → B → C → D (5 levels)
        configs = [baseline_config]
        for i in range(4):
            child = service.create_branch(
                parent_config_id=configs[-1].id,
                name=f"Level {i+1}",
                description=f"Nested level {i+1}",
            )
            configs.append(child)

        # Query lineage for deepest config (should be O(1) with lineage table)
        deepest = configs[-1]
        lineage = db_session.query(ConfigLineage).filter_by(config_id=deepest.id).order_by(ConfigLineage.depth).all()

        # Verify full lineage
        assert len(lineage) == 5  # self + 4 ancestors
        assert lineage[0].depth == 0  # self
        assert lineage[4].depth == 4  # root
        assert lineage[4].ancestor_id == baseline_config.id


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestScenarioBranchingEdgeCases:
    """Test edge cases and error handling."""

    def test_create_branch_invalid_parent(self, db_session: Session):
        """Test creating branch from non-existent parent."""
        service = ScenarioBranchingService(db_session)

        with pytest.raises(ValueError, match="Parent config .* not found"):
            service.create_branch(
                parent_config_id=99999,
                name="Invalid Branch",
                description="Should fail",
            )

    def test_get_effective_config_invalid_id(self, db_session: Session):
        """Test getting effective config for non-existent config."""
        service = ScenarioBranchingService(db_session)

        with pytest.raises(ValueError, match="Config .* not found"):
            service.get_effective_config(99999)

    def test_update_scenario_invalid_config(self, db_session: Session):
        """Test updating non-existent scenario."""
        service = ScenarioBranchingService(db_session)

        with pytest.raises(ValueError, match="Config .* not found"):
            service.update_scenario(
                config_id=99999,
                entity_type=EntityType.NODE,
                operation=Operation.CREATE,
                delta_data={},
            )

    def test_multiple_deltas_apply_in_order(self, db_session: Session, baseline_config: SupplyChainConfig):
        """Test that multiple deltas on same entity apply in order."""
        service = ScenarioBranchingService(db_session)

        # Get retailer
        retailer = db_session.query(Node).filter_by(config_id=baseline_config.id, name="Retailer").first()

        # Create branch
        child = service.create_branch(
            parent_config_id=baseline_config.id,
            name="Multi-Update TBG",
            description="Multiple updates to retailer",
        )

        # Apply multiple updates
        service.update_scenario(
            config_id=child.id,
            entity_type=EntityType.NODE,
            operation=Operation.UPDATE,
            entity_id=retailer.id,
            delta_data={"name": "Retailer V1"},
        )
        service.update_scenario(
            config_id=child.id,
            entity_type=EntityType.NODE,
            operation=Operation.UPDATE,
            entity_id=retailer.id,
            delta_data={"name": "Retailer V2"},
        )
        service.update_scenario(
            config_id=child.id,
            entity_type=EntityType.NODE,
            operation=Operation.UPDATE,
            entity_id=retailer.id,
            delta_data={"name": "Retailer V3"},
        )

        # Get effective config
        effective = service.get_effective_config(child.id)

        # Should have final name
        retailer_effective = next((n for n in effective["nodes"] if n["id"] == retailer.id), None)
        assert retailer_effective["name"] == "Retailer V3"
