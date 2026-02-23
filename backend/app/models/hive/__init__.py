"""
Hive coordination neural network components.

Layer 2: HiveHetGAT — Heterogeneous graph attention across 11 TRM types.
Layer 1: RecursiveTRMHead — Per-head iterative refinement with adaptive halting.
"""

from app.models.hive.het_gat_layer import (
    HiveHetGAT,
    HiveHetGATConfig,
    TRMCaste,
    TRM_TO_CASTE,
    CASTE_TO_TRMS,
)
from app.models.hive.recursive_head import (
    RecursiveTRMHead,
    RecursiveHeadConfig,
    RECURSIVE_HEAD_REGISTRY,
)

__all__ = [
    "HiveHetGAT",
    "HiveHetGATConfig",
    "TRMCaste",
    "TRM_TO_CASTE",
    "CASTE_TO_TRMS",
    "RecursiveTRMHead",
    "RecursiveHeadConfig",
    "RECURSIVE_HEAD_REGISTRY",
]
