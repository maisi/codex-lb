from __future__ import annotations

from sqlalchemy.engine import make_url


class UnsupportedDatabaseBackendError(RuntimeError):
    """A selected driver or operation is unsupported for this backend."""


def require_supported_database_backend(database_url: str, *, operation: str) -> None:
    """Keep Oracle on its verified native Thin driver before loading it."""
    parsed = make_url(database_url)
    if parsed.get_backend_name().lower() == "oracle" and parsed.drivername != "oracle+oracledb":
        raise UnsupportedDatabaseBackendError(
            f"{operation} requires the native oracle+oracledb:// Thin driver for Oracle. "
            "Install codex-lb[oracle] and use codex-lb-db oracle-check to validate the connection."
        )
