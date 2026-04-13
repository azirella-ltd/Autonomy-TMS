"""Context Engine dashboard helpers — re-export shim from Core.

The canonical implementations live in
`azirella_data_model.context_engine.dashboard`. This file re-exports
them so existing imports like
`from app.services.context_engine_dashboard import context_engine_envelope`
keep working unchanged.

See `azirella_data_model/context_engine/dashboard.py` for the contract.
"""

from azirella_data_model.context_engine import (
    context_engine_envelope,
    resolve_active_config_async,
    resolve_active_config_sync,
)

__all__ = [
    "context_engine_envelope",
    "resolve_active_config_async",
    "resolve_active_config_sync",
]
