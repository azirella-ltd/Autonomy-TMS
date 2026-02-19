import json
import os
import numpy as np
import torch
from torch_geometric.data import Data, Dataset, DataLoader
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

class SupplyChainDataset(Dataset):
    """PyTorch Geometric Dataset for supply chain data."""
    
    def __init__(self, 
                 data_path: str, 
                 seq_len: int = 10,
                 node_features: List[str] = [
                     'inventory', 'order_quantity', 'demand', 
                     'backlog', 'incoming_shipment'
                 ],
                 edge_attr: List[str] = [
                     'lead_time', 'cost', 'relationship_strength'
                 ]):
        """
        Args:
            data_path: Path to the JSON file containing game data
            seq_len: Length of the sequence to use for each sample
            node_features: List of node features to include
            edge_attr: List of edge attributes to include
        """
        super().__init__()
        self.seq_len = seq_len
        self.node_features = node_features
        self.edge_attr = edge_attr
        
        # Load and process data
        with open(data_path, 'r') as f:
            self.games = json.load(f)
        
        # Preprocess data
        self.samples = self._preprocess_data()
        
    def _preprocess_data(self) -> List[Dict]:
        """Convert raw game data into training samples."""
        samples = []
        
        for game in self.games:
            num_rounds = len(game['rounds'])
            roles = game['roles']
            num_roles = len(roles)
            
            # Create edge indices (fully connected graph)
            edge_index = []
            for i in range(num_roles):
                for j in range(num_roles):
                    if i != j:  # No self-loops
                        edge_index.append([i, j])
            edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()
            
            # Create edge attributes (all ones for now)
            edge_attr = torch.ones((edge_index.size(1), len(self.edge_attr)))
            
            # Create node features and targets for each time step
            for t in range(self.seq_len, num_rounds):
                # Get sequence of rounds
                seq_start = t - self.seq_len
                seq_end = t
                
                # Initialize node features and targets
                x = torch.zeros((self.seq_len, num_roles, len(self.node_features)))
                y_order = torch.zeros((num_roles,))
                y_demand = torch.zeros((num_roles,))
                
                # Fill node features
                for i in range(self.seq_len):
                    round_data = game['rounds'][seq_start + i]
                    for j, role in enumerate(roles):
                        # Find decision for this role
                        for decision in round_data['decisions']:
                            if decision['role'] == role:
                                x[i, j, 0] = decision['inventory']
                                x[i, j, 1] = decision['order_quantity']
                                x[i, j, 2] = decision['demand']
                                x[i, j, 3] = decision['backlog']
                                x[i, j, 4] = decision['incoming_shipment']
                                break
                
                # Set targets (next time step)
                next_round = game['rounds'][seq_end]
                for j, role in enumerate(roles):
                    for decision in next_round['decisions']:
                        if decision['role'] == role:
                            y_order[j] = decision['order_quantity']
                            y_demand[j] = decision['demand']
                            break
                
                # Normalize features
                x = self._normalize_features(x)
                
                samples.append({
                    'x': x,
                    'edge_index': edge_index,
                    'edge_attr': edge_attr,
                    'y_order': y_order,
                    'y_demand': y_demand,
                    'game_id': game['name'],
                    'round_num': t
                })
        
        return samples
    
    def _normalize_features(self, x: torch.Tensor) -> torch.Tensor:
        """Normalize features to zero mean and unit variance."""
        # Calculate mean and std across all nodes and time steps
        mean = x.mean(dim=(0, 1), keepdim=True)
        std = x.std(dim=(0, 1), keepdim=True) + 1e-6  # Add small constant to avoid division by zero
        
        # Normalize
        x_norm = (x - mean) / std
        
        return x_norm
    
    def __len__(self) -> int:
        return len(self.samples)
    
    def __getitem__(self, idx: int) -> Data:
        sample = self.samples[idx]
        
        return Data(
            x=sample['x'],
            edge_index=sample['edge_index'],
            edge_attr=sample['edge_attr'],
            y_order=sample['y_order'],
            y_demand=sample['y_demand'],
            game_id=sample['game_id'],
            round_num=sample['round_num']
        )

def create_data_loaders(
    data_path: str, 
    batch_size: int = 32,
    seq_len: int = 10,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    device: str = 'cuda' if torch.cuda.is_available() else 'cpu',
    num_workers: int = None,
    pin_memory: bool = None
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """
    Create train, validation, and test data loaders.
    
    Args:
        data_path: Path to the JSON file containing game data
        batch_size: Batch size for data loaders
        seq_len: Length of the sequence to use for each sample
        train_ratio: Ratio of data to use for training
        val_ratio: Ratio of data to use for validation
        
    Returns:
        Tuple of (train_loader, val_loader, test_loader)
    """
    # Create dataset
    dataset = SupplyChainDataset(data_path, seq_len=seq_len)
    
    # Split dataset
    num_samples = len(dataset)
    train_size = int(train_ratio * num_samples)
    val_size = int(val_ratio * num_samples)
    test_size = num_samples - train_size - val_size
    
    train_dataset, val_dataset, test_dataset = torch.utils.data.random_split(
        dataset, [train_size, val_size, test_size],
        generator=torch.Generator().manual_seed(42)
    )
    
    # Derive performant defaults for workers and pinning
    if num_workers is None:
        num_workers = max(0, min(4, (os.cpu_count() or 1) // 2))
    if pin_memory is None:
        pin_memory = (str(device).startswith('cuda') or getattr(device, 'type', '') == 'cuda')
    persistent_workers = bool(num_workers)

    # Create data loaders
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin_memory,
        persistent_workers=persistent_workers,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
        persistent_workers=persistent_workers,
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
        persistent_workers=persistent_workers,
    )
    
    return train_loader, val_loader, test_loader
