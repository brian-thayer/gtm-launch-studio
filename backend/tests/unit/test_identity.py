import pytest

from gtm_studio.domain.identity import (
    SYSTEM_ROLES,
    Actor,
    Permission,
    can_approve,
    permissions_for,
)


def _actor(*roles: str) -> Actor:
    return Actor(id="u1", email="u1@example.test", display_name="U One", roles=frozenset(roles))


def test_system_roles() -> None:
    assert sorted(SYSTEM_ROLES) == ["admin", "viewer"]


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
