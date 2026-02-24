"""
TRM (Tiny Recursive Model) Agent for Simulation.

Provides TRM-based decision making integrated with the simulation engine.
"""

import torch
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from app.models.trm import create_trm_model, TinyRecursiveModel

logger = logging.getLogger(__name__)


class TRMAgent:
    """
    TRM-powered agent for simulation decisions.

    Features:
    - Fast inference (<10ms per decision)
    - Supply chain context awareness
    - Recursive reasoning with chain-of-thought
    - Fallback to heuristic if model unavailable
    """

    # Node type mapping
    NODE_TYPE_MAP = {
        "retailer": 0,
        "wholesaler": 1,
        "distributor": 2,
        "factory": 3,
        "supplier": 4,
        "market": 5
    }

    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = "cpu",
        use_heuristic_fallback: bool = True,
        window_size: int = 10
    ):
        """
        Initialize TRM agent.

        Args:
            model_path: Path to pretrained TRM checkpoint
            device: Device for inference ("cpu" or "cuda")
            use_heuristic_fallback: Fallback to base stock if model fails
            window_size: History window for demand observations
        """
        self.device = device
        self.use_heuristic_fallback = use_heuristic_fallback
        self.window_size = window_size
        self.model: Optional[TinyRecursiveModel] = None
        self.model_loaded = False

        # Demand history buffer (per node)
        self.demand_history: Dict[str, List[float]] = {}

        # Try to load model
        if model_path:
            self.load_model(model_path)

    def load_model(self, model_path: str) -> bool:
        """
        Load TRM model from checkpoint.

        Args:
            model_path: Path to checkpoint file

        Returns:
            True if successful
        """
        try:
            checkpoint_path = Path(model_path)
            if not checkpoint_path.exists():
                logger.warning(f"TRM checkpoint not found: {model_path}")
                return False

            # Load checkpoint
            checkpoint = torch.load(checkpoint_path, map_location=self.device)

            # Create model with config
            model_config = checkpoint.get("model_config", {})
            self.model = create_trm_model(config=model_config)
            self.model.load_state_dict(checkpoint["model_state_dict"])
            self.model.to(self.device)
            self.model.eval()

            self.model_loaded = True
            logger.info(f"TRM model loaded from {model_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load TRM model: {e}")
            self.model_loaded = False
            return False

    def compute_order(self, node: Any, context: Dict) -> float:
        """
        Compute order quantity for a node using TRM.

        Args:
            node: Simulation node object
            context: Scenario context with state information

        Returns:
            order_quantity: Non-negative order quantity
        """
        node_id = node.name

        # Update demand history
        if node_id not in self.demand_history:
            self.demand_history[node_id] = []

        # Get current demand (downstream order received)
        current_demand = getattr(node, "incoming_order", 0.0)
        self.demand_history[node_id].append(current_demand)

        # Keep window_size observations
        if len(self.demand_history[node_id]) > self.window_size:
            self.demand_history[node_id] = self.demand_history[node_id][-self.window_size:]

        # Use model if loaded
        if self.model_loaded and self.model is not None:
            try:
                order_qty = self._compute_order_trm(node, context)
                return max(0.0, order_qty)
            except Exception as e:
                logger.warning(f"TRM inference failed for {node_id}: {e}")
                if self.use_heuristic_fallback:
                    return self._compute_order_heuristic(node, context)
                else:
                    return 0.0

        # Fallback to heuristic
        if self.use_heuristic_fallback:
            return self._compute_order_heuristic(node, context)
        else:
            logger.warning(f"TRM model not loaded and no fallback for {node_id}")
            return 0.0

    def _compute_order_trm(self, node: Any, context: Dict) -> float:
        """Use TRM model for decision."""
        node_id = node.name

        # Prepare input tensors
        inventory = float(getattr(node, "inventory", 0.0))
        backlog = float(getattr(node, "backlog", 0.0))
        pipeline = sum(float(shipment.quantity) for shipment in getattr(node, "pipeline_shipments", []))

        # Get demand history (pad if needed)
        demand_hist = self.demand_history.get(node_id, [0.0])
        if len(demand_hist) < self.window_size:
            demand_hist = [0.0] * (self.window_size - len(demand_hist)) + demand_hist

        # Get node type
        node_type_str = getattr(node, "node_type", "retailer").lower()
        node_type = self.NODE_TYPE_MAP.get(node_type_str, 0)

        # Get node position (use round_number as proxy)
        node_position = context.get("round_number", 0) % 10

        # Model inference
        order_qty = self.model.get_action(
            inventory=inventory,
            backlog=backlog,
            pipeline=pipeline,
            demand_history=demand_hist,
            node_type=node_type,
            node_position=node_position
        )

        return order_qty

    def _compute_order_heuristic(self, node: Any, context: Dict) -> float:
        """
        Fallback heuristic: Simple base stock policy.

        Args:
            node: Simulation site node
            context: Scenario context

        Returns:
            order_quantity
        """
        node_id = node.name

        # Get state
        inventory = float(getattr(node, "inventory", 0.0))
        backlog = float(getattr(node, "backlog", 0.0))
        pipeline = sum(float(shipment.quantity) for shipment in getattr(node, "pipeline_shipments", []))

        # Estimate recent average demand
        demand_hist = self.demand_history.get(node_id, [50.0])
        avg_demand = np.mean(demand_hist) if demand_hist else 50.0

        # Lead time estimate (use policy if available)
        lead_time = getattr(node, "lead_time", 2)

        # Base stock level: avg_demand * (lead_time + safety_factor)
        safety_factor = 2
        base_stock_level = avg_demand * (lead_time + safety_factor)

        # Inventory position
        inv_position = inventory + pipeline - backlog

        # Order up to base stock
        order_qty = max(0.0, base_stock_level - inv_position)

        return order_qty

    def reset(self):
        """Reset agent state (clear demand history)."""
        self.demand_history.clear()
        logger.info("TRM agent reset")

    def get_info(self) -> Dict[str, Any]:
        """Get agent information."""
        return {
            "agent_type": "trm",
            "model_loaded": self.model_loaded,
            "device": self.device,
            "window_size": self.window_size,
            "use_fallback": self.use_heuristic_fallback,
            "parameters": self.model.count_parameters() if self.model else None
        }


# Singleton instance for the application
_trm_agent_instance: Optional[TRMAgent] = None


def get_trm_agent(
    model_path: Optional[str] = None,
    device: str = "cpu",
    reload: bool = False
) -> TRMAgent:
    """
    Get or create TRM agent singleton.

    Args:
        model_path: Path to TRM checkpoint
        device: Device for inference
        reload: Force reload model

    Returns:
        TRM agent instance
    """
    global _trm_agent_instance

    if _trm_agent_instance is None or reload:
        _trm_agent_instance = TRMAgent(
            model_path=model_path,
            device=device,
            use_heuristic_fallback=True
        )

    return _trm_agent_instance


def compute_trm_order(node: Any, context: Dict, model_path: Optional[str] = None) -> float:
    """
    Compute TRM order (convenience function for agent integration).

    Args:
        node: Simulation site node
        context: Scenario context
        model_path: Optional path to TRM checkpoint

    Returns:
        order_quantity
    """
    agent = get_trm_agent(model_path=model_path)
    return agent.compute_order(node, context)
