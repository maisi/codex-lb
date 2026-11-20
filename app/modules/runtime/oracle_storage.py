"""Quota and online maintenance of the two known durable bridge tables."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.runtime.schemas import OracleMaintenanceState, OracleStorageLevel, OracleStorageStatus

if TYPE_CHECKING:
    import oracledb

GIB = 1024**3
WARNING_BYTES = 3 * GIB
AUTOMATIC_BYTES = 2 * GIB
_STATE_KEY = "oracle_bridge_quota_maintenance"
_TARGETS = (("HTTP_BRIDGE_OPERATIONS", "REQUEST_TEXT"), ("HTTP_BRIDGE_OPERATION_EVENTS", "EVENT_TEXT"))
_QUOTA = """
select case when q.max_bytes = -1 or exists
    (select 1 from session_privs where privilege = 'UNLIMITED TABLESPACE')
    then null else greatest(0, nvl(q.max_bytes,0)-nvl(q.bytes,0)) end,
    s.value, s.updated_at, t.tablespace_name
from user_tables t left join user_ts_quotas q on q.tablespace_name=t.tablespace_name
left join runtime_sentinels s on s.name=:state_key
where t.table_name='HTTP_BRIDGE_OPERATIONS'
"""
# SPACE_USAGE reports both live and expired LOB extents; only the live blocks
# need copying. Bound heap occupancy using the upper occupied fraction of
# every ASSM bucket. A full online move also copies the heap and maintains indexes.
_SEGMENT_USAGE = """
declare
  n number; f1 number; f2 number; f3 number; f4 number; full_bytes number;
begin
  dbms_space.space_usage(user,:name,:kind,n,n,n,f1,n,f2,n,f3,n,f4,n,full_bytes);
  :needed := full_bytes + f1 + f2*.75 + f3*.5 + f4*.25;
  :gain := f2*.25 + f3*.5 + f4*.75;
end;
"""
_LOB_USAGE = """
declare n number;
begin
  dbms_space.space_usage(user,:name,'LOB',n,n,n,:needed,n,:gain,n,n);
end;
"""
_EVENT_INDEXES = (
    "IDX_HTTP_BRIDGE_OPERATION_EVENTS_OPERATION_SEQUENCE",
    "UQ_HTTP_BRIDGE_OPERATION_EVENTS_OPERATION_FINGERPRINT",
)
# Session-owned lock survives implicit DDL commits. Separate schemas use separate lock IDs.
_LOCK_ID = "ora_hash('codex-lb:oracle-quota:' || user, 1073741823)"


@dataclass(frozen=True)
class StorageOperation:
    ddl: str
    working_bytes: int
    reclaimable_bytes: int


class OracleStorage:
    def __init__(self, session: AsyncSession, connection: oracledb.AsyncConnection):
        self.session = session
        self.connection = connection

    @classmethod
    async def open(cls, session: AsyncSession) -> OracleStorage:
        connection = await session.connection()
        raw = await connection.get_raw_connection()
        return cls(session, cast("oracledb.AsyncConnection", raw.driver_connection))

    async def status(self) -> OracleStorageStatus:
        with self.connection.cursor() as cursor:
            await cursor.execute(_QUOTA, state_key=_STATE_KEY)
            row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("Oracle bridge tablespace unavailable")
        free, state, updated, _ = row
        level: OracleStorageLevel = "healthy"
        if free is not None and free < WARNING_BYTES:
            level = "critical" if free < AUTOMATIC_BYTES else "warning"
        return OracleStorageStatus(level=level, free_bytes=free, maintenance=state or "idle", updated_at=updated)

    async def mark(self, state: OracleMaintenanceState) -> None:
        with self.connection.cursor() as cursor:
            await cursor.execute(
                """merge into runtime_sentinels s using (select :name name, :state value from dual) x
                on (s.name=x.name) when matched then update set s.value=x.value,
                s.updated_at=sys_extract_utc(systimestamp)
                when not matched then insert (name,value,updated_at)
                values (x.name,x.value,sys_extract_utc(systimestamp))""",
                name=_STATE_KEY,
                state=state,
            )
        # Commit on the pinned driver connection, keeping the advisory lock.
        await self.connection.commit()

    @asynccontextmanager
    async def lock(self) -> AsyncIterator[bool]:
        acquired = False
        try:
            with self.connection.cursor() as cursor:
                result = cursor.var(int)
                await cursor.execute(
                    f"declare k integer; begin select {_LOCK_ID} into k from dual; "
                    " :rc := dbms_lock.request(k,6,0,false); end;",
                    rc=result,
                )
                code = result.getvalue()
                if code not in (0, 1):
                    raise RuntimeError(f"Unexpected Oracle quota lock result {code}")
                acquired = code == 0
            yield acquired
        except BaseException:
            # Acquisition itself can be interrupted after the server granted it.
            if not acquired:
                await self.session.invalidate()
            raise
        finally:
            if acquired:
                # Close the physical session to release the lock and discard its
                # maintenance-specific timeout, also on cancellation or partial DDL.
                await self.session.invalidate()

    async def operations(self) -> list[StorageOperation]:
        operations = []
        with self.connection.cursor() as cursor:
            for table, column in _TARGETS:
                await cursor.execute(
                    """select l.segment_name, l.tablespace_name from user_lobs l
                    join user_tables t on t.table_name=l.table_name and t.tablespace_name=l.tablespace_name
                    where l.table_name=:tab and l.column_name=:col and l.securefile='YES'
                    and l.segment_created='YES' and l.partitioned='NO' and l.compression='NO' and l.deduplication='NO'
                    and l.encrypt='NO' and l.in_row='YES' and l.cache='NO' and l.logging='YES'
                    and l.retention_type='DEFAULT' and l.tablespace_name =
                      (select tablespace_name from user_tables where table_name='HTTP_BRIDGE_OPERATIONS')""",
                    tab=table,
                    col=column,
                )
                row = await cursor.fetchone()
                if row is None:
                    continue
                segment, tablespace = row
                heap, heap_gain = await _space(cursor, _SEGMENT_USAGE, name=table, kind="TABLE")
                lob, lob_gain = await _space(cursor, _LOB_USAGE, name=segment)
                tablespace = tablespace.replace('"', '""')
                ddl = f'alter table {table} move online lob ({column}) store as securefile (tablespace "{tablespace}")'
                operations.append(_operation(ddl, heap + lob, heap_gain + lob_gain))
            for index in _EVENT_INDEXES:
                await cursor.execute(
                    """select 1 from user_indexes i join user_segments s on s.segment_name=i.index_name
                    where i.index_name=:idx and i.table_name='HTTP_BRIDGE_OPERATION_EVENTS'
                    and i.index_type='NORMAL' and i.partitioned='NO' and i.status='VALID'
                    and s.bytes>=:minimum and i.tablespace_name=
                        (select tablespace_name from user_tables where table_name='HTTP_BRIDGE_OPERATIONS')""",
                    idx=index,
                    minimum=GIB // 8,
                )
                if await cursor.fetchone() is None:
                    continue
                used, gain = await _space(cursor, _SEGMENT_USAGE, name=index, kind="INDEX")
                operations.append(_operation(f"alter index {index} rebuild online", used, gain))
        return sorted(operations, key=lambda op: op.working_bytes)

    async def execute(self, operation: StorageOperation) -> None:
        self.connection.call_timeout = 300_000
        with self.connection.cursor() as cursor:
            await cursor.execute("alter session set ddl_lock_timeout=2")
            await cursor.execute(operation.ddl)


async def _space(cursor: oracledb.AsyncCursor, sql: str, **binds: str) -> tuple[int, int]:
    needed, gain = cursor.var(int), cursor.var(int)
    await cursor.execute(sql, **binds, needed=needed, gain=gain)
    return int(needed.getvalue()), int(gain.getvalue())


def _operation(ddl: str, used: int, gain: int) -> StorageOperation:
    # Reserve space for extent rounding, concurrent writes and index maintenance.
    return StorageOperation(ddl, used * 3 // 2 + GIB // 8, gain)
