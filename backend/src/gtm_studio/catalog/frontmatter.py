"""Markdown files with a YAML header: the split, and the rubric's criteria. Pure text handling.

Both functions raise ``ValueError`` for a malformed file; the loader adds the file's path.
"""

import re
from typing import Any

import yaml

from gtm_studio.domain.catalog import RubricCriterion

# '---', the YAML, '---' (each on its own line), then the body. The YAML may be empty.
_FRONTMATTER = re.compile(r"\A---[ \t]*\n(?P<yaml>.*?\n)?---[ \t]*(?:\n|\Z)", re.DOTALL)
_NOT_ALNUM = re.compile(r"[^a-z0-9]+")


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """``(frontmatter, body)`` of ``---\\n<yaml>\\n---\\n<body>``. Text with no header is ``({}, text)``."""
    # Drop a byte-order mark and treat Windows line ends as Unix ones.
    text = text.removeprefix("\N{BYTE ORDER MARK}").replace("\r\n", "\n")
    match = _FRONTMATTER.match(text)
    if match is None:
        if text.startswith("---\n"):
            raise ValueError("the frontmatter is not closed by a '---' line")
        return {}, text
    try:
        data: Any = yaml.safe_load(match["yaml"] or "")
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in the frontmatter: {' '.join(str(exc).split())}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("the frontmatter must be a YAML mapping")
    return {str(key): value for key, value in data.items()}, text[match.end() :]


def _slug(title: str) -> str:
    return _NOT_ALNUM.sub("_", title.lower()).strip("_")


def rubric_criteria(body: str) -> list[RubricCriterion]:
    """One criterion per ``## `` heading: the key is the title in snake_case, the body the text under it.

    Text before the first heading, and ``#`` or ``###`` headings, are not criteria. A ``## `` line inside a
    code fence is text. Raises ``ValueError`` for a title with no letters or digits or a repeated key.
    """
    sections: list[tuple[str, list[str]]] = []
    in_fence = False
    for line in body.replace("\r\n", "\n").split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)

    criteria: list[RubricCriterion] = []
    seen: set[str] = set()
    for title, lines in sections:
        key = _slug(title)
        if not key:
            raise ValueError(f"rubric heading {title!r} has no letters or digits to make a key from")
        if key in seen:
            raise ValueError(f"two rubric headings make the key {key!r}")
        seen.add(key)
        criteria.append(RubricCriterion(key=key, title=title, body_md="\n".join(lines).strip()))
    return criteria
