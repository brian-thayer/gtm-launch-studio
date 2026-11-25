"""The catalog models and their helpers, built in code (no files). Names are neutral on purpose."""

from typing import Any

import pytest
from pydantic import ValidationError

from gtm_studio.domain.catalog import (
    AssetType,
    AssetTypeSpec,
    Brand,
    Catalog,
    Gate,
    Lifecycle,
    RoleDef,
    Rubric,
    Terminology,
    Tier,
    Tiers,
    Trigger,
    Visual,
)
from gtm_studio.domain.errors import NotFoundError


def _asset(key: str, gate: str, **spec: Any) -> AssetType:
    return AssetType(
        spec=AssetTypeSpec(
            key=key, name=key, gate=gate, audience="internal", family="generic", formats=["md"], **spec
        ),
        prompt_md="prompt",
        rubric=Rubric(pass_threshold=4, criteria=[], raw_md=""),
    )


def _catalog(*, inherits_lower: bool = True, assets: list[AssetType] | None = None) -> Catalog:
    """Gates and tiers are listed out of order, so the helpers must sort them.

    Tiers: t1 (rank 1) core [a3, shared], optional [opt_missing]; t2 core [a2, shared];
    t3 core [a1, core_missing].
    Gates: g1 (order 1, role_1), g2 (order 2, role_1 and role_2).
    """
    gates = [
        Gate(key="g2", label="G2", short="2", order=2, approver_roles=["role_1", "role_2"]),
        Gate(key="g1", label="G1", short="1", order=1, approver_roles=["role_1"]),
    ]
    tiers = [
        Tier(key="t2", label="T2", rank=2, description="d", core=["a2", "shared"]),
        Tier(key="t3", label="T3", rank=3, description="d", core=["a1", "core_missing"]),
        Tier(key="t1", label="T1", rank=1, description="d", core=["a3", "shared"], optional=["opt_missing"]),
    ]
    triggers = [
        Trigger(key="everywhere", label="E", description="d", assets=["trig_asset"]),
        Trigger(key="only_t1", label="O", description="d", assets=["trig_missing"], tiers=["t1"]),
    ]
    if assets is None:
        assets = [
            _asset("a1", "g1"),
            _asset("a2", "g2", approver_roles=["role_2"]),
            _asset("a3", "g2"),
            _asset("shared", "g1"),
            _asset("trig_asset", "g2"),
        ]
    return Catalog(
        lifecycle=Lifecycle(
            roles=[RoleDef(key="role_1", label="R1"), RoleDef(key="role_2", label="R2")],
            gates=gates,
            approved_gate_values=["approved"],
        ),
        tiers=Tiers(inherits_lower=inherits_lower, tiers=tiers, triggers=triggers),
        context_keys={},
        brand=Brand(
            voice_md="v",
            claims_md="c",
            legal_md="l",
            terminology=Terminology(),
            visual=Visual(colors={"primary": "#000000"}),
        ),
        asset_types={a.spec.key: a for a in assets},
        version_hash="0" * 12,
    )


# ------------------------------------------------------------------- models
def test_models_are_frozen() -> None:
    gate = Gate(key="g", label="G", short="g", order=1, approver_roles=["role_1"])
    with pytest.raises(ValidationError):
        gate.order = 2  # pyright: ignore[reportAttributeAccessIssue]


def test_unknown_fields_are_refused() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        AssetTypeSpec.model_validate(
            {
                "key": "a",
                "name": "A",
                "gate": "g",
                "audience": "internal",
                "family": "f",
                "formats": ["md"],
                "typo_field": 1,
            }
        )


def test_spec_defaults() -> None:
    spec = _asset("a", "g").spec
    assert (spec.foundation, spec.decides, spec.depends_on) == (False, None, [])
    assert (spec.approver_roles, spec.route, spec.effort, spec.length) == (None, "writer", "medium", None)


def test_context_key_type_defaults_to_text_and_is_checked() -> None:
    from gtm_studio.domain.catalog import ContextKey

    assert ContextKey(key="k", label="K", description="d", sources=["aha"]).type == "text"
    with pytest.raises(ValidationError):
        ContextKey.model_validate(
            {"key": "k", "label": "K", "description": "d", "type": "color", "sources": []}
        )


# ------------------------------------------------------------------ lookups
def test_gates_and_tiers_come_back_in_order() -> None:
    catalog = _catalog()
    assert [g.key for g in catalog.gates_in_order()] == ["g1", "g2"]
    assert [t.key for t in catalog.tiers_by_rank()] == ["t1", "t2", "t3"]


def test_lookups_find_by_key_and_raise_not_found() -> None:
    catalog = _catalog()
    assert catalog.gate("g2").order == 2
    assert catalog.tier("t3").rank == 3
    assert catalog.asset_type("a1").spec.gate == "g1"
    for lookup in (catalog.gate, catalog.tier, catalog.asset_type):
        with pytest.raises(NotFoundError, match="nope"):
            lookup("nope")


# ---------------------------------------------------------- approver roles
def test_approver_roles_default_to_the_gates_and_a_spec_overrides_them() -> None:
    catalog = _catalog()
    assert catalog.approver_roles_for("a1") == ["role_1"]
    assert catalog.approver_roles_for("a3") == ["role_1", "role_2"]
    assert catalog.approver_roles_for("a2") == ["role_2"]  # the spec's own list


def test_approver_roles_for_unknown_asset_or_gate_is_not_found() -> None:
    catalog = _catalog(assets=[_asset("orphan", "no_such_gate")])
    with pytest.raises(NotFoundError):
        catalog.approver_roles_for("missing")
    with pytest.raises(NotFoundError):
        catalog.approver_roles_for("orphan")


def test_approver_roles_for_returns_a_copy() -> None:
    catalog = _catalog()
    catalog.approver_roles_for("a1").append("intruder")
    assert catalog.approver_roles_for("a1") == ["role_1"]


# ------------------------------------------------------------- core assets
def test_core_assets_inherit_from_smaller_tiers_in_rank_order_without_repeats() -> None:
    catalog = _catalog(inherits_lower=True)
    # own core, then t2's (a2; "shared" is already there), then t3's. Undefined keys are included.
    assert catalog.core_assets("t1") == ["a3", "shared", "a2", "a1", "core_missing"]
    assert catalog.core_assets("t2") == ["a2", "shared", "a1", "core_missing"]
    assert catalog.core_assets("t3") == ["a1", "core_missing"]


def test_core_assets_without_inheritance_are_the_tiers_own() -> None:
    catalog = _catalog(inherits_lower=False)
    assert catalog.core_assets("t1") == ["a3", "shared"]
    assert catalog.core_assets("t2") == ["a2", "shared"]


def test_core_assets_for_an_unknown_tier_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        _catalog().core_assets("nope")


def test_optional_assets_are_never_inherited() -> None:
    catalog = _catalog(inherits_lower=True)
    assert catalog.optional_assets("t1") == ["opt_missing"]
    assert catalog.optional_assets("t2") == []
    with pytest.raises(NotFoundError):
        catalog.optional_assets("nope")


# ---------------------------------------------------------------- triggers
def test_triggers_for_a_tier_include_those_for_every_tier_and_those_naming_it() -> None:
    catalog = _catalog()
    assert [t.key for t in catalog.triggers_for("t1")] == ["everywhere", "only_t1"]
    assert [t.key for t in catalog.triggers_for("t2")] == ["everywhere"]  # only_t1 lists t1 alone


def test_triggers_for_an_unknown_tier_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        _catalog().triggers_for("nope")


# ------------------------------------------------------------ tier decider
def test_tier_decider_is_none_without_one_and_the_asset_with_one() -> None:
    assert _catalog().tier_decider() is None
    decider = _asset("classifier", "g1", decides="tier", foundation=True)
    catalog = _catalog(assets=[_asset("a1", "g1"), decider])
    assert catalog.tier_decider() == decider


# ------------------------------------------------------------------ matrix
def test_matrix_has_every_tier_by_rank_and_every_gate_in_order() -> None:
    matrix = _catalog().matrix()
    assert list(matrix) == ["t1", "t2", "t3"]
    assert all(list(cells) == ["g1", "g2"] for cells in matrix.values())


def test_matrix_cells_hold_the_tiers_core_assets_by_gate_sorted_by_key() -> None:
    matrix = _catalog().matrix()
    assert matrix["t1"] == {"g1": ["a1", "shared"], "g2": ["a2", "a3"]}
    assert matrix["t2"] == {"g1": ["a1", "shared"], "g2": ["a2"]}
    assert matrix["t3"] == {"g1": ["a1"], "g2": []}  # empty cells are still there


def test_matrix_leaves_out_undefined_keys_and_optional_and_triggered_assets() -> None:
    cells = _catalog().matrix()["t1"]
    listed = {key for keys in cells.values() for key in keys}
    assert "core_missing" not in listed  # no asset type
    assert "opt_missing" not in listed  # optional
    assert "trig_asset" not in listed  # defined, but triggered


def test_matrix_without_inheritance_shows_only_the_tiers_own_assets() -> None:
    assert _catalog(inherits_lower=False).matrix()["t2"] == {"g1": ["shared"], "g2": ["a2"]}


# ------------------------------------------------------------- undefined keys
def test_undefined_asset_keys_cover_core_optional_and_trigger_assets() -> None:
    assert _catalog().undefined_asset_keys() == {"core_missing", "opt_missing", "trig_missing"}


def test_undefined_asset_keys_is_empty_when_everything_is_defined() -> None:
    keys = ["a1", "a2", "a3", "shared", "trig_asset", "core_missing", "opt_missing", "trig_missing"]
    catalog = _catalog(assets=[_asset(key, "g1") for key in keys])
    assert catalog.undefined_asset_keys() == set()
