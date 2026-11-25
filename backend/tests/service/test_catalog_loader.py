"""Loading ``catalog_min`` from disk, the errors a bad file gives, and the version hash."""

import re
import shutil
from pathlib import Path

import pytest

from gtm_studio.catalog.hashing import catalog_version_hash
from gtm_studio.catalog.loader import CatalogLoadError, catalog_present, load_catalog, loaded_files
from gtm_studio.domain.catalog import Catalog


def _spec(root: Path, key: str) -> Path:
    return root / "asset_types" / key / "spec.yaml"


def _load_error(root: Path) -> CatalogLoadError:
    with pytest.raises(CatalogLoadError) as caught:
        load_catalog(root)
    return caught.value


# --------------------------------------------------------------- loading
def test_catalog_min_loads(catalog_min: Catalog) -> None:
    assert [g.key for g in catalog_min.gates_in_order()] == ["gate_one", "gate_two"]
    assert [t.key for t in catalog_min.tiers_by_rank()] == ["tier_big", "tier_small"]
    assert sorted(catalog_min.asset_types) == ["brief", "classify", "deep_dive", "extra_note", "setup_guide"]
    assert re.fullmatch(r"[0-9a-f]{12}", catalog_min.version_hash)


def test_the_lifecycle_and_tiers_are_read_in_full(catalog_min: Catalog) -> None:
    gate_two = catalog_min.gate("gate_two")
    assert gate_two.approver_roles == ["role_a", "role_b"]
    assert gate_two.release_gate is True
    assert catalog_min.lifecycle.approved_gate_values == ["approved"]
    big = catalog_min.tier("tier_big")
    assert big.timing is not None
    assert (big.timing.anchor, big.timing.plan_start_days, big.timing.core_due_days) == (
        "facts.launch_date",
        -56,
        -14,
    )
    assert catalog_min.tiers.inherits_lower is True
    assert [(t.key, t.context_key, t.assets) for t in catalog_min.tiers.triggers] == [
        ("needs_setup", "facts.needs_setup", ["setup_guide"])
    ]


def test_context_keys_brand_and_specs_are_read(catalog_min: Catalog) -> None:
    assert {k: v.type for k, v in catalog_min.context_keys.items()} == {
        "facts.summary": "text",
        "facts.launch_date": "date",
        "facts.needs_setup": "boolean",
        "facts.audience": "list",
    }
    assert catalog_min.brand.terminology.banned_external == ["guaranteed"]
    assert catalog_min.brand.visual.colors["primary"] == "#112233"
    assert catalog_min.brand.voice_md.startswith("Plain and direct")
    classify = catalog_min.asset_type("classify").spec
    assert (classify.decides, classify.foundation, classify.family) == ("tier", True, "classification")
    assert catalog_min.asset_type("deep_dive").spec.depends_on == ["brief"]
    assert catalog_min.asset_type("setup_guide").spec.audience == "external"


def test_a_rubrics_frontmatter_and_criteria_parse(catalog_min: Catalog) -> None:
    rubric = catalog_min.asset_type("brief").rubric
    assert rubric.pass_threshold == 4
    assert [(c.key, c.title) for c in rubric.criteria] == [
        ("grounding", "Grounding"),
        ("structure_in_order", "Structure (in order)"),
    ]
    assert rubric.criteria[0].body_md == "Every claim cites a fact."
    assert rubric.raw_md.startswith("Score each criterion")  # the frontmatter is not part of it


def test_a_gold_example_gets_its_slug_and_body(catalog_min: Catalog) -> None:
    (example,) = catalog_min.asset_type("brief").examples
    assert example.slug == "sample"
    assert example.redacted is True
    assert example.redactions == ["[Customer A]"]
    assert example.tier == "tier_small"
    assert example.body_md.startswith("# Sample brief")


def test_the_matrix_of_catalog_min(catalog_min: Catalog) -> None:
    assert catalog_min.matrix() == {
        "tier_big": {"gate_one": ["brief", "classify"], "gate_two": ["deep_dive"]},
        "tier_small": {"gate_one": ["brief", "classify"], "gate_two": []},
    }
    assert catalog_min.undefined_asset_keys() == set()


# ---------------------------------------------------------------- presence
def test_catalog_present_needs_a_lifecycle_file(catalog_min_dir: Path, tmp_path: Path) -> None:
    assert catalog_present(catalog_min_dir)
    assert not catalog_present(tmp_path)  # an empty folder
    assert not catalog_present(tmp_path / "nowhere")
    (tmp_path / "tiers.yaml").write_text("tiers: []\n", encoding="utf-8")
    assert not catalog_present(tmp_path)  # lifecycle.yaml is the signal


# ------------------------------------------------------------------ errors
def test_an_unknown_field_in_a_spec_names_the_file(catalog_min_copy: Path) -> None:
    with _spec(catalog_min_copy, "brief").open("a", encoding="utf-8") as spec:
        spec.write("typo_field: 1\n")
    error = _load_error(catalog_min_copy)
    assert error.path == _spec(catalog_min_copy, "brief")
    assert "typo_field" in error.message
    assert "Extra inputs are not permitted" in error.message
    assert str(error).startswith(str(error.path))


def test_a_missing_field_is_reported_with_its_location(catalog_min_copy: Path) -> None:
    tiers = catalog_min_copy / "tiers.yaml"
    tiers.write_text(tiers.read_text(encoding="utf-8").replace("    rank: 2\n", ""), encoding="utf-8")
    error = _load_error(catalog_min_copy)
    assert error.path == tiers
    assert "tiers.1.rank: Field required" in error.message


def test_a_folder_that_differs_from_its_spec_key_fails(catalog_min_copy: Path) -> None:
    spec = _spec(catalog_min_copy, "brief")
    spec.write_text(spec.read_text(encoding="utf-8").replace("key: brief", "key: summary"), encoding="utf-8")
    error = _load_error(catalog_min_copy)
    assert error.path == spec
    assert "'summary'" in error.message
    assert "'brief'" in error.message


def test_a_missing_file_is_named(catalog_min_copy: Path) -> None:
    prompt = catalog_min_copy / "asset_types" / "brief" / "prompt.md"
    prompt.unlink()
    error = _load_error(catalog_min_copy)
    assert error.path == prompt
    assert "not found" in error.message


def test_invalid_yaml_is_named(catalog_min_copy: Path) -> None:
    lifecycle = catalog_min_copy / "lifecycle.yaml"
    lifecycle.write_text("roles: [unclosed\n", encoding="utf-8")
    error = _load_error(catalog_min_copy)
    assert error.path == lifecycle
    assert error.message.startswith("invalid YAML")


def test_yaml_tags_that_build_objects_are_refused(catalog_min_copy: Path) -> None:
    lifecycle = catalog_min_copy / "lifecycle.yaml"
    lifecycle.write_text("roles: !!python/object/apply:os.getcwd []\n", encoding="utf-8")
    assert _load_error(catalog_min_copy).path == lifecycle


def test_a_file_that_is_not_utf8_is_named(catalog_min_copy: Path) -> None:
    voice = catalog_min_copy / "brand" / "voice.md"
    voice.write_bytes(b"caf\xe9\n")
    error = _load_error(catalog_min_copy)
    assert (error.path, error.message) == (voice, "not valid UTF-8")


def test_a_rubric_without_a_threshold_is_named(catalog_min_copy: Path) -> None:
    rubric = catalog_min_copy / "asset_types" / "classify" / "rubric.md"
    rubric.write_text("## Grounding\n\ntext\n", encoding="utf-8")
    error = _load_error(catalog_min_copy)
    assert error.path == rubric
    assert "pass_threshold" in error.message


def test_a_rubric_with_repeated_headings_is_named(catalog_min_copy: Path) -> None:
    rubric = catalog_min_copy / "asset_types" / "classify" / "rubric.md"
    rubric.write_text("---\npass_threshold: 4\n---\n## Voice\n\na\n\n## Voice\n\nb\n", encoding="utf-8")
    assert _load_error(catalog_min_copy).path == rubric


def test_an_example_with_an_unclosed_header_is_named(catalog_min_copy: Path) -> None:
    example = catalog_min_copy / "asset_types" / "brief" / "examples" / "sample.md"
    example.write_text("---\ntitle: x\n", encoding="utf-8")
    error = _load_error(catalog_min_copy)
    assert error.path == example
    assert "not closed" in error.message


def test_an_example_missing_a_field_is_named(catalog_min_copy: Path) -> None:
    example = catalog_min_copy / "asset_types" / "brief" / "examples" / "sample.md"
    example.write_text("---\ntitle: x\n---\nbody\n", encoding="utf-8")
    error = _load_error(catalog_min_copy)
    assert error.path == example
    assert "redacted: Field required" in error.message


def test_a_context_key_listed_twice_is_a_load_error(catalog_min_copy: Path) -> None:
    path = catalog_min_copy / "context_keys.yaml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "  - { key: facts.summary, label: Again, description: d, sources: [aha] }\n",
        encoding="utf-8",
    )
    error = _load_error(catalog_min_copy)
    assert error.path == path
    assert "facts.summary" in error.message


def test_a_catalog_with_no_asset_types_folder_loads_with_no_asset_types(catalog_min_copy: Path) -> None:
    shutil.rmtree(catalog_min_copy / "asset_types")
    catalog = load_catalog(catalog_min_copy)
    assert catalog.asset_types == {}
    assert catalog.undefined_asset_keys() == {"brief", "classify", "deep_dive", "extra_note", "setup_guide"}


# ------------------------------------------------------------ which files
def test_loaded_files_are_the_catalogs_files_sorted(catalog_min_dir: Path) -> None:
    names = [p.relative_to(catalog_min_dir).as_posix() for p in loaded_files(catalog_min_dir)]
    assert names == sorted(names)
    assert len(names) == 3 + 5 + 5 * 4  # top-level files, brand files, and four files per asset type
    assert "asset_types/brief/examples/sample.md" in names
    assert "brand/visual.yaml" in names


def test_other_files_are_ignored(catalog_min_copy: Path) -> None:
    before = loaded_files(catalog_min_copy)
    (catalog_min_copy / "sources").mkdir()
    (catalog_min_copy / "sources" / "guide.md").write_text("confidential", encoding="utf-8")
    (catalog_min_copy / "CLAUDE.md").write_text("notes", encoding="utf-8")
    (catalog_min_copy / ".hidden.yaml").write_text("x: 1", encoding="utf-8")
    (catalog_min_copy / "asset_types" / "CLAUDE.md").write_text("notes", encoding="utf-8")
    (catalog_min_copy / "asset_types" / ".stash").mkdir()  # not an asset type, and not valid as one
    (catalog_min_copy / "asset_types" / "brief" / "notes.md").write_text("scratch", encoding="utf-8")
    (catalog_min_copy / "asset_types" / "brief" / "examples" / ".draft.md").write_text("x", encoding="utf-8")
    (catalog_min_copy / "asset_types" / "brief" / "examples" / "SHOUTING.MD").write_text(
        "x", encoding="utf-8"
    )
    assert loaded_files(catalog_min_copy) == before  # '.MD' is not '.md', on Windows as on Linux
    # The junk didn't break the load, and no junk became an asset type.
    assert sorted(load_catalog(catalog_min_copy).asset_types) == [
        "brief",
        "classify",
        "deep_dive",
        "extra_note",
        "setup_guide",
    ]


# --------------------------------------------------------------------- hash
def test_the_hash_is_twelve_hex_characters_and_stable(catalog_min_dir: Path) -> None:
    first = catalog_version_hash(catalog_min_dir)
    assert re.fullmatch(r"[0-9a-f]{12}", first)
    assert catalog_version_hash(catalog_min_dir) == first
    assert load_catalog(catalog_min_dir).version_hash == first


def test_one_changed_byte_changes_the_hash(catalog_min_copy: Path) -> None:
    before = catalog_version_hash(catalog_min_copy)
    prompt = catalog_min_copy / "asset_types" / "brief" / "prompt.md"
    prompt.write_bytes(prompt.read_bytes() + b".")
    assert catalog_version_hash(catalog_min_copy) != before


def test_a_renamed_file_changes_the_hash(catalog_min_copy: Path) -> None:
    before = catalog_version_hash(catalog_min_copy)
    examples = catalog_min_copy / "asset_types" / "brief" / "examples"
    (examples / "sample.md").rename(examples / "renamed.md")
    assert catalog_version_hash(catalog_min_copy) != before


def test_files_the_loader_ignores_do_not_change_the_hash(catalog_min_copy: Path) -> None:
    before = catalog_version_hash(catalog_min_copy)
    (catalog_min_copy / "sources").mkdir()
    (catalog_min_copy / "sources" / "guide.md").write_text("confidential", encoding="utf-8")
    (catalog_min_copy / "CLAUDE.md").write_text("notes", encoding="utf-8")
    (catalog_min_copy / ".hidden.yaml").write_text("x: 1", encoding="utf-8")
    assert catalog_version_hash(catalog_min_copy) == before
    (catalog_min_copy / "CLAUDE.md").write_text("changed notes", encoding="utf-8")
    assert catalog_version_hash(catalog_min_copy) == before


def test_windows_and_unix_line_ends_hash_the_same(catalog_min_copy: Path) -> None:
    # Set the line ends explicitly: a checkout with core.autocrlf already has CRLF in these files.
    files = loaded_files(catalog_min_copy)
    for path in files:
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    assert all(b"\r" not in path.read_bytes() for path in files)
    unix_hash = catalog_version_hash(catalog_min_copy)

    for path in files:
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert all(b"\r\n" in path.read_bytes() for path in files)
    assert catalog_version_hash(catalog_min_copy) == unix_hash
    assert load_catalog(catalog_min_copy).version_hash == unix_hash


def test_the_hash_does_not_depend_on_where_the_catalog_is(catalog_min_dir: Path, tmp_path: Path) -> None:
    elsewhere = Path(shutil.copytree(catalog_min_dir, tmp_path / "other" / "place"))
    assert catalog_version_hash(elsewhere) == catalog_version_hash(catalog_min_dir)
