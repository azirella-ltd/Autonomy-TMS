"""TMS plane router factory (AD-13 / §3.56 PR-D)."""
from __future__ import annotations

# Triggers the sys.path insertion in autonomy_tms.__init__.
import autonomy_tms  # noqa: F401

from fastapi import APIRouter


def get_router() -> APIRouter:
    """Return the combined TMS plane router with absolute paths.

    TMS's ``main.py`` defines ``api = APIRouter(prefix='/api/v1')``
    and registers TMS's full surface onto it. Returns this router
    directly; the host backend mounts it at prefix='' to avoid
    double-prefixing.
    """
    from main import api as _tms_api  # type: ignore[import-not-found]

    return _tms_api
