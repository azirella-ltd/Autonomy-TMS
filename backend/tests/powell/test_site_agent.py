"""
Tests for SiteAgent

Tests the unified orchestrator that combines engines with TRM heads.
"""

import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
import torch

from app.services.powell.site_agent import (
    SiteAgent,
    SiteAgentConfig,
    ATPResponse,
    PORecommendation,
)
from app.services.powell.site_agent_model import (
    SiteAgentModel,
    SiteAgentModelConfig,
)
from app.services.powell.cdc_monitor import (
    CDCMonitor,
    CDCConfig,
    SiteMetrics,
    TriggerReason,
    ReplanAction,
)
from app.services.powell.engines import (
    Priority,
    Order,
    ATPAllocation,
)


class TestSiteAgentConfig:
    """Tests for SiteAgent configuration"""

    def test_default_config(self):
        """Test default configuration values"""
        config = SiteAgentConfig(site_key="SITE001")

        assert config.site_key == "SITE001"
        assert config.use_trm_adjustments is True
        assert config.trm_confidence_threshold == 0.7
        assert config.agent_mode == "copilot"

    def test_custom_config(self):
        """Test custom configuration"""
        config = SiteAgentConfig(
            site_key="SITE001",
            use_trm_adjustments=False,
            agent_mode="autonomous",
            trm_confidence_threshold=0.9,
        )

        assert config.use_trm_adjustments is False
        assert config.agent_mode == "autonomous"
        assert config.trm_confidence_threshold == 0.9


class TestSiteAgentInitialization:
    """Tests for SiteAgent initialization"""

    def test_init_without_trm(self):
        """Test initialization without TRM model"""
        config = SiteAgentConfig(
            site_key="SITE001",
            use_trm_adjustments=False,
        )

        agent = SiteAgent(config)

        assert agent.site_key == "SITE001"
        assert agent.mrp_engine is not None
        assert agent.aatp_engine is not None
        assert agent.ss_calculator is not None
        assert agent.cdc_monitor is not None
        assert agent.model is None  # TRM disabled

    def test_init_with_trm(self):
        """Test initialization with TRM model"""
        config = SiteAgentConfig(
            site_key="SITE001",
            use_trm_adjustments=True,
        )

        agent = SiteAgent(config)

        assert agent.model is not None
        # Model should be in eval mode
        assert not agent.model.training

    def test_init_with_checkpoint(self, tmp_path):
        """Test initialization from checkpoint"""
        # Create a dummy checkpoint
        model_config = SiteAgentModelConfig()
        model = SiteAgentModel(model_config)

        checkpoint_path = tmp_path / "checkpoint.pt"
        torch.save({
            'model_state_dict': model.state_dict(),
            'model_config': model_config,
        }, checkpoint_path)

        config = SiteAgentConfig(
            site_key="SITE001",
            use_trm_adjustments=True,
            model_checkpoint_path=str(checkpoint_path),
        )

        agent = SiteAgent(config)

        assert agent.model is not None


class TestSiteAgentATP:
    """Tests for ATP execution"""

    @pytest.fixture
    def site_agent(self):
        config = SiteAgentConfig(
            site_key="SITE001",
            use_trm_adjustments=False,  # Test deterministic first
        )
        return SiteAgent(config)

    @pytest.fixture
    def sample_order(self):
        return Order(
            order_id="ORD001",
            product_id="PROD001",
            location_id="SITE001",
            requested_qty=50,
            requested_date=date.today(),
            priority=Priority.MEDIUM,
            customer_id="CUST001",
        )

    @pytest.mark.asyncio
    async def test_atp_full_availability(self, site_agent, sample_order):
        """Test ATP with full availability"""
        # Load allocations
        allocations = [
            ATPAllocation("PROD001", "SITE001", Priority.MEDIUM, 100, date.today(), date.today()),
        ]
        site_agent.aatp_engine.load_allocations(allocations)

        result = await site_agent.execute_atp(sample_order)

        assert result.promised_qty == 50
        assert result.source == "deterministic"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_atp_shortage_no_trm(self, site_agent, sample_order):
        """Test ATP with shortage when TRM disabled"""
        # Load insufficient allocations
        allocations = [
            ATPAllocation("PROD001", "SITE001", Priority.MEDIUM, 30, date.today(), date.today()),
        ]
        site_agent.aatp_engine.load_allocations(allocations)

        result = await site_agent.execute_atp(sample_order)

        # Should return partial fill
        assert result.promised_qty == 30
        assert result.source == "deterministic"

    @pytest.mark.asyncio
    async def test_atp_no_allocations(self, site_agent, sample_order):
        """Test ATP when no allocations exist"""
        result = await site_agent.execute_atp(sample_order)

        assert result.promised_qty == 0
        assert result.source == "deterministic"


class TestSiteAgentWithTRM:
    """Tests for SiteAgent with TRM enabled"""

    @pytest.fixture
    def site_agent_with_trm(self):
        config = SiteAgentConfig(
            site_key="SITE001",
            use_trm_adjustments=True,
            trm_confidence_threshold=0.5,
        )
        return SiteAgent(config)

    @pytest.mark.asyncio
    async def test_atp_trm_adjustment(self, site_agent_with_trm):
        """Test ATP with TRM exception handling"""
        # Load insufficient allocations to trigger TRM
        allocations = [
            ATPAllocation("PROD001", "SITE001", Priority.MEDIUM, 30, date.today(), date.today()),
        ]
        site_agent_with_trm.aatp_engine.load_allocations(allocations)

        order = Order(
            order_id="ORD001",
            product_id="PROD001",
            location_id="SITE001",
            requested_qty=50,
            requested_date=date.today(),
            priority=Priority.MEDIUM,
            customer_id="CUST001",
        )

        result = await site_agent_with_trm.execute_atp(order)

        # TRM should provide a decision
        assert result.source in ["deterministic", "trm_adjusted"]

    @pytest.mark.asyncio
    async def test_inventory_adjustments(self, site_agent_with_trm):
        """Test inventory adjustment suggestions from TRM"""
        adjustments = await site_agent_with_trm.get_inventory_adjustments()

        assert 'ss_multiplier' in adjustments
        assert 'rop_multiplier' in adjustments
        # Should be bounded
        assert 0.8 <= adjustments['ss_multiplier'] <= 1.2
        assert 0.8 <= adjustments['rop_multiplier'] <= 1.2


class TestCDCIntegration:
    """Tests for CDC monitor integration"""

    @pytest.fixture
    def site_agent(self):
        config = SiteAgentConfig(
            site_key="SITE001",
            cdc_config=CDCConfig(
                thresholds={
                    'demand_deviation': 0.10,
                    'inventory_ratio_low': 0.70,
                    'inventory_ratio_high': 1.50,
                    'service_level_drop': 0.05,
                    'lead_time_increase': 0.30,
                    'backlog_growth_days': 2,
                    'supplier_reliability_drop': 0.15,
                },
                cooldown_hours=1,
            ),
        )
        return SiteAgent(config)

    @pytest.fixture
    def normal_metrics(self):
        return SiteMetrics(
            site_key="SITE001",
            timestamp=datetime.utcnow(),
            demand_cumulative=100,
            forecast_cumulative=100,  # No deviation
            inventory_on_hand=500,
            inventory_target=500,
            service_level=0.96,
            target_service_level=0.95,
            avg_lead_time_actual=7,
            avg_lead_time_expected=7,
            supplier_on_time_rate=0.95,
            backlog_units=0,
            backlog_yesterday=0,
        )

    @pytest.fixture
    def deviation_metrics(self):
        return SiteMetrics(
            site_key="SITE001",
            timestamp=datetime.utcnow(),
            demand_cumulative=150,  # 50% above forecast
            forecast_cumulative=100,
            inventory_on_hand=500,
            inventory_target=500,
            service_level=0.96,
            target_service_level=0.95,
            avg_lead_time_actual=7,
            avg_lead_time_expected=7,
            supplier_on_time_rate=0.95,
            backlog_units=0,
            backlog_yesterday=0,
        )

    @pytest.mark.asyncio
    async def test_cdc_no_trigger(self, site_agent, normal_metrics):
        """Test CDC doesn't trigger when metrics are normal"""
        trigger = await site_agent.check_cdc_trigger(normal_metrics)

        assert not trigger.triggered
        assert trigger.recommended_action == ReplanAction.NONE

    @pytest.mark.asyncio
    async def test_cdc_demand_deviation(self, site_agent, deviation_metrics):
        """Test CDC triggers on demand deviation"""
        trigger = await site_agent.check_cdc_trigger(deviation_metrics)

        assert trigger.triggered
        assert TriggerReason.DEMAND_DEVIATION in trigger.reasons
        assert trigger.recommended_action == ReplanAction.FULL_CFA

    @pytest.mark.asyncio
    async def test_cdc_service_level_drop(self, site_agent):
        """Test CDC triggers on service level drop"""
        metrics = SiteMetrics(
            site_key="SITE001",
            timestamp=datetime.utcnow(),
            demand_cumulative=100,
            forecast_cumulative=100,
            inventory_on_hand=500,
            inventory_target=500,
            service_level=0.88,  # Below target - threshold
            target_service_level=0.95,
            avg_lead_time_actual=7,
            avg_lead_time_expected=7,
            supplier_on_time_rate=0.95,
            backlog_units=0,
            backlog_yesterday=0,
        )

        trigger = await site_agent.check_cdc_trigger(metrics)

        assert trigger.triggered
        assert TriggerReason.SERVICE_LEVEL_DROP in trigger.reasons
        assert trigger.severity == "critical"


class TestSiteAgentStatus:
    """Tests for status reporting"""

    def test_status_without_trm(self):
        """Test status when TRM is disabled"""
        config = SiteAgentConfig(
            site_key="SITE001",
            use_trm_adjustments=False,
        )
        agent = SiteAgent(config)

        status = agent.get_status()

        assert status['site_key'] == "SITE001"
        assert status['use_trm'] is False
        assert status['model_loaded'] is False

    def test_status_with_trm(self):
        """Test status when TRM is enabled"""
        config = SiteAgentConfig(
            site_key="SITE001",
            use_trm_adjustments=True,
        )
        agent = SiteAgent(config)

        status = agent.get_status()

        assert status['use_trm'] is True
        assert status['model_loaded'] is True
        assert 'cdc_status' in status
        assert 'allocations_summary' in status


class TestSiteAgentModel:
    """Tests for the SiteAgent neural network model"""

    @pytest.fixture
    def model(self):
        config = SiteAgentModelConfig(
            state_dim=260,
            embedding_dim=128,
        )
        return SiteAgentModel(config)

    def test_model_creation(self, model):
        """Test model can be created"""
        assert model.encoder is not None
        assert model.atp_exception_head is not None
        assert model.inventory_planning_head is not None
        assert model.po_timing_head is not None

    def test_parameter_count(self, model):
        """Test parameter counting"""
        counts = model.get_parameter_count()

        assert 'encoder' in counts
        assert 'atp_exception_head' in counts
        assert 'total' in counts
        assert counts['total'] > 0

    def test_forward_pass(self, model):
        """Test forward pass through model"""
        batch_size = 4
        n_products = 10

        inventory = torch.randn(batch_size, n_products)
        pipeline = torch.randn(batch_size, n_products, 4)
        backlog = torch.randn(batch_size, n_products)
        demand_history = torch.randn(batch_size, n_products, 12)
        forecasts = torch.randn(batch_size, n_products, 8)

        # Encode state
        state = model.encode_state(inventory, pipeline, backlog, demand_history, forecasts)

        assert state.shape == (batch_size, 128)

    def test_atp_head(self, model):
        """Test ATP exception head"""
        batch_size = 4
        state = torch.randn(batch_size, 128)
        order_context = torch.randn(batch_size, 16)
        shortage = torch.randn(batch_size, 1)

        output = model.forward_atp_exception(state, order_context, shortage)

        assert 'action_probs' in output
        assert output['action_probs'].shape == (batch_size, 4)
        # Probabilities should sum to 1
        assert torch.allclose(output['action_probs'].sum(dim=1), torch.ones(batch_size), atol=1e-5)

    def test_inventory_head(self, model):
        """Test inventory planning head"""
        batch_size = 4
        state = torch.randn(batch_size, 128)

        output = model.forward_inventory_planning(state)

        assert 'ss_multiplier' in output
        assert 'rop_multiplier' in output
        # Should be bounded
        assert (output['ss_multiplier'] >= 0.8).all()
        assert (output['ss_multiplier'] <= 1.2).all()

    def test_po_timing_head(self, model):
        """Test PO timing head"""
        batch_size = 4
        state = torch.randn(batch_size, 128)
        po_context = torch.randn(batch_size, 12)

        output = model.forward_po_timing(state, po_context)

        assert 'timing_probs' in output
        assert 'expedite_prob' in output
        assert 'days_offset' in output
        # Days offset bounded to ±7
        assert (output['days_offset'] >= -7).all()
        assert (output['days_offset'] <= 7).all()
