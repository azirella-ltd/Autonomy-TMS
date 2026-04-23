import os
import torch
import numpy as np
from datetime import datetime
from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm

from app.models.gnn.temporal_gnn import SupplyChainTemporalGNN, SupplyChainAgent, create_supply_chain_agents
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.db.session import SessionLocal
from app import crud, schemas

# Set up logging
logger = setup_logging(__name__)

def load_synthetic_data(data_path: str, num_episodes: int = 100):
    """Load synthetic data from JSON file.
    
    Args:
        data_path: Path to the JSON file containing synthetic data
        num_episodes: Maximum number of episodes to load
        
    Returns:
        List of scenario data dictionaries
    """
    import json
    with open(data_path, 'r') as f:
        scenarios = json.load(f)
    return scenarios[:num_episodes]

def prepare_training_data(data_path: str, num_episodes: int = 100, seq_len: int = 10):
    """
    Prepare training data from synthetic scenario data.
    
    Args:
        data_path: Path to the JSON file containing synthetic data
        num_episodes: Number of episodes to use for training
        seq_len: Length of the sequence to use for each sample
        
    Returns:
        List of (observation, action, reward, next_observation, done) tuples
    """
    # Load scenarios from JSON file
    scenarios = load_synthetic_data(data_path, num_episodes)
    training_data = []
    
    for scenario in scenarios:
        rounds = scenario.get('rounds', [])
        
        # Skip scenarios with too few rounds
        if len(rounds) < seq_len + 1:
            continue
            
        # Convert to sequential samples
        for i in range(len(rounds) - seq_len):
            # Get sequence of rounds
            sequence = rounds[i:i + seq_len + 1]
            
            # Extract node features for each role in each round
            node_features = []
            actions = []
            rewards = []
            
            for round_data in sequence:
                round_number = round_data['round_number']
                decisions = round_data.get('decisions', [])
                
                # Create node features for each role
                role_features = {}
                for decision in decisions:
                    role = decision['role']
                    role_features[role] = [
                        decision.get('inventory', 0),
                        decision.get('backlog', 0),
                        decision.get('incoming_shipment', 0),
                        decision.get('demand', 0),
                        decision.get('order_quantity', 0)
                    ]
                    
                    # Store action (order quantity) for this role
                    if 'order_quantity' in decision:
                        actions.append(decision['order_quantity'])
                    
                    # Simple reward function (negative of total cost)
                    cost = decision.get('inventory_cost', 0) + decision.get('backlog_cost', 0)
                    rewards.append(-cost)
                
                # Ensure all roles are present
                for role in ['retailer', 'wholesaler', 'distributor', 'manufacturer']:
                    if role not in role_features:
                        role_features[role] = [0] * 5  # Default features if missing
                
                # Flatten features in a consistent order
                features = []
                for role in ['retailer', 'wholesaler', 'distributor', 'manufacturer']:
                    features.extend(role_features[role])
                
                node_features.append(features)
            
            # Create edge indices (fully connected graph)
            num_nodes = 4  # 4 roles
            edge_index = []
            edge_attr = []
            
            # Define edge attributes (lead_time, cost, relationship_strength)
            edge_attributes = {
                ('retailer', 'wholesaler'): [1, 1.0, 1.0],
                ('wholesaler', 'distributor'): [2, 1.0, 1.0],
                ('distributor', 'manufacturer'): [3, 1.0, 1.0]
            }
            
            # Add forward edges
            for i, role1 in enumerate(['retailer', 'wholesaler', 'distributor']):
                for j, role2 in enumerate(['wholesaler', 'distributor', 'manufacturer']):
                    if (role1, role2) in edge_attributes:
                        edge_index.append([i, j+1])  # +1 because of 0-based indexing
                        edge_attr.append(edge_attributes[(role1, role2)])
            
            # Add backward edges
            for i, role1 in enumerate(['wholesaler', 'distributor', 'manufacturer']):
                for j, role2 in enumerate(['retailer', 'wholesaler', 'distributor']):
                    if (role2, role1) in edge_attributes:
                        edge_index.append([i+1, j])  # +1 because of 0-based indexing
                        edge_attr.append(edge_attributes[(role2, role1)])
            
            # Convert to tensors
            node_features = torch.FloatTensor(node_features)
            edge_index = torch.LongTensor(edge_index).t().contiguous()
            edge_attr = torch.FloatTensor(edge_attr)
            actions = torch.FloatTensor(actions)
            rewards = torch.FloatTensor(rewards)
            
            # Add to training data
            training_data.append({
                'node_features': node_features,
                'edge_index': edge_index,
                'edge_attr': edge_attr,
                'actions': actions,
                'rewards': rewards
            })
    
    return training_data

def train_agents(
    data_path: str,
    num_episodes: int = 100,
    batch_size: int = 32,
    seq_len: int = 10,
    num_epochs: int = 10,
    learning_rate: float = 1e-3,
    save_dir: str = "models/tgnn",
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
):
    """
    Train the TemporalGNN agents.
    
    Args:
        data_path: Path to the JSON file containing training data
        num_episodes: Number of episodes to use for training
        batch_size: Batch size for training
        seq_len: Length of the sequence to use for each sample
        num_epochs: Number of training epochs
        learning_rate: Learning rate for the optimizer
        save_dir: Directory to save the trained models
        device: Device to use for training ('cuda' or 'cpu')
    """
    import os
    from torch.utils.data import DataLoader, TensorDataset
    from torch.nn.utils.rnn import pad_sequence
    
    # Create save directory if it doesn't exist
    os.makedirs(save_dir, exist_ok=True)
    
    # Prepare training data
    training_data = prepare_training_data(data_path, num_episodes, seq_len)
    
    if not training_data:
        logger.error("No training data available. Exiting.")
        return
    
    # Create data loaders
    def collate_fn(batch):
        # Pad sequences to the same length
        node_features = pad_sequence([item['node_features'] for item in batch], batch_first=True)
        actions = pad_sequence([item['actions'] for item in batch], batch_first=True)
        rewards = pad_sequence([item['rewards'] for item in batch], batch_first=True)
        
        # Edge index and attributes are the same for all samples
        edge_index = batch[0]['edge_index'].to(device)
        edge_attr = batch[0]['edge_attr'].to(device)
        
        return {
            'node_features': node_features.to(device),
            'edge_index': edge_index,
            'edge_attr': edge_attr,
            'actions': actions.to(device),
            'rewards': rewards.to(device)
        }
    
    # Split into train and validation sets
    train_size = int(0.8 * len(training_data))
    val_size = len(training_data) - train_size
    train_data, val_data = torch.utils.data.random_split(training_data, [train_size, val_size])
    
    train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True, collate_fn=collate_fn)
    val_loader = DataLoader(val_data, batch_size=batch_size, shuffle=False, collate_fn=collate_fn)
    
    # Create agents
    agents = create_supply_chain_agents(
        num_agents=4,
        shared_model=True,
        learning_rate=learning_rate,
        device=device
    )
    
    # Training loop
    best_val_loss = float('inf')
    
    for epoch in range(num_epochs):
        # Training
        for agent in agents:
            agent.model.train()
        
        train_loss = 0.0
        for batch in train_loader:
            for i, agent in enumerate(agents):
                # Update agent with batch data
                loss = agent.update_batch(batch, agent_idx=i)
                train_loss += loss
        
        # Validation
        for agent in agents:
            agent.model.eval()
        
        val_loss = 0.0
        with torch.no_grad():
            for batch in val_loader:
                for i, agent in enumerate(agents):
                    # Evaluate agent on validation batch
                    loss = agent.eval_batch(batch, agent_idx=i)
                    val_loss += loss
        
        # Log metrics
        train_loss /= len(train_loader)
        val_loss /= len(val_loader)
        
        logger.info(f"Epoch {epoch+1}/{num_epochs} - "
                   f"Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")
        
        # Save best model
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            for i, agent in enumerate(agents):
                save_path = os.path.join(save_dir, f"agent_{i}_best.pt")
                torch.save(agent.model.state_dict(), save_path)
            logger.info(f"Saved new best model with val loss: {val_loss:.4f}")
    
    # Save final models
    for i, agent in enumerate(agents):
        save_path = os.path.join(save_dir, f"agent_{i}_final.pt")
        torch.save(agent.model.state_dict(), save_path)
    
    logger.info("Training complete. Models saved to {}".format(os.path.abspath(save_dir)))
    return agents
                    observations=observations,
                    actions=agent_actions,
                    rewards=rewards,
                    next_observations=next_observations,
                    dones=dones
                )
                
                # Log losses
                for loss_name, loss_value in losses.items():
                    writer.add_scalar(f"agent_{agent_idx}/{loss_name}", loss_value, global_step)
            
            global_step += 1
        
        # Save model checkpoint
        if (epoch + 1) % 5 == 0:
            checkpoint_path = os.path.join(save_dir, f"tgnn_epoch_{epoch+1}.pt")
            torch.save({
                'epoch': epoch,
                'model_state_dict': agents[0].model.state_dict(),  # All agents share the same model
                'optimizer_state_dict': agents[0].optimizer.state_dict(),
                'loss': losses.get('total_loss', 0.0),
            }, checkpoint_path)
            logger.info(f"Saved checkpoint to {checkpoint_path}")
    
    # Save final model
    final_path = os.path.join(save_dir, "tgnn_final.pt")
    return agents

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Train TemporalGNN agents on supply chain data')
    parser.add_argument('--data_path', type=str, default='data/synthetic_games_20250903_211141.json',
                        help='Path to the JSON file containing training data')
    parser.add_argument('--num_episodes', type=int, default=100,
                        help='Number of episodes to use for training')
    parser.add_argument('--batch_size', type=int, default=32,
                        help='Batch size for training')
    parser.add_argument('--seq_len', type=int, default=10,
                        help='Length of the sequence to use for each sample')
    parser.add_argument('--num_epochs', type=int, default=50,
                        help='Number of training epochs')
    parser.add_argument('--learning_rate', type=float, default=1e-3,
                        help='Learning rate for the optimizer')
    parser.add_argument('--save_dir', type=str, default='models/tgnn',
                        help='Directory to save the trained models')
    parser.add_argument('--device', type=str, default='cuda' if torch.cuda.is_available() else 'cpu',
                        help='Device to use for training (cuda or cpu)')
    
    args = parser.parse_args()
    
    # Run training
    train_agents(
        data_path=args.data_path,
        num_episodes=args.num_episodes,
        batch_size=args.batch_size,
        seq_len=args.seq_len,
        num_epochs=args.num_epochs,
        learning_rate=args.learning_rate,
        save_dir=args.save_dir,
        device=args.device
    )
