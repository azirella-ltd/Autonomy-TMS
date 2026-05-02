"""TMS's A2A surface — Agent Card + skill handlers.

§3.32 Phase 4. TMS publishes an Agent Card at
``/.well-known/agent.json`` and exposes its dispatch capabilities
as A2A skills under ``/a2a/``.

Phase 4 minimum viable skill set covering inter-plane traffic:

- ``transport.load.evaluate_consolidation`` — score whether a
  group of shipments should be consolidated into one load.
- ``transport.carrier.recommend`` — recommend a carrier for a
  given load.
- ``transport.lane.estimate_eta`` — return current ETA estimate
  + conformal band for a (lane, departure_date) pair.

Future skills land per concrete cross-plane caller need.
"""
from .skills import build_agent_card, get_skill_handlers, mount

__all__ = ["build_agent_card", "get_skill_handlers", "mount"]
