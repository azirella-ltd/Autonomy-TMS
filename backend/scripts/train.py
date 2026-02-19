#!/usr/bin/env python3
"""
Main training script for the Supply Chain GNN model.

This script provides a complete training pipeline for the Supply Chain GNN model,
with support for different environments (local, development, production) and
configuration management.
"""

import os
import sys
import argparse
import json
from pathlib import Path
from datetime import datetime
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter
import numpy as np
from tqdm import tqdm

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from app.models.gnn.simple_temporal_gnn import SimpleTemporalGNN
from app.data.basic_dataset import BasicSupplyChainDataset
from scripts.training.config import get_config
import logging
import argparse
from pathlib import Path

# Add project root to Python path
project_root = str(Path(__file__).parent.parent.absolute())
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import torch
import numpy as np
from torch.utils.data import DataLoader, random_split

# Import training framework
from scripts.training import Trainer, setup_logging, load_config, get_device

# Import your data loading and model code
from app.data.supply_chain_dataset import SupplyChainDataset  # Update this import based on your actual data module
from app.models.gnn.temporal_gnn import SupplyChainTemporalGNN

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Train Supply Chain GNN Model')
    parser.add_argument('--env', type=str, default='local',
                      help='Environment to run in (local, dev, prod)')
    parser.add_argument('--config', type=str, default=None,
                      help='Path to custom config file')
    parser.add_argument('--batch_size', type=int, default=None,
                      help='Batch size for training')
    parser.add_argument('--num_epochs', type=int, default=None,
                      help='Number of training epochs')
    parser.add_argument('--learning_rate', type=float, default=None,
                      help='Learning rate')
    parser.add_argument('--device', type=str, default=None,
                      help='Device to use (cpu, cuda, mps)')
    parser.add_argument('--log_dir', type=str, default=None,
                      help='Directory to save logs and checkpoints')
    return parser.parse_args()

def setup_environment(config):
    """Set up the training environment."""
    # Set random seeds for reproducibility
    torch.manual_seed(config.hardware.seed)
    np.random.seed(config.hardware.seed)
    
    # Set device
    if config.hardware.device == 'auto':
        device = torch.device('cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu')
    else:
        device = torch.device(config.hardware.device)
    
    # Create directories
    os.makedirs(config.logging.checkpoint_dir, exist_ok=True)
    os.makedirs(config.logging.log_dir, exist_ok=True)
    
    # Save config
    config_path = os.path.join(config.logging.log_dir, 'config.json')
    with open(config_path, 'w') as f:
        json.dump(vars(config), f, indent=2)
    
    return device

def load_data(config):
    """Load and prepare the dataset."""
    # Create dataset
    dataset = BasicSupplyChainDataset()
    
    # Split dataset
    dataset_size = len(dataset)
    train_size = int(config.dataset.train_ratio * dataset_size)
    val_size = int(config.dataset.val_ratio * dataset_size)
    test_size = dataset_size - train_size - val_size
    
    train_dataset, val_dataset, test_dataset = torch.utils.data.random_split(
        dataset, [train_size, val_size, test_size],
        generator=torch.Generator().manual_seed(config.hardware.seed)
    )
    
    # Create data loaders
    train_loader = DataLoader(
        train_dataset,
        batch_size=config.training.batch_size,
        shuffle=True,
        num_workers=config.hardware.num_workers,
        pin_memory=config.hardware.pin_memory
    )
    
    val_loader = DataLoader(
        val_dataset,
        batch_size=config.training.batch_size,
        shuffle=False,
        num_workers=config.hardware.num_workers,
        pin_memory=config.hardware.pin_memory
    )
    
    test_loader = DataLoader(
        test_dataset,
        batch_size=config.training.batch_size,
        shuffle=False,
        num_workers=config.hardware.num_workers,
        pin_memory=config.hardware.pin_memory
    )
    
    return train_loader, val_loader, test_loader

def create_model(config, device):
    """Create and initialize the model."""
    model = SimpleTemporalGNN(
        node_features=config.model.node_features,
        hidden_dim=config.model.hidden_dim,
        num_layers=config.model.num_layers,
        seq_len=config.dataset.seq_len,
        num_nodes=config.dataset.num_nodes,
        pred_len=config.dataset.pred_len,
        dropout=config.model.dropout
    ).to(device)
    
    # Initialize weights
    def init_weights(m):
        if isinstance(m, nn.Linear):
            nn.init.xavier_uniform_(m.weight)
            if m.bias is not None:
                nn.init.constant_(m.bias, 0)
    
    model.apply(init_weights)
    return model

def train_epoch(model, dataloader, criterion, optimizer, device):
    """Train the model for one epoch."""
    model.train()
    total_loss = 0.0
    
    for batch in tqdm(dataloader, desc="Training"):
        # Move data to device
        x = batch['x'].to(device)
        y = batch['y'].to(device)
        
        # Create edge_index for a fully connected graph
        num_nodes = x.size(2)
        edge_index = []
        for i in range(num_nodes):
            for j in range(num_nodes):
                if i != j:  # No self-loops
                    edge_index.append([i, j])
        edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous().to(device)
        
        # Forward pass
        optimizer.zero_grad()
        output = model(x, edge_index)
        
        # Calculate loss
        loss = criterion(output['order_quantity'], y[..., 0].unsqueeze(-1)) + \
               criterion(output['demand_forecast'], y[..., 1].unsqueeze(-1))
        
        # Backward pass and optimize
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        
        total_loss += loss.item() * x.size(0)
    
    return total_loss / len(dataloader.dataset)

def evaluate(model, dataloader, criterion, device):
    """Evaluate the model on the given dataset."""
    model.eval()
    total_loss = 0.0
    
    with torch.no_grad():
        for batch in tqdm(dataloader, desc="Evaluating"):
            x = batch['x'].to(device)
            y = batch['y'].to(device)
            
            # Create edge_index for a fully connected graph
            num_nodes = x.size(2)
            edge_index = []
            for i in range(num_nodes):
                for j in range(num_nodes):
                    if i != j:  # No self-loops
                        edge_index.append([i, j])
            edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous().to(device)
            
            # Forward pass
            output = model(x, edge_index)
            
            # Calculate loss
            loss = criterion(output['order_quantity'], y[..., 0].unsqueeze(-1)) + \
                   criterion(output['demand_forecast'], y[..., 1].unsqueeze(-1))
            
            total_loss += loss.item() * x.size(0)
    
    return total_loss / len(dataloader.dataset)

def main():
    """Main training function."""
    # Parse command line arguments
    args = parse_args()
    
    # Load configuration
    config = get_config(args.env)
    
    # Override config with command line arguments
    if args.batch_size is not None:
        config.training.batch_size = args.batch_size
    if args.num_epochs is not None:
        config.training.num_epochs = args.num_epochs
    if args.learning_rate is not None:
        config.training.learning_rate = args.learning_rate
    if args.device is not None:
        config.hardware.device = args.device
    if args.log_dir is not None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        config.logging.log_dir = os.path.join(args.log_dir, f'run_{timestamp}')
        config.logging.checkpoint_dir = os.path.join(config.logging.log_dir, 'checkpoints')
        config['output_dir'] = args.output_dir
    if args.device:
        config['device'] = args.device
    if args.debug:
        config['debug'] = True
    
    # Set up environment
    logger = setup_environment(config)
    
    # Set device
    device = get_device()
    
    try:
        # Load data
        logger.info("Loading data...")
        train_loader, val_loader, test_loader = load_data(config)
        
        # Create model
        logger.info("Creating model...")
        model = create_model(config, device)
        
        # Initialize trainer
        trainer = Trainer(
            model=model,
            train_loader=train_loader,
            val_loader=val_loader,
            test_loader=test_loader,
            config=config,
            device=device
        )
        
        # Resume training if checkpoint is provided
        if args.resume:
            logger.info(f"Resuming training from checkpoint: {args.resume}")
            trainer.load_checkpoint(args.resume)
        
        # Train the model
        logger.info("Starting training...")
        trainer.train()
        
        # Test the model
        logger.info("Testing model...")
        test_metrics = trainer.evaluate(test_loader)
        logger.info(f"Test metrics: {test_metrics}")
        
        # Save final model
        trainer.save_checkpoint(os.path.join(args.output_dir, 'final_model.pth'))
        logger.info("Training completed successfully!")
        
    except KeyboardInterrupt:
        logger.info("Training interrupted by user")
    except Exception as e:
        logger.exception(f"Training failed: {e}")
        raise

if __name__ == "__main__":
    main()
