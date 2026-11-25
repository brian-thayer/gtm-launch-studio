"""The catalog in the running app: loaded at start-up, replaced when an admin reloads it, and the source of
the approver roles (ADR-0005).

One ``CatalogService`` lives for the life of the process (``app.state.catalog_service``). Catalogs are
frozen, so a reader sees either the old catalog or the new one, never a mix. A reload reads and validates
the files **outside** the lock and swaps one reference under it, and only when there are no errors.

A reload changes this process only. The worker and any other API process keep their catalog until they
restart (S33 makes the worker compare ``version_hash`` before each job).
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import structlog

from gtm_studio.domain.audit import AuditAction
from gtm_studio.domain.catalog import AssetType, Brand, Catalog, Gate, Issue, IssueSummary, Tier
from gtm_studio.domain.clock import utcnow
from gtm_studio.domain.errors import NotFoundError
from gtm_studio.domain.identity import SYSTEM_ROLES, Actor
from gtm_studio.services.ports import CatalogSource, UnitOfWork, UnitOfWorkFactory

log = structlog.get_logger()

CATALOG_ENTITY = "catalog"  # audit_events.entity_type and entity_id: there is one catalog

CatalogState = Literal["ok", "missing"]


class CatalogStartupError(Exception):
    """The catalog is present but has errors, so the app must not start on it. The message lists them all."""

    def __init__(self, errors: list[Issue]) -> None:
        lines = [f"  {issue.where}: {issue.message}" for issue in errors]
        header = f"the catalog has {len(errors)} error(s)" if errors else "the catalog could not be loaded"
        super().__init__("\n".join([header, *lines]))
        self.errors = errors


@dataclass(frozen=True)
class LoadedCatalog:
    """A catalog with what was found when it was loaded: one value, so a reader sees one consistent state."""

    catalog: Catalog
    issues: list[Issue]
    todo_count: int
    loaded_at: datetime

    @property
    def summary(self) -> IssueSummary:
        return _summary(self.issues, self.todo_count)


@dataclass(frozen=True)
class ReloadResult:
    ok: bool
    old_hash: str | None
    new_hash: str | None  # None when the files didn't load at all
    issues: list[Issue]


@dataclass(frozen=True)
class RoleSyncResult:
    """What a role sync changed, as role keys. ``relabelled`` covers an active role that already existed
    and now has the catalog's label or source (a ``dev_seed`` or ``oidc`` row taking over the key)."""

    created: list[str]
    activated: list[str]
    deactivated: list[str]
    relabelled: list[str]

    @property
    def changed(self) -> bool:
        return bool(self.created or self.activated or self.deactivated or self.relabelled)


# ----------------------------------------------------------- views for the API
@dataclass(frozen=True)
class AssetRef:
    key: str
    name: str


@dataclass(frozen=True)
class MatrixTrigger:
    key: str
    label: str
    assets: list[AssetRef]


@dataclass(frozen=True)
class MatrixRow:
    tier: Tier
    cells: list[list[AssetRef]]  # one list per gate, in gate order
    optional: list[AssetRef]
    triggers: list[MatrixTrigger]


@dataclass(frozen=True)
class MatrixView:
    gates: list[Gate]
    rows: list[MatrixRow]
    undefined_assets: list[str]  # named by a tier or trigger but with no asset type yet


@dataclass(frozen=True)
class AssetTypeView:
    asset_type: AssetType
    approver_roles: list[str]  # its own override, else its gate's


def _summary(issues: list[Issue], todo_count: int) -> IssueSummary:
    return IssueSummary(
        errors=sum(issue.level == "error" for issue in issues),
        warnings=sum(issue.level == "warning" for issue in issues),
        todo_count=todo_count,
    )


class CatalogService:
    def __init__(
        self,
        source: CatalogSource,
        uow_factory: UnitOfWorkFactory,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._source = source
        self._uow_factory = uow_factory
        self._clock = clock
        self._lock = threading.Lock()  # guards the swap of ``_loaded``; readers never take it
        self._reload_lock = threading.Lock()  # one reload at a time, so the roles match the catalog served
        self._loaded: LoadedCatalog | None = None

    # ---- state
    @property
    def state(self) -> CatalogState:
        return "ok" if self._loaded is not None else "missing"

    @property
    def snapshot(self) -> LoadedCatalog:
        """The catalog with its issues and load time, as one value. Raises ``NotFoundError`` when missing."""
        loaded = self._loaded
        if loaded is None:
            raise NotFoundError("no catalog loaded")
        return loaded

    @property
    def current(self) -> Catalog:
        return self.snapshot.catalog

    @property
    def version_hash(self) -> str | None:
        """The loaded catalog's hash, read once; None when there is no catalog."""
        loaded = self._loaded
        return loaded.catalog.version_hash if loaded is not None else None

    @property
    def loaded_at(self) -> datetime | None:
        return self._loaded.loaded_at if self._loaded is not None else None

    @property
    def issues(self) -> list[Issue]:
        return list(self._loaded.issues) if self._loaded is not None else []

    # ---- loading
    def load_initial(self) -> None:
        """Called once at start-up, after the database exists. No catalog is a state (endpoints answer 404);
        a catalog with errors raises ``CatalogStartupError``, which stops the app."""
        if not self._source.present():
            log.warning("no catalog loaded: catalog endpoints answer 404 until one is added and reloaded")
            return
        catalog, issues = self._source.check()
        errors = [issue for issue in issues if issue.level == "error"]
        if catalog is None or errors:
            raise CatalogStartupError(errors)
        todo_count = self._source.todo_count()
        self._loaded = LoadedCatalog(catalog, issues, todo_count, self._clock())
        summary = _summary(issues, todo_count)
        log.info(
            "catalog loaded",
            version=catalog.version_hash,
            warnings=summary.warnings,
            todo_count=summary.todo_count,
        )
        self.sync_roles(None)

    def reload(self, actor: Actor) -> ReloadResult:
        """Read the files again. With no errors the new catalog replaces the old one (and the roles are
        synced); with errors the old one stays. Either way it is audited, and the result carries every issue.

        The role sync and the ``catalog.reloaded`` event commit together, **before** the swap: if the
        database fails, nothing has changed. Reloads run one at a time (two at once could leave the roles
        matching a different catalog from the one served); readers are never blocked."""
        with self._reload_lock:
            return self._reload(actor)

    def _reload(self, actor: Actor) -> ReloadResult:
        old = self._loaded
        old_hash = old.catalog.version_hash if old is not None else None
        if self._source.present():
            catalog, issues = self._source.check()
        else:
            catalog, issues = None, [Issue(level="error", where="lifecycle.yaml", message="no catalog found")]
        todo_count = self._source.todo_count() if catalog is not None else 0
        summary = _summary(issues, todo_count)
        new_hash = catalog.version_hash if catalog is not None else None
        details: dict[str, Any] = {"old_hash": old_hash, "new_hash": new_hash, **summary.model_dump()}

        if catalog is None or summary.errors:
            with self._uow_factory() as uow:
                uow.audit.record(
                    actor,
                    AuditAction.CATALOG_RELOAD_REJECTED,
                    CATALOG_ENTITY,
                    CATALOG_ENTITY,
                    details=details,
                )
            log.warning("catalog reload rejected", errors=summary.errors, kept=old_hash)
            return ReloadResult(ok=False, old_hash=old_hash, new_hash=new_hash, issues=issues)

        with self._uow_factory() as uow:
            uow.audit.record(
                actor, AuditAction.CATALOG_RELOADED, CATALOG_ENTITY, CATALOG_ENTITY, details=details
            )
            self._sync(uow, actor, catalog)
        loaded = LoadedCatalog(catalog, issues, todo_count, self._clock())
        with self._lock:
            self._loaded = loaded
        log.info("catalog reloaded", old=old_hash, new=new_hash)
        return ReloadResult(ok=True, old_hash=old_hash, new_hash=new_hash, issues=issues)

    # ---- roles
    def sync_roles(self, actor: Actor | None) -> RoleSyncResult:
        """Make the roles table match the current catalog, in one unit of work (see ``_sync``)."""
        catalog = self.current
        with self._uow_factory() as uow:
            return self._sync(uow, actor, catalog)

    @staticmethod
    def _sync(uow: UnitOfWork, actor: Actor | None, catalog: Catalog) -> RoleSyncResult:
        """Every role the catalog declares becomes ``source=catalog, active=True`` (whatever row held the
        key before: a ``dev_seed`` or ``oidc`` role is taken over and its grants take effect at the holders'
        next request). A ``catalog`` role the catalog no longer lists becomes inactive; its grants are kept
        for history. System roles are never touched. One ``catalog.roles_synced`` event, only on a change."""
        repo = uow.identity
        before = {role.key: role for role in repo.list_roles()}
        created: list[str] = []
        activated: list[str] = []
        relabelled: list[str] = []
        deactivated: list[str] = []
        declared: set[str] = set()
        for role in catalog.lifecycle.roles:
            if role.key in SYSTEM_ROLES:
                continue  # the validator refuses these; never touch them even so
            declared.add(role.key)
            if not repo.put_role(role.key, role.label, source="catalog", active=True):
                continue
            previous = before.get(role.key)
            if previous is None:
                created.append(role.key)
            elif not previous.active:
                activated.append(role.key)
            else:
                relabelled.append(role.key)
        for key, previous in before.items():
            if previous.source == "catalog" and previous.active and key not in declared:
                repo.put_role(key, previous.label, source="catalog", active=False)
                deactivated.append(key)
        result = RoleSyncResult(created, activated, deactivated, relabelled)
        if result.changed:
            uow.audit.record(
                actor,
                AuditAction.CATALOG_ROLES_SYNCED,
                CATALOG_ENTITY,
                CATALOG_ENTITY,
                details={
                    "created": created,
                    "activated": activated,
                    "deactivated": deactivated,
                    "relabelled": relabelled,
                },
            )
        return result

    # ---- views (plain values for the routers: no logic there)
    def matrix_view(self) -> MatrixView:
        """The tier x gate matrix with names, from ``Catalog`` helpers only. An asset key with no asset type
        is left out of every list and reported in ``undefined_assets``."""
        catalog = self.current
        grid = catalog.matrix()
        gates = catalog.gates_in_order()

        def refs(keys: list[str]) -> list[AssetRef]:
            return [
                AssetRef(key, catalog.asset_types[key].spec.name)
                for key in keys
                if key in catalog.asset_types
            ]

        rows = [
            MatrixRow(
                tier=tier,
                cells=[refs(grid[tier.key][gate.key]) for gate in gates],
                optional=refs(catalog.optional_assets(tier.key)),
                triggers=[
                    MatrixTrigger(trigger.key, trigger.label, refs(trigger.assets))
                    for trigger in catalog.triggers_for(tier.key)
                ],
            )
            for tier in catalog.tiers_by_rank()
        ]
        return MatrixView(gates, rows, sorted(catalog.undefined_asset_keys()))

    def asset_type_view(self, key: str) -> AssetTypeView:
        """Raises ``NotFoundError`` for a key that isn't an asset type. Its message is generic: the key came
        from a URL and ``detail`` goes back to the client as it is."""
        catalog = self.current
        if key not in catalog.asset_types:
            raise NotFoundError("no such asset type")
        return AssetTypeView(catalog.asset_type(key), catalog.approver_roles_for(key))

    def brand_view(self) -> Brand:
        return self.current.brand
