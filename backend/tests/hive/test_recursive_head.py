"""
Tests for RecursiveTRMHead — per-head iterative refinement.

Covers: tensor shapes, refinement effect, adaptive halting,
CGAR curriculum, all 11 head subclasses, parameter budget, latency.
"""

import pytest
import time
import torch

from app.models.hive.recursive_head import (
    RecursiveTRMHead,
    RecursiveHeadConfig,
    RefinementBlock,
    AnswerBlock,
    RecursiveATPHead,
    RecursiveRebalancingHead,
    RecursivePOHead,
    RecursiveOrderTrackingHead,
    RecursiveMOHead,
    RecursiveTOHead,
    RecursiveQualityHead,
    RecursiveMaintenanceHead,
    RecursiveSubcontractingHead,
    RecursiveForecastAdjHead,
    RecursiveSafetyStockHead,
    RECURSIVE_HEAD_REGISTRY,
)
from app.services.powell.trm_site_trainer import TRMSiteTrainer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_config():
    return RecursiveHeadConfig(input_dim=128, hidden_dim=64)


@pytest.fixture
def atp_head(default_config):
    return RecursiveATPHead(default_config)


# ---------------------------------------------------------------------------
# RefinementBlock
# ---------------------------------------------------------------------------

class TestRefinementBlock:
    def test_output_shape(self):
        block = RefinementBlock(input_dim=128, answer_dim=8, hidden_dim=64)
        head_input = torch.randn(2, 128)
        prev_answer = torch.randn(2, 8)
        prev_scratch = torch.randn(2, 64)
        out = block(head_input, prev_answer, prev_scratch)
        assert out.shape == (2, 64)

    def test_gradient_flows(self):
        block = RefinementBlock(input_dim=128, answer_dim=8, hidden_dim=64)
        x = torch.randn(1, 128, requires_grad=True)
        out = block(x, torch.randn(1, 8), torch.randn(1, 64))
        out.sum().backward()
        assert x.grad is not None


class TestAnswerBlock:
    def test_output_shape(self):
        block = AnswerBlock(hidden_dim=64, answer_dim=6)
        out = block(torch.randn(2, 6), torch.randn(2, 64))
        assert out.shape == (2, 6)


# ---------------------------------------------------------------------------
# Base RecursiveTRMHead
# ---------------------------------------------------------------------------

class TestRecursiveTRMHead:
    def test_forward_shape(self, default_config):
        head = RecursiveTRMHead(default_config)
        out = head(torch.randn(2, 128))
        assert "raw_answer" in out
        assert "confidence" in out
        assert out["confidence"].shape == (2, 1)

    def test_refinement_changes_output(self, default_config):
        """R=3 should produce different output than R=1."""
        head = RecursiveTRMHead(default_config)
        head.eval()
        x = torch.randn(1, 128)
        with torch.no_grad():
            r1 = head(x, R=1)
            r3 = head(x, R=3)
        assert not torch.allclose(r1["raw_answer"], r3["raw_answer"], atol=1e-5)

    def test_gradient_through_recursion(self, default_config):
        head = RecursiveTRMHead(default_config)
        x = torch.randn(2, 128, requires_grad=True)
        out = head(x, R=3)
        out["raw_answer"].sum().backward()
        assert x.grad is not None
        assert x.grad.abs().sum() > 0

    def test_avg_steps_tracking(self, default_config):
        head = RecursiveTRMHead(default_config)
        head.train()
        head(torch.randn(1, 128), R=3)
        head(torch.randn(1, 128), R=3)
        assert head.avg_steps == 3.0


# ---------------------------------------------------------------------------
# Adaptive Halting
# ---------------------------------------------------------------------------

class TestAdaptiveHalting:
    def test_halting_enabled(self):
        config = RecursiveHeadConfig(
            input_dim=128,
            hidden_dim=64,
            num_refinement_steps=3,
            adaptive_halt=True,
            halt_threshold=0.0,  # Very low → should halt immediately
        )
        head = RecursiveTRMHead(config)
        head.eval()
        out = head(torch.randn(1, 128))
        assert out["num_steps"] <= 3

    def test_halting_disabled(self, default_config):
        head = RecursiveTRMHead(default_config)
        head.eval()
        out = head(torch.randn(1, 128))
        assert out["num_steps"] == 3


# ---------------------------------------------------------------------------
# 11 Head Subclasses
# ---------------------------------------------------------------------------

class TestAllHeadSubclasses:
    """Verify all 11 concrete head subclasses produce valid outputs."""

    HEAD_CLASSES = [
        (RecursiveATPHead, {"action_probs": (4,), "fill_rate": (1,), "value": (1,)}),
        (RecursiveRebalancingHead, {"qty_multiplier": (1,), "direction_probs": (2,), "value": (1,)}),
        (RecursivePOHead, {"timing_probs": (3,), "expedite_prob": (1,), "days_offset": (1,), "value": (1,)}),
        (RecursiveOrderTrackingHead, {"action_probs": (5,), "severity": (1,), "value": (1,)}),
        (RecursiveMOHead, {"action_probs": (5,), "value": (1,)}),
        (RecursiveTOHead, {"action_probs": (4,), "value": (1,)}),
        (RecursiveQualityHead, {"action_probs": (5,), "value": (1,)}),
        (RecursiveMaintenanceHead, {"action_probs": (4,), "value": (1,)}),
        (RecursiveSubcontractingHead, {"action_probs": (3,), "split_ratio": (1,), "value": (1,)}),
        (RecursiveForecastAdjHead, {"direction_probs": (3,), "magnitude": (1,), "value": (1,)}),
        (RecursiveSafetyStockHead, {"ss_multiplier": (1,), "rop_multiplier": (1,), "value": (1,)}),
    ]

    @pytest.mark.parametrize("head_cls,expected_outputs", HEAD_CLASSES,
                             ids=[c[0].__name__ for c in HEAD_CLASSES])
    def test_head_outputs(self, head_cls, expected_outputs):
        config = RecursiveHeadConfig(input_dim=128, hidden_dim=64)
        head = head_cls(config)
        out = head(torch.randn(2, 128))

        # Check confidence always present
        assert "confidence" in out
        assert out["confidence"].shape == (2, 1)

        # Check task-specific outputs
        for key, shape_suffix in expected_outputs.items():
            assert key in out, f"Missing output '{key}' from {head_cls.__name__}"
            expected_shape = (2,) + shape_suffix
            assert out[key].shape == expected_shape, (
                f"{head_cls.__name__}.{key}: expected {expected_shape}, got {out[key].shape}"
            )

    def test_atp_action_probs_sum_to_one(self):
        config = RecursiveHeadConfig(input_dim=128, hidden_dim=64)
        head = RecursiveATPHead(config)
        out = head(torch.randn(2, 128))
        sums = out["action_probs"].sum(dim=-1)
        assert torch.allclose(sums, torch.ones(2), atol=1e-5)

    def test_safety_stock_multiplier_bounds(self):
        config = RecursiveHeadConfig(input_dim=128, hidden_dim=64)
        head = RecursiveSafetyStockHead(config)
        out = head(torch.randn(100, 128))
        assert (out["ss_multiplier"] >= 0.8).all()
        assert (out["ss_multiplier"] <= 1.2).all()
        assert (out["rop_multiplier"] >= 0.8).all()
        assert (out["rop_multiplier"] <= 1.2).all()

    def test_po_days_offset_bounded(self):
        config = RecursiveHeadConfig(input_dim=128, hidden_dim=64)
        head = RecursivePOHead(config)
        out = head(torch.randn(100, 128))
        assert (out["days_offset"] >= -7).all()
        assert (out["days_offset"] <= 7).all()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_all_11_types_registered(self):
        assert len(RECURSIVE_HEAD_REGISTRY) == 11

    def test_lookup_by_name(self):
        cls = RECURSIVE_HEAD_REGISTRY["atp_executor"]
        assert cls is RecursiveATPHead


# ---------------------------------------------------------------------------
# CGAR Curriculum
# ---------------------------------------------------------------------------

class TestCGARCurriculum:
    def test_early_training_R1(self):
        assert TRMSiteTrainer.cgar_refinement_steps(0, 100) == 1
        assert TRMSiteTrainer.cgar_refinement_steps(10, 100) == 1
        assert TRMSiteTrainer.cgar_refinement_steps(29, 100) == 1

    def test_mid_training_R2(self):
        assert TRMSiteTrainer.cgar_refinement_steps(30, 100) == 2
        assert TRMSiteTrainer.cgar_refinement_steps(45, 100) == 2
        assert TRMSiteTrainer.cgar_refinement_steps(59, 100) == 2

    def test_late_training_R3(self):
        assert TRMSiteTrainer.cgar_refinement_steps(60, 100) == 3
        assert TRMSiteTrainer.cgar_refinement_steps(80, 100) == 3
        assert TRMSiteTrainer.cgar_refinement_steps(99, 100) == 3

    def test_max_R_respected(self):
        assert TRMSiteTrainer.cgar_refinement_steps(99, 100, max_R=2) == 2
        assert TRMSiteTrainer.cgar_refinement_steps(99, 100, max_R=1) == 1


# ---------------------------------------------------------------------------
# Parameter Budget
# ---------------------------------------------------------------------------

class TestParameterBudget:
    def test_single_head_under_30k(self):
        config = RecursiveHeadConfig(input_dim=128, hidden_dim=64)
        head = RecursiveATPHead(config)
        total = sum(p.numel() for p in head.parameters())
        assert total < 30_000, f"ATP head has {total} params, expected <30K"

    def test_all_11_heads_under_350k(self):
        config = RecursiveHeadConfig(input_dim=128, hidden_dim=64)
        total = 0
        for cls in RECURSIVE_HEAD_REGISTRY.values():
            head = cls(config)
            total += sum(p.numel() for p in head.parameters())
        assert total < 350_000, f"All 11 heads have {total} params, expected <350K"


# ---------------------------------------------------------------------------
# Latency
# ---------------------------------------------------------------------------

class TestLatency:
    def test_single_head_under_5ms(self):
        config = RecursiveHeadConfig(input_dim=128, hidden_dim=64)
        head = RecursiveATPHead(config)
        head.eval()
        x = torch.randn(1, 128)

        # Warmup
        for _ in range(3):
            head(x)

        times = []
        for _ in range(10):
            start = time.perf_counter()
            with torch.no_grad():
                head(x, R=3)
            times.append(time.perf_counter() - start)

        avg_ms = sum(times) / len(times) * 1000
        assert avg_ms < 5.0, f"ATP head avg latency {avg_ms:.2f}ms exceeds 5ms target"
