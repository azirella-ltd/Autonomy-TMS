import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATv2Conv
from typing import Dict, Optional, Tuple

class SimpleTemporalGNN(nn.Module):
    """
    A simplified temporal graph neural network for supply chain forecasting.
    This version removes edge attributes to simplify the implementation.
    """
    def __init__(
        self,
        node_features: int = 10,
        hidden_dim: int = 32,
        num_layers: int = 2,
        seq_len: int = 10,
        num_nodes: int = 4,
        pred_len: int = 1,
        dropout: float = 0.1
    ):
        super().__init__()
        self.node_features = node_features
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.seq_len = seq_len
        self.num_nodes = num_nodes
        self.pred_len = pred_len
        
        # Input projection
        self.input_proj = nn.Linear(node_features, hidden_dim)
        
        # Temporal GNN layers
        self.gnn_layers = nn.ModuleList()
        for _ in range(num_layers):
            self.gnn_layers.append(
                GATv2Conv(hidden_dim, hidden_dim, heads=1, dropout=dropout)
            )
        
        # GRU for temporal processing
        self.gru = nn.GRU(hidden_dim, hidden_dim, batch_first=True)
        
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
        
        # Initialize weights
        self._init_weights()
    
    def _init_weights(self):
        """Initialize weights for better training stability."""
        for name, param in self.named_parameters():
            if 'weight' in name and 'bn' not in name:
                if len(param.shape) >= 2:
                    nn.init.xavier_uniform_(param)
                else:
                    nn.init.normal_(param)
            elif 'bias' in name:
                nn.init.constant_(param, 0.0)
    
    def forward(
        self, 
        x: torch.Tensor, 
        edge_index: torch.Tensor,
        edge_attr: Optional[torch.Tensor] = None,
        hx: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass of the model.
        
        Args:
            x: Input features [batch_size, seq_len, num_nodes, node_features]
            edge_index: Graph connectivity [2, num_edges]
            edge_attr: Not used, kept for compatibility
            hx: Optional hidden state for GRU
            
        Returns:
            Dictionary with 'order_quantity' and 'demand_forecast' predictions
        """
        batch_size, seq_len, num_nodes, node_features = x.shape
        
        # Project input features
        x = self.input_proj(x)  # [batch_size, seq_len, num_nodes, hidden_dim]
        
        # Process each time step
        h_list = []
        for t in range(seq_len):
            # Get node features for this time step
            x_t = x[:, t]  # [batch_size, num_nodes, hidden_dim]
            
            # Process each sample in the batch separately
            batch_h = []
            for b in range(batch_size):
                # Get features for this sample
                x_bt = x_t[b]  # [num_nodes, hidden_dim]
                
                # Apply GNN layers
                h_bt = x_bt
                for gnn_layer in self.gnn_layers:
                    h_bt = F.relu(gnn_layer(h_bt, edge_index))
                
                batch_h.append(h_bt.unsqueeze(0))  # [1, num_nodes, hidden_dim]
            
            # Stack batch samples
            h_t = torch.cat(batch_h, dim=0)  # [batch_size, num_nodes, hidden_dim]
            
            h_list.append(h_t.unsqueeze(1))  # [batch_size, 1, num_nodes, hidden_dim]
        
        # Stack hidden states
        h = torch.cat(h_list, dim=1)  # [batch_size, seq_len, num_nodes, hidden_dim]
        
        # Reshape for GRU: [batch_size * num_nodes, seq_len, hidden_dim]
        h = h.permute(0, 2, 1, 3).reshape(-1, seq_len, self.hidden_dim)
        
        # Apply GRU
        h, _ = self.gru(h, hx)  # [batch_size * num_nodes, seq_len, hidden_dim]
        
        # Get the last hidden state
        h_last = h[:, -1]  # [batch_size * num_nodes, hidden_dim]
        
        # Reshape back to [batch_size, num_nodes, hidden_dim]
        h_last = h_last.view(batch_size, num_nodes, self.hidden_dim)
        
        # Get predictions
        order_quantity = self.order_head(h_last)  # [batch_size, num_nodes, 1]
        demand_forecast = self.demand_head(h_last)  # [batch_size, num_nodes, 1]
        
        return {
            'order_quantity': order_quantity,
            'demand_forecast': demand_forecast
        }
