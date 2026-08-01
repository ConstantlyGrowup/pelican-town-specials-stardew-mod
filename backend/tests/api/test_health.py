from fastapi.testclient import TestClient

from pelican_town_specials.api.app import create_app


def test_health_contract() -> None:
    response = TestClient(create_app()).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "PelicanTownSpecials",
        "apiVersion": "v1",
    }
