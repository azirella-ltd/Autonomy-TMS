"""
SiteAgent Model - Shared Encoder + Task-Specific Heads

The SiteAgentModel uses a shared encoder with multiple task-specific heads.
This is more efficient than separate models and enables transfer learning.

Architecture:
- SharedStateEncoder: Encodes site state into embedding (compute once)
- ATPExceptionHead: Handles ATP shortage decisions
- InventoryPlanningHead: Suggests SS/ROP adjustments
- POTimingHead: Suggests PO timing/expedite decisions

The model outputs bounded adjustments (±20%) to engine baselines,
not raw decisions. This prevents catastrophic errors.
"""

import torch
import torch.nn as nn
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class SiteAgentModelConfig:
    """Configuration for SiteAgent neural network"""
    # Encoder config
    state_dim: int = 64           # Raw state features
    embedding_dim: int = 128      # Shared embedding size
    encoder_layers: int = 2       # Transformer layers in encoder
    encoder_heads: int = 4        # Attention heads

    # Head configs
    head_hidden_dim: int = 64     # Hidden dim for each head
    head_layers: int = 2          # Layers per head

    # Context dimensions
    order_context_dim: int = 16   # Order features for ATP
    po_context_dim: int = 12      # PO features for timing

    # Hive signal dimensions
    urgency_vector_dim: int = 11  # 11-slot UrgencyVector (one per TRM type)
    signal_summary_dim: int = 22  # 22 signal type counts (one per HiveSignalType)

    # Regularization
    dropout: float = 0.1

    # Output bounds
    adjustment_bounds: tuple = (0.8, 1.2)  # ±20%

    # Device
    device: str = "cuda" if torch.cuda.is_available() else "cpu"


class SharedStateEncoder(nn.Module):
    """
    Shared encoder that produces site state embeddings.

    Used by all TRM heads - compute once, use many times.

    Optionally accepts an ``urgency_vector`` (11-dim) from the HiveSignalBus,
    fused via a small projection before the transformer.  When the urgency
    vector is not provided, a zero vector is used (backward-compatible).
    """

    def __init__(self, config: SiteAgentModelConfig):
        super().__init__()
        self.config = config

        # Input projection (physical state → embedding)
        self.input_proj = nn.Linear(config.state_dim, config.embedding_dim)

        # Urgency vector projection (11-dim → small hidden, then added to embedding)
        self.urgency_proj = nn.Sequential(
            nn.Linear(config.urgency_vector_dim, config.embedding_dim // 4),
            nn.ReLU(),
            nn.Linear(config.embedding_dim // 4, config.embedding_dim),
        )

        # Signal summary projection (22-dim counts → embedding, added like urgency)
        self.signal_summary_proj = nn.Sequential(
            nn.Linear(config.signal_summary_dim, config.embedding_dim // 4),
            nn.ReLU(),
            nn.Linear(config.embedding_dim // 4, config.embedding_dim),
        )

        # Transformer encoder for temporal patterns
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=config.embedding_dim,
            nhead=config.encoder_heads,
            dim_feedforward=config.embedding_dim * 4,
            dropout=config.dropout,
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(
            encoder_layer,
            num_layers=config.encoder_layers
        )

        # Layer norm for stable training
        self.layer_norm = nn.LayerNorm(config.embedding_dim)

    def forward(
        self,
        inventory: torch.Tensor,      # [batch, products]
        pipeline: torch.Tensor,       # [batch, products, lead_time_buckets]
        backlog: torch.Tensor,        # [batch, products]
        demand_history: torch.Tensor, # [batch, products, history_window]
        forecasts: torch.Tensor,      # [batch, products, forecast_horizon]
        urgency_vector: Optional[torch.Tensor] = None,   # [batch, 11]
        signal_summary: Optional[torch.Tensor] = None,   # [batch, 22]
    ) -> torch.Tensor:
        """
        Encode site state into shared embedding.

        Args:
            urgency_vector: Optional 11-dim UrgencyVector from HiveSignalBus.
                When provided, its projection is *added* to the physical state
                embedding before the transformer — acting as a pheromone layer
                that biases attention toward areas of current urgency.
            signal_summary: Optional 22-dim signal type counts from
                HiveSignalBus.signal_summary().  Adds an additional pheromone
                layer that captures *which* types of signals are active.

        Returns: [batch, embedding_dim] site embedding
        """
        # Flatten temporal dimensions
        pipeline_flat = pipeline.flatten(start_dim=1)
        demand_flat = demand_history.flatten(start_dim=1)
        forecast_flat = forecasts.flatten(start_dim=1)

        # Concatenate all physical state features
        state = torch.cat([
            inventory,
            pipeline_flat,
            backlog,
            demand_flat,
            forecast_flat
        ], dim=-1)

        # Project to embedding dim
        x = self.input_proj(state)

        # Fuse urgency vector (additive — zero vector when None)
        if urgency_vector is not None:
            x = x + self.urgency_proj(urgency_vector)

        # Fuse signal summary (additive — zero vector when None)
        if signal_summary is not None:
            x = x + self.signal_summary_proj(signal_summary)

        # Add sequence dimension for transformer (single "token")
        x = x.unsqueeze(1)

        # Self-attention
        x = self.transformer(x)

        # Remove sequence dimension and normalize
        x = x.squeeze(1)
        x = self.layer_norm(x)

        return x


class ATPExceptionHead(nn.Module):
    """
    Head for ATP exception decisions.

    Decides how to handle shortages: partial fill, substitute, split, reject.
    """

    def __init__(self, config: SiteAgentModelConfig):
        super().__init__()

        # Context projection (order info)
        self.context_proj = nn.Linear(config.order_context_dim, config.head_hidden_dim)

        # Decision layers
        self.layers = nn.Sequential(
            nn.Linear(config.embedding_dim + config.head_hidden_dim, config.head_hidden_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.head_hidden_dim, config.head_hidden_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout),
        )

        # Output heads
        self.action_head = nn.Linear(config.head_hidden_dim, 4)  # partial, substitute, split, reject
        self.fill_rate_head = nn.Linear(config.head_hidden_dim, 1)  # suggested fill %
        self.confidence_head = nn.Linear(config.head_hidden_dim, 1)

    def forward(
        self,
        state_embedding: torch.Tensor,  # [batch, embedding_dim]
        order_context: torch.Tensor,     # [batch, order_context_dim]
        shortage_qty: torch.Tensor       # [batch, 1]
    ) -> Dict[str, torch.Tensor]:
        """
        Decide how to handle ATP exception.

        Returns dict with:
        - action_probs: [batch, 4] probability over actions
        - fill_rate: [batch, 1] suggested partial fill rate (0-1)
        - confidence: [batch, 1] decision confidence (0-1)
        """
        # Project context
        ctx = self.context_proj(order_context)

        # Combine with state
        x = torch.cat([state_embedding, ctx], dim=-1)
        x = self.layers(x)

        return {
            'action_probs': torch.softmax(self.action_head(x), dim=-1),
            'fill_rate': torch.sigmoid(self.fill_rate_head(x)),
            'confidence': torch.sigmoid(self.confidence_head(x))
        }


class InventoryPlanningHead(nn.Module):
    """
    Head for inventory planning adjustments.

    Suggests adjustments to safety stock multipliers and reorder points.
    Does NOT compute SS formula - that's the deterministic engine.
    """

    def __init__(self, config: SiteAgentModelConfig):
        super().__init__()

        self.layers = nn.Sequential(
            nn.Linear(config.embedding_dim, config.head_hidden_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.head_hidden_dim, config.head_hidden_dim),
            nn.ReLU(),
        )

        # Output: adjustment multipliers (centered at 1.0)
        self.ss_multiplier_head = nn.Linear(config.head_hidden_dim, 1)
        self.rop_multiplier_head = nn.Linear(config.head_hidden_dim, 1)
        self.confidence_head = nn.Linear(config.head_hidden_dim, 1)

        # Bounds
        self.min_mult = config.adjustment_bounds[0]
        self.max_mult = config.adjustment_bounds[1]

    def forward(
        self,
        state_embedding: torch.Tensor
    ) -> Dict[str, torch.Tensor]:
        """
        Suggest inventory parameter adjustments.

        Returns multipliers in [0.8, 1.2] range (bounded).
        """
        x = self.layers(state_embedding)

        # Raw outputs (unbounded)
        ss_raw = self.ss_multiplier_head(x)
        rop_raw = self.rop_multiplier_head(x)

        # Apply tanh and scale to bounds: tanh output in [-1,1] -> [0.8, 1.2]
        range_size = self.max_mult - self.min_mult
        center = (self.max_mult + self.min_mult) / 2

        ss_mult = torch.tanh(ss_raw) * (range_size / 2) + center
        rop_mult = torch.tanh(rop_raw) * (range_size / 2) + center

        return {
            'ss_multiplier': ss_mult,
            'rop_multiplier': rop_mult,
            'confidence': torch.sigmoid(self.confidence_head(x))
        }


class POTimingHead(nn.Module):
    """
    Head for PO timing decisions.

    Suggests whether to order now vs wait, and expedite decisions.
    """

    def __init__(self, config: SiteAgentModelConfig):
        super().__init__()

        # PO context projection
        self.context_proj = nn.Linear(config.po_context_dim, config.head_hidden_dim)

        self.layers = nn.Sequential(
            nn.Linear(config.embedding_dim + config.head_hidden_dim, config.head_hidden_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.head_hidden_dim, config.head_hidden_dim),
            nn.ReLU(),
        )

        # Outputs
        self.timing_head = nn.Linear(config.head_hidden_dim, 3)  # now, wait, split
        self.expedite_head = nn.Linear(config.head_hidden_dim, 1)  # expedite probability
        self.days_offset_head = nn.Linear(config.head_hidden_dim, 1)  # timing adjustment
        self.confidence_head = nn.Linear(config.head_hidden_dim, 1)

    def forward(
        self,
        state_embedding: torch.Tensor,
        po_context: torch.Tensor
    ) -> Dict[str, torch.Tensor]:
        """
        Suggest PO timing adjustments.
        """
        ctx = self.context_proj(po_context)
        x = torch.cat([state_embedding, ctx], dim=-1)
        x = self.layers(x)

        # Days offset bounded to ±7 days
        days_raw = self.days_offset_head(x)
        days_offset = torch.tanh(days_raw) * 7

        return {
            'timing_probs': torch.softmax(self.timing_head(x), dim=-1),
            'expedite_prob': torch.sigmoid(self.expedite_head(x)),
            'days_offset': days_offset,
            'confidence': torch.sigmoid(self.confidence_head(x))
        }


class SiteAgentModel(nn.Module):
    """
    Complete SiteAgent model with shared encoder and task heads.
    """

    def __init__(self, config: SiteAgentModelConfig):
        super().__init__()
        self.config = config

        # Shared encoder
        self.encoder = SharedStateEncoder(config)

        # Task-specific heads
        self.atp_exception_head = ATPExceptionHead(config)
        self.inventory_planning_head = InventoryPlanningHead(config)
        self.po_timing_head = POTimingHead(config)

    def encode_state(
        self,
        inventory: torch.Tensor,
        pipeline: torch.Tensor,
        backlog: torch.Tensor,
        demand_history: torch.Tensor,
        forecasts: torch.Tensor,
        urgency_vector: Optional[torch.Tensor] = None,
        signal_summary: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """Encode state once, use for all heads"""
        return self.encoder(
            inventory, pipeline, backlog, demand_history, forecasts,
            urgency_vector=urgency_vector,
            signal_summary=signal_summary,
        )

    def forward_atp_exception(
        self,
        state_embedding: torch.Tensor,
        order_context: torch.Tensor,
        shortage_qty: torch.Tensor
    ) -> Dict[str, torch.Tensor]:
        """ATP exception decision"""
        return self.atp_exception_head(state_embedding, order_context, shortage_qty)

    def forward_inventory_planning(
        self,
        state_embedding: torch.Tensor
    ) -> Dict[str, torch.Tensor]:
        """Inventory planning adjustments"""
        return self.inventory_planning_head(state_embedding)

    def forward_po_timing(
        self,
        state_embedding: torch.Tensor,
        po_context: torch.Tensor
    ) -> Dict[str, torch.Tensor]:
        """PO timing decisions"""
        return self.po_timing_head(state_embedding, po_context)

    def forward(
        self,
        inventory: torch.Tensor,
        pipeline: torch.Tensor,
        backlog: torch.Tensor,
        demand_history: torch.Tensor,
        forecasts: torch.Tensor,
        task: str = "all",
        order_context: Optional[torch.Tensor] = None,
        shortage_qty: Optional[torch.Tensor] = None,
        po_context: Optional[torch.Tensor] = None,
        urgency_vector: Optional[torch.Tensor] = None,
        signal_summary: Optional[torch.Tensor] = None,
    ) -> Dict[str, Any]:
        """
        Full forward pass for specified task(s).

        Args:
            task: "atp", "inventory", "po_timing", or "all"
            urgency_vector: Optional 11-dim hive urgency state
            signal_summary: Optional 22-dim signal type counts
        """
        # Encode state
        state_embedding = self.encode_state(
            inventory, pipeline, backlog, demand_history, forecasts,
            urgency_vector=urgency_vector,
            signal_summary=signal_summary,
        )

        results = {'state_embedding': state_embedding}

        if task in ("atp", "all") and order_context is not None:
            results['atp'] = self.forward_atp_exception(
                state_embedding, order_context, shortage_qty or torch.zeros_like(order_context[:, :1])
            )

        if task in ("inventory", "all"):
            results['inventory'] = self.forward_inventory_planning(state_embedding)

        if task in ("po_timing", "all") and po_context is not None:
            results['po_timing'] = self.forward_po_timing(state_embedding, po_context)

        return results

    def get_parameter_count(self) -> Dict[str, int]:
        """Get parameter counts for each component"""
        def count_params(module):
            return sum(p.numel() for p in module.parameters())

        return {
            'encoder': count_params(self.encoder),
            'atp_exception_head': count_params(self.atp_exception_head),
            'inventory_planning_head': count_params(self.inventory_planning_head),
            'po_timing_head': count_params(self.po_timing_head),
            'total': count_params(self)
        }

    def freeze_encoder(self):
        """Freeze encoder weights (for fine-tuning heads only)"""
        for param in self.encoder.parameters():
            param.requires_grad = False

    def unfreeze_encoder(self):
        """Unfreeze encoder weights"""
        for param in self.encoder.parameters():
            param.requires_grad = True

    def freeze_head(self, head_name: str):
        """Freeze a specific head"""
        head = getattr(self, f"{head_name}_head", None)
        if head:
            for param in head.parameters():
                param.requires_grad = False

    def get_head_names(self) -> List[str]:
        """Get list of head names"""
        return ['atp_exception', 'inventory_planning', 'po_timing']

    # Feature names for attribution mapping
    STATE_FEATURE_NAMES = [
        'inventory', 'pipeline', 'backlog', 'demand_history', 'forecasts',
        'urgency_vector', 'signal_summary',
    ]

    def predict_with_attribution(
        self,
        task: str,
        inventory: torch.Tensor,
        pipeline: torch.Tensor,
        backlog: torch.Tensor,
        demand_history: torch.Tensor,
        forecasts: torch.Tensor,
        order_context: Optional[torch.Tensor] = None,
        shortage_qty: Optional[torch.Tensor] = None,
        po_context: Optional[torch.Tensor] = None,
        urgency_vector: Optional[torch.Tensor] = None,
        signal_summary: Optional[torch.Tensor] = None,
    ) -> Dict[str, Any]:
        """
        Run inference with gradient-based input saliency for explainability.

        Computes which input features the model weighted most heavily for
        its decision, using gradient magnitude as the attribution signal.

        Args:
            task: "atp", "inventory", "po_timing", or "all"
            inventory, pipeline, backlog, demand_history, forecasts: State inputs
            order_context, shortage_qty: ATP-specific context
            po_context: PO-specific context
            urgency_vector: Optional 11-dim hive urgency state
            signal_summary: Optional 22-dim signal type counts

        Returns:
            Dict with standard outputs plus:
            - 'attribution': Dict[str, float] mapping feature groups to importance
        """
        # Enable gradients on a copy of the inputs
        inv = inventory.detach().clone().requires_grad_(True)
        pipe = pipeline.detach().clone().requires_grad_(True)
        blog = backlog.detach().clone().requires_grad_(True)
        dem = demand_history.detach().clone().requires_grad_(True)
        fcst = forecasts.detach().clone().requires_grad_(True)
        uv = None
        if urgency_vector is not None:
            uv = urgency_vector.detach().clone().requires_grad_(True)
        ss = None
        if signal_summary is not None:
            ss = signal_summary.detach().clone().requires_grad_(True)

        # Forward pass
        results = self.forward(
            inventory=inv,
            pipeline=pipe,
            backlog=blog,
            demand_history=dem,
            forecasts=fcst,
            task=task,
            order_context=order_context,
            shortage_qty=shortage_qty,
            po_context=po_context,
            urgency_vector=uv,
            signal_summary=ss,
        )

        # Find the primary output to compute gradients against
        target = None
        if task == 'atp' and 'atp' in results:
            atp_out = results['atp']
            target = atp_out['confidence'].sum() + atp_out['action_probs'].max(dim=-1).values.sum()
        elif task == 'inventory' and 'inventory' in results:
            inv_out = results['inventory']
            target = inv_out['ss_multiplier'].sum() + inv_out['confidence'].sum()
        elif task == 'po_timing' and 'po_timing' in results:
            po_out = results['po_timing']
            target = po_out['confidence'].sum() + po_out['timing_probs'].max(dim=-1).values.sum()
        elif 'atp' in results:
            target = results['atp']['confidence'].sum()
        elif 'inventory' in results:
            target = results['inventory']['confidence'].sum()

        attribution = {}
        if target is not None:
            target.backward(retain_graph=False)

            # Collect gradient magnitudes per input group
            grad_groups = {
                'inventory': inv.grad,
                'pipeline': pipe.grad,
                'backlog': blog.grad,
                'demand_history': dem.grad,
                'forecasts': fcst.grad,
            }
            if uv is not None and uv.grad is not None:
                grad_groups['urgency_vector'] = uv.grad
            if ss is not None and ss.grad is not None:
                grad_groups['signal_summary'] = ss.grad

            saliency = {}
            for name, grad in grad_groups.items():
                if grad is not None:
                    saliency[name] = grad.abs().sum().item()
                else:
                    saliency[name] = 0.0

            # Normalize to 0-1
            total = sum(saliency.values())
            if total > 0:
                attribution = {k: v / total for k, v in saliency.items()}
            else:
                attribution = saliency

        results['attribution'] = dict(sorted(
            attribution.items(), key=lambda x: x[1], reverse=True
        ))
        return results


def create_site_agent_model(
    config: Optional[SiteAgentModelConfig] = None
) -> SiteAgentModel:
    """Factory function to create SiteAgentModel"""
    config = config or SiteAgentModelConfig()
    model = SiteAgentModel(config)
    model = model.to(config.device)
    return model
