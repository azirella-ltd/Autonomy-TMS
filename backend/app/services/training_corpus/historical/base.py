"""Base contract for historical transaction extractors.

Each per-TRM extractor reconstructs (state, action, outcome) triples from the
tenant's real ERP history. Samples are streamed to the caller, which persists
them as training_corpus rows with origin='historical'.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class SampleRecord:
    """One (state, action, outcome) triple from history.

    Mirrors the Layer-1 schema of the simulation pipeline so both streams
    persist identically into training_corpus.sample_data.
    """
    trm_type: str
    product_id: str
    site_id: str
    decision_at: datetime
    state_features: Dict[str, Any]
    action: Dict[str, Any]
    outcome: Dict[str, Any]
    reward_components: Dict[str, Any]
    aggregate_reward: float   # 0..1, used for BC label quality weighting
    label_weight: float       # 0..1, quality-derived multiplier on training weight


@dataclass
class ExtractorCoverage:
    """Per-TRM coverage summary from a historical extraction run."""
    trm_type: str
    sample_count: int
    earliest: Optional[datetime]
    latest: Optional[datetime]
    distinct_sites: int
    distinct_products: int
    avg_reward: float
    label_weight_distribution: Dict[str, int]  # e.g., {"good": 412, "mixed": 108, "poor": 37}
    skipped_reason: Optional[str] = None       # Case A (topology) or Case C (no data)


@dataclass
class HistoricalExtractionSummary:
    """Orchestrator-level summary returned to the provisioning step."""
    tenant_id: int
    config_id: int
    total_samples: int
    coverage: Dict[str, ExtractorCoverage] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    thin_trms: List[str] = field(default_factory=list)  # coverage < MIN_COVERAGE

    def is_thin(self, trm_type: str, min_samples: int) -> bool:
        cov = self.coverage.get(trm_type)
        return cov is None or cov.sample_count < min_samples


class BaseHistoricalExtractor(ABC):
    """Contract every per-TRM historical extractor must implement."""

    trm_type: str = ""

    def __init__(self, db: AsyncSession):
        self.db = db

    @abstractmethod
    async def extract(
        self,
        tenant_id: int,
        config_id: int,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[SampleRecord]:
        """Yield (state, action, outcome) sample records from real history.

        Args:
            tenant_id: Tenant scope.
            config_id: Config scope.
            since: If provided, only extract decisions made after this timestamp
                (for incremental refresh). Default: all available history.
        """
        if False:
            yield  # make this an async generator for the ABC signature
