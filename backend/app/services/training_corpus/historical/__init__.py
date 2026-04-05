"""Historical Transaction Extractor — primary training data stream.

Extracts (state, action, outcome) triples from ERP transaction tables to serve
as behavioral-cloning labels for the 12 TRMs. See
docs/internal/architecture/UNIFIED_TRAINING_CORPUS.md §2a.
"""

from .base import (
    BaseHistoricalExtractor,
    ExtractorCoverage,
    HistoricalExtractionSummary,
    SampleRecord,
)
from .orchestrator import HistoricalExtractionOrchestrator

__all__ = [
    "BaseHistoricalExtractor",
    "ExtractorCoverage",
    "HistoricalExtractionSummary",
    "HistoricalExtractionOrchestrator",
    "SampleRecord",
]
