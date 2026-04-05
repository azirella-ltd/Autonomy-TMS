"""Historical extractor for subcontracting TRM.

No dedicated `subcontracting_order` table is present in the schema we have;
if it existed we would pull from it. For now this extractor emits zero
samples and reports thin coverage so the orchestrator knows to let the
simulation stream (or none at all for DC-only tenants) handle this TRM.
"""

import logging
from typing import AsyncIterator

from .base import BaseHistoricalExtractor, SampleRecord

logger = logging.getLogger(__name__)


class SubcontractingHistoricalExtractor(BaseHistoricalExtractor):
    trm_type = "subcontracting"

    async def extract(
        self, tenant_id: int, config_id: int, since=None,
    ) -> AsyncIterator[SampleRecord]:
        logger.info(
            "SubcontractingHistoricalExtractor: no subcontracting_order table — "
            "returning 0 samples (simulation stream will cover this TRM if needed)"
        )
        return
        yield  # pragma: no cover  (async generator marker)
