from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from agenthub.config import get_settings
from alembic import command
from alembic.config import Config


def test_fresh_database_upgrade_creates_current_schema(tmp_path, monkeypatch, request) -> None:
    database_path = tmp_path / "fresh.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    request.addfinalizer(get_settings.cache_clear)

    command.upgrade(Config("alembic.ini"), "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "conversationrecord",
        "messagerecord",
        "workspacerecord",
        "changesetrecord",
        "changesetfilerecord",
        "validationrunrecord",
        "memorysummaryrecord",
    }.issubset(tables)
    assert {"status", "error_json"}.issubset(
        {column["name"] for column in inspector.get_columns("messagerecord")}
    )
    assert "change_set_id" in {
        column["name"] for column in inspector.get_columns("applieddiffrecordrow")
    }
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "20260806_0001"
        )


def test_fresh_baseline_can_downgrade_to_empty_database(tmp_path, monkeypatch, request) -> None:
    database_url = f"sqlite:///{tmp_path / 'downgrade.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    request.addfinalizer(get_settings.cache_clear)
    config = Config("alembic.ini")

    command.upgrade(config, "head")
    command.downgrade(config, "base")

    remaining = set(inspect(create_engine(database_url)).get_table_names())
    assert remaining <= {"alembic_version"}
