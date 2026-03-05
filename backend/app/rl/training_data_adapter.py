"""
Training Data Adapter - SC Compliance Layer

This module provides adapters to make existing training data generators
SC compliant while maintaining backward compatibility with simulation schema.

Usage:
    # Wrap existing generator with SC adapter
    from app.rl.training_data_adapter import SCAdapter

    adapter = SCAdapter(use_sc_fields=True)

    # Generate training data (automatically uses SC fields)
    training_data = adapter.generate_training_sample(...)

    # Convert between schemas
    sc_state = adapter.to_aws_sc(simulation_state)
    simulation_state = adapter.to_simulation(sc_state)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import asdict

from .config import SimulationParams
from .sc_config import (
    SupplyChainParams,
    SimulationParamsV2,
    simulation_to_sc_state,
    sc_to_simulation_state,
    get_sc_node_features,
    SIMULATION_TO_AWS_SC_MAP,
    AWS_SC_TO_SIMULATION_MAP,
    AWS_SC_NODE_FEATURES,
    SIMULATION_COMPATIBLE_FEATURES,
    SiteType,
    SourceType,
)


class TrainingDataAdapter:
    """
    Base adapter for converting training data between simulation and SC schemas.

    This adapter wraps existing training data generators and provides
    transparent schema conversion based on configuration.
    """

    def __init__(
        self,
        use_sc_fields: bool = True,
        backward_compatible: bool = True,
    ):
        """
        Initialize adapter.

        Args:
            use_sc_fields: If True, use SC field names in generated data
            backward_compatible: If True, include simulation fields for compatibility
        """
        self.use_sc_fields = use_sc_fields
        self.backward_compatible = backward_compatible

    def convert_params(
        self,
        params: Union[SimulationParams, SimulationParamsV2, Dict],
    ) -> SimulationParamsV2:
        """
        Convert parameters to SC-compliant format.

        Args:
            params: Input parameters (any format)

        Returns:
            SimulationParamsV2 with SC fields
        """
        if isinstance(params, SimulationParamsV2):
            return params
        elif isinstance(params, SimulationParams):
            # Convert legacy SimulationParams to V2
            return SimulationParamsV2(
                on_hand_qty=params.init_inventory,
                backorder_qty=0.0,
                in_transit_qty=0.0,
                lead_time_days=params.order_leadtime,
                holding_cost_per_unit=params.holding_cost,
                backlog_cost_per_unit=params.backlog_cost,
                max_order_qty=params.max_order,
            )
        elif isinstance(params, dict):
            # Check if dict has SC or simulation fields
            if "on_hand_qty" in params:
                # SC format
                return SimulationParamsV2(**params)
            else:
                # simulation format
                return SimulationParamsV2.from_simulation_dict(params)
        else:
            raise TypeError(f"Unsupported params type: {type(params)}")

    def convert_state(
        self,
        state: Dict,
        to_schema: str = "aws_sc",
    ) -> Dict:
        """
        Convert state dictionary between schemas.

        Args:
            state: State dictionary
            to_schema: Target schema ("aws_sc" or "simulation")

        Returns:
            Converted state dictionary
        """
        if to_schema == "aws_sc":
            # Check if already SC format
            if "on_hand_qty" in state:
                return state
            else:
                return simulation_to_sc_state(state)
        elif to_schema == "simulation":
            # Check if already simulation format
            if "inventory" in state:
                return state
            else:
                return sc_to_simulation_state(state)
        else:
            raise ValueError(f"Unknown schema: {to_schema}")

    def get_feature_names(self) -> List[str]:
        """
        Get feature names based on current configuration.

        Returns:
            List of feature names
        """
        if self.use_sc_fields:
            if self.backward_compatible:
                return AWS_SC_NODE_FEATURES
            else:
                return SIMULATION_COMPATIBLE_FEATURES
        else:
            # Legacy simulation features
            from .config import NODE_FEATURES
            return NODE_FEATURES


class SCAdapter(TrainingDataAdapter):
    """
    Supply Chain Compliance Adapter.

    This adapter ensures all training data uses SC field names
    while providing backward compatibility with simulation agents.

    Example:
        ```python
        adapter = SCAdapter(use_sc_fields=True)

        # Generate training sample with SC fields
        sample = adapter.wrap_training_sample(
            site_id="retailer_001",
            item_id="cases",
            inventory=12,
            backlog=0,
            pipeline=8
        )

        # sample now contains:
        # {
        #     "site_id": "retailer_001",
        #     "item_id": "cases",
        #     "on_hand_qty": 12.0,    # SC field
        #     "backorder_qty": 0.0,   # SC field
        #     "in_transit_qty": 8.0,  # SC field
        #     "inventory": 12,        # Legacy field (if backward_compatible=True)
        #     "backlog": 0,
        #     "pipeline": 8
        # }
        ```
    """

    def wrap_training_sample(
        self,
        site_id: Optional[str] = None,
        item_id: Optional[str] = None,
        role: Optional[str] = None,
        position: Optional[int] = None,
        **kwargs,
    ) -> Dict:
        """
        Wrap training sample with SC fields.

        This method takes simulation-style keyword arguments and
        adds SC-compliant fields.

        Args:
            site_id: Site identifier (SC)
            item_id: Item identifier (SC)
            role: simulation role (for backward compat)
            position: simulation position (for backward compat)
            **kwargs: State fields (simulation or SC names)

        Returns:
            Dictionary with SC fields (and optionally simulation fields)
        """
        # Start with input kwargs
        sample = dict(kwargs)

        # Convert simulation fields to SC
        if self.use_sc_fields:
            sc_state = {}

            # Map known simulation fields
            for bg_field, aws_field in SIMULATION_TO_AWS_SC_MAP.items():
                if bg_field in sample:
                    sc_state[aws_field] = sample[bg_field]

            # Add SC fields to sample
            sample.update(sc_state)

        # Add identifiers
        if site_id:
            sample["site_id"] = site_id
        elif role:
            sample["site_id"] = f"{role}_001"

        if item_id:
            sample["item_id"] = item_id
        else:
            sample.setdefault("item_id", "item_001")

        # Add role/position for backward compat
        if self.backward_compatible:
            if role:
                sample["role"] = role
            if position is not None:
                sample["position"] = position

        return sample

    def wrap_training_batch(
        self,
        batch: Dict[str, np.ndarray],
    ) -> Dict[str, np.ndarray]:
        """
        Wrap training batch with SC field names.

        Args:
            batch: Training batch with simulation field names

        Returns:
            Training batch with SC field names added
        """
        if not self.use_sc_fields:
            return batch

        wrapped = dict(batch)

        # Map array fields
        for bg_field, aws_field in SIMULATION_TO_AWS_SC_MAP.items():
            if bg_field in batch and aws_field not in wrapped:
                wrapped[aws_field] = batch[bg_field]

        return wrapped


class RLEnvAdapter(SCAdapter):
    """
    Adapter for RL environment with SC compliance.

    This adapter wraps SimulationRLEnv to use SC field names
    in observations and state representations.

    Example:
        ```python
        from app.agents.rl_agent import SimulationRLEnv
        from app.rl.training_data_adapter import RLEnvAdapter

        adapter = RLEnvAdapter(use_sc_fields=True)

        # Wrap environment
        env = SimulationRLEnv(...)
        env = adapter.wrap_env(env)

        # Observations now use SC field names
        obs = env.reset()
        # obs[0] = on_hand_qty (was inventory)
        # obs[1] = backorder_qty (was backlog)
        # obs[2] = in_transit_qty[0] (was pipeline_shipments[0])
        ```
    """

    def wrap_env(self, env):
        """
        Wrap RL environment with SC field adapter.

        Args:
            env: SimulationRLEnv instance

        Returns:
            Wrapped environment with SC observations
        """
        # Store original methods
        original_get_obs = env._get_observation
        original_reset = env.reset

        def sc_get_observation():
            """Get observation with SC field semantics."""
            obs = original_get_obs()

            # obs[0]: inventory -> on_hand_qty
            # obs[1]: backlog -> backorder_qty
            # obs[2]: pipeline[0] -> in_transit_qty[0]
            # obs[3]: pipeline[1] -> in_transit_qty[1]
            # obs[4]: incoming_order -> demand_qty
            # obs[5]: last_order -> order_qty
            # obs[6]: round_norm
            # obs[7]: cost_norm

            # Observation values are the same, only semantic meaning changes
            return obs

        def sc_reset(seed=None, options=None):
            """Reset with SC state."""
            obs, info = original_reset(seed, options)

            # Add SC field metadata to info
            if self.use_sc_fields:
                info["observation_schema"] = "aws_sc"
                info["observation_fields"] = [
                    "on_hand_qty",
                    "backorder_qty",
                    "in_transit_qty_0",
                    "in_transit_qty_1",
                    "demand_qty",
                    "order_qty",
                    "round_normalized",
                    "cost_normalized",
                ]

            return obs, info

        # Monkey-patch methods
        env._get_observation = sc_get_observation
        env.reset = sc_reset

        return env
