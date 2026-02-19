"""
AutoML & Hyperparameter Optimization

Provides automated machine learning capabilities:
- Hyperparameter optimization with Optuna
- Architecture search for GNN models
- RL agent hyperparameter tuning
- Multi-objective optimization (accuracy, speed, memory)
"""

from typing import Dict, Any, Optional, List, Tuple, Callable
from datetime import datetime
import logging
import json
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import optuna
    from optuna.pruners import MedianPruner, HyperbandPruner
    from optuna.samplers import TPESampler
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    optuna = None  # type: ignore

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.cuda.amp import autocast, GradScaler
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None  # type: ignore
    nn = None  # type: ignore


class GNNHyperparameterOptimizer:
    """
    Hyperparameter optimization for GNN models using Optuna.

    Optimizes:
    - Architecture parameters (hidden_dim, num_layers, num_heads)
    - Training parameters (learning_rate, dropout, weight_decay)
    - Batch and sequence parameters (window_size, batch_size)
    """

    def __init__(
        self,
        data_loader: Callable,
        config_name: str,
        architecture: str = "enhanced",
        n_trials: int = 50,
        timeout: Optional[int] = None,
        study_name: Optional[str] = None,
        storage: Optional[str] = None
    ):
        """
        Initialize GNN hyperparameter optimizer.

        Args:
            data_loader: Function that returns (X, A, P, Y) training data
            config_name: Supply chain configuration name
            architecture: GNN architecture type
            n_trials: Number of optimization trials
            timeout: Optimization timeout in seconds
            study_name: Optuna study name (for persistence)
            storage: Optuna storage URL (for persistence)
        """
        if not OPTUNA_AVAILABLE:
            raise RuntimeError("Optuna is required for AutoML. Install with: pip install optuna")

        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch is required for GNN training. Install with: pip install torch")

        self.data_loader = data_loader
        self.config_name = config_name
        self.architecture = architecture
        self.n_trials = n_trials
        self.timeout = timeout
        self.study_name = study_name or f"gnn_{architecture}_{config_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.storage = storage

        self.best_params: Optional[Dict[str, Any]] = None
        self.best_value: Optional[float] = None
        self.study: Optional[optuna.Study] = None

    def objective(self, trial: optuna.Trial) -> float:
        """
        Optuna objective function for GNN hyperparameter optimization.

        Args:
            trial: Optuna trial object

        Returns:
            validation_loss: Validation loss to minimize
        """
        # Suggest hyperparameters
        hidden_dim = trial.suggest_int('hidden_dim', 64, 256, step=32)
        num_spatial_layers = trial.suggest_int('num_spatial_layers', 2, 4)
        num_temporal_layers = trial.suggest_int('num_temporal_layers', 1, 3)
        num_heads = trial.suggest_categorical('num_heads', [4, 8, 16])
        dropout = trial.suggest_float('dropout', 0.1, 0.5, step=0.1)
        learning_rate = trial.suggest_float('learning_rate', 1e-5, 1e-2, log=True)
        weight_decay = trial.suggest_float('weight_decay', 1e-6, 1e-3, log=True)
        window_size = trial.suggest_int('window_size', 10, 52, step=4)

        # Load data
        logger.info(f"Trial {trial.number}: Loading data with window_size={window_size}")
        X, A, P, Y = self.data_loader(window=window_size, horizon=1)

        # Normalize features
        X_mean = X.mean(axis=(0, 1, 2), keepdims=True)
        X_std = X.std(axis=(0, 1, 2), keepdims=True)
        X_std = np.where(X_std < 1e-6, 1.0, X_std)
        X_norm = (X - X_mean) / X_std

        # Split into train/val
        train_size = int(0.8 * len(X_norm))
        X_train, X_val = X_norm[:train_size], X_norm[train_size:]
        Y_train, Y_val = Y[:train_size], Y[train_size:]

        # Create model
        from app.models.gnn.enhanced_gnn import create_enhanced_gnn

        in_dim = X.shape[-1]
        model = create_enhanced_gnn(
            architecture=self.architecture,
            node_feature_dim=in_dim,
            edge_feature_dim=4,
            hidden_dim=hidden_dim,
            num_spatial_layers=num_spatial_layers,
            num_temporal_layers=num_temporal_layers,
            num_heads=num_heads,
            dropout=dropout,
            window_size=window_size
        )

        # Device selection
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        model = model.to(device)

        # Optimizer
        optimizer = optim.Adam(model.parameters(), lr=learning_rate, weight_decay=weight_decay)

        # Training loop
        epochs = 10  # Fixed epochs for each trial
        model.train()

        for epoch in range(epochs):
            # Training step
            x = torch.as_tensor(X_train, dtype=torch.float32, device=device)
            y = torch.as_tensor(Y_train, dtype=torch.long, device=device)

            optimizer.zero_grad()

            # Forward pass (architecture-specific)
            if self.architecture in ['graphsage']:
                # GraphSAGE expects [B*T*N, F] and edge_index
                B, T, N, F = x.shape
                x_flat = x.reshape(B * T * N, F)

                # Create edge index from adjacency matrix
                edge_index = self._create_edge_index(A, device)

                outputs = model(x_flat, edge_index)
                order_pred = outputs['order']

                # Reshape predictions
                order_pred = order_pred.reshape(B, T, N, -1)

            elif self.architecture in ['temporal', 'enhanced']:
                # Temporal models expect [B, T, N, F]
                edge_index = self._create_edge_index(A, device)
                outputs = model(x, edge_index)
                order_pred = outputs['order']

            else:
                raise ValueError(f"Unknown architecture: {self.architecture}")

            # Compute loss
            if Y_train.ndim == 3 and Y_train.shape[1] == N:
                y = torch.as_tensor(np.swapaxes(Y_train, 1, 2), dtype=torch.long, device=device)

            # Flatten for cross entropy
            H = y.shape[1]  # horizon
            order_pred_flat = order_pred[:, -H:].reshape(-1, order_pred.shape[-1]) if order_pred.ndim == 4 else order_pred.reshape(-1, order_pred.shape[-1])
            y_flat = y.reshape(-1)

            loss = nn.functional.cross_entropy(order_pred_flat, y_flat)

            loss.backward()
            optimizer.step()

            # Validation
            if epoch % 2 == 0:
                model.eval()
                with torch.no_grad():
                    x_val = torch.as_tensor(X_val, dtype=torch.float32, device=device)
                    y_val = torch.as_tensor(Y_val, dtype=torch.long, device=device)

                    # Forward pass
                    if self.architecture in ['graphsage']:
                        B_val, T_val, N_val, F_val = x_val.shape
                        x_val_flat = x_val.reshape(B_val * T_val * N_val, F_val)
                        outputs_val = model(x_val_flat, edge_index)
                        order_pred_val = outputs_val['order'].reshape(B_val, T_val, N_val, -1)
                    else:
                        outputs_val = model(x_val, edge_index)
                        order_pred_val = outputs_val['order']

                    # Compute validation loss
                    if Y_val.ndim == 3 and Y_val.shape[1] == N:
                        y_val = torch.as_tensor(np.swapaxes(Y_val, 1, 2), dtype=torch.long, device=device)

                    H_val = y_val.shape[1]
                    order_pred_val_flat = order_pred_val[:, -H_val:].reshape(-1, order_pred_val.shape[-1]) if order_pred_val.ndim == 4 else order_pred_val.reshape(-1, order_pred_val.shape[-1])
                    y_val_flat = y_val.reshape(-1)

                    val_loss = nn.functional.cross_entropy(order_pred_val_flat, y_val_flat).item()

                # Report intermediate value for pruning
                trial.report(val_loss, epoch)

                # Prune unpromising trials
                if trial.should_prune():
                    raise optuna.TrialPruned()

                model.train()

        # Final validation loss
        model.eval()
        with torch.no_grad():
            x_val = torch.as_tensor(X_val, dtype=torch.float32, device=device)
            y_val = torch.as_tensor(Y_val, dtype=torch.long, device=device)

            if self.architecture in ['graphsage']:
                B_val, T_val, N_val, F_val = x_val.shape
                x_val_flat = x_val.reshape(B_val * T_val * N_val, F_val)
                outputs_val = model(x_val_flat, edge_index)
                order_pred_val = outputs_val['order'].reshape(B_val, T_val, N_val, -1)
            else:
                outputs_val = model(x_val, edge_index)
                order_pred_val = outputs_val['order']

            if Y_val.ndim == 3 and Y_val.shape[1] == N:
                y_val = torch.as_tensor(np.swapaxes(Y_val, 1, 2), dtype=torch.long, device=device)

            H_val = y_val.shape[1]
            order_pred_val_flat = order_pred_val[:, -H_val:].reshape(-1, order_pred_val.shape[-1]) if order_pred_val.ndim == 4 else order_pred_val.reshape(-1, order_pred_val.shape[-1])
            y_val_flat = y_val.reshape(-1)

            final_val_loss = nn.functional.cross_entropy(order_pred_val_flat, y_val_flat).item()

        logger.info(f"Trial {trial.number} finished: val_loss={final_val_loss:.4f}")

        return final_val_loss

    def _create_edge_index(self, A: np.ndarray, device: torch.device) -> torch.Tensor:
        """Create edge index from adjacency matrix."""
        # A is [2, num_nodes, num_nodes]
        # Extract first adjacency matrix (assuming static graph structure)
        adj = A[0] if A.ndim == 3 else A

        # Convert to edge list
        edge_list = np.argwhere(adj > 0)
        edge_index = torch.tensor(edge_list.T, dtype=torch.long, device=device)

        return edge_index

    def optimize(self) -> Dict[str, Any]:
        """
        Run hyperparameter optimization.

        Returns:
            results: Dictionary with best parameters and optimization history
        """
        logger.info(f"Starting hyperparameter optimization for {self.architecture}")
        logger.info(f"Config: {self.config_name}, Trials: {self.n_trials}, Timeout: {self.timeout}s")

        # Create study
        sampler = TPESampler(seed=42)
        pruner = MedianPruner(n_startup_trials=5, n_warmup_steps=3)

        self.study = optuna.create_study(
            study_name=self.study_name,
            storage=self.storage,
            load_if_exists=True,
            direction='minimize',
            sampler=sampler,
            pruner=pruner
        )

        # Run optimization
        self.study.optimize(
            self.objective,
            n_trials=self.n_trials,
            timeout=self.timeout,
            show_progress_bar=True
        )

        # Extract best parameters
        self.best_params = self.study.best_params
        self.best_value = self.study.best_value

        logger.info(f"Optimization complete!")
        logger.info(f"Best validation loss: {self.best_value:.4f}")
        logger.info(f"Best parameters: {json.dumps(self.best_params, indent=2)}")

        # Compile results
        results = {
            "status": "completed",
            "architecture": self.architecture,
            "config_name": self.config_name,
            "n_trials": len(self.study.trials),
            "best_value": self.best_value,
            "best_params": self.best_params,
            "study_name": self.study_name,
            "completed_at": datetime.now().isoformat()
        }

        return results

    def save_results(self, output_path: str):
        """Save optimization results to JSON file."""
        if self.best_params is None:
            raise RuntimeError("No optimization results to save. Run optimize() first.")

        results = {
            "study_name": self.study_name,
            "architecture": self.architecture,
            "config_name": self.config_name,
            "n_trials": len(self.study.trials),
            "best_value": self.best_value,
            "best_params": self.best_params,
            "all_trials": [
                {
                    "number": trial.number,
                    "value": trial.value,
                    "params": trial.params,
                    "state": trial.state.name
                }
                for trial in self.study.trials
            ],
            "timestamp": datetime.now().isoformat()
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"Saved optimization results to {output_path}")


class RLHyperparameterOptimizer:
    """
    Hyperparameter optimization for RL agents.

    Optimizes:
    - RL algorithm parameters (learning_rate, gamma, ent_coef, etc.)
    - Network architecture (policy_layers, value_layers)
    - Training parameters (batch_size, n_steps, n_epochs)
    """

    def __init__(
        self,
        config_name: str,
        algorithm: str = 'PPO',
        n_trials: int = 30,
        timeout: Optional[int] = None,
        study_name: Optional[str] = None,
        storage: Optional[str] = None
    ):
        """
        Initialize RL hyperparameter optimizer.

        Args:
            config_name: Supply chain configuration name
            algorithm: RL algorithm ('PPO', 'SAC', 'A2C')
            n_trials: Number of optimization trials
            timeout: Optimization timeout in seconds
            study_name: Optuna study name
            storage: Optuna storage URL
        """
        if not OPTUNA_AVAILABLE:
            raise RuntimeError("Optuna is required for AutoML. Install with: pip install optuna")

        self.config_name = config_name
        self.algorithm = algorithm
        self.n_trials = n_trials
        self.timeout = timeout
        self.study_name = study_name or f"rl_{algorithm}_{config_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.storage = storage

        self.best_params: Optional[Dict[str, Any]] = None
        self.best_value: Optional[float] = None
        self.study: Optional[optuna.Study] = None

    def objective(self, trial: optuna.Trial) -> float:
        """
        Optuna objective function for RL hyperparameter optimization.

        Args:
            trial: Optuna trial object

        Returns:
            mean_reward: Negative mean reward (to minimize)
        """
        # Algorithm-specific hyperparameters
        if self.algorithm == 'PPO':
            learning_rate = trial.suggest_float('learning_rate', 1e-5, 1e-2, log=True)
            gamma = trial.suggest_float('gamma', 0.9, 0.9999)
            ent_coef = trial.suggest_float('ent_coef', 0.0, 0.1)
            clip_range = trial.suggest_float('clip_range', 0.1, 0.4)
            n_steps = trial.suggest_categorical('n_steps', [128, 256, 512, 1024, 2048])
            n_epochs = trial.suggest_int('n_epochs', 3, 30)
            batch_size = trial.suggest_categorical('batch_size', [32, 64, 128, 256])
            gae_lambda = trial.suggest_float('gae_lambda', 0.8, 1.0)

        elif self.algorithm == 'SAC':
            learning_rate = trial.suggest_float('learning_rate', 1e-5, 1e-2, log=True)
            gamma = trial.suggest_float('gamma', 0.9, 0.9999)
            tau = trial.suggest_float('tau', 0.001, 0.05)
            ent_coef = trial.suggest_categorical('ent_coef', ['auto', 0.01, 0.1, 0.5])
            batch_size = trial.suggest_categorical('batch_size', [64, 128, 256, 512])

        elif self.algorithm == 'A2C':
            learning_rate = trial.suggest_float('learning_rate', 1e-5, 1e-2, log=True)
            gamma = trial.suggest_float('gamma', 0.9, 0.9999)
            ent_coef = trial.suggest_float('ent_coef', 0.0, 0.1)
            n_steps = trial.suggest_categorical('n_steps', [5, 16, 32, 64])
            gae_lambda = trial.suggest_float('gae_lambda', 0.8, 1.0)

        else:
            raise ValueError(f"Unknown algorithm: {self.algorithm}")

        # Network architecture
        net_arch_type = trial.suggest_categorical('net_arch', ['small', 'medium', 'large'])
        net_arch = {
            'small': [dict(pi=[64, 64], vf=[64, 64])],
            'medium': [dict(pi=[128, 128], vf=[128, 128])],
            'large': [dict(pi=[256, 256], vf=[256, 256])]
        }[net_arch_type]

        # Train RL agent
        try:
            from app.agents.rl_agent import RLAgent

            # Create hyperparameter dictionary
            hyperparams = {
                'learning_rate': learning_rate,
                'gamma': gamma,
                'policy_kwargs': {'net_arch': net_arch}
            }

            if self.algorithm == 'PPO':
                hyperparams.update({
                    'ent_coef': ent_coef,
                    'clip_range': clip_range,
                    'n_steps': n_steps,
                    'n_epochs': n_epochs,
                    'batch_size': batch_size,
                    'gae_lambda': gae_lambda
                })
            elif self.algorithm == 'SAC':
                hyperparams.update({
                    'tau': tau,
                    'ent_coef': ent_coef,
                    'batch_size': batch_size
                })
            elif self.algorithm == 'A2C':
                hyperparams.update({
                    'ent_coef': ent_coef,
                    'n_steps': n_steps,
                    'gae_lambda': gae_lambda
                })

            # Create and train agent
            agent = RLAgent(
                config_name=self.config_name,
                algorithm=self.algorithm,
                **hyperparams
            )

            # Train for limited timesteps
            total_timesteps = 10000  # Quick evaluation
            mean_reward = agent.train(total_timesteps=total_timesteps)

            logger.info(f"Trial {trial.number} finished: mean_reward={mean_reward:.2f}")

            # Return negative reward to minimize (Optuna minimizes by default)
            return -mean_reward

        except Exception as e:
            logger.error(f"Trial {trial.number} failed: {str(e)}")
            # Return penalty for failed trials
            return 1e6

    def optimize(self) -> Dict[str, Any]:
        """
        Run hyperparameter optimization.

        Returns:
            results: Dictionary with best parameters and optimization history
        """
        logger.info(f"Starting RL hyperparameter optimization")
        logger.info(f"Algorithm: {self.algorithm}, Config: {self.config_name}")
        logger.info(f"Trials: {self.n_trials}, Timeout: {self.timeout}s")

        # Create study
        sampler = TPESampler(seed=42)
        pruner = MedianPruner(n_startup_trials=5, n_warmup_steps=2)

        self.study = optuna.create_study(
            study_name=self.study_name,
            storage=self.storage,
            load_if_exists=True,
            direction='minimize',  # Minimizing negative reward
            sampler=sampler,
            pruner=pruner
        )

        # Run optimization
        self.study.optimize(
            self.objective,
            n_trials=self.n_trials,
            timeout=self.timeout,
            show_progress_bar=True
        )

        # Extract best parameters
        self.best_params = self.study.best_params
        self.best_value = -self.study.best_value  # Convert back to positive reward

        logger.info(f"Optimization complete!")
        logger.info(f"Best mean reward: {self.best_value:.2f}")
        logger.info(f"Best parameters: {json.dumps(self.best_params, indent=2)}")

        # Compile results
        results = {
            "status": "completed",
            "algorithm": self.algorithm,
            "config_name": self.config_name,
            "n_trials": len(self.study.trials),
            "best_value": self.best_value,
            "best_params": self.best_params,
            "study_name": self.study_name,
            "completed_at": datetime.now().isoformat()
        }

        return results

    def save_results(self, output_path: str):
        """Save optimization results to JSON file."""
        if self.best_params is None:
            raise RuntimeError("No optimization results to save. Run optimize() first.")

        results = {
            "study_name": self.study_name,
            "algorithm": self.algorithm,
            "config_name": self.config_name,
            "n_trials": len(self.study.trials),
            "best_value": self.best_value,
            "best_params": self.best_params,
            "all_trials": [
                {
                    "number": trial.number,
                    "value": -trial.value if trial.value is not None else None,  # Convert to positive reward
                    "params": trial.params,
                    "state": trial.state.name
                }
                for trial in self.study.trials
            ],
            "timestamp": datetime.now().isoformat()
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"Saved optimization results to {output_path}")
