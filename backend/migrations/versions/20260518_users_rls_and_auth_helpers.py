"""Mirror of Core 0054: users RLS + auth.find_user_* helpers.

Revision ID: 20260518_users_rls_and_auth_helpers
Revises: 20260518_soc2_supply_chain_configs_rls
Create Date: 2026-05-18

Companion to Autonomy-Core@d1c9afd. Core's migration covers
``public.users`` in autonomy-db; this one covers TMS's standalone DB.

Closes the final §3.80 audit deferral for TMS. Companion deps.py
refactor lands alongside so TMS auth continues to work post-RLS —
``get_current_user`` switches from ``db.query(User).filter(User.email ==
email)`` (which would fail-closed under RLS pre-tenant-context) to
``SELECT * FROM auth.find_user_by_email(:e)`` (SECURITY DEFINER
bypass), mirroring SCP's pattern.

Same DDL as Core 0054.
"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260518_users_rls_and_auth_helpers"
down_revision = "20260518_soc2_supply_chain_configs_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS auth;")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION auth.find_user_by_email(p_email text)
        RETURNS SETOF public.users
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path TO 'public', 'pg_temp'
        AS $$
            SELECT * FROM users WHERE email = p_email LIMIT 1;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION auth.find_user_by_id(p_id integer)
        RETURNS SETOF public.users
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path TO 'public', 'pg_temp'
        AS $$
            SELECT * FROM users WHERE id = p_id LIMIT 1;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION auth.find_user_by_username(p_username text)
        RETURNS SETOF public.users
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path TO 'public', 'pg_temp'
        AS $$
            SELECT * FROM users WHERE username = p_username LIMIT 1;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION auth.find_user_by_username_or_email(p_login text)
        RETURNS SETOF public.users
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path TO 'public', 'pg_temp'
        AS $$
            SELECT * FROM users
            WHERE LOWER(username) = LOWER(p_login)
               OR LOWER(email) = LOWER(p_login)
            LIMIT 1;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION auth.tenant_for_config(p_config_id integer)
        RETURNS integer
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path TO 'public', 'pg_temp'
        AS $$
            SELECT tenant_id FROM supply_chain_configs WHERE id = p_config_id LIMIT 1;
        $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT (
                SELECT relrowsecurity FROM pg_class
                WHERE oid = 'public.users'::regclass
            ) THEN
                ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = 'users'
                  AND policyname = 'tenant_isolation'
            ) THEN
                CREATE POLICY tenant_isolation ON public.users
                  USING (
                    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer
                  );
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.users;")
    op.execute("ALTER TABLE public.users DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP FUNCTION IF EXISTS auth.tenant_for_config(integer);")
    op.execute("DROP FUNCTION IF EXISTS auth.find_user_by_username_or_email(text);")
    op.execute("DROP FUNCTION IF EXISTS auth.find_user_by_username(text);")
    op.execute("DROP FUNCTION IF EXISTS auth.find_user_by_id(integer);")
    op.execute("DROP FUNCTION IF EXISTS auth.find_user_by_email(text);")
