#!/usr/bin/env bash
# PreToolUse hook for Autonomy-TMS (Transport plane).
# Specific to TMS: the repo was forked from SCP in the past; a live risk is
# accidentally re-syncing SCP code, sharing SCP's SQLAlchemy Base, or running
# destructive DB commands during independence migration.
set -uo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || echo "")

block() { echo "BLOCKED (TMS): $1" >&2; exit 2; }

# TMS is a SIBLING product, not a fork — prevent accidental re-coupling to SCP
if printf '%s' "$cmd" | grep -qE 'git[[:space:]]+remote[[:space:]]+add.*(upstream|Autonomy-SCP|azirella-ltd/Autonomy-SCP)'; then
  block "TMS is a sibling product, not a fork of SCP. Do not add an upstream remote pointing to SCP. See CLAUDE.md 'TMS is a Sibling Product, Not a Fork'."
fi
if printf '%s' "$cmd" | grep -qE 'git[[:space:]]+(pull|fetch|merge).*Autonomy-SCP'; then
  block "Never pull/fetch/merge from Autonomy-SCP into TMS. Shared code belongs in Autonomy-Core."
fi

# Destructive DB ops
if printf '%s' "$cmd" | grep -qE 'make[[:space:]]+(rebuild-db|db-reset|reseed-db)'; then
  block "Destructive DB operation. Confirm with user — independence migration may be in progress."
fi
if printf '%s' "$cmd" | grep -qE '(psql|pg_dump|pg_restore|docker[[:space:]]+exec.*psql).*-c[[:space:]]+["'\''].*\b(DROP|TRUNCATE)\b'; then
  block "Direct DDL from the shell violates SOC II change-management. Use an Alembic migration."
fi
if printf '%s' "$cmd" | grep -qE 'alembic[[:space:]]+downgrade.*base'; then
  block "alembic downgrade base wipes all schema. Confirm with user."
fi

# Force push / history rewrite
if printf '%s' "$cmd" | grep -qE 'git[[:space:]]+push.*(--force|--force-with-lease|[[:space:]]-f([[:space:]]|$))'; then
  block "Force push: confirm with user."
fi
if printf '%s' "$cmd" | grep -qE 'git[[:space:]]+(reset[[:space:]]+--hard|filter-branch|filter-repo)'; then
  block "History rewrite — confirm with user."
fi

# Docker volume nuke
if printf '%s' "$cmd" | grep -qE 'docker[[:space:]]+(volume[[:space:]]+rm|system[[:space:]]+prune)'; then
  block "Docker volume/system prune removes DB state. Confirm with user."
fi

# Generic rm -rf outside build dirs
if printf '%s' "$cmd" | grep -qE 'rm[[:space:]]+(-[rRf]+[[:space:]]+)*(/|~|\$HOME|\*)'; then
  if ! printf '%s' "$cmd" | grep -qE '(dist/|build/|\.pytest_cache/|__pycache__/|\.mypy_cache/|\.ruff_cache/|node_modules/|frontend/build/|logs/)'; then
    block "rm -rf outside of build/cache dirs requires explicit user confirmation."
  fi
fi

exit 0
