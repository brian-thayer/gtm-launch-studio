"""``CatalogService``: start-up states, reload, role sync, and the views the API serves. It runs on a
migrated database, over ``catalog_min`` or an edited copy of it."""

import shutil
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from structlog.testing import capture_logs

from gtm_studio.catalog.source import FileCatalogSource
from gtm_studio.db.models.identity import UserRole
from gtm_studio.domain.audit import AuditEventView, AuditFilters
from gtm_studio.domain.catalog import Catalog
from gtm_studio.domain.errors import NotFoundError
from gtm_studio.domain.identity import Actor, RoleRecord, RoleSource, UserRecord
from gtm_studio.services.activity import ActivityService
from gtm_studio.services.catalog import CatalogService, CatalogStartupError
from gtm_studio.services.identity import IdentityService, SeedSummary
from gtm_studio.services.ports import UnitOfWorkFactory

ADMIN_ID = "00000000-0000-4000-8000-000000000001"
HOLDER_ID = "11111111-1111-4111-8111-111111111111"
PMM_ID = "00000000-0000-4000-8000-000000000003"  # a seeded user (config/dev_users.yaml)


# ------------------------------------------------------------------ helpers
def _service(root: Path, uow_factory: UnitOfWorkFactory) -> CatalogService:
    return CatalogService(FileCatalogSource(root), uow_factory)


def _stepping_clock() -> Iterator[datetime]:
    """A clock that moves one minute on every read, so two reads are never equal."""
    moment = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
    while True:
        yield moment
        moment += timedelta(minutes=1)


def _admin(uow_factory: UnitOfWorkFactory) -> Actor:
    actor = IdentityService(uow_factory).get_actor(ADMIN_ID)
    assert actor is not None
    return actor


def _events(uow_factory: UnitOfWorkFactory) -> list[AuditEventView]:
    """The catalog's audit events, oldest first."""
    page = ActivityService(uow_factory).list_events(AuditFilters(entity_type="catalog"), limit=100)
    return list(reversed(page.items))


def _actions(uow_factory: UnitOfWorkFactory) -> list[str]:
    return [event.action for event in _events(uow_factory)]


def _roles(uow_factory: UnitOfWorkFactory) -> dict[str, RoleRecord]:
    with uow_factory() as uow:
        return {role.key: role for role in uow.identity.list_roles()}


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} is not in {path}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def _break(root: Path) -> None:
    """A catalog that loads but has an error: an asset type at a gate that doesn't exist."""
    _edit(root / "asset_types" / "brief" / "spec.yaml", "gate: gate_one", "gate: no_such_gate")


def _drop_role_b(root: Path) -> None:
    _edit(root / "lifecycle.yaml", "  - { key: role_b, label: Role B }\n", "")
    _edit(root / "lifecycle.yaml", "approver_roles: [role_a, role_b]", "approver_roles: [role_a]")


def _holder(
    uow_factory: UnitOfWorkFactory,
    role_key: str,
    *,
    role_source: RoleSource,
    active: bool,
    grant_source: RoleSource,
) -> None:
    """A user who holds ``role_key``, whose row is created as given (label = key)."""
    with uow_factory() as uow:
        uow.identity.put_role(role_key, role_key, source=role_source, active=active)
        uow.identity.upsert_user(
            UserRecord(
                id=HOLDER_ID,
                email="holder@example.test",
                display_name="Holder",
                is_active=True,
                auth_provider="dev",
                auth_subject=None,
                roles=frozenset(),
            )
        )
        uow.identity.set_roles(HOLDER_ID, [role_key], source=grant_source)


def _held(uow_factory: UnitOfWorkFactory, user_id: str = HOLDER_ID) -> frozenset[str]:
    """The active roles the user holds now (an inactive role grants nothing)."""
    actor = IdentityService(uow_factory).get_actor(user_id)
    assert actor is not None
    return actor.roles


# ------------------------------------------------------------- the source
def test_the_file_source_reads_a_folder(catalog_min_copy: Path, tmp_path: Path) -> None:
    source = FileCatalogSource(catalog_min_copy)
    assert source.present()
    catalog, issues = source.check()
    assert catalog is not None
    assert issues == []
    assert source.todo_count() == 0
    _edit(catalog_min_copy / "brand" / "voice.md", "\n", "\nTODO(confirm) tone\n")
    assert source.todo_count() == 1
    assert not FileCatalogSource(tmp_path / "nowhere").present()


# --------------------------------------------------------------- start-up
def test_a_missing_catalog_is_a_state_not_a_crash(tmp_path: Path, uow_factory: UnitOfWorkFactory) -> None:
    service = _service(tmp_path / "nowhere", uow_factory)
    with capture_logs() as logs:
        service.load_initial()
    assert any(entry["log_level"] == "warning" and "no catalog" in entry["event"] for entry in logs)
    assert service.state == "missing"
    assert service.loaded_at is None
    assert service.issues == []
    with pytest.raises(NotFoundError, match="no catalog loaded"):
        _ = service.current
    assert _actions(uow_factory) == []


def test_a_catalog_with_errors_stops_start_up_and_names_every_one(
    catalog_min_copy: Path, uow_factory: UnitOfWorkFactory
) -> None:
    _break(catalog_min_copy)
    service = _service(catalog_min_copy, uow_factory)
    with pytest.raises(CatalogStartupError) as raised:
        service.load_initial()
    assert "asset_types/brief/spec.yaml" in str(raised.value)
    assert "no_such_gate" in str(raised.value)
    assert service.state == "missing"
    assert "role_a" not in _roles(uow_factory)  # nothing was synced


def test_a_file_that_does_not_load_stops_start_up_too(
    catalog_min_copy: Path, uow_factory: UnitOfWorkFactory
) -> None:
    (catalog_min_copy / "tiers.yaml").write_text("tiers: [unclosed\n", encoding="utf-8")
    with pytest.raises(CatalogStartupError, match=r"tiers\.yaml"):
        _service(catalog_min_copy, uow_factory).load_initial()


def test_a_catalog_with_only_warnings_loads_and_counts_the_markers(
    catalog_min_copy: Path, uow_factory: UnitOfWorkFactory
) -> None:
    _edit(catalog_min_copy / "brand" / "voice.md", "\n", "\nTODO(confirm) tone\n")
    service = _service(catalog_min_copy, uow_factory)
    service.load_initial()
    assert service.state == "ok"
    assert [(issue.level, issue.where) for issue in service.issues] == [("warning", "brand/voice.md")]
    assert service.snapshot.todo_count == 1
    assert service.loaded_at is not None


def test_loading_syncs_the_catalogs_roles_and_audits_it_as_the_system(
    catalog_min: Catalog, uow_factory: UnitOfWorkFactory, catalog_min_dir: Path
) -> None:
    service = _service(catalog_min_dir, uow_factory)
    service.load_initial()
    assert service.current == catalog_min
    roles = _roles(uow_factory)
    assert (roles["role_a"].label, roles["role_a"].source, roles["role_a"].active) == (
        "Role A",
        "catalog",
        True,
    )
    assert roles["role_b"].source == "catalog"
    [event] = _events(uow_factory)
    assert (event.action, event.actor_user_id, event.actor_display) == (
        "catalog.roles_synced",
        None,
        "system",
    )
    assert event.details == {
        "created": ["role_a", "role_b"],
        "activated": [],
        "deactivated": [],
        "relabelled": [],
    }


# ----------------------------------------------------------------- reload
def test_a_reload_with_errors_keeps_the_old_catalog_and_audits_the_rejection(
    catalog_min_copy: Path, uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    service = _service(catalog_min_copy, uow_factory)
    service.load_initial()
    old = service.current
    _break(catalog_min_copy)

    result = service.reload(_admin(uow_factory))

    assert not result.ok
    assert result.old_hash == old.version_hash
    assert result.new_hash is not None
    assert result.new_hash != old.version_hash  # the files did load: they are just not valid
    assert [(issue.level, issue.where) for issue in result.issues] == [
        ("error", "asset_types/brief/spec.yaml: gate")
    ]
    assert service.current is old  # the very same object: nothing was swapped
    reject = _events(uow_factory)[-1]
    assert (reject.action, reject.actor_display) == ("catalog.reload_rejected", "Avery Admin")
    assert reject.details == {
        "old_hash": old.version_hash,
        "new_hash": result.new_hash,
        "errors": 1,
        "warnings": 0,
        "todo_count": 0,
    }


def test_a_reload_after_the_folder_was_deleted_is_rejected_and_keeps_the_catalog(
    catalog_min_copy: Path, uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    service = _service(catalog_min_copy, uow_factory)
    service.load_initial()
    old = service.current
    shutil.rmtree(catalog_min_copy)

    result = service.reload(_admin(uow_factory))

    assert (result.ok, result.old_hash, result.new_hash) == (False, old.version_hash, None)
    assert service.current is old
    assert _events(uow_factory)[-1].action == "catalog.reload_rejected"


def test_a_reload_of_files_that_do_not_load_has_no_new_hash(
    catalog_min_copy: Path, uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    service = _service(catalog_min_copy, uow_factory)
    service.load_initial()
    (catalog_min_copy / "tiers.yaml").write_text("tiers: [unclosed\n", encoding="utf-8")
    result = service.reload(_admin(uow_factory))
    assert (result.ok, result.new_hash) == (False, None)
    assert [issue.where for issue in result.issues] == ["tiers.yaml"]
    assert _events(uow_factory)[-1].details["new_hash"] is None


def test_a_good_reload_swaps_audits_both_hashes_and_syncs_the_roles(
    catalog_min_copy: Path, uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    ticks = _stepping_clock()
    service = CatalogService(FileCatalogSource(catalog_min_copy), uow_factory, clock=lambda: next(ticks))
    service.load_initial()
    old = service.current
    assert service.loaded_at == datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
    _edit(catalog_min_copy / "lifecycle.yaml", "label: Role A", "label: Role Alpha")

    result = service.reload(_admin(uow_factory))

    assert result.ok
    assert result.old_hash == old.version_hash
    assert result.new_hash == service.current.version_hash != old.version_hash
    assert service.current is not old
    assert service.loaded_at == datetime(2026, 11, 25, 12, 1, tzinfo=UTC)  # the reload read the clock once
    assert _roles(uow_factory)["role_a"].label == "Role Alpha"
    assert _actions(uow_factory) == ["catalog.roles_synced", "catalog.reloaded", "catalog.roles_synced"]
    reloaded, synced = _events(uow_factory)[1:]
    assert (reloaded.actor_display, reloaded.details) == (
        "Avery Admin",
        {
            "old_hash": old.version_hash,
            "new_hash": result.new_hash,
            "errors": 0,
            "warnings": 0,
            "todo_count": 0,
        },
    )
    assert synced.actor_display == "Avery Admin"
    assert synced.details["relabelled"] == ["role_a"]


def test_reloading_unchanged_files_swaps_nothing_new_and_syncs_nothing(
    catalog_min_dir: Path, uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    service = _service(catalog_min_dir, uow_factory)
    service.load_initial()
    result = service.reload(_admin(uow_factory))
    assert result.ok
    assert result.old_hash == result.new_hash
    assert _actions(uow_factory) == ["catalog.roles_synced", "catalog.reloaded"]  # no second sync event


def test_reloading_a_missing_catalog_that_is_still_missing_is_rejected(
    tmp_path: Path, uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    service = _service(tmp_path / "nowhere", uow_factory)
    service.load_initial()
    result = service.reload(_admin(uow_factory))
    assert (result.ok, result.old_hash, result.new_hash) == (False, None, None)
    assert [(issue.level, issue.where) for issue in result.issues] == [("error", "lifecycle.yaml")]
    assert service.state == "missing"
    assert _actions(uow_factory) == ["catalog.reload_rejected"]


def test_a_catalog_added_after_start_up_loads_on_reload(
    tmp_path: Path, catalog_min_dir: Path, uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    root = tmp_path / "later"
    root.mkdir()
    service = _service(root, uow_factory)
    service.load_initial()
    assert service.state == "missing"
    shutil.copytree(catalog_min_dir, root, dirs_exist_ok=True)

    result = service.reload(_admin(uow_factory))

    assert (result.ok, result.old_hash) == (True, None)
    assert service.state == "ok"
    assert "role_a" in _roles(uow_factory)
    assert _actions(uow_factory) == ["catalog.reloaded", "catalog.roles_synced"]


# -------------------------------------------------------------- role sync
def test_the_sync_activates_an_inactive_oidc_role_and_its_holders_get_it_back(
    catalog_min_dir: Path, uow_factory: UnitOfWorkFactory
) -> None:
    # S09: an IdP group mapped to a key nothing declares creates the role inactive.
    _holder(uow_factory, "role_a", role_source="oidc", active=False, grant_source="oidc")
    assert _held(uow_factory) == frozenset()

    _service(catalog_min_dir, uow_factory).load_initial()

    assert _held(uow_factory) == {"role_a"}
    role = _roles(uow_factory)["role_a"]
    assert (role.label, role.source, role.active) == ("Role A", "catalog", True)
    assert _events(uow_factory)[0].details["activated"] == ["role_a"]


def test_the_sync_takes_over_a_dev_seed_role_without_touching_other_dev_roles(
    catalog_min_dir: Path, uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    _holder(uow_factory, "role_a", role_source="dev_seed", active=True, grant_source="dev_seed")
    assert _held(uow_factory) == {"role_a"}

    _service(catalog_min_dir, uow_factory).load_initial()

    assert _held(uow_factory) == {"role_a"}  # the grant is the same one
    roles = _roles(uow_factory)
    assert (roles["role_a"].label, roles["role_a"].source) == ("Role A", "catalog")
    assert _events(uow_factory)[0].details["relabelled"] == ["role_a"]
    assert (roles["pmm"].source, roles["pmm"].active) == ("dev_seed", True)  # not in the catalog: left alone
    assert (roles["admin"].source, roles["viewer"].source) == ("system", "system")


def test_the_sync_deactivates_a_removed_catalog_role_but_keeps_its_grants(
    catalog_min_copy: Path, uow_factory: UnitOfWorkFactory, migrated_engine: Engine, seeded: SeedSummary
) -> None:
    service = _service(catalog_min_copy, uow_factory)
    service.load_initial()
    with uow_factory() as uow:  # role_b is a catalog role now: grant it to someone
        uow.identity.set_roles(PMM_ID, ["pmm", "role_b"], source="dev_seed")
    assert "role_b" in _held(uow_factory, PMM_ID)

    _drop_role_b(catalog_min_copy)
    assert service.reload(_admin(uow_factory)).ok

    assert _roles(uow_factory)["role_b"].active is False
    assert _held(uow_factory, PMM_ID) == {"pmm"}  # an inactive role grants nothing
    with Session(migrated_engine) as session:  # but the grant row stays, for history
        kept = session.scalars(select(UserRole).where(UserRole.role_key == "role_b")).all()
    assert [grant.user_id for grant in kept] == [PMM_ID]
    assert _events(uow_factory)[-1].details["deactivated"] == ["role_b"]


def test_a_removed_role_that_comes_back_is_active_again_with_its_grants(
    catalog_min_copy: Path, uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    service = _service(catalog_min_copy, uow_factory)
    service.load_initial()
    with uow_factory() as uow:
        uow.identity.set_roles(PMM_ID, ["pmm", "role_b"], source="dev_seed")
    shutil.copy(catalog_min_copy / "lifecycle.yaml", catalog_min_copy / "lifecycle.keep")
    _drop_role_b(catalog_min_copy)
    service.reload(_admin(uow_factory))
    assert "role_b" not in _held(uow_factory, PMM_ID)

    shutil.copy(catalog_min_copy / "lifecycle.keep", catalog_min_copy / "lifecycle.yaml")
    assert service.reload(_admin(uow_factory)).ok

    assert _held(uow_factory, PMM_ID) == {"pmm", "role_b"}
    assert _events(uow_factory)[-1].details["activated"] == ["role_b"]


def test_a_second_sync_with_nothing_to_change_writes_no_event(
    catalog_min_dir: Path, uow_factory: UnitOfWorkFactory
) -> None:
    service = _service(catalog_min_dir, uow_factory)
    service.load_initial()
    result = service.sync_roles(None)
    assert not result.changed
    assert _actions(uow_factory) == ["catalog.roles_synced"]  # only the first one


# ------------------------------------------------------------------ views
def test_the_matrix_view_names_the_cells_in_gate_order(
    catalog_min_dir: Path, uow_factory: UnitOfWorkFactory
) -> None:
    service = _service(catalog_min_dir, uow_factory)
    service.load_initial()
    view = service.matrix_view()
    assert [gate.key for gate in view.gates] == ["gate_one", "gate_two"]
    assert [row.tier.key for row in view.rows] == ["tier_big", "tier_small"]
    big, small = view.rows
    assert [[ref.key for ref in cell] for cell in big.cells] == [["brief", "classify"], ["deep_dive"]]
    assert big.cells[1][0].name == "Deep dive"
    assert [[ref.key for ref in cell] for cell in small.cells] == [["brief", "classify"], []]
    assert [ref.key for ref in big.optional] == ["extra_note"]
    assert small.optional == []
    assert [(t.key, [ref.key for ref in t.assets]) for t in big.triggers] == [
        ("needs_setup", ["setup_guide"])
    ]
    assert view.undefined_assets == []


def test_the_matrix_view_leaves_out_assets_with_no_type_and_lists_them_apart(
    catalog_min_copy: Path, uow_factory: UnitOfWorkFactory
) -> None:
    _edit(catalog_min_copy / "tiers.yaml", "optional: [extra_note]", "optional: [extra_note, not_yet]")
    service = _service(catalog_min_copy, uow_factory)
    service.load_initial()
    view = service.matrix_view()
    assert [ref.key for ref in view.rows[0].optional] == ["extra_note"]
    assert view.undefined_assets == ["not_yet"]


def test_an_asset_type_view_resolves_its_approver_roles(
    catalog_min_dir: Path, uow_factory: UnitOfWorkFactory
) -> None:
    service = _service(catalog_min_dir, uow_factory)
    service.load_initial()
    assert service.asset_type_view("brief").approver_roles == ["role_a"]  # gate_one
    assert service.asset_type_view("deep_dive").approver_roles == ["role_a", "role_b"]  # gate_two
    with pytest.raises(NotFoundError) as unknown:
        service.asset_type_view("no_such")
    assert unknown.value.detail == "no such asset type"  # not the key: it came from a URL


def test_the_views_need_a_catalog(tmp_path: Path, uow_factory: UnitOfWorkFactory) -> None:
    service = _service(tmp_path / "nowhere", uow_factory)
    service.load_initial()
    for view in (service.matrix_view, service.brand_view, lambda: service.asset_type_view("brief")):
        with pytest.raises(NotFoundError, match="no catalog loaded"):
            view()
    with pytest.raises(NotFoundError, match="no catalog loaded"):
        service.sync_roles(None)
