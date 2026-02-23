"""
Heterogeneous Graph Attention (HetGAT) layer for intra-hive TRM coordination.

Models the 11 TRM agents within a site hive as a heterogeneous graph with
5 node types (biological castes) and ~15 active edge types derived from the
signal production/consumption matrix.

Architecture reference: TRM_HIVE_ARCHITECTURE.md Section 14.2

Forward pass:
    state_embedding [B, 128]
    + urgency_vector [B, 11]
    + signal_summary [B, 22]
    → HiveHetGAT
    → cross_context [B, 11, hidden_dim]

Each TRM node's cross_context captures learned attention-weighted messages
from its signal-connected neighbors, enabling data-driven coordination
that supersedes the fixed 6-phase decision cycle ordering.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Caste taxonomy — maps TRM types to biological castes
# ---------------------------------------------------------------------------

class TRMCaste(enum.IntEnum):
    """Biological caste for each TRM type (5 castes)."""
    SCOUT = 0     # Demand-side observation
    FORAGER = 1   # Supply acquisition
    NURSE = 2     # Colony health
    GUARD = 3     # Production integrity
    BUILDER = 4   # Execution


# TRM type → caste mapping (matches UrgencyVector.TRM_INDICES ordering)
TRM_TO_CASTE: Dict[str, TRMCaste] = {
    "atp_executor": TRMCaste.SCOUT,
    "order_tracking": TRMCaste.SCOUT,
    "po_creation": TRMCaste.FORAGER,
    "rebalancing": TRMCaste.FORAGER,
    "subcontracting": TRMCaste.FORAGER,
    "safety_stock": TRMCaste.NURSE,
    "forecast_adj": TRMCaste.NURSE,
    "quality": TRMCaste.GUARD,
    "maintenance": TRMCaste.GUARD,
    "mo_execution": TRMCaste.BUILDER,
    "to_execution": TRMCaste.BUILDER,
}

# Reverse mapping: caste → list of TRM type names
CASTE_TO_TRMS: Dict[TRMCaste, List[str]] = {}
for _trm, _caste in TRM_TO_CASTE.items():
    CASTE_TO_TRMS.setdefault(_caste, []).append(_trm)

# TRM name → node index (matches UrgencyVector.TRM_INDICES)
TRM_NODE_INDEX: Dict[str, int] = {
    "atp_executor": 0,
    "order_tracking": 1,
    "po_creation": 2,
    "rebalancing": 3,
    "subcontracting": 4,
    "safety_stock": 5,
    "forecast_adj": 6,
    "quality": 7,
    "maintenance": 8,
    "mo_execution": 9,
    "to_execution": 10,
}

NUM_TRM_NODES = 11
NUM_CASTES = 5

# ---------------------------------------------------------------------------
# Signal-derived edge topology
# ---------------------------------------------------------------------------

# Directed edges: (source_trm, target_trm) pairs derived from
# signal production → consumption in hive_signal.py.
# Each edge means "source produces signals that target consumes".
SIGNAL_EDGES: List[Tuple[str, str]] = [
    # Scout → Forager: shortage/surplus signals
    ("atp_executor", "po_creation"),
    ("atp_executor", "rebalancing"),
    ("atp_executor", "subcontracting"),
    ("atp_executor", "safety_stock"),
    ("order_tracking", "po_creation"),
    # Forager → Scout/Builder: supply signals
    ("po_creation", "atp_executor"),
    ("po_creation", "order_tracking"),
    ("rebalancing", "atp_executor"),
    ("rebalancing", "to_execution"),
    ("subcontracting", "mo_execution"),
    # Nurse → Forager/Scout: health signals
    ("safety_stock", "po_creation"),
    ("safety_stock", "atp_executor"),
    ("forecast_adj", "po_creation"),
    ("forecast_adj", "safety_stock"),
    ("forecast_adj", "atp_executor"),
    # Guard → Scout/Builder: integrity signals
    ("quality", "atp_executor"),
    ("quality", "mo_execution"),
    ("maintenance", "mo_execution"),
    ("maintenance", "subcontracting"),
    # Builder → Scout/Forager: execution signals
    ("mo_execution", "atp_executor"),
    ("mo_execution", "po_creation"),
    ("mo_execution", "subcontracting"),
    ("to_execution", "order_tracking"),
    ("to_execution", "rebalancing"),
]


def _build_edge_index() -> torch.Tensor:
    """Build sparse edge_index [2, E] from SIGNAL_EDGES."""
    src_list, tgt_list = [], []
    for src_name, tgt_name in SIGNAL_EDGES:
        src_list.append(TRM_NODE_INDEX[src_name])
        tgt_list.append(TRM_NODE_INDEX[tgt_name])
    return torch.tensor([src_list, tgt_list], dtype=torch.long)


def _build_edge_type_index() -> torch.Tensor:
    """Build edge type index [E] — edge type = source_caste * 5 + target_caste."""
    types = []
    for src_name, tgt_name in SIGNAL_EDGES:
        src_caste = TRM_TO_CASTE[src_name].value
        tgt_caste = TRM_TO_CASTE[tgt_name].value
        types.append(src_caste * NUM_CASTES + tgt_caste)
    return torch.tensor(types, dtype=torch.long)


# ---------------------------------------------------------------------------
# HetGAT Configuration
# ---------------------------------------------------------------------------

@dataclass
class HiveHetGATConfig:
    """Configuration for the HiveHetGAT layer."""
    embedding_dim: int = 128         # Input state embedding dimension
    hidden_dim: int = 64             # Cross-context output dimension per node
    num_heads: int = 2               # GAT attention heads
    urgency_dim: int = 11            # UrgencyVector dimension
    signal_summary_dim: int = 22     # Signal type count dimension
    num_edge_types: int = 25         # 5×5 caste-caste combinations
    dropout: float = 0.1


# ---------------------------------------------------------------------------
# HiveHetGAT Module
# ---------------------------------------------------------------------------

class HiveHetGAT(nn.Module):
    """Heterogeneous Graph Attention layer across 11 TRM nodes.

    Computes a per-node cross_context embedding by aggregating attention-
    weighted messages from signal-connected neighbor nodes. Edge types are
    derived from caste×caste combinations, with type-specific attention
    projections.

    Args:
        config: HiveHetGATConfig with layer dimensions.
    """

    def __init__(self, config: Optional[HiveHetGATConfig] = None):
        super().__init__()
        config = config or HiveHetGATConfig()
        self.config = config
        self.num_heads = config.num_heads
        self.hidden_dim = config.hidden_dim
        head_dim = config.hidden_dim // config.num_heads

        # Node feature projection: state_embedding + urgency_slot + caste_embed → node_feat
        node_input_dim = config.embedding_dim + 1 + config.hidden_dim  # state + urgency + caste
        self.node_proj = nn.Linear(node_input_dim, config.hidden_dim)

        # Caste embedding (5 castes → hidden_dim)
        self.caste_embedding = nn.Embedding(NUM_CASTES, config.hidden_dim)

        # Per-edge-type attention: query and key projections
        # We use a shared base + per-type bias to keep parameter count low
        self.query_proj = nn.Linear(config.hidden_dim, config.hidden_dim)
        self.key_proj = nn.Linear(config.hidden_dim, config.hidden_dim)
        self.value_proj = nn.Linear(config.hidden_dim, config.hidden_dim)

        # Edge type bias — one learnable vector per edge type
        self.edge_type_bias = nn.Embedding(config.num_edge_types, config.num_heads)

        # Output projection
        self.output_proj = nn.Linear(config.hidden_dim, config.hidden_dim)
        self.layer_norm = nn.LayerNorm(config.hidden_dim)
        self.dropout = nn.Dropout(config.dropout)

        # Register static edge topology as buffers (moved to device with model)
        self.register_buffer("edge_index", _build_edge_index())
        self.register_buffer("edge_types", _build_edge_type_index())

        # Node caste indices (for caste embedding lookup)
        caste_indices = []
        for trm_name in sorted(TRM_NODE_INDEX.keys(), key=lambda k: TRM_NODE_INDEX[k]):
            caste_indices.append(TRM_TO_CASTE[trm_name].value)
        self.register_buffer("node_castes", torch.tensor(caste_indices, dtype=torch.long))

    def forward(
        self,
        state_embedding: torch.Tensor,       # [B, embedding_dim]
        urgency_vector: Optional[torch.Tensor] = None,   # [B, 11]
        signal_summary: Optional[torch.Tensor] = None,   # [B, 22]
    ) -> torch.Tensor:
        """Compute cross-TRM context via heterogeneous graph attention.

        Args:
            state_embedding: Shared encoder output [B, embedding_dim].
            urgency_vector: Per-TRM urgency values [B, 11]. Defaults to zeros.
            signal_summary: Signal type counts [B, 22]. Not directly used in
                attention (captured implicitly via urgency); kept for future
                edge feature enrichment.

        Returns:
            cross_context: [B, 11, hidden_dim] — per-node cross-TRM context.
        """
        B = state_embedding.shape[0]
        device = state_embedding.device
        H = self.num_heads
        D = self.hidden_dim // H

        # Default urgency to zeros
        if urgency_vector is None:
            urgency_vector = torch.zeros(B, NUM_TRM_NODES, device=device)

        # Build per-node features: [B, 11, node_input_dim]
        # Each node gets: shared state_embedding + its urgency slot + caste embedding
        caste_emb = self.caste_embedding(self.node_castes)  # [11, hidden_dim]
        caste_emb = caste_emb.unsqueeze(0).expand(B, -1, -1)  # [B, 11, hidden_dim]

        state_expanded = state_embedding.unsqueeze(1).expand(-1, NUM_TRM_NODES, -1)  # [B, 11, emb_dim]
        urgency_expanded = urgency_vector.unsqueeze(-1)  # [B, 11, 1]

        node_input = torch.cat([state_expanded, urgency_expanded, caste_emb], dim=-1)  # [B, 11, input_dim]
        node_feat = self.node_proj(node_input)  # [B, 11, hidden_dim]

        # Compute Q, K, V for all nodes
        Q = self.query_proj(node_feat)   # [B, 11, hidden_dim]
        K = self.key_proj(node_feat)     # [B, 11, hidden_dim]
        V = self.value_proj(node_feat)   # [B, 11, hidden_dim]

        # Reshape for multi-head: [B, 11, H, D]
        Q = Q.view(B, NUM_TRM_NODES, H, D)
        K = K.view(B, NUM_TRM_NODES, H, D)
        V = V.view(B, NUM_TRM_NODES, H, D)

        # Sparse attention using edge_index
        src_idx = self.edge_index[0]  # [E]
        tgt_idx = self.edge_index[1]  # [E]
        E = src_idx.shape[0]

        # Gather source (key) and target (query) features for each edge
        K_src = K[:, src_idx, :, :]  # [B, E, H, D]
        Q_tgt = Q[:, tgt_idx, :, :]  # [B, E, H, D]
        V_src = V[:, src_idx, :, :]  # [B, E, H, D]

        # Attention scores: dot product + edge type bias
        attn_scores = (Q_tgt * K_src).sum(dim=-1) / (D ** 0.5)  # [B, E, H]
        edge_bias = self.edge_type_bias(self.edge_types)  # [E, H]
        attn_scores = attn_scores + edge_bias.unsqueeze(0)  # [B, E, H]

        # Softmax per target node (scatter-based)
        # For each target node, softmax over its incoming edges
        aggregated = torch.zeros(B, NUM_TRM_NODES, H, D, device=device)

        for target_node in range(NUM_TRM_NODES):
            mask = (tgt_idx == target_node)
            if not mask.any():
                continue
            edge_scores = attn_scores[:, mask, :]  # [B, n_incoming, H]
            edge_values = V_src[:, mask, :, :]     # [B, n_incoming, H, D]

            attn_weights = F.softmax(edge_scores, dim=1)  # [B, n_incoming, H]
            attn_weights = self.dropout(attn_weights)

            # Weighted sum of values: [B, n_incoming, H, D] * [B, n_incoming, H, 1]
            weighted = edge_values * attn_weights.unsqueeze(-1)
            aggregated[:, target_node] = weighted.sum(dim=1)  # [B, H, D]

        # Merge heads: [B, 11, H, D] → [B, 11, hidden_dim]
        cross_context = aggregated.reshape(B, NUM_TRM_NODES, self.hidden_dim)

        # Output projection + residual from node features + layer norm
        cross_context = self.output_proj(cross_context)
        cross_context = self.layer_norm(cross_context + node_feat)

        return cross_context
