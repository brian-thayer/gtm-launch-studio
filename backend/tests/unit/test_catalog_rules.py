"""The catalog validator: one test per error rule, each breaking ``catalog_min`` in memory (no files)."""

from typing import Any

import pytest

from gtm_studio.domain.catalog import Catalog, GoldExample, Issue, RoleDef
from gtm_studio.domain.catalog_rules import validate

FAMILIES = {"generic_doc", "classification"}


# ------------------------------------------------------------------ helpers
def _issues(catalog: Catalog, *, strict: bool = False) -> list[Issue]:
    return validate(catalog, families=FAMILIES, strict=strict)


def _only(catalog: Catalog, where: str, text: str, *, level: str = "error") -> None:
    """The catalog has exactly one problem: ``text`` at ``where``."""
    issues = _issues(catalog)
    assert [(i.level, i.where) for i in issues] == [(level, where)], issues
    assert text in issues[0].message


def _has(catalog: Catalog, where: str, text: str) -> None:
    issues = _issues(catalog)
    assert any(i.level == "error" and i.where == where and text in i.message for i in issues), issues


def _swap[T](items: list[T], key: str, update: dict[str, Any]) -> list[T]:
    return [item.model_copy(update=update) if item.key == key else item for item in items]  # type: ignore[attr-defined]


def _lifecycle(catalog: Catalog, **update: Any) -> Catalog:
    return catalog.model_copy(update={"lifecycle": catalog.lifecycle.model_copy(update=update)})


def _tiers(catalog: Catalog, **update: Any) -> Catalog:
    return catalog.model_copy(update={"tiers": catalog.tiers.model_copy(update=update)})


def _gate(catalog: Catalog, key: str, **update: Any) -> Catalog:
    return _lifecycle(catalog, gates=_swap(catalog.lifecycle.gates, key, update))


def _tier(catalog: Catalog, key: str, **update: Any) -> Catalog:
    return _tiers(catalog, tiers=_swap(catalog.tiers.tiers, key, update))


def _trigger(catalog: Catalog, key: str, **update: Any) -> Catalog:
    return _tiers(catalog, triggers=_swap(catalog.tiers.triggers, key, update))


def _asset(catalog: Catalog, key: str, **update: Any) -> Catalog:
    asset = catalog.asset_types[key].model_copy(update=update)
    return catalog.model_copy(update={"asset_types": {**catalog.asset_types, key: asset}})


def _spec(catalog: Catalog, key: str, **update: Any) -> Catalog:
    return _asset(catalog, key, spec=catalog.asset_types[key].spec.model_copy(update=update))


def _without(catalog: Catalog, key: str) -> Catalog:
    return catalog.model_copy(
        update={"asset_types": {k: v for k, v in catalog.asset_types.items() if k != key}}
    )


# -------------------------------------------------------------------- clean
def test_catalog_min_has_no_issues_even_when_strict(catalog_min: Catalog) -> None:
    assert _issues(catalog_min, strict=True) == []


# --------------------------------------------------------- duplicate keys
def test_duplicate_role_keys(catalog_min: Catalog) -> None:
    roles = [*catalog_min.lifecycle.roles, RoleDef(key="role_a", label="Again")]
    _only(_lifecycle(catalog_min, roles=roles), "lifecycle.yaml: roles", "duplicate role key 'role_a'")


def test_duplicate_gate_keys(catalog_min: Catalog) -> None:
    again = catalog_min.gate("gate_one").model_copy(update={"order": 9})  # the copy's order wins lookups
    broken = _lifecycle(catalog_min, gates=[*catalog_min.lifecycle.gates, again])
    _has(broken, "lifecycle.yaml: gates", "duplicate gate key 'gate_one'")


def test_duplicate_tier_keys(catalog_min: Catalog) -> None:
    again = catalog_min.tier("tier_big").model_copy(update={"rank": 9})
    _only(
        _tiers(catalog_min, tiers=[*catalog_min.tiers.tiers, again]),
        "tiers.yaml: tiers",
        "duplicate tier key 'tier_big'",
    )


def test_duplicate_trigger_keys(catalog_min: Catalog) -> None:
    triggers = [*catalog_min.tiers.triggers, catalog_min.tiers.triggers[0]]
    _only(
        _tiers(catalog_min, triggers=triggers), "tiers.yaml: triggers", "duplicate trigger key 'needs_setup'"
    )


def test_a_context_key_filed_twice(catalog_min: Catalog) -> None:
    keys = {**catalog_min.context_keys, "facts.copy": catalog_min.context_keys["facts.summary"]}
    broken = catalog_min.model_copy(update={"context_keys": keys})
    _has(broken, "context_keys.yaml", "duplicate context key 'facts.summary'")
    _has(broken, "context_keys.yaml", "filed as 'facts.copy'")


def test_an_asset_type_filed_twice(catalog_min: Catalog) -> None:
    types = {**catalog_min.asset_types, "copy": catalog_min.asset_types["brief"]}
    broken = catalog_min.model_copy(update={"asset_types": types})
    _has(broken, "asset_types", "duplicate asset type 'brief'")
    _has(broken, "asset_types", "filed as 'copy'")


def test_gate_orders_must_be_unique(catalog_min: Catalog) -> None:
    _only(_gate(catalog_min, "gate_two", order=1), "lifecycle.yaml: gates", "share order 1")


def test_tier_ranks_must_be_unique(catalog_min: Catalog) -> None:
    _only(_tier(catalog_min, "tier_small", rank=1), "tiers.yaml: tiers", "share rank 1")


# -------------------------------------------------------------------- roles
def test_a_role_key_with_the_wrong_shape(catalog_min: Catalog) -> None:
    roles = [*catalog_min.lifecycle.roles, RoleDef(key="Bad Role", label="x")]
    _only(_lifecycle(catalog_min, roles=roles), "lifecycle.yaml: roles[Bad Role]", "invalid role key")


def test_a_role_key_with_the_wrong_shape_in_an_approver_list(catalog_min: Catalog) -> None:
    gate = _gate(catalog_min, "gate_one", approver_roles=["Role A"])
    _only(gate, "lifecycle.yaml: gates[gate_one].approver_roles", "invalid role key")
    spec = _spec(catalog_min, "brief", approver_roles=["Role A"])
    _only(spec, "asset_types/brief/spec.yaml: approver_roles", "invalid role key")


def test_a_system_role_cannot_be_declared_as_an_approver_role(catalog_min: Catalog) -> None:
    roles = [*catalog_min.lifecycle.roles, RoleDef(key="viewer", label="Viewer")]
    _only(_lifecycle(catalog_min, roles=roles), "lifecycle.yaml: roles[viewer]", "system role")


def test_admin_cannot_approve_a_gate(catalog_min: Catalog) -> None:
    broken = _gate(catalog_min, "gate_one", approver_roles=["role_a", "admin"])
    _only(broken, "lifecycle.yaml: gates[gate_one].approver_roles", "'admin' is a system role")


def test_a_system_role_cannot_approve_one_asset_either(catalog_min: Catalog) -> None:
    broken = _spec(catalog_min, "brief", approver_roles=["viewer"])
    _only(broken, "asset_types/brief/spec.yaml: approver_roles", "'viewer' is a system role")


def test_a_gate_approver_role_must_be_declared(catalog_min: Catalog) -> None:
    broken = _gate(catalog_min, "gate_one", approver_roles=["role_a", "role_z"])
    _only(broken, "lifecycle.yaml: gates[gate_one].approver_roles", "role 'role_z' is not declared")


def test_an_asset_approver_role_must_be_declared(catalog_min: Catalog) -> None:
    broken = _spec(catalog_min, "brief", approver_roles=["role_z"])
    _only(broken, "asset_types/brief/spec.yaml: approver_roles", "role 'role_z' is not declared")


def test_a_gate_needs_an_approver_role(catalog_min: Catalog) -> None:
    broken = _gate(catalog_min, "gate_one", approver_roles=[])
    _only(broken, "lifecycle.yaml: gates[gate_one].approver_roles", "has no approver roles")


def test_an_empty_asset_override_means_nobody_can_approve(catalog_min: Catalog) -> None:
    _only(
        _spec(catalog_min, "brief", approver_roles=[]),
        "asset_types/brief/spec.yaml: approver_roles",
        "nobody",
    )


# ------------------------------------------------------------ asset types
def test_an_unknown_gate(catalog_min: Catalog) -> None:
    _only(_spec(catalog_min, "brief", gate="nowhere"), "asset_types/brief/spec.yaml: gate", "unknown gate")


def test_an_unknown_family(catalog_min: Catalog) -> None:
    _only(_spec(catalog_min, "brief", family="poster"), "asset_types/brief/spec.yaml: family", "'poster'")


def test_an_unknown_dependency(catalog_min: Catalog) -> None:
    broken = _spec(catalog_min, "deep_dive", depends_on=["ghost"])
    _only(broken, "asset_types/deep_dive/spec.yaml: depends_on", "unknown dependency 'ghost'")


def test_a_dependency_cycle(catalog_min: Catalog) -> None:
    broken = _spec(catalog_min, "brief", depends_on=["deep_dive"])  # deep_dive already depends on brief
    _has(broken, "asset_types/brief/spec.yaml: depends_on", "cycle: brief -> deep_dive -> brief")


def test_an_asset_cannot_depend_on_itself(catalog_min: Catalog) -> None:
    _has(
        _spec(catalog_min, "brief", depends_on=["brief"]),
        "asset_types/brief/spec.yaml: depends_on",
        "cycle: brief -> brief",
    )


def test_a_dependency_on_a_later_gate(catalog_min: Catalog) -> None:
    broken = _spec(
        catalog_min, "brief", depends_on=["extra_note"]
    )  # brief is at gate_one, extra_note at gate_two
    _has(broken, "asset_types/brief/spec.yaml: depends_on", "'extra_note' is at a later gate")


def test_an_unknown_required_context_key(catalog_min: Catalog) -> None:
    broken = _spec(catalog_min, "brief", required_context=["facts.ghost"])
    _only(broken, "asset_types/brief/spec.yaml: required_context", "unknown context key 'facts.ghost'")


def test_more_than_one_asset_decides_the_tier(catalog_min: Catalog) -> None:
    _has(
        _spec(catalog_min, "brief", decides="tier"),
        "asset_types/classify/spec.yaml: decides",
        "more than one",
    )


def test_the_asset_that_decides_the_tier_must_be_foundation(catalog_min: Catalog) -> None:
    broken = _spec(catalog_min, "classify", foundation=False)
    _only(broken, "asset_types/classify/spec.yaml: decides", "must be foundation")


def test_a_rubric_threshold_outside_1_to_5(catalog_min: Catalog) -> None:
    for threshold in (0, 6):
        rubric = catalog_min.asset_types["brief"].rubric.model_copy(update={"pass_threshold": threshold})
        _only(_asset(catalog_min, "brief", rubric=rubric), "asset_types/brief/rubric.md", "outside 1 to 5")


def test_a_rubric_needs_criteria(catalog_min: Catalog) -> None:
    rubric = catalog_min.asset_types["brief"].rubric.model_copy(update={"criteria": []})
    _only(_asset(catalog_min, "brief", rubric=rubric), "asset_types/brief/rubric.md", "no criteria")


def test_a_gold_example_must_be_redacted(catalog_min: Catalog) -> None:
    example: GoldExample = catalog_min.asset_types["brief"].examples[0].model_copy(update={"redacted": False})
    _only(
        _asset(catalog_min, "brief", examples=[example]),
        "asset_types/brief/examples/sample.md",
        "redacted: true",
    )


# ----------------------------------------------------------- tiers, triggers
def test_a_trigger_context_key_must_exist(catalog_min: Catalog) -> None:
    broken = _trigger(catalog_min, "needs_setup", context_key="facts.ghost")
    _only(broken, "tiers.yaml: triggers[needs_setup].context_key", "unknown context key")


def test_a_trigger_context_key_must_be_boolean(catalog_min: Catalog) -> None:
    broken = _trigger(catalog_min, "needs_setup", context_key="facts.summary")
    _only(broken, "tiers.yaml: triggers[needs_setup].context_key", "must be boolean")


def test_a_timing_anchor_must_exist(catalog_min: Catalog) -> None:
    timing = catalog_min.tier("tier_big").timing
    assert timing is not None
    broken = _tier(catalog_min, "tier_big", timing=timing.model_copy(update={"anchor": "facts.ghost"}))
    _only(broken, "tiers.yaml: tiers[tier_big].timing.anchor", "unknown context key")


def test_a_timing_anchor_must_be_a_date(catalog_min: Catalog) -> None:
    timing = catalog_min.tier("tier_big").timing
    assert timing is not None
    broken = _tier(catalog_min, "tier_big", timing=timing.model_copy(update={"anchor": "facts.summary"}))
    _only(broken, "tiers.yaml: tiers[tier_big].timing.anchor", "must be date")


def test_a_trigger_cannot_name_an_unknown_tier(catalog_min: Catalog) -> None:
    broken = _trigger(catalog_min, "needs_setup", tiers=["tier_big", "tier_ghost"])
    _only(broken, "tiers.yaml: triggers[needs_setup].tiers", "unknown tier 'tier_ghost'")


def test_an_asset_cannot_be_core_and_optional_in_one_tier(catalog_min: Catalog) -> None:
    broken = _tier(catalog_min, "tier_big", optional=["extra_note", "deep_dive"])
    _only(broken, "tiers.yaml: tiers[tier_big].optional", "'deep_dive' is in both core and optional")


# ----------------------------------------------------------------- lifecycle, brand
def test_approved_gate_values_cannot_be_empty(catalog_min: Catalog) -> None:
    _only(_lifecycle(catalog_min, approved_gate_values=[]), "lifecycle.yaml: approved_gate_values", "empty")


@pytest.mark.parametrize("name", ["voice", "claims", "legal"])
def test_a_brand_file_cannot_be_blank(catalog_min: Catalog, name: str) -> None:
    brand = catalog_min.brand.model_copy(update={f"{name}_md": " \n\t "})
    _only(catalog_min.model_copy(update={"brand": brand}), f"brand/{name}.md", "empty")


# ----------------------------------------------------------------- warnings
def _no_tier_decider(catalog: Catalog) -> Catalog:
    return _spec(catalog, "classify", decides=None)


def _unreferenced(catalog: Catalog) -> Catalog:
    return _tier(catalog, "tier_big", optional=[])  # extra_note was only an optional asset


def _no_gold_examples(catalog: Catalog) -> Catalog:
    return _asset(catalog, "brief", examples=[])


def _missing_folder(catalog: Catalog) -> Catalog:
    return _without(catalog, "extra_note")  # tier_big still lists it as optional


def _empty_tier(catalog: Catalog) -> Catalog:
    return _tiers(_tier(catalog, "tier_small", core=[]), inherits_lower=False)


WARNINGS = [
    (_missing_folder, "no asset type folder"),
    (_no_tier_decider, "no asset type decides the tier"),
    (_unreferenced, "is in no tier and no trigger"),
    (_no_gold_examples, "no gold examples"),
    (_empty_tier, "has no core assets"),
]


@pytest.mark.parametrize(("break_it", "text"), WARNINGS, ids=[text for _, text in WARNINGS])
def test_a_warning_becomes_an_error_when_strict(catalog_min: Catalog, break_it: Any, text: str) -> None:
    broken = break_it(catalog_min)
    loose = [i for i in _issues(broken) if text in i.message]
    strict = [i for i in _issues(broken, strict=True) if text in i.message]
    assert [i.level for i in loose] == ["warning"]
    assert [i.level for i in strict] == ["error"]


def test_a_tier_that_inherits_core_assets_has_some(catalog_min: Catalog) -> None:
    emptied = _tier(catalog_min, "tier_big", core=[])  # it still gets tier_small's core
    assert not any("no core assets" in i.message for i in _issues(emptied))


def test_a_trigger_asset_with_no_folder_is_a_warning(catalog_min: Catalog) -> None:
    broken = _trigger(catalog_min, "needs_setup", assets=["setup_guide", "ghost"])
    issues = [i for i in _issues(broken) if "ghost" in i.message]
    assert [(i.level, i.where) for i in issues] == [("warning", "tiers.yaml: triggers[needs_setup].assets")]


# ----------------------------------------------------------------- ordering
def test_issues_are_ordered_by_file_then_location_and_do_not_change_between_runs(
    catalog_min: Catalog,
) -> None:
    broken = _gate(catalog_min, "gate_one", approver_roles=["role_z"])
    broken = _spec(broken, "deep_dive", gate="nowhere", family="poster")
    broken = _trigger(broken, "needs_setup", tiers=["tier_ghost"])
    broken = _lifecycle(broken, approved_gate_values=[])
    first = _issues(broken)
    assert [i.where for i in first] == [
        "asset_types/deep_dive/spec.yaml: family",
        "asset_types/deep_dive/spec.yaml: gate",
        "lifecycle.yaml: approved_gate_values",
        "lifecycle.yaml: gates[gate_one].approver_roles",
        "tiers.yaml: triggers[needs_setup].tiers",
    ]
    assert _issues(broken) == first
