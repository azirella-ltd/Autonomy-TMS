"""TMS heuristics — fallback implementations for HEURISTIC-tier responses.

Two sub-modules:

- :mod:`.cross_plane` — heuristics that answer cross-plane skill calls
  (e.g., from SCP/DP) when the tenant is at HEURISTIC tier per AD-12.
- (Future) :mod:`.internal` — self-fallback heuristics for when TMS's
  own TRMs / agents aren't ready (training failed, no checkpoint, etc.).
  This space is currently served by ``app/services/powell/tms_heuristic_library/``;
  we don't move it here in Phase 1 of the AD-12 migration.

See ``cross_plane/README.md`` for the AD-12 migration story.
"""
