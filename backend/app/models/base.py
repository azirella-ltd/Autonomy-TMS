"""SQLAlchemy Base — re-exports from canonical azirella-data-model.

Stage 3 Phase 3a: TMS now uses the canonical Base so that ALL models
(canonical re-exports + TMS-specific entities) register against the
same metadata. Cross-model relationships resolve because everything
is on one shared metadata object.

Previously TMS had its own Base via declarative_base(cls=CustomBase)
with a table_names dict for Beer Game legacy naming (Game→games,
Player→players, Round→rounds). That dict is removed; any model that
relied on it must have an explicit __tablename__ attribute.
"""

# THE canonical Base — all TMS models must inherit from this.
from azirella_data_model.base import Base  # noqa: F401

# Import canonical subpackages to register with Base metadata.
# Each subpackage is added here when its local model files are
# rewritten as re-export shims (to avoid metadata collisions).
# Phase 3a: tenant/ — adopted 2026-04-12
# Phase 3b: governance/ — adopted 2026-04-12
# Phase 3c: master/ — adopted 2026-04-12
import azirella_data_model.tenant  # noqa: F401
import azirella_data_model.governance  # noqa: F401
import azirella_data_model.master  # noqa: F401

# Import TMS-specific models to register them with the same Base metadata.
# These are the models that stay in TMS (not canonical).
from app.models.tms.user_extensions import TMSUserExtension  # noqa: F401
