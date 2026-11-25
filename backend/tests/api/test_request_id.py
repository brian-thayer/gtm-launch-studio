"""The request ID through the real app: middleware order, the access log and the audit trail."""

import uuid
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from gtm_studio.api.app import create_app
from gtm_studio.audit.middleware import REQUEST_ID_HEADER
from gtm_studio.settings import Settings

CSRF = {"X-Requested-With": "gtm-studio"}
StderrLogs = Callable[[], list[dict[str, Any]]]
LoginAs = Callable[..., TestClient]


def test_every_response_carries_a_request_id(app: FastAPI, login_as: LoginAs) -> None:
    anonymous = TestClient(app)
    for response in (
        anonymous.get("/api/health"),
        anonymous.get("/api/auth/me"),  # 401
        anonymous.get("/api/nowhere"),  # 404
        anonymous.post("/api/auth/logout"),  # 403: the CSRF middleware answers before the app does
        anonymous.post("/api/auth/dev/login", json={}, headers=CSRF),  # 422
        login_as("viewer").get("/api/activity"),  # 403
    ):
        assert uuid.UUID(response.headers[REQUEST_ID_HEADER]).version == 4, response.request.url


def test_a_caller_supplied_request_id_comes_back(login_as: LoginAs) -> None:
    response = login_as("viewer").get("/api/auth/me", headers={REQUEST_ID_HEADER: "from-the-proxy-1234"})
    assert response.headers[REQUEST_ID_HEADER] == "from-the-proxy-1234"


def test_the_access_line_has_the_request_id_and_the_actor(
    app: FastAPI, login_as: LoginAs, stderr_logs: StderrLogs
) -> None:
    viewer = login_as("viewer")
    viewer_id = viewer.get("/api/auth/me").json()["id"]
    stderr_logs()  # drop what logging in wrote

    response = viewer.get("/api/auth/me", params={"secret": "in-the-query"})
    anonymous = TestClient(app).get("/api/auth/me")

    signed_in, signed_out = (line for line in stderr_logs() if line["event"] == "request")
    assert signed_in["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert signed_in["actor_id"] == viewer_id
    assert (signed_in["method"], signed_in["path"], signed_in["status"]) == ("GET", "/api/auth/me", 200)
    assert signed_out["request_id"] == anonymous.headers[REQUEST_ID_HEADER]
    assert (signed_out["actor_id"], signed_out["status"]) == (None, 401)
    assert "in-the-query" not in str(signed_in)


def test_the_login_access_line_names_the_person_who_just_signed_in(
    app: FastAPI, login_as: LoginAs, stderr_logs: StderrLogs
) -> None:
    pmm_id = login_as("pmm").get("/api/auth/me").json()["id"]
    stderr_logs()
    TestClient(app).post("/api/auth/dev/login", json={"user_id": pmm_id}, headers=CSRF)
    [line] = [e for e in stderr_logs() if e["event"] == "request"]
    assert (line["path"], line["status"], line["actor_id"]) == ("/api/auth/dev/login", 200, pmm_id)


def test_the_audit_event_has_the_same_request_id_as_the_response(app: FastAPI, login_as: LoginAs) -> None:
    pmm_id = login_as("pmm").get("/api/auth/me").json()["id"]
    login = TestClient(app).post("/api/auth/dev/login", json={"user_id": pmm_id}, headers=CSRF)
    params = {"action_prefix": "auth.login", "actor_id": pmm_id}
    newest = login_as("admin").get("/api/activity", params=params).json()["items"][0]
    assert newest["request_id"] == login.headers[REQUEST_ID_HEADER]


def test_the_request_id_is_readable_cross_origin(settings: Settings, migrated_engine: Engine) -> None:
    cors = settings.model_copy(update={"cors_origins": ["https://app.example.test"]})
    with TestClient(create_app(cors)) as client:
        response = client.get("/api/health", headers={"Origin": "https://app.example.test"})
    assert response.headers["access-control-expose-headers"] == REQUEST_ID_HEADER
    assert REQUEST_ID_HEADER in response.headers
