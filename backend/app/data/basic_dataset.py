import os
import torch
import numpy as np
from torch.utils.data import Dataset
from typing import Optional, Callable

class BasicSupplyChainDataset(Dataset):
    """A basic PyTorch Dataset for supply chain data."""
    
    def __init__(self, 
                 data_dir: str = 'data/basic_processed',
                 seq_len: int = 10,
                 pred_len: int = 1,
                 transform: Optional[Callable] = None):
        """
        Initialize the dataset.
        
        Args:
            data_dir: Directory to store/load the data
            seq_len: Length of input sequences
            pred_len: Length of prediction sequences
            transform: Optional data transformation
        """
        self.data_dir = data_dir
        self.seq_len = seq_len
        self.pred_len = pred_len
        self.transform = transform
        
        # Create directory if it doesn't exist
        os.makedirs(self.data_dir, exist_ok=True)
        
        # File paths
        self.features_path = os.path.join(self.data_dir, 'features.pt')
        self.targets_path = os.path.join(self.data_dir, 'targets.pt')
        self.edge_index_path = os.path.join(self.data_dir, 'edge_index.pt')
        
        # Generate or load data
        if not os.path.exists(self.features_path):
            self._generate_sample_data()
        else:
            self.features = torch.load(self.features_path)
            self.targets = torch.load(self.targets_path)
            self.edge_index = torch.load(self.edge_index_path)
        
        # Calculate number of samples
        self.num_samples = len(self.features) - self.seq_len - self.pred_len + 1
        self.num_samples = min(100, self.num_samples)  # Limit to 100 samples for testing
    
    def _generate_sample_data(self):
        """Generate sample data for testing."""
        print("Generating sample data...")
        
        # Parameters
        num_nodes = 4  # Number of nodes in the supply chain
        num_features = 10
        num_time_steps = 100
        
        # Generate random features and targets
        features = torch.randn(num_time_steps, num_nodes, num_features, dtype=torch.float32)
        targets = torch.randn(num_time_steps, num_nodes, 2, dtype=torch.float32)
        
        # Create a fully connected graph (except self-loops)
        edge_index = []
        for i in range(num_nodes):
            for j in range(num_nodes):
                if i != j:
                    edge_index.append([i, j])
        edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()
        
        # Save the data
        torch.save(features, self.features_path)
        torch.save(targets, self.targets_path)
        torch.save(edge_index, self.edge_index_path)
        
        self.features = features
        self.targets = targets
        self.edge_index = edge_index
        
        print(f"Sample data generated and saved to {self.data_dir}")
    
    def __len__(self) -> int:
        return self.num_samples
    
    def __getitem__(self, idx: int):
        # Get sequence and target windows
        x = self.features[idx:idx+self.seq_len]
        y = self.targets[idx+self.seq_len:idx+self.seq_len+self.pred_len]
        
        # Create a sample dictionary
        sample = {
            'x': x,  # [seq_len, num_nodes, num_features]
            'y': y,  # [pred_len, num_nodes, 2]
            'edge_index': self.edge_index,
            'num_nodes': 4,
            'seq_len': self.seq_len,
            'pred_len': self.pred_len
        }
        
        if self.transform:
            sample = self.transform(sample)
            
        return sample
    
    def __repr__(self) -> str:
        return (f'{self.__class__.__name__}(len={len(self)}, '
                f'seq_len={self.seq_len}, pred_len={self.pred_len})')
