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


# ── Monkey-patch convenience properties on canonical User ────────────────────
# These run at import time (when base.py imports this module) and attach
# read-only properties to the canonical User class so that existing code
# doing `user.decision_level` continues to work without rewriting every
# call site. The properties read from the TMSUserExtension sibling table
# via the backref.
#
# WRITE operations (user.decision_level = X) must use the helper functions
# in app.helpers.user_helpers because they need session context to create
# the extension row if it doesn't exist.
#
# This pattern lives entirely in TMS — the canonical User in
# azirella-data-model doesn't know about it. SCP can do the same with
# its own _scp_decision_level property.

from azirella_data_model.tenant import User as _CanonicalUser


def _tms_decision_level_get(self):
    """Read decision_level from TMSUserExtension sibling table."""
    ext = getattr(self, "tms_extension", None)
    return ext.decision_level if ext else None


def _tms_decision_level_set(self, value):
    """Write decision_level to TMSUserExtension sibling table.

    Auto-creates the extension row if it doesn't exist. The new row
    is tracked by SQLAlchemy via the backref relationship — it'll be
    persisted when the session flushes.
    """
    ext = getattr(self, "tms_extension", None)
    if ext is None:
        ext = TMSUserExtension(user_id=self.id, decision_level=value)
        self.tms_extension = ext  # backref assignment — SQLAlchemy tracks it
    else:
        ext.decision_level = value


def _tms_default_config_id_get(self):
    """Read default_config_id from TMSUserExtension sibling table."""
    ext = getattr(self, "tms_extension", None)
    return ext.default_config_id if ext else None


def _tms_default_config_id_set(self, value):
    """Write default_config_id to TMSUserExtension sibling table."""
    ext = getattr(self, "tms_extension", None)
    if ext is None:
        ext = TMSUserExtension(user_id=self.id, default_config_id=value)
        self.tms_extension = ext
    else:
        ext.default_config_id = value


def _tms_explainability_level_override_get(self):
    """Read explainability_level_override from TMSUserExtension sibling table."""
    ext = getattr(self, "tms_extension", None)
    return ext.explainability_level_override if ext else None


_CanonicalUser.decision_level = property(_tms_decision_level_get, _tms_decision_level_set)
_CanonicalUser.default_config_id = property(_tms_default_config_id_get, _tms_default_config_id_set)
_CanonicalUser.explainability_level_override = property(_tms_explainability_level_override_get)
