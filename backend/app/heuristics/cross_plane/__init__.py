"""TMS cross-plane heuristics — direct-call module for AD-12 HEURISTIC tier.

Public API
----------

Skill handlers (one per cross-plane TMS skill consumers expect):

- :func:`estimate_lane_eta`
- :func:`evaluate_consolidation`
- :func:`recommend_carrier`

Plus the registry and write-refusal helpers Phase 2's dispatcher uses:

- :data:`HEURISTIC_HANDLERS` — ``{skill_id: handler}`` for read skills.
- :data:`HEURISTIC_WRITE_SKILLS` — write-side skill IDs to refuse.
- :func:`refuse_write` — raises :class:`HeuristicWriteRefused`.
- :data:`HEURISTIC_PRODUCER_SIGNATURE` — base producer signature.

Plus the warning-stamp helper for any handler outside the registry
that wants to participate in the four-place warning regime:

- :func:`stamp_heuristic_response`

See ``README.md`` in this directory for the AD-12 migration story.
"""
from .handlers import (
    HEURISTIC_HANDLERS,
    HEURISTIC_PRODUCER_SIGNATURE,
    HEURISTIC_WRITE_SKILLS,
    HeuristicWriteRefused,
    estimate_lane_eta,
    evaluate_consolidation,
    recommend_carrier,
    refuse_write,
)
from .warning import (
    heuristic_warning_text,
    stamp_heuristic_response,
)

__all__ = [
    "HEURISTIC_HANDLERS",
    "HEURISTIC_PRODUCER_SIGNATURE",
    "HEURISTIC_WRITE_SKILLS",
    "HeuristicWriteRefused",
    "estimate_lane_eta",
    "evaluate_consolidation",
    "heuristic_warning_text",
    "recommend_carrier",
    "refuse_write",
    "stamp_heuristic_response",
]
