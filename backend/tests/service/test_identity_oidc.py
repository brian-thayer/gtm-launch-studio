"""The identity service's OIDC use cases: just-in-time provisioning and role sync (S09). The HTTP flow
that calls them is in tests/api/test_oidc.py."""

from dataclasses import replace

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from structlog.testing import capture_logs

from gtm_studio.db.models.identity import Role, UserRole
from gtm_studio.domain.audit import AuditFilters
from gtm_studio.services.identity import IdentityService, SeedSummary, UserConflictError
from gtm_studio.services.ports import UnitOfWorkFactory

PMM_ID = "00000000-0000-4000-8000-000000000003"


def _events(uow_factory: UnitOfWorkFactory) -> list[tuple[str, dict[str, object]]]:
    """(action, details) of every audit event, oldest first."""
    with uow_factory() as uow:
        return [(e.action, e.details) for e in reversed(uow.audit.query(AuditFilters(), None, 100).items)]


def _grants(engine: Engine, user_id: str) -> dict[str, str]:
    """role key -> where the grant came from. Includes grants to roles that are switched off."""
    with Session(engine) as session:
        rows = session.execute(select(UserRole.role_key, UserRole.source).where(UserRole.user_id == user_id))
        return {role_key: source for role_key, source in rows}


def test_a_new_oidc_user_is_provisioned_once_and_an_unchanged_one_is_left_alone(
    uow_factory: UnitOfWorkFactory, migrated_engine: Engine
) -> None:
    service = IdentityService(uow_factory)
    created = service.upsert_oidc_user(subject="sub-1", email=" Ada@Example.test ", display_name="Ada")
    assert (created.email, created.auth_provider, created.auth_subject) == (
        "ada@example.test",
        "oidc",
        "sub-1",
    )
    assert created.is_active
    assert created.roles == frozenset()
    again = service.upsert_oidc_user(subject="sub-1", email="ada@example.test", display_name="Ada")
    assert again.id == created.id
    assert [action for action, _ in _events(uow_factory)] == ["user.provisioned"]


def test_an_email_owned_by_another_user_is_a_conflict_and_nothing_is_written(
    uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    with pytest.raises(UserConflictError):
        IdentityService(uow_factory).upsert_oidc_user(
            subject="sub-1", email="Avery.Admin@example.test", display_name="Not Avery"
        )
    assert _events(uow_factory) == []
    with uow_factory() as uow:
        assert uow.identity.get_user_by_subject("oidc", "sub-1") is None


def test_an_oidc_user_is_never_matched_by_email_to_a_different_subject(
    uow_factory: UnitOfWorkFactory, migrated_engine: Engine
) -> None:
    service = IdentityService(uow_factory)
    service.upsert_oidc_user(subject="sub-1", email="ada@example.test", display_name="Ada")
    with pytest.raises(UserConflictError):  # the same mailbox under a new subject is not the same person
        service.upsert_oidc_user(subject="sub-2", email="ada@example.test", display_name="Ada")


def test_a_deactivated_oidc_user_is_returned_as_left(
    uow_factory: UnitOfWorkFactory, migrated_engine: Engine
) -> None:
    service = IdentityService(uow_factory)
    created = service.upsert_oidc_user(subject="sub-1", email="ada@example.test", display_name="Ada")
    with uow_factory() as uow:
        uow.identity.upsert_user(replace(created, is_active=False))
    left = service.upsert_oidc_user(subject="sub-1", email="new@example.test", display_name="Renamed")
    assert (left.is_active, left.email, left.display_name) == (False, "ada@example.test", "Ada")
    assert [action for action, _ in _events(uow_factory)] == ["user.provisioned"]


def test_a_deactivated_user_is_refused_as_inactive_even_when_their_new_email_is_taken(
    uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    service = IdentityService(uow_factory)
    created = service.upsert_oidc_user(subject="sub-1", email="ada@example.test", display_name="Ada")
    with uow_factory() as uow:
        uow.identity.upsert_user(replace(created, is_active=False))
    left = service.upsert_oidc_user(subject="sub-1", email="avery.admin@example.test", display_name="Ada")
    assert (left.id, left.is_active) == (
        created.id,
        False,
    )  # not a UserConflictError: the reason is "inactive"


def test_sync_roles_changes_only_its_own_source_and_audits_only_a_change(
    uow_factory: UnitOfWorkFactory, migrated_engine: Engine, seeded: SeedSummary
) -> None:
    service = IdentityService(uow_factory)
    user = service.upsert_oidc_user(subject="sub-1", email="ada@example.test", display_name="Ada")
    with uow_factory() as uow:  # `cs` was given by hand
        uow.identity.sync_source_roles(user.id, ["cs"], source="dev_seed")

    first = service.sync_roles(user.id, ["pmm", "viewer"], "oidc")
    assert (first.added, first.removed) == ({"pmm", "viewer"}, frozenset())
    assert _grants(migrated_engine, user.id) == {"cs": "dev_seed", "pmm": "oidc", "viewer": "oidc"}

    second = service.sync_roles(user.id, ["product", "viewer"], "oidc")
    assert (second.added, second.removed) == ({"product"}, {"pmm"})
    assert _grants(migrated_engine, user.id) == {"cs": "dev_seed", "product": "oidc", "viewer": "oidc"}

    third = service.sync_roles(user.id, ["product", "viewer"], "oidc")  # nothing to do, so nothing audited
    assert (third.added, third.removed) == (frozenset(), frozenset())
    synced = [details for action, details in _events(uow_factory) if action == "user.roles_synced"]
    assert synced == [
        {"source": "oidc", "added": ["pmm", "viewer"], "removed": []},
        {"source": "oidc", "added": ["product"], "removed": ["pmm"]},
    ]


def test_a_role_held_by_hand_stays_when_the_idp_stops_asking_for_it(
    uow_factory: UnitOfWorkFactory, migrated_engine: Engine, seeded: SeedSummary
) -> None:
    service = IdentityService(uow_factory)
    user = service.upsert_oidc_user(subject="sub-1", email="ada@example.test", display_name="Ada")
    with uow_factory() as uow:
        uow.identity.sync_source_roles(user.id, ["pmm"], source="dev_seed")
    service.sync_roles(user.id, ["pmm"], "oidc")  # already held: not granted a second time
    service.sync_roles(user.id, [], "oidc")
    assert _grants(migrated_engine, user.id) == {"pmm": "dev_seed"}


def test_an_unknown_role_is_created_inactive_and_logged_never_granted(
    uow_factory: UnitOfWorkFactory, migrated_engine: Engine
) -> None:
    service = IdentityService(uow_factory)
    user = service.upsert_oidc_user(subject="sub-1", email="ada@example.test", display_name="Ada")
    with capture_logs() as logs:
        service.sync_roles(user.id, ["growth"], "oidc")
    assert [(e["log_level"], e["role"]) for e in logs] == [("warning", "growth")]

    assert _grants(migrated_engine, user.id) == {"growth": "oidc"}  # the grant exists, the role is off
    actor = service.get_actor(user.id)
    assert actor is not None
    assert actor.roles == frozenset()
    assert actor.permissions == frozenset()
    with Session(migrated_engine) as session:
        role = session.get(Role, "growth")
        assert role is not None
        assert (role.active, role.source) == (False, "oidc")


def test_sync_roles_refuses_a_malformed_key_before_changing_anything(
    uow_factory: UnitOfWorkFactory, migrated_engine: Engine
) -> None:
    service = IdentityService(uow_factory)
    user = service.upsert_oidc_user(subject="sub-1", email="ada@example.test", display_name="Ada")
    with pytest.raises(ValueError, match="role key"):
        service.sync_roles(user.id, ["viewer", "Not A Key"], "oidc")
    assert _grants(migrated_engine, user.id) == {}


def test_login_audit_details_carry_the_provider_the_roles_and_the_denial_reason(
    uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    service = IdentityService(uow_factory)
    actor = service.get_actor(PMM_ID)
    assert actor is not None
    service.record_login(actor, "oidc", roles_synced={"viewer", "pmm"})
    service.record_login(actor, "dev")
    service.record_login_denied("sub-9", "oidc", "inactive")
    service.record_login_denied("not-a-user", "dev")
    assert _events(uow_factory) == [
        ("auth.login", {"provider": "oidc", "roles_synced": ["pmm", "viewer"]}),
        ("auth.login", {"provider": "dev"}),
        ("auth.login_denied", {"provider": "oidc", "reason": "inactive"}),
        ("auth.login_denied", {"provider": "dev"}),
    ]
