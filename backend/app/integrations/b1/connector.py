"""SCP shim — canonical B1 connector in Core.

``B1Connector`` + ``B1ConnectionConfig`` now live in
``azirella_integrations.erp.b1.connector`` (lifted 2026-05-15 per
MIGRATION_REGISTER §1.1.5). Byte-identical between SCP and TMS pre-lift.
"""
from azirella_integrations.erp.b1.connector import (  # noqa: F401
    B1Connector,
    B1ConnectionConfig,
)


__all__ = ["B1Connector", "B1ConnectionConfig"]
