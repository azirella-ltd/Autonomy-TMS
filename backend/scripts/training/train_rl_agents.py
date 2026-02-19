"""
Training script for Reinforcement Learning agents.

Supports PPO, SAC, and A2C algorithms.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.agents.rl_agent import RLAgent, RLConfig, create_rl_agent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Train RL agents for The Beer Game")

    parser.add_argument(
        "--algorithm",
        type=str,
        default="PPO",
        choices=["PPO", "SAC", "A2C"],
        help="RL algorithm to use"
    )

    parser.add_argument(
        "--total-timesteps",
        type=int,
        default=1_000_000,
        help="Total training timesteps"
    )

    parser.add_argument(
        "--n-envs",
        type=int,
        default=4,
        help="Number of parallel environments"
    )

    parser.add_argument(
        "--learning-rate",
        type=float,
        default=3e-4,
        help="Learning rate"
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Batch size"
    )

    parser.add_argument(
        "--hidden-dim",
        type=int,
        default=256,
        help="Hidden layer dimension"
    )

    parser.add_argument(
        "--n-layers",
        type=int,
        default=2,
        help="Number of hidden layers"
    )

    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="Device to use for training"
    )

    parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default="checkpoints/rl",
        help="Directory to save checkpoints"
    )

    parser.add_argument(
        "--log-dir",
        type=str,
        default="logs/rl",
        help="Directory for TensorBoard logs"
    )

    parser.add_argument(
        "--eval-freq",
        type=int,
        default=10000,
        help="Evaluation frequency (timesteps)"
    )

    parser.add_argument(
        "--eval-episodes",
        type=int,
        default=10,
        help="Number of evaluation episodes"
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed"
    )

    parser.add_argument(
        "--verbose",
        type=int,
        default=1,
        choices=[0, 1, 2],
        help="Verbosity level"
    )

    return parser.parse_args()


def main():
    """Main training function."""
    args = parse_args()

    logger.info("=" * 80)
    logger.info("RL Agent Training Configuration")
    logger.info("=" * 80)
    logger.info(f"Algorithm: {args.algorithm}")
    logger.info(f"Total timesteps: {args.total_timesteps:,}")
    logger.info(f"Parallel environments: {args.n_envs}")
    logger.info(f"Learning rate: {args.learning_rate}")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Hidden dimension: {args.hidden_dim}")
    logger.info(f"Device: {args.device}")
    logger.info(f"Checkpoint directory: {args.checkpoint_dir}")
    logger.info(f"Log directory: {args.log_dir}")
    logger.info("=" * 80)

    # Create policy kwargs
    policy_kwargs = {
        "net_arch": [
            dict(pi=[args.hidden_dim] * args.n_layers, vf=[args.hidden_dim] * args.n_layers)
        ]
    }

    # Create config
    config = RLConfig(
        algorithm=args.algorithm,
        total_timesteps=args.total_timesteps,
        learning_rate=args.learning_rate,
        batch_size=args.batch_size,
        policy_kwargs=policy_kwargs,
        device=args.device,
        seed=args.seed,
        checkpoint_dir=args.checkpoint_dir,
        log_dir=args.log_dir
    )

    # Create agent
    logger.info("Creating RL agent...")
    agent = RLAgent(config=config)

    # Train
    logger.info("Starting training...")
    try:
        agent.train(
            n_envs=args.n_envs,
            eval_freq=args.eval_freq,
            eval_episodes=args.eval_episodes,
            verbose=args.verbose
        )

        logger.info("Training completed successfully!")

        # Evaluate final model
        logger.info("\nEvaluating final model...")
        metrics = agent.evaluate(n_episodes=20, render=False)

        logger.info("\nFinal Evaluation Metrics:")
        logger.info(f"  Mean reward: {metrics['mean_reward']:.2f} ± {metrics['std_reward']:.2f}")
        logger.info(f"  Mean cost: {metrics['mean_cost']:.2f} ± {metrics['std_cost']:.2f}")
        logger.info(f"  Mean episode length: {metrics['mean_length']:.1f}")

        logger.info("\nTraining complete! Model saved to:")
        logger.info(f"  {agent.model_path}")
        logger.info("\nView training progress with TensorBoard:")
        logger.info(f"  tensorboard --logdir {args.log_dir}")

    except KeyboardInterrupt:
        logger.info("\nTraining interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\nTraining failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
