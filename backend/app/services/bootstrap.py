"""Helpers to bootstrap a default tenant/scenario for developer convenience."""

from __future__ import annotations

import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from app.models.scenario import Scenario

# Aliases for backwards compatibility
Game = Scenario
from app.schemas.tenant import TenantCreate
from app.schemas.user import UserCreate

logger = logging.getLogger(__name__)

DEFAULT_TENANT_NAME = "Autonomy"
DEFAULT_TENANT_DESCRIPTION = "Default Autonomy tenant"
DEFAULT_TENANT_LOGO = "/autonomy_logo.svg"
DEFAULT_ADMIN_USERNAME = "groupadmin"
DEFAULT_ADMIN_EMAIL = "groupadmin@autonomy.ai"
DEFAULT_ADMIN_FULL_NAME = "Group Administrator"
DEFAULT_ADMIN_PASSWORD = os.getenv("AUTONOMY_DEFAULT_PASSWORD", "Autonomy@2025")

# Backward compatibility aliases
DEFAULT_CUSTOMER_NAME = DEFAULT_TENANT_NAME
DEFAULT_CUSTOMER_DESCRIPTION = DEFAULT_TENANT_DESCRIPTION
DEFAULT_CUSTOMER_LOGO = DEFAULT_TENANT_LOGO


def build_default_tenant_payload() -> TenantCreate:
    """Return the default Autonomy tenant payload used across the app."""
    return TenantCreate(
        name=DEFAULT_TENANT_NAME,
        description=DEFAULT_TENANT_DESCRIPTION,
        logo=DEFAULT_TENANT_LOGO,
        admin=UserCreate(
            username=DEFAULT_ADMIN_USERNAME,
            email=DEFAULT_ADMIN_EMAIL,
            password=DEFAULT_ADMIN_PASSWORD,
            full_name=DEFAULT_ADMIN_FULL_NAME,
            user_type="GROUP_ADMIN",
        ),
    )


# Backward compatibility alias
build_default_customer_payload = build_default_tenant_payload


def ensure_default_tenant_and_scenario(db: Session) -> Optional[Game]:
    """Ensure at least one scenario exists for developer-focused SQLite fallback."""
    existing_game = db.query(Game).first()
    if existing_game:
        return existing_game

    logger.info("Bootstrapping default tenant and scenario for local development")
    from .tenant_service import TenantService  # local import to avoid circular dependency

    service = TenantService(db)
    tenant = service.create_tenant(build_default_tenant_payload())
    db.refresh(tenant)
    return db.query(Game).first()


# Backward compatibility alias
ensure_default_customer_and_game = ensure_default_tenant_and_scenario
