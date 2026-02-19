import torch
import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.models.gnn.temporal_gnn import SupplyChainTemporalGNN, create_supply_chain_agents

def generate_test_data(batch_size=4, seq_len=10, num_nodes=4, node_features=5, edge_features=3):
    """Generate test data for the TemporalGNN model."""
    # Generate random node features [batch_size, seq_len, num_nodes, node_features]
    node_features_data = torch.randn(batch_size, seq_len, num_nodes, node_features)
    
    # Create a fully connected directed graph for testing
    edge_index = []
    for i in range(num_nodes):
        for j in range(num_nodes):
            if i != j:  # No self-loops
                edge_index.append([i, j])
    
    edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()
    
    # Generate random edge features [num_edges, edge_features]
    edge_attr = torch.randn(edge_index.size(1), edge_features)
    
    return {
        'node_features': node_features_data,
        'edge_index': edge_index,
        'edge_attr': edge_attr
    }

def test_temporal_gnn():
    print("Testing TemporalGNN model...")
    
    # Generate test data
    batch_size = 4
    test_data = generate_test_data(batch_size=batch_size)
    
    # Initialize model with matching dimensions
    hidden_dim = 32  # Match this with the model's default hidden_dim
    model = SupplyChainTemporalGNN(
        node_features=5,      # Must match node_features in generate_test_data
        edge_features=3,      # Must match edge_features in generate_test_data
        hidden_dim=hidden_dim,
        num_layers=2,
        num_heads=1,          # Using single head for simplicity
        seq_len=10,           # Must match seq_len in generate_test_data
        num_nodes=4           # Must match num_nodes in generate_test_data
    )
    
    # Print model architecture for debugging
    print("\nModel Architecture:")
    print(model)
    
    # Test forward pass
    with torch.no_grad():
        # Process each sample in the batch individually
        all_order_quantities = []
        all_demand_forecasts = []
        
        for i in range(batch_size):
            # Process one sample at a time
            sample = {
                'node_features': test_data['node_features'][i:i+1],  # Keep batch dim
                'edge_index': test_data['edge_index'],
                'edge_attr': test_data['edge_attr']
            }
            
            outputs = model(
                node_features=sample['node_features'],
                edge_index=sample['edge_index'],
                edge_attr=sample['edge_attr']
            )
            
            all_order_quantities.append(outputs['order_quantity'])
            all_demand_forecasts.append(outputs['demand_forecast'])
        
        # Stack the results
        order_quantity = torch.cat(all_order_quantities, dim=0)
        demand_forecast = torch.cat(all_demand_forecasts, dim=0)
        
        # Check output shapes
        assert order_quantity.shape == (batch_size, 4), \
            f"Expected order_quantity shape [{batch_size}, 4], got {order_quantity.shape}"
        assert demand_forecast.shape == (batch_size, 4), \
            f"Expected demand_forecast shape [{batch_size}, 4], got {demand_forecast.shape}"
            
        print("✅ TemporalGNN forward pass test passed!")
    
    print("✅ TemporalGNN forward pass test passed!")
    
    # Test SupplyChainAgent
    print("\nTesting SupplyChainAgent...")
    agents = create_supply_chain_agents(num_agents=4, shared_model=True)
    
    # Test agent act method
    action = agents[0].act(test_data, training=False)
    assert action.shape == (batch_size,), f"Expected action shape [4], got {action.shape}"
    
    print("✅ SupplyChainAgent act() test passed!")
    
    # Test agent update method
    next_obs = generate_test_data(batch_size=batch_size)
    batch = {
        'observations': [test_data] * batch_size,
        'actions': [torch.randint(0, 10, (batch_size,)) for _ in range(batch_size)],
        'rewards': [1.0] * batch_size,
        'next_observations': [next_obs] * batch_size,
        'dones': [False] * batch_size
    }
    
    loss = agents[0].update(
        observations=batch['observations'],
        actions=batch['actions'],
        rewards=batch['rewards'],
        next_observations=batch['next_observations'],
        dones=batch['dones']
    )
    
    assert 'loss' in loss, "Training step did not return loss"
    print("✅ SupplyChainAgent update() test passed!")
    
    print("\nAll tests passed successfully! 🎉")

if __name__ == "__main__":
    test_temporal_gnn()
