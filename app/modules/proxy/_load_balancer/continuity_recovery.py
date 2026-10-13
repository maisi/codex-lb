"""Read the existing local backoff for a still-active continuity owner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.balancer.logic import transient_error_backoff_until
from app.db.models import AccountStatus

if TYPE_CHECKING:
    from app.modules.proxy.load_balancer import LoadBalancer


async def continuity_owner_recovery_delay(owner: LoadBalancer, account_id: str) -> float | None:
    lock = await owner._get_account_lock(account_id)
    async with lock:
        async with owner._repo_factory() as repos:
            account = await repos.accounts.get_by_id(account_id)
            if account is None or account.status != AccountStatus.ACTIVE:
                return None
            state = owner._state_for(account)
        deadlines = [
            deadline
            for deadline in (state.cooldown_until, transient_error_backoff_until(state))
            if deadline is not None
        ]
        if not deadlines:
            return None
        delay = max(deadlines) - owner._clock.time()
        return delay if delay > 0 else None
