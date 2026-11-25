from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, delete, func, inspect, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from gtm_studio.audit.context import RequestContext, reset_request_context, set_request_context
from gtm_studio.audit.sql_audit_log import SqlAuditLog
from gtm_studio.db.models.audit import AuditEvent
from gtm_studio.domain.audit import (
    SYSTEM_ACTOR_DISPLAY,
    AuditAction,
    AuditFilters,
    InvalidCursorError,
    canonical_hash,
)
from gtm_studio.domain.identity import Actor
from gtm_studio.services.activity import ActivityService
from gtm_studio.services.identity import IdentityService, SeedSummary
from gtm_studio.services.ports import UnitOfWorkFactory

PMM_ID = "00000000-0000-4000-8000-000000000003"
NO_FILTERS = AuditFilters()


def _pmm(uow_factory: UnitOfWorkFactory) -> Actor:
    actor = IdentityService(uow_factory).get_actor(PMM_ID)
    assert actor is not None
    return actor


def _count(engine: Engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(AuditEvent)) or 0


def _stored(engine: Engine) -> list[AuditEvent]:
    """The rows as stored, newest first (ties by ID), bypassing the service layer."""
    with Session(engine) as session:
        return list(
            session.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()))
        )


# ------------------------------------------------------------------ writing an event


def test_an_event_is_written_with_the_request_context(
    uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    actor = _pmm(uow_factory)
    context = RequestContext(request_id="req-12345678", ip="203.0.113.9", user_agent="agent/1")
    token = set_request_context(context)
    try:
        with uow_factory() as uow:
            uow.audit.record(actor, "thing.changed", "thing", "t-1", details={"why": "because"})
    finally:
        reset_request_context(token)

    [event] = ActivityService(uow_factory).list_events(NO_FILTERS).items
    assert (event.actor_user_id, event.actor_display) == (PMM_ID, "Priya Marketing")
    assert (event.action, event.entity_type, event.entity_id) == ("thing.changed", "thing", "t-1")
    assert (event.request_id, event.ip, event.user_agent) == ("req-12345678", "203.0.113.9", "agent/1")
    assert event.details == {"why": "because"}
    assert (event.before_hash, event.after_hash) == (None, None)
    assert abs(datetime.now(UTC) - event.occurred_at) < timedelta(seconds=30)


def test_outside_a_request_the_request_fields_are_empty(uow_factory: UnitOfWorkFactory) -> None:
    with uow_factory() as uow:
        uow.audit.record(None, AuditAction.AUTH_LOGIN_DENIED, "user", "u-1")
    [event] = ActivityService(uow_factory).list_events(NO_FILTERS).items
    assert (event.request_id, event.ip, event.user_agent) == (None, None, None)
    assert (event.action, event.details) == ("auth.login_denied", {})  # the enum is stored as its string


def test_no_actor_means_a_system_event(uow_factory: UnitOfWorkFactory) -> None:
    with uow_factory() as uow:
        uow.audit.record(None, "job.finished", "job", "j-1")
    [event] = ActivityService(uow_factory).list_events(NO_FILTERS).items
    assert (event.actor_user_id, event.actor_display) == (None, SYSTEM_ACTOR_DISPLAY)


def test_before_and_after_are_stored_as_canonical_hashes(uow_factory: UnitOfWorkFactory) -> None:
    with uow_factory() as uow:
        uow.audit.record(
            None, "thing.changed", "thing", "t-1", before={"b": 1, "a": [1, 2]}, after={"state": "approved"}
        )
    [event] = ActivityService(uow_factory).list_events(NO_FILTERS).items
    assert event.before_hash == canonical_hash({"a": [1, 2], "b": 1})  # key order is irrelevant
    assert event.after_hash == canonical_hash({"state": "approved"})
    assert event.before_hash != event.after_hash


def test_canonical_hash_is_stable_regardless_of_key_order() -> None:
    assert canonical_hash({"a": 1, "b": {"c": 2, "d": 3}}) == canonical_hash({"b": {"d": 3, "c": 2}, "a": 1})
    assert len(canonical_hash({})) == 64


# ------------------------------------------------------------------ one transaction with the change


def test_rollback_removes_both_the_change_and_the_event(
    uow_factory: UnitOfWorkFactory, migrated_engine: Engine, seeded: SeedSummary
) -> None:
    actor = _pmm(uow_factory)
    with pytest.raises(RuntimeError, match="boom"), uow_factory() as uow:
        uow.identity.set_roles(PMM_ID, ["viewer"], source="dev_seed")  # the change
        uow.audit.record(actor, "user.roles_changed", "user", PMM_ID)  # its event
        raise RuntimeError("boom")

    assert _count(migrated_engine) == 0
    assert _pmm(uow_factory).roles == {"pmm"}  # still the original role


def test_commit_keeps_both_the_change_and_the_event(
    uow_factory: UnitOfWorkFactory, migrated_engine: Engine, seeded: SeedSummary
) -> None:
    actor = _pmm(uow_factory)
    with uow_factory() as uow:
        uow.identity.set_roles(PMM_ID, ["viewer"], source="dev_seed")
        uow.audit.record(actor, "user.roles_changed", "user", PMM_ID)
    assert _count(migrated_engine) == 1
    assert _pmm(uow_factory).roles == {"viewer"}


def test_an_event_that_cannot_be_written_takes_the_change_with_it(
    uow_factory: UnitOfWorkFactory, migrated_engine: Engine, seeded: SeedSummary
) -> None:
    """The other direction: no change without its event. An actor who isn't a user breaks the foreign key."""
    ghost = Actor(
        id="99999999-9999-4999-8999-999999999999", email="g@x.test", display_name="G", roles=frozenset()
    )
    with pytest.raises(IntegrityError), uow_factory() as uow:
        uow.identity.set_roles(PMM_ID, ["viewer"], source="dev_seed")
        uow.audit.record(ghost, "user.roles_changed", "user", PMM_ID)

    assert _count(migrated_engine) == 0
    assert _pmm(uow_factory).roles == {"pmm"}


def test_a_login_is_stamped_and_audited_in_one_transaction(
    uow_factory: UnitOfWorkFactory, seeded: SeedSummary, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("audit write failed")

    service = IdentityService(uow_factory)
    actor = _pmm(uow_factory)
    monkeypatch.setattr(SqlAuditLog, "record", fail)
    with pytest.raises(RuntimeError, match="audit write failed"):
        service.record_login(actor, "dev")
    with uow_factory() as uow:
        user = uow.identity.get_user(PMM_ID)
    assert user is not None
    assert user.last_login_at is None  # the stamp went with the event that failed


# ------------------------------------------------------------------ append-only


def _insert_one(engine: Engine) -> str:
    with Session(engine) as session:
        event = AuditEvent(actor_display="x", action="thing.changed", entity_type="thing", entity_id="t-1")
        session.add(event)
        session.commit()
        return event.id


def test_the_table_has_the_expected_indexes(migrated_engine: Engine) -> None:
    indexes = {ix["name"]: ix["column_names"] for ix in inspect(migrated_engine).get_indexes("audit_events")}
    assert indexes == {
        "ix_audit_events_entity_type_entity_id": ["entity_type", "entity_id"],
        "ix_audit_events_occurred_at": ["occurred_at"],
        "ix_audit_events_actor_user_id": ["actor_user_id"],
    }


def test_update_is_rejected(migrated_engine: Engine) -> None:
    event_id = _insert_one(migrated_engine)
    with Session(migrated_engine) as session, pytest.raises(DBAPIError, match="append-only"):
        session.execute(update(AuditEvent).where(AuditEvent.id == event_id).values(action="tampered"))
    with Session(migrated_engine) as session:
        assert session.get_one(AuditEvent, event_id).action == "thing.changed"


def test_update_through_the_orm_is_rejected(migrated_engine: Engine) -> None:
    event_id = _insert_one(migrated_engine)
    with Session(migrated_engine) as session:
        session.get_one(AuditEvent, event_id).details = {"rewritten": True}
        with pytest.raises(DBAPIError, match="append-only"):
            session.commit()


def test_delete_is_rejected(migrated_engine: Engine) -> None:
    event_id = _insert_one(migrated_engine)
    with Session(migrated_engine) as session, pytest.raises(DBAPIError, match="append-only"):
        session.execute(delete(AuditEvent).where(AuditEvent.id == event_id))
    with Session(migrated_engine) as session:
        session.delete(session.get_one(AuditEvent, event_id))
        with pytest.raises(DBAPIError, match="append-only"):
            session.commit()
    assert _count(migrated_engine) == 1


def test_raw_sql_cannot_get_around_the_triggers(migrated_engine: Engine) -> None:
    _insert_one(migrated_engine)
    for statement in ("UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events"):
        with migrated_engine.begin() as connection, pytest.raises(DBAPIError, match="append-only"):
            connection.execute(text(statement))
    assert _count(migrated_engine) == 1


# ------------------------------------------------------------------ reading


def _insert_events(engine: Engine, count: int, *, at: datetime, action: str = "test.event") -> None:
    with Session(engine) as session:
        for i in range(count):
            session.add(
                AuditEvent(
                    occurred_at=at, actor_display="x", action=action, entity_type="thing", entity_id=f"t-{i}"
                )
            )
        session.commit()


def test_events_come_newest_first(uow_factory: UnitOfWorkFactory) -> None:
    for name in ("first", "second", "third"):
        with uow_factory() as uow:
            uow.audit.record(None, f"test.{name}", "thing", "t-1")
    page = ActivityService(uow_factory).list_events(NO_FILTERS)
    assert [e.action for e in page.items] == ["test.third", "test.second", "test.first"]
    assert page.next_cursor is None


def test_events_recorded_back_to_back_keep_the_order_they_happened_in(uow_factory: UnitOfWorkFactory) -> None:
    """The Windows clock ticks every ~15.6 ms, so without a strictly increasing stamp these 50 events would
    share a timestamp and come back sorted by their random IDs."""
    with uow_factory() as uow:
        for i in range(50):
            uow.audit.record(None, "test.step", "thing", f"t-{i:02d}")
    items = ActivityService(uow_factory).list_events(NO_FILTERS).items
    assert [e.entity_id for e in items] == [f"t-{i:02d}" for i in range(49, -1, -1)]
    assert len({e.occurred_at for e in items}) == 50


def test_pagination_never_skips_or_repeats_events_that_share_a_timestamp(
    uow_factory: UnitOfWorkFactory, migrated_engine: Engine
) -> None:
    moment = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    _insert_events(migrated_engine, 25, at=moment)
    _insert_events(migrated_engine, 5, at=moment + timedelta(seconds=1), action="test.newer")
    service = ActivityService(uow_factory)

    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        page = service.list_events(NO_FILTERS, cursor, limit=7)
        seen += [e.id for e in page.items]
        pages += 1
        cursor = page.next_cursor
        if cursor is None:
            break

    stored = _stored(migrated_engine)
    assert pages == 5  # 7 + 7 + 7 + 7 + 2
    assert seen == [e.id for e in stored]  # every event once, in the stored order: newest first, ties by ID
    assert [e.action for e in stored[:5]] == ["test.newer"] * 5


def test_the_last_full_page_has_no_next_cursor(
    uow_factory: UnitOfWorkFactory, migrated_engine: Engine
) -> None:
    _insert_events(migrated_engine, 4, at=datetime(2026, 5, 1, tzinfo=UTC))
    service = ActivityService(uow_factory)
    first = service.list_events(NO_FILTERS, limit=2)
    assert first.next_cursor is not None
    second = service.list_events(NO_FILTERS, first.next_cursor, limit=2)
    assert len(second.items) == 2
    assert second.next_cursor is None  # exactly drained: no phantom empty page


def test_the_page_size_is_clamped(uow_factory: UnitOfWorkFactory, migrated_engine: Engine) -> None:
    _insert_events(migrated_engine, 3, at=datetime(2026, 5, 1, tzinfo=UTC))
    service = ActivityService(uow_factory)
    assert len(service.list_events(NO_FILTERS, limit=0).items) == 1
    assert len(service.list_events(NO_FILTERS, limit=10_000).items) == 3


def test_a_bad_cursor_raises(uow_factory: UnitOfWorkFactory) -> None:
    with pytest.raises(InvalidCursorError):
        ActivityService(uow_factory).list_events(NO_FILTERS, "garbage")


def test_filters_narrow_the_events(uow_factory: UnitOfWorkFactory, seeded: SeedSummary) -> None:
    pmm = _pmm(uow_factory)
    with uow_factory() as uow:
        uow.audit.record(pmm, "asset.approved", "asset", "a-1")
        uow.audit.record(pmm, "asset.rejected", "asset", "a-2")
        uow.audit.record(None, "catalog.reloaded", "catalog", "c-1")
    service = ActivityService(uow_factory)

    def actions(**filters: str) -> set[str]:
        return {e.action for e in service.list_events(AuditFilters(**filters)).items}

    assert actions(action_prefix="asset.") == {"asset.approved", "asset.rejected"}
    assert actions(action_prefix="asset.appr") == {"asset.approved"}
    assert actions(entity_type="catalog") == {"catalog.reloaded"}
    assert actions(entity_id="a-2") == {"asset.rejected"}
    assert actions(actor_id=PMM_ID) == {"asset.approved", "asset.rejected"}
    assert actions(actor_id=PMM_ID, entity_id="a-1") == {"asset.approved"}
    assert actions(actor_id=PMM_ID, entity_type="catalog") == set()
    assert actions(entity_type="nothing") == set()


def test_a_prefix_is_not_a_pattern(uow_factory: UnitOfWorkFactory) -> None:
    with uow_factory() as uow:
        uow.audit.record(None, "asset.approved", "asset", "a-1")
        uow.audit.record(None, "a_set.thing", "x", "x-1")
    service = ActivityService(uow_factory)
    assert service.list_events(AuditFilters(action_prefix="%")).items == []
    assert [e.action for e in service.list_events(AuditFilters(action_prefix="a_set")).items] == [
        "a_set.thing"
    ]


def test_my_events_are_only_mine_whatever_the_filter_says(
    uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    pmm = _pmm(uow_factory)
    with uow_factory() as uow:
        uow.audit.record(pmm, "mine.one", "thing", "t-1")
        uow.audit.record(None, "theirs.one", "thing", "t-2")
    service = ActivityService(uow_factory)
    assert [e.action for e in service.list_own_events(pmm, NO_FILTERS).items] == ["mine.one"]
    sneaky = AuditFilters(actor_id="someone-else")
    assert [e.action for e in service.list_own_events(pmm, sneaky).items] == ["mine.one"]


# ------------------------------------------------------------------ the identity events


def test_login_writes_one_event_with_the_provider(
    uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    IdentityService(uow_factory).record_login(_pmm(uow_factory), "dev")
    [event] = ActivityService(uow_factory).list_events(NO_FILTERS).items
    assert (event.action, event.entity_type, event.entity_id) == ("auth.login", "user", PMM_ID)
    assert (event.actor_user_id, event.details) == (PMM_ID, {"provider": "dev"})


def test_logout_writes_one_event(uow_factory: UnitOfWorkFactory, seeded: SeedSummary) -> None:
    IdentityService(uow_factory).record_logout(_pmm(uow_factory))
    [event] = ActivityService(uow_factory).list_events(NO_FILTERS).items
    assert (event.action, event.actor_user_id, event.entity_id) == ("auth.logout", PMM_ID, PMM_ID)


def test_a_denied_login_has_no_actor_and_names_the_user_tried(
    uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    IdentityService(uow_factory).record_login_denied("not-a-user", "dev")
    [event] = ActivityService(uow_factory).list_events(NO_FILTERS).items
    assert (event.action, event.actor_user_id, event.actor_display) == (
        "auth.login_denied",
        None,
        SYSTEM_ACTOR_DISPLAY,
    )
    assert (event.entity_type, event.entity_id, event.details) == ("user", "not-a-user", {"provider": "dev"})
