"""Does a loaded catalog make sense? Pure: it checks a ``Catalog`` and never reads a file.

The loader (``catalog/``) only proves each file fits its model. This module finds the mistakes a model
can't: an unknown gate, a dependency cycle, a gate nobody (or everybody) can approve. It returns every
problem at once, ordered by file and then location, so the output is stable.

Errors stop the app from using the catalog. Warnings are things worth a look; with ``strict`` they become
errors. (``TODO(confirm)`` markers are warnings that ``catalog/source.py`` adds, and they stay warnings.)
"""

from collections import Counter
from collections.abc import Collection, Iterable, Mapping

from gtm_studio.domain.catalog import Catalog, Issue
from gtm_studio.domain.identity import SYSTEM_ROLES, check_role_key

_ASSET_TYPES = "asset_types"


class _Issues:
    def __init__(self, *, strict: bool) -> None:
        self._strict = strict
        self._found: list[Issue] = []

    def error(self, where: str, message: str) -> None:
        self._found.append(Issue(level="error", where=where, message=message))

    def warning(self, where: str, message: str) -> None:
        level = "error" if self._strict else "warning"
        self._found.append(Issue(level=level, where=where, message=message))

    def ordered(self) -> list[Issue]:
        return sorted(self._found, key=lambda issue: (issue.where, issue.message))


def validate(catalog: Catalog, *, families: Collection[str], strict: bool = False) -> list[Issue]:
    """Every problem in ``catalog``. ``families`` are the output families the backend can render."""
    out = _Issues(strict=strict)
    _check_keys(catalog, out)
    _check_roles(catalog, out)
    _check_tiers(catalog, out)
    _check_asset_types(catalog, families, out)
    _check_dependencies(catalog, out)
    _check_brand(catalog, out)
    if not catalog.lifecycle.approved_gate_values:
        out.error("lifecycle.yaml: approved_gate_values", "empty: no gate value would count as approved")
    return out.ordered()


def _duplicates[T: (str, int)](values: Iterable[T]) -> list[T]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


# --------------------------------------------------------------------- keys
def _check_keys(catalog: Catalog, out: _Issues) -> None:
    lifecycle, tiers = catalog.lifecycle, catalog.tiers
    for key in _duplicates(role.key for role in lifecycle.roles):
        out.error("lifecycle.yaml: roles", f"duplicate role key {key!r}")
    for key in _duplicates(gate.key for gate in lifecycle.gates):
        out.error("lifecycle.yaml: gates", f"duplicate gate key {key!r}")
    for order in _duplicates(gate.order for gate in lifecycle.gates):
        shared = [gate.key for gate in lifecycle.gates if gate.order == order]
        out.error("lifecycle.yaml: gates", f"gates {shared} share order {order}")
    for key in _duplicates(tier.key for tier in tiers.tiers):
        out.error("tiers.yaml: tiers", f"duplicate tier key {key!r}")
    for rank in _duplicates(tier.rank for tier in tiers.tiers):
        shared = [tier.key for tier in tiers.tiers if tier.rank == rank]
        out.error("tiers.yaml: tiers", f"tiers {shared} share rank {rank}")
    for key in _duplicates(trigger.key for trigger in tiers.triggers):
        out.error("tiers.yaml: triggers", f"duplicate trigger key {key!r}")
    # These two are dicts, so a repeat can only show as an entry filed under another name.
    _check_declared_keys(
        {name: item.key for name, item in catalog.context_keys.items()},
        "context_keys.yaml",
        "context key",
        out,
    )
    _check_declared_keys(
        {name: item.spec.key for name, item in catalog.asset_types.items()}, _ASSET_TYPES, "asset type", out
    )


def _check_declared_keys(declared: Mapping[str, str], where: str, what: str, out: _Issues) -> None:
    for name, key in sorted(declared.items()):
        if name != key:
            out.error(where, f"{what} filed as {name!r} but declares the key {key!r}")
    for key in _duplicates(declared.values()):
        out.error(where, f"duplicate {what} {key!r}")


# -------------------------------------------------------------------- roles
def _role_problem(role: str, defined: Collection[str]) -> str | None:
    """Why ``role`` can't be an approver role here, or None. System roles never approve (ADR-0002)."""
    if role in SYSTEM_ROLES:
        return f"{role!r} is a system role, not an approver role (it would let every {role} approve)"
    try:
        check_role_key(role)
    except ValueError as exc:
        return str(exc)
    if role not in defined:
        return f"role {role!r} is not declared in lifecycle.yaml roles"
    return None


def _check_role_refs(roles: Iterable[str], defined: Collection[str], where: str, out: _Issues) -> None:
    for role in roles:
        if problem := _role_problem(role, defined):
            out.error(where, problem)


def _check_roles(catalog: Catalog, out: _Issues) -> None:
    defined = {role.key for role in catalog.lifecycle.roles}
    for role in catalog.lifecycle.roles:
        if problem := _role_problem(role.key, {role.key}):  # declared by definition: only its shape counts
            out.error(f"lifecycle.yaml: roles[{role.key}]", problem)
    for gate in catalog.lifecycle.gates:
        where = f"lifecycle.yaml: gates[{gate.key}].approver_roles"
        if not gate.approver_roles:
            out.error(where, f"gate {gate.key!r} has no approver roles")
        _check_role_refs(gate.approver_roles, defined, where, out)
    for key, asset in sorted(catalog.asset_types.items()):
        override = asset.spec.approver_roles
        if override is not None:
            where = f"{_ASSET_TYPES}/{key}/spec.yaml: approver_roles"
            if not override:
                out.error(where, "an empty override: nobody could approve this asset")
            _check_role_refs(override, defined, where, out)


# -------------------------------------------------------------------- tiers
def _check_tiers(catalog: Catalog, out: _Issues) -> None:
    tier_keys = {tier.key for tier in catalog.tiers.tiers}
    for tier in catalog.tiers.tiers:
        where = f"tiers.yaml: tiers[{tier.key}]"
        for key in sorted(set(tier.core) & set(tier.optional)):
            out.error(f"{where}.optional", f"asset {key!r} is in both core and optional")
        if tier.timing is not None:
            _check_context_type(catalog, tier.timing.anchor, "date", f"{where}.timing.anchor", out)
        # With inherits_lower the tier's own core may be empty and still get assets from the tiers below.
        if not catalog.core_assets(tier.key):
            out.warning(f"{where}.core", f"tier {tier.key!r} has no core assets")
        for field, keys in (("core", tier.core), ("optional", tier.optional)):
            _warn_undefined(catalog, keys, f"{where}.{field}", out)
    for trigger in catalog.tiers.triggers:
        where = f"tiers.yaml: triggers[{trigger.key}]"
        if trigger.context_key is not None:
            _check_context_type(catalog, trigger.context_key, "boolean", f"{where}.context_key", out)
        for key in trigger.tiers or []:
            if key not in tier_keys:
                out.error(f"{where}.tiers", f"unknown tier {key!r}")
        _warn_undefined(catalog, trigger.assets, f"{where}.assets", out)


def _check_context_type(catalog: Catalog, key: str, wanted: str, where: str, out: _Issues) -> None:
    context_key = catalog.context_keys.get(key)
    if context_key is None:
        out.error(where, f"unknown context key {key!r}")
    elif context_key.type != wanted:
        out.error(where, f"context key {key!r} is of type {context_key.type}, but must be {wanted}")


def _warn_undefined(catalog: Catalog, keys: Iterable[str], where: str, out: _Issues) -> None:
    for key in keys:
        if key not in catalog.asset_types:
            out.warning(where, f"asset {key!r} has no asset type folder yet")


# -------------------------------------------------------------- asset types
def _check_asset_types(catalog: Catalog, families: Collection[str], out: _Issues) -> None:
    gate_keys = {gate.key for gate in catalog.lifecycle.gates}
    referenced = {key for tier in catalog.tiers.tiers for key in (*tier.core, *tier.optional)}
    referenced |= {key for trigger in catalog.tiers.triggers for key in trigger.assets}
    deciders = sorted(key for key, asset in catalog.asset_types.items() if asset.spec.decides == "tier")
    if not deciders:
        out.warning(_ASSET_TYPES, "no asset type decides the tier (decides: tier)")
    for key, asset in sorted(catalog.asset_types.items()):
        spec, folder = asset.spec, f"{_ASSET_TYPES}/{key}"
        if spec.gate not in gate_keys:
            out.error(f"{folder}/spec.yaml: gate", f"unknown gate {spec.gate!r}")
        if spec.family not in families:
            out.error(f"{folder}/spec.yaml: family", f"unknown family {spec.family!r}")
        for context_key in spec.required_context:
            if context_key not in catalog.context_keys:
                out.error(f"{folder}/spec.yaml: required_context", f"unknown context key {context_key!r}")
        if spec.decides == "tier":
            if not spec.foundation:
                out.error(f"{folder}/spec.yaml: decides", "an asset that decides the tier must be foundation")
            if len(deciders) > 1:
                out.error(
                    f"{folder}/spec.yaml: decides", f"more than one asset type decides the tier: {deciders}"
                )
        if key not in referenced:
            out.warning(f"{folder}/spec.yaml", f"asset type {key!r} is in no tier and no trigger")
        rubric = asset.rubric
        if not 1 <= rubric.pass_threshold <= 5:
            out.error(f"{folder}/rubric.md", f"pass_threshold {rubric.pass_threshold} is outside 1 to 5")
        if not rubric.criteria:
            out.error(f"{folder}/rubric.md", "the rubric has no criteria (one '## ' heading each)")
        if not asset.examples:
            out.warning(f"{folder}/examples", "no gold examples")
        for example in asset.examples:
            if not example.redacted:
                out.error(f"{folder}/examples/{example.slug}.md", "a gold example must have redacted: true")


def _check_dependencies(catalog: Catalog, out: _Issues) -> None:
    gate_order = {gate.key: gate.order for gate in catalog.lifecycle.gates}
    graph: dict[str, list[str]] = {}
    for key, asset in sorted(catalog.asset_types.items()):
        where = f"{_ASSET_TYPES}/{key}/spec.yaml: depends_on"
        graph[key] = []
        for dependency in asset.spec.depends_on:
            if dependency not in catalog.asset_types:
                out.error(where, f"unknown dependency {dependency!r}")
                continue
            graph[key].append(dependency)
            own, theirs = (
                gate_order.get(asset.spec.gate),
                gate_order.get(catalog.asset_types[dependency].spec.gate),
            )
            if own is not None and theirs is not None and theirs > own:
                out.error(where, f"{dependency!r} is at a later gate than {key!r}")
    for cycle in _cycles(graph):
        out.error(
            f"{_ASSET_TYPES}/{cycle[0]}/spec.yaml: depends_on", f"cycle: {' -> '.join([*cycle, cycle[0]])}"
        )


def _cycles(graph: Mapping[str, list[str]]) -> list[list[str]]:
    """The dependency cycles found by a depth-first walk in key order, each once and starting at its
    smallest key. Overlapping cycles may be reported one at a time as the earlier ones are fixed."""
    found: dict[tuple[str, ...], None] = {}
    state: dict[str, int] = {}  # absent: unseen, 1: on the current path, 2: finished
    path: list[str] = []

    def visit(node: str) -> None:
        state[node] = 1
        path.append(node)
        for dependency in sorted(graph[node]):
            if state.get(dependency) == 1:
                cycle = path[path.index(dependency) :]
                start = cycle.index(min(cycle))
                found[tuple(cycle[start:] + cycle[:start])] = None
            elif dependency not in state:
                visit(dependency)
        path.pop()
        state[node] = 2

    for node in sorted(graph):
        if node not in state:
            visit(node)
    return [list(cycle) for cycle in found]


# -------------------------------------------------------------------- brand
def _check_brand(catalog: Catalog, out: _Issues) -> None:
    brand = catalog.brand
    for name, text in (
        ("voice.md", brand.voice_md),
        ("claims.md", brand.claims_md),
        ("legal.md", brand.legal_md),
    ):
        if not text.strip():
            out.error(f"brand/{name}", "the file is empty")
