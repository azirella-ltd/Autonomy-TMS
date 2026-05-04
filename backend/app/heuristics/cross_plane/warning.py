"""Four-place warning regime for HEURISTIC-tier responses.

Ported from ``azirella-stub-common.response`` into TMS as part of
the AD-12 migration (Phase 1). When this app's request handler
runs in HEURISTIC tier for a given tenant — i.e. the customer
hasn't licensed full TMS — every response from the cross-plane
heuristics MUST carry these markers so consumer planes know they're
consuming heuristic data, not real planning.

Four canonical markers in every response:

1. ``producer_tier="HEURISTIC"`` (the AD-12 tier classification;
   formerly ``STUB`` under §3.32a).
2. ``producer_signature`` — app + skill + version, e.g.
   ``"autonomy-tms:lane.estimate_eta:heuristic:v0.1.0"``.
3. ``heuristic_warning`` — canonical audit-grep-friendly warning
   text. Same head phrase (``AZIRELLA-STUB-WARNING``) as the
   pre-AD-12 stub package so existing log pipelines, dashboards,
   and runbooks keep matching.
4. ``heuristic_plane`` — namespaced source identifier
   (``autonomy-tms-heuristics``).

Plus the structural propagation: every ``ConformalBand`` and
``OutcomeEvent`` returned by these handlers carries
``producer_tier=ProducerTier.HEURISTIC``.
"""
from __future__ import annotations

from typing import Any, Dict


# Canonical warning phrase. Stays stable across the AD-12 migration
# so log search pipelines, dashboards, and customer-support runbooks
# can keep matching on the substring "AZIRELLA-STUB-WARNING".
_CANONICAL_WARNING_HEAD = "AZIRELLA-STUB-WARNING"


def heuristic_warning_text(*, skill_id: str) -> str:
    """Canonical heuristic-warning string for TMS cross-plane skills."""
    return (
        f"{_CANONICAL_WARNING_HEAD}: response from autonomy-tms heuristics "
        f"(producer_tier=HEURISTIC) for skill={skill_id!r}. Values are "
        "conservative defaults synthesized in lieu of a real planning "
        "agent. Consumer planes MUST treat outputs as low-confidence: "
        "widen ConformalBand coverage, discount BSC reward weights, "
        "never auto-execute decisions derived from HEURISTIC-tier data "
        "without a human-in-the-loop."
    )


def stamp_heuristic_response(
    payload: Dict[str, Any],
    *,
    skill_id: str,
    producer_signature: str,
) -> Dict[str, Any]:
    """Inject the four canonical heuristic markers into a response.

    Handlers build their domain payload, then call this helper once at
    the return boundary. Existing keys are preserved unless they
    collide with the four reserved names — in which case heuristic-side
    values win, because the four markers are the audit contract.
    """
    out = dict(payload)
    out["producer_tier"] = "HEURISTIC"
    out["producer_signature"] = producer_signature
    out["heuristic_warning"] = heuristic_warning_text(skill_id=skill_id)
    out["heuristic_plane"] = "autonomy-tms-heuristics"
    return out
