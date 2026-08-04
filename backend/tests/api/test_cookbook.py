"""Task 9 Cookbook API privacy, 405, and tombstone delete tests."""

from __future__ import annotations

from .conftest import ApiClient, ApiServices, make_reviewable_draft

_PRIVATE_FIELDS = (
    "mode",
    "sourceDraftId",
    "gusComment",
    "internalProvenance",
    "visionModel",
    "textModel",
    "imageModel",
    "canonicalDishSignature",
    "promptVersions",
)


def _archive_draft(services: ApiServices, auth_client: ApiClient) -> dict[str, object]:
    reviewable = make_reviewable_draft(services)
    headers = {**auth_client.mutation_headers, "Idempotency-Key": "cb-key"}
    response = auth_client.client.post(
        f"/api/v1/drafts/{reviewable.draft_id}/archive",
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_cookbook_list_hides_source_fields(
    services: ApiServices,
    auth_client: ApiClient,
) -> None:
    _archive_draft(services, auth_client)

    response = auth_client.client.get(
        "/api/v1/cookbook",
        headers=auth_client.session_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["displayName"]
    for private_field in _PRIVATE_FIELDS:
        assert private_field not in response.text


def test_cookbook_detail_hides_source_fields(
    services: ApiServices,
    auth_client: ApiClient,
) -> None:
    dish = _archive_draft(services, auth_client)

    response = auth_client.client.get(
        f"/api/v1/cookbook/{dish['dishId']}",
        headers=auth_client.session_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["dishId"] == dish["dishId"]
    for private_field in _PRIVATE_FIELDS:
        assert private_field not in response.text


def test_cookbook_patch_returns_405(
    services: ApiServices,
    auth_client: ApiClient,
) -> None:
    dish = _archive_draft(services, auth_client)

    response = auth_client.client.patch(
        f"/api/v1/cookbook/{dish['dishId']}",
        headers=auth_client.mutation_headers,
        json={},
    )

    assert response.status_code == 405


def test_cookbook_delete_writes_tombstone_and_removes_from_list(
    services: ApiServices,
    auth_client: ApiClient,
) -> None:
    dish = _archive_draft(services, auth_client)

    delete_response = auth_client.client.delete(
        f"/api/v1/cookbook/{dish['dishId']}",
        headers=auth_client.mutation_headers,
    )

    assert delete_response.status_code == 204
    detail = auth_client.client.get(
        f"/api/v1/cookbook/{dish['dishId']}",
        headers=auth_client.session_headers,
    )
    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "PTS_COOKBOOK_NOT_FOUND"
    list_response = auth_client.client.get(
        "/api/v1/cookbook",
        headers=auth_client.session_headers,
    )
    assert list_response.json()["total"] == 0

    trash_dir = services.workspace.trash_dir / "cookbook" / str(dish["dishId"])
    assert (trash_dir / "record.json").exists()
    assert (trash_dir / "tombstone.json").exists()


def test_cookbook_repeat_delete_returns_404(
    services: ApiServices,
    auth_client: ApiClient,
) -> None:
    dish = _archive_draft(services, auth_client)
    first = auth_client.client.delete(
        f"/api/v1/cookbook/{dish['dishId']}",
        headers=auth_client.mutation_headers,
    )
    second = auth_client.client.delete(
        f"/api/v1/cookbook/{dish['dishId']}",
        headers=auth_client.mutation_headers,
    )

    assert first.status_code == 204
    assert second.status_code == 404
    assert second.json()["error"]["code"] == "PTS_COOKBOOK_NOT_FOUND"


def test_cookbook_unknown_id_returns_404(auth_client: ApiClient) -> None:
    response = auth_client.client.get(
        "/api/v1/cookbook/00000000-0000-4000-8000-000000000002",
        headers=auth_client.session_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PTS_COOKBOOK_NOT_FOUND"
