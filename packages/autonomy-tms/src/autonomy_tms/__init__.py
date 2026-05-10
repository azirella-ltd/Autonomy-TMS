"""autonomy-tms — TMS plane package (AD-13).

Wrapper around ``Autonomy-TMS/backend/`` that exposes its FastAPI
router via the ``autonomy_app.plane_routers`` entry point. Same
two-path sys.path strategy as the DP and SCP wrappers (see
``Autonomy-DP/packages/autonomy-dp/src/autonomy_dp/__init__.py``).
"""
from __future__ import annotations

import os
import sys

# Mutually exclusive: prefer the unified-backend layout when present.
_UNIFIED_BACKEND_DIR = "/app/planes/tms"
_HERE = os.path.dirname(os.path.abspath(__file__))
_LEGACY_BACKEND_DIR = os.path.normpath(
    os.path.join(_HERE, "..", "..", "..", "..", "backend")
)

if os.path.isdir(_UNIFIED_BACKEND_DIR):
    if _UNIFIED_BACKEND_DIR not in sys.path:
        sys.path.insert(0, _UNIFIED_BACKEND_DIR)
elif os.path.isdir(_LEGACY_BACKEND_DIR):
    if _LEGACY_BACKEND_DIR not in sys.path:
        sys.path.insert(0, _LEGACY_BACKEND_DIR)


__version__ = "0.1.0"
