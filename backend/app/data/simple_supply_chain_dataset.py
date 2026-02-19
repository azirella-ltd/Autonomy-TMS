import os
import torch
import numpy as np
from torch_geometric.data import Data, InMemoryDataset
from typing import Optional, Callable, List
from pathlib import Path

class SimpleSupplyChainDataset(InMemoryDataset):
    """A simplified version of the SupplyChainDataset for testing."""
    
    def __init__(self, 
                 root: str = 'data/processed',
                 seq_len: int = 10,
                 pred_len: int = 1,
                 transform: Optional[Callable] = None,
                 pre_transform: Optional[Callable] = None):
        
        self.seq_len = seq_len
        self.pred_len = pred_len
        
        # Initialize the parent class first to set up the directory structure
        super().__init__(root, transform, pre_transform)
        
        # Generate sample data if it doesn't exist
        if not os.path.exists(os.path.join(self.raw_dir, 'features.npy')):
            self._create_sample_data()
        
        # Process the data if needed
        if not os.path.exists(self.processed_paths[0]):
            self.process()
            
        # Load the processed data
        self.data, self.slices = torch.load(self.processed_paths[0])
    
    @property
    def raw_file_names(self):
        return ['features.npy', 'targets.npy', 'edge_index.pt']
    
    @property
    def processed_file_names(self):
        return ['data.pt']
    
    def _create_sample_data(self):
        """Create sample data for testing."""
        print("Creating sample data...")
        
        # Parameters
        num_nodes = 4  # Number of nodes in the supply chain
        num_features = 10
        num_time_steps = 100
        
        # Generate random features and targets
        features = np.random.randn(num_time_steps, num_nodes, num_features).astype(np.float32)
        targets = np.random.randn(num_time_steps, num_nodes, 2).astype(np.float32)
        
        # Create a fully connected graph (except self-loops)
        edge_index = []
        for i in range(num_nodes):
            for j in range(num_nodes):
                if i != j:
                    edge_index.append([i, j])
        edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()
        
        # Save raw data
        np.save(os.path.join(self.raw_dir, 'features.npy'), features)
        np.save(os.path.join(self.raw_dir, 'targets.npy'), targets)
        torch.save(edge_index, os.path.join(self.raw_dir, 'edge_index.pt'))
        
        print(f"Sample data created in {self.raw_dir}")
    
    def process(self):
        """Process the raw data and save it."""
        print("Processing data...")
        
        # Load raw data
        features = np.load(os.path.join(self.raw_dir, 'features.npy'))
        targets = np.load(os.path.join(self.raw_dir, 'targets.npy'))
        edge_index = torch.load(os.path.join(self.raw_dir, 'edge_index.pt'))
        
        # Create data list
        data_list = []
        num_samples = len(features) - self.seq_len - self.pred_len + 1
        
        # Limit number of samples for testing
        num_samples = min(100, num_samples)
        
        for i in range(num_samples):
            # Get sequence and target windows
            x = torch.FloatTensor(features[i:i+self.seq_len])
            y = torch.FloatTensor(targets[i+self.seq_len:i+self.seq_len+self.pred_len])
            
            # Create Data object
            data = Data(
                x=x.view(-1, x.size(-1)),  # Flatten time and node dimensions
                edge_index=edge_index,
                y=y.view(-1, y.size(-1)),  # Flatten time and node dimensions
                num_nodes=4,
                seq_len=self.seq_len,
                pred_len=self.pred_len
            )
            
            if self.pre_filter is not None and not self.pre_filter(data):
                continue
                
            if self.pre_transform is not None:
                data = self.pre_transform(data)
                
            data_list.append(data)
        
        # Save processed data
        data, slices = self.collate(data_list)
        torch.save((data, slices), self.processed_paths[0])
        print(f"Processed data saved to {self.processed_paths[0]}")
    
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({len(self)})'
