"""TMS extraction/injection adapter — re-export shim from canonical package.

The canonical ABC and contract dataclasses now live in the
`azirella-integrations` package (`azirella_integrations.base.tms_adapter`).
This file re-exports them so existing imports like
`from app.integrations.core.tms_adapter import TMSExtractionAdapter`
keep working unchanged while the actual definition is shared with SCP
and any future Autonomy product.

Same shim pattern as tenant/master/governance/powell/context_engine.

See `Autonomy-TMS/docs/internal/plans/TMS_ERP_INTEGRATION.md` and
`Autonomy-Core/docs/INTEGRATION_ARCHITECTURE.md` for the architecture.
"""

from azirella_integrations.base.tms_adapter import (
    ConnectionConfig,
    ExtractionMode,
    ExtractionResult,
    InjectionResult,
    TMSExtractionAdapter,
)

__all__ = [
    "ConnectionConfig",
    "ExtractionMode",
    "ExtractionResult",
    "InjectionResult",
    "TMSExtractionAdapter",
]
