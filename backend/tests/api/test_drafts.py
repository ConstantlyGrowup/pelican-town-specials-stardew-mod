"""Task 9 draft lifecycle API contract tests."""

from __future__ import annotations

import io

from PIL import Image

from .conftest import ApiClient, ApiServices, make_reviewable_draft


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(output, format="PNG")
    return output.getvalue()


def _upload(auth_client: ApiClient) -> dict[str, object]:
    response = auth_client.client.post(
        "/api/v1/assets/images",
        headers=auth_client.mutation_headers,
        files={"file": ("photo.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_blueprint(auth_client: ApiClient, asset_id: object) -> dict[str, object]:
    response = auth_client.client.post(
        "/api/v1/drafts",
        headers=auth_client.mutation_headers,
        json={
            "mode": "BLUEPRINT",
            "language": "zh-CN",
            "source": {"originalImageAssetId": str(asset_id)},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _presentation() -> dict[str, object]:
    return {
        "displayName": "南瓜汤",
        "internalName": "PumpkinSoup",
        "categoryLabel": "汤类",
        "description": "香甜的南瓜汤。",
        "tags": ["fall", "soup"],
    }


def test_create_blueprint_draft_returns_blueprint_template(
    auth_client: ApiClient,
) -> None:
    uploaded = _upload(auth_client)
    body = _create_blueprint(auth_client, uploaded["assetId"])

    assert body["mode"] == "BLUEPRINT"
    assert body["baseTemplateVersion"] == "blueprint-v1"
    assert body["status"] == "DRAFT"
    assert body["revision"] == 1
    assert body["analysis"] is None
    assert body["presentation"] is None
    assert body["gameplay"] is None
    assert body["visuals"] is None
    assert body["source"]["originalImageAssetId"] == uploaded["assetId"]
    assert body["provenance"]["mode"] == "BLUEPRINT"
    assert body["provenance"]["cacheEligibility"] is False
    assert body["provenance"]["visionModel"] is None
    assert body["provenance"]["textModel"] is None
    assert body["provenance"]["imageModel"] is None
    assert (
        body["provenance"]["authorityByField"]["gameplay.buff"] == "USER_ASSIGNED"
    )


def test_create_draft_rejects_oversized_context_text(
    auth_client: ApiClient,
) -> None:
    uploaded = _upload(auth_client)

    response = auth_client.client.post(
        "/api/v1/drafts",
        headers=auth_client.mutation_headers,
        json={
            "mode": "BLUEPRINT",
            "language": "zh-CN",
            "source": {
                "originalImageAssetId": str(uploaded["assetId"]),
                "contextText": "x" * 501,
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PTS_INPUT_VALIDATION_FAILED"


def test_list_drafts_returns_page(auth_client: ApiClient) -> None:
    uploaded = _upload(auth_client)
    _create_blueprint(auth_client, uploaded["assetId"])

    response = auth_client.client.get(
        "/api/v1/drafts",
        headers=auth_client.session_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["nextCursor"] is None
    assert body["page"] == 1
    assert body["pageSize"] == 10
    assert body["totalPages"] == 1
    assert body["hasRunningGeneration"] is False
    assert body["items"][0]["mode"] == "BLUEPRINT"
    assert body["items"][0]["displayName"] == ""
    assert body["items"][0]["originalImageAssetId"] == uploaded["assetId"]
    assert body["items"][0]["createdAt"] == body["items"][0]["updatedAt"]


def test_list_drafts_honors_pagination_query(auth_client: ApiClient) -> None:
    uploaded = _upload(auth_client)
    for _index in range(3):
        _create_blueprint(auth_client, uploaded["assetId"])

    response = auth_client.client.get(
        "/api/v1/drafts",
        headers=auth_client.session_headers,
        params={"page": 2, "pageSize": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["page"] == 2
    assert body["pageSize"] == 2
    assert body["totalPages"] == 2
    assert len(body["items"]) == 1


def test_list_drafts_accepts_created_at_sort_query(auth_client: ApiClient) -> None:
    uploaded = _upload(auth_client)
    _create_blueprint(auth_client, uploaded["assetId"])

    response = auth_client.client.get(
        "/api/v1/drafts",
        headers=auth_client.session_headers,
        params={"sortBy": "createdAt", "sortOrder": "asc", "pageSize": 100},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["page"] == 1


def test_list_drafts_rejects_unknown_sort_values(auth_client: ApiClient) -> None:
    bad = auth_client.client.get(
        "/api/v1/drafts",
        headers=auth_client.session_headers,
        params={"sortBy": "bogus", "sortOrder": "sideways"},
    )
    assert bad.status_code == 422

    zero_page = auth_client.client.get(
        "/api/v1/drafts",
        headers=auth_client.session_headers,
        params={"page": 0},
    )
    assert zero_page.status_code == 422

    oversized = auth_client.client.get(
        "/api/v1/drafts",
        headers=auth_client.session_headers,
        params={"pageSize": 101},
    )
    assert oversized.status_code == 422


def test_get_draft_returns_draft_view(auth_client: ApiClient) -> None:
    uploaded = _upload(auth_client)
    created = _create_blueprint(auth_client, uploaded["assetId"])

    response = auth_client.client.get(
        f"/api/v1/drafts/{created['draftId']}",
        headers=auth_client.session_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["draftId"] == created["draftId"]
    assert body["baseTemplateVersion"] == "blueprint-v1"


def test_get_unknown_draft_returns_404(auth_client: ApiClient) -> None:
    response = auth_client.client.get(
        "/api/v1/drafts/00000000-0000-4000-8000-000000000001",
        headers=auth_client.session_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PTS_DRAFT_NOT_FOUND"


def test_convert_to_blueprint_only_copies_original_image(
    services: ApiServices,
    auth_client: ApiClient,
) -> None:
    reviewable = make_reviewable_draft(services)

    response = auth_client.client.post(
        f"/api/v1/drafts/{reviewable.draft_id}/convert-to-blueprint",
        headers=auth_client.mutation_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mode"] == "BLUEPRINT"
    assert body["baseTemplateVersion"] == "blueprint-v1"
    assert (
        body["source"]["originalImageAssetId"]
        == str(reviewable.source.original_image_asset_id)
    )
    assert body["source"]["contextText"] is None
    assert body["analysis"] is None
    assert body["presentation"] is None
    assert body["gameplay"] is None
    assert body["visuals"] is None
    assert body["provenance"]["visionModel"] is None
    assert body["provenance"]["promptVersions"] == {}


def test_convert_to_blueprint_rejects_blueprint_source(
    auth_client: ApiClient,
) -> None:
    uploaded = _upload(auth_client)
    blueprint = _create_blueprint(auth_client, uploaded["assetId"])

    response = auth_client.client.post(
        f"/api/v1/drafts/{blueprint['draftId']}/convert-to-blueprint",
        headers=auth_client.mutation_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PTS_STATE_ILLEGAL_TRANSITION"


def test_patch_blueprint_accepts_gameplay_recipe_unlock_string(
    auth_client: ApiClient,
) -> None:
    uploaded = _upload(auth_client)
    created = _create_blueprint(auth_client, uploaded["assetId"])

    response = auth_client.client.patch(
        f"/api/v1/drafts/{created['draftId']}",
        headers=auth_client.mutation_headers,
        json={
            "expectedRevision": created["revision"],
            "gameplay": {
                "ingredients": [
                    {
                        "itemId": "24",
                        "displayName": "Parsnip",
                        "quantity": 1,
                        "mappingReason": "catalog match",
                        "catalogVersion": "stardew-1.6.15-v1",
                    }
                ],
                "recovery": {"edibility": 20},
                "sellPrice": 35,
                "isDrink": False,
                "recipeUnlock": "DEFAULT",
            },
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["gameplay"]["recipeUnlock"] == "DEFAULT"


def test_patch_blueprint_updates_fields_and_bumps_revision(
    auth_client: ApiClient,
) -> None:
    uploaded = _upload(auth_client)
    created = _create_blueprint(auth_client, uploaded["assetId"])

    response = auth_client.client.patch(
        f"/api/v1/drafts/{created['draftId']}",
        headers=auth_client.mutation_headers,
        json={
            "expectedRevision": created["revision"],
            "presentation": _presentation(),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == created["revision"] + 1
    assert body["presentation"]["displayName"] == "南瓜汤"
    assert body["status"] == "DRAFT"
    assert body["provenance"]["authorityByField"]["presentation.display_name"] == (
        "USER_ASSIGNED"
    )


def test_patch_requires_expected_revision(auth_client: ApiClient) -> None:
    uploaded = _upload(auth_client)
    created = _create_blueprint(auth_client, uploaded["assetId"])

    response = auth_client.client.patch(
        f"/api/v1/drafts/{created['draftId']}",
        headers=auth_client.mutation_headers,
        json={"presentation": _presentation()},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PTS_INPUT_VALIDATION_FAILED"


def test_patch_stale_revision_conflicts(auth_client: ApiClient) -> None:
    uploaded = _upload(auth_client)
    created = _create_blueprint(auth_client, uploaded["assetId"])

    response = auth_client.client.patch(
        f"/api/v1/drafts/{created['draftId']}",
        headers=auth_client.mutation_headers,
        json={
            "expectedRevision": created["revision"] + 5,
            "presentation": _presentation(),
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PTS_STATE_REVISION_CONFLICT"


def test_patch_ask_gus_is_rejected(
    services: ApiServices,
    auth_client: ApiClient,
) -> None:
    reviewable = make_reviewable_draft(services)

    response = auth_client.client.patch(
        f"/api/v1/drafts/{reviewable.draft_id}",
        headers=auth_client.mutation_headers,
        json={
            "expectedRevision": reviewable.revision,
            "presentation": _presentation(),
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PTS_STATE_ILLEGAL_TRANSITION"


def test_archive_reviewable_draft_is_idempotent(
    services: ApiServices,
    auth_client: ApiClient,
) -> None:
    reviewable = make_reviewable_draft(services)
    headers = {**auth_client.mutation_headers, "Idempotency-Key": "api-archive-key"}

    first = auth_client.client.post(
        f"/api/v1/drafts/{reviewable.draft_id}/archive",
        headers=headers,
    )
    second = auth_client.client.post(
        f"/api/v1/drafts/{reviewable.draft_id}/archive",
        headers=headers,
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201
    assert first.json()["dishId"] == second.json()["dishId"]
    assert "mode" not in first.text
    assert "sourceDraftId" not in first.text


def test_archive_non_reviewable_draft_rejected(auth_client: ApiClient) -> None:
    uploaded = _upload(auth_client)
    created = _create_blueprint(auth_client, uploaded["assetId"])

    response = auth_client.client.post(
        f"/api/v1/drafts/{created['draftId']}/archive",
        headers={**auth_client.mutation_headers, "Idempotency-Key": "key"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PTS_STATE_ILLEGAL_TRANSITION"


def test_discard_draft_returns_204_and_deletes(auth_client: ApiClient) -> None:
    uploaded = _upload(auth_client)
    created = _create_blueprint(auth_client, uploaded["assetId"])

    response = auth_client.client.post(
        f"/api/v1/drafts/{created['draftId']}/discard",
        headers=auth_client.mutation_headers,
    )

    assert response.status_code == 204
    detail = auth_client.client.get(
        f"/api/v1/drafts/{created['draftId']}",
        headers=auth_client.session_headers,
    )
    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "PTS_DRAFT_NOT_FOUND"

    listing = auth_client.client.get(
        "/api/v1/drafts",
        headers=auth_client.session_headers,
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 0
