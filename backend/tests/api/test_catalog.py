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


def test_catalog_search_browses_all_ingredients_when_query_empty(
    auth_client: ApiClient,
) -> None:
    response = auth_client.client.get(
        "/api/v1/catalog/ingredients",
        params={"query": "", "limit": 5, "offset": 0},
        headers=auth_client.session_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 100
    assert len(body["items"]) == 5
    assert all(item["itemId"] != "-5" for item in body["items"])


def test_catalog_search_rejects_invalid_limit(auth_client: ApiClient) -> None:
    response = auth_client.client.get(
        "/api/v1/catalog/ingredients",
        params={"query": "tomat", "limit": 0},
        headers=auth_client.session_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PTS_INPUT_VALIDATION_FAILED"
