"""The demo catalog (``fixtures/demo/catalog``): S15, S15b and e2e run on it until a real catalog exists."""

from pathlib import Path

import pytest

from gtm_studio.catalog.loader import load_catalog
from gtm_studio.catalog.source import check_catalog
from gtm_studio.domain.catalog import Catalog
from gtm_studio.settings import REPO_ROOT

DEMO = REPO_ROOT / "fixtures" / "demo" / "catalog"
MARK = "DEMO ONLY: synthetic, not a real company's GTM framework"


@pytest.fixture(scope="module")
def demo() -> Catalog:
    return load_catalog(DEMO)


def test_the_demo_catalog_has_no_errors() -> None:
    catalog, issues = check_catalog(DEMO)
    assert catalog is not None
    assert [i for i in issues if i.level == "error"] == []
    # Gold examples are not required for the demo: that is the only kind of warning it has.
    assert {i.message for i in issues} == {"no gold examples"}


def _marked(path: Path) -> bool:
    """The marker is the first line, or, in a Markdown file with frontmatter, the first line after it."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if path.suffix == ".yaml":
        return lines[0] == f"# {MARK}"
    if lines[0] == "---":
        end = lines.index("---", 1)
        return lines[end + 1] == f"<!-- {MARK} -->"
    return lines[0] == f"<!-- {MARK} -->"


def test_every_demo_file_carries_the_demo_marker() -> None:
    files = [p for p in DEMO.rglob("*") if p.is_file()]
    assert len(files) > 40
    assert [p.relative_to(DEMO).as_posix() for p in files if not _marked(p)] == []


def test_the_matrix_is_three_tiers_by_eight_gates(demo: Catalog) -> None:
    matrix = demo.matrix()
    assert list(matrix) == ["tier_1", "tier_2", "tier_3"]
    assert all(len(row) == 8 for row in matrix.values())
    assert list(matrix["tier_3"]) == [g.key for g in demo.gates_in_order()]


def test_a_bigger_tier_gets_the_assets_of_the_smaller_ones(demo: Catalog) -> None:
    matrix = demo.matrix()
    assert matrix["tier_3"]["beta_approved"] == []
    assert matrix["tier_2"]["ga_candidate"] == ["battlecard", "master_narrative", "one_pager"]
    assert matrix["tier_1"] == matrix["tier_2"]


def test_the_demo_has_eleven_asset_types_and_one_tier_decider(demo: Catalog) -> None:
    assert len(demo.asset_types) == 11
    decider = demo.tier_decider()
    assert decider is not None
    assert decider.spec.key == "tier_classification"
    assert demo.undefined_asset_keys() == set()


def test_gate_approvers_are_role_keys_never_system_roles(demo: Catalog) -> None:
    assert demo.gate("beta_approved").approver_roles == ["product", "pmm", "cs"]
    assert {r.key for r in demo.lifecycle.roles} == {"pmm", "product", "cs", "support", "launch_owner"}
    assert demo.gate("monthly_release").release_gate is True
