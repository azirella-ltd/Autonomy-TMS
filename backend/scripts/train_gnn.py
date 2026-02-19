#!/usr/bin/env python3
"""
Script to train the TemporalGNN model on synthetic supply chain data.
"""
import os
import sys
import torch
import logging
from pathlib import Path

# Add the project root to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from app.models.gnn.temporal_gnn import SupplyChainTemporalGNN, create_supply_chain_agents
from app.train_tgnn_clean import train_agents
from app.core.logging_config import setup_logging

# Set up logging
setup_logging()
logger = logging.getLogger(__name__)

def main():
    # Configuration
    config_identifier = os.getenv('SC_CONFIG_IDENTIFIER', 'default-tbg')

    config = {
        'data_path': 'data/synthetic_games_20250903_211141.json',  # Path to synthetic data
        'num_episodes': 100,      # Number of episodes to use for training
        'batch_size': 32,         # Batch size for training
        'seq_len': 10,            # Sequence length for the temporal model
        'num_epochs': 50,         # Number of training epochs
        'learning_rate': 0.001,    # Learning rate
        'save_dir': 'models/tgnn', # Directory to save trained models
        'device': 'cuda' if torch.cuda.is_available() else 'cpu',  # Use GPU if available
        'config_identifier': config_identifier,
    }
    
    # Create save directory if it doesn't exist
    os.makedirs(config['save_dir'], exist_ok=True)
    
    logger.info("Starting GNN training with configuration:")
    for key, value in config.items():
        logger.info(f"  {key}: {value}")
    
    # Run training
    try:
        train_agents(
            data_path=config['data_path'],
            num_episodes=config['num_episodes'],
            batch_size=config['batch_size'],
            seq_len=config['seq_len'],
            num_epochs=config['num_epochs'],
            learning_rate=config['learning_rate'],
            save_dir=config['save_dir'],
            device=config['device'],
            config_identifier=config['config_identifier'],
        )
        logger.info("GNN training completed successfully!")
    except Exception as e:
        logger.error(f"Error during GNN training: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
