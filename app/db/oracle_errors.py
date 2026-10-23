"""Driver error classification shared by prepared Oracle ownership operations."""

from sqlalchemy.exc import IntegrityError


def is_oracle_unique_violation(error: IntegrityError) -> bool:
    original = error.orig
    detail = original.args[0] if original is not None and original.args else None
    return getattr(detail, "code", None) == 1
