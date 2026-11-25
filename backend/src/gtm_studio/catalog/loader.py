"""Read a ``gtm_catalog/``-shaped folder into a ``Catalog``. File IO lives here (ADR-0006), not in the models.

Only the files named in ``loaded_files`` are read, and so only they are hashed: ``sources/``,
``CLAUDE.md``, dotfiles and anything else in the folder are ignored.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from gtm_studio.catalog.frontmatter import rubric_criteria, split_frontmatter
from gtm_studio.domain.catalog import (
    AssetType,
    AssetTypeSpec,
    Brand,
    Catalog,
    ContextKey,
    GoldExample,
    Lifecycle,
    Rubric,
    Terminology,
    Tiers,
    Visual,
)

_LIFECYCLE = "lifecycle.yaml"
_TIERS = "tiers.yaml"
_CONTEXT_KEYS = "context_keys.yaml"
_BRAND = Path("brand")
_ASSET_TYPES = Path("asset_types")


class CatalogLoadError(Exception):
    """A catalog file that can't be read or doesn't fit the models. ``path`` names the file."""

    def __init__(self, path: Path, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


class _ContextKeysFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_keys: list[ContextKey]


class _RubricFrontmatter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pass_threshold: int


# --------------------------------------------------------------------- files
def catalog_present(root: Path) -> bool:
    """True when ``root`` has a ``lifecycle.yaml``: the signal that someone has started a catalog."""
    return (root / _LIFECYCLE).is_file()


def _asset_type_dirs(root: Path) -> list[Path]:
    """One folder per asset type, by name. Dotfolders are skipped, and so are plain files."""
    parent = root / _ASSET_TYPES
    if not parent.is_dir():
        return []
    return sorted(p for p in parent.iterdir() if p.is_dir() and not p.name.startswith("."))


def _example_files(asset_dir: Path) -> list[Path]:
    examples = asset_dir / "examples"
    if not examples.is_dir():
        return []
    # Case-sensitive on every platform, so Windows and Linux load (and hash) the same files.
    return sorted(p for p in examples.glob("*.md", case_sensitive=True) if not p.name.startswith("."))


def loaded_files(root: Path) -> list[Path]:
    """The files ``load_catalog`` reads, as far as they exist, sorted by relative POSIX path (the order
    the version hash uses, whatever the platform's own path ordering)."""
    candidates = [root / _LIFECYCLE, root / _TIERS, root / _CONTEXT_KEYS]
    candidates += [
        root / _BRAND / name
        for name in ("voice.md", "claims.md", "legal.md", "terminology.yaml", "visual.yaml")
    ]
    for folder in _asset_type_dirs(root):
        candidates += [folder / name for name in ("spec.yaml", "prompt.md", "rubric.md")]
        candidates += _example_files(folder)
    return sorted((p for p in candidates if p.is_file()), key=lambda p: p.relative_to(root).as_posix())


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise CatalogLoadError(path, "file not found") from None
    except UnicodeDecodeError:
        raise CatalogLoadError(path, "not valid UTF-8") from None
    except OSError as exc:
        raise CatalogLoadError(path, f"cannot be read: {exc.strerror or exc}") from exc


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(_read_text(path))
    except yaml.YAMLError as exc:
        raise CatalogLoadError(path, f"invalid YAML: {' '.join(str(exc).split())}") from exc


def _flatten(exc: ValidationError) -> str:
    """Pydantic's errors as one line: ``tiers.0.core: Input should be a valid list; ...``."""
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or '(file)'}: {error['msg']}"
        for error in exc.errors(include_url=False)
    )


def _validated[T: BaseModel](model: type[T], data: Any, path: Path) -> T:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise CatalogLoadError(path, _flatten(exc)) from exc


def _load_yaml_model[T: BaseModel](model: type[T], path: Path) -> T:
    return _validated(model, _read_yaml(path), path)


def _split(path: Path) -> tuple[dict[str, Any], str]:
    try:
        return split_frontmatter(_read_text(path))
    except ValueError as exc:
        raise CatalogLoadError(path, str(exc)) from exc


# --------------------------------------------------------------- the pieces
def _load_context_keys(path: Path) -> dict[str, ContextKey]:
    keys: dict[str, ContextKey] = {}
    for item in _load_yaml_model(_ContextKeysFile, path).context_keys:
        if item.key in keys:
            raise CatalogLoadError(path, f"context key {item.key!r} is listed twice")
        keys[item.key] = item
    return keys


def _load_brand(folder: Path) -> Brand:
    return Brand(
        voice_md=_read_text(folder / "voice.md"),
        claims_md=_read_text(folder / "claims.md"),
        legal_md=_read_text(folder / "legal.md"),
        terminology=_load_yaml_model(Terminology, folder / "terminology.yaml"),
        visual=_load_yaml_model(Visual, folder / "visual.yaml"),
    )


def _load_rubric(path: Path) -> Rubric:
    frontmatter, body = _split(path)
    header = _validated(_RubricFrontmatter, frontmatter, path)
    try:
        criteria = rubric_criteria(body)
    except ValueError as exc:
        raise CatalogLoadError(path, str(exc)) from exc
    return Rubric(pass_threshold=header.pass_threshold, criteria=criteria, raw_md=body)


def _load_example(path: Path) -> GoldExample:
    frontmatter, body = _split(path)
    return _validated(GoldExample, {**frontmatter, "slug": path.stem, "body_md": body}, path)


def _load_asset_type(folder: Path) -> AssetType:
    spec = _load_yaml_model(AssetTypeSpec, folder / "spec.yaml")
    if spec.key != folder.name:
        raise CatalogLoadError(
            folder / "spec.yaml", f"key {spec.key!r} must match its folder name {folder.name!r}"
        )
    return AssetType(
        spec=spec,
        prompt_md=_read_text(folder / "prompt.md"),
        rubric=_load_rubric(folder / "rubric.md"),
        examples=[_load_example(p) for p in _example_files(folder)],
    )


def load_catalog(root: Path) -> Catalog:
    """The catalog in ``root``, or ``CatalogLoadError`` naming the first file that is missing, unreadable or
    doesn't fit the models. Whether it makes *sense* (unknown references, cycles) is the validator's job."""
    # Imported here because hashing.py imports loaded_files from this module.
    from gtm_studio.catalog.hashing import catalog_version_hash

    # In file order, so the first error reported is the first one a person would meet.
    lifecycle = _load_yaml_model(Lifecycle, root / _LIFECYCLE)
    tiers = _load_yaml_model(Tiers, root / _TIERS)
    context_keys = _load_context_keys(root / _CONTEXT_KEYS)
    brand = _load_brand(root / _BRAND)
    asset_types = {folder.name: _load_asset_type(folder) for folder in _asset_type_dirs(root)}
    return Catalog(
        lifecycle=lifecycle,
        tiers=tiers,
        context_keys=context_keys,
        brand=brand,
        asset_types=asset_types,
        version_hash=catalog_version_hash(root),
    )
