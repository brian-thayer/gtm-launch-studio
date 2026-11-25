"""``check_catalog``: load a folder, validate it, and add the TODO(confirm) warnings."""

from pathlib import Path

from gtm_studio.catalog.source import check_catalog
from gtm_studio.catalog.todos import count_todos


def test_catalog_min_has_no_issues_even_when_strict(catalog_min_dir: Path) -> None:
    catalog, issues = check_catalog(catalog_min_dir, strict=True)
    assert catalog is not None
    assert issues == []


def test_a_file_that_does_not_load_is_one_error_naming_it(catalog_min_copy: Path) -> None:
    (catalog_min_copy / "tiers.yaml").write_text("tiers: [unclosed\n", encoding="utf-8")
    catalog, issues = check_catalog(catalog_min_copy)
    assert catalog is None
    assert [(i.level, i.where) for i in issues] == [("error", "tiers.yaml")]
    assert "invalid YAML" in issues[0].message


def test_a_bad_asset_type_file_is_named_by_its_relative_path(catalog_min_copy: Path) -> None:
    spec = catalog_min_copy / "asset_types" / "brief" / "spec.yaml"
    spec.write_text(spec.read_text(encoding="utf-8") + "typo_field: 1\n", encoding="utf-8")
    catalog, issues = check_catalog(catalog_min_copy)
    assert catalog is None
    assert [(i.level, i.where) for i in issues] == [("error", "asset_types/brief/spec.yaml")]
    assert "typo_field" in issues[0].message


def test_a_context_key_listed_twice_is_one_error_naming_the_file(catalog_min_copy: Path) -> None:
    keys = catalog_min_copy / "context_keys.yaml"
    line = next(x for x in keys.read_text(encoding="utf-8").splitlines() if "facts.summary" in x)
    keys.write_text(keys.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
    catalog, issues = check_catalog(catalog_min_copy)
    assert catalog is None
    assert [(i.level, i.where) for i in issues] == [("error", "context_keys.yaml")]
    assert "'facts.summary' is listed twice" in issues[0].message


def test_an_asset_type_key_that_does_not_match_its_folder_is_one_error(catalog_min_copy: Path) -> None:
    spec = catalog_min_copy / "asset_types" / "deep_dive" / "spec.yaml"
    spec.write_text(
        spec.read_text(encoding="utf-8").replace("key: deep_dive", "key: brief"), encoding="utf-8"
    )
    catalog, issues = check_catalog(catalog_min_copy)
    assert catalog is None
    assert [(i.level, i.where) for i in issues] == [("error", "asset_types/deep_dive/spec.yaml")]
    assert "must match its folder name" in issues[0].message


def test_validator_errors_come_back_with_the_catalog(catalog_min_copy: Path) -> None:
    spec = catalog_min_copy / "asset_types" / "brief" / "spec.yaml"
    spec.write_text(spec.read_text(encoding="utf-8").replace("generic_doc", "poster"), encoding="utf-8")
    catalog, issues = check_catalog(catalog_min_copy)
    assert catalog is not None
    assert [(i.level, i.where) for i in issues] == [("error", "asset_types/brief/spec.yaml: family")]


def test_todo_markers_are_counted_per_file(catalog_min_copy: Path) -> None:
    voice = catalog_min_copy / "brand" / "voice.md"
    voice.write_text(
        voice.read_text(encoding="utf-8") + "\nTODO(confirm): one\nTODO(confirm): two\n", "utf-8"
    )
    spec = catalog_min_copy / "asset_types" / "brief" / "spec.yaml"
    spec.write_text(spec.read_text(encoding="utf-8") + "# TODO(confirm): gate\n", encoding="utf-8")
    (catalog_min_copy / "sources").mkdir()
    (catalog_min_copy / "sources" / "notes.md").write_text("TODO(confirm) in a file nobody loads", "utf-8")
    assert count_todos(catalog_min_copy) == {"asset_types/brief/spec.yaml": 1, "brand/voice.md": 2}


def test_todo_markers_are_warnings_even_when_strict(catalog_min_copy: Path) -> None:
    voice = catalog_min_copy / "brand" / "voice.md"
    voice.write_text(voice.read_text(encoding="utf-8") + "\nTODO(confirm): one\n", encoding="utf-8")
    catalog, issues = check_catalog(catalog_min_copy, strict=True)
    assert catalog is not None
    assert [(i.level, i.where) for i in issues] == [("warning", "brand/voice.md")]
    assert "1 TODO(confirm) marker" in issues[0].message


def test_a_catalog_without_markers_counts_none(catalog_min_dir: Path) -> None:
    assert count_todos(catalog_min_dir) == {}


def test_counts_the_caller_already_has_are_the_ones_reported(catalog_min_dir: Path) -> None:
    _, issues = check_catalog(catalog_min_dir, todos={"brand/voice.md": 3})
    assert [(i.level, i.where, i.message) for i in issues] == [
        ("warning", "brand/voice.md", "3 TODO(confirm) marker(s) to resolve")
    ]
