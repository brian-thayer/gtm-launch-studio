"""The catalog's version hash: what every generated asset records as "made under this catalog"."""

import hashlib
from pathlib import Path

from gtm_studio.catalog.loader import loaded_files

HASH_LENGTH = 12


def catalog_version_hash(root: Path) -> str:
    """The first 12 hex characters of a sha256 over the files ``load_catalog`` reads.

    Each file contributes its relative POSIX path and its bytes, in path order. ``\\r\\n`` counts as
    ``\\n``, so a Windows checkout and a Linux one hash the same. Files the loader ignores (``sources/``,
    ``CLAUDE.md``, dotfiles) never change it.
    """
    digest = hashlib.sha256()
    for path in loaded_files(root):
        content = path.read_bytes().replace(b"\r\n", b"\n")
        name = path.relative_to(root).as_posix().encode("utf-8")
        # Length-prefix both parts, so no (path, content) pair can be read as another.
        digest.update(len(name).to_bytes(8, "big") + name + len(content).to_bytes(8, "big") + content)
    return digest.hexdigest()[:HASH_LENGTH]
