from fastapi.testclient import TestClient

from pelican_town_specials.api.app import app, create_app


def test_health_contract() -> None:
    response = TestClient(create_app()).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "PelicanTownSpecials",
        "apiVersion": "v1",
    }


def test_module_exports_uvicorn_application() -> None:
    assert app is not None
    assert app.title == create_app().title
