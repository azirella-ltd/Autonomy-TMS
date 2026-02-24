"""
GNN (Graph Neural Network) Agent for Simulation.

Provides GNN-based decision making integrated with the simulation engine.
Models are config-specific - each supply chain configuration has its own trained model.
"""

import torch
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class GNNAgent:
    """
    GNN-powered agent for simulation decisions.

    Features:
    - 128M+ parameter graph neural network
    - Supply chain graph structure awareness
    - Temporal message passing
    - Fallback to heuristic if model unavailable
    """

    # Node type mapping
    NODE_TYPE_MAP = {
        "retailer": 0,
        "wholesaler": 1,
        "distributor": 2,
        "factory": 3,
        "manufacturer": 3,
        "supplier": 4,
        "market": 5,
        "market_demand": 6,
        "market_supply": 7,
    }

    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = "cpu",
        use_heuristic_fallback: bool = True,
        window_size: int = 10
    ):
        """
        Initialize GNN agent.

        Args:
            model_path: Path to pretrained GNN checkpoint
            device: Device for inference ("cpu" or "cuda")
            use_heuristic_fallback: Fallback to base stock if model fails
            window_size: History window for demand observations
        """
        self.device = device
        self.use_heuristic_fallback = use_heuristic_fallback
        self.window_size = window_size
        self.model = None
        self.model_loaded = False
        self.model_config = {}

        # Demand history buffer (per node)
        self.demand_history: Dict[str, List[float]] = {}

        # Try to load model
        if model_path:
            self.load_model(model_path)

    def load_model(self, model_path: str) -> bool:
        """
        Load GNN model from checkpoint.

        Args:
            model_path: Path to checkpoint file

        Returns:
            True if successful
        """
        try:
            checkpoint_path = Path(model_path)
            if not checkpoint_path.exists():
                logger.warning(f"GNN checkpoint not found: {model_path}")
                return False

            # Load checkpoint
            checkpoint = torch.load(checkpoint_path, map_location=self.device)

            # Extract model state and config
            if isinstance(checkpoint, dict):
                self.model_config = checkpoint.get("config", {})
                model_state = checkpoint.get("model_state_dict")

                # Try to create the model from config
                try:
                    from app.models.gnn.temporal_gnn import SupplyChainTemporalGNN

                    # Get architecture params from config
                    node_features = self.model_config.get("node_features", 8)
                    hidden_channels = self.model_config.get("hidden_channels", 64)
                    num_layers = self.model_config.get("num_layers", 3)

                    self.model = SupplyChainTemporalGNN(
                        node_features=node_features,
                        hidden_channels=hidden_channels,
                        num_layers=num_layers
                    )

                    if model_state:
                        self.model.load_state_dict(model_state)

                    self.model.to(self.device)
                    self.model.eval()
                    self.model_loaded = True
                    logger.info(f"GNN model loaded from {model_path}")
                    return True

                except ImportError as e:
                    logger.warning(f"Could not import GNN model class: {e}")
                    # Store the state dict for later use
                    self.model = model_state
                    self.model_loaded = True
                    logger.info(f"GNN model state loaded from {model_path}")
                    return True
            else:
                logger.warning(f"Unexpected checkpoint format in {model_path}")
                return False

        except Exception as e:
            logger.error(f"Failed to load GNN model: {e}")
            self.model_loaded = False
            return False

    def compute_order(self, node: Any, context: Dict) -> float:
        """
        Compute order quantity for a node using GNN.

        Args:
            node: Simulation node object
            context: Scenario context with state information

        Returns:
            order_quantity: Non-negative order quantity
        """
        node_id = getattr(node, "name", "unknown")

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
                order_qty = self._compute_order_gnn(node, context)
                return max(0.0, order_qty)
            except Exception as e:
                logger.warning(f"GNN inference failed for {node_id}: {e}")
                if self.use_heuristic_fallback:
                    return self._compute_order_heuristic(node, context)
                else:
                    return 0.0

        # Fallback to heuristic
        if self.use_heuristic_fallback:
            return self._compute_order_heuristic(node, context)
        else:
            logger.warning(f"GNN model not loaded and no fallback for {node_id}")
            return 0.0

    def _compute_order_gnn(self, node: Any, context: Dict) -> float:
        """Use GNN model for decision."""
        node_id = getattr(node, "name", "unknown")

        # Prepare input features
        inventory = float(getattr(node, "inventory", 0.0))
        backlog = float(getattr(node, "backlog", 0.0))

        # Handle pipeline shipments
        pipeline_shipments = getattr(node, "pipeline_shipments", [])
        if pipeline_shipments:
            if hasattr(pipeline_shipments[0], 'quantity'):
                pipeline = sum(float(s.quantity) for s in pipeline_shipments)
            else:
                pipeline = sum(float(s) for s in pipeline_shipments)
        else:
            pipeline = 0.0

        # Get demand history (pad if needed)
        demand_hist = self.demand_history.get(node_id, [0.0])
        if len(demand_hist) < self.window_size:
            demand_hist = [0.0] * (self.window_size - len(demand_hist)) + demand_hist

        # Get node type
        node_type_str = getattr(node, "node_type", "retailer").lower()
        node_type = self.NODE_TYPE_MAP.get(node_type_str, 0)

        # Calculate average demand
        avg_demand = np.mean(demand_hist) if demand_hist else 0.0

        # If we have a proper model with forward method, use it
        if hasattr(self.model, 'forward'):
            # Build feature tensor
            features = torch.tensor([
                inventory,
                backlog,
                pipeline,
                avg_demand,
                float(node_type),
                float(len(demand_hist)),
                float(context.get("round_number", 0)),
                float(max(demand_hist) if demand_hist else 0),
            ], dtype=torch.float32).unsqueeze(0).to(self.device)

            with torch.no_grad():
                # Get model output
                output = self.model(features)
                if isinstance(output, tuple):
                    order_qty = output[1].item()  # inventory_optimizer output
                else:
                    order_qty = output.item()

            return max(0.0, order_qty)
        else:
            # Use heuristic with model guidance
            return self._compute_order_heuristic(node, context)

    def _compute_order_heuristic(self, node: Any, context: Dict) -> float:
        """
        Fallback heuristic: Simple base stock policy.

        Args:
            node: Simulation site node
            context: Scenario context

        Returns:
            order_quantity
        """
        node_id = getattr(node, "name", "unknown")

        # Get state
        inventory = float(getattr(node, "inventory", 0.0))
        backlog = float(getattr(node, "backlog", 0.0))

        # Handle pipeline
        pipeline_shipments = getattr(node, "pipeline_shipments", [])
        if pipeline_shipments:
            if hasattr(pipeline_shipments[0], 'quantity'):
                pipeline = sum(float(s.quantity) for s in pipeline_shipments)
            else:
                pipeline = sum(float(s) for s in pipeline_shipments)
        else:
            pipeline = 0.0

        # Estimate recent average demand
        demand_hist = self.demand_history.get(node_id, [50.0])
        avg_demand = np.mean(demand_hist) if demand_hist else 50.0

        # Lead time estimate
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
        logger.info("GNN agent reset")

    def get_info(self) -> Dict[str, Any]:
        """Get agent information."""
        return {
            "agent_type": "gnn",
            "model_loaded": self.model_loaded,
            "device": self.device,
            "window_size": self.window_size,
            "use_fallback": self.use_heuristic_fallback,
            "config": self.model_config,
        }


# Singleton instances keyed by model_path for config-specific models
_gnn_agent_instances: Dict[str, GNNAgent] = {}


def get_gnn_agent(
    model_path: Optional[str] = None,
    device: str = "cpu",
    reload: bool = False
) -> GNNAgent:
    """
    Get or create GNN agent for a specific model path.

    Args:
        model_path: Path to GNN checkpoint (config-specific)
        device: Device for inference
        reload: Force reload model

    Returns:
        GNN agent instance
    """
    global _gnn_agent_instances

    # Use model_path as key, or "default" for no path
    cache_key = model_path or "default"

    if cache_key not in _gnn_agent_instances or reload:
        _gnn_agent_instances[cache_key] = GNNAgent(
            model_path=model_path,
            device=device,
            use_heuristic_fallback=True
        )

    return _gnn_agent_instances[cache_key]


def compute_gnn_order(node: Any, context: Dict, model_path: Optional[str] = None) -> float:
    """
    Compute GNN order (convenience function for agent integration).

    Args:
        node: Simulation site node
        context: Scenario context
        model_path: Optional path to GNN checkpoint (config-specific)

    Returns:
        order_quantity
    """
    agent = get_gnn_agent(model_path=model_path)
    return agent.compute_order(node, context)
