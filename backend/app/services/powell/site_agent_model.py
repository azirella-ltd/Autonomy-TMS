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

    # HetGAT (cross-TRM graph attention) — disabled by default for backward compat
    het_gat_enabled: bool = False
    het_gat_hidden_dim: int = 64  # Cross-context output dim per TRM node
    het_gat_heads: int = 2        # GAT attention heads

    # Recursive heads — disabled by default for backward compat
    recursive_heads_enabled: bool = False
    num_refinement_steps: int = 3
    adaptive_halt: bool = False
    halt_threshold: float = 0.95

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

    When ``config.het_gat_enabled`` is True, a HiveHetGAT layer sits between
    the shared encoder and the task heads, providing learned cross-TRM context
    for each of the 11 TRM nodes.  Head input becomes
    ``[state_embedding ‖ cross_context]`` (embedding_dim + het_gat_hidden_dim).
    """

    def __init__(self, config: SiteAgentModelConfig):
        super().__init__()
        self.config = config

        # Shared encoder
        self.encoder = SharedStateEncoder(config)

        # Optional HetGAT layer (cross-TRM graph attention)
        self.het_gat = None
        if config.het_gat_enabled:
            from app.models.hive.het_gat_layer import HiveHetGAT, HiveHetGATConfig
            gat_config = HiveHetGATConfig(
                embedding_dim=config.embedding_dim,
                hidden_dim=config.het_gat_hidden_dim,
                num_heads=config.het_gat_heads,
                urgency_dim=config.urgency_vector_dim,
                signal_summary_dim=config.signal_summary_dim,
                dropout=config.dropout,
            )
            self.het_gat = HiveHetGAT(gat_config)

        # Task-specific heads (legacy, used when recursive_heads_enabled=False)
        self.atp_exception_head = ATPExceptionHead(config)
        self.inventory_planning_head = InventoryPlanningHead(config)
        self.po_timing_head = POTimingHead(config)

        # Optional recursive heads (used when recursive_heads_enabled=True)
        self.recursive_heads = None
        if config.recursive_heads_enabled:
            from app.models.hive.recursive_head import (
                RecursiveHeadConfig,
                RECURSIVE_HEAD_REGISTRY,
            )
            # Head input dim: state_embedding + optional cross_context
            head_input_dim = config.embedding_dim
            if config.het_gat_enabled:
                head_input_dim += config.het_gat_hidden_dim

            rh_config = RecursiveHeadConfig(
                input_dim=head_input_dim,
                hidden_dim=config.head_hidden_dim,
                num_refinement_steps=config.num_refinement_steps,
                adaptive_halt=config.adaptive_halt,
                halt_threshold=config.halt_threshold,
                dropout=config.dropout,
            )
            self.recursive_heads = nn.ModuleDict({
                name: cls(rh_config)
                for name, cls in RECURSIVE_HEAD_REGISTRY.items()
            })

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

    def compute_cross_context(
        self,
        state_embedding: torch.Tensor,
        urgency_vector: Optional[torch.Tensor] = None,
        signal_summary: Optional[torch.Tensor] = None,
    ) -> Optional[torch.Tensor]:
        """Run HetGAT to produce per-node cross-TRM context.

        Returns:
            cross_context [B, 11, het_gat_hidden_dim] or None if HetGAT disabled.
        """
        if self.het_gat is None:
            return None
        return self.het_gat(state_embedding, urgency_vector, signal_summary)

    def _get_head_input(
        self,
        state_embedding: torch.Tensor,
        cross_context: Optional[torch.Tensor],
        node_index: int,
    ) -> torch.Tensor:
        """Build head input: state_embedding optionally concatenated with cross_context."""
        if cross_context is not None:
            ctx = cross_context[:, node_index, :]  # [B, het_gat_hidden_dim]
            return torch.cat([state_embedding, ctx], dim=-1)
        return state_embedding

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
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Full forward pass for specified task(s).

        Args:
            task: "atp", "inventory", "po_timing", or any TRM type name (e.g. "atp_executor")
            urgency_vector: Optional 11-dim hive urgency state
            signal_summary: Optional 22-dim signal type counts
            R: Optional refinement step override for CGAR curriculum (recursive heads only)
        """
        # Encode state
        state_embedding = self.encode_state(
            inventory, pipeline, backlog, demand_history, forecasts,
            urgency_vector=urgency_vector,
            signal_summary=signal_summary,
        )

        # Optional HetGAT cross-TRM context
        cross_context = self.compute_cross_context(
            state_embedding, urgency_vector, signal_summary,
        )

        results = {'state_embedding': state_embedding}
        if cross_context is not None:
            results['cross_context'] = cross_context

        # Dispatch to recursive heads when enabled
        if self.recursive_heads is not None:
            R = kwargs.get('R', None)  # CGAR curriculum override
            return self._forward_recursive(
                task, state_embedding, cross_context, results, R=R,
            )

        # Legacy head dispatch
        if task in ("atp", "all") and order_context is not None:
            results['atp'] = self.forward_atp_exception(
                state_embedding, order_context, shortage_qty or torch.zeros_like(order_context[:, :1])
            )

        if task in ("inventory", "all"):
            results['inventory'] = self.forward_inventory_planning(state_embedding)

        if task in ("po_timing", "all") and po_context is not None:
            results['po_timing'] = self.forward_po_timing(state_embedding, po_context)

        return results

    # Mapping from legacy task names to recursive head registry keys + node indices
    _TASK_TO_RECURSIVE_HEAD = {
        "atp": "atp_executor",
        "inventory": "inventory_buffer",
        "po_timing": "po_creation",
    }

    # Full TRM type name → node index (matches het_gat_layer.TRM_NODE_INDEX)
    _TRM_NODE_INDEX = {
        "atp_executor": 0, "order_tracking": 1, "po_creation": 2,
        "rebalancing": 3, "subcontracting": 4, "inventory_buffer": 5,
        "forecast_adj": 6, "quality": 7, "maintenance": 8,
        "mo_execution": 9, "to_execution": 10,
        # Aliases used in RECURSIVE_HEAD_REGISTRY
        "quality_disposition": 7, "maintenance_scheduling": 8,
        "forecast_adjustment": 6,
    }

    def _forward_recursive(
        self,
        task: str,
        state_embedding: torch.Tensor,
        cross_context: Optional[torch.Tensor],
        results: Dict[str, Any],
        R: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Dispatch forward pass through recursive heads.

        Handles both legacy task names (atp, inventory, po_timing) and
        direct TRM type names (atp_executor, safety_stock, etc.).
        """
        # Resolve which heads to run
        heads_to_run = []
        if task == "all":
            heads_to_run = list(self.recursive_heads.keys())
        elif task in self._TASK_TO_RECURSIVE_HEAD:
            heads_to_run = [self._TASK_TO_RECURSIVE_HEAD[task]]
        elif task in self.recursive_heads:
            heads_to_run = [task]
        else:
            logger.warning(f"Unknown task '{task}' for recursive heads")
            return results

        for head_name in heads_to_run:
            head = self.recursive_heads[head_name]
            node_idx = self._TRM_NODE_INDEX.get(head_name, 0)
            head_input = self._get_head_input(state_embedding, cross_context, node_idx)
            out = head(head_input, R=R)

            # Store under legacy task name if applicable
            result_key = head_name
            for legacy_name, reg_name in self._TASK_TO_RECURSIVE_HEAD.items():
                if reg_name == head_name:
                    result_key = legacy_name
                    break
            results[result_key] = out

        return results

    def get_parameter_count(self) -> Dict[str, int]:
        """Get parameter counts for each component"""
        def count_params(module):
            return sum(p.numel() for p in module.parameters())

        counts = {
            'encoder': count_params(self.encoder),
            'atp_exception_head': count_params(self.atp_exception_head),
            'inventory_planning_head': count_params(self.inventory_planning_head),
            'po_timing_head': count_params(self.po_timing_head),
        }
        if self.het_gat is not None:
            counts['het_gat'] = count_params(self.het_gat)
        if self.recursive_heads is not None:
            rh_total = 0
            for name, head in self.recursive_heads.items():
                n = count_params(head)
                counts[f'recursive_{name}'] = n
                rh_total += n
            counts['recursive_heads_total'] = rh_total
        counts['total'] = count_params(self)
        return counts

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
        if self.recursive_heads is not None:
            return list(self.recursive_heads.keys())
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
