from __future__ import annotations

from sqlalchemy.engine import make_url


class UnsupportedDatabaseBackendError(RuntimeError):
    """A database preparation backend is not enabled for application use."""


def require_supported_database_backend(database_url: str, *, operation: str) -> None:
    """Reject incomplete Oracle paths before SQLAlchemy loads a driver."""
    if make_url(database_url).get_backend_name().lower() == "oracle":
        raise UnsupportedDatabaseBackendError(
            f"{operation} is disabled for Oracle: application runtime and schema migrations are incomplete. "
            "Use codex-lb-db oracle-check for a read-only connection check. "
            "Use SQLite or PostgreSQL to run codex-lb."
        )
