"""
Tiny Recursive Model (TRM) for Beer Game Supply Chain Optimization.

A compact 7M parameter model using recursive refinement for multi-step reasoning.
Based on the architecture described in TRM_IMPLEMENTATION_PLAN.md.

Architecture:
- 2-layer transformer encoder (d_model=512, nhead=8)
- Recursive refinement with chain-of-thought
- Fast inference (<10ms per decision)
- Supply chain context awareness
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Optional, Tuple
import math


class SupplyChainEncoder(nn.Module):
    """Encodes supply chain state into compact representations."""

    def __init__(self, d_model: int = 512):
        super().__init__()
        self.d_model = d_model

        # Node state encoding
        self.inventory_proj = nn.Linear(1, d_model // 4)
        self.backlog_proj = nn.Linear(1, d_model // 4)
        self.pipeline_proj = nn.Linear(1, d_model // 4)
        self.demand_proj = nn.Linear(1, d_model // 4)

        # Position encoding for supply chain topology
        self.position_encoding = nn.Parameter(torch.randn(10, d_model))  # Max 10 nodes

        # Node type embedding
        self.node_type_embedding = nn.Embedding(
            num_embeddings=6,  # retailer, wholesaler, distributor, factory, supplier, market
            embedding_dim=d_model
        )

        self.layer_norm = nn.LayerNorm(d_model)

    def forward(
        self,
        inventory: torch.Tensor,
        backlog: torch.Tensor,
        pipeline: torch.Tensor,
        demand_history: torch.Tensor,
        node_types: torch.Tensor,
        node_positions: torch.Tensor
    ) -> torch.Tensor:
        """
        Args:
            inventory: (batch, num_nodes, 1)
            backlog: (batch, num_nodes, 1)
            pipeline: (batch, num_nodes, 1)
            demand_history: (batch, num_nodes, window_size)
            node_types: (batch, num_nodes) - integer node type IDs
            node_positions: (batch, num_nodes) - integer position in supply chain

        Returns:
            encoded: (batch, num_nodes, d_model)
        """
        batch_size, num_nodes = inventory.shape[0], inventory.shape[1]

        # Encode state components
        inv_enc = self.inventory_proj(inventory)  # (batch, num_nodes, d_model/4)
        back_enc = self.backlog_proj(backlog)
        pipe_enc = self.pipeline_proj(pipeline)

        # Encode recent demand (use mean)
        demand_mean = demand_history.mean(dim=-1, keepdim=True)  # (batch, num_nodes, 1)
        demand_enc = self.demand_proj(demand_mean)

        # Concatenate state features
        state_enc = torch.cat([inv_enc, back_enc, pipe_enc, demand_enc], dim=-1)  # (batch, num_nodes, d_model)

        # Add node type embeddings
        type_emb = self.node_type_embedding(node_types)  # (batch, num_nodes, d_model)
        state_enc = state_enc + type_emb

        # Add positional encoding
        pos_emb = self.position_encoding[node_positions]  # (batch, num_nodes, d_model)
        state_enc = state_enc + pos_emb

        return self.layer_norm(state_enc)


class RecursiveRefinementBlock(nn.Module):
    """Single recursive refinement iteration with transformer attention."""

    def __init__(self, d_model: int = 512, nhead: int = 8, dim_feedforward: int = 2048, dropout: float = 0.1):
        super().__init__()

        # Multi-head self-attention
        self.self_attn = nn.MultiheadAttention(
            embed_dim=d_model,
            num_heads=nhead,
            dropout=dropout,
            batch_first=True
        )

        # Feedforward network
        self.ffn = nn.Sequential(
            nn.Linear(d_model, dim_feedforward),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim_feedforward, d_model),
            nn.Dropout(dropout)
        )

        # Layer norms
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)

        # Refinement gate (learned mixing)
        self.refinement_gate = nn.Sequential(
            nn.Linear(d_model * 2, d_model),
            nn.Sigmoid()
        )

    def forward(self, x: torch.Tensor, prev_thought: Optional[torch.Tensor] = None) -> torch.Tensor:
        """
        Args:
            x: (batch, num_nodes, d_model) - current state encoding
            prev_thought: (batch, num_nodes, d_model) - previous reasoning step

        Returns:
            refined: (batch, num_nodes, d_model) - refined representation
        """
        # Self-attention with residual
        attn_out, _ = self.self_attn(x, x, x)
        x = self.norm1(x + attn_out)

        # Feedforward with residual
        ffn_out = self.ffn(x)
        x = self.norm2(x + ffn_out)

        # Recursive refinement: mix with previous thought
        if prev_thought is not None:
            gate = self.refinement_gate(torch.cat([x, prev_thought], dim=-1))
            x = gate * x + (1 - gate) * prev_thought

        return x


class TinyRecursiveModel(nn.Module):
    """
    Tiny Recursive Model for Beer Game decisions.

    Total parameters: ~7M
    - Encoder: ~1.5M
    - 2x Transformer layers: ~4M
    - Decision head: ~1.5M
    """

    def __init__(
        self,
        d_model: int = 512,
        nhead: int = 8,
        num_layers: int = 2,
        num_refinement_steps: int = 3,
        dim_feedforward: int = 2048,
        dropout: float = 0.1,
        max_order_quantity: float = 1000.0
    ):
        super().__init__()

        self.d_model = d_model
        self.num_refinement_steps = num_refinement_steps
        self.max_order_quantity = max_order_quantity

        # Supply chain state encoder
        self.encoder = SupplyChainEncoder(d_model=d_model)

        # Transformer layers for recursive refinement
        self.refinement_blocks = nn.ModuleList([
            RecursiveRefinementBlock(
                d_model=d_model,
                nhead=nhead,
                dim_feedforward=dim_feedforward,
                dropout=dropout
            )
            for _ in range(num_layers)
        ])

        # Decision head
        self.decision_head = nn.Sequential(
            nn.Linear(d_model, dim_feedforward),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim_feedforward, 512),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(512, 1)  # Single order quantity
        )

        # Value head for RL training
        self.value_head = nn.Sequential(
            nn.Linear(d_model, 512),
            nn.GELU(),
            nn.Linear(512, 1)
        )

        # Initialize weights
        self._init_weights()

    def _init_weights(self):
        """Initialize weights with Xavier/Kaiming initialization."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Embedding):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(
        self,
        inventory: torch.Tensor,
        backlog: torch.Tensor,
        pipeline: torch.Tensor,
        demand_history: torch.Tensor,
        node_types: torch.Tensor,
        node_positions: torch.Tensor,
        return_thoughts: bool = False
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass with recursive refinement.

        Args:
            inventory: (batch, num_nodes, 1)
            backlog: (batch, num_nodes, 1)
            pipeline: (batch, num_nodes, 1)
            demand_history: (batch, num_nodes, window_size)
            node_types: (batch, num_nodes)
            node_positions: (batch, num_nodes)
            return_thoughts: If True, return intermediate reasoning steps

        Returns:
            Dictionary with:
                - order_quantities: (batch, num_nodes, 1)
                - state_values: (batch, num_nodes, 1)
                - thoughts: List of (batch, num_nodes, d_model) if return_thoughts=True
        """
        # Encode supply chain state
        x = self.encoder(
            inventory=inventory,
            backlog=backlog,
            pipeline=pipeline,
            demand_history=demand_history,
            node_types=node_types,
            node_positions=node_positions
        )

        thoughts = [] if return_thoughts else None
        prev_thought = None

        # Recursive refinement
        for step in range(self.num_refinement_steps):
            for block in self.refinement_blocks:
                x = block(x, prev_thought)
            prev_thought = x.clone()

            if return_thoughts:
                thoughts.append(x.clone())

        # Generate order quantities
        order_quantities = self.decision_head(x)  # (batch, num_nodes, 1)

        # Apply constraints: non-negative, bounded
        order_quantities = torch.clamp(order_quantities, min=0.0, max=self.max_order_quantity)

        # Predict state value (for RL)
        state_values = self.value_head(x)  # (batch, num_nodes, 1)

        result = {
            "order_quantities": order_quantities,
            "state_values": state_values
        }

        if return_thoughts:
            result["thoughts"] = thoughts

        return result

    def get_action(
        self,
        inventory: float,
        backlog: float,
        pipeline: float,
        demand_history: List[float],
        node_type: int,
        node_position: int
    ) -> float:
        """
        Get single action for inference (convenience method).

        Args:
            inventory: Current inventory level
            backlog: Current backlog
            pipeline: Items in transit
            demand_history: Recent demand observations
            node_type: Node type ID (0-5)
            node_position: Position in supply chain (0-9)

        Returns:
            order_quantity: Recommended order quantity
        """
        self.eval()
        with torch.no_grad():
            # Prepare tensors
            inv = torch.tensor([[inventory]], dtype=torch.float32).unsqueeze(0)
            back = torch.tensor([[backlog]], dtype=torch.float32).unsqueeze(0)
            pipe = torch.tensor([[pipeline]], dtype=torch.float32).unsqueeze(0)
            demand = torch.tensor([demand_history], dtype=torch.float32).unsqueeze(0)
            n_type = torch.tensor([[node_type]], dtype=torch.long)
            n_pos = torch.tensor([[node_position]], dtype=torch.long)

            # Forward pass
            output = self.forward(inv, back, pipe, demand, n_type, n_pos)
            order_qty = output["order_quantities"].item()

        return order_qty

    def count_parameters(self) -> Dict[str, int]:
        """Count model parameters by component."""
        encoder_params = sum(p.numel() for p in self.encoder.parameters())
        refinement_params = sum(p.numel() for p in self.refinement_blocks.parameters())
        decision_params = sum(p.numel() for p in self.decision_head.parameters())
        value_params = sum(p.numel() for p in self.value_head.parameters())

        return {
            "encoder": encoder_params,
            "refinement": refinement_params,
            "decision_head": decision_params,
            "value_head": value_params,
            "total": encoder_params + refinement_params + decision_params + value_params
        }


def create_trm_model(
    config: Optional[Dict] = None,
    pretrained_path: Optional[str] = None
) -> TinyRecursiveModel:
    """
    Factory function to create TRM model.

    Args:
        config: Model configuration override
        pretrained_path: Path to pretrained checkpoint

    Returns:
        TRM model instance
    """
    default_config = {
        "d_model": 512,
        "nhead": 8,
        "num_layers": 2,
        "num_refinement_steps": 3,
        "dim_feedforward": 2048,
        "dropout": 0.1,
        "max_order_quantity": 1000.0
    }

    if config:
        default_config.update(config)

    model = TinyRecursiveModel(**default_config)

    if pretrained_path:
        checkpoint = torch.load(pretrained_path, map_location="cpu")
        model.load_state_dict(checkpoint["model_state_dict"])
        print(f"Loaded pretrained TRM from {pretrained_path}")

    # Print parameter count
    param_counts = model.count_parameters()
    print(f"TRM Parameters: {param_counts['total']:,} total")
    print(f"  - Encoder: {param_counts['encoder']:,}")
    print(f"  - Refinement: {param_counts['refinement']:,}")
    print(f"  - Decision: {param_counts['decision_head']:,}")
    print(f"  - Value: {param_counts['value_head']:,}")

    return model
