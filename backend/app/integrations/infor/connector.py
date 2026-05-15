"""SCP shim — canonical Infor connector in Core.

``InforConnector`` + ``InforConnectionConfig`` now live in
``azirella_integrations.erp.infor.connector`` (lifted 2026-05-15 per
MIGRATION_REGISTER §1.1.6). Byte-identical between SCP and TMS pre-lift.
"""
from azirella_integrations.erp.infor.connector import (  # noqa: F401
    InforConnector,
    InforConnectionConfig,
)


__all__ = ["InforConnector", "InforConnectionConfig"]
