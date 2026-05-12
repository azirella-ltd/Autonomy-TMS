"""TMS-side concrete :class:`TwinCounterfactualReplayer` (§3.72 / §3.26 Phase 1).

Composed with Core's :class:`TwinReplayCounterfactualStrategy` and
:class:`OutcomeCollectorService` to produce structural counterfactuals
for TMS decisions — what would the network have done under the agent's
recommendation, replayed through the digital twin.

Phase-1 status
--------------

The TMS replayer is **a documented stub** today: ``replay()`` returns
``None`` for every decision, which causes Core's strategy to propagate
``None`` and the collector to fall through to
:class:`NaiveCounterfactualStrategy` for TMS rows. The naive path is
the same per-decision delta the legacy ``outcome_collector`` produced
before §3.64.

Why a stub rather than a real implementation:

1. :class:`LaneFlowSimulator`
   (``app.services.digital_twin.lane_flow_simulator``) is an RL
   training surface — it exposes ``reset(scenario_seed=…)`` +
   ``step(LaneFlowAction)`` aimed at RL rollout, not "snapshot the
   current network state and replay forward from here." It is not
   constructed from any production call site today.
2. The ``LaneFlowAction`` schema (carrier_id, equipment_kind, rate
   offered, …) doesn't have a clean inverse from a ``SiteAgentDecision``
   payload. Mapping ``po_timing`` / ``atp_exception`` decisions onto
   per-bucket dispatch actions needs a design pass that lands with the
   TMS RL training loop, not before.
3. Until ``LaneFlowSimulator`` is wired into a production factory
   (parallel to SCP's ``load_topology`` path), there is no honest
   "snapshot" surface for the replayer to read from.

Phase 2 plan — to be implemented when the TMS twin gets a production
caller:

* Build a ``LaneFlowSimulatorFactory.from_decision_context(decision)``
  that loads a snapshot of the lane / carrier / equipment state at
  ``decision.timestamp`` from operational tables, constructs a
  :class:`LanePhysicsParams` + :class:`ShipmentGenerator` for the lane,
  and returns a simulator pinned to that anchor.
* Map ``po_timing`` decisions onto a substituted dispatch bucket
  (the agent's recommended ship date → bucket offset → action
  installed at that bucket).
* Run ``horizon_steps`` ``step(action)`` calls in
  ``TwinMode.PLAN_PRODUCTION`` (no demand / on-time stochasticity).
* Aggregate the resulting OutcomeEvent stream into the outcome shape
  Core's ``RewardCalculator`` scores for ``po_timing`` /
  ``atp_exception``.

Keeping the file in place as an honest stub means: (a) the
construction site in ``relearning_jobs`` doesn't have to be re-wired
when Phase 2 lands — only the ``replay()`` body changes; (b) anybody
auditing "where's the TMS twin replayer?" finds it immediately and
sees the design constraints rather than silence.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from azirella_data_model.governance.causal import TwinCounterfactualReplayer  # noqa: F401 — re-exported for type-checker visibility
from azirella_data_model.powell.powell_decision import SiteAgentDecision

log = logging.getLogger(__name__)


class TmsTwinReplayer:
    """Stub TMS replayer satisfying :class:`TwinCounterfactualReplayer`.

    Returns ``None`` for every decision today. Construction kwargs match
    the eventual Phase-2 shape so wiring in ``relearning_jobs.py``
    doesn't need to change when the body is implemented.
    """

    name = "tms_lane_flow_replayer"

    def __init__(
        self,
        *,
        tenant_id: int,
        config_id: int,
        db_session_factory: Any,
        horizon_buckets_default: int = 30,
    ) -> None:
        self.tenant_id = int(tenant_id)
        self.config_id = int(config_id)
        self.db_session_factory = db_session_factory
        self.horizon_buckets_default = int(horizon_buckets_default)

    def replay(
        self,
        *,
        decision: SiteAgentDecision,
        actual_outcome: Dict[str, Any],
        plane_inputs: Dict[str, Any],
        horizon_steps: int = 30,
    ) -> Optional[Dict[str, Any]]:
        log.debug(
            "TmsTwinReplayer: Phase-1 stub for decision %s "
            "(decision_type=%s); returning None so collector falls "
            "through to NaiveCounterfactualStrategy.",
            decision.decision_id, decision.decision_type,
        )
        return None
