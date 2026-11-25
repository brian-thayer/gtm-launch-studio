from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gtm_studio.audit.middleware import REQUEST_ID_HEADER
from gtm_studio.services.ports import UnitOfWorkFactory

CSRF = {"X-Requested-With": "gtm-studio"}
PMM_ID = "00000000-0000-4000-8000-000000000003"
MISSING_ID = "99999999-9999-4999-8999-999999999999"

LoginAs = Callable[..., TestClient]


def _activity(client: TestClient, path: str = "/api/activity", **params: Any) -> dict[str, Any]:
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _seed_events(uow_factory: UnitOfWorkFactory, count: int) -> None:
    """``count`` events, one transaction each, so each has its own timestamp."""
    for i in range(count):
        with uow_factory() as uow:
            uow.audit.record(None, "test.event", "thing", f"t-{i:03d}")


# ------------------------------------------------------------------ the identity events


def test_a_login_creates_an_event_with_the_request_details(app: FastAPI, login_as: LoginAs) -> None:
    anonymous = TestClient(app)
    login = anonymous.post(
        "/api/auth/dev/login",
        json={"user_id": PMM_ID},
        headers={**CSRF, "User-Agent": "pytest-agent/9.9", REQUEST_ID_HEADER: "login-request-0001"},
    )
    assert login.status_code == 200

    events = _activity(login_as("admin"), action_prefix="auth.login", actor_id=PMM_ID)["items"]
    [event] = [e for e in events if e["request_id"] == "login-request-0001"]
    assert event["action"] == "auth.login"
    assert (event["actor_user_id"], event["actor_display"]) == (PMM_ID, "Priya Marketing")
    assert (event["entity_type"], event["entity_id"]) == ("user", PMM_ID)
    assert event["details"] == {"provider": "dev"}
    assert event["ip"] == "testclient"
    assert event["user_agent"] == "pytest-agent/9.9"
    assert event["occurred_at"].endswith(("Z", "+00:00"))


def test_logout_and_a_denied_login_are_audited(app: FastAPI, login_as: LoginAs) -> None:
    pmm = login_as("pmm")
    assert pmm.post("/api/auth/logout", headers=CSRF).status_code == 204
    denied = TestClient(app).post("/api/auth/dev/login", json={"user_id": MISSING_ID}, headers=CSRF)
    assert denied.status_code == 404

    events = _activity(login_as("admin"), action_prefix="auth.")["items"]
    by_action = {e["action"]: e for e in events if e["action"] != "auth.login"}
    assert by_action["auth.logout"]["actor_user_id"] == PMM_ID
    assert by_action["auth.login_denied"]["actor_user_id"] is None
    assert by_action["auth.login_denied"]["entity_id"] == MISSING_ID
    assert by_action["auth.login_denied"]["ip"] == "testclient"


def test_an_inactive_users_login_is_denied_and_audited(
    app: FastAPI, login_as: LoginAs, uow_factory: UnitOfWorkFactory
) -> None:
    with uow_factory() as uow:
        record = uow.identity.get_user(PMM_ID)
        assert record is not None
        uow.identity.upsert_user(replace(record, is_active=False))
    assert (
        TestClient(app).post("/api/auth/dev/login", json={"user_id": PMM_ID}, headers=CSRF).status_code == 404
    )

    events = _activity(login_as("admin"), action_prefix="auth.login_denied")["items"]
    assert [(e["entity_id"], e["actor_user_id"]) for e in events] == [(PMM_ID, None)]


def test_a_login_that_does_not_happen_leaves_no_login_event(app: FastAPI, login_as: LoginAs) -> None:
    TestClient(app).post("/api/auth/dev/login", json={"user_id": PMM_ID})  # no CSRF header: refused
    events = _activity(login_as("admin"), action_prefix="auth.", actor_id=PMM_ID)["items"]
    assert events == []


# ------------------------------------------------------------------ who may read


def test_only_the_audit_permission_may_read_everyones_activity(app: FastAPI, login_as: LoginAs) -> None:
    assert login_as("viewer").get("/api/activity").status_code == 403
    assert login_as("pmm").get("/api/activity").status_code == 403
    assert login_as("admin").get("/api/activity").status_code == 200
    assert TestClient(app).get("/api/activity").status_code == 401


def test_anyone_signed_in_may_read_their_own_activity(app: FastAPI, login_as: LoginAs) -> None:
    for role in ("viewer", "pmm", "admin"):
        assert login_as(role).get("/api/activity/me").status_code == 200
    assert TestClient(app).get("/api/activity/me").status_code == 401


def test_my_activity_is_only_mine(login_as: LoginAs) -> None:
    viewer, pmm = login_as("viewer"), login_as("pmm")
    pmm.post("/api/auth/logout", headers=CSRF)  # ends pmm's session: log in again below
    pmm = login_as("pmm")

    mine = _activity(pmm, "/api/activity/me")["items"]
    assert {e["actor_user_id"] for e in mine} == {PMM_ID}
    assert [e["action"] for e in mine] == ["auth.login", "auth.logout", "auth.login"]

    viewer_events = _activity(viewer, "/api/activity/me")["items"]
    assert {e["actor_user_id"] for e in viewer_events} == {viewer.get("/api/auth/me").json()["id"]}
    assert PMM_ID not in {e["actor_user_id"] for e in viewer_events}


def test_my_activity_ignores_an_actor_id_parameter(login_as: LoginAs) -> None:
    pmm, admin = login_as("pmm"), login_as("admin")
    admin_id = admin.get("/api/auth/me").json()["id"]
    events = _activity(pmm, "/api/activity/me", actor_id=admin_id)["items"]
    assert {e["actor_user_id"] for e in events} == {PMM_ID}


# ------------------------------------------------------------------ pagination


def test_cursor_pagination_over_120_events(login_as: LoginAs, uow_factory: UnitOfWorkFactory) -> None:
    admin = login_as("admin")
    _seed_events(uow_factory, 120)

    pages: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"action_prefix": "test.", "limit": 50}
        if cursor is not None:
            params["cursor"] = cursor
        page = _activity(admin, **params)
        pages.append(page)
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert [len(p["items"]) for p in pages] == [50, 50, 20]
    assert all(p["next_cursor"] for p in pages[:-1])
    items = [e for p in pages for e in p["items"]]
    assert len({e["id"] for e in items}) == 120  # no event twice
    assert [e["entity_id"] for e in items] == [f"t-{i:03d}" for i in range(119, -1, -1)]  # newest first


def test_the_default_page_is_50_and_a_cursor_is_opaque_text(
    login_as: LoginAs, uow_factory: UnitOfWorkFactory
) -> None:
    admin = login_as("admin")
    _seed_events(uow_factory, 60)
    page = _activity(admin, action_prefix="test.")
    assert len(page["items"]) == 50
    assert isinstance(page["next_cursor"], str)
    assert "t-" not in page["next_cursor"]


@pytest.mark.parametrize("limit", [0, 201, -1, "many"])
def test_a_limit_outside_1_to_200_is_rejected(login_as: LoginAs, limit: int | str) -> None:
    assert login_as("admin").get("/api/activity", params={"limit": limit}).status_code == 422


def test_the_largest_page_is_allowed(login_as: LoginAs) -> None:
    assert login_as("admin").get("/api/activity", params={"limit": 200}).status_code == 200


def test_a_cursor_that_was_not_issued_here_is_a_422(login_as: LoginAs) -> None:
    admin = login_as("admin")
    for path in ("/api/activity", "/api/activity/me"):
        response = admin.get(path, params={"cursor": "garbage"})
        assert response.status_code == 422
        assert response.json() == {"detail": "invalid cursor"}


# ------------------------------------------------------------------ filters


def test_filters(login_as: LoginAs, uow_factory: UnitOfWorkFactory) -> None:
    admin = login_as("admin")
    with uow_factory() as uow:
        uow.audit.record(None, "asset.approved", "asset", "a-1")
        uow.audit.record(None, "asset.rejected", "asset", "a-2")
        uow.audit.record(None, "catalog.reloaded", "catalog", "c-1")

    def actions(**params: str) -> list[str]:
        return [e["action"] for e in _activity(admin, **params)["items"]]

    assert actions(action_prefix="asset.") == ["asset.rejected", "asset.approved"]
    assert actions(entity_type="catalog") == ["catalog.reloaded"]
    assert actions(entity_type="asset", entity_id="a-1") == ["asset.approved"]
    assert actions(entity_id="c-1", action_prefix="catalog.") == ["catalog.reloaded"]
    assert actions(entity_type="asset", entity_id="c-1") == []
    admin_id = admin.get("/api/auth/me").json()["id"]
    assert set(actions(actor_id=admin_id)) == {"auth.login"}
    assert actions(actor_id=MISSING_ID) == []


def test_my_activity_can_be_filtered_too(login_as: LoginAs) -> None:
    pmm = login_as("pmm")
    pmm.post("/api/auth/logout", headers=CSRF)
    pmm = login_as("pmm")
    logins = _activity(pmm, "/api/activity/me", action_prefix="auth.login")["items"]
    assert [e["action"] for e in logins] == ["auth.login", "auth.login"]
    assert _activity(pmm, "/api/activity/me", entity_type="asset")["items"] == []


def test_an_overlong_filter_is_rejected(login_as: LoginAs) -> None:
    assert login_as("admin").get("/api/activity", params={"entity_id": "x" * 101}).status_code == 422
