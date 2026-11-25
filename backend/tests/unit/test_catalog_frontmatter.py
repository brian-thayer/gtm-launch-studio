import pytest

from gtm_studio.catalog.frontmatter import rubric_criteria, split_frontmatter


# ------------------------------------------------------------ split_frontmatter
def test_splits_the_header_from_the_body() -> None:
    header, body = split_frontmatter("---\ntitle: A\ntags: [x, y]\n---\n# Body\n\ntext\n")
    assert header == {"title": "A", "tags": ["x", "y"]}
    assert body == "# Body\n\ntext\n"


def test_text_without_a_header_is_all_body() -> None:
    assert split_frontmatter("# Just a body\n") == ({}, "# Just a body\n")
    assert split_frontmatter("") == ({}, "")


def test_an_empty_header_is_an_empty_mapping() -> None:
    assert split_frontmatter("---\n---\nbody\n") == ({}, "body\n")
    assert split_frontmatter("---\n\n---\nbody\n") == ({}, "body\n")


def test_windows_line_ends_and_a_byte_order_mark_are_fine() -> None:
    header, body = split_frontmatter("\N{BYTE ORDER MARK}---\r\nkey: v\r\n---\r\nline one\r\nline two\r\n")
    assert header == {"key": "v"}
    assert body == "line one\nline two\n"


def test_a_rule_inside_the_body_is_not_a_second_header() -> None:
    header, body = split_frontmatter("---\na: 1\n---\nabove\n\n---\n\nbelow\n")
    assert header == {"a": 1}
    assert body == "above\n\n---\n\nbelow\n"


def test_a_dashed_line_that_is_longer_does_not_close_the_header() -> None:
    with pytest.raises(ValueError, match="not closed"):
        split_frontmatter("---\na: 1\n----\nbody\n")


def test_an_unclosed_header_is_an_error() -> None:
    with pytest.raises(ValueError, match="not closed"):
        split_frontmatter("---\na: 1\nbody\n")


def test_a_header_that_is_not_a_mapping_is_an_error() -> None:
    with pytest.raises(ValueError, match="mapping"):
        split_frontmatter("---\n- a\n- b\n---\nbody\n")


def test_invalid_yaml_in_the_header_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="invalid YAML"):
        split_frontmatter("---\nkey: [unclosed\n---\nbody\n")


def test_yaml_is_loaded_safely() -> None:
    with pytest.raises(ValueError, match="invalid YAML"):
        split_frontmatter("---\nkey: !!python/object/apply:os.getcwd []\n---\nbody\n")


# -------------------------------------------------------------- rubric_criteria
def test_one_criterion_per_second_level_heading() -> None:
    body = (
        "# Rubric\n\nScore 1 to 5.\n\n## Grounding\n\nClaims cite facts.\n\n## Brand voice\n\nSounds right.\n"
    )
    criteria = rubric_criteria(body)
    assert [(c.key, c.title) for c in criteria] == [
        ("grounding", "Grounding"),
        ("brand_voice", "Brand voice"),
    ]
    assert criteria[0].body_md == "Claims cite facts."
    assert criteria[1].body_md == "Sounds right."


def test_the_key_is_the_title_in_snake_case() -> None:
    criteria = rubric_criteria("## Grounding (claims cited & supported)\n\ntext\n")
    assert criteria[0].key == "grounding_claims_cited_supported"
    assert criteria[0].title == "Grounding (claims cited & supported)"


def test_other_heading_levels_belong_to_the_criterion_above() -> None:
    criteria = rubric_criteria("## One\n\n### 5 looks like\n\ngood\n\n#### deeper\n\n## Two\n\nx\n")
    assert [c.key for c in criteria] == ["one", "two"]
    assert "### 5 looks like" in criteria[0].body_md
    assert "#### deeper" in criteria[0].body_md


def test_a_heading_inside_a_code_fence_is_text() -> None:
    criteria = rubric_criteria("## One\n\n```\n## not a heading\n```\n\n## Two\n")
    assert [c.key for c in criteria] == ["one", "two"]
    assert "## not a heading" in criteria[0].body_md


def test_no_headings_means_no_criteria() -> None:
    assert rubric_criteria("Just text.\n") == []


def test_windows_line_ends_do_not_leak_into_criteria() -> None:
    criteria = rubric_criteria("## One\r\n\r\nline\r\n")
    assert (criteria[0].title, criteria[0].body_md) == ("One", "line")


def test_two_headings_with_the_same_key_are_an_error() -> None:
    with pytest.raises(ValueError, match="make the key 'voice'"):
        rubric_criteria("## Voice\n\na\n\n## voice!\n\nb\n")


def test_a_heading_with_nothing_to_make_a_key_from_is_an_error() -> None:
    with pytest.raises(ValueError, match="letters or digits"):
        rubric_criteria("## ???\n\na\n")
