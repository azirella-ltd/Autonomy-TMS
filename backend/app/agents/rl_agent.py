"""
Reinforcement Learning Agent for Supply Chain Simulation

Implements multiple RL algorithms:
- Proximal Policy Optimization (PPO)
- Soft Actor-Critic (SAC)
- Advantage Actor-Critic (A3C)

Uses Stable-Baselines3 for training and inference.
"""

import numpy as np
import torch
import torch.nn as nn
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
import logging
from pathlib import Path

try:
    import gymnasium as gym
    from gymnasium import spaces
    from stable_baselines3 import PPO, SAC, A2C
    from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
    from stable_baselines3.common.callbacks import BaseCallback, EvalCallback
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.policies import ActorCriticPolicy
    SB3_AVAILABLE = True
except ImportError:
    SB3_AVAILABLE = False
    logging.warning("Stable-Baselines3 not available. RL agents will use fallback heuristics.")
    # Define dummy gym module
    class gym:
        class Env:
            pass
    class spaces:
        pass

logger = logging.getLogger(__name__)


class BasePolicy:
    """Base class for agent policies."""
    pass


def compute_base_stock_order(node, context):
    """
    Compute base-stock heuristic order.
    Simple fallback when RL model not available.
    """
    target_inventory = 12  # Simple base-stock target
    pipeline = sum(node.pipeline_shipments)
    on_hand = max(0, node.inventory - node.backlog)

    # Order up to target level
    order = max(0, target_inventory - on_hand - pipeline + node.incoming_order)
    return int(order)


@dataclass
class RLConfig:
    """Configuration for RL agent training."""
    # Training parameters
    algorithm: str = "PPO"  # PPO, SAC, A2C
    total_timesteps: int = 1_000_000
    learning_rate: float = 3e-4
    batch_size: int = 64
    n_steps: int = 2048  # PPO only
    gamma: float = 0.99
    gae_lambda: float = 0.95  # PPO only
    ent_coef: float = 0.01  # Entropy coefficient
    vf_coef: float = 0.5  # Value function coefficient
    max_grad_norm: float = 0.5
    n_epochs: int = 10  # PPO only
    clip_range: float = 0.2  # PPO only
    policy_kwargs: Optional[Dict[str, Any]] = None
    device: str = "auto"  # "auto", "cuda", "cpu"
    seed: Optional[int] = None
    checkpoint_dir: str = "checkpoints/rl"
    log_dir: str = "logs/rl"

    # Environment parameters
    max_periods: int = 52
    max_order: int = 50
    holding_cost: float = 0.5
    backlog_cost: float = 1.0
    normalize_obs: bool = True


class SimulationRLEnv(gym.Env):
    """
    Gymnasium environment for training RL agents on supply chain simulation.

    Observation space:
    - inventory: current inventory level
    - backlog: current backlog
    - incoming_shipment_0: shipment arriving this round
    - incoming_shipment_1: shipment arriving next round
    - incoming_order: order received from downstream
    - last_order: last order placed upstream
    - round_number: current round (normalized)
    - total_cost: cumulative cost (normalized)

    Action space:
    - order_quantity: integer [0, max_order]
    """
    metadata = {'render_modes': []}

    def __init__(
        self,
        max_periods: int = 52,
        max_order: int = 50,
        holding_cost: float = 0.5,
        backlog_cost: float = 1.0,
        initial_inventory: int = 12,
        lead_time: int = 2,
        normalize_obs: bool = True
    ):
        self.max_periods = max_periods
        self.max_order = max_order
        self.holding_cost = holding_cost
        self.backlog_cost = backlog_cost
        self.initial_inventory = initial_inventory
        self.lead_time = lead_time
        self.normalize_obs = normalize_obs

        # State variables
        self.current_period = 0
        self.inventory = initial_inventory
        self.backlog = 0
        self.pipeline_shipments = [0] * lead_time
        self.incoming_order = 0
        self.last_order = 0
        self.total_cost = 0.0

        # Demand simulation (simple stochastic model)
        self.demand_mean = 8
        self.demand_std = 4

        # Observation and action spaces (for SB3 compatibility)
        self.observation_space = self._get_obs_space()
        self.action_space = self._get_action_space()

    def _get_obs_space(self):
        """Define observation space."""
        return spaces.Box(
            low=np.array([0, 0, 0, 0, 0, 0, 0, 0], dtype=np.float32),
            high=np.array([100, 100, 100, 100, 100, 100, 1, 10000], dtype=np.float32),
            dtype=np.float32
        )

    def _get_action_space(self):
        """Define action space."""
        return spaces.Discrete(self.max_order + 1)

    def reset(self, seed=None, options=None):
        """Reset environment to initial state."""
        super().reset(seed=seed)
        if seed is not None:
            np.random.seed(seed)

        self.current_period = 0
        self.inventory = self.initial_inventory
        self.backlog = 0
        self.pipeline_shipments = [0] * self.lead_time
        self.incoming_order = int(np.random.normal(self.demand_mean, self.demand_std))
        self.incoming_order = max(0, self.incoming_order)
        self.last_order = 0
        self.total_cost = 0.0

        return self._get_observation(), {}

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict[str, Any]]:
        """
        Execute one step in the environment.

        Args:
            action: Order quantity to place upstream

        Returns:
            observation: Next state
            reward: Reward signal (negative cost)
            done: Whether episode is complete
            info: Additional information
        """
        order_quantity = int(action)
        order_quantity = np.clip(order_quantity, 0, self.max_order)

        # Receive shipment from upstream
        arriving_shipment = self.pipeline_shipments[0] if self.pipeline_shipments else 0
        self.inventory += arriving_shipment

        # Fulfill demand (incoming order from downstream)
        demand = self.incoming_order
        if self.inventory >= demand:
            # Full fulfillment
            self.inventory -= demand
            fulfilled = demand
        else:
            # Partial fulfillment, backlog increases
            fulfilled = self.inventory
            self.backlog += (demand - fulfilled)
            self.inventory = 0

        # Fulfill backlog if possible
        if self.backlog > 0 and self.inventory > 0:
            backlog_fulfilled = min(self.backlog, self.inventory)
            self.backlog -= backlog_fulfilled
            self.inventory -= backlog_fulfilled

        # Calculate costs for this round
        round_cost = (self.inventory * self.holding_cost) + (self.backlog * self.backlog_cost)
        self.total_cost += round_cost

        # Reward is negative cost (we want to minimize cost)
        reward = -round_cost

        # Place order upstream (add to pipeline)
        self.pipeline_shipments.append(order_quantity)
        if len(self.pipeline_shipments) > self.lead_time:
            self.pipeline_shipments.pop(0)

        self.last_order = order_quantity

        # Generate next round's demand (stochastic)
        self.incoming_order = int(np.random.normal(self.demand_mean, self.demand_std))
        self.incoming_order = max(0, self.incoming_order)

        # Advance round
        self.current_period += 1
        terminated = self.current_period >= self.max_periods
        truncated = False  # We don't have truncation conditions

        info = {
            "round": self.current_period,
            "inventory": self.inventory,
            "backlog": self.backlog,
            "cost": round_cost,
            "total_cost": self.total_cost,
            "order": order_quantity,
            "demand": demand
        }

        return self._get_observation(), reward, terminated, truncated, info

    def _get_observation(self) -> np.ndarray:
        """Get current observation vector."""
        obs = np.array([
            self.inventory,
            self.backlog,
            self.pipeline_shipments[0] if len(self.pipeline_shipments) > 0 else 0,
            self.pipeline_shipments[1] if len(self.pipeline_shipments) > 1 else 0,
            self.incoming_order,
            self.last_order,
            self.current_period / self.max_periods,  # Normalized round
            self.total_cost / (self.max_periods * 100)  # Normalized cost
        ], dtype=np.float32)

        if self.normalize_obs:
            # Normalize observations for better training stability
            obs[:6] = obs[:6] / 100.0  # Inventory, backlog, orders

        return obs


class TensorBoardCallback(BaseCallback):
    """Callback for logging training metrics to TensorBoard."""

    def __init__(self, verbose: int = 0):
        super().__init__(verbose)
        self.episode_rewards = []
        self.episode_lengths = []
        self.episode_costs = []

    def _on_step(self) -> bool:
        """Called at each environment step."""
        # Log episode metrics when episode ends
        for idx, done in enumerate(self.locals.get("dones", [])):
            if done:
                info = self.locals["infos"][idx]
                if "total_cost" in info:
                    self.episode_costs.append(info["total_cost"])
                    self.logger.record("train/episode_cost", info["total_cost"])
                if "episode" in info:
                    self.episode_rewards.append(info["episode"]["r"])
                    self.episode_lengths.append(info["episode"]["l"])
                    self.logger.record("train/episode_reward", info["episode"]["r"])
                    self.logger.record("train/episode_length", info["episode"]["l"])

        return True


class RLAgent(BasePolicy):
    """
    Reinforcement Learning agent for supply chain simulation.

    Uses Stable-Baselines3 for training and inference.
    Falls back to base-stock heuristic if SB3 not available or model not trained.
    """

    def __init__(
        self,
        config: Optional[RLConfig] = None,
        model_path: Optional[str] = None
    ):
        super().__init__()
        self.config = config or RLConfig()
        self.model = None
        self.model_path = model_path
        self.is_trained = False

        if not SB3_AVAILABLE:
            logger.warning("Stable-Baselines3 not available. Using fallback heuristic.")
            return

        # Load model if path provided
        if model_path and Path(model_path).exists():
            self.load_model(model_path)

    def compute_order(self, node: Any, context: Dict[str, Any]) -> int:
        """
        Compute order quantity using RL agent.

        Args:
            node: Node object with inventory, backlog, etc.
            context: Scenario context

        Returns:
            order_quantity: Integer order quantity
        """
        if not self.is_trained or not SB3_AVAILABLE:
            # Fallback to base-stock heuristic
            return compute_base_stock_order(node, context)

        # Prepare observation from node state
        observation = self._prepare_observation(node, context)

        # Get action from trained model
        action, _states = self.model.predict(observation, deterministic=True)

        # Convert action to order quantity
        order_quantity = int(action)

        # Safety clamp
        order_quantity = max(0, min(order_quantity, 100))

        logger.debug(f"RL agent order: {order_quantity} (inventory={node.inventory}, backlog={node.backlog})")

        return order_quantity

    def _prepare_observation(self, node: Any, context: Dict[str, Any]) -> np.ndarray:
        """Prepare observation vector from node state."""
        inventory = node.inventory
        backlog = node.backlog

        # Get pipeline shipments
        pipeline = node.pipeline_shipments if hasattr(node, 'pipeline_shipments') else []
        incoming_shipment_0 = pipeline[0] if len(pipeline) > 0 else 0
        incoming_shipment_1 = pipeline[1] if len(pipeline) > 1 else 0

        # Get incoming order
        incoming_order = node.incoming_order if hasattr(node, 'incoming_order') else 0

        # Get last order
        last_order = node.last_order_placed if hasattr(node, 'last_order_placed') else 0

        # Get round number
        round_number = context.get("round_number", 0)
        max_periods = context.get("max_periods", 52)

        # Get total cost
        total_cost = node.total_cost if hasattr(node, 'total_cost') else 0

        obs = np.array([
            inventory,
            backlog,
            incoming_shipment_0,
            incoming_shipment_1,
            incoming_order,
            last_order,
            round_number / max_periods,
            total_cost / (max_periods * 100)
        ], dtype=np.float32)

        if self.config.normalize_obs:
            obs[:6] = obs[:6] / 100.0

        return obs

    def train(
        self,
        n_envs: int = 4,
        eval_freq: int = 10000,
        eval_episodes: int = 10,
        save_freq: int = 50000,
        verbose: int = 1
    ):
        """
        Train RL agent using parallel environments.

        Args:
            n_envs: Number of parallel environments
            eval_freq: Evaluate every N timesteps
            eval_episodes: Number of evaluation episodes
            save_freq: Save model every N timesteps
            verbose: Verbosity level
        """
        if not SB3_AVAILABLE:
            raise ImportError("Stable-Baselines3 required for training. Install with: pip install stable-baselines3")

        # Create checkpoint and log directories
        Path(self.config.checkpoint_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.log_dir).mkdir(parents=True, exist_ok=True)

        # Create vectorized environments
        def make_env():
            env = SimulationRLEnv(
                max_periods=52,
                max_order=50,
                normalize_obs=self.config.normalize_obs
            )
            env = Monitor(env)
            return env

        if n_envs > 1:
            env = SubprocVecEnv([make_env for _ in range(n_envs)])
        else:
            env = DummyVecEnv([make_env])

        # Create evaluation environment
        eval_env = DummyVecEnv([make_env])

        # Policy kwargs
        policy_kwargs = self.config.policy_kwargs or {
            "net_arch": [dict(pi=[256, 256], vf=[256, 256])],
            "activation_fn": nn.ReLU
        }

        # Initialize model
        if self.config.algorithm == "PPO":
            self.model = PPO(
                "MlpPolicy",
                env,
                learning_rate=self.config.learning_rate,
                n_steps=self.config.n_steps,
                batch_size=self.config.batch_size,
                n_epochs=self.config.n_epochs,
                gamma=self.config.gamma,
                gae_lambda=self.config.gae_lambda,
                clip_range=self.config.clip_range,
                ent_coef=self.config.ent_coef,
                vf_coef=self.config.vf_coef,
                max_grad_norm=self.config.max_grad_norm,
                policy_kwargs=policy_kwargs,
                verbose=verbose,
                device=self.config.device,
                seed=self.config.seed,
                tensorboard_log=self.config.log_dir
            )
        elif self.config.algorithm == "SAC":
            self.model = SAC(
                "MlpPolicy",
                env,
                learning_rate=self.config.learning_rate,
                batch_size=self.config.batch_size,
                gamma=self.config.gamma,
                ent_coef=self.config.ent_coef,
                policy_kwargs=policy_kwargs,
                verbose=verbose,
                device=self.config.device,
                seed=self.config.seed,
                tensorboard_log=self.config.log_dir
            )
        elif self.config.algorithm == "A2C":
            self.model = A2C(
                "MlpPolicy",
                env,
                learning_rate=self.config.learning_rate,
                n_steps=self.config.n_steps,
                gamma=self.config.gamma,
                gae_lambda=self.config.gae_lambda,
                ent_coef=self.config.ent_coef,
                vf_coef=self.config.vf_coef,
                max_grad_norm=self.config.max_grad_norm,
                policy_kwargs=policy_kwargs,
                verbose=verbose,
                device=self.config.device,
                seed=self.config.seed,
                tensorboard_log=self.config.log_dir
            )
        else:
            raise ValueError(f"Unknown algorithm: {self.config.algorithm}")

        # Callbacks
        eval_callback = EvalCallback(
            eval_env,
            best_model_save_path=f"{self.config.checkpoint_dir}/best",
            log_path=f"{self.config.log_dir}/eval",
            eval_freq=eval_freq,
            n_eval_episodes=eval_episodes,
            deterministic=True,
            render=False
        )

        tb_callback = TensorBoardCallback(verbose=verbose)

        # Train
        logger.info(f"Starting {self.config.algorithm} training for {self.config.total_timesteps} timesteps...")
        self.model.learn(
            total_timesteps=self.config.total_timesteps,
            callback=[eval_callback, tb_callback],
            log_interval=10
        )

        # Save final model
        final_path = f"{self.config.checkpoint_dir}/{self.config.algorithm}_final.zip"
        self.model.save(final_path)
        logger.info(f"Training complete. Model saved to {final_path}")

        self.is_trained = True
        self.model_path = final_path

        env.close()
        eval_env.close()

    def load_model(self, path: str):
        """Load trained model from file."""
        if not SB3_AVAILABLE:
            raise ImportError("Stable-Baselines3 required for loading models.")

        logger.info(f"Loading RL model from {path}")

        # Detect algorithm from path
        if "PPO" in path or self.config.algorithm == "PPO":
            self.model = PPO.load(path)
        elif "SAC" in path or self.config.algorithm == "SAC":
            self.model = SAC.load(path)
        elif "A2C" in path or self.config.algorithm == "A2C":
            self.model = A2C.load(path)
        else:
            # Try PPO as default
            self.model = PPO.load(path)

        self.is_trained = True
        self.model_path = path
        logger.info(f"Model loaded successfully")

    def save_model(self, path: str):
        """Save trained model to file."""
        if not self.is_trained or self.model is None:
            raise ValueError("Model must be trained before saving")

        self.model.save(path)
        self.model_path = path
        logger.info(f"Model saved to {path}")

    def evaluate(
        self,
        n_episodes: int = 10,
        render: bool = False
    ) -> Dict[str, float]:
        """
        Evaluate trained model.

        Args:
            n_episodes: Number of episodes to evaluate
            render: Whether to render environment

        Returns:
            metrics: Dictionary of evaluation metrics
        """
        if not self.is_trained or self.model is None:
            raise ValueError("Model must be trained before evaluation")

        env = SimulationRLEnv(normalize_obs=self.config.normalize_obs)

        episode_rewards = []
        episode_costs = []
        episode_lengths = []

        for episode in range(n_episodes):
            obs, info = env.reset()
            terminated = False
            truncated = False
            done = False
            episode_reward = 0
            episode_length = 0

            while not done:
                action, _states = self.model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, info = env.step(action)
                done = terminated or truncated
                episode_reward += reward
                episode_length += 1

                if render:
                    print(f"Round {info['round']}: Inv={info['inventory']}, "
                          f"Backlog={info['backlog']}, Order={info['order']}, "
                          f"Cost={info['cost']:.2f}")

            episode_rewards.append(episode_reward)
            episode_costs.append(info["total_cost"])
            episode_lengths.append(episode_length)

            if render:
                print(f"Episode {episode + 1}: Total Cost={info['total_cost']:.2f}, "
                      f"Total Reward={episode_reward:.2f}\n")

        metrics = {
            "mean_reward": np.mean(episode_rewards),
            "std_reward": np.std(episode_rewards),
            "mean_cost": np.mean(episode_costs),
            "std_cost": np.std(episode_costs),
            "mean_length": np.mean(episode_lengths)
        }

        logger.info(f"Evaluation over {n_episodes} episodes:")
        logger.info(f"  Mean reward: {metrics['mean_reward']:.2f} ± {metrics['std_reward']:.2f}")
        logger.info(f"  Mean cost: {metrics['mean_cost']:.2f} ± {metrics['std_cost']:.2f}")

        return metrics


# Factory function for creating RL agents
def create_rl_agent(
    algorithm: str = "PPO",
    model_path: Optional[str] = None,
    **kwargs
) -> RLAgent:
    """
    Factory function for creating RL agents.

    Args:
        algorithm: RL algorithm (PPO, SAC, A2C)
        model_path: Path to pre-trained model
        **kwargs: Additional config parameters

    Returns:
        agent: Configured RL agent
    """
    config = RLConfig(algorithm=algorithm, **kwargs)
    agent = RLAgent(config=config, model_path=model_path)
    return agent
