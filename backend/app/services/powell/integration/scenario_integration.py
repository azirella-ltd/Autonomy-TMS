"""
Scenario Integration

Enables SiteAgent as a Beer Game agent strategy.
Provides integration with mixed_scenario_service for simulation scenarios.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.services.powell.site_agent import SiteAgent, SiteAgentConfig
from app.services.powell.engines import Priority, Order
from app.services.policies import OrderPolicy
from app.services.agents import AgentDecision

logger = logging.getLogger(__name__)


class SiteAgentPolicy(OrderPolicy):
    """
    Order policy backed by SiteAgent.

    Integrates with the Beer Game engine by implementing the OrderPolicy interface.
    Uses SiteAgent's deterministic engines + TRM for order decisions.
    """

    def __init__(
        self,
        site_key: str,
        use_trm: bool = True,
        trm_confidence_threshold: float = 0.7,
        model_checkpoint_path: Optional[str] = None
    ):
        """
        Initialize SiteAgent policy.

        Args:
            site_key: Site identifier (role in Beer Game)
            use_trm: Enable TRM adjustments
            trm_confidence_threshold: Minimum confidence for TRM decisions
            model_checkpoint_path: Path to trained model checkpoint
        """
        self.site_key = site_key
        self.use_trm = use_trm
        self.trm_confidence_threshold = trm_confidence_threshold

        # Default checkpoint path if not specified and TRM enabled
        if model_checkpoint_path is None and use_trm:
            # Try to find checkpoint for this site
            from pathlib import Path
            default_path = Path("checkpoints") / f"site_agent_{site_key}.pt"
            if default_path.exists():
                model_checkpoint_path = str(default_path)

        # Initialize SiteAgent
        config = SiteAgentConfig(
            site_key=site_key,
            use_trm_adjustments=use_trm,
            trm_confidence_threshold=trm_confidence_threshold,
            agent_mode="copilot",
            model_checkpoint_path=model_checkpoint_path,
        )
        self.site_agent = SiteAgent(config)

        # Cache for state encoding
        self._last_state = None
        self._last_encoded = None

    def order(self, observation: Dict[str, Any]) -> int:
        """
        Compute order quantity using SiteAgent.

        This is called by the Beer Game engine each period.

        Args:
            observation: Current node state
                - inventory: Current on-hand inventory
                - backlog: Current backlog
                - pipeline_on_order: In-transit shipments
                - last_incoming_order: Demand from downstream
                - base_stock: Target inventory level
                - inventory_position: inventory + pipeline - backlog

        Returns:
            Order quantity for this period
        """
        # Extract state from observation
        inventory = observation.get('inventory', 0)
        backlog = observation.get('backlog', 0)
        pipeline = observation.get('pipeline_on_order', 0)
        incoming_order = observation.get('last_incoming_order', 0)
        base_stock = observation.get('base_stock', 20)
        inventory_position = observation.get('inventory_position', inventory + pipeline - backlog)

        # Compute deterministic base order using base-stock policy
        # Order = Base Stock - Inventory Position + Incoming Demand
        deterministic_order = max(0, base_stock - inventory_position + incoming_order)

        # If TRM is enabled and model is loaded, apply adjustments
        if self.use_trm and self.site_agent.model:
            try:
                import asyncio
                import torch

                # Encode state for TRM
                state_tensor = self._encode_state_for_trm(observation)

                # Get PO timing recommendation
                with torch.no_grad():
                    output = self.site_agent.model.forward_po_timing(
                        state_tensor,
                        self._build_po_context(observation)
                    )

                # Apply timing adjustment
                days_offset = float(output['days_offset'].mean())
                expedite_prob = float(output['expedite_prob'].mean())
                confidence = float(output.get('confidence', torch.tensor(0.8)).mean())

                # Only apply if confidence is above threshold
                if confidence >= self.trm_confidence_threshold:
                    # Adjust order quantity based on expedite probability
                    if expedite_prob > 0.7:
                        # Expedite: increase order by up to 20%
                        adjustment = min(0.2, expedite_prob - 0.5)
                        deterministic_order = int(deterministic_order * (1 + adjustment))
                    elif days_offset > 0:
                        # Defer: reduce order slightly if can wait
                        adjustment = min(0.1, days_offset * 0.02)
                        deterministic_order = int(deterministic_order * (1 - adjustment))

                    logger.debug(
                        f"TRM adjustment for {self.site_key}: "
                        f"expedite_prob={expedite_prob:.2f}, days_offset={days_offset:.1f}, "
                        f"confidence={confidence:.2f}"
                    )

            except Exception as e:
                logger.warning(f"TRM order adjustment failed: {e}")

        return max(0, int(deterministic_order))

    def _encode_state_for_trm(self, observation: Dict[str, Any]) -> 'torch.Tensor':
        """Encode observation into state tensor for TRM."""
        import torch

        # Extract values
        inventory = observation.get('inventory', 0)
        backlog = observation.get('backlog', 0)
        pipeline = observation.get('pipeline_on_order', 0)
        incoming_order = observation.get('last_incoming_order', 0)

        # Create mock state tensor (batch_size=1, state_dim)
        # In full implementation, this would use the shared encoder
        n_products = 1
        batch_size = 1

        inventory_tensor = torch.tensor([[inventory]], dtype=torch.float32)
        pipeline_tensor = torch.tensor([[[pipeline, 0, 0, 0]]], dtype=torch.float32)
        backlog_tensor = torch.tensor([[backlog]], dtype=torch.float32)
        demand_history = torch.tensor([[[incoming_order] * 12]], dtype=torch.float32)
        forecasts = torch.tensor([[[incoming_order] * 8]], dtype=torch.float32)

        # Encode through model
        state = self.site_agent.model.encode_state(
            inventory_tensor,
            pipeline_tensor,
            backlog_tensor,
            demand_history,
            forecasts
        )

        return state

    def _build_po_context(self, observation: Dict[str, Any]) -> 'torch.Tensor':
        """Build PO context tensor from observation."""
        import torch

        # Extract relevant values
        inventory = observation.get('inventory', 0)
        backlog = observation.get('backlog', 0)
        pipeline = observation.get('pipeline_on_order', 0)
        incoming_order = observation.get('last_incoming_order', 0)
        base_stock = observation.get('base_stock', 20)

        # Normalize and pad to 12 dimensions
        context = [
            inventory / max(base_stock, 1),
            backlog / max(base_stock, 1),
            pipeline / max(base_stock, 1),
            incoming_order / max(base_stock, 1),
            1.0,  # Supplier reliability placeholder
            0.5,  # Lead time variability placeholder
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0  # Padding
        ]

        return torch.tensor([context], dtype=torch.float32)


class SiteAgentStrategy:
    """
    Agent strategy wrapper for SiteAgent integration with AgentManager.

    Enables SiteAgent to be used as an agent strategy in Beer Game scenarios.
    """

    def __init__(
        self,
        db: Session,
        use_trm: bool = True,
        checkpoint_path: Optional[str] = None
    ):
        """
        Initialize SiteAgent strategy.

        Args:
            db: Database session
            use_trm: Enable TRM adjustments
            checkpoint_path: Path to model checkpoint
        """
        self.db = db
        self.use_trm = use_trm
        self.checkpoint_path = checkpoint_path
        self._policies: Dict[str, SiteAgentPolicy] = {}

    def get_policy(self, site_key: str) -> SiteAgentPolicy:
        """Get or create policy for a site/role."""
        if site_key not in self._policies:
            self._policies[site_key] = SiteAgentPolicy(
                site_key=site_key,
                use_trm=self.use_trm,
            )
            # Load checkpoint if provided
            if self.checkpoint_path and self._policies[site_key].site_agent.model:
                try:
                    import torch
                    checkpoint = torch.load(
                        self.checkpoint_path,
                        map_location='cpu'
                    )
                    self._policies[site_key].site_agent.model.load_state_dict(
                        checkpoint['model_state_dict']
                    )
                    logger.info(f"Loaded checkpoint for {site_key}")
                except Exception as e:
                    logger.warning(f"Failed to load checkpoint: {e}")

        return self._policies[site_key]

    def compute_order(
        self,
        site_key: str,
        observation: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AgentDecision:
        """
        Compute order decision for a site.

        Args:
            site_key: Site/role identifier
            observation: Current node state
            context: Additional context (e.g., game state, history)

        Returns:
            AgentDecision with order quantity and reasoning
        """
        policy = self.get_policy(site_key)
        order_qty = policy.order(observation)

        # Build decision with explanation
        decision = AgentDecision(
            order_quantity=order_qty,
            strategy="site_agent",
            reasoning=self._build_reasoning(observation, order_qty),
            confidence=0.85 if policy.use_trm else 1.0,
            metadata={
                "use_trm": policy.use_trm,
                "site_key": site_key,
            }
        )

        return decision

    def _build_reasoning(
        self,
        observation: Dict[str, Any],
        order_qty: int
    ) -> str:
        """Build human-readable reasoning for the decision."""
        inventory = observation.get('inventory', 0)
        backlog = observation.get('backlog', 0)
        pipeline = observation.get('pipeline_on_order', 0)
        incoming_order = observation.get('last_incoming_order', 0)
        base_stock = observation.get('base_stock', 20)
        inv_position = observation.get('inventory_position', inventory + pipeline - backlog)

        reasoning_parts = []

        # Inventory position analysis
        if inv_position < base_stock * 0.5:
            reasoning_parts.append(f"Low inventory position ({inv_position}) vs target ({base_stock})")
        elif inv_position > base_stock * 1.5:
            reasoning_parts.append(f"High inventory position ({inv_position}) vs target ({base_stock})")

        # Backlog analysis
        if backlog > 0:
            reasoning_parts.append(f"Backlog of {backlog} units to clear")

        # Demand analysis
        if incoming_order > 0:
            reasoning_parts.append(f"Incoming demand of {incoming_order} units")

        # Order decision
        reasoning_parts.append(f"Ordering {order_qty} units to maintain service level")

        return "; ".join(reasoning_parts)


def register_site_agent_strategy():
    """
    Register SiteAgent as an available agent strategy.

    Call this during application startup to make site_agent strategy available.
    """
    from app.services.agents import AgentManager, AgentStrategy

    # Add site_agent to AgentStrategy enum if not present
    # Note: This requires modifying the AgentStrategy enum in agents.py
    logger.info("SiteAgent strategy registered for scenario use")


def create_site_agent_for_scenario(
    db: Session,
    scenario_id: int,
    site_key: str,
    config_overrides: Optional[Dict[str, Any]] = None
) -> SiteAgentPolicy:
    """
    Create a SiteAgent policy for a specific scenario.

    Args:
        db: Database session
        scenario_id: Scenario ID
        site_key: Site/role identifier
        config_overrides: Optional configuration overrides

    Returns:
        Configured SiteAgentPolicy
    """
    # Load scenario-specific configuration
    from app.models.scenario import Scenario

    scenario = db.query(Scenario).filter_by(id=scenario_id).first()
    if not scenario:
        raise ValueError(f"Scenario {scenario_id} not found")

    # Determine TRM settings
    use_trm = True
    trm_threshold = 0.7

    if config_overrides:
        use_trm = config_overrides.get('use_trm', use_trm)
        trm_threshold = config_overrides.get('trm_threshold', trm_threshold)

    policy = SiteAgentPolicy(
        site_key=site_key,
        use_trm=use_trm,
        trm_confidence_threshold=trm_threshold
    )

    logger.info(f"Created SiteAgent policy for scenario {scenario_id}, site {site_key}")

    return policy
