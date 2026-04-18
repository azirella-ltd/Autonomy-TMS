"""
SiteAgent Model - Shared Encoder + Task-Specific Heads

Re-exports from azirella_data_model.powell.site_agent_model (Core) and
extends with TMS-specific features (HetGAT, recursive heads).

The pure PyTorch nn.Module implementations live in Core. This module
provides backward-compatible imports and the TMS-specific factory that
wires in HetGAT and recursive heads from app.models.hive.*.
"""

import logging
from typing import Dict, List, Optional, Any

import torch
import torch.nn as nn

# Re-export all Core classes for backward compatibility
from azirella_data_model.powell.site_agent_model import (  # noqa: F401
    SiteAgentModelConfig,
    SharedStateEncoder,
    ATPExceptionHead,
    InventoryPlanningHead,
    POTimingHead,
    SiteAgentModel as _CoreSiteAgentModel,
    create_site_agent_model as _core_create_site_agent_model,
)

logger = logging.getLogger(__name__)


class SiteAgentModel(_CoreSiteAgentModel):
    """TMS-specific SiteAgentModel that auto-wires HetGAT and recursive heads.

    When config.het_gat_enabled or config.recursive_heads_enabled is True,
    this subclass imports the TMS-specific modules and injects them into
    the Core base class.
    """

    def __init__(self, config: SiteAgentModelConfig):
        # Build optional TMS-specific modules
        het_gat = None
        recursive_heads = None

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
            het_gat = HiveHetGAT(gat_config)

        if config.recursive_heads_enabled:
            from app.models.hive.recursive_head import (
                RecursiveHeadConfig,
                RECURSIVE_HEAD_REGISTRY,
            )
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
            recursive_heads = nn.ModuleDict({
                name: cls(rh_config)
                for name, cls in RECURSIVE_HEAD_REGISTRY.items()
            })

        super().__init__(config, het_gat=het_gat, recursive_heads=recursive_heads)


def create_site_agent_model(
    config: Optional[SiteAgentModelConfig] = None
) -> SiteAgentModel:
    """Factory function to create TMS SiteAgentModel with HetGAT/recursive heads."""
    config = config or SiteAgentModelConfig()
    model = SiteAgentModel(config)
    model = model.to(config.device)
    return model
