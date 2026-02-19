#!/usr/bin/env python3
"""
End-to-End SiteAgent Training and Testing with Food Dist

Complete pipeline that:
1. Generates Food Dist supply chain configuration (if needed)
2. Generates training data from the configuration
3. Trains the SiteAgent model (behavioral cloning + supervised)
4. Runs the full test suite with TRM enabled

Usage:
    python scripts/train_and_test_food_dist.py [options]

Options:
    --epochs N          Training epochs (default: 50)
    --samples N         Training samples to generate (default: 5000)
    --skip-generate     Skip config generation (assume exists)
    --skip-training     Skip training (use existing checkpoint)
    --checkpoint PATH   Use specific checkpoint file
    --device DEVICE     Training device: cpu or cuda (default: cpu)

Examples:
    # Full pipeline
    python scripts/train_and_test_food_dist.py

    # Quick test with fewer epochs
    python scripts/train_and_test_food_dist.py --epochs 10 --samples 1000

    # Skip to testing with existing checkpoint
    python scripts/train_and_test_food_dist.py --skip-training --checkpoint checkpoints/site_agent_DC001.pt
"""

import sys
import os
import asyncio
import argparse
import time
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def print_header(title: str):
    """Print a section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_step(step: int, total: int, description: str):
    """Print a step indicator."""
    print(f"\n[Step {step}/{total}] {description}")
    print("-" * 50)


async def step1_generate_config(db, skip: bool = False):
    """Step 1: Generate Food Dist configuration."""
    from app.models.supply_chain_config import SupplyChainConfig
    from app.models.group import Group

    # Check if config exists
    existing = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.name.ilike("%Food Dist%")
    ).first()

    if existing:
        print(f"  Found existing config: {existing.name} (ID: {existing.id})")
        if skip:
            print("  Skipping generation (--skip-generate)")
            return existing

        # Check for associated group
        group = db.query(Group).filter(Group.name.ilike("%Food Dist%")).first()
        if group:
            print(f"  Found group: {group.name} (ID: {group.id})")

        return existing

    if skip:
        print("  ERROR: No Food Dist config found and --skip-generate specified")
        return None

    print("  Generating Food Dist configuration...")
    from app.db.session import async_session_factory
    from app.services.food_dist_config_generator import generate_food_dist_config

    async with async_session_factory() as async_db:
        result = await generate_food_dist_config(async_db)

    # Refresh sync session to see the newly created config
    db.expire_all()
    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.name.ilike("%Food Dist%")
    ).first()

    if config:
        print(f"  Created config: {config.name} (ID: {config.id})")
    else:
        print("  WARNING: Config generation completed but not found in sync session")

    return config


def step2_generate_training_data(config, site_key: str, num_samples: int):
    """Step 2: Generate training data."""
    print(f"  Generating {num_samples} training samples for site {site_key}...")

    # Generate synthetic training data
    # This creates realistic supply chain scenarios
    data_generator = SyntheticTrainingDataGenerator(
        config_id=config.id,
        site_key=site_key,
    )

    dataset = data_generator.generate(num_samples=num_samples)

    print(f"  Generated {len(dataset)} training samples")
    print(f"  - ATP scenarios: {dataset.atp_count}")
    print(f"  - Inventory scenarios: {dataset.inventory_count}")
    print(f"  - PO timing scenarios: {dataset.po_count}")

    return dataset


class SyntheticTrainingDataGenerator:
    """Generates synthetic training data for SiteAgent."""

    def __init__(self, config_id: int, site_key: str):
        self.config_id = config_id
        self.site_key = site_key

    def generate(self, num_samples: int):
        """Generate training dataset."""
        import torch
        import numpy as np
        from datetime import date, timedelta

        samples = {
            'atp': [],
            'inventory': [],
            'po_timing': [],
        }

        np.random.seed(42)

        for i in range(num_samples):
            # Generate varied scenarios
            scenario_type = np.random.choice(['normal', 'shortage', 'excess', 'volatile'])

            if scenario_type == 'normal':
                inventory = np.random.randint(80, 120)
                demand = np.random.randint(90, 110)
                backlog = 0
            elif scenario_type == 'shortage':
                inventory = np.random.randint(20, 50)
                demand = np.random.randint(100, 150)
                backlog = np.random.randint(10, 50)
            elif scenario_type == 'excess':
                inventory = np.random.randint(150, 250)
                demand = np.random.randint(50, 80)
                backlog = 0
            else:  # volatile
                inventory = np.random.randint(30, 200)
                demand = np.random.randint(50, 200)
                backlog = np.random.randint(0, 30)

            pipeline = np.random.randint(20, 80)

            # ATP scenario
            samples['atp'].append({
                'inventory': inventory,
                'pipeline': pipeline,
                'backlog': backlog,
                'demand': demand,
                'requested_qty': np.random.randint(30, 100),
                'priority': np.random.randint(1, 6),
                # Labels (what a good planner would do)
                'should_fulfill': 1 if inventory + pipeline > demand else 0,
                'action': np.random.choice([0, 1, 2, 3]),  # fulfill, partial, defer, escalate
            })

            # Inventory scenario
            samples['inventory'].append({
                'inventory': inventory,
                'pipeline': pipeline,
                'backlog': backlog,
                'demand_history': [demand + np.random.randint(-20, 20) for _ in range(12)],
                'forecast': [demand + np.random.randint(-10, 10) for _ in range(8)],
                # Labels
                'optimal_ss_multiplier': 1.0 + (0.1 if scenario_type == 'volatile' else 0.0),
                'optimal_rop_multiplier': 1.0 + (0.05 if backlog > 0 else 0.0),
            })

            # PO timing scenario
            samples['po_timing'].append({
                'inventory': inventory,
                'pipeline': pipeline,
                'backlog': backlog,
                'forecast_demand': demand,
                'supplier_reliability': np.random.uniform(0.8, 1.0),
                'lead_time_variability': np.random.uniform(0.1, 0.3),
                # Labels
                'optimal_days_offset': -2 if backlog > 20 else (2 if inventory > 150 else 0),
                'should_expedite': 1 if backlog > 30 or inventory < 30 else 0,
            })

        return TrainingDataset(samples)


class TrainingDataset:
    """Container for training data."""

    def __init__(self, samples: dict):
        self.samples = samples
        self.atp_count = len(samples['atp'])
        self.inventory_count = len(samples['inventory'])
        self.po_count = len(samples['po_timing'])

    def __len__(self):
        return self.atp_count + self.inventory_count + self.po_count

    def to_tensors(self):
        """Convert to PyTorch tensors for training."""
        import torch
        import numpy as np

        # ATP data
        atp_features = []
        atp_labels = []
        for s in self.samples['atp']:
            atp_features.append([
                s['inventory'] / 100,
                s['pipeline'] / 100,
                s['backlog'] / 100,
                s['demand'] / 100,
                s['requested_qty'] / 100,
                s['priority'] / 5,
            ])
            atp_labels.append(s['action'])

        # Inventory data
        inv_features = []
        inv_labels = []
        for s in self.samples['inventory']:
            features = [
                s['inventory'] / 100,
                s['pipeline'] / 100,
                s['backlog'] / 100,
            ]
            features.extend([d / 100 for d in s['demand_history'][:12]])
            features.extend([f / 100 for f in s['forecast'][:8]])
            inv_features.append(features)
            inv_labels.append([s['optimal_ss_multiplier'], s['optimal_rop_multiplier']])

        # PO timing data
        po_features = []
        po_labels = []
        for s in self.samples['po_timing']:
            po_features.append([
                s['inventory'] / 100,
                s['pipeline'] / 100,
                s['backlog'] / 100,
                s['forecast_demand'] / 100,
                s['supplier_reliability'],
                s['lead_time_variability'],
            ])
            po_labels.append([s['optimal_days_offset'] / 7, s['should_expedite']])

        return {
            'atp': (torch.tensor(atp_features, dtype=torch.float32),
                    torch.tensor(atp_labels, dtype=torch.long)),
            'inventory': (torch.tensor(inv_features, dtype=torch.float32),
                          torch.tensor(inv_labels, dtype=torch.float32)),
            'po_timing': (torch.tensor(po_features, dtype=torch.float32),
                          torch.tensor(po_labels, dtype=torch.float32)),
        }


def step3_train_model(dataset, site_key: str, epochs: int, device: str, checkpoint_dir: str):
    """Step 3: Train the SiteAgent model."""
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset

    print(f"  Training SiteAgent model...")
    print(f"  - Epochs: {epochs}")
    print(f"  - Device: {device}")

    from app.services.powell.site_agent_model import (
        SiteAgentModel,
        SiteAgentModelConfig,
    )

    # Create model
    # state_dim = inventory(1) + pipeline(4) + backlog(1) + demand_history(12) + forecasts(8) = 26
    config = SiteAgentModelConfig(
        state_dim=26,
        embedding_dim=128,
        encoder_heads=4,
        encoder_layers=2,
    )
    model = SiteAgentModel(config)
    model = model.to(device)

    print(f"  - Model parameters: {model.get_parameter_count()['total']:,}")

    # Convert dataset to tensors
    tensors = dataset.to_tensors()

    # Training loop
    optimizer = optim.AdamW(model.parameters(), lr=1e-4, weight_decay=0.01)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    # Loss functions
    ce_loss = nn.CrossEntropyLoss()
    mse_loss = nn.MSELoss()

    best_loss = float('inf')
    start_time = time.time()

    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0

        # Train on ATP data
        atp_features, atp_labels = tensors['atp']
        atp_features = atp_features.to(device)
        atp_labels = atp_labels.to(device)

        # Create mock state from features
        batch_size = len(atp_features)
        n_products = 1

        inventory = atp_features[:, 0:1]
        pipeline = atp_features[:, 1:2].unsqueeze(-1).expand(-1, -1, 4)
        backlog = atp_features[:, 2:3]
        demand_history = atp_features[:, 3:4].unsqueeze(-1).expand(-1, -1, 12)
        forecasts = atp_features[:, 4:5].unsqueeze(-1).expand(-1, -1, 8)

        state = model.encode_state(inventory, pipeline, backlog, demand_history, forecasts)

        # ATP head forward
        order_context = atp_features[:, :6]
        # Pad to 16 dims
        order_context = torch.nn.functional.pad(order_context, (0, 10))
        shortage = (atp_features[:, 4:5] - atp_features[:, 0:1]).clamp(min=0)

        atp_output = model.forward_atp_exception(state, order_context, shortage)
        atp_loss = ce_loss(atp_output['action_probs'], atp_labels)
        epoch_loss += atp_loss.item()

        # Train on inventory data
        inv_features, inv_labels = tensors['inventory']
        inv_features = inv_features.to(device)
        inv_labels = inv_labels.to(device)

        # Create state from inventory features
        batch_size = len(inv_features)
        inventory = inv_features[:, 0:1]
        pipeline = inv_features[:, 1:2].unsqueeze(-1).expand(-1, -1, 4)
        backlog = inv_features[:, 2:3]
        demand_history = inv_features[:, 3:15].unsqueeze(1)
        forecasts = inv_features[:, 15:23].unsqueeze(1)

        state = model.encode_state(inventory, pipeline, backlog, demand_history, forecasts)

        inv_output = model.forward_inventory_planning(state)
        inv_pred = torch.cat([inv_output['ss_multiplier'], inv_output['rop_multiplier']], dim=1)
        inv_loss = mse_loss(inv_pred, inv_labels)
        epoch_loss += inv_loss.item()

        # Train on PO timing data
        po_features, po_labels = tensors['po_timing']
        po_features = po_features.to(device)
        po_labels = po_labels.to(device)

        batch_size = len(po_features)
        inventory = po_features[:, 0:1]
        pipeline = po_features[:, 1:2].unsqueeze(-1).expand(-1, -1, 4)
        backlog = po_features[:, 2:3]
        demand_history = po_features[:, 3:4].unsqueeze(-1).expand(-1, -1, 12)
        forecasts = po_features[:, 3:4].unsqueeze(-1).expand(-1, -1, 8)

        state = model.encode_state(inventory, pipeline, backlog, demand_history, forecasts)

        po_context = po_features
        # Pad to 12 dims
        po_context = torch.nn.functional.pad(po_context, (0, 6))

        po_output = model.forward_po_timing(state, po_context)
        po_pred = torch.cat([po_output['days_offset'] / 7, po_output['expedite_prob']], dim=1)
        po_loss = mse_loss(po_pred, po_labels)
        epoch_loss += po_loss.item()

        # Backward pass
        total_loss = atp_loss + inv_loss + po_loss
        optimizer.zero_grad()
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        scheduler.step()

        # Progress
        if (epoch + 1) % 10 == 0 or epoch == 0:
            elapsed = time.time() - start_time
            print(f"    Epoch {epoch + 1}/{epochs}: loss={epoch_loss:.4f} "
                  f"(atp={atp_loss.item():.4f}, inv={inv_loss.item():.4f}, po={po_loss.item():.4f}) "
                  f"[{elapsed:.1f}s]")

        # Save best model
        if epoch_loss < best_loss:
            best_loss = epoch_loss

    # Save checkpoint
    checkpoint_path = Path(checkpoint_dir) / f"site_agent_{site_key}.pt"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    torch.save({
        'model_state_dict': model.state_dict(),
        'model_config': config,
        'epoch': epochs,
        'loss': best_loss,
        'site_key': site_key,
        'timestamp': datetime.now().isoformat(),
    }, checkpoint_path)

    print(f"\n  Model saved to: {checkpoint_path}")
    print(f"  Final loss: {best_loss:.4f}")

    return str(checkpoint_path)


async def step4_run_tests(config, site_key: str, checkpoint_path: str, db):
    """Step 4: Run the full test suite."""
    print(f"  Running test suite with TRM enabled...")
    print(f"  - Checkpoint: {checkpoint_path}")

    from app.services.powell.site_agent import SiteAgent, SiteAgentConfig

    # Create SiteAgent with checkpoint
    agent_config = SiteAgentConfig(
        site_key=site_key,
        use_trm_adjustments=True,
        agent_mode="copilot",
        model_checkpoint_path=checkpoint_path,
    )

    site_agent = SiteAgent(agent_config)

    print(f"\n  SiteAgent status:")
    print(f"    Model loaded: {site_agent.model is not None}")
    if site_agent.model:
        print(f"    Parameters: {site_agent.model.get_parameter_count()['total']:,}")

    # Import test functions from the test script
    from scripts.test_site_agent_food_dist import (
        test_mrp_engine,
        test_aatp_engine,
        test_safety_stock_calculator,
        test_atp_execution,
        test_cdc_monitor,
        test_inventory_adjustments,
        test_agent_strategy_integration,
    )

    results = {}

    # Deterministic tests
    print("\n  Running deterministic engine tests...")
    results["MRP Engine"] = test_mrp_engine(site_agent, config, db)
    results["AATP Engine"] = test_aatp_engine(site_agent, config, db)
    results["Safety Stock"] = test_safety_stock_calculator(site_agent, config, db)

    # Async tests with TRM
    print("\n  Running TRM-enabled tests...")
    results["ATP Execution (TRM)"] = await test_atp_execution(site_agent, config, db)
    results["CDC Monitor"] = await test_cdc_monitor(site_agent, config, db)
    results["Inventory Adjustments (TRM)"] = await test_inventory_adjustments(site_agent, config, db)

    # Integration test
    print("\n  Running integration tests...")
    results["Agent Strategy"] = test_agent_strategy_integration(site_agent, config, db)

    return results


async def main():
    parser = argparse.ArgumentParser(description="End-to-end SiteAgent training and testing")
    parser.add_argument("--epochs", type=int, default=50, help="Training epochs")
    parser.add_argument("--samples", type=int, default=5000, help="Training samples")
    parser.add_argument("--skip-generate", action="store_true", help="Skip config generation")
    parser.add_argument("--skip-training", action="store_true", help="Skip training")
    parser.add_argument("--checkpoint", type=str, help="Use existing checkpoint")
    parser.add_argument("--device", type=str, default="cpu", choices=["cpu", "cuda"], help="Training device")
    parser.add_argument("--checkpoint-dir", type=str, default="checkpoints", help="Checkpoint directory")
    args = parser.parse_args()

    print_header("SiteAgent End-to-End Training & Testing Pipeline")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Configuration:")
    print(f"    - Epochs: {args.epochs}")
    print(f"    - Samples: {args.samples}")
    print(f"    - Device: {args.device}")
    print(f"    - Skip generate: {args.skip_generate}")
    print(f"    - Skip training: {args.skip_training}")

    start_time = time.time()

    from app.db.session import sync_session_factory

    # Use sync session for this script
    db = sync_session_factory()
    try:
        # Step 1: Generate/Find Config
        print_step(1, 4, "Generate Food Dist Configuration")
        config = await step1_generate_config(db, skip=args.skip_generate)
        if not config:
            print("  FAILED: Could not find or create Food Dist configuration")
            return 1

        site_key = "DC001"

        # Step 2: Generate Training Data
        if not args.skip_training:
            print_step(2, 4, "Generate Training Data")
            dataset = step2_generate_training_data(config, site_key, args.samples)
        else:
            print_step(2, 4, "Generate Training Data (SKIPPED)")
            dataset = None

        # Step 3: Train Model
        if not args.skip_training:
            print_step(3, 4, "Train SiteAgent Model")
            checkpoint_path = step3_train_model(
                dataset, site_key, args.epochs, args.device, args.checkpoint_dir
            )
        else:
            print_step(3, 4, "Train SiteAgent Model (SKIPPED)")
            checkpoint_path = args.checkpoint
            if not checkpoint_path:
                # Try default path
                checkpoint_path = f"{args.checkpoint_dir}/site_agent_{site_key}.pt"
                if not Path(checkpoint_path).exists():
                    print(f"  WARNING: No checkpoint found at {checkpoint_path}")
                    checkpoint_path = None

        # Step 4: Run Tests
        print_step(4, 4, "Run Test Suite")
        results = await step4_run_tests(config, site_key, checkpoint_path, db)

        # Summary
        print_header("Pipeline Summary")

        elapsed = time.time() - start_time
        print(f"  Total time: {elapsed:.1f} seconds")
        print(f"  Checkpoint: {checkpoint_path}")

        print(f"\n  Test Results:")
        passed = sum(1 for r in results.values() if r)
        total = len(results)

        for test_name, test_passed in results.items():
            status = "PASS" if test_passed else "FAIL"
            print(f"    [{status}] {test_name}")

        print(f"\n  Overall: {passed}/{total} tests passed")

        if passed == total:
            print("\n  SUCCESS: All tests passed!")
            return 0
        else:
            print("\n  WARNING: Some tests failed")
            return 1

    finally:
        db.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
