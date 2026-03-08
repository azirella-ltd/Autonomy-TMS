"""
Site tGNN (Layer 1.5) — Intra-Site Cross-TRM Coordination Model.

Operates within a single site across all 11 TRM agents, learning causal
relationships between execution decisions. For example:
  "when ATP fulfills P1 aggressively for 3 cycles, MO capacity starves on cycle 4"

Architecture: GATv2 + GRU (~25K params, <5ms inference)
  - 11 TRM-type nodes with ~22 directed causal edges
  - 2-layer GATv2Conv for spatial message passing across TRM graph
  - GRU for temporal state across hourly ticks
  - Per-TRM output heads producing urgency adjustments

Layer 1.5 sits between:
  - Layer 1 (HiveSignalBus, <10ms) — reactive, pheromone-based
  - Layer 2 (Network tGNN, daily) — inter-site, allocation-focused

Architecture reference: TRM_HIVE_ARCHITECTURE.md Section 16.3.5
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATv2Conv
from typing import Dict, List, Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# TRM Names and Indices (must match UrgencyVector.TRM_INDICES)
# ============================================================================

TRM_NAMES: List[str] = [
    "atp_executor",
    "order_tracking",
    "po_creation",
    "rebalancing",
    "subcontracting",
    "inventory_buffer",
    "forecast_adj",
    "quality",
    "maintenance",
    "mo_execution",
    "to_execution",
]

TRM_NAME_TO_IDX: Dict[str, int] = {name: i for i, name in enumerate(TRM_NAMES)}
NUM_TRM_TYPES = len(TRM_NAMES)


# ============================================================================
# Causal Edge Topology — directed edges between TRM types
# ============================================================================

SITE_TGNN_EDGES: List[Tuple[str, str]] = [
    # ATP decisions affect downstream execution
    ("atp_executor", "mo_execution"),         # ATP commit -> MO must produce
    ("atp_executor", "to_execution"),         # ATP commit -> TO must ship
    ("atp_executor", "inventory_buffer"),     # ATP consumption -> buffer depletion

    # MO execution cascades
    ("mo_execution", "quality"),              # MO output -> quality inspection
    ("mo_execution", "maintenance"),          # MO load -> maintenance urgency
    ("mo_execution", "subcontracting"),       # MO overflow -> subcontracting

    # PO creation feeds inbound
    ("po_creation", "to_execution"),          # PO -> inbound TO
    ("po_creation", "inventory_buffer"),      # PO pipeline -> buffer comfort

    # Quality disposition impacts
    ("quality", "mo_execution"),              # Quality reject -> rework MO
    ("quality", "inventory_buffer"),          # Quality scrap -> buffer hit
    ("quality", "subcontracting"),            # Quality issues -> subcontracting shift

    # Maintenance impacts production
    ("maintenance", "mo_execution"),          # Maintenance downtime -> MO capacity
    ("maintenance", "subcontracting"),        # Maintenance -> subcontracting overflow

    # Forecast drives everything
    ("forecast_adj", "atp_executor"),         # Forecast change -> ATP availability
    ("forecast_adj", "po_creation"),          # Forecast -> PO quantities
    ("forecast_adj", "inventory_buffer"),     # Forecast -> buffer targets
    ("forecast_adj", "mo_execution"),         # Forecast -> MO planning

    # Rebalancing cross-effects
    ("rebalancing", "to_execution"),          # Rebalancing -> TO creation
    ("rebalancing", "inventory_buffer"),      # Rebalancing -> buffer redistribution

    # TO execution feedback
    ("to_execution", "inventory_buffer"),     # TO receipt -> buffer replenishment

    # Order tracking triggers
    ("order_tracking", "atp_executor"),       # Exception -> ATP reallocation
    ("order_tracking", "rebalancing"),        # Exception -> rebalancing trigger
]


def _build_edge_index() -> torch.Tensor:
    """Build static edge_index tensor from SITE_TGNN_EDGES."""
    src_indices = []
    dst_indices = []
    for src_name, dst_name in SITE_TGNN_EDGES:
        src_idx = TRM_NAME_TO_IDX.get(src_name)
        dst_idx = TRM_NAME_TO_IDX.get(dst_name)
        if src_idx is not None and dst_idx is not None:
            src_indices.append(src_idx)
            dst_indices.append(dst_idx)
    return torch.tensor([src_indices, dst_indices], dtype=torch.long)


# ============================================================================
# SiteTGNN Model
# ============================================================================

class SiteTGNN(nn.Module):
    """Intra-site tGNN (Layer 1.5): learns cross-TRM causal relationships.

    Architecture:
        Input: 11 TRM nodes x input_dim features each
        Graph: 11 nodes, ~22 directed causal edges
        GATv2Conv (input_dim -> 32, 2 heads) -> ELU -> Dropout
        GATv2Conv (64 -> 32, 2 heads) -> ELU -> Dropout
        GRU (64 -> 32, 1 layer) -- temporal state across hourly ticks
        Per-TRM output heads (32 -> 3):
          - urgency_adjustment: [-0.3, +0.3]
          - confidence_modifier: [-0.2, +0.2]
          - coordination_signal: [0, 1]

    Total parameters: ~25K
    Inference time: <5ms on CPU
    """

    HIDDEN_DIM = 32
    NUM_HEADS = 2
    OUTPUT_DIM = 3  # urgency_adj, confidence_mod, coordination_signal

    def __init__(self, input_dim: int = 18):
        super().__init__()
        self.input_dim = input_dim
        self.num_nodes = NUM_TRM_TYPES  # 11

        # Layer 1: GATv2Conv with multi-head attention
        self.conv1 = GATv2Conv(
            in_channels=input_dim,
            out_channels=self.HIDDEN_DIM,
            heads=self.NUM_HEADS,
            concat=True,       # Output: HIDDEN_DIM * NUM_HEADS = 64
            dropout=0.1,
            add_self_loops=True,
            share_weights=False,
        )

        # Layer 2: GATv2Conv
        self.conv2 = GATv2Conv(
            in_channels=self.HIDDEN_DIM * self.NUM_HEADS,  # 64
            out_channels=self.HIDDEN_DIM,
            heads=self.NUM_HEADS,
            concat=True,       # Output: 64
            dropout=0.1,
            add_self_loops=True,
            share_weights=False,
        )

        # Temporal GRU — maintains hidden state across hourly ticks
        self.gru = nn.GRU(
            input_size=self.HIDDEN_DIM * self.NUM_HEADS,  # 64
            hidden_size=self.HIDDEN_DIM,                  # 32
            num_layers=1,
            batch_first=True,
        )

        # Per-TRM output heads (shared architecture, independent weights)
        self.output_heads = nn.ModuleDict({
            name: nn.Sequential(
                nn.Linear(self.HIDDEN_DIM, 16),
                nn.ReLU(),
                nn.Linear(16, self.OUTPUT_DIM),
            )
            for name in TRM_NAMES
        })

        # Dropout
        self.dropout = nn.Dropout(0.1)

        # Static edge topology (registered as buffer, not parameter)
        self.register_buffer("edge_index", _build_edge_index())

    def forward(
        self,
        x: torch.Tensor,
        hidden_state: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Forward pass.

        Args:
            x: Node features [batch_size, num_nodes=11, input_dim=18]
            hidden_state: GRU hidden state [1, batch_size * num_nodes, hidden_dim=32]
                          None for first tick (initialized to zeros).

        Returns:
            output: Per-TRM outputs [batch_size, num_nodes=11, output_dim=3]
            new_hidden: Updated GRU state [1, batch_size * num_nodes, hidden_dim=32]
        """
        batch_size = x.size(0)

        # Expand edge_index for batched graph processing
        # Process each batch element through GATv2Conv
        all_outputs = []

        for b in range(batch_size):
            node_features = x[b]  # [11, input_dim]

            # GATv2 Layer 1
            h = self.conv1(node_features, self.edge_index)
            h = F.elu(h)
            h = self.dropout(h)

            # GATv2 Layer 2
            h = self.conv2(h, self.edge_index)
            h = F.elu(h)
            h = self.dropout(h)

            all_outputs.append(h)

        # Stack batch: [batch_size, num_nodes, hidden*heads=64]
        spatial_out = torch.stack(all_outputs, dim=0)

        # Reshape for GRU: [batch_size * num_nodes, 1, 64]
        gru_in = spatial_out.reshape(batch_size * self.num_nodes, 1, -1)

        # GRU temporal processing
        if hidden_state is None:
            hidden_state = torch.zeros(
                1, batch_size * self.num_nodes, self.HIDDEN_DIM,
                device=x.device, dtype=x.dtype,
            )

        gru_out, new_hidden = self.gru(gru_in, hidden_state)
        # gru_out: [batch_size * num_nodes, 1, 32]

        # Reshape back: [batch_size, num_nodes, 32]
        temporal_out = gru_out.squeeze(1).reshape(batch_size, self.num_nodes, -1)

        # Per-TRM output heads
        outputs = []
        for i, name in enumerate(TRM_NAMES):
            node_repr = temporal_out[:, i, :]  # [batch_size, 32]
            head_out = self.output_heads[name](node_repr)  # [batch_size, 3]
            outputs.append(head_out)

        # Stack: [batch_size, 11, 3]
        output = torch.stack(outputs, dim=1)

        # Apply activation bounds
        # urgency_adjustment: tanh * 0.3 -> [-0.3, +0.3]
        output[:, :, 0] = torch.tanh(output[:, :, 0]) * 0.3
        # confidence_modifier: tanh * 0.2 -> [-0.2, +0.2]
        output[:, :, 1] = torch.tanh(output[:, :, 1]) * 0.2
        # coordination_signal: sigmoid -> [0, 1]
        output[:, :, 2] = torch.sigmoid(output[:, :, 2])

        return output, new_hidden

    def count_parameters(self) -> int:
        """Count total trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
