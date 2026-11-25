"""Load a catalog folder and say everything that is wrong with it. ``FileCatalogSource`` is what the running
app (``services/catalog.py``) reads the catalog through."""

from collections.abc import Mapping
from pathlib import Path

from gtm_studio.catalog.families import KNOWN_FAMILIES
from gtm_studio.catalog.loader import CatalogLoadError, catalog_present, load_catalog
from gtm_studio.catalog.todos import MARKER, count_todos
from gtm_studio.domain.catalog import Catalog, Issue
from gtm_studio.domain.catalog_rules import validate


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def check_catalog(
    root: Path, *, strict: bool = False, todos: Mapping[str, int] | None = None
) -> tuple[Catalog | None, list[Issue]]:
    """``(catalog, issues)``. A file that can't be loaded gives ``(None, [one error naming the file])``.

    Otherwise the issues are the validator's, then one warning per file that still has ``TODO(confirm)``
    markers. Those are never errors, even with ``strict``: the catalog works, a person has a question.
    ``todos`` is a ``count_todos(root)`` the caller already has (so a report can't disagree with itself).
    """
    try:
        catalog = load_catalog(root)
    except CatalogLoadError as exc:
        return None, [Issue(level="error", where=_relative(root, exc.path), message=exc.message)]
    counts = count_todos(root) if todos is None else todos
    issues = validate(catalog, families=KNOWN_FAMILIES, strict=strict)
    issues += [
        Issue(level="warning", where=where, message=f"{count} {MARKER} marker(s) to resolve")
        for where, count in sorted(counts.items())
    ]
    return catalog, issues


class FileCatalogSource:
    """The ``CatalogSource`` port over a ``gtm_catalog/``-shaped folder."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def present(self) -> bool:
        return catalog_present(self._root)

    def check(self) -> tuple[Catalog | None, list[Issue]]:
        return check_catalog(self._root)

    def todo_count(self) -> int:
        return sum(count_todos(self._root).values())
