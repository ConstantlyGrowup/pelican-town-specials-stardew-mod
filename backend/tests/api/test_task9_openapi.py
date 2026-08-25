"""Task 9 OpenAPI export contract tests."""

from __future__ import annotations

from .conftest import ApiServices

_TASK9_PATHS = {
    "/api/v1/assets/images",
    "/api/v1/assets/{asset_id}",
    "/api/v1/drafts",
    "/api/v1/drafts/{draft_id}",
    "/api/v1/drafts/{draft_id}/convert-to-blueprint",
    "/api/v1/drafts/{draft_id}/archive",
    "/api/v1/drafts/{draft_id}/discard",
    "/api/v1/cookbook",
    "/api/v1/cookbook/{dish_id}",
}

_TASK9_SCHEMAS = {
    "AssetView",
    "DraftCreateRequest",
    "DraftCreateSource",
    "DraftPatchRequest",
    "DraftView",
    "DraftSummary",
    "Page_DraftSummary_",
    "Page_CookbookDishSummary_",
    "CookbookDishSummary",
    "CookbookDishDetail",
}

_COOKBOOK_PRIVATE_FIELDS = {
    "mode",
    "sourceDraftId",
    "gusComment",
    "internalProvenance",
    "visionModel",
    "textModel",
    "imageModel",
    "canonicalDishSignature",
    "promptVersions",
}


def test_openapi_contains_all_task9_paths(services: ApiServices) -> None:
    schema = services.client.app.openapi()

    paths = set(schema["paths"])
    assert _TASK9_PATHS <= paths


def test_openapi_contains_task9_schemas(services: ApiServices) -> None:
    schema = services.client.app.openapi()

    components = set(schema["components"]["schemas"])
    assert _TASK9_SCHEMAS <= components


def test_cookbook_openapi_schemas_hide_source_fields(services: ApiServices) -> None:
    schema = services.client.app.openapi()
    schemas = schema["components"]["schemas"]

    for schema_name in ("CookbookDishSummary", "CookbookDishDetail"):
        properties = schemas[schema_name]["properties"]
        for private_field in _COOKBOOK_PRIVATE_FIELDS:
            assert private_field not in properties


def test_cookbook_openapi_has_no_patch(services: ApiServices) -> None:
    schema = services.client.app.openapi()

    assert "patch" not in schema["paths"]["/api/v1/cookbook/{dish_id}"]
    assert "patch" not in schema["paths"]["/api/v1/cookbook"]


def test_asset_view_openapi_excludes_relative_path(services: ApiServices) -> None:
    schema = services.client.app.openapi()
    properties = schema["components"]["schemas"]["AssetView"]["properties"]

    assert "relativePath" not in properties


def test_provenance_openapi_contains_canonical_reuse_extension(
    services: ApiServices,
) -> None:
    schema = services.client.app.openapi()
    provenance = schema["components"]["schemas"]["Provenance"]
    properties = provenance["properties"]

    assert properties["generationSource"]["$ref"] == (
        "#/components/schemas/GenerationSource"
    )
    assert properties["canonicalDishId"]["anyOf"] == [
        {"type": "string", "format": "uuid"},
        {"type": "null"},
    ]
    assert properties["recallConfidence"]["anyOf"] == [
        {"type": "number", "maximum": 1.0, "minimum": 0.0},
        {"type": "null"},
    ]
    assert properties["recallElapsedMs"]["anyOf"] == [
        {"type": "integer", "minimum": 0},
        {"type": "null"},
    ]
    assert schema["components"]["schemas"]["GenerationSource"]["enum"] == [
        "FRESH_GENERATION",
        "USER_AUTHORED",
        "CANONICAL_REUSED",
    ]
