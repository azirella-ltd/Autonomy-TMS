"""Exceptions for the Unified Training Corpus pipeline.

Maps to the failure policy defined in
docs/internal/architecture/UNIFIED_TRAINING_CORPUS.md §6b:

- Case A (out of topology) -> no exception, handled by skip
- Case B (transient DB/infra) -> TransientCorpusError (pause + resume)
- Case C (missing master data for in-scope TRM) -> MissingMasterDataError (hard fail)
"""


class CorpusBuildError(Exception):
    """Base class for corpus build errors."""


class MissingMasterDataError(CorpusBuildError):
    """Required master data is absent for an in-scope TRM (Case C).

    Raised when a site is topologically valid for a TRM but lacks the
    master data the deterministic engine needs (e.g., a manufacturer
    with no routings cannot generate MO training samples).

    The tenant admin must fix master data and re-provision. SOC II:
    this error must be surfaced, never swallowed.
    """

    def __init__(self, site_id: str, trm_type: str, missing: str):
        self.site_id = site_id
        self.trm_type = trm_type
        self.missing = missing
        super().__init__(
            f"Site {site_id} is in-scope for {trm_type} but is missing "
            f"required master data: {missing}. Fix master data and re-provision."
        )


class TransientCorpusError(CorpusBuildError):
    """Transient infrastructure failure during corpus build (Case B).

    Raised when the underlying DB is unreachable (connection drop, pool
    exhaustion, deadlock, network blip). The caller should checkpoint
    progress, pause with a tenant-admin-visible message, and resume from
    the last committed scenario once the DB is reachable again.
    """

    def __init__(self, underlying: Exception, last_scenario_completed: int):
        self.underlying = underlying
        self.last_scenario_completed = last_scenario_completed
        super().__init__(
            f"Transient DB failure after scenario {last_scenario_completed}: "
            f"{type(underlying).__name__}: {underlying}"
        )
