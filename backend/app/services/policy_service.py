"""
L4 Strategic policy_parameters service helpers.

Two entry points:

  * `get_active_policy(tenant_id, config_id)` — resolve the current θ
    for a (tenant, config) scope. Config-specific row beats tenant-wide
    default. Raises if neither exists.

  * `apply_policy_patch(tenant_id, config_id, patch, approved_by, ...)`
    — supersede the active policy with a new versioned row carrying
    the patched fields. Validates before commit; raises on invariant
    violation.

  * `ensure_default_policy(tenant_id)` — provisioning hook. Creates a
    tenant-wide default row with `source='MIGRATION'` if no active
    policy exists. Idempotent.

The model itself enforces the four invariants (BSC sum, mode-mix
brackets, unique tier priorities, carrier portfolio sum) via
`PolicyParameters.validate()`. The service is a thin wrapper that
adds versioning discipline + commit semantics.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.policy_parameters import PolicyParameters, PolicySource

logger = logging.getLogger(__name__)


# Columns that CANNOT be carried forward when patching — version /
# effective window / authoring metadata are recomputed per new row.
_PATCH_FORBIDDEN = {
    "id",
    "effective_from",
    "effective_to",
    "version",
    "created_at",
    "updated_at",
    "source",
    "source_proposal_id",
    "approved_by",
    "created_by",
}


class PolicyNotFound(LookupError):
    """No active policy for the requested (tenant, config) scope."""


def get_active_policy(
    db: Session,
    *,
    tenant_id: int,
    config_id: Optional[int] = None,
) -> PolicyParameters:
    """Resolve the active policy for (tenant_id, config_id).

    Resolution order:
      1. config-specific policy (`config_id == <param>`) if one exists
      2. tenant-wide default (`config_id IS NULL`) otherwise

    Raises PolicyNotFound if neither exists. Provisioning should call
    `ensure_default_policy` so this is never the case in production.
    """
    q = (
        select(PolicyParameters)
        .where(
            PolicyParameters.tenant_id == tenant_id,
            or_(
                PolicyParameters.config_id == config_id,
                PolicyParameters.config_id.is_(None),
            ),
            PolicyParameters.effective_to.is_(None),
        )
        # config-specific (non-null) wins; tenant-wide default is fallback.
        .order_by(PolicyParameters.config_id.is_(None).asc())
    )
    policy = db.execute(q).scalars().first()
    if policy is None:
        raise PolicyNotFound(
            f"No active PolicyParameters for tenant={tenant_id} "
            f"config={config_id}. Provisioning may have skipped policy creation."
        )
    return policy


def ensure_default_policy(
    db: Session,
    *,
    tenant_id: int,
    created_by: Optional[int] = None,
) -> PolicyParameters:
    """Idempotently create the tenant-wide default policy if none exists.

    Called from tenant provisioning. Returns the existing policy if one
    is already active for `(tenant_id, config_id IS NULL)`; otherwise
    creates a fresh one and FLUSHES (server_defaults populate, validate
    runs). Caller owns commit — this lets create_tenant batch policy
    creation into the same atomic transaction as user/customer/tenant.
    """
    try:
        return get_active_policy(db, tenant_id=tenant_id, config_id=None)
    except PolicyNotFound:
        pass

    policy = PolicyParameters(
        tenant_id=tenant_id,
        config_id=None,
        version=1,
        source=PolicySource.MIGRATION,
        created_by=created_by,
    )
    db.add(policy)
    # Flush first so server_defaults populate (BSC floats + JSONB blobs).
    # validate() needs the populated values, not the in-memory Nones.
    db.flush()
    db.refresh(policy)
    policy.validate()  # Caller catches ValueError + handles rollback
    logger.info(
        "Created default PolicyParameters for tenant=%s (id=%s)",
        tenant_id, policy.id,
    )
    return policy


def apply_policy_patch(
    db: Session,
    *,
    tenant_id: int,
    config_id: Optional[int],
    patch: Dict[str, Any],
    approved_by: int,
    source_proposal_id: Optional[int] = None,
    source: Optional[str] = None,
) -> PolicyParameters:
    """Supersede the active policy with a new versioned row.

    Closes the previous row (`effective_to = now()`) and inserts a fresh
    row carrying the patched fields with `version += 1`. The previous
    row's audit-relevant columns (created_by, etc.) do NOT carry forward
    — only the policy θ values do.

    Args:
        patch: dict of column-name → new-value. Forbidden keys
            (id, effective_from, effective_to, version, source*, audit
            timestamps) are silently dropped to avoid corrupting the
            versioning chain.
        approved_by: user who signed off on the change.
        source_proposal_id: AgentDecision.id when this patch comes from
            an L4 Strategic agent proposal. None for manual edits.
        source: explicit override; defaults to STRATEGIC_AGENT when
            source_proposal_id is set, MANUAL otherwise.

    Raises:
        PolicyNotFound: no active policy for the scope.
        ValueError: patch causes an invariant violation (BSC sum,
            mode-mix brackets, etc.).
    """
    current = get_active_policy(db, tenant_id=tenant_id, config_id=config_id)

    # Carry forward every θ column except the forbidden ones.
    new_fields: Dict[str, Any] = {}
    for col in PolicyParameters.__table__.columns:
        if col.name in _PATCH_FORBIDDEN or col.name == "tenant_id" or col.name == "config_id":
            continue
        new_fields[col.name] = getattr(current, col.name)

    # Apply patch (filtering forbidden keys with a warning so the caller
    # knows their attempt was a no-op rather than silently succeeding).
    cleaned_patch: Dict[str, Any] = {}
    for k, v in patch.items():
        if k in _PATCH_FORBIDDEN or k in {"tenant_id", "config_id"}:
            logger.warning(
                "apply_policy_patch: ignoring forbidden patch key %r "
                "(must not be set via patch)", k,
            )
            continue
        cleaned_patch[k] = v
    new_fields.update(cleaned_patch)

    if source is None:
        source = (
            PolicySource.STRATEGIC_AGENT
            if source_proposal_id is not None
            else PolicySource.MANUAL
        )

    now = datetime.utcnow()

    # Close the old row first so the partial unique index doesn't
    # bite us when we INSERT the new one with effective_to=NULL.
    current.effective_to = now
    db.flush()

    new_policy = PolicyParameters(
        tenant_id=tenant_id,
        config_id=config_id,
        **new_fields,
        version=current.version + 1,
        source=source,
        source_proposal_id=source_proposal_id,
        approved_by=approved_by,
        effective_from=now,
        effective_to=None,
    )
    new_policy.validate()
    db.add(new_policy)
    # Flush so the new row gets an id + the partial unique index check
    # fires inside this transaction; caller owns commit so that an
    # encompassing operation (e.g. AgentDecision.status update on the
    # same proposal) commits atomically with the policy supersede.
    db.flush()
    db.refresh(new_policy)

    logger.info(
        "PolicyParameters patched: tenant=%s config=%s v%s → v%s "
        "(source=%s, proposal=%s, keys=%s)",
        tenant_id, config_id, current.version, new_policy.version,
        source, source_proposal_id, sorted(cleaned_patch.keys()),
    )
    return new_policy
