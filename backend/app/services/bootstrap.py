"""Helpers to bootstrap a default customer/game for developer convenience."""

from __future__ import annotations

import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from app.models.scenario import Scenario

# Aliases for backwards compatibility
Game = Scenario
from app.schemas.customer import CustomerCreate
from app.schemas.user import UserCreate

logger = logging.getLogger(__name__)

DEFAULT_CUSTOMER_NAME = "Autonomy"
DEFAULT_CUSTOMER_DESCRIPTION = "Default Autonomy customer"
DEFAULT_CUSTOMER_LOGO = "/autonomy_logo.svg"
DEFAULT_ADMIN_USERNAME = "groupadmin"
DEFAULT_ADMIN_EMAIL = "groupadmin@autonomy.ai"
DEFAULT_ADMIN_FULL_NAME = "Group Administrator"
DEFAULT_ADMIN_PASSWORD = os.getenv("AUTONOMY_DEFAULT_PASSWORD", "Autonomy@2025")


def build_default_customer_payload() -> CustomerCreate:
    """Return the default Autonomy customer payload used across the app."""
    return CustomerCreate(
        name=DEFAULT_CUSTOMER_NAME,
        description=DEFAULT_CUSTOMER_DESCRIPTION,
        logo=DEFAULT_CUSTOMER_LOGO,
        admin=UserCreate(
            username=DEFAULT_ADMIN_USERNAME,
            email=DEFAULT_ADMIN_EMAIL,
            password=DEFAULT_ADMIN_PASSWORD,
            full_name=DEFAULT_ADMIN_FULL_NAME,
            user_type="GROUP_ADMIN",
        ),
    )


def ensure_default_customer_and_game(db: Session) -> Optional[Game]:
    """Ensure at least one game exists for developer-focused SQLite fallback."""
    existing_game = db.query(Game).first()
    if existing_game:
        return existing_game

    logger.info("Bootstrapping default customer and game for local development")
    from .customer_service import CustomerService  # local import to avoid circular dependency

    service = CustomerService(db)
    customer = service.create_customer(build_default_customer_payload())
    db.refresh(customer)
    return db.query(Game).first()
