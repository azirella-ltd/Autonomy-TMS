"""LaneFlowStepAdapter — RL trajectory façade around LaneFlowSimulator.

Parallel to Autonomy-Core's ``TwinStepAdapter``
(``packages/data-model/src/azirella_data_model/digital_twin/twin_interface.py``).
The Core adapter is currently SCP-shaped (its ``observe`` builds an
on-hand / in-transit / safety-stock observation). When Core slims
``TwinObservation`` into a generic base per TWIN_AND_ENVELOPES.md §9
bullet 3, this adapter migrates to inherit from the slimmed Core base
and the Core adapter becomes the SCP subclass.

Until then, lane-flow has its own adapter so a Core ``RolloutHarness``
can drive the TMS simulator with the same ``(observe, step, record)``
protocol it uses for SCP.

PR-1: skeleton only. The trajectory list, default reward, and harness
conversion ship here so PR-2 / PR-3 only have to fill in the simulator
hookup and the per-step BSC reward weights.
"""
from __future__ import annotations

from typing import Callable

from .lane_flow_simulator import LaneFlowSimulator
from .observations import (
    LaneFlowAction,
    LaneFlowObservation,
    LaneFlowReward,
    LaneFlowTransition,
)


class LaneFlowStepAdapter:
    """Wraps a ``LaneFlowSimulator`` and captures trajectories for RL.

    Usage (PR-3 onward):

        adapter = LaneFlowStepAdapter(simulator)
        observation = adapter.reset(scenario_seed=...)
        for _ in range(horizon):
            action = policy(observation)
            observation, reward, done, info = adapter.step(action)
            if done:
                break
        traj = adapter.trajectory  # list[LaneFlowTransition]
    """

    def __init__(
        self,
        simulator: LaneFlowSimulator,
        *,
        reward_fn: Callable[
            [LaneFlowObservation, LaneFlowAction, dict],
            LaneFlowReward,
        ] | None = None,
    ):
        self.simulator = simulator
        self.reward_fn = reward_fn  # PR-3 supplies a default BSC-shaped fn.
        self.trajectory: list[LaneFlowTransition] = []
        self._last_observation: LaneFlowObservation | None = None
        self._last_action: LaneFlowAction | None = None

    # ------------------------------------------------------------------

    def reset(self, *, scenario_seed: int) -> LaneFlowObservation:
        observation = self.simulator.reset(scenario_seed=scenario_seed)
        self.trajectory = []
        self._last_observation = observation
        self._last_action = None
        return observation

    def step(
        self,
        action: LaneFlowAction,
    ) -> tuple[LaneFlowObservation, LaneFlowReward, bool, dict]:
        if self._last_observation is None:
            raise RuntimeError(
                "LaneFlowStepAdapter.step called before reset()."
            )
        next_obs, reward, done, info = self.simulator.step(action)
        self.trajectory.append(
            LaneFlowTransition(
                observation=self._last_observation,
                action=action,
                reward=reward,
                next_observation=next_obs if not done else None,
                done=done,
                metadata=info,
            )
        )
        self._last_observation = next_obs
        self._last_action = action
        return next_obs, reward, done, info


__all__ = ["LaneFlowStepAdapter"]
