from __future__ import annotations

import logging

from app.core.metrics import prometheus as _prometheus
from app.core.utils.time import to_utc_naive, utcnow
from app.db.models import Account, AccountStatus

logger = logging.getLogger(__name__)

# Low-cardinality source labels identifying which subsystem flipped the account.
REAUTH_SOURCE_TOKEN_REFRESH = "token_refresh"
REAUTH_SOURCE_USAGE_REFRESH = "usage_refresh"
REAUTH_SOURCE_PROXY = "proxy"


def _last_refresh_age_seconds(account: Account) -> float | None:
    last_refresh = getattr(account, "last_refresh", None)
    if last_refresh is None:
        return None
    try:
        age = (utcnow() - to_utc_naive(last_refresh)).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return None
    return age if age >= 0 else 0.0


def record_account_status_transition(
    account: Account,
    *,
    status: AccountStatus | str,
    error_code: str | None,
    source: str,
) -> None:
    """Emit a metric + structured log when an account is flipped to a
    non-routable auth status (``REAUTH_REQUIRED`` / ``DEACTIVATED``).

    This is the single observability hook for *why* an account needs re-auth:
    it records the upstream error code, the originating subsystem, and how
    stale the account's credentials were at the moment it flipped. The
    ``error_code`` and ``source`` labels are server-controlled and bounded, so
    the counter cardinality stays low. Never logs token material.
    """
    status_label = status.value if isinstance(status, AccountStatus) else str(status)
    code = error_code or "unknown"
    age_seconds = _last_refresh_age_seconds(account)

    counter = _prometheus.account_status_transition_total
    if _prometheus.PROMETHEUS_AVAILABLE and counter is not None:
        counter.labels(status=status_label, error_code=code, source=source).inc()

    logger.warning(
        "Account auth status transition account_id=%s status=%s error_code=%s source=%s last_refresh_age_seconds=%s",
        getattr(account, "id", "unknown"),
        status_label,
        code,
        source,
        f"{age_seconds:.0f}" if age_seconds is not None else "unknown",
    )
