import os
import torch
import torch.nn.functional as F
import numpy as np
from datetime import datetime
from pathlib import Path
from torch.utils.data import DataLoader, Dataset
from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm
import json
import argparse
import logging
from typing import List, Dict, Tuple, Optional, Union, Any

from app.models.gnn.temporal_gnn import SupplyChainTemporalGNN, SupplyChainAgent, create_supply_chain_agents
from app.core.logging_config import setup_logging
from app.utils.device import (
    get_available_device, 
    to_device, 
    set_device,
    device_scope,
    is_cuda_available,
    empty_cache
)

# Set up logging
logger = setup_logging(__name__)


def _slugify_identifier(raw: str) -> str:
    token = raw.strip().lower()
    if not token:
        return ""
    sanitized = [ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in token]
    slug = "".join(sanitized).strip("-_")
    return slug


def _derive_run_identifier(
    config_identifier: Optional[str],
    *,
    data_path: Optional[str] = None,
    default: Optional[str] = None,
) -> str:
    candidates = [
        config_identifier,
        os.getenv("SC_CONFIG_IDENTIFIER"),
        os.getenv("SUPPLY_CHAIN_CONFIG"),
        default,
    ]
    for candidate in candidates:
        if candidate:
            slug = _slugify_identifier(candidate)
            if slug:
                return slug

    if data_path:
        stem = Path(data_path).stem
        for suffix in ("_dataset", "-dataset", "_data", "-data"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        slug = _slugify_identifier(stem)
        if slug:
            return slug

    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")

def load_synthetic_data(data_path: str, num_episodes: int = 100) -> List[dict]:
    """Load synthetic data from JSON file.
    
    Args:
        data_path: Path to the JSON file containing synthetic data
        num_episodes: Maximum number of episodes to load
        
    Returns:
        List of scenario data dictionaries
    """
    # Load synthetic data
    if not os.path.exists(data_path):
        # Try to load the default synthetic data file
        data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'synthetic_games_20250903_211141.json')
    
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    # Handle both formats: direct list or wrapped in 'scenarios' key
    if isinstance(data, list):
        scenarios = data[:num_episodes]
    else:
        scenarios = data.get('scenarios', [])[:num_episodes]
    return scenarios

def prepare_training_data(
    data_path: str, 
    num_episodes: int = 100, 
    seq_len: int = 10
) -> List[Dict]:
    """Prepare training data from synthetic scenario data.
    
    Args:
        data_path: Path to the JSON file containing synthetic data
        num_episodes: Number of episodes to use for training
        seq_len: Length of the sequence to use for each sample
        
    Returns:
        List of training samples with observations, actions, rewards, etc.
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
                
                # Create node features tensor with shape [num_nodes, node_features]
                # Order: retailer, wholesaler, distributor, manufacturer
                features = torch.tensor([
                    role_features['retailer'],
                    role_features['wholesaler'],
                    role_features['distributor'],
                    role_features['manufacturer']
                ], dtype=torch.float32)
                
                node_features.append(features)
            
            # Create edge indices (fully connected graph)
            num_nodes = 4  # 4 roles
            edge_index = []
            
            # Add edges between consecutive nodes in the supply chain
            for i in range(num_nodes - 1):
                edge_index.append([i, i+1])  # Forward edge
                edge_index.append([i+1, i])  # Backward edge
            
            edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()
            
            # Edge attributes: [lead_time, cost, relationship_strength]
            edge_attr = []
            for _ in edge_index.T:
                edge_attr.append([1.0, 1.0, 1.0])  # Placeholder values
            edge_attr = torch.tensor(edge_attr, dtype=torch.float32)
            
            # Stack along sequence dimension to get [seq_len, num_nodes, node_features]
            node_features = torch.stack(node_features, dim=0)
            
            # Ensure we have the correct shape [batch_size=1, seq_len, num_nodes, node_features]
            if len(node_features.shape) == 3:
                node_features = node_features.unsqueeze(0)  # Add batch dimension
            
            # Verify final shape
            if len(node_features.shape) != 4:
                raise ValueError(f"Expected node_features to have 4 dimensions, got {node_features.shape}")
            
            actions = torch.tensor(actions, dtype=torch.float32).unsqueeze(1)  # [seq_len, 1]
            rewards = torch.tensor(rewards, dtype=torch.float32).unsqueeze(1)  # [seq_len, 1]
            
            # Add to training data
            training_data.append({
                'node_features': node_features,
                'edge_index': edge_index,
                'edge_attr': edge_attr,
                'actions': actions,
                'rewards': rewards
            })
    
    return training_data

class SupplyChainDataset(torch.utils.data.Dataset):
    """Custom dataset for supply chain data."""
    def __init__(self, data):
        self.data = data
    
    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, idx):
        return self.data[idx]

def collate_fn(batch):
    """Collate function for DataLoader to handle sequences of node features."""
    # Get sequence length (should be the same for all samples)
    seq_len = len(batch[0]['node_features'])
    
    # Initialize lists to store batched data
    batched_node_features = []
    batched_actions = []
    batched_rewards = []
    
    # Stack sequences for each timestep
    for t in range(seq_len):
        # Get node features for this timestep across all samples in batch
        node_features_t = torch.stack([item['node_features'][t] for item in batch])
        batched_node_features.append(node_features_t)
        
        # Get actions and rewards for this timestep
        actions_t = torch.stack([item['actions'][t] for item in batch])
        rewards_t = torch.stack([item['rewards'][t] for item in batch])
        
        batched_actions.append(actions_t)
        batched_rewards.append(rewards_t)
    
    # Stack along sequence dimension
    node_features = torch.stack(batched_node_features, dim=1)  # [batch_size, seq_len, num_nodes, node_features]
    actions = torch.stack(batched_actions, dim=1)  # [batch_size, seq_len]
    rewards = torch.stack(batched_rewards, dim=1)  # [batch_size, seq_len]
    
    # Edge index and attributes (same for all samples)
    edge_index = batch[0]['edge_index']
    edge_attr = batch[0].get('edge_attr', None)
    
    return {
        'node_features': node_features,
        'actions': actions,
        'rewards': rewards,
        'edge_index': edge_index,
        'edge_attr': edge_attr
    }

def train_agents(
    data_path: str,
    num_episodes: int = 100,
    batch_size: int = 32,
    seq_len: int = 10,
    num_epochs: int = 10,
    learning_rate: float = 1e-3,
    save_dir: str = "models/tgnn",
    device: Optional[Union[str, torch.device]] = None,
    force_cpu: bool = False,
    clip_grad_norm: float = 1.0,
    num_workers: Optional[int] = None,
    config_identifier: Optional[str] = None,
) -> List[SupplyChainAgent]:
    """Train the TemporalGNN agents with enhanced device management.
    
    Args:
        data_path: Path to the JSON file containing training data
        num_episodes: Number of episodes to use for training
        batch_size: Batch size for training
        seq_len: Length of the sequence to use for each sample
        num_epochs: Number of training epochs
        learning_rate: Learning rate for the optimizer
        save_dir: Directory to save the trained models
        device: Device to use for training (None for auto-detect)
        force_cpu: If True, force CPU usage even if GPU is available
        clip_grad_norm: Maximum gradient norm for gradient clipping
        num_workers: Number of worker processes for data loading (None for auto-detect)
        
    Returns:
        List of trained SupplyChainAgent instances
    """
    # Set up device with enhanced utilities
    if device is None:
        if force_cpu or os.environ.get('FORCE_CPU', '0').lower() in ('1', 'true', 'yes'):
            device = 'cpu'
        else:
            device = get_available_device()
    
    # Set the global device and initialize device context
    set_device(device)
    device = torch.device(device)
    logger.info(f"Using device: {device}")
    
    # Set up CUDA if available
    use_cuda = device.type == 'cuda'
    if use_cuda:
        try:
            torch.backends.cudnn.benchmark = True
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
        except Exception as e:
            logger.warning(f"Could not optimize CUDA settings: {e}")
    
    # Create save directory if it doesn't exist
    os.makedirs(save_dir, exist_ok=True)
    
    identifier = _derive_run_identifier(
        config_identifier,
        data_path=data_path,
    )
    log_dir = os.path.join("runs", f"tgnn_{identifier}")
    writer = SummaryWriter(log_dir)
    
    # Determine number of workers for data loading
    if num_workers is None:
        num_workers = min(4, (os.cpu_count() or 1) // 2)
    
    # Create agents with device context
    with device_scope(device):
        # Create a single model instance to be shared among agents
        model = SupplyChainTemporalGNN(device='cpu')  # Initialize on CPU first
        model = model.to(device)  # Then move to target device
        
        # Create agents (one for each role, sharing the same model)
        agents = create_supply_chain_agents(
            num_agents=4,  # retailer, wholesaler, distributor, manufacturer
            shared_model=True,
            learning_rate=learning_rate,
            device=device
        )
        
        # Set the shared model for all agents
        for agent in agents:
            agent.model = model
    
    # Model has been created and moved to device in the device_scope
    
    # Prepare training data
    logger.info("Preparing training data...")
    training_data = prepare_training_data(data_path, num_episodes, seq_len)
    logger.info(f"Prepared {len(training_data)} training samples")
    
    if not training_data:
        logger.error("No training data available. Exiting.")
        return None
    
    # Training loop
    global_step = 0
    best_val_loss = float('inf')
    
    for epoch in range(num_epochs):
        logger.info(f"Starting epoch {epoch+1}/{num_epochs}")
        
        # Shuffle training data
        np.random.shuffle(training_data)
        
        # Split into training and validation sets (80/20)
        split_idx = int(0.8 * len(training_data))
        train_data = training_data[:split_idx]
        val_data = training_data[split_idx:]
        
        # Create datasets
        train_dataset = SupplyChainDataset(train_data)
        val_dataset = SupplyChainDataset(val_data)
        
        # Create data loaders with optimized settings
        pin_memory = use_cuda
        persistent_workers = num_workers > 0
        
        # Configure DataLoader for training
        train_loader = DataLoader(
            train_dataset,
            batch_size=batch_size,
            shuffle=True,
            collate_fn=collate_fn,
            num_workers=num_workers,
            pin_memory=pin_memory,
            persistent_workers=persistent_workers,
            prefetch_factor=2 if num_workers > 0 else None,
            drop_last=True  # Avoid issues with batch norm on last batch
        )
        
        # Configure DataLoader for validation
        val_loader = DataLoader(
            val_dataset,
            batch_size=batch_size,
            shuffle=False,
            collate_fn=collate_fn,
            num_workers=num_workers,
            pin_memory=pin_memory,
            persistent_workers=persistent_workers
        )
        
        # Training phase
        train_loss = 0.0
        num_batches = 0
        
        # Set all agents to training mode
        for agent in agents:
            agent.model.train()
        
        # Process batches with tqdm for progress tracking
        train_iter = tqdm(train_loader, desc=f"Epoch {epoch+1}/{num_epochs} [Train]", leave=False)
        
        for batch_idx, batch in enumerate(train_iter):
            try:
                # Move data to device using non-blocking transfer
                batch = to_device(batch, device, non_blocking=True)
                
                # Unpack batch with device awareness
                observations = batch['node_features'].to(device)
                actions = batch['actions'].to(device)
                rewards = batch['rewards'].to(device)
                edge_index = batch['edge_index'].to(device)
                edge_attr = batch.get('edge_attr')
                if edge_attr is not None:
                    edge_attr = edge_attr.to(device)
                
                # Get tensor dimensions
                if len(observations.shape) == 4:
                    batch_size, seq_len, num_nodes, node_feat_dim = observations.shape
                elif len(observations.shape) == 5:
                    # Handle case where there's an extra dimension
                    batch_size, seq_len, _, num_nodes, node_feat_dim = observations.shape
                    observations = observations.squeeze(2)  # Remove the extra dimension
                else:
                    raise ValueError(f"Unexpected observations shape: {observations.shape}")
                
                print(f"Batch shape: {observations.shape}")
                
                # Create next_observations by shifting the sequence by 1
                next_observations = torch.cat([
                    observations[:, 1:],  # All but first timestep
                    observations[:, -1:].detach().clone()  # Repeat last timestep
                ], dim=1)
                
                # Process each timestep in the sequence
                batch_loss = 0.0
                
                for t in range(seq_len):
                    # Get current and next observations
                    # observations shape: [batch_size, seq_len, num_nodes, node_features]
                    node_features = observations[:, t]  # [batch_size, num_nodes, node_features]
                    next_node_features = next_observations[:, t]  # [batch_size, num_nodes, node_features]
                    
                    # Ensure all tensors are on the correct device
                    node_features = node_features.to(device)
                    next_node_features = next_node_features.to(device)
                    
                    # Create observation dictionaries for each sample in the batch
                    for b in range(batch_size):
                        # Get the current batch item and ensure it's on the right device
                        node_feat = node_features[b].unsqueeze(0)  # [1, num_nodes, node_features]
                        next_node_feat = next_node_features[b].unsqueeze(0)  # [1, num_nodes, node_features]
                        
                        # Ensure edge_index and edge_attr are on the same device as node features
                        edge_idx = edge_index.to(device)
                        edge_attr_dev = edge_attr.to(device) if edge_attr is not None else None
                        
                        obs = {
                            'node_features': node_feat,
                            'edge_index': edge_idx,
                            'edge_attr': edge_attr_dev
                        }
                        
                        next_obs = {
                            'node_features': next_node_feat,
                            'edge_index': edge_idx,
                            'edge_attr': edge_attr_dev
                        }
                    
                        # Update each agent for this batch sample
                        for i, agent in enumerate(agents):
                            # Get action for the current agent
                            # Ensure we have a valid action index
                            action_idx = min(i, actions.size(2) - 1) if len(actions.shape) > 2 else 0
                            agent_action = actions[b, t, action_idx] if len(actions.shape) > 2 else actions[t]
                            
                            # Convert to tensor if needed
                            if not isinstance(agent_action, torch.Tensor):
                                agent_action = torch.tensor(agent_action, device=device, dtype=torch.long)
                            
                            # Update agent with device context
                            with device_scope(device):
                                loss = agent.update(
                                    observations=[obs],
                                    actions=[agent_action.item()],  # Pass scalar value
                                    rewards=[rewards[b, t].item()],
                                    next_observations=[next_obs],
                                    dones=[t == seq_len - 1],  # Last timestep in sequence
                                    gamma=0.99,
                                    clip_grad_norm=clip_grad_norm
                                )
                                
                                # Update metrics
                                batch_loss += loss.get('loss', 0.0)
                                
                                # Log training metrics
                                writer.add_scalar(f'train/agent_{i}/loss', loss.get('loss', 0), global_step)
                                if 'value_loss' in loss:
                                    writer.add_scalar(
                                        f'train/agent_{i}/value_loss', loss['value_loss'], global_step
                                    )
                                if 'policy_loss' in loss:
                                    writer.add_scalar(
                                        f'train/agent_{i}/policy_loss', loss['policy_loss'], global_step
                                    )
                                if 'grad_norm' in loss:
                                    writer.add_scalar(f'train/agent_{i}/grad_norm', loss['grad_norm'], global_step)
                    
                    global_step += 1
                
                # Update average loss
                avg_batch_loss = batch_loss / (seq_len * len(agents))
                train_loss += avg_batch_loss
                num_batches += 1
                
                # Update progress bar
                train_iter.set_postfix(loss=f"{avg_batch_loss:.4f}")
                
                # Manual garbage collection for memory management
                if use_cuda and (batch_idx + 1) % 10 == 0:
                    torch.cuda.empty_cache()
            
            except RuntimeError as e:
                if 'out of memory' in str(e).lower() and use_cuda:
                    logger.warning(f"CUDA out of memory on batch {batch_idx}. Reducing batch size and trying again...")
                    empty_cache()
                    # Reduce batch size for next attempt
                    batch_size = max(1, batch_size // 2)
                    logger.info(f"Reduced batch size to {batch_size}")
                    continue
                raise
        
        # Calculate average training loss
        train_loss = train_loss / max(1, num_batches)
        
        # Validation phase
        val_loss = 0.0
        num_val_batches = 0
        
        # Set all agents to evaluation mode
        for agent in agents:
            agent.model.eval()
        
        # Process validation batches with tqdm
        val_iter = tqdm(val_loader, desc=f"Epoch {epoch+1}/{num_epochs} [Val]", leave=False)
        
        with torch.no_grad():
            for batch_idx, batch in enumerate(val_iter):
                try:
                    # Move data to device
                    batch = to_device(batch, device, non_blocking=True)
                    
                    # Unpack batch
                    observations = batch['node_features']
                    actions = batch['actions']
                    rewards = batch['rewards']
                    
                    # Handle next_observations
                    next_observations = batch.get('next_node_features', None)
                    if next_observations is None:
                        next_observations = [obs.clone() for obs in observations[1:]]
                        next_observations.append(observations[-1].clone())
                    
                    # Process each timestep in the sequence
                    batch_val_loss = 0.0
                    seq_len = len(observations)
                    
                    for t in range(seq_len - 1):
                        # Prepare observations for all agents at once
                        node_features = observations[t].unsqueeze(0).unsqueeze(1)  # [1, 1, num_nodes, node_features]
                        next_node_features = next_observations[t].unsqueeze(0).unsqueeze(1)
                        
                        # Create observation dictionaries
                        obs = {
                            'node_features': node_features,
                            'edge_index': batch['edge_index'],
                            'edge_attr': batch.get('edge_attr')
                        }
                        
                        next_obs = {
                            'node_features': next_node_features,
                            'edge_index': batch['edge_index'],
                            'edge_attr': batch.get('edge_attr')
                        }
                        
                        # Evaluate each agent
                        for i, agent in enumerate(agents):
                            # Get action for the current agent
                            agent_action = actions[t][i] if isinstance(actions[t], (list, tuple)) else actions[t]
                            
                            # Get model outputs with device context
                            with device_scope(device):
                                outputs = agent.model(
                                    node_features=obs['node_features'],
                                    edge_index=obs['edge_index'],
                                    edge_attr=obs.get('edge_attr')
                                )
                                
                                # Get predictions
                                order_quantities = outputs['order_quantity']
                                demand_forecasts = outputs['demand_forecast']
                                
                                # Calculate losses
                                action_tensor = torch.as_tensor(agent_action, device=device, dtype=torch.float32)
                                action_tensor = action_tensor.view(-1, 1)  # Ensure shape [batch_size, 1]
                                
                                # Action loss (MSE between predicted and actual order quantities)
                                action_loss = F.mse_loss(order_quantities, action_tensor)
                                
                                # Value loss (MSE between predicted and actual rewards)
                                if isinstance(rewards[t], (list, np.ndarray, torch.Tensor)):
                                    reward_value = float(rewards[t][0]) if len(rewards[t]) > 0 else 0.0
                                else:
                                    reward_value = float(rewards[t])
                                
                                reward_tensor = torch.tensor([[reward_value]], device=device, dtype=torch.float32)
                                value_loss = F.mse_loss(demand_forecasts.mean(dim=1, keepdim=True), reward_tensor)
                                
                                # Combined loss
                                loss = action_loss + 0.5 * value_loss
                                batch_val_loss += loss.item()
                    
                    # Update metrics
                    avg_batch_val_loss = batch_val_loss / (seq_len * len(agents))
                    val_loss += avg_batch_val_loss
                    num_val_batches += 1
                    
                    # Update progress bar
                    val_iter.set_postfix(val_loss=f"{avg_batch_val_loss:.4f}")
                    
                    # Manual garbage collection
                    if use_cuda and (batch_idx + 1) % 10 == 0:
                        torch.cuda.empty_cache()
                
                except RuntimeError as e:
                    if 'out of memory' in str(e).lower() and use_cuda:
                        logger.warning(f"CUDA out of memory during validation on batch {batch_idx}. Skipping...")
                        empty_cache()
                        continue
                    raise
        
        # Calculate average validation loss
        val_loss = val_loss / max(1, num_val_batches)
        
        # Log epoch metrics
        logger.info(f"Epoch {epoch+1}/{num_epochs} - "
                  f"Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")
        
        # Log to TensorBoard
        writer.add_scalar('loss/train', train_loss, epoch)
        writer.add_scalar('loss/val', val_loss, epoch)
        
        # Save best model
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            try:
                # Save each agent's model
                for i, agent in enumerate(agents):
                    save_path = os.path.join(save_dir, f"agent_{i}_best.pt")
                    # Save with metadata
                    torch.save({
                        'epoch': epoch,
                        'model_state_dict': agent.model.state_dict(),
                        'optimizer_state_dict': agent.optimizer.state_dict(),
                        'loss': val_loss,
                        'config': {
                            'site_id': agent.site_id,
                            'learning_rate': agent.optimizer.param_groups[0]['lr']
                        }
                    }, save_path)
                
                logger.info(f"Saved new best model with val loss: {val_loss:.4f}")
                
            except Exception as e:
                logger.error(f"Error saving best model: {e}")
        
        # Save checkpoint every 5 epochs
        if (epoch + 1) % 5 == 0 or (epoch + 1) == num_epochs:
            checkpoint_path = os.path.join(save_dir, f'checkpoint_epoch_{epoch+1}.pt')
            try:
                # Save a single checkpoint with all agents' states
                checkpoint = {
                    'epoch': epoch,
                    'best_val_loss': best_val_loss,
                    'config': {
                        'batch_size': batch_size,
                        'learning_rate': learning_rate,
                        'seq_len': seq_len
                    },
                    'agents': []
                }
                
                # Save each agent's state
                for i, agent in enumerate(agents):
                    checkpoint['agents'].append({
                        'site_id': agent.site_id,
                        'model_state_dict': agent.model.state_dict(),
                        'optimizer_state_dict': agent.optimizer.state_dict(),
                        'loss': val_loss
                    })
                
                # Save the checkpoint
                torch.save(checkpoint, checkpoint_path)
                logger.info(f"Saved checkpoint to {checkpoint_path}")
                
                # Clean up old checkpoints (keep only the latest 3)
                if (epoch + 1) > 10:  # Start cleaning up after 10 epochs
                    checkpoint_files = sorted([f for f in os.listdir(save_dir) 
                                            if f.startswith('checkpoint_epoch_') and f.endswith('.pt')])
                    # Keep the 3 most recent checkpoints
                    for old_checkpoint in checkpoint_files[:-3]:
                        try:
                            os.remove(os.path.join(save_dir, old_checkpoint))
                        except Exception as e:
                            logger.warning(f"Could not remove old checkpoint {old_checkpoint}: {e}")
                
            except Exception as e:
                logger.error(f"Error saving checkpoint: {e}")
    
    # Save final models with metadata
    try:
        for i, agent in enumerate(agents):
            save_path = os.path.join(save_dir, f"agent_{i}_final.pt")
            torch.save({
                'model_state_dict': agent.model.state_dict(),
                'optimizer_state_dict': agent.optimizer.state_dict(),
                'config': {
                    'site_id': agent.site_id,
                    'learning_rate': agent.optimizer.param_groups[0]['lr'],
                    'device': str(device)
                },
                'training_complete': True
            }, save_path)
        
        # Save a combined final checkpoint
        final_checkpoint = {
            'epoch': num_epochs,
            'best_val_loss': best_val_loss,
            'config': {
                'batch_size': batch_size,
                'learning_rate': learning_rate,
                'seq_len': seq_len,
                'num_epochs': num_epochs,
                'device': str(device)
            },
            'agents': [
                {
                    'site_id': agent.site_id,
                    'model_state_dict': agent.model.state_dict(),
                    'optimizer_state_dict': agent.optimizer.state_dict()
                }
                for agent in agents
            ]
        }
        
        final_checkpoint_path = os.path.join(save_dir, 'final_checkpoint.pt')
        torch.save(final_checkpoint, final_checkpoint_path)
        
        logger.info(f"Training complete. Models saved to {os.path.abspath(save_dir)}")
        
    except Exception as e:
        logger.error(f"Error saving final models: {e}")
    
    # Close TensorBoard writer
    writer.close()
    
    return agents

def parse_args():
    """Parse command line arguments with enhanced help and defaults."""
    parser = argparse.ArgumentParser(
        description='Train TemporalGNN agents on supply chain data with enhanced device management',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Data arguments
    data_group = parser.add_argument_group('Data')
    data_group.add_argument('--data-path', type=str, default='data/synthetic_games.json',
                          help='Path to the training data JSON file')
    data_group.add_argument('--num-episodes', type=int, default=100,
                          help='Number of episodes to use for training')
    data_group.add_argument('--batch-size', type=int, default=32,
                          help='Batch size for training')
    data_group.add_argument('--seq-len', type=int, default=10,
                          help='Sequence length for each training sample')
    
    # Training arguments
    train_group = parser.add_argument_group('Training')
    train_group.add_argument('--num-epochs', type=int, default=50,
                           help='Number of training epochs')
    train_group.add_argument('--learning-rate', type=float, default=1e-3,
                           help='Learning rate for the optimizer')
    train_group.add_argument('--clip-grad-norm', type=float, default=1.0,
                           help='Maximum gradient norm for gradient clipping')
    
    # Device and performance arguments
    device_group = parser.add_argument_group('Device')
    device_group.add_argument('--device', type=str, default=None,
                            help='Device to use for training (e.g., "cuda", "cuda:0", "cpu")')
    device_group.add_argument('--force-cpu', action='store_true',
                            help='Force CPU usage even if GPU is available')
    device_group.add_argument('--num-workers', type=int, default=None,
                            help='Number of worker processes for data loading')
    
    # Output arguments
    output_group = parser.add_argument_group('Output')
    output_group.add_argument('--save-dir', type=str, default='models/tgnn',
                            help='Directory to save the trained models')
    output_group.add_argument('--log-level', type=str, default='INFO',
                            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                            help='Logging level')
    output_group.add_argument(
        '--config-identifier',
        type=str,
        default=None,
        help='Supply chain configuration identifier used to name run artifacts',
    )
    
    return parser.parse_args()


def main():
    """Main training function with enhanced error handling and resource management."""
    # Parse command line arguments
    args = parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join(args.save_dir, 'training.log'))
        ]
    )
    
    logger = logging.getLogger(__name__)
    
    # Log command line arguments
    logger.info("Starting training with arguments:")
    for arg, value in vars(args).items():
        logger.info(f"  {arg}: {value}")
    
    try:
        # Create save directory if it doesn't exist
        os.makedirs(args.save_dir, exist_ok=True)
        
        # Save the command line arguments
        with open(os.path.join(args.save_dir, 'args.json'), 'w') as f:
            json.dump(vars(args), f, indent=2)
        
        # Set up device
        device = args.device
        if device is None and not args.force_cpu:
            device = get_available_device()
        
        # Log device information
        if torch.cuda.is_available() and device != 'cpu':
            logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
            logger.info(f"CUDA version: {torch.version.cuda}")
            logger.info(f"PyTorch version: {torch.__version__}")
            logger.info(f"CUDA device count: {torch.cuda.device_count()}")
        else:
            logger.info("Using CPU for training")
        
        # Train the agents
        agents = train_agents(
            data_path=args.data_path,
            num_episodes=args.num_episodes,
            batch_size=args.batch_size,
            seq_len=args.seq_len,
            num_epochs=args.num_epochs,
            learning_rate=args.learning_rate,
            save_dir=args.save_dir,
            device=device,
            force_cpu=args.force_cpu,
            clip_grad_norm=args.clip_grad_norm,
            num_workers=args.num_workers,
            config_identifier=args.config_identifier,
        )
        
        return 0
        
    except Exception as e:
        logger.exception("An error occurred during training:")
        return 1
    finally:
        # Ensure all resources are properly released
        if 'agents' in locals():
            del agents
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("Training session ended")


if __name__ == "__main__":
    import sys
    # Set environment variable to force CPU if needed
    # os.environ['FORCE_CPU'] = '1'  # Uncomment to force CPU usage
    sys.exit(main())
