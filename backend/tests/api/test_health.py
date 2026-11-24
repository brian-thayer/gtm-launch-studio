from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from gtm_studio.api.app import create_app
from gtm_studio.api.deps import get_session
from gtm_studio.settings import Settings


def test_health_ok_without_authentication(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0", "env": "test", "db": "ok"}


def test_health_is_only_under_api_prefix(client: TestClient) -> None:
    assert client.get("/health").status_code == 404


class _BrokenSession:
    def execute(self, *_args: object, **_kwargs: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("unable to open database file"))


def test_health_reports_a_database_error_instead_of_failing(settings: Settings) -> None:
    app = create_app(settings)

    def broken_session() -> Iterator[_BrokenSession]:
        yield _BrokenSession()

    app.dependency_overrides[get_session] = broken_session
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["db"] == "error"
