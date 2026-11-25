"""The pure parts of the OIDC sign-in: the redirect-target guard, the group -> role map and its file."""

from pathlib import Path

import pytest

from gtm_studio.auth.oidc import MAX_NEXT_LENGTH, RoleMapError, load_role_map, safe_next
from gtm_studio.domain.identity import OidcRoleMap
from gtm_studio.settings import REPO_ROOT

# ---------------------------------------------------------------- safe_next


@pytest.mark.parametrize("value", ["/", "/activity", "/activity?action_prefix=auth.&x=1", "/a/b#frag"])
def test_a_path_on_this_site_is_kept(value: str) -> None:
    assert safe_next(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "//evil.example",
        "/\\evil.example",
        "/ok\\../../evil",
        "/\t/evil.example",  # browsers drop the tab and read //evil.example
        "/\n/evil.example",
        "/\x00",
        "/\x7f",
        "https://evil.example",
        "javascript:alert(1)",
        "evil",
        "",
        "/" + "a" * MAX_NEXT_LENGTH,  # one over the cap: it travels in a cookie
        None,
        42,
        ["/ok"],
    ],
)
def test_anything_else_becomes_the_home_page(value: object) -> None:
    assert safe_next(value) == "/"


def test_the_longest_allowed_path_is_kept() -> None:
    path = "/" + "a" * (MAX_NEXT_LENGTH - 1)
    assert safe_next(path) == path


# ---------------------------------------------------------------- OidcRoleMap


def _map() -> OidcRoleMap:
    return OidcRoleMap(
        group_to_roles={"pmm-group": frozenset({"pmm"}), "both": frozenset({"pmm", "cs"})},
        default_roles=frozenset({"viewer"}),
    )


def test_a_person_gets_the_union_of_their_groups_roles() -> None:
    assert _map().roles_for(["pmm-group", "both", "unmapped"]) == {"pmm", "cs"}


def test_a_person_in_no_mapped_group_gets_the_default_roles() -> None:
    assert _map().roles_for([]) == {"viewer"}
    assert _map().roles_for(["unmapped"]) == {"viewer"}


def test_defaults_are_not_added_to_mapped_roles() -> None:
    assert "viewer" not in _map().roles_for(["pmm-group"])


def test_groups_match_exactly_and_case_sensitively() -> None:
    assert _map().roles_for(["PMM-GROUP", " pmm-group"]) == {"viewer"}


def test_no_default_roles_means_no_roles() -> None:
    assert OidcRoleMap(group_to_roles={}, default_roles=frozenset()).roles_for(["x"]) == frozenset()


# ---------------------------------------------------------------- load_role_map


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "oidc_roles.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_example_file_loads() -> None:
    role_map = load_role_map(REPO_ROOT / "config" / "oidc_roles.example.yaml")
    assert role_map.default_roles == {"viewer"}
    assert role_map.group_to_roles["<another group>"] == {"product", "cs"}


def test_an_empty_file_is_an_empty_map(tmp_path: Path) -> None:
    role_map = load_role_map(_write(tmp_path, ""))
    assert (dict(role_map.group_to_roles), role_map.default_roles) == ({}, frozenset())


@pytest.mark.parametrize(
    "text",
    [
        "group_to_roles: [unclosed",  # not YAML
        "group_to_roles: [a, b]",  # a list, not a mapping
        "group_to_roles: {g: pmm}",  # roles must be a list
        "group_to_roles: {g: [Not A Key]}",
        "group_to_roles: {'': [pmm]}",
        "default_roles: [VIEWER]",
        "group_to_role: {g: [pmm]}",  # a typo must not silently give nobody any roles
    ],
)
def test_a_malformed_file_is_a_role_map_error_naming_the_file(tmp_path: Path, text: str) -> None:
    path = _write(tmp_path, text)
    with pytest.raises(RoleMapError, match=r"oidc_roles\.yaml"):
        load_role_map(path)


def test_a_missing_file_is_a_role_map_error(tmp_path: Path) -> None:
    with pytest.raises(RoleMapError, match=r"nope\.yaml"):
        load_role_map(tmp_path / "nope.yaml")
