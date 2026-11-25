from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gtm_studio.auth.dev_users import load_dev_users
from gtm_studio.db.models.identity import Role, User, UserRole
from gtm_studio.domain.audit import SYSTEM_ACTOR_DISPLAY, AuditFilters
from gtm_studio.domain.identity import UserRecord
from gtm_studio.services.activity import ActivityService
from gtm_studio.services.identity import IdentityService, SeedError, SeedSummary
from gtm_studio.services.ports import UnitOfWorkFactory
from gtm_studio.settings import REPO_ROOT

ADMIN_ID = "00000000-0000-4000-8000-000000000001"
PMM_ID = "00000000-0000-4000-8000-000000000003"
DEV_USERS = REPO_ROOT / "config" / "dev_users.yaml"


def _write(path: Path, users: list[dict[str, object]]) -> Path:
    path.write_text(yaml.safe_dump({"users": users}), encoding="utf-8")
    return path


def _user(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "11111111-1111-4111-8111-111111111111",
        "email": "Zed@Example.test",
        "display_name": "Zed",
        "roles": ["zed_role"],
    }
    return base | overrides


def test_seeding_creates_the_demo_users_and_roles(
    uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    assert seeded == SeedSummary(users_created=5, users_updated=0, users_unchanged=0, roles_created=3)
    actor = IdentityService(uow_factory).get_actor(ADMIN_ID)
    assert actor is not None
    assert (actor.email, actor.display_name, actor.roles) == (
        "avery.admin@example.test",
        "Avery Admin",
        {"admin"},
    )


def test_the_system_roles_exist_before_any_seeding(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        roles = {r.key: (r.source, r.active) for r in session.scalars(select(Role))}
    assert roles == {"admin": ("system", True), "viewer": ("system", True)}


def test_seeded_roles_are_marked_dev_seed(migrated_engine: Engine, seeded: SeedSummary) -> None:
    with Session(migrated_engine) as session:
        sources = {r.key: r.source for r in session.scalars(select(Role))}
        grants = {g.source for g in session.scalars(select(UserRole))}
    assert sources == {
        "admin": "system",
        "viewer": "system",
        "pmm": "dev_seed",
        "product": "dev_seed",
        "cs": "dev_seed",
    }
    assert grants == {"dev_seed"}


def test_seeding_twice_changes_nothing(uow_factory: UnitOfWorkFactory, seeded: SeedSummary) -> None:
    again = IdentityService(uow_factory).seed_dev_users(load_dev_users(DEV_USERS))
    assert again == SeedSummary(users_created=0, users_updated=0, users_unchanged=5, roles_created=0)


def test_seeding_updates_a_changed_user_and_leaves_others_alone(
    uow_factory: UnitOfWorkFactory, tmp_path: Path
) -> None:
    service = IdentityService(uow_factory)
    path = _write(
        tmp_path / "users.yaml",
        [_user(), _user(id="22222222-2222-4222-8222-222222222222", email="y@example.test")],
    )
    assert service.seed_dev_users(load_dev_users(path)).users_created == 2

    _write(path, [_user(display_name="Zed Renamed", roles=["zed_role", "other"])])
    summary = service.seed_dev_users(load_dev_users(path))
    assert (summary.users_created, summary.users_updated, summary.users_unchanged) == (0, 1, 0)
    assert summary.roles_created == 1

    actor = service.get_actor("11111111-1111-4111-8111-111111111111")
    assert actor is not None
    assert (actor.display_name, actor.roles) == ("Zed Renamed", {"zed_role", "other"})
    assert service.get_actor("22222222-2222-4222-8222-222222222222") is not None  # not in the file: kept


def test_seeding_lowercases_the_email(uow_factory: UnitOfWorkFactory, tmp_path: Path) -> None:
    service = IdentityService(uow_factory)
    service.seed_dev_users(load_dev_users(_write(tmp_path / "users.yaml", [_user()])))
    with uow_factory() as uow:
        user = uow.identity.get_user_by_email("ZED@example.TEST")
    assert user is not None
    assert user.email == "zed@example.test"


@pytest.mark.parametrize(
    "bad",
    [
        {"id": "not-a-uuid"},
        {"email": "no-at-sign"},
        {"roles": []},
        {"roles": ["Has Space"]},
        {"display_name": ""},
        {"unexpected": "field"},
    ],
)
def test_a_malformed_seed_file_is_rejected_by_the_loader(tmp_path: Path, bad: dict[str, object]) -> None:
    path = _write(tmp_path / "users.yaml", [_user(id="33333333-3333-4333-8333-333333333333"), _user(**bad)])
    with pytest.raises(SeedError, match=r"users.yaml"):
        load_dev_users(path)


def test_an_inactive_user_gives_no_actor(uow_factory: UnitOfWorkFactory, seeded: SeedSummary) -> None:
    service = IdentityService(uow_factory)
    with uow_factory() as uow:
        record = uow.identity.get_user(PMM_ID)
        assert record is not None
        uow.identity.upsert_user(replace(record, is_active=False))
    assert service.get_actor(PMM_ID) is None
    assert PMM_ID not in {u.id for u in service.list_active_users()}


def test_an_unknown_user_gives_no_actor(uow_factory: UnitOfWorkFactory, seeded: SeedSummary) -> None:
    assert IdentityService(uow_factory).get_actor("99999999-9999-4999-8999-999999999999") is None


def test_a_deactivated_role_stops_granting_its_permissions(
    uow_factory: UnitOfWorkFactory, migrated_engine: Engine, seeded: SeedSummary
) -> None:
    with Session(migrated_engine) as session:
        session.get_one(Role, "pmm").active = False
        session.commit()
    actor = IdentityService(uow_factory).get_actor(PMM_ID)
    assert actor is not None
    assert actor.roles == frozenset()
    assert actor.permissions == frozenset()


def test_record_login_stamps_last_login_with_the_clock(
    uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    moment = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    service = IdentityService(uow_factory, clock=lambda: moment)
    actor = service.get_actor(ADMIN_ID)
    assert actor is not None
    service.record_login(actor, "dev")
    with uow_factory() as uow:
        user = uow.identity.get_user(ADMIN_ID)
    assert user is not None
    assert user.last_login_at == moment


def test_email_and_provider_subject_are_unique(migrated_engine: Engine, seeded: SeedSummary) -> None:
    with Session(migrated_engine) as session:
        session.add(User(email="AVERY.ADMIN@example.test", display_name="Dup", auth_provider="dev"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(
            User(email="a@example.test", display_name="A", auth_provider="oidc", auth_subject="sub-1")
        )
        session.add(
            User(email="b@example.test", display_name="B", auth_provider="oidc", auth_subject="sub-1")
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_lookups_by_email_and_subject(uow_factory: UnitOfWorkFactory, migrated_engine: Engine) -> None:
    with uow_factory() as uow:
        uow.identity.upsert_user(
            UserRecord(
                id="44444444-4444-4444-8444-444444444444",
                email="Oidc.Person@Example.test",
                display_name="Oidc Person",
                is_active=True,
                auth_provider="oidc",
                auth_subject="sub-123",
                roles=frozenset(),
            )
        )
    with uow_factory() as uow:
        assert uow.identity.get_user_by_subject("oidc", "sub-123") is not None
        assert uow.identity.get_user_by_subject("dev", "sub-123") is None
        found = uow.identity.get_user_by_email(" oidc.person@example.test ")
        assert found is not None
        assert found.id == "44444444-4444-4444-8444-444444444444"


def test_a_failed_unit_of_work_rolls_back(uow_factory: UnitOfWorkFactory, seeded: SeedSummary) -> None:
    with pytest.raises(RuntimeError, match="boom"), uow_factory() as uow:
        uow.identity.set_roles(PMM_ID, ["viewer"], source="dev_seed")
        raise RuntimeError("boom")
    actor = IdentityService(uow_factory).get_actor(PMM_ID)
    assert actor is not None
    assert actor.roles == {"pmm"}


def test_a_seed_email_that_belongs_to_another_user_is_a_clear_error(
    uow_factory: UnitOfWorkFactory, seeded: SeedSummary, tmp_path: Path
) -> None:
    path = _write(tmp_path / "users.yaml", [_user(email="avery.admin@example.test")])
    with pytest.raises(SeedError, match="already belongs to a different user"):
        IdentityService(uow_factory).seed_dev_users(load_dev_users(path))


def test_a_missing_or_unparsable_seed_file_is_a_seed_error(tmp_path: Path) -> None:
    with pytest.raises(SeedError):
        load_dev_users(tmp_path / "nope.yaml")
    broken = tmp_path / "broken.yaml"
    broken.write_text("users: [unclosed", encoding="utf-8")
    with pytest.raises(SeedError):
        load_dev_users(broken)


# ------------------------------------------------------------------ seeding is audited (ADR-0006)


def _seed_events(uow_factory: UnitOfWorkFactory) -> list[tuple[str, str, dict[str, object]]]:
    """(action, entity_id, details) of every event, oldest first, after checking each has no actor."""
    events = ActivityService(uow_factory).list_events(AuditFilters(), limit=100).items
    assert {(e.actor_user_id, e.actor_display) for e in events} <= {(None, SYSTEM_ACTOR_DISPLAY)}
    return [(e.action, e.entity_id, e.details) for e in reversed(events)]


def test_seeding_a_fresh_database_audits_each_user_and_their_roles(
    uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    events = _seed_events(uow_factory)
    seeded_ids = [entity for action, entity, _ in events if action == "user.seeded"]
    assert len(seeded_ids) == 5
    assert {details["provider"] for action, _, details in events if action == "user.seeded"} == {"dev"}
    roles_set = {entity: details for action, entity, details in events if action == "user.roles_set"}
    assert set(roles_set) == set(seeded_ids)
    assert roles_set[ADMIN_ID] == {"added": ["admin"], "removed": []}
    assert {action for action, _, _ in events} == {"user.seeded", "user.roles_set"}


def test_seeding_again_unchanged_audits_nothing(uow_factory: UnitOfWorkFactory, seeded: SeedSummary) -> None:
    before = len(_seed_events(uow_factory))
    IdentityService(uow_factory).seed_dev_users(load_dev_users(DEV_USERS))
    assert len(_seed_events(uow_factory)) == before


def test_seeding_a_changed_user_audits_the_change(uow_factory: UnitOfWorkFactory, tmp_path: Path) -> None:
    service = IdentityService(uow_factory)
    path = _write(tmp_path / "users.yaml", [_user()])
    service.seed_dev_users(load_dev_users(path))
    first = len(_seed_events(uow_factory))

    _write(path, [_user(display_name="Zed Renamed", roles=["other"])])
    service.seed_dev_users(load_dev_users(path))
    zed = "11111111-1111-4111-8111-111111111111"
    assert _seed_events(uow_factory)[first:] == [
        ("user.updated", zed, {"provider": "dev", "fields": ["display_name"]}),
        ("user.roles_set", zed, {"added": ["other"], "removed": ["zed_role"]}),
    ]


def test_a_failed_seed_writes_no_events(
    uow_factory: UnitOfWorkFactory, seeded: SeedSummary, tmp_path: Path
) -> None:
    before = len(_seed_events(uow_factory))
    seeds = load_dev_users(
        _write(tmp_path / "users.yaml", [_user(), _user(id=PMM_ID, email="avery.admin@example.test")])
    )
    with pytest.raises(SeedError):
        IdentityService(uow_factory).seed_dev_users(seeds)
    assert len(_seed_events(uow_factory)) == before  # the first user's events rolled back with it


def test_user_exists_sees_inactive_users_too(uow_factory: UnitOfWorkFactory, seeded: SeedSummary) -> None:
    service = IdentityService(uow_factory)
    with uow_factory() as uow:
        record = uow.identity.get_user(PMM_ID)
        assert record is not None
        uow.identity.upsert_user(replace(record, is_active=False))
    assert service.user_exists(PMM_ID)
    assert not service.user_exists("99999999-9999-4999-8999-999999999999")
