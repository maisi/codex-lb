"""Processing provenance preserves unknown history across additive schema changes."""

from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import String, create_engine, inspect, text

from app.db.migrate import _build_alembic_config, check_schema_drift, run_upgrade

PARENT = "20261023_000000_renumber_api_key_account_priority"
REVISION = "20261101_000000_add_request_processing_node"


def test_processing_node_upgrade_history_new_rows_and_downgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'processing-node.sqlite'}"
    run_upgrade(url, PARENT, bootstrap_legacy=False)
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO request_logs (request_id, model, requested_at, status, request_kind) "
                    "VALUES ('historical-fixture', 'fixture', '2026-01-01 12:00:00', 'success', 'normal')"
                )
            )
        run_upgrade(url, bootstrap_legacy=False)
        columns = {column["name"]: column for column in inspect(engine).get_columns("request_logs")}
        assert "processing_node" in columns
        assert columns["processing_node"]["nullable"] is True
        assert columns["processing_node"]["default"] is None
        node_type = columns["processing_node"]["type"]
        assert isinstance(node_type, String)
        assert node_type.length == 64
        assert ScriptDirectory.from_config(_build_alembic_config(url)).get_heads() == [REVISION]
        with engine.begin() as connection:
            assert connection.scalar(text("SELECT processing_node FROM request_logs")) is None
            connection.execute(
                text(
                    "INSERT INTO request_logs (request_id, model, requested_at, status, request_kind, processing_node) "
                    "VALUES ('new-fixture', 'fixture', '2026-01-01 12:01:00', 'success', 'normal', 'home-b')"
                )
            )
            assert (
                connection.scalar(text("SELECT processing_node FROM request_logs WHERE request_id='new-fixture'"))
                == "home-b"
            )
        assert check_schema_drift(url) == ()
        # Startup also supports model-created schemas with an older/missing
        # ledger. Replaying this revision must preserve existing attribution.
        command.stamp(_build_alembic_config(url), PARENT)
        run_upgrade(url, bootstrap_legacy=False)
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT processing_node FROM request_logs WHERE request_id='new-fixture'"))
                == "home-b"
            )
        command.downgrade(_build_alembic_config(url), PARENT)
        assert "processing_node" not in {column["name"] for column in inspect(engine).get_columns("request_logs")}
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM request_logs")) == 2
        run_upgrade(url, bootstrap_legacy=False)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT processing_node FROM request_logs")).scalars().all() == [None, None]
    finally:
        engine.dispose()
