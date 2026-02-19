import copy
import random
from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List, Union, Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATv2Conv

from app.utils.device import (
    get_available_device,
    to_device,
    device_scope,
    is_cuda_available,
    empty_cache
)

# Type aliases
Tensor = torch.Tensor
Device = Union[str, torch.device]


@dataclass
class ReplayTransition:
    observation: Dict[str, torch.Tensor]
    action: torch.Tensor
    reward: torch.Tensor
    next_observation: Dict[str, torch.Tensor]
    done: torch.Tensor


class ReplayBuffer:
    """Simple FIFO replay buffer for off-policy updates."""

    def __init__(self, capacity: int = 10_000):
        self.capacity = int(capacity)
        self.buffer: deque[ReplayTransition] = deque(maxlen=self.capacity)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.buffer)

    def push(
        self,
        observation: Dict[str, torch.Tensor],
        action: torch.Tensor,
        reward: torch.Tensor,
        next_observation: Dict[str, torch.Tensor],
        done: torch.Tensor,
    ) -> None:
        self.buffer.append(
            ReplayTransition(
                observation=observation,
                action=action,
                reward=reward,
                next_observation=next_observation,
                done=done,
            )
        )

    def sample(self, batch_size: int) -> List[ReplayTransition]:
        if batch_size > len(self.buffer):
            raise ValueError("Not enough samples in replay buffer to draw batch")
        return random.sample(self.buffer, batch_size)

class TemporalGNN(nn.Module):
    """
    A simple temporal graph neural network layer that combines graph and temporal information.
    This is a simplified version for debugging purposes.
    """
    def __init__(self, in_channels: int, out_channels: int, edge_dim: int = 3, heads: int = 1,
                 device: Optional[Device] = None):
        super().__init__()
        self.device = get_available_device(device)
        self.edge_dim = edge_dim  # Should match the edge_attr dimension (3 in our case)
        self.in_channels = in_channels
        
        # Ensure the device is properly set
        if isinstance(self.device, str):
            self.device = torch.device(self.device)
            
        # Move all parameters to the specified device during initialization
        self._register_load_state_dict_pre_hook(self._move_to_device_hook)
        self.out_channels = out_channels
        
        # Initialize layers with proper device handling
        # Note: edge_dim should match the dimension of edge_attr (3 in our case)
        self.gat = GATv2Conv(
            in_channels=in_channels,
            out_channels=out_channels,
            heads=1,
            edge_dim=edge_dim,
            add_self_loops=True
        )
        
        self.gru = nn.GRU(
            input_size=out_channels,
            hidden_size=out_channels,
            batch_first=True
        )
        
        # Move to device after initialization
        self.to(self.device)
        
    def _move_to_device_hook(self, state_dict, prefix, *args, **kwargs):
        """Ensure all parameters and buffers are moved to the correct device."""
        for key, param in self.named_parameters():
            if param is not None:
                param.data = param.data.to(self.device)
        for key, buf in self.named_buffers():
            if buf is not None:
                buf.data = buf.data.to(self.device)
                
    def forward(self, x: Tensor, edge_index: Tensor, edge_attr: Optional[Tensor] = None) -> Tensor:
        # Ensure all input tensors are on the correct device
        with device_scope(self.device):
            x = to_device(x, self.device, non_blocking=True)
            edge_index = to_device(edge_index, self.device, non_blocking=True)
            if edge_attr is not None:
                edge_attr = to_device(edge_attr, self.device, non_blocking=True)
                
            # Ensure model parameters are on the correct device
            self.gat = self.gat.to(self.device)
            self.gru = self.gru.to(self.device)
            
            # x shape: [batch_size, seq_len, num_nodes, in_channels] or [seq_len, num_nodes, in_channels]
        # Add batch dimension if missing
        if x.dim() == 3:  # [seq_len, num_nodes, in_channels]
            x = x.unsqueeze(0)  # [1, seq_len, num_nodes, in_channels]
            
        batch_size, seq_len, num_nodes, in_channels = x.size()
        
        # Process each time step separately
        h_list = []
        for t in range(seq_len):
            # Get node features for this time step: [batch_size, num_nodes, in_channels]
            x_t = x[:, t]  # [batch_size, num_nodes, in_channels]
            
            # Process each graph in the batch separately
            batch_h = []
            for b in range(batch_size):
                # Get features for this batch element: [num_nodes, in_channels]
                x_bt = x_t[b]  # [num_nodes, in_channels]
                
                # Ensure all tensors are on the same device and have correct dimensions
                device = next(self.parameters()).device
                x_bt = x_bt.to(device)
                edge_idx = edge_index.to(device)
                
                # Ensure edge_attr has the correct shape [num_edges, edge_dim]
                if edge_attr is not None:
                    edge_attr_dev = edge_attr.to(device)
                    # Ensure edge_attr has shape [num_edges, edge_dim]
                    if edge_attr_dev.dim() == 1:
                        edge_attr_dev = edge_attr_dev.unsqueeze(-1)  # [num_edges, 1]
                    elif edge_attr_dev.dim() > 2:
                        edge_attr_dev = edge_attr_dev.view(edge_attr_dev.size(0), -1)  # Flatten to [num_edges, edge_dim]
                else:
                    edge_attr_dev = None
                
                # Ensure GAT is on the same device
                self.gat = self.gat.to(device)
                
                # Apply GAT with edge attributes if provided
                try:
                    if edge_attr_dev is not None:
                        # Ensure edge_attr has the correct shape [num_edges, edge_dim]
                        if edge_attr_dev.size(1) != self.edge_dim:
                            # If edge_attr has wrong dimension, project it to the correct dimension
                            if hasattr(self, 'edge_proj'):
                                edge_attr_dev = self.edge_proj(edge_attr_dev)
                            else:
                                # Create a projection layer if it doesn't exist
                                self.edge_proj = nn.Linear(edge_attr_dev.size(1), self.edge_dim).to(device)
                                edge_attr_dev = self.edge_proj(edge_attr_dev)
                        
                        h_bt = self.gat(x_bt, edge_idx, edge_attr=edge_attr_dev)  # [num_nodes, out_channels]
                    else:
                        h_bt = self.gat(x_bt, edge_idx)  # [num_nodes, out_channels]
                except RuntimeError as e:
                    print(f"Error in GAT forward pass:")
                    print(f"x_bt device: {x_bt.device}, shape: {x_bt.shape}")
                    print(f"edge_index device: {edge_idx.device}, shape: {edge_idx.shape}")
                    if edge_attr_dev is not None:
                        print(f"edge_attr device: {edge_attr_dev.device}, shape: {edge_attr_dev.shape}")
                    print(f"GAT device: {next(self.gat.parameters()).device if next(self.gat.parameters(), None) is not None else 'no parameters'}")
                    raise
                
                batch_h.append(h_bt.unsqueeze(0))  # Add batch dimension back
                
            # Stack batch items: [batch_size, num_nodes, out_channels]
            h_t = torch.cat(batch_h, dim=0)
            h_list.append(h_t.unsqueeze(1))  # Add sequence dimension
        
        # Stack along sequence dimension: [batch_size, seq_len, num_nodes, out_channels]
        h = torch.cat(h_list, dim=1)
        
        # Apply GRU
        h = h.permute(0, 2, 1, 3)  # [batch_size, num_nodes, seq_len, out_channels]
        h = h.reshape(batch_size * num_nodes, seq_len, -1)  # [batch_size * num_nodes, seq_len, out_channels]
        
        # Ensure GRU is on the correct device
        self.gru = self.gru.to(h.device)
        h, _ = self.gru(h)  # [batch_size * num_nodes, seq_len, out_channels]
        
        h = h.reshape(batch_size, num_nodes, seq_len, -1)  # [batch_size, num_nodes, seq_len, out_channels]
        h = h.permute(0, 2, 1, 3)  # [batch_size, seq_len, num_nodes, out_channels]
        
        return h

class SupplyChainTemporalGNN(nn.Module):
    """
    Temporal Graph Neural Network for supply chain forecasting and decision making.
    Combines GNN with temporal attention for modeling supply chain dynamics.
    """
    
    def __init__(
        self,
        node_features: int = 5,  # inventory, orders, demand, backlog, incoming_shipments
        edge_features: int = 3,  # lead_time, cost, relationship_strength
        hidden_dim: int = 32,   # Reduced from 64 to make it easier to debug
        num_layers: int = 2,    # Reduced from 3 to make it simpler
        num_heads: int = 1,     # Using single head for simplicity
        dropout: float = 0.1,
        seq_len: int = 10,      # Number of time steps to consider
        num_nodes: int = 4,     # retailer, wholesaler, distributor, manufacturer
        device: Optional[Device] = None,
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.seq_len = seq_len
        self.num_nodes = num_nodes
        
        # Initialize device handling
        self.device = get_available_device(device)
        if isinstance(self.device, str):
            self.device = torch.device(self.device)
            
        # Store edge dimension
        self.edge_dim = edge_features
        
        # Register hook to ensure parameters are moved to the correct device
        self._register_load_state_dict_pre_hook(self._move_to_device_hook)
        
        # Initialize layers
        self.node_encoder = nn.Linear(node_features, hidden_dim)
        self.edge_encoder = nn.Linear(edge_features, hidden_dim) if edge_features > 0 else None

        # Create temporal GNN layers
        self.tgnn_layers = nn.ModuleList([
            TemporalGNN(
                in_channels=hidden_dim,
                out_channels=hidden_dim,
                edge_dim=edge_features,
                heads=1,  # Using single head for simplicity
                device=self.device
            ) for _ in range(num_layers)
        ])
        
        # Output heads
        self.order_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 1)  # Predict order quantity
        )
        
        self.demand_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 1)  # Predict next demand
        )

        self.value_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1)  # Estimate value per node
        )

        # Input projection
        self.input_proj = nn.Linear(node_features, hidden_dim)

        # Input normalization buffers (disabled until stats provided)
        self.register_buffer("feature_mean", torch.zeros(node_features))
        self.register_buffer("feature_std", torch.ones(node_features))
        self._use_input_normalization = False
        
        # Initialize weights and move to device
        self._init_weights()
        self.to(self.device)
    
    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)

    def set_normalization_stats(
        self,
        mean: Union[np.ndarray, torch.Tensor],
        std: Union[np.ndarray, torch.Tensor],
    ) -> None:
        """Provide feature normalization statistics computed offline."""

        mean_t = torch.as_tensor(mean, dtype=torch.float32, device=self.device)
        std_t = torch.as_tensor(std, dtype=torch.float32, device=self.device)
        std_t = torch.clamp(std_t, min=1e-6)
        if mean_t.dim() != 1 or std_t.dim() != 1:
            raise ValueError("Normalization stats must be 1-D per feature vectors")
        if mean_t.numel() != self.input_proj.in_features:
            raise ValueError(
                f"Expected {self.input_proj.in_features} feature stats, got {mean_t.numel()}"
            )
        self.feature_mean = mean_t
        self.feature_std = std_t
        self._use_input_normalization = True
    
    def _move_to_device_hook(self, state_dict, prefix, *args, **kwargs):
        """Ensure all parameters and buffers are moved to the correct device."""
        for key, param in self.named_parameters():
            if param is not None:
                param.data = param.data.to(self.device)
        for key, buf in self.named_buffers():
            if buf is not None:
                buf.data = buf.data.to(self.device)
                
    def forward(
        self,
        node_features: torch.Tensor,  # [batch_size, seq_len, num_nodes, node_features] or [batch_size, 1, seq_len, num_nodes, node_features]
        edge_index: torch.Tensor,     # [2, num_edges]
        edge_attr: Optional[torch.Tensor] = None  # [num_edges, edge_features]
    ) -> Dict[str, torch.Tensor]:
        with device_scope(self.device):
            # Move all inputs to the correct device
            node_features = to_device(node_features, self.device, non_blocking=True)
            edge_index = to_device(edge_index, self.device, non_blocking=True)
            if edge_attr is not None:
                edge_attr = to_device(edge_attr, self.device, non_blocking=True)

            # Debug shapes
            print(f"Input node_features shape: {node_features.shape}")
            print(f"Input edge_index shape: {edge_index.shape}")
            if edge_attr is not None:
                print(f"Input edge_attr shape: {edge_attr.shape}")

            if self._use_input_normalization:
                mean = self.feature_mean.view(1, 1, 1, -1)
                std = torch.clamp(self.feature_std.view(1, 1, 1, -1), min=1e-6)
                node_features = (node_features - mean) / std
            
            # Handle both 5D and 6D input shapes
            original_shape = node_features.shape
            if len(original_shape) == 6:
                # Reshape from [batch_size, 1, 1, seq_len, num_nodes, node_features] to [batch_size, seq_len, num_nodes, node_features]
                node_features = node_features.squeeze(1).squeeze(1)
                print(f"Reshaped node_features from {original_shape} to {node_features.shape}")
            elif len(original_shape) == 5:
                # Reshape from [batch_size, 1, seq_len, num_nodes, node_features] to [batch_size, seq_len, num_nodes, node_features]
                node_features = node_features.squeeze(1)
                print(f"Reshaped node_features from {original_shape} to {node_features.shape}")
            
            try:
                batch_size, seq_len, num_nodes, node_feat_dim = node_features.size()
                print(f"Successfully unpacked shape: batch_size={batch_size}, seq_len={seq_len}, num_nodes={num_nodes}, node_feat_dim={node_feat_dim}")
            except Exception as e:
                print(f"Error unpacking node_features shape: {node_features.shape}")
                raise
            
            try:
                # Encode node and edge features
                h = self.node_encoder(node_features)  # [batch_size, seq_len, num_nodes, hidden_dim]
                
                # Encode edge attributes if provided
                if edge_attr is not None and self.edge_encoder is not None:
                    edge_embeddings = self.edge_encoder(edge_attr)  # [num_edges, hidden_dim]
                else:
                    edge_embeddings = None
                    
                # Apply temporal GNN layers
                for layer in self.tgnn_layers:
                    h = layer(h, edge_index, edge_embeddings)  # [batch_size, seq_len, num_nodes, hidden_dim]
                    
                # Get the last time step's hidden state for each node
                last_hidden = h[:, -1]  # [batch_size, num_nodes, hidden_dim]
                
                # Predict order quantities and demand forecasts
                order_quantities = self.order_head(last_hidden).squeeze(-1)  # [batch_size, num_nodes]
                demand_forecasts = self.demand_head(last_hidden).squeeze(-1)  # [batch_size, num_nodes]
                state_values = self.value_head(last_hidden).squeeze(-1)  # [batch_size, num_nodes]

                # Return node embeddings and predictions
                return {
                    'order_quantity': order_quantities,  # [batch_size, num_nodes]
                    'demand_forecast': demand_forecasts,  # [batch_size, num_nodes]
                    'node_embeddings': last_hidden,  # [batch_size, num_nodes, hidden_dim]
                    'state_value': state_values,
                }
                
            except RuntimeError as e:
                if 'out of memory' in str(e).lower() and is_cuda_available():
                    # Clear CUDA cache and retry once
                    empty_cache()
                    return self.forward(node_features, edge_index, edge_attr)
                raise
                
    def forward_original(
        self,
        x: Tensor,
        edge_index: Tensor,
        edge_attr: Optional[Tensor] = None,
        hx: Optional[Tensor] = None
    ) -> Dict[str, Tensor]:
        # Ensure tensors are on the correct device
        x = to_device(x, self.device)
        edge_index = to_device(edge_index, self.device)
        if edge_attr is not None:
            edge_attr = to_device(edge_attr, self.device)
        if hx is not None:
            hx = to_device(hx, self.device)
        """
        Forward pass of the model.
        
        Args:
            x: Node features [batch_size, seq_len, num_nodes, node_features] or [seq_len, num_nodes, node_features]
            edge_index: Graph connectivity [2, num_edges]
            edge_attr: Edge features [num_edges, edge_features]
            hx: Optional hidden state
            
        Returns:
            Dictionary with 'order_quantity' and 'demand_forecast' predictions
        """
        if self._use_input_normalization:
            mean = self.feature_mean.view(1, 1, 1, -1)
            std = torch.clamp(self.feature_std.view(1, 1, 1, -1), min=1e-6)
            x = (x - mean) / std

        # Ensure input has 4 dimensions [batch_size, seq_len, num_nodes, node_features]
        print(f"Input x shape: {x.shape}")
        
        # Handle 6D input [1, 1, 1, seq_len, num_nodes, node_features] -> [1, seq_len, num_nodes, node_features]
        if x.dim() == 6:
            # Remove the extra dimensions at indices 1 and 2
            x = x.squeeze(1).squeeze(1)
            print(f"After removing extra dims (6D case), x shape: {x.shape}")
        # Handle 5D input [1, 1, seq_len, num_nodes, node_features] -> [1, seq_len, num_nodes, node_features]
        elif x.dim() == 5:
            # Remove the extra dimension at index 1
            x = x.squeeze(1)
            print(f"After removing extra dim (5D case), x shape: {x.shape}")
        # Handle 3D input [seq_len, num_nodes, node_features] -> [1, seq_len, num_nodes, node_features]
        elif x.dim() == 3:
            # Add batch dimension if missing
            x = x.unsqueeze(0)  # [1, seq_len, num_nodes, node_features]
            print(f"After adding batch dim, x shape: {x.shape}")
        
        try:
            batch_size, seq_len, num_nodes, node_features = x.size()
            print(f"Batch size: {batch_size}, Seq len: {seq_len}, Num nodes: {num_nodes}, Node features: {node_features}")
        except Exception as e:
            print(f"Error unpacking x size: {e}")
            print(f"x size: {x.size()}")
            raise
        
        # Project input features
        x = self.input_proj(x)  # [batch_size, seq_len, num_nodes, hidden_dim]
        print(f"After input projection, x shape: {x.shape}")
        
        # Apply temporal GNN layers
        for tgnn in self.tgnn_layers:
            # Process each time step separately to avoid dimension issues
            time_step_outputs = []
            for t in range(seq_len):
                # Get features for this time step
                x_t = x[:, t]  # [batch_size, num_nodes, hidden_dim]
                
                # Apply temporal GNN
                h_t = tgnn(x_t, edge_index, edge_attr)  # [batch_size, num_nodes, hidden_dim]
                time_step_outputs.append(h_t.unsqueeze(1))  # Add time dimension back
                
            # Stack time steps
            x = torch.cat(time_step_outputs, dim=1)  # [batch_size, seq_len, num_nodes, hidden_dim]
            
        # Take the last time step's output
        x = x[:, -1]  # [batch_size, num_nodes, hidden_dim]
        
        # Process each node separately to avoid dimension issues
        order_outputs = []
        demand_outputs = []
        value_outputs = []
        
        for i in range(x.size(1)):  # Iterate over num_nodes
            # Get features for this node [batch_size, hidden_dim]
            node_features = x[:, i, :]
            
            # Get order quantity for this node
            order = self.order_head(node_features)  # [batch_size, 1]
            order_outputs.append(order)
            
            # Get demand forecast for this node
            demand = self.demand_head(node_features)  # [batch_size, 1]
            demand_outputs.append(demand)

            value = self.value_head(node_features)  # [batch_size, 1]
            value_outputs.append(value)
        
        # Stack outputs: [batch_size, num_nodes]
        order_quantity = torch.cat(order_outputs, dim=1)  # [batch_size, num_nodes]
        demand_forecast = torch.cat(demand_outputs, dim=1)  # [batch_size, num_nodes]
        state_value = torch.cat(value_outputs, dim=1)  # [batch_size, num_nodes]

        return {
            'order_quantity': order_quantity,
            'demand_forecast': demand_forecast,
            'state_value': state_value,
        }

class SupplyChainAgent:
    """Temporal-GNN agent with replay buffer and target network."""

    def __init__(
        self,
        site_id: int,
        model: Optional[SupplyChainTemporalGNN] = None,
        learning_rate: float = 1e-3,
        device: Optional[Union[str, torch.device]] = None,
        feature_stats: Optional[Dict[str, Union[np.ndarray, torch.Tensor]]] = None,
        buffer_capacity: int = 5000,
        batch_size: int = 32,
        target_update_interval: int = 50,
        policy_loss_weight: float = 0.1,
    ):
        self.site_id = site_id
        self.device = get_available_device(device)
        if isinstance(self.device, str):
            self.device = torch.device(self.device)

        if model is None:
            self.model = SupplyChainTemporalGNN(device=self.device)
        else:
            self.model = model.to(self.device)

        if feature_stats and hasattr(self.model, "set_normalization_stats"):
            mean = feature_stats.get("mean")
            std = feature_stats.get("std")
            if mean is not None and std is not None:
                self.model.set_normalization_stats(mean, std)

        self.optimizer = torch.optim.Adam(
            filter(lambda p: p.requires_grad, self.model.parameters()),
            lr=learning_rate,
        )
        self.value_loss = nn.MSELoss().to(self.device)

        self.target_model = copy.deepcopy(self.model).to(self.device)
        for param in self.target_model.parameters():
            param.requires_grad_(False)

        if feature_stats and hasattr(self.target_model, "set_normalization_stats"):
            mean = feature_stats.get("mean")
            std = feature_stats.get("std")
            if mean is not None and std is not None:
                self.target_model.set_normalization_stats(mean, std)

        self.replay_buffer = ReplayBuffer(capacity=buffer_capacity)
        self.batch_size = batch_size
        self.target_update_interval = max(1, target_update_interval)
        self.policy_loss_weight = policy_loss_weight
        self.gamma = 0.99
        self.update_steps = 0

        self.model.eval()
        self.target_model.eval()

    def _sync_target_network(self) -> None:
        self.target_model.load_state_dict(self.model.state_dict())

    def reset_hidden_state(self) -> None:  # pragma: no cover - interface hook
        pass

    def _format_observation(
        self,
        observation: Dict[str, torch.Tensor],
        *,
        device: torch.device,
        detach: bool,
    ) -> Dict[str, torch.Tensor]:
        node_features = observation.get("node_features")
        if node_features is None:
            raise ValueError("Observation missing 'node_features'")
        if not isinstance(node_features, torch.Tensor):
            node_tensor = torch.as_tensor(node_features, dtype=torch.float32)
        else:
            node_tensor = node_features.detach() if detach else node_features
            node_tensor = node_tensor.to(dtype=torch.float32)
            if detach:
                node_tensor = node_tensor.clone()

        if node_tensor.dim() == 3:
            node_tensor = node_tensor.unsqueeze(0)
        elif node_tensor.dim() == 5 and node_tensor.size(1) == 1:
            node_tensor = node_tensor.squeeze(1)
        elif node_tensor.dim() == 6:
            node_tensor = node_tensor.squeeze(1).squeeze(1)

        if device is not None:
            node_tensor = node_tensor.to(device, non_blocking=not detach)

        formatted: Dict[str, torch.Tensor] = {"node_features": node_tensor}

        edge_index = observation.get("edge_index")
        if edge_index is not None:
            if not isinstance(edge_index, torch.Tensor):
                edge_idx = torch.as_tensor(edge_index, dtype=torch.long)
            else:
                edge_idx = edge_index.detach() if detach else edge_index
                if detach:
                    edge_idx = edge_idx.clone()
                edge_idx = edge_idx.to(dtype=torch.long)
            if device is not None:
                edge_idx = edge_idx.to(device, non_blocking=not detach)
            formatted["edge_index"] = edge_idx

        edge_attr = observation.get("edge_attr")
        if edge_attr is not None:
            if not isinstance(edge_attr, torch.Tensor):
                attr = torch.as_tensor(edge_attr, dtype=torch.float32)
            else:
                attr = edge_attr.detach() if detach else edge_attr
                if detach:
                    attr = attr.clone()
                attr = attr.to(dtype=torch.float32)
            if device is not None:
                attr = attr.to(device, non_blocking=not detach)
            formatted["edge_attr"] = attr

        return formatted

    def _collate(self, batch: List[Dict[str, torch.Tensor]]) -> Dict[str, torch.Tensor]:
        node_features = torch.cat([item["node_features"] for item in batch], dim=0)
        edge_index = batch[0].get("edge_index")
        edge_attr = batch[0].get("edge_attr")

        return {
            "node_features": node_features,
            "edge_index": edge_index,
            "edge_attr": edge_attr,
        }

    def act(self, observation: Dict[str, torch.Tensor], training: bool = False) -> torch.Tensor:
        with device_scope(self.device):
            self.model = self.model.to(self.device)
            self.model.train(training)

            formatted = self._format_observation(
                observation,
                device=self.device,
                detach=False,
            )

            try:
                with torch.no_grad():
                    outputs = self.model(**formatted)
                    actions = outputs["order_quantity"][:, self.site_id]
                return actions.detach().cpu()
            except RuntimeError as exc:
                if "out of memory" in str(exc).lower() and is_cuda_available():
                    empty_cache()
                    return self.act(observation, training)
                raise

    def update(
        self,
        observations: List[Dict[str, torch.Tensor]],
        actions: List[torch.Tensor],
        rewards: List[float],
        next_observations: List[Dict[str, torch.Tensor]],
        dones: List[bool],
        gamma: float = 0.99,
        clip_grad_norm: Optional[float] = 1.0,
    ) -> Dict[str, float]:
        if gamma != self.gamma:
            self.gamma = gamma

        for obs, act, reward, next_obs, done in zip(
            observations, actions, rewards, next_observations, dones
        ):
            obs_cpu = self._format_observation(
                obs,
                device=torch.device("cpu"),
                detach=True,
            )
            next_obs_cpu = self._format_observation(
                next_obs,
                device=torch.device("cpu"),
                detach=True,
            )

            action_tensor = torch.as_tensor(act, dtype=torch.float32)
            if action_tensor.numel() > 1:
                flat_action = action_tensor.reshape(-1)
                index = min(self.site_id, flat_action.numel() - 1)
                action_tensor = flat_action[index]
            action_tensor = action_tensor.view(1)

            reward_tensor = torch.tensor([float(reward)], dtype=torch.float32)
            done_tensor = torch.tensor([1.0 if done else 0.0], dtype=torch.float32)

            self.replay_buffer.push(
                observation=obs_cpu,
                action=action_tensor,
                reward=reward_tensor,
                next_observation=next_obs_cpu,
                done=done_tensor,
            )

        if len(self.replay_buffer) < self.batch_size:
            return {"loss": 0.0, "value_loss": 0.0, "policy_loss": 0.0, "grad_norm": 0.0}

        transitions = self.replay_buffer.sample(self.batch_size)
        obs_formatted = [
            self._format_observation(t.observation, device=self.device, detach=False)
            for t in transitions
        ]
        next_obs_formatted = [
            self._format_observation(t.next_observation, device=self.device, detach=False)
            for t in transitions
        ]

        batch_obs = self._collate(obs_formatted)
        batch_next = self._collate(next_obs_formatted)

        action_batch = torch.cat([t.action.view(1) for t in transitions], dim=0).to(self.device)
        reward_batch = torch.cat([t.reward.view(1) for t in transitions], dim=0).to(self.device)
        done_batch = torch.cat([t.done.view(1) for t in transitions], dim=0).to(self.device)

        self.model.train()
        self.model = self.model.to(self.device)
        self.optimizer.zero_grad(set_to_none=True)

        outputs = self.model(**batch_obs)
        predicted_actions = outputs["order_quantity"][:, self.site_id]
        state_values = outputs["state_value"][:, self.site_id]

        with torch.no_grad():
            target_outputs = self.target_model(**batch_next)
            next_values = target_outputs["state_value"][:, self.site_id]
            target_values = reward_batch + (1 - done_batch) * self.gamma * next_values

        value_loss = F.mse_loss(state_values, target_values)
        advantage = (target_values - state_values.detach())
        policy_error = predicted_actions - action_batch
        policy_loss = torch.mean(policy_error.pow(2) * (advantage.abs() + 1.0))

        total_loss = value_loss + self.policy_loss_weight * policy_loss
        total_loss.backward()

        grad_norm_value = 0.0
        if clip_grad_norm is not None:
            grad_norm_value = float(
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), clip_grad_norm)
            )

        self.optimizer.step()
        self.update_steps += 1

        if self.update_steps % self.target_update_interval == 0:
            self._sync_target_network()

        self.model.eval()

        return {
            "loss": float(total_loss.detach().cpu()),
            "value_loss": float(value_loss.detach().cpu()),
            "policy_loss": float(policy_loss.detach().cpu()),
            "grad_norm": grad_norm_value,
        }

def create_supply_chain_agents(
    num_agents: int = 4,
    shared_model: bool = True,
    device: Optional[Union[str, torch.device]] = None,
    **kwargs
) -> List[SupplyChainAgent]:
    """
    Create a list of supply chain agents with proper GPU support.
    
    Args:
        num_agents: Number of agents to create (one per node in the supply chain)
        shared_model: Whether agents should share the same model parameters
        device: Device to place the model on (None for auto-detect)
        **kwargs: Additional arguments to pass to SupplyChainAgent
        
    Returns:
        List of SupplyChainAgent instances
    """
    # Get the device and ensure it's a torch.device
    device = get_available_device(device)
    if isinstance(device, str):
        device = torch.device(device)
    
    # Print device info for debugging
    print(f"Creating {num_agents} agents on device: {device}")
    if device.type == 'cuda':
        print(f"  CUDA Device: {torch.cuda.get_device_name(device)}")
        print(f"  CUDA Memory: {torch.cuda.memory_allocated(device) / 1024**2:.2f}MB allocated")
        print(f"  CUDA Memory: {torch.cuda.memory_reserved(device) / 1024**2:.2f}MB reserved")
    
    # Create shared model if needed
    try:
        if shared_model:
            print("Creating shared model for all agents...")
            model = SupplyChainTemporalGNN(device=device, **kwargs)
            agents = [
                SupplyChainAgent(site_id=i, model=model, device=device, **kwargs)
                for i in range(num_agents)
            ]
            print("Shared model created successfully.")
        else:
            # Create separate models for each agent
            print(f"Creating {num_agents} separate models...")
            agents = []
            for i in range(num_agents):
                print(f"  Creating model for agent {i}...")
                agent_model = SupplyChainTemporalGNN(device=device, **kwargs)
                agent = SupplyChainAgent(
                    site_id=i,
                    model=agent_model,
                    device=device,
                    **kwargs
                )
                agents.append(agent)
                # Free up memory
                if device.type == 'cuda':
                    torch.cuda.empty_cache()
            print("All agent models created successfully.")
            
    except RuntimeError as e:
        print(f"Error creating models: {e}")
        if 'CUDA out of memory' in str(e):
            print("CUDA out of memory error detected. Trying to free up memory...")
            if device.type == 'cuda':
                torch.cuda.empty_cache()
            print("Please reduce model size or batch size and try again.")
        raise
    
    return agents
