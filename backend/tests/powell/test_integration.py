"""
Tests for SiteAgent Integration Modules

Tests the integration of SiteAgent with existing services:
- Supply plan integration
- ATP integration
- Scenario integration
- Decision tracking
"""

import pytest
from datetime import date, datetime
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.powell.integration import (
    SiteAgentSupplyPlanAdapter,
    SiteAgentATPAdapter,
    SiteAgentStrategy,
    SiteAgentPolicy,
    SiteAgentDecisionTracker,
    TRMDecisionRecord,
)
from app.services.powell.engines import Priority


class TestSiteAgentPolicy:
    """Tests for SiteAgentPolicy (Beer Game integration)"""

    def test_policy_creation(self):
        """Test policy can be created"""
        policy = SiteAgentPolicy(
            site_key="retailer",
            use_trm=False,
        )

        assert policy.site_key == "retailer"
        assert policy.site_agent is not None

    def test_policy_order_without_trm(self):
        """Test order computation without TRM"""
        policy = SiteAgentPolicy(
            site_key="retailer",
            use_trm=False,
        )

        observation = {
            'inventory': 12,
            'backlog': 0,
            'pipeline_on_order': 8,
            'last_incoming_order': 4,
            'base_stock': 20,
            'inventory_position': 20,  # 12 + 8 - 0
        }

        order = policy.order(observation)

        # Should order to maintain base stock
        # Order = Base Stock - Inv Position + Demand = 20 - 20 + 4 = 4
        assert order >= 0
        assert isinstance(order, int)

    def test_policy_order_with_backlog(self):
        """Test order computation with backlog"""
        policy = SiteAgentPolicy(
            site_key="wholesaler",
            use_trm=False,
        )

        observation = {
            'inventory': 0,
            'backlog': 10,
            'pipeline_on_order': 8,
            'last_incoming_order': 8,
            'base_stock': 20,
            'inventory_position': -2,  # 0 + 8 - 10
        }

        order = policy.order(observation)

        # Should order more due to backlog
        # Order = 20 - (-2) + 8 = 30
        assert order > observation['last_incoming_order']


class TestSiteAgentStrategy:
    """Tests for SiteAgentStrategy wrapper"""

    def test_strategy_creation(self):
        """Test strategy wrapper creation"""
        db = MagicMock()
        strategy = SiteAgentStrategy(db=db, use_trm=False)

        assert strategy.use_trm is False

    def test_get_policy(self):
        """Test policy retrieval"""
        db = MagicMock()
        strategy = SiteAgentStrategy(db=db, use_trm=False)

        policy1 = strategy.get_policy("retailer")
        policy2 = strategy.get_policy("retailer")

        # Should return same cached instance
        assert policy1 is policy2

    def test_compute_order(self):
        """Test order computation through strategy"""
        db = MagicMock()
        strategy = SiteAgentStrategy(db=db, use_trm=False)

        observation = {
            'inventory': 12,
            'backlog': 0,
            'pipeline_on_order': 8,
            'last_incoming_order': 4,
            'base_stock': 20,
            'inventory_position': 20,
        }

        decision = strategy.compute_order("retailer", observation)

        assert decision.order_quantity >= 0
        assert decision.strategy == "site_agent"
        assert decision.reasoning is not None


class TestSiteAgentATPAdapter:
    """Tests for ATP integration"""

    @pytest.fixture
    def atp_adapter(self):
        db = MagicMock()
        return SiteAgentATPAdapter(db=db, use_trm=False)

    def test_adapter_creation(self, atp_adapter):
        """Test adapter creation"""
        assert atp_adapter.use_trm is False

    def test_get_site_agent(self, atp_adapter):
        """Test site agent retrieval"""
        agent1 = atp_adapter.get_site_agent("SITE001")
        agent2 = atp_adapter.get_site_agent("SITE001")

        # Should return same cached instance
        assert agent1 is agent2

    def test_load_allocations(self, atp_adapter):
        """Test loading allocations from tGNN"""
        allocations = [
            {"product_id": "PROD001", "priority": 3, "allocated_qty": 100},
            {"product_id": "PROD001", "priority": 1, "allocated_qty": 50},
        ]

        result = atp_adapter.load_allocations_from_tgnn("SITE001", allocations)

        assert result['allocations_loaded'] == 2
        assert result['site_key'] == "SITE001"

    def test_get_available_by_priority(self, atp_adapter):
        """Test getting available ATP by priority"""
        # Load some allocations
        allocations = [
            {"product_id": "PROD001", "priority": 3, "allocated_qty": 100},
            {"product_id": "PROD001", "priority": 1, "allocated_qty": 50},
        ]
        atp_adapter.load_allocations_from_tgnn("SITE001", allocations)

        available = atp_adapter.get_available_by_priority("SITE001", "PROD001")

        assert 3 in available
        assert available[3] == 100
        assert 1 in available
        assert available[1] == 50


class TestSiteAgentDecisionTracker:
    """Tests for decision tracking"""

    @pytest.fixture
    def tracker(self):
        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = None
        return SiteAgentDecisionTracker(db=db)

    def test_record_atp_decision(self, tracker):
        """Test recording ATP decision"""
        from app.services.powell.site_agent import ATPResponse

        response = MagicMock()
        response.order_id = "ORD001"
        response.promised_qty = 50
        response.source = "deterministic"
        response.exception_action = None
        response.confidence = 1.0

        decision_id = tracker.record_atp_decision(
            site_key="SITE001",
            order_context={"order_id": "ORD001", "requested_qty": 50},
            deterministic_result={"available": 50},
            trm_adjustment=None,
            final_response=response,
        )

        assert decision_id.startswith("ATP-")
        assert decision_id in tracker._pending_decisions

    def test_record_inventory_adjustment(self, tracker):
        """Test recording inventory adjustment"""
        decision_id = tracker.record_inventory_adjustment(
            site_key="SITE001",
            current_state={"inventory": 100, "forecast_demand": 50},
            deterministic_ss=100,
            trm_multiplier=1.1,
            final_ss=110,
            confidence=0.85,
        )

        assert decision_id.startswith("INV-")
        record = tracker._pending_decisions[decision_id]
        assert record.decision_type == "inventory_adjustment"
        assert record.confidence == 0.85

    def test_record_outcome(self, tracker):
        """Test recording outcome for decision"""
        # First create a decision
        decision_id = tracker.record_inventory_adjustment(
            site_key="SITE001",
            current_state={},
            deterministic_ss=100,
            trm_multiplier=1.0,
            final_ss=100,
            confidence=1.0,
        )

        # Record outcome
        result = tracker.record_outcome(
            decision_id=decision_id,
            actual_outcome={"service_level": 0.98},
            reward_signal=0.98,
        )

        assert result is True
        record = tracker._pending_decisions[decision_id]
        assert record.actual_outcome == {"service_level": 0.98}
        assert record.reward_signal == 0.98

    def test_compute_reward_signals(self, tracker):
        """Test reward signal computation"""
        # Create ATP decision with outcome
        from app.services.powell.site_agent import ATPResponse

        response = MagicMock()
        response.order_id = "ORD001"
        response.promised_qty = 50
        response.source = "deterministic"
        response.exception_action = None
        response.confidence = 1.0

        decision_id = tracker.record_atp_decision(
            site_key="SITE001",
            order_context={},
            deterministic_result={},
            trm_adjustment=None,
            final_response=response,
        )

        # Record outcome
        tracker.record_outcome(
            decision_id=decision_id,
            actual_outcome={"fulfilled_qty": 50},
        )

        # Compute rewards
        rewards = tracker.compute_reward_signals([decision_id])

        assert decision_id in rewards
        assert rewards[decision_id] == 1.0  # Full fulfillment


class TestAgentStrategyIntegration:
    """Tests for AgentStrategy enum integration"""

    def test_site_agent_strategy_exists(self):
        """Test SITE_AGENT is in AgentStrategy enum"""
        from app.services.agents import AgentStrategy

        assert hasattr(AgentStrategy, 'SITE_AGENT')
        assert AgentStrategy.SITE_AGENT.value == "site_agent"

    def test_beer_game_agent_site_agent_strategy(self):
        """Test SimulationAgent can use site_agent strategy"""
        from app.services.agents import SimulationAgent, AgentType, AgentStrategy

        agent = SimulationAgent(
            agent_id=1,
            agent_type=AgentType.RETAILER,
            strategy=AgentStrategy.SITE_AGENT,
            can_see_demand=True,
        )

        assert agent.strategy == AgentStrategy.SITE_AGENT

    def test_site_agent_strategy_decision(self):
        """Test site_agent strategy produces decisions"""
        from app.services.agents import SimulationAgent, AgentType, AgentStrategy

        agent = SimulationAgent(
            agent_id=1,
            agent_type=AgentType.RETAILER,
            strategy=AgentStrategy.SITE_AGENT,
            can_see_demand=True,
        )

        # Set up agent state
        agent.inventory = 12
        agent.backlog = 0

        decision = agent.make_decision(
            current_round=1,
            prev_order=4,
            current_demand=4,
            upstream_data=None,
            inventory_level=12,
            backlog_level=0,
            incoming_shipments=4,
        )

        assert decision.quantity >= 0
        assert "SiteAgent" in decision.reason or "site_agent" in decision.reason.lower()
