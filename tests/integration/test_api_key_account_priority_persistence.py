"""Per-key account priority must survive the write/read round trip.

``replace_account_assignments`` inserts through an INSERT..SELECT, which does
not preserve the caller's ordering on its own, so the rank is carried across
explicitly. These tests pin that behavior end to end.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.utils.time import utcnow
from app.db.models import Account, ApiKey, ApiKeyAccountAssignment
from app.db.session import SessionLocal
from app.modules.api_keys.repository import ApiKeysRepository

ACCOUNTS = ["acc_prio_a", "acc_prio_b", "acc_prio_c"]
KEY_ID = "key_prio"


async def _seed() -> None:
    async with SessionLocal() as session:
        for account_id in ACCOUNTS:
            session.add(
                Account(
                    id=account_id,
                    email=f"{account_id}@example.com",
                    plan_type="plus",
                    access_token_encrypted=b"access",
                    refresh_token_encrypted=b"refresh",
                    id_token_encrypted=b"id",
                    last_refresh=utcnow(),
                )
            )
        session.add(
            ApiKey(
                id=KEY_ID,
                name="priority-key",
                key_hash="hash_prio",
                key_prefix="sk-prio",
            )
        )
        await session.commit()


async def _stored_ranks() -> dict[str, int]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(ApiKeyAccountAssignment.account_id, ApiKeyAccountAssignment.priority).where(
                    ApiKeyAccountAssignment.api_key_id == KEY_ID
                )
            )
        ).all()
    return {account_id: priority for account_id, priority in rows}


async def _relationship_order() -> list[str]:
    async with SessionLocal() as session:
        key = (await session.execute(select(ApiKey).where(ApiKey.id == KEY_ID))).scalar_one()
        return [assignment.account_id for assignment in key.account_assignments]


@pytest.mark.asyncio
async def test_assignment_order_is_persisted_as_rank(db_setup):
    await _seed()
    async with SessionLocal() as session:
        await ApiKeysRepository(session).replace_account_assignments(KEY_ID, ACCOUNTS)

    assert await _stored_ranks() == {"acc_prio_a": 0, "acc_prio_b": 1, "acc_prio_c": 2}
    # The relationship is ordered, so readers get the selection order for free.
    assert await _relationship_order() == ACCOUNTS


@pytest.mark.asyncio
async def test_reordering_rewrites_the_rank(db_setup):
    await _seed()
    async with SessionLocal() as session:
        await ApiKeysRepository(session).replace_account_assignments(KEY_ID, ACCOUNTS)
    reordered = list(reversed(ACCOUNTS))
    async with SessionLocal() as session:
        await ApiKeysRepository(session).replace_account_assignments(KEY_ID, reordered)

    assert await _stored_ranks() == {"acc_prio_c": 0, "acc_prio_b": 1, "acc_prio_a": 2}
    assert await _relationship_order() == reordered


@pytest.mark.asyncio
async def test_rank_map_derived_from_read_order_matches_request(db_setup):
    """The proxy builds its rank map by enumerating the loaded assignment list."""
    await _seed()
    requested = ["acc_prio_b", "acc_prio_c", "acc_prio_a"]
    async with SessionLocal() as session:
        await ApiKeysRepository(session).replace_account_assignments(KEY_ID, requested)

    loaded = await _relationship_order()
    assert {account_id: rank for rank, account_id in enumerate(loaded)} == {
        "acc_prio_b": 0,
        "acc_prio_c": 1,
        "acc_prio_a": 2,
    }
