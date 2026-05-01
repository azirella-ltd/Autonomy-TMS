"""One-shot script: apply the 6 new 0501_* migrations as a linear chain.

The TMS DB has multiple alembic heads, which prevents
``alembic upgrade <rev>`` from planning a path. Workaround: invoke each
migration's ``upgrade()`` directly and stamp ``alembic_version`` after
each step.

Idempotent — every migration's ``upgrade()`` is idempotent on its own
(information_schema guards), and we skip steps already in
``alembic_version``.
"""
from __future__ import annotations

import os
import sys

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.operations import Operations
from sqlalchemy import create_engine, text


CHAIN = [
    ("20260501_plane_reg_wildcard", "20260501_canonical_cfg_nn"),
    ("20260501_canonical_cfg_nn", "20260501_ext_signal_creds"),
    ("20260501_ext_signal_creds", "20260501_powell_tid_nn"),
    ("20260501_powell_tid_nn", "20260501_authorities_tid_nn"),
    ("20260501_authorities_tid_nn", "20260501_audit_tid_nn"),
    ("20260501_audit_tid_nn", "20260501_role_templates"),
]


def main() -> int:
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://autonomy_user:autonomy_password@db:5432/autonomy",
    ).replace("+asyncpg", "")

    engine = create_engine(db_url)
    cfg = Config("/app/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    script = ScriptDirectory.from_config(cfg)

    with engine.begin() as conn:
        for from_rev, to_rev in CHAIN:
            applied = conn.execute(
                text(
                    "SELECT COUNT(*) FROM alembic_version "
                    "WHERE version_num = :v"
                ),
                {"v": to_rev},
            ).scalar()
            if applied:
                print(f"SKIP   {to_rev} (already in alembic_version)")
                continue

            print(f"APPLY  {from_rev} -> {to_rev}")
            rev = script.get_revision(to_rev)

            mctx = MigrationContext.configure(connection=conn)
            with Operations.context(mctx):
                rev.module.upgrade()

            # Replace from_rev in alembic_version with to_rev. If
            # from_rev isn't there (e.g. multi-head merge), insert.
            updated = conn.execute(
                text(
                    "UPDATE alembic_version SET version_num = :new "
                    "WHERE version_num = :old"
                ),
                {"new": to_rev, "old": from_rev},
            ).rowcount
            if updated == 0:
                conn.execute(
                    text(
                        "INSERT INTO alembic_version (version_num) "
                        "VALUES (:v)"
                    ),
                    {"v": to_rev},
                )
            print(f"  stamped {to_rev}")

    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
