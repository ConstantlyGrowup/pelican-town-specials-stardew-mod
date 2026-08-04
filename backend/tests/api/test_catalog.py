"""Task 10 catalog search API contract tests."""

from __future__ import annotations

from .conftest import ApiClient, ApiServices


def test_catalog_search_requires_session(services: ApiServices) -> None:
    response = services.client.get(
        "/api/v1/catalog/ingredients",
        params={"query": "tomat"},
        headers={"Host": "testserver"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "PTS_AUTH_SESSION_REQUIRED"


def test_catalog_search_returns_usable_results(auth_client: ApiClient) -> None:
    response = auth_client.client.get(
        "/api/v1/catalog/ingredients",
        params={"query": "tomat", "limit": 10},
        headers=auth_client.session_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["catalogVersion"] == "stardew-1.6.15-v1"
    assert body["items"]
    for item in body["items"]:
        assert set(item) == {"itemId", "displayNameEn", "displayNameZh"}
        assert item["itemId"] != "-5"


def test_catalog_search_excludes_non_usable(auth_client: ApiClient) -> None:
    response = auth_client.client.get(
        "/api/v1/catalog/ingredients",
        params={"query": "349"},
        headers=auth_client.session_headers,
    )

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_catalog_search_rejects_empty_query(auth_client: ApiClient) -> None:
    response = auth_client.client.get(
        "/api/v1/catalog/ingredients",
        params={"query": ""},
        headers=auth_client.session_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PTS_INPUT_VALIDATION_FAILED"


def test_catalog_search_rejects_invalid_limit(auth_client: ApiClient) -> None:
    response = auth_client.client.get(
        "/api/v1/catalog/ingredients",
        params={"query": "tomat", "limit": 0},
        headers=auth_client.session_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PTS_INPUT_VALIDATION_FAILED"
