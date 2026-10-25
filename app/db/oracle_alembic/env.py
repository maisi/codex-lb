"""Separate Oracle lineage: SQLite/PostgreSQL historical DDL is not replayed."""

from alembic import context
from sqlalchemy.pool import NullPool

from app.db.oracle_connection import create_oracle_sync_engine

config = context.config
url = config.get_main_option("sqlalchemy.url")
if not url:
    raise RuntimeError("sqlalchemy.url is required for Oracle migrations")

if context.is_offline_mode():
    raise RuntimeError("Oracle baseline requires online catalog verification; offline upgrades are unsupported")

engine = create_oracle_sync_engine(url, poolclass=NullPool, hide_parameters=True)
try:
    with engine.connect() as connection:
        context.configure(connection=connection, transactional_ddl=False, version_table_pk=True)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
