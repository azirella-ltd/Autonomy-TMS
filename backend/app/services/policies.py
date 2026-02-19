"""Order policies for the Beer Game engine.

This module implements a tiny policy abstraction that can be plugged into the
Beer Game simulation engine.  Policies consume a dictionary of observations for
the current node and return the order quantity that should be placed upstream
for the current tick.

Two policies are provided:

* :class:`NaiveEchoPolicy` – echoes the order that arrived from the downstream
  partner in the previous tick.  This matches the classic "naïve" benchmark in
  which each role simply replaces what was requested from them.
* :class:`PIDPolicy` – a lightweight proportional–integral–derivative controller that tries
  to keep the inventory position close to a base-stock target.  The controller
  operates on the inventory position (on-hand + pipeline − backlog), which is
  the standard control signal for the Beer Game.

The policies expose a very small state interface so that their internal state
can be serialised along with the engine state between requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


class OrderPolicy:
    """Base interface for order policies."""

    def order(self, obs: Dict[str, Any]) -> int:
        """Return the order quantity for the current period."""

    # The default implementations below make the policy stateless.  Policies
    # that maintain internal state (e.g. the PID controller) override the
    # methods to expose their state so that the engine can persist it.

    def get_state(self) -> Dict[str, Any]:
        """Return a serialisable snapshot of the policy state."""
        return {}

    def set_state(self, state: Optional[Dict[str, Any]]) -> None:
        """Restore the policy state from :func:`get_state`."""
        # Stateless by default – nothing to restore.
        _ = state


class NaiveEchoPolicy(OrderPolicy):
    """Simple base-stock heuristic mirroring the classic teaching version of the Beer Game.

    The controller uses a one-step demand estimate (the last incoming order) and
    tops up inventory to the configured base-stock level while clearing any
    backlog:

        order_qty = backlog + incoming + target_inventory - current_position
    """

    def order(self, obs: Dict[str, Any]) -> int:
        def _safe_int(value: Any, default: int = 0) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        backlog = max(0, _safe_int(obs.get("backlog", 0)))
        incoming = max(0, _safe_int(obs.get("last_incoming_order", 0)))

        target_inventory = obs.get("target_inventory")
        if target_inventory is None:
            target_inventory = obs.get("base_stock", 0)
        target_inventory = _safe_int(target_inventory, 0)

        if "inventory_position" in obs:
            current_position = _safe_int(obs.get("inventory_position"), 0)
        else:
            inventory = _safe_int(obs.get("inventory", 0))
            pipeline = _safe_int(obs.get("pipeline_on_order", 0))
            current_position = inventory + pipeline - backlog

        replenish_delta = max(0, target_inventory - current_position)
        quantity = backlog + incoming + replenish_delta
        return max(0, quantity)


class FixedOrderPolicy(OrderPolicy):
    """Return a predetermined order quantity supplied by external players."""

    def __init__(self, quantity: int = 0) -> None:
        self.quantity = max(0, int(quantity))

    def order(self, obs: Dict[str, Any]) -> int:  # noqa: ARG002 - policy ignores observation
        return self.quantity

    def set_quantity(self, quantity: int) -> None:
        """Update the scripted order quantity in-place."""

        self.quantity = max(0, int(quantity))


@dataclass
class PIDState:
    integral_error: float = 0.0
    previous_error: Optional[float] = None


class PIDPolicy(OrderPolicy):
    """Simple PID controller operating on inventory position."""

    def __init__(
        self,
        base_stock: int,
        kp: float = 0.6,
        ki: float = 0.2,
        kd: float = 0.05,
        clamp_min: int = 0,
        clamp_max: Optional[int] = None,
    ) -> None:
        self.base_stock = int(base_stock)
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.clamp_min = int(clamp_min)
        self.clamp_max = None if clamp_max is None else int(clamp_max)
        self.state = PIDState()

    def order(self, obs: Dict[str, Any]) -> int:
        on_hand = int(obs.get("inventory", 0))
        backlog = int(obs.get("backlog", 0))
        pipeline = int(obs.get("pipeline_on_order", 0))
        demand_anchor = int(obs.get("last_incoming_order", 0))

        inv_position = on_hand + pipeline - backlog
        error = self.base_stock - inv_position
        self.state.integral_error += error
        derivative = 0.0
        if self.state.previous_error is not None:
            derivative = error - self.state.previous_error
        self.state.previous_error = error

        control = (
            self.kp * error
            + self.ki * self.state.integral_error
            + self.kd * derivative
        )
        quantity = max(0, int(round(demand_anchor + control)))

        if self.clamp_max is not None:
            quantity = max(self.clamp_min, min(quantity, self.clamp_max))
        else:
            quantity = max(self.clamp_min, quantity)
        return quantity

    def get_state(self) -> Dict[str, Any]:
        return {
            "integral_error": self.state.integral_error,
            "previous_error": self.state.previous_error,
        }

    def set_state(self, state: Optional[Dict[str, Any]]) -> None:
        if not state:
            self.state = PIDState()
            return
        try:
            self.state.integral_error = float(state.get("integral_error", 0.0))
        except (TypeError, ValueError):
            self.state.integral_error = 0.0
        try:
            prev_error = state.get("previous_error")
            self.state.previous_error = None if prev_error is None else float(prev_error)
        except (TypeError, ValueError):
            self.state.previous_error = None
