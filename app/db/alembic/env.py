from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from app.core.config.settings import get_settings
from app.db.backend_support import UnsupportedDatabaseBackendError, require_supported_database_backend
from app.db.migration_url import to_sync_database_url
from app.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    database_url = configured if configured else get_settings().database_url
    require_supported_database_backend(database_url, operation="Alembic schema migration")
    if make_url(database_url).get_backend_name() == "oracle":
        raise UnsupportedDatabaseBackendError(
            "Oracle uses a dedicated Alembic baseline; use codex-lb-db upgrade head. "
            "The SQLite/PostgreSQL migration history cannot run on Oracle."
        )
    return database_url if configured else to_sync_database_url(database_url)


def run_migrations_offline() -> None:
    url = _sync_database_url()
    config.set_main_option("sqlalchemy.url", url)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _sync_database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
