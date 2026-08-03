from fastapi.testclient import TestClient

from pelican_town_specials.api.app import app, create_app
from pelican_town_specials.api.security import SecurityConfig, SecurityState


def _test_security_state() -> SecurityState:
    return SecurityState(
        config=SecurityConfig(
            allowed_hosts=frozenset({"testserver"}),
            expected_port=None,
        )
    )


def test_health_contract() -> None:
    response = TestClient(
        create_app(security_state=_test_security_state())
    ).get("/api/v1/health", headers={"Host": "testserver"})
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "PelicanTownSpecials",
        "apiVersion": "v1",
    }


def test_module_exports_uvicorn_application() -> None:
    assert app is not None
    assert app.title == create_app().title
