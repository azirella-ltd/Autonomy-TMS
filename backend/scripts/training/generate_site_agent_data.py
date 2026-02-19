#!/usr/bin/env python3
"""
Generate Training Data for SiteAgent

Generates training data from three sources:
1. Historical decisions from database
2. Simulated episodes using SimPy
3. Synthetic data with configurable patterns

Usage:
    python scripts/training/generate_site_agent_data.py --site-key SITE001 --episodes 1000
    python scripts/training/generate_site_agent_data.py --from-db --site-key SITE001

Environment Variables:
    DATABASE_URL: Database connection string
"""

import argparse
import asyncio
import logging
import sys
import os
from pathlib import Path
from datetime import datetime, date, timedelta
import random
import json

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description='Generate SiteAgent Training Data')

    # Source selection
    parser.add_argument('--from-db', action='store_true',
                        help='Extract historical decisions from database')
    parser.add_argument('--from-simpy', action='store_true',
                        help='Generate data using SimPy simulation')
    parser.add_argument('--synthetic', action='store_true',
                        help='Generate synthetic data with patterns')

    # Common options
    parser.add_argument('--site-key', type=str, default='DEFAULT',
                        help='Site key for data generation')
    parser.add_argument('--output', type=str, default='data/site_agent_training.json',
                        help='Output file path')

    # SimPy options
    parser.add_argument('--episodes', type=int, default=1000,
                        help='Number of simulation episodes')
    parser.add_argument('--episode-length', type=int, default=100,
                        help='Steps per episode')

    # Synthetic options
    parser.add_argument('--num-samples', type=int, default=10000,
                        help='Number of synthetic samples')
    parser.add_argument('--num-products', type=int, default=10,
                        help='Number of products')
    parser.add_argument('--demand-pattern', type=str, default='seasonal',
                        choices=['constant', 'seasonal', 'trending', 'volatile'],
                        help='Demand pattern for synthetic data')

    # Database options
    parser.add_argument('--db-limit', type=int, default=50000,
                        help='Max records to extract from database')

    # Data split
    parser.add_argument('--train-ratio', type=float, default=0.8,
                        help='Ratio of training data')
    parser.add_argument('--split-output', action='store_true',
                        help='Output separate train/val files')

    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed')

    return parser.parse_args()


class SyntheticDataGenerator:
    """Generate synthetic training data with realistic patterns"""

    def __init__(
        self,
        num_products: int = 10,
        demand_pattern: str = 'seasonal',
        seed: int = 42
    ):
        self.num_products = num_products
        self.demand_pattern = demand_pattern
        self.seed = seed
        random.seed(seed)

        # Product characteristics
        self.base_demands = [random.uniform(10, 50) for _ in range(num_products)]
        self.demand_stds = [d * random.uniform(0.1, 0.3) for d in self.base_demands]
        self.lead_times = [random.randint(3, 14) for _ in range(num_products)]

    def generate_demand(self, day: int, product_idx: int) -> float:
        """Generate demand based on pattern"""
        base = self.base_demands[product_idx]
        std = self.demand_stds[product_idx]

        if self.demand_pattern == 'constant':
            return max(0, random.gauss(base, std))

        elif self.demand_pattern == 'seasonal':
            # Seasonal factor (peaks in winter/summer)
            seasonal = 1.0 + 0.3 * abs(((day % 365) - 182) / 182)
            return max(0, random.gauss(base * seasonal, std))

        elif self.demand_pattern == 'trending':
            # Gradual growth
            trend = 1.0 + 0.001 * day
            return max(0, random.gauss(base * trend, std))

        elif self.demand_pattern == 'volatile':
            # High variability with occasional spikes
            if random.random() < 0.05:  # 5% chance of spike
                spike = random.uniform(2, 4)
            else:
                spike = 1.0
            return max(0, random.gauss(base * spike, std * 2))

        return max(0, random.gauss(base, std))

    def generate_sample(self, day: int) -> dict:
        """Generate a single training sample"""

        # Current state
        inventory = [random.uniform(20, 200) for _ in range(self.num_products)]
        pipeline = [
            [random.uniform(0, 50) for _ in range(4)]  # 4 lead time buckets
            for _ in range(self.num_products)
        ]
        backlog = [random.uniform(0, 30) if random.random() < 0.2 else 0
                   for _ in range(self.num_products)]

        # Historical demand (12 periods)
        demand_history = [
            [self.generate_demand(day - i, p) for i in range(12, 0, -1)]
            for p in range(self.num_products)
        ]

        # Forecasts (8 periods ahead)
        forecasts = [
            [self.generate_demand(day + i, p) * random.uniform(0.9, 1.1)
             for i in range(1, 9)]
            for p in range(self.num_products)
        ]

        # ATP context (order info)
        order_priority = random.randint(1, 5)
        order_qty = random.uniform(10, 100)
        is_rush = 1.0 if random.random() < 0.1 else 0.0
        customer_importance = random.uniform(0, 1)

        atp_context = [
            order_qty / 100,  # Normalized quantity
            order_priority / 5,  # Normalized priority
            is_rush,
            customer_importance,
        ] + [random.uniform(0, 1) for _ in range(12)]  # Pad to 16

        # Determine ATP label based on inventory
        product_idx = random.randint(0, self.num_products - 1)
        available = inventory[product_idx] + sum(pipeline[product_idx])
        shortage = max(0, order_qty - available)

        if shortage == 0:
            atp_label = [1, 0, 0, 0]  # Full fill
        elif shortage < order_qty * 0.5:
            atp_label = [1, 0, 0, 0]  # Partial fill (still "partial" action)
        elif random.random() < 0.3:
            atp_label = [0, 1, 0, 0]  # Substitute
        elif random.random() < 0.5:
            atp_label = [0, 0, 1, 0]  # Split
        else:
            atp_label = [0, 0, 0, 1]  # Reject

        # Inventory planning label (SS/ROP multipliers)
        # Higher multiplier if service level is struggling
        avg_demand = sum(self.base_demands) / self.num_products
        avg_inventory = sum(inventory) / self.num_products
        dos = avg_inventory / avg_demand if avg_demand > 0 else 10

        if dos < 5:
            ss_mult = random.uniform(1.1, 1.2)  # Increase SS
        elif dos > 15:
            ss_mult = random.uniform(0.8, 0.95)  # Decrease SS
        else:
            ss_mult = random.uniform(0.95, 1.05)  # Keep stable

        rop_mult = ss_mult * random.uniform(0.95, 1.05)
        inv_label = [ss_mult, rop_mult]

        # PO context and label
        item_inventory = inventory[product_idx]
        item_demand = self.base_demands[product_idx]
        rop = item_demand * (self.lead_times[product_idx] + 5)  # Simple ROP

        po_context = [
            item_inventory / 100,
            rop / 100,
            item_demand / 50,
            self.lead_times[product_idx] / 14,
        ] + [random.uniform(0, 1) for _ in range(8)]  # Pad to 12

        if item_inventory < rop * 0.8:
            po_label = [1, 0, 0]  # Order now
        elif item_inventory > rop * 1.5:
            po_label = [0, 1, 0]  # Wait
        else:
            po_label = [1, 0, 0] if random.random() < 0.6 else [0, 1, 0]

        # Outcomes (for RL training)
        base_sl = 0.95
        if shortage > 0:
            sl_impact = shortage / order_qty * 0.1
            outcome_sl = max(0.7, base_sl - sl_impact + random.gauss(0, 0.02))
        else:
            outcome_sl = min(0.99, base_sl + random.gauss(0, 0.02))

        outcome_cost = (
            sum(inventory) * 0.5 +  # Holding cost
            sum(backlog) * 2.0 +    # Backlog cost
            random.uniform(50, 200)  # Fixed costs
        )

        return {
            'day': day,
            'inventory': inventory,
            'pipeline': pipeline,
            'backlog': backlog,
            'demand_history': demand_history,
            'forecasts': forecasts,
            'atp_context': atp_context,
            'atp_shortage': shortage,
            'atp_label': atp_label,
            'inv_label': inv_label,
            'po_context': po_context,
            'po_label': po_label,
            'outcome_sl': outcome_sl,
            'outcome_cost': outcome_cost,
        }

    def generate_dataset(self, num_samples: int) -> list:
        """Generate full dataset"""
        samples = []
        for i in range(num_samples):
            day = i % 365 + random.randint(0, 365)  # Vary across year
            sample = self.generate_sample(day)
            samples.append(sample)

            if (i + 1) % 1000 == 0:
                logger.info(f"Generated {i + 1}/{num_samples} samples")

        return samples


async def extract_from_database(site_key: str, limit: int) -> list:
    """Extract historical decisions from database"""
    logger.info(f"Extracting historical data for site: {site_key}")

    # This would connect to actual database
    # For now, return empty list as placeholder
    logger.warning("Database extraction not fully implemented - using synthetic data")

    # Placeholder: would query tables like:
    # - powell_atp_decisions
    # - powell_po_decisions
    # - inventory_level
    # - forecast

    return []


async def generate_from_simpy(
    site_key: str,
    episodes: int,
    episode_length: int
) -> list:
    """Generate data using SimPy simulation"""
    logger.info(f"Running SimPy simulation: {episodes} episodes x {episode_length} steps")

    # This would use the actual SimPy runner
    # For now, use synthetic generator as fallback
    logger.warning("SimPy simulation not fully implemented - using synthetic data")

    generator = SyntheticDataGenerator(demand_pattern='volatile')
    return generator.generate_dataset(episodes * 10)


def split_data(data: list, train_ratio: float, seed: int) -> tuple:
    """Split data into train and validation sets"""
    random.seed(seed)
    random.shuffle(data)

    split_idx = int(len(data) * train_ratio)
    train_data = data[:split_idx]
    val_data = data[split_idx:]

    return train_data, val_data


async def main():
    args = parse_args()
    random.seed(args.seed)

    logger.info(f"Generating training data for site: {args.site_key}")

    samples = []

    # Collect data from selected sources
    if args.from_db:
        db_samples = await extract_from_database(args.site_key, args.db_limit)
        samples.extend(db_samples)
        logger.info(f"Collected {len(db_samples)} samples from database")

    if args.from_simpy:
        simpy_samples = await generate_from_simpy(
            args.site_key, args.episodes, args.episode_length
        )
        samples.extend(simpy_samples)
        logger.info(f"Generated {len(simpy_samples)} samples from SimPy")

    if args.synthetic or (not args.from_db and not args.from_simpy):
        # Default to synthetic if no source specified
        generator = SyntheticDataGenerator(
            num_products=args.num_products,
            demand_pattern=args.demand_pattern,
            seed=args.seed,
        )
        synthetic_samples = generator.generate_dataset(args.num_samples)
        samples.extend(synthetic_samples)
        logger.info(f"Generated {len(synthetic_samples)} synthetic samples")

    logger.info(f"Total samples: {len(samples)}")

    # Create output directory
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.split_output:
        # Split into train/val
        train_data, val_data = split_data(samples, args.train_ratio, args.seed)

        train_path = output_path.with_suffix('.train.json')
        val_path = output_path.with_suffix('.val.json')

        with open(train_path, 'w') as f:
            json.dump(train_data, f)
        logger.info(f"Saved {len(train_data)} training samples to: {train_path}")

        with open(val_path, 'w') as f:
            json.dump(val_data, f)
        logger.info(f"Saved {len(val_data)} validation samples to: {val_path}")
    else:
        # Single output file
        with open(output_path, 'w') as f:
            json.dump(samples, f)
        logger.info(f"Saved {len(samples)} samples to: {output_path}")

    # Save metadata
    metadata_path = output_path.with_suffix('.meta.json')
    with open(metadata_path, 'w') as f:
        json.dump({
            'site_key': args.site_key,
            'total_samples': len(samples),
            'sources': {
                'database': args.from_db,
                'simpy': args.from_simpy,
                'synthetic': args.synthetic or (not args.from_db and not args.from_simpy),
            },
            'generation_params': {
                'num_products': args.num_products,
                'demand_pattern': args.demand_pattern,
                'episodes': args.episodes if args.from_simpy else None,
            },
            'generated_at': datetime.now().isoformat(),
            'seed': args.seed,
        }, f, indent=2)

    logger.info("Data generation complete")


if __name__ == '__main__':
    asyncio.run(main())
