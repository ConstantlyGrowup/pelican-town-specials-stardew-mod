from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pelican_town_specials.api.error_handlers import register_error_handlers


def test_unexpected_exception_message_is_not_written_to_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()
    sentinel = "sk-log-redaction-sentinel"

    @app.get("/unexpected")
    def unexpected_route() -> None:
        raise RuntimeError(f"unexpected failure containing {sentinel}")

    register_error_handlers(app)
    with caplog.at_level("ERROR"):
        response = TestClient(app, raise_server_exceptions=False).get("/unexpected")

    assert response.status_code == 500
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text
