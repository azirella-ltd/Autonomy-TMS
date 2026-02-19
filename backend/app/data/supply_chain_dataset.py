import os
import torch
import numpy as np
from torch_geometric.data import Data, Dataset, InMemoryDataset
from typing import Optional, Callable, List, Dict, Any
import pandas as pd
from pathlib import Path

class SupplyChainDataset(InMemoryDataset):
    """A PyTorch Geometric Dataset for supply chain data.
    
    This dataset handles loading and preprocessing of supply chain data for GNN training.
    """
    
    def __init__(self, 
                 root: str = 'data/processed',
                 seq_len: int = 10,
                 pred_len: int = 1,
                 transform: Optional[Callable] = None,
                 pre_transform: Optional[Callable] = None,
                 pre_filter: Optional[Callable] = None):
        """Initialize the dataset.
        
        Args:
            root: Root directory where the dataset should be saved.
            seq_len: Length of input sequences
            pred_len: Length of prediction sequences
            transform: A function/transform that takes in a Data object and returns a transformed version.
            pre_transform: A function/transform that takes in a Data object and returns a transformed version.
            pre_filter: A function that takes in a Data object and returns a boolean value.
        """
        self.seq_len = seq_len
        self.pred_len = pred_len
        self.data_dir = Path(root)
        
        # Initialize the parent class first to set up the directory structure
        super().__init__(root, transform, pre_transform, pre_filter)
        
        # Create necessary directories
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        # Create sample data if it doesn't exist
        if not (self.raw_dir / 'features.npy').exists():
            self._create_sample_data()
        
        # Process the data if needed
        if not self.processed_paths[0].exists():
            self.process()
            
        # Load the processed data
        self.data, self.slices = torch.load(self.processed_paths[0])
    
    @property
    def raw_file_names(self):
        """Files in this folder will be found and returned by the dataloader."""
        return ['features.npy', 'targets.npy', 'edge_index.pt']
    
    @property
    def processed_file_names(self):
        """Files in this folder will be found and returned by the dataloader."""
        return ['data.pt']
    
    def _create_sample_data(self):
        """Create sample data for testing if no data is found."""
        print(f"Creating sample data in {self.raw_dir}...")
        
        # Create raw directory if it doesn't exist
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        
        num_nodes = 4  # Retailer, Wholesaler, Distributor, Manufacturer
        num_features = 10
        num_time_steps = 1000
        
        print("Generating random features and targets...")
        features = np.random.randn(num_time_steps, num_nodes, num_features).astype(np.float32)
        targets = np.random.randn(num_time_steps, num_nodes, 2).astype(np.float32)
        
        print("Generating edge indices...")
        edge_index = []
        for i in range(num_nodes):
            for j in range(num_nodes):
                if i != j:  # No self-loops
                    edge_index.append([i, j])
        edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()
        
        # Save the raw data with full paths
        features_path = self.raw_dir / 'features.npy'
        targets_path = self.raw_dir / 'targets.npy'
        edge_index_path = self.raw_dir / 'edge_index.pt'
        
        print(f"Saving features to {features_path}...")
        np.save(features_path, features)
        
        print(f"Saving targets to {targets_path}...")
        np.save(targets_path, targets)
        
        print(f"Saving edge indices to {edge_index_path}...")
        torch.save(edge_index, edge_index_path)
        
        print(f"Sample data creation complete in {self.raw_dir}")
        
        # Verify the files were created
        for path in [features_path, targets_path, edge_index_path]:
            if not path.exists():
                raise RuntimeError(f"Failed to create {path}")
            print(f"Verified: {path} exists")
    
    def process(self):
        """Process the raw data and save it."""
        # Load the raw data
        features = np.load(self.raw_paths[0])
        targets = np.load(self.raw_paths[1])
        edge_index = torch.load(self.raw_paths[2])
        
        # Calculate number of samples
        num_samples = len(features) - self.seq_len - self.pred_len + 1
        if num_samples <= 0:
            raise ValueError(
                f"Sequence length ({self.seq_len}) plus prediction length "
                f"({self.pred_len}) exceeds number of time steps ({len(features)})"
            )
        
        data_list = []
        for i in range(min(100, num_samples)):  # Limit to 100 samples for testing
            x = torch.FloatTensor(features[i:i+self.seq_len])
            y = torch.FloatTensor(targets[i+self.seq_len:i+self.seq_len+self.pred_len])
            
            data = Data(
                x=x.view(-1, x.size(-1)),
                edge_index=edge_index,
                y=y.view(-1, y.size(-1)),
                num_nodes=4,
                seq_len=self.seq_len,
                pred_len=self.pred_len
            )
            
            if self.pre_filter is not None and not self.pre_filter(data):
                continue
                
            if self.pre_transform is not None:
                data = self.pre_transform(data)
                
            data_list.append(data)
        
        # Save the processed data
        data, slices = self.collate(data_list)
        torch.save((data, slices), self.processed_paths[0])
        
    def len(self) -> int:
        """Return the number of graphs in the dataset."""
        return self.slices['x'].size(0) - 1
    
    def get(self, idx: int) -> Data:
        """Get a single data point."""
        data = super().get(idx)
        return data
    
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({len(self)})'
