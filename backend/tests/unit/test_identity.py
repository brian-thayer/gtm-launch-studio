import pytest

from gtm_studio.domain.identity import (
    SYSTEM_ROLES,
    Actor,
    Permission,
    can_approve,
    check_role_key,
    permissions_for,
    role_kind,
)


def _actor(*roles: str) -> Actor:
    return Actor(id="u1", email="u1@example.test", display_name="U One", roles=frozenset(roles))


def test_system_roles() -> None:
    assert sorted(SYSTEM_ROLES) == ["admin", "viewer"]


@pytest.mark.parametrize(
    ("role", "kind"),
    [("admin", "system"), ("viewer", "system"), ("pmm", "approver"), ("role_a", "approver")],
)
def test_role_kind_is_system_only_for_the_two_system_roles(role: str, kind: str) -> None:
    assert role_kind(role) == kind


def test_admin_has_every_permission() -> None:
    assert permissions_for(["admin"]) == frozenset(Permission)


def test_viewer_can_only_read() -> None:
    assert permissions_for(["viewer"]) == {Permission.SOLUTION_READ, Permission.CATALOG_READ}


@pytest.mark.parametrize("role", ["pmm", "product", "cs", "anything_else"])
def test_any_other_role_is_an_approver_role(role: str) -> None:
    assert permissions_for([role]) == {
        Permission.SOLUTION_READ,
        Permission.CATALOG_READ,
        Permission.CONTEXT_WRITE,
        Permission.IMPORT_RUN,
        Permission.ASSET_GENERATE,
        Permission.ASSET_REVIEW,
    }


def test_approvers_cannot_read_the_audit_log_or_administer() -> None:
    held = permissions_for(["pmm"])
    assert not held & {Permission.AUDIT_READ, Permission.CATALOG_ADMIN, Permission.USER_ADMIN}


def test_permissions_are_the_union_of_the_roles() -> None:
    assert permissions_for(["viewer", "pmm"]) == permissions_for(["pmm"])
    assert permissions_for(["viewer", "admin"]) == frozenset(Permission)


def test_no_roles_means_no_permissions() -> None:
    assert permissions_for([]) == frozenset()


def test_actor_permissions_follow_its_roles() -> None:
    assert _actor("viewer").permissions == permissions_for(["viewer"])


def test_can_approve_when_the_actor_holds_an_approver_role() -> None:
    assert can_approve(_actor("pmm"), ["pmm", "product"])
    assert can_approve(_actor("viewer", "cs"), {"cs"})


def test_cannot_approve_without_one_of_the_roles() -> None:
    assert not can_approve(_actor("cs"), ["pmm", "product"])
    assert not can_approve(_actor("pmm"), [])


def test_admin_without_the_role_cannot_approve() -> None:
    """Separation of duties: administering the app does not let you approve a gate's assets."""
    assert not can_approve(_actor("admin"), ["pmm", "product"])


def test_admin_who_also_holds_the_role_can_approve() -> None:
    assert can_approve(_actor("admin", "pmm"), ["pmm"])


def test_a_viewer_cannot_approve_even_if_a_gate_lists_viewer() -> None:
    assert not can_approve(_actor("viewer"), ["viewer"])


@pytest.mark.parametrize("key", ["pmm", "a", "growth_2", "a" * 50])
def test_check_role_key_returns_a_valid_key(key: str) -> None:
    assert check_role_key(key) == key


@pytest.mark.parametrize("key", ["", "Pmm", "2pmm", "has space", "pmm-lead", "a" * 51])
def test_check_role_key_rejects_anything_else(key: str) -> None:
    with pytest.raises(ValueError, match=r"invalid role key .*: must be lowercase letters"):
        check_role_key(key)
