import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import JSON, Boolean, Engine, Integer, String, Text, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

import gtm_studio.db.models  # noqa: F401  (registers every table on Base.metadata)
from gtm_studio.db import migrate
from gtm_studio.db.base import Base, UTCDateTime
from gtm_studio.db.engine import make_engine
from gtm_studio.db.models.app_meta import INSTALL_ID_KEY, AppMeta
from gtm_studio.settings import Settings

SRC = Path(__file__).resolve().parents[2] / "src"


def _tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


@pytest.fixture
def migrated_engine(settings: Settings) -> Iterator[Engine]:
    """Overrides conftest's copy of the template database: these tests are about Alembic, so they run it."""
    migrate.upgrade(settings)
    engine = make_engine(settings)
    try:
        yield engine
    finally:
        engine.dispose()


def test_a_fresh_database_is_not_migrated_and_asking_does_not_create_it(
    settings: Settings, tmp_path: Path
) -> None:
    assert migrate.current(settings) is None
    assert not (tmp_path / "gtm_studio.db").exists()


def test_upgrade_creates_app_meta_with_an_install_id(settings: Settings, migrated_engine: Engine) -> None:
    assert migrate.current(settings) == "0004_audit_pagination_index" == migrate.head(settings)
    assert {"app_meta", "alembic_version"} <= _tables(migrated_engine)
    with Session(migrated_engine) as session:
        install_id = session.scalars(select(AppMeta.value).where(AppMeta.key == INSTALL_ID_KEY)).one()
    assert uuid.UUID(install_id).version == 4


def test_upgrade_is_idempotent_and_keeps_the_install_id(settings: Settings, migrated_engine: Engine) -> None:
    def install_id() -> str:
        with Session(migrated_engine) as session:
            return session.scalars(select(AppMeta.value).where(AppMeta.key == INSTALL_ID_KEY)).one()

    first = install_id()
    migrate.upgrade(settings)
    assert install_id() == first


def test_upgrade_then_downgrade_then_upgrade(settings: Settings, migrated_engine: Engine) -> None:
    migrate.downgrade(settings, "base")
    assert migrate.current(settings) is None
    assert "app_meta" not in _tables(migrated_engine)
    migrate.upgrade(settings)
    assert migrate.current(settings) == migrate.head(settings)
    assert "app_meta" in _tables(migrated_engine)


def test_a_database_at_0003_upgrades_to_0004_and_stays_append_only(settings: Settings) -> None:
    migrate.upgrade(settings, "0003_audit_events")
    engine = make_engine(settings)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO audit_events (id, occurred_at, actor_display, action, entity_type, "
                    "entity_id, details) VALUES ('e1', '2026-01-01 00:00:00', 'x', 'thing.changed', "
                    "'thing', 't-1', '{}')"
                )
            )
        migrate.upgrade(settings)
        assert migrate.current(settings) == "0004_audit_pagination_index"
        indexes = {ix["name"]: ix["column_names"] for ix in inspect(engine).get_indexes("audit_events")}
        assert indexes["ix_audit_events_occurred_at_id"] == ["occurred_at", "id"]
        assert "ix_audit_events_occurred_at" not in indexes
        for statement in ("UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events"):
            with engine.begin() as connection, pytest.raises(DBAPIError, match="append-only"):
                connection.execute(text(statement))
        with engine.connect() as connection:
            assert connection.execute(text("SELECT action FROM audit_events")).scalars().all() == [
                "thing.changed"
            ]
    finally:
        engine.dispose()


def test_models_and_migrations_agree(migrated_engine: Engine) -> None:
    """A failure means a model changed without a migration: `gtm db revision -m "..." --autogenerate`."""
    with migrated_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_autogenerate_writes_a_self_contained_migration(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`gtm db revision --autogenerate` end to end, in a copy of the migrations folder with no
    versions, so every model table is new and the generated code covers every column type."""
    scripts = tmp_path / "migrations"
    shutil.copytree(migrate.MIGRATIONS_DIR, scripts, ignore=shutil.ignore_patterns("versions", "__pycache__"))
    (scripts / "versions").mkdir()
    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", scripts)

    [script] = migrate.new_revision(settings, "every table", autogenerate=True)

    code = Path(script.path).read_text(encoding="utf-8")
    assert "op.create_table('app_meta'" in code
    assert "sa.DateTime(timezone=True)" in code
    assert "UTCDateTime" not in code  # migrations must not depend on application code
    assert "gtm_studio" not in code


def test_models_use_portable_column_types_only() -> None:
    """Types that behave the same on SQLite and Postgres. Timestamps must be UTCDateTime, not DateTime."""
    portable = (String, Text, JSON, Boolean, Integer, UTCDateTime)
    offenders = [
        f"{table.name}.{column.name}: {column.type!r}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if not isinstance(column.type, portable)
    ]
    assert offenders == []


def test_the_schema_is_only_ever_created_by_migrations() -> None:
    offenders = [str(p.relative_to(SRC)) for p in SRC.rglob("*.py") if "create_all" in p.read_text("utf-8")]
    assert offenders == []
