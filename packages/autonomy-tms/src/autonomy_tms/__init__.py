"""autonomy-tms — TMS plane package (AD-13).

Wrapper around ``Autonomy-TMS/backend/`` that exposes its FastAPI
router via the ``autonomy_app.plane_routers`` entry point. The
unified backend (``Autonomy-Core/apps/backend/``) discovers this at
startup and mounts the router.

This module only manipulates ``sys.path`` — it adds the TMS backend
directory so that ``from main import api`` (and the transitive
``from app.x import y`` imports inside TMS's main) resolve to the
existing TMS backend code.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "..", "backend"))

if os.path.isdir(_BACKEND_DIR) and _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


__version__ = "0.1.0"
