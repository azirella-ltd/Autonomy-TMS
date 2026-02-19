#!/usr/bin/env python3
"""Quick test of RL agent."""

import os
from app.agents.rl_agent import create_rl_agent, RLConfig


def main():
    print("Creating RL agent...")
    agent = create_rl_agent(
        algorithm="PPO",
        total_timesteps=10000,
        device="cpu"
    )

    # Train for 10K steps (should take ~2 minutes)
    # Use n_envs=1 to avoid multiprocessing issues
    print("\nStarting training...")
    agent.train(n_envs=1, verbose=1)

    # Evaluate
    print("\n\nEvaluating agent...")
    metrics = agent.evaluate(n_episodes=5, render=False)

    print(f"\nResults:")
    print(f"  Mean Cost: {metrics['mean_cost']:.2f} ± {metrics['std_cost']:.2f}")
    print(f"  Mean Reward: {metrics['mean_reward']:.2f} ± {metrics['std_reward']:.2f}")

    # Save model
    os.makedirs("./checkpoints/rl", exist_ok=True)
    agent.save_model("./checkpoints/rl/test_ppo.zip")
    print(f"\n✅ Model saved to ./checkpoints/rl/test_ppo.zip")


if __name__ == "__main__":
    main()
