"""User extension helpers — null-safe access to TMS-specific User fields.

The canonical User (from azirella-data-model) does not have decision_level,
default_config_id, or explainability_level_override. These live in the
TMSUserExtension sibling table, accessed via the .tms_extension backref.

These helpers provide null-safe read/write access so call sites don't need
to handle the "extension row might not exist" case inline.

Usage:
    from app.helpers.user_helpers import get_decision_level, set_decision_level

    level = get_decision_level(user)  # returns DecisionLevelEnum or None
    set_decision_level(user, DecisionLevelEnum.MPS_MANAGER, session)
"""

from typing import Optional, TYPE_CHECKING

from app.models.tms.user_extensions import TMSUserExtension, DecisionLevelEnum

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from azirella_data_model.tenant import User


def get_decision_level(user: "User") -> Optional[DecisionLevelEnum]:
    """Get the user's TMS decision level, or None if no extension exists."""
    ext = getattr(user, "tms_extension", None)
    return ext.decision_level if ext else None


def set_decision_level(
    user: "User", level: Optional[DecisionLevelEnum], session: "Session"
) -> None:
    """Set the user's TMS decision level, creating the extension row if needed."""
    ext = getattr(user, "tms_extension", None)
    if ext is None:
        ext = TMSUserExtension(user_id=user.id, decision_level=level)
        session.add(ext)
    else:
        ext.decision_level = level


def get_default_config_id(user: "User") -> Optional[int]:
    """Get the user's default supply chain config ID, or None."""
    ext = getattr(user, "tms_extension", None)
    return ext.default_config_id if ext else None


def set_default_config_id(
    user: "User", config_id: Optional[int], session: "Session"
) -> None:
    """Set the user's default config ID, creating the extension row if needed."""
    ext = getattr(user, "tms_extension", None)
    if ext is None:
        ext = TMSUserExtension(user_id=user.id, default_config_id=config_id)
        session.add(ext)
    else:
        ext.default_config_id = config_id


def get_explainability_override(user: "User") -> Optional[str]:
    """Get the user's explainability level override, or None."""
    ext = getattr(user, "tms_extension", None)
    return ext.explainability_level_override if ext else None
