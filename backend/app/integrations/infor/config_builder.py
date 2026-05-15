"""SCP shim — canonical Infor config builder in Core.

``InforConfigBuilder`` + ``InforConfigBuildResult`` now live in
``azirella_integrations.erp.infor.config_builder`` (lifted 2026-05-15
per MIGRATION_REGISTER §1.1.6). SCP canonical (~17% diff vs TMS — SCP
fixed an orphan-vendor-Site anti-pattern that TMS still carries).
"""
from azirella_integrations.erp.infor.config_builder import (  # noqa: F401
    InforConfigBuilder,
    InforConfigBuildResult,
)


__all__ = ["InforConfigBuilder", "InforConfigBuildResult"]
