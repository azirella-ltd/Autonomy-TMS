import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

# Try to import torch_geometric. If unavailable, we will fall back to a minimal MLP
try:
    from torch_geometric.nn import GCNConv, global_mean_pool  # type: ignore
    HAS_PYG = True
except Exception:  # ImportError most likely due to torch_sparse not installed
    GCNConv = None  # type: ignore
    global_mean_pool = None  # type: ignore
    HAS_PYG = False

class SupplyChainGNN(nn.Module):
    """Graph model when torch_geometric is available; else a simple MLP fallback."""

    def __init__(self, node_features=5, edge_features=3, hidden_channels=64, num_layers=3):
        super(SupplyChainGNN, self).__init__()

        self.has_pyg = HAS_PYG

        if self.has_pyg:
            # Node feature dimensions: [capacity_mean, capacity_std, lead_time_mean, lead_time_std, throughput_mean, throughput_std]
            self.node_encoder = nn.Linear(node_features, hidden_channels)
            self.edge_encoder = nn.Linear(edge_features, hidden_channels)

            # GNN layers
            self.convs = nn.ModuleList()
            for _ in range(num_layers):
                self.convs.append(GCNConv(hidden_channels, hidden_channels))

            # Prediction heads
            self.demand_forecast = nn.Sequential(
                nn.Linear(hidden_channels, hidden_channels // 2),
                nn.ReLU(),
                nn.Linear(hidden_channels // 2, 1)
            )
            self.inventory_optimizer = nn.Sequential(
                nn.Linear(hidden_channels, hidden_channels // 2),
                nn.ReLU(),
                nn.Linear(hidden_channels // 2, 1)
            )
        else:
            # Fallback: a tiny MLP over aggregated node features
            self.mlp = nn.Sequential(
                nn.Linear(node_features, hidden_channels),
                nn.ReLU(),
                nn.Linear(hidden_channels, hidden_channels // 2),
                nn.ReLU(),
            )
            self.demand_head = nn.Linear(hidden_channels // 2, 1)
            self.inventory_head = nn.Linear(hidden_channels // 2, 1)

    def forward(self, x, edge_index=None, edge_attr=None, batch=None):
        if self.has_pyg:
            x = F.relu(self.node_encoder(x))
            edge_attr = F.relu(edge_attr) if edge_attr is not None else None
            for conv in self.convs:
                # Pass edge_attr only if provided
                if edge_attr is not None:
                    x = F.relu(conv(x, edge_index, edge_attr=edge_attr))
                else:
                    x = F.relu(conv(x, edge_index))
            if batch is not None:
                x = global_mean_pool(x, batch)
            demand_pred = self.demand_forecast(x)
            optimal_inventory = self.inventory_optimizer(x)
            return demand_pred, optimal_inventory
        else:
            # Aggregate node features (mean pooling) then run MLP heads
            if x.dim() == 2:
                x_agg = x.mean(dim=0, keepdim=True)
            else:
                x_agg = x.view(1, -1)
            h = self.mlp(x_agg)
            return self.demand_head(h), self.inventory_head(h)

class SupplyChainSimulator:
    def __init__(self, gnn_model=None):
        self.gnn_model = gnn_model or SupplyChainGNN()
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.gnn_model.to(self.device)
        
    def prepare_graph_data(self, supply_chain_data):
        """Convert supply chain data to PyTorch Geometric format"""
        # This is a placeholder - implement based on your specific data structure
        pass
    
    def simulate_step(self, current_state, actions):
        """Simulate one step in the supply chain"""
        # Convert state to tensors
        x = torch.tensor(current_state['node_features'], dtype=torch.float).to(self.device)
        if HAS_PYG:
            edge_index = torch.tensor(current_state['edge_index'], dtype=torch.long).to(self.device)
            edge_attr = torch.tensor(current_state['edge_attr'], dtype=torch.float).to(self.device)
        else:
            edge_index = None
            edge_attr = None
        # Get predictions from model (works with or without torch_geometric)
        with torch.no_grad():
            demand_pred, optimal_inventory = self.gnn_model(x, edge_index=edge_index, edge_attr=edge_attr)
        
        # Apply actions and update state
        # This is a simplified example - implement your actual simulation logic here
        new_state = current_state.copy()
        # ... update state based on actions and predictions ...
        
        return new_state
    
    def run_simulation(self, initial_state, num_steps):
        """Run the simulation for a given number of steps"""
        states = [initial_state]
        current_state = initial_state
        
        for step in range(num_steps):
            # Get actions from smart agents
            actions = self.get_actions(current_state)
            
            # Simulate one step
            current_state = self.simulate_step(current_state, actions)
            states.append(current_state)
            
        return states
    
    def get_actions(self, state):
        """Get actions from smart agents at each node"""
        # Implement your agent logic here
        # This could use the GNN predictions, reinforcement learning, or other methods
        return {}  # Return actions for each node
