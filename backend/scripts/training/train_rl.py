#!/usr/bin/env python3
"""
Train RL agents for Beer Game using Stable-Baselines3.

Usage:
    python train_rl.py --algorithm PPO --timesteps 1000000 --device cuda
"""

import argparse
import logging
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.agents.rl_agent import create_rl_agent, RLConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Train RL agent for Beer Game")

    # Algorithm and training parameters
    parser.add_argument("--algorithm", default="PPO", choices=["PPO", "SAC", "A2C"],
                        help="RL algorithm to use")
    parser.add_argument("--timesteps", type=int, default=1_000_000,
                        help="Total training timesteps")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"],
                        help="Device for training")
    parser.add_argument("--n-envs", type=int, default=4,
                        help="Number of parallel environments")

    # Hyperparameters
    parser.add_argument("--learning-rate", type=float, default=3e-4,
                        help="Learning rate")
    parser.add_argument("--batch-size", type=int, default=64,
                        help="Batch size")
    parser.add_argument("--n-steps", type=int, default=2048,
                        help="Steps per update (PPO only)")
    parser.add_argument("--gamma", type=float, default=0.99,
                        help="Discount factor")
    parser.add_argument("--gae-lambda", type=float, default=0.95,
                        help="GAE lambda (PPO only)")
    parser.add_argument("--ent-coef", type=float, default=0.01,
                        help="Entropy coefficient")
    parser.add_argument("--vf-coef", type=float, default=0.5,
                        help="Value function coefficient")
    parser.add_argument("--max-grad-norm", type=float, default=0.5,
                        help="Max gradient norm")
    parser.add_argument("--n-epochs", type=int, default=10,
                        help="Epochs per update (PPO only)")
    parser.add_argument("--clip-range", type=float, default=0.2,
                        help="PPO clip range")

    # Environment parameters
    parser.add_argument("--max-rounds", type=int, default=52,
                        help="Max rounds per episode")
    parser.add_argument("--max-order", type=int, default=50,
                        help="Maximum order quantity")
    parser.add_argument("--holding-cost", type=float, default=0.5,
                        help="Holding cost per unit")
    parser.add_argument("--backlog-cost", type=float, default=1.0,
                        help="Backlog cost per unit")
    parser.add_argument("--normalize-obs", action="store_true", default=True,
                        help="Normalize observations")

    # Evaluation parameters
    parser.add_argument("--eval-freq", type=int, default=10000,
                        help="Evaluation frequency (timesteps)")
    parser.add_argument("--eval-episodes", type=int, default=10,
                        help="Number of evaluation episodes")

    # Output parameters
    parser.add_argument("--checkpoint-dir", default="./checkpoints/rl",
                        help="Directory to save checkpoints")
    parser.add_argument("--log-dir", default="./logs/rl",
                        help="TensorBoard log directory")
    parser.add_argument("--save-freq", type=int, default=50000,
                        help="Save checkpoint every N timesteps")
    parser.add_argument("--config-name", default=None,
                        help="Supply chain config name (included in checkpoint filename)")
    parser.add_argument("--verbose", type=int, default=1, choices=[0, 1, 2],
                        help="Verbosity level")

    # Advanced parameters
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed")
    parser.add_argument("--policy-kwargs", type=str, default=None,
                        help="Policy kwargs as JSON string")

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("RL Agent Training Configuration")
    logger.info("=" * 80)
    logger.info(f"Algorithm: {args.algorithm}")
    if args.config_name:
        logger.info(f"Supply Chain Config: {args.config_name}")
    logger.info(f"Total timesteps: {args.timesteps:,}")
    logger.info(f"Device: {args.device}")
    logger.info(f"Parallel environments: {args.n_envs}")
    logger.info(f"Learning rate: {args.learning_rate}")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Entropy coefficient: {args.ent_coef}")
    logger.info(f"Max rounds: {args.max_rounds}")
    logger.info(f"Max order: {args.max_order}")
    logger.info(f"Holding cost: {args.holding_cost}")
    logger.info(f"Backlog cost: {args.backlog_cost}")
    logger.info(f"Checkpoint dir: {args.checkpoint_dir}")
    logger.info(f"Log dir: {args.log_dir}")
    logger.info("=" * 80)

    # Create checkpoint and log directories
    Path(args.checkpoint_dir).mkdir(parents=True, exist_ok=True)
    Path(args.log_dir).mkdir(parents=True, exist_ok=True)

    # Parse policy kwargs if provided
    policy_kwargs = None
    if args.policy_kwargs:
        import json
        policy_kwargs = json.loads(args.policy_kwargs)

    # Create RL agent
    logger.info(f"Creating {args.algorithm} agent...")
    agent = create_rl_agent(
        algorithm=args.algorithm,
        total_timesteps=args.timesteps,
        learning_rate=args.learning_rate,
        batch_size=args.batch_size,
        n_steps=args.n_steps,
        gamma=args.gamma,
        gae_lambda=args.gae_lambda,
        ent_coef=args.ent_coef,
        vf_coef=args.vf_coef,
        max_grad_norm=args.max_grad_norm,
        n_epochs=args.n_epochs,
        clip_range=args.clip_range,
        policy_kwargs=policy_kwargs,
        device=args.device,
        seed=args.seed,
        checkpoint_dir=args.checkpoint_dir,
        log_dir=args.log_dir,
        max_rounds=args.max_rounds,
        max_order=args.max_order,
        holding_cost=args.holding_cost,
        backlog_cost=args.backlog_cost,
        normalize_obs=args.normalize_obs
    )

    # Train agent
    logger.info(f"Starting training for {args.timesteps:,} timesteps...")
    logger.info(f"Episodes expected: ~{args.timesteps // args.max_rounds:,}")
    logger.info("-" * 80)

    try:
        agent.train(
            n_envs=args.n_envs,
            eval_freq=args.eval_freq,
            eval_episodes=args.eval_episodes,
            save_freq=args.save_freq,
            verbose=args.verbose
        )

        logger.info("-" * 80)
        logger.info("Training completed successfully!")

        # Save final model with config name if provided
        if args.config_name:
            # Sanitize config name for filename (replace spaces/special chars with underscore)
            safe_config_name = args.config_name.lower().replace(" ", "_").replace("-", "_")
            safe_config_name = "".join(c for c in safe_config_name if c.isalnum() or c == "_")
            final_model_path = f"{args.checkpoint_dir}/{args.algorithm}_{safe_config_name}_final.zip"
        else:
            final_model_path = f"{args.checkpoint_dir}/{args.algorithm}_final.zip"
        agent.save_model(final_model_path)
        logger.info(f"Final model saved to: {final_model_path}")

        # Run final evaluation
        logger.info("-" * 80)
        logger.info("Running final evaluation...")
        metrics = agent.evaluate(n_episodes=20, render=False)

        logger.info("=" * 80)
        logger.info("Final Evaluation Results")
        logger.info("=" * 80)
        logger.info(f"Episodes: 20")
        logger.info(f"Mean Cost: {metrics['mean_cost']:.2f} ± {metrics['std_cost']:.2f}")
        logger.info(f"Mean Reward: {metrics['mean_reward']:.2f} ± {metrics['std_reward']:.2f}")
        logger.info(f"Mean Episode Length: {metrics['mean_length']:.1f}")
        logger.info("=" * 80)

        # TensorBoard info
        logger.info("")
        logger.info("To view training progress in TensorBoard:")
        logger.info(f"  tensorboard --logdir {args.log_dir}")
        logger.info(f"  Then open: http://localhost:6006")
        logger.info("")

        logger.info("Training script completed successfully!")
        return 0

    except KeyboardInterrupt:
        logger.warning("Training interrupted by user")
        return 1

    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
