"""SCP shim — canonical B1 config builder in Core.

``B1ConfigBuilder`` + ``B1ConfigBuildResult`` now live in
``azirella_integrations.erp.b1.config_builder`` (lifted 2026-05-15
per MIGRATION_REGISTER §1.1.5). SCP-superset canonical (~2% diff vs TMS).
"""
from azirella_integrations.erp.b1.config_builder import (  # noqa: F401
    B1ConfigBuilder,
    B1ConfigBuildResult,
)


__all__ = ["B1ConfigBuilder", "B1ConfigBuildResult"]
