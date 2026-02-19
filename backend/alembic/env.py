from logging.config import fileConfig
import os
from sqlalchemy import engine_from_config, pool
from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add model's MetaData object for 'autogenerate' support
from app.db.base import Base
target_metadata = Base.metadata

# Import database URL resolver
from app.core.db_urls import resolve_sync_database_url


def get_url():
    """Get database URL from environment or config."""
    # Try to get from alembic config first
    url = config.get_main_option("sqlalchemy.url")

    # If not in config or using ${DATABASE_URL}, resolve from environment
    if not url or "${DATABASE_URL}" in url or url == "${DATABASE_URL}":
        url = resolve_sync_database_url()

    return url


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.
    """
    url = get_url()

    # Detect database dialect for render_as_batch setting
    # PostgreSQL doesn't need batch mode (that's for SQLite)
    render_batch = "sqlite" in url

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=render_batch,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    # Override sqlalchemy.url in config with resolved URL
    url = get_url()
    config.set_main_option("sqlalchemy.url", url)

    print(f"Running migrations with database: {url.split('@')[-1] if '@' in url else url}")

    # Detect database dialect for render_as_batch setting
    render_batch = "sqlite" in url

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=render_batch,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
