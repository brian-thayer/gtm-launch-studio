"""``gtm catalog show``."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from gtm_studio.catalog.hashing import catalog_version_hash
from gtm_studio.cli import app

runner = CliRunner()


def _show(*args: str) -> tuple[int, str]:
    result = runner.invoke(app, ["catalog", "show", *args])
    return result.exit_code, result.output


def test_show_prints_the_hash_gates_tiers_matrix_and_triggers(catalog_min_dir: Path) -> None:
    code, output = _show("--path", str(catalog_min_dir))
    assert code == 0
    lines = [" ".join(line.split()) for line in output.splitlines()]
    assert f"version {catalog_version_hash(catalog_min_dir)}" in lines
    assert "1 gate_one Gate One approvers: role_a" in lines
    assert "2 gate_two Gate Two approvers: role_a, role_b [release gate]" in lines
    assert any(
        line.startswith("1 tier_big Big timing: anchor facts.launch_date, plan start -56d") for line in lines
    )
    assert "gate_one gate_two" in lines  # the matrix header
    assert "tier_big brief, classify deep_dive" in lines
    assert "tier_small brief, classify -" in lines
    assert "needs_setup facts.needs_setup -> setup_guide every tier" in lines


def test_show_lists_asset_keys_with_no_folder(catalog_min_copy: Path) -> None:
    tiers = catalog_min_copy / "tiers.yaml"
    tiers.write_text(
        tiers.read_text(encoding="utf-8").replace("[deep_dive]", "[deep_dive, ghost]"), encoding="utf-8"
    )
    code, output = _show("--path", str(catalog_min_copy))
    assert code == 0
    assert output.rstrip().endswith("asset keys with no asset type folder\n  ghost")


def test_show_copes_with_a_catalog_that_has_no_gates_or_tiers_yet(catalog_min_copy: Path) -> None:
    (catalog_min_copy / "lifecycle.yaml").write_text(
        "roles: []\ngates: []\napproved_gate_values: []\n", encoding="utf-8"
    )
    (catalog_min_copy / "tiers.yaml").write_text("tiers: []\n", encoding="utf-8")
    code, output = _show("--path", str(catalog_min_copy))
    assert code == 0
    assert "gates, in order\n  none\n" in output
    assert "tiers, by rank\n  none\n" in output
    assert "triggers\n  none\n" in output


def test_a_relative_path_is_relative_to_the_working_directory(
    catalog_min_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(catalog_min_dir.parent)
    code, output = _show("--path", "catalog_min")
    assert code == 0
    assert catalog_version_hash(catalog_min_dir) in output


def test_without_a_path_it_uses_the_configured_catalog_dir(
    catalog_min_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTM_CATALOG_DIR", str(catalog_min_dir))
    code, output = _show()
    assert code == 0
    assert catalog_version_hash(catalog_min_dir) in output


def test_no_catalog_says_where_it_looked_and_exits_1(tmp_path: Path) -> None:
    code, output = _show("--path", str(tmp_path))
    assert code == 1
    assert f"no catalog at {tmp_path}" in output


def test_a_broken_file_is_named_and_exits_1(catalog_min_copy: Path) -> None:
    spec = catalog_min_copy / "asset_types" / "brief" / "spec.yaml"
    with spec.open("a", encoding="utf-8") as handle:
        handle.write("typo_field: 1\n")
    code, output = _show("--path", str(catalog_min_copy))
    assert code == 1
    assert str(spec) in output
    assert "typo_field" in output
    assert "Traceback" not in output
