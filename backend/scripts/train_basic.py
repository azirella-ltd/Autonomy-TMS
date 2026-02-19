#!/usr/bin/env python3
"""
Basic training script for the supply chain GNN model.
"""

import os
import sys
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from tqdm import tqdm
import numpy as np

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from app.data.basic_dataset import BasicSupplyChainDataset
from app.models.gnn.simple_temporal_gnn import SimpleTemporalGNN

def train_epoch(model, dataloader, criterion, optimizer, device):
    """Train the model for one epoch."""
    model.train()
    total_loss = 0.0
    
    for batch in tqdm(dataloader, desc="Training"):
        # Move data to device
        x = batch['x'].to(device)  # [batch_size, seq_len, num_nodes, num_features]
        y = batch['y'].to(device)  # [batch_size, pred_len, num_nodes, 2]
        edge_index = batch['edge_index'].to(device)  # [2, num_edges]
        
        # Create edge_index for a fully connected graph
        num_nodes = x.size(2)
        edge_index = []
        for i in range(num_nodes):
            for j in range(num_nodes):
                if i != j:  # No self-loops
                    edge_index.append([i, j])
        edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous().to(device)
        
        # Reshape for the model
        batch_size, seq_len, num_nodes, num_features = x.shape
        
        # The model expects [batch_size, seq_len, num_nodes, num_features]
        # No need to reshape further as the model handles the rest
        
        # Forward pass
        optimizer.zero_grad()
        output = model(x, edge_index)  # Returns dict with 'order_quantity' and 'demand_forecast'
        
        # Extract predictions
        order_pred = output['order_quantity']  # [batch_size, num_nodes, 1]
        demand_pred = output['demand_forecast']  # [batch_size, num_nodes, 1]
        
        # Stack predictions to match target shape [batch_size, pred_len, num_nodes, 2]
        pred = torch.stack([order_pred.squeeze(-1), demand_pred.squeeze(-1)], dim=-1)  # [batch_size, num_nodes, 2]
        pred = pred.unsqueeze(1)  # [batch_size, 1, num_nodes, 2]
        pred = pred.expand(-1, y.size(1), -1, -1)  # [batch_size, pred_len, num_nodes, 2]
        
        # Calculate loss
        loss = criterion(pred, y)
        
        # Backward pass and optimize
        loss.backward()
        optimizer.step()
        
        total_loss += loss.item()
    
    return total_loss / len(dataloader)

def evaluate(model, dataloader, criterion, device):
    """Evaluate the model on the given dataset."""
    model.eval()
    total_loss = 0.0
    
    with torch.no_grad():
        for batch in tqdm(dataloader, desc="Evaluating"):
            # Move data to device
            x = batch['x'].to(device)
            y = batch['y'].to(device)
            edge_index = batch['edge_index'].to(device)
            
            # Create edge_index for a fully connected graph
            num_nodes = x.size(2)
            edge_index = []
            for i in range(num_nodes):
                for j in range(num_nodes):
                    if i != j:  # No self-loops
                        edge_index.append([i, j])
            edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous().to(device)
            
            # The model expects [batch_size, seq_len, num_nodes, num_features]
            batch_size, seq_len, num_nodes, num_features = x.shape
            
            # Forward pass
            output = model(x, edge_index)  # Returns dict with 'order_quantity' and 'demand_forecast'
            
            # Extract predictions
            order_pred = output['order_quantity']  # [batch_size, num_nodes, 1]
            demand_pred = output['demand_forecast']  # [batch_size, num_nodes, 1]
            
            # Stack predictions to match target shape [batch_size, pred_len, num_nodes, 2]
            pred = torch.stack([order_pred.squeeze(-1), demand_pred.squeeze(-1)], dim=-1)  # [batch_size, num_nodes, 2]
            pred = pred.unsqueeze(1)  # [batch_size, 1, num_nodes, 2]
            pred = pred.expand(-1, y.size(1), -1, -1)  # [batch_size, pred_len, num_nodes, 2]
            
            # Calculate loss
            loss = criterion(pred, y)
            total_loss += loss.item()
    
    return total_loss / len(dataloader)

def main():
    # Set random seed for reproducibility
    torch.manual_seed(42)
    np.random.seed(42)
    
    # Device configuration
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    
    # Hyperparameters
    seq_len = 10
    pred_len = 1
    batch_size = 8
    num_epochs = 10
    learning_rate = 0.001
    
    # Create dataset and dataloader
    print("Loading dataset...")
    dataset = BasicSupplyChainDataset(seq_len=seq_len, pred_len=pred_len)
    
    # Split into train and validation sets
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=2)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=2)
    
    print(f"Train samples: {len(train_dataset)}, Validation samples: {len(val_dataset)}")
    
    # Initialize the simplified model
    model = SimpleTemporalGNN(
        node_features=10,  # Number of input features per node
        hidden_dim=32,
        num_layers=2,
        seq_len=seq_len,
        num_nodes=4,  # Number of nodes in the supply chain
        pred_len=pred_len,
        dropout=0.1
    ).to(device)
    
    # Loss and optimizer
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    
    # Training loop
    print("Starting training...")
    for epoch in range(num_epochs):
        # Train for one epoch
        train_loss = train_epoch(model, train_loader, criterion, optimizer, device)
        
        # Evaluate on validation set
        val_loss = evaluate(model, val_loader, criterion, device)
        
        print(f"Epoch [{epoch+1}/{num_epochs}], "
              f"Train Loss: {train_loss:.6f}, Val Loss: {val_loss:.6f}")
    
    print("Training complete!")
    
    # Save the model
    os.makedirs("checkpoints", exist_ok=True)
    model_path = "checkpoints/supply_chain_gnn.pth"
    torch.save({
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'epoch': num_epochs,
        'train_loss': train_loss,
        'val_loss': val_loss,
    }, model_path)
    print(f"Model saved to {model_path}")

if __name__ == "__main__":
    main()
