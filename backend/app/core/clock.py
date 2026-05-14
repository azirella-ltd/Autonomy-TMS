"""TMS clock shim — re-exports canonical from Core.

The canonical tenant-aware virtual clock lives in
`azirella_data_model.tenant.clock` (promoted 2026-05-13 per §1.1.1 of
Core MIGRATION_REGISTER). Both SCP and TMS carried byte-identical
copies before promotion.

Why Core/tenant: every plane needs the same "what is today for this
tenant" answer — frozen demo dates, real production dates — and the
substrate sits on the tenants table.
"""
from azirella_data_model.tenant.clock import (  # noqa: F401
    _tenant_clock_cache,
    config_today,
    config_today_sync,
    invalidate_cache,
    resolve_tenant_from_config,
    resolve_tenant_from_config_sync,
    tenant_now,
    tenant_now_sync,
    tenant_today,
    tenant_today_sync,
)


__all__ = [
    "config_today",
    "config_today_sync",
    "invalidate_cache",
    "resolve_tenant_from_config",
    "resolve_tenant_from_config_sync",
    "tenant_now",
    "tenant_now_sync",
    "tenant_today",
    "tenant_today_sync",
]
