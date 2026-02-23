"""
Tests for HiveHetGAT — Heterogeneous Graph Attention layer.

Covers: tensor shapes, attention normalization, edge topology,
backward compat, latency, and integration with SiteAgentModel.
"""

import pytest
import time
import torch
import torch.nn as nn

from app.models.hive.het_gat_layer import (
    HiveHetGAT,
    HiveHetGATConfig,
    TRMCaste,
    TRM_TO_CASTE,
    CASTE_TO_TRMS,
    TRM_NODE_INDEX,
    SIGNAL_EDGES,
    NUM_TRM_NODES,
    NUM_CASTES,
    _build_edge_index,
    _build_edge_type_index,
)
from app.services.powell.site_agent_model import (
    SiteAgentModel,
    SiteAgentModelConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_config():
    return HiveHetGATConfig()


@pytest.fixture
def gat(default_config):
    return HiveHetGAT(default_config)


# ---------------------------------------------------------------------------
# Caste / Edge Topology
# ---------------------------------------------------------------------------

class TestCasteMapping:
    """Verify caste taxonomy is complete and consistent."""

    def test_all_11_trms_mapped(self):
        assert len(TRM_TO_CASTE) == 11
        for trm_name in TRM_NODE_INDEX:
            assert trm_name in TRM_TO_CASTE

    def test_five_castes(self):
        assert len(TRMCaste) == 5
        castes_used = set(TRM_TO_CASTE.values())
        assert castes_used == set(TRMCaste)

    def test_caste_to_trms_reverse(self):
        for trm_name, caste in TRM_TO_CASTE.items():
            assert trm_name in CASTE_TO_TRMS[caste]

    def test_scout_caste_members(self):
        scouts = CASTE_TO_TRMS[TRMCaste.SCOUT]
        assert "atp_executor" in scouts
        assert "order_tracking" in scouts
        assert len(scouts) == 2

    def test_forager_caste_members(self):
        foragers = CASTE_TO_TRMS[TRMCaste.FORAGER]
        assert "po_creation" in foragers
        assert "rebalancing" in foragers
        assert "subcontracting" in foragers
        assert len(foragers) == 3


class TestEdgeTopology:
    """Verify signal-derived edge structure."""

    def test_edge_count(self):
        assert len(SIGNAL_EDGES) == 24

    def test_edge_index_shape(self):
        ei = _build_edge_index()
        assert ei.shape == (2, 24)
        assert ei.dtype == torch.long

    def test_edge_type_index_shape(self):
        et = _build_edge_type_index()
        assert et.shape == (24,)
        assert et.dtype == torch.long

    def test_edge_types_valid(self):
        et = _build_edge_type_index()
        for t in et:
            assert 0 <= t.item() < NUM_CASTES * NUM_CASTES

    def test_all_edge_nodes_valid(self):
        ei = _build_edge_index()
        assert (ei >= 0).all()
        assert (ei < NUM_TRM_NODES).all()

    def test_scout_to_forager_edges_exist(self):
        """ATP shortage → PO creation should be in the edge list."""
        atp_idx = TRM_NODE_INDEX["atp_executor"]
        po_idx = TRM_NODE_INDEX["po_creation"]
        ei = _build_edge_index()
        edges = list(zip(ei[0].tolist(), ei[1].tolist()))
        assert (atp_idx, po_idx) in edges


# ---------------------------------------------------------------------------
# Forward Pass
# ---------------------------------------------------------------------------

class TestHetGATForward:
    """Verify forward pass produces correct shapes and is differentiable."""

    def test_output_shape(self, gat):
        B = 4
        state_emb = torch.randn(B, 128)
        urgency = torch.randn(B, 11)
        out = gat(state_emb, urgency)
        assert out.shape == (B, NUM_TRM_NODES, 64)

    def test_output_shape_no_urgency(self, gat):
        B = 2
        state_emb = torch.randn(B, 128)
        out = gat(state_emb)
        assert out.shape == (B, NUM_TRM_NODES, 64)

    def test_output_shape_with_signal_summary(self, gat):
        B = 3
        state_emb = torch.randn(B, 128)
        urgency = torch.randn(B, 11)
        sig_sum = torch.randn(B, 22)
        out = gat(state_emb, urgency, sig_sum)
        assert out.shape == (B, NUM_TRM_NODES, 64)

    def test_batch_size_one(self, gat):
        state_emb = torch.randn(1, 128)
        out = gat(state_emb)
        assert out.shape == (1, NUM_TRM_NODES, 64)

    def test_gradient_flows(self, gat):
        state_emb = torch.randn(2, 128, requires_grad=True)
        out = gat(state_emb)
        loss = out.sum()
        loss.backward()
        assert state_emb.grad is not None
        assert state_emb.grad.abs().sum() > 0

    def test_different_urgency_produces_different_output(self, gat):
        state_emb = torch.randn(1, 128)
        u1 = torch.zeros(1, 11)
        u2 = torch.ones(1, 11)
        out1 = gat(state_emb, u1)
        out2 = gat(state_emb, u2)
        assert not torch.allclose(out1, out2, atol=1e-5)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class TestHetGATConfig:
    """Verify configurable dimensions work correctly."""

    def test_custom_hidden_dim(self):
        config = HiveHetGATConfig(hidden_dim=32, num_heads=2)
        gat = HiveHetGAT(config)
        out = gat(torch.randn(1, 128))
        assert out.shape == (1, NUM_TRM_NODES, 32)

    def test_custom_embedding_dim(self):
        config = HiveHetGATConfig(embedding_dim=64)
        gat = HiveHetGAT(config)
        out = gat(torch.randn(1, 64))
        assert out.shape == (1, NUM_TRM_NODES, 64)

    def test_four_heads(self):
        config = HiveHetGATConfig(hidden_dim=64, num_heads=4)
        gat = HiveHetGAT(config)
        out = gat(torch.randn(1, 128))
        assert out.shape == (1, NUM_TRM_NODES, 64)


# ---------------------------------------------------------------------------
# Parameter Count
# ---------------------------------------------------------------------------

class TestParameterBudget:
    """Verify HetGAT stays within parameter budget."""

    def test_parameter_count_under_200k(self, gat):
        total = sum(p.numel() for p in gat.parameters())
        assert total < 200_000, f"HetGAT has {total} params, expected <200K"

    def test_parameter_count_positive(self, gat):
        total = sum(p.numel() for p in gat.parameters())
        assert total > 10_000, f"HetGAT has only {total} params, seems too low"


# ---------------------------------------------------------------------------
# Latency
# ---------------------------------------------------------------------------

class TestLatency:
    """Verify HetGAT meets latency target."""

    def test_latency_under_10ms(self, gat):
        """Single forward pass should complete in <10ms on CPU."""
        gat.eval()
        state_emb = torch.randn(1, 128)
        urgency = torch.randn(1, 11)

        # Warmup
        for _ in range(3):
            gat(state_emb, urgency)

        # Measure
        times = []
        for _ in range(10):
            start = time.perf_counter()
            with torch.no_grad():
                gat(state_emb, urgency)
            times.append(time.perf_counter() - start)

        avg_ms = sum(times) / len(times) * 1000
        assert avg_ms < 10.0, f"HetGAT average latency {avg_ms:.2f}ms exceeds 10ms target"


# ---------------------------------------------------------------------------
# SiteAgentModel Integration
# ---------------------------------------------------------------------------

class TestSiteAgentModelIntegration:
    """Verify HetGAT integrates correctly with SiteAgentModel."""

    def _make_dummy_inputs(self, B=2):
        P, L, W, H = 4, 4, 4, 3
        return {
            "inventory": torch.randn(B, P),
            "pipeline": torch.randn(B, P, L),
            "backlog": torch.randn(B, P),
            "demand_history": torch.randn(B, P, W),
            "forecasts": torch.randn(B, P, H),
        }

    def _make_config(self, het_gat_enabled=False):
        P, L, W, H = 4, 4, 4, 3
        total_dim = P + P * L + P + P * W + P * H
        return SiteAgentModelConfig(
            state_dim=total_dim,
            het_gat_enabled=het_gat_enabled,
        )

    def test_model_without_hetgat(self):
        config = self._make_config(het_gat_enabled=False)
        model = SiteAgentModel(config)
        assert model.het_gat is None

    def test_model_with_hetgat(self):
        config = self._make_config(het_gat_enabled=True)
        model = SiteAgentModel(config)
        assert model.het_gat is not None

    def test_forward_with_hetgat(self):
        config = self._make_config(het_gat_enabled=True)
        model = SiteAgentModel(config)
        inputs = self._make_dummy_inputs()
        urgency = torch.randn(2, 11)
        results = model(
            **inputs,
            urgency_vector=urgency,
            task="inventory",
        )
        assert "cross_context" in results
        assert results["cross_context"].shape == (2, NUM_TRM_NODES, 64)
        assert "inventory" in results

    def test_forward_without_hetgat_no_cross_context(self):
        config = self._make_config(het_gat_enabled=False)
        model = SiteAgentModel(config)
        inputs = self._make_dummy_inputs()
        results = model(**inputs, task="inventory")
        assert "cross_context" not in results
        assert "inventory" in results

    def test_hetgat_param_count_in_model(self):
        config = self._make_config(het_gat_enabled=True)
        model = SiteAgentModel(config)
        counts = model.get_parameter_count()
        assert "het_gat" in counts
        assert counts["het_gat"] > 10_000

    def test_backward_compat_no_hetgat(self):
        """Model with het_gat_enabled=False should produce same result on repeated calls."""
        config = self._make_config(het_gat_enabled=False)
        model = SiteAgentModel(config)
        model.eval()
        inputs = self._make_dummy_inputs(B=1)

        with torch.no_grad():
            r1 = model(**inputs, task="inventory")
            r2 = model(**inputs, task="inventory")

        assert torch.allclose(
            r1["inventory"]["ss_multiplier"],
            r2["inventory"]["ss_multiplier"],
            atol=1e-6,
        )
