#!/usr/bin/env python3
"""
Train SiteAgent Model

Multi-phase training for the unified SiteAgent architecture:
1. Behavioral Cloning (warmup from expert decisions)
2. Multi-task Supervised (joint encoder + heads)
3. RL Fine-tuning (optional)

Usage:
    python scripts/training/train_site_agent.py --site-key SITE001 --epochs 50
    python scripts/training/train_site_agent.py --config configs/site_agent_training.yaml

Environment Variables:
    CUDA_VISIBLE_DEVICES: GPU selection
    SITE_AGENT_DATA_PATH: Path to training data
"""

import argparse
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import torch
import json
import yaml

from app.services.powell.site_agent_model import SiteAgentModel, SiteAgentModelConfig
from app.services.powell.site_agent_trainer import (
    SiteAgentTrainer,
    TrainingConfig,
    TrainingPhase,
    SiteAgentDataset,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description='Train SiteAgent Model')

    # Data
    parser.add_argument('--site-key', type=str, default='DEFAULT',
                        help='Site key for training')
    parser.add_argument('--train-data', type=str, default=None,
                        help='Path to training data JSON')
    parser.add_argument('--val-data', type=str, default=None,
                        help='Path to validation data JSON')

    # Training
    parser.add_argument('--epochs', type=int, default=50,
                        help='Total supervised epochs')
    parser.add_argument('--bc-epochs', type=int, default=10,
                        help='Behavioral cloning epochs')
    parser.add_argument('--batch-size', type=int, default=64,
                        help='Training batch size')
    parser.add_argument('--lr', type=float, default=1e-4,
                        help='Learning rate for supervised training')
    parser.add_argument('--bc-lr', type=float, default=1e-3,
                        help='Learning rate for behavioral cloning')

    # Model
    parser.add_argument('--embedding-dim', type=int, default=128,
                        help='Embedding dimension')
    parser.add_argument('--encoder-layers', type=int, default=2,
                        help='Number of transformer layers in encoder')
    parser.add_argument('--dropout', type=float, default=0.1,
                        help='Dropout rate')

    # Task weights
    parser.add_argument('--atp-weight', type=float, default=1.0,
                        help='Weight for ATP task')
    parser.add_argument('--inv-weight', type=float, default=1.0,
                        help='Weight for inventory task')
    parser.add_argument('--po-weight', type=float, default=1.0,
                        help='Weight for PO timing task')

    # Output
    parser.add_argument('--checkpoint-dir', type=str,
                        default='checkpoints/site_agent',
                        help='Directory for checkpoints')
    parser.add_argument('--save-every', type=int, default=10,
                        help='Save checkpoint every N epochs')

    # Hardware
    parser.add_argument('--device', type=str, default=None,
                        help='Device (cuda/cpu, auto-detect if not specified)')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed')

    # Phases
    parser.add_argument('--skip-bc', action='store_true',
                        help='Skip behavioral cloning phase')
    parser.add_argument('--skip-supervised', action='store_true',
                        help='Skip supervised training phase')
    parser.add_argument('--include-rl', action='store_true',
                        help='Include RL fine-tuning phase')

    # Resume
    parser.add_argument('--resume', type=str, default=None,
                        help='Resume from checkpoint path')

    # Config file (overrides other args)
    parser.add_argument('--config', type=str, default=None,
                        help='YAML config file')

    return parser.parse_args()


def load_config(args):
    """Load config from file and merge with args"""
    if args.config and Path(args.config).exists():
        with open(args.config) as f:
            config = yaml.safe_load(f)
        # Merge with args (args take precedence)
        for key, value in config.items():
            if not hasattr(args, key) or getattr(args, key) is None:
                setattr(args, key, value)
    return args


def create_sample_data(site_key: str, num_samples: int = 1000) -> list:
    """Create sample training data for testing"""
    import random

    samples = []
    for i in range(num_samples):
        samples.append({
            'inventory': [random.uniform(0, 100) for _ in range(10)],
            'pipeline': [[random.uniform(0, 50) for _ in range(4)] for _ in range(10)],
            'backlog': [random.uniform(0, 20) for _ in range(10)],
            'demand_history': [[random.uniform(5, 15) for _ in range(12)] for _ in range(10)],
            'forecasts': [[random.uniform(5, 15) for _ in range(8)] for _ in range(10)],
            'atp_context': [random.uniform(0, 1) for _ in range(16)],
            'atp_shortage': random.uniform(0, 50),
            'atp_label': [1, 0, 0, 0] if random.random() > 0.3 else [0, 0, 0, 1],
            'inv_label': [random.uniform(0.9, 1.1), random.uniform(0.9, 1.1)],
            'po_context': [random.uniform(0, 1) for _ in range(12)],
            'po_label': [1, 0, 0] if random.random() > 0.5 else [0, 1, 0],
            'outcome_sl': random.uniform(0.85, 0.99),
            'outcome_cost': random.uniform(100, 1000),
        })

    return samples


def main():
    args = parse_args()
    args = load_config(args)

    # Setup device
    if args.device is None:
        args.device = 'cuda' if torch.cuda.is_available() else 'cpu'

    logger.info(f"Training SiteAgent for site: {args.site_key}")
    logger.info(f"Device: {args.device}")

    # Set seed
    torch.manual_seed(args.seed)
    if args.device == 'cuda':
        torch.cuda.manual_seed(args.seed)

    # Create model config
    model_config = SiteAgentModelConfig(
        embedding_dim=args.embedding_dim,
        encoder_layers=args.encoder_layers,
        dropout=args.dropout,
        device=args.device,
    )

    # Create training config
    training_config = TrainingConfig(
        device=args.device,
        seed=args.seed,
        bc_epochs=args.bc_epochs,
        bc_lr=args.bc_lr,
        supervised_epochs=args.epochs,
        supervised_lr=args.lr,
        batch_size=args.batch_size,
        task_weights={
            'atp': args.atp_weight,
            'inv': args.inv_weight,
            'po_timing': args.po_weight,
        },
        checkpoint_dir=args.checkpoint_dir,
        save_every_epochs=args.save_every,
    )

    # Create or load model
    if args.resume:
        logger.info(f"Resuming from checkpoint: {args.resume}")
        trainer, model = SiteAgentTrainer.load_checkpoint(args.resume, training_config)
    else:
        logger.info("Creating new model")
        model = SiteAgentModel(model_config)
        trainer = SiteAgentTrainer(model, training_config)

    # Log model size
    param_counts = model.get_parameter_count()
    logger.info(f"Model parameters: {param_counts}")

    # Load or create training data
    if args.train_data and Path(args.train_data).exists():
        logger.info(f"Loading training data from: {args.train_data}")
        train_dataset = SiteAgentDataset.from_file(args.train_data, model_config)
    else:
        logger.info("Creating sample training data (no data file provided)")
        train_data = create_sample_data(args.site_key, num_samples=5000)
        train_dataset = SiteAgentDataset(train_data, model_config)

    # Load or create validation data
    val_dataset = None
    if args.val_data and Path(args.val_data).exists():
        logger.info(f"Loading validation data from: {args.val_data}")
        val_dataset = SiteAgentDataset.from_file(args.val_data, model_config)
    elif not args.val_data:
        logger.info("Creating sample validation data")
        val_data = create_sample_data(args.site_key, num_samples=500)
        val_dataset = SiteAgentDataset(val_data, model_config)

    logger.info(f"Training samples: {len(train_dataset)}")
    if val_dataset:
        logger.info(f"Validation samples: {len(val_dataset)}")

    # Determine phases
    phases = []
    if not args.skip_bc:
        phases.append(TrainingPhase.BEHAVIORAL_CLONING)
    if not args.skip_supervised:
        phases.append(TrainingPhase.MULTI_TASK_SUPERVISED)
    if args.include_rl:
        phases.append(TrainingPhase.RL_FINETUNING)

    logger.info(f"Training phases: {[p.value for p in phases]}")

    # Train
    start_time = datetime.now()
    results = trainer.train(
        train_data=train_dataset,
        val_data=val_dataset,
        phases=phases,
    )
    end_time = datetime.now()

    # Log results
    logger.info(f"Training completed in {end_time - start_time}")
    logger.info(f"Results: {json.dumps(results, indent=2, default=str)}")

    # Compute final metrics
    if val_dataset:
        from torch.utils.data import DataLoader
        val_loader = DataLoader(val_dataset, batch_size=training_config.val_batch_size)
        metrics = trainer.compute_metrics(val_loader)
        logger.info(f"Final metrics: {metrics}")

    # Save final info
    checkpoint_dir = Path(args.checkpoint_dir)
    with open(checkpoint_dir / 'training_info.json', 'w') as f:
        json.dump({
            'site_key': args.site_key,
            'model_config': model_config.__dict__,
            'training_config': {
                'epochs': args.epochs,
                'bc_epochs': args.bc_epochs,
                'lr': args.lr,
                'batch_size': args.batch_size,
            },
            'results': results,
            'duration': str(end_time - start_time),
            'param_counts': param_counts,
        }, f, indent=2, default=str)

    logger.info(f"Training complete. Checkpoints saved to: {args.checkpoint_dir}")


if __name__ == '__main__':
    main()
