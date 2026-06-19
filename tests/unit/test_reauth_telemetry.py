from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pytest

from app.core.auth import reauth_telemetry
from app.core.auth.reauth_telemetry import (
    REAUTH_SOURCE_PROXY,
    REAUTH_SOURCE_TOKEN_REFRESH,
    REAUTH_SOURCE_USAGE_REFRESH,
    record_account_status_transition,
)
from app.core.crypto import TokenEncryptor
from app.core.metrics import prometheus as prometheus_metrics
from app.core.utils.time import utcnow
from app.db.models import Account, AccountStatus

pytestmark = pytest.mark.unit

# Distinctive plaintext token material; the hook must never surface these.
_ACCESS_SECRET = "ACCESS-SECRET-DO-NOT-LOG"
_REFRESH_SECRET = "REFRESH-SECRET-DO-NOT-LOG"
_ID_SECRET = "ID-SECRET-DO-NOT-LOG"


def _account(account_id: str = "acc_obs", *, last_refresh: datetime | None = None) -> Account:
    encryptor = TokenEncryptor()
    return Account(
        id=account_id,
        email="user@example.com",
        plan_type="plus",
        access_token_encrypted=encryptor.encrypt(_ACCESS_SECRET),
        refresh_token_encrypted=encryptor.encrypt(_REFRESH_SECRET),
        id_token_encrypted=encryptor.encrypt(_ID_SECRET),
        last_refresh=last_refresh if last_refresh is not None else utcnow(),
        status=AccountStatus.ACTIVE,
        deactivation_reason=None,
    )


def _counter_value(status: str, error_code: str, source: str) -> float | None:
    registry = prometheus_metrics.REGISTRY
    if registry is None:
        return None
    return registry.get_sample_value(
        "codex_lb_account_status_transition_total",
        {"status": status, "error_code": error_code, "source": source},
    )


def _transition_record(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    return next(r for r in caplog.records if "Account auth status transition" in r.getMessage())


def test_records_counter_and_structured_log(caplog: pytest.LogCaptureFixture) -> None:
    account = _account(last_refresh=utcnow() - timedelta(days=9))
    before = _counter_value("reauth_required", "invalid_grant", REAUTH_SOURCE_TOKEN_REFRESH) or 0.0

    with caplog.at_level(logging.WARNING):
        record_account_status_transition(
            account,
            status=AccountStatus.REAUTH_REQUIRED,
            error_code="invalid_grant",
            source=REAUTH_SOURCE_TOKEN_REFRESH,
        )

    message = _transition_record(caplog).getMessage()
    assert "account_id=acc_obs" in message
    assert "status=reauth_required" in message
    assert "error_code=invalid_grant" in message
    assert f"source={REAUTH_SOURCE_TOKEN_REFRESH}" in message
    assert "last_refresh_age_seconds=" in message
    assert "unknown" not in message  # a fresh-enough last_refresh yields a numeric age
    # Never leak token material.
    assert _ACCESS_SECRET not in message
    assert _REFRESH_SECRET not in message
    assert _ID_SECRET not in message

    if prometheus_metrics.PROMETHEUS_AVAILABLE:
        after = _counter_value("reauth_required", "invalid_grant", REAUTH_SOURCE_TOKEN_REFRESH)
        assert after == pytest.approx(before + 1.0)


def test_missing_last_refresh_and_none_error_code_degrade_gracefully(caplog: pytest.LogCaptureFixture) -> None:
    account = _account("acc_no_refresh")
    account.last_refresh = None  # defensive: column is non-nullable but the hook must not raise

    with caplog.at_level(logging.WARNING):
        record_account_status_transition(
            account,
            status="deactivated",
            error_code=None,
            source=REAUTH_SOURCE_PROXY,
        )

    message = _transition_record(caplog).getMessage()
    assert "last_refresh_age_seconds=unknown" in message
    assert "error_code=unknown" in message
    assert "status=deactivated" in message


def test_no_metric_when_prometheus_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(reauth_telemetry._prometheus, "PROMETHEUS_AVAILABLE", False)
    monkeypatch.setattr(reauth_telemetry._prometheus, "account_status_transition_total", None)
    account = _account("acc_no_prom")

    with caplog.at_level(logging.WARNING):
        record_account_status_transition(
            account,
            status=AccountStatus.REAUTH_REQUIRED,
            error_code="token_expired",
            source=REAUTH_SOURCE_USAGE_REFRESH,
        )

    # Still logs; metric path is simply skipped without raising.
    assert "Account auth status transition" in _transition_record(caplog).getMessage()
