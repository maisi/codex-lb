from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import QueuePool

import app.db.session as db_session
from app.core.auth import guardian as guardian_module
from app.core.auth.refresh import RefreshError, TokenRefreshResult
from app.core.config import settings as settings_module
from app.core.crypto import TokenEncryptor
from app.core.scheduling import leader_election as leader_module
from app.core.utils.time import utcnow
from app.db.models import Account, AccountRefreshClaim, AccountStatus, Base
from app.modules.accounts import auth_manager as auth_module
from app.modules.accounts.background_repository import BackgroundAccountsRepository
from app.modules.accounts.refresh_claims import RefreshClaimCoordinator, set_refresh_claim_coordinator

pytestmark = pytest.mark.integration


@pytest.fixture
async def guardian_pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncEngine]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'guardian.db'}"
    engine = create_async_engine(url, pool_size=4, max_overflow=0, pool_timeout=0.25)
    db_session._configure_sqlite_engine(engine.sync_engine, enable_wal=True)
    settings = settings_module.get_settings().model_copy(
        update={"database_url": url, "leader_election_enabled": True, "leader_election_ttl_seconds": 60}
    )
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    monkeypatch.setattr(leader_module, "get_settings", lambda: settings)
    monkeypatch.setattr(db_session, "_settings", settings)
    monkeypatch.setattr(db_session, "_sqlite_writer_lock", None)
    monkeypatch.setattr(db_session, "_background_session_factory", async_sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr(db_session, "_leader_session_factory", None, raising=False)
    set_refresh_claim_coordinator(RefreshClaimCoordinator(claimant_id="guardian"))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
        assert cast(QueuePool, engine.pool).checkedout() == 0
    finally:
        await engine.dispose()


async def _seed_accounts(count: int) -> None:
    encryptor = TokenEncryptor()
    async with db_session.get_background_session() as session:
        session.add_all(
            Account(
                id=f"account-{index}",
                chatgpt_account_id=f"workspace-{index}",
                email=f"account-{index}@example.com",
                plan_type="plus",
                access_token_encrypted=encryptor.encrypt(f"access-{index}"),
                refresh_token_encrypted=encryptor.encrypt(f"refresh-{index}"),
                id_token_encrypted=encryptor.encrypt(f"id-{index}"),
                last_refresh=utcnow() - timedelta(hours=13),
                status=AccountStatus.PAUSED if index == 1 else AccountStatus.ACTIVE,
            )
            for index in range(count)
        )
        await session.commit()


async def _enabled() -> bool:
    return True


def _scheduler(leader: leader_module.LeaderElection) -> guardian_module.AuthGuardianScheduler:
    scheduler = guardian_module.build_auth_guardian_scheduler()
    scheduler.dashboard_enabled = _enabled
    scheduler.leader_election_factory = lambda: leader
    assert scheduler.concurrency == 3
    return scheduler


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("wait_phase", ["oauth", "admission"])
async def test_guardian_slow_refresh_releases_pool_and_settles_partial_failure(
    guardian_pool: AsyncEngine, monkeypatch: pytest.MonkeyPatch, cancel: bool, wait_phase: str
) -> None:
    await _seed_accounts(3)
    started: set[str] = set()
    all_started = asyncio.Event()
    finish = asyncio.Event()

    async def wait_for_upstream(account_id: str) -> None:
        started.add(account_id)
        if len(started) == 3:
            all_started.set()
        await finish.wait()

    if wait_phase == "admission":
        acquire = auth_module.AuthManager._acquire_refresh_admission_bounded

        async def blocked_admission(
            manager: auth_module.AuthManager, account: Account, deadline: float | None
        ) -> auth_module.RefreshAdmissionLeasePort | None:
            await wait_for_upstream(account.id)
            return await acquire(manager, account, deadline)

        monkeypatch.setattr(auth_module.AuthManager, "_acquire_refresh_admission_bounded", blocked_admission)

    async def exchange(refresh_token: str, **_kwargs: object) -> TokenRefreshResult:
        if wait_phase == "oauth":
            await wait_for_upstream(refresh_token)
        if refresh_token == "refresh-2":
            raise RefreshError("transport_error", "Controlled upstream failure", False, transport_error=True)
        return TokenRefreshResult(
            access_token=f"new-access-{refresh_token}",
            refresh_token=f"rotated-{refresh_token}",
            id_token="new-id",
            account_id=None,
            plan_type="plus",
            email=None,
        )

    monkeypatch.setattr(auth_module, "refresh_access_token", exchange)
    leader = leader_module.LeaderElection("guardian-pool")
    scheduler = _scheduler(leader)
    task = asyncio.create_task(scheduler._refresh_once())
    try:
        await asyncio.wait_for(all_started.wait(), timeout=3)
        assert cast(QueuePool, guardian_pool.pool).checkedout() == 0
        # Lease renewal and unrelated background work finish while OAuth waits.
        assert await asyncio.wait_for(leader.renew(), timeout=1)
        async with db_session.get_background_session() as session:
            assert await session.scalar(text("SELECT 1")) == 1
            assert await session.scalar(select(func.count()).select_from(AccountRefreshClaim)) == 3
        if cancel:
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
    finally:
        finish.set()
        if cancel and task.cancelling():
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=3)
        else:
            await asyncio.wait_for(task, timeout=3)

    encryptor = TokenEncryptor()
    accounts = await BackgroundAccountsRepository().list_accounts()
    assert [encryptor.decrypt(account.refresh_token_encrypted) for account in accounts] == [
        "rotated-refresh-0",
        "rotated-refresh-1",
        "refresh-2",
    ]
    assert [account.status for account in accounts] == [
        AccountStatus.ACTIVE,
        AccountStatus.PAUSED,
        AccountStatus.ACTIVE,
    ]
    async with db_session.get_background_session() as session:
        assert await session.scalar(select(func.count()).select_from(AccountRefreshClaim)) == 0
    assert await leader.release()


async def test_guardian_peer_claim_poll_returns_read_connection_and_adopts_rotation(
    guardian_pool: AsyncEngine, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await _seed_accounts(1)
    polling = asyncio.Event()
    resume = asyncio.Event()

    class WaitingClaims(RefreshClaimCoordinator):
        denials = 0

        async def try_acquire(self, account_id: str, *, ttl_seconds: float, owner: str) -> bool:
            claimed = await super().try_acquire(account_id, ttl_seconds=ttl_seconds, owner=owner)
            if not claimed:
                self.denials += 1
                if self.denials == 2:
                    polling.set()
                    await resume.wait()
            return claimed

    set_refresh_claim_coordinator(WaitingClaims(claimant_id="guardian"))
    peer = RefreshClaimCoordinator(claimant_id="peer")
    assert await peer.try_acquire("account-0", ttl_seconds=60, owner="peer-refresh")

    async def unexpected_exchange(*_args: object, **_kwargs: object) -> TokenRefreshResult:
        pytest.fail("Guardian exchanged a token already rotated by its peer")

    monkeypatch.setattr(auth_module, "refresh_access_token", unexpected_exchange)
    caplog.set_level(logging.INFO, logger=guardian_module.logger.name)
    leader = leader_module.LeaderElection("guardian-poll")
    task = asyncio.create_task(_scheduler(leader)._refresh_once())
    try:
        await asyncio.wait_for(polling.wait(), timeout=3)
        assert cast(QueuePool, guardian_pool.pool).checkedout() == 0
        assert await asyncio.wait_for(leader.renew(), timeout=1)
        repo = BackgroundAccountsRepository()
        account = await repo.get_by_id("account-0")
        assert account is not None
        encryptor = TokenEncryptor()
        assert await repo.rotate_tokens(
            account.id,
            encryptor.encrypt("peer-access"),
            encryptor.encrypt("peer-rotation"),
            encryptor.encrypt("peer-id"),
            utcnow(),
            expected_refresh_token_encrypted=account.refresh_token_encrypted,
        )
        await peer.release(account.id, owner="peer-refresh")
    finally:
        resume.set()
        await asyncio.wait_for(task, timeout=3)
    assert "Auth Guardian refreshed account_id=account-0" in caplog.text
    assert await leader.release()
