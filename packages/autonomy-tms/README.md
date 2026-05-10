# autonomy-tms — TMS plane package (AD-13)

Exposes the Autonomy-TMS backend's FastAPI router via the
`autonomy_app.plane_routers` entry point so the unified backend
(`Autonomy-Core/apps/backend/`) can mount it.

This is a **thin wrapper**, not a code copy. The TMS backend's source
of truth stays at `Autonomy-TMS/backend/`; the wrapper sys.path-
inserts that directory at import time and imports `main.api`
directly.

## Install (development)

From `Autonomy-Core/apps/backend/`:

```bash
pip install -e ../../../Autonomy-TMS/packages/autonomy-tms
```

## What's registered

- `autonomy_app.plane_routers.tms` → `autonomy_tms.routes:get_router`
- `azirella_router.azirella_handlers.tms` →
  `autonomy_tms.handlers:get_handler_bundle` — initially an empty
  bundle (most demo customers run TMS at HEURISTIC tier today, so
  the existing `autonomy-tms-heuristics` package handles dispatch
  via the `azirella_router.heuristics` entry point).
