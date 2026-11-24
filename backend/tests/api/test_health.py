from fastapi.testclient import TestClient


def test_health_ok_without_authentication(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0", "env": "test"}


def test_health_is_only_under_api_prefix(client: TestClient) -> None:
    assert client.get("/health").status_code == 404
