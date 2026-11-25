"""The shared mixins, on a throwaway table in a private metadata so Base.metadata (and therefore the
migrations test) is unaffected."""

import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import Engine, MetaData, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from gtm_studio.db import base as db_base
from gtm_studio.db.base import NAMING_CONVENTION, IdMixin, TimestampMixin, UTCDateTime


class _ScratchBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class _Thing(IdMixin, TimestampMixin, _ScratchBase):
    __tablename__ = "thing"
    name: Mapped[str] = mapped_column(String(50))


@pytest.fixture
def scratch_engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://")
    _ScratchBase.metadata.create_all(engine)  # test-only: the app itself never calls create_all
    yield engine
    engine.dispose()


def test_ids_are_uuid4_strings(scratch_engine: Engine) -> None:
    with Session(scratch_engine) as session:
        first, second = _Thing(name="a"), _Thing(name="b")
        session.add_all([first, second])
        session.commit()
        assert uuid.UUID(first.id).version == 4
        assert len(first.id) == 36
        assert first.id != second.id


def test_timestamps_are_set_in_python_and_come_back_as_aware_utc(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = iter(datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=n) for n in range(100))
    monkeypatch.setattr(db_base, "utcnow", lambda: next(ticks))  # every read is a second later
    with Session(scratch_engine) as session:
        session.add(_Thing(id="t1", name="a"))
        session.commit()
    with Session(scratch_engine) as session:
        thing = session.get_one(_Thing, "t1")
        assert thing.created_at.tzinfo is not None
        assert thing.created_at.utcoffset() == timedelta(0)  # SQLite alone would return a naive value
        # One clock read for both columns: a second read would have been a second later.
        assert thing.created_at == thing.updated_at == datetime(2026, 1, 1, tzinfo=UTC)


def test_updated_at_moves_on_update_and_created_at_does_not(scratch_engine: Engine) -> None:
    with Session(scratch_engine) as session:
        session.add(_Thing(id="t1", name="a"))
        session.commit()
        thing = session.get_one(_Thing, "t1")
        created, updated = thing.created_at, thing.updated_at
        time.sleep(0.05)  # Windows clocks can tick coarsely
        thing.name = "b"
        session.commit()
        session.refresh(thing)
        assert thing.created_at == created
        assert thing.updated_at > updated


def test_utc_datetime_normalizes_other_offsets_and_rejects_naive_values(scratch_engine: Engine) -> None:
    plus_two = timezone(timedelta(hours=2))
    with Session(scratch_engine) as session:
        session.add(_Thing(id="t1", name="a", created_at=datetime(2026, 1, 1, 12, 0, tzinfo=plus_two)))
        session.commit()
    with Session(scratch_engine) as session:
        assert session.get_one(_Thing, "t1").created_at == datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    with Session(scratch_engine) as session:
        session.add(_Thing(id="t2", name="b", created_at=datetime(2026, 1, 1, 12, 0)))
        with pytest.raises(Exception, match="naive datetime"):
            session.flush()


def test_utc_datetime_type_is_the_portable_datetime_with_timezone() -> None:
    assert UTCDateTime.impl.timezone is True  # type: ignore[attr-defined]
