"""``/api/catalog``: read-only for anyone with ``catalog:read``, a reload for admins, and a clear state when
there is no catalog. Most tests run on ``catalog_min`` (the ``settings`` fixture); the two classes at the end
point the app at a folder they can change."""

import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gtm_studio.domain.catalog import Catalog
from gtm_studio.domain.identity import DevUserSeed
from gtm_studio.services.identity import IdentityService, SeedSummary
from gtm_studio.services.ports import UnitOfWorkFactory
from gtm_studio.settings import Settings

CSRF = {"X-Requested-With": "gtm-studio"}
GETS = ["/api/catalog", "/api/catalog/matrix", "/api/catalog/asset-types/brief", "/api/catalog/brand"]
ROLE_A_USER = "22222222-2222-4222-8222-222222222222"


def _catalog_events(admin: TestClient, action_prefix: str = "catalog.") -> list[dict[str, Any]]:
    response = admin.get("/api/activity", params={"entity_type": "catalog", "action_prefix": action_prefix})
    assert response.status_code == 200, response.text
    return response.json()["items"]


# ---------------------------------------------------------------- reading
def test_reading_the_catalog_needs_a_session(client: TestClient) -> None:
    assert [client.get(path).status_code for path in GETS] == [401] * 4


def test_a_viewer_reads_all_four_endpoints(login_as: Any) -> None:
    viewer = login_as("viewer")
    assert [viewer.get(path).status_code for path in GETS] == [200] * 4


def test_the_overview_lists_what_the_catalog_declares(login_as: Any, catalog_min: Catalog) -> None:
    body = login_as("viewer").get("/api/catalog").json()
    assert body["version_hash"] == catalog_min.version_hash
    assert body["loaded_at"].endswith("Z") or "+" in body["loaded_at"]  # timezone-aware
    assert body["issues"] == {"errors": 0, "warnings": 0, "todo_count": 0, "items": []}
    assert body["roles"] == [{"key": "role_a", "label": "Role A"}, {"key": "role_b", "label": "Role B"}]
    assert [(g["key"], g["short"], g["approver_roles"]) for g in body["gates"]] == [
        ("gate_one", "One", ["role_a"]),
        ("gate_two", "Two", ["role_a", "role_b"]),
    ]
    assert body["gates"][1]["release_gate"] is True
    big, small = body["tiers"]
    assert (big["key"], big["rank"], small["key"], small["rank"]) == ("tier_big", 1, "tier_small", 2)
    assert big["timing"] == {
        "anchor": "facts.launch_date",
        "anchor_label": "Launch date",  # from context_keys.yaml
        "plan_start_days": -56,
        "core_due_days": -14,
    }
    assert small["timing"] is None
    assert big["criteria"] == [
        {"key": "reach", "label": "Reach", "description": "How many customers it touches."}
    ]
    assert [t["key"] for t in body["triggers"]] == ["needs_setup"]
    assert body["triggers"][0]["context_key"] == "facts.needs_setup"
    by_key = {a["key"]: a for a in body["asset_types"]}
    assert list(by_key) == sorted(by_key)
    assert by_key["classify"] == {
        "key": "classify",
        "name": "Classify",
        "gate": "gate_one",
        "audience": "internal",
        "family": "classification",
        "foundation": True,
        "decides": "tier",
        "example_count": 1,
    }


def test_the_matrix_is_the_one_the_catalog_computes(login_as: Any, catalog_min: Catalog) -> None:
    body = login_as("viewer").get("/api/catalog/matrix").json()
    assert body["gates"] == [{"key": "gate_one", "short": "One"}, {"key": "gate_two", "short": "Two"}]
    assert body["undefined_assets"] == []
    # Same cells as `Catalog.matrix()` (S10), as names too, in gate order.
    for row in body["rows"]:
        expected = catalog_min.matrix()[row["tier"]["key"]]
        assert [[a["key"] for a in cell] for cell in row["cells"]] == list(expected.values())
    big, small = body["rows"]
    assert big["tier"] == {"key": "tier_big", "label": "Big"}
    assert big["cells"][1] == [{"key": "deep_dive", "name": "Deep dive"}]
    assert small["cells"][1] == []
    assert big["optional"] == [{"key": "extra_note", "name": "Extra note"}]
    assert small["optional"] == []
    assert big["triggers"] == [
        {
            "key": "needs_setup",
            "label": "Needs setup",
            "assets": [{"key": "setup_guide", "name": "Setup guide"}],
        }
    ]
    assert small["triggers"] == big["triggers"]  # the trigger applies to every tier


def test_an_asset_type_comes_with_its_prompt_rubric_examples_and_approvers(login_as: Any) -> None:
    body = login_as("viewer").get("/api/catalog/asset-types/deep_dive").json()
    assert body["spec"]["key"] == "deep_dive"
    assert body["spec"]["depends_on"] == ["brief"]
    assert body["approver_roles"] == ["role_a", "role_b"]  # gate_two's approvers
    assert body["prompt_md"].strip()
    assert body["rubric"]["pass_threshold"] > 0
    assert body["rubric"]["criteria"]
    assert set(body["rubric"]["criteria"][0]) == {"key", "title", "body_md"}
    [example] = body["examples"]
    assert example["body_md"].strip()
    assert {"slug", "title", "redacted", "why_good", "context_summary", "tier"} <= set(example)


def test_an_unknown_asset_type_is_404(login_as: Any) -> None:
    response = login_as("viewer").get("/api/catalog/asset-types/no_such_type")
    assert response.status_code == 404
    assert response.json() == {"detail": "no such asset type"}  # the key from the URL is not echoed back
    assert login_as("viewer").get(f"/api/catalog/asset-types/{'x' * 101}").status_code == 422


def test_the_brand_is_served_whole(login_as: Any, catalog_min: Catalog) -> None:
    body = login_as("viewer").get("/api/catalog/brand").json()
    assert body["voice_md"] == catalog_min.brand.voice_md
    assert body["claims_md"] == catalog_min.brand.claims_md
    assert body["legal_md"] == catalog_min.brand.legal_md
    assert body["terminology"] == catalog_min.brand.terminology.model_dump()
    assert body["visual"]["colors"] == catalog_min.brand.visual.colors


def test_health_says_which_catalog_is_loaded(client: TestClient, catalog_min: Catalog) -> None:
    body = client.get("/api/health").json()
    assert (body["catalog"], body["catalog_version"]) == ("ok", catalog_min.version_hash)


# ----------------------------------------------------------------- reload
def test_only_an_admin_may_reload(login_as: Any) -> None:
    assert login_as("viewer").post("/api/catalog/reload").status_code == 403
    assert login_as("pmm").post("/api/catalog/reload").status_code == 403  # an approver is not an admin
    assert login_as("admin", csrf=False).post("/api/catalog/reload").status_code == 403  # the CSRF header
    admin = login_as("admin")
    response = admin.post("/api/catalog/reload")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["old_hash"] == body["new_hash"]  # nothing changed
    assert body["issues"] == []


def test_a_reload_needs_a_session(client: TestClient) -> None:
    assert client.post("/api/catalog/reload", headers=CSRF).status_code == 401


def test_after_a_reload_the_activity_shows_who_did_it(login_as: Any) -> None:
    admin = login_as("admin")
    admin.post("/api/catalog/reload")
    [reloaded] = _catalog_events(admin, "catalog.reloaded")
    assert reloaded["actor_display"] == "Avery Admin"
    assert reloaded["details"]["errors"] == 0
    assert login_as("viewer").get("/api/activity").status_code == 403  # the trail itself stays admin-only


# ------------------------------------------------------- roles in /api/auth/me
def test_me_describes_each_role_with_the_catalogs_label_and_kind(
    client: TestClient, uow_factory: UnitOfWorkFactory, seeded: SeedSummary
) -> None:
    IdentityService(uow_factory).seed_dev_users(
        [DevUserSeed(id=ROLE_A_USER, email="a@example.test", display_name="A", roles=["role_a"])]
    )
    assert client.post("/api/auth/dev/login", json={"user_id": ROLE_A_USER}, headers=CSRF).status_code == 200
    me = client.get("/api/auth/me").json()
    assert me["roles"] == ["role_a"]
    assert me["role_info"] == [
        {"key": "role_a", "label": "Role A", "kind": "approver"}
    ]  # not the seed's label


def test_me_marks_the_system_roles(login_as: Any) -> None:
    info = login_as("admin").get("/api/auth/me").json()["role_info"]
    assert [(role["key"], role["kind"]) for role in info] == [("admin", "system")]
    assert info[0]["label"]


# ------------------------------------------------------- a catalog that changes
class TestFilesThatChange:
    """The app reads a writable copy of ``catalog_min``, so a test can edit it and reload."""

    @pytest.fixture
    def settings(self, settings: Settings, catalog_min_copy: Path) -> Settings:
        return settings.model_copy(update={"catalog_dir": catalog_min_copy})

    def test_a_reload_with_errors_is_409_with_the_issues_and_the_old_catalog_stays(
        self, login_as: Any, catalog_min_copy: Path, catalog_min: Catalog
    ) -> None:
        admin = login_as("admin")
        spec = catalog_min_copy / "asset_types" / "brief" / "spec.yaml"
        spec.write_text(
            spec.read_text(encoding="utf-8").replace("gate_one", "no_such_gate"), encoding="utf-8"
        )

        response = admin.post("/api/catalog/reload")

        assert response.status_code == 409
        body = response.json()
        assert body["ok"] is False
        assert body["old_hash"] == catalog_min.version_hash
        assert body["new_hash"] not in (None, catalog_min.version_hash)
        assert [(i["level"], i["where"]) for i in body["issues"]] == [
            ("error", "asset_types/brief/spec.yaml: gate")
        ]
        assert admin.get("/api/catalog").json()["version_hash"] == catalog_min.version_hash  # still served
        assert admin.get("/api/health").json()["catalog_version"] == catalog_min.version_hash
        [rejected] = _catalog_events(admin, "catalog.reload_rejected")
        assert (rejected["actor_display"], rejected["details"]["errors"]) == ("Avery Admin", 1)
        assert _catalog_events(admin, "catalog.reloaded") == []

    def test_an_edited_catalog_is_served_after_a_reload(self, login_as: Any, catalog_min_copy: Path) -> None:
        admin = login_as("admin")
        before = admin.get("/api/catalog").json()["version_hash"]
        lifecycle = catalog_min_copy / "lifecycle.yaml"
        lifecycle.write_text(
            lifecycle.read_text(encoding="utf-8").replace("Role A", "Role Alpha"), encoding="utf-8"
        )

        response = admin.post("/api/catalog/reload")

        assert response.status_code == 200
        after = response.json()["new_hash"]
        assert after != before
        assert admin.get("/api/catalog").json()["version_hash"] == after
        assert admin.get("/api/catalog").json()["roles"][0] == {"key": "role_a", "label": "Role Alpha"}
        assert admin.get("/api/health").json()["catalog_version"] == after
        # newest first: the reload's own sync, the reload, then the sync at start-up
        assert [e["action"] for e in _catalog_events(admin)] == [
            "catalog.roles_synced",
            "catalog.reloaded",
            "catalog.roles_synced",
        ]


class TestNoCatalog:
    """The app starts with an empty folder as its catalog: a state, not a crash (ADR-0005)."""

    @pytest.fixture
    def settings(self, settings: Settings, tmp_path: Path) -> Settings:
        empty = tmp_path / "empty_catalog"
        empty.mkdir()
        return settings.model_copy(update={"catalog_dir": empty})

    def test_every_read_answers_404_and_health_says_missing(self, login_as: Any) -> None:
        viewer = login_as("viewer")
        for path in GETS:
            response = viewer.get(path)
            assert (response.status_code, response.json()) == (404, {"detail": "no catalog loaded"}), path
        health = viewer.get("/api/health").json()
        assert (health["status"], health["catalog"], health["catalog_version"]) == ("ok", "missing", None)

    def test_a_reload_still_works_and_is_rejected_while_there_is_nothing_to_load(self, login_as: Any) -> None:
        admin = login_as("admin")
        response = admin.post("/api/catalog/reload")
        assert response.status_code == 409
        assert response.json()["old_hash"] is None
        assert response.json()["new_hash"] is None
        assert response.json()["issues"][0]["where"] == "lifecycle.yaml"
        assert admin.get("/api/catalog").status_code == 404

    def test_a_catalog_added_later_is_loaded_by_a_reload(
        self, login_as: Any, settings: Settings, catalog_min_dir: Path
    ) -> None:
        admin = login_as("admin")
        shutil.copytree(catalog_min_dir, settings.catalog_dir, dirs_exist_ok=True)

        response = admin.post("/api/catalog/reload")

        assert response.status_code == 200
        assert response.json()["old_hash"] is None
        assert admin.get("/api/catalog").status_code == 200
        assert admin.get("/api/health").json()["catalog"] == "ok"
