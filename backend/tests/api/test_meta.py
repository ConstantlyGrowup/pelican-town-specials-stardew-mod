"""Task refinement: dish category/tag option API tests."""

from __future__ import annotations

from .conftest import ApiClient, ApiServices


def test_meta_categories_requires_session(services: ApiServices) -> None:
    response = services.client.get(
        "/api/v1/meta/categories",
        params={},
        headers={"Host": "testserver"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "PTS_AUTH_SESSION_REQUIRED"


def test_meta_categories_returns_curated_list(auth_client: ApiClient) -> None:
    response = auth_client.client.get(
        "/api/v1/meta/categories",
        params={"limit": 20},
        headers=auth_client.session_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 5
    assert any(item["value"] == "主菜" for item in body["items"])


def test_meta_tags_returns_curated_list_and_filters(auth_client: ApiClient) -> None:
    all_tags = auth_client.client.get(
        "/api/v1/meta/tags",
        params={"limit": 20},
        headers=auth_client.session_headers,
    )
    assert all_tags.status_code == 200
    assert all_tags.json()["total"] >= 5

    filtered = auth_client.client.get(
        "/api/v1/meta/tags",
        params={"query": "辣"},
        headers=auth_client.session_headers,
    )
    assert filtered.status_code == 200
    assert all("辣" in item["value"] for item in filtered.json()["items"])
