"""TMSUserExtension — TMS-specific User fields as a sibling table.

The canonical User in azirella-data-model.tenant.user is minimal: identity,
authentication, lifecycle, tenant scope, span of control. App-specific role
enums (SCP's manufacturing roles, TMS's freight/carrier roles) live in sibling
tables keyed by user_id, not in the canonical User.

This module defines:
  - DecisionLevelEnum: TMS-specific decision role classification
  - TMSUserExtension: sibling table (1:1 with users) holding
    decision_level, default_config_id, explainability_level_override

Pattern: Option B (sibling table with backref), per the Q2 architectural
decision from 2026-04-11. The backref adds .tms_extension to the canonical
User at import time. Helper functions in app.helpers.user_helpers provide
null-safe access (get_decision_level(user), set_decision_level(user, ...)).

Do NOT add polymorphism to the canonical User. If this pattern doesn't
work, push back and redesign rather than polluting the canonical.
"""

from enum import Enum as PyEnum

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship, backref

from azirella_data_model.base import Base


class DecisionLevelEnum(str, PyEnum):
    """Decision level classification for TMS users.

    Determines landing page routing and navigation section visibility.
    Currently uses the same values as SCP (inherited from the fork);
    TMS-specific role names (e.g., CAPACITY_PROMISE_ANALYST) will be
    added in a future refactor aligned with Workstream A3 (navigation
    type extension).
    """
    SC_VP = "SC_VP"
    SOP_DIRECTOR = "SOP_DIRECTOR"
    MPS_MANAGER = "MPS_MANAGER"
    ALLOCATION_MANAGER = "ALLOCATION_MANAGER"
    ORDER_PROMISE_MANAGER = "ORDER_PROMISE_MANAGER"
    ATP_ANALYST = "ATP_ANALYST"
    REBALANCING_ANALYST = "REBALANCING_ANALYST"
    PO_ANALYST = "PO_ANALYST"
    ORDER_TRACKING_ANALYST = "ORDER_TRACKING_ANALYST"
    EXECUTIVE = "EXECUTIVE"
    DEMO_ALL = "DEMO_ALL"


class TMSUserExtension(Base):
    """TMS-specific User extensions as a sibling table.

    1:1 relationship with the canonical User via user_id FK.
    The backref adds .tms_extension to User at import time.
    """
    __tablename__ = "tms_user_extensions"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    decision_level = Column(
        SAEnum(DecisionLevelEnum, name="tms_decision_level_enum"),
        nullable=True,
    )
    default_config_id = Column(
        Integer,
        nullable=True,
        comment="FK to supply_chain_configs.id — TMS-specific default config for this user",
    )
    explainability_level_override = Column(
        String(20),
        nullable=True,
        comment="Powell explainability level override (e.g., 'detailed', 'summary')",
    )

    # Backref adds .tms_extension to the canonical User class at import time.
    # uselist=False because it's 1:1.
    user = relationship(
        "User",
        backref=backref("tms_extension", uselist=False, cascade="all, delete-orphan"),
    )
