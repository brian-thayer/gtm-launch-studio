"""``api/errors.py``: one handler turns each domain exception into its status (ADR-0006)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gtm_studio.audit.middleware import REQUEST_ID_HEADER
from gtm_studio.domain.audit import InvalidCursorError
from gtm_studio.domain.errors import (
    ConflictError,
    DomainError,
    InvalidInputError,
    NotFoundError,
    NotPermittedError,
)

PROBES: dict[str, tuple[DomainError | Exception, int]] = {
    "not-found": (NotFoundError("no such thing"), 404),
    "conflict": (ConflictError("already there"), 409),
    "invalid": (InvalidInputError("bad value"), 422),
    "not-permitted": (NotPermittedError("not yours"), 403),
    "cursor": (InvalidCursorError(), 422),  # a subclass reaches its base class's status
}


@pytest.fixture
def probe_client(app: FastAPI) -> TestClient:
    """The real app (so the real middleware and handlers) plus a test-only route per exception."""

    @app.get("/api/test-probe/{name}")
    def probe(name: str) -> None:
        if name == "crash":
            raise RuntimeError("an unexpected bug")
        raise PROBES[name][0]

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("name", PROBES)
def test_each_domain_error_maps_to_its_status_and_detail(probe_client: TestClient, name: str) -> None:
    exc, status_code = PROBES[name]
    response = probe_client.get(f"/api/test-probe/{name}")
    assert response.status_code == status_code
    assert response.json() == {"detail": str(exc)}
    assert REQUEST_ID_HEADER in response.headers


def test_an_unexpected_exception_is_still_a_plain_500_with_a_request_id(probe_client: TestClient) -> None:
    response = probe_client.get("/api/test-probe/crash")
    assert response.status_code == 500
    assert response.text == "Internal Server Error"  # nothing about the exception reaches the client
    assert REQUEST_ID_HEADER in response.headers


def test_the_detail_is_the_one_the_service_chose() -> None:
    assert InvalidCursorError().detail == "invalid cursor"
    assert NotFoundError("gone").detail == "gone"
