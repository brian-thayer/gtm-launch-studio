"""``TODO(confirm)`` markers: things the catalog author inferred and a person must still confirm."""

from pathlib import Path

from gtm_studio.catalog.loader import loaded_files

MARKER = "TODO(confirm)"


def count_todos(root: Path) -> dict[str, int]:
    """Markers per catalog file, by relative POSIX path, for the files that have any. Only the files the
    loader reads are searched, so ``sources/`` and ``CLAUDE.md`` never count."""
    counts: dict[str, int] = {}
    for path in loaded_files(root):
        found = path.read_text(encoding="utf-8", errors="replace").count(MARKER)
        if found:
            counts[path.relative_to(root).as_posix()] = found
    return counts
